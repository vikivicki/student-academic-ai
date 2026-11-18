
import { useEffect, useState } from 'react'
import API from './api'
import './App.css'

const emptySignup = {
  college_name: '',
  college_slug: '',
  admin_name: '',
  admin_email: '',
  password: '',
}

// Convert API errors into readable text for React
const getErrorMessage = (err, fallback) => {
  const detail = err?.response?.data?.detail

  if (typeof detail === 'string') return detail

  if (Array.isArray(detail)) {
    return detail
      .map((item) =>
        typeof item === 'string'
          ? item
          : item?.msg || JSON.stringify(item)
      )
      .join('; ')
  }

  if (detail && typeof detail === 'object') {
    return detail.msg || detail.message || JSON.stringify(detail)
  }

  return err?.message || fallback
}

// Format academic eligibility results or JSON strings
const formatAssistantResponse = (answer) => {
  let data = answer

  if (typeof data === 'string') {
    const trimmed = data.trim()
    const withoutFence = trimmed
      .replace(/^```(?:json)?\s*/i, '')
      .replace(/\s*```$/, '')

    try {
      data = JSON.parse(withoutFence)
    } catch {
      return answer
    }
  }

  if (!data || typeof data !== 'object') {
    return String(data ?? 'No answer was returned.')
  }

  // Handle API responses wrapped in an answer property
  if (
    !data.eligibility_status &&
    data.answer !== undefined &&
    data.answer !== answer
  ) {
    return formatAssistantResponse(data.answer)
  }

  // Format academic eligibility response
  if (data.eligibility_status || data.status === 'evaluated') {
    const attendance = data.attendance || {}
    const assessments = Array.isArray(data.assessments)
      ? data.assessments
      : []

    const lines = [
      `ACADEMIC ELIGIBILITY REPORT`,
      `Student ID: ${data.student_id || 'Not available'}`,
      `Course ID: ${data.course_id || 'Not available'}`,
      `Result: ${data.eligibility_status || 'Unable to determine'}`,
      `Reference date: ${data.reference_date || 'Not provided'}`,
      '',
      'ATTENDANCE',
      `Attendance: ${attendance.percentage ?? 'Not available'}%`,
      `Classes attended: ${attendance.classes_attended ?? 'Not available'} / ${attendance.total_classes ?? 'Not available'}`,
      `Minimum required: ${attendance.minimum_required ?? 'Not available'}%`,
      '',
      'ASSESSMENTS',
    ]

    if (assessments.length > 0) {
      assessments.forEach((item) => {
        lines.push(
          `Assessment: ${item.assessment || 'Not available'}`,
          `Marks: ${item.marks_obtained ?? 'N/A'} / ${item.total_marks ?? 'N/A'}`,
          `Percentage: ${item.percentage ?? 'N/A'}%`,
          `Status: ${
            item.passed === true
              ? 'Passed'
              : item.passed === false
                ? 'Failed'
                : 'Not evaluated'
          }`,
          ''
        )
      })
    } else {
      lines.push('No assessment records returned.')
    }

    if (
      Array.isArray(data.missing_assessments) &&
      data.missing_assessments.length > 0
    ) {
      lines.push(
        '',
        'MISSING ASSESSMENTS',
        ...data.missing_assessments.map((item) => `- ${item}`)
      )
    }

    if (
      Array.isArray(data.failed_assessments) &&
      data.failed_assessments.length > 0
    ) {
      lines.push(
        '',
        'FAILED ASSESSMENTS',
        ...data.failed_assessments.map((item) => `- ${item}`)
      )
    }

    if (Array.isArray(data.reasons) && data.reasons.length > 0) {
      lines.push('', 'REASONS')

      data.reasons.forEach((reason) => {
        lines.push(`- ${reason}`)
      })
    }

    return lines.join('\n')
  }

  // Format other objects instead of rendering raw JSON
  return Object.entries(data)
    .map(([key, value]) => {
      const label = key
        .replace(/_/g, ' ')
        .replace(/\b\w/g, (letter) => letter.toUpperCase())

      const readableValue =
        value && typeof value === 'object'
          ? JSON.stringify(value)
          : String(value ?? 'Not provided')

      return `${label}: ${readableValue}`
    })
    .join('\n')
}

function App() {
  const [screen, setScreen] = useState('login')

  const [signup, setSignup] = useState(emptySignup)

  const [login, setLogin] = useState({
    college_slug: '',
    email: '',
    password: '',
  })

  const [session, setSession] = useState(null)
  const [profile, setProfile] = useState(null)
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState([])
  const [students, setStudents] = useState([])

  const [newStudent, setNewStudent] = useState({
    full_name: '',
    email: '',
    password: '',
    student_id: '',
  })

  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')

  const clearMessages = () => {
    setError('')
    setNotice('')
  }

  const clearChat = () => {
    setMessages([
      {
        role: 'assistant',
        content: `Welcome to ${
          profile?.name || session?.college?.name || 'your college'
        }. Ask me about attendance, marks, courses, mentors or academic policies.`,
      },
    ])

    setQuestion('')
    setError('')
    setNotice('')
  }

  const loadProfile = async () => {
    try {
      const response = await API.get('/college/profile')
      setProfile(response.data)
    } catch {
      localStorage.removeItem('student_agent_token')
      localStorage.removeItem('student_agent_session')
      setSession(null)
    }
  }

  const loadStudents = async () => {
    try {
      const response = await API.get('/admin/students')
      setStudents(response.data.students || [])
    } catch (err) {
      setError(
        getErrorMessage(err, 'Could not load student accounts.')
      )
    }
  }

  // Restore existing login session
  useEffect(() => {
    const token = localStorage.getItem('student_agent_token')
    const saved = localStorage.getItem('student_agent_session')

    if (token && saved) {
      try {
        const parsed = JSON.parse(saved)
        setSession(parsed)
        loadProfile()
      } catch {
        localStorage.removeItem('student_agent_token')
        localStorage.removeItem('student_agent_session')
      }
    }
  }, [])

  // Load students for college administrator
  useEffect(() => {
    if (session?.user?.role === 'admin') {
      loadStudents()
    }
  }, [session])

  // College login
  const handleLogin = async (event) => {
    event.preventDefault()
    clearMessages()
    setBusy(true)

    try {
      const response = await API.post('/auth/login', login)
      const data = response.data

      localStorage.setItem(
        'student_agent_token',
        data.access_token
      )

      localStorage.setItem(
        'student_agent_session',
        JSON.stringify(data)
      )

      setSession(data)
      setProfile(data.college)

      setMessages([
        {
          role: 'assistant',
          content: `Welcome to ${data.college.name}. Ask me about attendance, marks, courses, mentors or academic policies.`,
        },
      ])

      setNotice('Login successful.')
    } catch (err) {
      setError(
        getErrorMessage(
          err,
          'Login failed. Check your college URL name, email and password.'
        )
      )
    } finally {
      setBusy(false)
    }
  }

  // Register a new college
  const handleRegister = async (event) => {
    event.preventDefault()
    clearMessages()
    setBusy(true)

    try {
      const response = await API.post(
        '/auth/register-college',
        signup
      )

      setNotice(
        `${response.data.message} Your college URL name is "${response.data.college_slug}". Please log in.`
      )

      setLogin({
        college_slug: response.data.college_slug,
        email: signup.admin_email,
        password: '',
      })

      setSignup(emptySignup)
      setScreen('login')
    } catch (err) {
      setError(
        getErrorMessage(err, 'Could not create college account.')
      )
    } finally {
      setBusy(false)
    }
  }

  // Send question to academic assistant
  const sendMessage = async (event) => {
    event.preventDefault()

    if (!question.trim() || busy) return

    const prompt = question.trim()

    setQuestion('')

    setMessages((old) => [
      ...old,
      { role: 'user', content: prompt },
    ])

    setBusy(true)
    clearMessages()

    try {
      const response = await API.post('/chat', {
        question: prompt,
      })

      setMessages((old) => [
        ...old,
        {
          role: 'assistant',
          content: formatAssistantResponse(
            response.data.answer ?? response.data
          ),
        },
      ])
    } catch (err) {
      const detail = getErrorMessage(
        err,
        'Could not connect to the academic assistant. Check that the backend is running.'
      )

      setMessages((old) => [
        ...old,
        { role: 'assistant', content: detail },
      ])
    } finally {
      setBusy(false)
    }
  }

  // Create a student account
  const addStudent = async (event) => {
    event.preventDefault()
    clearMessages()
    setBusy(true)

    try {
      await API.post('/admin/students', newStudent)

      setNotice('Student account created successfully.')

      setNewStudent({
        full_name: '',
        email: '',
        password: '',
        student_id: '',
      })

      await loadStudents()
    } catch (err) {
      setError(
        getErrorMessage(err, 'Could not create student account.')
      )
    } finally {
      setBusy(false)
    }
  }

  // Upload college logo
  const uploadLogo = async (event) => {
    const file = event.target.files?.[0]

    if (!file) return

    clearMessages()

    const form = new FormData()
    form.append('file', file)

    setBusy(true)

    try {
      await API.post('/college/logo', form, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      })

      await loadProfile()
      setNotice('College logo updated.')
    } catch (err) {
      setError(
        getErrorMessage(err, 'Logo upload failed.')
      )
    } finally {
      setBusy(false)
      event.target.value = ''
    }
  }

  // Logout
  const logout = () => {
    localStorage.removeItem('student_agent_token')
    localStorage.removeItem('student_agent_session')

    setSession(null)
    setProfile(null)
    setMessages([])
    setScreen('login')

    clearMessages()
  }

  const logoUrl = profile?.logo_path || profile?.logo_url

  const fullLogoUrl = logoUrl?.startsWith('http')
    ? logoUrl
    : logoUrl
      ? `${API.defaults.baseURL}${logoUrl}`
      : ''

  // Login and college registration screen
  if (!session) {
    return (
      <div className="auth-shell">
        <div className="auth-card">
          <div className="brand-mark">EA</div>

          <p className="eyebrow">
            STUDENT ACADEMICS PLATFORM
          </p>

          <h1>
            {screen === 'register'
              ? 'Register your college'
              : 'Welcome back'}
          </h1>

          <p className="muted">
            {screen === 'register'
              ? 'Create a separate academic portal for your institution.'
              : 'Sign in to your college academic portal.'}
          </p>

          <div className="auth-tabs">
            <button
              className={screen === 'login' ? 'selected' : ''}
              onClick={() => {
                setScreen('login')
                clearMessages()
              }}
            >
              Login
            </button>

            <button
              className={screen === 'register' ? 'selected' : ''}
              onClick={() => {
                setScreen('register')
                clearMessages()
              }}
            >
              Register college
            </button>
          </div>

          {error && (
            <div className="alert error">{error}</div>
          )}

          {notice && (
            <div className="alert success">{notice}</div>
          )}

          {screen === 'login' ? (
            <form
              className="stack-form"
              onSubmit={handleLogin}
            >
              <label>
                College URL name

                <input
                  required
                  value={login.college_slug}
                  onChange={(e) =>
                    setLogin({
                      ...login,
                      college_slug: e.target.value,
                    })
                  }
                  placeholder="example-college"
                />
              </label>

              <label>
                Email address

                <input
                  required
                  type="email"
                  value={login.email}
                  onChange={(e) =>
                    setLogin({
                      ...login,
                      email: e.target.value,
                    })
                  }
                  placeholder="you@college.edu"
                />
              </label>

              <label>
                Password

                <input
                  required
                  type="password"
                  value={login.password}
                  onChange={(e) =>
                    setLogin({
                      ...login,
                      password: e.target.value,
                    })
                  }
                  placeholder="Your password"
                />
              </label>

              <button
                className="primary-btn"
                disabled={busy}
              >
                {busy ? 'Signing in...' : 'Sign in'}
              </button>
            </form>
          ) : (
            <form
              className="stack-form"
              onSubmit={handleRegister}
            >
              <label>
                College name

                <input
                  required
                  minLength="2"
                  value={signup.college_name}
                  onChange={(e) =>
                    setSignup({
                      ...signup,
                      college_name: e.target.value,
                    })
                  }
                  placeholder="Example College of Engineering"
                />
              </label>

              <label>
                College URL name

                <input
                  required
                  pattern="[a-z0-9]+(-[a-z0-9]+)*"
                  minLength="2"
                  value={signup.college_slug}
                  onChange={(e) =>
                    setSignup({
                      ...signup,
                      college_slug: e.target.value
                        .toLowerCase()
                        .replace(/\s+/g, '-'),
                    })
                  }
                  placeholder="example-college"
                />
              </label>

              <label>
                Administrator name

                <input
                  required
                  value={signup.admin_name}
                  onChange={(e) =>
                    setSignup({
                      ...signup,
                      admin_name: e.target.value,
                    })
                  }
                  placeholder="College administrator"
                />
              </label>

              <label>
                Administrator email

                <input
                  required
                  type="email"
                  value={signup.admin_email}
                  onChange={(e) =>
                    setSignup({
                      ...signup,
                      admin_email: e.target.value,
                    })
                  }
                  placeholder="admin@college.edu"
                />
              </label>

              <label>
                Password{' '}
                <span className="hint">
                  (at least 10 characters)
                </span>

                <input
                  required
                  minLength="10"
                  type="password"
                  value={signup.password}
                  onChange={(e) =>
                    setSignup({
                      ...signup,
                      password: e.target.value,
                    })
                  }
                  placeholder="Create a strong password"
                />
              </label>

              <button
                className="primary-btn"
                disabled={busy}
              >
                {busy ? 'Creating...' : 'Create college portal'}
              </button>

              <p className="fine-print">
                College registration is currently open for
                initial setup. Restrict it before public
                deployment.
              </p>
            </form>
          )}
        </div>
      </div>
    )
  }

  // Main college dashboard
  return (
    <div className="portal">
      <aside className="sidebar">
        <div className="sidebar-brand">
          {fullLogoUrl ? (
            <img src={fullLogoUrl} alt="College logo" />
          ) : (
            <div className="brand-mark small">EA</div>
          )}

          <div>
            <strong>
              {profile?.name ||
                session.college?.name ||
                'College Portal'}
            </strong>

            <span>Academic workspace</span>
          </div>
        </div>

        <div className="side-label">WORKSPACE</div>

        <div className="nav-current">
          ✦ <span>AI Assistant</span>
        </div>

        {session.user.role === 'admin' && (
          <div className="nav-current muted-nav">
            ♙ <span>Student accounts</span>
          </div>
        )}

        <div className="sidebar-bottom">
          <span className="avatar">
            {(session.user.name || 'U')
              .slice(0, 1)
              .toUpperCase()}
          </span>

          <div className="user-meta">
            <strong>{session.user.name}</strong>
            <span>{session.user.role}</span>
          </div>

          <button
            className="logout-btn"
            onClick={logout}
            title="Log out"
          >
            ↗
          </button>
        </div>
      </aside>

      <main className="main-area">
        <header className="top-header">
          <div>
            <p className="eyebrow">
              COLLEGE ACADEMIC PORTAL
            </p>

            <h1>
              {profile?.name || session.college?.name}
            </h1>
          </div>

          <div className="signed-in">
            <span className="online-dot" />
            Signed in as {session.user.role}
          </div>
        </header>

        {(error || notice) && (
          <div
            className={`alert ${error ? 'error' : 'success'}`}
          >
            {error || notice}
          </div>
        )}

        <section className="welcome-row">
          <div>
            <h2>Your academic assistant</h2>

            <p>
              Ask questions and get help from your college's
              academic information.
            </p>
          </div>

          {session.user.role === 'admin' && (
            <label className="upload-btn">
              Upload college logo

              <input
                type="file"
                accept=".png,.jpg,.jpeg,.webp"
                onChange={uploadLogo}
                disabled={busy}
              />
            </label>
          )}
        </section>

        <section className="chat-card">
          <div className="chat-title">
            <div className="assistant-icon">✦</div>

            <div>
              <h3>EduAssist AI</h3>

              <p>
                Academic support · Attendance · Marks ·
                Courses · Policies
              </p>
            </div>

            <button
              type="button"
              className="clear-chat-btn"
              onClick={clearChat}
            >
              Clear Chat
            </button>

            <span className="live-pill">
              <i /> Ready
            </span>
          </div>

          <div className="chat-messages">
            {messages.map((message, index) => (
              <div
                key={index}
                className={`message ${message.role}`}
              >
                <span className="message-name">
                  {message.role === 'user'
                    ? 'YOU'
                    : 'EDUASSIST AI'}
                </span>

                <p style={{ whiteSpace: 'pre-line' }}>
                  {message.content}
                </p>
              </div>
            ))}

            {busy && (
              <div className="message assistant">
                <span className="message-name">
                  EDUASSIST AI
                </span>

                <p>Checking your college information...</p>
              </div>
            )}
          </div>

          <form
            className="chat-form"
            onSubmit={sendMessage}
          >
            <input
              value={question}
              onChange={(e) =>
                setQuestion(e.target.value)
              }
              placeholder="Ask about attendance, marks, courses or policies..."
              disabled={busy}
            />

            <button
              type="submit"
              disabled={busy || !question.trim()}
            >
              Send ↗
            </button>
          </form>

          <p className="privacy-note">
            Your session is connected to{' '}
            {profile?.name || session.college?.name}.
          </p>
        </section>

        {session.user.role === 'admin' && (
          <section className="admin-card">
            <div className="section-heading">
              <div>
                <p className="eyebrow">ADMINISTRATION</p>
                <h2>Student accounts</h2>
              </div>

              <span className="count-pill">
                {students.length} students
              </span>
            </div>

            <form
              className="student-form"
              onSubmit={addStudent}
            >
              <input
                required
                placeholder="Student full name"
                value={newStudent.full_name}
                onChange={(e) =>
                  setNewStudent({
                    ...newStudent,
                    full_name: e.target.value,
                  })
                }
              />

              <input
                required
                type="email"
                placeholder="Student email"
                value={newStudent.email}
                onChange={(e) =>
                  setNewStudent({
                    ...newStudent,
                    email: e.target.value,
                  })
                }
              />

              <input
                required
                minLength="10"
                type="password"
                placeholder="Temporary password (10+ chars)"
                value={newStudent.password}
                onChange={(e) =>
                  setNewStudent({
                    ...newStudent,
                    password: e.target.value,
                  })
                }
              />

              <input
                required
                placeholder="Student ID"
                value={newStudent.student_id}
                onChange={(e) =>
                  setNewStudent({
                    ...newStudent,
                    student_id: e.target.value,
                  })
                }
              />

              <button
                className="primary-btn"
                disabled={busy}
              >
                Add student
              </button>
            </form>

            <div className="student-list">
              {students.length === 0 ? (
                <p className="muted">
                  No student accounts yet. Add the first
                  student above.
                </p>
              ) : (
                students.map((student) => (
                  <div
                    className="student-row"
                    key={student.id}
                  >
                    <span className="avatar">
                      {student.full_name
                        .slice(0, 1)
                        .toUpperCase()}
                    </span>

                    <div>
                      <strong>{student.full_name}</strong>

                      <span>
                        {student.email} · ID:{' '}
                        {student.student_id}
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>
        )}
      </main>
    </div>
  )
}

export default App

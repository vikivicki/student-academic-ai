
from pathlib import Path

from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

BASE_DIR = Path(__file__).resolve().parent
COLLEGES_DIR = BASE_DIR / "data" / "colleges"

# Load embedding model once
embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

# Split policy documents into chunks
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=50
)

if not COLLEGES_DIR.exists():
    raise FileNotFoundError("College data directory not found.")

college_folders = [
    folder for folder in COLLEGES_DIR.iterdir()
    if folder.is_dir()
]

if not college_folders:
    raise RuntimeError("No college folders found.")

for college_folder in college_folders:
    college_id = college_folder.name
    policy_dir = college_folder / "policies"
    faiss_dir = college_folder / "faiss_index"

    if not policy_dir.is_dir():
        print(f"SKIPPED {college_id}: policies folder missing.")
        continue

    loader = DirectoryLoader(
        str(policy_dir),
        glob="*.md",
        loader_cls=TextLoader
    )

    documents = loader.load()

    if not documents:
        print(f"SKIPPED {college_id}: no policy documents.")
        continue

    chunks = text_splitter.split_documents(documents)

    if not chunks:
        print(f"SKIPPED {college_id}: no text chunks.")
        continue

    vector_store = FAISS.from_documents(chunks, embeddings)

    faiss_dir.mkdir(parents=True, exist_ok=True)
    vector_store.save_local(str(faiss_dir))

    print(
        f"SUCCESS: {college_id} | "
        f"Documents: {len(documents)} | "
        f"Chunks: {len(chunks)} | "
        f"Index: {faiss_dir}"
    )

print("College-specific FAISS indexing finished.")

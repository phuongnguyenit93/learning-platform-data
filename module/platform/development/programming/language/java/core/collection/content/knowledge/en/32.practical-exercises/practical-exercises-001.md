# Comprehensive Practice: List Management with Insertion, Update, Search, and Deletion in Java

## 1. Problem and Objectives

Build a Java program to manage a **list of books** using Java Collections. Each book has an **ID** (`id`), a **title** (`title`), and a **publication year** (`year`). This is illustrative data; you can replace books with students, products, or tasks while keeping the same list management principles.

After this practical exercise, you should be able to:

- Use `List<T>` and `ArrayList<T>` to store objects of the same type, preserve order, and access elements by index.
- **Append to the end** and **insert at a specified position**, understanding how subsequent elements shift.
- **Update** an element by its identifier without confusing updating with inserting a new entry.
- **Search** by exact ID and find multiple results by a partial title, case-insensitively.
- **Delete** the right element by ID and handle the not-found case.
- Control duplicate IDs, invalid data, out-of-range indices, and external list modification.
- Understand the complexity of each operation to choose an appropriate data structure.

### Business Rules

1. Each book has a **unique** ID. ID `B01` is different from `b01` (case-sensitive comparison).
2. Both ID and title must be non-empty after stripping leading and trailing whitespace; the publication year must be a positive integer.
3. The insertion position is a **0-based** index. For a list with `n` elements, valid insertion indices are `0` through `n`, whereas valid indices of existing elements are `0` through `n - 1`.
4. When updating a book, **the ID remains unchanged**; only the title and publication year are updated. If the ID does not exist, the operation returns `false`.
5. Searching for or deleting a non-existent ID must yield a deterministic result (`Optional.empty()` or `false`) without corrupting the list.
6. The list returned to callers is a **read-only snapshot**, preventing external code from arbitrarily adding or removing elements and violating the unique ID rule.

## 2. Why Choose `ArrayList`?

`List<Book>` expresses the interface for working with a list; `new ArrayList<>()` provides a dynamic array implementation. `ArrayList` preserves insertion order and allows fast `get(index)` access. It is well-suited for small- to medium-scale problems where linear traversal and search are acceptable.

For example, if the list initially contains `[B01, B03]`:

- `add(B02)` produces `[B01, B03, B02]`: appends to the **end**.
- `add(1, B02)` produces `[B01, B02, B03]`: **inserts** at index 1, shifting `B03` to the right.
- `set(1, B02Moi)` **replaces** the element currently at index 1 without changing the list length.
- `remove(1)` removes the element at index 1, and subsequent elements shift to the left.

Crucial point: **the book ID is the business identity; the index is the current position**. After an insertion or deletion, indices can change, so the program searches by ID first to determine the index to update or delete. Never use an index saved from a previous access to identify a book.

## 3. Complete Program Running on Java 17+

Create a `Main.java` file containing all the code below. The example deliberately uses deterministic data so you can verify the output. `Book` is an immutable `record`; `BookManager` encapsulates the list and provides operations for adding, inserting, updating, searching, and deleting.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.Optional;

public class Main {

    record Book(String id, String title, int year) {
        Book {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("Mã sách không được trống");
            }
            if (title == null || title.isBlank()) {
                throw new IllegalArgumentException("Tên sách không được trống");
            }
            if (year <= 0) {
                throw new IllegalArgumentException("Năm xuất bản phải dương");
            }
            id = id.strip();
            title = title.strip();
        }
    }

    static final class BookManager {
        private final List<Book> books = new ArrayList<>();

        // Append a book to the end of the list.
        void add(Book book) {
            Objects.requireNonNull(book, "book");
            rejectDuplicateId(book.id());
            books.add(book);
        }

        // Insert before the element currently at index; index == size() means appending to the end.
        void insert(int index, Book book) {
            Objects.requireNonNull(book, "book");
            if (index < 0 || index > books.size()) {
                throw new IndexOutOfBoundsException("Vị trí chèn: " + index);
            }
            rejectDuplicateId(book.id());
            books.add(index, book);
        }

        // Return false when no matching ID exists; keep the book ID unchanged when updating.
        boolean update(String id, String newTitle, int newYear) {
            int index = indexOfId(id);
            if (index == -1) {
                return false;
            }
            Book replacement = new Book(id, newTitle, newYear);
            books.set(index, replacement);
            return true;
        }

        // Look up by exact ID.
        Optional<Book> findById(String id) {
            int index = indexOfId(id);
            return index == -1
                    ? Optional.empty()
                    : Optional.of(books.get(index));
        }

        // Find all books whose title contains the keyword, case-insensitively.
        List<Book> searchByTitle(String keyword) {
            Objects.requireNonNull(keyword, "keyword");
            String needle = keyword.strip().toLowerCase(Locale.ROOT);
            if (needle.isEmpty()) {
                return List.of();
            }

            List<Book> matches = new ArrayList<>();
            for (Book book : books) {
                if (book.title().toLowerCase(Locale.ROOT).contains(needle)) {
                    matches.add(book);
                }
            }
            return List.copyOf(matches);
        }

        // Delete by ID; leave the list unchanged if the ID does not exist.
        boolean delete(String id) {
            int index = indexOfId(id);
            if (index == -1) {
                return false;
            }
            books.remove(index);
            return true;
        }

        // Return a read-only snapshot without exposing the internal list.
        List<Book> list() {
            return List.copyOf(books);
        }

        private void rejectDuplicateId(String id) {
            if (indexOfId(id) != -1) {
                throw new IllegalArgumentException(
                        "Mã sách đã tồn tại: " + id);
            }
        }

        private int indexOfId(String id) {
            Objects.requireNonNull(id, "id");
            for (int i = 0; i < books.size(); i++) {
                if (books.get(i).id().equals(id)) {
                    return i;
                }
            }
            return -1;
        }
    }

    public static void main(String[] args) {
        BookManager manager = new BookManager();

        manager.add(new Book("B01", "Effective Java", 2018));
        manager.add(new Book("B03", "Clean Code", 2008));
        manager.insert(1, new Book(
                "B02", "Java Concurrency in Practice", 2006));

        System.out.println("Sau khi chèn: " + manager.list());
        System.out.println("Cập nhật B03: "
                + manager.update("B03", "Clean Code - revised", 2009));
        System.out.println("Tìm mã B02: "
                + manager.findById("B02").orElseThrow());
        System.out.println("Tìm tên java: "
                + manager.searchByTitle("java"));
        System.out.println("Xóa B01: " + manager.delete("B01"));
        System.out.println("Còn lại: " + manager.list());
        System.out.println("Xóa mã lạ: " + manager.delete("B99"));

        try {
            manager.add(new Book("B02", "Duplicate", 2020));
        } catch (IllegalArgumentException ex) {
            System.out.println("Trùng mã: " + ex.getMessage());
        }
    }
}
```

Compile and run in the directory containing `Main.java`:

```bash
javac Main.java
java Main
```

Corresponding output (each line below is **one line of stdout**; long lines may wrap automatically depending on your terminal width):

```text
Sau khi chèn: [Book[id=B01, title=Effective Java, year=2018], Book[id=B02, title=Java Concurrency in Practice, year=2006], Book[id=B03, title=Clean Code, year=2008]]
Cập nhật B03: true
Tìm mã B02: Book[id=B02, title=Java Concurrency in Practice, year=2006]
Tìm tên java: [Book[id=B01, title=Effective Java, year=2018], Book[id=B02, title=Java Concurrency in Practice, year=2006]]
Xóa B01: true
Còn lại: [Book[id=B02, title=Java Concurrency in Practice, year=2006], Book[id=B03, title=Clean Code - revised, year=2009]]
Xóa mã lạ: false
Trùng mã: Mã sách đã tồn tại: B02
```

### Execution Flow Walkthrough

1. `add` appends `B01` and `B03` to the end: `[B01, B03]`.
2. `insert(1, B02)` places `B02` in the middle: `[B01, B02, B03]`; it does not overwrite `B03`.
3. `update("B03", ...)` finds the index of `B03` and calls `set` with a new record. The position and list size remain unchanged.
4. `findById("B02")` returns an `Optional<Book>` containing that single book; `searchByTitle("java")` returns both `B01` and `B02` in list order.
5. `delete("B01")` removes the first book, leaving `[B02, B03]`; deleting `B99` returns `false` and does not modify the data.
6. Re-adding `B02` is blocked due to a duplicate ID; the exception is caught at the demo boundary so the user can see the reason.

## 4. Understanding Each CRUD Operation

### 4.1. Appending and Positional Insertion — Create

`books.add(book)` appends to the end. `books.add(index, book)` inserts **before** position `index`. If `index == books.size()`, inserting at the end is valid, including for an empty list with `index == 0`. If `index < 0` or `index > size()`, an error must be thrown; do not silently convert an invalid position into the end position.

The duplicate ID check is placed **before modifying the list**. This ensures that the same ID never accidentally creates two records, which would make `update` or `delete` ambiguous. In this example, duplicate checking uses linear search; this approach is simple and keeps all data in a single list.

### 4.2. Updating by ID — Update

Steps: find the index via `indexOfId(id)` → if `-1`, return `false` → create a new validated `Book` → `books.set(index, replacement)`. Because `Book` is an immutable record, updating means **replacing the object at the exact index**, rather than mutating the object's fields directly.

`set(index, value)` differs from `add(index, value)`: `set` keeps the element count unchanged, whereas `add` increases the count by one. When updating, do not use `add`, as it would create an extra record and potentially duplicate IDs.

### 4.3. Searching by ID and by Title — Read

- **By ID:** uses `equals` for an exact match and returns `Optional<Book>`. The caller can use `orElse(...)`, `ifPresent(...)`, or `orElseThrow()` depending on whether absence is considered an error. Only use `orElseThrow()` when the ID is guaranteed to exist, as in the demo runner.
- **By title:** converts both the keyword and the title to lowercase using `Locale.ROOT` and uses `contains` for partial matching; returns multiple results while preserving the original list order. A whitespace-only keyword returns an empty list, avoiding accidentally turning a blank query into a "find all" query.
- **View all:** `list()` returns `List.copyOf(books)`. This is an unmodifiable list and a snapshot at the time of the call; it does not automatically update when `BookManager` changes later. The `Book` elements themselves are also immutable, so callers cannot surreptitiously mutate internal data through element references.

### 4.4. Deleting by ID — Delete

`indexOfId` locates the object by ID, and then `books.remove(index)` removes the exact position. When removing the first or a middle element, subsequent elements shift left and their indices change. The method returns `true` if a book was removed, or `false` if no matching ID was found. Do not pass the `String` ID directly to `remove(Object)` because the list holds `Book` instances.

If you need to delete multiple books matching a condition, `removeIf` or `Iterator.remove()` is the appropriate choice. You should not call `books.remove(...)` directly inside a `for-each` loop over the same list, as that structurally modifies the list while the iterator is traversing it and can throw a `ConcurrentModificationException`.

## 5. Boundary Checks and Functional Testing

Minimum scenarios to test in addition to the happy path in `main`:

| Scenario | Operation | Expected Result |
| --- | --- | --- |
| Add to empty list | `add(B01)` | List contains one book |
| Insert at head | `insert(0, B00)` | `B00` appears before existing books |
| Insert at tail | `insert(size(), B99)` | `B99` appears at the end |
| Insert out of bounds | `insert(-1, ...)` or `insert(size()+1, ...)` | `IndexOutOfBoundsException`, list unchanged |
| Duplicate ID | Add/insert a book with an existing ID | `IllegalArgumentException`, list unchanged |
| Successful update | `update("B03", ..., 2009)` | Replaces title/year, keeps ID, position, and count |
| Update non-existent ID | `update("B99", ..., 2024)` | `false`, list unchanged |
| Find non-existent ID | `findById("B99")` | `Optional.empty()` |
| Case-insensitive title search | `searchByTitle("JAVA")` | Receives books whose titles contain "java" |
| Blank keyword | `searchByTitle("   ")` | Empty result list |
| Successful delete | `delete("B01")` | `true`, removes only `B01` |
| Delete same ID again | `delete("B01")` a second time | `false` |
| Blank ID/title or year ≤ 0 | `new Book(... )` | `IllegalArgumentException` |
| Attempt to mutate returned list | `manager.list().clear()` | `UnsupportedOperationException`; data in manager unchanged |

You can append the following test calls to `main` **after** running the original example (no testing library required):

```java
BookManager check = new BookManager();
check.insert(0, new Book("S1", "Java Basics", 2023));
if (check.list().size() != 1) {
    throw new AssertionError("Chèn vào danh sách rỗng thất bại");
}
if (check.update("S9", "Missing", 2024)) {
    throw new AssertionError("Không được sửa mã không tồn tại");
}
if (!check.findById("S1").isPresent()) {
    throw new AssertionError("Không tìm được sách vừa thêm");
}
if (!check.delete("S1") || check.delete("S1")) {
    throw new AssertionError("Xóa phải thành công đúng một lần");
}
System.out.println("Các kiểm tra bổ sung đã qua");
```

The snippet above is **additional code to be placed inside `main`**, sharing the already declared `Book` and `BookManager` classes; it is not a standalone file. After adding it, only one extra line `Các kiểm tra bổ sung đã qua` appears at the end of the program output.

### Invariants to Maintain After Every Operation

- No two elements have the same `id`.
- No `null` elements or books violating ID/title/year constraints exist.
- Insertion increases `size()` by exactly 1; updating preserves `size()`; successful deletion decreases `size()` by exactly 1.
- Operations that fail due to not-found items or invalid arguments must never silently mutate the list.
- The relative order of remaining elements is not scrambled when updating or deleting.

## 6. Complexity and Extension Options

Let `n` be the number of books in the list, and `L` be the length of the title or keyword when considering string searching.

| Operation in `BookManager` | Typical/Worst-Case Time | Explanation |
| --- | --- | --- |
| `add` | `O(n)` | Appending to an `ArrayList` has `O(1)` amortized average cost, but checking for duplicate IDs scans in `O(n)` |
| `insert` | `O(n)` | Duplicate check and shifting subsequent elements |
| `update` | `O(n)` | Finding ID takes `O(n)`, replacing at index takes `O(1)` |
| `findById` | `O(n)` | Scans until found or end of list |
| `searchByTitle` | Around `O(n × L)` | Scans `n` titles and matches substrings; actual cost depends on each title's length and the `contains` algorithm |
| `delete` | `O(n)` | Finds ID and shifts elements after removal |
| `list` | `O(n)` | Creates a snapshot via `List.copyOf` |

Memory for storing books is `O(n)`; each call returning a result list or snapshot may use up to `O(n)` additional memory. The time complexity table reflects the entire **method as written**, not just the underlying `ArrayList.add` or `set` call.

When the list is large and lookups by ID happen frequently, consider combining a `List<Book>` to preserve order with a `Map<String, Book>` for faster ID lookups. However, you must update **both structures consistently** on every addition, update, and deletion. For this exercise, a single `ArrayList` is easier to verify.

`ArrayList` does not guarantee thread safety under concurrent modifications; the example program runs on a single thread. If used in a multi-threaded application, design proper synchronization rather than assuming the CRUD operations shown here are inherently thread-safe.

## 7. Common Mistakes and How to Avoid Them

1. **Confusing insertion with overwriting:** `add(index, x)` inserts, whereas `set(index, x)` replaces; check `size()` after each operation.
2. **Relying on index to identify an element:** indices shift after insertion/deletion; search by a stable ID instead.
3. **Failing to block duplicate IDs:** `update`/`delete` may only process the first record and miss duplicates; validate before adding.
4. **Using `==` to compare strings:** use `String.equals`, because `==` compares object references.
5. **Exposing the internal list directly:** returning `books` lets external code bypass validation; return a read-only snapshot instead.
6. **Invalidly modifying contents inside a `for-each` loop:** structural deletion should use an index after searching, `Iterator.remove()`, or `removeIf`.
7. **Removing by value without understanding `equals`:** `remove(Object)` compares objects using `equals`; when deleting by ID, finding the index first is clearer.
8. **Catching all exceptions and swallowing them:** invalid input or out-of-bounds indices must be reported clearly, whereas a missing ID should be represented by `false` or `Optional.empty()` according to the method contract.
9. **Using `List.of(...)` as a mutable list:** lists created by `List.of` do not support `add`/`set`/`remove`; use `new ArrayList<>()` for a mutable list.

## 8. Self-Practice Extension Exercises

Once the original example runs properly, implement the following in order:

1. Add a console menu using `Scanner`: view list, append to end, insert at position, update by ID, search by ID/title, delete by ID, and exit. Validate numeric input before calling the manager.
2. Write an `insertBeforeId(String existingId, Book newBook)` method: find the index of the anchor book and insert the new book before it; if the anchor book does not exist, return a failure status and leave the list unchanged.
3. Add a search by publication year range that returns a result list preserving the original order.
4. Write automated tests (using JUnit or a standalone test suite) for the cases in the Section 5 table, especially duplicate IDs, invalid indices, and post-error invariants.
5. For optimization, add a `HashMap<String, Book>` and design a synchronized update strategy between the map and the list; prove that additions and deletions never leave the two structures out of sync.

**Completion Criteria:** the program compiles and runs on Java 17+, implements all four core operations (insert, update, search, delete), covers both success and failure scenarios, preserves unique IDs and list order, reports clear outcomes, and prevents external code from directly mutating internal state.

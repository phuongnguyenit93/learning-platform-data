# Building a Generic Repository with Multiple Storage Mechanisms

A **repository** provides an API to save, find, list, and delete objects. With **generics** in Java, the same contract can be used for multiple data types while preserving compile-time type checking. Combining an interface with multiple implementations allows the application to choose a storage mechanism without rewriting business logic.

This practice exercise builds the `Repository<ID, T>` contract with two backends:

- **In-memory:** uses a `Map` to hold data in process memory.
- **File-backed:** writes the data map to a file and reloads it when a new repository is created.

The caller uses `Repository<String, Book>`, so it can switch between backends without changing the API type that the application sees.

## 1. Designing the Generic Contract

A repository typically requires two type parameters:

- `T`: the type of object being stored, for example `Book`.
- `ID`: the key type used to find an object, for example `String` or `UUID`.

If `BookRepository`, `CustomerRepository`, and `OrderRepository` are written separately, the basic operations can be duplicated. A generic interface consolidates them into one contract:

~~~java
interface Repository<ID, T> {
    void save(T entity) throws IOException;
    Optional<T> findById(ID id);
    List<T> findAll();
    boolean deleteById(ID id) throws IOException;
}
~~~

This is an excerpt to illustrate the contract; the complete program in Section 5 includes all necessary imports and implementations.

- `save` adds or replaces an object with the same ID.
- `findById` returns `Optional<T>`: containing a value when found, empty when absent.
- `findAll` returns a list of results.
- `deleteById` returns `true` if an object was deleted, and `false` otherwise.

The contract declares `IOException` for write operations because the file backend can encounter errors. The in-memory implementation does not need to throw this exception, yet it can still use the same API. The interface hides implementation differences while still expressing the kind of error that the caller needs to handle.

## 2. Identifying Keys and Preserving Types

A repository using `Map<ID, T>` needs to know each object's ID. For example, it accepts a `Function<T, ID>` in the constructor:

~~~java
Function<Book, String> idExtractor = Book::id;
~~~

`Book::id` is a method reference to the record's accessor. The repository calls this function to obtain the key without needing to know the concrete structure of `Book`.

This approach allows reusing the repository for many kinds of objects if the caller provides an appropriate ID extraction function. The ID should be non-null and stable when the object is stored. If the ID changes after saving, a find or delete operation using the new ID may fail to find the old entry.

## 3. In-Memory Backend

`InMemoryRepository<ID, T>` uses `LinkedHashMap<ID, T>`. The key is the ID and the value is the object; saving an existing ID replaces the old value, and `LinkedHashMap` preserves insertion order when listing. Data is lost when the process ends or the repository is discarded.

This is a useful choice for temporary data, simple caches, exercises, and testing. It does not provide durability across program runs.

## 4. File-Backed Backend

`FileRepository<ID, T>` keeps a `Map` in memory while running and writes the map to a file after each save or delete. When creating a new instance, the repository loads the map from the file.

Because the example uses Java Object Serialization, both the ID and the object must implement `Serializable`. This is a constraint of the file-storage implementation, not a requirement of the generic interface in general. Other backends may use JSON, a relational database, or a remote service with their own constraints.

The example writes to a temporary file and then moves it to the target location to reduce the risk of leaving a partial data file if the write step fails. The demo code is intended only for trusted application files: **do not use `ObjectInputStream` to deserialize files supplied by untrusted users**. Object serialization also couples the data format to Java classes, so it is not inherently a good choice for long-term storage.

## 5. Complete Java 17+ Program

Save all of the following code to **GenericRepositoryDemo.java**. The program declares the contract, the two implementations, and the sample data type in the same file so it is easy to run and try out.

~~~java
import java.io.IOException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.function.Function;

interface Repository<ID, T> {
    void save(T entity) throws IOException;
    Optional<T> findById(ID id);
    List<T> findAll();
    boolean deleteById(ID id) throws IOException;
}

final class InMemoryRepository<ID, T> implements Repository<ID, T> {
    private final Map<ID, T> data = new LinkedHashMap<>();
    private final Function<T, ID> idExtractor;

    InMemoryRepository(Function<T, ID> idExtractor) {
        this.idExtractor = Objects.requireNonNull(idExtractor, "idExtractor");
    }

    @Override
    public synchronized void save(T entity) {
        Objects.requireNonNull(entity, "entity");
        ID id = Objects.requireNonNull(idExtractor.apply(entity), "entity id");
        data.put(id, entity);
    }

    @Override
    public synchronized Optional<T> findById(ID id) {
        return Optional.ofNullable(data.get(Objects.requireNonNull(id, "id")));
    }

    @Override
    public synchronized List<T> findAll() {
        return List.copyOf(data.values());
    }

    @Override
    public synchronized boolean deleteById(ID id) {
        return data.remove(Objects.requireNonNull(id, "id")) != null;
    }
}

final class FileRepository<ID extends Serializable, T extends Serializable>
        implements Repository<ID, T> {
    private final Path file;
    private final Function<T, ID> idExtractor;
    private final Map<ID, T> data;

    FileRepository(Path file, Function<T, ID> idExtractor) throws IOException {
        this.file = Objects.requireNonNull(file, "file");
        this.idExtractor = Objects.requireNonNull(idExtractor, "idExtractor");
        this.data = load();
    }

    @Override
    public synchronized void save(T entity) throws IOException {
        Objects.requireNonNull(entity, "entity");
        ID id = Objects.requireNonNull(idExtractor.apply(entity), "entity id");
        data.put(id, entity);
        persist();
    }

    @Override
    public synchronized Optional<T> findById(ID id) {
        return Optional.ofNullable(data.get(Objects.requireNonNull(id, "id")));
    }

    @Override
    public synchronized List<T> findAll() {
        return List.copyOf(data.values());
    }

    @Override
    public synchronized boolean deleteById(ID id) throws IOException {
        boolean removed = data.remove(Objects.requireNonNull(id, "id")) != null;
        if (removed) {
            persist();
        }
        return removed;
    }

    @SuppressWarnings("unchecked")
    private Map<ID, T> load() throws IOException {
        if (!Files.exists(file)) {
            return new LinkedHashMap<>();
        }

        try (ObjectInputStream input =
                     new ObjectInputStream(Files.newInputStream(file))) {
            Object stored;
            try {
                stored = input.readObject();
            } catch (ClassNotFoundException ex) {
                throw new IOException("Stored class is unavailable", ex);
            }

            if (!(stored instanceof Map<?, ?> storedMap)) {
                throw new IOException("Unexpected repository file format");
            }

            Map<ID, T> result = new LinkedHashMap<>();
            for (Map.Entry<?, ?> entry : storedMap.entrySet()) {
                result.put((ID) entry.getKey(), (T) entry.getValue());
            }
            return result;
        }
    }

    private void persist() throws IOException {
        Path absolute = file.toAbsolutePath();
        Path parent = absolute.getParent();
        Files.createDirectories(parent);
        Path temporary = Files.createTempFile(parent, "repo-", ".tmp");

        try {
            try (ObjectOutputStream output =
                         new ObjectOutputStream(Files.newOutputStream(temporary))) {
                output.writeObject(data);
            }

            try {
                Files.move(temporary, absolute,
                        StandardCopyOption.ATOMIC_MOVE,
                        StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException ex) {
                Files.move(temporary, absolute,
                        StandardCopyOption.REPLACE_EXISTING);
            }
        } finally {
            Files.deleteIfExists(temporary);
        }
    }
}

record Book(String id, String title) implements Serializable {}

public class GenericRepositoryDemo {
    public static void main(String[] args) throws IOException {
        Repository<String, Book> memory = new InMemoryRepository<>(Book::id);
        memory.save(new Book("b1", "Java"));
        System.out.println("Memory: " + memory.findById("b1").orElseThrow());

        Path file = Files.createTempFile("books-", ".bin");
        Files.deleteIfExists(file);

        try {
            Repository<String, Book> disk = new FileRepository<>(file, Book::id);
            disk.save(new Book("b2", "Generics"));

            Repository<String, Book> reopened =
                    new FileRepository<>(file, Book::id);
            System.out.println("File: " + reopened.findById("b2").orElseThrow());
            System.out.println("Count after reopen: " + reopened.findAll().size());

            System.out.println("Deleted b2: " + reopened.deleteById("b2"));
            Repository<String, Book> afterDelete =
                    new FileRepository<>(file, Book::id);
            System.out.println("Count after delete: " + afterDelete.findAll().size());
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac GenericRepositoryDemo.java
java GenericRepositoryDemo
~~~

Exact stdout:

~~~text
Memory: Book[id=b1, title=Java]
File: Book[id=b2, title=Generics]
Count after reopen: 1
Deleted b2: true
Count after delete: 0
~~~

The line `Count after reopen: 1` shows that the data is read back from the file when creating a new repository. After deleting `b2`, a new instance reads a count of 0, confirming that the change was written to the file.

## 6. How Do Generics and Interfaces Separate Responsibilities?

The application declares the variable against the interface:

~~~java
Repository<String, Book> repository =
        new InMemoryRepository<>(Book::id);
~~~

If a file-backed backend is needed, it can be initialized with another implementation:

~~~java
Repository<String, Book> repository =
        new FileRepository<>(path, Book::id);
~~~

The two snippets above illustrate the same contract type; in a single program, the `repository` variable is declared only once and initialized with the chosen backend. The business logic continues to call `save`, `findById`, or `findAll` without depending directly on a concrete class.

Three key design points:

1. **Generics maintain type safety.** `Repository<String, Book>` uses `Book` as the data and `String` as the key; the compiler catches many cases where the wrong type is passed.
2. **The interface defines the contract.** Both implementations provide the same operations while using different storage mechanisms.
3. **Dependencies are chosen at the initialization boundary.** The repository can be passed into a service via its constructor so that the business logic does not create or tightly couple to a backend.

Generics do not automatically provide data durability, cross-process synchronization, or transactions. Those properties depend on the specific backend and contract.

## 7. Comparison and Limitations

| Criterion | In-memory | File-backed in the example |
|---|---|---|
| Retains data after the process stops | No | Yes, in the written file |
| Typical operation overhead | Usually low | Additional I/O on writes |
| Data type requirements | Does not require `Serializable` | ID and T must be `Serializable` |
| Sharing across multiple processes | No | Not synchronized across multiple instances |
| Suitable for | Caches, temporary data, tests | Demos, small datasets, and trusted files |

This file-backed implementation loads all data into memory at initialization and rewrites the map after every change. In the example, `save`/`deleteById` mutate the `Map` before writing the file; if `persist()` throws `IOException`, the in-memory state may already have changed even though the operation reports an error. A real-world application needs a recovery/rollback policy, or should update a copy and only publish the state after saving succeeds. Two instances opening the same file do not automatically synchronize state; concurrent operations from multiple processes are also neither locked nor coordinated. Real-world applications requiring multiple writers, large datasets, querying, transactions, or fault recovery should consider a database or a dedicated backend.

Checks to include when developing a repository:

- Saving two objects with the same ID must properly replace the old object.
- Finding a nonexistent ID must return `Optional.empty()`.
- Deleting a nonexistent ID must return `false`.
- Null IDs and null objects must be handled consistently.
- Read/write errors must be propagated to where a decision can be made to retry, report the error, or recover.
- Test invalid files, changed class versions, and file access permissions.
- If concurrent use is needed, define a synchronization and consistency policy rather than assuming `synchronized` on each instance protects a shared file.

## 8. Common Pitfalls

- **Binding concrete types to the generic contract.** If the interface declares `Book` directly, it becomes hard to use for other types. Place type parameters where generalization is needed.
- **Using `Object` instead of generics.** This loses type checking and often forces callers to cast.
- **Failing to define ID rules.** A repository needs a consistent way to obtain keys; null or mutable IDs make lookups unpredictable.
- **Assuming all backends share the same behavior.** The same interface does not mean the same latency, durability, transactions, or concurrency limits.
- **Ignoring I/O errors.** Saving to a file can fail due to permissions, disk space, or system errors. Do not report success when the data has not been written.
- **Deserializing untrusted data.** Java native serialization is unsuitable for arbitrarily reading untrusted data; choose an appropriate format and safety validation mechanism.
- **Letting business logic depend on a concrete implementation.** If a service calls details specific to `FileRepository` directly, switching backends becomes harder and the benefit of the interface is diminished.

## 9. Practical Workflow

1. Identify the data type `T`, the key type `ID`, and the minimum operations required by the business logic.
2. Declare `Repository<ID, T>` with clear return types such as `Optional<T>` and `List<T>`.
3. Write a simple implementation first, such as `InMemoryRepository`, to verify the contract.
4. Add another backend without changing how the business logic calls the interface.
5. Test the same behavioral suite on each implementation, then separately test specific properties such as durability, I/O errors, and concurrency.
6. Choose a backend based on actual requirements for data lifecycle, scale, querying, operations, and recovery.

A generic repository reuses the same contract across multiple data types; implementations provide concrete storage mechanisms. When these two responsibilities are clearly separated, the application becomes easier to test, switching backends becomes easier, and business logic remains less dependent on storage details.

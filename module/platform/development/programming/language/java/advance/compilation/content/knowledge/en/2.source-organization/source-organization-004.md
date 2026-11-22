# Organizing Multiple Mutually Referencing Java Files

A real-world Java program rarely consists of just one file. One class can call methods of a class in another file; two classes can even know each other's types. To compile and run properly, you need to distinguish **source files**, **Java classes/types**, **packages**, **source lookup path**, **compiled class lookup path**, and **runtime dependencies**.

This lesson uses Java 17 or later and focuses on how to lay out, reference, compile, and troubleshoot errors when source files depend on one another.

## 1. How Does One Java File Reference Another?

Suppose the file `Book.java` defines the `Book` type, and `Main.java` creates a `Book` object. Code in `Main` references the **`Book` type**, rather than "including a file" in the way `#include` does in C/C++.

The `javac` compiler reads type declarations and checks names, accessibility, method signatures, and type constraints. It can process multiple source files in **the same compilation invocation**. The result is typically `.class` files containing bytecode; the JVM loads the needed classes at runtime.

Three relationships to distinguish:

- **Compile-time type dependency:** `Book` declares a field of type `Author`; the compiler must find and check `Author`.
- **Runtime object reference:** a `Book` object holds a reference to an `Author` object. Two objects can hold references to each other.
- **Module/library dependency:** project A needs library B on the classpath/module path. Configuration rules and cyclicity rules at this layer differ from the relationship between two classes.

**A pair of classes referencing each other's types does not automatically cause a compilation error.** What matters is that declarations are valid, locatable, and accessible; object initialization must also make sense.

## 2. Rules for Files, Packages, and Directories

For a `public` top-level class named `Book`, the source file name must be `Book.java`. If the top of the file declares `package vn.lesson.domain;`, place the file following the structure `src/vn/lesson/domain/Book.java`. The `src` part is the **source root**, not part of the package name.

A typical layout:

~~~text
project/
├── src/
│   └── vn/
│       └── lesson/
│           ├── domain/
│           │   ├── Author.java
│           │   └── Book.java
│           ├── service/
│           │   └── BookCatalog.java
│           └── app/
│               └── Main.java
└── out/                 # created during compilation
~~~

Fundamental rules:

1. The `package` declaration (if present) precedes any `import` declarations and type declarations, except for comments.
2. Two types in the **same package** can refer to each other using their simple names `Author`, `Book` without an `import`, even if they are in separate files.
3. For a type in another package, use `import vn.lesson.domain.Book;` or the fully qualified name `vn.lesson.domain.Book`.
4. `import vn.lesson.domain.*;` considers only types directly accessible in that package; it does not automatically import subpackages.
5. Package names are case-sensitive. On a case-sensitive filesystem, `domain` and `Domain` are two different paths.
6. Avoid using the default package (no `package` line) for multi-file applications; a class in a named package cannot import a class from the default package.
7. A file may contain multiple package-private top-level types, but at most one `public` top-level type; ordinarily, each main type should be placed in its own easy-to-find file.

`src/` holds source code, while `out/` holds only compilation output. Keeping them separate avoids mixing old `.class` files with new source code.

## 3. Complete Example: Four Files with Mutually Referencing Classes

Requirements: `Author` knows its featured book; `Book` knows its author; `BookCatalog` formats book information; `Main` coordinates the objects. Here `Author` and `Book` **mutually reference each other's types** across two different files. Create the four files at the exact paths shown in section 2.

### 3.1. `src/vn/lesson/domain/Author.java`

~~~java
package vn.lesson.domain;

public final class Author {
    private final String name;
    private Book featuredBook;

    public Author(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }

    public void feature(Book book) {
        if (book == null || book.author() != this) {
            throw new IllegalArgumentException(
                "Book must belong to this author"
            );
        }
        this.featuredBook = book;
    }

    public String featuredTitle() {
        return featuredBook == null
            ? "(chưa có)"
            : featuredBook.title();
    }
}
~~~

`Author` directly uses the `Book` type in its field, parameter, and method call. No import for `Book` is needed because both types belong to the same package `vn.lesson.domain`. The `featuredBook` field starts as `null`; we link the relationship after creating `Book`, avoiding dependency on an object that does not yet exist.

### 3.2. `src/vn/lesson/domain/Book.java`

~~~java
package vn.lesson.domain;

import java.util.Objects;

public final class Book {
    private final String title;
    private final Author author;

    public Book(String title, Author author) {
        this.title = Objects.requireNonNull(title, "title");
        this.author = Objects.requireNonNull(author, "author");
    }

    public String title() {
        return title;
    }

    public Author author() {
        return author;
    }
}
~~~

`Book` also references `Author`, creating a bidirectional relationship **between type declarations**. `Objects.requireNonNull` ensures the two required parameters are non-null; it is a call to the standard library class `java.util.Objects`.

### 3.3. `src/vn/lesson/service/BookCatalog.java`

~~~java
package vn.lesson.service;

import vn.lesson.domain.Book;

public final class BookCatalog {
    public String label(Book book) {
        return book.title() + " — " + book.author().name();
    }
}
~~~

`BookCatalog` belongs to a different package, so it imports the public type `Book`. It does not need to know the file path of `Book.java`, nor does it need `import Author` because it does not directly use the type name `Author` in a declaration or expression.

### 3.4. `src/vn/lesson/app/Main.java`

~~~java
package vn.lesson.app;

import vn.lesson.domain.Author;
import vn.lesson.domain.Book;
import vn.lesson.service.BookCatalog;

public final class Main {
    public static void main(String[] args) {
        Author author = new Author("Lan");
        Book book = new Book("Java 17", author);
        author.feature(book);

        System.out.println(new BookCatalog().label(book));
        System.out.println(author.featuredTitle());
        System.out.println(book.author() == author);
    }
}
~~~

Type dependency structure:

~~~text
app.Main ──> domain.Author
         ├─> domain.Book <──> domain.Author
         └─> service.BookCatalog ──> domain.Book
~~~

The bidirectional arrow between `Book` and `Author` represents type reference capability. At runtime, the fields `book.author` and `author.featuredBook` point back and forth between the two instantiated objects; the final `==` check verifies that they point to the exact same `Author` object.

## 4. Compiling and Running from the `project` Directory

Requires JDK 17 or later; check with `javac -version` and `java -version`. Open a terminal in the `project` directory (which contains `src`). Create the output directory, then pass all source files to **a single `javac` invocation**:

~~~sh
mkdir out
javac --release 17 -encoding UTF-8 -d out src/vn/lesson/domain/Author.java src/vn/lesson/domain/Book.java src/vn/lesson/service/BookCatalog.java src/vn/lesson/app/Main.java
java -cp out vn.lesson.app.Main
~~~

Standard output:

~~~text
Java 17 — Lan
Java 17
true
~~~

The example has been verified to compile with `--release 17` and produce the exact three output lines above.

Explanation of each part of the commands:

- `--release 17`: checks language syntax and APIs against the Java 17 platform; helps avoid accidentally using APIs only available in newer JDKs.
- `-encoding UTF-8`: character encoding used when `javac` reads `.java` files; this is very helpful if there are Vietnamese diacritics or Unicode characters in the code.
- `-d out`: writes `.class` files under the `out` root while preserving the package tree, for example `out/vn/lesson/domain/Book.class`.
- `-cp out`: places the root containing the compiled packages onto the **runtime classpath**.
- `vn.lesson.app.Main`: fully qualified class name, including the package; do **not** pass `src/.../Main.java` or `Main.class` for this execution mode.

The order in which the four files are listed in the same `javac` invocation is **not** a required compilation order among the classes. The compiler resolves type references across the entire supplied set of sources. There is no need to compile `Author` before `Book`, or vice versa.

Note about terminals on Windows: paths with `/` in the commands above are accepted by Java; you may use `\` as the directory separator when needed. In PowerShell 5, some file-writing commands with `-Encoding UTF8` add a BOM; `javac` may report `illegal character: '\uFEFF'` at the start of the file. Save `.java` files as UTF-8 **without BOM**.

### 4.1. When Specifying Only `Main.java`

You can let `javac` automatically locate dependent source files in the source root:

~~~sh
javac --release 17 -encoding UTF-8 -sourcepath src -d out src/vn/lesson/app/Main.java
java -cp out vn.lesson.app.Main
~~~

`-sourcepath src` tells `javac` where to look for `.java` files of referenced types that do not yet have suitable `.class` files. This example uses the same four files from section 3, with the `out` directory already created.

Important differences:

| Option | Role |
|---|---|
| `-sourcepath src` | Where `javac` searches for dependent `.java` sources. |
| `-classpath out` or `-cp out` | Where `javac` or `java` searches for compiled classes/libraries, depending on the command. |
| `-d out` | Where `javac` writes new `.class` files. |
| `--module-path` | Where to search for compiled Java modules, in projects using the Java Platform Module System (JPMS). |

If `-sourcepath` is not set, whether `javac` finds dependent sources depends on the default classpath/source path configuration. Do not rely on the compiler happening to find a file in another directory. For medium and large projects, let Maven/Gradle define source sets and classpaths consistently.

## 5. How Java Resolves Names and Access Control

Successful compilation does not only require finding the right file; the referenced types and members must be **accessible**:

- `public` top-level class: usable from another package, provided the type is present on the compilation path and, when using JPMS, the package is appropriately exported.
- Top-level class without `public`: accessible only within the same package.
- `private` members: accessible only according to permitted class/nest scope rules; placing two classes in the same package does not let one access the other's `private` members.
- Members with no modifier (package-private): accessible within the same package.
- `protected`: has specific rules for the same package and for subclasses in other packages; it does not mean `public`.
- `import` only allows using a shorter name; it does **not** grant access rights, put libraries onto the classpath, create classes automatically, or execute code.

For example, `BookCatalog` cannot access `book.author` because it is a `private` field; it calls the `public author()` method instead.

If two classes share the same name in two packages, you can use fully qualified names to avoid ambiguity, such as `java.util.Date` and `java.sql.Date`. Parent and child packages are independent with respect to access control: `vn.lesson` and `vn.lesson.domain` are **not** considered the same package.

## 6. Valid "Mutual References" and Cycles to Avoid

### 6.1. Bidirectional Type Relationships Differ from Runtime Loops

In the example, `Author` declares `Book featuredBook`, while `Book` declares `Author author`. That is a **type-relationship cycle**, which is valid in Java. The program only calls `feature` after both objects have been created.

Do not infer that every kind of cycle is valid:

- Two classes attempting to `extends` each other directly or indirectly are rejected due to **cyclic inheritance**.
- Two constructors unconditionally instantiating each other (`new A()` in A's constructor calls `new B()`, and B's constructor calls `new A()`) can lead to a `StackOverflowError`.
- Getter `A.toString()` calling `B.toString()` and `B.toString()` calling back can cause infinite recursion.
- Initializing `static` fields across multiple classes can observe default values before initialization finishes, or trigger initialization errors. You need to understand initialization order according to the Java Language Specification.
- Serializers, loggers, and equality comparisons that deeply traverse the entire object graph can loop infinitely if cycles are not handled.

**Practical rule:** mutual references should appear only when the data model genuinely needs a bidirectional relationship. Separate object construction from relationship wiring if sequential construction could cause a constructor call cycle.

### 6.2. Bidirectional Dependencies Make Design Harder to Maintain

Two classes referencing each other's types can compile, yet if multiple packages cross-call everywhere, the code becomes hard to test and hard to change. In a system with `app → service → repository` layers, it is usually best to keep the dependency direction consistent:

~~~text
app/Main  --->  service/BookService  --->  domain/Book
                           |
                           +----> repository/BookRepository (interface)
                                          ^
                                          |
                              repository/InMemoryBookRepository
~~~

This is a design-guidance diagram, **not** additional files for the runnable example in section 3. Placing an interface at an appropriate layer lets high-level components depend on a contract rather than a concrete implementation class. When access from object A to B and back is unnecessary, storing only one direction, or passing data as a method parameter, is usually simpler.

In Maven/Gradle, dependency cycles **between projects/modules** are a different matter: build tools, JPMS, and architectural design each have their own rules. Do not take the fact that two classes compile together to mean two Java modules can `requires` each other; JPMS does not allow module cycles of that form.

## 7. Multi-Stage Compilation, External Libraries, and JPMS

The example uses a single `javac` call with all source files. When built in multiple stages, classes compiled in an earlier stage must be present on the **compile classpath** of the subsequent stage. For instance, to compile `Main.java` after `Book`, `Author`, and `BookCatalog` are already in `out`:

~~~sh
javac --release 17 -encoding UTF-8 -cp out -d out src/vn/lesson/app/Main.java
~~~

This command is valid **only** when `out` already contains compatible bytecode for the dependent classes. If `out` lacks them and `-sourcepath` is not set, `javac` will report missing symbols or packages. If you change a dependent class's API, you must recompile the affected parts; do not rely on stale `.class` files.

For external JARs, add the library to the classpath at compile time, and at runtime if the application needs those classes while running. On Windows, classpath entries are separated by `;`; on Linux/macOS by `:`. Do not confuse these path separators with `.` in package names.

When moving to **named modules** (`module-info.java`), you must declare `requires` for other modules and `exports` for public packages intended for other modules to use. `import` does not substitute for `requires` or `exports`; nor are classpath and module path equivalent. The section 3 example is a simple application running on the classpath without `module-info.java`.

## 8. Diagnosing Common Errors

| Symptom | Common cause | How to check/fix |
|---|---|---|
| `cannot find symbol: class Book` | Missing source file during compilation, wrong package/class name, or missing compile classpath/sourcepath | Verify the `package` declaration and `Book.java` location, then compile all needed sources or specify `-sourcepath`. |
| `package vn.lesson.domain does not exist` | Compiler cannot find the package in the source/class path | Set the proper source root, pass the dependent files, or provide an appropriate classpath. |
| `class Book is public, should be declared in a file named Book.java` | File name does not match the `public` top-level type name | Rename it to exact `Book.java`; check uppercase/lowercase. |
| `Book is not public ... cannot be accessed from outside package` | Top-level class lacks `public` | Adjust access level to match the intended API rather than trying to fix it with `import`. |
| `has private access` | Directly accessing a `private` field/method of another class | Use an allowed accessor API such as `book.author()`, or redesign the contract. |
| `Could not find or load main class vn.lesson.app.Main` | Wrong runtime classpath root, wrong fully qualified class name, or not compiled yet | Verify `out/vn/lesson/app/Main.class`, then run `java -cp out vn.lesson.app.Main`. |
| `NoClassDefFoundError` | Class present at compile time is missing at runtime, or class initialization failed | Check the runtime classpath/module path and the root cause in the stack trace. |
| `NoSuchMethodError` | Bytecode calls an API that does not match the class/JAR version loaded at runtime | Clean build output, compile and run with the same dependency/version set. |
| `StackOverflowError` | Two objects invoke each other's methods/constructors without a stopping condition | Follow the stack trace to locate the repeating call chain; change construction/wiring or add a termination condition. |
| `illegal character: '\uFEFF'` at file start | File saved as UTF-8 with BOM which `javac` reads as a source character | Re-save source as UTF-8 without BOM; keep using `-encoding UTF-8`. |

**Effective investigation sequence:** read the first `javac` error → identify the missing type/name → open the declaring file → compare `package`, file name, and access level → check source root and compile classpath → recompile → if it fails only at runtime, check runtime classpath and bytecode/JARs. Do not tweak `import` lines blindly when the root cause is the class lookup path.

## 9. Practice and Comprehension Check

Try extending the runnable example:

1. Create `src/vn/lesson/domain/Publisher.java` with `public final class Publisher`, a `name` field, and a getter. Have `Book` reference `Publisher`; then update `Main`, `BookCatalog`, and the compile command to also display the publisher.
2. Move `BookCatalog` into package `vn.lesson.app`, updating its `package` line, file path, and `import` statements accordingly. Predict the error if you only change the directory and forget to update `package`.
3. Try removing `public` from the `Book` declaration: why can `Author` in the same package still use it, while `Main` and `BookCatalog` in other packages can no longer access it?
4. Try invoking `javac` with only `Main.java` into an empty output directory **without** specifying `-sourcepath src`, then add that option and compare the results.
5. Try changing `Author.feature(Book)` to unconditionally call back `book.author().feature(book)`. Identify why runtime recursion forms even though the code compiles cleanly; restore the original after experimenting.

**Self-check:** can you explain why `Author.java` and `Book.java` can mutually reference each other's types, whereas an `extends` cycle or `requires` cycle is invalid? Can you distinguish `-d`, `-sourcepath`, and `-cp`? Can you predict `.class` output locations and the `java` command based on the package?

## 10. Checklist Before Finalizing a Multi-File Project

- Each Java file has a matching name, `package` declaration, and location; `public` top-level types follow naming rules.
- Cross-package references use proper `import` statements/qualified names, and the API actually has the required visibility.
- All dependent sources and JARs are present on the appropriate sourcepath/classpath/module path for each stage.
- Compile into a separate output directory, and run using the **fully qualified class name** on the appropriate runtime classpath.
- Do not create unconditional constructor loops, recursion, or static initialization cycles merely because types have a bidirectional relationship.
- For large projects, let a build tool manage dependencies, incremental compilation, and testing; keep dependency directions across layers/modules clear.

The expected result is a type graph with clear relationships, easy to trace from `Main` to its dependent classes, and a compilation workflow that is reproducible on another machine.
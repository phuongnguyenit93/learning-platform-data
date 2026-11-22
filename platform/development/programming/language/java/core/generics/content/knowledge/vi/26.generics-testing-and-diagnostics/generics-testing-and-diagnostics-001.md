# Viết mẫu mã phải biên dịch và mẫu mã phải bị từ chối — kiểm thử hợp đồng Java Generics

## 1. Mục tiêu

Một API generic tốt không chỉ chạy đúng với đầu vào hợp lệ, mà còn **ngăn caller viết những lời gọi sai kiểu ngay ở thời điểm biên dịch**. Vì vậy, khi kiểm thử generics, cần xây **hai nhóm mẫu mã đối chứng**:

- **Positive compilation test:** Đoạn mã sử dụng đúng hợp đồng phải được `javac` chấp nhận; nếu có `main` hoặc assertions thì chạy thêm để kiểm tra kết quả thực.
- **Negative compilation test:** Đoạn mã cố ý vi phạm một luật generic phải bị `javac` **từ chối**. Đây không phải test ném exception trong runtime: source sai không trở thành chương trình hợp lệ.
- **Warning/policy test:** Một số thao tác raw/unchecked chỉ phát **warning**, vẫn compile khi không bật `-Werror`. Cần tách khỏi những luật cấm do ngôn ngữ.
- **Runtime test:** Những vấn đề như kiểm tra dữ liệu từ legacy API, `Class.cast` hoặc heap pollution có thể chỉ bộc lộ khi chạy; phải viết test riêng.

Bài này thuộc **Java Core – Generics / Kiểm thử và lỗi**. Các chương trình đầy đủ dưới đây đã được kiểm chứng với **Java 17**, `javac --release 17 -Xlint:all -Werror` và `java`. Bộ harness dùng `javax.tools.JavaCompiler` đã xác nhận **2 mẫu được chấp nhận, 6 mẫu bị từ chối**; các ví dụ raw type cũng được kiểm tra riêng với và không có `-Werror`.

Sau khi hoàn thành, bạn sẽ biết chọn kiểu test đúng, tạo cặp code phải compile / không được compile cho invariance, wildcards, bounds, generic arrays, erasure, type variables; kiểm tra exit code/diagnostics; tự động hóa bằng Compiler API; và tránh false positive trong CI.

## 2. Bốn loại kết quả cần phân biệt

| Ví dụ | Kết quả biên dịch | Khi chạy | Loại test |
| --- | --- | --- | --- |
| `List<String>` thêm chuỗi | Thành công | Bình thường | Positive compilation + runtime |
| `List<String>` gán cho `List<Object>` | **Lỗi biên dịch** | Không chạy | Negative compilation |
| Thêm chuỗi qua `List<?>` | **Lỗi biên dịch** | Không chạy | Negative compilation |
| `new List<String>[2]` | **Lỗi biên dịch** | Không chạy | Negative compilation |
| Raw `List` rồi `raw.add(42)` | Có thể thành công **kèm warning** | Có thể gây heap pollution | Warning + runtime |
| Raw `List` và bật `-Werror` | Build không thành công **do warning** | Không chạy binary của build mới | Policy test |
| `String.class.cast(42)` | Thành công | `ClassCastException` | Runtime rejection |
| Adapter nhận `List<?>` và kiểm tra phần tử | Thành công | Có thể báo lỗi nghiệp vụ | Runtime validation |

**Không được dùng lẫn thuật ngữ:** `javac` từ chối do type-checking khác với Java code được chấp nhận rồi ném `ClassCastException` khi chạy. `-Werror` còn là **chính sách build**, không biến raw type thành cú pháp bị cấm tuyệt đối.

## 3. Tiêu chí PASS/FAIL của một compilation test

**Mã được phép biên dịch** phải thỏa:

1. Đúng tên tệp/lớp, imports, classpath, target Java version và các dependencies cần thiết.
2. `javac` trả **exit code 0**.
3. Nếu dự án yêu cầu sạch warning, biên dịch với `-Xlint:all -Werror` và vẫn thành công.
4. Với chương trình runnable, `java` trả 0 và output/assertions đúng kỳ vọng.
5. Không dựa trên class files của lần compile trước đã tồn tại.

**Mã bắt buộc bị từ chối** phải thỏa:

1. Một fixture chỉ cố ý chứa **một lỗi generic cốt lõi** (hoặc tập lỗi được mô tả rõ).
2. Dù đã cung cấp đúng imports, classpath và Java baseline, `javac` trả **exit code khác 0**.
3. Có diagnostics mức **ERROR**.
4. Lỗi liên quan đến **quy tắc generic dự định kiểm tra**, không phải lỗi tên file, package hay thiếu dependency.
5. Không cố chạy fixture sau khi compile thất bại.

Với JavaCompiler API, kết quả `task.call()` là `true` khi compile thành công và `false` khi không thành công. Một negative test nên xác minh thêm `Diagnostic.Kind.ERROR`, không chỉ tìm chuỗi "error" trong console.

## 4. Cặp 1 — Invariance của generic container

**Phải được chấp nhận:**

```java
import java.util.List;

class ValidWildcard {
    static Object first(List<?> items) {
        return items.get(0);
    }

    static void run() {
        List<String> words = List.of("Java");
        List<?> values = words;
        Object item = first(values);
    }
}
```

**Phải bị từ chối:**

```java
import java.util.List;

class InvalidInvariant {
    void run() {
        List<String> words = List.of("Java");
        List<Object> objects = words;
    }
}
```

Một `String` là một `Object`, nhưng `List<String>` **không** là subtype của `List<Object>`. Nếu có thể gán, caller có thể thêm một `Integer` qua `objects`, làm hỏng danh sách vốn được tin là chỉ chứa chuỗi. `List<?>` là lựa chọn phù hợp khi chỉ cần đọc phần tử mà không đặt tên kiểu element cụ thể.

Đây là một ví dụ **negative language rule**, không phải warning hay runtime exception.

## 5. Cặp 2 — Không được ghi giá trị tùy ý vào `List<?>`

**Phải biên dịch:**

```java
import java.util.List;

class ValidRead {
    static int count(List<?> items) {
        return items.size();
    }
}
```

**Phải bị từ chối:**

```java
import java.util.List;

class InvalidWildcardWrite {
    static void add(List<?> items) {
        items.add("abc");
    }
}
```

Ở đây compiler không biết `?` có phải `String` hay không. Nó có thể là `List<Integer>` hoặc `List<Number>`, nên thêm `"abc"` không được chứng minh an toàn. Chẩn đoán của `javac` có thể nhắc đến **capture of ?** / `CAP#1`.

Đừng hiểu `List<?>` là immutable tuyệt đối: những method như `clear` có thể compile; nếu list là mutable, chúng vẫn có thể sửa list. Wildcard hạn chế **loại phần tử được phép ghi qua tham chiếu ấy**, không tự cấm tất cả mutation.

## 6. Cặp 3 — Giới hạn kiểu `T extends Number`

**Phải biên dịch:**

```java
class ValidBound {
    static <T extends Number> double number(T value) {
        return value.doubleValue();
    }

    static void run() {
        double x = number(Integer.valueOf(7));
    }
}
```

**Phải bị từ chối:**

```java
class InvalidBound {
    static <T extends Number> void take(T value) {}

    void run() {
        take("x");
    }
}
```

`Integer` thỏa bound `Number`; `String` không thỏa. Những lỗi ở đây xuất hiện khi giải các ràng buộc type inference. Không cần chạy method để biết một `String` không phù hợp với tham số kiểu bị giới hạn bởi `Number`.

## 7. Cặp 4 — Generic array creation và reifiability

**Phải biên dịch:**

```java
import java.util.List;

class ValidWildcardArray {
    List<?>[] groups = new List<?>[2];
}
```

**Phải bị từ chối:**

```java
import java.util.List;

class InvalidGenericArray {
    List<String>[] groups = new List<String>[2];
}
```

Mảng Java có runtime component type; `List<String>` là non-reifiable do type erasure nên không được dùng làm component khi tạo mảng bằng cú pháp này. `List<?>[]` là dạng hợp lệ, nhưng **không khẳng định** mọi list trong mảng chứa chuỗi.

Nếu một generic varargs array xuất hiện trong Java source, compiler có thể cảnh báo về **possible heap pollution** thay vì từ chối ngay toàn bộ method; đó là một kịch bản warning riêng, không nên trộn với luật `new List<String>[2]`.

## 8. Cặp 5 — Erasure làm hai overload đụng nhau

**Phải biên dịch:**

```java
import java.util.List;

class ValidNames {
    void showStrings(List<String> items) {}
    void showNumbers(List<Integer> items) {}
}
```

**Phải bị từ chối:**

```java
import java.util.List;

class InvalidErasureOverload {
    void show(List<String> items) {}
    void show(List<Integer> items) {}
}
```

Generic arguments bị xóa trong method descriptor. Hai overload tên `show` với tham số erased đều là `List` không thể tạo hai chữ ký khác nhau ở JVM; `javac` từ chối do name clash. Đổi tên method hoặc dùng các tham số thực sự phân biệt về erased types thay vì mong runtime phân biệt `List<String>` và `List<Integer>`.

## 9. Cặp 6 — `T.class` không được phép với biến kiểu generic

**Phải biên dịch:**

```java
class ValidTypeToken {
    static <T> boolean matches(Object value, Class<T> type) {
        return type.isInstance(value);
    }
}
```

**Phải bị từ chối:**

```java
class InvalidTypeVariableClass<T> {
    Class<?> token() {
        return T.class;
    }
}
```

`T` trong generic class không là một runtime class literal. Muốn kiểm tra class ở runtime, hãy **truyền token `Class<T>`** vào API thay vì tưởng rằng compiler luôn giữ lại actual type arguments của mọi object.

## 10. Positive runnable demo — nhiều hợp đồng generic trong một chương trình

Tạo tệp **`GenericsContractDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Function;

public class GenericsContractDemo {
    static <T> void copy(
            List<? extends T> source,
            List<? super T> target) {
        for (T item : source) target.add(item);
    }

    static double sum(List<? extends Number> numbers) {
        double result = 0;
        for (Number n : numbers) result += n.doubleValue();
        return result;
    }

    static void swapAny(List<?> items, int i, int j) {
        swapCaptured(items, i, j);
    }

    private static <T> void swapCaptured(
            List<T> items, int i, int j) {
        T old = items.get(i);
        items.set(i, items.get(j));
        items.set(j, old);
    }

    static <T extends Comparable<? super T>> T maximum(
            List<? extends T> items) {
        if (items.isEmpty())
            throw new IllegalArgumentException("empty");
        T result = items.get(0);
        for (T item : items)
            if (item.compareTo(result) > 0) result = item;
        return result;
    }

    static <T, R> List<R> map(
            List<? extends T> items,
            Function<? super T, ? extends R> mapper) {
        List<R> result = new ArrayList<>();
        for (T item : items) result.add(mapper.apply(item));
        return List.copyOf(result);
    }

    public static void main(String[] args) {
        List<Integer> numbers = List.of(5, 8);
        List<Number> output = new ArrayList<>();
        copy(numbers, output);
        System.out.println("copied: " + output);
        System.out.println("sum: " + sum(numbers));

        List<String> words =
                new ArrayList<>(List.of("left", "right"));
        swapAny(words, 0, 1);
        System.out.println("swapped: " + words);
        System.out.println("maximum: "
                + maximum(List.of("apple", "pear")));

        Function<CharSequence, StringBuilder> upper =
                s -> new StringBuilder(
                        s.toString().toUpperCase(java.util.Locale.ROOT));
        List<CharSequence> result = GenericsContractDemo
                .<CharSequence, CharSequence>map(
                        List.of("java", "type"), upper);
        System.out.println("mapped: " + result);
    }
}
```

Chạy:

```bash
javac --release 17 -Xlint:all -Werror GenericsContractDemo.java
java GenericsContractDemo
```

**Stdout đã xác minh:**

```text
copied: [5, 8]
sum: 13.0
swapped: [right, left]
maximum: pear
mapped: [JAVA, TYPE]
```

Các khía cạnh được bao phủ:

- `copy(List<? extends T>, List<? super T>)`: source sản xuất `T`, destination tiêu thụ `T` (**PECS**).
- `sum(List<? extends Number>)`: chấp nhận `List<Integer>` khi chỉ cần đọc như `Number`.
- `swapAny(List<?>)` + private `swapCaptured(List<T>)`: compiler capture một element type chưa biết nhưng thống nhất để hoán đổi dữ liệu của **cùng list**.
- `maximum`: bound `T extends Comparable<? super T>` cho phép so sánh và giữ kiểu phần tử trong return type.
- `map`: callback nhận supertype của `T` và tạo subtype của `R`; ví dụ function nhận `CharSequence`, trả `StringBuilder` trong một lời gọi yêu cầu kết quả `CharSequence`.

Đây là **positive compile test** có ích vì đã thử cả kiểu con/kiểu cha và wildcard capture thay vì chỉ chấp nhận một trường hợp `List<String>` đơn giản.

Không kết luận từ đó rằng tất cả list mutable. `swapAny` được thử trên `ArrayList`; nếu dùng list bất biến từ `List.of(...)`, phép `set` có thể ném `UnsupportedOperationException` dù type checking hợp lệ.

## 11. Runtime demo — kiểm tra dữ liệu không nằm trong tầm nhìn compiler

Tạo tệp **`CheckedBoundaryDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class CheckedBoundaryDemo {
    static <T> List<T> checkedCopy(
            List<?> source, Class<T> token) {
        Objects.requireNonNull(source, "source");
        Objects.requireNonNull(token, "token");

        List<T> result = new ArrayList<>();
        for (int i = 0; i < source.size(); i++) {
            Object value = source.get(i);
            if (!token.isInstance(value)) {
                throw new IllegalArgumentException(
                        "index=" + i);
            }
            result.add(token.cast(value));
        }
        return List.copyOf(result);
    }

    public static void main(String[] args) {
        System.out.println("accepted: "
                + checkedCopy(
                        List.of("An", "Binh"), String.class));
        try {
            checkedCopy(List.of("An", 42), String.class);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected at runtime: "
                    + ex.getMessage());
        }
        System.out.println("list token not enough: "
                + List.class.isInstance(List.of(42)));
    }
}
```

Lệnh:

```bash
javac --release 17 -Xlint:all -Werror CheckedBoundaryDemo.java
java CheckedBoundaryDemo
```

**Stdout đã xác minh:**

```text
accepted: [An, Binh]
rejected at runtime: index=1
list token not enough: true
```

Đây là ví dụ **compile thành công**, sau đó **chủ động từ chối dữ liệu sai ở runtime** bằng `IllegalArgumentException`. Nó không phải negative compilation test.

`List.class` không giữ type argument `String` ở runtime. Một `List<Integer>` vẫn thỏa `List.class.isInstance(...)`. Muốn phát hành một `List<String>` đáng tin từ `List<?>` lấy ở ranh giới dữ liệu, cần duyệt kiểm tra từng phần tử và tạo danh sách typed mới như ví dụ.

## 12. Viết các mẫu âm thành những fixture độc lập

Một cách tổ chức hợp lý:

```text
project/
  src/main/java/                   # Production code: phải compile
  src/test/java/                   # Harness, JUnit test: phải compile
  src/test/resources/
    compile-positive/
      ValidWildcard.java
      ValidBound.java
    compile-negative/
      InvalidInvariant.java
      InvalidWildcardWrite.java
      InvalidBound.java
      InvalidGenericArray.java
      InvalidErasureOverload.java
      InvalidTypeVariableClass.java
```

Các tên thư mục là gợi ý, không phải quy định của Gradle/Maven. Quan trọng nhất: **không để các tệp cố ý không compile nằm trong một source set mà compiler build chính luôn xử lý**. Thay vào đó, một compiler harness đọc fixtures và compile mỗi fixture riêng.

Khi đặt tên fixture, chọn tên luật đang bị vi phạm thay vì `Bad1`, `Bad2`. Mỗi negative fixture nên có **positive counterpart**, để chứng minh môi trường compile không bị lỗi trước khi đi tới quy tắc kiểm thử.

## 13. Java Compiler API — một harness chạy cả mẫu dương và âm

JDK cung cấp `javax.tools.JavaCompiler`. API này có thể biên dịch những source strings trong bộ nhớ, trả kết quả thành công/thất bại và cung cấp diagnostics. Mẫu dưới đây là **một chương trình độc lập**, đã chạy thực tế với Java 17.

Tạo tệp **`CompileContractHarness.java`**:

```java
import java.io.IOException;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class CompileContractHarness {
    record Case(String name, String source, boolean shouldCompile) {}

    static final class Source extends SimpleJavaFileObject {
        private final String code;

        Source(String className, String code) {
            super(URI.create("string:///" + className
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(
                boolean ignoreEncodingErrors) {
            return code;
        }
    }

    static void check(Case test, Path output) throws IOException {
        JavaCompiler compiler =
                ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("A JDK is required");
        }

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager manager =
                compiler.getStandardFileManager(
                        diagnostics, null, null)) {

            List<String> options = List.of(
                    "--release", "17",
                    "-Xlint:all", "-Werror", "-proc:none",
                    "-d", output.toString());

            JavaCompiler.CompilationTask task =
                    compiler.getTask(null, manager, diagnostics,
                            options, null,
                            List.of(new Source(
                                    test.name(), test.source())));

            boolean actual = Boolean.TRUE.equals(task.call());
            long errors = diagnostics.getDiagnostics().stream()
                    .filter(d ->
                            d.getKind() == Diagnostic.Kind.ERROR)
                    .count();

            if (actual != test.shouldCompile()
                    || (!test.shouldCompile() && errors == 0)) {
                throw new AssertionError(
                        "Unexpected compile result: " + test.name());
            }

            System.out.println(
                    (actual ? "COMPILES: " : "REJECTED: ")
                    + test.name());
        }
    }

    public static void main(String[] args) throws IOException {
        Path classes = Files.createTempDirectory(
                "generic-compile-contracts");
        List<Case> cases = List.of(
            new Case("ValidWildcard",
                    "class ValidWildcard {"
                    + " static int size(java.util.List<?> x)"
                    + " { return x.size(); } }",
                    true),
            new Case("ValidBound",
                    "class ValidBound {"
                    + " static <T extends Number> double x(T n)"
                    + " { return n.doubleValue(); } }",
                    true),
            new Case("InvalidInvariant",
                    "class InvalidInvariant { void f() {"
                    + " java.util.List<String> a="
                    + "java.util.List.of(\"x\");"
                    + " java.util.List<Object> b=a; } }",
                    false),
            new Case("InvalidWildcardWrite",
                    "class InvalidWildcardWrite {"
                    + " void f(java.util.List<?> a)"
                    + " { a.add(\"x\"); } }",
                    false),
            new Case("InvalidBound",
                    "class InvalidBound {"
                    + " static <T extends Number> void take(T x) {}"
                    + " void f() { take(\"x\"); } }",
                    false),
            new Case("InvalidGenericArray",
                    "class InvalidGenericArray {"
                    + " java.util.List<String>[] xs ="
                    + " new java.util.List<String>[2]; }",
                    false),
            new Case("InvalidErasureOverload",
                    "class InvalidErasureOverload {"
                    + " void f(java.util.List<String> x) {}"
                    + " void f(java.util.List<Integer> x) {} }",
                    false),
            new Case("InvalidTypeVariableClass",
                    "class InvalidTypeVariableClass<T> {"
                    + " Class<?> token() { return T.class; } }",
                    false)
        );

        for (Case test : cases) check(test, classes);
        System.out.println(
                "ALL COMPILE CONTRACTS PASSED: " + cases.size());
    }
}
```

Chạy:

```bash
javac --release 17 -Xlint:all -Werror CompileContractHarness.java
java CompileContractHarness
```

**Stdout đã kiểm chứng:**

```text
COMPILES: ValidWildcard
COMPILES: ValidBound
REJECTED: InvalidInvariant
REJECTED: InvalidWildcardWrite
REJECTED: InvalidBound
REJECTED: InvalidGenericArray
REJECTED: InvalidErasureOverload
REJECTED: InvalidTypeVariableClass
ALL COMPILE CONTRACTS PASSED: 8
```

Giải thích từng thành phần:

- `Source extends SimpleJavaFileObject` tạo một Java source trong bộ nhớ với URI `string:///TênLớp.java`. Tên của source và tên class nhất quán để lỗi về tên file không làm test âm thành công giả.
- `JavaCompiler.getTask` thực hiện một lần compile riêng cho từng case. Mỗi case dùng `DiagnosticCollector` riêng để không lẫn lỗi cũ.
- `--release 17` khóa mức Java source và platform APIs được compiler sử dụng theo baseline Java 17.
- `-Xlint:all -Werror` áp dụng chính sách sạch warning cho mẫu dương; với mẫu âm, vẫn cần kiểm tra nguyên nhân thất bại.
- `-proc:none` tắt annotation processing tránh phụ thuộc ngoài ý muốn. Nếu dự án cần processors, cấu hình một compile-testing task thích hợp thay vì tắt cơ học.
- `-d` đưa output classes vào thư mục tạm thay vì ghi đè production/test classes. Mẫu demo không dọn thư mục tạm; trong test framework thực nên quản lý vòng đời bằng cleanup.
- `getSystemJavaCompiler()` có thể trả `null` khi không chạy trên môi trường JDK có compiler; harness báo lỗi rõ ràng trong trường hợp đó.

**Giới hạn của harness:** một negative compile test có `ERROR` **chưa đủ xác nhận luật mục tiêu** nếu code cũng có lỗi khác. Bộ fixture đã dùng rất nhỏ, độc lập và được kiểm thử, nhưng trong CI nghiêm ngặt còn nên xác minh chẩn đoán gắn với biểu thức cần kiểm tra (file/dòng/mã lỗi phù hợp) và luôn có positive counterpart. Không nên so khớp cứng **toàn bộ nội dung tiếng Anh** của error message vì nó có thể khác JDK/locale.

## 14. Cảnh báo raw type không phải lỗi biên dịch bắt buộc

Tạo tệp **`RawWarningDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class RawWarningDemo {
    public static void main(String[] args) {
        List<String> typed = new ArrayList<>();
        List raw = typed;
        raw.add(123);

        System.out.println("stored: " + typed);
        try {
            String value = typed.get(0);
            System.out.println(value);
        } catch (ClassCastException ex) {
            System.out.println("runtime: "
                    + ex.getClass().getSimpleName());
        }
    }
}
```

**Không bật `-Werror`:**

```bash
javac -Xlint:rawtypes -Xlint:unchecked RawWarningDemo.java
java RawWarningDemo
```

`javac` đã được kiểm chứng trả exit code **0** nhưng phát **hai warnings**: `[rawtypes]` ở `List raw` và `[unchecked]` ở `raw.add(123)`.

Stdout chương trình:

```text
stored: [123]
runtime: ClassCastException
```

Raw alias và typed alias tham chiếu cùng một `ArrayList`, nhưng raw alias chèn `Integer`; khi đọc như `String`, runtime cast bị lỗi. Đây là bằng chứng về **heap pollution và hậu quả runtime**, không phải bằng chứng Java compiler cấm raw type.

**Bật `-Werror`:**

```bash
javac -Xlint:rawtypes -Xlint:unchecked -Werror RawWarningDemo.java
```

Ở lượt kiểm chứng, lệnh trả exit code **1** và có thông báo:

```text
error: warnings found and -Werror specified
```

Đây là **policy rejection**. Để kiểm thử đúng, ghi rõ compiler flags và tách case raw warning khỏi negative tests của invariance/generic array/bounds.

## 15. Kiểm tra exit code đúng cách trong terminal

### Bash

```bash
# Chương trình hợp lệ: muốn javac thành công.
if ! javac --release 17 -Xlint:all -Werror GenericsContractDemo.java; then
  echo "FAIL: valid code did not compile"
  exit 1
fi
java GenericsContractDemo || exit 1

# Chương trình cố ý sai: muốn javac thất bại.
if javac --release 17 InvalidInvariant.java; then
  echo "FAIL: invalid code unexpectedly compiled"
  exit 1
else
  echo "PASS: invalid code was rejected"
fi
```

### Windows PowerShell

```powershell
javac --release 17 -Xlint:all -Werror GenericsContractDemo.java
if ($LASTEXITCODE -ne 0) {
    throw "Valid code unexpectedly failed"
}
java GenericsContractDemo
if ($LASTEXITCODE -ne 0) {
    throw "Valid program unexpectedly failed"
}

javac --release 17 InvalidInvariant.java
if ($LASTEXITCODE -eq 0) {
    throw "Invalid code unexpectedly compiled"
}
Write-Output "PASS: invalid source rejected"
```

Ở PowerShell 5.1, một external command trả nonzero **không phải lúc nào** khiến toàn bộ script tự dừng; cần đọc `$LASTEXITCODE` ngay sau lệnh. Đừng tiếp tục chạy `java` sau một lần compile thất bại, vì có thể còn class file cũ.

Trong pipeline thực, tốt nhất dùng output folder riêng/sạch cho từng case, quản lý classpath theo fixture và xóa artifacts sau test. Dù test manual hay automated, **sự thành công của shell script** không có giá trị nếu nó vô tình bỏ qua exit code của `javac`.

## 16. Phân biệt cảnh báo và chẩn đoán trong compiler API

Compiler trả những loại diagnostics khác nhau, ví dụ:

- `Diagnostic.Kind.ERROR` — lỗi khiến source không được chấp nhận theo luật được áp dụng.
- `Diagnostic.Kind.WARNING` / `MANDATORY_WARNING` — cảnh báo về nguy cơ/chính sách.
- `Diagnostic.Kind.NOTE` — thông tin giải thích thêm.

Trong một negative test, hãy kiểm tra `ERROR`; nhưng nếu đang bật `-Werror`, có thể nhận lỗi tổng quát do warning policy. Nếu mục tiêu là chứng minh **Java language type rule**, có thể chạy fixture đó **không có `-Werror`** để tách policy khỏi type-system rejection.

Các tùy chọn `-Xdiags:verbose` và `-Xlint` có ích trong lúc điều tra lỗi, nhưng chuỗi text có thể thay đổi giữa compiler/version. Với test dạy kiến thức, mô tả **bản chất** và minh họa excerpt là đủ. Với compiler regression test thực sự, cần khóa toolchain và chọn mức chẩn đoán phù hợp.

## 17. Cách ngăn false-positive negative tests

**Sai lầm 1 — Lỗi do thiếu import hoặc tên file:** `javac` trả nonzero nhưng chẳng chứng minh điều gì về generics. Dùng fully qualified names cho fixture in-memory hoặc imports đúng; đặt tên file/class nhất quán.

**Sai lầm 2 — Một file chứa nhiều lỗi không liên quan:** chỉ cần một lỗi phụ cũng khiến case bị từ chối. Tách thành từng nguồn nhỏ, tương ứng từng luật.

**Sai lầm 3 — Không có positive control:** nếu một file hợp lệ cùng dependencies cũng không compile được, nguyên nhân có thể là cấu hình JDK/classpath chứ không phải luật generic.

**Sai lầm 4 — So khớp stdout hoặc message đúng từng ký tự:** compiler diagnostics có khác biệt về đường dẫn, locale, line numbers và cách diễn đạt. Ưu tiên `Kind.ERROR` và điều kiện vị trí/nội dung được chuẩn hóa.

**Sai lầm 5 — Nhầm warning-as-error với lỗi ngôn ngữ:** raw types có thể compile khi tắt `-Werror`. Test policy cần tên và flags khác test negative compile.

**Sai lầm 6 — Chạy class cũ sau compile thất bại:** dùng output folder tạm riêng và chỉ chạy positive binary nếu compile hiện tại thành công.

**Sai lầm 7 — Dùng unchecked cast để ép positive example compile:** làm thế có thể che lỗi cần phát hiện, đẩy `ClassCastException` sang runtime. Mẫu dương nên sạch raw/unchecked khi có thể.

**Sai lầm 8 — Chỉ kiểm tra source đúng một phiên bản JDK:** các đặc tính ngôn ngữ và thông báo lỗi có thể thay đổi. Dùng `--release`/toolchains và ghi rõ baseline.

**Sai lầm 9 — Coi một runtime `ClassCastException` là compile-time rejection:** chúng thuộc hai tầng kiểm thử; cần một fixture âm độc lập cho luật type checker.

**Sai lầm 10 — Không thử subtypes/supertypes:** một generic API có thể bác bỏ caller hợp lệ do chữ ký quá chặt. Positive test với `List<Integer>` → `List<Number>` và `Function<CharSequence,StringBuilder>` là bài kiểm tra hữu ích về độ linh hoạt.

**Sai lầm 11 — Negative test đúng luật nhưng đặt trong production source set:** làm hỏng build toàn project. Dùng test/resources hoặc compiler-in-memory fixtures.

**Sai lầm 12 — Kiểm thử fail với `-Werror` nhưng không đọc diagnostics:** có thể lỗi bắt nguồn từ một warning không liên quan. Với regression nghiêm túc, ghi nhận nguyên nhân cụ thể.

## 18. Quan sát tác động của erasure với `javap`

Sau khi compile chương trình dương, chạy:

```bash
javap -p -s GenericsContractDemo
```

Trích đoạn đã kiểm chứng:

```text
static <T> void copy(
    java.util.List<? extends T>, java.util.List<? super T>);
  descriptor: (Ljava/util/List;Ljava/util/List;)V

static double sum(java.util.List<? extends java.lang.Number>);
  descriptor: (Ljava/util/List;)D

static <T extends java.lang.Comparable<? super T>>
    T maximum(java.util.List<? extends T>);
  descriptor: (Ljava/util/List;)Ljava/lang/Comparable;

static <T, R> java.util.List<R> map(
    java.util.List<? extends T>,
    java.util.function.Function<? super T, ? extends R>);
  descriptor: (Ljava/util/List;Ljava/util/function/Function;)Ljava/util/List;
```

`javap` trình bày generic signature khi metadata có sẵn, còn JVM descriptor sử dụng erased types: `List`, `Function`, `Comparable`. Đây là cơ sở giải thích vì sao hai overload chỉ khác `List<String>` và `List<Integer>` có cùng erased signature.

**Không suy luận rằng JVM descriptors giống nhau tức mọi hợp đồng generic đều giống nhau:** compiler vẫn kiểm tra wildcard/bounds ở source trước khi tạo bytecode. `javap -v` có thể hiển thị thuộc tính `Signature` khi cần nghiên cứu sâu hơn.

## 19. Bổ sung regression tests khi sửa API công khai

Nếu thay một chữ ký:

```java
// Ban đầu:
static <T> void copy(List<T> source, List<T> target)

// Linh hoạt hơn:
static <T> void copy(
        List<? extends T> source,
        List<? super T> target)
```

hãy kiểm thử **cả hướng dương và hướng âm**:

1. Caller mới hợp lệ (ví dụ `List<Integer>` → `List<Number>`) có biên dịch không?
2. Caller sai kiểu thật sự (ví dụ nguồn chuỗi sang đích số) có vẫn bị chặn không?
3. Các method references, overloaded calls, inference với lambda có còn compile khi sử dụng public API không?
4. Với ABI đã phát hành, các erased descriptors/bridge methods có đổi không?
5. Framework đọc generic `Signature` bằng reflection có phụ thuộc vào chữ ký trước không?

Đôi khi refactor vẫn giữ descriptor erased nhưng **thay đổi source-level contract**, nên không nên chỉ kiểm tra binary link hoặc runtime unit tests. Một suite compiler contracts giúp bạn nhìn thấy những lời gọi sai đột nhiên được chấp nhận, hay những lời gọi hợp lệ bị từ chối sau khi chỉnh wildcard/bounds.

## 20. Khi nào dùng Compiler API, khi nào dùng `javac` CLI?

| Tình huống | Công cụ phù hợp | Lý do |
| --- | --- | --- |
| Học một quy tắc, chỉ 1–2 snippets | `javac` CLI | Dễ quan sát lỗi ngay |
| Nhiều positive/negative fixtures trong CI | `JavaCompiler` hoặc compile-testing framework | Tự động hóa, thu diagnostics có cấu trúc |
| Kiểm tra chương trình chạy và stdout | `javac` + `java` hoặc test framework | Compilation thôi chưa đo được behavior |
| Enforce zero warnings | `-Xlint:all -Werror` theo policy | Phân biệt lint policy với language constraints |
| Kiểm tra API baseline | `--release` và toolchain | Tránh phụ thuộc tính năng của JDK mới hơn |
| Kiểm tra overloads và erasure | `javac` + `javap` | Xem cả type-checking và erased descriptor |
| Kiểm tra dữ liệu runtime từ legacy | Unit/integration test + validation | Compiler không biết dữ liệu thật |

Đối với chương trình kiểm thử dương, có thể dùng JUnit nếu project đã có. Những đoạn minh họa `@Test` đòi imports và dependencies JUnit, nên không được quảng bá như source độc lập chạy chỉ với JDK. Harness `CompileContractHarness` ở trên **không cần JUnit**.

## 21. Bài tập và đáp án

### Bài 1 — Phân loại lỗi

`List<String> names = List.of("a"); List<Object> target = names;` thuộc loại test nào?

**Đáp án:** Negative compilation test do invariance. Nó phải bị `javac` từ chối trước runtime.

### Bài 2 — Wildcard

Vì sao `List<?>` đọc được một `Object` nhưng `list.add("x")` bị từ chối?

**Đáp án:** kiểu phần tử không được đặt tên; khi đọc có thể dùng `Object`, khi thêm `String` không chắc hợp element type thực.

### Bài 3 — Bounded generic

`take(Integer.valueOf(5))` hợp lệ còn `take("5")` bị từ chối khi `take` khai báo `<T extends Number>`, đúng không?

**Đáp án:** đúng. `Integer` là subtype `Number` còn `String` không phải.

### Bài 4 — Array generic

`new List<String>[1]` và `new List<?>[1]` có cùng kết quả compile không?

**Đáp án:** không. Loại đầu bị từ chối vì generic array creation; unbounded wildcard array type là hợp lệ.

### Bài 5 — Chạy negative fixture?

Một fixture không compile được. Có nên chạy `java Fixture` rồi kiểm tra nó ném exception?

**Đáp án:** không. Test kiểm tra compiler result và diagnostics; không chạy chương trình không hợp lệ. Một class file cũ không thuộc lần compile đó cũng không có giá trị.

### Bài 6 — Raw warning

`List raw = ...; raw.add(42);` phát warning với `-Xlint` nhưng compile thành công. Có được gọi là “mẫu phải bị từ chối bởi ngôn ngữ” không?

**Đáp án:** không. Với `-Werror` đó là policy rejection; nếu không có flag, compiler có thể tạo bytecode. Có thể kiểm tra hậu quả runtime riêng.

### Bài 7 — Lỗi wrong reason

Một test “phải fail vì invariance” lại fail do thiếu classpath. Test PASS chứ?

**Đáp án:** không; phải sửa setup và kiểm tra lỗi đúng mục tiêu. Đây là lý do cần negative fixture tối giản và positive counterpart.

### Bài 8 — JavaCompiler diagnostics

`CompilationTask.call()` trả `false`. Đã đủ chứng minh generic bound test đúng chưa?

**Đáp án:** chưa. Cần xác minh ít nhất một diagnostic ERROR và nguyên nhân liên quan tới bound, không phải lỗi khác.

### Bài 9 — Type erasure

Hai overload `f(List<String>)` và `f(List<Integer>)` có thể cùng tồn tại không?

**Đáp án:** không, vì erasure làm parameter signatures đụng nhau.

### Bài 10 — Runtime list validation

`List.class.isInstance(List.of(42))` trả gì? Nó có chứng minh input là `List<String>` không?

**Đáp án:** trả `true`; không chứng minh element type `String`. Cần kiểm tra từng phần tử nếu dữ liệu không đáng tin.

### Bài 11 — Bài test về API PECS

Một method có `List<? extends T> source` và `List<? super T> destination`, dùng `List<Integer>` làm nguồn, `List<Number>` làm đích có hợp lệ không?

**Đáp án:** hợp lệ. Source cung cấp `Integer` như `T`, destination chấp nhận `T` hoặc supertype.

### Bài 12 — Mục tiêu `-Werror`

Nếu muốn zero warnings trên JDK 17, nên dùng lệnh nào?

**Đáp án:** `javac --release 17 -Xlint:all -Werror File.java` và kiểm tra exit code 0. Chỉ thêm `-Werror` khi đó là chính sách phù hợp, không coi tất cả warnings là lỗi cú pháp của Java.

## 22. Checklist cuối bài

- [ ] Mỗi luật có một **positive fixture** và một **negative fixture** liên quan.
- [ ] Mẫu âm thất bại vì **đúng quy tắc**; không vì lỗi import, tên class/file hay classpath.
- [ ] Mẫu dương biên dịch bằng JDK baseline và không có unchecked/raw warning ngoài chủ đích.
- [ ] Mọi lệnh `javac`/`java` đều được kiểm tra exit code.
- [ ] Không chạy một `.class` cũ sau lần compile thất bại.
- [ ] Warning-as-error được phân biệt với language rejection.
- [ ] Runtime validation được kiểm tra riêng với compile-time constraints.
- [ ] Nếu dùng `JavaCompiler`, kiểm tra `Diagnostic.Kind.ERROR` cho negative cases.
- [ ] Fixtures cố ý sai không xuất hiện trong source set production.
- [ ] Generic signatures được đánh giá với subtype/supertype, wildcard và bounds phù hợp.
- [ ] Output của các chương trình được đối chiếu và không bị suy đoán.
- [ ] Khi thay generic API, rerun cả dương và âm để bắt regression.

## Kết luận

**Viết mã mẫu phải biên dịch và mã mẫu phải bị từ chối** là cách kiểm thử đúng bản chất nhất của Java Generics: những lời gọi đáp ứng hợp đồng được chấp nhận, còn những lời gọi không type-safe bị ngăn ở compile time. Hãy tạo cặp đối chứng, kiểm tra exit code và diagnostics, cô lập đúng lý do compiler từ chối, và ghi rõ JDK baseline.

Kết hợp compile tests với runtime tests cho dữ liệu mà type erasure hoặc raw/unchecked API khiến compiler không thể xác minh. Khi đó, một thay đổi về `<T>`, wildcard, bound hoặc generic overload được đánh giá bằng **hợp đồng kiểu thật sự mà caller có thể hoặc không thể biên dịch**, không chỉ bằng vài test runtime tình cờ đi qua.

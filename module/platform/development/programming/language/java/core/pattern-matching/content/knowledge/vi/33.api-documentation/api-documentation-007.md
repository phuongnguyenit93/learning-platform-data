# Ghi chú phiên bản Java yêu cầu trong API và tài liệu Java Pattern Matching

## 1. Mục đích

Khi viết tài liệu cho **Java Core Pattern Matching**, câu “cần Java mới” không đủ để người học hoặc người dùng API chọn đúng JDK. Các thành phần được hoàn thiện qua nhiều bản Java: `instanceof` type patterns và records từ **Java 16**, sealed types từ **Java 17**, record patterns và pattern matching for `switch` từ **Java 21**. Một ví dụ chạy trên JDK 21 **không mặc nhiên** tương thích Java 17.

Một ghi chú phiên bản tốt cần chỉ ra:

- **Minimum Java runtime**: JVM thấp nhất có thể tải và chạy artifact.
- **Build JDK**: phiên bản JDK thực hiện build.
- **Compile target**: cú pháp và Java SE/JDK API mà source được phép dùng, thường đặt bằng `javac --release N`.
- **Preview policy**: code có cần `--enable-preview` không?
- **Tested/supported JDKs**: những runtime đã được kiểm thử và được công bố hỗ trợ.

Bài tập trung vào **cách ghi và xác minh những thông tin đó** trong README, JavaDoc, code samples, Maven/Gradle, CI và release notes.

## 2. Các mốc Java cần nhớ

| Tính năng | Final đầu tiên | Ghi chú |
| --- | --- | --- |
| `switch` expression với constant labels và `yield` | Java 14 — JEP 361 | Khác pattern `switch` |
| `value instanceof String text` | **Java 16 — JEP 394** | Preview Java 14–15 |
| Record classes `record Point(int x, int y)` | **Java 16 — JEP 395** | Record class không phải record pattern |
| `sealed`, `permits`, `non-sealed` | **Java 17 — JEP 409** | Preview Java 15–16 |
| Type patterns trong `switch` | **Java 21 — JEP 441** | Preview Java 17–20 |
| Record patterns `Point(var x, var y)` | **Java 21 — JEP 440** | Preview Java 19–20 |
| Guard `when` của pattern `switch` | Java 21 final | Cú pháp preview cũ có thể khác |
| `case null` của pattern `switch` | Java 21 final | `default` không tự xử lý null |
| Unnamed patterns `_` | Không final trong Java 21 | Preview Java 21 — JEP 443 |

Bảng dùng **mốc tính năng final, không cần preview flags**, phù hợp để định yêu cầu tối thiểu cho tài liệu và ứng dụng ổn định. Các bản preview lịch sử cần gắn nhãn riêng; không coi chúng là bằng chứng một cú pháp final đã sẵn có ở runtime cũ.

Nguồn: [Oracle Java SE 21 — Language Changes Summary](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-summary.html).

## 3. Phiên bản của JDK, source, runtime và library là bốn chuyện khác nhau

Ví dụ một dự án build bằng **JDK 21** nhưng dùng `javac --release 17`: nếu mã và các API đều tương thích, compiler phát hành class file theo target Java 17. Do đó, **build JDK = 21** không có nghĩa **minimum runtime = 21**.

Ngược lại, nếu project có code pattern `switch` Java 21, build theo `--release 21` thường tạo class-file major 65; JVM Java 17 không thể tải class đó, dù chữ ký public method có thể chỉ là `String classify(Object)`.

Ngoài cú pháp, cần kiểm tra cả:

1. **JDK API được gọi**: source target cũ nhưng gọi một API chỉ xuất hiện ở bản mới có thể gây lỗi lúc chạy. `--release N` giúp phát hiện lỗi đó ở compile time.
2. **Dependencies**: một library phụ thuộc có thể phát hành bytecode target cao hơn, dù source của module hiện tại dùng cú pháp cũ.
3. **Runtime/container**: Java được đặt trong Docker image hoặc trên server có thể khác JDK chạy compiler.
4. **Library version**: phiên bản artifact `2.3.0` không phải là phiên bản Java `21`.

Tài liệu phát hành nên công bố riêng minimum runtime, compile target và tested JDKs nếu các giá trị không trùng nhau.

## 4. Cách xác định minimum Java thực tế

| Nội dung thực tế | Mốc cú pháp final tối thiểu |
| --- | --- |
| `if (obj instanceof String text)` | Java 16 |
| `record Box<T>(T value)` kết hợp type pattern | Java 16 |
| Sealed hierarchy + records + type pattern `instanceof` | Java 17 |
| Enum `switch` expression chỉ có hằng enum | Java 14 |
| Type pattern `case String s ->` trong `switch` | Java 21 |
| Record pattern `case Point(var x, var y) ->` | Java 21 |
| Guard `case String s when ...` | Java 21 |
| Nested record patterns | Java 21 |

Chọn mốc **cao nhất trong các feature, Java API, dependency và yêu cầu runtime thực tế**. Không chỉ tìm từ khóa `switch` rồi kết luận Java 21: `switch` với hằng số và pattern `switch` là hai khả năng khác nhau.

## 5. Ví dụ Java 16: type pattern trong `instanceof`

Lưu `Java16PatternDemo.java`:

```java
import java.util.Locale;

public class Java16PatternDemo {
    static String classify(Object value) {
        if (value instanceof String text) {
            return "text:" + text.toUpperCase(Locale.ROOT);
        }
        return "other";
    }

    public static void main(String[] args) {
        System.out.println(classify("java"));
        System.out.println(classify(42));
        System.out.println(classify(null));
    }
}
```

Lệnh build/chạy bằng compiler còn hỗ trợ target 16:

```bash
javac --release 16 Java16PatternDemo.java
java Java16PatternDemo
```

Stdout:

```text
text:JAVA
other
other
```

Type pattern `instanceof String text` final từ Java 16. Nếu `value == null`, phép matching thất bại và trả `"other"`. Ví dụ **không dùng records, sealed types hoặc pattern `switch`**.

**Nhãn đề xuất ngay trước ví dụ:** “Java 16+ (final). No preview flag. JEP 394.”

## 6. Ví dụ Java 17: sealed types và `instanceof`

Java 17 đã có sealed types final nhưng **pattern matching for `switch` còn preview**. Nếu cần API non-preview tương thích Java 17, có thể xử lý sealed hierarchy bằng type patterns trong `instanceof`.

`Java17ModelDemo.java`:

```java
public class Java17ModelDemo {
    sealed interface Event permits Started, Stopped {}

    record Started(String id) implements Event {}
    record Stopped(String id) implements Event {}

    static String label(Event event) {
        if (event instanceof Started started) {
            return "start:" + started.id();
        }
        if (event instanceof Stopped stopped) {
            return "stop:" + stopped.id();
        }
        return "unknown";
    }

    public static void main(String[] args) {
        System.out.println(label(new Started("A-1")));
        System.out.println(label(new Stopped("A-1")));
        System.out.println(label(null));
    }
}
```

```bash
javac --release 17 Java17ModelDemo.java
java Java17ModelDemo
```

Stdout:

```text
start:A-1
stop:A-1
unknown
```

Ở đây `record` final từ Java 16, `sealed` final từ Java 17, còn `instanceof` pattern final từ Java 16. Phương thức chọn `"unknown"` cho null theo **hợp đồng minh họa**, không phải một hành vi bắt buộc của sealed types.

**Nhãn đề xuất:** “Java 17+; sealed classes final (JEP 409); no preview features.”

## 7. Ví dụ Java 21: record patterns + pattern `switch`

`Java21PatternsDemo.java`:

```java
public class Java21PatternsDemo {
    sealed interface Event permits Created, Paid {}

    record Created(String id) implements Event {}
    record Paid(String id, long cents) implements Event {}

    static String describe(Event event) {
        return switch (event) {
            case Created(var id) ->
                    "created:" + id;
            case Paid(var id, var cents) when cents > 0 ->
                    "paid:" + id + ":" + cents;
            case Paid(var id, var cents) ->
                    "invalid-paid:" + id;
            case null ->
                    "missing";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Created("E-1")));
        System.out.println(describe(new Paid("E-1", 500)));
        System.out.println(describe(new Paid("E-1", 0)));
        System.out.println(describe(null));
    }
}
```

```bash
javac --release 21 Java21PatternsDemo.java
java Java21PatternsDemo
```

Stdout:

```text
created:E-1
paid:E-1:500
invalid-paid:E-1
missing
```

Điểm cần giải thích trong tài liệu:

- `Created(var id)` và `Paid(var id, var cents)` là **record patterns**, final từ Java 21.
- `when cents > 0` là guard trong pattern `switch`, final từ Java 21.
- Case `Paid` không có guard xử lý những `Paid` còn lại.
- `case null` định nghĩa rõ selector null.
- Expression `switch` có thể exhaustive mà không cần `default` nhờ sealed hierarchy.

**Nhãn đề xuất:** “Java 21+ (non-preview), JEP 440 và JEP 441; build with `javac --release 21`.”

Không ghi Java 17+ chỉ vì interface `Event` là sealed: phiên bản thực sự cần cho toàn ví dụ là 21.

## 8. JavaDoc: `@since` không phải minimum JDK

Giả sử thư viện có release version **2.3.0**, và bản artifact ấy yêu cầu **Java 21**. Hai thông tin có ý nghĩa khác nhau:

- `@since 2.3.0` nghĩa là API element được giới thiệu từ **release 2.3.0 của thư viện** theo quy ước version của dự án.
- “Minimum Java runtime: 21” nói về **môi trường tải và chạy artifact**.

`@since` là một **documentation tag**, tạo mục “Since” trong JavaDoc; nó không tạo kiểm tra binary và không cấu hình compiler.

Ví dụ phương thức trong một class API (đoạn minh họa, không phải tệp độc lập):

```java
/**
 * Phân loại giá trị theo kiểu runtime.
 *
 * <p>Artifact này yêu cầu Java 21 trở lên.
 *
 * @param value giá trị đầu vào, có thể null
 * @return nhãn phân loại
 * @since 2.3.0
*/
public static String classify(Object value) {
    return switch (value) {
        case String text -> "text:" + text;
        case Integer n -> "int:" + n;
        case null -> "missing";
        default -> "other";
    };
}
```

Nếu API đã xuất hiện từ thư viện version 1.8.0 và chỉ **implementation** chuyển sang pattern `switch` ở 2.3.0, không tự sửa `@since` thành 2.3.0. Lịch sử API và yêu cầu Java của artifact khác nhau.

Với các class thuộc **Java Platform API**, `@since 21` có thể chỉ release của đặc tả Java Platform API. Đừng mặc nhiên áp dụng cách ghi ấy cho thư viện bên thứ ba có hệ thống phiên bản riêng.

## 9. Mẫu README về tương thích Java

Đoạn dưới đây là **mẫu để chỉnh theo dữ liệu thật của module**:

```markdown
## Java compatibility

- Minimum Java runtime: **21**
- Build JDK: **21**
- Compile target: **21** (`javac --release 21`)
- Pattern-matching preview flag required: **No**
- Language features:
  - Type pattern `instanceof` (final in Java 16)
  - Records (final in Java 16)
  - Sealed types (final in Java 17)
  - Record patterns and pattern `switch` (final in Java 21)

### Quick start

    javac --release 21 Java21PatternsDemo.java
    java Java21PatternsDemo

### Notes

The published artifact requires a Java 21-or-newer runtime.
Java 17 cannot load Java 21-targeted class files.
```

Mẫu không tự khẳng định project cụ thể đã được test bằng Java 21. Với hệ thống có nhiều ví dụ Java16/17/21, nên gắn thêm **nhãn phiên bản ngay trước mỗi code block** chứ không chỉ một câu chung ở trang chủ.

## 10. Chứng minh bằng `javac --release`

Các lệnh sau minh họa cách kiểm tra ba chương trình:

```bash
javac --release 16 Java16PatternDemo.java
javac --release 17 Java17ModelDemo.java
javac --release 21 Java21PatternsDemo.java
```

Dùng compiler còn hỗ trợ target tương ứng. Theo hướng dẫn `javac`, `--release N` yêu cầu compiler:

1. Kiểm tra ngôn ngữ theo release N.
2. Giới hạn Java SE/JDK API tham chiếu theo release N.
3. Tạo class file target cho release N.

Không kết hợp `--release` với `--source`/`--target` trong cùng lệnh. Cấu hình chỉ có `-target 17` không mạnh bằng `--release 17` để phát hiện tham chiếu API mới từ JDK đang chạy compiler.

**Negative tests có chủ đích:**

```bash
javac --release 17 Java21PatternsDemo.java
javac --release 16 Java17ModelDemo.java
```

Với compiler hỗ trợ các target ấy, **hai lệnh phải bị từ chối** vì source dùng tính năng chưa final ở release được yêu cầu. Đặt loại test này riêng khỏi source production và kiểm tra nonzero exit code; không phụ thuộc tuyệt đối vào câu chữ diagnostic.

Nếu JDK compiler không còn hỗ trợ một giá trị `--release` cũ, đó là giới hạn công cụ chứ không nhất thiết là lỗi cú pháp ở release gốc.

## 11. Class-file version là bằng chứng khác với source

| Java target | Major class-file version |
| --- | --- |
| 16 | 60 |
| 17 | 61 |
| 21 | 65 |

Kiểm tra class đã compile:

```bash
javap -verbose Java21PatternsDemo
```

Với build `--release 21`, output có dòng:

```text
major version: 65
```

JVM Java 17 chỉ hỗ trợ tối đa major 61 nên **không thể nạp class Java21 major65**, thường dẫn đến `UnsupportedClassVersionError`.

Lưu ý class-file major không đủ chứng minh mọi dependency đều hoạt động trên JVM tối thiểu. Một dependency hoặc framework có yêu cầu JDK mới hơn vẫn có thể làm ứng dụng thất bại khi chạy.

Preview class files của các Java release hiện đại có thể mang **minor version 65535**. Khi preview feature trở thành final, hãy clean rebuild với JDK và release tương ứng; không sửa header class file thủ công để vượt kiểm tra.

## 12. Maven: đặt compile target tường minh

Trong `pom.xml` của module Java 21 (đoạn cấu hình, không phải file hoàn chỉnh):

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

Cần dùng JDK/Maven/compiler plugin hỗ trợ target 21. Nên pin compiler plugin trong project phát hành để tránh sự khác nhau do phiên bản Maven mặc định.

Kiểm tra:

```bash
mvn --version
mvn clean verify
```

`mvn --version` cho biết JVM chạy Maven; dự án dùng toolchains có thể chọn compiler JDK khác, vì vậy cần đọc cấu hình toolchain/CI thực tế.

Nếu muốn tiếp tục hỗ trợ Java17, đặt release17 **và** thay code Java21 bằng code tương thích. Maven không dịch ngược record patterns Java21 sang Java17.

## 13. Gradle: toolchain khác `release`

Trong `build.gradle.kts` (Kotlin DSL, Java plugin):

```kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(21)
}
```

`toolchain` chọn JDK của các tác vụ build phù hợp; `release` giới hạn cú pháp, Java SE/JDK APIs và bytecode target. Có thể dùng JDK21 toolchain để build target17 bằng `release.set(17)` nếu source và các phụ thuộc **thực sự tương thích Java17**.

Không copy nguyên Kotlin DSL vào `build.gradle` dùng Groovy DSL. Với Gradle mới, cần chắc chắn bản Gradle thực tế hỗ trợ Java toolchain đã chọn.

## 14. Preview cần được ghi tách riêng

Pattern `switch` từng là preview Java17–20. Một ví dụ **lịch sử** dành riêng cho JDK20 có thể ghi:

```bash
javac --enable-preview --release 20 Example.java
java --enable-preview Example
```

Lệnh ấy không có nghĩa một JDK mới có thể bật lại tùy ý cú pháp preview của JDK20: preview features được ràng buộc với **release tương ứng**.

Trên Java21, record patterns và pattern `switch` đã final, nên các ví dụ Java21 của bài **không cần `--enable-preview`**. Nhưng nếu project dùng **một preview feature khác của Java21**, phải công bố feature và cờ riêng cho nó.

Ví dụ preview guard `case String s && condition ->` không phải cú pháp guard final Java21. Bản final dùng `case String s when condition ->`.

## 15. CI và runtime phải nhất quán với tài liệu

Một lỗi phổ biến:

- IDE dùng JDK21.
- Compiler chạy target17.
- Docker image dùng JVM17.
- README lại ghi “Java21 only”.
- CI chỉ kiểm thử một bản Java nên tài liệu tự suy ra đã hỗ trợ các bản khác.

Bắt đầu bằng:

```bash
java --version
javac --version
```

Sau đó đối chiếu JVM dùng chạy Maven/Gradle, toolchain, test runner và ứng dụng triển khai.

Tài liệu nên có hai phần riêng: **minimum supported runtime** và **JDKs actually tested**. Không tuyên bố “tested on 21 and 22” nếu chưa có test trên cả hai.

Với một thư viện dùng chung cho nhiều service, tăng baseline từ Java17 lên Java21 có thể là thay đổi phá vỡ khả năng chạy của client cũ dù public API method signatures không thay đổi. Hãy nêu trong release notes và kiểm tra consumer thực tế.

## 16. Khi hỗ trợ nhiều Java baseline

Nếu sản phẩm cần một API cho Java17 và một implementation mới dùng pattern `switch` Java21, có thể:

- Giữ một module/artifact **Java17** với `instanceof` patterns.
- Phát hành module/artifact **Java21+** với record patterns và pattern `switch`.
- Công bố tọa độ artifact, Java runtime minimum và CI compatibility matrix **cho từng bản**.

Multi-Release JAR có thể là lựa chọn nâng cao nhưng không tự giải quyết mọi vấn đề public API, dependency và runtime class loading.

Không thể phát hành một JAR toàn class Java21 rồi khẳng định Java17 sẽ chạy được khi chỉ gọi “phương thức đơn giản”: JVM có thể từ chối classfile major65 trước khi code được thực thi.

## 17. Mẫu release notes khi nâng minimum Java

Ví dụ cho thư viện **giả định** nâng Java17 → Java21 ở version `3.0.0`:

```markdown
## Java requirement changed in 3.0.0

- Old minimum runtime: Java 17
- New minimum runtime: Java 21
- Compile target: `javac --release 21`
- Reason: final record patterns and pattern `switch`
- Preview flags: not required for those features
- Upgrade: update runtime, build toolchains, CI,
  and rerun integration tests for all consumers
```

Đoạn trên chỉ là mẫu cho trường hợp đã xác minh, không phải lịch sử của một thư viện cụ thể. Không tự ghi “last Java17-compatible version” nếu chưa kiểm tra release thực tế.

## 18. Các lỗi tài liệu thường gặp

| Hiểu nhầm | Cách ghi đúng |
| --- | --- |
| “Mọi pattern matching đều cần Java21” | `instanceof` pattern final từ Java16 |
| “Sealed interface cần Java21” | Sealed types final từ Java17 |
| “Pattern `switch` final từ Java17” | Preview17–20, final21 |
| “`@since 21` luôn nghĩa là min JVM21” | `@since` thường theo lịch sử API/library |
| “Build bằng JDK21 nghĩa là mọi artifact chỉ chạy JVM21” | Cần kiểm tra `--release` và output |
| “Chỉ đặt `-target 17` là đủ” | Ưu tiên `--release 17` để hạn chế API |
| “Có `default` nên pattern `switch` nhận null” | `case null` phải được xử lý đúng hợp đồng |
| “Preview flag bật được mọi cú pháp cũ” | Preview gắn với từng release |
| “Major65 vẫn chạy trên Java17” | JVM17 không tải class Java21 major65 |
| “Test JDK21 nghĩa là đã test các JDK cao hơn” | Chỉ công bố những runtime đã kiểm thử |
| “Sửa README là đủ khi tăng Java baseline” | Phải sửa artifact, CI và release notes |

## 19. Checklist trước khi xuất bản tài liệu API

- [ ] Đã xác định feature final mới nhất trong mỗi ví dụ chưa?
- [ ] Đã phân biệt Java16 `instanceof`, Java17 sealed, Java21 record/switch patterns chưa?
- [ ] Có nhầm `switch` expression Java14 với pattern `switch` Java21 không?
- [ ] Các code fence Java hoàn chỉnh có đúng tên file/class và output không?
- [ ] Có gắn nhãn preview/final và Java minimum ngay trước các ví dụ không?
- [ ] Compile target có được ràng buộc bằng `--release` không?
- [ ] JavaDoc `@since` có phản ánh phiên bản phần mềm đúng quy ước không?
- [ ] Runtime minimum có khớp class-file major và dependencies không?
- [ ] Những JDK “tested” có thực sự được CI kiểm chứng không?
- [ ] Maven/Gradle, IDE, Docker image, README và release notes có nhất quán không?
- [ ] Nếu tăng Java minimum, đã công bố thay đổi phá vỡ tương thích và cách nâng cấp chưa?

**Kết luận:** Ghi chú phiên bản Java là một phần **hợp đồng sử dụng API**. Hãy xác định mốc Java theo feature mới nhất (đặc biệt là **16 / 17 / 21** với Pattern Matching), ghi riêng phiên bản thư viện và JDK, rồi chứng minh bằng `--release`, class-file inspection và runtime tests thay vì chỉ ghi một con số trong README.

## Tài liệu chính thức

- [Oracle Java SE 21 — Language Changes Summary](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-summary.html)
- [Oracle Java SE 21 — Language Changes by Release](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html)
- [JEP 361 — Switch Expressions](https://openjdk.org/jeps/361)
- [JEP 394 — Pattern Matching for `instanceof`](https://openjdk.org/jeps/394)
- [JEP 395 — Records](https://openjdk.org/jeps/395)
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for `switch`](https://openjdk.org/jeps/441)
- [Oracle Java 21 `javac` — `--release`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
- [Oracle Javadoc — Documentation Comment Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/javadoc/doc-comment-spec.html)
- [Oracle JVM SE21 — ClassFile Structure](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.1)
- [Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/)
- [Gradle JVM Toolchains](https://docs.gradle.org/current/userguide/toolchains.html)

# Kiểm tra thư viện và công cụ hỗ trợ `record` cùng `text block` trong Java hiện đại

## 1. Vì sao “JDK biên dịch được” chưa đủ chứng minh cả dự án tương thích?

Một dự án Java có thể biên dịch thành công mã nguồn dùng **record** và **text block**, nhưng vẫn gặp lỗi khi chạy test, xử lý JSON, sử dụng annotation processor, tạo proxy, sinh tài liệu, kiểm tra chất lượng code hoặc chạy trong CI. Lý do là **mỗi lớp công cụ hiểu một khía cạnh khác nhau của mã Java**:

- **Compiler (`javac`):** phải nhận ra cú pháp `record`, `"""`, các API và tùy chọn ngôn ngữ.
- **Runtime (JVM):** phải tải được bytecode, nhận diện superclass `java.lang.Record` và thực thi constructor, accessors, string literals.
- **Build tool (Maven/Gradle):** phải dùng JDK đúng và đặt `--release` phù hợp cho source/test.
- **IDE, formatter, linter, source analyzer:** phải có parser/inspection hỗ trợ grammar tương ứng.
- **Annotation processor/code generator:** phải hiểu `ElementKind.RECORD`, record components và cách khai báo accessors/constructor.
- **Thư viện runtime (JSON/XML/ORM/DI/validation):** phải biết cách tạo đối tượng record, bind component names và gọi canonical constructor.
- **Test, mock, coverage, bytecode instrumentation:** phải hiểu class-file và mô hình record khi chạy test/đo coverage.
- **CI/CD và artifact deployment:** phải dùng toolchain/runtime đúng, không chỉ chạy được trên laptop.

**Câu trả lời chính:** kiểm tra tương thích ở **nhiều tầng**, với ít nhất một phép thử thực tế **compile → test → serialize/deserialize → run → inspect output** cho record và text block trên đúng **JDK, build tools, plugin versions, dependencies và runtime** mà dự án sẽ phát hành.

### 1.1. Liên hệ Java 14 và giới hạn kiến thức hiện hành

Java 14 là một cột mốc lịch sử:

| Tính năng | Trạng thái tại Java 14 | Trạng thái ổn định còn dùng |
| --- | --- | --- |
| **Record classes** | Preview theo JEP 359 | Chính thức từ **Java 16** theo JEP 395 |
| **Text blocks** | Preview lần thứ hai theo JEP 368 | Chính thức từ **Java 15** theo JEP 378 |
| **Dùng cả record và text block trong một chương trình** | Không phải cặp tính năng final tại Java 14 | **Java 16+**, ví dụ ưu tiên **Java 17+** |

**Không dùng** `--enable-preview` để bật record/text block trong dự án Java 17+ thông thường. Hai tính năng đó đã là cú pháp chính thức. Dùng lại hướng dẫn “chạy `--enable-preview` cho record/text block” từ thời Java 14 là một khuyến nghị lỗi thời nếu đặt làm quy trình hiện nay.

Bài hướng dẫn cách kiểm tra **API/công cụ còn được hỗ trợ**, sử dụng **Java 17** làm mức tương thích của các ví dụ và kiểm chứng trên JDK 24.0.2. Những ví dụ gắn với Jackson, Maven, Gradle được ghi rõ khi cần thư viện, plugin hoặc cấu hình riêng; không giả vờ rằng chúng đã được chạy nếu môi trường test không có dependencies đó.

### 1.2. Các thuật ngữ quan trọng

- **Build JDK/toolchain:** JDK thực sự được Maven, Gradle hoặc IDE dùng để biên dịch.
- **`--release 17`:** yêu cầu compiler áp dụng language/API/bytecode target Java 17; **không tự chọn JDK cài trên máy**.
- **Runtime JDK:** JDK/JRE thực sự dùng chạy tests hoặc artifact; có thể khác JDK build.
- **Class-file major version:** thông tin trong `.class` cho biết mức bytecode; Java 17 dùng **major version 61**.
- **Library compatibility:** không chỉ nạp được một JAR; phải hoàn thành use case thực tế (ví dụ đọc JSON thành record).
- **Source parser compatibility:** IDE/formatter/processor phải hiểu cấu trúc source code, kể cả text blocks có dấu xuống dòng/escape.

Không coi “chạy `java -version` trên shell” là xác minh mọi thứ. Hệ thống có thể dùng một JDK cho IDE, một JDK cho Maven daemon, một JDK cho Gradle toolchain và một JVM khác trong container chạy sản phẩm.

## 2. Ma trận mức ngôn ngữ — xác nhận được bằng compiler thực tế

Để xác nhận tính năng có thể compile **không cần preview**, thử hai source files tối thiểu.

**Tệp `RecordGate.java`:**

```java
record RecordGate(int value) {}
```

**Tệp `TextBlockGate.java`:**

```java
class TextBlockGate {
    static final String TEXT = """
            hello
            """;
}
```

Trên một JDK hiện đại có thể target các release từ 14 đến 17, chạy lần lượt:

```bash
javac --release 14 RecordGate.java
javac --release 14 TextBlockGate.java

javac --release 15 RecordGate.java
javac --release 15 TextBlockGate.java

javac --release 16 RecordGate.java
javac --release 16 TextBlockGate.java

javac --release 17 RecordGate.java
javac --release 17 TextBlockGate.java
```

**Ma trận đã kiểm chứng với `javac` của JDK 24.0.2:**

| `--release` | `record` | `text block` | Giải thích |
| --- | --- | --- | --- |
| **14** | FAIL | FAIL | Trong Java 14, cả hai còn preview; `--release` hiện đại không biến chúng thành cú pháp final của 14 |
| **15** | FAIL | PASS | Text block đã final, record còn preview |
| **16** | PASS | PASS | Record đã final, text block đã final |
| **17** | PASS | PASS | Cả hai ổn định, không dùng preview flags |

**Đọc kết quả đúng cách:** đây là phép thử **cú pháp final khi biên dịch với `--release` hiện tại**, không phải hướng dẫn phục dựng JDK 14 cũ. Một bản JDK mới hơn có thể không còn hỗ trợ biên dịch về mọi release cũ; nếu `--release 14` bị từ chối vì bản compiler không hỗ trợ target 14, cần ghi nhận đó là lỗi toolchain/target availability, không gán nhầm thành lỗi ngôn ngữ.

**Đối với ứng dụng cần cả hai, chọn `--release >=16`; với thực hành bài này chọn `17`.** Nhưng version của **mọi runtime chạy code** cũng cần đủ mới; compile thành bytecode Java 17 không có nghĩa sẽ chạy được trên Java 11.

### 2.1. Xác nhận class-file và metadata sau compile

Ví dụ sau khi biên dịch chương trình mẫu ở mục 4:

```bash
javac --release 17 -encoding UTF-8 RecordTextBlockSmoke.java
javap -v 'RecordTextBlockSmoke$Task.class'
```

Dấu nháy đơn quanh tên file có ký tự `$` giúp **shell kiểu POSIX** không mở rộng biến môi trường. Trên PowerShell cũng có thể dùng single quotes. Đây là lệnh kiểm tra; đường dẫn class file cần đổi nếu bạn dùng `-d`.

Ở lần biên dịch đã thử, `javap -v` cho thấy:

```text
major version: 61
```

Record class có superclass `java.lang.Record` và record-component metadata tương ứng. Với tool đọc bytecode như coverage agent hoặc serializer, **chỉ cần gặp class-file mới hơn mức hỗ trợ** là có thể lỗi trước khi application code chạy. Vì thế hãy kiểm tra **tool đọc class file** riêng với JDK dùng chạy.

### 2.2. Khi thay đổi compatibility baseline

Nếu thư viện của bạn được phân phối cho sản phẩm chạy trên Java 11, bạn **không thể** đưa record/text block final vào source target 11 rồi kỳ vọng `--release 11` compile. Cần quyết định rõ:

1. **Nâng minimum runtime** của thư viện/sản phẩm lên phiên bản có tính năng.
2. Giữ source API/bytecode cũ nếu cần hỗ trợ consumers Java cũ.
3. Nếu có nhiều artifact/variants, lập kế hoạch riêng với thử nghiệm class loader, module path, publishing metadata và CI matrix.
4. Không dùng việc “compiler mới vẫn đọc được code” để che giấu sự khác biệt giữa compile target và runtime của khách hàng.

`--release` kiểm tra API Java SE của một version được hỗ trợ, **không tự xác nhận** tất cả third-party dependencies có tương thích với runtime đó hay không.

## 3. Đặc điểm record mà thư viện phải hiểu

Một record:

```java
public record User(String name, int age) {}
```

là một **loại class đặc biệt**, có các record components `name` và `age`. Java tự cung cấp:

- Các component fields `private final`, accessors `name()`, `age()`.
- Canonical constructor nhận đủ components theo thứ tự khai báo.
- `equals`, `hashCode`, `toString` dựa trên components.
- Superclass `java.lang.Record`; record class ngầm **final** nên không được kế thừa bằng subclass.
- Metadata để reflection nhận biết `Class.isRecord()` và `Class.getRecordComponents()`.

**Lưu ý tương thích lớn:** accessor do record tạo ra là **`name()`**, không tự động là **`getName()`** kiểu JavaBeans. Một thư viện chỉ tìm `getX()/setX()` có thể không nhận được `name` hoặc không thể gán vào final fields.

### 3.1. Canonical constructor và ràng buộc dữ liệu

Record cho phép **compact constructor** để validate hoặc chuẩn hóa tham số trước khi Java gán vào fields:

```java
public record Task(String label, int retries) {
    public Task {
        label = java.util.Objects.requireNonNull(label).strip();
        if (label.isEmpty() || retries < 0) {
            throw new IllegalArgumentException("invalid task");
        }
    }
}
```

Khi một thư viện deserialize JSON hoặc gắn kết dữ liệu vào `Task`, nó cần gọi **canonical constructor** đúng cách. Nếu dữ liệu không qua constructor hoặc truyền sai tên/kiểu/giá trị, behavior sẽ khác hợp đồng record.

Cần kiểm thử:

- Tên JSON/XML fields có khớp components không?
- Object một component có được hiểu là **properties-based** hay delegating?
- Giá trị thiếu có thành `null`/zero? Constructor có chấp nhận không?
- Validation trong compact constructor có được thực thi và lỗi được hiển thị có ý nghĩa?
- Library có bind annotations đặt trên record component sang constructor parameters, fields hoặc accessors như mong muốn không?
- Quy tắc naming strategy (snake_case/camelCase), generics, nested records và collections hoạt động như thế nào?

### 3.2. Record **shallowly immutable**, không tự deep immutable

`private final` ngăn đổi tham chiếu field sau khi tạo record, nhưng **không tự sao chép** danh sách/mảng hoặc nested objects. Ví dụ `record Box(List<String> items) {}` vẫn giữ reference tới một `List` có thể bị chỉnh ngoài record.

Nếu contract cần collection không bị mutate, hãy dùng `List.copyOf(...)` trong canonical/compact constructor và kiểm thử sau khi sửa list gốc. Ngay cả `List.copyOf` cũng chỉ sao chép **structure** của list và giữ reference tới elements; nếu element mutable thì không tự biến thành deep immutable.

Với mảng, `record Bytes(byte[] value) {}` không có value equality của nội dung array theo cách bạn có thể mong đợi: phương thức `equals` record dùng semantics của array reference. Nếu muốn bất biến sâu/value equality cho bytes, cần thiết kế wrapper và `equals/hashCode` thích hợp hoặc thay đổi API, không mặc định dùng record để giải quyết.

### 3.3. Các framework tạo proxy/subclass

Một số ORM/DI/proxy tooling mong muốn **class không final**, constructor không tham số và setters để dựng/hydrate entity. Record không thích hợp làm **drop-in replacement cho mọi JPA entity mutable/proxy**.

Tuy nhiên, record thường thích hợp làm **DTO, API response, projection, event hoặc immutable configuration values**, **nếu framework/version cụ thể có hỗ trợ**. Một vài thư viện có thể dùng constructor-based mapping hoặc công cụ tạo proxy final-class riêng; đừng kết luận mọi framework đều không hỗ trợ record. Hãy viết integration test **trên đúng phiên bản framework** và đường code được sử dụng.

### 3.4. Reflection và annotation processor

Trong Java 17+, API quan trọng gồm:

- `Class.isRecord()`.
- `Class.getRecordComponents()`.
- `java.lang.reflect.RecordComponent`: `getName()`, `getType()`, `getAccessor()`, annotations.
- `javax.lang.model.element.ElementKind.RECORD` cho compile-time processors.
- `TypeElement.getRecordComponents()` để lấy components ở mô hình annotation processing.
- `javax.lang.model.element.RecordComponentElement`.
- `java.lang.annotation.ElementType.RECORD_COMPONENT` khi khai báo annotation dành cho component.

Một annotation trên record component có thể được **propagate** tới field, accessor, canonical constructor parameter tùy `@Target` của annotation. Không giả định scanner chỉ quét fields hoặc chỉ quét getters là đủ.

**Một tool hỗ trợ class-file của Java 17 chưa chắc đã có parser record/text-block trong source.** Reflection runtime và annotation processing tại compile time là hai tuyến kiểm tra khác nhau.

## 4. Chương trình Java 17+ chạy độc lập: record + text block + reflection

Để test cú pháp/compiler/runtime mà không cần tải thư viện bên ngoài, có thể dùng một chương trình thuần JDK. Nó gồm:

- Record với **compact constructor** chuẩn hóa input.
- Record với `List.copyOf` minh họa không bị sửa theo list gốc.
- Text block dùng `String.formatted`.
- Escape `\s` giữ một space cuối dòng và `\` dùng **line continuation**.
- Reflection đọc record-component names.
- Assertion dùng so sánh chuỗi **chính xác**, không chỉ kiểm tra code compile.

**Tệp `RecordTextBlockSmoke.java`:**

```java
import java.lang.reflect.RecordComponent;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class RecordTextBlockSmoke {
    public record Task(String label, int retries) {
        public Task {
            label = Objects.requireNonNull(label, "label").strip();
            if (label.isEmpty() || retries < 0) {
                throw new IllegalArgumentException("invalid task");
            }
        }
    }

    public record Tags(List<String> values) {
        public Tags {
            values = List.copyOf(values);
        }
    }

    public static void main(String[] args) {
        Task task = new Task("  compile  ", 2);

        String report = """
                task=%s
                retries=%d
                """.formatted(task.label(), task.retries());

        String preserved = """
                first\s
                second\
                joined
                """;

        String[] components = Arrays.stream(Task.class.getRecordComponents())
                .map(RecordComponent::getName)
                .toArray(String[]::new);

        ArrayList<String> input = new ArrayList<>(List.of("core"));
        Tags snapshot = new Tags(input);
        input.add("later");

        System.out.print(report);
        System.out.println("record=" + Task.class.isRecord());
        System.out.println("components=" + String.join(",", components));
        System.out.println("valueEquals=" +
                task.equals(new Task("compile", 2)));
        System.out.println("snapshotSize=" + snapshot.values().size());
        System.out.println("exactWhitespace=" +
                preserved.equals("first \nsecondjoined\n"));
        System.out.println("reportLines=" + report.lines().count());
        System.out.println("reportHasFinalLf=" + report.endsWith("\n"));

        if (!Task.class.isRecord() ||
                !Arrays.equals(components, new String[]{"label", "retries"}) ||
                !preserved.equals("first \nsecondjoined\n") ||
                snapshot.values().size() != 1) {
            throw new AssertionError("record/text block contract failed");
        }
    }
}
```

**Biên dịch và chạy:**

```bash
javac --release 17 -encoding UTF-8 RecordTextBlockSmoke.java
java RecordTextBlockSmoke
```

**Stdout chính xác đã kiểm chứng trên JDK 24.0.2:**

```text
task=compile
retries=2
record=true
components=label,retries
valueEquals=true
snapshotSize=1
exactWhitespace=true
reportLines=2
reportHasFinalLf=true
```

Bài test không phụ thuộc thời gian/tải máy. Nếu test sai semantics về record hoặc text block, chương trình chủ động ném `AssertionError`.

### 4.1. Giải thích từng kiểm tra

1. `new Task("  compile  ",2)` đi qua compact constructor, chuẩn hóa `label` bằng `strip()` và validate `retries`.
2. Text block `report` bao gồm **LF cuối** theo vị trí closing delimiter; `System.out.print` in đúng hai dòng rồi các `println` tiếp tục phía sau.
3. `.formatted(...)` là API Java hiện đại (Java 15+) để format `String`; formatter không cần hiểu dấu `"""` trong source vì chuỗi đã được compiler xử lý.
4. `Task.class.isRecord()` xác nhận runtime reflection nhận dạng record.
5. `getRecordComponents()` xác nhận tên `label,retries` đúng như header; library xử lý record metadata cần biết thông tin này.
6. `task.equals(new Task("compile",2))` trả true vì dữ liệu đã được chuẩn hóa và record có value-like equality của các components ở đây.
7. `Tags` dùng `List.copyOf`; sửa `input` bên ngoài sau khi tạo `Tags` không làm đổi `snapshot.values().size()`.
8. `\s` trong text block tạo **một khoảng trắng không bị strip** ở cuối dòng `first`.
9. Ký tự `\` đặt ở cuối dòng source của `second` là **line-continuation escape**, loại bỏ newline giữa `second` và `joined`; chuỗi đúng là `"first \nsecondjoined\n"`.
10. Chương trình so sánh chính xác bằng `String.equals`; đây là phép thử **nội dung bytes/characters của string**, không chỉ “nhìn bằng mắt” ở console.

### 4.2. Nếu chạy cùng source ở Java thấp hơn

Khi target nhỏ hơn Java 16, `record` chưa là cú pháp final. Khi target Java 14, `text block` cũng chưa là cú pháp final. Do đó, mục tiêu của demo là **xác nhận một toolchain hiện đại, không dùng preview**, không phải viết cách bật tính năng preview thời Java 14.

### 4.3. Cần biên dịch **mọi source và test source** ở đúng target

Đừng chỉ compile `src/main/java` bằng `--release 17` rồi để test source dùng ngôn ngữ/API của một JDK mới hơn ngoài ý muốn. Một dự án vẫn có thể chọn test source mới hơn để phục vụ CI, nhưng phải **công bố rõ** rằng runtime chạy test khác minimum runtime của thư viện sản phẩm. Với bài kiểm thử tương thích này, nên thống nhất ít nhất một pipeline **compile+test+run** thật trên Java 17.

## 5. Text blocks: những kiểm tra mà formatter và test phải vượt qua

Text block là **`String`** được viết bằng ba dấu nháy kép mở/đóng và newline ở đầu body. Compiler chuẩn hóa line terminators thành LF, xử lý **incidental indentation**, rồi diễn giải escapes như `\s` và **line continuation**. Điều này dễ ảnh hưởng output của JSON, SQL, CSV, template và golden-file tests.

### 5.1. Cú pháp và nội dung cuối dòng

Ví dụ:

```java
String sql = """
        SELECT id, title
        FROM jobs
        WHERE status = ?
        """;
```

Chuỗi nhận được:

```text
SELECT id, title
FROM jobs
WHERE status = ?
```

**Có ký tự LF cuối** sau dấu `?` nếu closing delimiter ở dòng riêng như trên. `System.out.println(sql)` có thể tạo thêm một newline ngoài chuỗi; khi so sánh expected output cần phân biệt **chuỗi** với cách console in chuỗi.

Nếu thư viện cần không có newline cuối, có thể đặt closing delimiter cùng dòng dữ liệu theo cú pháp phù hợp hoặc dùng `stripTrailing()` khi **đúng ý nghĩa nghiệp vụ**. Nhưng `stripTrailing()` sẽ bỏ cả whitespace cuối khác, không chỉ LF — hãy test chính xác thay vì dùng cho mọi JSON/SQL theo thói quen.

### 5.2. Incidental indentation và tab/space

Ví dụ:

```java
String body = """
        alpha
          beta
        """;
```

Đây là **snippet** với hai dòng dữ liệu; compiler loại indent ngẫu nhiên theo thuật toán trong Java Language Specification. Kết quả phụ thuộc vị trí closing delimiter và indent của các dòng. Một IDE formatter có thể thay indentation ở source; đôi khi điều đó **thay đổi nội dung chuỗi** nếu làm khác mức common indent.

Để bảo vệ:

- Test `body.equals(expected)` hoặc kiểm tra bytes UTF-8/golden file khi whitespace quan trọng.
- Giữ formatter có hỗ trợ text-block grammar và quy định về indent.
- Không “chỉnh đẹp” text block có cấu trúc fixed-width/indent/Markdown mà chưa chạy test.
- Nếu cần space cuối, dùng `\s` rõ ràng thay vì để trailing spaces thô dễ bị editor xóa.
- Nếu muốn ngắt dòng hoặc nối dòng cụ thể, dùng escape đúng và test các `\n`.

### 5.3. Text block không phải JSON parser/SQL binder

`String` được tạo từ text block vẫn chỉ là **chuỗi ký tự**. Nó **không tự đảm bảo** nội dung JSON hợp lệ, chống SQL injection hoặc chống template injection.

Sai về bảo mật:

```java
String query = """
        SELECT * FROM users WHERE name = '%s'
        """.formatted(untrustedName);
```

Đây là **snippet cố ý không an toàn** nếu `untrustedName` do người dùng cung cấp. Đúng hơn là dùng `PreparedStatement` với placeholder `?` và bind value qua driver; tương tự, với JSON dynamic phải dùng serializer/JSON generator để escape dữ liệu, không lắp `"name":"%s"` bằng tay rồi tưởng text block tự escape JSON.

### 5.4. Unicode, charset và newline qua hệ điều hành

Trong runtime, Java `String` chứa các ký tự; khi ghi file hoặc gửi network cần xác định **encoding** (thường UTF-8), newline protocol (LF hay CRLF) và API ghi.

Không giả định vì source file được biên dịch trên Windows thì text block tự thành CRLF. Java text-block processing chuẩn hóa line terminators theo specification. Nếu output protocol yêu cầu CRLF, hãy **chuyển đổi một cách có chủ đích khi serialize**, test bytes chính xác và tránh chuyển đổi hai lần.

Với SQL multi-line, nhiều JDBC drivers chấp nhận LF; với hệ thống khác như CSV/golden file, newline chính xác có thể là một phần contract.

### 5.5. Tools nào cần hiểu source và tools nào chỉ thấy String?

| Thành phần | Nhìn thấy `"""` trong source? | Kiểm tra cần làm |
| --- | --- | --- |
| `javac` | Có | Parse/compile đúng grammar, version |
| IDE language parser | Có | Không báo lỗi giả, syntax highlight/refactor đúng |
| Formatter | Có | Không phá whitespace/escape và nội dung cuối |
| Static analysis/source scanner | Có | Nhận diện text blocks, không hiểu nhầm content là source |
| Annotation processor | Chủ yếu nhận mô hình compiler, có thể thấy giá trị constant | Tạo mã/metadata đúng với annotations và element kinds |
| Java runtime `String` | Không, chỉ thấy chuỗi sau compile | Nội dung LF/indent/escape đúng |
| JSON/SQL/XML library | Không, nhận chuỗi | Parse/bind đúng nội dung, escaping/encoding |
| Golden-file/snapshot tests | Nhận output | Bảo toàn whitespace qua OS/charset |

Nhiều lỗi xảy ra **không phải vì Java không hỗ trợ text block**, mà vì formatter, parser hoặc test snapshot quá cũ; vì vậy cần xác nhận **bản công cụ và kết quả chạy thực tế**.

## 6. Kiểm tra khả năng hiểu record của JavaBeans tools và reflection

Một thư viện introspection kiểu JavaBeans có thể chỉ tìm methods dạng `getName()` hoặc `isActive()`. Record tạo accessors `name()`, `active()`, nên phải kiểm tra thư viện có **nhận record components** hay không.

**Tệp `RecordBeanProbe.java` — Java 17+:**

```java
import java.beans.Introspector;
import java.beans.PropertyDescriptor;
import java.util.Arrays;

public class RecordBeanProbe {
    public record User(String name, int age) {}

    public static void main(String[] args) throws Exception {
        String[] beanProperties = Arrays.stream(
                Introspector.getBeanInfo(User.class).getPropertyDescriptors())
                .map(PropertyDescriptor::getName)
                .sorted()
                .toArray(String[]::new);

        System.out.println("recordAccessors=" +
                User.class.getRecordComponents().length);
        System.out.println("javaBeansNames=" + String.join(",", beanProperties));
        System.out.println("hasNameBeanProperty=" +
                Arrays.asList(beanProperties).contains("name"));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 RecordBeanProbe.java
java RecordBeanProbe
```

**Kết quả đã thử trên JDK 24.0.2:**

```text
recordAccessors=2
javaBeansNames=class
hasNameBeanProperty=false
```

Vì thế, **trên implementation đã thử**, `Introspector` theo quy tắc JavaBeans không trả `name` là một JavaBean property, trong khi reflection record metadata có đủ hai components.

**Đừng tổng quát quá mức:** đây là phép thử behavior của **`java.beans.Introspector` ở JDK cụ thể**, không phải kết luận rằng **Jackson, Spring hoặc mọi thư viện** sẽ thất bại với record. Các framework hiện đại có thể có record introspector riêng. Tự kiểm tra **thư viện đích** bằng một round-trip hoặc binding test.

### 6.1. Phân biệt “không có setter” với “không deserialize được”

Một record không có setter thông thường, nhưng một JSON library hỗ trợ record có thể đọc tên components và gọi **canonical constructor**. Do đó:

- **Không** yêu cầu thư viện bắt buộc phải có setter nếu nó đã hỗ trợ constructor binding.
- **Không** tin rằng library “hỗ trợ immutable objects” đồng nghĩa nó đã kiểm thử **record components**.
- **Không** đánh giá “thư viện tương thích” chỉ vì có thể **serialize**; cần kiểm tra cả **deserialize** và validation.
- Khi có annotations trên components, xác minh chúng được thư viện nhận đúng vị trí.
- Kiểm thử nested records, collections, generic components, nullability và một-component records.

## 7. Annotation processors và code generators

Annotation processors hoạt động tại **compile time** qua `javax.lang.model`; chúng không tự dùng reflection runtime `Class.getRecordComponents()`. Nếu processor bị giới hạn ở `ElementKind.CLASS`, nó có thể bỏ qua records; nếu chỉ đọc enclosed fields/getters, nó có thể bỏ qua component metadata hoặc xử lý annotation sai.

Java 17 có:

```java
ElementKind.RECORD
((TypeElement) element).getRecordComponents()
```

Đây là **snippet** dùng trong processor, chỉ hợp lệ khi có imports và `element` đúng kiểu, không phải chương trình tự chạy.

### 7.1. Test một processor tối thiểu trên Java 17

**Tệp `RecordAwareProcessor.java`:**

```java
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.TypeElement;

@SupportedAnnotationTypes("*")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class RecordAwareProcessor extends AbstractProcessor {
    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment round) {
        if (round.processingOver()) return false;
        for (Element element : round.getRootElements()) {
            if (element.getKind() == ElementKind.RECORD) {
                TypeElement record = (TypeElement) element;
                System.out.println("recordSeen=" + record.getSimpleName() +
                                   ",components=" + record.getRecordComponents().size());
            }
        }
        return false;
    }
}
```

Tạo `RecordGate.java` như ở mục 2 trong cùng thư mục, chạy:

```bash
javac --release 17 -encoding UTF-8 RecordAwareProcessor.java
javac --release 17 -encoding UTF-8 -cp . -processor RecordAwareProcessor RecordGate.java
```

**Một dòng in được trên JDK 24.0.2 sau khi processor chạy thành công:**

```text
recordSeen=RecordGate,components=1
```

Đây là **demo minh họa compiler model**. Processor production nên dùng `Messager` thay vì `System.out` để báo diagnostics, định nghĩa rõ supported annotation types/source version và build output. Nếu toolchain nâng quá Java 17 và processor tự giới hạn `SupportedSourceVersion.RELEASE_17`, compiler có thể cảnh báo; cần cập nhật/test processor theo release mới khi hỗ trợ.

### 7.2. Các rủi ro với Lombok, MapStruct, validators và code generation

- **Lombok:** record đã có canonical constructor, accessors, equals/hashCode/toString; nhiều annotation vốn dùng sinh getter/setter cho class truyền thống **không phù hợp hoặc không cần thiết**. Kiểm thử annotation thật sự được thư viện hỗ trợ thay vì áp các annotation trên class cũ theo thói quen.
- **MapStruct/mapper generators:** cần nhận source/target record properties, mapping tới canonical constructor và null/default strategy. Test generated code **compile và chạy**, không chỉ thấy processor exit code 0.
- **Validation annotations:** đặt `@NotNull`, `@Size`, v.v. lên component cần kiểm tra vị trí annotation được thư viện nhận; compact constructor có thể kiểm tra invariants độc lập với framework.
- **ORM entity tools:** nếu framework cần proxy subclass/no-arg constructor, records final và immutable không thể coi như entity truyền thống.
- **OpenAPI/schema generators:** field/component names và required/nullability có thể khác JavaBeans mapping; test schema snapshot và consumer compatibility.

Nếu một thư viện chỉ công bố “Java 17 compatible”, chưa chắc nó đã có semantics đúng cho **record components**. Cần có **integration test đặc thù** chứ không chỉ test dependency resolve.

## 8. JSON, Jackson và thư viện binding: test use case thật

### 8.1. Phiên bản thư viện quan trọng hơn số phiên bản JDK

Jackson hỗ trợ Java records từ dòng **2.12** (mốc lịch sử về tính năng). Tuy nhiên, **không khuyên chốt dùng Jackson 2.12 cũ cho sản phẩm mới**: hãy chọn **phiên bản vẫn được duy trì/vá**, tương thích framework/BOM và JDK mục tiêu.

Cũng cần phân biệt hai nhánh API:

| Thư viện | Package mapper | Kiểm tra tương thích |
| --- | --- | --- |
| **Jackson 2.x** | `com.fasterxml.jackson.databind.ObjectMapper` | Record introspection, canonical constructor, Jackson modules/BOM đang hỗ trợ |
| **Jackson 3.x** | `tools.jackson.databind.ObjectMapper` và `tools.jackson.databind.json.JsonMapper` | Java 17 baseline, package migration, defaults/removed deprecated APIs |
| Annotation của Jackson | Nhiều annotations vẫn ở `com.fasterxml.jackson.annotation` trong Jackson 3.x | Không đổi imports annotation tùy tiện |
| Thư viện JSON khác | Package riêng | Không suy ra hỗ trợ record từ Jackson |

**Cảnh báo migration:** Jackson 3 thay groupId và Java packages lõi sang `tools.jackson`, giữ một số annotation APIs trong `com.fasterxml.jackson`. Nếu đang dùng Spring/framework/BOM quản lý Jackson, không thêm dependency 2.x và 3.x pha trộn tùy tiện. Phải xác định branch thực sự chạy, các modules và transitive dependencies.

### 8.2. Integration test gợi ý trên Jackson 3.x

Ví dụ sau là **snippet cần Jackson 3.x databind dependency**, không phải Java SE standalone:

```java
import tools.jackson.databind.json.JsonMapper;

record JobDto(String label, int retries) {}

var mapper = JsonMapper.builder().build();
var input = new JobDto("compile", 2);
String json = mapper.writeValueAsString(input);
JobDto restored = mapper.readValue(json, JobDto.class);

if (!input.equals(restored)) {
    throw new AssertionError("record JSON round-trip mismatch");
}
```

**Giới hạn cú pháp:** các dòng `var mapper` phải được đặt trong method, `JobDto` được đặt trong một file/class đúng phạm vi, và dependency Jackson 3.x phải có trên classpath/module path. Đây **không phải** source file độc lập hay stdout đã kiểm chứng trong môi trường chỉ có JDK. Khi đưa vào test JUnit, hãy sử dụng code đầy đủ và exception handling theo API được dependency quản lý.

Đối với Jackson 2.x, dùng namespace `com.fasterxml.jackson.databind` và API tương ứng, **không** copy import Jackson 3 vào dự án vẫn dùng nhánh 2.

**Các trường hợp tối thiểu cần test:** serialize → deserialize → equality, một-component record, renamed field annotation, compact constructor validation, thiếu/extra field, `null`, nested record, `List<T>`, ngày giờ với modules cần thiết và dữ liệu Unicode/multiline.

### 8.3. Text block + JSON library

Tách hai công việc:

1. Text block tạo **chuỗi input** JSON hoặc expected snapshot.
2. Jackson/JSON parser xác nhận **JSON hợp lệ và mapping đúng**.

Ví dụ một JSON test fixture:

```java
String json = """
        {
          "label": "compile",
          "retries": 2
        }
        """;
```

Đây là **snippet chuỗi hằng** trong method. Nó không test parser nếu bạn không thực sự gọi parser. Có thể dùng `json` làm input của integration test Jackson để so sánh với `new JobDto("compile",2)`.

Khi cần JSON với dữ liệu người dùng, hãy dùng `mapper.writeValueAsString(...)` hoặc JSON generator; **không** dùng `formatted` để chèn trực tiếp untrusted values vào JSON vì text blocks không tự escape ký tự `"`, newline hoặc backslash theo JSON rules.

### 8.4. Record serialization khác JavaBean serialization

Ngay cả khi record là Java class, behavior **Java Object Serialization**, JSON serialization và ORM mapping là **những cơ chế khác nhau**. Với Java Object Serialization, record có các quy tắc riêng về canonical constructor và serializable components; không suy ra behavior từ `readObject` customization của class truyền thống.

Trong hệ thống mới, khi có nhiều phiên bản service/client, ưu tiên **format dữ liệu có schema và versioning rõ**; không coi Java default serialization là một hợp đồng chia sẻ dữ liệu tự động an toàn giữa các phiên bản.

## 9. Maven: kiểm tra JDK build, compiler release và plugins

### 9.1. Khai báo mục tiêu Java 17 bằng Maven Compiler Plugin

Ví dụ `pom.xml` **tối thiểu cho Maven 3 với compiler plugin được pin**:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>record-textblock-check</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.16.0</version>
      </plugin>
    </plugins>
  </build>
</project>
```

`3.16.0` là phiên bản **Maven Compiler Plugin 3.x được công bố vào năm 2026** trong tài liệu chính thức; production phải kiểm tra compatibility của toàn bộ Maven lifecycle/plugins với Maven version đã dùng. POM minh họa chỉ cấu hình Java compile, **chưa gồm JUnit dependencies/tests hoặc runtime deployment**.

Đặt file Java thuộc project:

```text
record-textblock-check/
  pom.xml
  src/
    main/
      java/
        RecordTextBlockSmoke.java
```

Kiểm tra:

```bash
mvn --version
mvn clean compile
mvn test
```

`mvn test` chỉ thực sự chạy những tests đã được định nghĩa và dependency/test plugin đã cấu hình; không được coi lệnh trả 0 **với 0 tests** là bằng chứng JUnit/JSON/formatter tương thích. Ghi lại số tests executed và bản plugin Surefire/Failsafe đang chạy.

### 9.2. `--release` không thay việc chọn JDK thực

`<maven.compiler.release>17</maven.compiler.release>` điều khiển target compiler. Nó **không cài hoặc chọn tự động một JDK 17**; Maven có thể đang chạy JDK khác.

Nếu build cần dùng đúng JDK (ví dụ processor/native tool khác nhau), sử dụng **Maven Toolchains** để chọn JDK theo dự án. JDK toolchain có thể khác JDK đang chạy Maven. Kiểm tra đúng `mvn --version`, toolchain config, compiler plugin logs và Java executable thực sự dùng cho tests.

**Không** giữ một JDK developer mới nhất rồi ngầm hiểu CI/test-runtime giống hệt. Mục tiêu là có ít nhất một lane chạy được bằng **minimum supported runtime**.

### 9.3. Plugin test, formatter, linter, coverage

Trong Maven, các plugin như Surefire/Failsafe, Checkstyle/Spotless/formatter, SpotBugs, annotation processors và JaCoCo có **parser/ASM/test-engine versions riêng**. Khi bật record/text block:

- Xác minh plugin tương thích với **class-file target 61** cho Java 17.
- Kiểm tra formatter không phá text block indentation, `\s` và line continuation.
- Kiểm tra annotation processor nhận record elements.
- Kiểm tra JaCoCo/coverage có thể instrument record-generated methods mà không `Unsupported class file major version`.
- Nếu plugin chỉ có parser cũ, nâng tới một bản **đang được hỗ trợ** theo release notes chính thức, đừng bỏ quality gate.
- Chạy `mvn clean verify` với tests thực sự, record assertions và golden-file checks, không chỉ `mvn compile`.

**Mốc kiểm chứng hiện hành:** JaCoCo **0.8.16** (phát hành 24/10/2026) công bố hỗ trợ Java 27. Với dự án target 17, vẫn cần kiểm tra runtime instrumentation và chính plugin/bản mà CI dùng; “có hỗ trợ Java 27” không thay kiểm thử mọi project configuration.

## 10. Gradle: toolchain đúng + release đúng

Với Gradle Kotlin DSL, đoạn `build.gradle.kts` đơn giản:

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
```

Đây là **cấu hình build snippet**, không phải chương trình Java. Nó sử dụng Gradle Java plugin và phiên bản Gradle có hỗ trợ Java toolchains. Kiểm tra Gradle Wrapper của dự án và **compatibility matrix giữa Gradle version, JVM chạy Gradle và JDK compiler target**.

Hai dòng cấu hình giải quyết hai trách nhiệm khác nhau:

- `toolchain.languageVersion=17` chọn công cụ Java 17 cho compile/test/javaDoc theo cấu hình plugin.
- `options.release=17` yêu cầu compiler dùng language/API/classfile target 17, giảm rủi ro vô tình gọi API Java mới hơn mức target.

Gradle docs khuyên kết hợp **toolchain và `--release`** nếu muốn kiểm soát chính xác compatibility. Không chỉ khai báo `sourceCompatibility=17` rồi nghĩ mọi tests, annotation processors và runtime đều đã được pin.

Kiểm tra trong project có Gradle wrapper:

```bash
./gradlew --version
./gradlew clean test
./gradlew check
```

Trên Windows PowerShell/cmd, dùng script wrapper thích hợp của dự án (thường `gradlew.bat`). `clean test` chỉ có ý nghĩa nếu tests thật đã được khai báo. Plugin formatter/coverage, test JVM, codegen processor và dependencies vẫn phải được cập nhật phù hợp.

### 10.1. Tránh mismatch IDE ↔ Gradle daemon

IDE có thể mở source với language level 17 nhưng Gradle daemon sử dụng JDK khác hoặc toolchain chưa được tải/cấp. Khi gặp lỗi:

1. Xem IDE project SDK/source level.
2. Xem JDK dùng chạy Gradle/Maven và build tool version.
3. Xem configured Java toolchain và `--release`.
4. Xem compiler output của CI.
5. Chạy một lệnh build từ **terminal ngoài IDE** để phân biệt lỗi editor với lỗi thực tế.

Không vô hiệu hóa `record` inspection hoặc formatter tùy tiện chỉ để IDE ngừng báo đỏ; sửa project settings/plugin parser.

## 11. IDE, formatter, test runner và source analyzers

Những lớp công cụ cần kiểm tra tối thiểu:

| Loại tool | Dấu hiệu không tương thích | Phép thử nên chạy |
| --- | --- | --- |
| IDE (IntelliJ/Eclipse/VS Code Java language server) | `record`/`"""` bị đánh dấu syntax error giả | Tạo file mẫu, compare IDE compile vs CLI compile |
| Formatter/Spotless | Thay indent, trailing spaces, `\s` hoặc line continuation | Compare chuỗi `String` sau format với golden test |
| Linter/Checkstyle/source parser | Parser unexpected token ở `record`/`"""` | Chạy lint trên source thật và class record |
| Annotation processor (MapStruct, Lombok...) | Bỏ qua `ElementKind.RECORD`, generated code sai getter | Bật processor, compile generated sources, assert mapping |
| Runtime serializer (Jackson...) | `InvalidDefinitionException`, thiếu properties, lỗi canonical constructor | JSON round-trip + invalid inputs |
| Test runner (JUnit) | 0 tests chạy, unsupported JVM class file | Chạy tests thật trên minimum runtime |
| Coverage (JaCoCo) | Unsupported class-file version hoặc instrumentation error | Chạy coverage verify, kiểm tra report |
| JVM runtime | `UnsupportedClassVersionError` hoặc `NoClassDefFoundError` cho `Record` | Khởi động app bằng runtime thực |
| API/ORM integration | Record final/proxy/no-arg constructor mismatch | Integration test transaction/mapping thực tế |
| CI pipeline | Local PASS nhưng CI FAIL do JDK/formatter khác | Ghi build environment và chạy cùng wrapper/toolchain |

**Không đánh giá khả năng IDE chỉ bằng việc cú pháp được tô màu.** Editor có thể nhận grammar nhưng test runner/annotation processor/formatter tích hợp vẫn dùng version khác.

### 11.1. Giá trị của format/compile repeatability

Một test hữu ích để xác nhận formatter không làm hỏng text block:

1. Compile và chạy `RecordTextBlockSmoke`; lưu stdout và kết quả `exactWhitespace=true`.
2. Chạy formatter được dự án cấu hình trên source này.
3. Compile và chạy lại cùng compiler target 17.
4. Assert chuỗi `"first \nsecondjoined\n"`, report content và LF cuối vẫn giống.
5. Nếu khác, kiểm tra formatter settings/parser/version và diff **đặc biệt ở text blocks**, không chỉ diff code nhìn bằng mắt.

Với code chứa JSON/SQL/HTML, so sánh thêm **parser result** hoặc golden bytes để không bỏ sót trailing newline, indentation hoặc escape.

### 11.2. Test runner và coverage phải có test thực sự

Dùng JUnit Jupiter hoặc test framework hiện hành với dependency versions được quản lý bởi build tool/BOM. Những assertions quan trọng:

- Record constructor reject invalid fields.
- Accessors và equality đúng.
- Defensive copying hoạt động với mutable inputs.
- JSON/XML round-trip.
- Text block string equals expected literal.
- Dữ liệu Unicode, quotes, trailing spaces và newline.
- Generated code từ annotation processor compile được.
- Coverage tool không lỗi khi instrument record.

**Đừng dựa duy nhất vào coverage percentage:** record có synthetic/generated members và branching do compiler; coverage tool có thể lọc hoặc trình bày khác qua phiên bản. Đọc báo cáo và xác nhận các **hành vi** đang được test.

## 12. Ma trận kiểm thử tương thích nên dùng trong CI

Một bản kế hoạch CI có thể chia thành các lane:

| Lane | JDK build/runtime | Cần đạt |
| --- | --- | --- |
| **Minimum supported JDK** | Java 17 | Compile/run tests, record+textblock smoke, serializers |
| **JDK dùng phát hành** | Vendor/version production đã duyệt | Build, integration tests, generated code, package smoke |
| **JDK mới hơn trong phạm vi hỗ trợ** | JDK đã kiểm thử | Phát hiện regression của dependencies/frameworks |
| **Formatter/linter/annotation processors** | Cùng versions đã pin | Source parser, generated code, format golden tests |
| **Jackson 2.x hoặc 3.x branch** | Branch thực tế đang dùng | Serial + deserial + annotation + constructor validation |
| **Coverage/static analysis** | Tool version phù hợp bytecode | Không crash, test report đáng tin |
| **Deployment** | Container/VM runtime thật | Khởi động, feature behavior, serializer+API integration |

Không cần chạy mọi tổ hợp của mọi JDK/dependency nếu số tổ hợp quá lớn, nhưng phải xác định **minimum-runtime lane**, **production lane** và những điểm có rủi ro cao khi đổi phiên bản. Với thư viện phân phối cho bên thứ ba, test thêm consumer project và dependency graph thực sự.

### 12.1. Điều kiện PASS rõ ràng

**Compile PASS** chưa đủ. Một release nên có:

- **Language PASS:** `javac --release 17` compile cả record, text block không preview.
- **Runtime PASS:** ứng dụng chạy thật trên minimum runtime, `Class.isRecord()==true`, output đúng.
- **Framework PASS:** Jackson/mapper/JPA DTO conversions đúng, đủ error cases.
- **Processor PASS:** compiler model `RECORD` được xử lý và generated code compile.
- **Source-tool PASS:** formatter/linter không đổi ngữ nghĩa chuỗi.
- **Bytecode-tool PASS:** test agent/coverage/static analysis hoạt động với class-file version.
- **Deployment PASS:** artifact cuối chạy bằng JVM thực tế, không vô tình dựa vào local IDE.

Nên log **JDK vendor/build, Java target, Maven/Gradle wrapper, plugin versions, Jackson branch, OS, dependencies lock/BOM**. Nếu chỉ ghi `Java=17`, chưa đủ phân biệt mismatch build/runtime và plugin parser.

### 12.2. Negative tests có chủ đích

Không chỉ test đường thành công. Các trường hợp cần fail được coi là hữu ích:

- `new Task(" ",2)` → `IllegalArgumentException` sau `strip`.
- `new Task("compile",-1)` → `IllegalArgumentException`.
- Deserialize record JSON thiếu trường bắt buộc → validation failure theo contract.
- Deserialize record với tên property không khớp → fail hoặc mapping rõ như policy đã định.
- IDE/formatter nâng version nhưng làm đổi `\s` hoặc newline → **golden test FAIL**.
- Chạy bytecode Java 17 trên runtime quá cũ → expected incompatibility, không đổi compile target để giấu lỗi.
- Plugin annotation processing quá cũ không hiểu `RECORD` → pipeline FAIL thay vì “bỏ qua generated code”.

**Test phải kiểm tra đúng loại lỗi**, không so chuỗi exception message từ compiler/framework làm hợp đồng, vì messages thường thay đổi theo phiên bản.

## 13. Các lỗi thường gặp và cách sửa

### Lỗi 1 — Dùng `--enable-preview` cho record và text block trên Java 17

Cả hai đã final từ Java 16 và 15. **Sửa:** dùng `--release 17` và loại flags preview không cần thiết. Đừng áp một hướng dẫn Java 14 lịch sử cho code ổn định hiện nay.

### Lỗi 2 — Dùng `--release 14` rồi mong record/text block compile như cú pháp final

Ở Java 14 cả hai preview; `--release` hiện đại không cho phép bật lại preview cũ. **Sửa:** chọn target mới đủ hỗ trợ cả hai, chẳng hạn 17, hoặc giữ cú pháp phù hợp target cũ.

### Lỗi 3 — IDE code màu xanh nên tin CI cũng compile

IDE source level có thể khác JDK compiler, Maven daemon và Gradle toolchain. **Sửa:** so `javac`/wrapper settings và chạy build từ CLI.

### Lỗi 4 — Chỉ cập nhật plugin compiler, bỏ plugin test/formatter/coverage cũ

Một plugin code quality có parser/ASM riêng. **Sửa:** chạy đủ pipeline và cập nhật plugin đang được duy trì, không chỉ compile.

### Lỗi 5 — Library tìm `getName()` trên record component `name`

Record tạo `name()`, không `getName()`. **Sửa:** dùng record-aware introspection/constructor mapping và test thực tế.

### Lỗi 6 — Tin rằng record có setter hoặc constructor rỗng

Record thông thường dùng canonical constructor và fields final. **Sửa:** chọn DTO mapping bằng constructor, hoặc giữ mutable entity class khi framework đòi setters/no-arg/proxy.

### Lỗi 7 — Chỉ test serialize, không test deserialize record

Ghi JSON được chưa đảm bảo tạo record lại đúng. **Sửa:** test **round-trip** và fields thiếu/null/constructor validation.

### Lỗi 8 — Dùng Jackson 2 imports trong Jackson 3 project hoặc ngược lại

Jackson 3 đổi packages core thành `tools.jackson`. **Sửa:** chọn một major branch được framework/BOM hỗ trợ, migrate code/dependencies đúng và test toàn bộ.

### Lỗi 9 — Tin rằng thêm Jackson 2.12 lịch sử là khuyến nghị production

2.12 là mốc bắt đầu hỗ trợ record, không phải lời khuyên dùng bản cũ đã qua vòng hỗ trợ. **Sửa:** dùng bản đang bảo trì theo BOM và security policy.

### Lỗi 10 — Annotation processor bỏ qua `ElementKind.RECORD`

Processor có thể chỉ nhận `CLASS`. **Sửa:** test compile-time model, generated code, annotation target propagation.

### Lỗi 11 — Dùng Lombok getters/setters như thể record là mutable bean

Nhiều tính năng sinh boilerplate không cần/không phù hợp record. **Sửa:** loại annotations thừa, kiểm tra support và dùng canonical validation.

### Lỗi 12 — Cho rằng record tự deep immutable

Tham chiếu final nhưng mutable list/array element vẫn có thể đổi. **Sửa:** defensive copies và test mutable inputs, hoặc model bất biến sâu hơn.

### Lỗi 13 — Dùng record làm JPA entity drop-in

Final/no-arg/proxy/mutability assumptions có thể xung đột. **Sửa:** dùng record cho DTO/projection khi framework hỗ trợ; test persistence proxy trước khi chọn record entity.

### Lỗi 14 — Format text block làm biến dạng payload

Thay indent/closing delimiter có thể làm nội dung LF/spaces đổi. **Sửa:** formatter hỗ trợ text blocks và golden tests cho string.

### Lỗi 15 — Đặt trailing spaces thô và nghĩ formatter sẽ giữ

Whitespace cuối dòng có thể bị strip. **Sửa:** dùng `\s` khi cần giữ space cuối và test giá trị cụ thể.

### Lỗi 16 — Trộn text block với parser JSON/SQL

Text block chỉ tạo `String`; không tự validate/escape dữ liệu JSON, SQL. **Sửa:** serializer/PreparedStatement với binding, tránh nối dữ liệu không tin cậy.

### Lỗi 17 — Quên LF cuối text block

Closing delimiter khác dòng thường tạo final LF; đây có thể làm snapshot fail. **Sửa:** kiểm tra `endsWith("\n")`, string equals và bytes của protocol.

### Lỗi 18 — Coi `java.lang.Record` là tên class dự án không thể trùng

Một class tên `Record` trong package khác có thể tạo import ambiguity với `java.lang.Record`. **Sửa:** đổi tên hoặc dùng explicit import/tên đủ điều kiện khi cần.

### Lỗi 19 — Thử trên JDK24 rồi tuyên bố runtime Java17 chắc chắn chạy

`--release17` chỉ giúp compiler giữ language/API target; third-party dependencies và runtime launcher vẫn phải được test bằng **Java17 thật**. **Sửa:** minimum-runtime CI lane.

### Lỗi 20 — Xem `mvn test` SUCCESS với 0 tests là bằng chứng

Không có tests được chạy thì không xác minh được serializer, formatter và records. **Sửa:** kiểm tra số tests, reports và đường code đã thực hiện.

### Lỗi 21 — Coverage thấp ở record-generated methods nên sửa code theo % mù quáng

Coverage instrumentation và compiler-generated code có đặc thù riêng. **Sửa:** nâng tool tương thích và test behavior quan trọng, không tối ưu chỉ số không có ý nghĩa.

### Lỗi 22 — Thư viện chạy được cho class thường nên chắc chắn hỗ trợ record

Record có constructor/accessor/final/metadata khác. **Sửa:** tạo một fixture record thật, test cả success/invalid inputs.

## 14. Checklist thực hành trước khi nâng phiên bản thư viện/công cụ

- [ ] Đã xác định minimum supported runtime và build JDK.
- [ ] Có `--release 17` hoặc mục tiêu phù hợp cả record và text block, không dùng preview flags lỗi thời.
- [ ] `javac` biên dịch record/text block trên source/test.
- [ ] Bytecode class-file version được toolchain và runtime đích chấp nhận.
- [ ] Maven/Gradle **wrapper/compiler plugin/toolchain** được pin và hiển thị trong CI log.
- [ ] Có smoke test `RecordTextBlockSmoke` trên minimum runtime.
- [ ] Có integration test serialize+deserialize record với JSON library đúng major branch.
- [ ] Có validation test cho compact constructor, fields thiếu/null và component naming.
- [ ] Có test record `equals/hashCode/toString` khi đó là hợp đồng sản phẩm.
- [ ] Có defensive copy tests khi record chứa mutable references.
- [ ] Annotation processors/MapStruct/schema generators nhận record components.
- [ ] Code generation outputs compile thành công trên target.
- [ ] Test runner thực sự chạy tests; không chấp nhận 0 tests ngoài dự kiến.
- [ ] Formatter/linter/source analyzer xử lý `"""`, `\s` và line continuation.
- [ ] Golden tests bảo vệ exact LF, incidental indentation và trailing spaces của text blocks.
- [ ] Coverage agent/bytecode scanner có hỗ trợ class-file target.
- [ ] Framework/ORM proxy constraints được kiểm tra nếu dùng records với persistence.
- [ ] Trên Jackson 3.x, packages core dùng `tools.jackson`; không pha Jackson majors mù quáng.
- [ ] Test runtime thật (VM/container) thay vì chỉ Java cài trên workstation.
- [ ] Có bảng tương thích library/plugin versions và JDK baseline.
- [ ] Không dùng text block formatted trực tiếp để dựng SQL/JSON từ input không đáng tin.
- [ ] Có log JDK vendor/build, Maven/Gradle version, dependency graph/BOM và kết quả test.
- [ ] Kiểm tra tương thích consumer nếu đây là thư viện được publish ra ngoài.
- [ ] Không lấy một dòng “build success” làm bằng chứng toàn bộ use cases.

## 15. Bài tập thực hành

1. **Mốc version:** record và text block trở thành tính năng final ở các phiên bản Java nào?
2. **Compiler:** dự đoán kết quả của `--release 14`/`15`/`16`/`17` với `RecordGate` và `TextBlockGate`, sau đó xác nhận.
3. **Preview:** vì sao không dùng `--enable-preview` cho hai tính năng này trong Java 17+?
4. **Reflection:** dùng `Class.isRecord()` và `getRecordComponents()` liệt kê các components của `Task`.
5. **Constructor:** thử `new Task(" ",2)` và `new Task("compile",-1)`; cả hai cần kết thúc thế nào?
6. **Value equality:** tạo hai records có các component values như nhau; kiểm tra `equals`/`hashCode`.
7. **Shallow immutability:** đặt `List` có thể sửa vào record, thay list sau khi tạo, rồi thêm defensive copy; so sánh.
8. **Arrays:** vì sao records chứa `byte[]` có thể không có equality theo nội dung mong muốn?
9. **Text block LF:** so sánh output của `System.out.print` với `println`; xác nhận final newline.
10. **Escapes:** giải thích `\s` và `\` cuối dòng trong `RecordTextBlockSmoke`.
11. **Formatter:** chạy formatter trên `RecordTextBlockSmoke`, test exactWhitespace trước/sau.
12. **SQL/JSON:** tại sao `"""...""".formatted(untrustedName)` không chống injection?
13. **JavaBeans:** so `RecordBeanProbe` reflection components với `Introspector` property names.
14. **Annotation processing:** biên dịch `RecordAwareProcessor`, kiểm tra phát hiện `ElementKind.RECORD` và số components.
15. **Maven:** tạo POM với `maven.compiler.release=17`, xác minh compiler plugin version và build JDK.
16. **Gradle:** cấu hình Java toolchain 17 và `options.release.set(17)`, chạy `./gradlew check`.
17. **Jackson:** viết integration test cho cả serialize và deserialize một `record JobDto(...)`; kiểm tra fields thiếu/null.
18. **Jackson major migration:** chỉ ra khác nhau giữa imports `com.fasterxml.jackson.databind` (2.x) và `tools.jackson.databind` (3.x).
19. **Coverage:** nâng JDK của CI, sau đó `jacocoTestReport`/Maven JaCoCo hoặc quality gate bị lỗi classfile; phải kiểm tra ở tầng nào?
20. **CI:** thiết kế ma trận gồm minimum JDK, production JDK, lint/formatter, annotation processors, serializer và runtime container.
21. **Negative tests:** tạo `RecordGate.java` và `TextBlockGate.java` với mức release thấp hơn để xác minh test gate báo lỗi có chủ đích.
22. **Review:** khi “IDE xanh nhưng CI đỏ”, liệt kê ít nhất năm nơi cần so sánh version/settings.

**Gợi ý đáp án:** (1) text block Java15, record Java16; (2) bảng mục 2; (3) tính năng final; (4) Java17 reflection; (5) IllegalArgumentException; (6) component-based equality; (7) defensive List.copyOf, không tự sâu; (8) mảng so reference; (9) closing delimiter và print/println; (10) space và line continuation; (11) golden string equality; (12) cần serializer/binder; (13) accessor names khác; (14) compiler model; (15–16) build toolchain + target; (17) round-trip với library thực; (18) Jackson major packages; (19) plugin/parser/bytecode compat; (20–22) CI theo scope và versions có thể tái lập.

## 16. Nguồn tài liệu chính thức/còn áp dụng

- **Oracle Java SE 17 — Record Classes:** components, accessors, canonical/compact constructors, reflection, `java.lang.Record` và `Class.getRecordComponents`: https://docs.oracle.com/en/java/javase/17/language/records.html
- **Oracle Java SE 17 — Text Blocks:** hướng dẫn text block và semantics chuỗi: https://docs.oracle.com/en/java/javase/17/language/text-blocks.html
- **OpenJDK JEP 395 — Records:** final trong Java 16: https://openjdk.org/jeps/395
- **OpenJDK JEP 378 — Text Blocks:** final trong Java 15: https://openjdk.org/jeps/378
- **Oracle Java Language Changes Java 16:** bảng trạng thái final/preview Java14–16: https://docs.oracle.com/en/java/javase/16/language/java-language-changes.html
- **Oracle Java SE 17 — `RecordComponent` API:** reflection: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/RecordComponent.html
- **Oracle Java SE 17 — `ElementKind.RECORD`/`RecordComponentElement`:** Java compiler annotation model: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/ElementKind.html
- **Apache Maven — Targeting a Java Version:** `maven.compiler.release`: https://maven.apache.org/guides/mini/guide-java-target.html
- **Apache Maven — Toolchains:** chọn JDK toolchain cho Maven plugins: https://maven.apache.org/guides/mini/guide-using-toolchains
- **Apache Maven — Compiler Plugin:** phiên bản và cấu hình hiện hành: https://maven.apache.org/plugins/maven-compiler-plugin/
- **Gradle — Toolchains for JVM Projects:** `languageVersion`, `options.release`, daemon/runtime compatibility: https://docs.gradle.org/current/userguide/toolchains.html
- **FasterXML Jackson — Jackson Release 2.12:** mốc record support và thay đổi one-property record: https://github.com/FasterXML/jackson/wiki/Jackson-Release-2.12
- **FasterXML Jackson — Release 3.0 / Migration:** Java17 baseline, namespace `tools.jackson`, thay đổi core API: https://github.com/FasterXML/jackson/wiki/Jackson-Release-3.0
- **FasterXML Jackson — Migrating to Jackson 3:** chuyển dependency/package và defaults: https://github.com/FasterXML/jackson/blob/main/jackson3/MIGRATING_TO_JACKSON_3.md
- **JaCoCo — Change History:** mức hỗ trợ Java class-file hiện hành: https://www.jacoco.org/jacoco/trunk/doc/changes.html
- **Oracle JDK 17 — `javac` man page:** `--release` và compiler options: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html

**Ghi nhớ:** Kiểm tra record và text block **không chỉ là chọn một JDK đủ mới**. `record` final từ Java 16; `text block` final từ Java 15; Java 17+ dùng cả hai bình thường **không có preview flags**. Hãy giữ **build JDK, compiler `--release`, test runtime, Maven/Gradle plugins, IDE/formatter, annotation processors, serializers và bytecode tools** nhất quán. Dùng **runnable smoke test + integration tests** để xác nhận cả record-component mapping lẫn nội dung text block **đúng từng ký tự** trước khi phát hành.
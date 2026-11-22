# Phân biệt phiên bản ngôn ngữ Java, phiên bản API và JVM đích khi xây dựng ứng dụng

## 1. Vì sao một dự án Java có thể “biên dịch thành công nhưng chạy lỗi”?

Giả sử nhóm phát triển dùng **JDK 24** để biên dịch, trong khi máy chủ production còn chạy **Java 17**. Mã nguồn chỉ dùng cú pháp Java 17, và compiler tạo tệp `.class` tương thích Java 17. Liệu chương trình chắc chắn chạy được trên máy chủ?

**Chưa chắc.** Nếu biên dịch vô tình tham chiếu một **API JDK được bổ sung sau Java 17**, tệp `.class` có thể có đúng phiên bản bytecode nhưng khi thực thi trên JDK 17 lại không tìm thấy phương thức hoặc lớp đó.

Để đánh giá tương thích Java, cần tách rõ ít nhất bốn thông tin:

1. **Phiên bản JDK dùng để build:** bộ compiler và thư viện nền tảng có mặt trên máy biên dịch, ví dụ JDK 21 hoặc JDK 24.
2. **Phiên bản ngôn ngữ nguồn (*source/language level*):** cú pháp và tính năng ngôn ngữ được phép viết, ví dụ `var`, record, switch expression.
3. **Phiên bản API được phép tham chiếu:** các lớp, phương thức và hằng số thư viện JDK mà chương trình có thể gọi, ví dụ `List.copyOf` hay `String.indent`.
4. **Phiên bản tệp class/JVM đích (*bytecode target*):** format `.class` được tạo và mức JVM thấp nhất có thể hiểu format đó.

Ngoài ra, còn có **JVM thực sự chạy ứng dụng**, **thư viện phụ thuộc**, module, native library, hệ điều hành và tính năng runtime. Bốn trục đầu là nền tảng để không hiểu nhầm các tùy chọn `javac` và cấu hình build.

**Thông điệp chính:** “mã viết theo cú pháp Java 17”, “chỉ dùng API có trên Java 17” và “tạo class file cho JVM 17” là **ba cam kết khác nhau**. Trong thực tế nên dùng `javac --release 17` khi cần kiểm soát đồng thời ba cam kết đó đối với API nền tảng Java.

## 2. Bốn phiên bản cần nhận biết

| Trục | Câu hỏi cần trả lời | Điều gì kiểm soát? |
| --- | --- | --- |
| **Compiler JDK** | Lệnh `javac` thuộc JDK nào? | JDK được chọn bởi PATH/toolchain/IDE/build tool |
| **Language/source** | Source được phép dùng cú pháp đến phiên bản nào? | `--source N` hoặc `--release N` |
| **JDK API** | Source được phép dùng API Java SE/JDK đến phiên bản nào? | **`--release N`** (hoặc nền tảng API thích hợp khi có cấu hình thủ công) |
| **Class/JVM target** | `.class` sẽ dùng major version nào? | `--target N` hoặc `--release N` |
| **Runtime deployment** | Ứng dụng thực sự chạy trên JVM nào? | `java` / container image / server JDK thực tế; **không do compiler tự quyết định** |

Ví dụ một dự án có thể có:

```text
Compiler JDK:    24
Language level:  17
JDK API level:   17
Class target:    17 (major 61)
Runtime JVM:     17 hoặc mới hơn, tùy hệ thống triển khai
```

Khi build với một compiler hỗ trợ đích 17:

```bash
javac --release 17 Main.java
```

`--release 17` yêu cầu **quy tắc ngôn ngữ Java 17**, **API nền tảng được hỗ trợ của Java 17** và **class format mục tiêu Java 17**. Tuy vậy, lệnh này **không tự chạy hay kiểm thử** ứng dụng trên một JVM 17 thật, cũng không bảo đảm mọi dependency bên ngoài tương thích.

**Cần phân biệt build JDK và runtime JDK:** compiler mới có thể tạo class file cũ, còn JVM production không cần cùng phiên bản với compiler miễn các điều kiện tương thích thực sự được đáp ứng.

## 3. Phiên bản ngôn ngữ: cú pháp nào được phép viết?

Phiên bản ngôn ngữ xác định **cấu trúc source được compiler chấp nhận**.

Ví dụ về các mốc ngôn ngữ đã được chuẩn hóa và vẫn được dùng:

| Ví dụ | Mốc giới thiệu ổn định | Thuộc loại |
| --- | --- | --- |
| Biến cục bộ khai báo `var` | Java **10** | **Ngôn ngữ** |
| Switch expressions | Java **14** | **Ngôn ngữ** |
| Records | Java **16** | **Ngôn ngữ** |
| Pattern matching cho `instanceof` | Java **16** | **Ngôn ngữ** |
| Sealed classes | Java **17** | **Ngôn ngữ** |
| Pattern matching cho `switch` | Java **21** | **Ngôn ngữ** |

Ví dụ `var`:

```java
var count = 3; // Java 10+
```

Đây là lệnh minh họa bên trong phương thức; không thể dùng `var` làm kiểu khai báo trường theo cùng cách. Nếu source target thấp hơn 10, cú pháp biến cục bộ `var` không được chấp nhận như tính năng Java 10.

Ví dụ record:

```java
record Point(int x, int y) {}
```

Record trở thành tính năng ngôn ngữ chính thức ở Java 16. Vì vậy:

- Với `javac --release 11`, mã record ở trên **không được chấp nhận**.
- Với `javac --release 17`, cú pháp trên **được chấp nhận**.

**Đừng nhầm API với cú pháp:** `List.copyOf` không phải một từ khóa hay cấu trúc ngôn ngữ mới. Nó là **phương thức của thư viện JDK**, nên khả năng gọi nó thuộc trục **API**. Ngược lại, `record` và `var` cần compiler hiểu cú pháp tương ứng.

## 4. Phiên bản API: lớp/phương thức nào tồn tại?

Java liên tục bổ sung các API trong `java.*`, `javax.*` hoặc JDK modules. Source có thể hợp lệ về **cú pháp** nhưng dùng một **phương thức chưa tồn tại** ở runtime đích.

| API minh họa | Có từ | Vì sao cần kiểm tra? |
| --- | --- | --- |
| `List.of(...)` | Java 9 | API factory của List |
| `List.copyOf(...)` | Java **10** | API tạo List không sửa được từ Collection |
| `Collectors.toUnmodifiableList()` | Java **10** | API Collector |
| `String.isBlank()` | Java **11** | API String |
| `String.indent(int)` | Java **12** | API String |
| `Stream.toList()` | Java **16** | API Stream |
| `Thread.ofVirtual()` | Java **21** | API tạo virtual thread |

Các phiên bản trên là mốc giới thiệu API, không phải tuyên bố rằng mọi ứng dụng phải dùng JDK mới nhất. **Nếu chạy trên Java 11**, gọi `String.indent(2)` không hợp lệ vì Java 11 **chưa có phương thức này**, dù cú pháp gọi phương thức hoàn toàn tương thích Java 11.

Ví dụ:

```java
class ApiCheck {
    static String indent(String text) {
        return text.indent(2); // String.indent(int) có từ Java 12
    }
}
```

Chương trình này **không cần cú pháp Java 12**. Nó chỉ dùng các cấu trúc ngôn ngữ quen thuộc từ trước, nhưng **phụ thuộc vào JDK API Java 12+**.

Một phản ví dụ khác:

```java
var unique = java.util.List.copyOf(source);
```

Lệnh này cùng lúc yêu cầu **ngôn ngữ Java 10** (do `var`) và **API Java 10** (do `List.copyOf`). Nếu bỏ `var` mà thay bằng kiểu tường minh, ràng buộc API vẫn tồn tại: không thể dùng `List.copyOf` trên runtime Java 9 chỉ nhờ đổi cú pháp.

### Không chỉ nhìn tên lớp

Một lớp có thể tồn tại từ rất lâu nhưng **một phương thức mới trong lớp ấy** chỉ có ở JDK gần đây. Ví dụ `String` tồn tại từ những bản Java đầu, nhưng `String.indent` được bổ sung ở Java 12. Vì vậy “lớp String đã có từ lâu” **không chứng minh** tất cả phương thức của `String` đều có trên runtime cũ.

## 5. JVM đích: định dạng tệp `.class`

Compiler Java chuyển source thành bytecode và metadata trong các tệp `.class`. Mỗi tệp class có một **major version** chỉ ra định dạng mà JVM phải hỗ trợ.

Theo Java Virtual Machine Specification hiện hành:

| Java SE | Class file major | Gợi ý |
| --- | ---: | --- |
| Java 10 | **54** | Mốc của module Java 10 |
| Java 11 | **55** | Runtime Java 11 |
| Java 17 | **61** | Runtime Java 17 |
| Java 21 | **65** | Runtime Java 21 |
| Java 25 | **69** | Runtime Java 25 |
| Java 27 | **71** | Runtime Java 27 |

Ví dụ khi dùng compiler hỗ trợ release 17:

```bash
javac --release 17 Hello.java
javap -verbose Hello
```

Trong output của `javap -verbose` có thông tin kiểu:

```text
major version: 61
```

Dòng major có thể xác định với tệp class bất kỳ, không cần suy luận từ tên JAR hay cấu hình IDE.

**Ý nghĩa:** JVM Java 11 không hiểu class format major 61 của Java 17 và có thể ném `UnsupportedClassVersionError`. Ngược lại, một JVM mới hơn nhìn chung hỗ trợ classfile của các phiên bản cũ, nhưng **nó vẫn phải có các API/libraries và hành vi tương thích mà chương trình cần**.

**Đừng nhầm:** `major 55` nghĩa class được đóng gói theo định dạng Java 11, **không có nghĩa chương trình chắc chắn chỉ dùng API Java 11**. Đó chính là lỗ hổng khi chỉ đặt `-target 11` mà không giới hạn API nền tảng.

## 6. `--source`, `--target` và `--release` có vai trò khác nhau

### 6.1. `--source N`: giới hạn cú pháp

```bash
javac --source 17 MyApp.java
```

`--source 17` yêu cầu compiler phân tích mã theo quy tắc ngôn ngữ Java 17. Nó **không tự áp dụng hàng rào API JDK 17**, và không thay thế việc chọn JVM đích.

Trong hướng dẫn hiện đại, không nên coi `--source` một mình là một chính sách tương thích runtime hoàn chỉnh.

### 6.2. `--target N`: đặt classfile target

```bash
javac --source 17 --target 17 MyApp.java
```

Tùy chọn `--target 17` hướng dẫn compiler tạo tệp class theo phiên bản có thể được JVM Java 17 đọc. Nó **không bảo đảm mã chỉ tham chiếu các phương thức đã có trong Java 17** nếu compiler đang sử dụng thư viện nền tảng mới hơn.

`--target` phải **không thấp hơn** `--source` theo các quy tắc compiler được hỗ trợ. Đừng cố “viết source Java 21 nhưng ép target Java 17” và kỳ vọng compiler tự hạ cấp một tính năng ngôn ngữ mới theo cách tùy ý.

### 6.3. `--release N`: đặt cả ba lớp tương thích nền tảng

```bash
javac --release 17 MyApp.java
```

`--release` kiểm soát đồng thời:

1. Các **quy tắc ngôn ngữ** được chấp nhận.
2. **API Java SE/JDK công khai được hỗ trợ và có tài liệu** cho release đó.
3. **Định dạng classfile** tương ứng với release đó.

Đây là lựa chọn khuyến nghị khi mục tiêu là **build trên JDK mới và chạy trên nền tảng Java cũ hơn**. Nó được bổ sung từ JDK 9 và vẫn là công cụ hiện hành.

**Không kết hợp `--release` với `--source` hoặc `--target` trong cùng một lệnh**: Javadoc `javac` quy định các tùy chọn đó không đi cùng nhau.

Ví dụ nếu yêu cầu tối thiểu Java 17:

```bash
javac --release 17 MyApp.java
java MyApp
```

Để thực sự bảo đảm hỗ trợ production Java 17, còn cần **chạy kiểm thử trên JVM Java 17** và rà soát dependencies/runtime. `--release` là điều kiện mạnh ở bước compile nhưng **không phải bảo chứng toàn hệ thống**.

## 7. Minh họa lỗi nguy hiểm của `-source` + `-target` khi build trên JDK mới

Giả sử file `ApiCheck.java` chứa:

```java
public class ApiCheck {
    public static void main(String[] args) {
        System.out.println("x".indent(2).length());
    }
}
```

`String.indent` có từ Java **12**. Nhưng cú pháp của đoạn code này không đòi hỏi tính năng ngôn ngữ Java 12.

Trên **compiler JDK 17 trở lên** có hỗ trợ release 11:

```bash
javac --release 11 ApiCheck.java
```

**Kết quả:** compiler **không cho qua**, vì API `String.indent(int)` không tồn tại ở Java 11. Nội dung lỗi cụ thể thay đổi theo phiên bản javac, nhưng thường là không tìm thấy phương thức thích hợp trong `String`.

Ngược lại:

```bash
javac -source 11 -target 11 ApiCheck.java
```

Trên một JDK mới có `String.indent`, câu lệnh này **có thể biên dịch thành công** và tạo class major 55. Compiler chấp nhận cú pháp Java 11, tạo bytecode target Java 11, **nhưng vẫn tham chiếu `String.indent` từ thư viện JDK mới đang dùng để build**.

Khi chạy tệp class đó trên **JVM Java 11**, trình liên kết phương thức không tìm thấy `String.indent(int)` và ứng dụng có thể gặp **`NoSuchMethodError`** khi đường chạy chạm vào lời gọi ấy.

Đây là **lỗi tương thích API**, không phải lỗi classfile major. Nếu chỉ kiểm tra `major 55` rồi kết luận hỗ trợ runtime Java 11, kiểm thử sẽ bỏ sót.

**Kết luận thực hành:** để đảm bảo API nền tảng theo đích, ưu tiên `--release 11` thay cho chỉ `-source 11 -target 11`.

## 8. Ví dụ về tính năng ngôn ngữ khác với API

Xét record:

```java
record Point(int x) {}
```

Với compiler hỗ trợ cả hai release:

```bash
javac --release 11 Point.java
```

**Kết quả:** thất bại vì `record` không phải tính năng ngôn ngữ đã hoàn thiện ở Java 11.

```bash
javac --release 17 Point.java
```

**Kết quả:** thành công và tạo class format Java 17 (`major 61`).

Khác với ví dụ `String.indent`, lỗi ở đây là **source/language level**, không phải API đã có hay chưa. Khi chọn `--release`, compiler kiểm tra cả hai loại lỗi độc lập.

**Cảnh báo với preview features:** một số tính năng ngôn ngữ đi qua giai đoạn *preview* trước khi thành chính thức. Không nên coi ví dụ preview là cú pháp được hỗ trợ lâu dài ở mọi bản release. Với phần mềm production, ưu tiên tính năng đã ổn định và theo đúng tài liệu release đang dùng. `--enable-preview` có quy tắc riêng, có thể yêu cầu đúng phiên bản JDK tương ứng; nó không phải cách “hạ cấp” một tính năng mới cho JVM cũ.

## 9. Công cụ đang dùng là JDK nào?

Không nên phỏng đoán phiên bản Java từ cấu hình IDE hoặc tệp `pom.xml` mà chưa nhìn tool thực tế.

Các lệnh kiểm tra:

```bash
java --version
javac --version
javac --help
```

Ý nghĩa:

- `java --version`: phiên bản Java launcher/runtime của lệnh `java` hiện tại.
- `javac --version`: phiên bản compiler thực sự được chọn.
- `javac --help`: trong đó có danh sách **các release mà phiên bản compiler này hỗ trợ** cho `--source`, `--target` và `--release`.

**Điểm rất quan trọng với Java 10:** một compiler hiện đại **không bắt buộc hỗ trợ `--release 10` mãi mãi**. Javadoc `javac` nói compiler chỉ hỗ trợ **release hiện tại và một số release trước đó có giới hạn**. Do đó, trước khi dùng `--release 10` trên một JDK rất mới, phải kiểm tra `javac --help` và không suy ra việc compiler có thể biên dịch mọi phiên bản Java lịch sử.

Java 10 từng là một mốc tính năng quan trọng, nhưng với ứng dụng production hiện đại, cần chọn phiên bản Java được sản phẩm và nhà cung cấp runtime duy trì cập nhật bảo mật. Bài này dùng Java 10 như mốc **kiến thức về mô hình phiên bản**, không khuyến nghị triển khai mới trên một JDK 10 đã hết chu kỳ cập nhật thông thường.

## 10. Build JDK, target runtime và dependencies phải tương thích với nhau

Giả sử ứng dụng có:

```text
Compiler JDK:          21
Ứng dụng --release:    17
JVM chạy thật:         17
Dependency A:          biên dịch cho Java 17
Dependency B:          biên dịch cho Java 21
```

Dù source ứng dụng qua `--release 17`, **dependency B** vẫn có thể làm build hoặc runtime Java 17 thất bại vì nó dùng classfile major 65 hoặc API Java 21.

`--release` giới hạn **API nền tảng Java được tham chiếu từ source đang biên dịch**; nó **không hạ cấp bytecode trong JAR bên thứ ba**. Tùy cách dependency được đưa vào và được dùng, compiler có thể báo lỗi khi đọc classfile mới hơn mức compiler hỗ trợ, hoặc runtime có thể ném `UnsupportedClassVersionError` khi tải lớp của dependency trên JVM cũ.

Các yếu tố cần kiểm soát:

- **Classfile version** của mọi JAR cần tải trên runtime mục tiêu.
- **API yêu cầu** của dependency, kể cả API nền tảng được gọi nội bộ.
- **Phiên bản JDK tối thiểu** do nhà phát hành thư viện công bố.
- **JPMS/module descriptors**, service loading, reflection, agent, class loading.
- **JNI/native libraries**, kiến trúc CPU/OS và phiên bản runtime thực tế.
- Sự khác nhau về hành vi, thuật toán hoặc hệ thống mã hóa/locale khi nâng JDK.

Một dependency có bytecode cũ **chưa chắc** an toàn với JVM cũ nếu nó viện dẫn API mới ở runtime. Kiểm tra bytecode là một bước cần thiết nhưng không thể thay thế **test chạy thật**.

## 11. Cách nhận biết các lỗi tương thích khi chạy

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra đầu tiên |
| --- | --- | --- |
| `UnsupportedClassVersionError` | JVM không hỗ trợ **major version** của class đang tải | `javap -verbose` trên class và `java --version` của runtime |
| `NoSuchMethodError` | Method mà bytecode gọi **không có** ở định nghĩa class được tải khi chạy | API JDK/dependency thực tế, classpath/module path |
| `NoSuchFieldError` | Field được tham chiếu không tồn tại ở runtime | Phiên bản thư viện/class đã nạp |
| `NoClassDefFoundError` | JVM không thể tìm/khởi tạo class cần thiết tại runtime | Packaging, dependency, modules |
| `ClassNotFoundException` | Tra cứu class động bằng tên thất bại | Classloader, tên class, runtime classpath |
| Lỗi cú pháp khi build | Source dùng tính năng mới hơn `--source`/`--release` | Language level và lỗi compiler |
| Không tìm thấy phương thức JDK khi build với `--release` | API chỉ có ở Java mới hơn mức release | Javadoc `Since` của method và giá trị `--release` |
| Chạy được nhưng kết quả khác | API/locale/provider/runtime behavior khác hoặc dùng preview | Test trên JVM mục tiêu, kiểm tra migration notes |

**`UnsupportedClassVersionError` và `NoSuchMethodError` không giống nhau.** Một lỗi báo “JVM không đọc được định dạng class”, lỗi kia báo “đã đến bước liên kết lời gọi nhưng không có thành viên tương ứng”. Biết phân biệt sẽ giúp chẩn đoán đúng trục tương thích.

## 12. Chương trình Java 17+ hoàn chỉnh: tự kiểm chứng ba trục bằng Java Compiler API

Chương trình dưới đây sử dụng **`javax.tools.JavaCompiler`** có trong JDK để biên dịch một số source nhỏ **hoàn toàn trong bộ nhớ**. Nó giúp quan sát khác biệt giữa:

- Cú pháp record không được phép khi `--release 11` nhưng được phép khi `--release 17`.
- API `String.indent` (Java 12) bị chặn bởi `--release 11`.
- Cùng API đó **vẫn được chấp nhận** bởi `-source 11 -target 11` khi compiler chạy trên một JDK mới.
- Major version của classfile thật trong bộ nhớ: Java 11 là **55**, Java 17 là **61**.

Tạo file `JavaCompatibilityDemo.java`:

```java
import java.io.ByteArrayOutputStream;
import java.io.OutputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class JavaCompatibilityDemo {

    record Result(boolean ok, int major, long errors) { }

    static Result compile(
            String name, String code, List<String> options)
            throws Exception {

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Need a JDK compiler");
        }

        var diagnostics = new DiagnosticCollector<JavaFileObject>();

        try (var standard = compiler.getStandardFileManager(
                diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {

            var classBytes =
                    new HashMap<String, ByteArrayOutputStream>();

            // Ghi classfile vào bộ nhớ, không tạo .class trên đĩa.
            var memoryFiles =
                    new ForwardingJavaFileManager<
                            StandardJavaFileManager>(standard) {

                @Override
                public JavaFileObject getJavaFileForOutput(
                        Location location,
                        String className,
                        JavaFileObject.Kind kind,
                        FileObject sibling) {

                    return new SimpleJavaFileObject(
                            URI.create("mem:///"
                                    + className.replace('.', '/')
                                    + kind.extension),
                            kind) {

                        @Override
                        public OutputStream openOutputStream() {
                            var output = new ByteArrayOutputStream();
                            classBytes.put(className, output);
                            return output;
                        }
                    };
                }
            };

            var source = new SimpleJavaFileObject(
                    URI.create("string:///" + name + ".java"),
                    JavaFileObject.Kind.SOURCE) {

                @Override
                public CharSequence getCharContent(
                        boolean ignoreEncodingErrors) {
                    return code;
                }
            };

            boolean ok = compiler.getTask(
                    null,
                    memoryFiles,
                    diagnostics,
                    options,
                    null,
                    List.of(source)).call();

            int major = -1;
            if (classBytes.containsKey(name)) {
                byte[] bytes = classBytes.get(name).toByteArray();
                // Magic CAFEBABE (0..3), minor (4..5), major (6..7).
                major = ((bytes[6] & 0xff) << 8)
                        | (bytes[7] & 0xff);
            }

            long errors = diagnostics.getDiagnostics().stream()
                    .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
                    .count();

            return new Result(ok, major, errors);
        }
    }

    public static void main(String[] args) throws Exception {
        // Record là tính năng ngôn ngữ chính thức từ Java 16.
        String syntax = "record Point(int x) {}";

        var syntax11 = compile(
                "Point", syntax, List.of("--release", "11"));
        var syntax17 = compile(
                "Point", syntax, List.of("--release", "17"));

        System.out.println(
                "record.release11=" + syntax11.ok());
        System.out.println(
                "record.release17=" + syntax17.ok());
        System.out.println(
                "record.release17.major=" + syntax17.major());

        // String.indent(int) là API JDK có từ Java 12.
        String newerAPI =
                "class ApiCheck { static String f(String s) { "
                + "return s.indent(2); } }";

        var safe = compile(
                "ApiCheck",
                newerAPI,
                List.of("--release", "11"));

        var unsafe = compile(
                "ApiCheck",
                newerAPI,
                List.of("-source", "11", "-target", "11"));

        System.out.println(
                "api.release11=" + safe.ok());
        System.out.println(
                "api.source11.target11=" + unsafe.ok());
        System.out.println(
                "api.source11.target11.major=" + unsafe.major());

        var simple = compile(
                "Hello",
                "class Hello { static int answer() { return 42; } }",
                List.of("--release", "11"));

        System.out.println(
                "safe.release11=" + simple.ok());
        System.out.println(
                "safe.release11.major=" + simple.major());

        boolean passed =
                !syntax11.ok()
                && syntax17.ok()
                && syntax17.major() == 61
                && !safe.ok()
                && unsafe.ok()
                && unsafe.major() == 55
                && simple.ok()
                && simple.major() == 55;

        System.out.println("tests=" + (passed ? "PASS" : "FAIL"));
    }
}
```

Biên dịch và chạy trên **JDK 17 trở lên** có Java Compiler API và hỗ trợ các đích `11`/`17`:

```bash
javac JavaCompatibilityDemo.java
java JavaCompatibilityDemo
```

Output đã kiểm chứng với JDK 24:

```text
record.release11=false
record.release17=true
record.release17.major=61
api.release11=false
api.source11.target11=true
api.source11.target11.major=55
safe.release11=true
safe.release11.major=55
tests=PASS
```

**Tại sao các dòng đó quan trọng?**

1. `record.release11=false`: compiler không chấp nhận cú pháp record dưới language level Java 11.
2. `record.release17=true`: cùng source được chấp nhận dưới language level Java 17.
3. `record.release17.major=61`: classfile được tạo theo Java 17.
4. `api.release11=false`: API `String.indent` bị giới hạn bởi platform API Java 11.
5. `api.source11.target11=true`: chỉ dùng `-source 11 -target 11` cho phép compiler mới tham chiếu API Java 12.
6. `api.source11.target11.major=55`: classfile vẫn là Java 11; **major thấp không chứng minh API tương thích**.
7. `safe.release11=true` và `safe.release11.major=55`: một source chỉ dùng cú pháp/API phù hợp có thể build đúng theo Java 11.
8. `tests=PASS` được in khi mọi điều kiện trên đều đúng.

**Lưu ý:** các đoạn source được biên dịch bởi chương trình là **chuỗi trong bộ nhớ**, không cần tạo các file `Point.java`/`ApiCheck.java` vật lý. Đây là một ví dụ dùng Compiler API để **kiểm chứng nguyên lý**, không phải khuyến nghị thay thế Maven/Gradle trong dự án sản xuất. Chỉ có `JavaCompatibilityDemo.java` là file người học cần tạo để chạy chương trình hoàn chỉnh.

## 13. Cấu hình Maven: dùng `maven.compiler.release`

Trong một dự án Maven dùng compiler plugin hiện hành, có thể khai báo mức Java yêu cầu:

```xml
<project>
    <!-- Các phần cấu hình project khác -->
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>
</project>
```

Đoạn XML chỉ minh họa **phần cấu hình liên quan**; không phải một `pom.xml` đầy đủ để build độc lập.

Khi Maven Compiler Plugin chạy bằng compiler hỗ trợ `--release 17`, cấu hình đó được chuyển thành yêu cầu phù hợp, giới hạn:

- Source language đến Java 17.
- JDK API được phép dùng đến Java 17.
- Classfile target Java 17.

**Nhưng Maven đang chạy bằng JDK nào?** Hãy xem:

```bash
mvn -version
```

Lệnh này cho biết Java runtime được Maven sử dụng. Nếu cần một compiler JDK cụ thể bất kể JDK chạy Maven, có thể cấu hình Maven toolchains/plugin phù hợp. `maven.compiler.release` **không tự động cài hoặc chọn đúng phiên bản JDK compiler ở mọi hệ thống**.

Trong CI nên kiểm tra cả Maven JDK lẫn JVM dùng cho test/runtime, không chỉ thuộc tính release trong POM.

## 14. Cấu hình Gradle: toolchain và `options.release` là hai việc khác nhau

Gradle hiện hành hỗ trợ **Java toolchains** để chọn JDK thực sự dùng để biên dịch, chạy test và một số tác vụ JVM khác. Đồng thời `JavaCompile.options.release` dùng để ràng buộc **language/API/classfile target**.

Ví dụ `build.gradle.kts` (Kotlin DSL):

```kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
```

Đây là **đoạn cấu hình Gradle** minh họa, cần dùng dự án có Java plugin và Gradle đủ mới; không phải code Java. Ý nghĩa:

- **Toolchain 21:** yêu cầu dùng compiler JDK 21 để xây dựng.
- **Release 17:** source được kiểm tra theo Java 17, API nền tảng Java 17, classfile major 61.

Không nhầm hai loại cấu hình:

| Cấu hình | Chọn JDK thực sự dùng để build? | Cấm API nền tảng mới hơn đích? |
| --- | --- | --- |
| Gradle **toolchain** | Có | **Không tự động**, nếu chỉ chọn compiler mới mà không đặt release cũ |
| `options.release.set(17)` | Không | **Có**, theo khả năng compiler |
| `sourceCompatibility` + `targetCompatibility` | Không | **Không có cùng bảo đảm API như `--release`** |

Vì vậy các dự án muốn build bằng JDK mới nhưng chạy trên Java cũ có thể cần **kết hợp toolchain + release**. Dự án production vẫn cần test trên JVM đích và kiểm tra dependency.

Đừng giả định JVM chạy Gradle daemon là cùng JDK với compiler toolchain; xem cấu hình/tác vụ cụ thể để biết công cụ nào đang được dùng.

## 15. Một tình huống cấu hình đúng: build JDK 21, triển khai Java 17

Giả sử sản phẩm đã chốt rằng Java 17 là **mức runtime tối thiểu**.

Quy trình hợp lý:

1. Chọn JDK compiler được build tool hỗ trợ, ví dụ JDK 21.
2. Cấu hình `--release 17` cho source Java của ứng dụng.
3. Dùng cú pháp chỉ có đến Java 17: records, sealed classes… nếu dự án cần.
4. Dùng **API Java SE/JDK chỉ có đến Java 17**; compiler sẽ chặn ví dụ `Thread.ofVirtual()` của Java 21 khi build với `--release 17`.
5. Chọn dependencies có mức Java tối thiểu tương thích 17.
6. Chạy test và một lần smoke/integration test trên **JVM 17 thật**.
7. Đóng gói/deploy cùng cấu hình được kiểm tra, tránh tình trạng local chạy JDK 21 nhưng production chỉ có 17.

Ví dụ một API Java 21 nhưng **không đòi hỏi cú pháp Java 21**:

```java
class TaskLauncher {
    void launch(Runnable task) {
        Thread.ofVirtual().start(task);
    }
}
```

`Thread.ofVirtual()` được thêm vào API ở Java 21. Dù source này nhìn rất quen thuộc với Java 17, nó **không thể build với `--release 17`**. Điều đó là chủ đích giúp phát hiện ràng buộc runtime từ sớm.

Ngược lại, nếu target **Java 21**, dùng `--release 21` trên compiler hỗ trợ release 21, và xác nhận cả thư viện và deployment phù hợp.

## 16. Java 10 có vai trò gì trong mô hình phiên bản?

Java 10 minh họa rõ việc **ngôn ngữ, API và classfile** có thể đồng thời thay đổi ở một release, nhưng không đồng nghĩa ba khái niệm là một.

| Hạng mục liên quan Java 10 | Loại thay đổi |
| --- | --- |
| `var` cho biến cục bộ | **Tính năng ngôn ngữ** |
| `List.copyOf`, `Set.copyOf`, `Map.copyOf` | **API thư viện** |
| `Collectors.toUnmodifiableList/Set/Map` | **API thư viện** |
| `Optional.orElseThrow()` không tham số | **API thư viện** |
| Classfile `major 54` | **Định dạng bytecode/JVM target** |

Ví dụ Java 10:

```java
var names = List.copyOf(source);
```

- `var` cần language level từ 10.
- `List.copyOf` cần API JDK từ 10.
- Nếu build và target đúng mức Java 10, classfile được tạo có major 54.
- Nhưng việc *chạy trên Java 10 ngày nay* còn phải xem tính an toàn cập nhật, khả năng hỗ trợ và yêu cầu môi trường; không nên chọn runtime hết hỗ trợ chỉ để tái hiện một cú pháp.

Trên JDK mới, **source tương thích Java 10 có thể chạy trên runtime mới** nếu các API và hành vi vẫn còn phù hợp. Mục tiêu học module Java 10 là hiểu các tính năng còn được sử dụng và tương thích về phía trước, không phải giữ production ở một runtime đã lỗi thời.

## 17. `--release` bảo đảm điều gì và không bảo đảm điều gì?

### `--release N` bảo đảm trong phạm vi compilation Java SE/JDK

- Áp dụng rules ngôn ngữ cho release `N`.
- Sinh classfile target `N`.
- Giới hạn việc tham chiếu đến **API Java SE/JDK công khai và được hỗ trợ** của release `N`.
- Giúp phát hiện việc vô tình gọi API Java mới hơn so với mức tối thiểu yêu cầu.

### `--release N` không tự bảo đảm

- Dependency bên thứ ba được build cho đúng target hoặc không gọi API JDK mới.
- Runtime cũ có thư viện, native library, module và classloader phù hợp.
- Tính tương thích trong trường hợp reflection/dynamic loading, service providers, JNI.
- Các hành vi thay đổi giữa nhà cung cấp JDK hoặc phiên bản dữ liệu timezone/locale.
- Tính năng preview có thể được mang tùy ý về release cũ.
- Chất lượng hiệu năng, bảo mật hoặc việc còn nhận bản vá của runtime đích.
- Việc **chạy test trên JVM `N`** (compiler không tự khởi động JVM `N`).

Do đó, `--release` là hàng rào **biên dịch** quan trọng, chứ không phải giấy chứng nhận tương thích runtime cho toàn bộ hệ thống.

**Lưu ý module và API nội bộ:** `--release` chỉ cho phép API nền tảng đã được công bố/được hỗ trợ theo release; không thể dùng tùy chọn `--add-exports` để “mở rộng” tập API Java SE/JDK của bản target có module system trong chế độ `--release`. Với mã mới, tránh phụ thuộc các package nội bộ JDK để né kiểm soát phiên bản.

## 18. Đừng suy đoán “JDK mới nhất” luôn hỗ trợ target Java rất cũ

Java SE phát hành bản mới định kỳ. `javac` của mỗi bản chỉ giữ một tập có giới hạn các giá trị hỗ trợ cho `--source`, `--target` và `--release`. Số release được hỗ trợ **thay đổi giữa các JDK**.

Vì vậy, câu lệnh:

```bash
javac --release 10 OldExample.java
```

**Chỉ có thể được sử dụng nếu chính compiler đang chạy vẫn liệt kê release 10 là hợp lệ.** Trên một số JDK mới hơn, nó có thể không còn được chấp nhận. Giải pháp không phải đổi bừa sang `-source 10 -target 10` vì cách đó vừa có thể không được hỗ trợ, vừa không bảo vệ API.

Khi thật sự buộc phải duy trì một nền tảng cũ vì yêu cầu khách hàng:

- Sử dụng một **compiler/toolchain tương thích** với target đó.
- Khóa phiên bản môi trường build có kiểm soát, chú ý cập nhật bảo mật.
- Kiểm tra mức API/dependency theo runtime cần hỗ trợ.
- Chạy ít nhất smoke test/integration test trên runtime mục tiêu.
- Lập kế hoạch nâng cấp runtime và loại bỏ phụ thuộc không còn được bảo trì.

Với các dự án mới, nên chọn một phiên bản JDK **được duy trì cập nhật và được hệ sinh thái của dự án hỗ trợ**, thường là một bản LTS phù hợp. Đừng xem “JDK 10 vẫn đọc được bài học Java 10” là lý do để vận hành production bằng JDK 10.

## 19. Kiểm tra thông tin classfile và runtime trong CI

Có thể kiểm tra build bằng các lệnh:

```bash
java --version
javac --version
javac --help
javap -verbose com.example.Main
```

Ở dòng cuối, giả sử class `com.example.Main` đã biên dịch, classpath đang chứa nó. `javap -verbose` cho biết `major version` của class mà tool đọc.

Một ứng dụng Java đơn giản cũng có thể in thông tin runtime:

```java
public class RuntimeInfo {
    public static void main(String[] args) {
        System.out.println(
                "feature=" + Runtime.version().feature());
        System.out.println(
                "classFormat=" + System.getProperty("java.class.version"));
    }
}
```

Đoạn này có thể lưu thành `RuntimeInfo.java` và chạy trên JDK 17+:

```bash
javac --release 17 RuntimeInfo.java
java RuntimeInfo
```

**Output phụ thuộc JVM thực sự đang chạy.** Ví dụ với JVM Java 17 thì `feature=17` và `classFormat=61.0`; JVM Java 24 sẽ cho `feature=24` và `classFormat=68.0`. Thuộc tính `java.class.version` phản ánh **mức classfile được JVM hỗ trợ**, không phải major version của **mọi class trong ứng dụng**. Muốn xem một artifact cụ thể, hãy kiểm tra tệp bằng `javap -verbose`.

Đây là cách tốt để tìm nguyên nhân “CI dùng JDK A nhưng container production dùng JDK B” mà không trộn các loại phiên bản.

## 20. Gợi ý ma trận kiểm thử tính tương thích

Một dự án có thể đặt chính sách:

| Kiểm tra | Ví dụ với minimum runtime Java 17 | Mục đích |
| --- | --- | --- |
| Compile | Compiler JDK 21, `--release 17` | Giới hạn cú pháp/API/classfile |
| Unit tests | JVM Java 17 | Phát hiện lỗi chạy ở mức target |
| Integration tests | JVM Java 17 với dependencies production | Phát hiện lệch thư viện và cấu hình |
| Forward compatibility | JVM Java 21/25 nếu là platform sản phẩm hỗ trợ | Phát hiện thay đổi khi nâng runtime |
| Classfile inspection | `javap -verbose` trên class/JAR quan trọng | Kiểm tra major version thực tế |
| Build metadata | Log `java --version`, `javac --version`, toolchain | Tái hiện môi trường build |
| Runtime monitoring | Ghi JDK vendor/version của container server | Chẩn đoán sự cố triển khai |

**Không có một lệnh compiler nào thay thế toàn bộ các test này.** Ngay cả khi mọi class đều là major 61, vẫn có thể xảy ra lỗi khi runtime 17 tải một thư viện có API không tồn tại hoặc môi trường production thiếu module/native dependency.

Nếu ứng dụng chỉ hỗ trợ Java 21 trở lên, chọn `--release 21` và chạy test trên Java 21 phù hợp. Mục tiêu là **cấu hình trung thực với cam kết hỗ trợ**, không mặc định một con số thấp để “hỗ trợ được nhiều JVM” mà không thực sự kiểm chứng.

## 21. Những hiểu nhầm thường gặp

| Hiểu nhầm | Vì sao sai? | Cách sửa |
| --- | --- | --- |
| “`--target 17` nghĩa chỉ dùng Java 17 API.” | `--target` chỉ xác định classfile format | Dùng `--release 17` |
| “`--source 17` nghĩa mọi phương thức JDK đều có từ Java 17.” | Ngôn ngữ nguồn khác API | Kiểm soát API bằng `--release` |
| “Class major 55 chắc chắn chạy trên JVM Java 11.” | Có thể tham chiếu `String.indent`/API mới và lỗi khi link | Build bằng `--release 11` + test runtime 11 |
| “JDK compiler 21 thì chương trình bắt buộc cần JVM 21.” | Compiler 21 có thể tạo classfile target cũ | Cấu hình `--release` thích hợp |
| “JDK compiler 21 tự động dùng API 17 khi có `-target 17`.” | Có thể tham chiếu API mới trên boot modules của JDK 21 | Ưu tiên `--release 17` |
| “`record` chỉ là API thư viện.” | Record là tính năng ngôn ngữ được compiler nhận diện | Đặt language level phù hợp |
| “`List.copyOf` chỉ là cú pháp Java 10.” | Đó là phương thức API Java 10 | Kiểm tra API level |
| “`--release` sẽ hạ mọi JAR dependency về phiên bản cũ.” | Không transcompile dependency | Kiểm tra JAR riêng và chạy test |
| “JVM 17 có thể đọc classfile major 65 vì code chỉ dùng Java 17.” | Class format major 65 là Java 21 | Biên dịch lại với target17 hoặc nâng runtime |
| “Vừa `--release 17` vừa `--target 17` an toàn hơn.” | `javac` không cho kết hợp chúng | Chỉ dùng `--release 17` |
| “Mọi JDK mới đều có `--release 10`.” | Compiler chỉ hỗ trợ một số release cũ giới hạn | Xem `javac --help` |
| “Compiler qua là chắc chắn production chạy được.” | Chưa kiểm tra runtime/dependencies/OS | Test trên đúng JVM đích |
| “`java.class.version` là major của file class tôi vừa build.” | Nó phản ánh mức format của JVM hiện tại | Dùng `javap -verbose` cho artifact |
| “Chọn toolchain 21 là đủ để build tương thích 17.” | Toolchain chọn compiler, không tự hạ API | Kết hợp toolchain 21 + `--release 17` |
| “Java 10 là phiên bản nên dùng trong production mới.” | Java 10 không còn là runtime nhận bảo trì thông thường | Học tính năng còn dùng, triển khai trên JDK được hỗ trợ |

## 22. Bài tập tự kiểm tra

### Bài 1: hai đoạn code cần những mức nào?

```java
var names = java.util.List.copyOf(source);
```

**Đáp án:** cần cú pháp `var` Java 10+ và API `List.copyOf` Java 10+. Nếu đưa vào phương thức có `source` phù hợp, source ở Java 10+ mới được compiler chấp nhận; JVM đích phải hỗ trợ format và API tương ứng hoặc mới hơn.

### Bài 2: bản build với `-source 11 -target 11`

```java
class ApiCheck {
    static String render(String s) {
        return s.indent(2);
    }
}
```

Nếu dùng compiler JDK 17 với `-source 11 -target 11`, có thể compile không?

**Đáp án:** Có. Compiler có `String.indent` trên JDK 17, và lệnh chỉ kiểm soát source syntax/class target, nên việc compile có thể thành công thành major 55. Nếu chạy method trên JVM Java 11, thiếu `String.indent` nên có thể ném `NoSuchMethodError`. Dùng `--release 11` để phát hiện lỗi ngay khi build.

### Bài 3: record và API

Vì sao `record Point(int x) {}` thất bại với `--release 11`?

**Đáp án:** Do **ngôn ngữ/source level** Java 11 chưa có record như một tính năng chính thức, chứ không phải vì target Java 11 không đọc được classfile Java 17. `--release 17` chấp nhận syntax record và tạo major 61.

### Bài 4: compiler mới với runtime cũ

Một người đặt JDK 21 để compile, `--release 17`, sau đó thêm thư viện third-party yêu cầu Java 21. Có chắc runtime 17 chạy được không?

**Đáp án:** Không. `--release` không tái biên dịch hay hạ API/bytecode của dependency. Phải kiểm tra mức Java tối thiểu của thư viện và chạy test trên JVM Java 17.

### Bài 5: major version

Có một tệp `.class` với `major version: 65`. Nó tương ứng với Java nào? JVM 17 có đọc được không?

**Đáp án:** Major 65 là classfile Java **21**. JVM Java 17 chỉ hỗ trợ format tới major **61**, nên không đọc được classfile 65; nếu tải nó, có thể báo `UnsupportedClassVersionError`.

### Bài 6: ứng dụng muốn giữ API Java 17 nhưng dùng compiler JDK 24

Lệnh nào rõ ý hơn: `javac -source 17 -target 17 App.java` hay `javac --release 17 App.java`?

**Đáp án:** `javac --release 17 App.java`, vì nó giới hạn cả API nền tảng Java 17, không chỉ cú pháp và class format. Vẫn cần test production runtime.

## 23. Checklist quyết định phiên bản Java trong dự án

1. **Xác định runtime tối thiểu được hỗ trợ** theo yêu cầu khách hàng và bảo trì bảo mật.
2. **Chọn compiler/toolchain** có khả năng build với release đó.
3. **Đặt `--release N`** (Maven/Gradle tương ứng) thay vì chỉ đặt source/target.
4. **Kiểm tra `javac --help`** để biết compiler còn hỗ trợ release N không.
5. **Kiểm tra cú pháp**: source có dùng `var`, record, sealed class hoặc feature mới hơn N không?
6. **Kiểm tra API**: các method/class có `Since` nào? Có API Java mới hơn N không?
7. **Kiểm tra class major** của artifact sau build, không suy luận chỉ từ cấu hình IDE.
8. **Kiểm tra dependencies** và mức bytecode/API tối thiểu của từng thư viện.
9. **Chạy unit/integration tests trên JVM N thật**, không chỉ JDK build.
10. **Xác nhận JDK của container/production**, module, native library và JVM flags.
11. **Không lạm dụng preview features** nếu muốn hỗ trợ nhiều bản runtime.
12. **Theo dõi nâng cấp JDK** và bảo trì an toàn, không tiếp tục giữ runtime đã ngừng cập nhật chỉ vì cấu hình cũ.
13. **Ghi nhận riêng** language/API/bytecode/runtime trong tài liệu build để tránh hiểu nhầm các con số.
14. **Test lại khi nâng compiler**: compiler mới có thể thay cảnh báo/behavior, nhưng release target và runtime support phải giữ đúng chính sách.

## Kết luận

Trong Java hiện đại, **phiên bản ngôn ngữ**, **phiên bản API được phép tham chiếu** và **phiên bản JVM/classfile đích** là ba khái niệm **khác nhau**, dù chúng thường mang cùng con số release.

- `--source N` giới hạn **cú pháp ngôn ngữ**.
- `--target N` quyết định **định dạng bytecode**.
- **`--release N` kiểm soát cả cú pháp, API Java SE/JDK được hỗ trợ và classfile target**, nên là lựa chọn ưu tiên khi cần bảo đảm mức tương thích nền tảng.

Trường hợp `String.indent` chỉ rõ nguy cơ: compiler mới có thể tạo class major **55** với `-source 11 -target 11` nhưng vẫn dùng **API Java 12**, dẫn đến lỗi runtime Java 11. `--release 11` phát hiện điều đó sớm.

Sau cùng, `--release` không kiểm soát toàn bộ thư viện phụ thuộc hay chạy thay bạn trên JVM đích. **Tương thích thật** cần build đúng target, kiểm tra dependencies và **kiểm thử trên đúng runtime được sản phẩm cam kết**.

## Tài liệu tham khảo chính thức

- [Oracle Java SE 27 — `javac` command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html): `--release`, `--source`, `--target`, API được phép dùng, hạn chế các release có hỗ trợ và Java Compiler API.
- [Java Virtual Machine Specification, Java SE 27 — classfile major versions](https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-1.html): bảng các phiên bản Java và major classfile 54, 55, 61, 65, 69, 71.
- [Java SE 17 — `String.indent(int)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#indent(int)): API được giới thiệu từ Java 12, dùng để minh họa khác biệt giữa language/target/API.
- [Java SE 21 — `Thread.ofVirtual()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html#ofVirtual()): API từ Java 21, không thể gọi trong build `--release 17`.
- [Maven — Guide to Targeting a Java Version](https://maven.apache.org/guides/mini/guide-java-target.html): cấu hình `maven.compiler.release` và khác biệt với source/target.
- [Gradle — Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html): sự khác nhau giữa compiler toolchain, `options.release` và source/target compatibility.
- [Oracle Java SE 27 — Preparing for Migration](https://docs.oracle.com/en/java/javase/27/migrate/preparing-migration.html): khuyến nghị `--release` khi build cho bản nền tảng cũ hơn.
- [OpenJDK — JEP 247, Compile for Older Platform Versions](https://openjdk.org/jeps/247): cơ sở thiết kế của `javac --release`.

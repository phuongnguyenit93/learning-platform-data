# Kiểm thử `--release`, preview và các phiên bản JDK hỗ trợ trong Java

## 1. Vấn đề cần giải quyết

Một dự án có thể được **biên dịch bằng JDK 17** nhưng hứa hỗ trợ **runtime Java 11**; một dự án khác dùng tính năng **preview của Java 17** nên chỉ chạy với một cấu hình rất cụ thể. Nếu kiểm thử chỉ chạy `javac` một lần trên máy lập trình viên, ta không biết lời hứa tương thích ấy có đúng hay không.

Bài này tập trung vào ba câu hỏi phải kiểm chứng riêng:

1. **Biên dịch cho phiên bản Java đích:** `javac --release N` có từ chối cú pháp/API mới hơn Java N và sinh class file đúng mức không?
2. **Preview:** mã phụ thuộc tính năng preview có được biên dịch bằng đúng JDK phát hành tính năng đó, với `--enable-preview`, và chạy với đúng runtime/flag không?
3. **Ma trận JDK hỗ trợ:** artifact có thật sự chạy và vượt qua test trên **những phiên bản JDK mà dự án tuyên bố hỗ trợ** không?

Hai kết luận thường bị nhầm lẫn:

- “Build trên JDK 17 với `--release 11` thành công” **không chứng minh** đã chạy thử chương trình trên JDK 11.
- “Chạy được preview trên JDK 17” **không chứng minh** class preview đó chạy được trên JDK 21 hoặc trên bất kỳ JDK mới hơn nào.

Muốn có bằng chứng tốt, cần kết hợp **compile test**, **runtime test**, **negative test** (kiểm tra trường hợp phải bị từ chối) và thông tin toolchain có thể tái lập.

## 2. Phân biệt bốn số phiên bản

| Khái niệm | Ý nghĩa | Cách kiểm tra |
|---|---|---|
| **JDK chạy compiler** | Bộ `javac` thực tế đang dùng, ví dụ JDK 17 | `javac -version` và đường dẫn executable |
| **`--release N`** | Mức ngôn ngữ, API Java SE chuẩn và class file mà compiler phải nhắm đến | `javac --release N`, negative compile test |
| **JDK chạy chương trình** | JVM thực tế nạp class và thực hiện mã | `java -version`, chạy smoke/integration tests |
| **JDK chạy build tool** | JVM chạy Gradle/Maven hoặc daemon, có thể khác compiler và JVM của test | `./gradlew -version`, `mvn -version`, cấu hình toolchain |

Ví dụ: Gradle daemon có thể chạy trên JDK 21, task JavaCompile dùng toolchain JDK 17 với `options.release = 11`, còn một task `Test` chuyên biệt dùng Java launcher 11. Đây là **bốn vai trò**, dù một số có thể trùng phiên bản trong dự án đơn giản.

**Thế nào là “hỗ trợ JDK 11”?** Cần định nghĩa trước: dự án phải compile cho Java 11, chạy unit/integration test trên JDK 11, và có phụ thuộc/ứng dụng tương thích; hay chỉ cần *thư viện* sinh bytecode có thể nạp trên Java 11? Mục tiêu kiểm thử khác nhau theo cam kết sản phẩm.

## 3. `--release` thực sự bảo đảm điều gì?

`javac --release N` yêu cầu compiler tương thích với phiên bản Java SE N trong ba chiều chính:

- **Quy tắc ngôn ngữ:** từ chối cú pháp hoặc tính năng Java xuất hiện sau release N.
- **API Java SE khả dụng:** ngăn source gọi nhầm API chuẩn mới hơn Java N, ngay cả khi đang dùng compiler JDK mới.
- **Mức class file:** sinh bytecode theo định dạng cho release N.

Ví dụ chạy `javac` JDK 17 với `--release 11` là một cách **cross-compilation** cho Java 11. Nó không yêu cầu máy có trình biên dịch JDK 11, miễn compiler hiện tại hỗ trợ release 11.

Tuy nhiên, `--release` **không** tự chứng minh:

- Thư viện ngoài (third-party dependencies) và native library có hỗ trợ Java 11.
- Các đường runtime có phản xạ, service loading, JNI, network hoặc phụ thuộc hệ điều hành vận hành đúng.
- Đầu ra được chạy thử trên JVM 11.
- Một release Java bất kỳ được mọi phiên bản compiler hỗ trợ. `javac` chỉ hỗ trợ một tập release, có thể loại bỏ mục tiêu quá cũ và không thể biên dịch cho release **mới hơn compiler**.

Hãy chạy:

```bash
javac -version
javac --help
```

Kiểm tra dòng **Supported releases** trong output `javac --help` của chính JDK sử dụng, thay vì giả định mọi JDK đều nhận `--release 8`, `11`, `17`, `21`.

### 3.1. Vì sao `-source` / `-target` chưa đủ?

`-source 8` kiểm tra ngữ pháp Java 8; `-target 8` yêu cầu class file tương ứng. Khi dùng compiler mới và **không** cấu hình bootclasspath phù hợp, hai cờ này không chặn chắc chắn việc gọi API chuẩn chỉ có từ Java mới.

Ví dụ sau dùng cú pháp Java 8 bình thường nhưng phương thức `String.isBlank()` chỉ có từ Java 11:

**Tệp `ApiGate.java`:**

```java
public class ApiGate {
    public static void main(String[] args) {
        System.out.println(" ".isBlank());
    }
}
```

Trên **JDK 17**, chạy tại thư mục chứa file:

```bash
javac --release 8 -d out8 ApiGate.java
```

**Kỳ vọng:** compilation **thất bại** vì API `String.isBlank()` không có trong Java SE 8. Không kiểm tra bằng cách buộc stderr phải đúng nguyên văn câu tiếng Anh của compiler; hãy kiểm tra trạng thái khác 0 và nguyên nhân tương ứng.

Vẫn trên JDK 17, chạy:

```bash
javac --release 11 -d out11 ApiGate.java
java -cp out11 ApiGate
```

**Stdout của lệnh `java`:**

```text
true
```

Nếu biên dịch bằng `-source 8 -target 8` **trên JDK 17** mà không dùng `--release` hoặc bootclasspath tương ứng, compiler có thể chấp nhận lời gọi `isBlank()` dù target bytecode là Java 8. Chạy bytecode đó trên Java 8 sẽ không tìm thấy method ở runtime, thường dẫn đến `NoSuchMethodError`. Đây là ví dụ cụ thể vì sao phải kiểm thử **API gate**, không chỉ đọc major version của class file.

Cũng cần kiểm tra **cú pháp**: file khai báo `record Item(String name) {}` hợp lệ với Java 17, nhưng phải bị từ chối bởi `--release 11` vì records chỉ thành tính năng chính thức ở Java 16. `--release` bảo vệ cả ngôn ngữ lẫn API chuẩn.

### 3.2. Không thể gộp các compiler flags tùy ý

`--release` không thể dùng cùng `-source` / `-target` trong một lời gọi `javac` thông thường: đây là những cách đặt mức biên dịch cạnh tranh nhau. Nó cũng hạn chế một số tùy chọn can thiệp vào API của hệ thống module, chẳng hạn xuất package không được export của module hệ thống trong một số trường hợp. Không nên “vá” lỗi biên dịch dưới `--release` bằng cách mở quyền tới JDK internal APIs.

Nếu cần compiler mới nhắm runtime cũ, ưu tiên **toolchain/compiler xác định + `--release N`** và để build tool tạo tham số đúng.

## 4. Kiểm thử bằng command line: positive và negative case

Một thử nghiệm tốt không chỉ kiểm tra source hợp lệ có thể compile, mà còn kiểm tra compiler **từ chối đúng** source vượt quá hợp đồng.

| Case | JDK compiler | Flags | Fixture | Kỳ vọng |
|---|---:|---|---|---|
| A | 17 | `--release 8` | `ApiGate.java` gọi `String.isBlank()` | **FAIL**, API chưa có ở Java 8 |
| B | 17 | `--release 11` | Cùng fixture | **PASS** |
| C | 17 | `--release 11` | File dùng `record` | **FAIL**, cú pháp chưa có ở Java 11 |
| D | 17 | `--release 17` | File dùng `record` | **PASS** |
| E | 17 | `--release 21` | File Java hợp lệ bất kỳ | **FAIL**, compiler 17 không hỗ trợ tương lai 21 |

Case E thất bại vì **cấu hình release không hợp lệ**, khác với lỗi cú pháp của fixture. Bộ test phải phân biệt **không có toolchain phù hợp** và **source bị từ chối đúng dự kiến**.

### 4.1. POSIX shell kiểm tra trạng thái thay vì text

Trên macOS/Linux với JDK 17, khi fixture `ApiGate.java` tồn tại:

```bash
if javac --release 8 -d out8 ApiGate.java; then
    echo "FAIL: Java 8 unexpectedly accepted the API"
    exit 1
else
    echo "PASS: Java 8 target rejected the API"
fi

javac --release 11 -d out11 ApiGate.java
java -cp out11 ApiGate
```

**Stdout do các lệnh/script tạo**, nếu case đúng:

```text
PASS: Java 8 target rejected the API
true
```

`javac` vẫn có thể in diagnostics lên stderr. Dù script minh họa nhận mã khác 0 từ case đầu, trong **test runner thật** cần đảm bảo executable `javac` chạy được và fixture tồn tại; nếu không, lỗi “command not found” cũng khiến nhánh `else` chạy và tạo false positive.

Ở PowerShell, đọc `$LASTEXITCODE` **ngay sau `javac`**, rồi so với 0. Tránh buộc test dựa trên câu `cannot find symbol` hoặc đường dẫn tệp cụ thể.

### 4.2. Đọc major version class file

Có thể xem class file được sinh bởi `--release 11`:

```bash
javap -verbose out11/ApiGate.class
```

Tìm `major version: 55`. Một số mốc phổ biến:

| Java release | Major version của class file bình thường |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Mốc này kiểm tra **định dạng bytecode**, không thể thay thế kiểm tra API compatibility. Như ví dụ `-source/-target`, class file version phù hợp không có nghĩa tất cả method/library mà nó gọi đều tồn tại trên JVM cũ.

## 5. Java 17+: tự động kiểm thử API gate bằng Java Compiler API

Dùng `javax.tools.JavaCompiler` và `DiagnosticCollector` giúp test compilation theo **trạng thái và diagnostic có cấu trúc**. Ta có thể kiểm thử hai target `--release 8` và `--release 11` từ cùng một JDK 17 mà không parse toàn bộ stderr.

**Tệp `ReleaseMatrixCheck.java` — chương trình Java 17 chạy độc lập:**

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class ReleaseMatrixCheck {
    public static void main(String[] args) throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Run with a full JDK");
        }

        Path root = Files.createTempDirectory("release-matrix-");
        Path source = root.resolve("ApiGate.java");

        Files.writeString(source,
                "public class ApiGate {"
                + " public static void main(String[] args) {"
                + " System.out.println(\" \".isBlank());"
                + " }"
                + "}");

        boolean on8 = compile(compiler, source, root, "8");
        boolean on11 = compile(compiler, source, root, "11");

        if (on8 || !on11) {
            throw new AssertionError(
                    "Expected --release 8 to reject and 11 to accept");
        }

        System.out.println("release 8 accepted: " + on8);
        System.out.println("release 11 accepted: " + on11);
    }

    private static boolean compile(
            JavaCompiler compiler,
            Path source,
            Path root,
            String release) throws IOException {

        Path out = Files.createDirectories(
                root.resolve("classes-" + release));
        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager files =
                     compiler.getStandardFileManager(
                             diagnostics, null, null)) {

            Iterable<? extends JavaFileObject> units =
                    files.getJavaFileObjects(source.toFile());

            Boolean success = compiler.getTask(
                    null,
                    files,
                    diagnostics,
                    List.of("--release", release,
                            "-d", out.toString(),
                            "-proc:none"),
                    null,
                    units
            ).call();

            boolean hasError = diagnostics.getDiagnostics()
                    .stream()
                    .anyMatch(d -> d.getKind()
                            == Diagnostic.Kind.ERROR);

            if (Boolean.FALSE.equals(success) && !hasError) {
                throw new AssertionError(
                        "Compilation failed without ERROR diagnostic");
            }
            return Boolean.TRUE.equals(success);
        }
    }
}
```

Biên dịch và chạy bằng **JDK 17** (hoặc JDK mới hơn còn hỗ trợ cả hai release 8 và 11; kiểm tra `javac --help`):

```bash
javac ReleaseMatrixCheck.java
java ReleaseMatrixCheck
```

**Stdout khi chạy với JDK 17:**

```text
release 8 accepted: false
release 11 accepted: true
```

Chương trình tạo source và output tạm trong thư mục hệ thống để chạy hai lần compilation độc lập. Việc nó không xóa tự động thư mục tạm **không ảnh hưởng logic test**, nhưng ở test suite thực tế nên bổ sung cleanup an toàn (ví dụ JUnit `@TempDir`) để tránh tích lũy file khi chạy thường xuyên.

Cần phân biệt:

- Trường hợp `--release 8` thất bại vì `isBlank()` không thuộc API Java 8.
- Trường hợp `--release 11` thành công.
- Cả hai chỉ kiểm tra **biên dịch**; chưa chạy class bằng runtime JDK 8/11.
- Ví dụ **không** gọi trực tiếp executable `javac` bằng đường dẫn mà dùng system compiler của JDK đang chạy chương trình. Phải cố định JDK chạy `ReleaseMatrixCheck` để kết quả tái lập.

Không nên dùng một test như trên để tuyên bố “hỗ trợ tất cả phiên bản JDK”; nó là một phần nhỏ của bộ kiểm thử tương thích.

## 6. Preview là gì và vì sao đặc biệt?

Java có một số tính năng ngôn ngữ, VM hoặc API được đưa ra dưới dạng **preview** để người dùng thử nghiệm trước khi chúng được sửa đổi, chuẩn hóa hoặc loại bỏ. Preview được chỉ định **theo từng Java SE release**. Một tính năng có thể có cú pháp khác giữa các vòng preview; khi được chuẩn hóa, cách bật và quy tắc tương thích có thể thay đổi.

Điểm cần nhớ:

1. Tính năng preview không mặc nhiên được bật như tính năng chính thức.
2. Khi biên dịch source dùng **preview language feature**, cần `--enable-preview` **và** `--release N` hoặc `-source N` với N là **phiên bản hiện tại của chính compiler**.
3. Khi chạy class file phụ thuộc preview của release N, cần JVM **đúng Java SE N** cùng `java --enable-preview`.
4. Class preview với minor version **65535** gắn với major version của release đó. JVM khác release **không được** nạp class phụ thuộc preview ấy chỉ bằng cách thêm `--enable-preview`.
5. Một tính năng đã thành chính thức ở bản Java mới không làm preview class cũ tự động chuyển thành class ổn định; cần biên dịch lại source theo đặc tả/phiên bản mục tiêu.

**Không hiểu `--enable-preview` là cờ “bật mọi tính năng mới của các bản Java khác”.** Ví dụ một `javac` JDK 17 không thể dùng `--enable-preview --release 21` để hiểu cú pháp Java 21; nó cũng không thể dùng preview của release 17 khi biên dịch target `--release 11`.

### 6.1. Ví dụ preview thực tế trong Java 17

**Pattern matching for switch** là tính năng preview trong **Java 17** (JEP 406). Đoạn dưới đây phải chạy với **JDK 17**, không tự giả định phiên bản compiler khác còn xem cú pháp đó là preview theo cùng quy tắc.

**Tệp `PreviewSwitch.java`:**

```java
public class PreviewSwitch {
    static String describe(Object value) {
        return switch (value) {
            case Integer number -> "int: " + number;
            case String text -> "string: " + text;
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe(7));
    }
}
```

**Trên JDK 17**, biên dịch và chạy:

```bash
javac --enable-preview --release 17 -d out-preview PreviewSwitch.java
java --enable-preview -cp out-preview PreviewSwitch
```

**Stdout mong đợi:**

```text
string: Java
int: 7
```

Compiler có thể in note cảnh báo về preview trên **stderr**, nhưng không cần so nguyên văn lời nhắn đó khi test chỉ muốn chứng minh code hoạt động.

Hai negative test quan trọng:

```bash
# Trên JDK 17: thiếu --enable-preview, kỳ vọng compilation FAIL.
javac --release 17 -d out-no-preview PreviewSwitch.java

# Trên JDK 17: preview không dùng để nhắm release 11, kỳ vọng FAIL.
javac --enable-preview --release 11 -d out-old-preview PreviewSwitch.java
```

Các dòng comment mô tả **kỳ vọng**, không phải phần của cú pháp `javac`. Trước khi chạy từng thử nghiệm, chắc chắn `javac -version` trả đúng 17. Với compiler mới hơn, pattern switch có thể đã là tính năng chính thức và test “thiếu preview phải fail” không còn mang nghĩa như trên. **Negative test preview phải gắn với release cụ thể.**

### 6.2. Kiểm thử lúc chạy

Nếu đã biên dịch `PreviewSwitch.class` bằng JDK 17 với preview:

```bash
# JDK 17: thiếu runtime flag, kỳ vọng chương trình không nạp được class.
java -cp out-preview PreviewSwitch

# JDK 17: bật flag, kỳ vọng chạy thành công.
java --enable-preview -cp out-preview PreviewSwitch
```

Nếu cố chạy class preview của Java 17 bằng **JDK 21**, kể cả `java --enable-preview` cũng không biến class preview JDK 17 thành artifact Java 21. Nếu muốn dùng Java 21, hãy **biên dịch lại nguồn** bằng compiler Java 21 và kiểm thử theo đặc tả của Java 21.

Đọc phiên bản class:

```bash
javap -verbose out-preview/PreviewSwitch.class
```

Với class phụ thuộc preview của Java 17, mong đợi `major version: 61` và `minor version: 65535`. Class không dùng preview có thể có minor version 0 dù compiler chạy với `--enable-preview`; không nên kết luận cứ thêm flag thì mọi class đều phải là preview class.

## 7. Thiết kế ma trận JDK: compile target khác runtime target

Ma trận nên bắt đầu từ **chính sách hỗ trợ của dự án**. Ví dụ thư viện tuyên bố chạy trên Java **11, 17 và 21** nhưng compile target Java **11**:

| Lượt | Compiler JDK | `--release` | Runtime JDK | Điều chứng minh |
|---|---:|---:|---:|---|
| 1 | 17 | 11 | 11 | Biên dịch tương thích Java 11 và chạy/test trên JVM cũ nhất được hỗ trợ |
| 2 | 17 | 11 | 17 | Cùng artifact vận hành trên runtime 17 |
| 3 | 17 | 11 | 21 | Cùng artifact vận hành trên runtime 21 |
| 4 (bổ sung) | 21 | 11 | 11 | Compiler mới vẫn tạo đầu ra tương thích với baseline 11 |
| 5 (bổ sung) | 21 | 11 | 21 | Kiểm thử tương tác toolchain/compiler mới với runtime mới |

Ma trận là **ví dụ**, không phải tuyên bố tất cả dự án đều phải hỗ trợ ba bản này. Nếu JDK compiler không còn hỗ trợ release mục tiêu, phải dùng toolchain phù hợp hoặc thay đổi chính sách có chủ đích.

**Điểm then chốt:** Hãy build **một artifact theo mức tương thích thấp nhất**, rồi chạy **cùng artifact** trên các JVM runtime cần hỗ trợ. Nếu build lại riêng trên mỗi JDK với target ngầm định khác nhau, bạn đang kiểm tra các artifact khác nhau và có thể bỏ sót lỗi tương thích của bản phân phối thực tế.

Một lớp Java 21 thông thường có major version 65 và sẽ không chạy trên JVM 17 (major tối đa 61), ngay cả khi mã nguồn không dùng API Java 21. Đó là lý do **runtime test không thay thế thiết lập release đúng**, và compile target cũng không thay thế runtime test.

### 7.1. Checklist mỗi ô trong ma trận

Với từng cặp compiler/runtime được chọn, ghi lại:

- Phiên bản và vendor/compiler thực tế (`javac -version`, `java -version`), không chỉ `JAVA_HOME` dự định.
- Tập source, `--release`, compiler arguments, dependency versions và artifact hash.
- Trạng thái compile, số lỗi và diagnostic cần thiết.
- Exit code của chương trình/test runner, số test pass/fail/skip và các lỗi liên kết/runtime.
- Preview có dùng không; nếu có, cờ của cả compiler **và** runtime, cùng release chính xác.
- Hệ điều hành và kiến trúc nếu dự án có JNI, file encoding hoặc các phụ thuộc OS đặc thù.

Nếu có code path phụ thuộc Java version (`Runtime.version()`, multi-release JAR, service provider riêng), test cần kiểm tra **hành vi** trên mỗi JVM, chứ không chỉ “main method exit 0”.

### 7.2. Những ca lỗi cần có

| Lỗi mong đợi | Bài test |
|---|---|
| Gọi API chuẩn mới hơn target | `--release` cũ phải từ chối |
| Sử dụng cú pháp mới hơn target | `--release` cũ phải từ chối |
| Compiler quá cũ so với target | Báo lỗi cấu hình/toolchain; không tính là source language failure |
| Runtime cũ hơn major version | Runtime phải từ chối class mới |
| Runtime thiếu preview flag | Runtime phải từ chối class preview của chính release |
| Dùng class preview của release N trên JVM M khác N | Runtime phải từ chối class phụ thuộc preview |
| Runtime mới và API bên ngoài không tương thích | Test/integration phải phát hiện lỗi runtime, không suy chỉ từ `--release` |
| Build tool chạy đúng nhưng test chạy sai JDK | Kiểm tra Java launcher của task và log toolchain |

**Mỗi expected-failure nên được định nghĩa là “test pass khi compiler/runtime từ chối đúng lý do”.** Một lỗi do file không tồn tại, Java executable không khởi động hoặc dependency cache thiếu phải được phân loại thành *hạ tầng*, không phải pass.

## 8. Tích hợp Gradle: cố định compiler và release

Với Gradle Java plugin, có thể dùng toolchain để chọn JDK biên dịch, kết hợp `options.release` để đặt mức tương thích.

**Fragment `build.gradle` (Groovy DSL):**

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 11
}
```

Cấu hình này yêu cầu compiler JDK 17 nhưng tạo classes nhắm Java 11. Nó **chưa cấu hình test chạy bằng Java 11**: test task mặc định có thể dùng Java launcher của toolchain JDK 17.

Các lệnh quan sát:

```bash
./gradlew -version
./gradlew javaToolchains
./gradlew clean test --info
```

Windows dùng `gradlew.bat`. `javaToolchains` cung cấp thông tin JDK được Gradle phát hiện; `--info` hỗ trợ quan sát công cụ được chọn và task nào chạy.

Nếu phải chạy test trên JDK 11, có thể bổ sung task Java Test dùng launcher 11:

```groovy
// Fragment mở rộng build.gradle của dự án có test source set.
// Với JUnit Jupiter, cần dependencies phù hợp và useJUnitPlatform().
tasks.register('testOn11', Test) {
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(11)
    }
    useJUnitPlatform()
}
```

Đây là **cấu hình minh họa**; để chạy thật phải có JDK 11 khả dụng với Gradle toolchains và dependency JUnit/test phù hợp. Nếu library trong test runtime yêu cầu Java 17, task trên vẫn có thể fail dù lớp của ứng dụng đặt `--release 11`. Đó là một lỗi tương thích hữu ích được ma trận runtime phát hiện.

### 8.1. Gradle và preview

Khi chủ đích sử dụng preview **trên JDK 17**, compile task và test JVM đều cần cờ tương ứng:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.compilerArgs.add('--enable-preview')
}

tasks.withType(Test).configureEach {
    jvmArgs '--enable-preview'
}
```

Nếu dự án chạy qua task `JavaExec` hoặc đóng gói JAR để người dùng chạy từ terminal, runtime đó cũng phải có `--enable-preview`. Chỉ bật trên `Test` không làm JAR khi phát hành tự biết bật preview.

Nếu dự án cần baseline Java 11, không đặt `options.release = 11` rồi bật preview JDK 17. Hãy tách module/nhánh thử nghiệm preview khỏi artifact được hứa hỗ trợ JDK 11.

### 8.2. Phân biệt JVM chạy Gradle và JDK của toolchain

`./gradlew -version` hiển thị môi trường chạy Gradle, nhưng **không luôn là compiler của `compileJava`** khi toolchain đã cấu hình. Nên kiểm tra `javaToolchains` và task `--info`. Khi build thất bại vì JDK toolchain chưa có, đừng đổi `--release` để ép qua: cần cài/cấu hình toolchain hợp lệ hoặc chính sách provision phù hợp.

Gradle có ma trận phiên bản Gradle ↔ JDK: JDK có thể được hỗ trợ cho toolchain compilation nhưng **chưa được hỗ trợ để chạy chính Gradle** ở một version cụ thể. Khi nâng JDK, kiểm tra ma trận tương thích của phiên bản Gradle Wrapper đang dùng.

## 9. Tích hợp Maven: target release và preview

Với Maven Compiler Plugin, có thể chỉ định release trong `pom.xml`. Ví dụ **fragment dành cho Maven 3 và Compiler Plugin 3.x**:

```xml
<properties>
    <maven.compiler.release>11</maven.compiler.release>
</properties>
```

Maven 3 plugin hỗ trợ tùy chọn `release`, nhưng hành vi cụ thể có thể phụ thuộc phiên bản compiler plugin và JDK. Maven Compiler Plugin 3.13.0+ còn có cơ chế chuyển `release` thành `source/target` khi chạy compiler JDK 8; **chuyển đổi đó không bảo đảm API gate chặt như `javac --release` thực sự trên JDK 9+**. Với bài kiểm thử này, hãy ưu tiên JDK mới có `--release` native.

Kiểm tra môi trường:

```bash
mvn -version
mvn clean test
```

`mvn -version` thường báo JDK chạy Maven. Để kiểm tra JDK dùng biên dịch khi có toolchains/plugin cấu hình đặc biệt, xem compiler plugin output và cấu hình thực tế. Maven reactor hay surefire vẫn cần môi trường JVM đúng để kiểm thử runtime hỗ trợ.

### 9.1. Maven và preview

Maven Compiler Plugin 3.x có `enablePreview` (từ 3.10.1), ví dụ với JDK 17:

```xml
<!-- Fragment cấu hình trong pom.xml, chưa phải POM hoàn chỉnh. -->
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <maven.compiler.enablePreview>true</maven.compiler.enablePreview>
</properties>
```

**Compiler flag không tự bật flag ở JVM chạy test.** Với Maven Surefire cần cấu hình `argLine` phù hợp, ví dụ:

```xml
<!-- Fragment thuộc cấu hình maven-surefire-plugin. -->
<configuration>
    <argLine>--enable-preview</argLine>
</configuration>
```

Nếu dự án đã dùng `argLine` cho JaCoCo hay các JVM arguments khác, phải **kết hợp** cấu hình hiện có thay vì ghi đè. Preview khi chạy ứng dụng ngoài Surefire cũng cần truyền cho `java`.

Maven 4/Compiler Plugin 4.x có thay đổi về cách khai báo sources và targetVersion, nên không sao chép máy móc cấu hình Maven 3 sang mọi dự án. Khi cần chính xác, đối chiếu documentation của phiên bản plugin đang sử dụng.

## 10. Tổ chức kiểm thử CI thực tế

Đối với dự án yêu cầu runtime Java 11/17/21 và sản phẩm nhắm `--release 11`, pipeline có thể chia thành:

**A. Kiểm tra compiler contract.** Chạy fixture API gate bằng compiler đã khóa (ví dụ JDK 17), xác minh Java 8 bị từ chối còn Java 11 được chấp nhận. Kiểm tra class major version và chạy unit tests gốc.

**B. Build artifact một lần.** Tạo JAR với `--release 11`, lưu artifact và fingerprint/hash. Nếu cần build reproducibility, khóa plugin/dependencies và bảo đảm input ổn định.

**C. Runtime matrix.** Cùng artifact chạy smoke/integration tests trên JVM 11, 17 và 21 (các JDK có trong cam kết). Không biên dịch lại thành những artifact khác nhau cho mỗi runtime rồi coi đó là cùng một kiểm thử.

**D. Compiler matrix bổ sung.** Có thể chạy lại compile source với JDK 21 `--release 11` để phát hiện cảnh báo, processor hoặc biến đổi compiler khi nâng toolchain. Ghi rõ đây là một **artifact/compile job khác** với runtime matrix ở bước C.

**E. Preview lane riêng.** Nếu dự án có nhánh/module thử nghiệm preview, ghim exact JDK release, bật flags, kiểm tra cả trường hợp thiếu flag và không tuyên bố portability sang JDK khác cho preview class file.

Một bảng kết quả CI dễ đọc:

| Job | Compiler | Target | Runtime | Kỳ vọng |
|---|---|---|---|---|
| `compat-compile` | JDK 17 | 11 | — | PASS, bytecode major 55 |
| `api-negative` | JDK 17 | 8 | — | Expected FAIL cho fixture API mới |
| `runtime-11` | artifact đã build | 11 | 11 | PASS |
| `runtime-17` | cùng artifact | 11 | 17 | PASS |
| `runtime-21` | cùng artifact | 11 | 21 | PASS |
| `preview-17` | JDK 17 | 17 + preview | 17 + preview | PASS |
| `preview-no-flag` | JDK 17 | 17 + preview | 17 không bật preview | Expected runtime FAIL |

Nếu không có đủ JDK được cài đặt ở runner, nên dùng matrix/container/toolchain để cấp đúng phiên bản, thay vì im lặng bỏ qua một phần ma trận và tuyên bố coverage đầy đủ.

### 10.1. Phân biệt compatibility với support policy

Một class file Java 11 có thể được JVM mới hơn nạp được theo quy tắc tương thích ngược của JVM, nhưng sản phẩm có thể vẫn thất bại do dependency, APIs bị thay đổi, lỗi module access, thư viện native hay behavior khác nhau. Ngược lại, một dependency cần Java 17 làm cho ứng dụng **không** hỗ trợ JDK 11 dù mã nguồn của chính ứng dụng compile với `--release 11`.

**Cam kết hỗ trợ** cần được xác minh bằng test thật trên **toàn bộ runtime mục tiêu** và bằng phiên bản dependency/distribution thực tế, không suy chỉ từ class major version.

## 11. Cách xác minh failure đúng nguyên nhân

Có ba loại thất bại cần phân biệt:

| Loại | Ví dụ | Cách xác nhận |
|---|---|---|
| **Source bị từ chối đúng** | `String.isBlank()` với `--release 8` | Compiler đã chạy, source hợp lệ làm fixture, diagnostic `ERROR` phù hợp |
| **Cấu hình/toolchain sai** | JDK 17 nhận `--release 21`, thiếu JDK 11 launcher | Phân loại thành infrastructure/config failure; không chấm pass negative source test |
| **Runtime không tương thích** | Chạy class major 65 trên JVM 17 hoặc thiếu preview flag | Artifact, Java launcher, exit code và exception type phù hợp được ghi nhận |

Đừng kiểm thử bằng cách so nguyên văn câu `invalid source release`, `UnsupportedClassVersionError: ...` hoặc toàn bộ stderr. Câu chữ và định dạng khác nhau theo JDK, vendor, locale. Có thể assert **trạng thái** và, khi test thực sự cần, **loại exception/diagnostic** hoặc phần thông tin có cấu trúc.

Các lỗi thường thấy:

- **`UnsupportedClassVersionError`:** JVM nhận class file có version không hỗ trợ hoặc class preview không đúng điều kiện nạp. Cần kiểm tra major/minor và JVM thật.
- **`NoSuchMethodError` / `NoClassDefFoundError`:** có thể do API runtime/dependency không phù hợp dù class file nạp được.
- **`invalid source release` / `release version ... not supported`:** compiler không nhận target release; cần kiểm tra compiler thật, không suy source có lỗi.
- **Preview feature disabled:** source/bytecode phụ thuộc preview nhưng compiler hoặc runtime thiếu cờ thích hợp.

Trước khi kết luận một bug ngôn ngữ, xác nhận `java` và `javac` cùng đường dẫn toolchain đúng dự kiến; trên máy có nhiều JDK, chúng hoàn toàn có thể đến từ các installation khác nhau.

## 12. Bài tập thực hành

### Bài 1 — API boundary

Dùng `ApiGate.java` ở mục 3, chạy `javac --release 8`, `--release 11` và `--release 17` bằng compiler JDK 17. Ghi lại pass/fail, class major version và diagnostic chính.

**Đáp án kỳ vọng:** `--release 8` FAIL; 11 và 17 PASS; class compile cho 11 có major 55, cho 17 major 61. Không nhầm fail vì thiếu file hay gọi sai executable với expected API rejection.

### Bài 2 — Syntax boundary

Tạo `Item.java`:

```java
public record Item(String name) {
}
```

Biên dịch dưới `--release 11` và `--release 17` bằng compiler JDK 17. Vì sao khác nhau?

**Đáp án kỳ vọng:** Java 11 không có record như tính năng ngôn ngữ chính thức nên bị từ chối; Java 17 hỗ trợ record chính thức. Đây là rào cú pháp, khác rào API như `String.isBlank()`.

### Bài 3 — Preview lane

Dùng `PreviewSwitch.java` với JDK 17. Thử (1) compile không preview, (2) compile có preview và chạy không flag, (3) compile và chạy có flag, (4) thử dùng compiler JDK 17 với `--enable-preview --release 11`.

**Đáp án kỳ vọng:** (1) FAIL, (2) runtime FAIL, (3) PASS và stdout như mục 6, (4) FAIL vì preview JDK 17 không thể target Java 11.

### Bài 4 — Runtime matrix

Thư viện `utils.jar` được compile JDK 17 với `--release 11`. Team chạy unit test bằng JDK 17 và tuyên bố hỗ trợ Java 11. Bằng chứng nào còn thiếu?

**Đáp án kỳ vọng:** Chạy **đúng artifact được phát hành** trên JVM 11 cùng runtime dependencies tương ứng, gồm smoke/integration tests cần thiết. Chỉ compile target 11 không kiểm tra mọi nhánh runtime hay phụ thuộc.

### Bài 5 — Tìm lỗi cấu hình CI

CI có các job `JDK 17 -> --release 11` PASS và `JDK 21 -> --release 21` PASS. Nhưng artifact phát hành được build với JDK 21 target 21, người dùng Java 17 bị lỗi nạp class. Vì sao?

**Đáp án kỳ vọng:** Artifact target 21 mang class major 65, cao hơn JVM 17 hỗ trợ. Nếu cam kết Java 17, phải xây artifact phát hành với target tối thiểu tương ứng và kiểm thử runtime 17. Việc một job riêng compile target 11 không thay đổi class của artifact đã phát hành.

## 13. Những ngộ nhận phổ biến

**“`--release` là cách cài JDK.”** Sai: nó là compiler option. Nó không tải JDK, không thay JVM chạy tool/test và không làm `javac` cũ hiểu cú pháp Java tương lai.

**“Chỉ cần `-target` đúng major version.”** Chưa đủ: class có thể liên kết tới API Java SE mới hơn target nếu compile trên JDK mới mà không kiểm soát bootstrap APIs.

**“Có `--release 11` thì khỏi chạy test trên Java 11.”** Sai: release kiểm tra compile-time standard platform, không đánh giá runtime dependencies và behavior.

**“`--enable-preview` cho phép chạy preview class trên mọi JDK mới.”** Sai: preview class file phụ thuộc release cụ thể. Phải dùng cùng Java SE release và runtime flag, hoặc biên dịch lại nguồn theo release mới.

**“Một đoạn code từng preview luôn cần preview flag.”** Sai: tính năng có thể đã thành chính thức trong release sau. Phải đánh giá theo Java release đang dùng.

**“Negative test pass khi command trả non-zero.”** Chưa đủ: non-zero có thể do thiếu tool, thiếu file hoặc invalid flags. Kiểm tra nguyên nhân phù hợp fixture.

**“Máy CI có JDK 11,17,21 thì test tự chạy đủ ba bản.”** Sai: phải thực sự cấu hình đúng launcher cho từng job và log phiên bản đang chạy.

**“Mọi version Java đều dùng được `--release 8`.”** Không nên giả định: mỗi `javac` có danh sách releases được hỗ trợ; kiểm tra `javac --help`.

## 14. Checklist trước khi tuyên bố hỗ trợ một JDK

- [ ] Có danh sách phiên bản JDK/runtime thực sự cam kết hỗ trợ.
- [ ] Build ghi rõ phiên bản compiler/toolchain và `--release`.
- [ ] Kiểm tra `javac --help` xác nhận release target được compiler hỗ trợ.
- [ ] Có positive test source hợp lệ và negative tests cho API/cú pháp vượt target.
- [ ] Không nhầm `-source/-target` với API compatibility của `--release`.
- [ ] Kiểm tra class major/minor khi cần, hiểu giới hạn của chỉ số này.
- [ ] Artifact được kiểm thử trên runtime thấp nhất và các runtime được hứa hỗ trợ.
- [ ] Runtime dependencies cũng tương thích với JVM thấp nhất.
- [ ] Preview lane, nếu có, khóa exact JDK release, compile/runtime flags và test expected failures.
- [ ] Có log phân biệt failure do source, toolchain hay runtime.
- [ ] CI thực sự thực thi từng ô matrix và không tự động chấm “skip” thành pass.
- [ ] Khi nâng JDK hoặc Gradle/Maven plugin, chạy lại compiler và runtime matrix.

## Tài liệu chính thức

- [Oracle Java SE — `javac` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
- [Oracle Java SE 17 — Preview features](https://docs.oracle.com/en/java/javase/17/language/preview-language-and-vm-features.html)
- [OpenJDK — JEP 406: Pattern Matching for switch (Preview)](https://openjdk.org/jeps/406)
- [OpenJDK — JEP 12: Preview Features](https://openjdk.org/jeps/12)
- [Gradle — Building Java & JVM projects](https://docs.gradle.org/current/userguide/building_java_projects.html)
- [Gradle — Toolchains for JVM projects](https://docs.gradle.org/current/userguide/toolchains.html)
- [Gradle — Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html)
- [Maven Compiler Plugin — Setting `--release`](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html)
- [Maven Compiler Plugin — Compiler parameters](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html)

Khi lựa chọn một ma trận cụ thể, ưu tiên chính sách hỗ trợ của dự án và tài liệu **đúng phiên bản** JDK, Gradle Wrapper hoặc Maven Compiler Plugin đang được triển khai. Kiểm thử tương thích có giá trị khi nó chứng minh được cả **source/API boundary, class file boundary và runtime behavior** của artifact thực tế.

# Compiler warning, lint, định dạng và phân tích tĩnh trong Java 27

Một dự án Java có thể **biên dịch thành công** nhưng vẫn chứa phép ép kiểu không an toàn, sử dụng API sắp bị loại bỏ, tài nguyên có nguy cơ không được đóng, lỗi trong Javadoc hoặc những mẫu code khiến việc bảo trì khó khăn. Ngược lại, một dự án có hàng trăm cảnh báo không phân loại cũng khiến nhà phát triển bỏ qua cảnh báo thật sự nguy hiểm.

Trong **Java 27**, quy trình bảo đảm chất lượng mã nên kết hợp **diagnostics của `javac`**, **lint categories**, **định dạng tự động**, **các công cụ phân tích tĩnh** và **kiểm thử**, thay vì kỳ vọng một công cụ xử lý tất cả.

Bài thuộc chương **Build và quản lý phụ thuộc** trong module **Java 27 và các kiến thức liên quan**. Nội dung chỉ mô tả các API/công cụ Java SE đang được hỗ trợ hiện nay. Những plugin của Maven, Gradle và bên thứ ba được giới thiệu dưới dạng **lựa chọn tích hợp**, với lưu ý phải chọn phiên bản tương thích với JDK 27.

## 1. Phân biệt compiler error, warning, lint và static analysis

| Khái niệm | Mục tiêu | Tác động khi phát hiện | Công cụ ví dụ |
| --- | --- | --- | --- |
| **Compiler error** | Phát hiện chương trình không hợp lệ theo Java language/type rules | `javac` không tạo bản build hợp lệ | `javac` |
| **Compiler warning** | Nêu rủi ro hoặc mã cần chú ý dù có thể vẫn biên dịch | Mặc định có thể không chặn build | `javac` diagnostics |
| **Lint** | Chọn các nhóm cảnh báo bổ sung theo quy tắc compiler | Có thể bật theo nhóm và nâng mức nghiêm trọng | `javac -Xlint` |
| **Formatting** | Chuẩn hóa cách trình bày mã | Formatter thay đổi văn bản; check mode có thể fail CI | Google Java Format, Spotless, IDE formatter |
| **Style checks** | Kiểm tra quy ước cú pháp, tổ chức, đặt tên, tài liệu | Báo vi phạm policy dự án | Checkstyle |
| **Bug-oriented static analysis** | Tìm mẫu lỗi tiềm ẩn, data flow và API misuse | Báo finding với mức độ/độ tin cậy khác nhau | SpotBugs, PMD, Error Prone |
| **Dependency analysis** | Xem phụ thuộc và rủi ro liên quan tới bản build | Cảnh báo xung đột, API không mong muốn, phiên bản thư viện | Maven/Gradle dependency reports, `jdeps` |
| **Tests** | Kiểm tra hành vi khi thực thi | Fail nếu kiểm thử phát hiện sai | JUnit, integration tests |

**Compiler warning không đồng nghĩa compiler error.** Với `-Werror`, những warning được phát ra có thể làm compilation thất bại, nhưng nguyên nhân gốc vẫn là một warning đã được nâng thành điều kiện fail.

**Formatter không phải static bug analyzer.** Đổi indent hoặc vị trí dấu ngoặc có thể cải thiện tính nhất quán nhưng không chứng minh code an toàn với `null`, concurrency hay các đường đi exception.

**Static analysis không thay thế test.** Công cụ chỉ phân tích dựa trên mô hình và rule mà nó hiểu; các lỗi phụ thuộc dữ liệu thật, cấu hình runtime hoặc tương tác hệ thống có thể vẫn lọt qua.

## 2. Quy trình phát triển nên có nhiều lớp kiểm soát

Một pipeline thường gồm:

```text
Source .java + dependencies + toolchain JDK 27
           │
           ├──► Formatter check ──► kiểm tra diff định dạng
           │
           ├──► javac ────────────► errors / warnings / -Xlint
           │                                  │
           │                                  └─► -Werror hoặc -Werror:key
           │
           ├──► Style/static analyzers ──► rule violations / findings
           │
           ├──► Unit + integration tests ──► sai hành vi
           │
           ├──► Javadoc/doclint ─────────► lỗi tài liệu API
           │
           └──► Build/package ──────────► artifact
                                              │
                                      release nếu policy PASS
```

Sơ đồ trình bày **các lớp kiểm tra**, không bắt buộc build thực thi từng bước theo đúng thứ tự này. Ví dụ SpotBugs thường phân tích **bytecode đã biên dịch**, còn formatter kiểm tra source độc lập.

Mỗi bước nên có **mục tiêu, phiên bản công cụ, mức cảnh báo chặn build và cách xử lý finding** được thống nhất. Một CI báo hàng trăm warning không ai xử lý thường kém hiệu quả hơn CI có chính sách rõ ràng và ít tín hiệu nhiễu.

## 3. Quan sát compiler warnings với javac trong JDK 27

Các lệnh căn bản:

```bash
javac --version
javac --help-lint
javac -Xlint LintExample.java
```

- `javac --version` xác nhận compiler được dùng.
- `javac --help-lint` liệt kê các **lint keys thực sự có trên JDK**; đây là cách đáng tin để tránh sao chép danh sách từ phiên bản khác.
- `-Xlint` bật các danh mục lint được khuyến nghị; trong JDK 27, tài liệu `javac` mô tả toàn bộ lint categories hiện có là recommended.
- `-Xlint:all` bật toàn bộ các danh mục lint.
- `-Xlint:unchecked,rawtypes` chỉ bật hai nhóm được nêu.
- `-Xlint:all,-serial` bật toàn bộ nhưng bỏ nhóm `serial`.

Không nhầm `-Xlint` của compiler với một lệnh format mã; nó **chỉ chẩn đoán** và không tự sửa source.

### 3.1. Cách đọc một diagnostic

Ví dụ hình thức đầu ra:

```text
LintExample.java:9: warning: [unchecked] unchecked conversion
    List<String> names = raw;
                         ^
```

Thông tin thường có:

1. Tên file, số dòng, đôi khi vị trí cột.
2. Severity như `warning` hoặc `error`.
3. Lint key trong ngoặc, ví dụ `[unchecked]`.
4. Nội dung mô tả và vị trí source liên quan.

Đây là **minh họa hình thức**, wording và số dòng có thể khác giữa các bản compiler hoặc theo chính xác mã nguồn.

Nếu warning là `[rawtypes]`, hãy tìm biến hoặc chữ ký dùng generic type **không khai báo type argument**. Nếu là `[deprecation]`, hãy xác định thành phần API nào bị đánh dấu deprecated, bắt đầu từ Javadoc và gợi ý thay thế.

### 3.2. Lệnh thực tế khi biên dịch nhiều file

```bash
javac -encoding UTF-8 --release 27 -Xlint:all -d out src/example/*.java
```

Cú pháp glob `src/example/*.java` phụ thuộc shell/môi trường; trong dự án thật có nhiều source sets và dependencies, ưu tiên để **Maven/Gradle** tạo command line thích hợp. Lệnh chỉ biểu diễn việc chọn encoding, release, lint và thư mục output, không bao gồm classpath/module path.

## 4. Những lint categories hữu ích nhất

Các tên dưới đây đều thuộc danh mục `-Xlint` có tài liệu trong JDK 27:

| Lint key | Điều cần chú ý | Ví dụ rủi ro |
| --- | --- | --- |
| `unchecked` | Thao tác generic không được compiler kiểm chứng kiểu đầy đủ | Gán raw `List` sang `List<String>` |
| `rawtypes` | Dùng generic class/interface mà không có type argument | `List items` thay vì `List<String>` |
| `deprecation` | Dùng API đã được đánh dấu `@Deprecated` | Phụ thuộc phương thức không còn được khuyến nghị |
| `removal` | Dùng API deprecated **for removal** | Có nguy cơ không còn ở release sau |
| `fallthrough` | Switch statement có nhánh rơi xuống nhánh sau không được bảo vệ | Thiếu `break` ở dạng switch statement cổ điển |
| `finally` | `finally` không kết thúc bình thường, ví dụ `return` che mất kết quả/exception | Khó xác định lỗi gốc |
| `try` | Vấn đề liên quan try-with-resources | Resource bị khai báo nhưng không được tham chiếu theo một số mẫu |
| `serial` | Vấn đề liên quan serializable classes | Thiếu metadata/hợp đồng serialization |
| `cast` | Ép kiểu dư thừa | `(String) "hi"` |
| `overrides` | Bất thường ở chữ ký khi override | Varargs vs array giữa phương thức gốc/override |
| `options` | Cờ biên dịch bất thường/không tương thích | Kết hợp source/release flags sai |
| `path` | Classpath hoặc đường dẫn không hợp lệ | Dependency ở thư mục không tồn tại |
| `processing` | Vấn đề trong annotation processing | Processor không claim annotation |
| `exports` | Vấn đề về types trong API của module | API export nhưng kiểu phụ thuộc không accessible |
| `module` | Vấn đề trong khai báo/usage module | Cấu trúc module có dấu hiệu không phù hợp |
| `dangling-doc-comments` | Javadoc bị đặt sai vị trí | Comment không còn gắn với declaration mong muốn |

Bảng không thay thế `javac --help-lint`: tập lint keys có thể tiếp tục được bổ sung theo JDK. Những warning **mặc định** và warning bật bởi `-Xlint` cũng không hoàn toàn giống nhau.

### 4.1. Chọn tập lint có mục tiêu

Đội dự án có thể bắt đầu với các nhóm có ảnh hưởng đến độ đúng đắn và vòng đời API:

```bash
javac -Xlint:unchecked,rawtypes,deprecation,removal,fallthrough,try -d out LintExample.java
```

Sau khi xử lý các cảnh báo lịch sử, mở rộng sang `-Xlint:all` để đánh giá xem policy nào phù hợp. Không nên vô hiệu hóa cả compiler warnings chỉ vì vài cảnh báo chưa được phân loại.

## 5. Ví dụ thực tế: raw types và unchecked conversion

Tạo file `LintProblem.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class LintProblem {
    static List<String> copyUnsafe(List source) {
        List<String> result = source;
        return result;
    }

    public static void main(String[] args) {
        List source = new ArrayList();
        source.add("Java 27");

        List<String> result = copyUnsafe(source);
        System.out.println(result.get(0));
    }
}
```

Lệnh kiểm tra:

```bash
javac -Xlint:rawtypes,unchecked -d out LintProblem.java
```

Các vị trí warning điển hình:

- `List source` và `new ArrayList()` sử dụng **raw types**.
- `source.add(...)` là thao tác trên raw generic collection.
- `List<String> result = source;` thực hiện **unchecked conversion** vì compiler không xác nhận mọi phần tử đều là `String`.

Mã vẫn có thể biên dịch rồi chạy với dữ liệu trong demo, nhưng nếu `source` chứa `Integer` thì một truy cập sau đó có thể gây `ClassCastException`. Việc một input thử nghiệm thành công không chứng minh kiểu dữ liệu đúng.

### 5.1. Cách sửa theo type safety

Tạo file `LintFixed.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class LintFixed {
    static List<String> copy(List<String> source) {
        return new ArrayList<>(source);
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("Java 27");

        List<String> result = copy(source);
        System.out.println(result.get(0));
    }
}
```

Lệnh:

```bash
javac -Xlint:rawtypes,unchecked -Werror -d out LintFixed.java
java -cp out LintFixed
```

Kết quả:

```text
Java 27
```

Điểm sửa không chỉ là thêm `<String>` vào một vài dòng: **hợp đồng phương thức** đã xác định dữ liệu đầu vào thuộc kiểu nào và constructor sử dụng diamond syntax. Mã này không còn phải dựa vào ép kiểu runtime để đưa `Object` vào `String`.

### 5.2. Nếu boundary thật sự nhận dữ liệu không rõ kiểu?

Đừng ép trực tiếp `List<?>` thành `List<String>` rồi ẩn warning:

```java
// Không phải giải pháp kiểm chứng kiểu:
// @SuppressWarnings("unchecked")
// List<String> strings = (List<String>) unknown;
```

Nếu input đến từ API không typed hoặc JSON đã decode thành các object tùy ý, hãy **kiểm tra từng phần tử**:

```java
import java.util.ArrayList;
import java.util.List;

static List<String> checkedStrings(List<?> source) {
    List<String> result = new ArrayList<>();

    for (Object value : source) {
        if (!(value instanceof String text)) {
            throw new IllegalArgumentException("Phần tử không phải String");
        }
        result.add(text);
    }

    return List.copyOf(result);
}
```

Đây là **fragment của phương thức** được đặt trong một class, với hai import như đã trình bày. Với dữ liệu legacy, validate ở **boundary** sẽ an toàn hơn giả định mà không có bằng chứng.

## 6. @SuppressWarnings: ngoại lệ có phạm vi rõ ràng

Java hỗ trợ annotation `@SuppressWarnings` để tắt những compiler warnings được khai báo trong một phạm vi thích hợp:

```java
@SuppressWarnings("unchecked")
static <T> T castAfterValidation(Object value) {
    return (T) value;
}
```

**Ví dụ trên chỉ thể hiện cú pháp và vẫn có ép kiểu không được kiểm chứng.** Tên `castAfterValidation` không khiến ép kiểu trở nên an toàn. Với bất kỳ `@SuppressWarnings("unchecked")` thực tế nào, cần có lập luận/kiểm thử chứng minh invariant trước khi ép.

Quy tắc sử dụng:

1. **Ưu tiên sửa warning** hơn là suppression.
2. Đặt annotation ở **phạm vi nhỏ nhất** có thể: biến, phương thức hoặc class thực sự cần.
3. Ghi ngắn lý do tại sao warning là false positive hoặc không thể loại bỏ bằng thiết kế khác.
4. Không dùng `@SuppressWarnings("all")` làm policy chung.
5. Không phải mọi lint category đều có thể suppress bằng annotation; chẳng hạn những vấn đề command-line option/path cần sửa **build configuration**, không gắn annotation vào source.

Đối với code từ dependency bên ngoài gây warning, trước tiên kiểm tra có thể **nâng phiên bản thư viện**, thay API hay cấu hình analyzer để không phân tích generated/vendor code không. Đừng đặt suppression diện rộng lên module ứng dụng để che mọi cảnh báo.

## 7. Deprecation và API đánh dấu forRemoval

Hai trường hợp liên quan nhưng khác mức độ:

- `@Deprecated`: thành phần không còn được khuyến nghị sử dụng; vẫn có thể được cung cấp.
- `@Deprecated(forRemoval = true)`: tác giả API thông báo dự kiến loại bỏ trong một bản phát hành tương lai; đây là tín hiệu cần ưu tiên migration.

Ví dụ tự chứa với API của chính dự án:

```java
public class CompatibilityExample {

    @Deprecated(since = "27", forRemoval = true)
    static String oldDisplayName(String name) {
        return name.toUpperCase();
    }

    static String displayName(String name) {
        return name.strip().toUpperCase(java.util.Locale.ROOT);
    }

    public static void main(String[] args) {
        System.out.println(displayName("Java"));
    }
}
```

Đoạn không gọi API cũ nên không tạo warning tại lời gọi. Nếu một class **khác** gọi `oldDisplayName(...)`, compiler có thể báo `[removal]` khi bật lint tương ứng.

**Không hiểu sai rằng một phần tử đánh dấu forRemoval đã bị xóa trong Java 27**: nó có thể vẫn tồn tại trong release đang dùng. Nhưng dự án mới không nên chọn nó nếu đã có hướng thay thế được hỗ trợ.

### 7.1. Chính sách migration thực tế

Khi gặp warning:

1. Xem **Javadoc của API** và `@Deprecated.since`/`forRemoval`.
2. Tìm API thay thế trong tài liệu của **đúng JDK/library version**.
3. Đánh giá khác biệt semantics, không chỉ thay tên.
4. Cập nhật code, test và dependency.
5. Kiểm tra mọi module/consumer bị ảnh hưởng.
6. Chỉ dùng suppression tạm thời khi có thời hạn và lý do rõ ràng.

Bật `-Xlint:deprecation,removal` là cách tìm chỗ sử dụng API cũ; **không cần** mở các file thư viện nội bộ của JDK hoặc dựa vào `sun.*` APIs.

## 8. Switch fallthrough, finally và warning có thể gây lỗi logic

Trong switch statement dạng có dấu hai chấm, việc thiếu `break` ở nhánh phù hợp có thể làm code tiếp tục qua nhánh sau:

```java
static String describe(int status) {
    StringBuilder result = new StringBuilder();

    switch (status) {
        case 1:
            result.append("created");
            // Thiếu break: có thể rơi xuống case 2.
        case 2:
            result.append(" processed");
            break;
        default:
            result.append("unknown");
    }

    return result.toString();
}
```

`javac -Xlint:fallthrough` giúp phát hiện mẫu cần review. Với code mới, **switch expressions** hoặc nhánh arrow-style (`case ... ->`) là cách viết rõ ràng hơn khi bài toán phù hợp:

```java
static String describe(int status) {
    return switch (status) {
        case 1 -> "created";
        case 2 -> "processed";
        default -> "unknown";
    };
}
```

Không phải mọi fallthrough đều sai: đôi khi đó là chủ đích. Nhưng cần biểu đạt rõ và kiểm thử; không nên dùng comment/suppression chỉ để lách một trường hợp chưa hiểu.

### 8.1. finally có thể che lỗi gốc

```java
static int badExample() {
    try {
        throw new IllegalStateException("origin");
    } finally {
        return 0;
    }
}
```

`return` trong `finally` khiến ngoại lệ ban đầu không được ném tiếp. `-Xlint:finally` được thiết kế để cảnh báo các `finally` không kết thúc bình thường.

Hướng sửa: chỉ dùng `finally` để cleanup và **không return/throw không kiểm soát** làm che đường đi lỗi. Với tài nguyên `AutoCloseable`, ưu tiên `try-with-resources` để đóng đúng và lưu các lỗi cleanup dưới dạng suppressed exception.

## 9. -Werror: xác định ranh giới cho warning

Lệnh:

```bash
javac -Xlint:all -Werror -d out LintFixed.java
```

bật mọi lint category và biến **các warning được phát ra** thành điều kiện khiến compilation thất bại. `-Werror` không tự bật mọi lint category: nếu muốn fail trên một nhóm warning, phải đảm bảo nhóm đó được **bật**.

Tài liệu `javac` của **JDK 27** còn mô tả khả năng chọn các lint categories được coi là lỗi qua:

```bash
javac -Xlint:unchecked,rawtypes,deprecation \
      -Werror:unchecked,rawtypes \
      -d out LintFixed.java
```

Ý nghĩa:

- Các warning `unchecked` và `rawtypes` được bật và có thể làm fail compilation.
- Các warning `deprecation` vẫn được phát ra để review nhưng **không tự làm fail theo lựa chọn `-Werror:...` trên**.
- `-Werror` không có danh sách sẽ fail trên **mọi** warning được phát ra, kể cả non-lint warnings.

**Tương thích toolchain:** cú pháp `-Werror:<key>` được mô tả cho JDK 27; nếu một dự án còn phải build bằng JDK thấp hơn, phải xác nhận compiler của release đó có hỗ trợ hay không. Không sao chép nguyên cờ mới rồi kỳ vọng các compiler cũ hiểu được.

### 9.1. Không cần chặn toàn bộ warning ngay ngày đầu

Một lộ trình áp dụng hợp lý:

1. Bắt đầu bật `-Xlint` trên CI và lưu báo cáo.
2. Phân loại warning theo độ rủi ro và module.
3. Sửa warning nguy hiểm và warning xuất hiện trong code mới.
4. Với code cũ, tạo baseline có kiểm soát, không che warning mới.
5. Bật `-Werror` cho các nhóm đã sạch.
6. Mở rộng phạm vi khi tooling và nguồn phụ thuộc ổn định.

Nếu bật `-Werror` đột ngột cho một monorepo có hàng nghìn warning từ generated code, CI có thể trở nên không hữu ích. Điều quan trọng là **ngăn phát sinh nợ mới và giảm nợ cũ có đo lường**.

## 10. Toolchain, --release và việc kiểm tra trên đúng Java 27

Các warning phụ thuộc vào **phiên bản compiler** và ngôn ngữ/API mà bạn chọn. Cần tách:

- **JDK chạy Maven/Gradle:** JVM thực thi công cụ build.
- **JDK dùng làm compiler:** `javac` thật dùng để biên dịch.
- **Target release:** mức ngôn ngữ, class-file version và API chuẩn được cho phép.
- **JRE/JDK thực thi ứng dụng:** môi trường runtime thật.

Ví dụ:

```bash
javac --version
javac --release 27 -Xlint:all -d out LintFixed.java
```

`--release 27` nói với `javac` được chạy trên JDK 27 sử dụng ngôn ngữ, API công khai và class-file target tương ứng với Java 27.

Nếu thư viện đang hỗ trợ **Java 21** nhưng build bằng **JDK 27**, sử dụng `--release 21` cho phần mã tương ứng giúp compiler kiểm tra API/language ở mức 21:

```bash
javac --release 21 -Xlint:all -d out LintFixed.java
```

Điều này vẫn **không thay thế** thử chạy trên JDK 21 thực tế khi dự án tuyên bố hỗ trợ runtime đó, đặc biệt đối với dependency và hành vi OS/native.

### 10.1. Vì sao không chỉ dùng -source/-target?

`-source` kiểm soát quy tắc ngôn ngữ và `-target` kiểm soát class-file version, nhưng không độc lập bảo đảm bạn tránh dùng **API của JDK mới hơn**. Khi cần tương thích với một Java release xác định, `--release` là cách ưu tiên.

Nếu dùng Gradle, cấu hình **Java toolchain** để thống nhất compiler/Javadoc/test runtime khi phù hợp. Nếu dùng Maven, đảm bảo process chạy compiler/toolchain dự kiến, không chỉ gán `<maven.compiler.release>` mà bỏ qua JDK thật.

Một formatter hoặc static analyzer cũng có thể cần **phiên bản riêng** hỗ trợ cú pháp Java 27. Build dùng JDK 27 không bảo đảm plugin bên thứ ba tự nhiên đã parse được cú pháp mới.

## 11. Annotation processing: cấu hình rõ, không dựa vào auto-discovery cũ

Các dự án dùng annotation processors như mã sinh DTO, mapper hoặc metadata phải cấu hình **processor path/dependencies** tường minh. Trong `javac` hiện hành, processing được yêu cầu bằng những lựa chọn như `-processor`, `--processor-path`, `--processor-module-path` hoặc `-proc:full`/`-proc:only`.

```bash
javac --release 27 \
      --processor-path path/to/processor.jar \
      -processor example.processor.MyProcessor \
      -d out \
      src/example/App.java
```

Đây là mẫu lệnh về **cấu hình**, không phải demo chạy trực tiếp: `example.processor.MyProcessor` và `path/to/processor.jar` là placeholder, cần có processor thật, dependency đầy đủ và mã nguồn hợp lệ.

Các chế độ:

| Cờ | Hành vi |
| --- | --- |
| `-proc:none` | Không thực hiện annotation processing |
| `-proc:only` | Chạy annotation processing, không tiếp tục biên dịch class thông thường |
| `-proc:full` | Thực hiện processing và compilation |
| `-processor A,B` | Chọn processor bằng tên |
| `--processor-path path` | Đặt nơi tìm processor |
| `--processor-module-path path` | Đặt nơi tìm modular processors |

Điểm hiện đại quan trọng: **không dựa vào giả định cứ có processor ở classpath là compiler mọi bản JDK sẽ tự chạy như trước**. Kiểm tra cấu hình JDK 27 và build plugin, khai báo processor bằng dependency scope/chế độ riêng.

Lợi ích:

- Dễ nhận biết **plugin nào chạy code trong quá trình build**.
- Tránh việc thêm dependency ngẫu nhiên kích hoạt processor không mong muốn.
- Tái lập build đáng tin hơn.
- Giảm cảnh báo processing và lỗi khác biệt giữa local/CI.

Đừng tắt toàn bộ processing để “làm hết warning” nếu project thật sự cần source generation; cách đó có thể làm các class sinh ra biến mất.

## 12. DocLint: kiểm tra Javadoc là bước riêng

Bình luận tài liệu có thể có link `{@link ...}` sai, thiếu `@param`, thiếu `@return`, cấu trúc HTML không hợp lệ hoặc lỗi tham chiếu API.

JDK cung cấp **DocLint** trong hai công cụ:

- `javac -Xdoclint`: bật kiểm tra doc comments trong lúc biên dịch (mặc định `javac` không bật).
- `javadoc -Xdoclint:all`: kiểm tra documentation trong quá trình tạo tài liệu API; Javadoc chuẩn đã có DocLint enabled theo tài liệu hiện hành.

Ví dụ:

```bash
javac -Xdoclint:all/protected -d out src/example/Calculator.java
javadoc -Xdoclint:all -d docs src/example/Calculator.java
```

Đây là lệnh ví dụ với file `Calculator.java` cần tồn tại; tùy package, module và classpath sẽ cần thêm options.

### 12.1. Những nhóm DocLint

| Group | Phát hiện |
| --- | --- |
| `accessibility` | Một số vấn đề khả năng tiếp cận trong HTML Javadoc |
| `html` | Một số lỗi cấu trúc HTML |
| `missing` | Missing comments/tags theo mức độ hiển thị |
| `reference` | Sai tham chiếu API, `@see`, `@link`, `@param`, `@throws` |
| `syntax` | Lỗi cú pháp của documentation comments |

Có thể chọn mức truy cập:

```bash
javac -Xdoclint:all/protected -d out src/example/Calculator.java
```

Nghĩa là kiểm tra declaration `protected` và `public` theo quy tắc DocLint, thay vì bắt buộc mọi private helper đều có Javadoc.

### 12.2. Ví dụ tài liệu đúng

```java
/**
 * Tính tổng hai số nguyên.
 *
 * @param left số hạng thứ nhất
 * @param right số hạng thứ hai
 * @return tổng của hai số
 */
public static int add(int left, int right) {
    return Math.addExact(left, right);
}
```

Đây là fragment trong một class, không phải file Java độc lập. Nó mô tả API, tên tham số và kết quả. Nếu muốn trình bày rằng phép cộng **có thể ném `ArithmeticException` khi tràn**, tài liệu cũng nên nói rõ hợp đồng đó.

**DocLint không tự sửa lỗi tài liệu** và không bảo đảm HTML đạt mọi tiêu chuẩn. Nó cung cấp kiểm tra có trọng tâm, nên dùng cùng review API và kiểm thử.

## 13. Định dạng tự động và lint là hai công việc khác nhau

**Formatter** phân tích source và tạo lại cách trình bày theo quy tắc xác định. Khi chạy ở chế độ *apply*, formatter có thể **sửa file**. Khi chạy ở chế độ *check*, công cụ chỉ xác định source hiện tại có khớp output mong đợi hay không.

**Lint/static analyzer** chủ yếu tạo diagnostics/findings; chúng có thể có tính năng sửa tự động nhưng không nên coi việc sửa đó tương đương với formatter.

Ví dụ hai vấn đề khác nhau:

```java
// Vấn đề trình bày:
class  Example{ int number(){return 27;} }

// Vấn đề kiểu dữ liệu, không thể giải quyết chỉ bằng indent:
java.util.List raw = new java.util.ArrayList();
```

Formatter có thể đổi khoảng trắng, thụt dòng, xuống dòng hoặc vị trí dấu ngoặc nhưng **không biến raw List thành generic List<String> an toàn**.

### 13.1. Công cụ formatter phổ biến

Các lựa chọn thực tế:

- **Google Java Format**: formatter theo quy tắc nhất quán, ít tùy chỉnh, thường được tích hợp qua IDE hoặc công cụ build.
- **Spotless**: tích hợp vào Gradle/Maven, có nhiệm vụ **check/apply**, có thể gọi Google Java Format và kiểm tra cả file cấu hình/headers.
- **IDE formatter**: thuận tiện khi phát triển cục bộ, nhưng cần xuất/chia sẻ chính sách để tránh IDE của từng thành viên sinh diff khác nhau.
- **EditorConfig**: quy định một số thuộc tính file như charset, end-of-line và indentation cho editor hỗ trợ; **không thay thế** một Java formatter đầy đủ.

Đối với Java 27, kiểm tra **phiên bản formatter/parser bên dưới hỗ trợ cú pháp được dự án sử dụng**. Một formatter bên thứ ba cũ có thể thất bại khi gặp language construct mới, kể cả khi `javac 27` biên dịch được.

### 13.2. Check trong CI, apply ở local

Quy trình nên là:

```text
Developer thay đổi source
   ├── chạy formatter apply khi cần
   ├── kiểm tra diff
   └── commit
         │
         ▼
CI chạy formatter check
   ├── PASS → tiếp tục compiler/lint/static analysis
   └── FAIL → báo file không tuân theo format
```

CI thường nên **fail và yêu cầu developer commit định dạng chuẩn**, không âm thầm sửa rồi công bố một artifact tạo từ mã chưa được review. Điều này giữ code được kiểm thử tương ứng với code đã commit.

## 14. EditorConfig: một quy ước đơn giản trên nhiều IDE

Tệp `.editorconfig` minh họa:

```ini
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true

[*.java]
indent_style = space
indent_size = 4

[*.md]
trim_trailing_whitespace = false
```

Ý nghĩa:

- `charset=utf-8` giúp tránh lỗi encoding, đặc biệt với tài liệu hoặc string tiếng Việt.
- `end_of_line=lf` thống nhất kết thúc dòng khi cộng tác khác OS.
- `insert_final_newline=true` giúp file kết thúc nhất quán.
- `trim_trailing_whitespace=true` hạn chế khoảng trắng thừa.
- `indent_size=4` áp dụng cho editor/plugin tôn trọng thiết lập.

**Không mặc định EditorConfig ghi đè quyết định của Google Java Format.** Nếu formatter có quy ước riêng, formatter vẫn là nguồn kiểm chứng chính của Java code; EditorConfig chủ yếu chuẩn hóa hành vi editor và các file khác.

Đây là **ví dụ nội dung file cấu hình**, không phải yêu cầu tạo thêm file trong assignment này.

## 15. Gradle Kotlin DSL: cấu hình warning và formatter

Với dự án Gradle dùng Kotlin DSL, các phần dưới đây có thể nằm trong `build.gradle.kts`:

```kotlin
plugins {
    java
    id("com.diffplug.spotless") version "8.12.0"
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(27)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 27
    options.encoding = "UTF-8"
    options.compilerArgs.addAll(
        listOf(
            "-Xlint:all",
            "-Werror"
        )
    )
}

spotless {
    java {
        target("src/**/*.java")
        googleJavaFormat()
    }
}
```

**Lưu ý về ví dụ:**

1. `java.toolchain` chọn JDK 27 phù hợp nếu đã được cài hoặc cơ chế provisioning của Gradle được thiết lập.
2. `options.release = 27` kiểm soát target ngôn ngữ/API/class file của `javac`.
3. `options.compilerArgs` đưa các cờ thực sự tới Java compiler.
4. `spotless` cung cấp tác vụ check/apply thông qua formatter đã cấu hình.
5. Phiên bản `Spotless 8.12.0` là một **phiên bản plugin cụ thể được phát hành trong năm 2026**, nhưng người dùng vẫn phải kiểm tra **tương thích Gradle, JDK và phiên bản Google Java Format** với project thực tế. Không coi version này là lựa chọn bắt buộc hoặc dùng mãi mãi.
6. `googleJavaFormat()` không có tham số phiên bản trong ví dụ sử dụng mặc định do plugin chọn; với build yêu cầu tính tái lập nghiêm ngặt nên **pin phiên bản formatter engine** đã kiểm chứng theo tài liệu Spotless tương ứng.

Lệnh khi project đã cấu hình:

```bash
./gradlew spotlessCheck
./gradlew spotlessApply
./gradlew clean check
```

- `spotlessCheck`: kiểm tra định dạng, thích hợp CI.
- `spotlessApply`: sửa định dạng, thích hợp developer trước commit.
- `check`: các verification tasks theo cấu hình project.

Trên Windows, có thể dùng `gradlew.bat` tương ứng. Không chạy `spotlessApply` trực tiếp trên CI nếu chính sách yêu cầu build đúng source đã commit.

### 15.1. Khi chưa muốn fail mọi warning

Có thể dùng trước:

```kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.addAll(
        listOf("-Xlint:unchecked,rawtypes,deprecation,removal")
    )
}
```

Sau khi warning được xử lý, thêm `-Werror` hoặc `-Werror:unchecked,rawtypes` trên JDK 27. Không nên đổi `-Xlint:all` thành `-Xlint:none` chỉ để pipeline có màu xanh.

**Giới hạn:** cấu hình trên chỉ tác động tới `JavaCompile` tasks do Gradle quản lý và các source sets tương ứng. Nếu còn code được compile bằng lệnh javac riêng, annotation generator, hoặc build khác, cần áp dụng policy tương đương ở những nơi đó.

## 16. Maven: cấu hình javac warnings bằng Compiler Plugin

Với dự án Maven, ví dụ `pom.xml` tối giản có thể dùng **Maven Compiler Plugin 3.16.0** và JDK 27:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>lint-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>27</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.16.0</version>
                <configuration>
                    <showWarnings>true</showWarnings>
                    <compilerArgs>
                        <arg>-Xlint:all</arg>
                        <arg>-Werror</arg>
                    </compilerArgs>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Ý nghĩa:

- `maven.compiler.release` yêu cầu compilation ở mức Java 27 theo plugin/JDK.
- `compilerArgs` truyền `-Xlint:all` và `-Werror`.
- `showWarnings=true` không thay việc **bật nhóm lint** bằng `-Xlint`.
- Version plugin được khai báo tường minh để các lần build không tự chọn version khác.

Lệnh minh họa khi JDK 27 và Maven đã sẵn có:

```bash
mvn -B -ntp clean verify
```

**Không nhầm phiên bản plugin với phiên bản Maven hoặc JDK.** Một Maven Compiler Plugin cụ thể có thể tương thích nhiều JDK, nhưng trước khi nâng JDK hãy xác nhận Maven runtime, compiler plugin, surefire/test plugins và static analyzers cũng hỗ trợ môi trường đó.

### 16.1. Compiler Plugin không tự là formatter hoặc bug analyzer

`maven-compiler-plugin` chịu trách nhiệm biên dịch. Các mục khác như format, Checkstyle, PMD, SpotBugs cần **plugin và cấu hình riêng**, không tự được kích hoạt chỉ vì thêm `-Xlint:all` vào compiler.

Nếu dùng Spotless Maven Plugin, `spotless:check`/`spotless:apply` là các goal tương ứng **khi plugin đã được khai báo**. Đừng khẳng định lệnh này tự tồn tại trong một POM chỉ có Maven Compiler Plugin.

## 17. Static analysis: chọn công cụ theo loại rủi ro

Một dự án Java không nhất thiết cần mọi công cụ dưới đây; mỗi tool có phạm vi khác nhau:

| Công cụ | Phân tích chủ yếu | Điểm mạnh | Cần lưu ý |
| --- | --- | --- | --- |
| `javac -Xlint` | Source/typing/compiler diagnostics | Có sẵn trong JDK, tích hợp build dễ | Không kiểm tra mọi logic bug |
| Checkstyle | Cấu trúc/style/source conventions | Naming, imports, quy ước code | Không phải data-flow bug detector chuyên sâu |
| PMD | Source rules và một số phân tích luồng | Complexity, suspicious patterns, anti-patterns | Rule set cần điều chỉnh; có false positives |
| SpotBugs | Bytecode analysis | Một số bug patterns, null/resource/concurrency findings | Phải có bytecode, kiểm tra hỗ trợ Java 27 class files |
| Error Prone | Kiểm tra tĩnh tích hợp compiler `javac` | Nhiều bug patterns tại compile time | Phiên bản/plugin cần tương thích đúng JDK/compiler |
| Formatter | Chuẩn hóa source presentation | Giảm diff stylistic | Không thay semantic analysis |
| `jdeps` | Phân tích phụ thuộc class/package/module | Phát hiện tham chiếu JDK internals/module boundaries | Không phải Java security scanner hoặc full bug analyzer |

**Đừng đưa tất cả tool vào CI chỉ vì chúng nổi tiếng.** Hãy xác định lớp lỗi thực sự cần ngăn, khả năng xử lý finding và chi phí chạy.

Ví dụ một chính sách nhẹ:

1. `javac -Xlint:all` cho warning compiler.
2. Spotless check cho định dạng.
3. Checkstyle hoặc PMD cho quy ước nhóm.
4. SpotBugs cho bytecode bug patterns.
5. Tests và dependency/security scanning cho các rủi ro không có trong static analysis cấp source.

Một tổ chức khác có thể dùng Error Prone thay một phần rule set của PMD; **tránh kích hoạt quy tắc trùng nhau** rồi báo cùng một vấn đề dưới ba tên khác nhau.

### 17.1. Phải kiểm tra khả năng parse Java 27

JDK 27 có mức source và class-file version riêng. Công cụ bên thứ ba có thể chưa:

- Đọc class-file version Java 27.
- Parse cú pháp mới tương ứng source level 27.
- Tương thích với internals/compiler hooks của `javac 27`.
- Hỗ trợ compiler plugins hoặc annotation processors của project.

Vì vậy **không bảo đảm** một version của SpotBugs, PMD, Checkstyle hoặc Error Prone chạy được chỉ vì JDK 27 đã cài thành công. Trước khi bật fail CI, thử đúng tool versions trên repo và JDK runtime mục tiêu.

## 18. Thế nào là một static-analysis finding hữu ích?

Giả sử công cụ báo: *potential null dereference*. Tín hiệu này là **giả thuyết về một đường đi lỗi**, không phải bằng chứng chương trình chắc chắn xảy ra lỗi ở runtime.

Quy trình triage:

1. Đọc **rule ID**, severity và đường dẫn source/bytecode.
2. Tái hiện đường đi có thể tạo `null` hoặc trạng thái bất thường.
3. Tìm hợp đồng của API và invariant của project.
4. Sửa code nếu có lỗi: validate input, thay luồng điều khiển hoặc thay model dữ liệu.
5. Bổ sung unit/integration test chứng minh tình huống đã được bảo vệ.
6. Nếu rule báo sai, ghi suppression **hẹp** với lý do và người chịu trách nhiệm.
7. Đánh giá lại sau mỗi lần nâng công cụ.

Ví dụ cải thiện hợp đồng:

```java
static int nameLength(String name) {
    return name.length();
}
```

Nếu `name` không được bảo đảm non-null, lời gọi có thể ném `NullPointerException`.

Một lựa chọn rõ:

```java
static int nameLength(String name) {
    return java.util.Objects.requireNonNull(
            name, "name phải khác null"
    ).length();
}
```

Đoạn thứ hai vẫn ném exception với `null`, nhưng **ràng buộc ở boundary** và message rõ ràng hơn. Nếu nghiệp vụ chấp nhận `null`, giải pháp phải là policy khác, ví dụ trả 0 hoặc dùng kiểu dữ liệu biểu diễn “không có giá trị”; static tool không thể tự quyết định quy tắc này.

## 19. Chọn severity và xử lý false positives

Nên phân biệt **severity** với **confidence**:

- Một vấn đề có tác động lớn nhưng công cụ có độ tin cậy thấp vẫn cần review, không nên mặc nhiên block mọi build.
- Một cảnh báo compiler rõ ràng như unchecked conversion tại API boundary có thể được xếp cao hơn quy tắc style về chiều dài dòng.
- Một finding từ code được sinh ra có thể cần xử lý ở **generator/template**, thay vì sửa file generated rồi bị ghi đè.

Một chiến lược:

| Loại finding | Phản ứng đề xuất |
| --- | --- |
| Compiler errors | Fail ngay |
| Cảnh báo generic type safety hoặc API forRemoval trong code mới | Fix, có thể gate |
| Bug finding mức độ nghiêm trọng cao, đã xác minh | Fail CI hoặc chặn release |
| Vi phạm formatter | Fail formatter check và hướng dẫn chạy apply |
| Vấn đề style ưu tiên thấp | Warning/baseline khi đang chuyển đổi |
| Finding đã phân loại false positive | Suppression hẹp, có lý do |
| Vấn đề trong generated/third-party source | Cấu hình scope, sửa generator hoặc nâng dependency |

Nếu mọi warning trở thành error ngay từ đầu, nhóm có thể chọn cách xóa warning bằng suppression diện rộng. Chính sách tốt cần khuyến khích **sửa nguyên nhân** thay vì chỉ làm số lượng warning bằng 0.

## 20. Dependency và toolchain cũng là một phần của chất lượng phân tích

Một kết quả CI có thể khác local do:

- Local dùng `javac 27`, CI dùng JDK cũ.
- Maven/Gradle plugin version khác nhau.
- Bộ rules Checkstyle/PMD/SpotBugs được cập nhật không kiểm soát.
- Formatter engine tự nâng version và tạo diff hàng loạt.
- Annotation processor xuất hiện trên classpath khác với dự kiến.
- Source được compile bằng `--release` khác nhau.
- Dependency resolution trả các thư viện hoặc transitive versions khác nhau.

Cách quản lý:

1. Pin phiên bản **JDK/toolchain**, Maven/Gradle wrapper và plugins.
2. Sử dụng dependency locking/version catalogs/BOM hoặc dependency management thích hợp.
3. Giữ một bộ rules và formatter config được version-control.
4. Nếu cần build có thể tái lập, quản lý repository, artifact checksums/verification và nguồn dependency theo policy.
5. Chạy cùng verification commands ở local và CI khi có thể.
6. Cập nhật version có kế hoạch và quan sát diff findings trước/sau.

**Quản lý phiên bản chỉ làm môi trường phân tích nhất quán hơn**; nó không biến một static-analysis rule thành bảo đảm tuyệt đối về độ đúng đắn.

## 21. Quy trình CI đề xuất cho Java 27

Một pipeline có thể chia thành các stage:

```text
Checkout repository
   │
   ▼
Khởi tạo JDK 27 + build wrapper versions đã pin
   │
   ▼
Formatter check ──────► fail nếu source sai định dạng
   │
   ▼
javac + -Xlint + chính sách -Werror
   │
   ▼
Style/static analysis (tools đã xác minh JDK 27)
   │
   ▼
Unit tests + integration tests
   │
   ▼
Javadoc/DocLint và kiểm tra artifact
   │
   ▼
Publish artifacts nếu toàn bộ các quality gates đạt
```

Trên Gradle, nếu các plugin/tasks tương ứng đã được thiết lập:

```bash
./gradlew --no-daemon spotlessCheck
./gradlew --no-daemon clean check
```

Trên Maven, với plugin format/static-analysis được cấu hình vào lifecycle:

```bash
mvn -B -ntp clean verify
```

**Lệnh build không tự kích hoạt bất cứ analyzer nào nếu plugin chưa được bind đúng**. Ví dụ `clean verify` mặc định không đồng nghĩa SpotBugs/PMD/Checkstyle đều đã chạy.

### 21.1. Tách kiểm tra nhẹ và kiểm tra nặng

- **Editor/pre-commit:** formatter và lint đơn giản, feedback nhanh.
- **Pull request CI:** formatter check, compilation warnings, unit tests, phân tích tĩnh các module liên quan.
- **Main branch/release:** full module scan, integration tests, Javadoc, security/dependency audits và packaging.
- **Nightly (nếu phù hợp):** kiểm tra rộng, fuzz/property testing hoặc công cụ tốn thời gian.

Không phải dự án nào cũng cần bốn pipeline. Đây là một gợi ý nhằm giảm thời gian phản hồi nhưng vẫn giữ kiểm soát ở bản build cuối.

## 22. Lộ trình xử lý nợ cảnh báo trên codebase lớn

Nếu repository hiện có hàng nghìn warning, có thể áp dụng từng giai đoạn:

**Giai đoạn 1 — Lập danh sách**

- Bật `-Xlint:all` không `-Werror` trong một build có phiên bản JDK cố định.
- Lưu warning theo **category, module, source owner**.
- Phân biệt warning từ code sở hữu với generated code.
- Xác nhận có bao nhiêu warning thực sự và nguyên nhân phổ biến.

**Giai đoạn 2 — Ưu tiên**

- Ưu tiên `unchecked`, `rawtypes` ở API boundary, `removal` và lỗi có ảnh hưởng runtime.
- Ưu tiên code đang thay đổi trong pull request.
- Tránh hàng loạt change thuần formatter khi cùng PR đang sửa bug phức tạp.

**Giai đoạn 3 — Quality gate**

- Chặn warning **mới** trong những nhóm đã sạch.
- Dùng baseline tạm thời cho warning cũ nếu analyzer hỗ trợ.
- Đặt thời hạn giảm baseline.
- Không thêm suppression không có lý do chỉ để đạt “zero warnings”.

**Giai đoạn 4 — Nâng tiêu chuẩn**

- Chuyển những nhóm đã xử lý xong sang `-Werror` hoặc kiểm tra tương ứng.
- Bổ sung rule set có thể bảo trì.
- Theo dõi xu hướng warning và false positives qua các phiên bản công cụ.

Baseline là **công cụ chuyển đổi**, không phải kho lưu trữ vĩnh viễn cho mọi lỗi.

## 23. Những lỗi cấu hình phổ biến

| Sai lầm | Tại sao sai | Hướng sửa |
| --- | --- | --- |
| Dùng `-nowarn` để sửa cảnh báo | Chỉ che tín hiệu | Phân loại/sửa nguyên nhân |
| Bật `-Werror` nhưng không bật lint categories cần thiết | Nhiều warning không được sinh ra | Thêm `-Xlint`/các keys phù hợp |
| Sao chép `-Werror:key` sang JDK cũ không hỗ trợ | Build fail vì option không được nhận diện | Kiểm tra `javac --version` và tài liệu release |
| Dùng `@SuppressWarnings("all")` cho module lớn | Che cả vấn đề mới | Suppression hẹp có lý do |
| Coi `-Xlint:unchecked` sửa generics | Compiler chỉ cảnh báo | Sửa type declarations và validate boundary |
| Bỏ qua `@Deprecated(forRemoval=true)` | Phụ thuộc API có thể biến mất trong release sau | Có kế hoạch thay API |
| Dùng `-source/-target` mà quên kiểm soát API level | Có thể tham chiếu API JDK mới không phù hợp | Dùng `--release` |
| Tin Gradle/Maven chạy trên JDK 27 thì mọi task dùng javac 27 | Toolchain/fork configuration có thể khác | Kiểm tra toolchain thực và build logs |
| Formatter ở IDE khác formatter CI | Diff lặp lại | Pin engine/config, cung cấp check/apply giống nhau |
| Dùng `spotlessApply` trong CI rồi không commit | CI test source khác source review | CI dùng check, developer dùng apply |
| Coi Checkstyle là bug analyzer đầy đủ | Chủ yếu kiểm soát conventions | Kết hợp analyzer/tests thích hợp |
| Coi SpotBugs hiểu mọi Java 27 class files | Version tool có thể chưa hỗ trợ | Kiểm tra phiên bản trước khi bật |
| Cho rằng Error Prone tự hoạt động với mọi `javac` | Compiler integration nhạy với version | Kiểm tra compatibility và config |
| Coi `javadoc` tự kiểm thử runtime behavior | Chỉ kiểm tra tài liệu API | Viết tests |
| Để processor tự chạy từ classpath không kiểm soát | Khó tái lập và tăng rủi ro build | Khai báo processor path/selection tường minh |
| Bỏ qua warning generated code bằng suppression cả project | Che lỗi trong code tự viết | Exclude đúng scope, sửa generator |
| Chặn mọi warning trên legacy project ngay lập tức | Nhóm bị kẹt hoặc lách suppression | Baseline và gate theo giai đoạn |
| Tin static analysis chứng minh không có race/security issues | Phân tích có giới hạn | Threat modeling, concurrency tests, security audits |
| Không kiểm tra nguồn artifact/plugins | Build có thể nhận code khác dự kiến | Pin/verify dependencies và repositories |

## 24. Checklist review pull request

Trước khi merge một PR Java 27, hãy kiểm tra:

1. **JDK/compiler version đúng chưa?** `javac --version` và build toolchain phải khớp.
2. **Target release đúng chưa?** Dự án dùng Java 27 hay cần tương thích thấp hơn?
3. **Có compiler errors không?** Bất kỳ lỗi nào đều phải được xử lý.
4. **Cảnh báo mới thuộc lint category nào?** Đọc nguyên nhân trước khi suppress.
5. **Có unchecked/raw types ở boundary không?** Kiểm tra generic contracts và dữ liệu runtime.
6. **Có dùng deprecated/forRemoval API không?** Đã xem phương án thay thế chưa?
7. **Có bất thường switch/finally/try-with-resources không?** Ưu tiên các warning có ảnh hưởng logic.
8. **Mã đã qua formatter check chưa?** Không để CI tự sửa source rồi bỏ qua diff.
9. **Analyzer nào đã chạy?** Phân biệt javac lint với PMD, Checkstyle, SpotBugs, Error Prone.
10. **Phiên bản analyzer đã xác nhận hỗ trợ Java 27 chưa?** Kiểm tra parser/classfile support.
11. **Findings nghiêm trọng đã được triage chưa?** Không chỉ xóa cảnh báo bằng comment.
12. **Generated code có được phân loại đúng không?** Không sửa file sẽ bị generator ghi đè.
13. **Annotation processing được khai báo tường minh chưa?** Biết processor nào chạy trong build.
14. **Dependency/tool versions có được pin không?** Cần nhất quán local/CI.
15. **Các test liên quan đã chạy chưa?** Static analysis không thay hành vi thực tế.
16. **Javadoc API có được kiểm tra bằng DocLint không?** Đặc biệt với public library.
17. **Có baseline warning không?** PR không được làm tăng nợ kỹ thuật vô hình.
18. **Build cuối có tạo đúng artifact không?** Compilation pass riêng chưa đủ cho release.

**Kết luận:** Compiler warnings của Java 27 cho bạn biết **chỗ nào compiler thấy rủi ro**; `-Xlint` giúp mở rộng phạm vi; `-Werror` giúp biến những warning đã chọn thành **quality gate**. Formatter giữ **cách viết nhất quán**, còn static analyzers và kiểm thử bảo vệ thêm những mặt **ngữ nghĩa và hành vi**. Hệ thống có chất lượng tốt không cần chặn mọi cảnh báo từ ngày đầu, mà cần **policy rõ ràng, phiên bản công cụ ổn định và lộ trình giảm cảnh báo có kiểm chứng**.

## 25. Tài liệu chính thức và công cụ tham khảo

### 25.1. Java SE 27 / JDK 27

- [The `javac` Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html): `--help-lint`, `-Xlint`, `-Werror`/`-Werror:key`, `--release`, `-Xdoclint`, annotation processing và compiler diagnostics.
- [The `javadoc` Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javadoc.html): `-Xdoclint`, các nhóm kiểm tra tài liệu, phạm vi truy cập và xử lý tham chiếu.
- [`java.lang.SuppressWarnings` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/SuppressWarnings.html): cách suppress compiler warnings theo phạm vi declaration.
- [`java.lang.Deprecated` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Deprecated.html): `since` và `forRemoval`.
- [Java Compiler API — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.compiler/javax/tools/JavaCompiler.html): điều khiển compilation qua API khi xây công cụ tích hợp.

### 25.2. Build tools và static analysis

- [Gradle — Building Java & JVM Projects](https://docs.gradle.org/current/userguide/building_java_projects.html): toolchains, `JavaCompile`, target release và cách cấu hình compiler flags.
- [Gradle — CompileOptions](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.compile.CompileOptions.html): `compilerArgs`, encoding, release và warning-related options.
- [Apache Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/): `release`, `compilerArgs` và cấu hình Java compilation.
- [Maven Compiler Plugin — Pass Compiler Arguments](https://maven.apache.org/components/plugins/maven-compiler-plugin-4.x/examples/pass-compiler-arguments.html): hướng dẫn truyền lệnh `-Xlint` tới `javac`; lưu ý dòng tài liệu Maven 4/plugin 4.x có khác cấu hình Maven 3/plugin 3.x.
- [Spotless](https://github.com/diffplug/spotless): formatter check/apply cho Gradle và Maven.
- [Google Java Format](https://github.com/google/google-java-format): formatter source Java.
- [Checkstyle](https://checkstyle.org/): quy ước mã và style checks.
- [PMD](https://pmd.github.io/): static analysis dựa trên source.
- [SpotBugs](https://spotbugs.github.io/): bug-pattern analysis trên bytecode.
- [Error Prone](https://errorprone.info/): bug checks kết hợp với `javac`; kiểm tra compatibility khi nâng JDK.

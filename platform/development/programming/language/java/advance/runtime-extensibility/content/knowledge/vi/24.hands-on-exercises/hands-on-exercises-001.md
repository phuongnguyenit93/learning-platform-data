# Xây ứng dụng xử lý tài liệu với hợp đồng và hai provider SPI

## 1. Mục tiêu bài thực hành

Bài tập xây dựng một ứng dụng Java xử lý tài liệu bằng **Service Provider Interface (SPI)**. Host không import hoặc khởi tạo trực tiếp implementation. Thay vào đó, host chỉ phụ thuộc **hợp đồng `DocumentProcessor`**, còn hai JAR provider đăng ký implementation qua `META-INF/services` và được `ServiceLoader` khám phá tại runtime.

Sau bài thực hành, bạn có thể:

- Thiết kế API ổn định để plugin trả về kết quả xử lý tài liệu.
- Đóng gói **hai provider độc lập** với hai hành vi rõ ràng: đếm từ (`word-count`) và thống kê dòng (`line-count`).
- Dùng `ServiceLoader` tìm provider, chọn theo `id()`, xử lý trùng ID, không tìm thấy provider và lỗi trong plugin.
- Biên dịch, đóng gói và chạy project trên **Java 17+** bằng `javac`, `jar`, `java` mà không cần Maven/Gradle.
- Chứng minh tính mở rộng: bỏ một provider JAR thì provider còn lại vẫn hoạt động; bổ sung JAR mới không cần biên dịch lại host.

**Phạm vi:** Dữ liệu đầu vào là văn bản thuần UTF-8, không phải parser PDF/DOCX. Đếm từ và dòng dùng quy tắc minh bạch để kiểm thử được; khi cần định dạng tài liệu khác, có thể thêm provider mới tuân thủ cùng contract.

## 2. Kiến trúc: host ↔ contract ↔ providers

```text
                      +--------------------------+
                      | DocumentApp (host)       |
                      | ServiceLoader.load(...)  |
                      +-------------+------------+
                                    |
                                    v
                      +--------------------------+
                      | DocumentProcessor (API)  |
                      | id(), process(String)   |
                      +-------------+------------+
                                    ^
                       implements  | implements
                  +-----------------+------------------+
                  |                                    |
       +----------+-----------+            +-----------+----------+
       | WordCountProcessor   |            | LineCountProcessor   |
       | provider-word.jar    |            | provider-line.jar    |
       +----------------------+            +----------------------+
```

**Nguyên tắc class identity:** `DocumentProcessor` phải được định nghĩa **một lần** và chia sẻ cho host và cả hai provider. Ví dụ này dùng class path: `api.jar` là một artifact chung; **không đóng gói bản sao contract class vào hai provider JAR**. Nếu contract bị định nghĩa bởi nhiều class loader khác nhau, provider có thể không assignable tới interface host đang dùng.

## 3. Cấu trúc thư mục

```text
document-spi/
├── api/
│   └── src/demo/api/
│       ├── DocumentProcessor.java
│       └── ProcessingResult.java
├── host/
│   └── src/demo/host/DocumentApp.java
├── provider-word/
│   ├── src/demo/word/WordCountProcessor.java
│   └── resources/META-INF/services/demo.api.DocumentProcessor
└── provider-line/
    ├── src/demo/line/LineCountProcessor.java
    └── resources/META-INF/services/demo.api.DocumentProcessor
```

Các lệnh dưới đây chạy từ thư mục gốc `document-spi/`, dùng shell POSIX (Linux/macOS/Git Bash) và JDK 17+. Trên Windows PowerShell/cmd cần điều chỉnh dấu nối dòng và class path separator (`;` thay vì `:`).

## 4. Thiết kế hợp đồng SPI

Một hợp đồng tốt không nên phụ thuộc class của provider cụ thể. Dùng ID ổn định để chọn chức năng, method `process` nhận tài liệu dưới dạng `String`, kết quả được biểu diễn bởi `record` chỉ gồm các kiểu Java chuẩn.

### 4.1. Interface

File `api/src/demo/api/DocumentProcessor.java`:

```java
package demo.api;

public interface DocumentProcessor {
    /** ID duy nhất, ổn định của provider, ví dụ word-count. */
    String id();

    /** Xử lý nội dung văn bản, không ghi file và không in stdout. */
    ProcessingResult process(String document);
}
```

### 4.2. Kiểu kết quả chung

File `api/src/demo/api/ProcessingResult.java`:

```java
package demo.api;

import java.util.Objects;

public record ProcessingResult(String processorId, String description, long value) {
    public ProcessingResult {
        Objects.requireNonNull(processorId, "processorId");
        Objects.requireNonNull(description, "description");
        if (value < 0) throw new IllegalArgumentException("value must be >= 0");
    }
}
```

`record` sẵn có trên Java 17. Contract dùng kiểu kết quả thuần dữ liệu giúp host không phải cast sang implementation. Nếu đổi method signature hoặc record format sau này, cần versioning API và kiểm tra binary compatibility của các plugin JAR.

## 5. Provider 1: đếm từ

Quy ước: một **từ** là nhóm ký tự không phải whitespace theo regex Java `\S+`. Trên chuỗi rỗng hoặc toàn dấu cách, kết quả 0. Đây là quy tắc token hóa đơn giản, không phải word segmentation chuẩn cho mọi ngôn ngữ.

File `provider-word/src/demo/word/WordCountProcessor.java`:

```java
package demo.word;

import demo.api.DocumentProcessor;
import demo.api.ProcessingResult;
import java.util.Objects;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class WordCountProcessor implements DocumentProcessor {
    private static final Pattern TOKEN = Pattern.compile("\\S+");

    public WordCountProcessor() {}

    @Override
    public String id() {
        return "word-count";
    }

    @Override
    public ProcessingResult process(String document) {
        Objects.requireNonNull(document, "document");
        long count = 0;
        Matcher matcher = TOKEN.matcher(document);
        while (matcher.find()) count++;
        return new ProcessingResult(id(), "Từ", count);
    }
}
```

File **`provider-word/resources/META-INF/services/demo.api.DocumentProcessor`** phải chứa đúng binary name của implementation:

```text
demo.word.WordCountProcessor
```

Đây là phần cấu hình bắt buộc của SPI class path. Tên file là **tên fully qualified của service interface**, không phải tên plugin ID hay tên JAR.

## 6. Provider 2: đếm dòng

Quy ước: tài liệu rỗng có 0 dòng; chuỗi không rỗng có `1 + số ký tự '\n'`, nhưng nếu kết thúc bằng newline thì newline cuối chỉ là ký tự kết thúc dòng, không tạo thêm một dòng trống mới. Tức `"a\nb\n"` có 2 dòng, còn `"a\nb"` cũng có 2 dòng. `\r\n` được xem là một dòng mới bởi vì có `\n`.

File `provider-line/src/demo/line/LineCountProcessor.java`:

```java
package demo.line;

import demo.api.DocumentProcessor;
import demo.api.ProcessingResult;
import java.util.Objects;

public final class LineCountProcessor implements DocumentProcessor {
    public LineCountProcessor() {}

    @Override
    public String id() {
        return "line-count";
    }

    @Override
    public ProcessingResult process(String document) {
        Objects.requireNonNull(document, "document");
        if (document.isEmpty()) {
            return new ProcessingResult(id(), "Dòng", 0);
        }

        long count = 1;
        for (int i = 0; i < document.length(); i++) {
            if (document.charAt(i) == '\n') count++;
        }
        if (document.charAt(document.length() - 1) == '\n') count--;
        return new ProcessingResult(id(), "Dòng", count);
    }
}
```

File **`provider-line/resources/META-INF/services/demo.api.DocumentProcessor`**:

```text
demo.line.LineCountProcessor
```

Trong production, cần xác định cách xử lý `\r` đơn lẻ, Unicode line separator, dòng trống và encoding. Bài này dùng quy ước tối giản để thấy rõ cách provider triển khai logic độc lập với host.

## 7. Host: khám phá và chọn provider

Host chỉ import `demo.api.*`, không tham chiếu hai class implementation. `ServiceLoader` tải danh sách provider qua SPI descriptors trên class path. Vì thứ tự discovery không nên được dùng làm nghiệp vụ, host đưa providers vào `TreeMap` để liệt kê ổn định theo ID.

File `host/src/demo/host/DocumentApp.java`:

```java
package demo.host;

import demo.api.DocumentProcessor;
import demo.api.ProcessingResult;
import java.util.Map;
import java.util.ServiceLoader;
import java.util.TreeMap;

public final class DocumentApp {
    public static void main(String[] args) {
        Map<String, DocumentProcessor> providers = new TreeMap<>();

        for (DocumentProcessor provider :
                ServiceLoader.load(DocumentProcessor.class)) {
            String id = provider.id();
            if (id == null || id.isBlank()) {
                throw new IllegalStateException("Invalid provider ID");
            }
            if (providers.putIfAbsent(id, provider) != null) {
                throw new IllegalStateException("Duplicate provider ID: " + id);
            }
        }

        if (providers.isEmpty()) {
            System.err.println("Không có provider SPI được tìm thấy");
            System.exit(1);
        }

        String document = "Xin chào Java\nSPI xử lý tài liệu\n";
        System.out.println("Available providers: " + providers.keySet());
        for (DocumentProcessor processor : providers.values()) {
            ProcessingResult result = processor.process(document);
            System.out.println(result.processorId() + " => "
                    + result.description() + ": " + result.value());
        }

        if (args.length > 0) {
            DocumentProcessor selected = providers.get(args[0]);
            if (selected == null) {
                System.err.println("Unknown provider: " + args[0]);
                System.exit(2);
            }
            System.out.println("Selected: " + selected.id());
        }
    }
}
```

**Vì sao `ServiceLoader` có thể nhìn thấy provider?** `java` khởi động với cả `provider-word.jar` và `provider-line.jar` trên class path, chứa đúng `META-INF/services/demo.api.DocumentProcessor`. Application class loader đọc service descriptor, nạp implementation, gọi public constructor không tham số, rồi trả các instance cho host.

Nếu provider constructor hoặc class loading lỗi, `ServiceLoader` có thể ném `ServiceConfigurationError` (một `Error`) trong lúc duyệt. Không nên `catch(Throwable)` để bỏ qua các lỗi nghiêm trọng. Production cần phân biệt provider invalid, fail to initialize và policy không chấp nhận.

## 8. Biên dịch và đóng gói bằng JDK 17+

### 8.1. Tạo thư mục build

```bash
mkdir -p build/api build/host build/word build/line dist
```

### 8.2. Biên dịch contract

```bash
javac -encoding UTF-8 -d build/api \
  api/src/demo/api/DocumentProcessor.java \
  api/src/demo/api/ProcessingResult.java
jar --create --file dist/document-api.jar -C build/api .
```

### 8.3. Biên dịch hai providers

```bash
javac -encoding UTF-8 -cp dist/document-api.jar -d build/word \
  provider-word/src/demo/word/WordCountProcessor.java

javac -encoding UTF-8 -cp dist/document-api.jar -d build/line \
  provider-line/src/demo/line/LineCountProcessor.java
```

### 8.4. Đóng gói JAR và service descriptor

```bash
jar --create --file dist/provider-word.jar \
  -C build/word . \
  -C provider-word/resources META-INF

jar --create --file dist/provider-line.jar \
  -C build/line . \
  -C provider-line/resources META-INF
```

Kiểm tra nội dung:

```bash
jar --list --file dist/provider-word.jar
jar --list --file dist/provider-line.jar
```

Cả hai JAR phải chứa `META-INF/services/demo.api.DocumentProcessor` tương ứng. Không đóng gói `demo/api/DocumentProcessor.class` vào provider JAR.

### 8.5. Biên dịch host

```bash
javac -encoding UTF-8 -cp dist/document-api.jar -d build/host \
  host/src/demo/host/DocumentApp.java
jar --create --file dist/document-host.jar -C build/host .
```

### 8.6. Chạy với cả hai providers

```bash
java -cp 'dist/document-api.jar:dist/document-host.jar:dist/provider-word.jar:dist/provider-line.jar' \
  demo.host.DocumentApp
```

Stdout chính xác:

```text
Available providers: [line-count, word-count]
line-count => Dòng: 2
word-count => Từ: 8
```

Giải thích phép đếm: tài liệu gồm `Xin chào Java` (3 token) và `SPI xử lý tài liệu` (5 token); có 2 dòng và newline cuối không tạo dòng thứ ba. Thứ tự provider ổn định theo `TreeMap` thay vì phụ thuộc thứ tự ServiceLoader discovery.

### 8.7. Chọn provider theo ID

```bash
java -cp 'dist/document-api.jar:dist/document-host.jar:dist/provider-word.jar:dist/provider-line.jar' \
  demo.host.DocumentApp word-count
```

Output thêm một dòng:

```text
Selected: word-count
```

Host vẫn chạy cả hai provider trong phần demo rồi mới in lựa chọn. Trong ứng dụng thực, việc lọc provider có thể diễn ra trước xử lý, và nếu cần chọn **một** implementation thì chỉ gọi `process` trên provider được chọn.

## 9. Kiểm thử tính độc lập của các provider

### 9.1. Chỉ cài một provider

Bỏ provider line khỏi class path:

```bash
java -cp 'dist/document-api.jar:dist/document-host.jar:dist/provider-word.jar' \
  demo.host.DocumentApp
```

Stdout:

```text
Available providers: [word-count]
word-count => Từ: 8
```

Điều này chứng minh host không cần liên kết trực tiếp với `LineCountProcessor` để hoạt động. Nếu bỏ cả hai provider JAR, host trả mã lỗi 1 với thông báo `Không có provider SPI được tìm thấy` trên stderr.

### 9.2. Provider ID không tồn tại

Chạy cả hai providers và truyền argument `missing`:

```bash
java -cp 'dist/document-api.jar:dist/document-host.jar:dist/provider-word.jar:dist/provider-line.jar' \
  demo.host.DocumentApp missing
```

Host in hai kết quả rồi in `Unknown provider: missing` ra stderr, kết thúc với exit code 2. Đây là xử lý yêu cầu chọn plugin không tồn tại, khác với lỗi SPI discovery.

### 9.3. Trùng ID

Nếu một provider mới cũng trả `id() == "word-count"`, chương trình từ chối trong lúc tạo registry. Chính sách trùng ID phải được xác định trước: fail-fast là lựa chọn an toàn hơn thay vì chọn ngẫu nhiên provider đầu tiên.

### 9.4. Provider ném lỗi khi xử lý

Trong production, `process` có thể ném exception do nội dung tài liệu sai, thiếu dependency, I/O hoặc lỗi plugin. Host nên ghi lỗi theo provider ID và quyết định fallback có cho phép không. **Không mặc định chuyển dữ liệu sang provider khác** nếu semantics khác nhau (ví dụ từ đếm từ sang đếm dòng).

## 10. Mở rộng sang plugin nạp động

Ví dụ hiện tại dùng class path lúc khởi động. Trong hệ thống cần cài JAR khi JVM đang chạy, có thể dùng một `URLClassLoader` mới rồi tạo `ServiceLoader.load(DocumentProcessor.class, pluginLoader)`. Phải bảo đảm plugin loader nhìn thấy **cùng contract API class** mà host sử dụng.

Phác thảo API, **chưa phải chương trình độc lập**:

```java
URL[] jars = { Path.of("plugins/provider-new.jar").toUri().toURL() };
URLClassLoader pluginLoader = new URLClassLoader(
        jars, DocumentProcessor.class.getClassLoader());

ServiceLoader<DocumentProcessor> loader =
        ServiceLoader.load(DocumentProcessor.class, pluginLoader);
for (DocumentProcessor processor : loader) {
    System.out.println(processor.id());
}
```

Cần import `java.net.URL`, `java.net.URLClassLoader`, `java.nio.file.Path`, `java.util.ServiceLoader`. Khi không còn dùng, dừng provider, giải phóng resource, hủy registry/callback rồi đóng loader. `URLClassLoader.close()` không bảo đảm unloading class tức thì.

Nếu chuyển sang JPMS named modules, contract có thể khai báo `module demo.api { exports demo.api; }`, host khai báo `uses demo.api.DocumentProcessor`, provider khai báo `provides demo.api.DocumentProcessor with ...`, và runtime cần module path/layer được resolve đúng. Đó là một biến thể triển khai khác với service descriptor class path đã xây ở bài này.

## 11. Thiết kế lifecycle, bảo mật và độ tin cậy

Trong thực tế, provider có thể không chỉ tính toán trên `String` mà còn truy cập file/DB/network. Cần thêm các điều kiện:

1. **Hợp đồng versioned:** có chính sách tương thích API và metadata capability để tránh plugin biên dịch theo bản contract không phù hợp.
2. **Input validation:** giới hạn kích thước tài liệu, encoding, độ sâu cấu trúc, đường dẫn hoặc định dạng được phép.
3. **Tài nguyên:** nếu provider có executor/connection, cần `start/stop` hoặc `AutoCloseable` và rollback đúng thứ tự khi startup lỗi.
4. **Trust boundary:** chỉ nạp artifact đã kiểm tra nguồn gốc, chữ ký/hash và dependency; class loader không phải sandbox cho mã không tin cậy.
5. **Observability:** log provider ID, version, thời gian xử lý, lỗi và tài nguyên; không log nội dung tài liệu nhạy cảm.
6. **Concurrency:** contract phải xác định provider là singleton thread-safe, instance-per-request hay được đồng bộ bởi host.
7. **Fallback:** chỉ tự chuyển provider khi chúng được xác nhận có cùng semantics và dữ liệu không bị xử lý trùng.

## 12. Checklist nghiệm thu

- [ ] Contract interface và result record nằm trong `document-api.jar` duy nhất.
- [ ] Hai implementation không phụ thuộc nhau và mỗi JAR có descriptor SPI chính xác.
- [ ] Host chỉ import package `demo.api`, không import `demo.word` hoặc `demo.line`.
- [ ] Chạy được trên Java 17+ và stdout khớp phần hướng dẫn.
- [ ] Khi bỏ provider-line JAR, provider-word vẫn được khám phá.
- [ ] Khi thiếu cả hai provider, host báo lỗi và không chạy tiếp.
- [ ] Khi trùng provider ID, host từ chối thay vì chọn tùy ý.
- [ ] Có chính sách version, kiểm tra artifact và lifecycle nếu triển khai thực tế.

**Kết luận:** Với Java SPI, host lập trình theo interface chứ không theo implementation. Hai provider độc lập được đóng gói và phát hiện bằng `ServiceLoader`, nên ứng dụng có thể mở rộng chức năng xử lý tài liệu mà không sửa code host. Khi tiến tới plugin nạp động hoặc JPMS, nguyên tắc quan trọng nhất vẫn là giữ contract chung ổn định, định nghĩa rõ capability và quản lý vòng đời provider.

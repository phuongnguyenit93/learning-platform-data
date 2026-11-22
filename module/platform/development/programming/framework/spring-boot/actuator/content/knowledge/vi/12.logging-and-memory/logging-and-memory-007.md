# Tạo heap dump và kiểm tra định dạng phù hợp với JVM

## 1. Heap dump cho biết điều gì?

**Heap dump** là bản chụp dữ liệu trên vùng nhớ heap của một JVM tại thời điểm thu thập. Nó giúp khảo sát các đối tượng, lớp và quan hệ tham chiếu để tìm hiểu vì sao bộ nhớ đang bị giữ lại.

Ví dụ, một dịch vụ đã xử lý xong nhiều yêu cầu nhưng một danh sách dùng chung vẫn giữ dữ liệu của tất cả yêu cầu cũ. Log có thể cho biết thời điểm xử lý; heap dump giúp tìm đối tượng nào còn giữ các dữ liệu đó.

Cần phân biệt các nguồn bằng chứng:

| Nguồn dữ liệu | Câu hỏi chính |
| --- | --- |
| Log | Sự kiện nào đã xảy ra, theo trình tự nào? |
| Thread dump | Các luồng đang thực hiện hoặc chờ ở đâu? |
| Histogram đối tượng | Có bao nhiêu đối tượng theo từng lớp, chiếm khoảng bao nhiêu bộ nhớ? |
| Heap dump | Đối tượng nào đang tồn tại và liên kết, giữ tham chiếu đến nhau ra sao? |
| System/core dump | Trạng thái bộ nhớ và tiến trình ở phạm vi rộng hơn heap Java, tùy JVM/hệ điều hành |

Một heap dump không tự kết luận có rò rỉ bộ nhớ. Bộ đệm lớn nhưng hợp lệ và tập đối tượng bị giữ lại ngoài dự kiến có thể trông giống nhau nếu chỉ nhìn tổng dung lượng. Cần kết hợp thời điểm thu thập, tải hệ thống và quan hệ tham chiếu.

Trong Spring Boot 3.3, endpoint `heapdump` cung cấp dump của **JVM đang chạy chính ứng dụng nhận yêu cầu**, qua `GET /actuator/heapdump`. Phản hồi là dữ liệu nhị phân và có thể lớn; cần lưu ra tệp để phân tích. [Heap Dump REST API — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/heapdump.html)

## 2. Định dạng phụ thuộc vào JVM

Không nên bắt đầu bằng giả định “heap dump Java luôn là tệp .hprof”.

| JVM chạy ứng dụng | Định dạng heap dump được Actuator cung cấp | Điều cần kiểm tra |
| --- | --- | --- |
| HotSpot | HPROF | Header HPROF và khả năng đọc của công cụ phân tích |
| Eclipse OpenJ9 | PHD — Portable Heap Dump | Header PHD và bộ đọc hỗ trợ OpenJ9/PHD |
| JVM hoặc runtime tùy biến khác | Không suy ra chỉ từ phiên bản Java | Cơ chế dump được JVM và bản Spring Boot đang dùng hỗ trợ |

Spring Boot công bố rõ sự khác nhau HPROF trên HotSpot và PHD trên OpenJ9. Hai tệp có thể cùng được tải từ URL `/actuator/heapdump` nhưng không cùng cấu trúc nhị phân. [Heapdump format](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/heapdump.html)

**Tên tệp không quyết định định dạng.** Nếu lưu phản hồi OpenJ9 thành `heapdump.hprof`, dữ liệu vẫn là PHD. Đổi tên tệp không chuyển đổi PHD sang HPROF.

Cũng không được dùng riêng tên nhà cung cấp JDK để suy ra máy ảo. Khi ghi nhận môi trường, nên giữ cả tên JVM và phiên bản thực tế của tiến trình:

```java
System.out.println("java.vm.name=" + System.getProperty("java.vm.name"));
System.out.println("java.vm.version=" + System.getProperty("java.vm.version"));
System.out.println("java.vendor=" + System.getProperty("java.vendor"));
System.out.println("java.version=" + System.getProperty("java.version"));
```

Đây là **đoạn mã đặt trong ứng dụng hoặc chương trình chẩn đoán**, không phải một lớp Java chạy độc lập. Giá trị cụ thể thay đổi theo môi trường.

Lệnh `java -version` ở terminal chỉ cho biết executable `java` mà terminal chọn. Ứng dụng đang chạy có thể sử dụng JDK khác hoặc nằm trong container khác.

Với một tiến trình HotSpot mà bạn có quyền chẩn đoán, có thể dùng:

```text
jcmd <PID_THỰC_TẾ> VM.version
```

Thay `<PID_THỰC_TẾ>` bằng PID của đúng ứng dụng. Dùng công cụ JDK phù hợp phiên bản và thực hiện trong ngữ cảnh có thể attach vào tiến trình đích; đừng suy ra thông tin JVM của ứng dụng chỉ từ máy đang tải tệp. [JDK 21 diagnostic tools](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html)

## 3. Chuẩn bị endpoint heapdump trong Spring Boot 3.3

### 3.1. Dependency và cấu hình

Với một ứng dụng web Spring MVC đã có Spring Boot và cơ chế quản lý phiên bản dependency, phần khai báo Gradle thường gồm:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Đây là **đoạn bổ sung vào build hiện có**, không phải toàn bộ một dự án độc lập. Ứng dụng WebFlux dùng starter tương ứng; không cần thêm cả MVC lẫn WebFlux để lấy heap dump.

Cấu hình minh họa:

```properties
management.endpoint.heapdump.enabled=true
management.endpoints.web.exposure.include=health,heapdump
```

Trong dòng Spring Boot 3.3, bật endpoint và công bố qua HTTP là hai điều kiện riêng. Mặc định chỉ `health` được công bố qua HTTP; nếu `heapdump` có mặt trong danh sách `exclude` thì việc loại trừ được ưu tiên hơn `include`. [Enabling and Exposing Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.enabling)

Cấu hình trên dùng URL mặc định `/actuator/heapdump`. Nếu đổi management port, context path, base path hoặc ánh xạ endpoint thì phải dùng URL tương ứng.

### 3.2. Quyền truy cập và khả năng tạo tệp

Công bố endpoint không thay thế quy tắc bảo mật. Nếu ứng dụng dùng Spring Security, cần dùng tài khoản và quyền phù hợp với cấu hình hiện tại. Không nên giải quyết lỗi 401/403 bằng cách mở heap dump cho mọi người.

Ngoài HTTP, còn cần khả năng tạo dump trong JVM và quyền ghi tệp tạm ở phía ứng dụng. Việc máy khách còn nhiều ổ đĩa không giúp được nếu thư mục tạm hoặc volume của container ứng dụng đã đầy.

Heap dump có thể chứa dữ liệu nhạy cảm của ứng dụng; với HPROF, giá trị chuỗi và dữ liệu đối tượng có thể xuất hiện trong nội dung. Vì vậy, chỉ cung cấp endpoint cho người cần chẩn đoán và lưu tệp ở nơi kiểm soát quyền truy cập. Không coi cơ chế che giá trị trên một endpoint cấu hình khác là cơ chế tự làm sạch heap dump.

### 3.3. Dự trù tác động khi thu thập

Tạo dump có thể làm JVM tạm dừng và tạo lượng I/O đáng kể. Thời gian và kích thước phụ thuộc heap, lượng đối tượng, JVM, thiết bị lưu trữ và cách thu thập; không có một con số cố định áp dụng cho mọi ứng dụng.

Trước khi lấy dump, cần xác định đúng tiến trình/bản sao ứng dụng, thời điểm và dung lượng dự kiến ở cả phía tạo tệp lẫn phía tải về. Không đưa thao tác này vào vòng thăm dò lặp lại hoặc kiểm tra sức khỏe định kỳ.

Nếu dịch vụ có nhiều bản sao sau bộ cân bằng tải, một request có thể tới bất kỳ bản sao nào được định tuyến. Ghi nhận bản sao ứng dụng (instance) thực sự tạo dump; không ghép kết luận về bộ nhớ của một bản sao với số liệu của bản sao khác.

## 4. Tải đúng dữ liệu nhị phân và kiểm tra HTTP

### 4.1. Lưu tệp bằng curl

Trong PowerShell, dùng `curl.exe` để gọi đúng chương trình curl, tránh nhầm với alias ở một số môi trường:

```powershell
curl.exe --fail --show-error --dump-header heapdump.headers.txt --output heapdump.bin --write-out "HTTP_STATUS=%{http_code}\n" "http://localhost:8080/actuator/heapdump"
```

Trên Linux/macOS dùng cùng các tùy chọn với `curl` thay cho `curl.exe`:

```bash
curl --fail --show-error --dump-header heapdump.headers.txt --output heapdump.bin --write-out 'HTTP_STATUS=%{http_code}\n' 'http://localhost:8080/actuator/heapdump'
```

Hai tệp được tạo ở **máy chạy curl**:

- `heapdump.headers.txt` chứa header HTTP để đối chiếu.
- `heapdump.bin` chứa body tải về; dùng đuôi trung tính trước khi xác định định dạng.

Dùng tên tệp mới cho mỗi lần thu thập để tránh ghi đè bằng chứng trước đó. Không cần in dữ liệu nhị phân ra terminal.

Nếu ứng dụng dùng Basic authentication, có thể thêm `--user operator` để curl hỏi mật khẩu tương tác, với điều kiện `operator` là tài khoản thực sự đã được cấp quyền. Nếu hệ thống dùng cơ chế khác, áp dụng cơ chế đó thay vì tự thay đổi bảo mật ứng dụng.

### 4.2. Phải kiểm tra kết quả, không chỉ kiểm tra tệp đã xuất hiện

Với yêu cầu lấy toàn bộ dump, cần thấy HTTP 200 và tải hoàn tất không lỗi. `--fail` giúp báo lỗi cho các phản hồi HTTP từ 400 trở lên, nhưng không thay thế việc kiểm tra redirect, nội dung hoặc một lần truyền bị ngắt.

Một trang đăng nhập trả HTTP 200 cũng có thể bị lưu vào `heapdump.bin`. Phản hồi chuyển hướng 302 cần được xử lý theo luồng xác thực của hệ thống, không tự coi là dump thành công.

Cần kiểm tra tiếp:

1. Mã thoát của curl và HTTP status.
2. Tệp có dung lượng lớn hơn 0.
3. Header nhị phân phù hợp với định dạng dự kiến.
4. Công cụ phân tích đọc được cấu trúc tài liệu.

`Content-Type: application/octet-stream` chỉ mô tả dữ liệu nhị phân chung; nó không phân biệt HPROF với PHD. Không dùng riêng media type hoặc đuôi tệp làm bằng chứng định dạng.

**Không dùng `curl -I` hoặc chỉ lấy header để thay cho việc tải dump.** Mục tiêu là thu được và kiểm tra toàn bộ body; việc thử endpoint nhiều lần cũng có thể tạo nhiều lần thu thập tốn tài nguyên.

### 4.3. Tách vị trí tệp phía máy chủ và máy khách

```text
JVM ứng dụng
    → tạo tệp dump ở phía máy chủ
    → truyền body qua HTTP
    → curl ghi tệp ở máy khách
    → công cụ phân tích đọc tệp đã tải
```

`--output heapdump.bin` chỉ chọn tên tệp phía curl. Nó không yêu cầu JVM ghi tệp máy chủ vào cùng đường dẫn đó.

Nếu dùng một cơ chế JVM ghi trực tiếp ra tệp thay vì tải HTTP, đường dẫn thuộc máy chứa JVM, không thuộc laptop đang điều khiển chẩn đoán. Đây là điểm dễ nhầm khi làm việc với container và máy chủ từ xa.

## 5. Kiểm tra header trước khi mở bằng công cụ phân tích

### 5.1. Dấu hiệu nhận diện ban đầu

| Dấu hiệu ở đầu tệp | Nhận định ban đầu |
| --- | --- |
| Chuỗi `JAVA PROFILE ` | Có header của HPROF |
| Chuỗi UTF `portable heap dump` theo cấu trúc PHD | Có header của PHD |
| Hai byte `1F 8B` | Là vỏ nén GZIP; cần giải nén hoặc dùng bộ đọc hỗ trợ nén rồi kiểm tra nội dung bên trong |
| JSON, HTML, tệp rỗng hoặc header khác | Chưa xác định là heap dump đúng định dạng; cần kiểm tra nguồn và HTTP |

PHD có header gồm chuỗi UTF nhận diện, phiên bản và cờ định dạng; không phải văn bản thuần chỉ vì có một đoạn chữ đọc được. [OpenJ9 Heap Dump Format](https://eclipse.dev/openj9/docs/dump_heapdump/)

Một tệp có header đúng vẫn có thể bị cắt cụt hoặc hỏng ở phần sau. Kiểm tra header là bước sàng lọc, chưa phải xác nhận tính toàn vẹn.

### 5.2. Chương trình Java 17+ nhận diện sơ bộ

Lưu thành `DumpHeaderCheck.java`. Chương trình chỉ đọc tối đa 64 byte đầu nên không đưa toàn bộ heap dump lớn vào bộ nhớ của chính nó.

```java
import java.io.ByteArrayInputStream;
import java.io.DataInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class DumpHeaderCheck {
    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException("Usage: java DumpHeaderCheck <file>");
        }

        byte[] prefix;
        try (InputStream input = Files.newInputStream(Path.of(args[0]))) {
            prefix = input.readNBytes(64);
        }

        String format = "UNKNOWN";
        String text = new String(prefix, StandardCharsets.ISO_8859_1);

        if (text.startsWith("JAVA PROFILE ")) {
            format = "HPROF_HEADER";
        } else if (prefix.length >= 2
                && (prefix[0] & 0xff) == 0x1f
                && (prefix[1] & 0xff) == 0x8b) {
            format = "GZIP_CONTAINER";
        } else {
            try (DataInputStream input = new DataInputStream(
                    new ByteArrayInputStream(prefix))) {
                if ("portable heap dump".equals(input.readUTF())) {
                    format = "PHD_HEADER";
                }
            } catch (IOException ignored) {
                // Prefix does not contain a complete PHD UTF header.
            }
        }

        System.out.println(format);
    }
}
```

Biên dịch và chạy với JDK 21:

```text
javac --release 21 -encoding UTF-8 DumpHeaderCheck.java
java DumpHeaderCheck heapdump.bin
```

Với tệp HPROF chưa nén có header phù hợp, stdout là:

```text
HPROF_HEADER
```

Với tệp lỗi JSON hoặc HTML thông thường, kết quả là `UNKNOWN`. Với PHD có header nhận diện, kết quả là `PHD_HEADER`. `GZIP_CONTAINER` chỉ xác nhận vỏ nén, không khẳng định dữ liệu bên trong là heap dump.

Chương trình này không kiểm tra toàn bộ bản ghi HPROF/PHD, không chuyển đổi định dạng và không thay thế công cụ phân tích. Sau bước nhận diện, có thể đổi tên tệp thành `.hprof` hoặc `.phd` để thuận tiện chọn bộ đọc; hành động đổi tên không thay đổi byte nào bên trong.

## 6. Thực hành HotSpot độc lập với Java 21

Ví dụ sau tạo một dump nhỏ của **chính JVM minh họa**, không lấy dữ liệu từ tiến trình ứng dụng khác và không cố gây `OutOfMemoryError`. Nó giúp kiểm chứng đường tạo HPROF mà không phụ thuộc cấu hình HTTP.

### 6.1. Chương trình hoàn chỉnh

Lưu thành `HeapDumpLab.java`:

```java
import com.sun.management.HotSpotDiagnosticMXBean;
import java.io.InputStream;
import java.lang.management.ManagementFactory;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public class HeapDumpLab {
    private static final List<byte[]> PAYLOAD = new ArrayList<>();

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Usage: java HeapDumpLab <new-file.hprof>");
        }

        Path output = Path.of(args[0]).toAbsolutePath().normalize();
        if (!output.toString().endsWith(".hprof")) {
            throw new IllegalArgumentException("Output must end with .hprof");
        }
        if (Files.exists(output)) {
            throw new IllegalArgumentException("Output already exists");
        }
        Files.createDirectories(output.getParent());

        for (int i = 0; i < 8; i++) {
            PAYLOAD.add(new byte[256 * 1024]);
        }

        HotSpotDiagnosticMXBean bean = ManagementFactory.getPlatformMXBean(
                HotSpotDiagnosticMXBean.class);
        if (bean == null) {
            throw new UnsupportedOperationException("HotSpot diagnostic MBean unavailable");
        }
        bean.dumpHeap(output.toString(), true);

        byte[] prefix;
        try (InputStream input = Files.newInputStream(output)) {
            prefix = input.readNBytes(32);
        }
        String header = new String(prefix, StandardCharsets.ISO_8859_1);

        System.out.println("DUMP_CREATED=" + Files.isRegularFile(output));
        System.out.println("HEADER_IS_HPROF=" + header.startsWith("JAVA PROFILE "));
        System.out.println("FILE_NONEMPTY=" + (Files.size(output) > 0));
    }
}
```

`PAYLOAD` giữ tám mảng, tổng dung lượng phần tử là 2 MiB, để có dữ liệu minh họa còn được tham chiếu. Đây là dữ liệu có chủ đích, không phải một thí nghiệm tự kết luận về rò rỉ bộ nhớ.

`HotSpotDiagnosticMXBean.dumpHeap(..., true)` yêu cầu chỉ thu thập các đối tượng còn sống, tức còn truy cập được qua chuỗi tham chiếu (reachable) theo cơ chế JVM. API yêu cầu tên tệp kết thúc bằng `.hprof` và báo lỗi nếu tệp đã tồn tại hoặc không thể ghi. Đây là API chẩn đoán dành cho HotSpot, không phải một API heap dump trung lập cho mọi JVM. [HotSpotDiagnosticMXBean — JDK 21](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.management/com/sun/management/HotSpotDiagnosticMXBean.html)

### 6.2. Lệnh chạy và stdout

Trong một thư mục thực hành riêng, đảm bảo `demo.hprof` chưa tồn tại:

```text
javac --release 21 -encoding UTF-8 HeapDumpLab.java
java -Xms32m -Xmx64m HeapDumpLab demo.hprof
```

Với HotSpot hỗ trợ API và có quyền ghi, stdout của chương trình là:

```text
DUMP_CREATED=true
HEADER_IS_HPROF=true
FILE_NONEMPTY=true
```

Kích thước tệp không cố định theo đúng 2 MiB dữ liệu minh họa: dump còn chứa đối tượng của runtime và các đối tượng khác trong JVM.

Chạy tiếp chương trình nhận diện ở phần trước:

```text
java DumpHeaderCheck demo.hprof
```

Kết quả mong đợi:

```text
HPROF_HEADER
```

Nếu chạy lại `HeapDumpLab` với cùng tên tệp, chương trình sẽ từ chối ghi đè. Dùng một tên mới cho lần thu thập tiếp theo.

Trên OpenJ9, không dùng chương trình HotSpot này làm tiêu chí kết luận JVM có hỗ trợ heap dump hay không. JVM khác có API/cơ chế chẩn đoán khác.

## 7. Các đường thu thập khác và phạm vi của chúng

### 7.1. Tạo dump HotSpot bằng jcmd

Với PID đã được xác định và quyền attach phù hợp:

```text
jcmd <PID_THỰC_TẾ> help GC.heap_dump
jcmd <PID_THỰC_TẾ> GC.heap_dump <ĐƯỜNG_DẪN_TỆP_MỚI.hprof>
```

Các mục trong dấu `<...>` là chỗ cần thay bằng giá trị thực tế, không gõ nguyên dấu ngoặc vào shell.

Trên HotSpot JDK 21, `GC.heap_dump` tạo HPROF. Tùy chọn `-all` có thể bao gồm cả đối tượng không còn reachable; theo tài liệu, lệnh yêu cầu thu gom rác toàn bộ (full GC) trừ khi dùng `-all`. Đây là thao tác có tác động cao, phụ thuộc nội dung/kích thước heap. [jcmd — JDK 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html#gc-heap-dump)

Đường dẫn thuộc máy chứa JVM. Trong container, PID và đường dẫn phải được hiểu theo đúng ngữ cảnh tiến trình/container, cùng quyền ghi cần thiết.

Tùy chọn của một lệnh chẩn đoán có thể khác theo JVM/phiên bản. Đọc `help` của chính tiến trình đích trước khi áp dụng biến thể từ môi trường khác.

### 7.2. Thu thập khi HotSpot gặp OutOfMemoryError

Có thể cấu hình từ lúc khởi động, ví dụ với đường dẫn Linux:

```bash
java -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/var/dumps/app-oom.hprof -jar app.jar
```

Cơ chế này khác với yêu cầu chủ động qua Actuator: JVM được cấu hình để tạo dump khi xảy ra lỗi phù hợp. Thư mục phải tồn tại, có quyền ghi và đủ dung lượng; không cố gây lỗi OOM trên dịch vụ thật chỉ để thử lệnh. [Java 21 serviceability options](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html#advanced-serviceability-options-for-java)

Không nhầm `-XX:HeapDumpPath` với đường dẫn của `curl --output`. Một bên là nơi JVM ghi khi cơ chế OOM được kích hoạt, một bên là nơi máy khách lưu phản hồi HTTP.

### 7.3. OpenJ9 và PHD

OpenJ9 có cơ chế dump riêng, gồm cấu hình `-Xdump` và API chẩn đoán của OpenJ9. Khi lấy dump từ Actuator trên OpenJ9 theo hợp đồng Spring Boot, cần chuẩn bị để đọc PHD thay vì ép dùng công cụ chỉ đọc HPROF.

PHD không tương đương HPROF ở mọi trường dữ liệu. Chẳng hạn thông tin về giá trị primitive và một số thông tin chi tiết phục vụ phân tích có thể không có như trong HPROF; giữ lại `javacore` cùng thời điểm nếu có để bổ sung ngữ cảnh. Không hứa rằng một câu truy vấn phân tích dành cho HPROF sẽ cho cùng thông tin trên PHD.

Phần hướng dẫn của Eclipse Memory Analyzer mô tả khả năng đọc dump IBM/OpenJ9 bằng bộ đọc DTFJ và sự khác nhau giữa PHD, HPROF, system dump. [Acquiring Heap Dumps — Eclipse MAT](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/tasks/acquiringheapdump.html)

## 8. Chọn công cụ phân tích phù hợp và xác minh tệp đọc được

Sau khi tải và nhận diện định dạng:

1. Chọn công cụ/bộ đọc hỗ trợ đúng HPROF hoặc OpenJ9/PHD và phiên bản liên quan.
2. Với Eclipse Memory Analyzer (MAT), mở `File → Open Heap Dump`.
3. Nếu cần đọc PHD, cài bộ đọc/plug-in DTFJ theo tài liệu công cụ; tên tệp `.hprof` không thay được bộ đọc PHD.
4. Cho công cụ hoàn tất bước parse và tạo chỉ mục.
5. Chỉ khi parse thành công mới bắt đầu diễn giải histogram, cây chi phối (dominator tree) và đường tham chiếu tới GC roots.

OpenJ9 hướng dẫn sử dụng MAT hoặc IBM Memory Analyzer với plug-in DTFJ để phân tích PHD. [Analyzing OpenJ9 Heap Dumps](https://eclipse.dev/openj9/docs/dump_heapdump/#analyzing-dumps)

Cần phân biệt ba mức bằng chứng:

```text
Tải thành công qua HTTP
    ≠ đã xác nhận đúng định dạng
    ≠ đã xác nhận tệp đầy đủ và công cụ đọc được
```

Một công cụ không mở được tệp có thể do thiếu bộ đọc, thiếu bộ nhớ phân tích hoặc tệp bị hỏng. Không lập tức kết luận ứng dụng đã xuất sai dump.

Khi cần xác minh việc chuyển tệp giữa các máy, có thể so SHA-256 ở hai đầu truyền. Mã băm giống nhau chỉ chứng minh hai bản có cùng byte; nó không chứng minh tệp gốc là dump đầy đủ hoặc mô tả đúng bản sao ứng dụng cần chẩn đoán.

Sau khi parse được, ưu tiên câu hỏi cụ thể: lớp nào tăng nhiều, đối tượng nào giữ dữ liệu, đường tham chiếu nào dẫn về GC roots? Một dump cho biết trạng thái tại một thời điểm; so sánh nhiều thời điểm có điều kiện tương đương mới giúp hiểu xu hướng.

## 9. Những lỗi thường gặp

| Hiện tượng | Khả năng cần phân biệt | Hướng kiểm tra |
| --- | --- | --- |
| HTTP 404 | Sai đường dẫn, management port, endpoint bị tắt hoặc chưa công bố | URL thực tế, `enabled`, exposure và cấu hình định tuyến |
| HTTP 401/403 | Xác thực/phân quyền chưa đáp ứng | Tài khoản, vai trò và cấu hình bảo mật hiện tại |
| Tệp chỉ vài trăm byte, chứa JSON/HTML | Đã lưu thông báo lỗi/trang đăng nhập | HTTP status, redirect, header và body đầu tệp |
| Tệp có đuôi `.hprof` nhưng công cụ báo sai định dạng | Có thể là PHD hoặc một tệp khác bị đặt sai tên | JVM thực tế và header nhị phân |
| Header đúng nhưng công cụ báo unexpected EOF | Có thể tải chưa đủ hoặc tệp bị cắt cụt | Mã thoát curl, lỗi truyền, dung lượng ổ đĩa, tệp nguồn nếu còn |
| PHD không xuất hiện trong bộ chọn tệp hoặc không parse | Có thể thiếu bộ đọc phù hợp | Hỗ trợ PHD/DTFJ của công cụ |
| Công cụ parse hết bộ nhớ | Heap dump lớn so với bộ nhớ dành cho phân tích | Cấu hình JVM của công cụ, dung lượng làm việc và log parse |
| Ứng dụng lỗi khi tạo dump | Có thể thiếu dung lượng/quyền ghi hoặc cơ chế dump không hỗ trợ | Log ứng dụng, JVM/runtime, thư mục tạm và tài nguyên phía máy chủ |
| Dung lượng dump khác dung lượng heap đã cấu hình | Dump là biểu diễn dữ liệu chụp, không phải bản sao đúng kích thước `-Xmx` | Tập đối tượng được thu thập, định dạng, nén và thời điểm chụp |

Đừng dùng việc “đổi đuôi sang .hprof” như cách sửa định dạng, hoặc tạo dump liên tục để thử xem lần sau có mở được không. Xác định lớp lỗi trước khi thu thập lại.

## 10. Bài tập kiểm chứng

1. Chạy `HeapDumpLab` trên HotSpot JDK 21 và xác minh ba dòng stdout.
2. Dùng `DumpHeaderCheck` kiểm tra `demo.hprof`; kết quả phải là `HPROF_HEADER`.
3. Tạo một tệp văn bản nhỏ chứa `{"status":403,"error":"Forbidden"}` rồi kiểm tra; kết quả phải là `UNKNOWN`. Đổi đuôi tệp lỗi thành `.hprof` cũng không biến nó thành heap dump.
4. Với một ứng dụng Spring Boot thực hành có endpoint được cấp quyền, tải dump bằng curl, ghi lại HTTP status, JVM thực tế và thời điểm thu thập.
5. Chọn bộ đọc đúng định dạng và xác nhận parse thành công. Nếu môi trường dùng OpenJ9, ghi nhận PHD và hỗ trợ DTFJ thay vì áp dụng kết quả HotSpot một cách máy móc.

Kết quả cần đạt là một chuỗi bằng chứng rõ ràng: **đúng JVM/instance → thu thập hoàn tất → nhận diện đúng định dạng → bộ đọc phù hợp parse được → phân tích quan hệ giữ bộ nhớ**.

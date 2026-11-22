# Lựa chọn công cụ theo mục tiêu chức năng, hiệu năng và vận hành trong Java 11

## 1. Mục tiêu và phạm vi

Khi xây dựng ứng dụng Java, một công cụ chỉ phù hợp nếu nó **giải quyết đúng nhu cầu, đáp ứng được tải thực tế và có thể vận hành an toàn lâu dài**. Tên công cụ phổ biến hay kết quả một bài benchmark đơn lẻ chưa đủ để quyết định.

Bài này lấy **Java 11 làm mức tương thích của mã nguồn và API**. Các công cụ cốt lõi như `javac`, `java`, `java.net.http.HttpClient`, `java.nio.file.Files`, `jcmd`, Java Flight Recorder (JFR), `jdeps` và `jlink` vẫn hữu ích trong các ứng dụng Java hiện nay. Java 11 là một bản LTS đã cũ: khi bắt đầu hệ thống mới, cần xem xét một bản JDK LTS hiện được nhà cung cấp hỗ trợ (chẳng hạn 17, 21 hoặc 25) và kiểm tra yêu cầu của framework/thư viện. Nếu dự án bắt buộc hỗ trợ Java 11, mọi ví dụ trong bài phải chạy được trên Java 11.

Sau bài học, người học có thể:

- Chuyển yêu cầu chức năng, hiệu năng, vận hành thành tiêu chí có thể kiểm chứng.
- Chọn giải pháp từ JDK chuẩn trước khi cân nhắc thêm thư viện hoặc nền tảng.
- Đánh giá lựa chọn bằng thử nghiệm tải, đo đạc và khả năng triển khai, giám sát, cập nhật bảo mật.
- Giải thích được vì sao cùng một công việc có thể cần công cụ khác nhau tùy điều kiện thực tế.

## 2. Ba nhóm câu hỏi phải trả lời trước khi chọn

| Góc nhìn | Cần xác định | Minh chứng chấp nhận |
| --- | --- | --- |
| **Chức năng** | Giao thức, dữ liệu đầu vào/đầu ra, lỗi cần xử lý, tích hợp hệ thống, tính nhất quán, bảo mật | Thử nghiệm chức năng, hợp đồng API, kiểm tra tình huống lỗi và tương thích |
| **Hiệu năng** | Tải đồng thời, lưu lượng, thời gian phản hồi p95/p99, thông lượng, CPU, bộ nhớ, thời gian khởi động | Benchmark có tải và dữ liệu đại diện, kết quả theo nhiều lần chạy, hồ sơ CPU/heap/GC |
| **Vận hành** | Phiên bản JDK được vá lỗi, build tái lập, đóng gói, logs/metrics/traces, xử lý sự cố, khả năng nâng cấp | Pipeline chạy được, quan sát được lỗi, quy trình phát hành/rollback, kiểm tra bảo mật |

**Thứ tự ra quyết định:** loại phương án không đáp ứng yêu cầu bắt buộc; đo những phương án còn lại trên cùng môi trường; sau đó chọn giải pháp có chi phí phát triển và vận hành phù hợp. Không hy sinh tính đúng đắn hoặc an toàn chỉ để có một con số nhanh hơn.

Ví dụ một dịch vụ xử lý đơn hàng có thể cần: gửi HTTPS với timeout, giữ tỷ lệ lỗi trong mục tiêu, p95 dưới 250 ms ở tải đã nêu, chạy ổn định trong giới hạn RAM, có dữ liệu chẩn đoán khi chậm. Các con số trên **chỉ là ví dụ cách viết tiêu chí**, không phải mức mặc định cho mọi dự án.

## 3. Chọn theo mục tiêu chức năng

### 3.1. Truy cập API HTTP: `HttpClient` của Java 11 hay thư viện bên ngoài?

`java.net.http.HttpClient` là API chuẩn có từ Java 11, hỗ trợ HTTP/1.1, HTTP/2, kết nối HTTPS, gọi đồng bộ bằng `send` và bất đồng bộ bằng `sendAsync` với `CompletableFuture`. Nó phù hợp khi ứng dụng chủ yếu cần tự gửi HTTP request và muốn giảm phụ thuộc ngoài JDK.

- **Chọn `HttpClient` chuẩn** khi cần GET/POST/PUT thông thường, timeout, header, xử lý status/body và không có nhiều yêu cầu tích hợp đặc thù. Nên tái sử dụng một `HttpClient` thay vì liên tục tạo client cho từng request.
- **Cân nhắc HTTP client do framework quản lý** khi dự án đã có sẵn cơ chế xác thực, discovery, bộ mã hóa/giải mã, metric/tracing, chính sách retry và giới hạn lưu lượng theo chuẩn tổ chức. Việc thêm thư viện phải đem lại năng lực thực sự cần dùng.
- **Không nhầm client với server**: `HttpClient` là công cụ gọi dịch vụ khác, không phải framework xây dựng REST API server.

Dù chọn cách nào, phải định nghĩa cả **connect timeout** lẫn **request timeout** theo nhu cầu, xử lý status không thành công, tránh log token/secret và có giới hạn số lời gọi đồng thời. Retry cần có điều kiện, backoff và chú ý tính idempotent; retry mọi yêu cầu POST có thể gây tạo giao dịch trùng lặp.

Mẫu Java 11 dưới đây minh họa cấu hình và một lời gọi. URL là miền ví dụ; đoạn này cần endpoint thật để chạy và không có stdout cố định:

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.org/data"))
        .timeout(Duration.ofSeconds(5))
        .GET()
        .build();

HttpResponse<String> response =
        client.send(request, HttpResponse.BodyHandlers.ofString());

if (response.statusCode() / 100 != 2) {
    throw new IllegalStateException("HTTP " + response.statusCode());
}
String body = response.body();
```

Đoạn mã trên là **trích đoạn trong một phương thức**, yêu cầu import tương ứng, xử lý `IOException` và `InterruptedException` theo luồng ứng dụng. `HttpClient` cung cấp chuỗi hoặc byte cho response nhưng **không tự cung cấp bộ ánh xạ JSON sang domain object**; chỉ thêm thư viện JSON được duy trì khi nhu cầu này xuất hiện.

### 3.2. Đọc và ghi dữ liệu: đơn giản hay streaming?

- **Tệp văn bản nhỏ, kích thước giới hạn rõ**: `Files.readString(path, UTF_8)` và `Files.writeString(path, text, UTF_8)` của Java 11 giúp code ngắn và dễ kiểm tra.
- **Tệp lớn hoặc dữ liệu đến liên tục**: dùng `Files.newBufferedReader`, `Files.lines`, `InputStream` hoặc `BufferedReader` để xử lý từng phần; đóng tài nguyên bằng `try-with-resources`. `Files.readString` nạp toàn bộ nội dung vào bộ nhớ nên không thích hợp với tệp rất lớn.
- **Xử lý nhiều bản ghi trong bộ nhớ**: `Stream` tốt cho chuỗi biến đổi rõ ràng, nhưng vòng lặp thông thường thường dễ debug hơn khi logic phân nhánh hoặc có trạng thái. Không nên chọn `parallelStream` chỉ vì muốn “nhanh”: phải xét kích thước dữ liệu, chi phí chia việc, cấu trúc thread và tài nguyên dùng chung.

Ví dụ với tệp lớn, sau khi đã xác định encoding:

```java
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    long count = lines.filter(line -> !line.isBlank()).count();
    System.out.println("So dong khong rong: " + count);
}
```

Đây là trích đoạn cần khai báo `path` và import `Files`, `Stream`, `StandardCharsets`. Tài nguyên stream được đóng khi thoát khối. Không áp dụng mẫu trên cho dữ liệu nhị phân hoặc tệp có format cần parser chuyên dụng.

### 3.3. Công việc đồng bộ hay bất đồng bộ?

- **Luồng yêu cầu tuần tự, số cuộc gọi ít, dễ dự đoán**: gọi đồng bộ thường dễ đọc, dễ truyền lỗi và theo dõi.
- **Nhiều I/O độc lập, cần chờ các nguồn khác nhau**: `sendAsync` + `CompletableFuture` có thể giảm số luồng đang chặn trong khi chờ mạng; vẫn cần kiểm soát concurrency, timeout, lỗi kết hợp và huỷ tác vụ.
- **Tác vụ nặng CPU**: bất đồng bộ không tự làm tính toán nhanh hơn. Chỉ song song hóa khi đo được lợi ích và có tài nguyên CPU, cơ chế giới hạn tác vụ phù hợp.

Với Java 11, tránh giải pháp thiết kế dựa trên API xuất hiện ở JDK mới hơn nếu hệ thống vẫn phải chạy trên Java 11. Khả năng tương thích runtime là yêu cầu chức năng bắt buộc.

## 4. Chọn theo hiệu năng: đo vấn đề trước khi tối ưu

### 4.1. Xác định tải, môi trường và đường cơ sở

Ghi rõ số request/giây, số người dùng đồng thời, kích thước payload, cache, kết nối mạng, dung lượng dữ liệu và giới hạn CPU/RAM. Cùng một giải pháp có thể tốt ở tải nhỏ nhưng kém ở tải cao. Chạy thử với dữ liệu và thời gian warm-up thích hợp, lặp lại phép đo, ghi cả sai số/bất ổn.

Các chỉ số nên quan sát cùng nhau:

- **Độ trễ**: p50 và p95/p99; trung bình có thể che giấu nhóm request rất chậm.
- **Thông lượng**: request/giây hoặc bản ghi/giây, kèm tỷ lệ lỗi; tốc độ cao nhưng sai kết quả không phải thành công.
- **CPU và bộ nhớ**: mức sử dụng CPU, heap, non-heap và bộ nhớ thực của tiến trình; tránh chỉ nhìn `-Xmx`.
- **GC và cấp phát**: tần suất, thời lượng dừng, tốc độ cấp phát object, có hay không hết bộ nhớ.
- **Startup và kích thước runtime**: quan trọng với các chương trình chạy ngắn, job hoặc image triển khai nhỏ.

Nếu chậm do chờ database/network, thay garbage collector hay thêm thread thường không giải quyết nguyên nhân gốc. Nếu chậm do allocation/GC, cần đo heap/GC trước khi đổi cách viết mã.

### 4.2. Bắt đầu từ công cụ quan sát có trong JDK 11

JDK 11 cung cấp `jcmd` để xem trạng thái JVM, thread, heap và điều khiển Java Flight Recorder (JFR). JFR thu thập sự kiện hiệu năng để tìm điểm nóng, phân bổ bộ nhớ, thread và sự kiện JVM; công cụ JDK này vẫn là lựa chọn thực tiễn cho chẩn đoán JVM.

```bash
jcmd -l
jcmd 12345 Thread.print
jcmd 12345 JFR.start name=investigate settings=profile duration=60s filename=investigate.jfr
```

`12345` là **PID minh họa**, phải thay bằng PID thực từ `jcmd -l`. Tệp `investigate.jfr` cần được phân tích bằng công cụ hỗ trợ JFR, chẳng hạn JDK Mission Control. Khi chạy trong container, cần có quyền truy cập tiến trình và đường dẫn ghi file thích hợp. Tránh để cấu hình chẩn đoán nặng chạy vô hạn trên môi trường production.

GC logging có thể bật qua Unified Logging của JVM 11 khi cần đánh giá tác động của GC:

```bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar app.jar
```

`app.jar` là tên JAR minh họa. **G1 GC là điểm khởi đầu hợp lý trên cấu hình server phổ biến của Java 11**; hãy đo trước khi tinh chỉnh heap hoặc thay collector. ZGC có mặt ở Java 11 dưới dạng thử nghiệm, vì vậy không coi cấu hình thử nghiệm của Java 11 là phương án mặc định cho production. Nếu độ trễ GC cực thấp là yêu cầu thực sự, hãy đánh giá JVM được hỗ trợ mới hơn cùng dữ liệu benchmark phù hợp.

### 4.3. Benchmark đúng phạm vi

Không dùng số đo từ một lần chạy hoặc microbenchmark tự phát để kết luận về hiệu năng hệ thống. Nếu cần benchmark đoạn Java thuần tính toán, có thể dùng JMH phù hợp với JDK mục tiêu; nếu cần biết dịch vụ có đáp ứng SLO không, phải thử nghiệm end-to-end bao gồm mạng, persistence, serialization và hệ thống phụ thuộc. Luôn giữ cùng một cấu hình để so sánh công bằng.

## 5. Chọn theo vận hành và vòng đời

### 5.1. JDK, build và tính tương thích

- **Chọn JDK được bảo trì và cập nhật bản vá** theo nhà cung cấp, hệ điều hành và chính sách tổ chức. “LTS” không đồng nghĩa mọi bản binary được hỗ trợ vô thời hạn; kiểm tra lịch cung cấp bản vá của đúng distribution.
- **Khóa phiên bản build bằng Maven Wrapper hoặc Gradle Wrapper** và xác định JDK dùng cho build/test/runtime. Cập nhật phụ thuộc và kiểm thử định kỳ; cân nhắc kiểm tra vulnerability, license và SBOM theo yêu cầu hệ thống.
- **Dự án bắt buộc chạy trên Java 11**: biên dịch với `javac --release 11` hoặc cấu hình tương đương của Maven/Gradle, chạy CI trên runtime Java 11 thật. Chỉ đặt `source`/`target` mà dùng API của JDK mới hơn có thể tạo lỗi lúc chạy.
- **Phân biệt JDK chạy công cụ build với JDK của sản phẩm**: các bản Gradle hiện đại có thể cần JDK mới hơn để chạy Gradle, nhưng vẫn có thể dùng toolchain Java 11 để biên dịch/kiểm thử dự án mục tiêu Java 11. Kiểm tra compatibility matrix của bản Gradle đang sử dụng.
- **Kiểm tra yêu cầu của framework**: một thư viện/framework có thể yêu cầu Java 17 hoặc cao hơn; không ép nó chạy trên Java 11 vì bản JDK 11 được ghi là LTS.

Ví dụ biên dịch trực tiếp để chắc rằng mã dùng API và cú pháp trong giới hạn Java 11:

```bash
javac --release 11 ToolChoiceDemo.java
java ToolChoiceDemo
```

Đối với dự án Maven/Gradle, cấu hình mục tiêu và toolchain trong build chính thức thay vì phụ thuộc thiết lập JDK ngẫu nhiên trên máy lập trình viên.

### 5.2. Đóng gói: runtime đầy đủ hay `jlink`?

`jdeps` phân tích phụ thuộc module; `jlink` tạo custom runtime image từ các module JDK cần thiết. Đây là lựa chọn hữu ích khi cần image gọn, chủ động kiểm soát những module đi kèm.

```bash
jlink --add-modules java.base,java.net.http --output runtime11
```

Lệnh minh họa tạo runtime chứa hai module gốc và các phụ thuộc module cần thiết; **chưa bảo đảm** đủ module cho một ứng dụng cụ thể. Phải dùng `jdeps`, kiểm tra các phụ thuộc động, service provider, thư viện native và chạy kiểm thử toàn bộ trên image đã ghép. `jlink` không tự biến mọi dependency bên ngoài thành module có thể link; với ứng dụng có nhiều thư viện hoặc cần dễ nâng cấp, một runtime JDK tiêu chuẩn phù hợp vẫn có thể đơn giản hơn.

Bản runtime tùy biến cần được **xây lại khi JDK có bản vá bảo mật**. Không tách việc giảm dung lượng image khỏi quy trình cập nhật, chẩn đoán và rollback.

### 5.3. Vận hành dịch vụ

Một lựa chọn công cụ nên đi kèm: log có ngữ cảnh và không lộ dữ liệu nhạy cảm, metric độ trễ/lỗi/tải, trace cho luồng phân tán khi cần, readiness/liveness check phù hợp, cấu hình timeout và kết nối, giới hạn tài nguyên container, rollback và lịch cập nhật bản vá. Đảm bảo có thể tái hiện build và xử lý sự cố trong môi trường triển khai thật.

## 6. Ví dụ Java 11 chạy độc lập: lựa chọn đơn giản cho dữ liệu nhỏ

Chương trình sau **biên dịch trên Java 11**, đọc/ghi một tệp nhỏ bằng API chuẩn, đồng thời tạo một HTTP client có connect timeout mà **không gọi mạng**. Nó minh họa hai quyết định: dùng API JDK khi đủ chức năng và cấu hình hành vi vận hành ngay từ đầu.

Tạo tệp `ToolChoiceDemo.java`:

```java
import java.net.http.HttpClient;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;

public class ToolChoiceDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("tool-choice-", ".txt");
        try {
            Files.writeString(file, "alpha\nbeta\n", StandardCharsets.UTF_8);

            String content = Files.readString(file, StandardCharsets.UTF_8);
            long lines = content.lines().count();

            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            System.out.println("So dong: " + lines);
            System.out.println("Timeout ket noi: "
                    + client.connectTimeout().orElseThrow().getSeconds()
                    + " giay");
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 11 ToolChoiceDemo.java
java ToolChoiceDemo
```

Kết quả chuẩn (khi thao tác tạo/đọc/ghi tệp được phép):

```text
So dong: 2
Timeout ket noi: 3 giay
```

Giải thích:

1. `Files.writeString/readString` phù hợp vì dữ liệu chỉ có hai dòng; nếu kích thước tệp không kiểm soát được, đổi sang xử lý luồng.
2. `String.lines()` của Java 11 đếm đúng hai dòng; ký tự xuống dòng cuối không tạo thêm dòng dữ liệu.
3. `HttpClient` chỉ được khởi tạo, không gửi request, nên chương trình không phụ thuộc mạng hay endpoint bên ngoài.
4. `finally` giải phóng tệp tạm ngay cả khi xử lý gặp lỗi. Trong ứng dụng thật vẫn cần thiết kế xử lý lỗi, log và retry theo đặc tính nghiệp vụ.

## 7. Hai tình huống lựa chọn

### Tình huống A — Công cụ đồng bộ hóa dữ liệu định kỳ

**Yêu cầu:** mỗi đợt đọc một file cấu hình nhỏ và gọi vài API HTTPS; số đợt ít, thời gian chạy không gấp, cần dễ triển khai.

**Lựa chọn ban đầu:** `Files.readString` cho cấu hình nhỏ, `HttpClient.send` cho yêu cầu HTTP tuần tự, timeout cho kết nối/request, Maven hoặc Gradle có wrapper, log rõ status và thời gian chạy. **Chỉ chuyển sang bất đồng bộ** nếu đo thấy thời gian chờ nhiều lời gọi độc lập là nút thắt thực sự. Kiểm tra cấu hình secrets và việc retry không làm chạy lại giao dịch đã hoàn thành.

**Kiểm chứng:** kết quả dữ liệu đúng, trường hợp HTTP 4xx/5xx/timeout được xử lý, job hoàn tất trong khung thời gian, có thể vận hành lại và chẩn đoán lỗi.

### Tình huống B — API service có độ trễ cao và bộ nhớ bị giới hạn

**Yêu cầu:** lượng request đồng thời lớn, p95/p99 theo SLO, tài nguyên container có giới hạn, cần quan sát sự cố.

**Lựa chọn ban đầu:** HTTP client tái sử dụng, quản lý pool/giới hạn đồng thời theo mô hình của framework, đặt timeout và backpressure, baseline G1 GC, metrics/tracing và JFR khi điều tra. Nếu đa số thời gian chờ là I/O, thử `sendAsync`/`CompletableFuture` trong phạm vi có giới hạn; nếu vấn đề là CPU, tìm hotspot và allocation trước.

**Kiểm chứng:** thử tải đại diện ở nhiều mức concurrency; so sánh độ trễ đuôi, tỷ lệ lỗi, throughput, RSS, CPU, GC pause và khả năng phục hồi khi dịch vụ phụ thuộc chậm. Chỉ giữ thay đổi khi lợi ích đo được lớn hơn độ phức tạp mới phát sinh.

## 8. Các sai lầm thường gặp

| Sai lầm | Tác hại | Cách xử lý |
| --- | --- | --- |
| Chọn công cụ vì đang thịnh hành | Thêm dependency và rủi ro vận hành không cần thiết | Xuất phát từ yêu cầu và kiểm chứng bằng tình huống thật |
| Mặc định bất đồng bộ/song song luôn nhanh hơn | Tốn thread, tăng contention, khó kiểm soát lỗi | Đo tải I/O/CPU, đặt giới hạn concurrency |
| Dùng `Files.readString` với dữ liệu rất lớn | Có thể tăng heap đột biến hoặc hết bộ nhớ | Dùng reader/stream, xử lý theo từng phần |
| Dùng trung bình latency để khẳng định SLA | Che giấu request ở đuôi phân phối rất chậm | Theo dõi p95/p99 và tỷ lệ lỗi |
| Chỉnh GC trước khi xác định bottleneck | Tối ưu nhầm, khó so sánh | Đo JFR, GC logs, CPU, heap và request path |
| Build bằng JDK mới nhưng chỉ đặt target 11 | Có thể gọi API không tồn tại trên Java 11 | Dùng `--release 11`/toolchain và test runtime 11 |
| Xem custom runtime `jlink` là tự động an toàn | Thiếu module/provider hoặc không nhận bản vá | Test trên image thật và xây lại theo lịch cập nhật JDK |
| Tin rằng “Java 11 LTS” đủ chứng minh môi trường an toàn | Có thể dùng bản phân phối hết hỗ trợ hoặc thiếu vá lỗi | Kiểm tra lịch hỗ trợ của đúng vendor, cập nhật bản vá |

## 9. Checklist quyết định trước khi chốt công cụ

1. **Bắt buộc:** giải pháp chạy trên Java mục tiêu, đáp ứng giao thức, dữ liệu, bảo mật, tình huống lỗi và yêu cầu tích hợp chưa?
2. **Đơn giản:** JDK chuẩn đã giải quyết được chưa? Nếu thêm thư viện, năng lực nào biện minh cho dependency mới?
3. **Đo được:** đã có số liệu baseline và thử nghiệm lại trên tải đại diện, bao gồm p95/p99, lỗi, CPU, RSS và GC chưa?
4. **Vận hành được:** có logs/metrics/JFR, timeout, giới hạn tài nguyên, build tái lập, CI và kế hoạch rollback chưa?
5. **Bảo trì được:** JDK, thư viện, framework và runtime image có nguồn cập nhật bản vá đáng tin cậy không?
6. **Quyết định có chứng cứ:** ghi lại phương án được chọn, phương án đã cân nhắc, số liệu kiểm chứng và điều kiện cần đánh giá lại.

**Nguyên tắc áp dụng:** chọn công cụ **đủ chức năng → đạt hiệu năng đã đo → vận hành và cập nhật được**. Khi điều kiện tải, giới hạn tài nguyên hoặc phiên bản Java thay đổi, đánh giá lại thay vì giữ một lựa chọn cũ vì thói quen.

## Tài liệu tham khảo còn hữu ích

- Java 11 `HttpClient` API: https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html
- Java 11 `Files` API: https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/Files.html
- Java 11 `jcmd` và công cụ chẩn đoán: https://docs.oracle.com/en/java/javase/11/troubleshoot/diagnostic-tools.html
- Java 11 GC tuning và tính thử nghiệm của ZGC: https://docs.oracle.com/en/java/javase/11/gctuning/available-collectors1.html
- Java 11 `jlink`: https://docs.oracle.com/en/java/javase/11/tools/jlink.html
- Gradle Java compatibility matrix (tra cứu theo phiên bản đang dùng): https://docs.gradle.org/current/userguide/compatibility.html
- Eclipse Temurin support timeline (tra cứu theo distribution): https://adoptium.net/support/
- Oracle Java SE Support Roadmap: https://www.oracle.com/technetwork/java/javase/tech/eol-135779.html

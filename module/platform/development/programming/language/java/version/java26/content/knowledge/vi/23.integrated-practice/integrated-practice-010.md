# Bộ kiểm thử lỗi, tài nguyên, bảo mật và báo cáo nghiệm thu

Bài thực hành này xây dựng một bộ kiểm thử nghiệm thu cho dịch vụ Java 26 có các luồng gọi HTTP, xử lý kết quả bằng pattern matching, phối hợp công việc đồng thời, mã hóa payload và chạy trên JVM đã tối ưu. Mục tiêu là chứng minh dịch vụ đáp ứng hợp đồng chức năng, giải phóng tài nguyên khi thành công lẫn thất bại, bảo vệ dữ liệu và có bằng chứng đủ rõ để quyết định phát hành.

Bộ kiểm thử phải tách API ổn định khỏi preview và incubator. Các kiểm tra bắt buộc của production chỉ dựa trên API đã được phát hành chính thức. Structured Concurrency, primitive patterns, PEM preview và Vector API có thể có lane thử nghiệm riêng, nhưng không được làm điều kiện bắt buộc để chạy ứng dụng production khi nhóm chưa chấp nhận rủi ro phụ thuộc API chưa ổn định.

Một điểm cập nhật phiên bản cần ghi rõ: JDK 27 đã phát hành ngày 15-09-2026 và là release mới hơn JDK 26. JDK 26 vẫn là target của bài học này; khi nghiệm thu triển khai mới, phải ghi rõ đang kiểm tra JDK 26 hay JDK 27 và dùng đúng patch/build được tổ chức hỗ trợ. Các API preview/incubator liên quan vẫn tiếp tục ở trạng thái thử nghiệm trong JDK 27, nên không thể kết luận chúng đã ổn định chỉ vì đã xuất hiện qua nhiều preview/incubator release.

## 1. Kịch bản nghiệm thu

Giả sử nhóm phát triển một dịch vụ xử lý đơn hàng. Khi nhận yêu cầu tạo đơn, dịch vụ:

1. Kiểm tra dữ liệu và phân loại kết quả nghiệp vụ.
2. Gọi HTTP đến dịch vụ giá, kho và vận chuyển.
3. Phối hợp các tác vụ độc lập, áp dụng timeout và hủy công việc khi một nhánh thất bại.
4. Mã hóa payload nhạy cảm trước khi gửi hoặc lưu trữ.
5. Ghi nhận kết quả và trạng thái giao dịch.
6. Khởi chạy bằng JVM có thể sử dụng AOT cache và garbage collector được cấu hình cho môi trường đích.

Bộ kiểm thử cần trả lời bốn câu hỏi:

- **Đúng chức năng:** API trả đúng status, body, mã lỗi và trạng thái dữ liệu theo hợp đồng?
- **An toàn tài nguyên:** stream, HTTP client, statement, connection, executor và tác vụ con được giải phóng khi mọi nhánh kết thúc?
- **An toàn dữ liệu:** TLS, chữ ký JAR, HPKE, key lifecycle và log không làm lộ dữ liệu hoặc bí mật?
- **Sẵn sàng triển khai:** đúng JDK, đúng target, cache được nạp, hiệu năng đạt ngưỡng đã thống nhất và có thể rollback?

Không dùng một kết quả “ứng dụng chạy được” để thay thế cả bốn nhóm bằng chứng. Mỗi nhóm cần test case, log hoặc artifact kiểm chứng riêng.

## 2. Chốt phiên bản và trạng thái tính năng trước khi viết test

Các tính năng trong Java 26 không cùng một mức ổn định. Bảng sau là căn cứ để quyết định lane kiểm thử:

| Tính năng | Trạng thái trong JDK 26 | Cách đưa vào nghiệm thu |
|---|---|---|
| HTTP/3 cho HTTP Client API — JEP 517 | Tính năng chính thức | Có thể nằm trong production acceptance nếu server và mạng hỗ trợ |
| Pattern matching cho instanceof, switch và record patterns đã finalized ở các release trước | API/ngôn ngữ ổn định | Dùng trong code production và contract tests |
| Primitive Types in Patterns, instanceof, and switch — JEP 530 | Preview lần thứ tư | Chỉ chạy trong preview lane với --enable-preview |
| Structured Concurrency — JEP 525 | Preview lần thứ sáu | Chỉ chạy trong preview lane với --enable-preview |
| Vector API — JEP 529 | Incubator lần thứ mười một | Chỉ chạy trong incubator lane với --add-modules jdk.incubator.vector |
| PEM Encodings — JEP 524 | Preview lần thứ hai | Chỉ chạy trong preview lane với --enable-preview |
| HPKE trong JCA Cipher | API Java SE chính thức từ JDK 26 | Có thể dùng trong production khi provider và suite đã được xác minh |
| AOT Object Caching with Any GC — JEP 516 | Tính năng JVM chính thức | Kiểm tra cache trên đúng target; đo lợi ích bằng benchmark |
| G1 GC throughput — JEP 522 | Tối ưu JVM chính thức | Đánh giá bằng tải và số đo GC, không bằng unit test |
| Remove the Applet API — JEP 504 | API đã bị loại bỏ | Kiểm tra dependency không còn tham chiếu API đã bị xóa |

JDK 27 tiếp tục thay đổi số lần preview/incubator:

| Tính năng | JDK 27 | Ý nghĩa khi nghiệm thu |
|---|---|---|
| Structured Concurrency | JEP 533, preview lần thứ bảy | Vẫn cần preview flag; API tiếp tục thay đổi |
| Vector API | JEP 537, incubator lần thứ mười hai | Vẫn là incubator module |
| Primitive Types in Patterns | JEP 532, preview lần thứ năm | Vẫn không phải ngôn ngữ ổn định |
| PEM Encodings | JEP 538, preview lần thứ ba | Vẫn không nên là dependency production mặc định |

Tại ngày 28-11-2026, Oracle đã phát hành JDK 27.0.1.1 ngày 17-11-2026; bản build tương ứng của các vendor khác có thể mang số hiệu riêng. Với deployment mới, chọn patch mới nhất còn được vendor hỗ trợ và được tổ chức phê duyệt. JDK 26 là target của các ví dụ trong bài, không phải release mới nhất hiện nay.

Khi nâng lên JDK 27, kiểm tra thêm các thay đổi ổn định: JEP 523 đưa G1 thành garbage collector mặc định trong mọi môi trường; JEP 527 bổ sung post-quantum hybrid key exchange cho TLS 1.3; JEP 536 bật JFR in-process data redaction cho command-line arguments, environment variables và system properties theo mặc định. JDK 27 cũng bổ sung jcmd VM.security_properties để xem security properties đang có hiệu lực và báo số file descriptor đang mở trong VM.info trên nền tảng hỗ trợ.

JDK 27 thêm AOTMode=required như alias của AOTMode=on; tài liệu release note khuyến nghị dùng required thay cho on vì on dự kiến được deprecated và loại bỏ trong tương lai. Các ví dụ JDK 26 trong bài vẫn dùng on; khi target JDK 27, cập nhật lệnh và ghi đúng mode trong report. Đồng thời rà soát startup script để loại các launcher option đã bị xóa như -noverify, -Xverify:none, -noclassgc và -verifyremote. Không giữ option cũ chỉ vì JVM trước đó bỏ qua hoặc chấp nhận nó.

Với preview feature của JDK 26, cả biên dịch và chạy đều phải bật preview bằng đúng JDK 26. Incubator module cần được thêm vào module graph bằng --add-modules; không đồng nhất yêu cầu này với preview flag. Một artifact được biên dịch bằng preview của JDK 26 không được xem là artifact Java ổn định có thể chạy tùy ý trên JDK khác.

## 3. Xây dựng test plan theo hợp đồng

Trước khi chạy test, ghi rõ yêu cầu, điều kiện, kết quả mong đợi và bằng chứng. Mỗi test case cần có ID ổn định để báo cáo nghiệm thu có thể truy ngược về log, test report và build.

| Nhóm | Nội dung cần kiểm tra | Bằng chứng |
|---|---|---|
| HTTP contract | Method, path, status, headers, schema, timeout, retry | Test report và response capture đã loại dữ liệu nhạy cảm |
| Pattern matching | Mỗi loại kết quả, nhánh lỗi, null và kiểu không được hỗ trợ | Unit/contract test |
| Đồng thời | Kết quả, timeout, cancellation, lỗi tác vụ con, không rò rỉ task | Test report, thread/task metrics |
| Resource lifecycle | Đóng stream, response body, connection, statement, executor | Test với close tracking và integration test |
| Bảo mật | TLS, HPKE, JAR signature, key access, secret handling | Verification output, security scan, audit evidence |
| AOT/JVM | Cache compatibility, GC behavior, startup và warm-up | JVM log, benchmark report, target metadata |
| Migration | API đã bị loại bỏ, preview flags, JDK build và dependency | Compile report, dependency report, runtime inventory |

Định nghĩa severity trước khi chạy:

- **Blocker:** có thể làm lộ dữ liệu/secret, làm sai dữ liệu nghiệp vụ, bỏ qua kiểm tra chữ ký hoặc khiến dịch vụ không khởi động trên target được hỗ trợ.
- **Major:** lỗi timeout/cancellation, resource leak, sai HTTP contract hoặc hiệu năng vượt ngưỡng vận hành.
- **Minor:** sai lệch log/metrics hoặc thông báo không ảnh hưởng dữ liệu và hợp đồng chính.
- **Observation:** khác biệt có thể chấp nhận, đã có owner và kế hoạch theo dõi.

Không hạ severity chỉ để đạt trạng thái PASS. Một lỗi bảo mật hoặc dữ liệu sai không được chuyển thành observation nếu chưa có biện pháp xử lý và người chịu trách nhiệm.

## 4. Kiểm thử HTTP Client và HTTP/3

JEP 517 bổ sung HTTP/3 cho Java HTTP Client API. Test cần xác nhận cả response contract lẫn protocol thực sự được thương lượng. Việc gọi API với preference HTTP/3 không tự chứng minh kết nối đã dùng HTTP/3; hãy kiểm tra giá trị HttpResponse.version().

Ví dụ kiểm tra endpoint HTTP/3 trong môi trường nghiệm thu có server hỗ trợ QUIC:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.junit.jupiter.api.Test;

class Http3AcceptanceTest {
    @Test
    void orderEndpointUsesHttp3AndReturnsAccepted() throws Exception {
        try (HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_3)
                .connectTimeout(Duration.ofSeconds(3))
                .build()) {

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create("https://orders.test.example/api/orders"))
                    .timeout(Duration.ofSeconds(5))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(
                            """
                            {"customerId":"c-42","sku":"SKU-7","quantity":2}
                            """))
                    .build();

            HttpResponse<String> response =
                    client.send(request, HttpResponse.BodyHandlers.ofString());

            assertEquals(202, response.statusCode());
            assertEquals(HttpClient.Version.HTTP_3, response.version());
        }
    }
}
~~~

Domain và payload trong ví dụ là dữ liệu giả lập. Test thực tế phải dùng endpoint test/staging và dữ liệu tổng hợp.

Tách hai chính sách:

- Nếu hợp đồng yêu cầu HTTP/3, test phải xác nhận response.version() là HTTP_3. Môi trường test phải cho phép QUIC/UDP, TLS và đường mạng tương ứng.
- Nếu HTTP/3 chỉ là preference, test fallback theo danh sách protocol được tổ chức cho phép. Không ép test pass bằng cách chấp nhận mọi protocol nếu production policy yêu cầu HTTP/2 trở lên.

Các trường hợp cần có:

| ID gợi ý | Điều kiện | Kết quả cần xác minh |
|---|---|---|
| HTTP-001 | HTTP/3 server khỏe | Status, schema và version HTTP_3 đúng |
| HTTP-002 | Server không hỗ trợ HTTP/3 | Fallback đúng policy; không giả định đã dùng HTTP/3 |
| HTTP-003 | Certificate không tin cậy | TLS handshake thất bại; không tắt kiểm tra certificate để test pass |
| HTTP-004 | Response chậm vượt request timeout | Client kết thúc theo timeout contract |
| HTTP-005 | Server trả 4xx/5xx | Mã lỗi và Problem Details đúng hợp đồng |
| HTTP-006 | Body lớn hoặc stream dài | Đọc đủ dữ liệu, đóng body và không giữ connection ngoài scope |
| HTTP-007 | Kết nối bị reset giữa chừng | Lỗi được ánh xạ đúng; retry chỉ thực hiện theo policy |
| HTTP-008 | Retry cùng idempotency key | Không tạo đơn hoặc thanh toán trùng nếu API cam kết idempotency |

Không dùng một timeout ngắn cố định để đo hiệu năng trong unit test. Dùng server thử nghiệm có khả năng điều khiển delay, reset và response body; thời gian chờ phải đủ ổn định để tránh test chập chờn. Kiểm tra timeout và retry bằng trạng thái cuối, số lần gọi và idempotency record.

## 5. Kiểm thử pattern matching và hợp đồng lỗi

Các dạng pattern matching cho kiểu tham chiếu, switch type patterns và record patterns đã ổn định từ các release trước Java 26. Chúng phù hợp để phân loại kết quả API rõ ràng mà không phải ép kiểu thủ công.

Ví dụ mô hình kết quả:

~~~java
import java.time.Duration;
import java.util.UUID;

sealed interface OrderResult
        permits Accepted, Rejected, RetryLater { }

record Accepted(UUID orderId) implements OrderResult { }

record Rejected(String code, int httpStatus)
        implements OrderResult { }

record RetryLater(Duration retryAfter) implements OrderResult { }

final class OrderResultMapper {
    static String metricName(OrderResult result) {
        return switch (result) {
            case Accepted accepted ->
                    "order.accepted";
            case Rejected rejected ->
                    "order.rejected." + rejected.code();
            case RetryLater retry ->
                    "order.retry";
        };
    }
}
~~~

Contract tests phải kiểm tra mọi loại kết quả được phép:

- Accepted chứa order ID hợp lệ và trạng thái thành công.
- Rejected chứa error code ổn định và status theo API contract.
- RetryLater có retryAfter trong phạm vi hợp lệ.
- Null được xử lý đúng chính sách; switch trên null có thể ném NullPointerException nếu không có nhánh null.
- Nếu sealed hierarchy thay đổi, test/compile phải phát hiện nhánh mới chưa được xử lý.

Không dùng primitive patterns trong production baseline của JDK 26 nếu chưa chấp nhận preview dependency. JEP 530 trong JDK 26 là preview lần thứ tư; nếu muốn đánh giá, tạo lane riêng và biên dịch/chạy bằng --enable-preview. Khi lên JDK 27, kiểm tra lại JEP 532 và Javadoc tương ứng; không tái sử dụng kết luận preview của JDK 26 cho release khác.

Các trường hợp lỗi cần bao phủ:

| Đầu vào | Kết quả mong đợi |
|---|---|
| Thiếu customer ID | Lỗi validation với code công khai |
| Quantity bằng 0 hoặc âm | Từ chối trước khi ghi dữ liệu |
| SKU không tồn tại | Not found theo hợp đồng |
| Kho không đủ hàng | Conflict hoặc mã nghiệp vụ đã công bố |
| Giá dịch vụ upstream timeout | Retryable error hoặc gateway timeout theo policy |
| Response JSON sai schema | Lỗi upstream; không ánh xạ thành đơn hàng hợp lệ |
| Result type mới chưa được mapper xử lý | Compile/test phát hiện thay đổi contract |

Không assert toàn bộ exception message nếu message không phải API contract. Ưu tiên exception type, error code, HTTP status và trạng thái dữ liệu sau lỗi.

## 6. Kiểm thử concurrency, timeout và cancellation

Trong production baseline, dùng API đồng thời đã ổn định như ExecutorService, virtual threads, CompletableFuture hoặc các cơ chế đã được công bố. Một nhóm tác vụ cần có timeout, giới hạn tài nguyên và chính sách hủy rõ ràng.

Nếu dùng Structured Concurrency của JDK 26 (JEP 525), đây là preview lần thứ sáu. Acceptance test của lane preview cần tập trung vào:

- Một tác vụ con thất bại thì scope có báo lỗi theo policy không?
- Timeout hoặc cancellation có yêu cầu các tác vụ còn lại dừng không?
- Sau khi scope đóng, có tác vụ con nào tiếp tục chạy ngoài lifetime dự kiến không?
- Exception của tác vụ con có được giữ nguyên nguyên nhân để chẩn đoán không?
- Tài nguyên của các tác vụ con có được giải phóng khi parent thất bại hoặc bị interrupt không?

Không copy ví dụ StructuredTaskScope từ JDK cũ mà không đọc JDK 26 Javadoc; API đã thay đổi qua nhiều preview. Compile và run lane này bằng cùng JDK 26 với --enable-preview. Nếu kiểm tra trên JDK 27, phải dùng API và preview flag của JDK 27, đồng thời ghi nhận đó là JEP 533 seventh preview.

Bộ kiểm thử đồng thời:

| ID gợi ý | Tình huống | Kết quả |
|---|---|---|
| CON-001 | Ba upstream cùng phản hồi thành công | Kết quả tổng hợp đúng và không mất dữ liệu |
| CON-002 | Một upstream thất bại sớm | Hủy hoặc tiếp tục các nhánh còn lại đúng policy |
| CON-003 | Một upstream timeout | Request kết thúc trong giới hạn đã cam kết |
| CON-004 | Caller bị hủy | Tác vụ con dừng và tài nguyên được giải phóng |
| CON-005 | Nhiều request cùng lúc | Không vượt connection/thread/task limit |
| CON-006 | Retry đồng thời cùng idempotency key | Chỉ có một side effect nghiệp vụ |
| CON-007 | Một tác vụ con ném exception | Exception được truyền và báo cáo đúng nguyên nhân |

Không dùng Thread.sleep để hy vọng các thread chạy theo thứ tự. Dùng latch, barrier, Future hoặc test server điều khiển được thời điểm phản hồi. Kiểm tra số tác vụ còn sống sau khi test kết thúc và thu thập mọi exception từ task.

## 7. Kiểm thử vòng đời tài nguyên

Một request có thể tạo nhiều tài nguyên: HttpClient, response body stream, file stream, JDBC Connection, Statement, ResultSet, executor và task con. Mỗi tài nguyên phải có owner và scope đóng rõ ràng.

### 7.1. HTTP response body

Khi dùng BodyHandlers.ofInputStream(), caller chịu trách nhiệm đóng stream. Không giữ response body sau khi request scope kết thúc.

~~~java
try (HttpClient client = HttpClient.newBuilder().build()) {
    HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://files.test.example/export"))
            .GET()
            .build();

    HttpResponse<java.io.InputStream> response =
            client.send(request, HttpResponse.BodyHandlers.ofInputStream());

    try (java.io.InputStream body = response.body()) {
        byte[] payload = body.readAllBytes();
        // Xử lý payload trong phạm vi stream còn mở.
    }
}
~~~

Nếu body được chuyển sang một consumer khác, phải chuyển giao quyền sở hữu stream rõ ràng và xác định consumer nào đóng nó. Không vừa đóng ở caller vừa giả định consumer còn có thể đọc tiếp.

### 7.2. JDBC

Khi dùng JDBC, đóng theo thứ tự ngược: ResultSet, Statement, Connection. Dùng try-with-resources để việc đóng vẫn diễn ra khi câu SQL hoặc phần ánh xạ dữ liệu ném exception.

~~~java
try (var connection = dataSource.getConnection();
     var statement = connection.prepareStatement(
             "SELECT id, status FROM orders WHERE id = ?")) {

    statement.setObject(1, orderId);

    try (var resultSet = statement.executeQuery()) {
        if (!resultSet.next()) {
            throw new OrderNotFoundException(orderId);
        }

        return new OrderView(
                resultSet.getObject("id", UUID.class),
                resultSet.getString("status"));
    }
}
~~~

Nếu transaction do framework quản lý, tuân theo owner và transaction manager; không tự ý đóng connection được framework giữ trong transaction hiện tại.

### 7.3. Executor và tác vụ con

ExecutorService hiện hành hỗ trợ AutoCloseable, nên có thể quản lý bằng try-with-resources trong scope phù hợp. Đảm bảo các task kết thúc hoặc bị hủy trước khi scope đóng. Không giữ executor dùng chung trong một request rồi đóng nó sau mỗi lần gọi; lifecycle phải phù hợp với owner của executor.

Kiểm tra bằng:

- Test stream/statement wrapper ghi nhận close được gọi.
- Test exception giữa chừng để xác nhận mọi tài nguyên đã mở đều được đóng.
- Integration test kiểm tra connection pool không tăng số connection đang mượn sau khi request kết thúc.
- Kiểm tra task/thread còn sống sau cancellation.
- Quan sát file descriptor, connection pool metrics và heap/thread metrics trong stress test.

Trên JDK 27, có thể dùng jcmd VM.info để xem số file descriptor đang mở trên nền tảng hỗ trợ. So sánh số liệu trước/sau một chuỗi request lặp lại để phát hiện xu hướng tăng không hồi phục; không dùng một snapshot đơn lẻ làm bằng chứng leak.

Không dùng số file descriptor hoặc thời gian GC của một lần chạy làm assertion cứng trong unit test. Dùng ngưỡng và xu hướng trong performance/stress test có môi trường kiểm soát.

## 8. Kiểm thử HPKE và dữ liệu nhạy cảm

JDK 26 cung cấp Cipher algorithm HPKE theo RFC 9180 cùng HPKEParameterSpec. Đây là API Java SE chính thức từ JDK 26, không cần --enable-preview. HPKE kết hợp KEM, KDF và AEAD; test cần xác nhận sender/recipient dùng cùng suite, info và AAD.

Các ca bảo mật bắt buộc:

| ID gợi ý | Kiểm tra | Kết quả |
|---|---|---|
| SEC-001 | Sender mã hóa bằng recipient public key, recipient giải mã bằng private key | Plaintext khôi phục đúng |
| SEC-002 | Sửa một byte ciphertext | Giải mã thất bại |
| SEC-003 | Dùng AAD khác nhau | Xác thực thất bại |
| SEC-004 | Dùng recipient private key khác | Giải mã thất bại |
| SEC-005 | Dùng sai KEM/KDF/AEAD | Khởi tạo bị từ chối hoặc lỗi theo provider contract |
| SEC-006 | Thay encapsulation | Giải mã thất bại |
| SEC-007 | Base mode nhận payload | Không được xem đó là bằng chứng xác thực sender |
| SEC-008 | Gửi lại envelope cũ | Ứng dụng áp dụng replay policy riêng |
| SEC-009 | Target JDK 27 yêu cầu PQ hybrid TLS 1.3 | Handshake thương lượng nhóm key exchange nằm trong policy |

Base mode không xác thực danh tính sender. Nếu nghiệp vụ cần xác minh sender, dùng HPKE auth mode, PSK mode hoặc chữ ký/xác thực ở tầng giao thức theo thiết kế đã được review. HPKE cũng không tự giải quyết replay qua nhiều session; API phải kiểm tra message ID, counter hoặc trạng thái nghiệp vụ.

Ví dụ kiểm tra dữ liệu bị sửa nên xác nhận thao tác giải mã ném lỗi xác thực:

~~~java
byte[] damaged = ciphertext.clone();
damaged[0] ^= 1;

assertThrows(
        java.security.GeneralSecurityException.class,
        () -> decryptWithHpke(recipientPrivateKey, encapsulation,
                              info, aad, damaged));
~~~

Helper decryptWithHpke trong ví dụ đại diện cho adapter dùng HPKEParameterSpec và Cipher của JDK 26. Trong test thật, plaintext chỉ được sử dụng sau khi doFinal() hoàn tất thành công; không log ciphertext nhạy cảm cùng key material hoặc plaintext.

## 9. Kiểm thử chữ ký JAR và quản lý secret

Artifact phát hành phải được ký và xác minh bằng chính sách thuật toán hiện hành. Dùng keytool/jarsigner với password prompt hoặc nguồn secret được bảo vệ; không đặt password literal trong command line, shell history, CI log hoặc repository.

Các bước nghiệm thu:

1. Kiểm tra keystore có alias và private key entry đúng.
2. Xác minh certificate chain, fingerprint, thời hạn và mục đích code signing.
3. Ký artifact trong job có quyền truy cập khóa.
4. Dùng timestamp service được tin cậy nếu quy trình phát hành yêu cầu.
5. Chạy xác minh strict.
6. Chỉ publish artifact sau khi chữ ký và danh tính signer đạt policy.

Lệnh xác minh:

~~~sh
jarsigner -verify -strict -verbose -certs app-signed.jar
~~~

Không truyền store password hoặc key password khi chỉ xác minh chữ ký. Kết quả chữ ký hợp lệ về mặt mật mã không tự chứng minh certificate thuộc tổ chức mong đợi; phải đối chiếu fingerprint và trust chain.

Kiểm tra thêm:

- Không có secret trong log, crash dump hoặc report.
- Private key không được đóng gói trong JAR hoặc container runtime.
- Quyền đọc keystore và quyền sử dụng HSM chỉ cấp cho job phát hành.
- Thuật toán bị disabled không được bật lại chỉ để chấp nhận chữ ký cũ.
- Nếu dùng PEM Encodings API của JDK 26 (JEP 524), nhớ đó là preview lần thứ hai; dùng lane riêng và không đặt làm dependency bắt buộc cho production baseline.

JDK 27 bổ sung post-quantum hybrid key exchange cho TLS 1.3 qua JEP 527. Nếu target triển khai là JDK 27 và policy yêu cầu hybrid key exchange, kiểm tra handshake thực tế và nhóm key_share được thương lượng. Đây là cơ chế bảo vệ kênh TLS; không nhầm với HPKE mã hóa payload theo RFC 9180.

## 10. Kiểm thử AOT cache và hiệu năng JVM

AOT object caching với mọi GC (JEP 516) là tối ưu chính thức của JDK 26. Bộ nghiệm thu phải chứng minh cache thuộc đúng application artifact, JDK release, OS và CPU architecture. Cache sai target có thể bị bỏ qua trong AOTMode=auto; vì vậy phải có kiểm tra fail-fast trong staging.

Các bước:

- Tạo cache từ đúng build và classpath sẽ deploy.
- Training bằng workload startup và nghiệp vụ đại diện.
- Tạo cache riêng cho từng target OS/CPU/JDK.
- Kiểm tra cache bằng AOTMode=on.
- Dùng AOTMode=auto trong production nếu cần fallback khi cache không tương thích.
- Ghi log AOT để xác nhận cache thực sự được nạp.
- Deploy và rollback application cùng cache theo một cặp build bất biến.

Với JDK 27, dùng AOTMode=required thay cho AOTMode=on để yêu cầu cache phải được nạp và tránh dựa vào option sẽ được thay thế. JDK 26 vẫn dùng AOTMode=on theo tài liệu của release đó.

JEP 522 cải thiện throughput của G1 bằng cách giảm synchronization. Nếu production dùng G1, đo throughput, pause time, allocation rate và CPU utilization trước/sau trên cùng workload. Không kết luận cải thiện từ một lần chạy hoặc một unit test.

Nếu target là JDK 27, G1 trở thành default collector trong mọi môi trường theo JEP 523. Hãy ghi rõ collector thực tế trong acceptance report thay vì dựa vào default của một release trước đó; cấu hình tường minh trong JVM options vẫn cần được kiểm tra theo target.

Vector API của JDK 26 vẫn là incubator lần thứ mười một. Nếu thử nghiệm, phải so sánh kết quả vector với scalar reference trên dữ liệu rỗng, một phần tử, độ dài không chia hết vector lane, giá trị biên và overflow. Đo hiệu năng riêng trên CPU mục tiêu; không giả định mọi CPU đều có cùng vector width hoặc cùng lợi ích.

Một số quy tắc benchmark:

- Chạy warm-up và nhiều iteration, ghi lại JDK build, CPU, OS, GC và heap.
- Tách cold start, warm start và steady-state throughput.
- Dùng dữ liệu giống nhau giữa scalar và vector implementation.
- Kiểm tra kết quả bằng checksum hoặc equality để tránh benchmark code bị tối ưu bỏ.
- Không đặt một ngưỡng millisecond cứng trong unit test.
- Chỉ đưa tối ưu vào production khi lợi ích đo được lớn hơn chi phí phức tạp và rủi ro tương thích.

## 11. Lane stable, preview và incubator trong CI

Một pipeline nghiệm thu nên có ít nhất ba lane độc lập:

| Lane | Thành phần | Điều kiện chạy | Gate phát hành |
|---|---|---|---|
| Stable production | HTTP Client HTTP/3, pattern matching đã finalized, HPKE, keytool/jarsigner, AOT/G1 | JDK build được hỗ trợ; không bật preview | Bắt buộc PASS |
| Preview evaluation | Structured Concurrency, primitive patterns, PEM preview | JDK 26 với --enable-preview khi đánh giá JDK 26; JDK khác phải dùng đúng release và API của release đó | Không làm gate production mặc định |
| Incubator evaluation | Vector API | --add-modules jdk.incubator.vector và đúng JDK incubator version | Không làm gate production mặc định |

Ví dụ lệnh compile/run cho preview lane trên JDK 26:

~~~sh
javac --release 26 --enable-preview -d out-preview src-preview/*.java
java --enable-preview -cp out-preview com.example.PreviewAcceptance
~~~

Ví dụ cho Vector API incubator:

~~~sh
javac --release 26 --add-modules jdk.incubator.vector \
  -d out-vector src-vector/*.java

java --add-modules jdk.incubator.vector \
  -cp out-vector com.example.VectorAcceptance
~~~

Nếu một module dùng cả preview feature và Vector API, compile/run phải mang cả hai tùy chọn phù hợp. Không thêm --enable-preview cho incubator API nếu không có preview feature nào khác cần nó.

Lane preview/incubator phải ghi:

- JDK vendor, full version string và feature release.
- JEP/API version đang thử nghiệm.
- Cờ compiler và runtime.
- Test case đã chạy.
- Lý do cần thử nghiệm và người chịu trách nhiệm.
- Kế hoạch bỏ, cập nhật hoặc thay thế khi API thay đổi.

Không phát hành dependency preview/incubator chỉ vì lane thử nghiệm PASS. Quyết định production cần phê duyệt kiến trúc, đánh giá khả năng migration và kế hoạch fallback.

## 12. Ma trận kiểm thử tổng hợp

Bảng dưới đây có thể dùng làm bộ test ID ban đầu. Nhóm phát triển cần điều chỉnh expected result theo hợp đồng thực tế của dịch vụ.

| ID | Nhóm | Kịch bản | Điều kiện PASS |
|---|---|---|---|
| INT-001 | HTTP | HTTP/3 endpoint thành công | Status/body đúng và protocol đúng policy |
| INT-002 | HTTP | Timeout upstream | Request kết thúc đúng deadline, không tạo đơn dở dang |
| INT-003 | HTTP | Upstream 5xx | Error mapping đúng, retry có giới hạn |
| INT-004 | Pattern | Mỗi subtype của OrderResult | Mapper trả đúng kết quả |
| INT-005 | Pattern | Null hoặc subtype không hợp lệ | Lỗi theo null/error contract |
| INT-006 | Concurrency | Một task con thất bại | Cancellation và lỗi theo policy |
| INT-007 | Concurrency | Caller bị hủy | Không còn task ngoài scope |
| INT-008 | Resource | HTTP body stream đọc xong | Stream đóng đúng một owner |
| INT-009 | Resource | JDBC query lỗi giữa chừng | ResultSet, Statement, Connection được đóng |
| INT-010 | Resource | Pool stress | Không tăng connection mượn tồn đọng |
| INT-011 | Security | HPKE round-trip | Plaintext khôi phục chính xác |
| INT-012 | Security | Sửa ciphertext/AAD | Giải mã thất bại |
| INT-013 | Security | Replay envelope | Replay policy từ chối hoặc trả kết quả idempotent đúng hợp đồng |
| INT-014 | Security | JAR signature | Strict verification và signer identity đạt policy |
| INT-015 | Security | Secret scan | Không tìm thấy password/private key/token trong log/artifact |
| INT-016 | JVM | AOT cache đúng target | AOTMode=on nạp thành công |
| INT-017 | JVM | Cache sai target | Fail-fast trong staging hoặc fallback có log theo policy |
| INT-018 | JVM | G1 workload | Throughput/pause đạt ngưỡng đã thống nhất |
| INT-019 | Vector | Vector và scalar đối chiếu | Kết quả giống nhau trên dữ liệu test |
| INT-020 | Compatibility | Compile production lane | Không dùng preview/incubator ngoài allowlist |
| INT-021 | Compatibility | Dependency scan | Không phụ thuộc API đã bị loại bỏ như Applet API |
| INT-022 | Compatibility | JDK matrix | Test pass trên mọi JDK target đã công bố |
| INT-023 | Security/JDK 27 | TLS 1.3 post-quantum hybrid key exchange | Nhóm key_share thực tế đáp ứng policy |

## 13. Tiêu chí nghiệm thu

Một build chỉ được đánh dấu ACCEPTED khi đáp ứng tất cả điều kiện bắt buộc đã thống nhất:

- Tất cả test Blocker và Major trong stable production lane đều PASS.
- Không có lỗi dữ liệu, lỗi giao dịch dở dang hoặc resource leak chưa xử lý.
- Không có secret hoặc plaintext nhạy cảm trong log/artifact.
- HTTP/TLS và chữ ký JAR đáp ứng trust policy.
- HPKE test xác nhận ciphertext/AAD tamper bị từ chối và sender authentication được xử lý đúng yêu cầu.
- AOT cache được kiểm tra trên đúng target và có log chứng minh trạng thái nạp.
- Hiệu năng đạt ngưỡng đã định trước trên workload đại diện.
- Preview/incubator được ghi nhận riêng, không bị hiểu nhầm là dependency ổn định.
- Có bằng chứng rollback về application artifact và cache tương ứng.
- Có owner và thời hạn cho mọi observation được chấp nhận.

Nếu có Blocker, trạng thái là REJECTED. Nếu chỉ còn Major đã được phê duyệt ngoại lệ, trạng thái phải là CONDITIONAL ACCEPTANCE với owner, deadline, phạm vi ảnh hưởng và kế hoạch rollback. Không dùng PASS cho test chưa chạy; ghi NOT RUN và lý do.

## 14. Mẫu báo cáo nghiệm thu

Dùng mẫu sau để lưu cùng build artifact hoặc hồ sơ phát hành. Không đưa password, private key, access token, dữ liệu cá nhân hoặc plaintext nhạy cảm vào báo cáo.

~~~text
ACCEPTANCE REPORT
Project:
Service:
Build ID / Commit:
Test date:
Environment:
JDK vendor:
JDK full version:
OS / CPU architecture:
Container image digest:
Application checksum:
Classpath checksum:
GC:
AOT cache ID / checksum:

RESULT: ACCEPTED | CONDITIONAL ACCEPTANCE | REJECTED

SUMMARY
- Total test cases:
- PASS:
- FAIL:
- NOT RUN:
- Blockers:
- Major issues:
- Observations:

FUNCTIONAL
- HTTP/3 policy:
- HTTP status/schema:
- Pattern matching contract:
- Error mapping:
- Idempotency:

RESOURCE
- HTTP body/stream cleanup:
- JDBC cleanup:
- Executor/task cleanup:
- Connection pool:
- Leak/stress evidence:

SECURITY
- TLS/certificate validation:
- TLS key exchange group, nếu policy yêu cầu:
- HPKE suite and tamper tests:
- Sender authentication policy:
- Replay policy:
- JAR signature and signer identity:
- Secret scan:
- JFR command-line/environment/property redaction, nếu dùng JDK 27:
- Security warnings:

JVM / PERFORMANCE
- AOT cache compatibility:
- AOT cache load evidence:
- GC:
- Cold start:
- Warm start:
- Throughput / p95 / p99:
- Vector comparison, if applicable:

PREVIEW / INCUBATOR
- JEP/API:
- JDK release:
- Compiler/runtime flags:
- Result:
- Production dependency: YES | NO

DEFECTS / EXCEPTIONS
- ID:
- Severity:
- Impact:
- Owner:
- Due date:
- Mitigation:
- Rollback plan:

EVIDENCE
- Test report path:
- Sanitized logs:
- Signature verification output:
- AOT/JFR/GC evidence:
- Benchmark report:

APPROVED BY:
DATE:
~~~

Lưu report dưới dạng artifact của pipeline với build ID, không sửa đè báo cáo của build trước. Nếu cần đính kèm log, loại bỏ header Authorization, cookie, key material, password, token và payload nhạy cảm trước khi lưu.

## 15. Những lỗi thường gặp khi nghiệm thu

| Lỗi | Vì sao sai | Cách khắc phục |
|---|---|---|
| Chỉ kiểm tra status 200 | Không xác minh schema, protocol hoặc side effect | Kiểm tra body, headers, version và trạng thái dữ liệu |
| Gửi HTTP/3 preference rồi kết luận đã dùng HTTP/3 | Có thể fallback sang protocol khác | Kiểm tra HttpResponse.version() |
| Dùng preview API trong stable build | Tăng rủi ro tương thích và vận hành | Tách preview lane và bật đúng flag |
| Dùng Vector API nhưng không có scalar baseline | Không chứng minh kết quả đúng | So sánh vector/scalar trên nhiều biên dữ liệu |
| Chỉ test concurrency khi mọi task thành công | Bỏ sót cancellation, timeout và task leak | Tiêm lỗi ở từng nhánh và kiểm tra scope cleanup |
| Đóng HTTP client nhưng quên body stream | Response body vẫn giữ tài nguyên | Đóng stream bằng try-with-resources |
| Mock JDBC rồi kết luận transaction rollback đúng | Mock không xác minh database transaction | Có integration test với database thật |
| HPKE base mode bị xem là xác thực sender | Base mode không xác minh danh tính người gửi | Dùng auth/PSK mode hoặc chữ ký theo threat model |
| Chỉ test HPKE round-trip | Không phát hiện tamper, sai AAD hoặc replay | Thêm negative và replay tests |
| JAR verified nhưng không kiểm tra signer | Chữ ký hợp lệ không đồng nghĩa signer đáng tin | Đối chiếu fingerprint, chain và trust policy |
| AOTMode=auto chạy thành công được xem là cache đã dùng | JVM có thể fallback khi cache không nạp | Kiểm tra staging bằng AOTMode=on và xem log |
| Đặt threshold performance trong unit test | Dễ flaky theo tải và máy | Dùng benchmark/performance environment |
| Báo cáo ghi PASS cho test chưa chạy | Mất độ tin cậy của nghiệm thu | Ghi NOT RUN và lý do |
| Ghi secret vào report hoặc log | Tạo thêm bản sao của bí mật | Sanitization trước khi lưu bằng chứng |
| Gắn test JDK 26 với JDK 27 mà không đổi flags | Preview/incubator API và JEP đã đổi | Tạo ma trận riêng cho từng JDK release |

## 16. Checklist cuối trước khi ký nghiệm thu

- [ ] Ghi chính xác JDK vendor, full version string, OS và CPU architecture.
- [ ] Xác định production lane chỉ dùng API ổn định.
- [ ] Ghi riêng preview và incubator JEP cùng compiler/runtime flags.
- [ ] HTTP contract kiểm tra status, schema, timeout, protocol và retry.
- [ ] Pattern matching xử lý mọi subtype và null theo hợp đồng.
- [ ] Concurrency test có failure, cancellation, timeout và kiểm tra task leak.
- [ ] HTTP body, stream, JDBC resource và executor được đóng đúng owner.
- [ ] Transaction không để lại dữ liệu dở dang khi lỗi.
- [ ] HPKE có round-trip, tamper, wrong key, AAD và sender-auth tests.
- [ ] TLS certificate và JAR signer được xác minh theo trust policy.
- [ ] Không có password, token, private key hoặc plaintext nhạy cảm trong log/report.
- [ ] AOT cache được ghép đúng application artifact và target.
- [ ] AOTMode=on PASS ở staging; production fallback được theo dõi.
- [ ] G1/AOT/Vector performance được đo bằng workload đại diện.
- [ ] Không phụ thuộc Applet API đã bị loại bỏ hoặc API lỗi thời.
- [ ] Tất cả Blocker/Major có quyết định rõ ràng.
- [ ] Báo cáo có evidence, owner, approval và rollback plan.
- [ ] Chỉ publish artifact sau khi kết quả nghiệm thu đạt policy.

## Tài liệu tham khảo

- [Oracle JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html): trạng thái các JEP trong JDK 26, gồm HTTP/3, Structured Concurrency, Vector API, primitive patterns, PEM, AOT và G1.
- [Significant Changes in JDK 26](https://docs.oracle.com/en/java/javase/26/migrate/significant-changes-jdk-26-release.html): thay đổi HTTP Client, HTTP/3 và các cải tiến runtime.
- [Java SE 26 Preview API List](https://docs.oracle.com/en/java/javase/26/docs/api/preview-list.html): xác định chính xác API preview trong JDK 26.
- [JEP 517 — HTTP/3 for the HTTP Client API](https://openjdk.org/jeps/517): hỗ trợ HTTP/3 trong Java HTTP Client.
- [JEP 525 — Structured Concurrency (Sixth Preview)](https://openjdk.org/jeps/525): trạng thái và mục tiêu API concurrency trong JDK 26.
- [JEP 529 — Vector API (Eleventh Incubator)](https://openjdk.org/jeps/529): trạng thái incubator và mô hình vector computation.
- [JEP 530 — Primitive Types in Patterns, instanceof, and switch (Fourth Preview)](https://openjdk.org/jeps/530): giới hạn preview của primitive patterns.
- [RFC 9180 — Hybrid Public Key Encryption](https://www.rfc-editor.org/rfc/rfc9180): mô hình KEM, KDF, AEAD và các mode HPKE.
- [Java SE 26 — HPKEParameterSpec](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/spec/HPKEParameterSpec.html): tham số và suite cho HPKE trong JDK 26.
- [Java SE 26 — Cipher](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/Cipher.html): API mã hóa, AAD và thao tác doFinal.
- [JEP 516 — Ahead-of-Time Object Caching with Any GC](https://openjdk.org/jeps/516): cache object AOT và khả năng dùng với các garbage collector.
- [JEP 522 — G1 GC: Improve Throughput by Reducing Synchronization](https://openjdk.org/jeps/522): thay đổi throughput của G1 trong JDK 26.
- [Oracle JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): trạng thái JDK 27 hiện hành, preview/incubator tiếp tục và các thay đổi cần kiểm tra khi nâng cấp.
- [Significant Changes in JDK 27](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html): structured concurrency, Vector API, primitive patterns, PEM và hybrid key exchange cho TLS 1.3 trong JDK 27.
- [JEP 523 — Make G1 the Default Garbage Collector in All Environments](https://openjdk.org/jeps/523): thay đổi default collector trong JDK 27.
- [JEP 527 — Post-Quantum Hybrid Key Exchange for TLS 1.3](https://openjdk.org/jeps/527): hybrid key exchange hậu lượng tử cho TLS 1.3 trong JDK 27.
- [JEP 536 — JFR In-Process Data Redaction](https://openjdk.org/jeps/536): redaction dữ liệu nhạy cảm ngay trong tiến trình trước khi ghi JFR recording trên JDK 27.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): định dạng lỗi HTTP có cấu trúc.


# Tiêu chí nghiệm thu chức năng, hiệu năng và tương thích

## 1. Mục tiêu của bộ tiêu chí nghiệm thu

Khi nâng ứng dụng lên JDK 26 hoặc áp dụng các cải tiến mới của Java 26, việc biên dịch thành công chỉ chứng minh source code có thể được compiler xử lý. Nó chưa chứng minh ứng dụng chạy đúng, đạt SLA, hoạt động trên môi trường triển khai hoặc tương thích với thư viện và dịch vụ bên ngoài.

Bộ tiêu chí nghiệm thu cần trả lời ba câu hỏi:

1. **Chức năng:** Ứng dụng có tạo đúng kết quả, xử lý lỗi, hủy tác vụ và giải phóng tài nguyên theo hợp đồng không?
2. **Hiệu năng:** Thay đổi có cải thiện hoặc giữ được throughput, latency, startup, warmup, CPU và memory trong giới hạn đã thống nhất không?
3. **Tương thích:** Source, bytecode, API, module, provider, thư viện và hệ thống triển khai có hoạt động trên các JDK/OS/CPU được hỗ trợ không?

Mỗi tiêu chí phải có điều kiện kích hoạt, dữ liệu đầu vào, kết quả mong đợi và cách đo. Không dùng các câu chung như "chạy tốt", "nhanh hơn" hoặc "không có lỗi" làm điều kiện nghiệm thu.

Bài học áp dụng cho các nhóm thay đổi trong module Java 26: HTTP/3, primitive patterns, structured concurrency, Vector API, bảo mật và tối ưu JVM. Các ngưỡng cụ thể phải lấy từ SLA và yêu cầu sản phẩm của dự án; không có một con số hiệu năng đúng cho mọi ứng dụng.

## 2. Xác định đúng trạng thái tính năng trước khi nghiệm thu

Tiêu chí đầu tiên là xác định tính năng thuộc loại nào trong đúng JDK sẽ build và chạy.

### 2.1. Trạng thái trên JDK 26

| Tính năng | Trạng thái JDK 26 | Căn cứ | Cách nghiệm thu |
|---|---|---|---|
| HTTP/3 trong `java.net.http.HttpClient` | API chuẩn, stable | JEP 517 | Có thể đưa vào kiểm thử và triển khai theo điều kiện server/network |
| Primitive types trong patterns, `instanceof`, `switch` | Preview lần thứ tư | JEP 530 | Build/run riêng với preview; chưa coi là API ổn định |
| Structured Concurrency | Preview lần thứ sáu | JEP 525 | Build/run riêng với preview; kiểm thử cancellation và lỗi |
| Lazy Constants | Preview lần thứ hai | JEP 526 | Không đưa thành dependency production mặc định |
| PEM Encodings | Preview lần thứ hai | JEP 524 | Kiểm thử riêng với preview và kiểm tra thay đổi API qua từng JDK |
| Vector API | Incubator lần thứ mười một | JEP 529 | Cần module `jdk.incubator.vector`; cô lập dependency và benchmark |
| G1 giảm đồng bộ giữa application/GC threads | Cải tiến runtime stable | JEP 522 | Đo throughput, pause và CPU; không cần preview flag |
| AOT object cache hỗ trợ mọi GC | Cải tiến runtime stable | JEP 516 | Đo startup/warmup và kiểm tra cache theo đúng runtime/artifact |

### 2.2. Trạng thái thay đổi trên JDK 27

JDK 27 tiếp tục cập nhật một số tính năng đang preview hoặc incubator. Vì vậy, không được lấy binary hoặc giả định API của JDK 26 để kết luận tương thích với JDK 27.

| Tính năng | JDK 26 | JDK 27 |
|---|---|---|
| Primitive patterns | Preview lần 4 — JEP 530 | Preview lần 5 — JEP 532 |
| Structured Concurrency | Preview lần 6 — JEP 525 | Preview lần 7 — JEP 533 |
| Vector API | Incubator lần 11 — JEP 529 | Incubator lần 12 — JEP 537 |
| PEM Encodings | Preview lần 2 — JEP 524 | Preview lần 3 — JEP 538 |
| Lazy Constants | Preview lần 2 — JEP 526 | Preview lần 3 — JEP 531 |
| HTTP/3 | API chuẩn từ JDK 26 | Tiếp tục là API chuẩn |
| G1 | Có cải tiến throughput | G1 trở thành GC mặc định trong mọi môi trường — JEP 523 |
| Compact Object Headers | Có thể bật theo cấu hình | Mặc định bật trong HotSpot — JEP 534 |

Đến ngày 27/11/2026, JDK 27 đã phát hành. Nếu dự án hỗ trợ cả JDK 26 và JDK 27, phải có hai lane kiểm thử riêng cho preview/incubator. Với API stable, vẫn cần kiểm thử runtime trên cả hai bản để phát hiện thay đổi hành vi, provider hoặc cấu hình mặc định.

### 2.3. Quy tắc phân loại để quyết định có đưa vào production

- **Stable API/feature:** Có thể xem xét đưa vào production sau khi đạt đủ tiêu chí chức năng, hiệu năng và tương thích.
- **Preview:** Chỉ dùng khi chấp nhận API có thể thay đổi hoặc bị rút lại. Tách build/test profile, không xuất bản như dependency ổn định cho bên thứ ba.
- **Incubator:** API và module còn trong giai đoạn thử nghiệm; phải cô lập adapter, có đường scalar/ổn định thay thế và kế hoạch chuyển đổi khi API thay đổi.
- **Runtime optimization:** Không cần API mới, nhưng vẫn phải benchmark trên workload và cấu hình thực tế.

Một tính năng được đánh dấu stable không có nghĩa mọi server, provider hoặc CPU đều hỗ trợ cùng khả năng. Ví dụ HTTP/3 là API chuẩn trong JDK 26 nhưng endpoint vẫn cần hỗ trợ HTTP/3 và mạng phải cho phép QUIC.

## 3. Viết tiêu chí nghiệm thu theo dạng có thể kiểm chứng

Một tiêu chí tốt nên có đủ các phần:

| Thành phần | Câu hỏi cần trả lời |
|---|---|
| ID | Có mã duy nhất để liên kết requirement, test và báo cáo không? |
| Điều kiện | JDK, OS, CPU, cấu hình và dữ liệu nào được dùng? |
| Hành động | Tác vụ hoặc request nào được thực hiện? |
| Kết quả chức năng | Kết quả, exception, side effect và trạng thái tài nguyên mong đợi là gì? |
| Chỉ số | Đo latency, throughput, memory hoặc startup bằng cách nào? |
| Ngưỡng | Giá trị nào được xem là đạt? |
| Bằng chứng | Test report, benchmark, log, JFR hoặc trace nào chứng minh kết quả? |

Ví dụ tiêu chí theo Given/When/Then:

~~~text
AC-HTTP3-01
Given: JDK 26, HTTPS endpoint có HTTP/3, QUIC/UDP được phép,
       client dùng cấu hình HTTP/3 discovery phù hợp.
When:  Gửi GET request đến endpoint.
Then:  Response body và status đúng hợp đồng API;
       protocol thực tế được xác nhận là HTTP/3;
       không có lỗi TLS hoặc dữ liệu bị cắt.
Evidence: Integration test + server access log + client trace.
~~~

Ví dụ tiêu chí hiệu năng:

~~~text
AC-PERF-01
Given: Cùng build ứng dụng, dữ liệu, CPU quota, memory limit,
       số request đồng thời và thời gian warmup.
When:  Chạy baseline và build sau thay đổi qua nhiều lần đo.
Then:  p95/p99 nằm trong SLO đã phê duyệt;
       throughput không thấp hơn ngưỡng dự án;
       RSS và CPU không vượt ngân sách.
Evidence: Benchmark report + JFR + GC log + application metrics.
~~~

Không đưa số đo vào tiêu chí sau khi đã nhìn thấy kết quả benchmark. Ngưỡng phải được thống nhất trước khi chạy để tránh điều chỉnh tiêu chí theo kết quả thuận lợi.

## 4. Tiêu chí nghiệm thu chức năng

### 4.1. Tính đúng đắn của kết quả

Với mỗi tính năng, cần xác định:

- Đầu vào hợp lệ và đầu vào không hợp lệ.
- Giá trị biên, dữ liệu rỗng, dữ liệu lớn và dữ liệu Unicode.
- Kết quả chính xác hoặc sai số cho phép.
- Thứ tự xử lý và các side effect.
- Exception hoặc error response theo hợp đồng.
- Hành vi khi dependency hoặc môi trường không hỗ trợ tính năng.

Nếu thay đổi thuật toán hoặc runtime optimization, hãy so sánh kết quả với implementation tham chiếu. Với phép tính số học vector, dùng scalar implementation làm oracle để kiểm tra.

### 4.2. Tính đồng thời và khả năng hủy

Với HTTP async, virtual threads và structured concurrency, tiêu chí phải kiểm tra:

- Request hoặc subtask có hoàn thành đúng khi mọi dependency thành công.
- Khi một subtask thất bại, các subtask liên quan có được xử lý/hủy theo chính sách không.
- Khi caller bị interrupt hoặc timeout, tác vụ con có dừng đúng cách không.
- Không để thread, socket, response body, file handle hoặc scope bị bỏ quên.
- Không trả kết quả một phần nếu hợp đồng yêu cầu tất cả tác vụ thành công.
- Không giữ lock hoặc tài nguyên dùng chung quá thời gian cần thiết.

### 4.3. Tính an toàn và bảo mật

Kiểm tra cả đường thành công lẫn đường bị từ chối:

- Thuật toán bị policy chặn không được âm thầm dùng lại.
- TLS certificate phải hợp lệ về trust chain, hostname, thời hạn và mục đích.
- HTTP/3 không được bỏ qua TLS validation.
- Input không hợp lệ phải bị từ chối hoặc chuẩn hóa theo hợp đồng đã định nghĩa.
- Secret, token và dữ liệu nhạy cảm không xuất hiện trong log/test artifact.
- Fallback protocol hoặc scalar fallback không được làm yếu chính sách bảo mật.

## 5. Tiêu chí nghiệm thu HTTP/3 và HTTP Client

HTTP/3 trong `HttpClient` là API stable từ JDK 26. HTTP/3 chạy trên QUIC/UDP; HTTP/1.1 và HTTP/2 chạy trên TCP. HTTP/3 không tự động trở thành protocol mặc định của `HttpClient`; ứng dụng cần chọn preferred version hoặc request discovery phù hợp.

### 5.1. Nghiệm thu chức năng HTTP/3

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| HTTP3-01 | HTTPS endpoint hỗ trợ HTTP/3, UDP/QUIC hoạt động | Request hoàn tất và protocol thực tế là HTTP/3 |
| HTTP3-02 | Server không hỗ trợ HTTP/3, client cho phép fallback | Request vẫn hoàn tất qua HTTP/2 hoặc HTTP/1.1 theo discovery mode |
| HTTP3-03 | Chỉ cho phép HTTP/3 bằng `HTTP_3_URI_ONLY` | Không fallback; lỗi được báo rõ nếu không thiết lập được HTTP/3 |
| HTTP3-04 | Mạng chặn UDP hoặc QUIC | Fallback đúng chính sách hoặc trả lỗi nếu yêu cầu HTTP/3-only |
| HTTP3-05 | TLS certificate không hợp lệ | Handshake bị từ chối; không bỏ qua hostname/certificate validation |
| HTTP3-06 | Request có redirect | Redirect được xử lý theo policy và protocol được chọn lại hợp lệ |
| HTTP3-07 | Proxy được cấu hình | Kiểm tra giới hạn implementation; JDK default HttpClient hiện không dùng HTTP/3 khi proxy được chọn |
| HTTP3-08 | HTTP request body và response body lớn | Body đầy đủ, đúng thứ tự và không bị mất dữ liệu |
| HTTP3-09 | Response body bị chậm | Timeout bao phủ cả thời gian tiêu thụ body theo hành vi JDK 26 |
| HTTP3-10 | Kết nối lại cùng origin | Connection reuse và Alt-Svc/discovery hoạt động theo thiết kế |

HTTP/3 chỉ áp dụng cho URI `https` trong implementation mặc định. Nếu client có proxy hoặc `SSLContext`/`SSLParameters` không phù hợp với HTTP/3, request có thể không dùng được protocol này. Hãy test đúng cấu hình production thay vì chỉ test bằng client mặc định.

### 5.2. Chọn chiến lược discovery có chủ đích

Ví dụ ưu tiên HTTP/3 nhưng cho phép discovery/fallback:

~~~java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_3)
        .build();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.com/data"))
        .GET()
        .build();

HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString()
);
~~~

Nếu nghiệp vụ bắt buộc chỉ dùng HTTP/3, cấu hình discovery rõ ràng:

~~~java
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.com/data"))
        .version(HttpClient.Version.HTTP_3)
        .setOption(
                HttpOption.H3_DISCOVERY,
                HttpOption.Http3DiscoveryMode.HTTP_3_URI_ONLY
        )
        .GET()
        .build();
~~~

Tiêu chí nghiệm thu phải phân biệt rõ hai trường hợp: ưu tiên HTTP/3 có fallback và HTTP/3-only. Không kiểm tra chỉ bằng `HttpClient.Version` đã cấu hình; cần xác nhận protocol thực tế bằng trace, server log hoặc công cụ quan sát phù hợp.

### 5.3. Nghiệm thu upload vùng file bằng FileChannel

JDK 26 bổ sung `BodyPublishers.ofFileChannel(FileChannel, long, long)` để upload một vùng file mà không cần đọc toàn bộ file vào heap.

Kiểm tra:

- Offset và length hợp lệ.
- Chỉ các byte trong vùng yêu cầu được gửi.
- Dữ liệu nhận ở server khớp byte-for-byte với vùng file nguồn.
- `FileChannel` được truyền vào không bị thay đổi vị trí hiện tại.
- Backpressure, cancellation và lỗi đọc file được xử lý đúng.
- Upload file lớn không làm heap tăng tương ứng với toàn bộ kích thước file.

### 5.4. Kiểm tra thay đổi hành vi HTTP Client trong JDK 26

Một số thay đổi hành vi cần có regression test nếu ứng dụng phụ thuộc vào chúng:

- `HttpRequest.Builder.timeout` hiện bao phủ cả việc tiêu thụ response body, không chỉ đến lúc nhận response headers.
- Với HTTP/1.1 request dùng `BodyPublisher` báo `contentLength() == 0` và method không phải POST/PUT, HttpClient không còn tự gửi `Content-Length: 0` trong trường hợp tương ứng.
- `BodyPublishers.ofFile` chuẩn hóa lỗi file không tồn tại thành `FileNotFoundException`.
- HTTP server built-in thay đổi cách chia sẻ `HttpContext` attributes với từng `HttpExchange`; mỗi exchange có map riêng theo mặc định.

Không đưa mọi thay đổi này vào một test chung. Mỗi behavior cần một ca test có assertion cụ thể và chỉ áp dụng khi ứng dụng sử dụng chức năng liên quan.

## 6. Tiêu chí nghiệm thu Primitive Patterns

Primitive types trong patterns, `instanceof` và `switch` vẫn là preview trong JDK 26. Trạng thái là preview lần thứ tư ở JDK 26 và tiếp tục được preview lần thứ năm ở JDK 27.

### 6.1. Kiểm tra chức năng

Với mọi pattern mới được sử dụng, cần kiểm tra:

- Nhánh đúng được chọn với từng kiểu primitive được hỗ trợ.
- Giá trị nằm đúng biên của miền kiểu.
- Chuyển đổi widening/narrowing tuân theo quy tắc của preview release đang dùng.
- Guard `when` đúng với điều kiện nghiệp vụ.
- `switch` xử lý đầy đủ các nhánh và không có nhánh vô tình bị chi phối.
- Giá trị `NaN`, positive/negative infinity, `+0.0` và `-0.0` được xử lý theo đặc tả nghiệp vụ.
- Kết quả tương đương implementation hiện tại ở mọi input hợp lệ.

Ví dụ ca kiểm thử:

| Nhóm | Giá trị kiểm thử | Assertion |
|---|---|---|
| Integer boundary | `Integer.MIN_VALUE`, `Integer.MAX_VALUE` | Không overflow hoặc rẽ nhánh sai |
| Floating boundary | `NaN`, `POSITIVE_INFINITY` | Nhánh theo đặc tả được chọn |
| Signed zero | `+0.0`, `-0.0` | Không làm mất khác biệt nếu nghiệp vụ cần phân biệt |
| Conversion | Các cặp primitive có quan hệ chuyển đổi | Chỉ chấp nhận conversion được đặc tả cho phép |
| Guard | Giá trị sát ngưỡng `when` | Nhánh đúng tại biên |
| Switch coverage | Mọi giá trị và pattern label | Không thiếu nhánh, không có dominance ngoài dự kiến |

### 6.2. Không nhầm preview với stable

Build và chạy bằng cùng release JDK:

~~~bash
javac --release 26 --enable-preview -Xlint:preview -d out src/main/java/example/PatternDemo.java
java --enable-preview -cp out example.PatternDemo
~~~

Không được compile preview bằng JDK 26 rồi lấy class file đó chạy trên JDK 27 chỉ bằng cách thêm `--enable-preview`. Class file phụ thuộc preview của một release chỉ được chạy với đúng release đó.

Nếu kiểm tra JDK 27, compile lại bằng JDK 27 compiler với `--release 27 --enable-preview`, sau đó chạy bằng JDK 27 với `--enable-preview`. API hoặc quy tắc preview có thể đã thay đổi.

## 7. Tiêu chí nghiệm thu Structured Concurrency

Structured Concurrency là preview API trên JDK 26 và JDK 27. Cần đánh giá đúng phiên bản API vì `StructuredTaskScope`, Joiner, Subtask và các kiểu exception/configuration có thể thay đổi giữa các preview round.

### 7.1. Kiểm tra vòng đời tác vụ

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| SC-01 | Mọi subtask thành công | Scope join và trả kết quả theo Joiner |
| SC-02 | Một subtask thất bại | Kết quả lỗi được truyền theo policy; các subtask liên quan được hủy nếu Joiner yêu cầu |
| SC-03 | Caller bị interrupt | Scope xử lý interruption đúng hợp đồng và không để task mồ côi |
| SC-04 | Deadline hết hạn | Scope được cancel; caller nhận kết quả/exception đã định nghĩa |
| SC-05 | Subtask chậm hoặc treo | Timeout/cancellation giải phóng tài nguyên theo thiết kế |
| SC-06 | Scope lồng nhau | Thứ tự đóng scope hợp lệ; không có structure violation |
| SC-07 | Resource trong subtask | Socket, response body, file và database resource được đóng |
| SC-08 | Context propagation | Scoped values/security context được kế thừa theo thiết kế và không rò rỉ sang request khác |

### 7.2. Kiểm tra không có tác vụ mồ côi

Sau khi request hoàn tất hoặc thất bại:

- Không còn subtask chạy ngầm ngoài lifetime của scope.
- Không giữ thread hoặc resource do task đã bị hủy.
- Không bỏ qua exception từ subtask.
- Không trả response thành công khi task bắt buộc chưa hoàn tất.
- Không để timeout ở tầng HTTP nhưng subtask vẫn tiếp tục thực hiện side effect.

Với tác vụ có side effect như ghi database hoặc gửi lệnh thanh toán, cancellation không tự động rollback hành động đã được gửi ra hệ thống bên ngoài. Tiêu chí cần kiểm tra tính idempotent, transaction boundary và khả năng bù trừ theo nghiệp vụ.

### 7.3. Build/test riêng cho preview

~~~bash
javac --release 26 --enable-preview -Xlint:preview -d out src/main/java/example/ConcurrentService.java
java --enable-preview -cp out example.ConcurrentService
~~~

Tạo lane riêng cho JDK 26 và JDK 27. Không đưa preview API vào public library hoặc module dùng chung nếu consumer không thể khóa đúng JDK release.

## 8. Tiêu chí nghiệm thu Vector API

Vector API trong JDK 26 là incubator module lần thứ mười một. Trên JDK 27, API tiếp tục là incubator lần thứ mười hai. Module `jdk.incubator.vector` chưa phải Java SE stable API và có thể thay đổi hoặc bị loại bỏ trong tương lai.

### 8.1. Kiểm tra tính đúng đắn

Vector implementation phải cho kết quả tương đương scalar reference trong miền dữ liệu đã cam kết.

| Nhóm test | Nội dung |
|---|---|
| Vector lanes | Số phần tử bằng đúng số lane, lớn hơn một vector và nhỏ hơn một vector |
| Tail handling | Số phần tử không chia hết cho vector length |
| Mask | Mask đúng với lane hợp lệ, không đọc/ghi ngoài mảng |
| Boundary | Mảng rỗng, một phần tử, kích thước lớn, offset khác 0 |
| Numeric | Overflow, underflow, NaN, infinity, signed zero và rounding |
| Alignment | Offset và địa chỉ không căn chỉnh nếu implementation hỗ trợ |
| Data types | Các primitive type thực sự được thuật toán dùng |
| Concurrency | Nhiều request cùng gọi vector routine không chia sẻ mutable state ngoài ý muốn |

Không so sánh floating-point bằng `==` nếu thuật toán có phép toán mà thứ tự thực thi có thể làm thay đổi rounding. Xác định trước tiêu chí sai số tuyệt đối/tương đối và các trường hợp cần bitwise equality.

### 8.2. Kiểm tra hiệu năng trên nhiều CPU

Vector API chỉ có lợi khi runtime và CPU hỗ trợ các vector instruction phù hợp. Phải đo trên các kiến trúc production, chẳng hạn x86-64 và AArch64 nếu hệ thống triển khai trên cả hai.

Nghiệm thu cần trả lời:

- Vector implementation có nhanh hơn scalar baseline trên CPU mục tiêu không?
- Trên CPU khác, có hoạt động đúng và có fallback phù hợp không?
- Kích thước dữ liệu nhỏ có bị overhead lớn hơn scalar không?
- Tail handling và mask có làm mất lợi ích hiệu năng không?
- Allocation hoặc memory bandwidth có trở thành bottleneck không?
- JIT có thực sự tạo vector code trong workload production-like không?

### 8.3. Module và build

Trên classpath/unnamed module, có thể khai báo module lúc compile và run:

~~~bash
javac --add-modules jdk.incubator.vector -d out src/main/java/example/VectorDemo.java
java --add-modules jdk.incubator.vector -cp out example.VectorDemo
~~~

Trong ứng dụng modular, khai báo `requires jdk.incubator.vector;` trong `module-info.java`.

`--enable-preview` không thay thế `--add-modules jdk.incubator.vector`. Preview và incubator là hai cơ chế khác nhau.

Giữ vector-specific code trong một module/adapter riêng. Cung cấp scalar implementation làm kết quả tham chiếu và fallback khi ứng dụng chạy trên runtime không có module incubator hoặc khi chưa chấp nhận API đó.

## 9. Tiêu chí nghiệm thu bảo mật

Các cải tiến bảo mật phải được kiểm tra bằng test tích hợp và policy thực tế, không chỉ bằng unit test gọi API.

### 9.1. Thuật toán và provider

Với các policy như `jdk.crypto.disabledAlgorithms`, `jdk.tls.disabledAlgorithms` và `jdk.certpath.disabledAlgorithms`, xác nhận từng phạm vi:

- Dịch vụ JCA/JCE bị hạn chế không được sử dụng.
- TLS không thương lượng protocol/cipher/signature đã bị chặn.
- PKIX từ chối certificate path có thuật toán/key size vi phạm.
- Thuật toán legacy không bị nhầm với thuật toán disabled.
- Provider thực tế được ghi nhận và nằm trong danh sách được hỗ trợ.

Không làm test pass bằng cách bỏ các policy bảo mật hoặc tắt certificate/hostname validation.

### 9.2. TLS và certificate

Các ca test tối thiểu:

- Certificate hợp lệ, hostname đúng và chain được tin cậy.
- Certificate hết hạn, hostname sai hoặc chain không đầy đủ.
- Certificate sử dụng thuật toán/key size bị policy chặn.
- Trust anchor bị distrust theo policy.
- TLS handshake với peer chỉ hỗ trợ protocol/cipher bị chặn.
- TLS handshake với peer hỗ trợ cấu hình hiện hành.
- Client/server certificate selection đúng với signature schemes và named groups.

### 9.3. Tiêu chí bảo mật dữ liệu

- Không ghi private key, password, token hoặc raw secret vào test log.
- Không đưa dữ liệu production nhạy cảm vào benchmark/training.
- Các cache, PEM artifact, keystore và certificate test được quản lý quyền truy cập.
- Không tắt validation để vượt qua lỗi môi trường.
- Kết quả fail phải có log đủ để xác định policy/provider đã từ chối ở tầng nào.

## 10. Tiêu chí nghiệm thu tối ưu JVM

Các thay đổi G1 và AOT cache là tối ưu runtime. Không cần thêm API ứng dụng, nhưng phải chứng minh tác động bằng phép đo có kiểm soát.

### 10.1. G1 throughput

JEP 522 cải thiện throughput bằng cách giảm đồng bộ giữa application threads và GC refinement threads. Nghiệm thu bằng workload có nhiều cập nhật object reference:

- So sánh cùng ứng dụng, dữ liệu, heap, collector và phần cứng.
- Đo throughput và CPU utilization.
- Theo dõi GC pause p50/p95/p99 và tổng thời gian pause.
- Kiểm tra heap occupancy, allocation rate và native memory.
- Không giả định mọi workload đều tăng tốc cùng một tỷ lệ.

JDK 27 đưa G1 thành collector mặc định trong mọi môi trường. Nếu hỗ trợ JDK 27, cần kiểm tra ứng dụng trước đây dùng Serial GC theo ergonomics trên container nhỏ có chuyển sang G1 hay không.

### 10.2. AOT cache

JEP 516 giúp AOT object caching hoạt động với mọi GC, gồm ZGC. Nghiệm thu cần có hai cấu hình:

- Không dùng cache để tạo baseline.
- Dùng cache được tạo từ đúng JDK, OS, CPU, application artifact và classpath.

Đo:

- Process startup và readiness time.
- First useful request.
- Warmup time đến throughput ổn định.
- CPU và RSS trong startup.
- Kích thước file cache.
- Thời gian training và assembly.
- Tỷ lệ cache được nạp thành công ở production.

Cache không tương thích phải fallback theo chế độ triển khai đã chọn. Với production, cần xác nhận ứng dụng vẫn chạy đúng khi cache bị thiếu hoặc không sử dụng được.

### 10.3. Compact Object Headers trên JDK 27

JDK 27 bật Compact Object Headers mặc định trong HotSpot. Nếu hỗ trợ JDK 27, đo:

- Heap used/committed và RSS.
- Throughput/latency ở workload tạo nhiều object.
- Startup và GC pause.
- Tương thích với JNI/JVMTI agent hoặc thư viện có giả định về object layout.

Native code không được suy đoán hoặc truy cập trực tiếp layout nội bộ của object. Chỉ dùng các JNI/JVMTI contract được tài liệu công bố.

## 11. Tiêu chí nghiệm thu hiệu năng

### 11.1. Chọn chỉ số theo loại thay đổi

| Chỉ số | Ý nghĩa | Áp dụng |
|---|---|---|
| Startup time | Thời gian từ process start đến readiness | AOT, runtime upgrade |
| Warmup time | Thời gian đến khi throughput/latency ổn định | AOT, JIT, vector |
| Throughput | Request hoặc công việc hoàn thành mỗi giây | HTTP, concurrency, Vector, G1 |
| p50/p95/p99 latency | Độ trễ ở các phân vị | HTTP, structured concurrency, G1 |
| CPU utilization | CPU ứng dụng và GC tiêu thụ | Vector, G1, HTTP/3, AOT |
| Heap/RSS | Bộ nhớ heap và tổng process | Vector, G1, AOT, object headers |
| Allocation rate | Tốc độ cấp phát object | G1, structured concurrency |
| GC pause | Thời gian dừng do GC | G1 |
| Network metrics | RTT, retransmission, packet loss, UDP/TCP, bytes | HTTP/3 |
| Error/cancel rate | Tỷ lệ request hoặc task lỗi/hủy | HTTP, structured concurrency |

Không dùng một chỉ số duy nhất. Ví dụ throughput tăng nhưng p99 latency vượt SLA thì thay đổi vẫn không đạt.

### 11.2. Xác định ngưỡng trước khi benchmark

Mỗi dự án phải định nghĩa:

- SLO p95/p99 cho endpoint quan trọng.
- Throughput tối thiểu tại tải dự kiến.
- CPU quota và giới hạn memory.
- Startup/readiness budget.
- Warmup budget khi scale-out.
- Tỷ lệ lỗi và timeout cho phép.
- Regression tolerance cho các chỉ số không phải mục tiêu chính.

Ví dụ minh họa về cấu trúc ngưỡng:

~~~text
Throughput >= [project minimum]
p95 latency <= [service SLO]
p99 latency <= [service SLO]
Startup/readiness <= [startup budget]
RSS <= [container memory budget]
Error rate <= [error budget]
~~~

Thay các placeholder bằng số đã được product/operations chấp thuận. Không lấy số trong ví dụ của tài liệu hoặc benchmark máy cá nhân làm SLO production.

### 11.3. Benchmark có thể lặp lại

Giữ các điều kiện giống nhau giữa baseline và candidate:

1. Cùng JDK vendor, feature release và update build, trừ phiên bản đang được so sánh.
2. Cùng CPU model, OS, container CPU quota và memory limit.
3. Cùng heap options, GC collector và JVM flags nếu đang so sánh riêng một tính năng.
4. Cùng application artifact, dependency, dữ liệu và cấu hình.
5. Cùng số client, concurrency, request mix và thời lượng tải.
6. Có warmup trước khi đo steady state.
7. Chạy nhiều fork/lần đo và báo cáo median, percentile cùng độ phân tán.
8. Lưu log, JFR, benchmark output và version metadata.

Với microbenchmark JVM, dùng JMH thay cho tự đo thời gian bằng `System.nanoTime()` trong một vòng lặp đơn giản. Với end-to-end performance, dùng load generator và production-like environment.

### 11.4. Không để benchmark tạo kết luận sai

Tránh các lỗi:

- Chạy chỉ một lần rồi kết luận.
- Đo khi JIT chưa warmup.
- So sánh cold start với warm start.
- Dùng dữ liệu nhỏ không đại diện production.
- Chạy baseline và candidate trên hai máy khác nhau.
- Thay nhiều JVM flags cùng lúc nên không biết thay đổi nào tạo kết quả.
- Chỉ đo average latency mà bỏ qua p95/p99.
- Chỉ đo CPU mà bỏ qua memory và GC.
- Chỉ đo vector microbenchmark mà không đo toàn ứng dụng.
- Bỏ qua CPU throttling, network congestion và storage page cache.

## 12. Tiêu chí nghiệm thu tương thích

Oracle phân loại compatibility thành ba nhóm: source, binary và behavioral. Cả ba đều cần được kiểm tra khi nâng JDK.

### 12.1. Source compatibility

Source compatibility trả lời: source hiện tại có compile được trên compiler mục tiêu không?

Kiểm tra:

- API mới/đã đổi package/module có được tham chiếu đúng không.
- Compiler có phát hiện overload ambiguity hoặc method reference không còn hợp lệ không.
- Preview feature có được bật đúng release không.
- Incubator module có được resolve không.
- Warning deprecation/removal có được xử lý không.
- Annotation processor, code generator và compiler plugin có hỗ trợ JDK mới không.

JDK 26 `javac` có thể từ chối một số source method reference mà compiler trước đó chấp nhận do áp dụng đầy đủ capture conversion theo JLS. Vì vậy, không chỉ compile file mới; cần compile lại toàn bộ module và generated source.

### 12.2. Binary compatibility

Binary compatibility trả lời: class file đã biên dịch có thể link và nạp trên runtime mới không?

Kiểm tra:

- Thư viện bên thứ ba có dùng API đã bị loại bỏ không.
- JNI/JVMTI/native agent có giả định về layout hoặc internal JDK representation không.
- Module descriptor, service provider và reflection có hoạt động không.
- Preview class file có bị đưa sang JDK khác release không.
- Classpath/module path production có giống cấu hình test không.

Không truy cập trực tiếp JDK internal API hoặc JVM object layout. Nếu native library phụ thuộc chi tiết nội bộ không được công bố, nâng JDK có thể làm binary đó không còn hoạt động.

### 12.3. Behavioral compatibility

Behavioral compatibility trả lời: chương trình vẫn có hành vi giống hợp đồng trước đây không?

Các thay đổi JDK 26 cần kiểm tra nếu ứng dụng có sử dụng:

| Thành phần | Thay đổi cần kiểm tra |
|---|---|
| `HttpRequest.timeout` | Timeout hiện bao phủ cả việc tiêu thụ response body |
| HTTP/1.1 request không body | `Content-Length: 0` không còn tự gửi trong trường hợp method không phải POST/PUT |
| Built-in `HttpServer` | `HttpContext` attributes không còn được chia sẻ với mọi exchange theo mặc định |
| RMI TLS | Endpoint identification được bật mặc định |
| `Cipher.getInstance` | `NoSuchPaddingException` có thể được ném trực tiếp thay vì bọc trong `NoSuchAlgorithmException` |
| `jmethodID` trong native code | Không được giả định đây là con trỏ trực tiếp tới JVM Method |

Chỉ áp dụng test cho các module đang dùng API liên quan. Mục tiêu là xác nhận hợp đồng ứng dụng, không phải kiểm tra mọi thay đổi của JDK bằng một bộ test khổng lồ không có phân loại.

## 13. Ma trận tương thích JDK và môi trường

Một ma trận phù hợp cho dự án đang nâng lên Java 26 có thể gồm:

| Lane | JDK | Mục đích |
|---|---|---|
| Baseline | JDK hiện tại của production, ví dụ JDK 25 | Đối chiếu hành vi và hiệu năng trước nâng cấp |
| Candidate | JDK 26 GA/update được chọn | Kiểm tra tính năng và thay đổi của Java 26 |
| Forward compatibility | JDK 27 GA nếu dự án hỗ trợ | Kiểm tra API stable và thay đổi runtime tiếp theo |
| Preview 26 | JDK 26 với `--enable-preview` | Chỉ kiểm tra primitive patterns, structured concurrency, PEM, lazy constants |
| Preview 27 | JDK 27 với `--enable-preview` | Kiểm tra preview round tương ứng của JDK 27 |
| Vector 26 | JDK 26 với `--add-modules jdk.incubator.vector` | Kiểm tra incubator API và hiệu năng SIMD |
| Vector 27 | JDK 27 với incubator API tương ứng | Kiểm tra thay đổi module/API và hiệu năng |
| CPU matrix | x86-64 và AArch64 nếu production dùng cả hai | Kiểm tra vector instruction và runtime-specific behavior |
| Network matrix | HTTP/3 có/không, UDP bị chặn, proxy, TLS peer khác nhau | Kiểm tra protocol negotiation và fallback |

Không cần chạy mọi lane cho mọi commit. Có thể chia thành smoke test nhanh cho pull request, regression đầy đủ trước release và performance suite định kỳ. Nhưng trước khi phát hành, tất cả lane liên quan đến runtime production phải đạt.

## 14. Build và test đúng với preview/incubator

### 14.1. API stable

Dùng `--release` để giới hạn ngôn ngữ và Java SE API theo version mục tiêu:

~~~bash
javac --release 26 -Xlint:all -d out src/main/java/example/App.java
java -cp out example.App
~~~

Nếu dự án cần chạy trên Java 25, build bằng `--release 25` và không dùng API chỉ có từ JDK 26.

### 14.2. Preview trên JDK 26

~~~bash
javac --release 26 --enable-preview -Xlint:preview -d out src/main/java/example/PreviewDemo.java
java --enable-preview -cp out example.PreviewDemo
~~~

Phải bật preview ở cả compile time và run time. Preview class file của JDK 26 gắn với preview của JDK 26; không dùng lại trên JDK 27.

### 14.3. Incubator Vector API

~~~bash
javac --add-modules jdk.incubator.vector -d out src/main/java/example/VectorDemo.java
java --add-modules jdk.incubator.vector -cp out example.VectorDemo
~~~

Trong ứng dụng modular, khai báo `requires jdk.incubator.vector;` trong `module-info.java`. Không nhầm `--add-modules` với `--enable-preview`.

### 14.4. Không gộp preview/incubator vào build production stable

Tạo profile/lane riêng để:

- Build stable source không bật preview.
- Build preview source bằng đúng JDK release.
- Build Vector API với module incubator.
- Chạy test runtime bằng cùng feature release.
- Kiểm tra dependency tree không vô tình kéo preview/incubator vào artifact stable.
- Chỉ đóng gói production artifact từ lane stable đã được phê duyệt.

## 15. Mẫu ma trận nghiệm thu theo tính năng

Bảng dưới đây có thể dùng làm khung cho test plan của dự án. Bổ sung owner, ngưỡng và test ID cụ thể trước khi release.

| Nhóm | Chức năng | Hiệu năng | Tương thích |
|---|---|---|---|
| HTTP/3 | Protocol, TLS, body, redirect, fallback và timeout đúng | p95/p99, throughput, connection setup, UDP/network cost | HTTPS, QUIC, proxy, HTTP/2/1.1 peer |
| Primitive patterns | Nhánh, guard, boundary, conversion đúng | Không tạo regression đáng kể trên đường code đã thay đổi | Preview đúng release, compile/runtime flags |
| Structured concurrency | Join, failure, cancellation, timeout, resource cleanup | Task completion, latency, thread/resource usage | Preview API round, interrupt semantics, framework |
| Vector API | Scalar-equivalent result, mask/tail/boundary đúng | Speedup có ý nghĩa trên CPU mục tiêu, không tăng memory vượt budget | Incubator module, CPU architecture, JDK round |
| Security | Policy, trust chain, hostname và algorithm rejection đúng | TLS handshake cost, crypto throughput và CPU | Provider, truststore, certificate chain, peer |
| G1 | Kết quả nghiệp vụ không đổi, GC không gây lỗi | Throughput, pause, CPU, heap/RSS | GC default và JVM options trên JDK mục tiêu |
| AOT cache | Cache được nạp hoặc fallback đúng | Startup, readiness, warmup, CPU/RSS, cache size | JDK, OS, CPU, app artifact, classpath |
| Runtime migration | API và lỗi theo hợp đồng | Không vượt regression budget | Source/binary/behavioral trên JDK matrix |

## 16. Ví dụ kế hoạch nghiệm thu trước release

### 16.1. Trước khi bắt đầu

- Chốt JDK vendor, version/update và môi trường chạy.
- Ghi lại baseline build, JVM flags, dependency versions và artifact checksum.
- Chốt SLO và regression budget.
- Xác định tính năng stable, preview hoặc incubator.
- Liệt kê các module, endpoint và native agent bị ảnh hưởng.

### 16.2. Trong quá trình kiểm thử

1. Compile toàn bộ project với JDK mục tiêu.
2. Chạy unit test cho logic đã thay đổi.
3. Chạy integration test với HTTP server, database, certificate và dependency thật hoặc môi trường staging.
4. Chạy compatibility test trên các JDK/OS/CPU được hỗ trợ.
5. Chạy security test với policy thực tế.
6. Chạy load/performance test với workload production-like.
7. Thu thập JFR, GC log, HTTP trace và test reports.
8. So sánh kết quả với baseline và ngưỡng đã chốt.

### 16.3. Trước khi phát hành

- Tất cả test chức năng critical pass.
- Không có lỗi source/binary/behavioral chưa được đánh giá.
- Không có security regression hoặc bypass policy.
- p95/p99 và throughput đạt SLO.
- CPU, RSS, heap và startup nằm trong ngân sách.
- Preview/incubator không bị đưa vào stable artifact ngoài chủ đích.
- Có fallback/rollback cho thay đổi runtime hoặc protocol.
- Lưu bằng chứng test cùng artifact được phát hành.

## 17. Quy tắc quyết định đạt/không đạt

### Đạt

Một thay đổi được nghiệm thu khi:

- Mọi yêu cầu chức năng bắt buộc có test và bằng chứng pass.
- Không có lỗi bảo mật hoặc lỗi tương thích chưa được xử lý.
- Chỉ số hiệu năng nằm trong ngưỡng đã thống nhất.
- Mọi JDK/OS/CPU nằm trong support matrix đều đạt.
- Tính năng preview/incubator được cô lập đúng phạm vi và có quyết định chấp nhận rủi ro rõ ràng.

### Không đạt

Không phát hành nếu xảy ra một trong các trường hợp:

- Kết quả chức năng sai hoặc không xác định được.
- Request/task bị mất, chạy mồ côi hoặc không được cancel đúng.
- p95/p99, throughput hoặc memory vượt SLO.
- HTTP/3-only bị fallback trái yêu cầu hoặc TLS validation bị bỏ qua.
- Vector result khác scalar reference ngoài sai số cho phép.
- Preview class file bị đưa sang runtime release khác.
- Incubator module bị phụ thuộc ngầm trong artifact stable.
- Security policy bị vô hiệu hóa để làm test pass.
- Native agent hoặc thư viện không tương thích với runtime mới.

### Chấp nhận có điều kiện

Chỉ chấp nhận khi:

- Vấn đề không ảnh hưởng chức năng, bảo mật hoặc SLA bắt buộc.
- Có owner, deadline và issue theo dõi.
- Có fallback hoặc giới hạn rollout.
- Có bằng chứng rằng rủi ro được kiểm soát.
- Quyết định được ghi nhận trong release review.

Không dùng trạng thái "pass with warning" để che lỗi security, data corruption hoặc compatibility failure.

## 18. Kết luận

Tiêu chí nghiệm thu cho Java 26 phải tách chức năng, hiệu năng và tương thích. Một tính năng chỉ được xem là sẵn sàng khi có test xác nhận kết quả đúng, benchmark chứng minh đáp ứng SLO và runtime/dependency được kiểm tra trên môi trường hỗ trợ.

Các điểm cần nhớ:

- HTTP/3 là API stable trong JDK 26 nhưng vẫn cần kiểm tra QUIC, HTTPS, proxy, discovery và fallback.
- Primitive patterns, Structured Concurrency, PEM và Lazy Constants là preview trên JDK 26; Vector API là incubator.
- Preview phải compile và run bằng đúng JDK release; incubator cần resolve module riêng.
- JDK 27 tiếp tục đổi preview/incubator round, vì vậy không tái sử dụng preview class file của JDK 26.
- Đo throughput, p95/p99, startup, warmup, CPU, memory, GC và network theo workload thật.
- Kiểm tra source, binary và behavioral compatibility; chú ý các thay đổi HTTP Client và runtime defaults.
- Không bật preview/incubator trong production stable artifact nếu chưa có quyết định chấp nhận rõ ràng.
- Chỉ phát hành khi test evidence, SLO và compatibility matrix đều đạt.

Bộ tiêu chí nghiệm thu tốt giúp đội ngũ biết chính xác thay đổi nào được phép phát hành, thay đổi nào cần thêm thử nghiệm và thay đổi nào phải hoãn. Nó cũng tạo bằng chứng có thể lặp lại cho các lần nâng cấp JDK tiếp theo.

## Tài liệu tham khảo chính thức

- [JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html)
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)
- [Oracle JDK 26 Migration Guide — Preparing for Migration](https://docs.oracle.com/en/java/javase/26/migrate/preparing-migration.html)
- [The javac Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html)
- [Java SE 26 Preview API List](https://docs.oracle.com/en/java/javase/26/docs/api/preview-list.html)
- [Java SE 26 Primitive Types in Patterns, instanceof, and switch](https://docs.oracle.com/en/java/javase/26/language/primitive-types-patterns-instanceof-switch.html)
- [StructuredTaskScope — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html)
- [Vector API — Java SE 26 Incubator Module](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html)
- [HttpClient — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html)
- [HttpOption.Http3DiscoveryMode — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpOption.Http3DiscoveryMode.html)
- [HTTP Client Updates in Java 26 — Inside Java](https://inside.java/2026/03/04/jdk-26-http-client/)
- [JEP 517 — HTTP/3 for the HTTP Client API](https://openjdk.org/jeps/517)
- [JEP 522 — G1 GC: Improve Throughput by Reducing Synchronization](https://openjdk.org/jeps/522)
- [JEP 516 — Ahead-of-Time Object Caching with Any GC](https://openjdk.org/jeps/516)
- [JEP 530 — Primitive Types in Patterns, instanceof, and switch (Fourth Preview)](https://openjdk.org/jeps/530)
- [JEP 525 — Structured Concurrency (Sixth Preview)](https://openjdk.org/jeps/525)
- [JEP 529 — Vector API (Eleventh Incubator)](https://openjdk.org/jeps/529)
- [JEP 526 — Lazy Constants (Second Preview)](https://openjdk.org/jeps/526)
- [JEP 532 — Primitive Types in Patterns, instanceof, and switch (Fifth Preview, JDK 27)](https://openjdk.org/jeps/532)
- [JEP 533 — Structured Concurrency (Seventh Preview, JDK 27)](https://openjdk.org/jeps/533)
- [JEP 537 — Vector API (Twelfth Incubator, JDK 27)](https://openjdk.org/jeps/537)
- [JEP 538 — PEM Encodings of Cryptographic Objects (Third Preview, JDK 27)](https://openjdk.org/jeps/538)
- [JEP 523 — Make G1 the Default Garbage Collector in All Environments (JDK 27)](https://openjdk.org/jeps/523)
- [JEP 534 — Compact Object Headers (JDK 27)](https://openjdk.org/jeps/534)


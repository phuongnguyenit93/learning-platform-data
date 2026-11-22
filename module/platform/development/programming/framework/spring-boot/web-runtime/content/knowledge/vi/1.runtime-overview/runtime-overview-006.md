# Tài nguyên khi chạy: kết nối, luồng, bộ nhớ, phiên và bộ đệm

## 1. Vì sao phải hiểu tài nguyên runtime?

Một ứng dụng Spring Boot không chỉ chạy các phương thức trong Controller. Khi nhận một HTTP request, ứng dụng phải duy trì kết nối mạng, bố trí luồng thực thi, sử dụng bộ nhớ cho dữ liệu và đối tượng, có thể đọc trạng thái phiên, mượn kết nối đến cơ sở dữ liệu hoặc dịch vụ ngoài, rồi ghi dữ liệu qua các bộ đệm trước khi trả response. Các tài nguyên này hữu hạn và có vòng đời khác nhau.

Điều quan trọng nhất là phân biệt **số request đang xử lý** với **số kết nối, số luồng, số kết nối DB và lượng bộ nhớ đang dùng**. Chúng có quan hệ nhưng không tương đương. Tăng một giới hạn đơn lẻ có thể chuyển nút thắt sang tài nguyên khác hoặc làm hệ thống quá tải nhanh hơn.

Mục tiêu của bài: nhận diện từng loại tài nguyên; hiểu ai tạo, giữ, tái sử dụng và giải phóng nó; đọc triệu chứng khi cạn tài nguyên; đặt giới hạn phù hợp; và kiểm chứng bằng số đo thay vì điều chỉnh theo cảm tính.

## 2. Bản đồ tài nguyên trong một yêu cầu web

| Tài nguyên | Vai trò | Vòng đời điển hình | Khi bị giới hạn |
| --- | --- | --- | --- |
| Kết nối HTTP vào | Kênh TCP/TLS giữa client, proxy và web server | Có thể được giữ lại cho nhiều request (keep-alive) | Không nhận được kết nối mới, chờ hoặc bị từ chối |
| Luồng/worker | Thực thi mã xử lý; có thể chờ I/O chặn trong Spring MVC | Được pool tái sử dụng qua nhiều request | Request xếp hàng, độ trễ tăng |
| Kết nối ra ngoài | Truy cập DB, Redis, HTTP service khác | Thường lấy từ pool và trả về sau thao tác | Chờ lấy kết nối, timeout, lỗi phụ thuộc |
| Bộ nhớ | Đối tượng Java, payload, phiên, cache, stack và bộ nhớ native | Tùy đối tượng, request hoặc vòng đời process | GC nhiều, tăng latency, OOM hoặc container bị kill |
| Phiên HTTP | Giữ trạng thái giữa các request của một client khi ứng dụng cần | Tồn tại đến timeout/invalidate | Tốn bộ nhớ/store, khó mở rộng nhiều instance |
| Bộ đệm (buffer) | Lưu tạm khối dữ liệu để đọc/ghi theo lô | Thường ngắn hạn, theo luồng hoặc kết nối | Dồn dữ liệu, tăng memory, backpressure |

Ví dụ luồng xử lý của ứng dụng **Spring MVC + Tomcat + JDBC**:

1. Client kết nối qua load balancer đến Tomcat; HTTP keep-alive có thể tái sử dụng socket cho request tiếp theo.
2. Tomcat phân phối request đến một worker. Nếu Controller gọi JDBC đồng bộ, worker thường bị giữ trong thời gian chờ DB.
3. Tầng truy cập dữ liệu mượn một kết nối DB từ HikariCP; lệnh SQL chạy, kết quả được ánh xạ thành các đối tượng trong heap; khi phạm vi thao tác/transaction hoàn tất, kết nối được trả về pool.
4. Khi áp dụng phiên, request có thể đọc/cập nhật dữ liệu gắn với session ID; phiên có vòng đời riêng với luồng đang xử lý.
5. Framework ghi response qua các buffer của ứng dụng, web server và hệ điều hành. Worker được giải phóng sau khi hoàn tất xử lý; socket HTTP có thể còn mở để tái sử dụng.

Đây là mô hình khái quát, không phải quy tắc một socket = một luồng = một DB connection. HTTP/2 có thể ghép nhiều luồng request trên một kết nối; Spring MVC có cơ chế xử lý bất đồng bộ; và một request có thể không gọi DB.

## 3. Kết nối (connections): mở, tái sử dụng, trả về pool

### 3.1. Phân biệt ba đường kết nối

- **Kết nối inbound HTTP**: từ client/load balancer tới embedded server như Tomcat, Jetty hoặc Reactor Netty. Giới hạn về số kết nối, thời gian chờ và keep-alive thuộc lớp web server.
- **Kết nối outbound HTTP**: ứng dụng gọi API khác bằng RestClient, WebClient hoặc thư viện HTTP tương ứng. Có pool, timeout và chính sách tái sử dụng **riêng**; giới hạn inbound không thay thế giới hạn outbound.
- **Kết nối dữ liệu**: JDBC DataSource/HikariCP, Redis, message broker… Mỗi loại có pool hoặc cơ chế quản lý vòng đời riêng. Một kết nối HTTP không phải một kết nối JDBC.

Mở kết nối mới có chi phí TCP/TLS, xác thực và tài nguyên hệ điều hành. Pool giúp tái sử dụng kết nối nhưng phải có giới hạn. Nếu pool đầy, tác vụ mới **chờ** hoặc **timeout**; không tự động có kết nối vô hạn.

### 3.2. Một số nguyên tắc với JDBC/HikariCP

- Mượn kết nối **muộn nhất có thể**, hoàn trả **sớm nhất có thể**. Trong Spring Data/JPA, để framework quản lý tài nguyên và ranh giới transaction; khi tự dùng JDBC, bảo đảm đóng Connection/Statement/ResultSet đúng cách. Gọi close trên kết nối proxy của pool thường **trả nó về pool**, không hủy socket vật lý ngay.
- Không đặt lệnh gọi HTTP chậm hoặc thao tác chờ người dùng trong transaction DB dài nếu không cần: connection có thể bị giữ trong lúc chờ.
- Đặt timeout hợp lý cho **lấy kết nối**, **gọi mạng**, **truy vấn** và **transaction**; chúng là các giới hạn khác nhau.
- Tính ngân sách trên **toàn bộ replica**. Ví dụ 3 instance, mỗi instance tối đa 16 connection JDBC ⇒ có thể mở tới 48 kết nối từ dịch vụ này, chưa tính công cụ quản trị và dịch vụ khác. DB phải chịu được tổng đó.
- Khi Hikari báo thiếu connection, xem cả truy vấn chậm, transaction kéo dài, request đồng thời và leak trước khi tăng kích thước pool.

### 3.3. Triệu chứng cần phân biệt

**Inbound HTTP connection đầy**: client khó tạo kết nối, có thể timeout ngay từ phía proxy/web server. **Worker đầy**: kết nối đã được chấp nhận nhưng request chờ xử lý. **DB pool đầy**: request có worker nhưng bị kẹt chờ JDBC connection. Cả ba đều có thể biểu hiện thành API chậm; cần đo đúng lớp.

## 4. Luồng (threads): tài nguyên thực thi và chi phí chờ

### 4.1. Spring MVC/Servlet

Với ứng dụng Servlet truyền thống, embedded Tomcat dùng worker thread để thực thi request. Một request đồng bộ gọi JDBC hoặc REST blocking thường chiếm một worker trong phần thời gian chờ. Worker pool có giới hạn, hàng đợi có giới hạn hoặc cách xử lý riêng tùy connector, cấu hình và phiên bản. Tăng max threads có thể tăng mức đồng thời **chỉ khi CPU, DB, bộ nhớ và downstream còn dư năng lực**.

Đừng nhầm:
- **Số kết nối HTTP mở** với **số request đang được worker xử lý**: keep-alive có thể giữ nhiều kết nối đang rảnh.
- **Thread đang bận** với **CPU đang bận**: một thread bận có thể chỉ đang chờ socket/DB.
- **Thread pool request** với **executor @Async hoặc scheduler**: chúng có thể là các pool khác, có hàng đợi và giới hạn riêng.

### 4.2. Spring WebFlux/Reactor Netty

WebFlux trên Reactor Netty thường sử dụng số ít event-loop thread để phục vụ nhiều kết nối không chặn. Nếu chặn event loop bằng JDBC blocking, Thread.sleep, đọc file blocking dài hoặc tác vụ CPU nặng, nhiều request có thể cùng bị chậm. Với phần việc blocking bắt buộc, phải chuyển sang scheduler/executor phù hợp **và giới hạn mức đồng thời**; với luồng phản ứng, ưu tiên driver và thư viện non-blocking khi đó là kiến trúc đã chọn.

**Java 21 virtual threads** có thể giúp ứng dụng Servlet viết theo kiểu blocking xử lý nhiều tác vụ chờ hơn, nhưng không tăng năng lực DB, không thay thế timeout, pool, giới hạn kết nối hoặc ngân sách bộ nhớ. Các cấu hình Tomcat về platform worker thread có thể không còn hiệu lực khi virtual threads được bật; cần quan sát và kiểm chứng theo stack thực tế.

### 4.3. Một cách ước lượng tải

Dùng gần đúng của Little's Law khi hệ ổn định:

**Request đang xử lý trung bình ≈ số request/giây × thời gian xử lý trung bình (giây).**

Ví dụ 120 request/giây × 0,25 giây ≈ **30 request đồng thời đang xử lý**. Nếu downstream chậm thành 2 giây ở cùng tốc độ tới, con số tăng lên khoảng **240**. Đây **không** phải công thức đặt đúng 30 hoặc 240 thread: còn sự phân bố thời gian, request asynchronous, I/O, đỉnh lưu lượng, hàng đợi và mục tiêu độ trễ (đặc biệt p95/p99). Kết luận hữu ích là tăng latency làm tăng số công việc đồng thời cần giữ trong hệ thống.

## 5. Bộ nhớ (memory): heap chỉ là một phần

Một tiến trình Spring Boot/JVM tiêu thụ nhiều loại bộ nhớ:

| Vùng | Ví dụ | Điểm cần nhớ |
| --- | --- | --- |
| Java heap | DTO, entity, JSON, collection, session trong RAM, cache | GC thu hồi đối tượng không còn reachable; đối tượng còn được giữ tham chiếu sẽ không được thu hồi |
| Java thread stack | Stack frame và biến cục bộ của các luồng nền tảng | Nhiều platform thread làm tăng chi phí bộ nhớ ngoài heap |
| Metaspace, code cache và runtime native | Metadata class, JIT, JVM internals | Không nằm trong giới hạn -Xmx của heap |
| Direct/native buffer và networking | ByteBuffer direct, Netty/native I/O, TLS | Có thể tăng dù heap không đầy |
| Bộ nhớ dùng bởi container/process | Heap + native + stack + phần khác | Container có thể hết memory trước khi heap chạm ngưỡng |

Ví dụ -Xmx512m chỉ giới hạn **heap tối đa**; nó không có nghĩa toàn tiến trình chỉ dùng 512 MiB. Khi chạy trong container, dành ngân sách cho native, direct buffer, stack, metaspace, GC và phần dự phòng; theo dõi cả mức dùng của container lẫn JVM.

Các yếu tố làm memory tăng: đọc toàn bộ request/response lớn vào byte[], giữ toàn bộ kết quả SQL thay vì phân trang/stream, cache không giới hạn, session phình to, giữ reference trong static collection, tạo quá nhiều luồng, hoặc nhiều request đồng thời mỗi request giữ buffer lớn.

Ví dụ 200 request đồng thời, mỗi request giữ một byte[] cỡ 2 MiB sẽ chiếm xấp xỉ **400 MiB payload** chưa tính object overhead, bản sao, framework và các vùng nhớ khác. Đây là phép tính minh họa, không phải dự báo heap thực tế.

**Phân biệt lỗi**:
- Heap tăng rồi giảm theo chu kỳ GC có thể là hoạt động bình thường.
- Heap sau GC tiếp tục tăng nhiều chu kỳ có thể do giữ đối tượng, cache/session lớn hoặc leak; cần đo retained objects/heap dump để kết luận.
- CPU cao do GC hoặc allocation không giống CPU cao vì tính toán nghiệp vụ.
- Container bị OOMKilled khi heap chưa đầy có thể do native/direct/thread stack hoặc ngân sách container quá nhỏ.

Giảm rủi ro bằng phân trang, streaming, giới hạn kích thước body/upload, bounded queue/cache, quản lý vòng đời tài nguyên và đo allocation trước khi tăng RAM. Không dùng System.gc() làm cách xử lý gốc của memory leak.

## 6. Phiên (session): trạng thái trải qua nhiều request

HTTP tự thân không buộc server lưu trạng thái giữa các request. **Servlet HttpSession** được tạo khi ứng dụng yêu cầu; nó không bắt buộc tồn tại cho mọi request. Thông thường trình duyệt giữ cookie phiên (như JSESSIONID) chứa **định danh phiên**; dữ liệu phía server được lưu ở một session store phù hợp, không nằm toàn bộ trong cookie đó.

### 6.1. Vòng đời và kiến trúc

1. Ứng dụng tạo/tra cứu session khi cần thiết.
2. Những request sau mang session ID; server liên kết ID với state phía server.
3. Session hết hạn theo thời gian không hoạt động hoặc bị invalidate; dữ liệu/metadata liên quan cần được giải phóng theo chính sách store.
4. Với nhiều instance, session chỉ nằm trong memory cục bộ của một instance sẽ gặp vấn đề khi request được chuyển sang instance khác. Sticky session có thể giảm hiện tượng lệch node nhưng không thay thế cơ chế chia sẻ state hoặc phục hồi sau khi node mất; Spring Session có thể dùng store tập trung khi kiến trúc cần.

Nên lưu **tối thiểu**: ví dụ một số thông tin điều hướng ngắn hạn, không nhét toàn bộ entity graph, danh sách kết quả truy vấn lớn, đối tượng không serializable hoặc dữ liệu nhạy cảm không cần thiết vào session. Khi có thể, dịch vụ API stateless dùng cơ chế xác thực thích hợp và giữ state nghiệp vụ trong kho dữ liệu riêng.

### 6.2. Bảo mật và khả năng mở rộng

- Bật cookie HttpOnly và Secure trên HTTPS; chọn SameSite theo luồng xác thực thực tế; tái tạo/đổi ID phiên khi đăng nhập theo cơ chế bảo vệ chống session fixation.
- Hạn chế session timeout và số lượng dữ liệu lưu; định nghĩa hành vi logout/invalidate.
- Đừng coi session là cache chung cho mọi người dùng: phạm vi dữ liệu, thời hạn, số lượng bản sao và yêu cầu đồng bộ khác nhau.
- Redis session store cũng có kết nối, memory, latency và TTL riêng: chuyển state ra ngoài không làm chi phí biến mất.

## 7. Bộ đệm (buffer): xử lý theo khối để không giữ tất cả trong RAM

**Buffer** lưu tạm dữ liệu đang truyền hoặc xử lý; **cache** giữ kết quả để tái sử dụng trong những request sau. Hai cơ chế có mục đích khác nhau dù cùng dùng bộ nhớ.

Các vị trí thường có buffer: socket receive/send, Tomcat/Netty, request parsing, JSON serialization, JDBC fetch, bộ đọc tệp, nén response và reverse proxy. Có thể xảy ra **nhiều bản sao dữ liệu** giữa các lớp này. Không giả định framework luôn giữ toàn bộ body trong heap, cũng không giả định streaming ở một tầng có nghĩa mọi tầng đều stream.

### 7.1. Ví dụ Java 17+ chạy độc lập: sao chép dữ liệu qua buffer cố định

Tệp **BoundedCopyDemo.java**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

public class BoundedCopyDemo {
    public static void main(String[] args) throws IOException {
        byte[] payload = "Hello, runtime!".getBytes(StandardCharsets.UTF_8);

        try (var input = new ByteArrayInputStream(payload);
             var output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[4];
            int bytesRead;
            int totalBytes = 0;

            while ((bytesRead = input.read(buffer)) != -1) {
                output.write(buffer, 0, bytesRead);
                totalBytes += bytesRead;
            }

            System.out.println("Copied " + totalBytes + " bytes");
            System.out.println(output.toString(StandardCharsets.UTF_8));
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac BoundedCopyDemo.java
java BoundedCopyDemo
~~~

Kết quả chính xác:

~~~text
Copied 15 bytes
Hello, runtime!
~~~

**Giải thích:** buffer 4 byte được tái sử dụng qua nhiều lần đọc; dữ liệu cuối cùng vẫn đầy đủ, kể cả lượt đọc cuối ít hơn 4 byte. Đây là ví dụ nhỏ minh họa thuật toán. Vì ByteArrayOutputStream ở đây giữ **toàn bộ output trong RAM**, nó không phải ví dụ streaming tiết kiệm RAM cho dữ liệu lớn. Trong ứng dụng thực, nên đọc từ nguồn stream và ghi dần đến file hoặc response output stream, giữ giới hạn kích thước, xử lý lỗi và đóng tài nguyên đúng vòng đời.

### 7.2. Buffer, backpressure và cache

Nếu nơi nhận ghi chậm hơn nơi gửi đọc, dữ liệu sẽ tích lại: một queue hoặc buffer không giới hạn có thể chuyển lỗi chậm thành lỗi OOM. Các chiến lược gồm: giới hạn buffer/queue, tạm dừng đọc khi phía sau chưa sẵn sàng (backpressure), giới hạn số request đồng thời, timeout, từ chối tải vượt năng lực và stream kết quả thay vì gom toàn bộ vào collection.

Cache ứng dụng (ví dụ Spring Cache + Caffeine/Redis) nên có **giới hạn dung lượng, thời hạn lưu, khóa cache và chính sách invalidation**. Cache hit giảm số lần truy cập downstream nhưng cache lớn hoặc dữ liệu lỗi thời gây vấn đề mới. Trong Spring Boot, annotation @Cacheable chỉ có tác dụng khi caching được kích hoạt, có CacheManager/provider phù hợp và lời gọi đi qua cơ chế proxy/giải pháp cache tương ứng; việc tự gọi phương thức cùng bean theo mặc định có thể không đi qua advice.

## 8. Cấu hình tham khảo có kiểm soát

Ví dụ sau áp dụng cho **Spring Boot 3.x dùng Spring MVC, embedded Tomcat, JDBC với HikariCP và Actuator** (khi các dependency tương ứng có mặt). Đây là **giá trị minh họa**, không phải con số chuẩn cho mọi ứng dụng:

~~~yaml
server:
  tomcat:
    threads:
      max: 160
    max-connections: 3000
    mbeanregistry:
      enabled: true
  servlet:
    session:
      timeout: 20m

spring:
  datasource:
    hikari:
      maximum-pool-size: 16
      connection-timeout: 2000
  servlet:
    multipart:
      max-file-size: 10MB
      max-request-size: 12MB

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

- **server.tomcat.threads.max**: trần platform worker thread trong cấu hình Tomcat thông thường; không phải tổng số kết nối HTTP và có thể không áp dụng khi bật virtual threads.
- **server.tomcat.max-connections**: số kết nối mà Tomcat xử lý đồng thời; không nói lên bao nhiêu request đang thực thi Controller.
- **server.tomcat.mbeanregistry.enabled**: bật MBean registry để Spring Boot có thể thu thập nhóm Tomcat metrics tương ứng.
- **spring.datasource.hikari.maximum-pool-size**: tối đa connection vật lý của pool ở mỗi instance; phải cân đối với khả năng DB và số replica.
- **spring.datasource.hikari.connection-timeout**: thời gian tối đa chờ lấy connection từ pool, giá trị 2000 tương đương 2.000 ms trong cấu hình ví dụ.
- **server.servlet.session.timeout**: thời hạn session không hoạt động; không phải HTTP keep-alive timeout.
- **spring.servlet.multipart.***: đặt giới hạn phần upload multipart, nhưng chưa thay thế giới hạn tổng body tại proxy, gateway hoặc cơ chế nhận khác.
- **management.endpoints.web.exposure.include**: công bố các actuator endpoint được chọn; trong môi trường thật phải hạn chế truy cập tới endpoint quản trị bằng cấu hình mạng và bảo mật phù hợp.

Nếu dùng **WebFlux + Reactor Netty** hoặc không có JDBC, các thiết lập Tomcat/Hikari tương ứng không quản lý runtime đó. Hãy xác định đúng web stack, driver, provider và phiên bản trước khi chỉnh bất kỳ thuộc tính nào.

## 9. Đo lường và chẩn đoán trước khi tối ưu

Với dependency Spring Boot Actuator và tích hợp metrics phù hợp, có thể xem danh sách meter qua **GET /actuator/metrics** khi endpoint được expose. Ví dụ tên/nhóm metrics thường cần kiểm tra:

| Tín hiệu | Nên đọc cùng điều gì? | Gợi ý chẩn đoán |
| --- | --- | --- |
| http.server.requests, latency p95/p99 ở backend metrics | RPS, lỗi, route, dependency latency | Response chậm ở endpoint nào, tăng từ lúc nào? |
| tomcat.threads.busy hoặc Tomcat thread metrics khi MBean registry đã bật | Thread limit, queue, CPU | Bận vì CPU hay chờ downstream? |
| jdbc.connections.active và nhóm hikaricp.connections.* | Pool max/idle/pending, thời gian lấy connection | Query chậm, transaction dài hoặc pool thiếu? |
| jvm.memory.used / jvm.memory.max, GC metrics | Heap sau GC, allocation rate, container memory | Leak/retained object, burst hay thiếu RAM? |
| jvm.threads.live, thread dump | Thread state, stack trace, deadlock | Có nhiều thread bị chặn ở cùng một thao tác? |
| jvm.buffer.* và chỉ số OS/container | Direct buffer/native memory | Heap bình thường nhưng RSS hoặc container memory tăng? |
| Session/store, cache hit/miss/evictions do ứng dụng/provider ghi nhận | Số session, kích thước state, cache TTL | State/cache không giới hạn hoặc hit rate thấp? |

Tên meter cụ thể phụ thuộc Spring Boot, Micrometer, web stack, pool, tính năng đã bật và registry. **Hãy xem danh sách meter thật của ứng dụng** trước khi tạo dashboard; không mặc định mọi tên trong bảng đều có. /actuator/metrics là công cụ chẩn đoán; với giám sát lịch sử/cảnh báo nên xuất số liệu vào hệ thống metrics phù hợp và giữ endpoint quản trị khỏi public.

Quy trình tìm nút thắt:

1. **Khoanh vùng triệu chứng:** throughput (RPS), độ trễ p50/p95/p99, tỷ lệ lỗi/timeouts và thời điểm bắt đầu.
2. **Đọc ngân sách tài nguyên:** CPU, RSS/container memory, heap/GC, thread busy, connection inbound/outbound, DB pool active/pending, hàng đợi và downstream latency.
3. **Đối chiếu cùng thời điểm:** nếu DB pending tăng trước khi HTTP latency tăng, tìm hiểu transaction/DB; nếu GC tăng cùng heap retained, phân tích allocation hoặc cache; nếu event loop bị block, lấy thread dump/profiling.
4. **Thay đổi một nút có lý do:** giới hạn đồng thời, sửa truy vấn/chỗ giữ tài nguyên, thêm timeout, streaming hoặc tăng tài nguyên hợp lý. Sau đó load test và so sánh throughput, error rate, p95/p99.
5. **Theo dõi toàn hệ thống:** nhiều replica chia tải nhưng cộng dồn connection tới DB, session store, cache và downstream.

### Ba tình huống thực hành

**Tình huống A — API chậm nhưng CPU thấp.** Tomcat threads busy gần ngưỡng, Hikari pending nhiều, DB query latency cao. Khả năng cao worker đang chờ DB. Bắt đầu từ slow query, lock/transaction và connection lifetime; tăng thread count có thể chỉ làm queue ở DB lớn hơn.

**Tình huống B — Heap ổn nhưng container OOMKilled.** Xem RSS, số platform threads, direct buffer, native memory và kích thước container. Nâng -Xmx có thể làm thiếu phần RAM dành cho native nghiêm trọng hơn.

**Tình huống C — Tăng replica rồi phiên đăng nhập 'biến mất'.** Khi session lưu cục bộ, request của cùng client có thể tới instance khác. Kiểm tra session persistence/routing và yêu cầu state-sharing; đừng nhầm lỗi này với JSESSIONID tự bị xóa.

## 10. Checklist thiết kế runtime an toàn

- Xác định rõ **Servlet blocking hay WebFlux non-blocking**, server và client thư viện nào đang sử dụng; không áp dụng cấu hình của stack khác.
- Với mọi đường I/O: biết timeout ở đâu, connection được mượn/trả khi nào, giới hạn connection/queue và hành vi khi quá tải.
- Với thread/executor: biết ai tạo, max size, queue capacity, cách shutdown và cách xử lý tác vụ bị từ chối; tránh chặn event loop.
- Với memory: tính ngân sách cả heap lẫn native và container; giới hạn payload, cache, session, collection và request đồng thời.
- Với session: quyết định có thực sự cần state phía server không; đặt TTL, invalidate, cookie an toàn và chiến lược nhiều instance.
- Với buffer/cache: streaming cho dữ liệu lớn, giới hạn buffer/queue; với cache phải có eviction/TTL và quy tắc dữ liệu được phép lưu.
- Với vận hành: có metric, log, trace và load test trước/sau khi đổi giới hạn; kiểm thử trường hợp downstream chậm, mất kết nối và tải tăng đột biến.

**Ghi nhớ:** Runtime khỏe khi *mỗi tài nguyên có chủ sở hữu, vòng đời, giới hạn, tín hiệu đo lường và cách giải phóng rõ ràng*. Một request đi qua nhiều tài nguyên, nên nút thắt phải được xác định theo bằng chứng của cả chuỗi xử lý.

## Tài liệu tham khảo

- Spring Boot — Common Application Properties: https://docs.spring.io/spring-boot/appendix/application-properties/
- Spring Boot — Metrics and Actuator: https://docs.spring.io/spring-boot/reference/actuator/metrics.html
- Spring Boot — Caching: https://docs.spring.io/spring-boot/reference/io/caching.html

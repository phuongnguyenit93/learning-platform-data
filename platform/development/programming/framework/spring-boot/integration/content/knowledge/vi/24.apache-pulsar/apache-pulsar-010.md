# Xác thực, TLS và kiểm soát tài nguyên client

Trong Spring Boot, Apache Pulsar kết nối với ứng dụng qua `PulsarClient`, các producer/consumer được tạo bởi framework, `PulsarTemplate` và `@PulsarListener`. Một luồng tích hợp có thể chạy tốt trên môi trường phát triển nhưng thất bại ở production vì token hết hạn, chứng chỉ TLS sai hostname hoặc vì hàng đợi message tăng không giới hạn khi broker chậm.

Bài này xây dựng cách cấu hình và kiểm chứng **danh tính, đường truyền, phân quyền và ngân sách tài nguyên** của Pulsar Java client. Các ví dụ gắn với một dịch vụ Spring Boot nhận HTTP request tạo đơn hàng, ghi vào cơ sở dữ liệu và phát event `OrderCreated` tới topic `persistent://commerce/orders/order-created`; consumer khác xử lý event qua broker và có thể gọi HTTP hoặc DB phía sau. Mục tiêu là giữ đúng hợp đồng dữ liệu, giao dịch, xử lý trùng lặp và hành vi lỗi khi kết nối không ổn định.

## 1. Phân biệt TLS, authentication và authorization

| Lớp | Giải quyết vấn đề gì? | Cần xác minh |
| --- | --- | --- |
| **TLS** | Bảo mật kênh truyền giữa client với broker/proxy; xác minh server | CA, certificate chain, SAN/hostname, hạn chứng chỉ, protocol |
| **Authentication** | Xác định client/role là ai | Token, OAuth2 hoặc chứng chỉ client mTLS; hạn và cách refresh |
| **Authorization** | Role được làm gì trên tenant/namespace/topic | Quyền `produce`, `consume`, quyền quản trị được cấp riêng |

TLS không tự cấp quyền truy cập topic. Một token hợp lệ không thay thế việc kiểm tra chứng chỉ broker. Kết nối thành công đến service URL cũng không chứng minh role có thể gửi hoặc nhận ở mọi topic.

~~~mermaid
flowchart LR
    A[Spring Boot] --> B[TLS handshake và xác minh server]
    B --> C[Broker/proxy]
    C --> D[Authentication: xác định role]
    D --> E{Authorization}
    E -->|Đúng quyền| F[Produce / consume topic]
    E -->|Sai quyền| G[Từ chối thao tác]
~~~

Cluster phải bật TLS, provider xác thực và cơ chế phân quyền tương ứng; cấu hình riêng phía client không thể thay thế việc cấu hình broker. Với mô hình mTLS, broker còn phải tin CA của client và ánh xạ chứng chỉ client thành identity/role theo chính sách của cluster.

## 2. Endpoint Pulsar binary và Admin API

Pulsar binary protocol và REST Admin API là hai đường kết nối khác nhau:

| Thành phần | Service URL minh họa | Ghi chú |
| --- | --- | --- |
| Client binary không mã hóa | `pulsar://broker.example:6650` | Chỉ ở môi trường chủ động cho phép plaintext |
| Client binary có TLS | `pulsar+ssl://pulsar.example:6651` | Dùng cho producer/consumer tới broker hoặc proxy |
| Admin HTTP | `http://admin.example:8080` | REST admin không mã hóa |
| Admin HTTPS | `https://admin.example:8443` | REST admin được bảo vệ bằng TLS |

Các cổng `6650`, `6651`, `8080`, `8443` là giá trị thường gặp, không phải mặc định bắt buộc khi cluster dùng listener hoặc proxy tùy chỉnh. Không điền URL dạng `https://...` vào `spring.pulsar.client.service-url` hoặc dùng `pulsar+ssl://...` làm Admin URL.

Khi kết nối trực tiếp nhiều broker, client có thể lookup topic rồi đi tới địa chỉ broker được quảng bá (`advertisedListeners`). Cần đảm bảo cả endpoint ban đầu **và những broker sau lookup** có thể truy cập qua mạng, dùng đúng scheme/cổng và có tên DNS khớp SAN của server certificate. Với proxy hoặc load balancer, xác định TLS kết thúc ở đâu và đoạn kết nối tiếp có được mã hóa hay không.

**Quy tắc:** giữ `allowTlsInsecureConnection(false)` và bật hostname verification. Nếu certificate lỗi, phải sửa CA/trust store, DNS, SAN hoặc certificate đã hết hạn; không tắt kiểm tra để vượt qua lỗi.

## 3. Ví dụ Spring Boot: token authentication và TLS

Khi dùng Spring Boot starter tương thích với dự án, framework tự cấu hình `PulsarClient`, producer/consumer factory và các component tích hợp. Ví dụ Gradle:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-pulsar'
}
~~~

Cấu hình ứng dụng với token nhận từ secret manager hoặc biến môi trường:

~~~yaml
# application.yml - không chứa token thật
spring:
  pulsar:
    client:
      service-url: ${PULSAR_SERVICE_URL}
      authentication:
        plugin-class-name: org.apache.pulsar.client.impl.auth.AuthenticationToken
        param:
          token: ${PULSAR_AUTH_TOKEN}
      connection-timeout: 10s
      operation-timeout: 30s
      threads:
        io: 2
        listener: 4

app:
  pulsar:
    tls:
      ca-file: ${PULSAR_CA_FILE}
~~~

Ví dụ triển khai: `PULSAR_SERVICE_URL=pulsar+ssl://pulsar.internal.example:6651`, CA tại `/etc/pulsar/tls/ca.pem` và token được cấp cho role của service. Không commit token, private key hoặc mật khẩu vào Git, log hoặc container image. Không tự thêm tiền tố `Bearer ` nếu auth plugin không yêu cầu.

Các tên dưới `spring.pulsar.client.authentication.param.*` **phải khớp chính xác** tên mà plugin đòi hỏi. Spring Boot không thực hiện relaxed binding ở phần tên tham số này. Chẳng hạn plugin OAuth2 cần `issuerUrl`; `issuer-url` hay `issuerurl` không tương đương. Khi nhận giá trị từ biến môi trường, đặt tham chiếu trong `application.yml` theo đúng tên tham số thay vì trông cậy vào biến môi trường tự chuyển thành camelCase.

### 3.1. Thiết lập TLS qua `PulsarClientBuilderCustomizer`

Theo tài liệu Spring for Apache Pulsar, các cấu hình TLS chi tiết có thể cần thiết lập qua `PulsarClientBuilderCustomizer`; không giả định rằng phiên bản Spring Boot hiện tại có đầy đủ các property `spring.pulsar.client.tls.*`. Ví dụ dưới đây dùng Java client API `org.apache.pulsar.client.api` (API v4), là họ API thường được Spring Pulsar sử dụng:

~~~java
import org.apache.pulsar.client.api.SizeUnit;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.pulsar.core.PulsarClientBuilderCustomizer;

@Configuration
class PulsarClientConfig {
    @Bean
    PulsarClientBuilderCustomizer securePulsar(
            @Value("${app.pulsar.tls.ca-file}") String caFile) {
        return builder -> builder
                .tlsTrustCertsFilePath(caFile)
                .allowTlsInsecureConnection(false)
                .enableTlsHostnameVerification(true)
                .connectionsPerBroker(1)
                .memoryLimit(64, SizeUnit.MEGA_BYTES);
    }
}
~~~

`caFile` trỏ tới CA thực sự được mount trong pod với quyền đọc phù hợp. Nếu chứng chỉ đã được tin cậy thông qua trust store mặc định của JVM, đường dẫn CA riêng có thể không cần thiết tùy cách cấu hình, nhưng vẫn phải bật hostname verification. `connectionsPerBroker(1)` và `memoryLimit(64, SizeUnit.MEGA_BYTES)` là **giá trị khởi đầu để benchmark**, không phải các mức tối ưu chung.

API Java v5 thay đổi một số loại cấu hình tài nguyên (ví dụ cách biểu diễn giới hạn memory). Chỉ copy ví dụ này khi dự án đang dùng đúng phiên bản client API và Spring Pulsar tương thích; nếu chuyển sang v5, cần đối chiếu tài liệu v5.

### 3.2. Admin API cần cấu hình riêng

Spring Boot có thể auto-configure `PulsarAdministration`/`PulsarAdmin`. Nếu ứng dụng **thật sự cần** dùng Admin API, cấu hình URL và auth riêng:

~~~yaml
spring:
  pulsar:
    admin:
      service-url: ${PULSAR_ADMIN_URL}
      authentication:
        plugin-class-name: org.apache.pulsar.client.impl.auth.AuthenticationToken
        param:
          token: ${PULSAR_ADMIN_TOKEN}
~~~

`PULSAR_ADMIN_URL` có thể là `https://pulsar-admin.internal.example:8443`. Với CA nội bộ, Admin client cũng cần cấu hình TLS/trust/hostname phù hợp, thường qua `PulsarAdminBuilderCustomizer`. Client binary đã tin CA không tự chứng minh Admin client có trust configuration giống hệt. Role admin nên tách khỏi role producer/consumer; ở production có thể tạo topic, namespace và ACL bằng pipeline provisioning thay vì cho ứng dụng runtime quyền superuser.

## 4. Token, OAuth2 và mTLS: chọn cơ chế theo môi trường

| Cơ chế | Phương thức cấp danh tính | Các việc phải vận hành |
| --- | --- | --- |
| Token/JWT | Plugin `AuthenticationToken` nhận token đã được hệ thống cấp | Hạn token, issuer/audience nếu áp dụng, refresh, thu hồi |
| OAuth2 | `AuthenticationOAuth2` và các tham số như `issuerUrl`, `privateKey`, `audience` | Quyền lấy token, secret, connectivity tới identity provider |
| mTLS PEM | Chứng chỉ và private key của client, broker ánh xạ identity/role | CA hai chiều, private key, renewal và SAN |
| mTLS JKS | Keystore/truststore và TLS authentication plugin phù hợp | Mật khẩu, loại store, đường dẫn, vòng đời certificate |

Ví dụ cấu hình mTLS PEM trên client builder:

~~~java
import org.apache.pulsar.client.api.AuthenticationFactory;

// Một lựa chọn khác thay cho token authentication:
builder
    .authentication(AuthenticationFactory.TLS(
            "/etc/pulsar/tls/client.cert.pem",
            "/etc/pulsar/tls/client.key-pk8.pem"))
    .tlsTrustCertsFilePath("/etc/pulsar/tls/ca.pem")
    .allowTlsInsecureConnection(false)
    .enableTlsHostnameVerification(true);
~~~

Đừng ghép mTLS authentication với plugin token mà không hiểu cơ chế xác thực cuối cùng trên builder: hai đoạn code thể hiện **hai lựa chọn**. mTLS chỉ hoạt động nếu broker yêu cầu/chấp nhận client cert và có provider/role mapping tương ứng.

Bất kể plugin nào, cần có kiểm thử cả ba trường hợp: credential hợp lệ và được phép; credential không hợp lệ bị từ chối; credential hợp lệ nhưng **thiếu quyền topic** cũng bị từ chối.

## 5. Áp dụng quyền tối thiểu theo topic và vai trò

Trong hệ thống đơn hàng, có thể tách danh tính như sau:

| Service/actor | Phạm vi topic | Quyền cần thiết |
| --- | --- | --- |
| `order-api` | `persistent://commerce/orders/order-created` | `produce` |
| `order-projection` | Cùng topic | `consume` |
| `event-auditor` | Topic audit được cấp riêng | `consume` theo phạm vi audit |
| `infra-provisioner` | Namespace được quản lý | Quyền quản trị có kiểm soát, tránh cấp cho runtime |

Không cấp cùng một token superuser cho mọi service vì bất kỳ container bị chiếm quyền nào cũng có thể gây ảnh hưởng trên toàn cluster. Nếu một ứng dụng cần cả producer và consumer với quyền tách biệt nghiêm ngặt, cân nhắc hai identity/client riêng hoặc tách tiến trình theo ranh giới quyền.

Việc broker cho phép `consume` cũng không có nghĩa nội dung event đáng tin tuyệt đối. Consumer vẫn phải xác minh schema, tenant, version, event ID, các trường dữ liệu nghiệp vụ và quyền truy cập hệ thống đích. Tránh đưa password, access token và dữ liệu cá nhân không cần thiết vào payload hoặc message properties. Dữ liệu nhạy cảm đặc biệt có thể cần mã hóa payload độc lập với TLS vận chuyển.

## 6. Xoay vòng secret và chứng chỉ

Một chính sách bảo mật có ích khi được vận hành liên tục:

1. **Cấp secret:** sử dụng secret manager hoặc Kubernetes Secret, mount certificate/key dưới dạng file chỉ đọc; phân quyền người và workload theo mức tối thiểu.
2. **Phân tách môi trường:** role/token production không tái sử dụng ở development/staging.
3. **Hạn dùng:** theo dõi expiry token, certificate; có cảnh báo trước hạn và người chịu trách nhiệm rotation.
4. **Cập nhật credential:** file được thay trên disk không đảm bảo client/plugin tự nạp ngay. Phải xác minh plugin có hỗ trợ refresh hay cần rolling restart/recreate client.
5. **Đổi CA:** có giai đoạn tin cậy chồng lấp khi cần, kiểm tra các hostname broker/proxy trước khi gỡ CA cũ.
6. **Giảm lộ thông tin:** không log raw Spring Environment, authentication config, token, private key hoặc URL chứa credential; bảo vệ endpoint Actuator/config.

Một quy trình có thể kiểm thử: cấp token mới → cập nhật nguồn secret → rollout replica từng phần hoặc refresh qua plugin → kiểm tra produce/consume → thu hồi token cũ. Khi cần downtime bằng 0, phải xác nhận khả năng refresh và retry client trong chính version đang triển khai.

## 7. `PulsarClient` là tài nguyên dùng chung có vòng đời

`PulsarClient` quản lý network I/O, thread, lookup, connection và memory buffers. Tạo client mới ở **mỗi HTTP request, mỗi lần gửi event hoặc mỗi lần nhận message** sẽ làm tăng số socket, thread và memory theo lượng truy cập.

~~~mermaid
flowchart TD
    A[Spring Boot ApplicationContext] --> B[PulsarClient quản lý theo cluster / identity]
    B --> C[ProducerFactory / PulsarTemplate]
    B --> D[ConsumerFactory / PulsarListener]
    C --> E[Pending producer messages]
    D --> F[Prefetch / consumer xử lý]
    E --> G[Broker]
    F --> G
~~~

Ưu tiên dùng `PulsarClient` được Spring Boot auto-configure và factory/cache producer do Spring Pulsar quản lý. Khi cần nhiều cluster hoặc credential khác nhau, có thể tạo nhiều client có chủ đích nhưng phải cộng tổng chi phí tài nguyên của tất cả client trong cùng pod. Nếu tự tạo client thủ công, chịu trách nhiệm đóng producer, consumer và client khi shutdown; không tự đóng bean Spring quản lý sau mỗi request.

### 7.1. Các tham số quan trọng

| Tham số | Ảnh hưởng | Rủi ro khi cấu hình |
| --- | --- | --- |
| `ioThreads` | Thread quản lý kết nối và network I/O | Ít quá nghẽn event loop; nhiều quá tốn CPU |
| `listenerThreads` | Thread chạy callback/listener của Pulsar client | Callback chậm có thể chiếm thread; nhiều quá tốn tài nguyên |
| `connectionsPerBroker` | Số kết nối từ client tới mỗi broker | Nhiều quá tăng socket và chi phí broker; ít quá có thể hạn throughput |
| `memoryLimit` (API v4) | Ngân sách memory buffer được Pulsar client quản lý | Không giới hạn/đặt quá cao có thể tạo memory pressure |
| `connectionTimeout` | Thời gian chờ mở connection | Quá dài khiến lỗi network xuất hiện muộn |
| `operationTimeout` | Giới hạn thời gian cho thao tác client | Quá ngắn gây timeout giả; quá dài giữ request chờ |
| Client/producer/consumer count | Tổng connection, queue, callback, subscription | Dễ nhân theo replica, topic và partition |

`memoryLimit` không phải giới hạn tổng **JVM RSS, heap, direct memory**. Application object, JSON serialization, callback queue, Netty buffer và bộ nhớ của luồng nghiệp vụ có thể nằm ngoài phần accounting của Pulsar client. Với Java client API v5, cú pháp và cơ chế giới hạn pending sends khác API v4; cần dùng đúng tài liệu theo phiên bản.

Đặt `ioThreads(2)`, `listenerThreads(4)` và `connectionsPerBroker(1)` chỉ là một điểm xuất phát. Kiểm tra CPU, socket count, latency, throughput, memory và broker load trước khi tăng.

## 8. Backpressure ở producer khi broker chậm

Producer thường gửi bất đồng bộ để tránh chặn HTTP thread. Tuy nhiên, nếu số `sendAsync()` mới lớn hơn tốc độ broker xác nhận, số message pending tăng đến khi hết buffer hoặc memory.

Với client API v4, có thể đặt giới hạn message pending ngay tại producer:

~~~java
import java.util.concurrent.TimeUnit;
import org.apache.pulsar.client.api.Producer;
import org.apache.pulsar.client.api.Schema;

// client là PulsarClient được tạo/quản lý theo vòng đời ứng dụng.
Producer<String> producer = client.newProducer(Schema.STRING)
        .topic("persistent://commerce/orders/order-created")
        .maxPendingMessages(1_000)
        .blockIfQueueFull(false)
        .enableBatching(true)
        .batchingMaxPublishDelay(10, TimeUnit.MILLISECONDS)
        .create();
~~~

Với `blockIfQueueFull(false)`, ứng dụng nhận lỗi khi không thể đưa thêm message vào queue và phải có hành vi tương ứng, ví dụ retry qua outbox. Với `true`, caller có thể chờ có chỗ trống, nhưng nguy cơ chặn thread quan trọng. Các mặc định và giới hạn pending queue giữa Java API v4/v5 khác nhau, đặc biệt đối với partitioned producer; không giả định giá trị cụ thể của mọi version.

~~~java
producer.newMessage()
        .key(orderId)
        .property("eventId", eventId)
        .value(eventJson)
        .sendAsync()
        .whenComplete((messageId, error) -> {
            if (error != null) {
                // Ghi nhận publish failure; giữ outbox record để retry.
            } else {
                // Acknowledgment của Pulsar: cho phép cập nhật trạng thái outbox.
            }
        });
~~~

Ví dụ trên minh họa cách xử lý completion; thành phần production cần semaphore/bounded work queue và xử lý exception thích hợp. Nếu hàng nghìn request xếp `sendAsync` trước khi callback hoàn tất, cần **giới hạn in-flight ở tầng ứng dụng**, không chỉ trông cậy producer pending queue.

**Không suy ra “timeout nghĩa là broker chưa ghi message”.** Broker có thể đã ghi nhưng ack thất lạc. Một lần retry có thể tạo bản sao; event ID ổn định, outbox và idempotent consumer giúp xử lý kết quả chưa xác định. Tính năng broker deduplication nếu bật cũng cần hiểu phạm vi và cấu hình, không thay thế mọi kiểm tra nghiệp vụ.

Batching có thể tăng throughput nhưng thêm thời gian chờ. Nếu consumer dùng subscription `Key_Shared` để xử lý theo key, kiểm chứng producer có dùng **key-based batching** hoặc tắt batching khi cần; batching thông thường có thể ảnh hưởng phân phối theo key. Compression tiết kiệm băng thông nhưng thêm CPU; đo bằng payload thật.

## 9. Kiểm soát consumer: prefetch, concurrency và acknowledgment

Pulsar consumer prefetch message nhằm giảm round trip; khi nhân số partition, consumer và replica, buffer nhận có thể chiếm bộ nhớ lớn. `receiverQueueSize` của API v4 điều chỉnh lượng message được prefetch; các giới hạn tổng cho partitioned consumer tùy phiên bản cũng cần xét.

~~~java
import org.apache.pulsar.client.api.Consumer;
import org.apache.pulsar.client.api.Schema;
import org.apache.pulsar.client.api.SubscriptionType;

Consumer<String> consumer = client.newConsumer(Schema.STRING)
        .topic("persistent://commerce/orders/order-created")
        .subscriptionName("order-projection")
        .subscriptionType(SubscriptionType.Key_Shared)
        .receiverQueueSize(200)
        .subscribe();
~~~

Đây là ví dụ Java client; trong Spring Boot thường dùng `@PulsarListener` với `ConsumerFactory` và các `ConsumerBuilderCustomizer` hoặc property `spring.pulsar.consumer.*`, `spring.pulsar.listener.*`. Không tạo consumer thủ công trong mỗi lần listener chạy.

Ước tính bộ nhớ tiếp nhận cần tính số replica × số receiver/partition × message prefetched × kích thước payload, cộng overhead batch/deserialize. Đây chỉ là mô hình ước lượng vì cách phân phối và giới hạn nội bộ thay đổi theo phiên bản. Concurrency listener cao không đồng nghĩa xử lý nhanh nếu DB pool hoặc HTTP downstream đã đầy.

- **Ack sau khi xử lý thành công:** transaction DB phải hoàn tất trước khi coi message đã được xử lý theo hợp đồng. Thiết lập ack mode/container phù hợp.
- **At-least-once và redelivery:** khi consumer crash hoặc ack thất bại, event có thể xuất hiện lại; dùng idempotency key, unique constraint hoặc version trong DB.
- **Retry có giới hạn:** phân biệt lỗi tạm thời như DB timeout với lỗi payload/schema không thể phục hồi; dùng backoff và DLQ để ngăn poison message chiếm subscription.
- **Ordering:** `Shared` không bảo đảm thứ tự toàn cục; `Key_Shared` có điều kiện riêng về key và batching. Không xây dựng invariant nghiệp vụ trên một bảo đảm ordering chưa được kiểm chứng.
- **Tốc độ nhận:** nếu DB/HTTP downstream chậm, giảm concurrency/prefetch hoặc áp dụng bulkhead thay vì mở rộng song song không giới hạn.

## 10. Ranh giới transaction, retry và idempotency

Trong mô hình HTTP → DB → Pulsar, ghi DB thành công nhưng publish thất bại là tình huống có thật. Một Pulsar transaction không mặc nhiên bao gồm transaction của cơ sở dữ liệu quan hệ. Với yêu cầu “đơn hàng commit thì event cuối cùng phải xuất hiện”, có thể áp dụng **transactional outbox**:

~~~mermaid
flowchart LR
    A[HTTP tạo đơn] --> B[Transaction DB]
    B --> C[Ghi order và outbox record]
    C --> D[Commit]
    D --> E[Outbox publisher]
    E --> F[Producer gửi Pulsar]
    F --> G[Consumer]
    G --> H[DB commit và ack]
~~~

Publisher độc lập đọc outbox, gọi Pulsar producer và chỉ đánh dấu đã gửi khi có acknowledgment phù hợp. Khi publish timeout, retry với cùng event ID và giả định **có thể gửi trùng**. Consumer lưu event ID đã xử lý hoặc dùng business version cùng transaction DB để chống side effect lặp lại.

Nếu bảo mật client gặp lỗi (certificate, token, ACL), không tăng retry vô hạn hoặc tự chuyển sang connection plaintext; phát cảnh báo và giữ outbox record đến khi sự cố được xử lý. Với telemetry ít quan trọng, ứng dụng có thể có chính sách drop có ghi metric; với event giao dịch, không được âm thầm drop. Chính sách lỗi phải theo hợp đồng nghiệp vụ.

Khi một Spring Integration flow hoặc adapter bọc việc gửi/nhận Pulsar, cần ghi rõ retry diễn ra ở tầng adapter, broker hay HTTP/DB, vì retry của một tầng có thể làm thao tác của tầng khác lặp lại.

## 11. Chẩn đoán sự cố có hệ thống

| Biểu hiện | Nguyên nhân cần kiểm chứng | Hướng xử lý |
| --- | --- | --- |
| TLS handshake failed | CA không đúng, hostname/SAN sai, cert hết hạn | Kiểm chứng trust chain, DNS, advertised broker, thời gian hệ thống |
| Authentication failed | Token sai/hết hạn, auth plugin sai tham số, mTLS role mapping lỗi | Xác minh nguồn secret, plugin, token refresh/certificate |
| Authorization denied | Role thiếu quyền topic/namespace | Cấp đúng `produce`/`consume`, không mở superuser |
| Chỉ Admin API lỗi | URL `https://`, Admin token hoặc trust config riêng | Kiểm tra `spring.pulsar.admin.*` và customizer |
| Kết nối được nhưng publish chậm | Broker quá tải, pending queue, network, batching | Đo p95/p99, queue depth, timeout và resource pressure |
| Consumer backlog tăng | DB/HTTP chậm, quá nhiều retry, concurrency không phù hợp | Đo process time, DLQ, giảm prefetch, giới hạn downstream |
| JVM memory tăng | Producer pending, receiver queue, direct buffer, object retention | Đo heap/direct memory, kiểm tra budget client và callback |
| Sau rollout mới mất kết nối | CA, token, DNS, permission hoặc version thay đổi | So sánh cấu hình/credential của rollout và test đầy đủ |

Phân biệt lỗi HTTP `401`/`403` ở Admin REST với exception của Pulsar binary protocol; không tự quy đổi mọi lỗi binary thành mã HTTP. Khi TLS/auth/ACL thất bại, ưu tiên sửa cấu hình/danh tính trước khi điều chỉnh retry.

## 12. Quan sát và bảo vệ dữ liệu nhạy cảm

Các metric và log nên trả lời đồng thời: “client có xác thực được không?”, “broker có theo kịp tốc độ gửi/nhận không?” và “sự kiện nghiệp vụ đã được xử lý đúng chưa?”.

| Tín hiệu | Ví dụ đo lường | Ý nghĩa |
| --- | --- | --- |
| Security | TLS/auth failure, authorization denial, token expiry | Phát hiện lỗi danh tính/đường truyền |
| Producer | Publish rate, send latency, error/timeout, pending messages | Phát hiện backpressure, mất ack |
| Consumer | Ack rate, backlog, redelivery, DLQ, process latency | Phát hiện hệ thống đích quá tải hoặc poison messages |
| JVM và broker | CPU, heap/direct memory, thread, socket, broker connections | Kiểm tra ngân sách tài nguyên |
| Nghiệp vụ | Outbox pending age, delivery lag, số event trùng đã chặn | Quan sát độ đúng và độ trễ của integration |

Micrometer/Actuator, tracing và metric Pulsar client/broker phụ thuộc cách triển khai; cần xác minh metric thực sự đã bật trên phiên bản đang dùng. Log nên ghi service, môi trường, topic, subscription, correlation ID, event ID và loại lỗi, nhưng **không** ghi token, secret, private key hoặc raw payload nhạy cảm. Không đặt event ID, user ID hay message ID làm metric tag cardinality cao.

Cảnh báo nên gồm: auth failure tăng sau rollout, certificate sắp hết hạn, pending producer queue cao kéo dài, memory áp sát quota, outbox không được publish, DLQ bất thường và consumer backlog tăng cùng lúc DB latency xấu đi.

## 13. Kịch bản kiểm thử trước production

Test với broker plaintext không bật auth chỉ xác minh logic cơ bản, không chứng minh kết nối TLS/auth/ACL production hoạt động. Cần môi trường tích hợp có TLS, token/mTLS, role và topic ACL đại diện cho cụm thật.

| Kịch bản | Cách tạo tình huống | Kỳ vọng |
| --- | --- | --- |
| Role hợp lệ | CA đúng, token/cert đúng, topic được cấp quyền | Produce/consume thành công |
| CA hoặc hostname sai | Dùng CA khác hoặc hostname không nằm trong SAN | Handshake bị từ chối, không fallback plaintext |
| Token hết hạn/thu hồi | Xoay token hoặc cung cấp credential hết hạn | Lỗi xác thực rõ ràng, có alert |
| Role thiếu `produce` | Consumer identity thử publish | Broker từ chối |
| Role thiếu `consume` | Producer identity thử subscribe | Broker từ chối |
| Admin role không hợp lệ | Role runtime thử tạo topic | Admin operation bị từ chối |
| Broker chậm/ngắt mạng | Throttle, drop kết nối, nhiều send đồng thời | Pending queue, memory và retry nằm trong giới hạn |
| Consumer xử lý chậm | DB/HTTP downstream chậm, nhiều partition | Backlog và latency được đo, không cạn tài nguyên pod |
| Ack bị mất | Broker đã nhận nhưng caller timeout | Có thể retry, consumer chặn event trùng |
| Poison message | Gửi payload/schema sai lặp lại | Retry hữu hạn, đưa DLQ/ghi cảnh báo |
| Credential rotation | Đổi CA hoặc token khi replica đang chạy | Có quy trình refresh/rolling restart được kiểm chứng |

Test tải cần đo CPU, số socket/thread, heap và direct memory, message throughput, p95/p99 publish latency, consumer backlog và business lag theo số replica. Không dùng test chỉ gọi `@PulsarListener` một lần để kết luận cấu hình đã chịu được broker outage.

## 14. Checklist triển khai cho đội phát triển và vận hành

- [ ] Service URL đúng loại (`pulsar+ssl://` cho binary, `https://` cho admin) và đúng port/listener.
- [ ] Trust chain và hostname verification hoạt động cả ở endpoint ban đầu lẫn broker lookup.
- [ ] Token/mTLS/OAuth2 thuộc đúng môi trường, đúng plugin parameters, có kế hoạch rotation.
- [ ] Role producer/consumer/admin có quyền tối thiểu theo tenant, namespace và topic.
- [ ] `PulsarClient` được tái sử dụng theo vòng đời Spring; số client/connection/thread được đo.
- [ ] Memory, pending producer sends và receiver queue có giới hạn tương ứng với số replica/partition.
- [ ] Consumer ack, redelivery, DLQ và idempotency thống nhất với transaction DB.
- [ ] Khi broker hoặc credential lỗi, event quan trọng được giữ trong outbox; không tự hạ TLS.
- [ ] Đã có metric, cảnh báo và kiểm thử lỗi TLS, auth, ACL, broker outage, resource exhaustion.

**Kết luận:** bảo mật và kiểm soát tài nguyên của Pulsar client là một phần hợp đồng tích hợp, không đơn thuần là cấu hình kết nối. TLS bảo vệ và xác minh endpoint; authentication/authorization giới hạn danh tính và quyền; ngân sách connection, thread, queue, memory cùng outbox/idempotency giúp Spring Boot giữ hành vi xác định khi broker chậm, mất kết nối hoặc giao dịch phải retry.

### Tài liệu tham khảo

- [Spring Boot — Apache Pulsar Support](https://docs.spring.io/spring-boot/reference/messaging/pulsar.html): starter, auto-configuration, client/admin, producer/consumer.
- [Spring for Apache Pulsar — Pulsar Client](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/pulsar-client.html): TLS, auth plugins, token/OAuth2/mTLS, customizer.
- [Apache Pulsar — Set up Java client](https://pulsar.apache.org/docs/client-libraries/java-setup/): client API, memory budget, pending producer queue, version differences.

Ví dụ sử dụng API Java client v4; khi áp dụng thực tế phải đối chiếu đúng phiên bản Spring Boot, Spring Pulsar và Pulsar Java client được quản lý trong dự án, đặc biệt với các knob thay đổi ở API v5.

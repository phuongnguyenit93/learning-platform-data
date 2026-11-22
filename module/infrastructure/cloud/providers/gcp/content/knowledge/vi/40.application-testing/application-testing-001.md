# Chiến lược unit, integration và end-to-end cho dịch vụ GCP

Một dịch vụ chạy trên Google Cloud có thể nhận request qua Cloud Run hoặc Google Kubernetes Engine (GKE), ghi dữ liệu vào Cloud SQL, tải object lên Cloud Storage và phát sự kiện qua Pub/Sub. Nếu chỉ kiểm tra rằng một phương thức Java trả về giá trị đúng, nhóm chưa biết IAM, mạng, cơ sở dữ liệu hay hàng đợi có hoạt động cùng nhau hay không. Ngược lại, nếu mọi kiểm thử đều triển khai lên GCP, thời gian chạy, chi phí và mức độ phụ thuộc vào môi trường sẽ tăng cao.

Chiến lược kiểm thử hiệu quả cần phân chia trách nhiệm giữa **unit test**, **integration test** và **end-to-end (E2E) test**. Unit test kiểm tra quyết định và quy tắc nghiệp vụ, integration test kiểm tra ranh giới kết nối giữa các thành phần, còn E2E test xác nhận luồng người dùng trên một hệ thống đã triển khai thực tế.

Bài học này xây dựng chiến lược kiểm thử cho dịch vụ GCP, với ví dụ Java/Spring Boot, Cloud Run, GKE, Cloud SQL, Pub/Sub, Cloud Storage và CI/CD. Trọng tâm là kiểm thử đúng mức, cô lập dữ liệu, tránh kiểm thử không ổn định và dùng kết quả để quyết định một bản phát hành có đủ tin cậy hay không.

## 1. Hiểu ba cấp kiểm thử

Ba cấp kiểm thử trả lời những câu hỏi khác nhau:

| Cấp | Câu hỏi chính | Tài nguyên cần dùng | Đặc tính |
|---|---|---|---|
| Unit | Logic của một đơn vị có đúng với đầu vào đã cho? | Process test, mock/fake và dữ liệu trong bộ nhớ | Nhanh, xác định, chạy liên tục |
| Integration | Hai hoặc nhiều thành phần có tương tác đúng không? | Database/container, emulator hoặc dịch vụ GCP thật | Chậm hơn, kiểm tra contract và cấu hình kết nối |
| E2E | Một hành trình nghiệp vụ có chạy trọn vẹn trên hệ thống triển khai không? | API, identity, network, runtime và dependency gần production | Chi phí cao hơn, dễ bị ảnh hưởng môi trường |

Chẳng hạn với hành trình đặt đơn hàng:

- Unit test: tổng tiền không âm, không thể xác nhận đơn đã hủy, retry phải tuân thủ idempotency key.
- Integration test: repository ghi/đọc Cloud SQL đúng schema; publisher tạo Pub/Sub message có payload và attributes hợp lệ.
- E2E test: gọi API tạo đơn trên Cloud Run, xác minh đơn được lưu, sự kiện được xử lý và trạng thái đơn chuyển sang `CONFIRMED`.

~~~mermaid
flowchart TD
    A[Source change] --> B[Unit tests]
    B --> C[Component and integration tests]
    C --> D[Build immutable artifact]
    D --> E[Deploy isolated staging]
    E --> F[E2E critical journeys]
    F --> G{Quality gates passed?}
    G -->|Yes| H[Release approval or promotion]
    G -->|No| I[Inspect failure and fix]
    I --> A
~~~

**Số lượng test không phải là mục tiêu cuối cùng.** Một tập test ngắn nhưng bảo vệ các rủi ro nghiệp vụ quan trọng có thể giá trị hơn hàng nghìn test chỉ lặp lại cấu trúc mã nguồn. Chọn cấp thấp nhất có thể phát hiện lỗi một cách đáng tin cậy; dùng cấp cao hơn để kiểm chứng ranh giới mà cấp thấp không thể chứng minh.

## 2. Thiết kế chiến lược dựa trên rủi ro

Trước khi viết test, liệt kê các hành vi có thể gây tổn thất khi sai: xử lý thanh toán hai lần, mất message, cấp quyền quá rộng, ghi dữ liệu vào project production hoặc không phục hồi được sau timeout.

Một ma trận phù hợp cho dịch vụ GCP:

| Rủi ro | Unit | Integration | E2E |
|---|---|---|---|
| Tính tiền sai | Kiểm tra quy tắc và làm tròn | Kiểm tra mapping kiểu dữ liệu DB | Kiểm tra một đơn hàng hoàn chỉnh |
| Gửi message trùng | Kiểm tra quyết định idempotency | Kiểm tra retry, ack/nack và consumer | Gửi cùng request hai lần, xác minh một tác động nghiệp vụ |
| Schema database sai | Kiểm tra mapper thuần | Chạy migrations với PostgreSQL thật | Kiểm tra API sau deploy với schema staging |
| Thiếu IAM | Mock mô phỏng lỗi để kiểm tra ứng xử | Gọi API trong sandbox với principal thật | Kiểm tra workload identity thực tế tại staging |
| Sai cấu hình mạng | Không cần ở unit | Kiểm tra kết nối giữa service và dependency | Kiểm tra hành trình xuyên VPC/ingress/runtime |
| API không tương thích | Kiểm tra serialization/validation | Contract test consumer/provider | Smoke test giao tiếp giữa service đã deploy |
| Latency vượt SLO | Kiểm tra timeout logic | Kiểm tra timeout/retry với fault control | Đo hành trình và tín hiệu vận hành thực tế |

Gắn mỗi rủi ro với một **assertion có ý nghĩa** và một người chịu trách nhiệm. Không bắt mọi test kiểm tra toàn bộ hành vi. Ví dụ, unit test không cần kiểm tra IAM của Cloud Storage, vì mock không thực thi IAM thật.

### Kim tự tháp kiểm thử

Thường nên có nhiều unit test, ít integration test hơn và một tập E2E ngắn, tập trung các hành trình quan trọng. Đây là nguyên tắc thiết kế, không phải tỷ lệ số lượng bắt buộc.

- Unit test chạy khi developer sửa code và trên mọi pull request.
- Integration test chạy trên pull request hoặc trước khi merge, tùy chi phí và khả năng chạy container/emulator.
- E2E smoke test chạy sau deploy staging và trước khi promote production.
- Full E2E, performance và fault-injection test có thể chạy định kỳ hoặc theo thay đổi rủi ro cao.

## 3. Tạo ranh giới rõ ràng để dễ kiểm thử

Dịch vụ Java/Spring nên tách nghiệp vụ khỏi adapter gọi Google Cloud. Controller xử lý HTTP, application service điều phối nghiệp vụ, repository hoặc gateway chịu trách nhiệm làm việc với Cloud SQL, Pub/Sub và Cloud Storage.

~~~mermaid
flowchart LR
    A[HTTP Controller] --> B[Application Service]
    B --> C[Domain Rules]
    B --> D[OrderRepository interface]
    B --> E[EventPublisher interface]
    D --> F[Cloud SQL adapter]
    E --> G[Pub/Sub adapter]
    B --> H[AttachmentStore interface]
    H --> I[Cloud Storage adapter]
~~~

Ví dụ một interface dùng để tách phần quyết định khỏi SDK:

~~~java
public interface AttachmentStore {
    boolean exists(String objectName);
}

public final class AttachmentService {
    private final AttachmentStore store;

    public AttachmentService(AttachmentStore store) {
        this.store = store;
    }

    public String status(String objectName) {
        if (objectName == null || objectName.isBlank()) {
            throw new IllegalArgumentException("Object name is required");
        }
        return store.exists(objectName) ? "READY" : "MISSING";
    }
}
~~~

Adapter production dùng Google Cloud Storage client; unit test có thể dùng mock của `AttachmentStore`.

Các đường ranh giới dễ kiểm thử còn bao gồm:

- Đưa `Clock` vào code xử lý thời hạn và TTL, thay vì gọi `Instant.now()` ở khắp nơi.
- Đưa UUID generator hoặc interface cung cấp ID vào phần code cần kết quả xác định.
- Đưa cấu hình retry và timeout ra cấu hình riêng có thể thay thế trong test.
- Chỉ tạo Google Cloud clients tại lớp cấu hình hoặc adapter; tránh khởi tạo client trong mỗi phương thức nghiệp vụ.
- Xử lý Pub/Sub message qua một handler thuần trước khi kết nối với subscriber.
- Phân biệt quyết định nghiệp vụ với bước side effect; mô hình outbox khi cần đảm bảo dữ liệu DB và sự kiện nhất quán.

Không nên mock mọi dòng code. Mock là phương tiện kiểm soát ranh giới bên ngoài, còn domain rules nên được chạy thật trong test.

## 4. Unit test với JUnit 5 và Mockito

Unit test nên chạy nhanh, không phụ thuộc mạng, ADC, GCP project hay tài nguyên dùng chung. Một unit test tốt có dữ liệu đầu vào rõ ràng và kết quả không thay đổi theo thời gian chạy.

Ví dụ kiểm thử `AttachmentService`:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;

class AttachmentServiceTest {
    @Test
    void returnsMissingWhenObjectDoesNotExist() {
        AttachmentStore store = mock(AttachmentStore.class);
        when(store.exists("orders/42.pdf")).thenReturn(false);

        AttachmentService service = new AttachmentService(store);

        assertEquals("MISSING", service.status("orders/42.pdf"));
        verify(store).exists("orders/42.pdf");
        verifyNoMoreInteractions(store);
    }

    @Test
    void rejectsBlankObjectNameWithoutCloudCall() {
        AttachmentStore store = mock(AttachmentStore.class);
        AttachmentService service = new AttachmentService(store);

        assertThrows(IllegalArgumentException.class,
                () -> service.status("  "));
        verifyNoInteractions(store);
    }
}
~~~

Các test trên kiểm tra được hai điều: kết quả nghiệp vụ và việc chương trình không gọi adapter khi đầu vào sai. Chúng không cần Cloud Storage bucket thật.

Nên ưu tiên assertion về hành vi hoặc trạng thái quan sát được. Việc kiểm tra số lần một phương thức nội bộ được gọi chỉ có ích khi số lần đó liên quan đến yêu cầu, ví dụ chống ghi trùng hoặc chống gọi API không cần thiết.

### Parameterized tests

Với nhiều biến thể đầu vào, có thể dùng JUnit 5 parameterized test:

~~~java
@ParameterizedTest
@ValueSource(strings = {"", " ", "\t"})
void rejectsInvalidNames(String name) {
    AttachmentService service = new AttachmentService(object -> true);

    assertThrows(IllegalArgumentException.class,
            () -> service.status(name));
}
~~~

Ví dụ này kiểm tra cả dữ liệu rỗng lẫn khoảng trắng. Khi code có nhiều trường hợp biên, parameterized test dễ đọc hơn các test trùng lặp.

### Kiểm thử logic retry và idempotency

Một adapter gọi Pub/Sub hoặc Cloud Storage cần phân loại lỗi: timeout hoặc lỗi tạm thời có thể retry, trong khi lỗi phân quyền hoặc request không hợp lệ thường không nên retry vô hạn. Với unit test, giả lập lỗi và dùng clock/scheduler có kiểm soát để kiểm tra:

- Số lần thử tối đa và thời gian chờ.
- Exponential backoff và jitter trong giới hạn.
- Dừng retry với lỗi không thể khắc phục.
- Không tạo bản ghi hoặc sự kiện trùng khi cùng idempotency key xuất hiện.
- Không để retry vượt thời hạn request tổng thể.

Tránh `Thread.sleep()` trong unit test để chờ scheduler. Dùng fake clock, fake scheduler hoặc component cho phép điều khiển thời gian.

## 5. Test Spring MVC và HTTP boundary

Một Spring controller còn phải kiểm tra status code, validation, JSON serialization, error response và security filter. Có thể dùng `@WebMvcTest` cho HTTP slice test mà không khởi động toàn bộ application context và không kết nối GCP.

Ví dụ cấu trúc:

~~~java
@WebMvcTest(OrdersController.class)
class OrdersControllerWebTest {
    @Autowired MockMvc mvc;

    // Cung cấp mock cho dependency của controller theo
    // Spring Boot version đang sử dụng, ví dụ @MockitoBean.

    @Test
    void missingOrderReturns404() throws Exception {
        // Arrange: mock application service trả về not found.
        // Act: mvc.perform(get("/orders/missing-id")).
        // Assert: status, content type và error response.
    }
}
~~~

Đây là khung minh họa, cần bổ sung controller và mock tương ứng của dự án. Với Spring Boot 3.4+ có thể dùng `@MockitoBean` của Spring Framework; ở các phiên bản cũ thường gặp `@MockBean`. Chọn annotation theo Spring Boot/Spring Framework version của dự án, không trộn tùy tiện.

Các trường hợp nên kiểm tra:

- Request đúng và thiếu field bắt buộc.
- JSON không hợp lệ và field không hỗ trợ.
- Quy tắc authentication và authorization ở HTTP layer.
- Trạng thái 400/401/403/404/409/429/5xx theo hợp đồng API.
- Response schema và thông tin lỗi không làm lộ token hoặc stack trace.
- Header idempotency và correlation ID.

**HTTP slice test không chứng minh kết nối đến Cloud SQL hoặc Pub/Sub thực sự hoạt động.** Những ranh giới đó thuộc integration test.

## 6. Integration test với database thật bằng Testcontainers

Cloud SQL for PostgreSQL vận hành PostgreSQL, vì vậy nhiều lỗi SQL/schema có thể phát hiện sớm bằng PostgreSQL container cục bộ. Testcontainers giúp mỗi suite khởi chạy database có version xác định thay vì phụ thuộc vào một database chung do developer quản lý.

Ví dụ integration test với Spring Boot, JUnit 5 và Testcontainers:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.util.AssertionErrors.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.dao.DataIntegrityViolationException;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import java.util.UUID;

@SpringBootTest
@Testcontainers
class OrderPersistenceIT {
    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProps(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void rejectsDuplicateIdempotencyKey() {
        jdbc.update(
                "INSERT INTO order_requests (id, idempotency_key) VALUES (?, ?)",
                UUID.randomUUID(), "request-42");

        assertThrows(DataIntegrityViolationException.class,
                () -> jdbc.update(
                        "INSERT INTO order_requests (id, idempotency_key) VALUES (?, ?)",
                        UUID.randomUUID(), "request-42"));
    }
}
~~~

Ví dụ giả định migration của ứng dụng đã tạo bảng `order_requests` và unique constraint trên `idempotency_key`. Test cũng cần dependency Spring Boot Test, Testcontainers JUnit Jupiter, Testcontainers PostgreSQL và PostgreSQL JDBC driver. Chạy trên máy hoặc CI runner có Docker/container runtime tương thích.

Một integration test chất lượng cần:

- Chạy migration đúng với production, không tạo schema giả khác thực tế.
- Dùng version PostgreSQL tương thích Cloud SQL đang dùng.
- Xác minh constraint, transaction, index, serialization, timezone và isolation.
- Dọn dữ liệu hoặc tạo database/schema riêng cho mỗi suite.
- Tránh để test chạy song song cùng sửa một bảng dữ liệu chung.

**PostgreSQL container không mô phỏng Cloud SQL HA, IAM database authentication, VPC, Cloud SQL connector, backup hoặc failover.** Các yếu tố này cần kiểm tra với dịch vụ GCP thật trong sandbox/staging.

## 7. Integration test với Pub/Sub emulator

Pub/Sub hỗ trợ emulator để phát triển và kiểm thử một số hành vi publish/subscribe mà không phải gọi dịch vụ thật. Có thể khởi động bằng Google Cloud CLI:

~~~bash
gcloud beta emulators pubsub start \
  --project="orders-test" \
  --host-port="127.0.0.1:8085"
~~~

Sau đó lấy các biến môi trường cần thiết bằng:

~~~bash
gcloud beta emulators pubsub env-init
~~~

Phần cấu hình Java cần trỏ Pub/Sub client đến endpoint emulator, dùng kênh không TLS cho localhost và cơ chế không yêu cầu credentials thật. **Không giả định mọi phiên bản Java Pub/Sub client tự dùng `PUBSUB_EMULATOR_HOST` giống nhau**; hãy cấu hình endpoint/channel và credentials provider theo đúng thư viện đang sử dụng.

Một suite integration test có thể:

1. Khởi tạo topic và subscription riêng cho suite.
2. Publish message có `eventType=OrderCreated` và correlation ID.
3. Đọc message từ subscription.
4. Kiểm tra payload, attributes, event version và message ordering nếu logic yêu cầu.
5. Xác nhận ack/nack/retry trong phạm vi emulator hỗ trợ.
6. Đóng publisher/subscriber và dọn tài nguyên emulator.

Không dùng emulator như bằng chứng về các thuộc tính production sau:

- IAM và service account permissions.
- VPC, Private Service Connect hoặc VPC Service Controls.
- Quota, throughput và latency thực tế.
- Mọi edge case của ordering, dead-letter topic hoặc exactly-once delivery.
- Đặc điểm availability và sự cố của dịch vụ quản lý.

Với các thuộc tính này, cần integration test trên Pub/Sub thật trong project riêng.

### Xử lý xử lý trùng

Với Pub/Sub, consumer nên xử lý được trường hợp message được giao lại. Trong test, gửi cùng logical event ID hai lần và xác nhận chỉ một thay đổi nghiệp vụ được commit. Cơ chế deduplication nên dựa trên trạng thái bền vững, ví dụ unique constraint trong database hoặc bảng processed events; một `Set` trong bộ nhớ có thể mất khi process khởi động lại.

## 8. Firestore, Cloud Storage và các emulator khác

Không phải dịch vụ nào cũng có emulator chính thức với mức tương thích như nhau. Chọn test double dựa trên câu hỏi cần kiểm chứng.

| Dịch vụ | Kiểm thử nhanh | Kiểm thử cần GCP thật |
|---|---|---|
| Firestore | Firestore emulator cho CRUD/query cơ bản | IAM, indexes/config, performance, quotas và tính năng không được emulator mô phỏng đầy đủ |
| Pub/Sub | Emulator cho publish/subscribe và message handler | IAM, quota, throughput, networking, advanced delivery semantics |
| Cloud SQL | Testcontainers với PostgreSQL/MySQL/SQL Server tương ứng | Cloud SQL Auth Proxy/connector, IAM, HA, backup, mạng |
| Cloud Storage | Fake adapter hoặc emulator bên thứ ba có giới hạn | IAM bucket, signed URL, retention, versioning, metadata và API semantics thực |
| Spanner/Bigtable | Emulator được dịch vụ hỗ trợ cho những API phù hợp | IAM, consistency/performance đặc thù, quota và vận hành quản lý |
| Secret Manager | Fake adapter/fixture không chứa secret thật | IAM trên version, secret lifecycle và runtime identity |

Ví dụ khởi động Firestore emulator:

~~~bash
gcloud emulators firestore start \
  --host-port="127.0.0.1:8080"
~~~

Khi chạy test Java, cấu hình `FIRESTORE_EMULATOR_HOST` và project test phù hợp với thư viện. Kiểm tra cách Java client nhận emulator endpoint trong phiên bản đang sử dụng; không cấu hình ADC production cho request đến emulator.

Với Cloud Storage, các fake hoặc emulator bên thứ ba chỉ nên dùng cho integration test phù hợp với phạm vi chúng hỗ trợ. **Không xem fake Cloud Storage là mô phỏng đầy đủ IAM, retention policy, signed URLs hay hành vi production.**

Một quy tắc thực tế là chọn emulator khi muốn phát hiện lỗi serialization, API use hoặc handler; chọn GCP thật khi kiểm thử quyền, networking, cấu hình dịch vụ hoặc semantics không được emulator bảo đảm.

## 9. Integration test trên dịch vụ GCP thật

Testcontainers và emulator không thể kiểm chứng toàn bộ chính sách IAM hoặc cấu hình Cloud Run/GKE. Vì vậy, một số integration test nên chạy trên project sandbox với tài nguyên Google Cloud thật.

Ví dụ:

- Cloud Storage: service account test chỉ đọc/ghi prefix của bucket lab; kiểm tra metadata, generation precondition và lỗi 403.
- Pub/Sub: publish message đến topic lab, xác nhận subscriber xử lý và ack; kiểm tra dead-letter policy được cấu hình.
- Cloud SQL: kết nối bằng Cloud SQL connector/Auth Proxy qua IAM và network tương ứng với staging.
- Secret Manager: xác nhận workload đọc đúng secret/version được phép và bị từ chối với secret khác.
- Cloud Run/GKE: xác minh service identity có quyền mong muốn, thiếu quyền sẽ thất bại với lỗi rõ ràng.

### Cách cô lập test project

Tạo tài nguyên theo tên chứa run ID hoặc commit:

~~~text
environment: test
run-id: pr-1842-a1b2
topic: orders-pr-1842-a1b2
subscription: orders-pr-1842-a1b2-sub
object-prefix: tests/pr-1842-a1b2/
~~~

Nên:

- Sử dụng project và quota riêng cho integration test.
- Dùng danh tính test có quyền tối thiểu.
- Không kết nối trực tiếp đến database production.
- Đặt quota/budget/alert để tránh chi phí không kiểm soát.
- Dùng thời hạn tự dọn tài nguyên và ghi lại owner.
- Bảo đảm cleanup chạy cả khi test thất bại hoặc CI bị hủy.

Cleanup không nên xóa resource chỉ dựa vào prefix quá rộng. Hãy ghi chính xác resource được tạo bởi test run và chỉ xóa những resource đó.

## 10. End-to-end test trên Cloud Run và GKE

E2E test kiểm chứng đường đi tương tự người dùng thật: client → ingress/authentication → application → database/event system → kết quả nghiệp vụ.

Ví dụ một hành trình:

~~~mermaid
sequenceDiagram
    participant T as E2E test client
    participant A as Orders API on Cloud Run
    participant DB as Cloud SQL
    participant P as Pub/Sub
    participant W as Worker on GKE
    T->>A: POST /orders with idempotency key
    A->>DB: Save order and outbox record
    DB-->>A: Commit success
    A-->>T: 202 Accepted and order ID
    A->>P: Publish pending event via outbox relay
    P->>W: OrderCreated message
    W->>DB: Complete workflow and update status
    T->>A: GET /orders/{id}
    A->>DB: Read current status
    A-->>T: CONFIRMED
~~~

E2E test nên xác nhận những hành vi quan trọng:

1. API trả status và schema phù hợp.
2. Authentication token có đúng audience và quyền.
3. ID/trace được truyền xuyên hệ thống.
4. Dữ liệu xuất hiện trong database.
5. Message được phát và consumer xử lý.
6. Trạng thái cuối cùng đúng và không bị xử lý trùng.
7. Thời gian hoàn thành nằm trong ngưỡng được định nghĩa.

Với hệ thống bất đồng bộ, E2E test phải chờ theo điều kiện hoàn thành đến deadline. Không chỉ `sleep(10s)` rồi coi kết quả ngẫu nhiên là đúng. Một vòng polling có bounded timeout và backoff thường ổn định hơn.

### Chọn điểm gọi test

- Với Cloud Run private service, client dùng Google-signed ID token có audience đúng cho service URL hoặc audience đã cấu hình.
- Với GKE private service, test runner có thể chạy trong VPC/cluster hoặc qua endpoint được bảo vệ theo thiết kế.
- Không mở public ingress hoặc bỏ authentication chỉ để E2E chạy dễ hơn.
- Nếu có Cloud Load Balancing, API Gateway hoặc Cloud Armor trong đường production, E2E cần quyết định có kiểm thử xuyên lớp đó hay chỉ kiểm tra service trực tiếp.

Một E2E test gọi service trực tiếp có thể chạy thành công trong khi ingress/API Gateway bị cấu hình sai. Bởi vậy, nên có ít nhất một smoke test đi qua đường truy cập mà người dùng thực sự sử dụng.

## 11. Contract test và kiểm thử sự kiện bất đồng bộ

Trong kiến trúc nhiều dịch vụ, một thay đổi JSON field hoặc Pub/Sub attribute có thể làm consumer lỗi dù từng service vẫn vượt qua unit test.

**Contract test** kiểm tra một producer hoặc provider có giữ đúng hợp đồng mà consumer cần hay không.

Các hợp đồng thường gồm:

- REST API: path, method, status, required headers, JSON schema.
- Pub/Sub event: event type, schema version, payload, ordering key, attributes và dữ liệu bắt buộc.
- Database/event schema: backward compatibility khi thay đổi field.
- CloudEvents: `id`, `source`, `type`, `time` và data theo định dạng sự kiện.
- gRPC/Protocol Buffers: field numbers, optional fields và compatibility rules.

Ví dụ event:

~~~json
{
  "eventId": "evt-00042",
  "eventType": "OrderCreated",
  "schemaVersion": 2,
  "orderId": "ord-00042",
  "totalCents": 4200
}
~~~

Consumer contract test nên xác nhận consumer xử lý được event hợp lệ phiên bản hiện tại và phiên bản tương thích trước đó. Khi thêm field mới, không mặc định mọi consumer đã được triển khai cùng lúc.

### Không dùng E2E để phát hiện mọi lỗi schema

Contract test chạy sớm trong CI giúp phát hiện breaking change nhanh hơn, còn E2E đảm bảo hệ thống đã triển khai vẫn truyền nhận đúng giữa các service. Hai cấp bổ trợ nhau.

### Kiểm thử idempotency và outbox

Với workflow ghi Cloud SQL rồi publish Pub/Sub, hai thao tác độc lập không tạo thành một distributed transaction tự động. Nếu DB commit thành công nhưng publish thất bại, có thể mất sự kiện nếu code không có cơ chế bảo đảm.

Mẫu outbox ghi dữ liệu nghiệp vụ và bản ghi sự kiện trong cùng database transaction, sau đó relay publish riêng. Test cần kiểm tra:

- Database rollback thì outbox event không được commit.
- Publish lỗi tạm thời thì event vẫn còn để retry.
- Publish thành công nhưng ack/mark-complete thất bại có thể tạo lần publish lại.
- Consumer xử lý trùng bằng idempotency key hoặc event ID.

Đây là yêu cầu nghiệp vụ quan trọng hơn việc chỉ mock publisher và kiểm tra `publish()` được gọi một lần.

## 12. Test dữ liệu, thời gian và môi trường

Test không ổn định thường bắt nguồn từ dữ liệu dùng chung, race condition, clock và khác biệt môi trường hơn là từ framework test.

### Test fixture phải độc lập

- Dùng UUID/run ID cho mỗi suite và object/message.
- Không giả định thứ tự thực thi các test.
- Không chia sẻ một database mutable giữa nhiều job CI nếu không có isolation.
- Tạo dữ liệu tối thiểu để xác minh, không copy dữ liệu cá nhân từ production.
- Nếu cần dữ liệu gần production, dùng dữ liệu tổng hợp hoặc đã ẩn danh theo quy trình phù hợp.
- Kiểm tra cleanup bằng resource ID thực tế.

### Timezone và thời gian

- Dùng UTC khi so sánh timestamp xuyên service.
- Unit test nên inject `Clock.fixed(...)` để kiểm tra TTL, expiry và deadline.
- Test async cần phân biệt processing time, event time và timestamp do client gửi.
- Không dùng deadline quá sát khiến test chỉ fail trên CI chậm hơn máy cá nhân.

### Eventual consistency và polling

Hệ thống sự kiện có thể cần thời gian để consumer cập nhật trạng thái. Thay vì assertion ngay sau publish, dùng vòng chờ có deadline rõ ràng:

~~~java
Instant deadline = Instant.now().plus(Duration.ofSeconds(45));
boolean confirmed = false;

while (Instant.now().isBefore(deadline)) {
    if (orderClient.getStatus(orderId).equals("CONFIRMED")) {
        confirmed = true;
        break;
    }
    Thread.sleep(500);
}

assertTrue(confirmed, "Order did not reach CONFIRMED within deadline");
~~~

Đây là minh họa cho E2E polling: sleep có giới hạn và chỉ dùng ở test bất đồng bộ. Trong unit test, nên thay bằng fake scheduler hoặc virtual time. Test thực tế cần xử lý interruption đúng cách, giới hạn số request và trả thông tin chẩn đoán khi quá deadline.

## 13. Kiểm thử bảo mật và cấu hình runtime

Unit test có thể kiểm tra authorization rule trong ứng dụng, nhưng IAM và service identity thực tế cần được xác minh trong môi trường đã triển khai.

Một ma trận bảo mật tối thiểu:

| Kiểm tra | Nơi phù hợp |
|---|---|
| Validation từ chối input sai | Unit / HTTP slice |
| Endpoint trả 401 khi thiếu token | HTTP slice và E2E |
| User không có quyền nhận 403 | Integration/E2E với principal thử nghiệm |
| Cloud Run runtime service account đọc bucket được phép | Integration trên GCP |
| Cùng service account bị từ chối với bucket khác | Integration trên GCP |
| GKE Workload Identity Federation hoạt động | Integration trên cluster thật |
| Secret Manager chỉ trả đúng secret được cấp IAM | Integration trên GCP |
| Network egress/ingress đúng VPC policy | E2E/network test riêng |

Kiểm tra cả trường hợp được phép và bị từ chối. Ví dụ, một service account có thể đọc bucket lab nhưng phải bị từ chối với bucket không thuộc quyền.

Không đưa JSON key dài hạn vào container test khi có thể dùng service account gắn với runner hoặc Workload Identity Federation. Trên Cloud Run và GKE, client Java nên dùng Application Default Credentials (ADC) của runtime. Với CI ngoài GCP, ưu tiên Workload Identity Federation thay cho khóa tải xuống.

Các test security không được in access token, ID token, API key hoặc secret payload ra log. Nếu cần debug, ghi principal email không nhạy cảm theo chính sách, resource, mã lỗi và correlation ID.

## 14. Đặt quality gate trong CI/CD

Một pipeline nên chạy kiểm thử theo mức độ chi phí và khả năng phát hiện lỗi.

~~~mermaid
flowchart TD
    A[Pull request] --> B[Static checks and unit tests]
    B --> C[Contract and container integration tests]
    C --> D{Pass?}
    D -->|No| E[Block merge]
    D -->|Yes| F[Build and scan image]
    F --> G[Deploy isolated staging]
    G --> H[Cloud integration and E2E smoke]
    H --> I{Critical journeys pass?}
    I -->|No| J[Stop promotion and collect diagnostics]
    I -->|Yes| K[Approval and production rollout]
    K --> L[Post-deploy health verification]
~~~

Ví dụ với Maven và các nhóm test được đặt tên rõ:

~~~bash
./mvnw -B test
./mvnw -B verify
~~~

Lệnh `test` thường chạy unit tests qua Maven Surefire. Để `verify` chạy integration tests, cần cấu hình Maven Failsafe hoặc plugin tương ứng, cùng naming convention như `*IT`. Chỉ đặt tên file `OrderRepositoryIT` không bảo đảm Maven tự chạy nếu build chưa cấu hình.

### Gắn gate vào giai đoạn phù hợp

| Giai đoạn | Kiểm tra đề xuất | Hành động khi fail |
|---|---|---|
| Developer/PR | Unit, validation, contract, static security | Chặn merge |
| Pre-merge/CI | Integration với Testcontainers/emulator | Chặn build/release |
| Pre-release | Build, scan, provenance, image digest | Chặn phát hành |
| Staging deploy | GCP integration và critical-path E2E | Chặn promote |
| Production deploy | Smoke test an toàn, SLI/error rate | Dừng rollout, cân nhắc rollback |
| Định kỳ | Full E2E, load, restore, fault simulation | Tạo remediation và theo dõi |

Nếu sử dụng Cloud Build, lưu test reports (JUnit XML) và artifacts ở nơi có quyền truy cập thích hợp. Cloud Deploy có thể đưa cùng image digest qua staging và production; quality gate phải gắn với release và artifact đã kiểm tra, không phụ thuộc vào tag `latest`.

### Kiểm soát thời gian và chi phí

- Cache dependency Maven/Gradle theo chính sách phù hợp.
- Chạy unit test song song khi test không chia sẻ trạng thái.
- Nhóm integration tests theo dependency hoặc container, tránh khởi động quá nhiều tài nguyên.
- Chỉ chạy full E2E khi cần; sau deploy dùng smoke suite ngắn.
- Đặt timeout cho từng test, suite và job.
- Giới hạn số test project và tài nguyên tồn tại cùng lúc.

## 15. Khả năng quan sát kết quả và xử lý flaky tests

Một test fail không phải lúc nào cũng là lỗi sản phẩm. Nó có thể do hạ tầng CI thiếu quota, dependency không sẵn sàng, dữ liệu dùng chung hoặc logic test dựa trên thời gian không ổn định. Tuy nhiên, gọi mọi lỗi là flaky rồi bỏ qua sẽ làm mất giá trị quality gate.

Khi một test thất bại, cần thu thập:

- Test name, commit SHA, run ID, môi trường và thời điểm UTC.
- Assertion nào sai, input nào đã dùng và expected/actual.
- HTTP status, request ID, trace ID và response đã làm sạch.
- Cloud Logging, Cloud Trace hoặc Cloud Monitoring tương ứng.
- Tình trạng Pod/revision, database và message backlog.
- Retry count, timeout và thông tin cleanup.

### Phân loại lỗi

| Nhóm | Ví dụ | Xử lý |
|---|---|---|
| Lỗi ứng dụng | Tính tiền sai, schema không tương thích | Sửa code và giữ gate |
| Lỗi cấu hình | IAM, secret, endpoint, network sai | Sửa cấu hình môi trường |
| Lỗi dữ liệu test | Fixture dùng chung, cleanup chưa chạy | Cô lập dữ liệu |
| Test chờ không đúng | Assertion quá sớm, sleep cố định | Dùng polling có deadline |
| Hạ tầng/quota | API 429, thiếu capacity, CI runner không có Docker | Điều chỉnh quota, runner hoặc lịch chạy |
| Flaky chưa rõ nguyên nhân | Chỉ fail một số lần | Quarantine có owner và deadline, điều tra và sửa |

Retry test có thể giúp phát hiện tính không ổn định, nhưng không nên dùng retry vô hạn để làm pipeline xanh. Nếu một test quan trọng liên tục flaky, cần đánh giá rủi ro trước khi tạm loại khỏi gate và ghi rõ người chịu trách nhiệm khắc phục.

### Coverage và mutation testing

Code coverage có thể cho biết phần code nào được chạy trong test, nhưng không chứng minh assertion đủ mạnh. Với logic nghiệp vụ quan trọng, có thể bổ sung mutation testing để đánh giá khả năng test phát hiện thay đổi sai. Không cố nâng coverage bằng các test chỉ gọi getter/setter hoặc mock mọi dependency rồi xác nhận kết quả được stub sẵn.

## 16. Performance, resilience và fault testing

E2E test thường kiểm tra tính đúng đắn của hành trình; load test và fault test kiểm tra hệ thống khi chịu tải hoặc gặp sự cố. Nên tách chúng khỏi smoke suite thông thường.

### Performance

Với Cloud Run/GKE, xây dựng bài đo:

- Throughput, request/second và concurrency.
- p50/p95/p99 latency.
- Error rate, timeout và tỷ lệ retry.
- CPU, memory, autoscaling, số instance/Pod.
- Cloud SQL connection pool và giới hạn kết nối.
- Pub/Sub backlog và age of oldest unacked message.

Load test trên môi trường cô lập phải dùng traffic synthetic, có giới hạn QPS và thời gian. Không để test vô tình tạo chi phí lớn hoặc vượt quota của project dùng chung.

### Resilience

Một số thử nghiệm có kiểm soát:

- Dừng một replica GKE khi workload còn các replica khác.
- Giả lập Pub/Sub subscriber ngừng xử lý rồi kiểm tra backlog drain.
- Inject timeout vào adapter của dependency.
- Kiểm tra retry và circuit breaker không khuếch đại tải.
- Test restore Cloud SQL từ backup/PITR trên instance riêng.
- Xác minh rollback Cloud Run hoặc Cloud Deploy release hoạt động theo runbook.

Mỗi thử nghiệm cần có giả thuyết, phạm vi, điều kiện dừng, mục tiêu SLO/RTO/RPO và cách khôi phục. Không đưa fault injection có thể ảnh hưởng production vào một E2E smoke test chạy tự động trên mọi deploy.

## 17. Tình huống thực hành: Orders API trên GCP

Giả sử một hệ thống có:

- Java/Spring Boot `orders-api` chạy trên Cloud Run.
- Cloud SQL for PostgreSQL lưu orders và outbox.
- Pub/Sub truyền `OrderCreated` events.
- Worker chạy trên GKE xử lý event.
- Cloud Storage lưu hóa đơn.
- Cloud Monitoring/Logging theo dõi trạng thái.

### Giai đoạn A — Unit tests

Test các quy tắc:

1. Đơn hàng có tổng tiền âm bị từ chối.
2. Cùng idempotency key không tạo hai đơn.
3. Trạng thái `CANCELLED` không thể chuyển sang `CONFIRMED`.
4. Timeout tạm thời được retry có giới hạn.
5. Adapter lỗi phân quyền trả lỗi nghiệp vụ thích hợp.

Dùng JUnit 5 và Mockito/fake, không tạo GCP resources.

### Giai đoạn B — Integration tests cục bộ

- Khởi chạy PostgreSQL Testcontainers với migration thực.
- Kiểm tra unique constraint và transaction tạo order + outbox event.
- Dùng Pub/Sub emulator để kiểm tra serialization và handler.
- Dùng fake Cloud Storage adapter để kiểm tra các nhánh xử lý thông thường.
- Đo rằng tests không phụ thuộc vào thứ tự hoặc dữ liệu còn sót từ lần chạy trước.

### Giai đoạn C — Integration tests trên sandbox GCP

- Dùng service account test để kết nối Cloud SQL qua connector được hỗ trợ.
- Publish và consume một event trên Pub/Sub thật, kiểm tra ack và retry behavior.
- Ghi/đọc object tạm trong bucket lab, xác minh generation precondition.
- Kiểm tra principal có quyền đọc bucket cho phép và bị từ chối ở bucket khác.
- Kiểm tra Secret Manager và network configuration cần cho workload.

### Giai đoạn D — E2E trên staging

1. Deploy cùng image digest qua Cloud Deploy.
2. Tạo một order với idempotency key chứa run ID.
3. Xác minh HTTP response trả order ID.
4. Poll trạng thái đến `CONFIRMED` với deadline.
5. Xác minh hóa đơn được tạo trong prefix của test run.
6. Gửi lại cùng idempotency key và xác nhận không nhân đôi nghiệp vụ.
7. Kiểm tra log/trace, độ trễ và số lượng message.
8. Cleanup chính xác order/test resources theo chính sách lưu trữ.

### Giai đoạn E — Quality gate và báo cáo

| Kiểm tra | Tiêu chí đạt |
|---|---|
| Unit | Rules đúng, không phụ thuộc GCP |
| Database integration | Migration và transaction/constraint đúng |
| Pub/Sub integration | Event schema, ack/retry, idempotency đúng |
| GCP sandbox | IAM và kết nối dịch vụ được xác minh |
| E2E | Critical order journey hoàn thành trong deadline |
| Security | Không lộ token, không vượt quyền |
| CI/CD | Report và artifact gắn với commit/image digest |

Nếu bất kỳ gate quan trọng nào fail, dừng promote và xác định root cause trước khi triển khai production.

## 18. Checklist thiết kế chiến lược kiểm thử

### Unit

- [ ] Nghiệp vụ cốt lõi được kiểm tra bằng dữ liệu biên.
- [ ] Test không truy cập mạng, GCP hoặc hệ thống dữ liệu dùng chung.
- [ ] Dependency ngoài được thay bằng fake/mock ở ranh giới phù hợp.
- [ ] Có thể kiểm soát clock, ID và retry scheduler.
- [ ] Assertion đo hành vi cần bảo vệ, không chỉ lặp lại implementation.

### Integration

- [ ] Database migrations và constraint được chạy trên engine phù hợp.
- [ ] Emulator được dùng đúng phạm vi, các giới hạn được ghi rõ.
- [ ] Test trên GCP thật cho IAM, network và tính năng không mô phỏng đầy đủ.
- [ ] Dữ liệu/tài nguyên cô lập theo run ID và có cleanup an toàn.
- [ ] Không dùng credentials production hoặc khóa dài hạn không cần thiết.
- [ ] Có timeout và thông tin chẩn đoán khi dependency lỗi.

### End-to-end

- [ ] Critical journeys đi qua ingress và identity gần production.
- [ ] Có kiểm tra tác động nghiệp vụ cuối cùng, không chỉ HTTP 200.
- [ ] Hệ thống bất đồng bộ dùng polling có deadline.
- [ ] Có kiểm tra idempotency và failure path cần thiết.
- [ ] Smoke suite ngắn, ổn định và không làm thay đổi dữ liệu khách hàng.
- [ ] E2E result gắn với release, commit và image digest.

### CI/CD và vận hành

- [ ] Unit/contract chạy trên pull request.
- [ ] Integration gates chạy trước release.
- [ ] GCP sandbox và E2E chạy trước promote production.
- [ ] Test reports, logs và trace được lưu theo chính sách.
- [ ] Có quy trình xử lý flaky test với owner và deadline.
- [ ] Có budget/quota/cleanup cho tài nguyên test.
- [ ] Load và chaos tests có phạm vi, guardrail và thời điểm riêng.

Một chiến lược unit, integration và end-to-end tốt trên GCP bảo vệ cùng lúc tính đúng đắn của mã, hợp đồng giữa các dịch vụ và hành vi thực tế sau triển khai. Khi phân chia đúng trách nhiệm từng cấp, cô lập dữ liệu kiểm thử và gắn quality gates vào CI/CD, nhóm có thể phát hiện lỗi sớm mà vẫn kiểm chứng được các rủi ro chỉ xuất hiện trong runtime Google Cloud.


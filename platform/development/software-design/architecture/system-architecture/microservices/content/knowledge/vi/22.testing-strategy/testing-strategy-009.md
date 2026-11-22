# Quản lý dữ liệu kiểm thử và môi trường tạm thời trong Microservices

Trong kiến trúc Microservices, một kịch bản kiểm thử có thể đi qua nhiều dịch vụ, nhiều cơ sở dữ liệu và các thành phần bất đồng bộ như Kafka, RabbitMQ, Redis hoặc hệ thống bên thứ ba. Vì vậy, quản lý dữ liệu kiểm thử không chỉ là chèn vài bản ghi mẫu. Nhóm phát triển cần biết **dữ liệu do ai sở hữu, được tạo vào lúc nào, được cô lập ra sao, được sử dụng trong bao lâu và được xóa bằng cách nào**. Môi trường tạm thời (ephemeral environment) giúp kiểm tra các luồng tích hợp trong một hệ thống gần với sản phẩm thật mà không để các lần chạy kiểm thử ảnh hưởng lẫn nhau.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt fixture, seed data, factory, snapshot, dữ liệu giả lập và dữ liệu đã khử định danh.
- Chọn phạm vi dữ liệu phù hợp với unit test, component test, integration test, contract test và end-to-end test.
- Thiết kế vòng đời **tạo → chuẩn bị → sử dụng → xác minh → dọn dẹp** có thể chạy lặp lại.
- Cô lập dữ liệu theo test case, test suite, pipeline hoặc môi trường mà không tạo xung đột giữa các dịch vụ.
- Dựng môi trường tạm thời bằng Testcontainers, Docker Compose hoặc namespace Kubernetes tùy quy mô.
- Kiểm thử các tình huống bất đồng bộ, eventual consistency, retry, idempotency và saga bằng dữ liệu ổn định.
- Thiết lập quy tắc an toàn cho thông tin nhạy cảm, tài nguyên cloud, chi phí và thời gian tồn tại môi trường.

## 2. Vì sao bài toán khó hơn trong Microservices?

Ở ứng dụng nguyên khối, nhiều bài kiểm thử có thể tạo dữ liệu trong một database và rollback transaction sau khi chạy. Trong Microservices, mỗi dịch vụ thường sở hữu dữ liệu riêng; giao dịch nghiệp vụ có thể được hoàn thành thông qua HTTP, message broker và nhiều transaction độc lập.

Ví dụ luồng đặt hàng:

1. **Order Service** tạo đơn hàng ở database của mình.
2. **Inventory Service** giữ hàng dựa trên sự kiện đặt hàng.
3. **Payment Service** xử lý thanh toán qua cổng giả lập hoặc sandbox.
4. **Notification Service** tiêu thụ sự kiện để gửi thông báo.
5. **Order Service** cập nhật trạng thái cuối khi nhận kết quả từ các dịch vụ khác.

Một bài kiểm thử thành công phải biết đơn hàng nào thuộc riêng lần chạy đó, trạng thái nào là cuối cùng, sự kiện nào đã được xử lý, và tài nguyên nào cần giải phóng. Nếu dùng chung dữ liệu cố định như user ID = 1 hoặc một topic Kafka chia sẻ mà không đặt giới hạn, hai pipeline chạy đồng thời có thể sửa/xóa dữ liệu của nhau và tạo lỗi kiểm thử chập chờn (*flaky test*).

**Nguyên tắc:** mỗi bài kiểm thử phải kiểm soát được điều kiện ban đầu, cách nhận diện dữ liệu của chính nó và tiêu chí kết thúc; mọi phụ thuộc bên ngoài cần có ranh giới rõ ràng.

## 3. Khái niệm và lựa chọn loại dữ liệu

| Loại dữ liệu | Vai trò | Dùng ở đâu | Lưu ý |
|---|---|---|---|
| Fixture | Bộ dữ liệu xác định trước để tái hiện một tình huống | Unit, component, integration | Ngắn gọn, có tên thể hiện tình huống |
| Factory / Builder | Sinh đối tượng hợp lệ rồi tùy biến trường cần thử | Unit, integration | Mặc định hợp lệ; các ngoại lệ phải được khai báo tường minh |
| Seed data | Dữ liệu nền như bảng mã, sản phẩm mẫu, cấu hình | Database test, môi trường tạm thời | Phiên bản hóa cùng schema; áp dụng lặp lại được |
| Synthetic data | Dữ liệu được tạo mới, không lấy từ người dùng thật | Integration, E2E, tải | Bảo đảm tính nhất quán nghiệp vụ và độ phân bố phù hợp |
| Masked / de-identified data | Dữ liệu nguồn đã được xử lý để giảm rủi ro lộ thông tin | Kiểm thử tương thích dữ liệu có kiểm soát | Phải được rà soát quyền sử dụng và khả năng tái nhận diện |
| Snapshot | Trạng thái lưu sẵn để dựng nhanh nền dữ liệu | Kiểm thử hiệu năng, tái hiện lỗi | Kèm version schema, hạn sử dụng và nguồn gốc |
| Contract example | Payload mẫu hợp lệ/sai theo hợp đồng API hoặc event | Contract test | Theo dõi version; không giả định payload luôn đầy đủ |

Ưu tiên **factory nhỏ và dữ liệu tổng hợp có chủ đích** cho kiểm thử tự động. Chỉ dùng dữ liệu phản ánh thực tế sản xuất khi có nhu cầu cụ thể và quy trình bảo vệ thông tin phù hợp. Dữ liệu từ production không tự động trở nên an toàn chỉ vì đã thay tên hoặc email.

### 3.1. Dữ liệu hợp lệ và dữ liệu biên

Mỗi entity nên có một tập dữ liệu tối thiểu hợp lệ để test tập trung vào thuộc tính đang xét. Bổ sung trường hợp biên có tên rõ ràng: đơn hàng hết tồn kho, thanh toán timeout, coupon hết hạn, event trùng ID, timestamp sai múi giờ, số lượng bằng 0 hoặc vượt giới hạn. Đừng tạo tập JSON quá lớn mà không biết trường nào quyết định hành vi.

Ví dụ factory khái niệm:

~~~java
record TestOrder(
    String orderId,
    String customerId,
    String productId,
    int quantity
) {}

static TestOrder validOrder(String runId) {
    return new TestOrder(
        "order-" + runId + "-" + UUID.randomUUID(),
        "customer-" + runId,
        "sku-demo",
        1
    );
}
~~~

Factory tạo trạng thái cơ bản hợp lệ, trong khi test chủ động đổi quantity hoặc productId để mô tả điều kiện cần kiểm tra. UUID giúp tránh trùng khóa; với kiểm thử cần tái lập chính xác, có thể dùng seed giả ngẫu nhiên cố định và ghi seed vào kết quả chạy.

## 4. Phân lớp kiểm thử và phạm vi môi trường

| Cấp kiểm thử | Phụ thuộc cần có | Chiến lược dữ liệu | Tốc độ / phạm vi |
|---|---|---|---|
| Unit | Hàm, class, mock trong bộ nhớ | Builder/fixture độc lập | Rất nhanh, chạy trên mỗi commit |
| Component | Một service và adapter giả | Factory, stub, database cục bộ khi cần | Nhanh, chủ yếu kiểm tra logic service |
| Integration | Database, cache, broker thật ở mức giao thức | Dữ liệu seed hoặc container riêng | Phát hiện lỗi truy vấn, transaction, serialization |
| Contract | Provider/consumer và schema API/event | Request/response mẫu, các version tương thích | Phát hiện phá vỡ hợp đồng giữa dịch vụ |
| E2E / workflow | Nhiều service được triển khai cùng nhau | Dataset độc lập theo run và luồng nghiệp vụ | Chậm hơn, giữ ít kịch bản trọng yếu |
| Performance / resilience | Cấu hình gần sản xuất, lưu lượng đo được | Dataset lớn, có phân bố và kích thước kiểm soát | Tách lịch chạy và giới hạn tài nguyên |

Không cần dựng toàn bộ hệ thống cho mọi test. Nếu chỉ kiểm tra ánh xạ JSON của Payment Service, stub hợp đồng là đủ. Nếu kiểm tra Order Service nhận sự kiện PaymentCompleted và cập nhật trạng thái, cần broker cùng persistence thực tế ở lớp tích hợp. Nếu kiểm tra một hành trình mua hàng xuyên dịch vụ, môi trường tạm thời nhiều service mới mang lại giá trị.

## 5. Thiết kế vòng đời dữ liệu kiểm thử

Một vòng đời có thể tái lập bao gồm sáu trạng thái:

1. **Định danh lần chạy:** tạo RUN_ID duy nhất từ PR/pipeline/run attempt; gắn nó vào dữ liệu, log, trace và tên tài nguyên được phép đặt tên.
2. **Provision:** dựng database, broker, object storage hoặc dịch vụ giả lập; chạy migration đúng version ứng dụng.
3. **Seed:** khởi tạo dữ liệu nền và dữ liệu cho kịch bản; kiểm tra precondition bằng API hoặc truy vấn chuyên biệt.
4. **Execute:** gọi nghiệp vụ, phát sự kiện hoặc chạy bộ kiểm thử; các khóa như orderId phải truy vết được về RUN_ID.
5. **Assert:** xác nhận kết quả người dùng quan sát được, đồng thời xác minh các tác dụng phụ quan trọng (event, trạng thái lưu trữ, side effect).
6. **Teardown:** xóa namespace/container/database/topic đã cấp riêng; lưu log, trace và artifact chẩn đoán theo chính sách trước khi xóa.

Luồng này cần làm việc cả khi test thất bại, pipeline bị hủy hoặc worker CI mất kết nối. Vì vậy, ngoài nhánh cleanup bình thường, cần một bộ quét tài nguyên quá hạn theo nhãn thời gian và owner.

### 5.1. Khóa nhận diện và dữ liệu có thể tái lập

Một định danh thực dụng là:

~~~text
RUN_ID = pr-<number>-<workflow-run>-<attempt>
RESOURCE_TAGS = { owner: "qa-ci", runId: RUN_ID, expiresAt: "ISO-8601" }
TEST_ENTITY_ID = "order-" + RUN_ID + "-" + caseId
~~~

RUN_ID phải không gây lộ bí mật và đủ khác nhau giữa hai lần chạy. Nên in RUN_ID vào báo cáo kiểm thử, log có cấu trúc và trace attributes. Có thể kết hợp dữ liệu cố định dùng để tái hiện lỗi với ID duy nhất dùng để chống va chạm: **giá trị nghiệp vụ ổn định, tên tài nguyên và khóa định danh được cô lập**.

### 5.2. Idempotent seeding

Seed cần chạy lại mà không nhân bản bản ghi hoặc phá dữ liệu có sẵn. Với database riêng hoàn toàn, có thể khởi tạo từ migration sạch và insert fixture. Với vùng test có dữ liệu dùng chung được cho phép, dùng các khóa tự nhiên/khóa run và thao tác upsert trong phạm vi ownership rõ ràng.

Ví dụ PostgreSQL trong **database chuyên dụng cho test**:

~~~sql
CREATE TABLE IF NOT EXISTS test_catalog (
    sku         text PRIMARY KEY,
    name        text NOT NULL,
    active      boolean NOT NULL
);

INSERT INTO test_catalog(sku, name, active)
VALUES ('sku-demo', 'Demo product', true)
ON CONFLICT (sku)
DO UPDATE SET name = EXCLUDED.name, active = EXCLUDED.active;
~~~

Đây là ví dụ seed đơn giản. Schema bảng thực tế phải đến từ migration của service; test không nên tự tạo cấu trúc khác với sản xuất chỉ để “chạy được”.

## 6. Cô lập dữ liệu: chọn ranh giới phù hợp

### 6.1. Các mức cô lập

| Mức | Cách làm | Điểm mạnh | Rủi ro hoặc giới hạn |
|---|---|---|---|
| Mỗi test | Transaction rollback, instance repo in-memory, database/schema riêng | Test độc lập cao | Rollback chỉ có hiệu lực trong phạm vi transaction phù hợp |
| Mỗi test suite | Một database/container riêng cho suite | Cân bằng tốc độ và độ cô lập | Test trong suite cần tránh phụ thuộc thứ tự |
| Mỗi CI run | Namespace, database, broker/topic riêng theo RUN_ID | Hỗ trợ chạy PR song song | Tốn tài nguyên hơn |
| Môi trường tích hợp dùng chung | Dữ liệu gắn tenant/run ID, fixture theo ownership | Tiết kiệm chi phí | Phải kiểm soát xung đột, race, cleanup và quyền truy cập |

Phương án đơn giản nhất để bảo đảm test không can thiệp nhau là tài nguyên dùng riêng trong thời gian chạy. Chỉ chia sẻ hạ tầng nếu lợi ích về tốc độ và chi phí đáng kể và đã có cơ chế cách ly ở lớp ứng dụng.

### 6.2. Lưu ý về transaction và database

- **Rollback sau test** chỉ thu hồi những thao tác trong transaction mà test thực sự kiểm soát. Gọi HTTP sang service có transaction độc lập thì rollback của test không tự hoàn tác được giao dịch ở service đó.
- Mỗi Microservice vẫn phải sở hữu schema/database của mình. Test E2E nên chuẩn bị và xác minh qua API hoặc test-support contract có kiểm soát, không trực tiếp sửa bảng nội bộ của nhiều service.
- Dùng **TRUNCATE** hoặc reset schema chỉ trên database đã xác nhận là dành riêng cho lần kiểm thử. Tuyệt đối không chạy cleanup dạng xóa toàn bảng trên database dùng chung.
- Migration Flyway/Liquibase phải chạy trước seed; dữ liệu snapshot cần gắn schema version để không âm thầm che giấu lỗi migration.
- Khi kiểm thử song song, constraint unique, khóa nghiệp vụ và idempotency key phải tránh dùng cùng một giá trị giữa hai lần chạy.

### 6.3. Broker, cache và object storage

Database không phải nguồn nhiễm chéo duy nhất. Với Kafka/RabbitMQ, có thể dùng broker riêng, topic/queue riêng theo run hoặc consumer group riêng kèm quy ước correlation ID; cách nào phù hợp phụ thuộc đặc tính retention và offset. Consumer group mới **không** biến một topic chung thành nơi chỉ chứa dữ liệu của riêng run đó. Consumer vẫn phải lọc/đối chiếu đúng thông điệp thuộc kịch bản nếu topic được chia sẻ.

Redis cần namespace key hoặc instance riêng; object storage cần bucket/prefix riêng và lifecycle rule; webhook và email phải chuyển đến endpoint/sink giả lập để tránh tạo side effect thật. Kiểm soát cleanup không chỉ xóa dữ liệu chính mà còn xóa các blob, message và key tạm thời do kịch bản phát sinh.

## 7. Testcontainers cho tích hợp cục bộ và CI

**Testcontainers** tạo các dependency có giao thức thực như PostgreSQL, Redis hoặc Kafka cho bài integration test. Nó hữu ích khi lỗi xuất phát từ JDBC, migration, transaction, serialization hoặc cấu hình client mà mock đơn thuần không kiểm chứng được.

Ví dụ minh họa với Spring Boot và JUnit 5:

~~~java
@Testcontainers
@SpringBootTest
class OrderRepositoryIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    OrderRepository orderRepository;

    @Test
    void savesAnOrder() {
        OrderEntity order = new OrderEntity(
            "order-it-001", "customer-it", "CREATED"
        );
        orderRepository.save(order);

        assertThat(orderRepository.findById("order-it-001"))
            .isPresent();
    }
}
~~~

Các import, entity và repository được rút gọn để tập trung vào cách dùng container. Dự án cần các dependency tương ứng của JUnit 5, Testcontainers và driver PostgreSQL. Khi chạy với Spring Boot, hãy xác nhận migration và schema của service được khởi động đúng trước test. Nếu suite dùng chung container, tránh hard-code ID giống nhau ở nhiều bài hoặc dùng cơ chế reset phù hợp.

**Khi nào không nên dùng Testcontainers?** Nếu test chỉ kiểm tra logic thuần túy không phụ thuộc I/O, container làm bài chạy chậm mà ít tăng độ tin cậy. Nếu cần kiểm tra hành vi triển khai và đường truyền mạng giữa nhiều service thực, một container database trong process test chưa thay thế được môi trường tích hợp đa dịch vụ.

## 8. Dựng môi trường tạm thời theo Pull Request

Môi trường tạm thời là một tập tài nguyên được tạo cho một mục đích hữu hạn rồi hủy khi hết hạn: service, database, broker, secret, ingress, cấu hình và telemetry. Nó có thể nằm trong Docker Compose trên CI runner hoặc namespace Kubernetes trên cụm dùng chung.

### 8.1. Khi nào chọn công cụ nào?

| Công cụ | Phù hợp | Lưu ý |
|---|---|---|
| Testcontainers | Một vài dependency cho test Java | Quản lý lifecycle tự động theo bài/suite |
| Docker Compose | Nhóm service nhỏ trên CI runner | Quản lý port, healthcheck, volume và cleanup |
| Kubernetes namespace + Helm/Kustomize | PR preview nhiều service dùng cụm chung | Resource quota, network policy, RBAC và TTL |
| Infrastructure as Code | Tài nguyên cloud thực cần kiểm tra riêng | Tag owner/TTL, giới hạn chi phí, hủy sau workflow |
| Service virtualization / WireMock | API bên thứ ba khó cấp môi trường | Giữ contract và hành vi lỗi quan trọng |

### 8.2. Quy trình gợi ý trên CI

~~~text
PR opened/updated
    |
    v
Build image có version bằng commit SHA
    |
    v
Tạo RUN_ID và namespace riêng + expiry tag
    |
    v
Dựng dependency / apply secret của môi trường test
    |
    v
Triển khai các service theo version cần kiểm thử
    |
    v
Chờ readiness + chạy database migrations
    |
    v
Seed dataset + chạy contract/integration/E2E
    |
    v
Thu junit report, service logs và traces
    |
    v
Teardown trong finally/always + quét TTL dự phòng
~~~

Ví dụ shell minh họa cho môi trường Kubernetes đã được cấu hình quyền:

~~~bash
RUN_ID="pr-$PR_NUMBER-$CI_RUN_ID"
kubectl create namespace "$RUN_ID"
kubectl label namespace "$RUN_ID" owner=qa-ci run-id="$RUN_ID"

helm upgrade --install order ./charts/order \
  --namespace "$RUN_ID" \
  --set image.tag="$GIT_SHA"

kubectl rollout status deployment/order -n "$RUN_ID" --timeout=180s

# Chạy migration/seed/test theo cơ chế CI của dự án.
# Sau khi lưu báo cáo và log:
kubectl delete namespace "$RUN_ID" --wait=false
~~~

Đoạn lệnh cho thấy nguyên tắc đặt tên và vòng đời, chưa phải pipeline production-ready. Trong hệ thống thực tế, các bước triển khai và kiểm thử cần nằm trong khối **finally/always**, có kiểm tra namespace trước khi xóa, có quyền tối thiểu, có quota và có job dọn tài nguyên hết hạn khi pipeline bị hủy. Không tái sử dụng secret production cho môi trường PR.

### 8.3. Thành phần của một môi trường đủ tin cậy

- **Version:** image được gắn commit SHA; manifest, migration và test suite tương thích với cùng lần chạy.
- **Cấu hình:** biến môi trường và feature flag được kiểm soát; không dùng cấu hình ẩn khác biệt không ghi lại.
- **Readiness:** ứng dụng chỉ nhận test sau khi dependency và migration hoàn tất; readiness khác với việc process vừa khởi động.
- **Networking:** route giữa service cần giống hành vi mong muốn; chặn truy cập ra bên ngoài không cần thiết.
- **Giới hạn:** CPU, RAM, số pod, dung lượng DB, timeout CI và thời gian tồn tại có ngưỡng cụ thể.
- **Quan sát:** log/trace có RUN_ID, correlation ID, version dịch vụ và thời điểm sự kiện để truy vết lỗi.
- **Lifecycle:** test thất bại vẫn xuất artifact và dọn tài nguyên; tài nguyên mồ côi được phát hiện bằng tag/TTL.

Không phải mọi PR đều cần môi trường đầy đủ nếu chi phí cao. Có thể giữ unit, component và contract test làm cổng nhanh; triển khai preview environment cho các thay đổi tích hợp quan trọng hoặc các suite E2E có giá trị cao.

## 9. Kiểm thử bất đồng bộ và eventual consistency

Trong Microservices, câu lệnh API trả 202 Accepted không có nghĩa toàn bộ workflow đã hoàn tất. Một event có thể đi qua broker, consumer, outbox và retry trước khi projection được cập nhật.

### 9.1. Đợi điều kiện nghiệp vụ, không ngủ cố định

Tránh dùng sleep 10 giây trong mọi test: máy nhanh thì lãng phí, máy chậm vẫn có thể thất bại. Thay vào đó, đợi trạng thái quan sát được với timeout giới hạn.

Ví dụ với Awaitility:

~~~java
await()
    .atMost(Duration.ofSeconds(20))
    .pollInterval(Duration.ofMillis(250))
    .untilAsserted(() -> {
        var order = orderApi.getOrder(orderId);
        assertThat(order.status()).isEqualTo("PAID");
    });
~~~

Timeout là ngân sách tối đa để phát hiện thành công, không phải độ trễ cố định. Nếu hết thời gian, log nên cho biết orderId, eventId, correlationId và trạng thái cuối đọc được để phân biệt lỗi nghiệp vụ với môi trường chậm.

### 9.2. Kiểm thử retry và idempotency

Một consumer có thể nhận lại cùng event do cơ chế giao nhận *at least once*. Bài kiểm thử nên phát lại cùng eventId và xác minh side effect được áp dụng một lần về mặt nghiệp vụ.

Ví dụ kịch bản:

1. Tạo đơn hàng có RUN_ID duy nhất.
2. Gửi PaymentCompleted(eventId = E1, orderId = O1).
3. Đợi Order Service chuyển O1 thành PAID.
4. Gửi lại đúng event E1.
5. Xác minh số lần ghi nhận thanh toán không tăng ngoài quy tắc nghiệp vụ; không phát hai thông báo cùng mục đích nếu hệ thống cam kết deduplication.
6. Kiểm tra trạng thái bền vững qua API hoặc dữ liệu mà test được phép xem.

Với saga, test thêm nhánh lỗi thanh toán/hết hàng và xác minh hành động bù (compensation) được thực hiện đúng. Dữ liệu cần thiết kế sao cho biết rõ bước nào đã hoàn tất và bước nào còn chờ; đừng giả định thứ tự message luôn cố định khi các service xử lý song song.

### 9.3. Dead-letter, outbox và độ trễ

Các test quan trọng gồm event sai schema, consumer tạm thời lỗi, timeout bên thứ ba, outbox publish lại và message vào dead-letter queue. Mỗi trường hợp phải có **đầu vào nhận diện được**, hành vi kỳ vọng và thời gian chờ tối đa. Không xác nhận “queue rỗng” để kết luận thành công nếu trong queue có thể có message của run khác.

## 10. Dữ liệu phụ thuộc thời gian và ngẫu nhiên

Các trường hợp dễ gây flaky test:

- **Timestamp:** múi giờ máy CI khác local, daylight saving, ngày kết thúc tháng hoặc expiry dựa trên thời gian thật.
- **Random:** sinh chuỗi không lưu seed, làm lỗi khó tái hiện.
- **Thứ tự:** database query không có ORDER BY, hoặc giả định message luôn đến theo một thứ tự.
- **Cache:** dữ liệu tồn đọng khiến test sau đọc trạng thái cũ.
- **Parallelism:** hai test cùng sửa một resource hoặc cùng sử dụng user giả định.
- **Môi trường:** rate limit, mạng chập chờn, service mock thay đổi kịch bản do test khác.

Cách khắc phục là tiêm Clock vào logic phụ thuộc thời gian, kiểm soát seed ngẫu nhiên, dùng ID riêng, chờ condition, xác định thứ tự dữ liệu khi cần và mô tả rõ dependency. Không tăng timeout vô hạn để che lỗi; nếu timeout tăng đột ngột, xem trace để phân biệt nghẽn tài nguyên với logic không hoàn tất.

## 11. An toàn dữ liệu và bảo mật môi trường

### 11.1. Nguyên tắc dữ liệu

- Ưu tiên dữ liệu tổng hợp không gắn với người thật. Nếu buộc dùng dữ liệu bắt nguồn từ production, phải có quyền và quy trình giảm thiểu rủi ro theo chính sách tổ chức.
- Mã hóa dữ liệu nhạy cảm khi truyền/lưu theo yêu cầu; không đưa mật khẩu, token, số thẻ, thông tin định danh hay secret vào fixture, log hoặc báo cáo test.
- Khử định danh phải xét cả khóa liên kết, metadata, nội dung tự do và trường hiếm có thể tái nhận diện; đổi một cột email đơn lẻ không đủ.
- Tài khoản test dùng quyền tối thiểu, có hạn dùng. Secret được cấp qua công cụ quản lý bí mật và thu hồi khi môi trường hủy.
- Luồng gửi email/SMS/thanh toán phải sử dụng sandbox hoặc stub, kèm chặn egress để test không tạo tác động thật.
- Nếu cần lưu artifact thất bại, áp dụng thời hạn lưu, quyền truy cập và quy tắc xóa thích hợp.

### 11.2. An toàn hạ tầng

Namespace là ranh giới tổ chức tài nguyên, nhưng **không mặc nhiên là ranh giới bảo mật đầy đủ**. Cần kiểm tra RBAC, NetworkPolicy, service account, quota và quyền truy cập secret. Không cho pipeline dùng quyền xóa tài nguyên ngoài phạm vi RUN_ID. Với cloud resources được tạo qua IaC, gắn tag owner và expiresAt ngay khi cấp phát; đặt cơ chế tự động hủy phòng trường hợp pipeline bị ngắt.

## 12. Thiết kế cleanup đáng tin cậy

Cleanup tốt cần **giới hạn phạm vi, chạy lặp lại được và có chứng cứ**:

- Xác định chủ sở hữu tài nguyên bằng RUN_ID/namespace/bucket prefix; thao tác xóa chỉ tác động đúng tài nguyên đã provision.
- Thu log và kết quả test trước khi xóa môi trường; tránh giữ toàn bộ dữ liệu nhạy cảm trong artifact.
- Cho phép chạy cleanup hai lần mà không báo lỗi vô nghĩa khi tài nguyên đã biến mất.
- Đặt retry có giới hạn cho API hạ tầng; báo rõ resource còn sót khi cleanup thất bại.
- Dùng job quét TTL định kỳ để tìm namespace, volume, database hoặc tài nguyên cloud không còn pipeline sở hữu.
- Tách **retention để debug** (có thời hạn và truy cập giới hạn) khỏi tài nguyên tạm phải xóa ngay; không giữ môi trường vô hạn vì một test thất bại.

Một mô hình trạng thái có thể là PROVISIONING → READY → TESTING → COLLECTING → DELETING → DELETED. Nếu chuyển sang FAILED, hệ thống vẫn đi qua COLLECTING và DELETING. Với tài nguyên mồ côi, sweeper dùng expiresAt và ownership đã được ghi để xác định đối tượng có thể hủy.

## 13. Ví dụ xuyên suốt: kiểm thử luồng đặt hàng

Giả sử hệ thống có Order Service, Inventory Service, Payment Service, Kafka và PostgreSQL riêng cho mỗi service.

**Kịch bản:** tạo đơn hàng một sản phẩm còn tồn kho, xử lý thanh toán giả lập thành công, nhận trạng thái PAID và phát thông báo một lần.

**Dựng dữ liệu:**

~~~text
runId: pr-42-180-1
customerId: customer-pr-42-180-1
productId: sku-demo
orderId: order-pr-42-180-1-A
paymentId: payment-pr-42-180-1-A
eventId: payment-completed-pr-42-180-1-A
~~~

**Trình tự:**

1. Tạo namespace/stack riêng, chạy migration và đợi readiness của từng service.
2. Seed sản phẩm và tồn kho qua API/support endpoint có kiểm soát hoặc fixture cục bộ của service sở hữu; không ghi trực tiếp xuyên database.
3. Cấu hình Payment gateway sandbox phản hồi success cho paymentId của run.
4. Gửi POST /orders với customerId, productId, quantity = 1; lấy orderId do hệ thống trả về nếu API tự sinh ID.
5. Dùng orderId thực tế và correlation ID để đợi GET /orders/{id} trả PAID.
6. Kiểm tra số lượng tồn kho và trạng thái thanh toán theo hợp đồng được công bố.
7. Phát lại event thanh toán có cùng eventId để xác minh cơ chế xử lý trùng.
8. Thu test report, logs, traces; chạy cleanup và xác nhận resource tạm đã được gửi yêu cầu xóa.

**Kịch bản lỗi bổ sung:** tồn kho = 0 dẫn đến từ chối giữ hàng; Payment gateway timeout dẫn đến retry có giới hạn; message trùng không tạo hai lần trừ tồn hoặc hai khoản thanh toán. Với saga, xác minh bù trừ khi bước sau thất bại. Dữ liệu tạo mới cho mỗi nhánh giúp test không phụ thuộc thứ tự chạy.

## 14. Mẫu quy ước vận hành cho nhóm

Một nhóm có thể thống nhất cấu hình tối thiểu như sau:

| Hạng mục | Quy ước gợi ý |
|---|---|
| Định danh | RUN_ID duy nhất cho pipeline attempt; correlation ID theo workflow |
| Nguồn dữ liệu | Factory/synthetic mặc định; seed và schema được version hóa |
| Ownership | Service sở hữu dữ liệu của mình; API/test hook có quyền giới hạn khi cần |
| Cô lập | Database/namespace riêng cho E2E song song; key prefix riêng cho tài nguyên dùng chung |
| Mốc sẵn sàng | Readiness, migration thành công, seed hoàn tất |
| Chờ bất đồng bộ | Poll assertion với deadline; không sleep cố định |
| Cleanup | finally/always + sweeper TTL; chỉ xóa resource có owner/run ID khớp |
| Debug | JUnit report, version image, run ID, logs và traces có thời hạn lưu |
| Quyền và chi phí | Secret test, RBAC tối thiểu, quota, TTL, giới hạn số môi trường hoạt động |
| Trách nhiệm | Chủ sở hữu test fixture, schema contract và môi trường được ghi rõ |

### 14.1. Những chỉ số nên theo dõi

- **Tỷ lệ flaky:** test fail rồi pass khi rerun mà không đổi code.
- **Thời gian provision đến ready:** trung vị và nhóm chậm nhất.
- **Tỷ lệ lỗi do dữ liệu:** trùng ID, sai schema, seed lỗi, cleanup sót.
- **Tỷ lệ cleanup thành công:** tài nguyên còn sót sau TTL.
- **Chi phí mỗi pipeline hoặc mỗi PR preview:** CPU, storage, cloud resources.
- **Khả năng tái hiện lỗi:** có đủ run ID, seed, version, trace và fixture để chạy lại không.

Những chỉ số này hỗ trợ cải thiện hạ tầng test, không thay thế việc đánh giá đúng/sai của nghiệp vụ.

## 15. Các lỗi thiết kế thường gặp và cách xử lý

| Dấu hiệu | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Test pass riêng, fail khi chạy song song | Dùng chung khóa hoặc tài nguyên | RUN_ID, isolation theo suite/run, tránh record cố định |
| Test E2E bị treo chờ trạng thái | Consumer chậm, event chưa được xử lý, test chờ sai điều kiện | Poll theo trạng thái nghiệp vụ, trace correlation ID |
| Cleanup xóa nhầm dữ liệu | Tên resource mơ hồ, lệnh xóa quá rộng | Gắn owner/run ID và kiểm tra phạm vi xóa |
| Local pass, CI fail | Migration/config/clock khác nhau | Pin version, kiểm soát cấu hình và Clock |
| Contract test pass nhưng runtime lỗi | Fixture thiếu field hoặc không khớp version provider | Consumer-driven contract, kiểm tra backward compatibility |
| Môi trường PR chạy mãi | Pipeline bị hủy trước teardown | TTL sweeper, quota và lịch xóa tự động |
| Lỗi tái hiện khó | Dữ liệu random không lưu seed, thiếu log | Ghi seed, RUN_ID, image digest, test parameters |
| Test phát email/thanh toán thật | Egress hoặc credentials trỏ nhầm production | Sandbox/stub, secret scope riêng, chặn outbound ngoài danh sách |

## 16. Checklist triển khai trong một dự án Microservices

Trước khi bổ sung suite integration/E2E, nhóm nên trả lời được:

- [ ] Test đang kiểm chứng điều gì và cần bao nhiêu service thật?
- [ ] Fixture hoặc factory nào tạo điều kiện ban đầu, ai sở hữu dữ liệu đó?
- [ ] Có RUN_ID/correlation ID và khóa riêng cho mỗi lần chạy song song không?
- [ ] Migration, seed và cấu hình môi trường được version hóa và tái lập không?
- [ ] Database, broker, cache, object storage có phạm vi cô lập phù hợp không?
- [ ] Assertion cho xử lý bất đồng bộ dùng điều kiện nghiệp vụ và deadline hợp lý không?
- [ ] Các nhánh retry, duplicate event, timeout, compensation có dữ liệu riêng không?
- [ ] Tất cả endpoint ngoài hệ thống có chuyển sang sandbox/stub không?
- [ ] Secret và dữ liệu nhạy cảm có được kiểm soát trong fixture, logs và artifact không?
- [ ] Cleanup có chạy khi thất bại/hủy pipeline và có TTL dọn tài nguyên mồ côi không?
- [ ] Có report, version image, RUN_ID và trace để tái hiện lỗi không?

## 17. Kết luận

Dữ liệu kiểm thử đáng tin cậy phải **đúng điều kiện nghiệp vụ, độc lập giữa các lần chạy, dễ tái hiện và có vòng đời rõ ràng**. Môi trường tạm thời đưa nguyên tắc đó lên cấp hạ tầng: tạo đúng cấu hình, chờ hệ thống sẵn sàng, thực hiện kịch bản, giữ đủ chứng cứ chẩn đoán và hủy tài nguyên an toàn. Trong Microservices, hãy bắt đầu từ test nhỏ và hợp đồng rõ ràng, rồi chỉ dựng thêm dependency hoặc service thật khi mục tiêu kiểm thử cần đến chúng.
# Chọn thành phần thật, fake, stub, mock hoặc dịch vụ trong container

Trong chiến lược kiểm thử Spring Boot, câu hỏi đầu tiên không phải “dùng Mockito hay Testcontainers?” mà là **thành phần nào phải chạy thật để bài kiểm thử phát hiện đúng loại lỗi ta quan tâm**. Một `PaymentGateway` có thể là stub trong bài test tính tiền, mock trong bài test gửi lệnh thu tiền, hoặc kết nối dịch vụ sandbox thật trong bài test tích hợp. Chọn sai có thể khiến test nhanh nhưng không có giá trị, hoặc quá chậm và khó chẩn đoán.

**Mục tiêu học tập:** phân biệt real component, fake, stub, mock và dịch vụ container; lựa chọn dựa trên phạm vi và rủi ro; viết unit test và integration test có bằng chứng rõ ràng; nhận diện giới hạn của mỗi lựa chọn.

## 1. Phân biệt rõ từng loại thành phần

*Test double* là thuật ngữ chung cho đối tượng thay một collaborator trong test. “Mock” thường được dùng như tên gọi chung trong giao tiếp, nhưng khi thiết kế test phải phân biệt vai trò.

| Thành phần | Bản chất | Nên dùng khi | Không tự chứng minh được |
| --- | --- | --- | --- |
| **Real component** | Chính implementation/cấu hình production trong phạm vi kiểm thử | Kiểm logic nghiệp vụ, validation, mapper, Spring wiring, transaction hoặc security thật | Những phụ thuộc khác đã bị thay |
| **Fake** | Một implementation có hành vi nhưng giản lược, ví dụ repository lưu bằng `HashMap` | Cần trạng thái và nhiều bước đọc/ghi trong unit test | SQL, locking, unique constraint, rollback, độ trễ và lỗi database thật |
| **Stub** | Trả giá trị/lỗi được định trước | Muốn cố định đầu vào và đi qua nhánh thành công/thất bại | Phụ thuộc thật có xử lý request/protocol đúng không |
| **Mock** | Ghi nhận/kiểm tra lời gọi, tham số và số lần gọi | Hợp đồng cần xác minh một lệnh gửi ra ngoài | Hệ thống ngoài có thực sự hoàn thành lệnh không |
| **Dịch vụ thật trong container** | Chạy PostgreSQL/Redis/Kafka… thật bằng image trong môi trường tạm | Lỗi phụ thuộc SQL dialect, driver, schema, protocol, transaction hoặc cấu hình tích hợp | Toàn bộ quy mô và hạ tầng production |

**Spy** là dạng khác: cho phần lớn logic thật chạy và quan sát cách đối tượng được gọi. Tránh spy nếu chỉ dùng để tiếp cận chi tiết nội bộ mà test không cần biết.

Hai điểm rất quan trọng:

- Đối tượng tạo bởi `Mockito.mock(...)` **có thể đóng vai trò stub** khi chỉ cấu hình `when(...).thenReturn(...)`, hoặc **mock** khi dùng `verify(...)` kiểm tương tác. Vai trò phụ thuộc điều mà test khẳng định, không phụ thuộc tên API.
- PostgreSQL trong Testcontainers vẫn là **PostgreSQL thật**, chỉ khác nơi triển khai. Một fake repository bằng map là implementation giản lược và không có đặc tính đầy đủ của PostgreSQL.

## 2. Bắt đầu bằng câu hỏi “test cần chứng minh gì?”

Trước khi chọn phụ thuộc, xác định:

1. **Hành vi:** đầu vào hoặc sự kiện nào kích hoạt chức năng?
2. **Kết quả quan sát:** giá trị trả về, trạng thái lưu, HTTP status/body, message hay lời gọi nào cần đúng?
3. **Rủi ro:** tính đúng có liên quan SQL, transaction, serialization, bảo mật, mạng hoặc Spring configuration thật không?
4. **Ranh giới:** kiểm một lớp thuần Java, một slice Spring, nhiều bean, hay toàn hệ thống?
5. **Chi phí:** thay phần nào mà vẫn giữ được tín hiệu lỗi mong muốn?

Từ đó:

- **Giữ thật** logic đang được kiểm. Muốn kiểm `PricingService` thì không mock chính `PricingService`.
- **Stub** đầu vào khi cần dữ liệu hoặc ngoại lệ cố định để kiểm nhánh xử lý.
- **Fake** state khi cần lưu/đọc nhiều lần nhưng hành vi công nghệ lưu trữ không phải trọng tâm.
- **Mock** side effect khi phải chứng minh lệnh được phát ra đúng đối số/số lần.
- **Container** khi semantic của hạ tầng thật là nội dung bài test: query, constraint, migration, transaction isolation, Redis TTL, broker acknowledgement…
- **Spring context thật** khi test dependency injection, AOP, filter chain, validation và các bean framework.

Mục tiêu là **thay ít nhất những thành phần mà việc thay thế sẽ làm mất khả năng phát hiện lỗi**. Không có quy tắc “unit test luôn phải mock repository” hoặc “integration test luôn phải có Docker”.

## 3. Ma trận lựa chọn cho Spring Boot

| Tình huống | Thành phần phải thật | Thay thế hữu ích | Tín hiệu cần assert |
| --- | --- | --- | --- |
| Tính phí, giảm giá, thuế | Domain/service | Stub cấu hình phí, fake catalog | Tổng tiền, invariant |
| Hết hàng không được thu tiền | Checkout service | Fake inventory, mock payment port | Tồn không đổi; gateway không được gọi |
| Gửi một event với key/payload | Service tạo event | Mock publisher | Một lời gọi đúng tham số |
| MVC binding, JSON, validation, exception mapping | Controller và web MVC pipeline | `@WebMvcTest`, mock service cộng tác | HTTP status, body, headers |
| Query repository, unique constraint, rollback | Entity/repository, transaction, DB driver | PostgreSQL/MySQL trong container | Dữ liệu/schema/transaction thực |
| Spring `@Transactional`, `@Cacheable`, `@PreAuthorize` | Bean do Spring quản lý và AOP/filter cần thiết | Thay I/O không liên quan nếu được | Hiệu ứng advice và security thực |
| Redis cache expiration hoặc Kafka consumer group | Adapter/driver, Redis/Kafka | Container cùng loại dịch vụ | TTL/ack/order/serialization |
| HTTP đối tác trả 429/500 hoặc JSON lạ | HTTP client, retry/error mapping | HTTP stub server (ví dụ WireMock) | Request thật đến stub server và cách xử lý response |
| Kiểm tra role trong endpoint | Security chain và endpoint | `@WithMockUser` khi chỉ test authorization | 403/200 theo role |
| JWT signature/OIDC discovery | Security chain và token validation | Token thật/identity provider test | Xác thực protocol thật |
| Quy trình đặt hàng xuyên nhiều tầng | Service, repository, adapter liên quan | Container DB, stub server cho bên thứ ba | Trạng thái end-to-end trong phạm vi đã chọn |

**H2 không đồng nhất với PostgreSQL.** H2 là một database thật, nhưng dialect, kiểu dữ liệu, isolation và constraint có thể khác. Nếu mục tiêu kiểm query PostgreSQL, dùng PostgreSQL thật. Tương tự, mock repository không thể chứng minh một query hoặc mapping entity chạy đúng.

## 4. Ví dụ đầy đủ: fake cho tồn kho, mock cho cổng thanh toán

Giả sử `CheckoutService` kiểm tra hàng tồn, tính tiền, gửi yêu cầu thanh toán, rồi trừ tồn kho. Ta cần test nghiệp vụ, chưa cần Spring context, DB hoặc mạng. Fake quản lý số lượng còn lại; mock xác minh lệnh thanh toán.

File `src/test/java/example/CheckoutServiceTest.java` dưới đây tự chứa tất cả các interface/lớp cần cho ví dụ. Chạy được trong dự án Java 17+ đã có JUnit Jupiter và Mockito (ví dụ dùng `spring-boot-starter-test`).

~~~java
package example;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

class CheckoutServiceTest {

    interface Inventory {
        int stockOf(String sku);
        int priceCents(String sku);
        void decrease(String sku, int quantity);
    }

    interface PaymentGateway {
        void charge(int amountCents);
    }

    static final class CheckoutService {
        private final Inventory inventory;
        private final PaymentGateway payment;

        CheckoutService(Inventory inventory, PaymentGateway payment) {
            this.inventory = inventory;
            this.payment = payment;
        }

        void checkout(String sku, int quantity) {
            if (quantity <= 0 || inventory.stockOf(sku) < quantity) {
                throw new IllegalArgumentException("Not enough stock");
            }

            int amount = Math.multiplyExact(inventory.priceCents(sku), quantity);
            payment.charge(amount);
            inventory.decrease(sku, quantity);
        }
    }

    static final class FakeInventory implements Inventory {
        private int stock;

        FakeInventory(int initialStock) {
            this.stock = initialStock;
        }

        private void requireBook(String sku) {
            if (!"BOOK".equals(sku)) {
                throw new IllegalArgumentException("Unknown SKU");
            }
        }

        @Override
        public int stockOf(String sku) {
            requireBook(sku);
            return stock;
        }

        @Override
        public int priceCents(String sku) {
            requireBook(sku);
            return 1_500;
        }

        @Override
        public void decrease(String sku, int quantity) {
            requireBook(sku);
            stock -= quantity;
        }
    }

    @Test
    void chargesOnceAndDecreasesInventory() {
        FakeInventory inventory = new FakeInventory(3);
        PaymentGateway payment = mock(PaymentGateway.class);

        new CheckoutService(inventory, payment).checkout("BOOK", 2);

        assertEquals(1, inventory.stockOf("BOOK"));
        verify(payment).charge(3_000);
    }

    @Test
    void doesNotChargeWhenStockIsInsufficient() {
        FakeInventory inventory = new FakeInventory(1);
        PaymentGateway payment = mock(PaymentGateway.class);

        assertThrows(IllegalArgumentException.class,
                () -> new CheckoutService(inventory, payment).checkout("BOOK", 2));

        assertEquals(1, inventory.stockOf("BOOK"));
        verifyNoInteractions(payment);
    }

    @Test
    void keepsInventoryWhenChargeFails() {
        FakeInventory inventory = new FakeInventory(3);
        PaymentGateway payment = mock(PaymentGateway.class);
        doThrow(new IllegalStateException("Payment rejected"))
                .when(payment).charge(3_000);

        assertThrows(IllegalStateException.class,
                () -> new CheckoutService(inventory, payment).checkout("BOOK", 2));

        assertEquals(3, inventory.stockOf("BOOK"));
        verify(payment).charge(3_000);
    }
}
~~~

Trong module Gradle đã cấu hình `spring-boot-starter-test`:

~~~bash
./gradlew test --tests example.CheckoutServiceTest
~~~

**Kỳ vọng:** ba test đều đạt (Gradle báo `BUILD SUCCESSFUL` nếu toàn bộ cấu hình và điều kiện chạy test hợp lệ); các test không in stdout. Không cần chạy Spring ApplicationContext hoặc Docker.

Giải thích:

- `CheckoutService` chạy **thật**, vì mục đích là kiểm tra logic của nó.
- `FakeInventory` có state và được assert trực tiếp bằng `stockOf`, nên không cần `verify` nội bộ fake. Nó chỉ biết SKU `BOOK`, không giả vờ mô phỏng DB, transaction hoặc concurrency.
- `PaymentGateway` là Mockito mock vì kết quả quan sát cần thiết là lệnh `charge(3_000)`; `verify` mặc định kiểm đúng một lần. Trong test thứ ba, `doThrow` còn dùng cùng mock để **stub một lỗi**.
- Test hết hàng xác minh cả kết quả trạng thái lẫn việc **không gửi lệnh** bằng `verifyNoInteractions`.
- Không dùng `@SpringBootTest` khi chưa cần kiểm wiring hoặc framework behavior.

Nếu chỉ muốn kiểm tồn kho và cố ý bỏ qua tương tác thanh toán, có thể thay gateway bằng stub:

~~~java
PaymentGateway stubPayment = amountCents -> { };
~~~

Stub này trả về bình thường với mọi số tiền, nhưng **không chứng minh lệnh thanh toán được gửi hay gửi đúng**. Khi hợp đồng yêu cầu phát lệnh, mock với assertion rõ ràng phù hợp hơn.

Giới hạn quan trọng: ví dụ chưa xử lý sự cố nhất quán phân tán khi thanh toán thành công nhưng ghi tồn kho thất bại. Rủi ro đó cần thiết kế giao dịch/saga hoặc compensation và các integration test riêng; không thể suy ra từ test thuần Java trên.

## 5. Khi cần dịch vụ thật trong container

Fake/mock thích hợp cho unit test, nhưng không phát hiện được:

- Query không tương thích PostgreSQL, lỗi index, foreign key hoặc unique constraint.
- Entity mapping khác schema thật, migration Flyway/Liquibase hỏng.
- Lỗi JDBC driver, connection pool, transaction boundary và rollback.
- TTL, serialization, locking của Redis.
- Kafka ack/offset/consumer-group behavior, message codec và broker protocol.
- Sai endpoint, header, body, timeout hay retry do giao thức HTTP thật.

Với DB/broker, dùng adapter thật và dịch vụ container. Với HTTP đối tác, tùy mục tiêu có thể dùng HTTP stub server để kiểm request/response qua network mà vẫn kiểm soát phản hồi; chỉ gọi dịch vụ sandbox thật khi cần xác minh hợp đồng phía đối tác.

### Ví dụ Testcontainers + JDBC với PostgreSQL

Ví dụ sau áp dụng cho Spring Boot 3.x có `@ServiceConnection` (từ 3.1). Dự án phải có `@SpringBootApplication` để Spring test tìm cấu hình trong cùng nhánh package, Docker tương thích Testcontainers, `spring-boot-starter-jdbc`, `spring-boot-starter-test`, `spring-boot-testcontainers`, `org.testcontainers:junit-jupiter`, `org.testcontainers:postgresql` và JDBC driver PostgreSQL. Quản lý version theo BOM tương thích Spring Boot.

File `src/test/java/example/PostgresJdbcTest.java`:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.jdbc.core.JdbcTemplate;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;

@JdbcTest
@Testcontainers
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
class PostgresJdbcTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void executesPostgresArrayOperator() {
        Boolean result = jdbc.queryForObject(
                "SELECT ARRAY[1, 2, 3] @> ARRAY[2]", Boolean.class);

        assertEquals(Boolean.TRUE, result);
    }
}
~~~

~~~bash
./gradlew test --tests example.PostgresJdbcTest
~~~

**Vai trò của các thành phần:**

- `@JdbcTest` dựng một Spring slice cho JDBC; không cần toàn bộ web application.
- `@AutoConfigureTestDatabase(replace = NONE)` ngăn Spring tự đổi datasource thành database nhúng.
- `@Testcontainers` và `@Container` quản lý vòng đời PostgreSQL container.
- `@ServiceConnection` chuyển connection details của container vào Spring Boot mà không phải hardcode host/port.
- `JdbcTemplate` thật phát câu SQL với toán tử mảng `@>` của PostgreSQL, giúp phát hiện khác biệt dialect mà fake/H2 có thể không biểu diễn được.

Đây là bài test **kết nối và đặc điểm SQL**, chưa kiểm repository nghiệp vụ. Để kiểm `OrderRepository`, giữ repository thật, áp dụng schema/migration của ứng dụng, ghi dữ liệu và assert kết quả, constraint hoặc rollback có ý nghĩa. Nếu chưa dùng `@ServiceConnection`, có thể đăng ký `spring.datasource.url`, username, password bằng `@DynamicPropertySource` lấy giá trị động từ container. Không hardcode cổng container.

Nếu môi trường CI không có Docker thì test container có thể thất bại do thiếu hạ tầng; cần phân biệt lỗi khởi động container với lỗi logic ứng dụng.

## 6. Chọn tầng test hợp lý trong Spring Boot

| Tầng | Phần chạy thật | Phần thường thay | Mục đích |
| --- | --- | --- | --- |
| **Unit test** | Service/domain thuần Java | Stub/fake/mock ở interface phụ thuộc | Nhánh nghiệp vụ, edge case, lời gọi bắt buộc |
| **Slice test** | Một phần framework: `@WebMvcTest`, `@JsonTest`, `@JdbcTest`, `@DataJpaTest` | Bean ngoài slice; DB thật khi cần | Binding, JSON, Spring Data mapping, HTTP contract |
| **Integration test** | Nhiều bean, transaction, security, adapter | Container cho hạ tầng; stub server cho đối tác | Wiring, cấu hình, protocol, dữ liệu |
| **End-to-end** | Luồng từ client qua các service thực | Hệ ngoài không thuộc phạm vi test | Kịch bản thiết yếu xuyên hệ thống |

Ghi nhớ về annotation:

- `@Mock` với MockitoExtension hoặc gọi `mock(...)` trực tiếp dành cho unit test, không cần Spring ApplicationContext.
- Trong một Spring test context, muốn **thay bean đã inject**, Spring Boot đến 3.3 thường dùng `@MockBean`. Từ Spring Boot 3.4, `@MockBean` bị deprecate để thay bằng `@MockitoBean` của Spring Framework; Spring Boot 4 loại API cũ. Đọc version và import của module trước khi sử dụng.
- `@WebMvcTest` thường tập trung controller, request binding và MVC infrastructure; mock service ở ranh giới khi service không phải mục tiêu. Muốn kiểm full filter chain hay server integration cần phạm vi tương ứng.
- `@WithMockUser` giúp test authorization theo role với identity mô phỏng; nó **không** kiểm chữ ký JWT, token expiry hoặc OIDC discovery thật.

Số lượng bài test nên phản ánh rủi ro: nhiều unit test nhỏ cho nhánh nghiệp vụ; integration test chọn lọc tại database, security, messaging, serialization; ít end-to-end cho các luồng quan trọng. Chạy nhiều Spring context chỉ vì “test có chất lượng hơn” thường không tạo thêm bằng chứng tương xứng.

## 7. Quy trình quyết định lặp lại được

Đối với mỗi collaborator của đối tượng được kiểm thử:

1. **Nó chứa logic hoặc cơ chế phải chứng minh?** Giữ implementation thật.
2. **Chỉ cần trả giá trị/lỗi được chọn trước?** Dùng stub, kể cả phản hồi rỗng hoặc ngoại lệ đã lập trình.
3. **Cần state đơn giản qua nhiều thao tác?** Dùng fake nhỏ, có hợp đồng rõ và dữ liệu độc lập theo test.
4. **Việc gọi phụ thuộc là một kết quả nghiệp vụ?** Dùng mock; `verify` đúng đối số/số lần thực sự quan trọng.
5. **Lỗi nằm ở SQL/schema/transaction/protocol/config của hệ ngoài?** Dùng adapter thật với container hoặc endpoint thử nghiệm phù hợp.
6. **Có cần so sánh hành vi fake với adapter thật?** Thêm contract/integration test để fake không trôi khỏi hợp đồng.
7. **Bài test có thể lặp lại trên máy local và CI?** Cố định clock/random/fixture, tránh shared mutable state và port hardcode.

Ví dụ cùng `OrderRepository` có hai cách dùng hoàn toàn hợp lý: trong `OrderServiceTest`, fake repository giúp kiểm quy tắc đặt hàng; trong `OrderRepositoryIT`, repository và PostgreSQL đều phải thật để kiểm query và transaction. Chúng chứng minh hai điều khác nhau.

## 8. Lỗi thường gặp

**Mock chính thứ cần test.** Nếu mock `OrderService` rồi assert kết quả trả về đã stub, test không chứng minh hành vi của `OrderService`. Hãy giữ thật SUT (system under test).

**Mock quá sâu.** Mock controller, service, mapper, repository và domain object khiến bài test chỉ diễn lại kịch bản đã lập trình. Ưu tiên object thật cho logic nội bộ, test double ở ranh giới I/O.

**Verify mọi lời gọi nội bộ.** `verify(repository).save(...)` có thể làm test hỏng sau một refactor hợp lệ dù kết quả vẫn đúng. Khi trạng thái/response quan sát được, ưu tiên assert chúng; verify khi lời gọi bản thân là hợp đồng.

**Tin fake giống database.** Fake `HashMap` không tự enforce foreign key, unique constraint, locking và rollback. Không suy ra tính đúng của SQL từ unit test với fake.

**Stub che lỗi mạng.** Khi mock HTTP client và trả DTO đã parse, bạn không test URL, method, header, JSON, status mapping hay retry. Dùng stub server trên đường HTTP để kiểm protocol ở mức cần thiết.

**Thay bean khiến mất AOP.** Nếu mục tiêu là `@Transactional`, `@Cacheable`, `@Retryable` hoặc security advice, đừng mock bean hoặc `new` object bên ngoài context rồi kết luận cơ chế Spring hoạt động.

**Dùng container cho mọi test.** Container có chi phí khởi động và lệ thuộc Docker. Chỉ dùng khi semantic thật là mục tiêu; giữ fixture gọn, dọn dữ liệu, quản lý vòng đời và isolation hợp lý.

**Test không quyết định được.** Đồng hồ thật, random seed không cố định, `Thread.sleep`, cổng cố định, dữ liệu chung và phụ thuộc thứ tự test làm suite flaky. Inject `Clock`, cố định seed, chờ theo điều kiện có timeout, dùng cổng động và fixture cô lập.

**Nhầm pass với đủ bằng chứng.** Unit test với mock/fake chứng minh logic dưới giả định về collaborator; integration test xác minh một số kết nối thật; end-to-end và kiểm thử vận hành có phạm vi khác. Mỗi test phải nêu rõ ranh giới.

## 9. Checklist trước khi hoàn tất

- [ ] Tên test mô tả hành vi quan sát được, assertions kiểm đúng kết quả mong muốn.
- [ ] Thành phần chứa logic cần kiểm chạy thật.
- [ ] Mỗi stub/fake/mock có lý do cụ thể và không làm mất tín hiệu lỗi cần tìm.
- [ ] Fake chỉ mô phỏng các invariant nhỏ đã nêu; những invariant thuộc DB/broker có test thật.
- [ ] Mock chỉ verify những tương tác là hợp đồng, không phụ thuộc chi tiết triển khai không cần thiết.
- [ ] Test query/schema/transaction/protocol chạy trên công nghệ thật nếu đó là rủi ro chính.
- [ ] Spring Boot annotations và dependencies tương thích version module.
- [ ] CI có Docker nếu cần Testcontainers; data và port được cô lập.
- [ ] Suite bao phủ cả lỗi nghiệp vụ lẫn lỗi kết nối ở các ranh giới quan trọng.

**Gợi nhớ:** *real* cho hành vi cần kiểm; *stub* cho đầu vào có kiểm soát; *fake* cho trạng thái giản lược; *mock* cho tương tác bắt buộc; *container* cho đặc tính thật của dịch vụ hạ tầng. Luôn chọn dựa trên lỗi bạn muốn bài test phát hiện.

### Tài liệu tham khảo

- Martin Fowler, [Test Double](https://martinfowler.com/bliki/TestDouble.html) — thuật ngữ fake, stub, mock, spy.
- [Spring Framework: `@MockitoBean` và `@MockitoSpyBean`](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html) — ghi đè bean trong Spring tests.
- [Spring Framework: `@DynamicPropertySource`](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-dynamicpropertysource.html) — đăng ký property động trong integration tests.
- [Spring Boot 3.4 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes) — deprecation của `@MockBean`.

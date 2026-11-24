# Kiểm soát thời gian, mã định danh và nguồn dữ liệu động

## Mục tiêu bài học

Trong **Spring Cloud Contract**, hợp đồng **Groovy DSL** hoặc **YAML DSL** mô tả hành vi HTTP/thông điệp mà **producer** cam kết với **consumer**. Công cụ sinh kiểm thử phía producer, đóng gói stub để consumer chạy bằng **Stub Runner**, và các bước này thường được tích hợp vào CI nhằm phát hiện thay đổi API không tương thích.

Một thách thức thực tế là producer có thể sử dụng **thời gian hiện tại**, **mã định danh tự sinh**, **dữ liệu trong database**, **random**, **thông tin từ dịch vụ ngoài** hoặc trạng thái của một hàng đợi. Nếu generated test không kiểm soát những nguồn này, cùng một hợp đồng có thể PASS hôm nay và FAIL ngày mai dù producer không thay đổi. Ngược lại, nếu sửa contract theo giá trị mới mỗi lần chạy, ta có nguy cơ biến cam kết thành một phép kiểm tra vô nghĩa.

Phần lớn cách giải quyết nằm ở **base test class**, cấu hình test và fixture được điều khiển có chủ đích; không nên nhét dữ liệu production hoặc logic ngẫu nhiên vào tệp contract.

Sau bài học, bạn có thể:

- Phân biệt **hành vi công khai cần cam kết** với **nguồn dữ liệu động dùng để tạo hành vi ấy**.
- Dùng `java.time.Clock` và một abstraction sinh ID để làm test ổn định mà không đổi API production.
- Chuẩn bị và dọn dẹp fixture, tránh test phụ thuộc thứ tự chạy hoặc dữ liệu của lần chạy trước.
- Viết hợp đồng Groovy/YAML với ví dụ xác định, đồng thời biết khi nào nên dùng matcher cho giá trị động.
- Kiểm thử thời điểm hết hạn, múi giờ, độ chính xác timestamp và mã định danh được sinh nhiều lần.
- Hiểu giới hạn của producer tests, stubs và consumer tests khi xác nhận tương thích.

## 1. Nhận diện dữ liệu động trước khi viết hợp đồng

Giả sử Checkout gọi POST /api/orders và producer trả:

~~~json
{
  "orderId": "ORD-9001",
  "status": "CREATED",
  "createdAt": "2026-01-15T08:00:00Z"
}
~~~

`orderId` và `createdAt` có thể thay đổi ở lần gọi tiếp theo:

- ID có thể được tạo bởi bộ sinh mã, UUID hoặc database.
- Timestamp có thể đến từ đồng hồ hệ thống.
- Trạng thái có thể phụ thuộc fixture hoặc một hệ thống thanh toán bên ngoài.
- Dữ liệu response có thể phụ thuộc một service khác, message broker hay cache.

Nếu dùng nguyên response hiện tại làm kỳ vọng tuyệt đối mà không kiểm soát nguồn dữ liệu, generated test dễ trở nên không ổn định.

| Nguồn biến động | Triệu chứng thường gặp | Công cụ/chiến lược kiểm soát |
| --- | --- | --- |
| `Instant.now()`, `LocalDateTime.now()` | Thời gian khác ở mỗi lần chạy | Inject `Clock` hoặc abstraction thời gian |
| `UUID.randomUUID()`, auto-increment DB | ID khác, dễ va chạm fixture | Inject ID generator; dùng sequence/fixture test |
| Random và dữ liệu giả lập | Một lần PASS, lần khác FAIL | Seed có kiểm soát, fixture cố định; hạn chế random trong contract |
| Database dùng chung | Test phụ thuộc trạng thái và thứ tự | Transaction/cleanup/seed riêng cho từng test |
| Service HTTP/broker ngoài | Phụ thuộc mạng, latency và dữ liệu môi trường | Test doubles tại biên hoặc môi trường tích hợp cách ly |
| Cache và trạng thái tiến trình | Test chạy đơn lẻ PASS, chạy toàn bộ FAIL | Reset hoặc tạo context/namespace riêng |
| Múi giờ, locale, format | So sánh thời gian/tiền tệ sai trên CI | Chọn zone/locale rõ ràng và chuẩn hóa serialization |

**Nguyên tắc:** nếu một giá trị thay đổi chỉ vì test chạy vào thời điểm hoặc máy khác, phải xem lại cách tạo fixture/kỳ vọng. Nhưng nếu giao diện thực sự cho phép giá trị thay đổi, hợp đồng cũng không nên buộc producer trả một hằng không thuộc cam kết.

## 2. Phân chia trách nhiệm: contract, base test và producer

Ba thành phần cần được tách biệt:

| Thành phần | Trách nhiệm |
| --- | --- |
| **Contract DSL** | Khai báo request/response hoặc message, mã trạng thái, kiểu, các quy tắc và giá trị ví dụ quan sát được |
| **Base test class / test configuration** | Khởi tạo test client, thiết lập Clock/ID generator, tạo và dọn fixture, mock dependency ở ranh giới phù hợp |
| **Producer implementation** | Thực sự xử lý input và tạo output; cần được generated tests kiểm chứng |

Sơ đồ thực thi:

~~~mermaid
flowchart TD
    A["Contract Groovy/YAML<br/>cam kết hành vi"] --> B["Spring Cloud Contract"]
    B --> C["Generated producer tests"]
    B --> D["Stub/mapping"]
    E["Base test class<br/>Clock, ID generator, fixture"] --> C
    C --> F["Gọi producer đang kiểm thử"]
    F --> G["Assert response/message"]
    D --> H["Consumer chạy Stub Runner"]
    H --> I["Test logic của consumer"]
~~~

Base test **không thay thế producer**. Nó tạo trạng thái và đầu vào có thể kiểm soát để phép thử thực sự gọi phần giao diện cần xác minh. Nếu base test chỉ trả lại một response mock đã giống hệt contract mà không đi qua logic cần kiểm tra, kết quả PASS có thể không chứng minh được hành vi producer.

## 3. Vì sao không nên gọi đồng hồ tĩnh ở mọi nơi?

Ví dụ một service trực tiếp đọc thời gian:

~~~java
public final class OrderService {
    public OrderReceipt createOrder(CreateOrderCommand command) {
        String id = java.util.UUID.randomUUID().toString();
        java.time.Instant time = java.time.Instant.now();
        // Lưu đơn hàng và trả về receipt...
        return new OrderReceipt(id, time, "CREATED");
    }
}
~~~

Đây là **phác thảo** để thấy vấn đề, không phải một service hoàn chỉnh. Test khó quyết định trước `id` và `time`; việc mock toàn bộ đồng hồ hệ thống ở mức global cũng có thể ảnh hưởng test khác.

Thiết kế dễ kiểm thử hơn là đưa nguồn biến động thành **dependency**:

~~~java
import java.time.Clock;
import java.time.Instant;

public interface OrderIdGenerator {
    String nextId();
}

public final class OrderService {
    private final Clock clock;
    private final OrderIdGenerator ids;

    public OrderService(Clock clock, OrderIdGenerator ids) {
        this.clock = clock;
        this.ids = ids;
    }

    public OrderReceipt createOrder(CreateOrderCommand command) {
        String newId = ids.nextId();
        Instant createdAt = Instant.now(clock);
        // Validate command, lưu dữ liệu và công bố kết quả...
        return new OrderReceipt(newId, createdAt, "CREATED");
    }
}
~~~

`OrderIdGenerator` là **interface do ứng dụng tự thiết kế**, không phải lớp Spring Cloud Contract cung cấp. `OrderReceipt` và `CreateOrderCommand` là các kiểu miền nghiệp vụ minh họa.

Điểm cần nhớ:

- `Instant.now(clock)` đọc thời gian thông qua Clock được inject.
- `ids.nextId()` lấy ID qua giao diện có thể thay implementation trong test.
- Production vẫn có thể dùng đồng hồ thật và bộ sinh ID phù hợp yêu cầu bảo mật/độc nhất.
- Generated producer tests có thể chạy với dependency test có kết quả xác định.

**Không nên để logic production chuyển sang dùng ID dễ đoán chỉ để test dễ viết.** Abstraction giúp test thay nguồn dữ liệu, không làm thay đổi yêu cầu bảo mật của hệ thống thật.

## 4. Chọn Clock cố định cho một tình huống hợp đồng

Trong Java:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock testClock = Clock.fixed(
    Instant.parse("2026-01-15T08:00:00Z"),
    ZoneOffset.UTC
);

Instant createdAt = Instant.now(testClock);
// createdAt luôn là 2026-01-15T08:00:00Z
~~~

`Clock.fixed` giúp cùng một request tạo cùng timestamp trong các lần chạy test. Đây là lựa chọn phù hợp với các kịch bản cần **trạng thái thời gian cố định**.

So với việc gọi `Instant.now()` trực tiếp:

| Cách dùng | Hệ quả kiểm thử |
| --- | --- |
| `Instant.now()` | Phụ thuộc đồng hồ hệ thống, khó so sánh với expected cố định |
| `Instant.now(clock)` với `Clock.systemUTC()` | Vẫn là thời gian thật nhưng đã có điểm thay thế dependency |
| `Instant.now(clock)` với `Clock.fixed(...)` | Kết quả xác định, phù hợp fixture/test có timestamp cố định |
| Clock có thể điều chỉnh trong test | Có thể thử trước/sau hạn, nhưng phải reset và tránh state chia sẻ |

Đồng hồ cố định không tự giải quyết mọi trường hợp. Nếu một kịch bản cần **thời gian trôi qua**, ví dụ đơn hàng hết hạn sau 15 phút, một Clock luôn cố định không cho phép quan sát sự thay đổi trừ khi test thay Clock hoặc dùng Clock có thể dịch chuyển.

## 5. Cấu hình Clock và ID generator ở base test class

Đối với producer dùng Spring Boot, có thể đưa các dependency xác định vào **test configuration**, rồi khởi tạo HTTP test client trong base test class.

Ví dụ **khung thiết lập tham khảo** (tên các lớp miền nghiệp vụ là minh họa, cần phù hợp dự án thật):

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@Import(OrderContractBase.DeterministicTestBeans.class)
public abstract class OrderContractBase {

    @Autowired
    private MockMvc mockMvc;

    @BeforeEach
    void prepare() {
        RestAssuredMockMvc.mockMvc(mockMvc);
        // Seed dữ liệu tổng hợp trong database test,
        // reset cache / trạng thái phụ thuộc nếu cần.
    }

    @TestConfiguration
    static class DeterministicTestBeans {

        @Bean
        @Primary
        Clock contractClock() {
            return Clock.fixed(
                Instant.parse("2026-01-15T08:00:00Z"),
                ZoneOffset.UTC
            );
        }

        @Bean
        @Primary
        OrderIdGenerator contractOrderIds() {
            return () -> "ORD-TEST-9001";
        }
    }
}
~~~

Ví dụ trên thể hiện **ý tưởng cấu hình**, không phải một dự án build hoàn chỉnh. Nó giả định ứng dụng đã có `OrderIdGenerator`, các dependency cần thiết và được cấu hình để generated tests thực sự sử dụng base class này. Tên method/annotation, cách inject clock, test mode và dependencies phải phù hợp phiên bản Spring Boot/Spring Cloud Contract.

Một số chú ý thực hành:

1. `@Primary` chỉ có tác dụng khi dependency injection thực sự lấy bean thuộc kiểu đó. Nếu service gọi `Instant.now()` trực tiếp hoặc tự `new` bộ sinh ID, bean test không kiểm soát được hành vi.
2. Nếu bean production được inject bằng `@Qualifier` hoặc có cấu hình condition riêng, phải thiết kế test override phù hợp; không mặc định `@Primary` sẽ thắng mọi cơ chế chọn bean.
3. `OrderIdGenerator` giả lập **luôn trả cùng một ID** chỉ phù hợp kịch bản tạo một bản ghi. Khi chạy nhiều request trong cùng test, nó có thể gây lỗi trùng khóa và cần thay bằng sequence có thể reset.
4. Cần đảm bảo HTTP framework mà Verifier sinh test tương thích với setup của base class. Ví dụ trên dùng Rest Assured Mock MVC; test sinh theo WebTestClient hoặc cơ chế khác phải cấu hình tương ứng.
5. `@TestConfiguration` và test fixture không được đưa vào runtime production.

## 6. Chuẩn bị và dọn dữ liệu trước mỗi generated test

Clock và ID generator mới chỉ giải quyết hai nguồn biến động. Một generated test còn phụ thuộc vào dữ liệu nền:

~~~text
Trước test:
  - Test database sạch hoặc được cô lập
  - Có khách hàng giả CUS-TEST-1001
  - Có cấu hình giá/thuế mẫu cần thiết
  - Clock = 2026-01-15T08:00:00Z
  - Bộ sinh ID theo quy tắc của scenario

Test:
  POST /api/orders
  Expect 201 với orderId và createdAt đã định

Sau test:
  - Dọn dữ liệu/rollback nếu phù hợp
  - Reset cache, sequence, message state
~~~

Đối với test GET /api/orders/ORD-TEST-9001, fixture nên tạo bản ghi trước khi request chạy. Đối với test POST tạo đơn, fixture thường tạo khách hàng/sản phẩm nền, còn producer cần **tự thực hiện thao tác tạo đơn**, để test có ý nghĩa.

Những kỹ thuật có thể chọn:

- **Transaction/rollback** cho các test đồng bộ có thể chạy trong cùng transaction. Chú ý request chạy qua HTTP server hoặc luồng khác **có thể không tham gia** transaction của test method.
- **Database riêng cho test**, ví dụ database container được khởi tạo theo pipeline.
- **Cleanup bằng repository hoặc SQL** theo đúng ranh giới dữ liệu test, rồi seed trạng thái cần thiết.
- **Namespace/key riêng** khi dùng Redis, cache hoặc các tài nguyên ngoài database.
- **Phương thức reset** cho fake clock, fake ID generator và fake publisher nếu chúng giữ state.

Không dùng database production làm nguồn fixture. Hợp đồng và stub có thể được lưu/lan truyền trong repository/artifact, do đó phải dùng ID, email và dữ liệu **tổng hợp**.

## 7. Contract Groovy DSL kết hợp với fixture xác định

Giả sử POST /api/orders của Order Service cần nhận một đơn hàng mẫu và trả ID/timestamp từ các dependency đã được kiểm soát.

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description "Tạo đơn hàng với dữ liệu thời gian và ID ổn định"

    request {
        method POST()
        url "/api/orders"
        headers {
            contentType(applicationJson())
        }
        body(
            customerId: "CUS-TEST-1001",
            items: [
                [sku: "SKU-TEST-BOOK", quantity: 2]
            ]
        )
    }

    response {
        status 201
        headers {
            contentType(applicationJson())
        }
        body(
            orderId: "ORD-TEST-9001",
            status: "CREATED",
            createdAt: "2026-01-15T08:00:00Z"
        )
    }
}
~~~

Kết nối giữa ba thành phần:

- **Contract** định nghĩa input và output mong muốn.
- **Base test** thiết lập Clock, ID generator và dữ liệu test sao cho producer có thể thực thi tình huống đó.
- **Generated producer test** gửi request và xác minh response thật.

Nếu test FAIL vì timestamp sai, không nên sửa contract theo thời gian chạy hiện tại. Trước hết hãy kiểm tra producer có lấy thời gian từ Clock được inject, formatter có dùng UTC, và fixture có được reset đúng hay không.

### YAML DSL cho cùng kịch bản

~~~yaml
description: "Tạo đơn hàng với dữ liệu thời gian và ID ổn định"
name: create_order_with_fixed_clock
request:
  method: POST
  url: /api/orders
  headers:
    Content-Type: application/json
  body:
    customerId: "CUS-TEST-1001"
    items:
      - sku: "SKU-TEST-BOOK"
        quantity: 2
response:
  status: 201
  headers:
    Content-Type: application/json
  body:
    orderId: "ORD-TEST-9001"
    status: CREATED
    createdAt: "2026-01-15T08:00:00Z"
~~~

Hai phiên bản trên minh họa **cùng một hợp đồng**, không có yêu cầu phải đặt đồng thời cả hai vào thư mục contract của producer: nếu nạp cả hai, công cụ có thể sinh hai scenario trùng nhau.

Khi áp dụng vào dự án thật, cần quyết định dùng một trong hai DSL hoặc có lý do rõ ràng để giữ các scenario khác nhau. Không lấy việc test PASS trong YAML hay Groovy làm bằng chứng rằng Clock của production đã được cấu hình đúng; đó là bằng chứng cho **bản producer đang được test cùng setup tương ứng**.

## 8. Khi không thể cố định ID: dùng matcher có chủ đích

Một số hệ thống bắt buộc ID được tạo từ database hoặc một dịch vụ định danh và không dễ override ở cấp test. Khi đó hợp đồng có thể quy định **định dạng đầu ra** thay vì một giá trị cố định.

Ví dụ response dùng giá trị hai phía trong Groovy DSL:

~~~groovy
response {
    status 201
    headers {
        contentType(applicationJson())
    }
    body(
        orderId: value(
            consumer("ORD-TEST-9001"),
            producer(regex("ORD-[A-Z0-9-]+"))
        ),
        status: "CREATED"
    )
}
~~~

**Trong response**:

- Stub có thể trả giá trị mẫu `ORD-TEST-9001` cho consumer.
- Generated producer test có thể xác minh ID mà producer tạo phù hợp regex.

Nhưng regex `ORD-[A-Z0-9-]+` là một quy tắc định dạng tương đối rộng. Nó không kiểm tra ID duy nhất, không chứng minh đơn được lưu thành công và không bảo đảm có thể gọi GET ngay sau POST. Nếu những điều đó thuộc cam kết, cần kiểm thử riêng.

Với timestamp động, thường có thể dùng matcher theo định dạng ISO-8601 hoặc một assertion thích hợp về độ lệch thời gian. **Tránh so sánh với `Instant.now()` tại thời điểm assertion mà không có biên sai số rõ ràng**, vì scheduling và serialization có thể làm test chập chờn.

Không dùng matcher quá rộng chỉ để làm test xanh. **Clock xác định** vẫn là lựa chọn tốt nếu cần xác minh **giá trị thời gian chính xác** theo kịch bản nghiệp vụ.

## 9. Kiểm thử thời điểm hết hạn: trước, đúng hạn và sau hạn

Giả sử đơn đặt chỗ hết hạn tại `2026-01-15T08:15:00Z`. Quy tắc nghiệp vụ:

~~~text
ACTIVE  khi now < expiresAt
EXPIRED khi now >= expiresAt
~~~

Các mốc cần kiểm tra:

| Thời gian giả lập | Kết quả kỳ vọng | Mục đích |
| --- | --- | --- |
| 08:14:59Z | ACTIVE | Trước hạn |
| 08:15:00Z | EXPIRED | Đúng thời điểm biên |
| 08:15:01Z | EXPIRED | Sau hạn |

Nếu không kiểm soát Clock, việc chạy test gần mốc chuyển trạng thái dễ cho kết quả không ổn định. Trong test có thể tạo các `Clock.fixed(...)` khác nhau:

~~~java
Instant expiry = Instant.parse("2026-01-15T08:15:00Z");

Clock before = Clock.fixed(
    Instant.parse("2026-01-15T08:14:59Z"),
    ZoneOffset.UTC
);

Clock atBoundary = Clock.fixed(expiry, ZoneOffset.UTC);

Clock after = Clock.fixed(
    Instant.parse("2026-01-15T08:15:01Z"),
    ZoneOffset.UTC
);
~~~

Đối với generated contract tests, có thể dùng các test context/fixture phù hợp cho từng scenario, hoặc một clock có khả năng điều chỉnh nếu cần test nhiều trạng thái trong cùng phiên test. **Không được mặc định rằng một `@Bean Clock.fixed` chung đủ kiểm tra mọi thời điểm biên**.

Nếu dùng clock có state để điều chỉnh:

- Reset về thời điểm ban đầu trước mỗi test.
- Không chia sẻ instance mutable cho các test chạy song song nếu không có cơ chế cách ly.
- Tránh để một test thay clock làm test khác thất bại.
- Ghi rõ chính sách xử lý tại biên: `>` và `>=` có ý nghĩa khác nhau.

## 10. Múi giờ, độ chính xác và kiểu thời gian

Timestamp là nguồn lỗi phổ biến ngay cả khi Clock đã được inject.

| Vấn đề | Sai lệch thường gặp | Cách kiểm soát |
| --- | --- | --- |
| `Instant` so với `LocalDateTime` | Mất thông tin múi giờ, hiểu sai thời điểm | Dùng kiểu thời gian rõ ràng theo contract |
| UTC so với múi giờ hệ thống | Cùng thời điểm nhưng serialize khác offset | Chọn zone cố định, xác định định dạng API |
| Mili-giây so với nano-giây | Assertion chuỗi thất bại vì precision | Chọn đơn vị/truncation theo giao diện |
| DST (giờ mùa hè) | Giờ địa phương không tồn tại hoặc lặp lại ở một số vùng | Dùng `Instant`/`ZoneId` phù hợp, test kịch bản biên nếu nghiệp vụ cần |
| Locale | Tên tháng, chữ số hoặc dấu phân cách khác | Tránh phụ thuộc locale mặc định; định dạng nhất quán |
| `now()` gọi nhiều lần | Hai trường thời gian chênh nhau vài ms | Lấy một `Instant` từ Clock cho cùng nghiệp vụ, tái sử dụng |

Ví dụ:

~~~java
Instant instant = Instant.parse("2026-01-15T08:00:00Z");

// Cùng một thời điểm dưới các offset khác nhau.
String utc = instant.toString();
String plusSeven = instant.atOffset(
    java.time.ZoneOffset.ofHours(7)
).toString();
~~~

Giá trị `2026-01-15T08:00:00Z` và `2026-01-15T15:00:00+07:00` biểu diễn **cùng một thời điểm** nhưng là **hai chuỗi khác nhau**. Nếu hợp đồng cam kết UTC với hậu tố Z, producer phải xuất đúng định dạng đó. Nếu hợp đồng chỉ cam kết cùng một thời điểm có offset hợp lệ, matcher/assertion nên phản ánh quy tắc chứ không khóa cố định cách biểu diễn.

**Quan trọng:** thay Clock không tự cấu hình JSON serializer. Cần xác minh Jackson/date formatter và các DTO thật sự dùng chung định dạng mà consumer chấp nhận.

## 11. Kiểm soát bộ sinh ID khi có nhiều request

Một fake generator luôn trả `ORD-TEST-9001` rất dễ hiểu nhưng có thể lỗi khi test tạo nhiều đơn hàng:

~~~text
POST /api/orders -> ORD-TEST-9001
POST /api/orders -> ORD-TEST-9001  (trùng ID!)
~~~

Đối với kịch bản cần nhiều ID, có thể dùng **sequence test có khả năng reset**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public final class TestOrderIdGenerator implements OrderIdGenerator {
    private final AtomicInteger next = new AtomicInteger(9001);

    @Override
    public String nextId() {
        return "ORD-TEST-" + next.getAndIncrement();
    }

    public void reset() {
        next.set(9001);
    }
}
~~~

Trong base test, trước mỗi generated test có thể gọi `reset()` nếu fake được inject và có lifecycle phù hợp. Nhưng **AtomicInteger chỉ tránh lỗi tăng biến đồng thời**, không tự bảo đảm toàn bộ logic test cách ly giữa các luồng. Nếu nhiều tests song song dùng chung bean sequence, một test có thể lấy ID dự kiến của test khác.

Chiến lược an toàn hơn:

- Mỗi test có fake riêng nếu khả thi.
- Nếu phải dùng shared fake, tắt chạy song song cho các kịch bản phụ thuộc thứ tự hoặc thiết kế namespace riêng.
- Reset generator và xóa bản ghi khi test kết thúc/bắt đầu.
- Không ràng buộc ID theo **thứ tự chạy giữa các test**.

Đối với ID production, tính duy nhất toàn hệ thống, không đoán được và collision resistance là các yêu cầu riêng. Fake generator **không chứng minh** những thuộc tính này; cần test/số liệu phù hợp ở lớp sản phẩm/hạ tầng thật.

## 12. Các nguồn dữ liệu động khác ngoài thời gian và ID

Một bài contract test có thể chập chờn dù Clock và ID đã xác định:

### Database và transaction

Nếu test đọc bản ghi của lần chạy trước, kết quả có thể thay đổi theo thứ tự test. Cần seed dữ liệu và cleanup đúng phạm vi, không dựa vào database cá nhân.

### Cache

Một test thay dữ liệu nguồn nhưng cache vẫn giữ giá trị cũ. Có thể xóa cache, dùng key namespace riêng hoặc test riêng behavior cache nếu đó là cam kết công khai.

### Dịch vụ HTTP bên ngoài

Nếu producer phải gọi Payment Service để tạo đơn hàng, generated producer test không nên phụ thuộc vào một Payment Service production đang thay đổi. Có thể dùng test double ở ranh giới dependency, nhưng vẫn phải đi qua **logic producer** cần kiểm chứng. Nếu mọi thứ đều được mock tới mức response trả ra không qua code xử lý thật, phép thử mất giá trị.

### Message broker và xử lý bất đồng bộ

Một consumer của message có thể nhận event trễ hoặc trùng. Chọn broker/test container và cách chờ có điều kiện, dọn queue/topic theo namespace. **Không thay đồng bộ bất đồng bộ bằng sleep cố định** rồi coi test ổn định; sleep quá ngắn gây flaky, quá dài gây chậm CI.

### Random và thứ tự

Nếu việc sắp xếp danh sách phụ thuộc iteration order của map/set, test có thể nhận thứ tự khác nhau. Chỉ khóa thứ tự khi consumer thực sự cần; nếu API không bảo đảm thứ tự, assertion không nên bắt buộc một thứ tự giả tạo.

### Biến môi trường

Không để hợp đồng phát sinh response khác nhau chỉ vì `CI=true` hay timezone máy chạy. Giá trị môi trường ảnh hưởng behavior phải được mô tả minh bạch hoặc đưa vào cấu hình test cố định có kiểm soát.

## 13. Với message contract, fixture vẫn phải có nguồn gốc xác định

Ví dụ Groovy DSL cho sự kiện sau khi thanh toán:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description "Phát sự kiện thanh toán với dữ liệu test xác định"
    label "order_paid"

    input {
        triggeredBy("publishPaidTestOrder()")
    }

    outputMessage {
        sentTo("order-events")
        body(
            eventType: "ORDER_PAID",
            eventId: "EVT-TEST-0001",
            orderId: "ORD-TEST-9001",
            occurredAt: "2026-01-15T08:00:00Z"
        )
        headers {
            contentType(applicationJson())
        }
    }
}
~~~

Ở đây `publishPaidTestOrder()` là một phương thức cần được cung cấp trong ngữ cảnh generated producer test; nó phải kích hoạt đúng logic producer tạo event. Đây **không** phải lệnh mà consumer Stub Runner sẽ thực thi.

Nếu producer sinh `eventId` hoặc `occurredAt` động, nên kiểm soát Clock và ID generator trong base test, hoặc dùng matcher thích hợp cho message output nếu đó mới là cam kết cần xác minh.

**Không kiểm tra bằng cách đơn thuần tự gửi một message đã đúng format từ base class tới fake broker rồi kết luận producer bảo đảm behavior** nếu logic nghiệp vụ thực tế chưa được kích hoạt. Test phải chứng minh phần giao diện producer cần cam kết trong phạm vi kịch bản.

## 14. Stub Runner không dùng chung Clock và fixture producer

Khi producer contract test chạy với `Clock.fixed`, đó là **dependency của môi trường producer test**, không tự động truyền sang consumer hoặc stub server.

~~~mermaid
sequenceDiagram
    participant P as Producer CI
    participant S as Stub artifact
    participant C as Consumer CI
    P->>P: Inject Clock + ID generator giả lập
    P->>P: Chạy generated producer test
    P->>S: Sinh và phát hành stub từ contract
    C->>S: Stub Runner tải version cụ thể
    C->>S: Gửi request tới stub server
    S-->>C: Trả response theo stub mapping
~~~

Phía consumer:

- Có thể dùng **timestamp/ID mẫu cố định** trong stub response.
- Test logic của consumer xử lý response; ví dụ lưu orderId và điều hướng tới màn hình chi tiết.
- Nếu consumer cần thử nhiều timestamp hoặc trạng thái, thiết kế thêm các hợp đồng/stub scenario rõ ràng.
- Không giả định stub sẽ gọi lại `Clock` hoặc `OrderIdGenerator` của producer khi mỗi request đến.

Một stub trả `ORD-TEST-9001` không chứng minh producer production luôn sinh ID đó. Ngược lại, producer test có thể xác minh ID theo matcher trong khi stub trả một ID mẫu hợp lệ.

**Tuyên bố tương thích** cần gắn với contract revision, producer build, stub artifact và phiên bản consumer thực sự được kiểm tra. PASS ở môi trường fixture không bảo đảm mọi dữ liệu hoặc cấu hình production đều an toàn.

## 15. Tính tái lập và độ tin cậy trong CI

Trước khi đánh dấu tương thích, CI nên xác minh:

1. **Hợp đồng không phụ thuộc thời điểm build:** không dùng `Instant.now()` hoặc UUID random trong Groovy script để âm thầm quyết định expected body.
2. **Base test class được chọn đúng:** generated test kế thừa setup dùng Clock/ID generator test, thay vì chạy với bean production không kiểm soát.
3. **Fixture độc lập:** mỗi test có dữ liệu chuẩn, không phụ thuộc thứ tự chạy và không dùng database production.
4. **Test thực sự được thực thi:** không chỉ có generated source hoặc kết quả build xanh khi contract test bị skip.
5. **Kiểm tra ranh giới động:** hợp đồng/extra tests bao phủ các thời điểm biên, dữ liệu bất hợp lệ và trường hợp nhiều ID nếu consumer phụ thuộc.
6. **Stub đúng phiên bản:** consumer test dùng Stub Runner với artifact được tạo từ đúng contract đã kiểm tra producer.
7. **Báo cáo có nguồn gốc rõ:** ghi commit, build ID, contract revision, test report, version stub và các giới hạn chưa kiểm chứng.

Một mẫu ghi nhận do dự án tự thiết kế:

~~~yaml
# Chỉ minh họa release evidence, không phải cấu hình SCC mặc định.
producer: "order-service:2.4.0"
producer_revision: "commit-abc123"
contract_revision: "contracts-def456"
test_clock: "2026-01-15T08:00:00Z"
id_fixture: "ORD-TEST-9001"
fixture_profile: "isolated-test"
generated_producer_tests: PASS
stub_artifact: "com.example:order-service:2.4.0:stubs"
consumer_stub_tests: PASS
notes:
  - "Kết quả chỉ bao phủ các scenario đã chạy"
  - "Không chứng minh tính duy nhất ID trên production"
~~~

**Không phải CI nào cũng cần cùng một Clock ở tất cả test.** Khi một scenario cần thử thời điểm khác, hãy ghi rõ Clock test đó. Mục tiêu là **có thể tái lập và truy vết**, không phải ép mọi kịch bản vào một thời điểm duy nhất.

## 16. Những sai lầm thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| Test FAIL do timestamp thay mỗi lần | Producer gọi đồng hồ thật; assertion khóa giá trị | Inject `Clock` hoặc dùng matcher đúng cam kết |
| Test PASS local nhưng FAIL CI | Múi giờ, locale hoặc precision khác | Cố định zone/format và đối chiếu JSON serializer |
| Hai test tạo cùng ID | Fake generator luôn trả một giá trị | Dùng sequence reset hoặc fake riêng từng test |
| Test chạy đơn lẻ PASS nhưng chạy suite FAIL | Database/cache/fake clock bị chia sẻ state | Dọn/reset fixture, cách ly hoặc kiểm soát parallelism |
| Producer test FAIL sau khi mock Clock | Service không dùng Clock inject | Thay nguồn đọc thời gian đúng tại production seam |
| Test code so sánh `Instant.now()` với timestamp producer | Scheduling gây sai lệch | Dùng Clock chung hoặc matcher với khoảng sai số rõ |
| CI xanh dù không chạy hợp đồng | Test bị skip hoặc nguồn contract sai | Xác minh số test được sinh và thực thi |
| Consumer Stub Runner trả timestamp cố định | Stub mapping được tạo từ contract, không chạy Clock producer | Thiết kế scenario stub hoặc matcher thích hợp |
| Dùng dữ liệu production để có fixture “thật” | Rò rỉ thông tin, test phụ thuộc trạng thái ngoài | Tạo dữ liệu tổng hợp và database riêng |
| Test chỉ kiểm tra regex ID | Không chứng minh uniqueness/persistence | Thêm test riêng cho thuộc tính đó nếu là yêu cầu |

Khi gặp lỗi, tránh sửa mỗi lần giá trị expected trong hợp đồng theo kết quả build. Hãy xác định **nguồn không ổn định** và giải quyết ở tầng phù hợp.

## 17. Bài tập thực hành

### Bài tập A — Dùng Clock thay thời gian hệ thống

Một service sử dụng `LocalDateTime.now()` để tính thời gian hết hạn. Generated test kỳ vọng cùng một timestamp nhưng FAIL trên CI.

**Yêu cầu:** đề xuất thay đổi thiết kế và base test setup.

**Gợi ý:** inject `Clock`, dùng `Instant.now(clock)` hoặc `LocalDateTime.now(clock)` tùy giao diện, cấu hình Clock cố định và timezone rõ ràng. Đảm bảo JSON serialization giữ định dạng consumer cần.

### Bài tập B — ID sinh nhiều lần

Fake ID generator đang luôn trả `ORD-TEST-9001`. Một kịch bản tạo hai đơn và kiểm tra chúng độc lập.

**Yêu cầu:** viết chiến lược để ID không trùng, nhưng test vẫn tái lập được.

**Gợi ý:** sequence riêng theo test, có reset, ví dụ ORD-TEST-9001 và ORD-TEST-9002; làm rõ chính sách chạy song song và cleanup dữ liệu.

### Bài tập C — Trường hợp biên của hạn sử dụng

Quy tắc một mã giảm giá hết hạn khi `now >= expiresAt`, với `expiresAt = 2026-01-15T08:15:00Z`.

**Yêu cầu:** xây ba scenario trước, đúng và sau thời điểm biên; chỉ ra vì sao một Clock.fixed duy nhất không kiểm chứng hết.

**Gợi ý:** dùng các Clock khác nhau hoặc reset Clock có thể điều chỉnh, rồi đối chiếu status/HTTP response theo từng trường hợp.

### Bài tập D — Producer test và stub dùng dữ liệu khác

Producer test chạy với Clock cố định và ID mẫu. Consumer CI dùng Stub Runner nhưng vẫn kéo một artifact stub từ tháng trước.

**Yêu cầu:** lý giải tại sao các kết quả PASS không đủ để khẳng định tương thích bản mới.

**Gợi ý:** cần sinh/phát hành stub từ cùng contract revision và producer build đã kiểm chứng, chốt version và chạy consumer test với chính artifact đó.

### Bài tập E — Nhận biết mocking quá mức

Base test mock cả controller hoặc HTTP handler trả một JSON đã được chép nguyên từ contract. Generated producer test PASS.

**Yêu cầu:** giải thích nguy cơ và đề xuất ranh giới mock phù hợp hơn.

**Gợi ý:** mock dependency ngoài như payment gateway, nhưng để controller/service xử lý request thật và tạo response cần kiểm chứng; nếu test chỉ gọi một stub phản hồi sẵn, không có bằng chứng về behavior producer.

## 18. Checklist trước khi chấp nhận base test cho dữ liệu động

- [ ] Xác định giá trị nào động và giá trị nào thực sự thuộc cam kết producer–consumer.
- [ ] Producer đọc thời gian qua dependency có thể kiểm soát, ví dụ `Clock`.
- [ ] Bộ sinh ID có giao diện testable và không làm suy yếu ID production.
- [ ] Clock, ID generator và fixture được reset/cách ly đúng lifecycle.
- [ ] Dữ liệu giả lập không lấy từ production hoặc chứa secret.
- [ ] Múi giờ, precision, định dạng timestamp và thời điểm biên được kiểm tra nếu API phụ thuộc.
- [ ] Các scenario nhiều request không vô tình nhận cùng ID hoặc phụ thuộc thứ tự chạy.
- [ ] Mock chỉ ở ranh giới thích hợp; producer logic cần kiểm chứng vẫn được gọi.
- [ ] Hợp đồng Groovy/YAML chứa ví dụ hoặc matcher có ý nghĩa, không chứa random/now phụ thuộc build.
- [ ] Generated producer tests thực sự được sinh, biên dịch và chạy với đúng base class.
- [ ] Stub có nguồn gốc từ cùng contract revision và không giả định chạy mã của base test.
- [ ] Consumer tests qua Stub Runner dùng đúng stub version và có assertion cho logic consumer.
- [ ] CI lưu bằng chứng cùng các giới hạn còn chưa kiểm chứng.

**Ghi nhớ:** Base test trong Spring Cloud Contract có vai trò **kiểm soát điều kiện thực thi để hành vi producer có thể được xác minh lặp lại**. Đồng hồ giả lập, bộ sinh ID test và fixture được cách ly không phải thủ thuật “làm test xanh”, mà là cách loại bỏ nhiễu bên ngoài khỏi phép kiểm tra. Hợp đồng vẫn phải mô tả đúng cam kết; generated producer tests và stub/consumer tests phải cùng dựa trên đúng revision để phát hiện thay đổi API không tương thích.

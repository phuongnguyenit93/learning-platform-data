# Rà soát tác dụng phụ của base test và custom assertion

## Mục tiêu bài học

**Spring Cloud Contract** cho phép producer và consumer mô tả hành vi HTTP hoặc thông điệp bằng **Groovy DSL** hoặc **YAML DSL**, sinh kiểm thử phía producer, tạo stub để consumer dùng qua **Stub Runner** và tích hợp các bước kiểm tra tương thích vào CI. Với hợp đồng có vẻ chỉ đọc một HTTP response, nhiều người nghĩ kiểm thử là thao tác vô hại. Trên thực tế, **base test class**, Spring test context, fixture và **custom assertion/helper** có thể chạy mã có tác dụng phụ: ghi database, gửi request ra mạng, phát message, tạo file, log thông tin nhạy cảm hoặc làm thay đổi trạng thái dùng chung giữa các bài test.

Trong chương **Bảo mật hợp đồng**, bài **“Rà soát tác dụng phụ của base test và custom assertion”** tập trung vào một nguyên tắc:

> **Kiểm thử hợp đồng phải đủ thực để chứng minh hành vi producer, nhưng phải được giới hạn quyền, cô lập tác dụng phụ và không làm rò rỉ thông tin khi chạy trong CI.**

Sau bài học, bạn có thể:

- Phân biệt **Contract DSL**, **generated tests**, **base test class**, **test fixture** và **custom assertions** theo thời điểm thực thi.
- Lập threat model cho các đường có thể tạo tác dụng phụ, kể cả trong **Spring context startup**.
- Rà soát những lời gọi ra **database, HTTP, broker, file system, cache, scheduler** và dịch vụ thực.
- Giữ custom assertion tập trung vào kiểm tra kết quả, tránh I/O, network và thay đổi state.
- Cấu hình môi trường test cô lập, dữ liệu giả, quyền hạn thấp và các kiểm tra phủ định.
- Phát hiện trường hợp test “PASS” vì mock sai chỗ hoặc vì assertion che giấu lỗi.
- Thiết kế checklist review và CI gate cho HTTP contract, message contract và stub consumer test.

## 1. Hợp đồng, generated test và base test không phải cùng một thứ

Một cấu trúc producer đơn giản có thể trông như sau:

~~~text
order-service/
├── src/test/resources/contracts/orders/get_paid_order.yml
├── src/test/java/com/example/orders/contract/OrderContractBase.java
├── src/main/java/com/example/orders/...
└── pom.xml
~~~

Tệp contract YAML mô tả hành vi:

~~~yaml
description: "Lấy đơn hàng đã thanh toán"
name: get_paid_order
request:
  method: GET
  url: /api/orders/ORD-1001
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: ORD-1001
    status: PAID
~~~

Spring Cloud Contract Maven/Gradle plugin có thể sinh test dựa trên contract, rồi test đó gọi producer theo chế độ đã cấu hình. **Base test class** cung cấp phần setup mà generated test kế thừa hoặc tham chiếu. Những **custom assertions** là phương thức hoặc logic kiểm tra bổ sung, đôi khi được gọi từ generated tests hoặc code test do nhóm viết.

~~~mermaid
flowchart TD
    A["Groovy/YAML contract"] --> B["Contract Verifier<br/>sinh test"]
    A --> C["Chuyển contract thành<br/>stub mappings"]
    B --> D["Generated producer test"]
    E["Base test + fixture + helper"] --> D
    D --> F["Producer implementation<br/>Spring test context"]
    F --> G["DB, outbound HTTP,<br/>broker, cache, filesystem"]
    D --> H["Assertions và test reports"]
    C --> I["Stub JAR / Stub Runner"]
~~~

Điểm cần phân biệt:

| Thành phần | Việc chính | Có thể tạo tác dụng phụ? |
| --- | --- | --- |
| Contract DSL | Đặc tả request/response hoặc input/output message | Có thể, nếu cho phép Groovy code/extension thực thi trong quá trình xử lý |
| Generated producer test | Gọi hành vi được đặc tả và kiểm tra kết quả | Có, vì test kích hoạt code producer |
| Base test class | Tạo Spring context, cấu hình HTTP/message test, setup dữ liệu | **Có**, bao gồm trước và sau từng test |
| Fixture/helper | Chuẩn bị ID, state, dữ liệu giả và dependencies | **Có**, tùy implementation |
| Custom assertion | Kiểm tra điều kiện sau khi gọi producer | **Có nếu được viết như mã có I/O**, không nên mặc định là “read-only” |
| Stub Runner/WireMock | Mô phỏng dependency cho consumer | Có thể thay đổi request journal/scenario state; extensions cũng là code |
| CI runner | Biên dịch và chạy tất cả các thành phần trên | Có thể truy cập những tài nguyên mà job được cấp quyền |

**Mã kiểm thử có cùng khả năng gây tác động như mã Java khác**, trong giới hạn quyền của process chạy nó. Tên class có chữ `Test`, annotation `@BeforeEach` hoặc phương thức `assert...` không tự tạo sandbox bảo mật.

## 2. Threat model: cần bảo vệ tài sản và ranh giới nào?

Trước khi review, hãy xác định:

- **Tài sản cần bảo vệ:** dữ liệu người dùng, production database, cloud storage, queue/topic thật, secrets CI, Maven repository credentials, log và artifact build.
- **Đường thực thi:** quá trình xử lý Groovy contracts; plugin build; Spring context startup; test setup; HTTP/message producer code; assertion; teardown; stub extensions.
- **Nguồn kích hoạt:** PR thay đổi contract/base class/helper, dependency mới, CI configuration, environment variables, test profile hoặc code producer có side effects.
- **Ranh giới tin cậy:** repository code được phép chạy trong CI không đồng nghĩa được phép truy cập production hoặc có quyền publish/deploy.

Một bảng nguy cơ:

| Đường tác dụng phụ | Ví dụ | Hậu quả |
| --- | --- | --- |
| **Outbound HTTP** | Fixture gọi service thật để “lấy dữ liệu mẫu” | Tạo giao dịch thật, lộ metadata, test phụ thuộc mạng |
| **Database** | `@BeforeEach` insert/xóa trên datasource sai | Thay đổi dữ liệu của môi trường dùng chung |
| **Message broker** | `triggeredBy` phát event lên broker staging/production | Consumer thật xử lý event test |
| **Scheduler/background job** | Spring context khởi động job gửi email/thanh toán | Tác động xảy ra dù test chỉ gửi GET |
| **Filesystem** | Assertion ghi file vào thư mục chung, xóa dữ liệu không thuộc test | Mất dữ liệu hoặc CI race |
| **Secrets/logs** | In HTTP Authorization, token hay raw payload | Rò rỉ vào console/artifact reports |
| **Global mutable state** | Test sửa static config, JVM system properties, timezone | Làm kết quả test khác thay đổi |
| **Unsafe TLS config** | Test tắt certificate/hostname verification cho toàn JVM | Che lỗi bảo mật, ảnh hưởng client khác |
| **Custom assertion** | Helper tự gọi API khác để kiểm tra dữ liệu | Kết quả phụ thuộc dịch vụ ngoài, có thể tạo tác động mới |
| **Groovy contract code** | Đoạn script thực thi trong build thay vì DSL khai báo thuần | Mở rộng quyền thực thi theo quyền của CI |

Vì thế “tác dụng phụ” không chỉ là `INSERT` database. **Việc đọc bí mật và log ra nơi không được phép cũng là tác dụng phụ đáng quan tâm**.

## 3. Thời điểm nào base test có thể thực thi mã?

Một test có thể tạo tác dụng phụ **trước khi assertion đầu tiên chạy**.

~~~mermaid
sequenceDiagram
    participant CI as CI job
    participant SC as Spring context
    participant BT as Base test
    participant GT as Generated test
    participant EXT as Database / broker / HTTP
    CI->>SC: Khởi tạo application context
    SC->>EXT: Bean startup / lifecycle / scheduler có thể gọi ngoài
    SC->>BT: Tạo/inject base test
    BT->>EXT: BeforeEach / fixture setup (nếu có)
    GT->>SC: Gửi request hoặc kích hoạt message
    SC->>EXT: Business logic có thể ghi/đọc/phát
    GT->>BT: Gọi custom assertion/helper
    BT->>EXT: Helper có thể I/O nếu viết không an toàn
    BT->>EXT: AfterEach / cleanup (nếu có)
    GT-->>CI: Kết quả PASS/FAIL + logs
~~~

Các điểm cần review:

1. **Static initializer** hoặc constructor của test/base class.
2. `@BeforeAll`, `@BeforeEach`, `@AfterEach`, `@AfterAll`.
3. Spring bean lifecycle: `@PostConstruct`, `ApplicationRunner`, `CommandLineRunner`, listener, scheduler.
4. Test configuration và bean overrides.
5. Test fixture/reset database/cache.
6. Method được gọi từ DSL hoặc generated test.
7. Assertion helper, logging interceptor, RestAssured filters.
8. `@Transactional`, test retries và teardown.
9. Các task bất đồng bộ còn chạy **sau khi test kết thúc**.

**Nguy cơ đặc biệt:** mở Spring context có thể khởi chạy listener hoặc job thực. Test chỉ gửi `GET` không chứng minh toàn bộ quá trình là read-only.

## 4. Thiết kế base test HTTP: kiểm tra controller thật nhưng cô lập dependency ngoài

Một mô hình phổ biến cho HTTP producer contract tests là chạy Spring Boot test context với MockMvc. Ví dụ **minh họa**:

~~~java
package com.example.orders.contract;

import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.AfterEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
public abstract class OrderContractBase {

    @Autowired
    MockMvc mvc;

    @BeforeEach
    void configureContractClient() {
        RestAssuredMockMvc.mockMvc(mvc);
    }

    @AfterEach
    void clearContractClient() {
        RestAssuredMockMvc.reset();
    }
}
~~~

Đoạn này giả định producer sử dụng **Spring MVC** và generated tests được cấu hình tương thích với **RestAssuredMockMvc**; package, dependencies, lifecycle và base class mapping phải khớp phiên bản Spring Cloud Contract/Spring Boot của dự án. Nếu dùng WebFlux hoặc test mode khác, cần setup tương ứng chứ không sao chép ví dụ này một cách máy móc.

**Điểm bảo mật quan trọng:** `webEnvironment = MOCK` không mở HTTP server thật, nhưng **không chặn tự động outbound HTTP, DB hoặc broker** do bean producer gọi. MockMvc chỉ mô phỏng ranh giới HTTP inbound; các phụ thuộc nội bộ vẫn cần cô lập.

### Thiết kế tốt: mock ở biên hệ thống

Ví dụ controller Order gọi service, service gọi một **external payment gateway**. Để bảo vệ môi trường test:

- Giữ controller/service path quan trọng **được thực thi thật**.
- Thay client đi tới payment gateway thật bằng một **fake/recording client** trong test profile.
- Sử dụng database/schema **dành riêng cho test** hoặc test DB container.
- Ngăn scheduler/email sender/broker producer ngoài phạm vi test phát đi sự kiện thật.
- Bảo đảm setup dữ liệu không gọi API public để “tạo đơn mẫu”.

Nếu mock trực tiếp method HTTP controller để trả JSON đã hardcode, producer test có thể PASS trong khi implementation thật trả response khác. Mục tiêu là **cô lập tài nguyên nguy hiểm ở ranh giới ra ngoài**, không mock hết hành vi cần được kiểm chứng.

## 5. Cẩn trọng với các annotation và transaction tưởng là “an toàn”

Một số annotation rất hữu ích nhưng **không phải ranh giới bảo mật tuyệt đối**:

| Cơ chế | Nó thường làm gì? | Không bảo đảm điều gì? |
| --- | --- | --- |
| `@SpringBootTest` | Khởi tạo application context cho test | Không tự chặn network, scheduler, broker, DB thật |
| `webEnvironment = MOCK` | Dùng mock web environment thay vì HTTP server thật | Không cô lập outbound HTTP hoặc bean startup |
| `@Transactional` trên test | Có thể rollback DB thay đổi cùng transaction của test | Không rollback transaction khác thread, request server thật hoặc message đã publish |
| `@DirtiesContext` | Yêu cầu làm mới Spring context | Không hoàn tác tác dụng phụ ở hệ thống ngoài |
| Mockito mocks/test fakes | Thay một dependency theo cấu hình | Không tự ngăn các bean khác gọi production |
| `@Sql` setup/cleanup | Chạy SQL theo script test | Nguy hiểm nếu datasource trỏ sai DB hoặc cleanup quá rộng |
| Testcontainers | Khởi chạy tài nguyên test cô lập | Không tự cấm code gọi URL khác hoặc dùng credentials production |
| `@ActiveProfiles("test")` | Chọn profile/test configuration | Không bảo đảm mọi property nguy hiểm được override |

### Giới hạn của rollback

Ví dụ một test có `@Transactional` gọi producer qua HTTP server thật ở cổng ngẫu nhiên. Request được xử lý ở thread/transaction khác với test method. Rollback của transaction test **không chắc rollback** database writes từ thread xử lý HTTP đó.

Tương tự, một message đã được gửi vào broker ngoài test **không thể được hoàn tác** bằng rollback database.

**Quy tắc:** trước khi dựa vào `@Transactional` hoặc teardown, xác minh rõ **đường thực thi, thread và transaction boundary** của hành vi cần cô lập.

## 6. Thiết lập dữ liệu test: deterministic, idempotent và có phạm vi

Một fixture an toàn nên:

- Tạo dữ liệu trong **datasource test** được kiểm tra rõ trước khi ghi.
- Dùng ID tổng hợp có namespace: `CONTRACT-ORD-1001`, `TEST-CORR-1001`.
- Không dùng email/địa chỉ/token người dùng thật.
- Có thể chạy lại mà không phụ thuộc kết quả của job trước.
- Chỉ xóa dữ liệu thuộc sở hữu test, không chạy lệnh dọn toàn bộ bảng/hệ thống dùng chung.
- Quản lý transaction, cleanup và bất đồng bộ có chủ đích.
- Có timeout khi chờ event hoặc eventual consistency.

Ví dụ pseudocode:

~~~text
BeforeEach:
    assert effectiveEnvironment == ISOLATED_TEST
    seed order with ID "CONTRACT-ORD-1001" into test database
    clear only this test's recorded outbound calls

Generated producer test:
    GET /api/orders/CONTRACT-ORD-1001
    assert 200 and agreed JSON response

AfterEach:
    remove records whose owner == current test namespace
    verify no unexpected outbound call was recorded
~~~

Đây là **quy trình minh họa**, không phải hàm API có sẵn trong Spring Cloud Contract. Quan trọng nhất là tiền điều kiện `effectiveEnvironment == ISOLATED_TEST` được kiểm tra từ cấu hình thực, không phải một nhãn tự đặt mà hệ thống không sử dụng.

### Tránh reset state vượt phạm vi

Một test dùng chung DB test với các job khác mà chạy `DELETE FROM orders` có thể làm hỏng test đồng thời. Nếu dùng Testcontainers mỗi job hoặc schema riêng theo job, phạm vi cô lập rõ ràng hơn.

Tương tự, không xóa toàn bộ topic hoặc thư mục dùng chung để dọn một scenario. Nên dùng namespace riêng hoặc tạo hạ tầng ngắn hạn cho từng test suite.

## 7. Khóa đường ra mạng của process test

Một hợp đồng HTTP có thể chỉ kiểm tra GET, nhưng Spring context vẫn có thể tạo HTTP client tới payment processor, notification gateway, telemetry endpoint hoặc service discovery.

Mục tiêu review:

1. Kiểm tra **effective base URLs** mà process test nhận từ application properties, system properties và environment.
2. Không cho test sử dụng URL production/staging ngoài danh sách allowlist test.
3. Nếu có thể, dùng môi trường CI với **default-deny egress** và chỉ mở các đích cần thiết.
4. Thay external clients bằng test doubles/MockWebServer/WireMock tương ứng.
5. Ghi lại những outbound calls được phép và assert **không có call bất ngờ**.
6. Bảo đảm retries không vô tình gửi cùng request test tới endpoint thật.
7. Không đặt token production trong CI job của PR không đáng tin.

### Cảnh báo về localhost

`localhost` chỉ an toàn theo ngữ cảnh. Trong CI container, nó trỏ đến chính container đó; trong Docker Compose, WireMock container khác cần service hostname. Một client gọi sai localhost thường thất bại, nhưng nếu có một process khác tình cờ nghe cùng cổng thì test có thể tương tác nhầm.

**Network allowlist và test fixture phải cùng xác định endpoint cuối**, không chỉ rely vào tên property như `test.payment.url`.

### “Network call để assert” có nên dùng không?

Một custom assertion gọi endpoint production `GET /orders/{id}` để kiểm tra “dữ liệu có thật” tạo thêm đường truy cập ra ngoài. Dù gọi GET, nó vẫn có thể:

- Đọc dữ liệu nhạy cảm.
- Gây rate limiting hoặc audit side effects.
- Phụ thuộc availability của môi trường ngoài.
- Phá tính tái lập của test.
- Bị tấn công qua URL được tạo từ dữ liệu test nếu không kiểm soát.

Nếu thực sự cần đối chiếu một hệ thống ngoài, hãy **tách thành integration test riêng** với quyền/môi trường được duyệt, không giấu nó trong assertion helper của contract test.

## 8. Database và trạng thái lưu trữ: nguy cơ lộ dữ liệu và mất isolation

Một test có thể ghi DB theo nhiều đường:

- `@BeforeEach` tạo bản ghi fixture.
- Request POST/PUT/PATCH/DELETE của generated test kích hoạt producer logic.
- Bean startup chạy migration, data initializer hoặc background worker.
- Custom assertion gọi repository để kiểm tra trạng thái rồi vô tình update.
- Cleanup xóa rộng quá phạm vi.
- Retry lặp lại request không idempotent.

### Hạn chế bằng kiến trúc test

- Sử dụng một database test riêng hoặc container test có lifecycle quản lý.
- Dùng tài khoản chỉ có quyền cần cho test database, không có quyền đọc production.
- Tách schema theo CI job nếu cần chạy song song.
- Chỉ dùng migration trên DB test, không dùng credentials cho môi trường thật.
- Đặt test transaction boundary rõ ràng.
- Assert các side effects **được phép** và **không được phép** xảy ra.

Một ví dụ bài kiểm tra producer POST hợp lệ có thể tạo đúng một bản ghi test. Đây là tác dụng phụ **có chủ đích** trong môi trường cô lập; không nên cấm mọi DB write một cách máy móc. Điều quan trọng là phạm vi tác động được kiểm soát và cleanup phù hợp.

## 9. Message contract: triggeredBy có thể kích hoạt hành vi thật

Spring Cloud Contract hỗ trợ message-based contracts. Ví dụ YAML minh họa:

~~~yaml
description: "Thanh toán thành công phát ORDER_PAID"
label: order_paid
input:
  triggeredBy: markTestOrderAsPaid()
outputMessage:
  sentTo: orders.events
  body:
    eventType: ORDER_PAID
    orderId: CONTRACT-ORD-1001
  headers:
    correlationId: TEST-CORR-1001
~~~

Trong ví dụ:

- `triggeredBy` là phương thức mà **generated producer test** gọi để kích hoạt hành vi.
- `outputMessage.sentTo` là logical destination producer phải gửi message đến, theo adapter/binder được cấu hình.
- `label` có thể giúp nhận diện hoặc kích hoạt stub ở consumer test khi tích hợp phù hợp.
- **Không được hiểu** `label` là tên topic hay cho rằng DSL tự tạo broker an toàn.

### Điều cần review ở phương thức trigger

Một phương thức `markTestOrderAsPaid()` có thể:

1. Thay đổi database order.
2. Gọi payment gateway thật.
3. Publish `ORDER_PAID` lên broker đang cấu hình.
4. Gọi email/sms notifier.
5. Kích hoạt listener khác trong ứng dụng.

Nếu `spring.kafka.bootstrap-servers` hoặc broker URL vô tình trỏ tới môi trường dùng chung, test có thể phát message ngoài ý muốn.

**Yêu cầu an toàn:** dùng test broker/binder, test topic namespace hoặc adapter giả được kiểm soát; ghi rõ cách producer message thực sự được xác minh. Nếu đang dùng in-memory binder, không tuyên bố đã kiểm chứng toàn bộ semantics của broker production.

### Tác dụng phụ bất đồng bộ tồn tại sau test

Một job hoàn thành JUnit method nhưng async consumer hoặc scheduled retry vẫn đang chạy. Cleanup có thể xóa fixture trước khi task kết thúc hoặc event test tiếp tục đến service khác.

Review phải xét:

- Timeout hữu hạn và waiting theo điều kiện.
- Task/thread lifecycle, shutdown hooks.
- Namespace riêng cho events.
- Cách cô lập topic/consumer group.
- Việc cleanup khi test FAIL hoặc CI bị hủy.

## 10. Custom assertion nên là hàm quan sát, không phải hành động

Tên `assertOrderIsPaid` có thể khiến người review nghĩ phương thức an toàn. Nhưng custom assertion chỉ là Java/Groovy code; nó có thể làm bất cứ điều gì mà process test được phép.

### Ví dụ anti-pattern về mặt thiết kế

~~~text
assertOrderIsPaid(orderId):
    call external payment API to "verify" payment
    update test database to PAID if response differs
    print entire Authorization header on failure
    return true
~~~

Lỗi ở đây không chỉ là có external call. Phương thức:

- Thay đổi state để làm kết quả trông như kỳ vọng.
- Trộn **setup/repair** với **assertion**.
- Làm mất dấu lỗi producer thật.
- Có thể lộ secrets khi thất bại.
- Có thể khiến test PASS vì assertion sửa dữ liệu trước khi so sánh.

**Thiết kế mong muốn:** assertion nhận **output đã thu thập**, xác minh bất biến và ném assertion failure khi sai — không tự sửa trạng thái để đạt kết quả mong muốn.

## 11. Ví dụ custom assertion thuần với Jackson

Một helper kiểm tra JSON response đã được nhận từ producer:

~~~java
package com.example.orders.contract;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;

public final class OrderResponseAssertions {
    private static final ObjectMapper JSON = new ObjectMapper();

    private OrderResponseAssertions() {}

    public static void assertPaidOrder(String responseBody,
                                       String expectedId) {
        final JsonNode root;
        try {
            root = JSON.readTree(responseBody);
        } catch (IOException e) {
            throw new AssertionError("Response không phải JSON hợp lệ", e);
        }

        if (root == null || !root.isObject()) {
            throw new AssertionError("Response phải là JSON object");
        }
        if (!expectedId.equals(root.path("id").asText(null))) {
            throw new AssertionError("Order ID không đúng hợp đồng");
        }
        if (!"PAID".equals(root.path("status").asText(null))) {
            throw new AssertionError("Status không phải PAID");
        }
    }
}
~~~

Helper này có các đặc điểm tốt:

- Đầu vào là **response body đã nhận**, không cần URL, database hay credentials.
- Không gọi network hoặc ghi file.
- Không sửa state producer.
- Chỉ đọc dữ liệu và ném lỗi khi bất biến không thỏa.
- Không log nguyên response body (có thể chứa dữ liệu nhạy cảm).
- Kết quả phụ thuộc input rõ ràng, dễ unit test.

**Lưu ý:** custom assertion có thể được gọi từ một test viết tay hoặc từ generated test nếu DSL/extension/version hỗ trợ cách tham chiếu helper. Cú pháp tích hợp tùy phiên bản Spring Cloud Contract; ví dụ này chỉ minh họa **implementation an toàn của helper**, không tuyên bố một phương thức Java tự động được generator gọi.

### Có cần luôn cấm ObjectMapper static?

`ObjectMapper` thông thường có thể tái sử dụng khi đã cấu hình xong và chỉ thực hiện serialization/deserialization thread-safe theo điều kiện sử dụng. Ví dụ không thay đổi cấu hình của nó sau khởi tạo. Nếu custom assertion thay đổi mapper settings trong lúc tests chạy song song, đó lại là shared mutable state cần review.

## 12. Không dùng assertion làm chỗ chứa logic setup và cleanup

Một phân tách tốt:

~~~text
Fixture/Setup:
    tạo dữ liệu test trong môi trường cô lập
    cấu hình fake dependencies

Act:
    generated test gọi endpoint hoặc trigger message

Assert:
    kiểm tra response/event và những side effects đã được cho phép

Cleanup:
    dọn tài nguyên do test sở hữu
~~~

Nếu assertion cần đọc database để kiểm tra hiệu ứng của POST, đó là **integration assertion** có I/O, không phải hàm thuần. Nó vẫn có thể hợp lệ khi:

- Chỉ truy cập **database test** được xác minh.
- Chỉ đọc records thuộc current test namespace.
- Không tự sửa dữ liệu hoặc gọi thêm business workflow.
- Có timeout và cơ chế eventual consistency phù hợp.
- Không đưa raw dữ liệu nhạy cảm vào lỗi hoặc log.
- Phần I/O được mô tả rõ trong test và review.

Nói cách khác, không phải mọi assertion có I/O đều bị cấm; nhưng **không được ẩn những tác động đó** hoặc dùng chúng như bằng chứng mà không chỉ rõ môi trường.

## 13. Custom assertion không được che lỗi hoặc tạo false PASS

Các anti-pattern thường gặp:

| Anti-pattern | Vì sao nguy hiểm | Thay bằng |
| --- | --- | --- |
| `try/catch` rồi bỏ qua exception | Test có thể PASS dù không kiểm chứng | Re-throw hoặc fail có ngữ cảnh |
| So sánh `contains("PAID")` trên toàn JSON | Có thể match error text/unrelated field | Parse JSON và kiểm tra đúng path |
| Xóa/ghi lại state trước khi assert | Che behavior sai | Assertion chỉ quan sát; setup nằm riêng |
| Tự retry đến khi bất kỳ HTTP 200 | Có thể bỏ qua response sai hoặc gọi nhầm service | Retry có timeout, endpoint và predicate rõ |
| Log toàn bộ payload + headers khi FAIL | Rò rỉ token, PII | Redact và chỉ log trường không nhạy cảm |
| Đọc `System.getenv("TOKEN")` để xác minh response | Kéo secrets vào code path test | Dùng dữ liệu/credentials test scope hẹp |
| Gọi `Thread.sleep` cố định | Flaky, che race condition | Awaitility/polling theo điều kiện nếu async |
| Sửa system properties/global timezone | Ảnh hưởng tests khác | Clock/client config theo instance |
| Vô hiệu hóa TLS hostname verification | Test xanh giả, mở rộng tin cậy | Test certificate + truststore phù hợp |
| Catch `AssertionError` rồi chỉ log | Giấu thất bại | Để test framework báo FAIL |
| Đưa business decision vào matcher tùy ý | Khó review, có side effects | Contract DSL rõ; helper thuần tối thiểu |

### Một test PASS có thể vẫn không kiểm tra đúng hành vi

Nếu helper `assertPaidOrder` chỉ kiểm tra chuỗi “PAID” có xuất hiện ở đâu đó, response:

~~~json
{
  "id": "ORD-1001",
  "status": "PENDING",
  "debug": "Last previous status was PAID"
}
~~~

có thể làm assertion yếu PASS. Helper trong mục 11 kiểm tra đúng `status` ở JSON path tương ứng, nên phát hiện sai lệch.

**Bảo mật và correctness liên quan nhau:** test yếu có thể bỏ sót một authorization regression hoặc một response chứa trường dữ liệu nhạy cảm không được phép.

## 14. Kiểm tra dữ liệu nhạy cảm trong assertion failure

Một test có thể được viết đúng chức năng nhưng khi FAIL lại log:

~~~text
Request headers:
Authorization: Bearer <token>
Cookie: <session>
Response:
<full payload containing personal data>
~~~

Dù token ở môi trường test, việc lưu nó vào CI log/artifact vẫn có rủi ro, đặc biệt khi nhóm dùng shared infrastructure.

Quy ước:

- Không log nguyên `Authorization`, `Cookie`, API keys hoặc credentials.
- Không dump toàn bộ request/response khi có dữ liệu nhạy cảm; chỉ trích xuất fields an toàn.
- Redact headers/body ở test logging filters và exception handlers.
- Không nhúng secret vào snapshot, Golden Master hay stub response.
- Bảo vệ quyền truy cập test reports và đặt retention phù hợp.
- Dùng synthetic data thay dữ liệu production để giảm tác động khi log bị chia sẻ.
- Xác minh **redaction thật sự hoạt động** bằng test hoặc kiểm tra log, không chỉ ghi một comment `// redacted`.

### Không dùng giá trị secret thật làm expected assertion

Một hợp đồng không nên kiểm tra response bằng cách nhúng access token production vào DSL. Nếu cần xác minh behavior authentication/authorization, sử dụng test-only credential/token và môi trường test với quyền hạn phù hợp.

**Không dùng cấu hình `spring.cloud.contract...` hoặc test helper để ép generator in ra giá trị bí mật** nhằm “dễ debug”.

## 15. Groovy DSL có thể thực thi mã trong build

Khi dùng Groovy DSL, file contract không chỉ là dữ liệu YAML tĩnh: nó được xử lý trong môi trường Groovy/JVM theo cơ chế plugin. Những lời gọi, imports, extensions hoặc mã tùy ý có thể có mức năng lực khác nhau theo phiên bản/cấu hình.

Rủi ro cần xét:

- Một PR thay đổi DSL đưa vào code thực thi thao tác ngoài mong muốn.
- Build plugin/extension tự tải tài nguyên qua mạng.
- Groovy expression gọi helper có I/O.
- CI có credentials production hoặc quyền publish khi chạy PR chưa được review.

**Không coi file Groovy trong PR không đáng tin là “chỉ là tài liệu”.** Build chạy mã và dependencies với quyền của CI job.

Biện pháp:

1. Chạy PR builds trong môi trường hạn chế secrets/credentials, đặc biệt với nguồn chưa tin cậy.
2. Thiết lập network egress policy phù hợp.
3. Bắt buộc review DSL changes như code.
4. Hạn chế helper/extension được phép dùng và kiểm tra dependencies.
5. Không chạy job publish/deploy trên contract PR chưa qua quyền review.
6. Truy vết contract revision cùng artifact và producer verification.

### YAML DSL có hoàn toàn vô hại?

YAML thường là biểu diễn khai báo, nhưng nó có thể kích hoạt **generated tests, expression/helper và producer code** khi thực thi. Vì vậy dữ liệu YAML không tự biến toàn pipeline thành read-only.

## 16. Khi nào cần custom execution/matcher?

Spring Cloud Contract hỗ trợ các matchers và các cơ chế diễn đạt giá trị động. Tùy phiên bản, có thể có chức năng gọi mã test helper hoặc expression.

Nguyên tắc lựa chọn:

- **Ưu tiên DSL matcher khai báo** khi điều kiện là so khớp JSONPath, regex, type, status hoặc headers đơn giản.
- Chỉ dùng helper khi bất biến có ý nghĩa nghiệp vụ **không thể diễn đạt rõ** bằng các matcher sẵn có.
- Giữ helper ngắn, thuần, test độc lập và không truy cập network.
- Nếu cần kiểm tra side effects của producer, viết **integration assertion được mô tả rõ** và hạn chế truy cập tài nguyên test.
- Không đưa mã tùy ý phức tạp vào hợp đồng để thay thế một service-level integration test riêng.

### Minh họa matcher rõ điều kiện

~~~yaml
description: "Lấy một đơn có trạng thái xác định"
name: get_paid_order
request:
  method: GET
  url: /api/orders/CONTRACT-ORD-1001
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: CONTRACT-ORD-1001
    status: PAID
~~~

Ví dụ này kiểm tra `status` chính xác mà không cần custom assertion có I/O. Nếu ID thay đổi theo test, có thể dùng matcher phù hợp, nhưng phải bảo vệ format/semantics consumer đang phụ thuộc.

### Cần phân biệt matcher và mock

Một response body matcher kiểm tra output producer khác với việc stub trả response mẫu. Nếu generated producer test tự cấp response mẫu thông qua mock controller rồi assert mẫu đó, bài kiểm tra có nguy cơ **tự chứng minh chính nó**, không chứng minh implementation.

## 17. Phân loại side effect: được phép, phải cô lập hay bị cấm

Không nên ra quy tắc “mọi side effect trong test đều sai”. Ví dụ một hợp đồng POST tạo Order cần producer ghi DB để chứng minh nghiệp vụ. Vấn đề là **tác dụng phụ có chủ đích và được cô lập** hay không.

| Tác dụng phụ | Phân loại gợi ý | Điều kiện |
| --- | --- | --- |
| Ghi record vào DB test container | Có thể chấp nhận | Quyền test, isolation, cleanup và assertion rõ |
| Phát event tới in-memory test binder | Có thể chấp nhận | Chứng minh payload/headers, ghi giới hạn so với broker thật |
| Gửi HTTP tới WireMock test service | Có thể chấp nhận | Đúng URL, network isolation, no unexpected requests |
| Tạo file trong temporary directory của test | Có thể chấp nhận | Chỉ trong vùng được cấp, cleanup có phạm vi |
| Đọc config test không nhạy cảm | Thường chấp nhận | Không log secret hoặc sửa global |
| Gọi payment gateway thật | Không chấp nhận trong contract test cô lập | Thay bằng test double; nếu cần integration ngoài, tách test được phê duyệt |
| Ghi production/staging DB | Không chấp nhận | Chặn bằng credentials và network restrictions |
| Publish message vào shared broker topic thật | Không chấp nhận nếu có thể tác động người khác | Test topic/broker riêng |
| In credentials/PII vào CI log | Không chấp nhận | Redact, dữ liệu giả |
| Assertion tự sửa result để PASS | Không chấp nhận | Tách setup, assert thuần |
| Tắt TLS verification toàn JVM | Không chấp nhận như cách làm test hợp lệ | SSLContext test-specific với trust material hẹp |

**Ngoại lệ cho integration tests** cần được đánh giá riêng: một e2e test có thể cố ý gọi môi trường staging được cô lập; nó không nên được trộn âm thầm vào contract verification mặc định.

## 18. Cách test tác dụng phụ được phép mà không tạo side effect nguy hiểm

Một producer POST có thể cần verify:

- HTTP status `201`.
- Response body có `id`.
- Database test xuất hiện đúng một Order.
- Chỉ một event `ORDER_CREATED` được tạo cho test binder.
- Không có outbound email/payment call ngoài dự kiến.

Một mô hình:

~~~mermaid
flowchart TD
    A["Fixture tạo môi trường test riêng"] --> B["Generated producer test: POST /orders"]
    B --> C["Producer controller + service thật"]
    C --> D["Test database"]
    C --> E["Test event binder"]
    C --> F["Mock external payment client"]
    D --> G["Assert đúng record thuộc test"]
    E --> H["Assert đúng event"]
    F --> I["Verify no unexpected external call"]
    G --> J["PASS có giới hạn"]
    H --> J
    I --> J
~~~

Điểm quan trọng:

- Không mock controller trả status 201 nếu mục tiêu là kiểm tra producer implementation.
- Không dùng DB thật ngoài phạm vi test.
- Không coi fake binder là bằng chứng broker production đã đảm bảo routing/exactly-once.
- Assertions kiểm tra **những hiệu ứng có chủ đích** và khẳng định **không có hiệu ứng ngoài danh sách** nếu an toàn là một acceptance criterion.

## 19. Test isolation khi chạy song song và retry trên CI

Một bài contract test có thể PASS riêng lẻ nhưng FAIL hoặc gây tác động ngoài khi chạy song song:

- Test A thay static `RestAssuredMockMvc` configuration, Test B dùng nhầm.
- Hai tests dùng cùng Order ID và xóa fixture của nhau.
- Một test xóa topic trong khi test khác vẫn chờ message.
- Background job tiếp tục chạy sau `@AfterEach`.
- Retries gửi lặp lại POST không idempotent.
- CI jobs chia sẻ Maven local repository, làm consumer dùng stub artifact không đúng revision.
- Property toàn JVM như `javax.net.ssl.trustStore` bị thay giữa các test.

### Các cách giảm rủi ro

1. Ưu tiên **client configuration theo instance**, tránh sửa mutable global.
2. Sử dụng ID/namespace theo test và cleanup có ownership.
3. Dùng test broker/database riêng mỗi job hoặc mỗi suite khi cần.
4. Không retry request tạo side effect nếu chưa định nghĩa idempotency.
5. Quản lý lifecycle các async tasks và resources.
6. Giới hạn parallelism với tests vẫn phụ thuộc state chung cho đến khi refactor.
7. Chạy kiểm tra **trong isolation và trong parallel** để phát hiện race.
8. Gắn artifact và report với build ID, contract revision và checksum.

### Retry không xóa được một tác dụng phụ đã xảy ra

Một test gửi POST, timeout rồi retry có thể tạo **hai** record nếu endpoint không hỗ trợ idempotency. Kết quả HTTP cuối cùng PASS không bảo đảm không có duplicate side effects.

Nếu contract yêu cầu idempotency, ghi header/token và kịch bản lặp request rõ ràng; nếu không, tránh retries tự động không được đánh giá.

## 20. CI sandbox: không đặt secrets ở nơi mã chưa được review có thể đọc

Nếu một PR có thể sửa Groovy contracts hoặc base test classes, build của PR **thực thi code chưa được merge**. Không nên cung cấp quyền nhạy cảm cho job đó.

Một chính sách CI an toàn có thể:

- PR verification chạy với credentials test hạn chế, không có production cloud token.
- Không cấp quyền deploy/publish release cho PR build từ nguồn không tin cậy.
- Network egress hạn chế; repository/download endpoints được allowlist nếu cần.
- Database/broker test cấp phát tạm thời, tự hủy.
- Test reports và artifacts được kiểm tra/redact trước khi chia sẻ rộng.
- Publish stubs chỉ sau khi code/contract đã được review và producer verification PASS.
- Có audit trail cho job nào đã publish artifacts và từ commit nào.

**Container không tự động là sandbox tuyệt đối.** Nếu mount host credentials, Docker socket hoặc quyền cloud admin vào container test, mã trong container vẫn có thể gây tác động rộng. Cần đánh giá permissions thực sự, không chỉ việc test chạy “trong Docker”.

## 21. Review dependencies và plugin extensions

Ngoài code tự viết, các dependencies hoặc extensions của test cũng có thể có side effects trong:

- Class static initialization.
- Test framework extensions.
- Logging filters.
- HTTP client interceptors.
- ObjectMapper custom serializers/deserializers.
- Spring `@TestConfiguration`, bean factories và lifecycle.
- Build plugins hoặc contract DSL helper libraries.

Quy ước:

1. Khóa plugin/library versions theo BOM/build policy.
2. Review dependency mới nếu nó thực thi trong CI có credentials.
3. Đảm bảo code test không tải script hoặc artifact không bất biến trong khi chạy.
4. Không giả định mọi plugin test đều chỉ đọc file.
5. Xác minh các classpath/test profile khác nhau không vô tình bật production connector.
6. Nếu dùng extension để xử lý contract, ghi rõ execution boundary và tác dụng phụ được phép.

Khi test behavior bất thường, kiểm tra plugin/version và effective configuration trước khi sửa hợp đồng.

## 22. Những điều không thể kết luận chỉ vì test PASS

Một generated producer contract test PASS có thể cho biết:

- Implementation test theo cấu hình đang đáp ứng **scenario được sinh**.
- Assertions của scenario tương ứng đã chạy và không phát hiện vi phạm.
- Fixture và dependencies của môi trường test cho phép đường thực thi đó.

Nhưng nó **không tự chứng minh**:

- Spring context không có bất kỳ tác dụng phụ nào ngoài những đường đã quan sát.
- Không có secret bị log ở một test khác.
- Không có outbound call tới production trong môi trường khác.
- Mọi authorization rule hoặc security policy đều đã được kiểm thử.
- Custom assertion chắc chắn là side-effect-free.
- Consumer cũ xử lý được stub mới.
- TLS/mTLS, broker delivery semantics và rolling deployment đều an toàn.
- Generated tests đã bao phủ mọi API/path.

Do đó, cần hai bộ evidence riêng nhưng liên quan:

1. **Contract correctness:** producer và consumer phù hợp hành vi đã thỏa thuận.
2. **Test-environment safety:** process bị giới hạn quyền, tài nguyên cô lập, không có side effects trái phép.

## 23. Mẫu review matrix cho base test và assertion helpers

Một bảng do nhóm tự xây dựng:

| Thành phần | Trigger | Có I/O? | Tài nguyên | Được phép? | Cách kiểm chứng |
| --- | --- | --- | --- | --- | --- |
| Spring context startup | Mỗi test context | Có thể | HTTP, broker, DB | Chỉ test resources | Review bean startup, egress audit |
| `@BeforeEach seedOrder` | Mỗi generated test | Có | Test DB | Có điều kiện | Xác minh datasource + cleanup |
| `markTestOrderAsPaid` | Message `triggeredBy` | Có | DB + binder | Có điều kiện | Test broker isolation, event assertions |
| `assertPaidOrder` | Sau HTTP response | Không | In-memory JSON | Có | Unit tests cho helper |
| `assertOrderPersisted` | Sau POST | Read I/O | Test DB | Có điều kiện | Read-only query, namespace test |
| Logging filter | Mỗi HTTP test | Có | CI logs | Giới hạn | Redaction tests |
| Stub Runner setup | Consumer test | Network/file | Maven repo + local stub | Có điều kiện | Chốt artifact, checksum, port |
| Teardown | Sau test | Có | DB/files/topic | Có điều kiện | Cleanup trong vùng ownership |

Reviewer có thể yêu cầu tác giả điền các ô **“Có I/O?”** và **“Tài nguyên”** thay vì chỉ gửi chữ “helper an toàn”.

### Phân biệt loại hành động

- **Đọc:** có thể lộ dữ liệu nhạy cảm hoặc tạo audit log.
- **Ghi:** thay đổi state, cần cleanup và quyền thấp.
- **Gọi ra ngoài:** có thể gửi thông tin hoặc phát lệnh không mong muốn.
- **Gây bất đồng bộ:** side effect có thể xảy ra ngoài thời gian kiểm tra.
- **Sửa state toàn cục:** gây lỗi lây lan giữa các tests.

## 24. Checklist CI tự động phát hiện sai phạm

Một pipeline không thể tự động chứng minh “không có tác dụng phụ ở bất cứ đâu” chỉ bằng static checks; nhưng có thể phát hiện nhiều dấu hiệu.

| Cổng kiểm tra | Điều cần xác minh |
| --- | --- |
| Preflight environment | URL/DSN trỏ tới tài nguyên test, không có production credentials |
| Network policy | Egress ngoài allowlist bị chặn |
| Contract discovery | Đúng tập DSL được phát hiện |
| Generated test execution | Tests thực sự chạy, không bị skip hoặc 0 tests |
| Base test review | Setup/teardown và bean startup có bản rà soát |
| Assertion unit tests | Helpers thuần cho ra kết quả nhất quán với input |
| Side-effect verification | Không có outbound calls ngoài danh sách; DB/event thay đổi đúng phạm vi |
| Secret scanning | Không có credentials/PII trong DSL, fixtures, artifacts |
| Log redaction check | Không lộ Authorization/Cookie/token khi test FAIL |
| Artifact provenance | Stub GAV/version/classifier và checksum khớp producer build |
| Consumer CI | Stub Runner dùng đúng artifact; consumer assertions PASS |
| Parallel/isolation | Không có shared state/race nếu CI chạy đồng thời |

Đây là **khuyến nghị quản trị CI**, không phải những chức năng tự bật của Spring Cloud Contract.

## 25. Bài tập thực hành

### Bài tập A — GET contract nhưng production side effect

Base test dùng `@SpringBootTest`. Một bean `ApplicationRunner` trong application context gửi email khi startup, dù generated test chỉ chạy GET.

**Yêu cầu:** xác định thời điểm tác dụng phụ, nêu cách cô lập và bằng chứng review cần có.

**Gợi ý:** startup của Spring context; thay email sender bằng test fake, cô lập credentials/egress, assert không có outbound send.

### Bài tập B — Test dùng nhầm datasource

`@BeforeEach` chạy `DELETE FROM orders`. Developer cho rằng `@Transactional` sẽ bảo vệ, nhưng datasource thực trỏ đến staging.

**Yêu cầu:** đánh giá rủi ro và thiết kế lại fixture.

**Gợi ý:** bảo vệ bằng datasource/credentials test-only, test-specific schema/containers, fail-fast environmental checks; không dựa vào rollback để cấp phép thao tác nguy hiểm.

### Bài tập C — Custom assertion tự sửa state

`assertOrderPaid` gọi `updateOrderStatus("PAID")` trước khi đọc lại record.

**Yêu cầu:** vì sao đây là assertion không hợp lệ? Viết hướng thay thế.

**Gợi ý:** setup tạo fixture, act gọi producer, assert chỉ đọc trạng thái sau act; không sửa để test PASS.

### Bài tập D — Rò rỉ token khi test FAIL

Logging filter in nguyên `Authorization` và response body khi nhận 401.

**Yêu cầu:** đề xuất quy tắc log và một cách kiểm chứng redaction.

**Gợi ý:** log method/path và status, redact header nhạy cảm, dùng token test-only; kiểm tra logs của test fail có kiểm soát.

### Bài tập E — Message trigger gửi broker thật

Một message contract có `triggeredBy: markTestOrderAsPaid()`. Method phát `ORDER_PAID` vào broker URL lấy từ biến môi trường chung của laptop.

**Yêu cầu:** chỉ rõ cách chặn rủi ro trước khi chạy.

**Gợi ý:** test binder/broker riêng, profile và credentials test-only, egress isolation, kiểm tra đích thực tế, cleanup/stop async tasks.

### Bài tập F — Transaction rollback không bao phủ HTTP request

Test có `@Transactional` và gửi request tới producer chạy HTTP server trên thread khác. Sau test, DB vẫn có Order mới.

**Yêu cầu:** giải thích tại sao và đề xuất isolation/cleanup phù hợp.

**Gợi ý:** rollback test thread không mặc nhiên rollback transaction của server thread; dùng DB test riêng, namespace hoặc cleanup kiểm soát.

### Bài tập G — Regex/assertion yếu

Response có `status: PENDING` và `debug: "Trước đây PAID"`; custom assertion kiểm tra response JSON string có chứa `PAID`.

**Yêu cầu:** sửa assertion về đúng JSON field và mô tả vì sao checker cũ có false PASS.

**Gợi ý:** parse JSON và so sánh `status` chính xác; không log payload gốc khi FAIL.

### Bài tập H — PR contract từ nguồn chưa tin cậy

Một PR thêm Groovy contract và custom helper; CI PR được cấp credentials deploy remote Maven repository.

**Yêu cầu:** nêu trust boundary và các quyền cần tách.

**Gợi ý:** PR verification không có quyền deploy/production credentials; hạn chế egress, review Groovy như code và publish qua job riêng có phê duyệt.

### Bài tập I — CI parallel làm rối state

Hai generated tests dùng chung Order ID, test đầu xóa fixture khi test thứ hai chưa chạy xong.

**Yêu cầu:** đưa ra hai cách làm tests không can thiệp lẫn nhau.

**Gợi ý:** namespace theo test hoặc DB/transaction isolation; tránh global cleanup và quản lý thread lifecycle.

### Bài tập J — Production verification hay mock verification?

Base test mock luôn `OrderController` trả JSON từ contract DSL, trong khi producer thật có thể trả field khác.

**Yêu cầu:** vì sao generated test PASS chưa có ý nghĩa? Mock ở tầng nào phù hợp hơn?

**Gợi ý:** giữ controller/service path thật; fake external gateway/network/broker tại boundary nguy hiểm, không mock chính output cần xác minh.

## 26. Checklist rà soát trước khi chạy và phát hành contract tests

### Môi trường và quyền hạn

- [ ] Build/test process có **credentials test-only** với quyền thấp.
- [ ] Không có URL/database/broker production trong effective test configuration.
- [ ] Nếu PR chưa được review, CI không cấp secrets và quyền publish nhạy cảm.
- [ ] Network egress được giới hạn; outbound calls bất ngờ bị phát hiện.
- [ ] Test DB/broker/storage có isolation, naming và cleanup rõ ràng.
- [ ] Không dựa vào `@Transactional` để khẳng định mọi external side effects rollback.
- [ ] Background jobs, schedulers và app startup hooks được review.

### Base test và fixtures

- [ ] Base test class được map đúng với generated producer tests.
- [ ] Spring test mode (MockMvc/WebFlux/server thật) được hiểu đúng.
- [ ] Setup/teardown không truy cập tài nguyên ngoài phạm vi test.
- [ ] Không có cleanup xóa dữ liệu ngoài ownership của test.
- [ ] Fixtures deterministic, synthetic và tái lập được.
- [ ] Không có shared static mutable state gây rối tests khác.
- [ ] Retry của request không idempotent được đánh giá.
- [ ] Các async tasks được chờ/dừng có kiểm soát.

### Custom assertions và DSL

- [ ] Custom assertion ưu tiên **pure function** nhận kết quả đã quan sát.
- [ ] Nếu helper có I/O, tài nguyên và quyền truy cập được ghi rõ.
- [ ] Assertion không tự sửa state để làm test PASS.
- [ ] Không swallow `AssertionError`, không dùng matcher quá rộng.
- [ ] Assertions kiểm tra đúng JSON path/field/semantics consumer cần.
- [ ] Không log token, Cookie, raw PII hoặc response nhạy cảm khi FAIL.
- [ ] Groovy DSL/extension được review như mã có thể thực thi trong build.
- [ ] Không có custom helper tải script/artifact không được khóa nguồn.

### Producer, stub và consumer evidence

- [ ] Generated producer tests thật sự được sinh và thực thi PASS.
- [ ] Không có required tests bị skip hoặc số tests bằng 0 ngoài dự kiến.
- [ ] Base test kích hoạt code producer cần xác minh, không mock luôn endpoint output.
- [ ] Stub mappings/JAR được sinh từ đúng contract revision.
- [ ] Artifact GAV/classifier/version/checksum được ghi.
- [ ] Consumer Stub Runner lấy đúng artifact được producer verify.
- [ ] Consumer tests có assertions nghiệp vụ, không chỉ kiểm tra stub khởi động.
- [ ] CI logs, reports và artifact không chứa dữ liệu nhạy cảm.
- [ ] Những giới hạn của HTTP/message test, TLS, broker và production deployment được nêu rõ.

## Kết luận

**Base test và custom assertion là mã thực thi**, không phải phần phụ vô hại của hợp đồng. Chúng có thể chạm database, gửi HTTP request, phát message, đọc secret, ghi file hoặc làm thay đổi trạng thái giữa các test. Vì vậy, rà soát bảo mật không dừng ở việc DSL trông hợp lệ: cần xét **toàn bộ đường chạy từ plugin/generator tới Spring context, fixture, producer implementation, assertion và teardown**.

Cách làm tốt là giữ **hành vi producer cần xác minh** càng thật càng tốt, trong khi cô lập **các ranh giới nguy hiểm** bằng credentials test-only, DB/broker riêng, network policy, fixtures xác định và helpers có phạm vi rõ ràng. Kết quả PASS phải đi kèm bằng chứng test thật sự chạy, stub artifact đúng nguồn và consumer verification phù hợp.

**Ghi nhớ:** *Một assertion không nên làm thay đổi điều mà nó đang xác minh; một base test không được có quyền tác động tới production chỉ vì nó mang tên “test”; và một pipeline xanh không đồng nghĩa an toàn nếu các tác dụng phụ chưa được kiểm soát.*

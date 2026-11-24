# Tránh base test mô phỏng chính hành vi producer cần kiểm chứng

## 1. Vấn đề: hợp đồng đúng nhưng test vẫn có thể xanh giả

Trong **Spring Cloud Contract (SCC)**, producer và consumer thỏa thuận hành vi HTTP hoặc thông điệp qua **Groovy DSL/YAML DSL**. **Contract Verifier** sinh test cho producer; từ contract còn có thể đóng gói **stub** để consumer chạy bằng **Stub Runner**. Đưa cả hai luồng vào CI giúp phát hiện thay đổi API không tương thích trước khi triển khai.

Tuy nhiên, một generated contract test chỉ đáng tin khi nó thực sự **đi qua implementation producer cần kiểm chứng**. Nếu lớp **base test** lại tự dựng một controller giả hoặc mock trả đúng response mẫu trong contract, test có thể luôn xanh dù controller, service hoặc logic thật đã bị sửa sai.

Đây là một lỗi thiết kế test đặc biệt nguy hiểm: **test đang chứng minh bản mô phỏng do người viết test tạo ra khớp contract, thay vì chứng minh producer khớp contract**.

Ví dụ, contract nói:

~~~http
GET /api/inventory/SKU-123 HTTP/1.1
Accept: application/json
~~~

~~~json
{
  "sku": "SKU-123",
  "available": true,
  "quantity": 12
}
~~~

Nếu base test dựng một controller giả luôn trả chính JSON đó, generated test sẽ đạt cho dù ứng dụng production đã đổi tên trường `available` thành `inStock`. Kết quả **BUILD SUCCESS** lúc này không phản ánh sự tương thích của API thật.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích base test được phép **thiết lập môi trường** tới mức nào mà không tự mô phỏng hành vi được kiểm chứng.
2. Phân biệt **Spring context thật**, controller giả, mocked service, fake repository và stub của hệ thống bên ngoài.
3. Viết một base test Spring Boot/MockMvc kết nối tới **controller và service thật**.
4. Nhận biết các anti-pattern như `standaloneSetup` với fake controller, `@MockitoBean` trả nguyên response mẫu hoặc dùng WireMock thay thế chính producer.
5. Thiết kế dữ liệu test ổn định mà vẫn giữ **đường thực thi nghiệp vụ quan trọng**.
6. Dùng phép thử cố ý làm sai producer để xác nhận generated test thực sự có khả năng phát hiện lỗi.
7. Xác định chỗ nào cần kiểm thử HTTP/message, consumer Stub Runner và cổng CI bổ sung.

## 2. Base test có nhiệm vụ gì?

Contract Verifier có thể sinh test, nhưng test được sinh cần một **môi trường chạy**: Spring ApplicationContext, HTTP adapter, dữ liệu mẫu, mock của một số hệ thống ngoài hoặc phương thức kích hoạt message. Lớp base test là nơi kết nối các thành phần này.

Một base test đúng thường thực hiện:

- Khởi tạo **ứng dụng producer** với Spring Boot test context thích hợp.
- Cấu hình **MockMvc, WebTestClient hoặc HTTP thật** theo test mode mà plugin sinh ra.
- Chuẩn bị dữ liệu có thể lặp lại (test database, fixture, fixed clock khi phù hợp).
- Cô lập phụ thuộc không thuộc phạm vi kiểm chứng (dịch vụ bên thứ ba, SMTP, payment gateway, API ngoại vi).
- Cung cấp **custom assertion** hoặc phương thức kích hoạt message khi contract cần.
- Khôi phục trạng thái giữa các bài test để tránh kết quả phụ thuộc thứ tự.

Base test **không nên** tự định nghĩa response endpoint mà contract cần bảo vệ, trừ khi nhóm **cố ý** chỉ kiểm tra một lớp rất hẹp và đã nêu rõ giới hạn đó.

| Việc làm trong base test | Thường phù hợp? | Điều kiện |
|---|---|---|
| Tải Spring context chứa controller production | **Có** | Generated test gọi đúng bean/endpoint |
| Thiết lập MockMvc với context thật | **Có** | Không tự thay controller production bằng giả |
| Tạo dữ liệu test trong database riêng | **Có** | Test đi qua query và mapper cần kiểm chứng |
| Giả lập email gateway bên ngoài | **Có thể** | Không phải hành vi email thật thuộc contract đang kiểm chứng |
| Mock repository trả dữ liệu thô | **Có thể** | Service/controller/serialization vẫn là code thật, phạm vi được công bố |
| Mock service trả sẵn response DTO hoàn chỉnh | **Rủi ro cao** | Bỏ qua logic service, chỉ kiểm tra tầng HTTP mỏng |
| Tạo fake controller trả JSON đúng contract | **Không**, nếu muốn kiểm chứng API thật | Test không chạm implementation production |
| Cho WireMock trả response thay endpoint producer | **Không**, nếu mục tiêu là producer verification | Đang kiểm tra stub chứ không kiểm tra producer |

**Câu hỏi then chốt:** “Nếu sửa sai đoạn code production mà hợp đồng muốn bảo vệ, generated test này có chuyển đỏ không?” Nếu không, phải xem lại base test hoặc phạm vi contract.

## 3. Ba ranh giới kiểm thử cần tách bạch

~~~mermaid
flowchart TD
    A["Contract HTTP"] --> B["Generated producer test"]
    B --> C["Base test cấu hình HTTP/test context"]
    C --> D["Controller production"]
    D --> E["Service production"]
    E --> F["Repository hoặc adapter dữ liệu"]
    F --> G["Test DB / fake ở điểm cắt đã chọn"]
    A --> H["Stub artifact"]
    H --> I["Stub Runner cho consumer"]
    I --> J["HTTP client production của consumer"]
~~~

Trong sơ đồ:

- **Producer verification** đi theo nhánh trên: request của generated test phải đến được **controller production**, và qua các thành phần ứng dụng mà nhóm muốn chứng minh.
- **Điểm cắt có kiểm soát** có thể nằm ở database hoặc cổng tới một dịch vụ ngoài. Nhưng nếu điểm cắt nằm ở **chính service xử lý hợp đồng**, test mất khả năng phát hiện sai nghiệp vụ của service.
- **Consumer verification** dùng stub của producer để thử client/handler của consumer. Stub Runner **không thay thế** việc kiểm tra implementation producer.

Không có một “độ sâu đúng cho mọi dự án”. Contract HTTP đơn giản có thể đặt phạm vi ở controller + mapper; contract chứa quy tắc giá, tồn kho hoặc lỗi nghiệp vụ có thể cần chạy cả service và repository. Điều bắt buộc là **nêu rõ phạm vi rồi kiểm chứng đúng phạm vi đó**, không tự nhận đây là test toàn hệ thống khi đã mock phần quan trọng nhất.

## 4. Ví dụ producer thật: Inventory Service

Giả sử Inventory Service có logic: số lượng tồn kho lớn hơn 0 thì `available=true`. Đây là quy tắc cần được test bảo vệ.

Một mô hình dữ liệu:

~~~java
package com.example.inventory;

public record InventorySnapshot(
        String sku,
        boolean available,
        int quantity) {
}
~~~

Service **production** (ví dụ đơn giản dùng dữ liệu trong bộ nhớ để dễ nhìn đường thực thi):

~~~java
package com.example.inventory;

import java.util.Map;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {

    private final Map<String, Integer> stock =
            Map.of("SKU-123", 12, "SKU-456", 0);

    public InventorySnapshot find(String sku) {
        int quantity = stock.getOrDefault(sku, 0);
        return new InventorySnapshot(sku, quantity > 0, quantity);
    }
}
~~~

Controller **production**:

~~~java
package com.example.inventory;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/inventory")
public class InventoryController {

    private final InventoryService service;

    public InventoryController(InventoryService service) {
        this.service = service;
    }

    @GetMapping("/{sku}")
    public InventorySnapshot find(@PathVariable String sku) {
        return service.find(sku);
    }
}
~~~

Mẫu này cố ý đơn giản để tập trung vào test. Một hệ thống thật thường truy vấn repository/database; khi đó cần fixture hoặc test database để tạo SKU và lượng tồn kho ổn định. Phần quan trọng vẫn là **controller và logic chuyển từ số lượng sang available thuộc code production**.

## 5. Contract HTTP bảo vệ điều gì?

Tệp Groovy DSL minh họa tại `src/test/resources/contracts/inventory/get-available-stock.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Checkout cần biết SKU-123 còn 12 sản phẩm'

    request {
        method GET()
        url '/api/inventory/SKU-123'
        headers {
            header('Accept', 'application/json')
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-123',
            available: true,
            quantity: 12
        )
    }
}
~~~

Nếu dự án dùng YAML DSL, một lựa chọn tương đương là:

~~~yaml
description: Checkout cần biết SKU-123 còn 12 sản phẩm
name: get_available_stock

request:
  method: GET
  url: /api/inventory/SKU-123
  headers:
    Accept: application/json

response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    available: true
    quantity: 12
~~~

Hai đoạn trên là **hai phương án thay thế nhau**. Contract nêu hành vi mong muốn, nhưng **chưa xác định controller nào sẽ được gọi**. Việc đó phụ thuộc cấu hình test mode/base test.

Ở ví dụ này, test có ý nghĩa nếu request `GET /api/inventory/SKU-123` được gửi đến **InventoryController thật**, và field `available` được tính bởi **InventoryService thật**. Nếu test trả body mẫu từ lớp giả, hợp đồng chỉ được kiểm tra với dữ liệu do chính test viết.

## 6. Base test đúng: dùng Spring context thật với MockMvc

Khi chọn test mode **MockMvc** phù hợp với version SCC, có thể cấu hình base test như sau:

~~~java
package com.example.inventory;

import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
public abstract class ContractTestBase {

    @Autowired
    MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
~~~

Đây là ví dụ dành cho dự án Spring Boot + Spring MVC có **RestAssuredMockMvc** trên test classpath và plugin được cấu hình sinh test ở **MockMvc mode**.

### Vì sao cách này đáng tin hơn controller giả?

1. `@SpringBootTest` khởi tạo **ApplicationContext của producer** (gồm các bean được scan/configure).
2. `@AutoConfigureMockMvc` tạo MockMvc nối với Spring MVC context đó.
3. `@Autowired MockMvc` lấy adapter **đã gắn vào application context thật**.
4. `RestAssuredMockMvc.mockMvc(mockMvc)` cung cấp adapter cho generated tests gọi HTTP handler.
5. `InventoryController` và `InventoryService` vẫn là bean production bình thường, không bị thay bởi fake.
6. Contract test thấy status, header và JSON thực tế do controller/service sinh ra.

**MockMvc không mở TCP socket thật**, nhưng vẫn đi qua Spring MVC handler mapping, conversion, validation và controller trong context test. Đó là khác biệt quan trọng với việc **tự tạo một controller giả** chỉ để trả response mẫu.

### Một biến thể thiết lập tương đương

Với một số cấu hình dự án, base test có thể dùng `WebApplicationContext`:

~~~java
@Autowired
WebApplicationContext context;

@BeforeEach
void setUp() {
    RestAssuredMockMvc.webAppContextSetup(context);
}
~~~

Chọn **một** cách thiết lập phù hợp với test mode. Trong bài thực tế, đừng đặt cả hai cấu hình chồng chéo nếu không có lý do. Tên API, import và khả năng hỗ trợ tùy vào version RestAssured/SCC nên phải đối chiếu version của dự án khi triển khai.

## 7. Base test sai: standaloneSetup với controller giả

Phản ví dụ sau chứa chính lỗi mà bài muốn ngăn.

~~~java
package com.example.inventory;

import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

public abstract class WrongContractTestBase {

    @BeforeEach
    void setUp() {
        RestAssuredMockMvc.standaloneSetup(new FakeInventoryController());
    }

    @RestController
    @RequestMapping("/api/inventory")
    static class FakeInventoryController {

        @GetMapping("/{sku}")
        InventorySnapshot get(@PathVariable String sku) {
            // Test tự trả response mà contract yêu cầu.
            return new InventorySnapshot("SKU-123", true, 12);
        }
    }
}
~~~

Ở đây generated test có thể gửi GET và nhận đúng JSON, nhưng request chạy vào **FakeInventoryController** chứ không vào `InventoryController` của production.

Hậu quả:

- Đổi logic trong `InventoryService.find` từ `quantity > 0` thành `quantity == 0` có thể **không làm test đỏ**.
- Xóa mapping thật `GET /api/inventory/{sku}` vẫn có thể **không ảnh hưởng** test.
- Đổi serializer hoặc error handler của ứng dụng production có thể bị test bỏ qua.
- Test đang kiểm tra việc fake controller trả đúng dữ liệu đã được lập trình sẵn, nên dễ trở thành **self-fulfilling test**.

**Không phải `standaloneSetup` luôn sai.** Dùng `standaloneSetup(new InventoryController(realService))` có thể phù hợp cho một bài kiểm thử controller cô lập, nhưng bạn phải biết phần Spring configuration, filter, controller advice và các thành phần không được chạy. Nó không tự thay thế `@SpringBootTest` nếu contract muốn bảo vệ giao diện HTTP của ứng dụng hoàn chỉnh.

Với SCC generated producer tests, lựa chọn an toàn phổ biến là **base test khởi tạo đúng implementation production** theo phạm vi đã thống nhất.

## 8. Base test sai tinh vi hơn: mock service trả sẵn toàn bộ DTO

Đôi khi base test sử dụng Spring context thật nhưng thay bean nghiệp vụ bằng một mock:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
public abstract class RiskyContractTestBase {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    InventoryService inventoryService;

    @BeforeEach
    void setUp() {
        org.mockito.Mockito.when(
            inventoryService.find("SKU-123")
        ).thenReturn(
            new InventorySnapshot("SKU-123", true, 12)
        );

        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
~~~

Ví dụ dùng `@MockitoBean` của các dòng Spring Framework có hỗ trợ annotation này. Ở những dự án cũ, có thể thấy `@MockBean` của Spring Boot. Cú pháp thay đổi theo phiên bản nhưng rủi ro **không thay đổi**.

Test kiểu này **vẫn kiểm tra controller production, route, serialization và một phần cấu hình MVC**. Không nên nói nó hoàn toàn vô nghĩa. Tuy nhiên, nó **không kiểm tra logic InventoryService.find**, vì response đã bị mock quyết định sẵn.

Nếu contract khẳng định “còn hàng khi số lượng > 0”, mock toàn bộ service là điểm cắt **quá cao**: thay đổi sai trong service không làm contract test đỏ.

**Quy tắc:** không mock đơn vị xử lý mà chính hợp đồng muốn bảo vệ. Nếu phải dùng một MVC slice test, hãy ghi rõ chỉ đang bảo vệ **HTTP adapter/serialization**, và bổ sung kiểm tra nghiệp vụ thích hợp ở cấp khác.

## 9. Khi nào mock/fake là hợp lý?

Mục đích cô lập không phải biến test thành “tất cả đều thật”. Test có thể chạy với những phụ thuộc giả lập hợp lý, miễn là **đường thực thi cần kiểm tra** vẫn còn.

Ví dụ kiến trúc:

~~~text
GET /api/inventory/{sku}
    -> InventoryController thật
    -> InventoryService thật (quy tắc available)
    -> InventoryRepository / InventoryGateway
    -> Test database hoặc fake repository trả dữ liệu thô
~~~

Trong tình huống này, ta có thể:

- Dùng **test database** được nạp dữ liệu SKU-123 với quantity 12. Cách này bao phủ cả persistence mapping/query khi điều đó quan trọng.
- Dùng **fake repository** trả một entity hoặc bản ghi tồn kho, nếu mục tiêu chỉ kiểm tra HTTP + service. Service vẫn tự tính `available`.
- Mock **email sender** hoặc hệ thống audit phụ trợ để tránh gửi thông báo thật trong test.
- Stub **dịch vụ ngoài** mà producer gọi, nhưng phải bảo đảm producer vẫn xử lý response của dịch vụ ngoài qua code thật.

Phân biệt hai ví dụ sau:

| Chuẩn bị test | Còn kiểm tra quy tắc `available = quantity > 0`? |
|---|---|
| Fake repository trả `StockEntity(quantity=12)`, service thật tính `available` | **Có** |
| Mock service trả sẵn `InventorySnapshot(available=true, quantity=12)` | **Không** |
| Fake controller trả body mẫu | **Không** |
| Test database với dữ liệu tồn kho, controller/service/repository thật | **Có**, và kiểm tra rộng hơn |

Một fake repository cũng có thể tạo kết quả xanh giả nếu nó mô phỏng **chính quy tắc nghiệp vụ** đang cần kiểm tra. Điểm cắt phù hợp phải được đánh giá theo **tính chất hợp đồng**, không theo tên công nghệ.

## 10. Làm dữ liệu ổn định nhưng vẫn kiểm tra implementation thật

Test đáng tin cần có dữ liệu xác định và độc lập giữa những lần chạy. Tuy nhiên, không nên giải quyết tính ổn định bằng cách tự ghi cứng response trong base.

Một số kỹ thuật phù hợp:

- **Database migration + fixture:** tạo schema và dữ liệu mẫu cho môi trường kiểm thử.
- **`@Sql` hoặc fixture loader:** chèn SKU và quantity được contract sử dụng trước test; dọn sạch/rollback phù hợp.
- **Testcontainers:** dùng database hoặc broker thật trong container khi cần kiểm tra tích hợp có mức độ sát production.
- **Fixed clock:** truyền một `Clock` kiểm thử cố định khi timestamp do ứng dụng tự tạo và thời điểm nằm ngoài bản chất nghiệp vụ.
- **Dữ liệu ngẫu nhiên có seed** nếu cần nhiều trường hợp nhưng vẫn muốn test tái lập được.
- **Test profile:** trỏ vào database/test endpoint riêng, không làm yếu hoặc thay implementation nghiệp vụ.

Ví dụ ý tưởng dùng `@Sql` trên base test:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@Sql(
    scripts = "/sql/inventory-contract-fixture.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
public abstract class ContractTestBase {
    // Setup RestAssuredMockMvc như phần trước.
}
~~~

Ví dụ trên giả định **dự án có file SQL fixture phù hợp**, và cần import `org.springframework.test.context.jdbc.Sql`. Đây chỉ là minh họa kỹ thuật tổ chức dữ liệu; bài hiện tại không tạo tệp SQL, controller hoặc database.

Điểm quan trọng là input có thể kiểm soát, nhưng response vẫn do **code producer thật** tính toán và serialize.

## 11. Phân biệt MockMvc đúng và HTTP thực sự

MockMvc chạy qua Spring MVC stack nhưng không đi qua toàn bộ tầng mạng và web server thật. Tùy hợp đồng, có thể cần mức kiểm chứng cao hơn:

| Cách chạy | Những gì thường được kiểm tra | Điều không tự bảo đảm |
|---|---|---|
| MockMvc với `@SpringBootTest` | Mapping, controller, converter, validation, service/repository được nạp trong context | Socket/network, reverse proxy, TLS hoặc cấu hình container thật |
| `@WebMvcTest` + mock service | HTTP slice và controller với service giả | Quy tắc service/repository đã bị mock |
| `standaloneSetup` với controller thật | Controller ở phạm vi unit/slice đã thiết lập | Toàn bộ auto-configuration, filter, security, advice... |
| HTTP test với server boot ở cổng ngẫu nhiên | HTTP server + application stack chạy trong test | Hệ thống bên ngoài nếu đã stub; production infra |
| E2E với môi trường tích hợp | Một tập tuyến giao tiếp rộng hơn | Không bảo đảm tất cả tình huống nếu test coverage thiếu |

**Nên chọn mode theo mục tiêu test.** Nếu contract phụ thuộc cách triển khai HTTP container, authentication filter hoặc error handling ở tầng ngoài MVC, có thể cần HTTP integration test thật. Nếu contract chỉ kiểm tra body mapping và nghiệp vụ service, MockMvc với context thật thường cho vòng phản hồi nhanh và hiệu quả.

Tránh áp dụng khẩu hiệu “mọi thứ phải chạy thật”: cần cô lập dịch vụ ngoài có kiểm soát để CI ổn định. Nhưng **không được che lớp chịu trách nhiệm tạo ra hành vi hợp đồng**.

## 12. Cấu hình Contract Verifier trỏ đúng base class

Với Maven, plugin Contract Verifier cần biết test base nào được sử dụng. Một cấu hình minh họa:

~~~xml
<plugin>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-contract-maven-plugin</artifactId>
    <version>CONTRACT_PLUGIN_VERSION</version>
    <extensions>true</extensions>
    <configuration>
        <baseClassForTests>
            com.example.inventory.ContractTestBase
        </baseClassForTests>
    </configuration>
</plugin>
~~~

`CONTRACT_PLUGIN_VERSION` là placeholder, **phải thay bằng một phiên bản thật phù hợp với Spring Boot, Spring Cloud Release Train và Contract dependencies**. Không chạy nguyên ví dụ với placeholder.

Trong `dependencies` của producer thường có:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-contract-verifier</artifactId>
    <scope>test</scope>
</dependency>
~~~

Với Gradle có SCC plugin tương ứng:

~~~groovy
contracts {
    baseClassForTests = 'com.example.inventory.ContractTestBase'
}
~~~

Cần bảo đảm:

1. Plugin có **được chạy** trong vòng đời build.
2. Generated test thừa kế hoặc có thể dùng **đúng base test**.
3. MockMvc/RestAssuredMockMvc hoặc adapter khác khớp với **test mode sinh ra**.
4. Không có base test từ nhóm contract khác vô tình thay bean/controller.
5. Các generated tests **được compile và thực thi** trong test runner.
6. Version plugin không bị lệch dòng với dependency do BOM quản lý.

Khi dự án có nhiều nhóm contract, cơ chế chọn base class theo package/cấu hình plugin cần được thiết kế rõ để mỗi generated test dùng đúng môi trường.

## 13. Anti-pattern: lấy stub của producer để thay producer

Stub Runner/WireMock rất hữu ích để consumer phát triển độc lập với producer. Nhưng dùng stub thay thế chính endpoint producer khi chạy generated producer tests là **sai mục đích**.

Ví dụ một vòng kiểm tra không đáng tin:

~~~text
Contract:
GET /api/inventory/SKU-123 -> {"available":true}

Base test:
  khởi động WireMock với mapping từ cùng contract
  generated producer test gửi request tới WireMock
  WireMock trả {"available":true}

Kết quả: PASS, mặc dù InventoryController thật không hề được gọi.
~~~

Đó là kiểu **so sánh contract với bản sao của chính contract**. Nếu producer thật đổi `available` thành `inStock`, bài test vẫn có thể xanh.

Cách tách đúng:

- **Producer test:** request phải đến **application code của producer**.
- **Consumer test:** request của **client consumer** đến **stub của producer**.
- **E2E test (nếu cần):** client consumer đến producer thật trên môi trường test.

Nên đặt tên rõ các job trong CI để đội phát triển không nhầm “producer verification” với “consumer stub test”.

## 14. Không chỉ HTTP: base test của message contract

Spring Cloud Contract cũng có hợp đồng trao đổi thông điệp. Ví dụ producer phát sự kiện sau thay đổi tồn kho:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'stockChanged'

    input {
        triggeredBy('triggerStockChanged()')
    }

    outputMessage {
        sentTo('inventory.events')
        body(
            eventType: 'StockChanged',
            sku: 'SKU-123',
            available: true
        )
    }
}
~~~

Ở producer test, base class có thể cung cấp phương thức `triggerStockChanged()`. **Phải kích hoạt đường production thực sự tạo message**, chẳng hạn gọi application service use case. Không nên để phương thức test **tự gửi một message đúng mẫu vào test sink**, vì như vậy bỏ qua logic producer.

Phản ví dụ về ý tưởng:

~~~java
// SAI về mục đích producer verification:
// Base test tự gửi đúng nội dung mà contract muốn kiểm tra.
public void triggerStockChanged() {
    testMessageSink.send(
        "inventory.events",
        "{\"eventType\":\"StockChanged\",\"sku\":\"SKU-123\",\"available\":true}"
    );
}
~~~

Thay vào đó, thiết lập test context và gọi **entry point của ứng dụng**:

~~~java
// Ý tưởng đúng: phương thức production tự xây dựng và phát message.
// InventoryApplicationService là bean thực của ứng dụng.
@Autowired
InventoryApplicationService applicationService;

public void triggerStockChanged() {
    applicationService.changeStock("SKU-123", 12);
}
~~~

Đoạn trên là mô tả cách nối test base với một **application service giả định**; cách truyền tham số/khởi tạo dữ liệu phụ thuộc ứng dụng. Message verifier/test binder phải được cấu hình để quan sát output thật của producer.

Với messaging còn có những điểm cắt được phép: giả lập broker bên ngoài, dùng test binder hoặc môi trường broker test. Điều không nên mô phỏng là **mã production định hình payload, headers và destination** mà contract cam kết.

## 15. Cách phát hiện test xanh giả: mutation test có chủ đích

Một phép kiểm tra thực dụng là **làm sai producer thật trong nhánh thử** rồi quan sát generated test.

### Thử nghiệm A — Đổi tên trường response

1. Giữ nguyên contract yêu cầu `available: true`.
2. Đổi response production để chỉ còn `inStock` (bỏ `available`).
3. Chạy lại generated producer test.
4. **Kỳ vọng:** test đỏ vì body trả về không đáp ứng contract.
5. Khôi phục code sau phép thử.

Nếu test vẫn xanh, có thể nó đã **gọi fake controller**, nhận body từ mock service hoặc không được chạy.

### Thử nghiệm B — Làm sai quy tắc nghiệp vụ

Thay service từ:

~~~java
return new InventorySnapshot(sku, quantity > 0, quantity);
~~~

thành:

~~~java
// Cố ý sai trong nhánh thử, không giữ trong production.
return new InventorySnapshot(sku, quantity == 0, quantity);
~~~

Với `SKU-123` có quantity 12, contract yêu cầu `available: true` phải **thất bại**. Nếu không, kiểm tra liệu service thật có được gọi hay đã bị `@MockitoBean` thay thế.

### Thử nghiệm C — Bỏ endpoint production

Tạm xóa hoặc đổi URL mapping của `InventoryController`. Generated test đúng phạm vi phải báo response không như kỳ vọng, ví dụ 404. Nếu vẫn nhận 200, có thể có một controller giả hoặc mapping khác đang tiếp nhận request.

### Thử nghiệm D — Thay đổi dữ liệu test thô

Cho repository/test DB trả quantity 0 trong khi contract vẫn yêu cầu 12 và `available=true`. Nếu test vẫn xanh, cần kiểm tra có mock nào đang **trả response DTO đã đóng cứng** và bỏ qua dữ liệu nền.

**Mutation test ở đây là kiểm tra khả năng phát hiện lỗi của bộ test**, không phải thay đổi cần merge. Chạy trong nhánh riêng, luôn khôi phục code trước khi commit.

## 16. Bằng chứng nào chứng minh generated test đi qua producer thật?

Một bài test có cấu hình `@SpringBootTest` chưa tự bảo đảm mọi bean liên quan đều là production bean: Spring có thể được override bằng test configuration, bean `@Primary` hoặc annotation mock.

Hãy thu thập các bằng chứng:

| Điều cần xác nhận | Cách kiểm tra | Vì sao quan trọng |
|---|---|---|
| Test thực sự chạy | Generated source + test report | Tránh false green do 0 tests |
| Đúng test base | Generated class extends/khai báo theo base mong muốn | Tránh dùng base của nhóm khác |
| Đúng endpoint | Kiểm tra request URL và handler được Spring mapping | Tránh fake controller hoặc nhầm URL |
| Bean production được dùng | Kiểm tra Spring context và overrides | Tránh service/controller bị thay bởi mock |
| Quy tắc nghiệp vụ có chạy | Mutation làm sai service rồi test đỏ | Bằng chứng mạnh cho phạm vi test |
| Dữ liệu test ổn định | Fixture, seed, isolation | Tránh test xanh/đỏ tùy thứ tự |
| Response thật được assert | Xem generated assertions về status/header/body | Tránh matcher quá rộng |
| Stub đúng commit | Kiểm tra artifact/version/mapping | Consumer test kiểm tra thay đổi ứng viên |

Khi có nhiều implementation của cùng interface, phải kiểm tra **bean được chọn** trong test profile. Một fake hợp lệ ở tầng repository không nên bị nhầm với fake service đã bỏ qua hành vi đang kiểm chứng.

## 17. Những lựa chọn tổ chức test hợp lý

| Tình huống | Base test đề xuất | Test bổ sung nên có |
|---|---|---|
| API GET đơn giản, controller + service không phụ thuộc ngoài | `@SpringBootTest` + MockMvc, code thật | Unit tests cho edge cases |
| API đọc database, contract cần xác nhận mapping/persistence | Context thật + test database/fixture | Migration và repository integration tests |
| API gọi đối tác thanh toán | Controller/service thật; fake/mock HTTP gateway ngoài | Contract/integration tests của gateway, kiểm tra lỗi timeout |
| API chỉ bảo vệ mapping HTTP của controller | MVC slice/standalone với controller thật, phạm vi ghi rõ | Service tests riêng cho nghiệp vụ |
| API có auth/filter quan trọng | Full application context và security filter phù hợp | Security/integration tests |
| API phụ thuộc container/header thực | HTTP test với server boot thực | E2E nếu cần |
| Producer phát message | Gọi production use case; dùng broker test hoặc test binder | Consumer handler test và message schema tests |

**Không có mode nào thay thế hết mode khác.** Spring Cloud Contract bảo vệ **hành vi được mô tả và được thực thi**. Nếu ứng dụng có logic cần kiểm tra nhưng nằm sau mock, phải bổ sung bài test tương ứng hoặc điều chỉnh điểm cắt.

## 18. Sai lầm phổ biến và cách xử lý

| Dấu hiệu | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Producer đổi field mà contract test vẫn xanh | Base test trả response giả | Đảm bảo generated request gọi controller thật |
| Thay đổi service không làm test đỏ | `@MockitoBean`/mock service trả DTO mẫu | Giữ service thật, mock dependency thấp hơn hoặc thêm service test |
| Test thiếu filter/security/error handler | Dùng `standaloneSetup` hoặc slice quá hẹp | Dùng Spring context phù hợp hoặc bổ sung integration test |
| Test 404 dù controller có tồn tại | Sai application context, URL mapping hoặc base setup | Kiểm tra bean scan, path, generated request |
| Test 200 nhưng không đúng controller | Controller giả trùng mapping hoặc base override bean | Kiểm tra handler mapping thực tế |
| Generated test chưa chạy | Plugin/lifecycle/source set sai | Xem generated sources và số test executed |
| Test lệ thuộc database thật | Không cô lập dữ liệu và môi trường | Dùng test DB/fixture, cleanup/transaction phù hợp |
| Test flakiness vì time/random | Dữ liệu động không cố định hoặc matcher không phù hợp | Fixed clock/seed và matcher đúng semantics |
| Mock đúng nhưng thiếu kiểm tra nghiệp vụ | Điểm cắt ở tầng quá cao | Ghi rõ scope, bổ sung test service hoặc hạ điểm cắt |
| Stub Runner xanh nhưng producer sai | Consumer đang thử stub, không thử implementation producer | Bật producer generated contract tests riêng |
| Pipeline consumer vẫn dùng stub cũ | Version động/cache hoặc artifact không đổi | Ghim stub ứng viên và kiểm tra mapping |
| Test đỏ khi thay code nhưng team sửa contract ngay | Thay đổi breaking chưa được đánh giá | Kiểm thử consumer cũ, lập kế hoạch migration |

## 19. Đưa bài kiểm chứng vào CI/CD

~~~mermaid
flowchart TD
    A["PR thay đổi producer, contract hoặc test base"] --> B["Generate và compile contract tests"]
    B --> C["Chạy generated tests với producer thật"]
    C --> D{"Có tests và tất cả đều đạt?"}
    D -- "Không" --> X["Chặn PR / điều tra"]
    D -- "Có" --> E["Đóng gói stub từ cùng commit"]
    E --> F["Consumer CI dùng Stub Runner đúng artifact"]
    F --> G{"Consumer tests đạt?"}
    G -- "Không" --> X
    G -- "Có" --> H["Tiếp tục release gates"]
~~~

Lệnh tham khảo trong dự án đã cấu hình SCC:

~~~bash
# Maven producer
./mvnw clean verify

# Gradle producer
./gradlew clean test
~~~

Tùy plugin, task, test mode và dự án, các lệnh cần điều chỉnh. Trên Windows dùng wrapper tương ứng. Không coi kết quả exit 0 là bằng chứng đã chạy hợp đồng nếu không có generated tests.

Những cổng nên có trong CI:

1. **Có contract đầu vào**, generated test được sinh và được thực thi (nếu module producer phải có contract).
2. **Không dùng fake controller/mock business service** để trả nguyên body hợp đồng mà không có lý do phạm vi rõ ràng.
3. **Chạy test theo đúng mode và Spring context** đã chọn; kiểm tra phản hồi thực sự của producer.
4. **Kiểm tra breaking change** với contract và consumer hiện hành; không chỉ sửa contract để hợp thức hóa code mới.
5. **Đóng gói stub ứng viên** từ cùng commit sau producer verification.
6. Consumer chạy **client thật** qua Stub Runner với đúng version/classifier.
7. Lưu test reports, tọa độ stub, commit SHA và bằng chứng kiểm chứng để chẩn đoán.

Không cần chạy mutation cho mọi commit, nhưng nên đưa một hoặc vài **kiểm tra mutation định kỳ** khi refactor base test, chuyển test mode hoặc thay quy trình CI. Nếu hệ thống không phát hiện được một lỗi producer có chủ đích, đó là dấu hiệu cần chỉnh lại phạm vi test.

## 20. Thực hành: từ base test giả đến base test đáng tin

### Phần A — Lập baseline

1. Tạo ứng dụng Inventory Service với `InventoryController` và `InventoryService` như ở phần 4.
2. Viết một contract Groovy hoặc YAML bảo vệ `GET /api/inventory/SKU-123`.
3. Cấu hình plugin SCC và base test dùng Spring context thật.
4. Chạy generated producer test và xem source/test report để xác nhận test được thực thi.
5. Chạy consumer test với stub ứng viên, xác minh Checkout đọc `available`.

**Kết quả mong đợi:** test producer và consumer đều xanh; biết rõ code nào được chạy ở mỗi phía.

### Phần B — Tạo false green có chủ đích

1. Trong nhánh thử, đổi base test sang `standaloneSetup(new FakeInventoryController())` như phần 7.
2. Cho production service trả sai `available` hoặc xóa mapping endpoint thật.
3. Chạy lại generated test.
4. Quan sát nếu test vẫn xanh, xác định chính xác vì sao.
5. Khôi phục base test, để test trỏ vào application context thật.

**Kết quả mong đợi:** hiểu rằng test xanh giả **không nói lên producer tương thích**.

### Phần C — Cắt dependency đúng chỗ

1. Thay Map trong service bằng repository port có thể kiểm soát trong test.
2. Chuẩn bị test DB hoặc fake repository trả bản ghi chứa quantity 12.
3. Giữ **controller/service production** thật.
4. Cố tình đổi công thức `quantity > 0` thành `quantity == 0` và xác nhận generated test đỏ.
5. Khôi phục công thức và chạy lại test.

**Kết quả mong đợi:** vẫn có dữ liệu xác định, nhưng bảo vệ được logic sinh response.

### Phần D — Chốt consumer/CI

1. Đóng gói stub từ producer sau khi đã đạt generated tests.
2. Cho Checkout dùng Stub Runner trỏ đúng stub ứng viên.
3. Thử thay response field `available` thành `inStock`; đánh giá consumer cũ.
4. Thiết lập cổng CI chặn khi producer verification hoặc consumer compatibility thất bại.
5. Lưu bằng chứng test report và artifact version/commit.

**Đầu ra nộp bài:** sơ đồ điểm cắt, file contract, base test trước/sau, generated test report, log mutation, stub coordinate và kết quả consumer test.

## 21. Checklist kiểm tra base test

- [ ] Contract nêu rõ hành vi producer cần bảo vệ, không chỉ status hoặc một field quá rộng.
- [ ] Generated tests thật sự được sinh, compile và chạy.
- [ ] Base test khởi tạo HTTP/message adapter **gọi implementation production**.
- [ ] Không có fake controller thay endpoint cần kiểm tra.
- [ ] Nếu service nghiệp vụ bị mock, phạm vi test hẹp đó được ghi rõ và có test bổ sung.
- [ ] Repository/adapter bị fake chỉ khi phần được bỏ qua **không thuộc** cam kết cần kiểm tra.
- [ ] Test data ổn định, có cleanup/isolation thích hợp.
- [ ] Có bằng chứng handler/bean trong test context là đúng.
- [ ] Một mutation làm sai hành vi quan trọng khiến generated test **đỏ**.
- [ ] MockMvc/RestAssuredMockMvc/WebTestClient/HTTP mode khớp với plugin và base class.
- [ ] Không dùng Stub Runner/WireMock thay producer trong producer verification.
- [ ] Contract messaging kích hoạt production use case thay vì base test tự gửi payload mẫu.
- [ ] Producer test đạt trước khi sinh/đưa stub ứng viên cho consumer.
- [ ] Consumer test dùng client/handler thật với đúng stub version.
- [ ] CI không coi “build xanh nhưng 0 test được chạy” là đủ chứng cứ.
- [ ] Những thay đổi có nguy cơ breaking được đánh giá trên consumer hiện hành.

## 22. Câu hỏi tự kiểm tra

**1. Vì sao dùng fake controller trong `standaloneSetup` tạo ra false green?**

Vì generated test chỉ kiểm tra response do fake controller trả, không đi qua endpoint và service production. Thay đổi phá hợp đồng trong code thật có thể không ảnh hưởng test.

**2. `@SpringBootTest` có bảo đảm mọi logic producer được kiểm chứng không?**

Không. Bean trong context có thể bị thay bởi `@MockitoBean`, `@Primary` hoặc test configuration. Phải xem điểm cắt và hành vi nào thực sự được chạy.

**3. Có được mock repository không?**

Có thể, nếu contract muốn bảo vệ controller/service và repository chỉ cung cấp dữ liệu thô được kiểm soát. Nếu contract còn phải kiểm tra truy vấn/persistence, cần test database hoặc integration test phù hợp.

**4. Khi nào `@WebMvcTest` có ích?**

Khi mục đích là test **MVC slice**, route, binding và controller với dependency đã mock. Nhưng không được dùng kết quả đó như bằng chứng mọi service/business logic của producer đã được kiểm chứng.

**5. Cách nhanh nhất chứng minh generated test kiểm tra producer thật là gì?**

Trong nhánh thử, làm sai có chủ đích một đoạn code production mà contract bảo vệ. Nếu generated test chuyển đỏ, đó là bằng chứng trực tiếp rằng test phát hiện được lỗi ở phạm vi đó.

**6. Stub Runner có thể thay thế producer test không?**

Không. Stub Runner giúp consumer thử với hành vi mẫu từ contract. Nó không chứng minh implementation producer thật đang đáp ứng contract.

## 23. Tài liệu tham khảo

- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/): mô hình producer/consumer, Contract Verifier và Stub Runner.
- [Spring Cloud Contract – Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): Groovy/YAML DSL và sinh test.
- [Spring Framework – Testing Spring MVC](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html): MockMvc và phạm vi kiểm thử web layer.
- [Spring Boot – Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): SpringBootTest, test slices và thiết lập test context.
- [Mockito](https://site.mockito.org/): mock/stub các dependency khi phù hợp với phạm vi kiểm chứng.

**Lưu ý phiên bản:** Annotation mock bean, test mode, API khởi tạo RestAssuredMockMvc và cấu hình plugin có thể khác giữa các dòng Spring Boot/Spring Cloud Contract. Hãy đối chiếu tài liệu của phiên bản đang dùng, kiểm tra generated source và test report trước khi coi các ví dụ là thiết lập hoàn chỉnh cho dự án.

---

**Điểm cần nhớ:** Base test của Spring Cloud Contract phải **đưa generated test tới code producer cần bảo vệ**, không được **tự trả đúng response mà contract kỳ vọng**. Mock/fake là công cụ cô lập hợp lý khi đặt ở **đúng điểm cắt**; fake controller hoặc mock toàn bộ logic quan trọng sẽ tạo false green. Bằng chứng mạnh nhất là **làm sai producer thật → generated test đỏ**, rồi tiếp tục kiểm tra consumer bằng **stub ứng viên** trong CI.

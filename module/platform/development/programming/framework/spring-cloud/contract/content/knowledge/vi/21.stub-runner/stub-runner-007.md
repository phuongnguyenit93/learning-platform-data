# Khởi động nhiều producer stub trong cùng kiểm thử

## 1. Khi consumer cần gọi nhiều producer

Trong hệ thống microservices, một consumer thường phụ thuộc nhiều API. Ví dụ **Checkout Service** cần hỏi **Inventory Service** về tồn kho và **Pricing Service** về giá trước khi cho phép khách đặt hàng. Để chạy test Checkout theo cách thông thường, đội phát triển có thể phải khởi động hai producer cùng database, cấu hình mạng và tài nguyên liên quan. Điều đó khiến vòng phản hồi chậm, khó tái lập và phụ thuộc lịch phát triển của hai nhóm.

**Spring Cloud Contract (SCC)** cho phép producer và consumer cam kết hành vi HTTP hoặc message bằng **Groovy/YAML DSL**. Từ hợp đồng, Contract Verifier sinh test phía producer và tạo stub để consumer chạy bằng **Stub Runner**. Trong cùng một bài kiểm thử, Stub Runner có thể tải **nhiều artifact stubs** của các producer khác nhau, khởi động các HTTP stub servers và cho code consumer gọi chúng thay vì gọi dịch vụ thật.

Bài này thuộc chương **Stub Runner**, tập trung vào **khởi động nhiều producer stub trong cùng kiểm thử**: từ việc nhận diện artifact và quản lý cổng, đến kết nối client, xử lý lỗi, bảo đảm tương thích và cấu hình CI.

### Kết quả học tập

Sau bài học, bạn có thể:

1. Mô tả luồng một consumer gọi hai producer và biết mỗi stub mô phỏng điều gì.
2. Chuẩn bị stubs JAR độc lập do mỗi producer phát hành.
3. Cấu hình `@AutoConfigureStubRunner` với **nhiều `ids`** trong cùng Spring Boot test.
4. Phân biệt fixed ports và dynamic ports; tìm đúng port cho từng producer.
5. Gắn các URL Stub Runner vào **HTTP client thực của consumer**, thay vì mock kết quả nghiệp vụ.
6. Kiểm tra happy path và lỗi riêng của từng producer, phân biệt business 404 với unmatched 404.
7. Chẩn đoán artifact thiếu, version sai, cache cũ, mapping chồng lấn và trùng cổng.
8. Đưa bài test nhiều producer stubs vào CI với phiên bản ứng viên chính xác.

## 2. Kịch bản xuyên suốt: Checkout, Inventory và Pricing

Checkout cần hiển thị preview cho **2 đơn vị SKU-123**. Trong production, ứng dụng thực hiện hai lệnh gọi:

~~~mermaid
flowchart LR
    C["Checkout Service<br/>Consumer"] -->|"GET /api/inventory/SKU-123"| I["Inventory Service<br/>Producer A"]
    C -->|"GET /api/prices/SKU-123"| P["Pricing Service<br/>Producer B"]
    I -->|"available, quantity"| C
    P -->|"unitPriceVnd"| C
~~~

API Inventory:

~~~http
GET /api/inventory/SKU-123 HTTP/1.1
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"sku":"SKU-123","available":true,"quantity":12}
~~~

API Pricing:

~~~http
GET /api/prices/SKU-123 HTTP/1.1
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"sku":"SKU-123","unitPriceVnd":150000}
~~~

Checkout hợp nhất hai response:

~~~json
{
  "sku": "SKU-123",
  "canCheckout": true,
  "subtotalVnd": 300000
}
~~~

Các con số chỉ là dữ liệu **minh họa**. Phép tính subtotal = 2 × 150.000 nằm trong **logic của Checkout**, không phải trách nhiệm của Stub Runner.

Trong consumer test, thay hai dịch vụ thật bằng hai stub servers:

~~~mermaid
flowchart LR
    C["Checkout code thật"] -->|"Inventory HTTP client"| WI["WireMock Inventory<br/>port A"]
    C -->|"Pricing HTTP client"| WP["WireMock Pricing<br/>port B"]
    R["Stub Runner"] --> WI
    R --> WP
    A["Inventory stubs JAR"] --> R
    B["Pricing stubs JAR"] --> R
~~~

Đây vẫn là bài test **của Checkout**. Một test có thể cần cả hai stub vì một thao tác consumer thật phải giao tiếp với hai API.

## 3. Phân biệt producer verification và consumer stub test

| Loại test | Chạy gì? | Chứng minh điều gì? |
|---|---|---|
| **Inventory producer verification** | Generated tests trên code Inventory thật | Inventory đáp ứng contract tồn kho |
| **Pricing producer verification** | Generated tests trên code Pricing thật | Pricing đáp ứng contract giá |
| **Checkout consumer contract test** | Code Checkout thật + hai HTTP stubs | Checkout gửi request và xử lý response của hai producer theo contract |
| **Integration/E2E test** | Checkout + producer và hạ tầng thật phù hợp | Hành vi giao tiếp triển khai thực tế vượt ngoài mô phỏng stub |

**Stub không phải implementation producer.** Nếu Inventory thay code và trả sai `available`, một stub Inventory vẫn có thể trả đúng JSON mẫu của contract. Do đó, không được dùng consumer stub test thay cho generated producer tests.

Ngược lại, việc hai producer test đều đạt chưa chứng minh Checkout xử lý đúng sự kết hợp giữa tồn kho và giá. Đó chính là giá trị bổ sung của multi-stub consumer test.

## 4. Mỗi producer sở hữu bộ contract và artifact riêng

Mô hình nguồn:

~~~text
inventory-service/
  src/test/resources/contracts/inventory/get-stock.groovy
  -> inventory-service-1.3.0-rc1-stubs.jar

pricing-service/
  src/test/resources/contracts/prices/get-price.yml
  -> pricing-service-2.1.0-rc2-stubs.jar

checkout-service/
  src/test/java/.../CheckoutMultiProducerContractTest.java
~~~

Contract Inventory bằng Groovy DSL:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Checkout tra tồn kho SKU-123'
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

Contract Pricing bằng YAML DSL:

~~~yaml
description: Checkout tra giá SKU-123
name: get_price_sku123

request:
  method: GET
  url: /api/prices/SKU-123
  headers:
    Accept: application/json

response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    unitPriceVnd: 150000
~~~

Đây là **hai contract thuộc hai producer**, không phải hai phiên bản của một contract. Mỗi producer sinh test, kiểm tra implementation của mình, rồi đóng gói mapping WireMock và tài nguyên liên quan vào artifact stubs riêng.

Một artifact có thể chứa nhiều endpoint và nhiều response scenarios; **không cần một artifact hay một stub server cho mỗi endpoint**.

## 5. Tọa độ dùng để định danh từng stub

Stub Runner thường nhận các ID theo dạng:

~~~text
groupId:artifactId:version:classifier:port
~~~

Ví dụ:

~~~text
com.example:inventory-service:1.3.0-rc1:stubs:18081
com.example:pricing-service:2.1.0-rc2:stubs:18082
~~~

| Trường | Ý nghĩa | Ví dụ |
|---|---|---|
| `groupId` | Namespace của artifact producer | `com.example` |
| `artifactId` | Tên producer | `inventory-service` |
| `version` | Bản ứng viên hoặc bản stable được chốt | `1.3.0-rc1` |
| `classifier` | Phân biệt stubs JAR với application JAR | `stubs` |
| `port` | Cổng HTTP yêu cầu cho stub | `18081` |

Nếu **bỏ phần port**, Stub Runner có thể cấp cổng động theo cấu hình. Nếu dùng version động (ví dụ `+` ở những dòng hỗ trợ), kết quả có thể phụ thuộc repository/cache và khó truy vết. Đối với CI kiểm chứng một PR, nên dùng **exact candidate version**.

**Một điều dễ nhầm:** cổng của stub là cổng trong **máy test/CI**, không phải cổng production của Inventory hoặc Pricing. Khi chạy nhiều stubs, mỗi HTTP server cần một địa chỉ/cổng có thể phân biệt.

## 6. Chuẩn bị các stubs JAR trước khi chạy Checkout

Đối với `LOCAL` mode, Stub Runner cần tìm được **cả hai** artifacts trong Maven local repository hoặc nguồn local đã cấu hình. Vì vậy, mỗi producer phải hoàn thành:

1. Đọc contract Groovy/YAML.
2. Sinh generated producer tests.
3. Chạy tests với code producer thật.
4. Sinh WireMock mappings và các response files liên quan.
5. Đóng gói stubs JAR đúng group/artifact/version/classifier.
6. Install/publish đúng nơi consumer test sẽ tải.

Trong producer Maven đã cấu hình SCC, lệnh tham khảo:

~~~bash
# Chạy riêng trong dự án Inventory và Pricing.
./mvnw clean install
~~~

Lệnh trên chỉ có ý nghĩa nếu plugin/lifecycle của mỗi producer đã được cấu hình đúng. Với Gradle, kiểm tra task tương ứng:

~~~bash
./gradlew tasks --all
./gradlew clean build
~~~

`build` của Gradle **không mặc định chứng minh** stubs artifact đã được publish vào Maven local hoặc repository từ xa. Cần xem cấu hình publication/task và artifact đầu ra của dự án thực.

Trước khi chuyển sang Checkout test, xác nhận:

- Có `inventory-service-1.3.0-rc1-stubs.jar`.
- Có `pricing-service-2.1.0-rc2-stubs.jar`.
- Trong mỗi JAR có mapping cần dùng và body files khi được tham chiếu.
- Version của JAR là bản **đã được producer tests kiểm chứng**.
- Không dùng application JAR thông thường thay cho artifact classifier `stubs`.

## 7. Khởi động hai producer stub bằng @AutoConfigureStubRunner

Cấu hình Spring Boot integration test trong Checkout:

~~~java
package com.example.checkout;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
    "clients.inventory.base-url=http://localhost:18081",
    "clients.pricing.base-url=http://localhost:18082"
})
@AutoConfigureStubRunner(
    ids = {
        "com.example:inventory-service:1.3.0-rc1:stubs:18081",
        "com.example:pricing-service:2.1.0-rc2:stubs:18082"
    },
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CheckoutMultiProducerContractTest {

    @Autowired
    CheckoutPreviewService checkout;

    @Test
    void composesTwoProducerResponses() {
        CheckoutPreview result = checkout.preview("SKU-123", 2);

        assertThat(result.sku()).isEqualTo("SKU-123");
        assertThat(result.canCheckout()).isTrue();
        assertThat(result.subtotalVnd()).isEqualTo(300_000L);
    }
}
~~~

Ở đây:

1. `ids` là **mảng gồm hai tọa độ khác nhau**; Stub Runner cần khởi động stub của cả Inventory và Pricing.
2. Mỗi stub được yêu cầu dùng **một cổng riêng**.
3. `@SpringBootTest(properties=...)` cung cấp hai base URL ngay lúc Spring tạo context Checkout.
4. Test `@Autowired` service **của Checkout**, để service này gọi HTTP client thật.
5. `LOCAL` yêu cầu stub artifacts đã có ở nguồn local; CI tách repository có thể sử dụng `REMOTE`.

Các cổng 18081/18082 phục vụ minh họa. Nếu môi trường CI chạy nhiều suite song song, nên cân nhắc **cổng động** để giảm xung đột.

## 8. Code Checkout thật phải gọi cả hai stub servers

Để bài test có ý nghĩa, Checkout phải dùng chính code HTTP client dự kiến chạy ở production. Ví dụ `CheckoutPreviewService` dùng `RestClient`:

~~~java
package com.example.checkout;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class CheckoutPreviewService {

    private final RestClient inventory;
    private final RestClient pricing;

    public CheckoutPreviewService(
            @Value("${clients.inventory.base-url}") String inventoryUrl,
            @Value("${clients.pricing.base-url}") String pricingUrl) {
        this.inventory = RestClient.create(inventoryUrl);
        this.pricing = RestClient.create(pricingUrl);
    }

    public CheckoutPreview preview(String sku, int amount) {
        InventoryStock stock = inventory.get()
                .uri("/api/inventory/{sku}", sku)
                .retrieve()
                .body(InventoryStock.class);

        PriceInfo price = pricing.get()
                .uri("/api/prices/{sku}", sku)
                .retrieve()
                .body(PriceInfo.class);

        if (stock == null || price == null) {
            throw new IllegalStateException("Producer response is empty");
        }
        if (!sku.equals(stock.sku()) || !sku.equals(price.sku())) {
            throw new IllegalStateException("SKU mismatch");
        }

        boolean allowed = stock.available()
                && stock.quantity() >= amount;

        long subtotal = Math.multiplyExact(
                price.unitPriceVnd(), amount);

        return new CheckoutPreview(sku, allowed, subtotal);
    }

    public record InventoryStock(
            String sku, boolean available, int quantity) {}

    public record PriceInfo(String sku, long unitPriceVnd) {}
}
~~~

Và kiểu kết quả:

~~~java
package com.example.checkout;

public record CheckoutPreview(
        String sku, boolean canCheckout, long subtotalVnd) {
}
~~~

**Điểm cốt lõi:** `preview` thực sự gọi **hai HTTP servers khác nhau**, giải mã JSON và kết hợp kết quả. Nếu thay `InventoryStock`/`PriceInfo` bằng Mockito trong test, ta không còn kiểm tra URL, header, serialization hoặc cách consumer xử lý response mà contract đang bảo vệ.

Ví dụ bỏ qua validation cho `amount <= 0`, timeout, bảo mật, retry, lỗi 4xx và quy tắc tiền tệ để tập trung vào multi-stub. Hệ thống thật cần các kiểm tra bổ sung tương ứng.

## 9. Fixed ports: dễ cấu hình nhưng có rủi ro

Với fixed ports, Spring test có thể cấu hình các bean client trước khi gọi:

~~~text
clients.inventory.base-url = http://localhost:18081
clients.pricing.base-url   = http://localhost:18082
~~~

Ưu điểm: cấu hình đơn giản, kết quả dễ theo dõi và phù hợp với bài học.

Nhược điểm:

- Port có thể đã được ứng dụng/test khác sử dụng.
- Hai suite CI chạy song song có thể cùng bind port 18081.
- Một client copy sai URL và trỏ nhầm server còn lại.
- Nếu test cũ để lại WireMock server trên port, suite mới có thể gọi nhầm.
- Code production không đọc property test mà vẫn dùng discovery/URL hardcode.

Vì thế fixed ports phù hợp với môi trường **cô lập**, còn dynamic ports thường phù hợp hơn khi nhiều test jobs cùng chạy trên một host.

## 10. Dynamic ports: không đoán theo thứ tự

Khi bỏ phần `port` ở IDs, Stub Runner có thể tự cấp cổng thích hợp:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerPort;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = {
        "com.example:inventory-service:1.3.0-rc1:stubs",
        "com.example:pricing-service:2.1.0-rc2:stubs"
    },
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CheckoutDynamicPortsTest {

    @StubRunnerPort("com.example:inventory-service")
    int inventoryPort;

    @StubRunnerPort("com.example:pricing-service")
    int pricingPort;

    @Test
    void hasTwoDistinctStubPorts() {
        assertThat(inventoryPort).isPositive();
        assertThat(pricingPort).isPositive();
        assertThat(inventoryPort).isNotEqualTo(pricingPort);
    }
}
~~~

`@StubRunnerPort` giúp test lấy cổng dựa trên **định danh producer**, thay vì đoán “artifact thứ nhất nhận port nhỏ nhất”. Tên annotation, cú pháp định danh và cách inject cần kiểm tra theo phiên bản SCC cụ thể.

### Đưa dynamic port vào HTTP client

Việc lấy được port trong field test **không tự đổi** URL của bean Checkout đã được tạo trước đó. Nếu consumer client nhận base URL khi Spring context khởi động, cần một cơ chế cấu hình hoạt động đúng lifecycle, chẳng hạn:

- Dùng fixed ports trong `@SpringBootTest(properties=...)` cho một suite đơn giản.
- Dùng registry/lookup của Stub Runner và factory để tạo client đúng thời điểm.
- Sử dụng cơ chế cấu hình URL động của Spring test/plugin phù hợp với phiên bản đang chạy.

Ví dụ tạo client ở test setup sau khi có port:

~~~java
String inventoryUrl = "http://localhost:" + inventoryPort;
String pricingUrl = "http://localhost:" + pricingPort;

// Truyền URL vào các constructor client thực của ứng dụng
// hoặc cấu hình bean thông qua test-specific factory.
~~~

Đây không phải yêu cầu phải tự tạo HTTP client mới thay cho code Checkout: mục tiêu vẫn là kiểm chứng **implementation client thật**, với URL thực tế của hai stub.

## 11. Cấu hình từ test properties thay vì annotation

Một cách tổ chức khác là để test đọc danh sách stub IDs từ configuration:

~~~yaml
stubrunner:
  ids:
    - com.example:inventory-service:1.3.0-rc1:stubs:18081
    - com.example:pricing-service:2.1.0-rc2:stubs:18082
  stubs-mode: local

clients:
  inventory:
    base-url: http://localhost:18081
  pricing:
    base-url: http://localhost:18082
~~~

Đoạn YAML là ví dụ cách biểu diễn; cần xác minh binding của các property và cơ chế bật Stub Runner theo phiên bản dự án. Không đưa cấu hình này vào profile production. Có thể dùng `application-contract-test.yml` hoặc cấu hình tương đương trong test source.

Nếu dùng **cả annotation và properties** nhưng khai báo hai danh sách khác nhau, dễ phát sinh lỗi ưu tiên config hoặc tải artifact không như dự kiến. Hãy chọn một nguồn cấu hình chính và xác minh log startup.

## 12. Mỗi producer có thể phục vụ nhiều contract scenarios

Một Inventory stub JAR có thể chứa:

~~~text
GET /api/inventory/SKU-123 -> 200, còn hàng
GET /api/inventory/SKU-456 -> 200, hết hàng
GET /api/inventory/SKU-404 -> 404, không tồn tại
~~~

Trong cùng thời gian, Pricing stub JAR có thể chứa:

~~~text
GET /api/prices/SKU-123 -> 200, có giá
GET /api/prices/SKU-404 -> 404, chưa có giá
POST /api/prices/quote -> 200 hoặc 400 theo request
~~~

Stub Runner nạp các mappings của một artifact vào server tương ứng. **Một server cho mỗi bộ stub producer** có thể phục vụ nhiều endpoints.

Tuy nhiên, khi một artifact chứa nhiều mappings **cùng method/path**, điều kiện request phải đủ chặt. Nếu mapping A match cả request của mapping B, WireMock có thể trả sai scenario. Cần xem `headers`, `queryParameters`, `bodyPatterns`, `priority` trong mapping thật và chạy negative tests.

## 13. Kiểm tra từng stub server trước khi kiểm tra kết quả kết hợp

Với cổng cố định, hai yêu cầu độc lập có thể được dùng để xác nhận wiring:

~~~bash
curl -i \
  -H "Accept: application/json" \
  http://localhost:18081/api/inventory/SKU-123

curl -i \
  -H "Accept: application/json" \
  http://localhost:18082/api/prices/SKU-123
~~~

Các lệnh trên chỉ chạy được khi test/Stub Runner server đang thực sự mở cổng. Trong test chính, **Checkout service vẫn phải gọi hai client thật** chứ không dùng kết quả curl.

| Request | Response kỳ vọng |
|---|---|
| Inventory port + inventory path | 200, `quantity:12` |
| Pricing port + price path | 200, `unitPriceVnd:150000` |
| Inventory port + price path | Không trả business price hợp lệ ngoài chủ đích |
| Pricing port + inventory path | Không trả inventory hợp lệ ngoài chủ đích |

Hai negative checks giúp phát hiện **hai client trỏ nhầm cổng** hoặc mappings không thuộc producer mong muốn. Nếu một artifact cố tình phục vụ nhiều paths, cần đánh giá theo contract thực tế.

## 14. Business 404 khác WireMock unmatched 404

Một contract Inventory có thể chủ động cam kết:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json

{"code":"SKU_NOT_FOUND","sku":"SKU-404"}
~~~

Nếu client gửi URL sai hoặc thiếu header cần thiết, WireMock cũng có thể trả 404 vì **không có mapping match**. Hai trường hợp có cùng status nhưng khác ngữ nghĩa.

Để test đúng, consumer cần assert **mã lỗi/body/schema** chứ không chỉ status. Khi request unmatched:

1. Kiểm tra Stub Runner log của **đúng producer server**.
2. Xem URL, method, query, headers và body client thật gửi.
3. Đọc mapping trong stubs JAR.
4. Dùng request journal/near misses của WireMock nếu phiên bản hỗ trợ.
5. Xác nhận artifact và cổng không bị tráo giữa Inventory/Pricing.

Một 404 trả từ Pricing port không nên bị hiểu ngay là Inventory không tìm được SKU.

## 15. Hai producer có cùng URL path có xung đột không?

Giả sử cả Inventory và Pricing đều có:

~~~text
GET /api/status
~~~

Nếu hai stub servers lắng nghe **hai cổng riêng**, các mappings hoàn toàn có thể tồn tại độc lập:

~~~text
localhost:18081/api/status -> Inventory status
localhost:18082/api/status -> Pricing status
~~~

Không có xung đột chỉ vì route giống nhau. Xung đột xuất hiện khi:

- Hai server cố bind cùng địa chỉ/cổng.
- Client của một producer bị cấu hình gọi cổng của producer khác.
- Một server được nạp những mappings không mong muốn.
- Nhiều mappings trong **cùng server** match một request do predicate quá rộng.

Không dựa vào thứ tự tên file hoặc thứ tự `ids` để giải quyết các trường hợp đó; phải kiểm tra mapping và định danh producer.

## 16. Các lỗi từng producer phải được kiểm thử riêng

Một happy path Inventory=12, Pricing=150000 chưa bao phủ nhiều tình huống quan trọng:

| Inventory | Pricing | Hành vi Checkout cần quyết định |
|---|---|---|
| Còn hàng | Có giá | Cho phép checkout, tính subtotal |
| Hết hàng | Có giá | Không cho checkout |
| SKU không tồn tại | Có giá | Báo SKU không hợp lệ |
| Còn hàng | Chưa có giá | Không cho checkout, báo giá chưa sẵn sàng |
| Inventory 503 | Có giá | Retry/fallback hoặc lỗi theo chính sách |
| Còn hàng | Pricing 503 | Lỗi giá theo quy ước |
| Còn hàng | Pricing timeout | Thử client timeout/retry, không trả giá giả |

Để mô phỏng những response lỗi là một phần API, **mỗi producer cần contract tương ứng**. Stub Runner không tự phát sinh tất cả lỗi từ ý tưởng “có API”. Nếu muốn mô phỏng chậm mạng hoặc connection fault, dùng một **resilience test** riêng (WireMock delay/fault hoặc test server), vì stub contract bình thường thường trả nhanh.

Consumer test cần xác nhận **lỗi được xử lý đúng**: ví dụ Pricing 404 không được silently trở thành giá 0, và Inventory 503 không được hiểu là “còn hàng”.

## 17. Hai stub độc lập không tự chia sẻ trạng thái nghiệp vụ

Stub Runner không biến hai stubs thành một workflow sống. Mỗi server trả dữ liệu theo contract/mappings của mình.

Ví dụ Checkout gọi Inventory trả `SKU-123` nhưng Pricing trả `SKU-456`, Stub Runner **không tự sửa dữ liệu**. Chính Checkout cần kiểm tra quan hệ giữa responses. Vì vậy, trong code consumer mẫu có assertion kiểm tra `stock.sku` và `price.sku` đều bằng requested SKU.

Với hệ thống phức tạp:

- Các contract samples nên nhất quán ở các trường liên quan.
- Consumer integration test kiểm tra cách kết hợp dữ liệu.
- Stateful scenarios chỉ dùng khi WireMock/SCC version và test requirements thật sự cần, không mặc định có.
- E2E/integration test với producer thật vẫn cần khi phải xác nhận transaction, eventual consistency, authorization hoặc logic phụ thuộc nhiều dịch vụ.

**Giá trị của multi-stub test là kiểm tra consumer orchestration**, không mô phỏng mọi tác động thực tế của hệ phân tán.

## 18. Port lookup theo group và artifact, không theo thứ tự

Với nhiều stubs, cách suy đoán sau không an toàn:

~~~text
ids[0] -> port thấp nhất
ids[1] -> port kế tiếp
~~~

Thay vào đó, dùng định danh đầy đủ:

~~~java
@StubRunnerPort("com.example:inventory-service")
int inventoryPort;

@StubRunnerPort("com.example:pricing-service")
int pricingPort;
~~~

Một số phiên bản Stub Runner còn cung cấp `StubFinder` để lookup địa chỉ stub đã chạy. Khi `artifactId` trùng nhau dưới hai `groupId` khác nhau, phải dùng **group + artifact** đầy đủ.

Nếu cùng một suite cần hai **version của chính một artifact**, lookup bằng group/artifact có thể nhập nhằng; hãy kiểm tra khả năng hỗ trợ của phiên bản Stub Runner hoặc tách thành hai test suites với hai version được chốt.

## 19. LOCAL và REMOTE cho nhiều producer artifacts

| Chế độ | Nguồn stub | Khi phù hợp | Điểm cần kiểm tra |
|---|---|---|---|
| **LOCAL** | Maven local repository hoặc nguồn local được cấu hình | Dev/test trên cùng máy sau khi install stubs | Đã có đủ **hai** artifact chưa? |
| **REMOTE** | Artifact repository được chỉ định | CI đa repository và nhiều đội | Quyền truy cập, exact version, cache, checksum/mapping |

Với REMOTE, cần cấu hình URL repository và credentials theo hướng dẫn phiên bản SCC. Không hardcode token trong annotation/YAML nguồn. Một artifact tải được không chứng minh cả hai đã có: log startup phải thể hiện **từng tọa độ được resolve** và server/mappings tương ứng.

Nếu mục tiêu là kiểm chứng bản ứng viên của Inventory nhưng repository không có candidate JAR, pipeline phải báo lỗi; không nên âm thầm dùng Inventory stable và coi là đã kiểm tra PR.

## 20. Version ứng viên của từng producer là độc lập

Không phải lúc nào hai producer cũng thay đổi trong cùng PR. Một ma trận ví dụ:

| Thay đổi đang kiểm tra | Inventory stub | Pricing stub |
|---|---|---|
| PR Inventory | **Inventory candidate** | Pricing stable đã chốt |
| PR Pricing | Inventory stable đã chốt | **Pricing candidate** |
| PR Checkout | Các phiên bản producer được tuyên bố hỗ trợ | Các phiên bản producer được tuyên bố hỗ trợ |
| Thay đổi đồng thời hai producer | **Inventory candidate** | **Pricing candidate** |

Mỗi CI run phải ghi lại **hai tọa độ exact** và commit liên quan. Dùng version `+`/latest có thể khiến job lấy artifact cũ hoặc mới không kiểm soát được.

Một rủi ro phổ biến:

~~~text
Inventory candidate đổi response "available" -> "inStock".
Pricing không đổi.
Checkout cũ vẫn đọc "available".

Nếu Checkout test tải Inventory stub cũ: PASS giả.
Nếu Checkout test tải Inventory candidate stub: có thể FAIL,
bộc lộ consumer chưa tương thích.
~~~

Producer Inventory mới có thể tự pass nếu code và contract cùng đổi. **Consumer test với stub ứng viên** là cổng bổ sung cần thiết trước khi phát hành breaking change.

## 21. Chạy song song và va chạm cổng

Khi hai test suites trên cùng host cùng khai báo:

~~~text
Suite A: Inventory=18081, Pricing=18082
Suite B: Inventory=18081, Pricing=18082
~~~

một suite có thể không bind được cổng, hoặc tương tác với server còn sót từ suite khác. Hướng xử lý:

1. Ưu tiên dynamic ports khi CI chạy song song nhiều suite.
2. Truyền port đã được cấp vào client bằng cơ chế phù hợp lifecycle.
3. Cô lập test container/job nếu cần fixed ports.
4. Tránh chia sẻ singleton/static base URL giữa những class test có bộ stub khác nhau.
5. Đảm bảo lifecycle của test dừng server và dọn trạng thái sau mỗi suite.
6. Không dùng `Thread.sleep` để “đợi stub khởi động”; dựa vào lifecycle của test framework và readiness check phù hợp.

Dynamic ports giảm rủi ro bind collision, nhưng không giúp nếu hai client vẫn bị cấu hình cùng URL.

## 22. Sự cố thường gặp và đường chẩn đoán

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| Inventory chạy nhưng Pricing không start | Pricing stubs JAR chưa install/publish hoặc ID sai | Kiểm tra artifact tọa độ, repository và log |
| Pricing trả 404 | Path, header hoặc mapping Pricing không match | So raw request với mapping đã nạp |
| Hai clients đều trả JSON Inventory | Hai base URL cùng trỏ Inventory port | Kiểm tra properties, bean wiring, logs |
| Một stub báo bind error | Port bị chiếm hoặc trùng cổng | Dynamic ports hoặc cô lập suite |
| Tắt Pricing stub mà test vẫn pass | Checkout client bị mock hoặc logic không gọi Pricing | Xem code consumer và negative test |
| Dữ liệu đã đổi mà response vẫn cũ | Artifact version/cache cũ | Chốt exact coordinate, mở JAR và mapping |
| Build producer xanh nhưng stub JAR trống | Contract discovery hoặc packaging bị skip | Xem generated tests và mapping count |
| Chạy local xanh, CI fail | CI thiếu một artifact ở local repo | Cấu hình REMOTE/install đầy đủ, xác minh mode |
| Lỗi 404 bị hiểu là SKU_NOT_FOUND | WireMock unmatched request | Assert body code, xem request journal |
| Test gọi producer production ngoài ý muốn | HTTP client không dùng test URL | Kiểm tra target host, service discovery, bean setup |
| Một scenario trả sai status | Mappings cùng server chồng lấn | Kiểm tra predicates/priority và negative tests |
| Consumer pass nhưng producer thật không đáp ứng | Chưa chạy generated producer tests | Bổ sung producer verification của từng producer |
| CI flaky khi chạy song song | Port conflict, trạng thái test dùng chung | Dynamic ports, cleanup, isolation |

Thứ tự điều tra hiệu quả: **Stub Runner startup logs → tọa độ và port của từng producer → mapping trong từng artifact → raw request của từng client → response → assertion Checkout → generated producer test reports**.

## 23. Tách HTTP stubs khỏi messaging và resilience tests

Một producer có thể có cả HTTP và message contracts. Không nên hiểu việc khởi động hai HTTP WireMock servers đồng nghĩa đã khởi động một Kafka broker hoặc RabbitMQ exchange. Với message contracts, Stub Runner có API/message-trigger support theo test infrastructure và phiên bản phù hợp; consumer handler phải được kiểm tra ở tầng messaging.

Tương tự, Stub Runner thường phục vụ phản hồi mẫu nhanh, chưa chứng minh Checkout xử lý đúng:

- HTTP response bị delay;
- connection timeout;
- retry và backoff;
- cancellation của reactive WebClient;
- circuit breaker hoặc fallback.

Những yêu cầu đó cần **resilience tests** riêng, ví dụ WireMock response delay/fault ở môi trường test. Không tự sửa candidate stubs JAR để thêm delay rồi gọi đó là artifact chuẩn phát hành từ producer.

## 24. Thiết kế CI kiểm chứng nhiều producer

~~~mermaid
flowchart TD
    A["Inventory candidate build"] --> B["Producer contract tests Inventory"]
    C["Pricing candidate/stable build"] --> D["Producer contract tests Pricing"]
    B --> E["Inventory stubs JAR"]
    D --> F["Pricing stubs JAR"]
    E --> G["Checkout consumer verification"]
    F --> G
    G --> H["Stub Runner tải cả hai"]
    H --> I["Checkout client thật gọi hai stubs"]
    I --> J{"Compatibility tests đạt?"}
    J -- "Không" --> X["BLOCK + phân tích breaking change"]
    J -- "Có" --> K["Tiếp tục integration/release gates"]
~~~

Pipeline nên xác nhận:

1. **Producer verification:** generated tests của producer ứng viên được sinh và thực sự chạy.
2. **Packaging:** mỗi stubs JAR có mappings cần thiết, không rỗng.
3. **Publication:** hai artifacts có version/commit riêng, có thể resolve từ job Checkout.
4. **Startup:** Stub Runner tải đúng các tọa độ và chạy hai servers với địa chỉ khác nhau.
5. **Wiring:** mỗi HTTP client thật của Checkout trỏ đúng producer stub.
6. **Assertions:** test kiểm tra cả kết quả kết hợp và các lỗi quan trọng.
7. **Provenance:** lưu log/test reports, group/artifact/version/classifier và commit SHA.
8. **Release gate:** không promote khi consumer cũ không tương thích với contract mới mà chưa có kế hoạch migration.

Không coi một dòng `BUILD SUCCESS` là bằng chứng khi generated test không chạy, artifact stub thiếu mappings hoặc Checkout vẫn dùng stub của commit trước đó.

## 25. Thực hành A — Khởi động hai producer stub

**Mục tiêu:** Checkout preview hoạt động mà không cần chạy Inventory/Pricing thật.

1. Viết contract Inventory và Pricing theo phần 4.
2. Cho mỗi producer sinh tests, chạy producer verification và tạo stubs JAR.
3. Install vào Maven local repository hoặc publish test artifacts.
4. Thêm `@AutoConfigureStubRunner(ids={...})` với hai tọa độ và cổng khác nhau.
5. Cấu hình `CheckoutPreviewService` dùng hai base URLs.
6. Gọi `preview("SKU-123", 2)`.
7. Assert `canCheckout=true` và `subtotalVnd=300000`.
8. Xem Stub Runner log để xác nhận **cả hai stubs** đã được load.

**Bằng chứng:** hợp đồng của từng producer, stubs coordinates, logs ports, consumer test source/report.

## 26. Thực hành B — Phát hiện nhầm producer và request không match

1. Trong nhánh thử, trỏ PricingClient sang port Inventory.
2. Chạy test: phải phát hiện lỗi khi Pricing endpoint không có hoặc response không đúng.
3. Khôi phục port; cố ý thay `Accept` hoặc URL trong client nếu contract yêu cầu.
4. Kiểm tra unmatched request trên đúng WireMock server.
5. Thêm business 404 cho SKU-404 và assert body `code` để phân biệt unmatched 404.
6. Thử bỏ phần port trong ids, lấy `@StubRunnerPort` của từng producer.
7. Nếu chạy song song, xác nhận không có port conflict.

**Bằng chứng:** raw HTTP request, mapping, near misses và kết quả test âm tính.

## 27. Thực hành C — Thử breaking change ở một producer

Giả sử Inventory đổi field `available` thành `inStock`, Pricing không thay đổi.

1. Giữ contract Inventory cũ, đổi code: generated producer test phải đỏ nếu đang bảo vệ field đó.
2. Sau khi thống nhất behavior mới, cập nhật contract; producer test có thể xanh.
3. Tạo Inventory **candidate stubs JAR** của commit mới.
4. Cho Checkout cũ chạy với **Inventory candidate + Pricing stable**.
5. Quan sát lỗi deserialize/logic/assertion của Checkout khi field `available` không còn.
6. Lập kế hoạch tương thích: tạm giữ field cũ và thêm field mới, hoặc API versioning khi cần.
7. Chạy lại consumer test bằng client tương thích, ghi rõ hai artifact coordinates.

**Bằng chứng:** test reports producer/consumer trước–sau, diff contract, artifact version, quyết định migration.

## 28. Checklist review

- [ ] Đã liệt kê đầy đủ các producer mà một consumer flow thực sự gọi.
- [ ] Từng producer sở hữu contract, generated tests và stubs artifact riêng.
- [ ] `@AutoConfigureStubRunner` có đúng các ids cần kiểm tra.
- [ ] Các artifact có **version cố định** và classifier `stubs` đúng.
- [ ] Mỗi HTTP stub có cổng riêng; client không trỏ nhầm server.
- [ ] Dynamic ports được lookup theo **producer ID**, không theo vị trí trong danh sách.
- [ ] URL của từng stub được gắn đúng vào client bean với lifecycle hợp lý.
- [ ] Test gọi **consumer service/HTTP client production**, không dùng mock trả kết quả cố định.
- [ ] Có kiểm tra kết quả kết hợp và lỗi riêng của mỗi producer.
- [ ] Business 404 được phân biệt với unmatched 404.
- [ ] Mappings/body files tồn tại trong mỗi JAR; không có scenario quan trọng bị thiếu.
- [ ] LOCAL/REMOTE phù hợp môi trường; CI không fallback âm thầm sang stub stable cũ.
- [ ] Test song song không tranh chấp port hoặc chia sẻ mapping/state ngoài ý muốn.
- [ ] Nếu có timeout, retry hoặc message, có bài test chuyên biệt phù hợp.
- [ ] CI đã chạy producer verification của producer ứng viên và consumer compatibility với **đúng bộ stub ứng viên**.
- [ ] Có log version/commit cho **từng producer**, không chỉ một version chung.

## 29. Câu hỏi tự kiểm tra

**1. Vì sao phải khởi động nhiều stub trong một bài test Checkout?**

Vì flow consumer cần gọi nhiều producer. Multi-stub test giúp chạy **code Checkout thật** với các API mô phỏng độc lập, không phải dựng cả hai producer.

**2. Một producer có ba endpoint có cần ba stubs JAR không?**

Không. Một stubs JAR có thể chứa nhiều WireMock mappings cho nhiều endpoints/scenarios của cùng producer.

**3. Dùng hai stub chung một cổng có an toàn không?**

Hai servers không thể bind cùng host/port theo cách thông thường; dùng chung cổng còn dễ làm client trỏ nhầm. Nên tách cổng hoặc dùng dynamic port lookup theo producer.

**4. `@StubRunnerPort` giải quyết bài toán gì?**

Giúp nhận biết cổng Stub Runner đã cấp cho một producer, tránh đoán port từ thứ tự trong mảng ids.

**5. LOCAL và REMOTE khác nhau thế nào?**

LOCAL tìm artifacts ở nguồn local đã cấu hình, thường là Maven local repository; REMOTE tải artifacts từ repository từ xa. Cả hai cần version/candidate chính xác.

**6. Nếu Checkout test dùng Inventory stub cũ và pass, có chứng minh Inventory candidate tương thích không?**

Không. Nó chỉ chứng minh tương thích với stub cũ; phải thử **Inventory candidate**.

**7. Stub Runner có tự đồng bộ giá và số lượng tồn kho giữa hai producer không?**

Không. Hai stubs mô phỏng các scenarios đã định nghĩa. Logic kết hợp và kiểm tra tính nhất quán thuộc consumer; hành vi liên dịch vụ thực cần integration/E2E test khi thích hợp.

## 30. Tài liệu tham khảo

- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/): Contract Verifier, sinh stub và Stub Runner.
- [Spring Cloud Contract — Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner.html): ids, modes, ports, artifact resolution và nhiều stubs.
- [Spring Cloud Contract — Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): Groovy/YAML HTTP contracts.
- [Spring Cloud Contract — Maven Plugin](https://docs.spring.io/spring-cloud-contract/reference/project-features-maven.html): generated producer tests và stub packaging.
- [Spring Cloud Contract — Gradle Plugin](https://docs.spring.io/spring-cloud-contract/reference/project-features-gradle.html): task sinh/đóng gói stubs.
- [WireMock — Request Matching](https://wiremock.org/docs/request-matching/): URL/header/body matchers và chẩn đoán request.
- [Spring Framework — RestClient](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): HTTP client của consumer.
- [Spring Cloud Commons — LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): định tuyến theo service ID khi không dùng URL tĩnh.

**Lưu ý phiên bản:** Cú pháp chi tiết của `@AutoConfigureStubRunner`, `@StubRunnerPort`, StubFinder, properties và resolution có thể khác theo dòng Spring Cloud Contract. Cần chọn bộ Spring Boot–Spring Cloud Release Train–Contract tương thích và kiểm tra generated mappings, startup logs, exact candidate artifacts. Ví dụ trong bài chưa được chạy build ở bước biên soạn này.

---

**Điểm cần nhớ:** Khi một consumer phụ thuộc nhiều producer, hãy **đóng gói stubs JAR cho từng producer**, khai báo **nhiều IDs với Stub Runner**, nối **đúng URL/cổng** vào các HTTP clients thật, rồi kiểm tra cách consumer kết hợp responses. CI phải sử dụng **đúng phiên bản ứng viên của từng producer**, đồng thời chạy producer verification và consumer compatibility; chỉ như vậy mới có cơ sở phát hiện sớm thay đổi API không tương thích.

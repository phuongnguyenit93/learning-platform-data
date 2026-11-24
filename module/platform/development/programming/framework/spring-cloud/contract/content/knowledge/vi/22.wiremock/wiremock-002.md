# @AutoConfigureWireMock cho kiểm thử HTTP độc lập

## Mục tiêu học tập

Trong **Spring Cloud Contract**, producer và consumer có thể thống nhất hành vi HTTP hoặc thông điệp qua **Groovy/YAML DSL**. Công cụ sinh **producer contract tests**, tạo stub, cho phép consumer chạy với **Stub Runner** và đưa các kiểm tra tương thích vào **CI**.

Bên cạnh luồng kiểm thử hợp đồng đó, Spring Cloud Contract cung cấp tích hợp **WireMock** để một ứng dụng Spring Boot có thể kiểm thử HTTP client **độc lập với dịch vụ thật**. Annotation `@AutoConfigureWireMock` khởi tạo một WireMock server trong Spring Test context và giúp test thay thế dịch vụ HTTP bên ngoài bằng các response có thể kiểm soát.

Bài học thuộc chương **WireMock**, tập trung vào cách sử dụng `@AutoConfigureWireMock` một cách có chủ đích. Sau bài, bạn sẽ biết:

- Giải thích sự khác nhau giữa **WireMock HTTP client test**, **producer contract test** và **consumer test với Stub Runner**.
- Thêm dependency WireMock dành cho Spring Cloud Contract và cấu hình `@SpringBootTest` kết hợp `@AutoConfigureWireMock(port = 0)`.
- Kết nối HTTP client thật của ứng dụng tới cổng WireMock động qua property `wiremock.server.port`.
- Khai báo HTTP stubs bằng Java DSL, lưu mapping JSON trong test resources và xác nhận request thực sự được gửi.
- Giả lập các response thành công, `404`, `503`, phản hồi chậm và connection fault với phạm vi kiểm thử rõ ràng.
- Giảm lỗi do mapping chồng lấn, trạng thái server còn sót, cổng cố định, thời gian chờ và test chạy song song.
- Biết khi nào nên chuyển từ stub tự viết sang **contract-generated stubs / Stub Runner** để kiểm soát tương thích với producer.

## 1. Tại sao kiểm thử HTTP client cần một server giả lập?

Giả sử **Checkout Service** cần hỏi **Inventory Service** xem sản phẩm còn hàng hay không:

~~~http
GET /api/inventory/SKU-101 HTTP/1.1
Accept: application/json
~~~

Inventory trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"sku":"SKU-101","available":true,"quantity":8}
~~~

Checkout cần một `InventoryClient` gửi HTTP request, đọc JSON, chuyển thành dữ liệu Java và đưa kết quả cho luồng đặt hàng. Nếu test gọi trực tiếp Inventory thật, kết quả có thể phụ thuộc vào mạng, tài khoản test, dữ liệu database của bên kia hoặc dịch vụ đang ngừng hoạt động.

Dùng WireMock, ta thay **đích HTTP bên ngoài** bằng một HTTP server chạy ngay trong môi trường test:

~~~mermaid
flowchart LR
    T["JUnit / Spring Boot test"] --> C["InventoryClient thật"]
    C -->|HTTP localhost:dynamic-port| W["Embedded WireMock server"]
    W -->|Response mẫu| C
    C --> A["Assertion trên kết quả client"]
    T --> V["Verify HTTP request trên WireMock"]
    V --> W
~~~

**Điểm quan trọng:** `InventoryClient` vẫn phải **thực hiện request HTTP thật** tới WireMock. Ta không mock trực tiếp phương thức `inventoryClient.getStock(...)`; nếu làm vậy, test không còn bảo vệ cách client tạo URL, header, serialize request hoặc deserialize response.

### Phạm vi kiểm thử

| Lựa chọn | Đối tượng thật được kiểm tra | Thành phần giả lập | Mục tiêu |
|---|---|---|---|
| Mockito mock của `InventoryClient` | Code sử dụng client trong Checkout | Toàn bộ lời gọi client | Kiểm tra logic gọi service, **không** kiểm tra HTTP |
| **`@AutoConfigureWireMock`** | HTTP client/adapter của Checkout | Inventory HTTP server | Kiểm tra URL, header, body, parse response, lỗi |
| `MockMvc` | Controller HTTP **đầu vào** của một ứng dụng Spring MVC | Servlet container/network | Kiểm tra ứng dụng nhận request |
| Generated producer contract test | Producer implementation (đúng test mode) | Các dependency được setup trong producer test | Kiểm tra producer thực sự đáp ứng hợp đồng |
| **Stub Runner** | Consumer client và logic xử lý | Producer được mô phỏng từ contract đã sinh stub | Kiểm tra consumer theo phiên bản hợp đồng |

`@AutoConfigureWireMock` không tự tạo hợp đồng Groovy/YAML, không tự chạy test producer, cũng không tự tải stub artifact từ Maven repository. Đây là **công cụ hỗ trợ kiểm thử HTTP độc lập**, có thể bổ sung cho quy trình Spring Cloud Contract.

## 2. Các thành phần mà @AutoConfigureWireMock cấu hình

Trong một Spring Boot test context, annotation:

~~~java
@SpringBootTest
@AutoConfigureWireMock(port = 0)
class InventoryClientTest {
    // ...
}
~~~

giúp:

1. Khởi tạo một **WireMock HTTP server** gắn với Spring Test context.
2. Đăng ký cổng đang chạy vào property `wiremock.server.port`.
3. Cho phép test tạo stubs bằng WireMock Java DSL hoặc nạp mappings từ resources.
4. Dọn/quản lý vòng đời WireMock theo Spring test context và cơ chế của thư viện.

`port = 0` yêu cầu chọn một **cổng còn trống**; không có nghĩa server chỉ lắng nghe ở cổng 0. Cổng thực được cấp khi server khởi động và có thể khác nhau giữa các lần chạy.

### Vì sao chọn cổng ngẫu nhiên?

Một cổng cố định như `8089` có thể đang được ứng dụng khác sử dụng hoặc bị hai test suite tranh chấp. Với `port = 0`, CI có thể chạy nhiều job an toàn hơn, miễn là mỗi test dùng đúng cổng được cấp.

Không nên hardcode `http://localhost:8089` trong production client rồi hy vọng test thay đổi được. Đích gọi HTTP phải đến từ **cấu hình ứng dụng**, và môi trường test sẽ ghi đè cấu hình đó.

### Property quan trọng

| Property/cấu hình | Mục đích |
|---|---|
| `@AutoConfigureWireMock(port = 0)` | Khởi tạo WireMock ở cổng động |
| `wiremock.server.port` | Cổng thật do WireMock được cấp trong test |
| `inventory.base-url` | Property **do ứng dụng tự định nghĩa** để HTTP client biết đích gọi |
| `@SpringBootTest(properties = ...)` | Ghi đè property trong Spring test context |
| `stubs` của annotation | Chỉ vị trí nạp các mapping JSON bổ sung khi sử dụng file stubs |

`inventory.base-url` **không phải property mặc định của Spring Cloud Contract**. Nhóm Checkout phải viết client sao cho sử dụng property này.

## 3. Cài dependency và chọn phiên bản tương thích

Với module consumer đang dùng Spring Boot và Spring Cloud Contract, ví dụ dependency Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-contract-wiremock</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Nếu dùng Gradle:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.cloud:spring-cloud-contract-wiremock'
}
~~~

Các ví dụ giả định dự án đã áp dụng **Spring Cloud BOM** và chọn release train tương thích với Spring Boot, nên không ghi cứng số version. Nếu không dùng BOM, phải khai báo version hợp lệ cho các dependency liên quan.

Các lớp/API chính:

~~~java
import org.springframework.cloud.contract.wiremock.AutoConfigureWireMock;

import static com.github.tomakehurst.wiremock.client.WireMock.*;
~~~

`@AutoConfigureWireMock` thuộc **Spring Cloud Contract WireMock support**, còn `stubFor`, `get`, `urlEqualTo`, `aResponse` và `verify` đến từ **WireMock Java DSL**.

**Lưu ý phiên bản:** các bản Spring Boot/Spring Cloud Contract/WireMock khác nhau có thể có thay đổi về Java baseline, JUnit, dependency hoặc API cấu hình. Hãy dùng bộ phiên bản tương thích với dự án. Ví dụ Java bên dưới sử dụng `RestClient` (Spring Framework 6.1+, thường có trong ứng dụng Spring Boot 3.2+), không đại diện cho mọi ứng dụng Spring Boot đời cũ.

## 4. Tạo HTTP client thật để kiểm chứng

Để test có ý nghĩa, trước hết cần một HTTP client thật trong Checkout. Giả sử response của Inventory được biểu diễn như sau:

~~~java
package com.example.checkout.inventory;

public record StockView(
    String sku,
    boolean available,
    int quantity
) {}
~~~

`record` ở đây đòi phiên bản Java hỗ trợ record. Nếu dự án dùng Java cũ, có thể dùng POJO với getters/constructor phù hợp.

### Adapter InventoryClient

~~~java
package com.example.checkout.inventory;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class InventoryClient {

    private final RestClient http;

    public InventoryClient(
            RestClient.Builder builder,
            @Value("${inventory.base-url}") String baseUrl) {
        this.http = builder.baseUrl(baseUrl).build();
    }

    public StockView getStock(String sku) {
        return http.get()
            .uri("/api/inventory/{sku}", sku)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .body(StockView.class);
    }
}
~~~

Trong production, property `inventory.base-url` có thể là URL của Inventory Service thật, được quản lý bằng cấu hình triển khai. Trong test, property sẽ được trỏ đến WireMock.

Lớp này thực hiện những việc mà một Mockito stub trực tiếp sẽ không kiểm tra:

- Xây dựng path với biến `sku`.
- Gửi HTTP method `GET`.
- Gửi header `Accept: application/json`.
- Đọc HTTP status và deserialization JSON qua Spring HTTP client.
- Trả về `StockView` với giá trị/kiểu tương ứng.

Ở đây chưa có xử lý lỗi nghiệp vụ; `retrieve()` mặc định sẽ báo lỗi cho các HTTP error status theo behavior của `RestClient`. Ta sẽ kiểm tra nhánh đó riêng.

## 5. Một bài test hoàn chỉnh với @SpringBootTest

Giả sử Checkout có Spring Boot application và bean `InventoryClient` trong component scan. Đặt test ở nguồn `src/test/java` của consumer:

~~~java
package com.example.checkout.inventory;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.wiremock.AutoConfigureWireMock;

import static com.github.tomakehurst.wiremock.client.WireMock.*;
import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
    "inventory.base-url=http://localhost:${wiremock.server.port}"
})
@AutoConfigureWireMock(port = 0)
class InventoryClientWireMockTest {

    @Autowired
    InventoryClient inventoryClient;

    @BeforeEach
    void resetWireMock() {
        // Phù hợp khi test chỉ tạo stub động bằng Java DSL.
        reset();
    }

    @Test
    void readsStockFromHttpResponse() {
        stubFor(get(urlEqualTo("/api/inventory/SKU-101"))
            .withHeader("Accept", containing("application/json"))
            .willReturn(aResponse()
                .withStatus(200)
                .withHeader("Content-Type", "application/json")
                .withBody("""
                    {
                      "sku": "SKU-101",
                      "available": true,
                      "quantity": 8
                    }
                    """)));

        StockView stock = inventoryClient.getStock("SKU-101");

        assertThat(stock.sku()).isEqualTo("SKU-101");
        assertThat(stock.available()).isTrue();
        assertThat(stock.quantity()).isEqualTo(8);

        verify(1, getRequestedFor(
                urlEqualTo("/api/inventory/SKU-101"))
            .withHeader("Accept", containing("application/json")));
    }
}
~~~

### Tách từng giai đoạn

| Giai đoạn | Code | Ý nghĩa |
|---|---|---|
| Dựng ứng dụng | `@SpringBootTest` | Khởi tạo `InventoryClient` và cấu hình consumer |
| Dựng stub server | `@AutoConfigureWireMock(port = 0)` | Mở HTTP endpoint giả lập |
| Trỏ client đến stub | `inventory.base-url=http://localhost:${wiremock.server.port}` | Không gọi Inventory thật |
| Khai báo response | `stubFor(...willReturn(...))` | Chỉ định điều kiện request và response |
| Gọi client thật | `inventoryClient.getStock(...)` | Kiểm tra cách consumer thực sự gọi HTTP |
| Assert kết quả | `assertThat(stock...)` | Kiểm tra dữ liệu sau deserialize |
| Verify request | `verify(1, getRequestedFor(...))` | Kiểm tra method/path/header đã gửi |

Mẫu này sử dụng JUnit 5, AssertJ và Java text block (cần Java 15+). Trong dự án Java cũ, hãy thay text block bằng chuỗi thông thường. Để chạy, Spring Boot test cần tìm được class ứng dụng hoặc cấu hình `classes=...` phù hợp, và bean `RestClient.Builder` phải có trong context.

**Chú ý về `reset()`:** trong bài test này, toàn bộ stub được đăng ký **bằng Java DSL trong từng test**, nên việc reset trước test phù hợp. Nếu bạn dùng các mapping mặc định được nạp từ file, thao tác reset có thể xóa các mapping ấy; phải tổ chức reset và nạp lại mapping có chủ đích, không sao chép `reset()` máy móc.

### Vì sao phải kiểm tra cả response lẫn request?

Nếu chỉ assert:

~~~java
assertThat(inventoryClient.getStock("SKU-101").quantity())
    .isEqualTo(8);
~~~

test xác nhận khả năng đọc response, nhưng chưa thể hiện rõ rằng client đã gửi `Accept` hay gọi đúng URL nếu cấu hình WireMock quá lỏng.

Ngược lại, nếu chỉ `verify(...)`, ta mới biết request được gửi, chưa chứng minh consumer deserialize đúng `available` và `quantity`. Một test client chất lượng thường cần **cả hai chiều**.

## 6. @AutoConfigureWireMock và cổng động

Dòng:

~~~java
@AutoConfigureWireMock(port = 0)
~~~

khiến WireMock lắng nghe một cổng ngẫu nhiên. Spring Cloud Contract đưa cổng đó vào `wiremock.server.port`. Vì thế có thể cấu hình:

~~~properties
inventory.base-url=http://localhost:${wiremock.server.port}
~~~

Trong ví dụ test, property được ghi ngay trong `@SpringBootTest(properties=...)`. Có thể đặt nó trong file cấu hình riêng của test nếu dự án đã có quy ước rõ:

~~~text
src/test/resources/application-contract-test.properties
~~~

Nếu dùng file cấu hình riêng, phải bảo đảm profile `contract-test` được kích hoạt đúng. Tên file trên chỉ là ví dụ cho cơ chế cấu hình Spring Boot; không có nghĩa Spring Cloud Contract tự phát hiện mọi file có tên đó.

### Hai cổng khác nhau

Một test có thể chạy:

- **Checkout application test server** nếu `@SpringBootTest(webEnvironment = RANDOM_PORT)` được bật.
- **WireMock server** do `@AutoConfigureWireMock(port = 0)` tạo.

Đây là **hai server và hai cổng khác nhau**. `wiremock.server.port` chỉ đến **WireMock**, không phải cổng ứng dụng Checkout. Nếu chỉ cần kiểm tra một outbound client, `@SpringBootTest` ở chế độ mặc định thường đủ; không cần khởi chạy web server riêng của Checkout.

## 7. Khớp request bằng WireMock Java DSL

WireMock có thể match nhiều thuộc tính của request:

| Thành phần | API Java DSL thường dùng | Ví dụ |
|---|---|---|
| Method | `get(...)`, `post(...)`, `put(...)` | `GET` |
| Đường dẫn chính xác | `urlEqualTo(...)` | `/api/inventory/SKU-101` |
| Path không tính query | `urlPathEqualTo(...)` | `/api/inventory` |
| Query parameter | `withQueryParam(...)` | `sku=SKU-101` |
| Request header | `withHeader(...)` | `Accept: application/json` |
| JSON body | `matchingJsonPath(...)` hoặc `equalToJson(...)` | `$.sku == SKU-101` |
| Form/body text | `equalTo(...)`, `containing(...)` | Nội dung cố định hoặc một phần |
| Cookies | `withCookie(...)` | Giá trị cookie mà client cần gửi |

Một ví dụ khác, với endpoint tìm kiếm:

~~~java
stubFor(get(urlPathEqualTo("/api/inventory"))
    .withQueryParam("sku", equalTo("SKU-101"))
    .withHeader("Accept", containing("application/json"))
    .willReturn(okJson("""
        {"sku":"SKU-101","available":true,"quantity":8}
        """)));
~~~

Nếu API nhận JSON body bằng POST:

~~~java
stubFor(post(urlEqualTo("/api/reservations"))
    .withHeader("Content-Type", containing("application/json"))
    .withRequestBody(matchingJsonPath(
        "$.sku", equalTo("SKU-101")))
    .willReturn(aResponse()
        .withStatus(201)
        .withHeader("Content-Type", "application/json")
        .withBody("""
            {"reservationId":"RSV-1001","accepted":true}
            """)));
~~~

Cách match quá lỏng như **chỉ kiểm tra URL mà không kiểm tra field `sku`** có thể khiến một request sai body vẫn nhận response thành công. Tuy vậy, không nên khóa cứng những header ngẫu nhiên, request ID động hay thứ tự JSON object nếu giao diện không cam kết chúng.

### Body pattern và kiểu JSON

`equalToJson` hữu ích khi muốn so sánh body như **JSON** thay vì so sánh text từng dấu cách. `matchingJsonPath` phù hợp để kiểm tra các trường riêng lẻ. Chọn matcher dựa trên những điều producer thực sự yêu cầu từ consumer.

Ví dụ JSON số:

~~~json
{"quantity":8}
~~~

khác với:

~~~json
{"quantity":"8"}
~~~

Nếu server API yêu cầu kiểu number, test phải đủ chặt để phát hiện thay đổi này. Tuy nhiên, regex hoặc matcher kiểu văn bản có thể vô tình cho phép hai dạng; cần đọc **mapping và hành vi match thực tế**, đặc biệt khi xây dựng request body động.

## 8. Kiểm tra lỗi HTTP 404, 503 và các nhánh xử lý client

Một HTTP client phải xử lý cả tình huống không thành công.

### Giả lập 404

~~~java
stubFor(get(urlEqualTo("/api/inventory/SKU-404"))
    .willReturn(aResponse()
        .withStatus(404)
        .withHeader("Content-Type", "application/json")
        .withBody("""
            {"code":"SKU_NOT_FOUND","message":"SKU does not exist"}
            """)));
~~~

Với `InventoryClient` minh họa đang dùng `RestClient.retrieve()` không có `onStatus` tùy chỉnh, Spring thường báo lỗi dạng `HttpClientErrorException.NotFound` cho `404`. Test có thể kiểm tra:

~~~java
import org.springframework.web.client.HttpClientErrorException;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

assertThatThrownBy(() -> inventoryClient.getStock("SKU-404"))
    .isInstanceOf(HttpClientErrorException.NotFound.class);

verify(1, getRequestedFor(
    urlEqualTo("/api/inventory/SKU-404")));
~~~

Nếu ứng dụng ánh xạ lỗi HTTP sang một exception nghiệp vụ như `InventoryUnavailableException`, hãy assert **loại lỗi và kết quả ứng dụng đã công bố**, không buộc test phụ thuộc trực tiếp vào exception của RestClient.

### Giả lập 503

~~~java
stubFor(get(urlEqualTo("/api/inventory/SKU-UNAVAILABLE"))
    .willReturn(aResponse()
        .withStatus(503)
        .withHeader("Content-Type", "application/json")
        .withHeader("Retry-After", "2")
        .withBody("""
            {"code":"INVENTORY_TEMPORARILY_UNAVAILABLE"}
            """)));
~~~

`503` là **HTTP response thực sự có status/header/body**, khác với network timeout hoặc connection reset. Nếu consumer phải đọc `Retry-After`, parse mã lỗi hoặc retry theo chính sách, viết test cho các nhánh đó.

**Không xem `404` mặc định của WireMock khi request không match là bằng chứng API trả `404` như đã định nghĩa.** Để thử lỗi nghiệp vụ `SKU_NOT_FOUND`, cần có mapping dành riêng cho request, sau đó kiểm tra mã lỗi và/hoặc request journal. Nếu không, test có thể nhận `404` chỉ vì bạn viết sai URL và không match stub nào.

## 9. Phản hồi chậm và lỗi kết nối: đúng phạm vi HTTP client test

WireMock hỗ trợ giả lập độ trễ:

~~~java
stubFor(get(urlEqualTo("/api/inventory/SKU-SLOW"))
    .willReturn(aResponse()
        .withStatus(200)
        .withHeader("Content-Type", "application/json")
        .withBody("""
            {"sku":"SKU-SLOW","available":true,"quantity":8}
            """)
        .withFixedDelay(1500)));
~~~

Với `withFixedDelay(1500)`, WireMock trì hoãn response khoảng **1.500 ms**. Nếu HTTP client của Checkout đã được cấu hình request/read timeout ngắn hơn, test có thể kiểm tra fallback hoặc lỗi timeout.

**Chỉ thêm delay vào WireMock không tự cấu hình timeout cho RestClient.** Timeout do HTTP client/request factory bên dưới quyết định; tùy phiên bản Spring và thư viện HTTP, cách thiết lập khác nhau. Khi test, phải xác nhận cấu hình của **client đang được dùng thật**, không chỉ cấu hình một property không được client đọc.

Một response chậm cũng **không mô phỏng connection timeout**: WireMock đã mở cổng và có thể chấp nhận kết nối ngay, sau đó mới chậm trả response. Với connect timeout, cần một điều kiện network/transport tương ứng.

### Connection fault

WireMock có thể mô phỏng kết nối bị reset:

~~~java
import static com.github.tomakehurst.wiremock.http.Fault.CONNECTION_RESET_BY_PEER;

stubFor(get(urlEqualTo("/api/inventory/SKU-RESET"))
    .willReturn(aResponse()
        .withFault(CONNECTION_RESET_BY_PEER)));
~~~

Trong tình huống này có thể **không có HTTP response hợp lệ**. Exception mà consumer nhìn thấy phụ thuộc HTTP client, JDK và nền tảng. Nên kiểm chứng rằng Checkout:

- Không coi sự cố mạng là `available=false` khi chưa có dữ liệu tồn kho.
- Giới hạn retry theo ngân sách thời gian.
- Hiển thị hoặc trả một trạng thái “không thể xác minh” phù hợp với nghiệp vụ.
- Ghi log/metric chẩn đoán nhưng không lộ dữ liệu nhạy cảm.

Không cần đưa mọi fault WireMock vào contract DSL. Với ứng dụng thực tế, chúng thường thuộc nhóm **resilience/consumer HTTP tests** tách biệt với producer contract tests.

## 10. Stubs bằng file JSON thay vì Java DSL

Khi mapping dài hoặc cần xem lại nhiều lần, WireMock hỗ trợ khai báo JSON stubs trong resources. Một cấu trúc thường dùng:

~~~text
src/test/resources/
├── mappings/
│   └── stock-available.json
└── __files/
    └── stock-available-body.json
~~~

Nội dung `mappings/stock-available.json`:

~~~json
{
  "request": {
    "method": "GET",
    "url": "/api/inventory/SKU-101",
    "headers": {
      "Accept": {
        "contains": "application/json"
      }
    }
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json"
    },
    "bodyFileName": "stock-available-body.json"
  }
}
~~~

Nội dung `__files/stock-available-body.json`:

~~~json
{
  "sku": "SKU-101",
  "available": true,
  "quantity": 8
}
~~~

WireMock có quy ước **`mappings`** cho mapping JSON và **`__files`** cho body được đọc từ file. Với Spring Cloud Contract WireMock, những resources này có thể được nạp khi WireMock server khởi tạo, tùy cấu hình của annotation và đường dẫn test resources.

Bạn cũng có thể chỉ định thư mục mapping riêng:

~~~java
@SpringBootTest
@AutoConfigureWireMock(
    port = 0,
    stubs = "classpath:/inventory-stubs"
)
class InventoryClientMappingTest {
    // Các mapping JSON trong vị trí đã chỉ định.
}
~~~

Lưu ý:

- `stubs` là tham số của `@AutoConfigureWireMock` để chỉ đường dẫn nạp mapping.
- `bodyFileName` được giải quyết tương đối với **WireMock files root** (`__files` theo quy ước mặc định); nếu tùy chỉnh files root, phải kiểm tra đường dẫn tương ứng.
- Nếu test sử dụng mapping nạp từ file, không gọi `reset()` rồi bất ngờ làm mất mapping mà không nạp lại.
- File JSON hợp lệ về cú pháp chưa đủ; vẫn cần test **client thật** gọi đúng và xử lý body được trả về.

### Ưu và nhược của hai cách viết

| Cách viết | Phù hợp khi | Lưu ý |
|---|---|---|
| Java DSL `stubFor(...)` trong test | Một vài request, đọc setup gần assertion | Test dài nếu mapping phức tạp |
| JSON file mappings | Stub lớn, nhiều kịch bản, body lưu ngoài | Quản lý thư mục, files root, reset và naming |
| Stub được sinh từ Groovy/YAML contract | Muốn giữ hành vi thống nhất với producer và consumer | Cần producer contract tests + Stub Runner/artifact |

**Không đồng nhất** JSON mapping viết tay với stub được sinh từ hợp đồng: cả hai có thể chạy trên WireMock, nhưng chỉ stub đi qua quy trình Spring Cloud Contract producer verification mới có liên hệ kiểm chứng với code producer.

## 11. Quản lý trạng thái WireMock giữa các test

WireMock giữ **stub mappings** và **request journal** trong vòng đời server. Spring test có thể tái sử dụng application context qua cơ chế caching, nên không nên mặc định mỗi test method được cấp một server hoàn toàn mới.

Các tình huống gây lỗi:

| Hiện tượng | Nguyên nhân | Hướng khắc phục |
|---|---|---|
| Test thứ hai match mapping của test thứ nhất | Stub mappings còn trong server | Reset/thiết lập lại stubs có chủ đích |
| `verify(1, ...)` thấy 2 request | Request journal từ test trước chưa được dọn | Reset requests trước mỗi test hoặc tách setup |
| Mapping file tự nhiên biến mất | `reset()` đã xóa stubs nạp ban đầu | Không reset all khi phụ thuộc default mappings; nạp lại |
| Test chạy riêng thì xanh, chạy cả suite thì đỏ | Dùng context/server chung và state mutable | Isolation và tránh test parallel xung đột |
| WireMock nhận request từ client khác | Nhiều bean trỏ cùng base URL/server | Tách resource, request matcher và xác định scope test |

Với test chỉ sử dụng Java DSL để tạo stubs trong từng method, có thể làm sạch đầu mỗi test:

~~~java
@BeforeEach
void resetAndPrepare() {
    reset();
    // Sau đó mỗi test đăng ký stubFor(...) riêng.
}
~~~

Với các mapping được nạp từ `src/test/resources/mappings` hoặc `stubs=...`, cân nhắc chỉ reset request journal nếu đó là nhu cầu, hoặc nạp lại mapping sau reset. WireMock có API dọn riêng **request journal** và **mapping**; chọn đúng thao tác thay vì xóa toàn bộ một cách vô thức.

**Test chạy song song:** `@AutoConfigureWireMock` thường gắn server với Spring test context. Nếu nhiều test cùng context ghi stub vào một server dùng chung, chúng có thể tranh chấp trạng thái. Tách context, tắt parallel cho nhóm đó hoặc dùng server riêng theo nhu cầu; cổng ngẫu nhiên **không tự giải quyết tranh chấp mappings trong cùng server**.

## 12. Khác nhau giữa @AutoConfigureWireMock và Stub Runner

Hai công cụ đều có thể dùng WireMock cho HTTP, nhưng mục tiêu khác nhau.

| Tiêu chí | `@AutoConfigureWireMock` | Spring Cloud Contract Stub Runner |
|---|---|---|
| Nguồn response | Java DSL hoặc WireMock JSON mappings do test cung cấp | Stub được sinh từ hợp đồng Groovy/YAML và đóng gói |
| Có cần tọa độ artifact Maven? | Không bắt buộc | Thường có `group:artifact:version:stubs` |
| Có tự kiểm chứng producer thật? | **Không** | **Không**; việc đó do generated producer tests |
| Có thể test HTTP client thật? | Có | Có |
| Có thể simulate delay/fault tùy ý? | Có, bằng WireMock API | Chỉ khi mapping/tích hợp thực sự hỗ trợ; thường test riêng rõ ràng hơn |
| Dùng khi | Adapter/client test độc lập, debug, thử lỗi mạng | Consumer-driven contract test theo phiên bản producer |
| Nguy cơ chính | Stub viết tay có thể **lệch** với producer thật | Artifact cũ/khác revision hoặc producer chưa chạy test |
| Cách đưa vào CI | Test module consumer với WireMock embedded | Producer verification → candidate stub → consumer tests |

### Một lời hứa trong DSL cần hai phía kiểm chứng

Ví dụ contract producer Groovy:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Ton kho SKU-101'
    request {
        method 'GET'
        url '/api/inventory/SKU-101'
        headers {
            accept(applicationJson())
        }
    }
    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(sku: 'SKU-101', available: true, quantity: 8)
    }
}
~~~

**Generated producer test** kiểm tra Inventory thật có trả đúng response đã cam kết không. **Stub Runner** giúp Checkout test dựa trên chính contract đó.

Nếu Checkout tự viết một WireMock mapping `quantity=8` nhưng producer thật đã đổi thành string `"8"`, test WireMock độc lập vẫn có thể xanh. Vì vậy với những giao diện **cần kiểm tra tương thích liên dịch vụ**, nên dùng contract-generated stub và Stub Runner thay vì chỉ duy trì mapping viết tay không được kiểm chứng.

Ngược lại, khi cần test logic xử lý **HTTP timeout**, **connection reset**, hoặc một trường hợp chưa thuộc contract chính thức, `@AutoConfigureWireMock` có thể là công cụ phù hợp hơn để cô lập consumer.

### Kết hợp hai loại test

Một chiến lược thực tế:

- **Contract-driven consumer tests:** chạy với Stub Runner và candidate stub đã được producer kiểm chứng.
- **Consumer resilience tests:** chạy với `@AutoConfigureWireMock` và mappings delay/fault/edge cases do nhóm consumer kiểm soát.
- **Producer contract tests:** chạy trong repository producer, với code producer thật và base test phù hợp.
- **Integration/end-to-end tests:** bổ sung cho database, broker, TLS, proxy hoặc môi trường cần bằng chứng khác.

Tách vai trò rõ ràng giúp mỗi lần test fail biết nên điều tra contract, code producer, cách client xử lý HTTP hay hạ tầng.

## 13. @AutoConfigureWireMock không thay thế MockMvc

Hai annotation/cơ chế có thể xuất hiện trong Spring Boot test nhưng phục vụ hai hướng khác nhau:

~~~mermaid
flowchart TB
    O["Checkout Service trong test"] -->|HTTP outbound| W["WireMock giả lập Inventory"]
    I["Test của controller Checkout"] -->|HTTP inbound| M["MockMvc / WebTestClient"]
    M --> O
~~~

- `MockMvc` kiểm tra **request vào** controller/servlet stack của ứng dụng Spring MVC mà không cần HTTP socket thực.
- `@AutoConfigureWireMock` dựng một **HTTP server bên ngoài ứng dụng đang test** để kiểm tra **request đi ra** từ HTTP client.
- `@SpringBootTest` có thể dựng cả hai loại thành phần nếu cần, nhưng đừng làm một test phức tạp hơn phạm vi yêu cầu.

Nếu mục tiêu là “Inventory Controller trả JSON đúng contract”, phải dùng producer test hoặc controller test của Inventory. Nếu mục tiêu là “Checkout gọi Inventory với header đúng và xử lý JSON”, WireMock cho outbound client là lựa chọn tự nhiên.

Trong nhiều ứng dụng, dùng `@SpringBootTest` khiến context khởi động khá lớn. Với test chỉ cần một HTTP client bean, có thể thiết kế test configuration tối giản; tuy nhiên `@AutoConfigureWireMock` cần được đưa vào Spring test context đúng cách, không phải cứ đổi sang một test slice là annotation sẽ hoạt động y hệt mà không cần cấu hình thêm.

## 14. Chẩn đoán lỗi khi WireMock test thất bại

### Trường hợp A: “Connection refused”

Có thể `InventoryClient` vẫn trỏ URL production hoặc `localhost:8089` cứng thay vì `wiremock.server.port`, hoặc WireMock chưa chạy đúng Spring context.

Kiểm tra:

1. Property `inventory.base-url` thực sự được bind vào client bean lúc khởi tạo.
2. Cổng WireMock trong log/`wiremock.server.port` có đúng với URL đang gọi.
3. Bean client có tự tạo client mới với base URL cứng hay không.
4. Test có chạy đúng annotation và Spring Boot context không.

### Trường hợp B: HTTP 404 ngoài ý muốn

WireMock thường trả phản hồi không khớp mapping khi request chưa match. Kiểm tra:

- Method `GET` hay `POST`?
- Path có bị thêm context path/trailing slash?
- URL có query và mapping dùng `urlEqualTo` không?
- Header `Accept`/`Content-Type` có giống matcher không?
- JSON body và kiểu dữ liệu có khác không?

Đừng sửa response thành `404` để làm test “khớp lỗi” khi mục tiêu thật là tình huống thành công. Dùng request journal và thông tin unmatched/near misses của WireMock để biết request đã gửi khác mapping ở đâu.

### Trường hợp C: Test không tìm thấy stub mapping file

Kiểm tra `src/test/resources/mappings`, đường dẫn `stubs`, resources có được đưa vào test classpath không và root `__files` cho `bodyFileName`. Nếu test reset stubs sau khi server nạp mapping mặc định, cần điều chỉnh cách reset.

### Trường hợp D: Test timeout trên CI

Phân biệt:

- **WireMock không nhận request**: sai URL/port.
- **WireMock nhận request nhưng response bị delay**: timeout của HTTP client được kích hoạt theo cấu hình.
- **Client retry quá nhiều**: tổng thời gian vượt deadline.
- **CI khởi động context chậm**: khác với network/read timeout của một request.

Không tự tăng timeout lên rất cao mà chưa phân loại nguyên nhân. Với các phép thử phụ thuộc thời gian, dùng khoảng delay và timeout có chênh lệch đủ lớn, tránh so sánh chính xác từng millisecond.

### Trường hợp E: Test chạy đơn lẻ xanh, chạy suite fail

Khả năng cao có **request journal hoặc stub mappings chia sẻ**. Dọn đúng loại state, không chạy concurrent tests cùng cấu hình WireMock mutable hoặc tạo test context riêng khi cần.

## 15. Checklist cho một bài WireMock HTTP client test

- [ ] HTTP client của consumer là **code thật**, không bị Mockito mock toàn bộ.
- [ ] `@AutoConfigureWireMock` được sử dụng đúng dependency và Spring context.
- [ ] Cổng WireMock **động** (`port=0`) và được lấy từ `wiremock.server.port`.
- [ ] Base URL của client được cấu hình, không hardcode production URL.
- [ ] Stub matcher có đúng method, path, query, header và body quan trọng.
- [ ] Response giả lập có status, header, JSON/body kiểu dữ liệu đúng.
- [ ] Test assert dữ liệu **sau khi client deserialize** hoặc hành vi ứng dụng.
- [ ] Test verify ít nhất các request quan trọng mà client đã thực sự gửi.
- [ ] Không coi HTTP `404` do unmatched mapping là `404` nghiệp vụ có chủ đích.
- [ ] State WireMock được làm sạch/cô lập đúng giữa các test.
- [ ] Nếu dùng file mappings, test resources và files root được cấu hình đúng.
- [ ] Nếu kiểm tra timeout/fault, client timeout và retry được cấu hình thật.
- [ ] Test có thể chạy cùng CI, không tranh cổng cố định hay state dùng chung.
- [ ] Những hành vi cần compatibility được bảo vệ thêm bằng contract + Stub Runner.
- [ ] CI chạy generated producer tests trước khi công bố stub để consumer sử dụng.

## 16. Bài thực hành: sửa test đang gọi sai nơi

### Đề bài

Nhóm Checkout viết test:

~~~java
@SpringBootTest
@AutoConfigureWireMock(port = 8089)
class InventoryClientTest {

    @Autowired InventoryClient inventoryClient;

    @Test
    void testStock() {
        stubFor(get(urlEqualTo("/api/inventory/SKU-101"))
            .willReturn(okJson("""
                {"sku":"SKU-101","available":true,"quantity":8}
                """)));

        StockView result = inventoryClient.getStock("SKU-101");
        assertThat(result.quantity()).isEqualTo(8);
    }
}
~~~

Nhưng `InventoryClient` đang nhận base URL từ cấu hình production: `https://inventory.internal.example`. Test đôi khi gọi được dịch vụ thật, đôi khi lỗi mạng; trên CI lại không thể gọi dịch vụ đó.

**Câu hỏi 1:** Sai ở đâu?

**Gợi ý:** WireMock được dựng ở cổng `8089` nhưng client **không được cấu hình trỏ vào WireMock**. Chỉ gắn annotation không tự thay thế URL của mọi HTTP client trong ứng dụng.

**Câu hỏi 2:** Sửa test theo hướng nào?

~~~java
@SpringBootTest(properties = {
    "inventory.base-url=http://localhost:${wiremock.server.port}"
})
@AutoConfigureWireMock(port = 0)
class InventoryClientTest {
    // Cấu hình stub và assert như ví dụ chính.
}
~~~

Điều kiện là `InventoryClient` phải thật sự lấy `inventory.base-url` từ Spring configuration. Dùng cổng động giúp giảm va chạm giữa các lần chạy.

**Câu hỏi 3:** Nếu stub trả `quantity: 8` nhưng producer thật hiện trả string `"8"`, test WireMock độc lập có tìm ra không?

**Đáp án:** Không nhất thiết. Nó chỉ kiểm tra consumer đối với **response mẫu được khai báo bằng tay**. Muốn phát hiện lệch giữa hợp đồng và producer thật, chạy generated producer contract test và dùng candidate stub qua Stub Runner.

**Câu hỏi 4:** Có cần thêm `verify(...)` không?

**Đáp án:** Nên có khi method/path/header/query là một phần quan trọng của giao diện. Nhờ đó test có bằng chứng rằng client gửi request đúng, không chỉ kiểm tra response sau deserialize.

**Câu hỏi 5:** Nếu test timeout fail ngay lập tức, bước điều tra đầu tiên?

**Đáp án:** Kiểm tra URL/port, request có đến WireMock không, có mapping match không; sau đó mới xem delay và timeout của HTTP client. Không tự tăng thời gian chờ khi request còn chưa đến server.

### Bài tập nâng cao

Hãy viết ba test độc lập cho `InventoryClient`:

1. `200` + JSON hợp lệ → `StockView` có đúng kiểu và giá trị.
2. `404` + `{"code":"SKU_NOT_FOUND"}` → client hoặc application adapter phát hiện lỗi không tìm thấy và bảo toàn mã lỗi theo thiết kế.
3. `503` hoặc delay dài hơn read timeout → consumer chuyển sang nhánh “không thể xác minh tồn kho”, không tự hiểu là “hết hàng”.

Với mỗi test, giải thích vì sao stubs khác nhau và cách làm sạch WireMock trước khi chạy. Nếu consumer có retry, hãy verify số request gửi ra và bảo đảm budget/side effects đúng chính sách.

## 17. Ghi nhớ và tài liệu tham khảo

**`@AutoConfigureWireMock` giúp kiểm thử HTTP client độc lập bằng cách dựng một WireMock server trong Spring test context.** Để test có ý nghĩa, client thật phải được cấu hình trỏ tới server đó thông qua `wiremock.server.port`, test phải khai báo request matcher/response phù hợp và xác nhận cả dữ liệu xử lý lẫn HTTP request được gửi.

**Đừng nhầm một HTTP stub tự viết với hợp đồng đã được producer kiểm chứng.** Khi mục tiêu là kiểm soát tương thích giữa các dịch vụ, hãy sử dụng Spring Cloud Contract Groovy/YAML DSL, chạy generated producer tests, đóng gói stub theo revision và cho consumer chạy Stub Runner. WireMock độc lập vẫn rất hữu ích để thử lỗi HTTP, timeout, request construction và cách client hoạt động khi producer không sẵn sàng.

### Tài liệu tham khảo

- [Spring Cloud Contract — WireMock](https://docs.spring.io/spring-cloud-contract/reference/project-features-wiremock.html): cấu hình `@AutoConfigureWireMock`, random port, stubs và resource files.
- [WireMock — Stubbing](https://wiremock.org/docs/stubbing/): Java DSL và JSON stub mappings.
- [WireMock — Verifying Requests](https://wiremock.org/docs/verifying/): kiểm tra request journal và số lần gọi.
- [Spring Cloud Contract — Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-boot.html): consumer chạy stub sinh từ contract.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): cách sử dụng `RestClient`.

**Kết luận thực hành:** kiểm thử client bằng `@AutoConfigureWireMock` cần ba điều: **đúng server**, **đúng HTTP request**, **đúng cách consumer xử lý response**. Khi bổ sung producer contract tests và Stub Runner vào CI, nhóm vừa có test HTTP client nhanh, độc lập, vừa có cơ chế phát hiện các thay đổi API không tương thích giữa producer và consumer.

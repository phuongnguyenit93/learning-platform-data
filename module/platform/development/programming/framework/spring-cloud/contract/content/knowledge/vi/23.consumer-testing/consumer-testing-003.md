# Xác minh serialization, deserialization và ánh xạ lỗi

## 1. Vì sao consumer test phải kiểm tra cả ba khâu?

Trong **Spring Cloud Contract (SCC)**, một hợp đồng Groovy DSL hoặc YAML DSL mô tả request mà **consumer** phải gửi và response mà **producer** cam kết trả. SCC sinh **generated tests** để kiểm chứng implementation producer, đồng thời sinh **HTTP stub** để consumer kiểm thử độc lập với producer bằng **Stub Runner**. Khi được tích hợp đúng vào CI, hai hướng kiểm chứng này giúp phát hiện thay đổi API không tương thích.

Tuy nhiên, một client có thể lỗi dù stub đang trả JSON đúng, vì ranh giới HTTP không chỉ là đối tượng Java:

- **Serialization (mã hóa request):** client phải chuyển đối tượng Java thành **đúng method, path, query, headers và bytes JSON** mà producer mong đợi.
- **Deserialization (giải mã response):** client phải chuyển HTTP response thành DTO/kiểu dữ liệu đúng, không làm mất trường cần thiết hoặc âm thầm đổi ý nghĩa dữ liệu.
- **Error mapping (ánh xạ lỗi):** client phải hiểu status và error body theo hợp đồng, chuyển thành kết quả/exception nghiệp vụ phù hợp, thay vì coi mọi `404`, `409` hoặc `503` là cùng một lỗi.

Ví dụ, producer cam kết `quantity` là số JSON, nhưng DTO consumer lưu dưới dạng `String`; một số trường hợp có thể được thư viện tự chuyển kiểu, làm che lỗi. Hoặc producer trả lỗi có cấu trúc `{"code":"SKU_NOT_FOUND"}`, nhưng consumer chỉ bắt mọi HTTP 404 rồi coi là “không có SKU” — kể cả khi 404 xuất phát từ **WireMock không match request**.

Bài thuộc chương **Kiểm thử consumer**, tập trung trực tiếp vào **xác minh serialization, deserialization và ánh xạ lỗi**. Các ví dụ dùng **Checkout Service** làm consumer và **Inventory Service** làm producer, với Spring Framework `RestClient`, Jackson và SCC Stub Runner.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích ba biên dữ liệu của HTTP consumer và vì sao cần kiểm thử bằng client thật.
2. Viết hợp đồng Groovy/YAML cho request JSON, response thành công và error response.
3. Kiểm tra serialization về method, URL, `Content-Type`, `Accept`, tên trường và kiểu số/boolean.
4. Thiết kế DTO Jackson xử lý trường thiếu, `null`, field lạ, enum, ngày giờ và tiền tệ rõ ràng.
5. Viết client chuyển `404 SKU_NOT_FOUND`, `503 INVENTORY_UNAVAILABLE` và lỗi transport/protocol thành các kết quả khác nhau.
6. Phân biệt **business 404** với **unmatched WireMock 404**.
7. Tạo consumer contract tests bằng Stub Runner và negative tests chứng minh lỗi được phát hiện.
8. Đưa producer tests, stub ứng viên và consumer tests vào CI để kiểm tra breaking changes.

## 2. Luồng dữ liệu thực tế qua ranh giới HTTP

~~~mermaid
sequenceDiagram
    participant A as Checkout Application
    participant C as InventoryClient
    participant W as WireMock qua Stub Runner
    A->>C: reserve(SKU-123, 2)
    Note over C: Serialize Java request -> HTTP
    C->>W: POST /api/reservations + JSON body
    W-->>C: HTTP 201 + JSON response
    Note over C: Deserialize JSON -> Java DTO
    C-->>A: ReservationResponse
    A->>C: getStock(SKU-404)
    C->>W: GET /api/inventory/SKU-404
    W-->>C: HTTP 404 + ApiError JSON
    Note over C: Map HTTP error -> domain exception
    C-->>A: InventoryNotFoundException
~~~

Trên sơ đồ, Stub Runner đóng vai trò **producer giả lập bằng contract**, còn `InventoryClient` là **client thực của Checkout**. Sự khác biệt này quan trọng: không được mock chính `InventoryClient` rồi tự trả `StockResponse` mẫu, vì như vậy bài test bỏ qua serialization và deserialization.

| Biên cần bảo vệ | Input | Output | Kiểu lỗi có thể phát hiện |
|---|---|---|---|
| Serialization | DTO Java + method gọi | HTTP method/path/query/headers/body | Đổi tên trường, nhầm kiểu, sai content type, URL không encode đúng |
| Request matching của stub | HTTP request thật | Mapping được chọn | Thiếu header, sai URL, JSON không khớp |
| Deserialization | HTTP 2xx + JSON | DTO Java | Thiếu field, sai kiểu, lệch property name, dữ liệu null |
| Error mapping | HTTP 4xx/5xx + error body | Exception/kết quả nghiệp vụ | Nhầm 404, bỏ qua mã lỗi, coi 503 là không tìm thấy |
| Consumer business logic | DTO hoặc domain error | Hành vi Checkout | Tính sai giá/tồn kho, fallback không phù hợp |

**Nguyên tắc chính:** bài test phải đi qua **lời gọi HTTP client production thật**, không chỉ gọi thư viện JSON trực tiếp hoặc assert một response body mẫu đã hardcode.

## 3. Định nghĩa các tình huống API đã cam kết

Ta dùng ba hành vi chính của Inventory Service:

| Tình huống | Request | Response đã cam kết |
|---|---|---|
| Tồn kho hiện có | `GET /api/inventory/SKU-123` | `200`, `StockResponse` JSON |
| SKU không tồn tại | `GET /api/inventory/SKU-404` | `404`, `ApiError(code=SKU_NOT_FOUND)` |
| Backend Inventory tạm lỗi | `GET /api/inventory/SKU-503` | `503`, `ApiError(code=INVENTORY_UNAVAILABLE)` |

Response thành công:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sku": "SKU-123",
  "available": true,
  "quantity": 12
}
~~~

Response không tìm thấy:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json

{
  "code": "SKU_NOT_FOUND",
  "message": "SKU does not exist",
  "traceId": "trace-demo-404"
}
~~~

Response dịch vụ không sẵn sàng:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json

{
  "code": "INVENTORY_UNAVAILABLE",
  "message": "Try again later",
  "traceId": "trace-demo-503"
}
~~~

Để kiểm thử **serialization request body**, ta dùng thêm API:

~~~http
POST /api/reservations HTTP/1.1
Content-Type: application/json
Accept: application/json

{"sku":"SKU-123","quantity":2}
~~~

Producer cam kết trả:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{"reservationId":"R-1001","status":"RESERVED"}
~~~

Đây là **API giả định dùng trong bài học**, không phải đường dẫn hoặc status mặc định của Spring Cloud Contract. Quan trọng là ba tình huống GET và một tình huống POST giúp kiểm tra đầy đủ request serializer, success deserializer và error translator.

## 4. Serialization là gì và cần assert gì?

Serialization biến dữ liệu trong tiến trình consumer thành cấu trúc giao thức. Với Spring HTTP client và Jackson, một record Java có thể được chuyển sang JSON, nhưng kết quả còn phụ thuộc cấu hình ObjectMapper, HTTP message converters và client.

Ví dụ:

~~~java
public record ReservationRequest(String sku, int quantity) {}
~~~

Mục tiêu gửi:

~~~json
{"sku":"SKU-123","quantity":2}
~~~

Một số sai khác có thể phá hợp đồng:

| Consumer thực gửi | Vấn đề | Vì sao stub/producer có thể từ chối |
|---|---|---|
| `{"sku":"SKU-123","quantity":2}` | Đúng | Khớp kiểu và tên trường |
| `{"productId":"SKU-123","quantity":2}` | Đổi tên `sku` | Producer không biết `productId` |
| `{"sku":"SKU-123","quantity":"2"}` | Quantity là string | Contract yêu cầu JSON number |
| `{"sku":"SKU-123","quantity":null}` | Quantity null | Có thể vi phạm validation |
| `{"sku":"SKU-123"}` | Thiếu quantity | Có thể bị từ chối hoặc bị default sai |
| `{"sku":"SKU-123","quantity":2,"debug":true}` | Trường thừa | Tùy producer và policy schema, không phải luôn breaking |
| Body JSON nhưng `Content-Type: text/plain` | Header sai | Producer hoặc stub matcher có thể từ chối |
| POST sai path hoặc query | Định tuyến sai | Mapping không match |

**Không nên kiểm tra JSON bằng cách so sánh byte string một cách mù quáng** nếu contract không yêu cầu thứ tự các property hay khoảng trắng. Một WireMock `equalToJson` hoặc JSONPath matcher thích hợp sẽ kiểm tra semantics JSON tốt hơn; khi thứ tự bytes hoặc chữ ký HMAC thực sự quan trọng, cần test riêng ở đúng cấp độ byte.

## 5. Contract Groovy DSL cho POST request body

Giả sử producer quản lý hợp đồng tại:

~~~text
src/test/resources/contracts/reservations/create-reservation.groovy
~~~

Nội dung minh họa:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Checkout tạo reservation bằng JSON request'

    request {
        method POST()
        url '/api/reservations'

        headers {
            contentType(applicationJson())
            accept(applicationJson())
        }

        body(
            sku: 'SKU-123',
            quantity: 2
        )
    }

    response {
        status CREATED()
        headers {
            contentType(applicationJson())
        }
        body(
            reservationId: 'R-1001',
            status: 'RESERVED'
        )
    }
}
~~~

Ý nghĩa với consumer testing:

1. `method POST()` và `url` trở thành điều kiện request matching.
2. `Content-Type` và `Accept` là header giao tiếp mà client cần gửi đúng.
3. `request.body` là mẫu request đúng, phục vụ producer test và sinh WireMock matcher.
4. `response.status CREATED()` tương ứng HTTP 201.
5. `response.body` là dữ liệu mà stub trả cho consumer khi request match.
6. Generated producer test dùng contract để kiểm chứng **implementation producer thật**, không chỉ WireMock.

Nếu muốn cho phép SKU động, có thể dùng matcher phù hợp (regex/JSONPath) thay vì cố định mọi giá trị. Nhưng **mẫu thực tế gửi trong producer test** vẫn phải hợp lệ và matcher không được quá rộng đến mức nhận JSON sai kiểu.

## 6. Cách tương đương trong YAML DSL

Nếu dự án chọn YAML:

~~~yaml
description: Checkout tạo reservation bằng JSON request
name: create_reservation

request:
  method: POST
  url: /api/reservations
  headers:
    Content-Type: application/json
    Accept: application/json
  body:
    sku: SKU-123
    quantity: 2

response:
  status: 201
  headers:
    Content-Type: application/json
  body:
    reservationId: R-1001
    status: RESERVED
~~~

Một số lưu ý với YAML:

- `quantity: 2` là **số**; `quantity: '2'` là **chuỗi**.
- `available: true` là boolean; `available: 'true'` là chuỗi.
- `null`, chuỗi rỗng `''` và **thiếu field** là những trạng thái khác nhau.
- Đặt `request`/`response` hoặc `headers` sai thụt lề có thể khiến DSL lỗi hoặc sai semantics.
- Có thể dùng `request.matchers.body` nếu phiên bản SCC hỗ trợ loại matcher phù hợp.

Hai ví dụ Groovy và YAML là **hai lựa chọn thay thế** cho một contract. Không cần đưa cả hai vào cùng thư mục nếu tạo trùng test/stub.

## 7. WireMock matching bảo vệ serialization của client như thế nào?

SCC chuyển phần request của contract thành **WireMock request predicates**. Một mapping khái niệm từ POST ở trên có hình dạng:

~~~json
{
  "request": {
    "method": "POST",
    "url": "/api/reservations",
    "headers": {
      "Content-Type": {
        "contains": "application/json"
      },
      "Accept": {
        "contains": "application/json"
      }
    },
    "bodyPatterns": [
      {
        "equalToJson": "{\"sku\":\"SKU-123\",\"quantity\":2}"
      }
    ]
  },
  "response": {
    "status": 201,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "reservationId": "R-1001",
      "status": "RESERVED"
    }
  }
}
~~~

Đây là **ví dụ WireMock**, không phải cam kết rằng một phiên bản SCC cụ thể sẽ sinh ra đúng từng thuộc tính, matcher hay `jsonBody`. Trong output thực, SCC có thể chọn `body`, `matchesJsonPath`, predicate khác hoặc tên file mapping riêng.

Kiểm tra mapping đã sinh để biết chính xác nó có bắt:

- Đúng method và URL;
- Đúng Content-Type/Accept nếu hợp đồng yêu cầu;
- Đúng tên field `sku`, kiểu số của `quantity`;
- Không vô tình nhận `quantity:"2"`;
- Không vô tình nhận request mà consumer lẽ ra không được gửi.

**Cảnh báo:** WireMock request matcher có thể cho phép những dạng JSON tương đương hoặc trường thừa theo cấu hình. Nếu strict schema là yêu cầu, hãy chọn matcher/cấu hình phù hợp hoặc bổ sung test validation ở producer. Không suy luận một mapping có `equalToJson` sẽ mặc định áp mọi quy tắc schema/Bean Validation.

## 8. Viết consumer HTTP client gửi request đúng

Một ví dụ với `RestClient` (Spring Framework 6.1+; chọn dòng Spring Boot/Cloud phù hợp):

~~~java
package com.example.checkout;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class ReservationClient {

    private final RestClient client;

    public ReservationClient(RestClient.Builder builder,
            @org.springframework.beans.factory.annotation.Value(
                "${inventory.base-url}") String baseUrl) {
        this.client = builder.baseUrl(baseUrl).build();
    }

    public ReservationResponse reserve(String sku, int quantity) {
        ReservationRequest request =
                new ReservationRequest(sku, quantity);

        ReservationResponse response = client.post()
                .uri("/api/reservations")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .body(request)
                .retrieve()
                .body(ReservationResponse.class);

        if (response == null || response.reservationId() == null) {
            throw new IllegalStateException(
                    "Reservation response is missing required fields");
        }

        return response;
    }

    public record ReservationRequest(String sku, int quantity) {}

    public record ReservationResponse(
            String reservationId, String status) {}
}
~~~

Bộ ví dụ giả định có `RestClient.Builder` được cấu hình bởi Spring Boot, Jackson HTTP message converters và property `inventory.base-url` chỉ vào Inventory stub trong consumer tests.

Những điểm cần chú ý:

- `.body(request)` sử dụng JSON serializer thực của client.
- `.contentType(application/json)` mô tả **format request**.
- `.accept(application/json)` thông báo kiểu response mong muốn.
- `.retrieve().body(ReservationResponse.class)` giải mã response, không dùng DTO mock.
- Nếu stub không match vì sai path/header/body, HTTP response có thể là WireMock unmatched 404; test phải fail thay vì âm thầm chọn response giả.

Bài test chỉ chứng minh semantics của scenario được mô tả. Client production còn cần timeout, retry, authorization và chính sách xử lý các lỗi khác, được kiểm tra bằng các bài test phù hợp.

## 9. Stub Runner test thực thi serialization đầu-cuối

Sau khi Inventory producer đã sinh và đóng gói stub, Checkout test có thể dùng `@AutoConfigureStubRunner`.

~~~java
package com.example.checkout;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties =
    "inventory.base-url=http://localhost:18081")
@AutoConfigureStubRunner(
    ids = "com.example:inventory-service:1.3.0-rc1:stubs:18081",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class ReservationSerializationContractTest {

    @Autowired
    ReservationClient reservationClient;

    @Test
    void sendsValidJsonAndDeserializesCreatedResponse() {
        var result = reservationClient.reserve("SKU-123", 2);

        assertThat(result.reservationId()).isEqualTo("R-1001");
        assertThat(result.status()).isEqualTo("RESERVED");
    }
}
~~~

Giải thích:

1. Consumer test dùng **client production** và gọi HTTP thật qua WireMock.
2. Stub Runner tải artifact có classifier `stubs`.
3. Mapping được sinh từ contract có điều kiện cho **POST JSON đúng**.
4. Nếu request serialize sai và không match, test phải fail — đó là tín hiệu cần kiểm tra.
5. Response stub được giải mã qua Jackson/message converters thành `ReservationResponse`.
6. Assertions kiểm tra dữ liệu sau **deserialization**, không chỉ status của WireMock.

Port 18081 là ví dụ **cố định**, phù hợp với minh họa. CI chạy song song nên cân nhắc dynamic port và lookup/bean wiring chính xác. Khi `LOCAL`, artifact stub phải được cài vào local repository của môi trường test; khi CI chạy tách máy, cần dùng repository remote hoặc cơ chế cung cấp artifact phù hợp.

## 10. Một test xanh chưa chứng minh request khớp đủ chặt

Đôi khi mapping quá rộng, ví dụ chỉ match:

~~~json
{
  "request": {
    "method": "POST",
    "url": "/api/reservations"
  },
  "response": {
    "status": 201,
    "jsonBody": {
      "reservationId": "R-1001",
      "status": "RESERVED"
    }
  }
}
~~~

Nếu đây là toàn bộ điều kiện, client có thể gửi body sai hoặc thiếu header vẫn nhận 201. Consumer test xanh nhưng **không thực sự bảo vệ serialization**.

Cách phát hiện:

- Mở generated WireMock mapping và xác nhận có `bodyPatterns`/headers cần thiết.
- Tạo **negative test** hoặc HTTP request thử với body sai kiểu `quantity:"2"`; request đó không nên được xử lý như hợp đồng hợp lệ nếu strict type là yêu cầu.
- Đọc WireMock request journal/near misses để biết request thực tế đã đi vào server.
- Trong producer tests, xác minh request validation của service thật, vì stub matcher không thay mọi ràng buộc nghiệp vụ.

**Phân biệt trách nhiệm:** SCC bảo vệ những cam kết đã khai báo; nếu contract không kiểm tra một trường, consumer test với stub đó không thể tự suy ra trường ấy là bắt buộc.

## 11. Deserialization: JSON response thành kiểu Java

Phía GET thành công nhận:

~~~json
{
  "sku": "SKU-123",
  "available": true,
  "quantity": 12
}
~~~

Một DTO Java nên phản ánh **kiểu thực của API**:

~~~java
package com.example.checkout;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonIgnoreProperties(ignoreUnknown = true)
public record StockResponse(
        @JsonProperty("sku") String sku,
        @JsonProperty("available") Boolean available,
        @JsonProperty("quantity") Integer quantity) {
}
~~~

Vì sao dùng `Boolean` và `Integer` thay `boolean`/`int` trong ví dụ consumer?

- Với primitive `boolean`, một field thiếu hoặc null có thể bị chuyển thành giá trị mặc định `false` theo cấu hình Jackson, khiến consumer **khó phân biệt “không có dữ liệu” với “thực sự hết hàng”**.
- Với `Boolean`, có thể phát hiện `null` rồi báo lỗi contract/protocol rõ ràng.
- Với `Integer`, có thể phát hiện field `quantity` thiếu thay vì âm thầm dùng 0.
- `@JsonProperty` thể hiện tường minh tên field trên wire.
- `@JsonIgnoreProperties(ignoreUnknown=true)` cho phép **thêm field không gây hỏng client** theo chính sách forward compatibility đã chọn.

Tuy nhiên, **Jackson không tự bảo đảm các field record là bắt buộc chỉ vì dùng `@JsonProperty`**. Việc validate `sku`, `available` và `quantity` cần được thực hiện sau deserialize hoặc qua Bean Validation/cấu hình strict phù hợp.

## 12. Kiểm tra DTO sau khi deserialize

Một validate function rõ ràng:

~~~java
package com.example.checkout;

public final class StockResponseValidator {

    private StockResponseValidator() {}

    public static StockResponse requireValid(
            StockResponse response, String requestedSku) {

        if (response == null) {
            throw new UpstreamProtocolException(
                    "Inventory 2xx response body is empty");
        }
        if (response.sku() == null
                || !requestedSku.equals(response.sku())) {
            throw new UpstreamProtocolException(
                    "Inventory sku does not match request");
        }
        if (response.available() == null) {
            throw new UpstreamProtocolException(
                    "Inventory field available is missing or null");
        }
        if (response.quantity() == null
                || response.quantity() < 0) {
            throw new UpstreamProtocolException(
                    "Inventory quantity missing or negative");
        }
        if (response.available() != (response.quantity() > 0)) {
            throw new UpstreamProtocolException(
                    "Inventory available/quantity inconsistent");
        }
        return response;
    }
}
~~~

Ở ví dụ, `UpstreamProtocolException` là một exception phía consumer do dự án tự định nghĩa (được minh họa ở phần ánh xạ lỗi). Quy tắc `available == (quantity > 0)` là **quy tắc nghiệp vụ giả định** của API demo; trong hệ thống có reserved stock hoặc backorder, quan hệ này có thể khác và phải được định nghĩa bằng contract thật.

Tại sao cần validate sau parse?

| JSON | Jackson có thể tạo DTO? | Lý do vẫn cần kiểm tra |
|---|---|---|
| Đủ các field đúng kiểu | Có | Kiểm tra quan hệ giữa các field |
| Thiếu `available` | Có thể, giá trị null | Không được coi là hết hàng |
| `available:null` | Có thể, null | Không được âm thầm mặc định false |
| `quantity:-1` | Có | Giá trị không hợp lệ nghiệp vụ |
| `sku:"SKU-OTHER"` | Có | Response không tương ứng request |
| `quantity:"12"` | Có thể bị coercion tùy ObjectMapper | Nếu strict type, cần cấu hình chống coercion hoặc kiểm tra raw JSON |
| Body `null` hoặc rỗng | Có thể trả null/exception | Không coi 2xx là thành công hợp lệ |

**Không nên coi 200 HTTP là bằng chứng payload đã đúng.** Một 200 với body sai schema phải dẫn đến lỗi protocol rõ ràng, không chuyển thành dữ liệu nghiệp vụ hợp lệ.

## 13. Phân biệt absent, null, empty và kiểu sai

Bốn trạng thái trong JSON có ý nghĩa khác nhau:

~~~json
{"sku":"SKU-123","available":false,"quantity":0}
~~~

~~~json
{"sku":"SKU-123","available":null,"quantity":0}
~~~

~~~json
{"sku":"SKU-123","quantity":0}
~~~

~~~json
{"sku":"SKU-123","available":"false","quantity":"0"}
~~~

- **`false`**: giá trị boolean có nghĩa, không được xem là thiếu.
- **`null`**: field xuất hiện nhưng không có giá trị.
- **Absent**: field không tồn tại trong payload.
- **String `"false"`/`"0"`**: khác JSON boolean/number.

Với Java record chỉ có `Boolean available`, trạng thái **absent** và **explicit null** thường đều tạo `null`; nếu API cần phân biệt, phải kiểm tra `JsonNode.has(...)` và `isNull(...)` hoặc dùng deserializer/validation riêng.

Ví dụ kiểm tra cấu trúc nguyên bản:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

JsonNode root = mapper.readTree(rawJson);

if (!root.has("available")) {
    throw new UpstreamProtocolException(
        "Field available is absent");
}
if (root.get("available").isNull()) {
    throw new UpstreamProtocolException(
        "Field available is explicitly null");
}
if (!root.get("available").isBoolean()) {
    throw new UpstreamProtocolException(
        "Field available must be JSON boolean");
}
~~~

Đoạn code giả định `mapper` là ObjectMapper và `rawJson` là response string đã nhận; cần đặt bên trong method có xử lý `JsonProcessingException` phù hợp.

Trong consumer tests, nên có các **negative payload cases** quan trọng để chứng minh client **không lặng lẽ chấp nhận** thiếu/null/sai kiểu khi contract yêu cầu strict. Không nhất thiết đưa mọi payload bất hợp lệ vào artifact stubs chuẩn của producer; có thể dùng một WireMock fixture riêng cho resilience/protocol negative tests.

## 14. Jackson property naming: đúng wire name mới là đúng contract

Producer có thể dùng snake_case:

~~~json
{"sku":"SKU-123","available":true,"quantity_available":12}
~~~

Nếu consumer DTO lại có field `quantityAvailable` mà không có annotation/naming strategy, việc map phụ thuộc cấu hình Jackson. Có thể đặt rõ:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

public record StockWireDto(
        String sku,
        Boolean available,
        @JsonProperty("quantity_available")
        Integer quantityAvailable) {
}
~~~

Các quy tắc cần thống nhất:

- `quantity_available` khác `quantityAvailable` trong JSON; JSON property names **phân biệt chữ và ký tự**.
- `@JsonProperty` trên DTO là một cách ghi rõ tên thuộc contract.
- Naming strategy `SNAKE_CASE` có thể làm thay đổi **mọi field**, cần xét tác động khi refactor.
- Nếu producer đổi tên field, consumer cần xem đó là một **potential breaking change**, không tự đổi DTO để làm test xanh mà bỏ qua consumer khác.
- Header HTTP không có cùng quy tắc case-sensitive như JSON property; không áp dụng một logic cho cả hai.

Một test DTO riêng bằng ObjectMapper có ích nhưng chưa đủ: phải kiểm tra **RestClient dùng cùng ObjectMapper/message converters** như trong môi trường consumer thực, vì cấu hình test tách biệt có thể che sai khác.

## 15. Trường lạ và forward compatibility

Một thay đổi additive thường gặp:

~~~json
{
  "sku": "SKU-123",
  "available": true,
  "quantity": 12,
  "warehouse": "HCM-01"
}
~~~

Nếu consumer **không cần** `warehouse`, việc bỏ qua field lạ có thể tăng khả năng tương thích khi producer bổ sung metadata. Với DTO:

~~~java
@JsonIgnoreProperties(ignoreUnknown = true)
public record StockResponse(
    String sku, Boolean available, Integer quantity) {}
~~~

consumer có thể vẫn giải mã thành công.

Nhưng có hai mặt cần cân nhắc:

| Chính sách | Ưu điểm | Nguy cơ |
|---|---|---|
| **Ignore unknown fields** | Chịu được phần lớn thay đổi thêm field | Có thể bỏ qua field mới lẽ ra mang ý nghĩa bảo mật/semantics |
| **Fail on unknown fields** | Phát hiện thay đổi schema không được dự kiến | Có thể phá consumer vì một field additive vô hại |
| **Allow unknown + validate required/critical fields** | Cân bằng khả năng tiến hóa với tính đúng | Cần thiết kế validation và test rõ ràng |

Chính sách không có đáp án chung cho mọi API. Đối với response JSON có khả năng mở rộng, **cho phép field lạ nhưng kiểm tra chặt field bắt buộc** là một chiến lược hợp lý. Với message/command nhạy cảm, việc bỏ qua field có thể không được chấp nhận.

Đừng nhầm “ignore unknown” với “ignore missing”: hai chính sách phục vụ mục tiêu khác nhau.

## 16. Jackson coercion có thể che lỗi kiểu

Một consumer nhận `{"quantity":"12"}` có thể vẫn parse vào `Integer` tùy cấu hình coercion của Jackson. Nếu hợp đồng quy định **JSON number**, đừng chỉ kiểm tra object Java sau parse rồi suy ra raw JSON đúng kiểu.

Các giải pháp:

1. Dùng **JSONPath/type matcher** trong contract và xem generated mapping/test.
2. Cấu hình ObjectMapper strict cho những kiểu quan trọng, ví dụ giới hạn coercion của String→Integer hoặc Float→Integer tùy phiên bản Jackson.
3. Kiểm tra `JsonNode.isNumber()`, `isBoolean()`, `isTextual()` khi cần bảo vệ chính xác kiểu wire.
4. Viết consumer negative tests với body `quantity:"12"` và `quantity:12.5`, quan sát behavior thực tế.

Với trường tiền tệ, timestamp và enum, coercion có thể nguy hiểm hơn JSON number đơn giản: một string trống bị xem như null, enum lạ thành null hoặc số có phần lẻ bị làm tròn có thể tạo sai nghiệp vụ. Cần xác định **tính strict theo domain**, không chỉ theo việc thư viện có parse được hay không.

## 17. Enum và giá trị mới từ producer

Giả sử Reservation API trả:

~~~json
{"reservationId":"R-1001","status":"RESERVED"}
~~~

Consumer dùng enum:

~~~java
public enum ReservationStatus {
    RESERVED,
    CONFIRMED,
    CANCELLED
}
~~~

Nếu producer sau này thêm `EXPIRED`, Jackson có thể ném lỗi khi deserialize enum chưa biết, tùy cấu hình. Đây có thể là **breaking change** với consumer cũ, dù chỉ là “thêm một giá trị”.

Các lựa chọn thiết kế:

- Nếu enum là tập đóng theo contract, cần test đảm bảo producer **không phát giá trị chưa được hỗ trợ**.
- Nếu producer cần mở rộng giá trị, consumer có thể dùng cơ chế `UNKNOWN` hoặc đọc string rồi xử lý fallback theo policy.
- Không cấu hình “unknown enum → null” mà không validate; giá trị null có thể khiến consumer đi nhầm nhánh nghiệp vụ.
- Tên enum Java, serialized value và wire format cần được kiểm tra bằng contract/DTO; một `@JsonProperty` cho field không tự chuyển giá trị enum theo tên mong muốn.
- Các hành vi không biết trạng thái nên rõ ràng: từ chối, bỏ qua có log, retry hay chuyển sang trạng thái an toàn.

Một consumer contract test với stub cũ chỉ chứa `RESERVED` **không chứng minh** consumer đã sẵn sàng cho `EXPIRED`. Cần tạo case ứng viên hoặc test decode riêng khi producer muốn mở rộng enum.

## 18. Số tiền và thời gian: tránh mất ý nghĩa khi deserialize

Hai kiểu dữ liệu thường gây lỗi âm thầm:

### 18.1. Tiền tệ

Ví dụ API Pricing trả:

~~~json
{"sku":"SKU-123","price":"150000.50","currency":"VND"}
~~~

Nếu `price` được mô tả là **string thập phân**, DTO dùng `BigDecimal` có thể được Jackson chuyển đổi theo cấu hình, nhưng contract vẫn phải nói rõ **wire type**. Nếu API quy định JSON number, ví dụ:

~~~json
{"sku":"SKU-123","price":150000.50,"currency":"VND"}
~~~

hãy kiểm tra số decimal và độ chính xác. Tránh dùng `double` cho phép tính tiền nhạy cảm với làm tròn. Có thể dùng `BigDecimal` hoặc số nguyên theo đơn vị nhỏ nhất, kèm quy tắc currency/rounding.

### 18.2. Ngày giờ

Ví dụ:

~~~json
{"lastUpdatedAt":"2026-11-24T04:00:00Z"}
~~~

Chọn `Instant` hoặc `OffsetDateTime` theo semantics; định dạng ISO-8601, offset/timezone và Jackson Java Time module phải được cấu hình đúng. Một timestamp không có offset, ví dụ `"2026-11-24T11:00:00"`, có thể bị hiểu thành local time khác nhau giữa môi trường.

Nên test cả **format** lẫn **semantics** khi consumer phụ thuộc vào thời gian. Không dùng System default timezone hoặc floating-point equality ngẫu nhiên để xác nhận contract.

## 19. Ánh xạ lỗi: status không đủ để xác định nghiệp vụ

HTTP có nhiều loại lỗi, nhưng consumer thường cần biết chính xác **loại lỗi nghiệp vụ**.

| HTTP status | Error body minh họa | Hướng xử lý trong Checkout |
|---|---|---|
| `400` | `INVALID_REQUEST` | Sửa input/validation, không retry tự động |
| `404` | `SKU_NOT_FOUND` | Trả nghiệp vụ “sản phẩm không tồn tại” |
| `409` | `RESERVATION_CONFLICT` | Có thể yêu cầu retry theo semantics/idempotency |
| `422` | `INVALID_QUANTITY` | Báo input vi phạm quy tắc, thường không retry |
| `500` | `INTERNAL_ERROR` | Lỗi server; có thể retry có kiểm soát tùy policy |
| `503` | `INVENTORY_UNAVAILABLE` | Retry/backoff hoặc fallback theo ngân sách |
| Không có HTTP response | Connection refused/timeout | Lỗi transport, không được gán thành business 404 |
| HTTP 200 với JSON sai schema | Không phải HTTP error | Lỗi protocol/deserialization, không được xem là thành công |

Đừng gom mọi lỗi vào `RuntimeException("Inventory failed")`: điều đó khiến phía Checkout không thể phân biệt sản phẩm không tồn tại với hệ thống tạm ngừng. Ngược lại, cũng không nên tạo một exception class riêng cho từng status nếu nghiệp vụ không cần; mục tiêu là **bảo toàn ý nghĩa cần ra quyết định**.

## 20. Contract cho business 404 bằng YAML DSL

Một hợp đồng riêng cho SKU không tồn tại:

~~~yaml
description: Inventory báo SKU không tồn tại
name: inventory_sku_not_found

request:
  method: GET
  url: /api/inventory/SKU-404
  headers:
    Accept: application/json

response:
  status: 404
  headers:
    Content-Type: application/json
  body:
    code: SKU_NOT_FOUND
    message: SKU does not exist
    traceId: trace-demo-404
~~~

Với tình huống upstream tạm lỗi:

~~~yaml
description: Inventory tạm không sẵn sàng
name: inventory_unavailable

request:
  method: GET
  url: /api/inventory/SKU-503
  headers:
    Accept: application/json

response:
  status: 503
  headers:
    Content-Type: application/json
  body:
    code: INVENTORY_UNAVAILABLE
    message: Try again later
    traceId: trace-demo-503
~~~

Đây là **hai contract khác nhau** để producer/stub biết khi nào phát từng response. Những SKU đặc biệt chỉ dùng làm **fixture ổn định cho demo**; trong producer test thực, base test phải tạo dữ liệu/điều kiện tương ứng sao cho **implementation producer thật** trả ra 404 hoặc 503, không tự dựng controller giả trả response mẫu.

Trên producer thật, lỗi 503 có thể được kích hoạt bằng gateway/test adapter không sẵn sàng, còn error handler production phải tạo đúng status/body. Nếu test base tự trả `503 JSON` đúng contract, producer verification sẽ bị xanh giả.

## 21. Mô hình hóa error body và domain exception

Trước khi viết client, định nghĩa DTO error:

~~~java
package com.example.checkout;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record ApiError(
        String code,
        String message,
        String traceId) {
}
~~~

Khi HTTP error đến, client cần kiểm tra:

- Status là bao nhiêu?
- Body có phải JSON hợp lệ không?
- `code` có nằm trong nhóm được consumer hiểu không?
- `message` có thể được hiển thị hay chỉ nên log? Thông điệp từ upstream có thể chứa dữ liệu không an toàn.
- `traceId` có cần lưu để điều tra, và có được đưa ra ngoài theo policy bảo mật không?
- Lỗi là **response hợp lệ của producer** hay **unmatched 404** do stub?

Một vài domain exceptions minh họa:

~~~java
package com.example.checkout;

public class InventoryNotFoundException extends RuntimeException {
    public InventoryNotFoundException(String message) {
        super(message);
    }
}

public class InventoryUnavailableException extends RuntimeException {
    public InventoryUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class UpstreamProtocolException extends RuntimeException {
    public UpstreamProtocolException(String message) {
        super(message);
    }

    public UpstreamProtocolException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class InventoryTransportException extends RuntimeException {
    public InventoryTransportException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class InventoryHttpException extends RuntimeException {
    public InventoryHttpException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Những `public class` trên là **các file Java riêng** khi áp dụng, không đặt nhiều public top-level classes trong cùng một file. Có thể dùng package-private classes hoặc cấu trúc nested exceptions tùy convention dự án.

## 22. RestClient: GET, deserialize và phân loại HTTP errors

Một implementation tiêu biểu trong Checkout:

~~~java
package com.example.checkout;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

@Component
public class InventoryClient {

    private final RestClient client;
    private final ObjectMapper mapper;

    public InventoryClient(
            RestClient.Builder builder,
            ObjectMapper mapper,
            @Value("${inventory.base-url}") String baseUrl) {
        this.client = builder.baseUrl(baseUrl).build();
        this.mapper = mapper;
    }

    public StockResponse getStock(String sku) {
        try {
            StockResponse response = client.get()
                    .uri("/api/inventory/{sku}", sku)
                    .accept(MediaType.APPLICATION_JSON)
                    .retrieve()
                    .body(StockResponse.class);

            return StockResponseValidator.requireValid(response, sku);

        } catch (RestClientResponseException exception) {
            // HTTP 4xx/5xx đã nhận từ producer/stub.
            throw translateHttpError(exception);

        } catch (ResourceAccessException exception) {
            // Không có HTTP response hợp lệ (I/O, kết nối, timeout).
            throw new InventoryTransportException(
                    "Cannot reach Inventory Service", exception);

        } catch (RestClientException exception) {
            // Ví dụ: message converter không đọc được response.
            throw new UpstreamProtocolException(
                    "Cannot decode Inventory HTTP response", exception);
        }
    }

    private RuntimeException translateHttpError(
            RestClientResponseException exception) {

        ApiError error;
        try {
            error = mapper.readValue(
                    exception.getResponseBodyAsByteArray(),
                    ApiError.class);
        } catch (JsonProcessingException cause) {
            return new UpstreamProtocolException(
                    "Inventory error body is not valid ApiError JSON",
                    cause);
        }

        if (error == null || error.code() == null
                || error.code().isBlank()) {
            return new UpstreamProtocolException(
                    "Inventory error response has no code");
        }

        int status = exception.getStatusCode().value();

        if (status == 404 && "SKU_NOT_FOUND".equals(error.code())) {
            return new InventoryNotFoundException(
                    "Inventory SKU does not exist");
        }

        if (status == 503
                && "INVENTORY_UNAVAILABLE".equals(error.code())) {
            return new InventoryUnavailableException(
                    "Inventory temporarily unavailable",
                    exception);
        }

        // Không coi một mã 404 bất kỳ là SKU_NOT_FOUND.
        if (status == 404) {
            return new UpstreamProtocolException(
                    "Unexpected Inventory 404 code: " + error.code());
        }

        return new InventoryHttpException(
                "Unexpected Inventory status="
                        + status + ", code=" + error.code(),
                exception);
    }
}
~~~

Đây là ví dụ **strict error mapping**. Trong `RestClient.retrieve()`, hành vi mặc định với 4xx/5xx thường là ném `RestClientResponseException`; các catch ở trên minh họa xử lý theo kết quả đó. Nếu dự án đã cấu hình `defaultStatusHandler`/`onStatus`, phải kiểm tra và điều chỉnh để **không xử lý hai lần hoặc bỏ qua lỗi**.

Các nguyên tắc quan trọng:

1. **Lỗi transport** khác **HTTP 503 response**: timeout/connection refused không có đầy đủ status+error body.
2. **Lỗi JSON decode** khác **SKU không tồn tại**.
3. **404 có error code khác** không tự trở thành `InventoryNotFoundException`.
4. Chỉ ánh xạ `503 + INVENTORY_UNAVAILABLE` thành trạng thái unavailable đã cam kết.
5. Phần success response được **validate** để tránh `200` kèm null field.
6. Không ghi raw error body chứa thông tin nhạy cảm thẳng vào log/exception công khai.
7. Trong production cần có HTTP timeouts và retry/backoff policy được kiểm chứng riêng.

Nếu muốn ánh xạ lỗi theo `onStatus` của `RestClient` thay vì catch exception, có thể thực hiện, nhưng phải giữ nguyên các quy tắc status + code + body và test trên **client cấu hình thật**.

## 23. Consumer contract tests cho GET thành công và error mapping

Giả sử cả ba contract GET đã được đóng gói vào cùng stubs JAR của Inventory:

~~~java
package com.example.checkout;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.*;

@SpringBootTest(properties =
    "inventory.base-url=http://localhost:18081")
@AutoConfigureStubRunner(
    ids = "com.example:inventory-service:1.3.0-rc1:stubs:18081",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class InventoryConsumerContractTest {

    @Autowired
    InventoryClient inventory;

    @Test
    void decodesSuccessfulJson() {
        StockResponse stock = inventory.getStock("SKU-123");

        assertThat(stock.sku()).isEqualTo("SKU-123");
        assertThat(stock.available()).isTrue();
        assertThat(stock.quantity()).isEqualTo(12);
    }

    @Test
    void mapsBusiness404ToNotFound() {
        assertThatThrownBy(() -> inventory.getStock("SKU-404"))
                .isInstanceOf(InventoryNotFoundException.class);
    }

    @Test
    void maps503ToUnavailable() {
        assertThatThrownBy(() -> inventory.getStock("SKU-503"))
                .isInstanceOf(InventoryUnavailableException.class);
    }
}
~~~

Cần có bean `InventoryClient`, DTO, validator và exception đã minh họa trong test application context. Trên CI, stubs JAR `1.3.0-rc1` phải có thật ở nguồn LOCAL hoặc đổi sang REMOTE với repository đã cấu hình.

**Bằng chứng test đạt:** client thật gửi đúng GET/Accept, Stub Runner match mapping, Jackson decode response, validator xác nhận dữ liệu và lớp client chuyển error status/body thành đúng domain exception.

Nếu test chỉ gọi `RestClient` tới WireMock rồi assert status 404, chưa đủ chứng minh **logic error mapping của Checkout** đã hoạt động.

## 24. Unmatched WireMock 404 không phải business 404

Đây là một lỗi rất dễ bị bỏ qua. Giả sử consumer gửi:

~~~http
GET /api/inventory/WRONG-PATH HTTP/1.1
Accept: application/json
~~~

Không có mapping nào phù hợp, WireMock có thể trả HTTP 404 với body chẩn đoán mặc định, có thể **không phải JSON ApiError**.

Nếu client viết:

~~~java
// SAI: đánh đồng tất cả HTTP 404 với lỗi SKU_NOT_FOUND.
if (status == 404) {
    throw new InventoryNotFoundException("No stock");
}
~~~

thì lỗi **client gọi sai URL** có thể bị che thành “SKU không tồn tại”, làm consumer test xanh giả.

Client `InventoryClient` ở phần 22 không làm điều đó: nó yêu cầu JSON error có `code: SKU_NOT_FOUND`. Nếu 404 từ WireMock không match có body không parse được, client báo `UpstreamProtocolException`. Nếu response là JSON nhưng code khác, client cũng không coi là business 404.

Negative test minh họa:

~~~java
@Test
void unmatchedRequestIsNotMappedAsBusinessNotFound() {
    assertThatThrownBy(() -> inventory.getStock("SKU-NOT-STUBBED"))
            .isInstanceOf(UpstreamProtocolException.class);
}
~~~

Kết quả cụ thể phụ thuộc WireMock response và mappings đã nạp; nếu có catch-all mapping hợp lệ, test cần điều chỉnh. **Cần kiểm tra thực tế** rằng request âm tính không bị một mapping quá rộng bắt nhầm.

Một test quan trọng nữa là gửi request thiếu header hoặc URL khác qua client cấu hình thử nghiệm để chứng minh stub từ chối request đó, nếu header/path là ràng buộc thực sự của contract.

## 25. Mapping lỗi cần xét cả code, không chỉ status

Đối với business error, status và body code thường tạo thành một tổ hợp có ý nghĩa.

| Status | `code` | Kết quả hợp lý |
|---|---|---|
| `404` | `SKU_NOT_FOUND` | `InventoryNotFoundException` |
| `404` | `ORDER_NOT_FOUND` | Protocol/unexpected error đối với Inventory API demo |
| `404` | Body WireMock unmatched | Protocol/unexpected error |
| `503` | `INVENTORY_UNAVAILABLE` | `InventoryUnavailableException` |
| `503` | Body HTML từ gateway | Protocol/transport-layer diagnostic theo policy |
| `200` | Body thiếu `available` | Validation/protocol failure |
| Không nhận HTTP response | N/A | `InventoryTransportException` |

Một số API có lỗi không mang body JSON. Nếu đó là **cam kết hợp lệ**, client phải thiết kế mapping khác, không áp cứng ApiError cho mọi status. Ví dụ 204 No Content là kết quả thành công có chủ đích cho DELETE và không được ép parse thành DTO.

**Thỏa thuận error schema phải nằm trong contract**, không chỉ tồn tại trong code Java của consumer. Nếu producer đổi `code` hoặc `Content-Type`, consumer cần nhận được stub ứng viên mới để test phát hiện.

## 26. Request serialization và error handling cho POST

`ReservationClient.reserve` ở phần 8 sử dụng `retrieve().body(...)`. Nếu producer trả `400 INVALID_QUANTITY` hoặc `409 RESERVATION_CONFLICT`, cần ánh xạ lỗi theo business policy.

Ví dụ thông điệp khi quantity bằng 0:

~~~http
POST /api/reservations HTTP/1.1
Content-Type: application/json

{"sku":"SKU-123","quantity":0}
~~~

Response hợp đồng:

~~~http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json

{"code":"INVALID_QUANTITY","message":"quantity must be positive"}
~~~

Trong producer contract YAML có thể mô tả case riêng:

~~~yaml
description: Quantity phải lớn hơn 0 khi giữ hàng
name: reservation_invalid_quantity

request:
  method: POST
  url: /api/reservations
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    quantity: 0

response:
  status: 422
  headers:
    Content-Type: application/json
  body:
    code: INVALID_QUANTITY
    message: quantity must be positive
~~~

Với một client production, policy có thể là:

- `400/422` validation: trả domain validation error, **không retry**.
- `409` conflict: quyết định retry có idempotency hay yêu cầu người dùng xử lý.
- `503` unavailable: retry/backoff có ngân sách hoặc circuit breaker.
- `500` unexpected: log/metrics an toàn, không biến thành “hàng không tồn tại”.

Đoạn `ReservationClient` ở phần 8 chỉ có **happy path**; để sản xuất thực tế cần bổ sung error translation riêng và consumer tests cho các status có ý nghĩa.

## 27. Content-Type và encoding cũng thuộc hợp đồng

Hai HTTP response có cùng body text không nhất thiết có cùng semantics:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"available":true}
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain

{"available":true}
~~~

Tùy message converter và cấu hình, consumer có thể giải mã sai hoặc từ chối loại content. Trong contract và consumer test:

- Kiểm tra `Content-Type` của request và response đúng loại đã cam kết.
- `Accept` là yêu cầu từ client; producer có thể không hỗ trợ mọi dạng `Accept`.
- Header HTTP thường không phân biệt chữ hoa/thường ở tên; JSON field thì có.
- `application/json;charset=UTF-8` có thể tương thích về media type với `application/json`; tránh equality quá chặt nếu charset không phải yêu cầu.
- Với non-ASCII text, bảo đảm encoding đúng và không biến dữ liệu thành chuỗi lỗi khi serialize/deserialize.
- Với gzip hoặc binary/file body, cần thêm test về bytes/MIME type nếu client phụ thuộc.

Không test chỉ bằng DTO nội bộ mà bỏ qua HTTP headers. Một DTO map đúng trong unit test không chứng minh RestClient đã gửi Content-Type đúng hoặc nhận được content converter dự kiến.

## 28. Kiểm thử reactive WebClient: nguyên tắc tương đương

Nếu Checkout dùng `WebClient` thay `RestClient`, ba biên dữ liệu vẫn giống nhau, chỉ khác API bất đồng bộ:

~~~java
Mono<StockResponse> getStock(String sku) {
    return webClient.get()
            .uri("/api/inventory/{sku}", sku)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .onStatus(
                status -> status.value() == 404,
                response -> response.bodyToMono(ApiError.class)
                    .switchIfEmpty(Mono.error(
                        new UpstreamProtocolException(
                            "404 without ApiError body")))
                    .map(error -> {
                        if ("SKU_NOT_FOUND".equals(error.code())) {
                            return new InventoryNotFoundException(
                                "Inventory SKU does not exist");
                        }
                        return new UpstreamProtocolException(
                            "Unexpected Inventory 404 code");
                    })
            )
            .bodyToMono(StockResponse.class)
            .map(response ->
                StockResponseValidator.requireValid(response, sku));
}
~~~

Đây là **đoạn phương thức minh họa**, cần đặt trong class đã có `webClient`, imports Reactor và DTO/exceptions tương ứng. Phần handler mới xử lý 404; production client còn phải quy định 503, 5xx, timeout và lỗi decode.

Khi kiểm tra, phải **subscribe** vào Mono (ví dụ `StepVerifier`) để HTTP request thực sự chạy:

~~~java
StepVerifier.create(inventoryClient.getStock("SKU-123"))
    .assertNext(stock -> assertThat(stock.available()).isTrue())
    .verifyComplete();
~~~

Stub Runner vẫn kiểm tra HTTP request/response contract; `StepVerifier` kiểm tra kết quả/tín hiệu của client reactive. **Không thay HTTP client bằng `Mono.just(StockResponse...)`** rồi gọi đó là consumer contract test.

Lưu ý: `Mono.empty()` và error signal khác nhau. Một error body rỗng trong `onStatus` không được âm thầm biến thành success; phải định nghĩa fallback hoặc lỗi contract rõ ràng.

## 29. Consumer message contracts cũng có serialization và error handling

Spring Cloud Contract còn hỗ trợ hợp đồng **message**, không chỉ HTTP. Ví dụ producer phát:

~~~json
{
  "eventId": "evt-101",
  "eventType": "InventoryChanged",
  "sku": "SKU-123",
  "available": true
}
~~~

Consumer handler cần:

1. Giải mã message từ bytes/JSON sang DTO đúng schema.
2. Đọc và validate headers như `contentType`, `correlationId`, schema version nếu hợp đồng yêu cầu.
3. Kiểm tra event type mới/không biết và policy forward compatibility.
4. Phân biệt **invalid payload**, **business reject**, **transient handler failure**.
5. Quyết định acknowledgement/retry/DLQ theo broker và idempotency policy.
6. Với stub message, kiểm tra consumer handler thực sự nhận và xử lý event khi Stub Runner trigger label.

**Khác biệt quan trọng:** trong messaging, lỗi deserialize có thể xảy ra trước khi listener method được gọi; không có HTTP 404/503 để map. Cần integration tests của message converter/consumer binding, retry và DLQ; Stub Runner không tự chứng minh broker topology, partition key hay at-least-once semantics.

## 30. Ma trận test nên bao phủ

| Loại test | Input | Điều cần assert |
|---|---|---|
| POST serialization happy path | `sku=SKU-123`, `quantity=2` | WireMock match request JSON và trả 201 |
| POST sai tên field | `productId` thay `sku` | Không match/producer từ chối theo contract |
| POST sai kiểu | `quantity="2"` | Bị phát hiện nếu strict type được yêu cầu |
| POST thiếu header | Thiếu `Content-Type` | Không match nếu header thuộc contract |
| GET success | `200` với body hợp lệ | DTO đúng kiểu/giá trị, validator đạt |
| GET thiếu field | Không có `available` | Client báo protocol error |
| GET explicit null | `available:null` | Client không coi là false |
| GET sai kiểu | `quantity:"12"` | Chống coercion nếu strict JSON number |
| GET extra field | Thêm `warehouse` | Đạt hoặc fail theo forward-compatibility policy |
| GET unknown enum | `status:"EXPIRED"` | Fallback/error theo policy |
| HTTP 404 hợp đồng | `SKU_NOT_FOUND` | Domain not found |
| HTTP 404 unmatched | WireMock không có mapping | Không coi là business not found |
| HTTP 503 hợp đồng | `INVENTORY_UNAVAILABLE` | Domain unavailable/retry policy |
| HTTP 503 body sai | HTML hoặc code khác | Protocol/unexpected error |
| Connect timeout/refused | Không có HTTP response | Transport error |
| Body lỗi không parse được | JSON malformed | Protocol error, không che thành 404 |
| Version mới | Producer thêm/đổi schema | Consumer test với stub ứng viên phát hiện kết quả |

Ma trận này không nhất thiết biến thành tất cả **producer contracts chính thức**. Những request/response mà producer thực sự cam kết cần xuất hiện trong contract; các payload **cố ý sai** có thể được kiểm tra bằng fixture WireMock riêng hoặc deserializer unit tests, nhưng phải giữ rõ test nào kiểm chứng **tương thích** và test nào kiểm chứng **khả năng chịu lỗi**.

## 31. Negative testing: chứng minh bài test có khả năng phát hiện lỗi

Một bài test luôn xanh với body chuẩn chưa chứng minh nó phát hiện serialization sai.

Thử các **mutation có chủ đích trong nhánh thử**:

### Mutation A — Đổi tên trường request

Trong `ReservationRequest`, tạm thay `sku` thành `productId` nhưng giữ contract cũ. Nếu WireMock matcher kiểm tra body, stub phải **không chấp nhận** request hoặc consumer test đỏ.

Nếu test vẫn xanh, mở mapping để xem có thiếu body matcher, có catch-all mapping hoặc test đã mock HTTP client không.

### Mutation B — Đổi tên field response

Producer ứng viên đổi `available` thành `inStock`. Nếu stub ứng viên mới chứa field đó, consumer DTO cũ phải phát hiện missing `available` qua validator. Nếu client mặc định `false` và vẫn báo hết hàng bình thường, đang có nguy cơ che breaking change.

### Mutation C — Đổi error code

Thay `SKU_NOT_FOUND` thành `ITEM_UNKNOWN` nhưng giữ HTTP 404. Với strict mapping, consumer không được âm thầm trả `InventoryNotFoundException` như cũ. Đây là ví dụ vì sao **status-only mapping** không đủ.

### Mutation D — Response số thành chuỗi

Đổi `quantity:12` thành `quantity:"12"` trong một test fixture. Nếu policy yêu cầu strict JSON number, test phải phát hiện dù Jackson có thể thực hiện coercion. Kiểm tra JSON raw type hoặc cấu hình ObjectMapper.

### Mutation E — Client gọi nhầm URL

Đổi `/api/inventory/{sku}` thành `/api/stock/{sku}`. Consumer test qua Stub Runner phải fail do request không match, không được “dịch” thành business 404.

**Luôn khôi phục mutation** sau khi xác nhận. Những thay đổi này là bài kiểm tra năng lực phát hiện lỗi của suite, không phải thay đổi production cần merge.

## 32. Khi producer đổi contract: ai phải chạy test nào?

~~~mermaid
flowchart TD
    A["PR thay API, DTO hoặc error schema ở producer"] --> B["Generated producer contract tests"]
    B --> C{"Producer vẫn đáp ứng contract?"}
    C -- "Không" --> X["BLOCK hoặc đánh giá lại contract"]
    C -- "Có" --> D["Sinh/publish candidate stubs JAR"]
    D --> E["Consumer tests dùng HTTP client thật"]
    E --> F{"Serialization và deserialization đạt?"}
    F -- "Không" --> Y["Sửa consumer hoặc lập migration"]
    F -- "Có" --> G{"Error mapping và negative tests đạt?"}
    G -- "Không" --> Y
    G -- "Có" --> H["Tiếp tục release gates"]
~~~

Hai lớp kiểm chứng bổ sung nhau:

- Producer test xác nhận code producer **thực sự tuân thủ** contract được công bố.
- Consumer test xác nhận **client consumer hiện hành** chấp nhận request/response/error schema của artifact ứng viên.

Nếu producer đổi code và contract cùng lúc, generated producer test có thể vẫn xanh dù consumer cũ bị phá. Vì vậy, **consumer phải thử với stub được sinh từ chính commit/version ứng viên**, không phải stub stable cũ.

Nếu có nhiều consumer, cần chạy ít nhất các consumer được khai báo là cần hỗ trợ hoặc ma trận tương thích phù hợp. Đừng chỉ kiểm tra consumer mới nhất rồi bỏ qua những bản đang vận hành.

## 33. CI/CD: những điều phải ghi lại

Trong producer Maven đã cấu hình Spring Cloud Contract:

~~~bash
./mvnw clean verify
~~~

Với Gradle có plugin phù hợp:

~~~bash
./gradlew clean test
~~~

Trong môi trường consumer, Stub Runner có thể lấy stub từ `LOCAL` hoặc `REMOTE` repository; tọa độ ví dụ:

~~~text
com.example:inventory-service:1.3.0-rc1:stubs
~~~

CI cần kiểm tra:

1. Producer **có contract** được phát hiện, generated producer tests thật sự được chạy và đạt.
2. Stub JAR chứa mapping request/response cần thiết, không rỗng và không bị thiếu body file.
3. Tọa độ group/artifact/version/classifier khớp **commit ứng viên**; không dùng version `+`/latest không xác định.
4. Consumer test trỏ đến **đúng Stub Runner port/repository**; không gọi producer production ngoài ý muốn.
5. Test dùng **RestClient/WebClient/Feign thật** của consumer, không mock toàn bộ HTTP client.
6. Test happy path kiểm tra cả serialization request và deserialization response.
7. Error tests kiểm tra tổ hợp **status + code + body** và các exception/kết quả nghiệp vụ.
8. Unmatched WireMock 404 được phân biệt với business 404.
9. Có negative tests cho missing/null/wrong type hoặc schema evolution quan trọng.
10. Log thất bại nêu rõ contract, artifact version, request path, mã lỗi và điểm fail, không in secret/raw token.
11. Nếu producer đổi error schema hoặc enum, các consumer cũ trong phạm vi hỗ trợ được kiểm chứng với stub ứng viên.
12. Các test timeout/retry/resilience ở tầng riêng được chạy khi yêu cầu, không suy ra từ stub luôn phản hồi ngay.

**Không coi build xanh là đủ** nếu generated tests bằng 0, stub trống hoặc consumer vẫn dùng một artifact cũ.

## 34. Troubleshooting: test đỏ do đâu?

| Triệu chứng | Nguyên nhân thường gặp | Cách điều tra |
|---|---|---|
| Stub trả 404 dù SKU-123 tồn tại trong contract | URL/header/body request không match | Xem WireMock mappings và request journal |
| Client báo `InventoryNotFoundException` với URL sai | Mapping dựa vào HTTP 404 quá rộng | Kiểm tra error body `code` trước khi phân loại |
| POST luôn trả 201 kể cả body sai | Stub request matcher quá lỏng | Kiểm tra `bodyPatterns` và negative mutation |
| Jackson báo unrecognized property | DTO/config đang strict, producer thêm field | Xác định policy forward compatibility |
| `available` thiếu mà consumer vẫn chạy | Primitive/default giá trị che missing field | Dùng wrapper + validation |
| `quantity:"12"` vẫn được parse | Jackson coercion | Kiểm tra raw JSON hoặc strict coercion |
| Client lỗi khi nhận enum mới | Giá trị không thuộc enum Java | Điều chỉnh contract/migration/unknown policy |
| 503 bị coi là SKU không tồn tại | Bắt chung `RestClientException` và map sai | Phân biệt HTTP status, transport, protocol |
| JSON body lỗi không parse được | Producer trả HTML/body sai hoặc converter lệch | Kiểm tra status, Content-Type và bytes an toàn |
| Test chỉ xanh khi chạy local | Stub version khác, ObjectMapper config khác | So classpath, properties, exact artifact |
| Không có generated producer tests | Plugin/contract discovery bị skip | Kiểm tra generation, task và test report |
| Consumer test gọi service thật | Base URL test chưa inject đúng | Ghi target host/port, kiểm tra client bean |
| Error response từ stub khác producer | Multi-stub port/URL bị trỏ nhầm | So producer ID, port, mappings |
| Test có schema đúng nhưng nghiệp vụ sai | Chỉ assert DTO decode, không assert invariant | Thêm validator và business tests |
| Test fail ngẫu nhiên theo thời gian | Dữ liệu/clock/timeouts không ổn định | Dùng fixture/clock cố định và giới hạn chờ rõ |

Đường chẩn đoán hiệu quả:

~~~text
Contract source
  -> Generated WireMock mapping
  -> Exact stubs JAR version
  -> Stub Runner URL/port
  -> Raw HTTP request của consumer client
  -> HTTP response status/headers/body
  -> Jackson DTO hoặc parse exception
  -> Domain error mapping
  -> Business assertions
~~~

Đọc đúng tầng sẽ tránh “sửa hợp đồng” trong khi nguyên nhân thật là client serialization sai hoặc stub cũ.

## 35. Thực hành A — Kiểm chứng serialization của POST

1. Tạo contract POST `/api/reservations` theo phần 5 hoặc 6.
2. Cho Inventory producer sinh generated tests/mappings và đóng gói stubs JAR.
3. Dùng `ReservationClient.reserve("SKU-123", 2)` từ Checkout gọi Stub Runner.
4. Assert HTTP response được deserialize thành `ReservationResponse("R-1001","RESERVED")`.
5. Trong nhánh thử, đổi tên field Java `sku` thành `productId`.
6. Chạy lại consumer test, xác nhận không còn match nếu matcher đúng.
7. Mở generated mapping giải thích sự khác nhau giữa request hợp lệ và request lỗi.
8. Khôi phục code, chạy lại test.

**Bằng chứng:** Groovy/YAML contract, mapping JSON, test source/report và screenshot/log request không match (nếu hệ thống hỗ trợ).

## 36. Thực hành B — Kiểm tra deserialization và schema evolution

1. Viết contract GET `SKU-123` trả `sku`, `available` và `quantity`.
2. Dùng DTO wrapper `Boolean`/`Integer` và validator như phần 11/12.
3. Chạy consumer contract test qua Stub Runner, xác nhận response hợp lệ được parse.
4. Tạo negative fixture không có `available` và một fixture `available:null`.
5. Tạo fixture `quantity:"12"` và kiểm tra strict wire type policy đã chọn.
6. Thử thêm field `warehouse` để kiểm tra forward compatibility.
7. Thử đổi `available` thành `inStock` từ producer candidate, quan sát consumer cũ.

**Bằng chứng:** bảng pass/fail cho normal, missing, null, wrong type, extra field và rename field.

## 37. Thực hành C — Phân loại business error và transport error

1. Tạo hai contract GET: `SKU-404` trả 404 + `SKU_NOT_FOUND`; `SKU-503` trả 503 + `INVENTORY_UNAVAILABLE`.
2. Dùng client `InventoryClient` và domain exceptions ở phần 21/22.
3. Chạy consumer tests, xác nhận hai exception loại khác nhau.
4. Gọi một URL **không có mapping** để kiểm tra WireMock unmatched 404 không bị phân loại là business not found.
5. Sử dụng một test server/fixture riêng trả 503 + HTML để kiểm tra protocol error.
6. Mô phỏng connection refused hoặc read timeout trong một resilience test, xác nhận đó là transport error.
7. Kiểm tra retry chỉ áp dụng cho lỗi phù hợp và không gây request lặp ngoài chính sách.

**Bằng chứng:** error mapping matrix, client code và logs/test reports cho HTTP 404, 503, unmatched, malformed body và transport.

## 38. Checklist khi review consumer contract tests

- [ ] Dùng **HTTP client/handler production** của consumer, không mock toàn bộ phía client.
- [ ] Stub artifact đến từ contract producer đã được generated tests kiểm chứng.
- [ ] Request serialization kiểm tra method/path/query, Content-Type/Accept và JSON body.
- [ ] Matcher đủ chặt để nhận biết field/kiểu quan trọng bị thay đổi.
- [ ] Consumer DTO khớp wire names; không chỉ dựa vào default naming.
- [ ] Trường bắt buộc được validate sau deserialization; null/missing không bị default che đi.
- [ ] Kiểu number/boolean/enum/time/money được xử lý đúng semantics.
- [ ] Trường lạ có policy forward compatibility rõ, không tự chọn strict/lenient tùy tiện.
- [ ] Response 2xx thiếu body/sai schema được coi là protocol error nếu contract yêu cầu dữ liệu.
- [ ] Mapping lỗi dùng **status + code + body**, không chỉ status.
- [ ] Business 404 và WireMock unmatched 404 không bị đánh đồng.
- [ ] Transport timeout/connection refused khác HTTP 503 có body hợp lệ.
- [ ] Có negative tests cho tên field, wrong type, null/absent, malformed JSON, unknown enum khi cần.
- [ ] Consumer test bao phủ happy path lẫn error cases có ý nghĩa nghiệp vụ.
- [ ] CI dùng **exact candidate stubs version** và lưu artifact/commit.
- [ ] Generated producer tests chạy thật, stub JAR có mappings, consumer test không trỏ production.
- [ ] Không đưa token, PII hoặc dữ liệu thực vào fixtures/stub artifact.
- [ ] Những breaking changes có migration/versioning và được kiểm chứng với consumer cũ.

## 39. Câu hỏi tự kiểm tra

**1. Vì sao unit test `objectMapper.writeValueAsString(request)` chưa đủ chứng minh consumer serialization đúng?**

Vì nó không kiểm tra HTTP client thực có gửi đúng method, path, headers, body converter và cấu hình ObjectMapper đang dùng hay không. Test qua Stub Runner phải gọi **client production**.

**2. Vì sao DTO dùng `boolean available` có thể nguy hiểm?**

Vì field bị thiếu/null có thể bị chuyển thành giá trị primitive mặc định theo cấu hình, khiến consumer hiểu nhầm “không có dữ liệu” thành `false`. Dùng `Boolean` và validate giúp phát hiện.

**3. Vì sao status 404 không đủ để ném `InventoryNotFoundException`?**

Vì 404 còn có thể là unmatched WireMock request hoặc lỗi upstream khác. Cần kiểm tra error schema và `code` được cam kết, ví dụ `SKU_NOT_FOUND`.

**4. Một producer thêm `warehouse` vào JSON có luôn là breaking change không?**

Không nhất thiết. Với consumer bỏ qua field lạ, nó thường tương thích. Nhưng nếu client đang strict hoặc field mới đổi semantics/bảo mật, cần đánh giá và test.

**5. Jackson parse `quantity:"12"` thành Integer có chứng minh wire contract đúng không?**

Không. Có thể là kết quả coercion; nếu JSON number là yêu cầu, kiểm tra raw type hoặc cấu hình strict và test âm tính.

**6. HTTP 503 và connection refused có phải cùng một lỗi?**

Không. HTTP 503 là response có status (và có thể error body) do upstream gửi; connection refused không có HTTP response hợp lệ. Client cần chính sách retry/diagnostic phù hợp.

**7. Vì sao phải dùng stub ứng viên thay vì artifact stable trong CI?**

Vì producer có thể đã đổi contract (field name, enum, error code). Chỉ stub ứng viên của commit mới thể hiện thay đổi mà consumer cũ cần thử để phát hiện breaking change.

**8. Tại sao consumer test nên kiểm tra domain exception thay vì chỉ đọc raw response?**

Vì yêu cầu thực tế là **code consumer xử lý lỗi đúng**, không chỉ mạng trả status. Exception/kết quả nghiệp vụ là giao diện mà phần còn lại của Checkout sử dụng.

## 40. Tài liệu tham khảo

- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/): Contract Verifier, stubs và consumer testing.
- [Spring Cloud Contract – Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): Groovy/YAML, request/response và matcher.
- [Spring Cloud Contract – Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner.html): tải stub ứng viên và khởi động HTTP mapping.
- [Spring Framework – REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): `RestClient`, `WebClient`, response handling.
- [Spring Boot – Jackson Customization](https://docs.spring.io/spring-boot/reference/features/json.html): cấu hình JSON mapper trong ứng dụng Boot.
- [Jackson Databind Documentation](https://github.com/FasterXML/jackson-databind): JSON data binding, records, coercion và unknown properties.
- [WireMock – Request Matching](https://wiremock.org/docs/request-matching/): HTTP method, headers, query, JSON body matcher và request journal.
- [WireMock – Stubbing](https://wiremock.org/docs/stubbing/): response status/header/body và unmatched requests.
- [Project Reactor – Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier` cho consumer reactive.

**Lưu ý phiên bản:** `RestClient`, annotation Jackson, Spring Cloud Contract DSL, Stub Runner, WireMock mappings và các mặc định coercion/error handling phụ thuộc phiên bản. Hãy dùng bộ Spring Boot–Spring Cloud Release Train–Spring Cloud Contract tương thích, đối chiếu tài liệu tương ứng và kiểm tra generated mappings/test reports thực tế. Những đoạn code là ví dụ học tập; **chưa được chạy build hoặc Content QA chuyên sâu trong bước biên soạn này**.

---

**Điểm cần nhớ:** Consumer contract testing không dừng ở việc nhận HTTP 200. Bài test phải đi qua **client production thật** để chứng minh **Java DTO → HTTP request đúng (serialization)**, **HTTP response → DTO hợp lệ (deserialization)** và **HTTP/transport/protocol error → xử lý nghiệp vụ đúng (error mapping)**. Kết hợp các kiểm tra này với **producer generated tests** và **stub ứng viên đúng commit** trong CI mới có cơ sở phát hiện các thay đổi API không tương thích.

# Producer test đạt nhưng consumer vẫn không tương thích

Một pipeline của **Order Service** có thể báo tất cả generated producer contract tests đều PASS, nhưng ngay sau khi phát hành, **Billing Service** vẫn lỗi khi gọi API. Billing có thể không deserialize được response, gửi sai header, không xử lý status 404/409, đọc nhầm đơn vị tiền hoặc đang tải một JAR `stubs` khác với hợp đồng mà producer vừa xác minh. Kết quả producer test xanh là một bằng chứng quan trọng, nhưng **không tự chứng minh mọi consumer đang được hỗ trợ đều tương thích với bản producer sắp triển khai**.

Trong **Spring Cloud Contract**, producer verification tests được sinh từ các contract Groovy/YAML và chạy trên implementation producer. Chúng trả lời câu hỏi: **producer có đáp ứng các tình huống được mô tả trong hợp đồng hay không?** Consumer test với **Stub Runner** trả lời một câu hỏi khác: **mã client/listener của consumer có sử dụng được hành vi stub đã chọn hay không?** Muốn hai kết quả có ý nghĩa cùng nhau, contract phải phản ánh nhu cầu thực tế, consumer test phải chạy trên client thật, artifact phải đúng version, và release/deployment phải giữ liên kết với chính bộ hợp đồng đã được kiểm.

Bài thuộc chương **Chẩn đoán sự cố** của mô-đun **SPRING_CLOUD_CONTRACT**. Mô-đun học kiểm thử hợp đồng giữa producer và consumer qua HTTP hoặc thông điệp, định nghĩa hành vi bằng Groovy/YAML DSL, sinh producer tests, phát hành stub, dùng Stub Runner và tích hợp CI để phát hiện thay đổi API không tương thích. Bài này tập trung vào trường hợp **producer test đạt nhưng consumer vẫn không tương thích**, từ xác định phạm vi bằng chứng đến khoanh vùng request, response, artifact, DTO, semantics, transport và quy trình phát hành.

## 1. Producer test xanh thực sự chứng minh điều gì?

Giả sử Order Service có contract:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldReturnPaidOrder'

    request {
        method 'GET'
        url '/api/orders/42'
        headers {
            header('Accept', 'application/json')
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            id: 42,
            status: 'PAID',
            amountMinor: 125000,
            currency: 'VND'
        )
    }
}
~~~

Khi generated producer test PASS, ta có bằng chứng rằng **trong test mode/base test/fixture của lần build đó**, request được mô tả đã kích hoạt producer và response đáp ứng các assertions được sinh từ contract.

Kết quả này **không tự chứng minh**:

- Tất cả endpoint, query parameter, header, error response và trạng thái nghiệp vụ của API đều được mô tả.
- Mọi phiên bản Billing đang chạy đều có DTO/HTTP client tương thích.
- Consumer đang tải đúng artifact `stubs` của producer release vừa kiểm.
- Docker image được deploy chính là image có source đã qua producer verification.
- Gateway, TLS, authentication, compression, proxy và network production hoạt động như test context.
- Mọi event đã lưu trên broker, retry, DLQ hoặc replay đều tương thích.
- Matcher không quá rộng đến mức chấp nhận một response sai nhưng vẫn đúng kiểu.

**Producer verification chứng minh implementation phù hợp với những gì contract yêu cầu; chất lượng của bằng chứng phụ thuộc vào độ bao phủ và độ chính xác của contract.**

## 2. Bốn loại bằng chứng phải nối với nhau

~~~mermaid
flowchart TD
    A["Consumer needs + contract Groovy/YAML"] --> B["Producer generated verification"]
    A --> C["Stub artifact được đóng gói"]
    B --> D["Producer release được xác minh"]
    C --> E["Consumer Stub Runner tests"]
    E --> F["Client/listener thật của consumer"]
    D --> G["Producer image được deploy"]
    G --> H["Runtime API/message behavior"]
    F --> I["Compatibility evidence"]
    H --> I
~~~

| Bằng chứng | Câu hỏi được trả lời | Giới hạn |
| --- | --- | --- |
| **Generated producer test** | Implementation producer có đáp ứng contract scenario? | Chỉ các scenario/assertions đã được sinh và thực thi. |
| **Stub Runner consumer test** | Consumer code có hoạt động với stub artifact được chọn? | Không chứng minh producer instance production giống artifact stub nếu thiếu liên kết release/deploy. |
| **Artifact provenance** | JAR stubs đến từ producer commit/build nào? | Không chứng minh image đã được deploy hoặc runtime không bị cấu hình khác. |
| **Runtime/deployment evidence** | Producer image/version nào thực sự nhận traffic và trả gì? | Không thay thế kiểm thử đầy đủ mọi consumer scenario. |

**Không lấy một kết quả PASS để suy ra ba kết quả còn lại.** Khi xảy ra sự cố, phải xác định bằng chứng nào đang thiếu hoặc không khớp.

## 3. Ví dụ: Order Service và Billing Service

Producer công bố:

~~~http
GET /api/orders/42
Accept: application/json
~~~

Response theo contract:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": 42,
  "status": "PAID",
  "amountMinor": 125000,
  "currency": "VND"
}
~~~

Billing client đang dùng DTO:

~~~java
package com.acme.billing;

import com.fasterxml.jackson.annotation.JsonProperty;

public record OrderDto(
    long id,
    String status,
    long amountMinor,
    String currency
) {}
~~~

Trong tình huống này, nếu client gọi đúng endpoint và response thực có đúng schema, DTO có thể deserialize thành công. Nhưng các thay đổi sau có thể khiến Billing không tương thích:

| Producer response thực | Consumer có thể gặp vấn đề |
| --- | --- |
| `amountMinor` đổi từ number thành string | Jackson/DTO có thể không chuyển được hoặc semantics thay đổi. |
| `currency` bị bỏ | Consumer nhận null/default hoặc lỗi validation. |
| `status` đổi `PAID` thành `SETTLED` | Enum mapping hoặc business branch không nhận giá trị mới. |
| `amountMinor` đổi nghĩa từ minor units sang major units | JSON parse thành công nhưng số tiền sai nghiêm trọng. |
| `Content-Type` thành loại media khác | Message converter không chọn JSON converter. |
| Response thành 202 thay vì 200 | Client có thể coi là chưa có dữ liệu hoặc đi nhánh xử lý khác. |
| Path chuyển sang `/api/v2/orders/42` | Client cũ vẫn gọi v1 hoặc nhận 404. |
| 404 body đổi schema | Error decoder không lấy được error code. |

**Một số lỗi không thể phát hiện bằng happy path duy nhất**. Contract phải có các scenario đại diện cho behavior consumer phụ thuộc, còn consumer test phải kiểm client thật với dữ liệu có ý nghĩa.

## 4. Nguyên nhân 1: contract không đại diện nhu cầu consumer

Một producer có thể tự viết contract chỉ cho happy path:

~~~text
GET /api/orders/42 -> 200
~~~

Trong khi Billing cần thêm:

- `Accept` và `Authorization` header đúng.
- Query `include=payment` hoặc `currency` nếu API quy định.
- 404 khi order không tồn tại.
- 403 khi token không có scope.
- 409 khi order đang ở trạng thái không thể thanh toán.
- Error body có `code` và `message` để map sang lỗi nghiệp vụ.
- Semantics của tiền, timezone, idempotency và retry.

Producer test xanh cho happy path **không chứng minh các scenario còn lại**.

### 4.1. Viết contract theo consumer-visible behavior

Contract nên phản ánh **những gì bên gọi có thể quan sát và phụ thuộc**, không chỉ cấu trúc controller nội bộ. Ví dụ thêm scenario lỗi:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldReturnOrderNotFound'

    request {
        method 'GET'
        url '/api/orders/999'
        headers {
            header('Accept', 'application/json')
        }
    }

    response {
        status 404
        headers {
            contentType(applicationJson())
        }
        body(
            code: 'ORDER_NOT_FOUND',
            message: 'Order does not exist'
        )
    }
}
~~~

Đây là một **scenario bổ sung** cho API lỗi. Nó giúp producer verification kiểm response 404 đã cam kết và cho phép consumer test kiểm error mapping. Nội dung message có thể cần matcher linh hoạt nếu không phải cam kết ổn định; error code thường quan trọng hơn text hiển thị.

### 4.2. Consumer phải tham gia review contract

Một quy trình consumer-driven hoặc phối hợp producer/consumer nên:

1. Consumer nêu **request/response/message behavior** mà client thực sự cần.
2. Producer xác nhận có thể cung cấp semantics đó và mức tương thích.
3. Các bên review schema, required fields, types, enum, errors, headers, auth và retry.
4. Contract được commit vào nguồn có ownership rõ ràng.
5. Producer verification kiểm implementation.
6. Consumer Stub Runner tests kiểm client/listener.

**Contract chỉ do producer viết vẫn có thể hợp lệ**, nhưng nếu producer không biết consumer đang phụ thuộc điều gì, contract dễ thiếu những scenario quan trọng.

## 5. Nguyên nhân 2: matcher quá rộng khiến producer test đạt giả

Một contract có thể dùng:

~~~groovy
bodyMatchers {
    jsonPath('$.status', byType())
    jsonPath('$.amountMinor', byType())
}
~~~

Các matcher theo kiểu có ích khi giá trị thực sự biến thiên nhưng **kiểu JSON phải đúng**. Tuy nhiên, nếu fixture cho Billing cần `status=PAID` và `amountMinor=125000`, chỉ kiểm kiểu có thể bỏ lọt:

~~~json
{
  "status": "CANCELLED",
  "amountMinor": -1
}
~~~

Producer test có thể PASS ở các assertions theo kiểu dù dữ liệu nghiệp vụ sai.

| Trường | Kiểm tra cần cân nhắc |
| --- | --- |
| `id` gắn với request ID | Equality hoặc invariant request–response. |
| `status` trong scenario PAID | Equality/enum semantics, không chỉ string type. |
| `amountMinor` | Numeric type + giá trị/range/business invariant. |
| `currency` | Required field và enum/code được công bố. |
| `createdAt` động | Pattern/parse validity và timezone policy. |
| `traceId` động | Presence/format, không equality với ID mẫu. |

**Đừng nới matcher chỉ để producer test xanh.** Cần thử mutation: một thay đổi hợp lệ phải PASS; một thay đổi phá semantics phải FAIL.

## 6. Nguyên nhân 3: consumer DTO hoặc deserializer khác contract

Ngay cả khi response khớp contract, consumer có thể deserialize sai vì:

- Field Java dùng tên khác nhưng thiếu `@JsonProperty`/naming strategy tương ứng.
- DTO khai báo `int` trong khi producer có thể trả giá trị vượt giới hạn.
- Enum consumer không có giá trị mới mà producer bắt đầu phát.
- Consumer dùng `LocalDateTime` nhưng API trả timestamp có offset hoặc timezone.
- Consumer yêu cầu field non-null nhưng contract cho phép missing/null.
- Jackson bật strict unknown properties trong khi producer thêm field.
- Consumer converter không hỗ trợ media type thực tế.

### 6.1. Tên field và DTO

Nếu producer trả:

~~~json
{
  "order_id": "ORD-42",
  "amount_minor": 125000
}
~~~

nhưng consumer DTO dùng:

~~~java
public record OrderDto(
    String orderId,
    long amountMinor
) {}
~~~

thì phải xác định quy ước mapping thực tế. Có thể dùng:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

public record OrderDto(
    @JsonProperty("order_id") String orderId,
    @JsonProperty("amount_minor") long amountMinor
) {}
~~~

**Không đổi contract field chỉ để khớp DTO cũ** nếu producer đã công bố schema khác và consumer cần cập nhật. Trước tiên xác nhận JSON response thực có đúng contract; sau đó sửa mapping DTO/client hoặc điều chỉnh contract qua một quyết định API có review.

### 6.2. Unknown fields và field bị thiếu

`@JsonIgnoreProperties(ignoreUnknown = true)` có thể giúp DTO cũ bỏ qua **field mới không dùng**:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record OrderDto(
    long id,
    String status,
    long amountMinor,
    String currency
) {}
~~~

Nhưng annotation này **không tạo ra field bị thiếu**, không giải quyết đổi tên field và không bảo đảm semantics. Nếu `currency` bắt buộc nhưng producer bỏ field, consumer có thể nhận null hoặc giá trị mặc định; phải kiểm validation và error handling rõ ràng.

Không nên bật ignore-unknown trên toàn hệ thống mà không xem policy schema. Có những API cố ý dùng schema đóng để phát hiện producer gửi field ngoài hợp đồng.

## 7. Nguyên nhân 4: kiểu dữ liệu và semantics khác nhau

JSON có thể deserialize thành công nhưng consumer vẫn xử lý sai.

| Contract mong đợi | Producer thực trả | Vấn đề |
| --- | --- | --- |
| Number `amountMinor` | String `"125000"` | Kiểu wire thay đổi. |
| Minor units | Major units | Giá trị parse được nhưng sai đơn vị. |
| `currency=VND` | `currency=USD` | Sai semantics nghiệp vụ. |
| Timestamp UTC | Timestamp local không offset | Khác cách diễn giải thời điểm. |
| `status=PAID` | `status=SETTLED` | Consumer enum/switch chưa hỗ trợ. |
| Boolean `paid=true` | String `"true"` | Sai JSON type. |
| Required array `items` | `items=null` hoặc thiếu | Khác presence/nullability. |
| Ordered history | Cùng phần tử nhưng thứ tự khác | Sai semantics nếu thứ tự có ý nghĩa. |

**Producer test chỉ bảo vệ semantics nếu contract có assertions tương ứng.** Nếu hợp đồng chỉ kiểm `amountMinor` là number, nó không biết đơn vị có bị đổi. Business invariant cần được diễn đạt bằng contract scenario/matcher hoặc test nghiệp vụ phù hợp.

## 8. Nguyên nhân 5: request của consumer không khớp stub

Consumer test qua Stub Runner có thể thất bại dù producer verification PASS vì consumer gửi:

- Sai method hoặc path.
- Thiếu query parameter.
- Header `Accept`/`Content-Type` khác mapping.
- Body thiếu field hoặc khác JSON type.
- Request ID động bị matcher so equality với mẫu cố định.
- Authorization header bị gửi sai hoặc không được cấu hình trong test.

Ví dụ contract request:

~~~groovy
request {
    method 'GET'
    url '/api/orders/42'
    headers {
        header('Accept', 'application/json')
    }
}
~~~

Nhưng consumer gọi `/api/order/42` (thiếu chữ `s`) hoặc `POST`. WireMock có thể trả **404 no-match**. Đây không phải bằng chứng producer có response 404 nghiệp vụ.

**Hãy xem request thực tế và mapping**:

1. Method có đúng?
2. Path có đúng sau khi URL template được expand?
3. Query parameters có được encode/serialize đúng?
4. Headers bắt buộc có hiện diện?
5. Body có đúng cấu trúc/kiểu?
6. Stub artifact có chứa mapping mới nhất?

Đừng nới request matcher đến mức mọi request đều match. Stub phải phát hiện consumer gửi sai request.

## 9. Nguyên nhân 6: status code và error handling không tương thích

Một client có thể chỉ xử lý `200` nhưng producer trả `202` hoặc `204` theo hành vi mới. Hoặc producer trả `409` cho duplicate request trong khi consumer chỉ map `400`.

| Response | Consumer cần có hành vi tương ứng |
| --- | --- |
| 200 OK | Deserialize body và xử lý dữ liệu thành công. |
| 201 Created | Có thể cần đọc body và/hoặc `Location`. |
| 202 Accepted | Không giả định kết quả nghiệp vụ đã hoàn tất. |
| 204 No Content | Không cố deserialize JSON body không tồn tại. |
| 400 Bad Request | Map validation errors. |
| 401 Unauthorized | Xử lý token/authentication. |
| 403 Forbidden | Phân biệt thiếu quyền với thiếu xác thực. |
| 404 Not Found | Xử lý resource không tồn tại. |
| 409 Conflict | Xử lý state conflict/idempotency. |
| 429 Too Many Requests | Tôn trọng retry/backoff/Retry-After nếu được cam kết. |
| 5xx | Timeout/retry/circuit breaker theo policy. |

**Producer contract tests phải có các error scenarios mà producer cam kết**; consumer tests phải kiểm cách client xử lý chúng. Không nên dùng matcher “bất kỳ 4xx” để che sự khác nhau giữa 401, 403, 404 và 409.

## 10. Nguyên nhân 7: Stub Runner đang dùng artifact cũ hoặc sai

Một producer vừa sửa contract và producer test PASS, nhưng consumer test vẫn fail. Có thể Billing đang tải:

~~~text
com.acme:order-service:1.4.1:stubs
~~~

trong khi producer build mới tạo:

~~~text
com.acme:order-service:1.4.2:stubs
~~~

Hoặc cả hai run cùng tọa độ `1.4.2` nhưng repository cho phép overwrite JAR.

Consumer cấu hình:

~~~java
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.4.2:stubs",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.org/repository/releases"
)
~~~

Các điểm cần xác minh:

- `groupId:artifactId:version:classifier` chính xác.
- `StubsMode.LOCAL` hay `REMOTE`.
- Maven local cache có JAR cũ cùng tọa độ không.
- Remote repository có trả đúng release bytes không.
- Stub JAR có chứa mapping/contract vừa sửa không.
- Checksum của JAR được tải có khớp producer build record không.
- Consumer test có đang dùng `latest`/`SNAPSHOT` mutable không.

**Thay contract trong source không tự thay JAR mà Stub Runner đang tải.** Phải build, publish/cài đúng artifact, ghim version và kiểm nội dung thực tế.

## 11. Nguyên nhân 8: producer stub và producer image không cùng một build

Một lỗi quy trình nghiêm trọng:

1. Producer CI build A chạy generated tests và publish JAR `stubs`.
2. Một job khác build lại image từ branch đã thay đổi hoặc dependency graph khác.
3. Image mới được deploy nhưng consumer đã kiểm với JAR của build A.

Khi đó, **producer tests PASS và consumer tests PASS đều có thể đúng**, nhưng không áp dụng cho cùng release.

Một release record nên nối:

| Trường | Ví dụ |
| --- | --- |
| Producer Git SHA | Full commit SHA. |
| Contract paths | Những file Groovy/YAML đã được nạp. |
| Producer CI run | ID của build đã chạy verification. |
| Producer test report | Link/report ID, test count. |
| Stub coordinates | `com.acme:order-service:1.4.2:stubs`. |
| Stub checksum | SHA-256 của JAR đã publish. |
| Container image digest | Digest image producer được deploy. |
| Deployment revision | Environment, region, rollout ID. |

**Promote chính artifact đã được xác minh** hoặc chứng minh build/deploy tái tạo từ cùng source/toolchain và có gate tương ứng. Đừng dùng tên tag mutable làm bằng chứng duy nhất.

## 12. Consumer test với Stub Runner: phải dùng client thật

Một test hữu ích không chỉ kiểm Stub Runner tải được artifact. Nó cần gọi **mã HTTP client thực của Billing**:

~~~java
package com.acme.billing;

import java.net.URL;
import java.util.Objects;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubFinder;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.4.2:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class BillingOrderClientContractTest {

    @Autowired
    StubFinder stubFinder;

    @Test
    void billingClientReadsPaidOrder() {
        URL stubUrl = Objects.requireNonNull(
            stubFinder.findStubUrl("com.acme", "order-service")
        );

        OrderClient client = new OrderClient(stubUrl.toExternalForm());
        OrderDto order = client.getOrder(42L);

        assertThat(order.id()).isEqualTo(42L);
        assertThat(order.status()).isEqualTo("PAID");
        assertThat(order.amountMinor()).isEqualTo(125000L);
        assertThat(order.currency()).isEqualTo("VND");
    }
}
~~~

`OrderClient` và `OrderDto` là các lớp ứng dụng của Billing trong ví dụ. Với `LOCAL`, JAR stub phải tồn tại trong Maven local repository của test runner. Với `REMOTE`, cần repository URL và read credentials phù hợp.

**Không tự tạo một RestClient mới trong test nếu production dùng một client khác có cấu hình riêng** rồi kết luận consumer tương thích. Nếu code production sử dụng `OrderClient` được inject với base URL, converter, interceptors, auth, timeout và error handler riêng, test nên sử dụng chính bean/client đó hoặc cùng factory/configuration.

### 12.1. Kiểm cả request mà client gửi

Consumer có thể deserialize được response mẫu nhưng gửi sai URL/header. Hãy kiểm request qua WireMock journal hoặc API verify tương ứng:

~~~java
wireMockServer.verify(
    1,
    getRequestedFor(urlEqualTo("/api/orders/42"))
        .withHeader("Accept", containing("application/json"))
);
~~~

Đoạn này giả định test có quyền truy cập đúng `WireMockServer` instance. Với Stub Runner, nếu không có bean server trực tiếp, có thể kiểm **WireMock Admin API** tại URL mà `StubFinder` trả. Tránh hardcode port vì Stub Runner thường cấp port động.

## 13. Consumer compatibility matrix

Một consumer có thể có nhiều version đang được hỗ trợ. Không nên chỉ test phiên bản mới nhất:

| Consumer | Producer stub release | Trạng thái kiểm | Ý nghĩa |
| --- | --- | --- | --- |
| Billing 3.7 | Order 1.4.1 stubs | PASS | Baseline trước thay đổi. |
| Billing 3.7 | Order 1.4.2 stubs | FAIL | Consumer cũ không tương thích release mới. |
| Billing 3.8 | Order 1.4.2 stubs | PASS | Client mới đã hỗ trợ schema mới. |
| Analytics batch 2.2 | Order 1.4.2 stubs | NOT TESTED | Cần xác minh trước khi tuyên bố release an toàn. |

Đây là bảng **giả định minh họa**, không phải kết quả test thực. Nó cho thấy một producer release có thể tương thích với consumer mới nhưng phá consumer cũ.

**Ma trận nên ưu tiên**:

- Consumer versions đang chạy production hoặc còn được hỗ trợ.
- Producer release sắp triển khai.
- Consumer có lịch deploy dài (batch, mobile, external partner).
- Các scenario liên quan field/enum/error/header/auth đã thay đổi.
- Các phiên bản đang trong deprecation/migration window.

Không nhất thiết test mọi tổ hợp lịch sử, nhưng **mọi tổ hợp được tuyên bố hỗ trợ phải có bằng chứng** hoặc một quyết định ngoại lệ được ghi rõ.

## 14. API v1/v2 và expand–migrate–contract

Nếu producer thay schema phá tương thích, ví dụ:

~~~json
{
  "id": 42,
  "status": "PAID",
  "amountMinor": 125000
}
~~~

thành:

~~~json
{
  "orderId": "ORD-42",
  "state": "PAID",
  "amount": {
    "minor": 125000,
    "currency": "VND"
  }
}
~~~

thì không thể kỳ vọng consumer v1 tự tương thích. Một hướng an toàn:

1. **Expand:** thêm v2, giữ v1 đúng semantics trong migration window.
2. **Migrate:** consumer chuyển sang v2, chạy Stub Runner tests với v2 artifact và deploy.
3. **Verify:** kiểm consumer inventory/usage, error behavior, telemetry và deployment evidence.
4. **Contract:** chỉ bỏ v1 sau khi quyết định EOL được phê duyệt.

Producer release trong giai đoạn migration phải **kiểm cả v1 và v2** nếu còn cam kết hỗ trợ cả hai. JAR `stubs` đi cùng producer release cần phản ánh các hợp đồng còn được hỗ trợ.

## 15. Consumer cấu hình sai base URL hoặc path

Consumer test có thể gọi đúng stub nhưng production gọi sai service:

~~~text
Contract path:  /api/orders/{id}
Consumer config: https://order-service/api/order/{id}
                                  ^ thiếu "s"
~~~

Một số lỗi thường gặp:

- Base URL đã chứa `/api` nhưng client nối thêm `/api` lần nữa.
- URL template bị encode dấu ngoặc hoặc query sai.
- Gateway prefix/route rewrite khác test environment.
- Consumer dùng HTTP thay vì HTTPS hoặc hostname khác.
- DNS/service discovery trỏ sang phiên bản hoặc service cũ.
- Timeout/proxy/TLS certificate khiến request không tới producer.

**Stub Runner thường cung cấp URL riêng cho WireMock**, không tự thay thế toàn bộ service discovery/runtime config của production. Consumer test phải inject stub URL vào đúng abstraction, còn deployment phải cấu hình base URL/route chính xác.

### 15.1. Phân biệt lỗi HTTP client với lỗi contract

| Dấu hiệu | Hướng kiểm |
| --- | --- |
| Connection refused | Stub URL/port, server lifecycle, network namespace. |
| 404 no-match | Method/path/query/header/body và mapping stub. |
| 401/403 | Authorization, token scopes, security config. |
| 415 Unsupported Media Type | Request `Content-Type` và converter. |
| 406 Not Acceptable | Request `Accept` và producer media type. |
| 429 | Rate limit/retry policy. |
| 5xx | Producer runtime, gateway, dependency hoặc test fixture. |
| Timeout | Network, async behavior, retry và timeout config. |
| JSON parse exception | Response body thực, media type, DTO/converter. |

Đừng đổi contract path khi lỗi thực tế là consumer base URL hoặc gateway rewrite.

## 16. Headers, content negotiation và serialization

Producer test chạy trong MockMvc có thể pass, nhưng consumer thực dùng một HTTP client khác với converter/configuration khác.

Kiểm tra:

- `Accept`: client có chấp nhận media type producer trả?
- `Content-Type`: server trả JSON hay một media type khác?
- `charset`: consumer có decode đúng encoding?
- `Content-Encoding`: gzip/br có được client giải nén?
- `Authorization`: token audience/scope có đúng?
- `If-Match`/`ETag`: optimistic concurrency semantics có khớp?
- `Idempotency-Key`: retry có dùng cùng key theo policy?
- `Location`: client tạo resource có đọc đúng URL?
- `Retry-After`: consumer có tôn trọng throttling policy?

Ví dụ:

~~~http
Content-Type: application/json;charset=UTF-8
~~~

và:

~~~http
Content-Type: application/problem+json
~~~

không phải lúc nào cũng được converter xử lý giống nhau. Nếu consumer chỉ cấu hình JSON converter cho `application/json`, response problem details có thể không được parse như DTO lỗi dự kiến.

**Không bỏ assertions header để giải quyết lỗi converter** khi header đó là một phần của contract. Xác định media type thực và điều chỉnh contract/client có review.

## 17. Error decoder và retry behavior của consumer

Nhiều consumer dùng một client wrapper:

~~~java
public OrderDto getOrder(long id) {
    return restClient.get()
        .uri("/api/orders/{id}", id)
        .retrieve()
        .body(OrderDto.class);
}
~~~

Đoạn ngắn này không cho thấy error mapping. Trong code thật, có thể có:

- `onStatus(...)` hoặc `ResponseErrorHandler`.
- Retry template/resilience policy.
- Circuit breaker/time limiter.
- Exception mapping sang domain error.
- Logging/metrics/interceptor.

Nếu producer đổi 404 body hoặc status 409, client wrapper có thể ném exception khác hoặc retry sai. **Consumer contract test nên kiểm cả happy path và error paths mà ứng dụng phụ thuộc**, không chỉ DTO thành công.

Một test có thể kiểm:

~~~java
assertThatThrownBy(() -> client.getOrder(999L))
    .isInstanceOf(OrderNotFoundException.class);
~~~

Điều này giả định client có mapping domain exception như trên. Nếu API trả 404 theo một error code cụ thể, test nên bảo đảm exception có đúng code/meaning; không chỉ kiểm bất kỳ exception nào.

## 18. Messaging: producer verification đạt nhưng consumer listener không đọc được

Với event-driven architecture, producer test có thể xác minh event được phát trong test adapter nhưng consumer vẫn lỗi do:

- Topic/destination hoặc routing key khác.
- Header `eventType`/`schemaVersion` bị mất hoặc đổi kiểu.
- Serializer tạo bytes không đúng schema consumer.
- Consumer listener đăng ký group/queue sai.
- Broker retention, offset, retry hoặc DLQ làm consumer nhận message cũ.
- Consumer không hỗ trợ event version mới.
- Adapter test dùng fake/in-memory trong khi production dùng SDK/codec khác.

Ví dụ contract message:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'orderCreatedV1'
    input {
        triggeredBy('publishOrderCreated()')
    }
    outputMessage {
        sentTo('orders.created')
        headers {
            header('eventType', 'OrderCreated')
            header('schemaVersion', 1)
            header('contentType', 'application/json')
        }
        body(
            eventId: 'evt-42',
            orderId: 'ORD-42',
            amountMinor: 125000,
            currency: 'VND'
        )
    }
}
~~~

Producer verification PASS chứng minh **message quan sát được qua verifier adapter** phù hợp contract trong test context. Nếu adapter dùng fake, điều đó **không chứng minh bytes trên broker thật** giống hệt. Khi transport/codec là rủi ro, cần integration test với broker test environment và consumer decoder thật.

### 18.1. Consumer Stub Runner message trigger

Consumer có thể trigger message từ label của stub artifact:

~~~java
assertThat(stubTrigger.trigger(
    "com.acme:order-service", "orderCreatedV1"
)).isTrue();

assertThat(billingEventProbe.awaitOrder(
    "ORD-42", Duration.ofSeconds(5)
)).isTrue();
~~~

`stubTrigger` và `billingEventProbe` là các bean/test helper được cấu hình theo project. Test cần sender adapter và transport mà listener thật đang đọc. **Trigger thành công không tự chứng minh listener đã xử lý đúng**; phải assert side effect nghiệp vụ.

Nếu consumer test dùng Stub Runner messaging với fake sender trong khi listener production kết nối broker khác, hai thành phần không gặp nhau. Kiểm Spring test context, adapter bean, destination mapping, headers và queue/topic namespace.

## 19. Consumer test xanh với stub nhưng production vẫn lỗi

Đây là trường hợp ngược lại: Stub Runner consumer test PASS, nhưng khi gọi producer thật lại fail.

Nguyên nhân có thể:

1. Stub JAR cũ hoặc mapping mẫu không phản ánh response thực của producer release.
2. Stub response cố định có field mà producer runtime đang thiếu.
3. Producer image deploy không phải build đã được contract verification.
4. Gateway/auth/TLS/content negotiation khác test.
5. Producer data thực có enum/null/range không xuất hiện trong fixture.
6. Consumer test không dùng production HTTP client configuration.
7. Consumer chỉ test happy path, không test timeout/error/retry.

**Stub là một mô hình hành vi hợp đồng, không phải bản sao của toàn bộ producer runtime.** Cần smoke/integration test sau deploy và quan sát runtime để xác nhận.

### 19.1. So sánh response thật với contract một cách an toàn

Trong incident, thu thập:

- HTTP method, route template, status.
- Media type và các header contract-relevant.
- Schema/body sample đã **redact PII/secrets**.
- Producer deployment revision/image digest.
- Consumer release và trace/correlation ID.
- Contract source/version và stub artifact checksum.

Không log Authorization, cookie, token hoặc raw customer payload chỉ để debug. Có thể tạo một request synthetic tương đương trong staging để tái hiện.

## 20. Contract Verifier, Stub Runner và integration tests có phạm vi khác nhau

| Loại test | Phạm vi | Phát hiện tốt | Không đủ để kết luận |
| --- | --- | --- | --- |
| Generated producer verification | Producer code với contract scenario | Response/message producer không đúng contract. | Consumer DTO/logic đã tương thích. |
| Stub Runner consumer test | Consumer code với stub artifact | Client/listener không dùng được stub behavior. | Producer image production khớp stub artifact. |
| Adapter/codec unit test | Mapping/serialization helper | Lỗi converter, header mapping, custom logic. | Broker/runtime đầy đủ. |
| Broker/HTTP integration test | Transport thật hoặc test instance đại diện | Routing, codec, auth, delivery. | Mọi deployment/consumer combination. |
| Staging smoke/E2E | Các service đã triển khai | Cấu hình/runtime/network thực tế. | Mọi edge case, mọi consumer version. |

**Một pipeline trưởng thành dùng các lớp này bổ trợ nhau**. Không bắt mọi PR chạy full E2E nếu tốn kém, nhưng phải có gate phù hợp với rủi ro thay đổi và một lớp xác nhận sau deploy.

## 21. Quy trình chẩn đoán theo bằng chứng

~~~mermaid
flowchart TD
    A["Consumer báo lỗi sau producer release"] --> B["Xác định consumer release + trace/request"]
    B --> C["Kiểm request: method/path/query/headers/body"]
    C --> D["Kiểm response thực: status/media type/schema"]
    D --> E["Đối chiếu consumer DTO/client/error handling"]
    E --> F["Kiểm contract source và generated producer tests"]
    F --> G["Kiểm stub coordinates/checksum/mapping"]
    G --> H["Nối producer Git SHA -> image digest -> deployment"]
    H --> I{"Cùng release và đúng semantics?"}
    I -->|Không| J["Sửa version/artifact/deployment hoặc contract gap"]
    I -->|Có| K["Sửa consumer/client/config/transport"]
    J --> L["Chạy lại producer + consumer + integration checks"]
    K --> L
~~~

Thực hiện theo thứ tự:

1. **Xác định lỗi chính xác:** request timeout, 404 no-match, 401/403, 415, JSON parse, business result sai hay message không tới.
2. **Ghi consumer release:** Git SHA, application version, HTTP client/configuration hoặc listener version.
3. **Xem request thực tế:** method/path/query/headers/body; không suy từ code gọi.
4. **Xem response/message thực tế:** status, media type, JSON types, error code, destination và headers.
5. **So consumer DTO/decoder:** field mapping, enum, nullability, date/time, number precision, error handling.
6. **Đọc contract source:** scenario có mô tả đúng consumer need không, matcher có quá lỏng không?
7. **Xem generated producer test:** test nào thực thi, assertion nào kiểm field/semantics, có bị skip không?
8. **Xem stub artifact:** version, mode LOCAL/REMOTE, checksum, mappings và source producer run.
9. **Xem producer deployment:** image digest, environment/region, rollout revision, config.
10. **Tái hiện có kiểm soát:** cùng consumer source và đúng stub artifact hoặc staging producer release.
11. **Sửa ở đúng lớp:** contract gap, producer implementation, consumer client, artifact publishing, deployment hay transport.
12. **Chạy lại cả hai phía:** producer verification và consumer Stub Runner tests; thêm integration/smoke test theo rủi ro.

## 22. Ma trận triệu chứng và nguyên nhân

| Triệu chứng | Nguyên nhân có thể | Kiểm tra ưu tiên |
| --- | --- | --- |
| Producer test PASS, consumer JSON parse fail | DTO/field/type/media type khác | Response thực, DTO, Jackson config. |
| Consumer nhận `null` cho field | Field thiếu/null hoặc tên JSON không khớp | Contract body và JSONPath/DTO mapping. |
| Consumer enum mapping fail | Producer thêm/đổi enum value | Enum contract và forward compatibility. |
| Consumer tính tiền sai nhưng deserialize thành công | Đơn vị/rounding/semantics đổi | Business invariant, currency, scale. |
| Stub Runner trả 404 | Request không khớp mapping hoặc artifact cũ | WireMock journal, path/method/headers/body, JAR version. |
| Stub Runner trả 200 nhưng production 404 | Gateway route/base URL/deployment khác | Runtime URL, routing, producer deployment. |
| Producer test xanh nhưng 401/403 ở production | Test security context khác, token/scope khác | Auth contract, gateway/security config. |
| Consumer không nhận message | Destination/header/group/adapter mismatch | Broker route, listener, consumer group, test namespace. |
| Stub trigger thành công nhưng business state không đổi | Listener không xử lý hoặc probe không chờ đúng | Sender adapter, listener binding, side effect. |
| Consumer test xanh với stub nhưng production schema khác | Stub cũ hoặc producer image lệch build | Artifact checksum, image digest, release manifest. |
| Producer test chỉ có một happy path | Contract thiếu error/scenario | Coverage và consumer requirements. |
| Matcher byType pass dù giá trị sai | Matcher quá rộng | Equality/range/invariant và mutation tests. |
| Consumer cũ fail sau field mới | Strict deserializer/schema đóng | Unknown-field policy và supported consumer matrix. |
| Consumer nhận 202 nhưng code đợi body hoàn chỉnh | Status semantics không tương thích | Contract status và async workflow. |
| Response lỗi có HTML thay JSON | Gateway/security/error handler | Status, Content-Type và error path. |
| Test chỉ fail trên production | Config/network/TLS/proxy/data thực | Environment parity, smoke tests, telemetry. |
| Release mới phá v1 nhưng consumer v2 pass | Chỉ test consumer mới, thiếu legacy matrix | Consumer versions đang hỗ trợ và v1 contracts. |

## 23. Những sửa chữa sai thường làm tình hình tệ hơn

| Cách sửa hấp tấp | Vì sao nguy hiểm | Cách xử lý đúng |
| --- | --- | --- |
| Nới mọi matcher sang `byType()` | Che giá trị enum, ID, amount sai. | Chỉ nới field động, giữ business assertions. |
| Bỏ producer contract test vì consumer đang fail | Mất bằng chứng producer implementation. | Xác định test nào thiếu scenario hoặc matcher sai. |
| Bỏ consumer Stub Runner test vì producer test xanh | Không còn kiểm client thật. | Sửa DTO/client/request và giữ test. |
| Cập nhật mọi consumer DTO để khớp response chưa review | Có thể chấp nhận breaking change không được thống nhất. | Review API change, versioning và consumer impact. |
| Dùng `latest` để “lấy stub mới nhất” | Rerun không tái lập, cache có thể chọn khác. | Pin version/checksum. |
| Chỉ kiểm một consumer version | Bỏ sót binary cũ còn chạy production. | Ma trận supported consumer/producer. |
| Mock toàn bộ HTTP client | Không kiểm URL, converter, interceptors hoặc error handler thật. | Dùng client production với base URL được thay bằng Stub Runner. |
| Tắt security filter trong mọi test | Producer test xanh giả dù production auth sai. | Negative contract/security scenarios riêng. |
| Coi WireMock 404 là nghiệp vụ 404 | Có thể client gọi sai path. | Kiểm request journal và error body mapping. |
| Chỉnh generated test code | Bị ghi đè ở lần generate sau. | Sửa Groovy/YAML contract hoặc base test. |
| Deploy image rebuild khác artifact đã verify | Stub và producer runtime lệch nhau. | Promote verified artifacts và lưu digest. |
| Bỏ v1 ngay khi v2 producer test pass | Consumer v1 vẫn có thể đang được hỗ trợ. | Expand–migrate–contract và EOL gates. |

## 24. CI gates để tránh tình trạng “producer xanh, consumer đỏ”

~~~mermaid
flowchart TD
    A["Producer PR + contract diff"] --> B["Review consumer impact + API owner"]
    B --> C["Generate producer tests"]
    C --> D["Run producer verification"]
    D --> E{"Required scenarios pass?"}
    E -->|No| X["Block publish"]
    E -->|Yes| F["Package immutable stubs + checksum"]
    F --> G["Consumer matrix: Stub Runner + real clients"]
    G --> H{"Supported consumers pass?"}
    H -->|No| Y["Block release or approve migration exception"]
    H -->|Yes| I["Build/promote verified producer image"]
    I --> J["Deploy canary + smoke/integration checks"]
    J --> K["Record runtime version and monitor"]
~~~

Các gate nên có:

1. **Contract review:** có owner, affected consumers, compatibility classification.
2. **Producer verification:** generated tests được sinh và chạy, không phải 0 tests hoặc skipped.
3. **Matcher quality:** required fields, types, enum, status, error scenarios và business invariants được bảo vệ.
4. **Stub packaging:** JAR `stubs` chứa mappings/contracts dự kiến, version bất biến, checksum lưu lại.
5. **Consumer matrix:** test client/listener thật của các consumer được hỗ trợ với artifact đúng version.
6. **Legacy support:** nếu producer còn hỗ trợ v1, chạy các v1 contracts/tests trên release producer hiện tại.
7. **Provenance:** producer Git SHA, CI run, stub checksum, image digest có thể đối chiếu.
8. **Post-deploy:** smoke/integration tests và metrics/traces xác nhận runtime.
9. **Rollback/migration:** có kế hoạch nếu một consumer ngoài inventory hoặc consumer cũ gặp lỗi.

**Một consumer không có kết quả test không nên được coi là PASS.** Ghi rõ NOT TESTED/EXEMPTED và owner/phê duyệt, không chuyển trạng thái bằng giả định.

## 25. Bài thực hành: producer PASS nhưng Billing không tương thích

Thực hành với Order Service producer và Billing Service consumer:

1. **Tạo contract v1** cho `GET /api/orders/42` trả `id`, `status`, `amountMinor`, `currency`; tạo base test và generated producer tests.
2. **Chạy producer verification** và xác nhận test thật sự được sinh/chạy. Cố tình đổi `amountMinor` thành string để chứng minh test fail.
3. **Tạo Billing OrderClient và DTO thật**, cấu hình client qua base URL có thể inject trong test.
4. **Publish stub artifact version cụ thể**, ví dụ `com.acme:order-service:1.4.2:stubs`; kiểm JAR có mappings mới và lưu checksum.
5. **Chạy Stub Runner consumer test** dùng `LOCAL` hoặc `REMOTE`; tìm URL động bằng `StubFinder`, gọi client thật và assert field/semantics.
6. **Gây lỗi consumer có kiểm soát:** đổi DTO field name, bỏ currency, thay enum mapping hoặc dùng sai path; quan sát test fail và ghi chính xác exception/status.
7. **Gây lỗi matcher quá rộng:** đổi `status=PAID` thành `CANCELLED` nhưng chỉ giữ `byType()`; chứng minh producer test có thể không phát hiện, rồi bổ sung equality/business assertion.
8. **Thêm negative contracts** cho 404/401/403/409; kiểm producer verification và Billing error mapping.
9. **Thử artifact drift:** chạy consumer với JAR stub cũ rồi JAR mới, so kết quả; ghi coordinates/checksum mỗi lượt.
10. **Thử producer image drift:** mô phỏng deploy image khác producer CI build đã verify; giải thích vì sao producer test và consumer stub test vẫn có thể xanh.
11. **Lập compatibility matrix** cho Billing cũ/mới và Analytics batch; đánh dấu NOT TESTED khi chưa có bằng chứng.
12. **Thử v2 breaking change** đổi `amountMinor` thành `amount.minor`; thêm v2 riêng, giữ v1 trong migration window và chạy cả hai bộ producer tests.
13. **Thêm một message contract** `OrderCreated` với `eventType`/`schemaVersion`; trigger qua Stub Runner và assert Billing listener side effect.
14. **Nếu có broker test**, kiểm serializer/headers/route trên broker test thật; phân biệt kết quả fake adapter và transport integration.
15. **Gắn CI gates** producer verification → stub packaging → consumer matrix → verified image promotion → staging smoke.
16. **Viết incident note** nêu triệu chứng, request/response thực, contract/version, producer test report, stub checksum, consumer release và nguyên nhân gốc.

**Tiêu chí đạt:** người học giải thích được producer test xanh chứng minh gì và không chứng minh gì; tìm được nguyên nhân consumer incompatibility ở đúng lớp; chạy consumer test với client/listener thật và đúng stub version; phân biệt lỗi contract, DTO, request, artifact và deployment; bảo vệ các consumer versions còn được hỗ trợ.

## 26. Câu hỏi tự kiểm tra

1. Generated producer test PASS chứng minh chính xác điều gì?
2. Vì sao kết quả producer verification không chứng minh mọi consumer đều tương thích?
3. Khác biệt giữa producer verification và Stub Runner consumer test là gì?
4. Nếu contract chỉ có happy path 200, các lỗi 401/403/404/409 có được bảo vệ không?
5. Vì sao `byType()` cho `status` có thể che `PAID` đổi thành `CANCELLED`?
6. Một JSON response đúng contract vẫn có thể làm Jackson DTO fail trong trường hợp nào?
7. `@JsonIgnoreProperties(ignoreUnknown = true)` giải quyết được vấn đề nào và không giải quyết vấn đề nào?
8. Vì sao JSON parse thành công chưa đủ chứng minh semantics của amount/currency đúng?
9. Khi Stub Runner trả 404, làm sao phân biệt no-match với 404 nghiệp vụ?
10. Vì sao cần kiểm method/path/query/header/body thực tế của consumer?
11. `LOCAL` và `REMOTE` trong Stub Runner khác nhau ở đâu?
12. Vì sao cùng Maven coordinates chưa đủ chứng minh JAR `stubs` giống nhau?
13. Producer stub JAR và producer image phải được liên kết bằng thông tin nào?
14. Consumer test nên dùng HTTP client production hay tạo một client khác trong test? Vì sao?
15. Vì sao cần kiểm cả status/error decoder/retry behavior?
16. Khi producer hỗ trợ đồng thời API v1/v2, pipeline phải bảo vệ hợp đồng nào?
17. Producer messaging test PASS với fake adapter có chứng minh broker serialization thật không?
18. StubTrigger trả true có chứng minh consumer listener đã xử lý event không?
19. Các lớp test nào nên bổ sung cho schema registry, routing, broker ack/retry?
20. Nếu consumer mới PASS nhưng Billing cũ FAIL, release producer có thể được coi là tương thích với mọi consumer đang hỗ trợ không?
21. Những thông tin nào cần thu thập khi điều tra lỗi production mà không log secrets/PII?
22. Vì sao CI nên ghi NOT TESTED thay vì mặc định consumer không có kết quả là PASS?

## 27. Checklist chẩn đoán nhanh

| Nhóm | Cần xác nhận |
| --- | --- |
| **Contract coverage** | Có đúng scenario, request, response, errors, headers và business semantics consumer cần? |
| **Producer verification** | Generated tests đã sinh/chạy đủ, không skip/0 test ngoài ý muốn? |
| **Matcher quality** | Không quá rộng ở status, enum, required fields, type, amount hoặc auth? |
| **Consumer client** | Dùng DTO, converter, base URL, headers, timeout và error decoder đúng? |
| **Consumer test** | Stub Runner gọi client/listener thật và assert kết quả nghiệp vụ? |
| **Stub artifact** | Đúng coordinates, version, classifier, mode, checksum và mappings? |
| **Request matching** | Method/path/query/header/body có khớp? Có 404 no-match không? |
| **Runtime response** | Status, Content-Type, body, null/type/enum/units có khớp contract? |
| **Version matrix** | Tất cả consumer versions được hỗ trợ đã có bằng chứng? |
| **Deployment provenance** | Producer image digest có cùng nguồn build đã verification? |
| **Messaging** | Destination, schemaVersion, headers, codec, offset/replay và listener đúng? |
| **CI/post-deploy** | Có compatibility gates, smoke tests, monitoring và rollback? |

**Ghi nhớ:** **Producer test đạt là điều kiện cần, không phải chứng nhận tương thích toàn hệ thống.** Hãy kiểm xem contract có mô tả đúng nhu cầu consumer và có đủ error/business scenarios; generated assertions có đủ chặt; consumer test có dùng client/listener thật; Stub Runner có tải đúng JAR `stubs`; producer image có thực sự là bản đã được xác minh; và các consumer versions còn được hỗ trợ có nằm trong compatibility matrix. Khi điều tra, đi từ request/response hoặc message thực tế tới DTO, contract, generated test, artifact và deployment record. Sửa đúng lớp gây lỗi, giữ producer verification và consumer tests cùng hoạt động, rồi thêm CI gates để phát hiện lại regression trước khi release.

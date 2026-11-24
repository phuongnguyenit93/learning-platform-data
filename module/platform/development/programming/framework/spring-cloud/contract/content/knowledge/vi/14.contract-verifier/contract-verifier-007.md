# Đọc mã kiểm thử được sinh để hiểu lời gọi và assertion

## 1. Vì sao cần đọc generated tests thay vì chỉ xem build xanh hay đỏ?

Khi dùng **Spring Cloud Contract**, nhóm phát triển thường viết hợp đồng bằng Groovy hoặc YAML DSL rồi để **Contract Verifier** sinh mã kiểm thử phía **producer**. Các test này gọi HTTP endpoint hoặc kích hoạt hành vi gửi message của producer và kiểm tra rằng kết quả phù hợp với cam kết dành cho **consumer**.

Ví dụ, một consumer gọi `GET /api/orders/ORD-123` và cần nhận JSON:

~~~json
{
  "orderId": "ORD-123",
  "status": "CONFIRMED",
  "totalAmount": 120000
}
~~~

Một lần refactor có thể khiến producer đổi tên `orderId` thành `id` hoặc trả `"totalAmount": "120000"` thay vì một số. Code Java vẫn biên dịch và các unit test nghiệp vụ có thể vẫn đạt, nhưng consumer có nguy cơ hỏng. Generated contract test giúp chặn thay đổi này trước khi phát hành.

Để **hiểu vì sao test đạt hoặc thất bại**, cần biết đọc mã test được sinh:

- **Lời gọi (invocation/request):** Test gửi method, path, headers, query và body nào tới producer?
- **Assertion:** Test đang đòi hỏi HTTP status, header, JSON field hoặc kiểu dữ liệu nào?
- **Nguồn giá trị:** Giá trị nào được lấy từ contract, giá trị nào do base class hoặc fixture cung cấp?
- **Phạm vi bảo vệ:** Test có thực sự kiểm chứng điều consumer cần, hay chỉ kiểm tra một ví dụ quá hẹp?
- **Hành động khi thất bại:** Cần sửa producer, test setup, contract hay phối hợp thay đổi với consumer?

Bài học thuộc chương **Contract Verifier** của module `SPRING_CLOUD_CONTRACT`. Mục tiêu không phải học thuộc mã Java do một phiên bản plugin sinh ra, mà là **đọc được ý nghĩa hành vi của generated test** để hỗ trợ kiểm thử hợp đồng HTTP/messaging, phát hành stub, dùng Stub Runner và tích hợp CI.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Truy vết từ một tệp Groovy/YAML DSL đến lớp test được sinh tương ứng.
2. Nhận diện cấu trúc `given → when → then` và ý nghĩa các lời gọi HTTP.
3. Hiểu assertion cho status, header, JSONPath, giá trị cố định và matcher linh hoạt.
4. Phân biệt generated test, base class, fixture và test tự viết.
5. Đọc log khi test thất bại để xác định sai ở request, môi trường hay response.
6. Hiểu cách việc sinh và chạy test ở producer liên hệ với stub dành cho consumer.

> **Lưu ý phiên bản:** Mã Java minh họa trong bài là dạng **rút gọn, đại diện cho cấu trúc thường thấy**. Tên lớp, thư viện assertion, import, JSONPath helper và cách tổ chức phương thức do plugin sinh ra có thể khác nhau giữa các phiên bản Spring Cloud Contract, chế độ HTTP test và lựa chọn JUnit. Khi làm việc thực tế, hãy đọc chính file generated test và build output của dự án.

## 2. Luồng từ DSL đến mã test có thể chạy

~~~mermaid
flowchart TD
    A["Contract Groovy/YAML"] --> B["Spring Cloud Contract plugin"]
    B --> C["Sinh mã kiểm thử producer"]
    C --> D["Biên dịch với test sources"]
    D --> E["Generated test kế thừa base class"]
    E --> F["Khởi tạo ứng dụng / MockMvc / HTTP client"]
    F --> G["Gửi request hoặc kích hoạt message"]
    G --> H["Assertion status, header, body hoặc message"]
    H --> I{"Đúng hợp đồng?"}
    I -- "Không" --> J["Build thất bại"]
    I -- "Có" --> K["Producer verification đạt"]
    B --> L["Sinh stub mapping"]
    K --> M["Có thể phát hành stub"]
    L --> M
    M --> N["Consumer test qua Stub Runner"]
~~~

Có bốn sản phẩm hoặc thành phần cần tách biệt:

| Thành phần | Nguồn gốc | Vai trò |
| --- | --- | --- |
| **Contract DSL** | Nhóm phát triển/thỏa thuận giữa producer và consumer | Mô tả request, response, matcher và kỳ vọng công khai |
| **Generated producer test** | Plugin Spring Cloud Contract | Biến hợp đồng thành lời gọi và assertion có thể chạy |
| **Base test class** | Người viết code producer | Cấu hình application context, MockMvc, dependencies, fixture hoặc messaging |
| **Generated stub** | Công cụ sinh stub từ contract | Mô phỏng producer để consumer test bằng Stub Runner |

Generated test **không phải stub**. Một generated test chạy trên code producer; stub là phản hồi được dựng dựa trên contract để consumer gọi trong môi trường kiểm thử độc lập.

## 3. Ví dụ xuyên suốt: hợp đồng HTTP tra cứu đơn hàng

Giả sử `Order Service` cung cấp API:

~~~http
GET /api/orders/ORD-123 HTTP/1.1
Accept: application/json
~~~

Phản hồi cam kết:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "orderId": "ORD-123",
  "status": "CONFIRMED",
  "totalAmount": 120000,
  "paid": true
}
~~~

Tệp `src/test/resources/contracts/orders/get_confirmed_order.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_confirmed_order')
    description('Consumer tra cứu một đơn hàng đã xác nhận')

    request {
        method GET()
        urlPath('/api/orders/ORD-123')
        headers {
            accept(applicationJson())
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            orderId: 'ORD-123',
            status: 'CONFIRMED',
            totalAmount: 120000,
            paid: true
        )
    }
}
~~~

Hãy đọc contract trước khi mở generated test:

- `request.method` là `GET`.
- `request.urlPath` là `/api/orders/ORD-123`.
- `request.headers.Accept` là `application/json`.
- `response.status` là `200`.
- `response.headers.Content-Type` phải thể hiện JSON.
- `response.body` có các trường và giá trị mà consumer dùng.

**Mỗi điều kiện quan trọng này phải có dấu vết trong generated test**: hoặc là một phần request được tạo, hoặc là assertion trên response thực nhận. Nếu sau khi sinh test bạn không thấy nhánh cần kiểm tra, phải đối chiếu DSL và cấu hình plugin trước khi tin vào kết quả build.

## 4. Tìm đúng generated test trong dự án

Trong dự án Maven sử dụng Spring Cloud Contract Verifier, một đường dẫn đầu ra thường gặp là:

~~~text
target/generated-test-sources/contracts/
~~~

Trong dự án Gradle, nguồn test được sinh thường nằm dưới cấu trúc như:

~~~text
build/generated-test-sources/contracts/
~~~

**Đường dẫn chính xác phụ thuộc phiên bản và cấu hình plugin.** Hãy ưu tiên thông tin trong build log, cấu hình generate-contract-tests, test source sets và cấu trúc thư mục mà dự án thật đang tạo. Không giả định rằng hai build tool luôn sinh tên thư mục giống hệt nhau.

Ví dụ cây file minh họa:

~~~text
order-service/
├── src/test/resources/contracts/orders/
│   └── get_confirmed_order.groovy
├── src/test/java/com/example/orders/
│   └── ContractVerifierBase.java
└── target/generated-test-sources/contracts/
    └── com/example/orders/
        └── OrdersTest.java
~~~

Tên `OrdersTest.java` chỉ là ví dụ. Plugin có thể dùng tên khác dựa trên file contract, `name`, package và cấu hình. Cách xác nhận đúng nhất là **mở generated source và tìm phương thức kiểm tra request `/api/orders/ORD-123` hoặc tên contract `get_confirmed_order`**.

### 4.1. Những thứ nên đọc trước trong file test

1. **Package và class name:** Cho biết test thuộc nhóm hợp đồng nào.
2. **`extends ContractVerifierBase`:** Cho biết môi trường test được thiết lập ở đâu.
3. **Import và annotation:** Chỉ ra JUnit, RestAssured MockMvc/HTTP, JSONPath, assertion library.
4. **Phương thức `@Test`:** Một hoặc nhiều tương tác được kiểm tra.
5. **Phần tạo request:** Method, path, headers, body và query thực tế.
6. **Phần kiểm tra response:** Status, headers, body assertions và matcher.

Đừng lấy độ dài hoặc số dòng của file generated test làm chỉ số bảo đảm chất lượng. Một contract có thể tạo test rất ngắn nhưng bỏ sót trường consumer thực sự cần; ngược lại test nhiều assertion có thể trói chặt dữ liệu không cần thiết.

## 5. Đọc cấu trúc generated test: lớp, phương thức và base class

Mã rút gọn sau thể hiện **hình dáng** của một generated test dùng Spring MVC/MockMvc; **không phải nguyên văn đầu ra bắt buộc của plugin**:

~~~java
// PSEUDOCODE JAVA: giúp đọc logic, tên API/assertion thay đổi theo phiên bản
class OrdersContractTest extends ContractVerifierBase {

    @Test
    void validate_get_confirmed_order() {
        // given: chuẩn bị HTTP request
        request.header("Accept", "application/json");

        // when: gọi endpoint producer
        response = request.get("/api/orders/ORD-123");

        // then: kiểm tra HTTP response
        assertStatus(response, 200);
        assertHeaderContains(response, "Content-Type", "application/json");
        assertJsonEquals(response, "$.orderId", "ORD-123");
        assertJsonEquals(response, "$.status", "CONFIRMED");
        assertJsonEquals(response, "$.totalAmount", 120000);
        assertJsonEquals(response, "$.paid", true);
    }
}
~~~

Các hàm `assertStatus`, `assertJsonEquals` và biến `request` trong khối trên **chỉ là ký hiệu minh họa**, không phải API của Spring Cloud Contract mà bạn có thể copy để compile.

Ở nhiều cấu hình Spring Cloud Contract với RestAssured MockMvc, mã thật có thể trông gần với các thành phần sau:

~~~java
// Các dấu hiệu nhận diện thường gặp, không phải generated source hoàn chỉnh
MockMvcRequestSpecification request = given()
    .header("Accept", "application/json");

ResponseOptions response = given()
    .spec(request)
    .get("/api/orders/ORD-123");

assertThat(response.statusCode()).isEqualTo(200);
~~~

Một số phiên bản sinh các dòng `DocumentContext parsedJson = JsonPath.parse(...)` hoặc dùng `assertThatJson(parsedJson)`; phiên bản khác có thể dùng biểu thức kiểm tra tương đương. Khi xem generated source, hãy **dịch các API cụ thể về cùng bốn câu hỏi**:

- Request nào đã được gửi?
- Producer nào nhận request đó?
- Response nào được nhận?
- Assertion nào quyết định pass/fail?

### 5.1. `extends` có tác dụng gì?

Generated test có thể kế thừa base class:

~~~java
public class OrdersContractTest extends ContractVerifierBase {
    // generated tests
}
~~~

`ContractVerifierBase` có thể cung cấp:

- Cấu hình `MockMvc` hoặc client HTTP.
- Spring application context.
- Mock của service/repository hoặc kết nối test database.
- Dữ liệu mẫu như đơn hàng `ORD-123`.
- Xác thực, principal, header mặc định hoặc môi trường messaging.
- Hook `@BeforeEach` hoặc phương thức setup cần thiết.

**Nếu generated test không có controller setup trong chính phương thức `@Test`, không có nghĩa nó chạy “trên không”.** Setup có thể nằm ở base class được kế thừa hoặc trong cấu hình test framework.

## 6. Đọc `given`: request được dựng từ contract như thế nào?

Với hợp đồng `GET /api/orders/ORD-123`, generated test phải chuẩn bị đủ thông tin để gửi đúng lời gọi. Tên `given` trong RestAssured mang nghĩa **khởi tạo điều kiện của request**.

Ví dụ logic cần tìm trong generated code:

~~~java
// Minh họa hình thức thường gặp với RestAssured-style API
MockMvcRequestSpecification request = given()
    .header("Accept", "application/json");
~~~

Trong request test, các điều kiện sau đến từ DSL:

| DSL | Đầu ra cần nhận diện trong test |
| --- | --- |
| `method GET()` | Lời gọi GET, không phải POST |
| `urlPath('/api/orders/ORD-123')` | Path `/api/orders/ORD-123` |
| `accept(applicationJson())` | Header `Accept: application/json` |
| `body(customerId: 'CUS-7')` | Một request body có trường `customerId` |
| `queryParameters { parameter 'page': 0 }` | Query parameter `page=0` |
| `header('X-Trace-ID','TRACE-1')` | Header có tên và giá trị đã khai báo |

**Phân biệt dữ liệu request và response.** `request.body` trong generated test được dùng để **gửi vào producer**, còn `response.body` trong contract được dùng làm **kỳ vọng để assertion**.

### 6.1. Request POST với JSON body

Giả sử contract:

~~~groovy
request {
    method POST()
    urlPath('/api/orders')
    headers {
        contentType(applicationJson())
    }
    body(
        customerId: 'CUS-7',
        items: [
            [sku: 'BK-1', quantity: 2]
        ]
    )
}
~~~

Trong generated test, bạn cần tìm các dấu hiệu tương ứng:

~~~text
HTTP method: POST
Request target: /api/orders
Content-Type: application/json
Body:
{
  "customerId": "CUS-7",
  "items": [{"sku": "BK-1", "quantity": 2}]
}
~~~

Nếu producer test gửi `GET`, thiếu body hoặc gửi `quantity` như String, hãy kiểm tra lại DSL, value/matcher và test mode. Trong build đúng, test được sinh phải phản ánh dữ liệu **producer-side** của request.

### 6.2. `when`: hành động thật sự diễn ra ở đâu?

Từ cấu trúc RestAssured-style:

~~~java
ResponseOptions response = given()
    .spec(request)
    .get("/api/orders/ORD-123");
~~~

phần `.get(...)` là **hành động gọi endpoint**. Đây là ranh giới giữa việc dựng request và nhận response.

Đừng coi những dòng phía sau `then` là phần “trả kết quả” của producer: đó là **assertion của test**. Producer thực sự tạo response thông qua controller/handler và các dependency được base class nạp.

## 7. Đọc `then`: assertion HTTP status

Contract:

~~~groovy
response {
    status OK()
}
~~~

có nghĩa producer phải trả HTTP status `200`. Generated test thường có một assertion logic tương đương:

~~~java
assertThat(response.statusCode()).isEqualTo(200);
~~~

Nếu producer trả `201`, `204`, `404` hoặc `500`, điều kiện này không đạt.

Một số status quan trọng:

| Status trong contract | Số HTTP | Tình huống điển hình |
| --- | --- | --- |
| `OK()` | `200` | Đọc tài nguyên thành công |
| `CREATED()` | `201` | Tạo tài nguyên mới thành công |
| `NO_CONTENT()` | `204` | Thành công nhưng không có response body |
| `BAD_REQUEST()` | `400` | Request không hợp lệ theo chính sách API |
| `NOT_FOUND()` | `404` | Không tìm thấy tài nguyên |
| `CONFLICT()` | `409` | Xung đột với trạng thái hiện tại |

**Status là assertion độc lập với JSON body.** Một response có body `{"code":"ORDER_NOT_FOUND"}` nhưng status `200` không tương đương hợp đồng yêu cầu `404`.

### 7.1. Thất bại `expected 200 but was 404` nói lên điều gì?

Không nên lập tức kết luận producer đã đổi API. Các nguyên nhân có thể gồm:

1. Request path trong DSL không khớp controller mapping.
2. Controller tồn tại nhưng fixture không tạo resource `ORD-123`.
3. Base class mock sai dependency nên producer trả không tìm thấy.
4. Security hoặc routing thay đổi.
5. Producer thực sự bỏ endpoint hoặc đổi hành vi.

Cần truy ngược **request thật gửi**, **test setup** và **response thật nhận** để phân biệt lỗi môi trường với breaking change.

## 8. Đọc assertion header: media type, correlation và version

Contract:

~~~groovy
response {
    status OK()
    headers {
        contentType(applicationJson())
        header('X-Api-Version', '1')
    }
    body(orderId: 'ORD-123')
}
~~~

Generated test sẽ có những kiểm tra tương ứng với:

- `Content-Type` là media type JSON theo matcher đã sinh.
- `X-Api-Version` có giá trị `1` nếu contract yêu cầu.

Tùy phiên bản plugin, một kiểm tra có thể sử dụng Hamcrest, AssertJ hoặc helper riêng. Không cần ghi nhớ chính xác mọi method assertion; hãy tìm **tên header** và **giá trị được đòi hỏi**.

### 8.1. Content-Type thường có thêm charset hoặc thông số

Producer có thể trả:

~~~http
Content-Type: application/json;charset=UTF-8
~~~

khi contract ghi:

~~~http
Content-Type: application/json
~~~

Tùy matcher/header assertion được DSL sinh ra, việc kiểm tra có thể chấp nhận hoặc từ chối phần mở rộng `charset`. Không tự suy ra hai header luôn phải bằng đúng chuỗi hoặc luôn tương đương trong mọi test. Nếu thất bại, mở generated assertion để xem nó dùng **equality, regex, contains hoặc media-type matching**.

Nếu consumer phụ thuộc charset hoặc định dạng nội dung cụ thể, hãy mô tả cam kết đó một cách rõ ràng.

### 8.2. Đừng kiểm tra header mà API không cam kết

Một proxy hoặc server có thể tự thêm `Date`, `Server` hoặc `Transfer-Encoding`. Nếu consumer không phụ thuộc những header đó, không nên ràng buộc cứng chúng trong contract chỉ vì chúng xuất hiện trong một response mẫu. Điều này làm test dễ thất bại vì những thay đổi hạ tầng không liên quan.

## 9. Đọc assertion JSON body và JSONPath

Với response:

~~~json
{
  "orderId": "ORD-123",
  "status": "CONFIRMED",
  "totalAmount": 120000,
  "paid": true
}
~~~

Generated test có thể dùng **JSONPath**, RestAssured body matcher hoặc helper assertion của Spring Cloud Contract để truy cập các trường:

| JSONPath | Giá trị dự kiến | Kiểu JSON |
| --- | --- | --- |
| `$.orderId` | `ORD-123` | String |
| `$.status` | `CONFIRMED` | String |
| `$.totalAmount` | `120000` | Number |
| `$.paid` | `true` | Boolean |

Mã rút gọn về mặt ý tưởng:

~~~java
// PSEUDOCODE ASSERTIONS: không phải tên API cố định của plugin
assertJsonEquals(body, "$.orderId", "ORD-123");
assertJsonEquals(body, "$.status", "CONFIRMED");
assertJsonEquals(body, "$.totalAmount", 120000);
assertJsonEquals(body, "$.paid", true);
~~~

Ở các phiên bản dùng Jayway JSONPath, bạn có thể gặp các dấu hiệu như:

~~~java
DocumentContext parsedJson =
    JsonPath.parse(response.getBody().asString());

// Plugin sẽ sinh các phép kiểm tra field/giá trị tương ứng.
~~~

Nếu mở generated code và thấy `parsedJson` hoặc `jsonPath`, hãy tìm **đường dẫn trường JSON được kiểm tra**. Điều này đặc biệt quan trọng với JSON lồng nhau, ví dụ:

~~~json
{
  "customer": {
    "id": "CUS-7"
  },
  "items": [
    {"sku": "BK-1", "quantity": 2}
  ]
}
~~~

JSONPath:

~~~text
$.customer.id
$.items[0].sku
$.items[0].quantity
~~~

### 9.1. Kiểu JSON là một phần của hợp đồng

Hai JSON này khác nhau:

~~~json
{"totalAmount": 120000, "paid": true}
~~~

~~~json
{"totalAmount": "120000", "paid": "true"}
~~~

Nếu consumer deserialize `totalAmount` thành number và `paid` thành boolean, response thứ hai có thể phá vỡ hợp đồng.

Khi đọc generated test, hãy kiểm tra **assertion có ràng buộc kiểu như mong muốn không**, hoặc có dùng matcher quá rộng khiến producer trả String mà test vẫn đạt. Một test xanh không bảo đảm schema được kiểm tra đầy đủ nếu DSL đã mô tả quá lỏng.

### 9.2. Mảng JSON và thứ tự phần tử

Với:

~~~groovy
body(
    items: [
        [sku: 'BK-1', quantity: 2],
        [sku: 'PEN-9', quantity: 1]
    ]
)
~~~

Generated assertions có thể kiểm tra vị trí mảng, số phần tử hoặc field của từng phần tử theo quy tắc framework sinh ra. Hãy xem test thực tế để biết:

- Nó kiểm tra đúng hai phần tử hay chỉ một vài trường?
- Nó phụ thuộc thứ tự `items[0]`/`items[1]` hay không?
- Nó cho phép mảng có thêm phần tử?
- Nó kiểm tra kiểu `quantity` hay chỉ kiểm tra cách biểu diễn giá trị?

Nếu consumer không yêu cầu thứ tự cố định, một assertion cứng theo index có thể khiến test quá chặt. Ngược lại, nếu consumer xử lý phần tử đầu tiên như ưu tiên cao nhất, thứ tự là một cam kết quan trọng và nên có test bảo vệ.

## 10. Đọc matcher động: literal, regex, type và timestamp

Không phải giá trị nào của producer cũng cố định. Ví dụ ID được sinh mới hoặc thời điểm tạo đơn có thể thay đổi giữa các lần chạy.

Groovy DSL:

~~~groovy
response {
    status CREATED()
    headers {
        contentType(applicationJson())
    }
    body(
        orderId: 'ORD-123',
        status: 'CREATED',
        totalAmount: 120000,
        createdAt: '2026-11-24T08:00:00Z'
    )
    bodyMatchers {
        jsonPath('$.orderId', byRegex('ORD-[0-9]+'))
        jsonPath('$.totalAmount', byType())
        jsonPath('$.createdAt', byTimestamp())
    }
}
~~~

Khi đọc generated test, cần hiểu **giá trị mẫu trong `body` và matcher có thể đóng vai trò khác nhau**:

| Field | Giá trị mẫu | Assertion producer cần hiểu |
| --- | --- | --- |
| `orderId` | `ORD-123` | Khớp mẫu `ORD-[0-9]+`, không nhất thiết bằng `ORD-123` |
| `status` | `CREATED` | Bằng giá trị nghiệp vụ `CREATED` nếu không có matcher thay thế |
| `totalAmount` | `120000` | Đúng kiểu number khi dùng `byType()`; không đủ để chứng minh tính toán đúng |
| `createdAt` | Chuỗi timestamp mẫu | Giá trị có định dạng timestamp được matcher chấp nhận |

Các assertion thật có thể là `matches(...)`, `instanceOf(...)` hoặc helper JSON assertion; bạn phải **đọc logic**, không chỉ tìm chữ `equalTo`.

### 10.1. `byType()` không kiểm tra toàn bộ nghiệp vụ

Nếu `totalAmount` phải chính xác là số tiền được tính từ giỏ hàng, chỉ dùng `byType()` có thể cho qua `999999` vì nó vẫn là number. Cần giữ assertion giá trị, thêm matcher phù hợp, hoặc unit/domain test để bảo vệ công thức.

### 10.2. Matcher ở request và matcher ở response có vai trò khác

Đối với request:

~~~groovy
body(
    customerId: $(consumer(regex('CUS-[0-9]+')),
                  producer('CUS-7'))
)
~~~

Generated producer test **gửi `CUS-7`** vào hệ thống. Phía stub dùng matcher để nhận nhiều `customerId` hợp lệ.

Đối với response:

~~~groovy
body(
    orderId: $(consumer('ORD-123'),
               producer(regex('ORD-[0-9]+')))
)
~~~

Generated producer test kiểm tra ID theo regex, trong khi stub có thể trả giá trị mẫu `ORD-123`.

Không đảo hai chiều này khi điều tra sai lệch. `consumer(...)` và `producer(...)` được đọc theo **phía sử dụng giá trị ở vị trí request/response cụ thể**.

## 11. Phân biệt test generated và base class

Một generated test có thể chỉ chứa vài lời gọi HTTP và assertions. Nhưng môi trường test thường được thiết lập ở `ContractVerifierBase`.

Ví dụ khung minh họa với Spring MVC/MockMvc, JUnit 5:

~~~java
// Ví dụ base class theo dự án, cần package/import phù hợp
@WebMvcTest(OrderController.class)
abstract class ContractVerifierBase {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderQuery orderQuery;

    @BeforeEach
    void setUp() {
        given(orderQuery.findById("ORD-123"))
            .willReturn(new OrderView(
                "ORD-123", "CONFIRMED", 120000L, true
            ));

        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
~~~

Đây là **khung minh họa**, không phải đoạn Java đầy đủ có thể copy vào mọi dự án. Nó giả định ứng dụng có `OrderQuery`, `OrderView` và `OrderController` với phương thức phù hợp. `@MockitoBean` phù hợp với Spring Framework 6.2+ và bản Spring Boot tương ứng; dự án cũ có thể dùng `@MockBean`. Chọn dependency và annotation theo phiên bản dự án.

Vai trò của base class:

1. Nạp controller và cấu hình Spring MVC.
2. Đưa dữ liệu thử nghiệm vào dependency để endpoint có thể trả response.
3. Kết nối RestAssured MockMvc với `MockMvc`.
4. Thiết lập security/test context khi cần.
5. Bảo đảm mỗi generated test có môi trường tái lập.

Nếu test fail với `404` nhưng contract yêu cầu `200`, hãy kiểm tra **fixture dữ liệu**. Nếu test fail vì thiếu Bean, mock hoặc application context, hãy kiểm tra base class trước khi coi đó là API breaking change.

### 11.1. Base class không nên tự “giả” toàn bộ contract

Nếu base class mock luôn cả HTTP response JSON, test có thể xanh mà **không đi qua phần code producer cần được kiểm chứng**. Khi dùng `@WebMvcTest`, ta đang kiểm tra ranh giới web/controller và serialization nhưng có thể đã loại khỏi kiểm thử logic service.

Phạm vi này không nhất thiết sai. Điều quan trọng là **biết điều gì đã được mock** và thêm integration/domain tests nếu consumer thực sự phụ thuộc vào logic vượt ngoài lớp web.

## 12. Đọc generated test ở các chế độ HTTP khác nhau

Spring Cloud Contract hỗ trợ nhiều kiểu kiểm thử HTTP tùy phiên bản và stack ứng dụng. Cách viết request trong generated source có thể khác nhau, nhưng cấu trúc ý nghĩa vẫn tương tự.

| Chế độ/cách tiếp cận | Dấu hiệu khi đọc generated test | Ý nghĩa |
| --- | --- | --- |
| **MockMvc** | `RestAssuredMockMvc`, `MockMvc`, `MockMvcRequestSpecification` | Gọi Spring MVC mà không cần HTTP server thật trên một cổng |
| **HTTP client / server thực** | `RestAssured` và cổng/base URI được cấu hình | Gửi request HTTP tới ứng dụng đang chạy trong môi trường test |
| **Reactive/web client** | Các thành phần WebTestClient hoặc test mode tương ứng | Kiểm tra stack reactive theo cấu hình và phiên bản hỗ trợ |
| **Messaging** | Phương thức trigger, receive/send/message assertions | Kiểm tra payload/header/destination của thông điệp, không phải HTTP response |

Không đổi mode để làm test xanh khi producer sử dụng stack khác. Ví dụ `MockMvc` phù hợp với Spring MVC; một ứng dụng thuần WebFlux cần chế độ hoặc cách setup test tương ứng.

### 12.1. Base URI và cổng ở HTTP test

Nếu generated test gửi đến `http://localhost:<port>`, hãy kiểm tra cổng đó có được mở trong test context không. Test có thể thất bại vì **không kết nối được server** trước khi chạy bất kỳ JSON assertion nào. Đó là lỗi môi trường/khởi động chứ chưa phải mismatch với body của hợp đồng.

### 12.2. Đừng nhầm lỗi application context với assertion failure

| Dấu hiệu | Nơi cần xem trước |
| --- | --- |
| `ApplicationContext failed to load` | Base class, bean configuration, profiles, dependency versions |
| `Connection refused` | Server đã khởi động? Cổng/base URI đúng? |
| `expected status 200, was 404` | Request path, fixture, controller routing |
| `expected status 200, was 500` | Exception/log của producer, setup dữ liệu |
| `expected JSON field $.orderId` | Serialization, field naming, DTO/response mapper |
| `expected number, got string` | JSON type, matcher trong DSL |
| `No tests found` | Plugin generation, test source sets, JUnit engine, test filtering |

Đọc **dòng lỗi đầu tiên có ý nghĩa**, không chỉ nhìn chữ “BUILD FAILURE”.

## 13. Đọc generated test cho response lỗi

Một contract không tìm thấy tài nguyên:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_order_not_found')

    request {
        method GET()
        urlPath('/api/orders/ORD-404')
    }

    response {
        status NOT_FOUND()
        headers {
            contentType(applicationJson())
        }
        body(
            code: 'ORDER_NOT_FOUND'
        )
    }
}
~~~

Generated test có nhiệm vụ gọi `GET /api/orders/ORD-404` và kiểm tra:

- HTTP status phải là `404`.
- Content-Type phải theo hợp đồng.
- JSON field `code` phải là `ORDER_NOT_FOUND`.

**404 do không có route khác 404 do không có resource.** Nếu base class chạy một controller không đăng ký `/api/orders/{id}`, test có thể nhận `404` do routing. Khi body được kiểm tra, nó có thể phát hiện việc phản hồi không phải lỗi nghiệp vụ `ORDER_NOT_FOUND`. Đây là lý do contract nên ràng buộc **status và error body** mà consumer thật sự đọc, tránh pass nhầm khi chỉ kiểm tra status.

Tương tự, với request sai validation:

~~~groovy
request {
    method POST()
    urlPath('/api/orders')
    headers {
        contentType(applicationJson())
    }
    body(
        customerId: '',
        items: [[sku: 'BK-1', quantity: 1]]
    )
}

response {
    status BAD_REQUEST()
    headers {
        contentType(applicationJson())
    }
    body(
        code: 'VALIDATION_FAILED',
        errors: [
            [field: 'customerId', code: 'REQUIRED']
        ]
    )
}
~~~

Generated test phải gửi request **sai cụ thể** và kiểm tra `400` với error schema tương ứng. Nếu test thất bại, hãy xác nhận producer thực sự bật Bean Validation/exception handler và xử lý body đúng như API đã công bố.

## 14. Generated messaging tests khác HTTP tests như thế nào?

Spring Cloud Contract không chỉ kiểm tra HTTP. Với messaging, producer có thể phát sự kiện khi thao tác nghiệp vụ xảy ra.

Ví dụ contract:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('payment_authorized_event')
    description('Producer phát sự kiện khi thanh toán được xác nhận')
    label 'paymentAuthorized'

    input {
        triggeredBy('publishAuthorizedPayment()')
    }

    outputMessage {
        sentTo('payments.authorized')
        headers {
            header('contentType', 'application/json')
        }
        body(
            eventType: 'PaymentAuthorized',
            paymentId: 'PAY-123',
            amount: 120000
        )
    }
}
~~~

Trong generated messaging test, cấu trúc quan trọng thường là:

1. **Trigger:** Gọi `publishAuthorizedPayment()` hoặc kích hoạt đầu vào theo DSL.
2. **Quan sát thông điệp:** Dùng message verifier/binder/test infrastructure đọc output từ destination được khai báo.
3. **Assertion destination, headers, payload:** So sánh message thực với contract.
4. **Pass/fail:** Báo lỗi nếu producer không phát hoặc phát dữ liệu sai.

Ví dụ pseudocode mô tả ý tưởng:

~~~java
// PSEUDOCODE: không phải API chính thức dùng để compile
trigger("publishAuthorizedPayment()");
Message message = receiveFrom("payments.authorized");

assertMessageHeader(message, "contentType", "application/json");
assertJsonEquals(message.payload(), "$.eventType", "PaymentAuthorized");
assertJsonEquals(message.payload(), "$.paymentId", "PAY-123");
assertJsonEquals(message.payload(), "$.amount", 120000);
~~~

Phần `trigger` và `receiveFrom` chỉ là ký hiệu đọc hiểu. Generated code thật và base class phụ thuộc message verifier/binder cấu hình trong dự án.

### 14.1. Những điều messaging generated test không tự chứng minh

- Broker luôn giao hàng thành công trong mọi điều kiện mạng.
- Message không bị lặp hoặc luôn có thứ tự tuyệt đối.
- Consumer xử lý retry/idempotency đúng.
- Một event đủ bảo mật khi đi qua broker thật.

Các đặc tính này cần integration, resilience hoặc security tests phù hợp. Đừng nhìn một generated contract test cho payload rồi kết luận toàn bộ hệ thống messaging đã được kiểm chứng.

## 15. Generated tests có giống consumer tests dùng stub không?

Không. Cùng một contract thường tạo ra hai cách sử dụng khác nhau.

| Tiêu chí | Generated producer test | Consumer test với Stub Runner |
| --- | --- | --- |
| Đối tượng được thử | Code producer thật hoặc test context của producer | Code consumer gọi stub mô phỏng producer |
| Nguồn request | Giá trị **producer-side** của contract | Request do consumer code tạo |
| Nguồn response | Response thật do producer trả | Response mẫu/template từ stub |
| Cách xác minh | Assertion theo contract | Assertions do nhóm consumer viết |
| Phát hiện lỗi | Producer không đáp ứng cam kết | Consumer gọi sai hoặc xử lý sai cam kết |
| Giới hạn | Chỉ các contract được sinh và chạy | Chỉ những tình huống được stub và consumer test sử dụng |

Ví dụ contract request có `customerId` matcher:

~~~groovy
request {
    method POST()
    url '/api/echo'
    headers {
        contentType(applicationJson())
    }
    body(
        customerId: $(consumer(regex('CUS-[0-9]+')),
                      producer('CUS-7'))
    )
}

response {
    status OK()
    body(
        customerId: fromRequest().body('$.customerId')
    )
}
~~~

Generated producer test có thể gửi `CUS-7` và kiểm tra producer trả lại `CUS-7`. Stub được hỗ trợ response templating có thể khớp các mã `CUS-8`, `CUS-9` rồi phản ánh dữ liệu từ request runtime.

Vì vậy, **một generated producer test xanh với `CUS-7` không chứng minh producer phản ánh đúng mọi mã khách hàng**. Cần bổ sung kịch bản khác nếu API cam kết hành vi tổng quát này.

## 16. Quy trình đọc một lỗi generated test từ đầu tới cuối

Giả sử CI báo:

~~~text
Expected JSON path $.totalAmount to satisfy matcher
Actual value: "120000"
Contract test: get_confirmed_order
~~~

Đây là thông báo minh họa, không phải nguyên văn bắt buộc của framework. Quy trình điều tra:

### Bước 1 — Xác định contract nguồn

Tìm tệp DSL chứa `name('get_confirmed_order')` hoặc request `/api/orders/ORD-123`. Xem field `totalAmount` được khai báo như thế nào:

~~~groovy
body(
    totalAmount: 120000
)
~~~

Nếu đây là number, producer không được tự đổi nó thành String khi consumer còn phụ thuộc kiểu number.

### Bước 2 — Mở generated test

Xác định:

- Request method/path và body đầu vào.
- Assertion nào đang kiểm tra `totalAmount`.
- Có matcher `byType()`, `byEquality()` hay regex không.
- Test kế thừa base class nào.

### Bước 3 — Kiểm tra response thực

Ví dụ producer trả:

~~~json
{
  "orderId": "ORD-123",
  "status": "CONFIRMED",
  "totalAmount": "120000"
}
~~~

Trường `totalAmount` đã trở thành String. Nếu DSL yêu cầu Number, đây có thể là thay đổi không tương thích.

### Bước 4 — Kiểm tra producer code và fixture

Các nguyên nhân có thể gồm:

- DTO đổi `long totalAmount` thành `String totalAmount`.
- Serialization layer bọc số trong dấu nháy.
- Mock trong base class trả đối tượng có kiểu không đúng.
- Contract mô tả sai so với thỏa thuận thực tế.

### Bước 5 — Chọn cách sửa có chủ đích

- Nếu API đã cam kết number: **sửa producer** để tiếp tục trả Number.
- Nếu hợp đồng sai từ đầu: trao đổi với consumer rồi **sửa contract có kiểm soát**.
- Nếu producer cần đổi schema: xây dựng migration/phiên bản API mới và giữ khả năng tương thích trong giai đoạn chuyển đổi.

**Không sửa Java generated test trực tiếp** vì code sẽ bị ghi đè khi sinh lại. Không chuyển matcher thành “bất kỳ chuỗi nào” chỉ để test xanh nếu việc đó che đi breaking change.

### Bước 6 — Chạy lại producer verification và consumer tests

Sau khi sửa, chạy build sinh + chạy generated tests; khi đạt, kiểm thử consumer với stub đúng version để xác nhận phía sử dụng hợp đồng vẫn hoạt động.

## 17. Các mẫu thất bại thường gặp và ý nghĩa

| Triệu chứng | Điều cần xem trước | Rủi ro nếu sửa sai |
| --- | --- | --- |
| Không tìm thấy generated test | Vị trí DSL, plugin, task, tên class, JUnit engine | Build xanh nhưng không kiểm tra contract nào |
| Test không compile vì base class | Package, `baseClassForTests`, dependencies, import | Đổ lỗi cho API trong khi cấu hình test sai |
| Test không chạy, báo `No tests found` | Test runner, task includes/excludes | Phát hành mà không có producer verification |
| Connection refused | HTTP test mode, server port, startup | Nhầm lỗi mạng thành lỗi JSON |
| `200` nhưng thiếu field | Response DTO/serializer và contract | Consumer deserialize thất bại |
| Sai số với kiểu String | JSON type và matcher | Che breaking change khi nới matcher bừa |
| `404` thay `200` | Path hoặc dữ liệu fixture | Kết luận nhầm producer phá vỡ API |
| `403` hoặc `401` ngoài dự kiến | Security setup và auth requirements | Tắt security filter để test xanh giả |
| Header sai | Filter/interceptor/content negotiation | Bỏ sót media type mà consumer cần |
| Timestamp khác literal | Matcher giá trị động | Test thất bại giả vì thời điểm hợp lệ thay đổi |
| Array đổi thứ tự | Contract có cam kết thứ tự không? | Over-specify response hoặc bỏ lọt lỗi hiển thị |
| Message không thấy | Trigger, destination, binder và message verifier | Nhầm messaging setup với vi phạm payload |
| Stub chạy nhưng consumer thất bại | Request matcher, stub version, response template | Đổ lỗi cho producer dù client gọi sai |

Trong một lỗi có nhiều assertion fail cùng lúc, bắt đầu từ **lời gọi** và **status** trước, rồi mới đi sâu vào từng field. Ví dụ nếu request trỏ nhầm path và nhận HTML 404, nhiều JSONPath assertion sẽ cùng thất bại do body không phải JSON; sửa JSONPath không giải quyết nguyên nhân gốc.

## 18. Kiểm tra số lượng generated tests trước khi tin vào CI

Một trong những sai lầm nguy hiểm nhất là cho rằng `BUILD SUCCESS` đồng nghĩa mọi hợp đồng đã được kiểm chứng.

Cần phân biệt các trường hợp:

1. **Không có contract nguồn:** Plugin có thể không sinh test nào.
2. **Có contract nhưng sai thư mục:** Plugin không đọc được dữ liệu.
3. **Test được sinh nhưng không được compile:** Cấu hình test source sets thiếu.
4. **Test compile nhưng bị skip/filter:** Build vẫn có thể xanh.
5. **Test được chạy nhưng matcher quá lỏng:** Sai lệch quan trọng không bị phát hiện.
6. **Producer tests đạt nhưng stub chưa phát hành đúng phiên bản:** Consumer CI có thể vẫn chạy artifact cũ.

### 18.1. Những thông tin nên thu thập trong một pull request

- Các file Groovy/YAML contract được thêm hoặc sửa.
- Generated test cho tương tác đó có tồn tại không.
- Test runner báo đã thực thi bao nhiêu tests, bao nhiêu failures.
- Những thay đổi về method/path/status/header/body có được bắt bởi assertion không.
- Nếu có sửa contract, lý do thay đổi và consumer nào bị ảnh hưởng.
- Stub artifact phiên bản nào sẽ được phát hành và consumer test sẽ dùng.

Đừng commit generated Java test để thay thế tệp contract nguồn, trừ khi quy trình dự án thật có yêu cầu đặc biệt. Thông thường **DSL là nguồn chân lý**, mã generated là sản phẩm build.

### 18.2. Ví dụ lệnh build

Với Maven đã cấu hình Spring Cloud Contract Verifier:

~~~bash
./mvnw -B clean verify
~~~

Với Gradle đã cấu hình plugin và task test phù hợp:

~~~bash
./gradlew clean build
~~~

Bài học chỉ trình bày lệnh minh họa; **không cần chạy build để đọc khái niệm**. Trong dự án thực tế, phải xác minh plugin, dependency, base class và đường dẫn contract đã được cấu hình trước khi dựa vào kết quả.

## 19. Bài thực hành: đọc generated test và phát hiện thay đổi không tương thích

Giả sử `Catalog Service` cung cấp:

~~~http
GET /api/products/P-100 HTTP/1.1
Accept: application/json
~~~

Phản hồi:

~~~json
{
  "productId": "P-100",
  "name": "Wireless Mouse",
  "price": 350000,
  "available": true,
  "tags": ["wireless", "mouse"]
}
~~~

### 19.1. Contract nguồn Groovy

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_product_detail')

    request {
        method GET()
        urlPath('/api/products/P-100')
        headers {
            accept(applicationJson())
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            productId: 'P-100',
            name: 'Wireless Mouse',
            price: 350000,
            available: true,
            tags: ['wireless', 'mouse']
        )
        bodyMatchers {
            jsonPath('$.productId', byRegex('P-[0-9]+'))
            jsonPath('$.price', byType())
        }
    }
}
~~~

### 19.2. Nhiệm vụ A — Đọc phần request

Sau khi cấu hình plugin và sinh test trong **dự án thực hành**:

1. Mở generated test tương ứng với `get_product_detail`.
2. Chỉ ra dòng nào cho biết HTTP method là `GET`.
3. Chỉ ra dòng nào gửi đến `/api/products/P-100`.
4. Xác định nơi header `Accept: application/json` được gắn vào request.
5. Xác định test kế thừa base class nào và fixture sản phẩm `P-100` nằm ở đâu.

### 19.3. Nhiệm vụ B — Đọc assertions

Tìm và giải thích:

- Assertion HTTP `200`.
- Assertion `Content-Type`.
- Assertion `name: Wireless Mouse`.
- Matcher cho `productId`; vì sao nó khác equality `P-100`?
- Matcher `price`; vì sao đúng kiểu number chưa đủ bảo đảm giá đúng `350000`?
- Các trường `available` và `tags` được kiểm tra ra sao trong generated test thực tế?

### 19.4. Nhiệm vụ C — Cố ý làm test thất bại

Thử từng thay đổi ở producer:

| Thay đổi | Điều dự kiến |
| --- | --- |
| Đổi HTTP status từ `200` sang `201` | Status assertion thất bại |
| Đổi `name` thành `Computer Mouse` | Literal equality thất bại nếu ràng buộc đúng |
| Đổi `price` từ number sang String | Type matcher thất bại |
| Đổi `productId` thành `P-ABC` | Regex `P-[0-9]+` không khớp |
| Đổi `price` từ `350000` sang `999999` | Chỉ `byType()` có thể không phát hiện vì vẫn là number |
| Xóa trường `available` | Contract có thể phát hiện thiếu field nếu assertion được sinh cho trường đó |
| Đảo thứ tự `tags` | Kết quả phụ thuộc assertion về mảng/thứ tự được tạo |

**Mục tiêu của bài tập không chỉ là thấy test đỏ.** Hãy ghi rõ **dòng assertion** nào thất bại và nguyên nhân nghiệp vụ/tương thích có thật hay không.

### 19.5. Nhiệm vụ D — Đọc YAML contract tương đương

~~~yaml
name: get_product_detail
request:
  method: GET
  urlPath: /api/products/P-100
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    productId: P-100
    name: Wireless Mouse
    price: 350000
    available: true
    tags:
      - wireless
      - mouse
  matchers:
    body:
      - path: $.productId
        type: by_regex
        value: 'P-[0-9]+'
      - path: $.price
        type: by_type
~~~

Giải thích vì sao Groovy và YAML có cú pháp khác nhau nhưng **lời gọi và assertions có cùng ý nghĩa** khi được plugin chuyển đổi. Khi thực hành, chỉ kích hoạt **một bản contract cho cùng một tương tác** để tránh tạo các định nghĩa trùng lặp không mong muốn.

### 19.6. Nhiệm vụ E — Phân biệt một lỗi setup với breaking change

Hai tình huống giả định:

- **Tình huống 1:** Test trả `404` vì base class không mock hoặc không tạo sản phẩm `P-100`.
- **Tình huống 2:** Test trả `200` nhưng `price` là String `"350000"` do DTO/serializer đổi.

Với tình huống 1, kiểm tra fixture/test setup và producer routing trước. Với tình huống 2, đối chiếu schema consumer rồi sửa producer hoặc thương lượng hợp đồng. Không sửa test generated trực tiếp trong cả hai trường hợp.

## 20. Checklist đọc một generated producer contract test

- [ ] Tìm được tệp DSL nguồn và generated test tương ứng.
- [ ] Biết test sử dụng JUnit/test framework và HTTP/messaging mode nào.
- [ ] Hiểu generated test kế thừa base class nào và base class thiết lập điều gì.
- [ ] Nhận diện được HTTP method, path, headers, query, body từ request DSL.
- [ ] Xác định chính xác lời gọi gửi request tới producer.
- [ ] Tách bạch status assertion, header assertion và body assertion.
- [ ] Hiểu JSONPath trỏ đến field/cấp lồng nhau nào.
- [ ] Phân biệt equality, regex, type và timestamp matcher.
- [ ] Biết giá trị nào là producer-side test input và giá trị nào dành cho consumer stub.
- [ ] Kiểm tra request/response có đúng kiểu JSON và media type không.
- [ ] Không nhầm dữ liệu setup sai với breaking change của producer.
- [ ] Không tự sửa mã generated test; sửa DSL, setup hoặc producer theo đúng nguyên nhân.
- [ ] CI thực sự sinh **và thực thi** generated tests, không báo xanh khi 0 tests.
- [ ] Sau khi producer verification đạt, consumer vẫn dùng stub artifact đúng phiên bản qua Stub Runner.
- [ ] Những quy tắc nghiệp vụ, security, broker delivery và integration nằm ngoài contract test có kiểm thử bổ sung.

## 21. Tài liệu tham khảo

- [Spring Cloud Contract — Reference Documentation](https://docs.spring.io/spring-cloud-contract/reference/): giới thiệu Verifier, contract DSL, plugin và stub.
- [Spring Cloud Contract — HTTP Contracts](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/http.html): thành phần request và response được ánh xạ thành kiểm chứng.
- [Spring Cloud Contract — Dynamic Properties](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/dsl-dynamic-properties.html): giá trị consumer/producer, `bodyMatchers` và JSONPath.
- [Spring Cloud Contract — Developing Your First Application](https://docs.spring.io/spring-cloud-contract/reference/getting-started/first-application.html): ví dụ xây producer, sinh và chạy generated tests.

**Ghi nhớ:** Mã kiểm thử do **Contract Verifier** sinh là bản dịch **có thể thực thi** của contract Groovy/YAML: phần request tạo **lời gọi**, phần response tạo **assertions**, còn base class dựng môi trường cho producer. Đọc được ba phần này giúp bạn xác định lỗi setup, lỗi matcher và thay đổi API không tương thích; từ đó chỉ phát hành stub khi producer đã đáp ứng những hợp đồng cần thiết.

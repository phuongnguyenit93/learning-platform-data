# Stub HTTP được sinh từ hợp đồng như thế nào

## 1. Bài toán: consumer cần API trước khi producer sẵn sàng

Trong một hệ thống nhiều dịch vụ, **Checkout Service** cần gọi **Inventory Service** để biết sản phẩm có còn hàng. Nếu mỗi lần kiểm thử Checkout đều phải khởi động Inventory, kết nối database và dựng đầy đủ môi trường, vòng phản hồi sẽ chậm, dễ lỗi và phụ thuộc lịch triển khai của đội khác.

**Spring Cloud Contract (SCC)** giải quyết một phần vấn đề này bằng cách biến **hợp đồng giao tiếp** thành các tài sản kiểm thử:

- **Generated producer tests:** kiểm tra implementation Inventory Service thực sự trả đúng status, headers và body đã thỏa thuận.
- **HTTP stubs:** mô phỏng những hành vi HTTP đã mô tả để Checkout Service có thể kiểm thử client khi Inventory Service không chạy.

Trong hệ sinh thái SCC, HTTP stub thông thường được biểu diễn bằng **WireMock mappings** và các tài nguyên response liên quan. Chúng có thể được đóng gói vào một artifact có classifier **`stubs`**, sau đó dùng **Stub Runner** để tải và khởi động stub trong bộ test của consumer.

Bài này thuộc chương **Sinh và đóng gói stub**, tập trung trả lời chính xác câu hỏi: **“Stub HTTP được sinh từ hợp đồng như thế nào?”**. Ta sẽ theo dõi từ Groovy/YAML DSL tới mapping, stub JAR, Stub Runner, producer/consumer tests và cổng CI.

### Bạn sẽ học được

1. Phân biệt **contract source**, **generated producer test**, **WireMock stub mapping** và **stubs JAR**.
2. Giải thích trường nào của contract tạo ra điều kiện **request matching**, trường nào trở thành **stubbed response**.
3. Nhìn vào một ví dụ Groovy/YAML và hiểu cấu trúc WireMock JSON tương ứng.
4. Biết cách kiểm tra headers, query, JSON body matcher, response status và body file.
5. Hiểu **consumer/producer values**, dữ liệu động và giới hạn của việc sinh stub.
6. Đóng gói, định danh, phát hành và tải stub đúng phiên bản với Maven/Gradle và Stub Runner.
7. Chẩn đoán những lỗi “stub không match”, “stub cũ”, “mapping trùng” và pipeline xanh giả.
8. Đưa việc sinh–kiểm chứng–phát hành stub vào CI để phát hiện thay đổi API không tương thích.

## 2. Một contract, hai hướng sinh khác nhau

~~~mermaid
flowchart TD
    A["Contract Groovy DSL / YAML DSL"] --> B["Spring Cloud Contract plugin"]
    B --> C["Generated producer tests"]
    B --> D["Generated HTTP stub mappings"]
    C --> E["Chạy với producer application thật"]
    E --> F{"Producer đáp ứng hợp đồng?"}
    F -- "Không" --> X["Chặn thay đổi"]
    F -- "Có" --> G["Cho phép đóng gói/publish stub ứng viên"]
    D --> H["WireMock mappings + body files"]
    H --> I["JAR classifier stubs"]
    I --> J["Repository artifact"]
    J --> K["Stub Runner trong consumer tests"]
    K --> L["HTTP client thật của consumer"]
    L --> M{"Consumer xử lý đúng?"}
    M -- "Không" --> X
    M -- "Có" --> N["Qua cổng tương thích"]
~~~

Hai nhánh cùng xuất phát từ hợp đồng, nhưng mục tiêu trái chiều:

| Nhánh | Ai thực thi? | Điều được kiểm tra |
|---|---|---|
| **Producer tests** | Test framework của producer, với code producer thật | Producer hiện tại **tuân thủ** contract |
| **HTTP stubs** | WireMock do Stub Runner khởi động cho consumer | Consumer **gửi request đúng** và **xử lý response mẫu đúng** |
| **CI kết hợp** | Pipeline các dịch vụ | Thay đổi ở producer không phá các consumer đang hỗ trợ |

**Stub không phải bản sao chạy thật của producer.** Nó không gọi InventoryController, không đọc database Inventory và không tự áp dụng toàn bộ business logic. Stub chỉ mô phỏng **những tình huống đã được mô tả**, bằng matching request và phát response được cấu hình.

Producer tests cũng không thể bị bỏ qua: nếu chỉ sinh mapping rồi cho consumer test xanh, cả contract lẫn stub có thể đúng với nhau trong khi ứng dụng producer thật đã thay đổi và trả dữ liệu khác.

## 3. Ví dụ xuyên suốt: kiểm tra tồn kho qua HTTP GET

Giả sử Checkout gọi:

~~~http
GET /api/inventory/SKU-123 HTTP/1.1
Host: inventory.example.test
Accept: application/json
X-Client-Id: checkout-service
~~~

Inventory Service cam kết:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sku": "SKU-123",
  "available": true,
  "quantity": 12
}
~~~

Khi tồn kho của sản phẩm đó chưa được cung cấp, API có thể trả `404` theo một contract riêng. Trong ví dụ đầu tiên, ta chỉ xét **một tình huống thành công cố định** để dễ nhìn việc sinh stub.

Hợp đồng có những thành phần mà công cụ có thể biến thành hành vi WireMock:

| Contract | Bản đồ ý nghĩa trong stub |
|---|---|
| `request.method: GET` | Chỉ nhận HTTP GET |
| `request.url: /api/inventory/SKU-123` | Chỉ nhận URL/path đúng điều kiện |
| Request header `Accept: application/json` | Kiểm tra header cần thiết nếu mapping được sinh với ràng buộc đó |
| Request header `X-Client-Id` | Phân biệt caller nếu đây là phần contract |
| `response.status: 200` | Stub trả HTTP 200 |
| Response header `Content-Type: application/json` | Stub trả header JSON |
| Response body chứa `sku/available/quantity` | Stub trả body JSON mẫu |

Nếu client thay GET bằng POST, gọi URL khác hoặc gửi header mà contract yêu cầu không đúng, WireMock có thể không tìm thấy mapping tương ứng. **Điều kiện thực sự phải được xác nhận trên mapping JSON đã sinh**, không chỉ dựa vào cách đọc DSL.

## 4. Viết hợp đồng bằng Groovy DSL

Tệp minh họa phía producer:

~~~text
src/test/resources/contracts/inventory/get-inventory.groovy
~~~

Nội dung:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Checkout có thể xem tồn kho sản phẩm SKU-123'

    request {
        method GET()
        url '/api/inventory/SKU-123'

        headers {
            header('Accept', 'application/json')
            header('X-Client-Id', 'checkout-service')
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

Cách đọc:

1. `Contract.make` tạo một mô tả contract.
2. `request.method` và `url` là phần đầu vào để sinh **request trong producer test** và **request matcher trong stub**.
3. `request.headers` quy định những header consumer được kỳ vọng gửi.
4. `response.status/headers/body` là phần producer phải đáp ứng và stub sẽ mô phỏng.
5. Giá trị `available: true` trong Groovy map là boolean; `quantity: 12` là số, không phải string.
6. SCC dùng hợp đồng để sinh test và mapping theo các task/goal của plugin được cấu hình.

**Quan trọng:** tệp Groovy không phải một script WireMock trực tiếp. SCC trước hết xử lý DSL thành mô hình hợp đồng, rồi một cơ chế sinh code/mapping mới chuyển mô hình đó thành các đầu ra phù hợp.

## 5. Cách viết tương đương bằng YAML DSL

Nếu dự án dùng YAML, có thể thay tệp Groovy bằng `get-inventory.yml`:

~~~yaml
description: Checkout có thể xem tồn kho sản phẩm SKU-123
name: get_inventory_sku123

request:
  method: GET
  url: /api/inventory/SKU-123
  headers:
    Accept: application/json
    X-Client-Id: checkout-service

response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    available: true
    quantity: 12
~~~

| Ý tưởng | Groovy | YAML |
|---|---|---|
| Method | `method GET()` | `method: GET` |
| URL | `url '/api/inventory/SKU-123'` | `url: /api/inventory/SKU-123` |
| Header request | `header('Accept', 'application/json')` | `Accept: application/json` |
| HTTP status | `status OK()` | `status: 200` |
| Response JSON | `body(sku: ..., available: ..., quantity: ...)` | `body:` với các thuộc tính |
| Tên contract tùy chọn | Tên file/metadata DSL | `name: get_inventory_sku123` |

Đây là **hai cách biểu diễn cùng một hợp đồng**, không cần đồng thời tạo cả hai trong một module nếu điều đó chỉ sinh hai test/mapping trùng lặp. YAML có quy tắc suy kiểu: `true` là boolean và `12` là số; nếu viết `'true'` hoặc `'12'` thì chúng trở thành chuỗi, có thể khiến stub trả schema sai.

## 6. Quá trình sinh stub diễn ra qua những bước nào?

Tùy Maven/Gradle plugin và phiên bản SCC, tên task/goal có thể khác nhau, nhưng về mặt logic quá trình gồm:

~~~text
1. Tìm hợp đồng trong thư mục nguồn đã cấu hình
   ↓
2. Parse Groovy DSL hoặc YAML DSL
   ↓
3. Kiểm tra cấu trúc và xây mô hình contract
   ↓
4. Xác định request matcher của stub
   ↓
5. Tạo response cố định hoặc có dữ liệu động theo contract
   ↓
6. Sinh WireMock JSON mappings và tài nguyên body (nếu cần)
   ↓
7. Tập hợp mappings/tài nguyên thành stubs JAR
   ↓
8. Install/publish artifact để consumer tải
~~~

Những bước cần hiểu rõ:

- **Discovery:** plugin phải quét đúng đường dẫn và extension; nếu không có contract nào được phát hiện, có thể không có mapping nào.
- **Parsing:** một YAML parse được vẫn có thể dùng key không thuộc schema SCC; Groovy có thể lỗi khi đánh giá DSL.
- **Mapping:** điều kiện request có thể là equality, URL pattern, JSON body pattern, headers hoặc query parameters tùy contract.
- **Response:** có thể là literal body, JSON, status, headers, tài nguyên file hoặc một dạng templating được công cụ hỗ trợ.
- **Packaging:** mapping đúng chỉ có ích cho consumer khi được đóng gói đúng cấu trúc và phân phối đúng phiên bản.

**Tên file mapping và cách sinh JSON chi tiết là đầu ra của công cụ**, không nên viết code consumer phụ thuộc vào tên file ngẫu nhiên do plugin tạo. Consumer sử dụng **HTTP hành vi** và tọa độ stub, không gọi trực tiếp “mapping số 3”.

## 7. Hình dạng một WireMock stub mapping

Giả sử contract GET cố định ở phần trước được sinh thành một mapping có cấu trúc gần như sau:

~~~json
{
  "request": {
    "method": "GET",
    "url": "/api/inventory/SKU-123",
    "headers": {
      "Accept": {
        "equalTo": "application/json"
      },
      "X-Client-Id": {
        "equalTo": "checkout-service"
      }
    }
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "sku": "SKU-123",
      "available": true,
      "quantity": 12
    }
  }
}
~~~

Đây là **mapping minh họa có cú pháp WireMock**, không phải cam kết rằng SCC sẽ sinh **chính xác từng trường JSON và định dạng body** như vậy. Tùy phiên bản, response có thể được thể hiện bằng `body` thay cho `jsonBody`, mapping có thể có `id`/`name`/`priority`, và header/body matcher có thể khác.

Đọc mapping theo hai nửa:

- **`request`**: WireMock dùng các predicate để quyết định request incoming có khớp không.
- **`response`**: nếu khớp, WireMock trả status/headers/body đã định nghĩa.

Khi consumer chạy, **không có truy vấn vào InventoryService thật**. WireMock chỉ tra các mapping đã nạp rồi trả dữ liệu tương ứng.

### Minh họa request không match

~~~http
GET /api/inventory/SKU-123 HTTP/1.1
Accept: text/plain
X-Client-Id: checkout-service
~~~

Nếu mapping yêu cầu `Accept: application/json` chính xác, request trên **không khớp**. Tương tự, client quên `X-Client-Id` có thể nhận phản hồi unmatched của WireMock.

Một phản hồi HTTP 404 từ stub khi mapping không match **không nhất thiết là lỗi nghiệp vụ “SKU không tồn tại”**. Cần phân biệt “WireMock không có stub phù hợp” với “stub đã match và chủ động trả response 404”. Đó là khác biệt rất quan trọng khi chẩn đoán consumer test.

## 8. Request matcher được sinh từ phần nào?

Các trường trong `request` của contract trở thành **điều kiện khớp**. Với HTTP, các nhóm phổ biến gồm:

| Thành phần | Ví dụ contract | Ý tưởng trong mapping |
|---|---|---|
| Method | GET/POST/PUT/DELETE | `request.method` |
| URL chính xác | `/api/inventory/SKU-123` | `url` hoặc cơ chế exact URL tương ứng |
| URL path | `/api/orders` | Match path tách khỏi query khi contract dùng `urlPath` |
| Header | `Accept: application/json` | `headers.<name>.equalTo` hoặc matcher khác |
| Query parameter | `page=2` | `queryParameters.page` với equality/regex |
| JSON body | `{"sku":"SKU-123"}` | `bodyPatterns`, chẳng hạn JSON equality/JSONPath |
| Raw body | `name=Minh+Anh` | Matcher theo nội dung text/form |
| Request cookies | Cookie phiên hoặc tùy chọn API | Điều kiện cookie nếu version DSL/mapping hỗ trợ |
| Metadata phục vụ routing | Các field riêng của contract | Phụ thuộc cơ chế DSL/adapter, không tự mặc định là request matcher |

Một hợp đồng không khai báo header `Authorization` không có nghĩa stub sẽ tự kiểm tra xác thực. Stub cũng không thực thi bộ lọc security thật, trừ khi có test/hạ tầng khác được gắn vào.

**Quy tắc kiểm chứng:** nếu muốn chặn một dạng request không hợp lệ ở consumer test, phải biết mapping được sinh có **điều kiện tương ứng**, hoặc bổ sung test validation/integration riêng. Không suy đoán từ tên trường trong payload.

## 9. Phân biệt URL chính xác và URL path kèm query

Ví dụ các request:

~~~http
GET /api/items?category=books&page=2 HTTP/1.1
~~~

~~~http
GET /api/items?page=2&category=books HTTP/1.1
~~~

Về ý nghĩa query parameters, hai request có thể tương đương. Nếu contract sử dụng **URL literal gồm cả query**, stub có thể match chặt hơn dự kiến và phụ thuộc thứ tự biểu diễn. Khi API có query parameters thực sự, ưu tiên sử dụng cấu trúc DSL cho **`urlPath` + `queryParameters`** theo cú pháp/version tương ứng.

Ý tưởng mapping WireMock:

~~~json
{
  "request": {
    "method": "GET",
    "urlPath": "/api/items",
    "queryParameters": {
      "category": {"equalTo": "books"},
      "page": {"equalTo": "2"}
    }
  },
  "response": {
    "status": 200,
    "jsonBody": {"items": []}
  }
}
~~~

Tùy plugin, mapping có thể có predicate bổ sung. Tên query parameter và giá trị **đều cần được so khớp** nếu contract bảo vệ chúng.

Một sai lầm hay gặp: đặt form POST vào `queryParameters`, trong khi producer thực tế đọc body `application/x-www-form-urlencoded`. Stub được sinh khi đó sẽ match request khác với request consumer thật gửi.

## 10. JSON request body và matcher linh hoạt

Một API POST tạo yêu cầu giữ hàng:

~~~http
POST /api/reservations HTTP/1.1
Content-Type: application/json

{"sku":"SKU-123","quantity":2}
~~~

Contract Groovy với body cố định:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Tạo phiếu giữ hàng với SKU-123'

    request {
        method POST()
        url '/api/reservations'
        headers {
            contentType(applicationJson())
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

Trong stub mapping, SCC có thể sinh **`bodyPatterns`** với kiểu so khớp JSON, ví dụ gần tương đương:

~~~json
{
  "request": {
    "method": "POST",
    "url": "/api/reservations",
    "headers": {
      "Content-Type": {
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

Đây cũng là **mapping khái niệm**, không phải bản chép chính xác output của plugin. Kiểu `equalToJson` có hành vi riêng về khoảng trắng, thứ tự key, trường thừa và tùy chọn JSON equality; cần **mở mapping thật** và chạy test âm tính nếu việc từ chối extra fields là quan trọng.

### Khi body chứa dữ liệu động

Ví dụ `quantity` cố định nhưng SKU được phép theo một mẫu. Trong Groovy DSL, có thể dùng matcher:

~~~groovy
bodyMatchers {
    jsonPath('$.sku', byRegex('SKU-[0-9]+'))
}
~~~

Với matcher request, generator có thể tạo pattern JSONPath/regex hoặc các predicate WireMock phù hợp theo phiên bản. **Mẫu body cụ thể** vẫn cần được cung cấp để generated producer test có thể gửi request hợp lệ.

Khi viết YAML DSL, cấu trúc matcher thường ở `request.matchers.body`:

~~~yaml
request:
  method: POST
  url: /api/reservations
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    quantity: 2
  matchers:
    body:
      - path: $.sku
        type: by_regex
        value: 'SKU-[0-9]+'
~~~

Ví dụ này chỉ minh họa **request matcher**, chưa phải contract YAML hoàn chỉnh vì chưa có phần `response`. Khi áp dụng phải bổ sung response và xem các mapping/generator assertions thực tế.

## 11. Phân biệt giá trị phía consumer và producer

Spring Cloud Contract có cơ chế mô tả **giá trị khác nhau cho hai phía** khi một contract cần matcher linh hoạt nhưng generated test vẫn cần dữ liệu cụ thể.

Một mẫu trong Groovy DSL:

~~~groovy
body([
    sku: value(
        consumer(regex('SKU-[0-9]+')),
        producer('SKU-123')
    ),
    quantity: 2
])
~~~

Ở **request body**:

- **Giá trị phía consumer** mô tả điều kiện request mà **stub** phải chấp nhận, ở đây là SKU theo regex.
- **Giá trị phía producer** là ví dụ dữ liệu mà **generated producer test** gửi để kiểm tra implementation thật.

Ở **response body**, chiều sử dụng cần được hiểu theo phía nhìn nhận: stub phải cung cấp dữ liệu **consumer có thể nhận**, còn producer test kiểm tra phản hồi thật theo điều kiện phía **producer**. Không hoán đổi tùy tiện `consumer(...)`/`producer(...)` vì có thể tạo test hoặc stub không như mong đợi.

### Hai nguy cơ thường gặp

1. Matcher request **quá rộng**: regex `.*` làm stub chấp nhận cả SKU rỗng, sai kiểu hoặc đường dẫn không có quyền truy cập.
2. Giá trị response mẫu **không hợp lệ**: consumer test xanh với response hardcoded không phù hợp schema hoặc có giá trị lỗi nhưng chưa được producer test bảo vệ.

Khi có dữ liệu động như ID, timestamp hoặc số ngẫu nhiên, trước hết nên chọn **mẫu cụ thể hợp lệ cho stub** và **matcher đủ chặt cho producer**. Không cần biến mọi field thành regex.

## 12. Response mà stub trả được sinh như thế nào?

Phần `response` trong contract quyết định hành vi sau khi request match:

~~~yaml
response:
  status: 201
  headers:
    Content-Type: application/json
    Location: /api/reservations/R-1001
  body:
    reservationId: R-1001
    status: RESERVED
~~~

Từ đó stub có thể trả:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/reservations/R-1001

{"reservationId":"R-1001","status":"RESERVED"}
~~~

Trong quá trình sinh, SCC chuyển mô tả body thành dữ liệu mà WireMock có thể trả. **JSON key, kiểu dữ liệu, status và headers** cần được bảo toàn theo contract. Vì thế:

- `status: 201` khác `status: 200`; một consumer kiểm tra Location hoặc thao tác theo status sẽ nhận kết quả khác.
- `status: RESERVED` là chuỗi nghiệp vụ, không phải HTTP status.
- `Location` có thể là một phần hợp đồng: nếu consumer đọc nó, cần được test.
- Body có thể được lưu trực tiếp trong mapping hoặc tham chiếu tài nguyên file.
- Response động theo request có thể cần cơ chế dynamic property hoặc templating hỗ trợ bởi phiên bản SCC/WireMock; **không mặc định** mọi dấu `$`/placeholder trong body sẽ được render.

Stub **không suy luận** response từ database của producer. Chỉ khi contract định nghĩa nhiều tình huống hoặc cơ chế biến đổi hợp lệ, stub mới có hành vi tương ứng.

## 13. Stub trả mã lỗi cũng đến từ contract

Một endpoint có nhiều tình huống nên có **nhiều contract rõ ràng**. Ví dụ GET cho SKU không tồn tại:

~~~yaml
description: Báo không có sản phẩm SKU-404
name: inventory_missing

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
    message: SKU was not found
~~~

Stub mapping tương ứng có thể trả **HTTP 404 có mã lỗi `SKU_NOT_FOUND`** nếu request khớp.

Điều này khác với **WireMock unmatched request**, thường cũng xuất hiện một dạng 404 nhưng **không có response body nghiệp vụ đã cam kết**. Khi test consumer bị 404, cần kiểm tra:

1. Request có match mapping `inventory_missing` hay không?
2. Có mapping nào yêu cầu header, URL hoặc body khác không?
3. Response có body `code: SKU_NOT_FOUND` và header đúng như contract không?
4. Có đang gọi nhầm port WireMock khác không?

Nếu consumer test cần phân biệt “sản phẩm không có” và “không có mapping”, phải kiểm tra **schema lỗi**, không chỉ HTTP status.

## 14. Body file, payload lớn và tài nguyên ngoài

Khi response JSON rất dài, chứa text nhiều dòng hoặc body nhị phân, contract có thể tham chiếu **file tài nguyên** thay vì nhúng toàn bộ body.

Tùy DSL/version, những cơ chế như `bodyFromFile` (YAML) hoặc `body(file(...))` (Groovy) hỗ trợ lấy dữ liệu từ file theo đường dẫn tài nguyên đã định.

Ví dụ ý tưởng YAML:

~~~yaml
request:
  method: GET
  url: /api/reports/REPORT-123
response:
  status: 200
  headers:
    Content-Type: application/json
  bodyFromFile: report-123.json
~~~

Nếu file `report-123.json` tồn tại đúng nơi được plugin hỗ trợ, generator có thể dùng nội dung nó để sinh test/stub. WireMock có thể lưu dữ liệu trả về trong **response file**, mapping dẫn đến bằng thuộc tính như `bodyFileName`:

~~~json
{
  "request": {
    "method": "GET",
    "url": "/api/reports/REPORT-123"
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json"
    },
    "bodyFileName": "report-123.json"
  }
}
~~~

**Lưu ý:** đây là mapping minh họa. SCC có thể inline body hoặc tổ chức lại file theo quy tắc của phiên bản plugin; **đừng giả định** mọi `bodyFromFile` luôn sinh `bodyFileName` đúng tên gốc.

Khi đóng gói stub cần kiểm tra **mapping và file body cùng hiện diện**. Chỉ copy mappings JSON mà bỏ file dưới thư mục body sẽ khiến stub lỗi khi chạy hoặc trả response không hợp lệ.

Với payload nhị phân, cần xem DSL/version hỗ trợ file body, encoding, MIME type và cách lưu byte. Không convert nhị phân thành chuỗi UTF-8 tùy tiện.

## 15. Matchers động và response templating không giống nhau

Hai cơ chế thường bị trộn lẫn:

- **Request matcher**: quyết định request **có phù hợp một tình huống không**.
- **Response templating**: tính một phần response **từ dữ liệu request** khi stub được gọi, nếu đã được cấu hình và hỗ trợ.

Ví dụ consumer gửi:

~~~http
GET /api/inventory/SKU-456 HTTP/1.1
~~~

Nếu mapping chỉ chấp nhận `SKU-[0-9]+` nhưng response được hardcode:

~~~json
{"sku":"SKU-123","available":true,"quantity":12}
~~~

thì stub có thể nhận request SKU-456 nhưng vẫn trả **SKU-123**. Regex ở request **không tự khiến response echo** lại SKU. Nếu consumer dựa vào sự tương ứng `response.sku == request SKU`, cần:

1. Dùng các contract tình huống xác định;
2. Hoặc cấu hình dynamic property/response templating có kiểm chứng theo DSL/version;
3. Hoặc bổ sung integration test của producer/consumer để kiểm tra quan hệ này.

Một số phiên bản WireMock hỗ trợ **response-template transformer** và các biến như request path/header, nhưng plugin SCC có thể có cách tích hợp cụ thể. Không chép một cú pháp templating từ tài liệu WireMock vào contract rồi mặc định được xử lý. Hãy xem **generated mapping** có phần transformer và response body dự kiến hay không.

## 16. Nhiều contract biến thành nhiều stub scenarios

API thực tế có nhiều kết quả:

~~~text
GET /api/inventory/SKU-123 -> 200, còn hàng
GET /api/inventory/SKU-456 -> 200, hết hàng
GET /api/inventory/SKU-404 -> 404, không tồn tại
POST /api/reservations với body hợp lệ -> 201
POST /api/reservations với quantity=0 -> 400
~~~

Có thể viết một contract cho mỗi scenario quan trọng. SCC sẽ tạo các tài sản test/mapping tương ứng theo khả năng và cấu hình của generator.

Tuy vậy, nhiều contract **cùng method/path** có thể tạo **mapping cạnh tranh**:

- Mapping A so khớp POST với body JSON quá rộng.
- Mapping B dành cho quantity=0, nhưng A cũng match request đó.
- WireMock chọn một mapping theo độ phù hợp/priority, làm consumer nhận sai status.

Cách giảm rủi ro:

1. Đặt điều kiện request đủ rõ: method, path, headers, body/query matchers.
2. Xem generated WireMock mappings, đặc biệt `bodyPatterns` và `priority` nếu có.
3. Chạy test **âm tính**: request dành cho scenario B không được match A.
4. Không dựa vào thứ tự tên file hoặc thứ tự nạp JAR để lựa chọn scenario.
5. Nếu cần stateful scenarios, xác nhận SCC/WireMock version và quy trình có hỗ trợ, thay vì giả định mỗi contract tự lưu state.

**Một mapping nhận được request không đồng nghĩa mapping đó đúng về mặt nghiệp vụ.**

## 17. Stub JAR chứa những gì?

HTTP stub thường được đóng gói thành **JAR có classifier `stubs`** để phân biệt với JAR application. Một bộ tọa độ Maven mẫu:

~~~text
groupId:     com.example
artifactId:  inventory-service
version:     1.3.0-rc1
classifier:  stubs
type:        jar
~~~

Tên file artifact minh họa:

~~~text
inventory-service-1.3.0-rc1-stubs.jar
~~~

Cấu trúc có thể gần như sau (cần kiểm tra JAR **do chính plugin của dự án sinh ra**):

~~~text
inventory-service-1.3.0-rc1-stubs.jar
└── META-INF/
    └── com.example/
        └── inventory-service/
            └── 1.3.0-rc1/
                ├── mappings/
                │   ├── get-inventory.json
                │   ├── inventory-missing.json
                │   └── create-reservation.json
                └── contracts/
                    ├── inventory/
                    │   ├── get-inventory.groovy
                    │   └── inventory-missing.yml
                    └── reservations/
                        └── create-reservation.groovy
~~~

Với response bodies lưu ở file, JAR còn có những tài nguyên tương ứng (thường dưới đường dẫn `__files` phù hợp với cấu trúc WireMock/Stub Runner). Tên, mức lồng thư mục và cả việc có kèm contracts nguồn hay không **phụ thuộc plugin/version, DSL và cấu hình đóng gói**.

Điểm cốt lõi là **mappings và tài nguyên cần thiết phải ở vị trí mà Stub Runner biết cách tìm**. Không nên yêu cầu consumer truy cập trực tiếp cấu trúc nội bộ của JAR.

### Vì sao dùng classifier `stubs`?

- Phân biệt **binary application artifact** và **artifact phục vụ kiểm thử giao tiếp**.
- Cho phép consumer tải stub mà không khởi động ứng dụng.
- Giữ phiên bản contract/stub tương ứng với phiên bản producer.
- Hỗ trợ nhiều consumer khác nhau dùng cùng một bộ mock giao tiếp chuẩn của producer.

Không đánh đồng classifier `stubs` với một Java package hoặc WireMock server chạy sẵn. JAR là **tài sản cấu hình**, Stub Runner/WireMock sẽ nạp và phục vụ HTTP khi test cần.

## 18. Maven: sinh, kiểm chứng và đóng gói stub

Trong producer dùng Maven, cấu hình cơ bản thường có `spring-cloud-contract-maven-plugin` với `extensions`, cùng starter Contract Verifier trong test scope.

Minh họa phần plugin:

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

Và dependency kiểm thử:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-contract-verifier</artifactId>
    <scope>test</scope>
</dependency>
~~~

`CONTRACT_PLUGIN_VERSION` là **placeholder**, không phải phiên bản thật. Hãy dùng phiên bản tương thích với Spring Boot, Spring Cloud Release Train và các dependency Contract theo BOM của dự án. Maven BOM quản lý dependency nhưng **không nhất thiết định version của build plugin**.

Trong một dự án đã cấu hình đúng, luồng lệnh tham khảo:

~~~bash
# Sinh/compile/chạy kiểm chứng contract theo Maven lifecycle đã cấu hình.
./mvnw clean verify

# Install artifact ứng viên (bao gồm stubs nếu plugin đóng gói đúng).
./mvnw install
~~~

Lệnh `install` có thể chạy lại lifecycle nếu gọi riêng sau `verify`; trong CI có thể dùng một chuỗi phù hợp hơn theo pipeline. Khi publish lên repository từ xa, thường có stage `deploy` với credentials và policy rõ ràng.

**Không đoán kết quả từ lệnh:** kiểm tra log plugin có đọc contract, đã sinh generated test, test chạy thành công và có artifact `*-stubs.jar` hay không. Nếu dự án tắt generation/test hoặc task bị skip, lệnh build có thể vẫn kết thúc mà không tạo bằng chứng tương thích.

### Kiểm tra JAR đã được sinh

~~~bash
# Cú pháp tham khảo cho hệ có Java jar CLI.
jar tf target/inventory-service-1.3.0-rc1-stubs.jar
~~~

Tên artifact thực phải lấy từ build output. Kiểm tra có các mapping, contracts/fixture nếu plugin đóng kèm và thư mục tài nguyên liên quan. Nếu JAR không có mapping, quay lại bước discovery/generation trước khi cho consumer tải.

## 19. Gradle: các bước tương đương

Với Gradle, cần áp dụng plugin Spring Cloud Contract phù hợp và cấu hình contracts. Ví dụ một phần cấu hình **Groovy DSL**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.cloud.contract' version 'CONTRACT_PLUGIN_VERSION'
}

contracts {
    baseClassForTests = 'com.example.inventory.ContractTestBase'
}
~~~

Đây là **đoạn minh họa**, không phải build script hoàn chỉnh. Cần thêm dependency, repository/BOM và Spring Boot plugin thích hợp nếu project dùng Spring Boot; `CONTRACT_PLUGIN_VERSION` phải thay bằng version thực.

Các task có thể liên quan đến:

- Sinh tests từ contract;
- Sinh HTTP stubs/WireMock mappings;
- Đóng gói JAR classifier `stubs`;
- Chạy test và publish artifact.

Tên task và dependency của chúng **phụ thuộc phiên bản plugin**. Hãy xem:

~~~bash
./gradlew tasks --all
./gradlew clean build
~~~

Một số phiên bản dùng các task như `generateClientStubs` và `verifierStubsJar`. Không mặc định mọi project đều có những tên đó hoặc task `build` luôn tự publish stub. Kiểm tra task graph, build outputs và mục tiêu publication đã cấu hình.

Khi publish qua `maven-publish`, cần xác nhận **artifact `stubs` được khai báo trong publication** và repository nhận đúng group/artifact/version/classifier. Không chỉ publish application JAR rồi suy ra consumer sẽ tải được stub.

## 20. Stub Runner tải và khởi động stub như thế nào?

Sau khi producer install/publish JAR `stubs`, consumer có thể sử dụng Stub Runner để tự tải artifact và khởi động WireMock server.

Ví dụ test consumer:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-service:1.3.0-rc1:stubs:8081",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class InventoryClientContractTest {

    @Test
    void checkoutCanReadInventory() {
        // Gọi InventoryClient thực tới http://localhost:8081.
        // Assert sku, available và quantity trên response.
    }
}
~~~

Giải thích coordinate:

~~~text
com.example : inventory-service : 1.3.0-rc1 : stubs : 8081
   groupId       artifactId         version      classifier  requested port
~~~

Port 8081 chỉ là ví dụ; trong nhiều dự án, **port động** tốt hơn vì tránh đụng độ khi CI chạy song song. Khi dùng cổng động, client test cần được cấu hình trỏ **đúng port Stub Runner cấp**, thường qua cơ chế injection/lookup của SCC hoặc test properties.

Hai chế độ phân phối thường gặp:

| Mode | Stub lấy từ đâu? | Khi nào dùng |
|---|---|---|
| **LOCAL** | Maven repository local hoặc nguồn local đã cấu hình | Producer/consumer test trên cùng máy hoặc CI stage có artifact đã install |
| **REMOTE** | Artifact repository được chỉ định | CI phân tách job, nhiều nhóm phát triển, cần tái sử dụng stub ứng viên |

Cấu hình repository, authentication, snapshot/release và cache phụ thuộc hạ tầng và phiên bản. Một Stub Runner chạy thành công **không chứng minh** nó đang dùng đúng commit nếu version được gắn không chặt.

## 21. Consumer test phải dùng HTTP client thật

Stub Runner chỉ có ý nghĩa khi consumer test gọi **chính HTTP client mà ứng dụng sử dụng**. Ví dụ client dùng RestClient:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

public class InventoryClient {

    private final RestClient client;

    public InventoryClient(String baseUrl) {
        this.client = RestClient.create(baseUrl);
    }

    public StockResponse getStock(String sku) {
        return client.get()
            .uri("/api/inventory/{sku}", sku)
            .header("X-Client-Id", "checkout-service")
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .body(StockResponse.class);
    }

    public record StockResponse(
            String sku, boolean available, int quantity) {}
}
~~~

Một test consumer có thể cấu hình `InventoryClient` trỏ tới URL của stub và kiểm tra:

~~~java
InventoryClient client = new InventoryClient(
    "http://localhost:8081"
);

InventoryClient.StockResponse result =
    client.getStock("SKU-123");

org.assertj.core.api.Assertions.assertThat(result.sku())
        .isEqualTo("SKU-123");
org.assertj.core.api.Assertions.assertThat(result.available())
        .isTrue();
org.assertj.core.api.Assertions.assertThat(result.quantity())
        .isEqualTo(12);
~~~

Đây là các đoạn minh họa **đặt trong test setup/class phù hợp**, không phải một JUnit test hoàn chỉnh để chép nguyên vào file production.

**Không nên** chỉ gửi request trực tiếp bằng một công cụ khác với client thật rồi kết luận consumer sẽ hoạt động. Client thực có thể thiếu header, sai path, sai serialization hoặc xử lý response lỗi không đúng. Chính những sai khác đó là thứ consumer contract testing cần phát hiện.

Khi API có `404`, `400` hoặc `500` đã được mô tả, consumer cần test cả **cách xử lý lỗi**, không chỉ happy path.

## 22. Stub ứng viên phải đi cùng commit producer

Một vấn đề lớn trong CI là consumer chạy với **artifact cũ**:

~~~text
Commit producer A: GET /inventory -> {"available":true}
Commit producer B: GET /inventory -> {"inStock":true}

Producer B:
  - code mới
  - contract cũng được đổi sang inStock
  - generated producer tests PASS

Consumer cũ:
  - vẫn đọc available
  - test tải stub của commit A
  - consumer tests PASS (xanh giả)
~~~

Muốn phát hiện breaking change, consumer test phải dùng **stub sinh từ contract/code của commit B**. Khi đó test client cũ có thể lỗi vì `available` không còn được trả.

Cách thiết kế pipeline:

1. Producer tạo một **candidate version duy nhất** cho mỗi PR/commit hoặc build.
2. Chạy generated producer tests trước khi công bố artifact.
3. Đóng gói stub của chính build đó, ghi commit SHA và tọa độ artifact.
4. Publish artifact ứng viên tới repository phù hợp.
5. Chuyển **exact coordinate** cho consumer verification job.
6. Chạy consumer tests với tọa độ đó, không dùng `latest` hoặc ký hiệu version động không kiểm soát.
7. Chỉ promote/release khi các cổng tương thích cần thiết đều đạt.

Trong CI song song, tránh ghi đè cùng một version mutable giữa hai commit. Cache phụ thuộc version có thể giữ mapping cũ dù producer đã thay đổi.

## 23. Contract có thể sinh stub đúng nhưng producer vẫn sai

Một trường hợp rất dễ bỏ sót:

- Contract đúng, stub được sinh đúng;
- Consumer test chạy với stub và đạt;
- Producer implementation lại trả status/body khác do refactor.

Vì stub mô phỏng **contract**, không phải **code chạy thật của producer**, consumer test vẫn có thể xanh. Do đó phải thực thi **generated producer tests** trước hoặc cùng với publish.

Ví dụ mutation có chủ đích:

~~~java
// Producer cũ, đúng contract:
return new StockResponse("SKU-123", true, 12);

// Producer mới bị lỗi:
return new StockResponse("SKU-123", false, 12);
~~~

Nếu contract yêu cầu `available: true` và generated test thực sự gọi controller/service production, bài test phải đỏ. Nếu không, kiểm tra test base có đang tự tạo mock response hoặc generated tests có bị skip không.

**Đừng sửa contract theo code sai chỉ để làm build xanh** khi consumer còn phụ thuộc behavior cũ. Nếu chủ ý thay đổi contract, phải có kế hoạch tương thích, migration hoặc versioning.

## 24. Không phải mọi contract đều sinh đúng một stub đơn giản

Cần hiểu những giới hạn sau:

- Một tệp DSL có thể mô tả nhiều tình huống theo cách mà plugin hỗ trợ; số file **không nhất thiết bằng** số mapping.
- Matcher động có thể được dịch thành nhiều điều kiện JSONPath/regex thay vì equality đơn giản.
- Response body có thể được inline, dùng file hoặc thông qua templating được hỗ trợ.
- Contract message sinh các tài sản/mô phỏng messaging, **không nên giả định** nó hoạt động như HTTP WireMock mapping.
- Header hoặc matcher quá rộng có thể dẫn tới nhiều mappings cùng match một request.
- Những hành vi stateful, streaming lâu, pagination động, transaction, auth/permission, retry hoặc latency **không tự xuất hiện trong stub** nếu contract/test không mô tả hoặc không có test bổ sung.
- Một stub cố định thường không thay thế hoàn chỉnh một dịch vụ production có logic nghiệp vụ phong phú.

Vì vậy, stub có vai trò **mô phỏng giao thức đã cam kết để kiểm tra client**, không phải môi trường tích hợp toàn diện. Đối với yêu cầu quan trọng như Kafka routing, database semantics, security hoặc SLO, cần thêm integration/resilience/E2E tests.

## 25. Troubleshooting: tại sao stub không match?

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| WireMock trả 404 không có body lỗi nghiệp vụ | Không có mapping match | Xem unmatched requests và mapping đang nạp |
| Stub luôn trả response sai scenario | Nhiều mapping cùng method/path, matcher quá rộng | Xem `bodyPatterns`, headers, priority, chạy request âm tính |
| GET đúng path nhưng không match | Header `Accept`/`X-Client-Id` thiếu hoặc sai | Xem HTTP request thực gửi và matching predicates |
| POST JSON không match | Body sai field/kiểu, Content-Type, matcher quá chặt | So body sau serialize, matcher JSON/JSONPath |
| Query đúng ý nghĩa nhưng sai thứ tự | URL literal chứa query | Dùng `urlPath` + `queryParameters` nếu DSL yêu cầu |
| Unicode/form body mismatch | Space `+` vs `%20`, `%2B`, encoding kép | Kiểm tra raw bytes và Content-Type |
| Response file không tìm thấy | `bodyFileName` trỏ tài nguyên không đóng gói | Mở JAR, xem `mappings` + `__files` |
| Stub chạy nhưng không có contract mới | Consumer tải artifact/cached version cũ | Kiểm tra exact coordinate, commit, mapping JAR |
| Producer tests không phát hiện regression | Generated test không chạy hoặc base test fake producer | Kiểm tra test source/report, mutation lỗi có chủ đích |
| Stub 404 bị hiểu là SKU_NOT_FOUND | Test chỉ assert HTTP 404 | Assert body `code` và header của business error |
| CI chạy song song bị đụng cổng | Ghim port tĩnh ở nhiều worker | Dùng port động và injection phù hợp |
| Maven/Gradle build xanh nhưng stubs JAR trống | Contract không được phát hiện/generation bị skip | Kiểm tra plugin, đường dẫn và mapping count |
| Stub đúng nhưng consumer production vẫn lỗi | Contract chưa bao phủ case, response dynamic, security hoặc hạ tầng khác | Bổ sung consumer integration/resilience tests |

Thứ tự chẩn đoán hiệu quả: **coordinate artifact → Stub Runner log → mapping JSON → raw request → response mapping → consumer client assertion → producer test report**.

### Xem request không khớp trên WireMock

WireMock có cơ chế ghi request journal và chẩn đoán “near misses” trong một số phiên bản. Dùng test API/log tương ứng để xem WireMock đã thấy **method, path, query, headers và body** nào. Không chỉ xem exception “404” từ HTTP client, vì nó không cho biết mapping nào đã bị bỏ qua.

Nếu dùng WireMock standalone server/Stub Runner với nhiều stub cùng port, phải xác minh chính xác **server instance** nhận request. Có thể đã gọi nhầm stub của một dịch vụ khác hoặc WireMock đang chạy từ test trước.

## 26. Xử lý sai khác ở request/response trước khi sửa contract

Một quy trình debug đúng tránh “hợp thức hóa” bug bằng cách sửa hợp đồng:

1. **Quan sát client thực:** method, URL, query, headers, body và encoding trước khi vào WireMock.
2. **Đối chiếu mapping:** xem điều kiện `request` mà stub đã sinh, không dựa vào trực giác đọc DSL.
3. **Xác định sai phía nào:** client gửi sai cam kết, contract chưa cập nhật theo API hợp lệ, hay generator gặp vấn đề theo version?
4. **Kiểm tra producer thật:** generated test có chạy và assert response đúng không?
5. **Kiểm tra consumer handler:** đã xử lý status/error/response đúng chưa?
6. **Sửa đúng nguyên nhân:** sửa client, sửa code producer, hoặc chỉnh contract theo thay đổi được thống nhất.
7. **Sinh lại artifact ứng viên:** không để consumer tiếp tục dùng JAR cũ.
8. **Thử âm tính:** request sai phải bị từ chối nếu đó là yêu cầu; case 404 nghiệp vụ phải khác unmatched request.

Không nên sửa mapping JSON **bằng tay trong cache Stub Runner** rồi tuyên bố contract đã được thay đổi; mapping được sinh lại từ source contract mới là nguồn kiểm soát phiên bản.

## 27. Bảo mật và dữ liệu trong stub artifacts

Stubs JAR thường được phân phối rộng hơn runtime service. Đừng đặt dữ liệu nhạy cảm vào contract hoặc fixture:

- Không chèn token thật, API key, mật khẩu, session cookie hay private signing key vào request/response mẫu.
- Không dùng dữ liệu khách hàng thật trong body file/fixtures, kể cả bản dump được “ẩn tên” không đầy đủ.
- Dùng ID giả, địa chỉ giả và dữ liệu tổng hợp có thể chia sẻ.
- Nếu header bảo mật cần được match, dùng **giá trị test** hoặc matcher phù hợp, không hardcode credential production.
- Kiểm soát repository quyền đọc/ghi nếu stub schema hoặc payload thuộc tài sản nội bộ cần bảo vệ.
- Tránh đưa nguyên request chứa Authorization vào log CI; chỉ log thông tin tối thiểu và redact.
- Không tự coi Stub Runner là server có cơ chế auth đầy đủ của producer; stub test thường chỉ mô phỏng những điều kiện được cấu hình.

Một consumer test có thể được phép chạy trên laptop hoặc CI không có production secret. Đó là lợi ích lớn của stub, nhưng chỉ an toàn khi fixture đã được thiết kế đúng.

## 28. Thực hành A — Từ contract đầu tiên tới WireMock mapping

**Mục tiêu:** nhìn thấy “đường chuyển đổi” thay vì chỉ đọc khái niệm.

1. Tạo Inventory Service có endpoint `GET /api/inventory/SKU-123` trả JSON như phần 3.
2. Cấu hình Spring Cloud Contract plugin và producer test base phù hợp.
3. Viết một contract Groovy hoặc YAML ở đúng thư mục hợp đồng.
4. Chạy build generation theo plugin/version dự án.
5. Mở generated producer test: xem request và assertions.
6. Mở generated WireMock mapping: tìm `request.method`, URL/header predicates, `response.status` và body.
7. Cho producer trả sai `available:false`, kiểm chứng test đỏ.
8. Khôi phục code, chạy test lại và đóng gói `*-stubs.jar`.

**Bằng chứng nộp:** file contract, generated test source/report, mapping JSON và tên stubs JAR. Không cần phải có đúng cùng tên file mapping như ví dụ.

## 29. Thực hành B — Consumer gọi stub và xử lý response

**Mục tiêu:** consumer sử dụng stub như một server HTTP thay thế.

1. Install/publish candidate stubs JAR của Inventory Service.
2. Tạo test Checkout với Stub Runner `LOCAL` hoặc `REMOTE` phù hợp.
3. Cấu hình `InventoryClient` trỏ vào **port thực của stub**.
4. Gọi client thật `GET /api/inventory/SKU-123` với `Accept` và `X-Client-Id` đúng.
5. Assert `sku`, `available` và `quantity` như contract.
6. Cố tình bỏ `X-Client-Id`: xem stub có từ chối match hay không.
7. Cố tình đổi URL thành `/api/inventory/SKU-456`: xem mapping nào xử lý và phân biệt unmatched với 404 nghiệp vụ.
8. Đọc request journal/near misses nếu có và giải thích mismatch.

**Bằng chứng nộp:** artifact coordinate, logs Stub Runner, request thực và test report consumer.

## 30. Thực hành C — Breaking change và CI gate

**Bối cảnh:** producer muốn đổi response field `available` thành `inStock`.

1. **Giữ contract cũ**, đổi implementation producer: generated test phải đỏ nếu đang bảo vệ field đó.
2. Nếu đổi contract theo hành vi mới, generated producer test có thể xanh nhưng **consumer cũ chưa chắc an toàn**.
3. Sinh stub ứng viên của commit mới, dùng exact candidate version.
4. Chạy Checkout client test cũ với stub đó: kiểm tra có lỗi deserialize/logic hoặc assertion nào đỏ không.
5. Đề xuất chiến lược mở rộng–chuyển đổi–thu hẹp: thêm field mới mà vẫn giữ `available` trong giai đoạn chuyển đổi, hoặc versioning API khi cần.
6. Tạo thêm một case `404 SKU_NOT_FOUND` và chứng minh nó khác unmapped 404.
7. Thêm gate CI chặn khi **generated producer test không chạy**, stub JAR không có mapping, hoặc consumer test dùng sai artifact.

**Bằng chứng nộp:** bảng kết quả producer/consumer trước–sau, diff contract, tọa độ stub từng commit và kế hoạch migration.

## 31. Checklist khi review sinh và đóng gói HTTP stub

- [ ] Contract source đúng module, đúng thư mục và DSL được plugin hỗ trợ.
- [ ] Request method, URL/path/query, headers và body được mô tả rõ.
- [ ] Response status, headers, body, kiểu JSON và body file có ý nghĩa đúng với consumer.
- [ ] Generated producer tests thực sự được sinh, compile và chạy với **implementation producer**.
- [ ] Stub mappings đã được sinh và có ít nhất một scenario cần thiết.
- [ ] Matcher của mapping **không quá rộng hoặc quá chặt** so với contract.
- [ ] Request không khớp stub và business 404 được phân biệt trong test.
- [ ] Các mapping cùng method/path được kiểm tra chống overlap, có test âm tính.
- [ ] Mọi `bodyFileName`/fixture cần thiết được đóng gói cùng JAR.
- [ ] Stubs JAR có group/artifact/version/classifier rõ ràng, không phải application JAR.
- [ ] Artifact ứng viên khớp **chính commit** producer đang kiểm tra.
- [ ] Consumer dùng Stub Runner ở chế độ repository phù hợp và port thực.
- [ ] Consumer tests gọi **HTTP client thật**, không chỉ gửi request bằng mock/test helper khác.
- [ ] Consumer test có cả response thành công và error scenarios quan trọng.
- [ ] Không có secret hoặc dữ liệu người dùng thật trong contract/stub artifact.
- [ ] CI chặn khi producer verification thất bại, không có contract/generated tests hoặc stub trống.
- [ ] Các thay đổi API nguy cơ breaking đều được kiểm tra với consumer cũ trước release.

## 32. Câu hỏi tự kiểm tra

**1. Tại sao cần sinh cả producer test và HTTP stub từ cùng contract?**

Vì producer test chứng minh code producer tuân thủ cam kết, còn stub giúp consumer kiểm tra client với hành vi mẫu. Chỉ có stub không xác nhận implementation producer đúng.

**2. Phần `request` và `response` của contract đi vào stub như thế nào?**

`request` được chuyển thành các **điều kiện WireMock matching**; `response` trở thành status, headers và body mà WireMock trả khi một request khớp.

**3. Stub có tự truy vấn database hay chạy InventoryService thật không?**

Không. WireMock phục vụ các response đã được mô tả hoặc templating được cấu hình; nó không tự thực thi business logic producer.

**4. `equalToJson` và `matchesJsonPath` dùng khi nào?**

Cả hai đều có thể là cách kiểm tra JSON body của request trong WireMock. `equalToJson` so sánh nội dung JSON theo quy tắc equality; `matchesJsonPath` kiểm tra một điều kiện theo đường dẫn. Cần xem mapping thật để hiểu generator đã chọn cách nào và mức độ chặt của nó.

**5. Tại sao `404` từ WireMock không nhất thiết là `SKU_NOT_FOUND`?**

Vì đó có thể là **unmatched request**, không phải một mapping error response 404 được định nghĩa trong contract. Phải kiểm tra response schema/mapping/log.

**6. Tại sao cần classifier `stubs` và version ứng viên?**

Classifier phân biệt artifact mock giao tiếp với application JAR; candidate version giúp consumer test tải đúng stub của thay đổi đang xét, không phải mapping cũ.

**7. Nếu producer và contract cùng đổi `available` thành `inStock` rồi producer test xanh, có đủ an toàn không?**

Chưa. Consumer cũ vẫn có thể đọc `available`. Cần sinh stub của commit mới và chạy consumer test cũ với stub ứng viên, hoặc lập kế hoạch migration/versioning.

**8. Nếu request SKU-456 match một regex nhưng stub trả SKU-123, có phải generator tự sai không?**

Không nhất thiết. Matcher request chỉ chọn mapping; response cố định có thể vẫn trả mẫu SKU-123. Nếu contract yêu cầu response phụ thuộc request, cần mô tả cơ chế dynamic response phù hợp hoặc chia scenario rõ hơn.

## 33. Tài liệu tham khảo

- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/): hợp đồng HTTP/message, Contract Verifier, sinh stub và Stub Runner.
- [Spring Cloud Contract — HTTP Contracts](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/http.html): request/response, DSL HTTP.
- [Spring Cloud Contract — Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): Groovy/YAML DSL, dynamic values và matcher.
- [Spring Cloud Contract — Maven Plugin](https://docs.spring.io/spring-cloud-contract/reference/project-features-maven.html): tích hợp Maven, test generation, stub packaging.
- [Spring Cloud Contract — Gradle Plugin](https://docs.spring.io/spring-cloud-contract/reference/project-features-gradle.html): các task và cấu hình Gradle.
- [Spring Cloud Contract — Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner.html): tải artifact và chạy stub phía consumer.
- [WireMock — Stubbing](https://wiremock.org/docs/stubbing/): cấu trúc request/response mappings.
- [WireMock — Request Matching](https://wiremock.org/docs/request-matching/): URL, header, query và JSON/body matching.
- [WireMock — Response Templating](https://wiremock.org/docs/response-templating/): khi response được tạo từ request, cần cấu hình transformer phù hợp.

**Lưu ý phiên bản:** tên task/goal, định dạng mapping, vị trí resource trong JAR, cách dùng dynamic values và cấu hình Stub Runner có thể khác theo phiên bản Spring Cloud Contract/WireMock. Luôn đối chiếu tài liệu đi cùng **Spring Boot–Spring Cloud Release Train–Contract** đang dùng, kiểm tra **generated source, mappings và artifact thật**. Ví dụ trong bài là tài liệu minh họa, không phải kết quả một build đã chạy.

---

**Điểm cần nhớ:** SCC lấy **request của contract** để sinh điều kiện **WireMock matching**, lấy **response của contract** để tạo dữ liệu stub trả về, đồng thời sinh **producer tests** để kiểm chứng code thật. Những mapping/tài nguyên này được đóng gói vào **stubs JAR** có phiên bản, rồi Stub Runner khởi động thành HTTP server cho consumer. Chỉ khi **producer test đạt, stub đúng commit và consumer test với client thật đạt**, quy trình mới có cơ sở phát hiện thay đổi API không tương thích.

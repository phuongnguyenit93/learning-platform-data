# Tách dữ liệu body lớn sang tệp tài nguyên

## 1. Bối cảnh: vì sao không nên nhúng mọi payload vào contract?

Trong **Spring Cloud Contract (SCC)**, một contract mô tả lời cam kết giao tiếp giữa **producer** và **consumer**: request nào được chấp nhận, response nào được trả về, hoặc thông điệp nào được phát đi. Contract có thể viết bằng **Groovy DSL** hoặc **YAML DSL**. SCC dùng contract để sinh bài kiểm thử phía producer và tạo stub cho consumer kiểm tra qua **Stub Runner**. Pipeline CI có thể chạy hai phía này để phát hiện thay đổi API không tương thích.

Ở giai đoạn đầu, một response có vài trường thường được viết trực tiếp trong DSL:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    request {
        method GET()
        url '/api/inventory/SKU-123'
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

Cách này ngắn và dễ đọc. Tuy nhiên, nếu response có hàng trăm dòng JSON, nhiều mảng lồng nhau, dữ liệu đa ngôn ngữ hoặc cấu trúc message phức tạp, phần **hành vi** của contract bị che bởi phần **dữ liệu minh họa**. Người review khó nhận ra thay đổi thực chất nằm ở đường dẫn, status, header, kiểu dữ liệu hay chỉ là một giá trị trong body.

Một giải pháp là đặt body vào **tệp tài nguyên riêng** và để contract **tham chiếu** tới tệp đó. Lúc này, DSL tiếp tục mô tả quy tắc giao tiếp; tài nguyên lưu payload cụ thể. Điều quan trọng là hai thành phần vẫn phải được review và kiểm thử cùng nhau.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Quyết định khi nào nên giữ body ngay trong DSL và khi nào nên tách ra tệp riêng.
2. Tổ chức contract và fixture JSON/XML/text theo một cấu trúc dễ tìm, dễ review.
3. Sử dụng **Groovy DSL** với `file(...)` và **YAML DSL** với `bodyFromFile`.
4. Phân biệt tệp chứa **dữ liệu ví dụ cố định** với **body matcher** dùng để mô tả dữ liệu động.
5. Kiểm tra đường dẫn, nội dung, generated producer test, stub artifact và consumer test khi đưa fixture vào CI.

## 2. Phân biệt contract, payload fixture và matcher

Ba khái niệm liên quan nhưng có trách nhiệm khác nhau:

| Thành phần | Chứa gì? | Ví dụ |
|---|---|---|
| **Contract** | Method, URL, status, header, body reference, matcher, message destination và điều kiện kích hoạt | `stock-available.groovy` hoặc `stock-available.yml` |
| **Payload fixture** | Nội dung request/response/message mẫu ở dạng JSON, XML, text hoặc byte | `payloads/stock-available.json` |
| **Matcher** | Quy tắc xác nhận các giá trị có thể thay đổi nhưng vẫn hợp lệ | Trường `transactionId` phải đúng kiểu UUID, `items` có kiểu dữ liệu phù hợp |

Ví dụ: contract yêu cầu GET `/api/inventory/SKU-123`, response HTTP 200 và `Content-Type: application/json`. Fixture lưu đối tượng tồn kho gồm danh sách kho hàng. Matcher có thể cho phép trường thời điểm cập nhật thay đổi mà không khiến test sai do giá trị cố định.

Tệp tài nguyên **không thay thế contract**: chỉ có JSON mà thiếu DSL thì SCC chưa biết request nào kích hoạt stub, HTTP status nào cần trả hoặc response thuộc tình huống nào. Ngược lại, DSL tham chiếu tệp không tồn tại thì contract không thể được xử lý như kỳ vọng.

## 3. Khi nào nên tách body ra file?

Có thể cân nhắc tách payload khi gặp một hoặc nhiều dấu hiệu:

- Body dài khiến người đọc phải cuộn qua nhiều màn hình mới nhìn thấy status, header hoặc matcher.
- Đối tượng JSON/XML có **cấu trúc lồng sâu**, nhiều phần tử mảng hoặc nhiều nhánh dữ liệu.
- Cần xem/chỉnh payload bằng trình định dạng JSON/XML, so sánh mẫu với schema hoặc kiểm tra dữ liệu bằng công cụ riêng.
- Cần quản lý nhiều tình huống trả về như **còn hàng**, **hết hàng**, **không tìm thấy**, **lỗi nghiệp vụ**.
- Một thông điệp có payload lớn và nhiều trường cần được kiểm tra giữa producer với consumer.

Ngược lại, body chỉ 2–3 trường và bộc lộ rõ ý nghĩa hợp đồng thì nhúng trực tiếp trong DSL vẫn phù hợp. Không cần tách mọi response nhỏ thành file vì sẽ khiến người review phải mở quá nhiều tệp để hiểu một hành vi đơn giản.

**Nguyên tắc:** tách để tăng khả năng đọc và kiểm chứng; không tách chỉ để đạt một số dòng giới hạn cứng.

## 4. Đề xuất cấu trúc thư mục

Ví dụ bên **Inventory Service** dùng một contract Groovy và một fixture JSON:

~~~text
inventory-service/
└── src/
    └── test/
        └── resources/
            └── contracts/
                └── inventory/
                    ├── stock-available.groovy
                    ├── stock-unavailable.groovy
                    └── payloads/
                        ├── stock-available.json
                        └── stock-unavailable.json
~~~

Trong bài này:

- `contracts/` là thư mục chứa hợp đồng để Contract Verifier tìm khi build được cấu hình theo vị trí mặc định.
- `inventory/` nhóm hợp đồng theo ngữ cảnh API hoặc bounded context.
- `stock-available.groovy` định nghĩa request và response cho trường hợp còn hàng.
- `payloads/stock-available.json` lưu mẫu response được contract đó tham chiếu.
- Nếu chọn **YAML DSL**, có thể dùng `stock-available.yml` thay cho `stock-available.groovy`. Không nên vô tình giữ cả hai dưới cùng thư mục nếu chúng chỉ là hai bản sao của cùng một tình huống; công cụ build có thể coi chúng là hai contract.

Đường dẫn trong `file(...)` hoặc `bodyFromFile` phải được giải quyết theo quy tắc của **DSL và phiên bản SCC** đang sử dụng. Cách tổ chức đơn giản nhất để bắt đầu là **đặt fixture trong thư mục con gần contract** và sử dụng đường dẫn tương đối rõ ràng; kiểm tra ngay bằng bước sinh test/stub thực tế. Nếu dự án tùy chỉnh vị trí contract trong Maven/Gradle, phải đối chiếu lại cách resolve đường dẫn thay vì sao chép mù quáng.

### Quy ước đặt tên

| Nên dùng | Vì sao? |
|---|---|
| `stock-available.json` | Thể hiện tình huống nghiệp vụ, dễ tìm khi test thất bại |
| `stock-unavailable.json` | Phân biệt rõ với response còn hàng |
| `reservation-created.json` | Gắn với trạng thái và kết quả của API |
| `inventory-changed-event.json` | Thể hiện payload dành cho thông điệp |
| `payloads/` | Phân biệt dữ liệu mẫu với tệp contract |

Tránh đặt tên chung chung kiểu `body1.json`, `data-final.json` hoặc `sample-new-2.json`. Tên file nên cho biết **dữ liệu thuộc hợp đồng và kịch bản nào**, không chỉ mô tả định dạng.

## 5. Ví dụ đầy đủ với Groovy DSL

Giả sử consumer **Checkout Service** gọi:

~~~http
GET /api/inventory/SKU-123 HTTP/1.1
Accept: application/json
~~~

Producer trả dữ liệu tồn kho theo từng kho và các thuộc tính của sản phẩm.

### 5.1. Đưa body ra tệp JSON

Nội dung tệp **`src/test/resources/contracts/inventory/payloads/stock-available.json`**:

~~~json
{
  "sku": "SKU-123",
  "available": true,
  "quantity": 12,
  "warehouses": [
    {
      "code": "HCM-01",
      "quantity": 7,
      "priority": 1
    },
    {
      "code": "HN-02",
      "quantity": 5,
      "priority": 2
    }
  ],
  "attributes": {
    "unit": "piece",
    "allowBackorder": false,
    "tags": [
      "ready-to-ship",
      "standard"
    ]
  }
}
~~~

Lợi ích là phần nội dung JSON có thể được format, validate và review như một tài liệu dữ liệu độc lập. Ví dụ dùng giá trị cố định `SKU-123` để dễ kiểm chứng, đồng thời cho thấy các mảng và đối tượng lồng nhau khiến inline DSL nhanh chóng dài ra.

### 5.2. Tham chiếu tệp trong contract

Nội dung tệp **`src/test/resources/contracts/inventory/stock-available.groovy`**:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Checkout đọc tồn kho của SKU-123'

    request {
        method GET()
        url '/api/inventory/SKU-123'
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }

        body(file('payloads/stock-available.json'))
    }
}
~~~

Điểm đáng chú ý:

1. `body(file('payloads/stock-available.json'))` yêu cầu SCC lấy body từ tệp, thay vì khai báo trực tiếp toàn bộ đối tượng trong contract.
2. `status OK()` và `contentType(applicationJson())` vẫn nằm trong contract vì chúng là phần quan trọng của hành vi HTTP.
3. Fixture đặt gần contract để người review thấy rõ thay đổi trong cùng một PR.
4. Request, response và payload đều thuộc **cùng một tình huống**. Không nên tham chiếu tệp của tình huống hết hàng cho contract còn hàng chỉ vì cấu trúc JSON gần giống.

Đây là **cặp tệp minh họa**. Khi thực hành, bạn cần tạo cả contract và JSON ở vị trí mà plugin đã cấu hình; chỉ tạo file JSON mà không sửa DSL sẽ không làm test sử dụng dữ liệu mới.

## 6. Cách tương đương với YAML DSL

Nếu nhóm dùng **YAML DSL**, SCC hỗ trợ thuộc tính **`bodyFromFile`** để chỉ định tệp body, ví dụ **`stock-available.yml`**:

~~~yaml
description: Checkout đọc tồn kho của SKU-123

request:
  method: GET
  url: /api/inventory/SKU-123

response:
  status: 200
  headers:
    Content-Type: application/json
  bodyFromFile: payloads/stock-available.json
~~~

Ở đây, `bodyFromFile` đóng vai trò tương đương lời tham chiếu `file(...)` trong Groovy DSL. Dữ liệu JSON vẫn giữ nguyên như phần trước.

**Lưu ý cú pháp:** trường `bodyFromFile` thuộc **DSL của Spring Cloud Contract**, không phải cú pháp YAML chuẩn tự diễn giải. YAML parser thông thường chỉ đọc được chuỗi đường dẫn; Contract Verifier mới hiểu rằng cần lấy body từ file. Hãy kiểm tra đúng tài liệu DSL của **phiên bản SCC hiện dùng**, đặc biệt khi chuyển đổi giữa Groovy và YAML hoặc nâng major version.

### So sánh nhanh

| Nhu cầu | Groovy DSL | YAML DSL |
|---|---|---|
| Body JSON khai báo trực tiếp | `body(...)` | `body:` |
| Body lấy từ file | `body(file('payloads/stock-available.json'))` | `bodyFromFile: payloads/stock-available.json` |
| Status HTTP | `status OK()` | `status: 200` |
| Content type | `contentType(applicationJson())` trong `headers` | `Content-Type: application/json` trong `headers` |
| Kiểm tra trường động | `bodyMatchers` và các matcher phù hợp | Các cấu hình `matchers` của YAML DSL |

Một contract chỉ cần dùng **một** trong hai định dạng. Hai đoạn ví dụ trên là hai cách viết thay thế nhau để học cú pháp, không cần cùng tồn tại trong dự án.

## 7. Tách cả request body và response body

Không chỉ response, **request có body lớn** cũng nên được tổ chức thành fixture khi điều đó giúp contract rõ hơn.

Giả sử một dịch vụ tạo phiếu giữ hàng:

~~~http
POST /api/reservations HTTP/1.1
Content-Type: application/json
~~~

Tệp `payloads/reservation-request.json`:

~~~json
{
  "requestId": "REQ-1001",
  "customerRef": "CUSTOMER-DEMO",
  "items": [
    {
      "sku": "SKU-123",
      "quantity": 2
    },
    {
      "sku": "SKU-456",
      "quantity": 1
    }
  ],
  "options": {
    "allowPartial": false,
    "warehouseRegion": "south"
  }
}
~~~

Tệp `payloads/reservation-created.json`:

~~~json
{
  "reservationId": "RSV-1001",
  "status": "CREATED",
  "reservedItems": 2
}
~~~

Contract Groovy:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Tạo phiếu giữ hàng thành công'

    request {
        method POST()
        url '/api/reservations'
        headers {
            contentType(applicationJson())
        }
        body(file('payloads/reservation-request.json'))
    }

    response {
        status CREATED()
        headers {
            contentType(applicationJson())
        }
        body(file('payloads/reservation-created.json'))
    }
}
~~~

Cùng ý tưởng trong YAML DSL:

~~~yaml
description: Tạo phiếu giữ hàng thành công
request:
  method: POST
  url: /api/reservations
  headers:
    Content-Type: application/json
  bodyFromFile: payloads/reservation-request.json
response:
  status: 201
  headers:
    Content-Type: application/json
  bodyFromFile: payloads/reservation-created.json
~~~

Việc tách request và response giúp reviewer nhìn thấy ngay phần nào mô tả **đầu vào producer cần chấp nhận** và phần nào mô tả **đầu ra producer phải bảo đảm**. Đồng thời, một thay đổi làm request payload không còn đúng có thể ảnh hưởng đến stub matching phía consumer; cần kiểm tra cả hai phía chứ không chỉ response.

## 8. Fixture cố định khác gì dữ liệu động?

Tách body ra file **không tự động biến các trường trong file thành giá trị linh hoạt**. Nếu JSON ghi:

~~~json
{
  "reservationId": "RSV-1001",
  "status": "CREATED"
}
~~~

thì `RSV-1001` vẫn là giá trị ví dụ cụ thể. Với producer tạo ID động mỗi lần chạy, một kiểm chứng so sánh cứng có thể thất bại dù hành vi sản phẩm là hợp lệ.

Cần xác định riêng:

- **Giá trị bất biến:** ví dụ `status` phải là `CREATED` đối với kịch bản tạo thành công.
- **Giá trị biến thiên có ràng buộc:** `reservationId` là chuỗi không rỗng, có cấu trúc xác định; `updatedAt` là thời gian hợp lệ.
- **Giá trị cần liên hệ với request:** SKU hoặc request ID được phản ánh lại theo logic nghiệp vụ.
- **Thứ tự và tập phần tử:** khi consumer phụ thuộc thứ tự mảng, phải thể hiện ràng buộc đó; nếu không, cần cân nhắc matcher phù hợp.

Với Groovy DSL, có thể dùng **`bodyMatchers`** để mô tả quy tắc thay vì buộc mọi lần chạy trả đúng một ID cố định. Ví dụ minh họa phần matcher đặt trong **response** của contract dùng JSON ở trên:

~~~groovy
response {
    status CREATED()
    headers {
        contentType(applicationJson())
    }
    body(file('payloads/reservation-created.json'))

    bodyMatchers {
        jsonPath('$.reservationId', byRegex('RSV-[0-9]+'))
    }
}
~~~

Matcher giúp diễn tả điều kiện với trường động; vẫn cần kiểm tra **hành vi thực tế của generated producer test và stub** theo phiên bản SCC đang chạy. Regex phía **producer test** và cách sinh **response ở consumer stub** không nhất thiết giống nhau về ý nghĩa. Chẳng hạn, stub có thể trả giá trị ví dụ trong fixture trong khi producer test chấp nhận nhiều ID đúng mẫu.

Với YAML, hãy dùng nhóm cấu hình `matchers` tương ứng của phiên bản DSL đang dùng; không chèn placeholder tùy ý vào JSON rồi giả định SCC sẽ tự nội suy. Những biểu thức có ý nghĩa trên một DSL có thể không được xử lý giống nhau ở DSL còn lại.

## 9. Có nên tái sử dụng cùng một file ở nhiều contract?

Tái sử dụng fixture có ích khi **hai contract thật sự cam kết một payload giống nhau**. Tuy nhiên, việc chia sẻ quá rộng khiến sửa một JSON vô tình thay đổi hành vi của nhiều hợp đồng.

Ví dụ:

| Tình huống | Nên làm | Lý do |
|---|---|---|
| Hai contract dùng cùng một response lỗi chung có semantics giống hệt | Có thể dùng chung `error-invalid-request.json` | Giảm trùng lặp mà không làm mơ hồ hành vi |
| Còn hàng và hết hàng có cùng schema nhưng `available` khác nhau | Tạo hai fixture rõ nghĩa | Reviewer thấy khác biệt nghiệp vụ và contract riêng |
| GET sản phẩm và event cập nhật sản phẩm cùng chứa một số trường giống nhau | Cân nhắc **tách file theo kênh giao tiếp** | HTTP response và event có vòng đời, schema, consumer khác nhau |
| Nhiều contract chỉ khác ID động | Dùng matcher hoặc cấu trúc hợp đồng phù hợp | Sao chép hàng loạt file chỉ để đổi một ID sẽ khó bảo trì |

**Đừng biến fixture thành kho dữ liệu dùng chung không có chủ sở hữu.** Trong bài kiểm thử contract, mỗi tệp phải được gắn với hành vi và phạm vi thay đổi có thể xác định.

Khi cần một fixture dùng chung, đặt tên rõ ràng và đánh giá tác động đến **mọi contract đang tham chiếu** trước khi sửa.

## 10. Với message contract thì tệp body nằm ở đâu?

Spring Cloud Contract còn hỗ trợ hợp đồng **thông điệp**, nơi producer phát message thay vì trả HTTP response. Body event dài có thể được tách tương tự.

Ví dụ `payloads/inventory-changed-event.json`:

~~~json
{
  "eventId": "EVT-1001",
  "eventType": "InventoryChanged",
  "sku": "SKU-123",
  "after": {
    "available": true,
    "quantity": 12
  },
  "source": {
    "service": "inventory-service",
    "region": "south"
  }
}
~~~

Một contract Groovy mô tả thông điệp đầu ra:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'inventoryChanged'

    input {
        triggeredBy('triggerInventoryChanged()')
    }

    outputMessage {
        sentTo('inventory.events')
        body(file('payloads/inventory-changed-event.json'))
    }
}
~~~

Đây là **mẫu học tập**; phương thức `triggerInventoryChanged()` cần được cung cấp bởi test base và cơ chế messaging mà dự án cấu hình. Khi tích hợp Kafka, RabbitMQ hoặc Spring Cloud Stream, hãy kiểm tra thêm destination/topic, header, serialization, schema và cách kích hoạt, thay vì chỉ kiểm tra JSON trong file.

Nếu payload message có trường động hoặc cần đối chiếu với request/event trước đó, hãy bổ sung matcher phù hợp. Việc dùng file giúp kiểm tra payload thuận tiện hơn nhưng **không thay thế cấu hình môi trường messaging**.

## 11. Dữ liệu văn bản, XML và nhị phân

Không phải body nào cũng là JSON. Tách ra file càng hữu ích khi cần giữ chính xác dấu xuống dòng, dấu cách có ý nghĩa hoặc định dạng riêng.

### XML hoặc văn bản

Một response XML có thể dùng tệp `payloads/stock.xml`:

~~~xml
<stock>
    <sku>SKU-123</sku>
    <available>true</available>
    <quantity>12</quantity>
</stock>
~~~

Contract vẫn tham chiếu bằng `file('payloads/stock.xml')` hoặc `bodyFromFile`, đồng thời khai báo `Content-Type` phù hợp, ví dụ `application/xml`.

### Dữ liệu nhị phân

Với PDF, ảnh hoặc payload byte khác, **không dùng cách đọc chuỗi văn bản thông thường** nếu cần giữ byte nguyên vẹn. Các phiên bản SCC hỗ trợ cơ chế như **`fileAsBytes(...)`** trong Groovy DSL hoặc **`bodyFromFileAsBytes`** ở YAML DSL cho body ở dạng byte. Cần kiểm tra cú pháp và khả năng hỗ trợ của version đã chốt.

Ví dụ minh họa kiểu tham chiếu:

~~~groovy
response {
    status OK()
    headers {
        header('Content-Type', 'application/pdf')
    }
    body(fileAsBytes('payloads/invoice-demo.pdf'))
}
~~~

Tệp binary phải được cung cấp trong phạm vi tài nguyên contract mà build có thể truy cập. Khi đóng gói stub, cần xác minh byte thực sự được trả về, header đúng và kích thước/checksum phù hợp. Không nên dùng file text chứa chuỗi Base64 rồi mặc định đó là bytes của PDF nếu contract không mô tả quá trình giải mã.

## 12. Từ tệp body đến generated producer test và stub

Chuyển payload từ inline DSL sang file **không làm thay đổi mục đích contract**. Với HTTP, dòng xử lý có thể mô tả như sau:

~~~mermaid
flowchart TD
    A["Contract Groovy/YAML"] --> C["Spring Cloud Contract"]
    B["Fixture JSON/XML/text/bytes"] --> C
    C --> D["Generated producer test"]
    C --> E["Stub mappings / stub artifact"]
    D --> F{"Producer thực tế đáp ứng contract?"}
    E --> G["Consumer test qua Stub Runner"]
    F -- "Không" --> H["Sửa code, contract hoặc fixture"]
    F -- "Có" --> I["Đánh giá kết quả consumer"]
    G --> I
    I --> J{"Các consumer cần hỗ trợ đều đạt?"}
    J -- "Không" --> H
    J -- "Có" --> K["Đủ điều kiện tiếp tục quy trình release"]
~~~

Chẳng hạn, Checkout Service đang đọc `available`. Nếu ai đó sửa fixture `stock-available.json` từ:

~~~json
{
  "sku": "SKU-123",
  "available": true
}
~~~

sang:

~~~json
{
  "sku": "SKU-123",
  "inStock": true
}
~~~

thì đây **không chỉ là chỉnh dữ liệu test**; nó có thể biểu thị việc đổi contract và phá tương thích consumer. Nếu producer đã đổi code theo fixture mới, generated producer test có thể vẫn xanh. **Consumer test với stub được sinh từ fixture mới** mới cho thấy client hiện tại còn đọc được dữ liệu hay không.

Vì vậy, khi review thay đổi payload, cần đặt hai câu hỏi:

1. Fixture đã thay đổi **giá trị ví dụ** hay thay đổi **cam kết API/message**?
2. Stub ứng viên tạo từ thay đổi đó đã được **consumer thực tế** kiểm tra chưa?

Không nên coi một PR “chỉ sửa JSON fixture” là thay đổi an toàn nếu field, kiểu dữ liệu, cấu trúc lồng nhau hoặc semantics đã đổi.

## 13. Kiểm chứng fixture và đường dẫn trước khi tích hợp CI

Các bước kiểm tra hiệu quả có thể được áp dụng theo thứ tự:

**Bước 1 — Kiểm tra định dạng gốc.** JSON phải parse hợp lệ, không có dấu phẩy thừa hoặc comment không hợp lệ; XML phải well-formed; văn bản cần encoding/line-ending đúng; binary cần được lưu nguyên byte. Dùng dữ liệu giả lập, không để thông tin cá nhân hay token thật trong fixture.

**Bước 2 — Kiểm tra đường dẫn tham chiếu.** Xác nhận tên tệp và chữ hoa/chữ thường khớp, nhất là khi CI chạy Linux trong khi người viết contract dùng Windows. Khi đổi tên hoặc di chuyển file, phải sửa mọi contract đang tham chiếu.

**Bước 3 — Chạy producer contract generation.** Xác nhận SCC thực sự tìm và đọc được fixture. Kiểm tra generated test đã chứa assertion liên quan đến body, không chỉ khởi động build thành công mà không sinh test.

**Bước 4 — Chạy producer test.** Test phải chạy với code producer và ngữ cảnh dữ liệu thích hợp; sai khác JSON, status hoặc message phải khiến test báo lỗi.

**Bước 5 — Kiểm tra stub đã sinh.** Mở artifact hoặc kết quả đóng gói để xác nhận body thực tế của stub phản ánh fixture. Khi dùng body từ file, cần xác minh các file/mapping liên quan được đưa vào đầu ra build theo cơ chế của phiên bản plugin hiện tại.

**Bước 6 — Chạy consumer test với stub ứng viên.** Ghim đúng group, artifact, version và classifier; Stub Runner phải dùng artifact mới sinh, không lấy nhầm stub cũ đã có trong local cache.

Ví dụ các lệnh **tham khảo để học viên chạy trong dự án producer đã cấu hình SCC**:

~~~bash
# Maven: sinh, chạy test và kiểm tra vòng đời build.
./mvnw clean verify

# Gradle: chạy test, bao gồm generated tests nếu plugin đã nối đúng task.
./gradlew clean test
~~~

Trên Windows dùng wrapper tương ứng (`mvnw.cmd`, `gradlew.bat`). Các lệnh trên chỉ là điểm khởi đầu: cách tạo stub JAR, đường dẫn generated sources và task cụ thể phụ thuộc plugin/build của dự án.

**Điểm kiểm chứng then chốt:** build thành công chỉ đáng tin khi contract đã được phát hiện, body fixture được đọc, generated test chạy, và stub mới thực sự được tạo/kiểm thử.

## 14. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| Build báo không tìm thấy tệp body | Sai đường dẫn tương đối, rename, đặt file ngoài vị trí mà DSL loader đọc | Kiểm tra vị trí contract, vị trí fixture và quy tắc resolve của SCC version đang dùng |
| Chạy trên Windows được nhưng Linux CI lỗi | Sai chữ hoa/chữ thường, separator hoặc file chưa commit | Kiểm tra chính xác tên tệp và đường dẫn trong Git |
| JSON fixture parse lỗi | Thiếu dấu ngoặc, dấu phẩy cuối, comment hoặc BOM/encoding không phù hợp | Validate JSON độc lập trước khi chạy Contract Verifier |
| Test producer đỏ do ID/timestamp khác nhau | Fixture chứa dữ liệu cố định ở trường vốn động | Dùng matcher thích hợp thay vì ép giá trị ví dụ |
| Test producer xanh nhưng consumer lỗi | Fixture mới đã thay đổi cấu trúc mà consumer cũ phụ thuộc | Chạy consumer test với stub của commit ứng viên; lên kế hoạch migration |
| Consumer test vẫn xanh sau khi sửa fixture | Stub Runner lấy artifact cũ, pipeline không đóng gói lại stub | Ghim version/commit, kiểm tra log tải artifact và nội dung stub |
| Nhiều contract đột nhiên đổi kết quả | Một fixture dùng chung đã bị sửa | Tìm tất cả contract tham chiếu và xem xét tách file theo tình huống |
| Binary body sai kích thước/nội dung | Dùng cơ chế đọc text thay vì byte hoặc xử lý encoding sai | Dùng cơ chế file-as-bytes phù hợp, đối chiếu checksum/Content-Type |
| Message không xuất hiện dù JSON hợp lệ | Thiếu cấu hình trigger, broker/test binder, destination hoặc serializer | Kiểm tra test base, messaging adapter và contract outputMessage |
| Review khó phát hiện breaking change | Diff chỉ thấy file JSON dài, không có mô tả thay đổi API | Yêu cầu mô tả field/semantics thay đổi và bằng chứng consumer verification |

## 15. Mẫu quy tắc review trong nhóm

Một đội phát triển nhiều consumer có thể đặt quy tắc:

- **Mỗi fixture có tên theo kịch bản** và nằm gần contract liên quan.
- **Mỗi PR sửa fixture** phải nêu rõ phần nào là thay đổi test data, phần nào là thay đổi hành vi công khai của API/message.
- **Đường dẫn tham chiếu** phải được kiểm tra trong build, kể cả trên hệ thống file phân biệt chữ hoa/thường.
- **Không dùng dữ liệu production nhạy cảm** trong fixture; thay bằng dữ liệu mẫu giữ nguyên cấu trúc cần kiểm tra.
- **Không sửa fixture dùng chung** nếu chưa xem tất cả contract và consumer bị ảnh hưởng.
- **Giá trị động cần matcher phù hợp**; không cố định timestamp, UUID, generated ID chỉ để test xanh.
- **Stub ứng viên phải được tạo lại** khi contract hoặc fixture đổi, và consumer test phải dùng đúng artifact ứng viên.
- **CI lưu được bằng chứng**: phiên bản/commit, generated test report, tọa độ stub và kết quả kiểm tra consumer.

Các quy tắc này biến tệp body thành một phần của hợp đồng có khả năng review và truy vết, thay vì một tập dữ liệu phụ không ai kiểm soát.

## 16. Bài thực hành: tách JSON và bắt một breaking change

**Bối cảnh:** Inventory Service trả tồn kho theo kho hàng; Checkout Service kiểm tra trường `available` để quyết định tạo đơn.

### Phần A — Refactor nhưng không đổi hành vi

1. Tạo contract HTTP GET với response JSON lồng nhau, ban đầu viết inline.
2. Chuyển đối tượng response vào `payloads/stock-available.json`.
3. Đổi contract Groovy sang `body(file('payloads/stock-available.json'))` hoặc YAML sang `bodyFromFile: payloads/stock-available.json`.
4. Chạy generated producer test và xác nhận output/stub vẫn mô tả cùng hành vi như trước.
5. Kiểm tra rằng consumer test với stub mới vẫn đọc được `available: true`.

**Kết quả mong đợi:** Cấu trúc dự án dễ đọc hơn, nhưng hành vi giao tiếp và các kết quả kiểm thử không đổi.

### Phần B — Phát hiện thay đổi phá tương thích

1. Sửa JSON fixture: bỏ `available`, thay bằng `inStock`.
2. Đồng bộ producer để trả field mới và chạy generated producer test.
3. Đóng gói stub ứng viên từ đúng commit này.
4. Chạy Checkout Service hiện tại với Stub Runner trỏ đến stub ứng viên.
5. Ghi nhận consumer test thất bại ở assertion hoặc bước xử lý dữ liệu phụ thuộc `available`.

**Kết quả mong đợi:** Producer có thể thỏa contract mới trong khi consumer cũ không tương thích. Người học phải giải thích được vì sao việc đổi một tệp tài nguyên cũng có thể là một breaking change.

### Phần C — Sửa theo cách có giai đoạn

1. Cho producer và fixture tạm thời trả **cả** `available` và `inStock`.
2. Kiểm thử consumer cũ với stub của phiên bản mở rộng.
3. Nâng consumer để đọc `inStock` và chạy lại kiểm chứng.
4. Chỉ loại bỏ `available` khi các consumer đang được hỗ trợ không còn phụ thuộc nó.

**Đầu ra cần nộp:** sơ đồ thư mục, contract sau refactor, fixture JSON hợp lệ, generated producer test report, stub coordinate ứng viên, kết quả consumer test và giải thích về quyết định tương thích.

## 17. Checklist trước khi hợp nhất PR

- [ ] Contract mô tả rõ request, response/message và lý do tham chiếu body file.
- [ ] Tệp fixture có tên mang ý nghĩa nghiệp vụ, nằm ở vị trí được plugin đọc được.
- [ ] Tệp JSON/XML/text/binary hợp lệ, dùng encoding và cách đọc phù hợp.
- [ ] Đường dẫn khớp chính xác trên môi trường CI, không phụ thuộc máy cá nhân.
- [ ] Các trường động được xác nhận bằng matcher hoặc chiến lược phù hợp.
- [ ] Fixture không chứa token, dữ liệu khách hàng thật hoặc thông tin bí mật.
- [ ] Tất cả contract dùng chung fixture đã được đánh giá tác động.
- [ ] Generated producer test thực sự chạy và kiểm tra nội dung body.
- [ ] Artifact stub mới phản ánh đúng fixture từ commit ứng viên.
- [ ] Consumer test chạy với đúng stub ứng viên trước khi phát hành API/message thay đổi.

## 18. Câu hỏi tự kiểm tra

**1. Vì sao tách body JSON ra file làm contract dễ bảo trì hơn?**

Vì DSL tập trung mô tả hành vi như method, URL, status và matcher, trong khi JSON/XML lớn được format, validate, so sánh và review riêng. Tuy vậy, contract và fixture phải được quản lý như một thay đổi thống nhất.

**2. Khác biệt cơ bản giữa Groovy `body(file(...))` và YAML `bodyFromFile` là gì?**

Đó là hai cú pháp theo hai DSL để biểu đạt cùng ý tưởng lấy body từ tài nguyên. Cần dùng đúng cú pháp và quy tắc đường dẫn của phiên bản SCC tương ứng.

**3. Tách body thành file có làm cho ID sinh ngẫu nhiên được bỏ qua khi kiểm chứng không?**

Không. Giá trị trong file vẫn là dữ liệu mẫu. Nếu cần chấp nhận giá trị động, phải thiết kế matcher theo những điều kiện hợp lệ và kiểm tra cách generated test/stub xử lý matcher đó.

**4. Vì sao sửa một JSON fixture có thể là breaking change?**

Vì fixture tham gia tạo generated producer test và stub; đổi tên hoặc bỏ trường có thể làm thay đổi hợp đồng API/message mà consumer đang phụ thuộc. Producer test có thể xanh với contract mới nhưng consumer cũ vẫn lỗi.

**5. Điều gì chứng minh consumer đã kiểm tra chính thay đổi mới?**

Consumer test sử dụng **stub artifact ứng viên được sinh từ đúng contract và fixture của commit cần kiểm tra**, có version/commit truy vết được, thay vì dùng stub cũ từ cache.

---

**Điểm cần nhớ:** Tách dữ liệu body lớn ra **tệp tài nguyên** giúp contract Spring Cloud Contract rõ ràng và dễ review. Nhưng file JSON/XML/message là **một phần của cam kết giao tiếp**, nên mọi thay đổi ở fixture vẫn phải đi qua chuỗi **contract → generated producer test → stub ứng viên → consumer verification → CI**.

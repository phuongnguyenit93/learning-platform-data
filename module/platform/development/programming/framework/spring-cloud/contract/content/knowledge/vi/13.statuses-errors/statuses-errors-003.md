# Hợp đồng cho dữ liệu không tồn tại và yêu cầu không hợp lệ

## 1. Vì sao phải viết contract cho các nhánh lỗi?

Giả sử một ứng dụng web gọi `Order Service` để hiển thị đơn hàng. Ở trường hợp thành công, producer trả HTTP `200 OK` và JSON có `orderId`, `status`, `totalAmount`. Nếu đơn hàng không tồn tại, consumer cần biết phải hiển thị “Không tìm thấy đơn hàng”, cho phép người dùng quay lại danh sách hay thử một mã khác. Nếu yêu cầu tạo đơn thiếu thông tin bắt buộc, consumer cần chỉ ra đúng trường phải sửa.

Hai hành vi lỗi này là một phần **giao diện công khai** chứ không chỉ là chi tiết exception nội bộ. Một thay đổi từ HTTP `404` sang `500`, từ field `code` sang `errorCode`, hoặc từ danh sách lỗi validation sang một chuỗi khó phân tích có thể phá vỡ consumer dù unit test của producer vẫn đạt.

**Spring Cloud Contract** biến các kỳ vọng giữa producer và consumer thành Groovy/YAML DSL. Công cụ sinh kiểm thử phía producer, tạo stub để consumer kiểm thử với Stub Runner và cho phép tích hợp các bước đó vào CI. Bài này thuộc chương **Trạng thái và lỗi**, tập trung vào:

- **Dữ liệu không tồn tại:** Một resource được định danh hợp lệ nhưng không tìm thấy, thường được mô tả bằng HTTP `404 Not Found`.
- **Yêu cầu không hợp lệ:** Request có cú pháp, tham số hoặc nội dung không đáp ứng giao diện công bố, thường được mô tả bằng HTTP `400 Bad Request`; một số API chọn `422 Unprocessable Content` cho trường hợp nội dung có cú pháp đúng nhưng không thể xử lý về ngữ nghĩa.

Sau khi học xong, bạn có thể chọn nhánh lỗi cần bảo vệ, định nghĩa một **error response contract** ổn định, viết contract HTTP bằng Groovy/YAML, chuẩn bị producer verification và phân biệt loại sai lệch mà contract test bắt được so với loại cần kiểm thử khác.

> **Thông điệp chính:** Đừng chỉ lập hợp đồng cho `2xx`. Consumer thường đưa ra những quyết định quan trọng dựa trên **status, mã lỗi và cấu trúc body** của các response `4xx`.

## 2. Đầu tiên, phân biệt “không tồn tại” và “không hợp lệ”

Xét hai request:

~~~http
GET /api/orders/ORD-404 HTTP/1.1
Accept: application/json
~~~

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json

{
  "customerId": "",
  "items": [
    { "sku": "BOOK-1", "quantity": 1 }
  ]
}
~~~

Request thứ nhất có phương thức và đường dẫn **hợp lệ**, nhưng không có đơn hàng `ORD-404`. Request thứ hai có JSON hợp lệ về **cú pháp**, nhưng `customerId` là chuỗi rỗng trong khi API yêu cầu mã khách hàng không rỗng. Chúng cần **hai kịch bản riêng**.

| Thuộc tính | Dữ liệu không tồn tại | Yêu cầu không hợp lệ |
| --- | --- | --- |
| Ví dụ | `GET /api/orders/ORD-404` | `POST /api/orders` với `customerId: ""` |
| Vấn đề | Không tìm thấy resource theo định danh | Request vi phạm quy tắc tiếp nhận |
| Status minh họa | `404 Not Found` | `400 Bad Request` |
| Mã lỗi ứng dụng | `ORDER_NOT_FOUND` | `VALIDATION_FAILED` |
| Consumer xử lý | Hiển thị “không tìm thấy”, điều hướng hoặc yêu cầu ID khác | Hiển thị lỗi nhập liệu, giữ dữ liệu form |
| Fixture producer | Resource được yêu cầu **không tồn tại** | Request cố ý vi phạm quy tắc |
| Trọng tâm contract | Status, error code, resource/path theo cam kết | Status, error code và chi tiết trường sai nếu consumer dùng |

**Không phải mọi lỗi đều tương đương `400` hoặc `404`.** Một API có thể sử dụng `409 Conflict` khi trạng thái tài nguyên không cho phép thao tác, `401 Unauthorized` khi chưa có xác thực thích hợp, `403 Forbidden` khi không được phép hoặc `422 Unprocessable Content` theo chính sách đã công bố. Hãy chọn dựa trên **ngữ nghĩa HTTP và giao diện thực tế**, không đổi status tùy tiện chỉ để test xanh.

## 3. Thiết kế error envelope ổn định trước khi viết DSL

Một body lỗi dễ sử dụng nên có cấu trúc đủ ổn định để consumer **ra quyết định**. Ví dụ hai phản hồi tự thiết kế cho `Order Service`:

**Không tìm thấy đơn hàng:**

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json

{
  "code": "ORDER_NOT_FOUND",
  "message": "Order not found"
}
~~~

**Yêu cầu không hợp lệ:**

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "field": "customerId",
      "code": "REQUIRED"
    }
  ]
}
~~~

Các trường trong ví dụ:

| Trường | Kiểu JSON | Ý nghĩa |
| --- | --- | --- |
| `code` | String | Mã lỗi ứng dụng ổn định để consumer phân nhánh |
| `message` | String | Văn bản giải thích cho người dùng hoặc vận hành; có thể đổi theo ngôn ngữ |
| `errors` | Array | Các vi phạm validation có thể xử lý theo từng trường |
| `errors[].field` | String | Tên trường request không hợp lệ |
| `errors[].code` | String | Mã lỗi validation ổn định, ví dụ `REQUIRED` hoặc `INVALID_FORMAT` |

Đây là **schema minh họa do nhóm dự án tự lựa chọn**; Spring Cloud Contract không áp đặt tên `code`, `message` hay `errors`. Nếu dự án dùng Spring `ProblemDetail`/Problem Details theo RFC 9457, phải viết contract theo **schema đó** và media type phù hợp, chứ không ghép hai dạng response vào một hợp đồng thiếu nhất quán.

### 3.1. Consumer thực sự cần những field nào?

Không phải field nào nhìn thấy trong JSON cũng cần ràng buộc cứng:

- Nếu consumer dựa vào `code: ORDER_NOT_FOUND`, hãy giữ mã lỗi đó ổn định.
- Nếu consumer hiển thị localized message tự dịch, chữ tiếng Anh `Order not found` có thể chỉ là dữ liệu mô tả, **không nên mặc định là cam kết bất biến**.
- Nếu UI đánh dấu ô nhập `customerId`, phải đảm bảo đường dẫn và tên field validation còn đáp ứng cơ chế liên kết của form.
- Nếu `requestId` hoặc timestamp được server sinh, nên kiểm tra định dạng thay vì cố định một ID hoặc thời điểm ngẫu nhiên.
- Tránh đưa stack trace, SQL error, chi tiết database hoặc thông tin nhạy cảm vào API lỗi công khai.

Một cấu trúc lỗi tốt thường thống nhất giữa các endpoint, nhưng contract của từng tương tác vẫn phải mô tả **status và những field mà consumer dùng cho tình huống cụ thể**.

## 4. Hợp đồng Groovy cho dữ liệu không tồn tại: HTTP 404

Giả sử consumer gọi endpoint:

~~~http
GET /api/orders/ORD-404 HTTP/1.1
Accept: application/json
~~~

Producer cam kết trả `404` cùng `ORDER_NOT_FOUND`. Tạo tệp minh họa:

~~~text
src/test/resources/contracts/orders/get_order_not_found.groovy
~~~

Nội dung Groovy DSL:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_order_not_found')
    description('Không tìm thấy đơn hàng theo mã được yêu cầu')

    request {
        method GET()
        urlPath('/api/orders/ORD-404')
        headers {
            accept(applicationJson())
        }
    }

    response {
        status NOT_FOUND()
        headers {
            contentType(applicationJson())
        }
        body(
            code: 'ORDER_NOT_FOUND',
            message: 'Order not found'
        )
    }
}
~~~

**Ý nghĩa của hợp đồng:**

1. `request.method` và `urlPath` xác định request mà consumer gửi; đây không phải trường hợp route sai.
2. `NOT_FOUND()` biểu diễn HTTP status `404`.
3. `Content-Type: application/json` bảo đảm producer công bố định dạng response như đã thỏa thuận.
4. `body.code` là mã lỗi giúp consumer xử lý một cách có cấu trúc.
5. `body.message` có trong mẫu vì API minh họa đã cam kết nó; nếu message không cần chính xác từng chữ, hãy giảm mức ràng buộc phù hợp khi chuyển sang triển khai thực tế.

Nếu producer trả `200` kèm body `{"code":"ORDER_NOT_FOUND"}` thay vì `404`, generated contract test phải phát hiện sai **status**. Nếu producer trả `404` nhưng bỏ `code`, test cũng cần phát hiện sai lệch ở **response body**.

### 4.1. Đặt tên để dễ điều tra lỗi

Tên `get_order_not_found` diễn tả:

- Hành vi: `get_order`.
- Kịch bản: `not_found`.
- Không gắn tên vào lớp Java nội bộ, vì contract bảo vệ giao diện HTTP chứ không bảo vệ tên method controller.

Tệp có thể nằm trong nhóm `orders/` hoặc thư mục theo consumer; quan trọng là plugin biết đường dẫn nguồn contract và CI thực thi các test được sinh.

## 5. Cùng hợp đồng 404 bằng YAML DSL

Nếu dự án chọn YAML DSL, viết một contract có ý nghĩa tương đương:

~~~yaml
name: get_order_not_found
description: Không tìm thấy đơn hàng theo mã được yêu cầu
request:
  method: GET
  urlPath: /api/orders/ORD-404
  headers:
    Accept: application/json
response:
  status: 404
  headers:
    Content-Type: application/json
  body:
    code: ORDER_NOT_FOUND
    message: Order not found
~~~

Đối chiếu Groovy và YAML:

| Thành phần | Groovy DSL | YAML DSL |
| --- | --- | --- |
| Request method | `method GET()` | `method: GET` |
| Request path | `urlPath('/api/orders/ORD-404')` | `urlPath: /api/orders/ORD-404` |
| Error status | `status NOT_FOUND()` | `status: 404` |
| Media type | `contentType(applicationJson())` | `Content-Type: application/json` |
| Error code | `body(code: 'ORDER_NOT_FOUND')` | `body:` rồi `code: ORDER_NOT_FOUND` |

Đừng bật đồng thời một file Groovy và một file YAML có cùng tên/hành vi trong cùng source contract chỉ vì muốn “cho chắc”. Như vậy có thể tạo các mapping hoặc generated tests trùng lặp. Với một dự án thật, chọn một định dạng hoặc quản lý tình huống trùng nhau có chủ đích.

## 6. Hợp đồng Groovy cho yêu cầu không hợp lệ: HTTP 400

Giả sử API tạo đơn hàng yêu cầu `customerId` là String không rỗng. Consumer gửi JSON **đúng cú pháp nhưng không đáp ứng validation**:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json
Accept: application/json

{
  "customerId": "",
  "items": [
    { "sku": "BOOK-1", "quantity": 1 }
  ]
}
~~~

Producer cam kết trả `400 Bad Request` và một lỗi có mã `VALIDATION_FAILED`, chỉ rõ `customerId`. Viết contract:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('create_order_missing_customer_id')
    description('Từ chối đơn hàng có customerId rỗng')

    request {
        method POST()
        urlPath('/api/orders')

        headers {
            contentType(applicationJson())
            accept(applicationJson())
        }

        body(
            customerId: '',
            items: [
                [sku: 'BOOK-1', quantity: 1]
            ]
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
                [
                    field: 'customerId',
                    code: 'REQUIRED'
                ]
            ]
        )
    }
}
~~~

### 6.1. Điểm cần kiểm tra

- `request.body.customerId` là chuỗi rỗng, không phải field bị thiếu hoặc giá trị `null`.
- `items` là **JSON array** chứa một object, được khai báo bằng list chứa map.
- `status BAD_REQUEST()` tương ứng HTTP `400`.
- `errors` là list: consumer có thể lặp và hiển thị lỗi cho từng trường.
- `errors[0].field` và `errors[0].code` là những gì UI có thể dùng để tô sáng ô nhập.

Không nên mô tả đơn hàng hợp lệ bằng contract này rồi chỉ thay `status` thành `400`: khi đó test không chứng minh producer từ chối **đúng loại request không hợp lệ**.

### 6.2. Lỗi “thiếu trường” khác lỗi “chuỗi rỗng”

Ba request khác nhau:

~~~json
{"items":[{"sku":"BOOK-1","quantity":1}]}
~~~

~~~json
{"customerId":null,"items":[{"sku":"BOOK-1","quantity":1}]}
~~~

~~~json
{"customerId":"","items":[{"sku":"BOOK-1","quantity":1}]}
~~~

Nếu API cùng trả mã `REQUIRED` cho cả ba thì có thể viết những contract riêng cho các tình huống consumer thực sự phụ thuộc. Nhưng không được mặc định mọi framework validation đều trả **cùng response** cho field thiếu, null và chuỗi rỗng. Hành vi thực tế phụ thuộc DTO, validation annotation, exception mapping và chính sách lỗi của producer.

## 7. Cùng hợp đồng 400 bằng YAML DSL

Biểu diễn YAML của tình huống `customerId` rỗng:

~~~yaml
name: create_order_missing_customer_id
description: Từ chối đơn hàng có customerId rỗng
request:
  method: POST
  urlPath: /api/orders
  headers:
    Content-Type: application/json
    Accept: application/json
  body:
    customerId: ""
    items:
      - sku: BOOK-1
        quantity: 1
response:
  status: 400
  headers:
    Content-Type: application/json
  body:
    code: VALIDATION_FAILED
    errors:
      - field: customerId
        code: REQUIRED
~~~

Chú ý cách biểu diễn:

- `customerId: ""` là String rỗng có chủ đích; bỏ dấu nháy và bỏ giá trị có thể khiến YAML hiểu thành null.
- `items` và `errors` đều là array. Dấu `-` biểu diễn phần tử của YAML sequence.
- Đừng thay `errors` bằng một object đơn nếu client đang xử lý `List<ValidationError>`.
- Các chuỗi trông giống boolean, số hoặc null nên được trích dẫn khi cần giữ **kiểu String**.

Nếu `errors` có nhiều phần tử, thứ tự các lỗi có thể phụ thuộc trình tự validation của framework. Không nên ràng buộc một thứ tự cụ thể trừ khi API thật sự cam kết thứ tự đó; nếu cần, chọn matcher/kiểm thử phù hợp để tránh test không ổn định.

## 8. Request sai cú pháp JSON: một trường hợp 400 khác

Yêu cầu vi phạm validation khác với yêu cầu **không parse được**. Ví dụ:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json

{"customerId": "CUS-7",
~~~

Body không phải JSON hợp lệ vì thiếu ký tự đóng. Producer có thể từ chối ngay ở tầng HTTP message converter, trước khi vào controller hoặc Bean Validation.

Nếu consumer cần phân biệt lỗi cú pháp, có thể thiết kế response:

~~~json
{
  "code": "MALFORMED_JSON"
}
~~~

Một contract minh họa bằng Groovy:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('create_order_malformed_json')

    request {
        method POST()
        urlPath('/api/orders')

        headers {
            contentType(applicationJson())
        }

        // Chuỗi body sai cú pháp JSON có chủ đích
        body('{"customerId": "CUS-7",')
    }

    response {
        status BAD_REQUEST()
        headers {
            contentType(applicationJson())
        }
        body(
            code: 'MALFORMED_JSON'
        )
    }
}
~~~

**Điều kiện quan trọng:** Contract này chỉ xanh nếu producer **thực sự có cơ chế xử lý lỗi parse JSON** và trả đúng schema `MALFORMED_JSON`. Nếu Spring Boot trả cấu trúc lỗi mặc định khác, đừng khẳng định code trên sẽ chạy xanh ngay. Cần thiết lập exception handling theo giao diện đã thống nhất hoặc điều chỉnh contract dựa trên hành vi thực được công bố.

Nên phân biệt rõ trong thiết kế:

| Lỗi | Ví dụ | Xảy ra ở đâu? |
| --- | --- | --- |
| JSON sai cú pháp | `{"customerId": "CUS-7",` | HTTP parser/message converter |
| Sai kiểu field | `{"quantity": "abc"}` khi DTO yêu cầu number | Deserialize/type conversion |
| Vi phạm validation | `{"customerId": ""}` khi không cho phép rỗng | Bean Validation hoặc logic nghiệp vụ |
| Tài nguyên không tồn tại | `GET /api/orders/ORD-404` | Lookup resource |
| Xung đột trạng thái | Hủy một đơn đã hoàn tất | Domain/business policy, có thể là `409` |

Cùng một HTTP status có thể phục vụ nhiều loại lỗi. **Error code ứng dụng** giúp consumer phân biệt nếu nghiệp vụ yêu cầu.

## 9. Chọn 400, 404, 409 hay 422 cho đúng mục đích

Không nên sử dụng status theo thói quen mà không thống nhất ngữ nghĩa.

| Status | Ý nghĩa tổng quát | Ví dụ |
| --- | --- | --- |
| `400 Bad Request` | Server không thể/không muốn xử lý request do vấn đề được quy cho client, như cú pháp hoặc tham số không hợp lệ | JSON sai cú pháp, field bắt buộc rỗng theo chính sách API |
| `404 Not Found` | Server không tìm thấy biểu diễn hiện tại của tài nguyên được yêu cầu hoặc không muốn tiết lộ sự tồn tại | Đơn hàng với ID hợp lệ nhưng không tồn tại |
| `409 Conflict` | Request xung đột với trạng thái hiện tại của tài nguyên | Hai thao tác cập nhật cùng phiên bản, trạng thái không cho phép sửa |
| `422 Unprocessable Content` | Nội dung có media type và cú pháp hiểu được nhưng không thể xử lý theo chỉ dẫn chứa trong đó | API chọn `422` cho một số lỗi ngữ nghĩa/validation |
| `401 Unauthorized` | Request cần xác thực hợp lệ | Không có credential phù hợp |
| `403 Forbidden` | Server hiểu request nhưng từ chối thực hiện | Tài khoản không được phép thao tác |
| `500 Internal Server Error` | Lỗi phía server, không phải một cách biểu diễn thông thường cho input sai | Lỗi hạ tầng/bug không được xử lý |

**Quan trọng:** Không có luật cứng rằng mọi validation error đều phải là `422` hoặc mọi request không hợp lệ đều phải là `400`. Dự án cần chọn một chính sách nhất quán, công bố cho consumer và đưa status tương ứng vào contract.

Với resource thuộc về tenant khác, chính sách bảo mật có thể quyết định **trả `404` để không tiết lộ sự tồn tại** thay vì `403`. Contract phải được thiết kế cùng chính sách xác thực/phân quyền, không tự ép mọi trường hợp “có resource nhưng không có quyền” thành `403`.

### 9.1. 404 do không có route khác 404 do không có resource

Nếu `GET /api/orders/ORD-404` được route đúng tới controller nhưng không có bản ghi, đó là lỗi **dữ liệu không tồn tại**.

Nếu consumer gọi nhầm `GET /api/orderz/ORD-123`, `404` có thể do **không có endpoint**. Hai tình huống đều có thể cho `404` nhưng **không nhất thiết dùng cùng JSON error envelope**, vì xử lý lỗi tuyến đường và xử lý lỗi domain có thể là hai luồng khác nhau trong Spring MVC.

Contract cho tài nguyên không tồn tại nên dùng **path hợp lệ** và fixture bảo đảm resource thực sự không tồn tại. Đừng viết nhầm path rồi tưởng mình đang kiểm chứng nghiệp vụ “không tìm thấy”.

## 10. Nếu sử dụng Problem Details thay cho error envelope tự thiết kế

Hệ sinh thái Spring hỗ trợ dạng response **Problem Details** (RFC 9457; kế thừa RFC 7807), ví dụ:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "No order matches the supplied identifier",
  "instance": "/api/orders/ORD-404"
}
~~~

Những field phổ biến gồm `type`, `title`, `status`, `detail`, `instance`. API có thể bổ sung extension members theo quy ước của tổ chức.

Với cách này, hợp đồng phải dùng `application/problem+json` nếu đó là media type producer đã công bố:

~~~groovy
response {
    status NOT_FOUND()
    headers {
        header('Content-Type', 'application/problem+json')
    }
    body(
        type: 'https://api.example.test/problems/order-not-found',
        title: 'Order not found',
        status: 404,
        detail: 'No order matches the supplied identifier',
        instance: '/api/orders/ORD-404'
    )
}
~~~

**Đây là lựa chọn thay thế**, không phải body bắt buộc của Spring Cloud Contract. Các ví dụ chính của bài này sử dụng schema `code/errors` để minh họa dễ hơn cách consumer xử lý form. Khi chọn Problem Details, cần thống nhất field mở rộng hoặc URI `type` nào đóng vai trò **mã lỗi máy đọc được**.

Nếu `detail` có ngôn ngữ hoặc chứa ID thay đổi, nên cân nhắc matcher thay vì cố định toàn bộ câu. Hãy tránh phụ thuộc vào wording của message khi consumer thực ra chỉ cần mã lỗi ổn định.

## 11. Producer phải làm gì để generated tests có ý nghĩa?

Spring Cloud Contract có thể sinh kiểm thử từ DSL, nhưng **không tự tạo hành vi xử lý exception** cho ứng dụng. Producer phải thật sự trả status/header/body như contract.

Một luồng xử lý đơn giản:

~~~mermaid
flowchart TD
    R["HTTP request"] --> V{"Request hợp lệ?"}
    V -- "Không" --> B["400 + VALIDATION_FAILED"]
    V -- "Có" --> L{"Tài nguyên tồn tại?"}
    L -- "Không" --> N["404 + ORDER_NOT_FOUND"]
    L -- "Có" --> S["2xx + dữ liệu thành công"]
    B --> C["Contract test kiểm tra status + JSON body"]
    N --> C
    S --> C
~~~

Sơ đồ mang tính khái niệm. Với `POST /api/orders`, có thể không có bước lookup resource; với `GET` có path ID thì bước tìm dữ liệu phù hợp hơn. **Đừng áp cùng một chuỗi xử lý cho mọi endpoint.**

### 11.1. Ứng dụng Spring MVC cần cơ chế chuẩn hóa lỗi

Một triển khai điển hình có thể gồm:

- DTO request được đánh dấu `@Valid` và các constraint như `@NotBlank`.
- Controller chuyển thao tác nghiệp vụ sang service.
- Service ném domain exception, ví dụ `OrderNotFoundException`, khi lookup không có dữ liệu.
- `@RestControllerAdvice` chuyển exception có ý nghĩa thành response HTTP đã cam kết.
- Cơ chế xử lý lỗi parse/body hoặc validation của Spring được tùy chỉnh khi API muốn một error envelope chung.

Ví dụ ý tưởng về domain exception handler:

~~~java
@RestControllerAdvice
class ApiErrorHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<Map<String, String>> onNotFound(
            OrderNotFoundException exception) {

        return ResponseEntity
                .status(HttpStatus.NOT_FOUND)
                .body(Map.of(
                    "code", "ORDER_NOT_FOUND",
                    "message", "Order not found"
                ));
    }
}
~~~

Ví dụ này giả định ứng dụng đã định nghĩa `OrderNotFoundException` và import đúng các thành phần Spring/Java. Nó **chỉ minh họa nhánh 404**. Để contract `400` ở trên đạt, cần thêm handler hoặc response mapping cho lỗi validation, trả `VALIDATION_FAILED` cùng `errors[]`. Spring Boot không mặc định dùng một error body tùy chỉnh giống hệt các ví dụ bài học.

### 11.2. Cơ chế xử lý validation

Một DTO minh họa:

~~~java
record CreateOrderRequest(
    @NotBlank String customerId,
    @NotEmpty List<CreateOrderItem> items
) {}

record CreateOrderItem(
    @NotBlank String sku,
    @Positive int quantity
) {}
~~~

Controller phải kích hoạt validation ở nơi nhận request, ví dụ:

~~~java
@PostMapping("/api/orders")
ResponseEntity<?> create(@Valid @RequestBody CreateOrderRequest request) {
    // Thực hiện nghiệp vụ, không tự bỏ qua validation
    return ResponseEntity.status(HttpStatus.CREATED).build();
}
~~~

Khi `customerId` rỗng, Bean Validation có thể tạo lỗi `NotBlank`. Nếu API muốn chuyển thành mã `REQUIRED`, producer cần một bước **mapping mã validation nội bộ sang mã public**. Không mặc định tên annotation `NotBlank` tự động biến thành `REQUIRED` trong JSON response.

Nếu validation xảy ra tại lớp service thay vì controller, cách ngoại lệ được phát và xử lý sẽ khác. Kỳ vọng contract phải bám vào **response HTTP cuối cùng** mà consumer nhận.

## 12. Cấu hình base test class và fixture cho hai nhánh lỗi

Generated producer tests cần chạy với trạng thái **lặp lại được**, không phụ thuộc dữ liệu ngẫu nhiên.

Với contract `get_order_not_found`:

- Controller phải tồn tại ở route `GET /api/orders/{id}`.
- Mã `ORD-404` phải được hệ thống thử nghiệm coi là **không tồn tại**.
- Exception handler phải trả `404` cùng error envelope đã thỏa thuận.
- Nếu có security, test request cần đi qua chính sách xác thực phù hợp hoặc thiết lập principal được phép.

Với contract `create_order_missing_customer_id`:

- Request JSON phải parse thành đối tượng đầu vào.
- Constraint `customerId` rỗng phải được kích hoạt.
- Handler phải trả `400`, mã `VALIDATION_FAILED`, và một phần tử `errors[]` phản ánh `customerId`.
- Không được vô tình cho controller chấp nhận request mà bỏ qua validation trong test slice.

### 12.1. Ví dụ khung base class với MockMvc

Trong một dự án Spring MVC dùng JUnit 5, base class có thể bắt đầu như sau:

~~~java
@WebMvcTest(OrderController.class)
@Import(ApiErrorHandler.class)
abstract class ContractVerifierBase {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderQuery orderQuery;

    @BeforeEach
    void setUp() {
        given(orderQuery.findById("ORD-404"))
            .willReturn(Optional.empty());

        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
~~~

Đây là **khung minh họa**, không phải lớp Java độc lập có thể dán vào mọi dự án mà không bổ sung package/import và các class ứng dụng. Nó giả định `OrderQuery.findById` trả `Optional`, controller chuyển `Optional.empty()` thành `OrderNotFoundException` và `ApiErrorHandler` xử lý exception. Cách dùng `@MockitoBean` phù hợp với Spring Framework 6.2+/Spring Boot tương ứng; các dự án cũ có thể cần `@MockBean`. Cấu hình Spring Boot, Spring Cloud và Spring Cloud Contract phải tương thích với nhau.

Với nhánh `400` dựa vào `@Valid`, một `@WebMvcTest` được thiết lập đúng controller, validator và exception handler có thể xác minh cả pipeline MVC. Nếu unit test mock thẳng vào response mà bỏ qua controller/validation thật, hãy đánh giá mức độ tin cậy: test có thể xanh nhưng không chứng minh middleware xử lý request không hợp lệ đúng cách.

## 13. Test cần bảo vệ điều gì trong response lỗi?

### 13.1. Status và mã lỗi là hai lớp độc lập

Hợp đồng không nên chỉ kiểm tra mã lỗi trong JSON:

~~~json
{"code": "ORDER_NOT_FOUND"}
~~~

Nếu producer trả response đó với `200`, client có thể chạy vào nhánh thành công. Vì vậy status HTTP cần được kiểm chứng độc lập.

Ngược lại, chỉ kiểm tra `404` mà bỏ `code` có thể làm producer đổi schema lỗi một cách vô ý khiến client phân tích body hỏng.

### 13.2. Có nên kiểm tra message chính xác?

Một mã lỗi có thể cố định nhưng message có thể được bản địa hóa:

~~~json
{
  "code": "ORDER_NOT_FOUND",
  "message": "Không tìm thấy đơn hàng"
}
~~~

Nếu consumer hiển thị `message` nguyên văn theo hợp đồng, cần kiểm tra sự hiện diện/kiểu và chính sách ngôn ngữ. Nếu consumer dùng `code` để tự hiển thị bản dịch, việc cố định đúng từng chữ của `message` sẽ tạo ra test quá chặt.

Có thể giảm mức ràng buộc bằng matcher. Ví dụ:

~~~groovy
response {
    status NOT_FOUND()
    headers {
        contentType(applicationJson())
    }

    body(
        code: 'ORDER_NOT_FOUND',
        message: 'Order not found'
    )

    bodyMatchers {
        jsonPath('$.message', byType())
    }
}
~~~

Trong ví dụ này, `message` được kiểm tra **là String** thay vì buộc bằng một câu cụ thể, còn `code` vẫn giữ giá trị cố định. Tuy nhiên, nếu contract thật sự cam kết một wording nguyên văn, `byType()` là quá lỏng; hãy chọn matcher dựa trên nhu cầu consumer.

### 13.3. Danh sách lỗi validation và thứ tự phần tử

Giả sử request sai cả `customerId` và `items[0].quantity`. Response có thể chứa:

~~~json
{
  "code": "VALIDATION_FAILED",
  "errors": [
    {"field": "customerId", "code": "REQUIRED"},
    {"field": "items[0].quantity", "code": "POSITIVE"}
  ]
}
~~~

Nếu thứ tự lỗi **không được API cam kết**, producer có thể trả hai phần tử theo thứ tự khác nhau. Một contract cố định toàn bộ list theo thứ tự có thể thất bại dù consumer vẫn xử lý tốt.

Chiến lược:

1. Với bài học ban đầu, viết **mỗi contract một lỗi đơn giản**, ví dụ chỉ `customerId` rỗng.
2. Nếu consumer cần hiển thị nhiều lỗi, thiết kế contract cho array theo các thuộc tính quan trọng; hiểu rõ matcher/list semantics của phiên bản tool.
3. Có thể bổ sung integration test kiểm tra **tập field/code** mà không phụ thuộc thứ tự nếu đó mới là cam kết thực sự.
4. Tránh regex quá rộng làm mất khả năng phát hiện field/code lỗi.

## 14. Stub Runner giúp consumer thử các nhánh lỗi như thế nào?

Stub được sinh từ contract giúp consumer thử hành vi mà không cần chạy producer thật. Với hai contract ví dụ, Stub Runner có thể phục vụ các tương tác:

| Request từ consumer | Stub theo contract | Consumer nên xử lý |
| --- | --- | --- |
| `GET /api/orders/ORD-404` | `404` + `ORDER_NOT_FOUND` | Hiển thị trạng thái không tìm thấy |
| `POST /api/orders` với `customerId: ""` đúng matcher | `400` + `VALIDATION_FAILED` | Gắn lỗi vào form |
| Request không khớp bất kỳ stub nào | Không có response theo contract đã định nghĩa | Đây là lỗi matching; không suy ra đó là lỗi nghiệp vụ 404/400 đã mô tả |

**Quan trọng:** `404` do **WireMock không tìm thấy mapping** không tương đương với `404` có JSON `ORDER_NOT_FOUND` do contract cố tình mô tả. Consumer test nên kiểm tra **status và error body** chứ không chỉ `404`, để không nhận nhầm một stub không match là một phản hồi “không tồn tại” hợp lệ.

Khi một request dùng header hoặc body khác với contract, stub có thể không khớp. Vì vậy cần xem điều kiện matcher của `request` và kết quả stub thực tế trước khi kết luận client xử lý lỗi đúng.

### 14.1. Kiểm tra consumer xử lý chứ không chỉ nhận response

Một consumer test có ý nghĩa cần khẳng định hệ quả:

- Với `ORDER_NOT_FOUND`, UI hiển thị trạng thái “không tìm thấy” hoặc service gọi không tiếp tục xử lý đơn hàng.
- Với `VALIDATION_FAILED`, form hiển thị lỗi tại `customerId` và không chuyển trang thành công.
- Với lỗi khác, consumer không nuốt exception hoặc nhầm sang thành công.

Stub chỉ mô phỏng giao tiếp; **test consumer** phải kiểm tra code của consumer ứng xử đúng với phản hồi đó.

## 15. Đặt các hợp đồng lỗi vào CI

Luồng thông dụng:

~~~mermaid
flowchart TD
    A["Contract: 404 và 400"] --> B["Sinh generated producer tests"]
    B --> C["Chạy test với producer"]
    C --> D{"Status, headers, body đúng?"}
    D -- "Không" --> E["Chặn merge hoặc phát hành"]
    D -- "Có" --> F["Tạo stub artifact có version"]
    F --> G["Consumer CI chạy Stub Runner"]
    G --> H["Kiểm tra nhánh not-found và invalid-input"]
~~~

Ví dụ lệnh Maven cho một dự án đã cấu hình verifier plugin và base test class:

~~~bash
./mvnw -B clean verify
~~~

Hoặc với Gradle plugin và task kiểm thử tương ứng:

~~~bash
./gradlew clean build
~~~

Các lệnh này chỉ là minh họa; **không có nghĩa contract tự động được kiểm thử** nếu build thiếu plugin/dependency, nguồn contract sai hoặc generated tests bị skip.

### 15.1. Những điều CI nên bảo đảm

- Contract Groovy/YAML và fixture liên quan được quản lý trong source control.
- Có generated producer test cho cả **nhánh thành công** và **những nhánh lỗi consumer thực sự dùng**.
- Test được chạy, không chỉ sinh ra hoặc compile.
- Dữ liệu/setup khiến `ORD-404` thực sự không tồn tại, `customerId` rỗng thực sự bị chặn.
- Schema lỗi đã công bố không bị thay đổi âm thầm trong commit.
- Stub từ producer đã xác minh được phát hành với phiên bản phù hợp.
- Consumer CI thử status và error code/body; không coi WireMock unmatched request là lỗi nghiệp vụ hợp lệ.
- Các trường hợp authentication, authorization, performance, retry hoặc môi trường gateway thật được kiểm tra ở tầng thích hợp.

### 15.2. Breaking change nào contract lỗi có thể phát hiện?

| Producer đổi | Tác động consumer | Contract nên phản ứng |
| --- | --- | --- |
| `404` thành `200` khi resource không tồn tại | Consumer có thể coi lỗi là thành công | Generated test thất bại do sai status |
| `400` thành `500` khi input sai | Consumer có thể retry nhầm hoặc hiển thị lỗi hệ thống | Generated test thất bại do sai status |
| `ORDER_NOT_FOUND` thành `NOT_FOUND` | Consumer phân nhánh theo code cũ có thể lỗi | Test thất bại nếu code đã được ràng buộc |
| `errors` từ array thành String | Consumer không thể đọc theo field | Test có thể thất bại vì cấu trúc sai |
| Chỉ đổi wording `message` | Có thể tương thích nếu client không phụ thuộc wording | Chọn matcher phù hợp để tránh báo lỗi giả |
| Thêm metadata `traceId` | Thường tương thích nếu consumer bỏ qua field lạ | Không cần khóa chặt mọi trường, tùy parser consumer |

**Không đổi contract chỉ để làm build xanh** sau khi thay đổi producer. Trước hết xác định consumer nào phụ thuộc và cần giữ tương thích, migration hay phiên bản API mới.

## 16. Lỗi thường gặp khi viết contract cho 404/400

| Lỗi | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Dùng đường dẫn không tồn tại để “test resource 404” | Không kiểm tra được lookup resource thật | Dùng route hợp lệ và fixture không có bản ghi |
| Chỉ kiểm tra `404`, bỏ error body | Không bắt được thay đổi `code` mà consumer dùng | Kiểm tra status, media type và field quan trọng |
| Chỉ kiểm tra body lỗi, bỏ status | Producer có thể trả `200` với error JSON | Luôn ràng buộc status phù hợp |
| Giả định Spring Boot tự trả `VALIDATION_FAILED` | Generated test không khớp default error response | Cấu hình exception handler/schema hoặc điều chỉnh API contract |
| Coi JSON parse error và Bean Validation là cùng một nguyên nhân | Lỗi bị phân loại sai, khó xử lý | Tách contract theo loại input mà consumer cần phân biệt |
| Không kích hoạt `@Valid` | Request sai vẫn được chấp nhận trong test | Đảm bảo MVC validation được sử dụng |
| Test dùng `@WebMvcTest` nhưng quên `@RestControllerAdvice` | Nhận response lỗi mặc định khác contract | Import/cấu hình advice phù hợp |
| Dùng `errors` là object nhưng consumer mong array | Giải mã lỗi form thất bại | Giữ đúng schema list |
| Matcher cho `code` quá rộng | Không phát hiện thay đổi mã lỗi | So khớp chính xác code nghiệp vụ |
| Ràng buộc thông báo theo từng chữ không cần thiết | Đổi bản dịch làm fail test | Kiểm tra kiểu/hiện diện theo cam kết |
| Gộp mọi lỗi vào `500` | Consumer không biết sửa request | Phân loại lỗi đúng chính sách HTTP |
| Coi unmatched stub `404` là not-found hợp lệ | Consumer test xanh sai | Kiểm tra error body và xác nhận mapping |
| Dữ liệu test lệ thuộc database môi trường khác | Test không ổn định | Dùng fixture, mock hoặc test database có kiểm soát |
| Trả stack trace/SQL vào body lỗi | Rò rỉ dữ liệu nội bộ | Chuẩn hóa response công khai, log chi tiết ở server |

## 17. Bài thực hành: Catalog Service và hai tình huống thất bại

Giả sử producer `Catalog Service` cung cấp:

1. `GET /api/products/{id}` để tra cứu sản phẩm.
2. `POST /api/products` để tạo sản phẩm mới.

Consumer muốn:

- Khi không có sản phẩm `P-404`: nhận `404` với `code: PRODUCT_NOT_FOUND`.
- Khi tạo sản phẩm có `name` rỗng: nhận `400` với `code: VALIDATION_FAILED` và lỗi `field: name`, `code: REQUIRED`.

### 17.1. Nhiệm vụ

1. Viết hợp đồng Groovy tên `get_product_not_found` cho `GET /api/products/P-404`.
2. Viết hợp đồng YAML tên `create_product_missing_name` cho `POST /api/products` với JSON `{"name":"","price":350000}`.
3. Đặt `Content-Type: application/json` trong những response lỗi có JSON.
4. Chuẩn bị producer test fixture để `P-404` không tồn tại và validation bắt `name` rỗng.
5. Cố ý đổi error code hoặc status ở producer, quan sát producer verification thất bại.
6. Dùng Stub Runner để kiểm tra consumer hiển thị đúng nhánh not-found và validation.
7. Giải thích vì sao một stub trả `404` nhưng **không có body `PRODUCT_NOT_FOUND`** chưa đủ chứng minh rằng nhánh not-found đã được test đúng.

### 17.2. Gợi ý Groovy cho lỗi không tìm thấy

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_product_not_found')

    request {
        method GET()
        urlPath('/api/products/P-404')
    }

    response {
        status NOT_FOUND()
        headers {
            contentType(applicationJson())
        }
        body(
            code: 'PRODUCT_NOT_FOUND'
        )
    }
}
~~~

### 17.3. Gợi ý YAML cho input không hợp lệ

~~~yaml
name: create_product_missing_name
request:
  method: POST
  urlPath: /api/products
  headers:
    Content-Type: application/json
  body:
    name: ""
    price: 350000
response:
  status: 400
  headers:
    Content-Type: application/json
  body:
    code: VALIDATION_FAILED
    errors:
      - field: name
        code: REQUIRED
~~~

### 17.4. Câu hỏi tự đánh giá

1. Vì sao không nên dùng `GET /api/prodcts/P-404` (sai chính tả path) để kiểm tra tài nguyên không tồn tại?
2. Nếu Spring Boot trả JSON lỗi mặc định khác body contract, cần sửa ở đâu?
3. Nếu producer đổi mã `PRODUCT_NOT_FOUND` thành `ITEM_NOT_FOUND` nhưng status vẫn `404`, consumer có thể bị ảnh hưởng gì?
4. Vì sao validation error cho `name: ""` khác với lỗi JSON sai cú pháp?
5. Khi nào `422` có thể là lựa chọn phù hợp thay cho `400`?
6. Nếu response lỗi có trường `traceId` sinh ngẫu nhiên, nên ràng buộc như thế nào?
7. Contract test có tự chứng minh người dùng không được xem sản phẩm của tenant khác không?
8. Làm sao tránh một unmatched WireMock stub bị hiểu nhầm thành phản hồi not-found hợp lệ?

**Gợi ý:** Route phải hợp lệ để kiểm tra lookup; error envelope cần được triển khai thật; code lỗi là giao diện máy đọc được; `400`/`422` phụ thuộc chính sách API; dữ liệu động dùng matcher; phân quyền cần security tests; luôn kiểm tra status **cùng với** cấu trúc và mã lỗi kỳ vọng.

## 18. Checklist trước khi coi nhánh lỗi đã có hợp đồng

- [ ] Đã xác định rõ **nguyên nhân lỗi**: resource không tồn tại, request sai cú pháp, validation sai hay xung đột nghiệp vụ.
- [ ] Mỗi contract có request cụ thể tái lập được và phản hồi lỗi tương ứng.
- [ ] `404` cho dữ liệu không tồn tại được kiểm tra qua **route hợp lệ** và fixture thiếu resource.
- [ ] `400`/`422` phản ánh chính sách public API đã thống nhất, không suy đoán từ framework.
- [ ] Có HTTP status và media type đúng với response body.
- [ ] JSON error code ổn định nếu consumer dựa vào nó.
- [ ] `errors` là array khi consumer cần danh sách lỗi; field/code đúng schema.
- [ ] Không ràng buộc message quá chặt nếu consumer không phụ thuộc wording.
- [ ] Các trường optional, null và dữ liệu động được xử lý có chủ đích.
- [ ] Producer có exception handler, validation và test setup phù hợp.
- [ ] Generated producer tests thực sự được **sinh và chạy** trong build.
- [ ] Consumer tests kiểm tra cả status, error body và hành vi xử lý lỗi.
- [ ] CI không phát hành stub/producer sau khi verification thất bại.
- [ ] Không đưa stack trace hoặc dữ liệu nhạy cảm vào lỗi công khai.
- [ ] Các chính sách security, authorization, retry hoặc resilience được kiểm tra ở tầng phù hợp.

## 19. Tài liệu tham khảo

- [Spring Cloud Contract – HTTP Contracts](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/http.html): DSL cho status, headers, request và response body.
- [Spring Cloud Contract – Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): cấu trúc Groovy/YAML, generated producer tests và stub.
- [Spring Cloud Contract – Dynamic Properties](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/dsl-dynamic-properties.html): matcher cho các trường response biến đổi.
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): ngữ nghĩa HTTP status, bao gồm 400, 404 và 409.
- [RFC 9457 – Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html): định dạng lỗi chuẩn hóa tùy chọn.

**Ghi nhớ:** **Không tìm thấy tài nguyên** và **yêu cầu không hợp lệ** là hai giao tiếp lỗi cần hợp đồng riêng. Kiểm tra **đúng request, HTTP status, Content-Type và error body mà consumer sử dụng**. Groovy/YAML DSL chỉ mô tả cam kết; producer phải triển khai và vượt qua generated tests, còn consumer dùng stub/Stub Runner để chứng minh cách xử lý lỗi. Khi các bước này chạy trong CI, những thay đổi không tương thích ở nhánh lỗi cũng được phát hiện trước khi phát hành.

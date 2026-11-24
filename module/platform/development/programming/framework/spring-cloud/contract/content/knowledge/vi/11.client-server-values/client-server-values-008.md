# Tham chiếu dữ liệu request trong response khi được hỗ trợ

## 1. Tình huống: response cần phản ánh chính request đã nhận

Hãy xét một dịch vụ cung cấp API tiếp nhận lệnh. Consumer gửi:

~~~http
POST /api/requests?region=HCM HTTP/1.1
Content-Type: application/json
X-Request-ID: REQ-123

{
  "customerId": "CUS-7",
  "quantity": 2
}
~~~

Producer cần phản hồi:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
X-Request-ID: REQ-123

{
  "customerId": "CUS-7",
  "quantity": 2,
  "region": "HCM",
  "requestId": "REQ-123",
  "accepted": true
}
~~~

Một số giá trị response như `accepted: true` là cố định trong tình huống này. Nhưng `customerId`, `quantity`, `region` và `requestId` phải đến từ **chính request đã được gửi**. Nếu consumer gửi `CUS-8`, một stub phản hồi cố định `CUS-7` có thể làm test consumer thất bại hoặc che giấu việc client xử lý sai dữ liệu.

**Spring Cloud Contract** hỗ trợ tham chiếu dữ liệu request trong response đối với các kịch bản HTTP và cơ chế sinh stub phù hợp. Trong **Groovy DSL**, ta dùng `fromRequest()`; trong **YAML DSL**, ta dùng biểu thức **Handlebars** `{{{ ... }}}`. Các giá trị này phục vụ hai phía của vòng đời hợp đồng: generated test kiểm tra hành vi producer; stub sử dụng request lúc chạy để tạo response tương ứng cho consumer.

Bài học thuộc chương **Giá trị hai phía** trong module `SPRING_CLOUD_CONTRACT`. Phạm vi bao gồm hành vi HTTP, Groovy/YAML DSL, sinh test phía producer, phát hành stub, sử dụng Stub Runner và tích hợp CI để phát hiện thay đổi API không tương thích.

Sau khi học, bạn có thể:

- Phân biệt giá trị cố định và giá trị response phụ thuộc vào request.
- Dùng `fromRequest()` lấy URL, path, query, header và dữ liệu JSON body trong Groovy DSL.
- Viết biểu thức Handlebars tương đương trong YAML khi cú pháp được hỗ trợ.
- Hiểu vì sao matcher của request và response templating cần phối hợp với nhau.
- Giữ đúng kiểu dữ liệu, xử lý dữ liệu thiếu và tránh rò rỉ header nhạy cảm.
- Xác minh cả producer tests và consumer tests với stub trước khi đưa hợp đồng vào CI.

> **Lưu ý phạm vi:** Tham chiếu request → response mô tả cách kiểm chứng hoặc tạo response ở một tương tác HTTP. Nó không thay thế code xử lý nghiệp vụ, không tự lưu trạng thái qua nhiều request và không đảm bảo mọi backend stub hoặc phiên bản công cụ đều hỗ trợ cùng một biểu thức.

## 2. Giá trị hai phía: producer/consumer và ý nghĩa của tham chiếu request

Spring Cloud Contract phân biệt cách một giá trị được sử dụng ở **phía consumer** và **phía producer**. Với các giá trị động thông thường, Groovy DSL có các biểu thức `value(consumer(...), producer(...))` hoặc `$(consumer(...), producer(...))`.

| Vị trí | Phía consumer (stub) | Phía producer (generated test) |
| --- | --- | --- |
| **Request** | Điều kiện mà request của consumer phải khớp; có thể là regex | Dữ liệu cụ thể được test gửi đến producer |
| **Response** | Dữ liệu mẫu hoặc template được stub trả về | Giá trị/matcher mà generated test dùng để xác minh producer |

Ví dụ: request có mã khách hàng linh hoạt ở phía stub nhưng một giá trị cụ thể ở phía producer test:

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
~~~

Ở đây stub có thể khớp nhiều mã khách hàng dạng `CUS-<số>`, còn generated producer test có dữ liệu xác định để gửi. Đây là **khai báo giá trị hai phía**, chưa phải sao chép giá trị request vào response.

Khi cần **tham chiếu trực tiếp giá trị request ở phần response**, Groovy có:

~~~groovy
response {
    status OK()
    headers {
        contentType(applicationJson())
    }
    body(
        customerId: fromRequest().body('$.customerId')
    )
}
~~~

Trong DSL, `fromRequest().body('$.customerId')` có ý nghĩa **response phải chứa giá trị đọc từ field `customerId` của request**. Khi sinh stub được hỗ trợ, cơ chế response templating sẽ lấy dữ liệu từ request thật gửi tới stub thay vì cứng hóa một chuỗi.

### 2.1. So sánh bằng sơ đồ

~~~mermaid
flowchart LR
    C["Consumer gửi request"] --> S["Stub WireMock"]
    S --> T["Đọc field/header/query của request"]
    T --> R["Dựng response tương ứng"]
    R --> C
    DSL["Contract DSL"] --> STUB["Sinh stub và template"]
    DSL --> TEST["Sinh producer test"]
    STUB --> S
    TEST --> P["Producer thật trả response"]
    P --> A["Assertion dựa trên request mẫu"]
~~~

Hai mục tiêu cần kiểm tra tách biệt:

1. **Producer verification:** Với request mẫu do generated test gửi, producer có phản hồi đúng theo hợp đồng không?
2. **Consumer verification với stub:** Với request được matcher chấp nhận, stub có phản ánh dữ liệu request trong response như DSL mô tả không, và client có xử lý kết quả đúng không?

## 3. Các nguồn dữ liệu của `fromRequest()` trong Groovy

Tài liệu Spring Cloud Contract mô tả các phương thức sau để tham chiếu dữ liệu HTTP request:

| Biểu thức Groovy | Dữ liệu được lấy | Ví dụ |
| --- | --- | --- |
| `fromRequest().url()` | URL và query string của request | `/api/orders/ORD-123?view=detail` |
| `fromRequest().path()` | Toàn bộ path | `/api/orders/ORD-123` |
| `fromRequest().path(2)` | Path segment có chỉ số 2 (tính từ 0) | `ORD-123` trong `/api/orders/ORD-123` |
| `fromRequest().query('view')` | Giá trị đầu tiên của query parameter `view` | `detail` |
| `fromRequest().query('tag', 1)` | Giá trị thứ hai của query parameter lặp `tag` | `priority` |
| `fromRequest().header('X-Request-ID')` | Giá trị đầu tiên của header tương ứng | `REQ-123` |
| `fromRequest().header('X-Trace', 1)` | Giá trị thứ hai của header tương ứng nếu có | Giá trị thứ hai của `X-Trace` |
| `fromRequest().body()` | Toàn bộ request body | JSON hoặc text request |
| `fromRequest().body('$.customerId')` | Giá trị tìm thấy bằng JSONPath trong request body | `CUS-7` |
| `fromRequest().body('$.items[0].sku')` | Giá trị lồng trong JSON request | `BK-1` |

Các chỉ số dùng trong `path(index)`, `query(key, index)` và `header(key, index)` là **chỉ số bắt đầu từ 0**. Nếu `/api/orders/ORD-123` được tách thành ba segment `api`, `orders`, `ORD-123` thì `path(0)` là `api` và `path(2)` là `ORD-123`.

Một số phiên bản còn hỗ trợ biến thể `rawUrl()`, `rawPath()`, `rawQuery()`, `rawHeader()` và `rawBody()`. Chỉ sử dụng biến thể raw khi hiểu rõ yêu cầu giữ nguyên/escape nội dung và đã kiểm tra template được sinh trong phiên bản thực tế của dự án.

### 3.1. JSONPath chọn dữ liệu từ request body

Cho request:

~~~json
{
  "customer": {
    "id": "CUS-7",
    "vip": true
  },
  "items": [
    {"sku": "BK-1", "quantity": 2},
    {"sku": "PEN-9", "quantity": 1}
  ]
}
~~~

Một số biểu thức:

~~~groovy
fromRequest().body('$.customer.id')
fromRequest().body('$.customer.vip')
fromRequest().body('$.items[0].sku')
fromRequest().body('$.items[1].quantity')
~~~

Kết quả dự kiến lần lượt là `CUS-7` (String), `true` (Boolean), `BK-1` (String), `1` (Number).

**JSONPath không phải một phép biến đổi nghiệp vụ tùy ý.** Nó chọn giá trị từ request body; nếu muốn tính giá tiền, kiểm tra quyền truy cập hoặc tổng hợp thông tin khác, producer phải thực hiện logic đó và cần domain/integration tests tương ứng.

## 4. Ví dụ Groovy hoàn chỉnh: phản hồi dữ liệu từ body, header và query

Dưới đây là một contract cho `POST /api/requests` có ba nguồn dữ liệu trong request.

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('request_echo_customer_and_context')
    description('Response phản ánh dữ liệu request đã nhận')

    request {
        method POST()

        url('/api/requests') {
            queryParameters {
                parameter 'region': 'HCM'
            }
        }

        headers {
            contentType(applicationJson())
            header('X-Request-ID', 'REQ-123')
        }

        body(
            customerId: 'CUS-7',
            quantity: 2
        )
    }

    response {
        status OK()

        headers {
            contentType(applicationJson())
            header('X-Request-ID',
                   fromRequest().header('X-Request-ID'))
        }

        body(
            customerId: fromRequest().body('$.customerId'),
            quantity: fromRequest().body('$.quantity'),
            region: fromRequest().query('region'),
            requestId: fromRequest().header('X-Request-ID'),
            accepted: true
        )
    }
}
~~~

Ý nghĩa của từng phần:

1. `request.method`, URL và query xác định giao tiếp mà consumer thực sự gửi.
2. `customerId` và `quantity` là dữ liệu đầu vào của producer test, đồng thời là các trường được stub request matcher kiểm tra.
3. `response.headers` yêu cầu response nhắc lại cùng `X-Request-ID`, một kiểu correlation ID dùng trong truy vết.
4. `response.body.customerId` và `quantity` tham chiếu dữ liệu JSON body đã gửi.
5. `response.body.region` lấy query parameter thay vì gõ lại chuỗi `HCM`.
6. `accepted: true` là giá trị cố định theo kịch bản, không phụ thuộc field request.

### 4.1. Hành vi producer cần đáp ứng

Với request đã mô tả, generated test sẽ có các điều kiện kiểm tra tương đương:

~~~json
{
  "customerId": "CUS-7",
  "quantity": 2,
  "region": "HCM",
  "requestId": "REQ-123",
  "accepted": true
}
~~~

Phía producer, service phải thực sự đưa giá trị request vào response. Test không chấp nhận việc producer luôn trả một mã khách hàng khác, ví dụ `CUS-99`.

Tuy nhiên, **một test chạy với request mẫu không tự chứng minh producer phản ánh đúng mọi request hợp lệ**. Nếu code bị hard-code đúng `CUS-7`, test chỉ có kịch bản `CUS-7` vẫn có khả năng xanh. Để bảo vệ chức năng “echo mọi customerId”, hãy thêm các trường hợp kiểm thử với giá trị khác hoặc unit/integration test ở tầng logic.

### 4.2. Hành vi stub dành cho consumer

Khi được sinh bằng WireMock có hỗ trợ response templating, stub có thể lấy `customerId`, `quantity`, `region` và `X-Request-ID` từ request runtime. Vì vậy response có thể thay đổi tùy input **mà matcher của stub cho phép**.

Nếu contract chỉ yêu cầu body chính xác `CUS-7`, consumer gửi `CUS-8` sẽ không khớp; templating không tự mở rộng điều kiện request. Muốn hỗ trợ nhiều input, phải thiết kế request matcher tương ứng. Đây là khác biệt quan trọng giữa **khả năng khớp request** và **khả năng tạo response động**.

## 5. Tham chiếu path segment và query parameter lặp

Giả sử consumer gửi:

~~~http
GET /api/v1/orders/ORD-123?view=summary&tag=sale&tag=priority HTTP/1.1
~~~

Ở đây các path segment lần lượt là:

| Chỉ số | Segment |
| --- | --- |
| `0` | `api` |
| `1` | `v1` |
| `2` | `orders` |
| `3` | `ORD-123` |

Groovy:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_order_context')

    request {
        method GET()

        url('/api/v1/orders/ORD-123') {
            queryParameters {
                parameter 'view': 'summary'
                parameter 'tag': 'sale'
                parameter 'tag': 'priority'
            }
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            orderId: fromRequest().path(3),
            view: fromRequest().query('view'),
            firstTag: fromRequest().query('tag'),
            secondTag: fromRequest().query('tag', 1),
            requestPath: fromRequest().path()
        )
    }
}
~~~

Kết quả dự kiến:

~~~json
{
  "orderId": "ORD-123",
  "view": "summary",
  "firstTag": "sale",
  "secondTag": "priority",
  "requestPath": "/api/v1/orders/ORD-123"
}
~~~

**Điểm cần lưu ý:**

- `path(3)` lấy segment thứ tư, không phải “tên biến `orderId`” của Spring MVC.
- `query('tag')` và `query('tag', 1)` xử lý các giá trị xuất hiện nhiều lần của cùng một khóa.
- Nếu API không cam kết thứ tự các giá trị query lặp, không nên thiết kế contract phụ thuộc cứng vào chỉ số mà không có lý do.
- Khi phân tích URL có ký tự được percent-encode, cần thử thực tế cách chúng được giải mã trong phiên bản công cụ đang sử dụng.
- Cú pháp tham chiếu không thay thế route matching. Hai đường dẫn khác nhau vẫn cần request matcher cho phép tương ứng.

## 6. Dùng giá trị request trong chuỗi response

Đôi khi cần chèn giá trị request vào một câu, ví dụ ghi chú theo tên người dùng:

~~~groovy
response {
    status OK()
    headers {
        contentType(applicationJson())
    }
    body(
        customerId: fromRequest().body('$.customerId'),
        message: "Đã tiếp nhận yêu cầu cho ${fromRequest().body('$.customerId')}"
    )
}
~~~

Dấu nháy kép của Groovy tạo **GString**, cho phép dùng `${fromRequest().body('$.customerId')}` bên trong câu. Nếu dùng chuỗi nháy đơn:

~~~groovy
message: 'Đã tiếp nhận yêu cầu cho $customerId'
~~~

thì `$customerId` chỉ là những ký tự cố định, không tự tham chiếu request.

Một phản hồi có ý nghĩa nghiệp vụ cần cân nhắc **giá trị nào nên được trả nguyên vẹn**. Không echo các thông tin bí mật, mật khẩu, token truy cập hoặc nội dung nhạy cảm chỉ vì DSL cho phép đọc header/body.

### 6.1. Truyền giữ nguyên kiểu thay vì ghép chuỗi

Với JSON request:

~~~json
{"quantity": 2, "active": true}
~~~

nếu contract mong response:

~~~json
{"quantity": 2, "active": true}
~~~

thì nên dùng các giá trị tham chiếu độc lập:

~~~groovy
body(
    quantity: fromRequest().body('$.quantity'),
    active: fromRequest().body('$.active')
)
~~~

`quantity` vẫn có thể được kiểm chứng như number và `active` như boolean. Nếu ghép tất cả bằng string interpolation, rất dễ vô tình biến number/boolean thành chuỗi, khiến schema của response không còn đúng với consumer.

## 7. YAML DSL: Handlebars thay cho `fromRequest()`

Khi viết contract bằng **YAML**, tài liệu Spring Cloud Contract dùng cú pháp **Handlebars triple braces** để tham chiếu HTTP request trong response:

~~~text
{{{ request.path }}}
{{{ request.query.region.[0] }}}
{{{ request.headers.X-Request-ID.[0] }}}
{{{ jsonpath this '$.customerId' }}}
~~~

Trong các biểu thức này:

- `request.path` đại diện cho path.
- `request.query.region.[0]` lấy giá trị query `region` đầu tiên.
- `request.headers.X-Request-ID.[0]` lấy giá trị header `X-Request-ID` đầu tiên.
- `jsonpath this '$.customerId'` lấy giá trị từ request JSON body.

Đây là **template** mà công cụ phải xử lý khi tạo stub và kiểm chứng. Chuỗi `{{{ ... }}}` không phải dữ liệu JSON nghiệp vụ mà producer được yêu cầu trả nguyên văn.

### 7.1. Ví dụ YAML hoàn chỉnh

~~~yaml
name: request_echo_customer_and_context
description: Response tham chiếu JSON body, header và query của request
request:
  method: POST
  url: /api/requests
  queryParameters:
    region: HCM
  headers:
    Content-Type: application/json
    X-Request-ID: REQ-123
  body:
    customerId: CUS-7
response:
  status: 200
  headers:
    Content-Type: application/json
    X-Request-ID: '{{{ request.headers.X-Request-ID.[0] }}}'
  body:
    customerId: "{{{ jsonpath this '$.customerId' }}}"
    requestId: '{{{ request.headers.X-Request-ID.[0] }}}'
    region: '{{{ request.query.region.[0] }}}'
    accepted: true
~~~

Đây là ví dụ tương đương về **ý định phản ánh dữ liệu String** so với Groovy. Trong YAML, dấu nháy bên ngoài template giúp YAML parser nhận đây là **chuỗi chứa biểu thức**. Không viết template không nháy trong một vị trí mà YAML coi dấu `{` là mở cấu trúc mapping.

Đối với number, boolean hoặc object lồng nhau, cần bảo đảm kết quả templating được sinh dưới **đúng kiểu JSON**. Nếu đặt một tham chiếu số trong dấu nháy JSON theo cách khiến response trở thành String, consumer sẽ nhận sai schema. Hãy kiểm tra generated WireMock mapping và output thực nhận khi đưa kiểu khác String vào template.

### 7.2. Bảng đối chiếu Groovy – YAML

| Dữ liệu từ request | Groovy | YAML template |
| --- | --- | --- |
| URL và query | `fromRequest().url()` | `{{{ request.url }}}` |
| Toàn bộ path | `fromRequest().path()` | `{{{ request.path }}}` |
| Path segment chỉ số 1 | `fromRequest().path(1)` | `{{{ request.path.[1] }}}` |
| Query đầu tiên | `fromRequest().query('region')` | `{{{ request.query.region.[0] }}}` |
| Query thứ hai | `fromRequest().query('tag', 1)` | `{{{ request.query.tag.[1] }}}` |
| Header đầu tiên | `fromRequest().header('X-Request-ID')` | `{{{ request.headers.X-Request-ID.[0] }}}` |
| Toàn bộ body | `fromRequest().body()` | `{{{ request.body }}}` |
| Trường JSON | `fromRequest().body('$.customerId')` | `{{{ jsonpath this '$.customerId' }}}` |

Tài liệu cũng mô tả biến thể helper `jsonPath request.body` trong ví dụ JSON body dạng chuỗi của Groovy. Hãy chọn cách biểu diễn tương thích với **DSL và phiên bản plugin thực tế**, thay vì sao chép nguyên template từ một loại DSL sang loại khác mà không kiểm tra.

## 8. Template không có nghĩa mọi request đều được chấp nhận

Một sai lầm thường gặp là thấy response dùng `fromRequest()` thì tưởng stub là một endpoint echo tổng quát. Trong thực tế, **request matcher của stub** vẫn là điều kiện cần.

Giả sử request DSL khai báo:

~~~groovy
request {
    method POST()
    url '/api/echo'
    headers {
        contentType(applicationJson())
    }
    body(customerId: 'CUS-7')
}
~~~

Stub có thể chỉ khớp JSON body với mã `CUS-7`. Nếu gửi `CUS-8`, không thể mặc định response templating sẽ hoạt động vì request **chưa chắc khớp stub**.

Nếu consumer được phép gửi nhiều mã khách hàng và cần nhận lại chính mã đã gửi, có thể chọn matcher linh hoạt cho request:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('echo_valid_customer_id')

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
        headers {
            contentType(applicationJson())
        }
        body(
            customerId: fromRequest().body('$.customerId')
        )
    }
}
~~~

Ở phía stub, pattern `CUS-[0-9]+` cho phép các request có mã khách hàng hợp lệ theo định dạng. Ở phía producer test, `CUS-7` là dữ liệu xác định để gọi endpoint. Với stub backend hỗ trợ templating, response có thể phản ánh đúng giá trị consumer thực gửi.

Tuy nhiên, nếu yêu cầu API còn có xác thực, kiểm tra quyền sở hữu, định dạng nâng cao hoặc trạng thái đơn hàng, **regex không thay thế các quy tắc đó**. Contract chỉ mô tả một phần hành vi quan sát được; cần thêm test tương ứng với mức rủi ro.

## 9. Trường hợp tham chiếu trong response header

Không chỉ JSON body, response header cũng có thể mang thông tin từ request:

~~~groovy
request {
    method GET()
    url '/api/health-details'
    headers {
        header('X-Correlation-ID', 'CORR-123')
    }
}
response {
    status OK()
    headers {
        header('X-Correlation-ID',
               fromRequest().header('X-Correlation-ID'))
    }
}
~~~

Đây là kiểu hợp đồng hữu ích khi hệ thống **cam kết phản hồi correlation ID** để client ghép log và theo dõi lời gọi.

Một số nguyên tắc:

1. Chỉ phản ánh header **được công bố là an toàn để trả lại** và có mục đích rõ ràng.
2. Không tự echo `Authorization`, cookie phiên, access token hoặc credential.
3. Nếu header có thể vắng, xác định kỳ vọng khi vắng: bỏ header ở response, trả giá trị mặc định hay từ chối request. Cần viết contract phù hợp.
4. Nếu header có nhiều giá trị, hiểu đúng việc chọn giá trị đầu hoặc giá trị theo chỉ số.
5. Header name không phân biệt chữ hoa/thường theo HTTP; dù vậy cú pháp template và cách runtime truy cập cần được kiểm tra trong tích hợp thực tế.

## 10. Giá trị missing, null và dữ liệu ngoài JSON

### 10.1. JSONPath không tìm được dữ liệu

Xét:

~~~groovy
body(
    orderId: fromRequest().body('$.orderId')
)
~~~

nếu request thực tế là:

~~~json
{"customerId": "CUS-7"}
~~~

thì `$.orderId` không tìm thấy trường. Bạn không nên tự giả định DSL sẽ trả một chuỗi rỗng, `null` hay ném cùng một ngoại lệ ở mọi phiên bản hoặc stub backend.

Để có contract có thể tái lập:

- Đảm bảo request schema và matcher yêu cầu field được tham chiếu.
- Nếu field tùy chọn, viết tình huống riêng hoặc sử dụng template xử lý thiếu giá trị khi **công cụ cụ thể có hỗ trợ**.
- Xem generated tests và stub runtime để xác nhận hành vi khi field vắng.
- Không đưa các field tùy chọn vào response như bắt buộc nếu producer thật không có cam kết đó.

### 10.2. `null` không đồng nghĩa với field vắng mặt

Request:

~~~json
{"discountCode": null}
~~~

khác request:

~~~json
{}
~~~

Nếu producer trả lại `discountCode`, hợp đồng cần thể hiện việc nhận `null`, bỏ field hay trả giá trị mặc định. Tham chiếu JSONPath đơn thuần **không định nghĩa chính sách optional/null** cho API.

### 10.3. Text, XML hoặc binary body

Các ví dụ `fromRequest().body('$.name')` giả định request là **JSON** phù hợp với JSONPath. Với XML, cần một cơ chế chọn dữ liệu theo XML/XPath hoặc logic test phù hợp; không tự áp JSONPath lên XML.

Với binary upload (PDF, ảnh, ZIP), trả lại nguyên byte stream hoặc trích thông tin từ file đòi hỏi kiểm chứng riêng. Đừng suy ra rằng `fromRequest().body()` và response templating thông thường có thể thay thế đầy đủ cho binary forwarding hoặc multipart processing.

## 11. Phân biệt “sao chép giá trị” và “tính toán từ giá trị”

Dùng `fromRequest()` hợp lý khi giá trị response là **phản chiếu trực tiếp** một phần request, chẳng hạn:

- Client gửi correlation ID, server trả lại ID để truy vết.
- Client gửi mã tham chiếu, response giữ nguyên mã đó.
- API echo/debug hoặc endpoint sandbox có chức năng phản hồi dữ liệu nhận được.
- Một trường response được định nghĩa là cùng giá trị với field tương ứng trong request.

Nhưng nhiều phản hồi cần logic nghiệp vụ:

| Request | Response mong đợi | Có nên chỉ dùng tham chiếu? |
| --- | --- | --- |
| `quantity: 2` | `quantity: 2` | Có, nếu chỉ phản ánh |
| `quantity: 2`, `unitPrice: 50000` | `totalAmount: 100000` | Không, cần logic tính giá và test |
| `customerId: CUS-7` | `customerId: CUS-7` | Có, nếu API cam kết nhắc lại mã |
| `customerId: CUS-7` | `vip: true` | Không, cần kiểm tra hồ sơ hoặc chính sách nghiệp vụ |
| `X-Request-ID: REQ-123` | `X-Request-ID: REQ-123` | Có, nếu đây là cam kết truy vết |
| `Authorization: Bearer ...` | Trả lại token trong body | Không nên thiết kế như vậy vì có thể làm lộ bí mật |

Một response trông giống echo không có nghĩa producer có thể bỏ qua kiểm tra nghiệp vụ hoặc quyền hạn.

## 12. Response templating ở stub và producer test khác nhau

Hãy phân biệt hai quá trình:

### 12.1. Test được sinh ở phía producer

Spring Cloud Contract sinh test gửi một **request mẫu** được DSL mô tả. Với hợp đồng phản ánh request vào response, generated assertion sẽ so sánh giá trị response producer trả với giá trị lấy từ request mẫu tương ứng. Đây là một kiểm chứng hành vi tại thời điểm chạy test.

Ví dụ: test gửi `customerId: CUS-7`; nếu producer trả `customerId: CUS-8`, kiểm chứng phải báo lỗi.

Nhưng nếu producer chỉ hoạt động đúng với một dữ liệu mẫu, bài test đó chưa đủ đánh giá tính đúng đắn của mọi giá trị có thể nhận. Hãy bổ sung test khác nếu yêu cầu nghiệp vụ đòi hỏi **tương quan dữ liệu trên nhiều input**.

### 12.2. Stub được sinh cho consumer

Đối với WireMock, Spring Cloud Contract có thể sinh stub mapping chứa **response-template transformer**. Khi consumer gửi request khớp mapping, WireMock lấy path/header/query/body từ request runtime để tạo response.

Ví dụ một phần mapping minh họa:

~~~json
{
  "response": {
    "status": 200,
    "body": "{\"customerId\":\"{{{jsonpath this '$.customerId'}}}\"}",
    "transformers": ["response-template"]
  }
}
~~~

Đoạn này chỉ minh họa **phần response** của mapping, không phải file WireMock hoàn chỉnh: một mapping thực còn cần phần `request` với matcher phù hợp. Tên/biểu diễn có thể khác giữa các phiên bản.

Nếu transformer không được kích hoạt hoặc stub engine không hỗ trợ, consumer có thể nhận nguyên template thay vì giá trị hoặc mapping không thực thi như mong đợi. Vì vậy phải **kiểm thử stub runtime** sau khi tạo artifact.

### 12.3. Điều kiện “khi được hỗ trợ”

Tài liệu Spring Cloud Contract mô tả cơ chế này với WireMock có response templating (tài liệu nêu yêu cầu từ WireMock 2.5.1 trở lên). Với các phiên bản Spring Cloud Contract/WireMock hiện đại, hãy dùng tổ hợp phiên bản tương thích được quản lý bởi dự án, rồi kiểm tra thực tế:

1. DSL được plugin chấp nhận khi sinh generated tests và stub.
2. Generated producer tests được compile và chạy.
3. Stub mapping có cấu hình templating cần thiết.
4. Stub Runner khởi động stub và thay thế placeholder bằng giá trị request thật.
5. Content-Type, escaping và kiểu dữ liệu của response vẫn đúng schema.

Đừng suy ra **mọi** định dạng stub, giao thức messaging, proxy hoặc test mode đều hiểu Handlebars như WireMock HTTP.

## 13. Bẫy kiểu dữ liệu và escape khi dùng template

### 13.1. Number bị trả thành String

Request JSON:

~~~json
{"quantity": 2}
~~~

Consumer muốn response:

~~~json
{"quantity": 2}
~~~

Nhưng một template tạo JSON như sau:

~~~json
{"quantity": "{{{jsonpath this '$.quantity'}}}"}
~~~

có nguy cơ xuất kết quả `{"quantity":"2"}`, đổi từ number thành String. Trong JSON template ở cấp văn bản, chèn number **không có dấu nháy JSON bên ngoài** khi muốn giữ kiểu number:

~~~text
{"quantity": {{{jsonpath this '$.quantity'}}}}
~~~

Cách trình bày trên là **ví dụ template**, không phải JSON hoàn chỉnh trước khi render. Cần kiểm tra generated mapping và response sau khi Stub Runner chạy, nhất là khi biểu thức nằm trong YAML DSL hoặc JSON string.

### 13.2. Chuỗi có dấu nháy và ký tự điều khiển

Request có thể chứa:

~~~json
{"name": "Lan \"VIP\""}
~~~

Nếu một template nhúng nguyên giá trị vào JSON mà không escape đúng, response có thể trở thành JSON sai cú pháp. Các helper và cách escape phụ thuộc ngữ cảnh:

- Đối với **JSON value**, phải giữ JSON encoding hợp lệ.
- Đối với **text/plain**, có thể cần dữ liệu raw theo đúng thỏa thuận.
- Đối với URL/header, cần phân biệt decoded value và dữ liệu raw.
- Đối với nội dung XML/HTML, không tự coi JSON escaping là đủ.

Trong Spring Cloud Contract, một số biến thể `raw...` và helper như `escapejsonbody` có thể hỗ trợ các tình huống tương ứng. Tuy vậy, không nên tự thêm hoặc bỏ escape theo cảm tính. Hãy kiểm tra một mẫu có dấu nháy, backslash, Unicode và ký tự xuống dòng.

### 13.3. Kiểm soát an toàn dữ liệu được phản ánh

Một API phản ánh dữ liệu do client gửi có thể trở thành đường đưa dữ liệu không tin cậy vào response. Với ứng dụng web, rủi ro còn phụ thuộc nơi response được hiển thị và cách client xử lý dữ liệu. Contract test nên kiểm tra định dạng/schema; những quy tắc encode/sanitize và phân quyền cần thêm security tests phù hợp.

## 14. Lỗi thường gặp và cách xác định nguyên nhân

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Stub trả nguyên chuỗi `{{{ ... }}}` | Templating transformer chưa chạy hoặc backend không hỗ trợ | Xem generated WireMock mapping, cấu hình Stub Runner và phiên bản |
| Stub không khớp request mới | Request matcher cố định trong khi consumer gửi giá trị khác | Điều chỉnh matcher theo dải giá trị được phép |
| Generated producer test thất bại | Producer không phản ánh đúng field/header/query đã cam kết | Đối chiếu request thực, response thực và contract |
| JSON response sai kiểu | Biến số/boolean thành String khi render template | Kiểm tra quote và kết quả JSON sau templating |
| JSON response không parse được | Giá trị chứa nháy/backslash chưa escape đúng | Dùng helper/encoding phù hợp và test với dữ liệu đặc biệt |
| Field tham chiếu nhận null hoặc không có giá trị | JSONPath sai hoặc field không có trong request | Kiểm tra schema request, matcher và dữ liệu test |
| Path segment bị lấy sai | Nhầm chỉ số bắt đầu từ 0 | Viết bảng index cho path thực tế |
| Query parameter lặp lấy sai phần tử | Gọi `query('tag')` thay vì `query('tag', 1)` | Dùng chỉ số theo thứ tự đã thỏa thuận |
| Header nhiều giá trị bị chọn sai | Chỉ lấy giá trị đầu tiên hoặc sai tên truy cập | Kiểm tra header list và cú pháp index |
| Tham chiếu JSONPath không dùng được với XML | Áp JSONPath lên dữ liệu không phải JSON | Chọn test/XML handling phù hợp |
| Không thấy generated tests | Plugin chưa cấu hình, contract sai đường dẫn hoặc bị skip | Kiểm tra số test sinh và log build |
| Stub được tạo nhưng response không đúng | Khác behavior giữa producer và transformer | Chạy cả producer verification lẫn consumer tests với stub |
| Contract quá chặt | Cố định header/ID ngẫu nhiên không cần thiết | Dùng matcher và tham chiếu hợp lý |
| Contract quá lỏng | Regex chấp nhận dữ liệu không hợp lệ | Thu hẹp điều kiện khớp theo schema/API thực tế |

### 14.1. Chẩn đoán từ request đến response

Khi có sai lệch, đi theo thứ tự:

1. **Request DSL:** Method, URL, query, headers và body được khai báo đúng chưa?
2. **Request runtime:** Generated test hoặc consumer thực sự gửi giá trị gì?
3. **Matcher:** Stub có chấp nhận request đó không?
4. **Template:** `fromRequest()` hoặc Handlebars đang đọc trường nào, ở chỉ số bao nhiêu?
5. **Response:** Giá trị sau render có đúng loại dữ liệu và encoding không?
6. **Producer:** Code nghiệp vụ có thật sự giữ lời cam kết về dữ liệu được phản ánh không?
7. **Build:** Generated tests và consumer stub tests có được thực thi trong CI không?

Đừng sửa file Java generated test hoặc file stub đã đóng gói để che lỗi; thay đổi bền vững nằm ở DSL, fixture, base class hoặc code producer.

## 15. Thực hành: phản hồi mã tương quan từ request

Giả sử `Payment Gateway Adapter` nhận:

~~~http
POST /api/payments/confirm?source=mobile HTTP/1.1
Content-Type: application/json
X-Correlation-ID: CORR-99

{
  "paymentId": "PAY-8",
  "amount": 120000
}
~~~

API đã thống nhất phản hồi:

~~~json
{
  "paymentId": "PAY-8",
  "source": "mobile",
  "correlationId": "CORR-99",
  "confirmed": true
}
~~~

**Nhiệm vụ:**

1. Viết contract Groovy cho method/path/header/query/body trên.
2. Dùng `fromRequest().body('$.paymentId')`, `fromRequest().query('source')` và `fromRequest().header('X-Correlation-ID')` trong response.
3. Đặt header `X-Correlation-ID` ở response bằng giá trị request tương ứng.
4. Chuyển sang YAML với Handlebars; đảm bảo mọi string template có dấu nháy YAML phù hợp.
5. Thay body mẫu bằng `PAY-9` để thử phản hồi đúng dữ liệu; lưu ý matcher request của stub phải chấp nhận mã mới.
6. Thử xóa header tương quan và quan sát kết quả, từ đó quyết định API cho phép thiếu header hay coi là request không hợp lệ.

### 15.1. Gợi ý lời giải Groovy

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('confirm_payment_with_correlation')

    request {
        method POST()

        url('/api/payments/confirm') {
            queryParameters {
                parameter 'source': 'mobile'
            }
        }

        headers {
            contentType(applicationJson())
            header('X-Correlation-ID', 'CORR-99')
        }

        body(
            paymentId: 'PAY-8',
            amount: 120000
        )
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
            header('X-Correlation-ID',
                   fromRequest().header('X-Correlation-ID'))
        }

        body(
            paymentId: fromRequest().body('$.paymentId'),
            source: fromRequest().query('source'),
            correlationId: fromRequest().header('X-Correlation-ID'),
            confirmed: true
        )
    }
}
~~~

### 15.2. Gợi ý lời giải YAML

~~~yaml
name: confirm_payment_with_correlation
request:
  method: POST
  url: /api/payments/confirm
  queryParameters:
    source: mobile
  headers:
    Content-Type: application/json
    X-Correlation-ID: CORR-99
  body:
    paymentId: PAY-8
    amount: 120000
response:
  status: 200
  headers:
    Content-Type: application/json
    X-Correlation-ID: '{{{ request.headers.X-Correlation-ID.[0] }}}'
  body:
    paymentId: "{{{ jsonpath this '$.paymentId' }}}"
    source: '{{{ request.query.source.[0] }}}'
    correlationId: '{{{ request.headers.X-Correlation-ID.[0] }}}'
    confirmed: true
~~~

Không nên đồng thời giữ hai hợp đồng Groovy/YAML trùng cùng tên và cùng request trong nguồn build nếu chỉ dùng hai cách viết để học: hãy chọn một bản khi chạy producer verification, hoặc đặt tên/đường dẫn riêng và quản lý điều kiện khớp phù hợp.

### 15.3. Câu hỏi tự kiểm tra

1. Vì sao `fromRequest().body('$.paymentId')` phù hợp hơn một literal response `'PAY-8'` khi API cam kết nhắc lại giá trị?
2. Nếu stub matcher yêu cầu `PAY-8` chính xác, consumer gửi `PAY-9` có nhận được response từ stub không?
3. `{{{ request.headers.X-Correlation-ID.[0] }}}` lấy dữ liệu ở đâu và số `0` có ý nghĩa gì?
4. Nếu `amount` được phản ánh trong response, cần chú ý điều gì để không đổi JSON Number thành String?
5. Vì sao một generated producer test chỉ dùng `PAY-8` có thể không phát hiện lỗi code hard-code giá trị `PAY-8`?
6. Nếu API bắt buộc có correlation ID, test nhánh thiếu header nên mong response gì?
7. Nếu transformer không được chạy trên Stub Runner, hiện tượng thường thấy là gì?

**Định hướng đáp án:** Tham chiếu thể hiện quan hệ giữa input/output; stub chỉ xử lý request khớp điều kiện; chỉ số `0` là phần tử đầu; kiểu dữ liệu phải giữ nguyên; cần nhiều test độc lập để kiểm tra tính tổng quát; nhánh thiếu header cần contract theo chính sách API; template không được xử lý sẽ không trở thành giá trị request.

## 16. Đưa vào CI: kiểm tra cả hai phía

Một quy trình kiểm chứng có thể tổ chức:

~~~mermaid
flowchart TD
    A["Contract Groovy/YAML có tham chiếu request"] --> B["Sinh producer tests"]
    B --> C["Chạy trên producer"]
    C --> D{"Kỳ vọng response khớp?"}
    D -- "Không" --> E["Chặn build và rà soát thay đổi"]
    D -- "Có" --> F["Sinh và phát hành stub có version"]
    F --> G["Consumer dùng Stub Runner"]
    G --> H["Gửi nhiều request phù hợp matcher"]
    H --> I{"Response phản ánh đúng dữ liệu?"}
    I -- "Không" --> J["Kiểm tra matcher, templating và kiểu dữ liệu"]
    I -- "Có" --> K["Consumer contract tests đạt"]
~~~

Ví dụ lệnh build của producer đã cấu hình Maven plugin:

~~~bash
./mvnw -B clean verify
~~~

Để CI thực sự bảo vệ tính tương thích, nên:

- Xác minh số generated tests **được thực thi**, không chỉ được sinh ra.
- Với contract có echo dynamic, chạy thêm một hoặc hai request mẫu khác nhau qua Stub Runner để bảo đảm transformer hoạt động đúng theo matcher.
- Kiểm tra JSON body sau render có đúng String/Number/Boolean/null và escaping.
- Giữ stub artifact đúng phiên bản producer đã xác minh.
- Bổ sung test nghiệp vụ nếu tính phản ánh dữ liệu phải đúng cho mọi input, không chỉ một fixture.
- Xem lại tác động của thay đổi DSL trước khi sửa contract chỉ để build xanh.

## 17. Checklist khi tham chiếu dữ liệu request trong response

- [ ] Producer và consumer đã thống nhất **field nào được phản ánh**, field nào được tính toán hoặc tạo mới.
- [ ] Chỉ tham chiếu dữ liệu HTTP request từ nguồn được DSL và stub backend hỗ trợ.
- [ ] Groovy dùng đúng `fromRequest().path/query/header/body` và chỉ số bắt đầu từ 0.
- [ ] YAML dùng cú pháp Handlebars `{{{ ... }}}` và helper JSONPath được tài liệu hỗ trợ.
- [ ] Request matcher chấp nhận đúng dải input mà stub phải mô phỏng.
- [ ] JSONPath trỏ tới field có thật; trường optional/null có chính sách rõ.
- [ ] Response templating giữ đúng kiểu dữ liệu và escaping.
- [ ] Không phản ánh token, cookie phiên, mật khẩu hoặc dữ liệu nhạy cảm ngoài hợp đồng.
- [ ] Generated producer tests có dữ liệu mẫu và base class phù hợp.
- [ ] Stub WireMock đã được kiểm tra transformer `response-template` và hoạt động qua Stub Runner.
- [ ] Có test với input khác để phát hiện code hard-code trong trường hợp cần echo tổng quát.
- [ ] CI chạy cả producer verification và consumer stub tests, và quản lý phiên bản artifact.
- [ ] Các hành vi tính toán nghiệp vụ, xử lý multipart/binary hoặc state qua nhiều request được kiểm thử ở tầng thích hợp.

## 18. Tài liệu tham khảo

- [Spring Cloud Contract — Dynamic properties, Referencing the Request from the Response](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/dsl-dynamic-properties.html): `fromRequest()`, Handlebars cho YAML, nguyên tắc response templating và các giá trị phía consumer/producer.
- [Spring Cloud Contract — HTTP Contracts](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/http.html): method, URL, headers, query, request/response body.
- [Spring Cloud Contract — Reference Documentation](https://docs.spring.io/spring-cloud-contract/reference/): phiên bản, plugin sinh test, stub và cấu hình trong vòng đời build.

**Ghi nhớ:** Khi hợp đồng yêu cầu response phản ánh giá trị từ request, dùng **`fromRequest()` trong Groovy** hoặc **Handlebars trong YAML** nếu công cụ hỗ trợ. Luôn kiểm tra cả **request matcher** lẫn **response template**, giữ nguyên kiểu dữ liệu, và chạy producer verification cùng Stub Runner trong CI. Một contract có thể mô tả quan hệ input/output, nhưng tính đúng đắn nghiệp vụ tổng quát vẫn cần được kiểm thử theo phạm vi thực tế.

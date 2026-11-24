# Đánh giá assertion được sinh thay vì chỉ nhìn hợp đồng nguồn

## Mục tiêu học tập

Trong chương **Matcher và assertion** của **Spring Cloud Contract**, hợp đồng được viết bằng **Groovy/YAML DSL** là đầu vào để công cụ sinh **kiểm thử phía producer** và **stub** cho consumer sử dụng với **Stub Runner**. Tuy nhiên, nhìn file DSL và thấy các quy tắc có vẻ hợp lý **không đủ** để kết luận các assertion được sinh sẽ phát hiện đúng lỗi.

Sau bài này, bạn có thể:

- Phân biệt **ý định trong hợp đồng nguồn**, **assertion trong generated producer test** và **điều kiện của stub mapping**.
- Tìm và đọc những assertion quan trọng về HTTP status, header, JSON body, kiểu dữ liệu, regex, trường bắt buộc và danh sách.
- Giải thích tại sao matcher `byType()`, `byRegex(...)` hoặc so khớp cố định có sức phát hiện lỗi khác nhau.
- Nhận ra khi test có thể **xanh giả về mặt nghiệp vụ** vì assertion quá lỏng, thiếu nhánh hoặc dùng sai phía.
- Xây dựng checklist review và cổng CI để producer thực sự đáp ứng contract, đồng thời consumer kiểm thử với đúng stub.

## 1. Bốn câu hỏi khi đánh giá chất lượng contract test

Giả sử **Catalog Service** là producer của API giá sản phẩm, còn **Checkout Service** là consumer sử dụng giá để tính đơn hàng. Producer công bố:

~~~http
GET /api/prices/SKU-101 HTTP/1.1
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sku": "SKU-101",
  "price": 125000,
  "currency": "VND",
  "updatedAt": "2026-01-15T08:30:00Z"
}
~~~

Nhóm Checkout phụ thuộc vào:

1. `200 OK` cho SKU đã tồn tại.
2. `sku` phản ánh đúng sản phẩm được hỏi.
3. `price` là số biểu thị số tiền theo đơn vị mà API công bố.
4. `currency` là mã tiền tệ `VND` trong tình huống ví dụ.
5. `updatedAt` là một timestamp hợp lệ theo định dạng đã thống nhất; giá trị có thể thay đổi theo lần cập nhật.

Bây giờ cần phân biệt bốn câu hỏi:

| Câu hỏi | Đọc ở đâu? | Tại sao quan trọng? |
|---|---|---|
| Tác giả *muốn* bảo vệ hành vi nào? | Contract Groovy/YAML | Xác định ý nghĩa và trường consumer phụ thuộc |
| Generator *đã tạo* assertion nào? | Generated producer test | Kiểm tra status, header, body thật có được so khớp đủ chặt không |
| Stub *sẽ nhận và trả* gì? | WireMock mapping/stub artifact | Kiểm tra consumer có thể gọi đúng request và nhận đúng response mẫu không |
| Hai phía *đã chạy* những test nào? | Build log và báo cáo CI | Bảo đảm producer test và consumer test thực sự thực thi trên cùng phiên bản hợp đồng/stub |

**Không thể lấy việc “DSL chứa field `price`” làm bằng chứng rằng generated test đã kiểm tra giá dương, currency phù hợp hoặc quan hệ giữa các trường.** Cần đọc assertion được sinh và đối chiếu với nhu cầu nghiệp vụ.

~~~mermaid
flowchart TD
    A["Groovy/YAML contract"] --> B["Generated producer test"]
    A --> C["Stub mapping / stub artifact"]
    B --> D{"Assertion có bắt lỗi cần bắt?"}
    C --> E["Consumer test qua Stub Runner"]
    D -->|Có| F["Chạy với producer thật trong môi trường test"]
    D -->|Chưa| G["Sửa DSL, matcher hoặc bổ sung test"]
    G --> A
    F --> H{"Producer test đạt?"}
    E --> I{"Consumer test đạt với đúng stub?"}
~~~

## 2. Viết hợp đồng nguồn rồi dự đoán assertion

Ví dụ file `src/test/resources/contracts/prices/priceForSku101.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Tra ve gia cho SKU-101'

    request {
        method 'GET'
        url '/api/prices/SKU-101'
        headers {
            accept(applicationJson())
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-101',
            price: 125000,
            currency: 'VND',
            updatedAt: '2026-01-15T08:30:00Z'
        )
        bodyMatchers {
            jsonPath('$.price', byType())
            jsonPath(
                '$.updatedAt',
                byRegex('[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z')
            )
        }
    }
}
~~~

Đây là **một contract minh họa** cho Spring Cloud Contract Groovy DSL. Tùy phiên bản, generator và cấu hình test mode, mã test được sinh có thể khác nhau ở tên class, cách gọi HTTP và thư viện assertion. Nhưng ý nghĩa cần kiểm tra vẫn gồm:

| Thuộc tính | Giá trị/matcher trong DSL | Ý nghĩa assertion kỳ vọng |
|---|---|---|
| `status` | `200` | Response HTTP phải có status 200 |
| `Content-Type` | `application/json` | Response dùng JSON |
| `sku` | `SKU-101` | Giá trị response cho tình huống này phải phù hợp với mẫu cố định |
| `currency` | `VND` | Producer không được tự thay thành mã tiền tệ khác trong tình huống này |
| `price` | `byType()` | Producer phải trả giá trị có **kiểu** phù hợp với ví dụ body, không nhất thiết đúng số 125000 |
| `updatedAt` | `byRegex(...)` | Chuỗi timestamp phải khớp biểu thức dạng ngày-giờ UTC đã mô tả |

Điểm dễ bỏ lọt: `byType()` với `price` kiểm tra **kiểu**, không tự kiểm tra `price > 0`, giá trong một khoảng hợp lệ, hay tính đúng của công thức chiết khấu. Regex timestamp trên cũng chỉ kiểm tra **cấu trúc ký tự**; nó không tự chứng minh một ngày bất kỳ như 2026-19-99 là hợp lệ theo lịch.

### Giá trị mẫu và matcher không giống nhau

Trong hợp đồng trên, `price: 125000` đóng vai trò một **giá trị mẫu** hữu ích để tạo stub. Khi khai báo `jsonPath('$.price', byType())`, generated producer test có thể kiểm tra giá trị thật theo **kiểu dữ liệu** thay vì buộc bằng đúng 125000.

Tương tự, `updatedAt` có một giá trị mẫu ổn định để stub trả cho consumer, nhưng phía producer có thể trả timestamp khác nếu phù hợp regex. Đừng kết luận producer phải trả đúng ngày `2026-01-15T08:30:00Z` chỉ vì nó nằm trong `body`; matcher đã làm rõ mức ràng buộc.

## 3. Đọc generated producer test theo bằng chứng, không theo suy đoán

Khi dự án producer đã được cấu hình với Spring Cloud Contract Verifier và plugin Maven/Gradle tương ứng, build sinh test từ DSL. Vị trí thường gặp:

~~~text
Maven:
  target/generated-test-sources/contracts/

Gradle:
  build/generated-test-sources/contracts/
~~~

Đường dẫn chính xác, tên class, ngôn ngữ generated test và API kiểm thử phụ thuộc phiên bản và cấu hình plugin. Hãy dựa vào **build log và artifact thực tế của dự án**, không chỉ lấy đường dẫn trên rồi kết luận “không có test”.

### Đọc test theo năm lớp

Khi mở một generated test, tìm lần lượt:

1. **Setup và lời gọi thực tế:** test dựng ứng dụng, fake hoặc HTTP test mode nào? Request `GET` có được gửi tới `/api/prices/SKU-101` không?
2. **Status assertion:** có kiểm tra `200` không, hay chỉ kiểm tra body?
3. **Header assertion:** có kiểm tra `Content-Type` và các header mà consumer cần không?
4. **Body assertion:** mỗi field được kiểm tra bằng equality, regex, type hay cách khác? Có đúng JSONPath không?
5. **Ràng buộc quan trọng chưa có:** test có phát hiện thiếu `price`, sai mã tiền, giá âm hoặc timestamp sai quy tắc nghiệp vụ không?

### Pseudocode minh họa điều cần tìm

Đoạn dưới đây là **mã giả dễ đọc**, không phải output Java nguyên văn của một phiên bản generator cụ thể:

~~~text
GIVEN producer test environment is ready

WHEN
  GET /api/prices/SKU-101
  Accept: application/json

THEN
  assert HTTP status == 200
  assert Content-Type is compatible with application/json

  parse JSON response body
  assert $.sku == "SKU-101"
  assert $.currency == "VND"
  assert $.price has the type expected by the contract
  assert $.updatedAt matches "[0-9]{4}-[0-9]{2}-..."
~~~

**Điều quan trọng nhất khi review là kiểm tra output thật có thực hiện đúng các bước này.** Có thể generator tạo `RestAssuredMockMvc`, `RestAssured`, `WebTestClient` hoặc công cụ khác; những wrapper này không làm thay đổi ý nghĩa cần kiểm chứng.

Đừng chỉnh sửa file generated test để “sửa” assertion: lần sinh kế tiếp sẽ ghi đè. Nếu assertion thiếu hoặc sai, hãy sửa **DSL, matcher, fixture hoặc cấu hình test generation**, sau đó sinh lại và đọc lại output.

## 4. Phân biệt các kiểu assertion qua ví dụ

| Kiểu kiểm tra | Mục tiêu | Phát hiện được | Có thể không phát hiện |
|---|---|---|---|
| So khớp giá trị cụ thể | `currency == "VND"` | Đổi từ `VND` sang `USD` | Cách dùng currency đúng ở những endpoint khác |
| So khớp kiểu | `price` là number | Producer trả string `"125000"` thay vì number | Giá âm, giá sai nhưng vẫn là số |
| Regex | `reservationId` theo mẫu `RSV-[0-9]+` | ID sai format | ID hợp format nhưng không tồn tại hoặc trùng |
| JSONPath | `$.price` hoặc `$.items[0].id` | Kiểm tra đường dẫn/field được nêu | Field khác, nhánh khác không được mô tả |
| HTTP status | `200`, `400`, `404` | Response trả status ngoài dự kiến | Body có thông tin sai nhưng status đúng |
| Header assertion | `Content-Type`, `Location` khi có cam kết | Mất hoặc sai header quan trọng | Nội dung/giá trị nghiệp vụ trong body |
| XML XPath | Một node hoặc attribute của XML | Sai giá trị tại vị trí được chọn | Cấu trúc XML khác không nằm trong XPath |
| Test nghiệp vụ bổ sung | `price >= 0`, quan hệ giữa các field | Bất biến mà matcher đơn giản không biểu diễn | Chỉ bao phủ những tình huống đã test |

Từ bảng này, quy tắc thiết kế là **mỗi assertion phải có lý do gắn với một phụ thuộc cụ thể của consumer**. Không nên khóa cứng mọi giá trị biến động, cũng không nên thay mọi so khớp bằng matcher rộng như `.*`.

### Trường hợp giá âm: một ví dụ “xanh nhưng sai”

Response thật:

~~~json
{
  "sku": "SKU-101",
  "price": -500,
  "currency": "VND",
  "updatedAt": "2026-01-15T08:30:00Z"
}
~~~

Nếu generated test chỉ kiểm tra `price` là number bằng `byType()`, **giá -500 vẫn là số**. Test có thể xanh dù Checkout không được phép tính tổng tiền âm.

Đây là một **lỗ hổng của mức assertion**, không phải bằng chứng Spring Cloud Contract “bỏ qua” yêu cầu đã khai báo. Hãy thống nhất producer–consumer rằng `price` không âm; sau đó thêm kiểm tra phù hợp ở contract nếu DSL có matcher biểu diễn được ràng buộc, hoặc **test nghiệp vụ riêng** cho bất biến. Đừng suy rằng `byType()` có nghĩa “số hợp lệ theo nghiệp vụ”.

### Trường hợp timestamp sai ngày thực tế

Response:

~~~json
{
  "updatedAt": "2026-19-99T08:30:00Z"
}
~~~

Regex `[0-9]{4}-[0-9]{2}-[0-9]{2}T...Z` có thể **khớp văn bản này**. Muốn chứng minh thời gian hợp lệ, cần parser ngày-giờ với quy tắc tương ứng hoặc test bổ sung. Regex có thể kiểm tra hình dạng, nhưng không tự xác nhận mọi quan hệ lịch và múi giờ.

### Trường hợp đổi kiểu JSON

Response:

~~~json
{
  "price": "125000",
  "currency": "VND"
}
~~~

`"125000"` là string, khác với số `125000`. Đây có thể là **breaking change** với consumer deserialize thành kiểu số. Vì vậy khi review generated test, cần xác nhận assertion giữ đúng **kiểu JSON** chứ không chỉ so sánh văn bản sau khi ép kiểu.

## 5. Kiểm tra độ bao phủ của body: field thiếu, null, array và object

Một JSON body có thể trông gần giống fixture nhưng khác cấu trúc mà consumer phụ thuộc.

### Field thiếu khác field có giá trị null

~~~json
{
  "sku": "SKU-101",
  "currency": "VND"
}
~~~

Response trên **không có** key `price`. Một response khác:

~~~json
{
  "sku": "SKU-101",
  "price": null,
  "currency": "VND"
}
~~~

Ở đây `price` có mặt nhưng là JSON `null`. Nếu consumer yêu cầu number bắt buộc, hai trường hợp đều không đáp ứng nhu cầu. Cần đọc generated assertion để xác nhận trường bắt buộc và kiểu giá trị thật sự được kiểm tra, thay vì chỉ thấy `price` xuất hiện trong DSL.

### Array rỗng và thay đổi shape

Giả sử endpoint `GET /api/prices` có contract trả danh sách:

~~~json
[
  {
    "sku": "SKU-101",
    "price": 125000
  }
]
~~~

Consumer phải phân biệt:

- `[]`: danh sách rỗng, thường là kết quả tìm kiếm hợp lệ theo API đã thống nhất.
- `{}`: object rỗng, **không phải** array.
- `null`: JSON null, **không phải** array rỗng.
- `{"items":[]}`: object phân trang/bao bọc danh sách, **shape khác** array.

Một matcher chỉ kiểm tra `$[0].sku` cho tình huống có dữ liệu không tự bảo vệ trường hợp danh sách rỗng. Hãy viết hợp đồng riêng cho `200 []` nếu consumer dựa vào hành vi đó. Nếu cần kiểm tra **số lượng phần tử**, thứ tự hay kiểu của từng phần tử, phải đảm bảo matcher/test tương ứng có trong generated output.

### Field thừa và thứ tự key

Đổi thứ tự các key của JSON object thường không có ý nghĩa nếu consumer parse JSON đúng tiêu chuẩn. Thêm field tùy chọn cũng có thể tương thích **nếu** consumer bỏ qua field lạ; nhưng consumer dùng deserializer nghiêm ngặt có thể hỏng. Vì vậy đừng chỉ dựa vào việc generated producer test xanh để khẳng định thay đổi tương thích với **mọi** consumer.

## 6. Phân biệt assertion ở request và response

Trong Spring Cloud Contract, không phải mọi matcher đều sinh assertion phía producer theo cùng cách.

Giả sử một contract có `request.body.requestId` động và `response.body.reservationId` động:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Tao reservation'

    request {
        method 'POST'
        url '/api/reservations'
        headers {
            contentType(applicationJson())
        }
        body(
            requestId: $(
                consumer(regex('REQ-[0-9]{4}')),
                producer('REQ-1001')
            ),
            sku: 'SKU-101'
        )
    }

    response {
        status 201
        headers {
            contentType(applicationJson())
        }
        body(
            reservationId: $(
                consumer('RSV-1001'),
                producer(regex('RSV-[0-9]+'))
            ),
            accepted: true
        )
    }
}
~~~

Đọc đúng **hai phía**:

| Vị trí | Generated producer test | Stub mapping cho consumer |
|---|---|---|
| `request.requestId` | **Gửi** `REQ-1001` từ `producer(...)` | **Match** request ID theo regex từ `consumer(...)` |
| `response.reservationId` | **Assert** response ID khớp regex từ `producer(...)` | **Trả** ID ví dụ `RSV-1001` từ `consumer(...)` |
| `response.accepted` | Kiểm tra boolean `true` | Trả boolean `true` |

Đây là một nguyên nhân thường gây nhầm khi chỉ nhìn DSL: **request matcher chủ yếu ảnh hưởng cách stub nhận request**, còn **response matcher chủ yếu ảnh hưởng assertion phía producer**. Muốn biết một regex có thực sự biến thành assertion producer hay không, phải kiểm tra nơi nó được khai báo và file test được sinh.

### Với YAML DSL

YAML diễn tả ý tưởng tương ứng bằng **giá trị mẫu** trong `body` và các matcher tách biệt:

~~~yaml
description: 'Tao reservation'
request:
  method: POST
  url: '/api/reservations'
  headers:
    Content-Type: 'application/json'
  body:
    requestId: 'REQ-1001'
    sku: 'SKU-101'
  matchers:
    body:
      - path: '$.requestId'
        type: by_regex
        value: 'REQ-[0-9]{4}'
response:
  status: 201
  headers:
    Content-Type: 'application/json'
  body:
    reservationId: 'RSV-1001'
    accepted: true
  matchers:
    body:
      - path: '$.reservationId'
        type: by_regex
        value: 'RSV-[0-9]+'
~~~

Cách đối chiếu cần nhớ:

- `request.body.requestId` là ví dụ **generated producer test gửi**.
- `request.matchers.body` là **điều kiện stub dùng để match** request từ consumer.
- `response.body.reservationId` là ví dụ **stub trả**.
- `response.matchers.body` là **quy tắc generated producer test assert** response thực.

Cần dùng schema YAML của đúng phiên bản Spring Cloud Contract đang triển khai; không tự chép cú pháp matcher Groovy vào YAML.

## 7. Đọc stub mapping có ích gì nếu bài đang tập trung vào assertion?

Generated test cho thấy producer được kiểm tra bằng gì; **stub mapping** cho biết consumer thực sự được cung cấp ví dụ gì. Một contract có thể có assertion đúng nhưng stub lại khó dùng vì request matcher sai.

Ví dụ WireMock mapping minh họa (**rút gọn để giải thích, không phải output nguyên văn bắt buộc của generator**):

~~~json
{
  "request": {
    "method": "POST",
    "url": "/api/reservations",
    "bodyPatterns": [
      {
        "matchesJsonPath": "$[?(@.requestId =~ /REQ-[0-9]{4}/)]"
      }
    ]
  },
  "response": {
    "status": 201,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "reservationId": "RSV-1001",
      "accepted": true
    }
  }
}
~~~

Khi đối chiếu, hãy hỏi:

1. Mapping có **match** đúng request thực mà consumer sẽ gửi không?
2. Response stub có đủ field mà consumer cần không?
3. `accepted` là boolean hay string?
4. Nếu có nhiều contract cùng endpoint, mapping nào được chọn? Các điều kiện request có chồng lấn không?
5. Stub trong test có được sinh từ **chính revision hợp đồng vừa review** không?

Nếu mapping yêu cầu một request ID cố định trong khi consumer gửi nhiều ID hợp lệ, test consumer có thể nhận lỗi “no matching stub mapping” dù producer implementation tốt. Nhưng đó là vấn đề **stub matcher**, không phải một assertion response producer. Đọc hai artifact giúp phân biệt đúng nơi cần sửa.

## 8. Nhận diện assertion quá cứng và quá lỏng

| Dạng vấn đề | Ví dụ | Hậu quả | Cách cải thiện |
|---|---|---|---|
| **Quá cứng** | Producer phải trả đúng `updatedAt = 2026-01-15T08:30:00Z` | Test lỗi với timestamp hợp lệ khác | Matcher định dạng, hoặc cố định clock nếu đó là yêu cầu |
| **Quá cứng** | Bắt array luôn có đúng một phần tử | Test lỗi khi dữ liệu có thêm kết quả hợp lệ | Kiểm tra cardinality theo nghĩa vụ đã cam kết |
| **Quá cứng** | So khớp XML theo từng dấu cách khi API không cam kết whitespace | Test lỗi do serializer thay formatting | XPath với ràng buộc cần thiết |
| **Quá lỏng** | Regex `.*` cho mã lỗi | Cho phép mã lỗi rỗng hoặc không đúng quy tắc | Pattern cụ thể hoặc so khớp một mã lỗi ổn định |
| **Quá lỏng** | `byType()` cho giá tiền nhưng không kiểm tra giá âm | Test xanh với `price=-500` | Kiểm thử bất biến nghiệp vụ |
| **Quá lỏng** | Chỉ assert status 200 | Body sai trường/kiểu vẫn có thể lọt | Assert field thực sự consumer sử dụng |
| **Thiếu nhánh** | Chỉ có case thành công | Không kiểm chứng `404`, `400`, dữ liệu rỗng | Bổ sung các contract theo test matrix |
| **Sai phía** | Regex ID đặt ở phía stub response thay vì producer assertion | Stub không có giá trị response mẫu ổn định | Đọc và sửa `consumer/producer` theo vị trí |

Chất lượng contract nằm ở **mức độ ràng buộc chính xác**, không nằm ở số lượng matcher. Thêm 20 JSONPath không cần thiết có thể làm bảo trì khó khăn mà vẫn bỏ sót một hành vi consumer thực sự phụ thuộc.

## 9. Không bỏ quên các nhánh lỗi và trường hợp dữ liệu rỗng

API giá sản phẩm có thể có thêm hai trường hợp:

### SKU không tồn tại

~~~http
GET /api/prices/SKU-404 HTTP/1.1
Accept: application/json
~~~

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json

{"code":"PRICE_NOT_FOUND","message":"Price is unavailable"}
~~~

Groovy DSL có thể viết một contract riêng:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Gia cua SKU khong ton tai'
    request {
        method 'GET'
        url '/api/prices/SKU-404'
        headers {
            accept(applicationJson())
        }
    }
    response {
        status 404
        headers {
            contentType(applicationJson())
        }
        body(
            code: 'PRICE_NOT_FOUND',
            message: 'Price is unavailable'
        )
    }
}
~~~

Generated test tương ứng cần có assertion `404` và `code == "PRICE_NOT_FOUND"`, không chỉ gọi endpoint rồi kiểm tra “có response”. Nếu `message` có thể được dịch hoặc thay đổi, hai bên cần quyết định có nên ràng buộc nguyên văn hay chỉ kiểm tra kiểu/định dạng, trong khi `code` vẫn ổn định.

### Danh sách giá rỗng

API khác, `GET /api/prices?category=no-match`, nếu đã công bố trả danh sách, có thể thống nhất:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

[]
~~~

Đọc generated test để xác nhận `200` **và JSON array rỗng** đã được kiểm tra. `[]` khác `{}`, `null`, chuỗi `"[]"` và `204 No Content`. Nếu consumer dùng một kiểu list, đổi shape có thể phá vỡ client ngay cả khi status vẫn 200.

**Tại sao không gộp tất cả vào một contract?** Mỗi tình huống nên có điều kiện request và response rõ ràng để producer test và stub không bị mơ hồ. Mục tiêu là bảo vệ các nhánh hành vi quan trọng, không phải tăng số file một cách cơ học.

## 10. Kiểm tra chất lượng assertion theo mức rủi ro consumer

Khi review, hãy bắt đầu từ **hành động mà consumer sẽ thực hiện**:

| Hành động của consumer | Rủi ro khi producer thay đổi | Assertion tối thiểu cần cân nhắc |
|---|---|---|
| Tính tiền đơn hàng | `price` mất hoặc đổi sang string | Field tồn tại, kiểu numeric đúng |
| Hiển thị đơn vị tiền | `currency` sai mã hoặc không khớp price | Kiểm tra currency theo quy ước và test ngữ nghĩa liên quan |
| Phân nhánh “có giá/không có giá” | Đổi `404` thành `200` với error body | Kiểm tra status và mã lỗi |
| Lưu tham chiếu giữ chỗ | `reservationId` sai định dạng | Regex cụ thể và kiểm tra giá trị mẫu stub |
| Hiển thị danh sách trống | `200 []` đổi thành `204` hoặc `null` | Kiểm tra status và shape danh sách |
| Xử lý message `PriceChanged` | Payload mất field bắt buộc | Assertion schema/field quan trọng, test handler consumer |
| Parse timestamp | `updatedAt` đổi kiểu hoặc timezone | Kiểm tra format, kiểu và parse nghiệp vụ nếu cần |

Sự thay đổi có được xem là **breaking change** hay không còn phụ thuộc những consumer đã triển khai. Ví dụ thêm field tùy chọn thường an toàn với parser bỏ qua field lạ, nhưng có thể phá vỡ parser nghiêm ngặt. Một generated producer test chỉ chứng minh implementation phù hợp **hợp đồng mới**, không tự chứng minh hợp đồng mới tương thích với mọi consumer cũ.

## 11. Một quy trình review generated test có thể lặp lại

### Bước 1: Ghi kỳ vọng trước khi sinh test

Từ contract nguồn và yêu cầu consumer, viết một bảng nhỏ:

~~~text
Contract: priceForSku101

Producer test phải:
  - Gửi GET /api/prices/SKU-101, Accept: application/json
  - Assert HTTP status 200
  - Assert response Content-Type JSON
  - Assert sku là SKU-101
  - Assert currency là VND
  - Assert price có kiểu number
  - Assert updatedAt khớp pattern đã công bố

Consumer test với stub phải:
  - Gửi đúng HTTP request mà ứng dụng dùng
  - Đọc được response mẫu có price 125000, currency VND
  - Xử lý được timestamp theo format cam kết
~~~

Viết kỳ vọng **trước** khi xem output giúp reviewer không nhầm “generator đã làm gì” với “mình muốn nó làm gì”.

### Bước 2: Sinh và chạy test phía producer

Lệnh Maven tham khảo nếu module đã cấu hình plugin đầy đủ:

~~~bash
./mvnw verify
~~~

Với Gradle, chạy những task sinh/chạy contract test do **phiên bản plugin và build dự án** cung cấp. Kiểm tra log để biết tệp DSL nào được đọc, generated test nào được biên dịch và test nào thực sự chạy. Một build xanh nhưng không phát hiện contract nào vẫn chưa phải bằng chứng kiểm thử.

### Bước 3: Mở generated test thật

Không dừng ở số lượng test. Đọc ít nhất một test đại diện có **giá trị cố định**, **regex**, **type matcher**, **error status** và **danh sách** nếu các loại đó có trong hợp đồng.

Checklist đọc:

- Test gọi producer thật trong test environment, không đơn thuần gọi stub?
- Request path, query, header và body đúng tình huống?
- Assertion cho status/header đủ chưa?
- JSONPath/XPath trỏ đúng vị trí?
- Regex và type matcher có giữ được yêu cầu consumer?
- Field nhạy cảm, kiểu dữ liệu và quan hệ nghiệp vụ nào chưa được kiểm tra?
- Test có bị disable, skip hoặc thất bại ở khâu setup không?

### Bước 4: Mở mapping/stub artifact thật

Một layout Maven thường gặp:

~~~text
target/stubs/META-INF/<groupId>/<artifactId>/<version>/mappings/
target/<artifactId>-<version>-stubs.jar
~~~

Đây là **đường dẫn ví dụ**; project có thể thay đổi output directory. Xem request matcher, status, header và response JSON trong mapping; kiểm tra rằng stub **được sinh từ đúng contract/revision** vừa kiểm tra.

### Bước 5: Chạy consumer test với Stub Runner

Consumer cấu hình client thật trỏ tới stub do Stub Runner khởi chạy. Với từng nhánh quan trọng, kiểm tra:

- Consumer gửi request phù hợp contract.
- Stub nhận đúng mapping, không rơi vào mapping khác.
- Consumer parse dữ liệu và thực hiện quyết định nghiệp vụ mong đợi.
- Test đang dùng **đúng phiên bản candidate stub**, không phải bản cũ từ local Maven cache hoặc artifact repository.

Nếu producer test xanh nhưng consumer test thất bại, đó có thể là dấu hiệu thay đổi không tương thích, stub mapping chưa đúng hoặc consumer có giả định chưa được đưa vào contract. Cần điều tra nguyên nhân, không chỉ sửa expected value để test qua.

### Bước 6: Ghi lại bằng chứng vào pull request

Nên lưu những thông tin sau:

- Revision của DSL và fixture.
- Vị trí/tên generated test đã review.
- Assertion được sinh cho các field quan trọng.
- Artifact stub cụ thể: group, artifact, version, classifier/build ID.
- Consumer test nào đã chạy với artifact đó.
- Những trường hợp chưa bao phủ và kế hoạch bổ sung.

## 12. Đưa việc đánh giá assertion vào CI

Một pipeline có thể tổ chức như sau:

~~~mermaid
sequenceDiagram
    participant Dev as PR/Developer
    participant Gen as SCC Generator
    participant Prod as Producer tests
    participant Stub as Candidate stub
    participant Cons as Consumer tests
    Dev->>Gen: Cập nhật Groovy/YAML DSL
    Gen->>Prod: Sinh generated contract tests
    Prod->>Prod: Chạy assertion với implementation thật
    alt Producer test đạt
        Gen->>Stub: Tạo stub cùng revision
        Stub->>Cons: Stub Runner lấy đúng artifact
        Cons->>Cons: Kiểm tra logic consumer
    else Test producer lỗi
        Prod-->>Dev: Chặn merge/phát hành
    end
    Cons-->>Dev: Kết quả tương thích
~~~

Bên cạnh việc chạy test, CI hoặc người review cần kiểm tra những **cổng chất lượng** sau:

1. **Contract được phát hiện:** generator đã đọc đúng DSL cần kiểm thử; không chấp nhận build xanh do không tìm thấy contract.
2. **Generated test không bị skip:** các assertion thực sự chạy trong job.
3. **Diff của generated assertion được xem khi thay đổi DSL nhạy cảm:** đặc biệt khi đổi matcher, field, status, kiểu hoặc shape.
4. **Fixture và matcher hợp lệ:** không quá cứng gây lỗi giả, không quá lỏng bỏ lọt hành vi.
5. **Stub có version truy vết được:** consumer test sử dụng cùng candidate revision.
6. **Kiểm tra backward compatibility:** nếu sửa nghĩa, xóa trường, đổi kiểu, đổi HTTP status hoặc message schema, cần đánh giá consumer cũ.

**Không nhất thiết commit toàn bộ generated test vào Git.** Nếu nhóm không commit mã sinh, vẫn có thể lưu artifact/log CI và kiểm tra khi cần. Điều bắt buộc là có khả năng **xem được assertion thực sự được sinh ra và được thực thi**, không phải máy móc dựa vào sự tồn tại của một file.

## 13. Bài tập: test xanh nhưng còn thiếu assertion nào?

### Đề bài

Một API trả:

~~~json
{
  "sku": "SKU-101",
  "price": -1,
  "currency": "USD",
  "updatedAt": "2026-19-99T08:30:00Z"
}
~~~

Hợp đồng yêu cầu `sku=SKU-101`, `currency=VND`; `price` phải là số **không âm** và `updatedAt` phải là thời điểm hợp lệ theo chuẩn mà API đã thỏa thuận.

Một reviewer đọc generated test rút gọn và thấy:

~~~text
assert HTTP status == 200
assert sku == "SKU-101"
assert price is of numeric type
assert updatedAt matches "[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z"
~~~

**Câu hỏi:**

1. Assertion nào có thể bắt `price=-1`?
2. Có kiểm tra `currency=VND` chưa?
3. Regex timestamp có tự bảo đảm ngày `19`, `99` là hợp lệ không?
4. Nếu consumer thực tế nhận `USD` và tính tiền theo VND, test nào cần bổ sung?
5. Có nên chỉ thêm `byRegex('.*')` vào mọi field để giảm test lỗi không?

### Gợi ý lời giải

1. **Chưa có.** `price` là số, nên điều kiện kiểu vẫn có thể thỏa. Cần ràng buộc nghiệp vụ `price >= 0` bằng test hoặc matcher phù hợp.
2. **Chưa.** Generated test rút gọn không có assertion cho `currency`. Nếu trường đó thực sự bị bỏ qua trong output thật, cần kiểm tra lại DSL hoặc cấu hình sinh test để bảo vệ mã tiền tệ.
3. **Không.** Regex chỉ xác minh chuỗi đúng *hình dạng*; cần kiểm tra tính hợp lệ của ngày-giờ theo quy tắc tương ứng.
4. Cần **producer contract test** xác nhận hành vi công bố và **consumer test** xác nhận client tính/hiển thị đúng theo currency; nếu có quy tắc quy đổi thì bổ sung test nghiệp vụ riêng.
5. **Không.** Regex `.*` quá rộng và thường làm mất khả năng phát hiện giá trị sai. Chỉ nới matcher khi có lý do dựa trên hợp đồng.

### Bài tập mở rộng: nhận diện sai phía

Trong contract Groovy cho API tạo reservation:

~~~groovy
body(
    reservationId: $(
        consumer('RSV-1001'),
        producer(regex('RSV-[0-9]+'))
    )
)
~~~

Giải thích vì sao **generated producer test** nên kiểm tra regex, trong khi **stub response** nên trả `RSV-1001`. Sau đó tự tìm các vị trí tương ứng trong file generated test và WireMock mapping của dự án mẫu.

## 14. Checklist nhanh trước khi chấp nhận thay đổi contract

- [ ] Hợp đồng nguồn nêu rõ hành vi mà consumer phụ thuộc.
- [ ] Generated test thực sự được sinh và chạy với producer implementation phù hợp.
- [ ] Status, header và các trường body quan trọng đều có assertion.
- [ ] JSONPath/XPath và matcher đúng chỗ, đúng phía, đúng loại dữ liệu.
- [ ] So khớp cố định chỉ dùng khi giá trị thực sự cần cố định.
- [ ] Regex đủ chặt; `byType()` không bị hiểu nhầm là kiểm tra mọi ràng buộc nghiệp vụ.
- [ ] Field thiếu, null, shape array/object và dữ liệu rỗng được đánh giá theo nhu cầu.
- [ ] Các nhánh thành công và lỗi quan trọng có contract/test phù hợp.
- [ ] Stub mapping không chồng lấn bất ngờ, phản hồi mẫu có đúng kiểu.
- [ ] Consumer chạy với Stub Runner và đúng phiên bản stub đã sinh.
- [ ] CI lưu được bằng chứng generated test, candidate stub và kết quả consumer test.
- [ ] Những thay đổi có thể phá vỡ consumer cũ đã được review và có kế hoạch chuyển đổi.

## 15. Ghi nhớ

**Đánh giá contract test phải bắt đầu từ assertion thực sự được sinh và chạy, không dừng ở file Groovy/YAML nguồn.** Một matcher có thể hợp lệ về cú pháp nhưng quá lỏng, đặt sai phía hoặc không bảo vệ được bất biến mà consumer phụ thuộc. Hãy đối chiếu **DSL → generated producer test → stub mapping → consumer test với Stub Runner**, đồng thời kiểm tra phiên bản artifact trong CI.

Spring Cloud Contract giúp phát hiện những thay đổi HTTP hoặc thông điệp không tương thích **trong phạm vi các tình huống đã khai báo và được thực thi**. Chất lượng kiểm chứng phụ thuộc vào việc chọn đúng trường cần ràng buộc, mức assertion đủ chặt và việc thật sự xem lại đầu ra của generator khi hợp đồng thay đổi.

# Matcher quá rộng làm bỏ lọt thay đổi không tương thích

## 1. Bài toán: test xanh nhưng giao tiếp thật đã bị phá

**Spring Cloud Contract (SCC)** là công cụ kiểm thử hợp đồng giữa **producer** (dịch vụ cung cấp HTTP API hoặc phát thông điệp) và **consumer** (dịch vụ gọi API hoặc xử lý thông điệp). Nhóm phát triển mô tả hành vi bằng **Groovy/YAML contract DSL**, sau đó dùng **Contract Verifier** để sinh producer tests, sinh stub artifacts và dùng **Stub Runner** để kiểm thử consumer trong CI.

Một điểm quyết định chất lượng của hợp đồng là **matcher**: điều kiện để công cụ nhận một request, response hoặc message là “phù hợp”. Matcher có thể diễn đạt giá trị chính xác, biểu thức chính quy, kiểu dữ liệu, JSONPath, số lượng phần tử hoặc quy tắc kiểm tra tùy chỉnh.

Nếu matcher được viết **quá rộng**, bài test có thể **PASS mặc dù producer đã tạo ra hành vi không tương thích** hoặc **consumer đã gửi request sai hợp đồng**. Đây là *false assurance* — tín hiệu an toàn giả.

Ví dụ đơn giản:

~~~text
Cam kết với Checkout:
  GET /api/inventory/SKU-123
  -> {"available":true,"quantity":12}

Producer sau lỗi:
  -> {"available":false,"quantity":12}

Matcher quá rộng:
  $.available: byType()       # chỉ yêu cầu là boolean

Kết quả có thể thấy:
  producer generated test: PASS
  Checkout nghiệp vụ: FAIL vì không cho đặt hàng
~~~

Matcher `byType()` vẫn có giá trị trong những trường hợp cần linh hoạt; nó chỉ không đủ nếu **giá trị true hoặc quy tắc available** là nội dung cam kết.

Bài này thuộc chương **Chất lượng hợp đồng**, tập trung vào **“Matcher quá rộng làm bỏ lọt thay đổi không tương thích”**. Mục đích không phải khuyên mọi giá trị phải so chính xác, mà là hướng dẫn chọn matcher **đủ chặt để bắt breaking change, đủ linh hoạt với dữ liệu thực sự biến thiên**.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt matcher ở **phía request** (stub matching) và **phía response** (producer test assertions).
2. Đánh giá khi nào `byType()`, regex, JSONPath, matcher tùy chỉnh hoặc equality là phù hợp.
3. Nhận diện các lỗi `.*`, optional field quá rộng, không kiểm tra boundary, bỏ qua arrays/status/headers và request matcher quá lỏng.
4. Viết ví dụ HTTP contracts bằng Groovy/YAML và xem chúng được diễn giải ở generated producer tests/WireMock mappings.
5. Thiết kế negative tests/mutation tests để **bắt buộc matcher đỏ** khi một thay đổi có thể phá consumer.
6. Tránh hai cực đoan: matcher **quá rộng** làm lọt regression và matcher **quá chặt** gây flaky hoặc khóa chặt dữ liệu ngẫu nhiên.
7. Đưa các kiểm tra chất lượng hợp đồng vào code review và CI, không chỉ dựa vào `BUILD SUCCESS`.
8. Phối hợp producer–consumer để xác nhận ý nghĩa nghiệp vụ của các trường và phạm vi tương thích.

## 2. Matcher là gì và xuất hiện ở những đâu?

Trong SCC, một hợp đồng HTTP thường có:

~~~text
Contract
  request
    method / url / queryParameters / headers / body
    matcher(s) cho request
  response
    status / headers / body
    matcher(s) cho response
~~~

Về mặt khái niệm:

- **Request side:** khi sinh stub, công cụ cần quyết định request từ consumer có **match** hợp đồng nào không.
- **Response side:** khi sinh producer test, công cụ cần quyết định response thật từ producer có **đáp ứng cam kết** không.
- **Message side:** có thể cần match trigger/input, output destination, headers và payload được phát.
- **Dynamic data:** ID, timestamp và token có thể không có giá trị cố định, nên cần predicate chặt hơn `equals` một ví dụ.

**Quan trọng:** cùng tên matcher không có nghĩa hai phía được kiểm tra y hệt. SCC có thể dùng **những phía dữ liệu khác nhau** khi sinh producer test và consumer stub. Vì vậy phải kiểm tra **generated Java tests và WireMock mapping** chứ không chỉ nhìn Groovy/YAML source.

## 3. Hai kiểu bỏ lọt khác nhau: response lỏng và request lỏng

| Vị trí quá rộng | Hậu quả | Ví dụ |
|---|---|---|
| **Response matcher trong producer test** | Chấp nhận response sai mà consumer không xử lý đúng | `available=false` vẫn pass vì chỉ kiểm kiểu boolean |
| **Request matcher trong consumer stub** | Trả response mong đợi cho request sai | Client gửi `quantity:"2"` thay vì number `2` nhưng vẫn nhận 201 |
| **Header/path/query matcher** | Không phát hiện sai phiên bản hoặc điều kiện routing | Bỏ qua `Accept` hoặc header required |
| **Message payload matcher** | Chấp nhận event thiếu trường/ngữ nghĩa sai | `eventType: "Unknown"` vẫn pass vì “có string” |
| **Array matcher** | Chấp nhận list rỗng/thiếu phần tử hoặc sai thứ tự quan trọng | Không phát hiện mất một line item |
| **Error matcher** | Chấp nhận status/body lỗi không đúng | Mọi HTTP 404 được xem là `SKU_NOT_FOUND` |

Một hệ thống có thể mắc nhiều lỗi cùng lúc. Ví dụ response producer bị nới matcher, rồi stub consumer cũng được tạo với request matcher lỏng: cả hai pipeline đều xanh nhưng hai dịch vụ thực không thể giao tiếp an toàn.

## 4. Một cách hình dung: tập hợp kết quả được chấp nhận

Giả sử hợp đồng nghiệp vụ chỉ cho phép response với `available=true` khi SKU-123 có quantity 12.

Tập **hành vi được chấp nhận** cần phản ánh các điều kiện:

~~~text
A = {
  response.status = 200,
  response.body.sku = "SKU-123",
  response.body.available = true,
  response.body.quantity = 12
}
~~~

Một matcher kiểu dữ liệu quá rộng có thể kiểm tra:

~~~text
M = {
  response.status = 200,
  sku là string bất kỳ,
  available là boolean bất kỳ,
  quantity là number bất kỳ
}
~~~

Khi `M` cho qua response mà `A` không cho phép, bài kiểm thử tạo **false negative** theo nghĩa *không phát hiện regression* (dù runner báo PASS).

Nhưng ngược lại, nếu contract cho phép `requestId` biến động và matcher buộc `requestId="req-1001"`, nó có thể từ chối response hợp lệ. Đó là **false failure** do matcher quá chặt.

Nguyên tắc thiết kế:

> **Matcher phải chặt với điều consumer phụ thuộc, linh hoạt với dữ liệu không ảnh hưởng giao tiếp công khai.**

Một predicate tốt không đơn giản là “regex phức tạp”; nó phải diễn đạt **quy tắc đúng**.

## 5. Định nghĩa rõ điều consumer thực sự cần

Trước khi chọn matcher, cùng consumer owner trả lời:

| Field/behavior | Điều cần bảo vệ | Matcher gợi ý |
|---|---|---|
| `sku` | Chính xác SKU đã yêu cầu | Equality hoặc liên hệ request–response |
| `available` | Đúng trạng thái tồn kho | Equality trong scenario cụ thể |
| `quantity` | Số lượng đúng theo fixture | Equality cho scenario cụ thể, thêm boundary scenarios |
| `requestId` | Có ID hợp lệ, thay đổi mỗi lần | Regex ràng buộc format, không hardcode |
| `updatedAt` | Timestamp đúng chuẩn và parse được | Timestamp/format matcher + semantic tests nếu cần |
| `status` | Giá trị enum được consumer nhận diện | Equality cho case hoặc whitelist |
| `price.amount` | Không âm, chính xác scale/currency | Kiểu số + range/custom predicate |
| `items` | Không rỗng trong scenario có items | Matcher có ràng buộc phần tử và count |
| HTTP status | 200/404/503 có semantics khác nhau | Assert status **chính xác** |
| Error code | `SKU_NOT_FOUND`, `INVENTORY_UNAVAILABLE` | Equality, không chỉ regex bất kỳ |

**Không thể suy ra toàn bộ policy từ kiểu JSON.** Boolean chỉ có hai giá trị, nhưng consumer có thể phụ thuộc rất mạnh vào đúng giá trị. String có thể biểu diễn enum, ID, timestamp hoặc mã lỗi — các miền giá trị đó không thể thay thế nhau.

## 6. Ví dụ xuyên suốt: Inventory Service và Checkout

Checkout gọi Inventory:

~~~http
GET /api/inventory/SKU-123 HTTP/1.1
Accept: application/json
~~~

Trạng thái fixture đã xác định:

~~~text
SKU-123:
  quantity = 12
  available = true
~~~

Producer cam kết response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"sku":"SKU-123","available":true,"quantity":12}
~~~

Một phiên bản producer lỗi:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"sku":"SKU-999","available":false,"quantity":12}
~~~

Có ít nhất hai regression:

1. `sku` không còn gắn đúng request.
2. `available` trái với fixture/quantity.

Nếu test chỉ assert body có `sku` string, `available` boolean và `quantity` number, response sai vẫn có thể qua. Cần có một **scenario cụ thể đủ chặt**, bên cạnh các matcher cho trường động.

## 7. Contract Groovy với các cam kết cố định

Tệp contract minh họa:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Checkout đọc tồn kho SKU-123 đã được seed'

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

Trong hợp đồng này, **body ví dụ** mô tả đúng fixture và không chủ động nới các field bắt buộc bằng matcher động. Khi cấu hình SCC generator/test đúng, generated producer test cần kiểm tra response thực theo cam kết. Nếu nhóm quyết định dùng explicit matchers, có thể mô tả các field quan trọng bằng **equality**, còn field biến động sử dụng matcher thích hợp.

**Không nên mặc định rằng body ví dụ luôn được kiểm tra chặt theo mọi thuộc tính trong tất cả phiên bản/configuration.** Đọc generated test để biết nó assert JSONPath nào, body equality theo chế độ nào và có bỏ qua field nào.

## 8. Phản ví dụ: response bodyMatchers chỉ kiểm tra kiểu

Giả sử cùng contract nhưng cấu hình response matcher:

~~~groovy
response {
    status OK()
    body(
        sku: 'SKU-123',
        available: true,
        quantity: 12
    )

    bodyMatchers {
        jsonPath('$.sku', byType())
        jsonPath('$.available', byType())
        jsonPath('$.quantity', byType())
    }
}
~~~

Về ý tưởng, các matchers này kiểm **kiểu** từng field, không kiểm cụ thể `SKU-123`/`true`/`12`. Chúng có thể phù hợp nếu các giá trị được phép thay đổi tự do, nhưng **không phù hợp** với fixture mà consumer yêu cầu tính nhất quán.

Một response như:

~~~json
{"sku":"SKU-999","available":false,"quantity":12}
~~~

vẫn giữ đúng kiểu string, boolean, number. **Không nên tin những generated assertions chỉ dựa trên type** để bảo vệ business semantics.

### Khi nào `byType()` là lựa chọn tốt?

- Field có thể thay đổi giá trị nhưng **kiểu dữ liệu** là điều cần giữ ổn định.
- Có scenario khác hoặc custom assertion kiểm tra **miền giá trị và quan hệ**.
- API không cam kết giá trị chính xác, ví dụ một count được cập nhật đồng thời bởi hoạt động khác.
- Đội ngũ chấp nhận rằng test này **không kiểm tra nội dung cụ thể** và bổ sung lớp kiểm tra tương ứng.

Nếu cần kiểm tra `available=true` của một fixture cụ thể, nên dùng equality trong scenario này.

## 9. Regex `.*` và biểu thức quá dễ chấp nhận

Một matcher kiểu:

~~~groovy
bodyMatchers {
    jsonPath('$.sku', byRegex('.*'))
}
~~~

hoặc:

~~~groovy
bodyMatchers {
    jsonPath('$.reservationId', byRegex('.+'))
}
~~~

có thể không bảo vệ đúng định dạng hoặc ý nghĩa:

- `.*` có thể cho qua chuỗi rỗng tùy semantics.
- `.+` thường chỉ nói có ít nhất một ký tự, không nói đây là ID hợp lệ.
- `[A-Za-z0-9]+` có thể chấp nhận `ERROR` ở chỗ cần `SKU-123`.
- Một regex không kiểm tra quan hệ với URL đã yêu cầu, ví dụ SKU trong response thuộc **đúng request** không.

Matcher có thể chính xác hơn:

~~~groovy
bodyMatchers {
    jsonPath('$.reservationId',
        byRegex('R-[0-9]{4,}'))
}
~~~

Tuy nhiên, regex `R-[0-9]{4,}` chỉ kiểm **cấu trúc** của reservation ID; nó vẫn không chứng minh ID thuộc đúng giao dịch vừa tạo hoặc tồn tại trong database.

**Lưu ý:** regex engine có thể dùng full match hoặc partial search tùy adapter/matcher. Hãy xem generated code/WireMock mapping và thử input có prefix/suffix sai; khi cần, dùng anchors `^...$` cho ý định toàn chuỗi, rồi xác nhận syntax hỗ trợ của phiên bản.

## 10. Regex số không phải kiểm tra ngữ nghĩa số

Một anti-pattern thường thấy là ép mọi dữ liệu động vào regex:

~~~text
"quantity": "12"
Regex: [0-9]+
~~~

Nếu contract thật yêu cầu JSON number:

~~~json
{"quantity":12}
~~~

thì JSON string `"12"` và JSON number `12` **khác kiểu**. Regex chạy trên biểu diễn string có thể vô tình che thay đổi kiểu nếu test framework hoặc converter chuyển kiểu trước khi match.

Cách bảo vệ:

1. Xác định **JSON type** được cam kết: number, string, boolean, object, array hoặc null.
2. Viết scenario cố định có equality nếu quantity được seed.
3. Nếu giá trị biến thiên, kiểm kiểu numeric **và miền hợp lệ** theo quy tắc.
4. Thêm negative tests với `"12"`, `-1`, `0`, `12.5`, `null` theo yêu cầu.
5. Kiểm tra generated test thật sự phân biệt kiểu, thay vì chỉ so String.
6. Kiểm consumer DTO và Jackson coercion configuration nếu consumer có thể âm thầm ép kiểu.

**Regex không thể tự thay thế tất cả type/range/semantic assertions.**

## 11. Optional, null, empty và missing là bốn trạng thái khác nhau

Xét một JSON object:

~~~json
{"note": null}
~~~

Nó khác:

~~~json
{}
~~~

và khác:

~~~json
{"note": ""}
~~~

Cũng khác một giá trị toàn khoảng trắng:

~~~json
{"note":"   "}
~~~

Nếu consumer phân biệt “không gửi trường” với “gửi null” (đặc biệt ở PATCH/merge-patch), matcher chỉ kiểm `note` là string khi có thể có thể bỏ lọt **sai semantics về presence**.

Một bảng:

| Trạng thái | Dạng JSON | Ý nghĩa có thể có |
|---|---|---|
| Missing | `{}` | Không thay đổi giá trị hoặc dùng default |
| Null | `{"note":null}` | Xóa/clear hoặc unknown |
| Empty | `{"note":""}` | Chuỗi rỗng có mặt |
| Blank | `{"note":"  "}` | Có ký tự nhưng chỉ whitespace |

Khi contract yêu cầu field **bắt buộc**, hãy xác nhận **field tồn tại** và **không null** theo rule. Khi field được phép optional, vẫn nên có **case riêng** cho vắng mặt và một case cho giá trị hợp lệ nếu consumer cần xử lý cả hai.

Một JSONPath predicate kiểu “có tồn tại path” có thể chưa đủ để phân biệt null/empty hoặc giới hạn kiểu. Hãy kiểm tra semantics JSONPath của generated test/WireMock phiên bản dùng.

## 12. Enum matcher rộng có thể phá consumer dù JSON type không đổi

Giả sử Checkout chỉ hiểu:

~~~json
{"status":"RESERVED"}
~~~

hoặc:

~~~json
{"status":"REJECTED"}
~~~

Producer mới trả:

~~~json
{"status":"PENDING_MANUAL_REVIEW"}
~~~

Nếu matcher là:

~~~groovy
bodyMatchers {
    jsonPath('$.status', byRegex('[A-Z_]+'))
}
~~~

thì cả ba giá trị có cùng kiểu/cấu trúc và test có thể **không phát hiện** consumer chưa có handler cho trạng thái mới.

Các lựa chọn:

- **Equality theo scenario**, ví dụ case success phải là `RESERVED`.
- **Whitelist** nếu contract chủ đích cho phép nhiều trạng thái đã công bố.
- **Consumer test** với tất cả enum values được hỗ trợ, đặc biệt unknown enum fallback nếu policy yêu cầu.
- **Review versioning** khi thêm enum value, vì “thêm một giá trị” có thể là breaking change với exhaustive switch.

Một matcher whitelist dạng regex cần được thiết kế cẩn thận:

~~~text
^(RESERVED|REJECTED)$
~~~

Dù vậy regex chỉ bảo vệ miền enum, không bảo đảm nghiệp vụ đã chọn đúng một giá trị cho input cụ thể. Với trường hợp có fixture cố định, equality thường rõ hơn.

## 13. Request matcher rộng: stub cho qua client gửi sai body

Một lỗi ngược chiều response: consumer gửi request sai nhưng Stub Runner vẫn trả response hợp đồng.

Producer yêu cầu:

~~~http
POST /api/reservations HTTP/1.1
Content-Type: application/json

{"sku":"SKU-123","quantity":2}
~~~

Consumer code sai có thể gửi:

~~~http
POST /api/reservations HTTP/1.1
Content-Type: application/json

{"productCode":"SKU-123","quantity":"2"}
~~~

Nếu stub chỉ match method/path, nó vẫn trả HTTP 201 và làm test consumer xanh. Khi gọi producer thật, request có thể bị reject với 400/422 hoặc được deserialize sai.

**Phân biệt:** producer generated test sẽ kiểm tra một request mẫu từ contract; nó không tự chứng minh mọi consumer đã serialize request đúng. Consumer Stub Runner test phải làm việc đó bằng **matcher đủ chặt cho request**.

## 14. WireMock mapping quá rộng và mapping có ràng buộc

Một mapping quá rộng:

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

WireMock chỉ cần method/path khớp. Không có điều kiện Content-Type hoặc JSON body, request sai vẫn nhận 201.

Một mapping **mang tính minh họa** chặt hơn:

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

Đây là **WireMock mapping minh họa**, không phải khẳng định SCC sẽ sinh chính xác JSON này từ một DSL cụ thể. Kiểm tra output thực để biết matcher dùng `equalToJson`, `matchesJsonPath`, regex hoặc rule khác.

Khi business cho phép các `sku` khác nhau, không nhất thiết phải khóa cứng `SKU-123`. Có thể dùng JSONPath/range phù hợp, **nhưng `quantity` vẫn phải là number đúng schema**, `sku` phải theo format công bố, và những required fields phải được match.

## 15. Header và HTTP status cũng là một phần hợp đồng

Các lỗi dễ lọt khi chỉ chăm chăm body:

- Producer đổi 201 Created thành 200 OK trong API create, consumer dựa trên 201.
- Producer bỏ `Content-Type: application/json`, client không giải mã response.
- Consumer không gửi `Accept` mà producer cần để content negotiation.
- Request bị thiếu `Idempotency-Key`, tạo reservation trùng khi retry.
- Producer đổi `Retry-After`/rate-limit headers mà consumer retry policy phụ thuộc.
- Message header `eventType` bị đổi nhưng payload vẫn parse được.

Nếu matcher response chỉ kiểm body fields, không có test rõ status/header hoặc base test bỏ qua những field ấy, pipeline có thể bỏ lọt breaking change. Cần kiểm tra **status và headers quan trọng** bằng equality/predicate phù hợp.

**Không nên cố assert tất cả headers do server tự sinh**, như `Date` hoặc `Server`, nếu chúng không thuộc cam kết công khai; làm vậy dễ tạo false failures. Chỉ giữ ràng buộc có giá trị đối với consumer.

## 16. Array: kiểu đúng nhưng số lượng hoặc nội dung sai

Xét API trả các reservation line items:

~~~json
{
  "reservationId": "R-1001",
  "items": [
    {"sku":"SKU-123","quantity":2},
    {"sku":"SKU-456","quantity":1}
  ]
}
~~~

Consumer cần ít nhất một item, không cho quantity âm và có thể cần bảo toàn thứ tự theo request. Một matcher chỉ kiểm `items` là array cho qua response:

~~~json
{"reservationId":"R-1001","items":[]}
~~~

hoặc:

~~~json
{
  "reservationId":"R-1001",
  "items":[{"sku":"SKU-999","quantity":-5}]
}
~~~

Nếu consumer phụ thuộc số dòng, tổng tiền hoặc thứ tự, đây là lỗi nghiêm trọng dù JSON vẫn hợp lệ.

Trong Groovy SCC, một số phiên bản hỗ trợ ràng buộc **số phần tử** qua `byType` với `minOccurrence/maxOccurrence`:

~~~groovy
response {
    status OK()
    body(
        items: [
            [sku: 'SKU-123', quantity: 2]
        ]
    )

    bodyMatchers {
        jsonPath('$.items', byType {
            minOccurrence(1)
            maxOccurrence(20)
        })
    }
}
~~~

Đây là ví dụ về **ràng buộc cardinality**, không phải kiểm toàn bộ business invariants. Cú pháp `minOccurrence/maxOccurrence` và vị trí áp matcher cần đối chiếu phiên bản SCC đang dùng, rồi xem generated tests.

Để bảo vệ nội dung, có thể dùng **contract riêng cho case rỗng/một/nhiều phần tử**, matcher theo từng path hoặc custom assertions. Với danh sách có thể sắp xếp tự do, đừng assert thứ tự nếu contract không yêu cầu; kiểm **tập hợp phần tử và định danh** theo quy tắc.

## 17. Decimal, money và precision: number là chưa đủ

Một field thanh toán có thể có dạng:

~~~json
{"amount":125000,"currency":"VND"}
~~~

Contract thực tế có thể quy định số nguyên VND, amount không âm và currency thuộc tập được hỗ trợ. Matcher kiểu number chưa đủ để phát hiện:

~~~json
{"amount":-1,"currency":"UNKNOWN"}
~~~

hoặc response đúng kiểu nhưng sai đơn vị:

~~~json
{"amount":125000.75,"currency":"VND"}
~~~

Cần xác định:

- JSON number hay string?
- Đơn vị là đồng, xu hay giá trị decimal?
- Có chấp nhận phần thập phân không?
- Giá trị tối thiểu/tối đa là bao nhiêu?
- Currency là ISO code, enum nội bộ hay whitelist?
- Độ chính xác và chính sách rounding thế nào?

Matcher có thể bảo vệ kiểu/range/regex; nhưng **test nghiệp vụ vẫn cần kiểm giá trị chính xác của case cố định**. Với invariant liên trường như amount/currency/tax, dùng contract fixture cùng custom/integration assertion đọc đủ fields; đừng hy vọng từng `byType()` riêng lẻ chứng minh tính nhất quán.

## 18. Timestamp và UUID: không khóa cứng nhưng cũng không để `.*`

Các field thường biến động:

~~~json
{
  "requestId": "a38cf5f0-2d46-45ac-8b6b-5ef9299142a9",
  "createdAt": "2026-11-24T05:30:00Z"
}
~~~

Khóa cứng hai chuỗi này dễ tạo test flaky. Nhưng matcher `.+` cũng cho qua:

~~~json
{"requestId":"NOT_A_UUID","createdAt":"yesterday"}
~~~

Hướng bảo vệ:

1. Xác định format công bố: UUID/ULID, ISO-8601, epoch millis, v.v.
2. Dùng `byRegex`/`byTimestamp`/`byDate` tương ứng DSL.
3. Kiểm timezone/offset nếu consumer phụ thuộc; pattern chưa bảo đảm semantics.
4. Nếu `createdAt` phải nằm trong khoảng thời gian, dùng custom/integration assertion với clock kiểm soát.
5. Nếu `requestId` phải echo request header, kiểm quan hệ với request, không chỉ format.
6. Thử negative values sai chuẩn hoặc sai correlation.

Regex UUID đúng định dạng chưa chứng minh request ID duy nhất hoặc trace được. Phân biệt **format contract** với **business invariant**.

## 19. Groovy: equality cho fixture cố định, matcher hẹp cho dữ liệu động

Một contract GET với requestId động:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Tồn kho SKU-123 phải còn hàng'

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
            quantity: 12,
            requestId: 'a38cf5f0-2d46-45ac-8b6b-5ef9299142a9'
        )
        bodyMatchers {
            jsonPath('$.sku', byEquality())
            jsonPath('$.available', byEquality())
            jsonPath('$.quantity', byEquality())
            jsonPath('$.requestId', byRegex(
                '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
            ))
        }
    }
}
~~~

- `sku/available/quantity` quan trọng với fixture đã biết, nên dùng equality.
- `requestId` được match theo format thay vì giá trị cố định.
- Body sample của `requestId` vẫn cung cấp dữ liệu mẫu để sinh stub response.
- Regex trên chỉ kiểm dạng `8-4-4-4-12`; UUID v4 chuẩn còn có quy tắc version/variant.
- Nếu response có field tùy chọn bổ sung, cần xác định policy về unknown fields.

**Quan trọng:** cách SCC kết hợp `body` với `bodyMatchers`, biên dịch regex, và sinh assertions phụ thuộc version. Sau generation, đọc **Java producer test** và **WireMock mapping**; đừng chỉ tin contract source.

## 20. YAML DSL: mô tả matcher response có chủ đích

~~~yaml
description: Inventory trả tồn kho SKU-123
name: get_stock_sku123

request:
  method: GET
  url: /api/inventory/SKU-123
  headers:
    Accept: application/json

response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    available: true
    quantity: 12
    requestId: a38cf5f0-2d46-45ac-8b6b-5ef9299142a9
  matchers:
    body:
      - path: $.sku
        type: by_equality
      - path: $.available
        type: by_equality
      - path: $.quantity
        type: by_equality
      - path: $.requestId
        type: by_regex
        value: '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
~~~

Ý tưởng trung tâm là **không sử dụng `type: by_type` cho field mà consumer cần giá trị cụ thể**.

Các loại matcher và cấu trúc YAML SCC phụ thuộc version; hãy xác nhận contract parse thành công, xem generated assertions và mappings. Nếu plugin version không hỗ trợ cú pháp minh họa, đổi sang dạng được reference của version đó định nghĩa, **không bỏ matcher quan trọng để làm build xanh**.

Với body field cố định, có thể bỏ explicit equality matcher nếu **default assertion** của generator đã bảo vệ đúng path và giá trị. Đây phải là kết luận từ generated code.

## 21. YAML request matchers: linh hoạt có kiểm soát

Một YAML contract POST mẫu:

~~~yaml
description: Tạo reservation cho một SKU hợp lệ
name: create_reservation

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
        value: 'SKU-[0-9]{3}'
      - path: $.quantity
        type: by_equality

response:
  status: 201
  headers:
    Content-Type: application/json
  body:
    reservationId: R-1001
    status: RESERVED
~~~

- `sku` biến thiên trong format hẹp.
- `quantity` trong scenario này phải bằng `2`.
- Header Content-Type phải được gửi đúng.
- Status response đúng là `201`.

Ví dụ chưa bảo vệ toàn bộ khoảng quantity nguyên dương. Muốn range 1–100, cần scenario boundary hoặc matcher/custom validation tương ứng với plugin version.

**Không đánh giá độ chặt của request matcher chỉ bằng YAML source**: mở mapping WireMock thực và thử một request sai field/type để chắc chắn nó không bị nhận.

## 22. JSONPath chọn field chứ không tự nói giá trị đúng

JSONPath thường dùng:

~~~text
$.sku
$.available
$.items[0].sku
$.error.code
~~~

Một predicate chỉ nói `$.error.code` tồn tại có thể cho qua:

~~~json
{"error":{"code":"UNEXPECTED_FAILURE"}}
~~~

trong khi consumer chỉ hiểu:

~~~json
{"error":{"code":"SKU_NOT_FOUND"}}
~~~

Cần ràng buộc **giá trị** bằng equality hoặc regex whitelist, chứ không chỉ kiểm path tồn tại.

Cũng cần phân biệt path thiếu, path có null, chuỗi rỗng và giá trị sai kiểu. Các JSONPath implementations có thể khác nhau ở cách biểu diễn missing/null; hãy viết **negative cases** và kiểm generated test/WireMock mapping đã chọn đúng semantics.

## 23. Quan hệ giữa các field: type riêng lẻ không chứng minh invariant

Response:

~~~json
{"quantity":0,"available":true}
~~~

Hai field đều có kiểu hợp lệ, nhưng nếu quy tắc là `available = (quantity > 0)` thì response **sai**.

Để bảo vệ:

1. Dùng fixture quantity=0 và assert available=false.
2. Dùng fixture quantity>0 và assert available=true.
3. Thêm boundary scenarios.
4. Nếu values biến thiên phức tạp, dùng custom assertion hoặc producer integration test đọc **cả hai fields**.
5. Không dùng hai `byType()` riêng lẻ và kết luận đã chứng minh quan hệ.

Một `byCommand` matcher thường nhận **giá trị path**. Nếu invariant liên quan nhiều fields, phải cung cấp đủ dữ liệu hoặc bổ sung integration assertion; không tự suy rằng method nhận một field có thể kiểm cả JSON object.

## 24. Custom assertion: khi regex và type chưa đủ

Một số quy tắc, ví dụ quantity phải là số nguyên không âm và không vượt giới hạn, cần assertion có ý nghĩa hơn một regex tùy ý. Groovy DSL có thể gọi method trong base test:

~~~groovy
response {
    status OK()
    body(
        sku: 'SKU-123',
        quantity: 12
    )
    bodyMatchers {
        jsonPath('$.quantity',
            byCommand('assertValidQuantity($it)'))
    }
}
~~~

Một helper Java minh họa:

~~~java
import java.math.BigDecimal;

public void assertValidQuantity(Object value) {
    if (!(value instanceof Number)) {
        throw new AssertionError(
            "quantity phải là JSON number");
    }

    BigDecimal quantity = new BigDecimal(value.toString());

    if (quantity.signum() < 0) {
        throw new AssertionError("quantity không được âm");
    }

    if (quantity.stripTrailingZeros().scale() > 0) {
        throw new AssertionError("quantity phải là số nguyên");
    }

    if (quantity.compareTo(new BigDecimal("1000")) > 0) {
        throw new AssertionError("quantity vượt giới hạn");
    }
}
~~~

**Lưu ý phiên bản:** kiểu dữ liệu runtime do JSONPath trả và cách generated test truyền `$it` có thể khác; xem Java được sinh để dùng method signature phù hợp. Nếu scenario yêu cầu **chính xác quantity=12**, custom assertion “0–1000” vẫn **quá rộng**; equality của fixture mới đủ chặt.

Custom assertions cũng có thể sai: một helper chỉ làm `assert value != null` không thay thế validation nghiệp vụ. Phải thử mutation với số âm, số thập phân, giá trị quá lớn và field không phải number để chứng minh khả năng phát hiện.

## 25. Messaging contracts cũng có thể bị matcher quá rộng

Một message producer phát event:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'inventoryChanged'

    input {
        triggeredBy('triggerInventoryChanged()')
    }

    outputMessage {
        sentTo('inventory.events')
        headers {
            header('eventType', 'InventoryChanged')
        }
        body(
            sku: 'SKU-123',
            available: true,
            quantity: 12
        )
    }
}
~~~

Nếu test chỉ kiểm “có message”, “body là JSON” hoặc “header eventType có string”, nó có thể bỏ lọt:

- Đổi `eventType` thành một tên consumer dispatcher không biết;
- Đổi `sku` sang `productCode`;
- Đổi `quantity` number sang string;
- Gửi `available=false` dù quantity > 0;
- Phát đến destination/route khác;
- Thiếu schema version/correlation header quan trọng;
- Đổi cấu trúc event envelope.

Generated messaging tests cần kích hoạt **production use case** rồi quan sát output thật qua test binder/message verifier phù hợp. Nếu base test **tự gửi payload mẫu** thay application code, test có thể xanh giả.

Contract tests không mặc nhiên bảo vệ broker partition, ordering, at-least-once delivery, retry hoặc DLQ. Nếu consumer phụ thuộc vào chúng, cần thêm **broker integration tests** riêng.

## 26. Matcher quá rộng và quá chặt: hai cực đoan cần tránh

| Vấn đề | Ví dụ | Hậu quả |
|---|---|---|
| **Quá rộng** | Regex `.*` cho error code | Bỏ lọt breaking change |
| **Quá chặt** | Assert timestamp luôn bằng một giá trị | Test fail với response hợp lệ |
| Request quá rộng | Chỉ kiểm POST path, bỏ body | Client serialize sai vẫn pass |
| Request quá chặt | Bắt đúng một random request ID | Request hợp lệ bị stub từ chối |
| Response quá rộng | `byType()` cho enum | Enum mới không được phát hiện |
| Response quá chặt | Từ chối mọi field bổ sung dù API cho phép | Chặn additive change hợp lệ |
| Array quá rộng | Chỉ kiểm có type array | List rỗng vẫn pass |
| Array quá chặt | Bắt thứ tự khi contract không cam kết | Test flaky với response được phép |

**Chất lượng cao không đồng nghĩa có nhiều assertions.** Matcher tốt bảo vệ đúng tập hành vi mà consumer phụ thuộc và không khóa những chi tiết ngẫu nhiên.

Đánh giá matcher bằng hai câu hỏi:

1. **Một thay đổi nào có thể khiến consumer thực sự hỏng mà matcher vẫn PASS?**
2. **Một thay đổi nào được API cho phép nhưng matcher lại FAIL vô ích?**

Nếu có câu trả lời ở một trong hai phía, cần chỉnh matcher hoặc tách test scenarios.

## 27. Không phải mọi field bổ sung đều nên bị từ chối

Nhiều API cho phép response JSON có thêm optional field; consumer bỏ qua trường không biết. Trong trường hợp đó, bắt body phải có **chính xác tập field hiện tại** có thể gây false failures.

Nhưng cũng có consumer strict JSON schema hoặc Jackson config từ chối unknown fields. Cần thống nhất:

- Consumer có allow unknown fields không?
- Schema là **open** hay **closed**?
- Có field nhạy cảm nào không được phép rò rỉ trong response?
- Field mới có làm đổi semantics dù field cũ vẫn có mặt không?
- Có message schema registry policy về backward/forward compatibility không?

Khi API hỗ trợ mở rộng, chỉ assert **các field công khai bắt buộc và invariants**, có thể cho thêm field phù hợp. Khi schema đóng, cần schema validation hoặc kiểm chặt cấu trúc theo contract.

Không bật ignore-extra-elements chỉ để build xanh mà chưa hiểu **chính sách tương thích** của các consumer.

## 28. HTTP 404 unmatched stub không phải business error 404

WireMock có thể trả HTTP 404 khi request **không match mapping**. Đây là lỗi giao tiếp/test setup, khác với contract business error:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json

{"code":"SKU_NOT_FOUND","message":"SKU does not exist"}
~~~

Một client test yếu chỉ assert status 404 có thể bị đánh lừa nếu nó gửi sai URL và Stub Runner trả **unmatched 404**. Một consumer mapper không đủ chặt:

~~~java
// Phản ví dụ: coi mọi 404 là SKU không tồn tại.
if (status == 404) {
    throw new InventoryNotFoundException();
}
~~~

Để kiểm tra:

1. Có mapping **business 404** riêng trong stubs artifact không?
2. Request từ client có match đúng method, path, query, headers và body không?
3. Response có **error code/body** đúng contract không?
4. Test có assert mã lỗi nghiệp vụ, không chỉ HTTP status không?
5. Khi nghi mismatch, kiểm WireMock request journal/near misses.

Không nên dùng unmatched 404 để làm PASS cho bài test lỗi nghiệp vụ. Nếu request không match, đó thường là dấu hiệu phải **sửa client hoặc contract matcher**, không phải cách giải thích rằng SKU không tồn tại.

## 29. Stale stub hoặc fake producer có thể làm matcher mới mất tác dụng

Một matcher trong source có thể đã được sửa chặt nhưng pipeline vẫn dùng artifact cũ:

~~~text
Producer candidate B:
  contract mới yêu cầu error.code == SKU_NOT_FOUND

Consumer Stub Runner:
  tải stubs JAR A cũ (matcher lỏng)

Consumer result:
  PASS, nhưng không liên quan đến candidate B
~~~

Bằng chứng cần có:

1. Contract source đã review thuộc commit/revision nào?
2. Generated producer Java test có assertion mới không?
3. Test có thực sự chạy trên producer implementation không?
4. Stubs JAR được sinh từ đúng contract candidate không?
5. Stub Runner resolve version/timestamp/digest nào?
6. WireMock đã load mappings của JAR mới không?
7. Consumer test dùng HTTP client/message handler thật không?
8. Negative tests có chứng minh matcher mới bắt sai không?

**Không nên chỉ nhìn version string `-SNAPSHOT`**. Maven/Gradle/repository proxy/Stub Runner cache có thể khiến artifact khác nội dung với ứng viên. Cách đáng tin là dùng **candidate version duy nhất gắn commit** và digest, hoặc ghi resolved timestamped snapshot cùng provenance.

## 30. Test chỉ assert HTTP status không bảo vệ body schema

Consumer test:

~~~java
assertThat(response.statusCode()).isEqualTo(200);
~~~

có ích cho một điều kiện HTTP, nhưng không xác minh body, kiểu field, error mapping hoặc business outcome.

Producer generated test cũng có thể yếu nếu chỉ kiểm:

~~~text
expect status == 200
expect Content-Type == application/json
~~~

Một body sai:

~~~json
{"sku":"WRONG","available":false,"quantity":-1}
~~~

vẫn có status và header đúng.

Cần xây **bảng cam kết → assertion thực thi → negative mutation bị phát hiện**, không chỉ đếm số tests hoặc regex matchers. Đừng coi `Tests run: 100` là bằng chứng rằng tất cả hành vi quan trọng đều được bảo vệ.

## 31. Negative tests chứng minh request matcher có khả năng từ chối

Với contract POST `/api/reservations`, cần test ít nhất một số trường hợp **không được match**:

| Request thử | Kỳ vọng với stub matching đúng |
|---|---|
| `{"sku":"SKU-123","quantity":2}` | Match scenario hợp lệ |
| `{"productCode":"SKU-123","quantity":2}` | Không match vì thiếu `sku` |
| `{"sku":"SKU-123","quantity":"2"}` | Không match khi contract yêu cầu number |
| `{"sku":"SKU-123","quantity":-5}` | Không match nếu contract quy định positive quantity |
| `{"sku":"","quantity":2}` | Không match nếu SKU bắt buộc nonempty |
| Header `Content-Type` sai | Không match nếu content negotiation là requirement |
| URL sai `/api/reservation` | Không match path đúng |
| Query sai/thiếu required parameter | Không match scenario yêu cầu query |

**Cẩn thận:** một test “không match stub” không nên kết luận dựa chỉ vào HTTP 404, vì có thể có mapping fallback khác hoặc một business 404 chủ động. Khi cần, xem request journal, matched stub ID và mapping priority. Nếu dùng một **catch-all mapping**, nó phải được phân loại/test rõ, tránh che việc không match.

Một số request sai như quantity=-5 có thể **vẫn match** một stub cố tình mô tả **business validation 422**; điều quan trọng là nó **không được match nhầm happy-path 201**. Ma trận negative tests cần nêu rõ expected scenario, không chỉ nói “mọi input xấu phải 404”.

## 32. Mutation tests: biến một contract thành phép thử có thể chứng minh chất lượng

**Mutation testing** ở ngữ cảnh này là cố tình làm sai một hành vi quan trọng của producer hoặc consumer trong nhánh thử, rồi kiểm tra contract suite có chuyển **đỏ** hay không.

Ví dụ ở Inventory producer:

~~~java
// Logic đúng theo fixture SKU-123 quantity=12:
return new StockResponse("SKU-123", true, 12);
~~~

Thử mutation:

~~~java
// Cố tình sai trong nhánh thử, KHÔNG merge:
return new StockResponse("SKU-123", false, 12);
~~~

Nếu matcher cho `$.available` chỉ là `byType()`, test có thể vẫn PASS; nếu equality yêu cầu `true`, test phải FAIL.

Ma trận mutation gợi ý:

| Mutation cố ý | Matcher yếu có thể bỏ lọt | Matcher/test cần bắt |
|---|---|---|
| `available:true` → `false` | `byType()` | Equality theo scenario |
| `sku:SKU-123` → `SKU-999` | `byRegex('SKU-.*')` | Equality/correlation request |
| `quantity:12` → `-1` | `byType()` | Equality hoặc nonnegative invariant |
| JSON number → string | Regex trên string representation | JSON type strict / negative test |
| `status:RESERVED` → `UNKNOWN` | `[A-Z_]+` | Whitelist/equality |
| `items` 2 phần tử → rỗng | Array byType | Cardinality & scenario assertions |
| `error.code` đổi | Only status 404 | Equality error code |
| POST body `sku` → `productCode` | Request matcher chỉ method/path | Required JSONPath + body matching |
| `Content-Type` bị bỏ | Matcher body-only | Header assertion |
| Response timestamp sai format | `.+` | Date/timestamp validation |

### Các bước thử mutation

1. Bắt đầu ở commit có contract được hai bên thống nhất.
2. Chạy generated producer tests với implementation đúng, ghi tên test/ran count.
3. Làm **một mutation tại một thời điểm** để biết lỗi thuộc trường nào.
4. Chạy lại test; mong đợi một assertion liên quan **FAIL**.
5. Nếu test vẫn PASS, xem generated Java: matcher có thực sự assert field đó không?
6. Nếu test không chạy, sửa test runner/generation trước, không thay contract.
7. Khôi phục mutation và chạy test PASS trở lại.
8. Ghi “mutation detected/escaped” cùng nguyên nhân và quyết định bổ sung contract/test.

**Thử nghiệm này khác bài Content QA tổng thể**: nó là phương pháp kiểm tra chất lượng matcher được người học áp dụng trên dự án thử; không yêu cầu chỉnh repository ngoài hai tệp được giao trong bước biên soạn.

## 33. Boundary scenarios tốt hơn một regex chung chung

Một matcher `quantity là number` chưa kiểm tra các ngưỡng:

~~~text
quantity = -1    -> invalid
quantity = 0     -> out of stock
quantity = 1     -> available
quantity = 12    -> available
quantity = 1000  -> có thể còn trong giới hạn
quantity = 1001  -> invalid hoặc giới hạn khác
~~~

Một bộ contracts theo scenario có thể bảo vệ:

| Fixture | Expected response | Quy tắc được bảo vệ |
|---|---|---|
| SKU-000, quantity=0 | `available=false` | Biên 0 |
| SKU-001, quantity=1 | `available=true` | Biên 1 |
| SKU-123, quantity=12 | `available=true` | Positive quantity |
| SKU-404, không tồn tại | 404 + `SKU_NOT_FOUND` | Business error |
| SKU lỗi format | 400/422 theo API | Input validation |
| Inventory unavailable | 503 + error code | Error/retry policy |

Mỗi contract có request/response rõ ràng hoặc điều kiện producer state phù hợp. **Không nhất thiết nhét mọi giá trị vào một matcher regex duy nhất**. Các scenario đơn giản, có chủ ý thường giúp review và debug tốt hơn một predicate phức tạp không ai hiểu.

Khi backend dùng database/state, base test phải tạo fixture ổn định hoặc setup state tương ứng rồi gọi code production. Không dùng fake controller chỉ trả response hợp đồng vì sẽ phá mục tiêu producer verification.

## 34. Kiểm consumer: sửa request sai phải làm Stub Runner từ chối đúng case

Một consumer compatibility test nên gọi **HTTP client thật**, không mock chính client:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties =
    "inventory.base-url=http://localhost:18081")
@AutoConfigureStubRunner(
    ids = "com.example:inventory-service:1.4.0-rc.pr173:stubs:18081",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class InventoryConsumerContractTest {

    @Autowired
    InventoryClient inventory;

    @Test
    void usesInventoryProtocol() {
        StockResponse stock = inventory.getStock("SKU-123");

        assertThat(stock.sku()).isEqualTo("SKU-123");
        assertThat(stock.available()).isTrue();
        assertThat(stock.quantity()).isEqualTo(12);
    }
}
~~~

Các class `InventoryClient`/`StockResponse` là **ví dụ của consumer**, không phải SCC API có sẵn. `LOCAL` giả định stub đã được install vào local repository thích hợp. Nếu dùng CI nhiều container, cần repository REMOTE hoặc phân phối artifact có provenance.

Phép thử đối chứng:

1. Cho client gửi `/api/stock/SKU-123` thay vì `/api/inventory/SKU-123`.
2. Nếu matcher/request path đúng, request phải không match happy-path stub.
3. Cho client gửi body `{"quantity":"2"}` thay vì number khi hợp đồng yêu cầu number.
4. Nếu matcher đúng, test phải phát hiện protocol mismatch hoặc business error theo scenario.
5. Khôi phục client đúng, test đạt.
6. Xem Stub Runner logs/request journal để xác nhận **request đã thật sự đến server**.

Nếu test vẫn PASS dù client không gửi request, có khả năng client đang bị mock hoặc test chỉ kiểm một DTO tự tạo. Khi ấy **matcher nào trong stubs JAR cũng không được thực thi**.

## 35. Chất lượng matcher còn phụ thuộc artifact provenance

Trong CI producer–consumer, chuỗi bằng chứng cần được nối:

~~~mermaid
flowchart TD
    A["Contract source có matcher đúng"] --> B["Generate producer tests"]
    B --> C{"Generated tests thực thi và đạt?"}
    C -- "Không" --> X["BLOCK"]
    C -- "Có" --> D["Generate mappings + stubs JAR"]
    D --> E["Publish candidate version + digest"]
    E --> F["Stub Runner resolve exact candidate"]
    F --> G["Consumer client thật gửi request"]
    G --> H{"Matching và business assertions đạt?"}
    H -- "Không" --> X
    H -- "Có" --> I["Ghi CI evidence + compatibility decision"]
~~~

Một matcher đã sửa ở contract source nhưng generated test không regenerate hoặc Stub Runner còn tải stubs JAR cũ thì **không được áp dụng** vào những bài test đã chạy.

Cần xác nhận:

- Generated test có assertions mới và không bị skip;
- WireMock mapping có bodyPatterns/header/URL matcher như mong muốn;
- Producer test base gọi implementation thật;
- Candidate artifact có đúng commit/version/classifier và checksum;
- Consumer Stub Runner nạp đúng artifact và test client gọi đúng port;
- Negative mutations chứng minh sai field/path bị bắt;
- CI report có executed counts, artifact identity và test result.

Không thể chỉ dựa vào một dòng `BUILD SUCCESSFUL` để kết luận matcher đã bảo vệ compatibility.

## 36. Checklist review một matcher: từ ý nghĩa tới generated code

Khi code review contract, hãy xem lần lượt:

1. **Bối cảnh nghiệp vụ:** consumer phụ thuộc chính xác vào field/behavior nào?
2. **Schema:** field có required không, type gì, nullability thế nào?
3. **Giá trị:** equality, enum/range, regex format hay dynamic value?
4. **Quan hệ liên trường:** matcher có bỏ lọt trạng thái mâu thuẫn không?
5. **Request constraints:** method/path/query/headers/body có đủ chặt không?
6. **Response constraints:** status/header/body/error code có được assert không?
7. **Array:** min/max count, các item required và thứ tự có thuộc contract không?
8. **Message:** event type, destination, headers, payload schema được bảo vệ thế nào?
9. **Compatibility policy:** unknown fields, enum evolution và deprecation được quyết định chưa?
10. **Generator semantics:** generated Java test có đúng predicates không?
11. **Stub semantics:** WireMock mapping sinh ra có đúng request matching không?
12. **Mutation evidence:** thử một value sai có làm test đỏ không?
13. **Artifact freshness:** consumer test dùng mapping của candidate hay artifact cũ?
14. **Ownership:** producer/consumer reviewers có thống nhất điều nào linh hoạt và điều nào bất biến?

Không nên phê duyệt regex `.*` hoặc `byType()` chỉ vì “test đã xanh”. Review cần một câu giải thích: **matcher này đang cố ý cho phép tập giá trị nào, tại sao tập đó an toàn cho những consumer được hỗ trợ?**

## 37. Quy tắc lựa chọn matcher theo độ ổn định của field

| Field | Mức biến động | Chiến lược |
|---|---|---|
| HTTP status theo scenario | Cố định | Exact equality |
| Business error code | Cố định theo case | Exact equality |
| Request SKU trong response | Gắn với request | Equality/correlation |
| `available` cho fixture seed | Cố định | Equality |
| `quantity` cho fixture seed | Cố định | Equality |
| Generated requestId | Động có format | Regex đủ chặt, correlation nếu cần |
| `createdAt` | Động có semantics | Date/timestamp matcher + time checks phù hợp |
| `amount` | Động có domain | Type + range + currency/invariant |
| Enum status | Miền hữu hạn | Equality/whitelist + evolution tests |
| `items` | Collection | Type, cardinality, element schema và scenario checks |
| Optional feature field | Optional theo policy | Presence/null/absent scenarios |
| Unknown response property | Tùy compatibility policy | Open/closed schema decision |
| Authentication token | Động và nhạy cảm | Structure/required presence; không hardcode secret |

Quy tắc không phải luôn “exact > regex > type”. Có những field có thể biến động mạnh và chỉ cần loại dữ liệu; có field chỉ nên xuất hiện trong một trạng thái. **Độ chặt đúng là độ chặt của cam kết**, không phải độ phức tạp cú pháp matcher.

## 38. Những cách “sửa nhanh” khiến chất lượng giảm

| Triệu chứng | Sửa sai thường gặp | Cách xử lý đúng |
|---|---|---|
| Test fail vì `available=false` | Đổi `byEquality()` thành `byType()` | Xác định bug producer hay contract requirement đổi |
| Test fail vì timestamp khác | Đổi thành regex `.*` | Dùng timestamp/format matcher phù hợp |
| Consumer stub không match request | Bỏ mọi bodyPattern | So request thật với contract, sửa client hoặc matcher có chủ đích |
| API thêm enum mới | Dùng `[A-Z_]+` | Review unknown-enum policy và consumer tests |
| Array test đỏ khi list rỗng | Bỏ minOccurrence | Xác định list rỗng hợp lệ hay producer regression |
| Business error test không match | Chỉ assert HTTP status | Kiểm error code/body và unmatched 404 |
| Generated producer test không compile | Disable test/generation | Sửa plugin/test base/cú pháp DSL |
| Consumer dùng stub cũ | Bật latest và hi vọng refresh | Pin candidate version/digest, kiểm loader |
| Test đỏ do database fixture | Mock cả service trả response mẫu | Sửa fixture, giữ production behavior |
| Unit test mock client xanh | Tuyên bố consumer compatibility PASS | Thêm test dùng HTTP client thật + Stub Runner |

Một matcher lỏng được đưa vào để “giúp CI xanh” có thể **loại bỏ chính khả năng phát hiện breaking change**. Mỗi lần nới matcher phải có review và câu trả lời rõ về ảnh hưởng tới những consumer đang hoạt động.

## 39. Bài thực hành A — Đổi byType thành matcher bảo vệ ngữ nghĩa

**Mục tiêu:** chứng minh boolean `available` đúng kiểu nhưng sai giá trị phải làm producer test thất bại.

1. Tạo Inventory controller/service với fixture SKU-123 quantity=12.
2. Viết Groovy contract trả `available:true`.
3. Dùng `bodyMatchers.jsonPath('$.available', byType())` trong nhánh thử.
4. Sinh generated producer tests và chạy chúng trên implementation thật.
5. Cố ý đổi code thành `available:false`.
6. Ghi nhận test có bỏ lọt mutation hay không.
7. Đổi matcher thành `byEquality()` hoặc loại bỏ override quá rộng khi default equality đã đủ.
8. Chạy lại: với code sai, test phải **FAIL**.
9. Khôi phục code đúng, test **PASS**.
10. Mở generated Java assertions để giải thích lý do before/after.

**Bằng chứng:** contract diff, generated test assertions, mutation output và lời giải thích tại sao “đúng type” không đủ.

## 40. Bài thực hành B — Siết request matcher trong Stub Runner

**Mục tiêu:** client gửi sai JSON body phải không match happy-path 201.

1. Viết contract POST `/api/reservations` với `sku` string và `quantity` number.
2. Sinh stubs JAR và kiểm WireMock mapping.
3. Chạy consumer HTTP client thật với body đúng, ghi response 201.
4. Đổi consumer client gửi `productCode` thay `sku`.
5. Đổi quantity từ number `2` thành string `"2"`.
6. Nếu test vẫn nhận 201, kiểm bodyPatterns trong mapping và matcher trong DSL.
7. Bổ sung request matchers đủ chặt theo schema.
8. Sinh stubs artifact mới, dùng exact candidate version.
9. Chạy negative tests, xác nhận request sai **không match nhầm happy-path stub**.
10. Khôi phục client và xác nhận PASS.

**Bằng chứng:** mapping trước/sau, request journal, client HTTP request bytes và test report.

## 41. Bài thực hành C — Enum và error-code compatibility

**Mục tiêu:** ngăn regex rộng làm lọt breaking changes do enum/error schema.

1. Viết contract response status `RESERVED` và error code `SKU_NOT_FOUND`.
2. Giả lập matcher enum `[A-Z_]+` và error chỉ kiểm HTTP 404.
3. Cố ý trả `UNKNOWN_STATE` hoặc `ITEM_MISSING`.
4. Kiểm test có bỏ lọt mutation không.
5. Đổi sang equality/whitelist theo các trường hợp producer cam kết.
6. Sinh producer tests, xác nhận mutation làm FAIL.
7. Sinh candidate stubs artifact; consumer cũ kiểm tra enum/error mapper thật.
8. Phân biệt business 404 và unmatched WireMock 404.
9. Ghi quyết định compatibility khi muốn thêm enum value mới.

**Bằng chứng:** test matrix, error-code diff, generated assertions và consumer behavior.

## 42. Checklist chất lượng matcher trước khi merge

- [ ] Mọi trường quan trọng đều có ràng buộc **đúng kiểu và ngữ nghĩa**.
- [ ] Không dùng `.*`/`.+`/`byType()` cho field cần exact value hoặc whitelist.
- [ ] Các regex động được giới hạn format, không cho phép input vô nghĩa.
- [ ] Kiểm rõ JSON number vs string vs boolean và numeric bounds khi cần.
- [ ] Distinguish missing/null/empty/blank theo contract.
- [ ] Enum và error code không bị regex rộng che breaking change.
- [ ] Request matching kiểm method, URL, query, headers/body quan trọng.
- [ ] Response assertions kiểm HTTP status, headers, body schema/values cần thiết.
- [ ] Array có count/element/ordering rules khi consumer phụ thuộc.
- [ ] Invariants liên trường có scenario/custom assertion phù hợp.
- [ ] Dynamic IDs/timestamps không bị hardcode hoặc nới thành `.*`.
- [ ] JSON schema open/closed được quyết định có chủ đích.
- [ ] Không nhầm WireMock unmatched 404 với business error response.
- [ ] Message contracts bảo vệ destination, event type và payload cần thiết.
- [ ] Producer tests dùng implementation thật, không fake controller trả body mẫu.
- [ ] Generated Java tests và WireMock mappings được đọc kiểm semantics.
- [ ] Có negative/mutation tests khiến một lỗi compatibility quan trọng chuyển đỏ.
- [ ] Test runners không skip, executed contract test count > 0.
- [ ] Stubs JAR gắn đúng contract commit/candidate; không dùng artifact stale.
- [ ] Consumer test dùng client/handler thật, không mock ranh giới giao tiếp.
- [ ] CI ghi provenance và chặn nếu thiếu bằng chứng mandatory.
- [ ] Producer/consumer reviewers hiểu và chấp thuận mọi matcher được nới.

## 43. Câu hỏi tự kiểm tra

**1. Vì sao `byType()` cho field boolean `available` có thể quá rộng?**

Vì cả `true` và `false` đều là boolean. Nếu scenario yêu cầu `available=true`, matcher chỉ kiểm type không phát hiện producer đổi giá trị thành false.

**2. `byRegex('.*')` có phải cách xử lý tốt với ID động không?**

Không. Nó có thể chấp nhận ID rỗng/sai format. Cần regex theo cấu trúc công bố hoặc matcher phù hợp, đồng thời kiểm correlation nếu contract yêu cầu.

**3. Producer response test và consumer stub request matching khác nhau ở đâu?**

Producer test kiểm **response implementation thật** có đáp ứng contract không; stub request matching kiểm consumer có gửi **request thỏa hợp đồng** không. Matcher rộng ở một phía gây loại xác nhận giả khác nhau.

**4. Một JSONPath path tồn tại có bảo đảm field mang giá trị đúng không?**

Không. Path tồn tại không kiểm enum, numeric range, equality hay quan hệ liên trường. Cần predicate nội dung.

**5. Vì sao phải kiểm quantity=0 và quantity=1?**

Vì đây là các boundary scenarios dễ phát hiện sai quy tắc `available = (quantity > 0)` mà một type matcher không phát hiện.

**6. Vì sao test consumer nhận 404 chưa chắc đã kiểm đúng business not-found?**

WireMock trả 404 khi request không match. Cần assert business error code/body và, khi cần, request journal.

**7. Có nên so chính xác mọi timestamp và ID để tăng độ chặt không?**

Không nếu dữ liệu được phép biến thiên. Chọn format matcher và kiểm quan hệ/semantics cần thiết, không khóa dữ liệu ngẫu nhiên.

**8. Tại sao regex enum `[A-Z_]+` có thể làm lọt breaking change?**

Vì nó chấp nhận enum mới không nằm trong tập consumer đang hiểu. Equality/whitelist cùng compatibility tests sẽ bảo vệ tốt hơn.

**9. Nếu sửa contract matcher rồi CI vẫn dùng stubs JAR cũ thì sao?**

Kết quả consumer không chứng minh matcher mới. Phải sinh/publish candidate stubs và kiểm resolved version/digest cùng mappings đang phục vụ.

**10. Làm thế nào biết một matcher có thực sự hữu ích?**

Thử mutation có chủ đích: thay đổi hành vi theo cách sẽ phá consumer, rồi xem generated producer test hoặc consumer stub matching có **FAIL** đúng kỳ vọng không.

## 44. Tài liệu tham khảo

- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/): generated producer tests, Groovy/YAML contract DSL và stub artifacts.
- [Spring Cloud Contract — Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): cú pháp và nguyên tắc request/response matchers.
- [Spring Cloud Contract — HTTP Contracts](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/http.html): request/response, headers và JSON bodies.
- [Spring Cloud Contract — Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner.html): chạy consumer tests trên generated stubs.
- [Spring Cloud Contract — Maven](https://docs.spring.io/spring-cloud-contract/reference/project-features-maven.html): producer generated tests và stubs packaging.
- [Spring Cloud Contract — Gradle](https://docs.spring.io/spring-cloud-contract/reference/project-features-gradle.html): Gradle plugin, contract generation và test tasks.
- [WireMock — Request Matching](https://wiremock.org/docs/request-matching/): `equalToJson`, `matchesJsonPath`, headers, request journal và near misses.
- [WireMock — Stubbing](https://wiremock.org/docs/stubbing/): mappings, response bodies và stub priority.
- [JsonPath — GitHub](https://github.com/json-path/JsonPath): truy vấn field trong JSON và các giới hạn thực thi.
- [Martin Fowler — Consumer-Driven Contracts](https://martinfowler.com/articles/consumerDrivenContracts.html): nguyên tắc phối hợp producer/consumer để bảo vệ giao tiếp.

**Lưu ý phiên bản:** Cú pháp `bodyMatchers`, `byEquality`, `byType`, `byRegex`, `byCommand`, YAML `matchers.body`, các generated assertions và cấu trúc WireMock mapping có thể khác theo Spring Cloud Contract/plugin version. Các ví dụ trong bài thể hiện **ý tưởng kỹ thuật và điểm kiểm tra**; hãy đối chiếu reference theo đúng version của Spring Boot/Spring Cloud Contract và **đọc generated Java/mapping** trước khi dựa vào chúng trong CI. Các lệnh và bài thực hành là hướng dẫn, không phải kết quả build đã chạy tại bước biên soạn.

---

**Điểm cần nhớ:** **Matcher quá rộng tạo khoảng cách giữa “test PASS” và “consumer thật sự tương thích”.** Response matcher chỉ kiểm type có thể bỏ lọt sai giá trị nghiệp vụ; request matcher chỉ kiểm method/path có thể chấp nhận request sai schema. Chọn matcher theo **cam kết thật**: equality cho fixture cố định, format/range/whitelist cho dữ liệu biến thiên có ràng buộc, custom assertions cho invariants phức tạp. Kết hợp generated producer tests, Stub Runner với artifact đúng commit, negative/mutation tests và CI gates để chứng minh thay đổi không tương thích **thực sự làm test đỏ**.

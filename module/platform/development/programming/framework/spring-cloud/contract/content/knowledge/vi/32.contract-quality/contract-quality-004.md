# Matcher quá chặt khiến thay đổi vô hại làm vỡ test

Một hợp đồng API chất lượng phải phát hiện được **thay đổi phá tương thích**, nhưng không nên thất bại chỉ vì implementation đổi một chi tiết mà consumer **không được cam kết**. Trong thực tế, producer có thể thêm một trường JSON không bắt buộc, tạo `traceId` mới, đổi thời điểm `createdAt`, sắp xếp lại thứ tự các khóa trong object hoặc thêm tham số `charset` hợp lệ vào `Content-Type`. Nếu test yêu cầu toàn bộ response phải giống hệt một chuỗi mẫu, những thay đổi vô hại này có thể làm pipeline đỏ dù consumer vẫn hoạt động đúng.

Đó là vấn đề **matcher quá chặt (overly strict matcher)**: kiểm thử đang bảo vệ cả những chi tiết ngẫu nhiên, thay vì chỉ bảo vệ những **cam kết quan trọng của API**. Ngược lại, nới matcher quá mức — chẳng hạn chỉ kiểm HTTP 200 và một chuỗi `status` bất kỳ — có thể khiến test xanh dù producer đã đổi kiểu tiền tệ, trả sai đơn hàng hoặc bỏ yêu cầu bảo mật.

Bài thuộc chương **Chất lượng hợp đồng** của mô-đun **SPRING_CLOUD_CONTRACT**. Spring Cloud Contract giúp producer và consumer thống nhất hành vi HTTP hoặc thông điệp bằng **Groovy/YAML DSL**, sinh **producer verification tests**, phát hành JAR `stubs`, dùng **Stub Runner** để kiểm consumer và chạy các cổng kiểm tra trong CI/CD. Trọng tâm là thiết kế matcher **đủ chặt để bảo vệ ý nghĩa, đủ linh hoạt để tránh báo động giả**, rồi xác minh bằng generated tests và consumer tests thực tế.

## 1. Triệu chứng của một matcher quá chặt

Giả sử **Order Service** có endpoint `GET /api/orders/42` và **Billing Service** đọc thông tin đơn hàng. Lần đầu producer trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": 42,
  "status": "PAID",
  "amountMinor": 125000,
  "currency": "VND",
  "createdAt": "2026-11-24T04:12:13Z",
  "traceId": "trace-abc123"
}
~~~

Một lần gọi khác hợp lệ:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json;charset=UTF-8

{
  "traceId": "trace-def456",
  "currency": "VND",
  "amountMinor": 125000,
  "status": "PAID",
  "id": 42,
  "createdAt": "2026-11-24T04:12:15Z",
  "links": {
    "self": "/api/orders/42"
  }
}
~~~

Theo **giả định hợp đồng** của ví dụ: Billing cần `id`, `status`, `amountMinor`, `currency`; `createdAt` là thời điểm hợp lệ có thể thay đổi; `traceId` là dữ liệu quan sát; `links` là trường mở rộng không bắt buộc; thứ tự khóa JSON object không có ý nghĩa.

Nếu một test thất bại vì `createdAt` đổi hai giây, `traceId` khác, khoảng trắng JSON thay đổi hoặc `links` được thêm, có khả năng **test đang kiểm chi tiết ngoài hợp đồng**. Nếu producer đổi `amountMinor` từ JSON number sang string, trả `id=43` hoặc `currency=USD` trong fixture kỳ vọng VND, đó **có thể là lỗi hợp đồng thật**.

| Thay đổi | Có nên làm test thất bại? | Lý do |
| --- | --- | --- |
| Thứ tự các khóa JSON object đổi | **Không**, nếu không có yêu cầu canonical representation | JSON object không cam kết thứ tự khóa. |
| JSON được pretty-print khác | **Không** | Khoảng trắng không đổi dữ liệu JSON sau parse. |
| `traceId` đổi theo request | **Không** nếu chỉ yêu cầu format/presence | Đây là giá trị vận hành động. |
| `createdAt` đổi sang timestamp hợp lệ khác | **Không** nếu hợp đồng không cam kết một thời điểm cụ thể | Nên kiểm format hoặc quan hệ thời gian. |
| Thêm `links` không bắt buộc | **Thường không**, tùy chính sách unknown fields | Client cũ có thể dùng strict deserializer. |
| `amountMinor` đổi number thành string | **Có** nếu number là cam kết | Consumer có thể parse sai hoặc tính toán sai. |
| `id=42` đổi thành `id=43` cho request đơn hàng 42 | **Có** | Vi phạm quan hệ request–response. |
| `status=PAID` đổi thành `CANCELLED` trong fixture đơn đã trả tiền | **Có** | Thay đổi ý nghĩa nghiệp vụ. |
| 401 trở thành 200 khi thiếu token | **Có** | Phá ràng buộc bảo mật. |

**Quy tắc mở đầu:** mỗi assertion phải trả lời được câu hỏi: *consumer nào phụ thuộc vào hành vi này và chuyện gì xảy ra nếu nó thay đổi?* Nếu không có câu trả lời, cần xem lại độ chặt thay vì mặc định assert mọi byte.

## 2. “Chặt” và “lỏng” không phải hai mức cố định

Một matcher tốt được thiết kế **theo từng thuộc tính**, không phải chọn cả hợp đồng “strict” hoặc “lenient”:

| Kiểu ràng buộc | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Equality** | Giá trị phải khớp chính xác. | HTTP `200`, `status=PAID`, `id=42` của fixture. |
| **Type** | Giá trị có kiểu dữ liệu đúng, không khóa giá trị mẫu. | `amountMinor` là JSON number; `traceId` là string. |
| **Pattern** | Giá trị nằm trong miền định dạng hợp lệ. | `traceId` có prefix và ký tự quy định; timestamp có dạng ISO-8601. |
| **Range** | Giá trị trong giới hạn số được cam kết. | `quantity` phải dương, nếu nghiệp vụ quy định. |
| **Presence / optionality** | Trường phải có, được vắng mặt hoặc được phép null. | `id` bắt buộc; `description` optional. |
| **Structure** | Object/array và các phần tử cần thiết tồn tại. | `amount.minor` là số, `amount.currency` là mã tiền tệ. |
| **Cross-field invariant** | Các trường có quan hệ nghiệp vụ. | `totalMinor = sum(lineTotalMinor)`. |
| **Ordering** | Vị trí phần tử có hoặc không có ý nghĩa. | Danh sách timeline có thứ tự, tập tag không có thứ tự. |
| **Security/negative behavior** | Request không hợp lệ phải được từ chối đúng cách. | Thiếu quyền → 403, thiếu xác thực → 401. |

Lựa chọn độ chặt dựa trên **cam kết thực tế**, không chỉ dựa trên khả năng thư viện matcher hỗ trợ. `byType()` rất tiện, nhưng nếu một đơn `PAID` bị trả thành `CANCELLED` thì vẫn là string hợp lệ; chỉ kiểm kiểu sẽ **không phát hiện lỗi**.

## 3. Ba vòng kiểm thử không nên bị trộn

Trong Spring Cloud Contract, matcher có vai trò khác nhau ở những nơi khác nhau:

~~~mermaid
flowchart TD
    A["Groovy/YAML Contract DSL"] --> B["Generated producer verification tests"]
    A --> C["Generated stub mappings"]
    B --> D["So request mẫu với response producer thật"]
    C --> E["Stub Runner / WireMock"]
    E --> F["Consumer HTTP client gửi request"]
    F --> G["Consumer test assert kết quả giải mã/hành vi"]
    D --> H["CI chặn producer regression"]
    G --> I["CI chặn consumer incompatibility"]
~~~

| Lớp | Đang kiểm điều gì? | Matcher thường ảnh hưởng |
| --- | --- | --- |
| **Producer verification** | Producer code thật trả phản hồi đúng hợp đồng khi nhận request mẫu. | Matcher **response** trong DSL điều khiển nhiều assertions được sinh. |
| **Stub request matching** | Request của consumer có đủ điều kiện để stub trả response định nghĩa không. | Matcher **request** trong DSL được chuyển thành điều kiện request của stub. |
| **Consumer assertions** | Mã HTTP client/listener thật hiểu dữ liệu và xử lý nghiệp vụ đúng không. | Assertions do nhóm consumer viết, không tự xuất hiện chỉ vì stub đã trả 200. |

**Đây là bất đối xứng quan trọng:** nới **response matcher** có thể giúp producer test tránh phụ thuộc giá trị động, nhưng nới **request matcher** quá nhiều có thể khiến **stub chấp nhận request sai** từ consumer. Ngược lại, stub trả một response mẫu cố định cũng không tự bảo đảm producer thật luôn trả giá trị đó; generated producer tests phải kiểm implementation.

Không sửa cả hai phía bằng một câu “đổi hết sang `byType()`”. Cần xác định test fail ở **request matching, producer assertion hay consumer logic** trước khi chọn cách sửa.

## 4. Hợp đồng Groovy DSL quá phụ thuộc giá trị mẫu

Một hợp đồng ban đầu có thể ghi:

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
            currency: 'VND',
            createdAt: '2026-11-24T04:12:13Z',
            traceId: 'trace-abc123'
        )
    }
}
~~~

Nếu không khai báo matcher phù hợp cho các trường động, **generated producer tests có thể tạo assertions gắn với giá trị ví dụ**. Khi producer sinh `createdAt` và `traceId` mới theo từng request, test sẽ thất bại dù những giá trị đó **hợp lệ theo API**.

Điểm cần hiểu:

1. Giá trị trong `body(...)` vừa phục vụ **mẫu hợp đồng/stub** vừa có thể góp phần định nghĩa **assertions được sinh**.
2. Đối với **field cố định hoặc business invariant**, so sánh chính xác có thể là đúng.
3. Đối với **field biến thiên theo request**, cần một matcher phù hợp hoặc test custom có ý nghĩa.
4. Cơ chế chi tiết phụ thuộc **phiên bản Contract Verifier và loại matcher**: sau khi sửa DSL phải xem **generated test code** để xác nhận thư viện đang kiểm đúng điều bạn muốn.

**Không kết luận mọi chênh lệch JSON đều do Contract Verifier dùng so sánh nguyên chuỗi.** Nhiều generator chuyển body thành JSONPath assertions hoặc các matcher cụ thể. Vấn đề là **điều kiện assertion**, không phải nhất thiết là text comparison.

## 5. Dùng `bodyMatchers` để nới đúng trường động

Vẫn giữ các giá trị nghiệp vụ **chặt**, chỉ thay ràng buộc cho `createdAt` và `traceId`:

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
            currency: 'VND',
            createdAt: '2026-11-24T04:12:13Z',
            traceId: 'trace-abc123'
        )
        bodyMatchers {
            jsonPath('$.createdAt', byRegex(
                '[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z'
            ))
            jsonPath('$.traceId', byRegex('trace-[A-Za-z0-9-]+'))
        }
    }
}
~~~

Ở đây:

- `id=42` vẫn là expected value cho request đơn 42. Đổi thành 43 phải fail.
- `status=PAID`, `amountMinor=125000`, `currency=VND` vẫn là các điều kiện nghiệp vụ của fixture.
- `createdAt` được kiểm theo **format** minh họa, không khóa một thời điểm.
- `traceId` được kiểm là chuỗi có prefix/miền ký tự phù hợp, không khóa một mã duy nhất.
- **Stub vẫn có thể trả giá trị mẫu trong `body(...)`**; response matcher giúp kiểm **producer response**, không có nghĩa Stub Runner tự sinh trace ID ngẫu nhiên.

**Giới hạn của regex timestamp ở ví dụ:** regex chỉ kiểm **hình dạng chuỗi**, có thể chấp nhận tháng 99 hoặc ngày 32. Nếu consumer phụ thuộc vào timestamp thực sự hợp lệ, hãy thêm kiểm `Instant.parse(...)` hoặc validator tương ứng. Ví dụ regex chỉ hỗ trợ UTC đuôi `Z`; nếu API công bố các offset như `+07:00`, phải mở rộng rule đúng chủ đích, không để matcher từ chối response hợp lệ.

### 5.1. Vì sao không dùng `byType()` cho tất cả?

Nếu dùng:

~~~groovy
bodyMatchers {
    jsonPath('$.id', byType())
    jsonPath('$.status', byType())
    jsonPath('$.amountMinor', byType())
    jsonPath('$.currency', byType())
    jsonPath('$.createdAt', byType())
    jsonPath('$.traceId', byType())
}
~~~

thì những thay đổi sai như `id=999` hoặc `status=CANCELLED` **có nguy cơ vẫn qua được phần assertions chỉ kiểm kiểu**, trong khi consumer cần giá trị tương ứng. `byType()` có ích cho **trường giá trị không cố định nhưng kiểu phải đúng**, không phải giải pháp chung cho mọi test đỏ.

**Nguyên tắc:** nới đúng **chỗ gây báo động giả**, giữ chặt **điều consumer đã phụ thuộc**, và kiểm generated assertions để bảo đảm phần còn lại vẫn được bảo vệ.

## 6. YAML DSL: matcher tương đương khi dùng YAML

Một producer dùng YAML DSL có thể biểu diễn cùng trường động:

~~~yaml
description: Trả đơn hàng đã thanh toán với metadata động
request:
  method: GET
  url: /api/orders/42
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: 42
    status: PAID
    amountMinor: 125000
    currency: VND
    createdAt: "2026-11-24T04:12:13Z"
    traceId: trace-abc123
matchers:
  body:
    - path: $.createdAt
      type: by_regex
      value: '[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z'
    - path: $.traceId
      type: by_regex
      value: 'trace-[A-Za-z0-9-]+'
~~~

Đây là **một phương án thay cho Groovy DSL của mục 5**, không phải tệp thứ hai phải nạp cùng lúc. Cấu trúc `matchers.body` thể hiện đường JSONPath và loại matcher. Cần kiểm cú pháp thực tế theo **phiên bản Spring Cloud Contract** đang dùng và đối chiếu **test/mappings được sinh**.

**Một điểm thường bị nhầm:** YAML `matchers.body` của **response** dùng để tác động cách producer verification kiểm response; nó không giống một **JSON Schema toàn cục** ép tất cả consumer phải tuân thủ. Consumer cần các assertions riêng trong code/test của mình.

## 7. JSON object: thứ tự khóa và khoảng trắng không phải hợp đồng

Hai JSON object sau có cùng dữ liệu:

~~~json
{"id":42,"status":"PAID","currency":"VND"}
~~~

~~~json
{
  "currency": "VND",
  "status": "PAID",
  "id": 42
}
~~~

Nếu test dùng:

~~~java
assertThat(actualJson).isEqualTo(
    "{\"id\":42,\"status\":\"PAID\",\"currency\":\"VND\"}"
);
~~~

thì khác biệt format hoặc thứ tự khóa sẽ làm test fail. Cách đó chỉ hợp lý nếu **giao thức thực sự cam kết canonical byte representation**, chẳng hạn nội dung được ký hoặc hash theo quy ước riêng.

Với API JSON thông thường, nên parse rồi kiểm **giá trị/kiểu/field**:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import static org.assertj.core.api.Assertions.assertThat;

ObjectMapper mapper = new ObjectMapper();
JsonNode root = mapper.readTree(actualJson);

assertThat(root.path("id").isIntegralNumber()).isTrue();
assertThat(root.path("id").asLong()).isEqualTo(42L);
assertThat(root.path("status").asText()).isEqualTo("PAID");
assertThat(root.path("currency").asText()).isEqualTo("VND");
~~~

Với `JsonNode`, cần quan sát sự khác nhau giữa **path vắng mặt**, **null** và **giá trị thật** khi đó là cam kết quan trọng. Trong ví dụ này, `path("status").asText()` của field thiếu có thể cho kết quả không như kỳ vọng, nên assertion giá trị sẽ fail; với API lớn hơn nên kiểm presence tường minh để có thông báo lỗi dễ đọc.

### 7.1. JSONAssert strict/lenient không phải “bật/tắt strict toàn API”

Một số nhóm dùng JSONAssert:

~~~java
JSONAssert.assertEquals(
    expectedJson,
    actualJson,
    JSONCompareMode.LENIENT
);
~~~

**LENIENT** có thể chấp nhận extra object fields và so array theo cách không yêu cầu thứ tự. Đây là lựa chọn **có thể quá lỏng** nếu một array có ý nghĩa thứ tự. **STRICT** kiểm chặt hơn về extra fields và thứ tự array nhưng vẫn không có nghĩa **thứ tự khóa object** là bắt buộc.

Đừng chuyển toàn bộ bộ test sang LENIENT chỉ để hết lỗi khi producer thêm `traceId`. Hãy kiểm **mỗi đường JSONPath** và các danh sách có ordering semantics riêng.

## 8. Trường mới: thêm field có phải luôn tương thích không?

Producer thêm:

~~~json
{
  "id": 42,
  "status": "PAID",
  "amountMinor": 125000,
  "currency": "VND",
  "links": {
    "self": "/api/orders/42"
  }
}
~~~

Nếu API có chính sách **cho phép thêm optional response fields**, client cũ thường nên bỏ qua `links` khi không dùng. Khi đó, một producer test yêu cầu “response phải có **chính xác bốn key**” sẽ gây báo động giả.

Nhưng một số consumer có thể:

- Dùng JSON deserializer cấu hình **fail on unknown properties**.
- Ký/kiểm checksum canonical payload.
- Dùng JSON schema `additionalProperties: false` theo giao thức đã cam kết.
- Giải mã sang cấu trúc không chấp nhận phần mở rộng.

Vì vậy, **additive không phải luôn tương thích với mọi consumer**. Trước khi nới matcher, xác định **chính sách mở rộng schema** và chạy compatibility tests cho các consumer versions còn được hỗ trợ.

**Cách thiết kế:** producer contract assertions nên tập trung vào các required fields/semantics, còn consumer test có thể kiểm **mã client thật vẫn giải mã được** một response có extra field hợp lệ. Nếu consumer cố ý strict, phải quyết định thay đổi API như một migration/versioning issue, không chỉ sửa test.

## 9. Missing, null, empty và optional: không được đánh đồng

Bốn response này có thể mang ý nghĩa khác nhau:

~~~json
{"description": "Đơn hàng đã được giao"}
~~~

~~~json
{"description": ""}
~~~

~~~json
{"description": null}
~~~

~~~json
{}
~~~

Nếu hợp đồng nói `description` **optional** và **không được null khi xuất hiện**, một assertion chỉ kiểm “string hoặc bất kỳ” có thể bỏ qua vi phạm. Nếu `description` bắt buộc, chấp nhận missing/null cũng là quá lỏng.

Với Jackson:

~~~java
JsonNode response = mapper.readTree(actualJson);

boolean hasDescription = response.has("description");
if (hasDescription) {
    assertThat(response.get("description").isTextual()).isTrue();
}
~~~

Nếu API cho phép `null`, điều kiện sẽ khác:

~~~java
if (response.has("description")) {
    JsonNode value = response.get("description");
    assertThat(value.isNull() || value.isTextual()).isTrue();
}
~~~

**Không dùng matcher `byType()` như một quyết định thay thế chính sách presence/optional/nullability.** Khi request dùng PATCH, phân biệt field vắng mặt (“không đổi”), field `null` (“xóa giá trị”) và string rỗng là đặc biệt quan trọng.

## 10. JSON array: độ chặt phải theo ý nghĩa thứ tự

JSON object không có thứ tự khóa mang ý nghĩa thông thường, nhưng **array có thứ tự phần tử**. Câu hỏi là *thứ tự đó có thuộc hợp đồng nghiệp vụ không?*

Ví dụ **danh sách lịch sử trạng thái**:

~~~json
{
  "history": [
    {"state": "CREATED"},
    {"state": "PAID"},
    {"state": "SHIPPED"}
  ]
}
~~~

Nếu API cam kết sắp theo thời gian tăng dần, đảo `PAID` và `CREATED` là **vi phạm hợp đồng**. Một matcher bỏ qua thứ tự sẽ quá lỏng.

Ngược lại, **danh sách warehouse tags**:

~~~json
{"tags": ["east", "fragile", "insured"]}
~~~

Nếu API công bố `tags` là một tập không thứ tự, hai array với cùng phần tử nhưng thứ tự khác nhau nên được xem là tương đương.

Ví dụ với AssertJ:

~~~java
assertThat(historyStates)
    .containsExactly("CREATED", "PAID", "SHIPPED");

assertThat(tags)
    .containsExactlyInAnyOrder("east", "fragile", "insured");
~~~

**Đừng dùng `containsAll(...)` thay cho equality của tập có multiplicity** nếu cần bảo vệ số lượng phần tử: một array bị lặp tag có thể vẫn thỏa `containsAll`. `containsExactlyInAnyOrder` kiểm số lượng mỗi phần tử, chỉ bỏ yêu cầu thứ tự.

### 10.1. Với array object

Nếu Order API có `items` là một tập các dòng đơn, hãy:

1. Xác định trường **định danh item** (`sku`, `lineId`).
2. So item theo **định danh**, không theo index ngẫu nhiên.
3. Kiểm **mỗi item** có `quantity`/`price` đúng kiểu và giá trị nghiệp vụ.
4. Kiểm có hoặc không cho phép **duplicate items**.
5. Chỉ yêu cầu ordering nếu producer thực sự cam kết sắp xếp.

Một matcher quá lỏng kiểu “`items` là array bất kỳ” cũng nguy hiểm: có thể không phát hiện thiếu dòng đơn hoặc sai tổng tiền.

## 11. HTTP headers: so giá trị ngữ nghĩa thay vì byte-by-byte

Ở HTTP, tên header thường **không phân biệt chữ hoa/chữ thường**. `Content-Type` của JSON có thể mang tham số `charset` theo cấu hình framework. Test so nguyên chuỗi:

~~~text
Content-Type == "application/json"
~~~

có thể fail với:

~~~text
Content-Type: application/json;charset=UTF-8
~~~

trong khi consumer vẫn nhận JSON đúng. Nếu hợp đồng chỉ yêu cầu media type JSON, hãy kiểm **media type đã parse** theo giao thức, không so string máy móc.

Ví dụ trong test Spring:

~~~java
import org.springframework.http.MediaType;

MediaType parsed = MediaType.parseMediaType(contentTypeHeader);
assertThat(parsed.isCompatibleWith(MediaType.APPLICATION_JSON))
    .isTrue();
~~~

Đây là ví dụ **consumer/helper test**, không phải cú pháp Spring Cloud Contract DSL. Trong DSL, bạn có thể dùng `contentType(applicationJson())` cho response hợp đồng; nếu một producer hợp lệ thêm charset nhưng generated test fail, hãy kiểm **generated matcher và phiên bản tool** rồi lựa chọn header matcher thích hợp. Không bỏ kiểm `Content-Type` hoàn toàn chỉ để làm CI xanh.

**Một số header bắt buộc phải kiểm chặt**: `WWW-Authenticate`, `Location` sau tạo tài nguyên, idempotency/correlation semantics, ETag/If-Match theo hợp đồng, cache/security headers. Cần phân biệt tham số không quan trọng với thông tin consumer thật sự sử dụng.

## 12. Phía request: nới matcher có thể làm stub chấp nhận lời gọi sai

Một request consumer gửi để tạo đơn:

~~~http
POST /api/orders
Content-Type: application/json

{
  "customerId": "C-42",
  "quantity": 2,
  "clientRequestId": "req-1001"
}
~~~

Vì `clientRequestId` thay đổi qua mỗi request, một WireMock mapping so **toàn bộ JSON request bằng mẫu cố định** có thể từ chối request hoàn toàn hợp lệ. Có thể nới **đúng field động**:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldAcceptValidOrderRequest'

    request {
        method 'POST'
        url '/api/orders'
        headers {
            contentType(applicationJson())
        }
        body(
            customerId: 'C-42',
            quantity: 2,
            clientRequestId: 'req-1001'
        )
        bodyMatchers {
            jsonPath('$.clientRequestId',
                byRegex('req-[A-Za-z0-9-]+'))
        }
    }

    response {
        status 201
        headers {
            contentType(applicationJson())
        }
        body(id: 42, status: 'CREATED')
    }
}
~~~

Điều quan trọng:

- `clientRequestId` có thể khác **nếu đúng format** mà hợp đồng chấp nhận.
- `customerId=C-42` và `quantity=2` trong tình huống test vẫn được kiểm theo quy ước đã định.
- `method=POST`, `url=/api/orders` và status `201` không bị nới.
- Một stub chấp nhận `quantity=-999` vì matcher chỉ kiểm **type number** có thể làm **consumer test đạt giả**, dù producer thật sẽ trả 400.

**Request matcher trong contract không thay thế input validation của ứng dụng.** Kiểm giới hạn âm/dương, enum, auth và required fields bằng negative contracts hoặc integration tests phù hợp. Nới request matching nên tránh **false 404 no-match** của WireMock, không được biến mọi request thành “đúng”.

## 13. Chọn matcher theo loại dữ liệu và rủi ro

| Dữ liệu | Matcher gợi ý | Vì sao |
| --- | --- | --- |
| HTTP method/path cố định | **Exact** | Gọi sai endpoint không thể được che. |
| Status `200/201/401/403/404` | **Exact theo scenario** | Consumer phân nhánh theo status. |
| `id` phải tương ứng request ID | Exact trong fixture hoặc invariant | Không trả sai tài nguyên. |
| `status` enum theo scenario | Equality/allowed enum đã định | `PAID` khác `CANCELLED`. |
| `amountMinor` / `quantity` | Type + range + business assertions | Kiểu đúng chưa đủ nếu tiền hoặc số lượng sai. |
| `currency` theo fixture | Equality hoặc enum/schema quy định | Đổi currency có thể gây sai tính tiền. |
| `createdAt` động | Pattern + parse validity + quan hệ thời gian khi cần | Không khóa timestamp cụ thể. |
| `traceId` | Presence + regex phù hợp | Kiểm format, tránh gắn một ID cố định. |
| Optional additive object field | Chỉ kiểm nếu hiện diện hoặc theo version policy | Hỗ trợ schema mở rộng khi đã thỏa thuận. |
| Pagination `items` | Shape + item invariants + page constraints | Không nới đến mức thiếu dữ liệu. |
| Ordered timeline | Assert order rõ | Thứ tự là một phần semantics. |
| Unordered tags | Assert multiset, bỏ yêu cầu thứ tự | Tránh fail vì cách sắp xếp vô hại. |
| JWT/Authorization | Header & status/scopes phù hợp | Không nới bảo mật chỉ để qua test. |

**Không phải lúc nào cũng có một DSL matcher tích hợp để kiểm mọi invariant.** Những quan hệ như `sum(lineTotalMinor) = totalMinor` có thể cần **consumer business test** hoặc custom assertion có fixture; đừng giả vờ rằng `byRegex` trên số là đã kiểm phép tính.

## 14. So sánh `byEquality`, `byType` và `byRegex` đúng mục đích

Trong response body matchers của Spring Cloud Contract, các lựa chọn thường gặp:

~~~groovy
bodyMatchers {
    jsonPath('$.status', byEquality())
    jsonPath('$.createdAt', byRegex(
        '[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z'))
    jsonPath('$.traceId', byRegex('trace-[A-Za-z0-9-]+'))
}
~~~

**`byEquality()`** thường dùng khi giá trị response phải bằng mẫu contract; **`byType()`** dùng khi chỉ cần kiểm kiểu; **`byRegex(...)`** dùng khi có format được công bố. Những matcher này không nên được lựa chọn chỉ vì “cái nào pass nhiều hơn”.

So sánh:

| Giả định field | Giá trị mới | Equality | Type | Regex theo format |
| --- | --- | --- | --- | --- |
| `status=PAID` | `CANCELLED` | **Fail** | Có thể pass (cùng string) | Tùy regex; regex quá rộng có thể pass. |
| `traceId=trace-abc` | `trace-def` | Fail | Pass | Pass nếu hợp format. |
| `traceId=trace-abc` | `"oops"` | Fail | Pass | Fail nếu regex đủ chặt. |
| `createdAt` ISO UTC | `not-a-time` | Fail | Pass (string) | Fail nếu regex chặt; thêm parse để kiểm lịch hợp lệ. |
| `amountMinor=125000` | `"125000"` | Fail nếu kiểu được giữ | Có thể fail khi type matcher kiểm number | Regex trên string có thể che lỗi kiểu nếu đặt sai. |

Ở một số DSL version còn có matcher theo **command/custom predicate**, date/time helper hoặc occurrence constraints. Dùng chúng khi có yêu cầu rõ, nhưng phải **đọc generated code và test thực tế**, không chỉ nhìn DSL để suy luận mức bảo vệ.

## 15. Tính toán và quan hệ giữa các trường: không chỉ kiểm hình dạng

Giả sử response:

~~~json
{
  "items": [
    {"sku": "SKU-42", "quantity": 2, "unitMinor": 50000},
    {"sku": "SKU-99", "quantity": 1, "unitMinor": 25000}
  ],
  "totalMinor": 125000,
  "currency": "VND"
}
~~~

Một matcher chỉ kiểm:

~~~text
items is array
totalMinor is number
currency is string
~~~

vẫn có thể pass nếu producer trả `totalMinor=1`. Đó là **quá lỏng** với Billing vì tổng tiền là dữ liệu nghiệp vụ quan trọng.

Trong một lớp integration/consumer test có DTO phù hợp, có thể kiểm:

~~~java
long calculatedTotal = order.items().stream()
    .mapToLong(i -> i.quantity() * i.unitMinor())
    .sum();

assertThat(order.totalMinor()).isEqualTo(calculatedTotal);
assertThat(order.currency()).isEqualTo("VND");
~~~

**Tránh trùng lặp không cần thiết**: Contract DSL nên mô tả tương tác các bên phụ thuộc, còn các phép tính phức tạp có thể được kiểm bằng domain tests hoặc integration tests của producer. Cần đủ trường hợp để việc “nới matcher” không làm mất một business invariant quan trọng.

## 16. Kiểm error schema và bảo mật: nơi không được nới tùy tiện

Một hợp đồng chất lượng không chỉ có happy path:

| Tình huống | Kỳ vọng | Rủi ro nếu matcher quá lỏng |
| --- | --- | --- |
| Không có bearer token | `401` với cơ chế xác thực đã công bố | Test bỏ qua security filter mà vẫn 200. |
| Có token nhưng thiếu scope | `403` | Quyền truy cập bị mở ngoài ý muốn. |
| Không tồn tại order ID | `404` và error code nghiệp vụ nếu đã cam kết | Chấp nhận 404 do WireMock no-match và tưởng kiểm đúng. |
| Quantity âm | `400` với validation contract phù hợp | Stub chấp nhận mọi number, consumer không thử lỗi. |
| Conflict/idempotency | `409` hoặc hành vi đã thiết kế | Consumer xử lý lặp order sai. |
| Lỗi hệ thống tạm thời | `5xx` + retry contract nếu công bố | Test chỉ assert “không exception” bỏ qua response semantics. |

**Không được nới status matcher** từ `401` sang “bất kỳ 2xx/4xx” chỉ vì phiên bản Spring Security mới trả khác. Phải hiểu vì sao khác và thống nhất hợp đồng mới nếu chính sách thay đổi.

Trong Spring Boot test, nếu dùng `@WithMockUser` cho mọi scenario hoặc vô hiệu hóa security filters, generated producer tests về 401/403 có thể không còn kiểm hành vi thực. Fixture/test setup và DSL assertions phải được review cùng nhau.

### 16.1. Tránh 404 giả do request no-match

WireMock có thể trả `404` khi không có mapping nào phù hợp. Một test consumer assert mỗi `status=404` có thể **pass khi client gọi sai path**:

~~~text
Expected: GET /api/orders/99 -> HTTP 404 ORDER_NOT_FOUND
Actual:   GET /api/order/99  -> WireMock no-match HTTP 404
~~~

Hãy xác định hợp đồng lỗi có body/error code cụ thể và kiểm **request journal/matched mapping**. Việc bỏ matcher request để WireMock “trả được bất kỳ response” không phải cách sửa đúng.

## 17. Chất lượng matcher khi API có versioning và deprecation

Một producer đang hỗ trợ v1/v2 có thể bổ sung:

~~~text
GET /api/v1/orders/42 -> body v1
GET /api/v2/orders/42 -> body v2
~~~

Không nên “giải quyết” bài toán versioning bằng matcher v1 quá lỏng:

~~~text
response must be any JSON object
~~~

Nếu v1 cam kết `amountMinor` là số, khi producer chuyển v1 sang `amount: {minor, currency}`, generated producer test v1 phải fail. Cách đúng thường là:

1. **Giữ hợp đồng v1 và test v1** trong thời gian producer còn cam kết hỗ trợ.
2. **Thêm hợp đồng v2 độc lập** cho schema mới.
3. **Chạy consumer tests** trên cả hai nhóm consumer còn được hỗ trợ.
4. Chỉ bỏ v1 tests khi **quy trình EOL** đã xác nhận không còn cam kết.

Nới matcher để tránh false positives **không đồng nghĩa nới chính sách tương thích ngược**. Một test dễ xanh nhưng không phát hiện breaking change là không đạt mục tiêu của Contract Verifier.

## 18. Messaging contracts: dynamic metadata và message semantics

Với thông điệp, dữ liệu động còn phổ biến hơn HTTP response. Ví dụ Order Service phát sự kiện `OrderCreated`:

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
            header('contentType', 'application/json')
            header('eventType', 'OrderCreated')
            header('schemaVersion', 1)
        }
        body(
            eventId: 'evt-123',
            orderId: 'ORD-42',
            amountMinor: 125000,
            publishedAt: '2026-11-24T04:12:13Z'
        )
    }
}
~~~

**Những gì nên kiểm chặt:**

- Destination/topic được công bố, ví dụ `orders.created`.
- `eventType=OrderCreated` và `schemaVersion=1`.
- Payload field names/types bắt buộc, amount/currency và business invariants.
- Khả năng consumer giải mã sự kiện theo schema/version thực tế.

**Những gì có thể kiểm linh hoạt:**

- `eventId` nếu chỉ yêu cầu một ID hợp lệ, không phải giá trị mẫu cố định.
- `publishedAt` nếu thực tế thay đổi theo thời gian.
- Thứ tự khóa JSON trong payload sau parse.
- Một số header do broker/binder thêm nếu chúng không nằm trong giao tiếp được cam kết.

Đừng mặc định **bỏ qua thứ tự message delivery**. Nếu nghiệp vụ cần trình tự state transitions, producer/consumer tests phải kiểm ordering hoặc cơ chế bảo đảm ordering thích hợp. Ngược lại, không ép test nhìn nhận một thứ tự ngẫu nhiên khi broker không cam kết.

**Contract message test và Stub Runner không tự chứng minh serialization trên broker thật**. Nếu consumer phụ thuộc Avro/Protobuf, header mapping, partition key hoặc schema registry, cần integration tests tương ứng; matcher JSON trong DSL không bao phủ mọi thuộc tính transport.

## 19. Consumer test với Stub Runner: tránh đạt giả

Giả sử Order Service đã publish artifact:

~~~text
com.acme:order-service:1.4.2:stubs
~~~

Billing dùng Stub Runner:

~~~java
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
class BillingContractTest {

    @Autowired
    StubFinder stubFinder;

    @Test
    void readsOrderAndCalculatesAmount() {
        URL stubUrl = Objects.requireNonNull(
            stubFinder.findStubUrl("com.acme", "order-service")
        );

        OrderClient client = new OrderClient(
            stubUrl.toExternalForm()
        );
        OrderClient.OrderDto order = client.getOrder(42L);

        assertThat(order.id()).isEqualTo(42L);
        assertThat(order.status()).isEqualTo("PAID");
        assertThat(order.amountMinor()).isEqualTo(125000L);
        assertThat(order.currency()).isEqualTo("VND");
    }
}
~~~

Ví dụ giả định **OrderClient và OrderDto là mã thực của Billing**. Artifact `stubs` phải tồn tại trong Maven local với `LOCAL`; nếu runner khác máy, dùng `REMOTE` với Maven repository/credentials phù hợp. `StubFinder` trả **URL của WireMock stub đang chạy**, không phải URL của Maven repository.

**Consumer test không nên chỉ assert “gọi không ném exception” hoặc HTTP 200.** Nó cần kiểm DTO và hành vi nghiệp vụ mà client dựa vào. Đồng thời, không cần assert `traceId` luôn bằng chuỗi mẫu `trace-abc123` nếu Billing không dùng giá trị đó.

### 19.1. Kiểm request thật nếu matcher được nới

Khi WireMock request matcher cho phép các trường động, cần kiểm consumer **thật sự gửi đúng method/path/header/body phần quan trọng**. Với WireMock Java API trong một test có server instance:

~~~java
wireMockServer.verify(
    1,
    getRequestedFor(urlEqualTo("/api/orders/42"))
        .withHeader("Accept", containing("application/json"))
);
~~~

Nếu dùng Stub Runner và không trực tiếp có `WireMockServer`, có thể xem **Admin API request journal** tại URL stub được tìm. Hãy kiểm thật các giá trị quan trọng và tránh in token/auth header đầy đủ vào CI log.

**Một mapping request quá rộng có thể che lỗi URL hoặc header** dù consumer test xanh. Việc verify request thực tế là một biện pháp bổ sung cho việc thiết kế request matchers.

## 20. Generated producer tests là nơi chứng minh mức độ bảo vệ

Một câu hỏi review quan trọng: *Sau khi sửa DSL, generated test thực sự assert những gì?*

Quy trình:

1. Sửa contract Groovy/YAML, **không sửa file generated Java/Groovy trực tiếp**.
2. Chạy phase/task sinh tests theo Maven/Gradle Plugin được cấu hình.
3. Đọc generated test source: JSONPath nào kiểm equality, type, regex? Có thiếu required field không?
4. Chạy producer verification trên implementation thật hoặc test context đúng.
5. Gây một thay đổi **vô hại** đã được xác nhận và kiểm test vẫn pass.
6. Gây một thay đổi **phá hợp đồng** có chủ đích và kiểm test fail.
7. Hoàn nguyên thay đổi thử nghiệm, ghi kết quả trong PR hoặc CI report.

Một ma trận mutation nhỏ rất hữu ích:

| Mutation thử nghiệm | Kỳ vọng |
| --- | --- |
| Đổi `traceId` hợp lệ | PASS. |
| Đổi `createdAt` sang timestamp hợp lệ khác | PASS. |
| Đảo thứ tự khóa object | PASS nếu không có canonical contract. |
| Thêm optional `links` | PASS nếu contract cho phép mở rộng. |
| Đổi `id=42` thành `id=43` | **FAIL**. |
| Đổi `status=PAID` thành `CANCELLED` | **FAIL**. |
| Đổi `amountMinor` từ number thành string | **FAIL**. |
| Bỏ `currency` bắt buộc | **FAIL**. |
| Đổi HTTP `200` thành `500` | **FAIL**. |
| Bỏ kiểm authentication khiến thiếu token vẫn nhận 200 | **FAIL** ở negative contract/security test. |

**Đây là các mutation người học có thể làm trên nhánh thử nghiệm**, không yêu cầu bổ sung logic “giả lỗi” vào production code. Chỉ khi cả hai chiều PASS/FAIL được chứng minh, matcher mới có lý do đáng tin để xem là “đủ chặt”.

## 21. Độ chặt của matcher và phiên bản thư viện

Spring Cloud Contract, WireMock, JSONPath, Rest Assured, JUnit/Spock và Spring Boot có thể thay đổi behavior qua các phiên bản. Vì vậy:

- **Pin plugin/DSL/starter versions tương thích** trong Maven/Gradle và Spring Cloud BOM.
- Không sao chép tùy tiện cú pháp matcher từ một phiên bản khác mà không kiểm generated tests.
- Khi nâng thư viện, so **generated sources và mappings** của một tập contract đại diện.
- Kiểm rằng matcher vẫn phát hiện các regression cốt lõi qua mutation tests.
- Phân biệt **test failure do API** với lỗi parser/plugin/JSONPath dependency.
- Không đổi từ equality sang type chỉ để vượt qua một **bug của generator** mà chưa xác minh.

Một nguồn nhầm lẫn phổ biến là cùng một DSL field nhưng **stub request matching** và **producer response verification** có hướng giá trị khác nhau. Hãy xem **cả generated producer tests và WireMock mappings**, không chỉ một phía.

## 22. CI: fail đúng lúc, không bỏ qua lỗi thật

~~~mermaid
flowchart TD
    A["PR thay contract hoặc producer code"] --> B["Review semantic contract + compatibility policy"]
    B --> C["Generate producer tests"]
    C --> D["Chạy producer tests + targeted mutation checks"]
    D --> E{"Assertions đúng nghĩa?"}
    E -->|Không| F["Sửa DSL/matcher, không skip test"]
    E -->|Có| G["Đóng gói artifact stubs theo version"]
    G --> H["Consumer Stub Runner tests với client thật"]
    H --> I{"Producer và consumer đều đạt?"}
    I -->|Không| J["Chặn publish/deploy, điều tra request/response"]
    I -->|Có| K["Publish immutable stubs + triển khai có kiểm soát"]
~~~

Các cổng chất lượng nên có:

1. **Hợp đồng được phát hiện** và generated tests thật sự chạy, không phải 0 test hoặc skipped.
2. **Matcher review** xác định field nào exact, field nào type/pattern, field nào optional.
3. **Producer verification** fail khi phá required schema/semantics/security.
4. **Consumer Stub Runner tests** dùng client thật, không chỉ kiểm mock tự tạo.
5. **Stub artifact version được ghim**; tránh `latest`/mutable snapshot không kiểm soát khi chẩn đoán.
6. **Không sửa contract chỉ để khớp bug producer** khi consumer vẫn phụ thuộc hành vi cũ.
7. **Không bật global lenient assertion** cho mọi response nếu ordering/error semantics quan trọng.
8. **Kiểm request journal** khi nới request matcher hoặc có 404 no-match.
9. **Báo cáo nguyên nhân** của một test fail: assertion too strict, producer breaking, fixture drift, client wrong request, hoặc tool/version mismatch.

**Một pipeline ít đỏ hơn không nhất thiết chất lượng cao hơn.** Chỉ số quan trọng là **khả năng phát hiện lỗi có tác động tới consumer với ít báo động giả**, chứ không phải % test xanh bằng mọi giá.

## 23. Chẩn đoán matcher quá chặt trong thực tế

| Triệu chứng | Nguyên nhân có thể | Cách điều tra/sửa |
| --- | --- | --- |
| Test fail khi `createdAt` đổi vài giây | Exact value cho dữ liệu động. | Regex/parse datetime theo quy ước, không khóa timestamp. |
| Test fail khi `traceId` đổi | ID mẫu bị coi là business invariant. | Kiểm format/presence, không equality với một mã cố định. |
| Test fail chỉ vì JSON pretty-print | So chuỗi JSON thay vì parse cấu trúc. | JSONPath/Jackson structured assertions. |
| Test fail khi đổi thứ tự khóa object | Matcher đang so serialized text. | So JSON object semantics. |
| Test fail khi thêm field `links` | Full-object equality/strict additional fields. | Kiểm schema extension policy, nới extra fields nếu hợp lệ. |
| Test fail khi thêm `charset` | So Content-Type byte-by-byte. | Kiểm media type semantics và generated header matcher. |
| Test fail khi các tags đổi thứ tự | So array order dù API coi là tập. | Kiểm multiset với multiplicity, không ép index. |
| Timeline đảo thứ tự nhưng test vẫn pass | Matcher quá lỏng với ordered array. | Assert order có ý nghĩa nghiệp vụ. |
| JSON `amountMinor` đổi number→string vẫn pass | Chỉ kiểm string/regex quá lỏng hoặc bỏ assertion. | Bổ sung JSON type và value/invariant. |
| Status sai `CANCELLED` vẫn pass | `byType()` thay equality của enum. | Khôi phục equality/allowed enum theo scenario. |
| Consumer stub nhận request thiếu required field | Request matcher quá rộng. | Kiểm required paths, negative contracts và journal. |
| Consumer nhận 404 dù request hợp lệ | Stub match toàn body chứa dynamic field exact. | Nới đúng field động của request matcher. |
| Test 404 xanh dù client gọi sai path | WireMock trả no-match 404. | Assert error body/matched mapping và request journal. |
| Security test xanh dù không có filter | Test setup vô hiệu hóa auth hoặc dùng global mock identity. | Bật test context/filter đúng, tách 401/403 scenarios. |
| Generated tests và Stub Runner hành xử khác nhau | Hướng matcher request/response khác, tool version khác. | Đọc generated test code và WireMock mapping cụ thể. |
| PR nới matcher khiến test xanh ngay | Có thể che breaking change thực. | Chạy mutation test cho required fields và kiểm consumer impact. |

**Lộ trình điều tra:** xác định request/response thật → xem contract nguồn → xem generated producer assertion hoặc stub mapping → phân loại thay đổi là semantic hay incidental → sửa đúng matcher → chạy lại cả producer và consumer tests.

## 24. Checklist review một matcher trước khi merge

| Câu hỏi | Kỳ vọng khi review |
| --- | --- |
| Field này có thuộc cam kết API không? | Có lý do từ contract, docs hoặc consumer cần dùng. |
| Giá trị có cố định theo fixture không? | Exact nếu đúng invariant, pattern/type nếu thay đổi hợp lệ. |
| Format có ý nghĩa không? | Regex vừa đủ, thêm parse nếu cần hợp lệ ngữ nghĩa. |
| Kiểu JSON có cần giữ không? | Number/string/boolean/null/array/object được kiểm đúng. |
| Trường bắt buộc hay tùy chọn? | Missing/null/empty được phân biệt theo policy. |
| Có cho phép extra response fields không? | Tương thích với consumer/deserializer hiện tại. |
| Thứ tự array có quan trọng không? | Assert đúng order hoặc multiset semantics. |
| HTTP status/header/error schema có được bảo vệ không? | Không nới status/auth/error thiếu lý do. |
| Matcher nằm phía request hay response? | Hiểu tác động lên Stub Runner hay generated producer test. |
| Giá trị mẫu có còn tạo stub hữu ích không? | Stub trả dữ liệu hợp lệ, đủ để consumer kiểm logic thật. |
| Mutation vô hại có PASS không? | Ít nhất một phép thử cho thay đổi hợp lệ dễ gặp. |
| Mutation phá hợp đồng có FAIL không? | Kiểm field quan trọng và negative cases. |
| Source/generated output được xem chưa? | Test code/mapping thực tế xác nhận DSL đúng mục tiêu. |
| CI có chạy đủ producer và consumer tests không? | Không bỏ generated tests hoặc chỉ dựa vào stub response. |

Một review có thể ghi **bảng quy tắc cho từng path**:

~~~text
$.id            -> exact 42 (gắn với request /42)
$.status        -> exact PAID cho fixture này
$.amountMinor   -> number + expected business value
$.currency      -> exact VND cho fixture này
$.createdAt     -> ISO-8601 UTC format + parse validity
$.traceId       -> required string, format trace-[A-Za-z0-9-]+
$.links         -> optional extension nếu consumer policy cho phép
items order     -> không có (nếu API quy định tập), giữ multiplicity
~~~

Đây là **bản thiết kế matcher**, không phải một bộ assertion thực thi được. Nó giúp các bên review quyết định nào là **contract** và quyết định nào là **test implementation detail**.

## 25. Bài thực hành: loại bỏ báo động giả mà vẫn bắt breaking change

Thực hành với Order Service producer và Billing Service consumer:

1. **Định nghĩa contract ban đầu** cho `GET /api/orders/42` trả `id`, `status`, `amountMinor`, `currency`, `createdAt` và `traceId`; đầu tiên để các field động là giá trị mẫu exact.
2. **Cấu hình Contract Verifier** để sinh JUnit 5 producer tests (chẳng hạn dùng Spring MVC MockMvc và base test có fixture Order 42).
3. **Chạy generated tests**, xem chúng fail khi producer tạo `createdAt` và `traceId` mới mỗi request.
4. **Thay đúng hai field động bằng `byRegex`** trong `response.bodyMatchers`, giữ các field nghiệp vụ chính xác theo fixture.
5. **Đọc generated producer test**, xác nhận `createdAt`/`traceId` được kiểm theo pattern và các field nghiệp vụ vẫn được bảo vệ.
6. **Thử mutation hợp lệ:** đổi trace ID, đổi timestamp hợp lệ, đảo thứ tự khóa JSON, thêm optional `links`. Đánh giá từng thay đổi theo policy và kiểm test tương ứng PASS.
7. **Thử mutation sai:** `id=43`, `status=CANCELLED`, `amountMinor` là string, bỏ `currency`, đổi HTTP 200 thành 500. Generated producer tests hoặc domain assertions cần FAIL.
8. **Tạo YAML contract tương đương** rồi so generated assertions, không đưa hai DSL trùng vào cùng đường quét của plugin.
9. **Thử POST request** có `clientRequestId` động; quan sát stub no-match với exact body và sửa bằng matcher đúng path. Không nới `quantity`/`customerId` ngoài policy.
10. **Thử list không có thứ tự**: thay thứ tự `tags` và assert cùng multiset; thử thêm/xóa một tag để chắc chắn test vẫn phát hiện.
11. **Thử list có thứ tự**: đổi thứ tự history của trạng thái và xác nhận test FAIL.
12. **Viết consumer OrderClient thật**, publish JAR `stubs` và dùng Stub Runner kiểm mã client giải mã các field quan trọng.
13. **Kiểm request journal** để bảo đảm client gửi đúng path/header và không nhận 404 no-match bị hiểu sai là lỗi nghiệp vụ.
14. **Thêm negative contracts** cho 401/403/404 với security filter, error body và fixture phù hợp.
15. **Thử message contract** có `eventId`/`publishedAt` động nhưng `eventType`/`schemaVersion` và payload business fields cố định theo tình huống; phân biệt generated messaging tests với broker integration tests.
16. **Đưa vào CI**: producer verification → stub packaging → consumer tests; ghi nhận một mutation có thể PASS (vô hại) và một mutation phải FAIL (breaking).

**Tiêu chí hoàn thành:** bài kiểm **không còn fail vì metadata động, JSON formatting hay thay đổi mở rộng đã được cho phép**, nhưng vẫn **fail khi status, kiểu dữ liệu, dữ liệu nghiệp vụ, required fields, request path hoặc security behavior bị phá**. Người học có thể giải thích **vì sao từng matcher đủ chặt**, không chỉ chứng minh test đã xanh.

## 26. Câu hỏi tự kiểm tra

1. Thế nào là matcher quá chặt? Tại sao nó làm giảm giá trị CI/CD?
2. Vì sao cùng JSON object với thứ tự khóa khác nhau thường phải được coi là tương đương?
3. Vì sao chỉ đổi mọi matcher sang `byType()` có thể che regression?
4. Với `GET /api/orders/42`, vì sao `id=42` nên được giữ chặt hơn `traceId`?
5. Một regex timestamp có nhất thiết chứng minh ngày giờ hợp lệ không?
6. Khi producer thêm optional `links`, điều kiện nào quyết định đó là thay đổi tương thích?
7. JSONAssert LENIENT có thể bỏ qua điều gì quan trọng khi một array có ordering semantics?
8. Vì sao `containsExactlyInAnyOrder` tốt hơn `containsAll` trong trường hợp phải giữ multiplicity?
9. `description` missing, `null` và `""` có luôn tương đương không?
10. Response `Content-Type: application/json;charset=UTF-8` có nhất thiết vi phạm hợp đồng `application/json` không?
11. Matcher ở `request.bodyMatchers` tác động thế nào tới stub mà consumer gọi?
12. Matcher ở `response.bodyMatchers` tác động thế nào tới producer verification?
13. Vì sao một stub trả response cố định không chứng minh producer thật luôn trả đúng?
14. Vì sao 404 của WireMock no-match không phải 404 nghiệp vụ?
15. Khi nào nên dùng equality, type, regex, range và cross-field invariant?
16. Vì sao không được nới kiểm HTTP 401/403 chỉ để sửa test đỏ?
17. Thêm schema v2 có cho phép bỏ hợp đồng v1 ngay khi v1 vẫn được hỗ trợ không?
18. Với message contract, những trường nào thường động và những trường nào định nghĩa giao tiếp?
19. Generated producer test có thể xanh với pattern quá lỏng không? Làm sao phát hiện?
20. Một mutation vô hại PASS và một mutation phá hợp đồng FAIL chứng minh điều gì?
21. Nếu thay đổi matcher khiến consumer test xanh nhưng producer test đỏ, phải điều tra lớp nào?
22. Vì sao không nên sửa trực tiếp generated test source thay vì Groovy/YAML DSL?

**Kết luận:** **Matcher tốt không phải matcher so nhiều byte nhất, mà là matcher bảo vệ đúng những hành vi consumer thực sự phụ thuộc**. Trong Spring Cloud Contract, hãy giữ chặt method/path, status, required fields, kiểu dữ liệu, giá trị/quan hệ nghiệp vụ và security; nới có chủ đích những giá trị động như timestamp/trace ID hoặc chi tiết trình bày không thuộc hợp đồng. Phân biệt **response matcher của generated producer tests** với **request matcher của stub**, kiểm kết quả code/mappings được sinh và chạy cả producer lẫn consumer tests. Chỉ khi một thay đổi vô hại **PASS** và một thay đổi phá tương thích **FAIL**, nhóm mới có bằng chứng rằng hợp đồng vừa ổn định vừa đủ sức ngăn regression trong CI/CD.

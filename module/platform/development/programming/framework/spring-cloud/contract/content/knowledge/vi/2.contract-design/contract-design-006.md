# Phân biệt trường bắt buộc, trường tùy chọn và trường bị bỏ qua

## 1. Vì sao phải phân loại trường khi thiết kế hợp đồng?

Trong hệ thống nhiều dịch vụ, một API có thể trả về hàng chục trường nhưng consumer chỉ cần một phần trong số đó. Nếu hợp đồng kiểm tra mọi trường và mọi giá trị, producer khó thay đổi ngay cả những dữ liệu không ảnh hưởng đến consumer. Ngược lại, nếu hợp đồng quá lỏng, producer có thể xóa hoặc đổi kiểu một trường quan trọng mà kiểm thử vẫn thành công.

Với **Spring Cloud Contract**, nhóm phát triển định nghĩa các tương tác HTTP hoặc thông điệp bằng Groovy/YAML DSL, sinh kiểm thử xác minh phía producer, phát hành stub cho consumer và chạy các kiểm thử này trong CI. Để các kiểm thử bảo vệ đúng giao diện, trước hết cần trả lời: **trường nào phải luôn tồn tại, trường nào có thể vắng mặt, và trường nào không cần đưa vào điều kiện kiểm tra?**

Sau bài này, người học có thể:

- Phân biệt **required**, **optional** và **ignored** theo góc nhìn một consumer cụ thể.
- Nhận ra sự khác nhau giữa trường **vắng mặt**, trường có giá trị `null` và trường có giá trị rỗng.
- Chọn điều kiện khớp dữ liệu phù hợp trong hợp đồng Groovy/YAML, tránh ràng buộc quá chặt hoặc quá lỏng.
- Thiết kế các trường hợp kiểm thử ở producer và consumer, sử dụng stub để phát hiện thay đổi API không tương thích.

## 2. Một API, ba mức cam kết khác nhau

Giả sử **Order Service** gọi **Payment Service** qua `GET /api/payments/42`. Payment Service có thể trả về:

```json
{
  "paymentId": 42,
  "status": "PAID",
  "receiptUrl": "https://example.test/receipts/42",
  "traceId": "c31e84a0"
}
```

Order Service cần `paymentId` và `status` để liên kết giao dịch và quyết định trạng thái đơn hàng. Nó hiển thị liên kết biên lai nếu có `receiptUrl`, nhưng vẫn hoạt động khi không có liên kết. Trường `traceId` phục vụ quan sát hệ thống; Order Service không đọc nó để ra quyết định.

| Nhóm | Trường ví dụ | Cam kết cần kiểm tra | Khi trường vắng mặt |
| --- | --- | --- | --- |
| **Bắt buộc (required)** | `paymentId`, `status` | Phải hiện diện, đúng kiểu và tuân thủ ràng buộc đã thỏa thuận | **Vi phạm** hợp đồng |
| **Tùy chọn (optional)** | `receiptUrl` | Được vắng mặt; **nếu xuất hiện** thì phải đúng kiểu/định dạng đã thỏa thuận | **Hợp lệ** |
| **Bị bỏ qua (ignored)** | `traceId` | Consumer không phụ thuộc vào sự hiện diện, giá trị hoặc định dạng của trường này | **Không ảnh hưởng** hợp đồng của consumer đó |

Ba khái niệm này là **chính sách về tương thích giữa các bên**, không đơn thuần là ba nhãn trong JSON. Việc một trường “bị bỏ qua” không có nghĩa trường đó vô dụng trong toàn hệ thống: `traceId` vẫn có thể là dữ liệu rất quan trọng đối với hệ thống logging, nhưng không nằm trong cam kết phục vụ nghiệp vụ của Order Service.

### 2.1. Trường bắt buộc

Một trường bắt buộc phải có trong thông điệp/response phù hợp với trường hợp đang được mô tả. Điều kiện thường bao gồm:

1. **Có mặt:** đường dẫn JSON, key hoặc header cần thiết tồn tại.
2. **Không phải `null`:** nếu hợp đồng yêu cầu giá trị thực.
3. **Đúng kiểu:** chẳng hạn `paymentId` là số nguyên, `status` là chuỗi.
4. **Đúng miền giá trị:** `status` thuộc tập `PAID`, `PENDING`, `FAILED` nếu đó là các trạng thái đã thống nhất.

Ví dụ, `{"paymentId":42}` không đáp ứng hợp đồng nếu `status` bắt buộc. Tương tự, `{"paymentId":"42","status":"PAID"}` sai nếu consumer yêu cầu `paymentId` ở dạng số.

### 2.2. Trường tùy chọn

Trường tùy chọn **có thể không xuất hiện**. Tuy nhiên, “tùy chọn” không đồng nghĩa “nếu có thì giá trị nào cũng được”. Với `receiptUrl`, hai phản hồi dưới đây có thể đều hợp lệ:

```json
{"paymentId":42,"status":"PAID"}
```

```json
{"paymentId":42,"status":"PAID","receiptUrl":"https://example.test/receipts/42"}
```

Nếu hợp đồng quy định `receiptUrl` phải là chuỗi URL khi xuất hiện, thì `"receiptUrl": 17` là không hợp lệ. Cần định nghĩa rõ **có cho phép `null` hay không**, bởi vắng mặt và `null` không phải cùng một trạng thái.

Một trường có thể bắt buộc **theo điều kiện**, chẳng hạn `failureReason` chỉ bắt buộc khi `status = FAILED`. Trường hợp này nên được mô tả bằng các hợp đồng/tình huống riêng và các assertion nghiệp vụ tương ứng; không nên gắn nhãn “tùy chọn” chung rồi bỏ qua điều kiện liên quan.

### 2.3. Trường bị bỏ qua

Trường bị bỏ qua là trường mà consumer **không đặt kỳ vọng kiểm thử** về sự tồn tại hay giá trị của nó. Ví dụ, Order Service không sử dụng `traceId` thì hợp đồng dành cho Order Service không cần xác nhận `traceId` phải tồn tại, phải khớp một chuỗi nhất định hoặc phải được giữ nguyên qua các phiên bản.

“Bỏ qua” có thể có hai ý nghĩa cần tách bạch:

- **Bỏ qua trường thừa trong phản hồi:** producer được phép thêm `traceId` hoặc một trường mới, và consumer vẫn đọc được những trường cần thiết. Bộ giải mã/so sánh của consumer phải chấp nhận các trường JSON không biết.
- **Bỏ qua giá trị nhưng vẫn cần trường:** nếu consumer cần biết `traceId` có mặt nhưng không quan tâm giá trị cụ thể, trường đó **vẫn bắt buộc về sự hiện diện**; chỉ nên dùng matcher linh hoạt cho giá trị. Đây không phải là “bỏ qua hoàn toàn”.

Phân biệt này quan trọng vì một matcher theo kiểu dữ liệu hoặc regex vẫn đang **kiểm tra** trường, còn một trường thực sự không liên quan thì không cần xuất hiện trong các điều kiện của hợp đồng.

## 3. Vắng mặt, `null`, rỗng và giá trị mặc định là bốn tình huống khác nhau

Xét `receiptUrl` trong các phản hồi sau:

| JSON | Diễn giải | Có hợp lệ nếu quy tắc là “được vắng mặt, nếu có phải là URL không rỗng”? |
| --- | --- | --- |
| Không có key `receiptUrl` | **Absent**: trường không tồn tại | Có |
| `"receiptUrl": null` | Trường tồn tại nhưng giá trị là `null` | Không, trừ khi cho phép `null` rõ ràng |
| `"receiptUrl": ""` | Trường tồn tại, chuỗi rỗng | Không |
| `"receiptUrl": "https://example.test/r/42"` | Trường có giá trị URL hợp lệ | Có |
| `"receiptUrl": 42` | Trường có kiểu số | Không |

Điều tương tự áp dụng cho `0`, `false`, mảng rỗng và object rỗng: chúng là **giá trị có thật**, không tự động tương đương với “không có trường”. Trong quá trình serialization/deserialization, một số thư viện có thể mặc định bỏ qua trường `null` hoặc gán giá trị mặc định khi key thiếu. Vì thế, phải kiểm thử bằng dữ liệu JSON thực tế thay vì chỉ dựa vào kiểu field trong Java.

Khi một trường có thể vắng mặt, cần trả lời thêm: consumer sẽ dùng giá trị mặc định nào, có ghi log hay cảnh báo không, và dữ liệu `null` có được xử lý khác so với key vắng mặt không?

## 4. Phân loại theo **hướng giao tiếp**, không theo tên trường

Một trường có thể mang mức độ bắt buộc khác nhau tùy consumer, endpoint và ngữ cảnh:

| Giao tiếp | Bắt buộc | Tùy chọn | Bị bỏ qua |
| --- | --- | --- | --- |
| **HTTP request** từ Order Service | `orderId` trong JSON; header định danh nếu API yêu cầu | Header `X-Correlation-Id` nếu producer tự sinh khi thiếu | Header `User-Agent` nếu producer không dùng để xử lý |
| **HTTP response** từ Payment Service | `paymentId`, `status` | `receiptUrl` | `traceId` đối với Order Service |
| **Thông điệp** `PaymentCompleted` | `eventType`, `paymentId`, `orderId` | `receiptUrl` nếu consumer có thể xử lý sự kiện khi thiếu | Metadata chẩn đoán không được consumer sử dụng |

Ví dụ: Payment Service có thể coi `traceId` là bắt buộc đối với hệ thống thu thập telemetry, nhưng Order Service không cần trường này. **Hợp đồng phải được đọc theo cặp producer–consumer và theo tương tác cụ thể**, thay vì tạo một danh sách bắt buộc duy nhất cho mọi bên.

Với API công khai cho nhiều consumer, có thể chọn các yêu cầu chung tối thiểu rồi kiểm tra các điều kiện chuyên biệt cho từng consumer. Điều này giảm nguy cơ một consumer vô tình khóa các thay đổi chỉ phục vụ consumer khác.

## 5. Thể hiện kỳ vọng bằng Spring Cloud Contract Groovy DSL

Ví dụ sau mô tả các trường **bắt buộc** trong phản hồi từ Payment Service:

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description "Trả về thông tin tối thiểu của một khoản thanh toán"

    request {
        method GET()
        url "/api/payments/42"
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            paymentId: 42,
            status: "PAID"
        )
        bodyMatchers {
            jsonPath('$.paymentId', byType())
            jsonPath('$.status', byRegex('PAID|PENDING|FAILED'))
        }
    }
}
```

Ý nghĩa của hợp đồng:

- `request` quy định consumer gọi `GET /api/payments/42`.
- `response.status` yêu cầu phản hồi `200 OK`.
- `body` mô tả `paymentId` và `status`; đây là các trường hợp đồng muốn bảo vệ.
- `byType()` giúp kiểm tra kiểu dữ liệu thay vì gắn chặt vào mọi giá trị cụ thể.
- `byRegex(...)` giới hạn `status` trong một miền giá trị được chấp nhận.

**Điểm quan trọng:** `byType()` hoặc `byRegex()` chỉ làm linh hoạt cách **khớp giá trị**; chúng không tự biến trường bắt buộc thành trường tùy chọn. Hai khái niệm “có phải tồn tại không?” và “nếu tồn tại thì giá trị thế nào?” cần được thiết kế riêng.

`receiptUrl` và `traceId` không xuất hiện trong ví dụ vì đây là **hợp đồng tối thiểu**. Việc không nêu tên chúng không tự động chứng minh rằng mọi trường hợp có/không có `receiptUrl` đều được kiểm thử, hoặc rằng một framework so sánh JSON tùy ý sẽ bỏ qua tất cả trường thừa. Muốn bảo đảm chính sách tương thích đầy đủ, cần thêm các ca kiểm thử và cấu hình khớp dữ liệu phù hợp.

### Hợp đồng tương đương bằng YAML DSL

```yaml
description: Tra cứu thông tin tối thiểu của thanh toán
request:
  method: GET
  url: /api/payments/42
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    paymentId: 42
    status: PAID
  matchers:
    body:
      - path: $.paymentId
        type: by_type
      - path: $.status
        type: by_regex
        value: 'PAID|PENDING|FAILED'
```

DSL Groovy và YAML đều có thể diễn đạt yêu cầu/mã trạng thái/body cùng các matcher. Tuy nhiên, **cú pháp cho optional/matcher và khả năng hỗ trợ có thể khác giữa các phiên bản Spring Cloud Contract và giữa phần request/response**. Khi cần mô tả trường tùy chọn ngay trong DSL, hãy đối chiếu tài liệu đúng phiên bản đang sử dụng; tránh tự thêm cờ `optional: true` vào YAML nếu chưa xác nhận công cụ hỗ trợ ở vị trí đó.

## 6. Kiểm thử trường tùy chọn mà không vô tình khóa API

Giả sử `receiptUrl` có thể vắng mặt, nhưng nếu xuất hiện thì phải là một URL hợp lệ. Cần kiểm tra **cả hai nhánh**:

**Nhánh A — Không có biên lai:**

```http
GET /api/payments/43

HTTP/1.1 200 OK
Content-Type: application/json

{"paymentId":43,"status":"PENDING"}
```

**Nhánh B — Có biên lai:**

```http
GET /api/payments/42

HTTP/1.1 200 OK
Content-Type: application/json

{"paymentId":42,"status":"PAID","receiptUrl":"https://example.test/r/42"}
```

Một cách triển khai dễ kiểm soát là tạo các **kịch bản/hợp đồng tương tác riêng** cho dữ liệu không có và có `receiptUrl`, rồi kiểm thử consumer với stub tương ứng. Trong trường hợp hợp đồng cho phép optional ngay ở matcher, cần xác nhận chính xác khả năng đó của phiên bản DSL đang dùng. Nếu chỉ có một hợp đồng mô tả mẫu có `receiptUrl`, không thể kết luận consumer xử lý được phản hồi thiếu trường này.

Để kiểm tra **giá trị hợp lệ khi trường hiện diện**, có thể dùng assertion ở consumer:

```java
JsonNode payment = objectMapper.readTree(responseBody);

assertTrue(payment.path("paymentId").isIntegralNumber());
assertTrue(payment.path("status").isTextual());

// Có thể không có receiptUrl, nhưng nếu có thì phải là chuỗi URL.
if (payment.has("receiptUrl")) {
    assertTrue(payment.get("receiptUrl").isTextual());
    assertTrue(payment.get("receiptUrl").asText().startsWith("https://"));
}

// Không kiểm tra traceId vì consumer không phụ thuộc trường này.
```

Đây là **đoạn minh họa assertion**, giả sử đã có `objectMapper`, `responseBody` và các import JUnit/Jackson thích hợp. Trong sản phẩm thật nên dùng bộ phân tích URI và quy tắc domain/định dạng URL cụ thể thay vì chỉ kiểm tra tiền tố `https://`.

Đoạn test trên chủ đích **không cho phép `receiptUrl: null`**: nếu key xuất hiện với `null`, `isTextual()` trả về `false`. Nếu nghiệp vụ đồng ý `null`, điều kiện phải được thay đổi rõ ràng và có ca kiểm thử tương ứng.

### Cẩn thận với stub

Stub sinh từ một hợp đồng thường trả các dữ liệu mẫu đã mô tả. Nếu stub chỉ trả nhánh B, consumer không được thử nhánh A. Vì vậy, muốn kiểm thử đầy đủ hành vi tùy chọn, phải chuẩn bị dữ liệu/hợp đồng cho từng nhánh hoặc cấu hình stub phù hợp. Đồng thời, phía producer phải xác minh rằng ứng dụng thực tế đáp ứng các tương tác mà stub công bố.

## 7. Bỏ qua trường thừa thế nào cho an toàn?

Giả sử phiên bản mới của Payment Service bổ sung:

```json
{
  "paymentId": 42,
  "status": "PAID",
  "traceId": "c31e84a0",
  "diagnostics": {
    "region": "ap-southeast-1"
  }
}
```

Nếu Order Service chỉ phụ thuộc vào `paymentId` và `status`, hai trường mới không nên làm hỏng hợp đồng của Order Service. Tuy nhiên, **bỏ qua trong hợp đồng thôi chưa đủ**: mã consumer cũng phải xử lý được các trường không được khai báo.

Ví dụ, với Jackson, một DTO có thể chủ động cho phép trường JSON chưa biết:

```java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record PaymentResponse(long paymentId, String status) {}
```

Khi đó, trường `traceId` và `diagnostics` được bỏ qua trong quá trình ánh xạ vào `PaymentResponse`. Hãy dùng chính DTO/client thực tế trong consumer test để xác minh hành vi này; đừng dựa vào việc stub trả dữ liệu đẹp như mong đợi.

**Không nhầm “bỏ qua trường” với “không kiểm tra bảo mật”.** Nếu trường lạ đến từ input của người dùng, producer vẫn cần xác thực và kiểm soát các dữ liệu liên quan đến bảo mật/nghiệp vụ. Việc consumer bỏ qua một field trong response chỉ nói rằng field đó không thuộc kỳ vọng giao tiếp của consumer này.

## 8. Ma trận kiểm thử: trường hợp nào phải pass hoặc fail?

Giả định quy tắc của Order Service:

- `paymentId`: bắt buộc, kiểu số nguyên.
- `status`: bắt buộc, một trong `PAID`, `PENDING`, `FAILED`.
- `receiptUrl`: được vắng mặt; nếu có phải là chuỗi URL HTTPS không rỗng; `null` không được chấp nhận.
- `traceId`: không thuộc kỳ vọng consumer; trường JSON lạ được phép xuất hiện.

| Phản hồi của producer | Kết quả mong muốn | Lý do |
| --- | --- | --- |
| `{"paymentId":42,"status":"PAID"}` | **PASS** | Có đủ trường bắt buộc, trường tùy chọn vắng mặt |
| `{"paymentId":42,"status":"PAID","receiptUrl":"https://example.test/r/42"}` | **PASS** | Trường tùy chọn xuất hiện và hợp lệ |
| `{"paymentId":42,"status":"PAID","traceId":"x"}` | **PASS** | Trường ngoài nhu cầu consumer được bỏ qua |
| `{"paymentId":42}` | **FAIL** | Thiếu `status` bắt buộc |
| `{"paymentId":"42","status":"PAID"}` | **FAIL** | `paymentId` sai kiểu |
| `{"paymentId":42,"status":null}` | **FAIL** | `status` không có giá trị hợp lệ |
| `{"paymentId":42,"status":"PAID","receiptUrl":99}` | **FAIL** | Trường tùy chọn xuất hiện nhưng sai kiểu |
| `{"paymentId":42,"status":"PAID","receiptUrl":null}` | **FAIL** | Chính sách đã quy định `null` không hợp lệ |
| `{"paymentId":42,"status":"REFUNDED"}` | **FAIL** | Giá trị `status` chưa thuộc miền hợp đồng |

Đây là **ma trận hành vi mục tiêu**, không phải lời khẳng định rằng một hợp đồng DSL tối thiểu ở mục 5 tự động tạo đủ mọi ca kiểm thử. Phải thêm hợp đồng, matcher, kiểm thử consumer hoặc kiểm thử schema thích hợp để bảo vệ hết các quy tắc trên.

## 9. Áp dụng cùng nguyên tắc cho hợp đồng thông điệp

Trong hệ thống bất đồng bộ, Payment Service có thể phát sự kiện:

```json
{
  "eventType": "PaymentCompleted",
  "paymentId": 42,
  "orderId": 301,
  "receiptUrl": "https://example.test/r/42",
  "traceId": "c31e84a0"
}
```

Đối với dịch vụ giao vận:

- `eventType`, `paymentId` và `orderId` có thể là **bắt buộc** để xác định loại sự kiện và đơn hàng.
- `receiptUrl` có thể **tùy chọn** nếu dịch vụ vẫn xử lý giao vận khi chưa có biên lai.
- `traceId` có thể **bị bỏ qua** trong logic nghiệp vụ; dịch vụ vẫn có thể truyền nó đến hệ thống logging.

Sự kiện cần được kiểm thử với cả thông điệp có và không có `receiptUrl`, trong khi producer phải được xác minh rằng payload phát ra đáp ứng các trường bắt buộc. Contract testing giúp kiểm tra nội dung thông điệp đã cam kết nhưng không thay thế các kiểm thử broker, thứ tự sự kiện, xử lý trùng lặp và cơ chế retry.

## 10. Các sai lầm thường gặp trong thiết kế hợp đồng

### Sai lầm 1: Đưa mọi trường của response vào hợp đồng với giá trị cố định

Nếu `traceId` thay đổi ở mỗi request mà hợp đồng bắt nó bằng `"c31e84a0"`, producer test có thể thất bại dù consumer không bị ảnh hưởng. Cách xử lý: chỉ kiểm tra các trường mà consumer dùng; nếu bắt buộc có `traceId` nhưng giá trị động, kiểm tra **sự hiện diện và định dạng**, không so sánh chuỗi cố định.

### Sai lầm 2: Nhầm matcher linh hoạt với trường tùy chọn

Quy tắc `jsonPath('$.paymentId', byType())` kiểm tra kiểu dữ liệu của `paymentId`; nó không có nghĩa `paymentId` được vắng mặt. Quy tắc vắng mặt hợp lệ phải được thiết kế riêng.

### Sai lầm 3: Coi `null` tương đương “không có”

Thư viện JSON và DTO có thể phân biệt hai trạng thái này. Nếu consumer không hỗ trợ `null`, hãy định nghĩa và kiểm thử rõ việc `null` bị từ chối.

### Sai lầm 4: Chỉ chạy producer test hoặc chỉ chạy consumer test

Producer test xác minh implementation producer tuân thủ hợp đồng; consumer test với **stub được tạo từ hợp đồng đã kiểm chứng** xác minh consumer dùng giao diện đó đúng cách. Hai phía bảo vệ hai nửa của tương tác; cần cả hai trong quy trình nhiều dịch vụ.

### Sai lầm 5: Xóa trường vì “consumer hiện tại không dùng”

Một trường bị bỏ qua bởi Order Service vẫn có thể bắt buộc đối với một consumer khác. Trước khi xóa hoặc đổi tên trường, cần kiểm tra các hợp đồng đang được duy trì cho **toàn bộ consumer liên quan** và chính sách tương thích phiên bản API.

## 11. Thiết kế kiểm thử và CI để bảo vệ ba nhóm trường

Một quy trình thực hành với Spring Cloud Contract:

1. **Khảo sát cách consumer thật sự dùng dữ liệu.** Xác định trường dùng để ra quyết định, trường chỉ để hiển thị, trường để logging, và điều kiện phụ thuộc giữa các trường.
2. **Ghi quy tắc phân loại rõ ràng.** Với required: có mặt/kiểu/miền giá trị; với optional: khi vắng mặt có hợp lệ không, `null` có được chấp nhận không, khi có thì định dạng nào; với ignored: consumer có chấp nhận JSON thừa không.
3. **Viết hợp đồng Groovy/YAML cho các tương tác chính.** Dùng matcher thích hợp cho trường bắt buộc có giá trị biến động, thêm các trường hợp response cần thiết cho nhánh có/không có dữ liệu tùy chọn.
4. **Sinh và chạy kiểm thử ở producer.** Thay đổi implementation làm thiếu hoặc sai trường bắt buộc phải khiến producer verification thất bại.
5. **Phát hành stub theo phiên bản sau khi producer test pass.** Consumer dùng Stub Runner nạp đúng phiên bản stub rồi kiểm thử cả nhánh bình thường, nhánh thiếu trường tùy chọn và khả năng xử lý dữ liệu thừa.
6. **Đưa các kiểm thử vào CI.** Chạy khi hợp đồng hoặc API thay đổi; xem xét tác động lên các consumer chưa nâng cấp trước khi xóa trường đã công bố.

Checklist review hợp đồng trước khi merge:

- Trường bắt buộc đã được kiểm tra về hiện diện, kiểu và ràng buộc cần thiết chưa?
- Trường tùy chọn đã có kiểm thử **vắng mặt** lẫn **xuất hiện**, bao gồm quy tắc `null` chưa?
- Những trường bị bỏ qua có thực sự không ảnh hưởng đến consumer và parser có chấp nhận dữ liệu thừa không?
- Có trường nào chỉ bắt buộc theo điều kiện nghiệp vụ cần hợp đồng/test riêng không?
- Stub và bộ kiểm thử của consumer có dùng đúng phiên bản hợp đồng mà producer đã xác minh không?
- Việc thay đổi một trường có ảnh hưởng tới consumer khác hay phiên bản API đang vận hành không?

## 12. Bài thực hành tự kiểm tra

Một dịch vụ `Inventory Service` trả:

```json
{
  "sku": "SKU-001",
  "available": true,
  "quantity": 15,
  "restockDate": null,
  "requestId": "req-8d2"
}
```

Consumer `Checkout Service` luôn cần `sku`, `available` và `quantity` để quyết định có cho đặt hàng không. Khi hết hàng, nó có thể hiển thị `restockDate` nếu producer đã cung cấp ngày nhập lại; hệ thống không dùng `requestId` trong nghiệp vụ.

Hãy tự trả lời:

1. Trường nào là required, optional và ignored theo góc nhìn Checkout Service?
2. Nếu `restockDate` có `null`, đó là một giá trị được cho phép hay phải bỏ hẳn key? Cần thống nhất điều gì trong hợp đồng?
3. Nếu `quantity` đổi từ số thành chuỗi `"15"`, nên có kiểm thử nào thất bại?
4. Nếu producer thêm `warehouseCode`, có nên bắt Checkout Service cập nhật theo không?

**Gợi ý đáp án:** `sku`, `available`, `quantity` là các trường bắt buộc; `restockDate` là trường tùy chọn nhưng phải thống nhất riêng quy tắc `null` và định dạng ngày khi xuất hiện; `requestId` bị bỏ qua theo nhu cầu nghiệp vụ của consumer này. Việc đổi `quantity` sang chuỗi phải bị phát hiện nếu hợp đồng yêu cầu kiểu số. Thêm `warehouseCode` không nên làm hỏng Checkout Service khi dịch vụ không dùng nó và bộ giải mã cho phép trường JSON lạ.

**Ghi nhớ:** **Bắt buộc** nghĩa là vắng mặt là lỗi. **Tùy chọn** nghĩa là được vắng mặt, nhưng có mặt phải thỏa quy tắc. **Bị bỏ qua** nghĩa là không thuộc kỳ vọng của consumer đang xét. Phân loại đúng là nền tảng để hợp đồng Spring Cloud Contract phát hiện thay đổi API thực sự nguy hiểm mà vẫn cho phép producer mở rộng giao diện an toàn.

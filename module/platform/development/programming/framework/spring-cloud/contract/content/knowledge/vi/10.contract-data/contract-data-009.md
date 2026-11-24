# Ẩn danh dữ liệu và loại bỏ thông tin production

## Mục tiêu bài học

Trong **Spring Cloud Contract**, các hợp đồng Groovy/YAML DSL mô tả hành vi HTTP hoặc thông điệp giữa **producer** và **consumer**. Từ những hợp đồng này, hệ thống có thể sinh kiểm thử phía producer, tạo stub để consumer sử dụng qua **Stub Runner**, và chạy kiểm tra trong CI trước khi phát hành thay đổi API.

Các hợp đồng, dữ liệu mẫu, test được sinh, stub và log có thể xuất hiện ở nhiều repository, artifact repository và môi trường chạy. Nếu lấy nguyên payload từ production để làm ví dụ, thông tin cá nhân, token, dữ liệu kinh doanh hoặc định danh nội bộ có thể bị phát tán tới những nơi không được phép lưu dữ liệu đó.

Vì vậy, một hợp đồng tốt phải **giữ đúng ý nghĩa và định dạng dữ liệu mà consumer cần**, đồng thời **không mang dữ liệu production thật**. Chủ đề này là một phần của chương **Dữ liệu hợp đồng** và xuyên suốt vòng đời producer test, stub, Stub Runner và CI.

Sau bài học, bạn có thể:

- Nhận diện các loại dữ liệu không nên đưa vào hợp đồng, fixture hoặc stub.
- Phân biệt dữ liệu **ẩn danh**, **giả danh** (pseudonymized), **che/masking** và **dữ liệu tổng hợp** (synthetic).
- Viết hợp đồng HTTP và thông điệp với giá trị mẫu an toàn mà vẫn kiểm tra đúng schema, kiểu dữ liệu và hành vi.
- Chọn matcher để kiểm tra định dạng hoặc kiểu dữ liệu thay vì khóa cứng định danh nhạy cảm.
- Thiết lập quy trình rà soát để ngăn thông tin production lọt vào source control, generated tests, stub JAR và log CI.
- Hiểu giới hạn của việc dùng test/stub để chứng minh khả năng tương thích API.

## 1. Vì sao dữ liệu của hợp đồng phải được kiểm soát?

Một ví dụ dùng trong bài học hoặc kiểm thử có thể tồn tại lâu hơn một lần chạy test:

~~~mermaid
flowchart TD
    A["Hợp đồng Groovy/YAML<br/>trong repository"] --> B["Spring Cloud Contract"]
    B --> C["Generated producer tests"]
    B --> D["Generated stubs"]
    C --> E["Log và báo cáo producer CI"]
    D --> F["Stub artifact repository"]
    F --> G["Consumer dùng Stub Runner"]
    G --> H["Consumer test logs / CI artifacts"]
~~~

Nếu một email, số điện thoại, địa chỉ, token hoặc thông tin đơn hàng thật bị chép vào hợp đồng, nó có thể tiếp tục xuất hiện trong generated source, stub mapping, JAR, log khi matcher thất bại, bản cache của CI và artifact đã tải về máy của consumer. **Xóa giá trị trong một tệp nguồn không tự động xóa những bản sao đã được phát hành**.

Mục tiêu bảo vệ dữ liệu ở đây gồm hai phần:

1. **Bảo mật và quyền riêng tư:** ngăn dữ liệu thật xuất hiện trong tài liệu, source control, artifact và log có phạm vi truy cập rộng hơn hệ thống production.
2. **Độ tin cậy kiểm thử:** tạo dữ liệu mẫu ổn định, dễ hiểu và tái lập; không để hợp đồng phụ thuộc tài khoản khách hàng, cơ sở dữ liệu hay token production có thể hết hạn.

Việc giữ đúng dữ liệu thật đôi khi làm test có vẻ “thực tế” hơn, nhưng thường khiến test phụ thuộc trạng thái không kiểm soát. Dùng dữ liệu tổng hợp có thiết kế sẽ bảo vệ dữ liệu và cho kết quả kiểm thử ổn định hơn.

## 2. Những thông tin nào không nên có trong hợp đồng?

Trước khi đưa một giá trị vào Groovy/YAML DSL, phải phân biệt **cấu trúc API cần kiểm tra** và **giá trị cụ thể lấy từ môi trường thật**.

| Nhóm dữ liệu | Ví dụ | Cách xử lý khuyến nghị |
| --- | --- | --- |
| Thông tin nhận dạng cá nhân | Tên, email, số điện thoại, địa chỉ giao hàng của khách hàng thật | Thay bằng dữ liệu tổng hợp phù hợp schema |
| Dữ liệu giao dịch thực | Mã đơn, tổng tiền, chi tiết sản phẩm hoặc lịch sử giao dịch của khách hàng thật | Tạo đơn hàng, số tiền và mặt hàng mẫu riêng cho test |
| Bí mật xác thực | API key, access token, refresh token, mật khẩu, cookie phiên, khóa ký | Không ghi vào contract/stub; cấp credential thử nghiệm qua cơ chế an toàn khi cần |
| Dữ liệu thanh toán | Số thẻ thật, thông tin thanh toán nhạy cảm, dữ liệu thanh toán định danh | Dùng dữ liệu thử nghiệm do hệ thống thanh toán hỗ trợ và tuân thủ chính sách dữ liệu của tổ chức |
| Dữ liệu nội bộ không công khai | Hostname production, URL quản trị, tenant ID thật, IP nội bộ, tên tài nguyên riêng | Dùng giá trị giả lập hoặc cấu hình môi trường test |
| Dữ liệu kinh doanh nhạy cảm | Giá thực không công khai, điều kiện chiết khấu theo khách hàng, danh sách đối tác | Tạo kịch bản nghiệp vụ tổng hợp không tái hiện thông tin bí mật |
| Dữ liệu kỹ thuật công khai | Tên field, HTTP method, mã lỗi, kiểu dữ liệu, giá trị enum công bố | Giữ nguyên khi đó là điều consumer phụ thuộc |

Ví dụ, consumer có thể phải gửi JSON chứa trường **customer.email**. Khi đó tên trường và quy tắc định dạng email là một phần hợp đồng; **email thật của một khách hàng cụ thể thì không**.

Tương tự, tên trạng thái công khai như **PAID**, **CANCELLED** hoặc mã lỗi **ORDER_NOT_FOUND** không nên bị thay tùy tiện nếu consumer đang dựa vào chúng. Cần ẩn danh **giá trị dữ liệu**, không phá vỡ **hành vi và schema** đang được kiểm tra.

## 3. Ẩn danh, giả danh, masking và dữ liệu tổng hợp khác nhau thế nào?

Các thuật ngữ thường bị dùng thay thế nhưng có đặc điểm khác nhau:

| Phương pháp | Mô tả | Giới hạn cần nhớ |
| --- | --- | --- |
| **Ẩn danh (anonymization)** | Biến đổi dữ liệu để không thể xác định cá nhân một cách hợp lý trong bối cảnh sử dụng | Khó đạt khi các trường còn lại có thể liên kết với dữ liệu khác; không chỉ thay tên là đủ |
| **Giả danh (pseudonymization)** | Thay định danh bằng mã khác, có thể có bảng đối chiếu hoặc cơ chế liên kết | Dữ liệu có thể vẫn là dữ liệu cá nhân nếu có khả năng tái nhận dạng |
| **Masking/redaction** | Che hoặc loại bỏ các phần dữ liệu, ví dụ ẩn token trong log | Dữ liệu còn lại có thể vẫn nhận dạng được; bản gốc có thể tồn tại nơi khác |
| **Tổng hợp (synthetic data)** | Tạo dữ liệu hư cấu theo quy tắc và cấu trúc mong muốn | Cần xác minh dữ liệu không vô tình trùng giá trị thật và phản ánh đủ trường hợp nghiệp vụ |

Trong tài liệu hợp đồng và stub phổ biến, **dữ liệu tổng hợp được tạo từ đầu** thường là lựa chọn thuận tiện và an toàn hơn việc sao chép một JSON production rồi che vài trường.

Ví dụ:

~~~json
{
  "customerId": "CUS-TEST-1001",
  "email": "buyer@example.test",
  "address": {
    "city": "Test City",
    "street": "Sample Street 1"
  },
  "orderId": "ORD-TEST-9001"
}
~~~

Trong ví dụ:

- **CUS-TEST-1001** và **ORD-TEST-9001** là mã thử nghiệm được tạo có chủ đích.
- **example.test** là tên miền dành cho thử nghiệm; không gửi email tới một hộp thư khách hàng thật.
- Địa chỉ là dữ liệu minh họa, không lấy từ hồ sơ giao hàng thực.
- Tên trường, kiểu dữ liệu và cấu trúc object vẫn giống giao diện mà consumer cần sử dụng.

**Không suy diễn rằng mọi dữ liệu trông “giả” đều thật sự không nhạy cảm.** Một chuỗi được tạo từ hash không có salt của email thật, ví dụ, vẫn có thể được dò ngược bằng danh sách email phổ biến. Một bộ dữ liệu sau khi thay tên nhưng vẫn giữ địa chỉ, ngày sinh và lịch sử giao dịch cũng có thể bị liên kết để tìm lại cá nhân.

## 4. Chọn dữ liệu mẫu theo hợp đồng, không sao chép bản ghi production

Giả sử Checkout cần tạo một đơn hàng và kiểm tra producer trả mã đơn cùng trạng thái. Một request mẫu phù hợp:

~~~json
{
  "customer": {
    "id": "CUS-TEST-1001",
    "email": "buyer@example.test"
  },
  "items": [
    {
      "sku": "SKU-TEST-BOOK",
      "quantity": 2,
      "unitPrice": 15000
    }
  ],
  "delivery": {
    "city": "Test City",
    "method": "STANDARD"
  }
}
~~~

Phản hồi mẫu:

~~~json
{
  "orderId": "ORD-TEST-9001",
  "status": "CREATED",
  "totalAmount": 30000
}
~~~

Để biến ví dụ thành dữ liệu hợp đồng có ích, hãy kiểm tra:

1. **Định dạng:** customer.id và orderId dùng đúng kiểu và quy tắc định danh API đã công bố. Nếu production API chỉ cho phép UUID, fixture phải dùng một UUID tổng hợp hợp lệ thay vì chuỗi tùy ý.
2. **Tính nhất quán:** hai sản phẩm giá 15.000 mỗi đơn vị, tổng cộng 30.000 trong tình huống này. Nếu test kiểm tra tổng tiền, body phải có quan hệ dữ liệu hợp lý.
3. **Kiểu JSON:** quantity và totalAmount là số, email là string, items là mảng.
4. **Tính tái lập:** cùng hợp đồng, cùng fixture và cùng producer build cho ra cùng kỳ vọng test.
5. **Phạm vi dữ liệu:** không cần thêm tên đầy đủ, số điện thoại, số thẻ hay địa chỉ thật nếu consumer không dựa vào chúng.

Khi hợp đồng cần số định danh theo UUID, có thể dùng một **UUID tổng hợp cố định** phù hợp với schema, chẳng hạn:

~~~text
00000000-0000-4000-8000-000000000001
~~~

Không nên sử dụng UUID lấy từ bản ghi thực chỉ vì nó có định dạng đúng. Dữ liệu thử nghiệm có thể vừa đúng định dạng, vừa hoàn toàn độc lập với production.

## 5. Hợp đồng HTTP Groovy DSL với dữ liệu tổng hợp

Với Spring Cloud Contract Groovy DSL, request và response có thể khai báo trực tiếp bằng map/list:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description "Tạo đơn hàng bằng dữ liệu tổng hợp"

    request {
        method POST()
        url "/api/orders"
        headers {
            contentType(applicationJson())
            header("Accept", "application/json")
        }
        body(
            customer: [
                id: "CUS-TEST-1001",
                email: "buyer@example.test"
            ],
            items: [
                [sku: "SKU-TEST-BOOK", quantity: 2, unitPrice: 15000]
            ],
            delivery: [city: "Test City", method: "STANDARD"]
        )
    }

    response {
        status 201
        headers {
            contentType(applicationJson())
        }
        body(
            orderId: "ORD-TEST-9001",
            status: "CREATED",
            totalAmount: 30000
        )
    }
}
~~~

Hợp đồng này không cần token thật, tài khoản thật hoặc kết nối tới production để diễn đạt hành vi. Khi generated producer test chạy, **môi trường test** có trách nhiệm chuẩn bị dữ liệu và logic phù hợp để producer trả phản hồi như đã khai báo.

Nếu producer trong thực tế tự sinh orderId ngẫu nhiên, việc buộc đúng giá trị **ORD-TEST-9001** có thể quá chặt. Khi đó nên dùng matcher đúng quy tắc định danh hoặc fixture có cơ chế kiểm soát ID; không gọi production API để lấy một ID thật rồi điền vào hợp đồng.

### Cùng hành vi bằng YAML DSL

~~~yaml
description: "Tạo đơn hàng bằng dữ liệu tổng hợp"
name: create_order_with_synthetic_data
request:
  method: POST
  url: /api/orders
  headers:
    Content-Type: application/json
    Accept: application/json
  body:
    customer:
      id: "CUS-TEST-1001"
      email: "buyer@example.test"
    items:
      - sku: "SKU-TEST-BOOK"
        quantity: 2
        unitPrice: 15000
    delivery:
      city: "Test City"
      method: STANDARD
response:
  status: 201
  headers:
    Content-Type: application/json
  body:
    orderId: "ORD-TEST-9001"
    status: CREATED
    totalAmount: 30000
~~~

YAML DSL cũng cần được review như một nguồn của generated tests và stubs. Một file YAML không chứa mã tùy ý vẫn có thể **chứa dữ liệu production thật** nếu tác giả dán response thực vào phần body.

## 6. Dùng matcher để giữ quy tắc, không khóa cứng định danh

Dữ liệu tổng hợp cần đáp ứng nhu cầu của producer test, nhưng consumer có thể gửi nhiều giá trị hợp lệ khác nhau. Hợp đồng có thể mô tả **quy tắc định dạng** thay vì so khớp một định danh cụ thể.

Ví dụ Groovy DSL cho request body:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    request {
        method POST()
        url "/api/orders"
        headers {
            contentType(applicationJson())
        }
        body(
            customer: [id: "CUS-TEST-1001"],
            items: [[sku: "SKU-TEST-BOOK", quantity: 2]]
        )
        bodyMatchers {
            jsonPath('$.customer.id', byRegex('CUS-[A-Z0-9-]+'))
            jsonPath('$.items[0].quantity', byType())
        }
    }
    response {
        status 201
        headers {
            contentType(applicationJson())
        }
        body(orderId: "ORD-TEST-9001", status: "CREATED")
    }
}
~~~

Ví dụ dùng các matcher thường gặp trong Spring Cloud Contract; cần xác minh cú pháp và stub mapping sinh ra với **phiên bản DSL của dự án**.

**Các điểm cần hiểu đúng:**

- Giá trị mẫu **CUS-TEST-1001** phục vụ một trường hợp test có thể tái lập.
- **byRegex(...)** diễn đạt một kiểu mã đầu vào mà stub có thể match. Nó **không thay thế quá trình ẩn danh** dữ liệu.
- **byType()** mô tả kiểu; nó không tự chứng minh quantity lớn hơn 0 hoặc SKU tồn tại.
- Các giá trị response cũng có thể được kiểm chứng bằng matcher thích hợp khi producer sinh ID động, tùy phiên bản và cơ chế DSL.
- Chỉ dùng matcher cho trường có tính biến động được công nhận; ràng buộc quá lỏng khiến stub trả thành công cho những request producer thật không chấp nhận.

Một matcher không nên chỉ được chọn với mục đích “giấu” định danh. **Hợp đồng phải chứa dữ liệu tổng hợp ngay từ đầu**, sau đó matcher được dùng để diễn đạt quy tắc dữ liệu mà consumer phụ thuộc.

## 7. Giữ cấu trúc và quan hệ dữ liệu khi ẩn danh

Một lỗi thường gặp là xóa thông tin nhạy cảm bằng cách làm mất luôn quan hệ nghiệp vụ.

Ví dụ, một event có customerId và orderId; consumer dùng customerId để liên kết sự kiện với hồ sơ đã tải trước. Nếu thay **mọi customerId bằng một chuỗi duy nhất** thì test có thể bỏ sót lỗi nhầm khách hàng hoặc trùng khóa.

Thay vào đó, tạo những mã tổng hợp khác nhau nhưng ổn định trong cùng kịch bản:

~~~json
{
  "customerId": "CUS-TEST-1001",
  "orders": [
    {"orderId": "ORD-TEST-9001", "customerId": "CUS-TEST-1001"},
    {"orderId": "ORD-TEST-9002", "customerId": "CUS-TEST-1001"}
  ]
}
~~~

Nếu kịch bản có hai khách hàng, hãy dùng hai mã tổng hợp khác nhau. Tính liên kết giữa các trường được giữ, nhưng không có liên kết với định danh thật.

Khi cần tạo nhiều fixture lớn, có thể áp dụng cơ chế sinh dữ liệu tổng hợp với seed cố định và các quy tắc nhất quán. **Seed không phải phương pháp bảo vệ dữ liệu** nếu thuật toán dùng đầu vào là thông tin thật có thể đoán được; để làm hợp đồng, nên tạo bộ dữ liệu hoàn toàn hư cấu từ đầu.

Các nguyên tắc cần giữ:

| Quy tắc | Cách áp dụng |
| --- | --- |
| Đúng schema | Giữ field, kiểu, object/array và định dạng mà API yêu cầu |
| Đúng quan hệ | Các bản ghi liên kết tới nhau bằng mã tổng hợp nhất quán |
| Đúng biên nghiệp vụ | Tạo số lượng tối thiểu/tối đa, đơn thiếu dữ liệu, trạng thái lỗi bằng kịch bản riêng |
| Không nhận dạng | Tránh phối hợp các chi tiết thật có thể dẫn tới tái nhận dạng |
| Có thể tái lập | Fixture ổn định qua nhiều lần chạy test |
| Dễ review | Tên rõ như CUS-TEST, SKU-TEST, địa chỉ thử nghiệm, tên miền thử nghiệm |

## 8. Không đưa bí mật xác thực vào DSL và stub

Một ví dụ không nên xuất hiện trong repository:

~~~yaml
# PHẢN VÍ DỤ: không đưa giá trị token thật hoặc mật khẩu thật vào tệp.
request:
  headers:
    Authorization: "Bearer <TOKEN_LAY_TU_PRODUCTION>"
~~~

Ngay cả khi phía producer yêu cầu header Authorization, **giá trị secret thực** không phải một phần kiến thức hợp đồng cần công bố. Hãy tách:

1. **Cam kết giao diện:** có thể cần xác minh endpoint yêu cầu kiểu xác thực nào hoặc một claim/quyền cụ thể có tác động đến phản hồi.
2. **Cách test được cấp quyền:** một test identity và credential riêng, được cấp bởi môi trường test và quản lý qua hạ tầng test/secret store khi cần.
3. **Bảo vệ artifact:** không tạo stub mapping, expected body hoặc log chứa bearer token thật hay cookie phiên.

Với các contract chỉ kiểm thử hình dạng JSON và phản hồi nghiệp vụ, có thể test ở một lớp thích hợp với cơ chế auth giả lập được kiểm soát. Nếu cần kiểm thử xác thực thực sự, phải bổ sung **security/integration tests** chuyên biệt thay vì đưa token production vào fixture.

**Không nên in token** vào log khi một assertion thất bại. Redaction ở logger và test report quan trọng vì header có thể lọt vào stack trace, request dump hoặc bản ghi thất bại của Stub Runner.

## 9. Dữ liệu thông điệp cũng cần được loại bỏ thông tin production

Hợp đồng message-based có nguy cơ chứa dữ liệu nhạy cảm giống HTTP contract. Ví dụ, consumer chỉ cần biết đơn hàng nào vừa được thanh toán và thời điểm phát sinh sự kiện, không nhất thiết phải nhận tên, số điện thoại hoặc địa chỉ giao hàng của người mua.

Một payload tổng hợp tối thiểu:

~~~json
{
  "eventType": "ORDER_PAID",
  "eventId": "EVT-TEST-0001",
  "orderId": "ORD-TEST-9001",
  "occurredAt": "2026-01-15T08:00:00Z"
}
~~~

Ví dụ hợp đồng **Groovy DSL** cho thông điệp được producer phát:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description "Phát sự kiện thanh toán với dữ liệu tổng hợp"
    label "order_paid"

    input {
        triggeredBy("publishTestOrderPaid()")
    }

    outputMessage {
        sentTo("order-events")
        body(
            eventType: "ORDER_PAID",
            eventId: "EVT-TEST-0001",
            orderId: "ORD-TEST-9001",
            occurredAt: "2026-01-15T08:00:00Z"
        )
        headers {
            contentType(applicationJson())
        }
    }
}
~~~

Đây là kịch bản minh họa: producer test phải có phương thức **publishTestOrderPaid()** trong ngữ cảnh test và cơ chế xác minh message phù hợp. Không cần phát một sự kiện production thật để có bằng chứng hợp đồng.

Khi consumer cần biết email hoặc mã khách hàng vì giao diện công khai yêu cầu, vẫn có thể kiểm thử bằng dữ liệu tổng hợp. Đồng thời, cần cân nhắc **thu hẹp payload**: không thêm địa chỉ, số điện thoại hoặc thông tin thanh toán vào event chỉ vì producer đang có sẵn chúng.

Trong môi trường messaging, thông tin nhạy cảm có thể xuất hiện cả trong **header**, routing key, message key, trace metadata và dead-letter queue. Việc chỉ ẩn một trường trong payload chưa chắc đủ; phải xem cả luồng thông điệp và log sinh ra trong test.

## 10. Ẩn danh không làm thay đổi ý nghĩa hợp đồng

Khi thay dữ liệu production bằng dữ liệu thử nghiệm, phải giữ các đặc điểm mà consumer thực sự cần:

| Cần giữ | Có thể thay bằng dữ liệu tổng hợp |
| --- | --- |
| HTTP method, URL, status code | ID bản ghi thật trong ví dụ |
| Tên field, vị trí lồng nhau | Email/địa chỉ/tên người thật |
| Kiểu dữ liệu và định dạng công khai | Giá trị giao dịch và số tiền cụ thể nếu kịch bản không ràng buộc số đó |
| Giá trị enum mang nghĩa nghiệp vụ | Tên khách hàng hoặc số điện thoại |
| Quy tắc đồng nhất giữa các ID trong một kịch bản | Tên tenant hay mã tài khoản thật |
| Nhánh lỗi mà consumer xử lý | Thông báo lỗi chứa dữ liệu khách hàng thực |

**Ví dụ về kiểu dữ liệu:** nếu API yêu cầu số tiền dạng số nguyên đơn vị nhỏ nhất, đừng thay nó bằng chuỗi chữ để dễ che giá trị. Giữ kiểu số và dùng một lượng tiền tổng hợp có ý nghĩa.

**Ví dụ về datetime:** nếu consumer cần chuỗi thời gian có múi giờ theo ISO-8601, dùng một thời điểm giả cố định hoặc matcher đúng định dạng; không dán timestamp gắn với lịch sử giao dịch của khách hàng thực.

**Ví dụ về lỗi:** nếu consumer dựa vào mã lỗi **ORDER_NOT_FOUND**, giữ mã đó; không cần giữ nội dung message từng tiết lộ ID hay email thực từ log production.

Việc ẩn danh **không phải lý do sửa luôn schema API**. Nếu producer/consumer đang cần một trường nhạy cảm, hãy dùng dữ liệu tổng hợp cho trường đó trong test; việc loại trường khỏi giao diện thực cần được đánh giá như một thay đổi hợp đồng riêng.

## 11. Các lỗi ẩn danh thường gặp

### Chỉ thay tên nhưng giữ đặc điểm nhận dạng khác

Ví dụ thay “Người mua A” thành “Test User” nhưng giữ ngày sinh, số điện thoại, mã bưu chính hiếm hoặc lịch sử giao dịch thực. Khi kết hợp nhiều thuộc tính, vẫn có thể xác định lại người gốc.

**Cách xử lý:** tạo một bộ dữ liệu tổng hợp độc lập; bỏ những trường không cần thiết, và đánh giá khả năng liên kết giữa các trường còn lại.

### Hash trực tiếp email hoặc số điện thoại thật

Hash thường không đồng nghĩa với ẩn danh. Với không gian đầu vào dễ đoán, người khác có thể thử nhiều giá trị để tìm ra bản gốc. Nếu vẫn giữ bảng ánh xạ hoặc khóa liên kết thì dữ liệu có thể thuộc loại giả danh.

**Cách xử lý:** không cần xuất phát từ dữ liệu thật khi tạo contract. Tạo ID tổng hợp có format phù hợp và không ánh xạ sang tài khoản thực.

### Dùng ngẫu nhiên làm dữ liệu hợp đồng

Sinh UUID và timestamp ngẫu nhiên lúc plugin nạp Groovy có thể khiến một revision hợp đồng tạo ra test/stub khác nhau ở mỗi lần chạy.

**Cách xử lý:** dùng fixture tổng hợp cố định hoặc matcher mô tả giá trị động; có thể sinh dữ liệu theo quy tắc trong setup test khi thật sự cần.

### “Che” token trong một file nhưng còn trong log/artifact

Thay token bằng giá trị giả trong YAML không xóa token đã xuất hiện ở Git history, CI artifact, cache, ảnh chụp hoặc báo cáo test cũ.

**Cách xử lý:** xử lý sự cố lộ secret theo quy trình của tổ chức, bao gồm thu hồi/đổi secret nếu cần, kiểm tra nguồn đã phát tán và thu hẹp khả năng truy cập. Việc sửa hợp đồng là bước cần thiết nhưng chưa phải toàn bộ biện pháp khắc phục.

### Dùng một giá trị giả cho mọi bản ghi

Nếu mọi khách hàng, đơn hàng hoặc sự kiện đều dùng cùng một mã TEST, test có thể bỏ sót lỗi phân biệt đối tượng, trùng key hoặc quan hệ một-nhiều.

**Cách xử lý:** tạo tập mã tổng hợp đủ phân biệt, nhất quán và có thể tái lập.

## 12. Kiểm soát ở từng giai đoạn của Spring Cloud Contract

Chỉ rà soát tệp Groovy/YAML chưa đủ khi hệ thống còn sinh test, tạo stub, lưu artifact và chạy CI.

~~~mermaid
flowchart TD
    A["Thiết kế fixture tổng hợp"] --> B["Review Groovy/YAML"]
    B --> C["Sinh test và stub"]
    C --> D["Chạy producer contract tests"]
    C --> E["Kiểm tra nội dung stub artifact"]
    D --> F["Rà soát log/test report"]
    E --> G["Phát hành stub đã xác minh"]
    G --> H["Consumer dùng Stub Runner"]
    H --> I["Rà soát log consumer CI"]
    F --> J["Quyết định phát hành trong phạm vi đã kiểm chứng"]
    I --> J
~~~

| Giai đoạn | Điểm kiểm tra |
| --- | --- |
| Viết contract | Dữ liệu mẫu là tổng hợp, không có ID/email/token/địa chỉ production |
| Review pull request | Người review xem body, header, fixture được tham chiếu và thay đổi dữ liệu |
| Sinh producer tests | Test được sinh không nhúng thông tin production từ DSL, helper hay fixture |
| Chạy producer tests | Test dùng test database, test identity; không truy cập nguồn dữ liệu production khi không được phép |
| Tạo stub | Mapping/response file không chứa secret hay thông tin cá nhân thật |
| Phát hành stub | Artifact version và checksum có thể truy vết; chỉ phát hành artifact đã được kiểm tra |
| Stub Runner và consumer CI | Test dùng đúng stub version, log có cơ chế che header và dữ liệu nhạy cảm |
| Lưu trữ và dọn dẹp | Artifact/log/history có chính sách truy cập và thời hạn lưu phù hợp |

**Đặc biệt với stub:** một lần chạy producer test PASS không chứng minh stub đã được kiểm tra về dữ liệu nhạy cảm. Stub có thể chứa raw body và header được chuyển từ hợp đồng; cần xem trực tiếp nội dung được đóng gói hoặc dùng bước kiểm tra artifact tự động.

## 13. Đưa kiểm tra dữ liệu nhạy cảm vào CI

Một CI pipeline tham khảo có thể bao gồm:

1. Kiểm tra các tệp hợp đồng, fixture và thay đổi liên quan bằng cơ chế tìm secret đã được dự án phê duyệt.
2. Áp dụng quy tắc kiểm tra dữ liệu nhạy cảm trong request/response examples, message payload, header và tệp test.
3. Sinh producer tests và stub từ đúng revision.
4. Chạy generated producer tests; nếu thất bại, dừng phát hành.
5. Kiểm tra stub artifact đã đóng gói để tìm token, domain production và dữ liệu không mong muốn.
6. Phát hành stub có version xác định và chạy consumer tests với Stub Runner.
7. Lưu bằng chứng kiểm thử, kiểm tra log/artifact được phát hành và chỉ công bố tương thích trong phạm vi đã xác minh.

Một biểu diễn **mã giả** cho release gate:

~~~yaml
# Mẫu ý tưởng cho pipeline, không phải cấu hình CI chạy trực tiếp.
contract_security_gate:
  require:
    - reviewed_synthetic_fixtures
    - no_known_secrets_in_contracts
    - no_production_identifiers_in_contract_examples
    - producer_contract_tests_pass
    - stub_artifact_scanned
    - consumer_stub_tests_pass
    - logs_and_artifacts_access_reviewed
~~~

**Secret scanning không tự phát hiện mọi dữ liệu cá nhân.** Một email thật có thể trông giống email mẫu và một chuỗi giả có thể khớp regex cảnh báo. Vì thế, kết hợp kiểm tra tự động với review nội dung, quy ước dữ liệu thử nghiệm và kiểm soát quyền truy cập.

Không nên lưu **giá trị secret bị phát hiện** vào log kiểm tra hoặc báo cáo PR. Nếu scanner phát hiện lỗi, báo loại vấn đề, tệp, vị trí phù hợp và quy trình xử lý; hạn chế hiển thị lại giá trị nhạy cảm.

### Một lỗi CI cần tránh

Producer CI tạo stub từ contract chứa địa chỉ email thật; consumer CI dùng stub đó để chạy test. Hai pipeline đều PASS, nhưng artifact đã phát hành chứa dữ liệu không nên chia sẻ.

**PASS về mặt hợp đồng không có nghĩa PASS về mặt quản trị dữ liệu.** Release gate phải yêu cầu đồng thời:

- Hành vi producer khớp hợp đồng.
- Consumer xử lý đúng stub từ phiên bản đã xác minh.
- Hợp đồng, fixture và artifact không phát tán thông tin production ngoài phạm vi cho phép.

## 14. Tình huống thực hành

### Bài tập A — Phân loại dữ liệu

Bạn chuẩn bị contract POST /api/orders. Request mẫu có: customerId thật, email thật, trạng thái PAID, số lượng 2, tên bảng database, API key và tổng tiền.

**Yêu cầu:** phân loại thông tin nào cần giữ nguyên như quy tắc giao diện, thông tin nào phải thay bằng dữ liệu tổng hợp và thông tin nào cần loại khỏi contract.

**Gợi ý:** giữ tên field, kiểu, giá trị enum công khai và quan hệ nghiệp vụ; thay customerId/email/số tiền mẫu bằng giá trị tổng hợp; không đưa API key hay tên bảng nội bộ vào hợp đồng nếu chúng không thuộc giao diện công khai.

### Bài tập B — Thiết kế fixture có quan hệ

Một consumer phải xử lý hai đơn hàng của cùng một khách hàng và một đơn của khách hàng khác. Hãy thiết kế ba orderId và hai customerId **tổng hợp**, đảm bảo quan hệ một-nhiều nhất quán qua toàn bộ fixture.

**Gợi ý:** đặt tên như CUS-TEST-1001, CUS-TEST-1002 và ORD-TEST-9001/9002/9003; dùng cùng mã khách hàng cho hai đơn liên quan và mã khác cho đơn thứ ba.

### Bài tập C — Contract với định danh động

Producer tạo orderId động nên contract với response cố định **ORD-TEST-9001** thất bại; một thành viên đề xuất lấy orderId thật từ production để ghi lại.

**Yêu cầu:** giải thích vì sao đề xuất không phù hợp và cách sửa hợp đồng.

**Gợi ý:** dùng matcher theo định dạng orderId nếu phù hợp hoặc setup fixture/test để sinh kết quả có thể kiểm soát. Dùng dữ liệu tổng hợp và kiểm tra cơ chế matcher thật sự được sinh; không cần lấy ID từ production.

### Bài tập D — Stub rò rỉ dữ liệu

Một stub JAR đã được phát hành có chứa token thật trong header của mapping. Tệp contract nguồn đã được sửa để thay token bằng chuỗi thử nghiệm.

**Yêu cầu:** liệt kê các vấn đề còn tồn tại và đề xuất hành động trước khi tiếp tục phát hành.

**Gợi ý:** xem lại secret đã bị lộ ở artifact repository, bản cache, log và các bản tải về; thực hiện quy trình thu hồi/đổi token khi cần; kiểm tra và phát hành lại artifact an toàn. Chỉnh sửa nguồn không đủ để xử lý các bản sao cũ.

### Bài tập E — Kiểm tra giới hạn của bằng chứng

Producer test PASS với body có customerId CUS-TEST-1001. Stub Runner cũng trả phản hồi thành công cho đúng body này.

**Yêu cầu:** có thể kết luận mọi customerId đều hợp lệ, hoặc mọi thông tin production đều đã được loại bỏ không? Cần thêm kiểm tra nào?

**Gợi ý:** không. Một test minh họa chỉ kiểm chứng kịch bản đã chạy. Cần matcher/validation phù hợp cho các biến thể input và rà soát dữ liệu, artifact, log bằng cơ chế độc lập.

## 15. Checklist trước khi lưu và phát hành hợp đồng

- [ ] Tất cả dữ liệu mẫu đều được kiểm tra nguồn gốc; ưu tiên dữ liệu tổng hợp tạo mới.
- [ ] Không có tên, email, địa chỉ, số điện thoại hoặc định danh khách hàng thật.
- [ ] Không có access token, API key, mật khẩu, cookie phiên, khóa ký hoặc thông tin xác thực production.
- [ ] Không có thông tin giao dịch, số thẻ hoặc dữ liệu kinh doanh nhạy cảm thật.
- [ ] Các định danh tổng hợp có định dạng hợp lệ, nhất quán và dễ nhận biết là dữ liệu thử nghiệm.
- [ ] Tên trường, kiểu dữ liệu, cấu trúc JSON, enum và mã lỗi công khai được giữ đúng.
- [ ] Dữ liệu động có matcher hoặc setup test phù hợp, không phụ thuộc ID hay timestamp production.
- [ ] Các mối quan hệ giữa bản ghi được kiểm tra bằng fixture tổng hợp nhất quán.
- [ ] Header, message payload, metadata, fixture và dữ liệu lỗi cũng được rà soát.
- [ ] Generated producer tests thực sự chạy với dữ liệu test phù hợp.
- [ ] Stub artifact được kiểm tra nội dung trước khi phát hành; không chỉ dựa vào source DSL.
- [ ] Stub Runner và consumer CI dùng đúng phiên bản stub đã xác minh.
- [ ] Log, CI artifact và quyền truy cập được kiểm soát; scanner không in lại secret.
- [ ] Bất kỳ dữ liệu nhạy cảm đã lộ trong artifact/history được xử lý theo quy trình sự cố, không chỉ sửa tệp mới.
- [ ] Tuyên bố tương thích chỉ bao phủ hành vi, phiên bản và consumer có kết quả kiểm thử tương ứng.

**Ghi nhớ:** Hợp đồng Spring Cloud Contract phải thể hiện **hành vi và cấu trúc dữ liệu cần tương thích**, không phải bản sao thông tin production. Dữ liệu tổng hợp được thiết kế có chủ đích, fixture tái lập, matcher phù hợp và kiểm tra generated tests/stub/CI giúp phát hiện thay đổi API không tương thích mà không đưa thông tin nhạy cảm vào vòng đời hợp đồng.

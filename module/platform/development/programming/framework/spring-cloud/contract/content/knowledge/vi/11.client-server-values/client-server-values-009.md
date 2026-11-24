# Giới hạn của giá trị thực thi bằng mã phía kiểm thử

## Mục tiêu bài học

Trong **Spring Cloud Contract**, một hợp đồng HTTP hoặc thông điệp có thể được dùng để tạo **kiểm thử phía producer** và **stub phía consumer**. Groovy DSL hỗ trợ định nghĩa hai giá trị cho cùng một phần dữ liệu: một giá trị phục vụ phía consumer (client), một giá trị phục vụ phía producer (server). Ngoài các giá trị cố định và biểu thức chính quy, một số ngữ cảnh còn cho phép dùng **mã hoặc phương thức phía kiểm thử** để xác minh giá trị động.

Khả năng này hữu ích khi producer trả mã định danh, thời gian hoặc dữ liệu không thể so sánh với một chuỗi cố định. Tuy nhiên, **mã chạy trong generated test không trở thành hành vi mà stub tự thực thi**, và phương thức test không nên được dùng để tính lại kết quả bằng chính logic producer đang cần kiểm chứng.

Sau bài học, bạn có thể:

- Phân biệt giá trị **client/consumer** và **server/producer** trong request và response.
- Xác định thời điểm một giá trị được kiểm tra bằng biểu thức, matcher hoặc phương thức do test cung cấp.
- Nắm được phạm vi và giới hạn của **execute(...)**, **byCommand(...)** trong Groovy DSL.
- Tổ chức phương thức kiểm thử, fixture và lớp nền để kiểm tra giá trị động có thể tái lập.
- Nhận biết rủi ro do stub và generated test kiểm tra những điều khác nhau.
- Đưa kết quả producer tests, stub, Stub Runner và CI vào kết luận tương thích có phạm vi rõ ràng.

## 1. Vì sao cùng một trường dữ liệu cần giá trị ở hai phía?

Giả sử Checkout gửi yêu cầu tạo đơn hàng và Order Service trả về một ID do server sinh:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json

{"customerId":"CUS-TEST-1001","quantity":2}
~~~

Response:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{"orderId":"ORD-4821","status":"CREATED"}
~~~

Trong production, **orderId** có thể thay đổi giữa các lần gọi. Consumer cần nhận một ID mẫu hợp lệ để kiểm thử luồng tiếp theo, còn producer test cần xác minh ID thực tế có hình dạng hoặc đặc điểm đúng. Khóa cứng mọi lần trả về phải là **ORD-4821** có thể khiến test sai mục đích.

Spring Cloud Contract giải quyết sự khác biệt này bằng khả năng đặt **giá trị hai phía** trong contract. Hai tên thường gặp là:

- **consumer(...)**, còn có tên tương đương theo góc nhìn client là **client(...)**.
- **producer(...)**, còn có tên tương đương theo góc nhìn server là **server(...)**.

Các helper này thể hiện **đối tượng sẽ sử dụng giá trị**, không phải nơi phương thức Groovy được thực thi ngay lập tức.

### Bảng ánh xạ quan trọng

| Vị trí trong hợp đồng | Giá trị phía consumer/client | Giá trị phía producer/server |
| --- | --- | --- |
| **Request** | Dữ liệu cụ thể được generated producer test gửi | Điều kiện request mà stub dùng để match lời gọi consumer |
| **Response** | Dữ liệu mà stub trả cho consumer | Kỳ vọng hoặc matcher mà generated producer test dùng để xác minh response thật |

Đây là cách hiểu cốt lõi của các giá trị hai phía trong Spring Cloud Contract. Do request và response đi theo hai chiều ngược nhau, **vai trò của mỗi giá trị trong generated test và stub cũng đảo chiều**. Nếu chỉ ghi nhớ “consumer luôn là stub” hay “producer luôn là test” mà không xét request/response, rất dễ viết sai.

~~~mermaid
flowchart LR
    A["Hợp đồng hai phía"] --> B["Request"]
    A --> C["Response"]
    B --> D["consumer: input cho producer test"]
    B --> E["producer: matcher của stub"]
    C --> F["consumer: output mẫu của stub"]
    C --> G["producer: kiểm tra response trong producer test"]
~~~

## 2. Ví dụ giá trị hai phía với request động

Consumer có thể gửi nhiều mã khách hàng theo một định dạng. Producer test cần một mã cụ thể để setup dữ liệu, nhưng stub không nên chỉ chấp nhận đúng một khách hàng.

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description "Tạo đơn hàng với mã khách hàng có định dạng"

    request {
        method POST()
        url "/api/orders"
        headers {
            contentType(applicationJson())
        }
        body(
            customerId: value(
                consumer("CUS-TEST-1001"),
                producer(regex("CUS-[A-Z0-9-]+"))
            ),
            quantity: 2
        )
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

Trong ngữ cảnh request:

1. **Generated producer test** dùng giá trị mẫu CUS-TEST-1001. Test setup cần chuẩn bị dữ liệu thích hợp hoặc hành vi kiểm soát được cho khách hàng mẫu.
2. **Stub** có thể sử dụng biểu thức chính quy để match những mã khác cùng định dạng.
3. Một producer test PASS với CUS-TEST-1001 **không chứng minh** producer xử lý đúng tất cả chuỗi mà regex chấp nhận.
4. Regex chỉ kiểm tra hình dạng mã, **không chứng minh khách hàng tồn tại hay có quyền tạo đơn hàng**.

Khi chọn regex, tránh đặt điều kiện quá rộng chỉ để làm stub dễ match. Nếu producer thực tế chỉ nhận một tập định dạng hẹp hơn, stub có thể chấp nhận request mà producer thật sẽ từ chối.

### Giá trị hai phía trong YAML DSL

YAML DSL cũng có khả năng khai báo các quy tắc match và giá trị động, nhưng cấu trúc không giống hệt các lời gọi Groovy. Với dữ liệu request lồng nhau, một lựa chọn là **request.matchers.body**:

~~~yaml
description: "Tạo đơn hàng với mã khách hàng theo định dạng"
name: create_order_customer_pattern
request:
  method: POST
  url: /api/orders
  headers:
    Content-Type: application/json
  body:
    customerId: "CUS-TEST-1001"
    quantity: 2
  matchers:
    body:
      - path: $.customerId
        type: by_regex
        value: "CUS-[A-Z0-9-]+"
response:
  status: 201
  headers:
    Content-Type: application/json
  body:
    orderId: "ORD-TEST-9001"
    status: CREATED
~~~

Đây là ví dụ về **matcher khai báo**. Không nên suy luận rằng một tùy chọn Groovy như execute(...) có thể viết lại bằng cùng cú pháp trong YAML. Hãy xác minh tính năng và cú pháp theo phiên bản DSL thực tế.

## 3. Response động: stub cần ví dụ, producer test cần xác minh

Ở response, hai phía có nhu cầu ngược với request:

- Consumer test qua stub cần một giá trị **cụ thể** để mô phỏng server.
- Generated producer test cần kiểm tra **giá trị thực tế** mà producer tạo ra.

Ví dụ Groovy DSL với response chứa ID động:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    request {
        method POST()
        url "/api/orders"
        headers {
            contentType(applicationJson())
        }
        body(customerId: "CUS-TEST-1001", quantity: 2)
    }

    response {
        status 201
        headers {
            contentType(applicationJson())
        }
        body(
            orderId: value(
                consumer("ORD-TEST-9001"),
                producer(regex("ORD-[A-Z0-9-]+"))
            ),
            status: "CREATED"
        )
    }
}
~~~

Với response:

- Stub có thể trả **ORD-TEST-9001** cho consumer.
- Producer test kiểm tra ID thực có định dạng theo regex; **không đòi** server luôn sinh cùng ID.
- Consumer test cần kiểm tra logic ứng dụng xử lý ID được trả về; test chỉ xác minh endpoint stub trả 201 là chưa đủ.

Biểu thức này vẫn có giới hạn: regex phù hợp không chứng minh mã vừa sinh là **duy nhất**, được lưu trong cơ sở dữ liệu, truy vấn được về sau hay thuộc đúng khách hàng. Các hành vi đó cần hợp đồng/kịch bản khác hoặc kiểm thử tích hợp thích hợp.

## 4. Giá trị thực thi bằng mã phía kiểm thử là gì?

Khi regex và matcher khai báo không diễn đạt đủ điều kiện, Spring Cloud Contract Groovy DSL có thể hỗ trợ các cách **tham chiếu lời gọi mã phía kiểm thử**, thường được biết tới qua **execute(...)** hoặc matcher **byCommand(...)** trong những ngữ cảnh được hỗ trợ.

Điểm cần phân biệt:

| Cơ chế | Dùng để làm gì? | Nơi cần phương thức thực thi |
| --- | --- | --- |
| Giá trị cố định | Khớp một giá trị cụ thể | Không cần phương thức riêng |
| Regex, byType hoặc matcher khai báo | Kiểm tra kiểu, hình dạng hoặc quy tắc được DSL hỗ trợ | Công cụ sinh test/stub xử lý matcher |
| **execute(...)** | Tham chiếu một lời gọi được đưa vào generated test ở phía và vị trí phù hợp | Ngữ cảnh của generated test, thường qua base test class |
| **byCommand(...)** | Dùng lệnh hoặc phương thức kiểm tra tùy chỉnh cho phần body được chọn | Ngữ cảnh kiểm thử của generated producer test |

Không phải mọi chỗ nhận **value(...)** đều có thể đặt một đoạn mã tùy ý, và không phải mọi tổ hợp execute/matcher đều được hỗ trợ giống nhau giữa các phiên bản, generator và DSL. Cần xem **mã generated test** để xác nhận cú pháp và thời điểm thực thi.

**Quan trọng:** execute(...) trong contract **không** làm WireMock/Stub Runner trở thành trình chạy phương thức Java trong ứng dụng producer. Stub được tạo từ contract thường là tập mapping, matcher và response đã chuẩn bị.

### Tại sao cần thận trọng?

Nếu test dùng một phương thức do chính producer cung cấp để tính giá trị kỳ vọng, cả response thật và kỳ vọng có thể cùng sai. Một test như thế có thể PASS mà không kiểm chứng đúng cam kết với consumer.

Mặt khác, phương thức kiểm tra có quyền truy cập vào classpath và môi trường test. Nếu nó đọc mạng, đồng hồ hệ thống, cơ sở dữ liệu production hoặc biến môi trường không ổn định thì kết quả test khó tái lập và không còn phản ánh một hợp đồng độc lập.

## 5. Trường hợp phù hợp với byCommand: xác minh một giá trị phức tạp

Giả sử API trả một mã đơn hàng cần bắt đầu bằng **ORD-**, có hậu tố theo quy tắc nghiệp vụ và không được để trống. Trước hết hãy hỏi: matcher khai báo có đủ chưa? Nếu một regex biểu diễn chính xác điều kiện cần kiểm tra thì **regex thường đơn giản và dễ review hơn**.

Khi quy tắc phức tạp hơn, có thể dùng một phương thức kiểm tra phía producer test. Minh họa ý tưởng với matcher:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    request {
        method GET()
        url "/api/orders/ORD-1001"
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(orderId: "ORD-1001", status: "PAID")
        bodyMatchers {
            jsonPath('$.orderId', byCommand('isValidOrderId($it)'))
        }
    }
}
~~~

Trong một số cách sinh test, **$it** đại diện cho giá trị thực tế được trích từ response tại JSONPath được chọn. Lệnh hoặc phương thức **isValidOrderId(...)** phải được khai báo đúng chữ ký và kiểu trả về/cách assertion mà generator mong đợi.

Một lớp nền kiểm thử có thể chứa logic kiểm tra thuần túy. Ví dụ **minh họa nhiệm vụ của phương thức**:

~~~java
public abstract class OrderContractTestBase {

    protected boolean isValidOrderId(String actual) {
        return actual != null
            && actual.matches("ORD-[0-9]{4}");
    }
}
~~~

Cách cấu hình base test class, vị trí phương thức, kiểu tham số và dạng code do generator phát sinh phải được kiểm tra trong dự án thật. Nếu test mong đợi phương thức **assert** thay vì giá trị boolean, cần dùng chữ ký phù hợp và bảo đảm assertion thực sự làm test FAIL khi giá trị sai.

Đây không phải cơ chế xác nhận rằng orderId có bản ghi tương ứng trong production. Phương thức minh họa chỉ kiểm tra một điều kiện định dạng. Nếu hợp đồng cần chứng minh ID có thể được truy vấn lại, hãy viết thêm kịch bản HTTP hoặc kiểm thử tích hợp riêng.

### Vì sao không được viết một phương thức luôn trả true?

~~~java
// Phản ví dụ: làm cho test vô nghĩa.
protected boolean isValidOrderId(String ignored) {
    return true;
}
~~~

Với một phương thức như vậy, producer có thể trả ID sai mà test vẫn PASS. Vì thế code test nên có điều kiện phủ định rõ ràng, trường hợp sai phải dẫn tới **test thất bại** và có bài kiểm tra dành cho chính helper nếu quy tắc đủ phức tạp.

## 6. execute(...) không thay thế fixture và matcher

Một trường hợp khác là giá trị expected của producer test cần được lấy từ **trạng thái fixture có thể kiểm soát**, chẳng hạn mã đơn hàng do test đã thiết lập. Spring Cloud Contract có thể hỗ trợ tham chiếu một phương thức qua execute(...) trong phần giá trị phía producer ở ngữ cảnh tương ứng.

Đoạn sau minh họa **mục đích của giá trị hai phía**; cần kiểm tra cách generator hiện tại diễn giải execute và chữ ký method:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    request {
        method GET()
        url "/api/orders/ORD-1001"
    }
    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            id: "ORD-1001",
            status: "PAID",
            processedAt: value(
                consumer("2026-01-15T08:00:00Z"),
                producer(execute("expectedProcessedAt()"))
            )
        )
    }
}
~~~

Trong ví dụ:

- **consumer(...)** đưa cho stub một timestamp mẫu, đủ để consumer xử lý response.
- **producer(execute(...))** thể hiện mong muốn generated producer test dùng phương thức có sẵn để xác minh hoặc lấy giá trị kỳ vọng theo cách generator hỗ trợ.
- Phương thức **expectedProcessedAt()** phải tồn tại trong ngữ cảnh test, có kết quả ổn định và không dựa vào thời gian hiện tại một cách tùy tiện.
- Nếu thời gian thực tế không thể biết trước nhưng chỉ cần đúng định dạng, nên cân nhắc **regex/matcher cho response** thay vì tạo một cơ chế execute phức tạp.

Không lấy kỳ vọng bằng cách gọi chính endpoint đang kiểm tra rồi dùng response đó làm expected. Làm thế khiến phép kiểm tra gần như tự xác nhận, dễ bỏ sót lỗi.

### Ranh giới hợp lý của một phương thức kiểm thử

| Nên làm | Không nên làm |
| --- | --- |
| Đối chiếu một giá trị thực với quy tắc nghiệp vụ độc lập | Lấy expected trực tiếp từ kết quả của chính service đang kiểm tra |
| Dùng fixture có phiên bản hoặc giá trị tính trước từ đầu vào cố định | Đọc random, đồng hồ thực hoặc môi trường không kiểm soát |
| Tạo assertion thất bại khi vi phạm hợp đồng | Nuốt exception rồi trả PASS |
| Kiểm tra định dạng, tính nhất quán giữa các trường đã thỏa thuận | Khóa chặt thứ tự gọi repository hay cấu trúc class nội bộ |
| Giữ helper nhỏ, thuần, dễ review và có thể tái lập | Gọi HTTP production hoặc truy cập dữ liệu thật |

## 7. Phân biệt mã Groovy lúc nạp DSL với mã trong generated test

Một điểm dễ nhầm là viết Java/Groovy code ngay trong file contract và cho rằng mọi đoạn mã sẽ được chạy lúc producer test thực thi.

Ví dụ:

~~~groovy
// Phản ví dụ: biến được tạo khi Groovy contract được xử lý.
def generatedNow = java.time.Instant.now().toString()
~~~

Nếu dùng biến này làm response body, bản hợp đồng được sinh có thể phụ thuộc thời điểm build. Nó khác về bản chất với một **lời gọi phương thức mà generated test sẽ thực thi** theo cơ chế execute/byCommand.

~~~mermaid
sequenceDiagram
    participant D as DSL Groovy
    participant B as Build/Verifier
    participant T as Generated producer test
    participant S as Stub Runner
    participant C as Consumer
    D->>B: Đánh giá script và mô hình hợp đồng
    B->>T: Sinh test cùng matcher/lời gọi hỗ trợ
    B->>S: Sinh mapping/stub
    T->>T: Chạy assertion/helper trong môi trường test
    C->>S: Gửi request
    S-->>C: Trả dữ liệu stub đã cấu hình
~~~

Đặc biệt:

1. **Khi sinh test:** plugin có thể đánh giá Groovy DSL và tạo ra artifact. Mã Groovy tùy ý tại giai đoạn này có thể tạo tác dụng phụ ngay trên máy build.
2. **Khi test chạy:** lời gọi có trong generated test chỉ thực hiện nếu method tồn tại, ký hiệu đúng và môi trường test được cấu hình.
3. **Khi stub chạy:** consumer thường chỉ giao tiếp qua HTTP/message với mapping đã tạo. Nó không được quyền gọi phương thức tùy ý trong base test class của producer.

Do đó, một lời gọi execute không phải phép màu “đồng bộ dữ liệu động” giữa hai tiến trình hay hai repository. Cần thiết kế **giá trị mẫu cho stub** và **quy tắc xác minh cho producer** sao cho cả hai cùng phản ánh cam kết thực sự.

## 8. Giới hạn biên dịch và môi trường của phương thức kiểm thử

Để sử dụng cơ chế thực thi bằng mã, cần xem xét ít nhất năm điều kiện kỹ thuật:

1. **Khả năng hỗ trợ của DSL/generator.** Từng vị trí request/response, từng dạng matcher và từng loại test generator có thể chấp nhận tập tính năng khác nhau.
2. **Chữ ký phương thức.** Tên, số tham số, kiểu tham số, khả năng truy cập và kiểu trả về phải phù hợp với đoạn generated test thực tế.
3. **Ngữ cảnh lớp nền.** Generated test phải kế thừa hoặc truy cập đúng base test class được cấu hình.
4. **Dữ liệu đầu vào.** Giá trị JSONPath có thể đến dưới dạng String, Number, List hoặc null; helper phải xử lý kiểu và giá trị thiếu một cách có chủ đích.
5. **Tính quyết định.** Helper phải trả cùng kết quả với cùng dữ liệu, trừ khi chính sự biến động là một phần hợp đồng có thể kiểm chứng.

Một helper tưởng đúng có thể gây lỗi nếu JSONPath trỏ vào mảng nhưng method mong nhận một chuỗi, hoặc method nhận số nguyên trong khi parser đưa ra kiểu số khác. Cần kiểm tra generated source và chạy test để xác minh những chi tiết đó ở giai đoạn build/QA phù hợp.

Đừng sửa generated test bằng tay để “khớp” chữ ký. **Nguồn cần sửa** là DSL, base class, cấu hình generator hoặc fixture. Test được sinh lại có thể ghi đè mọi thay đổi thủ công.

## 9. Giới hạn học thuật: kiểm tra bằng mã không được che khuất hợp đồng

Một hợp đồng có thể hợp lệ về cú pháp nhưng yếu về ý nghĩa:

~~~text
Producer trả JSON
    |
    v
Generated test gọi customCheck(response)
    |
    v
customCheck() dùng implementation để quyết định đúng/sai
~~~

Khi toàn bộ quy tắc nằm trong phương thức **customCheck(...)**, người review contract không biết chính xác producer được cam kết điều gì. Tệ hơn, nếu helper gọi lại hàm xử lý nghiệp vụ của producer, test có thể kiểm tra một kết quả bằng chính thuật toán tạo ra kết quả đó.

Một hướng thiết kế rõ ràng hơn:

- Các trường, kiểu, HTTP status, mã lỗi và giá trị enum quan trọng được khai báo trực tiếp trong contract.
- Regex/matcher khai báo thể hiện quy tắc đơn giản, dễ nhìn.
- Mã kiểm tra tùy chỉnh chỉ dùng cho quy tắc không thể mô tả hợp lý bằng matcher chuẩn.
- Tên method, tài liệu và assertion nói rõ **điều kiện phải đúng**.
- Logic kiểm tra độc lập với logic triển khai producer trong phạm vi có thể.

Ví dụ, nếu consumer chỉ yêu cầu orderId khớp **ORD-** và bốn chữ số, regex đã là một hợp đồng minh bạch. Nếu consumer yêu cầu một checksum phức tạp có quy tắc công khai, helper có thể hợp lý, nhưng cần test riêng cho các trường hợp checksum sai.

## 10. Tác động đến stub và Stub Runner

Sự khác biệt giữa hai phía thường bộc lộ ở consumer CI:

| Điều producer test xác minh | Điều stub có thể mô phỏng | Giới hạn cần chú ý |
| --- | --- | --- |
| orderId có định dạng hợp lệ | Trả một orderId mẫu | Stub không chứng minh ID đó đã tồn tại trong database thật |
| Timestamp theo quy tắc | Trả timestamp mẫu cố định | Stub không chứng minh đồng hồ producer chính xác |
| Mã lỗi khi không tìm thấy đơn | Trả lỗi 404 cho request mẫu | Cần test producer thật và các nhánh lỗi quan trọng |
| Kiểm tra bằng method tùy chỉnh | Trả dữ liệu/mapping đã đóng gói | Stub không chạy method kiểm tra của producer |
| Giá trị liên quan nhiều request | Có thể cần nhiều stub/scenario được thiết kế riêng | Một mapping đơn lẻ không đảm bảo trạng thái xuyên request |

Nếu consumer dùng Stub Runner và nhận response **ORD-TEST-9001**, đó là dữ liệu mô phỏng phục vụ consumer test. Điều này **không khẳng định** producer thật sẽ trả chính ID đó. Producer phải được xác minh bằng generated test phù hợp.

Một pipeline CI có thể:

~~~mermaid
flowchart TD
    A["Hợp đồng Groovy/YAML đã review"] --> B["Sinh producer tests"]
    A --> C["Sinh stub"]
    B --> D["Chạy test với base class/helpers"]
    D --> E{"PASS và đủ test?"}
    E -->|Không| X["BLOCK"]
    E -->|Có| F["Đóng gói stub version cố định"]
    C --> F
    F --> G["Consumer test qua Stub Runner"]
    G --> H{"PASS với đúng stub?"}
    H -->|Không| X
    H -->|Có| I["Ghi bằng chứng tương thích có phạm vi"]
~~~

Nếu producer test dùng execute/byCommand nhưng không chạy được helper, pipeline phải thất bại. Không được bỏ qua test hoặc sửa matcher thành **luôn đúng** chỉ để artifact stub được phát hành.

## 11. Các lỗi dễ gặp khi dùng giá trị thực thi bằng mã

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Generated test không biên dịch | Method hoặc chữ ký không khớp | Xem source test sinh ra và base test class |
| Test luôn PASS kể cả response sai | Helper quá rộng, luôn true hoặc không assertion | Cho chạy với dữ liệu sai có kiểm soát; xác minh test phải FAIL |
| Test chập chờn | Dùng đồng hồ thực, random, phụ thuộc mạng | Tạo fixture cố định; chuyển sang matcher |
| Stub không có hành vi tính động như mong đợi | Coi execute là mã của stub | Phân biệt consumer response mẫu với producer assertion |
| Cùng contract cho hai kết quả khác nhau giữa CI | Helper/DSL dùng biến môi trường hoặc dữ liệu ngoài | Khóa cấu hình, dữ liệu và nguồn hợp đồng |
| Test sai kiểu dữ liệu | JSONPath trích Number/List nhưng helper nhận String | Kiểm tra kiểu actual và chữ ký phương thức |
| Producer test PASS nhưng consumer gặp lỗi | Stub quá đơn giản, consumer chưa kiểm tra logic hoặc thiếu kịch bản | Bổ sung consumer test và kịch bản hợp đồng cần thiết |
| Stub cũ vẫn PASS | Consumer CI chưa chọn artifact mới | Chốt phiên bản và checksum stub được phát hành |

Một lỗi khác là dùng **mã kiểm thử có tác dụng phụ** để thay đổi dữ liệu production hoặc môi trường dùng chung. Generated test phải được chạy trong môi trường kiểm thử có quyền và dữ liệu phù hợp, không nên đọc hoặc sửa trạng thái production để xác minh giá trị động.

## 12. Cách quyết định có nên dùng execute/byCommand

Hãy đặt các câu hỏi theo thứ tự:

1. **Có thể dùng giá trị cố định không?** Nếu là kịch bản đã có fixture ổn định, giá trị cố định thường đơn giản nhất.
2. **Có thể dùng matcher khai báo không?** Nếu chỉ cần định dạng ID, kiểu, độ dài hoặc một giá trị thuộc tập enum, hãy ưu tiên cú pháp DSL hỗ trợ.
3. **Có cần xác minh quy tắc phức tạp thật sự là cam kết công khai không?** Nếu có, cân nhắc helper độc lập và có test cho điều kiện đúng/sai.
4. **Method sẽ chạy ở đâu?** Cần chắc generated producer test gọi được method; stub không có cùng môi trường thực thi.
5. **Cùng fixture và cùng input có cho kết quả nhất quán không?** Nếu không, cần thiết kế lại dữ liệu hoặc matcher.
6. **Có kiểm chứng được phương thức sẽ làm test FAIL khi producer vi phạm không?** Nếu không, helper chưa phải một assertion đáng tin.

Một quy tắc hữu ích là **giữ hợp đồng khai báo càng nhiều càng tốt và chỉ dùng mã tùy chỉnh cho phần tối thiểu thật sự cần thiết**.

## 13. Bài tập tình huống

### Bài tập A — Chọn phía giá trị

Contract POST /api/orders dùng customerId cố định **CUS-TEST-1001** cho generated producer test, nhưng stub cần nhận nhiều customerId theo regex. Hãy xác định phía nào nên nhận giá trị mẫu và phía nào nên nhận regex.

**Gợi ý:** Ở request, giá trị **consumer(...)** là dữ liệu test gửi; **producer(...)** có thể chứa matcher stub dùng để nhận request consumer.

### Bài tập B — ID trong response

Producer tạo orderId động. Consumer test chỉ cần một ID mẫu để kiểm tra cách lưu/điều hướng. Producer test cần kiểm tra ID đúng định dạng.

**Yêu cầu:** viết phần response body dùng consumer value cố định và producer regex. Giải thích vì sao producer test PASS không chứng minh ID có thể truy vấn lại.

**Gợi ý:** dùng response với consumer("ORD-TEST-9001") và producer(regex("ORD-[A-Z0-9-]+")). Muốn chứng minh ID dùng được ở lần gọi tiếp theo phải có kiểm thử tích hợp riêng cho luồng đó.

### Bài tập C — Helper luôn đúng

Đội dùng byCommand gọi **validateAmount(...)**. Phương thức trả true với mọi số, kể cả âm. Producer test luôn PASS.

**Yêu cầu:** viết lại quy tắc nghiệp vụ, thêm các giá trị phản ví dụ và xác định việc nào thuộc contract, việc nào thuộc unit test.

**Gợi ý:** nếu giá trị phải là số không âm, helper cần từ chối số âm và giá trị thiếu; có thể dùng matcher phù hợp cùng test âm tính. Quy tắc tính giá chi tiết hơn có thể được unit test riêng.

### Bài tập D — Stub và mã thực thi

Consumer test qua Stub Runner mong stub gọi **expectedProcessedAt()** để lấy thời gian mỗi lần request, nhưng stub luôn trả một timestamp cố định.

**Yêu cầu:** giải thích hành vi đó, và mô tả cách kiểm tra consumer thích hợp.

**Gợi ý:** hàm test-side được dùng trong ngữ cảnh generated test đã được hỗ trợ, không mặc nhiên chạy trong stub. Dùng response mẫu có định dạng phù hợp, kiểm tra logic consumer; muốn mô phỏng nhiều response cần thiết kế stub/scenario riêng.

### Bài tập E — Kết luận tương thích

Generated producer tests PASS với regex của orderId, consumer CI PASS nhưng dùng stub phiên bản cũ. Có đủ bằng chứng để tuyên bố producer mới tương thích không?

**Gợi ý:** chưa. Cần gắn cùng revision hợp đồng, bản producer đã kiểm tra, artifact stub mới và consumer test sử dụng chính artifact đó. Kết luận chỉ bao phủ các kịch bản được kiểm chứng.

## 14. Checklist khi dùng giá trị thực thi bằng mã

- [ ] Đã phân biệt consumer/client và producer/server theo request hoặc response.
- [ ] Giá trị mẫu phía consumer giúp stub/generate test thực thi được, không chứa dữ liệu production.
- [ ] Matcher khai báo được ưu tiên nếu đủ mô tả điều kiện cần kiểm tra.
- [ ] Chỉ dùng execute/byCommand ở ngữ cảnh mà DSL/generator đang sử dụng hỗ trợ.
- [ ] Đã xem generated test để xác nhận method, tham số, kiểu trả về và thời điểm chạy.
- [ ] Base test class được cấu hình đúng và mọi method được tham chiếu thực sự tồn tại.
- [ ] Assertion/helper thất bại khi nhận dữ liệu sai, không luôn trả true.
- [ ] Giá trị expected và logic kiểm chứng độc lập với implementation producer trong phạm vi cần thiết.
- [ ] Không có I/O production, random, đồng hồ thực hoặc secret ngoài kiểm soát trong helper.
- [ ] Đã xác minh contract/stub được sinh từ cùng revision đã review.
- [ ] Producer tests chạy và PASS với bản build chuẩn bị phát hành.
- [ ] Consumer tests dùng đúng stub version qua Stub Runner và kiểm tra logic consumer.
- [ ] Kết luận tương thích giới hạn trong các cặp phiên bản và kịch bản thực sự được kiểm tra.

**Ghi nhớ:** Giá trị hai phía của Spring Cloud Contract cho phép **stub dùng ví dụ cụ thể** trong khi **generated producer test kiểm tra dữ liệu thật bằng kỳ vọng thích hợp**. execute(...) và byCommand(...) mở rộng khả năng xác minh nhưng bị giới hạn bởi ngữ cảnh sinh test, chữ ký method, tính tái lập và chất lượng assertion. Chúng không đưa mã producer vào stub; hợp đồng chỉ đáng tin khi cả producer test và consumer test xác minh đúng cam kết đã thống nhất.

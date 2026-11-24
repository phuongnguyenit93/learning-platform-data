# Giới hạn của mã tùy ý trong hợp đồng

## Mục tiêu bài học

**Spring Cloud Contract** cho phép producer và consumer thống nhất hành vi HTTP hoặc thông điệp bằng **Groovy DSL** hay **YAML DSL**. Từ hợp đồng đó, công cụ có thể sinh kiểm thử phía **producer** và stub để phía **consumer** chạy thử qua **Stub Runner**; CI dùng các kết quả này để phát hiện thay đổi API không tương thích.

Một đặc điểm cần hiểu rõ: tệp hợp đồng Groovy thường là **script Groovy được đánh giá khi công cụ xử lý hợp đồng**. Bởi vậy, về mặt ngôn ngữ, tác giả có thể viết biến, hàm, điều kiện hoặc gọi API Java/Groovy bên ngoài những cấu trúc DSL. Nhưng khả năng *viết được mã* không có nghĩa mã đó *nên nằm trong hợp đồng*.

Sau bài học, bạn có thể:

- Phân biệt **mã mô tả hành vi tích hợp** với **logic triển khai hoặc kiểm thử**.
- Giải thích vì sao mã tùy ý trong Groovy contract có thể khiến build khó tái lập, khó review hoặc có rủi ro bảo mật.
- Chọn đúng chỗ cho dữ liệu mẫu, matcher, biểu thức động trong DSL và phương thức ở base test class.
- Viết lại một contract phụ thuộc thời gian, biến môi trường hoặc trạng thái máy thành đặc tả ổn định.
- Đưa kiểm tra tính đầy đủ của producer tests, stub và consumer tests vào CI.

## 1. “Groovy DSL” là đặc tả bằng Groovy, không phải nơi chứa mọi logic

Một hợp đồng HTTP đơn giản:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description "Lấy trạng thái đơn hàng đã thanh toán"

    request {
        method GET()
        url "/api/orders/ORD-1001"
        headers {
            header "Accept", "application/json"
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            id: "ORD-1001",
            status: "PAID"
        )
    }
}
~~~

Hợp đồng trên diễn đạt một **cam kết quan sát được**: khi consumer gọi GET /api/orders/ORD-1001, producer trả HTTP 200 và JSON chứa id, status với giá trị đã thống nhất. Nó không mô tả producer dùng controller, database, repository hay thuật toán nào.

Về mặt kỹ thuật, đoạn này là script Groovy có lời gọi **Contract.make**. Khi plugin nạp nó để tạo mô hình hợp đồng, các biểu thức Groovy cần thiết sẽ được đánh giá. Điều này khác với việc chỉ đọc một tệp cấu hình thuần dữ liệu.

**Nguyên tắc:** dùng sức mạnh của Groovy để biểu diễn **điều consumer có quyền kỳ vọng**; không biến hợp đồng thành chương trình điều khiển build, chạy nghiệp vụ hoặc truy cập hệ thống bên ngoài.

## 2. “Giới hạn của mã tùy ý” có hai tầng

| Tầng | Bản chất | Điều cần làm |
| --- | --- | --- |
| **Khả năng kỹ thuật của Groovy/JVM** | Groovy có thể diễn đạt nhiều câu lệnh ngoài DSL; việc chạy được chúng phụ thuộc môi trường và classpath của plugin | Không mặc định xem tệp .groovy là dữ liệu trơ hoặc được sandbox hoàn toàn |
| **Giới hạn thiết kế của contract** | Đặc tả chỉ nên nêu hành vi và dữ liệu cần kiểm chứng giữa producer và consumer | Tránh logic không cần thiết, I/O, dữ liệu không ổn định và phụ thuộc triển khai |

Vì thế, khẳng định “Spring Cloud Contract không cho phép mã tùy ý” là **quá đơn giản và dễ gây hiểu sai**. Một file Groovy có thể chứa những thao tác mà người viết contract không cần dùng đến. Giới hạn quan trọng ở đây là **quy ước thiết kế và kiểm soát thực thi**, ngoài các ràng buộc cụ thể của API DSL.

### Ba thời điểm thực thi cần phân biệt

~~~mermaid
flowchart TD
    A["Tệp hợp đồng .groovy"] --> B["Plugin nạp/đánh giá script<br/>để xây mô hình contract"]
    B --> C["Sinh producer tests"]
    B --> D["Sinh stub/mapping"]
    C --> E["Chạy test trên producer"]
    D --> F["Đóng gói/phát hành stub"]
    F --> G["Consumer test qua Stub Runner"]
~~~

Có ba loại hành động **khác nhau**:

1. **Mã chạy khi nạp contract:** chẳng hạn biểu thức nối chuỗi, đọc biến môi trường hoặc gọi hàm bên ngoài khối DSL. Tác động của mã này phát sinh ngay trong giai đoạn xử lý hợp đồng.
2. **Logic test producer:** fixture, khởi tạo HTTP client hay phương thức trong base test class chạy khi generated test được thực thi.
3. **Hành vi stub:** stub nhận request và phát response theo mapping đã tạo. Việc consumer gọi stub không đồng nghĩa stub sẽ chạy lại toàn bộ script Groovy gốc.

Một số khả năng đặc biệt của Spring Cloud Contract có thể tạo ra lời gọi phương thức **ở generated test**. Cần biết chính xác phía thực thi và thời điểm của từng cơ chế DSL. Không được coi mọi đoạn Groovy hoặc mọi biểu thức động là cùng một loại thao tác.

## 3. Phản ví dụ: dùng biến môi trường để quyết định hợp đồng

~~~groovy
// Phản ví dụ: KHÔNG nên dùng để định nghĩa một API cố định.
import org.springframework.cloud.contract.spec.Contract

def orderId = System.getenv("CONTRACT_ORDER_ID") ?: "ORD-1001"
def expectedStatus = System.getenv("CONTRACT_STATUS") ?: "PAID"

Contract.make {
    request {
        method GET()
        url("/api/orders/" + orderId)
    }
    response {
        status OK()
        body(
            id: orderId,
            status: expectedStatus
        )
    }
}
~~~

Script này có thể tạo ra **hai hợp đồng khác nhau từ một commit** nếu môi trường của producer CI và consumer CI có các biến khác nhau:

- Người review thấy giá trị PAID trong Git nhưng pipeline dùng một trạng thái khác.
- Producer và consumer có thể sinh test/stub không cùng URL hoặc body.
- Việc chạy lại một build không còn bảo đảm cho ra cùng hợp đồng nếu biến môi trường thay đổi.
- PASS trong CI không chứng minh producer giữ ổn định một hành vi công khai cụ thể.

Nếu mục tiêu là mô tả trường hợp một đơn hàng xác định đã được thanh toán, hãy viết rõ:

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
        body(id: "ORD-1001", status: "PAID")
    }
}
~~~

Nếu producer hỗ trợ nhiều trạng thái nghiệp vụ, hãy định nghĩa **những kịch bản có chủ đích** hoặc dùng cơ chế matcher phù hợp. Không dùng biến của máy build để âm thầm quyết định trường hợp consumer sẽ nhận được.

## 4. Các loại mã cần hạn chế và cách thay thế

| Loại mã trong Groovy contract | Rủi ro | Cách diễn đạt tốt hơn |
| --- | --- | --- |
| Đọc biến môi trường để thay response/path | Hợp đồng phụ thuộc máy chạy | Cố định lời hứa công khai hoặc tách kịch bản rõ ràng |
| Đọc tệp cục bộ để lấy expected body | Phụ thuộc file ngoài nguồn hợp đồng | Đặt fixture có phiên bản, sử dụng dữ liệu khai báo và test setup có kiểm soát |
| Gọi HTTP/database khi nạp DSL | Build cần mạng/hạ tầng; có thể phát sinh tác dụng phụ | Chuẩn bị fixture trong base test class hoặc integration test setup |
| Dùng ngày hiện tại, UUID/random cho giá trị expected | Test/stub không tái lập được | Dùng dữ liệu mẫu cố định hoặc matcher theo định dạng |
| Gọi service/repository producer để tính expected response | Expected có thể lặp lại đúng lỗi implementation | Viết kỳ vọng độc lập từ yêu cầu consumer |
| Tự tạo nhiều contract bằng loop/if phức tạp | Khó review các trường hợp được kiểm chứng | Tách kịch bản có tên, nhóm hợp đồng rõ ràng |
| Gọi process, đọc secret hoặc ghi file khi nạp | Rủi ro bảo mật build | Chỉ chạy nguồn contract được review, hạn chế quyền CI |

Không phải **mọi biến Groovy** đều là lỗi. Một hằng rõ ràng và không có tác dụng phụ có thể giúp tránh viết sai cùng một giá trị:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

def orderId = "ORD-1001"

Contract.make {
    request {
        method GET()
        url("/api/orders/" + orderId)
    }
    response {
        status OK()
        body(id: orderId, status: "PAID")
    }
}
~~~

Hằng trên hiển thị đầy đủ khi review và tạo cùng kết quả khi xử lý lại. Tuy nhiên, nếu contract chỉ vài dòng, viết trực tiếp thường giúp người đọc hiểu hợp đồng nhanh hơn.

## 5. Dữ liệu động: ưu tiên matcher thay vì sinh giá trị ngẫu nhiên

Một ví dụ sai mục tiêu:

~~~groovy
// Phản ví dụ: giá trị thay đổi khi Groovy được xử lý.
def createdAt = java.time.Instant.now().toString()
def orderId = java.util.UUID.randomUUID().toString()
~~~

Nếu consumer chỉ cần một timestamp hợp lệ, việc khóa cứng *thời điểm build* vào expected response khiến test dễ thất bại khi producer trả một thời điểm hợp lệ khác. Cùng một revision hợp đồng cũng có thể sinh nhiều stub với nội dung khác nhau.

Hãy phân biệt:

- **Dữ liệu xác định:** ví dụ ORD-1001 và 2026-01-01T10:00:00Z, dùng khi đang kiểm tra một kịch bản cố định có fixture tương ứng.
- **Quy tắc định dạng:** id phải theo cấu trúc, timestamp phải theo ISO-8601, một trường số phải trong phạm vi hợp lệ. Sử dụng các **matcher** được DSL hỗ trợ.
- **Ngữ nghĩa nghiệp vụ:** ví dụ status PAID nghĩa là đã thanh toán; regex bất kỳ không thay thế được quy tắc nghiệp vụ này.

Spring Cloud Contract hỗ trợ matcher, regex và các giá trị khác nhau cho phía consumer/producer trong một số kịch bản. Cú pháp, phạm vi áp dụng và helper cụ thể cần kiểm chứng theo phiên bản đang dùng; một matcher quá rộng có thể khiến test PASS dù producer trả giá trị consumer không xử lý được.

**Không tạo giá trị random trong Groovy để “được nhiều độ phủ hơn”**: tính đa dạng dữ liệu nên được thiết kế trong test thích hợp, với seed hoặc fixture có thể tái lập. Hợp đồng phải diễn đạt điều kiện mà hai bên đã thỏa thuận.

## 6. Đưa setup vào base test class, giữ contract là lời cam kết

Generated test phía producer cần một ứng dụng hoặc HTTP context có thể gọi được và dữ liệu phù hợp. Việc chuẩn bị này thường thuộc **base test class** hoặc hạ tầng test, không thuộc script Groovy lúc nạp.

Hợp đồng:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description "Truy vấn đơn hàng đã thanh toán"
    request {
        method GET()
        url "/api/orders/ORD-1001"
    }
    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(id: "ORD-1001", status: "PAID")
    }
}
~~~

Một **phác thảo** base test class cho thấy trách nhiệm dữ liệu (chưa phải bài test Spring Boot hoàn chỉnh):

~~~java
abstract class OrderContractTestBase {

    @BeforeEach
    void prepareFixture() {
        // Đảm bảo ORD-1001 có trạng thái PAID
        // trong database/mock của môi trường kiểm thử.
    }
}
~~~

Base class thực tế còn phải cấu hình test context và client (ví dụ Rest Assured Mock MVC, MockMvc hay cách tích hợp tương ứng). Điểm chính là fixture có vòng đời rõ ràng và độc lập với dữ liệu production. Contract nói **producer cần trả gì**; setup test quyết định **làm sao tạo trạng thái để kiểm chứng điều đó**.

### Một ngoại lệ có kiểm soát: phương thức được tham chiếu bởi DSL

Với message contract, generated test có thể cần gọi một phương thức để kích hoạt event:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label "order_paid_event"
    input {
        triggeredBy("triggerOrderPaid()")
    }
    outputMessage {
        sentTo("order-events")
        body(eventType: "ORDER_PAID", orderId: "ORD-1001")
        headers {
            contentType(applicationJson())
        }
    }
}
~~~

Phương thức **triggerOrderPaid()** cần được định nghĩa trong ngữ cảnh kiểm thử producer, được gọi theo cơ chế generated test và phải kích hoạt hành vi cần xác minh. Dòng **triggeredBy(...)** là cấu trúc DSL, **không có nghĩa Stub Runner sẽ thực thi chuỗi đó khi consumer nhận message**.

Tương tự, một số biểu thức DSL như **execute(...)** phục vụ giá trị động hoặc gọi phương thức trong generated test, tùy ngữ cảnh. Khi dùng, phải hiểu chính xác **bên nào thực thi**, phương thức ở đâu và dữ liệu có ổn định không. Đây không phải giấy phép đưa logic nghiệp vụ hoặc I/O tùy ý vào hợp đồng.

## 7. Expected value phải độc lập với code cần kiểm chứng

Giả sử producer tính tổng tiền đơn hàng. Một hợp đồng gọi **chính service đang được kiểm thử** để tự tạo kỳ vọng là thiết kế yếu:

~~~groovy
// Mã giả phản ví dụ: tính kỳ vọng bằng implementation thực.
def expectedTotal = orderPricingService.calculateTotal("ORD-1001")
~~~

Nếu implementation tính sai, expectedTotal có thể nhận đúng kết quả sai đó, và test PASS dù consumer nhận giá trị không như cam kết. Một hợp đồng đủ ý nghĩa phải có **kỳ vọng độc lập**:

1. Hai bên thống nhất dữ liệu đầu vào và quy tắc công khai.
2. Hợp đồng mô tả số tiền, đơn vị tiền tệ và cấu trúc response consumer phụ thuộc.
3. Fixture tạo dữ liệu kiểm thử có kiểm soát.
4. Generated test gọi producer và đối chiếu với expected response đã xác định.

Những phép tính nghiệp vụ phức tạp nên có unit test hoặc integration test chuyên biệt. Hợp đồng tập trung vào tính tương thích của **giao diện producer–consumer**.

## 8. Mã Groovy có thể mở rộng bề mặt rủi ro bảo mật

Vì contract .groovy có thể được đánh giá bởi quá trình build, không được coi Groovy nhận từ một nguồn bất kỳ là **dữ liệu vô hại để nạp**. Tùy quyền tiến trình, classpath và cách plugin đánh giá mã, script có thể tiếp cận API JVM hoặc thông tin mà CI có quyền đọc.

Những rủi ro cần quản lý:

- Mã trong hợp đồng truy cập hoặc làm lộ biến môi trường, thông tin cấu hình, secret của build.
- Mã đọc/ghi file hoặc gọi hệ thống ngoài khi sinh test/stub.
- Một helper/import che giấu hành vi gây tác dụng phụ, khiến review diff chỉ nhìn thấy vài dòng.
- Build phụ thuộc một host đang hoạt động, thời điểm hiện tại hoặc thứ tự chạy.

Không nên giả định Maven, Gradle hoặc Spring Cloud Contract **tự sandbox toàn bộ mã Groovy**. Dùng nguồn contract đáng tin, review thay đổi như mã có thể thực thi, giới hạn quyền và secret của CI, khóa phiên bản công cụ/dependency phù hợp chính sách dự án.

**YAML DSL** thường dễ review hơn ở các hợp đồng chủ yếu là cấu trúc dữ liệu và giảm nhu cầu viết mã trực tiếp. Tuy nhiên, việc dùng YAML không tự làm toàn bộ pipeline an toàn: plugin, custom converter, test fixture và dependency vẫn là mã được thực thi.

## 9. Chọn Groovy DSL hay YAML DSL

Cùng cam kết HTTP ở trên có thể được khai báo bằng YAML:

~~~yaml
description: "Lấy trạng thái đơn hàng đã thanh toán"
name: get_paid_order
request:
  method: GET
  url: /api/orders/ORD-1001
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: ORD-1001
    status: PAID
~~~

| Tiêu chí | Groovy DSL | YAML DSL |
| --- | --- | --- |
| Hình thức | Script Groovy dùng API Contract | Dữ liệu khai báo theo cấu trúc |
| Khả năng biểu đạt | Linh hoạt; dùng được nhiều helper và biểu thức Groovy | Dễ đọc, đủ cho nhiều kịch bản HTTP/message |
| Rủi ro logic ẩn | Cao hơn khi lạm dụng import, vòng lặp, hàm và I/O | Thường ít mã tùy ý trực tiếp hơn |
| Review diff | Cần hiểu biểu thức được thực thi | Thường dễ nhìn thấy trường được thay đổi |
| Trường hợp phù hợp | Tính năng Groovy DSL thực sự hữu ích và nhóm kiểm soát được tính tái lập | Cam kết chủ yếu là cấu trúc cố định dễ diễn đạt |

Không chọn Groovy chỉ để chạy vòng lặp sinh test hoặc truy cập cơ sở dữ liệu. Nếu cần setup phức tạp, dùng **test setup**; nếu cần kiểm tra logic nghiệp vụ, dùng **unit/integration test**; nếu cần diễn đạt một quy tắc tích hợp, ưu tiên **matcher/DSL** hỗ trợ trực tiếp.

## 10. Bốn câu hỏi khi review Groovy contract

Với mỗi đoạn mã ngoài lời gọi DSL khai báo, reviewer nên hỏi:

1. **Đoạn này có thay đổi hành vi công khai không?** Nếu có, consumer cần hiểu tác động và thống nhất.
2. **Cùng revision và cùng đầu vào có sinh ra cùng hợp đồng không?** Nếu không, nguồn biến thiên có thực sự là một phần cam kết?
3. **Đoạn mã chạy ở thời điểm nào?** Lúc nạp DSL, lúc generated producer test chạy hay khi consumer gọi stub?
4. **Có thể dùng matcher hoặc chuyển sang fixture/base test class không?** Nếu có, hợp đồng thường dễ hiểu và dễ kiểm chứng hơn.

Một số ví dụ quyết định:

| Thay đổi | Đánh giá |
| --- | --- |
| Đổi HTTP 404 thành HTTP 200 cho đơn hàng không tồn tại | Thay đổi giao diện công khai, phải review khả năng tương thích |
| Đổi biến hằng orderId thành hằng có cùng giá trị | Thường giữ hành vi, nhưng vẫn nên kiểm tra generated output |
| Thêm System.getenv để chọn status | Không phù hợp với cam kết cần ổn định |
| Dùng matcher chuẩn cho định dạng ID | Có thể hợp lý khi chính định dạng là cam kết |
| Dùng triggeredBy để gọi phương thức kích hoạt message trong base class | Hợp lý nếu setup và hành vi producer được kiểm chứng đúng |
| Gọi cơ sở dữ liệu khi load contract để tự tạo expected body | Nên đưa sang fixture và khai báo kỳ vọng độc lập |

Ngoài ra, cần kiểm tra import/helper, phụ thuộc timezone/locale, random hoặc network; xác nhận script không âm thầm đổi URL, status hay schema giữa các môi trường.

## 11. CI cần kiểm chứng cả contract lẫn đầu ra được sinh

~~~mermaid
flowchart TD
    A["Review thay đổi Groovy/YAML"] --> B["Nạp contract trong môi trường build có quyền giới hạn"]
    B --> C["Sinh producer tests và stub"]
    C --> D{"Phát hiện đủ hợp đồng?"}
    D -->|Không| X["BLOCK / điều tra"]
    D -->|Có| E["Chạy producer contract tests"]
    E --> F{"PASS?"}
    F -->|Không| X
    F -->|Có| G["Đóng gói stub version cố định"]
    G --> H["Consumer test qua Stub Runner"]
    H --> I{"PASS với đúng revision?"}
    I -->|Không| X
    I -->|Có| J["Công bố bằng chứng trong phạm vi đã kiểm tra"]
~~~

Các bước quan trọng:

- **Review trước lúc nạp:** xem .groovy như mã có thể thực thi, nhất là khi lấy từ repository ngoài.
- **Tính tái lập:** cùng revision phải cho ra hợp đồng/test/stub tương đương trong điều kiện build được kiểm soát.
- **Độ đầy đủ:** kiểm tra hợp đồng được phát hiện và generated tests **thật sự được chạy**, tránh trường hợp file bị bỏ qua vì sai đường dẫn.
- **Truy vết artifact:** stub mới phải gắn với hợp đồng và producer build đã kiểm chứng.
- **Consumer tests:** dùng đúng phiên bản stub qua Stub Runner; một lần PASS với stub cũ không chứng minh producer mới tương thích.

Ví dụ hồ sơ kiểm tra **do dự án tự thiết kế**, không phải định dạng do Spring Cloud Contract tự sinh:

~~~yaml
contract_revision: "contracts@a1b2c3"
producer_revision: "order-service@d4e5f6"
discovered_contracts:
  - get_paid_order
  - get_missing_order
producer_generated_tests: PASS
stub_artifact: "com.example:order-service:2.4.0:stubs"
consumer_version: "checkout:1.9.0"
stub_runner_tests: PASS
~~~

Khi dùng thật, nên lưu thêm link báo cáo CI và checksum của artifact. Các giá trị minh họa trên **không phải kết quả kiểm thử đã chạy**.

## 12. Tình huống thực hành: contract “thông minh” nhưng thiếu ổn định

Nhóm Order API chuẩn bị phát hành producer 2.4.0. Một thành viên đề xuất:

~~~groovy
// Phản ví dụ: KHÔNG nên dùng.
import org.springframework.cloud.contract.spec.Contract

def state = System.getenv("ORDER_TEST_STATE") ?: "PAID"
def id = "ORD-" + (1000 + new Random().nextInt(9000))

Contract.make {
    request {
        method GET()
        url("/api/orders/" + id)
    }
    response {
        status OK()
        body(id: id, status: state)
    }
}
~~~

Producer CI A có thể sinh contract dùng ORD-1234 và PAID; ở nơi khác, hợp đồng được xử lý với ORD-8765 hoặc CANCELLED. Các bên không còn kiểm tra **cùng một kịch bản** dù cùng một commit.

Hướng sửa:

1. Chốt trường hợp nghiệp vụ, ví dụ GET đơn ORD-1001 trả PAID.
2. Viết hằng và phản hồi rõ trong contract; fixture kiểm thử chuẩn bị trạng thái tương ứng.
3. Nếu ID thực sự động, dùng matcher mô tả định dạng thay vì random ngay trong script.
4. Nếu cần kiểm tra CANCELLED, viết một kịch bản riêng với tên và expected response rõ ràng.
5. Sinh lại producer tests và stub, chạy test hai phía bằng artifact có version xác định.

Sau sửa, người đọc contract hiểu **lời hứa dành cho consumer** mà không phải dựng đủ môi trường CI để biết script sẽ tạo dữ liệu gì.

## 13. Bài tập tự luyện

### Bài 1 — Đặt mã đúng chỗ

Phân loại các thao tác sau:

| Thao tác | Vị trí khuyến nghị |
| --- | --- |
| Khai báo GET /api/orders/ORD-1001, trả 200 và status PAID | Groovy DSL |
| Tạo ORD-1001 trong database test | Base test class / fixture |
| Gọi production API để lấy ID lúc build | Loại bỏ khỏi quá trình xử lý hợp đồng |
| Dùng matcher DSL để ràng buộc định dạng ID | Groovy DSL |
| Kích hoạt event qua phương thức trong generated test | Hook DSL + phương thức base test class |
| Đọc biến môi trường để âm thầm thay tên trường status | Loại bỏ, thay bằng thay đổi giao diện được thỏa thuận |

### Bài 2 — Vì sao build xanh chưa đủ?

Một commit thêm contract có System.getenv để đổi expected status. Producer CI PASS và xuất bản stub. Consumer CI PASS nhưng dùng stub của tuần trước.

**Câu hỏi:** Vì sao chưa thể công bố producer mới tương thích? Bạn cần những bằng chứng nào?

**Gợi ý:** Hợp đồng không ổn định theo môi trường; consumer chưa chạy với stub từ build mới. Cần bỏ nguồn biến thiên không cần thiết, chạy lại producer tests, phát hành stub có nguồn gốc rõ và kiểm thử consumer với artifact đó.

### Bài 3 — Message contract có thực sự được kiểm chứng?

Một contract dùng triggeredBy("sendOrderPaid()") để phát sự kiện ORDER_PAID. Base class có phương thức này nhưng chỉ gọi mock publisher, không kiểm chứng luồng producer phát sự kiện theo ngữ cảnh thực.

**Câu hỏi:** Generated test hiện chứng minh điều gì và cần thay đổi setup nào?

**Gợi ý:** Xác định ranh giới thực sự được gọi và xác minh. Một mock đáp ứng đúng kỳ vọng chưa chắc chứng minh producer thật tạo ra thông điệp công khai. Cần setup để generated test kiểm tra hành vi producer trong phạm vi đã cam kết.

## 14. Checklist khi chấp nhận Groovy DSL

- [ ] Hợp đồng tập trung vào hành vi HTTP/message consumer quan sát được.
- [ ] Không có I/O, file, network, process hoặc secret ngoài setup được kiểm soát.
- [ ] Không dùng đồng hồ, random, UUID hay biến môi trường để đổi ngầm cam kết.
- [ ] Fixture nằm trong test setup; expected response độc lập với implementation đang được kiểm thử.
- [ ] Giá trị động dùng matcher/biểu thức DSL phù hợp với yêu cầu consumer.
- [ ] Mọi hook triggeredBy/execute được review về bên và thời điểm thực thi, với phương thức test rõ ràng.
- [ ] Tệp .groovy được review như mã có thể thực thi; quyền và nguồn hợp đồng trong CI được quản lý.
- [ ] Plugin phát hiện đủ contract và sinh generated tests tương ứng.
- [ ] Generated producer tests chạy PASS với đúng build dự kiến phát hành.
- [ ] Stub được đóng gói từ đúng tập hợp hợp đồng và producer build đã kiểm tra.
- [ ] Consumer kiểm thử với stub version cụ thể bằng Stub Runner.
- [ ] Tuyên bố tương thích chỉ bao phủ phiên bản và hành vi thực sự đã có bằng chứng.

**Ghi nhớ:** Groovy DSL cho phép diễn đạt hợp đồng linh hoạt, nhưng **hợp đồng tốt là cam kết rõ ràng, độc lập và có thể tái lập**, không phải một script càng “thông minh” càng tốt. Giữ đặc tả tập trung vào hành vi producer–consumer, chuyển setup sang vị trí test phù hợp và đối chiếu producer tests, stub, consumer tests trong CI theo đúng revision hợp đồng.

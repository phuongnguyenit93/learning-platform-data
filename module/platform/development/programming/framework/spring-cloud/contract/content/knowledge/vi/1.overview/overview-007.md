# Luồng kiểm chứng một thay đổi từ producer đến consumer

## 1. Vì sao cần kiểm chứng xuyên suốt?

Trong kiến trúc microservices, một thay đổi nhỏ ở dịch vụ cung cấp API có thể làm hỏng dịch vụ đang sử dụng API đó. Ví dụ, **Inventory Service** (producer) trả về thông tin tồn kho cho **Checkout Service** (consumer). Producer đổi tên trường JSON từ **available** sang **inStock** vì thấy tên mới dễ hiểu hơn. Endpoint vẫn trả HTTP 200, build của producer vẫn có thể xanh, nhưng consumer có thể đọc sai trạng thái tồn kho và từ chối một đơn hàng hợp lệ.

**Spring Cloud Contract (SCC)** giúp diễn đạt hành vi giao tiếp thành *contract* có thể thực thi: request nào cần được chấp nhận, response nào phải được trả về, hoặc message nào phải được phát ra. Từ contract, hệ thống có thể:

- **Sinh test cho producer** để kiểm tra implementation thực tế có làm đúng điều đã cam kết.
- **Sinh stub** để consumer kiểm tra cách tích hợp với một phiên bản hành vi dự kiến, không cần chạy producer thật.
- **Đưa cả hai loại kiểm tra vào CI** để ngăn thay đổi không tương thích trước khi phát hành.

Chủ đề này tập trung vào **đường đi của một thay đổi**: từ ý định sửa API, cập nhật hoặc giữ nguyên contract, kiểm chứng producer, tạo và phân phối stub, chạy test consumer, đến quyết định triển khai. Cùng một tư duy áp dụng được cho hợp đồng HTTP và hợp đồng trao đổi thông điệp.

### Kết quả học tập

Sau bài này, bạn có thể giải thích:

1. Producer và consumer kiểm chứng **những khẳng định khác nhau** ở hai phía của contract.
2. Một thay đổi gây lỗi sẽ bị phát hiện ở giai đoạn nào nếu chỉ sửa code, hoặc nếu sửa cả code lẫn contract.
3. Vì sao test producer xanh **chưa đủ** để kết luận consumer hiện tại vẫn tương thích.
4. Cách đưa contract, generated test, stub artifact, Stub Runner và các cổng kiểm tra CI vào cùng một quy trình.
5. Cách triển khai thay đổi API có rủi ro bằng chiến lược mở rộng trước, chuyển đổi sau, rồi mới loại bỏ hành vi cũ.

## 2. Thành phần tham gia

| Thành phần | Vai trò | Câu hỏi mà nó trả lời |
|---|---|---|
| **Producer** | Cung cấp HTTP endpoint hoặc phát thông điệp. | Implementation mới có tiếp tục đáp ứng cam kết không? |
| **Consumer** | Gọi endpoint hoặc xử lý thông điệp. | Client/handler của tôi có làm việc với hành vi dự kiến không? |
| **Contract (Groovy/YAML DSL)** | Mô tả request, response, header, body, trạng thái, hoặc input/output message. | Hai bên đang cùng hiểu hành vi nào? |
| **Generated producer test** | Test được SCC tạo từ contract và chạy với code producer thật. | Code producer có khớp contract không? |
| **Stub artifact** | Các stub được tạo từ contract, thường đóng gói thành JAR có classifier **stubs**. | Consumer có thể thử hành vi đã cam kết ở đâu? |
| **Stub Runner** | Tải stub, khởi chạy stub HTTP hoặc tích hợp cơ chế messaging phù hợp. | Test consumer có môi trường giả lập ổn định không? |
| **CI/CD** | Xây dựng, chạy test, phân phối stub ứng viên và tổng hợp kết quả. | Thay đổi đã vượt qua các cổng kiểm chứng để phát hành chưa? |

Contract không tự kiểm tra toàn bộ hệ thống. Nó chỉ bảo vệ **những hành vi đã được mô tả và thực sự được chạy test**. Stub là mô phỏng hành vi theo contract, không phải một instance của producer với đầy đủ database, nghiệp vụ và các phụ thuộc.

## 3. Bản đồ luồng kiểm chứng

~~~mermaid
flowchart TD
    A["Producer đề xuất thay đổi API/message"] --> B["Xác định consumer và hợp đồng bị ảnh hưởng"]
    B --> C["Giữ nguyên hoặc cập nhật contract"]
    C --> D["SCC sinh test cho producer"]
    D --> E{"Generated test + các test liên quan đạt?"}
    E -- "Không" --> F["Sửa implementation hoặc contract sai; chặn thay đổi"]
    E -- "Có" --> G["Đóng gói và cung cấp stub ứng viên"]
    G --> H["Consumer chạy test với Stub Runner dùng đúng phiên bản ứng viên"]
    H --> I{"Consumer test đạt?"}
    I -- "Không" --> J["Giữ tương thích, bổ sung giai đoạn chuyển đổi hoặc phối hợp consumer"]
    I -- "Có" --> K["Đánh giá thêm các kiểm tra cần thiết và cho phép phát hành"]
    F --> C
    J --> C
~~~

Có **hai lớp chứng cứ bổ sung cho nhau**:

- **Producer verification:** implementation hiện tại thỏa contract đang được kiểm thử. Nếu đổi code nhưng giữ contract cũ, generated test thường là nơi đầu tiên bắt được thay đổi phá vỡ hành vi đã cam kết.
- **Consumer verification:** code consumer thực tế có thể sử dụng stub được sinh từ contract của phiên bản producer đang xét. Nếu producer sửa **cả code lẫn contract** để phản ánh một giao diện mới, producer test có thể vẫn xanh; consumer test chạy với **stub mới** mới có cơ hội phát hiện client cũ không hiểu giao diện đó.

Điều kiện quan trọng là consumer phải được kiểm tra với **đúng artifact của phiên bản ứng viên**. Một bộ test xanh vì vẫn lấy stub cũ từ cache hoặc dùng phiên bản phát hành trước không chứng minh được thay đổi mới an toàn.

## 4. Ví dụ xuyên suốt: đổi tên trường phản hồi

Giả sử Checkout Service đang gọi:

~~~http
GET /api/inventory/SKU-123 HTTP/1.1
Accept: application/json
~~~

Producer phiên bản hiện hành trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sku": "SKU-123",
  "available": true,
  "quantity": 12
}
~~~

Checkout dựa vào **available = true** để cho phép khách đặt hàng. Nhóm Inventory muốn đổi thành:

~~~json
{
  "sku": "SKU-123",
  "inStock": true,
  "quantity": 12
}
~~~

Đây là thay đổi **có nguy cơ breaking** với những consumer đang đọc trường **available**. Việc response vẫn là JSON hợp lệ và status vẫn là 200 không đảm bảo tương thích. Với một DTO Java có trường primitive **boolean available**, dữ liệu không có trường tương ứng thậm chí có thể được giải mã thành **false**, khiến lỗi biểu hiện như một quyết định nghiệp vụ sai.

Trước khi sửa code, cần xác định consumer nào sử dụng trường này, các phiên bản consumer còn hoạt động, và hợp đồng nào đang kiểm tra nó. Từ đây có hai tình huống đặc biệt quan trọng.

## 5. Bước A — Định nghĩa contract của hành vi hiện tại

Trong dự án producer đã tích hợp Spring Cloud Contract, một contract HTTP thường nằm dưới thư mục **src/test/resources/contracts/**. Ví dụ tệp **inventory/shouldReturnInventory.groovy**:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Trả tồn kho cho Checkout Service'

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

Contract này biểu đạt: khi nhận request GET đến đường dẫn cụ thể, producer phải trả 200, nội dung JSON có các trường và giá trị mà bài kiểm chứng quan tâm. Nó là một ví dụ hành vi xác định; sản phẩm thực tế thường cần thêm contract hoặc matcher cho các tình huống khác như SKU không tồn tại, hết hàng, truy cập không hợp lệ hoặc dữ liệu động.

Nếu dự án chọn **YAML DSL**, có thể diễn đạt cùng hành vi bằng một tệp contract YAML:

~~~yaml
description: Trả tồn kho cho Checkout Service
request:
  method: GET
  url: /api/inventory/SKU-123
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    available: true
    quantity: 12
~~~

**Chọn một định dạng cho mỗi contract cụ thể**, tránh duy trì hai bản Groovy/YAML tương đương mà không có chủ đích. Cú pháp matcher và cấu hình plugin có thể khác nhau theo DSL/phiên bản SCC; hãy đồng bộ với phiên bản Spring Cloud Contract mà dự án đang dùng.

Những chi tiết cần được chốt rõ khi viết contract:

- **Đường dẫn, method, query, header và request body** nào consumer thực sự gửi.
- **Status, header và response body** nào consumer phụ thuộc.
- Giá trị nào là **ví dụ cố định**, giá trị nào cần matcher hoặc điều kiện động.
- Trường nào bắt buộc, trường nào tùy chọn; ý nghĩa nghiệp vụ của dữ liệu, không chỉ kiểu JSON.
- Trường hợp lỗi hoặc trường hợp biên nào có thể làm thay đổi hành vi consumer.

## 6. Bước B — Sinh và chạy test phía producer

Với **spring-cloud-contract-maven-plugin** hoặc plugin Gradle tương ứng đã được cấu hình, SCC đọc contract và sinh test kiểm tra producer. Tùy cấu hình, test có thể dùng MockMvc, WebTestClient hoặc HTTP thực; dự án cần cấu hình lớp cơ sở/context cho test sinh ra để gọi đúng ứng dụng và chuẩn bị dữ liệu kiểm thử.

Ví dụ quy trình Maven trên máy phát triển:

~~~bash
# Chạy trong dự án producer đã cấu hình Spring Cloud Contract.
./mvnw clean verify

# Khi producer test đạt, đưa artifact và stubs vào Maven local
# để thử luồng consumer ở máy phát triển.
./mvnw install
~~~

Lệnh và vị trí tệp sinh ra phụ thuộc vào cấu hình build. Với Maven, có thể kiểm tra generated test trong vùng **target/generated-test-sources/contracts/** và artifact stub có classifier **stubs** trong kết quả đóng gói. Trong CI, bước cài đặt local được thay bằng việc cung cấp stub ứng viên qua kho artifact hoặc workspace của pipeline.

Giả sử lập trình viên đổi controller để chỉ trả **inStock** nhưng **giữ nguyên contract** yêu cầu **available**. Khi test do SCC sinh chạy với producer thật, kỳ vọng về response không còn được đáp ứng và pipeline producer phải báo lỗi. Đây là điểm chặn sớm: thay đổi code đã phá vỡ một cam kết hiện hành.

Một cách khác là lập trình viên đổi **cả controller lẫn contract** sang **inStock**. Lúc này producer test có thể đạt, vì code khớp hợp đồng **mới**. Kết quả ấy không trả lời câu hỏi: “Checkout đang chạy phiên bản cũ có còn đọc được response hay không?”. Cần đi tiếp đến bước consumer.

> **Phân biệt:** Generated producer test kiểm tra **producer so với contract hiện tại**; nó không tự so sánh contract mới với mọi hợp đồng cũ hoặc mọi consumer đang triển khai.

## 7. Bước C — Đóng gói và phân phối stub ứng viên

Từ hợp đồng HTTP, SCC tạo các stub tương ứng (thường dựa trên WireMock). Artifact thường được xuất bản trong hệ sinh thái Maven dưới dạng một JAR với classifier **stubs**. Một tọa độ minh họa:

~~~text
groupId     = com.example
artifactId  = inventory-service
version     = 1.3.0-rc1
classifier  = stubs
~~~

Đây là **stub của producer ứng viên** 1.3.0-rc1, không phải stub của bản production đã phát hành. Luồng phổ biến:

1. CI của producer chạy generated contract tests và các test liên quan.
2. Nếu thành công, CI đóng gói stub từ **chính commit đang kiểm tra**.
3. Stub ứng viên được cài vào kho local trong cùng job, chia sẻ qua artifact pipeline, hoặc phát hành lên kho thử nghiệm có quyền truy cập thích hợp.
4. Job kiểm chứng consumer lấy **đúng version/commit** đó rồi chạy test.
5. Chỉ khi các cổng kiểm tra cần thiết đạt mới cho phép promote hoặc phát hành producer.

Cần phân biệt **công bố artifact để kiểm tra** với **phát hành phiên bản ổn định cho người dùng**. Stub ứng viên có thể được đưa vào kho thử nghiệm để các nhóm kiểm tra trước, không có nghĩa producer đã được triển khai ra production.

Khi đánh giá một thay đổi cụ thể, nên **ghim version ứng viên** thay vì dùng ký hiệu chọn phiên bản mới nhất như dấu **+** mà không kiểm soát. Nếu Stub Runner vô tình tải artifact cũ, test có thể xanh giả.

## 8. Bước D — Consumer kiểm thử với Stub Runner

Consumer không cần khởi động Inventory Service thật để kiểm tra HTTP client. **Spring Cloud Contract Stub Runner** có thể tải stub artifact và dựng một HTTP server giả để trả response theo contract.

Ví dụ test phía Checkout, giả sử consumer đã có **InventoryClient** dùng Spring **RestClient**, cùng DTO Java:

~~~java
// Mã minh họa phía consumer: lớp này được dùng trong production.
public record InventoryStock(String sku, boolean available, int quantity) {
}
~~~

~~~java
import org.springframework.web.client.RestClient;

public class InventoryClient {
    private final RestClient http;

    public InventoryClient(RestClient http) {
        this.http = http;
    }

    public InventoryStock findBySku(String sku) {
        return http.get()
                .uri("/api/inventory/{sku}", sku)
                .retrieve()
                .body(InventoryStock.class);
    }
}
~~~

Test tích hợp của consumer dùng **chính InventoryClient** đó:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;
import org.springframework.web.client.RestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureStubRunner(
        ids = "com.example:inventory-service:1.3.0-rc1:stubs:8081",
        stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class InventoryClientContractTest {

    @Test
    void checkoutCanReadAvailabilityFromCandidateStub() {
        InventoryClient client =
                new InventoryClient(RestClient.create("http://localhost:8081"));

        InventoryStock stock = client.findBySku("SKU-123");

        assertThat(stock).isNotNull();
        assertThat(stock.sku()).isEqualTo("SKU-123");
        assertThat(stock.available()).isTrue();
    }
}
~~~

**Giải thích cấu hình:**

- Chuỗi **com.example:inventory-service:1.3.0-rc1:stubs:8081** xác định group, artifact, version, classifier và cổng stub HTTP.
- **LOCAL** yêu cầu artifact đã có trong Maven local; cần chạy bước cài đặt producer stubs phù hợp trước khi chạy test. CI chạy tách môi trường thường dùng **REMOTE** và cấu hình kho artifact để lấy stub ứng viên.
- Cổng **8081** được cố định để ví dụ dễ theo dõi. Trong suite lớn, có thể để Stub Runner cấp phát cổng và tra URL qua **StubFinder** để tránh xung đột.
- Test sử dụng lớp HTTP client thật của consumer. Nếu chỉ gửi request thủ công đến stub và so sánh JSON, ta mới xác nhận stub chạy được, chưa chắc kiểm tra đúng logic giải mã và sử dụng của consumer.
- Ví dụ dựa trên Spring Framework có **RestClient**; ở phiên bản cũ hơn, consumer có thể dùng RestTemplate, WebClient hoặc client đang được ứng dụng sử dụng. Cần chọn phiên bản Spring Boot/Spring Cloud Contract tương thích và khai báo dependency Stub Runner cho test.

Với stub **mới** chỉ chứa **inStock**, consumer cũ vẫn tìm **available**. Test sẽ thất bại vì DTO không nhận được giá trị như kỳ vọng. Nếu test vẫn xanh, hãy kiểm tra trước tiên xem nó có thật sự tải stub **1.3.0-rc1** không, và dữ liệu trong stub có phản ánh hợp đồng mới không.

**Giới hạn:** Stub Runner kiểm tra tương thích giữa consumer và **những response/request được stub mô tả**. Nó không thay thế test tích hợp với producer chạy thật, database, authentication, timeout, hiệu năng hoặc những tình huống hợp đồng chưa mô tả.

## 9. Cùng một thay đổi có thể tạo những kết quả nào?

| Thay đổi ở producer | Generated producer test | Test consumer với stub ứng viên | Nhận định |
|---|---|---|---|
| Chỉ sửa code, đổi **available** thành **inStock**; contract giữ nguyên | **Đỏ** vì response không còn khớp contract | Chưa cần chạy để phát hiện sai lệch này | Chặn thay đổi, sửa code hoặc xem xét kế hoạch đổi contract |
| Sửa cả code và contract để chỉ trả **inStock** | Có thể **xanh** | **Đỏ** nếu consumer vẫn yêu cầu **available** và test bao phủ hành vi đó | Thay đổi phá tương thích với consumer hiện tại |
| Giữ **available**, bổ sung thêm **inStock** trong giai đoạn chuyển đổi | Phải thỏa mọi contract được duy trì | Consumer cũ và consumer mới có thể cùng **xanh** | Hướng tiến hóa an toàn hơn, vẫn phải kiểm tra giả định về trường bổ sung |
| Chuyển consumer sang đọc **inStock**, sau đó xóa **available** quá sớm | Có thể **xanh** với contract mới | Consumer đã nâng cấp xanh; phiên bản cũ chưa nâng cấp có thể đỏ | Chỉ loại bỏ trường cũ khi biết chắc các consumer còn hoạt động đã sẵn sàng |

Trường hợp **bổ sung field** thường tương thích với client JSON bỏ qua field lạ, nhưng không phải luôn luôn: một consumer cấu hình giải mã nghiêm ngặt hoặc kiểm tra cấu trúc tuyệt đối vẫn có thể lỗi. Quyết định an toàn phải dựa trên cách consumer thực sự đọc dữ liệu và các phiên bản đang chạy.

## 10. Cách thay đổi an toàn: mở rộng → chuyển đổi → thu hẹp

Để đổi **available** thành **inStock** mà không gây gián đoạn, có thể triển khai theo ba pha:

**Pha 1 — Mở rộng:** Producer trả cả hai field với ngữ nghĩa nhất quán. Duy trì contract kiểm tra field **available** và bổ sung kiểm tra field mới **inStock**. Chạy producer test và consumer test với stub của phiên bản mở rộng.

~~~json
{
  "sku": "SKU-123",
  "available": true,
  "inStock": true,
  "quantity": 12
}
~~~

**Pha 2 — Chuyển đổi:** Consumer cập nhật client để đọc **inStock**, triển khai theo thứ tự phù hợp. Trong giai đoạn này vẫn kiểm thử các consumer chưa nâng cấp và consumer đã nâng cấp với stub tương ứng; sử dụng telemetry hoặc thông tin phiên bản triển khai để xác định ai còn phụ thuộc field cũ.

**Pha 3 — Thu hẹp:** Chỉ khi không còn consumer được hỗ trợ phụ thuộc **available**, producer mới loại bỏ field cũ và cập nhật contract. Việc gỡ bỏ có thể cần phiên bản API mới hoặc chính sách deprecation rõ ràng tùy cam kết của hệ thống.

Cách này áp dụng tương tự cho đổi tên endpoint, thay kiểu dữ liệu, thay mã lỗi, thêm yêu cầu bắt buộc vào request hoặc đổi tên field của message. Với trường bắt buộc ở **request**, producer cần hỗ trợ cả client cũ chưa gửi field mới trong giai đoạn chuyển đổi.

## 11. Đưa vào CI/CD: các cổng kiểm tra thực sự cần thiết

Một pipeline thực tế thường có ít nhất ba giai đoạn logic:

| Giai đoạn | Đầu vào | Điều kiện đạt | Hành động khi lỗi |
|---|---|---|---|
| **Producer verification** | Code producer + contract của commit ứng viên | Generated contract tests cùng test liên quan đạt | Chặn merge/phát hành producer; trả lỗi về PR |
| **Candidate stub handoff** | Contract đã được producer xác nhận | Stub artifact được đóng gói, gắn đúng version/commit và consumer lấy được | Chặn bước consumer; sửa đóng gói/kho artifact, không coi là kiểm tra đạt |
| **Consumer compatibility gate** | Consumer được hỗ trợ + chính stub ứng viên | Các test gọi client/handler thực và assert hành vi phụ thuộc đều đạt | Chặn rollout, thương lượng contract hoặc áp dụng chuyển đổi từng bước |

Minh họa thứ tự các job độc lập với hệ thống CI cụ thể:

~~~text
PR/commit của producer
  └─ build + generated contract tests + producer tests
       └─ đóng gói stub ứng viên (group:artifact:version:stubs)
            └─ cung cấp artifact cho consumer CI
                 └─ chạy consumer contract/integration tests với version ứng viên
                      ├─ FAIL → đánh dấu thay đổi chưa tương thích
                      └─ PASS → tiếp tục các cổng cần thiết và quy trình phát hành
~~~

Ba lưu ý khi vận hành:

1. **Liên kết phiên bản/commit:** Lưu artifact coordinate và commit SHA trong log của hai pipeline; consumer job cần nhận đúng stub mới tạo. Tránh sử dụng version động không kiểm soát hoặc cache cũ.
2. **Định nghĩa tập consumer phải kiểm tra:** Nếu có nhiều consumer, một consumer test xanh không đại diện cho tất cả. Có thể chạy ma trận các consumer/version còn được hỗ trợ, hoặc một pipeline tương thích tập trung.
3. **Quyền quyết định release:** Lỗi contract không nhất thiết đồng nghĩa producer phải vĩnh viễn giữ API cũ; nó cho biết cần triển khai migration/versioning hoặc phối hợp kế hoạch release. Chính sách CI cần quy định rõ khi nào được phép chấp nhận thay đổi breaking.

Nếu test consumer chỉ chạy **sau khi producer đã lên production**, cơ chế này chủ yếu phát hiện sự cố muộn. Giá trị lớn nhất đến từ việc kiểm tra artifact ứng viên **trước** quyết định triển khai.

## 12. Khi giao tiếp qua message thì luồng thay đổi thế nào?

Với event hoặc message, producer không trả HTTP response trực tiếp. Contract có thể mô tả điều kiện kích hoạt và **outputMessage**, bao gồm destination, header, payload; ở phía consumer có thể mô tả thông điệp đầu vào cần xử lý.

Ví dụ Inventory Service phát sự kiện:

~~~json
{
  "eventType": "InventoryChanged",
  "sku": "SKU-123",
  "available": true
}
~~~

Nếu producer đổi **available** thành **inStock**, chuỗi kiểm chứng vẫn gồm hai phía:

- **Producer:** Generated test kiểm tra ứng dụng thật đã phát thông điệp đúng payload/header/destination theo contract, với môi trường messaging/test base được cấu hình.
- **Consumer:** Test kích hoạt hoặc nhận thông điệp từ stub/messaging support phù hợp, đưa nó qua **handler thật** của consumer, rồi xác minh kết quả xử lý.

Khác HTTP, bài test messaging cần chú ý broker/test binder, destination/topic, key, header, serialization, schema, thứ tự xử lý và cơ chế retry. Không nên xem stub JSON tự sinh là bằng chứng mọi cơ chế broker đã hoạt động đúng. SCC hỗ trợ hợp đồng message, nhưng cách kích hoạt và tích hợp phụ thuộc stack messaging mà dự án sử dụng.

Với message phát cho nhiều consumer độc lập, việc giữ field cũ đủ lâu thường đặc biệt quan trọng vì producer không điều khiển được thời điểm tất cả consumer nâng cấp.

## 13. Những lỗi triển khai thường gặp và cách chẩn đoán

| Triệu chứng | Khả năng cần kiểm tra | Cách xử lý |
|---|---|---|
| Producer test xanh dù code rõ ràng đổi response | Contract đã bị đổi theo code; matcher quá rộng; contract không bao phủ field quan trọng | Xem generated test và kỳ vọng contract; thêm trường hợp phản ánh nhu cầu consumer |
| Không tìm thấy test sinh ra | Plugin chưa được cấu hình/bind vào vòng đời build, contract đặt sai thư mục, cấu hình test base sai | Kiểm tra log sinh test, source set, cấu hình plugin và test runner |
| Consumer test xanh với stub cũ | Tọa độ/version sai, dấu **+** chọn nhầm, artifact cache chưa cập nhật | Ghim version/commit, ghi log stub đã tải, kiểm tra nội dung artifact |
| Stub Runner không tải được stub | JAR **stubs** chưa được đóng gói/cài đặt/công bố hoặc mode LOCAL/REMOTE không khớp | Kiểm tra artifact coordinates, local repository, remote repository và quyền truy cập |
| Consumer test chỉ so sánh body JSON và vẫn xanh | Chưa dùng client/handler thực, chưa assert dữ liệu downstream phụ thuộc | Chạy code consumer thực tế và assert ý nghĩa nghiệp vụ |
| Test trên máy cá nhân xanh, CI đỏ | Khác phiên bản Spring/Java, cổng cố định xung đột, test data hoặc artifact khác nhau | Đồng bộ dependency, cô lập port, cố định artifact và môi trường test |
| Hai phía đều xanh nhưng production vẫn lỗi | Contract không mô tả trường hợp phát sinh, cấu hình mạng/bảo mật/broker hoặc dữ liệu thật khác | Bổ sung contract cho hành vi thiếu và duy trì integration/E2E/observability thích hợp |

Khi lỗi xuất hiện, đọc theo thứ tự: **contract nào đang được sử dụng → generated producer test nào chạy → stub nào được xuất bản → Stub Runner thực sự tải phiên bản nào → consumer code/test nào được thực thi**. Chuỗi này cho phép phân biệt lỗi hành vi, lỗi cấu hình build và lỗi phát hành artifact.

## 14. Bài thực hành: theo dấu một breaking change

Chuẩn bị hai ứng dụng mẫu: **inventory-service** (producer) cung cấp endpoint GET tồn kho và **checkout-service** (consumer) có client đọc trạng thái tồn kho. Cấu hình plugin SCC ở producer và Stub Runner trong test consumer.

**Vòng 1 — Chốt hợp đồng gốc**

1. Viết contract GET cho SKU-123 với **available: true**.
2. Chạy build để sinh test producer; xác nhận test xanh và tạo stub.
3. Cho consumer dùng stub của phiên bản gốc; assert rằng client đọc được **available = true**.

**Vòng 2 — Phát hiện sai lệch code**

1. Chỉ đổi implementation producer để trả **inStock**.
2. Giữ nguyên contract và chạy lại generated producer test.
3. Quan sát test đỏ, đối chiếu field kỳ vọng với body thực tế.

**Vòng 3 — Phát hiện sai lệch giữa hai dịch vụ**

1. Cập nhật contract để chỉ trả **inStock**, đồng bộ code producer.
2. Chạy producer tests đến khi xanh, đóng gói stub với **version ứng viên mới**.
3. Chạy test của consumer cũ với **stub ứng viên**, không dùng lại stub v1.
4. Quan sát assertion ở consumer thất bại, dù producer test đạt.

**Vòng 4 — Chuyển đổi tương thích**

1. Sửa producer trả đồng thời **available** và **inStock**.
2. Kiểm chứng hợp đồng còn phục vụ consumer cũ và hợp đồng dành cho consumer mới.
3. Nâng cấp consumer đọc **inStock**, kiểm tra cả phiên bản cũ và phiên bản mới trong khoảng hỗ trợ.
4. Chỉ đề xuất xóa **available** khi các consumer được hỗ trợ không còn phụ thuộc nó.

**Bằng chứng cần thu thập:** test report producer; tên/đường dẫn generated test; version và checksum/commit của JAR **stubs**; log Stub Runner xác nhận stub ứng viên; kết quả test consumer trước/sau khi sửa. Từ bằng chứng này, bạn cần chỉ ra chính xác thay đổi bị chặn ở bước nào và vì sao.

## 15. Checklist trước khi hợp nhất một thay đổi hợp đồng

- [ ] Xác định endpoint/topic, consumer đang sử dụng và mức độ tương thích mong muốn.
- [ ] Contract phản ánh yêu cầu thật của consumer, bao gồm field, status, header và trường hợp lỗi quan trọng.
- [ ] Generated producer tests chạy trên **code ứng viên** và đạt.
- [ ] Stub được đóng gói từ **cùng contract/commit**, có version định danh rõ ràng.
- [ ] Stub Runner tải **đúng artifact ứng viên**; không dùng nhầm bản cũ.
- [ ] Test consumer chạy **client hoặc handler thật** và kiểm tra kết quả nghiệp vụ.
- [ ] Các consumer/phiên bản cần hỗ trợ đã được kiểm tra hoặc có kế hoạch migration rõ ràng.
- [ ] CI chặn phát hành khi cổng tương thích thất bại; có log truy vết contract, commit và stub.
- [ ] Những rủi ro ngoài phạm vi contract (dữ liệu thật, auth, network, broker, timeout) có kiểm tra phù hợp.

## 16. Câu hỏi tự kiểm tra

**1. Vì sao producer test vẫn xanh sau khi đổi tên một field mà consumer đang dùng?**

Vì producer có thể đã cập nhật contract cùng lúc với implementation. Test producer chứng minh code khớp **contract mới**; nó không kiểm tra trực tiếp client cũ. Consumer test phải chạy với stub ứng viên và assert hành vi phụ thuộc field đó.

**2. Vì sao consumer test với stub phiên bản trước không đủ để xác nhận PR mới?**

Vì phiên bản stub trước không chứa hành vi thay đổi. Bài test có thể xanh chỉ vì producer giả lập vẫn trả dữ liệu cũ. CI phải trỏ tới artifact được tạo từ commit ứng viên.

**3. Có thể bỏ integration test vì đã có Spring Cloud Contract không?**

Không. Contract test hữu ích cho hành vi giao tiếp đã được mô tả; hệ thống thật còn có persistence, security, network, broker, cấu hình, lỗi thời gian chạy và những tình huống không có contract.

**4. Khi nào có thể xóa field cũ khỏi response?**

Khi chính sách versioning/deprecation cho phép và đã xác nhận các consumer được hỗ trợ không còn phụ thuộc field đó, thường sau một giai đoạn trả cả field cũ lẫn field mới.

---

**Điểm cần nhớ:** Dòng bằng chứng đầy đủ là **thay đổi producer → contract → generated producer test → stub ứng viên → Stub Runner → test consumer → cổng quyết định trong CI**. Mỗi chặng trả lời một câu hỏi khác nhau; kiểm chứng đáng tin cậy chỉ có được khi artifact và phiên bản được nối liền xuyên suốt chuỗi này.

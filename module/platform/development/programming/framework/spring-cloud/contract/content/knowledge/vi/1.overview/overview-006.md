# Hợp đồng, kiểm thử được sinh và stub có quan hệ thế nào?

Trong kiến trúc có nhiều dịch vụ, một bên **producer** (bên cung cấp) triển khai API hoặc phát thông điệp, còn **consumer** (bên sử dụng) phụ thuộc vào hành vi đó. Nếu producer thay đổi đường dẫn, mã trạng thái, cấu trúc JSON hay nội dung sự kiện mà consumer không biết, hệ thống có thể lỗi dù từng dịch vụ vẫn vượt qua unit test của riêng mình.

**Spring Cloud Contract** giải quyết vấn đề này bằng cách dùng một định nghĩa hợp đồng làm đầu vào cho hai hoạt động bổ trợ nhau:

1. **Sinh kiểm thử phía producer** để đối chiếu hợp đồng với hành vi thực của ứng dụng cung cấp.
2. **Sinh stub** để consumer kiểm thử tương tác với một phiên bản mô phỏng hành vi producer, thường được khởi động bằng **Stub Runner**.

Hai đầu ra cùng xuất phát từ hợp đồng, nhưng chạy ở hai phía khác nhau và trả lời những câu hỏi khác nhau. Hiểu mối quan hệ này là nền tảng trước khi học Groovy/YAML DSL, Contract Verifier, WireMock, Stub Runner và tích hợp CI.

## 1. Ba khái niệm, ba trách nhiệm

| Thành phần | Bản chất | Ai dùng và mục đích | Điều **không** được bảo đảm riêng bởi thành phần đó |
| --- | --- | --- | --- |
| **Hợp đồng (contract)** | Đặc tả một tương tác được kỳ vọng: yêu cầu/phản hồi HTTP hoặc đầu vào/đầu ra thông điệp; viết bằng Groovy hay YAML DSL. | Producer và consumer thống nhất hành vi có ý nghĩa với consumer. | Chỉ có file hợp đồng không chứng minh chương trình hiện tại thực hiện đúng. |
| **Kiểm thử được sinh (generated producer test)** | Mã kiểm thử do Spring Cloud Contract Verifier tạo từ hợp đồng. | Chạy với triển khai producer để phát hiện hành vi không khớp. | Không kiểm tra mọi hành vi nằm ngoài những tình huống đã mô tả trong hợp đồng. |
| **Stub** | Bản mô phỏng phản hồi HTTP hoặc hành vi thông điệp được tạo từ hợp đồng. Với HTTP, thường là các ánh xạ WireMock. | Consumer chạy test mà không cần triển khai producer thực đang hoạt động. | Stub không phải chính ứng dụng producer và không tự chứng minh producer đã triển khai đúng. |

**Stub Runner** không phải là hợp đồng thứ tư: nó là công cụ **tìm, tải và chạy các stub** đã được đóng gói để bài kiểm thử consumer có thể gọi vào. Kiểm thử phía consumer thường do đội consumer viết; Spring Cloud Contract không tự tạo toàn bộ bài kiểm thử nghiệp vụ của consumer chỉ từ hợp đồng.

## 2. Một hợp đồng tạo ra hai nhánh kiểm tra

~~~mermaid
flowchart TD
    C["Hợp đồng Groovy / YAML"] --> T["Sinh kiểm thử phía producer"]
    C --> S["Sinh stub từ cùng hợp đồng"]
    T --> P["Chạy test với triển khai producer"]
    P --> G{"Producer test đạt?"}
    G -->|Không| F["CI báo lỗi, sửa mã hoặc xem lại hợp đồng"]
    G -->|Có| A["Cho phép phát hành artifact stubs"]
    S --> A
    A --> R["Stub Runner tải và khởi động stub"]
    R --> U["Consumer chạy test qua HTTP / messaging"]
~~~

Luồng trên thể hiện **quy trình CI nên thiết lập**: chỉ phát hành phiên bản stub được tin cậy khi kiểm thử producer đối với hợp đồng tương ứng đã đạt. Công cụ có thể tạo ra file stub trong quá trình build ngay cả khi chưa kiểm tra xong; **việc chỉ phát hành sau khi test đạt là trách nhiệm cấu hình pipeline**.

Có thể đọc sơ đồ theo ba câu hỏi:

- **Đã thống nhất điều gì?** → Đọc hợp đồng.
- **Producer có thực hiện đúng điều đã thống nhất không?** → Chạy kiểm thử được sinh trên producer.
- **Consumer có xử lý đúng hành vi đó không?** → Chạy bài kiểm thử consumer với stub do Stub Runner cung cấp.

Đây là hai phép kiểm tra bổ sung cho nhau, không phải hai bản sao của cùng một bài test.

## 3. Ví dụ xuyên suốt: đọc trạng thái đơn hàng

Giả sử ứng dụng **Order Service** là producer, còn ứng dụng **Billing Service** là consumer. Billing cần gọi:

~~~http
GET /api/orders/42
~~~

Hành vi hai nhóm thống nhất là:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"status":"PAID"}
~~~

Một hợp đồng HTTP tối giản bằng **Groovy DSL** có thể nằm trong thư mục hợp đồng của producer, chẳng hạn tại đường dẫn `src/test/resources/contracts/orders/get_paid_order.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Trả về đơn hàng 42 đã thanh toán'

    request {
        method 'GET'
        url '/api/orders/42'
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            id: 42,
            status: 'PAID'
        )
    }
}
~~~

Đặc tả này nói rằng khi nhận **GET /api/orders/42**, producer phải trả về **200**, nội dung JSON chứa **id = 42** và **status = PAID**. Nó không tự định nghĩa toàn bộ API đơn hàng, trường hợp ID không tồn tại hoặc trạng thái khác. Các trường hợp quan trọng ấy cần hợp đồng riêng hoặc các biến thể điều kiện phù hợp.

Spring Cloud Contract cũng hỗ trợ viết hợp đồng theo **YAML DSL**. Lựa chọn Groovy hay YAML ảnh hưởng cách biên soạn và biểu đạt quy tắc, không thay đổi ý nghĩa cốt lõi: từ đặc tả, công cụ tạo dữ liệu để kiểm tra producer và mô phỏng cho consumer. Trong dự án thực tế, cú pháp và khả năng của từng DSL cần khớp với phiên bản Spring Cloud Contract đang dùng.

### 3.1. Nhánh A — kiểm thử được sinh bảo vệ producer

Khi tích hợp plugin Spring Cloud Contract vào build của producer, Contract Verifier đọc file hợp đồng và sinh test trong giai đoạn phù hợp của Maven/Gradle. Đối với ví dụ trên, kiểm thử được sinh có ý nghĩa gần như đoạn **minh họa** sau (mã chính xác phụ thuộc chế độ kiểm thử, cấu hình base test và phiên bản):

~~~java
// Minh họa các xác nhận mà test được sinh sẽ thực hiện.
given()
    .get("/api/orders/42")
.then()
    .statusCode(200)
    .contentType("application/json")
    .body("id", equalTo(42))
    .body("status", equalTo("PAID"));
~~~

Test này phải thực thi **trên producer thật ở cấp giao diện được cấu hình để kiểm thử**, ví dụ HTTP server, MockMvc hoặc WebTestClient. Nhóm producer cần cấu hình lớp cơ sở kiểm thử, ngữ cảnh Spring và dữ liệu cần thiết để endpoint có thể tạo ra phản hồi đã mô tả. Không nên chỉnh sửa trực tiếp file test đã sinh, vì lần generate tiếp theo có thể ghi đè nó.

Nếu mã producer đổi trường `status` thành `state` trong khi hợp đồng vẫn yêu cầu `status`, bước kiểm thử phải báo lỗi. Tương tự, thay mã `200` bằng `204`, đổi đường dẫn hoặc bỏ trường bắt buộc sẽ làm các kiểm thử tương ứng thất bại nếu chúng còn nằm trong tập hợp hợp đồng đang được kiểm tra.

**Điểm mấu chốt:** test được sinh so sánh hợp đồng với **triển khai thực** của producer. Nó không thử HTTP call của consumer và không sử dụng stub để giả làm producer trong chính phép xác minh này.

### 3.2. Nhánh B — stub giúp consumer kiểm thử độc lập

Từ cùng hợp đồng, quá trình build có thể tạo một ánh xạ **WireMock** cho HTTP. Cách hiểu đơn giản của ánh xạ đó như sau:

~~~json
{
  "request": {
    "method": "GET",
    "url": "/api/orders/42"
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "id": 42,
      "status": "PAID"
    }
  }
}
~~~

Đây là **minh họa về ý nghĩa stub**, không cam kết file JSON được công cụ sinh ra sẽ giống hệt về tên thuộc tính, định dạng hay cấu trúc. Khi có yêu cầu trùng phương thức và đường dẫn, WireMock trả về phản hồi tương ứng. Consumer có thể thử mã gọi HTTP, ánh xạ dữ liệu, cách xử lý trạng thái và luồng nghiệp vụ của mình mà không cần khởi chạy Order Service.

Thông thường producer đóng gói các ánh xạ và tài nguyên stub vào artifact có classifier **stubs** (ví dụ tọa độ Maven `com.example:order-service:1.2.3:stubs`), sau đó cài vào kho local hoặc xuất bản lên kho artifact dùng chung. **Artifact stub phải đi kèm phiên bản producer/hợp đồng đã xác minh**, để các đội truy nguyên đúng tập kỳ vọng.

Trong test của Billing Service, **Spring Cloud Contract Stub Runner** có thể lấy artifact đó và chạy một HTTP stub server ở cổng chỉ định:

~~~java
// Phần cấu hình minh họa trong test của consumer.
@SpringBootTest(properties = "order.api.base-url=http://localhost:8089")
@AutoConfigureStubRunner(
    ids = "com.example:order-service:1.2.3:stubs:8089",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class BillingOrderClientTest {
    @Autowired
    OrderClient orderClient;

    @Test
    void docDuocTrangThaiDonHangDaThanhToan() {
        OrderDto order = orderClient.getOrder(42L);

        assertThat(order.getStatus()).isEqualTo("PAID");
    }
}
~~~

Ví dụ giả định consumer đã có `OrderClient`, `OrderDto`, thư viện kiểm thử và thuộc tính `order.api.base-url` để trỏ client về stub. **LOCAL** yêu cầu artifact stubs đã hiện diện trong kho Maven local; trên CI nhiều nhóm chuyển sang lấy artifact từ kho từ xa với cấu hình Stub Runner thích hợp. Tên artifact, phiên bản và cổng phải khớp môi trường đang kiểm thử.

**Ai viết test consumer?** Nhóm Billing viết hoặc duy trì test khẳng định client/luồng nghiệp vụ của họ hiểu phản hồi đúng cách. Stub Runner chỉ cung cấp dịch vụ mô phỏng khớp hợp đồng; nó không biết mọi yêu cầu nghiệp vụ của Billing để tự sinh các assert tương ứng.

## 4. Tại sao cần cả test producer và stub?

Xét ba trường hợp sau:

| Tình huống | Test producer từ hợp đồng | Test consumer qua stub | Ý nghĩa |
| --- | --- | --- | --- |
| Producer vô tình đổi `status` thành `state`, hợp đồng cũ vẫn còn. | **Thất bại** vì phản hồi thực không còn khớp. | Có thể **vẫn đạt** với stub cũ có `status`. | Cổng CI phía producer phát hiện việc phá hợp đồng; chỉ nhìn test consumer là chưa đủ. |
| Consumer viết sai parser, ví dụ đọc `paymentStatus` thay vì `status`. | Có thể **đạt** vì producer thực hiện đúng. | **Thất bại** khi nhận stub có `status`. | Stub phát hiện lỗi tích hợp trong mã consumer. |
| Cả hai bên đồng ý cập nhật hợp đồng và triển khai cùng thay đổi. | Đạt với hợp đồng mới nếu producer thực hiện đúng. | Đạt với stub mới nếu consumer xử lý đúng. | Hai phía khớp phiên bản mới, nhưng vẫn phải xét consumer cũ đang chạy. |

Một stub sinh ra từ hợp đồng **không tự trở thành bằng chứng** producer đang tuân thủ hợp đồng. Nếu producer chưa chạy hoặc chưa đạt test được sinh, stub chỉ phản ánh điều **được khai báo**, có thể khác thực tế. Ngược lại, producer đạt test không có nghĩa mọi consumer đều sử dụng kết quả đúng cách.

Quan hệ giữa các thành phần có thể ghi nhớ bằng chuỗi:

> **Hợp đồng là cam kết → test được sinh xác minh lời cam kết ở producer → stub tái hiện cam kết cho consumer → test consumer xác minh cách sử dụng cam kết.**

## 5. Hợp đồng thay đổi thì điều gì xảy ra?

Giả sử Billing đang đọc trường `status`. Producer muốn đổi thành `state`. Có hai khả năng dễ nhầm:

**Trường hợp 1 — producer đổi mã nhưng giữ hợp đồng hiện hành:** generated producer test phát hiện sai lệch và chặn bản build nếu pipeline yêu cầu test xanh trước khi phát hành.

**Trường hợp 2 — producer đồng thời sửa hoặc xóa hợp đồng cũ để chỉ còn trường mới:** test sinh từ hợp đồng mới có thể vẫn đạt. **Điều đó chưa chứng minh tương thích ngược** với bản Billing đang dùng trường cũ. Để phát hiện breaking change, cần lưu và kiểm tra các hợp đồng còn hiệu lực đối với những consumer được hỗ trợ, cùng chính sách phiên bản, thời gian chuyển đổi hoặc cách duy trì API cũ.

Điều này dẫn đến ba nguyên tắc khi thay đổi API:

1. **Review tác động với consumer trước khi đổi hợp đồng**: phương thức, path, HTTP status, headers, trường bắt buộc, kiểu dữ liệu, format và hành vi lỗi.
2. **Duy trì các hợp đồng còn được consumer sử dụng**: thay đổi có thể hợp lệ với consumer mới nhưng phá consumer cũ. Các kiểm thử chỉ bảo vệ những điều còn được mô tả và thực thi.
3. **Phát hành artifact theo phiên bản kiểm soát được**: test consumer nên chọn phiên bản stub tương ứng với producer mà hệ thống sẽ tích hợp. Trong CI cần tính đến việc artifact thay đổi và khả năng truy nguyên, tránh phụ thuộc vô điều kiện vào “mới nhất”.

Thêm một trường JSON tùy chọn thường ít gây ảnh hưởng hơn xóa hoặc đổi tên trường bắt buộc, nhưng **tính tương thích luôn phụ thuộc hợp đồng và cách consumer thực sự phân tích phản hồi**. Consumer dùng parser nghiêm ngặt có thể vẫn lỗi khi producer thêm trường.

## 6. Vị trí của từng phần trong CI/CD

Một quy trình hợp lý có thể tổ chức như sau:

1. **Đề xuất hoặc cập nhật hợp đồng**: producer và consumer thống nhất tương tác. Hợp đồng được lưu cùng mã producer hoặc trong kho hợp đồng riêng có quy trình đồng bộ rõ ràng.
2. **Sinh và chạy test producer**: plugin Contract Verifier tạo test; build thực thi chúng với ứng dụng producer và dữ liệu chuẩn bị trước. Nếu lỗi, sửa implementation hoặc thương lượng lại đặc tả.
3. **Tạo và phát hành stubs**: sau khi đạt cổng kiểm thử, xuất bản artifact stubs có phiên bản xác định vào kho artifact.
4. **Chạy test consumer**: Stub Runner lấy artifact, khởi tạo stub, rồi các test HTTP client/luồng nghiệp vụ consumer gọi tới địa chỉ stub.
5. **Quản lý thay đổi và phát hành**: CI đánh dấu thất bại khi kiểm thử liên quan không đạt; nhóm phụ trách quyết định giữ tương thích, bổ sung phiên bản API hay phối hợp nâng cấp consumer.

| Vị trí trong pipeline | Đầu vào chính | Kết quả cần quan sát |
| --- | --- | --- |
| Build producer | File contract + mã producer + cấu hình test | Generated producer tests **PASS/FAIL** |
| Publish stubs | Contract + kết quả build đã đạt | Artifact `stubs` theo đúng version |
| Build consumer | Mã consumer + artifact stubs + test consumer | Consumer tests với Stub Runner **PASS/FAIL** |
| Kiểm tra tích hợp sâu hơn | Các dịch vụ thật, dữ liệu và hạ tầng thực | Kiểm tra những vấn đề mà contract test/stub không bao phủ |

Lưu ý: kiểm thử qua stub giúp phát hiện sớm lệch kỳ vọng API và giảm nhu cầu dùng môi trường dịch vụ chung. Nó **không thay thế** hoàn toàn integration test hay end-to-end test cho xác thực, mạng, cấu hình triển khai, dữ liệu thật hoặc những hành vi chưa được mô tả.

## 7. Hợp đồng thông điệp có cùng ý tưởng không?

**Có, ở cấp nguyên lý.** Ngoài HTTP request/response, Spring Cloud Contract còn có thể đặc tả đầu vào kích hoạt và **thông điệp đầu ra** của producer (đích gửi, header, payload, v.v.). Khi đó:

- **Generated producer test** kiểm tra hành vi phát thông điệp thực tế của producer theo hợp đồng và cấu hình kiểm thử messaging.
- **Stub cho messaging** hỗ trợ consumer kiểm thử luồng nhận/xử lý thông điệp thông qua cơ chế và tích hợp message broker/test binding được hỗ trợ.
- **Stub Runner** và phần tích hợp messaging giúp đưa các định nghĩa stub vào môi trường test, nhưng không thể xem thông điệp như một phản hồi HTTP WireMock thông thường.

Ví dụ: khi lệnh tạo đơn hoàn tất, producer phải phát sự kiện `OrderCreated` với `orderId` và `eventType`. Hợp đồng mô tả kỳ vọng này; test producer kiểm tra việc phát; consumer dùng mô phỏng thông điệp để xác minh xử lý sự kiện. Việc kiểm chứng đúng broker, transaction và hành vi vận hành thực tế vẫn cần các bài kiểm thử phù hợp khác.

## 8. Những ngộ nhận thường gặp

**“Có hợp đồng là API chắc chắn tương thích.”** Không. Hợp đồng chỉ là mô tả; phải chạy generated tests với producer và duy trì các hợp đồng còn hiệu lực. API cũng có thể phá tương thích ở tình huống chưa được hợp đồng bao phủ.

**“Stub là một producer thu nhỏ, nên test consumer xanh nghĩa là triển khai thật chắc chắn xanh.”** Không. Stub chỉ trả lời theo những tương tác được cấu hình. Một stub có thể chạy tốt dù producer thực đã lệch hợp đồng, đặc biệt khi kiểm thử producer bị bỏ qua hoặc stub đã cũ.

**“Spring Cloud Contract sinh cả test nghiệp vụ của consumer.”** Thông thường không. Công cụ sinh kiểm thử xác minh producer và stub; consumer vẫn phải tự khẳng định cách client/ứng dụng của mình xử lý các phản hồi hoặc thông điệp nhận được.

**“Một hợp đồng cho HTTP 200 là đã bao phủ API.”** Chưa đủ nếu consumer phụ thuộc cả các trường hợp 400, 404, 409, 500, timeout, giá trị biến đổi hoặc luồng messaging. Hợp đồng nên thể hiện các hành vi có giá trị và rủi ro tương thích cao, kết hợp với các lớp kiểm thử khác.

**“Cứ sửa hợp đồng theo mã mới là giải quyết được lỗi build.”** Đây có thể là hành động phá API đối với consumer cũ. Cần xác định ai còn phụ thuộc vào hợp đồng và chiến lược chuyển đổi trước khi chấp nhận thay đổi.

## 9. Bài thực hành ngắn để tự kiểm tra quan hệ

Với ví dụ Order Service và Billing Service, có thể thực hành theo chuỗi sau trên một dự án đã cấu hình Spring Cloud Contract:

1. Viết hợp đồng GET đơn hàng với phản hồi JSON có `id` và `status`; sinh test và stub bằng plugin build.
2. Cài đặt endpoint đúng hợp đồng; chạy test producer và xác nhận đạt.
3. Phát hành artifact stubs từ bản đã đạt test; trong Billing, cấu hình Stub Runner và viết test xác nhận lấy được trạng thái `PAID`.
4. Chỉ đổi mã producer từ `status` sang `state`, **giữ nguyên hợp đồng**, sau đó chạy lại generated producer test: kỳ vọng **FAIL**.
5. Hoàn nguyên producer, nhưng sửa code consumer để đọc trường `state`: kỳ vọng test consumer với stub cũ **FAIL**.
6. Thảo luận cách đổi hợp đồng cho phiên bản mới mà vẫn bảo vệ consumer cũ, sau đó đưa cả hai bộ test vào CI.

Kết quả mong đợi không chỉ là hai test xanh. Quan trọng hơn, bạn phải chỉ ra được **test nào thất bại khi bên nào sai**, stub được tạo từ đâu, vì sao cần xác minh producer trước khi xuất bản stub và vì sao xóa hợp đồng cũ có thể làm mất khả năng phát hiện breaking change.

## 10. Tự kiểm tra kiến thức

- Khi generated producer test thất bại nhưng test consumer với stub vẫn đạt, khả năng nào cần kiểm tra trước? Gợi ý: so sánh triển khai thật, hợp đồng đang dùng và phiên bản stub.
- Nếu consumer nhận phản hồi đúng mẫu nhưng xử lý sai, lớp kiểm thử nào nên phát hiện? Gợi ý: các assert trong bài kiểm thử của consumer.
- Stub Runner có trách nhiệm chứng minh producer thực đã chạy đúng không? Vì sao?
- Nếu cả producer test và consumer test với hợp đồng mới đều đạt, cần làm gì trước khi khẳng định bản nâng cấp tương thích với các consumer cũ?

**Kết nối ý tưởng:** Hợp đồng mô tả hành vi mong đợi, kiểm thử được sinh đối chiếu hành vi đó với producer, còn stub tái hiện hành vi đó cho consumer kiểm thử độc lập. Sức mạnh của Spring Cloud Contract đến từ việc giữ **cùng một nguồn đặc tả**, chạy **đúng test ở từng phía** và kiểm soát **phiên bản hợp đồng** trong quy trình tích hợp liên tục.

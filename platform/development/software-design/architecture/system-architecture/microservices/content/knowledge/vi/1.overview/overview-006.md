# Phân biệt vi dịch vụ với việc chỉ chia nhỏ ứng dụng hoặc tạo nhiều API

> **Ý chính:** Microservices là cách chia hệ thống theo **năng lực nghiệp vụ và quyền tự chủ của từng dịch vụ**. Việc có nhiều package, nhiều ứng dụng chạy riêng, nhiều container hoặc nhiều REST API chỉ là những dấu hiệu kỹ thuật; riêng chúng chưa chứng minh hệ thống đã có kiến trúc microservices.

## 1. Sau bài học, cần phân biệt được điều gì?

Người học cần nhận diện ba trường hợp dễ bị gọi nhầm là “microservices”: một ứng dụng nguyên khối được tổ chức thành nhiều module; một ứng dụng có nhiều API; và nhiều tiến trình được tách ra nhưng vẫn phụ thuộc chặt chẽ vào dữ liệu, phát hành và vận hành của nhau. Từ đó, có thể giải thích vì sao một ranh giới microservice có ý nghĩa nghiệp vụ, được triển khai tương đối độc lập và có hợp đồng giao tiếp rõ ràng.

Câu hỏi trung tâm không phải “Hệ thống có bao nhiêu service hoặc endpoint?”, mà là: **Khi một năng lực nghiệp vụ thay đổi, nhóm phụ trách có thể sửa, kiểm thử, triển khai và vận hành phần đó mà không buộc các phần không liên quan phải thay đổi theo hay không?**

## 2. Ba cách chia cần phân biệt

| Cách tổ chức | Đơn vị chia | Điều thường thấy | Kết luận |
| --- | --- | --- | --- |
| **Modular monolith** | Package/module theo chức năng trong cùng ứng dụng | Một artifact và một tiến trình triển khai; các module có giao diện nội bộ rõ | Là kiến trúc module hóa tốt, **không tự động là microservices** |
| **Ứng dụng có nhiều API** | Endpoint, controller, route hoặc tài nguyên HTTP | /users, /orders, /payments cùng chạy trong một backend | API chỉ mô tả **cách truy cập**, không quyết định ranh giới triển khai |
| **Microservices** | Dịch vụ sở hữu một năng lực nghiệp vụ tương đối trọn vẹn | Hợp đồng giao tiếp, quyền sở hữu logic/dữ liệu, vòng đời build/deploy và vận hành tách biệt ở mức phù hợp | Là một lựa chọn kiến trúc phân tán, có lợi ích và chi phí rõ ràng |

Một **module** là ranh giới tổ chức code. Một **API** là giao diện giao tiếp. Một **service** trong kiến trúc microservices là ranh giới sở hữu và vận hành một năng lực nghiệp vụ. Các khái niệm có thể kết hợp nhưng không đồng nghĩa.

Ví dụ, một ứng dụng Spring Boot chứa UserController, OrderController và PaymentController với hàng chục endpoint vẫn là một ứng dụng nếu tất cả được build thành cùng JAR, dùng chung cơ sở dữ liệu và triển khai cùng phiên bản.

## 3. Thế nào là một ranh giới microservice có ý nghĩa?

### 3.1. Tách theo năng lực nghiệp vụ, không theo số lớp kỹ thuật

Hãy xét hệ thống bán hàng:

- **Catalog Service** quản lý danh mục, thông tin và giá niêm yết của sản phẩm.
- **Order Service** quản lý vòng đời đơn hàng và trạng thái đặt hàng.
- **Inventory Service** quản lý tồn kho và các lần giữ/nhả hàng.
- **Payment Service** quản lý giao dịch thanh toán và trạng thái thanh toán.

Các tên gọi trên là **ứng viên ranh giới**, không phải công thức bắt buộc. Ranh giới tốt phụ thuộc ngôn ngữ nghiệp vụ, quy tắc thay đổi, quy mô nhóm và luồng dữ liệu thực tế. Chia thành CustomerControllerService, CustomerRepositoryService, CustomerValidationService chỉ vì mỗi lớp có thể chạy trong một process thường tạo ra các lời gọi mạng liên tiếp mà không tạo ra tự chủ nghiệp vụ.

**Dấu hiệu tốt:** một service có thể mô tả nhiệm vụ của mình bằng câu “chịu trách nhiệm về ...”, biết dữ liệu nào mình sở hữu và có trách nhiệm rõ khi nghiệp vụ thất bại.

### 3.2. Tự chủ triển khai ở mức thực tế

Một microservice thường có artifact và quy trình phát hành riêng. Sửa quy tắc tính phí giao hàng chỉ cần phát hành dịch vụ liên quan, miễn là hợp đồng với các bên sử dụng không bị phá vỡ.

“Tự chủ” không có nghĩa service chạy mà không phụ thuộc bất kỳ dịch vụ nào. Một hệ thống phân tán vẫn có phụ thuộc khi hoạt động. Điểm quyết định là **giảm sự bắt buộc phối hợp khi thay đổi**, duy trì tương thích hợp đồng và giới hạn phạm vi lỗi. Nếu mỗi lần sửa Inventory đều phải build, kiểm thử và triển khai lại Order, Payment, Catalog cùng một lúc, ranh giới hiện tại cần được xem lại.

Tương tự, **có nhiều container, pod hoặc repository chưa đủ**. Có thể có nhiều container chứa những thành phần luôn phải phát hành đồng bộ và vẫn là một distributed monolith.

### 3.3. Dữ liệu có chủ sở hữu rõ ràng

Mỗi service phải có quyền quyết định các bất biến, quy tắc cập nhật và cấu trúc dữ liệu của miền mình quản lý. Ví dụ, Inventory Service là nơi thực hiện quy tắc “không giữ quá lượng tồn có thể bán”; Order Service không được tự cập nhật trực tiếp bảng tồn kho để vượt qua logic đó.

Mẫu **database per service** nhấn mạnh **quyền sở hữu dữ liệu**, không bắt buộc mỗi service phải có một máy chủ database riêng. Có thể dùng các database hoặc schema tách biệt trên cùng hạ tầng nếu quyền truy cập và vòng đời thay đổi được kiểm soát. Điều cần tránh là nhiều service tự do đọc/ghi cùng bảng, JOIN xuyên miền hoặc phụ thuộc vào migration nội bộ của nhau.

Khi cần dữ liệu của service khác, dùng hợp đồng API, sự kiện hoặc bản sao dữ liệu phục vụ đọc có cơ chế đồng bộ rõ ràng. Với cách này, thay đổi schema bên trong Inventory không mặc nhiên bắt Order sửa SQL.

### 3.4. Hợp đồng và mức kết dính

Service giao tiếp bằng hợp đồng rõ ràng: REST/gRPC, message, event schema hoặc giao thức thích hợp. Hợp đồng cần mô tả ý nghĩa nghiệp vụ, định dạng, lỗi, timeout và cách tiến hóa tương thích.

Hai service có thể giao tiếp qua HTTP nhưng vẫn kết dính chặt nếu một lệnh nghiệp vụ phải gọi đồng bộ qua nhiều bước nhỏ, hoặc nếu thay đổi một trường nội bộ làm nhiều service lỗi. Ngược lại, giao tiếp đồng bộ **không tự động làm mất tính microservice**; cần đánh giá tác động thay đổi, độ tin cậy và mức phụ thuộc trên đường xử lý.

### 3.5. Quyền sở hữu vận hành

Ranh giới hữu ích còn thể hiện ở khả năng theo dõi, cảnh báo, xử lý lỗi và mở rộng độc lập: log có correlation/trace ID, metrics theo dịch vụ, health check, rollback, giới hạn timeout và retry. Nhiều nhóm có thể cùng làm trong monorepo hoặc một nhóm phụ trách nhiều service; **số lượng team hay repository không phải tiêu chí định nghĩa**. Điều quan trọng là trách nhiệm và quyền thay đổi rõ ràng.

## 4. Minh họa: ba hệ thống đều có nhiều API nhưng bản chất khác nhau

### Trường hợp A — Một ứng dụng Spring Boot có nhiều endpoint

~~~text
Client
  |
  v
[Spring Boot application]
  |-- /api/products   -> Catalog module
  |-- /api/orders     -> Order module
  |-- /api/payments   -> Payment module
  |
  +-- [One shared application database]
       [One build + one deployment]
~~~

Ứng dụng này có thể được thiết kế rất tốt: module rõ, interface nội bộ sạch, kiểm thử nhanh, transaction đồng bộ đơn giản. Nhưng việc có ba nhóm API không biến nó thành ba microservice. Các controller chỉ là các điểm vào cùng một tiến trình.

### Trường hợp B — Chia thành nhiều ứng dụng nhưng vẫn bị khóa cùng nhau

~~~text
Client -> API Gateway
             |-- Order App ------+
             |-- Inventory App --+--> [Shared tables / shared writes]
             |-- Payment App ----+
                  |
         [Every change needs a coordinated release]
~~~

Trên sơ đồ có ba ứng dụng và ba deployment. Tuy nhiên, Order tự sửa bảng inventory, Payment đọc cấu trúc bảng order, mọi migration phải được triển khai đồng thời. Khi Inventory đổi schema, cả ba ứng dụng cùng thay đổi. Đây là ví dụ điển hình của **distributed monolith**: hệ thống nhận chi phí mạng và vận hành phân tán nhưng vẫn phụ thuộc như một khối.

Không thể kết luận chỉ từ hình vẽ: các bảng được chia schema và quyền truy cập ra sao, hợp đồng có ổn định không, triển khai có thật sự độc lập không mới là bằng chứng.

### Trường hợp C — Dịch vụ theo miền nghiệp vụ, tương tác qua hợp đồng

~~~text
Client -> Gateway / BFF
              |
              v
        [Order Service] ---- request/event ----> [Inventory Service]
          |  Order data                          |  Inventory data
          |
          +---- payment request/event ---------> [Payment Service]
               order lifecycle                    payment transactions

       Independent change ownership + explicit contracts
       Per-service telemetry, deployments and failure handling
~~~

Order là chủ sở hữu đơn hàng, Inventory quyết định có thể giữ hàng, Payment quyết định trạng thái giao dịch. Dịch vụ không cập nhật bảng của nhau trực tiếp. Một thay đổi nội bộ của Payment có thể phát hành riêng khi vẫn giữ hợp đồng tương thích. Đây là **ứng viên microservices hợp lý** nếu các ranh giới và quy trình đó thực sự được thực thi, không chỉ tồn tại trên sơ đồ.

## 5. API khác microservice ở đâu?

Một API là **giao diện** mà client hoặc thành phần khác sử dụng. Một microservice có thể cung cấp nhiều endpoint, một endpoint, consumer message hoặc chỉ xử lý sự kiện. Những ví dụ sau đều hợp lệ:

- Một monolith cung cấp 100 REST endpoint: **vẫn có thể là một monolith**.
- Một microservice cung cấp nhiều API cho cùng năng lực Order: **vẫn có thể là một microservice**.
- Một service xử lý sự kiện PaymentCaptured, không cung cấp public HTTP API: **vẫn có thể là microservice**.
- Nhiều API backend được đưa sau một API Gateway: **Gateway chỉ là điểm vào**; không tự chứng nhận kiến trúc phía sau.
- Nhiều microservice dùng chung thư viện logging hoặc cùng Git repository: **không tự động sai**; cần xét thư viện có tạo coupling phát hành hay không.

Điều dễ gây nhầm là microservices **thường** sử dụng API để trao đổi, nên từ “nhiều API” bị suy diễn thành “nhiều microservice”. Quan hệ đúng là: **API là công cụ tương tác; microservices là cách phân ranh trách nhiệm và vòng đời thay đổi**.

## 6. Một ví dụ Java/Spring: code HTTP không quyết định kiến trúc

Giả sử có controller sau:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {
    private final OrderApplicationService orders;

    OrderController(OrderApplicationService orders) {
        this.orders = orders;
    }

    @PostMapping
    ResponseEntity<OrderResponse> create(@RequestBody CreateOrderRequest request) {
        OrderResponse result = orders.placeOrder(request);
        return ResponseEntity.status(201).body(result);
    }
}
~~~

Đoạn code chỉ cho thấy **một endpoint nhận lệnh tạo đơn**. Không thể suy ra microservice từ annotation @RestController, đường dẫn /api/orders hay tên OrderApplicationService. Cần xem OrderApplicationService được đặt ở đâu, ai quản lý database, quy trình build/deploy và cách tương tác với Inventory/Payment.

Nếu Order, Inventory và Payment đều là module trong cùng Spring Boot, cùng một JAR và transaction nội bộ, đó là một modular monolith. Nếu Order là một ứng dụng độc lập sở hữu trạng thái đơn hàng và gọi hợp đồng công khai của Inventory để giữ hàng, thì có thêm bằng chứng cho ranh giới microservice. Nhưng nếu Order vẫn SELECT/UPDATE trực tiếp bảng Inventory, **chỉ tách controller ra tiến trình khác không giải quyết được sự kết dính**.

Hãy phân biệt:

~~~text
Trong cùng ứng dụng:
OrderController -> OrderApplicationService
                -> InventoryModule.reserve(...)  // internal call
                -> shared transaction if suitable

Giữa các dịch vụ:
Order API -> Order domain
          -> Inventory contract (HTTP/message)
          -> handle timeout, duplicate, rejection and reconciliation
~~~

Đoạn thứ hai đòi hỏi logic mạng và nhất quán dữ liệu; đổi từ lời gọi method sang HTTP không phải phép biến đổi “miễn phí”.

## 7. Vì sao phân chia thật sự khó hơn tách mã nguồn?

### 7.1. Ranh giới transaction thay đổi

Trong một monolith dùng cùng database, việc tạo đơn và trừ tồn kho có thể nằm trong một transaction ACID. Khi Order và Inventory sở hữu dữ liệu riêng, một transaction cục bộ ở Order không thể tự bảo đảm commit nguyên tử trên database của Inventory.

Giả sử quy trình gồm:

1. Order tiếp nhận yêu cầu và tạo đơn trạng thái PENDING.
2. Order yêu cầu Inventory giữ hàng với reservation ID cố định.
3. Inventory chấp nhận hoặc từ chối; kết quả được lưu bền vững.
4. Nếu hàng đã giữ, Order yêu cầu Payment xử lý giao dịch.
5. Khi Payment thành công, Order chuyển CONFIRMED; nếu thất bại, Order yêu cầu hoàn tác giữ hàng hoặc thực hiện quy trình bù tương ứng.

Luồng trên chỉ là **một thiết kế minh họa**. Các bước, thời điểm chấp nhận đơn và chính sách bù phụ thuộc nghiệp vụ. Không nên giả định một chuỗi REST call sẽ bảo đảm tính nguyên tử như transaction SQL cũ.

Các kỹ thuật thường cần là **Saga** hoặc quy trình điều phối có trạng thái, **transactional outbox** để công bố sự kiện phù hợp với commit nội bộ, **idempotency key** để chống xử lý trùng khi retry, và **reconciliation** để xử lý trạng thái lệch. Mỗi dịch vụ vẫn giữ bất biến miền của mình, thay vì cho dịch vụ khác cập nhật trực tiếp dữ liệu.

### 7.2. Mạng luôn có lỗi và độ trễ

Gọi một method trong process không tương đương gọi dịch vụ qua mạng. HTTP/message có thể timeout, mất kết nối, xử lý thành công nhưng response bị mất hoặc nhận message trùng. Service cần deadline/timeout, retry có giới hạn và chỉ retry khi thao tác có thể thực hiện an toàn, circuit breaker hoặc giới hạn tải khi phù hợp, cùng chiến lược fallback.

Ví dụ, Payment đã ghi nhận giao dịch nhưng Order bị timeout. Nếu Order gọi lại bằng mã giao dịch mới và không có idempotency, người mua có thể bị thanh toán hai lần. Tên gọi microservice không xóa được tình huống này; thiết kế hợp đồng và hành vi lỗi mới quyết định độ tin cậy.

### 7.3. Cần quan sát toàn bộ luồng

Một yêu cầu qua ba service tạo log ở ba nơi. Nếu không truyền trace/correlation ID, rất khó nối các sự kiện để tìm nguyên nhân. Health check chỉ nói tiến trình đang chạy, chưa đủ để chứng minh nghiệp vụ đặt hàng thành công. Cần theo dõi lỗi và độ trễ theo lời gọi, hàng đợi, tỷ lệ retry, tuổi của message và các trạng thái nghiệp vụ còn treo.

### 7.4. Cần quản lý thay đổi hợp đồng

Nếu Order và Inventory phát hành độc lập, hợp đồng giữa chúng phải chịu được chênh lệch phiên bản trong thời gian nâng cấp. Có thể dùng schema/contract test, quy tắc thêm trường có khả năng tương thích và chiến lược deprecate dần. Bắt mọi consumer nâng cấp đồng thời mỗi khi provider đổi trường sẽ lấy đi phần lớn lợi ích triển khai độc lập.

## 8. Những ngộ nhận thường gặp

| Nhận định | Đánh giá chính xác hơn |
| --- | --- |
| “Có 20 API nên có 20 microservice.” | Số endpoint không cho biết số ranh giới nghiệp vụ hay deployment. |
| “Mỗi controller chạy một Docker container là microservice.” | Container là đơn vị đóng gói; cần xét dữ liệu, hợp đồng và quyền thay đổi. |
| “Cứ tách repository là có microservices.” | Repository là cấu trúc quản lý mã nguồn, không bảo đảm tự chủ phát hành. |
| “Dùng Kafka là microservice; dùng REST thì không.” | Giao thức không quyết định kiến trúc. REST, gRPC và message đều có thể phù hợp. |
| “Mỗi service phải có server database vật lý riêng.” | Mấu chốt là quyền sở hữu dữ liệu và cô lập thay đổi; hạ tầng có thể chia sẻ có kiểm soát. |
| “Không thể có nhiều service cùng một team.” | Ranh giới service và sơ đồ tổ chức có liên quan nhưng không đồng nhất. |
| “Càng tách nhỏ càng tốt.” | Quá nhỏ tạo quá nhiều hợp đồng, độ trễ và chi phí vận hành, thường là sai ranh giới. |
| “Tách thành nhiều process chắc chắn mở rộng tốt hơn.” | Chỉ hiệu quả khi nhu cầu tải, hotspot và ranh giới tài nguyên phù hợp; còn có thêm network overhead. |
| “Microservices lúc nào cũng tốt hơn monolith.” | Kiến trúc phù hợp tùy quy mô, tốc độ thay đổi, năng lực vận hành và sự phức tạp nghiệp vụ. |

## 9. Cách nhận diện một “distributed monolith”

Một hệ thống có nhiều service về mặt triển khai nhưng mang nhiều dấu hiệu sau cần được xem xét:

- Một thay đổi nhỏ buộc sửa và phát hành đồng thời nhiều service.
- Nhiều service đọc/ghi trực tiếp cùng bảng hoặc lệ thuộc vào JOIN xuyên database.
- Luồng nghiệp vụ chỉ hoạt động khi mọi service nhỏ đều phản hồi tức thì; một lỗi nhỏ kéo sập toàn bộ request.
- Nhiều lớp kỹ thuật bị chia qua mạng: Controller Service gọi Business Service, tiếp tục gọi Repository Service.
- Có các thư viện domain hoặc DTO dùng chung thay đổi liên tục khiến mọi service phải nâng cấp cùng lúc.
- Service không thể định nghĩa rõ bất biến và dữ liệu mình sở hữu.
- Không có contract test, tracing, chiến lược timeout hay xử lý trùng lặp dù đang vận hành phân tán.

Đây là **dấu hiệu chẩn đoán**, không phải luật “chỉ cần một dấu hiệu là kết luận sai”. Có phụ thuộc phối hợp không thể tránh ở các thay đổi nghiệp vụ lớn. Hãy hỏi mức phối hợp đó xảy ra thường xuyên hay chỉ ở những thay đổi thật sự cắt ngang nhiều miền.

## 10. Khi nào nên chọn modular monolith thay vì microservices?

**Modular monolith là một lựa chọn có chủ đích**, phù hợp khi sản phẩm còn đổi nhiều, các miền nghiệp vụ chưa ổn định, nhóm phát triển nhỏ hoặc chưa có năng lực vận hành nhiều deployment. Có thể đạt tách biệt mã nguồn, dependency một chiều, transaction đơn giản, kiểm thử tích hợp gọn và quan sát tổng thể mà chưa trả giá cho mạng phân tán.

Microservices có thể hợp lý khi các năng lực nghiệp vụ đã đủ rõ, nhịp phát hành khác nhau, nhiều nhóm cần tự chủ, tải hoặc yêu cầu mở rộng khác biệt, hoặc một số miền cần cô lập lỗi/tuân thủ chuyên biệt. Giá trị kỳ vọng phải lớn hơn chi phí thêm của CI/CD, hạ tầng, sự cố mạng, consistency, security, tracing và vận hành.

Một lộ trình phổ biến là:

1. Thiết kế module theo business capability và tách phụ thuộc nội bộ.
2. Giao tiếp qua interface rõ, không cho module tùy ý sửa dữ liệu của module khác.
3. Đo tần suất thay đổi, xung đột phát hành, độ trễ, tải và sự cố.
4. Chỉ tách module có lợi ích độc lập triển khai thực sự; xác định contract, quyền sở hữu dữ liệu và cách di chuyển dữ liệu trước.
5. Sau khi tách, kiểm chứng khả năng phát hành riêng và điều hành lỗi bằng tình huống thực.

Đừng chia ngay mỗi bảng thành một service. Các thực thể dữ liệu thường tham gia cùng một bất biến; ranh giới theo bảng dễ dẫn đến chatty APIs và transaction phân tán không cần thiết.

## 11. Bộ câu hỏi thực hành để đánh giá hệ thống hiện tại

Khi ai đó nói “Chúng ta đã chuyển sang microservices”, hãy yêu cầu một ví dụ thay đổi và kiểm tra các câu hỏi sau:

1. **Năng lực nghiệp vụ:** Service chịu trách nhiệm cho hành vi nghiệp vụ nào, ai quyết định bất biến của hành vi đó?
2. **Dữ liệu:** Nó sở hữu những dữ liệu nào? Có service khác ghi trực tiếp hoặc phụ thuộc schema nội bộ không?
3. **Thay đổi:** Nếu đổi một quy tắc riêng của service, những repository/artifact/service nào bắt buộc đổi theo?
4. **Triển khai:** Có thể triển khai và rollback service riêng khi giữ hợp đồng tương thích không?
5. **Giao tiếp:** Contract có rõ về versioning, lỗi, timeout, idempotency và sự kiện không?
6. **Lỗi:** Nếu một dependency chậm hoặc unavailable, hệ thống suy giảm ra sao? Có thể quan sát và phục hồi không?
7. **Vận hành:** Có chủ sở hữu, metrics, log, tracing và quy trình xử lý sự cố theo dịch vụ không?
8. **Lợi ích:** Việc tách tạo ra giá trị đo được nào so với giữ một modular monolith?

Một cách kiểm tra cụ thể: giả sử thay quy tắc giữ tồn kho. Nếu chỉ Inventory thay code, chạy kiểm thử hợp đồng, triển khai riêng và Order không cần biết schema mới, hệ thống thể hiện ranh giới tốt. Nếu Order và Payment đều phải chỉnh SQL, rebuild và deploy đồng thời, số lượng service trên dashboard không phản ánh mức tự chủ thực tế.

## 12. Bài tập tình huống

**Tình huống 1.** Một ứng dụng Spring Boot có 15 controller, 80 endpoint, 12 module Gradle và một database. Mỗi lần phát hành tạo một JAR.

**Đáp án:** Đây có thể là một **modular monolith**, không đủ cơ sở gọi là 12 hoặc 80 microservice. Việc module hóa vẫn có giá trị lớn.

**Tình huống 2.** Ba container Orders, Stock, Billing chạy trên Kubernetes; cả ba cùng cập nhật bảng orders, stocks và invoices; release luôn theo cùng một lịch vì migration chung.

**Đáp án:** Có dấu hiệu mạnh của **distributed monolith**: triển khai phân tán nhưng dữ liệu và chu kỳ thay đổi kết dính. Giải pháp bắt đầu từ ranh giới sở hữu và hợp đồng, không phải tăng số pod.

**Tình huống 3.** Order và Inventory có database/schema do mỗi bên quản lý, không ghi vào bảng của nhau, có API hợp đồng và có thể triển khai riêng. Cả hai nằm trong một monorepo, cùng một team và dùng HTTP đồng bộ cho thao tác giữ hàng.

**Đáp án:** **Có thể là microservices**. Monorepo, một team và HTTP đồng bộ không loại trừ kiến trúc đó. Cần tiếp tục đánh giá timeout, lỗi, dữ liệu và quyền triển khai thực tế.

**Tình huống 4.** Một team muốn tách Pricing thành service mới chỉ vì PricingController dài, trong khi toàn bộ thay đổi giá và khuyến mãi đều đi cùng nhau và khối lượng tải nhỏ.

**Đáp án:** Chưa có luận cứ đủ mạnh để tách. Nên làm rõ miền giá/khuyến mãi, sửa thiết kế module và đo nhu cầu độc lập trước; độ dài một controller tự nó không phải ranh giới kiến trúc.

## 13. Ghi nhớ

- **Nhiều endpoint ≠ nhiều microservice.** API là cách một chức năng được gọi.
- **Nhiều package/module ≠ nhiều microservice.** Module hóa có thể ở trong một tiến trình duy nhất.
- **Nhiều container/deployment ≠ tự động có microservices tốt.** Tách tiến trình nhưng chia sẻ dữ liệu và lịch phát hành có thể tạo distributed monolith.
- **Microservice cần ranh giới nghiệp vụ, quyền sở hữu dữ liệu, contract và khả năng thay đổi/triển khai tương đối độc lập.** Hệ thống còn phải chịu được lỗi mạng và quan sát được toàn luồng.
- **Kiến trúc tốt được đánh giá bằng thay đổi thực tế và chi phí vận hành**, không bằng số lượng ô vuông trên sơ đồ.
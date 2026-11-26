# Các mô hình ba tầng, bốn tầng và nhiều tầng: không có số tầng bắt buộc

Kiến trúc phân tầng tổ chức phần mềm thành những nhóm có trách nhiệm khác nhau và quy định cách các nhóm cộng tác. Ba tầng, bốn tầng hay nhiều tầng là những cách chia phổ biến, không phải các cấp độ bắt buộc mà mọi dự án phải lần lượt đạt tới. Một hệ thống tốt có số tầng vừa đủ để làm rõ trách nhiệm, giới hạn phụ thuộc và hỗ trợ thay đổi.

Trong module **Học tổ chức phần mềm theo kiến trúc phân tầng**, điều cần nắm là lý do một nhóm chọn cách chia cụ thể, trách nhiệm nào được tách ra và chi phí của ranh giới đó. Không nên quyết định số tầng chỉ dựa vào quy mô dự án hoặc một sơ đồ mẫu.

## 1. Phân biệt tầng logic và tier triển khai

Từ “tầng” đôi khi được dùng cho hai khái niệm khác nhau:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Tầng logic (logical layer) | Nhóm mã nguồn theo trách nhiệm và quy tắc phụ thuộc | Presentation, Application, Domain, Infrastructure |
| Tier triển khai (deployment tier) | Nhóm thành phần chạy được triển khai và vận hành như một đơn vị riêng; thường tương ứng với tiến trình, máy chủ hoặc môi trường | Client/presentation, máy chủ ứng dụng, máy chủ cơ sở dữ liệu |

Các tầng logic có thể nằm trong cùng một tiến trình. Chẳng hạn, một ứng dụng Spring Boot đóng gói thành một tệp JAR có thể chứa controller, application service, domain model và repository adapter. Nếu xét các thành phần phía máy chủ, ứng dụng và máy chủ cơ sở dữ liệu là hai đơn vị triển khai chính, dù mã nguồn có bốn tầng logic.

Nếu tính cả trình duyệt chạy giao diện, một hệ thống có thể được mô tả theo mô hình triển khai ba tier: client/presentation, application server và database server. Trong khi đó, mã nguồn application server vẫn có thể được tổ chức thành bốn hoặc nhiều tầng logic. Vì vậy, khi nghe “kiến trúc ba tầng”, cần xác định người nói đang đề cập đến trách nhiệm trong mã nguồn hay các tier triển khai. Hai con số không nhất thiết trùng nhau.

## 2. Mô hình ba tầng

Mô hình ba tầng thường gom trách nhiệm vào ba nhóm:

| Tầng | Trách nhiệm chính | Ví dụ trong ứng dụng đặt hàng |
|---|---|---|
| Presentation (trình bày) | Nhận đầu vào, chuyển đổi dữ liệu giao tiếp và trả kết quả | **OrderController**, trang đặt hàng |
| Business/Application (nghiệp vụ hoặc ứng dụng) | Điều phối xử lý và thực thi quy tắc nghiệp vụ | **OrderService**, **Order** |
| Data Access (truy cập dữ liệu) | Đọc, ghi và ánh xạ dữ liệu lưu trữ | **OrderRepository**, DAO |

Luồng thường gặp là:

~~~text
HTTP request
    |
    v
OrderController
    |
    v
OrderService ---- thực hiện quy tắc và điều phối
    |
    v
OrderRepository
    |
    v
Database
~~~

Trong ứng dụng Java dùng Spring, controller nhận request và gọi service. Service xử lý trường hợp sử dụng, sau đó gọi repository để lưu hoặc truy vấn dữ liệu. Repository có thể dùng Spring Data JPA để làm việc với cơ sở dữ liệu. Kết quả được chuyển ngược lên controller để tạo response.

Ví dụ cấu trúc gói đơn giản:

~~~text
com.example.shop
├── presentation
│   └── OrderController.java
├── business
│   ├── OrderService.java
│   └── Order.java
└── data
    └── OrderRepository.java
~~~

Ưu điểm của cách chia này là dễ hiểu, ít lớp trung gian và phù hợp với ứng dụng CRUD hoặc nghiệp vụ còn đơn giản. Người đọc nhanh chóng biết mã giao tiếp nằm ở đâu, xử lý chính nằm ở đâu và truy cập dữ liệu nằm ở đâu.

Giới hạn xuất hiện khi nhóm Business/Application phải gánh quá nhiều loại trách nhiệm. Service có thể vừa điều phối use case, vừa chứa quy tắc miền, vừa phụ thuộc trực tiếp vào framework lưu trữ. Khi quy tắc nghiệp vụ phức tạp, việc thay đổi JPA hoặc kiểm thử nghiệp vụ có thể trở nên khó khăn. Khi đó, tách riêng Application và Domain có thể tạo ra ranh giới hữu ích.

## 3. Mô hình bốn tầng

Một cách chia chi tiết hơn là tách phần điều phối use case khỏi mô hình và quy tắc nghiệp vụ:

| Tầng | Trách nhiệm | Thành phần Java/Spring thường gặp |
|---|---|---|
| Presentation | Giao tiếp với HTTP, giao diện hoặc giao thức bên ngoài | **@RestController**, request/response DTO |
| Application | Điều phối một trường hợp sử dụng, quản lý ranh giới giao dịch và gọi các cộng tác cần thiết | Application service, use case, command handler |
| Domain | Mô hình hóa khái niệm, trạng thái, bất biến và quy tắc nghiệp vụ cốt lõi | Entity miền, value object, domain service |
| Infrastructure | Cung cấp kỹ thuật cụ thể để lưu trữ, gửi thông điệp hoặc gọi hệ thống ngoài | JPA adapter, message broker adapter, HTTP client |

Ví dụ với use case đặt hàng:

1. **OrderController** nhận **PlaceOrderRequest**, kiểm tra định dạng đầu vào và chuyển nó thành lệnh cho use case.
2. **PlaceOrderUseCase** điều phối quy trình đặt hàng, xác định các bước cần thực hiện và quản lý giao dịch.
3. Mô hình **Order** kiểm tra các điều kiện thuộc nghiệp vụ, chẳng hạn đơn hàng phải có ít nhất một dòng hàng và chỉ được chuyển trạng thái theo quy tắc hợp lệ.
4. Một repository adapter dùng Spring Data JPA để chuyển đổi và lưu dữ liệu.

Application trả lời câu hỏi “use case cần phối hợp những bước nào?”. Domain trả lời “trạng thái và hành vi nghiệp vụ nào hợp lệ?”. Infrastructure trả lời “các thao tác đó được thực hiện bằng công nghệ cụ thể nào?”.

Một quy tắc phụ thuộc thường dùng là Presentation gọi Application; Application sử dụng Domain và các cổng (port) mà nó cần; Infrastructure triển khai những cổng đó. Ví dụ, Application có thể định nghĩa hợp đồng **OrderRepository**, còn Infrastructure cung cấp lớp thực thi bằng JPA:

~~~java
// Hợp đồng mà use case cần; có thể đặt trong Application hoặc Domain
public interface OrderRepository {
    void save(Order order);
}
~~~

~~~java
// Adapter thuộc Infrastructure, dùng Spring Data JPA ở bên trong
@Repository
public class JpaOrderRepositoryAdapter implements OrderRepository {
    private final SpringDataOrderJpaRepository jpaRepository;

    public JpaOrderRepositoryAdapter(
            SpringDataOrderJpaRepository jpaRepository) {
        this.jpaRepository = jpaRepository;
    }

    @Override
    public void save(Order order) {
        jpaRepository.save(OrderJpaEntity.from(order));
    }
}
~~~

Vị trí chính xác của hợp đồng repository tùy thuộc cách thiết kế và phạm vi mà hợp đồng phục vụ. Điều quan trọng là mã nghiệp vụ phụ thuộc vào một hợp đồng có ý nghĩa đối với nó, còn chi tiết JPA được giữ trong adapter. Spring có thể kết nối adapter với use case thông qua dependency injection.

Mô hình bốn tầng giúp kiểm thử quy tắc miền mà không cần khởi động Spring hoặc kết nối cơ sở dữ liệu. Nó cũng giúp thay đổi công nghệ lưu trữ ít ảnh hưởng hơn tới nghiệp vụ. Đổi lại, dự án cần thêm hợp đồng, adapter, ánh xạ và cấu hình. Với ứng dụng rất đơn giản, các lớp này có thể chỉ chuyển tiếp lời gọi mà không tạo ra lợi ích tương xứng.

Bốn tầng cũng không đồng nghĩa với việc bắt buộc phải áp dụng đầy đủ Domain-Driven Design (DDD). Có thể tách Application và Domain để giữ trách nhiệm rõ ràng mà không cần dùng mọi khái niệm hay chiến thuật của DDD. DDD là một phương pháp mô hình hóa miền; số tầng là một quyết định tổ chức kiến trúc.

## 4. Mô hình nhiều tầng

Khi hệ thống có nhiều loại giao tiếp, tích hợp hoặc lưu trữ với vòng đời thay đổi khác nhau, nhóm có thể tiếp tục chia nhỏ các trách nhiệm. Một cách tổ chức có thể gồm:

- Presentation: giao diện web, REST controller hoặc giao tiếp từ ứng dụng di động.
- Application/API: điểm vào hoặc facade dành cho một nhóm giao thức hay nhóm client, nếu thực sự cần tách.
- Application use cases: các luồng nghiệp vụ mà hệ thống cung cấp.
- Domain: mô hình và quy tắc nghiệp vụ.
- Persistence adapters: truy cập cơ sở dữ liệu hoặc kho lưu trữ.
- Integration adapters: tích hợp cổng thanh toán, vận chuyển, email hoặc hệ thống đối tác.

Đây chỉ là một ví dụ về cách phân rã. Một dự án có thể gộp API với Presentation, hoặc gộp các adapter lưu trữ và tích hợp trong một nhóm Infrastructure. Cũng có thể chia các module theo miền nghiệp vụ thay vì tạo thêm tầng dùng chung cho toàn hệ thống.

Nên tách một trách nhiệm khi có lý do cụ thể, chẳng hạn:

- Nhiều giao thức đầu vào cần dùng chung một use case nhưng có cách chuyển đổi request khác nhau.
- Tích hợp với đối tác có cấu hình, lỗi, retry và cách kiểm thử riêng.
- Nhiều loại lưu trữ có thể thay đổi độc lập.
- Một module cần ranh giới sở hữu và phụ thuộc rõ ràng để nhiều nhóm phát triển song song.

Không nên tạo tầng chỉ để mỗi lớp có một thư mục riêng hoặc để sơ đồ trông “đầy đủ”. Nếu một tầng chỉ nhận tham số rồi chuyển nguyên trạng sang tầng kế tiếp, không bảo vệ hợp đồng hay thêm ý nghĩa, nó có thể là một lớp trung gian thừa. Quá nhiều tầng cũng khiến việc lần theo một request khó hơn, tăng số kiểu dữ liệu phải ánh xạ và làm thay đổi nhỏ lan qua nhiều nơi.

Các chức năng dùng chung như logging, metrics, cấu hình, bảo mật và quản lý giao dịch cũng không tự động trở thành một tầng riêng. Chúng có thể là mối quan tâm xuyên suốt, được áp dụng qua framework, middleware, interceptor hoặc cấu hình phù hợp.

## 5. Chọn số tầng theo trách nhiệm và chi phí

Có thể dùng bảng sau làm điểm bắt đầu khi thiết kế:

| Cách chia | Phù hợp khi | Cần chú ý |
|---|---|---|
| Ba tầng | Luồng xử lý và quy tắc còn đơn giản; nhóm muốn cấu trúc dễ hiểu, ít mã khung | Business/Application có thể trở thành nơi tập trung quá nhiều trách nhiệm |
| Bốn tầng | Cần phân biệt điều phối use case, quy tắc miền và chi tiết kỹ thuật | Phải xác định hợp đồng và hướng phụ thuộc để các tầng không chỉ chuyển tiếp lời gọi |
| Nhiều tầng | Có nhiều loại giao tiếp, tích hợp hoặc lưu trữ cần thay đổi và kiểm thử độc lập | Tránh chia nhỏ máy móc, trùng trách nhiệm hoặc tạo phụ thuộc vòng |

Trước khi thêm một tầng, hãy trả lời các câu hỏi:

1. Trách nhiệm nào đang bị trộn lẫn và thay đổi cùng nhau một cách không cần thiết?
2. Tầng mới sẽ sở hữu hợp đồng hoặc quy tắc nào?
3. Thành phần nào được phép phụ thuộc vào tầng mới, và phụ thuộc theo hướng nào?
4. Việc tách ra có giúp kiểm thử, thay đổi hoặc phân công sở hữu dễ hơn không?
5. Chi phí ánh xạ dữ liệu, cấu hình và điều hướng qua tầng mới có hợp lý không?

Nếu chưa có câu trả lời rõ ràng, giữ cách chia hiện tại và chỉ tách khi có nhu cầu thực tế là lựa chọn hợp lý. Có thể bắt đầu với ba tầng rồi tách Domain hoặc các adapter khi trách nhiệm phát triển phức tạp hơn. Cũng có thể thiết kế bốn tầng ngay từ đầu nếu miền nghiệp vụ đã có nhiều quy tắc và cần giữ chúng độc lập với công nghệ.

Số tầng còn là quyết định riêng với quy tắc tầng đóng hay tầng mở. Với tầng đóng, một tầng chỉ gọi tầng liền kề theo quy định. Với tầng mở, một số tầng có thể gọi trực tiếp tầng thấp hơn. Dù chọn cách nào, đường đi đó cần được quy định rõ; chẳng hạn controller không nên truy cập thẳng cơ sở dữ liệu nếu việc đó bỏ qua use case và quy tắc nghiệp vụ.

## 6. Theo dõi một request và kiểm thử theo ranh giới

Với mô hình bốn tầng trong Spring, luồng chạy của request đặt hàng có thể hình dung như sau:

~~~mermaid
sequenceDiagram
    participant C as OrderController
    participant U as PlaceOrderUseCase
    participant D as Order (Domain)
    participant R as OrderRepository port
    participant A as JPA repository adapter
    participant DB as Database

    C->>U: place(command)
    U->>D: tạo và kiểm tra Order
    D-->>U: Order hợp lệ
    U->>R: save(order)
    Note over R,A: Dependency injection cung cấp adapter thực thi port
    R->>A: gọi save(order)
    A->>DB: INSERT / UPDATE
    DB-->>A: kết quả lưu
    A-->>U: hoàn tất
    U-->>C: kết quả use case
~~~

Đường đi lúc chạy cho thấy controller không cần biết JPA entity hay câu lệnh SQL. Use case làm việc với hợp đồng repository; đối tượng thực thi hợp đồng được Spring cung cấp khi ứng dụng khởi động. Quy tắc nghiệp vụ của **Order** có thể được kiểm thử riêng mà không cần cơ sở dữ liệu.

Có thể tổ chức kiểm thử theo chính các ranh giới đó:

- **Domain unit test:** kiểm tra bất biến và chuyển trạng thái của **Order**; không cần Spring hay database.
- **Application unit test:** gọi use case với repository giả (fake hoặc mock) để xác minh điều phối và các nhánh xử lý.
- **Presentation test:** dùng Spring MVC test để kiểm tra mapping request/response, mã HTTP và validation ở biên giao tiếp.
- **Infrastructure integration test:** kiểm tra adapter với cơ sở dữ liệu tương thích hoặc môi trường kiểm thử gần với hệ thống thật.
- **End-to-end test:** kiểm tra một số luồng quan trọng qua các thành phần đã kết nối.

Không phải mọi dự án đều cần đủ mọi loại kiểm thử ở mọi tầng. Hãy tập trung vào rủi ro của từng ranh giới: quy tắc miền cần được kiểm tra độc lập, hợp đồng HTTP cần được xác minh ở biên giao tiếp và adapter cần được kiểm tra với công nghệ mà nó tích hợp.

Một kiến trúc phân tầng có giá trị khi người phát triển biết đặt trách nhiệm ở đâu, biết một thay đổi sẽ ảnh hưởng tới thành phần nào và có thể kiểm thử thành phần đó với mức phụ thuộc phù hợp. Ba, bốn hay nhiều tầng chỉ là phương tiện để đạt được điều đó; không có con số nào đúng cho mọi hệ thống.


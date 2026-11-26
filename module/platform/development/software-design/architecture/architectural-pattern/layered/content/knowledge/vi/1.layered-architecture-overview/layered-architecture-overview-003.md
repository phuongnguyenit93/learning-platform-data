 # Tổng quan kiến trúc phân tầng

 ## Từ vựng nền tảng: tầng, thành phần, hợp đồng, phụ thuộc và luồng gọi

 Trong module `SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED` — **Học tổ chức phần mềm theo kiến trúc phân tầng** — ta dùng các khái niệm dưới đây để mô tả cách mã nguồn được chia theo trách nhiệm và cách các phần phối hợp với nhau. Nắm đúng từ vựng giúp đọc sơ đồ kiến trúc, lần theo một yêu cầu và nhận ra nơi một thay đổi có thể lan tới.

 Kiến trúc phân tầng là cách tổ chức hệ thống thành những nhóm trách nhiệm có ranh giới và quy tắc phụ thuộc. Tên tầng có thể khác nhau giữa các dự án; số tầng cũng phụ thuộc quy mô và nhu cầu. Một ứng dụng nhỏ có thể gộp nghiệp vụ và điều phối vào một tầng ứng dụng. Hệ thống lớn có thể tách thêm các tầng hoặc mô-đun chuyên biệt. Điều quan trọng là mỗi ranh giới phải có ý nghĩa và các hướng phụ thuộc phải được chủ động quy định.

 ## 1. Tầng (layer)

 **Tầng** là một ranh giới tổ chức ở mức logic, gom những thành phần có trách nhiệm gần nhau và quy định cách chúng được phép cộng tác. Tầng trả lời câu hỏi: *phần này chịu trách nhiệm về loại công việc nào, và được phép phụ thuộc vào đâu?*

 Trong một ứng dụng nghiệp vụ Java, cách phân chia thường gặp là:

 | Tầng logic | Trách nhiệm thường gặp | Ví dụ |
 | --- | --- | --- |
 | Trình bày (presentation) | Tiếp nhận giao tiếp bên ngoài, chuyển dữ liệu vào/ra hệ thống | REST controller, giao diện web |
 | Ứng dụng (application) | Điều phối một ca sử dụng, quản lý ranh giới giao dịch và phối hợp các dịch vụ | `PlaceOrderService`, use case handler |
 | Miền nghiệp vụ (domain) | Biểu diễn khái niệm và quy tắc nghiệp vụ cốt lõi | `Order`, `Money`, chính sách tính giá |
 | Truy cập dữ liệu / hạ tầng (data access / infrastructure) | Lưu trữ, truy vấn và giao tiếp với hệ thống kỹ thuật bên ngoài | JPA adapter, repository triển khai, client gọi dịch vụ |

 Đây là một cách chia phổ biến để minh họa, không phải công thức bắt buộc cho mọi ứng dụng. Có dự án gộp tầng miền vào tầng ứng dụng; có dự án tách hạ tầng thành nhiều mô-đun. Không nên tạo một tầng chỉ vì muốn có thêm một thư mục.

 Tầng là khái niệm **logic**, không đồng nghĩa với máy chủ, tiến trình hay nơi triển khai. Một ứng dụng Spring Boot dạng monolith có thể chứa controller, service, domain model và adapter dữ liệu trong cùng một tiến trình JVM. Các phần đó vẫn là những tầng logic khác nhau dù được đóng gói và triển khai cùng nhau.

 **Tầng triển khai (tier)** nói về nơi các phần chạy và ranh giới triển khai. Ví dụ, một backend Spring Boot và một máy chủ cơ sở dữ liệu có thể tạo thành hai tier triển khai, trong khi mã nguồn backend có bốn tầng logic. Nếu giao diện web chạy riêng, backend chạy riêng và cơ sở dữ liệu chạy riêng, hệ thống có thể có ba tier triển khai. Vì vậy, không thể suy ra số tầng logic từ số máy chủ hoặc ngược lại.

 ## 2. Thành phần (component)

 **Thành phần** là một đơn vị phần mềm có trách nhiệm tương đối tập trung, có thể được nhận diện và sử dụng thông qua một ranh giới. Thành phần thường nằm trong một tầng và cộng tác với thành phần khác qua hợp đồng.

 Ví dụ trong tầng trình bày, `OrderController` là một thành phần tiếp nhận yêu cầu HTTP. Trong tầng ứng dụng, `PlaceOrderService` là thành phần điều phối ca sử dụng đặt hàng. Trong hạ tầng, `JpaOrderStore` là thành phần chuyển thao tác lưu đơn hàng thành thao tác với JPA.

 Một thành phần có thể gồm nhiều lớp, interface và cấu hình. Ngược lại, không phải mọi class đều cần được xem là một thành phần kiến trúc: một class nhỏ chỉ hỗ trợ nội bộ có thể không tạo ra ranh giới độc lập đáng kể. Khi xác định thành phần, hãy nhìn vào trách nhiệm, cách nó được gọi và những chi tiết mà nó che giấu.

 Tầng và thành phần nằm ở hai mức khác nhau: **một tầng thường chứa nhiều thành phần**. Chẳng hạn, tầng ứng dụng có thể có `PlaceOrderService`, `CancelOrderService` và các cổng (port) mà những ca sử dụng đó cần. Không nên dùng hai từ này thay thế cho nhau.

 ## 3. Hợp đồng (contract)

 **Hợp đồng** là thỏa thuận mà bên cung cấp và bên sử dụng cùng dựa vào khi giao tiếp. Hợp đồng mô tả điều gì có thể được yêu cầu, dữ liệu nào được trao đổi và kết quả hoặc lỗi nào có thể xảy ra. Tùy ranh giới, hợp đồng có thể là:

- Một Java interface giữa hai thành phần, chẳng hạn `OrderStore`.
- Một HTTP API gồm phương thức, đường dẫn, cấu trúc request/response và mã trạng thái.
- Một schema của thông điệp hoặc sự kiện được trao đổi giữa các dịch vụ.

 Chữ ký phương thức chỉ là một phần của hợp đồng. Ý nghĩa của tham số, điều kiện hợp lệ, quy tắc về lỗi, tính nhất quán và các tác dụng phụ cũng có thể là một phần của thỏa thuận. Ví dụ, `save(order)` cần làm rõ thao tác lưu có phát sinh lỗi khi dữ liệu không hợp lệ hay không và bên gọi có thể kỳ vọng dữ liệu đã được ghi bền vững ở thời điểm nào.

 Hợp đồng giúp bên sử dụng không phải biết chi tiết triển khai. Nếu `PlaceOrderService` chỉ cần khả năng tìm và lưu đơn hàng, nó có thể phụ thuộc vào interface `OrderStore`; nó không cần biết adapter dùng JPA, JDBC hay gọi một dịch vụ lưu trữ khác.

 ## 4. Phụ thuộc (dependency)

 **Phụ thuộc** tồn tại khi một phần của hệ thống cần biết hoặc cần dựa vào phần khác để hoạt động. Trong mã nguồn, dấu hiệu dễ thấy là một class import, khai báo kiểu tham chiếu, gọi phương thức hoặc tạo trực tiếp đối tượng của một class khác.

 Khi nói “A phụ thuộc B”, ta đang nói đến hướng từ **bên cần** sang **thứ mà bên đó cần**. Nếu `OrderController` sử dụng `PlaceOrderService`, controller phụ thuộc vào hợp đồng của tầng ứng dụng. Mũi tên phụ thuộc trong sơ đồ thường được đọc từ nơi sử dụng tới nơi được sử dụng; cần kiểm tra quy ước của sơ đồ trước khi diễn giải.

 Cần phân biệt hai hướng thường bị nhầm:

- **Phụ thuộc mã nguồn** cho biết mã của thành phần nào cần tham chiếu kiểu hoặc hợp đồng của thành phần nào để biên dịch.
- **Luồng gọi lúc chạy** cho biết thành phần nào thực sự gọi thành phần nào trong một lần thực thi.

 Hai hướng này có thể khác nhau. Với kỹ thuật đảo ngược phụ thuộc, tầng ứng dụng định nghĩa interface `OrderStore`; adapter hạ tầng triển khai interface đó. Mã nguồn của adapter phụ thuộc vào hợp đồng ở tầng ứng dụng, nhưng khi chạy, ứng dụng gọi phương thức qua interface và đối tượng thực tế nhận lời gọi là adapter hạ tầng.

 Ví dụ về hướng phụ thuộc mã nguồn trong cách tổ chức dùng cổng lưu trữ:

 ```text
 Presentation  ->  Application  ->  Domain
 Infrastructure -> Application (triển khai port OrderStore)
 Infrastructure -> Domain (khi adapter cần ánh xạ mô hình miền)
 ```

 Sơ đồ chỉ minh họa một lựa chọn thiết kế: interface `OrderStore` được đặt trong tầng ứng dụng, còn `JpaOrderStore` nằm ở hạ tầng và triển khai interface đó. Adapter cũng có thể tham chiếu mô hình miền khi cần ánh xạ dữ liệu. Dự án khác có thể đặt hợp đồng ở vị trí khác; hãy đọc mã và quy tắc kiến trúc thực tế trước khi kết luận.

 Một kiến trúc phân tầng cần quy định các cạnh phụ thuộc được phép. Trong cách tổ chức tầng đóng, một tầng thường chỉ được sử dụng tầng kế tiếp theo quy tắc đã chọn. Với tầng mở, một tầng có thể được phép sử dụng một tầng thấp hơn mà không đi qua mọi tầng trung gian. Quy tắc cụ thể phải được ghi rõ; không nên mặc định rằng controller được truy cập trực tiếp cơ sở dữ liệu chỉ vì có thể viết được lời gọi đó.

 ## 5. Luồng gọi (call flow)

 **Luồng gọi** là trình tự các lời gọi xảy ra khi một hành động hoặc yêu cầu được xử lý. Luồng gọi trả lời câu hỏi: *khi người dùng thực hiện việc này, thành phần nào chạy trước, gọi thành phần nào tiếp theo, và kết quả quay về ra sao?*

 Xét yêu cầu HTTP tạo đơn hàng trong một ứng dụng Spring Boot:

1. `OrderController` nhận request, kiểm tra cấu trúc dữ liệu đầu vào ở ranh giới HTTP và chuyển dữ liệu thành đầu vào của ca sử dụng.
2. `PlaceOrderService` điều phối ca sử dụng, gọi mô hình miền để áp dụng quy tắc như số lượng phải lớn hơn không và tổng tiền phải được tính nhất quán.
3. Dịch vụ ứng dụng gọi hợp đồng `OrderStore` để lưu đơn hàng.
4. Đối tượng `JpaOrderStore` đang được Spring cung cấp thực hiện hợp đồng đó, chuyển dữ liệu sang mô hình lưu trữ và dùng Spring Data JPA để ghi vào cơ sở dữ liệu.
5. Kết quả được trả ngược qua dịch vụ ứng dụng tới controller; controller chuyển kết quả thành HTTP response.

 Luồng chạy có thể hình dung như sau:

 ```mermaid
 sequenceDiagram
     actor Client as Client
     participant C as OrderController
     participant A as PlaceOrderService
     participant I as JpaOrderStore
     participant J as Spring Data JPA
     database DB as Database

     Client->>C: POST /orders
     C->>A: placeOrder(command)
     A->>A: Áp dụng quy tắc miền
     A->>I: save(order) qua OrderStore
     Note over A,I: Mã ứng dụng chỉ biết interface; JVM dispatch tới bean JpaOrderStore
     I->>J: persist dữ liệu
     J->>DB: INSERT / UPDATE
     DB-->>J: Kết quả lưu
     J-->>I: Kết quả
     I-->>A: Hoàn tất
     A-->>C: OrderId
     C-->>Client: 201 Created
 ```

 Trong ví dụ này, mũi tên gọi lúc chạy đi từ dịch vụ ứng dụng tới adapter. Tuy nhiên, mã nguồn của `PlaceOrderService` chỉ biết interface `OrderStore`; nó không cần import hoặc khởi tạo `JpaOrderStore`. Spring tạo và tiêm bean phù hợp khi ứng dụng khởi động. Đây là lý do sơ đồ phụ thuộc mã nguồn và sơ đồ luồng gọi không nhất thiết có các mũi tên giống nhau.

 Một hợp đồng Java tối giản có thể được khai báo ở tầng ứng dụng:

 ```java
 // application/port/out/OrderStore.java
 public interface OrderStore {
     Optional<Order> findById(OrderId id);
     void save(Order order);
 }
 ```

 Dịch vụ ứng dụng chỉ tham chiếu hợp đồng:

 ```java
 @Service
 public class PlaceOrderService {
     private final OrderStore orderStore;

     public PlaceOrderService(OrderStore orderStore) {
         this.orderStore = orderStore;
     }

     // Điều phối ca sử dụng và gọi orderStore.save(order).
 }
 ```

 Adapter hạ tầng triển khai hợp đồng và dùng thư viện lưu trữ cụ thể:

 ```java
 @Repository
 class JpaOrderStore implements OrderStore {
     private final SpringDataOrderRepository repository;

     // Chuyển đổi mô hình và ủy quyền thao tác cho repository JPA.
 }
 ```

 Đây là các đoạn mã minh họa cấu trúc, không phải một ví dụ hoàn chỉnh có thể biên dịch nguyên trạng. Trong Spring, constructor injection cho phép container cung cấp bean triển khai `OrderStore`. Nếu có nhiều bean cùng triển khai một interface, cấu hình cần chỉ rõ bean được chọn, chẳng hạn bằng `@Qualifier` hoặc cấu hình tương ứng.

 Không phải luồng gọi nào cũng đồng bộ như ví dụ HTTP trên. Một thành phần có thể phát sự kiện hoặc gửi thông điệp để thành phần khác xử lý sau. Khi đó, luồng thực thi có thể bị chia thành nhiều tiến trình hoặc thời điểm; hợp đồng thông điệp và cách xử lý lỗi trở nên đặc biệt quan trọng.

 ## 6. Đọc các khái niệm cùng nhau

 Năm khái niệm liên kết với nhau nhưng trả lời các câu hỏi khác nhau:

 | Khái niệm | Câu hỏi cần trả lời | Dấu hiệu khi đọc dự án |
 | --- | --- | --- |
 | Tầng | Trách nhiệm này thuộc khu vực logic nào? | Quy tắc phân tầng, package hoặc module |
 | Thành phần | Đơn vị nào thực hiện trách nhiệm cụ thể? | Class, nhóm class, module hoặc adapter |
 | Hợp đồng | Hai bên thống nhất giao tiếp bằng cách nào? | Interface, API schema, DTO hoặc event schema cùng ngữ nghĩa của chúng |
 | Phụ thuộc | Mã nào cần biết hợp đồng hoặc kiểu của mã nào? | Import, kiểu tham chiếu, cấu hình và quy tắc phụ thuộc |
 | Luồng gọi | Một yêu cầu thực sự đi qua những thành phần nào lúc chạy? | Call stack, trace, sequence diagram hoặc log |

 Khi lần theo một yêu cầu, hãy xác định tầng chịu trách nhiệm, tìm thành phần thực hiện, đọc hợp đồng tại ranh giới, kiểm tra hướng phụ thuộc và cuối cùng lần theo luồng gọi lúc chạy. Cách đọc này giúp phát hiện những trường hợp một tầng đang ôm quá nhiều trách nhiệm, một thành phần biết quá nhiều chi tiết triển khai hoặc một luồng gọi đi vòng qua ranh giới đã định.

 ## 7. Kiểm thử và đánh đổi khi đặt ranh giới

 Hợp đồng và ranh giới thành phần tạo ra những điểm kiểm thử tự nhiên:

- Kiểm thử đơn vị cho mô hình miền xác nhận quy tắc nghiệp vụ mà không cần khởi động Spring hoặc cơ sở dữ liệu.
- Kiểm thử dịch vụ ứng dụng có thể truyền vào một `OrderStore` giả (fake) để xác nhận ca sử dụng điều phối đúng và yêu cầu lưu dữ liệu phù hợp.
- Kiểm thử tích hợp adapter xác nhận `JpaOrderStore` ánh xạ và truy vấn đúng với cơ sở dữ liệu.
- Kiểm thử controller xác nhận HTTP request/response tuân thủ hợp đồng API.

 Phân tầng rõ ràng thường giúp thay đổi một chi tiết ít lan sang phần khác, cho phép kiểm thử thành phần độc lập và làm cho trách nhiệm dễ tìm hơn. Đổi lại, nhiều ranh giới có thể tạo thêm interface, adapter, chuyển đổi DTO và mã chuyển tiếp. Nếu một lớp chỉ chuyển nguyên vẹn lời gọi mà không tạo ra trách nhiệm, quy tắc hay ranh giới hữu ích, nó có thể làm thiết kế nặng nề hơn.

 Hãy chọn mức phân tách phù hợp với độ phức tạp, tốc độ thay đổi và nhu cầu kiểm thử của hệ thống. Không có một số tầng tối ưu áp dụng cho mọi dự án; chất lượng nằm ở trách nhiệm rõ ràng, hợp đồng có ý nghĩa và phụ thuộc có chủ đích.

 ## Tự kiểm tra

 1. Một ứng dụng Spring Boot có controller, service, domain model và repository nhưng cùng chạy trong một JVM có thể có nhiều tầng logic và chỉ một tier ứng dụng hay không? Vì sao?
 2. `PlaceOrderService` giữ tham chiếu kiểu `OrderStore`, còn bean thực tế là `JpaOrderStore`. Phụ thuộc mã nguồn và lời gọi lúc chạy hướng tới đâu?
 3. Vì sao chữ ký `save(Order order)` chưa chắc đã mô tả đầy đủ hợp đồng của thao tác lưu?
 4. Nếu controller truy cập trực tiếp repository để hoàn tất một ca sử dụng, cần kiểm tra quy tắc kiến trúc nào trước khi chấp nhận cách làm đó?


# Phân biệt Bounded Context với miền con, mô-đun và dịch vụ triển khai

Khi thiết kế một hệ thống theo Domain-Driven Design (DDD), đội phát triển thường dùng nhiều loại ranh giới: miền con (*subdomain*), ngữ cảnh giới hạn (*Bounded Context*), mô-đun mã nguồn (*module*) và dịch vụ có thể triển khai độc lập (*deployable service*). Các ranh giới này có thể được tổ chức trùng nhau, nhưng chúng trả lời những câu hỏi khác nhau.

Nếu xem chúng là một, đội phát triển dễ chia hệ thống theo cấu trúc tổ chức hoặc công nghệ trước khi hiểu nghiệp vụ. Chẳng hạn, một nhóm có thể tạo một microservice cho mỗi bảng dữ liệu, gọi mỗi nhóm chức năng là một subdomain, hoặc giả định rằng hai phần mềm chạy trong cùng một tiến trình phải dùng chung một mô hình domain. Những quyết định như vậy thường làm ranh giới nghiệp vụ trở nên mơ hồ.

DDD giúp phân biệt các khái niệm theo mục đích:

- **Domain và subdomain** mô tả bài toán nghiệp vụ và cách chia bài toán thành những lĩnh vực nhỏ hơn.
- **Bounded Context** xác định phạm vi mà một mô hình domain và ngôn ngữ chung có ý nghĩa nhất quán.
- **Module** tổ chức mã nguồn và kiểm soát sự phụ thuộc bên trong giải pháp.
- **Deployable service** xác định đơn vị phần mềm được đóng gói, triển khai và vận hành như một tiến trình hoặc dịch vụ độc lập.

Sau bài học này, bạn có thể giải thích mỗi ranh giới thuộc về góc nhìn nào, nhận diện mối quan hệ giữa chúng và chọn cách ánh xạ phù hợp cho một hệ thống cụ thể.

## 1. Bốn khái niệm, bốn câu hỏi khác nhau

Hãy bắt đầu bằng bốn câu hỏi:

1. **Subdomain:** Doanh nghiệp cần thực hiện năng lực nghiệp vụ nào để hoạt động?
2. **Bounded Context:** Trong phạm vi nào các thuật ngữ và mô hình cần giữ một ý nghĩa thống nhất?
3. **Module:** Mã nguồn được chia thành những phần nào để mỗi phần có trách nhiệm rõ và hạn chế phụ thuộc không mong muốn?
4. **Deployable service:** Phần mềm nào được đóng gói, phát hành, mở rộng và vận hành như một đơn vị riêng?

| Khái niệm | Thuộc góc nhìn | Ranh giới bảo vệ điều gì? | Ví dụ |
|---|---|---|---|
| Subdomain (Miền con) | Phân tích nghiệp vụ | Một phần bài toán hoặc năng lực nghiệp vụ | Quản lý danh mục, bán hàng, thanh toán, thực hiện giao hàng |
| Bounded Context | Mô hình hóa domain | Tính nhất quán của mô hình và ngôn ngữ chung | Sales Context có định nghĩa riêng về Order |
| Module (Mô-đun) | Tổ chức mã nguồn | Tính đóng gói, trách nhiệm và phụ thuộc giữa các phần code | Java module hoặc package `sales` |
| Deployable service | Kiến trúc triển khai và vận hành | Đơn vị phát hành, chạy, mở rộng và giám sát | Ứng dụng `sales-service` được triển khai độc lập |

Các ranh giới này có thể liên hệ với nhau. Một subdomain có thể được mô hình hóa bằng một Bounded Context; Bounded Context đó có thể được triển khai thành một module; module có thể nằm trong một deployable service. Đây là một cách ánh xạ thường gặp, không phải quy tắc bắt buộc.

## 2. Domain và subdomain: chia bài toán nghiệp vụ

### Domain là gì?

*Domain* là lĩnh vực nghiệp vụ mà tổ chức đang hoạt động hoặc phần vấn đề mà phần mềm cần hỗ trợ. Ví dụ, với một doanh nghiệp thương mại điện tử, domain có thể bao gồm việc giới thiệu hàng hóa, tiếp nhận đơn mua, thu tiền, quản lý tồn kho và giao hàng.

Domain không phải tên của một ứng dụng, một cơ sở dữ liệu hay một nhóm microservice. Nó mô tả thế giới nghiệp vụ mà đội phát triển cần hiểu. Khi domain được làm rõ, đội có thể xác định các năng lực, quy tắc và thuật ngữ quan trọng.

### Subdomain là gì?

*Subdomain* là một phần của domain, thường được nhận diện theo một nhóm vấn đề hoặc năng lực nghiệp vụ có ý nghĩa riêng. Chia domain thành các subdomain giúp đội phát triển hiểu phạm vi công việc, ưu tiên đầu tư và nhận ra phần nào tạo ra giá trị khác biệt.

Trong DDD, subdomain thường được phân thành ba nhóm:

- **Core Subdomain (Miền con cốt lõi):** Năng lực tạo lợi thế cạnh tranh hoặc giá trị khác biệt quan trọng của doanh nghiệp. Đây thường là nơi cần đầu tư hiểu biết nghiệp vụ và mô hình hóa sâu.
- **Supporting Subdomain (Miền con hỗ trợ):** Năng lực cần thiết để vận hành doanh nghiệp nhưng không phải yếu tố tạo khác biệt chính. Có thể phát triển nội bộ hoặc dùng giải pháp phù hợp với chi phí hợp lý.
- **Generic Subdomain (Miền con tổng quát):** Năng lực phổ biến ở nhiều doanh nghiệp, chẳng hạn xác thực người dùng hoặc gửi email. Có thể cân nhắc mua, dùng dịch vụ có sẵn hoặc tái sử dụng giải pháp tiêu chuẩn.

Phân loại này phụ thuộc chiến lược của từng doanh nghiệp. Ví dụ, thanh toán có thể là năng lực hỗ trợ trong một cửa hàng trực tuyến, nhưng lại là core subdomain đối với một công ty chuyên cung cấp nền tảng thanh toán. Không thể phân loại chỉ dựa vào tên chức năng.

### Ví dụ phân rã domain thương mại điện tử

| Subdomain minh họa | Năng lực nghiệp vụ | Vai trò có thể có |
|---|---|---|
| Product Catalog | Quản lý thông tin, thuộc tính và cách giới thiệu sản phẩm | Supporting |
| Sales | Tiếp nhận đơn, áp dụng chính sách bán và quyết định chấp nhận đơn | Có thể là Core |
| Payment | Thu tiền, ghi nhận giao dịch và hoàn tiền | Supporting hoặc Core tùy mô hình kinh doanh |
| Inventory | Quản lý số lượng có thể bán và tồn kho | Có thể là Core nếu năng lực tối ưu tồn kho tạo lợi thế |
| Fulfillment | Chuẩn bị hàng, điều phối kho và giao hàng | Supporting hoặc Core tùy cam kết dịch vụ |
| Identity | Xác thực và quản lý danh tính người dùng | Thường là Generic |

Danh sách này là ví dụ phân tích nghiệp vụ. Nó chưa quyết định mỗi phần phải là một ứng dụng, một module hay một microservice. Đó là các quyết định thiết kế tiếp theo.

## 3. Bounded Context: ranh giới của mô hình và ngôn ngữ

### Bounded Context là gì?

*Bounded Context* là ranh giới mà bên trong đó một mô hình domain cụ thể được định nghĩa và sử dụng nhất quán. Các thuật ngữ, quy tắc và đối tượng trong mô hình có ý nghĩa rõ ràng trong phạm vi này. Khi ra ngoài ranh giới, cùng một từ có thể mang ý nghĩa khác hoặc cần được chuyển đổi sang mô hình khác.

Ví dụ, từ `Product` có thể được hiểu khác nhau:

- Trong **Product Catalog Context**, Product là mặt hàng được mô tả để khách tìm kiếm và xem thông tin.
- Trong **Sales Context**, thông tin sản phẩm trên Order Line có thể là bản chụp tên, giá và thuộc tính đã chốt tại thời điểm mua.
- Trong **Inventory Context**, hệ thống quan tâm đến đơn vị hàng hóa, mã SKU và số lượng tồn có thể bán.

Những cách hiểu này liên quan với nhau nhưng phục vụ các quy tắc khác nhau. Bounded Context giúp nhóm giữ mô hình phù hợp với trách nhiệm của mình thay vì cố tạo một lớp `Product` duy nhất cho mọi nhu cầu.

Một Bounded Context không đơn giản là một folder, một database schema hay một microservice. Nó là ranh giới ngữ nghĩa của mô hình. Mã nguồn, dữ liệu và dịch vụ có thể được tổ chức để hỗ trợ ranh giới đó, nhưng bản thân các thành phần kỹ thuật không tự định nghĩa ý nghĩa domain.

### Subdomain và Bounded Context khác nhau thế nào?

Hai khái niệm này thường được đặt cạnh nhau vì chúng có thể được ánh xạ với nhau, nhưng chúng xuất phát từ hai góc nhìn:

| Tiêu chí | Subdomain | Bounded Context |
|---|---|---|
| Góc nhìn | Problem space (không gian vấn đề) | Solution/model space (không gian mô hình giải pháp) |
| Mục đích | Hiểu và chia nhỏ domain nghiệp vụ | Xác định nơi mô hình và ngôn ngữ có hiệu lực |
| Câu hỏi | Doanh nghiệp cần năng lực gì? | Mô hình nào được dùng nhất quán trong phạm vi nào? |
| Cách nhận diện | Quy trình, năng lực, mục tiêu và quy tắc nghiệp vụ | Thuật ngữ, mô hình, trách nhiệm và ranh giới nhất quán |
| Ví dụ | Sales là một subdomain | Sales Context là mô hình cụ thể dùng để xử lý bán hàng |

Một subdomain thường là điểm khởi đầu tốt để tìm Bounded Context tương ứng. Tuy nhiên, không có quy tắc một subdomain luôn bằng đúng một Bounded Context. Một subdomain có thể cần nhiều context nếu các nhóm quy tắc hoặc mô hình trong đó khác nhau đáng kể. Ngược lại, một context có thể bao quát các năng lực liên quan nếu chúng thực sự dùng chung một mô hình và ngôn ngữ nhất quán.

Ví dụ, năng lực bán hàng có thể được phân tích thành các phần như quản lý giỏ hàng, đặt hàng và chính sách khuyến mại. Nếu các phần này có thuật ngữ, quy tắc và vòng đời khác nhau, đội có thể cân nhắc các Bounded Context riêng. Nếu chúng cùng thuộc một mô hình bán hàng gắn kết, một Sales Context có thể là lựa chọn hợp lý. Quyết định cần dựa trên hiểu biết domain và chi phí duy trì ranh giới.

### Bounded Context và Ubiquitous Language

Ngôn ngữ chung (*Ubiquitous Language*) là ngôn ngữ mà chuyên gia nghiệp vụ và đội phát triển cùng sử dụng trong một Bounded Context. Một thuật ngữ có định nghĩa rõ trong context đó; nó được dùng trong trao đổi, tài liệu, mô hình và mã nguồn.

Khi một nhóm nói “Order đã được xác nhận”, các thành viên cần hiểu cùng một sự kiện và điều kiện. Nếu Sales dùng “Order” để chỉ cam kết mua bán nhưng Fulfillment dùng nó để chỉ yêu cầu lấy hàng, hai nhóm đang nói về hai mô hình khác nhau. Context boundary cho phép mỗi nhóm giữ cách hiểu phù hợp, còn cơ chế tích hợp sẽ chuyển thông tin giữa chúng.

## 4. Module: ranh giới tổ chức mã nguồn

*Module* là một đơn vị tổ chức mã nguồn. Module gom các thành phần liên quan, cung cấp giao diện cần thiết và giới hạn cách các phần khác phụ thuộc vào nó. Tùy nền tảng, module có thể là Java module, Gradle subproject, package, assembly hoặc một cấu trúc tương tự.

Ví dụ một ứng dụng Java có thể được tổ chức như sau:

```text
shop-app/
  catalog/
    Product.java
    CatalogQueryService.java
  sales/
    Order.java
    OrderLine.java
    OrderPolicy.java
  payment/
    Payment.java
    Refund.java
  fulfillment/
    FulfillmentOrder.java
    Shipment.java
```

Các thư mục trên có thể đại diện cho những module tương ứng với các Bounded Context. Module `sales` sở hữu mô hình Order của Sales; module `fulfillment` sở hữu mô hình Fulfillment Order và Shipment của Fulfillment.

Module giúp thực thi ranh giới trong mã nguồn: kiểm soát dependency, giới hạn truy cập vào chi tiết nội bộ và xác định API mà module khác được phép sử dụng. Nhưng chỉ tạo package hoặc folder chưa đủ để có module boundary thực chất. Nếu mọi phần đều truy cập trực tiếp vào class nội bộ của nhau, ranh giới mới chỉ mang tính hình thức.

### Module và Bounded Context khác nhau thế nào?

| Tiêu chí | Bounded Context | Module |
|---|---|---|
| Bản chất | Ranh giới ngữ nghĩa của mô hình domain | Ranh giới tổ chức và đóng gói mã nguồn |
| Mục tiêu | Bảo vệ ý nghĩa của thuật ngữ và quy tắc | Quản lý cấu trúc code và dependency |
| Có thể tồn tại không có code? | Có thể được xác định trong phân tích và thiết kế trước khi triển khai | Thường được hiện thực bằng cấu trúc mã nguồn hoặc artifact |
| Có cần triển khai riêng? | Không | Không |
| Ví dụ | Sales Context có mô hình Order riêng | Java module `sales` chứa mã nguồn của Sales |

Một Bounded Context có thể được hiện thực bằng một module lớn, hoặc nhiều module kỹ thuật bên trong. Ví dụ, Sales Context có thể chia thành `sales-domain`, `sales-application` và `sales-adapter` nhưng vẫn dùng chung một ngôn ngữ và mô hình Sales. Việc chia module theo lớp kiến trúc không tự tạo ra ba Bounded Context.

Ngược lại, một module kỹ thuật cũng có thể chứa mã của nhiều context nếu tổ chức chọn cách đóng gói như vậy. Điều đó đòi hỏi ranh giới mô hình vẫn rõ, các thành phần không dùng nhầm kiểu dữ liệu hoặc quy tắc của context khác.

## 5. Deployable service: ranh giới triển khai và vận hành

Trong bài này, *service* có nghĩa là một đơn vị phần mềm có thể đóng gói, triển khai và vận hành độc lập, thường chạy như một tiến trình hoặc nhóm tiến trình. Ví dụ: `sales-service`, `payment-service` hoặc `fulfillment-service`.

Một deployable service có thể có:

- Artifact và quy trình phát hành riêng.
- Cấu hình, tài nguyên và cơ chế mở rộng riêng.
- Endpoint hoặc kênh giao tiếp để thành phần khác sử dụng.
- Giám sát, log, cảnh báo và chính sách vận hành riêng.

Ranh giới service phục vụ các quyết định về triển khai, quy mô tải, độ tin cậy, quyền sở hữu và vận hành. Nó có thể được đặt trùng với Bounded Context để một nhóm sở hữu và phát hành mô hình của mình độc lập. Tuy nhiên, một service không tự động là một Bounded Context.

### Bounded Context và deployable service khác nhau thế nào?

| Tiêu chí | Bounded Context | Deployable service |
|---|---|---|
| Bản chất | Ranh giới của mô hình và ngôn ngữ | Ranh giới đóng gói và vận hành |
| Câu hỏi | Quy tắc và thuật ngữ nào thuộc mô hình này? | Phần mềm nào được triển khai và mở rộng như một đơn vị? |
| Có phụ thuộc công nghệ không? | Không bắt buộc | Có, gắn với nền tảng triển khai và vận hành |
| Quan hệ dữ liệu | Xác định quyền sở hữu và ý nghĩa dữ liệu theo mô hình | Có thể dùng database riêng, schema riêng hoặc cơ chế lưu trữ khác |
| Ví dụ | Payment Context định nghĩa Payment và Refund | `payment-service` chạy và phát hành độc lập |

### Một Bounded Context có nhất thiết là một microservice?

Không. Có nhiều cách triển khai một Bounded Context:

**Modular monolith:** Nhiều Bounded Context nằm trong một ứng dụng được triển khai cùng nhau, nhưng mỗi context có module, mô hình và giao diện nội bộ rõ ràng. Đây thường là lựa chọn phù hợp khi đội còn nhỏ, cần giao dịch trong cùng tiến trình hoặc chưa có lý do vận hành để tách dịch vụ.

**Một context tương ứng một service:** Mỗi Bounded Context được đóng gói thành một deployable service. Cách này tạo ranh giới triển khai gần với ranh giới mô hình, hỗ trợ quyền sở hữu và mở rộng độc lập khi lợi ích đủ lớn.

**Một service chứa nhiều context:** Vì lý do vận hành, chi phí hoặc quy mô đội, một deployable service có thể chứa nhiều Bounded Context. Khi đó cần giữ mô hình và ngôn ngữ riêng trong từng context, đồng thời kiểm soát việc gọi qua lại để không tạo ra một mô hình pha trộn.

**Một context có nhiều thành phần triển khai:** Một Bounded Context đôi khi cần nhiều tiến trình hoặc thành phần kỹ thuật, chẳng hạn API, worker xử lý nền và bộ dựng read model. Việc tách các thành phần này không tự tạo thêm Bounded Context nếu chúng vẫn thực thi cùng một mô hình domain. Cần xác định rõ thành phần nào sở hữu quyết định và dữ liệu domain.

Vì vậy, số lượng microservice không phải cách đo số lượng Bounded Context. Việc tách service nên có lý do rõ ràng như nhu cầu mở rộng độc lập, yêu cầu độ tin cậy, chu kỳ phát hành, quyền sở hữu của nhóm hoặc giới hạn công nghệ.

> Lưu ý về thuật ngữ: *Domain Service* trong tactical DDD là một khái niệm nghiệp vụ biểu diễn hành vi không phù hợp tự nhiên với một Entity hay Value Object. Nó không đồng nghĩa với một deployable service hoặc microservice.

## 6. Mối quan hệ giữa các ranh giới qua ví dụ

Giả sử một doanh nghiệp bán hàng trực tuyến. Sau khi phân tích domain, nhóm nhận diện các subdomain: Product Catalog, Sales, Payment, Inventory và Fulfillment. Từ đó, nhóm khám phá mô hình và quyết định các Bounded Context phù hợp.

| Subdomain (problem space) | Bounded Context (model space) | Module mã nguồn minh họa | Deployable service minh họa |
|---|---|---|---|
| Product Catalog | Catalog Context | `catalog` | `shop-core` |
| Sales | Sales Context | `sales` | `shop-core` |
| Payment | Payment Context | `payment` | `payment-service` |
| Inventory | Inventory Context | `inventory` | `shop-core` |
| Fulfillment | Fulfillment Context | `fulfillment` | `fulfillment-service` |

Bảng này minh họa một lựa chọn kiến trúc: Catalog, Sales và Inventory là các module độc lập về mã nguồn nhưng cùng nằm trong deployable service `shop-core`; Payment và Fulfillment được triển khai riêng. Mỗi context vẫn giữ mô hình và ngôn ngữ riêng dù cùng tiến trình hoặc cùng artifact.

Luồng nghiệp vụ có thể diễn ra như sau:

```text
Khách đặt hàng
    |
    v
Sales Context
  Chấp nhận Order
  Phát OrderPlaced
    |
    +-----------------------> Payment Context
    |                           Tạo Payment
    |                           Xử lý thu tiền
    |
    +-----------------------> Fulfillment Context
                                Tạo yêu cầu thực hiện
                                Chuẩn bị và giao hàng
```

Sơ đồ chỉ mô tả quan hệ nghiệp vụ ở mức khái niệm. Trong hệ thống thật, nhóm cần xác định thời điểm Fulfillment được phép chuẩn bị hàng, liệu có cần đợi thanh toán thành công hay có quy trình khác, và cách xử lý khi thanh toán thất bại. Các quyết định đó thuộc quy tắc domain và hợp đồng giữa context.

Ví dụ, `Order` trong Sales là cam kết mua bán. Payment có thể lưu một tham chiếu đến Order cùng số tiền cần thu; Fulfillment có thể tạo `FulfillmentOrder` từ các dòng hàng và địa chỉ đã chốt. Payment không cần dùng chính class `Order` của Sales, và Fulfillment cũng không cần biến `FulfillmentOrder` thành cùng một đối tượng. Mỗi context diễn giải dữ liệu nhận được theo mô hình của mình.

## 7. Context Map không phải sơ đồ module hay sơ đồ triển khai

Khi đã xác định các Bounded Context, đội cần hiểu chúng liên hệ với nhau như thế nào. *Context Map* mô tả các mối quan hệ và cách phối hợp giữa các context, ví dụ quan hệ upstream/downstream, Customer-Supplier, Conformist, Anti-Corruption Layer hoặc Shared Kernel.

Context Map giúp trả lời:

- Context nào cung cấp mô hình hoặc dữ liệu cho context nào?
- Context nhận có phụ thuộc vào mô hình của context gửi không?
- Có cần lớp chuyển đổi để bảo vệ mô hình nội bộ không?
- Hai nhóm thống nhất thay đổi hợp đồng như thế nào?

Sơ đồ triển khai trả lời một nhóm câu hỏi khác:

- Service nào chạy trên máy chủ hoặc nền tảng nào?
- Thành phần nào giao tiếp qua HTTP, message broker hay giao thức khác?
- Database và tài nguyên vận hành được bố trí ra sao?

Hai sơ đồ có thể tham chiếu nhau nhưng không thay thế nhau. Một đường kết nối giữa hai Bounded Context trong Context Map không bắt buộc phải là một HTTP call. Chúng có thể trao đổi qua event, batch, message hoặc thậm chí cùng tiến trình. Ngược lại, hai service có thể gọi nhau vì lý do kỹ thuật nhưng không nhất thiết là hai Bounded Context khác nhau.

## 8. Cách chọn và kiểm chứng ranh giới

Khi bắt đầu thiết kế, hãy đi từ hiểu biết nghiệp vụ đến mô hình rồi mới quyết định cách tổ chức code và triển khai.

### Bước 1: Phân tích domain và nhận diện subdomain

Liệt kê năng lực nghiệp vụ, quy tắc và mục tiêu của tổ chức. Hỏi phần nào tạo ra khác biệt cạnh tranh, phần nào hỗ trợ vận hành và phần nào là năng lực phổ biến có thể dùng giải pháp tiêu chuẩn.

### Bước 2: Tìm các mô hình và ngôn ngữ cần nhất quán

Trao đổi với chuyên gia nghiệp vụ, thu thập thuật ngữ, sự kiện, chính sách và quy trình. Tìm những nơi cùng một từ có nghĩa khác nhau hoặc các nhóm phải áp dụng quy tắc khác nhau. Những khác biệt có ý nghĩa có thể là dấu hiệu cần Bounded Context riêng.

### Bước 3: Xác định Bounded Context và quyền sở hữu

Mô tả rõ context chịu trách nhiệm về quyết định nào, mô hình nào và dữ liệu nào. Xác định các thuật ngữ chính và cách context giao tiếp với phần còn lại. Không tạo context mới chỉ vì có một bảng dữ liệu hoặc một endpoint mới.

### Bước 4: Chọn module để thực thi ranh giới trong code

Tạo module hoặc package phản ánh trách nhiệm. Định nghĩa giao diện công khai, hạn chế truy cập chi tiết nội bộ và quản lý dependency. Nếu hai context cùng nằm trong một module, cần cân nhắc liệu cấu trúc đó có làm các mô hình bị trộn lẫn hay không.

### Bước 5: Quyết định cách triển khai service

Đánh giá quy mô tải, yêu cầu sẵn sàng, bảo mật, chu kỳ phát hành, quyền sở hữu của nhóm và chi phí vận hành. Bắt đầu bằng cấu trúc đơn giản đủ đáp ứng yêu cầu; tách deployable service khi có lợi ích cụ thể và có thể quản lý chi phí giao tiếp phân tán.

### Bước 6: Kiểm chứng bằng tình huống thay đổi

Thử một số thay đổi nghiệp vụ và xem ranh giới có giúp kiểm soát ảnh hưởng không. Ví dụ:

- Chính sách giá thay đổi có buộc nhóm kho vận sửa mã không?
- Cách tính số tiền hoàn thay đổi có làm ảnh hưởng trực tiếp đến mô hình Order không?
- Tăng tải tra cứu catalog có cần phát hành lại phần xử lý thanh toán không?
- Một thuật ngữ được đổi nghĩa trong Sales có khiến Fulfillment hiểu sai thông điệp đã nhận không?

Nếu thay đổi nhỏ ở một năng lực thường xuyên làm ảnh hưởng nhiều phần không liên quan, ranh giới hiện tại có thể chưa tốt. Tuy nhiên, không phải mọi thay đổi liên thành phần đều là dấu hiệu sai: các context vẫn có thể cần phối hợp theo hợp đồng rõ ràng.

## 9. Các nhầm lẫn thường gặp

**Xem subdomain là microservice.** Subdomain là phần của bài toán nghiệp vụ. Nó có thể được hỗ trợ bởi một hoặc nhiều Bounded Context và có thể được triển khai theo nhiều cách.

**Xem Bounded Context là một database hoặc schema.** Database/schema là lựa chọn lưu trữ. Ranh giới mô hình còn bao gồm ngôn ngữ, quy tắc và quyền sở hữu. Hai schema khác nhau không tự chứng minh có hai context; một database chung cũng không chứng minh chỉ có một context.

**Xem mỗi module là một Bounded Context.** Module là cách tổ chức code. Nhiều module có thể thuộc cùng một context; một module có thể chứa nhiều context nếu thiết kế cho phép. Cần đánh giá ý nghĩa của mô hình chứ không chỉ nhìn folder.

**Xem mỗi microservice là một Bounded Context.** Service là đơn vị triển khai. Có thể ánh xạ một-một khi phù hợp, nhưng không phải định nghĩa của Bounded Context.

**Chia service theo từng Entity hoặc bảng dữ liệu.** Một Entity không đại diện cho toàn bộ năng lực nghiệp vụ. Tách service chỉ vì một bảng có thể tạo ra nhiều lời gọi mạng và quy trình phân tán mà không đem lại ranh giới domain tốt hơn.

**Ép mọi context dùng chung một mô hình.** Một mô hình thống nhất toàn hệ thống có thể làm mất các khác biệt nghiệp vụ quan trọng. Hãy giữ mô hình phù hợp trong từng context và xác định cách chuyển đổi ở ranh giới.

**Tách quá nhiều quá sớm.** Mỗi deployable service tạo thêm chi phí triển khai, giám sát, giao tiếp, xử lý lỗi và quản lý dữ liệu phân tán. Có thể bắt đầu bằng modular monolith với ranh giới context rõ rồi tách khi có lý do thực tế.

## 10. Bài tập tự kiểm tra

Một nền tảng đặt lịch khám có các năng lực: tìm bác sĩ, đặt lịch, thu phí khám, tiếp nhận bệnh nhân và quản lý kết quả xét nghiệm. Đội phát triển đề xuất tạo năm microservice tương ứng với năm năng lực.

Hãy trả lời:

1. Năm năng lực trên có thể là năm subdomain không? Cần thêm thông tin nào để phân loại core, supporting và generic?
2. Trong quy trình đặt lịch, từ “Bệnh nhân” có thể mang ý nghĩa gì với Booking, Billing và Clinic Operations?
3. Những khác biệt nào cho thấy cần một Bounded Context riêng?
4. Có thể tổ chức các Bounded Context thành các module trong một modular monolith không? Điều kiện nào giúp cách tổ chức đó vẫn giữ được ranh giới?
5. Lý do nào đủ mạnh để tách một module thành deployable service?

Gợi ý:

- Có thể xem các năng lực là những ứng viên subdomain, nhưng cần hiểu mục tiêu kinh doanh và quy tắc để xác định phân loại. Không thể kết luận tất cả đều là core chỉ từ tên chức năng.
- Booking có thể quan tâm người được đặt lịch; Billing quan tâm bên chịu nghĩa vụ thanh toán; Clinic Operations quan tâm hồ sơ và người đang được tiếp nhận. Cần xác nhận cách hiểu trong từng tổ chức.
- Nếu mô hình, ngôn ngữ và quy tắc khác nhau đáng kể, hãy cân nhắc các Bounded Context riêng.
- Modular monolith vẫn phù hợp nếu module có giao diện rõ, kiểm soát dependency và không truy cập tùy tiện vào nội bộ của context khác.
- Tách service khi có nhu cầu vận hành cụ thể như mở rộng độc lập, yêu cầu sẵn sàng, quyền sở hữu hoặc chu kỳ phát hành khác biệt, đồng thời đội có khả năng quản lý giao tiếp phân tán.

## Kết luận

Subdomain chia domain theo năng lực và vấn đề nghiệp vụ. Bounded Context xác định nơi một mô hình và ngôn ngữ chung có ý nghĩa nhất quán. Module tổ chức mã nguồn để kiểm soát trách nhiệm và phụ thuộc. Deployable service xác định đơn vị phần mềm được phát hành và vận hành độc lập.

Các ranh giới này nên hỗ trợ lẫn nhau nhưng không cần trùng khít. Hãy hiểu bài toán và mô hình trước, sau đó chọn cấu trúc code và cách triển khai phù hợp với nhu cầu thực tế. Khi mỗi ranh giới có mục đích rõ ràng, hệ thống dễ thay đổi hơn và các nhóm có thể phối hợp mà không làm mất ý nghĩa của domain.

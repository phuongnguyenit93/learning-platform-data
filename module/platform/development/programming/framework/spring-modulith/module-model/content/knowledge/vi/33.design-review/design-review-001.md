# Xác định module boundary từ trách nhiệm nghiệp vụ

Một module tốt gom những quy tắc nghiệp vụ và dữ liệu thường thay đổi cùng nhau, đồng thời giới hạn cách các phần khác của ứng dụng sử dụng chúng. Khi review thiết kế, hãy bắt đầu từ trách nhiệm nghiệp vụ, quyền sở hữu invariant và các quyết định mà một nhóm code phải bảo vệ. Sau đó mới ánh xạ các trách nhiệm ấy thành package, public API và dependency rule của Spring Modulith.

Nếu bắt đầu từ controller, service, repository hoặc entity, nhóm rất dễ tạo ra module theo tầng kỹ thuật. Những package như web, service và persistence có thể giúp tổ chức code bên trong một module, nhưng chúng thường không đại diện cho capability mà doanh nghiệp nhận diện được. Mục tiêu của review là tìm ra các ranh giới có ý nghĩa với nghiệp vụ và có thể được kiểm chứng trong code.

Sau bài học, bạn có thể:

- Phân tích capability và trách nhiệm nghiệp vụ để tìm module candidate.
- Xác định module sở hữu dữ liệu, invariant và vòng đời của từng khái niệm.
- Đánh giá cohesion, coupling và lý do thay đổi giữa các nhóm code.
- Phân biệt module nghiệp vụ với package kỹ thuật, shared utility và deployment service.
- Chọn public API, named interface và event contract phù hợp.
- Đọc dependency graph và nhận diện nguy cơ phụ thuộc vòng.
- Sử dụng Spring Modulith để biến quyết định thiết kế thành quy tắc có thể kiểm tra.
- Viết kết luận review gồm ranh giới, lý do, rủi ro và các quyết định còn mở.

## 1. Bắt đầu từ trách nhiệm và kết quả nghiệp vụ

Một module candidate nên mô tả được bằng một câu nói về trách nhiệm. Câu đó phải diễn đạt một kết quả hoặc một nhóm quy tắc nghiệp vụ mà hệ thống cần bảo vệ.

Ví dụ:

| Mô tả trách nhiệm | Module candidate |
|---|---|
| Quản lý thông tin sản phẩm được phép bán và giá niêm yết | catalog |
| Quản lý hồ sơ khách hàng và thông tin liên hệ | customer |
| Tiếp nhận đơn, tính tổng tiền và quản lý vòng đời đơn hàng | orders |
| Theo dõi số lượng có thể bán và giữ hàng cho đơn | inventory |
| Khởi tạo, xác nhận và hoàn tiền giao dịch | payment |

Các mô tả sau chưa đủ để xác định module:

- Xử lý HTTP request.
- Gọi database.
- Chứa các lớp service.
- Chuyển đổi JSON.
- Dùng chung một thư viện.

Đó là trách nhiệm kỹ thuật. Chúng có thể xuất hiện ở nhiều module và thường nên nằm bên trong module nghiệp vụ tương ứng.

Hãy hỏi: nếu capability này thay đổi quy tắc, ai chịu trách nhiệm sửa? Ai quyết định dữ liệu nào hợp lệ? Ai bảo vệ invariant khi dữ liệu được tạo hoặc cập nhật? Những câu trả lời này thường chỉ ra nơi nên đặt module boundary.

## 2. Thu thập bằng chứng trước khi vẽ package

Một design review đáng tin cậy cần bằng chứng từ cách doanh nghiệp vận hành và cách code hiện tại được thay đổi. Đừng kết luận ranh giới chỉ từ tên class hoặc số lượng file.

### Bằng chứng từ nghiệp vụ

Thu thập:

- Quy trình từ lúc bắt đầu đến khi hoàn thành một nghiệp vụ.
- Các quyết định nghiệp vụ và điều kiện hợp lệ.
- Các thuật ngữ được người dùng, chuyên gia nghiệp vụ và đội phát triển sử dụng.
- Các trường hợp ngoại lệ, hủy, sửa, hoàn tiền hoặc xử lý lại.
- Những thay đổi thường được yêu cầu cùng nhau.

Ví dụ, việc đặt hàng có thể cần tra cứu sản phẩm, kiểm tra khách hàng, tạo đơn, giữ hàng và thanh toán. Đây là một quy trình xuyên qua nhiều capability. Việc cùng xuất hiện trong một quy trình không có nghĩa tất cả phải nằm trong một module. Hãy xem mỗi capability có quy tắc và dữ liệu riêng hay không.

### Bằng chứng từ code và lịch sử thay đổi

Quan sát:

- Các lớp thường được sửa trong cùng một thay đổi.
- Các test thường thất bại cùng nhau sau một thay đổi.
- Những package được import trực tiếp từ nhiều khu vực.
- Các repository hoặc entity được nhiều nhóm code cùng ghi.
- Các service chứa nhiều nhánh điều kiện cho nhiều nghiệp vụ khác nhau.
- Những thay đổi nhỏ phải sửa nhiều package hoặc nhiều bảng không liên quan.

Lịch sử commit và pull request có thể cho biết code nào thay đổi cùng nhau. Tuy nhiên, tương quan trong lịch sử không tự chứng minh hai phần phải ở cùng module; có thể chúng đang bị ghép chặt do thiết kế hiện tại. Hãy kết hợp bằng chứng lịch sử với invariant và quyền sở hữu dữ liệu.

### Bằng chứng từ vận hành

Tìm hiểu:

- Các thao tác nào cần cùng một transaction để bảo vệ invariant?
- Các bước nào có thể hoàn tất bất đồng bộ?
- Khi một bước thất bại, hệ thống cần retry, bù trừ hay yêu cầu người vận hành xử lý?
- Dữ liệu nào cần có vòng đời, retention hoặc quyền truy cập riêng?
- Những thay đổi nào cần được triển khai hoặc kiểm soát độc lập?

Các câu trả lời này không quyết định module boundary một cách máy móc, nhưng giúp đánh giá liệu một ranh giới có phù hợp với consistency và ownership hay không.

## 3. Tìm module candidate bằng capability và invariant

Capability là khả năng nghiệp vụ mà hệ thống cung cấp. Một capability có thể được thực hiện bởi nhiều use case và nhiều loại adapter. Module thường là nơi gom các quy tắc và dữ liệu cần thiết để thực hiện một capability hoặc một phần capability có ownership rõ ràng.

Invariant là điều kiện phải luôn đúng đối với trạng thái nghiệp vụ. Ví dụ:

- Một đơn hàng đã xác nhận phải có ít nhất một dòng hàng.
- Tổng tiền đơn hàng phải được tính từ các dòng hàng và quy tắc giá đã áp dụng.
- Một reservation không được giữ nhiều hàng hơn số lượng có thể bán.
- Một payment attempt đã captured không được captured lần thứ hai.
- Một khách hàng đã bị khóa không được dùng cho một giao dịch mới nếu chính sách yêu cầu chặn.

Hãy gán mỗi invariant cho nơi có đủ thông tin và quyền kiểm soát để bảo vệ nó. Nếu nhiều module cùng ghi một trạng thái mà không có chủ sở hữu rõ ràng, ranh giới đang có vấn đề.

Ví dụ:

| Invariant | Chủ sở hữu phù hợp | Lý do |
|---|---|---|
| Giá niêm yết và trạng thái sản phẩm hợp lệ | catalog | Catalog quản lý vòng đời sản phẩm |
| Tổng tiền và trạng thái đơn hàng nhất quán | orders | Orders sở hữu Order và các dòng hàng |
| Không giữ vượt quá tồn kho khả dụng | inventory | Inventory sở hữu stock và reservation |
| Một giao dịch thanh toán không bị ghi nhận thành công hai lần | payment | Payment sở hữu payment attempt và trạng thái giao dịch |
| Email và trạng thái hồ sơ khách hàng hợp lệ | customer | Customer sở hữu hồ sơ và quy tắc cập nhật |

Nếu một quy tắc đòi hỏi hai module cùng ghi dữ liệu trong một transaction thường xuyên, hãy xem lại ownership. Có thể ranh giới đang chia một invariant thành hai phần. Cũng có thể quy trình thực sự trải qua nhiều capability và cần một workflow với consistency model rõ ràng. Hai trường hợp này cần cách thiết kế khác nhau.

## 4. Đánh giá cohesion và lý do thay đổi

Cohesion mô tả mức độ các phần tử trong module cùng phục vụ một trách nhiệm. Một module có cohesion tốt thường có:

- Một nhóm thuật ngữ nghiệp vụ nhất quán.
- Một tập invariant có chủ sở hữu rõ ràng.
- Dữ liệu được tạo, cập nhật và kiểm soát bởi cùng capability.
- Các use case thay đổi vì những lý do nghiệp vụ liên quan.
- Một public API tương đối nhỏ so với implementation bên trong.

Hãy thử viết một câu trách nhiệm cho module candidate. Nếu câu đó phải dùng nhiều từ “và” để nối những việc không liên quan, module có thể đang quá rộng.

Ví dụ, câu “quản lý sản phẩm, đơn hàng, khách hàng, thanh toán và tồn kho” không mô tả một capability có cohesion tốt. Đó là nhiều ownership khác nhau được gom vào một nơi.

Ngược lại, không nên tách module chỉ vì một nhóm có vài class. Một module nhỏ vẫn có thể là ranh giới đúng nếu nó sở hữu một khái niệm nghiệp vụ độc lập, có invariant và public contract rõ ràng. Số lượng class không phải tiêu chí quyết định.

## 5. Đánh giá coupling và dependency direction

Coupling thể hiện mức độ một phần phải biết hoặc phụ thuộc vào phần khác. Một dependency có thể chấp nhận được nếu nó đi qua hợp đồng ổn định và phản ánh quan hệ nghiệp vụ có chủ đích.

Hãy kiểm tra:

1. Module consumer cần một kết quả nghiệp vụ hay cần biết implementation của module provider?
2. Consumer có truy cập repository, entity hoặc service nội bộ của provider không?
3. Provider có phải thay đổi mỗi khi consumer đổi giao diện hoặc use case không?
4. Có dependency ngược làm hai module không thể thay đổi độc lập không?
5. Một module có phụ thuộc quá nhiều module khác để hoàn thành trách nhiệm của chính nó không?

Một dependency tốt thường có hướng từ consumer đến contract do module sở hữu capability cung cấp. Consumer biết hợp đồng; provider giữ quyền thay đổi implementation.

Ví dụ, orders cần thông tin sản phẩm để tạo snapshot trong OrderLine. Orders có thể gọi ProductCatalog API. Nó không cần biết catalog dùng JPA, MongoDB hay một dịch vụ ngoài để lưu sản phẩm.

Nếu orders import ProductRepository hoặc ProductEntity của catalog, consumer đang phụ thuộc vào chi tiết persistence. Điều đó làm thay đổi schema hoặc cách lưu trữ của catalog lan sang orders.

## 6. Worked example: phân ranh giới cho ứng dụng bán hàng

Giả sử ứng dụng hiện có một package theo tầng:

~~~text
com.acme.shop
├── controller
│   ├── ProductController.java
│   ├── CustomerController.java
│   ├── OrderController.java
│   └── PaymentController.java
├── service
│   ├── ProductService.java
│   ├── CustomerService.java
│   ├── OrderService.java
│   ├── InventoryService.java
│   └── PaymentService.java
├── repository
│   ├── ProductRepository.java
│   ├── CustomerRepository.java
│   ├── OrderRepository.java
│   ├── StockRepository.java
│   └── PaymentRepository.java
└── entity
    ├── ProductEntity.java
    ├── CustomerEntity.java
    ├── OrderEntity.java
    ├── StockEntity.java
    └── PaymentEntity.java
~~~

Từ cấu trúc này, Spring Modulith có thể phát hiện các package controller, service, repository và entity theo default direct-subpackages strategy. Nhưng đó là module theo tầng kỹ thuật, không phải module theo capability.

Sau khi xem use case, invariant và ownership, đề xuất package cấp module:

~~~text
com.acme.shop
├── ShopApplication.java
├── catalog
├── customer
├── orders
├── inventory
└── payment
~~~

Các package con như web, application, domain, persistence, api, events và internal được tổ chức bên trong từng module khi cần. Không bắt buộc mọi module phải có đủ tất cả package con.

### Bản đồ trách nhiệm

| Module | Trách nhiệm chính | Dữ liệu và invariant sở hữu |
|---|---|---|
| catalog | Quản lý sản phẩm được bán, mô tả và giá niêm yết | Product, ProductStatus, PublishedPrice |
| customer | Quản lý hồ sơ, liên hệ và trạng thái khách hàng | Customer, CustomerAddress, CustomerStatus |
| orders | Tiếp nhận đơn, xác định dòng hàng, tổng tiền và vòng đời đơn | Order, OrderLine, OrderStatus, giá snapshot |
| inventory | Theo dõi hàng có thể bán và reservation | StockItem, Reservation, AvailableQuantity |
| payment | Quản lý yêu cầu thanh toán và kết quả giao dịch | PaymentAttempt, PaymentStatus, ProviderReference |

### Vì sao các trách nhiệm được tách?

Catalog và orders có thể cùng nói về sản phẩm, nhưng chúng bảo vệ những quyết định khác nhau. Catalog quản lý thông tin hiện tại của sản phẩm. Orders cần lưu snapshot tên, mã và giá tại thời điểm đặt để lịch sử đơn không đổi khi catalog cập nhật sản phẩm sau đó.

Customer sở hữu hồ sơ hiện tại. Orders chỉ cần customerId và các thông tin cần thiết được snapshot theo chính sách tại thời điểm đặt hàng, ví dụ địa chỉ giao hàng đã xác nhận. Orders không nên cập nhật trực tiếp CustomerEntity.

Inventory sở hữu số lượng và reservation. Orders có thể yêu cầu quy trình giữ hàng, nhưng không nên cập nhật StockEntity trực tiếp. Khi quy trình phức tạp, inventory có thể cung cấp một command API hoặc nhận event theo hợp đồng đã thống nhất.

Payment sở hữu trạng thái giao dịch với nhà cung cấp thanh toán. Orders có thể biết trạng thái đơn cần cập nhật khi thanh toán thành công, nhưng không nên trực tiếp sửa PaymentAttempt.

### Quan hệ giữa các module

Một thiết kế có thể bắt đầu với các hợp đồng sau:

| Consumer | Provider | Hợp đồng | Lý do |
|---|---|---|---|
| orders | catalog | catalog::api | Tra cứu thông tin sản phẩm và giá để tạo snapshot |
| orders | customer | customer::api | Kiểm tra khách hàng và lấy thông tin cần thiết cho đơn |
| inventory | orders | orders::events | Nhận sự kiện OrderPlaced để tạo reservation |
| payment | orders | orders::events | Nhận yêu cầu nghiệp vụ bắt đầu quy trình thanh toán |

Dependency graph theo hướng code:

~~~mermaid
flowchart LR
    inventory["inventory"] -->|"orders::events"| orders["orders"]
    payment["payment"] -->|"orders::events"| orders
    orders -->|"catalog::api"| catalog["catalog"]
    orders -->|"customer::api"| customer["customer"]
~~~

Đây là dependency graph, không phải sơ đồ thứ tự xử lý. Khi orders phát OrderPlaced, inventory và payment có thể nhận event. Việc consumer phụ thuộc vào event type của orders tạo cạnh code từ consumer đến orders.

Đồ thị không có chu trình. Catalog và customer không cần biết orders, inventory hoặc payment. Orders sử dụng public API của catalog và customer; các module downstream sử dụng event contract của orders.

## 7. Quyết định module boundary ở đâu?

Ranh giới nên đặt nơi trách nhiệm, dữ liệu và invariant có thể được sở hữu nhất quán. Có một số tình huống cần review kỹ.

### Khi một quy trình nghiệp vụ đi qua nhiều capability

Đặt hàng có thể bao gồm:

1. Xác thực khách hàng.
2. Tra cứu sản phẩm.
3. Tạo đơn hàng.
4. Giữ hàng.
5. Thu tiền.

Đây là một workflow, không nhất thiết là một module. Customer, catalog, orders, inventory và payment có thể vẫn là các module riêng vì chúng sở hữu dữ liệu và quy tắc khác nhau.

Orders có thể điều phối phần tạo đơn, nhưng không vì thế mà sở hữu toàn bộ quy tắc tồn kho và thanh toán. Khi quy trình cần nhiều bước, retry hoặc bù trừ, cân nhắc một application workflow/process manager. Workflow điều phối các capability; nó không chiếm quyền sở hữu dữ liệu của chúng.

### Khi hai capability luôn thay đổi cùng nhau

Nếu hai nhóm quy tắc thường xuyên được sửa cùng nhau vì cùng bảo vệ một invariant, hãy cân nhắc đặt chúng trong một module. Ví dụ, nếu giá và eligibility của sản phẩm chỉ có ý nghĩa cùng một chính sách catalog, có thể giữ chúng trong catalog.

Nếu giá có chính sách độc lập, nhiều nguồn giá, thời gian hiệu lực và quy trình phê duyệt riêng, pricing có thể trở thành capability riêng. Khi đó catalog sử dụng hợp đồng pricing để hiển thị giá, hoặc orders gọi pricing theo chính sách đã xác định.

Không tách module chỉ để đạt số lượng module lớn hơn. Mỗi module mới tạo thêm hợp đồng và dependency cần quản lý.

### Khi nhiều module cùng dùng một khái niệm

Một khái niệm được nhiều module tham chiếu không có nghĩa tất cả phải cùng sở hữu nó. Hãy chọn một owner và công khai representation phù hợp.

Ví dụ, ProductDetails có thể là DTO trong catalog::api. Orders lưu snapshot của các trường cần thiết vào OrderLine. Inventory chỉ cần productId để giữ hàng. Không module nào cần chia sẻ ProductEntity hoặc ProductRepository.

### Khi có package common hoặc shared

Không gom logic nghiệp vụ vào common chỉ vì nhiều module cần dùng. Hãy phân biệt:

- Shared utility: hàm kỹ thuật thuần, không chứa khái niệm nghiệp vụ hoặc invariant.
- Shared contract: DTO hoặc interface nhỏ được công khai có chủ đích.
- Shared kernel: một tập mô hình nghiệp vụ được các bên đồng sở hữu và thay đổi theo quy trình phối hợp rõ ràng.

Shared kernel làm tăng coupling tổ chức và kỹ thuật. Chỉ dùng khi có lý do thực tế, owner chung và quy trình kiểm soát thay đổi. Nếu không, một module nên sở hữu khái niệm và các module khác sử dụng contract.

## 8. Chọn public API, named interface hay event

Sau khi xác định boundary, hãy quyết định module khác cần tương tác theo cách nào.

### Public API cho truy vấn hoặc lệnh cần kết quả ngay

Dùng API khi consumer cần câu trả lời trong cùng luồng xử lý hoặc cần yêu cầu provider thực hiện một thao tác có kết quả rõ ràng.

Ví dụ:

- orders gọi catalog để tìm thông tin sản phẩm.
- orders gọi customer để xác minh khách hàng được phép đặt hàng.

API nên thể hiện ngôn ngữ nghiệp vụ, không để lộ repository hoặc persistence model.

### Event khi một sự kiện nghiệp vụ đã xảy ra

Dùng event khi provider công bố một sự kiện có ý nghĩa và các consumer có thể phản ứng độc lập.

Ví dụ:

- orders phát OrderPlaced.
- inventory tạo reservation.
- payment bắt đầu quy trình thanh toán.

Event nên diễn đạt điều đã xảy ra, có dữ liệu đủ để consumer xử lý theo hợp đồng. Tránh event mang các object mutable hoặc reference tới service/repository nội bộ.

Event không tự động làm một workflow trở nên eventual consistent đúng cách. Review phải xác định consumer xử lý đồng bộ hay bất đồng bộ, retry ra sao, event có thể bị phát lặp không và khi nào nghiệp vụ được xem là hoàn tất.

### Named interface để giới hạn package được công khai

Trong Spring Modulith, package gốc của module là unnamed interface mặc định. Package con có thể được công khai như named interface bằng @NamedInterface. Điều này cho phép module công khai một số nhóm API mà vẫn giữ package nội bộ.

Ví dụ:

~~~java
@org.springframework.modulith.NamedInterface("api")
package com.acme.shop.catalog.api;
~~~

Module orders có thể giới hạn dependency đến catalog::api:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "catalog::api"
)
package com.acme.shop.orders;
~~~

Nếu module có nhiều dependency hợp lệ, khai báo rõ từng dependency:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = {
                "catalog::api",
                "customer::api"
        }
)
package com.acme.shop.orders;
~~~

Named interface không phải một module mới. Nó là một hợp đồng package được công khai bên trong module sở hữu nó.

## 9. Giữ dependency graph không có chu trình

Một dependency cycle thường là dấu hiệu hai module đã chia sẻ trách nhiệm hoặc hợp đồng chưa đúng.

Ví dụ:

~~~mermaid
flowchart LR
    orders["orders"] --> inventory["inventory"]
    inventory --> orders
~~~

Nếu orders gọi InventoryService và inventory tham chiếu OrderEntity để cập nhật đơn, hai module bị phụ thuộc lẫn nhau. Khi một thay đổi ảnh hưởng cả hai phía, ranh giới khó kiểm soát.

Hãy truy nguyên từng cạnh:

- Orders cần câu trả lời nào từ inventory?
- Inventory cần dữ liệu nào từ orders?
- Có thể dùng command API một chiều hoặc event contract để tách phụ thuộc không?
- Module nào thực sự sở hữu trạng thái và invariant đang bị cả hai cập nhật?
- Có workflow nào nên điều phối hai module thay vì để chúng gọi ngược nhau?

Ví dụ, nếu inventory chỉ cần biết một đơn đã được tạo, orders phát OrderPlaced và inventory phụ thuộc vào orders::events. Orders không import InventoryService. Nếu orders cần biết reservation đã thành công trước khi xác nhận đơn, hãy thiết kế một hợp đồng trả kết quả hoặc quy trình nhiều bước với trạng thái rõ ràng; không che giấu một lời gọi đồng bộ bên trong event không có phản hồi.

## 10. Phân biệt module boundary với transaction boundary

Hai khái niệm thường liên quan nhưng không đồng nhất:

- Module boundary xác định ownership, API và dependency trong code.
- Transaction boundary xác định nhóm thay đổi trạng thái cần được commit hoặc rollback cùng nhau.

Một module thường nên tự bảo vệ invariant của mình trong transaction. Khi một nghiệp vụ đi qua nhiều module, đừng mặc định một transaction database lớn là cách duy nhất để bảo đảm đúng.

Hãy xác định consistency requirement:

| Nhu cầu nghiệp vụ | Hướng thiết kế cần xem xét |
|---|---|
| Một invariant thuộc một aggregate/module | Thực hiện và commit trong module owner |
| Consumer chỉ cần biết một fact sau khi provider hoàn tất | Domain event và xử lý downstream |
| Nhiều bước có thể retry độc lập | Workflow/process manager với trạng thái tiến trình |
| Bước sau thất bại cần hoàn tác nghiệp vụ trước | Compensating action hoặc saga |
| Event không được mất khi process dừng | Transactional publication, outbox hoặc cơ chế registry phù hợp |

Nếu một thiết kế chỉ chạy đúng khi hai module cùng cập nhật bảng của nhau trong một transaction, đó là dấu hiệu cần review ownership. Có thể hai phần nên ở cùng module, hoặc cần một workflow với consistency model được công bố rõ.

## 11. Chuyển quyết định thiết kế thành package Spring Modulith

Sau khi review trách nhiệm và dependency, ánh xạ module candidate vào package con trực tiếp của application root:

~~~text
com.acme.shop
├── ShopApplication.java
├── catalog
│   ├── api
│   └── internal
├── customer
│   ├── api
│   └── internal
├── orders
│   ├── events
│   └── internal
├── inventory
│   └── internal
└── payment
    └── internal
~~~

Với detection strategy mặc định direct-subpackages, Spring Modulith nhận diện catalog, customer, orders, inventory và payment thành application module. Package con được tổ chức theo API và implementation của từng module.

Ví dụ, package metadata của orders:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = {
                "catalog::api",
                "customer::api"
        }
)
package com.acme.shop.orders;
~~~

Định nghĩa event contract:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.orders.events;
~~~

Module inventory có thể chỉ cho phép phụ thuộc event contract của orders:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "orders::events"
)
package com.acme.shop.inventory;
~~~

Module payment có thể dùng cùng event contract nếu nghiệp vụ xác định nó bắt đầu xử lý khi đơn được tạo:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "orders::events"
)
package com.acme.shop.payment;
~~~

Hãy nhớ rằng allowedDependencies giới hạn dependency đi ra của module được khai báo. Nó không khóa các module khác phụ thuộc vào API của module đó. Public API vẫn cần được thiết kế và review theo hướng ownership.

## 12. Kiểm chứng thiết kế bằng ApplicationModules

Sau khi package và metadata đã được tạo, dùng ApplicationModules để kiểm tra module model:

~~~java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ApplicationModuleArchitectureTests {

    @Test
    void verifiesApplicationModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Verification kiểm tra dependency graph và các quy tắc module như:

- Không có dependency cycle.
- Module đóng chỉ được truy cập API được công khai của module khác.
- Dependency tuân thủ allowedDependencies nếu module đã khai báo allowlist.

Nếu verification thất bại, đừng chỉ thêm dependency vào allowlist. Hãy xác định xem dependency đó có phản ánh một quan hệ nghiệp vụ cần thiết hay consumer đang truy cập nhầm implementation. Mỗi lần mở thêm một API nên có lý do và owner rõ ràng.

Module integration test có thể kiểm tra module độc lập với dependency được mock hoặc bootstrap theo nhu cầu:

~~~java
package com.acme.shop.orders;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest
class OrdersModuleTests {

    @Test
    void startsOrdersModuleInIsolation() {
        // Thêm assertion cho use case của orders.
    }
}
~~~

Architecture test kiểm tra cấu trúc. Module integration test kiểm tra hành vi của capability. Cả hai cùng bảo vệ quyết định boundary sau khi review.

## 13. Dấu hiệu ranh giới cần xem lại

| Dấu hiệu | Vấn đề có thể có | Câu hỏi review |
|---|---|---|
| Một module có controller, service và repository của nhiều capability | Module được chia theo tầng kỹ thuật | Mỗi capability sở hữu invariant nào? |
| Nhiều module ghi cùng một entity hoặc bảng | Ownership không rõ | Ai là owner duy nhất của trạng thái? |
| Consumer import repository hoặc persistence entity của provider | Coupling vào implementation | Consumer cần contract nghiệp vụ nào? |
| Hai module phụ thuộc lẫn nhau | Dependency cycle | Có thể xác định một owner và chuyển giao tiếp thành một chiều không? |
| Một module có nhiều public class không liên quan | API quá rộng hoặc module quá lớn | Những class nào thật sự là hợp đồng cho consumer? |
| Module có nhiều dependency để hoàn tất một use case đơn giản | Capability bị chia quá vụn hoặc orchestration chưa rõ | Những phần nào cùng bảo vệ một invariant? |
| Package common chứa quy tắc giá, đơn hàng hoặc tồn kho | Business ownership bị che khuất | Quy tắc đó thuộc capability nào? |
| Mọi module đều dùng chung một entity graph | Shared model gây coupling | Có thể dùng ID, DTO hoặc event contract không? |
| Một module OPEN kéo dài mà không có kế hoạch đóng | Boundary chưa được siết | Consumer nào còn cần package nội bộ và vì sao? |
| Test của một module cần khởi động hầu hết ứng dụng | Module có nhiều phụ thuộc hoặc test chưa cô lập | Dependency nào có thể thay bằng contract hoặc test double? |

Không phải dấu hiệu nào cũng đồng nghĩa phải tách module. Một module lớn có thể hợp lý nếu nó sở hữu một capability rộng và các invariant liên quan. Mục tiêu là giải thích được quyết định bằng trách nhiệm, ownership và thay đổi thực tế.

## 14. Review một đề xuất boundary theo cấu trúc

Khi nhận một bản thiết kế, hãy review theo thứ tự sau:

### Trách nhiệm

- Mỗi module có một mô tả trách nhiệm rõ ràng không?
- Mô tả có dùng ngôn ngữ nghiệp vụ không?
- Có module nào chỉ được định nghĩa bằng công nghệ hoặc tầng kỹ thuật không?

### Ownership

- Mỗi aggregate, entity và invariant có owner không?
- Module khác có cập nhật dữ liệu của owner trực tiếp không?
- Có snapshot hoặc contract phù hợp khi dữ liệu cần được dùng ở nơi khác không?

### API và dependency

- Mỗi dependency có mục đích nghiệp vụ rõ không?
- Consumer có dùng public API/named interface thay vì implementation không?
- Dependency direction có nhất quán và không có cycle không?
- Allowlist có phản ánh dependency thực sự cần thiết không?

### Consistency và vận hành

- Transaction boundary có bảo vệ đúng invariant không?
- Event có thể bị phát lặp hoặc consumer xử lý chậm không?
- Retry, idempotency và compensating action đã được xác định khi cần chưa?
- Có yêu cầu không được mất event hoặc cần audit trail không?

### Kiểm chứng

- Module model có được tạo từ đúng application root không?
- ApplicationModules.verify() có chạy trong test không?
- Có module integration test cho các capability quan trọng không?
- Tên package, named interface và allowedDependencies có khớp bản thiết kế không?

## 15. Ví dụ review: service đặt hàng đang làm quá nhiều việc

Giả sử OrderService hiện tại:

~~~java
public class OrderService {

    public Order placeOrder(PlaceOrderCommand command) {
        Customer customer = customerRepository.findById(command.customerId())
                .orElseThrow();

        Product product = productRepository.findById(command.productId())
                .orElseThrow();

        stockRepository.decrease(command.productId(), command.quantity());

        Order order = orderRepository.save(
                Order.create(customer, product, command.quantity())
        );

        paymentRepository.createPendingPayment(order.getId());

        return order;
    }
}
~~~

Vấn đề thiết kế:

- OrderService đọc trực tiếp repository của customer và catalog.
- Orders cập nhật tồn kho do inventory sở hữu.
- Orders tạo payment record do payment sở hữu.
- Một service điều phối nhiều invariant và nhiều persistence model.
- Test cho orders phải biết schema hoặc repository của nhiều capability.

Đề xuất sau review:

1. Customer công khai CustomerCheckoutProfile qua customer::api.
2. Catalog công khai ProductOffering qua catalog::api.
3. Orders dùng hai API để xác minh đầu vào và lưu snapshot vào Order.
4. Orders phát OrderPlaced sau khi đơn được tạo.
5. Inventory nhận OrderPlaced và quản lý reservation.
6. Payment nhận OrderPlaced và quản lý payment attempt.
7. Một workflow theo dõi kết quả inventory/payment nếu nghiệp vụ chỉ xác nhận đơn sau khi các bước này hoàn tất.

OrderService sau khi chỉnh sửa có thể tập trung vào ownership của đơn:

~~~java
public class OrderService {

    private final CustomerCheckoutProfile customers;
    private final ProductCatalog catalog;
    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    public OrderConfirmation placeOrder(PlaceOrderCommand command) {
        var customer = customers.findCheckoutProfile(command.customerId())
                .orElseThrow();

        var product = catalog.findById(command.productId())
                .orElseThrow();

        Order order = Order.place(
                customer.id(),
                customer.shippingAddress(),
                product.id(),
                product.name(),
                product.unitPrice(),
                command.quantity()
        );

        orders.save(order);
        events.publishEvent(new OrderPlaced(
                order.getId(),
                command.productId(),
                command.quantity()
        ));

        return OrderConfirmation.from(order);
    }
}
~~~

Đây là minh họa cấu trúc trách nhiệm, không phải implementation hoàn chỉnh. Khi dùng event, cần xác định rõ lúc nào OrderPlaced được phát so với transaction commit và cách bảo đảm publication. Nếu order chỉ được xem là hợp lệ sau khi inventory giữ hàng và payment thành công, workflow cần theo dõi các kết quả đó trước khi chuyển trạng thái cuối cùng.

## 16. Ghi lại quyết định boundary để nhóm có thể duy trì

Một review tốt nên tạo ra một quyết định có thể đọc lại khi hệ thống thay đổi. Có thể ghi theo mẫu:

| Trường | Nội dung cần ghi |
|---|---|
| Module candidate | Tên module và capability |
| Responsibility | Một hoặc hai câu mô tả trách nhiệm |
| Owned concepts | Aggregate, entity, dữ liệu và invariant thuộc module |
| Public contracts | API, named interface hoặc event được công khai |
| Allowed dependencies | Các module/interface mà module được phép sử dụng |
| Consumers | Những module sử dụng hợp đồng |
| Consistency | Transaction, event timing, retry và eventual consistency |
| Alternatives | Các cách chia khác đã cân nhắc |
| Consequences | Trade-off, rủi ro và hướng tiến hóa |
| Verification | Architecture test và module test cần có |

Ví dụ quyết định ngắn:

~~~text
Module: inventory
Responsibility: Quản lý lượng hàng có thể bán và reservation.
Owned concepts: StockItem, Reservation, AvailableQuantity.
Public contracts: InventoryAvailability API nếu consumer cần truy vấn đồng bộ.
Incoming contracts: orders::events / OrderPlaced.
Outgoing dependencies: orders::events.
Consistency: Reservation được xử lý sau khi OrderPlaced được công bố;
consumer cần idempotency theo orderId.
Verification: inventory không truy cập orders ngoài named interface events.
~~~

Ghi lại cả quyết định chưa hoàn tất. Nếu nhóm chưa biết một quy tắc thuộc catalog hay pricing, hãy ghi rõ bằng chứng còn thiếu và người chịu trách nhiệm xác minh. Đừng biến giả định thành ranh giới cứng khi chưa hiểu nghiệp vụ.

## 17. Bài tập design review

Một hệ thống đặt vé hiện có các package:

~~~text
com.acme.booking
├── controller
├── service
├── repository
├── entity
└── integration
~~~

Các chức năng hiện tại:

- Quản lý sự kiện, địa điểm, sơ đồ ghế và giá vé.
- Quản lý hồ sơ người mua.
- Giữ ghế trong một khoảng thời gian.
- Tạo booking và tính tổng tiền.
- Thu tiền và hoàn tiền.
- Gửi vé điện tử sau khi booking được xác nhận.

Hãy thực hiện review:

1. Viết trách nhiệm nghiệp vụ cho từng capability candidate.
2. Gán owner cho Event, Seat, SeatHold, Booking, Payment và Ticket.
3. Liệt kê invariant quan trọng của từng owner.
4. Xác định API cần trả lời đồng bộ và event có thể công bố sau khi một fact xảy ra.
5. Vẽ dependency graph theo hướng code và kiểm tra cycle.
6. Đề xuất package tree Spring Modulith.
7. Viết allowedDependencies cho các module có dependency đi ra.
8. Liệt kê các test architecture và module cần có.

Một hướng phân ranh giới có thể là:

| Module | Ownership |
|---|---|
| eventcatalog | Event, venue, seat map và chính sách giá |
| customers | Hồ sơ người mua |
| bookings | Booking, trạng thái booking và snapshot giá |
| seating | Seat hold, thời hạn giữ và trạng thái ghế |
| payments | Payment attempt, capture và refund |
| ticketing | Ticket được phát hành sau khi booking đủ điều kiện |

Đây chỉ là giả thuyết. Module eventcatalog quản lý các sự kiện được mở bán; domain event như BookingConfirmed là một thông điệp tích hợp do module sở hữu nghiệp vụ phát ra. Nếu SeatHold và Booking phải bảo vệ một invariant đồng bộ trong cùng transaction, hãy cân nhắc đặt chúng gần nhau hơn hoặc thiết kế một quy trình giữ chỗ có trạng thái rõ ràng. Nếu ticketing chỉ tạo vé từ sự kiện BookingConfirmed, nó có thể là consumer riêng. Hãy giải thích bằng ownership và consistency thay vì chỉ dựa trên tên.

## 18. Checklist kết thúc design review

- [ ] Mỗi module có một capability và responsibility statement rõ ràng.
- [ ] Không có module nào chỉ được định nghĩa bằng controller, service hoặc repository.
- [ ] Mỗi aggregate, dữ liệu và invariant có owner cụ thể.
- [ ] Các module không cập nhật trực tiếp persistence model của nhau.
- [ ] Consumer chỉ dùng public API hoặc named interface cần thiết.
- [ ] Event contract có owner, ý nghĩa nghiệp vụ và dữ liệu đủ dùng.
- [ ] Dependency graph không có cycle hoặc có lý do được ghi nhận cho ngoại lệ.
- [ ] allowedDependencies phản ánh đúng các dependency đi ra.
- [ ] Transaction và consistency model phù hợp với invariant.
- [ ] Workflow liên module có retry, idempotency hoặc bù trừ khi cần.
- [ ] Module package được phát hiện đúng từ application root.
- [ ] ApplicationModules.verify() được thực thi trong architecture test.
- [ ] Các quyết định, trade-off và câu hỏi chưa giải quyết được ghi lại.

## 19. Ghi nhớ

Hãy xác định module boundary từ trách nhiệm nghiệp vụ, invariant và quyền sở hữu dữ liệu. Một module nên gom những phần có cohesion cao và công khai hợp đồng nhỏ cho consumer. Quy trình nghiệp vụ có thể đi qua nhiều module; workflow điều phối chúng mà không lấy quyền sở hữu dữ liệu của từng capability. Trong Spring Modulith, package cấp module thể hiện boundary, named interface công khai các API con, allowedDependencies giới hạn dependency đi ra và ApplicationModules.verify() kiểm tra dependency graph. Design review chỉ hoàn tất khi nhóm giải thích được vì sao mỗi module tồn tại, dữ liệu nào thuộc về nó, ai được phép phụ thuộc vào nó và consistency được bảo đảm như thế nào.

## Tài liệu tham khảo

- [Spring Modulith – Fundamentals and Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith – Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith – Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html)
- [Spring Modulith – Application Events](https://docs.spring.io/spring-modulith/reference/events.html)
- [Spring Modulith – API Documentation](https://docs.spring.io/spring-modulith/docs/current/api/)

# Đánh giá tổ chức theo tính năng hoặc vertical slice và khả năng kết hợp phân tầng

Khi một ứng dụng lớn dần, cách sắp xếp mã nguồn ảnh hưởng trực tiếp đến tốc độ tìm hiểu, phạm vi thay đổi và khả năng làm việc song song của nhóm. Một dự án có thể gom tất cả controller vào một package, tất cả service vào package khác và tất cả repository vào package thứ ba. Cách tổ chức này thể hiện rõ các tầng kỹ thuật, nhưng một thay đổi nhỏ cho một tính năng có thể buộc người phát triển đi qua nhiều thư mục. Một cách khác là gom mã theo tính năng hoặc theo luồng sử dụng hoàn chỉnh (vertical slice), để các thành phần cùng phục vụ một khả năng nghiệp vụ nằm gần nhau.

Hai cách tổ chức không loại trừ nhau. Một hệ thống có thể tổ chức cấp cao theo tính năng, rồi chia từng tính năng thành các tầng trình bày, ứng dụng, miền và hạ tầng. Cũng có thể tổ chức theo từng ca sử dụng dọc, nhưng vẫn giữ các abstraction và quy tắc phụ thuộc của kiến trúc phân tầng. Điều cần đánh giá là mức độ gắn kết, phạm vi thay đổi, hướng phụ thuộc, quyền sở hữu dữ liệu và chi phí phối hợp của nhóm, chứ không chỉ là tên thư mục.

Bài học thuộc module SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED, với mục tiêu học tổ chức phần mềm theo kiến trúc phân tầng. Nội dung này giúp đánh giá package-by-layer, package-by-feature và vertical slice, sau đó chọn cách kết hợp phù hợp với quy mô và nhu cầu tiến hóa của hệ thống.

## 1. Hai trục tổ chức khác nhau

Trước tiên cần tách hai câu hỏi:

- **Tổ chức mã nguồn theo trục nào?** Theo loại kỹ thuật (controller, service, repository) hay theo khả năng nghiệp vụ (orders, catalog, billing)?
- **Chia trách nhiệm và hướng phụ thuộc ra sao?** Tầng trình bày, ứng dụng, miền và hạ tầng giao tiếp qua hợp đồng nào, và tầng nào được phép biết tầng nào?

Package-by-layer và package-by-feature chủ yếu trả lời câu hỏi thứ nhất. Kiến trúc phân tầng trả lời câu hỏi thứ hai. Vì vậy, một dự án có package theo feature vẫn có thể tuân thủ kiến trúc phân tầng; một dự án có package tên presentation/application/domain/infrastructure vẫn có thể vi phạm ranh giới nếu các tầng tham chiếu tùy ý lẫn nhau.

### 1.1. Tổ chức theo tầng kỹ thuật

Một cấu trúc package-by-layer thường có dạng:

~~~text
com.example.shop
  presentation
    OrderController.java
    ProductController.java
    CustomerController.java
  application
    CreateOrderService.java
    CancelOrderService.java
    UpdateProductService.java
  domain
    Order.java
    Product.java
    Customer.java
  infrastructure
    JpaOrderRepository.java
    JpaProductRepository.java
    JpaCustomerRepository.java
~~~

Ưu điểm là người đọc dễ tìm một loại thành phần kỹ thuật. Quy tắc chung của một tầng có thể được áp dụng trên toàn package, ví dụ controller không được gọi trực tiếp repository. Cấu trúc này có thể phù hợp với ứng dụng nhỏ, ít tính năng hoặc nhóm cần một quy ước đơn giản.

Khi số tính năng tăng, các package tầng trở thành nơi chứa rất nhiều thành phần không cùng phục vụ một thay đổi. Để sửa luồng tạo đơn hàng, người phát triển có thể phải mở controller ở presentation, service ở application, entity ở domain và repository ở infrastructure. Các lớp của nhiều tính năng nằm cạnh nhau về kỹ thuật nhưng xa nhau về ngữ cảnh nghiệp vụ. Một service tổng quát cũng có thể dần phình to nếu mọi use case được thêm vào cùng một package hoặc lớp điều phối.

### 1.2. Tổ chức theo tính năng

Package-by-feature gom các thành phần liên quan đến một khả năng nghiệp vụ vào cùng một vùng:

~~~text
com.example.shop
  orders
    OrderController.java
    CreateOrderService.java
    CancelOrderService.java
    Order.java
    JpaOrderRepository.java
  catalog
    ProductController.java
    UpdateProductService.java
    Product.java
    JpaProductRepository.java
  customers
    CustomerController.java
    RegisterCustomerService.java
    Customer.java
    JpaCustomerRepository.java
~~~

Khi sửa tính năng orders, phần lớn mã liên quan có thể được tìm thấy trong một khu vực. Điều này tăng tính gắn kết theo nghiệp vụ và giúp nhóm phụ trách một tính năng hiểu phạm vi thay đổi rõ hơn. Khi cần tách module sau này, một feature package có thể là điểm bắt đầu để xác định ranh giới.

Tuy nhiên, gom theo tính năng không tự tạo ra ranh giới tốt. Nếu OrderController gọi trực tiếp JpaCustomerRepository bên trong package customers, hoặc mọi feature truy cập mọi entity của nhau, coupling vẫn cao. Package-by-feature chỉ cải thiện cách định vị mã; các quy tắc phụ thuộc và hợp đồng vẫn cần được thiết kế.

## 2. Vertical slice là gì?

**Vertical slice** là một lát cắt đi qua các phần cần thiết để hoàn thành một luồng sử dụng hoặc một khả năng cụ thể, từ điểm vào đến kết quả và tác động dữ liệu. Ví dụ, slice tạo đơn hàng có thể bao gồm endpoint hoặc message handler, command/handler ứng dụng, quy tắc tạo đơn, cổng lưu trữ, adapter persistence và phản hồi.

Một slice thường được xác định theo hành vi mà người dùng hoặc hệ thống khác cần thực hiện, chẳng hạn:

- Tạo đơn hàng.
- Hủy đơn hàng.
- Tra cứu trạng thái giao hàng.
- Đổi địa chỉ nhận hàng.
- Hoàn tiền cho một giao dịch.

Vertical slice không có nghĩa mỗi tính năng phải trở thành một microservice hoặc một tiến trình triển khai riêng. Các slice có thể cùng chạy trong một ứng dụng modular monolith, dùng chung database và hạ tầng. Nó cũng không bắt buộc dùng CQRS, mediator hoặc một framework cụ thể. Cốt lõi là tổ chức mã quanh một luồng nghiệp vụ hoàn chỉnh, cho phép luồng đó được phát triển và kiểm thử với mức phụ thuộc hợp lý.

### 2.1. Package-by-feature và vertical slice liên quan thế nào?

Package-by-feature gom mã theo nhóm nghiệp vụ tương đối rộng, ví dụ orders. Vertical slice có thể đi sâu hơn, chia nhóm đó thành từng ca sử dụng như orders.create, orders.cancel và orders.get. Hai cách thường được kết hợp:

~~~text
com.example.shop
  orders
    create
      CreateOrderController.java
      CreateOrderHandler.java
      CreateOrderCommand.java
      CreateOrderResult.java
    cancel
      CancelOrderController.java
      CancelOrderHandler.java
      CancelOrderCommand.java
    query
      GetOrderController.java
      GetOrderHandler.java
      OrderDetails.java
    domain
      Order.java
      OrderLine.java
      OrderStatus.java
    infrastructure
      JpaOrderRepository.java
~~~

Ví dụ này có các slice riêng cho thao tác tạo, hủy và truy vấn, trong khi một số mô hình miền và adapter có thể được chia sẻ trong phạm vi orders. Nếu các slice có mô hình dữ liệu và quy tắc hoàn toàn khác nhau, không cần ép chúng dùng chung một service hoặc DTO chỉ để giảm số file.

Ngược lại, nếu nhiều use case thực sự cùng bảo vệ một bất biến trên một aggregate hoặc cùng cần một chính sách, chúng có thể dùng chung mô hình miền. Mục tiêu là chia sẻ khái niệm và quy tắc có cùng quyền sở hữu, không phải loại bỏ mọi sự trùng lặp bằng một lớp dùng chung quá tổng quát.

## 3. Có thể kết hợp vertical slice với kiến trúc phân tầng không?

Có. Một lựa chọn thường thực tế là tổ chức cấp cao theo feature, rồi giữ các trách nhiệm phân tầng bên trong mỗi feature:

~~~text
com.example.shop
  orders
    presentation
      OrderController.java
    application
      CreateOrderUseCase.java
      CreateOrderService.java
      OrderRepository.java
    domain
      Order.java
      OrderLine.java
    infrastructure
      JpaOrderRepository.java
  catalog
    presentation
    application
    domain
    infrastructure
  shared
    ...
~~~

Trong cấu trúc này:

- Tổ chức theo feature giúp các thay đổi của orders nằm gần nhau và tách khỏi catalog.
- Tầng presentation nhận giao tiếp bên ngoài và chuyển thành lệnh hoặc truy vấn phù hợp.
- Tầng application điều phối ca sử dụng và định nghĩa các cổng mà nó cần.
- Tầng domain giữ bất biến và quy tắc nghiệp vụ thuộc feature.
- Tầng infrastructure hiện thực cổng bằng JPA, HTTP client hoặc công nghệ cụ thể.

Đây là cách kết hợp trục tổ chức theo nghiệp vụ với ranh giới trách nhiệm kỹ thuật. Số tầng bên trong mỗi feature có thể khác nhau. Một feature đơn giản có thể chỉ cần handler và adapter; feature phức tạp có thể cần nhiều package nội bộ. Không nên tạo đủ bốn thư mục rỗng cho mọi tính năng chỉ vì muốn cấu trúc đồng đều.

~~~mermaid
flowchart TB
    subgraph Orders["Feature: Orders"]
        OP["Presentation"]
        OA["Application"]
        OD["Domain"]
        OI["Infrastructure"]
        OP --> OA
        OA --> OD
        OI --> OA
        OI --> OD
    end
    subgraph Catalog["Feature: Catalog"]
        CP["Presentation"]
        CA["Application"]
        CD["Domain"]
        CI["Infrastructure"]
        CP --> CA
        CA --> CD
        CI --> CA
        CI --> CD
    end
    OA -. "public contract nếu cần" .-> CA
~~~

Sơ đồ chỉ minh họa một khả năng tích hợp giữa feature. Đường phụ thuộc giữa Orders và Catalog phải đi qua hợp đồng công khai có chủ sở hữu rõ ràng. Không nên để Orders import tùy ý các lớp nội bộ của Catalog. Nếu use case cần thông tin sản phẩm, nó có thể gọi một cổng hoặc API ứng dụng được công bố bởi feature sở hữu dữ liệu đó.

## 4. So sánh package-by-layer, package-by-feature và vertical slice

| Tiêu chí | Package-by-layer | Package-by-feature | Vertical slice theo use case |
|---|---|---|---|
| Đơn vị tổ chức | Loại kỹ thuật | Nhóm khả năng nghiệp vụ | Một luồng hoặc hành động cụ thể |
| Tìm mã khi sửa tính năng | Có thể phải đi qua nhiều package | Các thành phần chính nằm gần nhau | Phần lớn mã của một luồng được gom trong slice |
| Tái sử dụng | Dễ nhìn thấy thành phần chung, nhưng dễ tạo service/repository tổng quát | Chia sẻ trong feature rõ hơn | Có thể lặp có chủ đích giữa slice để giữ tính độc lập |
| Phạm vi thay đổi | Có thể lan qua nhiều package tầng | Thường tập trung hơn theo feature | Thường hẹp theo ca sử dụng |
| Ranh giới phụ thuộc | Dễ đặt rule theo tầng | Cần kiểm soát truy cập giữa feature | Cần kiểm soát chia sẻ giữa slice và mô hình chung |
| Phù hợp | Ứng dụng nhỏ, quy tắc kỹ thuật đơn giản | Ứng dụng có nhiều nhóm nghiệp vụ | Hệ thống có nhiều luồng thay đổi độc lập hoặc khác nhau rõ |
| Rủi ro chính | Package tầng lớn, coupling theo kỹ thuật | Feature package trở thành vùng phụ thuộc tự do | Trùng lặp, phân mảnh hoặc slice quá nhỏ |

Không có cấu trúc nào thắng ở mọi tiêu chí. Package-by-layer có thể dễ áp dụng lúc đầu; package-by-feature thường giúp tăng tính gắn kết nghiệp vụ; vertical slice có thể giảm coupling giữa các ca sử dụng khi chúng cần tiến hóa độc lập. Lựa chọn cần dựa trên cách hệ thống thay đổi và cách nhóm làm việc.

## 5. Đánh giá theo tính gắn kết và phạm vi thay đổi

Một câu hỏi hữu ích là: khi một yêu cầu thay đổi, bao nhiêu thành phần phải được sửa và chúng có cùng thuộc một khả năng nghiệp vụ không?

Ví dụ, thay đổi quy tắc tạo đơn hàng từ “mỗi khách hàng có thể đặt nhiều đơn” sang “khách hàng bị giới hạn số đơn đang chờ” có thể tác động đến:

- Use case tạo đơn.
- Quy tắc miền kiểm tra số đơn đang chờ.
- Cổng truy vấn đơn hàng theo khách hàng.
- Có thể là API trả lỗi hoặc mã lỗi cho client.
- Test tích hợp và test nghiệp vụ liên quan.

Nếu các thành phần này nằm trong feature orders hoặc slice create order, phạm vi thay đổi dễ nhận biết. Nhưng nếu quy tắc được đặt trong một lớp common service được nhiều feature sử dụng, thay đổi có thể tác động rộng và khó đoán.

Hãy xem xét:

- **Cohesion:** các lớp trong cùng package/module có cùng lý do thay đổi không?
- **Coupling:** một feature cần biết bao nhiêu chi tiết nội bộ của feature khác?
- **Change locality:** thay đổi một use case có thể được thực hiện trong phạm vi nào?
- **Ownership:** nhóm hoặc người phụ trách có thể xác định rõ ai sở hữu hợp đồng và dữ liệu không?
- **Reuse:** phần được chia sẻ có thực sự cùng ngữ nghĩa hay chỉ giống cấu trúc tạm thời?

Nếu một package orders chứa nhiều lớp không liên quan chỉ vì chúng cùng dùng database, đó có thể là tổ chức theo kỹ thuật quá rộng. Nếu mỗi slice sao chép cùng một quy tắc tính thuế và các bản sao dần khác nhau, cần xem xét đưa quy tắc có cùng ý nghĩa về một abstraction có chủ sở hữu rõ ràng.

## 6. Kiểm soát phụ thuộc giữa các feature

Tổ chức theo feature làm nổi bật một câu hỏi mới: feature này được phép sử dụng phần nào của feature khác?

Ví dụ, Orders cần xác nhận SKU có thể bán hay không. Có một số lựa chọn:

1. Orders gọi một public application contract do Catalog cung cấp.
2. Orders định nghĩa cổng ProductAvailability của riêng mình và một adapter tích hợp gọi Catalog.
3. Nếu hai feature thực sự chia sẻ một khái niệm ổn định, hợp đồng có thể nằm trong một module contract được quản lý rõ.

Không nên để Orders truy cập thẳng JpaProductRepository hoặc ProductEntity nội bộ của Catalog. Làm vậy khiến cấu trúc lưu trữ của Catalog trở thành hợp đồng ngầm cho Orders. Khi Catalog đổi schema hoặc cách lưu trữ, feature khác có thể bị ảnh hưởng.

~~~java
// Catalog công bố hợp đồng ứng dụng
public interface ProductAvailability {
    boolean canBeOrdered(String sku, int quantity);
}

// Orders phụ thuộc vào khả năng, không phụ thuộc adapter JPA của Catalog
public class CreateOrderHandler {
    private final ProductAvailability availability;
    private final OrderRepository orders;

    public CreateOrderHandler(
            ProductAvailability availability,
            OrderRepository orders) {
        this.availability = availability;
        this.orders = orders;
    }

    public void handle(CreateOrderCommand command) {
        for (OrderItemRequest item : command.items()) {
            if (!availability.canBeOrdered(item.sku(), item.quantity())) {
                throw new ProductNotAvailableException(item.sku());
            }
        }
        orders.save(Order.create(command));
    }
}
~~~

Đoạn mã minh họa một hợp đồng giữa hai feature; trong ứng dụng thực tế cần quyết định feature nào sở hữu interface, ai cung cấp implementation và cách bảo đảm transaction/consistency khi hai feature dùng các nguồn dữ liệu khác nhau. Nếu việc kiểm tra availability và tạo order không thể nguyên tử trong cùng database transaction, cần xử lý khả năng dữ liệu thay đổi giữa lúc kiểm tra và lúc đặt hàng.

Các quy tắc phụ thuộc có thể được kiểm tra bằng ArchUnit hoặc quy tắc module của build. Ví dụ, package orders không được tham chiếu package infrastructure.persistence bên trong catalog. Test kiến trúc giúp ngăn một import tiện tay làm rò rỉ chi tiết nội bộ.

## 7. Khi nào nên chia sẻ và khi nào nên giữ riêng?

Một sai lầm phổ biến là coi mọi đoạn mã giống nhau là một cơ hội tái sử dụng. Hai use case có thể cùng có một trường amount nhưng ý nghĩa, quy tắc làm tròn và vòng đời khác nhau. Ép chúng dùng chung một kiểu hoặc service có thể tạo coupling không cần thiết.

Nên cân nhắc chia sẻ khi:

- Các feature dùng cùng một khái niệm có cùng ý nghĩa và quy tắc.
- Một chính sách phải được thực thi nhất quán ở nhiều nơi.
- Hợp đồng được nhiều bên sử dụng và có người sở hữu rõ.
- Chi phí thay đổi một abstraction chung thấp hơn chi phí duy trì các bản sao.

Nên giữ riêng khi:

- Hai luồng chỉ giống nhau về cấu trúc nhưng có ngữ nghĩa khác nhau.
- Các feature cần thay đổi độc lập với tốc độ khác nhau.
- Abstraction chung phải có nhiều cờ hoặc nhánh điều kiện để phục vụ các trường hợp khác nhau.
- Việc chia sẻ buộc feature này biết chi tiết nội bộ của feature kia.

Một package common hoặc shared có thể hữu ích cho kiểu giá trị, tiện ích kỹ thuật hoặc hợp đồng thật sự dùng chung. Nhưng nếu mọi lớp khó đặt chỗ đều được đưa vào common, package đó sẽ trở thành nơi chứa phụ thuộc không có chủ sở hữu. Hãy đặt tên và ranh giới theo ngữ nghĩa, ví dụ money, identity hoặc shared kernel có phạm vi rõ, thay vì một túi misc tùy tiện.

## 8. Chọn cấu trúc theo bối cảnh hệ thống

| Bối cảnh | Cách tổ chức có thể phù hợp | Điều cần quan sát |
|---|---|---|
| Ứng dụng nhỏ, ít tính năng, một nhóm | Package-by-layer đơn giản hoặc feature-first nhẹ | Tránh tạo abstraction và module quá sớm |
| Nhiều nhóm nghiệp vụ, nhiều tính năng độc lập | Package/module theo feature, giữ layer boundary trong feature khi cần | Quyền sở hữu, hợp đồng và dependency giữa feature |
| Nhiều use case có tốc độ thay đổi khác nhau | Vertical slice theo use case | Tính độc lập của slice và mức trùng lặp có chủ đích |
| Hệ thống modular monolith | Feature module kết hợp phân tầng nội bộ | Public API, module boundary, không truy cập package nội bộ |
| Hệ thống có nhiều adapter/công nghệ | Feature-first hoặc module-first với ports/adapters rõ | Hướng phụ thuộc vào abstraction và khả năng thay adapter |
| Nhóm đang cải tiến legacy code | Chuyển dần từng feature hoặc luồng có rủi ro | Characterization tests, phạm vi thay đổi nhỏ và khả năng rollback |

Đừng chọn vertical slice chỉ vì một xu hướng hoặc vì muốn mỗi use case có một thư mục riêng. Nếu các use case có cùng quy tắc miền và thay đổi cùng nhau, một feature module với các tầng nội bộ có thể dễ hiểu hơn. Nếu các use case khác nhau đáng kể và cần tiến hóa độc lập, chia slice có thể giảm sự can thiệp lẫn nhau.

## 9. Một cấu trúc hybrid cho ứng dụng modular monolith

Ví dụ một ứng dụng bán hàng có thể tổ chức theo feature ở cấp module:

~~~text
shop
  orders
    api
      CreateOrderUseCase.java
      OrderView.java
    application
      CreateOrderHandler.java
      CancelOrderHandler.java
    domain
      Order.java
      OrderPolicy.java
    infrastructure
      JpaOrderRepository.java
  catalog
    api
      ProductAvailability.java
      ProductDetails.java
    application
      ProductQueryService.java
    domain
      Product.java
    infrastructure
      JpaProductRepository.java
  payments
    api
      PaymentAuthorization.java
    application
    domain
    infrastructure
  bootstrap
    ApplicationConfiguration.java
~~~

Trong cấu trúc này, package api của một feature là bề mặt được phép sử dụng từ feature khác; các package application/domain/infrastructure nội bộ không mặc nhiên được truy cập. Bootstrap hoặc composition root lắp ráp implementation. Có thể dùng Java module, build module hoặc kiểm thử kiến trúc để củng cố ranh giới khi quy mô đủ lớn.

Không nhất thiết mọi feature đều có cùng số lớp hoặc package. Một feature truy vấn đơn giản có thể chỉ có query handler và adapter. Một feature thanh toán phức tạp có thể cần mô hình miền, transaction orchestration, cổng tích hợp và nhiều kiểm thử. Sự không đồng đều phản ánh độ phức tạp khác nhau của nghiệp vụ, không nhất thiết là thiếu nhất quán.

## 10. Tiến hóa từ package-by-layer sang feature-first

Không cần di chuyển toàn bộ hệ thống trong một lần. Có thể chuyển từng luồng:

1. Chọn một feature có phạm vi rõ và có kiểm thử đủ tin cậy.
2. Liệt kê controller, service, domain object, repository và adapter liên quan.
3. Di chuyển các lớp về package feature mới mà không đổi hành vi.
4. Xác định public contract của feature và giảm truy cập vào chi tiết nội bộ.
5. Kiểm tra hướng phụ thuộc và cập nhật quy tắc kiến trúc.
6. Chạy test liên quan, review diff và xác nhận cấu hình lắp ráp vẫn hoạt động.
7. Lặp lại với feature tiếp theo; chỉ tạo shared abstraction khi có bằng chứng về ngữ nghĩa chung.

~~~mermaid
flowchart TD
    A["Chọn một luồng nghiệp vụ"] --> B["Ghi nhận hành vi và dependency"]
    B --> C["Tạo ranh giới feature"]
    C --> D["Di chuyển mã, giữ hành vi"]
    D --> E["Công bố contract cần thiết"]
    E --> F["Kiểm tra dependency và test"]
    F --> G{"Ranh giới rõ và test pass?"}
    G -->|Có| H["Chọn feature tiếp theo"]
    G -->|Không| I["Điều chỉnh contract / dependency"]
    I --> F
~~~

Khi di chuyển, không nên đồng thời đổi tên hàng loạt, viết lại nghiệp vụ, thay database và tách service triển khai. Quá nhiều thay đổi làm khó xác định nguyên nhân nếu regression xuất hiện. Giữ bước refactor nhỏ và có thể review giúp giảm rủi ro.

## 11. Kiểm thử cấu trúc và chất lượng ranh giới

Một cấu trúc feature-first chỉ có ý nghĩa nếu ranh giới được duy trì. Có thể dùng:

- Unit test cho quy tắc miền và từng use case.
- Integration test cho repository, transaction và adapter.
- Contract test cho public API giữa các feature.
- Architecture test để cấm import package nội bộ hoặc phụ thuộc ngược.
- End-to-end test cho một số luồng quan trọng từ điểm vào đến kết quả.

Ví dụ một quy tắc ArchUnit có thể cấm feature Orders tham chiếu trực tiếp infrastructure của Catalog:

~~~java
@ArchTest
static final ArchRule ordersMustNotDependOnCatalogInfrastructure =
    noClasses().that().resideInAPackage("..orders..")
        .should().dependOnClassesThat()
        .resideInAPackage("..catalog.infrastructure..");
~~~

Quy tắc cụ thể cần điều chỉnh theo package thật và có thể cần ngoại lệ cho bootstrap hoặc adapter tích hợp. Một test architecture không thể tự xác nhận feature API có ngữ nghĩa tốt; vẫn cần review hợp đồng, dữ liệu được lộ ra và các trường hợp lỗi.

## 12. Các dấu hiệu cấu trúc đang không còn phù hợp

- Một thay đổi nhỏ luôn phải sửa nhiều package kỹ thuật không liên quan.
- Một package service chứa nhiều use case không cùng ngữ cảnh và khó phân công quyền sở hữu.
- Feature này thường xuyên import repository, entity hoặc class nội bộ của feature khác.
- Package common tăng liên tục và không ai chịu trách nhiệm về các abstraction bên trong.
- Một use case phải đi qua nhiều lớp chuyển tiếp chỉ để gọi một thao tác đơn giản.
- Mỗi vertical slice tự triển khai lại một quy tắc quan trọng và các bản sao bắt đầu khác nhau.
- Nhóm khó xác định nơi đặt test, nơi đặt hợp đồng hoặc nơi sở hữu transaction.

Những dấu hiệu này là lý do để đánh giá lại, không phải bằng chứng rằng phải chuyển sang một mô hình cụ thể. Có thể chỉ cần đổi package, tách một module, công bố một contract hoặc gom một nhóm lớp cùng lý do thay đổi.

## 13. Checklist lựa chọn

Trước khi chọn cách tổ chức hoặc thay đổi cấu trúc hiện tại, hãy trả lời:

1. Đơn vị thay đổi phổ biến nhất là tầng kỹ thuật, feature hay một use case?
2. Các lớp thường được sửa cùng nhau có nằm gần nhau không?
3. Feature có thể được kiểm thử và phát triển mà không cần biết chi tiết nội bộ của feature khác không?
4. Hợp đồng chia sẻ có ngữ nghĩa rõ và có chủ sở hữu không?
5. Có cần giữ các tầng logic bên trong feature để quản lý dependency direction không?
6. Cấu trúc mới có làm tăng quá nhiều lớp chuyển tiếp, abstraction hoặc trùng lặp không?
7. Có thể chuyển đổi từng bước với test bảo vệ hành vi không?
8. Cấu trúc có phản ánh cách nhóm sở hữu và vận hành hệ thống không?

Package-by-layer, package-by-feature và vertical slice là những cách nhìn khác nhau về cùng một mã nguồn. Feature-first giúp tổ chức theo khả năng nghiệp vụ; vertical slice giúp gom một luồng hoàn chỉnh; phân tầng giúp kiểm soát trách nhiệm và hướng phụ thuộc. Kết hợp chúng khi cần, nhưng hãy giữ hợp đồng rõ ràng, giới hạn truy cập nội bộ và chọn mức phân tách tương xứng với độ phức tạp thật của hệ thống.

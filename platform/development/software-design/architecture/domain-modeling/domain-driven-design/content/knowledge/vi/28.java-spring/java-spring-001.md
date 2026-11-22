# Tổ chức gói Java theo Bounded Context và ngăn phụ thuộc chéo ngoài ý muốn

Trong một ứng dụng DDD, cách tổ chức package Java ảnh hưởng trực tiếp đến khả năng nhìn thấy ranh giới giữa các phần nghiệp vụ. Nếu tất cả entity nằm trong một package, tất cả service nằm trong package khác và mọi repository được gom vào một chỗ, cấu trúc mã nguồn có thể khiến các bounded context phụ thuộc lẫn nhau dù mô hình nghiệp vụ đã phân biệt chúng. Một thay đổi trong Sales có thể làm hỏng Inventory; một controller có thể gọi thẳng repository của Billing; hoặc một context có thể import entity nội bộ của context khác.

DDD yêu cầu mỗi bounded context có mô hình, ngôn ngữ và trách nhiệm riêng. Java package, visibility, module và công cụ kiểm tra kiến trúc giúp hiện thực hóa các ranh giới đó ở cấp mã nguồn. Tuy nhiên, package không tự tạo ra bounded context. Bounded context là ranh giới mô hình nghiệp vụ; package là một trong những cơ chế tổ chức và kiểm soát phụ thuộc.

Bài học này trình bày cách tổ chức một modular monolith theo bounded context, phân chia các lớp bên trong từng context, xác định API công khai và implementation nội bộ, định hướng phụ thuộc, sử dụng Java visibility và JPMS, cũng như áp dụng ArchUnit hoặc Spring Modulith để phát hiện phụ thuộc chéo ngoài ý muốn. Mục tiêu là làm cho cấu trúc code hỗ trợ ranh giới nghiệp vụ và giúp các vi phạm được phát hiện sớm.

## 1. Bounded Context và Java package không phải cùng một khái niệm

**Bounded Context** là ranh giới trong đó một domain model và Ubiquitous Language có ý nghĩa nhất quán. Cùng một từ có thể mang nghĩa khác nhau ở các context khác nhau. Ví dụ, Sales xem Order là cam kết mua bán; Shipping xem Shipment là đơn vị giao nhận; Billing xem Invoice là chứng từ phải thu. Những mô hình này liên quan nhưng không nên bị nhập thành một mô hình dùng chung.

**Java package** là cơ chế nhóm các kiểu và tên trong namespace. Package giúp tổ chức code, hạn chế xung đột tên và hỗ trợ access control ở phạm vi package. Package không biết khái niệm nghiệp vụ, không tự đảm bảo một nhóm class thuộc cùng bounded context và không ngăn mọi phụ thuộc giữa các package.

| Khái niệm | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| Bounded Context | Mô hình và ngôn ngữ nghiệp vụ nào có ranh giới riêng? | Sales, Inventory, Billing |
| Java package | Các kiểu Java được nhóm và đặt tên thế nào? | com.acme.shop.sales |
| Maven/Gradle module | Phần mã nguồn nào được build và phụ thuộc như một đơn vị? | sales-module, inventory-module |
| JPMS module | Module Java nào đọc hoặc export package nào? | module com.acme.shop.sales |
| Spring Modulith module | Package/module ứng dụng Spring nào có API và dependency được xác định? | sales application module |

Một bounded context có thể được triển khai bằng một hoặc nhiều Java package, Maven module hoặc service. Ngược lại, một package không tự động tương ứng với một bounded context chỉ vì tên package giống tên nghiệp vụ.

### 1.1. Ranh giới nghiệp vụ phải được xác định trước

Trước khi tạo folder, nhóm cần xác định:

- Context nào sở hữu dữ liệu và quy tắc của khái niệm?
- Những hành vi nào thuộc context đó?
- Context khác cần biết thông tin nào?
- Dữ liệu nào được công bố qua API hoặc event?
- Những mô hình nào chỉ là cách biểu diễn nội bộ?
- Có thuật ngữ nào trùng tên nhưng khác ý nghĩa giữa các context?

Sau khi hiểu ranh giới, mới chọn package và module để phản ánh nó. Nếu bắt đầu bằng cấu trúc technical layer rồi cố gắng gom nghiệp vụ vào sau, các phụ thuộc chéo thường đã hình thành trước khi ranh giới được làm rõ.

## 2. Dấu hiệu cấu trúc package đang làm mờ Bounded Context

Một số cấu trúc thường gặp khiến mô hình bị kết dính:

~~~text
com.acme.shop
  controller
  service
  repository
  entity
  dto
  util
~~~

Khi dự án lớn lên, package entity có thể chứa Customer, Order, Product, Invoice, Payment và Shipment. Package service chứa logic của tất cả các khái niệm. Từ góc nhìn package, mọi phần nghiệp vụ đều nằm cạnh nhau và dễ import lẫn nhau.

Những dấu hiệu khác:

- Sales import trực tiếp JPA entity hoặc repository của Billing.
- Inventory gọi một service nội bộ của Sales để thay đổi trạng thái đơn.
- Một package common chứa entity, enum và service được nhiều context dùng chung dù semantics khác nhau.
- Controller truy cập repository của context khác để dựng response.
- Một thay đổi nhỏ buộc phải sửa nhiều module vì các class nội bộ đã trở thành dependency công khai.
- Không thể xác định package nào chịu trách nhiệm cho một quy tắc nghiệp vụ.
- Unit test của một context cần khởi tạo nhiều context không liên quan.

Một cấu trúc package tốt cần làm cho ranh giới nghiệp vụ dễ nhận biết ngay khi mở cây thư mục và khiến các phụ thuộc không hợp lệ khó được tạo ra.

## 3. Tổ chức package theo Bounded Context

Với một modular monolith, một cách khởi đầu dễ hiểu là đặt package cấp cao theo bounded context:

~~~text
com.acme.shop
  sales
  inventory
  billing
  shipping
  identity
~~~

Mỗi context sở hữu mô hình và các thành phần triển khai của mình. Bên trong context có thể tiếp tục chia theo layer hoặc theo feature tùy quy mô.

Ví dụ:

~~~text
com.acme.shop
  sales
    api
    application
    domain
    infrastructure
  inventory
    api
    application
    domain
    infrastructure
  billing
    api
    application
    domain
    infrastructure
  shipping
    api
    application
    domain
    infrastructure
~~~

Nhìn vào cấu trúc, người đọc thấy Sales, Inventory, Billing và Shipping là các vùng nghiệp vụ riêng. Các package con biểu diễn trách nhiệm bên trong mỗi context.

### 3.1. Lợi ích của package-by-context

- Các khái niệm cùng ngôn ngữ nghiệp vụ nằm gần nhau.
- Có thể tìm owner của một quy tắc nhanh hơn.
- Giảm import chéo giữa các mô hình.
- Có thể đặt quy tắc dependency riêng cho từng context.
- Dễ tách một context thành module build hoặc service riêng nếu có lý do.
- Hỗ trợ review code theo ranh giới nghiệp vụ.

### 3.2. Không nên chia context chỉ theo bảng database

Hai bảng có quan hệ foreign key không nhất thiết thuộc cùng bounded context. Một Order có thể tham chiếu Customer, nhưng Sales và Identity/Customer Management có thể sở hữu các mô hình khác nhau. Ngược lại, một bounded context có thể dùng nhiều bảng để lưu một khái niệm.

Package nên phản ánh quyền sở hữu và ngôn ngữ nghiệp vụ, không phải sao chép nguyên xi cấu trúc schema.

## 4. Chia layer bên trong từng context

Trong mỗi bounded context, có thể chia các trách nhiệm như sau:

| Package | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| api | Adapter đầu vào và hợp đồng được công bố | REST controller, request/response DTO |
| application | Điều phối use case | command/query handler, application service |
| domain | Quy tắc và mô hình nghiệp vụ | aggregate, entity, value object, policy |
| infrastructure | Chi tiết kỹ thuật và adapter ra ngoài | JPA repository adapter, message publisher, HTTP client |

Ví dụ chi tiết:

~~~text
com.acme.shop.sales
  api
    OrderController.java
    CreateOrderRequest.java
    OrderResponse.java
  application
    PlaceOrderHandler.java
    ConfirmOrderHandler.java
    GetOrderDetailsHandler.java
    port
      CustomerInformation.java
      OrderRepository.java
  domain
    Order.java
    OrderId.java
    OrderLine.java
    Money.java
    OrderPricingPolicy.java
    OrderDomainService.java
  infrastructure
    persistence
      JpaOrderRepository.java
      OrderJpaEntity.java
    customer
      CustomerInformationAdapter.java
    messaging
      OrderEventPublisher.java
~~~

Đây là một cấu trúc minh họa. Dự án nhỏ có thể chưa cần chia sâu đến từng package; dự án lớn có thể chia domain theo subdomain hoặc aggregate. Điều quan trọng là không để layer technical trở thành nơi chứa logic của nhiều bounded context.

### 4.1. Domain không phụ thuộc adapter

Domain model nên độc lập với REST, JPA, message broker và framework. Nếu domain cần một khả năng bên ngoài, có thể định nghĩa port/interface theo ngôn ngữ cần thiết rồi để infrastructure triển khai.

Ví dụ, Sales có thể cần thông tin khách hàng để xác định điều kiện giá. Domain/application có thể dùng một abstraction như CustomerPricingInformation; adapter gọi API hoặc đọc contract được công bố từ context sở hữu thông tin đó.

Domain không nên import CustomerJpaEntity hoặc gọi trực tiếp RestTemplate/WebClient để lấy dữ liệu.

### 4.2. Application điều phối, domain quyết định

Application handler tải aggregate, gọi hành vi và lưu kết quả. Nó có thể điều phối transaction, authorization và message. Các invariant vẫn thuộc aggregate hoặc domain service.

Nếu application service của Sales gọi một repository của Inventory để sửa tồn kho, ranh giới context đã bị vượt qua. Thay vào đó, Sales gửi command hoặc yêu cầu qua contract mà Inventory công bố.

## 5. Package-by-layer và package-by-feature

Hai cách tổ chức thường gặp:

**Package-by-layer** gom class theo vai trò kỹ thuật, ví dụ controller, service, repository, entity.

**Package-by-feature/context** gom class theo năng lực hoặc vùng nghiệp vụ, ví dụ sales, inventory, billing.

| Tiêu chí | Package-by-layer | Package-by-feature/context |
| --- | --- | --- |
| Tìm class theo loại kỹ thuật | Dễ | Có thể phải vào package feature |
| Nhìn thấy ranh giới nghiệp vụ | Khó khi nhiều context | Rõ hơn |
| Thay đổi một feature | Có thể chạm nhiều package toàn cục | Thường tập trung trong một vùng |
| Kiểm soát phụ thuộc giữa context | Khó hơn nếu mọi class cùng layer | Dễ đặt rule theo context |
| Phù hợp | Ứng dụng nhỏ, ít vùng nghiệp vụ | Ứng dụng có nhiều capability/context |

Trong DDD, package cấp cao theo bounded context thường là điểm bắt đầu phù hợp. Bên trong mỗi context, nhóm có thể dùng layer hoặc feature tùy độ phức tạp.

### 5.1. Không cần chọn một cách cho toàn bộ package

Có thể tổ chức package cấp cao theo context, bên trong context dùng feature, và trong từng feature có một số layer. Ví dụ:

~~~text
sales
  order
    api
    application
    domain
    infrastructure
  pricing
    application
    domain
  customer-view
    application
    infrastructure
~~~

Cấu trúc này phù hợp khi Sales có nhiều capability nội bộ. Tuy nhiên, cần tránh chia nhỏ quá sớm khiến một use case đơn giản phải đi qua quá nhiều package.

## 6. Quy tắc phụ thuộc giữa các layer

Một cấu trúc package có ích khi nó đi cùng quy tắc dependency rõ ràng. Một hướng thường dùng:

~~~mermaid
flowchart TD
    API[API adapters] --> APP[Application]
    INFRA[Infrastructure adapters] --> APP
    APP --> DOMAIN[Domain model]
    APP --> PORTS[Ports / contracts]
    INFRA --> PORTS
    DOMAIN -->|Không phụ thuộc| INFRA
    DOMAIN -->|Không phụ thuộc| API
~~~

Diễn giải:

- API adapter gọi application use case.
- Application phụ thuộc vào domain model và các port cần thiết.
- Infrastructure triển khai port và kết nối công nghệ bên ngoài.
- Domain không phụ thuộc controller, JPA repository implementation, message broker hoặc framework.
- Infrastructure có thể phụ thuộc domain type nếu cần chuyển đổi hoặc lưu trữ, nhưng domain không gọi ngược infrastructure.

### 6.1. Dependency inversion

Nếu application cần lưu Order, nó có thể phụ thuộc vào interface OrderRepository được định nghĩa trong application/domain boundary. JPA adapter triển khai interface đó. Khi đó, application không cần biết Hibernate hoặc database cụ thể.

~~~java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void save(Order order);
}
~~~

~~~java
@Repository
public class JpaOrderRepository implements OrderRepository {
    private final SpringDataOrderJpaRepository repository;
    private final OrderMapper mapper;

    @Override
    public Optional<Order> findById(OrderId id) {
        return repository.findById(id.value())
                .map(mapper::toDomain);
    }

    @Override
    public void save(Order order) {
        repository.save(mapper.toEntity(order));
    }
}
~~~

Đây là ví dụ khái quát. Nếu domain aggregate được JPA quản lý trực tiếp, implementation có thể đơn giản hơn. Dù chọn cách nào, interface và implementation cần có owner rõ, và domain không được phụ thuộc vào class adapter.

### 6.2. Không để package name đánh lừa hướng phụ thuộc

Đặt package tên là domain không khiến nó tự động độc lập. Nếu class trong domain import Spring, JPA hoặc client HTTP, dependency vẫn tồn tại. Cần kiểm tra import và build graph, không chỉ dựa vào tên folder.

## 7. Phân biệt API công khai và implementation nội bộ của context

Một bounded context cần công bố một bề mặt giao tiếp đủ nhỏ để context khác sử dụng. Phần còn lại nên được xem là nội bộ.

Ví dụ, Sales có thể công bố:

- Command/API để yêu cầu đặt hoặc xác nhận đơn nếu context khác thực sự cần.
- Query contract để lấy thông tin đơn được phép chia sẻ.
- Integration event như OrderPlaced hoặc OrderConfirmed.
- DTO hoặc schema có semantics ổn định.

Sales không nên công bố:

- JPA entity và repository implementation.
- Collection nội bộ của aggregate.
- Các policy nội bộ chưa có ý nghĩa ngoài context.
- Class helper chỉ phục vụ implementation.
- Database table hoặc package structure như một hợp đồng tích hợp.

### 7.1. Public API không nhất thiết là REST API

Trong modular monolith, một context có thể công bố Java interface hoặc application contract nội bộ cho context khác. Khi cần giao tiếp bất đồng bộ, nó có thể công bố integration event. REST endpoint chỉ là một kiểu adapter.

Điều quan trọng là contract có ý nghĩa, được sở hữu và version hóa rõ; không phải giao thức cụ thể.

### 7.2. DTO công khai không phải domain entity

Một SalesOrderSummary có thể chứa order ID, trạng thái công khai và tổng tiền cần thiết. Context khác không cần import Sales Order aggregate hoặc truy cập OrderRepository. DTO công khai giúp producer giữ quyền thay đổi mô hình nội bộ.

## 8. Java access modifier giúp bảo vệ ranh giới thế nào?

Java cung cấp bốn mức truy cập thường gặp:

| Modifier | Phạm vi truy cập |
| --- | --- |
| private | Bên trong class khai báo |
| package-private (không ghi modifier) | Các class trong cùng package |
| protected | Cùng package và subclass theo quy tắc Java |
| public | Mọi nơi có thể truy cập type/member theo module/classpath visibility |

Package-private là công cụ hữu ích để giữ implementation nội bộ. Ví dụ, entity con và helper có thể không cần public nếu chỉ được aggregate root sử dụng trong cùng package.

~~~java
package com.acme.shop.sales.domain;

public final class Order {
    private final List<OrderLine> lines = new ArrayList<>();

    public void addLine(ProductId productId, Quantity quantity) {
        lines.add(new OrderLine(productId, quantity));
    }
}

final class OrderLine {
    private final ProductId productId;
    private final Quantity quantity;

    OrderLine(ProductId productId, Quantity quantity) {
        this.productId = productId;
        this.quantity = quantity;
    }
}
~~~

OrderLine không có modifier nên chỉ các class trong cùng package truy cập được. Điều này giúp hạn chế code bên ngoài package thao tác trực tiếp với entity con.

### 8.1. Subpackage không phải package con về access control

Một điểm rất dễ nhầm: com.acme.shop.sales.domain và com.acme.shop.sales.domain.order là hai package riêng biệt trong Java. Package-private member của package thứ nhất không tự động truy cập được từ package thứ hai.

Tên package có quan hệ phân cấp bằng dấu chấm chỉ là namespace; nó không tạo quan hệ visibility cha-con. Nếu cần package-private access, các class phải ở cùng package thực tế.

### 8.2. Public không có nghĩa là API công khai giữa bounded context

Một class public có thể được bất kỳ code nào trong cùng module/classpath truy cập nếu biết tên. Java package không tự ngăn context khác import class đó. Vì vậy, muốn giới hạn API công khai cần thêm module boundary hoặc công cụ kiểm tra kiến trúc.

### 8.3. Không lạm dụng protected

Protected thường hữu ích cho inheritance, nhưng dùng nó để “mở” domain entity cho các package khác có thể làm tăng coupling. Ưu tiên public behavior rõ ràng của aggregate root và giữ implementation không cần thiết ở package-private/private.

## 9. Dùng JPMS để định nghĩa module và exports

Java Platform Module System (JPMS, từ Java 9) cho phép khai báo module, dependency và package được export. Nó bổ sung một lớp kiểm soát ở cấp module bên cạnh access modifier.

Ví dụ, Sales module có thể khai báo:

~~~java
module com.acme.shop.sales {
    requires com.acme.shop.sharedkernel;

    exports com.acme.shop.sales.api;
    exports com.acme.shop.sales.contract;
}
~~~

Các package domain, application và infrastructure không được export ra module khác. Code bên trong Sales module vẫn có thể sử dụng các package đó theo visibility Java thông thường, nhưng module khác không thể truy cập public type ở package không được export theo cách thông thường của JPMS.

### 9.1. requires và exports

- requires khai báo module cần đọc.
- exports công bố package cho các module khác.
- exports ... to giới hạn package được export cho một số module cụ thể.
- opens cho phép reflection truy cập package theo nhu cầu, thường liên quan framework serialization hoặc persistence.

~~~java
module com.acme.shop.sales {
    requires com.acme.shop.sharedkernel;

    exports com.acme.shop.sales.contract
        to com.acme.shop.shipping;
}
~~~

Ví dụ này chỉ cho module Shipping đọc package contract của Sales. Cú pháp và cách cấu hình module cần phù hợp với phiên bản Java và framework được dùng.

### 9.2. JPMS không thay thế bounded context design

JPMS kiểm soát module dependency và package visibility. Nó không xác định thuật ngữ, ownership hay invariant nghiệp vụ. Một module Java có thể chứa nhiều bounded context nếu thiết kế sai; một bounded context cũng có thể được triển khai qua nhiều module.

### 9.3. Framework reflection cần được xem xét

Spring, JPA provider và thư viện serialization có thể cần reflection vào constructor, field hoặc package. Khi dùng JPMS, nhóm có thể cần opens có mục tiêu. Không nên mở toàn bộ package domain cho mọi module nếu chỉ một framework cần truy cập một số kiểu.

## 10. Tổ chức modular monolith theo bounded context

Một modular monolith triển khai nhiều bounded context trong một tiến trình và thường dùng một pipeline deploy, nhưng giữ module boundary rõ ràng.

Có thể tổ chức Maven multi-module:

~~~text
shop
  pom.xml
  shared-kernel
  sales
  inventory
  billing
  shipping
  application-bootstrap
~~~

Hoặc dùng một Gradle multi-project build với các project tương ứng. Mỗi module sở hữu package và API riêng. Bootstrap module lắp ghép các module và cấu hình runtime.

### 10.1. Khi nào dùng một module build duy nhất?

Một project Java duy nhất với package-by-context có thể đủ nếu:

- Nhóm nhỏ và codebase còn vừa phải.
- Build boundary chưa cần độc lập.
- Package rules và architecture tests được thực thi nghiêm.
- Việc tách module build sẽ tạo nhiều cấu hình hơn giá trị nhận được.

### 10.2. Khi nào tách Maven/Gradle module?

Tách module build hữu ích khi:

- Context có API công khai rõ và implementation nội bộ lớn.
- Muốn compiler/build tool kiểm soát dependency.
- Có thể build/test module độc lập.
- Nhiều nhóm phát triển sở hữu các context khác nhau.
- Cần chuẩn bị khả năng tách deployment sau này.

Không nên tạo module riêng cho từng aggregate nhỏ nếu các module vẫn phụ thuộc vòng tròn và không có API rõ. Khi đó chỉ làm build phức tạp hơn.

### 10.3. Không cần tách microservice để có bounded context

Bounded Context là ranh giới mô hình; nó không đồng nghĩa với microservice. Modular monolith có thể giữ nhiều context trong một deployment và giao tiếp qua interface/event nội bộ. Tách thành service riêng là quyết định triển khai dựa trên ownership, scale, team autonomy, availability và chi phí vận hành.

## 11. Ngăn phụ thuộc trực tiếp giữa các Bounded Context

Một nguyên tắc quan trọng: context khác chỉ nên phụ thuộc vào contract được công bố, không phụ thuộc implementation nội bộ.

Ví dụ không tốt:

~~~java
package com.acme.shop.shipping.application;

import com.acme.shop.sales.domain.Order;
import com.acme.shop.sales.infrastructure.persistence.JpaOrderRepository;

public class CreateShipmentHandler {
    private final JpaOrderRepository orders;
}
~~~

Shipping đang biết domain entity và persistence implementation của Sales. Khi Sales thay đổi aggregate hoặc ORM, Shipping bị ảnh hưởng.

Một hướng tốt hơn:

~~~java
package com.acme.shop.shipping.application;

public record ShipmentOrderData(
        String orderReference,
        List<ShipmentLineData> lines,
        DeliveryAddressData destination
) {}

public interface SalesOrderInformation {
    Optional<ShipmentOrderData> findForShipment(String orderReference);
}
~~~

Adapter của Shipping gọi contract được công bố bởi Sales hoặc tiêu thụ integration event tương ứng. Trong một modular monolith, implementation có thể được wiring bằng dependency injection mà không làm Shipping import repository nội bộ của Sales.

### 11.1. Dùng ID thay vì chia sẻ entity

Khi hai context liên quan đến cùng một đối tượng ngoài đời, thường nên trao đổi reference ID hoặc một contract snapshot phù hợp. Không cần chia sẻ cùng một Customer entity giữa Sales, Billing và Identity.

Ví dụ:

- Sales dùng Buyer trong ngôn ngữ bán hàng.
- Billing dùng AccountDebtor hoặc Payer trong ngôn ngữ thanh toán.
- Identity dùng UserAccount cho xác thực.

Các context có thể lưu external reference hoặc mapping giữa ID. Chúng không cần dùng chung một class Customer với mọi trường của tất cả các context.

### 11.2. Anti-Corruption Layer

Nếu một context phải tiêu thụ contract hoặc mô hình từ context khác, Anti-Corruption Layer (ACL) chuyển đổi dữ liệu và semantics bên ngoài thành mô hình nội bộ. ACL giúp mô hình của consumer không bị chi phối bởi tên và cấu trúc của producer.

ACL có thể gồm adapter, mapper, translator và các port cần thiết. Nó không nên trở thành một lớp chuyển tiếp rỗng; trách nhiệm chính là bảo vệ ngôn ngữ và mô hình của context tiêu thụ.

## 12. Shared Kernel và package common

Shared Kernel là một phần mô hình được hai hoặc nhiều bounded context thống nhất chia sẻ và cùng chịu trách nhiệm thay đổi. Nó có phạm vi nhỏ, được quản trị rõ và có sự phối hợp giữa các nhóm.

Không nên biến shared-kernel hoặc common thành nơi gom mọi class được dùng ở nhiều nơi. Những class như Customer, OrderStatus, PaymentEntity hoặc một service tiện ích nghiệp vụ không tự động phù hợp để chia sẻ.

### 12.1. Những gì có thể phù hợp để chia sẻ

- Kiểu ID hoặc primitive wrapper thật sự có semantics chung.
- Một số value object kỹ thuật hoặc domain-neutral đã được thống nhất.
- Kiểu tiền tệ/đơn vị nếu cùng một định nghĩa và quy tắc.
- Contract hoặc event schema được các bên đồng sở hữu.

Ngay cả với các kiểu trên, cần xem xét chúng có thật sự cùng nghĩa trong các context hay chỉ trùng cấu trúc.

### 12.2. Khi nào không nên chia sẻ?

Nếu Sales và Billing dùng từ Customer với các quy tắc và dữ liệu khác nhau, không nên tạo một Customer class dùng chung chỉ để giảm số dòng mapping. Mapping giữa hai mô hình có thể là chi phí cần thiết để giữ ranh giới.

Shared Kernel lớn dần thường tạo coupling: thay đổi một field buộc nhiều context nâng cấp cùng lúc. Hãy giữ nó nhỏ và có owner/decision process rõ ràng.

## 13. Kiểm soát phụ thuộc bằng ArchUnit

Package convention chỉ có tác dụng nếu được kiểm tra. ArchUnit cho phép viết test kiến trúc dựa trên package, class và dependency bytecode.

Ví dụ, cấm Sales phụ thuộc trực tiếp vào package nội bộ của Billing:

~~~java
@AnalyzeClasses(packages = "com.acme.shop")
class BoundedContextDependencyTest {

    @ArchTest
    static final ArchRule salesMustNotDependOnBillingInternals =
            noClasses()
                    .that().resideInAPackage("..sales..")
                    .should().dependOnClassesThat()
                    .resideInAnyPackage(
                            "..billing.domain..",
                            "..billing.application..",
                            "..billing.infrastructure.."
                    );
}
~~~

Quy tắc minh họa dùng package pattern; cần điều chỉnh theo cấu trúc thật. Nếu Billing công bố contract trong package billing.api hoặc billing.contract, Sales có thể được phép phụ thuộc vào đúng package đó.

### 13.1. Quy định hướng phụ thuộc bên trong context

Có thể viết rule cấm domain phụ thuộc vào infrastructure hoặc API:

~~~java
@ArchTest
static final ArchRule salesDomainMustNotDependOnAdapters =
        noClasses()
                .that().resideInAPackage("..sales.domain..")
                .should().dependOnClassesThat()
                .resideInAnyPackage(
                        "..sales.api..",
                        "..sales.infrastructure.."
                );
~~~

Nếu domain package có subpackage, pattern cần bao phủ đúng phạm vi. Cũng cần nhớ rằng dependency có thể phát sinh qua annotation, generic type, method signature hoặc field, không chỉ câu import nhìn thấy trong một file.

### 13.2. Kiểm tra vòng phụ thuộc

Vòng phụ thuộc giữa package làm thay đổi khó kiểm soát. ArchUnit có thể kiểm tra:

~~~java
@ArchTest
static final ArchRule boundedContextPackagesShouldBeFreeOfCycles =
        slices()
                .matching("com.acme.shop.(*)..")
                .should().beFreeOfCycles();
~~~

Quy tắc này cần được điều chỉnh để các slice tương ứng với package context thực tế, không gom nhầm package bootstrap hoặc shared kernel vào cùng pattern.

### 13.3. Đưa architecture test vào CI

Architecture test nên chạy cùng unit test trong pipeline build. Khi một developer thêm dependency chéo không được phép, build báo lỗi sớm và chỉ rõ rule bị vi phạm. Rule cần có tên mô tả và thông báo dễ hiểu để không trở thành một tập lỗi khó xử lý.

## 14. Spring Modulith hỗ trợ ranh giới module ứng dụng

Spring Modulith là một dự án thuộc hệ sinh thái Spring giúp mô hình hóa và kiểm tra application module dựa trên package structure. Nó có thể hỗ trợ phát hiện dependency giữa các module, công bố interface và kiểm thử module trong một ứng dụng Spring.

Ví dụ, các package cấp cao như sales, inventory và billing có thể được xem là các application module. Nhóm có thể khai báo metadata module và kiểm tra dependency theo quy ước của phiên bản Spring Modulith đang dùng.

~~~java
@org.springframework.modulith.ApplicationModule
package com.acme.shop.sales;
~~~

Một module có thể công bố API hoặc event được phép sử dụng từ module khác; các package nội bộ nên được giữ kín theo cơ chế module của Spring Modulith.

### 14.1. Kiểm tra cấu trúc module

Trong test, có thể dùng ApplicationModules để xác minh cấu trúc:

~~~java
class ApplicationModuleStructureTest {
    @Test
    void modulesShouldRespectTheirBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Cú pháp và API có thể khác theo phiên bản Spring Modulith. Hãy đối chiếu dependency và tài liệu của phiên bản dự án đang sử dụng trước khi áp dụng trực tiếp.

### 14.2. Spring Modulith không thay thế phân tích domain

Công cụ kiểm tra package dependency, module exposure và một số quy tắc ứng dụng. Nó không thể quyết định Sales và Billing có thực sự là hai bounded context hay một thuật ngữ đã được hiểu đúng. Những quyết định đó vẫn cần knowledge crunching và trao đổi với chuyên gia.

### 14.3. ArchUnit và Spring Modulith có thể bổ trợ nhau

ArchUnit linh hoạt cho các rule dependency ở cấp package/class. Spring Modulith cung cấp cách mô hình hóa application module trong hệ sinh thái Spring. Có thể dùng một hoặc cả hai tùy yêu cầu; tránh lặp các rule giống nhau ở nhiều công cụ mà không có lý do.

## 15. Spring component scanning và dependency injection

Spring giúp wiring các component bằng dependency injection, nhưng DI không tự bảo vệ bounded context. Nếu mọi package đều được scan và mọi bean đều có thể inject lẫn nhau, một context có thể vô tình gọi service nội bộ của context khác.

Nhóm nên:

- Đặt package và module boundary rõ trước khi cấu hình component scanning.
- Dùng constructor injection để dependency nhìn thấy rõ trong class.
- Chỉ inject contract công khai, không inject repository implementation nội bộ của context khác.
- Giới hạn configuration và bean exposure theo module khi cần.
- Tránh một service locator hoặc application context lookup cho phép truy cập bean tùy ý.
- Dùng architecture test để kiểm tra dependency graph, không dựa vào convention trong code review בלבד.

### 15.1. DI không làm dependency biến mất

Một class có constructor nhận BillingInternalService vẫn phụ thuộc BillingInternalService dù Spring tạo object đó. Dependency injection thay cách khởi tạo, không thay đổi hướng phụ thuộc.

### 15.2. Tránh circular dependency

Nếu Sales service cần Billing service và Billing service lại cần Sales service, có thể hai context đang chia sẻ trách nhiệm không rõ. Hãy xác định event, contract hoặc process điều phối phù hợp. Dùng lazy injection hoặc cấu hình để phá vòng ở runtime có thể che giấu vấn đề thiết kế thay vì giải quyết nó.

## 16. Đặt tên package và class theo ngôn ngữ miền

Package cấp context nên dùng tên ngắn, ổn định và dễ nhận biết. Trong Java, package name thường viết chữ thường và theo dạng reverse domain name.

Ví dụ:

~~~text
com.acme.shop.sales
com.acme.shop.inventory
com.acme.shop.billing
~~~

Trong context, tên class nên theo Ubiquitous Language:

- Sales có Order, Buyer, OrderPricingPolicy.
- Inventory có StockItem, Reservation, AvailableQuantity.
- Billing có Invoice, PaymentAuthorization, Refund.
- Shipping có Shipment, DeliveryRoute, DeliveryWindow.

Không nên ép mọi context dùng chung một class chỉ vì tên ngoài đời giống nhau. Nếu hai khái niệm có ý nghĩa khác, hãy đặt tên theo context để người đọc phân biệt được.

### 16.1. Tránh tên package quá kỹ thuật ở cấp cao

Package gốc như entity, manager, common, service hoặc util không nói rõ vùng nghiệp vụ. Chúng có thể tồn tại bên trong context, nhưng không nên thay thế tên bounded context.

### 16.2. Không đặt package theo team nếu team không phải ranh giới mô hình

Tên package theo team có thể thay đổi khi tổ chức đổi nhân sự. Bounded Context phản ánh ranh giới nghiệp vụ và mô hình, thường ổn định hơn cấu trúc nhân sự. Team có thể sở hữu một hoặc nhiều context, nhưng package nên thể hiện domain.

## 17. Ví dụ tổng thể: modular monolith bán hàng

Giả sử ứng dụng thương mại điện tử có bốn bounded context: Sales, Inventory, Billing và Shipping. Cấu trúc package có thể như sau:

~~~text
com.acme.shop
  sales
    api
    contract
    application
    domain
    infrastructure
  inventory
    api
    contract
    application
    domain
    infrastructure
  billing
    api
    contract
    application
    domain
    infrastructure
  shipping
    api
    contract
    application
    domain
    infrastructure
  bootstrap
  sharedkernel
~~~

Một số quy tắc dependency:

| Nguồn | Được phép phụ thuộc | Không được phụ thuộc |
| --- | --- | --- |
| sales.api | sales.application, sales.contract | billing.infrastructure, inventory.domain |
| sales.application | sales.domain, port/contract cần thiết | inventory.repository implementation |
| sales.domain | Kiểu miền nội bộ và abstraction thuần | Spring, JPA, REST client, package của context khác |
| sales.infrastructure | sales.domain/application ports, thư viện kỹ thuật | Quy tắc nội bộ của Billing |
| shipping.application | shipping.domain, contract Sales được công bố | sales.domain.Order, sales.infrastructure.JpaOrderRepository |
| bootstrap | Các module công khai để wiring | Truy cập sâu implementation nội bộ nếu không cần |

### 17.1. Luồng giao tiếp giữa Sales và Inventory

Khi Sales đặt đơn, nó không gọi InventoryRepository để sửa số lượng. Có thể có một trong các cách:

- Sales gửi command ReserveStock đến contract của Inventory.
- Sales phát event OrderPlaced và Inventory phản ứng theo choreography.
- Một Process Manager điều phối bước giữ hàng và các bước tiếp theo.

Inventory nhận yêu cầu, tự kiểm tra tồn và tạo reservation theo invariant của mình. Sales nhận kết quả qua event hoặc contract và cập nhật trạng thái đơn phù hợp.

### 17.2. Bootstrap là composition root

Package bootstrap lắp ghép module, cấu hình bean, transaction manager, broker và runtime. Nó có thể biết nhiều module để wiring, nhưng không nên trở thành nơi chứa quy tắc nghiệp vụ. Nếu bootstrap import sâu class nội bộ, cần xem xét API module và cơ chế cấu hình.

## 18. Khi nào nên tách module hoặc microservice?

Package-by-context là bước đầu. Khi một context cần build, test, release hoặc scale độc lập hơn, có thể cân nhắc module build riêng. Khi cần triển khai độc lập và giao tiếp qua network, có thể cân nhắc microservice.

| Lựa chọn | Khi phù hợp | Chi phí cần cân nhắc |
| --- | --- | --- |
| Package trong một project | Codebase nhỏ, boundary được kiểm tra bằng test | Compiler không ngăn mọi dependency chéo |
| Maven/Gradle module | Cần dependency/build boundary rõ | Cấu hình build và versioning nội bộ |
| JPMS module | Cần module readability và package exports ở runtime/compile time | Tích hợp framework và reflection cần cấu hình |
| Spring Modulith | Ứng dụng Spring cần application module boundary | Thêm quy ước và công cụ kiểm tra |
| Microservice | Cần deployment autonomy, scaling hoặc isolation thực sự | Network, observability, distributed consistency, vận hành |

Không nên tách microservice chỉ để sửa một package lớn. Trước hết, cần làm rõ ownership, contract, dependency và quy trình giao tiếp. Một modular monolith có ranh giới tốt thường là nền tảng phù hợp để quyết định tách service sau này.

## 19. Các bước di chuyển từ cấu trúc package theo layer sang theo context

Không nhất thiết viết lại toàn bộ ứng dụng. Có thể chuyển dần:

### Bước 1: Lập bản đồ bounded context

Liệt kê các năng lực nghiệp vụ, thuật ngữ, aggregate và dữ liệu được sở hữu. Xác định các context và quan hệ giữa chúng.

### Bước 2: Gắn class hiện tại với owner

Với từng controller, service, entity và repository, xác định context sở hữu. Nếu class phục vụ nhiều context, tìm xem nó đang chứa nhiều trách nhiệm hay là contract thật sự cần chia sẻ.

### Bước 3: Tạo package cấp context

Tạo package sales, inventory, billing, shipping. Di chuyển các class theo owner, giữ thay đổi nhỏ và đảm bảo build/test sau mỗi bước.

### Bước 4: Tách contract khỏi implementation

Xác định các type cần công bố. Tạo DTO, interface hoặc event contract riêng. Giữ entity, repository implementation và policy nội bộ ở package không công bố.

### Bước 5: Thay import chéo bằng contract

Tìm các dependency trực tiếp giữa context. Thay bằng API, port/adapter, query contract hoặc event phù hợp. Không chỉ đổi tên package mà giữ nguyên coupling.

### Bước 6: Định hướng dependency bên trong context

Đảm bảo adapter gọi application, application dùng domain và port, infrastructure triển khai port. Domain không import framework hoặc adapter.

### Bước 7: Thêm architecture tests

Viết ArchUnit hoặc Spring Modulith verification để khóa các quy tắc mới. Chạy trong CI và xử lý các vi phạm còn lại theo lộ trình.

### Bước 8: Tách build module nếu có lợi ích

Sau khi dependency graph ổn định, cân nhắc Maven/Gradle module hoặc JPMS. Không tách trước khi biết API công khai và dependency thực tế.

### Bước 9: Duy trì ranh giới qua code review

Mỗi dependency mới giữa context cần có lý do và contract rõ. Khi thêm một shared type, cần xác nhận semantics có thật sự giống nhau và ai sở hữu thay đổi.

## 20. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| Chia package chỉ theo controller/service/repository | Ranh giới nghiệp vụ bị phân tán | Đặt package cấp cao theo bounded context |
| Coi package là bounded context | Tên folder không phản ánh mô hình thật | Xác định ownership và Ubiquitous Language trước |
| Cho context import entity/repository nội bộ của nhau | Coupling vào implementation và schema | Công bố contract/port/event |
| Dùng common để gom mọi class dùng chung | Shared kernel phình to và làm các context phụ thuộc nhau | Chỉ chia sẻ khái niệm thật sự có cùng semantics |
| Nghĩ subpackage kế thừa package-private access | Lỗi compile hoặc phải mở class không cần thiết | Nhớ rằng mỗi package là một namespace/access boundary riêng |
| Cho rằng public class là API được kiểm soát | Context khác có thể import implementation tùy ý | Dùng JPMS, module build hoặc architecture tests |
| Để domain phụ thuộc Spring/JPA | Mô hình bị khóa vào framework | Đưa abstraction và adapter về đúng hướng |
| Dùng DI để che dependency chéo | Runtime graph vẫn kết dính | Kiểm tra dependency graph và giới hạn contract |
| Tạo Maven module cho mọi aggregate | Build phức tạp và dependency vụn | Tách theo bounded context/capability có ownership rõ |
| Tách microservice chỉ để chia folder | Tăng distributed-system complexity | Bắt đầu bằng modular monolith |
| Dùng package rule nhưng không kiểm tra trong CI | Vi phạm quay lại theo thời gian | Thêm ArchUnit/Spring Modulith verification |
| Dùng một DTO chung cho nhiều context | Consumer bị phụ thuộc vào mô hình producer | Tạo contract và mapping theo context |

## 21. Nguyên tắc thực hành

Khi tổ chức package Java theo Bounded Context và ngăn phụ thuộc chéo, nhóm nên nhớ:

- **Xác định ranh giới nghiệp vụ trước.** Package chỉ phản ánh quyết định domain đã được làm rõ.
- **Đặt context ở cấp package cao.** Sales, Inventory, Billing và Shipping cần có vùng sở hữu dễ nhận biết.
- **Tổ chức layer bên trong context.** API, application, domain và infrastructure có trách nhiệm khác nhau.
- **Giữ domain độc lập với framework.** Domain không phụ thuộc REST, JPA, broker hoặc Spring.
- **Công bố contract nhỏ.** Context khác chỉ dùng API, DTO hoặc event được công bố.
- **Không chia sẻ entity/repository nội bộ.** Dùng ID, contract và ACL khi cần trao đổi.
- **Hiểu đúng Java visibility.** Package-private chỉ áp dụng trong cùng package; subpackage không có quyền đặc biệt.
- **Dùng JPMS khi cần module enforcement.** Exports công bố package, requires khai báo dependency, opens chỉ dùng có mục tiêu.
- **Kiểm tra dependency bằng công cụ.** ArchUnit hoặc Spring Modulith giúp biến quy tắc thành kiểm tra tự động.
- **Tách build module theo nhu cầu.** Không cần module hoặc microservice riêng cho mọi aggregate.
- **Giữ Shared Kernel nhỏ.** Chỉ chia sẻ khái niệm có semantics thật sự giống nhau và có quản trị chung.
- **Không nhầm DI với dependency inversion.** Inject implementation nội bộ của context khác vẫn là coupling.
- **Tiến hóa từng bước.** Di chuyển package, thay dependency và thêm rule theo từng lát nhỏ.

Tổ chức package theo bounded context giúp codebase phản ánh cách doanh nghiệp chia miền và sở hữu quy tắc. Nhưng tên package chỉ là lớp biểu diễn đầu tiên. Để ranh giới thực sự có hiệu lực, nhóm cần công bố contract nhỏ, giữ implementation nội bộ, định hướng dependency, dùng visibility/module phù hợp và kiểm tra kiến trúc trong CI. Một modular monolith có các context độc lập về mô hình và được kết nối qua hợp đồng rõ ràng có thể phát triển lâu dài mà chưa cần tách thành nhiều dịch vụ triển khai riêng.

## 22. Câu hỏi tự kiểm tra

1. Bounded Context khác Java package, Maven module và JPMS module như thế nào?
2. Vì sao nên xác định ownership và Ubiquitous Language trước khi tổ chức package?
3. Package-by-layer và package-by-context có ưu/nhược điểm gì trong một ứng dụng DDD?
4. Trách nhiệm của api, application, domain và infrastructure package là gì?
5. Vì sao domain model không nên phụ thuộc JPA, Spring hoặc HTTP client?
6. Làm thế nào để context khác sử dụng contract mà không import aggregate/repository nội bộ?
7. Package-private có giới hạn gì và vì sao subpackage không được xem là cùng package?
8. JPMS requires, exports và opens có vai trò gì?
9. ArchUnit có thể kiểm tra những quy tắc dependency nào?
10. Spring Modulith hỗ trợ kiểm tra ranh giới ứng dụng ra sao và giới hạn của nó là gì?
11. Vì sao DI không tự động loại bỏ dependency chéo hoặc circular dependency?
12. Shared Kernel khác package common tổng quát như thế nào?
13. Khi nào nên tách Maven/Gradle module hoặc microservice?
14. Hãy chọn một hệ thống có ít nhất ba bounded context, đề xuất cây package Java, API công khai và các rule cần đưa vào architecture test.

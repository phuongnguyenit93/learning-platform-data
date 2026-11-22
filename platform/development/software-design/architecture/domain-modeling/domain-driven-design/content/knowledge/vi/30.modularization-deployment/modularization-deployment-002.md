# Thiết kế ứng dụng nguyên khối có mô-đun theo ranh giới miền

Một ứng dụng nguyên khối có mô-đun (modular monolith) được triển khai như một ứng dụng thống nhất nhưng bên trong có các mô-đun với trách nhiệm, dữ liệu và hợp đồng rõ ràng. Cách tổ chức này phù hợp khi doanh nghiệp muốn giữ sự đơn giản của một đơn vị triển khai, đồng thời cần ngăn các phần nghiệp vụ phụ thuộc tùy tiện vào nhau.

Trong Domain-Driven Design (DDD), ranh giới mô-đun nên phản ánh cách tổ chức hiểu và vận hành nghiệp vụ. Sales, Fulfillment, Billing và Payment có thể là những mô hình riêng dù cùng chạy trong một tiến trình Java. Mỗi mô-đun sở hữu logic và dữ liệu của mình, công bố một bề mặt giao tiếp nhỏ, và không cho mô-đun khác truy cập trực tiếp vào chi tiết nội bộ.

Modular monolith không phải là một bước microservices bị trì hoãn. Nó là một lựa chọn kiến trúc có giá trị riêng: triển khai đơn giản, gọi nội bộ nhanh và có thể dùng transaction cục bộ khi phù hợp, nhưng vẫn giữ ranh giới để thay đổi từng phần mà không làm toàn hệ thống rối chặt. Bài học này trình bày cách xác định mô-đun theo Bounded Context, thiết kế API và dependency direction, quản lý dữ liệu và giao tiếp, kiểm tra ranh giới bằng automated architecture tests, rồi tiến hóa ứng dụng theo nhu cầu thực tế.

## 1. Modular monolith là gì?

### 1.1. Một đơn vị triển khai, nhiều mô-đun có ranh giới

Một modular monolith thường có:

- Một ứng dụng chính được khởi động và triển khai như một đơn vị.
- Nhiều mô-đun nội bộ đại diện cho các năng lực hoặc mô hình nghiệp vụ.
- API nội bộ được công bố có chủ đích giữa các mô-đun.
- Quyền sở hữu rõ ràng đối với logic và dữ liệu.
- Quy tắc dependency ngăn việc truy cập tùy tiện vào implementation của mô-đun khác.

Ví dụ một nền tảng thương mại điện tử có thể chạy trong một tiến trình Spring Boot:

~~~text
Commerce Application
|
+-- Sales
|   +-- Domain
|   +-- Application
|   +-- Infrastructure
|   +-- Public API
|
+-- Fulfillment
|   +-- Domain
|   +-- Application
|   +-- Infrastructure
|   +-- Public API
|
+-- Billing
|   +-- Domain
|   +-- Application
|   +-- Infrastructure
|   +-- Public API
|
+-- Payment
    +-- Domain
    +-- Application
    +-- Infrastructure
    +-- Public API
~~~

Các mô-đun có thể được đóng gói trong một artifact hoặc được biên dịch từ nhiều build module nhưng cuối cùng vẫn chạy như một ứng dụng. Số lượng JAR không quyết định hệ thống có phải modular monolith hay không; điều quan trọng là ranh giới phụ thuộc và quyền sở hữu có được thực thi hay không.

### 1.2. Phân biệt monolith có mô-đun với monolith nguyên khối tùy tiện

Một codebase có nhiều package chưa chắc đã có kiến trúc mô-đun.

Monolith thiếu ranh giới thường có:
- Bất kỳ package nào cũng gọi repository của package khác.
- Entity được chia sẻ rộng khắp.
- Mô-đun phụ thuộc vào implementation nội bộ của nhau.
- Một thay đổi nhỏ phải sửa nhiều phần không liên quan.
- Không có quy tắc kiểm tra dependency.

Modular monolith có:
- Public API được xác định rõ.
- Implementation được giữ kín.
- Dữ liệu có module owner.
- Giao tiếp theo hợp đồng ổn định.
- Dependency được kiểm tra tự động.
- Mỗi mô-đun có thể được hiểu và thay đổi trong phạm vi trách nhiệm của nó.

### 1.3. Modular monolith vẫn có thể có một database

Một ứng dụng có thể dùng cùng một database server hoặc một database vật lý. Điều đó không có nghĩa mọi mô-đun được quyền đọc và ghi mọi bảng.

Có thể dùng schema riêng cho từng mô-đun, hoặc dùng quy ước bảng và quyền truy cập để thể hiện ownership. Ranh giới logic phải tồn tại ngay cả khi hạ tầng lưu trữ được chia sẻ.

## 2. Vì sao tổ chức mô-đun theo ranh giới miền?

### 2.1. Giảm coupling giữa các năng lực nghiệp vụ

Khi Sales cần xác nhận đơn, nó không nên biết cách Fulfillment phân bổ kho hoặc Billing tạo chứng từ. Sales chỉ cần công bố rằng đơn đã được xác nhận theo hợp đồng phù hợp.

Nếu Sales gọi trực tiếp các repository nội bộ của Fulfillment và Billing, các mô hình sẽ phụ thuộc vào cấu trúc lưu trữ và lifecycle của nhau. Khi Fulfillment thay đổi cách lưu picking task, Sales có thể phải thay đổi dù quy tắc bán hàng không đổi.

### 2.2. Giữ ngôn ngữ riêng cho từng Bounded Context

DDD cho phép cùng một từ có ý nghĩa khác nhau trong những Bounded Context khác nhau.

Ví dụ:
- SalesOrder là cam kết thương mại với người mua.
- FulfillmentOrder là công việc thực hiện lấy và giao hàng.
- Invoice là chứng từ kế toán.
- Payment là trạng thái và lịch sử xử lý tiền.

Không nên ép các khái niệm này dùng chung một Entity Order chỉ vì chúng liên quan đến cùng giao dịch.

### 2.3. Tạo đường tiến hóa có kiểm soát

Một mô-đun có hợp đồng rõ ràng có thể được thay đổi nội bộ mà ít ảnh hưởng consumer. Nếu một năng lực sau này cần triển khai độc lập, module API và event contract đã là điểm bắt đầu để tách.

Tuy nhiên, khả năng tách sau này là lợi ích phụ. Không cần thiết kế mọi mô-đun như một microservice tương lai nếu điều đó làm code phức tạp ngay hôm nay.

### 2.4. Tăng khả năng hiểu và kiểm thử

Khi trách nhiệm được gom theo năng lực nghiệp vụ:
- Test domain tập trung vào invariant của mô-đun.
- Integration test tập trung vào adapter và persistence của mô-đun.
- Architecture test kiểm tra dependency giữa mô-đun.
- Người phát triển có thể tìm logic theo nghiệp vụ thay vì phải đi qua nhiều package kỹ thuật toàn cục.

## 3. Phân biệt Bounded Context, module và deployable

Ba khái niệm này liên quan nhưng không đồng nghĩa.

| Khái niệm | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Bounded Context | Mô hình và ngôn ngữ nào có ý nghĩa nhất quán? | Sales Context |
| Application module | Phần code nào sở hữu năng lực và hợp đồng cụ thể? | sales module |
| Build module | Đơn vị biên dịch và quản lý dependency nào? | Gradle subproject sales |
| Deployable | Thành phần nào được đóng gói và triển khai độc lập? | commerce-app.jar |

### 3.1. Bounded Context thường là cơ sở tốt để chia module

Nếu Sales và Fulfillment có mô hình, quy tắc và nhóm chịu trách nhiệm khác nhau, tạo hai application module riêng thường giúp giữ ranh giới rõ.

Một Bounded Context có thể cần nhiều build module vì lý do kỹ thuật, chẳng hạn sales-api, sales-domain và sales-infrastructure. Ngược lại, một build module không tự động là một Bounded Context nếu nó chứa nhiều mô hình nghiệp vụ không liên quan.

### 3.2. Không chia module chỉ theo tầng kỹ thuật toàn hệ thống

Cấu trúc kiểu:

~~~text
com.example
    controller
    service
    repository
    entity
~~~

có thể khiến một use case phải đi qua nhiều package toàn cục và làm ranh giới nghiệp vụ khó nhìn thấy. Người phát triển tìm chức năng Sales phải tìm ở controller, service, repository và entity riêng biệt.

Cấu trúc theo năng lực thường dễ hiểu hơn:

~~~text
com.example.commerce
    sales
        api
        application
        domain
        infrastructure
    fulfillment
        api
        application
        domain
        infrastructure
    billing
        api
        application
        domain
        infrastructure
~~~

Đây là cách tổ chức tham khảo; một mô-đun nhỏ không cần tạo đủ mọi package nếu không có nội dung tương ứng.

### 3.3. Một module không nhất thiết phải là một microservice

Module là ranh giới tổ chức code và ownership. Microservice là một đơn vị triển khai/vận hành độc lập có giao tiếp qua mạng và các vấn đề phân tán đi kèm.

Có thể có nhiều module trong một service. Cũng có thể một Bounded Context lớn được triển khai bằng nhiều thành phần. Không suy ra topology triển khai chỉ từ tên package.

## 4. Xác định ranh giới mô-đun

### 4.1. Bắt đầu từ capability và trách nhiệm nghiệp vụ

Hãy hỏi:
- Năng lực nghiệp vụ nào được cung cấp?
- Ai chịu trách nhiệm cho quy tắc và kết quả?
- Những dữ liệu nào có cùng vòng đời?
- Những thay đổi nào thường xảy ra cùng nhau?
- Mô hình nào cần được bảo vệ khỏi ngôn ngữ của mô hình khác?

Ví dụ một nền tảng thương mại có thể có:
- Catalog: quản lý thông tin sản phẩm và khả năng bán.
- Sales: quản lý cam kết thương mại.
- Fulfillment: quản lý thực hiện đơn và giao hàng.
- Billing: quản lý hóa đơn và điều chỉnh.
- Payment: quản lý authorization, capture, refund.
- Customer: quản lý hồ sơ khách hàng.

Tên và phạm vi phải được xác nhận bằng hiểu biết nghiệp vụ, không lấy danh sách bảng database làm nguồn duy nhất.

### 4.2. Dùng Context Map để xem quan hệ

Context Map cho biết các Bounded Context tương tác và phụ thuộc như thế nào.

~~~text
Catalog
   |
   | Product information / Published Language
   v
Sales
   |
   | SalesOrderConfirmed
   +---------------------> Fulfillment
   |
   +---------------------> Billing

Payment <----------------> Sales
       PaymentAuthorized / PaymentFailed

Fulfillment ----------------> Sales
             DeliveryCompleted
~~~

Sơ đồ chỉ là giả định minh họa. Hướng event, đồng bộ hay bất đồng bộ phải theo quy trình thật và quyền sở hữu của từng nhóm.

### 4.3. Không tạo module cho mọi Entity

Một Entity hoặc bảng không tự động cần một module. Các đối tượng cùng phục vụ một mô hình và cùng chịu trách nhiệm cho invariant có thể thuộc một module.

Ví dụ OrderLine thường thuộc SalesOrder Aggregate trong Sales, không cần một module OrderLine riêng.

### 4.4. Tránh module dùng chung quá rộng

Một module common hoặc shared có thể hữu ích cho một số primitive kỹ thuật ổn định, nhưng nếu chứa Customer, Order, Product, Money và các service nghiệp vụ được mọi nơi sử dụng, nó có thể trở thành nơi tập trung coupling.

Chỉ chia sẻ những khái niệm thực sự có cùng semantics và được quản lý chung. Nếu cùng một từ có ý nghĩa khác nhau theo context, hãy giữ kiểu riêng và chuyển đổi ở ranh giới.

## 5. Thiết kế cấu trúc module trong Java

### 5.1. Cấu trúc package theo năng lực

Ví dụ:

~~~text
src/main/java/com/acme/commerce
    CommerceApplication.java

    sales
        api
            SalesOrderCommands.java
            SalesOrderQueries.java
            SalesOrderConfirmed.java
        application
            ConfirmSalesOrderHandler.java
            GetSalesOrderSummaryHandler.java
        domain
            SalesOrder.java
            SalesOrderId.java
            SalesOrderLine.java
            Money.java
            SalesOrderRepository.java
        infrastructure
            JpaSalesOrderRepository.java
            SalesOrderEntity.java

    fulfillment
        api
            FulfillmentCommands.java
            DeliveryCompleted.java
        application
        domain
        infrastructure

    billing
        api
        application
        domain
        infrastructure
~~~

Các package api, application, domain, infrastructure là cách chia nội bộ của mỗi module. Public API không nên expose các lớp trong domain hoặc infrastructure nếu consumer không cần biết chúng.

### 5.2. Phân biệt public API và implementation

Một module có thể công bố:
- Command hoặc query request/response.
- Interface hoặc facade để gọi use case.
- Integration event và schema.
- Kiểu ID hoặc Value Object chỉ khi chúng thực sự thuộc hợp đồng.

Nên giữ kín:
- JPA Entity.
- Spring Data Repository.
- Aggregate Root nội bộ.
- Mapping database.
- Domain service nội bộ.
- Helper và factory chỉ phục vụ implementation.

Ví dụ public API:

~~~java
package com.acme.commerce.sales.api;

public interface SalesOrderCommands {
    ConfirmationResult confirm(ConfirmSalesOrder command);
}

public record ConfirmSalesOrder(
    String salesOrderId,
    String buyerId
) {
}

public record ConfirmationResult(
    String salesOrderId,
    String status
) {
}
~~~

Consumer phụ thuộc vào hợp đồng này. Nó không cần biết Sales dùng Hibernate, bảng nào hoặc Aggregate được dựng ra sao.

### 5.3. Đừng trả Entity qua module boundary

Không nên công bố repository trả về SalesOrder domain object nếu SalesOrder và SalesOrderId là kiểu nội bộ mà consumer không được phép sử dụng.

Thay vào đó, module API có thể trả DTO hoặc kiểu kết quả ổn định. Nếu consumer cần một hành vi, công bố command/query facade. Nếu cần thông tin cho read model, công bố một query contract phù hợp.

### 5.4. API nhỏ giúp module có quyền tự do thay đổi

Một API công khai quá rộng khiến mọi lớp nội bộ trở thành hợp đồng ngầm. Hãy chỉ công bố những thao tác mà consumer thực sự cần.

Khi cần thay đổi implementation, module có thể thay repository, ORM mapping hoặc cấu trúc Aggregate mà không phải sửa consumer nếu hợp đồng không đổi.

## 6. Quy tắc dependency giữa các module

### 6.1. Dependency phải đi qua public API

Giả sử Billing cần biết Sales Order nào đã được xác nhận. Billing có thể tiêu thụ integration event do Sales công bố hoặc gọi một query contract nếu cần dữ liệu đồng bộ.

Billing không nên import sales.infrastructure.JpaSalesOrderRepository hoặc đọc trực tiếp sales.domain.SalesOrder.

Một quy tắc đơn giản:

~~~text
billing.application
        |
        v
sales.api

Không cho phép:
billing.infrastructure
        |
        v
sales.infrastructure
sales.domain
~~~

Việc module consumer phụ thuộc compile-time vào API của provider có thể chấp nhận được. Phụ thuộc vào implementation nội bộ làm ranh giới yếu đi.

### 6.2. Hạn chế dependency vòng

Nếu Sales gọi Billing, Billing gọi Fulfillment, rồi Fulfillment lại gọi Sales để hoàn tất một thao tác, hệ thống có thể có dependency cycle.

Dependency vòng khiến khó xác định:
- Ai khởi tạo quy trình.
- Ai sở hữu quyết định.
- Thay đổi nào có thể triển khai độc lập trong code.
- Test cần dựng bao nhiêu module.

Hãy xem xét application orchestrator, process manager hoặc event-driven workflow. Nếu hai mô-đun liên tục gọi nhau hai chiều vì cùng sở hữu một invariant, có thể ranh giới đang đặt sai và cần khám phá lại.

### 6.3. Đặt abstraction ở nơi có quyền sở hữu hợp đồng

Không phải mọi interface đều nên đặt trong module common. Nếu Sales công bố một API, Sales sở hữu ý nghĩa và phiên bản của API đó. Consumer dùng hợp đồng được công bố.

Nếu một use case cần port do consumer định nghĩa để đảo chiều dependency, đặt port ở phía sở hữu chính sách của use case có thể phù hợp. Cần phân biệt module API liên context với port nội bộ trong kiến trúc hexagonal.

### 6.4. Tránh shared mutable state

Không chia sẻ một singleton mutable hoặc một object domain cho nhiều module cùng thay đổi. Mỗi module cần kiểm soát trạng thái thuộc mô hình của mình.

Dữ liệu có thể được trao đổi bằng immutable DTO, command hoặc event. Khi cần cập nhật, consumer gửi yêu cầu qua API của owner.

## 7. Quyền sở hữu dữ liệu và database

### 7.1. Mỗi module sở hữu dữ liệu nghiệp vụ của mình

Ví dụ:
- Sales sở hữu sales_order, sales_order_line.
- Fulfillment sở hữu fulfillment_order, delivery_attempt.
- Billing sở hữu invoice, invoice_line.
- Payment sở hữu payment, payment_transaction.

Module khác không được cập nhật trực tiếp các bảng này. Nếu Billing cần dữ liệu đơn hàng, nó lấy qua API/event hoặc lưu một projection/snapshot phù hợp.

### 7.2. Shared database không đồng nghĩa shared ownership

Có thể dùng một database vật lý vì chi phí vận hành hoặc nhu cầu transaction. Nhưng nên giữ:
- Schema hoặc namespace rõ theo module khi khả thi.
- Quyền truy cập repository giới hạn trong module owner.
- Migration có owner rõ.
- Query cross-module qua contract hoặc read model.
- Không phụ thuộc vào tên cột hoặc join nội bộ của module khác.

Một truy vấn join xuyên schema có thể tiện, nhưng nếu trở thành đường truy cập chính thức, nó tạo coupling vào cấu trúc lưu trữ. Hãy cân nhắc một read model hoặc query contract được owner hỗ trợ.

### 7.3. Tránh cập nhật bảng của module khác

Ví dụ không nên làm:

~~~java
@Repository
class BillingOrderLookup {
    @Query("update SalesOrderEntity o set o.invoiced = true where o.id = :id")
    void markSalesOrderInvoiced(UUID id);
}
~~~

Billing đang thay đổi trạng thái nội bộ của Sales. Thay vào đó, Billing phát InvoiceIssued hoặc gọi một command công khai của Sales nếu có hành vi Sales cần thực hiện khi nhận thông tin hóa đơn.

### 7.4. Foreign key xuyên module cần cân nhắc

Foreign key giữa các schema có thể bảo vệ tính toàn vẹn ở database, nhưng cũng tạo coupling ở tầng lưu trữ và thứ tự migration. Trong một modular monolith, điều đó không bị cấm tuyệt đối, nhưng phải là quyết định có chủ đích.

Nếu module cần độc lập về schema và lifecycle, lưu ID tham chiếu và kiểm tra qua hợp đồng thường phù hợp hơn. Không dùng cascade delete xuyên ownership.

### 7.5. Repository thuộc module sở hữu Aggregate

Repository là abstraction của domain/application module sở hữu Aggregate. Implementation JPA nằm trong infrastructure cùng module.

Module khác không nên inject repository nội bộ để tìm hoặc sửa Aggregate. Nó nên dùng public API hoặc dữ liệu đã được công bố.

## 8. Giao tiếp đồng bộ giữa các module

### 8.1. Dùng module facade cho command hoặc query đồng bộ

Khi caller cần kết quả ngay, có thể gọi public API trong cùng tiến trình.

~~~java
public interface CustomerQueries {
    CustomerSummary findSummary(CustomerId customerId);
}

public record CustomerSummary(
    String customerId,
    String displayName,
    boolean active
) {
}
~~~

Sales có thể dùng CustomerQueries để kiểm tra hoặc lấy snapshot thông tin cần thiết theo use case. API này không trả Customer Aggregate nội bộ.

### 8.2. Phân biệt command và query

- Command yêu cầu owner thực hiện một hành động.
- Query yêu cầu owner cung cấp thông tin.
- Event thông báo điều gì đã xảy ra.

Không dùng một method updateEverything chung cho cả ba mục đích. Tên và kiểu dữ liệu nên phản ánh intent.

### 8.3. Không gọi module khác chỉ để né sở hữu dữ liệu

Nếu Sales liên tục gọi Customer để kiểm tra nhiều thuộc tính trong mọi hành vi, hãy xác định chính sách nào thực sự thuộc Sales và dữ liệu nào cần snapshot.

Có thể lưu BuyerId, trạng thái đủ điều kiện tại thời điểm giao dịch hoặc snapshot được phép theo quy tắc. Không sao chép toàn bộ Customer Aggregate vào Sales.

### 8.4. Tránh call chain dài

Một request đồng bộ đi qua Sales → Customer → Catalog → Pricing → Inventory → Payment có thể trở thành một distributed monolith ngay cả khi tất cả nằm trong một JVM. Latency và failure propagation vẫn tích lũy.

Hãy xác định use case cần dữ liệu nào, module nào sở hữu quyết định và phần nào có thể xử lý bằng workflow/event. Nếu call chain dài và thường xuyên thay đổi cùng nhau, cần xem lại ranh giới hoặc tạo một application orchestrator rõ ràng.

## 9. Giao tiếp bất đồng bộ bằng Domain Event và Integration Event

### 9.1. Event thông báo sự việc đã xảy ra

Khi Sales xác nhận đơn, nó có thể phát SalesOrderConfirmed. Fulfillment nhận thông điệp và tạo công việc xử lý.

~~~java
public record SalesOrderConfirmed(
    UUID eventId,
    String salesOrderId,
    String buyerId,
    Instant occurredAt,
    int schemaVersion
) {
}
~~~

Event nên chứa dữ liệu cần thiết cho consumer và định danh ổn định. Không gửi trực tiếp JPA Entity hoặc toàn bộ object graph.

### 9.2. Phân biệt Domain Event và Integration Event

Domain Event mô tả điều xảy ra bên trong mô hình của module. Integration Event là hợp đồng công bố cho module hoặc hệ thống khác.

Không phải Domain Event nào cũng cần được công bố. Module có thể chuyển Domain Event thành Integration Event qua application/integration layer để kiểm soát schema và dữ liệu.

### 9.3. Dùng Transactional Outbox khi cần giao event đáng tin cậy

Nếu module lưu Aggregate rồi phát event trực tiếp, có thể xảy ra:
- Database commit thành công nhưng broker publish thất bại.
- Event được publish nhưng database rollback.

Transactional Outbox ghi thay đổi Aggregate và message outbox trong cùng transaction. Publisher đọc outbox và gửi message sau commit.

~~~text
Application command
       |
       v
Module transaction
   |             |
   v             v
Aggregate      Outbox row
   |             |
   +---- commit -+
                 |
                 v
          Outbox publisher
                 |
                 v
              Broker
~~~

Consumer cần xử lý message lặp an toàn vì publisher có thể gửi lại khi không chắc broker đã nhận.

### 9.4. Eventual consistency cần trạng thái có ý nghĩa

Khi Sales đã xác nhận nhưng Fulfillment chưa nhận event, trạng thái “đã xác nhận bán” và “chưa tạo fulfillment” có thể cùng tồn tại trong thời gian ngắn.

Đừng giả định mọi module cập nhật tức thì. Nếu người dùng cần theo dõi quy trình, mô hình nên diễn đạt trạng thái như FulfillmentPending, FulfillmentCreated hoặc một projection tổng hợp phù hợp.

### 9.5. Dùng Process Manager khi quy trình có nhiều bước

Nếu một quy trình phối hợp Sales, Payment, Fulfillment và Billing với retry, timeout hoặc compensation, Process Manager có thể theo dõi tiến trình.

Không đặt toàn bộ quy trình vào một Aggregate khổng lồ. Process Manager giữ trạng thái điều phối; mỗi module vẫn sở hữu Aggregate và quyết định miền của mình.

## 10. Transaction và consistency trong modular monolith

### 10.1. Transaction trong một module

Một transaction cục bộ nên bao quanh thay đổi cần bảo vệ invariant của mô-đun. Ví dụ Sales xác nhận SalesOrder và ghi outbox trong cùng transaction.

Đây là ranh giới tự nhiên để giữ tính nhất quán mạnh.

### 10.2. Có thể dùng một transaction xuyên module, nhưng phải hiểu coupling

Vì các module chạy trong cùng process và có thể dùng cùng database, một application service có thể gọi nhiều module trong một transaction. Điều này có thể hợp lý khi có một quy tắc nghiệp vụ thực sự cần tính nguyên tử và các module cùng nằm trong một ranh giới vận hành được chấp nhận.

Tuy nhiên, transaction xuyên module tạo phụ thuộc về schema, thứ tự gọi, rollback và lock. Nếu dùng thường xuyên để giữ các mô hình độc lập đồng bộ, ranh giới có thể chỉ tồn tại trên package.

Hãy ưu tiên transaction theo Aggregate/module owner. Chỉ mở rộng transaction khi yêu cầu consistency đã được xác định rõ và chi phí coupling được chấp nhận.

### 10.3. Không nhầm một JVM với một transaction nghiệp vụ duy nhất

Cùng tiến trình không có nghĩa mọi hành động phải commit cùng nhau. Các Bounded Context có thể có lifecycle và quy tắc riêng dù cùng triển khai.

Ví dụ:
1. Sales xác nhận đơn.
2. Payment thực hiện authorization.
3. Fulfillment phân bổ kho.
4. Billing phát hành hóa đơn theo chính sách.

Nếu bước 3 thất bại, quy trình cần xác định đơn sẽ chờ, retry, đổi kho hay hủy/compensate. Không nhất thiết rollback toàn bộ lịch sử Sales chỉ vì Fulfillment chưa hoàn tất.

### 10.4. Concurrency vẫn tồn tại trong modular monolith

Một JVM vẫn có nhiều request, thread và worker. Các module có thể tranh chấp cùng dữ liệu hoặc tài nguyên.

Dùng optimistic locking, unique constraint, transaction isolation hoặc cơ chế đồng bộ phù hợp với invariant. Ranh giới module không tự giải quyết race condition.

## 11. Ví dụ thiết kế module Sales và Fulfillment

### 11.1. Public contract của Sales

~~~java
package com.acme.commerce.sales.api;

public interface SalesOrderCommands {
    ConfirmationResult confirm(ConfirmSalesOrder command);
}

public record ConfirmSalesOrder(
    String salesOrderId,
    String buyerId
) {
}

public record ConfirmationResult(
    String salesOrderId,
    String status
) {
}
~~~

### 11.2. Implementation nội bộ của Sales

~~~java
package com.acme.commerce.sales.application;

final class ConfirmSalesOrderHandler
    implements SalesOrderCommands {

    private final SalesOrderRepository orders;
    private final UnitOfWork unitOfWork;

    @Override
    public ConfirmationResult confirm(
        ConfirmSalesOrder command
    ) {
        SalesOrderId id =
            SalesOrderId.from(command.salesOrderId());

        SalesOrder order = orders.get(id);
        order.confirm(BuyerId.from(command.buyerId()));

        orders.save(order);
        unitOfWork.commit();

        return new ConfirmationResult(
            order.id().value(),
            order.status().name()
        );
    }
}
~~~

Repository, Aggregate và UnitOfWork thuộc implementation của Sales. Consumer chỉ biết API và kết quả công bố.

### 11.3. Fulfillment tiêu thụ event

~~~java
package com.acme.commerce.fulfillment.application;

final class SalesOrderConfirmedHandler {

    private final FulfillmentOrderRepository orders;

    public void handle(SalesOrderConfirmed event) {
        if (orders.existsForSource(event.salesOrderId())) {
            return;
        }

        FulfillmentOrder order =
            FulfillmentOrder.createFrom(event);

        orders.save(order);
    }
}
~~~

Trong triển khai thực tế, exists rồi save riêng lẻ có thể race khi message được giao đồng thời. Cần unique constraint cho source key và xử lý duplicate một cách nguyên tử. Nếu cần event deduplication, lưu Event ID đã xử lý cùng transaction cập nhật Aggregate.

### 11.4. Quan hệ giữa các module

~~~text
Caller
  |
  v
SalesOrderCommands (public API)
  |
  v
Sales Application
  |
  v
Sales Domain + Sales Repository
  |
  +---- Sales DB tables
  |
  +---- Outbox: SalesOrderConfirmed
                 |
                 v
          Local event dispatcher
                 |
                 v
       Fulfillment event handler
                 |
                 v
       Fulfillment Domain + Repository
                 |
                 +---- Fulfillment DB tables
~~~

Các module có thể dùng cùng broker nội bộ hoặc dispatcher trong process. Dù cơ chế truyền message nào được chọn, consumer vẫn phải dựa trên hợp đồng và xử lý lặp an toàn.

## 12. Chọn cấu trúc build: package, Maven, Gradle và JPMS

### 12.1. Bắt đầu bằng package boundary nếu dự án còn nhỏ

Với codebase nhỏ, package theo module và architecture tests có thể đủ. Không cần tách thành nhiều build project ngay khi chưa có nhu cầu quản lý dependency phức tạp.

Ưu điểm:
- Cấu hình build đơn giản.
- Refactor nhanh.
- Ít boilerplate.
- Có thể thử nghiệm ranh giới trước khi khóa bằng module system.

Nhược điểm là compiler mặc định không ngăn mọi truy cập package nếu cấu trúc package và visibility không được thiết kế cẩn thận.

### 12.2. Dùng Maven hoặc Gradle subproject khi cần ranh giới compile-time

Có thể tách:

~~~text
commerce
    commerce-app
    sales-api
    sales-impl
    fulfillment-api
    fulfillment-impl
    billing-api
    billing-impl
~~~

commerce-app lắp ghép các module. sales-impl có thể phụ thuộc sales-api; consumer phụ thuộc API thay vì implementation nếu build structure cho phép.

Tách build module làm tăng thời gian cấu hình và quản lý dependency. Chỉ nên làm khi nó giúp enforce ownership hoặc độc lập build rõ ràng.

### 12.3. Java Platform Module System (JPMS)

JPMS cung cấp module-info.java, exports và requires để kiểm soát module dependency và package visibility ở cấp Java module.

Ví dụ:

~~~java
module com.acme.commerce.sales {
    exports com.acme.commerce.sales.api;
}
~~~

Các package không được export không thể được module khác truy cập theo quy tắc JPMS thông thường. Cần hiểu thêm yêu cầu reflection của framework như Spring/JPA và cấu hình opens nếu cần.

JPMS không tự thiết kế Bounded Context. Nó là cơ chế thực thi ranh giới ở cấp ngôn ngữ/runtime; mô hình miền vẫn phải được thiết kế trước.

### 12.4. Spring Modulith và công cụ hỗ trợ

Spring Modulith có thể giúp xác định application module theo package, kiểm tra dependency và hỗ trợ một số cách kiểm thử module/event. Đây là lựa chọn khi dự án dùng Spring và cần convention/tooling phù hợp.

Công cụ không thay thế quyết định nghiệp vụ. Một package được công cụ nhận diện là module chưa chắc đã là Bounded Context đúng.

## 13. Kiểm tra kiến trúc bằng automated tests

### 13.1. Quy tắc kiến trúc cần được thực thi

Ví dụ các quy tắc:
- sales không phụ thuộc fulfillment.infrastructure.
- billing không truy cập sales.domain.
- Mọi module chỉ công bố package api.
- Không có dependency cycle giữa module.
- Domain không phụ thuộc Spring MVC hoặc JPA.
- Infrastructure có thể phụ thuộc domain/application, nhưng domain không phụ thuộc infrastructure.

Ghi các quy tắc này thành test để lỗi xuất hiện ngay trong CI.

### 13.2. Ví dụ với ArchUnit

~~~java
@AnalyzeClasses(packages = "com.acme.commerce")
class ModuleBoundaryTest {

    @ArchTest
    static final ArchRule domainDoesNotDependOnInfrastructure =
        noClasses()
            .that().resideInAnyPackage("..domain..")
            .should().dependOnClassesThat()
            .resideInAnyPackage("..infrastructure..");

    @ArchTest
    static final ArchRule billingDoesNotAccessSalesInternals =
        noClasses()
            .that().resideInAPackage("..billing..")
            .should().dependOnClassesThat()
            .resideInAnyPackage(
                "..sales.domain..",
                "..sales.infrastructure.."
            );
}
~~~

Các package pattern cần điều chỉnh theo cấu trúc thật. Test thứ hai cho phép Billing dùng sales.api nhưng cấm truy cập domain và infrastructure nội bộ.

### 13.3. Kiểm tra module cycle

ArchUnit hoặc công cụ module phù hợp có thể phát hiện cycle giữa package/module. Một cycle thường là dấu hiệu cần xem lại dependency direction hoặc chuyển hợp đồng về đúng owner.

Không nên xử lý cycle bằng cách đẩy mọi class vào common. Hãy tìm lý do nghiệp vụ khiến hai module phụ thuộc hai chiều.

### 13.4. Kiểm thử module độc lập

Một module nên có thể được kiểm tra bằng:
- Unit test cho Entity, Value Object, Aggregate và Domain Service.
- Application test cho use case.
- Integration test cho repository và transaction.
- Contract test cho public API/event.
- Architecture test cho dependency.

Không cần boot toàn bộ ứng dụng cho mọi test. Test nhỏ giúp phản hồi nhanh và xác định đúng nơi có lỗi.

### 13.5. Architecture test không chứng minh mô hình nghiệp vụ đúng

Một dự án có thể vượt qua mọi dependency test nhưng vẫn chia module sai. Ví dụ Sales và Fulfillment không phụ thuộc code nội bộ nhau nhưng cùng dùng một Order model mơ hồ.

Architecture test bảo vệ quy tắc cấu trúc. Domain test và trao đổi nghiệp vụ xác nhận semantics. Cần cả hai.

## 14. Tích hợp giao diện và composition layer

### 14.1. Controller nên nằm ở module sở hữu use case hoặc composition layer

Có thể đặt REST controller trong module Sales nếu endpoint thuộc Sales. Một API gateway/composition layer nội bộ có thể tổng hợp dữ liệu từ nhiều module cho màn hình.

Điều quan trọng là controller không truy cập repository nội bộ của module khác để ghép response.

### 14.2. Read model tổng hợp cần có owner

Một màn hình Order Overview có thể cần Sales status, Fulfillment progress, Invoice status và Payment status. Có thể:
- Gọi các query API đồng bộ.
- Dùng projection được cập nhật từ event.
- Tạo query module sở hữu read model tổng hợp.

Nếu dùng projection, cần chấp nhận độ trễ cập nhật và hiển thị thời điểm dữ liệu được cập nhật nếu nghiệp vụ cần.

### 14.3. Không để UI trở thành nơi điều phối quy tắc

UI có thể gọi nhiều module, nhưng các quy tắc như “chỉ giao hàng sau khi đơn được xác nhận và thanh toán đủ điều kiện” cần được bảo vệ ở application/domain boundary. Không dựa vào việc frontend gọi API theo đúng thứ tự để giữ invariant.

## 15. Vận hành và triển khai modular monolith

### 15.1. Một deployable vẫn cần quan sát theo module

Dù triển khai một artifact, log và metric nên có module/context name, correlation ID và thông tin use case phù hợp.

Điều này giúp biết lỗi phát sinh ở Sales, Billing hay Fulfillment mà không cần tách process.

### 15.2. Cấu hình nên có namespace rõ

Ví dụ:
- sales.*
- fulfillment.*
- billing.*
- payment.*

Không để mọi module đọc/ghi chung một tập cấu hình mơ hồ. Secret và credential bên ngoài cần được quản lý theo quyền sử dụng.

### 15.3. Migration database cần có thứ tự và ownership

Nếu nhiều module dùng chung database, mỗi migration nên thuộc module owner và có version rõ. Một deployment có thể chạy nhiều migration, nhưng phải đảm bảo thứ tự tương thích giữa phiên bản ứng dụng và schema.

Dùng chiến lược expand–migrate–contract khi đổi schema có ảnh hưởng đến code hoặc consumer cũ.

### 15.4. Một lỗi module có thể ảnh hưởng toàn ứng dụng

Các module chạy cùng process nên lỗi nghiêm trọng, deadlock, memory leak hoặc thread exhaustion có thể ảnh hưởng toàn bộ ứng dụng. Ranh giới logic không phải ranh giới fault isolation như process riêng.

Cần timeout cho lời gọi bên ngoài, giới hạn tài nguyên, xử lý exception và giám sát phù hợp. Không biến lỗi nghiệp vụ dự kiến thành exception làm sập request hoặc worker không cần thiết.

## 16. Khi nào modular monolith phù hợp và khi nào nên tách service?

### 16.1. Modular monolith phù hợp khi

- Đội ngũ muốn giữ một đơn vị triển khai đơn giản.
- Các module cần giao tiếp thường xuyên và độ trễ thấp.
- Quy mô vận hành chưa cần scale từng năng lực độc lập.
- Đội ngũ có thể thống nhất lịch release.
- Ranh giới nghiệp vụ đã có thể xác định nhưng chưa có lý do mạnh để tách process.
- Muốn giảm chi phí vận hành phân tán.

### 16.2. Cân nhắc tách service khi có nhu cầu thực

Một module có thể cần triển khai riêng khi:
- Có yêu cầu scale khác biệt rõ rệt.
- Có yêu cầu bảo mật hoặc network isolation riêng.
- Nhóm sở hữu cần release độc lập thường xuyên.
- Có nhu cầu công nghệ hoặc runtime khác biệt.
- Mức độ tải và failure profile đòi hỏi fault isolation.
- Hợp đồng và dữ liệu đã đủ rõ để chịu chi phí phân tán.

Không tách chỉ vì module đã có package riêng hoặc vì số lượng dòng code lớn.

### 16.3. Tách service làm xuất hiện chi phí mới

Sau khi tách process, cần giải quyết:
- Network timeout và retry.
- Partial failure.
- Event delivery và deduplication.
- Data ownership và replication.
- Observability xuyên service.
- Deployment/version compatibility.
- Eventual consistency và compensation.
- Bảo mật giao tiếp service-to-service.

Nếu chưa cần các đặc tính độc lập này, modular monolith có thể là lựa chọn kinh tế hơn.

### 16.4. Ranh giới tốt giúp việc tách có chọn lọc

Khi module API nhỏ, dữ liệu có owner và event contract rõ, có thể tách một module mà không cần tái viết toàn bộ hệ thống. Nhưng trước khi tách, cần kiểm tra mọi dependency ẩn: shared table, transaction xuyên module, static singleton, shared cache và call chain đồng bộ.

## 17. Lộ trình xây dựng hoặc chuyển đổi sang modular monolith

### 17.1. Bước 1 — lập bản đồ năng lực và mô hình

Tổ chức workshop để xác định:
- Capability nghiệp vụ.
- Bounded Context.
- Aggregate và invariant quan trọng.
- Dữ liệu được sở hữu.
- Context Map và integration relationship.

Không bắt đầu bằng việc chia package theo số lượng team hoặc bảng.

### 17.2. Bước 2 — chọn một lát cắt có giá trị

Chọn một năng lực có ranh giới tương đối rõ, ví dụ Billing hoặc Catalog. Xác định API, implementation và dữ liệu owner.

Tránh di chuyển tất cả code cùng lúc. Một lát cắt nhỏ giúp kiểm chứng quy ước và tìm ra dependency ẩn.

### 17.3. Bước 3 — tạo public API và đóng implementation

Di chuyển các use case qua facade/contract. Chuyển consumer sang API thay vì gọi repository hoặc Entity nội bộ.

Giữ adapter tương thích tạm thời nếu cần, nhưng ghi rõ thời điểm và điều kiện loại bỏ.

### 17.4. Bước 4 — kiểm soát dữ liệu và transaction

Xác định module owner cho mỗi bảng. Nếu cần tách schema, dùng migration có kiểm soát. Loại bỏ các đường ghi xuyên module và thay bằng command/event/query contract.

Không thay đổi consistency semantics một cách âm thầm. Nếu chuyển từ transaction chung sang event-driven workflow, cần xác định trạng thái trung gian và hành động bù trừ.

### 17.5. Bước 5 — thêm architecture tests

Đưa dependency rules vào CI:
- Cấm cycle.
- Cấm truy cập package nội bộ.
- Cấm domain phụ thuộc framework.
- Kiểm tra public API.
- Kiểm tra module ownership nếu công cụ hỗ trợ.

Khi một test kiến trúc thất bại, sửa dependency tại nguồn thay vì thêm exception cho mọi trường hợp.

### 17.6. Bước 6 — đo và điều chỉnh

Theo dõi:
- Số dependency giữa module.
- Số dependency vòng.
- Số lần truy cập dữ liệu ngoài owner.
- Độ dài call chain.
- Thời gian build/test.
- Tần suất thay đổi đồng thời.
- Lỗi tích hợp và độ trễ event.

Nếu một module trở thành trung tâm coupling, xem lại ranh giới hoặc API của nó.

## 18. Những sai lầm thường gặp

### Chỉ tạo package rồi gọi đó là modular monolith

Nếu module vẫn truy cập repository và Entity của nhau, ranh giới chỉ tồn tại trên sơ đồ.

### Chia theo tầng kỹ thuật thay vì năng lực

Package controller/service/repository toàn cục làm logic một capability bị phân tán. Tổ chức theo module nghiệp vụ giúp ownership rõ hơn.

### Tạo module common chứa toàn bộ domain

Shared domain model làm các context mất ngôn ngữ riêng và tạo coupling khó tháo gỡ. Chỉ chia sẻ khái niệm có semantics thực sự chung.

### Public API trả Entity hoặc repository

Consumer sẽ phụ thuộc vào cấu trúc nội bộ. Hãy công bố command/query/event contract và DTO có chủ đích.

### Dùng transaction xuyên module cho mọi quy trình

Điều này làm ranh giới yếu và tăng lock coupling. Transaction mạnh chỉ nên dùng khi consistency requirement cần và được chấp nhận.

### Mọi giao tiếp đều bất đồng bộ

Event không phải lựa chọn tốt cho mọi thao tác. Nếu caller cần kết quả ngay và hành động thuộc owner rõ ràng, module facade đồng bộ có thể đơn giản hơn.

### Mọi giao tiếp đều đồng bộ

Call chain dài tạo coupling và failure propagation. Các quy trình độc lập theo lifecycle có thể phù hợp với event và process manager.

### Dùng chung bảng vì cùng database

Cùng database không có nghĩa mọi module cùng sở hữu dữ liệu. Hãy xác định owner và API đọc/ghi rõ.

### Tách microservice quá sớm

Tách process trước khi hiểu mô hình và hợp đồng khiến đội ngũ phải giải quyết network, consistency và vận hành trong khi ranh giới nghiệp vụ còn mơ hồ.

### Không kiểm tra dependency tự động

Quy ước trong tài liệu dễ bị vi phạm theo thời gian. Dùng architecture tests hoặc module system để biến quy tắc thành kiểm tra trong CI.

### Nghĩ module boundary đảm bảo fault isolation

Các module trong cùng JVM chia sẻ process, heap và tài nguyên. Một lỗi nghiêm trọng vẫn có thể ảnh hưởng toàn ứng dụng.

## 19. Bài tập thực hành: tổ chức modular monolith cho nền tảng thương mại

Một hệ thống hiện tại có các package toàn cục controller, service, repository và entity. Một số service gọi repository của nhau. Mọi chức năng cùng dùng Entity Order và bảng orders.

Các năng lực nghiệp vụ:
- Catalog quản lý sản phẩm.
- Sales quản lý cam kết mua bán.
- Fulfillment quản lý kho và giao hàng.
- Billing quản lý hóa đơn.
- Payment quản lý giao dịch thanh toán.

Hãy thực hiện:

1. Vẽ Context Map và xác định owner cho từng mô hình.
2. Đề xuất cấu trúc package theo module.
3. Xác định public API của từng module.
4. Liệt kê các lớp cần giữ kín như JPA Entity và repository.
5. Xác định dependency direction và các cycle hiện có.
6. Chọn dữ liệu cần trao đổi bằng command, query hoặc event.
7. Thiết kế transaction boundary và outbox cho Sales.
8. Đề xuất cách tổ chức schema/table ownership.
9. Viết architecture test ngăn Billing truy cập Sales internals.
10. Lập lộ trình chuyển đổi một module theo Expand–Migrate–Contract.
11. Đánh giá tiêu chí nào trong tương lai có thể biện minh cho việc tách Fulfillment thành service riêng.

### 19.1. Gợi ý module map

| Module | Aggregate tiêu biểu | Dữ liệu sở hữu | Hợp đồng công bố |
|---|---|---|---|
| Catalog | Product | Product, ProductVariant | ProductPublished |
| Sales | SalesOrder | SalesOrder, SalesOrderLine | SalesOrderConfirmed |
| Fulfillment | FulfillmentOrder | FulfillmentOrder, DeliveryAttempt | DeliveryCompleted |
| Billing | Invoice | Invoice, CreditNote | InvoiceIssued |
| Payment | Payment | Payment, PaymentTransaction | PaymentAuthorized, PaymentFailed |

Đây là gợi ý để thảo luận. Một hệ thống thực tế có thể cần thêm module hoặc phạm vi khác tùy capability và ownership.

## 20. Checklist thiết kế modular monolith theo ranh giới miền

Trước khi xem một ứng dụng là modular monolith có ranh giới vững, hãy kiểm tra:

- Module phản ánh capability hoặc Bounded Context có ý nghĩa.
- Mỗi module có trách nhiệm và owner rõ.
- Public API nhỏ và được công bố có chủ đích.
- Entity, Aggregate, repository và mapping nội bộ không bị expose tùy tiện.
- Dependency đi qua API hoặc integration contract.
- Không có dependency cycle không được giải thích.
- Domain không phụ thuộc infrastructure/framework.
- Dữ liệu có module owner rõ ràng.
- Không cập nhật trực tiếp bảng của module khác.
- Query cross-module có contract hoặc read model phù hợp.
- Command, query và event được phân biệt.
- Event có schema version và consumer xử lý duplicate.
- Outbox được dùng khi cần bảo đảm ghi dữ liệu và event nhất quán.
- Transaction boundary phản ánh invariant và consistency requirement.
- Eventual consistency có trạng thái trung gian và cách quan sát.
- Architecture tests chạy trong CI.
- Domain và integration tests kiểm tra hành vi ở đúng ranh giới.
- Cấu hình, migration và observability có namespace/owner.
- Quyết định tách service dựa trên nhu cầu scale, isolation và ownership thực tế.
- Lộ trình chuyển đổi có bước mở rộng, migrate, đối chiếu và contract.

## Kết luận

Thiết kế ứng dụng nguyên khối có mô-đun theo ranh giới miền bắt đầu bằng việc xác định những mô hình và trách nhiệm nghiệp vụ thực sự khác nhau. Mỗi module sở hữu logic và dữ liệu của mình, công bố API nhỏ, và cho phép các module khác tương tác qua hợp đồng rõ ràng. Bounded Context định hình ngôn ngữ và mô hình; module tổ chức code và dependency; deployable quyết định đơn vị vận hành.

Một modular monolith tốt giữ được sự đơn giản của triển khai thống nhất mà vẫn bảo vệ được ranh giới nội bộ. Điều đó đòi hỏi dependency rules có thể kiểm tra, dữ liệu có owner, transaction phù hợp với invariant và event được thiết kế có chủ đích. Khi nhu cầu thay đổi, ranh giới rõ giúp đội ngũ tiến hóa module hoặc tách service có chọn lọc mà không phải bắt đầu lại toàn bộ kiến trúc.


# MVC trong ứng dụng nguyên khối và nguyên khối mô-đun

Model–View–Controller (MVC) thường được giới thiệu như cách chia ứng dụng web thành Model, View và Controller. Tuy nhiên, MVC không quyết định ứng dụng phải chạy trong một tiến trình hay nhiều dịch vụ. Một ứng dụng MVC có thể được đóng gói thành một khối triển khai duy nhất, hoặc được tổ chức thành nhiều mô-đun nghiệp vụ có ranh giới rõ ràng nhưng vẫn chạy chung trong một ứng dụng.

Hai khái niệm cần phân biệt:

- **Ứng dụng nguyên khối (monolith):** ứng dụng được xây dựng và triển khai như một đơn vị. Các thành phần thường cùng chạy trong một tiến trình hoặc một gói triển khai.
- **Nguyên khối mô-đun (modular monolith):** vẫn là một đơn vị triển khai, nhưng mã nguồn và các thành phần được chia thành mô-đun nghiệp vụ với API, dữ liệu và quy tắc phụ thuộc được kiểm soát.

MVC là pattern tổ chức tương tác và trình bày; monolith và modular monolith mô tả cách tổ chức hệ thống và ranh giới triển khai. Vì vậy, có thể dùng MVC bên trong từng mô-đun của một modular monolith. Cách kết hợp này giữ luồng web quen thuộc, đồng thời giúp nghiệp vụ không bị trộn thành một khối khó thay đổi.

## 1. Phân biệt pattern MVC với kiểu kiến trúc triển khai

MVC tập trung vào việc tiếp nhận tương tác, xử lý trạng thái và trình bày kết quả:

- **Model:** trạng thái và quy tắc nghiệp vụ mà ứng dụng cần bảo vệ.
- **View:** cách trình bày dữ liệu cho người dùng hoặc client.
- **Controller:** tiếp nhận request, chuyển dữ liệu đầu vào, gọi hành vi ứng dụng và chọn phản hồi.

Monolith lại trả lời các câu hỏi khác:

- Ứng dụng được đóng gói và triển khai như thế nào?
- Các thành phần có chạy trong cùng tiến trình không?
- Mã nguồn được chia thành những mô-đun nào?
- Thành phần nào được phép phụ thuộc vào thành phần nào?
- Dữ liệu và transaction được sở hữu ở đâu?

Do đó, không nên xem MVC là kiến trúc đối lập với monolith hoặc microservices. MVC có thể xuất hiện trong:

- Một ứng dụng nguyên khối chia theo các tầng Controller, Service, Repository và View.
- Một modular monolith, trong đó mỗi mô-đun nghiệp vụ có adapter web, application service và domain model riêng.
- Một dịch vụ web trong hệ thống microservices, nơi MVC chỉ là cách tổ chức tầng giao tiếp HTTP của dịch vụ đó.

~~~mermaid
flowchart TD
    A[Kiểu triển khai hệ thống] --> B[Monolith]
    A --> C[Modular Monolith]
    A --> D[Microservices]
    B --> E[MVC có thể nằm trong ứng dụng]
    C --> F[Mỗi module có thể có MVC adapter riêng]
    D --> G[Mỗi service có thể dùng MVC]
~~~

## 2. MVC trong ứng dụng nguyên khối truyền thống

Một ứng dụng nguyên khối thường có một codebase, một quy trình build và một đơn vị triển khai. Trong cách tổ chức theo tầng phổ biến, các Controller nhận request rồi gọi Service; Service xử lý nghiệp vụ và gọi Repository; View hiển thị dữ liệu được Controller đưa vào model.

Ví dụ cấu trúc:

~~~text
src/main/java/com/example/shop/
├── controller/
│   ├── OrderController.java
│   ├── ProductController.java
│   └── AccountController.java
├── service/
│   ├── OrderService.java
│   ├── ProductService.java
│   └── AccountService.java
├── repository/
│   ├── OrderRepository.java
│   ├── ProductRepository.java
│   └── AccountRepository.java
├── model/
│   ├── Order.java
│   ├── Product.java
│   └── Account.java
└── resources/templates/
    ├── orders/
    ├── products/
    └── accounts/
~~~

Ưu điểm của cấu trúc này là dễ nhận ra tầng kỹ thuật. Người mới có thể tìm Controller ở một nơi, Service ở một nơi khác và Repository ở nơi thứ ba. Tuy nhiên, khi hệ thống lớn lên, một thay đổi nghiệp vụ thường phải sửa nhiều package chung. Những package này chứa code của nhiều năng lực nghiệp vụ khác nhau.

Ví dụ, một thay đổi về quy tắc đơn hàng có thể ảnh hưởng:

- OrderController trong package controller.
- OrderService trong package service.
- OrderRepository trong package repository.
- Order và các kiểu dữ liệu trong package model.
- Template trong resources/templates.

Khi mọi nghiệp vụ đều được chia theo loại kỹ thuật, ranh giới giữa các năng lực như đơn hàng, sản phẩm và tài khoản có thể không rõ. Các Service có thể gọi trực tiếp lẫn nhau, dùng chung entity hoặc truy vấn bảng của nhau. Theo thời gian, ứng dụng vẫn triển khai thành một khối nhưng bên trong hình thành một mạng phụ thuộc khó kiểm soát.

### 2.1. Luồng request trong monolith

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant C as Controller
    participant S as Application Service
    participant R as Repository
    participant DB as Database
    participant V as View

    User->>C: POST /orders
    C->>C: Bind và validate request
    C->>S: createOrder(command)
    S->>R: Lưu đơn hàng
    R->>DB: INSERT / UPDATE
    DB-->>R: Kết quả
    R-->>S: Order
    S-->>C: Kết quả use case
    C-->>V: Model dữ liệu
    V-->>User: HTML response
~~~

Luồng này hoàn toàn hợp lệ trong một monolith. Điểm cần chú ý là Controller không nên chứa toàn bộ quy tắc nghiệp vụ, còn View không nên truy cập trực tiếp Repository hoặc entity lazy để tự tải dữ liệu.

## 3. Giới hạn của cách chia package theo tầng khi ứng dụng phát triển

Cấu trúc theo tầng kỹ thuật không tự động tạo ra ranh giới nghiệp vụ. Một số dấu hiệu thường gặp:

- Package service chứa hàng chục lớp không liên quan.
- Một service cần truy cập repository của nhiều nghiệp vụ khác nhau.
- Entity của nghiệp vụ này được dùng làm kiểu dữ liệu đầu vào hoặc đầu ra của nghiệp vụ khác.
- Thay đổi một bảng hoặc entity làm nhiều phần ứng dụng phải sửa.
- Các package có vòng phụ thuộc hoặc phụ thuộc ngược.
- Không thể xác định ai chịu trách nhiệm cho một quy tắc nghiệp vụ.
- Test một use case phải khởi động quá nhiều thành phần không liên quan.

Ví dụ, OrderService có thể trực tiếp gọi ProductRepository để đọc tồn kho, AccountRepository để đọc địa chỉ và PaymentRepository để cập nhật thanh toán. Nếu những truy vấn và quy tắc đó được thực hiện tùy tiện, OrderService trở thành nơi điều phối dữ liệu của toàn hệ thống.

Không phải mọi lời gọi giữa các nghiệp vụ đều sai. Một use case đặt hàng có thể cần thông tin sản phẩm và thanh toán. Vấn đề nằm ở việc truy cập trực tiếp vào cấu trúc nội bộ của mô-đun khác thay vì đi qua hợp đồng được công bố.

## 4. Nguyên khối mô-đun là gì?

Modular monolith vẫn được build và triển khai như một ứng dụng. Điểm khác biệt là bên trong nó được chia thành các mô-đun có trách nhiệm nghiệp vụ riêng, ví dụ:

- Catalog: quản lý sản phẩm và thông tin danh mục.
- Inventory: quản lý tồn kho và khả năng cung cấp.
- Ordering: quản lý đơn hàng và vòng đời đơn.
- Payment: quản lý yêu cầu và trạng thái thanh toán.
- Identity: quản lý tài khoản và danh tính.

Mỗi mô-đun có thể chứa các lớp web, application, domain và persistence phù hợp với trách nhiệm của nó. Mô-đun khác chỉ sử dụng chức năng đã công bố thông qua API nội bộ hoặc sự kiện, thay vì truy cập tùy ý các lớp bên trong.

~~~mermaid
flowchart TB
    subgraph APP[Modular Monolith - một đơn vị triển khai]
        subgraph ORDER[Ordering]
            OC[Order Controller]
            OA[Order Application]
            OD[Order Domain]
            OR[Order Repository]
            OC --> OA
            OA --> OD
            OA --> OR
        end
        subgraph CATALOG[Catalog]
            CA[Catalog API]
            CD[Catalog Domain]
            CR[Catalog Repository]
            CA --> CD
            CA --> CR
        end
        subgraph PAYMENT[Payment]
            PA[Payment API]
            PD[Payment Domain]
            PR[Payment Repository]
            PA --> PD
            PA --> PR
        end
        OA --> CA
        OA --> PA
    end
    DB[(Database)]
    OR --> DB
    CR --> DB
    PR --> DB
~~~

Sơ đồ minh họa các mô-đun nằm trong cùng ứng dụng. Chúng có thể dùng chung một database vật lý nhưng cần có quyền sở hữu bảng, schema hoặc dữ liệu rõ ràng. Dùng chung database không có nghĩa mô-đun nào cũng được phép đọc và ghi mọi bảng.

## 5. Tổ chức MVC bên trong từng mô-đun

Trong modular monolith, Controller không nhất thiết nằm trong một package toàn cục. Có thể đặt adapter web cạnh mô-đun nghiệp vụ mà nó phục vụ:

~~~text
com.example.shop/
├── ordering/
│   ├── web/
│   │   ├── OrderController.java
│   │   └── OrderRequest.java
│   ├── application/
│   │   ├── CreateOrderUseCase.java
│   │   └── OrderQueryService.java
│   ├── domain/
│   │   ├── Order.java
│   │   └── OrderPolicy.java
│   └── infrastructure/
│       └── JpaOrderRepository.java
├── catalog/
│   ├── api/
│   │   ├── CatalogQueries.java
│   │   └── ProductSummary.java
│   ├── domain/
│   └── infrastructure/
├── payment/
│   ├── api/
│   ├── domain/
│   └── infrastructure/
└── shared/
    └── ...
~~~

Ở đây, MVC vẫn giữ vai trò ở ranh giới web:

- OrderController nhận request của người dùng.
- Request DTO chỉ chứa dữ liệu đầu vào được phép.
- CreateOrderUseCase điều phối nghiệp vụ đặt hàng.
- Order domain bảo vệ bất biến và vòng đời đơn.
- Repository lưu trữ trạng thái do Ordering sở hữu.
- View hoặc response DTO chỉ chứa dữ liệu được phép hiển thị.

Mô-đun Catalog không cần biết OrderController tồn tại. Nó công bố một API truy vấn sản phẩm để Ordering có thể lấy thông tin cần thiết. Mô-đun Payment cũng công bố một hợp đồng riêng cho yêu cầu thanh toán.

## 6. Ranh giới mô-đun và hợp đồng công khai

Một mô-đun nên công bố những hành vi mà mô-đun khác cần dùng, đồng thời giữ chi tiết triển khai ở bên trong.

Ví dụ API nội bộ của Catalog:

~~~java
package com.example.shop.catalog.api;

public interface CatalogQueries {
    Optional<ProductSummary> findPurchasableProduct(String productId);
}

public record ProductSummary(
        String productId,
        String displayName,
        BigDecimal currentPrice
) {}
~~~

Ordering có thể phụ thuộc vào hợp đồng này:

~~~java
package com.example.shop.ordering.application;

import com.example.shop.catalog.api.CatalogQueries;
import com.example.shop.catalog.api.ProductSummary;

public class CreateOrderUseCase {
    private final CatalogQueries catalogQueries;
    private final OrderRepository orderRepository;

    public CreateOrderUseCase(
            CatalogQueries catalogQueries,
            OrderRepository orderRepository
    ) {
        this.catalogQueries = catalogQueries;
        this.orderRepository = orderRepository;
    }

    public OrderId execute(CreateOrderCommand command) {
        ProductSummary product = catalogQueries
                .findPurchasableProduct(command.productId())
                .orElseThrow(ProductUnavailableException::new);

        Order order = Order.create(
                product.productId(),
                product.displayName(),
                product.currentPrice(),
                command.quantity()
        );
        orderRepository.save(order);
        return order.id();
    }
}
~~~

Ví dụ cho thấy Ordering dùng ProductSummary thay vì phụ thuộc vào Catalog entity hoặc CatalogRepository. Giá được lấy từ nguồn sở hữu sản phẩm tại thời điểm use case chạy; Ordering có thể lưu snapshot giá vào đơn hàng để lịch sử đơn không thay đổi khi giá sản phẩm được cập nhật sau này.

Hợp đồng công khai nên:

- Chỉ chứa thao tác hoặc kiểu dữ liệu cần cho bên gọi.
- Không để lộ entity ORM, repository implementation hoặc bảng dữ liệu.
- Có ý nghĩa nghiệp vụ, không chỉ là wrapper quanh mọi phương thức nội bộ.
- Có quy tắc lỗi và nullability rõ ràng.
- Tránh dùng kiểu dữ liệu chung quá rộng khiến bên gọi phải biết chi tiết nội bộ.

## 7. Hướng phụ thuộc giữa các mô-đun

Ranh giới mô-đun chỉ có giá trị khi phụ thuộc được kiểm soát. Một nguyên tắc hữu ích là mô-đun gọi phụ thuộc vào API công khai, không phụ thuộc vào chi tiết persistence hoặc domain nội bộ của mô-đun khác.

Ví dụ hướng phụ thuộc:

~~~mermaid
flowchart LR
    WEB[Ordering Web] --> APP[Ordering Application]
    APP --> DOM[Ordering Domain]
    APP --> REPO[Ordering Repository Port]
    REPO -. implementation .-> INF[Ordering Infrastructure]
    APP --> CAT[Catalog Public API]
    APP --> PAY[Payment Public API]
    INF --> DB[(Database)]
~~~

Một số quy tắc nên được xác định:

- Web adapter chỉ gọi application use case hoặc query service của mô-đun.
- Application layer điều phối domain và các port cần thiết.
- Domain không phụ thuộc Spring MVC, Servlet, JPA hoặc template engine.
- Infrastructure triển khai repository port và adapter kỹ thuật.
- Mô-đun khác chỉ phụ thuộc API công khai.
- Không để hai mô-đun truy cập trực tiếp repository nội bộ của nhau.
- Tránh vòng phụ thuộc giữa các mô-đun.

Không phải mọi dự án cần đủ bốn package con trong mọi mô-đun. Một mô-đun nhỏ có thể có cấu trúc đơn giản hơn. Điều quan trọng là ranh giới và hướng phụ thuộc được hiểu, không phải số lượng thư mục.

## 8. Tránh dùng chung entity và repository giữa các mô-đun

Một dấu hiệu phá vỡ modularity là mô-đun Ordering dùng trực tiếp entity Product do Catalog quản lý:

~~~java
// Ví dụ thiết kế dễ tạo coupling
Product product = productRepository.findById(productId).orElseThrow();
order.setProduct(product);
~~~

Điều này khiến Ordering phụ thuộc vào mapping ORM, lifecycle và thay đổi nội bộ của Catalog. Khi Catalog đổi cấu trúc entity, Ordering có thể phải sửa theo.

Thay vào đó, dùng kiểu dữ liệu công khai:

~~~java
ProductSummary product = catalogQueries
        .findPurchasableProduct(productId)
        .orElseThrow(ProductUnavailableException::new);

order.addLine(
        product.productId(),
        product.displayName(),
        product.currentPrice(),
        quantity
);
~~~

Đơn hàng giữ dữ liệu snapshot cần thiết cho nghiệp vụ của nó. Nếu cần hiển thị thông tin sản phẩm hiện tại, Ordering có thể gọi Catalog query API hoặc dùng read model phù hợp. Quyết định này phụ thuộc yêu cầu lịch sử và tính nhất quán của màn hình.

## 9. Giao tiếp đồng bộ và sự kiện nội bộ

Các mô-đun trong cùng tiến trình có thể giao tiếp đồng bộ qua interface hoặc bất đồng bộ qua sự kiện nội bộ.

### 9.1. Gọi API nội bộ đồng bộ

Phù hợp khi use case cần kết quả ngay:

- Ordering hỏi Catalog sản phẩm có thể bán không.
- Ordering yêu cầu Payment khởi tạo thanh toán và cần nhận payment reference.
- Account hỏi Identity về trạng thái xác minh.

Ưu điểm là luồng điều khiển dễ hiểu và có thể trả lỗi ngay. Nhược điểm là mô-đun gọi phụ thuộc vào khả năng sẵn sàng và thời gian thực thi của mô-đun được gọi, dù tất cả cùng chạy trong một tiến trình.

### 9.2. Sự kiện miền hoặc sự kiện ứng dụng

Phù hợp khi một mô-đun thông báo sự kiện đã xảy ra để mô-đun khác phản ứng:

- OrderPlaced.
- PaymentCompleted.
- InventoryReserved.
- AccountEmailVerified.

Ví dụ:

~~~java
public record OrderPlaced(
        UUID orderId,
        Instant occurredAt
) {}
~~~

Ordering phát sự kiện sau khi đơn được tạo. Inventory có thể lắng nghe để giữ hàng, còn Notification có thể gửi thông báo.

Trong modular monolith, event handler có thể chạy đồng bộ trong cùng process hoặc được xử lý bất đồng bộ qua queue. Hai cách có ngữ nghĩa lỗi và transaction khác nhau. Không nên gọi một event listener đồng bộ là message broker hoặc giả định nó có khả năng retry bền vững nếu chưa có hạ tầng tương ứng.

## 10. Transaction và quyền sở hữu dữ liệu

Một modular monolith có thể dùng chung database và transaction manager. Tuy nhiên, ranh giới transaction nên theo use case và chính sách nhất quán, không phải tùy tiện bao trùm mọi mô-đun.

Ví dụ tạo đơn có thể:

1. Đọc thông tin sản phẩm từ Catalog.
2. Kiểm tra và giữ tồn kho qua Inventory.
3. Tạo đơn trong Ordering.
4. Khởi tạo thanh toán qua Payment.

Nếu tất cả thao tác đồng bộ và dùng cùng database transaction, có thể thiết kế một transaction bao trùm một phần thao tác. Nhưng khi có dịch vụ ngoài hoặc xử lý bất đồng bộ, không thể giả định mọi bước sẽ rollback cùng nhau.

Một số nguyên tắc:

- Mỗi mô-đun sở hữu trạng thái và quy tắc cập nhật dữ liệu của mình.
- Mô-đun khác không ghi trực tiếp vào bảng do mô-đun kia sở hữu.
- Transaction nên ngắn và gắn với use case rõ ràng.
- Không giữ database transaction mở trong khi chờ một HTTP call chậm nếu có thể tránh.
- Với quy trình nhiều bước có thể thất bại từng phần, cân nhắc state machine hoặc Saga.
- Nếu publish event cần nhất quán với commit dữ liệu, cân nhắc transactional outbox.

### 10.1. Shared database không có nghĩa shared ownership

Các mô-đun có thể cùng dùng một database vật lý, nhưng nên xác định:

| Dữ liệu | Mô-đun sở hữu | Mô-đun khác truy cập qua |
|---|---|---|
| Product, category, giá hiện tại | Catalog | Catalog query API |
| Order, order line, trạng thái đơn | Ordering | Order API hoặc sự kiện |
| Payment attempt, payment status | Payment | Payment API hoặc sự kiện |
| Stock, reservation | Inventory | Inventory API hoặc sự kiện |

Quyền sở hữu có nghĩa mô-đun chịu trách nhiệm về schema, quy tắc thay đổi và tính đúng của dữ liệu đó. Một báo cáo liên mô-đun có thể cần read model hoặc truy vấn tổng hợp được thiết kế rõ, thay vì để mọi module tùy ý join các bảng nội bộ.

## 11. Khi cần phối hợp nhiều mô-đun: orchestration và choreography

Một use case có thể cần nhiều mô-đun phối hợp. Có hai cách tổ chức phổ biến:

- **Orchestration:** một application service điều phối thứ tự các bước và quyết định hành động tiếp theo.
- **Choreography:** các mô-đun phản ứng với sự kiện của nhau, không có một bộ điều phối trung tâm duy nhất.

Ví dụ quy trình đặt hàng:

~~~mermaid
flowchart TD
    A[Create order] --> B[Reserve inventory]
    B --> C{Reservation succeeds?}
    C -->|No| D[Reject order]
    C -->|Yes| E[Create payment]
    E --> F{Payment succeeds?}
    F -->|Yes| G[Confirm order]
    F -->|No| H[Release inventory]
    H --> I[Mark payment/order failed]
~~~

Orchestration làm rõ luồng và thuận tiện cho một use case có nhiều bước. Choreography giúp giảm điều phối tập trung nhưng có thể khiến luồng nghiệp vụ khó theo dõi khi có nhiều event handler.

Nếu mọi thứ chạy trong một process, có thể bắt đầu bằng orchestration tường minh. Khi có nhu cầu xử lý bất đồng bộ, retry hoặc phục hồi sau lỗi, thiết kế event và state transition rõ ràng trước khi chuyển sang choreography.

## 12. Phân chia View và route theo mô-đun

Trong modular monolith, route và template có thể được nhóm theo năng lực nghiệp vụ:

~~~text
templates/
├── ordering/
│   ├── list.html
│   ├── detail.html
│   └── create.html
├── catalog/
│   ├── products.html
│   └── product-detail.html
└── account/
    ├── profile.html
    └── settings.html
~~~

Controller của từng mô-đun nên chịu trách nhiệm cho route thuộc phạm vi đó. Một trang tổng hợp có thể cần dữ liệu từ nhiều mô-đun; khi đó nên có query service hoặc page composition layer chuyên biệt để lấy các DTO cần thiết.

Không nên để template gọi trực tiếp service hoặc repository của nhiều mô-đun. View nên nhận một model đã được chuẩn bị, có hợp đồng rõ và chỉ chứa dữ liệu được phép trình bày.

Với API, mỗi mô-đun có thể công bố endpoint theo resource hoặc capability của mình. Tuy nhiên, route public không nhất thiết phải phản chiếu tên package nội bộ. Hợp đồng HTTP nên ổn định và được thiết kế theo nhu cầu client.

## 13. Modular monolith không bắt buộc mỗi mô-đun có database riêng

Một quan niệm sai là modular monolith phải dùng một database riêng cho từng mô-đun. Điều đó không bắt buộc. Có thể dùng:

- Một database và schema chung, với quyền sở hữu bảng rõ.
- Một database vật lý nhưng schema riêng cho từng mô-đun.
- Một số database riêng khi có lý do vận hành hoặc bảo mật.

Điều cốt lõi là quyền sở hữu dữ liệu và cách truy cập được kiểm soát. Nếu mọi mô-đun cùng sửa bảng của nhau, chia package không tạo ra modularity thực chất.

Khi một mô-đun cần dữ liệu của mô-đun khác, hãy chọn một hợp đồng:

- Query API đồng bộ cho dữ liệu cần ngay.
- Event để thông báo thay đổi và xây dựng read model.
- Projection hoặc view được quản lý rõ cho báo cáo.
- Shared kernel rất nhỏ cho kiểu dữ liệu thực sự ổn định và không mang logic sở hữu.

Không nên tạo một package common chứa mọi entity, enum và utility rồi để tất cả mô-đun phụ thuộc vào đó. Shared kernel phình to sẽ trở thành một mô-đun trung tâm gây coupling.

## 14. Kiểm soát ranh giới bằng package và module Java

Package naming chỉ giúp tổ chức mã nguồn; nó không tự ngăn code truy cập lớp nội bộ. Có thể tăng mức bảo vệ bằng:

- Quy ước package và visibility: không public mọi lớp nếu không cần.
- JPMS module descriptor khi cấu trúc dự án phù hợp.
- Build module riêng với dependency rõ ràng.
- Architecture tests để phát hiện phụ thuộc trái phép.

Ví dụ module descriptor rút gọn:

~~~java
module com.example.shop.catalog {
    exports com.example.shop.catalog.api;
}
~~~

Chỉ package API được export cho module khác. Package domain và infrastructure vẫn là nội bộ theo ranh giới module Java. Cách dùng JPMS cần cân nhắc framework, reflection và cấu hình build; nhiều ứng dụng Spring vẫn bắt đầu bằng package boundary và architecture tests trước khi áp dụng module descriptor.

### 14.1. Kiểm thử quy tắc kiến trúc

Có thể dùng ArchUnit để kiểm tra dependency direction:

~~~java
@AnalyzeClasses(packages = "com.example.shop")
class ModuleBoundaryTest {

    @ArchTest
    static final ArchRule orderingMustNotDependOnCatalogInfrastructure =
            noClasses()
                    .that().resideInAPackage("..ordering..")
                    .should().dependOnClassesThat()
                    .resideInAPackage("..catalog.infrastructure..");

    @ArchTest
    static final ArchRule domainMustNotDependOnSpring =
            noClasses()
                    .that().resideInAPackage("..domain..")
                    .should().dependOnClassesThat()
                    .resideInAnyPackage("org.springframework..");
}
~~~

Ví dụ minh họa cần điều chỉnh package pattern theo dự án. Có thể bổ sung quy tắc để mô-đun chỉ phụ thuộc API công khai của mô-đun khác và không tạo vòng phụ thuộc.

## 15. Kiểm thử trong modular monolith

Modular monolith cần nhiều lớp test tương tự một ứng dụng MVC thông thường, nhưng bổ sung kiểm thử ranh giới mô-đun.

| Phạm vi | Nội dung kiểm thử |
|---|---|
| Domain từng mô-đun | Quy tắc và bất biến nội bộ |
| Application use case | Điều phối và xử lý lỗi |
| Repository của mô-đun | Mapping, query, transaction và quyền sở hữu dữ liệu |
| Web adapter của mô-đun | Route, binding, validation và response |
| Public module API | Hợp đồng input/output và lỗi |
| Module integration | Phối hợp giữa hai hoặc nhiều mô-đun |
| Architecture test | Dependency direction, package boundary, không có cycle |
| End-to-end | Hành trình người dùng xuyên các mô-đun |

Test public API đặc biệt quan trọng. Nó giúp mô-đun bên gọi phụ thuộc vào hợp đồng ổn định thay vì chi tiết implementation. Khi thay đổi nội bộ Catalog, test hợp đồng có thể chứng minh Ordering vẫn nhận được ProductSummary đúng.

### 15.1. Kiểm thử tích hợp mô-đun

Một test tích hợp có thể khởi tạo các mô-đun cần thiết trong cùng application context và xác minh use case xuyên ranh giới:

- Ordering gọi Catalog API để xác minh sản phẩm.
- Ordering gọi Inventory API để giữ hàng.
- Payment API trả kết quả khởi tạo thanh toán.
- Order được lưu với snapshot dữ liệu cần thiết.
- Lỗi ở một bước được ánh xạ đúng và không để lại trạng thái nửa vời ngoài thiết kế.

Không cần khởi động mọi mô-đun cho mọi test. Chỉ nạp các mô-đun liên quan đến hành vi cần kiểm tra.

## 16. Khi nào chọn monolith truyền thống, khi nào chọn modular monolith?

Một ứng dụng nhỏ với ít năng lực nghiệp vụ có thể dùng cấu trúc theo tầng đơn giản. Không cần tạo nhiều module chỉ để có nhiều thư mục.

Modular monolith phù hợp hơn khi:

- Có nhiều năng lực nghiệp vụ tương đối độc lập.
- Nhiều nhóm cùng phát triển trên một codebase.
- Các thay đổi thường xuyên xung đột giữa các phần.
- Cần kiểm soát quyền sở hữu dữ liệu và quy tắc nghiệp vụ.
- Muốn giữ đơn vị triển khai đơn giản nhưng giảm coupling.
- Có khả năng cần tách một số năng lực thành dịch vụ riêng trong tương lai, nhưng chưa có lý do vận hành để làm ngay.

Monolith theo tầng có thể vẫn là lựa chọn hợp lý khi:

- Phạm vi nghiệp vụ nhỏ và ít thay đổi.
- Một nhóm nhỏ sở hữu toàn ứng dụng.
- Các năng lực chưa đủ độc lập để hình thành module.
- Chi phí thiết lập ranh giới module lớn hơn lợi ích hiện tại.

Không nên chọn modular monolith chỉ vì nó là một xu hướng. Hãy dựa trên cấu trúc nghiệp vụ, tốc độ thay đổi, mức độ phụ thuộc và khả năng kiểm soát.

## 17. Modular monolith và microservices không phải hai bước bắt buộc

Modular monolith thường được xem là nền tảng thuận lợi nếu sau này cần tách dịch vụ. Tuy nhiên, không phải mọi mô-đun đều cần trở thành microservice. Một mô-đun có thể ở cùng ứng dụng trong suốt vòng đời sản phẩm.

Microservices làm xuất hiện các vấn đề vận hành và phân tán:

- Giao tiếp qua mạng và timeout.
- Retry, idempotency và xử lý message trùng.
- Consistency giữa nhiều database.
- Quan sát xuyên dịch vụ.
- Triển khai, cấu hình và bảo mật từng service.
- Versioning và tương thích API.
- Khả năng chịu lỗi khi một service không sẵn sàng.

Trong modular monolith, lời gọi API nội bộ thường là lời gọi trong process. Khi tách mô-đun thành service, lời gọi đó trở thành giao tiếp qua mạng và cần thiết kế lại hợp đồng, lỗi, transaction và vận hành. Không nên chỉ đổi interface Java thành HTTP endpoint rồi giả định mọi thứ giữ nguyên.

### 17.1. Dấu hiệu một mô-đun có thể cần tách

- Có nhu cầu scale độc lập rõ ràng.
- Có yêu cầu triển khai hoặc lịch phát hành riêng.
- Có yêu cầu cô lập bảo mật hoặc dữ liệu.
- Có mô hình vận hành và trách nhiệm đội ngũ riêng.
- Ranh giới nghiệp vụ và dữ liệu đã ổn định.
- Lợi ích tách dịch vụ lớn hơn chi phí giao tiếp phân tán.

Nếu chưa có những nhu cầu đó, giữ mô-đun trong cùng đơn vị triển khai có thể giảm đáng kể độ phức tạp.

## 18. Lộ trình chuyển từ monolith theo tầng sang modular monolith

Không cần viết lại toàn bộ ứng dụng. Có thể tiến hành từng bước:

1. **Nhận diện năng lực nghiệp vụ:** nhóm use case, dữ liệu và quy tắc liên quan thành các capability.
2. **Chọn một vùng có ranh giới rõ:** ví dụ Catalog hoặc Ordering.
3. **Tạo package theo mô-đun:** gom web adapter, application, domain và infrastructure thuộc vùng đó.
4. **Định nghĩa public API:** chỉ công bố hành vi và kiểu dữ liệu cần cho bên gọi.
5. **Ẩn chi tiết nội bộ:** giới hạn visibility của repository, entity và implementation.
6. **Chuyển lời gọi trực tiếp sang API:** thay truy cập repository/entity của mô-đun khác bằng hợp đồng.
7. **Làm rõ quyền sở hữu dữ liệu:** xác định mô-đun nào được ghi vào bảng hoặc aggregate nào.
8. **Thêm architecture test:** ngăn dependency trái phép và vòng phụ thuộc quay lại.
9. **Chuyển các vùng tiếp theo:** dựa trên coupling thực tế và lợi ích thay đổi.
10. **Đo lại:** đánh giá số phụ thuộc chéo, phạm vi thay đổi và độ khó kiểm thử.

Một lần refactor tốt có thể bắt đầu từ việc tạo một module boundary mà không thay đổi giao diện HTTP hoặc cách triển khai. Điều này giảm rủi ro và giúp so sánh hành vi trước/sau.

## 19. Những lỗi thiết kế thường gặp

### Chỉ đổi tên package thành module

Nếu tất cả mô-đun vẫn truy cập mọi repository và entity của nhau, ranh giới chỉ tồn tại trên sơ đồ. Cần có API công khai và quy tắc phụ thuộc được kiểm tra.

### Tạo một module common quá lớn

Đưa mọi entity, enum, helper và service vào common khiến các mô-đun lại phụ thuộc vào một trung tâm chung. Chỉ chia sẻ kiểu dữ liệu nhỏ, ổn định và thực sự có ý nghĩa chung.

### Dùng entity ORM làm public API

Entity mang theo mapping, lifecycle và quan hệ persistence. Hãy dùng DTO hoặc value type cho hợp đồng giữa mô-đun.

### Cho Controller điều phối nhiều mô-đun

Controller nên điều phối giao thức web. Logic nghiệp vụ xuyên mô-đun nên nằm trong application use case hoặc page/query composition service có trách nhiệm rõ.

### Dùng event cho mọi lời gọi

Nếu use case cần kết quả ngay, gọi API đồng bộ có thể rõ hơn. Event phù hợp với thông báo và xử lý bất đồng bộ có chủ đích; dùng event không đúng sẽ làm luồng nghiệp vụ khó theo dõi.

### Giả định transaction bao trùm mọi thứ

Một transaction database không thể tự rollback tác dụng phụ đã xảy ra ở dịch vụ bên ngoài. Cần thiết kế trạng thái, bù trừ, idempotency hoặc outbox khi có xử lý nhiều bước.

### Tách microservice quá sớm

Tách dịch vụ trước khi ranh giới nghiệp vụ ổn định làm tăng chi phí mạng, vận hành và consistency. Modular monolith cho phép kiểm tra ranh giới trong cùng tiến trình trước.

## 20. Checklist review MVC trong monolith và modular monolith

- [ ] Đã phân biệt MVC với kiểu triển khai monolith hoặc microservices.
- [ ] Controller tiếp nhận request và điều phối, không chứa toàn bộ nghiệp vụ.
- [ ] View nhận DTO/View Model và không truy cập repository.
- [ ] Domain không phụ thuộc web framework hoặc persistence framework.
- [ ] Mô-đun được chia theo năng lực nghiệp vụ có trách nhiệm rõ.
- [ ] Mỗi mô-đun có API công khai tối thiểu.
- [ ] Mô-đun khác không truy cập entity hoặc repository nội bộ.
- [ ] Hướng phụ thuộc không tạo vòng giữa các mô-đun.
- [ ] Quyền sở hữu bảng, schema và trạng thái được xác định.
- [ ] Transaction gắn với use case và có chính sách lỗi rõ.
- [ ] Sự kiện nội bộ có ngữ nghĩa đồng bộ/bất đồng bộ được xác định.
- [ ] Có architecture test cho module boundary.
- [ ] Có unit, persistence, MVC, module integration và E2E test phù hợp.
- [ ] Chỉ cân nhắc tách service khi có yêu cầu scale, triển khai, bảo mật hoặc vận hành cụ thể.

## Kết luận

MVC và monolith giải quyết hai câu hỏi khác nhau. MVC tổ chức tương tác giữa request, nghiệp vụ và trình bày; monolith mô tả cách ứng dụng được đóng gói và triển khai. Khi ứng dụng nguyên khối phát triển, việc chia package theo tầng kỹ thuật có thể khiến các năng lực nghiệp vụ phụ thuộc lẫn nhau. Modular monolith giữ một đơn vị triển khai nhưng tạo ranh giới theo nghiệp vụ, công bố API nội bộ và kiểm soát quyền sở hữu dữ liệu. Có thể đặt Controller, application service, domain và infrastructure trong từng mô-đun, đồng thời dùng DTO, interface và architecture test để giữ hướng phụ thuộc. Cách tổ chức này giúp ứng dụng duy trì sự đơn giản của triển khai nguyên khối mà vẫn kiểm soát được độ phức tạp khi sản phẩm lớn lên.

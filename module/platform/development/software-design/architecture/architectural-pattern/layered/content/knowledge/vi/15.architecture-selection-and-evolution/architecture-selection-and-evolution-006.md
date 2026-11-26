# Kết hợp phân tầng với ranh giới tính năng trong modular monolith

Một modular monolith là ứng dụng được triển khai như một đơn vị thống nhất nhưng mã nguồn được chia thành các module có trách nhiệm và ranh giới rõ ràng. Mỗi module thường đại diện cho một tính năng hoặc năng lực nghiệp vụ, sở hữu logic và dữ liệu liên quan, đồng thời công bố một giao diện có kiểm soát cho các module khác sử dụng.

Kiến trúc phân tầng và ranh giới tính năng giải quyết hai câu hỏi khác nhau. Phân tầng trả lời “mã thực hiện trách nhiệm nào và phụ thuộc theo hướng nào?”. Ranh giới tính năng trả lời “logic nghiệp vụ nào thuộc về module nào và module nào được phép truy cập nó?”. Kết hợp hai cách nhìn giúp một ứng dụng vừa giữ được cấu trúc kỹ thuật rõ ràng vừa tránh việc mọi tính năng phụ thuộc trực tiếp vào một nhóm package dùng chung khổng lồ.

Trong module **Học tổ chức phần mềm theo kiến trúc phân tầng**, modular monolith là một lựa chọn tiến hóa phù hợp khi nhóm muốn chia hệ thống theo năng lực nghiệp vụ mà vẫn giữ một quy trình build và triển khai đơn giản. Không có một sơ đồ package duy nhất bắt buộc; điều quan trọng là mỗi tính năng có quyền sở hữu rõ, các tầng bên trong có trách nhiệm cụ thể và phụ thuộc giữa module được kiểm soát.

## 1. Phân tầng và ranh giới tính năng bổ sung cho nhau

Phân tầng thường chia mã theo trách nhiệm kỹ thuật:

- Presentation tiếp nhận giao tiếp bên ngoài.
- Application điều phối ca sử dụng.
- Domain mô hình hóa quy tắc và trạng thái nghiệp vụ.
- Infrastructure/Data Access triển khai lưu trữ và tích hợp.

Chia theo tính năng (feature/module) nhóm mã theo năng lực nghiệp vụ như Orders, Catalog, Billing hoặc Shipping. Một module có thể chứa các tầng cần thiết cho năng lực đó.

~~~mermaid
flowchart TB
    subgraph App["Ứng dụng modular monolith"]
      subgraph Orders["Module Orders"]
        OP[Presentation/API]
        OA[Application]
        OD[Domain]
        OI[Infrastructure]
        OP --> OA
        OA --> OD
        OI --> OD
        OI --> OA
      end
      subgraph Catalog["Module Catalog"]
        CA[Public API]
        CD[Domain]
        CI[Infrastructure]
        CA --> CD
        CI --> CD
      end
      subgraph Billing["Module Billing"]
        BA[Public API]
        BD[Domain]
        BI[Infrastructure]
        BA --> BD
        BI --> BD
      end
    end
    OA -->|dùng hợp đồng công khai| CA
    OA -->|dùng hợp đồng công khai| BA
~~~

Sơ đồ chỉ minh họa một cách tổ chức. Presentation có thể là một lớp ở cấp ứng dụng, sau đó định tuyến request tới module tương ứng. Một số module chỉ cần Application và Infrastructure; module khác có Domain model phong phú hơn. Không cần tạo đủ bốn package trong mọi module nếu trách nhiệm không tồn tại.

Có thể hiểu hai trục như sau:

| Cách chia | Nhóm theo | Câu hỏi được trả lời |
|---|---|---|
| Theo tầng | Trách nhiệm kỹ thuật | Thành phần này nhận request, điều phối, bảo vệ quy tắc hay truy cập dữ liệu? |
| Theo tính năng | Năng lực nghiệp vụ | Tính năng này thuộc module nào, ai sở hữu và ai được phép thay đổi? |

Nếu chỉ chia theo tầng ở cấp toàn ứng dụng, các tính năng có thể bị rải khắp nơi: tất cả controller nằm trong một package, tất cả service ở package khác và tất cả repository ở package thứ ba. Khi đó, thay đổi một tính năng đòi hỏi sửa nhiều khu vực và ranh giới nghiệp vụ khó nhìn thấy. Chia theo feature giúp nhóm mã liên quan gần nhau; phân tầng bên trong feature giữ cho các trách nhiệm vẫn tách biệt.

## 2. Modular monolith khác gì một monolith chỉ chia package?

Một ứng dụng có nhiều package chưa chắc đã là modular monolith. Module cần có hợp đồng và quy tắc truy cập được thực thi.

| Đặc điểm | Monolith chia package lỏng lẻo | Modular monolith |
|---|---|---|
| Tổ chức mã | Có thể nhóm theo tên hoặc tầng | Nhóm theo năng lực nghiệp vụ, có ranh giới |
| Truy cập nội bộ | Package nào cũng có thể import package khác | Chỉ dùng API được công bố của module khác |
| Dữ liệu | Nhiều tính năng có thể truy cập trực tiếp bảng của nhau | Module có quyền sở hữu rõ với dữ liệu của mình |
| Phụ thuộc | Dễ hình thành vòng | Đồ thị module được quy định và kiểm tra |
| Triển khai | Thường một artifact | Vẫn một artifact hoặc một đơn vị triển khai thống nhất |
| Kiểm thử | Chủ yếu kiểm thử toàn ứng dụng | Có thể kiểm thử module và hợp đồng độc lập |

Một modular monolith vẫn có thể chạy trong một JVM, dùng một database và được triển khai như một ứng dụng Spring Boot duy nhất. Ranh giới module là ranh giới thiết kế và mã nguồn. Chúng không tự tạo ra cô lập tiến trình, tài nguyên hoặc lỗi như microservice.

Để module có ý nghĩa, cần quy định rõ API công khai, package nội bộ, quyền sở hữu dữ liệu, hướng phụ thuộc và cách kiểm thử. Nếu module Orders có thể import bất kỳ lớp nào trong Catalog hoặc đọc trực tiếp bảng Catalog mà không qua hợp đồng, ranh giới đó chỉ tồn tại trên sơ đồ.

## 3. Tổ chức package theo feature, phân tầng bên trong

Một cấu trúc thường gặp là đặt module theo tính năng ở cấp cao nhất, rồi chia tầng trong module:

~~~text
com.example.shop
├── orders
│   ├── api
│   │   ├── OrdersFacade.java
│   │   └── OrderSummary.java
│   ├── application
│   │   ├── PlaceOrderService.java
│   │   └── CancelOrderService.java
│   ├── domain
│   │   ├── Order.java
│   │   └── OrderRepository.java
│   └── infrastructure
│       └── JpaOrderRepositoryAdapter.java
├── catalog
│   ├── api
│   │   ├── CatalogQuery.java
│   │   └── ProductDetails.java
│   ├── application
│   ├── domain
│   └── infrastructure
└── billing
    ├── api
    ├── application
    ├── domain
    └── infrastructure
~~~

Package api là phần module cho phép module khác sử dụng. Các package application, domain và infrastructure có thể được xem là nội bộ, tùy cách công bố hợp đồng. Module Orders không nên gọi trực tiếp JpaOrderRepositoryAdapter của chính nó từ module khác; module khác cũng không nên import PlaceOrderService hoặc OrderJpaEntity.

Một biến thể khác là tách module theo package Java riêng và đặt interface public ở package gốc. Một dự án có thể dùng Java module system hoặc module build Gradle/Maven để kiểm soát visibility chặt hơn. Chọn mức kiểm soát phù hợp với quy mô, công cụ và cách nhóm phát triển.

Không cần tạo API facade cho mọi class. Chỉ công bố những thao tác hoặc kiểu dữ liệu mà module khác thực sự cần. API càng rộng, module càng khó thay đổi nội bộ vì nhiều caller có thể phụ thuộc vào nó.

## 4. Thiết kế API công khai giữa các module

API công khai là hợp đồng giữa các năng lực nghiệp vụ. Nó nên diễn đạt ngôn ngữ của module sở hữu, không phơi bày implementation.

Ví dụ, Orders cần biết sản phẩm có tồn tại và có thể được đặt hay không. Orders có thể gọi một API của Catalog:

~~~java
package com.example.shop.catalog.api;

import java.util.Optional;
import java.util.UUID;

public interface CatalogQuery {
    Optional<ProductDetails> findOrderableProduct(UUID productId);
}

public record ProductDetails(
        UUID productId,
        String name,
        MoneySnapshot currentPrice,
        boolean orderable
) {}
~~~

Module Catalog tự quyết định dữ liệu cần lấy và cách truy vấn. Module Orders chỉ phụ thuộc vào hợp đồng công khai:

~~~java
package com.example.shop.orders.application;

public class PlaceOrderService {
    private final CatalogQuery catalog;
    private final OrderRepository orders;

    public PlaceOrderService(
            CatalogQuery catalog,
            OrderRepository orders) {
        this.catalog = catalog;
        this.orders = orders;
    }

    public OrderId place(PlaceOrderCommand command) {
        ProductDetails product = catalog
                .findOrderableProduct(command.productId())
                .filter(ProductDetails::orderable)
                .orElseThrow(ProductUnavailableException::new);

        Order order = Order.place(
                command.customerId(),
                product.productId(),
                product.currentPrice(),
                command.quantity()
        );

        orders.save(order);
        return order.getId();
    }
}
~~~

Ví dụ minh họa cách một module gọi API đồng bộ. Trong thực tế, Catalog có thể trả giá tại thời điểm truy vấn hoặc một snapshot có phiên bản; Orders cần lưu lại giá đã chấp nhận cùng đơn hàng để thay đổi giá sản phẩm sau đó không làm thay đổi lịch sử đơn.

Có thể dùng interface Java, facade, query service hoặc command handler làm API. Dù chọn hình thức nào, hợp đồng cần xác định:

- Thao tác nào được hỗ trợ và ý nghĩa nghiệp vụ của nó.
- Kiểu đầu vào/đầu ra không phụ thuộc lớp nội bộ.
- Cách biểu diễn dữ liệu không tồn tại, xung đột hoặc lỗi.
- Quyền truy cập và phạm vi tenant nếu có.
- Các bảo đảm về transaction, tính lũy đẳng hoặc tính nhất quán khi cần.

Không nên trả JPA entity hoặc Spring Data Page qua API module. Những kiểu đó khiến module gọi bị phụ thuộc vào schema và framework nội bộ của module sở hữu.

## 5. Kiểm soát đồ thị phụ thuộc giữa module

Một modular monolith cần đồ thị phụ thuộc có hướng rõ ràng. Ví dụ:

~~~mermaid
flowchart LR
    Web[Web / Presentation]
    O[Orders]
    C[Catalog]
    B[Billing]
    S[Shared Kernel]
    Web --> O
    O --> C
    O --> B
    O --> S
    C --> S
    B --> S
~~~

Trong ví dụ này, Orders dùng API của Catalog và Billing; các module có thể cùng sử dụng một số kiểu nhỏ trong Shared Kernel. Đồ thị không có đường phụ thuộc quay lại Orders. Đây chỉ là một ví dụ; một hệ thống có thể chọn module điều phối khác hoặc giao tiếp qua event tùy nhu cầu.

Các nguyên tắc hữu ích:

- Tránh phụ thuộc vòng giữa module. Nếu Orders cần Billing và Billing cần Orders, hãy xác định use case điều phối, port hoặc event để bỏ liên kết hai chiều.
- Chỉ phụ thuộc vào API công khai của module khác.
- Giữ dependency direction nhất quán. Module không nên import implementation của module khác.
- Không tạo một module Common chứa mọi DTO, entity, enum và utility.
- Ghi nhận các phụ thuộc hợp lệ và kiểm tra tự động khi có thể.

Nếu hai module cần chia sẻ một khái niệm có ngữ nghĩa thật sự chung, có thể tách một module nhỏ như Shared Kernel. Tuy nhiên, Shared Kernel cần phạm vi hẹp, chủ sở hữu rõ và quy trình thay đổi có phối hợp. Nếu mỗi module có cách hiểu khác nhau về cùng một khái niệm, nên dùng kiểu riêng và ánh xạ tại ranh giới thay vì ép dùng chung một class.

## 6. Quyền sở hữu dữ liệu: mỗi module chịu trách nhiệm với dữ liệu của mình

Ranh giới module không đầy đủ nếu chỉ kiểm soát package mà mọi module vẫn đọc và ghi trực tiếp bảng của nhau.

Ví dụ:

- Catalog sở hữu sản phẩm, giá hiện hành và trạng thái có thể bán.
- Orders sở hữu đơn hàng, dòng hàng và snapshot giá tại thời điểm đặt.
- Billing sở hữu khoản thanh toán, giao dịch và trạng thái đối soát.

Module khác cần dữ liệu thì gọi API công khai hoặc tiêu thụ event phù hợp. Không nên để Orders join trực tiếp các bảng nội bộ của Catalog hoặc cập nhật cột trạng thái sản phẩm bằng SQL của riêng Orders.

Một module có thể dùng chung một database vật lý với các module khác. Việc dùng chung máy chủ database không có nghĩa mọi module cùng sở hữu mọi bảng. Có thể phân vùng bằng schema, naming convention, database user/permission hoặc quy ước package/repository. Nếu dùng chung một schema, vẫn cần quy tắc rõ về module nào được ghi bảng nào.

Với báo cáo tổng hợp nhiều module, có thể tạo read model hoặc projection dành riêng cho báo cáo. Việc này cần hợp đồng dữ liệu và cơ chế cập nhật có kiểm soát; không nên biến báo cáo thành lý do để mọi module truy cập trực tiếp bảng nội bộ của nhau.

## 7. Giao tiếp đồng bộ hay bất đồng bộ?

Trong modular monolith, module có thể giao tiếp đồng bộ bằng lời gọi interface trong cùng tiến trình. Cách này đơn giản, dễ debug và có thể dùng cùng transaction database khi thiết kế cho phép.

Dùng event khi module khác chỉ cần biết một sự kiện đã xảy ra và không cần kết quả đồng bộ ngay. Ví dụ, Orders phát OrderPlaced; Billing xử lý yêu cầu thanh toán hoặc một module thông báo gửi email phản hồi. Event làm giảm phụ thuộc trực tiếp nhưng thêm yêu cầu về thứ tự, xử lý lặp, lỗi và tính nhất quán.

| Hình thức | Phù hợp khi | Chi phí cần cân nhắc |
|---|---|---|
| Gọi API đồng bộ | Cần kết quả ngay để hoàn thành use case | Coupling theo thời gian, độ trễ và lỗi lan truyền |
| Event nội bộ | Bên nhận có thể xử lý sau, không cần kết quả ngay | Event contract, retry, deduplication và eventual consistency |
| Orchestrator/use case điều phối | Một quy trình cần phối hợp nhiều module theo thứ tự rõ | Cần xác định module nào sở hữu quy trình và ranh giới transaction |

Không nên dùng event chỉ để tránh một interface đơn giản. Ngược lại, không nên gọi đồng bộ qua nhiều module nếu nghiệp vụ có thể hoàn tất bằng một quy trình bất đồng bộ và cần giảm phụ thuộc thời gian.

## 8. Transaction khi một use case đi qua nhiều module

Một modular monolith thường dùng chung transaction manager và database. Điều này cho phép một use case phối hợp thay đổi ở nhiều module trong cùng transaction, nhưng không có nghĩa nên làm như vậy tùy tiện.

Ví dụ, đặt hàng có thể cần tạo Order và giữ chỗ tồn kho. Nếu hai thay đổi phải nguyên tử theo quy tắc nghiệp vụ, một application orchestrator có thể điều phối các module trong transaction được thiết kế rõ. Tuy nhiên, nếu module nào cũng truy cập trực tiếp repository nội bộ của module kia, ranh giới quyền sở hữu sẽ bị phá vỡ.

Có thể chọn một trong các cách:

- Một module sở hữu use case điều phối và gọi API công khai của module khác.
- Module sở hữu dữ liệu cung cấp thao tác có ý nghĩa nghiệp vụ, chẳng hạn reserveStock, thay vì cho caller tự sửa bảng.
- Nếu quy trình có thể hoàn tất theo nhiều bước, dùng trạng thái và event nội bộ, chấp nhận eventual consistency có chủ đích.

Ranh giới transaction nên được đặt theo use case và bảo đảm nghiệp vụ. Không nên để một method repository tùy tiện mở transaction riêng cho mỗi thao tác nếu use case cần tất cả thay đổi commit cùng nhau. Đồng thời, không nên giữ transaction dài trong khi chờ một lời gọi HTTP bên ngoài.

## 9. Tổ chức kiểm thử theo module và hợp đồng

Modular monolith cho phép kiểm thử từng module mà không cần triển khai từng module như một service riêng.

- **Domain unit test:** kiểm tra quy tắc và trạng thái trong từng module.
- **Application unit test:** thay các API/port của module khác bằng fake hoặc mock để kiểm tra điều phối.
- **Module integration test:** khởi tạo module với adapter và database kiểm thử cần thiết.
- **Contract test:** xác minh module cung cấp API đúng hợp đồng và caller dùng đúng kiểu dữ liệu/ý nghĩa.
- **Architecture test:** ngăn import package nội bộ, phụ thuộc ngược hoặc chu trình module.
- **End-to-end test:** kiểm tra một số luồng liên module quan trọng trong ứng dụng hoàn chỉnh.

Ví dụ với ArchUnit, có thể cấm module Orders phụ thuộc package infrastructure nội bộ của Catalog:

~~~java
@AnalyzeClasses(packages = "com.example.shop")
class ModuleBoundaryTest {

    @ArchTest
    static final ArchRule ordersMustNotUseCatalogInternals =
            noClasses()
                    .that().resideInAPackage("..orders..")
                    .should().dependOnClassesThat()
                    .resideInAPackage("..catalog.infrastructure..");

    @ArchTest
    static final ArchRule catalogMustNotUseOrdersInternals =
            noClasses()
                    .that().resideInAPackage("..catalog..")
                    .should().dependOnClassesThat()
                    .resideInAPackage("..orders.application..");
}
~~~

Các package rule cần điều chỉnh theo cấu trúc thật. Có thể bổ sung rule chỉ cho phép Orders truy cập Catalog API và cấm truy cập domain hoặc persistence nội bộ. Test kiến trúc biến quy ước thành kiểm tra tự động, giúp module không dần trở lại trạng thái package lỏng lẻo.

## 10. Chọn mức độ module hóa phù hợp

Không phải mọi tính năng đều cần cùng mức độ tách. Một module CRUD nhỏ có thể chỉ cần API, application service và adapter dữ liệu. Một miền có nhiều quy tắc có thể cần Domain model phong phú, port riêng và test sâu hơn.

Có thể dùng các câu hỏi sau:

1. Năng lực nghiệp vụ này có thuật ngữ, quy tắc hoặc vòng đời riêng không?
2. Có nhóm hoặc người chịu trách nhiệm rõ ràng cho module không?
3. Những module nào cần sử dụng chức năng này và họ cần những thao tác nào?
4. Dữ liệu nào module sở hữu, dữ liệu nào chỉ được đọc qua API?
5. Có thể tạo đồ thị phụ thuộc một chiều hay đang có vòng?
6. Việc tách module giúp thay đổi và kiểm thử độc lập hơn bao nhiêu?
7. Chi phí mapping, API contract và phối hợp transaction có hợp lý không?

Không nên tạo module cho mọi entity hoặc mọi bảng. Ranh giới nên phản ánh năng lực và quyền sở hữu nghiệp vụ, không chỉ cấu trúc database.

## 11. Tiến hóa từ monolith hiện có sang modular monolith

Có thể chuyển đổi từng bước mà không cần viết lại ứng dụng:

1. **Khảo sát tính năng:** xác định các luồng nghiệp vụ, package, service và bảng dữ liệu hiện có.
2. **Nhóm theo năng lực:** gom các thành phần cùng phục vụ một capability như Orders, Catalog hoặc Billing.
3. **Xác định ownership:** quyết định module nào sở hữu quy tắc, dữ liệu và hợp đồng của từng năng lực.
4. **Tạo API module:** công bố những thao tác caller cần, giữ implementation nội bộ.
5. **Chuyển callers:** thay import trực tiếp bằng API công khai, adapter hoặc event phù hợp.
6. **Khóa truy cập nội bộ:** dùng package visibility, module build hoặc architecture test.
7. **Tách dữ liệu từng bước:** chuyển quyền ghi về module sở hữu, thay truy vấn xuyên module bằng API hoặc projection.
8. **Đo và kiểm tra:** theo dõi build, test, hiệu năng và số lượng phụ thuộc chéo sau mỗi bước.

Một cách an toàn là bắt đầu với một feature có ranh giới tương đối rõ, chẳng hạn Catalog. Chuyển API, test và quyền sở hữu dữ liệu của feature đó trước, rồi áp dụng kinh nghiệm cho module tiếp theo. Không cần thay đổi toàn bộ cấu trúc package trong một lần.

## 12. Những lỗi thường gặp khi kết hợp hai cách chia

| Lỗi | Hậu quả | Cách điều chỉnh |
|---|---|---|
| Chỉ đổi tên package thành module | Không có API hoặc ownership thực | Định nghĩa hợp đồng và giới hạn truy cập |
| Mỗi module có đủ mọi tầng dù không cần | Nhiều package rỗng và lớp chuyển tiếp | Tạo tầng theo trách nhiệm thực tế |
| Caller import implementation nội bộ | Thay đổi lan giữa module | Chỉ sử dụng public API |
| Chia sẻ entity JPA giữa module | Coupling theo schema và ORM | Dùng API DTO hoặc kiểu riêng, mapping ở biên |
| Mọi module truy cập mọi bảng | Không rõ quyền sở hữu dữ liệu | Quy định module sở hữu và quyền ghi |
| Dùng Common cho mọi thứ | Common thành dependency hub | Giữ shared kernel nhỏ và có ngữ nghĩa chung |
| Dùng event quá mức | Khó theo dõi, eventual consistency không cần thiết | Dùng lời gọi đồng bộ khi phù hợp |
| Cho phép module phụ thuộc vòng | Build và thay đổi khó kiểm soát | Thiết kế lại ownership, port hoặc event |

## 13. Checklist thiết kế modular monolith

Trước khi coi một feature đã có ranh giới module rõ, hãy kiểm tra:

- Module có tên và trách nhiệm nghiệp vụ dễ hiểu không?
- API công khai có hẹp và ổn định không?
- Các package implementation có được giữ nội bộ không?
- Các tầng bên trong có hướng phụ thuộc rõ ràng không?
- Module khác có tránh import entity, repository và service nội bộ không?
- Quyền sở hữu dữ liệu và quyền ghi có được xác định không?
- Đồ thị module có tránh phụ thuộc vòng không?
- Shared Kernel có thực sự chứa khái niệm dùng chung không?
- Giao tiếp đồng bộ, event và transaction được chọn theo nhu cầu use case không?
- Có unit test, contract test và architecture test để giữ ranh giới không?

Kết hợp phân tầng với ranh giới tính năng giúp modular monolith vừa giữ được trách nhiệm kỹ thuật rõ ràng vừa tổ chức mã theo năng lực nghiệp vụ. Các tầng xác định cách một module thực hiện công việc; module xác định ai sở hữu hành vi, dữ liệu và hợp đồng. Khi các API công khai hẹp, dữ liệu có chủ sở hữu và phụ thuộc không tạo vòng, hệ thống có thể tiếp tục phát triển trong một đơn vị triển khai thống nhất mà vẫn giữ khả năng thay đổi từng phần.


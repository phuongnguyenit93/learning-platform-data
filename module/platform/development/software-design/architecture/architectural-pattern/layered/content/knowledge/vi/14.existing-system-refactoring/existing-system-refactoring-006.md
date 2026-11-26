# Tháo phụ thuộc vòng bằng điều chỉnh trách nhiệm và quyền sở hữu

Phụ thuộc vòng xuất hiện khi hai hoặc nhiều package, module hoặc thành phần cần biết lẫn nhau theo một chu trình. Ví dụ, Application phụ thuộc Infrastructure để dùng repository, trong khi Infrastructure lại import Application để gọi service. Chu trình này làm ranh giới tầng mất ý nghĩa: thay đổi ở một phía dễ kéo theo phía còn lại, khó kiểm thử độc lập và có thể khiến hệ thống build hoặc khởi động phức tạp.

Cách tháo phụ thuộc vòng bền vững là xem lại trách nhiệm và quyền sở hữu: thành phần nào thực sự cần khả năng đó, hợp đồng nên thuộc về ai, và implementation nào nên phụ thuộc vào hợp đồng. Đôi khi cần đảo hướng phụ thuộc bằng interface/port; đôi khi cần tách một khái niệm dùng chung có ngữ nghĩa ổn định; cũng có trường hợp phải chuyển trách nhiệm về đúng module sở hữu nó.

Trong module **Học tổ chức phần mềm theo kiến trúc phân tầng**, việc tháo chu trình giúp giữ hướng phụ thuộc hợp lý giữa Presentation, Application, Domain và Data Access/Infrastructure. Mục tiêu là làm rõ quyền sở hữu và giới hạn thay đổi, không phải chỉ làm cho công cụ build hết báo lỗi.

## 1. Phụ thuộc vòng là gì?

Một phụ thuộc vòng xảy ra khi có một đường đi từ thành phần A qua các thành phần khác rồi quay lại A. Ví dụ:

~~~mermaid
flowchart LR
    A[Application] --> I[Infrastructure]
    I --> A
~~~

Ở mức package, có thể thấy chu trình:

- Package application.order import lớp trong infrastructure.persistence.
- Package infrastructure.persistence import use case hoặc service trong application.order.
- Hai package không thể thay đổi độc lập; một số cấu trúc module còn không thể biên dịch nếu chúng được tách thành các module build riêng.

Chu trình cũng có thể xuất hiện ở cấp module:

~~~mermaid
flowchart LR
    M1[orders-application] --> M2[orders-persistence]
    M2 --> M3[orders-api]
    M3 --> M1
~~~

Cần phân biệt phụ thuộc mã nguồn với luồng gọi lúc chạy. Một Application service gọi interface repository, còn adapter Infrastructure triển khai interface đó là một cách thiết kế hợp lệ: mã nguồn Infrastructure phụ thuộc vào hợp đồng do Application sở hữu, nhưng luồng gọi lúc chạy đi từ Application qua interface tới adapter. Đây không phải chu trình phụ thuộc mã nguồn.

Ngoài ra, Spring có thể gặp circular bean dependency khi bean A cần bean B và bean B cần bean A trong lúc khởi tạo. Đây là vấn đề ở đồ thị object lúc chạy, có liên quan nhưng không hoàn toàn giống phụ thuộc package/module. Sửa bằng cách bật cơ chế xử lý circular reference hoặc dùng lazy injection có thể làm ứng dụng khởi động được, nhưng thường che giấu việc trách nhiệm đang đan xen. Hãy tìm nguyên nhân thiết kế trước khi chọn giải pháp cấu hình.

## 2. Vì sao phụ thuộc vòng làm hệ thống khó thay đổi?

Một chu trình thường tạo ra một số vấn đề:

- **Không rõ quyền sở hữu:** hai module cùng định nghĩa hoặc sửa cùng một khái niệm, không có bên chịu trách nhiệm cuối cùng.
- **Thay đổi lan truyền:** thay đổi một DTO, interface hoặc entity buộc nhiều module cập nhật đồng thời.
- **Khó kiểm thử riêng:** để kiểm thử một package phải dựng thêm các thành phần ở phía còn lại.
- **Khó tái sử dụng:** module muốn được dùng ở nơi khác lại kéo theo cả module phụ thuộc ngược.
- **Build và triển khai bị ràng buộc:** module không thể build độc lập hoặc phải build theo một nhóm lớn.
- **Khó hiểu luồng điều khiển:** người đọc phải lần qua nhiều lớp để biết ai sở hữu quy tắc và ai chỉ cung cấp kỹ thuật.

Không phải mọi liên kết hai chiều ở runtime đều là lỗi. Hai object có thể giữ tham chiếu qua lại vì mô hình miền cần điều đó. Nhưng phụ thuộc mã nguồn giữa các tầng hoặc module cần được kiểm soát rõ. Đặc biệt, Domain không nên import Presentation hoặc Infrastructure chỉ để gọi một tiện ích kỹ thuật.

## 3. Tìm chu trình trước khi sửa

Đừng bắt đầu bằng cách chuyển file sang một package khác theo cảm tính. Trước tiên hãy xác định các nút và cạnh trong đồ thị phụ thuộc:

- Nút có thể là package, module build, service hoặc bean.
- Cạnh A → B nghĩa là A cần biết mã nguồn hoặc hợp đồng của B.
- Một chu trình là đường đi có thể quay về nút ban đầu.

Có thể dùng IDE, công cụ phân tích dependency, Gradle/Maven dependency report hoặc công cụ kiểm tra kiến trúc như ArchUnit để tìm liên kết. Khi phân tích, phân loại từng cạnh:

| Loại phụ thuộc | Ví dụ | Câu hỏi cần đặt |
|---|---|---|
| Kiểu dữ liệu | Application import JPA entity | Kiểu này thuộc ngữ nghĩa của tầng nào? |
| Gọi service | Infrastructure gọi trực tiếp Application service | Có cần một port hoặc event không? |
| Repository | Application phụ thuộc Spring Data interface | Application có đang biết framework lưu trữ không? |
| DTO | Hai tầng dùng chung một DTO tổng hợp | Hợp đồng này phục vụ giao thức hay use case? |
| Tiện ích | Hai module cùng import một helper | Helper có ý nghĩa ổn định và chủ sở hữu rõ ràng không? |

Ví dụ, đồ thị có thể trông như sau:

~~~text
application.order
  -> infrastructure.persistence
  -> domain.order

infrastructure.persistence
  -> application.order
  -> domain.order
~~~

Ở đây, application.order cần repository JPA để lưu đơn hàng, còn adapter persistence cần application.order để lấy kiểu command hoặc gọi service. Cả hai chiều đều có thể được giải quyết bằng cách đưa hợp đồng về đúng phía sở hữu.

Khi chu trình đi qua nhiều module, hãy tìm strongly connected component (SCC): nhóm các nút mà mỗi nút đều có đường đi tới mọi nút còn lại. Một SCC có nhiều module thường là dấu hiệu cần xem xét ranh giới module hoặc quyền sở hữu hợp đồng. Không nhất thiết phải tách tất cả các cạnh trong SCC; hãy chọn cạnh có ý nghĩa sai rõ nhất.

## 4. Đặt hợp đồng ở phía cần khả năng đó

Một cách tháo vòng phổ biến là để bên cần một khả năng định nghĩa interface, còn bên cung cấp khả năng triển khai interface đó.

Ví dụ ban đầu có phụ thuộc ngược:

~~~java
// Application gọi trực tiếp implementation của Infrastructure
public class PlaceOrderService {
    private final JpaOrderRepositoryAdapter repository;

    public PlaceOrderService(JpaOrderRepositoryAdapter repository) {
        this.repository = repository;
    }
}
~~~

Nếu adapter cũng import Application để dùng command hoặc gọi service, hai module bị khóa vào nhau.

Chuyển sang port do Application sở hữu:

~~~java
package com.example.shop.application.port;

public interface OrderStore {
    Optional<Order> findById(OrderId id);
    void save(Order order);
}
~~~

Application service chỉ phụ thuộc hợp đồng:

~~~java
package com.example.shop.application.order;

public class PlaceOrderService {
    private final OrderStore orders;

    public PlaceOrderService(OrderStore orders) {
        this.orders = orders;
    }

    public OrderId place(PlaceOrderCommand command) {
        Order order = Order.place(
                command.customerId(),
                command.productId(),
                command.quantity()
        );
        orders.save(order);
        return order.getId();
    }
}
~~~

Infrastructure phụ thuộc vào port để triển khai:

~~~java
package com.example.shop.infrastructure.persistence;

@Repository
public class JpaOrderStoreAdapter implements OrderStore {
    private final SpringDataOrderRepository jpa;

    public JpaOrderStoreAdapter(SpringDataOrderRepository jpa) {
        this.jpa = jpa;
    }

    @Override
    public Optional<Order> findById(OrderId id) {
        return jpa.findById(id.value())
                .map(OrderJpaEntity::toDomain);
    }

    @Override
    public void save(Order order) {
        jpa.save(OrderJpaEntity.fromDomain(order));
    }
}
~~~

Đồ thị phụ thuộc sau thay đổi:

~~~mermaid
flowchart LR
    A[Application]
    P[OrderStore port]
    I[Infrastructure adapter]
    D[Domain]
    A --> P
    A --> D
    I --> P
    I --> D
~~~

Cả Application và Infrastructure cùng biết hợp đồng OrderStore; Infrastructure biết Domain model cần ánh xạ. Application không cần import JpaOrderStoreAdapter hoặc Spring Data. Lúc chạy, dependency injection cung cấp adapter phù hợp.

Port nên diễn đạt nhu cầu của use case, không sao chép nguyên vẹn interface của thư viện. Nếu interface có các kiểu như EntityManager, JpaRepository hoặc Page của Spring Data, chi tiết framework vẫn đang rò vào tầng cao.

## 5. Chuyển kiểu dữ liệu về đúng chủ sở hữu

Một chu trình thường tồn tại vì hai module dùng chung một kiểu nhưng không thống nhất ai sở hữu nó. Ví dụ, Application định nghĩa OrderRequest, còn Infrastructure import kiểu này để dựng entity; đồng thời Application import entity để xử lý use case.

Hãy tách kiểu theo ngữ nghĩa:

- Presentation sở hữu request/response DTO của HTTP.
- Application sở hữu command, query, input/output model và port của use case.
- Domain sở hữu entity, value object và quy tắc miền.
- Infrastructure sở hữu JPA entity, projection kỹ thuật và kiểu của client bên ngoài.

Ví dụ:

~~~java
// Presentation: mô tả JSON client gửi
public record PlaceOrderRequest(
        UUID productId,
        int quantity
) {}

// Application: mô tả ý định của ca sử dụng
public record PlaceOrderCommand(
        CustomerId customerId,
        ProductId productId,
        Quantity quantity
) {}

// Domain: biểu diễn khái niệm nghiệp vụ
public record Quantity(int value) {
    public Quantity {
        if (value <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
    }
}

// Infrastructure: cấu trúc lưu trữ, ví dụ rút gọn
@Entity
public class OrderJpaEntity {
    @Id
    private UUID id;

    private UUID customerId;
    private UUID productId;
    private int quantity;
}
~~~

Presentation ánh xạ request thành command. Application dùng command để gọi Domain. Adapter Infrastructure chuyển đổi giữa Domain và JPA entity. Việc có mapping ở ranh giới không phải dấu hiệu kiến trúc sai; đó là cách giữ mỗi tầng sở hữu biểu diễn phù hợp với trách nhiệm của nó.

Không nên tạo một module common để chứa tất cả DTO và entity chỉ nhằm phá chu trình. Nếu common lại import Application hoặc Infrastructure thì chu trình chỉ được chuyển vị trí. Nếu common chứa kiểu không có ngữ nghĩa chung ổn định, nó sẽ trở thành nơi phụ thuộc tập trung.

## 6. Tách abstraction dùng chung khi có ngữ nghĩa thật sự chung

Đôi khi hai module phụ thuộc lẫn nhau vì cả hai cùng cần một khái niệm thực sự độc lập, ví dụ Money, Currency hoặc một kiểu định danh dùng chung trong cùng miền. Có thể tách khái niệm đó thành module nhỏ hơn, có chủ sở hữu rõ ràng và không phụ thuộc ngược vào hai module ban đầu.

~~~mermaid
flowchart TD
    A[Orders]
    B[Billing]
    S[Shared Domain Types]
    A --> S
    B --> S
~~~

Cách này phù hợp khi module mới chứa một tập kiểu nhỏ, ổn định và có ý nghĩa độc lập. Không nên đưa logic điều phối của Orders hoặc Billing vào Shared chỉ để làm đồ thị không còn chu trình. Module shared phải có API hẹp, quy tắc tương thích và người chịu trách nhiệm.

Nếu khái niệm chỉ có ý nghĩa trong một bounded context, không nhất thiết phải dùng chung một class giữa các context. Có thể để mỗi context sở hữu kiểu riêng và ánh xạ ở ranh giới. Hai kiểu có cùng tên hoặc cùng cấu trúc không nhất thiết phải là cùng một hợp đồng.

## 7. Tách giao tiếp hai chiều bằng event hoặc mediator khi phù hợp

Một chu trình khác xuất hiện khi hai module gọi service của nhau trực tiếp. Ví dụ, OrderService gọi BillingService để thu tiền, còn BillingService gọi OrderService để cập nhật trạng thái đơn.

Trước khi chuyển sang event, hãy xác định liệu hai bước có thật sự cần gọi đồng bộ hay không. Nếu Billing chỉ cần thông báo rằng thanh toán đã được xác nhận, nó có thể phát một event; Order xử lý event đó qua một handler do phía Order sở hữu.

~~~mermaid
flowchart LR
    O[Orders] -->|PaymentRequested| E[Event channel]
    E --> B[Billing]
    B -->|PaymentAuthorized| E
    E --> H[Orders event handler]
    H --> O
~~~

Event tách phụ thuộc trực tiếp giữa hai module, nhưng tạo ra các yêu cầu mới: schema event, versioning, xử lý lặp, thứ tự, retry và eventual consistency. Nếu cần kết quả tức thời, có thể dùng một port ở phía gọi và adapter ở phía tích hợp. Event không phải cách sửa mặc định cho mọi chu trình.

Một mediator hoặc application orchestrator cũng có thể điều phối nhiều module mà không để chúng gọi trực tiếp lẫn nhau. Tuy nhiên, mediator cần có trách nhiệm rõ ràng và không nên trở thành một service trung tâm chứa toàn bộ nghiệp vụ của các module.

## 8. Điều chỉnh trách nhiệm thay vì chỉ di chuyển interface

Có những chu trình xuất hiện vì một module đang làm việc thuộc trách nhiệm của module khác. Ví dụ:

- Infrastructure gọi Application để yêu cầu Application tự chuyển đổi JPA entity.
- Domain gọi một service gửi email vì nghiệp vụ cần thông báo.
- Presentation truy cập repository vì Application chưa có use case phù hợp.
- Một module báo cáo gọi ngược vào module đơn hàng để lấy dữ liệu nội bộ thay vì dùng query contract.

Hãy chuyển trách nhiệm về đúng tầng:

| Trách nhiệm đặt sai | Điều chỉnh |
|---|---|
| Application biết JPA entity và repository của Spring | Đưa port và kiểu dữ liệu use case vào Application; adapter Infrastructure ánh xạ |
| Domain gửi email hoặc gọi HTTP | Domain thể hiện sự kiện/ý định; Application điều phối, Infrastructure thực hiện |
| Presentation truy cập database trực tiếp | Tạo use case/query port trong Application |
| Infrastructure gọi ngược controller hoặc application service | Để adapter thực hiện port; hoặc phát event để use case thích hợp xử lý |
| Shared module chứa logic riêng của nhiều module | Đưa logic về module sở hữu; chỉ giữ kiểu thực sự dùng chung |

Nếu chỉ chuyển interface mà vẫn để tầng thấp quyết định quy tắc nghiệp vụ, chu trình có thể biến mất về mặt import nhưng quyền sở hữu vẫn sai. Hãy kiểm tra cả vị trí định nghĩa, dữ liệu mà interface sử dụng và nơi quyết định hành vi.

## 9. Phân biệt chu trình module với circular bean trong Spring

Spring có thể báo lỗi tạo bean khi A phụ thuộc B và B phụ thuộc A qua constructor injection. Ví dụ:

~~~java
@Service
public class OrderService {
    public OrderService(BillingService billing) {}
}

@Service
public class BillingService {
    public BillingService(OrderService orders) {}
}
~~~

Cả hai bean cần nhau để khởi tạo, nên container không thể tạo một bean hoàn chỉnh trước bean còn lại theo cách thông thường.

Cách xử lý tốt thường là thay đổi trách nhiệm:

- Tách use case điều phối hai thao tác thành một application service thứ ba.
- Định nghĩa port ở phía cần khả năng và để adapter cung cấp.
- Dùng event nếu phản hồi không cần đồng bộ.
- Tách logic dùng chung thành một thành phần nhỏ có ý nghĩa độc lập.

Dùng @Lazy hoặc setter injection đôi khi có thể trì hoãn việc giải quyết tham chiếu, nhưng không tự loại bỏ coupling. Chỉ dùng khi có lý do vòng đời cụ thể và đã hiểu tác động. Không bật circular reference toàn cục để che một chu trình thiết kế.

## 10. Quy trình refactor tăng dần trong hệ thống hiện có

Tháo phụ thuộc vòng trong hệ thống đang chạy cần giữ hành vi và giảm rủi ro. Có thể thực hiện theo từng bước:

1. **Ghi nhận chu trình:** xác định package/module/bean tham gia và các import hoặc lời gọi tạo thành vòng.
2. **Xác định mục tiêu:** chọn hướng phụ thuộc mong muốn dựa trên trách nhiệm của các tầng.
3. **Tìm chủ sở hữu hợp đồng:** quyết định interface và kiểu dữ liệu thuộc Application, Domain, Presentation hay provider bên ngoài.
4. **Tạo abstraction hẹp:** định nghĩa port hoặc query contract chỉ chứa khả năng thực sự cần.
5. **Viết adapter:** chuyển implementation hiện tại sang adapter phụ thuộc port và ánh xạ kiểu ở ranh giới.
6. **Chuyển callers:** thay phụ thuộc lớp cụ thể bằng interface; dùng constructor injection.
7. **Xóa đường phụ thuộc cũ:** gỡ import, method chuyển tiếp và kiểu dùng chung không còn cần thiết.
8. **Kiểm tra lại đồ thị:** xác minh chu trình đã biến mất ở cấp package/module/bean mà không tạo vòng mới.
9. **Chạy kiểm thử phù hợp:** unit test use case, adapter integration test và test luồng quan trọng.
10. **Triển khai theo lát nhỏ:** nếu thay đổi rộng, giữ các bước tương thích tạm thời rồi xóa adapter cũ sau khi callers đã chuyển hết.

Một refactor tốt có thể thay đổi package hoặc module trong nhiều commit nhỏ. Không nên di chuyển hàng loạt file và đổi tên cùng lúc nếu điều đó khiến khó xác định thay đổi nào gây lỗi.

## 11. Kiểm soát hướng phụ thuộc bằng kiểm thử kiến trúc

Sau khi tháo chu trình, cần ngăn nó quay lại. Có thể dùng ArchUnit để kiểm tra package Domain không phụ thuộc Presentation hoặc Infrastructure:

~~~java
@AnalyzeClasses(packages = "com.example.shop")
class LayerRulesTest {

    @ArchTest
    static final ArchRule domainDoesNotDependOnInfrastructure =
            noClasses()
                    .that().resideInAPackage("..domain..")
                    .should().dependOnClassesThat()
                    .resideInAPackage("..infrastructure..");

    @ArchTest
    static final ArchRule applicationDoesNotDependOnInfrastructure =
            noClasses()
                    .that().resideInAPackage("..application..")
                    .should().dependOnClassesThat()
                    .resideInAPackage("..infrastructure..");

    @ArchTest
    static final ArchRule domainDoesNotDependOnPresentation =
            noClasses()
                    .that().resideInAPackage("..domain..")
                    .should().dependOnClassesThat()
                    .resideInAPackage("..presentation..");
}
~~~

Các rule cần điều chỉnh theo package thật của dự án. Nếu dùng module build riêng, Gradle/Maven cũng có thể ngăn module khai báo dependency trái hướng. Architecture test không thay thế review thiết kế, nhưng biến một số nguyên tắc thành kiểm tra tự động.

Cũng cần kiểm tra dependency graph của Spring context nếu ứng dụng có nhiều bean. Một bài test khởi động context giúp phát hiện circular bean dependency, nhưng không thay thế kiểm tra dependency source giữa package/module.

## 12. Các lỗi thường gặp khi tháo phụ thuộc vòng

| Cách xử lý | Vì sao chưa đủ | Cách tiếp cận tốt hơn |
|---|---|---|
| Chuyển interface vào package common tùy tiện | Không xác định chủ sở hữu và có thể tạo coupling mới | Đặt port ở phía cần khả năng; chỉ tách shared type khi có ngữ nghĩa độc lập |
| Dùng @Lazy để Spring khởi động | Che circular bean reference, không sửa trách nhiệm | Tách orchestration, port hoặc event |
| Tạo một module Shared chứa mọi thứ | Shared trở thành nơi tập trung phụ thuộc | Giữ module nhỏ, ổn định và có owner |
| Chuyển class qua package nhưng giữ nguyên imports | Đồ thị phụ thuộc không thay đổi | Kiểm tra cạnh phụ thuộc sau mỗi bước |
| Dùng event cho mọi lời gọi | Thêm eventual consistency và vận hành không cần thiết | Chọn event khi giao tiếp bất đồng bộ phù hợp nghiệp vụ |
| Tạo interface cho từng class | Tăng abstraction nhưng không giải quyết quyền sở hữu | Tạo interface khi có ranh giới, khả năng thay thế hoặc nhu cầu kiểm thử thực |
| Xóa một cạnh nhưng bỏ mất hành vi | Hệ thống build được nhưng use case không còn hoàn chỉnh | Viết test hành vi trước và sau refactor |

## 13. Checklist xác minh sau refactor

Sau khi thay đổi, hãy xác minh:

1. Đồ thị package/module không còn chu trình ở ranh giới đã chọn.
2. Domain không import Presentation, Infrastructure hoặc framework kỹ thuật.
3. Application phụ thuộc vào port/contract thay vì adapter cụ thể.
4. Infrastructure triển khai hợp đồng và giữ mapping kỹ thuật bên trong.
5. Presentation gọi use case, không truy cập persistence trực tiếp.
6. Không có module common mới chứa trách nhiệm chưa rõ chủ sở hữu.
7. Spring context khởi động mà không cần circular bean workaround.
8. Unit test, integration test và architecture test đều kiểm tra đúng ranh giới.
9. Hành vi nghiệp vụ trước và sau refactor vẫn tương đương.
10. Các abstraction tạm thời hoặc adapter chuyển tiếp đã được lên kế hoạch loại bỏ.

Tháo phụ thuộc vòng bằng điều chỉnh trách nhiệm và quyền sở hữu là một hoạt động thiết kế, không chỉ là thao tác sửa import. Khi hợp đồng nằm ở nơi có ngữ nghĩa phù hợp, tầng cần khả năng phụ thuộc vào abstraction và tầng kỹ thuật triển khai abstraction đó, hệ thống có thể giữ hướng phụ thuộc rõ ràng. Refactor từng bước cùng kiểm thử kiến trúc giúp loại bỏ chu trình mà vẫn bảo toàn hành vi của hệ thống hiện có.


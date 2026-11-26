# Xác định nơi sở hữu hợp đồng để tránh phụ thuộc ngược

Trong kiến trúc phân tầng, các tầng cần trao đổi dữ liệu và gọi khả năng của nhau thông qua những hợp đồng rõ ràng. Một hợp đồng có thể là interface, kiểu dữ liệu, command, query, event hoặc API schema. Vấn đề quan trọng là tầng nào có quyền định nghĩa và thay đổi hợp đồng đó.

Quy tắc hữu ích là đặt hợp đồng tại ranh giới của phần có ý nghĩa và có trách nhiệm sử dụng nó. Với một cổng mà Application cần để gọi ra ngoài, Application thường sở hữu interface và các kiểu dữ liệu của cổng; Infrastructure cung cấp implementation. Với dữ liệu HTTP, Presentation sở hữu request/response DTO của giao thức. Cách đặt này giúp tầng triển khai phụ thuộc vào hợp đồng ổn định, thay vì buộc tầng nghiệp vụ phụ thuộc ngược vào chi tiết kỹ thuật.

Trong module **Học tổ chức phần mềm theo kiến trúc phân tầng**, việc xác định quyền sở hữu hợp đồng giúp kiểm soát hướng phụ thuộc giữa Presentation, Application, Domain và Data Access/Infrastructure. Không có một vị trí duy nhất đúng cho mọi interface; cần xét hợp đồng đang diễn đạt ngữ nghĩa của ai và ai có quyền quyết định nó thay đổi như thế nào.

## 1. Hợp đồng là gì và vì sao quyền sở hữu quan trọng?

Hợp đồng là thỏa thuận về cách hai thành phần cộng tác. Nó quy định một hoặc nhiều điều sau:

- Những thao tác mà bên gọi có thể yêu cầu.
- Dữ liệu đầu vào và đầu ra, cùng ý nghĩa của từng trường.
- Điều kiện hợp lệ, kết quả có thể xảy ra và cách biểu diễn lỗi.
- Bảo đảm về thứ tự, tính nhất quán, giao dịch, tính lặp an toàn hoặc thời hạn phản hồi.
- Quy tắc tương thích khi một bên thay đổi.

Ví dụ, PaymentGateway có thể quy định Application được yêu cầu cấp phép thanh toán bằng một số tiền và mã giao dịch, sau đó nhận kết quả được chấp nhận hoặc bị từ chối. Hợp đồng này diễn đạt điều mà ca sử dụng thanh toán cần. Nó không nên yêu cầu Application biết endpoint HTTP của nhà cung cấp, tên header xác thực hay cấu trúc JSON riêng của đối tác.

Nếu hợp đồng nằm sai tầng, phụ thuộc có thể đi ngược hướng kiến trúc. Chẳng hạn, một service nghiệp vụ import JpaRepository chỉ để lưu đơn hàng. Khi đó, mã Application phải biết Spring Data JPA. Nếu sau này thay đổi cách lưu trữ, phần nghiệp vụ cũng phải thay đổi theo chi tiết kỹ thuật.

Quyền sở hữu hợp đồng không chỉ là vị trí đặt file interface. Nó xác định ai có quyền quyết định ngữ nghĩa, ai cần được thông báo khi hợp đồng thay đổi và ai chịu trách nhiệm giữ tính tương thích.

## 2. Phân biệt hướng gọi lúc chạy và hướng phụ thuộc khi biên dịch

Hai hướng này có thể khác nhau. Trong kiến trúc hướng phụ thuộc vào abstraction, một tầng cao gọi một interface, nhưng implementation cụ thể lại nằm ở tầng thấp hơn.

~~~mermaid
flowchart TB
    P[Presentation]
    A[Application: use case và port]
    D[Domain: quy tắc nghiệp vụ]
    I[Infrastructure: adapter và framework]
    P -->|phụ thuộc| A
    A -->|phụ thuộc| D
    I -->|implements port của| A
    I -->|dùng chi tiết kỹ thuật| DB[(Database / API ngoài)]
~~~

Các mũi tên thể hiện hướng phụ thuộc khi biên dịch: mã ở đầu mũi tên biết và sử dụng hợp đồng ở phía sau. Infrastructure phụ thuộc vào Application port để triển khai interface. Application không cần import lớp adapter.

Lúc chạy, luồng có thể đi theo hướng ngược lại ở ranh giới interface:

~~~mermaid
sequenceDiagram
    participant C as OrderController
    participant U as PlaceOrderUseCase
    participant S as PlaceOrderService
    participant R as OrderRepository port
    participant A as JpaOrderRepositoryAdapter
    participant DB as Database
    C->>U: execute(command)
    U->>S: gọi implementation use case
    S->>R: save(order)
    Note over R,A: Spring inject adapter triển khai port
    R->>A: lời gọi interface được dispatch
    A->>DB: ghi dữ liệu
    DB-->>A: kết quả
    A-->>S: hoàn tất
    S-->>C: kết quả use case
~~~

Dependency injection giúp kết nối interface với implementation lúc khởi động. Việc Application gọi một phương thức interface không có nghĩa Application phải phụ thuộc vào lớp cụ thể thực hiện phương thức đó.

Phân biệt hai hướng này giúp tránh nhầm lẫn khi đọc sơ đồ: hướng điều khiển (control flow) mô tả thành phần nào gọi thành phần nào khi chạy; hướng phụ thuộc (source/code dependency) mô tả mã nguồn cần biết định nghĩa nào để biên dịch. Kiến trúc phân tầng thường quan tâm đặc biệt tới hướng phụ thuộc để chi tiết thay đổi ít lan lên tầng nghiệp vụ.

## 3. Quy tắc xác định chủ sở hữu: ai cần hợp đồng và hợp đồng nói về điều gì?

Khi đặt một hợp đồng, hãy lần lượt trả lời:

1. **Ai là bên tiêu thụ?** Thành phần nào cần gọi thao tác hoặc đọc kiểu dữ liệu này?
2. **Hợp đồng diễn đạt ngữ nghĩa của ai?** Nó mô tả ca sử dụng, quy tắc miền, giao thức HTTP hay cách truy cập một công nghệ?
3. **Ai cần có quyền thay đổi nó?** Bên nào hiểu rõ nhất nhu cầu và có trách nhiệm giữ các caller hoạt động?
4. **Ai triển khai?** Thành phần nào có thể cung cấp cách thực hiện mà không làm rò chi tiết của nó qua hợp đồng?

Với một outbound port do Application cần, Application thường sở hữu hợp đồng vì Application định nghĩa mục đích và kết quả cần có. Infrastructure sở hữu adapter cụ thể. Với một API công khai do dịch vụ cung cấp cho nhiều client, nhà cung cấp API chịu trách nhiệm công bố và duy trì schema tương thích; các client là bên tiêu thụ. Vì thế, không nên biến “consumer sở hữu hợp đồng” thành quy tắc cứng cho mọi loại giao tiếp. Cần xét ranh giới và quyền quyết định ngữ nghĩa.

Một cách ghi nhớ thực tế:

| Loại hợp đồng | Nơi thường sở hữu | Lý do |
|---|---|---|
| Use case input/output và application port | Application | Mô tả điều ca sử dụng cần và cung cấp |
| Quy tắc, value object hoặc interface gắn chặt với mô hình miền | Domain | Là một phần ngôn ngữ và chính sách của miền |
| HTTP request/response DTO, view model | Presentation | Phản ánh giao thức hoặc nhu cầu hiển thị |
| JPA entity, Spring Data repository, SQL row mapping | Infrastructure | Phản ánh công nghệ và schema lưu trữ |
| Public API schema do dịch vụ công bố | Dịch vụ cung cấp API | Dịch vụ chịu trách nhiệm hợp đồng tương thích với client |
| Message/event schema liên tổ chức | Bên sở hữu capability hoặc nhóm quản trị event contract đã thống nhất | Cần một đầu mối chịu trách nhiệm phiên bản và tương thích giữa producer/consumer |

## 4. Ví dụ: Application sở hữu outbound port, Infrastructure triển khai

Giả sử use case đặt hàng cần tính phí thanh toán. Application cần một khả năng nghiệp vụ ở mức “ủy quyền thanh toán”, nhưng không cần biết nhà cung cấp dùng REST, SDK hay một hệ thống giả lập.

Đặt port và kiểu dữ liệu mà nó hiểu trong Application:

~~~java
package com.example.shop.application.port;

import java.math.BigDecimal;
import java.util.UUID;

public record PaymentRequest(
        UUID orderId,
        BigDecimal amount,
        String currency
) {}

public record PaymentAuthorization(
        String transactionId,
        boolean approved
) {}

public interface PaymentGateway {
    PaymentAuthorization authorize(PaymentRequest request);
}
~~~

Use case phụ thuộc vào port:

~~~java
package com.example.shop.application;

import com.example.shop.application.port.PaymentGateway;
import com.example.shop.application.port.PaymentRequest;

public class ConfirmOrderService {
    private final PaymentGateway paymentGateway;
    private final OrderRepository orders;

    public ConfirmOrderService(
            PaymentGateway paymentGateway,
            OrderRepository orders) {
        this.paymentGateway = paymentGateway;
        this.orders = orders;
    }

    public void confirm(OrderId id) {
        Order order = orders.findById(id)
                .orElseThrow(OrderNotFoundException::new);

        var authorization = paymentGateway.authorize(
                new PaymentRequest(
                        order.getId().value(),
                        order.total(),
                        order.currency()
                )
        );

        if (!authorization.approved()) {
            throw new PaymentRejectedException();
        }

        order.confirm(authorization.transactionId());
        orders.save(order);
    }
}
~~~

Infrastructure triển khai port bằng một nhà cung cấp cụ thể:

~~~java
package com.example.shop.infrastructure.payment;

@Component
public class HttpPaymentGatewayAdapter implements PaymentGateway {
    private final PaymentProviderClient client;

    public HttpPaymentGatewayAdapter(PaymentProviderClient client) {
        this.client = client;
    }

    @Override
    public PaymentAuthorization authorize(PaymentRequest request) {
        ProviderChargeRequest providerRequest =
                new ProviderChargeRequest(
                        request.orderId().toString(),
                        request.amount(),
                        request.currency()
                );

        ProviderChargeResponse response =
                client.charge(providerRequest);

        return new PaymentAuthorization(
                response.transactionReference(),
                response.isSuccessful()
        );
    }
}
~~~

Các kiểu ProviderChargeRequest, ProviderChargeResponse và PaymentProviderClient thuộc adapter Infrastructure. Chúng phản ánh API của nhà cung cấp và không nên xuất hiện trong hợp đồng Application. Khi đổi nhà cung cấp, adapter có thể thay đổi cách ánh xạ mà không buộc use case import SDK hoặc kiểu dữ liệu của đối tác.

Ví dụ đã lược bỏ phần xử lý lỗi mạng, timeout, retry và idempotency. Trong hệ thống thật, cần xác định rõ các hành vi đó ở hợp đồng và chính sách của Application/Infrastructure. Ví dụ cũng không hàm ý việc thanh toán và lưu đơn hàng có thể luôn nằm trong cùng một database transaction; tích hợp thanh toán bên ngoài cần thiết kế trạng thái và phục hồi riêng.

## 5. Đặt hợp đồng repository trong Domain hay Application?

Câu trả lời phụ thuộc vào ý nghĩa của interface.

Nếu repository là một phần cách Domain làm việc với aggregate và ngôn ngữ miền, có thể đặt interface trong Domain:

~~~java
package com.example.shop.domain.order;

public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void save(Order order);
}
~~~

Domain hoặc Application có thể dùng hợp đồng đó, còn Infrastructure triển khai bằng JPA. Đây là lựa chọn phù hợp khi hợp đồng gắn chặt với vòng đời aggregate, định danh miền và cách lưu/khôi phục đối tượng miền.

Nếu một cổng chỉ phục vụ riêng ca sử dụng Application, chẳng hạn truy vấn báo cáo theo nhiều bộ lọc và trả một projection dành cho màn hình, đặt interface trong Application thường tự nhiên hơn:

~~~java
package com.example.shop.application.orderhistory;

public interface SearchOrderHistory {
    OrderHistoryPage search(OrderHistoryFilter filter);
}
~~~

OrderHistoryPage và OrderHistoryFilter khi đó là kiểu dữ liệu thuộc hợp đồng của use case. Infrastructure có thể dùng SQL hoặc Spring Data projection để cung cấp kết quả.

Không cần chuyển tất cả repository vào Domain hoặc tất cả vào Application theo một quy tắc máy móc. Hãy đặt interface gần ngữ nghĩa mà nó phục vụ, đồng thời giữ cho Domain không phụ thuộc Application, Infrastructure hay framework.

## 6. Hợp đồng dữ liệu ở từng ranh giới: đừng dùng một DTO cho mọi tầng

Một lỗi phổ biến là tạo một lớp OrderDto dùng từ controller qua application, domain và persistence. Lúc đầu điều đó có vẻ tiết kiệm mapping, nhưng các tầng có nhu cầu khác nhau:

- Presentation cần định dạng giao thức, tên trường JSON, validation và cấu trúc phản hồi.
- Application cần command/query diễn đạt ý định của ca sử dụng và output phục vụ bên gọi.
- Domain cần entity, value object và quy tắc có ý nghĩa nghiệp vụ.
- Infrastructure cần entity lưu trữ, projection và kiểu dữ liệu do thư viện kỹ thuật yêu cầu.

Ví dụ, request HTTP có thể chứa productId và quantity. Application command còn có thể cần customerId lấy từ principal đã xác thực. Domain có thể biểu diễn ProductId, Quantity và Money bằng value object. Entity JPA có thể dùng UUID, decimal và các cột quan hệ. Những kiểu này không nhất thiết phải giống nhau.

~~~mermaid
flowchart LR
    H[HTTP JSON]
    P[Presentation DTO]
    A[Application Command / Result]
    D[Domain Model]
    I[Persistence Entity]
    H -->|parse và validate| P
    P -->|map| A
    A -->|thực thi quy tắc| D
    D -->|adapter mapping| I
~~~

Chuyển đổi dữ liệu ở ranh giới có chi phí, nhưng nó làm rõ ai chịu trách nhiệm với cấu trúc đó. Không cần tạo mapper riêng cho một phép đổi đơn giản chỉ có một nơi dùng; điều quan trọng là không để kiểu của một tầng vô tình trở thành hợp đồng bắt buộc của tất cả tầng khác.

Ví dụ, Presentation định nghĩa request DTO:

~~~java
package com.example.shop.presentation.http;

public record PlaceOrderRequest(
        UUID productId,
        int quantity
) {}
~~~

Application định nghĩa command:

~~~java
package com.example.shop.application.order;

public record PlaceOrderCommand(
        CustomerId customerId,
        ProductId productId,
        Quantity quantity
) {}
~~~

Controller chuyển DTO thành command:

~~~java
@PostMapping("/orders")
public ResponseEntity<OrderResponse> place(
        @Valid @RequestBody PlaceOrderRequest request,
        @AuthenticationPrincipal AppPrincipal principal) {

    var command = new PlaceOrderCommand(
            new CustomerId(principal.customerId()),
            new ProductId(request.productId()),
            new Quantity(request.quantity())
    );

    var result = placeOrder.execute(command);
    return ResponseEntity.created(
            URI.create("/orders/" + result.orderId())
    ).body(OrderResponse.from(result));
}
~~~

Application không cần import PlaceOrderRequest, ResponseEntity hay AppPrincipal. Nếu giao thức thay đổi từ REST sang message consumer, adapter đầu vào mới có thể tạo cùng command để gọi use case.

## 7. Tránh phụ thuộc ngược qua package và module

Cấu trúc package nên giúp người đọc nhận ra hợp đồng thuộc tầng nào:

~~~text
com.example.shop
├── presentation
│   └── http
│       ├── OrderController.java
│       ├── PlaceOrderRequest.java
│       └── OrderResponse.java
├── application
│   ├── order
│   │   ├── PlaceOrderCommand.java
│   │   ├── PlaceOrderUseCase.java
│   │   └── PlaceOrderService.java
│   └── port
│       └── PaymentGateway.java
├── domain
│   └── order
│       ├── Order.java
│       ├── OrderId.java
│       └── OrderRepository.java
└── infrastructure
    ├── persistence
    │   └── JpaOrderRepositoryAdapter.java
    └── payment
        └── HttpPaymentGatewayAdapter.java
~~~

Hướng phụ thuộc có thể được kiểm soát bằng quy ước package, module Java hoặc công cụ kiểm tra kiến trúc. Nếu chia thành module build riêng, có thể đặt quan hệ như sau:

- presentation phụ thuộc application để gọi use case.
- application phụ thuộc domain và các kiểu hợp đồng do Application sở hữu.
- infrastructure phụ thuộc application/domain để triển khai các port.
- domain không phụ thuộc presentation, application hay infrastructure.

Một dự án không nhất thiết phải tách thành nhiều Gradle/Maven module ngay từ đầu. Package và quy tắc review cũng có thể tạo ranh giới đủ rõ. Khi hệ thống lớn hơn hoặc nhiều nhóm cùng phát triển, module build riêng và kiểm tra dependency tự động giúp ngăn vi phạm sớm hơn.

Tránh tạo một package common hoặc shared chứa mọi DTO, entity, enum và interface chỉ vì nhiều tầng cùng cần import. Một module dùng chung không có chủ sở hữu rõ ràng thường trở thành nơi tập trung phụ thuộc, khiến thay đổi nhỏ buộc nhiều thành phần cập nhật. Chỉ chia sẻ một kiểu khi các bên thực sự đồng thuận cùng một ngữ nghĩa và có cơ chế quản lý thay đổi.

## 8. Khi nào hợp đồng thuộc nhà cung cấp thay vì bên tiêu thụ?

Với các cổng outbound bên trong ứng dụng, bên tiêu thụ thường định nghĩa abstraction vì nó quyết định khả năng cần có. Nhưng ở một số ranh giới, hợp đồng được công bố bởi bên cung cấp.

Ví dụ, một dịch vụ quản lý khách hàng công bố REST API GET /customers/{id}. Dịch vụ đó sở hữu public API schema và chịu trách nhiệm thông báo, quản lý phiên bản và duy trì tương thích với các client. Client không nên tự thay đổi schema của dịch vụ. Thay vào đó, client có thể tạo adapter hoặc client interface riêng để ánh xạ API công khai sang mô hình mà use case nội bộ cần.

Với event do một hệ thống phát ra, producer thường công bố schema và ý nghĩa event. Nhưng nếu event được chia sẻ giữa nhiều miền hoặc nhiều nhóm, cần thống nhất một chủ sở hữu capability/schema registry và quy tắc versioning. Không nên để một thư viện shared-events tự phát triển không kiểm soát mà không có nhóm chịu trách nhiệm.

Có thể phân biệt:

| Tình huống | Ai định nghĩa hợp đồng? | Ai thích nghi? |
|---|---|---|
| Application gọi cổng thanh toán bên ngoài | Application định nghĩa port theo nhu cầu use case | Infrastructure adapter ánh xạ sang API nhà cung cấp |
| Controller nhận request REST do ứng dụng cung cấp | Presentation/API của ứng dụng định nghĩa request schema công khai | Client bên ngoài thích nghi theo API |
| Ứng dụng gọi dịch vụ đối tác đã có API | Đối tác sở hữu API công khai | Adapter phía ứng dụng ánh xạ API đối tác sang port nội bộ |
| Các hệ thống trao đổi event | Chủ sở hữu event/capability được các bên thống nhất | Producer và consumer tuân theo schema/version đã công bố |

Quy tắc không phải “luôn đặt interface ở bên gọi” hay “luôn đặt interface ở bên cung cấp”. Quy tắc là xác định ai có quyền và trách nhiệm với ngữ nghĩa của hợp đồng, rồi đặt abstraction ở ranh giới phù hợp để chi tiết triển khai không lan qua các tầng.

## 9. Thay đổi hợp đồng và duy trì tương thích

Khi một hợp đồng được nhiều thành phần sử dụng, sửa nó có thể ảnh hưởng nhiều nơi. Trước khi thay đổi, cần xác định:

- Thay đổi có phá vỡ caller hiện tại không?
- Có thể bổ sung trường hoặc phương thức theo cách tương thích không?
- Giá trị mặc định và ý nghĩa khi thiếu trường là gì?
- Các adapter và test nào phải cập nhật cùng lúc?
- Nếu là API/event công khai, cần phiên bản mới, giai đoạn chuyển tiếp hay thời hạn ngừng hỗ trợ không?

Với interface nội bộ, thêm một phương thức trừu tượng có thể làm hỏng mọi implementation. Có thể cập nhật đồng bộ các adapter trong cùng một thay đổi, hoặc thiết kế một interface mới nếu hai nhóm caller có nhu cầu khác nhau. Không nên thêm method mặc định chỉ để che việc semantics chưa rõ.

Với API bên ngoài, cần thận trọng hơn. Xóa trường, đổi kiểu dữ liệu hoặc đổi ý nghĩa status có thể phá vỡ client đã triển khai. Có thể thêm trường tùy chọn, công bố phiên bản mới hoặc hỗ trợ song song trong một giai đoạn. Với event, thay đổi schema cần xét cả consumer cũ đang xử lý message đã phát ra trước đó.

Hợp đồng ổn định không có nghĩa là không bao giờ thay đổi. Nó có nghĩa là thay đổi có chủ đích, có người chịu trách nhiệm và có cách quản lý ảnh hưởng.

## 10. Kiểm thử để phát hiện phụ thuộc sai hướng

Một số kiểm tra giúp xác minh quyền sở hữu hợp đồng:

- **Application unit test:** thay adapter bằng fake/mock để kiểm tra use case chỉ phụ thuộc port.
- **Adapter integration test:** kiểm tra implementation thực hiện đúng hợp đồng khi kết nối database hoặc API ngoài.
- **Contract test:** chạy chung một bộ kiểm thử cho nhiều implementation của cùng port hoặc xác minh client tương thích với API/event schema.
- **Architecture test:** kiểm tra package/module không import tầng bị cấm, ví dụ Domain không phụ thuộc Spring, JPA hay Presentation.

Ví dụ kiểm tra quy tắc package bằng ArchUnit:

~~~java
@AnalyzeClasses(packages = "com.example.shop")
class LayerDependencyTest {

    @ArchTest
    static final ArchRule domainMustNotDependOnInfrastructure =
            noClasses()
                    .that().resideInAPackage("..domain..")
                    .should().dependOnClassesThat()
                    .resideInAPackage("..infrastructure..");

    @ArchTest
    static final ArchRule domainMustNotDependOnPresentation =
            noClasses()
                    .that().resideInAPackage("..domain..")
                    .should().dependOnClassesThat()
                    .resideInAPackage("..presentation..");
}
~~~

Có thể bổ sung quy tắc Application không phụ thuộc Infrastructure hoặc Presentation, tùy cấu trúc module. Những test này không chứng minh toàn bộ kiến trúc đúng, nhưng phát hiện sớm một số import làm đảo hướng phụ thuộc.

## 11. Checklist xác định nơi sở hữu hợp đồng

Trước khi thêm interface hoặc DTO mới, hãy tự kiểm tra:

1. Hợp đồng đang diễn đạt ngữ nghĩa của ca sử dụng, miền nghiệp vụ, giao thức hay công nghệ?
2. Thành phần nào cần nó và thành phần nào có quyền quyết định cách nó thay đổi?
3. Interface có làm lộ framework, schema database hoặc API riêng của đối tác không?
4. Kiểu dữ liệu có thuộc đúng ranh giới hay đang được dùng chung chỉ để tránh mapping?
5. Implementation có thể phụ thuộc vào interface mà không khiến tầng cao import lớp cụ thể không?
6. Nếu hợp đồng thay đổi, ai cần được thông báo và cách giữ tương thích là gì?
7. Có thể kiểm tra hướng phụ thuộc bằng module boundary hoặc architecture test không?

Xác định đúng chủ sở hữu hợp đồng giúp mỗi tầng nói bằng ngôn ngữ phù hợp với trách nhiệm của nó. Presentation sở hữu hợp đồng giao tiếp, Application sở hữu những port phục vụ ca sử dụng, Domain giữ mô hình và quy tắc miền, còn Infrastructure cung cấp implementation và ánh xạ công nghệ. Khi hướng phụ thuộc được giữ rõ ràng, thay đổi ở framework, database hoặc giao thức bên ngoài ít buộc tầng nghiệp vụ phải thay đổi theo.


# Chia thư mục thành ba nhóm nhưng vẫn phụ thuộc chéo

Một dự án có thể có ba thư mục mang tên Controller, Model và View nhưng vẫn không có kiến trúc MVC rõ ràng. Tên thư mục chỉ cho biết nơi đặt file; chúng không tự xác định ai được phép gọi ai, dữ liệu đi qua ranh giới nào hoặc quy tắc nghiệp vụ thuộc về đâu.

Ví dụ, Controller gọi trực tiếp Repository, View gọi Service để tự tải dữ liệu, còn Model lại import HttpServletRequest hoặc một lớp tiện ích nằm trong Controller. Các thành phần đã được chia thành ba nhóm trên cây thư mục, nhưng trách nhiệm vẫn đan xen. Khi sửa một màn hình, lập trình viên phải lần theo nhiều package; khi đổi giao thức HTTP hoặc persistence, thay đổi lan sang phần nghiệp vụ.

Vấn đề cốt lõi là **tách file theo tên vai trò nhưng không tách phụ thuộc theo trách nhiệm**. Muốn MVC có ích, cần xác định ranh giới và hướng phụ thuộc, sau đó tổ chức package để làm cho các quy tắc đó dễ nhìn, dễ kiểm tra và khó vi phạm.

## 1. Chia thư mục không đồng nghĩa với phân tách kiến trúc

Một cấu trúc thường gặp:

~~~text
src/main/java/com/example/shop/
  controller/
  model/
  view/
~~~

Cấu trúc này có thể phù hợp với ứng dụng nhỏ nếu mỗi nhóm có trách nhiệm rõ. Nhưng nó không tự trả lời những câu hỏi quan trọng:

- Controller được phép truy cập Repository trực tiếp không?
- Model là domain model, DTO, service hay toàn bộ các lớp dữ liệu?
- View chỉ hiển thị dữ liệu hay tự gọi API/Service?
- Domain có phụ thuộc vào Servlet, Spring MVC hoặc template engine không?
- Nhiều Controller có dùng chung một quy tắc nghiệp vụ không?
- Khi đổi database hoặc chuyển từ HTML sang JSON, những lớp nào phải thay đổi?

Nếu không có câu trả lời, package chỉ là cách xếp file.

### 1.1. MVC là phân chia trách nhiệm, không phải công thức đặt tên thư mục

MVC mô tả vai trò:

- **Model:** trạng thái, dữ liệu và quy tắc mà ứng dụng cần quản lý hoặc biểu diễn. Tùy biến thể, phần Model có thể bao gồm domain model và dữ liệu trình bày.
- **View:** hiển thị dữ liệu và cung cấp giao diện tương tác.
- **Controller:** tiếp nhận request hoặc thao tác, điều phối xử lý và chọn phản hồi.

MVC không yêu cầu mọi ứng dụng phải có đúng ba package cấp cao tên controller, model, view. Một ứng dụng có thể tổ chức theo tính năng, module hoặc lớp kiến trúc, miễn là trách nhiệm và hướng phụ thuộc vẫn rõ ràng.

### 1.2. Phân biệt vị trí file và quyền phụ thuộc

Hai lớp nằm ở hai thư mục khác nhau vẫn có thể phụ thuộc chặt chẽ. Ngược lại, hai lớp ở cùng package có thể có trách nhiệm riêng nhưng không cần tạo ranh giới module.

Cần phân biệt:

- **Vị trí:** file được đặt ở đâu.
- **Trách nhiệm:** lớp chịu trách nhiệm cho quyết định nào.
- **Phụ thuộc:** lớp cần biết hoặc gọi lớp nào để hoàn thành công việc.
- **Ranh giới:** phần nào được phép biết chi tiết của phần nào.
- **Hợp đồng:** dữ liệu và hành vi được công bố qua ranh giới.

Cấu trúc thư mục chỉ hỗ trợ thể hiện các quyết định này. Nó không thay thế các quyết định đó.

## 2. Dấu hiệu ba nhóm MVC vẫn phụ thuộc chéo

### 2.1. Controller truy cập Repository và xử lý nghiệp vụ

Ví dụ:

~~~java
@Controller
@RequestMapping("/orders")
public class OrderController {

    private final OrderRepository repository;

    @PostMapping("/{id}/cancel")
    public String cancel(@PathVariable UUID id) {
        Order order = repository.findById(id).orElseThrow();

        if (order.getStatus() == OrderStatus.SHIPPED) {
            throw new IllegalStateException("Cannot cancel");
        }

        order.setStatus(OrderStatus.CANCELLED);
        repository.save(order);

        return "redirect:/orders/" + id;
    }
}
~~~

Controller vừa xử lý HTTP, vừa truy vấn persistence, vừa quyết định quy tắc hủy đơn, vừa thay đổi trạng thái. Nếu REST endpoint, tác vụ nền hoặc message handler cũng cần hủy đơn, quy tắc có thể bị sao chép.

Controller nên chuyển yêu cầu thành command và gọi application service. Service điều phối ca sử dụng; domain model bảo vệ quy tắc trạng thái; repository được truy cập qua ranh giới phù hợp.

### 2.2. View tự truy cập Model hoặc Service

Ví dụ một template có helper truy vấn database, hoặc một View component tự gọi OrderService để tải danh sách.

Hậu quả:

- View không còn chỉ trình bày dữ liệu được cung cấp.
- Khó biết request nào tạo ra truy vấn nào.
- Một lần render có thể kích hoạt nhiều truy vấn ẩn.
- Test template phải khởi tạo thêm dịch vụ và persistence.
- Logic tải dữ liệu bị lặp giữa nhiều View.

View nên nhận Model/ViewModel đã được chuẩn bị. Nếu giao diện client cần tải thêm dữ liệu, nó gọi một API qua lớp client adapter hoặc ViewModel; không truy cập trực tiếp repository nội bộ của backend.

### 2.3. Model phụ thuộc vào Controller hoặc HTTP

Một lớp nghiệp vụ nhận HttpServletRequest, ResponseEntity, Model của Spring MVC hoặc tên template là dấu hiệu ranh giới đã bị đảo.

Ví dụ:

~~~java
public class OrderService {

    public String cancel(
            UUID orderId,
            HttpServletRequest request) {
        // Đọc session, sửa đơn hàng và quyết định redirect
        return "redirect:/orders/" + orderId;
    }
}
~~~

Service giờ phụ thuộc vào giao thức web. Nếu cùng use case được gọi từ job hoặc message listener, nó phải tạo request giả hoặc thêm nhánh đặc biệt.

Application service nên nhận dữ liệu có ý nghĩa với ca sử dụng như OrderId, UserId và CancelReason. HTTP adapter chịu trách nhiệm đọc request, lấy danh tính đã xác thực và quyết định redirect.

### 2.4. Package tiện ích trở thành điểm nối mọi thứ

Các lớp như CommonUtil, AppHelper, GlobalContext hoặc BaseController có thể dần chứa:

- Truy cập session.
- Lấy user hiện tại.
- Định dạng dữ liệu.
- Truy vấn repository.
- Chuyển đổi Entity.
- Tạo thông báo.
- Điều hướng View.

Khi mọi package đều import cùng một tiện ích, package đó trở thành điểm kết nối ngầm và khó kiểm soát. Hãy chia tiện ích theo năng lực cụ thể, đặt chúng ở tầng có trách nhiệm và truyền dependency qua constructor hoặc hợp đồng rõ ràng.

### 2.5. Vòng phụ thuộc giữa package

Một vòng phụ thuộc có thể xuất hiện như sau:

~~~mermaid
flowchart LR
    C[controller] --> M[model]
    M --> V[view]
    V --> C
~~~

Ví dụ:

- Controller gọi Model để lấy dữ liệu.
- Model gọi View formatter để tạo chuỗi hiển thị.
- View formatter gọi Controller helper để lấy người dùng hiện tại.

Mỗi package đều có vẻ “hợp lý” khi đứng riêng, nhưng không package nào có thể thay đổi độc lập. Một thay đổi nhỏ có thể yêu cầu biên dịch, kiểm thử và hiểu cả ba nhóm.

Không phải mọi phụ thuộc giữa các package đều sai. Controller phụ thuộc vào application service là bình thường. Vấn đề là phụ thuộc đi ngược trách nhiệm, tạo chu trình hoặc làm lõi nghiệp vụ biết chi tiết trình bày/hạ tầng.

## 3. Hướng phụ thuộc nên được xác định trước

Một cách tổ chức phổ biến cho ứng dụng web là:

~~~mermaid
flowchart TB
    Web[Web Adapter: Controller, Request/Response DTO, View]
    App[Application: Use Cases, Commands, Queries]
    Domain[Domain: Entity nghiệp vụ, Value Object, Policy]
    Ports[Ports: Repository, External Service]
    Infra[Infrastructure: JPA, HTTP Client, Message Adapter]

    Web --> App
    App --> Domain
    App --> Ports
    Infra -. implements .-> Ports
~~~

Ý nghĩa:

- Web adapter phụ thuộc vào hợp đồng application để gọi ca sử dụng.
- Application điều phối ca sử dụng và sử dụng domain.
- Application/domain định nghĩa những khả năng cần từ hạ tầng qua port khi phù hợp.
- Infrastructure triển khai các port bằng database, HTTP client hoặc message broker.
- Domain không cần biết Controller, template engine hoặc JPA adapter cụ thể.

Đây là hướng phụ thuộc thường dùng trong kiến trúc phân lớp hoặc Ports and Adapters. Dự án nhỏ có thể không cần tạo đủ mọi package, nhưng vẫn nên giữ nguyên nguyên tắc: chi tiết giao tiếp và lưu trữ không điều khiển quy tắc nghiệp vụ.

### 3.1. Controller gọi application service, không điều khiển toàn bộ Model

Luồng thường gặp:

1. Controller nhận request.
2. Controller bind và validate cấu trúc đầu vào.
3. Controller lấy danh tính người dùng từ security context.
4. Mapper chuyển request DTO thành command/query.
5. Application service thực thi ca sử dụng.
6. Domain kiểm tra bất biến và chuyển trạng thái.
7. Repository port được dùng để đọc/ghi dữ liệu.
8. Controller chuyển kết quả thành ViewModel hoặc response DTO.
9. View hoặc message converter tạo response.

Controller có thể kiểm tra điều kiện ở cấp HTTP như thiếu tham số hoặc sai định dạng. Các quy tắc nghiệp vụ như “đơn đã giao không thể hủy” phải được bảo vệ ở application/domain để mọi adapter đều tuân thủ.

### 3.2. View phụ thuộc vào hợp đồng trình bày

View nên biết tên và kiểu dữ liệu được cung cấp cho nó, chẳng hạn OrderDetailView. View không nên biết:

- EntityManager hoặc Repository.
- Cấu trúc bảng.
- Quy tắc transaction.
- Cách gọi dịch vụ thanh toán.
- Chi tiết session hoặc SecurityContext.
- Cách application service triển khai.

Nếu View cần dữ liệu mới, Controller hoặc ViewModel điều phối việc lấy dữ liệu qua hợp đồng thích hợp. Template chỉ render kết quả.

## 4. Một ví dụ tổ chức sai và cách sửa

### 4.1. Cấu trúc dễ tạo coupling

~~~text
com.example.shop
  controller/
    OrderController.java
    CustomerController.java
  model/
    Order.java
    Customer.java
    OrderRepository.java
    OrderService.java
    OrderValidator.java
  view/
    OrderFormatter.java
    CurrentUserHelper.java
    templates/
      orders/
~~~

Cấu trúc này có thể vẫn chạy, nhưng package model đang trộn Entity, Repository, Service và Validator. Package view lại có helper truy cập user/session. Theo thời gian, các lớp sẽ import chéo để bù cho ranh giới chưa rõ.

### 4.2. Cấu trúc theo lớp trách nhiệm

~~~text
com.example.shop
  web/
    order/
      OrderController.java
      CreateOrderRequest.java
      OrderResponse.java
      OrderHttpMapper.java
    view/
      OrderPageController.java
      OrderPageView.java
      OrderPageMapper.java
      templates/
        orders/
  application/
    order/
      CreateOrderUseCase.java
      CancelOrderUseCase.java
      CreateOrderCommand.java
      CancelOrderCommand.java
  domain/
    order/
      Order.java
      OrderId.java
      OrderStatus.java
      OrderRepository.java
  infrastructure/
    persistence/
      JpaOrderRepository.java
      OrderJpaEntity.java
      OrderPersistenceMapper.java
~~~

Trong ví dụ này:

- web xử lý giao thức, binding, View và mapping.
- application điều phối ca sử dụng.
- domain giữ quy tắc và kiểu dữ liệu nghiệp vụ.
- infrastructure triển khai lưu trữ.

Tên và số package có thể thay đổi theo framework. Điều quan trọng là mỗi lớp có lý do tồn tại và phụ thuộc đi theo hướng đã chọn.

### 4.3. Controller sau khi tách trách nhiệm

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final CancelOrderUseCase cancelOrder;
    private final CurrentUserProvider currentUser;

    public OrderController(
            CancelOrderUseCase cancelOrder,
            CurrentUserProvider currentUser) {
        this.cancelOrder = cancelOrder;
        this.currentUser = currentUser;
    }

    @PostMapping("/{id}/cancel")
    public ResponseEntity<Void> cancel(
            @PathVariable UUID id,
            @Valid @RequestBody CancelOrderRequest request) {

        UserId actorId = currentUser.requireUserId();

        cancelOrder.handle(new CancelOrderCommand(
            new OrderId(id),
            actorId,
            request.reason()
        ));

        return ResponseEntity.noContent().build();
    }
}
~~~

Controller chỉ chuyển request thành command và chọn response. Nó không biết repository dùng JPA hay SQL, cũng không tự thay đổi trạng thái Order.

### 4.4. Application service điều phối use case

~~~java
public class CancelOrderService implements CancelOrderUseCase {

    private final OrderRepository orders;
    private final OrderAccessPolicy accessPolicy;

    public CancelOrderService(
            OrderRepository orders,
            OrderAccessPolicy accessPolicy) {
        this.orders = orders;
        this.accessPolicy = accessPolicy;
    }

    @Override
    public void handle(CancelOrderCommand command) {
        Order order = orders.findById(command.orderId())
            .orElseThrow(() ->
                new OrderNotFoundException(command.orderId())
            );

        accessPolicy.requireCanCancel(command.actorId(), order);
        order.cancel(command.reason());
        orders.save(order);
    }
}
~~~

Service tải aggregate, kiểm tra quyền qua policy và gọi hành vi domain. Transaction có thể được đặt ở application boundary theo cơ chế của dự án. Repository interface là hợp đồng mà application/domain sử dụng; implementation cụ thể nằm ở infrastructure.

### 4.5. Domain bảo vệ bất biến

~~~java
public class Order {

    private OrderStatus status;

    public void cancel(String reason) {
        if (status == OrderStatus.SHIPPED
                || status == OrderStatus.DELIVERED) {
            throw new OrderCannotBeCancelledException(status);
        }

        if (reason == null || reason.isBlank()) {
            throw new InvalidCancellationReasonException();
        }

        status = OrderStatus.CANCELLED;
    }
}
~~~

Ví dụ này minh họa quy tắc chuyển trạng thái. Domain không trả về redirect, không biết HTTP status và không phụ thuộc Controller. Cả HTML Controller, REST Controller hay message handler đều phải đi qua cùng use case/domain behavior.

## 5. Tổ chức theo layer hay theo feature?

Có hai cách phổ biến, và không có cách nào đúng cho mọi quy mô.

### 5.1. Package-by-layer

~~~text
com.example.shop
  controller/
  application/
  domain/
  infrastructure/
  view/
~~~

Ưu điểm:

- Dễ nhận biết lớp kiến trúc.
- Phù hợp dự án nhỏ hoặc nhóm ít người.
- Có thể áp dụng quy tắc phụ thuộc tổng quát.

Nhược điểm:

- Một tính năng phải sửa nhiều thư mục xa nhau.
- Package controller hoặc service có thể phình lớn.
- Khó xác định một module nghiệp vụ sở hữu những gì.
- Các lớp của nhiều tính năng dễ phụ thuộc lẫn nhau qua package chung.

### 5.2. Package-by-feature

~~~text
com.example.shop
  order/
    web/
    application/
    domain/
    infrastructure/
  customer/
    web/
    application/
    domain/
    infrastructure/
  inventory/
    web/
    application/
    domain/
    infrastructure/
~~~

Ưu điểm:

- Các lớp cùng phục vụ một năng lực nghiệp vụ nằm gần nhau.
- Dễ xác định module sở hữu use case và dữ liệu.
- Có thể giới hạn API công khai giữa các feature.
- Dễ tách module khi ứng dụng phát triển.

Nhược điểm:

- Có thể lặp lại một số package con.
- Nếu không có quy tắc phụ thuộc, feature vẫn có thể gọi xuyên sâu vào nhau.
- Dễ tạo lớp shared/common quá lớn để tránh lặp.

### 5.3. Kết hợp layer và feature

Một lựa chọn thường cân bằng:

~~~text
com.example.shop
  order/
    api/
    application/
    domain/
    infrastructure/
  customer/
    api/
    application/
    domain/
    infrastructure/
  shared/
    kernel/
  bootstrap/
~~~

Ở đây mỗi feature giữ các lớp liên quan, còn shared chỉ chứa những abstraction thật sự dùng chung và ổn định. Không đưa mọi thứ khó phân loại vào shared.

Dù chọn package-by-layer hay package-by-feature, cần định nghĩa rõ public API của module và hướng phụ thuộc giữa chúng.

## 6. Phân biệt Model, Domain Model và ViewModel

Một nguồn gây coupling là dùng từ Model cho quá nhiều loại dữ liệu.

| Loại | Mục đích | Có nên phụ thuộc vào View/HTTP? |
|---|---|---|
| Domain Model | Bảo vệ trạng thái và quy tắc nghiệp vụ | Không |
| Persistence Entity | Ánh xạ cấu trúc lưu trữ | Không nên phụ thuộc View; thường chỉ thuộc adapter persistence |
| Request DTO | Nhận dữ liệu từ client | Có thể phụ thuộc validation ở web boundary |
| Application Command/Query | Diễn đạt yêu cầu của ca sử dụng | Không phụ thuộc HTTP hoặc template |
| Response DTO | Công bố dữ liệu qua API | Thuộc adapter giao tiếp |
| ViewModel | Chuẩn bị dữ liệu cho một màn hình | Có thể chứa nhãn/trạng thái trình bày; không chứa persistence logic |

Không nhất thiết phải tạo tất cả các kiểu trên trong mọi ứng dụng. Hãy tách khi chúng có vòng đời, quyền sở hữu hoặc lý do thay đổi khác nhau.

### 6.1. Không dùng Entity làm hợp đồng cho View và API

Trả Entity trực tiếp dễ tạo các vấn đề:

- Làm lộ trường nội bộ.
- Serialization kéo theo quan hệ không mong muốn.
- Client phụ thuộc vào cấu trúc database.
- Thay đổi schema có thể làm hỏng API.
- View có thể kích hoạt lazy loading ngoài ý muốn.

Dùng DTO hoặc ViewModel phù hợp với ranh giới. Mapper chuyển đổi giữa các mô hình và giữ phần giao tiếp không làm rò cấu trúc persistence.

### 6.2. Không đưa dữ liệu trình bày vào Domain

Domain không nên lưu statusLabel, formattedTotal, isDialogOpen hoặc redirectUrl. Đây là dữ liệu dành cho giao diện hoặc giao thức.

Domain nên giữ trạng thái có ý nghĩa nghiệp vụ, ví dụ OrderStatus và Money. Lớp trình bày chuyển chúng thành nhãn, chuỗi định dạng hoặc cờ hiển thị.

## 7. Phụ thuộc chéo không chỉ là vòng import

Một dự án có thể không có vòng import trực tiếp nhưng vẫn coupling mạnh.

### 7.1. Phụ thuộc qua dữ liệu dùng chung

Nhiều package có thể cùng sửa một object mutable hoặc một bảng dữ liệu mà không có hợp đồng rõ. Thay đổi một trường làm nhiều thành phần phải cập nhật đồng thời.

Cần xác định owner của dữ liệu, quy tắc thay đổi và API được phép sử dụng. Với module nghiệp vụ, ưu tiên truy cập qua use case hoặc public interface thay vì sửa trực tiếp cấu trúc nội bộ.

### 7.2. Phụ thuộc qua global state

Static singleton, ThreadLocal, application context hoặc session helper toàn cục làm dependency khó nhìn thấy trong constructor. Một lớp có thể gọi bất kỳ service nào mà không thể hiện điều đó trong chữ ký.

Ưu tiên constructor injection và truyền dữ liệu cần thiết qua tham số. Global state chỉ nên được dùng khi có lý do hạ tầng rõ và có kiểm soát vòng đời.

### 7.3. Phụ thuộc qua tên và quy ước ngầm

Nếu Controller phải biết tên bảng, tên template nội bộ hoặc chuỗi trạng thái persistence để hoạt động, nó đang phụ thuộc vào chi tiết triển khai.

Dùng enum/value object và hợp đồng rõ ràng. Tên View có thể là một phần quyết định trình bày của web adapter, nhưng không nên được truyền ngược vào application/domain.

### 7.4. Phụ thuộc qua callback và event

Event có thể giảm phụ thuộc trực tiếp, nhưng không tự động làm kiến trúc lỏng. Nếu mọi module phát và nghe các event không có schema, version hoặc owner rõ ràng, coupling chỉ chuyển từ method call sang sự kiện.

Định nghĩa ai sở hữu event, thời điểm phát, semantics, khả năng lặp và xử lý lỗi. Dùng event khi cần tách thời gian hoặc thông báo thay đổi; không dùng chỉ để né một dependency đơn giản.

## 8. Quy tắc để giữ ranh giới rõ

Có thể ghi lại một số quy tắc ngắn trong tài liệu kiến trúc:

1. Controller chỉ phụ thuộc vào application API, mapper và các thành phần web cần thiết.
2. View chỉ nhận dữ liệu trình bày; không truy cập repository.
3. Application không phụ thuộc vào Controller, Servlet API hoặc template engine.
4. Domain không phụ thuộc framework web hoặc persistence adapter.
5. Infrastructure triển khai các port được application/domain định nghĩa.
6. Không trả persistence Entity trực tiếp qua HTTP hoặc View.
7. Không đặt quy tắc nghiệp vụ trong Controller, template hoặc binding.
8. Module khác chỉ truy cập public API, không import package nội bộ.
9. Tránh vòng phụ thuộc giữa package/module.
10. Dùng constructor injection để dependency hiển thị rõ trong mã nguồn.

Đây là quy tắc định hướng. Dự án có thể có ngoại lệ hợp lý, nhưng ngoại lệ cần có lý do và phạm vi cụ thể.

## 9. Kiểm soát phụ thuộc bằng công cụ

Review thủ công hữu ích nhưng không đủ khi số package tăng. Có thể dùng công cụ phân tích dependency hoặc architecture test để ngăn vi phạm quay trở lại.

### 9.1. ArchUnit kiểm tra domain không phụ thuộc web

Ví dụ với ArchUnit:

~~~java
@AnalyzeClasses(packages = "com.example.shop")
class ArchitectureRulesTest {

    @ArchTest
    static final ArchRule domain_must_not_depend_on_web =
        noClasses()
            .that().resideInAPackage("..domain..")
            .should().dependOnClassesThat()
            .resideInAnyPackage(
                "..web..",
                "jakarta.servlet..",
                "org.springframework.web.."
            );
}
~~~

Quy tắc này minh họa cách cấm domain phụ thuộc vào web. Cần điều chỉnh package pattern và import theo cấu trúc thật của dự án.

### 9.2. Kiểm tra package không tạo chu trình

Nếu dự án dùng package-by-feature, có thể kiểm tra các slice không phụ thuộc vòng:

~~~java
@ArchTest
static final ArchRule feature_packages_are_acyclic =
    slices()
        .matching("com.example.shop.(*)..")
        .should().beFreeOfCycles();
~~~

Quy tắc cần được áp dụng với pattern phù hợp. Nếu các package cấp cao gồm shared, bootstrap và feature, hãy xác định slice nào cần kiểm tra để không coi những package hạ tầng dùng chung hợp lệ là feature.

### 9.3. Kiểm tra dependency trong build

Với dự án nhiều module Gradle hoặc Maven, có thể tách domain/application thành module riêng. Build sẽ từ chối nếu module domain thêm dependency vào web adapter. Đây là cách mạnh hơn package convention vì dependency được kiểm soát ở cấp build.

Không cần chia thành nhiều build module quá sớm. Một package boundary cùng architecture test có thể đủ cho ứng dụng nhỏ; module build hữu ích khi nhiều nhóm hoặc nhiều tính năng cần quyền sở hữu độc lập.

## 10. Refactor từng bước khi đã có coupling chéo

Không nên di chuyển hàng loạt file chỉ để tạo cây thư mục đẹp. Hãy bắt đầu từ một luồng nghiệp vụ cụ thể và làm rõ trách nhiệm.

### Bước 1: Chọn một use case

Ví dụ hủy đơn hàng. Theo dõi request từ Controller đến repository và response cuối cùng.

### Bước 2: Liệt kê trách nhiệm hiện đang trộn

Đánh dấu phần nào là:

- HTTP binding và response.
- Validation cấu trúc.
- Quy tắc nghiệp vụ.
- Điều phối transaction.
- Truy cập persistence.
- Mapping dữ liệu trình bày.

### Bước 3: Xác định hợp đồng application

Tạo command/query và use case có kiểu dữ liệu độc lập với HTTP. Chỉ đưa vào các thông tin ca sử dụng cần, ví dụ OrderId, ActorId và reason.

### Bước 4: Chuyển quy tắc về domain/application

Đưa điều kiện chuyển trạng thái vào domain behavior hoặc policy. Controller không tự kiểm tra trạng thái rồi sửa field.

### Bước 5: Tách persistence adapter

Nếu cần, định nghĩa repository port và để JPA/SQL adapter triển khai. Đừng để application phụ thuộc vào implementation cụ thể.

### Bước 6: Giữ View/API ở ranh giới

Tạo ViewModel hoặc Response DTO. Controller chuyển command/result sang dữ liệu trình bày. View không tự truy cập Service hoặc Repository.

### Bước 7: Thêm kiểm thử hành vi và dependency

Kiểm tra use case, Controller response và architecture rule. Sau đó mới di chuyển lớp hoặc đổi package theo cấu trúc đã chọn.

### Bước 8: Lặp lại theo luồng khác

Khi một luồng đã có ranh giới rõ, áp dụng cùng nguyên tắc cho use case kế tiếp. Tránh refactor toàn bộ dự án trong một thay đổi lớn nếu chưa có test bảo vệ.

## 11. Kiểm thử để phát hiện coupling

Cần kiểm tra cả hành vi lẫn cấu trúc.

| Loại kiểm thử | Câu hỏi cần trả lời |
|---|---|
| Domain unit test | Quy tắc có đúng khi không có Spring/HTTP không? |
| Application unit test | Use case có điều phối đúng qua các port không? |
| Controller test | Request được chuyển thành command và response đúng không? |
| View/template test | View có render từ dữ liệu được cung cấp mà không truy cập hạ tầng không? |
| Integration test | Adapter persistence và transaction hoạt động đúng không? |
| Architecture test | Domain có phụ thuộc web không; package có chu trình không? |
| Contract test | DTO và status có ổn định với client không? |

Một dấu hiệu tốt là có thể test domain bằng JUnit thuần, test application bằng fake port, test Controller bằng MockMvc và test persistence riêng. Nếu muốn test một quy tắc domain phải khởi động servlet container, database và template engine, có thể ranh giới đang bị trộn.

## 12. Những hiểu lầm thường gặp

### Tạo đủ ba thư mục là đã áp dụng MVC

Ba thư mục không chứng minh trách nhiệm đã được phân tách. Cần kiểm tra lớp nào gọi lớp nào và quyết định nào thuộc tầng nào.

### Mọi lớp dữ liệu đều thuộc Model

Entity, DTO, command, projection và ViewModel có mục đích khác nhau. Gộp chúng vào một package model chung khiến package thành nơi chứa mọi thứ và làm ranh giới mờ đi.

### Controller càng mỏng càng tốt bằng mọi giá

Controller mỏng là tốt khi nó chuyển request qua application contract. Nhưng không nên đẩy toàn bộ xử lý vào một helper toàn cục hoặc một service không có ranh giới rõ. Mục tiêu là đúng trách nhiệm, không phải giảm số dòng Controller.

### Cấm mọi phụ thuộc giữa package

Một ứng dụng cần dependency có hướng. Controller phụ thuộc application là hợp lý; application dùng domain là hợp lý. Cần cấm phụ thuộc sai hướng, chu trình và truy cập nội bộ trái hợp đồng, không cấm mọi tham chiếu giữa package.

### Dùng interface cho mọi class sẽ giải quyết coupling

Interface không tự tạo ra kiến trúc tốt. Một interface phản chiếu từng method của implementation mà không thể hiện hợp đồng có thể chỉ thêm lớp gián tiếp. Hãy tạo port khi cần bảo vệ ranh giới hoặc thay thế adapter, không chỉ để mọi class có một interface.

### Chuyển hết sang package-by-feature sẽ tự hết phụ thuộc chéo

Package-by-feature giúp gom trách nhiệm theo năng lực, nhưng module vẫn có thể import sâu vào nhau. Cần public API, quy tắc phụ thuộc và kiểm thử kiến trúc.

### Dùng event thay method call cho mọi thứ

Event không loại bỏ coupling về schema, thứ tự, retry và semantics. Dùng event khi cần thông báo hoặc tách thời gian; dùng lời gọi trực tiếp khi quan hệ đồng bộ đơn giản và rõ ràng.

## 13. Checklist rà soát cấu trúc MVC

- [ ] Controller không truy cập Repository trực tiếp cho ca sử dụng thông thường.
- [ ] Controller không chứa quy tắc chuyển trạng thái nghiệp vụ.
- [ ] View không truy cập Service hoặc Repository nội bộ.
- [ ] Application service không nhận HttpServletRequest, ResponseEntity hoặc tên template.
- [ ] Domain không phụ thuộc Spring MVC, Servlet API hoặc template engine.
- [ ] Persistence Entity không được dùng làm hợp đồng API/View một cách tùy tiện.
- [ ] Request DTO, command, response DTO và ViewModel có mục đích rõ.
- [ ] Dependency được truyền qua constructor hoặc hợp đồng tường minh.
- [ ] Package/module có hướng phụ thuộc và public API xác định.
- [ ] Không có vòng phụ thuộc không chủ ý.
- [ ] Architecture test bảo vệ các quy tắc quan trọng.
- [ ] Có thể kiểm thử domain/application mà không cần khởi động web stack.

## Kết luận

Chia dự án thành controller, model và view chỉ là bước tổ chức file. Nếu Controller truy cập persistence và xử lý nghiệp vụ, View tự gọi Service, hoặc Model phụ thuộc vào HTTP, ba nhóm vẫn bị trộn về mặt kiến trúc. Hãy xác định trách nhiệm, hợp đồng và hướng phụ thuộc trước; để Controller làm adapter, application điều phối use case, domain bảo vệ quy tắc, infrastructure triển khai chi tiết lưu trữ và View chỉ trình bày dữ liệu được cung cấp. Có thể tổ chức theo layer, feature hoặc kết hợp cả hai, nhưng cần kiểm soát chu trình phụ thuộc và kiểm thử các quy tắc kiến trúc để cấu trúc thư mục phản ánh được ranh giới thực sự.


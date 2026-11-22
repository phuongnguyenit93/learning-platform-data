# Request, session, application scope trong web context

Trong Spring, **scope** quy định vòng đời và phạm vi chia sẻ của một bean. Scope mặc định là `singleton`: một instance cho mỗi bean definition trong một Spring container. Với ứng dụng web chạy trên Servlet stack, Spring còn cung cấp các scope gắn với vòng đời HTTP:

- **Request scope**: một instance cho mỗi HTTP request.
- **Session scope**: một instance cho mỗi HTTP session của người dùng.
- **Application scope**: một instance cho mỗi ServletContext của web application.

Các scope này giúp đặt dữ liệu đúng nơi cần tồn tại. Ví dụ, metadata chỉ dùng trong một request nên thuộc request scope; giỏ hàng tạm của một người dùng có thể thuộc session scope; một catalog dùng chung và gần như bất biến có thể thuộc application scope.

Điều quan trọng là hiểu **phạm vi sống của bean khác nhau**, dù cả ba vẫn được Spring quản lý như bean bình thường. Chúng không tự động làm dữ liệu bền vững, không thay thế database và cũng không tự giải quyết vấn đề truy cập đồng thời.

## 1. Scope là gì?

Scope trả lời ba câu hỏi:

1. Khi nào container tạo instance của bean?
2. Những lần truy cập nào nhận cùng instance?
3. Khi nào instance kết thúc vòng đời và được dọn dẹp?

Trong Spring Core, hai scope cơ bản thường gặp là:

| Scope | Hành vi |
|---|---|
| **singleton** | Một instance cho một bean definition trong một container; đây là mặc định. |
| **prototype** | Container tạo instance mới mỗi lần bean được yêu cầu từ container. |

Trong web-aware context của Spring, có thêm các scope:

| Scope web | Phạm vi instance |
|---|---|
| **request** | Một HTTP request hiện hành. |
| **session** | Một HTTP session hiện hành. |
| **application** | Một ServletContext của web application. |

Có thể hình dung phạm vi lồng nhau:

```text
Web application (ServletContext)
│
├── Request A
│   ├── Request-scoped bean A
│   └── Session-scoped bean của Session X
│
├── Request B
│   ├── Request-scoped bean B
│   └── Session-scoped bean của Session X
│
└── Request C
    ├── Request-scoped bean C
    └── Session-scoped bean của Session Y

Application-scoped bean:
  Một instance trong phạm vi ServletContext,
  được các request trong web application dùng chung.
```

Sơ đồ là ví dụ với ba request thuộc hai session. Một request luôn có context riêng; nhiều request của cùng session có thể truy cập cùng session-scoped bean; mọi session trong cùng ServletContext có thể truy cập application-scoped bean.

## 2. Web scope chỉ hoạt động khi có web context phù hợp

Các scope request, session và application dựa trên hạ tầng web của Spring. Chúng cần một **web-aware ApplicationContext** và scope tương ứng phải đang hoạt động.

Trong ứng dụng Spring MVC chạy trên Servlet stack, Spring tích hợp request context thông qua `DispatcherServlet` hoặc các cơ chế Servlet request-context tương ứng. Spring Boot web application thường thiết lập hạ tầng cần thiết khi cấu hình web phù hợp.

Nếu tạo một `AnnotationConfigApplicationContext` thuần Java không có web environment rồi yêu cầu bean request-scoped, Spring không có HTTP request hiện hành để xác định instance. Tương tự, session scope không thể hoạt động nếu không có session đang gắn với request.

Ví dụ, nếu bean được khai báo:

```java
@Component
@RequestScope
public class RequestMetadata {
    // ...
}
```

và bạn cố lấy bean này trong một ứng dụng command-line không có request, container có thể báo lỗi scope chưa active. Annotation không tự tạo một HTTP request giả.

**Phân biệt hai việc:**

- Bean definition có thể được đăng ký khi application context khởi động.
- Target instance của request/session scope chỉ có thể được lấy khi scope tương ứng có context hợp lệ.

## 3. Request scope: một instance cho mỗi HTTP request

Request scope phù hợp với dữ liệu chỉ có ý nghĩa trong một lần xử lý HTTP, ví dụ:

- Request ID/correlation ID.
- Thông tin trace gắn với request.
- Một đối tượng gom dữ liệu tạm trong quá trình xử lý request.
- Metadata đã được xác định từ header hoặc request attributes.

### 3.1. Khai báo bằng `@RequestScope`

Ví dụ một bean chứa request ID:

```java
package com.example.demo.web;

import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope
public class RequestMetadata {

    private final String requestId = UUID.randomUUID().toString();

    public String getRequestId() {
        return requestId;
    }
}
```

`@RequestScope` là annotation chuyên dụng của Spring, tương đương khai báo scope request và mặc định dùng scoped proxy theo cơ chế class-based proxy.

Mỗi request có target instance riêng. Khi hai HTTP request khác nhau cùng sử dụng bean, chúng nhận hai `RequestMetadata` khác nhau.

### 3.2. Inject request-scoped bean vào singleton service

Service trong ứng dụng thường là singleton. Nếu constructor của singleton nhận trực tiếp một object request-scoped, cần cơ chế để dependency được phân giải đúng theo request hiện hành.

Ví dụ:

```java
package com.example.demo.service;

import com.example.demo.web.RequestMetadata;
import org.springframework.stereotype.Service;

@Service
public class AuditService {

    private final RequestMetadata metadata;

    public AuditService(RequestMetadata metadata) {
        this.metadata = metadata;
    }

    public void record(String action) {
        System.out.println(
                metadata.getRequestId() + " - " + action
        );
    }
}
```

Tại sao cách này không làm singleton giữ một request instance duy nhất?

Vì `@RequestScope` mặc định tạo **scoped proxy**. Singleton `AuditService` giữ tham chiếu tới proxy; khi gọi method, proxy tìm target instance tương ứng với request hiện hành.

```text
ApplicationContext tạo AuditService (singleton)
                │
                │ giữ tham chiếu
                ▼
       RequestMetadata proxy
                │
        method được gọi
                │
        ┌───────┴────────┐
        ▼                ▼
    Request A        Request B
        │                │
        ▼                ▼
  Target A           Target B
  RequestMetadata    RequestMetadata
```

Proxy cho phép một bean có vòng đời dài tham chiếu tới bean có vòng đời ngắn hơn. Không có proxy hoặc cơ chế lookup theo yêu cầu, singleton có thể giữ target được tạo ở thời điểm khởi tạo và dùng sai instance cho các request sau.

### 3.3. Dùng `ObjectProvider` thay cho scoped proxy

Một cách khác là inject provider và lấy target khi cần:

```java
import com.example.demo.web.RequestMetadata;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public class AuditService {

    private final ObjectProvider<RequestMetadata> metadataProvider;

    public AuditService(
            ObjectProvider<RequestMetadata> metadataProvider) {
        this.metadataProvider = metadataProvider;
    }

    public void record(String action) {
        RequestMetadata metadata = metadataProvider.getObject();
        System.out.println(metadata.getRequestId() + " - " + action);
    }
}
```

`ObjectProvider` trì hoãn việc lấy bean cho đến khi gọi `getObject()`. Đây là lựa chọn rõ ràng khi code muốn thể hiện rằng dependency được tra theo ngữ cảnh hiện hành.

Dù dùng proxy hay provider, target request-scoped vẫn chỉ có ý nghĩa khi request context đang active. Nếu gọi `record()` từ một thread nền không gắn với request, việc lấy `RequestMetadata` có thể thất bại.

### 3.4. Ví dụ controller quan sát request scope

```java
package com.example.demo.api;

import com.example.demo.service.AuditService;
import com.example.demo.web.RequestMetadata;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RequestController {

    private final RequestMetadata metadata;
    private final AuditService auditService;

    public RequestController(
            RequestMetadata metadata,
            AuditService auditService) {
        this.metadata = metadata;
        this.auditService = auditService;
    }

    @GetMapping("/request-info")
    public String requestInfo() {
        auditService.record("GET /request-info");
        return metadata.getRequestId();
    }
}
```

Gửi nhiều request tới `/request-info`; mỗi request sẽ trả về request ID được tạo cho target instance tương ứng. Nếu request đi qua cùng một session hay từ cùng một browser, request scope vẫn tạo target mới cho từng request.

## 4. Session scope: một instance cho mỗi HTTP session

**Session scope** dùng khi dữ liệu cần tồn tại qua nhiều HTTP request thuộc cùng một session. Ví dụ:

- Giỏ hàng tạm của người dùng.
- Một số lựa chọn trong wizard nhiều bước.
- Trạng thái giao diện ngắn hạn gắn với phiên làm việc.
- Một tập dữ liệu nhỏ được dùng lại trong nhiều request.

Ví dụ:

```java
package com.example.demo.web;

import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.SessionScope;

@Component
@SessionScope
public class ShoppingCart {

    private final List<String> productIds = new ArrayList<>();

    public void add(String productId) {
        productIds.add(productId);
    }

    public List<String> getProductIds() {
        return List.copyOf(productIds);
    }

    public void clear() {
        productIds.clear();
    }
}
```

`@SessionScope` là annotation chuyên dụng của Spring cho scope session và mặc định sử dụng scoped proxy.

Một request đầu tiên có thể tạo session nếu ứng dụng cần lưu trạng thái. Các request tiếp theo mang cùng session ID có thể truy cập cùng target `ShoppingCart`. Một session khác nhận target `ShoppingCart` riêng.

```text
Web application
│
├── Session X
│   ├── Request 1 ──┐
│   ├── Request 2 ──┼──> ShoppingCart X
│   └── Request 3 ──┘
│
└── Session Y
    ├── Request 4 ──┐
    └── Request 5 ──┴──> ShoppingCart Y
```

### 4.1. Inject session bean vào singleton

```java
@Service
public class CartService {

    private final ShoppingCart cart;

    public CartService(ShoppingCart cart) {
        this.cart = cart;
    }

    public void addProduct(String productId) {
        cart.add(productId);
    }

    public List<String> currentProducts() {
        return cart.getProductIds();
    }
}
```

`CartService` có thể là singleton. Nó giữ scoped proxy cho `ShoppingCart`; khi method được gọi trong một request, proxy lấy target gắn với session hiện hành.

Controller:

```java
@RestController
@RequestMapping("/cart")
public class CartController {

    private final CartService cartService;

    public CartController(CartService cartService) {
        this.cartService = cartService;
    }

    @PostMapping("/{productId}")
    public List<String> add(@PathVariable String productId) {
        cartService.addProduct(productId);
        return cartService.currentProducts();
    }

    @GetMapping
    public List<String> view() {
        return cartService.currentProducts();
    }
}
```

Các request có cùng session sẽ quan sát cùng danh sách sản phẩm. Nếu không có session hiện hành, Spring/Servlet container có thể tạo session tùy cách truy cập và cấu hình; hãy hiểu rõ khi nào ứng dụng tạo session để tránh phát sinh session không cần thiết.

### 4.2. Session scope không phải database

Session-scoped bean thường lưu trạng thái trong bộ nhớ của web application thông qua HTTP session. Nó không tự đảm bảo dữ liệu bền vững qua:

- Restart ứng dụng nếu session không được lưu/replicate.
- Session timeout hoặc người dùng logout.
- Deploy nhiều instance nếu session không được chia sẻ hoặc sticky routing không được cấu hình phù hợp.
- Mất session cookie hoặc session invalidation.

Nếu giỏ hàng hoặc dữ liệu người dùng cần tồn tại lâu dài, cần persistence phù hợp. Session scope chỉ là **phạm vi sử dụng trong vòng đời session**, không phải chiến lược lưu trữ bền vững.

### 4.3. Nhiều request của một session có thể chạy đồng thời

Một session có thể gửi nhiều request gần như cùng lúc: nhiều tab browser, AJAX song song hoặc retry. Do đó, hai thread có thể truy cập cùng một target session-scoped bean.

Trong ví dụ `ShoppingCart`, `ArrayList` không được thiết kế cho cập nhật đồng thời không đồng bộ. Ví dụ phù hợp để học scope, nhưng trong ứng dụng thật cần cân nhắc đồng bộ hóa, collection phù hợp, xử lý ở tầng service hoặc lưu trạng thái ở kho dữ liệu an toàn.

**Session scope không tự làm object thread-safe.** Nó chỉ quyết định instance nào được chia sẻ trong phạm vi session.

## 5. Application scope: một instance cho mỗi ServletContext

Application scope là phạm vi của **ServletContext** trong một web application. Bean có thể được dùng chung qua các request và session thuộc cùng ServletContext.

Ví dụ phù hợp:

- Catalog cấu hình ít thay đổi, dùng chung trong web application.
- Một tập metadata đọc nhiều, gần như bất biến.
- Một thành phần quản lý tài nguyên ứng dụng có lifecycle gắn với ServletContext.

Ví dụ bean catalog:

```java
package com.example.demo.web;

import java.util.List;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.ApplicationScope;

@Component
@ApplicationScope
public class ApplicationCatalog {

    private final List<String> categories =
            List.of("BOOK", "DEVICE", "ACCESSORY");

    public List<String> getCategories() {
        return categories;
    }
}
```

`@ApplicationScope` là annotation chuyên dụng của Spring cho scope application trong ServletContext. Nó mặc định sử dụng scoped proxy, tương tự request/session scope.

Controller có thể inject bean này:

```java
@RestController
@RequestMapping("/catalog")
public class CatalogController {

    private final ApplicationCatalog catalog;

    public CatalogController(ApplicationCatalog catalog) {
        this.catalog = catalog;
    }

    @GetMapping("/categories")
    public List<String> categories() {
        return catalog.getCategories();
    }
}
```

Mọi request và session trong cùng ServletContext nhận cùng target `ApplicationCatalog`. Trong ví dụ, danh sách là immutable nên phù hợp với dữ liệu dùng chung.

### 5.1. Application scope khác singleton như thế nào?

Hai scope này dễ bị nhầm vì đều có vẻ “một instance dùng chung”.

| Tiêu chí | Spring singleton | Application scope |
|---|---|---|
| Phạm vi | Một bean definition trong một Spring container. | Một ServletContext của web application. |
| Phụ thuộc web context | Không. | Có. |
| Dùng trong ứng dụng non-web | Có. | Không có ServletContext nên không phù hợp. |
| Ý nghĩa chia sẻ | Trong container sở hữu bean definition. | Trong phạm vi web application/ServletContext. |
| Dùng khi nào | Service, repository, component stateless phổ biến. | Trạng thái/đối tượng có phạm vi gắn với ServletContext. |

Nếu ứng dụng có một root `ApplicationContext` và một child web context, các singleton bean trong hai context là các instance thuộc hai container khác nhau nếu mỗi context đăng ký definition riêng. Application scope được gắn với ServletContext, nên semantics của nó khác singleton container scope.

**Không nên dùng application scope chỉ vì muốn “global singleton”.** Đối với service stateless thông thường, singleton mặc định thường phù hợp hơn. Application scope dành cho nhu cầu thật sự gắn với vòng đời web application.

### 5.2. Application scope không phải scope cho toàn bộ cluster

Nếu bạn chạy ba instance Spring Boot trên ba JVM/container, mỗi instance có ServletContext riêng và application-scoped bean riêng. Chúng không chia sẻ Java object qua mạng.

```text
Load balancer
   │
   ├── Instance A / ServletContext A ── ApplicationCatalog A
   ├── Instance B / ServletContext B ── ApplicationCatalog B
   └── Instance C / ServletContext C ── ApplicationCatalog C
```

Nếu cần dữ liệu đồng bộ giữa các instance, hãy dùng database, distributed cache, message broker hoặc dịch vụ cấu hình phù hợp. Application scope chỉ là **local shared state trong một web application instance**.

## 6. So sánh request, session và application scope

| Câu hỏi | Request | Session | Application |
|---|---|---|---|
| Một instance cho mỗi... | HTTP request | HTTP session | ServletContext |
| Được chia sẻ giữa nhiều request? | Không, mỗi request target riêng | Có, nếu cùng session | Có, trong cùng web application |
| Được chia sẻ giữa các session? | Không | Không | Có |
| Kết thúc thông thường | Khi request kết thúc | Khi session hết hạn/invalidated | Khi web application/ServletContext kết thúc |
| Ví dụ | Request metadata | Shopping cart tạm | Catalog cấu hình dùng chung |
| Rủi ro chính | Truy cập khi không có request active | Concurrent requests cùng session, session mất/timeout | Mutable state toàn ứng dụng, không chia sẻ giữa nhiều instance |

Một cách chọn nhanh:

- Dữ liệu chỉ cần trong **một lần HTTP request** → request scope.
- Dữ liệu cần giữ giữa nhiều request của **cùng một phiên** → session scope.
- Dữ liệu dùng chung trong **toàn bộ web application instance** → application scope.
- Thành phần nghiệp vụ không giữ trạng thái theo request/session → thường dùng singleton.

## 7. Scoped proxy giải quyết khác biệt vòng đời

Một singleton có vòng đời dài hơn request-scoped bean. Nếu inject target request bean trực tiếp vào constructor singleton mà không có cơ chế trung gian, target sẽ được giải quyết vào thời điểm tạo singleton; điều này không đáp ứng yêu cầu “mỗi request một instance”.

Các annotation chuyên dụng:

```java
@RequestScope
@Component
class RequestData { }

@SessionScope
@Component
class UserSessionData { }

@ApplicationScope
@Component
class WebApplicationData { }
```

Các annotation này mặc định khai báo scoped proxy theo kiểu class-based. Proxy tồn tại như dependency mà bean dài hạn có thể giữ; khi method được gọi, nó tìm target theo scope đang active.

Có thể khai báo scope thủ công:

```java
@Component
@Scope(
    value = WebApplicationContext.SCOPE_REQUEST,
    proxyMode = ScopedProxyMode.TARGET_CLASS
)
public class RequestData {
}
```

Tương tự, scope session và application có thể khai báo bằng hằng tương ứng trong `WebApplicationContext`.

### 7.1. Proxy có phải target bean không?

Không. Scoped proxy là đối tượng trung gian. Khi inject vào singleton, reference có thể là proxy; target thật được lấy theo request/session/application hiện hành.

Điều này có một số hệ quả:

- `getClass()` trên reference có thể cho thấy class proxy thay vì class target.
- Constructor của singleton có thể nhận proxy trước khi có request thực tế.
- Lời gọi method trên proxy cần scope tương ứng đang active.
- Proxy class-based có giới hạn với final class/method và một số kiểu cấu trúc; nếu cần, có thể dùng interface proxy hoặc `ObjectProvider`.

### 7.2. Chọn proxy mode tường minh

Có thể chọn proxy qua annotation:

```java
@RequestScope(proxyMode = ScopedProxyMode.INTERFACES)
@Component
public class RequestInfoImpl implements RequestInfo {
    // ...
}
```

Ví dụ này giả định có interface `RequestInfo` và class triển khai nó. Interface proxy phù hợp khi dependency được inject qua interface; class proxy có thể thuận tiện khi inject theo class cụ thể nhưng yêu cầu class/method có thể proxy.

Không nên đổi proxy mode chỉ để xử lý một lỗi chưa hiểu rõ. Trước hết xác định kiểu injection, class có final hay không, và scope target cần truy cập ở thời điểm nào.

## 8. Dùng `ObjectProvider` để lấy scoped bean đúng lúc

Thay vì để proxy chuyển tiếp lời gọi, singleton có thể nhận `ObjectProvider<T>` và yêu cầu bean khi cần.

Ví dụ:

```java
@Service
public class RequestAuditService {

    private final ObjectProvider<RequestMetadata> provider;

    public RequestAuditService(
            ObjectProvider<RequestMetadata> provider) {
        this.provider = provider;
    }

    public String currentRequestId() {
        return provider.getObject().getRequestId();
    }
}
```

`ObjectProvider` trì hoãn việc lấy bean cho đến khi gọi `getObject()`. Cách này thể hiện rõ dependency được tra theo thời điểm sử dụng.

Ưu điểm:

- Dependency được thể hiện rõ là cần lookup theo thời điểm sử dụng.
- Không cần giữ target scoped bean từ lúc singleton được khởi tạo.
- Có thể kiểm soát rõ nơi gọi `getObject()`.

Nhược điểm là caller phải gọi provider; nếu dùng khắp nơi, code có thể trở nên nhiều lớp gián tiếp. Scoped proxy thường tự nhiên hơn cho một dependency được dùng như object bình thường.

Không nên inject `ApplicationContext` vào mọi service chỉ để gọi `getBean()` thủ công. `ObjectProvider` thể hiện mục đích hẹp hơn và thường dễ test hơn.

## 9. Request scope và xử lý bất đồng bộ

Request scope gắn với **ngữ cảnh HTTP request**, không đơn giản là “một object cho mỗi thread”. Một request có thể được xử lý qua nhiều thread hoặc nhiều dispatch trong mô hình servlet async. Spring có cơ chế tích hợp request context trong các luồng xử lý web của framework, nhưng không nên giả định mọi thread do ứng dụng tự tạo đều tự động có request context.

Ví dụ không nên làm:

```java
@GetMapping("/report")
public String report() {
    executor.execute(() -> {
        // Không mặc định thread này có request context.
        auditService.record("background");
    });
    return "scheduled";
}
```

Nếu `auditService` cần `RequestMetadata` qua scoped proxy, lời gọi từ thread nền có thể thất bại vì request scope không active trên thread đó.

Hướng xử lý:

1. Đọc dữ liệu cần thiết từ request khi request còn active.
2. Truyền giá trị bất biến (ví dụ request ID) thành tham số của tác vụ nền.
3. Nếu cần correlation context, truyền/propagate context theo cơ chế phù hợp của framework/executor/observability.
4. Không giữ request/response object để sử dụng sau khi request đã kết thúc.

Ví dụ:

```java
@GetMapping("/report")
public String report() {
    String requestId = requestMetadata.getRequestId();

    executor.execute(() -> reportService.generate(requestId));
    return "scheduled";
}
```

Ở đây tác vụ nền nhận một chuỗi độc lập thay vì cố truy cập request-scoped bean sau này. `requestId` là dữ liệu được sao chép rõ ràng, không phải proxy gắn với request đã kết thúc.

Với Spring WebFlux, mô hình xử lý dựa trên reactive pipeline và Reactor Context; không áp dụng nguyên xi giả định ThreadLocal/Servlet request context. Hãy dùng API WebFlux tương ứng thay vì mang `HttpServletRequest`/Servlet scopes vào reactive flow.

## 10. Session scope và tính đồng thời

Session scope chia sẻ target giữa các request thuộc cùng session. Một người dùng có thể mở nhiều tab, gửi hai form đồng thời hoặc browser tự retry request. Vì vậy, một session-scoped bean mutable có thể bị truy cập đồng thời.

Ví dụ đơn giản:

```java
@SessionScope
@Component
public class ShoppingCart {
    private final List<String> productIds = new ArrayList<>();

    public void add(String productId) {
        productIds.add(productId);
    }
}
```

Hai request song song cùng gọi `add()` có thể gây race condition hoặc dữ liệu không nhất quán. Các lựa chọn phụ thuộc yêu cầu:

- Giữ session bean immutable, mỗi lần cập nhật tạo state mới.
- Đồng bộ hóa các thao tác cập nhật nếu phù hợp.
- Dùng cấu trúc dữ liệu có semantics đồng thời phù hợp, nhưng vẫn phải xét tính nguyên tử của nhiều thao tác.
- Chuyển trạng thái quan trọng sang database hoặc cache có cơ chế cập nhật nhất quán.

Đừng nghĩ `@SessionScope` tạo ra một object riêng cho từng thread. Nó tạo object theo **session**, còn một session có thể có nhiều request đang hoạt động.

Session cũng có thể bị timeout hoặc invalidated khi logout. Nếu bean có tài nguyên cần đóng, hãy hiểu cơ chế destruction callback và cấu hình session của container; không lưu socket/file handle hoặc tài nguyên không thể serialize một cách tùy tiện trong session.

## 11. Application scope và trạng thái dùng chung

Application-scoped bean có thể được nhiều request gọi đồng thời. Vì thế, cùng nguyên tắc thread-safety áp dụng mạnh hơn: mọi session và request trong cùng ServletContext đều có thể chạm tới cùng target.

Ví dụ dữ liệu cấu hình bất biến:

```java
@ApplicationScope
@Component
public class SupportedLanguages {
    private final Set<String> languages =
            Set.of("vi", "en", "ja");

    public Set<String> all() {
        return languages;
    }
}
```

Đây là kiểu object phù hợp: dữ liệu được tạo một lần, không thay đổi và có thể đọc đồng thời.

Ví dụ mutable state dùng chung:

```java
@ApplicationScope
@Component
public class GlobalCounter {
    private long count;

    public long increment() {
        return ++count;
    }
}
```

Code này không thread-safe. Nếu thực sự cần counter cục bộ một instance, có thể dùng `AtomicLong`:

```java
@ApplicationScope
@Component
public class GlobalCounter {
    private final AtomicLong count = new AtomicLong();

    public long increment() {
        return count.incrementAndGet();
    }
}
```

Nhưng `AtomicLong` chỉ bảo vệ cập nhật trong **một JVM/instance**. Khi triển khai nhiều instance, mỗi ServletContext vẫn có counter riêng. Muốn đếm toàn cluster cần một hệ thống lưu trữ/đồng bộ phân tán.

Một ứng dụng Spring Boot thường nên ưu tiên singleton service stateless và dữ liệu bất biến hơn là biến mọi cấu hình toàn cục thành application-scoped mutable bean.

## 12. Phân biệt session scope với Spring Security principal

Session-scoped bean không đồng nghĩa với đối tượng người dùng đã đăng nhập.

Spring Security thường lưu thông tin xác thực trong `SecurityContext` theo cơ chế security context repository phù hợp với ứng dụng. Một controller/service có thể truy cập principal hiện tại qua security context hoặc method security. Không nên tự lưu password, token bí mật hoặc toàn bộ object xác thực vào một bean session-scoped tùy tiện.

Nếu cần giữ lựa chọn UI hoặc giỏ hàng, session scope có thể phù hợp. Nếu cần xác định người dùng đang xác thực, dùng cơ chế của Spring Security. Hai loại trạng thái có thể cùng tồn tại nhưng có **trách nhiệm và lifecycle khác nhau**.

Trong ứng dụng stateless REST dùng bearer token, có thể không sử dụng HTTP session cho authentication. Điều đó không tự cấm ứng dụng có session scope cho một chức năng khác, nhưng cần quyết định rõ liệu endpoint có tạo session ngoài ý muốn hay không.

## 13. Scope và triển khai nhiều web application context

Trong ứng dụng web lớn, Spring có thể có nhiều `ApplicationContext`, ví dụ root context và context gắn với servlet. Điều này khiến hai khái niệm dễ nhầm:

- **Singleton scope**: một instance theo bean definition trong mỗi container.
- **Application scope**: gắn với `ServletContext`, là phạm vi web application.

Do đó, không nên dùng từ “global” mà không chỉ rõ phạm vi. Một singleton trong child context không tự động là cùng object với singleton có cùng class ở root context. Application scope gắn với ServletContext nên có semantics khác, dù các instance đó vẫn được truy cập qua Spring bean infrastructure.

Trong một Spring Boot app đơn giản, lập trình viên thường chỉ tương tác với một application context chính, vì vậy khác biệt này ít lộ ra. Nó quan trọng khi tích hợp servlet context phức tạp hoặc legacy application.

## 14. Scope nào phù hợp với tình huống nào?

| Tình huống | Scope/cơ chế nên cân nhắc | Vì sao |
|---|---|---|
| Service tính toán không lưu trạng thái request | Singleton mặc định | Một instance dùng lại, dependency rõ ràng. |
| Request ID, metadata riêng của một lần gọi | Request | Không rò dữ liệu sang request khác. |
| Giỏ hàng tạm trong một phiên người dùng | Session | Giữ state qua nhiều request cùng session. |
| Catalog cấu hình immutable dùng chung trong một web app | Application hoặc singleton tùy ranh giới cần thiết | Application gắn ServletContext; singleton gắn container. |
| Dữ liệu phải sống qua restart/deploy | Database/cache bền vững | Web scope chỉ sống theo vòng đời runtime. |
| Trạng thái dùng chung giữa nhiều JVM | Distributed store/service | Scope local không đồng bộ qua mạng. |
| Thông tin xác thực người dùng | Spring Security context | Security framework quản lý identity/authentication. |
| Tác vụ nền chạy sau khi request kết thúc | Truyền dữ liệu cần thiết hoặc context propagation | Không phụ thuộc request scope đã hết active. |

## 15. Cách kiểm tra behavior của từng scope

Một cách học trực quan là ghi lại identity của bean qua nhiều request.

Có thể tạo endpoint minh họa:

```java
@RestController
public class ScopeDemoController {

    private final RequestMetadata requestMetadata;
    private final ShoppingCart shoppingCart;
    private final ApplicationCatalog applicationCatalog;

    public ScopeDemoController(
            RequestMetadata requestMetadata,
            ShoppingCart shoppingCart,
            ApplicationCatalog applicationCatalog) {
        this.requestMetadata = requestMetadata;
        this.shoppingCart = shoppingCart;
        this.applicationCatalog = applicationCatalog;
    }

    @GetMapping("/scope-demo")
    public Map<String, Object> scopeDemo() {
        return Map.of(
            "requestId", requestMetadata.getRequestId(),
            "cartSize", shoppingCart.getProductIds().size(),
            "categories", applicationCatalog.getCategories()
        );
    }
}
```

Thử nghiệm:

1. Gọi `/scope-demo` lần đầu trong browser A.
2. Gọi lại bằng browser A, vẫn cùng session cookie: request ID mới, giỏ hàng cùng session.
3. Gọi bằng browser B không có session cookie: request ID mới, session/cart riêng.
4. So sánh catalog: cùng application instance thì nội dung catalog giống nhau.
5. Restart ứng dụng: request/session/application targets được tạo lại theo lifecycle mới, trừ khi session được lưu trữ/phục hồi bởi hạ tầng bên ngoài.

Không nên dựa vào nội dung catalog giống nhau để kết luận identity object giống nhau; nếu muốn kiểm tra identity, thêm một ID khởi tạo riêng cho bean trong môi trường thử nghiệm và quan sát có kiểm soát.

### Kiểm thử request scope bằng MockMvc

Trong Spring MVC test, mỗi HTTP request thực hiện qua MockMvc có request context riêng. Ví dụ:

```java
@SpringBootTest
@AutoConfigureMockMvc
class RequestScopeTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void eachRequestGetsItsOwnRequestId() throws Exception {
        MvcResult first = mockMvc.perform(get("/request-info"))
                .andExpect(status().isOk())
                .andReturn();

        MvcResult second = mockMvc.perform(get("/request-info"))
                .andExpect(status().isOk())
                .andReturn();

        assertNotEquals(
                first.getResponse().getContentAsString(),
                second.getResponse().getContentAsString()
        );
    }
}
```

Ví dụ giả định endpoint `/request-info` trả request ID duy nhất và có các import MockMvc/JUnit cần thiết. Hai request độc lập nên có request-scoped target khác nhau. Khi test session scope, cần dùng cùng `MockHttpSession` cho các request muốn mô phỏng cùng session; dùng session khác để kiểm tra target độc lập.

## 16. Lỗi thường gặp khi sử dụng web scope

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `Scope 'request' is not active` | Gọi request-scoped bean ngoài HTTP request hiện hành hoặc thread không có request context. | Xem call path, async task, web context và thời điểm gọi proxy. |
| `Scope 'session' is not active` | Không có HTTP session/request phù hợp tại thời điểm truy cập. | Kiểm tra request/session lifecycle, cách khởi tạo và môi trường test. |
| Bean request bị giữ qua nhiều request | Target được inject trực tiếp mà không có proxy/provider đúng cách hoặc cấu hình scope sai. | Kiểm tra `@RequestScope`, scoped proxy và bean definition. |
| Session state biến mất | Session hết hạn, bị invalidated, cookie không được gửi hoặc deploy không lưu/replicate session. | Kiểm tra cookie/session ID, timeout, logout và session store. |
| Dữ liệu giỏ hàng bị lỗi khi request song song | Nhiều request cùng session sửa mutable object không thread-safe. | Kiểm tra đồng thời và thiết kế cập nhật state. |
| Application bean có giá trị khác giữa các server | Mỗi JVM có ServletContext và application target riêng. | Dùng shared store/config service nếu cần đồng bộ. |
| Request scope lỗi trong background executor | Thread nền không tự có request context. | Truyền dữ liệu cần thiết hoặc propagate context theo cơ chế hỗ trợ. |
| Test scope lỗi dù chạy ứng dụng bình thường | Test dùng non-web ApplicationContext hoặc thiếu mock request/session. | Dùng web test environment, MockMvc và mock session phù hợp. |
| Proxy không tạo được | Kiểu bean/class không tương thích với proxy mode, ví dụ class final khi dùng class-based proxy. | Kiểm tra interface/class, method final và proxy mode. |

### Một lưu ý về exception và cleanup

Không bắt mọi exception từ scope rồi trả về giá trị mặc định như `null`. Nếu request/session không active, đó là dấu hiệu code đang truy cập sai lifecycle. Hãy sửa ranh giới giữa request và tác vụ nền hoặc chọn scope đúng thay vì che giấu lỗi.

## 17. Bài tập thực hành

### Bài tập A — Request scope

Tạo `RequestMetadata` với ID ngẫu nhiên khi bean được tạo. Inject vào controller và trả ID ở mỗi request. Gọi endpoint nhiều lần; quan sát mỗi request có ID mới.

### Bài tập B — Session scope

Tạo `ShoppingCart` dùng `@SessionScope`. Thêm endpoint để thêm/xem sản phẩm. Gửi hai request cùng session cookie rồi so sánh với một browser/session khác. Giải thích vì sao request mới nhưng cart vẫn giữ dữ liệu.

### Bài tập C — Application scope

Tạo `ApplicationCatalog` dùng `@ApplicationScope`, chứa danh sách immutable. Truy cập từ nhiều request và nhiều session. Quan sát nó được chia sẻ trong cùng web application instance.

### Bài tập D — Singleton service inject request bean

Tạo `AuditService` singleton nhận `RequestMetadata`. Kiểm tra hai request có ghi ID khác nhau. Sau đó gọi audit service từ executor thread không có request context và giải thích lỗi. Sửa bằng cách truyền request ID như tham số.

### Bài tập E — Thread safety của session/application

Tạo một endpoint tăng counter trong session scope, gửi nhiều request đồng thời từ cùng session. Quan sát race condition khi dùng `int`/`ArrayList` không đồng bộ. Thử cơ chế đồng bộ thích hợp và phân biệt bảo vệ trong một JVM với đồng bộ nhiều instance.

### Bài tập F — Phân biệt singleton và application

Tạo hai web-aware application contexts trong một test có kiểm soát, đăng ký bean cùng kiểu ở mỗi context. So sánh singleton theo container với application scope theo ServletContext. Ghi lại phạm vi thực sự mà mỗi object được chia sẻ.

## 18. Nguyên tắc cần nhớ

1. **Request scope** sống theo một HTTP request; request mới có target mới.
2. **Session scope** sống theo HTTP session; các request cùng session có thể dùng chung target.
3. **Application scope** sống theo ServletContext; các request/session trong cùng web application instance có thể dùng chung target.
4. **Singleton** sống theo bean definition trong một Spring container; không đồng nghĩa application scope hoặc một instance toàn cluster.
5. Scoped proxy hoặc `ObjectProvider` giúp singleton dùng bean có scope ngắn hơn; target chỉ truy cập được khi scope đang active.
6. Session/application scoped bean mutable phải được thiết kế cho truy cập đồng thời.
7. Web scopes không phải database, không bảo đảm persistence và không tự chia sẻ giữa nhiều JVM.
8. Servlet scopes và WebFlux reactive context có mô hình khác nhau; đừng áp dụng cơ học `HttpSession`/`ServletContext` cho reactive pipeline.

Khi chọn scope, hãy bắt đầu từ câu hỏi **“Dữ liệu này cần được chia sẻ giữa những request nào và phải tồn tại đến thời điểm nào?”**. Nếu câu trả lời là một request, một phiên người dùng hay toàn bộ web application instance, lần lượt xem xét request, session hoặc application scope. Nếu cần sống lâu hơn runtime hoặc chia sẻ giữa nhiều instance, hãy chuyển trách nhiệm lưu trữ sang một cơ chế phù hợp hơn.

# Scoped proxy và sự khác nhau giữa tham chiếu proxy với đối tượng đích

Trong Spring Boot, một service mặc định thường là singleton: container tạo một instance và dùng instance đó trong suốt vòng đời của application context. Nhưng có dữ liệu chỉ có ý nghĩa trong một phạm vi ngắn hơn, chẳng hạn thông tin của **HTTP request hiện tại** hoặc **HTTP session hiện tại**. Nếu một singleton cần sử dụng bean có scope ngắn hơn, việc inject trực tiếp đối tượng đích có thể gây lỗi hoặc làm sai phạm vi dữ liệu.

Spring giải quyết tình huống này bằng **scoped proxy**. Một proxy có thể được inject vào bean singleton và giữ tham chiếu ổn định. Khi code gọi phương thức qua proxy, proxy tìm đối tượng đích (*target object*) tương ứng với scope đang hoạt động rồi chuyển lời gọi tới đối tượng đó.

Điều cần phân biệt:

- **Tham chiếu proxy** là object trung gian mà bean dài hạn giữ lại.
- **Đối tượng đích** là instance thực sự thuộc scope, ví dụ instance riêng của một HTTP request.
- **Scope** quyết định khi nào target được tạo, được chia sẻ và hết hiệu lực.

Proxy không làm cho request-scoped target trở thành singleton. Nó chỉ cho phép một bean có vòng đời dài hơn truy cập target đúng phạm vi tại thời điểm sử dụng.

## 1. Vì sao cần scoped proxy?

Giả sử một ứng dụng web có `AuditService` là singleton và `RequestInfo` là request-scoped:

```text
ApplicationContext
   |
   +-- AuditService (singleton)
   |       |
   |       +-- giữ một tham chiếu RequestInfo proxy
   |
   +-- RequestInfo target của request A
   |
   +-- RequestInfo target của request B
```

Khi request A chạy, proxy chuyển lời gọi đến target A. Khi request B chạy, cùng proxy đó chuyển lời gọi đến target B.

```text
Request A
   |
   v
AuditService
   |
   v
RequestInfo proxy -------> RequestInfo target A

Request B
   |
   v
AuditService
   |
   v
RequestInfo proxy -------> RequestInfo target B
```

`AuditService` không cần được tạo lại cho từng request và cũng không phải tự quản lý một biến toàn cục để giữ request hiện tại. Spring quản lý việc phân giải target theo scope.

## 2. Ôn lại bean scope

Scope mô tả phạm vi tồn tại và cách Spring cung cấp instance của bean. Một số scope thường gặp:

| Scope | Vòng đời điển hình | Trường hợp sử dụng |
| --- | --- | --- |
| `singleton` | Một instance cho một bean definition trong một IoC container | Service, repository, cấu hình dùng chung |
| `prototype` | Tạo instance mới khi container được yêu cầu lấy bean | Đối tượng có state cần tạo mới theo lần lấy |
| `request` | Một instance trong một HTTP request | Request ID, thông tin người gọi trong request |
| `session` | Một instance trong một HTTP session | Dữ liệu gắn với phiên người dùng |
| `application` | Một instance trong phạm vi `ServletContext` | Trạng thái dùng chung của web application |
| `websocket` | Một instance theo WebSocket session | Dữ liệu gắn với kết nối WebSocket |

`singleton` là scope mặc định. Request, session, application và WebSocket là các web-aware scope, cần môi trường web phù hợp. Không thể mặc định sử dụng request scope trong một chương trình console hoặc một background job không có HTTP request đang hoạt động.

### 2.1. Vấn đề khi singleton giữ trực tiếp bean request-scoped

Ví dụ:

```java
@Component
@Scope("request")
public class RequestInfo {
    private final String requestId = UUID.randomUUID().toString();

    public String getRequestId() {
        return requestId;
    }
}
```

Và một singleton:

```java
@Service
public class AuditService {
    private final RequestInfo requestInfo;

    public AuditService(RequestInfo requestInfo) {
        this.requestInfo = requestInfo;
    }
}
```

Nếu Spring cố tạo `AuditService` lúc khởi động, trong khi chưa có HTTP request nào hoạt động, nó không thể lấy một request-scoped target cụ thể để đưa trực tiếp vào constructor. Request scope chưa có đối tượng đích hợp lệ tại thời điểm đó.

Nếu lấy target của request đầu tiên rồi giữ trong singleton, mọi request sau có thể vô tình sử dụng dữ liệu của request đầu tiên. Điều này vi phạm mục đích của scope và có thể làm lộ dữ liệu giữa các request.

Scoped proxy giải quyết bài toán bằng cách inject một **tham chiếu trung gian**. Target chỉ được phân giải khi có lời gọi phù hợp trong scope đang hoạt động.

## 3. Scoped proxy là gì?

**Scoped proxy** là một proxy do Spring tạo cho bean thuộc một scope. Proxy được đăng ký dưới bean name mà phần còn lại của ứng dụng sử dụng. Khi một phương thức được gọi, proxy hỏi cơ chế quản lý scope để lấy target tương ứng rồi chuyển lời gọi đến target đó.

Ví dụ:

```java
import org.springframework.context.annotation.ScopedProxyMode;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope
public class RequestInfo {
    // ...
}
```

`@RequestScope` là annotation chuyên biệt cho request scope. Mặc định, annotation này dùng class-based scoped proxy (`TARGET_CLASS`). Vì vậy, một singleton có thể inject tham chiếu `RequestInfo` mà không cần request target tồn tại ngay tại lúc singleton được tạo.

Với `@Scope` tổng quát, bạn có thể khai báo proxy mode rõ ràng:

```java
@Component
@Scope(
    value = WebApplicationContext.SCOPE_REQUEST,
    proxyMode = ScopedProxyMode.TARGET_CLASS
)
public class RequestInfo {
}
```

Hai ví dụ trên là hai cách khai báo thay thế nhau cho request-scoped bean. Không cần gắn cả `@RequestScope` và `@Scope` lên cùng một class.

### 3.1. `ScopedProxyMode` có những lựa chọn nào?

| Giá trị | Ý nghĩa |
| --- | --- |
| `DEFAULT` | Dùng giá trị mặc định được cấu hình cho component scan; trong nhiều cấu hình thông thường, mặc định là không tạo scoped proxy |
| `NO` | Không tạo scoped proxy |
| `INTERFACES` | Tạo proxy dựa trên interface mà target triển khai |
| `TARGET_CLASS` | Tạo proxy dựa trên class của target |

`@RequestScope` và `@SessionScope` có mặc định `TARGET_CLASS`, nhưng nếu dùng `@Scope` trực tiếp thì hãy chỉ rõ `proxyMode` khi cần. Ví dụ:

```java
@Scope(
    value = WebApplicationContext.SCOPE_REQUEST,
    proxyMode = ScopedProxyMode.TARGET_CLASS
)
```

## 4. Tham chiếu proxy và target object khác nhau thế nào?

Đây là phần cốt lõi của bài học.

### 4.1. Tham chiếu proxy

Giả sử một singleton giữ field:

```java
private final RequestInfo requestInfo;
```

Khi sử dụng scoped proxy, field `requestInfo` trỏ đến proxy. Proxy này thường được tạo và inject trong lúc singleton được khởi tạo. Tham chiếu đó có thể tồn tại suốt vòng đời của singleton.

### 4.2. Đối tượng đích

Target là instance thực tế của `RequestInfo` trong request đang hoạt động. Với request scope:

- Request A có target A.
- Request B có target B.
- Các lần truy cập trong cùng request thường nhận cùng target A hoặc B.
- Khi request kết thúc, target thuộc request đó hết vòng đời và được scope quản lý dọn dẹp theo lifecycle tương ứng.

### 4.3. Cùng một proxy có thể phục vụ nhiều target

```text
Singleton AuditService
       |
       | field requestInfo không đổi
       v
   [Proxy P]
       |
       +-- lời gọi trong request A --> [Target A]
       |
       +-- lời gọi trong request B --> [Target B]
       |
       +-- lời gọi trong request C --> [Target C]
```

Proxy P là tham chiếu ổn định mà singleton giữ. Target A, B, C là những instance khác nhau được chọn theo request hiện tại.

### 4.4. So sánh trực tiếp

| Khía cạnh | Tham chiếu proxy | Target object |
| --- | --- | --- |
| Vai trò | Trung gian chuyển lời gọi | Thực thi logic và giữ state theo scope |
| Ai giữ tham chiếu? | Bean dài hạn có thể giữ proxy | Scope quản lý target; proxy phân giải target khi gọi |
| Vòng đời | Thường dài bằng bean đang giữ proxy | Theo scope, ví dụ một HTTP request |
| Có đổi theo request? | Tham chiếu proxy thường không đổi | Target được chọn thay đổi theo request |
| Có thể gọi khi không có request? | Có thể giữ proxy, nhưng gọi method cần request target sẽ thất bại nếu scope không active | Không có target request hợp lệ |
| State | Không nên coi state của proxy là state nghiệp vụ của target | State thuộc instance thực tế trong scope |

Một cách nói ngắn gọn: **proxy là địa chỉ trung gian ổn định; target là đối tượng cụ thể mà địa chỉ đó phân giải tới trong scope hiện tại**.

## 5. Ví dụ đầy đủ: singleton service sử dụng request-scoped bean

Ví dụ sau dùng Spring Boot Web với embedded servlet server. Dự án cần dependency web phù hợp (`spring-boot-starter-web` trong các dòng Spring Boot quen thuộc) và cấu hình component scan bao phủ các package.

### 5.1. Request-scoped bean

`RequestInfo.java`:

```java
package com.example.demo.request;

import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope
public class RequestInfo {

    private final String requestId = UUID.randomUUID().toString();

    public String getRequestId() {
        return requestId;
    }
}
```

Spring tạo target `RequestInfo` cho mỗi HTTP request. `requestId` được khởi tạo khi target của request đó được tạo.

### 5.2. Singleton service giữ proxy

`AuditService.java`:

```java
package com.example.demo.service;

import com.example.demo.request.RequestInfo;
import org.springframework.stereotype.Service;

@Service
public class AuditService {

    private final RequestInfo requestInfo;

    public AuditService(RequestInfo requestInfo) {
        this.requestInfo = requestInfo;
    }

    public String currentRequestId() {
        return requestInfo.getRequestId();
    }
}
```

`AuditService` là singleton theo mặc định. Constructor nhận tham chiếu scoped proxy của `RequestInfo`. Trong mỗi lần gọi `currentRequestId()`, proxy phân giải target tương ứng với request hiện tại rồi gọi `getRequestId()`.

### 5.3. Controller gọi service

`RequestController.java`:

```java
package com.example.demo.web;

import com.example.demo.service.AuditService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RequestController {

    private final AuditService auditService;

    public RequestController(AuditService auditService) {
        this.auditService = auditService;
    }

    @GetMapping("/request-id")
    public String requestId() {
        return auditService.currentRequestId();
    }
}
```

Lớp main:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Gọi endpoint nhiều lần:

```bash
curl http://localhost:8080/request-id
curl http://localhost:8080/request-id
```

Ví dụ kết quả:

```text
f1c9bdb2-9a75-4d0f-9e5b-111111111111
7c2f19b0-2f12-4f23-8b3e-222222222222
```

Hai request độc lập có thể nhận hai ID khác nhau. Trong khi đó, `AuditService` vẫn là một singleton và field `requestInfo` vẫn giữ cùng tham chiếu proxy. Chính proxy đã phân giải đúng target theo từng request.

### 5.4. Vì sao constructor của singleton không lỗi?

Trong quá trình tạo `AuditService`, Spring không cần lấy ngay target request-scoped. Container có thể inject proxy vì proxy là object phù hợp với kiểu dependency được khai báo. Chỉ khi code gọi phương thức qua proxy trong một request đang hoạt động, target mới được phân giải.

Nếu bỏ scoped proxy và inject trực tiếp target request-scoped vào singleton, việc giải quyết dependency có thể đòi hỏi request scope khi chưa có request nào. Đây là nguyên nhân thường gặp của lỗi `ScopeNotActiveException`.

## 6. `TARGET_CLASS` và `INTERFACES`

Scoped proxy cần một kiểu có thể inject vào bean sử dụng. Spring hỗ trợ hai chiến lược phổ biến.

### 6.1. Class-based proxy (`TARGET_CLASS`)

Ví dụ:

```java
@Component
@RequestScope
public class RequestInfo {
    public String getRequestId() {
        return "...";
    }
}
```

Với mặc định của `@RequestScope`, Spring tạo proxy dựa trên class. Proxy là một lớp con tương thích với `RequestInfo`, do đó có thể inject vào constructor nhận `RequestInfo`.

Những giới hạn quan trọng của class-based proxy:

- Target class không thể là `final` nếu cần tạo subclass proxy.
- Phương thức `final` không thể được override để chặn theo cơ chế subclass.
- Phương thức `private` không thể được override.
- Nên tránh thiết kế API phụ thuộc vào việc gọi method không thể được proxy chặn.

### 6.2. Interface-based proxy (`INTERFACES`)

Nếu muốn công khai bean thông qua interface:

```java
package com.example.demo.request;

public interface RequestIdentity {
    String getRequestId();
}
```

Implementation:

```java
package com.example.demo.request;

import java.util.UUID;
import org.springframework.context.annotation.Scope;
import org.springframework.context.annotation.ScopedProxyMode;
import org.springframework.stereotype.Component;
import org.springframework.web.context.WebApplicationContext;

@Component
@Scope(
    value = WebApplicationContext.SCOPE_REQUEST,
    proxyMode = ScopedProxyMode.INTERFACES
)
public class DefaultRequestIdentity implements RequestIdentity {

    private final String requestId = UUID.randomUUID().toString();

    @Override
    public String getRequestId() {
        return requestId;
    }
}
```

Singleton sử dụng interface:

```java
@Service
public class AuditService {
    private final RequestIdentity requestIdentity;

    public AuditService(RequestIdentity requestIdentity) {
        this.requestIdentity = requestIdentity;
    }
}
```

JDK dynamic proxy triển khai interface được chỉ định. Vì vậy, nên inject `RequestIdentity`; không nên yêu cầu `DefaultRequestIdentity` nếu bean công khai chỉ là proxy interface.

### 6.3. So sánh

| Tiêu chí | `TARGET_CLASS` | `INTERFACES` |
| --- | --- | --- |
| Cơ chế thường dùng | Subclass proxy | JDK dynamic proxy |
| Cần interface? | Không | Có |
| Inject concrete class? | Có thể, nếu kiểu tương thích và không vi phạm giới hạn subclass | Không, nên inject interface |
| Giới hạn | Final class/method, private method không thể override | Chỉ expose interface; lời gọi qua interface |
| Phù hợp | Ứng dụng dùng concrete type và class không final | Thiết kế dựa trên interface |

Chọn proxy mode dựa trên API mà bean sử dụng cần công khai. Với code nghiệp vụ có interface rõ ràng, interface-based proxy có thể giúp giảm phụ thuộc vào implementation cụ thể.

## 7. Scoped proxy và các scope web khác

### 7.1. Request scope

```java
@Component
@RequestScope
public class RequestMetadata {
}
```

Target được gắn với HTTP request hiện tại. Những request khác nhau có target khác nhau. Đây là trường hợp điển hình khi singleton service cần truy cập thông tin request.

### 7.2. Session scope

```java
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
}
```

`@SessionScope` mặc định dùng class-based scoped proxy. Một proxy có thể được inject vào singleton `CartService`, nhưng target `ShoppingCart` được chọn theo HTTP session hiện tại. Những request thuộc cùng session có thể truy cập cùng một shopping cart target; những session khác nhau có target riêng.

Session-scoped state cần được thiết kế cẩn thận vì một session có thể gửi nhiều request đồng thời (ví dụ nhiều tab trình duyệt). Không nên mặc định rằng các request cùng session luôn chạy tuần tự.

### 7.3. Application scope

Application scope gắn target với servlet `ServletContext`. Nó không giống singleton Spring ở mọi khía cạnh: application scope thuộc web application context và có thể khác về phạm vi chia sẻ so với một bean singleton của một IoC container cụ thể.

### 7.4. Prototype scope

Prototype là một trường hợp cần chú ý. Khi dùng scoped proxy với prototype target, cơ chế target source có thể yêu cầu container lấy một prototype mới cho từng lần proxy phân giải target, thường là từng lời gọi phương thức qua proxy. Do đó, proxy không có nghĩa mọi lần gọi đều dùng cùng một prototype instance.

Nếu cần tạo một prototype object mới **một lần cho mỗi thao tác nghiệp vụ** và dùng object đó qua nhiều bước, hãy lấy object một lần bằng `ObjectProvider<T>.getObject()` rồi giữ biến cục bộ trong thao tác đó. Đừng giả định prototype scoped proxy tự giữ cùng target cho toàn bộ chuỗi method calls.

## 8. Khi nào proxy được phân giải thành target?

Với request-scoped bean, proxy thường không lấy target trong lúc constructor của singleton chạy. Target được lấy khi lời gọi method đi qua proxy và scope hiện tại có thể cung cấp target.

Luồng thực thi:

```text
HTTP request bắt đầu
        |
        v
Servlet request context được thiết lập
        |
        v
Controller gọi singleton service
        |
        v
Singleton gọi request-scoped proxy
        |
        v
Proxy yêu cầu request scope lấy target
        |
        v
Target của request hiện tại được tạo/lấy
        |
        v
Method được gọi trên target
        |
        v
Kết quả trả về qua proxy
        |
        v
HTTP request kết thúc, request scope được kết thúc
```

Nếu cùng request gọi proxy nhiều lần, request scope thường trả lại cùng target trong request đó. Nếu request khác gọi, proxy sẽ phân giải target tương ứng với request khác.

### 8.1. Gọi proxy khi scope không active

Ví dụ:

```java
@SpringBootApplication
public class DemoApplication implements CommandLineRunner {

    private final RequestInfo requestInfo;

    public DemoApplication(RequestInfo requestInfo) {
        this.requestInfo = requestInfo;
    }

    @Override
    public void run(String... args) {
        System.out.println(requestInfo.getRequestId());
    }
}
```

`CommandLineRunner` chạy sau khi application context khởi động, nhưng không phải trong một HTTP request. Constructor có thể nhận proxy thành công; đến khi gọi `getRequestId()`, Spring không tìm thấy request scope đang active và có thể ném `ScopeNotActiveException`.

Điều này không chứng minh proxy bị lỗi. Proxy đang hoạt động đúng: nó không thể cung cấp target request-scoped khi không có request hiện tại.

### 8.2. Background task và async execution

Không nên lấy request-scoped object rồi chuyển tham chiếu đó sang một background thread hoặc `@Async` task với giả định request scope vẫn hoạt động. Request context không tự động có mặt trong mọi thread. Khi task chạy sau khi request kết thúc, target có thể không còn hợp lệ.

Thay vì chuyển bean request-scoped, hãy đọc những giá trị cần thiết trong request thread và truyền **dữ liệu bất biến** sang task:

```java
public void submitAudit() {
    String requestId = requestInfo.getRequestId();
    backgroundExecutor.execute(() -> auditWriter.write(requestId));
}
```

Ví dụ này lấy request ID khi scope còn active rồi truyền một `String` sang task. `auditWriter` là dependency có scope phù hợp với background execution. Nếu cần propagation của security context hoặc tracing context, hãy dùng cơ chế propagation được thiết kế riêng cho loại context đó.

## 9. Scoped proxy khác gì với AOP proxy?

Hai loại proxy có thể cùng xuất hiện trong một ứng dụng, nhưng mục tiêu khác nhau:

| Khía cạnh | Scoped proxy | AOP proxy |
| --- | --- | --- |
| Mục đích chính | Chọn target theo scope hiện tại | Áp dụng advice quanh method invocation |
| Ví dụ | Request-scoped target trong singleton service | Transaction, cache, security, logging |
| Điều proxy làm | Tìm target phù hợp với scope rồi chuyển lời gọi | Chạy interceptor/advice rồi có thể gọi target |
| Target có thể đổi? | Có, theo request/session hoặc scope | Thường là target bean được proxy bọc, tùy target source |
| Có cần scope active? | Có nếu target thuộc web scope cần ngữ cảnh | Không nhất thiết; tùy advice và target |

Scoped proxy thường được xây trên hạ tầng proxy của Spring. Một bean cũng có thể tham gia nhiều cơ chế proxy; vì vậy khi debug, hãy xem mục đích của proxy và target source chứ đừng chỉ dựa vào tên runtime class.

Ví dụ, một request-scoped service có thể đồng thời cần transaction advice. Khi đó, việc phân giải target theo request và việc áp dụng transaction là hai trách nhiệm riêng. Cấu hình cụ thể của proxy và thứ tự interceptor phụ thuộc cách Spring đăng ký các post-processor và advisor.

## 10. Scoped proxy được đăng ký trong container như thế nào?

Khi Spring tạo scoped proxy, nó thường đăng ký:

1. Proxy dưới **bean name công khai** ban đầu, ví dụ `requestInfo`.
2. Target bean definition dưới tên nội bộ có tiền tố `scopedTarget.`, ví dụ `scopedTarget.requestInfo`.

Sơ đồ:

```text
BeanDefinitionRegistry
   |
   +-- "requestInfo"
   |       |
   |       +-- bean proxy được inject vào singleton
   |
   +-- "scopedTarget.requestInfo"
           |
           +-- target definition thuộc request scope
```

Đây là chi tiết triển khai nội bộ của Spring. Code nghiệp vụ nên inject và sử dụng bean theo tên công khai/kiểu interface bình thường. Không nên tự lấy `scopedTarget.requestInfo` để lưu vào singleton, vì làm vậy có thể bỏ qua cơ chế phân giải target theo scope.

### 10.1. Có thể xem proxy bằng cách nào?

Trong lúc debug, có thể kiểm tra kiểu runtime của bean công khai:

```java
Object bean = applicationContext.getBean(RequestInfo.class);
System.out.println(bean.getClass().getName());
```

Tên class có thể là tên proxy do Spring/JDK tạo. Đối với class-based proxy, nó thường có tên lớp con sinh tự động; với interface-based proxy, nó thường là JDK proxy.

Không nên gọi `getBean(RequestInfo.class)` ở một ngữ cảnh có nhiều bean cùng kiểu mà không có qualifier. Đoạn trên chỉ minh họa khi có đúng một ứng viên phù hợp.

### 10.2. Không nên giữ target reference trong bean singleton

Một số API hạ tầng cho phép unwrapping proxy hoặc truy xuất target trong những điều kiện cụ thể. Tuy nhiên, nếu lấy request target A rồi gán vào field singleton, field đó sẽ giữ object của request A và không tự chuyển sang target B ở request sau.

```java
// Không nên làm với request-scoped target:
private RequestInfo cachedTarget;
```

Proxy cần thực hiện việc phân giải target **ở mỗi lần sử dụng theo scope**. Tránh unwrap proxy rồi cache target trong bean có vòng đời dài hơn.

## 11. Dùng `ObjectProvider` hoặc `ObjectFactory` thay cho scoped proxy

Scoped proxy không phải lựa chọn duy nhất. Nếu muốn trì hoãn việc lấy target và chủ động kiểm soát thời điểm, bạn có thể inject provider.

### 11.1. `ObjectProvider<T>`

```java
package com.example.demo.service;

import com.example.demo.request.RequestInfo;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public class AuditService {

    private final ObjectProvider<RequestInfo> requestInfoProvider;

    public AuditService(ObjectProvider<RequestInfo> requestInfoProvider) {
        this.requestInfoProvider = requestInfoProvider;
    }

    public String currentRequestId() {
        RequestInfo requestInfo = requestInfoProvider.getObject();
        return requestInfo.getRequestId();
    }
}
```

`ObjectProvider` được inject an toàn vào singleton. Khi `getObject()` được gọi, Spring mới phân giải bean `RequestInfo` theo scope đang hoạt động. Với request scope, lời gọi này cần được thực hiện trong một HTTP request.

Khác với scoped proxy:

- Provider là một dependency factory/lookup mà code gọi rõ ràng.
- Scoped proxy cho phép code sử dụng bean như một dependency thông thường.
- Provider hữu ích khi muốn quyết định rõ lúc nào cần target hoặc muốn kiểm tra khả năng tồn tại bằng các API như `getIfAvailable()`.

### 11.2. `ObjectFactory<T>`

`ObjectFactory<T>` là abstraction đơn giản để lấy object khi cần:

```java
private final ObjectFactory<RequestInfo> requestInfoFactory;

public AuditService(ObjectFactory<RequestInfo> requestInfoFactory) {
    this.requestInfoFactory = requestInfoFactory;
}

public String currentRequestId() {
    return requestInfoFactory.getObject().getRequestId();
}
```

`ObjectProvider` mở rộng `ObjectFactory` với thêm nhiều tiện ích. Trong code Spring hiện đại, `ObjectProvider` thường được chọn khi cần khả năng lookup linh hoạt hơn.

### 11.3. So sánh scoped proxy và provider

| Tiêu chí | Scoped proxy | `ObjectProvider<T>` |
| --- | --- | --- |
| Cách sử dụng | Gọi method trực tiếp trên dependency được inject | Gọi `getObject()` để lấy bean |
| Khi resolve target | Khi lời gọi đi qua proxy | Khi gọi `getObject()` |
| Code nghiệp vụ | Trong suốt hơn, không cần biết proxy | Thể hiện rõ việc lookup |
| Kiểm soát thời điểm lấy bean | Theo method invocation qua proxy | Do code chủ động quyết định |
| Phù hợp | Muốn inject bean scope ngắn vào bean scope dài | Muốn trì hoãn lookup hoặc tạo target đúng một lần trong một thao tác |

### 11.4. Lấy prototype một lần cho một công việc

Ví dụ một singleton cần tạo một `JobContext` mới cho từng lần xử lý:

```java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class JobContext {
    private final String jobId = UUID.randomUUID().toString();

    public String getJobId() {
        return jobId;
    }
}
```

Service:

```java
@Service
public class JobService {
    private final ObjectProvider<JobContext> jobContexts;

    public JobService(ObjectProvider<JobContext> jobContexts) {
        this.jobContexts = jobContexts;
    }

    public void process() {
        JobContext context = jobContexts.getObject();
        validate(context);
        execute(context);
        finish(context);
    }

    private void validate(JobContext context) {
        System.out.println("Validate " + context.getJobId());
    }

    private void execute(JobContext context) {
        System.out.println("Execute " + context.getJobId());
    }

    private void finish(JobContext context) {
        System.out.println("Finish " + context.getJobId());
    }
}
```

Trong mỗi lần `process()`, service lấy một prototype object và truyền cùng reference qua các bước của công việc. Cách này diễn đạt rõ yêu cầu “một instance cho một lần xử lý”.

## 12. Kiểm thử scoped bean

Request scope cần một web request context. Unit test tạo service bằng `new` không tự cung cấp HTTP request, nên khi gọi scoped proxy có thể gặp lỗi scope không active.

### 12.1. Test qua HTTP request với `MockMvc`

Với Spring Boot Test và Spring MVC Test phù hợp:

```java
@SpringBootTest
@AutoConfigureMockMvc
class RequestScopeIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void eachRequestHasItsOwnRequestId() throws Exception {
        String first = mockMvc.perform(get("/request-id"))
                .andReturn()
                .getResponse()
                .getContentAsString();

        String second = mockMvc.perform(get("/request-id"))
                .andReturn()
                .getResponse()
                .getContentAsString();

        assertThat(first).isNotBlank();
        assertThat(second).isNotBlank();
        assertThat(first).isNotEqualTo(second);
    }
}
```

Test giả định có endpoint `/request-id` như ví dụ trước, `MockMvc` được cấu hình và các import static của MockMvc/AssertJ đã được thêm. Mỗi lần `perform` mô phỏng một request riêng, vì vậy request-scoped target được phân giải theo request tương ứng.

### 12.2. Test nhiều lần truy cập trong cùng request

Bạn có thể tạo endpoint trả cùng request ID hai lần:

```java
@GetMapping("/request-id/twice")
public List<String> requestIdTwice() {
    return List.of(
        auditService.currentRequestId(),
        auditService.currentRequestId()
    );
}
```

Hai giá trị trong cùng request thường giống nhau vì cùng request scope cung cấp cùng target. Hai HTTP request độc lập có thể có ID khác nhau.

### 12.3. Unit test singleton service với provider/proxy

Nếu test service trực tiếp bằng constructor, hãy cung cấp dependency giả hoặc mock phù hợp. Không nên kỳ vọng request-scoped proxy thật hoạt động khi test không thiết lập request context.

Với `ObjectProvider`, có thể mock provider để trả về một `RequestInfo` test. Với integration test, dùng web test context để kiểm tra tương tác thật giữa singleton, proxy và request scope.

## 13. Những lỗi thường gặp và cách xử lý

### 13.1. `ScopeNotActiveException`

Thông báo có thể nói request scope chưa active hoặc không có request hiện tại.

Nguyên nhân phổ biến:

- Gọi request-scoped proxy trong `CommandLineRunner`.
- Gọi proxy từ scheduled job hoặc background thread.
- Unit test gọi bean mà không thiết lập request context.
- Công việc bất đồng bộ tiếp tục sau khi HTTP request đã kết thúc.

Hướng xử lý:

1. Xác định lời gọi có thực sự nằm trong request/session scope không.
2. Nếu chỉ cần dữ liệu request, đọc dữ liệu trong request thread rồi truyền giá trị bất biến sang background task.
3. Nếu cần trì hoãn lấy bean, dùng `ObjectProvider` nhưng vẫn chỉ gọi khi scope active.
4. Với test, thiết lập web request context hoặc kiểm thử qua `MockMvc`.

### 13.2. `BeanCreationException` hoặc không tạo được proxy

Có thể class-based proxy không tạo được do target class `final`, constructor/kiểu không phù hợp hoặc cấu hình proxy không tương thích. Kiểm tra `proxyMode`, class/interface mà bean expose và giới hạn của loại proxy được dùng.

Nếu có interface ổn định, cân nhắc `ScopedProxyMode.INTERFACES` và inject qua interface.

### 13.3. Inject concrete class thất bại với interface proxy

Nếu scoped proxy chỉ triển khai interface, constructor nên nhận interface:

```java
public AuditService(RequestIdentity requestIdentity) {
    this.requestIdentity = requestIdentity;
}
```

Không yêu cầu implementation class cụ thể khi object được công khai là JDK dynamic proxy.

### 13.4. Dữ liệu request bị dùng nhầm giữa các request

Kiểm tra xem ứng dụng có:

- Lưu target request-scoped vào field của singleton.
- Dùng một static variable cho dữ liệu request.
- Chia sẻ mutable state không đúng scope.
- Truyền reference của request target sang thread khác.

Giữ proxy trong singleton và đọc target thông qua proxy trong request hiện tại. Nếu cần chuyển dữ liệu ra ngoài request, chỉ truyền các giá trị cần thiết.

### 13.5. Dùng session-scoped bean như thể nó luôn an toàn luồng

Một HTTP session có thể có nhiều request đồng thời. Session scope đảm bảo target gắn với session, nhưng **không tự đảm bảo thread safety** cho mutable state bên trong `ShoppingCart`. Hãy thiết kế thao tác cập nhật, đồng bộ và lưu trữ dữ liệu phù hợp.

## 14. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Inject proxy nghĩa là singleton giữ target của request đầu tiên.” | Singleton giữ proxy; target được phân giải theo scope khi gọi |
| “Proxy và target là cùng một object.” | Proxy là object trung gian; target là object thực thi logic theo scope |
| “Scoped proxy làm request bean tồn tại suốt ứng dụng.” | Target vẫn tuân theo request/session scope |
| “Có proxy thì gọi ở đâu cũng được.” | Method cần target chỉ hoạt động khi scope tương ứng active |
| “`@RequestScope` là singleton.” | Mỗi request có target riêng; proxy được chia sẻ có thể có vòng đời dài hơn |
| “Mọi bean đều cần scoped proxy.” | Proxy chỉ cần khi một dependency scope ngắn cần được tham chiếu từ context dài hơn hoặc có nhu cầu lookup tương ứng |
| “`@Order` hoặc AOP proxy thay thế scoped proxy.” | Chúng giải quyết các vấn đề khác nhau |
| “Prototype proxy luôn giữ một target qua nhiều lần gọi.” | Prototype lookup có thể tạo target mới qua từng lần phân giải; muốn một target cho một công việc, hãy lấy một lần bằng provider |
| “Session scope tự bảo vệ dữ liệu khỏi truy cập đồng thời.” | Scope không tự cung cấp thread safety cho state mutable |

## 15. Bài thực hành

### Bài 1 — Quan sát cùng proxy, khác target

Tạo `RequestInfo` có `@RequestScope` và field `requestId` được tạo từ `UUID.randomUUID()`. Inject nó vào singleton `AuditService`, sau đó tạo endpoint `/request-id`.

Gửi hai HTTP request độc lập và ghi lại:

- `AuditService` có được tạo lại mỗi lần không?
- Request ID có thay đổi không?
- Field `requestInfo` trong `AuditService` có phải được inject lại không?

Giải thích vai trò của proxy và target trong kết quả.

### Bài 2 — Hai lần gọi trong cùng request

Tạo endpoint gọi `auditService.currentRequestId()` hai lần rồi trả hai kết quả trong cùng response. So sánh hai ID và giải thích tại sao request scope cung cấp cùng target trong cùng một request.

### Bài 3 — Bỏ scoped proxy

Đổi request bean thành:

```java
@Scope(
    value = WebApplicationContext.SCOPE_REQUEST,
    proxyMode = ScopedProxyMode.NO
)
```

Giữ nguyên constructor injection vào singleton `AuditService`. Quan sát quá trình khởi động và giải thích vì sao container không thể cung cấp trực tiếp một request target khi chưa có request.

### Bài 4 — Thử interface proxy

Tạo interface `RequestIdentity`, cho implementation request-scoped triển khai interface và bật `proxyMode = ScopedProxyMode.INTERFACES`. Inject interface vào singleton. So sánh kiểu runtime và giải thích vì sao inject implementation class không phù hợp.

### Bài 5 — So sánh với `ObjectProvider`

Thay field `RequestInfo` bằng `ObjectProvider<RequestInfo>`. Gọi `getObject()` bên trong phương thức được controller gọi. So sánh cách viết với scoped proxy và nêu khi nào provider giúp code rõ ràng hơn.

### Bài 6 — Không chuyển target sang background thread

Tạo một background task chạy sau khi request kết thúc. Thử truyền trực tiếp proxy hoặc target request-scoped vào task và quan sát lỗi có thể xảy ra. Sau đó sửa bằng cách lấy `requestId` trong request thread rồi truyền một `String` vào task.

## 16. Ghi nhớ

**Scoped proxy là tham chiếu trung gian ổn định; target object là instance thực tế được chọn theo scope đang hoạt động.** Một singleton có thể giữ proxy của request-scoped bean, nhưng mỗi HTTP request vẫn có target riêng. Khi lời gọi đi qua proxy, Spring tìm target phù hợp rồi chuyển tiếp method invocation.

Hãy phân biệt rõ proxy với target, chọn `TARGET_CLASS` hoặc `INTERFACES` theo kiểu bean được expose, và chỉ gọi request/session scoped dependency khi scope tương ứng đang active. Nếu cần chủ động lấy target vào một thời điểm cụ thể, `ObjectProvider<T>` là một lựa chọn phù hợp. Đặc biệt, không lưu target ngắn hạn vào singleton và không truyền request-scoped object sang background thread như thể nó còn thuộc request ban đầu.

Nắm được sự khác nhau giữa tham chiếu proxy và đối tượng đích sẽ giúp bạn sử dụng request scope, session scope, dependency injection và các cơ chế proxy trong Spring Boot một cách an toàn, dễ dự đoán hơn.

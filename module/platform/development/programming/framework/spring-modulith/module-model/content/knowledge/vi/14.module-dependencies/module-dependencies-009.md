# Static model khác hành vi runtime ra sao?

Trong Spring Modulith, mô hình module tĩnh mô tả cấu trúc và các quan hệ phụ thuộc có thể suy ra từ mã nguồn, package và metadata của ứng dụng. Hành vi runtime mô tả những gì thực sự xảy ra khi Spring tạo `ApplicationContext`, khởi tạo bean, xử lý request, phát sự kiện và thực thi giao dịch. Hai góc nhìn liên quan chặt chẽ nhưng trả lời những câu hỏi khác nhau.

Hiểu rõ ranh giới này giúp đọc đúng kết quả `ApplicationModules.verify()`, thiết kế kiểm thử kiến trúc và bổ sung kiểm thử tích hợp cho những hành vi chỉ xuất hiện khi ứng dụng chạy.

## 1. Mô hình tĩnh mô tả điều gì?

Spring Modulith có thể phân tích codebase để tạo một biểu diễn trong bộ nhớ về cách ứng dụng được chia thành module. Điểm bắt đầu thường là lớp Spring Boot chính:

```java
ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

modules.forEach(System.out::println);
```

`ApplicationModules` sử dụng package của lớp ứng dụng, cấu trúc package, các kiểu Java và metadata liên quan để xác định module, API được công khai và những quan hệ phụ thuộc có thể phát hiện. Theo mặc định, các package con trực tiếp của package chứa lớp ứng dụng được xem là module; các cấu hình như `@ApplicationModule`, named interface và `allowedDependencies` điều chỉnh cách mô hình được hình thành.

Mô hình này có thể trả lời những câu hỏi kiến trúc như:

- Ứng dụng có những module nào và package gốc của mỗi module ở đâu?
- Module nào tham chiếu API hoặc kiểu dữ liệu được công khai bởi module khác?
- Module nào đang phụ thuộc vào package nội bộ mà module khác không công khai?
- Các quan hệ phụ thuộc có tạo thành chu trình hay vi phạm `allowedDependencies` không?
- Một module có khai báo đúng những named interface mà module khác được phép sử dụng không?

`ApplicationModules.verify()` kiểm tra các quy tắc kiến trúc trên mô hình đã phân tích. Những quy tắc chính gồm không có chu trình ở cấp module, chỉ truy cập API package được phép của module khác và tuân thủ các phụ thuộc đã khai báo khi sử dụng `allowedDependencies`.

```java
class ModuleArchitectureTests {

    @Test
    void verifiesModuleArrangement() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Đây là kiểm tra cấu trúc mã. Nó không cần gửi request HTTP, chạy toàn bộ nghiệp vụ, kết nối tới database hay thực thi từng nhánh điều kiện để xác định module phụ thuộc nhau ra sao.

## 2. Hành vi runtime mô tả điều gì?

Runtime bắt đầu khi ứng dụng được khởi động. Spring Boot tạo `ApplicationContext`, đánh giá các điều kiện cấu hình, đăng ký bean, áp dụng proxy và khởi tạo những thành phần cần thiết. Sau đó, request, message hoặc application event có thể kích hoạt các phương thức cụ thể.

Hành vi runtime phụ thuộc vào những yếu tố mà mô hình tĩnh không thể khẳng định chỉ từ một cạnh phụ thuộc:

- Profile, property và điều kiện như `@Profile`, `@ConditionalOnProperty` quyết định bean nào thực sự được đăng ký.
- Luồng xử lý quyết định phương thức nào được gọi, theo thứ tự nào và trong điều kiện nào.
- Proxy của Spring áp dụng transaction, security, caching hoặc retry tại thời điểm gọi.
- Application event chỉ được xử lý khi được phát hành và listener phù hợp được kích hoạt.
- Async execution, transaction commit, lỗi listener và retry ảnh hưởng đến kết quả thực tế.
- Database, HTTP service, message broker và các hệ thống ngoài có trạng thái, độ trễ và lỗi riêng.

Vì vậy, có một cạnh phụ thuộc trong mô hình tĩnh không có nghĩa phương thức ở module đích sẽ được gọi trong mọi lần chạy. Ngược lại, một tương tác được tạo động qua reflection, tra cứu bean bằng tên hoặc giao tiếp với hệ thống ngoài có thể không hiện thành cạnh phụ thuộc Java thông thường trong mô hình.

## 3. So sánh hai góc nhìn

| Khía cạnh | Mô hình module tĩnh | Hành vi runtime |
|---|---|---|
| Dữ liệu đầu vào | Package, bytecode, kiểu, annotation và metadata | `ApplicationContext`, bean instance, cấu hình đang hoạt động và dữ liệu thực tế |
| Câu hỏi chính | Code được phép phụ thuộc vào module nào? | Khi chạy, thành phần nào thực sự được tạo và tương tác? |
| Quan hệ | Quan hệ kiến trúc suy ra từ cấu trúc và tham chiếu | Lời gọi phương thức, event delivery, transaction và tương tác hệ thống |
| Điều kiện | Không thực thi toàn bộ nhánh điều kiện nghiệp vụ | Phụ thuộc profile, property, điều kiện bean và luồng xử lý |
| Thời điểm kiểm tra | Thường ở test hoặc build; có thể kiểm tra lại khi startup | Khi tạo context và trong quá trình ứng dụng hoạt động |
| Công cụ phù hợp | `ApplicationModules`, `verify()`, kiểm thử kiến trúc | Spring integration test, module integration test, kiểm thử event và quan sát runtime |
| Giới hạn | Không chứng minh nghiệp vụ chạy đúng hoặc hệ thống ngoài sẵn sàng | Một lần chạy hoặc một bộ test không bao phủ mọi đường đi và mọi cấu hình |

Không nên dùng một góc nhìn để thay thế hoàn toàn góc nhìn còn lại. Mô hình tĩnh giúp giữ ranh giới kiến trúc ổn định; kiểm thử và quan sát runtime xác nhận các thành phần thực sự phối hợp đúng khi ứng dụng hoạt động.

## 4. Ví dụ: phụ thuộc bean trực tiếp

Giả sử module `orders` gọi module `inventory` thông qua một Spring bean:

```java
package com.acme.shop.orders;

import com.acme.shop.inventory.InventoryManagement;
import org.springframework.stereotype.Service;

@Service
class OrderManagement {

    private final InventoryManagement inventory;

    OrderManagement(InventoryManagement inventory) {
        this.inventory = inventory;
    }

    void complete(Order order) {
        inventory.reserve(order.getProductId(), order.getQuantity());
    }
}
```

Nếu `InventoryManagement` là kiểu được công khai từ module `inventory`, mô hình có thể ghi nhận quan hệ `orders` phụ thuộc `inventory`. Đây là một quan hệ kiến trúc cần được xem xét ngay cả khi phương thức `complete()` chỉ được gọi trong một luồng hiếm gặp.

Khi chạy, Spring phải cung cấp một bean phù hợp cho constructor. Nếu bean bị loại khỏi context bởi profile hoặc điều kiện cấu hình, ứng dụng có thể không khởi động được. Nếu bean được tạo thành công, lời gọi `reserve()` chỉ xảy ra khi luồng thực thi đi tới `complete()`.

Như vậy, mô hình tĩnh cho biết sự phụ thuộc tồn tại trong code; runtime quyết định bean có được tạo và lời gọi có thực sự xảy ra hay không.

## 5. Ví dụ: event làm đảo chiều giữa phụ thuộc và luồng xử lý

Event giúp module phát sự kiện mà không cần biết module nào sẽ tiếp nhận. Xét module `orders` công bố event `OrderCompleted` trong API của mình:

```java
package com.acme.shop.orders;

import java.util.UUID;

public record OrderCompleted(UUID orderId) {
}
```

Module `orders` phát event sau khi hoàn tất thay đổi trạng thái đơn hàng:

```java
package com.acme.shop.orders;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderManagement {

    private final ApplicationEventPublisher events;

    OrderManagement(ApplicationEventPublisher events) {
        this.events = events;
    }

    @Transactional
    void complete(Order order) {
        order.complete();
        events.publishEvent(new OrderCompleted(order.getId()));
    }
}
```

Module `inventory` lắng nghe event đó:

```java
package com.acme.shop.inventory;

import com.acme.shop.orders.OrderCompleted;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class InventoryOnOrderCompleted {

    @ApplicationModuleListener
    void on(OrderCompleted event) {
        // Cập nhật tồn kho cho đơn hàng đã hoàn tất.
    }
}
```

Ví dụ này cho thấy hai hướng cần phân biệt:

1. **Hướng phụ thuộc trong mô hình tĩnh:** `inventory` tham chiếu kiểu `OrderCompleted` do `orders` công khai, nên `inventory` phụ thuộc vào hợp đồng event của `orders`.
2. **Hướng luồng sự kiện khi chạy:** `orders` phát `OrderCompleted`, sau đó listener trong `inventory` nhận và xử lý event.

```text
Mô hình phụ thuộc tĩnh:
inventory ───── phụ thuộc kiểu OrderCompleted ─────> orders

Luồng event runtime:
orders ───── publish OrderCompleted ─────> inventory listener
```

Mũi tên trong hai dòng biểu diễn hai khái niệm khác nhau. Mũi tên thứ nhất chỉ module có tham chiếu tới hợp đồng của module nào. Mũi tên thứ hai chỉ nơi phát và nơi nhận event. Nếu đọc dependency graph như một sơ đồ tuần tự runtime, ta có thể kết luận sai hướng phụ thuộc.

`@ApplicationModuleListener` là cách khai báo listener theo mô hình tích hợp module của Spring Modulith. Annotation này kết hợp xử lý bất đồng bộ, listener gắn với transaction và một transaction riêng cho listener. Event Publication Registry có thể ghi nhận publication cho các listener giao dịch, đánh dấu hoàn tất khi xử lý thành công và giữ lại publication chưa hoàn tất để phục vụ cơ chế khôi phục phù hợp.

Một event được khai báo không có nghĩa listener đã xử lý thành công. Runtime còn phụ thuộc vào transaction của bên phát, thời điểm commit, cấu hình async, listener có được đăng ký hay không, lỗi trong listener và cấu hình lưu publication.

## 6. `verify()` và runtime verifier có vai trò khác nhau

Lệnh sau thường được dùng trong kiểm thử kiến trúc:

```java
ApplicationModules.of(ShopApplication.class).verify();
```

Nó phân tích codebase và báo lỗi nếu cấu trúc module vi phạm các quy tắc đã bật. Lệnh này không tự khởi động một Spring `ApplicationContext` đầy đủ và không xác nhận mọi bean có thể khởi tạo trong môi trường triển khai.

Spring Modulith cũng cung cấp runtime support thông qua dependency `spring-modulith-runtime`. Khi bật `spring.modulith.runtime.verification-enabled=true`, `RuntimeApplicationModuleVerifier` có thể kiểm tra cách sắp xếp module trong lúc ứng dụng khởi động và làm ứng dụng dừng nếu phát hiện vi phạm. Cấu hình này đưa việc xác minh kiến trúc vào startup, nhưng bản chất kiểm tra vẫn dựa trên mô hình module và các quy tắc kiến trúc.

Ví dụ Gradle:

```groovy
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-runtime'
}
```

Ví dụ `application.properties`:

```properties
spring.modulith.runtime.verification-enabled=true
```

Runtime support còn có `ApplicationModuleInitializer`. Spring Modulith chạy các initializer theo thứ tự dựa trên cấu trúc phụ thuộc module. Thứ tự khởi tạo này sử dụng dependency model để điều phối startup; nó không phải bản ghi về thứ tự các phương thức nghiệp vụ được gọi trong suốt vòng đời ứng dụng.

## 7. Chọn loại kiểm tra phù hợp

| Mục tiêu | Cách kiểm tra nên dùng | Điều cần xác nhận |
|---|---|---|
| Không cho module truy cập package nội bộ | `ApplicationModules.of(...).verify()` | Mô hình không có vi phạm quyền truy cập |
| Ngăn chu trình phụ thuộc | Kiểm thử kiến trúc | Dependency graph ở cấp module là đồ thị có hướng không chu trình |
| Giới hạn module được phép phụ thuộc | `allowedDependencies` và `verify()` | Mọi cạnh đều nằm trong danh sách được phép |
| Kiểm tra bean được tạo theo profile | Spring integration test với profile tương ứng | Context khởi tạo thành công và bean mong đợi tồn tại |
| Kiểm tra luồng gọi service | Integration test gọi use case thực tế | Kết quả nghiệp vụ và tương tác giữa các bean đúng |
| Kiểm tra event listener | Module integration test phát event và xác nhận kết quả sau xử lý | Listener được đăng ký, transaction được commit và xử lý hoàn tất |
| Kiểm tra khôi phục event lỗi | Kiểm thử Event Publication Registry | Publication lỗi hoặc chưa hoàn tất được quan sát và xử lý theo chính sách |
| Tìm hiểu tương tác khi ứng dụng đang chạy | Runtime observability và tracing | Luồng tương tác thực tế, thời gian xử lý và lỗi phát sinh |

Với module integration test, Spring Modulith hỗ trợ `@ApplicationModuleTest` để khởi động phạm vi module cần kiểm tra. Đây là lớp kiểm tra bổ sung cho `verify()`: test có thể quan sát bean và tương tác thực trong Spring context. Khi kiểm tra `@ApplicationModuleListener`, cần thiết kế test phù hợp với thời điểm commit transaction và xử lý bất đồng bộ; chỉ publish event rồi assert ngay có thể tạo ra kết quả không ổn định.

## 8. Quy trình kết hợp hai góc nhìn

Một quy trình thực tế có thể tiến hành theo thứ tự sau:

1. **Xác định ranh giới:** dùng `ApplicationModules.of(ShopApplication.class)` để xem các module, package API và phụ thuộc được phát hiện.
2. **Đặt quy tắc:** khai báo named interface và `allowedDependencies` để giới hạn hợp đồng giữa các module.
3. **Khóa kiến trúc:** chạy `verify()` trong test hoặc build để phát hiện truy cập nội bộ, phụ thuộc ngoài danh sách và chu trình.
4. **Kiểm tra context:** viết integration test cho các profile và cấu hình quan trọng để xác nhận bean thực sự được đăng ký.
5. **Kiểm tra tương tác:** kiểm thử lời gọi service, event, transaction và các kết quả quan sát được ở runtime.
6. **Theo dõi khi triển khai:** dùng log, metric, trace và Event Publication Registry khi phù hợp để tìm các tương tác hoặc lỗi chỉ xuất hiện trong môi trường thật.

Nếu một kiểm thử tĩnh thất bại, hãy sửa cấu trúc hoặc hợp đồng module trước khi thêm ngoại lệ. Nếu mô hình tĩnh hợp lệ nhưng runtime thất bại, hãy kiểm tra cấu hình Spring, điều kiện tạo bean, transaction, async execution và các phụ thuộc bên ngoài. Cách phân loại này giúp xác định đúng lớp vấn đề.

## 9. Những kết luận không nên rút ra

- **“`verify()` thành công nghĩa là ứng dụng chạy được.”** Không đúng. Nó xác nhận các quy tắc kiến trúc được kiểm tra, không xác nhận toàn bộ Spring context, database hoặc hệ thống ngoài.
- **“Có cạnh phụ thuộc nghĩa là module đích luôn được gọi.”** Không đúng. Cạnh thể hiện quan hệ được suy ra từ code và metadata; lời gọi còn phụ thuộc đường thực thi.
- **“Không có cạnh nghĩa là runtime không thể tương tác.”** Không chắc chắn. Reflection, tra cứu bean động, message broker và HTTP có thể tạo tương tác không được biểu diễn như tham chiếu kiểu Java trực tiếp.
- **“Runtime verifier kiểm thử mọi luồng nghiệp vụ.”** Không đúng. Runtime verifier kiểm tra module arrangement trong lúc startup; integration test và quan sát runtime vẫn cần thiết.
- **“Event flow và dependency direction luôn cùng chiều.”** Không đúng. Listener thường phụ thuộc vào kiểu event được module phát công khai, trong khi event chạy từ publisher tới listener.

Khi đọc một dependency graph, hãy luôn xác định nó đang mô tả quan hệ phụ thuộc kiến trúc hay luồng thực thi. Sau đó dùng đúng loại kiểm tra để xác nhận điều mà mô hình đó không thể chứng minh.

## Tài liệu tham khảo

- [Spring Modulith – Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith – Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith – Runtime Support](https://docs.spring.io/spring-modulith/reference/runtime.html)
- [Spring Modulith – Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html)
- [ApplicationModuleListener API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/ApplicationModuleListener.html)

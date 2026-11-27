# Module Canvas và thông tin cần hiển thị

Application Module Canvas là bản tóm tắt có cấu trúc về một Spring Modulith application module. Canvas giúp người đọc nhanh chóng biết module sở hữu package nào, cung cấp những Spring component nào, có aggregate root nào, phát và lắng nghe event gì, đồng thời công khai các configuration properties nào. Spring Modulith tạo canvas từ mô hình `ApplicationModules`, vì vậy nội dung phản ánh cấu trúc và metadata mà framework nhận diện được trong codebase.

Canvas bổ sung cho sơ đồ component C4/UML. Sơ đồ cho thấy các module liên hệ với nhau ra sao; canvas tập trung vào những thành phần quan trọng bên trong từng module. Khi được tạo cùng `Documenter`, hai loại tài liệu giúp người đọc hiểu cả ranh giới module lẫn trách nhiệm và hợp đồng mà module thể hiện.

Trong phạm vi **SPRING_MODULITH_MODULE_MODEL**, Module Canvas hỗ trợ nhóm mô tả ranh giới nghiệp vụ, API công khai và dependency trong modular monolith. Canvas là tài liệu kỹ thuật được sinh từ model; nhóm vẫn cần xem lại ý nghĩa nghiệp vụ và bảo đảm các metadata cần thiết đã được khai báo.

## 1. Module Canvas là gì?

Module Canvas là bảng mô tả một application module. Nó tập hợp các thông tin Spring Modulith có thể suy ra từ package, Spring bean, repository, event type, listener và metadata configuration properties.

Một canvas điển hình có các nhóm thông tin:

| Nhóm | Thông tin thể hiện |
|---|---|
| Base package | Package gốc thuộc về application module |
| Spring components | Các bean được nhận diện, phân nhóm theo stereotype như service, repository, event listener và các thành phần khác |
| Aggregate roots | Các entity được nhận diện là aggregate root, ví dụ entity có repository hoặc được khai báo bằng jMolecules |
| Published events | Các application event mà module công bố |
| Events listened to | Các event mà component trong module đăng ký lắng nghe |
| Configuration properties | Các Spring Boot configuration properties được expose bởi module |

Canvas không phải danh sách mọi class trong module. Nó tập trung vào các loại thành phần có ý nghĩa đối với kiến trúc module. Các class helper, mapper hoặc implementation không được xem là API có thể không xuất hiện trong canvas mặc định.

## 2. Base package xác định phạm vi module

Base package là package nền mà Spring Modulith dùng để nhận diện application module. Ví dụ:

```text
com.acme.shop.inventory
├── InventoryManagement.java
├── api
│   ├── package-info.java
│   └── InventoryOperations.java
├── internal
│   ├── InventoryRepository.java
│   └── InventoryPolicy.java
└── events
    ├── package-info.java
    └── InventoryReserved.java
```

Canvas của module `inventory` hiển thị base package `com.acme.shop.inventory`. Package nền giúp người đọc liên hệ nội dung canvas với cấu trúc source code và hiểu phạm vi sở hữu của module.

Base package không phải display name hoặc logical identifier. Identifier được dùng để tham chiếu module trong dependency rules; base package xác định vị trí mã nguồn. Nếu module đổi identifier nhưng giữ nguyên package, base package trong canvas vẫn không đổi.

## 3. Spring components được phân nhóm theo stereotype

Canvas liệt kê các Spring bean mà module expose và nhóm chúng theo vai trò. Các grouping mặc định của `Documenter.CanvasOptions` nhận diện stereotype của Spring Framework và jMolecules khi các thư viện tương ứng có mặt trên classpath.

Các nhóm thường gặp:

| Nhóm | Ví dụ | Vai trò |
|---|---|---|
| Services | `InventoryManagement` | Điều phối use case hoặc cung cấp hành vi nghiệp vụ |
| Repositories | `InventoryRepository` | Truy cập và lưu trữ aggregate/entity |
| Event listeners | `InventoryOrderEventListener` | Phản ứng với application event từ module khác hoặc từ chính module |
| Others | `InventoryItemCreationListener`, component chuyên biệt khác | Bean được nhận diện nhưng không thuộc grouping mặc định cụ thể hơn |

Ví dụ, một service được đánh dấu bằng Spring `@Service`:

```java
package com.acme.shop.inventory;

import org.springframework.stereotype.Service;

@Service
public class InventoryManagement {

    public boolean isAvailable(String sku) {
        // Kiểm tra tồn kho.
        return true;
    }
}
```

`Documenter` có thể nhận diện Spring stereotype và đưa bean vào nhóm Services. Nếu dự án dùng stereotype jMolecules như `@Service`, `@Repository` hoặc các vai trò kiến trúc khác, các grouping tương ứng cũng có thể được áp dụng.

Canvas mặc định tập trung vào các Spring bean được expose trong package gốc hoặc named interface của module. Component nội bộ có thể được ẩn trong cấu hình mặc định; khi cần xem chi tiết implementation, có thể dùng `revealInternals()`.

## 4. Aggregate roots cho biết module sở hữu dữ liệu nghiệp vụ nào

Canvas có thể hiển thị các exposed aggregate roots. Spring Modulith nhận diện aggregate root dựa trên entity có repository tương ứng hoặc được khai báo rõ là aggregate bằng jMolecules.

Ví dụ, module `inventory` có entity `InventoryItem` và repository:

```java
package com.acme.shop.inventory;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class InventoryItem {

    @Id
    private String sku;

    private int availableQuantity;

    protected InventoryItem() {}

    public boolean hasAvailableStock() {
        return availableQuantity > 0;
    }
}
```

Repository của entity:

```java
package com.acme.shop.inventory;

import org.springframework.data.repository.Repository;

public interface InventoryItemRepository extends Repository<InventoryItem, String> {
}
```

Entity có repository có thể được nhận diện như aggregate root để canvas phản ánh dữ liệu nghiệp vụ mà module sở hữu. jMolecules cũng cho phép khai báo aggregate tường minh bằng stereotype tương ứng.

Việc một entity xuất hiện trong canvas không thay thế việc thiết kế aggregate boundary. Nhóm vẫn cần xác định invariant, transaction boundary và hành vi nghiệp vụ của aggregate. Canvas chỉ trình bày kết quả nhận diện từ code và metadata.

## 5. Published events cho biết module công bố điều gì

Canvas có thể liệt kê các application event được module công bố. Để Spring Modulith nhận diện event là domain/application event được công bố, event type cần được đánh dấu bằng jMolecules `@DomainEvent` hoặc triển khai interface `DomainEvent`.

Ví dụ dùng interface `DomainEvent`:

```java
package com.acme.shop.inventory.events;

import org.jmolecules.event.types.DomainEvent;

public record InventoryReserved(String sku, int quantity)
        implements DomainEvent {
}
```

Một biến thể của service phát event sau khi hoàn tất thay đổi trạng thái:

```java
package com.acme.shop.inventory;

import com.acme.shop.inventory.events.InventoryReserved;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class InventoryManagement {

    private final ApplicationEventPublisher events;

    public InventoryManagement(ApplicationEventPublisher events) {
        this.events = events;
    }

    public void reserve(String sku, int quantity) {
        // Cập nhật trạng thái tồn kho.
        events.publishEvent(new InventoryReserved(sku, quantity));
    }
}
```

Event được đánh dấu giúp `Documenter` đưa nó vào phần Published events. Nếu event type không có metadata jMolecules phù hợp, event vẫn có thể được Spring publish và listener vẫn xử lý, nhưng nó có thể không xuất hiện trong danh sách published events của canvas.

Đặt event type trong package API hoặc named interface nếu module khác cần tham chiếu nó. Canvas thể hiện event được công bố; `@NamedInterface` và `allowedDependencies` mới xác định event contract có được expose và consumer có được phép phụ thuộc hay không.

## 6. Events listened to cho biết module phản ứng với điều gì

Canvas cũng liệt kê các event mà module lắng nghe. Spring Modulith suy ra thông tin này từ:

- Phương thức được đánh dấu bằng Spring `@EventListener`.
- Phương thức được đánh dấu bằng Spring `@TransactionalEventListener`.
- Phương thức được đánh dấu bằng jMolecules `@DomainEventHandler`.
- Bean triển khai Spring `ApplicationListener`.

Ví dụ listener trong module `inventory`:

```java
package com.acme.shop.inventory.internal;

import com.acme.shop.orders.events.OrderCompleted;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class InventoryOrderEventListener {

    @ApplicationModuleListener
    void on(OrderCompleted event) {
        // Cập nhật trạng thái tồn kho sau khi đơn hoàn tất.
    }
}
```

`@ApplicationModuleListener` là annotation chuyên biệt của Spring Modulith và kết hợp các semantics của async transactional listener. Nó được xây dựng trên Spring event listener infrastructure, nên listener được nhận diện như một event listener trong mô hình và canvas.

Phần Events listened to cho biết module đang phản ứng với event type nào. Nó không mô tả đầy đủ thứ tự xử lý, retry policy, transaction flow hoặc kết quả của listener ở runtime. Để hiểu các khía cạnh đó, cần xem code listener, cấu hình Event Publication Registry và các bài kiểm thử tương ứng.

## 7. Configuration properties cho biết module công khai cấu hình nào

Canvas có thể hiển thị Spring Boot configuration properties được expose bởi module. Ví dụ:

```java
package com.acme.shop.inventory;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "shop.inventory")
public record InventoryProperties(int restockThreshold) {
}
```

File cấu hình:

```yaml
shop:
  inventory:
    restock-threshold: 10
```

Để `Documenter` trích xuất metadata của configuration properties, dự án cần có artifact `spring-boot-configuration-processor` trong quá trình compile/annotation processing. Nếu thiếu processor hoặc metadata không được sinh, phần properties trong canvas có thể không đầy đủ dù ứng dụng vẫn bind cấu hình khi chạy.

Ví dụ dependency cho Gradle:

```groovy
dependencies {
    annotationProcessor("org.springframework.boot:spring-boot-configuration-processor")
}
```

Hãy công khai properties type qua package gốc hoặc named interface nếu module khác thực sự cần sử dụng nó. Canvas chỉ liệt kê configuration properties được expose; nó không tự biến mọi class `@ConfigurationProperties` nội bộ thành API liên module.

## 8. Ví dụ một Module Canvas hoàn chỉnh

Giả sử module `inventory` có service, repository, aggregate root, event và listener. Canvas minh họa có thể được đọc như sau:

| Nhóm | Nội dung minh họa |
|---|---|
| Base package | `com.acme.shop.inventory` |
| Services | `InventoryManagement` |
| Repositories | `InventoryItemRepository` |
| Event listeners | `InventoryOrderEventListener` — lắng nghe `OrderCompleted` |
| Aggregate roots | `InventoryItem` |
| Published events | `InventoryReserved` |
| Events listened to | `OrderCompleted`, `OrderCanceled` |
| Configuration properties | `InventoryProperties` — prefix `shop.inventory` |

Khi đọc canvas, hãy đặt các câu hỏi:

1. Module sở hữu package nào?
2. Các Spring bean nào là API hoặc component quan trọng của module?
3. Module đang sở hữu aggregate root nào?
4. Module công bố những sự kiện nào để consumer có thể phản ứng?
5. Module đang lắng nghe sự kiện từ module nào?
6. Những cấu hình nào được expose để vận hành hoặc tích hợp module?

Nếu canvas không có một mục mà nhóm mong đợi, hãy kiểm tra source metadata, package API, stereotype và processor trước khi kết luận module không có thành phần đó.

## 9. Sinh Module Canvas bằng Documenter

Tạo `ApplicationModules` từ lớp ứng dụng, sau đó truyền cùng model vào `Documenter`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

import com.acme.shop.ShopApplication;

class DocumentationTests {

    private final ApplicationModules modules =
        ApplicationModules.of(ShopApplication.class);

    @Test
    void writeModuleCanvases() {
        new Documenter(modules)
            .writeModuleCanvases();
    }
}
```

`writeModuleCanvases()` tạo canvas cho tất cả application module. Mặc định, tài liệu được ghi vào thư mục `spring-modulith-docs` bên trong build directory của build system. Tên file mặc định theo mẫu `module-$moduleName.adoc`.

Nếu muốn sinh cả sơ đồ component và canvas, dùng:

```java
new Documenter(modules)
    .writeDocumentation();
```

Phương thức này tạo sơ đồ component tổng quan cho toàn bộ module, sơ đồ riêng cho từng module cùng các module mà nó phụ thuộc trực tiếp, Module Canvas cho từng module và tài liệu tổng hợp `all-docs.adoc` liên kết các sơ đồ cùng canvas đã được sinh.

Nên tạo tài liệu từ cùng instance `ApplicationModules` đã dùng để kiểm chứng kiến trúc. Khi đó, module list, dependency graph và canvas cùng phản ánh một model.

## 10. Tùy chỉnh nội dung bằng CanvasOptions

`Documenter.CanvasOptions` cho phép điều chỉnh cách canvas hiển thị. Một số lựa chọn hữu ích:

| API | Tác dụng |
|---|---|
| `defaults()` | Dùng grouping mặc định cho Spring Framework và jMolecules nếu có trên classpath |
| `revealInternals()` | Bao gồm các component nội bộ trong canvas |
| `revealEmptyLines()` | Giữ lại hàng trong bảng ngay cả khi không có giá trị, ví dụ nhóm aggregate trống |
| `withApiBase(String)` | Tạo liên kết tới Javadoc của các type trong canvas dựa trên URI gốc |
| `withTargetFileName(String)` | Đặt tên file canvas đầu ra |
| `groupingBy(...)` | Thêm grouping component tùy chỉnh bằng predicate trên `SpringBean` |
| `withoutDefaultGroupings()` | Tạo options không đăng ký các grouping mặc định |

Ví dụ, hiển thị cả internal components và các hàng rỗng:

```java
var canvasOptions = Documenter.CanvasOptions.defaults()
    .revealInternals()
    .revealEmptyLines();

new Documenter(modules)
    .writeModuleCanvases(canvasOptions);
```

Nếu muốn thêm grouping cho các bean được xem là API bean:

```java
import org.springframework.modulith.core.SpringBean;
import org.springframework.modulith.docs.Documenter;

var canvasOptions = Documenter.CanvasOptions.defaults()
    .groupingBy(
        "API beans",
        SpringBean::isApiBean,
        "Spring beans exposed through the module API"
    );

new Documenter(modules)
    .writeModuleCanvases(canvasOptions);
```

Grouping tùy chỉnh giúp tài liệu phản ánh cách nhóm muốn phân loại component. Predicate phải chọn đúng các `SpringBean` theo tiêu chí đã định nghĩa; nó không thay đổi package API hoặc dependency policy của module.

## 11. Vì sao một số mục có thể bị thiếu?

Canvas được tạo từ metadata và các loại thành phần mà Spring Modulith nhận diện. Nếu một mục không xuất hiện, hãy kiểm tra nguyên nhân tương ứng:

| Mục bị thiếu | Nguyên nhân cần kiểm tra |
|---|---|
| Spring service/repository | Bean chưa được đăng ký, thiếu stereotype hoặc nằm ngoài phạm vi module/API được canvas hiển thị |
| Aggregate root | Entity chưa có repository được nhận diện hoặc chưa khai báo aggregate bằng jMolecules |
| Published event | Event type chưa được đánh dấu bằng jMolecules `@DomainEvent` hoặc chưa triển khai `DomainEvent` |
| Event listener | Listener chưa dùng annotation được nhận diện hoặc bean chưa triển khai `ApplicationListener` |
| Configuration properties | Thiếu `spring-boot-configuration-processor`, metadata không được sinh hoặc properties không được expose |
| Internal component | Canvas đang ẩn internals; cân nhắc `revealInternals()` khi cần xem |

Không nên thêm annotation chỉ để làm canvas có thêm hàng. Annotation cần phản ánh đúng ý nghĩa kiến trúc. Nếu module không có aggregate root hoặc configuration properties được expose, việc hàng đó vắng mặt có thể hoàn toàn hợp lý.

## 12. Giới hạn của Module Canvas

Canvas là ảnh chụp kiến trúc được sinh từ code và metadata tại thời điểm chạy `Documenter`. Nó hữu ích nhưng không phải tài liệu đặc tả đầy đủ cho mọi khía cạnh của module.

- Canvas không giải thích đầy đủ business rule, invariant hoặc quy trình nghiệp vụ.
- Danh sách aggregate root dựa trên quy tắc nhận diện entity/repository hoặc stereotype, không thay thế domain modeling.
- Published events chỉ đầy đủ khi event type được đánh dấu theo quy ước jMolecules mà Spring Modulith nhận diện.
- Events listened to cho biết event type được đăng ký, không mô tả thứ tự, retry, kết quả hoặc độ trễ xử lý.
- Configuration properties phụ thuộc vào metadata được sinh bởi configuration processor.
- Các component nội bộ có thể bị ẩn theo options mặc định.
- Canvas không tự chứng minh module đã vượt qua `ApplicationModules.verify()`; cần chạy verification riêng.
- Canvas không tự đồng bộ với tài liệu viết tay nếu nhóm không chạy lại bước sinh tài liệu sau thay đổi.

Do đó, hãy dùng canvas như một nguồn thông tin kỹ thuật có thể tái tạo, rồi bổ sung mô tả nghiệp vụ, lý do thiết kế và các quyết định kiến trúc mà code không thể tự diễn đạt.

## 13. Quy trình duy trì Module Canvas

Một quy trình đơn giản để giữ canvas nhất quán:

1. **Tổ chức module và API.** Đặt package gốc, named interface và internal package đúng ownership.
2. **Đăng ký Spring beans.** Dùng stereotype hoặc `@Bean` phù hợp để component được nhận diện.
3. **Đánh dấu domain model.** Dùng repository hoặc jMolecules aggregate stereotype để thể hiện aggregate root.
4. **Đánh dấu event.** Dùng jMolecules `@DomainEvent` hoặc `DomainEvent` interface cho event cần xuất hiện trong phần published events.
5. **Khai báo listener.** Dùng Spring event annotations, `@ApplicationModuleListener`, `@DomainEventHandler` hoặc `ApplicationListener` phù hợp.
6. **Sinh configuration metadata.** Thêm `spring-boot-configuration-processor` nếu muốn canvas hiển thị configuration properties.
7. **Tạo model và kiểm chứng.** Dùng `ApplicationModules` và chạy `verify()` trong architecture test.
8. **Sinh canvas.** Gọi `Documenter.writeModuleCanvases()` hoặc `writeDocumentation()`.
9. **Đọc lại kết quả.** Xác nhận module, component, event và properties quan trọng xuất hiện đúng.
10. **Cập nhật tài liệu tổng hợp.** Chạy lại sau khi package, bean, event hoặc metadata thay đổi; cập nhật phần mô tả nghiệp vụ viết tay khi cần.

## 14. Những ngộ nhận thường gặp

- **“Module Canvas liệt kê mọi class trong module.”** Canvas tập trung vào base package và các nhóm component, aggregate, event, properties được nhận diện.
- **“Mọi application event đều tự xuất hiện trong Published events.”** Event type cần được đánh dấu bằng jMolecules `@DomainEvent` hoặc triển khai `DomainEvent`.
- **“Chỉ `@ApplicationModuleListener` mới được nhận diện.”** Spring `@EventListener`, `@TransactionalEventListener`, jMolecules `@DomainEventHandler` và `ApplicationListener` cũng được dùng để suy ra event listeners.
- **“Entity nào cũng tự là aggregate root.”** Canvas dựa trên entity có repository được nhận diện hoặc aggregate được khai báo bằng jMolecules.
- **“Configuration properties luôn hiện nếu Spring bind thành công.”** Canvas cần metadata từ `spring-boot-configuration-processor` để trích xuất properties.
- **“Canvas mặc định hiển thị toàn bộ internal components.”** Có thể cần bật `revealInternals()` để đưa internal components vào canvas.
- **“Canvas thay thế component diagram.”** Canvas mô tả thành phần bên trong module; component diagram mô tả quan hệ giữa các module.
- **“Canvas chứng minh module đã hợp lệ.”** Cần chạy `ApplicationModules.verify()` riêng để kiểm tra dependency và ranh giới.
- **“Sinh một lần là tài liệu luôn mới.”** Canvas là artifact tại thời điểm sinh; cần chạy lại khi model hoặc metadata thay đổi.

## Kết luận

Module Canvas là bảng mô tả application module gồm base package, Spring components, aggregate roots, published events, events listened to và configuration properties. `Documenter.writeModuleCanvases()` tạo canvas cho các module từ `ApplicationModules`, thường ghi vào `spring-modulith-docs` trong build directory. `CanvasOptions` cho phép hiển thị internal components, giữ hàng rỗng, thêm Javadoc links và tùy chỉnh grouping. Độ đầy đủ của canvas phụ thuộc vào stereotype, event metadata và configuration processor; hãy kiểm tra các nguồn metadata, chạy `ApplicationModules.verify()` riêng và sinh lại tài liệu sau mỗi thay đổi kiến trúc.

## Tài liệu tham khảo

- [Spring Modulith — Documenting Application Modules](https://docs.spring.io/spring-modulith/reference/documentation.html)
- [Spring Modulith — Documenter API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/docs/Documenter.html)
- [Spring Modulith — Documenter.CanvasOptions API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/docs/Documenter.CanvasOptions.html)
- [Spring Modulith — ApplicationModule API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModule.html)

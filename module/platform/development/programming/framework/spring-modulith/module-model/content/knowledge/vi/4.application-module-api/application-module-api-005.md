# Kiểm tra type có được module expose hay không

Khi đọc mã nguồn của một ứng dụng Spring Boot, ta có thể thấy một class được khai báo **public** và nghĩ rằng module khác được phép sử dụng nó. Trong Spring Modulith, khả năng truy cập của Java và API mà một Application Module công bố là hai khái niệm khác nhau. Một type có thể thuộc module nhưng vẫn là chi tiết nội bộ.

Spring Modulith cung cấp API mô hình để kiểm tra điều này trực tiếp: tìm module sở hữu type bằng **ApplicationModules.getModuleByType(…)**, sau đó gọi **ApplicationModule.isExposed(…)**. Bài học này hướng dẫn cách dùng hai API đó, cách phân biệt **contains()** với **isExposed()** và cách kiểm tra kết quả bằng một bài test kiến trúc.

## 1. Hiểu đúng câu hỏi “type có được expose không?”

Một Application Module có các type phục vụ API và các type chỉ dành cho phần triển khai bên trong. Với module đóng (closed module), quy tắc mặc định là:

- Các type public nằm trực tiếp trong base package của module thuộc API package mặc định.
- Các type trong subpackage là nội bộ, trừ khi subpackage được công bố bằng Named Interface.
- Một type nội bộ vẫn có thể được khai báo public để các package khác bên trong cùng module sử dụng.

Ví dụ:

~~~text
example
├── Application.java
├── order
│   ├── OrderManagement.java
│   ├── spi
│   │   ├── package-info.java
│   │   └── PaymentGateway.java
│   └── internal
│       └── OrderRepository.java
└── inventory
    └── InventoryService.java
~~~

Trong ví dụ này:

| Type | Vị trí | Trạng thái |
|---|---|---|
| **OrderManagement** | **example.order** | API package mặc định |
| **PaymentGateway** | **example.order.spi** | API thuộc Named Interface **spi** |
| **OrderRepository** | **example.order.internal** | Nội bộ của module **order** |

**OrderRepository** có thể là một class public, nhưng module **inventory** vẫn không được phụ thuộc vào nó. Vì vậy, khi hỏi một type có được expose hay không, cần kiểm tra mô hình module của Spring Modulith thay vì chỉ nhìn modifier **public**.

## 2. Dùng ApplicationModules để tìm module sở hữu type

**ApplicationModules** phân tích cấu trúc package của ứng dụng và tạo ra mô hình các Application Module trong bộ nhớ. Ta khởi tạo mô hình từ class ứng dụng Spring Boot:

~~~java
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(Application.class);
~~~

Sau đó, dùng **getModuleByType(Class<?>)** để tìm module chứa type:

~~~java
var owner = modules.getModuleByType(OrderManagement.class);
~~~

Kết quả là **Optional<ApplicationModule>**:

- Có giá trị: type được nhận diện trong một Application Module của mô hình.
- Rỗng: type không thuộc module nào được phát hiện trong mô hình hiện tại. Hãy kiểm tra package gốc, cấu hình phát hiện module, classpath và việc type có nằm trong phạm vi quét hay không.

Có thể lấy module theo logical name nếu đã biết tên:

~~~java
var orderModule = modules.getModuleByName("order")
    .orElseThrow(() -> new IllegalStateException("Không tìm thấy module order"));
~~~

Tên **order** trong ví dụ là logical name của module có base package **example.order**. Trong dự án thật, hãy dùng đúng tên module được Spring Modulith phát hiện.

## 3. Gọi isExposed() để kiểm tra API

Sau khi tìm được module sở hữu type, gọi **ApplicationModule.isExposed(Class<?>)**:

~~~java
ApplicationModules modules = ApplicationModules.of(Application.class);

boolean exposed = modules.getModuleByType(OrderManagement.class)
    .map(module -> module.isExposed(OrderManagement.class))
    .orElse(false);
~~~

Phương thức **isExposed()** trả về **true** nếu type thuộc một trong các interface mà module công bố. Những interface này gồm API package mặc định (unnamed interface) và các Named Interface được khai báo tường minh.

Nếu muốn kiểm tra một type cụ thể trong module đã biết, có thể gọi trực tiếp:

~~~java
var orderModule = modules.getModuleByName("order").orElseThrow();

boolean apiType = orderModule.isExposed(OrderManagement.class);
boolean spiType = orderModule.isExposed(PaymentGateway.class);
boolean internalType = orderModule.isExposed(OrderRepository.class);
~~~

Với cấu trúc ở phần trước, kết quả mong đợi là:

| Biểu thức | Kết quả | Lý do |
|---|---:|---|
| **isExposed(OrderManagement.class)** | **true** | Type nằm trong base package **example.order** |
| **isExposed(PaymentGateway.class)** | **true** | Package **example.order.spi** được công bố |
| **isExposed(OrderRepository.class)** | **false** | Type nằm trong subpackage nội bộ |

**isExposed(Class<?>)** có từ Spring Modulith 1.2.8 và 1.3.2 tương ứng với các nhánh phát hành. Nếu dự án dùng phiên bản cũ hơn, hãy kiểm tra Javadoc của đúng phiên bản trước khi sử dụng overload này.

## 4. Phân biệt contains() và isExposed()

Hai phương thức trả lời hai câu hỏi khác nhau:

- **contains(Class<?>)**: type có thuộc module này hay không?
- **isExposed(Class<?>)**: type đó có nằm trong API được module công bố hay không?

Ví dụ:

~~~java
var orderModule = modules.getModuleByName("order").orElseThrow();

assertTrue(orderModule.contains(OrderRepository.class));
assertFalse(orderModule.isExposed(OrderRepository.class));
~~~

Cả hai kết quả đều đúng: **OrderRepository** thuộc module **order**, nhưng module không công bố type này. Dùng **contains()** một mình để kết luận một type được expose sẽ dẫn đến kết quả sai.

Khi cần kiểm tra cả hai điều kiện, hãy thể hiện rõ ý nghĩa trong tên biến hoặc assertion:

~~~java
boolean belongsToOrder = orderModule.contains(OrderRepository.class);
boolean isPublicApi = orderModule.isExposed(OrderRepository.class);
~~~

## 5. Kiểm tra Named Interface

Một subpackage chỉ trở thành API khi được khai báo là Named Interface. Với Java, có thể đặt annotation trong **package-info.java**:

~~~java
@org.springframework.modulith.NamedInterface("spi")
package example.order.spi;
~~~

Type trong package đó được expose dưới tên interface **spi**:

~~~java
package example.order.spi;

public interface PaymentGateway {
    void authorize(String orderId);
}
~~~

**isExposed(PaymentGateway.class)** kiểm tra type có thuộc một interface đã công bố hay không. Nếu cần xem các interface mà module đang công bố, dùng **getNamedInterfaces()**:

~~~java
orderModule.getNamedInterfaces().forEach(namedInterface -> {
    String name = namedInterface.isUnnamed()
        ? "(API package mặc định)"
        : namedInterface.getName();

    System.out.println(name);
});
~~~

**isUnnamed()** giúp nhận diện API package mặc định; **getName()** trả về tên của Named Interface tường minh. Cách liệt kê này hữu ích khi cần kiểm tra module đã nhận diện đúng package **spi** hay chưa.

Với Kotlin, khai báo metadata package bằng một class có **@PackageInfo** và **@NamedInterface("spi")**, theo cú pháp trong tài liệu Spring Modulith. Cơ chế expose sau đó được mô hình hóa giống như với Java.

## 6. Viết test để bảo vệ hợp đồng công khai

Nên kiểm tra trạng thái expose trong test để thay đổi package hoặc annotation không vô tình làm hỏng API của module.

Ví dụ dưới đây dùng JUnit Jupiter:

~~~java
package example;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import example.order.OrderManagement;
import example.order.internal.OrderRepository;
import example.order.spi.PaymentGateway;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

class ApplicationModuleApiTests {

    private final ApplicationModules modules =
        ApplicationModules.of(Application.class);

    @Test
    void exposesOnlyDeclaredTypes() {
        ApplicationModule order = modules.getModuleByName("order")
            .orElseThrow();

        assertTrue(order.isExposed(OrderManagement.class));
        assertTrue(order.isExposed(PaymentGateway.class));
        assertFalse(order.isExposed(OrderRepository.class));
    }

    @Test
    void findsTheOwningModuleAndChecksExposure() {
        var owner = modules.getModuleByType(PaymentGateway.class)
            .orElseThrow();

        assertTrue(owner.isExposed(PaymentGateway.class));
    }
}
~~~

Test này kiểm tra ba hợp đồng cụ thể: API mặc định được công bố, Named Interface được công bố và repository nội bộ không được công bố. Các class trong ví dụ cần tồn tại trong source set mà **ApplicationModules.of(Application.class)** phân tích.

Khi test thất bại, hãy kiểm tra lần lượt: type đang nằm trong package nào, package đó có được khai báo **@NamedInterface** hay chưa, module có được phát hiện theo cấu hình hiện tại hay không và module có đang dùng chế độ mở hay không.

## 7. Hiểu kết quả trong các trường hợp đặc biệt

**Module mở (Open Application Module).** Khi module được cấu hình **@ApplicationModule(type = Type.OPEN)**, Spring Modulith cho phép truy cập rộng hơn: các type trong subpackage cũng được đưa vào unnamed interface, trừ các type được gán rõ vào Named Interface. Vì thế, một type ở package **internal** có thể trả về **true** trong module mở. Nếu muốn giữ ranh giới chặt, hãy dùng module đóng và công bố rõ từng Named Interface.

**Type không được tìm thấy.** Nếu **getModuleByType()** trả về **Optional.empty()**, chưa thể kết luận type là nội bộ. Có thể type không nằm trong vùng package mà mô hình quét, nằm ngoài source set đang phân tích hoặc module được cấu hình theo chiến lược phát hiện khác. Trước hết cần xác định type có thuộc mô hình hay không.

**Type được expose nhưng consumer không được phép phụ thuộc.** **isExposed()** kiểm tra API phía module cung cấp. Nó không kiểm tra module tiêu thụ có được cấp quyền phụ thuộc vào API đó hay không. Nếu consumer khai báo **allowedDependencies**, quyền này còn phải cho phép đúng module hoặc Named Interface. Dùng **ApplicationModules.verify()** để kiểm tra các tham chiếu thực tế và quy tắc phụ thuộc của toàn ứng dụng.

**Type public nhưng không được expose.** Đây là tình huống bình thường với implementation nằm trong subpackage. Không cần đổi class thành package-private chỉ để làm cho **isExposed()** trả về **false**; giữ type public nếu các package nội bộ cần gọi nó, đồng thời duy trì quy tắc kiến trúc bằng kiểm chứng Spring Modulith.

## 8. Quy trình kiểm tra trong dự án

Khi review một import hoặc thiết kế API liên module, thực hiện theo trình tự:

1. Xác định class ứng dụng Spring Boot dùng làm đầu vào cho **ApplicationModules.of(…)**.
2. Gọi **getModuleByType(TypeCanKiemTra.class)** để tìm module sở hữu type.
3. Nếu không tìm thấy module, kiểm tra phạm vi quét và cấu hình phát hiện module.
4. Nếu tìm thấy module, gọi **isExposed(TypeCanKiemTra.class)** để xác nhận type thuộc API công khai.
5. Nếu type không được expose, chuyển hợp đồng về API package hoặc công bố package bằng **@NamedInterface** khi có lý do nghiệp vụ.
6. Kiểm tra quyền của module tiêu thụ qua **allowedDependencies** và chạy **ApplicationModules.verify()** trong test kiến trúc.

Quy trình này giúp trả lời riêng rẽ ba câu hỏi: type thuộc module nào, module đó có công bố type không và module tiêu thụ có được phép phụ thuộc vào hợp đồng đó không. Nhờ vậy, review kiến trúc có thể dựa trên mô hình mà Spring Modulith phân tích thay vì suy đoán từ tên package hoặc modifier Java.

## Tài liệu tham khảo

- [Spring Modulith Reference — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html): cách tạo ApplicationModules, API package mặc định, Named Interface và Open Application Module.
- [Javadoc — ApplicationModule](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModule.html): contains(), isExposed(), getNamedInterfaces() và getBasePackage().
- [Javadoc — ApplicationModules](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html): of(), getModuleByType() và getModuleByName().
- [Javadoc — NamedInterface](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/NamedInterface.html): cách nhận diện Named Interface và interface mặc định.

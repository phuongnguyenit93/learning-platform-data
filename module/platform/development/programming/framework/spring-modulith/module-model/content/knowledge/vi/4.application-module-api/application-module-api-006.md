# Truy tìm type theo tên đơn giản hoặc tên đầy đủ

Khi xây dựng công cụ kiểm tra kiến trúc hoặc báo cáo cho một ứng dụng Spring Modulith, đôi khi bạn chỉ có tên của một kiểu Java và cần biết kiểu đó thuộc application module nào. `ApplicationModules` cung cấp phương thức `getModuleByType(String)` để tra cứu module theo tên đơn giản hoặc tên đầy đủ của type. Khi đã biết module, `ApplicationModule.getType(String)` có thể tìm chính type đó trong phạm vi module.

Hai phương thức này giúp công cụ làm việc với mô hình module mà không cần tự phân tích chuỗi package. Kết quả tra cứu được biểu diễn bằng `Optional`, vì vậy chương trình có thể xử lý rõ ràng trường hợp tìm thấy hoặc không tìm thấy type.

## 1. Chuẩn bị mô hình application module

Trước khi tra cứu, hãy tạo `ApplicationModules` từ lớp ứng dụng Spring Boot hoặc package gốc của ứng dụng. Ví dụ, ứng dụng bán hàng có lớp chính `ShopApplication`:

```java
package com.acme.shop;

import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
}
```

Giả sử module `order` có một type tên `OrderManagement`:

```java
package com.acme.shop.order;

public class OrderManagement {

    public void placeOrder(String orderId) {
        // Điều phối nghiệp vụ đặt hàng.
    }
}
```

Với cấu trúc package mặc định, `com.acme.shop.order` là module base package của module `order`. Khi đó có thể tạo mô hình:

```java
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
```

`ApplicationModules` khám phá các module từ điểm bắt đầu đã cung cấp. Các phương thức tra cứu type chỉ làm việc với các type thuộc mô hình được khám phá này; chúng không phải công cụ tìm kiếm mọi class có trong toàn bộ classpath của JVM.

## 2. Tìm module bằng tên đơn giản

Nếu biết tên lớp nhưng không cần chỉ rõ package, truyền tên đơn giản cho `getModuleByType(String)`:

```java
import java.util.Optional;
import org.springframework.modulith.core.ApplicationModule;

Optional<ApplicationModule> result = modules.getModuleByType("OrderManagement");

result.ifPresentOrElse(
        module -> System.out.println("Type thuộc module: " + module.getName()),
        () -> System.out.println("Không tìm thấy type OrderManagement")
);
```

Phương thức trả về `Optional<ApplicationModule>`:

- Nếu tìm thấy type trong mô hình, `Optional` chứa module sở hữu type đó.
- Nếu không tìm thấy, `Optional` rỗng.

Tên đơn giản phù hợp khi type đã biết rõ và không gây nhầm lẫn trong phạm vi ứng dụng. Nếu nhiều package có các type trùng tên đơn giản, hãy ưu tiên tên đầy đủ để xác định chính xác type cần tìm.

## 3. Tìm module bằng tên đầy đủ

Tên đầy đủ (fully-qualified name, FQCN) bao gồm package và tên type. Với `OrderManagement`, tên đầy đủ là `com.acme.shop.order.OrderManagement`:

```java
Optional<ApplicationModule> result = modules.getModuleByType(
        "com.acme.shop.order.OrderManagement"
);

ApplicationModule orderModule = result.orElseThrow(
        () -> new IllegalArgumentException("Không tìm thấy OrderManagement trong mô hình")
);

System.out.println(orderModule.getName());
```

Tra cứu bằng FQCN hữu ích khi:

- Nhiều module có type trùng tên đơn giản, ví dụ `OrderMapper` trong `order` và `OrderMapper` trong `reporting`.
- Công cụ nhận đầu vào từ file cấu hình, log hoặc metadata đã chứa tên đầy đủ.
- Bạn cần kết quả ổn định và rõ ràng khi package được tổ chức lại.

Tên đầy đủ phải khớp với tên package và type trong mô hình. Viết sai package hoặc sai tên lớp sẽ dẫn đến kết quả không tìm thấy.

## 4. Dùng overload nhận Class<?>

Khi chương trình đã tham chiếu được class tại thời điểm biên dịch, hãy dùng overload nhận `Class<?>`:

```java
Optional<ApplicationModule> result = modules.getModuleByType(OrderManagement.class);

result.ifPresent(module ->
        System.out.println(OrderManagement.class.getName() + " thuộc " + module.getName())
);
```

Cách này có lợi thế là compiler kiểm tra tên type, giúp tránh lỗi đánh máy trong chuỗi. Đây thường là lựa chọn phù hợp khi viết code ứng dụng hoặc bài kiểm thử có thể import trực tiếp type cần tra cứu.

Ba cách gọi thường dùng có thể so sánh như sau:

| Cách tra cứu | Ví dụ | Kiểu kết quả |
|---|---|---|
| Tên đơn giản | `getModuleByType("OrderManagement")` | `Optional<ApplicationModule>` |
| Tên đầy đủ | `getModuleByType("com.acme.shop.order.OrderManagement")` | `Optional<ApplicationModule>` |
| Đối tượng Class | `getModuleByType(OrderManagement.class)` | `Optional<ApplicationModule>` |

Hai overload nhận `String` có thể dùng tên đơn giản hoặc FQCN. Overload nhận `Class<?>` thích hợp khi type đã có sẵn trong mã nguồn và bạn muốn được kiểm tra kiểu ở compile time.

## 5. Tìm type bên trong một module đã biết

Đôi khi bạn đã biết module cần kiểm tra và chỉ muốn tìm một type trong phạm vi module đó. `ApplicationModule.getType(String)` trả về `Optional<JavaClass>` cho tên đơn giản hoặc tên đầy đủ của type.

```java
import com.tngtech.archunit.core.domain.JavaClass;
import java.util.Optional;
import org.springframework.modulith.core.ApplicationModule;

ApplicationModule orderModule = modules.getModuleByName("order")
        .orElseThrow(() -> new IllegalArgumentException("Không tìm thấy module order"));

Optional<JavaClass> simpleNameResult = orderModule.getType("OrderManagement");
Optional<JavaClass> qualifiedNameResult = orderModule.getType(
        "com.acme.shop.order.OrderManagement"
);

simpleNameResult.ifPresent(type -> System.out.println(type.getName()));
```

Ở đây có hai bước tra cứu khác nhau:

1. `modules.getModuleByName("order")` tìm module theo tên định danh của module.
2. `orderModule.getType("OrderManagement")` tìm type bên trong module đã chọn.

Kiểu `JavaClass` là mô hình type của ArchUnit mà Spring Modulith sử dụng khi phân tích mã nguồn. Nó không phải `java.lang.Class`. Đối với trường hợp chỉ cần xác định module chứa một class đã có trong mã nguồn, `getModuleByType(OrderManagement.class)` thường trực tiếp hơn.

## 6. Xử lý kết quả Optional an toàn

Các phương thức tra cứu trả về `Optional` để thể hiện rằng kết quả có thể không tồn tại. Tránh gọi `.get()` ngay mà không kiểm tra, vì kết quả rỗng sẽ gây `NoSuchElementException`.

Có thể chọn cách xử lý theo nhu cầu:

```java
// Trường hợp type bắt buộc phải có trong mô hình.
ApplicationModule module = modules.getModuleByType("OrderManagement")
        .orElseThrow(() -> new IllegalStateException("OrderManagement chưa thuộc module nào"));

// Trường hợp type chỉ là thông tin tùy chọn.
modules.getModuleByType("LegacyOrderAdapter")
        .ifPresent(moduleFound -> System.out.println(moduleFound.getName()));

// Trường hợp muốn có giá trị thay thế.
String moduleName = modules.getModuleByType("OrderManagement")
        .map(ApplicationModule::getName)
        .orElse("unknown");
```

Chọn cách xử lý phù hợp với ý nghĩa nghiệp vụ. Nếu type bắt buộc tồn tại, `orElseThrow` giúp lỗi xuất hiện gần vị trí tra cứu và có thông báo cụ thể. Nếu type có thể vắng mặt, `ifPresent` hoặc `orElse` giúp luồng xử lý tiếp tục có chủ đích.

## 7. Tra cứu type không đồng nghĩa với công bố API

`getModuleByType(...)` trả lời câu hỏi type thuộc module nào. Kết quả này không tự khẳng định module khác được phép phụ thuộc vào type đó.

Ví dụ, cả hai type sau đều có thể được tìm thấy trong mô hình:

```text
com.acme.shop.inventory
├── StockAvailability.java
└── internal
    └── StockRepository.java
```

`StockAvailability` nằm trong module base package và có thể là API công khai mặc định. `StockRepository` nằm trong package con `internal`, là chi tiết triển khai nội bộ. Việc tra cứu được `StockRepository` chỉ xác nhận rằng Spring Modulith biết type đó thuộc module `inventory`; nó không biến type này thành API được công bố.

Khi thiết kế phụ thuộc giữa module, hãy kiểm tra thêm quy tắc API công khai và named interface. Dùng `ApplicationModules.verify()` để phát hiện các phụ thuộc kiến trúc không hợp lệ trong toàn mô hình.

## 8. Bài tập thực hành

Giả sử ứng dụng `com.acme.shop` có các module `order`, `inventory` và `reporting`. Hai module `order` và `reporting` đều có type `OrderMapper` trong package riêng.

1. Tạo `ApplicationModules` từ `ShopApplication.class`.
2. Tra cứu `OrderManagement` bằng tên đơn giản và in tên module nhận được.
3. Tra cứu `OrderManagement` bằng FQCN `com.acme.shop.order.OrderManagement`.
4. Tra cứu cùng type bằng `OrderManagement.class`.
5. Tra cứu `OrderMapper` bằng tên đơn giản, sau đó thử dùng FQCN để chỉ rõ type thuộc module cần tìm.
6. Lấy module `order` bằng `getModuleByName("order")`, rồi gọi `getType("OrderManagement")`.
7. Thử tìm một type không tồn tại và xử lý kết quả `Optional.empty()`.
8. Tìm một type nằm trong package `internal`; giải thích vì sao tìm thấy type không có nghĩa type đó là API công khai.

Sau bài tập, hãy giải thích sự khác nhau giữa tên module, tên đơn giản của type, FQCN và `Class<?>`, cũng như lý do nên dùng FQCN khi tên đơn giản không đủ để xác định type.

## 9. Ghi nhớ

- `ApplicationModules.getModuleByType(String)` tìm module chứa type theo tên đơn giản hoặc tên đầy đủ và trả về `Optional<ApplicationModule>`.
- `ApplicationModules.getModuleByType(Class<?>)` tìm module từ đối tượng `Class` đã biết tại thời điểm biên dịch.
- `ApplicationModule.getType(String)` tìm `JavaClass` bên trong một module đã biết, cũng hỗ trợ tên đơn giản hoặc FQCN.
- Dùng tên đầy đủ khi cần chỉ rõ package, đặc biệt nếu có các type trùng tên đơn giản.
- Luôn xử lý trường hợp `Optional` rỗng; không gọi `.get()` mà chưa kiểm tra.
- Tra cứu được type không có nghĩa type đó đã được công bố làm API. Hãy tiếp tục kiểm tra ranh giới module và quy tắc phụ thuộc.

Tham khảo API chính thức: [ApplicationModules](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html) và [ApplicationModule](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModule.html).

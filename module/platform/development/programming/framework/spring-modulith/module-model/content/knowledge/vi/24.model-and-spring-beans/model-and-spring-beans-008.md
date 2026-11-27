# Model và Spring beans

## Bean proxy và ảnh hưởng tới static inspection

Spring Modulith xây dựng mô hình application module bằng cách phân tích cấu trúc mã nguồn và các kiểu Java. Trong khi đó, Spring AOP có thể tạo proxy cho bean khi application context khởi động để áp dụng transaction, security, caching hoặc advice khác. Hai hoạt động này diễn ra ở hai thời điểm và phục vụ hai mục đích khác nhau.

Điểm cần nhớ là **proxy runtime không trở thành một lớp nghiệp vụ mới trong mô hình tĩnh của Spring Modulith**. Mô hình vẫn cần xác định được kiểu bean gốc, interface mà bean triển khai và các kiểu được dùng tại điểm injection. Nếu thiết kế API mô-đun dựa trên interface rõ ràng, proxy thường không làm thay đổi kết luận về ranh giới mô-đun. Tuy nhiên, kiểu proxy có thể ảnh hưởng đến việc ứng dụng truy cập bean lúc chạy và những gì ta nhìn thấy khi kiểm tra đối tượng bằng reflection.

### 1. Static inspection của Spring Modulith làm gì?

`ApplicationModules` cho phép Spring Modulith phân tích codebase và tạo một mô hình application module trong bộ nhớ:

```java
import org.springframework.modulith.core.ApplicationModules;

var modules = ApplicationModules.of(Application.class);

modules.forEach(System.out::println);
modules.verify();
```

Quá trình này phân tích package, kiểu Java, stereotype Spring, các điểm khai báo dependency và những metadata kiến trúc có liên quan. Mỗi application module trong mô hình có danh sách Spring bean, các bean được xem là API và những quan hệ phụ thuộc với mô-đun khác.

Đây là kiểm tra cấu trúc mã nguồn. Lệnh `ApplicationModules.of(Application.class)` không cần khởi động toàn bộ Spring `ApplicationContext` để lấy từng đối tượng bean đang chạy. Vì vậy, nó không dựa vào lớp proxy được Spring tạo ra sau khi khởi tạo bean.

Ví dụ, khi in mô hình, Spring Modulith có thể hiển thị danh sách bean của từng mô-đun cùng ký hiệu thể hiện bean được công khai hay nằm trong phần triển khai nội bộ. Có thể dùng kết quả này để kiểm tra nhanh package nào đang được xem là API và bean nào đang được nhận diện trong mô hình.

### 2. Proxy được tạo ở thời điểm runtime

Spring AOP thường dùng proxy để chặn lời gọi phương thức và áp dụng một hành vi bổ sung. Một số trường hợp phổ biến là `@Transactional`, `@Cacheable`, `@Async` hoặc method security.

Spring có hai cách tạo proxy chính:

| Cách tạo proxy | Cách hoạt động | Hệ quả khi nhìn kiểu đối tượng lúc chạy |
|---|---|---|
| JDK dynamic proxy | Tạo một đối tượng proxy triển khai các interface của bean | Đối tượng proxy có thể được gán cho interface, nhưng không phải instance của lớp triển khai cụ thể |
| Class-based proxy (CGLIB) | Tạo lớp con của lớp bean để ghi đè phương thức có thể được proxy | Đối tượng proxy có kiểu lớp sinh tự động kế thừa lớp triển khai |

Ví dụ, bean `InventoryService` triển khai `InventoryOperations` và được áp dụng transaction advice. Nếu Spring dùng JDK dynamic proxy, đối tượng nhận được từ context có thể là một lớp như `jdk.proxy2.$Proxy...`. Nếu Spring dùng class-based proxy, kiểu runtime có thể có hậu tố sinh tự động như `$$SpringCGLIB$$`.

Do đó, đoạn mã sau không nên được dùng để suy luận trực tiếp lớp nghiệp vụ ban đầu:

```java
Object bean = applicationContext.getBean(InventoryOperations.class);

System.out.println(bean.getClass().getName());
```

`getClass()` trả về lớp runtime của đối tượng đang được inject hoặc lấy từ context. Khi bean được proxy, đó có thể là lớp do framework sinh ra. Nếu cần phân tích hành vi proxy trong một bài kiểm thử runtime, Spring cung cấp `AopUtils`:

```java
import org.springframework.aop.support.AopUtils;

boolean proxied = AopUtils.isAopProxy(bean);
```

Phép kiểm tra này hữu ích để xác nhận một đối tượng có phải AOP proxy hay không. Nó không thay thế việc kiểm tra cấu trúc mô-đun bằng `ApplicationModules`.

### 3. Vì sao proxy không làm thay đổi mô hình mô-đun tĩnh?

Giả sử mô-đun `inventory` có interface công khai và một implementation nội bộ:

```text
com.acme
├── Application.java
├── inventory
│   ├── InventoryOperations.java
│   └── internal
│       └── InventoryService.java
└── orders
    └── OrderService.java
```

Interface nằm trong package gốc `inventory`, còn lớp triển khai nằm trong package `inventory.internal`. Lớp triển khai được Spring quản lý và áp dụng transaction:

```java
// inventory/InventoryOperations.java
package com.acme.inventory;

public interface InventoryOperations {
    boolean hasStock(String productId, int quantity);
}
```

```java
// inventory/internal/InventoryService.java
package com.acme.inventory.internal;

import com.acme.inventory.InventoryOperations;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional
public class InventoryService implements InventoryOperations {

    @Override
    public boolean hasStock(String productId, int quantity) {
        // Truy vấn tồn kho và áp dụng quy tắc nghiệp vụ.
        return true;
    }
}
```

Mô-đun `orders` chỉ phụ thuộc vào interface:

```java
// orders/OrderService.java
package com.acme.orders;

import com.acme.inventory.InventoryOperations;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final InventoryOperations inventory;

    public OrderService(InventoryOperations inventory) {
        this.inventory = inventory;
    }

    public boolean canPlaceOrder(String productId, int quantity) {
        return inventory.hasStock(productId, quantity);
    }
}
```

Trong ví dụ này, static inspection nhìn thấy:

- `InventoryService` là Spring bean thuộc mô-đun `inventory`.
- `InventoryOperations` là interface được công khai từ package gốc của mô-đun.
- `OrderService` phụ thuộc vào `InventoryOperations`, tức hợp đồng API của `inventory`.

Spring Modulith xem một bean là API bean nếu kiểu bean là kiểu công khai trong API package của mô-đun hoặc bean triển khai một interface được công khai. Vì vậy, implementation có thể nằm trong package nội bộ nhưng vẫn cung cấp API thông qua interface được công khai. Việc Spring bọc implementation bằng JDK proxy hay CGLIB proxy không tạo ra một dependency mới giữa các mô-đun.

Đây là một lợi ích quan trọng của việc thiết kế hợp đồng bằng interface: mô-đun gọi không cần biết implementation cụ thể, còn framework có thể áp dụng proxy ở runtime mà không làm thay đổi kiểu dependency được khai báo trong mã nguồn.

### 4. Khi proxy làm lộ ra vấn đề về kiểu dependency

Proxy có thể làm ứng dụng gặp lỗi nếu code phụ thuộc vào lớp triển khai cụ thể trong khi Spring tạo JDK dynamic proxy. Xét constructor sau:

```java
@Service
public class OrderService {

    private final InventoryService inventory;

    public OrderService(InventoryService inventory) {
        this.inventory = inventory;
    }
}
```

Nếu bean `InventoryService` được bọc bằng JDK dynamic proxy, proxy chỉ triển khai các interface phù hợp và không phải instance của `InventoryService`. Spring không thể inject đối tượng proxy đó vào tham số constructor yêu cầu kiểu `InventoryService`. Lỗi có thể xuất hiện khi khởi tạo application context, dù static inspection vẫn đọc được dependency mà constructor khai báo.

Với class-based proxy, việc inject theo lớp có thể hoạt động nếu lớp và phương thức cần proxy đáp ứng các điều kiện kế thừa và ghi đè. Tuy nhiên, dựa vào kiểu proxy cụ thể để cho phép mô-đun khác phụ thuộc vào implementation nội bộ sẽ làm hợp đồng giữa các mô-đun trở nên mong manh.

Thiết kế nên ưu tiên:

- Mô-đun cung cấp đặt interface hoặc kiểu API trong package được công khai.
- Implementation nằm trong package nội bộ và được đăng ký như Spring bean.
- Mô-đun tiêu thụ inject interface công khai qua constructor.
- Các named interface được khai báo nếu API cần công khai nằm ngoài package gốc.

Nếu muốn dùng JDK proxy, có thể cấu hình Spring Boot:

```yaml
spring:
  aop:
    proxy-target-class: false
```

Thiết lập này yêu cầu cơ chế AOP của Spring Boot ưu tiên JDK dynamic proxy khi bean có interface phù hợp. Cấu hình proxy là quyết định ở tầng runtime; nó không thay đổi package nào được Spring Modulith xem là API.

### 5. Những điều static inspection có thể và không thể kết luận

| Nội dung | Static inspection có thể phân tích | Cần kiểm tra runtime |
|---|---|---|
| Package và module | Package chứa kiểu, ranh giới module, API package và named interface | Package scan thực tế có đăng ký bean như dự kiến hay không |
| Spring bean | Kiểu bean được nhận diện từ cấu trúc và metadata mã nguồn | Bean thực tế có được tạo, có bị loại bởi profile hoặc condition hay không |
| Dependency | Kiểu được khai báo tại constructor, field hoặc phương thức injection | Context có tìm được bean phù hợp và inject thành công hay không |
| AOP proxy | Kiểu gốc và hợp đồng interface thể hiện trong mã nguồn | JDK hay CGLIB proxy được tạo, advice có được áp dụng đúng không |
| Hành vi phương thức | Quan hệ kiểu và cấu trúc gọi có thể phân tích tĩnh | Transaction, security, cache hoặc async có hoạt động đúng ở runtime không |

Static inspection có giới hạn với các quan hệ được tạo động. Ví dụ, lời gọi `applicationContext.getBean("inventoryService")`, tra cứu bean qua tên được ghép từ chuỗi, đăng ký bean bằng API lập trình hoặc lựa chọn implementation theo dữ liệu runtime có thể không thể hiện đầy đủ trong đồ thị dependency tĩnh. Những trường hợp này cần được kiểm tra bằng integration test hoặc kiểm tra trực tiếp Spring context.

Tương tự, một dependency có thể hợp lệ theo package nhưng không inject được do kiểu proxy, điều kiện tạo bean hoặc cấu hình runtime. `ApplicationModules.verify()` kiểm tra các quy tắc cấu trúc mà nó biết; nó không thay thế kiểm thử khởi động ứng dụng.

### 6. Kết hợp kiểm tra cấu trúc và kiểm tra runtime

Nên có hai lớp kiểm tra bổ sung cho nhau. Lớp thứ nhất xác minh mô hình module:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleStructure() {
        ApplicationModules.of(Application.class).verify();
    }
}
```

Lớp thứ hai khởi động Spring context để kiểm tra bean và proxy thực tế. Ví dụ với Spring Boot test:

```java
import static org.assertj.core.api.Assertions.assertThat;

import com.acme.inventory.InventoryOperations;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class InventoryProxyTests {

    @Autowired
    InventoryOperations inventory;

    @Test
    void injectsThePublicContractAndAppliesProxyWhenConfigured() {
        assertThat(inventory).isNotNull();

        // Chỉ bật assertion này khi cấu hình và advice của ứng dụng
        // thực sự yêu cầu InventoryOperations được proxy.
        assertThat(AopUtils.isAopProxy(inventory)).isTrue();
    }
}
```

Assertion về proxy cần phù hợp với cấu hình thực tế. Nếu bean không có advice áp dụng hoặc AOP chưa được bật, bean có thể không phải proxy và assertion đó không nên được giữ. Điều quan trọng là integration test xác nhận context có thể inject đúng API và áp dụng đúng hành vi runtime.

Khi một bài kiểm tra cấu trúc thất bại, hãy đọc mô hình được in ra bằng `modules.forEach(System.out::println)` để xem bean nào được nhận diện là API hoặc internal. Khi một bài kiểm tra context thất bại, hãy kiểm tra kiểu constructor, interface mà bean triển khai, chiến lược proxy và điều kiện tạo bean. Hai loại kết quả giúp khoanh vùng lỗi ở đúng lớp.

### 7. Quy tắc thực hành

1. Thiết kế API mô-đun bằng interface hoặc kiểu công khai có vị trí package rõ ràng.
2. Inject API qua constructor thay vì phụ thuộc trực tiếp vào lớp triển khai nội bộ.
3. Không dùng `bean.getClass()` làm căn cứ duy nhất để xác định lớp nghiệp vụ khi bean có thể được proxy.
4. Dùng `ApplicationModules.verify()` để kiểm tra ranh giới và dependency tĩnh.
5. Dùng integration test để xác minh bean thực tế, khả năng inject và hành vi AOP.

Proxy là chi tiết triển khai ở runtime. Static inspection của Spring Modulith giúp giữ cho mô hình mô-đun gắn với cấu trúc mã nguồn và hợp đồng được khai báo. Khi interface công khai được thiết kế ổn định, nhóm có thể thay đổi cách proxy bean mà không làm thay đổi cách các mô-đun giao tiếp với nhau.

### Tài liệu tham khảo

- [Spring Modulith — Fundamentals: ApplicationModules và Spring beans](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith API — `SpringBean`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/SpringBean.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — Understanding AOP Proxies](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html#aop-understanding-aop-proxies)

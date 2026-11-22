# Ranh giới package không tự tạo ra ranh giới Spring context

Trong một dự án Spring Boot, lập trình viên thường tạo các package như `controller`, `service`, `repository`, hoặc tách theo nghiệp vụ thành `order`, `inventory`, `customer`. Cách chia này giúp đọc mã nguồn, tìm lớp và quản lý phụ thuộc. Tuy nhiên, **mỗi package Java không tự trở thành một Spring container riêng**. Nếu các bean trong những package đó cùng được đăng ký vào một `ApplicationContext`, chúng vẫn thuộc cùng một không gian quản lý bean và có thể được kết nối với nhau thông qua dependency injection.

Phân biệt được **ranh giới tổ chức mã Java** với **ranh giới runtime của Spring** giúp tránh hai hiểu lầm phổ biến: cho rằng hai package tự cách ly nhau và cho rằng di chuyển lớp sang package khác sẽ tự tạo một ứng dụng con độc lập.

## 1. Hai loại ranh giới có trách nhiệm khác nhau

### Package là đơn vị tổ chức và truy cập của Java

Trong Java, khai báo `package` đặt tên lớp vào một namespace:

```java
package com.example.store.order;

public class Order {
    // ...
}
```

Package giúp:

- Tránh xung đột tên lớp, chẳng hạn `order.Status` và `payment.Status`.
- Sắp xếp các lớp theo tính năng hoặc tầng kiến trúc để dễ đọc và bảo trì.
- Áp dụng một phần quy tắc truy cập của Java, đặc biệt với thành viên hoặc lớp có phạm vi *package-private*.
- Tạo cấu trúc dễ kiểm tra bằng quy ước, code review hoặc công cụ phân tích kiến trúc.

Package **không phải** tiến trình hệ điều hành, class loader độc lập, vùng bộ nhớ riêng, Spring `ApplicationContext` riêng hoặc cơ chế phân quyền nghiệp vụ. Hai lớp `public` ở hai package khác nhau vẫn có thể import và gọi nhau khi dependency và các quy tắc truy cập cho phép.

### `ApplicationContext` là nơi Spring quản lý bean

Một `ApplicationContext` là giao diện trung tâm của Spring container. Nó biết những bean definition đã được đăng ký, tạo và cấu hình bean, kết nối dependency, cung cấp các dịch vụ container như sự kiện, lifecycle và tích hợp cơ chế cấu hình của framework.

Một **bean** là đối tượng do Spring container quản lý. Bean có thể đến từ lớp được component scanning phát hiện (`@Component`, `@Service`, `@Repository`, `@Controller`, ...) hoặc từ phương thức `@Bean` trong một lớp cấu hình đã được đăng ký. Không phải mọi đối tượng được tạo bằng `new` trong ứng dụng đều tự trở thành Spring bean.

Ví dụ đơn giản:

```text
Java source packages                 Spring runtime
────────────────────                 ──────────────
com.example.store
├── order/
│   └── OrderService.java  ───────┐
├── inventory/                   │
│   └── InventoryService.java ───┼──> ApplicationContext
└── web/                         │       ├── orderService bean
    └── OrderController.java ────┘       ├── inventoryService bean
                                         └── orderController bean
```

Ba package Java khác nhau có thể đóng góp bean vào **cùng một context**. Cấu trúc thư mục bên trái chỉ mô tả cách tổ chức source; việc Spring đăng ký bean bên phải phụ thuộc vào cấu hình khởi động và các cơ chế đăng ký bean.

| Câu hỏi | Do package Java quyết định? | Do Spring context/cấu hình quyết định? |
|---|---|---|
| Tên đầy đủ của lớp là gì? | Có: `com.example.store.order.OrderService`. | Không. |
| Lớp package-private có thể được truy cập từ đâu? | Có: Java access control. | Spring không làm mất hiệu lực quy tắc Java. |
| Lớp có được tạo thành bean không? | Không trực tiếp. | Có: component scan, `@Bean`, `@Import` hoặc cơ chế đăng ký khác. |
| `OrderService` có inject được `InventoryService` không? | Package khác nhau không mặc nhiên cấm. | Phụ thuộc bean khả dụng, kiểu, qualifier và cấu hình context. |
| Bean được quản lý trong bao nhiêu container? | Không quyết định. | Do cách ứng dụng tạo/cấu hình các context. |
| Có cách ly dữ liệu, mạng hoặc tài nguyên OS không? | Không. | Một context cũng không tự tạo cách ly ở mức tiến trình/OS. |

## 2. Spring Boot mặc định tạo context như thế nào?

Một lớp khởi động tiêu biểu:

```java
package com.example.store;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StoreApplication {
    public static void main(String[] args) {
        SpringApplication.run(StoreApplication.class, args);
    }
}
```

Khi gọi `SpringApplication.run(...)`, Spring Boot chuẩn bị và khởi động một `ApplicationContext` thích hợp với loại ứng dụng và cấu hình hiện tại. Với một ứng dụng Boot thông thường, các bean nghiệp vụ trong những package được quét sẽ được quản lý bởi context chính của ứng dụng đó.

`@SpringBootApplication` kết hợp những năng lực cốt lõi của cấu hình ứng dụng Boot, trong đó có **component scanning** và **auto-configuration**. Với cách cấu hình mặc định, component scanning bắt đầu từ package chứa lớp có `@SpringBootApplication` và đi xuống các package con của nó.

Ví dụ:

```text
com.example.store
├── StoreApplication.java              <- package gốc của ứng dụng
├── order/
│   └── OrderService.java               <- được scan nếu là component phù hợp
├── inventory/
│   └── InventoryService.java           <- được scan nếu là component phù hợp
└── web/
    └── OrderController.java           <- được scan nếu là component phù hợp
```

Điểm cần nhớ là **component scanning xác định những lớp được xem xét để đăng ký bean**, còn **context xác định nơi các bean được quản lý**. Mở rộng hoặc thu hẹp phạm vi scanning có thể làm thay đổi tập bean trong context nhưng không tự tạo một context mới.

Ngoài component scan còn có auto-configuration và những cơ chế đăng ký bean khác. Vì vậy, không thể kết luận toàn bộ bean trong context đều phải nằm dưới package của lớp `StoreApplication`.

## 3. Ví dụ: package `order` vẫn dùng bean từ `inventory`

Giả sử dự án có package `com.example.store.order` và `com.example.store.inventory`. Để thấy rõ sự kết nối, tạo một service quản lý tồn kho:

**`src/main/java/com/example/store/inventory/InventoryService.java`**

```java
package com.example.store.inventory;

import org.springframework.stereotype.Service;

@Service
public class InventoryService {
    public boolean isAvailable(String sku) {
        return "SKU-001".equals(sku);
    }
}
```

Sau đó tạo service xử lý đơn hàng:

**`src/main/java/com/example/store/order/OrderService.java`**

```java
package com.example.store.order;

import com.example.store.inventory.InventoryService;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final InventoryService inventoryService;

    public OrderService(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    public String placeOrder(String sku) {
        return inventoryService.isAvailable(sku)
                ? "ACCEPTED"
                : "OUT_OF_STOCK";
    }
}
```

Điều gì xảy ra khi khởi chạy `StoreApplication`?

1. Component scanner nhìn thấy `InventoryService` và `OrderService` vì chúng thuộc các package con của `com.example.store` và được đánh dấu `@Service`.
2. Spring đăng ký bean definition tương ứng trong context của ứng dụng.
3. Khi tạo `OrderService`, Spring tìm bean kiểu `InventoryService` phù hợp với dependency ở constructor.
4. `OrderService` nhận bean đó và có thể gọi `isAvailable(...)`, dù hai lớp thuộc hai package khác nhau.

```text
com.example.store.order.OrderService
                │ constructor dependency
                ▼
com.example.store.inventory.InventoryService
                │
                ▼
          cùng Spring context
```

Package `order` không sở hữu một container riêng. Package `inventory` cũng không tự ẩn bean khỏi phần còn lại của ứng dụng. Ví dụ trên cố tình dùng dependency trực tiếp để làm rõ cơ chế; trong một thiết kế lớn, bạn có thể muốn giảm phụ thuộc này bằng các interface và quy tắc kiến trúc.

Ví dụ `isAvailable` chỉ mô phỏng dữ liệu và không phải cài đặt hệ thống quản lý tồn kho thực tế. Điều cần quan sát là **cách Spring nối hai bean**.

## 4. Đổi package có thể ảnh hưởng scanning nhưng không tạo context mới

Giả sử bạn chuyển `InventoryService` ra package **anh em** thay vì package con:

```text
com.example
├── store/
│   ├── StoreApplication.java
│   └── order/OrderService.java
└── shared/
    └── InventoryService.java
```

Nếu `StoreApplication` nằm trong `com.example.store`, cấu hình component scan mặc định thường **không phát hiện** lớp `com.example.shared.InventoryService`. Kết quả khi context tạo `OrderService` có thể là lỗi thiếu bean cho constructor.

Đây là lỗi **không tìm thấy/không đăng ký bean**, không phải bằng chứng `shared` đã có một context độc lập. Bản thân file Java vẫn có thể được biên dịch nếu classpath và Java access cho phép; vấn đề phát sinh lúc Spring giải quyết dependency trong container.

Một số cách có chủ đích để đăng ký bean ở ngoài package scan mặc định:

**Cách A — Đặt lớp khởi động tại package cha phù hợp.** Nếu cấu trúc dự án cho phép, đặt lớp `@SpringBootApplication` ở `com.example` sẽ khiến các package con của `com.example` nằm trong phạm vi component scan mặc định. Cách này cần cân nhắc vì phạm vi quá rộng có thể nhận thêm component không mong muốn.

**Cách B — Cấu hình rõ phạm vi component scan.** Chẳng hạn:

```java
package com.example.store;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(scanBasePackages = {
        "com.example.store",
        "com.example.shared"
})
public class StoreApplication {
    public static void main(String[] args) {
        SpringApplication.run(StoreApplication.class, args);
    }
}
```

Thêm `com.example.shared` vào scan vẫn nhằm **đăng ký thêm bean trong context đang chạy**; không tạo `SharedApplicationContext` riêng. Cần chú ý `scanBasePackages` tác động đến component scan, **không tự động thay thế mọi quy tắc phát hiện JPA entity và Spring Data repository**. Nếu dùng JPA, cần xem thêm cấu hình như `@EntityScan`, `@EnableJpaRepositories` và các quy tắc auto-configuration phù hợp.

**Cách C — Đăng ký bean tường minh.** Có thể dùng `@Import` với cấu hình/lớp phù hợp, hoặc khai báo `@Bean` trong một `@Configuration` đã được đăng ký:

```java
package com.example.store;

import com.example.shared.InventoryService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class InventoryConfiguration {
    @Bean
    InventoryService inventoryService() {
        return new InventoryService();
    }
}
```

Ở ví dụ này, giả sử `InventoryService` có constructor không đối số như code đã minh họa và package `InventoryConfiguration` thuộc phạm vi cấu hình. `@Bean` đăng ký đối tượng do factory method trả về vào **context chứa configuration đó**. Tránh đồng thời đăng ký nhiều bean cùng mục đích bằng nhiều cơ chế nếu không có lý do rõ ràng, vì có thể gây trùng tên hoặc mơ hồ khi inject.

Đừng sử dụng những cách trên một cách máy móc để “sửa lỗi scan” trước khi hiểu mục tiêu của cấu trúc package. Đặt package và điểm vào hợp lý thường đơn giản hơn việc liệt kê thủ công rất nhiều package.

## 5. Vì sao `@Service`, `@Component` hay `@Configuration` không phải dấu phân cách context?

Một nhầm lẫn khác là nhìn thấy các annotation khác nhau rồi suy ra chúng thuộc những container khác nhau.

| Annotation/khai báo | Tác dụng chính | Có tự tạo `ApplicationContext` mới? |
|---|---|---|
| `@Component` | Đánh dấu lớp là ứng viên component để đăng ký thành bean. | Không. |
| `@Service` | Stereotype cho thành phần nghiệp vụ; là biến thể của `@Component`. | Không. |
| `@Repository` | Stereotype cho lớp truy cập dữ liệu; có thể tham gia dịch ngoại lệ trong cấu hình phù hợp. | Không. |
| `@Controller` / `@RestController` | Đánh dấu thành phần web/controller để framework đăng ký. | Không. |
| `@Configuration` | Khai báo lớp cấu hình bean; các phương thức `@Bean` có thể đăng ký bean. | Không. |
| `@Bean` | Đăng ký đối tượng trả về từ một factory method vào container. | Không. |
| `@ComponentScan` | Xác định cách quét các ứng viên component. | Không. |
| `@Profile` / `@Conditional` | Điều kiện để cấu hình hoặc bean được đăng ký. | Không. |
| `@Scope` | Quy định scope của bean, ví dụ singleton hoặc prototype. | Không. |

Chẳng hạn, đặt `@Configuration` trong `com.example.store.payment` không khiến Spring mở một context mới cho package payment. Nếu lớp cấu hình được đăng ký trong context chính, các bean từ `@Bean` của nó cũng thuộc context đó.

**Bean scope cũng không phải context boundary**: bean `singleton` thông thường được quản lý theo container định nghĩa bean đó, còn `prototype` có thể tạo nhiều instance theo mỗi lần yêu cầu. Sự khác nhau về vòng đời bean không biến package chứa bean thành một container mới.

## 6. Làm sao biết các bean có cùng context?

Khi ứng dụng đang dùng một context chính, bạn có thể dùng `ApplicationContext` để quan sát các bean đã được đăng ký. Trong một test đặt cùng package gốc `com.example.store`:

```java
package com.example.store;

import com.example.store.inventory.InventoryService;
import com.example.store.order.OrderService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertSame;

@SpringBootTest
class StoreContextTests {

    @Autowired
    private ApplicationContext context;

    @Autowired
    private OrderService orderService;

    @Autowired
    private InventoryService inventoryService;

    @Test
    void findsBothServicesFromTheApplicationContext() {
        assertNotNull(orderService);
        assertSame(inventoryService, context.getBean(InventoryService.class));
        assertSame(orderService, context.getBean(OrderService.class));
    }
}
```

Test này minh họa cách hai service được lấy từ `ApplicationContext` của ứng dụng kiểm thử. Nó giả định có dependency test Spring Boot/JUnit và các bean từ ví dụ trên được đăng ký đúng. Trong ứng dụng có nhiều context theo dạng parent-child, thao tác `getBean(...)` có thể tìm thấy bean từ parent; muốn xác định **nơi bean thực sự được định nghĩa**, cần phân biệt bean local của context với bean được kế thừa trong hierarchy.

Một cách quan sát thêm là in `context.getId()` hoặc khảo sát danh sách bean definition tại context cụ thể. **Không nên suy ra có bao nhiêu context chỉ bằng việc đếm package hoặc đếm annotation `@Service`.**

## 7. Một JVM, một ứng dụng và một context có phải luôn là một không?

Không hoàn toàn. Các khái niệm này ở những tầng khác nhau:

- **JVM/tiến trình Java** cung cấp môi trường thực thi. Một tiến trình có thể chạy code tạo nhiều Spring context.
- **Spring Boot application** là khái niệm khởi động và cấu hình một ứng dụng. Trong đường chạy phổ biến, nó tạo một context chính.
- **`ApplicationContext`** là container quản lý tập bean cụ thể. Các context khác nhau có thể nằm trong cùng một tiến trình, thậm chí được sắp theo quan hệ parent-child.
- **Package** chỉ là cấu trúc tên và tổ chức lớp Java. Nó không quyết định số lượng tiến trình, số ứng dụng hoặc số context.

Sơ đồ phân biệt hai tình huống:

```text
Tình huống thường gặp:

Java process
└── JVM
    └── Spring Boot application
        └── ApplicationContext A
            ├── orderService  (package order)
            ├── inventoryService (package inventory)
            └── orderController (package web)

Tình huống được cấu hình riêng:

Java process
└── JVM
    ├── ApplicationContext A
    │   ├── bean ở package order
    │   └── bean ở package shared
    └── ApplicationContext B
        ├── bean ở package inventory
        └── bean ở package shared
```

Context A và B không xuất hiện vì source được chia thành package A/B. Chúng chỉ xuất hiện khi chương trình hoặc framework **thực sự khởi tạo nhiều container**. Các class ở cùng package thậm chí có thể được đăng ký trong hai context khác nhau, tạo hai bean instance khác nhau. Vì thế, tên package không đủ để suy ra bean instance hay vòng đời runtime.

## 8. Context khác nhau được kết nối thế nào?

Trong các trường hợp nâng cao, Spring hỗ trợ tạo nhiều context và có thể thiết lập **context hierarchy**:

```text
Parent ApplicationContext
├── sharedConfiguration
└── sharedService
          │
          └── parent visible to children
                   │
           ┌───────┴────────┐
           ▼                ▼
Child Context A       Child Context B
├── orderService      ├── inventoryService
└── orderController   └── inventoryController
```

Với cấu hình hierarchy, child context thường có thể tra cứu bean trong parent nếu không bị bean local che khuất, nhưng parent không tự động nhìn thấy bean chỉ tồn tại trong child. Hai child context cũng không mặc nhiên nhìn trực tiếp được bean local của nhau. Quy tắc cụ thể phụ thuộc cách cấu hình và sử dụng bean factory/context hierarchy.

Ngược lại, hai context độc lập không có quan hệ parent-child thì không tự chia sẻ bean registry chỉ vì nằm trong cùng một JVM. Muốn kết nối chúng phải có cơ chế rõ ràng: chia sẻ đối tượng qua cấu hình chủ đích, dùng API/service integration hoặc giao tiếp giữa các thành phần theo thiết kế.

Tạo nhiều context có chi phí về cấu hình, lifecycle, quan sát và xử lý dependency. Với một Spring Boot application cơ bản, **không cần tạo context mới chỉ để tách package `order` khỏi `inventory`**. Mục tiêu thông thường của việc chia package là tổ chức mã và kiểm soát phụ thuộc, có thể thực hiện trước ở cấp kiến trúc source.

## 9. Ranh giới kiến trúc phải do thiết kế và quy tắc bảo vệ

Giả sử nhóm phát triển muốn các chức năng `order` và `inventory` tương đối độc lập. Chia hai package là bước khởi đầu có ích, nhưng quy ước thư mục không tự cấm các dependency không mong muốn:

```text
com.example.store
├── order/
│   ├── api/OrderFacade.java
│   ├── internal/OrderService.java
│   └── internal/OrderCalculator.java
└── inventory/
    ├── api/InventoryQuery.java
    └── internal/InventoryRepositoryAdapter.java
```

Tên `api` và `internal` truyền tải ý định thiết kế. Tuy vậy, chỉ tên folder/package **không làm Java ngăn việc gọi vào `internal`** nếu lớp và thành viên vẫn `public` và classpath cho phép. Những biện pháp giúp giữ ranh giới rõ ràng hơn gồm:

1. **Định nghĩa API rõ ràng**: phần khác nên phụ thuộc vào giao diện hoặc service được công bố, thay vì truy cập thẳng lớp cài đặt nội bộ.
2. **Sử dụng đúng Java access modifiers**: không đưa `public` lên mọi lớp nếu không cần; cân nhắc package-private cho các lớp chi tiết cài đặt.
3. **Áp dụng chiều phụ thuộc nhất quán**: tránh chu trình `order → inventory → order`; nếu cần phối hợp, thiết kế một abstraction hoặc quy trình điều phối phù hợp.
4. **Đặt quy tắc kiểm tra kiến trúc**: dùng kiểm tra tĩnh, test quy tắc phụ thuộc hoặc công cụ phù hợp để phát hiện khi code vượt ranh giới.
5. **Xem xét module hóa khi bài toán thực sự cần**: Maven/Gradle subproject, JPMS hoặc phương pháp modular monolith có thể làm ranh giới nguồn và build rõ hơn, mỗi cơ chế có đánh đổi riêng.

Trong hệ sinh thái Spring, **Spring Modulith** là một lựa chọn hỗ trợ mô hình hóa và xác minh những module logic trong một ứng dụng Spring Boot. Nó không đồng nghĩa với việc mỗi package/module logic tự có một `ApplicationContext` riêng. Mục đích của cách tiếp cận này thường là kiểm soát cấu trúc và tương tác trong một ứng dụng, chứ không phải tự động tách thành nhiều tiến trình.

### Ví dụ ranh giới API giữa hai package

Một package inventory có thể công bố interface đơn giản:

```java
package com.example.store.inventory.api;

public interface InventoryQuery {
    boolean isAvailable(String sku);
}
```

Phần cài đặt nội bộ:

```java
package com.example.store.inventory.internal;

import com.example.store.inventory.api.InventoryQuery;
import org.springframework.stereotype.Service;

@Service
class InventoryQueryService implements InventoryQuery {
    @Override
    public boolean isAvailable(String sku) {
        return "SKU-001".equals(sku);
    }
}
```

Service đơn hàng chỉ import interface:

```java
package com.example.store.order;

import com.example.store.inventory.api.InventoryQuery;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final InventoryQuery inventory;

    public OrderService(InventoryQuery inventory) {
        this.inventory = inventory;
    }

    public boolean canPlaceOrder(String sku) {
        return inventory.isAvailable(sku);
    }
}
```

Khi package gốc vẫn được scan và chỉ có một bean thích hợp cho `InventoryQuery`, Spring có thể inject cài đặt đó vào constructor qua interface. Cả hai vẫn nằm trong **cùng context**, nhưng ở cấp source, `order` ít bị phụ thuộc vào chi tiết cài đặt của `inventory` hơn.

Trong ví dụ này, `InventoryQueryService` được để package-private theo chủ đích; code ngoài `inventory.internal` không thể tham chiếu trực tiếp lớp đó bằng kiểu Java thông thường. Spring vẫn có khả năng đăng ký các lớp component không `public` trong cấu hình phù hợp. Đây là **ranh giới truy cập Java**, không phải một cơ chế cách ly Spring context hay bảo mật tuyệt đối.

## 10. Tách package không đồng nghĩa với tách giao dịch, dữ liệu hay bảo mật

Khi các bean trong `order` và `inventory` dùng chung một `ApplicationContext`, việc tách tên package **không tự mang lại**:

- Database riêng, schema riêng hoặc quyền truy cập dữ liệu riêng.
- Transaction manager độc lập hoặc ranh giới transaction theo package.
- Thread pool, heap hoặc tài nguyên JVM được cách ly cho từng package.
- Quy tắc authentication/authorization riêng cho từng package.
- Circuit breaker, timeout hoặc network boundary như giữa các dịch vụ qua HTTP.

Ví dụ `@Transactional` tác động lên lời gọi được Spring quản lý theo proxy/aspect và transaction configuration tương ứng; **không phải** vì phương thức nằm trong package `order` nên nó tự có giao dịch độc lập khỏi package `inventory`. Nếu hai service cùng tham gia một transaction, kết quả phụ thuộc vào cách gọi, propagation, transaction manager và nguồn dữ liệu, không phụ thuộc riêng tên package.

Tương tự, đặt mã xử lý thanh toán ở `com.example.store.payment` không tự bảo vệ nó khỏi lời gọi trái phép. Ranh giới bảo mật cần các cơ chế xác thực, phân quyền, chính sách truy cập và kiểm soát dữ liệu thực sự. Quy ước package chỉ giúp người lập trình biết nơi đặt những cơ chế đó.

## 11. Phân biệt package scan với cấu trúc test context

Spring Boot Test có thể tạo **test ApplicationContext** riêng cho từng cấu hình kiểm thử. Ví dụ:

- `@SpringBootTest` thường khởi động Spring test context dựa trên cấu hình ứng dụng để kiểm tra sự tích hợp ở phạm vi rộng.
- `@WebMvcTest` hướng đến một phần cấu hình web MVC; các bean service khác có thể không hiện diện tự động và cần cách cung cấp dependency phù hợp cho test.
- Các test khác nhau có thể dùng lại context được Spring Test cache khi cấu hình tương thích, hoặc tạo context khác khi cấu hình thay đổi.

Điều này **không chứng minh mỗi package có context riêng**. Spring Test quyết định phạm vi test context theo annotation, cấu hình và cơ chế cache, không tự động tạo một context riêng cho `order` và một context riêng cho `inventory` chỉ vì chúng nằm ở hai package.

Vì vậy, khi `OrderService` inject được `InventoryService` trong ứng dụng thật nhưng không inject được trong một slice test, nguyên nhân có thể nằm ở **phạm vi test configuration**, không phải package đã tự cách ly hai bean. Đọc đúng annotation test và bean được nạp sẽ giúp chẩn đoán vấn đề.

## 12. Những triệu chứng dễ bị giải thích sai

| Tình huống | Suy luận dễ sai | Cách hiểu đúng |
|---|---|---|
| Chuyển `@Service` ra package ngoài package gốc rồi startup báo thiếu bean. | “Package mới đã mở một Spring context khác.” | Bean có thể nằm ngoài component scan; cần kiểm tra cơ chế đăng ký. |
| Hai `@Service` ở hai package inject được nhau. | “Spring đã kết nối hai context riêng.” | Chúng có thể cùng thuộc một context và được inject bình thường. |
| Hai package có cùng một kiểu repository và cùng database. | “Mỗi package sẽ có repository/transaction riêng.” | Ranh giới database/transaction được quyết định bởi cấu hình cụ thể, không bởi package. |
| `@Configuration` đặt dưới `config/payment`. | “Đây là Payment Context.” | Đây là lớp cấu hình; bean được đăng ký vào context chứa cấu hình ấy. |
| Thêm `@ComponentScan` cho package `shared`. | “Spring sẽ tạo thêm Shared Context.” | Spring mở rộng phạm vi tìm component cho context đang cấu hình. |
| Một test MVC không thấy service của package khác. | “Hai package không giao tiếp được.” | Slice test có thể chủ động chỉ nạp một phần bean. |
| Một lớp `public` trong `inventory.internal` được `order` import. | “Tên `internal` đã cấm phụ thuộc.” | Java vẫn cho phép truy cập nếu visibility và dependency cho phép; cần quy tắc kiến trúc rõ. |
| Hai class cùng package được đăng ký ở hai context. | “Chắc chắn chỉ có một instance vì chúng cùng package.” | Context khác nhau có thể chứa bean instance độc lập theo cấu hình và scope. |

Nếu gặp lỗi `NoSuchBeanDefinitionException` hoặc thông báo `required a bean of type ... that could not be found`, hãy lần lượt xem lớp có thực sự được đăng ký không, phạm vi scan, điều kiện `@Profile`/`@Conditional`, bean configuration/import và loại context đang chạy. **Đừng bắt đầu bằng giả thuyết mỗi folder/package là một container độc lập.**

## 13. Bài tập thực hành

### Bài tập 1 — Hai package, một context

Tạo project Spring Boot có package gốc `com.example.store`; thêm `InventoryService` và `OrderService` theo ví dụ phần 3. Đảm bảo starter cần thiết cho Spring context có mặt trong file build. Khởi động ứng dụng hoặc chạy test phần 6 và xác nhận Spring có thể lấy cả hai service qua constructor injection.

**Quan sát mong đợi:** Hai lớp ở hai package nhưng được đăng ký trong cùng application context thông thường. Quan hệ package không ngăn việc inject dependency.

### Bài tập 2 — Dời một service ra ngoài package scan mặc định

Chuyển `InventoryService` sang `com.example.shared`. Giữ `StoreApplication` trong `com.example.store` rồi thử chạy. Quan sát lỗi thiếu bean nếu không có cơ chế đăng ký khác. Sau đó dùng component scan có phạm vi tường minh hoặc khai báo bean hợp lệ để phục hồi dependency.

**Câu hỏi:** Động tác nào làm thay đổi **việc đăng ký bean**? Có bước nào ở bài tập tự tạo một context độc lập không?

### Bài tập 3 — Giới hạn phụ thuộc ở cấp source

Đổi dependency của `OrderService` từ lớp concrete `InventoryService` sang interface `InventoryQuery`, rồi đặt implementation package-private trong `inventory.internal`. Thử viết code ở package `order` tham chiếu trực tiếp tên lớp implementation. Trình biên dịch Java sẽ áp dụng quy tắc visibility, trong khi Spring vẫn có thể inject implementation qua interface nếu bean được đăng ký phù hợp.

**Quan sát mong đợi:** Có thể thiết lập một số giới hạn truy cập và quy tắc phụ thuộc **mà không cần nhân số lượng Spring context**.

### Bài tập 4 — So sánh application context và test slice

Khi đã học phần kiểm thử Spring, dùng một test `@SpringBootTest` để lấy `OrderService` và `InventoryService`. Sau đó tạo một test `@WebMvcTest` cho controller dùng `OrderService`; quan sát bean nào được nạp và bổ sung test dependency bằng cách phù hợp. Giải thích kết quả bằng phạm vi test configuration, không bằng số lượng package.

## 14. Cách tư duy đúng khi thiết kế cấu trúc Spring Boot

Khi đặt câu hỏi “Tách `order` và `inventory` như thế nào?”, nên xác định **ranh giới nào bạn thực sự muốn**:

| Mục tiêu | Công cụ/ý tưởng thường phù hợp |
|---|---|
| Mã dễ tìm, có tên rõ ràng | Java package theo tính năng hoặc tầng. |
| Chỉ công bố một số API giữa các phần | Interface, access modifier, quy tắc dependency và architecture tests. |
| Giảm phụ thuộc giữa các module nghiệp vụ | Modular monolith, cấu trúc module rõ ràng và kiểm tra phụ thuộc. |
| Điều khiển bean nào tồn tại | Component scan, `@Bean`, `@Import`, conditional configuration. |
| Cần nhiều tập bean/lifecycle được quản lý độc lập | Chủ động cấu hình nhiều `ApplicationContext`, nếu thật sự cần. |
| Cần cách ly tiến trình, scale/deploy độc lập | Kiến trúc triển khai và runtime riêng, kèm giao tiếp thích hợp. |
| Cần bảo vệ dữ liệu và endpoint | Authentication, authorization và các cơ chế kiểm soát truy cập thực tế. |

**Package là một công cụ tổ chức mã nguồn. Spring `ApplicationContext` là container runtime quản lý bean.** Việc có nhiều package không đồng nghĩa có nhiều context, và việc hai bean thuộc hai package không ngăn chúng được Spring inject trong cùng ứng dụng. Muốn một ranh giới được thực thi thật sự, bạn phải thiết kế và cấu hình cơ chế tương ứng với loại ranh giới đó.

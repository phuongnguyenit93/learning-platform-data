# Phân biệt metadata module với bean instance

Trong một ứng dụng Spring Boot dùng Spring Modulith, từ “module” và “bean” nói về hai khía cạnh khác nhau. **Application module** là ranh giới kiến trúc dùng để nhóm mã nguồn theo trách nhiệm nghiệp vụ. **Spring bean** là một đối tượng được Spring IoC container tạo và quản lý trong lúc ứng dụng chạy.

Spring Modulith mô tả module bằng metadata như package gốc, tên hiển thị, API công khai và các quan hệ phụ thuộc. Spring container quản lý những object instance như `OrderService`, `ProductCatalog` hoặc `StockRepository`. Metadata cho biết cấu trúc ứng dụng; bean instance thực hiện công việc khi ứng dụng hoạt động.

## 1. Application module là mô hình kiến trúc

Giả sử ứng dụng bán hàng có các module `catalog`, `orders` và `inventory`:

```text
com.example.shop
├── ShopApplication.java
├── catalog
│   ├── ProductCatalog.java
│   └── internal
│       └── ProductCatalogService.java
├── orders
│   ├── OrderManagement.java
│   └── internal
│       └── OrderService.java
└── inventory
    ├── StockAvailability.java
    └── internal
        └── StockService.java
```

Spring Modulith phân tích cấu trúc package để nhận diện các application module. Mỗi module đại diện cho một phần của ứng dụng, có base package và ranh giới API riêng. Module `orders` chẳng hạn, quản lý mã nguồn thuộc `com.example.shop.orders` và có thể công khai `OrderManagement` cho module khác sử dụng.

Ta có thể khai báo metadata của module ở `package-info.java`:

```java
@org.springframework.modulith.ApplicationModule(
    displayName = "Quản lý đơn hàng",
    allowedDependencies = {"catalog", "inventory"}
)
package com.example.shop.orders;
```

`@ApplicationModule` cung cấp thông tin và quy tắc cho mô hình kiến trúc. Annotation này không phải `@Component` hay `@Service`, vì vậy nó không yêu cầu Spring tạo một object bean đại diện cho module `orders`.

Tương tự, `@NamedInterface` có thể đánh dấu một package là API được công khai. Annotation đó xác định ranh giới truy cập ở cấp kiến trúc; nó không tạo ra một bean hay một object proxy để đại diện cho API.

## 2. Bean instance là đối tượng runtime do Spring quản lý

Spring bean là object mà Spring IoC container quản lý. Bean thường được đăng ký thông qua các stereotype như `@Component`, `@Service`, `@Repository`, `@Controller`, hoặc thông qua phương thức `@Bean` trong một lớp `@Configuration`.

Ví dụ, module `orders` có một service:

```java
package com.example.shop.orders.internal;

import org.springframework.stereotype.Service;

@Service
class OrderService {

    private final OrderRepository repository;

    OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    // Các thao tác xử lý đơn hàng
}
```

Khi Spring khởi tạo application context và phát hiện bean definition này, container tạo hoặc cung cấp một bean instance của `OrderService`, đồng thời inject dependency `OrderRepository` theo cấu hình. Mặc định, bean có scope singleton nên container thường quản lý một instance cho mỗi bean definition trong một application context. Nếu khai báo scope khác, vòng đời và số lượng instance có thể khác.

Bean cũng có thể được đăng ký bằng phương thức `@Bean`:

```java
@Configuration
class OrderConfiguration {

    @Bean
    OrderPolicy orderPolicy() {
        return new OrderPolicy();
    }
}
```

Trong ví dụ này, `OrderPolicy` là kiểu của object được tạo; `orderPolicy` là tên bean mặc định theo tên phương thức; object được trả về từ phương thức là bean instance do Spring quản lý.

## 3. Một module có thể chứa nhiều bean và nhiều loại lớp

Ranh giới application module không tương ứng một-một với bean instance. Một module nghiệp vụ thường chứa nhiều bean phối hợp với nhau, cùng các kiểu dữ liệu không phải bean.

Ví dụ module `orders` có thể chứa:

| Thành phần | Vai trò | Có nhất thiết là Spring bean? |
|---|---|---|
| `OrderService` | Điều phối nghiệp vụ đơn hàng | Thường có, nếu được đăng ký với Spring |
| `OrderRepository` | Truy cập dữ liệu đơn hàng | Có thể là bean, ví dụ repository do Spring Data tạo |
| `Order` | Mô hình dữ liệu hoặc entity | Không nhất thiết |
| `CreateOrderCommand` | Dữ liệu đầu vào cho use case | Thường không |
| `OrderStatus` | Enum trạng thái đơn hàng | Không |
| `OrderConfiguration` | Cấu hình các bean của module | Bản thân lớp cấu hình thường là bean nếu được Spring đăng ký; các phương thức `@Bean` tạo thêm bean |

Những lớp như entity, DTO, enum và value object vẫn thuộc mã nguồn của module dù Spring không quản lý chúng như bean. Vì thế, đếm số bean không cho biết một module có bao nhiêu thành phần mã nguồn hoặc ranh giới nghiệp vụ của module nằm ở đâu.

Ngược lại, một module có thể chỉ có một vài bean nhưng vẫn là một application module hoàn chỉnh nếu nó có trách nhiệm nghiệp vụ và ranh giới rõ ràng. Ranh giới module được thiết kế theo trách nhiệm và phụ thuộc, không theo số lượng object runtime.

## 4. Metadata module không phải bean đại diện cho module

Khi tạo mô hình bằng Spring Modulith:

```java
ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
```

`ApplicationModules` là mô hình chứa các application module được phát hiện. Mỗi `ApplicationModule` mô tả một module trong cấu trúc ứng dụng. Đây là các đối tượng mô hình của thư viện Spring Modulith, không phải những bean nghiệp vụ được Spring tự động đăng ký trong application context.

Có thể hình dung sự khác nhau như sau:

```text
Phân tích kiến trúc                         Ứng dụng đang chạy
-------------------                         ------------------
ApplicationModules                          Spring ApplicationContext
       |                                               |
       v                                               v
ApplicationModule                              Bean instances
       |                                      +---------+---------+
       v                                      |         |         |
Base package, API, dependencies            OrderService  Repository  OrderPolicy
```

Vế trái trả lời module nào tồn tại và quan hệ kiến trúc giữa chúng. Vế phải là các object thực thi do Spring container quản lý. Mô hình bên trái có thể được tạo để kiểm tra cấu trúc mà không cần khởi chạy toàn bộ application context hay tạo các bean nghiệp vụ ở vế phải.

## 5. Kiểm tra metadata và kiểm tra bean là hai việc khác nhau

Ta có thể kiểm tra cấu trúc module bằng một bài test kiến trúc:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Kiểm thử này phân tích cấu trúc mã nguồn theo package gốc và kiểm tra các quy tắc module mà Spring Modulith áp dụng, chẳng hạn phụ thuộc giữa module hoặc truy cập package nội bộ. Nó không phải bài kiểm tra xem `OrderService` đã được Spring tạo thành bean instance hay chưa.

Nếu cần xác minh bean được đăng ký trong Spring context, hãy dùng một bài kiểm thử Spring phù hợp, chẳng hạn `@SpringBootTest` hoặc một context test nhỏ:

```java
package com.example.shop.orders.internal;

import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

@SpringBootTest
class OrderServiceContextTests {

    @Autowired
    ApplicationContext context;

    @Test
    void registersOrderServiceBean() {
        assertNotNull(context.getBean(OrderService.class));
    }
}
```

Đoạn kiểm thử thứ hai khởi tạo Spring context để lấy bean từ container. Nó trả lời câu hỏi về cấu hình và vòng đời runtime, trong khi `ApplicationModules.verify()` trả lời câu hỏi về kiến trúc module. Một kiểm thử có thể thành công trong khi kiểm thử kia thất bại, vì hai kiểm thử kiểm tra những điều kiện khác nhau.

## 6. Quan hệ giữa module dependency và bean dependency

Khi `OrderService` sử dụng `ProductCatalog`, object graph lúc chạy có thể chứa một bean của `OrderService` tham chiếu đến bean cung cấp chức năng catalog. Ở cấp kiến trúc, việc mã nguồn của `orders` tham chiếu API của `catalog` tạo nên quan hệ phụ thuộc giữa hai application module.

```text
Application module:
orders  -------------------->  catalog

Runtime bean graph:
OrderService instance  ----->  ProductCatalog bean instance
```

Hai quan hệ có liên quan nhưng không đồng nhất. Quan hệ module mô tả hướng phụ thuộc được phép trong thiết kế. Quan hệ bean mô tả các object được nối với nhau trong Spring context bằng dependency injection hoặc cơ chế khác.

Ví dụ, `allowedDependencies` trong `@ApplicationModule` là quy tắc metadata giới hạn module `orders` được phụ thuộc vào module nào. Nó không tự tạo dependency injection, không khởi tạo `ProductCatalog` và cũng không thay thế cấu hình bean. Việc inject vẫn cần các bean definition và cơ chế wiring hợp lệ của Spring.

Nếu một module có nhiều bean, các bean trong cùng module có thể gọi nhau mà không tạo thêm một module dependency. Khi một bean sử dụng kiểu thuộc module khác, quan hệ đó cần tuân thủ API công khai và quy tắc phụ thuộc mà kiến trúc đã khai báo.

## 7. Cách dùng đúng hai khái niệm trong thực tế

Khi thiết kế một ứng dụng Spring Modulith, hãy bắt đầu từ module nghiệp vụ: xác định package gốc, API công khai, phần triển khai nội bộ và những module được phép phụ thuộc. Dùng metadata như `@ApplicationModule` và `@NamedInterface` để mô tả ranh giới, sau đó dùng `ApplicationModules.verify()` để kiểm tra cấu trúc.

Tiếp theo, trong từng module, xác định thành phần nào cần được Spring quản lý. Đăng ký service, repository, adapter và cấu hình phù hợp làm bean; giữ entity, DTO, enum và các kiểu dữ liệu thuần Java ở dạng object thông thường nếu chúng không cần vòng đời do container quản lý.

| Câu hỏi | Khái niệm cần xem xét |
|---|---|
| Phần nghiệp vụ này thuộc package và ranh giới nào? | Application module metadata |
| Module nào được phép phụ thuộc vào module nào? | Module dependencies và quy tắc kiến trúc |
| Đối tượng nào được Spring tạo và inject? | Bean definition và bean instance |
| Service đã được đăng ký trong application context chưa? | Kiểm thử Spring context |
| Ranh giới package có bị vi phạm không? | `ApplicationModules.verify()` |

Giữ riêng hai góc nhìn này giúp tránh việc tìm một bean đại diện cho mỗi module hoặc cho rằng mọi lớp trong module đều là bean. Spring Modulith mô tả cấu trúc và quy tắc của ứng dụng; Spring IoC container quản lý các đối tượng cần thiết để ứng dụng thực thi nghiệp vụ.

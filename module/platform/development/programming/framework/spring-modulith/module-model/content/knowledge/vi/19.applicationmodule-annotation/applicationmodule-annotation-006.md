# sharedModules cho kiểm thử module

Trong một ứng dụng Spring Modulith, một số mô-đun có thể chứa cấu hình Spring hoặc thành phần dùng chung cho hầu hết các mô-đun nghiệp vụ. Ví dụ, ứng dụng có thể có mô-đun `shared` cung cấp `Clock`, cấu hình serialization, một số bean hạ tầng hoặc cấu hình bảo mật dùng chung. Khi chạy `@ApplicationModuleTest` ở chế độ `STANDALONE`, Spring Modulith mặc định chỉ bootstrap mô-đun đang được kiểm thử. Nếu các bean dùng chung không được nạp, context có thể thiếu dependency cần thiết.

Thuộc tính `sharedModules` của `@Modulithic` giải quyết trường hợp này. Nó khai báo tên các application module được xem là dùng chung và luôn được đưa vào bootstrap của các application module integration test, bất kể test đang dùng `STANDALONE`, `DIRECT_DEPENDENCIES` hay `ALL_DEPENDENCIES`.

Các ví dụ kiểm thử cần artifact `spring-modulith-starter-test` trong test scope. Nếu dự án đã quản lý version bằng Spring Modulith BOM, có thể khai báo dependency mà không ghi version:

```xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

## 1. Nhận diện mô-đun dùng chung

Giả sử ứng dụng bán hàng có cấu trúc package:

```text
com.acme.shop
├── ShopApplication.java
├── shared
│   └── configuration
│       └── TimeConfiguration.java
├── orders
│   └── OrderService.java
├── inventory
│   └── InventoryService.java
└── customers
    └── CustomerService.java
```

Theo quy tắc phát hiện mặc định, `shared`, `orders`, `inventory` và `customers` là các application module trực tiếp bên dưới package gốc `com.acme.shop`. Mô-đun `shared` có thể chứa cấu hình hoặc bean được dùng trong nhiều module test.

Ví dụ, mô-đun `shared` cung cấp một bean `Clock`:

```java
package com.acme.shop.shared.configuration;

import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TimeConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

Các service trong mô-đun nghiệp vụ có thể inject `Clock` để kiểm soát thời gian và giúp test dễ dự đoán hơn. Vì bean được khai báo trong một module riêng, module test cần bootstrap module `shared` nếu muốn sử dụng cấu hình đó.

## 2. Khai báo sharedModules trên lớp ứng dụng

Đặt `@Modulithic` trên lớp Spring Boot application và liệt kê tên logic của các mô-đun cần được bootstrap chung:

```java
package com.acme.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.modulith.Modulithic;

@Modulithic(sharedModules = "shared")
@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Nếu có nhiều mô-đun dùng chung, truyền một mảng tên module:

```java
@Modulithic(sharedModules = { "shared", "observability" })
@SpringBootApplication
public class ShopApplication {
    // main method
}
```

`sharedModules` nhận tên mô-đun dưới dạng `String[]` và mặc định là mảng rỗng nếu không cấu hình. Trong ví dụ, `shared` và `observability` là tên logic của application module, không phải tên lớp Java hay đường dẫn thư mục tùy ý. Hãy dùng tên mà module model thực sự nhận diện. Nếu ứng dụng tùy chỉnh cách đặt tên module, kiểm tra tên hiển thị trong model trước khi khai báo.

`@Modulithic` được đặt trên lớp ứng dụng chính để cấu hình toàn bộ module arrangement. Thuộc tính `sharedModules` không được khai báo trên `@ApplicationModule` của từng package và cũng không phải thuộc tính của `@ApplicationModuleTest`.

Nếu ứng dụng dùng annotation tổng hợp `@Modulith`, annotation này đã bao gồm `@Modulithic` và `@SpringBootApplication`; có thể khai báo `sharedModules` trực tiếp trên `@Modulith`:

```java
package com.acme.shop;

import org.springframework.modulith.Modulith;

@Modulith(sharedModules = "shared")
public class ShopApplication {
    // main method
}
```

Hãy dùng một cách khai báo phù hợp với cấu trúc hiện có của dự án. Không cần đặt cả `@Modulith` và `@SpringBootApplication` trên cùng lớp vì `@Modulith` đã là annotation tổng hợp cho Spring Boot application.

## 3. sharedModules ảnh hưởng tới bootstrap mode như thế nào?

`sharedModules` được cộng vào phạm vi bootstrap của module integration test, bất kể `mode` của `@ApplicationModuleTest`:

| Bootstrap mode | Mô-đun được nạp theo mode | Mô-đun được thêm từ `sharedModules` |
|---|---|---|
| `STANDALONE` | Chỉ mô-đun đang kiểm thử | Tất cả mô-đun đã khai báo là shared |
| `DIRECT_DEPENDENCIES` | Mô-đun đang kiểm thử và các dependency trực tiếp | Tất cả mô-đun đã khai báo là shared |
| `ALL_DEPENDENCIES` | Mô-đun đang kiểm thử và toàn bộ dependency bắc cầu | Tất cả mô-đun đã khai báo là shared |

Ví dụ, `orders` có module test:

```java
package com.acme.shop.orders;

import java.time.Clock;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest(mode = ApplicationModuleTest.BootstrapMode.STANDALONE)
class OrderModuleTests {

    @Autowired
    Clock clock;

    @Test
    void sharedClockIsAvailable() {
        // Clock được cung cấp bởi module shared.
    }
}
```

Mặc dù test dùng `STANDALONE`, module `shared` vẫn được bootstrap vì đã được khai báo trên `@Modulithic`. Các mô-đun khác không được tự động nạp chỉ vì `shared` được nạp; phạm vi còn lại vẫn theo bootstrap mode.

Nếu một module test ở chế độ `DIRECT_DEPENDENCIES`, các dependency trực tiếp của module đó vẫn được xác định theo module graph. `sharedModules` chỉ bổ sung các module đã đánh dấu shared vào tập bootstrap.

## 4. sharedModules khác extraIncludes như thế nào?

Spring Modulith có hai cách phổ biến để thêm module vào một module test:

- `sharedModules` trên `@Modulithic`: khai báo ở cấp ứng dụng, áp dụng cho mọi application module integration test.
- `extraIncludes` trên `@ApplicationModuleTest`: khai báo ở cấp test class, chỉ thêm module cần thiết cho test đó, độc lập với bootstrap mode.

Ví dụ, chỉ một test của `orders` cần module `audit`:

```java
package com.acme.shop.orders;

import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest(
    mode = ApplicationModuleTest.BootstrapMode.STANDALONE,
    extraIncludes = "audit"
)
class OrderAuditIntegrationTests {
    // Chỉ test này thêm module audit vào bootstrap.
}
```

Không cần đưa `audit` vào `sharedModules` nếu chỉ một vài test cần nó. Ngược lại, nếu `shared` chứa cấu hình Spring thực sự cần có trong mọi module test, khai báo một lần ở `@Modulithic` giúp các test nhất quán.

| Tiêu chí | `sharedModules` | `extraIncludes` |
|---|---|---|
| Khai báo tại | `@Modulithic` hoặc `@Modulith` trên lớp ứng dụng | `@ApplicationModuleTest` trên test class |
| Phạm vi | Toàn bộ application module integration tests | Một test class cụ thể |
| Mục đích | Module dùng chung ở nhiều test | Module bổ sung cho một tình huống kiểm thử |
| Kết hợp với bootstrap mode | Luôn được thêm vào bất kể mode | Được thêm vào ngoài phạm vi do mode xác định |

## 5. Khi nào nên đưa module vào sharedModules?

Một module phù hợp để đánh dấu shared khi nó cung cấp cấu hình hoặc thành phần hạ tầng có tính dùng chung thực sự. Ví dụ:

- Cấu hình `Clock` hoặc `ClockProvider` để các test kiểm soát thời gian.
- Cấu hình serialization dùng chung cho application event hoặc message converter.
- Bean cung cấp thông tin tenant hoặc một context kỹ thuật xuyên suốt ứng dụng.
- Cấu hình Spring chung mà nhiều module test cần để khởi tạo context.
- Thành phần hạ tầng ổn định mà sự hiện diện của nó là điều kiện nền tảng cho module test.

Không nên đánh dấu một module nghiệp vụ là shared chỉ vì nhiều module khác phụ thuộc vào nó. Nếu `pricing` chứa logic tính giá nghiệp vụ và `orders`, `catalog` cùng sử dụng, đó vẫn là một module nghiệp vụ có dependency rõ ràng. Hãy để bootstrap mode hoặc `extraIncludes` thể hiện nhu cầu tích hợp cụ thể của từng test.

Một shared module tốt nên nhỏ, ổn định và ít thay đổi. Nếu module chứa nhiều service nghiệp vụ, repository hoặc logic thay đổi thường xuyên, đưa nó vào mọi module test sẽ làm tăng coupling giữa các test và khiến context khó hiểu.

## 6. sharedModules và quy tắc dependency

`sharedModules` có hai tác dụng:

1. Thêm các mô-đun được khai báo vào bootstrap của mọi `@ApplicationModuleTest`, bất kể bootstrap mode.
2. Đánh dấu các mô-đun đó là dependency được phép khi Spring Modulith xác minh `allowedDependencies`.

Vì vậy, nếu `shared` đã được khai báo trong `@Modulithic(sharedModules = "shared")`, consumer không cần lặp lại `shared` trong `allowedDependencies` chỉ để cho phép dependency tới mô-đun đó. Ví dụ, allow-list sau vẫn cho phép `orders` phụ thuộc vào `shared`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory"
)
package com.acme.shop.orders;
```

Tuy nhiên, quyền dependency được cho phép không tự tạo ra một tham chiếu mã nguồn hoặc một cạnh trong module graph. Cạnh `orders → shared` chỉ xuất hiện khi mã nguồn thực sự phụ thuộc vào một kiểu hoặc bean thuộc `shared`, chẳng hạn `orders` inject một `TenantResolver` được cung cấp bởi mô-đun đó.

`sharedModules` cũng không công khai package nội bộ, thay đổi module detection hoặc quyền sở hữu package, hay bỏ qua cơ chế đóng gói của module `CLOSED`. Consumer vẫn phải tham chiếu API ở package gốc hoặc Named Interface đã được công khai. Nếu `TenantResolver` nằm trong `shared.api` và package đó được đánh dấu `@NamedInterface("api")`, consumer có thể sử dụng hợp đồng `shared::api`. Nếu consumer truy cập `shared.internal.TenantResolver`, package boundary vẫn bị vi phạm dù `shared` đã được khai báo là shared module.

Tóm lại, `sharedModules` cấp quyền dependency trong bước xác minh allow-list và bổ sung module vào test context. Nó không tạo cạnh dependency thay cho mã nguồn và không biến implementation nội bộ thành API công khai. Hai việc cần review riêng là quan hệ tham chiếu thực tế và phạm vi API mà mô-đun cung cấp.

## 7. Tránh dùng sharedModules để che lỗi bootstrap

Khi `@ApplicationModuleTest` báo thiếu bean, đừng lập tức đưa module chứa bean đó vào `sharedModules`. Hãy xác định nguyên nhân:

1. Bean có thuộc cấu hình hạ tầng thật sự dùng chung cho mọi module test không?
2. Bean thuộc một module nghiệp vụ mà chỉ module đang kiểm thử cần dùng không?
3. Test có cần kiểm tra tương tác thật với module đó hay chỉ cần một collaborator giả lập?
4. Bootstrap mode hiện tại đã phù hợp với mục tiêu test chưa?

Nếu chỉ một test cần module phụ trợ, dùng `extraIncludes`. Nếu test chỉ cần kiểm tra cách module hiện tại gọi một collaborator, dùng `@MockitoBean` để thay bean bên ngoài. Nếu cần tích hợp với dependency trực tiếp hoặc bắc cầu, chọn `DIRECT_DEPENDENCIES` hoặc `ALL_DEPENDENCIES`.

Khi nhiều module test đều cần một bean cấu hình kỹ thuật, shared module là lựa chọn phù hợp. Nếu nhiều module nghiệp vụ cần gọi service của cùng một module, hãy giữ quan hệ dependency rõ ràng thay vì biến module đó thành shared để mọi test đều nạp nó.

## 8. Kiểm tra shared module được nạp trong test

Để xác nhận cấu hình, có thể bật log DEBUG cho Spring Modulith trong `src/test/resources/application.properties`:

```properties
logging.level.org.springframework.modulith=DEBUG
```

Khi chạy một `@ApplicationModuleTest`, đọc log bootstrap để xác nhận module đang kiểm thử, các dependency theo mode và shared module đã được đưa vào context. Ví dụ, khi test `orders` chạy ở `STANDALONE`, danh sách bootstrap mong đợi gồm `orders` và `shared`.

Ngoài log, có thể viết một assertion đơn giản cho bean dùng chung:

```java
package com.acme.shop.orders;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Clock;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest
class OrderModuleTests {

    @Autowired
    Clock clock;

    @Test
    void sharedConfigurationIsLoaded() {
        assertThat(clock).isNotNull();
    }
}
```

Assertion này xác nhận bean có mặt trong context của test. Nó không chứng minh mọi quy tắc kiến trúc đều hợp lệ; hãy duy trì architecture test gọi `ApplicationModules.verify()` riêng hoặc dựa vào cơ chế verification tự động của module test theo cấu hình dự án.

## 9. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Shared bean không xuất hiện trong module test | Tên module chưa được khai báo hoặc `@Modulithic` không nằm trên application class đang được dùng | Kiểm tra application class và module name trong module model |
| Khai báo package path thay cho module name | `sharedModules` yêu cầu tên module được nhận diện | Dùng logical name chính xác của module |
| Module test vẫn thiếu bean từ module nghiệp vụ | Module đó không phải shared module và không nằm trong bootstrap mode | Dùng mode phù hợp, `extraIncludes` hoặc mock bean |
| Thêm một module vào shared khiến nhiều test chậm hơn | Module chứa nhiều bean/configuration hoặc dependency nặng | Thu hẹp shared module hoặc chỉ dùng `extraIncludes` ở test cần thiết |
| Test chạy qua nhưng `verify()` báo vi phạm | Bootstrap scope và architecture rules là hai vấn đề khác nhau | Sửa API, package boundary hoặc `allowedDependencies` |
| Shared module không được phát hiện | Package không nằm trong application module arrangement hoặc detection strategy loại nó | Kiểm tra package root và module detection |

## 10. Quy trình cấu hình sharedModules

1. Xác định module chứa cấu hình hoặc thành phần kỹ thuật thực sự dùng chung.
2. Xác nhận module đó được Spring Modulith nhận diện và có logical name ổn định.
3. Khai báo `@Modulithic(sharedModules = { ... })` trên lớp Spring Boot application.
4. Giữ `@ApplicationModuleTest` tại package của module cần kiểm thử và chọn bootstrap mode phù hợp.
5. Chạy module test ở chế độ `STANDALONE` để xác nhận shared module vẫn được bootstrap.
6. Dùng `extraIncludes` cho module chỉ cần trong một test class.
7. Đọc log DEBUG và kiểm tra bean dùng chung có mặt trong context.
8. Kiểm tra dependency rules riêng; không xem shared bootstrap là quyền truy cập API.
9. Theo dõi thời gian khởi tạo context và loại bỏ module khỏi shared nếu không còn cần thiết toàn cục.

## 11. Bài tập thực hành

Với ứng dụng `com.acme.shop` có các module `shared`, `orders`, `inventory`, `customers` và `audit`, hãy thực hiện:

1. Tạo module `shared` chứa `TimeConfiguration` và bean `Clock`.
2. Đánh dấu `shared` là shared module bằng `@Modulithic(sharedModules = "shared")` trên `ShopApplication`.
3. Tạo `OrderModuleTests` trong package `com.acme.shop.orders` với `@ApplicationModuleTest(mode = STANDALONE)`.
4. Inject `Clock` trong test và xác nhận bean có mặt dù chế độ `STANDALONE` không đưa `shared` vào phạm vi mặc định.
5. Tạo một test khác dùng `extraIncludes = "audit"` để thêm `audit` chỉ trong test đó.
6. Chạy một test ở `DIRECT_DEPENDENCIES` và một test ở `ALL_DEPENDENCIES`; ghi lại các module được bootstrap trong từng trường hợp.
7. Kiểm tra rằng `sharedModules` luôn được thêm vào cả ba chế độ.
8. Chạy architecture verification và xác nhận cấu hình shared không làm thay đổi quy tắc API hoặc dependency.

Kết quả cần ghi lại:

| Test | Bootstrap mode | Module được mong đợi |
|---|---|---|
| `OrderModuleTests` | `STANDALONE` | `orders`, `shared` |
| `OrderWithDependenciesTests` | `DIRECT_DEPENDENCIES` | `orders`, các dependency trực tiếp, `shared` |
| `OrderWorkflowTests` | `ALL_DEPENDENCIES` | `orders`, toàn bộ dependency bắc cầu, `shared` |
| `OrderAuditIntegrationTests` | `STANDALONE` + `extraIncludes = "audit"` | `orders`, `audit`, `shared` |

Thứ tự hiển thị module trong log không phải hợp đồng cần dựa vào; hãy xác nhận tập module được bootstrap. Nếu kết quả khác dự kiến, kiểm tra logical name, module detection và application class chứa `@Modulithic`.

## 12. Câu hỏi tự kiểm tra

| Câu hỏi | Câu trả lời cần đạt |
|---|---|
| `sharedModules` được khai báo ở đâu? | Trên `@Modulithic` hoặc `@Modulith` của lớp ứng dụng chính. |
| Thuộc tính này nhận giá trị gì? | Tên logic của các application module cần luôn được bootstrap trong module integration tests. |
| `sharedModules` có áp dụng với mọi bootstrap mode không? | Có, các shared module được thêm bất kể `STANDALONE`, `DIRECT_DEPENDENCIES` hay `ALL_DEPENDENCIES`. |
| `extraIncludes` khác `sharedModules` thế nào? | `extraIncludes` chỉ thêm module cho một test class; `sharedModules` áp dụng cho mọi module integration test và cũng được xem là dependency được phép trong allow-list verification. |
| `sharedModules` có tự tạo source-code dependency hoặc công khai package internal không? | Không. Nó cho phép dependency trong allow-list và thêm module vào test bootstrap; cạnh vẫn cần tham chiếu thực tế, còn consumer phải dùng API công khai hoặc Named Interface. |
| Khi nào không nên dùng shared module? | Khi module chỉ là dependency nghiệp vụ của một số consumer hoặc khi việc thêm nó làm test context rộng không cần thiết. |

Sau bài học, bạn cần có khả năng xác định đúng module dùng chung, cấu hình `sharedModules` trên application class, phân biệt nó với `extraIncludes` và lựa chọn bootstrap mode phù hợp. Mục tiêu là giữ module test ổn định mà vẫn bảo toàn ranh giới kiến trúc giữa các mô-đun.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals: Customizing the Application Modules Arrangement](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html)
- [Spring Modulith API — `Modulithic`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/Modulithic.html)
- [Spring Modulith API — `ApplicationModuleTest`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/test/ApplicationModuleTest.html)

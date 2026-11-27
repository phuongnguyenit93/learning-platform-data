# Migration một package legacy thành open module

Trong bài thực hành này, bạn sẽ đưa một vùng package cũ vào module model của Spring Modulith mà chưa phải sửa tất cả consumer cùng lúc. Bạn sẽ nhận diện package legacy, đánh dấu nó thành open module, giữ cho các luồng nghiệp vụ hiện tại tiếp tục sử dụng được các lớp cũ, sau đó từng bước tạo API công khai và chuyển consumer sang hợp đồng mới. Cuối cùng, bạn sẽ đóng mô-đun và kiểm tra lại boundary.

Open module hữu ích trong giai đoạn đầu của quá trình modular hóa một ứng dụng Spring Boot lâu năm. Khi mô-đun được đánh dấu `OPEN`, các mô-đun khác có thể truy cập kiểu nội bộ của nó. Cơ chế này giúp nhóm chuyển đổi theo từng bước. Tuy nhiên, open module làm giảm một phần bảo vệ kiến trúc: các kiểu trong package con được đưa vào unnamed interface và open module bị loại khỏi thuật toán phát hiện dependency cycle của Spring Modulith. Vì vậy, mục tiêu của bài tập là dùng `OPEN` như trạng thái chuyển tiếp, rồi đưa mô-đun về `CLOSED` sau khi consumer đã chuyển sang API được công khai.

Các ví dụ architecture test và module integration test cần Spring Modulith test support. Nếu dự án quản lý version bằng BOM, khai báo dependency test mà không ghi version riêng:

```xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

## 1. Chuẩn bị codebase legacy

Giả sử ứng dụng bán hàng có package gốc `com.acme.shop` và cấu trúc sau:

```text
com.acme.shop
├── ShopApplication.java
├── orders
│   ├── OrderService.java
│   └── package-info.java
├── customers
│   └── CustomerService.java
└── legacy
    ├── billing
    │   └── internal
    │       └── LegacyTaxCalculator.java
    ├── customer
    │   └── internal
    │       └── LegacyCustomerRepository.java
    └── persistence
        └── LegacyEntityManager.java
```

Trong ví dụ, `legacy` là package con trực tiếp của `com.acme.shop`, nên được nhận diện là một application module theo detection mặc định. Các mô-đun `orders` và `customers` đang import những kiểu nằm trong package con của `legacy`.

Lớp ứng dụng chính cần nằm tại package gốc:

```java
package com.acme.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Trước khi thay đổi, ghi lại các consumer đang truy cập `legacy`. Ví dụ, `OrderService` đang dùng trực tiếp implementation tính thuế:

```java
package com.acme.shop.orders;

import java.math.BigDecimal;

import com.acme.shop.legacy.billing.internal.LegacyTaxCalculator;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final LegacyTaxCalculator taxCalculator;

    public OrderService(LegacyTaxCalculator taxCalculator) {
        this.taxCalculator = taxCalculator;
    }

    public BigDecimal taxFor(BigDecimal netAmount) {
        return taxCalculator.calculate(netAmount);
    }
}
```

Đây là dependency tới package triển khai nội bộ. Trong một module `CLOSED`, Spring Modulith sẽ kiểm tra và báo truy cập package nội bộ từ mô-đun khác.

## 2. Ghi nhận trạng thái ban đầu

Tạo architecture test dùng application class của production:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleArrangement() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Trước khi mở `legacy`, chạy test và lưu lại các violation liên quan tới package `legacy`. Nếu ứng dụng chưa có module test này, thêm nó vào test source set. Trong một codebase đã có architecture test, hãy dùng test hiện tại thay vì tạo một cổng kiểm tra trùng lặp.

Ghi lại dependency theo mẫu:

| Consumer | Package legacy đang dùng | Mục đích hiện tại | Hợp đồng dự kiến |
|---|---|---|---|
| `orders` | `legacy.billing.internal` | Tính thuế đơn hàng | `legacy::api` |
| `customers` | `legacy.customer.internal` | Tra cứu dữ liệu khách hàng cũ | `legacy::customer-api` hoặc API phù hợp |
| `orders` | `legacy.persistence` | Truy cập helper persistence | Cần đánh giá; không mặc định công khai |

Danh sách này là đầu vào để theo dõi migration. Không đưa mọi package legacy vào API mới chỉ vì chúng đang được sử dụng.

## 3. Đánh dấu legacy thành OPEN

Tạo file `src/main/java/com/acme/shop/legacy/package-info.java`:

```java
@org.springframework.modulith.ApplicationModule(
    type = org.springframework.modulith.ApplicationModule.Type.OPEN
)
package com.acme.shop.legacy;
```

Annotation được đặt ở package gốc của mô-đun legacy. Không đặt tại `com.acme.shop` vì như vậy sẽ mở phạm vi của toàn bộ ứng dụng thay vì chỉ mở mô-đun cần chuyển đổi.

Với khai báo này, Spring Modulith cho phép các mô-đun khác truy cập kiểu trong package con của `legacy`. Các kiểu trong package gốc và package con được đưa vào unnamed interface, trừ kiểu/package đã được gán rõ ràng vào Named Interface. Điều này cho phép `orders` tiếp tục tham chiếu `LegacyTaxCalculator` trong giai đoạn chuyển tiếp.

Open module vẫn là một application module trong model. `OPEN` không thay đổi modifier Java, không di chuyển lớp, không tự đăng ký bean và không thay thế component scanning của Spring.

## 4. Giữ allow-list của consumer chính xác

Nếu mô-đun consumer không khai báo `allowedDependencies`, dependency được xử lý theo các quy tắc mặc định của module model. Nếu consumer đã khai báo allow-list, việc mở mô-đun đích không tự thêm tên mô-đun vào danh sách đó.

Ví dụ, nếu `orders` có allow-list, hãy bổ sung `legacy` trong giai đoạn còn truy cập unnamed interface của open module:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {
        "inventory",
        "legacy"
    }
)
package com.acme.shop.orders;
```

Nếu `orders` đã có các dependency khác, hãy giữ chúng và chỉ thêm entry cần thiết. Không thay toàn bộ allow-list bằng một danh sách mới thiếu các dependency hợp lệ đang tồn tại.

Sau khi khai báo `OPEN` và cập nhật allow-list cần thiết, chạy lại architecture test. Các vi phạm truy cập package nội bộ của `legacy` có thể không còn xuất hiện vì mô-đun đã mở. Những vi phạm khác, chẳng hạn dependency chưa được cho phép tới mô-đun khác, vẫn cần được xử lý riêng.

## 5. Xác nhận module model và các consumer cũ

In module model để chắc chắn `legacy` được nhận diện đúng:

```java
ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

modules.forEach(System.out::println);
```

Tìm các thông tin sau trong output:

- Logical name của mô-đun là `legacy`.
- Base package là `com.acme.shop.legacy`.
- Các bean thuộc vùng legacy được gắn vào đúng mô-đun.
- Các Named Interface đã khai báo vẫn được hiển thị riêng nếu có.

Tiếp theo, kiểm tra những consumer cũ. Trong giai đoạn này, `OrderService` có thể tiếp tục inject `LegacyTaxCalculator` để hệ thống không phải chuyển đổi mọi luồng cùng lúc. Tuy nhiên, phải ghi nhận đây là dependency tạm thời và xác định người phụ trách cùng thời điểm loại bỏ.

## 6. Tạo API công khai cho nghiệp vụ tính thuế

Chọn một hợp đồng nhỏ mà consumer thực sự cần. Trong bài tập này, `orders` chỉ cần khả năng tính thuế, không cần biết lớp triển khai cũ hoặc cách tính thuế được lưu trữ.

Tạo package `com.acme.shop.legacy.api` và đánh dấu Named Interface trong file `src/main/java/com/acme/shop/legacy/api/package-info.java`:

```java
@org.springframework.modulith.NamedInterface("api")
package com.acme.shop.legacy.api;
```

Định nghĩa interface công khai:

```java
package com.acme.shop.legacy.api;

import java.math.BigDecimal;

public interface TaxCalculator {

    BigDecimal calculate(BigDecimal netAmount);
}
```

Điều chỉnh implementation cũ để triển khai interface mới:

```java
package com.acme.shop.legacy.billing.internal;

import java.math.BigDecimal;

import com.acme.shop.legacy.api.TaxCalculator;
import org.springframework.stereotype.Component;

@Component
public class LegacyTaxCalculator implements TaxCalculator {

    @Override
    public BigDecimal calculate(BigDecimal netAmount) {
        return netAmount.multiply(new BigDecimal("0.10"));
    }
}
```

Implementation vẫn nằm trong package nội bộ. Consumer chỉ cần biết `TaxCalculator` trong Named Interface `legacy::api`.

## 7. Chuyển consumer sang Named Interface

Thay đổi `OrderService` để inject interface công khai:

```java
package com.acme.shop.orders;

import java.math.BigDecimal;

import com.acme.shop.legacy.api.TaxCalculator;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final TaxCalculator taxCalculator;

    public OrderService(TaxCalculator taxCalculator) {
        this.taxCalculator = taxCalculator;
    }

    public BigDecimal taxFor(BigDecimal netAmount) {
        return taxCalculator.calculate(netAmount);
    }
}
```

Sau khi không còn import `LegacyTaxCalculator`, thu hẹp allow-list của `orders` về Named Interface:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {
        "inventory",
        "legacy::api"
    }
)
package com.acme.shop.orders;
```

`legacy::api` biểu diễn Named Interface `api` do mô-đun `legacy` công khai. Consumer không cần quyền truy cập toàn bộ unnamed interface hoặc các package nội bộ khác.

Nếu `customers` cũng đang truy cập `legacy.customer.internal`, hãy lặp lại quy trình: xác định dữ liệu hoặc hành vi thực sự cần dùng, tạo DTO/interface phù hợp trong Named Interface, chuyển consumer và thu hẹp allow-list. Không gom các hợp đồng không liên quan vào một interface lớn chỉ để giảm số lượng package.

## 8. Theo dõi phần internal còn được sử dụng

Sau mỗi lần chuyển consumer, cập nhật bảng migration:

| Consumer | Dependency cũ | Hợp đồng mới | Trạng thái |
|---|---|---|---|
| `orders` | `legacy.billing.internal.LegacyTaxCalculator` | `legacy::api.TaxCalculator` | Đã chuyển |
| `customers` | `legacy.customer.internal.LegacyCustomerRepository` | `legacy::customer-api.CustomerLookup` | Chờ chuyển |
| `orders` | `legacy.persistence.LegacyEntityManager` | Chưa xác định | Cần review quyền sở hữu |

Có thể dùng tìm kiếm mã nguồn hoặc rule ArchUnit trong dự án để phát hiện các import còn trỏ tới package `legacy.internal` hoặc các package triển khai tương tự. Hãy kiểm tra cả constructor parameter, field, method parameter, return type và generic type; dependency không chỉ xuất hiện ở dòng import.

Đặt tiêu chí hoàn thành rõ ràng:

- Không còn consumer bên ngoài `legacy` tham chiếu package triển khai nội bộ.
- Các hợp đồng cần chia sẻ được đặt trong package gốc công khai hoặc Named Interface có mục đích rõ ràng.
- Allow-list của từng consumer chỉ cho phép mô-đun hoặc Named Interface thực sự cần thiết.
- Các test nghiệp vụ vẫn hoạt động với implementation được inject qua API mới.
- Dependency cycle liên quan tới `legacy` đã được xem xét riêng trong giai đoạn open.

## 9. Đóng mô-đun sau khi migration

Khi các consumer đã chuyển sang API công khai, hãy đưa `legacy` về trạng thái `CLOSED`. Nếu file `package-info.java` chỉ được tạo để mở mô-đun, có thể bỏ annotation `OPEN`. Nếu muốn khai báo rõ trạng thái, dùng:

```java
@org.springframework.modulith.ApplicationModule(
    type = org.springframework.modulith.ApplicationModule.Type.CLOSED
)
package com.acme.shop.legacy;
```

Khi mô-đun đóng, các package con trở lại trạng thái nội bộ trừ những package được công khai bằng Named Interface. `legacy.api` vẫn là API được công khai vì có `@NamedInterface("api")`.

Chạy lại:

```java
ApplicationModules.of(ShopApplication.class).verify();
```

Nếu còn consumer truy cập `legacy.billing.internal`, `legacy.customer.internal` hoặc `legacy.persistence`, verification có thể báo vi phạm package boundary. Dùng thông tin source/target trong violation để tìm consumer còn sót và chuyển nó sang API phù hợp.

Sau khi đóng mô-đun, kiểm tra lại dependency cycle. Trong thời gian `legacy` là open module, nó bị loại khỏi thuật toán phát hiện dependency cycle của Spring Modulith; vì vậy một lần `verify()` pass khi module còn mở không chứng minh toàn bộ graph không có chu trình. Khi đã đóng, chạy verification lại để khôi phục kiểm tra cycle cho mô-đun này.

## 10. Kiểm thử hành vi sau khi chuyển API

Tạo module integration test cho `orders` để xác nhận Spring có thể inject implementation qua interface công khai:

```java
package com.acme.shop.orders;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest(mode = ApplicationModuleTest.BootstrapMode.DIRECT_DEPENDENCIES)
class OrderTaxIntegrationTests {

    @Autowired
    OrderService orders;

    @Test
    void calculatesTaxThroughPublicContract() {
        assertThat(orders.taxFor(new BigDecimal("100.00")))
                .isEqualByComparingTo("10.0000");
    }
}
```

Test này dùng `DIRECT_DEPENDENCIES` để bootstrap `orders` cùng mô-đun `legacy` mà nó phụ thuộc, sau đó kiểm tra luồng tới implementation của `TaxCalculator` đã được đăng ký trong Spring context. Nếu một test khác chỉ bootstrap `orders`, hãy dùng test double hoặc thêm dependency cần thiết theo đúng mục tiêu test. Không dùng `sharedModules` để biến một dependency nghiệp vụ thành cấu hình dùng chung.

Giữ architecture test riêng để xác minh module graph và boundary. Integration test kiểm tra wiring/hành vi runtime; `ApplicationModules.verify()` kiểm tra các quy tắc cấu trúc. Hai loại kiểm tra bổ sung cho nhau.

## 11. Các lỗi thường gặp trong quá trình migration

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `legacy` không xuất hiện trong module model | Package không nằm dưới application root hoặc detection strategy không nhận diện | Kiểm tra package root và module detection trước khi thêm `OPEN` |
| Consumer vẫn bị báo dependency không được phép | Mô-đun nguồn khai báo `allowedDependencies` nhưng chưa cho phép `legacy` | Bổ sung đúng module/interface vào allow-list hiện tại |
| `verify()` pass nhưng vẫn còn import internal | `OPEN` cho phép truy cập package con | Dùng tìm kiếm mã nguồn hoặc ArchUnit rule để theo dõi internal access |
| Consumer không tìm thấy bean sau khi đổi sang interface | Implementation không được đăng ký hoặc component scan không bao phủ package | Kiểm tra stereotype, package và Spring context |
| Test module không bootstrap được implementation legacy | Dependency module không nằm trong bootstrap mode | Dùng `DIRECT_DEPENDENCIES`, `ALL_DEPENDENCIES`, `extraIncludes` hoặc mock theo mục tiêu test |
| Sau khi đóng module, verification thất bại | Consumer còn tham chiếu package nội bộ | Chuyển consumer sang API/Named Interface rồi chạy lại |
| Cycle không được báo khi module còn OPEN | Open module bị loại khỏi cycle detection | Review dependency graph riêng và xác minh lại sau khi đóng module |

## 12. Bài tập thực hành

Hãy thực hiện migration trên một nhánh làm việc riêng với các yêu cầu:

1. Tạo hoặc chọn package `com.acme.shop.legacy` là package con trực tiếp của application root.
2. Ghi lại ít nhất hai consumer đang import kiểu từ package con của `legacy`.
3. Tạo architecture test gọi `ApplicationModules.of(ShopApplication.class).verify()` và ghi nhận các vi phạm ban đầu.
4. Thêm `package-info.java` với `@ApplicationModule(type = ApplicationModule.Type.OPEN)` cho `legacy`.
5. Cập nhật allow-list của consumer nếu chúng đang khai báo `allowedDependencies`.
6. Chạy lại verification và xác nhận truy cập nội bộ legacy được cho phép trong giai đoạn chuyển tiếp.
7. Tạo Named Interface `legacy::api` với một hợp đồng nghiệp vụ nhỏ, ví dụ `TaxCalculator`.
8. Chuyển ít nhất một consumer từ implementation nội bộ sang interface công khai.
9. Thu hẹp allow-list của consumer đó về `legacy::api` nếu dùng allow-list.
10. Tìm các import nội bộ còn lại và ghi nhận owner cùng kế hoạch chuyển đổi.
11. Khi không còn consumer ngoài mô-đun truy cập package internal, đóng `legacy`.
12. Chạy lại `ApplicationModules.verify()` và kiểm tra các dependency cycle sau khi mô-đun đã đóng.
13. Chạy module integration test để xác nhận bean implementation vẫn được inject qua API mới.

Kết quả cần ghi lại:

| Mốc | Bằng chứng hoàn thành |
|---|---|
| Trước migration | Module map và danh sách consumer đang truy cập internal |
| Sau khi mở module | `legacy` xuất hiện trong model với kiểu `OPEN`; các consumer cũ tiếp tục được phân tích |
| Sau khi tạo API | Named Interface `legacy::api` chứa hợp đồng nghiệp vụ ổn định |
| Sau khi chuyển consumer | Consumer import interface công khai, không import implementation nội bộ |
| Trước khi đóng | Không còn internal access từ mô-đun khác; allow-list đã thu hẹp |
| Sau khi đóng | `ApplicationModules.verify()` pass và dependency cycle được kiểm tra lại |

## 13. Câu hỏi tự kiểm tra

| Câu hỏi | Câu trả lời cần đạt |
|---|---|
| Khi nào nên dùng open module? | Khi cần đưa một codebase legacy vào module model và chuyển consumer theo từng bước. |
| Khai báo `OPEN` ở đâu? | Trong `package-info.java` của package gốc mô-đun legacy. |
| `OPEN` cho phép điều gì? | Mô-đun khác có thể truy cập kiểu nội bộ của mô-đun mở; các kiểu được đưa vào unnamed interface trừ kiểu đã gán Named Interface. |
| Open module có tự thêm dependency vào allow-list không? | Không. Allow-list của mô-đun nguồn vẫn cần phản ánh dependency được phép. |
| Vì sao không nên giữ module OPEN vĩnh viễn? | Nó làm giảm bảo vệ package boundary và bị loại khỏi thuật toán phát hiện dependency cycle. |
| Khi nào có thể đóng module? | Khi consumer bên ngoài đã chuyển sang package gốc hoặc Named Interface và không còn internal access. |
| Sau khi đóng cần kiểm tra gì? | Package access, allow-list, dependency cycle và hành vi integration qua API mới. |

Hoàn thành bài tập khi bạn có thể giải thích vì sao open module là bước chuyển tiếp, tạo được một API có chủ sở hữu rõ ràng, chuyển consumer khỏi implementation nội bộ và đóng mô-đun mà không làm mất các luồng nghiệp vụ cần thiết.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals: Open Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html#modules.advanced.open)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith API — `ApplicationModule`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
- [Spring Modulith API — `NamedInterface`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/NamedInterface.html)

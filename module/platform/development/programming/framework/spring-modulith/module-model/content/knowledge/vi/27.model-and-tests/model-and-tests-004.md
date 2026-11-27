# Kiểm tra phụ thuộc module trong test

Một modular monolith cần kiểm tra dependency giữa các Application Module như một phần của test suite. Nếu chỉ kiểm thử kết quả nghiệp vụ của từng service, code vẫn có thể dần hình thành chu trình module, import type nội bộ của module khác hoặc thêm dependency ngoài danh sách đã cho phép.

Spring Modulith cung cấp mô hình **ApplicationModules** và phương thức **verify()** để kiểm tra các ranh giới đó. Có thể gọi verification trực tiếp trong JUnit mà không cần khởi động Spring ApplicationContext. Khi cần kiểm tra bean wiring và hành vi tích hợp của riêng một module, dùng thêm **@ApplicationModuleTest** để bootstrap module trong phạm vi giới hạn.

Bài học này tập trung vào cách viết test cho dependency graph: kiểm tra toàn bộ mô hình, kiểm tra một dependency cụ thể, đọc vi phạm, phân biệt structural test với integration test và đưa các kiểm tra vào CI.

## 1. Vì sao cần test dependency giữa các module?

Giả sử ứng dụng có các module:

~~~text
com.acme.shop
├── orders
├── inventory
├── payments
└── shipping
~~~

Mỗi module sở hữu một phần nghiệp vụ và chỉ công bố API package mặc định hoặc Named Interface được thiết kế để module khác sử dụng.

Trong quá trình phát triển, một thay đổi tưởng như nhỏ có thể làm sai kiến trúc:

- Developer import repository hoặc entity trong package internal của module khác.
- Một module bắt đầu phụ thuộc vào module thứ ba mà allowlist chưa cho phép.
- Hai module gọi API của nhau, tạo chu trình dependency.
- Một Named Interface bị đổi tên hoặc bỏ metadata nhưng consumer vẫn tiếp tục tham chiếu.
- Một refactor package vô tình làm thay đổi module detection.

Unit test có thể vẫn PASS vì phương thức được gọi trả về kết quả mong đợi. Structural test kiểm tra các quan hệ type và module để phát hiện những thay đổi đó.

## 2. ApplicationModules.verify() kiểm tra những gì?

Spring Modulith kiểm tra ba nhóm quy tắc cốt lõi:

| Quy tắc | Ý nghĩa |
|---|---|
| Dependency graph không có chu trình | Các Application Module tạo thành directed acyclic graph (DAG) |
| Truy cập qua API được công bố | Module không tham chiếu type trong package nội bộ của module khác; Open Module có quy tắc riêng |
| allowedDependencies | Nếu consumer khai báo allowlist, dependency thực tế phải nằm trong danh sách module hoặc Named Interface được phép |

Nếu tích hợp jMolecules ArchUnit có trên classpath, các quy tắc DDD và kiến trúc bổ sung tương ứng cũng có thể được thực hiện.

Verification phân tích cấu trúc type và dependency trong application model. Nó không khởi động Spring, không thực thi HTTP request, không kiểm tra transaction và không chứng minh một use case trả về dữ liệu đúng. Các hành vi đó cần unit test hoặc integration test phù hợp.

## 3. Viết architecture test bằng JUnit

Tạo một test class ở test source set, ví dụ:

~~~text
src/test/java/com/acme/shop/ApplicationModuleStructureTests.java
~~~

Nội dung:

~~~java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ApplicationModuleStructureTests {

    @Test
    void verifiesApplicationModuleDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Khi JUnit chạy test, Spring Modulith phát hiện các module từ class ứng dụng rồi kiểm tra dependency graph. Nếu có chu trình, truy cập package nội bộ hoặc dependency ngoài allowlist, **verify()** ném exception và test thất bại.

Đây là một test kiến trúc tập trung cho toàn application model. Không cần gắn **@SpringBootTest** hoặc **@ApplicationModuleTest** vì mục tiêu ở đây là kiểm tra cấu trúc module, không phải tạo Spring ApplicationContext.

## 4. Ví dụ cấu trúc dependency được kiểm tra

Giả sử module **orders** cần dùng hai API công khai:

~~~java
package com.acme.shop.inventory;

public interface InventoryReservation {

    boolean reserve(String orderId);
}
~~~

~~~java
package com.acme.shop.payments;

public interface PaymentAuthorization {

    boolean authorize(String orderId);
}
~~~

Module orders khai báo dependency được phép tại package gốc:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = { "inventory", "payments" }
)
package com.acme.shop.orders;
~~~

Một service trong orders có thể sử dụng các hợp đồng đó:

~~~java
package com.acme.shop.orders.internal;

import com.acme.shop.inventory.InventoryReservation;
import com.acme.shop.payments.PaymentAuthorization;

class OrderPlacementService {

    private final InventoryReservation inventory;
    private final PaymentAuthorization payment;

    OrderPlacementService(
            InventoryReservation inventory,
            PaymentAuthorization payment) {
        this.inventory = inventory;
        this.payment = payment;
    }
}
~~~

Khi chạy **ApplicationModules.of(ShopApplication.class).verify()**, Spring Modulith kiểm tra dependency thực tế từ orders tới inventory và payments có tuân thủ các API boundary và allowlist hay không.

Nếu service bắt đầu import một type trong **com.acme.shop.inventory.internal**, test sẽ phát hiện truy cập type chưa được expose. Nếu orders phụ thuộc thêm shipping mà không có trong allowlist, test cũng thất bại.

## 5. Kiểm tra một dependency cụ thể bằng ApplicationModule

Ngoài việc gọi verify(), có thể đọc mô hình để kiểm tra một module có dependency trực tiếp như dự kiến hay không.

Ví dụ, test xác nhận orders phụ thuộc trực tiếp cả inventory và payments:

~~~java
package com.acme.shop;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

class ApplicationModuleDependencyTests {

    @Test
    void ordersDependsDirectlyOnInventoryAndPayments() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        ApplicationModule orders = modules.getModuleByName("orders")
            .orElseThrow();

        var dependencies = orders.getDirectDependencies(modules);

        assertThat(dependencies.containsModuleNamed("inventory")).isTrue();
        assertThat(dependencies.containsModuleNamed("payments")).isTrue();
    }
}
~~~

Các API được dùng:

- **getModuleByName("orders")** lấy module theo logical identifier và trả về Optional.
- **getDirectDependencies(modules)** lấy dependency trực tiếp của module đó.
- **containsModuleNamed("inventory")** kiểm tra dependency collection có module mang tên đó hay không.

Test này mô tả một kỳ vọng cụ thể của kiến trúc. Nếu sau này dependency trực tiếp tới payments bị loại bỏ khỏi orders, assertion sẽ thất bại và yêu cầu đội ngũ xem xét lại quyết định.

Lưu ý rằng dependency trực tiếp khác dependency bắc cầu. Nếu orders phụ thuộc inventory và inventory phụ thuộc catalog, catalog là dependency bắc cầu của orders. Khi muốn kiểm tra toàn bộ dependency tree, dùng **getAllDependencies(modules)** thay cho **getDirectDependencies(modules)**.

## 6. Kiểm tra danh sách vi phạm khi test thất bại

Thông thường, architecture test chỉ cần **verify()**. Khi cần chẩn đoán nhiều lỗi cùng lúc, dùng **detectViolations()** để nhận đối tượng Violations:

~~~java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleDependencyDiagnostics {

    @Test
    void printsAllDetectedViolations() {
        var violations = ApplicationModules.of(ShopApplication.class)
            .detectViolations();

        violations.getMessages().forEach(System.out::println);
    }
}
~~~

Các thông báo thường giúp xác định:

- Module consumer đang tạo dependency.
- Module provider được tham chiếu.
- Type hoặc package gây vi phạm.
- Dependency có nằm ngoài allowlist hay không.
- Chu trình module nào đang tồn tại.

**detectViolations()** thu thập kết quả để xử lý tiếp. Trong test bảo vệ kiến trúc, hãy để test thất bại khi còn vi phạm, ví dụ gọi **verify()** hoặc **throwIfPresent()** trên kết quả sau khi đã phân tích.

Không nên chỉ in lỗi rồi để test PASS. Khi vi phạm là ngoài dự kiến, build phải thất bại để lỗi không bị bỏ qua.

## 7. Phân biệt structural test và @ApplicationModuleTest

Hai loại test thường được dùng cùng nhau nhưng trả lời hai câu hỏi khác nhau:

| Loại test | Câu hỏi được trả lời | Có khởi động Spring context? |
|---|---|---|
| **ApplicationModules.verify()** trong JUnit | Dependency graph và module boundary có hợp lệ không? | Không |
| **@ApplicationModuleTest** | Các bean và use case trong một module có tích hợp đúng khi bootstrap module không? | Có, nhưng chỉ trong phạm vi module được chọn |

Structural test phát hiện dependency sai ở mức kiến trúc. Module integration test phát hiện vấn đề như bean thiếu, constructor injection không thỏa mãn, cấu hình hoặc persistence không hoạt động trong module.

**@ApplicationModuleTest** mặc định cũng tự động kiểm tra module structure khi bootstrap. Thuộc tính **verifyAutomatically** mặc định là true. Dù vậy, một architecture test tập trung vẫn hữu ích vì nó bảo vệ toàn bộ application model độc lập với việc có chạy integration test của từng module hay không.

## 8. Thiết lập module integration test

Để dùng **@ApplicationModuleTest**, thêm Spring Modulith test starter trong test scope:

~~~xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Đặt test class trong package của module hoặc một subpackage của module:

~~~java
package com.acme.shop.orders;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest
class OrderModuleIntegrationTests {

    @Test
    void startsOrdersModuleInIsolation() {
        // Kiểm tra bean và hành vi tích hợp của module orders.
    }
}
~~~

Spring Modulith giới hạn component scanning, auto-configuration và entity scanning theo module đang được kiểm tra. Mặc định, test bootstrap module hiện tại ở chế độ **STANDALONE**.

## 9. Chọn bootstrap mode theo dependency cần thiết

**@ApplicationModuleTest** hỗ trợ ba chế độ:

| Mode | Phạm vi bootstrap |
|---|---|
| **STANDALONE** | Chỉ module hiện tại |
| **DIRECT_DEPENDENCIES** | Module hiện tại và các module mà nó phụ thuộc trực tiếp |
| **ALL_DEPENDENCIES** | Module hiện tại cùng toàn bộ cây dependency bắc cầu |

Ví dụ, nếu test orders cần khởi tạo các module mà orders phụ thuộc trực tiếp:

~~~java
package com.acme.shop.orders;

import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest(
    mode = ApplicationModuleTest.BootstrapMode.DIRECT_DEPENDENCIES
)
class OrderModuleIntegrationTests {
}
~~~

Hãy bắt đầu bằng STANDALONE để kiểm tra module có thể chạy độc lập với các collaborator bên ngoài được thay thế phù hợp. Chỉ mở rộng sang DIRECT_DEPENDENCIES hoặc ALL_DEPENDENCIES khi kịch bản thực sự cần các module đó.

Nếu một module phụ thuộc quá nhiều bean của module khác, việc mở rộng bootstrap có thể che đi coupling. Hãy xem xét mock collaborator qua API được công bố hoặc chuyển giao tiếp phù hợp sang application event.

## 10. Mock dependency bên ngoài module

Trong standalone module test, một bean của orders có thể inject API của inventory. Nếu inventory không được bootstrap, Spring context không thể tìm thấy implementation thật. Có thể thay bean đó bằng mock:

~~~java
package com.acme.shop.orders;

import com.acme.shop.inventory.InventoryReservation;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@ApplicationModuleTest
class OrderModuleIntegrationTests {

    @MockitoBean
    InventoryReservation inventoryReservation;

    @Test
    void usesInventoryContractWhenPlacingOrder() {
        // Thiết lập hành vi mock và gọi use case của orders.
    }
}
~~~

Mock qua contract công khai giúp test chỉ phụ thuộc vào hành vi mà orders cần. Nó không thay thế architecture verification: dependency vào inventory vẫn phải được công bố và được phép trong module model.

Nếu phải mock nhiều bean từ một module khác, hãy xem xét lại số lượng collaborator và ranh giới API. Có thể orders đang biết quá nhiều về implementation của inventory.

## 11. Đưa module dependency test vào CI

Một pipeline nên chạy architecture test cùng các unit test khác ở mỗi thay đổi:

~~~text
Developer change
       |
       v
Compile production and test code
       |
       v
Run ApplicationModuleStructureTests
       |
       +---- FAIL: cycle / internal access / disallowed dependency
       |
       v
Run module integration tests
       |
       +---- FAIL: bean wiring / persistence / module behavior
       |
       v
Build can proceed
~~~

Architecture test thường nhanh hơn việc khởi động nhiều Spring context vì nó phân tích mô hình dependency. Đặt nó trong một test class ổn định để CI luôn chạy, kể cả khi một số module integration test được chọn lọc theo phạm vi thay đổi.

Không nên phụ thuộc vào việc developer nhớ chạy một lệnh thủ công. Khi dependency rule thay đổi, pipeline phải thực thi test để phát hiện vi phạm trước khi merge.

## 12. Những lỗi thường gặp khi kiểm tra dependency

**Chỉ test kết quả nghiệp vụ.** Unit test PASS không chứng minh module dependency hợp lệ. Thêm structural test dùng **ApplicationModules.verify()**.

**Nhầm module integration test với architecture test.** **@ApplicationModuleTest** kiểm tra bootstrap và hành vi của module; dùng một architecture test riêng để kiểm tra toàn application model.

**Chỉ kiểm tra dependency trực tiếp.** Nếu quy tắc cần áp dụng cho cả cây dependency, dùng API dependency bắc cầu hoặc gọi verify() cho toàn bộ mô hình.

**Dùng ALL_DEPENDENCIES cho mọi test.** Bootstrap quá rộng làm test khó cô lập và có thể che coupling. Chọn mode nhỏ nhất đáp ứng kịch bản.

**Mock bean nội bộ của module khác.** Consumer nên mock contract công khai mà nó phụ thuộc. Truy cập implementation nội bộ là dấu hiệu sai boundary.

**Bỏ qua violations để build PASS.** Chỉ lọc ngoại lệ có chủ đích, có lý do kiến trúc rõ và được review. Không bỏ qua một access violation hoặc cycle chỉ vì nó làm test đỏ.

**Dùng chung ApplicationModules instance cho nhiều lần verify với options khác nhau.** **verify()** chỉ thực thi verification nếu chưa chạy trên instance đó. Khi cần đánh giá lại với cấu hình khác, tạo instance mới hoặc dùng **detectViolations(options)** để thực thi lại.

## 13. Quy trình xây dựng bộ test dependency

1. Xác định class ứng dụng dùng làm điểm bắt đầu application model.
2. Tạo một JUnit test gọi **ApplicationModules.of(ShopApplication.class).verify()**.
3. Chạy test và sửa các cycle, internal access hoặc disallowed dependency được phát hiện.
4. Với dependency quan trọng, dùng **getModuleByName()** và **getDirectDependencies()** để viết assertion thể hiện quan hệ mong muốn.
5. Dùng **detectViolations()** khi cần đọc và phân loại nhiều lỗi.
6. Tạo **@ApplicationModuleTest** trong từng module để kiểm tra Spring bean wiring và hành vi tích hợp.
7. Chọn bootstrap mode nhỏ nhất; mock collaborator liên module qua API được công bố khi phù hợp.
8. Đưa architecture test và module integration test cần thiết vào CI.

Một bộ test tốt vừa bảo vệ dependency graph, vừa kiểm tra hành vi của module trong phạm vi rõ ràng. **ApplicationModules.verify()** giữ cho module graph tuân thủ ranh giới; **@ApplicationModuleTest** xác nhận module có thể được bootstrap và thực hiện công việc của nó. Kết hợp đúng hai lớp giúp modular monolith tiếp tục phát triển mà không làm dependency giữa các module trở nên khó kiểm soát.

## Tài liệu tham khảo

- [Spring Modulith Reference — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): các quy tắc dependency, **verify()**, **detectViolations()** và **VerificationOptions**.
- [Spring Modulith Javadoc — ApplicationModules](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html): tạo application model, **getModuleByName()**, **verify()** và **detectViolations()**.
- [Spring Modulith Javadoc — ApplicationModule](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModule.html): **getDirectDependencies()** và **getAllDependencies()**.
- [Spring Modulith Javadoc — ApplicationModuleDependencies](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDependencies.html): **containsModuleNamed()**, **uniqueModules()** và **withType()**.
- [Spring Modulith Reference — Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html): **@ApplicationModuleTest**, bootstrap modes và mock dependency liên module.
- [Spring Modulith Javadoc — ApplicationModuleTest](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/test/ApplicationModuleTest.html): cấu hình bootstrap và **verifyAutomatically**.

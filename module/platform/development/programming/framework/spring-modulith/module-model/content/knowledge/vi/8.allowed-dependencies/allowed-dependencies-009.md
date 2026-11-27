# Kiểm thử hợp đồng sau khi thêm module mới

Khi thêm một Application Module vào modular monolith, việc ứng dụng biên dịch thành công chưa chứng minh module mới tuân thủ kiến trúc hoặc giao tiếp đúng với các module hiện có. Một import có thể trỏ nhầm vào package nội bộ; một dependency mới có thể vượt khỏi danh sách cho phép; một listener có thể nhận event nhưng không tạo ra kết quả nghiệp vụ mong đợi.

Vì vậy, sau khi thêm module, cần kiểm tra ở nhiều mức:

1. **Kiểm thử cấu trúc kiến trúc** để xác nhận module graph và quy tắc phụ thuộc vẫn hợp lệ.
2. **Kiểm thử tích hợp module** để kiểm tra module mới hoạt động trong phạm vi Spring context của nó.
3. **Kiểm thử hợp đồng consumer/provider** để bảo đảm module tiêu thụ chỉ dựa vào API được công bố và module cung cấp vẫn giữ đúng hành vi.
4. **Kiểm thử luồng sự kiện** nếu module mới giao tiếp qua application event.

Bài học này sử dụng ví dụ thêm module **shipping** vào ứng dụng có **orders** và **inventory**, sau đó xây dựng các kiểm thử giúp phát hiện lỗi kiến trúc và lỗi tích hợp.

## 1. Xác định hợp đồng bị ảnh hưởng khi thêm module

Giả sử ứng dụng hiện có:

- **orders**: quản lý đơn hàng và công bố event **OrderPlaced**.
- **inventory**: giữ hàng và quản lý số lượng tồn.
- **shipping**: module mới, tiếp nhận đơn hàng đã được xác nhận để lên kế hoạch giao hàng.

Module **shipping** cần tham chiếu event **OrderPlaced** của **orders**. Nếu event nằm trong Named Interface **events**, module mới cần khai báo phụ thuộc đúng vào giao diện đó:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders :: events"
)
package com.acme.shop.shipping;
~~~

Sau khi thêm module, các câu hỏi cần được trả lời:

- Spring Modulith có nhận diện **shipping** là một Application Module không?
- **shipping** có chỉ sử dụng hợp đồng được **orders** công bố không?
- Dependency mới có tạo chu trình hoặc truy cập package nội bộ không?
- Listener trong **shipping** có phản ứng đúng với **OrderPlaced** không?
- Những API hoặc event hiện có của **orders** có còn đáp ứng consumer cũ không?

Mỗi câu hỏi cần loại kiểm thử phù hợp. Một bài test duy nhất không thể thay thế tất cả các mức xác minh.

## 2. Kiểm thử cấu trúc bằng ApplicationModules.verify()

Đầu tiên, tạo một bài test kiến trúc ở cấp ứng dụng:

~~~java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

**ApplicationModules.of(ShopApplication.class)** phân tích cấu trúc package để xây dựng mô hình module. **verify()** kiểm tra các quy tắc kiến trúc quan trọng, bao gồm:

- Không có chu trình phụ thuộc giữa các Application Module.
- Module không truy cập type thuộc package nội bộ của module khác theo quy tắc module đóng.
- Các outgoing dependency thực tế tuân thủ **allowedDependencies** nếu module khai báo allowlist.

Khi thêm **shipping**, bài test này có thể phát hiện các lỗi như:

~~~java
// Không nên: shipping tham chiếu implementation nội bộ của orders.
import com.acme.shop.orders.internal.OrderRepository;
~~~

Hoặc một dependency chưa được cho phép:

~~~java
// shipping khai báo chỉ dùng orders :: events,
// nhưng mã nguồn lại import API của inventory.
import com.acme.shop.inventory.StockReservation;
~~~

Khi đó, cần xác định module mới có thực sự cần hợp đồng đó hay không. Nếu cần, hãy công bố một API phù hợp và cập nhật **allowedDependencies** có chủ đích. Không nên mở rộng quyền phụ thuộc chỉ để làm cho test qua mà chưa xem xét thiết kế.

**verify()** kiểm tra cấu trúc và dependency rule. Nó không kiểm tra nội dung nghiệp vụ của một event, kết quả tính toán của API hoặc việc một bean có thực sự tạo được kết quả đúng lúc chạy.

## 3. Kiểm thử tích hợp riêng cho module mới

Spring Modulith cung cấp **@ApplicationModuleTest** để khởi tạo Spring context giới hạn theo Application Module đang kiểm thử. Thêm test starter vào cấu hình build:

~~~xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Đặt test class trong package của module cần kiểm thử hoặc subpackage của nó. Ví dụ:

~~~java
package com.acme.shop.shipping;

import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest
class ShippingModuleTests {

    // Các test tích hợp của module shipping.
}
~~~

Test này khởi tạo module **shipping** theo cơ chế module slicing của Spring Modulith. Component scan, auto-configuration và entity scan được giới hạn theo module đang kiểm thử. Nhờ đó, test có thể phát hiện module vô tình dựa vào bean chỉ được tạo bởi cấu hình nằm ngoài ranh giới của nó.

### Chọn bootstrap mode phù hợp

**@ApplicationModuleTest** hỗ trợ ba bootstrap mode:

| Mode | Phạm vi Spring context |
|---|---|
| **STANDALONE** | Chỉ module đang kiểm thử; đây là mặc định |
| **DIRECT_DEPENDENCIES** | Module đang kiểm thử và các module mà nó phụ thuộc trực tiếp |
| **ALL_DEPENDENCIES** | Module đang kiểm thử cùng toàn bộ cây dependency, bao gồm phụ thuộc bắc cầu |

Ví dụ muốn kiểm thử **shipping** cùng các module mà nó phụ thuộc trực tiếp:

~~~java
package com.acme.shop.shipping;

import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest(
    mode = ApplicationModuleTest.BootstrapMode.DIRECT_DEPENDENCIES
)
class ShippingIntegrationTests {
}
~~~

Chọn mode theo mục tiêu kiểm thử:

- Dùng **STANDALONE** để kiểm tra module độc lập và thay thế các bean bên ngoài bằng mock khi cần.
- Dùng **DIRECT_DEPENDENCIES** khi cần xác minh tích hợp với các module mà module hiện tại gọi trực tiếp.
- Dùng **ALL_DEPENDENCIES** khi kịch bản thực sự cần toàn bộ cây module phụ thuộc.

Không nên mở rộng context lên toàn bộ ứng dụng theo thói quen. Nếu một module cần quá nhiều bean từ module khác chỉ để khởi tạo, đó có thể là dấu hiệu coupling cao. Hãy xem xét mock các dependency bên ngoài hoặc thiết kế lại hợp đồng.

## 4. Mock dependency ngoài module khi kiểm thử độc lập

Giả sử **shipping** gọi API **OrderManagement** của **orders**. Trong test **STANDALONE**, Spring chỉ khởi tạo module **shipping**; bean **OrderManagement** ở module khác không được nạp vào context. Có thể thay bean đó bằng mock:

~~~java
package com.acme.shop.shipping;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.acme.shop.orders.OrderManagement;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@ApplicationModuleTest
class ShippingModuleTests {

    @MockitoBean
    OrderManagement orderManagement;

    @Autowired
    ShippingService shippingService;

    @Test
    void requestsOrderDetailsThroughPublicApi() {
        when(orderManagement.findOrder("order-42"))
            .thenReturn(new OrderDetails("order-42", "customer-7"));

        shippingService.prepareShipment("order-42");

        verify(orderManagement).findOrder("order-42");
    }
}
~~~

Ví dụ minh họa cách cô lập consumer bằng hợp đồng công khai. **OrderManagement**, **OrderDetails** và **ShippingService** là các kiểu minh họa; trong ứng dụng thực tế, thay bằng API và nghiệp vụ đang có. Phần quan trọng của test là **shipping** chỉ biết **OrderManagement**, không cần biết class triển khai của **orders**.

Nếu cần kiểm thử tích hợp thực với bean **OrderManagement**, có thể chọn **DIRECT_DEPENDENCIES**. Khi đó, context sẽ nạp thêm module **orders** nếu đây là dependency trực tiếp của **shipping**.

## 5. Kiểm thử hành vi của API công khai

Kiểm thử hợp đồng consumer/provider cần tập trung vào hành vi mà API cam kết. Ví dụ, nếu **orders** công bố:

~~~java
package com.acme.shop.orders;

public interface OrderManagement {

    OrderDetails findOrder(String orderId);
}
~~~

Consumer chỉ nên dựa vào chữ ký và ý nghĩa của **findOrder**. Khi thêm **shipping**, cần xác nhận:

- **findOrder** vẫn trả về đơn hàng đúng theo mã được yêu cầu.
- Trạng thái đơn hàng không hợp lệ được xử lý theo hợp đồng đã định nghĩa.
- Dữ liệu trả về không vô tình phơi bày entity hoặc repository nội bộ.
- Thay đổi implementation của **orders** không buộc **shipping** sửa mã nguồn nếu hợp đồng công khai không đổi.

Test của module cung cấp nên xác nhận các kết quả nghiệp vụ và các trường hợp biên. Test của consumer nên xác nhận nó sử dụng API công khai đúng cách. Khi hợp đồng thay đổi, chạy cả hai nhóm test để phát hiện thay đổi không tương thích.

## 6. Kiểm thử event contract bằng Scenario

Nếu **shipping** nhận event **OrderPlaced**, chỉ kiểm tra module graph là chưa đủ. Cần xác nhận event được phát và listener tạo ra kết quả mong đợi.

Spring Modulith cung cấp **Scenario** trong các test dùng **@ApplicationModuleTest**. Có thể kiểm thử một luồng event như sau:

~~~java
package com.acme.shop.shipping;

import static org.junit.jupiter.api.Assertions.assertEquals;

import com.acme.shop.orders.events.OrderPlaced;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.Scenario;

@ApplicationModuleTest
class ShippingEventTests {

    @Test
    void schedulesShipmentAfterOrderPlaced(Scenario scenario) {
        scenario.publish(new OrderPlaced("order-42"))
            .andWaitForEventOfType(ShipmentScheduled.class)
            .matching(event -> event.orderId().equals("order-42"))
            .toArriveAndVerify(event ->
                assertEquals("order-42", event.orderId())
            );
    }
}
~~~

Kịch bản gồm:

1. Phát event **OrderPlaced** làm stimulus.
2. Chờ event **ShipmentScheduled** phù hợp được phát.
3. Xác minh event nhận được có mã đơn hàng đúng.

**Scenario** cũng hỗ trợ bắt đầu bằng lời gọi một Spring bean và chờ event hoặc trạng thái thay đổi. Với event listener bất đồng bộ hoặc transactional, API này giúp quản lý việc chờ kết quả thay vì dùng **Thread.sleep()** tùy tiện.

Lưu ý: stimulus của **Scenario** được thực hiện trong transaction callback để bảo đảm event và transactional listener được xử lý theo cơ chế phù hợp. Callback có thể mở transaction mới; thay đổi database phát sinh từ stimulus không mặc nhiên được rollback cùng transaction của test. Hãy dọn dữ liệu test rõ ràng, có thể dùng các thao tác cleanup mà Scenario cung cấp.

## 7. Kiểm tra dependency contract sau khi thêm module

Ngoài test cấu trúc chung, có thể tạo bảng rà soát dependency cho module mới:

| Hạng mục | Điều cần xác nhận | Cách kiểm thử |
|---|---|---|
| Module được nhận diện | Package gốc đúng và module xuất hiện trong mô hình | **ApplicationModules.of(...).verify()** |
| API được sử dụng đúng | Consumer import type trong API package hoặc Named Interface | Review import và module test |
| Dependency được cho phép | Outgoing dependency phù hợp **allowedDependencies** | **verify()** |
| Không có chu trình | Dependency graph không có cycle | **verify()** |
| Bean được kết nối | Provider/consumer khởi tạo được trong context phù hợp | **@ApplicationModuleTest** |
| Hành vi API ổn định | Kết quả nghiệp vụ đáp ứng hợp đồng | Unit/integration contract test |
| Event được xử lý đúng | Listener tạo event hoặc state mong đợi | **Scenario** |

Một module mới có thể hợp lệ về cấu trúc nhưng sai hành vi. Ngược lại, test nghiệp vụ có thể chạy qua trong khi module đang import một package nội bộ. Cần giữ cả kiểm thử kiến trúc và kiểm thử hành vi.

## 8. Đưa kiểm thử vào CI

Một pipeline kiểm tra module có thể chạy theo trình tự:

1. Biên dịch source và test để phát hiện lỗi type, import hoặc chữ ký API.
2. Chạy test kiến trúc có **ApplicationModules.verify()**.
3. Chạy unit test cho logic nghiệp vụ của module mới.
4. Chạy **@ApplicationModuleTest** cho module mới và các consumer chịu ảnh hưởng.
5. Chạy các kịch bản event hoặc integration test cần thiết.

Khi thêm module, hãy bảo đảm test của các module đang phụ thuộc vào API bị thay đổi cũng được chạy. Nếu dùng change-aware test execution của Spring Modulith, có thể cấu hình **spring-modulith-junit** để chọn test dựa trên các module bị thay đổi và các module phụ thuộc vào chúng. Cơ chế này tối ưu phạm vi chạy test; nó không thay thế việc cấu hình pipeline và kiểm tra kết quả build.

## 9. Các lỗi kiểm thử thường gặp

**Chỉ chạy verify() rồi kết luận hợp đồng đúng.** **verify()** kiểm tra cấu trúc module và dependency rule, không xác minh kết quả nghiệp vụ. Hãy thêm test API hoặc event cho hành vi cần bảo vệ.

**Dùng @SpringBootTest cho mọi module test.** Context toàn ứng dụng có thể che khuất việc module đang dựa vào bean ngoài ranh giới. Dùng **@ApplicationModuleTest** để nhìn rõ phạm vi module và chọn dependency cần đưa vào.

**Mở rộng bootstrap mode để test hết lỗi bean.** Việc thêm toàn bộ dependency có thể khiến test trở nên rộng và khó cô lập. Nếu chỉ cần kiểm tra cách consumer gọi một hợp đồng, mock bean ngoài module bằng **@MockitoBean**.

**Mock cả API đang cần kiểm thử.** Nếu mục tiêu là xác minh provider thực thi đúng hợp đồng, không mock provider đó trong test. Hãy test module cung cấp riêng, rồi test consumer với mock ở ranh giới phù hợp.

**Chỉ test implementation class.** Consumer phụ thuộc API công khai. Test nên gọi qua API hoặc event contract để việc thay implementation không làm test mất ý nghĩa.

**Bỏ qua cleanup của event test.** Kịch bản transactional có thể tạo dữ liệu tồn tại sau test. Thiết kế cleanup rõ ràng để test có thể chạy lặp lại ổn định.

## 10. Quy trình thực hiện sau khi thêm module

Khi đưa một module mới vào ứng dụng, thực hiện lần lượt:

1. Xác nhận module mới có package gốc và hợp đồng công khai phù hợp.
2. Khai báo **allowedDependencies** theo đúng API package hoặc Named Interface mà module cần dùng.
3. Chạy **ApplicationModules.of(ShopApplication.class).verify()** để kiểm tra cấu trúc toàn ứng dụng.
4. Viết **@ApplicationModuleTest** trong package của module mới để kiểm tra module slice.
5. Mock các dependency ngoài module khi muốn kiểm thử độc lập; chọn bootstrap mode mở rộng khi thật sự cần tích hợp dependency thật.
6. Viết test consumer/provider cho các API bị ảnh hưởng.
7. Nếu giao tiếp qua event, dùng **Scenario** để kiểm tra stimulus và outcome.
8. Chạy toàn bộ nhóm test liên quan trong CI trước khi chấp nhận thay đổi.

Khi các mức kiểm thử này cùng đạt, đội ngũ có bằng chứng rõ hơn rằng module mới được kết nối đúng qua hợp đồng công khai, tuân thủ dependency rule và giữ được hành vi mà các module khác đang dựa vào.

## Tài liệu tham khảo

- [Spring Modulith Reference — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): kiểm tra module graph, truy cập package nội bộ và dependency rules.
- [Spring Modulith Reference — Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html): spring-modulith-starter-test, @ApplicationModuleTest, bootstrap modes, @MockitoBean và Scenario.
- [Javadoc — ApplicationModuleTest](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/test/ApplicationModuleTest.html): cấu hình bootstrap cho module integration tests.

# ApplicationModuleTest

`@ApplicationModuleTest` là annotation kiểm thử của Spring Modulith dùng để khởi động Spring application context trong phạm vi một application module. Thay vì luôn khởi động toàn bộ ứng dụng như một integration test thông thường, bài test có thể tập trung vào module đang kiểm thử và chỉ đưa các module phụ thuộc cần thiết vào context.

Với ứng dụng dùng application events, cách kiểm thử này giúp xác nhận module phát event đúng khi nghiệp vụ xảy ra, listener trong module phản ứng đúng và các dependency giữa module được khai báo rõ. Spring Modulith còn cung cấp `Scenario` để kiểm thử luồng event, bao gồm việc chờ event được phát và xác minh kết quả của listener bất đồng bộ.

## 1. Vì sao cần kiểm thử theo module?

Một ứng dụng Spring Modulith thường có nhiều module nghiệp vụ. Mỗi module sở hữu một phần mô hình và hành vi, nhưng vẫn có thể giao tiếp với module khác qua application event. Nếu mọi test đều dùng toàn bộ application context, test suite có thể khởi động chậm, phụ thuộc nhiều cấu hình và khó xác định module nào gây lỗi.

Kiểm thử theo module giúp:

- Khởi động đúng phạm vi thành phần thuộc module đang kiểm thử.
- Phát hiện module phụ thuộc ngoài dự kiến khi context không thể khởi động ở chế độ cô lập.
- Kiểm tra các use case và listener của module trong môi trường Spring thực tế.
- Giữ các test tập trung vào hợp đồng giữa module thay vì chi tiết triển khai nội bộ của module khác.
- Giảm chi phí khởi động so với việc luôn nạp toàn bộ ứng dụng, tùy cấu hình và số dependency.

Ví dụ, module `orders` phát `OrderPlaced`. Module `inventory` nhận event để giữ hàng, còn module `notifications` gửi xác nhận. Test của module `orders` nên xác nhận use case tạo đơn phát đúng event. Test của module `inventory` nên xác nhận listener xử lý `OrderPlaced` đúng. Mỗi module kiểm tra trách nhiệm mà nó sở hữu.

## 2. `@ApplicationModuleTest` hoạt động thế nào?

`@ApplicationModuleTest` là annotation kiểm thử tích hợp của Spring Modulith. Annotation này xác định module chứa test class và bootstrap context theo phạm vi module đó. Test class thường được đặt trong package của module cần kiểm thử để Spring Modulith xác định module phù hợp.

Ví dụ cấu trúc package:

```text
com.acme.shop
├── ShopApplication.java
├── orders
│   ├── OrderManagement.java
│   ├── Order.java
│   └── OrderModuleIntegrationTests.java
├── inventory
│   ├── InventoryManagement.java
│   └── InventoryModuleIntegrationTests.java
└── notifications
    └── NotificationModuleIntegrationTests.java
```

Test của module `orders` có thể khai báo:

```java
import org.springframework.modulith.test.ApplicationModuleTest;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

@ApplicationModuleTest
class OrderModuleIntegrationTests {

    @Autowired
    OrderManagement orders;

    @Test
    void createsAnOrder() {
        // Thực hiện use case qua API công khai của module.
    }
}
```

Test chạy với Spring context được giới hạn theo module `orders` và chế độ bootstrap đang chọn. `OrderManagement` đại diện cho API ứng dụng của module; test nên tương tác qua API này thay vì khởi tạo trực tiếp các class nội bộ nếu mục tiêu là kiểm thử tích hợp module.

Để sử dụng annotation, dự án cần có test support tương ứng của Spring Modulith, thường là dependency `spring-modulith-starter-test` phù hợp với dòng phiên bản Spring Boot/Spring Modulith đang dùng. Không trộn các artifact Spring Modulith khác phiên bản trong cùng test runtime.

## 3. Các bootstrap mode

`@ApplicationModuleTest` hỗ trợ các chế độ bootstrap để điều chỉnh phạm vi module được đưa vào application context. Ba chế độ thường dùng là:

| Mode | Phạm vi | Khi nên dùng |
| --- | --- | --- |
| `STANDALONE` | Chỉ module đang kiểm thử. | Kiểm tra module có thể hoạt động với các dependency được thay thế hoặc cấu hình trong test. |
| `DIRECT_DEPENDENCIES` | Module đang kiểm thử và các module mà nó phụ thuộc trực tiếp. | Kiểm tra module cùng các collaborator module trực tiếp cần cho use case. |
| `ALL_DEPENDENCIES` | Module đang kiểm thử và toàn bộ dependency theo quan hệ bắc cầu. | Kiểm tra một luồng cần nhiều module phụ thuộc thực sự. |

Chế độ mặc định là `STANDALONE`. Có thể chỉ định rõ mode:

```java
import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest(mode = ApplicationModuleTest.BootstrapMode.DIRECT_DEPENDENCIES)
class OrderModuleIntegrationTests {
}
```

Hãy chọn phạm vi nhỏ nhất vẫn kiểm tra được hành vi cần thiết. Nếu test chỉ cần kiểm tra logic của module `orders`, `STANDALONE` giúp bộc lộ dependency ngoài module. Nếu use case cần module khác thực sự tham gia, `DIRECT_DEPENDENCIES` hoặc `ALL_DEPENDENCIES` có thể phù hợp hơn.

Không nên chuyển tất cả test sang `ALL_DEPENDENCIES` chỉ để làm context khởi động thành công. Cách đó có thể che giấu việc module đang phụ thuộc quá rộng. Khi một test chỉ chạy được ở mode rộng, hãy xem đó là tín hiệu để kiểm tra lại ranh giới module hoặc bổ sung test double phù hợp.

## 4. Kiểm thử API công khai của module

Một module nên cung cấp API ứng dụng đủ rõ để các caller và test tương tác. Test module nên gọi API này để kiểm tra hành vi, thay vì truy cập trực tiếp repository hoặc service nội bộ.

Ví dụ use case tạo đơn hàng:

```java
import java.util.UUID;

public interface OrderManagement {
    UUID placeOrder(PlaceOrder command);
}
```

Test có thể gọi API và xác minh kết quả nghiệp vụ:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest
class OrderModuleIntegrationTests {

    @Autowired
    OrderManagement orders;

    @Test
    void placesAnOrder() {
        UUID orderId = orders.placeOrder(new PlaceOrder(/* dữ liệu test */));

        assertThat(orderId).isNotNull();
    }
}
```

Phần `PlaceOrder` cần được khởi tạo bằng dữ liệu hợp lệ theo mô hình của ứng dụng. Test tập trung vào kết quả quan sát được qua API module, để có thể thay đổi cách triển khai bên trong mà không phải viết lại test cho từng class nội bộ.

Nếu cần kiểm tra persistence, có thể inject repository hoặc query API trong test khi đó là điều cần thiết để xác minh kết quả. Tuy nhiên, test hành vi module nên ưu tiên API nghiệp vụ và chỉ kiểm tra chi tiết lưu trữ ở những test persistence chuyên biệt.

## 5. Kiểm thử application event bằng `Scenario`

Spring Modulith cung cấp `Scenario` trong test support để kiểm thử tương tác dựa trên event. API này giúp kích hoạt một hành động hoặc publish event, chờ event mong đợi và xác minh event được quan sát.

Ví dụ module `orders` phát `OrderPlaced` khi tạo đơn:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.Scenario;

@ApplicationModuleTest
class OrderEventTests {

    @Autowired
    OrderManagement orders;

    @Autowired
    Scenario scenario;

    @Test
    void publishesOrderPlacedAfterCreatingAnOrder() {
        scenario.stimulate(() -> orders.placeOrder(new PlaceOrder(/* dữ liệu test */)))
                .andWaitForEventOfType(OrderPlaced.class)
                .toArriveAndVerify(event ->
                        assertThat(event.orderId()).isNotNull());
    }
}
```

`stimulate(...)` thực hiện hành động kích hoạt luồng nghiệp vụ. `andWaitForEventOfType(...)` chờ event có kiểu mong đợi được phát; `toArriveAndVerify(...)` chạy assertion trên event nhận được. Cách này phù hợp với listener bất đồng bộ vì test chờ theo sự kiện thay vì đoán thời điểm hoàn tất bằng một khoảng `sleep` cố định.

Nếu chỉ muốn kiểm tra phản ứng của listener với một event đầu vào, có thể publish event trực tiếp trong scenario:

```java
@Test
void reactsToOrderPlaced() {
    UUID orderId = UUID.randomUUID();

    scenario.publish(new OrderPlaced(/* eventId, orderId, occurredAt */))
            .andWaitForEventOfType(InventoryReserved.class)
            .toArriveAndVerify(event ->
                    assertThat(event.orderId()).isEqualTo(orderId));
}
```

Đây là ví dụ minh họa; constructor hoặc factory của event cần khớp với event DTO thực tế. Test nên xác minh hành vi qua event kết quả hoặc trạng thái được công khai, không phụ thuộc vào thứ tự thực thi nội bộ không được cam kết.

## 6. Kiểm thử listener của module nhận

Module nhận nên có test riêng để xác minh listener chuyển event thành hành động nghiệp vụ đúng. Ví dụ, module `inventory` nhận `OrderPlaced` và phát `InventoryReserved` sau khi giữ hàng thành công.

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.Scenario;

@ApplicationModuleTest
class InventoryEventTests {

    @Autowired
    Scenario scenario;

    @Test
    void reservesInventoryWhenOrderIsPlaced() {
        UUID orderId = UUID.randomUUID();

        scenario.publish(new OrderPlaced(/* eventId, orderId, occurredAt */))
                .andWaitForEventOfType(InventoryReserved.class)
                .toArriveAndVerify(event ->
                        assertThat(event.orderId()).isEqualTo(orderId));
    }
}
```

Test này tập trung vào module `inventory`. Nếu `OrderPlaced` là event hợp đồng mà module inventory nhận, test có thể dùng fixture event để kích hoạt listener. Không cần khởi động toàn bộ module `orders` chỉ để kiểm tra phản ứng của inventory với payload đã xác định.

Nếu listener không phát event kết quả, có thể xác minh trạng thái thông qua API query của module hoặc repository trong phạm vi test. Khi kiểm tra trạng thái persistence, hãy bảo đảm test chờ listener hoàn tất trước khi đọc dữ liệu.

## 7. Kiểm thử listener bất đồng bộ và after-commit

`@ApplicationModuleListener` thường được dùng khi listener cần chạy sau khi transaction nguồn commit và trong transaction riêng. Điều này có nghĩa test cần tạo một transaction thực sự commit để listener được kích hoạt.

Một lỗi thường gặp là đặt `@Transactional` trên test và để test framework rollback transaction ở cuối phương thức. Nếu transaction nguồn chưa commit, listener after-commit có thể chưa chạy. Khi đó, test có thể timeout dù listener triển khai đúng.

Các nguyên tắc khi kiểm thử:

- Không bọc test after-commit trong transaction sẽ luôn rollback nếu mục tiêu là xác minh listener được kích hoạt sau commit.
- Tạo transaction boundary rõ ràng và để transaction nghiệp vụ commit trước khi chờ event.
- Dùng `Scenario` để chờ event hoặc trạng thái mong đợi với timeout hữu hạn.
- Không dùng `Thread.sleep` cố định vì thời gian xử lý phụ thuộc môi trường và tải.
- Đảm bảo test không đọc projection hoặc dữ liệu listener trước khi listener hoàn tất.

Ví dụ dùng `TransactionTemplate` để tạo transaction có commit rõ ràng khi cần kiểm soát thủ công:

```java
import org.springframework.transaction.support.TransactionTemplate;

class OrderEventTests {

    private final TransactionTemplate transactions;
    private final OrderManagement orders;

    OrderEventTests(
            TransactionTemplate transactions,
            OrderManagement orders) {
        this.transactions = transactions;
        this.orders = orders;
    }

    void createOrderInCommittedTransaction() {
        transactions.executeWithoutResult(status ->
                orders.placeOrder(new PlaceOrder(/* dữ liệu test */)));
    }
}
```

Đây là cách minh họa ranh giới transaction; trong test thực tế, cần kết hợp nó với `Scenario` hoặc cơ chế chờ listener để xác minh kết quả sau commit. Không gọi `commit()` thủ công trên transaction test được quản lý bởi framework.

## 8. Chọn bootstrap mode phù hợp với event test

Khi kiểm thử event, phạm vi context quyết định listener nào được đăng ký và module nào có thể tham gia luồng xử lý.

- Dùng `STANDALONE` khi test module phát event hoặc module nhận có thể kiểm tra độc lập với module khác.
- Dùng `DIRECT_DEPENDENCIES` khi luồng cần các module mà module đang test phụ thuộc trực tiếp.
- Dùng `ALL_DEPENDENCIES` khi cần một luồng tích hợp đi qua nhiều module phụ thuộc bắc cầu.

Nếu một listener thuộc module khác không xuất hiện trong context `STANDALONE`, đó là hành vi theo phạm vi bootstrap. Không nên kết luận event không được phát chỉ vì listener ngoài module không được khởi tạo. Hãy kiểm thử publisher trong module nguồn và listener trong module nhận bằng các test riêng, sau đó thêm một số integration test rộng hơn để xác nhận luồng liên module quan trọng.

Test mode rộng hơn có thể kiểm tra wiring tích hợp, nhưng không thay thế test độc lập của từng module. Nếu mọi test đều dùng `ALL_DEPENDENCIES`, lỗi ranh giới và coupling có thể khó nhận ra.

## 9. Dùng test double cho dependency ngoài module

Ở chế độ `STANDALONE`, một dependency bên ngoài module có thể không được nạp vào context. Nếu mục tiêu test là kiểm tra hành vi module hiện tại, có thể thay dependency bằng test double hoặc mock ở ranh giới phù hợp.

Ví dụ, module `orders` gọi một cổng thanh toán được khai báo như dependency:

```java
public interface PaymentGateway {
    PaymentResult authorize(PaymentRequest request);
}
```

Test có thể thay implementation thật bằng mock bean theo phiên bản Spring đang dùng. Với các phiên bản Spring Framework hỗ trợ `@MockitoBean`, có thể dùng:

```java
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@ApplicationModuleTest
class OrderPaymentTests {

    @MockitoBean
    PaymentGateway paymentGateway;

    @Autowired
    OrderManagement orders;

    @Test
    void createsOrderWhenPaymentIsAuthorized() {
        // Cấu hình mock và gọi API module.
    }
}
```

Ở các phiên bản Spring Boot cũ hơn, dự án có thể đang dùng `@MockBean`. Chọn annotation theo phiên bản dependency của dự án; không thêm đồng thời nhiều cơ chế mock bean cho cùng một collaborator.

Mock nên đặt ở ranh giới dependency bên ngoài hoặc hệ thống không thuộc module test. Không mock chính class đang kiểm thử hoặc quá nhiều collaborator nội bộ, vì test khi đó chỉ xác minh cách mock được gọi thay vì hành vi module.

## 10. Kiểm thử persistence và external dependency

`@ApplicationModuleTest` khởi động Spring context trong phạm vi module, nhưng không tự động thay thế chiến lược kiểm thử database hoặc hệ thống ngoài.

Với persistence:

- Dùng database phù hợp với ứng dụng khi cần xác minh query, constraint, transaction và mapping thực tế.
- Có thể dùng Testcontainers để chạy cùng loại database với môi trường triển khai.
- Không dựa hoàn toàn vào database in-memory nếu hành vi SQL hoặc locking khác với production.
- Kiểm tra transaction listener và transaction nguồn theo đúng ranh giới.

Với HTTP, broker hoặc hệ thống ngoài:

- Dùng mock server hoặc test container khi cần xác minh giao thức thực tế.
- Kiểm tra timeout, lỗi kết nối và retry ở test chuyên biệt.
- Giữ unit test nhanh bằng fake/mock, rồi dùng một số integration test để xác nhận adapter.
- Không gọi dịch vụ production hoặc dùng credential thật trong test.

Test module nên tập trung vào module đang sở hữu hành vi. Kiểm thử adapter và hạ tầng có thể nằm ở test riêng để không làm mọi test module phụ thuộc vào broker hoặc dịch vụ ngoài.

## 11. Kiểm thử Event Publication Registry

Event Publication Registry theo dõi publication tới transactional listener. Khi dùng persistent adapter, nó giúp xác định listener nào đã hoàn tất và publication nào còn dang dở để phục hồi.

Một số hành vi nên được xác minh bằng integration test phù hợp:

- Publication được đăng ký trong transaction nguồn và không còn hiệu lực nếu transaction nguồn rollback.
- Listener thành công dẫn tới publication được ghi nhận hoàn tất.
- Listener thất bại không bị đánh dấu hoàn tất sai.
- Một listener lỗi không làm mất trạng thái độc lập của listener khác.
- Publication chưa hoàn tất có thể được truy vấn hoặc resubmit theo API của phiên bản Spring Modulith.
- Serializer có thể đọc event payload đã lưu nếu ứng dụng cần xử lý lại sau deploy.

Không nên phụ thuộc vào tên bảng hoặc cột nội bộ của registry trong test module thông thường. Nếu cần xác minh persistence adapter, hãy viết integration test dành riêng cho adapter và schema do phiên bản framework quản lý. Ưu tiên API công khai khi kiểm tra trạng thái publication.

## 12. Phân biệt ApplicationModuleTest và architecture verification

`@ApplicationModuleTest` kiểm thử hành vi module trong Spring application context. Nó không tự động thay thế việc xác minh kiến trúc toàn bộ module.

Spring Modulith cung cấp `ApplicationModules` để kiểm tra cấu trúc module và các quy tắc phụ thuộc. Một architecture test có thể viết như sau:

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

Test này xác minh các quy tắc kiến trúc mà Spring Modulith nhận diện, chẳng hạn dependency giữa module và các vi phạm cấu trúc. Nó không chạy use case tạo đơn hoặc kiểm tra listener xử lý event.

Hai loại test bổ sung cho nhau:

| Loại test | Mục tiêu |
| --- | --- |
| Unit test | Kiểm tra logic class hoặc hàm riêng lẻ. |
| `@ApplicationModuleTest` | Kiểm tra hành vi module trong Spring context giới hạn theo module. |
| Event `Scenario` test | Kiểm tra kích hoạt event và phản ứng của listener, bao gồm xử lý bất đồng bộ. |
| Architecture verification | Kiểm tra cấu trúc module và dependency rule. |
| Full application integration test | Kiểm tra một số luồng xuyên nhiều module và hạ tầng tích hợp. |

Không nên dùng một full application test duy nhất để thay cho các test module và architecture test. Mỗi loại test cung cấp một lớp bảo đảm khác nhau.

## 13. Tổ chức test suite theo trách nhiệm module

Một cách tổ chức dễ duy trì là đặt test gần module mà nó kiểm tra và phân nhóm theo mục tiêu:

```text
orders/
├── OrderManagement.java
├── OrderPlaced.java
└── tests/
    ├── OrderModuleIntegrationTests.java
    ├── OrderEventPublicationTests.java
    └── OrderPersistenceTests.java

inventory/
├── InventoryManagement.java
├── InventoryOnOrderPlaced.java
└── tests/
    ├── InventoryModuleIntegrationTests.java
    └── InventoryEventTests.java
```

Tên package và vị trí thư mục thực tế có thể khác, nhưng test class cần nằm trong package mà Spring Modulith có thể xác định module mục tiêu. Không đặt mọi test ở package gốc nếu điều đó làm module được suy ra không rõ ràng.

Giữ fixture event và dữ liệu test dễ đọc. Nếu nhiều test dùng chung fixture, tạo builder hoặc factory trong test source set. Không đưa dữ liệu test vào production module chỉ để tiện khởi tạo test.

## 14. Các lỗi thường gặp khi dùng `@ApplicationModuleTest`

- **Test không tìm thấy module:** test class nằm ngoài package của module hoặc package structure không khớp cấu hình ứng dụng.
- **Thiếu bean dependency:** mode `STANDALONE` không nạp module khác mà test đang trực tiếp cần. Chọn mode phù hợp hoặc thay dependency bằng test double.
- **Context quá rộng:** dùng `ALL_DEPENDENCIES` cho mọi test khiến thời gian khởi động tăng và che giấu coupling.
- **Listener after-commit không chạy:** test transaction bị rollback thay vì commit.
- **Test async chập chờn:** dùng `Thread.sleep` thay vì chờ event hoặc điều kiện với timeout.
- **Mock quá sâu:** mock toàn bộ collaborator làm test không còn xác minh hành vi module.
- **Nhầm architecture test:** nghĩ rằng context khởi động thành công đồng nghĩa module dependency rules đều hợp lệ.
- **Phụ thuộc schema registry nội bộ:** test truy vấn trực tiếp bảng framework thay vì API công khai.
- **Không kiểm tra listener failure:** chỉ test happy path, bỏ qua publication chưa hoàn tất và retry.

Khi test context không khởi động, hãy đọc nguyên nhân bean thiếu và module chứa bean đó. Đừng lập tức mở rộng bootstrap mode; trước tiên xác định dependency có thuộc hợp đồng của module hay chỉ là một test fixture cần thay thế.

## 15. Checklist cho ApplicationModuleTest

- [ ] Test class nằm trong package của module cần kiểm thử.
- [ ] Dependency test support của Spring Modulith phù hợp với phiên bản ứng dụng.
- [ ] Bootstrap mode được chọn theo phạm vi hành vi cần xác minh.
- [ ] Test tương tác qua API công khai của module khi có thể.
- [ ] Dependency ngoài module được thay thế có chủ đích nếu dùng `STANDALONE`.
- [ ] Event flow được kiểm thử bằng `Scenario` khi cần chờ event/listener bất đồng bộ.
- [ ] Test after-commit tạo transaction commit thật.
- [ ] Listener success, failure và retry có test phù hợp.
- [ ] Persistence adapter được kiểm tra bằng database phù hợp khi cần.
- [ ] Event Publication Registry được kiểm tra qua API công khai và integration test chuyên biệt.
- [ ] Architecture verification được chạy riêng bằng `ApplicationModules.verify()`.
- [ ] Test không phụ thuộc vào `Thread.sleep` hoặc thứ tự bất đồng bộ không được bảo đảm.

`@ApplicationModuleTest` giúp kiểm thử ứng dụng theo đúng ranh giới module mà Spring Modulith hướng tới. Khi kết hợp bootstrap mode phù hợp, `Scenario` cho event flow, transaction boundary rõ ràng và architecture verification riêng, test suite có thể xác nhận hành vi của từng module mà vẫn phát hiện các vấn đề tích hợp giữa chúng.

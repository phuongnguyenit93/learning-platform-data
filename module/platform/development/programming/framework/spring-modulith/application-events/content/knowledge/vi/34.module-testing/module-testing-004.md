# Kiểm thử dependency giữa các module Spring Modulith

Một module Spring Modulith thường cần sử dụng năng lực do module khác cung cấp. Ví dụ, module đơn hàng gọi API công khai của module thanh toán, module giao vận sử dụng thông tin đơn hàng, hoặc module báo cáo đọc dữ liệu do các module nghiệp vụ công bố. Khi kiểm thử, cần quyết định module phụ thuộc nào sẽ được khởi tạo thật, module nào được thay bằng test double và phạm vi application context nên rộng đến đâu.

Spring Modulith cung cấp `@ApplicationModuleTest` để khởi động một phần ứng dụng theo ranh giới module. Thuộc tính `mode` cho phép chọn mức dependency được đưa vào test context. Chọn đúng chế độ giúp kiểm tra tương tác cần thiết mà vẫn giữ test tập trung, nhanh và thể hiện rõ dependency của module. Đây là nội dung quan trọng trong module `SPRING_MODULITH_APPLICATION_EVENTS`, vì publisher, listener và các module cộng tác thường được kết nối qua event hoặc API công khai.

## 1. Dependency trong kiểm thử module là gì?

Trong kiến trúc modular, dependency là quan hệ mà một module cần dùng một hợp đồng hoặc thành phần do module khác sở hữu. Ví dụ:

```text
orders  --->  payments
orders  --->  inventory
reporting ---> orders
```

Trong sơ đồ, module `orders` phụ thuộc vào API của `payments` và `inventory`; `reporting` phụ thuộc vào API mà `orders` công bố. Một test của `orders` có thể cần:

- Chỉ khởi tạo module `orders` để kiểm tra logic nội bộ.
- Khởi tạo thêm `payments` và `inventory` để kiểm tra tương tác với các dependency trực tiếp.
- Khởi tạo cả dependency gián tiếp nếu hành vi cần kiểm tra đi qua nhiều module.
- Khởi tạo toàn bộ ứng dụng cho một số luồng tích hợp đầu cuối.

Chọn phạm vi context là một quyết định về độ sâu kiểm thử. Context càng rộng thì càng nhiều bean, cấu hình, database và hạ tầng được khởi tạo; test có thể xác nhận nhiều tương tác hơn nhưng cũng dễ chậm và phụ thuộc môi trường hơn.

## 2. `@ApplicationModuleTest` và bootstrap mode

`@ApplicationModuleTest` là annotation của Spring Modulith Test dùng để tạo application context tập trung vào module đang kiểm thử. Module được nhận diện dựa trên vị trí/package của test trong cấu trúc ứng dụng theo quy ước Spring Modulith.

Thuộc tính `mode` điều khiển các module được đưa vào context. Những chế độ thường dùng là:

| Bootstrap mode | Phạm vi khởi tạo | Khi nên dùng |
| --- | --- | --- |
| `STANDALONE` | Chỉ module đang kiểm thử | Kiểm tra module độc lập hoặc khi dependency được thay bằng test double |
| `DIRECT_DEPENDENCIES` | Module đang kiểm thử và các module mà nó phụ thuộc trực tiếp | Kiểm tra hợp tác với public API của dependency gần nhất |
| `ALL_DEPENDENCIES` | Module đang kiểm thử cùng toàn bộ dependency trực tiếp và gián tiếp | Kiểm tra luồng cần các module phụ thuộc ở nhiều tầng |
| `ALL` | Toàn bộ application modules | Kiểm tra tích hợp rộng khi cần xác nhận nhiều module cùng hoạt động |

Ví dụ:

```java
import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest(mode = ApplicationModuleTest.BootstrapMode.STANDALONE)
class OrderModuleTests {
    // Chỉ bootstrap module orders.
}
```

Khi cần các dependency trực tiếp:

```java
@ApplicationModuleTest(
        mode = ApplicationModuleTest.BootstrapMode.DIRECT_DEPENDENCIES
)
class OrderWithDependenciesTests {
    // Bootstrap orders và các module orders phụ thuộc trực tiếp.
}
```

Tên enum và API cần khớp với phiên bản Spring Modulith mà dự án đang quản lý. Hãy dùng BOM của dự án để đồng bộ `spring-modulith-test` hoặc starter test tương ứng, thay vì chọn phiên bản độc lập không tương thích với Spring Boot.

## 3. Chế độ dependency không đồng nghĩa với mock dependency

`mode` quyết định module nào được bootstrap trong Spring context. Nó không tự động biến mọi dependency bên ngoài thành mock.

Ví dụ, `DIRECT_DEPENDENCIES` có thể khởi tạo module thanh toán thật nếu module đơn hàng phụ thuộc trực tiếp vào nó. Một `PaymentGateway` kết nối tới hệ thống bên ngoài vẫn cần được cấu hình hoặc thay bằng fake/mock theo mục đích test.

Hãy phân biệt ba nhóm:

| Nhóm | Cách xử lý thường dùng |
| --- | --- |
| Module nội bộ là dependency cần kiểm tra | Khởi tạo module thật bằng bootstrap mode phù hợp |
| Hệ thống bên ngoài như payment provider, email hoặc broker | Fake, mock hoặc container test theo loại bảo đảm cần xác nhận |
| Dependency không liên quan đến hành vi đang kiểm tra | Không đưa vào context nếu có thể |

Nếu một test chỉ cần xác nhận `OrderService` gọi đúng `PaymentPort`, có thể dùng `STANDALONE` và cung cấp test double cho port. Nếu mục tiêu là xác nhận hợp đồng công khai của module thanh toán hoạt động đúng, hãy khởi tạo module thanh toán thật và thay riêng gateway bên ngoài.

## 4. Đặt test trong đúng package của module

Spring Modulith xác định module dựa trên package và cấu trúc module của ứng dụng. Vì vậy, test nên nằm trong package thuộc module cần kiểm thử, thường ở source set test với package tương ứng module chính.

Ví dụ cấu trúc:

```text
com.example.shop
├── orders
│   ├── OrderManagement.java
│   ├── Order.java
│   └── ...
├── payments
│   ├── PaymentManagement.java
│   └── ...
└── inventory
    ├── InventoryManagement.java
    └── ...
```

Test cho module `orders` nên đặt trong package `com.example.shop.orders` hoặc package con phù hợp. Ví dụ:

```java
package com.example.shop.orders;

import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest
class OrderManagementModuleTests {
}
```

Nếu test đặt ở package gốc hoặc package không thuộc module dự kiến, module được nhận diện có thể khác mong muốn. Khi test khởi tạo sai phạm vi, trước tiên hãy kiểm tra package của test và module boundary; không vội tăng bootstrap mode lên `ALL` để che khuất vấn đề.

## 5. Khi nào dùng `STANDALONE`?

`STANDALONE` phù hợp khi muốn kiểm tra module như một đơn vị riêng. Dependency từ module khác có thể được thay bằng test double thông qua port hoặc bean test.

Ví dụ module đơn hàng cần gọi cổng thanh toán:

```java
public interface PaymentUseCase {
    PaymentResult requestPayment(PaymentRequest request);
}
```

```java
@Service
class OrderApplicationService {

    private final PaymentUseCase payments;
    private final OrderRepository orders;

    OrderApplicationService(
            PaymentUseCase payments,
            OrderRepository orders
    ) {
        this.payments = payments;
        this.orders = orders;
    }

    @Transactional
    public void submit(Order order) {
        orders.save(order);
        payments.requestPayment(PaymentRequest.forOrder(order));
    }
}
```

Trong test standalone, có thể cung cấp implementation giả cho `PaymentUseCase`:

```java
@ApplicationModuleTest(mode = ApplicationModuleTest.BootstrapMode.STANDALONE)
class OrderStandaloneTests {

    @TestConfiguration
    static class TestDependencies {

        @Bean
        PaymentUseCase paymentUseCase() {
            return request -> PaymentResult.accepted("test-payment");
        }
    }

    @Autowired
    OrderApplicationService orders;
}
```

Đây là ví dụ minh họa về test configuration. Cần bảo đảm bean test được import/nhận diện trong context theo cấu hình của dự án và không xung đột với bean production. Nếu Spring context đã có bean cùng loại, dùng cơ chế thay thế bean của phiên bản Spring Test phù hợp hoặc cấu hình test riêng rõ ràng.

Ưu điểm của standalone test là tập trung vào logic và hợp đồng mà module sở hữu. Nhược điểm là test double không xác nhận module dependency thật có hoạt động đúng; cần có test riêng cho module cung cấp API.

## 6. Khi nào dùng `DIRECT_DEPENDENCIES`?

Chọn `DIRECT_DEPENDENCIES` khi hành vi của module phụ thuộc trực tiếp vào public API của một hoặc nhiều module khác và cần kiểm tra sự phối hợp thật.

Ví dụ `orders` sử dụng `payments` và `inventory`. Test có thể bootstrap ba module này:

```java
@ApplicationModuleTest(
        mode = ApplicationModuleTest.BootstrapMode.DIRECT_DEPENDENCIES
)
class OrderDependencyIntegrationTests {

    @Autowired
    OrderApplicationService orders;

    @Autowired
    PaymentRepository payments;

    @Autowired
    InventoryRepository inventory;

    @Test
    void submitsOrderUsingPaymentAndInventoryModules() {
        // Arrange dữ liệu qua API/repository phù hợp.
        // Gọi use case của orders.
        // Assert trạng thái được sở hữu bởi từng module.
    }
}
```

Test này có thể xác nhận tương tác qua các bean thật của module dependency. Tuy nhiên, hãy cẩn trọng khi inject repository nội bộ của module khác. Test nên ưu tiên API công khai của module; truy cập trực tiếp repository private có thể làm test phụ thuộc vào cấu trúc lưu trữ và phá vỡ ý nghĩa của module boundary.

Nếu module `orders` chỉ phụ thuộc vào một abstraction công khai của `payments`, test direct dependency giúp phát hiện thay đổi hợp đồng hoặc wiring không tương thích. Hệ thống thanh toán bên ngoài vẫn nên được fake hoặc chạy trong sandbox/container test tùy phạm vi.

## 7. Khi nào dùng `ALL_DEPENDENCIES`?

`ALL_DEPENDENCIES` phù hợp khi hành vi cần kiểm tra đi qua nhiều tầng dependency. Ví dụ:

```text
reporting -> orders -> payments
                     -> inventory
```

Nếu test của `reporting` cần dữ liệu từ `orders`, và luồng của `orders` lại phụ thuộc vào `payments` hoặc `inventory`, chế độ này đưa toàn bộ dependency trong đồ thị vào context.

```java
@ApplicationModuleTest(
        mode = ApplicationModuleTest.BootstrapMode.ALL_DEPENDENCIES
)
class ReportingWithDependenciesTests {
    // Bootstrap reporting và dependency transitive của nó.
}
```

Chế độ này hữu ích cho một số luồng tích hợp theo module nhưng có thể làm context lớn hơn đáng kể. Nếu test cần nhiều module không phải dependency của module đang kiểm thử, `ALL_DEPENDENCIES` cũng không nhất thiết bao gồm chúng; hãy phân biệt đồ thị dependency với toàn bộ ứng dụng.

Không nên chọn chế độ này mặc định cho mọi test. Khi một dependency transitive không liên quan đến hành vi cần kiểm tra, hãy cân nhắc tách test hoặc thay thế dependency bên ngoài ở ranh giới phù hợp.

## 8. Khi nào dùng `ALL`?

`ALL` bootstrap toàn bộ application modules. Chế độ này phù hợp cho một số kiểm thử tích hợp rộng, ví dụ xác nhận một workflow đi qua nhiều module không có quan hệ dependency trực tiếp hoặc xác nhận listener ở nhiều module cùng phản ứng với một event.

Ví dụ một event được phát từ module đơn hàng và được các module kho, hóa đơn, thông báo lắng nghe. Các consumer thường không cần tạo compile-time dependency ngược về module phát event. Vì thế, việc chỉ bootstrap dependency của module publisher không bảo đảm listener ở mọi consumer được khởi tạo. Một test dùng `ALL` hoặc `@SpringBootTest` có thể phù hợp để kiểm tra luồng đầu cuối đó.

```java
@ApplicationModuleTest(mode = ApplicationModuleTest.BootstrapMode.ALL)
class OrderWorkflowIntegrationTests {
    // Kiểm tra một workflow cần nhiều module trong ứng dụng.
}
```

Không dùng `ALL` để sửa một test module đang thiếu bean mà chưa tìm hiểu nguyên nhân. Context toàn ứng dụng có thể che giấu dependency không được khai báo, làm test chậm, tăng khả năng xung đột cấu hình và khiến lỗi khó định vị.

## 9. Dependency giữa module và event listener

Trong kiến trúc event-driven, module phát event không nhất thiết phụ thuộc vào các module lắng nghe event đó. Ví dụ:

```text
orders --publishes OrderCompleted--> application event bus
                                      |       |        |
                                      v       v        v
                                  inventory billing notifications
```

Module `orders` chỉ cần công bố event contract. Các module `inventory`, `billing` và `notifications` tự đăng ký listener. Không nên tạo dependency ngược từ `orders` tới tất cả consumer chỉ để test chúng.

Vì vậy, có ba cách tổ chức test khác nhau:

1. Test publisher trong module `orders`, xác nhận event được phát đúng dữ liệu.
2. Test từng listener trong module sở hữu listener, chủ động publish event tương ứng và xác nhận hành vi của module đó.
3. Dùng một số test tích hợp rộng với `ALL` hoặc `@SpringBootTest` để xác nhận workflow giữa nhiều module.

Cách phân lớp này giữ được hướng dependency rõ ràng và giúp lỗi được định vị theo đúng module sở hữu hành vi.

## 10. Thay dependency bên ngoài bằng mock hoặc fake

Module dependency và external infrastructure dependency cần chiến lược khác nhau. Một module khác trong cùng ứng dụng có thể được khởi tạo thật để kiểm tra hợp đồng. Còn hệ thống bên ngoài như payment provider, SMTP, object storage hoặc broker thường cần fake, mock hay container test.

Với các phiên bản Spring hỗ trợ `@MockitoBean`, có thể thay bean trong context bằng mock:

```java
@ApplicationModuleTest
class OrderGatewayTests {

    @MockitoBean
    PaymentGateway paymentGateway;

    @Autowired
    OrderApplicationService orders;

    @Test
    void requestsPaymentThroughGateway() {
        // Cấu hình hành vi mock, gọi use case và xác minh kết quả.
    }
}
```

`@MockitoBean` thuộc Spring Test ở các dòng Spring Framework mới. Với phiên bản cũ hơn, dự án có thể dùng `@MockBean` của Spring Boot hoặc test configuration riêng. Hãy chọn annotation phù hợp với BOM và phiên bản Spring đang dùng.

Fake phù hợp khi cần mô phỏng stateful behavior, ví dụ payment gateway có thể trả kết quả pending rồi success. Mock phù hợp khi cần xác minh một tương tác cụ thể. Testcontainers phù hợp khi cần kiểm tra giao thức và hành vi thực của database hoặc broker.

Không mock mọi module dependency trong mọi test. Nếu tất cả dependency đều bị mock, test chỉ xác nhận module đang kiểm thử gọi đúng mock mà không chứng minh hợp đồng giữa các module còn tương thích.

## 11. Dependency test và cấu hình Spring context

Khi mở rộng bootstrap mode, số bean và cấu hình được nạp cũng tăng. Những lỗi thường gặp gồm:

- Thiếu bean vì dependency module chưa được bootstrap.
- Hai module cùng khai báo bean có tên hoặc kiểu không tương thích.
- Auto-configuration cố kết nối database/broker bên ngoài trong test không cần hạ tầng đó.
- Test configuration bị scan ngoài phạm vi dự kiến.
- Bean production được tạo cùng lúc với fake thay thế.
- Test phụ thuộc vào profile hoặc property của máy phát triển.

Hãy xử lý theo thứ tự:

1. Kiểm tra module được nhận diện từ package của test.
2. Xác định dependency là module nội bộ hay hệ thống bên ngoài.
3. Chọn bootstrap mode nhỏ nhất đáp ứng hành vi cần kiểm tra.
4. Với dependency ngoài, cấu hình fake/mock hoặc Testcontainers có chủ đích.
5. Kiểm tra profile, property và test configuration chỉ áp dụng cho test cần thiết.
6. Nếu context quá rộng, tách test thành các lớp nhỏ thay vì thêm nhiều override toàn cục.

Một test bị lỗi `NoSuchBeanDefinitionException` có thể cho thấy dependency chưa được bootstrap hoặc test đang dựa vào một bean không thuộc module. Đừng lập tức chuyển sang `ALL`; trước hết hãy xác định bean đó thuộc module nào và quan hệ dependency có đúng với kiến trúc dự kiến không.

## 12. Kiểm thử dependency qua public API

Module nên công bố một API mà consumer được phép sử dụng. Test dependency nên tương tác qua API đó thay vì truy cập class hoặc repository nội bộ.

Ví dụ module `payments` công bố:

```java
public interface PaymentManagement {
    PaymentResult requestPayment(PaymentRequest request);
}
```

Module `orders` inject `PaymentManagement` và không phụ thuộc vào implementation hoặc repository của `payments`. Trong test direct dependency, khởi tạo module `payments` thật và gọi use case của `orders`; assertion có thể kiểm tra kết quả qua API hoặc trạng thái công khai phù hợp.

Nếu test cần truy vấn trực tiếp bảng nội bộ của `payments`, có thể đó là dấu hiệu test đang phụ thuộc vào chi tiết triển khai. Hãy cân nhắc xác nhận qua kết quả nghiệp vụ hoặc API đọc được công bố. Trường hợp cần kiểm tra persistence của chính `payments`, viết test thuộc module `payments`.

## 13. Kiểm thử dependency có application event

Application event là một hợp đồng giao tiếp khác với gọi API trực tiếp. Test dependency cần xác định mục tiêu là publisher, listener hay toàn bộ workflow.

| Mục tiêu | Phạm vi test phù hợp |
| --- | --- |
| Publisher phát đúng event và payload | Test trong module publisher, dùng `ApplicationEventPublisher` hoặc `@RecordApplicationEvents` khi phù hợp |
| Listener xử lý đúng event | Test trong module sở hữu listener, publish event đầu vào và kiểm tra side effect |
| Listener dùng service thuộc dependency trực tiếp | `DIRECT_DEPENDENCIES` nếu cần module dependency thật |
| Luồng đi qua dependency transitive | `ALL_DEPENDENCIES` |
| Một event kích hoạt nhiều consumer không phụ thuộc trực tiếp | Test tích hợp rộng với `ALL` hoặc `@SpringBootTest` |

Ví dụ, test trong module kho có thể publish `OrderCompleted` và xác nhận reservation được cập nhật. Test đó không cần module đơn hàng được khởi tạo nếu chỉ kiểm tra listener. Một test workflow rộng có thể khởi tạo nhiều module để xác nhận publisher và các listener được kết nối trong cùng ứng dụng.

Nếu listener bất đồng bộ hoặc chạy sau commit, hãy chờ điều kiện hoàn tất bằng `Scenario` hoặc cơ chế await có timeout. Không giả định `publishEvent()` trả về nghĩa là mọi listener đã hoàn tất.

## 14. Chọn bootstrap mode theo mục tiêu

Có thể dùng bảng quyết định sau:

| Câu hỏi | Lựa chọn ban đầu |
| --- | --- |
| Chỉ cần kiểm tra logic và API nội bộ module? | `STANDALONE` |
| Cần module phụ thuộc trực tiếp hoạt động thật? | `DIRECT_DEPENDENCIES` |
| Cần cả chuỗi module mà dependency trực tiếp sử dụng? | `ALL_DEPENDENCIES` |
| Cần nhiều module không có quan hệ dependency trực tiếp cùng chạy? | `ALL` hoặc `@SpringBootTest` |
| Cần kiểm tra một dịch vụ ngoài? | Giữ module scope phù hợp và thay dịch vụ bằng fake/mock hoặc container |
| Cần kiểm tra broker thật? | Integration test có broker test, không chỉ mở rộng module bootstrap |

Chọn mode dựa trên câu hỏi test cần trả lời, không dựa trên mong muốn “khởi tạo càng nhiều càng tốt”. Test context nhỏ giúp phát hiện dependency bị khai báo thiếu và giảm chi phí chạy CI.

## 15. Tổ chức test suite để giữ tốc độ và độ tin cậy

Một module có thể có nhiều loại test với bootstrap mode khác nhau:

```text
orders/
├── OrderApplicationService.java
├── PaymentManagement.java
└── ...

test/
└── orders/
    ├── OrderUnitTests.java                  // Unit test, không bootstrap context
    ├── OrderStandaloneTests.java            // STANDALONE
    ├── OrderDependencyTests.java             // DIRECT_DEPENDENCIES
    └── OrderWorkflowIntegrationTests.java    // ALL hoặc SpringBootTest
```

Không nhất thiết phải tạo đủ bốn loại file cho mọi module. Cấu trúc chỉ minh họa cách tách mục tiêu. Nên giữ số lượng test toàn ứng dụng ở mức cần thiết và để phần lớn test chạy trong context module nhỏ hoặc unit test.

Spring Test có thể cache application context dựa trên cấu hình. Nếu mỗi test class thêm nhiều mock, property hoặc import khác nhau, số context cần tạo có thể tăng. Gom các test có cùng cấu hình khi hợp lý, nhưng không chia sẻ trạng thái mutable giữa test. Dữ liệu test cần có định danh riêng và được dọn dẹp theo lifecycle.

## 16. Những lỗi thường gặp khi kiểm thử dependency

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng `ALL` cho mọi module test | Context lớn, test chậm và phụ thuộc nhiều cấu hình | Chọn mode nhỏ nhất phù hợp |
| Nghĩ `DIRECT_DEPENDENCIES` tự mock dependency | Test có thể gọi module thật hoặc thiếu external bean | Tách bootstrap mode khỏi chiến lược mock |
| Đặt test ngoài package module | Spring Modulith có thể nhận diện sai module | Đặt test trong package tương ứng |
| Mock toàn bộ module khác | Không kiểm tra hợp đồng giữa các module | Giữ một số dependency nội bộ thật trong integration test |
| Inject repository nội bộ module khác | Test phụ thuộc vào implementation | Dùng public API và test trong module sở hữu repository |
| Tăng mode để chữa thiếu bean mà không tìm nguyên nhân | Che giấu dependency không rõ ràng | Xác định bean thuộc module nào và lý do cần nó |
| Nghĩ consumer event là dependency của publisher | Tạo dependency ngược không cần thiết | Test listener tại module consumer; dùng test workflow rộng khi cần |
| Không cô lập dịch vụ ngoài | Test phụ thuộc mạng, credential và trạng thái môi trường | Fake/mock hoặc container test |
| Test async nhưng assert ngay | Flaky do listener chưa hoàn tất | Dùng `Scenario` hoặc await có timeout |
| Dùng chung dữ liệu giữa các context | Test ảnh hưởng lẫn nhau | Dữ liệu riêng, cleanup và transaction rõ ràng |

## 17. Quy trình xây dựng test dependency

Khi viết test cho một module Spring Modulith, hãy thực hiện theo thứ tự:

1. Xác định module đang kiểm thử và hành vi nghiệp vụ cần chứng minh.
2. Liệt kê module dependency trực tiếp, dependency transitive và hệ thống bên ngoài.
3. Đặt test trong package thuộc module cần kiểm thử.
4. Chọn `STANDALONE`, `DIRECT_DEPENDENCIES`, `ALL_DEPENDENCIES` hoặc `ALL` theo phạm vi cần thiết.
5. Giữ module dependency thật nếu mục tiêu là kiểm tra hợp đồng giữa các module.
6. Thay external infrastructure bằng fake/mock hoặc container test theo mục tiêu.
7. Tương tác qua public API và event contract, tránh truy cập chi tiết nội bộ module khác.
8. Với event async hoặc after commit, đợi trạng thái hoàn tất bằng test support phù hợp.
9. Tách test module-level khỏi một số test workflow toàn ứng dụng.
10. Theo dõi thời gian khởi tạo context và độ ổn định của test suite trong CI.

Kiểm thử dependency giúp xác nhận một module có thể cộng tác với những module mà nó thực sự phụ thuộc, đồng thời giữ ranh giới kiến trúc có ý nghĩa. Khi chọn bootstrap mode theo mục tiêu, dùng module thật ở nơi cần kiểm tra hợp đồng và thay hạ tầng ngoài bằng test double phù hợp, test suite sẽ vừa kiểm tra được tích hợp cần thiết vừa tránh phụ thuộc toàn ứng dụng trong mọi trường hợp.

# Incoming dependency và outgoing dependency

Khi phân tích một Application Module, cần biết module đó đang phụ thuộc vào ai và những module nào đang phụ thuộc vào nó. Hai hướng này được gọi là **outgoing dependency** và **incoming dependency**. Phân biệt đúng hai hướng giúp đánh giá mức độ kết nối, xác định phạm vi ảnh hưởng khi thay đổi API và kiểm soát kiến trúc modular monolith.

Trong Spring Modulith, một module cung cấp API (provided interface) và phần triển khai nội bộ. Module khác có thể sử dụng API đó qua Spring bean, lắng nghe application event hoặc tham chiếu cấu hình được công bố. Ở chiều ngược lại, module tiêu thụ có các yêu cầu (required interface) đối với những module mà nó sử dụng. Bài học này giải thích hai hướng phụ thuộc từ góc nhìn của một module, cách đọc sơ đồ, cách xem dependency bằng API mô hình và cách kiểm chứng bằng **ApplicationModules.verify()**.

## 1. Phân biệt hai hướng phụ thuộc

Giả sử ứng dụng bán hàng có ba module:

- **orders**: quản lý đơn hàng.
- **inventory**: quản lý tồn kho.
- **payments**: xử lý thanh toán.

Module **inventory** gọi API **OrderManagement** của **orders** để xác nhận đơn hàng trước khi giữ hàng. Module **orders** gọi API **PaymentProcessing** của **payments** để thu tiền.

~~~text
inventory ────────> orders ────────> payments
~~~

Trong sơ đồ này, mũi tên biểu diễn **hướng phụ thuộc mã nguồn**: module ở đầu mũi tên tham chiếu hợp đồng do module ở cuối mũi tên cung cấp.

Vì vậy:

| Góc nhìn module | Outgoing dependency | Incoming dependency |
|---|---|---|
| **orders** | **payments** | **inventory** |
| **inventory** | **orders** | Không có trong ví dụ |
| **payments** | Không có trong ví dụ | **orders** |

**Outgoing dependency** là phụ thuộc đi ra từ module đang xét. Module đó cần API hoặc hợp đồng của module khác để hoàn thành công việc.

**Incoming dependency** là phụ thuộc đi vào module đang xét. Đây là các module khác đang sử dụng API hoặc hợp đồng mà module hiện tại công bố.

Một module có thể đồng thời có cả hai hướng. Ví dụ **orders** cung cấp API cho **inventory**, đồng thời sử dụng API của **payments**.

## 2. Outgoing dependency: module cần những gì?

Outgoing dependency thể hiện các module mà một module cần tham chiếu. Các phụ thuộc thường xuất hiện dưới những hình thức sau:

- Một Spring bean trong module này inject bean hoặc interface được cung cấp bởi module khác.
- Một module đăng ký listener cho application event được module khác công bố.
- Một thành phần sử dụng cấu hình hoặc type công khai thuộc module khác.

Ví dụ, **orders** sử dụng hợp đồng thanh toán của **payments**:

~~~java
package com.acme.shop.payments;

import java.math.BigDecimal;

public interface PaymentProcessing {

    boolean charge(String orderId, BigDecimal amount);
}
~~~

Trong module **orders**, một application service sử dụng hợp đồng này qua constructor injection:

~~~java
package com.acme.shop.orders.internal;

import com.acme.shop.payments.PaymentProcessing;
import java.math.BigDecimal;
import org.springframework.stereotype.Service;

@Service
class PlaceOrderService {

    private final PaymentProcessing paymentProcessing;

    PlaceOrderService(PaymentProcessing paymentProcessing) {
        this.paymentProcessing = paymentProcessing;
    }

    void placeOrder(String orderId, BigDecimal total) {
        paymentProcessing.charge(orderId, total);
    }
}
~~~

Từ góc nhìn **orders**, **payments** là outgoing dependency. **orders** cần hợp đồng **PaymentProcessing** để hoàn tất use case đặt hàng.

Outgoing dependency giúp trả lời các câu hỏi:

- Module cần những module nào để thực hiện nghiệp vụ?
- Một thay đổi ở module cung cấp có thể ảnh hưởng đến module hiện tại ở đâu?
- Module có đang phụ thuộc quá nhiều module khác hay không?
- Có thể thay một phụ thuộc trực tiếp bằng application event hoặc một hợp đồng ổn định hơn không?

### Phụ thuộc trực tiếp và phụ thuộc bắc cầu

Giả sử có chuỗi:

~~~text
web ─────> orders ─────> payments ─────> accounting
~~~

Nếu **orders** chỉ tham chiếu **payments**, thì **payments** là outgoing dependency trực tiếp của **orders**. **accounting** là phụ thuộc bắc cầu: **orders** có thể chịu ảnh hưởng gián tiếp khi thay đổi ở đó, nhưng không có nghĩa mã nguồn **orders** được phép import type từ **accounting**.

Phân biệt hai loại:

- **Direct dependency**: module hiện tại tham chiếu trực tiếp type hoặc hợp đồng của module khác.
- **Transitive dependency**: module khác xuất hiện trong chuỗi phụ thuộc thông qua một hoặc nhiều module trung gian.

Khi thiết kế API, nên ưu tiên phụ thuộc trực tiếp vào hợp đồng mà module cần. Không nên import type của một module bắc cầu chỉ vì nó tình cờ xuất hiện trên classpath hoặc được một module trung gian sử dụng.

## 3. Incoming dependency: ai đang sử dụng module của tôi?

Incoming dependency cho biết các module tiêu thụ API mà module hiện tại công bố. Đây là góc nhìn quan trọng khi thay đổi hoặc loại bỏ một API.

Ví dụ:

~~~text
inventory ─────┐
               ├────> orders
shipping ──────┤
               │
reporting ─────┘
~~~

**orders** có ba incoming dependencies trong ví dụ: **inventory**, **shipping** và **reporting**. Các module đó có thể gọi API **OrderManagement**, đọc type được công bố hoặc lắng nghe event thuộc hợp đồng của **orders**.

Incoming dependency giúp trả lời:

- Những module nào sẽ bị ảnh hưởng nếu đổi chữ ký API?
- Có thể đổi hoặc xóa một type công khai mà không phải sửa consumer nào?
- Module hiện tại đang là điểm dùng chung của quá nhiều module khác hay không?
- Một Named Interface có thể được thu hẹp hoặc tách phiên bản không?

Incoming dependency càng nhiều thì một thay đổi không tương thích ở API càng có phạm vi ảnh hưởng rộng. Điều đó không tự động có nghĩa thiết kế sai: một module nền tảng có thể được nhiều module sử dụng. Tuy nhiên, module cung cấp cần quản lý hợp đồng ổn định và có chiến lược thay đổi phù hợp.

## 4. Hai hướng phụ thuộc không phải hai luồng xử lý nghiệp vụ

Đặc biệt chú ý khi module giao tiếp qua application event.

Giả sử **orders** phát event **OrderPlaced** và **inventory** lắng nghe event đó:

~~~text
Luồng sự kiện lúc chạy:
orders ────── OrderPlaced ──────> inventory

Hướng phụ thuộc type:
inventory ──────────────────────> orders
~~~

Luồng sự kiện lúc chạy đi từ publisher đến listener. Nhưng module **inventory** cần tham chiếu type **OrderPlaced** do **orders** sở hữu, nên xét theo phụ thuộc mã nguồn, **inventory** có outgoing dependency đến **orders**; **orders** có incoming dependency từ **inventory**.

Vì thế, không nên đọc mũi tên trong sơ đồ event flow như mũi tên của dependency graph. Hai sơ đồ mô tả hai góc nhìn khác nhau:

- Event flow: ai phát sự kiện và ai nhận sự kiện.
- Dependency graph: mã nguồn module nào cần type hoặc hợp đồng do module nào cung cấp.

Event giúp giảm phụ thuộc trực tiếp vào service triển khai, nhưng consumer vẫn phụ thuộc vào hợp đồng event được công bố. Để tránh phụ thuộc vào package nội bộ, event type cần nằm trong API package hoặc Named Interface thích hợp.

## 5. Xem outgoing dependency bằng ApplicationModules

Spring Modulith cung cấp mô hình **ApplicationModules** và **ApplicationModule** để phân tích quan hệ giữa các module. Bắt đầu bằng class ứng dụng Spring Boot:

~~~java
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
~~~

Lấy module cần phân tích:

~~~java
var orders = modules.getModuleByName("orders")
    .orElseThrow(() -> new IllegalStateException("Không tìm thấy module orders"));
~~~

Dùng **getDirectDependencies(modules)** để lấy các outgoing dependency trực tiếp:

~~~java
var outgoing = orders.getDirectDependencies(modules);

boolean dependsOnPayments = outgoing.containsModuleNamed("payments");
~~~

**ApplicationModuleDependencies** biểu diễn các phụ thuộc thực tế của module hiện tại tới những module khác. Có thể duyệt các module liên quan bằng **uniqueModules()**:

~~~java
orders.getDirectDependencies(modules)
    .uniqueModules()
    .forEach(module -> System.out.println(module.getDisplayName()));
~~~

Nếu cần tính cả phụ thuộc bắc cầu, dùng **getAllDependencies(modules)**:

~~~java
var allOutgoing = orders.getAllDependencies(modules);
~~~

Khi phân tích, cần phân biệt kết quả trực tiếp và bắc cầu. Một module xuất hiện trong **getAllDependencies()** không nhất thiết được mã nguồn module hiện tại tham chiếu trực tiếp.

## 6. Tìm incoming dependency từ mô hình module

**ApplicationModule** cung cấp API để lấy outgoing dependencies của chính module đó. Để tìm incoming dependency của một module, có thể duyệt toàn bộ mô hình và tìm các module có direct dependencies chứa module đang xét.

Ví dụ tìm các module phụ thuộc trực tiếp vào **orders**:

~~~java
import java.util.List;
import java.util.stream.Collectors;

import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

ApplicationModule orders = modules.getModuleByName("orders")
    .orElseThrow();

List<ApplicationModule> incoming = modules.stream()
    .filter(candidate -> !candidate.equals(orders))
    .filter(candidate ->
        candidate.getDirectDependencies(modules).contains(orders))
    .collect(Collectors.toList());

incoming.forEach(module -> System.out.println(module.getDisplayName()));
~~~

Đoạn mã này đảo góc nhìn của dependency graph: với mỗi module ứng viên, nó kiểm tra xem outgoing dependency trực tiếp của module đó có chứa **orders** hay không. Nếu có, module ứng viên là một incoming dependent của **orders**.

Muốn tìm cả các module phụ thuộc bắc cầu vào **orders**, thay **getDirectDependencies(modules)** bằng **getAllDependencies(modules)**. Khi đánh giá phạm vi ảnh hưởng của một thay đổi API, hãy xem riêng consumer trực tiếp và consumer bắc cầu để không nhầm quan hệ gọi trực tiếp với ảnh hưởng gián tiếp.

## 7. allowedDependencies kiểm soát outgoing dependency

**@ApplicationModule(allowedDependencies = ...)** được khai báo ở module tiêu thụ. Vì nó mô tả module hiện tại được phép phụ thuộc vào đâu, nên đây là cách giới hạn **outgoing dependencies**.

Ví dụ, **orders** chỉ được phép sử dụng API mặc định của **payments** và Named Interface **events** của **customers**:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {
        "payments",
        "customers :: events"
    }
)
package com.acme.shop.orders;
~~~

Nếu một class trong **orders** tham chiếu type của **inventory** mà **inventory** không có trong danh sách cho phép, kiểm chứng kiến trúc sẽ báo vi phạm.

Một vài cách khai báo:

| Giá trị | Ý nghĩa đối với outgoing dependency của module khai báo |
|---|---|
| **"payments"** | Cho phép API package mặc định của **payments** |
| **"customers :: events"** | Cho phép Named Interface **events** của **customers** |
| **"customers :: &#42;"** | Cho phép mọi Named Interface đã khai báo của **customers** |
| **"customers :: &#42;&#42;"** | Cho phép API package mặc định và mọi Named Interface của **customers** |

Khai báo **allowedDependencies** không điều khiển incoming dependency của module cung cấp. Module cung cấp quản lý bề mặt API của mình bằng API package và Named Interface; module tiêu thụ quản lý outgoing dependency của mình bằng danh sách cho phép.

## 8. Đọc hai hướng khi thay đổi API

Hãy xét module **orders** đang cung cấp **OrderManagement** cho **inventory**, **shipping** và **reporting**, đồng thời phụ thuộc vào **payments**.

~~~text
inventory ──────┐
shipping ───────┼────> orders ─────> payments
reporting ──────┘

Incoming của orders: inventory, shipping, reporting
Outgoing của orders: payments
~~~

Nếu thay đổi chữ ký **OrderManagement.placeOrder(…)**, cần xem incoming dependencies vì các module đang sử dụng hợp đồng này có thể phải cập nhật. Nếu thay đổi interface **PaymentProcessing** mà **orders** sử dụng, cần xem outgoing dependency và vị trí gọi bên trong **orders**.

| Thay đổi | Hướng cần xem trước | Lý do |
|---|---|---|
| Đổi hoặc xóa method API công khai | Incoming | Consumer đang gọi method có thể bị ảnh hưởng |
| Đổi type trong Named Interface | Incoming | Các module được phép sử dụng interface đó có thể đang tham chiếu type |
| Đổi API của module mà mình gọi | Outgoing | Module hiện tại là consumer của API đó |
| Thêm một module phụ thuộc mới | Outgoing | Tăng số yêu cầu và mức kết nối của module |
| Tách một module đang được nhiều nơi sử dụng | Cả hai | Cần xem module phụ thuộc vào ai và ai phụ thuộc vào nó |

Khi một module có nhiều incoming dependencies, ưu tiên thay đổi tương thích ngược hoặc lên kế hoạch chuyển đổi consumer theo từng bước. Khi module có nhiều outgoing dependencies, xem xét liệu nó đang đảm nhận quá nhiều trách nhiệm hoặc có thể giao tiếp qua event hay một API nhỏ hơn.

## 9. Dùng verify() để bảo vệ đồ thị phụ thuộc

Tạo bài test kiến trúc để kiểm tra toàn bộ module:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Việc kiểm chứng bao gồm các quy tắc quan trọng:

1. Không có chu trình ở cấp Application Module; đồ thị phụ thuộc phải có hướng và không có chu trình.
2. Module chỉ truy cập type của module khác qua API package được công bố; truy cập package nội bộ bị từ chối theo quy tắc module đóng.
3. Nếu khai báo **allowedDependencies**, các outgoing dependencies thực tế phải nằm trong danh sách cho phép.

**verify()** kiểm tra các vi phạm kiến trúc, nhưng không tự quyết định một API có thiết kế tốt hay một incoming dependency có quá nhiều hay không. Việc đánh giá mức độ kết nối và tác động thay đổi vẫn cần dựa vào mô hình nghiệp vụ và mục tiêu thiết kế.

## 10. Quy trình phân tích dependency khi review

Khi review một module, hãy thực hiện theo thứ tự:

1. Xác định module đang xét và các API mà nó cung cấp.
2. Liệt kê outgoing dependencies trực tiếp để biết module cần những hợp đồng nào.
3. Liệt kê incoming dependents để biết module nào đang sử dụng API của nó.
4. Phân biệt dependency trực tiếp với dependency bắc cầu.
5. Kiểm tra event flow riêng với hướng phụ thuộc mã nguồn.
6. Đối chiếu outgoing dependencies với **allowedDependencies** nếu module khai báo danh sách này.
7. Chạy **ApplicationModules.verify()** để phát hiện truy cập nội bộ, phụ thuộc ngoài danh sách và chu trình.

Một module có ranh giới rõ thường công bố một tập hợp hợp đồng có chủ đích, giữ phần triển khai nội bộ và chỉ phụ thuộc vào những API cần thiết. Incoming dependencies cho biết trách nhiệm tương thích mà module cung cấp cần quan tâm; outgoing dependencies cho biết những yêu cầu mà module tiêu thụ phải quản lý. Đọc cả hai hướng giúp đội ngũ đánh giá được mức độ kết nối và tác động của mỗi thay đổi trong modular monolith.

## Tài liệu tham khảo

- [Spring Modulith Reference — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html): provided interface, required interface, Named Interface và allowedDependencies.
- [Spring Modulith Reference — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): các quy tắc kiểm chứng đồ thị phụ thuộc.
- [Javadoc — ApplicationModule](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModule.html): getDirectDependencies() và getAllDependencies().
- [Javadoc — ApplicationModuleDependencies](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDependencies.html): cách truy vấn các module nằm trong tập hợp phụ thuộc.

# Module boundary và thay đổi implementation

Java Platform Module System (JPMS) giúp một ứng dụng xác định rõ package nào là API công khai và package nào thuộc phần triển khai nội bộ. Ranh giới này tạo điều kiện để nhóm phát triển thay đổi thuật toán, cấu trúc class hoặc cách lưu trữ bên trong mà không buộc mọi module sử dụng phải thay đổi theo.

Muốn thay implementation an toàn, trước hết cần thiết kế một **contract ổn định ở module boundary**. Consumer chỉ phụ thuộc vào kiểu và hành vi được công khai; implementation cụ thể nằm trong package không export. Khi thay đổi bên trong, cần giữ tương thích với contract đó.

## 1. Module boundary bảo vệ điều gì?

Một module có thể chứa nhiều package. Trong file module descriptor (module-info.java), khai báo exports xác định package nào được module khác sử dụng như API Java thông thường.

Ví dụ:

~~~java
module com.example.orders {
    exports com.example.orders.api;
}
~~~

Trong module này:

- Package com.example.orders.api là bề mặt API được công khai.
- Các package khác, chẳng hạn com.example.orders.internal, không được export và được giữ bên trong module.
- Class public trong package không export vẫn có thể được sử dụng bởi code thuộc cùng module, nhưng module khác không thể truy cập nó như một API thông thường.

Module boundary ở cấp module rộng hơn access modifier của từng class. Modifier public cho biết class/member có thể được truy cập theo quy tắc Java; exports quyết định package có được công khai qua ranh giới module hay không.

Cần phân biệt:

| Cơ chế | Phạm vi và ý nghĩa |
| --- | --- |
| private | Chỉ truy cập bên trong class khai báo |
| package-private | Truy cập trong cùng package |
| protected | Truy cập theo quy tắc package và kế thừa |
| public | Công khai theo quy tắc truy cập Java |
| exports | Cho phép module khác truy cập public API trong package được export |
| opens | Cho phép deep reflection vào package theo quy tắc JPMS |

Một package không export không trở thành API công khai chỉ vì bên trong có class public.

## 2. Tách API khỏi implementation

Giả sử module orders cung cấp chức năng tạo đơn hàng. Consumer chỉ cần biết cách gọi dịch vụ và nhận kết quả. Consumer không cần biết implementation đang dùng database nào, thuật toán tính giá ra sao hoặc class nào thực hiện công việc.

Cấu trúc gợi ý:

~~~text
com.example.orders/
├── module-info.java
├── com/example/orders/api/
│   ├── OrderRequest.java
│   ├── OrderResult.java
│   ├── OrderService.java
│   └── OrderServices.java
└── com/example/orders/internal/
    └── DefaultOrderService.java
~~~

Module descriptor chỉ export package API:

~~~java
module com.example.orders {
    exports com.example.orders.api;
}
~~~

### API contract

OrderRequest và OrderResult là các kiểu dữ liệu mà consumer được phép sử dụng:

~~~java
package com.example.orders.api;

public record OrderRequest(String productId, int quantity) {
}
~~~

~~~java
package com.example.orders.api;

public record OrderResult(String orderId, boolean accepted) {
}
~~~

Interface mô tả hành vi:

~~~java
package com.example.orders.api;

public interface OrderService {
    OrderResult place(OrderRequest request);
}
~~~

Factory tạo implementation và chỉ trả về interface:

~~~java
package com.example.orders.api;

import com.example.orders.internal.DefaultOrderService;

public final class OrderServices {

    private OrderServices() {
    }

    public static OrderService create() {
        return new DefaultOrderService();
    }
}
~~~

### Implementation nội bộ

Class triển khai nằm trong package không export:

~~~java
package com.example.orders.internal;

import com.example.orders.api.OrderRequest;
import com.example.orders.api.OrderResult;
import com.example.orders.api.OrderService;
import java.util.UUID;

public final class DefaultOrderService implements OrderService {

    @Override
    public OrderResult place(OrderRequest request) {
        if (request.quantity() <= 0) {
            return new OrderResult(null, false);
        }

        String orderId = UUID.randomUUID().toString();
        return new OrderResult(orderId, true);
    }
}
~~~

Class DefaultOrderService có thể là public để factory ở package khác trong cùng module tạo instance. Package internal không được export nên consumer bên ngoài không thể phụ thuộc trực tiếp vào class này.

### Consumer sử dụng API

Module sử dụng chỉ cần khai báo dependency tới module orders:

~~~java
module com.example.shop {
    requires com.example.orders;
}
~~~

Code consumer:

~~~java
import com.example.orders.api.OrderRequest;
import com.example.orders.api.OrderResult;
import com.example.orders.api.OrderService;
import com.example.orders.api.OrderServices;

public class Checkout {

    public OrderResult submit(String productId, int quantity) {
        OrderService service = OrderServices.create();
        return service.place(new OrderRequest(productId, quantity));
    }
}
~~~

Consumer biết interface, request và result. Consumer không cần import DefaultOrderService hoặc biết package internal tồn tại.

## 3. Thay implementation mà không đổi consumer

Khi contract đã được tách rõ, module có thể thay class triển khai mà không thay đổi API.

Ví dụ, phiên bản đầu dùng:

~~~java
public OrderService create() {
    return new DefaultOrderService();
}
~~~

Phiên bản sau chuyển sang:

~~~java
public OrderService create() {
    return new OptimizedOrderService();
}
~~~

OptimizedOrderService cũng nằm trong package nội bộ và implement OrderService. Nếu chữ ký API và hành vi được cam kết vẫn tương thích, consumer tiếp tục gọi OrderServices.create() như trước.

Những thay đổi thường có thể thực hiện bên trong module:

- Thay thuật toán xử lý hoặc cấu trúc dữ liệu.
- Thêm cache, batching hoặc tối ưu truy vấn.
- Chia một implementation lớn thành nhiều class nội bộ.
- Thay thư viện nội bộ hoặc cách kết nối hạ tầng.
- Đổi tên, di chuyển hoặc xóa class trong package không export.
- Thêm package nội bộ để tổ chức code.
- Thay implementation mặc định trong factory.

Đây là lợi ích chính của encapsulation ở cấp module: consumer phụ thuộc vào contract, không phụ thuộc vào chi tiết triển khai.

Tuy nhiên, giữ nguyên chữ ký method chưa đủ để bảo đảm tương thích. Implementation mới còn phải tôn trọng ý nghĩa của contract: kết quả, điều kiện lỗi, quy tắc validate, tính nhất quán dữ liệu, thread-safety và các cam kết về thứ tự xử lý nếu API đã công bố.

## 4. Những thay đổi có thể phá vỡ API contract

Khi thay đổi package được export, cần đánh giá tác động tới cả source compatibility, binary compatibility và behavioral compatibility.

| Thay đổi | Tác động có thể xảy ra |
| --- | --- |
| Xóa public class hoặc public method đã công khai | Consumer có thể không biên dịch hoặc gặp lỗi liên kết lúc chạy |
| Đổi tên package được export | Consumer phải sửa import và module descriptor |
| Đổi kiểu tham số hoặc kiểu trả về | Chữ ký method thay đổi; mã đã biên dịch có thể không liên kết được |
| Đổi method instance thành static hoặc ngược lại | Cách gọi và binary contract thay đổi |
| Thay đổi interface mà consumer implement | Có thể làm implementation của consumer không còn tương thích |
| Xóa một package khỏi exports | Consumer ở module khác mất quyền truy cập package |
| Thay đổi ý nghĩa kết quả hoặc điều kiện lỗi | Có thể phá behavioral compatibility dù chữ ký không đổi |
| Thay đổi class nội bộ không được export | Thường không ảnh hưởng trực tiếp tới consumer tuân thủ module boundary |

Một trường hợp cần chú ý là thêm abstract method vào interface công khai. Consumer có thể đang cung cấp implementation riêng của interface đó. Khi interface thêm abstract method, implementation cũ có thể không còn đáp ứng contract mới. Nếu phù hợp về ngữ nghĩa, có thể cân nhắc default method hoặc tạo interface mở rộng riêng để biểu diễn capability mới.

Không nên đưa class implementation nội bộ vào chữ ký API. Ví dụ:

~~~java
// Không nên: làm lộ implementation type trong public contract.
public DefaultOrderService create();
~~~

Hãy trả về interface hoặc abstraction được công khai:

~~~java
// Tốt hơn: consumer chỉ phụ thuộc contract.
public OrderService create();
~~~

Nếu một public method trả về kiểu nằm trong package không export, consumer có thể gặp khó khăn khi biên dịch và sử dụng kết quả. Kiểu dữ liệu xuất hiện trong chữ ký API cũng là một phần của ranh giới công khai.

## 5. Exports, qualified exports và opens trong thiết kế boundary

Khai báo export không tham chiếu đến module cụ thể sẽ công khai package cho mọi module đọc được module này:

~~~java
module com.example.orders {
    exports com.example.orders.api;
}
~~~

Nếu package chỉ được phép sử dụng bởi một số module cụ thể, JPMS hỗ trợ qualified exports:

~~~java
module com.example.orders {
    exports com.example.orders.api;
    exports com.example.orders.integration
        to com.example.reporting;
}
~~~

Cách này có thể hữu ích khi cần một API tích hợp dành riêng cho module khác. Tuy nhiên, qualified export tạo ra quan hệ phụ thuộc rõ ràng giữa hai module. Nếu dùng quá rộng, nó có thể làm giảm khả năng thay đổi độc lập.

opens có mục đích khác:

~~~java
module com.example.orders {
    exports com.example.orders.api;

    opens com.example.orders.model
        to com.example.json;
}
~~~

Package model được mở cho module com.example.json để framework có thể thực hiện deep reflection. Package này không vì thế trở thành API Java thông thường.

Một open module mở tất cả package cho deep reflection theo quy tắc JPMS:

~~~java
open module com.example.legacy {
}
~~~

Đây là phạm vi rộng và làm giảm mức encapsulation. Với thiết kế module mới, nên cân nhắc mở đúng package và đúng module cần truy cập.

## 6. Giữ implementation có thể thay đổi trong dài hạn

Một số nguyên tắc giúp module dễ phát triển:

**Công khai abstraction thay vì class cụ thể.** Consumer nên phụ thuộc interface, record hoặc kiểu dữ liệu thuộc API package. Factory hoặc constructor công khai chịu trách nhiệm cung cấp implementation phù hợp.

**Giữ kiểu nội bộ ngoài chữ ký API.** Không để method public trả về hoặc nhận các kiểu chỉ tồn tại trong package internal. Nếu dữ liệu cần được trao đổi qua boundary, hãy định nghĩa kiểu hợp đồng trong package API.

**Giữ contract có ý nghĩa rõ ràng.** Mô tả nullability, exception, validation, trạng thái, thread-safety và các điều kiện vận hành mà consumer được phép dựa vào. Implementation mới phải duy trì các cam kết này.

**Tách capability tùy chọn.** Nếu một số implementation có chức năng bổ sung, cân nhắc interface mở rộng hoặc capability riêng thay vì liên tục thêm method bắt buộc vào interface gốc.

**Ẩn lựa chọn triển khai.** Để factory, dependency injection hoặc service discovery quyết định implementation. Consumer không nên tự khởi tạo class internal.

**Giới hạn package export.** Chỉ export những package mà module thực sự cam kết hỗ trợ như API. Không export toàn bộ package chỉ để làm cho một consumer truy cập được class nội bộ.

**Quản lý deprecation có lộ trình.** Khi API cũ cần thay thế, có thể đánh dấu deprecated, cung cấp API mới, tài liệu migration và một giai đoạn tương thích trước khi loại bỏ ở phiên bản major phù hợp.

## 7. Khi cần nhiều implementation: dùng ServiceLoader

Factory nội bộ phù hợp khi một module tự quyết định implementation. Nếu cần cho module khác cung cấp plugin, có thể thiết kế một service interface công khai và sử dụng ServiceLoader.

Module chứa service API khai báo:

~~~java
module com.example.payment.api {
    exports com.example.payment.api;
}
~~~

Service contract:

~~~java
package com.example.payment.api;

public interface PaymentProcessor {
    boolean supports(String method);
    void process(String paymentId);
}
~~~

Module provider phụ thuộc vào API và đăng ký implementation:

~~~java
module com.example.payment.card {
    requires com.example.payment.api;

    provides com.example.payment.api.PaymentProcessor
        with com.example.payment.card.CardPaymentProcessor;
}
~~~

Class provider có thể nằm trong package không export:

~~~java
package com.example.payment.card;

import com.example.payment.api.PaymentProcessor;

public final class CardPaymentProcessor
        implements PaymentProcessor {

    public boolean supports(String method) {
        return "CARD".equals(method);
    }

    public void process(String paymentId) {
        System.out.println("Processing card payment: " + paymentId);
    }
}
~~~

Module consumer khai báo sử dụng service:

~~~java
module com.example.checkout {
    requires com.example.payment.api;

    uses com.example.payment.api.PaymentProcessor;
}
~~~

Consumer tìm implementation:

~~~java
import com.example.payment.api.PaymentProcessor;
import java.util.ServiceLoader;

ServiceLoader.load(PaymentProcessor.class)
    .stream()
    .map(ServiceLoader.Provider::get)
    .filter(processor -> processor.supports("CARD"))
    .forEach(processor -> processor.process("PAY-001"));
~~~

ServiceLoader giúp consumer phụ thuộc vào service contract thay vì phụ thuộc trực tiếp vào module provider. Provider cần được đưa vào module resolution và service binding phù hợp để runtime tìm thấy. Với named module, các khai báo uses và provides thể hiện quan hệ này trong module descriptor.

Cách thiết kế này hữu ích cho plugin architecture, nhiều adapter hoặc các implementation được lựa chọn theo môi trường triển khai.

## 8. Kiểm tra module boundary khi thay đổi

Khi refactor implementation hoặc thay đổi module descriptor, nên kiểm tra các điểm sau:

1. Liệt kê package được export trong module-info.java.
2. Xác nhận public API chỉ tham chiếu các kiểu thuộc package được công khai hoặc các module dependency phù hợp.
3. Xác nhận package nội bộ không vô tình được export.
4. Kiểm tra module consumer vẫn biên dịch và gọi API như trước.
5. Kiểm tra các module provider hoặc service implementation nếu có.
6. Chạy kiểm thử contract để so sánh kết quả và hành vi của implementation mới.
7. Kiểm tra tương thích nhị phân khi thay module đã được consumer biên dịch trước đó.
8. Kiểm tra opens và qualified exports để bảo đảm quyền truy cập chỉ được cấp theo mục đích thiết kế.

Có thể dùng công cụ JDK để hỗ trợ phân tích:

~~~shell
# Xem dependency và package được sử dụng trong JAR
jdeps --module-path mods --module com.example.orders

# Phân tích dependency theo module
jdeps --module-path mods --print-module-deps app.jar

# Xem descriptor của một module JAR
jar --describe-module --file mods/com.example.orders.jar
~~~

jdeps giúp phát hiện dependency và hỗ trợ đánh giá module migration. Nó không thay thế kiểm thử behavioral contract hoặc kiểm tra tương thích API.

## 9. Ví dụ tư duy trước và sau khi thay implementation

Giả sử phiên bản đầu có:

~~~text
com.example.orders
├── api
│   ├── OrderService
│   └── OrderServices
└── internal
    └── DefaultOrderService
~~~

Consumer chỉ gọi:

~~~java
OrderService service = OrderServices.create();
service.place(request);
~~~

Ở phiên bản sau, nhóm phát triển cần thay đổi cách xử lý:

~~~text
com.example.orders
├── api
│   ├── OrderService
│   └── OrderServices
└── internal
    ├── OptimizedOrderService
    ├── OrderValidator
    ├── PricingEngine
    └── OrderRepositoryAdapter
~~~

Nếu module descriptor và contract API vẫn tương thích, consumer tiếp tục sử dụng cùng cách gọi. Các class nội bộ có thể được thêm, xóa hoặc tổ chức lại theo nhu cầu triển khai.

Ngược lại, nếu consumer trực tiếp khởi tạo DefaultOrderService, import package internal hoặc gọi method chỉ có trên implementation cụ thể, consumer đã phụ thuộc vào chi tiết triển khai. Khi thay class, module orders sẽ phải giữ lại compatibility adapter hoặc yêu cầu consumer sửa mã.

Đó là lý do cần giữ boundary rõ ràng ngay từ đầu, thay vì chỉ dựa vào quy ước đặt tên như Internal, Default hoặc Impl.

## Kết luận

Module boundary xác định phần nào là contract được công khai và phần nào thuộc implementation nội bộ. Khi consumer chỉ phụ thuộc vào API package, module có thể thay thuật toán, class, thư viện và cấu trúc nội bộ mà không buộc consumer thay đổi. Muốn duy trì khả năng đó, cần quản lý exports, giữ kiểu nội bộ ngoài chữ ký API, duy trì behavioral contract và kiểm tra tương thích khi phát hành phiên bản mới.

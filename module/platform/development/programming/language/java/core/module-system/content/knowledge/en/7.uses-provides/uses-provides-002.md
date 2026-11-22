# provides ... with khai báo service provider

## 1. Vai trò của provides trong JPMS

JPMS hỗ trợ cơ chế Service Provider Interface (SPI) để một module công bố implementation cho một service mà module khác định nghĩa. Cơ chế này giúp module tiêu thụ phụ thuộc vào abstraction, trong khi implementation có thể được thay thế hoặc bổ sung mà consumer không cần biết tên lớp triển khai cụ thể.

Một service thường gồm ba phần:

- **Service API**: định nghĩa interface hoặc abstract class mà ứng dụng muốn sử dụng.
- **Provider module**: chứa implementation và khai báo module đó cung cấp service bằng chỉ thị `provides ... with ...`.
- **Consumer module**: sử dụng service và khai báo nhu cầu bằng chỉ thị `uses`.

Ví dụ, ứng dụng thanh toán chỉ cần biết `PaymentProcessor`. Một module khác có thể cung cấp xử lý thẻ, module khác cung cấp xử lý chuyển khoản. Consumer không cần import hoặc gọi constructor của từng implementation.

Chỉ thị `provides` nằm trong `module-info.java` của module cung cấp service. Cú pháp tổng quát:

~~~java
provides service.type with provider.type;
~~~

Có thể khai báo nhiều provider cho cùng một service:

~~~java
provides com.acme.payment.api.PaymentProcessor
    with com.acme.payment.card.CardPaymentProcessor,
         com.acme.payment.bank.BankPaymentProcessor;
~~~

Tên service và provider thường được ghi đầy đủ theo package. Mỗi provider phải đáp ứng quy tắc của JPMS về constructor hoặc provider method.

## 2. Tách service API khỏi implementation

Một cấu trúc module dễ bảo trì thường tách API và provider:

~~~text
payment-api/
  module-info.java
  com/acme/payment/api/PaymentProcessor.java

payment-card/
  module-info.java
  com/acme/payment/card/CardPaymentProcessor.java

checkout-app/
  module-info.java
  com/acme/checkout/Main.java
~~~

Module API công bố package chứa service type:

~~~java
module com.acme.payment.api {
    exports com.acme.payment.api;
}
~~~

Service interface:

~~~java
package com.acme.payment.api;

public interface PaymentProcessor {
    String process(String orderId, long amount);
}
~~~

Package API phải được export để provider module và consumer module có thể tham chiếu kiểu `PaymentProcessor`. Việc export service API không yêu cầu phải export package chứa implementation.

## 3. Khai báo provider bằng provides ... with

Provider module đọc module API và khai báo implementation:

~~~java
module com.acme.payment.card {
    requires com.acme.payment.api;

    provides com.acme.payment.api.PaymentProcessor
        with com.acme.payment.card.CardPaymentProcessor;
}
~~~

Implementation:

~~~java
package com.acme.payment.card;

import com.acme.payment.api.PaymentProcessor;

public final class CardPaymentProcessor implements PaymentProcessor {

    public CardPaymentProcessor() {
    }

    @Override
    public String process(String orderId, long amount) {
        return "Card payment for " + orderId + ": " + amount;
    }
}
~~~

Trong ví dụ này:

- `requires com.acme.payment.api` tạo quan hệ readability để provider dùng service type.
- `provides PaymentProcessor with CardPaymentProcessor` đăng ký provider với module system.
- Provider class triển khai interface `PaymentProcessor`.
- Provider có public no-argument constructor để `ServiceLoader` tạo instance.
- Package `com.acme.payment.card` không cần export chỉ để `ServiceLoader` tìm và tạo provider.

Điểm cuối rất quan trọng: consumer phụ thuộc vào service API, không phụ thuộc trực tiếp vào package triển khai. Provider implementation có thể nằm trong package nội bộ và được giữ kín.

## 4. Hai cách tạo provider instance

Provider class được khai báo sau từ khóa `with` có thể dùng một trong hai cơ chế.

### Public no-argument constructor

Đây là cách thông dụng nhất. Provider class phải là public, triển khai service type và có public constructor không tham số:

~~~java
public final class CardPaymentProcessor implements PaymentProcessor {
    public CardPaymentProcessor() {
    }

    @Override
    public String process(String orderId, long amount) {
        return "Card: " + orderId;
    }
}
~~~

Khi `ServiceLoader` khởi tạo provider, nó gọi constructor này. Nếu constructor không tồn tại, không public hoặc ném lỗi trong lúc khởi tạo, quá trình tải provider có thể thất bại.

Cách này phù hợp khi implementation có thể được tạo trực tiếp mà không cần tham số cấu hình riêng.

### Public static provider() method

Nếu việc tạo service cần factory, cấu hình hoặc lựa chọn implementation, provider class có thể khai báo một public static method tên `provider`, không nhận tham số và trả về service type hoặc subtype của nó.

Descriptor:

~~~java
module com.acme.payment.card {
    requires com.acme.payment.api;

    provides com.acme.payment.api.PaymentProcessor
        with com.acme.payment.card.CardPaymentProvider;
}
~~~

Provider factory:

~~~java
package com.acme.payment.card;

import com.acme.payment.api.PaymentProcessor;

public final class CardPaymentProvider {

    private CardPaymentProvider() {
    }

    public static PaymentProcessor provider() {
        return new CardPaymentProcessor(loadConfiguration());
    }

    private static PaymentConfiguration loadConfiguration() {
        return PaymentConfiguration.fromEnvironment();
    }
}
~~~

Trong cách này, lớp `CardPaymentProvider` là provider class được ghi sau `with`; phương thức `provider()` trả về object thực hiện service. Provider class không nhất thiết phải tự triển khai `PaymentProcessor`. Nó phải public và có public static provider method với chữ ký phù hợp.

Factory method hữu ích khi implementation cần được khởi tạo thông qua một quy trình riêng. Nếu không cần factory, public no-argument constructor thường đơn giản hơn.

## 5. Consumer khai báo uses

Module tiêu thụ service cần khai báo `uses` trong module descriptor:

~~~java
module com.acme.checkout {
    requires com.acme.payment.api;
    uses com.acme.payment.api.PaymentProcessor;
}
~~~

Chỉ thị `uses` nói rằng module checkout cần tìm provider cho service `PaymentProcessor`. Consumer không cần khai báo:

~~~java
requires com.acme.payment.card;
~~~

nếu nó chỉ sử dụng service interface và không gọi trực tiếp implementation. Việc liên kết provider là trách nhiệm của module resolution và `ServiceLoader`.

Mã consumer:

~~~java
package com.acme.checkout;

import com.acme.payment.api.PaymentProcessor;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        ServiceLoader<PaymentProcessor> loader =
            ServiceLoader.load(PaymentProcessor.class);

        for (PaymentProcessor processor : loader) {
            System.out.println(
                processor.process("ORDER-100", 250_000)
            );
        }
    }
}
~~~

Trong một named module, nếu gọi `ServiceLoader.load(...)` mà không khai báo `uses` cho service tương ứng, việc tải service có thể thất bại với `ServiceConfigurationError`. Vì vậy, hãy khai báo `uses` ngay trong module consumer thay vì chỉ dựa vào việc service interface đã được import trong source.

## 6. Quan hệ giữa service API, provider và consumer

Sơ đồ phụ thuộc:

~~~text
                 requires
payment-card -----------------> payment-api
     |                              ^
     | provides                     | requires
     | PaymentProcessor             |
     v                              |
ServiceLoader <---------------- checkout-app
                                  uses PaymentProcessor
~~~

Có thể đọc sơ đồ theo ba quan hệ:

1. Provider module đọc service API vì implementation cần tham chiếu interface.
2. Consumer module cũng đọc service API vì mã ứng dụng gọi interface.
3. Provider module đăng ký implementation qua `provides`; consumer module khai báo nhu cầu qua `uses`.

`provides` không tạo một API import trực tiếp cho consumer. Nó cũng không buộc consumer khai báo `requires` tới module provider. Khi module resolution thực hiện service binding, các provider phù hợp có thể được đưa vào cấu hình nếu chúng quan sát được trên module path và service được sử dụng trong cấu hình.

Nếu ứng dụng tự tạo `ModuleLayer`, cần chú ý cách tạo `Configuration`. `Configuration.resolveAndBind(...)` thực hiện thêm bước liên kết service provider; `Configuration.resolve(...)` chỉ giải quyết các root dependency được yêu cầu. Khi muốn provider được tự động phát hiện trong layer riêng, hãy dùng quy trình resolve-and-bind phù hợp và tải service từ layer đó.

## 7. Một service có nhiều provider

Một module có thể cung cấp nhiều service khác nhau:

~~~java
module com.acme.platform.adapters {
    requires com.acme.payment.api;
    requires com.acme.notification.api;

    provides com.acme.payment.api.PaymentProcessor
        with com.acme.platform.adapters.CardPaymentProcessor;

    provides com.acme.notification.api.Notifier
        with com.acme.platform.adapters.EmailNotifier;
}
~~~

Một service cũng có thể có nhiều provider được liệt kê trong cùng một directive:

~~~java
provides com.acme.payment.api.PaymentProcessor
    with com.acme.platform.adapters.CardPaymentProcessor,
         com.acme.platform.adapters.BankTransferProcessor;
~~~

Consumer có thể duyệt tất cả provider được tìm thấy:

~~~java
ServiceLoader<PaymentProcessor> loader =
    ServiceLoader.load(PaymentProcessor.class);

loader.stream().forEach(provider ->
    System.out.println(provider.type().getName())
);
~~~

Không nên dùng thứ tự provider như một quy tắc ưu tiên nghiệp vụ nếu ứng dụng cần lựa chọn một implementation cụ thể. Nếu cần lựa chọn theo cấu hình, hãy đọc metadata hoặc cấu hình riêng rồi áp dụng chính sách lựa chọn rõ ràng trong ứng dụng.

Nếu provider cần tên, thứ tự hoặc thuộc tính cấu hình riêng, service API có thể cung cấp phương thức metadata, hoặc ứng dụng có thể quản lý registry riêng. Không nên suy luận hành vi từ thứ tự xuất hiện của JAR trên module path.

## 8. Lỗi thường gặp khi khai báo provides

### Service type không được đọc

Provider module phải đọc module sở hữu service type. Nếu thiếu:

~~~java
module com.acme.payment.card {
    provides com.acme.payment.api.PaymentProcessor
        with com.acme.payment.card.CardPaymentProcessor;
}
~~~

thì descriptor hoặc source provider có thể không được biên dịch đúng vì module chưa khai báo dependency. Thêm `requires com.acme.payment.api`.

### Provider class không đáp ứng quy tắc khởi tạo

Nếu dùng constructor, provider class cần public no-argument constructor. Nếu dùng provider method, method phải là public static, không tham số và trả về kiểu tương thích với service.

Các lỗi này có thể xuất hiện khi `ServiceLoader` duyệt hoặc khởi tạo provider. Hãy kiểm tra exception đầy đủ, bao gồm nguyên nhân bên trong, thay vì chỉ nhìn dòng đầu của `ServiceConfigurationError`.

### Consumer quên uses

Module consumer đã `requires` service API nhưng quên:

~~~java
uses com.acme.payment.api.PaymentProcessor;
~~~

Khi đó consumer có thể gặp `ServiceConfigurationError` khi sử dụng `ServiceLoader`. Thêm `uses` vào module descriptor của chính module gọi service.

### Provider module không được phân giải

Provider JAR có thể tồn tại trên đĩa nhưng không nằm trong module configuration/layer đang chạy. Kiểm tra module path, tên module, service binding và cách tạo layer. Đừng chỉ kiểm tra rằng file JAR có trong thư mục.

### Export nhầm implementation package

Không cần thêm:

~~~java
exports com.acme.payment.card;
~~~

chỉ để `ServiceLoader` tìm provider được khai báo bằng `provides`. Giữ package implementation không export nếu consumer không cần truy cập trực tiếp.

## 9. Kiểm tra descriptor và artifact

Sau khi build provider JAR, kiểm tra descriptor thực tế:

~~~bash
jar --describe-module --file build/libs/payment-card.jar
jar --list --file build/libs/payment-card.jar
~~~

Kết quả cần cho thấy module name, dependency tới service API, directive `provides` và provider class có trong archive.

Kiểm tra module resolution:

~~~bash
java --show-module-resolution \
  --module-path mods \
  -m com.acme.checkout/com.acme.checkout.Main
~~~

Chạy ứng dụng tiêu thụ với đúng các JAR phát hành. Kiểm tra rằng:

- Consumer có `uses` đúng service type.
- Provider module được phân giải và service binding tìm thấy provider.
- Provider được khởi tạo thành công.
- Mỗi provider thực hiện đúng hợp đồng service.
- Không có dependency chỉ tồn tại trong môi trường IDE nhưng thiếu trong module path phát hành.

Nếu dùng custom layer, tạo configuration bằng cơ chế service binding thích hợp và gọi `ServiceLoader.load(layer, PaymentProcessor.class)` cho layer đó.

## 10. Khi nào dùng provides và khi nào dùng META-INF/services?

Trong một explicit named module, khai báo provider bằng `provides ... with ...` trong `module-info.java`. Đây là cách module system đọc trực tiếp từ descriptor.

Với ứng dụng hoặc thư viện chạy trên classpath theo cơ chế truyền thống, ServiceLoader dùng file cấu hình:

~~~text
META-INF/services/com.acme.payment.api.PaymentProcessor
~~~

Nội dung file liệt kê tên đầy đủ của từng provider class, mỗi tên trên một dòng.

Hai cách phục vụ cùng mô hình SPI nhưng thuộc hai cơ chế đóng gói khác nhau. Khi chuyển JAR từ classpath sang explicit named module, hãy chuyển đăng ký provider sang `provides` và kiểm tra consumer `uses`. Không nên giả định chỉ thêm `module-info.java` là mọi cấu hình service cũ đã được chuyển đúng.

## 11. Checklist trước khi phát hành provider module

- [ ] Service interface nằm trong package được export từ module API.
- [ ] Provider module khai báo `requires` tới module API.
- [ ] `provides` dùng đúng service type và provider class.
- [ ] Provider class có public no-argument constructor hoặc public static `provider()` method hợp lệ.
- [ ] Consumer module khai báo `uses` cho service mà nó tải.
- [ ] Package implementation không export nếu không có nhu cầu API trực tiếp.
- [ ] Provider module có mặt trong module configuration hoặc service binding của layer.
- [ ] JAR phát hành chứa đúng `module-info.class` và provider class.
- [ ] ServiceLoader đã được thử trên module path thực tế và custom layer nếu có.
- [ ] Lỗi khởi tạo provider và lỗi cấu hình service được kiểm tra đầy đủ.

## Kết luận

`provides ... with` đăng ký provider ở phía module cung cấp; `uses` khai báo nhu cầu ở phía module tiêu thụ. Provider module đọc service API bằng `requires`, còn consumer thường chỉ cần đọc service API mà không cần phụ thuộc trực tiếp vào module implementation.

Để service hoạt động ổn định, hãy kiểm tra provider class hoặc provider method, service binding, module layer, artifact đóng gói và consumer thực tế. Khi giữ package implementation ở nội bộ và công bố đúng service API, các implementation có thể được thay thế hoặc bổ sung mà không làm consumer phụ thuộc vào lớp triển khai cụ thể.

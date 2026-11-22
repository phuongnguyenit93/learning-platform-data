# Giảm phụ thuộc bằng API nhỏ và boundary rõ

Trong Java Platform Module System (JPMS), module không chỉ gom các package thành một đơn vị triển khai. Module còn tạo ranh giới để kiểm soát dependency và phần API mà module công khai cho bên ngoài.

Một module được thiết kế tốt thường có hai đặc điểm:

- **API nhỏ:** chỉ công khai những kiểu và thao tác mà consumer thực sự cần.
- **Boundary rõ:** consumer phụ thuộc vào hợp đồng ổn định, còn chi tiết triển khai được giữ bên trong module.

Hai đặc điểm này giúp giảm coupling (mức độ phụ thuộc chặt), giới hạn phạm vi thay đổi và giữ module graph dễ hiểu khi hệ thống phát triển.

## 1. Coupling hình thành ở đâu?

Coupling xuất hiện khi một module biết quá nhiều về cấu trúc hoặc cách hoạt động của module khác. Ví dụ, module checkout có thể phụ thuộc trực tiếp vào:

- Lớp xử lý thanh toán cụ thể như `StripePaymentGateway`.
- Package nội bộ chứa repository, HTTP client hoặc cấu hình của provider.
- Kiểu dữ liệu của framework hoặc thư viện triển khai.
- Nhiều class chi tiết chỉ để gọi một chức năng đơn giản.

Khi implementation thay đổi, consumer có thể phải sửa và biên dịch lại dù nhu cầu nghiệp vụ không đổi. Nếu nhiều module cùng phụ thuộc vào những chi tiết đó, một thay đổi nhỏ có thể lan ra nhiều nơi.

JPMS hỗ trợ giảm coupling bằng cách kiểm soát hai quan hệ:

1. **Module dependency:** module nào khai báo `requires` module nào.
2. **Package accessibility:** package nào được công khai bằng `exports`, package nào được mở cho reflection bằng `opens`.

Dependency ở cấp module và API ở cấp package cần được thiết kế cùng nhau. Chỉ chia code thành nhiều module mà export quá nhiều package thì ranh giới vẫn yếu.

## 2. Chỉ export phần API cần thiết

Một module có thể chứa nhiều package nhưng chỉ export một số package nhất định. Package không được export vẫn thuộc module, nhưng module khác không thể sử dụng các kiểu của package đó theo truy cập Java thông thường.

Ví dụ:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
~~~

Cấu trúc package:

~~~text
com.acme.catalog/
├── module-info.java
└── com/acme/catalog/
    ├── api/
    │   ├── Product.java
    │   └── Catalog.java
    ├── internal/
    │   ├── JdbcCatalog.java
    │   └── ProductRowMapper.java
    └── config/
        └── DatabaseConfig.java
~~~

Consumer chỉ có thể sử dụng API trong `com.acme.catalog.api` nếu module đọc được `com.acme.catalog`. Các package `internal` và `config` không được export nên được giữ bên trong boundary của module.

Điều này tạo ra một hợp đồng rõ ràng:

- `api` là bề mặt mà module cam kết cho consumer sử dụng.
- `internal` là chi tiết triển khai có thể thay đổi mà không buộc consumer phụ thuộc vào nó.
- `config` chứa cách module tự cấu hình; consumer không cần biết cấu trúc nội bộ.

Không cần tạo một module riêng cho từng package. Boundary có thể nằm ngay trong một named module, với một vài package được export có chủ đích.

### API nhỏ có hình dạng như thế nào?

API nhỏ thường có:

- Ít kiểu public, tên và trách nhiệm rõ.
- Method thể hiện hành vi nghiệp vụ, không phơi bày các bước nội bộ.
- Kiểu dữ liệu đầu vào/đầu ra ổn định.
- Hợp đồng lỗi có thể hiểu và xử lý được.
- Không để lộ implementation class, persistence entity hoặc framework type nếu consumer không cần chúng.

Ví dụ, consumer chỉ cần lấy thông tin sản phẩm:

~~~java
package com.acme.catalog.api;

public interface Catalog {
    Product findById(String productId);
}
~~~

~~~java
package com.acme.catalog.api;

public record Product(String id, String name) {
}
~~~

Consumer làm việc với `Catalog` và `Product`. Nó không cần biết module đang dùng JDBC, JPA, file hay một remote service để tìm dữ liệu.

Nếu sau này `JdbcCatalog` được thay bằng `RemoteCatalog`, module có thể thay implementation mà vẫn giữ nguyên API.

## 3. Dùng requires cho dependency trực tiếp

Trong `module-info.java`, khai báo `requires` cho module mà code của module hiện tại thực sự sử dụng:

~~~java
module com.acme.checkout {
    requires com.acme.catalog;
}
~~~

Điều này nói rằng `com.acme.checkout` cần đọc module `com.acme.catalog` và dependency đó phải được giải quyết khi ứng dụng chạy theo quy tắc module system.

Một số nguyên tắc:

- Khai báo dependency trực tiếp, không dựa vào việc một module khác tình cờ kéo dependency vào graph.
- Không thêm `requires` chỉ vì module đó xuất hiện trên module path.
- Tránh phụ thuộc vào module triển khai nếu chỉ cần một API nhỏ.
- Không tạo vòng phụ thuộc giữa các named module; thiết kế graph theo các lớp trách nhiệm có hướng rõ ràng.

Ví dụ một graph dễ hiểu:

~~~text
com.acme.checkout  ──requires──>  com.acme.catalog
        │
        └──────────requires──>  com.acme.payment.api
                                      ▲
                                      │ requires
                              com.acme.payment.provider
~~~

Trong mô hình này, checkout phụ thuộc vào hợp đồng thanh toán. Provider cũng phụ thuộc vào hợp đồng đó để triển khai. Checkout không cần biết provider cụ thể.

## 4. Không lạm dụng requires transitive

`requires transitive` làm cho dependency được truyền khả năng đọc tới các module đọc module hiện tại. Đây là công cụ hữu ích khi dependency là một phần của API public, nhưng nó mở rộng dependency graph của consumer.

So sánh:

~~~java
module com.acme.billing {
    requires com.acme.money;
    exports com.acme.billing.api;
}
~~~

và:

~~~java
module com.acme.billing {
    requires transitive com.acme.money;
    exports com.acme.billing.api;
}
~~~

Ở trường hợp đầu, module billing đọc module money. Consumer của billing không tự động đọc money; nếu consumer trực tiếp sử dụng kiểu thuộc money, nó phải khai báo dependency trực tiếp của mình.

Ở trường hợp thứ hai, consumer đọc billing cũng được phép đọc money. Điều này hợp lý khi kiểu của money xuất hiện trong public API của billing và consumer cần sử dụng kiểu đó.

Ví dụ API:

~~~java
package com.acme.billing.api;

import com.acme.money.Money;

public interface Invoice {
    Money total();
}
~~~

Vì `Money` xuất hiện trong chữ ký public của `Invoice`, consumer cần đọc module chứa `Money` để sử dụng đầy đủ API. Billing có thể khai báo `requires transitive com.acme.money` nếu muốn cam kết truyền khả năng đọc này cho consumer.

Nếu API chỉ trả về kiểu do billing sở hữu:

~~~java
package com.acme.billing.api;

public record InvoiceTotal(long amountInCents, String currency) {
}
~~~

thì billing có thể giữ `requires com.acme.money` thông thường cho phần triển khai nội bộ, hoặc thậm chí không cần phụ thuộc money nếu không sử dụng nó. Consumer chỉ cần biết kiểu `InvoiceTotal`.

Không nên dùng `transitive` để “sửa nhanh” lỗi compile. Trước tiên hãy xem kiểu của dependency có thực sự xuất hiện trong API công khai hay consumer có đang thiếu dependency trực tiếp của chính nó hay không.

## 5. Đảo chiều phụ thuộc bằng interface hoặc service API

Một cách giảm coupling hiệu quả là để module nghiệp vụ phụ thuộc vào abstraction nhỏ, còn implementation nằm ở module khác.

Ví dụ hệ thống checkout cần thực hiện thanh toán. Nếu checkout phụ thuộc trực tiếp vào provider cụ thể, thay đổi nhà cung cấp sẽ ảnh hưởng đến module nghiệp vụ.

Thay vào đó, định nghĩa một hợp đồng nhỏ trong module API:

~~~java
module com.acme.payment.api {
    exports com.acme.payment.api;
}
~~~

~~~java
package com.acme.payment.api;

public interface PaymentGateway {
    PaymentReceipt charge(PaymentCommand command);
}
~~~

~~~java
package com.acme.payment.api;

public record PaymentCommand(String orderId, long amountInCents) {
}
~~~

~~~java
package com.acme.payment.api;

public record PaymentReceipt(String transactionId) {
}
~~~

Module checkout sử dụng hợp đồng này:

~~~java
module com.acme.checkout {
    requires com.acme.payment.api;
    exports com.acme.checkout.api;
    uses com.acme.payment.api.PaymentGateway;
}
~~~

`uses` khai báo rằng module checkout cần tìm implementation của service `PaymentGateway`. Module checkout không phải khai báo dependency tới một provider cụ thể.

Module provider triển khai hợp đồng:

~~~java
module com.acme.payment.stripe {
    requires com.acme.payment.api;

    provides com.acme.payment.api.PaymentGateway
        with com.acme.payment.stripe.internal.StripePaymentGateway;
}
~~~

~~~java
package com.acme.payment.stripe.internal;

import com.acme.payment.api.PaymentCommand;
import com.acme.payment.api.PaymentGateway;
import com.acme.payment.api.PaymentReceipt;

public final class StripePaymentGateway implements PaymentGateway {
    public StripePaymentGateway() {
    }

    @Override
    public PaymentReceipt charge(PaymentCommand command) {
        String transactionId = "txn-" + command.orderId();
        return new PaymentReceipt(transactionId);
    }
}
~~~

Package `com.acme.payment.stripe.internal` không cần export. Provider được khai báo bằng `provides ... with ...`, nên module system và `ServiceLoader` có thể tìm implementation theo service metadata.

Trong module checkout, việc tìm provider có thể thực hiện qua:

~~~java
package com.acme.checkout.api;

import com.acme.payment.api.PaymentCommand;
import com.acme.payment.api.PaymentGateway;
import com.acme.payment.api.PaymentReceipt;

import java.util.ServiceLoader;

public final class CheckoutService {
    public CheckoutResult checkout(CheckoutRequest request) {
        PaymentGateway gateway = ServiceLoader
            .load(PaymentGateway.class)
            .findFirst()
            .orElseThrow(() -> new IllegalStateException(
                "No PaymentGateway provider is available"
            ));

        PaymentReceipt receipt = gateway.charge(
            new PaymentCommand(request.orderId(), request.amountInCents())
        );

        return new CheckoutResult(request.orderId(), receipt.transactionId());
    }
}
~~~

Các kiểu công khai của checkout có thể do chính checkout sở hữu:

~~~java
package com.acme.checkout.api;

public record CheckoutRequest(String orderId, long amountInCents) {
}
~~~

~~~java
package com.acme.checkout.api;

public record CheckoutResult(String orderId, String paymentReference) {
}
~~~

Consumer của checkout chỉ cần biết `CheckoutRequest` và `CheckoutResult`. Nó không cần import `PaymentGateway`, `PaymentCommand` hay `StripePaymentGateway`, vì các kiểu đó không xuất hiện trong public signature của checkout.

Khi khởi chạy ví dụ, provider phải có mặt trong cấu hình module runtime. Có thể thêm provider làm root module một cách tường minh:

~~~bash
java --module-path out \
  --add-modules com.acme.payment.stripe \
  --module com.acme.checkout/com.acme.checkout.app.Main
~~~

Ví dụ này thể hiện ba boundary:

1. `com.acme.checkout` phụ thuộc vào API thanh toán.
2. `com.acme.payment.stripe` phụ thuộc vào cùng API để cung cấp implementation.
3. Consumer của checkout chỉ phụ thuộc vào API checkout mà nó sử dụng.

Khi đổi provider Stripe sang một provider khác, module checkout không cần sửa code nếu provider mới tuân thủ cùng hợp đồng và được đưa vào runtime configuration.

## 6. Giữ implementation bên trong boundary

Một module có thể export package API và giữ phần còn lại ở package không export:

~~~java
module com.acme.order {
    exports com.acme.order.api;
}
~~~

Ví dụ:

~~~text
com.acme.order/
├── module-info.java
└── com/acme/order/
    ├── api/
    │   ├── OrderService.java
    │   ├── OrderRequest.java
    │   └── OrderResult.java
    ├── internal/
    │   ├── DefaultOrderService.java
    │   └── OrderValidator.java
    └── persistence/
        ├── OrderRepository.java
        └── JdbcOrderRepository.java
~~~

Consumer chỉ nhìn thấy `api`. Các lớp trong `internal` và `persistence` có thể thay đổi mà không biến thành hợp đồng công khai.

Không export package chỉ để một module khác có thể gọi lớp nội bộ. Nếu module khác thực sự cần chức năng đó, hãy xác định xem chức năng có thuộc API ổn định hay nên được cung cấp qua một interface/service boundary.

### exports, qualified exports và opens

Có ba lựa chọn thường được cân nhắc:

~~~java
module com.acme.order {
    exports com.acme.order.api;
    exports com.acme.order.spi to com.acme.order.extension;
    opens com.acme.order.persistence to com.acme.orm;
}
~~~

- `exports` công khai package cho mọi module đọc module này.
- `exports ... to ...` chỉ công khai package cho một số module được chỉ định.
- `opens ... to ...` cho phép một module được chỉ định truy cập reflection sâu vào package.

Qualified exports có thể hữu ích cho một SPI nội bộ được chia sẻ với một số extension đã biết. Tuy nhiên, nếu danh sách consumer liên tục phình to, đó có thể là dấu hiệu boundary đang bị rò rỉ.

`opens` phục vụ nhu cầu reflection của framework. Nó không phải cách thay thế cho một API Java thông thường và không nên mở toàn bộ package nếu chỉ một framework cần truy cập một package cụ thể.

## 7. Giữ module graph có hướng và ít tầng phụ thuộc

Một graph rõ ràng thường có hướng từ tầng sử dụng tới tầng cung cấp hợp đồng:

~~~text
application
    │
    ▼
business module
    │
    ▼
small API / SPI
    ▲
    │
provider / adapter
~~~

Các module nghiệp vụ không nên phụ thuộc ngược vào implementation của adapter. Adapter phụ thuộc vào abstraction mà nó triển khai.

Nếu hai module cần gọi lẫn nhau, hãy kiểm tra xem chúng có đang gộp hai trách nhiệm khác nhau vào cùng một boundary hay không. Có thể tách một hợp đồng nhỏ dùng chung thành API module, nhưng không nên tạo một module `common` khổng lồ chứa mọi kiểu tiện ích của hệ thống.

Cần giữ cân bằng:

- **Module quá lớn:** boundary mờ, nhiều chức năng không liên quan bị gom lại.
- **Module quá nhỏ:** dependency graph phức tạp, nhiều descriptor và chi phí điều phối không đem lại lợi ích.
- **API quá rộng:** consumer phụ thuộc vào nhiều kiểu và chi tiết không cần thiết.
- **API quá vụn:** consumer phải ghép nhiều thao tác cấp thấp để thực hiện một hành vi nghiệp vụ.

Mục tiêu là module có cohesion cao: các thành phần bên trong phục vụ cùng một trách nhiệm, còn API công khai thể hiện đúng nhu cầu của consumer.

## 8. Quy trình thiết kế một boundary mới

Khi tạo module hoặc refactor dependency, có thể đi theo các bước sau:

1. **Xác định consumer:** module nào cần chức năng và consumer thực sự cần gọi những thao tác nào?
2. **Định nghĩa API trước:** tạo các interface, record hoặc exception cần thiết với chữ ký nhỏ và ổn định.
3. **Chọn package công khai:** chỉ export package chứa hợp đồng mà consumer được phép sử dụng.
4. **Giữ implementation nội bộ:** đặt class triển khai, repository, adapter và cấu hình vào package không export.
5. **Khai báo dependency trực tiếp:** dùng `requires` cho module mà code thực sự cần đọc.
6. **Xem lại public signatures:** chỉ dùng `requires transitive` khi consumer cần đọc dependency xuất hiện trong API public.
7. **Đảo chiều phụ thuộc khi phù hợp:** dùng interface/SPI và `uses`/`provides` nếu module nghiệp vụ không nên biết provider cụ thể.
8. **Kiểm tra module graph:** bảo đảm dependency đi theo hướng kiến trúc dự kiến và không tạo vòng phụ thuộc.
9. **Kiểm tra runtime:** xác nhận provider và dependency có mặt trong module configuration khi khởi chạy.

Một API boundary tốt phải có lý do rõ ràng cho từng kiểu public và từng cạnh `requires`. Nếu không giải thích được consumer cần một package hoặc dependency nào, hãy xem lại việc export và khai báo đó.

## Kết luận

Giảm phụ thuộc trong JPMS bắt đầu từ việc thu nhỏ bề mặt API và giữ implementation sau boundary của module. `exports` xác định package nào được công khai; `requires` thể hiện dependency trực tiếp; `requires transitive` chỉ nên dùng khi dependency thực sự là một phần của hợp đồng public. Với các integration có thể thay thế, interface và service provider giúp module nghiệp vụ phụ thuộc vào abstraction thay vì implementation cụ thể.

Khi thiết kế module, hãy bắt đầu từ nhu cầu của consumer, định nghĩa hợp đồng nhỏ, giữ package nội bộ không export và kiểm tra hướng của module graph. Cách làm này giúp implementation thay đổi độc lập hơn và giới hạn phạm vi ảnh hưởng của mỗi lần sửa đổi.

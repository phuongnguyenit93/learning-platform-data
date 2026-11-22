# Kiểm tra service binding bằng module descriptor

## 1. Service binding trong JPMS là gì?

JPMS hỗ trợ cơ chế Service Provider Interface (SPI) để một module công bố dịch vụ, module khác cung cấp implementation và module tiêu thụ tìm implementation thông qua `ServiceLoader`.

Cơ chế này được mô tả bằng hai chỉ thị trong `module-info.java`:

- `uses`: khai báo module có nhu cầu sử dụng một service type.
- `provides ... with ...`: khai báo module cung cấp implementation cho service type đó.

Ví dụ tổng quát:

~~~java
module com.acme.checkout {
    requires com.acme.payment.api;
    uses com.acme.payment.spi.PaymentProvider;
}
~~~

Module triển khai:

~~~java
module com.acme.payment.fastpay {
    requires com.acme.payment.api;

    provides com.acme.payment.spi.PaymentProvider
        with com.acme.payment.fastpay.FastPayProvider;
}
~~~

Các khai báo này là metadata của module. Chúng giúp compiler, JVM và cơ chế phân giải module biết consumer cần service nào, provider nào đăng ký service đó. Khi ứng dụng gọi `ServiceLoader`, các provider phù hợp có thể được phát hiện và tạo instance theo cơ chế service loading.

Cần phân biệt hai hoạt động:

1. **Service binding khi phân giải module graph:** resolver có thể tìm và đưa các module cung cấp service được sử dụng vào cấu hình module.
2. **Service loading khi chạy ứng dụng:** `ServiceLoader` tìm và tạo các provider để code sử dụng.

Module descriptor khai báo mối quan hệ. Việc kiểm tra runtime mới xác nhận ứng dụng thực sự tìm và sử dụng được provider.

## 2. Ba vai trò trong một service

Một service thường có ba vai trò:

| Vai trò | Trách nhiệm | Khai báo trong module descriptor |
|---|---|---|
| Service API | Định nghĩa interface hoặc abstract service type | Export package chứa service type |
| Consumer | Cần sử dụng service nhưng không phụ thuộc trực tiếp vào implementation cụ thể | `requires` API module và `uses` service type |
| Provider | Cung cấp một implementation của service | `requires` API module và `provides ... with ...` |

Ví dụ với hệ thống thanh toán:

~~~text
com.acme.payment.api
    Định nghĩa PaymentProvider

com.acme.payment.fastpay
    Cung cấp FastPayProvider

com.acme.checkout
    Sử dụng PaymentProvider qua ServiceLoader
~~~

Consumer chỉ cần biết contract `PaymentProvider`. Khi có provider mới, module provider có thể được bổ sung mà không phải sửa code consumer, miễn là provider tuân thủ cùng service contract và được đưa vào cấu hình runtime phù hợp.

## 3. Khai báo service API

Tạo module API:

~~~java
// src/com.acme.payment.api/module-info.java
module com.acme.payment.api {
    exports com.acme.payment.spi;
}
~~~

Định nghĩa service type trong package được export:

~~~java
// src/com.acme.payment.api/com/acme/payment/spi/PaymentProvider.java
package com.acme.payment.spi;

public interface PaymentProvider {
    String name();

    void pay(long amount);
}
~~~

Package chứa service type cần được export để consumer có thể import interface và provider có thể triển khai interface đó.

Không nên đặt implementation cụ thể vào module API. Module API chỉ giữ contract mà hai phía cùng phụ thuộc.

## 4. Khai báo provider bằng provides

Module provider khai báo:

~~~java
// src/com.acme.payment.fastpay/module-info.java
module com.acme.payment.fastpay {
    requires com.acme.payment.api;

    provides com.acme.payment.spi.PaymentProvider
        with com.acme.payment.fastpay.FastPayProvider;
}
~~~

Implementation:

~~~java
// src/com.acme.payment.fastpay/com/acme/payment/fastpay/FastPayProvider.java
package com.acme.payment.fastpay;

import com.acme.payment.spi.PaymentProvider;

public class FastPayProvider implements PaymentProvider {

    public FastPayProvider() {
    }

    @Override
    public String name() {
        return "FastPay";
    }

    @Override
    public void pay(long amount) {
        System.out.println("FastPay processes " + amount);
    }
}
~~~

Đọc chỉ thị:

~~~java
provides com.acme.payment.spi.PaymentProvider
    with com.acme.payment.fastpay.FastPayProvider;
~~~

- Phần sau `provides` là service type.
- Phần sau `with` là provider class được đăng ký.
- Provider module phải đọc được module chứa service type, vì vậy ví dụ có `requires com.acme.payment.api;`.

Provider class cần đáp ứng quy tắc của service provider, ví dụ có constructor public không tham số như trên. JPMS cũng hỗ trợ dạng provider method theo quy tắc của `ServiceLoader`; khi dùng dạng đó, cần bảo đảm method `provider()` có chữ ký hợp lệ và trả về service type tương ứng.

Package implementation `com.acme.payment.fastpay` không cần export chỉ để consumer tìm provider bằng `ServiceLoader`. Consumer phụ thuộc vào service type, còn module descriptor của provider đăng ký implementation. Giữ package implementation không export giúp tránh biến lớp triển khai thành API công khai.

## 5. Khai báo consumer bằng uses

Module consumer khai báo:

~~~java
// src/com.acme.checkout/module-info.java
module com.acme.checkout {
    requires com.acme.payment.api;

    uses com.acme.payment.spi.PaymentProvider;
}
~~~

Hai chỉ thị có vai trò riêng:

- `requires com.acme.payment.api;` tạo quan hệ readability để code consumer sử dụng kiểu `PaymentProvider`.
- `uses com.acme.payment.spi.PaymentProvider;` khai báo consumer cần tìm provider cho service type đó.

Với named module, module gọi `ServiceLoader.load(...)` cần khai báo `uses` cho service type. Nếu thiếu khai báo này, thao tác service loading từ module đó có thể thất bại với `ServiceConfigurationError`.

Chỉ thị `uses` không chỉ định provider class. Consumer không cần biết tên `FastPayProvider`, và cũng không cần `requires com.acme.payment.fastpay;` nếu mục tiêu là tìm implementation thông qua SPI.

## 6. Tìm provider bằng ServiceLoader

Code trong consumer:

~~~java
// src/com.acme.checkout/com/acme/checkout/Main.java
package com.acme.checkout;

import com.acme.payment.spi.PaymentProvider;
import java.util.ServiceLoader;

public class Main {

    public static void main(String[] args) {
        ServiceLoader<PaymentProvider> providers =
                ServiceLoader.load(PaymentProvider.class);

        for (PaymentProvider provider : providers) {
            System.out.println("Provider: " + provider.name());
            provider.pay(1000);
        }
    }
}
~~~

Khi chạy, `ServiceLoader` tìm các provider được đăng ký cho `PaymentProvider` trong phạm vi service loading tương ứng.

Nếu có nhiều provider, vòng lặp có thể nhận nhiều implementation. Thứ tự provider không nên được dùng như một quy tắc ưu tiên nghiệp vụ; nếu ứng dụng cần chọn provider theo cấu hình, hãy xây dựng chính sách lựa chọn rõ ràng.

Nếu không tìm thấy provider, vòng lặp không có phần tử để xử lý. Điều đó có thể là hợp lệ nếu service là tùy chọn; nếu ứng dụng bắt buộc phải có provider, cần kiểm tra và báo lỗi cấu hình một cách tường minh.

## 7. Kiểm tra module descriptor

Khi nghi ngờ service không được đăng ký đúng, hãy kiểm tra descriptor của từng module theo đúng vai trò.

### 7.1. Kiểm tra module API

Đảm bảo descriptor của API có package chứa service type:

~~~java
module com.acme.payment.api {
    exports com.acme.payment.spi;
}
~~~

Nếu package chưa được export, consumer hoặc provider ở module khác sẽ không thể sử dụng service type theo cách truy cập Java thông thường.

### 7.2. Kiểm tra module provider

Đảm bảo provider module có đủ hai phần:

~~~java
module com.acme.payment.fastpay {
    requires com.acme.payment.api;

    provides com.acme.payment.spi.PaymentProvider
        with com.acme.payment.fastpay.FastPayProvider;
}
~~~

Các điểm cần đối chiếu:

- Tên service type đúng package và đúng tên lớp.
- Tên provider class đúng với lớp implementation.
- Provider class nằm trong chính module khai báo `provides`.
- Provider module đọc được module chứa service type.
- Provider class đáp ứng quy tắc tạo provider của `ServiceLoader`.

Một lỗi thường gặp là code implementation đã tồn tại nhưng quên thêm `provides`. Khi đó, việc đặt JAR trên module path chưa đủ để biến implementation thành provider được đăng ký trong JPMS.

### 7.3. Kiểm tra module consumer

Đảm bảo consumer có:

~~~java
module com.acme.checkout {
    requires com.acme.payment.api;
    uses com.acme.payment.spi.PaymentProvider;
}
~~~

Đừng nhầm `uses` với `requires`:

- `requires` nói module consumer cần đọc module API.
- `uses` nói module consumer cần service loader tìm implementation cho service type.

Nếu consumer gọi `ServiceLoader` nhưng thiếu `uses`, descriptor chưa mô tả đầy đủ nhu cầu service của module.

## 8. Kiểm tra descriptor đã đóng gói trong JAR

Sau khi build module thành JAR, dùng công cụ `jar` để đọc module descriptor:

~~~bash
jar --describe-module --file build/libs/payment-api.jar
jar --describe-module --file build/libs/payment-fastpay.jar
jar --describe-module --file build/libs/checkout.jar
~~~

Đầu ra của từng JAR giúp xác nhận module name, `requires`, `exports`, `uses` và `provides` đã được đóng gói.

Ví dụ, provider JAR cần thể hiện quan hệ tương đương:

~~~text
com.acme.payment.fastpay
requires com.acme.payment.api
provides com.acme.payment.spi.PaymentProvider
  with com.acme.payment.fastpay.FastPayProvider
~~~

Consumer JAR cần thể hiện:

~~~text
com.acme.checkout
requires com.acme.payment.api
uses com.acme.payment.spi.PaymentProvider
~~~

Tên và cách trình bày chính xác có thể khác theo phiên bản JDK, nhưng cần tìm được đúng service type và provider class trong kết quả.

Nếu kết quả không có `provides` hoặc `uses`, hãy kiểm tra source `module-info.java`, cấu hình source set và quá trình đóng gói. Có thể bạn đang xem nhầm JAR hoặc artifact được build từ source cũ.

## 9. Build và chạy thử toàn bộ module

Với cấu trúc source module như sau:

~~~text
src/
├── com.acme.payment.api/
│   ├── module-info.java
│   └── com/acme/payment/spi/PaymentProvider.java
├── com.acme.payment.fastpay/
│   ├── module-info.java
│   └── com/acme/payment/fastpay/FastPayProvider.java
└── com.acme.checkout/
    ├── module-info.java
    └── com/acme/checkout/Main.java
~~~

Có thể biên dịch tất cả module bằng JDK:

~~~bash
javac --module-source-path src -d mods   -m com.acme.payment.api,com.acme.payment.fastpay,com.acme.checkout
~~~

Sau khi biên dịch, thư mục `mods` chứa các module đã được biên dịch. Chạy module consumer:

~~~bash
java --module-path mods   --module com.acme.checkout/com.acme.checkout.Main
~~~

Nếu mọi khai báo và provider đều hợp lệ, chương trình sẽ tìm thấy `FastPayProvider`, in tên provider và gọi phương thức `pay`.

Khi cần xem quá trình phân giải module, thêm `--show-module-resolution`:

~~~bash
java --show-module-resolution   --module-path mods   --module com.acme.checkout/com.acme.checkout.Main
~~~

Đầu ra giúp quan sát module gốc, các quan hệ phụ thuộc và những module được resolver đưa vào cấu hình. Khi có service binding, chú ý các dòng thể hiện module được bind do service. Việc một provider module xuất hiện trong cấu hình vẫn chưa chứng minh constructor hoặc nghiệp vụ của provider chạy thành công; cần quan sát kết quả `ServiceLoader` trong chương trình.

## 10. Kiểm tra service binding bằng Configuration.resolveAndBind

Ngoài launcher, Java API cho phép tạo module configuration có service binding thông qua `Configuration.resolveAndBind(...)`.

Về ý nghĩa, resolver bắt đầu từ các root module, đọc các chỉ thị `uses`, tìm module có `provides` cho những service type đó và bổ sung provider module cùng các dependency cần thiết vào cấu hình nếu chúng có thể được tìm thấy.

Điểm cần phân biệt:

- `Configuration.resolve(...)` phân giải module graph theo các quan hệ phụ thuộc.
- `Configuration.resolveAndBind(...)` thực hiện phân giải có xét service binding.

Điều này hữu ích khi ứng dụng tạo module layer động, chẳng hạn một hệ thống plugin tự tìm module từ một thư mục. Module layer có thể được tạo từ configuration đã resolve; sau đó dùng overload `ServiceLoader.load(layer, ServiceType.class)` để tìm service trong layer đó.

Service binding là một bước phân giải cấu hình. Nó không tự gọi constructor provider, không chạy code nghiệp vụ và không thay thế việc xử lý lỗi khi service được tải.

## 11. Kiểm tra runtime và các lỗi thường gặp

Sau khi descriptor được kiểm tra, cần chạy một kiểm tra thực tế bằng `ServiceLoader`.

Có thể ghi nhận số lượng provider:

~~~java
long count = ServiceLoader.load(PaymentProvider.class)
        .stream()
        .count();

if (count == 0) {
    throw new IllegalStateException(
            "No PaymentProvider is available");
}
~~~

Nếu provider là bắt buộc, kiểm tra rỗng giúp lỗi cấu hình xuất hiện ngay khi khởi động thay vì đến lúc thanh toán mới thất bại.

Một số tình huống cần phân biệt:

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Không tìm thấy provider | Provider module không có trong module path hoặc chưa được bind vào configuration | Kiểm tra module path và module-resolution output |
| JAR có implementation nhưng ServiceLoader không tìm thấy | Thiếu `provides` trong descriptor hoặc thiếu file cấu hình service ở kiểu triển khai cũ | Dùng `jar --describe-module` kiểm tra descriptor |
| Consumer gọi ServiceLoader nhưng bị lỗi cấu hình | Named consumer thiếu `uses` | Kiểm tra `module-info.java` của module gọi ServiceLoader |
| Không thể import service interface | API package chưa được export hoặc consumer chưa requires API module | Kiểm tra descriptor API và consumer |
| Provider không khởi tạo được | Constructor/provider method không hợp lệ, hoặc code khởi tạo ném exception | Đọc `ServiceConfigurationError` và nguyên nhân gốc |
| Provider class không tương thích | Provider không triển khai service type đúng cách | Kiểm tra kiểu trả về và quan hệ kế thừa/interface |
| Chạy được trên classpath nhưng lỗi trên module path | Descriptor hoặc quy tắc encapsulation khác với cách chạy classpath | Kiểm tra module path, `uses`, `provides`, `exports` và `opens` |

Các lỗi từ service loading có thể được báo dưới dạng `ServiceConfigurationError`. Không nên chỉ bắt lỗi rồi bỏ qua; cần ghi rõ service type, provider và nguyên nhân để người vận hành biết module nào cần sửa.

## 12. Service provider trong module và provider kiểu cũ

JPMS không loại bỏ cơ chế service provider truyền thống của Java. Trên classpath, thư viện có thể đăng ký provider bằng file:

~~~text
META-INF/services/com.acme.payment.spi.PaymentProvider
~~~

File này chứa tên đầy đủ của provider class, thường mỗi dòng một provider.

Với named module, nên khai báo provider bằng `provides ... with ...` trong `module-info.java`. Với ứng dụng đang chuyển đổi, có thể vẫn gặp các JAR cũ dùng `META-INF/services`; cần kiểm tra cách chúng được đặt trên classpath hoặc module path và cách cấu hình runtime phân giải provider.

Không nên mặc định rằng một JAR có file `META-INF/services` đồng nghĩa với việc module descriptor đã có `provides`. Hãy kiểm tra artifact thực tế.

## 13. Checklist kiểm tra service binding

Khi kiểm tra một service trong JPMS, có thể đi theo thứ tự:

1. Service type nằm trong package đã export của API module.
2. Consumer khai báo `requires` API module.
3. Consumer khai báo `uses` đúng service type.
4. Provider khai báo `requires` API module.
5. Provider khai báo `provides ServiceType with ProviderClass`.
6. Provider class đúng tên, nằm trong provider module và đáp ứng quy tắc khởi tạo.
7. Các module cần thiết được đưa vào module path hoặc module layer.
8. Dùng `jar --describe-module` xác nhận descriptor trong artifact.
9. Dùng `--show-module-resolution` khi cần quan sát quá trình phân giải và service binding.
10. Chạy `ServiceLoader` để xác nhận provider được phát hiện và có thể khởi tạo.

Không nên dừng ở việc nhìn thấy một dòng `provides` trong source. Bằng chứng tốt hơn là descriptor đã đóng gói đúng, cấu hình runtime phân giải được module provider và code consumer thực sự nhận được provider.

## 14. Ghi nhớ

Trong JPMS, `uses` mô tả nhu cầu service của consumer, còn `provides ... with ...` đăng ký implementation tại provider module. Hai chỉ thị được đặt ở đúng module theo vai trò của chúng.

`requires` và `exports` vẫn cần thiết để service type có thể được sử dụng giữa các module. Package implementation của provider thường có thể giữ kín vì consumer chỉ làm việc với service abstraction.

Để kiểm tra service binding, hãy kiểm tra cả ba lớp bằng chứng: **module descriptor**, **module resolution** và **ServiceLoader ở runtime**. Descriptor đúng cho biết mối quan hệ đã được khai báo; resolver cho biết module graph có thể đưa provider vào cấu hình; kiểm tra runtime xác nhận provider thực sự được tìm và khởi tạo.

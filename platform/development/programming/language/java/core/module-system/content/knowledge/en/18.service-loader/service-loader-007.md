# Ordering, duplicate provider và lựa chọn implementation

Trong Java, `ServiceLoader` cho phép một module hoặc ứng dụng tìm các implementation của một service interface mà không cần phụ thuộc trực tiếp vào từng class triển khai. Một service có thể có nhiều provider cùng lúc: ví dụ nhiều payment gateway, nhiều serializer hoặc nhiều plugin.

Khi có nhiều provider, ứng dụng cần giải quyết ba vấn đề:

- **Ordering:** thứ tự provider được phát hiện có ổn định và có ý nghĩa ưu tiên hay không?
- **Duplicate provider:** cùng một provider có thể được đăng ký lặp ở đâu, và ứng dụng xử lý trùng như thế nào?
- **Implementation selection:** khi có nhiều implementation hợp lệ, quy tắc nào quyết định implementation được sử dụng?

`ServiceLoader` chịu trách nhiệm khám phá provider. Nó không tự định nghĩa chính sách nghiệp vụ để chọn provider tốt nhất. Nếu kết quả cần ổn định, ứng dụng phải đặt quy tắc lựa chọn rõ ràng.

## 1. Một service có thể có nhiều provider

Giả sử ứng dụng thanh toán định nghĩa một service interface:

~~~java
package com.acme.payment.spi;

public interface PaymentGateway {
    String id();

    int priority();

    PaymentReceipt charge(PaymentCommand command);
}
~~~

Các implementation có thể đến từ những module khác nhau:

~~~java
package com.acme.payment.stripe;

public final class StripeGateway implements PaymentGateway {
    @Override
    public String id() {
        return "stripe";
    }

    @Override
    public int priority() {
        return 100;
    }

    @Override
    public PaymentReceipt charge(PaymentCommand command) {
        return new PaymentReceipt("stripe-" + command.orderId());
    }
}
~~~

~~~java
package com.acme.payment.bank;

public final class BankGateway implements PaymentGateway {
    @Override
    public String id() {
        return "bank";
    }

    @Override
    public int priority() {
        return 80;
    }

    @Override
    public PaymentReceipt charge(PaymentCommand command) {
        return new PaymentReceipt("bank-" + command.orderId());
    }
}
~~~

Một module consumer có thể tìm tất cả implementation bằng:

~~~java
ServiceLoader<PaymentGateway> loader =
    ServiceLoader.load(PaymentGateway.class);

for (PaymentGateway gateway : loader) {
    System.out.println(gateway.id());
}
~~~

Vòng lặp có thể trả về nhiều provider. Điều này là hành vi bình thường của SPI: một service interface mô tả hợp đồng chung, còn provider cung cấp các cách triển khai khác nhau.

## 2. Đăng ký provider trong named module

Với JPMS, provider có thể được khai báo trong `module-info.java`.

Module chứa service API:

~~~java
module com.acme.payment.spi {
    exports com.acme.payment.spi;
}
~~~

Module consumer:

~~~java
module com.acme.checkout {
    requires com.acme.payment.spi;
    uses com.acme.payment.spi.PaymentGateway;
}
~~~

Directive `uses` khai báo rằng module checkout tiêu thụ service `PaymentGateway`. Nó giúp module system biết service nào cần được tìm khi sử dụng cơ chế service binding và `ServiceLoader`.

Module provider:

~~~java
module com.acme.payment.stripe {
    requires com.acme.payment.spi;

    provides com.acme.payment.spi.PaymentGateway
        with com.acme.payment.stripe.StripeGateway;
}
~~~

Một provider khác có thể nằm trong module riêng:

~~~java
module com.acme.payment.bank {
    requires com.acme.payment.spi;

    provides com.acme.payment.spi.PaymentGateway
        with com.acme.payment.bank.BankGateway;
}
~~~

Provider class phải đáp ứng quy tắc của `ServiceLoader`. Cách thông dụng là class public triển khai service và có public no-argument constructor. Với provider trong named module, có thể dùng public static provider method theo quy tắc JPMS để tạo đối tượng service; cách này hữu ích khi cần factory hoặc cấu hình khởi tạo.

Trong kiến trúc plugin dùng `ModuleLayer`, có thể chỉ định layer cần tìm provider:

~~~java
ServiceLoader<PaymentGateway> loader =
    ServiceLoader.load(pluginLayer, PaymentGateway.class);
~~~

Cách gọi này giúp ứng dụng tìm provider trong layer được chỉ định và các parent layer của nó. Đây là lựa chọn phù hợp khi provider được nạp động trong plugin layer. Service API nên được chia sẻ từ layer cha để consumer và provider cùng tham chiếu một định nghĩa interface.

## 3. Đăng ký provider trên classpath

Thư viện chưa được modularize có thể đăng ký provider bằng file cấu hình:

~~~text
META-INF/services/com.acme.payment.spi.PaymentGateway
~~~

Nội dung file liệt kê tên đầy đủ của các provider class, mỗi dòng một class:

~~~text
com.acme.payment.stripe.StripeGateway
com.acme.payment.bank.BankGateway
~~~

Các dòng có thể chứa khoảng trắng và comment bắt đầu bằng ký tự `#`. File được đọc theo UTF-8. Dòng trùng tên provider trong cùng một provider-configuration file bị bỏ qua theo quy tắc của `ServiceLoader`.

Với classpath, `ServiceLoader.load(PaymentGateway.class)` thường dùng thread context class loader để tìm provider configuration và class tương ứng. Vì vậy, khi ứng dụng hoặc framework thay đổi context class loader, tập provider được tìm thấy cũng có thể thay đổi.

Không nên trộn lẫn hai kiểu đăng ký:

- Named module khai báo service bằng `uses` và `provides`.
- Provider trên classpath khai báo class trong `META-INF/services`.

Cả hai cùng phục vụ SPI, nhưng nguồn metadata và phạm vi class loading khác nhau.

## 4. Ordering: thứ tự provider được phát hiện

`ServiceLoader` tìm provider một cách lazy. Provider chỉ được nạp hoặc khởi tạo khi ứng dụng duyệt kết quả hoặc gọi `Provider.get()`. Service loader cũng lưu cache các provider đã được nạp; những lần duyệt tiếp theo có thể trả lại các instance đã cache trước khi tìm provider mới.

Không nên xem thứ tự phát hiện provider là một chính sách ưu tiên nghiệp vụ.

Với provider trên classpath, thứ tự có thể chịu ảnh hưởng bởi thứ tự resource được class loader trả về và thứ tự tên class trong từng file cấu hình. Với provider trong named module, không nên dựa vào thứ tự module được resolver tìm thấy hoặc thứ tự lặp của một tập module. API không cung cấp một hợp đồng ưu tiên toàn cục để ứng dụng chọn implementation theo vị trí.

Ví dụ sau có vẻ ngắn gọn:

~~~java
PaymentGateway gateway =
    ServiceLoader.load(PaymentGateway.class)
        .findFirst()
        .orElseThrow();
~~~

Nhưng `findFirst()` chỉ lấy provider đầu tiên trong encounter order hiện tại. Nếu thứ tự discovery thay đổi do classpath, module finder, plugin layer hoặc cách đóng gói, implementation được chọn có thể thay đổi theo.

Chỉ dùng `findFirst()` khi ứng dụng thực sự không quan tâm provider nào được chọn, hoặc khi thứ tự đã được đảm bảo bởi một cấu hình do ứng dụng kiểm soát. Nếu provider có ưu tiên, hãy biểu diễn ưu tiên thành dữ liệu và sắp xếp rõ ràng.

## 5. Duplicate provider: trùng ở đâu?

Trùng provider có thể xuất hiện ở nhiều mức:

1. **Trùng dòng trong cùng file cấu hình:** cùng tên provider được liệt kê nhiều lần trong một file `META-INF/services`.
2. **Trùng đăng ký trong quá trình đóng gói:** cùng implementation được đưa vào nhiều dependency hoặc nhiều resource cấu hình.
3. **Trùng implementation logic:** hai class khác nhau thực hiện cùng một chức năng hoặc cùng tự nhận một mã provider.
4. **Trùng giữa các nguồn khám phá:** ứng dụng kết hợp provider từ classpath và module layer, khiến cùng một implementation hoặc cùng một chức năng xuất hiện từ nhiều nơi.

`ServiceLoader` bỏ qua tên provider bị lặp trong cùng một provider-configuration file. Tuy nhiên, điều đó không giải quyết được mọi trường hợp trùng về mặt nghiệp vụ. Hai class khác nhau có thể cùng trả về `id()` là `stripe`; một class cũng có thể được đóng gói hoặc nạp trong những môi trường khác nhau.

Vì vậy, service nên có một định danh ổn định như `id()`. Ứng dụng có thể kiểm tra ID trùng sau khi khám phá provider:

~~~java
Map<String, PaymentGateway> byId = new HashMap<>();

for (PaymentGateway gateway : ServiceLoader
        .load(PaymentGateway.class)) {

    PaymentGateway previous =
        byId.putIfAbsent(gateway.id(), gateway);

    if (previous != null) {
        throw new IllegalStateException(
            "Duplicate payment provider id: " + gateway.id()
        );
    }
}
~~~

Cách này phát hiện hai implementation cùng công bố một ID. Nếu hệ thống cho phép nhiều phiên bản của một provider, ID cần bao gồm namespace hoặc version theo hợp đồng đã định nghĩa.

Đừng tự động bỏ provider trùng bằng cách giữ phần tử đầu tiên. Khi thứ tự discovery không được bảo đảm, cách đó có thể âm thầm chọn implementation khác nhau giữa các lần chạy. Với cấu hình sai, báo lỗi rõ ràng thường dễ chẩn đoán hơn.

## 6. Chọn implementation bằng priority và tie-breaker

Một service có thể định nghĩa hai thuộc tính:

- `priority()`: số nguyên lớn hơn biểu thị mức ưu tiên cao hơn.
- `id()`: mã duy nhất, ổn định để xử lý trường hợp bằng điểm ưu tiên.

Ví dụ lựa chọn provider:

~~~java
import java.util.Comparator;
import java.util.ServiceLoader;
import java.util.stream.Collectors;
import java.util.List;

List<PaymentGateway> gateways =
    ServiceLoader.load(PaymentGateway.class)
        .stream()
        .map(ServiceLoader.Provider::get)
        .collect(Collectors.toList());

PaymentGateway selected = gateways.stream()
    .min(
        Comparator.comparingInt(PaymentGateway::priority)
            .reversed()
            .thenComparing(PaymentGateway::id)
    )
    .orElseThrow(() ->
        new IllegalStateException("No PaymentGateway provider found")
    );
~~~

Quy tắc ở đây là:

1. Provider có priority cao hơn được chọn trước.
2. Nếu priority bằng nhau, ID có thứ tự từ điển nhỏ hơn được chọn.
3. Nếu không có provider, ứng dụng báo lỗi rõ ràng.

Comparator đã định nghĩa đầy đủ tie-breaker nên kết quả không phụ thuộc encounter order, miễn là mỗi provider có ID ổn định và duy nhất.

Nếu nghiệp vụ cần lựa chọn theo region, currency, tenant hoặc feature flag, hãy đưa tiêu chí đó vào một policy riêng. Ví dụ, ứng dụng có thể lọc các gateway hỗ trợ currency trước, sau đó mới sắp xếp theo priority. Không nên dùng priority đơn lẻ nếu một provider không đủ khả năng xử lý yêu cầu hiện tại.

## 7. Kiểm tra ID trùng trước khi chọn

Có thể kết hợp phát hiện duplicate với lựa chọn implementation trong cùng một bước:

~~~java
Map<String, PaymentGateway> providersById = new HashMap<>();

for (PaymentGateway gateway : ServiceLoader
        .load(PaymentGateway.class)) {

    String id = gateway.id();

    if (id == null || id.isBlank()) {
        throw new IllegalStateException(
            "PaymentGateway provider must declare a non-empty id"
        );
    }

    PaymentGateway existing =
        providersById.putIfAbsent(id, gateway);

    if (existing != null) {
        throw new IllegalStateException(
            "More than one PaymentGateway declares id: " + id
        );
    }
}

PaymentGateway selected = providersById.values().stream()
    .min(
        Comparator.comparingInt(PaymentGateway::priority)
            .reversed()
            .thenComparing(PaymentGateway::id)
    )
    .orElseThrow(() ->
        new IllegalStateException("No PaymentGateway provider found")
    );
~~~

Ví dụ này giả định provider được khởi tạo thành công và `id()` là một phần của service contract. Nếu khởi tạo provider có chi phí cao, có side effect hoặc cần cấu hình trước, nên thiết kế factory/configuration riêng để việc discovery không kích hoạt toàn bộ hoạt động nghiệp vụ.

Một lựa chọn khác là kiểm tra metadata trước khi tạo instance bằng `ServiceLoader.stream()` và `Provider.type()`. Tuy nhiên, metadata class chỉ hữu ích nếu chính sách lựa chọn có thể xác định từ type hoặc annotation mà không cần gọi provider. Nếu priority là dữ liệu runtime do instance cung cấp, ứng dụng vẫn phải tạo instance để đọc nó.

## 8. Lọc provider theo khả năng thay vì chỉ theo thứ tự

Priority trả lời provider nào được ưu tiên, nhưng chưa chắc provider nào phù hợp với request.

Ví dụ, một gateway chỉ hỗ trợ USD và EUR:

~~~java
public interface PaymentGateway {
    String id();

    int priority();

    boolean supports(String currency);

    PaymentReceipt charge(PaymentCommand command);
}
~~~

Chọn trong nhóm provider hỗ trợ currency:

~~~java
PaymentGateway selected = ServiceLoader
    .load(PaymentGateway.class)
    .stream()
    .map(ServiceLoader.Provider::get)
    .filter(gateway -> gateway.supports(command.currency()))
    .min(
        Comparator.comparingInt(PaymentGateway::priority)
            .reversed()
            .thenComparing(PaymentGateway::id)
    )
    .orElseThrow(() ->
        new IllegalStateException(
            "No gateway supports currency " + command.currency()
        )
    );
~~~

Luồng lựa chọn nên phản ánh thứ tự nghiệp vụ:

1. Loại provider không tương thích với request.
2. Loại provider bị tắt bởi cấu hình hoặc feature flag.
3. Sắp xếp provider còn lại theo priority.
4. Dùng tie-breaker ổn định.
5. Báo lỗi nếu không còn provider phù hợp.

Nếu ứng dụng cần người vận hành chọn implementation, có thể dùng cấu hình tường minh như `payment.gateway=stripe`. Khi đó, ServiceLoader vẫn đảm nhiệm discovery, còn cấu hình quyết định provider được chọn. Cần báo lỗi nếu ID được cấu hình không tồn tại hoặc provider không hỗ trợ request.

## 9. Provider được khởi tạo lazy và cache như thế nào?

`ServiceLoader` không nhất thiết tạo tất cả provider ngay khi gọi `load()`. Việc tìm và khởi tạo diễn ra khi ứng dụng duyệt iterator hoặc lấy instance từ `Provider`.

API `stream()` trả về các `ServiceLoader.Provider<S>`. Mỗi provider descriptor có thể cho biết type trước khi gọi `get()` để tạo instance:

~~~java
ServiceLoader<PaymentGateway> loader =
    ServiceLoader.load(PaymentGateway.class);

loader.stream().forEach(provider -> {
    System.out.println(provider.type().getName());
});
~~~

Khi cần instance:

~~~java
PaymentGateway gateway = provider.get();
~~~

Các instance đã được nạp được cache trong service loader. Nếu cấu hình provider thay đổi hoặc ứng dụng cần khám phá lại, có thể gọi:

~~~java
loader.reload();
~~~

`reload()` xóa cache provider đã nạp; lần duyệt tiếp theo sẽ tìm lại provider theo cấu hình hiện tại. Nó không tự thay đổi module layer, module path hoặc các JAR đã được define trong runtime.

Một `ServiceLoader` không được thiết kế để dùng đồng thời an toàn từ nhiều thread. Nếu cần truy cập đồng thời, hãy tạo loader theo phạm vi sử dụng phù hợp hoặc đồng bộ hóa việc truy cập theo thiết kế của ứng dụng.

## 10. Xử lý lỗi khi provider được phát hiện

Quá trình discovery hoặc khởi tạo có thể thất bại. Một số nguyên nhân thường gặp:

- Tên provider trong `META-INF/services` không hợp lệ.
- Provider class không tìm thấy bởi class loader.
- Provider không triển khai service interface.
- Constructor hoặc provider method không thể gọi.
- Provider ném exception khi khởi tạo.
- Module provider khai báo sai service hoặc module consumer thiếu `uses`.

`ServiceLoader` có thể ném `ServiceConfigurationError` khi cấu hình hoặc provider không hợp lệ. Không nên bắt lỗi rồi âm thầm bỏ qua tất cả provider hỏng, vì ứng dụng có thể tiếp tục với một implementation không đáp ứng yêu cầu.

Ví dụ ghi rõ provider gặp lỗi:

~~~java
try {
    for (PaymentGateway gateway :
            ServiceLoader.load(PaymentGateway.class)) {
        System.out.println("Loaded: " + gateway.id());
    }
} catch (ServiceConfigurationError error) {
    throw new IllegalStateException(
        "Unable to load PaymentGateway providers",
        error
    );
}
~~~

Nếu hệ thống có chính sách fallback, hãy xác định rõ provider nào được phép thay thế, điều kiện nào kích hoạt fallback và cách ghi log. Không nên xem provider bất kỳ còn chạy được là fallback hợp lệ.

## 11. Chọn provider trong plugin layer

Khi plugin được nạp vào layer con, nên dùng overload nhận layer để giới hạn phạm vi khám phá:

~~~java
ServiceLoader<PaymentGateway> loader =
    ServiceLoader.load(pluginLayer, PaymentGateway.class);
~~~

Giả sử:

~~~text
Parent layer
└── com.acme.payment.spi

Plugin layer
├── com.acme.payment.stripe
└── com.acme.payment.bank
~~~

Hai module provider khai báo `provides` cho service API ở parent. Ứng dụng có thể khám phá các provider trong plugin layer và các parent layer theo quy tắc của overload này.

Nếu ứng dụng có nhiều plugin layer độc lập, có thể tạo một service loader cho từng layer rồi kết hợp các candidate theo policy của host. Khi kết hợp, hãy kiểm tra ID trùng trên toàn bộ tập candidate; hai plugin khác layer vẫn có thể công bố cùng một ID.

Không nên dựa vào thứ tự của `pluginLayer.modules()` để quyết định provider ưu tiên. Đây là tập module của layer, không phải danh sách ưu tiên service. Hãy lấy provider qua ServiceLoader rồi áp dụng policy rõ ràng.

## 12. Các nguyên tắc thiết kế

- **Định danh ổn định:** mỗi provider nên có ID duy nhất trong phạm vi mà ứng dụng quản lý.
- **Ưu tiên rõ ràng:** nếu có nhiều implementation, định nghĩa priority và tie-breaker thay vì dùng `findFirst()`.
- **Không phụ thuộc discovery order:** thứ tự provider có thể thay đổi theo nguồn cấu hình, class loader hoặc layer.
- **Kiểm tra duplicate:** phát hiện ID trùng và báo lỗi cấu hình có thể hành động được.
- **Tách discovery khỏi selection:** ServiceLoader tìm candidate; policy của ứng dụng chọn candidate phù hợp.
- **Lọc theo capability:** kiểm tra provider hỗ trợ request hiện tại trước khi so sánh ưu tiên.
- **Quản lý lifecycle:** hiểu lazy initialization, cache, `reload()` và giới hạn thread-safety.
- **Giữ service API ổn định:** provider và consumer cùng phụ thuộc vào SPI module, không phụ thuộc trực tiếp vào implementation của nhau.

## 13. Chẩn đoán các vấn đề thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Không tìm thấy provider | Thiếu `uses`, thiếu `provides`, thiếu file service hoặc sai layer/class loader | Kiểm tra descriptor, `META-INF/services` và overload `ServiceLoader.load` |
| Provider đầu tiên thay đổi giữa các môi trường | Code dựa vào encounter order | Thêm priority và tie-breaker ổn định |
| Cùng một chức năng xuất hiện nhiều lần | Provider được đăng ký qua nhiều artifact hoặc module | Kiểm tra provider ID và nguồn đăng ký |
| Hai provider có cùng ID | Trùng cấu hình hoặc contract không quy định ID duy nhất | Fail fast và sửa registration |
| Provider lỗi khi duyệt | Class không nạp được hoặc constructor/provider method thất bại | Kiểm tra nguyên nhân của `ServiceConfigurationError` |
| Provider mới không xuất hiện sau khi thay đổi cấu hình | Loader đang giữ cache hoặc layer chưa được tạo lại | Cân nhắc `reload()` và kiểm tra lifecycle của layer |
| Plugin không tương thích service interface | SPI class bị nạp từ định nghĩa khác hoặc sai version | Đặt SPI trong parent layer chung và kiểm tra defining class loader |

## Kết luận

`ServiceLoader` có thể khám phá nhiều implementation của cùng một service. Nó hỗ trợ đăng ký provider bằng `provides ... with ...` trong named module hoặc file `META-INF/services` trên classpath, đồng thời nạp provider theo cơ chế lazy và cache instance đã được tìm thấy.

Ứng dụng cần tự định nghĩa cách xử lý nhiều provider. Hãy cấp ID ổn định, phát hiện ID trùng, lọc theo capability và chọn implementation bằng priority cùng tie-breaker xác định. `findFirst()` chỉ phản ánh encounter order hiện tại; nó không phải chính sách ưu tiên bền vững. Với plugin layer, dùng `ServiceLoader.load(layer, service)` để khám phá đúng phạm vi rồi áp dụng cùng policy lựa chọn của ứng dụng.

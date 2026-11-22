# Optional dependency và requires static

Trong Java Platform Module System (JPMS), directive **requires** khai báo một module cần được đọc. Với dependency thông thường, module được yêu cầu phải có mặt khi phân giải module graph ở runtime. Nhưng có những thư viện chỉ cần thiết khi biên dịch, hoặc chỉ cung cấp một tính năng bổ sung mà ứng dụng có thể chạy khi thư viện đó vắng mặt.

Directive **requires static** biểu diễn loại phụ thuộc này: dependency bắt buộc ở thời điểm biên dịch nhưng có thể vắng mặt ở runtime. Đây là một công cụ hữu ích để thiết kế module có tích hợp tùy chọn, nhưng cần xử lý cẩn thận các class thực sự tham chiếu tới dependency đó.

## 1. Dependency thông thường với requires

Một named module khai báo dependency bắt buộc bằng **requires** trong **module-info.java**:

~~~java
module com.example.orders {
    requires com.example.payment;
}
~~~

Điều này có nghĩa module orders cần đọc module payment. Module payment phải có thể được tìm thấy và phân giải khi biên dịch cũng như khi khởi chạy ứng dụng.

Nếu module payment không có trên module path runtime, quá trình phân giải module graph sẽ thất bại, ngay cả khi một nhánh code cụ thể không gọi tới payment trong lần chạy đó.

Dependency thông thường phù hợp khi module là một phần thiết yếu của ứng dụng. Nếu ứng dụng không thể hoạt động đúng khi thiếu module đó, hãy dùng **requires**.

## 2. requires static biểu diễn dependency tùy chọn ở runtime

Cú pháp:

~~~java
module com.example.orders {
    requires static com.example.metrics;
}
~~~

Module orders cần module metrics khi biên dịch, nhưng module metrics không bắt buộc phải có mặt khi chạy.

Có thể hiểu theo hai thời điểm:

- **Compile time:** compiler cần tìm thấy module metrics để kiểm tra import, kiểu dữ liệu và lời gọi API trong source.
- **Runtime:** module metrics có thể vắng mặt mà bản thân module orders vẫn được phân giải. Nếu metrics có mặt và được phân giải trong cấu hình runtime, quan hệ đọc tới nó được thiết lập.

Vì vậy, **requires static** không có nghĩa dependency bị bỏ qua hoàn toàn. Nó vẫn là một quan hệ module được khai báo và có ý nghĩa khi dependency tồn tại. Điểm khác biệt là module system không bắt buộc dependency phải hiện diện ở runtime.

## 3. Ví dụ module có tích hợp metrics tùy chọn

Giả sử ứng dụng orders có thể gửi số liệu tới một thư viện metrics. Chức năng đặt hàng chính vẫn hoạt động nếu không cài thư viện metrics.

Module descriptor:

~~~java
module com.example.orders {
    requires static com.example.metrics;
}
~~~

Một adapter riêng sử dụng API của thư viện:

~~~java
package com.example.orders.internal;

import com.example.metrics.MetricsRegistry;

public final class MetricsAdapter {
    private MetricsAdapter() {
    }

    public static void recordOrderCreated() {
        MetricsRegistry.increment("orders.created");
    }
}
~~~

Phần tích hợp tùy chọn có thể được nạp khi module metrics hiện diện trong boot layer:

~~~java
package com.example.orders;

import java.lang.reflect.Method;
import java.util.Optional;

public class OptionalMetrics {
    public static void recordIfAvailable() throws Exception {
        Optional<Module> metrics =
                ModuleLayer.boot().findModule("com.example.metrics");

        if (metrics.isEmpty()) {
            return;
        }

        Class<?> adapter = Class.forName(
                "com.example.orders.internal.MetricsAdapter");

        Method record = adapter.getMethod("recordOrderCreated");
        record.invoke(null);
    }
}
~~~

Ví dụ này minh họa cách cô lập phần tích hợp có tham chiếu tới thư viện tùy chọn. Khi module metrics không được phân giải vào boot layer, ứng dụng bỏ qua adapter. Khi module có mặt, adapter có thể được nạp và sử dụng.

Trong ứng dụng thực tế, cần chọn cơ chế phát hiện phù hợp với cách nạp module. Nếu dependency được đặt trong một module layer riêng thay vì boot layer, hãy kiểm tra layer chứa dependency đó. Đồng thời, xử lý các ngoại lệ reflection và lỗi liên kết phù hợp với chính sách của ứng dụng.

## 4. requires static không tự làm code an toàn khi thiếu dependency

Một hiểu nhầm phổ biến là chỉ cần đổi **requires** thành **requires static** thì mọi code tham chiếu dependency đều có thể chạy khi module đó bị gỡ khỏi runtime.

Điều đó không đúng. **requires static** chỉ làm cho dependency không bắt buộc trong bước phân giải module graph. Nó không thay thế class hoặc API của thư viện.

Nếu ứng dụng thực sự nạp class có tham chiếu tới kiểu của module đã vắng mặt, JVM có thể phát sinh lỗi liên kết như **NoClassDefFoundError** hoặc một lỗi **LinkageError** khác khi kiểu được phân giải hoặc sử dụng.

Ví dụ, nếu main flow luôn gọi trực tiếp **MetricsRegistry.increment(...)**, nhưng module metrics không có mặt, ứng dụng vẫn có thể thất bại khi chạy nhánh đó. Tùy thời điểm JVM phân giải symbolic reference, lỗi có thể xuất hiện khi nạp, liên kết hoặc thực thi class.

Để thiết kế optional dependency an toàn:

1. Giữ phần code tham chiếu trực tiếp tới thư viện tùy chọn trong adapter hoặc package riêng.
2. Chỉ nạp và gọi adapter khi dependency thực sự có mặt.
3. Đảm bảo luồng nghiệp vụ chính không cần kiểu của dependency tùy chọn.
4. Xử lý trường hợp dependency thiếu, sai phiên bản hoặc không thể khởi tạo theo chính sách rõ ràng.
5. Kiểm thử cả hai cấu hình: có dependency và không có dependency.

Không nên để kiểu của thư viện tùy chọn xuất hiện trong chữ ký API bắt buộc của những class luôn được ứng dụng sử dụng, trừ khi việc thiếu thư viện được xem là lỗi có chủ đích.

## 5. requires static khác requires và requires transitive

Ba dạng directive giải quyết những nhu cầu khác nhau:

| Directive | Bắt buộc khi biên dịch | Bắt buộc ở runtime | Truyền tiếp khả năng đọc |
|---|---|---|---|
| **requires M** | Có | Có | Không |
| **requires static M** | Có | Không | Không |
| **requires transitive M** | Có | Có | Có |
| **requires static transitive M** | Có | Không | Có, khi module được phân giải |

**requires transitive** dùng khi API của module hiện tại phụ thuộc vào kiểu từ module khác và các module đọc module hiện tại cũng cần đọc dependency đó.

**requires static transitive** kết hợp hai ý nghĩa: dependency cần thiết trong môi trường biên dịch và khả năng đọc được truyền tiếp, nhưng dependency vẫn có thể vắng mặt ở runtime.

Ví dụ:

~~~java
module com.example.api {
    requires static transitive com.example.annotations;
    exports com.example.api;
}
~~~

Nếu API public sử dụng annotation hoặc kiểu từ module annotations, module tiêu thụ có thể cần đọc module đó khi biên dịch. Với **static transitive**, khả năng đọc được truyền tiếp trong môi trường biên dịch; ở runtime, dependency vẫn không bắt buộc phải có mặt.

Hãy cân nhắc kỹ khi public API phơi bày kiểu từ một dependency optional. Nếu người gọi cần nạp hoặc thao tác với kiểu đó ở runtime, dependency phải được cung cấp trong cấu hình runtime tương ứng. Tính optional của module graph không làm kiểu dữ liệu trở nên khả dụng khi thư viện bị thiếu.

## 6. requires static có cần dependency trên module path không?

Có. Ở thời điểm biên dịch, compiler vẫn phải tìm thấy module được khai báo trong **requires static** để kiểm tra source.

Ví dụ:

~~~bash
javac --module-path libs \
      --module-source-path src \
      -d out \
      -m com.example.orders
~~~

Thư mục **libs** cần chứa module metrics hoặc một module tương thích mà source sử dụng. Nếu module metrics không có trong nguồn module có thể quan sát khi biên dịch, compiler sẽ báo không tìm thấy module hoặc không giải quyết được dependency.

Khi chạy, có thể không đưa module metrics vào module path:

~~~bash
java --module-path out \
     --module com.example.orders/com.example.orders.Main
~~~

Lệnh runtime chỉ chứa module orders. Vì dependency được khai báo static, module graph có thể được phân giải mà không cần module metrics. Tuy nhiên, ứng dụng phải tránh nạp hoặc gọi phần code cần metrics trong cấu hình này.

Nếu muốn bật tính năng metrics, đưa module đó vào module path runtime:

~~~bash
java --module-path "out:libs" \
     --module com.example.orders/com.example.orders.Main
~~~

Khi module metrics có mặt và được phân giải, module orders có thể đọc nó theo quan hệ static đã khai báo.

Trên Windows, dấu phân cách giữa các phần tử module path là dấu chấm phẩy (**;**); trên Linux và macOS là dấu hai chấm (**:**).

## 7. Dùng requires static cho thư viện annotation

Một trường hợp phổ biến là dependency chỉ cần để compiler đọc annotation hoặc metadata trong source.

Ví dụ:

~~~java
module com.example.domain {
    requires static com.example.nullness;
}
~~~

Source có thể sử dụng annotation:

~~~java
package com.example.domain;

import com.example.nullness.NonNull;

public class CustomerService {
    public String display(@NonNull String name) {
        return name.trim();
    }
}
~~~

Nếu annotation chỉ phục vụ kiểm tra lúc biên dịch và không cần được đọc ở runtime, dependency annotation có thể được khai báo bằng **requires static**.

Cần kiểm tra retention policy của annotation:

- **SOURCE:** annotation bị loại bỏ khỏi class file sau biên dịch.
- **CLASS:** annotation được giữ trong class file nhưng không nhất thiết có mặt qua reflection runtime.
- **RUNTIME:** annotation có thể được truy cập bằng reflection khi chạy.

Nếu framework runtime cần đọc annotation có retention **RUNTIME**, module chứa annotation phải có mặt ở runtime khi framework thực hiện truy cập. Khai báo **requires static** không làm cho annotation runtime tự xuất hiện nếu JAR đã bị loại khỏi runtime path.

## 8. Optional dependency và ServiceLoader

Nếu mục tiêu là cho phép ứng dụng tự phát hiện một implementation tùy chọn, có thể cân nhắc Java Service Provider Interface (SPI) và **ServiceLoader**.

Một module khai báo service mà nó sử dụng:

~~~java
module com.example.orders {
    uses com.example.orders.spi.OrderObserver;
}
~~~

Module plugin cung cấp implementation:

~~~java
module com.example.metrics {
    requires com.example.orders;

    provides com.example.orders.spi.OrderObserver
        with com.example.metrics.MetricsObserver;
}
~~~

Ứng dụng tìm các provider:

~~~java
ServiceLoader<OrderObserver> observers =
        ServiceLoader.load(OrderObserver.class);

for (OrderObserver observer : observers) {
    observer.onOrderCreated();
}
~~~

Nếu không có provider phù hợp trong cấu hình service, ứng dụng có thể không nhận được implementation nào và tiếp tục hoạt động theo chính sách đã định.

SPI giải quyết bài toán khám phá implementation theo contract. **requires static** giải quyết bài toán dependency module có thể vắng mặt ở runtime. Hai cơ chế có thể bổ trợ nhau, nhưng không thay thế nhau. Nếu module ứng dụng trực tiếp import kiểu từ module optional, nó vẫn cần khai báo quan hệ module phù hợp ở compile time.

Trong ví dụ plugin, module API và module provider được tách riêng. Cách này thường giúp module ứng dụng không cần phụ thuộc trực tiếp vào implementation metrics.

## 9. Khi nào nên dùng requires static?

Có thể cân nhắc **requires static** khi:

- Thư viện chỉ cần cho bước biên dịch, chẳng hạn một số annotation hoặc metadata.
- Tính năng tích hợp là tùy chọn và ứng dụng có thể chạy đúng khi thư viện không hiện diện.
- Module cung cấp API compile-time nhưng runtime không nhất thiết phải sử dụng các kiểu của dependency.
- Một adapter riêng có thể cô lập phần code cần dependency và chỉ được nạp khi module có mặt.

Không nên dùng **requires static** nếu:

- Module là thành phần bắt buộc để xử lý luồng nghiệp vụ chính.
- Các class luôn được nạp hoặc khởi tạo đều cần kiểu từ dependency.
- API public yêu cầu module tiêu thụ phải có dependency ở runtime nhưng cấu hình không đảm bảo điều đó.
- Mục tiêu thực tế chỉ là trì hoãn việc khởi tạo object; khi đó cần thiết kế lazy initialization, không phải thay directive dependency.

Một dependency optional phải optional cả về mặt hành vi ứng dụng. Nếu bỏ JAR khiến ứng dụng không thể hoàn thành chức năng chính, directive static không làm cho dependency đó trở thành optional theo nghĩa nghiệp vụ.

## 10. Lỗi thường gặp

**Compiler báo không tìm thấy module dù dùng requires static**

Static không có nghĩa compile-time optional. Module vẫn phải có mặt trên module path khi biên dịch.

**Ứng dụng khởi chạy được nhưng lỗi NoClassDefFoundError khi dùng tính năng tùy chọn**

Module graph có thể được phân giải khi dependency vắng mặt, nhưng code đang nạp hoặc gọi class phụ thuộc vào thư viện. Cô lập adapter, kiểm tra sự hiện diện của module trước khi nạp và xử lý lỗi liên kết.

**Đổi requires thành requires static làm mất khả năng đọc module ở runtime**

Nếu dependency không có trong runtime configuration, module không được phân giải và không có cạnh đọc tới nó. Nếu dependency hiện diện và được phân giải, quan hệ đọc static vẫn có hiệu lực.

**Dùng requires static cho dependency bắt buộc**

Nếu ứng dụng luôn cần module đó để hoạt động, hãy dùng **requires** để module system phát hiện thiếu dependency ngay khi phân giải.

**Public API dùng kiểu từ dependency optional**

Người tiêu thụ API có thể cần dependency ở compile time và runtime. Xem xét **requires static transitive** nếu cần truyền tiếp khả năng đọc ở compile time, nhưng vẫn phải bảo đảm dependency được cung cấp khi kiểu đó được sử dụng ở runtime.

**Nhầm requires static với ServiceLoader**

Requires static không tự khám phá hoặc khởi tạo provider. Nếu cần phát hiện implementation tùy chọn, hãy thiết kế SPI và dùng ServiceLoader.

## 11. Ghi nhớ

- **requires M** khai báo dependency bắt buộc khi biên dịch và runtime.
- **requires static M** bắt buộc ở compile time nhưng cho phép dependency vắng mặt ở runtime.
- Nếu dependency static hiện diện và được phân giải ở runtime, quan hệ đọc tới nó vẫn có hiệu lực.
- requires static không tự nạp thư viện, không thay thế class bị thiếu và không bảo đảm code tham chiếu trực tiếp dependency sẽ chạy khi thư viện vắng mặt.
- Cô lập phần tích hợp optional trong adapter và chỉ nạp nó khi module cần thiết có mặt.
- **requires static transitive** truyền tiếp khả năng đọc ở compile time nhưng vẫn giữ dependency optional ở runtime.
- Annotation dependency cần được xem xét theo retention policy.
- **ServiceLoader** hỗ trợ khám phá provider tùy chọn; nó giải quyết vấn đề khác với requires static.
- Chỉ dùng static khi ứng dụng thực sự có thể hoạt động đúng khi dependency vắng mặt.

Khi thiết kế module graph, hãy xác định dependency có bắt buộc cho toàn bộ ứng dụng hay chỉ phục vụ một phần tính năng. Dùng **requires** cho dependency cốt lõi và **requires static** cho dependency compile-time hoặc tích hợp runtime tùy chọn. Sau đó kiểm thử cả cấu hình có và không có module đó để bảo đảm tính optional được phản ánh đúng trong hành vi ứng dụng.

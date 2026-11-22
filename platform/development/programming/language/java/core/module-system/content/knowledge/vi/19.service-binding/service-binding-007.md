# Phân biệt service binding với reflection scan

## 1. Hai cơ chế giải quyết hai bài toán khác nhau

Trong Java Module System, **service binding** và **reflection scan** đều có thể giúp ứng dụng tìm implementation ở runtime, nhưng chúng hoạt động theo những quy tắc khác nhau.

**Service binding** dựa trên hợp đồng service được khai báo rõ ràng. Module tiêu thụ khai báo **uses**, module cung cấp khai báo **provides ... with ...**, còn **ServiceLoader** tìm các provider phù hợp. Khi tạo runtime image, **jlink --bind-services** có thể đưa các module provider cần thiết và phụ thuộc của chúng vào image.

**Reflection scan** là cách một ứng dụng hoặc framework dò tìm class theo package, annotation, tên class hoặc metadata. Framework có thể đọc tài nguyên trong JAR/module, tải class, rồi dùng reflection để kiểm tra annotation, constructor, field hoặc method. Đây là cơ chế khám phá do framework triển khai; JPMS không tự hiểu rằng mọi class có annotation nào đó đều là provider cần đưa vào runtime image.

Vì vậy, hai cơ chế không thay thế nhau:

- Service binding phù hợp khi ứng dụng có một service interface và muốn provider tuân theo hợp đồng được khai báo.
- Reflection scan phù hợp khi framework cần tìm nhiều loại class theo quy ước, annotation hoặc cấu hình riêng.
- Một ứng dụng có thể dùng cả hai: ServiceLoader để tìm plugin, reflection để kiểm tra metadata hoặc khởi tạo thành phần sau khi đã tìm thấy.

## 2. ServiceLoader và service binding trong JPMS

Service là một hợp đồng Java, thường được biểu diễn bằng interface hoặc abstract class. Module tiêu thụ biết hợp đồng nhưng không cần phụ thuộc trực tiếp vào từng implementation.

Ví dụ, module API công khai interface:

~~~java
package com.example.spi;

public interface PaymentProvider {
    String name();
    void pay(int amount);
}
~~~

Module chứa interface xuất package để module khác có thể sử dụng:

~~~java
module com.example.payment.api {
    exports com.example.spi;
}
~~~

Module ứng dụng tiêu thụ service khai báo **uses**:

~~~java
module com.example.payment.app {
    requires com.example.payment.api;

    uses com.example.spi.PaymentProvider;
}
~~~

Module provider khai báo implementation bằng **provides ... with ...**:

~~~java
module com.example.payment.card {
    requires com.example.payment.api;

    provides com.example.spi.PaymentProvider
        with com.example.payment.card.CardPaymentProvider;
}
~~~

Class provider triển khai interface:

~~~java
package com.example.payment.card;

import com.example.spi.PaymentProvider;

public class CardPaymentProvider implements PaymentProvider {
    @Override
    public String name() {
        return "card";
    }

    @Override
    public void pay(int amount) {
        System.out.println("Pay by card: " + amount);
    }
}
~~~

Module tiêu thụ có thể tìm provider bằng ServiceLoader:

~~~java
package com.example.payment.app;

import com.example.spi.PaymentProvider;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        ServiceLoader<PaymentProvider> providers =
            ServiceLoader.load(PaymentProvider.class);

        for (PaymentProvider provider : providers) {
            System.out.println(provider.name());
        }
    }
}
~~~

Trong named module, module gọi **ServiceLoader.load** cần khai báo **uses** cho service. Provider module cần khai báo **provides** cho đúng service type. Module provider cũng phải được tìm thấy và phân giải trong module layer đang sử dụng.

ServiceLoader không đi qua mọi package để tìm class có annotation. Nó đọc metadata service đã được khai báo theo quy ước của Java. Nhờ đó, quan hệ giữa service và provider có thể được xác định mà không cần quét toàn bộ classpath.

### Provider trên classpath

Ứng dụng chưa modular vẫn có thể dùng ServiceLoader. Provider trên classpath được khai báo trong file:

~~~text
META-INF/services/com.example.spi.PaymentProvider
~~~

Nội dung file liệt kê tên đầy đủ của class provider, mỗi provider trên một dòng:

~~~text
com.example.payment.card.CardPaymentProvider
com.example.payment.wallet.WalletPaymentProvider
~~~

Đây cũng là metadata service có cấu trúc, không phải reflection scan tổng quát. Với named module, khai báo provider nên được đặt trong **module-info.java** bằng **provides**.

## 3. Service binding khi tạo runtime image

**jlink** tạo runtime image từ các module có thể phân giải trên module path. Tùy chọn **--bind-services** yêu cầu jlink liên kết các module provider service phù hợp cùng các phụ thuộc của chúng.

Ví dụ cấu trúc module:

~~~text
mods/
  com.example.payment.api/
  com.example.payment.app/
  com.example.payment.card/
  com.example.payment.wallet/
~~~

Giả sử module ứng dụng khai báo **uses com.example.spi.PaymentProvider**, còn hai module card và wallet đều khai báo **provides** cho service đó. Có thể tạo image bằng:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.payment.app \
  --bind-services \
  --output payment-runtime
~~~

Ở đây:

- **--module-path** cung cấp module JDK và module ứng dụng.
- **--add-modules** chọn module gốc của ứng dụng.
- **--bind-services** tìm provider cho các service được sử dụng trong module graph và liên kết các module provider cùng phụ thuộc cần thiết.
- **--output** xác định thư mục runtime image.

Service binding có thể làm image chứa thêm module provider mà ứng dụng không liệt kê trực tiếp trong **--add-modules**. Đây là lợi ích quan trọng của việc mô tả service bằng **uses** và **provides**: công cụ có thể suy ra provider từ module metadata.

Có thể kiểm tra module trong image:

~~~bash
payment-runtime/bin/java --list-modules
~~~

Và chạy ứng dụng bằng runtime image:

~~~bash
payment-runtime/bin/java -m com.example.payment.app/com.example.payment.app.Main
~~~

Nếu tạo launcher riêng bằng tùy chọn **--launcher**, có thể chạy ứng dụng qua file launcher trong thư mục **bin** của image.

**--bind-services** chỉ xử lý service provider có thể được xác định qua module metadata và có mặt trên module path của quá trình link. Nó không quét annotation tùy ý, không tìm mọi class có cùng interface, không tải JAR từ mạng và không tự đưa các thư viện classpath tùy ý vào image.

Nếu provider được chọn bằng tên class lấy từ cấu hình, reflection hoặc plugin registry riêng, jlink có thể không biết module đó cần thiết. Khi ấy, phải khai báo module gốc phù hợp qua **--add-modules** hoặc thiết kế lại cơ chế discovery bằng service metadata.

## 4. Reflection scan hoạt động như thế nào?

Reflection scan thường bắt đầu bằng một package hoặc quy ước, ví dụ:

- Tìm mọi class có annotation **@Plugin** trong package **com.example.plugins**.
- Tìm class triển khai một interface cụ thể.
- Đọc metadata của class để đăng ký component.
- Tìm các class được cấu hình bằng tên trong file YAML hoặc properties.
- Quét các thư mục và JAR để xây dựng registry của framework.

Một framework có thể tìm tài nguyên package qua classloader, đọc danh sách entry trong JAR, sử dụng API của module hoặc đọc bytecode bằng thư viện phân tích class. Sau khi phát hiện class, framework có thể tải class bằng **Class.forName**, kiểm tra annotation bằng reflection và gọi constructor hoặc method.

Ví dụ minh họa cách một framework kiểm tra annotation sau khi đã có class:

~~~java
Class<?> type = Class.forName(
    "com.example.plugins.CardPlugin"
);

if (type.isAnnotationPresent(Plugin.class)) {
    System.out.println("Plugin found: " + type.getName());
}
~~~

Đoạn code trên chỉ minh họa bước kiểm tra một class đã biết tên. Một thư viện scanning thực tế còn phải tìm tên class hoặc tài nguyên trước khi có thể gọi **Class.forName**.

Reflection scan thường linh hoạt khi framework hỗ trợ nhiều kiểu extension khác nhau. Tuy nhiên, kết quả phụ thuộc vào phạm vi quét, cách framework liệt kê tài nguyên, classloader, module layer và quyền truy cập mà JPMS cho phép.

## 5. JPMS ảnh hưởng đến reflection scan

Trên classpath truyền thống, nhiều framework giả định rằng có thể liệt kê package và truy cập class tương đối tự do. Khi chuyển sang named module, giả định này có thể không còn đúng.

Cần tách biệt ba bước:

1. **Tìm class:** framework phải nhìn thấy tài nguyên hoặc module chứa class.
2. **Nạp class:** classloader hoặc module layer phải có khả năng nạp class đó.
3. **Truy cập bằng reflection:** framework phải được phép truy cập thành viên mà nó muốn kiểm tra hoặc gọi.

Một class có thể được tìm thấy nhưng framework vẫn không được phép truy cập field hoặc constructor private. Đây là vấn đề đóng gói module, không phải lúc nào cũng là lỗi tìm class.

### exports và opens

**exports** công khai package để module khác truy cập các kiểu public:

~~~java
module com.example.plugins {
    exports com.example.plugins.api;
}
~~~

**opens** cho phép reflection sâu vào package, bao gồm các thành viên không public theo quy tắc của JPMS:

~~~java
module com.example.plugins {
    opens com.example.plugins.model
        to com.example.framework;
}
~~~

Nếu framework cần reflection sâu vào nhiều package, có thể dùng **open module**, nhưng cách này mở toàn bộ package của module cho deep reflection và làm giảm mức đóng gói. Nên ưu tiên mở đúng package và đúng module framework cần truy cập.

**exports** không thay thế **opens** cho deep reflection. Ngược lại, **opens** không làm package trở thành API Java public thông thường để module khác import các kiểu trong package đó.

Nếu framework dùng reflection scan để đọc annotation public hoặc metadata, yêu cầu mở package có thể khác với trường hợp framework gọi private field/method. Cần xem tài liệu của framework để biết chính xác package nào phải **exports** hoặc **opens**.

### Module layer và classloader

Một ứng dụng có thể tạo module layer mới để nạp plugin động. Trong trường hợp này, framework cần tìm module trong đúng layer. API **ServiceLoader.load(layer, Service.class)** cho phép tìm service provider trong một module layer cụ thể.

Reflection scanner cũng cần biết các module và classloader mà nó phải quét. Quét classpath của system classloader không đồng nghĩa đã quét mọi named module trong mọi module layer.

Nếu framework chỉ hỗ trợ classpath scanning, việc đặt thư viện thành named module có thể khiến cơ chế quét không nhìn thấy package như trước. Hãy kiểm tra khả năng hỗ trợ JPMS của framework và cách nó phát hiện module trước khi chuyển đổi.

## 6. So sánh service binding và reflection scan

| Tiêu chí | Service binding / ServiceLoader | Reflection scan |
|---|---|---|
| Cơ sở khám phá | **uses**, **provides**, service metadata | Package, class, annotation, tên class hoặc quy ước |
| Hợp đồng | Service interface hoặc abstract class | Có thể là interface, annotation hoặc quy tắc riêng |
| Khai báo provider | **provides S with P** trong module descriptor; hoặc file META-INF/services trên classpath | Thường dựa vào class hiện diện trong vùng quét và metadata framework |
| Phạm vi tìm kiếm | Provider được khai báo và nhìn thấy trong module layer/classpath tương ứng | Phụ thuộc scanner, classloader, module layer và cấu hình |
| Hỗ trợ jlink | **--bind-services** có thể liên kết provider module | jlink không tự suy ra module chỉ từ annotation hoặc reflection |
| Quyền truy cập | Tuân theo exports và quy tắc provider của ServiceLoader | Có thể cần exports hoặc opens tùy cách reflection |
| Tính tường minh | Cao; provider và consumer khai báo hợp đồng | Linh hoạt hơn nhưng phụ thuộc quy ước framework |
| Phù hợp | SPI, plugin theo hợp đồng, provider chuẩn | Framework scanning, component registry, annotation processing ở runtime |

Điểm khác biệt quan trọng nhất là **service binding có metadata mà JPMS hiểu được**, còn reflection scan là logic do framework tự triển khai. Vì vậy, jlink có thể liên kết provider module theo service graph nhưng không thể suy ra mọi class mà một scanner có thể tìm thấy khi ứng dụng chạy.

## 7. Khi nào nên dùng từng cơ chế?

Dùng **ServiceLoader** khi:

- Ứng dụng định nghĩa một SPI rõ ràng và nhiều module có thể cung cấp implementation.
- Muốn consumer phụ thuộc vào interface thay vì implementation cụ thể.
- Cần để JPMS nhận diện provider và hỗ trợ liên kết provider khi tạo runtime image.
- Muốn có thể thêm hoặc thay provider bằng module khác mà không sửa consumer.

Dùng **reflection scan** khi:

- Framework cần tìm component theo annotation hoặc quy ước package.
- Cần đọc metadata của class để đăng ký controller, entity, serializer hoặc extension.
- Framework có cơ chế scanning đã được thiết kế và kiểm thử cho JPMS.
- Tập class cần phát hiện thay đổi theo cấu hình hoặc plugin registry.

Nếu chỉ cần tìm implementation của một SPI, ServiceLoader thường dễ mô tả và dễ tích hợp với module graph hơn. Nếu cần phát hiện nhiều loại component theo annotation, scanner có thể phù hợp hơn. Một framework cũng có thể dùng ServiceLoader để tìm extension root rồi dùng reflection để đọc cấu hình hoặc metadata của từng extension.

## 8. Kết hợp ServiceLoader với reflection đúng cách

Có thể kết hợp hai cơ chế theo luồng sau:

1. Consumer khai báo **uses** cho service interface.
2. Provider module khai báo **provides** với implementation.
3. ServiceLoader tìm các provider đã đăng ký.
4. Framework nhận instance provider và đọc annotation hoặc metadata public nếu cần.
5. Nếu framework phải truy cập thành viên không public, provider module mở package cụ thể cho module framework bằng **opens ... to**.

Ví dụ consumer:

~~~java
module com.example.host {
    requires com.example.plugin.api;
    uses com.example.plugin.api.Plugin;
}
~~~

Provider:

~~~java
module com.example.plugin.card {
    requires com.example.plugin.api;

    provides com.example.plugin.api.Plugin
        with com.example.plugin.card.CardPlugin;
}
~~~

API service có thể định nghĩa annotation để framework dùng trên implementation:

~~~java
package com.example.plugin.api;

public interface Plugin {
    String id();
}
~~~

Khi cần truy cập sâu vào package implementation, provider có thể khai báo:

~~~java
module com.example.plugin.card {
    requires com.example.plugin.api;

    provides com.example.plugin.api.Plugin
        with com.example.plugin.card.CardPlugin;

    opens com.example.plugin.card
        to com.example.framework;
}
~~~

Chỉ mở package khi framework thực sự cần deep reflection. Nếu framework chỉ gọi phương thức public của interface hoặc implementation, có thể không cần mở package implementation.

## 9. Các lỗi thường gặp khi tạo image có service provider

**Provider không xuất hiện trong ServiceLoader**

Kiểm tra consumer có khai báo **uses**, provider module có khai báo **provides**, service type có cùng module/package và provider có mặt trong module layer đang được tìm kiếm hay không. Nếu dùng classpath, kiểm tra file **META-INF/services** và tên class provider.

**Provider hoạt động trên JDK đầy đủ nhưng mất trong runtime image**

Kiểm tra lệnh jlink có dùng **--bind-services** hay không và service provider có nằm trên module path lúc link hay không. Nếu module provider được chọn bằng cấu hình hoặc reflection thay vì service metadata, thêm module đó vào **--add-modules**.

**Framework không quét được package sau khi modular hóa**

Kiểm tra scanner có hỗ trợ named module, module layer và module path hay không. Cần xác định scanner đang liệt kê tài nguyên bằng classloader hay API module. Một scanner chỉ duyệt classpath có thể bỏ qua named module.

**IllegalAccessException hoặc InaccessibleObjectException**

Kiểm tra module chứa class có xuất package hoặc mở package phù hợp cho module framework hay không. Dùng **exports** cho truy cập public và **opens** cho deep reflection. Nếu chỉ cần một package, hãy mở có mục tiêu thay vì mở toàn module.

**Class được tìm thấy nhưng không nạp được trong image**

Có thể module chứa class chưa được đưa vào image, hoặc một phụ thuộc của class chưa được phân giải. Reflection không tự bảo đảm module được thêm vào runtime image. Xác định module sở hữu class và thêm module đó vào module graph khi cần.

## 10. Checklist lựa chọn và triển khai

- Xác định nhu cầu là tìm provider theo một SPI hay quét component theo annotation.
- Nếu dùng ServiceLoader trong named module, khai báo **uses** ở consumer.
- Khai báo **provides ... with ...** trong provider module.
- Đảm bảo service interface nằm trong package được xuất.
- Nếu dùng **jlink --bind-services**, đặt provider module trên module path và kiểm tra service graph.
- Nếu provider được nạp bằng cấu hình/reflection, thêm module cần thiết vào **--add-modules**.
- Nếu dùng reflection sâu, mở đúng package cho đúng framework module.
- Kiểm tra framework có hỗ trợ module path và module layer.
- Chạy **java --list-modules** trên image để kiểm tra module đã được đóng gói.
- Thử thực tế đường chạy discovery, khởi tạo và sử dụng provider trên runtime image.

## 11. Ghi nhớ

**Service binding** dựa trên metadata service mà JPMS hiểu được. Consumer khai báo **uses**, provider khai báo **provides**, và jlink có thể dùng **--bind-services** để liên kết provider module vào runtime image.

**Reflection scan** do ứng dụng hoặc framework tự thực hiện để tìm class theo package, annotation hoặc quy ước. JPMS có thể giới hạn khả năng nhìn thấy module và truy cập thành viên; framework cần hỗ trợ module path/module layer và có thể cần **exports** hoặc **opens**.

Hãy chọn cơ chế dựa trên hợp đồng discovery của ứng dụng. ServiceLoader là lựa chọn tự nhiên cho SPI có provider khai báo rõ ràng; reflection scan phù hợp với framework cần khám phá component theo metadata. Khi tạo runtime image, luôn kiểm tra module provider và các đường chạy discovery bằng chính image sẽ được triển khai.

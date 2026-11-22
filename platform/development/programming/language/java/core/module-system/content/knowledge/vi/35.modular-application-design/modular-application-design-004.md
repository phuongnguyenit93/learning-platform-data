# Đặt service interface và provider implementation

## 1. Mục tiêu

Khi thiết kế ứng dụng Java modular, một service thường có nhiều implementation khác nhau: lưu file hoặc lưu database, gửi email qua SMTP hoặc API, thanh toán qua nhiều cổng, đọc dữ liệu từ nhiều định dạng. Nếu module sử dụng phụ thuộc trực tiếp vào class implementation, mỗi lần thay provider có thể buộc phải sửa dependency và module descriptor của consumer.

Java Platform Module System (JPMS) hỗ trợ tách ba vai trò:

1. **Service API module** định nghĩa contract mà consumer và provider cùng hiểu.
2. **Consumer module** sử dụng contract và khai báo service usage bằng **uses**.
3. **Provider module** triển khai contract và đăng ký implementation bằng **provides ... with ...**.

Consumer phụ thuộc vào service API. Provider cũng phụ thuộc vào service API. Consumer không cần khai báo requires tới từng provider cụ thể. Runtime có thể tìm implementation phù hợp thông qua **ServiceLoader** khi provider module đã được đưa vào module layer.

Cách tổ chức này giảm coupling, cho phép thay hoặc bổ sung provider theo cấu hình triển khai và giữ implementation detail trong module provider.

## 2. Phân chia trách nhiệm giữa các module

Giả sử ứng dụng cần một service để gửi thông báo:

~~~text
com.acme.notification.api
    com.acme.notification.spi
        NotificationSender
        Notification
        DeliveryResult

com.acme.notification.consumer
    com.acme.notification.app
        ReminderService

com.acme.notification.email
    com.acme.notification.email.internal
        SmtpNotificationSender

com.acme.notification.sms
    com.acme.notification.sms.internal
        SmsNotificationSender
~~~

Quan hệ phụ thuộc:

~~~text
                  +-------------------------------+
                  | com.acme.notification.api    |
                  | NotificationSender            |
                  | Notification / DeliveryResult |
                  +---------------+---------------+
                                  ^
                    +-------------+-------------+
                    |                           |
          +---------+----------+      +---------+---------+
          | consumer module    |      | provider modules  |
          | uses Notification  |      | provides ...      |
          +--------------------+      +-------------------+
~~~

Cả consumer và provider đều biết service contract. Consumer không cần biết class SMTP hoặc SMS nằm ở package nào.

### Service API module

Module API chứa những type cần thiết để gọi service:

- Interface hoặc abstract service type.
- Request/response type và exception thuộc contract.
- Enum hoặc value type cần trao đổi giữa consumer và provider.
- Các annotation hoặc capability type thuộc contract nếu thực sự cần.

Module API nên nhỏ và ổn định. Không đặt implementation SMTP, JDBC, HTTP client, framework hoặc cấu hình môi trường vào module API chỉ để consumer có thể gọi interface.

### Consumer module

Consumer chứa logic nghiệp vụ cần sử dụng service. Nó:

- Khai báo requires tới service API module.
- Khai báo uses cho service type.
- Dùng ServiceLoader để phát hiện provider.
- Chọn provider theo quy tắc của ứng dụng nếu có nhiều implementation.
- Xử lý trường hợp không có provider hoặc provider khởi tạo thất bại.

Consumer không cần import hoặc gọi trực tiếp implementation class.

### Provider module

Provider chứa implementation cụ thể và dependency riêng của nó. Nó:

- Khai báo requires tới service API module.
- Khai báo provides cho service type.
- Đặt implementation trong package nội bộ.
- Không export package implementation nếu module khác không cần truy cập trực tiếp.
- Quản lý cấu hình, kết nối và tài nguyên riêng của provider.

Provider có thể phụ thuộc vào thư viện SMTP, SDK thanh toán hoặc database driver mà consumer không cần biết.

## 3. Định nghĩa service contract trong API module

Module descriptor của API:

~~~java
module com.acme.notification.api {
    exports com.acme.notification.spi;
}
~~~

Service interface:

~~~java
package com.acme.notification.spi;

public interface NotificationSender {
    String providerId();

    DeliveryResult send(Notification notification);
}
~~~

Các type được trao đổi qua interface cũng thuộc API module:

~~~java
package com.acme.notification.spi;

public record Notification(
        String recipient,
        String subject,
        String body) {
}
~~~

~~~java
package com.acme.notification.spi;

public record DeliveryResult(
        String messageId,
        boolean accepted) {
}
~~~

Vì các type này nằm trong package được export, consumer và provider có thể tham chiếu chúng khi khai báo dependency tới API module.

### Thiết kế contract ổn định

Service interface là ranh giới giữa hai phía. Hãy thiết kế contract theo nghiệp vụ thay vì để lộ chi tiết của một provider:

- Dùng tên khái niệm như NotificationSender hoặc PaymentGateway thay vì SmtpSender nếu có nhiều loại provider.
- Đưa dữ liệu cần thiết vào request/response type có ý nghĩa rõ ràng.
- Không trả về class thuộc thư viện riêng của provider.
- Không yêu cầu consumer truyền đối tượng kết nối hoặc cấu hình nội bộ của implementation.
- Xác định rõ lỗi có thể xảy ra, tính đồng bộ/bất đồng bộ và timeout nếu service cần.
- Giữ thay đổi tương thích khi thêm field hoặc mở rộng contract.

Nếu consumer phải import một class của SDK SMTP chỉ để gọi NotificationSender, abstraction đã bị rò rỉ implementation detail.

### Không đặt implementation trong API module

API module không nên chứa:

~~~java
public final class SmtpNotificationSender
        implements NotificationSender {
    // SMTP implementation
}
~~~

Nếu đặt class này trong API module, consumer có thể bị kéo theo dependency của SMTP và ranh giới service không còn rõ. Implementation nên thuộc provider module riêng.

## 4. Consumer khai báo uses

Module descriptor của consumer:

~~~java
module com.acme.reminder {
    requires com.acme.notification.api;

    uses com.acme.notification.spi.NotificationSender;
}
~~~

Hai directive có mục đích khác nhau:

- **requires** cho phép consumer đọc service API module và tham chiếu các type trong package được export.
- **uses** khai báo consumer sử dụng service type để module system và ServiceLoader biết service dependence của consumer.

Consumer code:

~~~java
package com.acme.reminder.app;

import com.acme.notification.spi.Notification;
import com.acme.notification.spi.NotificationSender;
import java.util.ServiceLoader;

public final class ReminderService {

    public void sendReminder(String email, String body) {
        ServiceLoader<NotificationSender> loader =
                ServiceLoader.load(NotificationSender.class);

        NotificationSender sender = loader.findFirst()
                .orElseThrow(() -> new IllegalStateException(
                        "No NotificationSender provider is available"));

        sender.send(new Notification(
                email,
                "Reminder",
                body));
    }
}
~~~

Đối với code chạy trong named module, module chứa code gọi ServiceLoader phải khai báo **uses** cho service type. Nếu thiếu khai báo, ServiceLoader có thể ném ServiceConfigurationError khi thực hiện việc tìm provider.

Nếu chỉ chạy trên classpath trong unnamed module, quy tắc khai báo uses của named module không áp dụng theo cùng cách. Tuy nhiên, nên giữ thiết kế module rõ ràng khi ứng dụng sử dụng JPMS.

### Không requires provider cụ thể trong consumer

Consumer không cần viết:

~~~java
module com.acme.reminder {
    requires com.acme.notification.api;
    requires com.acme.notification.email;
}
~~~

Nếu consumer khai báo requires tới từng provider, nó đã phụ thuộc vào implementation module. Khi đổi từ email sang SMS, module descriptor và dependency graph của consumer lại phải thay đổi.

Thiết kế service-based thường chỉ cần:

~~~java
module com.acme.reminder {
    requires com.acme.notification.api;
    uses com.acme.notification.spi.NotificationSender;
}
~~~

Provider được đưa vào runtime configuration hoặc module layer theo nhu cầu triển khai.

## 5. Provider module đăng ký implementation bằng provides

Module email có thể triển khai service:

~~~java
module com.acme.notification.email {
    requires com.acme.notification.api;

    provides com.acme.notification.spi.NotificationSender
        with com.acme.notification.email.internal.SmtpNotificationSender;
}
~~~

Implementation:

~~~java
package com.acme.notification.email.internal;

import com.acme.notification.spi.DeliveryResult;
import com.acme.notification.spi.Notification;
import com.acme.notification.spi.NotificationSender;

public final class SmtpNotificationSender
        implements NotificationSender {

    public SmtpNotificationSender() {
    }

    @Override
    public String providerId() {
        return "smtp";
    }

    @Override
    public DeliveryResult send(Notification notification) {
        // Gửi notification qua SMTP.
        return new DeliveryResult("smtp-message-id", true);
    }
}
~~~

Với provider class theo kiểu constructor, implementation cần là public và có public no-argument constructor để ServiceLoader tạo instance.

Package implementation không cần export chỉ vì được khai báo trong provides. ServiceLoader có thể khởi tạo provider theo module descriptor. Consumer chỉ cần nhìn thấy service type trong API module.

Điều này giúp giữ implementation package ở mức encapsulated:

~~~java
module com.acme.notification.email {
    requires com.acme.notification.api;

    provides com.acme.notification.spi.NotificationSender
        with com.acme.notification.email.internal.SmtpNotificationSender;
}
~~~

Không cần thêm:

~~~java
exports com.acme.notification.email.internal;
~~~

Chỉ export package provider nếu có một API độc lập khác thực sự cần truy cập trực tiếp implementation đó.

### Provider method thay cho implementation constructor

Named module cũng có thể khai báo một provider class với public static method tên **provider** trả về service type:

~~~java
package com.acme.notification.email.internal;

import com.acme.notification.spi.NotificationSender;

public final class SmtpSenderProvider {

    private SmtpSenderProvider() {
    }

    public static NotificationSender provider() {
        return new SmtpNotificationSender(loadConfiguration());
    }

    private static SmtpConfiguration loadConfiguration() {
        return new SmtpConfiguration();
    }
}
~~~

Module descriptor khi đó dùng provider class:

~~~java
provides com.acme.notification.spi.NotificationSender
    with com.acme.notification.email.internal.SmtpSenderProvider;
~~~

Provider method hữu ích khi implementation cần khởi tạo qua factory, cấu hình hoặc dependency nội bộ. Provider class không cần trực tiếp implement service nếu nó cung cấp method hợp lệ theo ServiceLoader provider method contract.

Dù dùng constructor hay provider method, consumer vẫn nhận được service type đã công khai trong API module.

## 6. Nhiều provider có thể triển khai cùng một service

Module SMS có thể triển khai cùng interface:

~~~java
module com.acme.notification.sms {
    requires com.acme.notification.api;

    provides com.acme.notification.spi.NotificationSender
        with com.acme.notification.sms.internal.SmsNotificationSender;
}
~~~

Khi cả email và SMS provider được đưa vào cùng module layer, ServiceLoader có thể phát hiện nhiều implementation.

Consumer:

~~~java
ServiceLoader<NotificationSender> loader =
        ServiceLoader.load(NotificationSender.class);

for (NotificationSender sender : loader) {
    System.out.println(sender.providerId());
}
~~~

Không được dựa vào thứ tự provider được trả về để biểu diễn độ ưu tiên nghiệp vụ. Nếu cần chọn provider, hãy xác định quy tắc tường minh:

- Theo cấu hình triển khai.
- Theo loại notification hoặc recipient.
- Theo capability mà provider công bố.
- Theo policy fallback khi provider chính không khả dụng.
- Theo tenant hoặc vùng triển khai nếu đó là yêu cầu nghiệp vụ.

Ví dụ chọn theo cấu hình:

~~~java
String selectedProviderId = configuration.notificationProvider();

NotificationSender sender = ServiceLoader
        .load(NotificationSender.class)
        .stream()
        .map(ServiceLoader.Provider::get)
        .filter(candidate ->
                candidate.providerId().equals(selectedProviderId))
        .findFirst()
        .orElseThrow(() -> new IllegalStateException(
                "Configured notification provider is unavailable"));
~~~

Nếu hệ thống yêu cầu đúng một provider, hãy kiểm tra số lượng provider thay vì ngầm chọn provider đầu tiên. Nếu nhiều provider là hợp lệ, thiết kế API để ứng dụng quyết định rõ provider nào được sử dụng.

## 7. ServiceLoader tìm provider ở đâu?

ServiceLoader không tự tải mọi JAR nằm trên ổ đĩa. Provider phải hiện diện trong môi trường tìm kiếm phù hợp và được module system hoặc class loader phát hiện.

Với named modules:

- Consumer khai báo uses.
- Provider module khai báo provides.
- Provider module phải được resolve vào module layer mà ServiceLoader đang tìm kiếm.
- Module provider phải đọc được service API module và service type phải tương thích.

Với ứng dụng chạy trên module path, việc chỉ đặt provider JAR trên module path không đồng nghĩa provider chắc chắn đã nằm trong module graph. Cần bảo đảm module provider được đưa vào configuration/layer, chẳng hạn bằng cách thêm module provider vào root modules hoặc sử dụng cơ chế service binding phù hợp.

Ví dụ khi chạy ứng dụng và chọn provider tường minh:

~~~text
java
  --module-path mods
  --add-modules com.acme.notification.email
  --module com.acme.reminder/com.acme.reminder.app.Main
~~~

Trong ứng dụng lớn, danh sách root modules và cách tạo layer nên được quản lý bởi build/deployment configuration. Khi tạo custom runtime image bằng jlink, có thể thêm provider module rõ ràng bằng --add-modules hoặc bật --bind-services để liên kết provider cho service usage của các module đã resolve.

### Tìm provider trong một ModuleLayer cụ thể

Nếu ứng dụng tạo module layer riêng để nạp plugin, có thể tìm provider trong layer đó:

~~~java
ServiceLoader<NotificationSender> loader =
        ServiceLoader.load(pluginLayer, NotificationSender.class);
~~~

Overload nhận ModuleLayer giúp xác định phạm vi tìm kiếm provider trong layer được chọn và các parent layer của nó theo hợp đồng API.

Cách này hữu ích khi một ứng dụng có nhiều nhóm plugin hoặc nhiều cấu hình provider độc lập. Cần bảo đảm service API module được chia sẻ theo cách phù hợp giữa consumer và layer chứa provider.

### Provider trên classpath

Trong cách đóng gói classpath truyền thống, provider thường được đăng ký bằng file:

~~~text
META-INF/services/com.acme.notification.spi.NotificationSender
~~~

Nội dung file chứa tên đầy đủ của provider class, mỗi provider một dòng:

~~~text
com.acme.notification.email.internal.SmtpNotificationSender
~~~

Cách đăng ký này thuộc cơ chế classpath/service configuration. Với named module, nên khai báo provider bằng **provides ... with ...** trong module-info.java. Đừng nhầm hai cơ chế đăng ký hoặc giả định rằng một provider class được khai báo theo một cách sẽ tự động được tìm thấy trong mọi loại module layer.

## 8. Thiết kế service API và provider implementation

### Giữ service contract độc lập

Service API nên chứa các type mà cả consumer và provider cần. Tránh để interface phụ thuộc vào provider module:

~~~text
notification.api
    NotificationSender
    Notification
    DeliveryResult

notification.email
    SmtpNotificationSender
    SmtpConfiguration
    SmtpClient

notification.sms
    SmsNotificationSender
    SmsConfiguration
    SmsClient
~~~

Không để NotificationSender trả về SmtpMessage hoặc nhận SmtpSession. Nếu contract cần biểu diễn kết quả gửi, định nghĩa DeliveryResult trong API module.

### Giữ dependency của provider ở phía provider

Provider email có thể cần SMTP client library; provider SMS có thể cần SDK riêng. Chỉ provider module khai báo dependency đó.

~~~java
module com.acme.notification.email {
    requires com.acme.notification.api;
    requires com.acme.smtp.client;

    provides com.acme.notification.spi.NotificationSender
        with com.acme.notification.email.internal.SmtpNotificationSender;
}
~~~

Consumer không cần đọc com.acme.smtp.client và không cần biết implementation dùng thư viện nào.

### Không biến service API thành một module khổng lồ

Không gom mọi interface của toàn hệ thống vào một module chung chỉ vì các module đều có thể phụ thuộc vào nó. API module nên phản ánh ranh giới contract có ý nghĩa và có vòng đời versioning phù hợp.

Nếu service không liên quan hoặc thay đổi theo nhịp khác nhau, hãy cân nhắc tách API module. Tránh tạo dependency graph quá rộng khiến một thay đổi nhỏ trong contract ảnh hưởng tới toàn ứng dụng.

### Quản lý lifecycle và tài nguyên của provider

ServiceLoader tạo provider khi consumer duyệt hoặc lấy instance. Provider có thể mở connection pool, client hoặc thread. Hãy quyết định rõ:

- Instance provider có được dùng lâu dài hay tạo mới theo lần gọi?
- Ai đóng resource khi ứng dụng shutdown?
- Provider có thread-safe không?
- Cấu hình được đọc ở thời điểm khởi tạo hay mỗi request?
- Provider lỗi khi khởi tạo được báo cáo và xử lý như thế nào?

ServiceLoader không phải dependency injection container đầy đủ và không tự quản lý toàn bộ lifecycle của resource do provider mở. Nếu provider cần lifecycle phức tạp, hãy thiết kế contract khởi tạo/đóng rõ ràng hoặc tích hợp với application container.

## 9. Lỗi thường gặp

### Consumer requires trực tiếp provider

Nếu consumer khai báo requires com.acme.notification.email, consumer bị gắn với implementation cụ thể. Việc thay provider có thể buộc phải sửa descriptor và dependency.

Cách xử lý: consumer requires service API và khai báo uses. Provider module requires API và khai báo provides.

### Quên exports package service API

Consumer và provider không thể tham chiếu service interface nếu package chứa interface không được export phù hợp.

Cách xử lý: export package contract từ API module:

~~~java
module com.acme.notification.api {
    exports com.acme.notification.spi;
}
~~~

### Quên uses trong consumer module

Named module gọi ServiceLoader nhưng module descriptor không khai báo uses cho service type.

Cách xử lý: thêm uses cho đúng service interface trong module-info.java của consumer.

### Quên provides trong provider module

Implementation class có mặt trên module path nhưng module descriptor không đăng ký provider.

Cách xử lý: thêm provides ... with ... và kiểm tra provider type, constructor hoặc provider method.

### Provider không nằm trong module layer

Provider module có trên module path nhưng không được resolve vào layer đang tìm kiếm.

Cách xử lý: kiểm tra root modules, module finder, configuration resolution, parent layer và lựa chọn service binding. Có thể thêm provider module tường minh hoặc dùng resolveAndBind khi muốn liên kết service provider.

### Export package implementation không cần thiết

Nhiều dự án export package provider chỉ để ServiceLoader có thể tạo instance. Điều này làm lộ implementation package thành API.

Cách xử lý: giữ package implementation không export; đăng ký provider trong module descriptor.

### Chọn provider đầu tiên theo thứ tự tìm thấy

Thứ tự phát hiện provider không phải policy ưu tiên nghiệp vụ ổn định.

Cách xử lý: chọn theo providerId/capability/cấu hình hoặc yêu cầu đúng số lượng provider và từ chối cấu hình mơ hồ.

### Service contract chứa type riêng của provider

Consumer phải phụ thuộc vào thư viện hoặc class của implementation để sử dụng API.

Cách xử lý: chuyển type trao đổi cần thiết vào service API module và giữ type riêng ở provider module.

### Tin rằng ServiceLoader cách ly provider không đáng tin cậy

Provider được nạp và chạy trong cùng process với ứng dụng. ServiceLoader không tạo sandbox.

Cách xử lý: chỉ nạp provider đáng tin cậy. Nếu phải chạy plugin không đáng tin cậy, cân nhắc process/container riêng và giao thức IPC có kiểm soát.

## 10. Ví dụ hoàn chỉnh về ba module

### API module

module-info.java:

~~~java
module com.acme.codec.api {
    exports com.acme.codec;
}
~~~

Service type:

~~~java
package com.acme.codec;

public interface Codec {
    String format();
    byte[] encode(String input);
}
~~~

### Consumer module

module-info.java:

~~~java
module com.acme.document {
    requires com.acme.codec.api;

    uses com.acme.codec.Codec;
}
~~~

Consumer code:

~~~java
package com.acme.document;

import com.acme.codec.Codec;
import java.util.ServiceLoader;

public final class DocumentEncoder {

    public byte[] encode(String format, String content) {
        Codec codec = ServiceLoader.load(Codec.class)
                .stream()
                .map(ServiceLoader.Provider::get)
                .filter(candidate ->
                        candidate.format().equalsIgnoreCase(format))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException(
                        "Unsupported format: " + format));

        return codec.encode(content);
    }
}
~~~

### Provider module

module-info.java:

~~~java
module com.acme.codec.json {
    requires com.acme.codec.api;

    provides com.acme.codec.Codec
        with com.acme.codec.json.internal.JsonCodec;
}
~~~

Implementation:

~~~java
package com.acme.codec.json.internal;

import com.acme.codec.Codec;

public final class JsonCodec implements Codec {

    public JsonCodec() {
    }

    @Override
    public String format() {
        return "json";
    }

    @Override
    public byte[] encode(String input) {
        return input.getBytes(java.nio.charset.StandardCharsets.UTF_8);
    }
}
~~~

Module consumer không cần requires com.acme.codec.json. Module provider cũng không cần export package com.acme.codec.json.internal. Cả hai cùng phụ thuộc vào com.acme.codec.api.

### Chạy với provider đã được chọn

Một cách triển khai đơn giản là đưa provider vào root modules:

~~~text
java
  --module-path mods
  --add-modules com.acme.codec.json
  --module com.acme.document/com.acme.document.Main
~~~

Nếu muốn thêm provider khác, đưa module provider tương ứng vào module graph. Consumer tiếp tục dùng cùng contract.

## 11. Kiểm thử service API và provider

Nên có các loại kiểm thử sau:

### Kiểm thử contract

- Provider nhận đúng request type và trả về response type hợp lệ.
- Provider thực hiện đúng semantics của interface.
- Error mapping, timeout và validation tuân theo contract.
- Không để type nội bộ của provider rò rỉ qua API.

### Kiểm thử consumer

- Consumer hoạt động khi có provider hợp lệ.
- Consumer xử lý khi không có provider.
- Consumer chọn đúng provider theo cấu hình/capability.
- Consumer không phụ thuộc vào thứ tự ServiceLoader trả về.
- Consumer xử lý ServiceConfigurationError hoặc lỗi khởi tạo theo chính sách phù hợp.

### Kiểm thử module integration

- API module export đúng package.
- Consumer module có requires và uses.
- Provider module có requires và provides.
- Provider implementation package không cần export vẫn được ServiceLoader phát hiện.
- Provider module thực sự có mặt trong module layer/runtime image.
- Chạy test bằng module path hoặc runtime image gần với môi trường triển khai.

### Kiểm thử nhiều provider

- Khi có hai provider, lựa chọn có xác định và tái lập được không?
- Khi provider được cấu hình không tồn tại, lỗi có rõ ràng không?
- Khi provider chính lỗi, fallback có được phép theo policy không?
- Có kiểm tra duplicate provider ID hoặc cấu hình mâu thuẫn không?

## 12. Checklist thiết kế

- Service contract có nằm trong API module độc lập không?
- API module chỉ chứa type cần thiết cho consumer và provider không?
- Package chứa service interface đã được export chưa?
- Consumer module đã requires API module và khai báo uses chưa?
- Provider module đã requires API module và khai báo provides chưa?
- Provider implementation có public no-argument constructor hoặc provider method hợp lệ không?
- Package implementation có thể giữ không export không?
- Consumer có tránh requires trực tiếp provider module không?
- Provider module có được resolve vào module layer thực tế không?
- Có nhiều provider thì policy chọn provider đã rõ ràng chưa?
- Contract có tránh type phụ thuộc thư viện riêng của provider không?
- Lifecycle, resource, thread safety và lỗi khởi tạo của provider đã được xử lý chưa?
- Có kiểm thử trường hợp không provider, nhiều provider và provider lỗi không?
- Provider có phải code đáng tin cậy trong cùng process không?

**Ghi nhớ:** Đặt service interface trong API module được export; consumer khai báo **requires + uses**; provider khai báo **requires + provides**. Consumer phụ thuộc vào contract, còn provider chịu trách nhiệm implementation và dependency riêng. ServiceLoader nối hai phía tại runtime khi provider module đã được đưa vào module layer phù hợp.

## Tài liệu tham khảo

- Oracle Java SE 21 API — ServiceLoader: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html
- Java Language Specification, Java SE 21 — Service Providers and Module Declarations: https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html
- Oracle Java SE 21 — The java Command, module selection and module path: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- Oracle Java SE 21 API — Configuration.resolveAndBind: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/Configuration.html
- OpenJDK JEP 261 — Module System: https://openjdk.org/jeps/261

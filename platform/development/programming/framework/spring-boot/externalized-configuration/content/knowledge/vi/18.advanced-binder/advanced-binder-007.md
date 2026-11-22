# Tùy biến quá trình bằng BindHandler trong Spring Boot

Trong Spring Boot, `@ConfigurationProperties` và `Binder` giúp chuyển các thuộc tính từ `Environment` thành object Java có kiểu. Khi một ứng dụng lớn cần **quan sát, xác thực bổ sung, kiểm soát lỗi hoặc theo dõi quá trình bind**, đôi khi việc chỉ khai báo các field/record component là chưa đủ.

Giao diện **`org.springframework.boot.context.properties.bind.BindHandler`** cung cấp các callback để can thiệp vào từng giai đoạn binding. Spring Boot cũng có `AbstractBindHandler` để xây dựng handler theo kiểu *decorator*: gắn thêm hành vi mới nhưng vẫn chuyển tiếp callback đến handler cha, giữ những chức năng hiện có.

Bài này sử dụng **Spring Boot 3.3.x và Java 21**. Nội dung trình bày:

- Khi nào cần `BindHandler` và khi nào chỉ cần `@ConfigurationProperties` hoặc Bean Validation.
- Vai trò của `onStart`, `onSuccess`, `onCreate`, `onFailure` và `onFinish`.
- Cách viết handler tùy chỉnh dựa trên `AbstractBindHandler`.
- Cách sử dụng handler trong một lần gọi `Binder.bind(...)`.
- Cách áp dụng cho cơ chế bind `@ConfigurationProperties` qua `ConfigurationPropertiesBindHandlerAdvisor`.
- Cách phối hợp với handler có sẵn, kiểm thử và những rủi ro khi thay đổi dữ liệu hoặc nuốt lỗi.

## 1. BindHandler nằm ở đâu trong luồng nạp cấu hình?

Giả sử file `src/main/resources/application.yml`:

~~~yaml
app:
  client:
    endpoint: https://api.example.org
    connect-timeout: 3s
    max-connections: 12
    enabled: true
~~~

Và lớp cấu hình:

~~~java
package com.example.configdemo.config;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        URI endpoint,
        Duration connectTimeout,
        int maxConnections,
        boolean enabled) {
}
~~~

Spring Boot đọc các nguồn cấu hình, lựa chọn giá trị theo thứ tự ưu tiên, chuyển chúng sang `URI`, `Duration`, `int`, `boolean` rồi tạo một `ClientProperties`.

`BindHandler` là một điểm mở rộng của **Binder**. Nó được gọi trong quá trình Binder xử lý phần tử đích, chứ **không phải một loại `PropertySource` mới** và cũng không làm thay đổi cơ chế nạp file YAML ở giai đoạn Config Data.

Sơ đồ khái niệm:

~~~text
application.yml / environment / CLI / imported Config Data
                           |
                           v
                      Environment
                           |
                           v
               Binder.bind(prefix, type, handler)
                           |
             +-------------+--------------+
             |         BindHandler         |
             | onStart / onSuccess         |
             | onCreate / onFailure        |
             | onFinish                    |
             +-------------+--------------+
                           |
                           v
               ClientProperties object
                           |
                           v
                      Service
~~~

Các callback có thể được gọi cho **nhiều phần tử**: nhóm ở cấp root, thuộc tính con, collection item hoặc cấu trúc lồng nhau. Một callback không nhất thiết tương ứng duy nhất một lần cho cả object.

## 2. Khi nào nên tùy biến bằng BindHandler?

Một số tình huống phù hợp:

1. **Quan sát việc bind:** ghi nhận tên property nào được xử lý hoặc thành công, không log giá trị nhạy cảm.
2. **Chẩn đoán lỗi:** bổ sung ngữ cảnh tên property khi conversion hoặc bind thất bại.
3. **Kiểm soát kết quả:** thực hiện một quy tắc rất cụ thể sau khi một property được bind thành công.
4. **Tùy biến chính sách lỗi:** chọn cách xử lý một số lỗi binding đã biết và an toàn, nhưng phải tránh che giấu cấu hình sai.
5. **Áp dụng chính sách cho nhiều bean:** trang bị handler vào chuỗi binding do Spring Boot quản lý bằng một advisor.
6. **Theo dõi property đã dùng:** kết hợp handler có sẵn để thu thập thông tin trong phạm vi hợp lệ.

`BindHandler` thường **không phải lựa chọn đầu tiên** nếu mục tiêu chỉ là:

- Khai báo giá trị cấu hình: dùng `application.yml`, `application.properties` hoặc biến môi trường.
- Chuyển kiểu chuẩn: Binder đã hỗ trợ số, boolean, enum, `Duration`, `DataSize`, `URI`...
- Chuyển một String sang kiểu riêng: dùng `Converter` được đánh dấu `@ConfigurationPropertiesBinding` khi thích hợp.
- Kiểm tra `maxConnections >= 1`: ưu tiên Bean Validation (`@Min`, `@NotNull`...).
- Đặt giá trị mặc định cho record: dùng `@DefaultValue` hoặc cấu hình theo môi trường.
- Chọn file theo profile: dùng cơ chế `spring.profiles.active`, `spring.config.import` và Config Data.

Handler mạnh vì có thể can thiệp sâu vào vòng đời binding. Chính vì vậy, hãy chọn phạm vi tác động nhỏ và dễ kiểm soát.

## 3. API BindHandler: các callback chính

Package:

~~~java
import org.springframework.boot.context.properties.bind.BindHandler;
~~~

Trong Spring Boot 3.3, giao diện này có các phương thức callback:

~~~java
<T> Bindable<T> onStart(
        ConfigurationPropertyName name,
        Bindable<T> target,
        BindContext context);

Object onSuccess(
        ConfigurationPropertyName name,
        Bindable<?> target,
        BindContext context,
        Object result);

Object onCreate(
        ConfigurationPropertyName name,
        Bindable<?> target,
        BindContext context,
        Object result);

Object onFailure(
        ConfigurationPropertyName name,
        Bindable<?> target,
        BindContext context,
        Exception error) throws Exception;

void onFinish(
        ConfigurationPropertyName name,
        Bindable<?> target,
        BindContext context,
        Object result) throws Exception;
~~~

Đây là **chữ ký khái niệm**; trong interface các phương thức là default method. `BindHandler.DEFAULT` là handler mặc định không thêm hành vi đặc biệt.

### 3.1. onStart — trước khi bind một phần tử

`onStart` được gọi khi Binder bắt đầu xử lý một phần tử, trước khi xác định kết quả. Nó nhận `name`, `target` và `context`.

Kết quả trả về là một `Bindable<T>` đại diện cho target cần dùng tiếp. Nó **có thể được thay đổi** nếu handler có lý do rất cụ thể. Việc trả về `null` có ý nghĩa đặc biệt và có thể dừng việc bind phần tử; không tùy tiện trả null chỉ để “bỏ qua log”.

### 3.2. onSuccess — sau khi có kết quả bind thành công

`onSuccess` nhận thêm `result`. Handler có thể:

- Ghi nhận tên property đã bind thành công.
- Kiểm tra kết quả cuối cùng theo chính sách cụ thể.
- Trong trường hợp nâng cao, thay kết quả trả về bằng một object tương thích.

Nếu tự ý trả một kiểu khác với `target`, quá trình tạo object cha có thể lỗi hoặc dữ liệu bị biến đổi ngoài dự kiến. Với handler quan sát, **trả kết quả từ `super.onSuccess(...)`** để giữ chuỗi callback của handler cha.

### 3.3. onCreate — tạo object dù chưa có dữ liệu bind

`onCreate` được gọi khi một phần tử kết thúc với kết quả **không bind được**, nhưng một instance mới đã được tạo và chuẩn bị được trả về. Kết quả truyền vào không null; handler có thể kiểm tra hoặc thay instance theo hợp đồng API.

Đừng nhầm `onCreate` với `onSuccess`. `onCreate` không có nghĩa property đã xuất hiện trong Environment; nó mô tả đường tạo object mặc dù không nhận dữ liệu cấu hình cho phần tử tương ứng.

### 3.4. onFailure — khi binding thất bại

`onFailure` nhận exception gốc của quá trình bind, kể cả lỗi phát sinh từ một số callback xử lý kết quả. Handler có thể:

- Ghi thêm ngữ cảnh.
- Chuyển tiếp lỗi.
- Trong trường hợp đặc biệt, chọn một kết quả thay thế hoặc bỏ qua lỗi.

**Mặc định nên giữ lỗi.** Việc âm thầm trả null hay giá trị dự phòng có thể khiến ứng dụng khởi động với cấu hình sai, đặc biệt nguy hiểm với timeout, quyền truy cập, endpoint hoặc secret.

### 3.5. onFinish — kết thúc một phần tử

`onFinish` được gọi khi binding hoàn thành với một kết quả đã bind hoặc chưa bind. `result` có thể null. Theo tài liệu Spring Boot 3.3, callback này **không được gọi khi quá trình binding thất bại**, kể cả trường hợp `onFailure` lựa chọn trả về một kết quả thay thế.

Đừng hiểu `onFinish` như khối `finally` của Java chạy cho mọi đường đi. Nếu cần thống kê cả lỗi, hãy quan sát `onFailure` riêng.

### Bảng tóm tắt

| Callback | Thời điểm | Giá trị trả về | Cần lưu ý |
| --- | --- | --- | --- |
| `onStart` | Trước xử lý phần tử | `Bindable<T>` hoặc null | Có thể thay target hoặc dừng bind |
| `onSuccess` | Bind thành công | `Object` | Có thể thay đổi kết quả, cần giữ đúng kiểu |
| `onCreate` | Không bind nhưng tạo instance | `Object` | Không đồng nghĩa property tồn tại |
| `onFailure` | Có exception trong bind | `Object` hoặc ném exception | Không nên vô tình nuốt lỗi |
| `onFinish` | Kết thúc thành công hoặc unbound | `void` | Không chạy trên đường lỗi |

## 4. Các đối tượng truyền vào callback

### ConfigurationPropertyName

~~~java
import org.springframework.boot.context.properties.source.ConfigurationPropertyName;
~~~

Đây là tên thuộc tính ở dạng canonical của Spring Boot, ví dụ:

~~~text
app.client
app.client.endpoint
app.client.connect-timeout
app.client.max-connections
~~~

Có thể dùng `name.toString()` để xác định phần tử đang được xử lý. Với collection hoặc Map, đường tên có thể chứa index/key; không nên giả định chỉ có các field đơn giản.

### Bindable<T>

~~~java
import org.springframework.boot.context.properties.bind.Bindable;
~~~

`Bindable` mô tả target mà Binder đang thao tác, gồm thông tin kiểu và một số metadata về cách binding. Trong lời gọi thủ công, có thể tạo:

~~~java
Bindable.of(ClientProperties.class)
~~~

Cho cấu trúc generic, sử dụng `Bindable.listOf(...)`, `Bindable.mapOf(...)` hoặc `Bindable.of(ResolvableType)` theo nhu cầu API. Đừng đánh mất thông tin generic nếu cần bind `List<ClientSettings>` hay `Map<String, Endpoint>`.

### BindContext

~~~java
import org.springframework.boot.context.properties.bind.BindContext;
~~~

`BindContext` chứa thông tin ngữ cảnh trong khi binding, ví dụ thông tin cấu hình property hiện tại và độ sâu trong cây bind. Nó **không phải một Spring ApplicationContext** và không nên dùng để thực thi nghiệp vụ, truy vấn database hoặc gọi mạng trong callback.

Có thể dùng thông tin trong context để log/chẩn đoán nhưng cần kiểm tra null và không lộ giá trị của property chứa secret.

### result và error

`result` trong `onSuccess` là một object đã bind thành công, không phải luôn luôn String nguyên bản. Ví dụ có thể là `Integer`, `Duration`, `URI`, một record hoặc collection.

`error` trong `onFailure` là exception liên quan phần tử đang bind. Để tìm lỗi, nên ghi tên property, loại exception và thông tin chẩn đoán tối thiểu; đừng tự động log giá trị nguồn vì nó có thể là token hoặc password.

## 5. Viết handler quan sát bằng AbstractBindHandler

`AbstractBindHandler` là lớp nền thuận tiện khi chỉ muốn thêm hành vi ở một vài callback:

~~~java
import org.springframework.boot.context.properties.bind.AbstractBindHandler;
~~~

Lớp này hỗ trợ constructor nhận một `BindHandler parent` để tạo chuỗi decorator. Ví dụ một handler ghi nhận tên các thuộc tính trong nhóm `app.client`:

~~~java
package com.example.configdemo.bind;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.boot.context.properties.bind.AbstractBindHandler;
import org.springframework.boot.context.properties.bind.BindContext;
import org.springframework.boot.context.properties.bind.BindHandler;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.source.ConfigurationPropertyName;

public final class ClientTraceBindHandler extends AbstractBindHandler {

    private static final Logger log =
            LoggerFactory.getLogger(ClientTraceBindHandler.class);

    public ClientTraceBindHandler(BindHandler parent) {
        super(parent);
    }

    @Override
    public <T> Bindable<T> onStart(
            ConfigurationPropertyName name,
            Bindable<T> target,
            BindContext context) {

        if (isClientProperty(name)) {
            log.debug("Begin binding property {}", name);
        }

        return super.onStart(name, target, context);
    }

    @Override
    public Object onSuccess(
            ConfigurationPropertyName name,
            Bindable<?> target,
            BindContext context,
            Object result) {

        if (isClientProperty(name)) {
            // Chỉ ghi tên property, không ghi value.
            log.debug("Successfully bound property {}", name);
        }

        return super.onSuccess(name, target, context, result);
    }

    @Override
    public Object onFailure(
            ConfigurationPropertyName name,
            Bindable<?> target,
            BindContext context,
            Exception error) throws Exception {

        if (isClientProperty(name)) {
            log.warn(
                    "Binding failed for {}, exception type {}",
                    name, error.getClass().getSimpleName());
        }

        // Giữ nguyên chính sách xử lý lỗi của parent.
        return super.onFailure(name, target, context, error);
    }

    private static boolean isClientProperty(
            ConfigurationPropertyName name) {

        String path = name.toString();
        return path.equals("app.client")
                || path.startsWith("app.client.");
    }
}
~~~

### Những điều cần chú ý trong đoạn code

- `super(parent)` bảo đảm handler này **bọc một handler khác**, không thay toàn bộ chuỗi.
- `onStart` chỉ log rồi gọi `super.onStart`, giữ nguyên `Bindable` mà parent muốn sử dụng.
- `onSuccess` gọi `super.onSuccess` để kết quả cuối cùng vẫn đi qua handler cha.
- `onFailure` chỉ ghi loại exception, sau đó chuyển tiếp tới parent, không tự bỏ qua lỗi.
- Không có method thay đổi `result` nên handler chỉ phục vụ quan sát.
- Không in `result` hoặc `error.getMessage()` vào log trong ví dụ để tránh vô tình lộ thông tin cấu hình nhạy cảm.
- Đường tên được lọc theo prefix để tránh in log mọi cấu hình framework và thư viện.

### Vì sao nên kế thừa AbstractBindHandler?

Có thể viết class implements `BindHandler` trực tiếp. Tuy vậy, khi muốn kết hợp với handler đã có, `AbstractBindHandler` giúp việc chuyển tiếp callback đơn giản hơn, tránh vô tình bỏ qua chức năng validation hoặc xử lý lỗi của parent.

## 6. Gọi Binder.bind(...) thủ công với BindHandler

Một cách đơn giản để học và kiểm thử handler là truyền nó trực tiếp vào một lời gọi Binder.

Ví dụ bean quan sát sau khi Spring Boot đã khởi tạo:

~~~java
package com.example.configdemo;

import com.example.configdemo.bind.ClientTraceBindHandler;
import com.example.configdemo.config.ClientProperties;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.context.properties.bind.BindHandler;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
public class ManualBindingDemo {

    @Bean
    ApplicationRunner inspectManualBinding(Environment environment) {
        return args -> {
            Binder binder = Binder.get(environment);

            BindHandler handler =
                    new ClientTraceBindHandler(BindHandler.DEFAULT);

            ClientProperties config = binder.bind(
                    "app.client",
                    Bindable.of(ClientProperties.class),
                    handler
            ).get();

            System.out.println(
                    "Endpoint scheme: "
                            + config.endpoint().getScheme());
            System.out.println(
                    "Connect timeout: "
                            + config.connectTimeout());
        };
    }
}
~~~

Nếu `app.client` tồn tại và có dữ liệu hợp lệ, ví dụ này tạo một object `ClientProperties` qua một lần bind thủ công; handler sẽ quan sát các phần tử được xử lý.

`BindResult.get()` được dùng khi kỳ vọng có kết quả; nếu binding không tạo giá trị, lệnh này có thể báo lỗi thay vì âm thầm trả null. Trong ứng dụng thực tế, có thể chọn xử lý `BindResult` phù hợp yêu cầu.

**Điểm rất quan trọng:** truyền handler vào `binder.bind(...)` **chỉ áp dụng cho lời gọi đó**. Nó không tự gắn handler lên mọi bean `@ConfigurationProperties` được Spring Boot tạo ở thời điểm khởi động.

Ví dụ trên chạy trong `ApplicationRunner`, tức là **sau khi context đã khởi tạo**. Vì thế đây là một lượt bind độc lập để minh họa. Nếu mục tiêu là tùy biến ngay khi Spring Boot đang tạo configuration-properties beans, cần cơ chế advisor ở phần tiếp theo.

## 7. Áp dụng handler khi Spring Boot bind @ConfigurationProperties

Spring Boot cung cấp giao diện:

~~~java
import org.springframework.boot.context.properties.ConfigurationPropertiesBindHandlerAdvisor;
~~~

`ConfigurationPropertiesBindHandlerAdvisor` là một functional interface có phương thức:

~~~java
BindHandler apply(BindHandler bindHandler);
~~~

Nó cho phép trang bị thêm chức năng vào handler đang được sử dụng bởi `ConfigurationPropertiesBindingPostProcessor`, tức quá trình Spring Boot bind các bean `@ConfigurationProperties`.

Ví dụ configuration:

~~~java
package com.example.configdemo.bind;

import org.springframework.boot.context.properties.ConfigurationPropertiesBindHandlerAdvisor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class BindingAdviceConfiguration {

    @Bean
    static ConfigurationPropertiesBindHandlerAdvisor traceClientBinding() {
        return existing ->
                new ClientTraceBindHandler(existing);
    }
}
~~~

Khi Spring Boot khởi tạo các bean configuration properties phù hợp, advisor bọc `existing` bằng `ClientTraceBindHandler`. Handler bên trong chỉ log tên thuộc tính `app.client...`, nên tránh tác động đến nhóm khác.

### Vì sao phải truyền existing vào constructor?

Cách đúng:

~~~java
return existing -> new ClientTraceBindHandler(existing);
~~~

Không nên làm:

~~~java
return existing ->
        new ClientTraceBindHandler(BindHandler.DEFAULT);
~~~

nếu mục tiêu là giữ chuỗi xử lý hiện tại. Dùng `BindHandler.DEFAULT` thay `existing` có thể bỏ qua hành vi vốn đã được Spring Boot hoặc các advisor khác thêm vào, ví dụ validation và những xử lý đặc biệt.

### Phạm vi của advisor

Một bean advisor có thể tác động đến quá trình bind nhiều bean `@ConfigurationProperties` do Spring Boot quản lý. Vì vậy:

- Chỉ thêm chính sách thật sự cần áp dụng rộng.
- Đặt điều kiện lọc prefix hoặc target type trong handler.
- Tránh log tất cả tên/value của những cấu hình hệ thống.
- Không thực hiện I/O nặng hoặc truy vấn bean phức tạp trong callback.
- Không dùng advisor để thay thế việc chỉnh một giá trị cụ thể trong file cấu hình.

**Cơ chế advisor khác với lần Binder.bind thủ công:** advisor tác động tới pipeline do `ConfigurationPropertiesBindingPostProcessor` quản lý; nó không tự thay đổi các Binder độc lập do mã ứng dụng tự tạo nếu mã đó không sử dụng handler tương ứng.

## 8. Chuỗi handler và thứ tự gọi callback

Một `BindHandler` có thể bọc một handler khác:

~~~text
CustomTraceHandler
        |
        v
ExistingHandler
        |
        v
Các handler do Spring Boot cấu hình
~~~

Với `new ClientTraceBindHandler(existing)`, `ClientTraceBindHandler` là lớp ngoài. Khi một callback được gọi, implementation của nó có thể gọi `super.onStart(...)`, `super.onSuccess(...)` hoặc `super.onFailure(...)` để chuyển tiếp đến parent.

Điều này cho phép thêm chức năng mà không phá vỡ pipeline gốc.

### Thứ tự quan sát có thể khác thứ tự field

Binder có thể duyệt phần tử theo chiến lược phù hợp với type, constructor hoặc collection. Nếu handler log:

~~~text
Begin binding property app.client
Begin binding property app.client.endpoint
Successfully bound property app.client.endpoint
Begin binding property app.client.max-connections
Successfully bound property app.client.max-connections
Successfully bound property app.client
~~~

đó chỉ là một **trace minh họa**, không phải thứ tự callback bảo đảm trong mọi phiên bản và mọi kiểu. Một vài phần tử có thể chưa được bind, được tạo mặc định, hoặc vắng mặt tùy nguồn cấu hình.

Đừng viết logic nghiệp vụ dựa vào việc `endpoint` nhất định được bind trước `maxConnections`, hay số lần gọi callback phải bằng số field của record.

### Tránh lỗi đếm lặp

`onSuccess` có thể được gọi cho cả object cha và nhiều thuộc tính con. Nếu bạn tăng một counter mỗi lần callback chạy rồi gọi kết quả là “số bean configuration properties đã bind”, con số sẽ sai. Muốn đếm bean gốc, cần lọc đúng tên root hoặc phạm vi đích.

## 9. Kiểm tra một giá trị sau khi bind bằng onSuccess

Một handler có thể bổ sung kiểm tra kết quả. Ví dụ muốn từ chối số kết nối âm hoặc 0 **trong lần bind thủ công**:

~~~java
package com.example.configdemo.bind;

import org.springframework.boot.context.properties.bind.AbstractBindHandler;
import org.springframework.boot.context.properties.bind.BindContext;
import org.springframework.boot.context.properties.bind.BindHandler;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.source.ConfigurationPropertyName;

public final class PositiveConnectionsBindHandler
        extends AbstractBindHandler {

    public PositiveConnectionsBindHandler(BindHandler parent) {
        super(parent);
    }

    @Override
    public Object onSuccess(
            ConfigurationPropertyName name,
            Bindable<?> target,
            BindContext context,
            Object result) {

        if (name.toString().equals("app.client.max-connections")
                && result instanceof Integer value
                && value < 1) {

            throw new IllegalStateException(
                    "app.client.max-connections must be positive");
        }

        return super.onSuccess(name, target, context, result);
    }
}
~~~

Sử dụng:

~~~java
Binder binder = Binder.get(environment);

ClientProperties config = binder.bind(
        "app.client",
        Bindable.of(ClientProperties.class),
        new PositiveConnectionsBindHandler(BindHandler.DEFAULT)
).get();
~~~

Nếu người vận hành đặt `app.client.max-connections=-2`, callback có thể tạo lỗi để ngăn sử dụng cấu hình đó.

**Trong thực tế:** chỉ riêng quy tắc `max-connections >= 1` nên được giải quyết bằng Bean Validation:

~~~java
@Validated
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        @Min(1) int maxConnections) {
}
~~~

với các import và validation dependency cần thiết. Ví dụ `PositiveConnectionsBindHandler` chỉ nhằm minh họa khả năng can thiệp vào `onSuccess`. Đừng chuyển tất cả validation thành code handler nếu annotation chuẩn đã đáp ứng.

### Chú ý đường lỗi khi ném exception trong callback

Tài liệu `BindHandler` nêu rõ lỗi trong `onSuccess` hoặc `onCreate` có thể trở thành nguyên nhân cho `onFailure`. Vì vậy, nếu handler khác chọn bỏ qua lỗi, kết quả cuối có thể khác kỳ vọng. Với cấu hình bắt buộc, cần giữ chính sách fail-fast và kiểm thử toàn bộ chuỗi xử lý.

## 10. onFailure: không tự động nuốt lỗi cấu hình

Một sai lầm nguy hiểm là override `onFailure` như sau:

~~~java
@Override
public Object onFailure(
        ConfigurationPropertyName name,
        Bindable<?> target,
        BindContext context,
        Exception error) {

    return null;
}
~~~

Đoạn trên có thể che giấu lỗi conversion hoặc cấu hình sai, tùy vị trí phần tử và cách Binder dùng kết quả thay thế. Ứng dụng có nguy cơ tạo object thiếu giá trị, giữ default không phù hợp hoặc khởi động với cấu hình không mong muốn.

Ví dụ người vận hành đặt:

~~~properties
app.client.max-connections=many
~~~

Nếu ứng dụng đáng lẽ phải dừng vì số kết nối không hợp lệ, việc nuốt lỗi có thể khiến lớp cấu hình nhận giá trị mặc định hoặc trạng thái thiếu. Điều này gây khó khăn trong vận hành.

### Phương án thường an toàn hơn: log tối thiểu rồi chuyển tiếp

~~~java
@Override
public Object onFailure(
        ConfigurationPropertyName name,
        Bindable<?> target,
        BindContext context,
        Exception error) throws Exception {

    logger.warn("Failed to bind property {}", name);
    return super.onFailure(name, target, context, error);
}
~~~

Khi có parent, `super.onFailure` giữ chính sách của chuỗi handler hiện có. Việc log nên che/loại bỏ giá trị nhạy cảm, vì thông báo lỗi conversion đôi khi có dữ liệu đầu vào.

### Khi nào có thể bỏ qua lỗi?

Chỉ trong trường hợp một nhóm cấu hình thật sự **tùy chọn** và ứng dụng có đường fallback đã được thiết kế, ví dụ một module phụ trợ không được bật thì dữ liệu sai của nó không nên ảnh hưởng module chính. Nhưng cả khi đó, cần:

- Phân định đúng prefix và loại lỗi nào được bỏ qua.
- Có hành vi fallback an toàn, không tạo trạng thái nửa vời.
- Có log/metric để người vận hành biết cấu hình không được dùng.
- Có test cho giá trị sai, giá trị thiếu và cấu hình xung đột.
- Không bao giờ bỏ qua lỗi của secret, quyền truy cập hoặc cấu hình giao dịch quan trọng chỉ để ứng dụng khởi động.

## 11. Handler có sẵn: IgnoreErrorsBindHandler

Spring Boot cung cấp:

~~~java
import org.springframework.boot.context.properties.bind.handler.IgnoreErrorsBindHandler;
~~~

Handler này phục vụ chính sách **bỏ qua lỗi binding**. Ví dụ dùng trong phạm vi một lần Binder.bind:

~~~java
Binder binder = Binder.get(environment);

BindHandler ignoreErrors = new IgnoreErrorsBindHandler(
        BindHandler.DEFAULT);

ClientProperties config = binder.bind(
        "app.client",
        Bindable.of(ClientProperties.class),
        ignoreErrors
).orElse(null);
~~~

Đây là ví dụ minh họa API, **không phải cấu hình production được khuyến nghị** cho mọi ứng dụng. Nếu một property sai kiểu, việc bỏ qua có thể làm object cuối khác kỳ vọng, bao gồm kết quả không bind được hoặc trường nhận mặc định. Nếu toàn bộ object không có kết quả, `orElse(null)` có thể là null.

Nếu dữ liệu quan trọng, nên giữ lỗi để ứng dụng dừng sớm. Không dùng `IgnoreErrorsBindHandler` như một giải pháp chung cho file YAML sai.

### So sánh với ignoreInvalidFields

`@ConfigurationProperties` có thuộc tính `ignoreInvalidFields` để xử lý một số tình huống giá trị không bind được theo hợp đồng annotation. Cách đó nằm trong cơ chế tạo configuration properties bean; `IgnoreErrorsBindHandler` là một handler dùng khi xây dựng pipeline. Không nên coi hai cách hoàn toàn giống nhau về phạm vi và hành vi.

## 12. Handler có sẵn: NoUnboundElementsBindHandler

Một kiểu vấn đề khác là **có property dưới prefix nhưng không thuộc field nào được bind**. Ví dụ:

~~~yaml
app:
  client:
    endpoint: https://api.example.org
    max-connetions: 12  # Sai chính tả
~~~

Record thực tế chờ `maxConnections` tương ứng `max-connections`. Trong một số trường hợp, cấu hình không biết đến `max-connetions` có thể bị bỏ qua.

Spring Boot có:

~~~java
import org.springframework.boot.context.properties.bind.handler.NoUnboundElementsBindHandler;
~~~

`NoUnboundElementsBindHandler` dùng để yêu cầu các property thuộc phạm vi root đang bind được liên kết, nhằm phát hiện tên khóa thừa hoặc sai chính tả khi có thể kiểm tra nguồn property.

Ví dụ:

~~~java
Binder binder = Binder.get(environment);

BindHandler strict = new NoUnboundElementsBindHandler(
        BindHandler.DEFAULT);

ClientProperties config = binder.bind(
        "app.client",
        Bindable.of(ClientProperties.class),
        strict
).get();
~~~

Nếu property `app.client.max-connetions` có mặt nhưng không bind được vào field, handler có thể từ chối thay vì âm thầm bỏ qua, tùy đặc tính nguồn cấu hình và phạm vi phần tử đang xét.

### Không mặc định áp dụng strictness toàn hệ thống

Nếu áp dụng `NoUnboundElementsBindHandler` lên một root quá rộng, ứng dụng có thể vấp phải những property được dùng bởi các thành phần khác, hoặc nguồn không thể enumerate toàn bộ key. Nên chọn prefix cụ thể và hiểu khả năng liệt kê/kiểm tra của `ConfigurationPropertySource`.

Với `@ConfigurationProperties`, annotation có tùy chọn `ignoreUnknownFields` và cơ chế Spring Boot tương ứng để kiểm soát một số trường hợp không khớp. Lựa chọn strictness phải được đưa ra phù hợp với cấu trúc thực tế của dự án.

## 13. Handler có sẵn: ValidationBindHandler

Để validate cấu hình, Spring Boot có:

~~~java
import org.springframework.boot.context.properties.bind.validation.ValidationBindHandler;
~~~

Handler này phối hợp với `Validator` thích hợp để kiểm tra kết quả bind. Trong ứng dụng thông thường, cách thuận tiện nhất vẫn là đặt:

~~~java
@Validated
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        @NotNull URI endpoint,
        @Min(1) int maxConnections) {
}
~~~

và bảo đảm có Bean Validation provider, ví dụ `spring-boot-starter-validation`. Spring Boot sử dụng cơ chế validation trong quá trình configuration-properties binding thích hợp.

Nếu tự tạo một Binder và quản lý chuỗi handler riêng, có thể sử dụng `ValidationBindHandler` với các validator đã chuẩn bị. Tuy nhiên, không nên khởi tạo một validator tùy ý rồi giả định nó áp dụng mọi annotation validation trong mọi điều kiện. Kiểm tra cách đăng ký validator, các nhóm validation và tương thích với phiên bản framework.

**Điểm phân biệt:**

- `Conversion`: chuỗi `many` không chuyển thành `int`.
- `Validation`: số `-2` chuyển thành `int` được nhưng vi phạm `@Min(1)`.
- `Unknown/unbound`: tên `max-connetions` không khớp component `maxConnections`.

Các handler có thể can thiệp vào các vấn đề khác nhau, vì thế không có một handler duy nhất “sửa mọi lỗi cấu hình”.

## 14. Quan sát callback mà không lộ dữ liệu nhạy cảm

Một ứng dụng có thể chứa các property như:

~~~yaml
app:
  payment:
    api-key: "example-only"
    token: "not-a-real-token"
    enabled: true
~~~

Nếu một handler log toàn bộ:

~~~java
log.info("{} = {}", name, result);
~~~

nó có thể ghi token, password hoặc kết quả bind của object chứa nhiều secret vào log. Đây là rủi ro bảo mật nghiêm trọng.

Nên thiết kế handler theo nguyên tắc:

- Log **tên property** hoặc loại kết quả, không log giá trị.
- Chỉ log prefix do mình sở hữu.
- Không tự động log toàn bộ `error.getMessage()` nếu message có thể chứa dữ liệu nguồn.
- Tránh gọi `toString()` của record có trường nhạy cảm.
- Đảm bảo log ở mức phù hợp, ví dụ `DEBUG` trong môi trường phát triển.
- Nếu cần phân tích cấu hình trong production, dùng công cụ quan sát có cơ chế ẩn thông tin nhạy cảm và kiểm soát truy cập.

Không nên đưa các giá trị cấu hình động vào tên metric hoặc label có cardinality cao, vì chúng có thể làm tăng số chuỗi time-series và rò rỉ dữ liệu.

## 15. Dùng onCreate khi nào?

`onCreate` ít gặp trong mã ứng dụng hơn `onSuccess`, nhưng quan trọng khi Binder có thể tạo một object dù không có property tương ứng.

Ví dụ một nested record có default:

~~~java
package com.example.configdemo.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.notification")
public record NotificationProperties(
        @DefaultValue Retry retry) {

    public record Retry(
            @DefaultValue("3") int maxAttempts,
            @DefaultValue("250ms") java.time.Duration delay) {
    }
}
~~~

Khi không có `app.notification.retry.*`, `@DefaultValue` rỗng cho phép Binder tạo nested `Retry` với các default tương ứng. Trong những đường tạo object mà Binder hỗ trợ, callback `onCreate` có thể được dùng để quan sát việc một instance mới được tạo mà chưa có kết quả bind trực tiếp.

Cần tránh diễn giải tuyệt đối rằng “onCreate chắc chắn chạy một lần cho mọi @DefaultValue”. Thứ tự và đường nội bộ phụ thuộc Binder, kiểu object và cấu hình. Với việc kiểm thử, nên tập trung vào ý nghĩa callback được tài liệu công bố thay vì suy đoán chính xác số lần gọi trong mọi trường hợp.

### Một lưu ý về implementation

`onCreate` có method mặc định trên `BindHandler`. Nếu muốn override một callback chưa được `AbstractBindHandler` công bố riêng theo phiên bản đang dùng, cần đọc đúng API và bảo đảm việc chuyển tiếp phù hợp. Đừng tự tiện trả null vì hợp đồng của `onCreate` yêu cầu kết quả thay thế không null.

## 16. Custom handler có làm @ConfigurationProperties tự động reload không?

Không. `BindHandler` là callback **trong một lần binding**. Nếu file `application.yml` thay đổi sau khi context khởi tạo, việc có handler không làm Spring Boot tự động đọc lại Config Data và tạo lại object `@ConfigurationProperties`.

Trong ứng dụng Spring Boot tiêu chuẩn:

~~~text
Khởi động
  → nạp Config Data
  → tạo Environment
  → bind @ConfigurationProperties
  → tạo bean
  → ứng dụng hoạt động
~~~

Handler tham gia giai đoạn bind, không biến toàn bộ hệ thống thành cơ chế hot reload.

Nếu có yêu cầu cập nhật cấu hình động, cần thiết kế cơ chế refresh/lifecycle chuyên biệt, kiểm soát đồng bộ và nguồn dữ liệu phù hợp. Đừng dùng `onSuccess` để thay bean đang hoạt động hoặc làm “tự cập nhật” trong khi request đang được xử lý.

## 17. Test handler độc lập bằng MockEnvironment

Để kiểm tra handler một cách tập trung, có thể dùng `MockEnvironment` từ `spring-test`. Ví dụ test handler quan sát tên property:

~~~java
package com.example.configdemo;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.atomic.AtomicInteger;

import com.example.configdemo.config.ClientProperties;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.AbstractBindHandler;
import org.springframework.boot.context.properties.bind.BindContext;
import org.springframework.boot.context.properties.bind.BindHandler;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.ConfigurationPropertyName;
import org.springframework.mock.env.MockEnvironment;

class BindHandlerTest {

    @Test
    void countsSuccessfulClientBindings() {
        MockEnvironment environment = new MockEnvironment()
                .withProperty(
                        "app.client.endpoint",
                        "https://api.example.org")
                .withProperty(
                        "app.client.connect-timeout",
                        "3s")
                .withProperty(
                        "app.client.max-connections",
                        "12")
                .withProperty(
                        "app.client.enabled",
                        "true");

        AtomicInteger count = new AtomicInteger();

        BindHandler counter = new AbstractBindHandler(
                BindHandler.DEFAULT) {

            @Override
            public Object onSuccess(
                    ConfigurationPropertyName name,
                    Bindable<?> target,
                    BindContext context,
                    Object result) {

                if (name.toString().startsWith("app.client.")) {
                    count.incrementAndGet();
                }

                return super.onSuccess(name, target, context, result);
            }
        };

        ClientProperties properties = Binder.get(environment)
                .bind(
                        "app.client",
                        Bindable.of(ClientProperties.class),
                        counter)
                .get();

        assertThat(properties.maxConnections()).isEqualTo(12);
        assertThat(properties.connectTimeout().toSeconds())
                .isEqualTo(3);
        assertThat(count.get()).isGreaterThan(0);
    }
}
~~~

Test này không giả định chính xác số callback vì số lượng phần tử và cách duyệt có thể phụ thuộc Binder. Nó xác nhận handler quan sát được ít nhất một kết quả thành công trong prefix mong đợi và dữ liệu cuối không bị biến đổi.

Đoạn test giả định có `spring-boot-starter-test`, JUnit Jupiter và AssertJ. `MockEnvironment` giúp cấp property mà không cần khởi động toàn bộ Spring context.

### Test trường hợp chuyển đổi thất bại

Thay:

~~~text
app.client.max-connections=12
~~~

bằng:

~~~text
app.client.max-connections=many
~~~

Nếu handler chỉ log rồi chuyển tiếp lỗi, Binder có thể báo exception. Dùng AssertJ để xác nhận:

~~~java
assertThatThrownBy(() -> Binder.get(environment).bind(
        "app.client",
        Bindable.of(ClientProperties.class),
        handler))
    .isInstanceOf(RuntimeException.class);
~~~

Cần import `assertThatThrownBy` và tạo `handler` thích hợp từ test. Đây là snippet minh họa kiểm tra đường lỗi; không nên dựa vào một exception wrapper cụ thể nếu muốn test vẫn ổn định khi nâng phiên bản framework.

## 18. Test advisor trong một Spring context nhỏ

Để kiểm tra handler được áp dụng **tự động** cho configuration properties bean, nên tạo test với `ApplicationContextRunner` và cấu hình chứa advisor.

Ví dụ configuration:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ClientProperties.class)
@Import(BindingAdviceConfiguration.class)
class BindingTestConfiguration {
}
~~~

Các import:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
~~~

Test ý tưởng:

~~~java
ApplicationContextRunner runner =
        new ApplicationContextRunner()
                .withUserConfiguration(BindingTestConfiguration.class);

runner.withPropertyValues(
        "app.client.endpoint=https://api.example.org",
        "app.client.connect-timeout=3s",
        "app.client.max-connections=12",
        "app.client.enabled=true")
    .run(context -> {
        ClientProperties properties =
                context.getBean(ClientProperties.class);

        assertThat(properties.maxConnections()).isEqualTo(12);
    });
~~~

Đoạn kiểm thử trên xác nhận binding runtime của bean cấu hình. Nếu cần xác nhận advisor thực sự được gọi, có thể bổ sung một counter/test hook chỉ trong phạm vi test, thay vì phụ thuộc vào log console hoặc chính xác số callback.

Phải nhớ rằng việc tạo `Binder.get(environment)` trong test và gọi thủ công không tự kiểm tra advisor; advisor chỉ tác động vào pipeline cấu hình mà Spring Boot quản lý.

## 19. Chẩn đoán khi handler không chạy

### 19.1. Chưa truyền handler vào Binder.bind

~~~java
Binder.get(environment)
        .bind("app.client", ClientProperties.class);
~~~

Overload trên không nhận custom handler. Nếu muốn test handler riêng, dùng:

~~~java
Binder.get(environment).bind(
        "app.client",
        Bindable.of(ClientProperties.class),
        handler);
~~~

### 19.2. Nhầm Binder thủ công với @ConfigurationProperties bean

Bean configuration properties đã được Spring Boot bind ở bootstrap. Việc gọi một `Binder.bind(...)` sau đó chỉ tạo object thứ hai, không thay thế bean cũ. Muốn áp dụng rộng, dùng `ConfigurationPropertiesBindHandlerAdvisor` thích hợp.

### 19.3. Lọc sai prefix

Handler lọc `app.clients.` trong khi cấu hình dùng `app.client.` sẽ không log. Kiểm tra đúng canonical property name bằng `name.toString()`.

### 19.4. Callback có thể không chạy như bạn dự đoán

`onSuccess` chỉ áp dụng khi bind thành công, `onCreate` dành cho đường tạo instance chưa bind, `onFailure` trên đường lỗi, `onFinish` không chạy cho lỗi theo hợp đồng API. Nếu property không tồn tại, không thể mặc định đợi `onSuccess` cho chính property đó.

### 19.5. Log level không đủ

Trong handler dùng:

~~~java
log.debug("Bound {}", name);
~~~

nhưng ứng dụng chạy với DEBUG bị tắt. Code vẫn có thể thực thi, chỉ là không có dòng log. Trong môi trường phát triển có thể cấu hình:

~~~yaml
logging:
  level:
    com.example.configdemo.bind: DEBUG
~~~

Không bật DEBUG cho mọi framework package chỉ để quan sát một handler nhỏ nếu chưa cần.

### 19.6. Advisor không được đăng ký làm bean

Nếu phương thức tạo `ConfigurationPropertiesBindHandlerAdvisor` không có `@Bean` hoặc class chứa nó không nằm trong component scan/không được import, advisor không được áp dụng. Đảm bảo Spring đăng ký configuration chứa advisor.

### 19.7. Mất chuỗi parent

Nếu tạo handler mới nhưng bỏ `existing`, có nguy cơ làm mất hành vi do pipeline hiện có cung cấp. Cần dùng `new ClientTraceBindHandler(existing)` và gọi `super` ở callback cần giữ.

### 19.8. Giá trị đã bị ghi đè bởi nguồn khác

Handler đọc kết quả bind hiệu lực, không nhất thiết từ file YAML cụ thể. Nếu CLI cấp `--app.client.max-connections=20`, kết quả có thể là 20 thay vì 12 trong file chung. Không kết luận handler “sửa sai” nếu nguyên nhân thực là thứ tự ưu tiên PropertySource.

## 20. So sánh BindHandler với các cơ chế mở rộng khác

| Nhu cầu | Cơ chế nên cân nhắc |
| --- | --- |
| Xác định cấu hình thuộc nhóm nào | `@ConfigurationProperties` |
| Giải quyết tên property đa dạng | Relaxed binding của Binder |
| Chuyển String sang kiểu nghiệp vụ riêng | `Converter` + `@ConfigurationPropertiesBinding` |
| Validation thông thường | `@Validated` và Jakarta Bean Validation |
| Cấp default khi thiếu property | `@DefaultValue` |
| Ghi nhận callback trong một bind thủ công | `BindHandler` truyền vào `Binder.bind` |
| Tùy biến handler cho các bean config do Spring Boot quản lý | `ConfigurationPropertiesBindHandlerAdvisor` |
| Phát hiện property trong root không bind được | `NoUnboundElementsBindHandler` |
| Bỏ qua một số lỗi binding theo chính sách riêng | `IgnoreErrorsBindHandler`, rất thận trọng |
| Nạp tệp cấu hình bổ sung | `spring.config.import`/Config Data |
| Thay thứ tự ưu tiên nguồn | Cơ chế PropertySource và cấu hình khởi động |
| Sinh metadata gợi ý IDE | `spring-boot-configuration-processor` |

Từ bảng này có thể thấy `BindHandler` không nên được dùng làm “dao đa năng” cho mọi vấn đề externalized configuration. Nó hữu ích khi yêu cầu thực sự liên quan **vòng đời bind**.

## 21. Những lưu ý vận hành và thiết kế

1. **Đừng log giá trị nhạy cảm.** Handler có thể gặp object đã bind hoặc lỗi chứa thông tin riêng tư; log tên property thường đủ.
2. **Giữ callback nhanh và không có tác dụng phụ.** Một lời gọi bind có thể bao gồm nhiều phần tử; I/O nặng trong callback kéo dài bootstrap.
3. **Không giả định thứ tự callback cố định.** Đừng thiết kế state machine nghiệp vụ dựa vào thứ tự các field được Binder duyệt.
4. **Không thay đổi kết quả tùy tiện.** Nếu `onSuccess` trả object không tương thích target type, kết quả có thể gây lỗi sâu trong Binder.
5. **Giữ exception trừ khi có chính sách phục hồi rõ.** Nuốt lỗi cấu hình quan trọng thường nguy hiểm hơn fail fast.
6. **Giữ parent handler.** Khi dùng advisor, luôn bọc handler đã có thay vì tạo một pipeline không liên quan.
7. **Phân biệt root và thuộc tính con.** Handler được gọi ở nhiều cấp; nếu thu metric/đếm event, lọc phù hợp.
8. **Không dùng handler để reload Config Data.** Nó tham gia binding, không giám sát file thay đổi.
9. **Test cả thành công và lỗi.** Kiểm tra conversion sai, property thiếu, unknown property và cách chain hoạt động.
10. **Thực hiện chính sách ở đúng tầng.** Default, converter, validation, PropertySource và BindHandler có trách nhiệm riêng.

## 22. Bài tập thực hành

### Bài 1 — Log tên property thành công

Tạo `ClientTraceBindHandler` kế thừa `AbstractBindHandler`, override `onSuccess` và chỉ log các property có prefix `app.client`. Gọi `super.onSuccess(...)` để giữ parent. Cấp YAML hợp lệ, chạy Binder.bind thủ công và quan sát log DEBUG.

### Bài 2 — Xem lỗi conversion

Đặt:

~~~properties
app.client.max-connections=unknown
~~~

Dùng handler override `onFailure`, chỉ log property name và loại exception rồi gọi `super.onFailure(...)`. Giải thích vì sao lỗi không nên tự bị bỏ qua.

### Bài 3 — Dùng advisor

Đăng ký:

~~~java
@Bean
static ConfigurationPropertiesBindHandlerAdvisor advisor() {
    return parent -> new ClientTraceBindHandler(parent);
}
~~~

Bật `@ConfigurationPropertiesScan` và xác nhận handler hoạt động khi Spring Boot tạo bean `ClientProperties`.

### Bài 4 — Kiểm tra validation

Với `@Min(1) int maxConnections`, đặt `-2`. So sánh việc dùng Bean Validation và ném `IllegalStateException` trong `onSuccess`. Chọn Bean Validation nếu chỉ cần một constraint số chuẩn.

### Bài 5 — Phát hiện unknown key

Đặt `app.client.max-connetions=12` (sai chính tả). Dùng `NoUnboundElementsBindHandler` cho bind thủ công và quan sát kết quả trong nguồn có thể enumerate property. Giải thích vì sao strictness phải được giới hạn theo prefix.

### Bài 6 — Thử IgnoreErrorsBindHandler

Tạo một ví dụ không chứa secret với giá trị sai kiểu. So sánh đường bind bình thường với `IgnoreErrorsBindHandler`. Xác định kết quả có thể bị bỏ qua/null và giải thích rủi ro khi áp dụng cho cấu hình production.

### Bài 7 — Kiểm tra onFinish

Ghi nhận `onFinish` với một property hợp lệ và một property sai kiểu. Giải thích vì sao không thể coi `onFinish` là `finally` chạy cho mọi lỗi theo tài liệu Spring Boot 3.3.

### Bài 8 — Đếm phần tử, không đếm bean

Override `onSuccess` và tăng một counter. Cho record có bốn component. Quan sát số callback và giải thích vì sao không nên gọi counter đó là “số @ConfigurationProperties bean” nếu chưa lọc root.

### Bài 9 — BindResult khi thiếu prefix

Gọi:

~~~java
Binder.get(environment).bind(
        "app.missing",
        Bindable.of(ClientProperties.class),
        new ClientTraceBindHandler(BindHandler.DEFAULT)
);
~~~

Nếu không có property dưới root được tìm thấy, kiểm tra trạng thái `BindResult` và chọn `orElse(...)`/`get()` phù hợp. Không tự giả định luôn có object.

### Bài 10 — Câu hỏi thiết kế

Một nhóm muốn:
- Đổi chuỗi cấu hình `vnm` thành `RegionCode("VNM")`.
- Từ chối `max-connections=0`.
- Log tên property không chứa secret.
- Gợi ý property trong IDE.

Hãy chọn cơ chế đúng cho từng mục: `Converter`, Bean Validation, `BindHandler` và `spring-boot-configuration-processor`. Giải thích vì sao dùng một handler để xử lý cả bốn không phải thiết kế tốt.

## 23. Ghi nhớ

- `BindHandler` cung cấp callback tùy biến **vòng đời binding**, không thay đổi cách Spring Boot nạp Config Data hoặc thứ tự ưu tiên `PropertySource`.
- Trong Spring Boot 3.3, callback gồm `onStart`, `onSuccess`, `onCreate`, `onFailure` và `onFinish`.
- `AbstractBindHandler` giúp tạo decorator có parent; với handler quan sát, gọi `super` để giữ hành vi ban đầu.
- `Binder.get(environment).bind(prefix, Bindable.of(Type.class), handler)` chỉ dùng handler cho **lần bind đó**.
- `ConfigurationPropertiesBindHandlerAdvisor` cho phép bọc handler mà Spring Boot sử dụng khi tạo các bean `@ConfigurationProperties`. Đừng thay parent bằng `BindHandler.DEFAULT` nếu cần giữ pipeline hiện có.
- `onSuccess` có thể bổ sung kiểm tra/thay kết quả; `onFailure` có thể xử lý lỗi nhưng không nên nuốt lỗi tùy tiện. `onFinish` không được gọi trên đường binding thất bại.
- `IgnoreErrorsBindHandler` và `NoUnboundElementsBindHandler` là các handler có sẵn cho những chính sách khác nhau; phải hiểu phạm vi trước khi dùng.
- Với validation đơn giản, ưu tiên `@Validated` + Bean Validation. Với kiểu dữ liệu nghiệp vụ mới, ưu tiên converter. Chỉ dùng custom handler khi cần can thiệp thật sự vào vòng đời Binder.
- Không log giá trị cấu hình nhạy cảm, không dựa vào thứ tự callback và không coi BindHandler là cơ chế hot reload.

## Tài liệu tham khảo

- [Spring Boot 3.3 — BindHandler API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/BindHandler.html)
- [Spring Boot 3.3 — AbstractBindHandler API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/AbstractBindHandler.html)
- [Spring Boot 3.3 — Binder API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/Binder.html)
- [Spring Boot 3.3 — ConfigurationPropertiesBindHandlerAdvisor API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationPropertiesBindHandlerAdvisor.html)
- [Spring Boot 3.3 — NoUnboundElementsBindHandler API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/handler/NoUnboundElementsBindHandler.html)
- [Spring Boot 3.3 — IgnoreErrorsBindHandler API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/handler/IgnoreErrorsBindHandler.html)
- [Spring Boot 3.3 — ValidationBindHandler API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/validation/ValidationBindHandler.html)
- [Spring Boot 3.3 — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)

# Liên kết vào đối tượng sẵn có bằng `Bindable.ofInstance` trong Spring Boot

## 1. Bối cảnh và mục tiêu

Spring Boot hỗ trợ **Externalized Configuration** để ứng dụng nhận tham số vận hành từ `application.properties`, `application.yml`, biến môi trường, Java system properties, command-line arguments và các nguồn cấu hình bổ sung. Cách phổ biến nhất là khai báo class có `@ConfigurationProperties`, để framework tự tạo object rồi liên kết các giá trị vào class đó.

Trong một số tình huống nâng cao, ứng dụng **đã có một object** được tạo bởi code, factory, thư viện bên thứ ba hoặc quá trình khởi tạo đặc biệt. Thay vì yêu cầu Binder tự tạo object mới, ta muốn cập nhật các JavaBean properties của **chính instance đã tồn tại**, dựa trên dữ liệu trong `Environment`.

Spring Boot cung cấp:

~~~java
Bindable.ofInstance(existingObject)
~~~

để mô tả target cho thao tác binding. Phương thức này thuộc `org.springframework.boot.context.properties.bind.Bindable` và được dùng cùng `Binder`.

Ví dụ khái quát:

~~~java
ClientOptions options = new ClientOptions();

Binder binder = Binder.get(environment);
BindResult<ClientOptions> result =
        binder.bind("app.client", Bindable.ofInstance(options));
~~~

Trong ví dụ, `app.client` là **prefix** của các property cần tìm; `options` là **đối tượng đã có**. Với một JavaBean có setter phù hợp, Binder có thể gán các giá trị của `app.client.*` lên object đó.

Chủ đề này thuộc nhóm **Binder nâng cao** vì ứng dụng chủ động gọi API binding thay vì chỉ để cơ chế `@ConfigurationProperties` tự chạy.

Sau bài này, cần phân biệt rõ:

1. `Bindable.ofInstance(existing)` khác gì `Bindable.of(Type.class)`?
2. Một object đã có giá trị mặc định được cập nhật ra sao nếu chỉ có vài property được khai báo?
3. Có thể dùng với JavaBean, record, nested object, collection và object của thư viện ngoài đến mức nào?
4. Khi nào nên binding thủ công, khi nào nên để Spring Boot quản lý tự động?
5. Làm sao kiểm soát validation, lỗi chuyển đổi kiểu, side effects và lifecycle?
6. Vì sao không nên coi binding vào instance đã tồn tại là cơ chế cập nhật cấu hình động tự động?

## 2. Ba thành phần chính: `Binder`, `Bindable` và `BindResult`

Các API liên quan nằm trong package:

~~~java
org.springframework.boot.context.properties.bind
~~~

### 2.1. `Binder`

`Binder` là đối tượng thực hiện binding từ một hoặc nhiều nguồn `ConfigurationPropertySource` vào target có kiểu.

Với ứng dụng Spring Boot đã tạo `Environment` thích hợp:

~~~java
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;

Binder binder = Binder.get(environment);
~~~

`Binder.get(Environment)` tạo Binder dựa trên Environment và những nguồn configuration properties đã được gắn vào Environment đó. Trong một Spring Boot application context thông thường, đây là đường đi thuận tiện khi muốn làm binding thủ công.

Một số phương thức quan trọng:

~~~java
binder.bind("app.client", Bindable.of(ClientOptions.class));
binder.bind("app.client", Bindable.ofInstance(existing));
binder.bindOrCreate("app.client", ClientOptions.class);
~~~

Chúng **không có cùng hợp đồng**. Lời gọi `bind` trả về `BindResult<T>`; `bindOrCreate` cung cấp object sau binding hoặc một instance mới theo khả năng và điều kiện của API nếu không có kết quả binding.

### 2.2. `Bindable<T>`

`Bindable<T>` mô tả target được Binder xử lý. Nó bao gồm thông tin về kiểu, annotation liên quan và có thể có **existing value**.

Hai cách tạo thông dụng:

~~~java
Bindable.of(ClientOptions.class);
Bindable.ofInstance(existing);
~~~

Khác biệt:

- `Bindable.of(ClientOptions.class)`: mô tả một target theo class, **không cung cấp existing object**.
- `Bindable.ofInstance(existing)`: mô tả target theo kiểu runtime của `existing` và chỉ định **existing value chính là object đó**.

Theo Javadoc của Spring Boot, `ofInstance` tạo một `Bindable` có existing value bằng instance được truyền vào; **instance không được null**.

### 2.3. `BindResult<T>`

`Binder.bind(...)` trả `BindResult<T>`, dùng để biết binding có kết quả hay không và lấy giá trị tương ứng:

~~~java
BindResult<ClientOptions> result =
        binder.bind("app.client", Bindable.ofInstance(options));

if (result.isBound()) {
    ClientOptions bound = result.get();
    // Dùng object đã bind.
}
~~~

`isBound()` kiểm tra có kết quả binding; `get()` chỉ nên gọi khi có kết quả, nếu không có thể phát sinh ngoại lệ do không có giá trị. API còn cung cấp cách xử lý tùy chọn như `orElse(...)` và `ifBound(...)` theo phiên bản Spring Boot.

**Không nhầm:** `BindResult` là kết quả của thao tác binder, không phải một báo cáo validation tự động chứa mọi thuộc tính sai, và việc nhận một object không tự đảm bảo dữ liệu hợp lệ với nghiệp vụ.

## 3. Ví dụ tối thiểu với JavaBean mutable

Giả sử ứng dụng có object cấu hình kết nối, khởi tạo một số default trong Java:

~~~java
package com.example.demo.config;

import java.time.Duration;

public class ClientOptions {

    private String host = "localhost";
    private int port = 8080;
    private Duration timeout = Duration.ofSeconds(2);
    private boolean enabled = true;

    public ClientOptions() {
    }

    public String getHost() {
        return host;
    }

    public void setHost(String host) {
        this.host = host;
    }

    public int getPort() {
        return port;
    }

    public void setPort(int port) {
        this.port = port;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
~~~

Trong `application.properties`:

~~~properties
app.client.host=api.example.test
app.client.timeout=5s
~~~

Chủ động bind:

~~~java
import com.example.demo.config.ClientOptions;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.core.env.Environment;

public ClientOptions createOptions(Environment environment) {
    ClientOptions options = new ClientOptions();

    Binder.get(environment)
            .bind("app.client", Bindable.ofInstance(options));

    return options;
}
~~~

Với bean và nguồn cấu hình phù hợp:

| Trường | Giá trị ban đầu | Property nguồn | Giá trị sau binding |
| --- | --- | --- | --- |
| `host` | `localhost` | `app.client.host=api.example.test` | `api.example.test` |
| `port` | `8080` | Không khai báo | `8080` |
| `timeout` | `2s` | `app.client.timeout=5s` | `5s` |
| `enabled` | `true` | Không khai báo | `true` |

Ý nghĩa chính: **không cần thay thế cả object khi chỉ một số thuộc tính được cung cấp**. Binder có thể áp dụng những giá trị có mặt lên instance với các setter thích hợp; những field khác có thể giữ nguyên default đã có.

Nhưng đây **không phải một cam kết hợp nhất tùy ý cho mọi loại object hoặc collection**. Các trường lồng nhau, danh sách, map và kiểu bất biến có quy tắc binding riêng.

### 3.1. Phương thức `ofInstance` không tự thực hiện binding

Sai lầm thường gặp:

~~~java
ClientOptions options = new ClientOptions();
Bindable.ofInstance(options); // Chỉ tạo đối tượng mô tả target.
~~~

Dòng thứ hai **không** đọc `Environment` và không gọi setter. Phải truyền `Bindable` vào một thao tác Binder:

~~~java
Binder.get(environment)
        .bind("app.client", Bindable.ofInstance(options));
~~~

### 3.2. `ofInstance` không phải annotation

Không viết:

~~~java
@Bindable.ofInstance
public class ClientOptions {}
~~~

`ofInstance` là **static factory method**, không phải annotation. Nó trả một `Bindable<T>` dùng làm tham số của Binder.

## 4. Mô hình đầy đủ trong một Spring Boot application

Cách rõ ràng là tạo object thông qua một `@Bean` factory method và bind **một lần** trước khi trả object cho application context.

~~~java
package com.example.demo.config;

import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
public class ClientOptionsConfiguration {

    @Bean
    ClientOptions clientOptions(Environment environment) {
        ClientOptions options = new ClientOptions();

        Binder binder = Binder.get(environment);
        binder.bind("app.client", Bindable.ofInstance(options));

        return options;
    }
}
~~~

Một service có thể inject bean:

~~~java
package com.example.demo.service;

import com.example.demo.config.ClientOptions;
import org.springframework.stereotype.Service;

@Service
public class ClientService {

    private final ClientOptions options;

    public ClientService(ClientOptions options) {
        this.options = options;
    }

    public String endpoint() {
        return options.getHost() + ":" + options.getPort();
    }
}
~~~

Khi `@Configuration` được Spring quét hoặc import vào context, Spring tạo bean `clientOptions`. Trong factory method, object được khởi tạo trước, binder liên kết giá trị vào object và method trả về instance cho container sử dụng.

### 4.1. Vì sao binding trước khi đưa object vào sử dụng?

Binding một JavaBean mutable có thể gọi nhiều setter lần lượt. Trong khoảng thời gian đó, object có thể ở trạng thái **mới cập nhật một phần**. Nếu đem object đang bind chia sẻ cho thread khác, thread đó có thể thấy tập giá trị chưa nhất quán.

Do đó, hãy:

1. Tạo object cục bộ.
2. Bind trên object đó.
3. Kiểm tra invariants/validation cần thiết.
4. Chỉ sau khi thành công mới publish vào application context hoặc nơi sử dụng.

Không dùng `Bindable.ofInstance` như một cơ chế thay đổi cấu hình đang được nhiều request thread truy cập nếu chưa có thiết kế concurrency thích hợp.

### 4.2. Cần chú ý đến lỗi giữa chừng

Nếu Binder đã gọi setter cho `host` nhưng thất bại khi convert `timeout`, **object đã truyền vào có thể bị thay đổi một phần**. Không nên giả định thao tác bind vào existing instance là một transaction có khả năng rollback.

Trong factory method ví dụ, object chưa được công khai nên có thể để startup thất bại và bỏ nó. Với một singleton đã được chia sẻ, partial mutation là rủi ro lớn hơn nhiều.

## 5. So sánh `ofInstance` và `of(Class)`

### 5.1. Tạo target theo kiểu

~~~java
BindResult<ClientOptions> result =
        binder.bind("app.client", Bindable.of(ClientOptions.class));

ClientOptions options = result.orElse(new ClientOptions());
~~~

Trong hướng này, caller mô tả **kiểu cần bind**, để Binder tạo target theo khả năng của kiểu và cơ chế binding phù hợp. Nếu không có property nào được bind, `BindResult` có thể không chứa giá trị; ví dụ dùng `orElse` để cung cấp một object dự phòng.

### 5.2. Bind vào instance đã có

~~~java
ClientOptions options = new ClientOptions();

BindResult<ClientOptions> result =
        binder.bind("app.client", Bindable.ofInstance(options));
~~~

Ở đây object đã tồn tại trước lời gọi `bind`. Cơ chế binding theo JavaBean có thể cập nhật object này.

| Tiêu chí | `Bindable.of(ClientOptions.class)` | `Bindable.ofInstance(options)` |
| --- | --- | --- |
| Target được chỉ định bằng | Kiểu Java | Object đã tạo |
| Có existing value ban đầu | Không | Có |
| Ai tạo instance ban đầu | Binder hoặc cơ chế khởi tạo target tương ứng | Code gọi |
| Phù hợp record/immutable | Có thể với value-object/constructor binding đúng cách | Không phù hợp để “sửa” các field bất biến |
| Giữ default do object tự thiết lập | Phụ thuộc object được tạo và logic binding | Thường giữ các field không được cung cấp trong JavaBean |
| Mục đích | Bind một object từ cấu hình | Áp cấu hình lên object có sẵn |
| Có tự đăng ký Spring bean | Không | Không |

**Lưu ý:** hai lời gọi đều là API Binder thủ công. Chúng không tự thay thế cơ chế đăng ký bean của Spring.

### 5.3. `Bindable.ofInstance` và `withExistingValue`

Javadoc cũng có:

~~~java
Bindable<ClientOptions> target =
        Bindable.of(ClientOptions.class)
                .withExistingValue(options);
~~~

Cách này diễn đạt ý định rất giống `Bindable.ofInstance(options)`: cung cấp existing value để Binder dùng trong JavaBean binding.

Ưu điểm của `withExistingValue` là có thể bắt đầu từ một `Bindable` đã mang thông tin type/annotations rồi bổ sung existing value. `ofInstance` ngắn gọn khi chỉ cần chính kiểu của instance.

Theo tài liệu API, `withExistingValue(...)` **ngụ ý JavaBean binding**; không nên dùng nó để kỳ vọng thực hiện constructor binding trên object bất biến đã được tạo.

### 5.4. `withSuppliedValue` khác existing value

`Bindable` còn có `withSuppliedValue(Supplier<T>)`, cho phép cung cấp một supplier thay vì truyền trực tiếp existing value.

Đây là khả năng nâng cao cho những tình huống muốn Binder lấy target từ một supplier. Không đồng nhất supplier với `ofInstance`:

- `ofInstance` đã có object và đưa object đó thành existing value.
- `withSuppliedValue` mô tả một cách cung cấp giá trị target khi binder cần.

Nếu không có nhu cầu đặc biệt, `ofInstance` thường dễ hiểu hơn khi đối tượng thực sự đã tồn tại.

## 6. `Binder.get(Environment)` và các nguồn cấu hình

Trong Spring Boot, `Environment` tập hợp những property sources theo thứ tự ưu tiên, trong đó có Config Data, biến môi trường, JVM system properties và đối số dòng lệnh.

Ví dụ:

~~~properties
app.client.host=localhost
app.client.port=8080
app.client.timeout=2s
~~~

Chạy với command line:

~~~bash
java -jar app.jar \
  --app.client.host=api.production.example \
  --app.client.timeout=10s
~~~

Trong ứng dụng Boot thông thường, command-line arguments có độ ưu tiên cao hơn file cấu hình, nên Binder có thể áp các giá trị `api.production.example` và `10s` lên `ClientOptions`.

Thứ tự ưu tiên được quyết định bởi `Environment` và cách Boot chuẩn bị các nguồn; **`ofInstance` không thay đổi quy tắc chọn nguồn**.

### 6.1. Prefix là điểm bắt đầu của quá trình binding

~~~java
binder.bind("app.client", Bindable.ofInstance(options));
~~~

Binder tìm các property thuộc nhóm `app.client`, ví dụ:

~~~text
app.client.host
app.client.port
app.client.timeout
app.client.enabled
~~~

Nếu cấu hình thực tế dùng:

~~~properties
external.client.host=api.example.test
~~~

thì prefix `app.client` không khớp, và field `host` có thể giữ default. Một thao tác binding không tự đọc mọi tên property trong Environment.

### 6.2. Relaxed binding

Tên JavaBean `connectTimeout` có thể tương ứng với tên canonical `connect-timeout`:

~~~properties
app.client.connect-timeout=5s
~~~

Với setter:

~~~java
public void setConnectTimeout(Duration timeout) {
    this.connectTimeout = timeout;
}
~~~

Binder có thể liên kết property theo quy tắc relaxed binding của Boot. Nên viết key và prefix ở dạng lowercase kebab-case để các nguồn cấu hình khác nhau dễ tương thích.

### 6.3. Không đọc trực tiếp file YAML trong `ofInstance`

`Bindable.ofInstance` không nhận đường dẫn file. Nó nhận **object Java**. Nguồn được cung cấp bởi `Binder`.

Nếu cấu hình đến từ một file `application.yml`, Spring Boot Config Data đã đưa nội dung file vào `Environment` trước khi Binder làm việc trong những giai đoạn phù hợp. Nếu cần bind từ một nguồn tùy chọn không có trong Environment, phải tạo `ConfigurationPropertySource` hoặc cấu hình Binder tương ứng; không biến `ofInstance` thành parser YAML.

## 7. Viết cấu hình bằng properties và YAML

### 7.1. Dạng properties

~~~properties
app.client.host=api.example.test
app.client.port=8443
app.client.timeout=3s
app.client.enabled=true
~~~

Với `ClientOptions` ở phần đầu, Binder cập nhật các field tương ứng qua setter.

### 7.2. Dạng YAML

~~~yaml
app:
  client:
    host: api.example.test
    port: 8443
    timeout: 3s
    enabled: true
~~~

Hai cách biểu diễn có ý nghĩa tương tự sau khi được Spring Boot nạp thành các configuration properties.

YAML parser xử lý cấu trúc lồng nhau; Binder xử lý binding và conversion. Dấu thụt lề và cú pháp YAML phải hợp lệ trước khi tới bước binder.

### 7.3. Dạng biến môi trường

Tên biến môi trường tương ứng với key canonical thường là:

~~~text
APP_CLIENT_HOST
APP_CLIENT_PORT
APP_CLIENT_TIMEOUT
APP_CLIENT_ENABLED
~~~

Ví dụ trên shell POSIX:

~~~bash
export APP_CLIENT_HOST="api.internal.example"
export APP_CLIENT_PORT=8443
export APP_CLIENT_TIMEOUT=5s

java -jar app.jar
~~~

Tùy nguồn ưu tiên cao hơn trong Environment, những giá trị này có thể ghi đè cấu hình file. Trong môi trường Windows/PowerShell, cách khai báo biến môi trường có cú pháp khác.

### 7.4. Placeholder và type conversion

~~~properties
app.client.host=${APP_REMOTE_HOST:localhost}
app.client.timeout=${APP_REMOTE_TIMEOUT:2s}
~~~

Spring có thể phân giải placeholder qua `Environment` và Binder chuyển `2s` thành `Duration`. Nếu giá trị cung cấp là chuỗi không phải Duration hợp lệ, binding có thể thất bại; `ofInstance` không bỏ qua conversion.

## 8. Giá trị đã có và property bị thiếu

Đây là hành vi khiến `ofInstance` hữu ích nhất với JavaBean.

Ví dụ:

~~~java
ClientOptions options = new ClientOptions();
options.setHost("127.0.0.1");
options.setPort(9090);

binder.bind("app.client", Bindable.ofInstance(options));
~~~

Nguồn cấu hình chỉ chứa:

~~~properties
app.client.timeout=8s
~~~

Trong tình huống JavaBean binding thông thường, có thể mong đợi:

~~~text
host    = 127.0.0.1
port    = 9090
timeout = 8s
enabled = true
~~~

Các property không được khai báo không nhất thiết bị đặt về `null` hoặc Java default; field đã được khởi tạo trong object có thể tiếp tục giữ giá trị cũ.

### 8.1. Không nhầm “không khai báo” với “khai báo rỗng”

~~~properties
app.client.host=
~~~

Đây là một property có giá trị chuỗi rỗng, không phải không có khóa. Binder có thể gọi setter với chuỗi rỗng; giá trị default `127.0.0.1` bị thay bằng `""`.

Nếu host bắt buộc phải có nội dung, dùng validation hoặc invariant rõ ràng. Không dựa vào default trên object để xử lý input rỗng.

### 8.2. Có khóa nhưng sai kiểu

~~~properties
app.client.port=not-a-number
~~~

Nếu target có `int port`, conversion có thể thất bại. Không coi Binder là hàm “thử gán, nếu không hợp lệ thì giữ default cũ” theo mặc định.

Đối với cấu hình bắt buộc, fail fast thường tốt hơn âm thầm bỏ qua dữ liệu sai.

### 8.3. Không có property nào khớp prefix

~~~properties
unrelated.value=hello
~~~

Nếu `Environment` không cung cấp property phù hợp với `app.client.*`, thao tác `bind("app.client", ...)` có thể trả `BindResult` không bound. Object `options` vẫn đã tồn tại vì **caller tạo nó**, không phải vì Binder đã bind thành công.

Do đó:

~~~java
ClientOptions options = new ClientOptions();
BindResult<ClientOptions> result =
        binder.bind("app.client", Bindable.ofInstance(options));

if (!result.isBound()) {
    // Không có kết quả binding; chọn cách xử lý phù hợp.
}
~~~

Có thể cho phép giữ default nếu phần cấu hình hoàn toàn tùy chọn. Nếu nhóm cấu hình bắt buộc, cần báo lỗi rõ khi không tìm thấy property.

## 9. `BindResult`: kiểm tra kết quả mà không làm mất existing instance

Một số API quan trọng:

~~~java
BindResult<ClientOptions> result =
        binder.bind("app.client", Bindable.ofInstance(options));

boolean bound = result.isBound();
~~~

Nếu cần giá trị có trong `BindResult`:

~~~java
if (result.isBound()) {
    ClientOptions effective = result.get();
}
~~~

Nếu chỉ quan tâm instance đã truyền vào và chấp nhận default khi không có property, có thể viết ngắn:

~~~java
ClientOptions options = new ClientOptions();
binder.bind("app.client", Bindable.ofInstance(options));
return options;
~~~

**Lưu ý:** không đọc `result.get()` vô điều kiện nếu prefix có thể không được cấu hình. Nếu dùng `orElse(options)`, nên hiểu đây là một fallback ở mức kết quả binding, không phải một quá trình rebind khác.

### 9.1. `bindOrCreate` không phải “áp dụng thêm cấu hình lên object đã chia sẻ”

`Binder.bindOrCreate(...)` có hợp đồng bind hoặc tạo object theo type nếu binding không tạo kết quả. Nó hữu ích khi bạn muốn luôn có object, nhưng **khác với việc yêu cầu mutate một instance cụ thể rồi quản lý lifecycle của instance đó**.

Khi mục đích là cấu hình một object mà bạn đã tự tạo, hãy thể hiện ý định bằng `Bindable.ofInstance(object)` và xử lý kết quả phù hợp.

## 10. Trường hợp sử dụng: cấu hình object của thư viện bên thứ ba

Một SDK có thể cung cấp class cấu hình mutable, ví dụ:

~~~java
package com.vendor.sdk;

import java.time.Duration;

public class VendorClientOptions {

    private String endpoint = "http://localhost:9000";
    private Duration timeout = Duration.ofSeconds(3);
    private int maxRetries = 1;

    public String getEndpoint() { return endpoint; }
    public void setEndpoint(String endpoint) { this.endpoint = endpoint; }

    public Duration getTimeout() { return timeout; }
    public void setTimeout(Duration timeout) { this.timeout = timeout; }

    public int getMaxRetries() { return maxRetries; }
    public void setMaxRetries(int maxRetries) {
        this.maxRetries = maxRetries;
    }
}
~~~

Giả sử bạn không sở hữu mã nguồn thư viện và không thể gắn annotation lên class này. Ứng dụng muốn áp cấu hình:

~~~yaml
vendor:
  client:
    endpoint: "https://vendor.example.test/v1"
    timeout: 4s
    max-retries: 3
~~~

Có thể viết factory:

~~~java
import com.vendor.sdk.VendorClientOptions;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
class VendorClientConfiguration {

    @Bean
    VendorClientOptions vendorClientOptions(Environment environment) {
        VendorClientOptions options = new VendorClientOptions();

        Binder.get(environment)
                .bind("vendor.client", Bindable.ofInstance(options));

        return options;
    }
}
~~~

Lợi ích là không cần tạo một lớp trung gian chỉ để sao chép từng property rồi gọi setter bằng tay.

### 10.1. Một lựa chọn đơn giản hơn: `@Bean` + `@ConfigurationProperties`

Nếu không cần kiểm soát Binder thủ công, Spring Boot cũng hỗ trợ đặt `@ConfigurationProperties` trên một `@Bean` method trả về JavaBean:

~~~java
import com.vendor.sdk.VendorClientOptions;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class VendorClientConfiguration {

    @Bean
    @ConfigurationProperties(prefix = "vendor.client")
    VendorClientOptions vendorClientOptions() {
        return new VendorClientOptions();
    }
}
~~~

Trong mô hình này, Boot quản lý bước bind. Đây thường là lựa chọn **gọn hơn** khi nhu cầu chỉ là cấu hình một bean được tạo sẵn bằng factory.

Chỉ dùng `Binder + Bindable.ofInstance` nếu cần quyền điều khiển đặc biệt như chọn prefix động, bind trong giai đoạn xử lý riêng, dùng nguồn riêng hoặc xử lý kết quả binding tường minh.

### 10.2. Không dùng đồng thời cả hai trên cùng một bean

**Tránh** vừa đặt `@ConfigurationProperties` trên `@Bean` vừa tự gọi `binder.bind(..., Bindable.ofInstance(bean))` chỉ vì muốn “chắc chắn”.

Điều đó có thể dẫn tới binding nhiều lần, setter có side effect bị gọi lại hoặc cấu hình bị áp theo thứ tự khó suy luận. Chọn một chủ thể chịu trách nhiệm binding cho mỗi object.

## 11. JavaBean binding và setter là trọng tâm

Theo API Spring Boot, cung cấp existing value qua `ofInstance` hoặc `withExistingValue` hướng Binder tới **JavaBean binding**. Điều này đòi hỏi target có những property mà Binder có thể cập nhật.

Ví dụ phù hợp:

~~~java
public class CacheOptions {
    private String region = "local";

    public String getRegion() { return region; }
    public void setRegion(String region) { this.region = region; }
}
~~~

Nếu field là scalar `String`/`int`/`Duration`, các setter công khai phù hợp là hướng đơn giản và rõ nhất.

### 11.1. Constructor có tham số không tự thành constructor binding

Ví dụ:

~~~java
public class ImmutableOptions {
    private final String endpoint;

    public ImmutableOptions(String endpoint) {
        this.endpoint = endpoint;
    }

    public String getEndpoint() {
        return endpoint;
    }
}
~~~

Đoạn:

~~~java
ImmutableOptions existing =
        new ImmutableOptions("https://default.example.test");

binder.bind("app.client", Bindable.ofInstance(existing));
~~~

không khiến `existing.endpoint` tự đổi. Field là `final`, không có setter; `ofInstance` không phải cơ chế gọi lại constructor của object đã có.

Nếu muốn immutable binding, nên yêu cầu Binder tạo object qua value-object/constructor binding phù hợp, ví dụ `Bindable.of(ImmutableOptions.class)` khi model và Spring Boot version hỗ trợ, hoặc dùng `@ConfigurationProperties` với record đăng ký đúng.

### 11.2. Record không thích hợp làm existing mutable target

~~~java
public record ClientRecord(String host, int port) {}
~~~

Record được thiết kế bất biến. `Bindable.ofInstance(new ClientRecord(...))` không phải cách để “sửa host, giữ port” trong record đã tạo.

Nếu cần record:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientRecord(String host, int port) {}
~~~

và đăng ký qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`, để Boot thực hiện constructor binding theo cơ chế phù hợp.

**Quy tắc chọn:** cần giữ và cập nhật một JavaBean mutable đã có → `ofInstance`. Cần một object bất biến được dựng từ cấu hình → constructor binding, không cố mutate record.

## 12. Nested JavaBean: object con đã tồn tại

Một trường hợp hữu ích là object cha giữ sẵn một nested object mutable:

~~~java
import java.time.Duration;

public class GatewayOptions {

    private final RetryOptions retry = new RetryOptions();
    private String host = "localhost";

    public RetryOptions getRetry() {
        return retry;
    }

    public String getHost() {
        return host;
    }

    public void setHost(String host) {
        this.host = host;
    }

    public static class RetryOptions {
        private int maxAttempts = 2;
        private Duration delay = Duration.ofMillis(250);

        public int getMaxAttempts() {
            return maxAttempts;
        }

        public void setMaxAttempts(int maxAttempts) {
            this.maxAttempts = maxAttempts;
        }

        public Duration getDelay() {
            return delay;
        }

        public void setDelay(Duration delay) {
            this.delay = delay;
        }
    }
}
~~~

Cấu hình:

~~~properties
gateway.host=api.example.test
gateway.retry.max-attempts=5
gateway.retry.delay=500ms
~~~

Bind:

~~~java
GatewayOptions options = new GatewayOptions();

binder.bind("gateway", Bindable.ofInstance(options));
~~~

Trong mô hình JavaBean binding phù hợp, Binder có thể đi vào object `retry` đã được khởi tạo và gọi setter của nested bean. Không cần thay hẳn `retry` nếu object con có thể bind được thông qua getter.

### 12.1. Cần phân biệt nested mutable và nested immutable

Nếu nested object là record hoặc class có toàn bộ field `final`, binder không thể tự cập nhật field như với JavaBean mutable. Có thể cần setter ở parent để thay nested object, hoặc chuyển toàn bộ cấu trúc sang constructor binding.

Không nên khẳng định rằng một field `final` ở parent luôn làm nested properties không bind được: parent có thể giữ **tham chiếu final tới một nested mutable object** và Binder có thể cập nhật object con đó.

### 12.2. Nguy cơ dùng chung nested instance

Nếu nhiều service đã giữ tham chiếu tới `options.getRetry()`, gọi binder vào object cha sau khi các service đang sử dụng có thể thay đổi nested object mà không có cơ chế đồng bộ. Vì thế, vẫn nên bind trước khi công khai object.

## 13. List, Set và Map: đừng suy luận như scalar

Với scalar như `host` và `timeout`, ý tưởng “giữ default cũ khi key thiếu” khá trực quan. Với collection, cần thận trọng hơn.

Ví dụ:

~~~java
import java.util.ArrayList;
import java.util.List;

public class PoolOptions {
    private List<String> endpoints = new ArrayList<>(
            List.of("http://localhost:8080")
    );

    public List<String> getEndpoints() {
        return endpoints;
    }

    public void setEndpoints(List<String> endpoints) {
        this.endpoints = endpoints;
    }
}
~~~

Cấu hình:

~~~properties
pool.endpoints[0]=https://primary.example.test
pool.endpoints[1]=https://backup.example.test
~~~

Bind:

~~~java
PoolOptions options = new PoolOptions();
binder.bind("pool", Bindable.ofInstance(options));
~~~

Kết quả mong muốn là danh sách có hai endpoint mới theo cấu hình. Nhưng **không nên hứa rằng Binder sẽ nối thêm vào list đã khởi tạo**. Tùy target, collection implementation và cách binding, collection có thể được tạo/chọn lại hoặc cập nhật theo quy tắc Binder.

### 13.1. List từ nhiều property source thường được thay thế

Spring Boot có quy tắc quan trọng: khi một `List` được khai báo ở nhiều nguồn cấu hình có độ ưu tiên khác nhau, Binder thông thường chọn **danh sách ở nguồn ưu tiên cao hơn**, không tự gộp phần tử của mọi nguồn.

Ví dụ file cơ sở:

~~~yaml
pool:
  endpoints:
    - https://a.example.test
    - https://b.example.test
~~~

File profile `prod`:

~~~yaml
pool:
  endpoints:
    - https://prod.example.test
~~~

Khi profile `prod` active và file này thắng, list hiệu lực thường là **một phần tử** `https://prod.example.test`, không phải ba phần tử.

`ofInstance` không biến cơ chế đó thành phép merge list đặc biệt. Không dùng nó để “patch” từng index một cách mơ hồ.

### 13.2. Map có đặc trưng khác List

Với `Map<String, ClientOptions>`, Binder có thể tổng hợp những key từ các nguồn và áp precedence cho cùng key theo quy tắc riêng của Map. Nhưng khi bind Map vào existing instance, cần xác định rõ yêu cầu merge/replace và test bằng dữ liệu thật.

Nếu hệ thống cần **merge có chủ đích**, nhất là với object mutable phức tạp, nên viết thuật toán merge riêng có test thay vì dựa vào giả định của một thao tác `ofInstance`.

### 13.3. Set không bảo đảm thứ tự

Nếu một target có `Set<String>`, không nên viết logic phụ thuộc vào vị trí iteration của Set. Nếu thứ tự endpoint quan trọng, dùng `List`.

Set cũng làm trùng phần tử biến mất theo `equals`/`hashCode`. Nếu khai báo trùng là lỗi vận hành cần phát hiện, bind vào List và validate duplicate trước khi đổi thành Set.

### 13.4. Giá trị collection mặc định

Nếu object có list default nhưng nguồn không cung cấp khóa list, list có thể được giữ nguyên trong JavaBean. Nếu nguồn cung cấp list mới, không được giả định nó luôn append vào default list.

Hãy quyết định rõ chính sách: **default list khi thiếu**, **replacement khi có**, hay **merge tự viết**. Chỉ chính sách cuối mới yêu cầu code merge tường minh.

## 14. `Bindable.ofInstance` không đồng nghĩa hot reload

Một câu hỏi thường gặp: “Nếu object đã tồn tại, có thể gọi `ofInstance` định kỳ để tự cập nhật cấu hình không?”

Về API, có thể thực hiện thêm các lời gọi binder trên cùng object. Nhưng **Spring Boot không tự động làm việc đó chỉ vì bạn dùng `ofInstance`**.

Rủi ro của việc rebind runtime:

- Setter được gọi lại trên object đã công khai.
- Những field mới có thể được thay đổi trước những field khác.
- Một lỗi binding có thể để object ở trạng thái cập nhật dở.
- Client đã được tạo từ cấu hình cũ không chắc tự tái khởi tạo.
- Các thread khác có thể thấy dữ liệu không nhất quán.
- Một property bị xóa khỏi nguồn không nhất thiết khiến field cũ được xóa hoặc reset theo cách bạn dự định.

Nếu cần runtime reconfiguration, hãy thiết kế một quy trình riêng: bind vào **object tạm**, validate toàn bộ, sau đó công bố snapshot mới bằng cơ chế thread-safe. Với cấu hình phần lớn không đổi, restart/redeploy thường đơn giản hơn.

### 14.1. Mô hình snapshot thay thế toàn bộ

Ví dụ ý tưởng:

~~~java
public final class SettingsHolder {
    private volatile ClientOptions current;

    public SettingsHolder(ClientOptions initial) {
        this.current = initial;
    }

    public ClientOptions get() {
        return current;
    }

    public void replace(ClientOptions next) {
        this.current = next;
    }
}
~~~

Đây chỉ là minh họa cơ chế thay **tham chiếu**. `ClientOptions` trong ví dụ trước vẫn mutable; để bảo đảm snapshot không bị chỉnh sửa sau khi publish, cần thiết kế immutable view/copy phù hợp, quản lý lifecycle tài nguyên và đồng bộ những dependency đã được tạo từ cấu hình cũ.

**Không áp dụng cơ chế này chỉ vì muốn dùng Bindable.ofInstance.** Nó là một bài toán kiến trúc riêng.

## 15. Chọn API khi chỉ cần bind thủ công

| Mục tiêu | Lựa chọn thường phù hợp |
| --- | --- |
| Spring quản lý một class có `@ConfigurationProperties` | `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` |
| Spring tạo JavaBean bằng `@Component` rồi bind | `@Component` + `@ConfigurationProperties` |
| Spring tạo JavaBean từ `@Bean` và tự bind | `@Bean` + `@ConfigurationProperties` |
| Code đã có object mutable và cần áp config | `Binder.bind(prefix, Bindable.ofInstance(object))` |
| Chỉ cần target theo kiểu | `Binder.bind(prefix, Bindable.of(Type.class))` |
| Muốn bind hoặc tạo object mới nếu cần | `Binder.bindOrCreate(...)` |
| Đối tượng là record bất biến | Constructor/value-object binding, không mutate bằng `ofInstance` |
| Muốn bind một danh sách thuần có kiểu phần tử | `Bindable.listOf(Element.class)` khi phù hợp |
| Muốn bind map có key/value rõ | `Bindable.mapOf(Key.class, Value.class)` khi phù hợp |
| Muốn cấu hình linh hoạt theo source riêng | Tạo `Binder` với `ConfigurationPropertySource` phù hợp |

**Nguyên tắc:** nếu cơ chế tự động của Spring Boot đã đáp ứng yêu cầu, không cần tự gọi Binder chỉ để làm lại đúng công việc đó.

## 16. Binder thủ công và Bean Validation

Với `@ConfigurationProperties` do Spring Boot quản lý, có thể dùng `@Validated` và Jakarta Bean Validation để kiểm tra các trường. Nhưng khi tự gọi:

~~~java
binder.bind("app.client", Bindable.ofInstance(options));
~~~

không nên giả định **mọi validation của ứng dụng đã tự động được kích hoạt giống hệt như một bean `@ConfigurationProperties` do framework quản lý**.

Manual binding cho phép truyền `BindHandler` phù hợp, và ứng dụng cũng có thể chủ động validate object bằng Bean Validation provider sau khi bind. Nếu dữ liệu bắt buộc, nên thiết kế bước kiểm tra rõ.

### 16.1. Ví dụ kiểm tra cấu hình sau bind

~~~java
import java.time.Duration;

public static void validateOptions(ClientOptions options) {
    if (options.getHost() == null || options.getHost().isBlank()) {
        throw new IllegalStateException(
                "app.client.host must be configured");
    }

    if (options.getPort() < 1 || options.getPort() > 65535) {
        throw new IllegalStateException(
                "app.client.port must be between 1 and 65535");
    }

    Duration timeout = options.getTimeout();
    if (timeout == null || timeout.isZero() || timeout.isNegative()) {
        throw new IllegalStateException(
                "app.client.timeout must be a positive duration");
    }
}
~~~

Dùng:

~~~java
ClientOptions options = new ClientOptions();
binder.bind("app.client", Bindable.ofInstance(options));
validateOptions(options);
~~~

Ví dụ sử dụng thông điệp cố định về **hợp đồng cấu hình**, không in trực tiếp hostname, password hoặc giá trị bị từ chối.

### 16.2. Bean Validation với cấu hình phức tạp

Với lớp có các annotation như `@NotBlank`, `@Min` và `@Max`, có thể chủ động sử dụng `jakarta.validation.Validator` để validate instance sau khi Binder hoàn tất. Cần Bean Validation provider trên classpath, thường qua `spring-boot-starter-validation`.

Khi dùng custom `BindHandler` để kiểm tra hoặc thay đổi hành vi, xem API của phiên bản Spring Boot thực tế. Không thêm nhiều handler tùy tiện nếu chưa hiểu lúc nào chúng được gọi.

### 16.3. Không coi binding là security validation

Một URI hợp lệ về cú pháp vẫn có thể trỏ vào mạng nội bộ không được phép, một string password có thể đã hết hạn, một `Resource` có thể dẫn tới file nhạy cảm, và một timeout có thể vượt ngân sách vận hành dù parse được `Duration`.

Kiểm tra domain/security là trách nhiệm bổ sung, không tự sinh từ việc chuyển đổi type.

## 17. Xử lý lỗi binding và tránh trạng thái cập nhật dở

Một lỗi cấu hình có thể xảy ra khi:

- `app.client.port` không phải số nguyên.
- `app.client.timeout` không parse được thành `Duration`.
- JavaBean không có setter phù hợp.
- Prefix không khớp nguồn.
- Một nested object không thể bind do kiểu bất biến.
- Converter tùy chỉnh ném exception.
- Custom `BindHandler` từ chối một giá trị.

Ví dụ:

~~~properties
app.client.port=oops
~~~

Binder có thể báo `BindException` hoặc exception liên quan conversion. Không nên nuốt lỗi rồi tiếp tục sử dụng object đã bị mutate một phần.

### 17.1. Pattern an toàn trong factory

~~~java
@Bean
ClientOptions clientOptions(Environment environment) {
    ClientOptions candidate = new ClientOptions();

    Binder.get(environment).bind(
            "app.client",
            Bindable.ofInstance(candidate)
    );

    validateOptions(candidate);
    return candidate;
}
~~~

Nếu binding hoặc validation thất bại, factory không trả object cho container. Application context có thể không khởi động; đây thường là lựa chọn hợp lý với cấu hình bắt buộc.

### 17.2. Không bật ignoreErrors để che dữ liệu sai

Một số cơ chế configuration properties có tùy chọn bỏ qua lỗi binding. Với cấu hình bắt buộc, che lỗi có thể khiến object giữ default ở những nơi bạn không mong đợi.

Chỉ cho phép fallback nếu đã có policy rõ ràng và đã kiểm thử trường hợp thiếu, sai kiểu và cấu hình conflict. Không để `ofInstance` vô tình biến lỗi dữ liệu thành hành vi âm thầm.

### 17.3. An toàn thông tin trong thông báo lỗi

Một cấu hình có thể chứa API key, password hoặc URI chứa credential. Không in `options.toString()`, toàn bộ `Environment` hoặc rejected raw value để debug.

Thông báo tốt nên nêu key/requirement an toàn, ví dụ:

~~~text
[CFG-201] app.client.timeout must be a valid positive duration.
Action: correct the deployment setting and restart.
~~~

Tránh in nguyên chuỗi đầu vào nếu nó có thể chứa bí mật. Điều này đặc biệt quan trọng khi exception bắt nguồn từ converter hoặc thư viện bên thứ ba.

## 18. `BindHandler` trong kịch bản nâng cao

`Binder.bind` có overload nhận `BindHandler`:

~~~java
binder.bind("app.client",
            Bindable.ofInstance(options),
            bindHandler);
~~~

`BindHandler` là extension point cho những bước của quá trình binding, ví dụ khi bắt đầu bind, khi thành công, khi thất bại hoặc khi kết thúc. Spring Boot cung cấp một số handler dùng cho các trường hợp cụ thể; đồng thời có thể viết custom handler khi có yêu cầu đặc biệt.

Điểm quan trọng:

- Không cần `BindHandler` để dùng `ofInstance` trong ví dụ cơ bản.
- Handler không tự làm JavaBean immutable có thể cập nhật được.
- Nếu handler tùy biến lỗi hoặc kết quả, cần kiểm thử cẩn thận vì có thể thay đổi hành vi chung của binding.
- Không log toàn bộ `ConfigurationProperty` hoặc giá trị đầu vào trong handler khi chứa dữ liệu nhạy cảm.
- Một handler validation không có nghĩa phép mutate existing instance có transactional rollback.

### 18.1. Khi nào nên dùng handler?

Một số nhu cầu thật sự:

- Kiểm tra các property không được sử dụng trong một phạm vi cấu hình quan trọng.
- Áp dụng rule validation đặc biệt trong quá trình bind.
- Gắn thông tin origin được phép vào diagnostic.
- Từ chối một nhóm property bị cấm theo policy.

Nếu chỉ muốn bảo đảm host không blank hoặc port hợp lệ, validation sau khi bind thường dễ đọc hơn việc tự viết handler phức tạp.

## 19. Tự tạo `Binder` từ nguồn riêng

`Binder.get(Environment)` thuận tiện trong Spring Boot context. Nhưng API `Binder` cũng có constructor nhận một hoặc nhiều `ConfigurationPropertySource`.

Điều này hữu ích khi ứng dụng muốn bind một object từ **nguồn giới hạn do mình lựa chọn** thay vì toàn bộ Environment.

Luồng khái quát:

~~~text
Map / custom PropertySource / ConfigurationPropertySource
                     |
                     v
                   Binder
                     |
                     v
           Bindable.ofInstance(existing)
                     |
                     v
               Existing JavaBean
~~~

Trong Java có thể dùng những utility dưới `org.springframework.boot.context.properties.source` để chuyển `PropertySource` thành `ConfigurationPropertySource` phù hợp rồi đưa vào Binder.

### 19.1. Vì sao phải để ý source precedence?

Nếu Binder nhận nhiều sources, thứ tự của chúng quyết định giá trị nào được chọn khi cùng một khóa xuất hiện nhiều lần. Một nguồn tự tạo không tự động có chính sách ưu tiên giống application context.

Với Spring Boot Environment thông thường, sử dụng `Binder.get(environment)` giúp tránh tự lắp ráp sai thứ tự nhiều nguồn. Chỉ dựng Binder riêng khi có yêu cầu rõ và test tương ứng.

### 19.2. Không nhầm Binder với trình đọc Config Data

`Binder` tập trung vào **liên kết property → Java object**. Việc nạp nhiều document YAML, lựa chọn profile và import Config Tree do cơ chế Config Data phụ trách ở những giai đoạn khác.

Nếu đọc một YAML file theo cách thủ công ngoài cơ chế Boot, bạn cần một parser/loader phù hợp trước khi có dữ liệu đưa vào Binder. `Bindable.ofInstance` không tự đọc đường dẫn file, không xác định profile và không import cấu hình.

## 20. Vấn đề kiểu generic và runtime type

`Bindable.ofInstance(existing)` suy luận kiểu từ object đã có. Điều này thuận tiện với một JavaBean cụ thể:

~~~java
ClientOptions options = new ClientOptions();
Bindable<ClientOptions> target = Bindable.ofInstance(options);
~~~

Với collection và generic type phức tạp, type erasure của Java làm một instance `ArrayList<String>` không mang đủ thông tin kiểu phần tử theo cách một `ResolvableType` tường minh có thể làm.

Nếu mục tiêu là bind một collection thuần, dùng các static factory dành cho collection:

~~~java
Bindable<List<String>> target = Bindable.listOf(String.class);
~~~

Hoặc khai báo target theo `ResolvableType` có đủ generic metadata nếu cần. Đừng tự suy ra `ofInstance(new ArrayList<>())` luôn biết phần tử phải là `String` khi không có ngữ cảnh khai báo generic.

### 20.1. Tại sao generic metadata quan trọng?

Giả sử cấu hình:

~~~properties
app.retry.delays[0]=100ms
app.retry.delays[1]=2s
~~~

Nếu target là `List<Duration>`, Binder cần biết phần tử là `Duration` để convert chuỗi `100ms` thành đúng kiểu. Nếu chỉ biết runtime class `ArrayList`, kiểu phần tử không được biểu diễn đầy đủ.

Với property `List<Duration> delays` là field của một JavaBean, metadata từ field/setter thường cung cấp thông tin generic type. Do đó, binding vào **JavaBean chứa collection field có khai báo kiểu** thường an toàn hơn việc bind trực tiếp vào một raw collection instance.

## 21. Kiểm thử bằng `@SpringBootTest`

Giả sử dự án đã có một Spring Boot application class và dependency test phù hợp.

~~~java
import com.example.demo.config.ClientOptions;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.context.properties.bind.BindResult;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(properties = {
        "app.client.host=test.example.test",
        "app.client.timeout=750ms"
})
class ExistingInstanceBindingTest {

    @Autowired
    Environment environment;

    @Test
    void bindsExistingJavaBean() {
        ClientOptions options = new ClientOptions();

        BindResult<ClientOptions> result =
                Binder.get(environment).bind(
                        "app.client",
                        Bindable.ofInstance(options)
                );

        assertTrue(result.isBound());
        assertEquals("test.example.test", options.getHost());
        assertEquals(Duration.ofMillis(750), options.getTimeout());
        assertEquals(8080, options.getPort()); // Giữ default.
    }
}
~~~

Bài test này kiểm tra hành vi trọng tâm: Binder nhìn thấy các property trong test Environment và áp chúng lên instance đã được tạo.

Nếu cần khẳng định identity của object ở đường JavaBean binding, có thể kiểm tra kết quả trả về bằng `assertSame(options, result.get())` trong tình huống API/target cụ thể đã được xác nhận hỗ trợ đúng hành vi đó.

### 21.1. Test không có property dưới prefix

Để kiểm tra `BindResult.isBound()` khi không có source, tạo một Environment test không chứa khóa `app.client.*` hoặc sử dụng một prefix riêng thật sự chưa cấu hình.

Đừng giả định chỉ vì bạn không viết `app.client.host` trong annotation test thì tất cả nguồn khác cũng không có khóa đó; file application và system properties vẫn có thể được nạp.

### 21.2. Test dữ liệu sai kiểu

Cấu hình:

~~~properties
app.client.timeout=invalid-duration
~~~

Kỳ vọng binding/convert báo lỗi thay vì giữ nguyên default `2s`. Nếu ứng dụng cố tình cho phép fallback, phải định nghĩa và kiểm chứng chính sách đó rõ ràng.

### 21.3. Test giá trị rỗng

~~~properties
app.client.host=
~~~

Kỳ vọng không phải “giữ localhost”, vì key đã tồn tại. Viết validation để xác minh host blank bị từ chối.

### 21.4. Test nested object và collection

Đối với nested mutable JavaBean, test getter/setter của object con. Đối với List/Map, test đúng behavior replacement/merge khi có nhiều property sources ưu tiên khác nhau; không chỉ test một nguồn đơn giản.

### 21.5. Không dùng credential thật trong test

Nếu target có password hoặc API key, dùng giá trị giả có dấu hiệu canary và kiểm tra log/error không tiết lộ. Không dán secret production vào source test hay stdout.

## 22. Những hiểu nhầm thường gặp

### 22.1. “`ofInstance` tự tạo object mới”

Không. Nó nhận object **đã được tạo** và xây một `Bindable` chứa existing value. Việc có một instance mới hay không phụ thuộc API và cách bạn gọi binder; `ofInstance` tự nó không tạo target mới.

### 22.2. “Chỉ cần gọi `ofInstance(options)` là đủ”

Không. Phải truyền target vào `Binder.bind` hoặc API tương ứng. Static factory chỉ mô tả target.

### 22.3. “`ofInstance` dùng được để sửa record”

Không nên. Nó ngụ ý existing value/JavaBean binding; record không có setter mutable. Nếu muốn record mới từ cấu hình, chọn constructor binding.

### 22.4. “Không khai báo property thì field mặc định sẽ luôn bị xóa”

Với JavaBean existing object, field không có property mới thường có thể giữ default đã được gán. Nhưng với collection/nested object cần kiểm tra riêng; không khẳng định mọi loại field có cùng behavior.

### 22.5. “List mới sẽ append vào List cũ”

Không nên. Binder có quy tắc thay thế List khi có nguồn ưu tiên cao hơn. Nếu muốn append/merge, định nghĩa cơ chế rõ trong code.

### 22.6. “Binding vào existing object luôn an toàn về concurrency”

Không. Setter có thể được gọi nhiều lần, không có atomic update xuyên các field. Bind trước khi publish hoặc dùng snapshot replacement được thiết kế riêng.

### 22.7. “Có `BindResult` là mọi giá trị đã được validate”

Không. Binding và validation là hai trách nhiệm. Đặc biệt với API thủ công, cần thiết kế validation rõ ràng.

### 22.8. “`ofInstance` làm biến môi trường có ưu tiên cao nhất”

Không. Prefix, thứ tự `PropertySource`, Config Data và môi trường quyết định giá trị nguồn; `ofInstance` chỉ mô tả target.

### 22.9. “Có thể bind object tùy ý không cần setter”

Không. Với existing value, JavaBean binding cần member hoặc nested object có thể cập nhật. Object bất biến không tự trở thành mutable.

### 22.10. “Chỉ cần chuyển đổi kiểu thành công là cấu hình đã dùng được”

Không. `URI` hợp lệ có thể không có host, timeout có thể âm, Resource có thể không đọc được. Validation và kiểm tra tài nguyên vẫn cần thiết.

## 23. Quy trình chẩn đoán khi binding không cập nhật object

Nếu gọi Binder nhưng không thấy thay đổi:

1. **Kiểm tra có thực sự gọi `binder.bind` không.** `ofInstance` đứng một mình không làm việc.
2. **Kiểm tra prefix.** `"app.client"` có đúng với các khóa nguồn `app.client.*` không?
3. **Kiểm tra Environment.** Có được Spring Boot chuẩn bị với đúng profile và Config Data không?
4. **Kiểm tra nguồn thắng.** File ngoài, env vars, system properties hoặc command-line args có ghi đè giá trị mong đợi không?
5. **Kiểm tra `BindResult.isBound()`.** Nếu false, đừng gọi `get()` và đừng tuyên bố đã bind.
6. **Kiểm tra target JavaBean.** Có getter/setter cần thiết, kiểu convert được, nested object có cấu trúc phù hợp không?
7. **Kiểm tra target là record hoặc immutable không.** `ofInstance` không sửa field final.
8. **Kiểm tra giá trị nguồn rỗng hay thiếu.** Hai trạng thái có thể dẫn tới kết quả khác.
9. **Kiểm tra conversion.** `Duration`, `URI`, số và enum cần input hợp lệ.
10. **Kiểm tra collection.** Danh sách có bị source ưu tiên cao hơn thay thế? Generic type có được giữ đúng không?
11. **Kiểm tra có binding tự động thứ hai không.** `@Bean` có `@ConfigurationProperties` hoặc `@Component` có thể khiến object bị bind thêm.
12. **Kiểm tra thời điểm sử dụng.** Object có bị publish trước khi bind xong hay không?
13. **Kiểm tra các setter có side effect không.** Binding không được thiết kế để gọi mạng hoặc thay đổi hệ thống ngoài trong setter.
14. **Kiểm tra validation.** Một object có vẻ được cập nhật nhưng vẫn vi phạm invariant.
15. **Chẩn đoán an toàn.** Không log toàn bộ object nếu có credential; chỉ ghi tên key/nhóm lỗi được phép.

Với Spring Boot Actuator, endpoint `/actuator/env` và `/actuator/configprops` có thể hỗ trợ quan sát property sources và bean đã đăng ký, nhưng chúng phải được bảo vệ và che thông tin nhạy cảm. Một object được tự bind bằng API thủ công **không nhất thiết được hiển thị như bean configuration properties được framework quản lý** nếu không được đăng ký theo cơ chế đó.

## 24. Checklist trước khi dùng `Bindable.ofInstance`

- [ ] Object đã được tạo và **khác null**.
- [ ] Object là JavaBean mutable hoặc có cấu trúc có thể bind phù hợp.
- [ ] Binder được tạo từ đúng `Environment`/`ConfigurationPropertySource`.
- [ ] Prefix được chọn đúng và là tên cấu hình canonical khi phù hợp.
- [ ] Quy tắc precedence của những nguồn cấu hình đã được hiểu.
- [ ] Không dùng `ofInstance` như cách cập nhật record hay immutable value object.
- [ ] Existing values/defaults được thiết kế rõ khi key thiếu.
- [ ] Phân biệt property thiếu, chuỗi rỗng và sai kiểu.
- [ ] Nested JavaBeans có getter/setter hoặc cơ chế cập nhật phù hợp.
- [ ] Collection không bị giả định append/merge ngoài hợp đồng.
- [ ] Không bind trực tiếp raw generic collection khi thiếu metadata phần tử.
- [ ] Gọi Binder **trước khi công khai** object cho nhiều thread.
- [ ] Có quy tắc xử lý khi `BindResult` không bound.
- [ ] Lỗi binding không bị nuốt, object cập nhật dở không được đưa vào sử dụng.
- [ ] Có validation hoặc invariant sau manual bind nếu cấu hình quan trọng.
- [ ] Không trùng binding thủ công với `@ConfigurationProperties` tự động.
- [ ] Test có giá trị cấu hình, không có giá trị và giá trị sai kiểu.
- [ ] Không lộ secret trong log, exception hoặc dữ liệu test.
- [ ] Không coi `ofInstance` là cơ chế refresh cấu hình tự động.
- [ ] Với trường hợp chỉ cần binding một `@Bean`, đã cân nhắc `@Bean` + `@ConfigurationProperties` đơn giản hơn.

## 25. Bài tập áp dụng

### Bài tập 1: Giữ default khi chỉ override timeout

JavaBean có:

~~~java
private String host = "localhost";
private Duration timeout = Duration.ofSeconds(2);
~~~

Cấu hình:

~~~properties
app.client.timeout=5s
~~~

Hãy giải thích vì sao object có thể giữ `host=localhost` nhưng timeout được đổi thành `5s` sau `binder.bind("app.client", Bindable.ofInstance(options))`. Nếu nguồn có thêm `app.client.host=`, điều gì khác?

**Gợi ý:** “không có khóa” khác “có khóa với chuỗi rỗng”.

### Bài tập 2: Phân biệt record và JavaBean

Hai class:

~~~java
public record ImmutableClient(String host, int port) {}
~~~

và:

~~~java
public class MutableClient {
    private String host;
    private int port;
    public String getHost() { return host; }
    public void setHost(String host) { this.host = host; }
    public int getPort() { return port; }
    public void setPort(int port) { this.port = port; }
}
~~~

Nếu yêu cầu là cập nhật **object đã tồn tại**, chọn class nào và vì sao? Nếu yêu cầu là tạo **snapshot bất biến mới** từ cấu hình, nên dùng cơ chế nào?

### Bài tập 3: Tránh binding hai lần

Một method `@Bean` có `@ConfigurationProperties(prefix="vendor.client")`. Developer đồng thời gọi `Binder.get(environment).bind("vendor.client", Bindable.ofInstance(options))` ngay trong method.

Hãy giải thích vì sao đây thường là thiết kế thừa và có thể gây side effect; chọn một cách đăng ký/binding thống nhất.

### Bài tập 4: Xử lý không có kết quả binding

Giả sử toàn bộ `app.client.*` không được khai báo. Hãy xác định có nên:

- dùng object với default đã khởi tạo;
- trả lỗi cấu hình thiếu;
- hoặc đổi sang `Binder.bindOrCreate` theo nhu cầu.

**Không có một đáp án áp dụng cho mọi ứng dụng**; quyết định phải dựa trên hợp đồng cấu hình.

## 26. Kết luận

`Bindable.ofInstance(existing)` là một công cụ nhỏ nhưng quan trọng trong **Spring Boot Binder nâng cao**: nó cho phép code **chỉ định một đối tượng đã có** làm target khi gọi `Binder.bind`. Với JavaBean mutable, Binder có thể áp các property từ nguồn cấu hình phù hợp lên object đó, tận dụng default, setter, nested binding, conversion và relaxed binding.

Tuy nhiên:

- `ofInstance` **không tự bind** và **không tự tạo object**.
- Nó hướng tới **existing value/JavaBean binding**, không phải sửa record bất biến.
- Không có property phù hợp thì `BindResult` có thể không bound.
- List/Map và nested object có quy tắc riêng; không giả định merge theo ý muốn.
- Binding vào mutable instance **không atomic**, không đảm bảo rollback và không tự refresh runtime.
- Validation, logging an toàn và lifecycle vẫn là trách nhiệm của ứng dụng.

Khi chỉ cần một bean cấu hình thông thường, `@ConfigurationProperties` tự động hoặc `@Bean` có annotation là lựa chọn đơn giản hơn. Dùng `Bindable.ofInstance` khi **quyền điều khiển trực tiếp đối với existing target** thật sự mang lại giá trị, và bind trước khi object đi vào sử dụng.

### Tài liệu tham khảo

- [Spring Boot API — Bindable, ofInstance, withExistingValue](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/bind/Bindable.html)
- [Spring Boot API — Binder, bind, bindOrCreate và get(Environment)](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/bind/Binder.html)
- [Spring Boot API — BindResult](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/bind/BindResult.html)
- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot Team — Property Binding in Spring Boot 2.0](https://spring.io/blog/2018/03/28/property-binding-in-spring-boot-2-0/)

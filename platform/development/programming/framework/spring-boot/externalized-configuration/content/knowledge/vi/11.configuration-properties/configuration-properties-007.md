# Mô hình hóa đối tượng lồng nhau và đường dẫn thuộc tính với @ConfigurationProperties trong Spring Boot

## Mục tiêu

Khi ứng dụng Spring Boot còn nhỏ, một vài cấu hình như **server.port** hoặc **app.timeout** có thể được đọc trực tiếp bằng **@Value**. Nhưng khi cấu hình gồm nhiều cấp, danh sách server, nhóm timeout, chính sách retry, kết nối dịch vụ và các giá trị chỉ thay đổi theo môi trường, cách đọc từng khóa riêng lẻ khiến mã khó theo dõi. **@ConfigurationProperties** giúp biến một nhóm thuộc tính thành **một mô hình Java có kiểu dữ liệu rõ ràng**, hỗ trợ đối tượng lồng nhau, collection, chuyển đổi kiểu và validation.

Ví dụ, tệp YAML:

~~~yaml
app:
  client:
    base-url: "https://api.example.test"
    http:
      connect-timeout: 2s
      read-timeout: 5s
      pool:
        max-size: 20
        enabled: true
~~~

có thể được bind vào đối tượng Java theo cấu trúc:

~~~text
AppProperties
└── client
    ├── baseUrl
    └── http
        ├── connectTimeout
        ├── readTimeout
        └── pool
            ├── maxSize
            └── enabled
~~~

Đường dẫn **app.client.http.pool.max-size** mô tả chính xác giá trị **20** cần đi vào trường **maxSize** của đối tượng **pool**, nằm bên trong **http**, rồi **client** của cấu hình **app**.

Bài học giải quyết những câu hỏi thực tế:

- Phân biệt **prefix**, các cấp đường dẫn property và tên trường Java.
- Biểu diễn một cấu hình lồng nhau bằng **record** hoặc **JavaBean**.
- Biết khi nào dùng class con, class static nested, List và Map.
- Hiểu dữ liệu YAML, .properties và biến môi trường cùng hướng đến mô hình Java thế nào.
- Xử lý kiểu Duration, DataSize, enum và giá trị mặc định.
- Áp dụng validation cho từng cấp, kể cả đối tượng nằm sâu bên trong.
- Đọc lỗi bind khi tên property sai cấp, kiểu không đúng hoặc cấu hình bị thiếu.
- Thiết kế cấu hình rõ ràng, dễ mở rộng và dễ kiểm thử.

## 1. Ba tầng cần tách biệt

Khi làm việc với @ConfigurationProperties, hãy hình dung một pipeline:

~~~text
Nguồn cấu hình
(application.yml / .properties / env / CLI / ...)
       |
       v
Spring Environment + thứ tự PropertySource
       |
       v
Tên property có cấu trúc
app.client.http.connect-timeout
       |
       v
Binder của Spring Boot
(relaxed binding + conversion + validation)
       |
       v
Đối tượng Java
AppProperties.client().http().connectTimeout()
~~~

**Tầng nguồn:** giá trị có thể đến từ tệp cấu hình, biến môi trường, JVM system property hoặc tham số dòng lệnh. Nếu một thuộc tính xuất hiện ở nhiều nguồn, Spring áp dụng mức ưu tiên tương ứng trước hoặc trong quá trình binder đọc giá trị.

**Tầng tên thuộc tính:** các dấu chấm **.** biểu diễn từng cấp logic. Dấu gạch ngang **-** trong **connect-timeout** là cách viết kebab-case của một tên thuộc tính ghép; nó không tạo thêm một cấp.

**Tầng mô hình Java:** binder chuyển đường dẫn thuộc tính thành field, record component hoặc constructor parameter, đồng thời chuyển giá trị sang kiểu Java tương ứng.

Khi có lỗi, đừng gộp ba tầng lại thành “YAML không hoạt động”. Một YAML hợp lệ có thể bind sai vì cấp cấu hình không đúng; một tên property chính xác có thể nhận giá trị khác vì nguồn ưu tiên hơn; một giá trị được tìm thấy có thể vẫn không chuyển được thành kiểu Java.

## 2. Prefix là điểm bắt đầu của một nhóm cấu hình

Annotation cơ bản:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(String name) {
}
~~~

Trong ví dụ, **prefix = "app"** yêu cầu binder tìm các thuộc tính trong nhóm **app**. Field **name** tương ứng với khóa đầy đủ:

~~~properties
app.name=Inventory Service
~~~

hoặc:

~~~yaml
app:
  name: "Inventory Service"
~~~

Nếu đổi prefix thành **platform.app**:

~~~java
@ConfigurationProperties(prefix = "platform.app")
public record AppProperties(String name) {
}
~~~

thì đường dẫn tương ứng đổi thành **platform.app.name**. Binder không tự tìm **app.name** chỉ vì tên class vẫn là AppProperties.

### 2.1. Prefix phải rõ ràng và có ý nghĩa

Trong Spring Boot, tên prefix nên dùng dạng canonical: chữ thường, các cấp cách nhau bằng dấu chấm và các phần tên ghép theo kebab-case. Ví dụ:

~~~text
app
app.client
app.notifications
payment.gateway
integration.catalog
~~~

Nếu nhóm thuộc tính thuộc về tích hợp riêng, nên chọn prefix có phạm vi cụ thể như **integration.catalog** thay vì **config** hoặc **settings**. Prefix rõ giúp tránh va chạm với thuộc tính của Spring Boot và các thư viện khác.

### 2.2. Tên class không quyết định prefix

Hai class có tên khác nhau nhưng cùng prefix có thể đọc cùng nguồn thuộc tính. Ngược lại, hai class cùng tên ở các package khác nhau có prefix khác nhau sẽ bind từ các vùng cấu hình khác nhau.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(String baseUrl) {
}
~~~

Record trên đọc **app.client.base-url**, không đọc **client.base-url** hoặc **app.base-url**.

Vì vậy khi truy nguyên lỗi, cần đọc cả **prefix** và **tên trường lồng nhau** để tạo tên property đầy đủ.

## 3. Mô hình record lồng nhau: ví dụ hoàn chỉnh

Giả sử ứng dụng cần nhóm cấu hình HTTP client với pool kết nối và retry. Ta có YAML:

~~~yaml
app:
  name: "Order Service"
  client:
    base-url: "https://orders.example.test"
    http:
      connect-timeout: 2s
      read-timeout: 10s
      pool:
        enabled: true
        max-size: 30
    retry:
      max-attempts: 4
      backoff: 500ms
~~~

Một mô hình bằng Java record:

~~~java
package example.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(
        String name,
        Client client
) {
    public record Client(
            String baseUrl,
            Http http,
            Retry retry
    ) {}

    public record Http(
            Duration connectTimeout,
            Duration readTimeout,
            Pool pool
    ) {}

    public record Pool(
            boolean enabled,
            int maxSize
    ) {}

    public record Retry(
            int maxAttempts,
            Duration backoff
    ) {}
}
~~~

Các record con mô tả cấu trúc dữ liệu, không cần có annotation **@ConfigurationProperties** riêng cho từng cấp.

Sau khi được đăng ký thành bean, ứng dụng có thể dùng:

~~~java
import org.springframework.stereotype.Service;
import example.config.AppProperties;

@Service
public class ClientSummary {

    private final AppProperties properties;

    public ClientSummary(AppProperties properties) {
        this.properties = properties;
    }

    public String describe() {
        var client = properties.client();
        var http = client.http();

        return "name=" + properties.name()
                + ", baseUrl=" + client.baseUrl()
                + ", connectTimeout=" + http.connectTimeout()
                + ", poolSize=" + http.pool().maxSize()
                + ", retryCount=" + client.retry().maxAttempts();
    }
}
~~~

Điểm cốt lõi: **properties.client().http().pool().maxSize()** là cách truy cập qua mô hình Java. Binder tìm dữ liệu bằng tên property **app.client.http.pool.max-size**.

### 3.1. Vì sao record phù hợp?

Record giúp biểu diễn cấu hình dạng dữ liệu tương đối bất biến sau khi khởi tạo. Với một constructor thích hợp, Spring Boot có thể bind giá trị qua constructor parameters. Tên component trong record như **baseUrl** được liên kết với **base-url** nhờ relaxed binding.

Tính bất biến làm rõ rằng cấu hình được tạo trong giai đoạn khởi động chứ không phải một object dự kiến bị sửa tùy tiện bởi các service.

Một số dự án vẫn cần class có setter vì thư viện cũ, yêu cầu mutation hoặc chiến lược binding khác. Cả record và JavaBean đều có chỗ dùng; chọn cách mô hình hóa phù hợp với cơ chế binder của phiên bản Spring Boot đang chạy.

### 3.2. Đăng ký record cấu hình thành Spring bean

Một cách đăng ký ở ứng dụng Spring Boot:

~~~java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Với cách này, record AppProperties cần nằm trong package mà **@ConfigurationPropertiesScan** quét được, ví dụ package con **example.config**.

Một cách đăng ký tường minh khác:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;
import example.config.AppProperties;

@Configuration
@EnableConfigurationProperties(AppProperties.class)
class PropertiesRegistration {
}
~~~

**@ConfigurationProperties** gắn trên record mô tả cách bind nhưng không nhất thiết tự khiến record trở thành bean. Nếu quên scan hoặc enable, ứng dụng có thể báo không tìm được bean AppProperties khi inject.

Đừng dùng đồng thời nhiều cơ chế đăng ký cho cùng một class nếu chưa hiểu cách Spring đặt tên và xử lý bean; mục tiêu là có một bean cấu hình rõ ràng.

## 4. Tạo bảng ánh xạ đường dẫn property

Từ mô hình ở mục 3, có thể tạo bảng đối chiếu:

| Đường dẫn canonical | Đường đi trong record | Kiểu Java | Ví dụ giá trị |
| --- | --- | --- | --- |
| app.name | name() | String | Order Service |
| app.client.base-url | client().baseUrl() | String | https://orders.example.test |
| app.client.http.connect-timeout | client().http().connectTimeout() | Duration | 2s |
| app.client.http.read-timeout | client().http().readTimeout() | Duration | 10s |
| app.client.http.pool.enabled | client().http().pool().enabled() | boolean | true |
| app.client.http.pool.max-size | client().http().pool().maxSize() | int | 30 |
| app.client.retry.max-attempts | client().retry().maxAttempts() | int | 4 |
| app.client.retry.backoff | client().retry().backoff() | Duration | 500ms |

Bảng này hữu ích khi viết tài liệu vận hành hoặc giao việc tạo biến môi trường. Nó cho thấy tên method Java **maxSize()** chỉ tương ứng một phần tên **max-size** trong đường dẫn cấu hình đầy đủ.

### 4.1. Dấu chấm và dấu gạch ngang không thay cho nhau

Xét hai đường dẫn:

~~~text
app.client.http.read-timeout
app.client.http.read.timeout
~~~

Đường dẫn đầu biểu diễn **readTimeout** là một field trong Http. Đường dẫn sau biểu diễn cấp **read** chứa field **timeout**.

Chúng không tự động tương đương chỉ vì cách đọc bằng tiếng Anh gần giống nhau.

Đối với record đang dùng:

~~~java
public record Http(Duration connectTimeout, Duration readTimeout, Pool pool) {}
~~~

đường dẫn mong đợi là **app.client.http.read-timeout**. Nếu YAML có:

~~~yaml
app:
  client:
    http:
      read:
        timeout: 10s
~~~

thì dữ liệu được đưa vào đường dẫn **app.client.http.read.timeout**, không phải field **Http.readTimeout** như dự kiến.

### 4.2. Thụt lề YAML chính là một phần của đường dẫn

Đúng:

~~~yaml
app:
  client:
    http:
      pool:
        enabled: true
        max-size: 30
~~~

Sai cấp nhưng có thể là YAML hợp lệ:

~~~yaml
app:
  client:
    http:
      pool:
        enabled: true
      max-size: 30
~~~

Đoạn thứ hai tạo **app.client.http.max-size** thay vì **app.client.http.pool.max-size**. Binder không tự dời thuộc tính sang đối tượng Pool.

Khi gặp một field nhận giá trị 0 hoặc null ngoài dự đoán, hãy kiểm tra **toàn bộ đường dẫn**, không chỉ tên của dòng cuối cùng.

## 5. Cùng mô hình ở định dạng .properties

Định dạng properties không dùng thụt lề để mô tả cấu trúc, mà biểu diễn đường dẫn đầy đủ trên từng dòng:

~~~properties
app.name=Order Service
app.client.base-url=https://orders.example.test
app.client.http.connect-timeout=2s
app.client.http.read-timeout=10s
app.client.http.pool.enabled=true
app.client.http.pool.max-size=30
app.client.retry.max-attempts=4
app.client.retry.backoff=500ms
~~~

Cả YAML và .properties đều có thể bind vào cùng AppProperties. Cần phân biệt **cấu trúc property logic** với **cách định dạng file**:

- YAML dùng mapping lồng nhau để biểu diễn các cấp.
- .properties dùng dấu chấm trong tên khóa.
- Binder đọc tên property sau khi các nguồn được nạp, không yêu cầu mô hình Java biết file gốc thuộc định dạng nào.

Không nên sử dụng đồng thời application.yml và application.properties ở cùng location một cách thiếu chủ đích rồi giả định Spring sẽ gộp chúng theo thứ tự tùy ý. Khi cần nhiều nguồn, xác định rõ thứ tự ưu tiên của Config Data hoặc cấu hình import/location.

## 6. Các kiểu dữ liệu lồng nhau không nhất thiết đều là String

Một lợi ích quan trọng của @ConfigurationProperties là **type-safe binding**. Trong record ví dụ, Spring Boot chuyển các chuỗi cấu hình thành các kiểu Java:

~~~yaml
app:
  client:
    http:
      connect-timeout: 250ms
      read-timeout: 5s
      pool:
        max-size: 25
        enabled: true
~~~

Các kết quả tương ứng:

~~~text
connectTimeout -> Duration biểu diễn 250 mili giây
readTimeout    -> Duration biểu diễn 5 giây
maxSize        -> int 25
enabled        -> boolean true
~~~

Nếu khai báo **max-size: many**, binder không thể chuyển **many** sang int. Nếu khai báo **read-timeout: yesterday**, binder không thể hiểu đó là Duration hợp lệ.

Spring Boot hỗ trợ các kiểu quen thuộc như:

- **String**, **int/Integer**, **long/Long**, **boolean/Boolean**.
- **Duration** cho timeout, backoff hoặc interval.
- **DataSize** cho kích thước bộ đệm, giới hạn dữ liệu hoặc cache.
- **Enum** cho tập giá trị hữu hạn.
- **List**, **Set**, **Map** và các cấu trúc Java tương thích.
- Những kiểu bổ sung khi có converter/binder phù hợp.

Ví dụ record có DataSize:

~~~java
import org.springframework.util.unit.DataSize;

public record Upload(int maxFiles, DataSize maxFileSize) {}
~~~

Cấu hình:

~~~yaml
app:
  upload:
    max-files: 10
    max-file-size: 25MB
~~~

Nếu bean @ConfigurationProperties gốc có một field **Upload upload**, binder có thể tạo Upload với maxFiles bằng 10 và maxFileSize theo đơn vị MB mà Spring Boot hỗ trợ.

Với Duration hoặc DataSize không ghi đơn vị, Spring Boot dùng đơn vị mặc định theo kiểu và annotation/cấu hình đi kèm. Để giảm mơ hồ, nên viết đơn vị rõ như **500ms**, **5s**, **10MB**, và dùng annotation **@DurationUnit** hoặc **@DataSizeUnit** khi cần thay quy tắc mặc định.

## 7. Record nested và giá trị mặc định

Một record không có setter, nên cơ chế constructor binding nhận dữ liệu tại thời điểm tạo object. Điều này cũng khiến vấn đề **thuộc tính bị thiếu** cần được thiết kế rõ.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "app")
public record AppProperties(String name, Client client) {
    public record Client(String baseUrl, int retries) {}
}
~~~

Nếu application.yml chỉ khai báo:

~~~yaml
app:
  name: Demo
~~~

thì **client** có thể không được tạo vì không có cấu hình cho nhóm ấy, dẫn tới khả năng **properties.client() == null** nếu mô hình không khai báo default hoặc ràng buộc bổ sung.

Nếu client bắt buộc, hãy dùng validation hoặc thiết kế constructor/config data để đảm bảo nó hiện diện. Không nên truy cập chuỗi **properties.client().baseUrl()** mà không có hợp đồng rõ cho trường hợp thiếu nhóm cấu hình.

### 7.1. @DefaultValue trên constructor-bound properties

Trong Spring Boot có hỗ trợ constructor binding tương ứng, có thể dùng annotation **@DefaultValue** để biểu diễn default cho constructor parameter/record component.

Ví dụ:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        @DefaultValue("3") int retries,
        @DefaultValue("5s") Duration timeout
) {}
~~~

Nếu các property **app.client.retries** hoặc **app.client.timeout** vắng mặt, binder có thể dùng các default được chỉ định. Việc có và cách sử dụng annotation phụ thuộc phiên bản Spring Boot; hãy bám vào API của phiên bản dự án.

Một hướng khác đơn giản là định nghĩa default trong application.yml:

~~~yaml
app:
  client:
    retries: 3
    timeout: 5s
~~~

Sau đó cho phép profile hoặc env var ghi đè. Với cấu hình vận hành, đặt default trong file nền giúp người đọc nhìn thấy giá trị mà ứng dụng dùng khi không override.

### 7.2. Tạo nested object ngay cả khi chưa có khóa con

Với constructor binding, có phiên bản hỗ trợ đánh dấu một nested parameter bằng **@DefaultValue** rỗng để binder tạo nested object ngay khi không có property con tương ứng, giúp các default của nested component được áp dụng.

Ví dụ ý tưởng:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @DefaultValue Client client
) {
    public record Client(
            @DefaultValue("3") int retries
    ) {}
}
~~~

Điều này khác với việc đặt null rồi mong Java tự tạo nested object. Khi chọn thiết kế này, cần kiểm tra khả năng hỗ trợ của version Spring Boot và các ràng buộc constructor binding đang sử dụng.

## 8. Mô hình JavaBean lồng nhau: phương án mutable

Không phải project nào cũng dùng Java record. Một class có getter/setter và nested class vẫn có thể bind cấu hình.

Ví dụ:

~~~java
package example.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "service")
public class ServiceProperties {

    private String name;
    private Http http = new Http();

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Http getHttp() {
        return http;
    }

    public void setHttp(Http http) {
        this.http = http;
    }

    public static class Http {
        private Duration timeout = Duration.ofSeconds(5);
        private int maxConnections = 10;

        public Duration getTimeout() {
            return timeout;
        }

        public void setTimeout(Duration timeout) {
            this.timeout = timeout;
        }

        public int getMaxConnections() {
            return maxConnections;
        }

        public void setMaxConnections(int maxConnections) {
            this.maxConnections = maxConnections;
        }
    }
}
~~~

YAML tương ứng:

~~~yaml
service:
  name: "Catalog Service"
  http:
    timeout: 8s
    max-connections: 40
~~~

Binder có thể gán:

~~~text
service.name                  -> ServiceProperties.name
service.http.timeout          -> ServiceProperties.http.timeout
service.http.max-connections  -> ServiceProperties.http.maxConnections
~~~

Ở đây Http được khởi tạo bằng **new Http()** và có giá trị mặc định tại field. Điều đó thể hiện một chiến lược **JavaBean binding** khác với record/constructor binding.

### 8.1. Khi nào nested object cần khởi tạo sẵn?

Nếu dùng setter binding và muốn binder cập nhật những thuộc tính trong một nested bean, cần đảm bảo đối tượng nested có thể được tạo hoặc có sẵn theo contract binder đang dùng. Khởi tạo sẵn nested mutable object như **private Http http = new Http()** là cách rõ ràng trong ví dụ này.

Nếu cố ý để nested field null và không có đường tạo/set phù hợp, kết quả binding có thể không như dự kiến. Không nên đoán rằng binder luôn tự tạo mọi object ở mọi cấp trong mọi kiểu Java.

### 8.2. Record và JavaBean không nên trộn mô hình một cách ngẫu nhiên

Record phù hợp với dữ liệu được tạo qua constructor và sau đó không sửa. JavaBean phù hợp khi code cũ yêu cầu setter hoặc khi đang bind vào đối tượng có thể thay đổi.

Trước khi đưa setter vào một record hay trộn constructor cùng setter trong nhiều tầng, hãy chọn một chiến lược rõ ràng theo phiên bản Spring Boot và cách đăng ký bean. Điều này giúp việc áp dụng default, validation và unit test nhất quán.

## 9. Constructor binding cần hiểu theo phiên bản Spring Boot

Spring Boot đã phát triển cơ chế constructor binding qua các phiên bản. Với Spring Boot 3 và các record thông dụng, một constructor duy nhất thường được suy ra cho mục đích bind cấu hình. Khi class có nhiều constructor, có thể cần chú thích **@ConstructorBinding** vào constructor phù hợp.

Ví dụ một class có constructor chỉ định:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.ConstructorBinding;

@ConfigurationProperties(prefix = "app")
public class TypedProperties {

    private final String name;

    @ConstructorBinding
    public TypedProperties(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
~~~

Cú pháp package và vị trí annotation có khác biệt đáng kể giữa một số phiên bản Spring Boot 2.x và 3.x. Khi dự án đang dùng một phiên bản cố định, cần xem API tương ứng thay vì copy một snippet annotation từ version khác.

Một lưu ý quan trọng: **constructor binding có vòng đời do cơ chế đăng ký @ConfigurationProperties quản lý**. Đừng coi một bean được tạo tùy ý qua @Component hoặc @Bean là chắc chắn có cùng quá trình constructor binding. Với class cấu hình dạng record, dùng **@ConfigurationPropertiesScan** hoặc **@EnableConfigurationProperties** là cách đăng ký dễ hiểu.

## 10. List của đối tượng lồng nhau

Đối tượng lồng nhau không chỉ là một quan hệ cha-con. Một ứng dụng có thể cần danh sách nhiều endpoint hoặc server.

YAML:

~~~yaml
app:
  servers:
    - name: alpha
      host: alpha.example.test
      port: 8081
    - name: beta
      host: beta.example.test
      port: 8082
~~~

Record:

~~~java
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record ServerProperties(List<Server> servers) {
    public record Server(String name, String host, int port) {}
}
~~~

Dữ liệu được bind theo các đường dẫn logic:

~~~text
app.servers[0].name
app.servers[0].host
app.servers[0].port

app.servers[1].name
app.servers[1].host
app.servers[1].port
~~~

Ví dụ khi dùng:

~~~java
for (ServerProperties.Server server : properties.servers()) {
    System.out.println(server.name() + ": " + server.host() + ":" + server.port());
}
~~~

Nếu muốn có list rỗng mặc định hoặc bắt buộc có ít nhất một server, hãy thể hiện điều đó bằng constructor default hoặc validation; không mặc định rằng **servers()** luôn không null khi YAML hoàn toàn thiếu khóa servers.

### 10.1. Trong .properties

~~~properties
app.servers[0].name=alpha
app.servers[0].host=alpha.example.test
app.servers[0].port=8081
app.servers[1].name=beta
app.servers[1].host=beta.example.test
app.servers[1].port=8082
~~~

Chỉ số **[0]** và **[1]** là một phần đường dẫn List. Nó không phải ký hiệu của một nested object thông thường có tên “0” hoặc “1”.

### 10.2. Biến môi trường cho List

Theo cách chuyển tên canonical sang environment variables trong Spring Boot, các chỉ số List được bao quanh bởi dấu gạch dưới:

~~~text
APP_SERVERS_0_NAME
APP_SERVERS_0_HOST
APP_SERVERS_0_PORT
APP_SERVERS_1_NAME
APP_SERVERS_1_HOST
APP_SERVERS_1_PORT
~~~

Ví dụ:

~~~bash
APP_SERVERS_0_NAME=alpha APP_SERVERS_0_HOST=alpha.example.test APP_SERVERS_0_PORT=8081 java -jar demo.jar
~~~

Nếu có nhiều nguồn định nghĩa List, không nên coi việc ghi đè một phần tử ở một nguồn ưu tiên cao hơn là thao tác thêm phần tử theo kiểu merge. Với Spring Boot, **List từ nguồn ưu tiên cao thường thay thế List ở nguồn ưu tiên thấp**, nên cần xác định danh sách hoàn chỉnh cần có ở nguồn được chọn.

### 10.3. List và Set

**List** giữ thứ tự và có chỉ số, nên phù hợp với endpoints theo thứ tự ưu tiên hoặc một nhóm server cần danh sách có vị trí. **Set** có ý nghĩa tập hợp không chứa phần tử trùng lặp theo equality và không nên được dùng khi vị trí phần tử có ý nghĩa nghiệp vụ.

Với các phần tử nested object, List thường dễ biểu diễn trong YAML và dễ truy nguyên khi cần debug bằng đường dẫn **app.servers[0]**.

## 11. Map của đối tượng lồng nhau

Có lúc cấu hình mang các key động, ví dụ theo mã vùng hoặc tên tenant. Khi không muốn tạo một Java field cho từng vùng, Map là lựa chọn phù hợp.

YAML:

~~~yaml
app:
  regions:
    asia:
      endpoint: "https://asia.example.test"
      timeout: 3s
    europe:
      endpoint: "https://europe.example.test"
      timeout: 5s
~~~

Record:

~~~java
import java.time.Duration;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record RegionProperties(Map<String, Region> regions) {

    public record Region(String endpoint, Duration timeout) {}
}
~~~

Ví dụ truy cập:

~~~java
RegionProperties.Region asia = properties.regions().get("asia");
System.out.println(asia.endpoint());
~~~

Các đường dẫn logic:

~~~text
app.regions.asia.endpoint
app.regions.asia.timeout
app.regions.europe.endpoint
app.regions.europe.timeout
~~~

Trong trường hợp này, **asia** và **europe** không phải tên field Java được định nghĩa sẵn. Chúng là key của Map. Đây là khác biệt bản chất so với nested record có field **asia** và **europe** cố định.

### 11.1. Map với key có ký tự đặc biệt

Giả sử key thực sự là **tenant.eu** (chứa dấu chấm là một phần tên tenant), không phải đường dẫn gồm hai cấp tenant và eu. Khi biểu diễn trong YAML, có thể dùng bracket notation để bảo toàn key khi binding Map:

~~~yaml
app:
  tenants:
    "[tenant.eu]":
      endpoint: "https://eu.example.test"
~~~

Trong .properties:

~~~properties
app.tenants.[tenant.eu].endpoint=https://eu.example.test
~~~

Dấu ngoặc vuông giúp biểu diễn **tenant.eu** như một key, thay vì phân tách dấu chấm thành một cấp khác. Trong YAML, nên đặt toàn bộ key có bracket trong dấu nháy để parser đọc đúng.

Một số key có dấu gạch chéo hoặc ký tự đặc biệt khác cũng cần bracket notation. Với **Map<String, String>** và **Map<String, Object>**, quy tắc binding có thể khác nhau ở việc giữ dấu chấm, vì vậy hãy mô hình hóa key rõ ràng và xác minh khi cần xử lý tên không chuẩn.

### 11.2. Cấu hình List hay Map?

Nếu các endpoint được nhận diện bằng vị trí **[0]**, **[1]** và thứ tự quan trọng, dùng List. Nếu được tra cứu qua key động như **asia**, **europe**, **tenant.eu**, dùng Map. Nếu mỗi endpoint là một khái niệm cố định riêng có ý nghĩa trong ứng dụng, có thể dùng nested object với field cụ thể.

Không nhất thiết chọn Map chỉ vì YAML nhìn có nhiều cấp. **Kiểu Java mong muốn và cách truy cập ở nghiệp vụ** mới quyết định List, Map hay object.

## 12. Nested enum và những giá trị lựa chọn

Giả sử ứng dụng hỗ trợ hai chiến lược retry:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.retry")
public record RetryProperties(Mode mode, int maxAttempts) {
    public enum Mode {
        FIXED, EXPONENTIAL
    }
}
~~~

Cấu hình:

~~~yaml
app:
  retry:
    mode: exponential
    max-attempts: 4
~~~

Spring Boot hỗ trợ chuyển đổi enum với cơ chế binding linh hoạt phù hợp, để giá trị cấu hình biểu diễn một phần tử trong enum. Nếu giá trị không thuộc tập hợp được hỗ trợ hoặc không thể chuyển đổi, ứng dụng có thể báo lỗi bind.

Đưa chiến lược về enum làm hợp đồng cấu hình chặt chẽ hơn so với một chuỗi tùy ý:

~~~java
if ("exponetial".equals(mode)) {
    // Sai chính tả nhưng compiler không phát hiện
}
~~~

Trong thực tế, với cấu hình mang nhiều lựa chọn, enum giúp lỗi chính tả được phát hiện khi bind. Nếu muốn alias hoặc giá trị tùy chỉnh, hãy định nghĩa converter phù hợp thay vì để logic nghiệp vụ đoán các biến thể String.

## 13. Validation cho cấu hình nhiều cấp

Một mô hình nested có thể được tạo thành công nhưng vẫn chứa dữ liệu không hợp lệ về mặt nghiệp vụ: timeout âm, số kết nối bằng 0, URL trống hoặc danh sách server rỗng.

Có thể dùng Jakarta Bean Validation cùng **@Validated**, **@Valid** và các constraint phù hợp:

~~~java
import java.time.Duration;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record ValidatedAppProperties(
        @NotBlank String name,
        @Valid @NotNull Http http,
        @Valid @NotEmpty List<Server> servers
) {
    public record Http(
            @NotNull Duration readTimeout,
            @Min(1) int maxConnections
    ) {}

    public record Server(
            @NotBlank String host,
            @Min(1) int port
    ) {}
}
~~~

YAML hợp lệ về mặt nghiệp vụ:

~~~yaml
app:
  name: Order Service
  http:
    read-timeout: 5s
    max-connections: 20
  servers:
    - host: primary.example.test
      port: 8080
~~~

Khi bean được đăng ký và ứng dụng có dependency validation tương thích, Spring Boot có thể phát hiện một số giá trị vi phạm ràng buộc ngay trong giai đoạn bind/khởi động.

### 13.1. @Valid giúp đi sâu vào nested object

**@Validated** trên class cấu hình giúp kích hoạt validation cho quá trình binding. **@Valid** trên các thành phần nested cho phép kiểm tra lan xuống object con hoặc phần tử collection, theo khả năng hỗ trợ của validation provider.

Ví dụ nếu chỉ có:

~~~java
public record Config(Http http) {}
~~~

mà không có yêu cầu validate nested, những constraint ở lớp Http có thể không được thực thi theo cách bạn mong muốn. Với cấu hình lồng nhau, cần chú ý đặt **@Valid** ở ranh giới xuống cấp con.

### 13.2. @NotNull không giống @NotBlank

- **@NotNull**: yêu cầu giá trị không null.
- **@NotBlank**: dành cho CharSequence, yêu cầu có ký tự không phải khoảng trắng.
- **@NotEmpty**: yêu cầu collection, array, Map hoặc chuỗi không rỗng theo kiểu được hỗ trợ.
- **@Min(1)**: yêu cầu số nguyên có giá trị từ 1 trở lên.

Ví dụ **@NotNull String baseUrl** có thể vẫn cho phép chuỗi rỗng, trong khi **@NotBlank** loại bỏ chuỗi rỗng hoặc toàn dấu cách.

### 13.3. Không tin primitive default trong cấu hình bắt buộc

Với kiểu nguyên thủy như int và boolean, khi một property thiếu, có những chiến lược binding có thể dẫn đến giá trị **0** hoặc **false** mà không thể phân biệt được với giá trị đã được người vận hành khai báo đúng như vậy.

Nếu số kết nối phải lớn hơn 0, **@Min(1)** giúp phát hiện 0. Nếu cần phân biệt **không được cung cấp** với **được cung cấp false**, có thể dùng kiểu bao **Boolean** và validation, hoặc xây dựng một hợp đồng cấu hình rõ ràng.

Không đặt giá trị mặc định vô điều kiện cho thông số bắt buộc về bảo mật hoặc kết nối nếu mục tiêu là phải từ chối khởi động khi thiếu.

## 14. Null, nhóm vắng mặt và chuỗi rỗng

Đối với nested properties, một nhóm có thể hoàn toàn không được khai báo:

~~~yaml
app:
  name: Demo
~~~

hoặc được khai báo với một child:

~~~yaml
app:
  name: Demo
  http:
    read-timeout: 5s
~~~

Hai trường hợp không nhất thiết tạo cùng một object Java. Với constructor binding, khi không có dữ liệu cho nhánh **http**, nested object có thể là null nếu không có default hoặc cơ chế tạo object phù hợp.

Trong khi đó:

~~~yaml
app:
  http:
    read-timeout: ""
~~~

thể hiện một **chuỗi rỗng** trong dữ liệu YAML. Binder cần chuyển chuỗi ấy sang Duration; nó không tự đồng nghĩa với 0 giây hoặc một default mong muốn.

Và:

~~~yaml
app:
  http:
    read-timeout: null
~~~

biểu diễn null scalar ở tầng YAML. Cách scalar null được đưa vào PropertySource và binder cần xét theo cơ chế Spring Boot đang dùng; không thể chắc chắn rằng dòng này sẽ xóa giá trị từ một nguồn cấu hình ưu tiên thấp hơn.

Nếu một nhóm cấu hình là bắt buộc, hãy dùng nested validation/constructor contract. Nếu nhóm đó tùy chọn, diễn đạt điều kiện sử dụng rõ ràng:

~~~java
if (properties.client() != null) {
    // Sử dụng cấu hình client khi có
}
~~~

hoặc thiết kế default object phù hợp.

Đừng tạo ra một nested object giả định luôn có đầy đủ trường bắt buộc chỉ vì field được khai báo trong class Java.

## 15. Biến môi trường và đường dẫn nested

Trong các hệ thống triển khai, mỗi cấp của tên property được chuyển thành một phần của tên biến môi trường.

Quy tắc chuyển tên canonical Spring Boot sang environment variable name:

1. Dấu chấm **.** thành dấu gạch dưới **_**.
2. Bỏ dấu gạch ngang **-**.
3. Chuyển chữ cái thành chữ hoa.

Ví dụ:

| Property canonical | Biến môi trường |
| --- | --- |
| app.name | APP_NAME |
| app.client.base-url | APP_CLIENT_BASEURL |
| app.client.http.connect-timeout | APP_CLIENT_HTTP_CONNECTTIMEOUT |
| app.client.http.pool.max-size | APP_CLIENT_HTTP_POOL_MAXSIZE |
| app.client.retry.max-attempts | APP_CLIENT_RETRY_MAXATTEMPTS |
| app.servers[0].host | APP_SERVERS_0_HOST |
| app.servers[1].port | APP_SERVERS_1_PORT |

Chú ý **connect-timeout** thành **CONNECTTIMEOUT**, không phải một cách máy móc **CONNECT_TIMEOUT**. Dấu gạch dưới thay **dấu chấm của các cấp**, không thay mọi dấu gạch ngang.

Ví dụ chạy:

~~~bash
APP_CLIENT_HTTP_CONNECTTIMEOUT=4s APP_CLIENT_HTTP_POOL_MAXSIZE=50 java -jar demo.jar
~~~

Nếu không có nguồn ưu tiên cao hơn, các giá trị này có thể ghi đè file application.yml.

### 15.1. Nested path sai sẽ tạo env var sai

Nếu Java record có:

~~~java
public record Client(Http http) {}
public record Http(Pool pool) {}
public record Pool(int maxSize) {}
~~~

và prefix là **app.client**, đường dẫn đầy đủ là **app.client.http.pool.max-size**. Nếu chỉ khai báo **APP_CLIENT_POOL_MAXSIZE**, bạn đã bỏ cấp **http**, nên binder không tự điền vào nhánh mong đợi.

Một cách kiểm tra tốt là viết ra **đường dẫn property đầy đủ trước**, rồi mới tính tên biến môi trường.

### 15.2. Docker và Kubernetes không tự hiểu Java field

Ví dụ một Pod container:

~~~yaml
containers:
  - name: order-service
    image: example/order-service:latest
    env:
      - name: APP_CLIENT_HTTP_CONNECTTIMEOUT
        value: "4s"
      - name: APP_CLIENT_HTTP_POOL_MAXSIZE
        value: "50"
~~~

Kubernetes chỉ cấp environment variables vào tiến trình. Nó không biết rằng record Java có một component **maxSize**. Cơ chế chuyển tên và bind do Spring Boot thực hiện khi ứng dụng chạy.

Nếu những biến được định nghĩa trong ConfigMap hoặc Secret, cần bảo đảm resource thực sự được tham chiếu vào Pod bằng env/envFrom hoặc một phương thức mount thích hợp. Sự tồn tại của ConfigMap không tự làm giá trị xuất hiện trong Spring Environment.

## 16. Nhiều nguồn cấu hình và thứ tự ghi đè

Giả sử file nền:

~~~yaml
app:
  client:
    http:
      read-timeout: 5s
      pool:
        max-size: 10
~~~

File theo profile prod:

~~~yaml
app:
  client:
    http:
      read-timeout: 10s
      pool:
        max-size: 30
~~~

Lệnh khởi động:

~~~bash
APP_CLIENT_HTTP_READTIMEOUT=12s java -Dapp.client.http.pool.max-size=40 -jar demo.jar   --spring.profiles.active=prod   --app.client.http.read-timeout=15s
~~~

Nếu sử dụng cơ chế PropertySource thông thường và không có nguồn cao hơn ngoài những nguồn trên, các giá trị có hiệu lực:

~~~text
app.client.http.read-timeout   = 15s
app.client.http.pool.max-size  = 40
~~~

**read-timeout** từ CLI có thể thắng biến môi trường 12s, file prod 10s và file nền 5s. **max-size** từ JVM system property 40 có thể thắng file prod 30 và file nền 10.

Nested binding không tạo một thứ tự ưu tiên riêng cho mỗi cấp object. Binder lấy giá trị của từng đường dẫn theo hệ thống nguồn cấu hình của Spring.

### 16.1. Có ghi đè cả object con không?

Với các scalar nằm trong một object lồng nhau, giá trị ở các nguồn có thể được kết hợp theo từng đường dẫn property. Ví dụ nguồn ưu tiên hơn chỉ khai báo **app.client.http.read-timeout**, còn **connect-timeout** vẫn có thể đến từ nguồn thấp hơn.

Nhưng với **List**, Spring Boot có quy tắc binding riêng và danh sách ở nguồn ưu tiên cao có thể thay thế danh sách nguồn thấp, không tự động nối hoặc hợp nhất từng phần tử. Với **Map**, các key khác nhau có thể được kết hợp từ nhiều nguồn.

Không suy diễn rằng toàn bộ object nested sẽ luôn được thay thế giống List, hay mọi nested collection luôn merge như Map. Cần xét kiểu Java tại cấp đang được bind.

## 17. @NestedConfigurationProperty dùng để làm gì?

Một annotation dễ gây hiểu nhầm là **@NestedConfigurationProperty**. Nó thường liên quan đến việc mô tả nested property cho **configuration metadata**, nhất là khi một field có kiểu đối tượng riêng không thuộc trường hợp nested tự động được công cụ metadata nhận diện.

Ví dụ:

~~~java
import org.springframework.boot.context.properties.NestedConfigurationProperty;

public class FeatureProperties {

    @NestedConfigurationProperty
    private Limits limits;

    public Limits getLimits() {
        return limits;
    }

    public void setLimits(Limits limits) {
        this.limits = limits;
    }
}
~~~

Nếu dùng kiểu class ở package ngoài hoặc một kiểu không được bộ xử lý metadata tự nhận diện là nested, annotation có thể giúp IDE và tài liệu metadata hiểu rằng **limits** là một nhóm thuộc tính.

**Quan trọng:** @NestedConfigurationProperty **không phải một công tắc bắt buộc để binder mới có khả năng bind object lồng nhau**. Nó không tự tạo object, không sửa prefix, không thay cơ chế constructor binding và không ép một child phải tồn tại.

Với các inner nested class và một số cấu trúc collection/map thông dụng, metadata processor có thể đã biết quan hệ lồng nhau mà không cần annotation này. Chỉ dùng nó khi cần diễn đạt rõ thông tin metadata theo khả năng của công cụ đang dùng.

## 18. Tổ chức nhiều class cấu hình thay vì một object khổng lồ

Một ứng dụng không nhất thiết gom tất cả cấu hình vào **AppProperties** với hàng chục nhánh lồng nhau. Có thể chia theo domain:

~~~text
app.http.*
app.notifications.*
app.cache.*
app.security.*
integration.catalog.*
integration.billing.*
~~~

Với mỗi nhóm, một class/record cấu hình riêng:

~~~java
@ConfigurationProperties(prefix = "app.http")
public record HttpProperties(
        java.time.Duration connectTimeout,
        java.time.Duration readTimeout
) {}
~~~

~~~java
@ConfigurationProperties(prefix = "app.cache")
public record CacheProperties(
        boolean enabled,
        java.time.Duration timeToLive
) {}
~~~

~~~java
@ConfigurationProperties(prefix = "integration.catalog")
public record CatalogProperties(
        String baseUrl,
        java.time.Duration timeout
) {}
~~~

Khi class chỉ chịu trách nhiệm cho một nhóm, prefix ngắn và mô hình Java dễ hiểu. Một service HTTP client có thể inject HttpProperties; service cache inject CacheProperties.

Ngược lại, nếu các giá trị thuộc cùng một đối tượng nghiệp vụ, ví dụ **Client** có **Http**, **Retry**, **Authentication**, giữ chúng trong một mô hình nested là hợp lý.

**Tiêu chí chia nhóm:** quan hệ sở hữu, vòng đời, trách nhiệm trong code và cách người vận hành chỉnh cấu hình. Đừng chia theo số dòng YAML thuần túy.

### 18.1. Không để secret bị in qua toString() của record

Java record tạo ra phương thức **toString()** bao gồm các component theo hành vi mặc định. Nếu nested configuration chứa token, password hoặc secret, việc log trực tiếp một record cấu hình có thể làm lộ giá trị.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "app.credentials")
public record CredentialsProperties(
        String username,
        String password
) {}
~~~

Đừng log:

~~~java
System.out.println(credentialsProperties);
~~~

trong môi trường thật. Hãy tránh lưu secret trong mã nguồn và dùng cơ chế cấp secret thích hợp; nếu cần log cấu hình, chỉ ghi tên trường hoặc giá trị đã được che, không ghi toàn bộ object.

## 19. Cấu trúc nested và validation ở cấp hệ thống

Khi một thuộc tính nested quan trọng, nên đặt hợp đồng cấu hình gần class chịu trách nhiệm, thay vì chỉ dựa vào một mặc định Java.

Ví dụ một HTTP client phải có endpoint và timeout dương:

~~~java
import java.time.Duration;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "integration")
public record IntegrationProperties(
        @Valid @NotNull Catalog catalog
) {
    public record Catalog(
            @NotBlank String baseUrl,
            @NotNull Duration timeout
    ) {}
}
~~~

Đối với Duration cần kiểm tra phải lớn hơn 0, không phải mọi Bean Validation provider đều có cùng constraint tích hợp cho mọi kiểu. Có thể viết validation tùy chỉnh, dùng điều kiện logic trong constructor hoặc một constraint class-level tương ứng.

Một ví dụ kiểm tra rõ trong constructor:

~~~java
public record Catalog(String baseUrl, Duration timeout) {
    public Catalog {
        if (baseUrl == null || baseUrl.isBlank()) {
            throw new IllegalArgumentException("baseUrl must not be blank");
        }
        if (timeout == null || timeout.isNegative() || timeout.isZero()) {
            throw new IllegalArgumentException("timeout must be positive");
        }
    }
}
~~~

Đây là Java record compact constructor, phù hợp khi muốn bảo đảm invariant bất kể object được tạo từ binder hay từ unit test. Khi có nhiều ràng buộc, giải pháp Bean Validation có thể cung cấp thông báo lỗi theo đường dẫn property nhất quán hơn.

Không lưu thông điệp lỗi chứa secret hoặc dữ liệu nhạy cảm. Chỉ nêu tên thuộc tính và điều kiện vi phạm.

## 20. Chẩn đoán lỗi binding nested

Khi ứng dụng báo lỗi tạo bean @ConfigurationProperties, các nguyên nhân có thể thuộc những nhóm sau:

| Triệu chứng | Nguyên nhân có thể | Nơi kiểm tra |
| --- | --- | --- |
| Cannot bind properties | Giá trị sai kiểu, constructor không thể tạo object | Kiểu Java và giá trị property |
| Field nested là null | Nhóm chưa được khai báo hoặc thiếu default | Đường dẫn prefix.child.*, chiến lược binding |
| Trường int bằng 0 ngoài dự kiến | Thiếu property hoặc giá trị đúng là 0 | Tên đầy đủ và validation |
| Không tìm được bean cấu hình | Chưa scan/enable configuration properties | @ConfigurationPropertiesScan, package |
| Chỉ một trường sai khi dùng YAML | Sai cấp thụt lề hoặc sai tên khóa | YAML mapping và đường dẫn canonical |
| Local chạy đúng, prod sai | Profile, env var, CLI hoặc location khác | PropertySource precedence |
| List mất phần tử từ file nền | List ở nguồn khác thay thế | Quy tắc collection binding |
| Map key bị đổi | Dấu chấm/ký tự đặc biệt không được bảo toàn | Bracket notation và kiểu Map |
| Validation không chạy trên child | Thiếu @Valid hoặc provider | Annotation ở từng cấp và dependency |
| Giá trị String đúng nhưng Duration lỗi | Conversion, đơn vị hoặc ký tự không hợp lệ | Giá trị thô và kiểu đích |

Hãy đọc **root cause** của exception chứ không dừng ở “Application failed to start”. Trong các lỗi bind, Spring Boot thường cung cấp tên property, giá trị gây lỗi, nguồn hoặc vị trí file và kiểu Java đích nếu thông tin có sẵn.

### 20.1. Phân biệt lỗi không tìm thấy property và lỗi chuyển kiểu

Nếu YAML khai báo:

~~~yaml
app:
  client:
    http:
      connect-timeout: fast
~~~

thì binder có thể tìm thấy **app.client.http.connect-timeout**, nhưng **fast** không phải Duration hợp lệ theo cú pháp thông thường.

Nếu YAML khai báo:

~~~yaml
app:
  client:
    connect-timeout: 3s
~~~

thì key **app.client.http.connect-timeout** lại không có. Hai lỗi có biểu hiện cuối giống nhau (record không có Duration mong muốn), nhưng cách sửa khác:

- Trường hợp đầu: sửa **giá trị**.
- Trường hợp sau: sửa **đường dẫn**.

### 20.2. Dùng Environment để kiểm tra một khóa

Một đoạn mã chẩn đoán an toàn với thuộc tính không nhạy cảm:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration
class ConfigProbe {

    @Bean
    ApplicationRunner inspect(Environment environment) {
        return args -> {
            System.out.println(
                environment.getProperty("app.client.http.connect-timeout")
            );
            System.out.println(
                environment.getProperty("app.client.http.pool.max-size")
            );
        };
    }
}
~~~

Environment đọc giá trị được phân giải từ PropertySource. Nếu Environment đã có giá trị đúng nhưng binder gặp lỗi, hãy xem conversion, constructor, validation hoặc cấu trúc Java. Nếu Environment không có giá trị mong đợi, hãy xem tên khóa, profile và nguồn nạp.

### 20.3. Liệt kê PropertySource mà không in secret

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

for (PropertySource<?> source : environment.getPropertySources()) {
    System.out.println(source.getName());
}
~~~

Đoạn này giả định biến **environment** có kiểu **ConfigurableEnvironment**. Nó chỉ in tên các nguồn, không in toàn bộ các cặp key/value. Việc in tất cả cấu hình có thể lộ token, password hoặc URL có thông tin xác thực.

Với ứng dụng đã triển khai Actuator và được cấu hình giới hạn truy cập, endpoint môi trường có thể hỗ trợ việc truy nguyên nguồn property. Không mở công khai endpoint chẩn đoán chỉ để tìm một tên khóa.

## 21. Bài thực hành 1: YAML thành record

Cho YAML:

~~~yaml
reporting:
  enabled: true
  export:
    directory: "/var/reports"
    schedule:
      interval: 30m
      max-jobs: 4
~~~

Hãy mô hình hóa thành một record gốc có prefix **reporting**, hai record con Export và Schedule.

Đáp án minh họa:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "reporting")
public record ReportingProperties(
        boolean enabled,
        Export export
) {
    public record Export(
            String directory,
            Schedule schedule
    ) {}

    public record Schedule(
            Duration interval,
            int maxJobs
    ) {}
}
~~~

Các đường dẫn đầy đủ:

~~~text
reporting.enabled
reporting.export.directory
reporting.export.schedule.interval
reporting.export.schedule.max-jobs
~~~

Đừng viết thành **reporting.schedule.max-jobs**, vì đã bỏ qua cấp export.

## 22. Bài thực hành 2: tìm lỗi thụt lề

Cấu hình mong muốn có **http.pool.max-size**, nhưng người viết tạo:

~~~yaml
service:
  http:
    timeout: 3s
  pool:
    max-size: 50
~~~

Đường dẫn thực của max-size là **service.pool.max-size**. Nếu Java có nested Http chứa nested Pool, đường dẫn mong đợi phải là **service.http.pool.max-size**.

Cách sửa:

~~~yaml
service:
  http:
    timeout: 3s
    pool:
      max-size: 50
~~~

Bài này nhấn mạnh rằng YAML có thể vẫn parse hợp lệ nhưng binder nhận sai cấu trúc.

## 23. Bài thực hành 3: List của object

YAML:

~~~yaml
app:
  workers:
    - name: indexing
      concurrency: 2
    - name: exporting
      concurrency: 5
~~~

Hãy xây dựng record có **List<Worker> workers**, mỗi Worker có **name** và **concurrency**. Đáp án:

~~~java
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record WorkerProperties(List<Worker> workers) {
    public record Worker(String name, int concurrency) {}
}
~~~

Các đường dẫn:

~~~text
app.workers[0].name
app.workers[0].concurrency
app.workers[1].name
app.workers[1].concurrency
~~~

Biến môi trường chuẩn:

~~~text
APP_WORKERS_0_NAME
APP_WORKERS_0_CONCURRENCY
APP_WORKERS_1_NAME
APP_WORKERS_1_CONCURRENCY
~~~

Nếu một Worker bắt buộc có name không rỗng và concurrency ít nhất 1, hãy đặt validation ở lớp con và kích hoạt cascade validation cho danh sách.

## 24. Bài thực hành 4: Map và key đặc biệt

YAML:

~~~yaml
app:
  tenants:
    default:
      quota: 100
    "[tenant.eu]":
      quota: 200
~~~

Java:

~~~java
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record TenantProperties(Map<String, Tenant> tenants) {
    public record Tenant(int quota) {}
}
~~~

Sau khi bind đúng, chương trình có thể tra cứu **tenants().get("default")** và **tenants().get("tenant.eu")**.

Giải thích: bracket notation hỗ trợ bảo toàn dấu chấm trong Map key. Nếu bỏ dấu ngoặc, key có thể được phân tích thành cấu trúc nested thay vì một tên tenant nguyên vẹn, tùy kiểu Map và quy tắc binding.

## 25. Bài thực hành 5: phân biệt cấp đối tượng và tên field

Hai cấu hình:

~~~yaml
app:
  http:
    retry-count: 3
~~~

và:

~~~yaml
app:
  http:
    retry:
      count: 3
~~~

Cấu hình thứ nhất hướng tới field **retryCount** trong Http. Cấu hình thứ hai hướng tới nested **retry** có field **count**.

Các đường dẫn:

~~~text
app.http.retry-count
app.http.retry.count
~~~

Bài tập: viết record cho từng cấu trúc.

Đáp án A:

~~~java
@ConfigurationProperties(prefix = "app")
public record AppProperties(Http http) {
    public record Http(int retryCount) {}
}
~~~

Đáp án B:

~~~java
@ConfigurationProperties(prefix = "app")
public record AppProperties(Http http) {
    public record Http(Retry retry) {}
    public record Retry(int count) {}
}
~~~

Đây là sự khác biệt về **mô hình Java**, không chỉ cách trình bày YAML.

## 26. Bài thực hành 6: nguồn ưu tiên và kiểu dữ liệu

File application.yml:

~~~yaml
app:
  http:
    connect-timeout: 1s
    read-timeout: 5s
~~~

Biến môi trường:

~~~bash
APP_HTTP_CONNECTTIMEOUT=2s java -Dapp.http.read-timeout=8s -jar demo.jar   --app.http.connect-timeout=3s
~~~

Giả sử thứ tự PropertySource mặc định và không có nguồn ưu tiên cao hơn, record:

~~~java
@ConfigurationProperties(prefix = "app.http")
public record HttpProperties(
        java.time.Duration connectTimeout,
        java.time.Duration readTimeout
) {}
~~~

có thể nhận **connectTimeout = 3s** và **readTimeout = 8s**.

Lý do: mỗi đường dẫn property được giải quyết theo precedence. Command-line property thắng env var đối với connect-timeout, còn system property thắng file nền đối với read-timeout.

Nếu một property không được cung cấp và không có default, hãy xét nullable, kiểu primitive và validation thay vì đoán kết quả.

## 27. Cách thiết kế một nhóm @ConfigurationProperties có thể bảo trì

Một quy trình thiết kế thực tế:

1. **Xác định phạm vi:** nhóm cấu hình thuộc service hoặc integration nào?
2. **Chọn prefix canonical:** ví dụ **integration.catalog**.
3. **Vẽ cây config logic:** endpoint, http, retry, pool, headers.
4. **Chọn kiểu cho từng nhánh:** nested record/class, List hoặc Map theo cách dùng.
5. **Chọn kiểu cho từng giá trị:** Duration cho timeout, DataSize cho size, enum cho chế độ, int cho số lượng.
6. **Quyết định trường bắt buộc và tùy chọn:** thêm validation hoặc default rõ ràng.
7. **Đăng ký configuration properties bean:** scan hoặc enable.
8. **Viết một file YAML mẫu:** bám sát đường dẫn và cấu trúc Java.
9. **Ghi tài liệu env var:** chuyển từ property canonical theo quy tắc của Spring Boot.
10. **Kiểm tra trên runtime thực tế:** xác nhận đường dẫn, precedence, conversion và lỗi khởi động khi thiếu thông số quan trọng.

Ví dụ cây trước khi viết code:

~~~text
integration.catalog
├── base-url                    : String
├── http
│   ├── connect-timeout         : Duration
│   ├── read-timeout            : Duration
│   └── pool
│       ├── enabled             : boolean
│       └── max-size            : int
├── retry
│   ├── max-attempts            : int
│   └── backoff                 : Duration
└── fallback-endpoints          : List<String>
~~~

Từ cây này, đường dẫn property rõ ràng, việc viết record có thể tiến hành từ lá lên gốc, và nhóm cấu hình dễ mở rộng mà không phải đoán tên của các trường nested.

## 28. Các lỗi kiến trúc nên tránh

**Không dùng một class cấu hình khổng lồ cho mọi module.** Nếu một nhóm có hàng trăm field không liên quan, service dễ phụ thuộc vào toàn bộ cấu hình và thay đổi nhỏ gây ảnh hưởng ngoài ý muốn.

**Không sao chép config DTO sang nhiều service rồi để chúng lệch nhau.** Một nhóm thuộc tính cần có hợp đồng tên và kiểu ổn định; khi đổi tên property cần cập nhật tài liệu triển khai và cấu hình ở các môi trường liên quan.

**Không nhầm object nested với Map tùy ý.** Nếu tên field được biết trước và mang ý nghĩa nghiệp vụ ổn định, record/class thường an toàn hơn. Nếu key do môi trường cung cấp và có số lượng biến động, Map phù hợp hơn.

**Không bind trực tiếp cấu hình vào domain entity.** Entity của database thường có vòng đời và trách nhiệm khác với cấu hình môi trường. Tách class @ConfigurationProperties giúp phân định nguồn dữ liệu và kiểm thử rõ ràng.

**Không sử dụng SpEL như một hệ thống mô hình hóa object trong file.** @ConfigurationProperties hướng đến bind cấu trúc và chuyển kiểu; không mặc nhiên thực thi mọi chuỗi biểu thức trong YAML. Dữ liệu tính toán nên được đưa vào Java method hoặc cơ chế cấu hình có hợp đồng riêng.

**Không sử dụng null như một cách chắc chắn để xóa cấu hình ở nguồn ưu tiên thấp.** Khi muốn tắt chức năng, dùng cờ rõ nghĩa như **enabled: false** và kiểm tra binder thực nhận.

**Không phụ thuộc việc tự cập nhật nóng.** Bean cấu hình thường được tạo lúc khởi động; thay biến môi trường sau khi JVM đã chạy không tự làm mới nested record. Khi cần refresh, phải dùng cơ chế được thiết kế riêng.

## 29. Bảng quyết định nhanh

| Nhu cầu | Mô hình nên cân nhắc | Đường dẫn minh họa |
| --- | --- | --- |
| Một nhóm trường cố định | Record hoặc JavaBean | app.http.connect-timeout |
| Một cấp con có vai trò rõ | Nested record/class | app.http.pool.max-size |
| Nhiều phần tử có thứ tự | List<Server> | app.servers[0].host |
| Nhiều phần tử tra theo key | Map<String, Region> | app.regions.asia.endpoint |
| Key Map chứa dấu chấm đặc biệt | Bracket notation | app.tenants.[tenant.eu].quota |
| Timeout, interval, backoff | Duration | app.retry.backoff |
| Kích thước file/buffer | DataSize | app.upload.max-file-size |
| Một tập chế độ hữu hạn | Enum | app.retry.mode |
| Trường bắt buộc/giới hạn giá trị | @Validated, @Valid và constraint | app.http.max-connections |
| Giá trị mặc định của constructor binding | @DefaultValue hoặc config nền | app.client.retries |
| Ghi đè qua env var | Tên canonical chuyển sang chữ hoa | APP_HTTP_CONNECTTIMEOUT |
| Chẩn đoán một thuộc tính | Environment + lỗi binder | app.http.read-timeout |

## 30. Những điểm cần ghi nhớ

- **@ConfigurationProperties(prefix = "...")** liên kết một nhóm thuộc tính vào một mô hình Java có kiểu dữ liệu. Prefix là gốc của đường dẫn.
- **Dấu chấm** thể hiện các cấp; **dấu gạch ngang** thể hiện các từ của một tên property. **app.http.read-timeout** khác về cấu trúc với **app.http.read.timeout**.
- Nested record hoặc nested JavaBean phản ánh cây YAML. Cùng đường dẫn có thể được khai báo trong .properties bằng tên khóa đầy đủ.
- **List** dùng chỉ số như **[0]**, **[1]**; **Map** dùng key động như **asia** hoặc **tenant.eu**. Key Map đặc biệt có thể cần bracket notation.
- Binder hỗ trợ chuyển đổi kiểu như Duration, DataSize, boolean, enum; việc tìm đúng tên property không bảo đảm chuyển đổi thành công.
- Với constructor binding, cần xét rõ nhóm thiếu, nested null và default. **@DefaultValue** là một cơ chế hỗ trợ tùy phiên bản; cấu hình nền và validation là những lựa chọn khác.
- **@Validated** kết hợp **@Valid** và constraint phù hợp giúp phát hiện cấu hình nested thiếu hoặc sai sớm trong quá trình khởi động.
- **@NestedConfigurationProperty** chủ yếu liên quan tới metadata cho công cụ, không phải điều kiện để binder có thể đọc nested object.
- Biến môi trường chuẩn được tạo từ tên canonical: **dấu chấm thành dấu gạch dưới, dấu gạch ngang bị bỏ và chữ cái thành chữ hoa**.
- Khi debug, lần theo **tên property đầy đủ → nguồn có hiệu lực → giá trị sau conversion → field Java**, thay vì chỉ đọc dòng cuối của một YAML mapping.

Tư duy quan trọng nhất là xem **cấu hình như một hợp đồng dữ liệu có cấu trúc**, không phải tập hợp các chuỗi rời rạc. Khi cây thuộc tính, mô hình Java, kiểu dữ liệu và quy tắc validation thống nhất, Spring Boot có thể bind cấu hình từ nhiều nguồn một cách dễ đọc và dễ vận hành.

# Liên kết danh sách đối tượng có cấu trúc lồng nhau

Spring Boot Externalized Configuration không chỉ dùng để đọc những key đơn như `server.port` hoặc `app.enabled`. Trong ứng dụng thực tế, cấu hình thường có dạng **một danh sách đối tượng, trong mỗi đối tượng lại chứa object, list, map và các trường có kiểu**. Ví dụ một hệ thống xử lý sự kiện có nhiều pipeline; mỗi pipeline có chính sách retry riêng, một danh sách endpoint, và mỗi endpoint có headers hoặc các tùy chọn vận hành khác nhau.

Spring Boot cung cấp **`@ConfigurationProperties` và Binder** để chuyển cấu trúc YAML hoặc các key có chỉ số trong `.properties` thành `List<Pipeline>`, `List<Destination>`, `Map<String,String>` và những record/class lồng nhau. Trọng tâm của bài là cách thiết kế cây cấu hình, khai báo kiểu Java, ánh xạ chỉ số, áp dụng validation, hiểu độ ưu tiên khi có nhiều nguồn cấu hình và chẩn đoán lỗi thường gặp.

Các ví dụ dùng Spring Boot 3.x với Java 17+ và Jakarta Bean Validation ở phần validation. Nguyên tắc về danh sách, map và Config Data cũng hữu ích khi làm việc với những phiên bản Spring Boot hỗ trợ Configuration Properties Binder.

## 1. Một danh sách object lồng nhau trông như thế nào?

Giả sử ứng dụng có cấu hình sau:

~~~yaml
app:
  pipelines:
    - name: orders
      enabled: true
      retry:
        max-attempts: 3
        backoff: 250ms
      destinations:
        - id: primary
          url: https://orders.example.test/events
          timeout: 2s
          headers:
            x-channel: retail
            x-region: asia
        - id: backup
          url: https://backup.example.test/orders
          timeout: 5s
          headers:
            x-channel: fallback
      labels:
        owner: team-orders
        tier: critical

    - name: invoices
      enabled: false
      retry:
        max-attempts: 1
        backoff: 1s
      destinations:
        - id: billing
          url: https://billing.example.test/events
          timeout: 3s
          headers:
            x-channel: finance
      labels:
        owner: team-finance
        tier: standard
~~~

Cây dữ liệu:

~~~text
app
└── pipelines                              List<Pipeline>
    ├── [0]                                Pipeline
    │   ├── name: orders                   String
    │   ├── enabled: true                  boolean
    │   ├── retry                          Retry
    │   │   ├── max-attempts: 3            int
    │   │   └── backoff: 250ms             Duration
    │   ├── destinations                   List<Destination>
    │   │   ├── [0] primary                Destination
    │   │   │   ├── url                    URI
    │   │   │   ├── timeout                Duration
    │   │   │   └── headers                Map<String,String>
    │   │   └── [1] backup                 Destination
    │   └── labels                         Map<String,String>
    └── [1]                                Pipeline
        ├── name: invoices
        ├── enabled: false
        ├── retry
        ├── destinations
        └── labels
~~~

Có **hai cấp danh sách**: `pipelines` và `destinations`. Mỗi phần tử của `pipelines` lại có một object `retry`, một list `destinations` và một map `labels`. Đây là tình huống điển hình để dùng typed binding thay vì tự đọc từng key bằng `Environment.getProperty(...)`.

Một điểm quan trọng: phần tử YAML sau dấu `-` không phải chuỗi đơn. Nó là một **object** vì bên trong có các trường `name`, `enabled`, `retry`, `destinations` và `labels`.

## 2. Từ YAML sang Java: thiết kế root và nested records

Ta muốn root object quản lý nhóm `app.*`. Dùng record `PipelineProperties`:

~~~java
package com.example.orders.config;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record PipelineProperties(
    List<Pipeline> pipelines
) {
    public record Pipeline(
        String name,
        boolean enabled,
        Retry retry,
        List<Destination> destinations,
        Map<String, String> labels
    ) {}

    public record Retry(
        int maxAttempts,
        Duration backoff
    ) {}

    public record Destination(
        String id,
        URI url,
        Duration timeout,
        Map<String, String> headers
    ) {}
}
~~~

Đây là một ví dụ **root record và các nested records**. Cấu trúc thuộc tính:

| YAML path | Java path | Kiểu |
| --- | --- | --- |
| `app.pipelines` | `pipelines` | `List<Pipeline>` |
| `app.pipelines[0].name` | `pipelines.get(0).name()` | `String` |
| `app.pipelines[0].enabled` | `pipelines.get(0).enabled()` | `boolean` |
| `app.pipelines[0].retry.max-attempts` | `pipelines.get(0).retry().maxAttempts()` | `int` |
| `app.pipelines[0].retry.backoff` | `pipelines.get(0).retry().backoff()` | `Duration` |
| `app.pipelines[0].destinations` | `pipelines.get(0).destinations()` | `List<Destination>` |
| `app.pipelines[0].destinations[1].id` | `pipelines.get(0).destinations().get(1).id()` | `String` |
| `app.pipelines[0].destinations[0].url` | `pipelines.get(0).destinations().get(0).url()` | `URI` |
| `app.pipelines[0].labels` | `pipelines.get(0).labels()` | `Map<String,String>` |

Spring Boot Binder nhìn **kiểu generic của list**, biết rằng các phần tử phải trở thành `Pipeline`; tiếp tục nhìn các record components của `Pipeline` để tạo `Retry`, `Destination` và map tương ứng. Người dùng không cần gọi constructor của từng nested record trong mã application.

### Vì sao dùng URI và Duration thay vì String?

Cấu hình YAML như `timeout: 2s` là văn bản, nhưng mô hình Java có thể dùng `Duration` để biểu đạt **thời gian chờ** một cách rõ ràng. Tương tự, một địa chỉ endpoint được bind thành `URI`. Khi dữ liệu không hợp kiểu, Binder có thể báo lỗi trong quá trình tạo bean, giúp tránh lỗi xuất hiện rất muộn khi code nghiệp vụ dùng giá trị.

## 3. Đăng ký @ConfigurationProperties bean

`@ConfigurationProperties` mô tả prefix, nhưng cần cơ chế đăng ký bean. Một cách phổ biến là quét các type được annotate:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Với cấu trúc:

~~~text
src/main/java/
  com/example/orders/
    OrderApplication.java
    config/
      PipelineProperties.java
    service/
      PipelineRunner.java
~~~

`@ConfigurationPropertiesScan` trên package `com.example.orders` có thể tìm `PipelineProperties` trong package con `com.example.orders.config`.

Hoặc đăng ký tường minh nếu muốn chỉ bật một type:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PipelineProperties.class)
public class PipelineConfiguration {}
~~~

Lớp `PipelineConfiguration` phải được đưa vào Spring context, ví dụ nằm trong phạm vi component scan hoặc được import phù hợp. Với root record constructor-bound, không cần thêm `@Component` chỉ để Spring tìm thấy record; dùng cơ chế dành riêng cho configuration properties.

**Nested record `Retry` và `Destination` không phải Spring bean độc lập trong ví dụ này.** Chúng là các value objects bên trong root `PipelineProperties`, được Binder dựng khi bind root.

## 4. Truy cập list đã bind trong mã nghiệp vụ

Một service có thể inject đúng một bean typed:

~~~java
package com.example.orders.service;

import com.example.orders.config.PipelineProperties;
import org.springframework.stereotype.Service;

@Service
public class PipelineRunner {
    private final PipelineProperties config;

    public PipelineRunner(PipelineProperties config) {
        this.config = config;
    }

    public void printNonSensitiveOverview() {
        for (PipelineProperties.Pipeline pipeline : config.pipelines()) {
            if (!pipeline.enabled()) {
                continue;
            }

            System.out.println("Pipeline: " + pipeline.name());
            System.out.println(
                "Retry count: " + pipeline.retry().maxAttempts());

            for (PipelineProperties.Destination dest
                    : pipeline.destinations()) {
                System.out.println(
                    " -> " + dest.id() + " at " + dest.url());
            }
        }
    }
}
~~~

Ví dụ trên giả định `pipelines`, `retry` và `destinations` đã được cung cấp hợp lệ. Trong ứng dụng thật, các cấu hình bắt buộc nên được validate khi khởi động để consumer không phải rải các kiểm tra null khắp nơi.

Ưu điểm: service không cần biết YAML dùng dấu `-`, chỉ số `[0]` hay thư mục nào đang chứa file cấu hình. Service nhận **cây đối tượng đã bind** và làm việc với các accessor Java.

Một service có thể chỉ tiêu thụ phần mình cần. Ví dụ, để xây endpoint client, chỉ cần lấy `Destination.url()` và `Destination.timeout()`, trong khi logic retry dùng `Retry.maxAttempts()` và `Retry.backoff()`.

## 5. Cú pháp YAML: dấu gạch đầu dòng tạo phần tử list

Trong YAML, một sequence thường được viết với dấu `-`. Mỗi dấu `-` ở mức thụt lề đó tạo một phần tử:

~~~yaml
app:
  pipelines:
    - name: orders
      enabled: true
    - name: invoices
      enabled: false
~~~

Ở đây:

- `pipelines` là một sequence có hai phần tử.
- Phần tử đầu là một mapping chứa `name` và `enabled`.
- Phần tử thứ hai là một mapping khác chứa hai key tương tự.
- Spring Binder có thể ánh xạ sequence thành `List<Pipeline>` dựa trên kiểu của record.

Danh sách object khác danh sách scalar:

~~~yaml
app:
  allowed-regions:
    - ap-southeast-1
    - eu-west-1
~~~

Danh sách này có thể bind vào `List<String> allowedRegions`. Không nên khai báo `List<Destination>` rồi đưa chuỗi đơn nếu Binder đang cần các field `id`, `url` và `timeout`.

### Thụt lề quyết định quan hệ cha-con

Đúng:

~~~yaml
app:
  pipelines:
    - name: orders
      retry:
        max-attempts: 3
        backoff: 250ms
      destinations:
        - id: primary
          url: https://orders.example.test/events
          timeout: 2s
~~~

`retry` và `destinations` ở cùng cấp với `name`, nên đều là field của phần tử `pipelines[0]`.

Sai về ý nghĩa cấu trúc:

~~~yaml
app:
  pipelines:
    - name: orders
      retry:
        max-attempts: 3
        backoff: 250ms
        destinations:
          - id: primary
            url: https://orders.example.test/events
~~~

Đoạn sau đặt `destinations` **bên trong `retry`**, không còn là field trực tiếp của `Pipeline`. Nếu kiểu `Retry` không khai báo field này, dữ liệu có thể bị bỏ qua hoặc gây lỗi tùy cấu hình Binder. Lỗi thụt lề là một trong các nguyên nhân thường gặp của cấu hình lồng nhau bind thiếu dữ liệu.

### Cùng một object phải đi dưới cùng một dấu '-'

~~~yaml
app:
  pipelines:
    - name: orders
      enabled: true
      retry:
        max-attempts: 3
        backoff: 250ms
    - name: invoices
      enabled: false
      retry:
        max-attempts: 1
        backoff: 1s
~~~

Hai block sau dấu `-` biểu thị hai object khác nhau; không phải một object có hai `name`. Các field chỉ thuộc phần tử mà chúng được thụt vào bên trong.

## 6. Viết cùng cấu trúc bằng application.properties

Khi chuyển YAML sequence sang `.properties`, dùng **chỉ số bắt đầu từ 0 trong dấu ngoặc vuông**:

~~~properties
app.pipelines[0].name=orders
app.pipelines[0].enabled=true
app.pipelines[0].retry.max-attempts=3
app.pipelines[0].retry.backoff=250ms

app.pipelines[0].destinations[0].id=primary
app.pipelines[0].destinations[0].url=https://orders.example.test/events
app.pipelines[0].destinations[0].timeout=2s
app.pipelines[0].destinations[0].headers.x-channel=retail
app.pipelines[0].destinations[0].headers.x-region=asia

app.pipelines[0].destinations[1].id=backup
app.pipelines[0].destinations[1].url=https://backup.example.test/orders
app.pipelines[0].destinations[1].timeout=5s
app.pipelines[0].destinations[1].headers.x-channel=fallback

app.pipelines[0].labels.owner=team-orders
app.pipelines[0].labels.tier=critical

app.pipelines[1].name=invoices
app.pipelines[1].enabled=false
app.pipelines[1].retry.max-attempts=1
app.pipelines[1].retry.backoff=1s
app.pipelines[1].destinations[0].id=billing
app.pipelines[1].destinations[0].url=https://billing.example.test/events
app.pipelines[1].destinations[0].timeout=3s
app.pipelines[1].destinations[0].headers.x-channel=finance
app.pipelines[1].labels.owner=team-finance
app.pipelines[1].labels.tier=standard
~~~

Một số key điển hình có thể đọc như đường dẫn từ root:

~~~text
app.pipelines[0].name
app.pipelines[0].retry.backoff
app.pipelines[0].destinations[1].url
app.pipelines[1].destinations[0].timeout
~~~

`[0]` ở giữa tên key đánh dấu **phần tử thứ nhất của một list**. `[1]` là phần tử thứ hai. Các phần `.retry` hoặc `.destinations` tiếp tục truy vào object lồng trong phần tử tương ứng.

### Đừng nhầm chỉ số list với tên key của map

`pipelines[0]` là cú pháp định vị index vì `pipelines` có kiểu `List<Pipeline>`. Trong khi đó, `labels.owner` là truy cập map có key `owner` (theo cơ chế binding map). Với map có key chứa ký tự đặc biệt hoặc dấu chấm cần giữ nguyên, Spring Boot có quy tắc bracket notation riêng cho map, được trình bày ở phần sau.

## 7. Quy tắc đánh chỉ số liên tục và trật tự phần tử

Khi biểu diễn list trong properties, hãy khai báo rõ phần tử `[0]`, `[1]`, `[2]` ... theo thứ tự. Trong các nguồn dạng property có index, Binder phải tổng hợp các entry theo chỉ số để tạo collection; **không nên để những khoảng trống index ngoài ý muốn** rồi chờ framework đoán cách điền.

Ví dụ dễ hiểu:

~~~properties
app.pipelines[0].name=orders
app.pipelines[1].name=invoices
app.pipelines[2].name=shipments
~~~

Một ví dụ khó dự đoán và khó bảo trì:

~~~properties
app.pipelines[0].name=orders
app.pipelines[5].name=invoices
~~~

Dù cấu hình có thể được parser nhận cú pháp, bạn không nên dựa vào việc danh sách tự xuất hiện các phần tử `[1]`–`[4]` hợp lý. Hãy kiểm soát rõ số phần tử, đủ trường bắt buộc và thứ tự.

**Thứ tự list có thể là một phần của nghiệp vụ.** Nếu pipeline được chạy theo đúng thứ tự trong file, hãy nói rõ trong tài liệu cấu hình. Nếu thứ tự chỉ để liệt kê mà không có ý nghĩa, nên dùng key định danh và xử lý như map khi phù hợp.

Ví dụ: khi `primary`, `backup` được chọn theo thứ tự failover, danh sách `destinations` nên ghi thứ tự ưu tiên rõ ràng. Nếu chỉ cần tra đích theo mã `id` mà thứ tự không quan trọng, `Map<String,Destination>` có thể diễn đạt ý định tốt hơn.

## 8. Danh sách nhiều tầng: List trong List

Cấu trúc pipeline ở trên có:

~~~text
List<Pipeline>
  └── List<Destination>
~~~

Spring Boot Binder có thể làm việc với những level lồng sâu hơn khi model Java và dữ liệu khớp nhau. Ví dụ một cấu hình phân nhóm rule:

~~~yaml
app:
  rule-groups:
    - id: checkout
      rules:
        - code: require-address
          conditions:
            - field: shippingAddress
              operator: present
            - field: country
              operator: allowed
        - code: require-email
          conditions:
            - field: email
              operator: present

    - id: invoices
      rules:
        - code: valid-currency
          conditions:
            - field: currency
              operator: supported
~~~

Model:

~~~java
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record RuleGroupProperties(
    List<RuleGroup> ruleGroups
) {
    public record RuleGroup(
        String id,
        List<Rule> rules
    ) {}

    public record Rule(
        String code,
        List<Condition> conditions
    ) {}

    public record Condition(
        String field,
        String operator
    ) {}
}
~~~

Một đường dẫn cụ thể:

~~~text
app.rule-groups[0].rules[1].conditions[0].field
~~~

Đường dẫn này tham chiếu:

1. Nhóm rule thứ nhất: `rule-groups[0]`.
2. Rule thứ hai trong nhóm: `rules[1]`.
3. Condition thứ nhất của rule: `conditions[0]`.
4. Field `field` của condition đó.

Cùng dữ liệu trong properties:

~~~properties
app.rule-groups[0].id=checkout
app.rule-groups[0].rules[0].code=require-address
app.rule-groups[0].rules[0].conditions[0].field=shippingAddress
app.rule-groups[0].rules[0].conditions[0].operator=present
app.rule-groups[0].rules[0].conditions[1].field=country
app.rule-groups[0].rules[0].conditions[1].operator=allowed
app.rule-groups[0].rules[1].code=require-email
app.rule-groups[0].rules[1].conditions[0].field=email
app.rule-groups[0].rules[1].conditions[0].operator=present

app.rule-groups[1].id=invoices
app.rule-groups[1].rules[0].code=valid-currency
app.rule-groups[1].rules[0].conditions[0].field=currency
app.rule-groups[1].rules[0].conditions[0].operator=supported
~~~

Chính **kiểu `List<RuleGroup>`, `List<Rule>`, `List<Condition>`** quyết định Binder cần xây các object, không phải việc người dùng tự viết parser đệ quy.

## 9. Map bên trong phần tử list

Một phần tử `Destination` có thể mang map headers:

~~~yaml
app:
  pipelines:
    - name: orders
      destinations:
        - id: primary
          url: https://orders.example.test/events
          timeout: 2s
          headers:
            x-channel: retail
            x-region: asia
~~~

Với record:

~~~java
public record Destination(
    String id,
    URI url,
    Duration timeout,
    Map<String, String> headers
) {}
~~~

Binder có thể tạo map tương ứng chứa `x-channel` và `x-region`. Đây là một **map nằm trong object, còn object nằm trong list**.

### Map có key chứa dấu chấm hoặc ký tự đặc biệt

Với `@ConfigurationProperties`, các key map có thể bị chuẩn hóa theo quy tắc binding nếu không dùng cú pháp rõ ràng. Khi cần giữ nguyên một key map có dấu chấm hoặc ký tự đặc biệt, dùng bracket notation.

Ví dụ properties:

~~~properties
app.pipelines[0].labels.[deployment.zone]=asia
app.pipelines[0].labels.[/team]=orders
~~~

Với `Map<String,String> labels`, bracket notation cho biết phần trong ngoặc là key của map cần được giữ theo quy tắc tương ứng. Ở YAML, đặt key bracket trong dấu nháy:

~~~yaml
app:
  pipelines:
    - name: orders
      labels:
        "[deployment.zone]": asia
        "[/team]": orders
~~~

Những key bình thường như `owner` hoặc `tier` không cần bracket notation.

**Lưu ý:** không lấy key map chứa dấu chấm của ví dụ trên để suy ra cú pháp list index thay đổi. `pipelines[0]` vẫn là chỉ số của list, còn `labels.[deployment.zone]` là key của map có chứa dấu chấm.

## 10. Bind object có nhiều loại dữ liệu

Một record lồng nhau có thể chứa `String`, `URI`, `Duration`, `DataSize`, enum, số và boolean, miễn Binder hỗ trợ chuyển đổi phù hợp.

Ví dụ:

~~~yaml
app:
  workers:
    - name: thumbnail
      enabled: true
      max-payload: 8MB
      retry-delay: 200ms
      mode: ASYNC
    - name: cleanup
      enabled: false
      max-payload: 1MB
      retry-delay: 2s
      mode: SYNC
~~~

Java:

~~~java
import java.time.Duration;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "app")
public record WorkerCatalogProperties(
    List<Worker> workers
) {
    public enum Mode {
        SYNC, ASYNC
    }

    public record Worker(
        String name,
        boolean enabled,
        DataSize maxPayload,
        Duration retryDelay,
        Mode mode
    ) {}
}
~~~

| YAML value | Java type | Ý nghĩa |
| --- | --- | --- |
| `true` | `boolean` | Bật một worker |
| `8MB` | `DataSize` | Dung lượng |
| `200ms` | `Duration` | Thời lượng |
| `ASYNC` | `Mode` enum | Chế độ thuộc tập định nghĩa |
| `thumbnail` | `String` | Tên định danh |

Đừng viết toàn bộ field dưới dạng `String` chỉ vì dữ liệu đọc từ file. Kiểu dữ liệu giúp consumer rõ intent, và việc chuyển đổi sai có thể được phát hiện khi khởi động.

Nếu có enum không hợp lệ, URI lỗi hoặc thời lượng không chuyển đổi được, Binder có thể báo lỗi kiểu dữ liệu. Đó là lỗi binding, không phải lỗi không tìm thấy file hay sai `@ConfigurationPropertiesScan`.

## 11. Constructor binding với record lồng nhau

Trong Spring Boot 3.x, record có một canonical constructor phù hợp thường là ứng viên tự nhiên cho constructor binding. Khi root record được đăng ký bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`, Binder có thể tạo cây record thông qua constructor.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "app")
public record PipelineProperties(
    List<Pipeline> pipelines
) {
    public record Pipeline(
        String name,
        Retry retry
    ) {}

    public record Retry(
        int maxAttempts,
        Duration backoff
    ) {}
}
~~~

Cấu hình:

~~~yaml
app:
  pipelines:
    - name: orders
      retry:
        max-attempts: 3
        backoff: 250ms
~~~

Binder cần xây `Retry(3, Duration.ofMillis(250))`, sau đó `Pipeline("orders", retry)`, cuối cùng là `PipelineProperties(List.of(pipeline))` theo cách phù hợp với quy tắc binding của nó.

**Không cần** đánh dấu `@Component` trên nested records. Chúng không phải component riêng. Thậm chí thêm `@Component` lên root record constructor-bound có thể đưa việc tạo bean sang cơ chế dependency injection của Spring thay vì constructor binding của Binder.

### Một record có thật sự immutable hoàn toàn?

Record khiến **tham chiếu field** là final, nhưng một `List` hoặc `Map` bên trong có thể vẫn là collection có khả năng thay đổi tùy implementation. Không suy ra `record List<...>` là immutable sâu.

Nếu các consumer có thể mutate list, cần thiết kế an toàn: không sửa trực tiếp collection cấu hình, chuyển thành snapshot bất biến nếu có yêu cầu, hoặc chỉ duy trì thao tác đọc. Các lựa chọn này thuộc thiết kế Java của ứng dụng, khác với khả năng bind từ YAML.

## 12. JavaBean mutable cho cấu hình list lồng nhau

Không bắt buộc phải dùng record. Một số ứng dụng lâu đời hoặc thư viện cần JavaBean có constructor mặc định và getter/setter.

Ví dụ đơn giản:

~~~java
import java.util.ArrayList;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public class PipelineSettings {
    private List<Pipeline> pipelines = new ArrayList<>();

    public List<Pipeline> getPipelines() {
        return pipelines;
    }

    public void setPipelines(List<Pipeline> pipelines) {
        this.pipelines = pipelines;
    }

    public static class Pipeline {
        private String name;
        private boolean enabled;

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }
    }
}
~~~

Với:

~~~yaml
app:
  pipelines:
    - name: orders
      enabled: true
    - name: invoices
      enabled: false
~~~

Binder có thể tạo các `Pipeline` JavaBean và điền dữ liệu qua setter. Các bean kiểu mutable dùng trong setter binding có quy tắc về constructor, getter, setter và collection initialization cần được đảm bảo phù hợp với mô hình thực tế.

### Chọn record hay JavaBean?

| Nhu cầu | Record/constructor binding | JavaBean/setter binding |
| --- | --- | --- |
| Muốn cấu hình có hợp đồng bất biến rõ ràng | Thường thuận lợi | Cần tự hạn chế mutation |
| Muốn không viết boilerplate getter/setter | Gọn | Tốn mã hơn |
| Tương thích một thư viện cần setter | Không phù hợp trực tiếp | Thường phù hợp |
| Muốn đặt default ở field initializer | Không theo kiểu JavaBean | Có thể |
| Có nhiều nested object/list | Hỗ trợ | Hỗ trợ |
| Bean được tạo qua `@Bean` rồi bind lên instance | Không dùng constructor binding | Có thể bind qua setter phù hợp |

Cả hai đều dùng `@ConfigurationProperties` để biểu đạt prefix; khác chủ yếu ở **cách tạo và điền dữ liệu vào đối tượng**.

## 13. Validation cho từng phần tử và object lồng nhau

Khi cấu hình có nhiều tầng, validation càng cần thiết. Nếu thiếu `destinations` hoặc `url`, mã nghiệp vụ có thể lỗi rất xa thời điểm khởi động. Spring Boot có thể kết hợp configuration properties binding với Jakarta Bean Validation.

Ví dụ:

~~~java
package com.example.orders.config;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record PipelineProperties(
    @NotEmpty List<@Valid Pipeline> pipelines
) {
    public record Pipeline(
        @NotBlank String name,
        boolean enabled,
        @NotNull @Valid Retry retry,
        @NotEmpty List<@Valid Destination> destinations,
        Map<String, String> labels
    ) {}

    public record Retry(
        @Min(0) int maxAttempts,
        @NotNull Duration backoff
    ) {}

    public record Destination(
        @NotBlank String id,
        @NotNull URI url,
        @NotNull Duration timeout,
        Map<String, String> headers
    ) {}
}
~~~

Để validation hoạt động trong Spring Boot 3.x, project cần provider và dependency phù hợp, thông dụng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Vai trò các annotation:

- `@Validated`: yêu cầu kiểm tra bean configuration properties theo cơ chế validation được cấu hình.
- `@NotEmpty` trên list: bắt buộc list có ít nhất một phần tử (nếu nghiệp vụ yêu cầu).
- `@Valid`: lan truyền validation vào object con hoặc phần tử của collection khi provider hỗ trợ.
- `@NotBlank` trên string: không cho phép thiếu/chuỗi rỗng hoặc chỉ chứa khoảng trắng.
- `@NotNull`: thể hiện một object/value bắt buộc có mặt.
- `@Min(0)`: `max-attempts` không âm.

Khi `app.pipelines[0].destinations[1].url` thiếu, validation có thể giúp phát hiện một lỗi có đường dẫn sâu thay vì để component chỉ lỗi khi thực hiện request thật.

### Kiểm tra giá trị bên trong Map

Nếu cần validate map values phức tạp, có thể dùng kiểu `Map<String, @Valid SomeConfig>` cùng những constraint phù hợp. Với `Map<String,String>` headers, cần phân biệt “map có mặt” với “mọi key/value trong map đều hợp lệ”. Một `@NotEmpty` trên map không chứng minh rằng mỗi header name đáp ứng chuẩn HTTP.

Những ràng buộc liên thuộc, như “pipeline enabled thì phải có destination” hoặc “timeout của backup lớn hơn timeout primary”, có thể cần validation tùy biến ở cấp object. Hãy đặt ràng buộc ở nơi phản ánh đúng domain.

### Không phải chỉ thêm @Valid là đủ

Nếu project chưa có Bean Validation provider, hoặc root bean chưa được đăng ký đúng cơ chế, việc annotate các field không bảo đảm tất cả validation sẽ được thực thi. Kiểm tra đủ dependency, `@ConfigurationPropertiesScan`/`@EnableConfigurationProperties` và annotation trên root.

## 14. List rỗng, key thiếu và default

Đối với binding collection, cần phân biệt:

1. **Không khai báo key list:** `app.pipelines` không tồn tại trong nguồn cấu hình.
2. **Khai báo danh sách rỗng:** YAML có `pipelines: []`.
3. **Khai báo một phần tử nhưng thiếu field:** có `pipelines[0].name` nhưng không có `pipelines[0].destinations`.
4. **Khai báo field với value rỗng:** có `name: ""` hoặc `url: ""`.

Những trường hợp này không đồng nghĩa:

~~~yaml
# Trường hợp A: không có pipelines
app:
  service-name: order-service
~~~

~~~yaml
# Trường hợp B: pipelines rỗng
app:
  pipelines: []
~~~

~~~yaml
# Trường hợp C: có phần tử nhưng destinations thiếu
app:
  pipelines:
    - name: orders
      enabled: true
~~~

Nếu một thành phần yêu cầu ít nhất một pipeline và mỗi pipeline có ít nhất một destination, dùng `@NotEmpty` với `@Valid` như ví dụ để báo lỗi phù hợp.

Với constructor-bound record, đừng giả định list sẽ luôn là `List.of()` khi key thiếu. Model cần có default rõ ràng nếu muốn coi thiếu key là collection rỗng. Với JavaBean mutable, có thể khởi tạo field list và dùng setter binding theo quy tắc hỗ trợ.

### Default cho một object lồng

Spring Boot Binder có hỗ trợ annotation `@DefaultValue` cho constructor binding. Ví dụ khi muốn cung cấp retry mặc định:

~~~java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app")
public record SimplePipelineProperties(
    @DefaultValue List<Pipeline> pipelines
) {
    public record Pipeline(
        String name,
        @DefaultValue Retry retry
    ) {}

    public record Retry(
        @DefaultValue("3") int maxAttempts,
        @DefaultValue("250ms") Duration backoff
    ) {}
}
~~~

Ở đây, `@DefaultValue` trống trên object nested có thể yêu cầu Binder tạo nested object bằng default values phù hợp, nếu điều kiện binding của phiên bản cho phép. Với list, cần xác định semantics mặc định của Binder trong Spring Boot đang dùng trước khi dựa vào việc list thiếu sẽ được tạo thành loại collection cụ thể; có thể đơn giản hơn nếu dùng validation hoặc cung cấp `pipelines: []` tường minh.

**Không dùng default để che thiếu dữ liệu thiết yếu.** Nếu pipeline enabled mà thiếu URL, một fallback mơ hồ có thể nguy hiểm hơn việc ứng dụng fail fast.

## 15. Điều cực quan trọng: list thường bị thay thế, không merge theo index

Khi cùng một list được khai báo ở **nhiều PropertySource/Config Data documents** với độ ưu tiên khác nhau, Spring Boot Configuration Properties Binder thường áp dụng **quy tắc thay thế cả list từ nguồn có ưu tiên cao hơn**, chứ không trộn tự động từng object theo index.

Ví dụ file cơ sở:

~~~yaml
# application.yml
app:
  pipelines:
    - name: orders
      enabled: true
      retry:
        max-attempts: 3
        backoff: 250ms
      destinations:
        - id: primary
          url: https://orders.example.test/events
          timeout: 2s
    - name: invoices
      enabled: true
      retry:
        max-attempts: 2
        backoff: 1s
      destinations:
        - id: billing
          url: https://billing.example.test/events
          timeout: 4s
~~~

Tệp theo profile `dev`:

~~~yaml
# application-dev.yml
app:
  pipelines:
    - name: orders
      enabled: false
~~~

Khi `dev` active, nếu `application-dev.yml` là nguồn thắng cho list, đừng mong cấu hình cuối cùng trở thành:

~~~text
pipelines[0] = orders (enabled=false, retry kế thừa, destinations kế thừa)
pipelines[1] = invoices (kế thừa hoàn toàn)
~~~

Đó là cách suy luận theo **deep merge**; list binding thông thường **không làm vậy**. Trong ví dụ, nguồn profile cao hơn cung cấp list với một phần tử `orders`, nên các giá trị nested của phần tử đó phải được khai báo đủ theo contract (hoặc có default thích hợp). Phần tử `invoices` từ list của nguồn thấp hơn không tự được thêm lại.

### Vì sao lại quan trọng với list object?

Nếu production cần tất cả endpoint được xác định rõ, một profile override chỉ ghi:

~~~properties
app.pipelines[0].retry.max-attempts=5
~~~

không nên được hiểu là thay `max-attempts` của pipeline thứ nhất trong một list dài từ file gốc mà **giữ mọi field và phần tử còn lại**. Độ ưu tiên list khiến kết quả khác kỳ vọng: có thể chỉ còn dữ liệu index/field hiện diện trong nguồn thắng, khiến validation bị lỗi.

**Cách triển khai an toàn:**

- Định nghĩa trọn list cho từng profile hoặc nguồn override khi dùng list configuration.
- Hoặc nếu muốn override từng phần tử theo key định danh, chuyển mô hình sang **map của object**.
- Hoặc giảm mức override bằng cách tách các phần cần thay đổi thành key scalar riêng, thay vì đè sâu vào list.

### Bảng so sánh list và map khi có nguồn chồng nhau

| Đặc điểm | `List<Pipeline>` | `Map<String,Pipeline>` |
| --- | --- | --- |
| Cách xác định phần tử | Index 0, 1, 2... | Key như `orders`, `invoices` |
| Thứ tự phần tử | Có thể mang ý nghĩa | Không nên dựa vào thứ tự như contract mặc định |
| Override từ nguồn ưu tiên cao | List được thay thế theo quy tắc binder | Map có cơ chế kết hợp theo key thuận lợi hơn |
| Thêm/xóa phần tử | Thay list tương ứng | Thêm/xóa hoặc sửa key rõ ràng hơn trong cấu hình |
| Tình huống phù hợp | Failover order, steps chạy tuần tự | Registry object tra theo tên |

Đối với map, quy tắc merge và overwrite value cũng phụ thuộc loại value và cấu trúc nguồn; không coi map là deep merge vô điều kiện. Nhưng map thường đúng ngữ nghĩa hơn khi identifier quan trọng còn index không quan trọng.

## 16. Chuyển list sang Map khi cần override theo mã định danh

Ví dụ thiết kế thay thế:

~~~yaml
app:
  pipeline-by-name:
    orders:
      enabled: true
      retry:
        max-attempts: 3
        backoff: 250ms
    invoices:
      enabled: false
      retry:
        max-attempts: 1
        backoff: 1s
~~~

Model:

~~~java
import java.time.Duration;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record PipelineRegistryProperties(
    Map<String, PipelineEntry> pipelineByName
) {
    public record PipelineEntry(
        boolean enabled,
        Retry retry
    ) {}

    public record Retry(
        int maxAttempts,
        Duration backoff
    ) {}
}
~~~

Truy cập:

~~~java
PipelineRegistryProperties.PipelineEntry orders =
    registry.pipelineByName().get("orders");
~~~

Mô hình map có các phần tử với key ổn định. Khi cần sắp xếp pipeline theo thứ tự, bổ sung trường `order` hoặc một danh sách tên riêng thay vì phụ thuộc thứ tự iteration của map.

**Chọn list khi thứ tự là dữ liệu quan trọng; chọn map khi mã định danh và khả năng tìm phần tử theo key quan trọng.** Đây là quyết định mô hình hóa domain, không chỉ là chi tiết cú pháp Spring Boot.

## 17. Profile-specific files và list replacement

Trong Spring Boot, các tệp như `application-dev.yml`, `application-prod.yml` tham gia Config Data khi profile tương ứng được bật. Với key scalar, mọi người thường quen việc ghi đè một value và giữ các value khác từ file cơ sở. Nhưng với **list**, ví dụ bên dưới có ý nghĩa đặc biệt.

Tệp cơ sở:

~~~yaml
app:
  gateways:
    - id: north
      url: https://north.example.test
    - id: south
      url: https://south.example.test
~~~

Tệp `application-dev.yml`:

~~~yaml
app:
  gateways:
    - id: local
      url: http://localhost:8090
~~~

Khi chạy:

~~~bash
java -jar order-service.jar --spring.profiles.active=dev
~~~

Giá trị list thắng trong tình huống thông thường là danh sách chứa `local`. Không tự kỳ vọng có ba phần tử `north`, `south`, `local` hoặc giữ hai phần tử cũ và thay field `[0]`.

Đối với danh sách object phức tạp, đây là điểm thường gây lỗi “ở local chạy được, sang prod thiếu nested field” nếu một profile chỉ override một vài key nhưng không khai báo đầy đủ list.

## 18. Command-line và environment variables cho list lồng nhau

Có thể dùng tên key theo chỉ số để cung cấp dữ liệu từ nguồn ngoài file.

Command-line argument Spring Boot:

~~~bash
java -jar order-service.jar \
  '--app.pipelines[0].name=orders' \
  '--app.pipelines[0].enabled=true' \
  '--app.pipelines[0].retry.max-attempts=3' \
  '--app.pipelines[0].retry.backoff=250ms'
~~~

Trong ví dụ, dấu nháy đơn là cú pháp bảo vệ argument của shell Unix-like. Nếu chạy PowerShell/CMD, cần cách quote phù hợp. Trên command-line với object lồng nhau, cần xem xét đủ các key bắt buộc của cả list do quy tắc list replacement.

Biến môi trường sử dụng quy tắc đặt tên dành cho Spring Boot:

~~~text
app.pipelines[0].name               -> APP_PIPELINES_0_NAME
app.pipelines[0].retry.max-attempts -> APP_PIPELINES_0_RETRY_MAXATTEMPTS
app.pipelines[1].enabled            -> APP_PIPELINES_1_ENABLED
~~~

Với biến môi trường, Spring Boot thường áp dụng các bước: chuyển dấu chấm thành `_`, bỏ dấu gạch ngang trong tên canonical, viết hoa, đồng thời biểu diễn index danh sách bằng số được bao quanh bởi dấu gạch dưới.

Ví dụ trong shell hỗ trợ cú pháp gán biến môi trường như Bash:

~~~bash
APP_PIPELINES_0_NAME=orders \
APP_PIPELINES_0_ENABLED=true \
APP_PIPELINES_0_RETRY_MAXATTEMPTS=3 \
APP_PIPELINES_0_RETRY_BACKOFF=250ms \
java -jar order-service.jar
~~~

Trong Kubernetes hoặc CI/CD, có thể khai báo các biến tương ứng trong cấu hình môi trường runtime. Tránh đưa cả hệ thống nhiều tầng thành hàng trăm biến môi trường không rõ contract; với list lớn, một file YAML được mount hoặc import có thể dễ bảo trì hơn.

**Cẩn thận precedence:** nếu những biến môi trường này tạo một list ở nguồn cao hơn cấu hình file, việc chỉ cấp một số index/field có thể khiến cấu hình list cuối cùng không còn các phần tử từ file cơ sở. Đừng dùng override sâu vào list nếu không quản lý đầy đủ cấu trúc nguồn thắng.

## 19. Có nên dùng @Value để đọc List<...>?

`@Value` tiện cho một hoặc vài value scalar, ví dụ:

~~~java
@Value("\${app.client.timeout:2s}")
private Duration timeout;
~~~

Nhưng với `List<Pipeline>`, mỗi phần tử lại có `Retry` và `List<Destination>`, dùng `@Value` để tự phân tách chuỗi không còn phù hợp. Annotation không phải giải pháp thay thế cho cả hệ thống Binder có nested collections, type conversion và validation.

`Environment.getProperty("app.pipelines[0].name")` cũng có thể trả một value đơn, nhưng nếu tự ghép hàng trăm tên key và index, code phải tự biết có bao nhiêu phần tử, xử lý null, chuyển kiểu và xác minh quan hệ cha-con.

Ví dụ cách tra cứu riêng lẻ:

~~~java
String first = environment.getProperty(
    "app.pipelines[0].name");
~~~

Việc này có thể hữu ích khi chẩn đoán, nhưng không nên xây toàn bộ cây `PipelineProperties` bằng cách gọi thủ công từng key nếu Binder đã đáp ứng nhu cầu.

**Ưu tiên `@ConfigurationProperties` cho list object lồng nhau.** Chỉ dùng `Environment` hoặc `@Value` khi thật sự cần một key riêng hoặc một thông tin đơn giản.

## 20. Cấu hình lồng nhau trong nhiều file import

Một ứng dụng có thể đặt danh sách trong file được nhập bằng `spring.config.import`:

~~~properties
# application.properties
spring.config.import=classpath:config/pipelines.yml
~~~

Tệp `src/main/resources/config/pipelines.yml`:

~~~yaml
app:
  pipelines:
    - name: orders
      enabled: true
      retry:
        max-attempts: 3
        backoff: 250ms
      destinations:
        - id: primary
          url: https://orders.example.test/events
          timeout: 2s
~~~

Spring Boot đưa Config Data import vào Environment theo cơ chế import, sau đó Binder có thể bind `app.pipelines`. `@ConfigurationProperties` không cần biết tệp đó là file gốc, file profile-specific hay file import.

Nếu hai nguồn cùng khai báo `app.pipelines`, vẫn cần xét **thứ tự property sources và quy tắc list replacement**. Việc import thêm một tệp không đồng nghĩa với việc tự động cộng list của hai tệp.

### Lưu ý về file ngoài JAR

~~~properties
spring.config.import=optional:file:./config/pipelines-local.yml
~~~

Cú pháp trên cho phép bỏ qua location nếu tệp không tồn tại. Nhưng nếu file tồn tại và chứa list chỉ có một pipeline, nó có thể thay thế list từ nguồn thấp hơn. Điều này là hành vi precedence, không phải tính năng cộng các phần tử.

Nếu file cấu hình là bắt buộc cho production, không dùng `optional:` để vô tình bỏ qua lỗi triển khai; hãy đặt đường dẫn và validation phù hợp.

## 21. Định danh, thứ tự, duplicate và hợp đồng của list

Binder hiểu **danh sách vị trí**. Nó không tự biết rằng hai object có `name: orders` giống nhau là không hợp lệ trong domain của bạn.

~~~yaml
app:
  pipelines:
    - name: orders
      enabled: true
    - name: orders
      enabled: false
~~~

Cú pháp YAML có hai phần tử. Nếu muốn `name` là duy nhất, cần thêm validation nghiệp vụ hoặc chuyển sang map theo key. `@NotBlank` chỉ đảm bảo mỗi name có giá trị, không bắt trùng giữa hai phần tử.

Những câu hỏi thiết kế quan trọng:

- Thứ tự của list có làm thay đổi hành vi không?
- Có cho phép hai object trùng tên hoặc trùng `id` không?
- Nếu `destinations` rỗng thì pipeline có hợp lệ không?
- Nếu pipeline `enabled=false`, vẫn yêu cầu cấu hình đầy đủ hay cho phép thiếu một số nhóm?
- Khi một destination bị lỗi, hệ thống thử destination tiếp theo theo thứ tự hay theo policy riêng?
- Bản cấu hình theo profile có cần lặp toàn bộ list hay chỉ một phần?

`@ConfigurationProperties` là cơ chế ánh xạ dữ liệu; nó không tự quyết định những quy tắc nghiệp vụ này. Với ràng buộc đặc thù, thiết kế validator rõ ràng sẽ giúp phát hiện lỗi sớm.

## 22. Test binding của nested list trong Spring Boot

Một integration test có thể chứng minh Spring context đã đăng ký root properties bean và bind đủ nested list.

~~~java
package com.example.orders;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import com.example.orders.config.PipelineProperties;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
    "app.pipelines[0].name=orders",
    "app.pipelines[0].enabled=true",
    "app.pipelines[0].retry.max-attempts=3",
    "app.pipelines[0].retry.backoff=250ms",
    "app.pipelines[0].destinations[0].id=primary",
    "app.pipelines[0].destinations[0].url=https://orders.example.test/events",
    "app.pipelines[0].destinations[0].timeout=2s",
    "app.pipelines[0].destinations[0].headers.x-channel=retail",
    "app.pipelines[0].labels.owner=team-orders"
})
class PipelinePropertiesTest {
    @Autowired
    PipelineProperties properties;

    @Test
    void nestedListAndObjectsAreBound() {
        assertThat(properties.pipelines()).hasSize(1);

        var pipeline = properties.pipelines().get(0);
        assertThat(pipeline.name()).isEqualTo("orders");
        assertThat(pipeline.retry().maxAttempts()).isEqualTo(3);
        assertThat(pipeline.retry().backoff())
            .isEqualTo(Duration.ofMillis(250));

        assertThat(pipeline.destinations()).hasSize(1);
        assertThat(pipeline.destinations().get(0).url().getHost())
            .isEqualTo("orders.example.test");
    }
}
~~~

Đoạn test giả định ứng dụng có `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` để đăng ký `PipelineProperties`, và có `spring-boot-starter-test` trong test dependencies. Với Bean Validation ở mẫu khác, cần cung cấp đủ field bắt buộc theo constraints tương ứng.

### Test thuần Java của consumer

Nếu chỉ muốn test logic của một service dùng typed config, có thể tự tạo cây record trong test:

~~~java
var retry = new PipelineProperties.Retry(
    3, Duration.ofMillis(250));

var destination = new PipelineProperties.Destination(
    "primary",
    URI.create("https://orders.example.test/events"),
    Duration.ofSeconds(2),
    Map.of("x-channel", "retail")
);

var pipeline = new PipelineProperties.Pipeline(
    "orders",
    true,
    retry,
    List.of(destination),
    Map.of("owner", "team-orders")
);

var properties = new PipelineProperties(List.of(pipeline));
~~~

Unit test kiểu này giúp kiểm tra consumer mà không cần Spring context, nhưng **không chứng minh Binder xử lý YAML/index syntax đúng**. Muốn kiểm binding thật, sử dụng context test.

## 23. ApplicationContextRunner để test riêng configuration properties

Khi không muốn khởi chạy toàn bộ web application, có thể dùng `ApplicationContextRunner` của Spring Boot test để tạo một context nhỏ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import com.example.orders.config.PipelineProperties;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class PipelineBindingRunnerTest {

    private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
            .withUserConfiguration(TestConfig.class)
            .withPropertyValues(
                "app.pipelines[0].name=orders",
                "app.pipelines[0].enabled=true",
                "app.pipelines[0].retry.max-attempts=3",
                "app.pipelines[0].retry.backoff=250ms",
                "app.pipelines[0].destinations[0].id=primary",
                "app.pipelines[0].destinations[0].url=https://orders.example.test/events",
                "app.pipelines[0].destinations[0].timeout=2s"
            );

    @Test
    void bindsNestedList() {
        contextRunner.run(context -> {
            assertThat(context).hasSingleBean(PipelineProperties.class);
            var config = context.getBean(PipelineProperties.class);
            assertThat(config.pipelines()).hasSize(1);
            assertThat(config.pipelines().get(0).destinations())
                .hasSize(1);
        });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(PipelineProperties.class)
    static class TestConfig {}
}
~~~

Nếu context test không bật các auto-configuration/conversion service như ứng dụng chính, việc kiểm các kiểu đặc thù cần chọn test setup phù hợp. Một `@SpringBootTest` tích hợp đầy đủ thường là cách đơn giản hơn để kiểm toàn bộ Spring Boot binding, trong khi `ApplicationContextRunner` giúp cô lập registration và property inputs.

## 24. Chẩn đoán lỗi ở đường dẫn lồng nhau

### Lỗi A: chưa đăng ký root @ConfigurationProperties bean

~~~java
@ConfigurationProperties(prefix = "app")
public record PipelineProperties(List<Pipeline> pipelines) {}
~~~

Nếu `PipelineProperties` không nằm trong phạm vi `@ConfigurationPropertiesScan` và cũng không được `@EnableConfigurationProperties` đăng ký, consumer có thể gặp lỗi thiếu bean dù YAML hợp lệ.

**Cách xử lý:** kiểm package scan, annotation, configuration class và cách đăng ký bean. Không thêm `@Component` vào record constructor-bound để “cứu” lỗi thiếu bean.

### Lỗi B: sai prefix

~~~java
@ConfigurationProperties(prefix = "application")
~~~

Trong khi file bắt đầu bằng `app:`. Binder không tự hiểu `application` và `app` là cùng một prefix. **Cách xử lý:** thống nhất prefix trên record và tên key thật trong nguồn cấu hình.

### Lỗi C: YAML indent sai

~~~yaml
app:
  pipelines:
    - name: orders
      retry:
        max-attempts: 3
        destinations:
          - id: primary
~~~

`destinations` đang nằm dưới `retry`. **Cách xử lý:** chuyển nó về cùng mức với `retry` nếu kiểu Java định nghĩa destination là trường của `Pipeline`.

### Lỗi D: nhầm một object với list object

~~~yaml
app:
  pipelines:
    name: orders
    enabled: true
~~~

`pipelines` ở đây là mapping đơn, không phải sequence. Nhưng Java đòi `List<Pipeline>`. **Cách xử lý:** dùng dấu `-` cho phần tử:

~~~yaml
app:
  pipelines:
    - name: orders
      enabled: true
~~~

### Lỗi E: thiếu chỉ số trong properties

~~~properties
app.pipelines.name=orders
app.pipelines.retry.max-attempts=3
~~~

Cú pháp không chỉ rõ phần tử list. **Cách xử lý:** dùng `app.pipelines[0].name` và `app.pipelines[0].retry.max-attempts`.

### Lỗi F: dữ liệu sai kiểu

~~~properties
app.pipelines[0].retry.max-attempts=many
app.pipelines[0].retry.backoff=tomorrow
~~~

Nếu Java cần `int` và `Duration`, Binder có thể lỗi conversion. **Cách xử lý:** dùng số nguyên và time unit hợp lệ, ví dụ `3` và `250ms`.

### Lỗi G: list từ profile không giữ cấu hình gốc

`application.yml` có hai pipelines, `application-dev.yml` chỉ viết một phần `pipelines[0]`. Khi active `dev`, pipeline thứ hai mất, nested field có thể thiếu.

**Cách xử lý:** nhận diện list replacement; khai báo trọn list ở nguồn thắng hoặc chuyển sang map theo mã định danh.

### Lỗi H: thiếu validation cho nested element

Một `Destination.url` có thể null nếu key thiếu, nhưng consumer vẫn gọi `dest.url().getHost()`. **Cách xử lý:** thêm `@Valid` cho nested list và `@NotNull` cho field bắt buộc, bật validation provider.

### Lỗi I: kỳ vọng thay file cấu hình là object tự refresh

Một developer chỉnh `application.yml` trong lúc ứng dụng đang chạy nhưng record `PipelineProperties` không đổi. Config Data thường được nạp lúc startup và bean được bind lúc khởi tạo.

**Cách xử lý:** phân biệt startup configuration với dynamic configuration. Nếu cần reload động, thiết kế cơ chế refresh/rebind phù hợp; `@ConfigurationProperties` tự nó không phải file watcher.

## 25. Quy trình debug theo tầng

Khi dữ liệu của danh sách lồng nhau khác kỳ vọng, kiểm tra theo thứ tự:

1. **Nguồn thật được nạp:** file cơ sở, profile-specific file, import, biến môi trường hoặc command-line?
2. **Tên prefix:** `app` trên annotation có khớp với cấu hình?
3. **Hình dạng cấu trúc:** YAML sequence có dấu `-`? `retry` và `destinations` đúng cấp?
4. **Index:** properties có `[0]`, `[1]` rõ ràng và liên tục?
5. **Loại Java:** `List<Pipeline>`, `List<Destination>`, `Map<String,String>` có đúng cấu trúc mong muốn?
6. **Register root bean:** `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` đã hoạt động trong đúng package?
7. **Constructor/setters:** đang dùng record constructor-bound hay mutable JavaBean đúng cơ chế?
8. **Kiểu dữ liệu:** URI/Duration/enum/int có conversion thành công?
9. **Validation:** nested object/list đã được validate theo yêu cầu?
10. **Precedence:** có nguồn cao hơn đang thay **toàn bộ list** không?
11. **Thời điểm:** đây là config lúc startup hay developer đang chờ file tự reload?
12. **Bằng chứng:** viết integration test bind một list nhỏ rồi mở rộng cấu hình từng bước.

Nếu ứng dụng có Spring Boot Actuator được bảo vệ phù hợp, endpoint `configprops` và `env` có thể hỗ trợ quan sát cấu hình đã bind và một số thông tin nguồn. Không mở công khai endpoint cấu hình hoặc in toàn bộ map headers/credential vào log. Một map cấu hình có thể chứa token, key hoặc dữ liệu nhạy cảm.

## 26. Những hiểu nhầm phổ biến

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Một danh sách object trong YAML chỉ là chuỗi có dấu phẩy.” | YAML sequence chứa các mapping; Binder chuyển thành phần tử object theo kiểu Java. |
| “List<Pipeline> chỉ bind các field scalar, không bind nested object.” | Binder có thể bind object, list và map lồng nhau nếu model phù hợp. |
| “Mỗi nested record phải có @Component riêng.” | Nested record là value object của root model, không phải Spring bean độc lập. |
| “Cứ thêm @Component lên root record để Spring tìm thấy.” | Với constructor-bound record, dùng dedicated scan/enable thay vì component construction. |
| “YAML list phải khai báo [0], [1].” | YAML thường dùng dấu `-`; chỉ số thể hiện tường minh trong flat properties. |
| “Trong properties có thể bỏ [0] khi chỉ có một phần tử.” | List indexed binding cần đường dẫn có chỉ số rõ ràng trong dạng cấu trúc này. |
| “Profile ghi một field trong list thì mọi phần còn lại được merge từ file gốc.” | List trong Configuration Properties thường bị thay thế theo nguồn thắng, không deep merge theo index. |
| “Thêm @Valid một lần là mọi constraint tự hoạt động.” | Cần validation provider, root registration và propagation vào nested object/list. |
| “Record chứa List nghĩa là List bất biến tuyệt đối.” | Record giữ tham chiếu final, nhưng collection bên trong có thể mutable. |
| “Sửa YAML khi chương trình chạy thì bean tự đổi.” | Config Data/binding thường diễn ra ở startup, refresh động là một cơ chế riêng. |
| “Map luôn giống List và bị thay cả map.” | Map có semantics binding theo key khác list; cần chọn cấu trúc đúng nhu cầu. |
| “@Value là cách tốt nhất để parse tất cả nested collections.” | @ConfigurationProperties Binder phù hợp hơn với cấu trúc lồng nhau có kiểu. |

## 27. Bài tập thực hành

### Bài 1 — Một list object có nested record

Cho:

~~~yaml
app:
  connectors:
    - name: payment
      retry:
        attempts: 4
        delay: 200ms
    - name: search
      retry:
        attempts: 2
        delay: 1s
~~~

Tạo model:

~~~java
@ConfigurationProperties(prefix = "app")
public record ConnectorProperties(List<Connector> connectors) {
    public record Connector(String name, Retry retry) {}
    public record Retry(int attempts, Duration delay) {}
}
~~~

**Hỏi:** `connectors.get(1).retry().delay()` là bao nhiêu?

**Đáp án:** một `Duration` tương ứng `1s`, với giả định dữ liệu được nạp/bind thành công.

### Bài 2 — Chuyển YAML sang properties

Cho:

~~~yaml
app:
  jobs:
    - name: daily
      triggers:
        - kind: cron
          expression: "0 0 2 * * *"
~~~

**Đáp án minh họa:**

~~~properties
app.jobs[0].name=daily
app.jobs[0].triggers[0].kind=cron
app.jobs[0].triggers[0].expression=0 0 2 * * *
~~~

Lưu ý syntax cron ở đây chỉ là một chuỗi cấu hình minh họa, không phải lời bảo đảm scheduler đã được đăng ký.

### Bài 3 — Tìm lỗi indent

~~~yaml
app:
  jobs:
    - name: daily
      retry:
        attempts: 3
        triggers:
          - kind: cron
~~~

Java định nghĩa `Job(String name, Retry retry, List<Trigger> triggers)`.

**Đáp án:** `triggers` đang thuộc `retry`; phải đưa nó về cùng cấp `name` và `retry` của phần tử `jobs[0]`.

### Bài 4 — List và profile override

`application.yml` có ba phần tử `app.jobs`. `application-prod.yml` khai báo `app.jobs` chỉ với một job.

**Hỏi:** Spring Boot Binder có tự cộng job production vào ba job cơ sở không?

**Đáp án:** không. List ở nguồn thắng được dùng theo quy tắc replacement; cần khai báo đầy đủ list mong muốn hoặc thay mô hình dữ liệu.

### Bài 5 — Map có key chứa dấu chấm

Cần một map `labels` có key chính xác là `deployment.zone`.

**Đáp án:** trong flat properties có thể dùng:

~~~properties
app.pipelines[0].labels.[deployment.zone]=asia
~~~

Trong YAML:

~~~yaml
labels:
  "[deployment.zone]": asia
~~~

Bracket notation diễn đạt key của map cần giữ.

### Bài 6 — Validation của list object

Một pipeline bắt buộc phải có ít nhất một destination, mỗi destination bắt buộc có URL.

**Đáp án gợi ý:** đặt `@NotEmpty List<@Valid Destination> destinations` trên model và `@NotNull URI url` bên trong `Destination`, dùng `@Validated` trên root cùng validation provider phù hợp.

### Bài 7 — Environment variable cho index

Flat property:

~~~properties
app.pipelines[0].retry.max-attempts=3
~~~

**Đáp án tên biến môi trường theo quy tắc Spring Boot:**

~~~text
APP_PIPELINES_0_RETRY_MAXATTEMPTS
~~~

Không giữ dấu gạch ngang trong tên biến môi trường canonical chuyển đổi.

### Bài 8 — Lỗi không xuất hiện bean

Root record có `@ConfigurationProperties(prefix="app")` nhưng service không inject được `PipelineProperties`.

**Đáp án:** kiểm tra `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` và phạm vi package. Có dữ liệu trong YAML chưa đồng nghĩa bean được đăng ký.

### Bài 9 — List rỗng

Cấu hình có:

~~~yaml
app:
  pipelines: []
~~~

Root record có `@NotEmpty List<@Valid Pipeline> pipelines`.

**Đáp án:** nếu validation được kích hoạt đúng, ràng buộc `@NotEmpty` không chấp nhận danh sách rỗng. Đây là kiểm tra nghiệp vụ mong muốn, không phải lỗi YAML syntax.

### Bài 10 — Khi nào nên chọn Map?

Có 500 connectors, mỗi connector được nhận diện bởi tên duy nhất, thứ tự không quan trọng và các môi trường khác nhau muốn sửa settings theo tên.

**Đáp án gợi ý:** dùng `Map<String, Connector>` có thể diễn đạt đúng hợp đồng hơn `List<Connector>`, vì key có ý nghĩa và cơ chế binding/override theo key thuận lợi hơn. Nếu thứ tự là yêu cầu, vẫn cần một biểu diễn thứ tự rõ ràng.

## 28. Bảng ghi nhớ cuối bài

| Mục tiêu | Cách biểu diễn |
| --- | --- |
| Danh sách object trong YAML | `- name: orders` dưới key list |
| Danh sách object trong properties | `app.pipelines[0].name=orders` |
| List trong List trong properties | `app.pipelines[0].destinations[1].url=...` |
| Model root | `@ConfigurationProperties(prefix="app")` |
| Model danh sách | `List<Pipeline> pipelines` |
| Model object lồng | `Retry retry` hoặc `List<Destination> destinations` |
| Model map lồng | `Map<String,String> headers` |
| Map key có dấu chấm | `labels.[deployment.zone]` |
| Bind kiểu thời gian | `Duration timeout` với YAML `2s` |
| Đăng ký root bean | `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` |
| Validate list bắt buộc có phần tử | `@NotEmpty` |
| Validate phần tử bên trong list | `@Valid` trên phần tử/nested object |
| Validate field bắt buộc | `@NotBlank`, `@NotNull`, `@Min` theo kiểu |
| Bind từ biến môi trường theo index | `APP_PIPELINES_0_NAME` |
| Override cả list qua profile | Khai báo lại list mong muốn ở nguồn thắng |
| Override theo tên định danh | Cân nhắc `Map<String,Pipeline>` |
| Kiểm thử binding | `@SpringBootTest` hoặc Spring context test phù hợp |

**Kết luận:** để liên kết danh sách đối tượng có cấu trúc lồng nhau trong Spring Boot, hãy bắt đầu từ **hình dạng dữ liệu**, dùng YAML sequence hoặc key `[index]` trong properties, thiết kế `List<record>`/`List<class>` khớp nhau, đăng ký root `@ConfigurationProperties` đúng cơ chế, và validate ở từng tầng quan trọng. Khi nhiều nguồn cấu hình cùng khai báo list, nhớ rằng **list thường được thay thế thay vì deep merge theo từng phần tử**. Chọn List khi thứ tự là ý nghĩa cốt lõi, Map khi phần tử được quản lý theo định danh, và để Binder đảm nhận công việc tạo cây object có kiểu thay vì tự ghép từng key bằng tay.

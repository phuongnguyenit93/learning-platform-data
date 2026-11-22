# Phân biệt baggage với tag và kiểm soát dữ liệu truyền giữa các dịch vụ

## 1. Bắt đầu từ một yêu cầu đi qua nhiều dịch vụ

Giả sử một yêu cầu đi theo đường `checkout → inventory → shipping`. Nhóm vận hành cần biết yêu cầu bắt nguồn từ kênh `web` hay `mobile`, đồng thời muốn tìm những lần giữ hàng thất bại tại `inventory`.

Hai nhu cầu này dẫn đến hai quyết định riêng:

- Dữ liệu nào cần đi cùng yêu cầu để dịch vụ phía sau đọc được?
- Dữ liệu nào cần ghi vào span để tìm kiếm và phân tích?

**Baggage** là tập cặp khóa–giá trị đi cùng ngữ cảnh thực thi; **span tag**, còn gọi là thuộc tính span (span attribute), mô tả một span. Ghi `channel=web` vào baggage không có nghĩa nó đã được ghi vào span. Việc sao chép sang thuộc tính cần mã hoặc cơ chế ánh xạ riêng. [OpenTelemetry: Baggage](https://opentelemetry.io/docs/concepts/signals/baggage/)

Trong ví dụ này, có thể chọn `channel=web` làm baggage và chỉ gắn `inventory.result=out_of_stock` vào span giữ hàng. Dịch vụ vận chuyển không cần mang theo kết quả nội bộ của từng lần truy vấn kho.

Bài dùng thuật ngữ **tag** theo ngữ cảnh truy vết. Khi nói đến nhãn của metric, bài sẽ ghi rõ **metric tag** để tránh nhầm hai loại chi phí.

## 2. Bốn nơi dữ liệu có thể xuất hiện

| Nơi chứa | Câu hỏi mà nó phục vụ | Ví dụ thiết kế trong bài |
| --- | --- | --- |
| Ngữ cảnh truy vết | Các span thuộc lần xử lý phân tán nào? | Trace ID và quan hệ cha–con |
| Baggage | Dịch vụ tiếp theo cần biết ngữ cảnh bổ sung nào? | `channel=web` |
| Span tag | Span này cần được mô tả bằng thông tin gì? | `inventory.result=out_of_stock` |
| MDC của log | Dòng log cần thêm trường nào để đối chiếu? | `channel=web` nếu được cấu hình |

Với W3C Trace Context, `traceparent` chứa thông tin liên kết truy vết; `tracestate` dành cho trạng thái riêng của hệ thống truy vết. Không tự nhét dữ liệu nghiệp vụ vào hai header này. [W3C Trace Context](https://www.w3.org/TR/trace-context/)

Một đoạn header minh họa cho **W3C Baggage** có thể là:

```http
baggage: channel=web,region=apac
```

Đây là ví dụ về định dạng trên đường truyền, không phải cam kết rằng mọi bridge và mọi cấu hình Spring đều phát đúng một header như vậy. W3C Baggage có quy tắc cú pháp, mã hóa giá trị và xử lý riêng. Không dùng phép nối chuỗi tùy ý để thay bộ truyền ngữ cảnh. [W3C Baggage](https://www.w3.org/TR/baggage/)

MDC chỉ là ngữ cảnh phục vụ log trong tiến trình. Có dữ liệu trong MDC không chứng minh rằng request ra ngoài có baggage; có baggage ở dịch vụ nhận cũng chưa chứng minh log sẽ in trường đó.

## 3. Đặt hai luồng dữ liệu cạnh nhau

```text
Luồng yêu cầu:
checkout -- ngữ cảnh truy vết + baggage --> inventory --> shipping

Luồng quan sát:
Các span checkout/inventory/shipping
    --> bộ xuất span --> hệ thống lưu truy vết
```

Trong thiết kế minh họa:

1. `checkout` xác định kênh từ nguồn đã kiểm chứng.
2. Chính sách quyết định `channel` được phép truyền đến `inventory`.
3. Bộ tích hợp HTTP chèn ngữ cảnh vào request.
4. `inventory` trích xuất ngữ cảnh và đọc baggage.
5. Nếu cần tìm kiếm theo kênh, `inventory` chủ động gắn `channel` lên span thích hợp.
6. Khi gọi một nhà cung cấp bên ngoài, chính sách đích đến có thể bỏ toàn bộ baggage.

Bước 5 không được ngầm suy ra từ bước 4. Tương tự, gắn một tag lên span của `checkout` không tạo hợp đồng truyền dữ liệu nghiệp vụ cho `inventory`.

Đừng dùng giao diện hệ thống truy vết làm bằng chứng duy nhất về header: dữ liệu hiển thị ở đó đã đi qua lấy mẫu, bộ xuất, nơi lưu và quy tắc hiển thị.

## 4. Cấu hình Spring Boot 3.3: tách truyền, log và tag

Spring Boot Actuator cung cấp tự cấu hình Micrometer Tracing. Client HTTP nên được tạo từ `RestClient.Builder`, `RestTemplateBuilder` hoặc `WebClient.Builder` do Boot cung cấp để giữ cơ chế truyền ngữ cảnh tự động. Với B3, cần khai báo các trường baggage truyền xa; W3C có cơ chế baggage của nó. [Spring Boot 3.3: Tracing](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html)

Ví dụ dưới đây **cố ý chọn Brave và B3_MULTI**, giúp quan sát rõ các header baggage riêng. Đây là cấu hình tích hợp vào một ứng dụng Boot 3.3 hiện có, không phải một dự án chạy độc lập.

### 4.1. Phụ thuộc

Đoạn Groovy sau giả định dự án đã áp dụng plugin Spring Boot và quản lý phiên bản theo BOM Boot 3.3:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-brave'
    implementation 'io.zipkin.reporter2:zipkin-reporter-brave'
}
```

Chọn một bridge phù hợp cho bài thử. Cấu hình nơi nhận span phải tương ứng với bộ xuất đã chọn; ví dụ này dùng Zipkin.

### 4.2. Cấu hình dùng ở cả hai dịch vụ thử nghiệm

```yaml
management:
  tracing:
    propagation:
      consume: [B3_MULTI]
      produce: [B3_MULTI]
    sampling:
      probability: 1.0
    baggage:
      remote-fields: [channel, region]
      correlation:
        fields: [channel]
      tag-fields: []
  zipkin:
    tracing:
      endpoint: http://localhost:9411/api/v2/spans
```

`probability: 1.0` phục vụ quan sát trong môi trường học. Nó không phải chính sách lấy mẫu bắt buộc cho vận hành thực tế.

Ba nhóm thuộc tính cần phân biệt:

| Thuộc tính | Vai trò |
| --- | --- |
| `management.tracing.baggage.remote-fields` | Khai báo các trường truyền qua mạng theo cấu hình tương ứng |
| `management.tracing.baggage.correlation.fields` | Chọn các trường đưa vào ngữ cảnh log như MDC |
| `management.tracing.baggage.tag-fields` | Chọn các trường được cơ chế baggage tự ánh xạ thành tag |

Danh mục Boot 3.3 cũng có `local-fields`, nhưng không hỗ trợ trường cục bộ này với OpenTelemetry. Không sao chép cấu hình giữa hai bridge rồi giả định hành vi hoàn toàn giống nhau. [Spring Boot 3.3: Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html)

Ví dụ giữ `tag-fields: []` để việc gắn tag được thể hiện bằng mã. Nếu muốn thử ánh xạ tự động, có thể đổi thành `tag-fields: [channel]` rồi kiểm chứng trên span thực tế của bridge/phiên bản đang dùng; đó là một lựa chọn khác với việc khai báo truyền qua mạng.

Cấu hình Brave của Boot 3.3 đăng ký các `remote-fields` bằng `BaggagePropagationConfig.SingleBaggageField.remote(...)`; các trường correlation được cấu hình riêng cho MDC. [Mã nguồn Brave propagation của Boot 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/tracing/BravePropagationConfigurations.java)

**Trong ví dụ B3 này**, hãy tìm header `channel: web` và `region: apac`. Không chỉ tìm header tên `baggage` rồi kết luận truyền thất bại.

### 4.3. Mã gọi dịch vụ trong phạm vi baggage

Lưu lớp sau tại `example/baggage/InventoryCaller.java` trong ứng dụng Boot. Lớp cần được component scan phát hiện. Dịch vụ ở cổng 8081 phải có endpoint `GET /stock`; lớp này không tự tạo endpoint đó.

Điều kiện đầu vào của ví dụ: request đã qua chính sách biên, ngữ cảnh hiện tại không chứa baggage ngoài chính sách, và đích cố định dưới đây là dịch vụ nội bộ được phép nhận hai trường này.

```java
package example.baggage;

import java.util.Set;

import io.micrometer.tracing.BaggageInScope;
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class InventoryCaller {
    private static final Set<String> CHANNELS =
            Set.of("web", "mobile", "batch");
    private static final Set<String> REGIONS =
            Set.of("apac", "emea", "amer");

    private final Tracer tracer;
    private final RestClient client;

    public InventoryCaller(Tracer tracer, RestClient.Builder builder) {
        this.tracer = tracer;
        this.client = builder
                .baseUrl("http://localhost:8081")
                .build();
    }

    public String stock(String channel, String region) {
        if (channel == null || region == null
                || !CHANNELS.contains(channel) || !REGIONS.contains(region)) {
            throw new IllegalArgumentException("Unsupported context");
        }

        Span span = tracer.nextSpan().name("inventory.lookup").start();
        try (Tracer.SpanInScope spanScope = tracer.withSpan(span);
             BaggageInScope channelScope =
                     tracer.createBaggageInScope("channel", channel);
             BaggageInScope regionScope =
                     tracer.createBaggageInScope("region", region)) {
            span.tag("channel", channel);
            return client.get()
                    .uri("/stock")
                    .retrieve()
                    .body(String.class);
        } catch (RuntimeException ex) {
            span.error(ex);
            throw ex;
        } finally {
            span.end();
        }
    }
}
```

Khi gọi `stock("web", "apac")`:

- Hai `BaggageInScope` mở phạm vi cho dữ liệu cần truyền.
- `span.tag("channel", channel)` ghi tag lên span `inventory.lookup` một cách tường minh.
- Span HTTP client do bộ tích hợp tạo là span khác; không suy ra nó có cùng bộ tag.
- `try-with-resources` đóng các phạm vi dù việc gọi HTTP thất bại; `finally` kết thúc span do lớp này tạo.

API scope và baggage được mô tả trong [Micrometer Tracing: sử dụng API trực tiếp](https://docs.micrometer.io/tracing/reference/api.html).

Đoạn này chạy đồng bộ trong phạm vi gọi. Nếu chuyển công việc sang executor hoặc luồng phản ứng, cần cơ chế truyền ngữ cảnh tương ứng; việc còn giữ tham chiếu `Tracer` không tự bảo đảm ngữ cảnh đi theo tác vụ.

Ở phía nhận, đoạn sau minh họa phần thân của một phương thức có `Tracer tracer` được tiêm sẵn. Nó **không phải chương trình Java độc lập**:

```java
var baggage = tracer.getBaggage("channel");
String channel = baggage == null ? null : baggage.get();

Span current = tracer.currentSpan();
if (current != null
        && channel != null
        && Set.of("web", "mobile", "batch").contains(channel)) {
    current.tag("channel", channel);
}
```

Đoạn phía nhận cần import `java.util.Set` và `io.micrometer.tracing.Span`. Kiểm tra tập giá trị chỉ xác nhận giá trị phù hợp chính sách; nó không xác thực ai đã gửi giá trị đó.

Việc không có chương trình khởi động hay endpoint nhận ở đây là ranh giới của ví dụ tích hợp. Không có stdout cố định cho nó: trace ID, span ID, thời gian và kết quả HTTP phụ thuộc lần chạy.

## 5. Chính sách dữ liệu: quyết định trước khi bật truyền tự động

Hãy thiết kế một danh mục nhỏ cho từng trường:

| Trường đề xuất | Quyết định trong tình huống minh họa | Lý do |
| --- | --- | --- |
| `channel` | Cho phép các giá trị `web/mobile/batch` | Cần phân tích theo nguồn yêu cầu |
| `region` | Chỉ cho dịch vụ nội bộ cần nó | Tránh phát tán thông tin không cần thiết |
| `inventory.result` | Tag tại span giữ hàng | Mô tả thao tác cục bộ |
| `customer.email` | Loại khỏi baggage | Dữ liệu cá nhân không cần cho chuỗi gọi này |
| `Authorization`, mật khẩu, khóa API | Loại khỏi baggage và tag | Không phải dữ liệu chẩn đoán để nhân bản |
| Toàn bộ JSON đơn hàng | Đưa qua hợp đồng API nếu thật sự cần | Baggage không phù hợp để thay nội dung yêu cầu |

Đây là chính sách của ví dụ, không phải danh sách khóa tiêu chuẩn của Spring.

Quy trình đề xuất cho một ranh giới tin cậy:

1. Xác định nguồn gửi và đích nhận; đích đến phải lấy từ cấu hình tin cậy.
2. Chọn danh sách khóa được phép.
3. Kiểm tra tập giá trị, độ dài, số mục và ngân sách byte.
4. Loại trường không hợp lệ trước khi đưa vào ngữ cảnh, tag hoặc log.
5. Chỉ tạo baggage từ dữ liệu đã được chấp nhận.
6. Khi sang miền không tin cậy, áp dụng chính sách bỏ/giảm baggage ở bước xuất request.

Baggage không có kiểm tra tính toàn vẹn mặc định. Một giá trị như `role=admin` hoặc `tenant=another-company` do bên gọi tự gửi không thể thay bằng chứng xác thực và phân quyền. [OpenTelemetry: lưu ý về bảo mật baggage](https://opentelemetry.io/docs/concepts/signals/baggage/#baggage-security-considerations)

Ngay cả `channel=web` cũng chỉ là dữ liệu mô tả nếu nó đến từ bên ngoài. Nếu kênh ảnh hưởng đến hạn mức hoặc tính phí, phải xác định từ nguồn tin cậy hay hợp đồng đã xác thực riêng.

### 5.1. Bộ lọc phải đặt đúng chỗ

`remote-fields` giúp cấu hình truyền; không được xem nó là một tường lửa dữ liệu hoàn chỉnh. Với W3C, có thể có baggage chuẩn được bộ truyền xử lý ngoài những header riêng bạn đang quan sát.

Không áp dụng cách sau rồi cho rằng đã an toàn:

```text
nhận request chưa lọc
→ thư viện đã trích xuất toàn bộ baggage
→ chỉ đọc và kiểm tra khóa channel
→ gọi dịch vụ ngoài bằng client có truyền ngữ cảnh tự động
```

Kiểm tra một khóa không loại những khóa còn lại khỏi ngữ cảnh hiện hành.

Vì vậy, kiểm soát đầu vào cần diễn ra trước khi dữ liệu không tin cậy được chấp nhận vào ngữ cảnh. Kiểm soát đầu ra cần áp dụng tại bước tạo ngữ cảnh xuất hoặc lớp chèn header cuối cùng. Với gateway, phải kiểm tra chính sách nằm ở phía nào của cơ chế tự chèn header.

Nếu chọn bỏ baggage ở biên ra, hãy xét cả header W3C `baggage` và các header riêng đã cấu hình. Bỏ chúng trước một bước tự chèn phía sau có thể khiến chúng xuất hiện trở lại.

Dùng HTTPS/TLS cho đường truyền phù hợp, nhưng vẫn giảm dữ liệu trước khi gửi: bên nhận được phép kết nối vẫn đọc được baggage. Bảo vệ đường truyền không biến baggage thành nơi lưu bí mật.

### 5.2. Không đợi đến Collector mới xử lý

Ẩn dữ liệu ở giao diện cuối không thu hồi được dữ liệu đã truyền qua dịch vụ, proxy hoặc log. Nên giảm dữ liệu ngay tại nguồn; xử lý xóa/biên tập tại pipeline telemetry là lớp bổ sung. Băm một định danh cũng không tự bảo đảm dữ liệu đã ẩn danh. [OpenTelemetry: xử lý dữ liệu nhạy cảm](https://opentelemetry.io/docs/security/handling-sensitive-data/)

Để biết một trường có thực sự cần truyền, hãy yêu cầu chủ sở hữu trả lời: ai dùng nó, dùng tại bước nào, có thể dùng giá trị ít chi tiết hơn hay không, và khi nào ngừng truyền.

## 6. Java 17+: kiểm chứng một chính sách nhỏ, chạy độc lập

Chương trình sau chỉ nhận **Map đã được phân tích cú pháp** và chọn dữ liệu hợp lệ. Nó không phân tích header W3C, không mã hóa header, không sửa ngữ cảnh Micrometer và không tự ngăn một HTTP client truyền dữ liệu khác.

Chính sách minh họa:

- Chỉ đích nội bộ đã được xác định tin cậy mới được nhận dữ liệu.
- Chỉ hai khóa `channel`, `region` được phép.
- Giá trị phải nằm trong tập hữu hạn đã định nghĩa.
- Mỗi giá trị tối đa 16 ký tự ASCII; tổng biểu diễn cặp khóa–giá trị tối đa 64 byte.
- Khóa hoặc giá trị không hợp lệ bị bỏ; không đưa giá trị bị loại vào thông báo log.

Lưu nguyên mã sau vào `BaggagePolicyDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;

public class BaggagePolicyDemo {
    private static final Map<String, Set<String>> ALLOWED = Map.of(
            "channel", Set.of("web", "mobile", "batch"),
            "region", Set.of("apac", "emea", "amer"));
    private static final int MAX_VALUE_LENGTH = 16;
    private static final int MAX_PAIR_BYTES = 64;

    static Map<String, String> select(
            Map<String, String> parsed, boolean trustedDestination) {
        if (!trustedDestination) {
            return Map.of();
        }

        TreeMap<String, String> selected = new TreeMap<>();
        int usedBytes = 0;

        for (String key : new TreeMap<>(ALLOWED).keySet()) {
            String value = parsed.get(key);
            if (value == null
                    || value.length() > MAX_VALUE_LENGTH
                    || !value.chars().allMatch(c -> c >= 0x21 && c <= 0x7e)
                    || !ALLOWED.get(key).contains(value)) {
                continue;
            }

            int pairBytes = (key + "=" + value)
                    .getBytes(StandardCharsets.US_ASCII).length;
            int separatorBytes = selected.isEmpty() ? 0 : 1;
            if (usedBytes + separatorBytes + pairBytes > MAX_PAIR_BYTES) {
                continue;
            }

            selected.put(key, value);
            usedBytes += separatorBytes + pairBytes;
        }

        return Collections.unmodifiableMap(selected);
    }

    public static void main(String[] args) {
        Map<String, String> incoming = Map.of(
                "channel", "web",
                "region", "apac",
                "customer.email", "alice@example.test",
                "role", "admin");

        System.out.println("internal=" + select(incoming, true));
        System.out.println("external=" + select(incoming, false));
        System.out.println("invalid=" + select(Map.of(
                "channel", "web\r\nInjected: yes",
                "region", "unknown"), true));
        System.out.println("missing=" + select(Map.of(), true));
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp, với JDK 17 trở lên:

```shell
javac BaggagePolicyDemo.java
java BaggagePolicyDemo
```

Stdout chính xác:

```text
internal={channel=web, region=apac}
external={}
invalid={}
missing={}
```

`TreeMap` làm thứ tự in ổn định. Các giá trị trong tập cho phép ngắn và hữu hạn nên hai trường hợp lệ hiện tại đều nằm dưới ngân sách. Nhánh kiểm tra byte giúp chính sách nêu rõ giới hạn nếu sau này mở rộng tập dữ liệu; không có trường hợp hợp lệ hiện tại nào chứng minh nhánh vượt 64 byte đã được kích hoạt.

`trustedDestination` là kết quả của quyết định tin cậy từ cấu hình ứng dụng, không được lấy trực tiếp từ tham số người dùng. Khi tích hợp, còn phải kiểm tra scheme, host, cổng và chính sách chuyển hướng của HTTP client để đích thực tế phù hợp quyết định đó.

Các con số 16 và 64 là **giới hạn do ví dụ tự chọn**, không phải giới hạn mặc định của Spring, W3C, proxy hay máy chủ. Chương trình cũng chưa giới hạn kích thước Map đầu vào: lớp nhận request phải chặn header quá lớn trước khi phân tích cú pháp.

Khi triển khai thực tế, đo kích thước header sau mã hóa và tính cả các header khác. W3C cho phép hệ thống giới hạn/xử lý bớt baggage; không coi mọi trung gian đều bảo toàn vô hạn các mục. [W3C Baggage: giới hạn](https://www.w3.org/TR/baggage/#limits)

## 7. Baggage, số lượng giá trị và chi phí quan sát

Số lượng giá trị phân biệt được gọi là **cardinality**. `channel` với ba giá trị là một tập nhỏ; mã đơn hàng sinh liên tục là tập lớn. Micrometer phân biệt khóa low cardinality và high cardinality trong Observation. [Micrometer: Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)

Trong thiết kế bài này:

- Cho `channel` làm metric tag có thể phù hợp vì số giá trị được chặn.
- Không đưa mã từng đơn hàng làm metric tag.
- Nếu thật sự cần mã đơn để chẩn đoán một span, phải xem xét quyền riêng tư, độ dài, lưu giữ và chi phí nơi lưu trước khi gắn.
- Không biến toàn bộ baggage thành tag của mọi span hoặc mọi metric.

Ví dụ tính kích thước để hình dung: nếu mỗi lần gọi nội bộ mang thêm 100 byte baggage và một yêu cầu tạo 20 lần gọi, tổng phần dữ liệu baggage ở các lượt gửi xấp xỉ 2.000 byte. Đây chỉ là phép tính trên dữ liệu thêm vào, chưa gồm header khác, mã hóa giao thức, lần thử lại hay lời gọi phát sinh.

Lấy mẫu span và truyền ngữ cảnh là hai quyết định khác nhau. Không dùng kết luận “không thấy span trong hệ thống lưu” để cho rằng dữ liệu đã ngừng đi qua mạng; hãy đo trực tiếp tại ranh giới truyền.

## 8. Kiểm chứng hành vi bằng các quan sát riêng

Với hai dịch vụ thử nghiệm cùng cấu hình B3 ở trên, hãy tách các bằng chứng:

| Bài thử | Điều cần quan sát | Bằng chứng đạt |
| --- | --- | --- |
| Chỉ gắn tag `channel`, không tạo baggage và đầu vào không mang baggage | Request đi sang dịch vụ nhận | Không xuất hiện dữ liệu `channel` do thao tác gắn tag tạo ra |
| Tạo baggage nhưng không gọi `span.tag`, giữ `tag-fields: []` | Header và span tự tạo | Có dữ liệu truyền; không suy ra có tag `channel` trên span |
| Tạo baggage rồi gọi `span.tag` như ví dụ | Header và span `inventory.lookup` | Quan sát được hai kết quả riêng |
| Thêm correlation field và mẫu log có `%X{channel}` | Log trong phạm vi baggage | Có giá trị MDC tại đúng phạm vi |
| Gọi nhà cung cấp ngoài qua lớp chính sách | Request cuối cùng thực sự được gửi | Không còn các header baggage bị cấm |
| Yêu cầu A có baggage, yêu cầu B không có | Hai lần xử lý độc lập | Không rò giá trị từ A sang B |
| Không xuất span của một lần xử lý | Request trên đường truyền | Xác định riêng baggage có được truyền hay không |

Không ghi toàn bộ header thực tế vào log dùng chung để làm bằng chứng. Trong môi trường thử, dùng dữ liệu giả và công cụ nhận request được giới hạn truy cập; kiểm tra cả đường gọi thành công, lỗi, thử lại và chuyển hướng nếu client hỗ trợ.

Với ví dụ B3, `channel` có thể xuất hiện dưới dạng header riêng. Với một cấu hình W3C khác, phải kiểm tra cả `baggage` và các header bổ sung đã khai báo. Nếu không thấy dữ liệu, lần lượt kiểm tra bridge, cấu hình ở hai phía, phạm vi còn mở, client được tạo từ builder của Boot và gateway có bỏ header hay không.

Chạy Java policy demo chỉ chứng minh các kết quả chọn Map ở mục 6. Nó không thay bài thử HTTP, MDC, span hay ranh giới tin cậy trong bảng này.

## 9. Những lỗi dễ mắc

| Cách làm | Hệ quả | Cách điều chỉnh |
| --- | --- | --- |
| Gắn tag rồi chờ dịch vụ sau đọc baggage | Lẫn dữ liệu lưu trên span với dữ liệu truyền | Tạo và kiểm chứng baggage riêng |
| Có baggage rồi mặc định tìm được trên mọi span | Bỏ qua bước ánh xạ | Chọn span và tag cần ghi |
| Cho rằng correlation field bật truyền mạng | Kiểm chứng sai luồng dữ liệu | Kiểm tra MDC và header độc lập |
| Dùng `remote-fields` làm chính sách bảo mật duy nhất | Có thể bỏ sót dữ liệu qua đường truyền khác | Áp dụng chính sách trước trích xuất và khi xuất request |
| Dùng baggage quyết định quyền truy cập | Tin dữ liệu do phía gọi tự khai | Dùng danh tính và quyền đã xác thực |
| Quên đóng scope | Dữ liệu có thể sống quá phạm vi dự kiến | Dùng `try-with-resources` và kiểm tra yêu cầu kế tiếp |
| Chuyển tác vụ sang luồng khác mà không truyền ngữ cảnh | Mất dữ liệu hoặc gắn nhầm phạm vi | Dùng cơ chế context propagation tương ứng |
| Chỉ xóa dữ liệu tại hệ thống lưu truy vết | Dữ liệu có thể đã đi qua dịch vụ ngoài | Giảm dữ liệu từ nguồn và tại biên ra |
| Đưa JSON lớn vào baggage | Phình header, tăng chi phí và rủi ro bị từ chối | Dùng hợp đồng API cho dữ liệu nghiệp vụ |

## 10. Thực hành và tự kiểm tra

1. Với chuỗi `checkout → inventory → payment-provider`, lập chính sách cho `channel`, `region`, email và access token. Ghi rõ trường nào chỉ gắn tag cục bộ, trường nào đi nội bộ, trường nào không được thu thập.
2. Đổi `channel` trong policy demo thành `desktop`. Kết quả cho khóa đó phải bị loại vì chưa nằm trong tập cho phép; không tự bổ sung giá trị để làm bài thử “xanh”.
3. Tạo một lần chạy chỉ có tag, một lần chỉ có baggage và một lần có cả hai. Thu bằng chứng header và span riêng.
4. Thử yêu cầu liên tiếp có/không có baggage để phát hiện lỗi phạm vi.
5. Kiểm tra đích ngoài sau toàn bộ chuỗi interceptor và bước truyền ngữ cảnh; xác nhận dữ liệu đã bị loại không được chèn lại.

Câu hỏi tự đánh giá:

- Muốn dịch vụ sau biết kênh yêu cầu, chỉ gắn tag có đủ không? **Không; cần cơ chế truyền ngữ cảnh bổ sung phù hợp.**
- Muốn tìm span theo kênh, chỉ tạo baggage có đủ không? **Không bảo đảm; cần ánh xạ sang tag trên span thích hợp.**
- Giá trị baggage hợp lệ có chứng minh người gửi có quyền không? **Không.**
- Không thấy trace được lưu có chứng minh không truyền baggage không? **Không; cần kiểm tra riêng đường truyền.**
- Một trường được phép truyền nội bộ có mặc nhiên được gửi cho bên thứ ba không? **Không; đó là quyết định theo đích đến.**

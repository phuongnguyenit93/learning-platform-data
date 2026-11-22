# Khám phá danh sách chỉ số bằng endpoint metrics

## 1. Bắt đầu bằng câu hỏi “ứng dụng đang có những chỉ số nào?”

Khi muốn kiểm tra bộ nhớ JVM, lưu lượng HTTP hay một bộ đếm nghiệp vụ, không nên đoán tên chỉ số từ dashboard hoặc từ một ứng dụng khác. Spring Boot Actuator cung cấp endpoint `metrics` để khám phá những tên chỉ số đang được biết đến trong các registry mà endpoint sử dụng.

Luồng làm việc cơ bản gồm ba bước: **lấy danh sách tên → chọn một tên có thật → đọc chi tiết và thu hẹp theo tags khi cần**. Sau đó có thể tạo một thao tác thử để quan sát việc đăng ký hoặc thay đổi giá trị.

```text
GET /actuator/metrics
        |
        v
names: các tên chỉ số hiện có
        |
        v
GET /actuator/metrics/{tên-chỉ-số}
        |
        v
mô tả, đơn vị, phép đo, các tags có thể lọc
```

Endpoint này phục vụ chẩn đoán ở ứng dụng. Có tên trong danh sách chưa chứng minh chỉ số đã được xuất thành công ra một hệ thống giám sát, có dữ liệu lịch sử, hay toàn hệ thống đang hoạt động tốt.

Bài dùng Spring Boot **3.3.0**, Micrometer thuộc dòng **1.13** và Java 17+ để kiểm chứng ví dụ. Cấu hình và dữ liệu ở ứng dụng thực cần được xác minh trực tiếp; không dùng một danh sách tên cố định làm tiêu chuẩn cho mọi dự án.

## 2. Chuẩn bị để endpoint truy cập được qua HTTP

### 2.1. Phân biệt phụ thuộc, bật endpoint và công khai qua HTTP

Với ứng dụng Spring MVC, các phụ thuộc thường dùng cho thí nghiệm là `spring-boot-starter-web` và `spring-boot-starter-actuator`. Actuator tích hợp hạ tầng metrics của Boot; endpoint `metrics` còn cần registry có trong application context.

Ba lớp điều kiện cần phân biệt:

| Lớp điều kiện | Kiểm tra điều gì? |
| --- | --- |
| Hạ tầng metrics | Micrometer và `MeterRegistry` thích hợp có được cấu hình không? |
| Endpoint được bật | `management.endpoint.metrics.enabled` có cho phép endpoint tồn tại theo cấu hình hiện hành không? |
| Endpoint được đưa ra HTTP | `management.endpoints.web.exposure.include`/`exclude` có cho phép truy cập qua web không? |

Trong Boot 3.3, mặc định chỉ `health` được đưa ra HTTP. Vì vậy thấy `/actuator/health` hoạt động không có nghĩa `/actuator/metrics` đã truy cập được. `exclude` cũng được ưu tiên hơn `include` khi chúng xung đột. [Quy tắc bật và công khai endpoint của Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

Cấu hình minh họa:

```yaml
management:
  endpoint:
    metrics:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,metrics
```

Không cần công khai toàn bộ Actuator chỉ để đọc metrics. Nếu đã có cấu hình bảo mật, quyền đọc vẫn do cấu hình đó quyết định; đưa endpoint ra HTTP không đồng nghĩa cho phép mọi người truy cập.

Về triển khai, cấu hình tự động của `MetricsEndpoint` kiểm tra điều kiện endpoint khả dụng và bean `MeterRegistry`. Thêm một chuỗi vào `include` không tự tạo các metric nghiệp vụ mà ứng dụng chưa đăng ký. [MetricsEndpointAutoConfiguration 3.3.0](https://github.com/spring-projects/spring-boot/blob/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/MetricsEndpointAutoConfiguration.java).

### 2.2. Xác định đúng URL trước khi phân tích dữ liệu

Các lệnh trong bài dùng URL mặc định `http://127.0.0.1:8080/actuator/metrics`. Nếu ứng dụng đổi cổng quản trị, base path, context path hoặc đi qua reverse proxy, cần dùng URL thực tế tương ứng.

Ví dụ, khi chỉ đổi `management.endpoints.web.base-path` thành `/manage` và vẫn dùng cùng cổng/context mặc định, đường dẫn trở thành `/manage/metrics`. Đừng giải thích mọi 404 là “chưa có chỉ số” trước khi chắc rằng đã gọi đúng endpoint.

## 3. Lấy danh sách tên bằng GET /actuator/metrics

```bash
curl -i http://127.0.0.1:8080/actuator/metrics
```

Khi endpoint có thể truy cập, kỳ vọng HTTP 200 và một JSON có trường `names`. Ví dụ sau chỉ minh họa cấu trúc với một vài tên thường gặp, không phải danh sách bắt buộc hoặc toàn bộ phản hồi của mọi ứng dụng:

```json
{
  "names": [
    "jvm.memory.used",
    "jvm.threads.live",
    "process.uptime"
  ]
}
```

`names` là mảng các tên đang được endpoint biết đến. Nó không chứa toàn bộ giá trị đo, không mô tả tất cả bộ tags và không phải danh sách HTTP API của ứng dụng. Để xem những thông tin đó cần chọn đúng tên rồi đọc chi tiết. [Hợp đồng HTTP của endpoint metrics](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

### 3.1. Số tên khác số meter

Cùng tên `demo.work.completed` có thể có meter cho `channel=web` và meter cho `channel=mobile`. Danh sách vẫn chỉ có một chuỗi `demo.work.completed`; không có một phần tử riêng cho từng bộ tags.

Trong Boot 3.3.0, triển khai liệt kê thu thập tên vào một tập hợp và đi qua các registry con nếu registry là composite. Vì vậy phép đếm độ dài `names` là đếm tên phân biệt ở tầng endpoint này, không phải số ID meter, số tổ hợp tags, dung lượng heap hay số chuỗi thời gian ở hệ thống giám sát. [Mã nguồn listNames/collectNames 3.3.0](https://github.com/spring-projects/spring-boot/blob/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/metrics/MetricsEndpoint.java).

Triển khai phiên bản này dùng cấu trúc sắp xếp tên, nhưng công cụ sử dụng dữ liệu nên tìm theo chuỗi tên thay vì vị trí phần tử. Không coi phần tử thứ ba là “metric bộ nhớ” ở mọi lần chạy.

### 3.2. Danh sách không phải một danh mục tĩnh

Các meter do binder tạo có thể xuất hiện ngay khi ứng dụng khởi động. Meter đăng ký trong một nhánh nghiệp vụ chỉ xuất hiện khi mã đăng ký đó đã chạy. Một metric chưa có tên không luôn là lỗi; cần biết thời điểm và điều kiện nó được tạo.

Ngược lại, một counter được đăng ký trước nhưng chưa tăng có thể đã có tên và có count bằng 0. **Không tồn tại meter** khác với **meter tồn tại nhưng giá trị hiện tại bằng 0**.

Cấu hình, thư viện trên classpath, loại ứng dụng, runtime và thao tác đã thực hiện có thể làm danh sách khác nhau. Một ứng dụng không dùng JDBC không bắt buộc có metric pool kết nối, cũng như một meter đo HTTP chưa chắc đã có mẫu trước khi luồng quan sát thích hợp hoàn tất.

Bản thân việc gọi các endpoint HTTP cũng có thể tạo hoặc cập nhật metric HTTP sau khi yêu cầu kết thúc. Vì vậy không yêu cầu tổng số tên toàn ứng dụng phải bất biến giữa hai lần khám phá.

## 4. Tìm nhóm tên cần quan tâm

Có thể bắt đầu bằng câu hỏi vận hành rồi tìm các tiền tố/tên phù hợp trong kết quả thực tế:

| Câu hỏi | Những nhóm tên có thể gặp | Cần lưu ý |
| --- | --- | --- |
| JVM đang dùng bộ nhớ và luồng ra sao? | `jvm.memory.*`, `jvm.threads.*` | Tags và đơn vị có thể phân biệt vùng nhớ/loại trạng thái |
| Tiến trình đã chạy bao lâu? | `process.uptime` | Một chỉ số của tiến trình không tự là số liệu toàn cụm |
| HTTP có đang được quan sát? | `http.server.requests` | Có thể cần tạo một yêu cầu và chờ nó hoàn tất |
| Nghiệp vụ thử nghiệm đã ghi nhận chưa? | `demo.work.completed` trong ví dụ | Tên chỉ xuất hiện sau lần đăng ký đầu tiên theo mã ví dụ |

Đây là gợi ý tìm kiếm, không phải cách xác định loại meter chỉ từ tiền tố. Hãy lấy một tên có thật từ `names`, đọc mô tả và đơn vị rồi mới diễn giải.

### 4.1. Lọc kết quả ở phía công cụ đọc

Nếu có `jq`, có thể in một tên trên mỗi dòng hoặc chọn nhóm JVM:

```bash
curl -s http://127.0.0.1:8080/actuator/metrics | jq -r '.names[]'
curl -s http://127.0.0.1:8080/actuator/metrics | jq -r '.names[] | select(startswith("jvm."))'
```

Với PowerShell, không cần cài jq:

```powershell
$metricNames = (Invoke-RestMethod -Uri 'http://127.0.0.1:8080/actuator/metrics').names
$metricNames | Where-Object { $_ -like 'jvm.*' }
```

Các phép lọc này chạy ở công cụ đọc JSON. Không tự thêm tham số như `prefix=jvm` hoặc `page=1` rồi giả định endpoint đã lọc/phân trang tên; API liệt kê không công bố các tham số đó.

Trên PowerShell có alias `curl`, dùng `curl.exe` nếu muốn chạy đúng cú pháp curl trong bài. Khi có lỗi, dùng `-i` để thấy trạng thái HTTP; chỉ nhìn một phần thân rỗng có thể che mất thông tin quan trọng.

## 5. Mở chi tiết một chỉ số đã có tên

Ví dụ, nếu danh sách thực sự có `jvm.memory.used`:

```bash
curl -i http://127.0.0.1:8080/actuator/metrics/jvm.memory.used
```

Chi tiết có thể chứa các trường:

| Trường | Cách sử dụng |
| --- | --- |
| `name` | Xác nhận đúng tên đã chọn |
| `description` | Hiểu ý nghĩa khi meter có mô tả |
| `baseUnit` | Biết đơn vị nếu meter cung cấp |
| `measurements` | Đọc các cặp `statistic`/`value` |
| `availableTags` | Xem các chiều/giá trị còn có thể dùng để thu hẹp |

Không buộc mọi meter có cùng bộ trường hoặc cùng statistic. Counter thường có COUNT; gauge thường có VALUE; timer có thể có COUNT, TOTAL_TIME, MAX. Mục tiêu của bước khám phá là tìm đúng công cụ và phạm vi, không suy tốc độ hay độ trễ từ tên đơn lẻ.

### 5.1. Dùng tên Micrometer, không dùng tên đã xuất theo quy ước khác

Tên trên endpoint cần khớp tên được dùng trong registry/mã nguồn. Nếu hệ thống giám sát đổi dấu chấm thành dấu gạch dưới hoặc thêm hậu tố cho thống kê, không sao chép nguyên tên đã xuất đó vào URL rồi kết luận metric bị mất.

Ví dụ, khi danh sách có `jvm.memory.used`, hãy dùng `/actuator/metrics/jvm.memory.used`. Trước hết đọc danh sách thực tế thay vì đoán một biến thể như `jvm_memory_used`. [Quy tắc tên tại metrics endpoint của Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.endpoint).

### 5.2. Thu hẹp theo tags sau khi đọc availableTags

Trong ví dụ nghiệp vụ bên dưới, chi tiết cho biết có tag `channel` với hai giá trị `web` và `mobile`. Có thể chọn riêng kênh web:

```bash
curl -s -G http://127.0.0.1:8080/actuator/metrics/demo.work.completed --data-urlencode "tag=channel:web"
```

Tham số dùng dạng `tag=khóa:giá-trị`. Với nhiều chiều, có thể lặp tham số `tag` để áp dụng đồng thời. Dùng `--data-urlencode` tránh phải tự xử lý dấu cách hoặc ký tự đặc biệt trong giá trị.

Không lọc tags có thể trả phép đo gộp từ nhiều meter phù hợp cùng tên. Một COUNT tổng bằng 3 không chứng minh chỉ có một counter trong registry. Khi đã lọc một chiều, nó có thể không còn xuất hiện trong `availableTags` của phản hồi vì endpoint chỉ liệt kê các chiều còn có thể thu hẹp.

Nếu tên có thật nhưng không có meter nào khớp toàn bộ tags đã chọn, thao tác đọc chi tiết có thể trả 404. Nếu tham số tag thiếu dấu phân cách như `tag=channel`, yêu cầu không hợp lệ có thể trả 400. Đây là lỗi ở bước chọn dữ liệu, khác với việc endpoint không được đưa ra HTTP.

## 6. Thí nghiệm hoàn chỉnh: một tên xuất hiện sau thao tác thử

Thí nghiệm tạo một ứng dụng Boot Spring MVC nhỏ. Endpoint `/work` ghi một counter chỉ khi được gọi; counter không được đăng ký sẵn trong hàm tạo. Nhờ đó có thể quan sát rõ trạng thái trước và sau.

Ứng dụng chỉ lắng nghe `127.0.0.1` và chỉ đưa `health,metrics` ra HTTP để dùng trên máy cá nhân. Dự án mẫu không thêm Spring Security. Nếu áp dụng vào ứng dụng đã có bảo mật, dùng quyền đọc quản trị phù hợp của ứng dụng đó.

Tạo dự án có Gradle wrapper tương thích Boot 3.3 và JDK 17 khả dụng. Có thể chạy các API này trên JDK 21 theo cấu hình dự án tương ứng.

```text
metrics-discovery-demo/
  build.gradle
  settings.gradle
  gradlew / gradlew.bat và gradle/wrapper/
  src/main/java/example/discovery/MetricsDiscoveryApplication.java
  src/main/resources/application.yml
```

`settings.gradle`:

```groovy
rootProject.name = 'metrics-discovery-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Các phiên bản trong ví dụ là mốc tái hiện API đã kiểm chứng, không phải chỉ dẫn chọn bản vá triển khai. Với dự án Boot hiện có, nên dùng quản lý phụ thuộc của Boot để giữ các phiên bản Micrometer phù hợp.

`src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  endpoint:
    metrics:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,metrics
  metrics:
    use-global-registry: false
```

`use-global-registry: false` tách thí nghiệm khỏi việc nối registry vào trạng thái tĩnh dùng chung của Micrometer; nó không tắt `MeterRegistry` được Spring tiêm và cũng không tắt endpoint metrics.

`src/main/java/example/discovery/MetricsDiscoveryApplication.java`:

```java
package example.discovery;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@RestController
public class MetricsDiscoveryApplication {
    private final MeterRegistry registry;

    public MetricsDiscoveryApplication(MeterRegistry registry) {
        this.registry = registry;
    }

    public static void main(String[] args) {
        SpringApplication.run(MetricsDiscoveryApplication.class, args);
    }

    @GetMapping("/work")
    public String work(
            @RequestParam(name = "channel", defaultValue = "web") String channel) {
        if (!"web".equals(channel) && !"mobile".equals(channel)) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "channel must be web or mobile");
        }

        Counter.builder("demo.work.completed")
            .description("Completed demo work")
            .baseUnit("operations")
            .tag("channel", channel)
            .register(registry)
            .increment();

        return "recorded:" + channel;
    }
}
```

Chỉ có hai nhãn kênh hợp lệ là `web`, `mobile`. Mã không lấy một chuỗi tự do từ người dùng làm tag, giúp tập phân loại của thí nghiệm ổn định. Lời gọi `/work` chỉ mô phỏng điểm hoàn tất công việc và trả thông báo đã ghi, không chạy một quy trình nghiệp vụ thật.

Khởi động tại thư mục dự án:

```bash
./gradlew bootRun
```

Trên Windows PowerShell dùng `.\gradlew.bat bootRun`. Đây là chương trình cần các phụ thuộc Spring/Micrometer; không chạy bằng `javac MetricsDiscoveryApplication.java` đơn lẻ thiếu classpath. Các dòng log khởi động phụ thuộc môi trường, còn phần thân HTTP của các yêu cầu hợp lệ phía dưới có giá trị xác định.

### 6.1. Trước khi gọi /work

Khởi động mới ứng dụng và lấy danh sách:

```bash
curl -i http://127.0.0.1:8080/actuator/metrics
```

Kỳ vọng HTTP 200, có `names`, nhưng chưa có `demo.work.completed` vì chưa chạy đoạn đăng ký counter. Có thể kiểm tra nhanh bằng PowerShell:

```powershell
$before = (Invoke-RestMethod -Uri 'http://127.0.0.1:8080/actuator/metrics').names
$before -contains 'demo.work.completed'
```

Kết quả biểu thức là `False`. Đọc trực tiếp chi tiết trước khi counter tồn tại:

```bash
curl -i http://127.0.0.1:8080/actuator/metrics/demo.work.completed
```

Kỳ vọng HTTP 404 ở cấu hình mẫu. Điều này không mâu thuẫn với việc `/actuator/metrics` đang trả 200: endpoint có thật, nhưng tên chỉ số được chọn chưa có dữ liệu đăng ký phù hợp.

### 6.2. Tạo đúng ba lượt ghi

Dùng một terminal khác trong khi ứng dụng vẫn chạy:

```bash
curl -i "http://127.0.0.1:8080/work?channel=web"
curl -i "http://127.0.0.1:8080/work?channel=web"
curl -i "http://127.0.0.1:8080/work?channel=mobile"
```

Cả ba yêu cầu hợp lệ trả HTTP 200. Phần thân lần lượt là `recorded:web`, `recorded:web`, `recorded:mobile`. Mỗi lần gọi tăng đúng một counter tương ứng với kênh đã chọn.

Các kết quả đếm tiếp theo giả định bắt đầu từ tiến trình mới và chỉ có đúng ba lượt `/work` trên. Nếu gọi thêm `/work`, tổng sẽ tăng; các yêu cầu đọc metrics không tự gọi phương thức `/work`.

### 6.3. Đọc lại danh sách

```powershell
$after = (Invoke-RestMethod -Uri 'http://127.0.0.1:8080/actuator/metrics').names
$after -contains 'demo.work.completed'
@($after | Where-Object { $_ -eq 'demo.work.completed' }).Count
```

Hai kết quả lần lượt là `True` và `1`. Tên tùy biến chỉ xuất hiện một lần dù đã có hai meter phân biệt theo tag channel. Không yêu cầu độ dài toàn bộ mảng chỉ tăng đúng 1, vì quá trình gọi HTTP có thể làm các meter quan sát HTTP khác xuất hiện.

### 6.4. Mở chi tiết và chọn một kênh

```bash
curl -s http://127.0.0.1:8080/actuator/metrics/demo.work.completed
```

Phản hồi tương ứng với ba lượt ghi:

```json
{
  "name": "demo.work.completed",
  "description": "Completed demo work",
  "baseUnit": "operations",
  "measurements": [
    {
      "statistic": "COUNT",
      "value": 3
    }
  ],
  "availableTags": [
    {
      "tag": "channel",
      "values": [
        "mobile",
        "web"
      ]
    }
  ]
}
```

Thứ tự giá trị trong các mảng không phải một phần bạn nên dùng để nhận diện kênh; hãy đọc chuỗi tên. COUNT bằng 3 là tổng của các meter phù hợp cùng tên tại thời điểm đọc, không phải số tên trong `names` và không tự là 3 lượt/giây.

Lọc riêng kênh web:

```bash
curl -s -G http://127.0.0.1:8080/actuator/metrics/demo.work.completed --data-urlencode "tag=channel:web"
```

Kết quả:

```json
{
  "name": "demo.work.completed",
  "description": "Completed demo work",
  "baseUnit": "operations",
  "measurements": [
    {
      "statistic": "COUNT",
      "value": 2
    }
  ],
  "availableTags": []
}
```

Giá trị COUNT bằng 2 xác nhận phép lọc. `availableTags` rỗng ở đây vì ví dụ chỉ có chiều channel và chiều đó đã được chọn. Nó không có nghĩa counter mất tag trong registry.

### 6.5. Đối chiếu các trường hợp không tìm thấy và yêu cầu sai

| Yêu cầu trong ứng dụng mẫu | HTTP kỳ vọng | Ý nghĩa |
| --- | --- | --- |
| `GET /actuator/metrics` | 200 | Đọc được danh sách tên |
| Chi tiết `demo.work.completed` trước lần gọi `/work` đầu | 404 | Tên chưa được đăng ký |
| `GET /work?channel=web` hoặc `mobile` | 200 | Đã ghi thêm một lượt |
| Chi tiết sau ba lượt ghi | 200 | Có mô tả, đơn vị, phép đo và tags |
| Chi tiết với `tag=channel:web` | 200 | Chọn được meter của kênh web |
| Chi tiết với `tag=channel:unknown` | 404 | Không có meter khớp bộ lọc |
| Chi tiết với `tag=channel` | 400 | Sai định dạng tag |
| `GET /work?channel=unknown` | 400 | Mã mẫu từ chối nhãn ngoài tập cho phép |

Các trạng thái trên được kiểm chứng với cấu hình mẫu. Nếu có Spring Security, proxy, đường dẫn tùy chỉnh hoặc bộ xử lý lỗi riêng, cần phân tích thêm tầng tạo phản hồi thực tế thay vì buộc mọi hệ thống trả đúng cùng một dạng lỗi.

## 7. Khi không thấy một chỉ số mong đợi

### 7.1. Tách lỗi truy cập endpoint khỏi lỗi tìm tên

Trước tiên kiểm tra `GET /actuator/metrics` có trả HTTP 200 với `names` không. Nếu chưa, hãy kiểm tra cổng/đường dẫn, phụ thuộc, cấu hình bật endpoint, web exposure, `exclude`, và quyền truy cập. Chưa đến bước đánh giá tên metric.

Nếu danh sách đọc được, kiểm tra đúng tên Micrometer và tìm trong mảng hiện tại. Không dùng tên đã đổi theo quy ước exporter; cũng không tìm một tên từ dự án khác rồi xem việc thiếu tên đó là lỗi của Actuator.

### 7.2. Kiểm tra vòng đời đăng ký và nguồn registry

Đối với meter tùy biến, đoạn đăng ký đã thực sự chạy chưa? Có bộ lọc từ chối nó không? Thành phần ghi có dùng `MeterRegistry` do Spring quản lý hay tự tạo `new SimpleMeterRegistry()` ở một nơi khác?

Đăng ký vào một registry riêng không tự khiến endpoint của ứng dụng thấy nó. Cách ví dụ dùng tiêm phụ thuộc giúp phép ghi và hạ tầng metrics ứng dụng làm việc với registry đã được quản lý.

Với metrics từ thư viện hoặc binder, cần có thành phần và điều kiện cấu hình tương ứng. Một tên chỉ xuất hiện sau thao tác cụ thể hoặc sau khi một tài nguyên được tạo có thể là hành vi bình thường.

### 7.3. Phân biệt các thuộc tính dễ nhầm

| Cấu hình | Điều nó điều khiển |
| --- | --- |
| `management.endpoint.metrics.enabled` | Việc bật endpoint metrics |
| `management.endpoints.web.exposure.include`/`exclude` | Những endpoint được đưa ra HTTP |
| `management.metrics.enable.<tiền-tố>` | Chấp nhận/từ chối các meter theo tiền tố tên qua cấu hình metrics |
| `management.metrics.use-global-registry` | Việc nối registry được cấu hình với global registry tĩnh |

Ví dụ `management.metrics.enable.demo=false` có thể lọc bỏ các meter bắt đầu bằng `demo`, dù `/actuator/metrics` vẫn hoạt động và tên JVM vẫn được liệt kê. Đừng sửa bằng cách công khai thêm endpoint khi nguyên nhân là meter đã bị filter từ chối. [Per-meter properties của Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.customizing.per-meter-properties).

### 7.4. Kiểm tra đúng tiến trình và thời điểm

Khởi động lại ứng dụng làm mất các meter tùy biến chỉ được đăng ký bởi những thao tác chưa chạy lại. Với nhiều instance, một lần gọi `/work` có thể vào instance A, còn lần đọc metrics tiếp theo vào B. Một danh sách khác nhau trong trường hợp đó không tự chứng minh metric “biến mất”.

Các meter được đăng ký sớm có thể tồn tại với giá trị 0 ngay sau khởi động; những meter đăng ký muộn thì cần tác động phù hợp. Luôn mô tả cách tái hiện và ranh giới tiến trình khi so kết quả.

## 8. Những kết luận danh sách tên không cung cấp

- Không biết hệ thống khỏe hay lỗi chỉ từ việc có tên `http.server.requests`.
- Không biết số lượng toàn bộ meter/tags hoặc mức dùng bộ nhớ từ độ dài mảng `names`.
- Không biết số request mỗi giây hoặc xu hướng nhiều giờ từ một ảnh chụp tên/giá trị hiện tại.
- Không xác nhận việc gửi dữ liệu tới Prometheus/OTLP hay hệ thống khác chỉ vì endpoint đọc được.
- Không tự thu thập thông tin của tất cả instance, mọi registry tùy ý hoặc mọi thư viện chưa được nối vào hạ tầng metrics.

`metrics` là cửa vào để khám phá và kiểm chứng instrumentation. Với biểu đồ, truy vấn lịch sử và cảnh báo, cần hệ thống giám sát và cấu hình xuất dữ liệu thích hợp. Endpoint `prometheus`, nếu được cấu hình, có vai trò/định dạng khác; không phải chỉ đổi tên URL là hai endpoint tương đương.

Không dùng vòng lặp gọi chi tiết mọi tên liên tục như một cách thay thế cơ chế thu thập metrics cho sản xuất. Công cụ chẩn đoán nên chọn tên liên quan tới câu hỏi đang điều tra, rồi đối chiếu với nguồn quan sát vận hành thực tế.

## 9. Quy trình khám phá có thể lặp lại

1. **Xác nhận đúng ứng dụng, instance, cổng và base path.** Ghi nhận trạng thái HTTP trước khi đọc dữ liệu.
2. **Lấy `/metrics` và lưu danh sách tên trong công cụ đang dùng.** Tìm tên theo câu hỏi, không đoán theo thứ tự phần tử.
3. **Mở chi tiết một tên có thật.** Đọc mô tả, đơn vị, statistic và tags hiện có.
4. **Tạo một thao tác thử có giới hạn rõ.** Biết đoạn mã nào sẽ đăng ký/ghi meter và số lượt dự kiến.
5. **Đọc lại tên và chi tiết.** Phân biệt tên mới xuất hiện với giá trị của meter đã có thay đổi.
6. **Lọc tags nếu tên đại diện nhiều nhóm.** Xác nhận từng nhóm trước khi diễn giải tổng.
7. **Kết luận đúng phạm vi.** Nêu dữ liệu của instance/thời điểm nào và điều gì chưa được kiểm chứng.

Với thí nghiệm trong bài, bằng chứng hoàn thành là: đọc được danh sách; tên tùy biến vắng trước thao tác và có sau thao tác; tên không bị lặp theo hai kênh; chi tiết tổng và phép lọc khớp ba lượt đã gửi. Không cần dựa vào một tổng số tên JVM cố định.

## 10. Tự kiểm tra

1. `/actuator/health` trả 200 nhưng `/actuator/metrics` trả 404. Nêu các lớp cấu hình cần kiểm tra trước khi sửa mã đăng ký counter.
2. Danh sách có 50 tên. Vì sao chưa thể kết luận registry chỉ có 50 meter hoặc hệ thống giám sát chỉ có 50 series?
3. Đăng ký sẵn một counter có giá trị 0 khác gì so với chỉ đăng ký counter trong lần gọi nghiệp vụ đầu tiên?
4. Thực hiện thí nghiệm từ tiến trình mới: gọi web hai lần và mobile một lần; dự đoán sự xuất hiện của tên, COUNT tổng và COUNT khi lọc web.
5. Vì sao `availableTags=[]` sau lọc channel không chứng minh tag channel đã bị xóa?
6. Tên có trong danh sách nhưng chi tiết với một bộ tags trả 404. Phân biệt tình huống đó với 404 của chính endpoint danh sách.
7. Một tên được tìm thấy bằng kiểu gạch dưới trên dashboard nhưng không thấy khi đưa vào URL metrics. Bạn sẽ lấy tên đúng từ đâu và kiểm tra điều gì tiếp theo?

Khám phá đúng endpoint metrics là tìm được **tên hiện có, chi tiết đúng phạm vi và bằng chứng trước–sau của thao tác đo**, trước khi chuyển sang phân tích sâu hoặc cấu hình hệ thống giám sát.

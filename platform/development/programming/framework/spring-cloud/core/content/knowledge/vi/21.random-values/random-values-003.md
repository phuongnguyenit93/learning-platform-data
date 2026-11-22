# Phân biệt cachedrandom với random của Spring Boot

Spring Boot và Spring Cloud đều có thể cung cấp giá trị ngẫu nhiên qua placeholder trong cấu hình, nhưng hai cơ chế phục vụ hai mục đích khác nhau. Spring Boot dùng tiền tố `random.` để tạo giá trị ngẫu nhiên khi property được tra cứu. Spring Cloud Context bổ sung tiền tố `cachedrandom.` để lưu giá trị đã tạo theo một khóa, nhờ đó cùng một khóa trả về cùng giá trị khi được tra cứu lại, kể cả khi ApplicationContext được khởi động lại trong cùng tiến trình.

Điểm khác biệt quan trọng là **có cache theo khóa hay không**. `random.uuid` phù hợp khi cần một giá trị mới; `cachedrandom.instance-id.uuid` phù hợp khi cần một giá trị ổn định trong vòng đời cache của tiến trình. Cả hai đều không thay thế kho cấu hình bền vững hoặc hệ thống quản lý secret.

Bài học thuộc chương **Giá trị ngẫu nhiên** của module **SPRING_CLOUD_CORE**. Nội dung giải thích `RandomValuePropertySource` của Spring Boot, `CachedRandomPropertySource` của Spring Cloud, cú pháp placeholder, thời gian tồn tại của giá trị, cách chọn cơ chế theo tình huống và cách kiểm thử.

## 1. Hai property source, hai hành vi

Spring Boot cung cấp `RandomValuePropertySource`, nhận diện các property bắt đầu bằng `random.`. Spring Cloud Context cung cấp `CachedRandomPropertySource`, nhận diện các property có dạng `cachedrandom.[yourkey].[type]`.

| Tiêu chí | `random.*` của Spring Boot | `cachedrandom.*` của Spring Cloud |
| --- | --- | --- |
| Property source | `RandomValuePropertySource` | `CachedRandomPropertySource` |
| Tiền tố | `random.` | `cachedrandom.` |
| Cách tạo giá trị | Sinh giá trị ngẫu nhiên khi property được tra cứu | Sinh lần đầu rồi cache theo khóa |
| Tra cứu lại cùng property | Có thể nhận giá trị mới | Nhận lại giá trị đã cache cho khóa đó |
| ApplicationContext restart trong cùng JVM | Không bảo đảm giữ giá trị cũ | Tài liệu Spring Cloud mô tả giữ giá trị qua lần restart context |
| JVM/process restart | Giá trị được tạo lại | Cache trong bộ nhớ mất; giá trị có thể khác |
| Phạm vi giữa các replica | Mỗi process tự sinh giá trị | Mỗi process có cache riêng |
| Thư viện cung cấp | Spring Boot | Spring Cloud Context |

Hai cơ chế dùng chung cách diễn giải phần `type`: kiểu giá trị mà Spring Boot RandomValuePropertySource hỗ trợ. `cachedrandom` bổ sung phần `yourkey` để xác định mục nào trong cache sẽ được dùng.

~~~mermaid
flowchart TD
    A["Placeholder trong cấu hình"] --> B{"Tiền tố"}
    B -->|"random.*"| C["Spring Boot RandomValuePropertySource"]
    B -->|"cachedrandom.*"| D["Spring Cloud CachedRandomPropertySource"]
    C --> E["Sinh giá trị theo lần tra cứu"]
    D --> F{"Khóa đã có trong cache?"}
    F -->|"Chưa"| G["Sinh giá trị và lưu theo khóa"]
    F -->|"Có"| H["Đọc giá trị đã lưu"]
    G --> I["Trả về giá trị"]
    H --> I
    E --> J["Trả về giá trị ngẫu nhiên"]
~~~

Không nên xem `cachedrandom` là một tên khác của `random`. Chúng có hợp đồng về tính ổn định khác nhau.

## 2. random của Spring Boot

Spring Boot tự thêm `RandomValuePropertySource` vào Environment trong quá trình khởi động. Ta có thể dùng placeholder trong file `application.yml` hoặc `application.properties` mà không cần tự viết bean tạo số ngẫu nhiên.

Ví dụ YAML:

~~~yaml
app:
  random:
    token-fragment: "${random.value}"
    instance-uuid: "${random.uuid}"
    worker-number: "${random.int}"
    delay-millis: "${random.int[100,1000]}"
    port-candidate: "${random.int[1024,65536]}"
    sequence-number: "${random.long}"
~~~

Ví dụ Properties:

~~~properties
app.random.token-fragment=${random.value}
app.random.instance-uuid=${random.uuid}
app.random.worker-number=${random.int}
app.random.delay-millis=${random.int[100,1000]}
app.random.port-candidate=${random.int[1024,65536]}
app.random.sequence-number=${random.long}
~~~

Các giá trị được resolve như property thông thường. Có thể inject bằng `@Value`, đọc qua `Environment` hoặc bind vào `@ConfigurationProperties`.

### 2.1. Các kiểu giá trị được hỗ trợ

| Placeholder | Kết quả |
| --- | --- |
| `${random.value}` | Giá trị ngẫu nhiên dạng byte/value do RandomValuePropertySource cung cấp |
| `${random.int}` | Số nguyên ngẫu nhiên |
| `${random.long}` | Số nguyên dài ngẫu nhiên |
| `${random.uuid}` | UUID ngẫu nhiên |
| `${random.int(10)}` | Số nguyên từ 0 đến nhỏ hơn 10 |
| `${random.int[1024,65536]}` | Số nguyên từ 1024 đến nhỏ hơn 65536 |
| `${random.long[1000,5000]}` | Số long từ 1000 đến nhỏ hơn 5000 |

Với cú pháp có hai giới hạn, giá trị đầu là min (được bao gồm) và giá trị thứ hai là max (không được bao gồm). Vì vậy, `random.int[1024,65536]` không sinh ra 65536.

Ký tự mở và đóng của phần range có thể dùng dấu ngoặc hoặc dấu ngoặc vuông theo cú pháp Spring Boot mô tả. Nên thống nhất một cách viết trong dự án để cấu hình dễ đọc.

### 2.2. random không cache theo tên property

`RandomValuePropertySource` không cung cấp hợp đồng cache theo tên property. Khi Environment tra cứu `random.uuid` nhiều lần, property source có thể sinh các UUID khác nhau.

Ví dụ kiểm tra trực tiếp:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class RandomValueReader {

    private final Environment environment;

    public RandomValueReader(Environment environment) {
        this.environment = environment;
    }

    public String nextUuid() {
        return environment.getProperty("random.uuid");
    }
}
~~~

Mỗi lần gọi `nextUuid()` là một lần đọc Environment. Với `random.uuid`, lần đọc mới có thể trả UUID khác lần trước.

Tuy nhiên, cần phân biệt tra cứu Environment với việc inject placeholder vào bean. Nếu `@Value("${random.uuid}")` được resolve khi bean khởi tạo, field của bean giữ giá trị đã inject đó. Field không tự đổi mỗi khi phương thức khác đọc `Environment.getProperty("random.uuid")`.

### 2.3. Ví dụ @Value và ConfigurationProperties

Inject trực tiếp:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class WorkerIdentity {

    private final String startupId;

    public WorkerIdentity(
            @Value("${random.uuid}") String startupId) {
        this.startupId = startupId;
    }

    public String getStartupId() {
        return startupId;
    }
}
~~~

Bind vào nhóm cấu hình:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.random")
public class RandomSettings {

    private String instanceUuid;
    private int workerNumber;

    public String getInstanceUuid() {
        return instanceUuid;
    }

    public void setInstanceUuid(String instanceUuid) {
        this.instanceUuid = instanceUuid;
    }

    public int getWorkerNumber() {
        return workerNumber;
    }

    public void setWorkerNumber(int workerNumber) {
        this.workerNumber = workerNumber;
    }
}
~~~

Đăng ký `RandomSettings` bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties(RandomSettings.class)`. Các giá trị được bind khi cấu hình được nạp. Nếu muốn đọc một random value mới ở mỗi thao tác, không nên chỉ giữ một field đã bind lúc startup.

## 3. cachedrandom của Spring Cloud Context

Spring Cloud Context cung cấp `CachedRandomPropertySource`. Cơ chế này hoạt động tương tự RandomValuePropertySource của Spring Boot, nhưng lưu giá trị theo khóa.

Cú pháp:

~~~text
cachedrandom.[yourkey].[type]
~~~

Trong đó:
- `cachedrandom` là tiền tố của property source.
- `yourkey` là khóa dùng để tìm giá trị trong cache.
- `type` là kiểu random mà Spring Boot hỗ trợ, ví dụ `value`, `int`, `long`, `uuid` hoặc kiểu có range.

Ví dụ:

~~~yaml
app:
  identity:
    instance-id: "${cachedrandom.catalog-service.instance-id.uuid}"
    worker-port: "${cachedrandom.catalog-service.worker-port.int[20000,30000]}"
    opaque-value: "${cachedrandom.catalog-service.opaque-value.value}"
~~~

Khi `catalog-service.instance-id.uuid` được tra cứu lần đầu, Spring Cloud tạo UUID rồi lưu vào cache theo khóa. Lần tra cứu sau với cùng khóa sẽ trả lại giá trị đã lưu.

### 3.1. Khóa cache quyết định giá trị được dùng lại

Giả sử hai thuộc tính cùng tham chiếu một cache key:

~~~yaml
app:
  primary-id: "${cachedrandom.orders.instance-id.uuid}"
  diagnostic-id: "${cachedrandom.orders.instance-id.uuid}"
~~~

Hai placeholder dùng cùng key và type nên nhận cùng giá trị đã cache.

Nếu cần hai giá trị độc lập, dùng hai key khác nhau:

~~~yaml
app:
  instance-id: "${cachedrandom.orders.instance-id.uuid}"
  correlation-seed: "${cachedrandom.orders.correlation-seed.uuid}"
~~~

Tên key nên:
- Có ý nghĩa theo mục đích sử dụng.
- Ổn định giữa các lần khởi tạo context.
- Không chứa secret hoặc dữ liệu cá nhân.
- Khác nhau giữa các giá trị cần độc lập.
- Được giữ nhất quán khi đổi tên property cấu hình.

Không thay key theo mỗi lần deploy nếu mục tiêu là dùng lại giá trị đã cache trong cùng process. Đổi key đồng nghĩa yêu cầu một mục cache khác và có thể sinh giá trị mới.

### 3.2. Ví dụ dùng cùng giá trị qua nhiều bean

~~~java
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class InstanceIdentity {

    private final UUID instanceId;

    public InstanceIdentity(
            @Value("${cachedrandom.orders.instance-id.uuid}")
            UUID instanceId) {
        this.instanceId = instanceId;
    }

    public UUID getInstanceId() {
        return instanceId;
    }
}
~~~

Một bean khác có thể dùng cùng placeholder:

~~~java
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class DiagnosticIdentity {

    private final UUID instanceId;

    public DiagnosticIdentity(
            @Value("${cachedrandom.orders.instance-id.uuid}")
            UUID instanceId) {
        this.instanceId = instanceId;
    }

    public UUID getInstanceId() {
        return instanceId;
    }
}
~~~

Hai bean nhận cùng UUID vì placeholder dùng cùng cache key. Đây là điểm khác với việc tạo UUID mới trong constructor bằng `UUID.randomUUID()`.

## 4. cachedrandom tồn tại bao lâu?

Tài liệu Spring Cloud mô tả cached random value có thể giữ tính nhất quán khi Spring ApplicationContext được restart. Điều này hữu ích khi ứng dụng đóng rồi tạo lại context trong cùng tiến trình JVM.

Cần phân biệt các phạm vi:

| Sự kiện | `random.*` | `cachedrandom.*` |
| --- | --- | --- |
| Đọc property nhiều lần | Sinh giá trị mới theo lần tra cứu | Dùng lại giá trị theo key |
| Tạo bean khác trong cùng context | Placeholder được resolve theo thời điểm tạo bean | Cùng key nhận giá trị đã cache |
| Đóng và tạo lại ApplicationContext trong cùng JVM | Không có cam kết giữ giá trị cũ | Cache có thể giữ giá trị cũ theo tài liệu |
| Restart JVM/process | Giá trị mới khi process khởi động lại | Cache bộ nhớ bị tạo lại; không bảo đảm giá trị cũ |
| Chạy hai replica độc lập | Mỗi process tự sinh giá trị | Mỗi process có cache riêng, có thể tạo hai giá trị khác nhau |

**cachedrandom không phải cache bền vững.** Nó không ghi giá trị xuống database, file, Config Server hoặc secret manager. Khi JVM kết thúc, cache trong bộ nhớ của process không còn.

Vì vậy:
- Dùng cachedrandom nếu cần ổn định qua việc tạo lại ApplicationContext trong cùng process.
- Không dùng nó làm định danh bền vững qua deployment/restart process.
- Không dùng nó để chia sẻ cùng một secret giữa nhiều replica.
- Không dùng nó để thay thế một ID được cấp từ database hoặc hệ thống định danh tập trung.

Nếu cần giữ cùng một giá trị qua nhiều lần triển khai, hãy tạo giá trị một lần rồi lưu vào nguồn bền vững, chẳng hạn Config Server, Vault, Kubernetes Secret hoặc database theo quy trình quản trị phù hợp.

### 4.1. Restart context khác restart process

Một số ứng dụng có thể đóng và tạo lại ApplicationContext để áp dụng một cơ chế restart trong cùng JVM. Đây là tình huống mà cachedrandom hướng tới.

Ngược lại, khi container bị xóa rồi tạo lại, Pod được reschedule, JVM bị kill hoặc máy chủ reboot, process mới có bộ nhớ mới. Không thể dựa vào cache của process cũ.

~~~mermaid
flowchart TD
    A["JVM process khởi động"] --> B["CachedRandomPropertySource"]
    B --> C["Tạo key instance-id lần đầu"]
    C --> D["Cache giá trị UUID"]
    D --> E["ApplicationContext hoạt động"]
    E --> F["Context đóng và tạo lại trong cùng JVM"]
    F --> G["Cùng cache key"]
    G --> H["Nhận lại UUID đã cache"]
    H --> I["JVM kết thúc"]
    I --> J["Process mới, cache mới"]
    J --> K["Cùng key có thể sinh UUID khác"]
~~~

## 5. Property source và thứ tự ưu tiên

Spring Boot nạp các nguồn cấu hình vào `Environment`. `RandomValuePropertySource` là một property source riêng dành cho các key `random.*`; tài liệu Spring Boot đặt nó sau config data và trước các nguồn như OS environment variables trong thứ tự mặc định.

Spring Cloud Context bổ sung property source cho `cachedrandom.*`. Khi cần chẩn đoán thứ tự thực tế, hãy kiểm tra Environment của đúng ứng dụng và phiên bản thay vì giả định mọi cấu hình đều có cùng thứ tự sau khi thêm các EnvironmentPostProcessor hoặc thư viện khác.

Một số điểm cần nhớ:
- `random.*` và `cachedrandom.*` là hai namespace khác nhau.
- Một property thông thường như `app.instance-id` có thể dùng placeholder để tham chiếu một trong hai namespace.
- Giá trị cuối cùng của property phụ thuộc property source và placeholder resolution.
- Nếu có nguồn cấu hình khác ghi đè property đích, hãy kiểm tra giá trị hiệu lực chứ không chỉ đọc file YAML.
- Không đưa giá trị ngẫu nhiên hoặc secret lên endpoint quản trị công khai.

Ví dụ:

~~~yaml
app:
  instance-id: "${cachedrandom.orders.instance-id.uuid}"
~~~

Các thành phần trong ứng dụng đọc `app.instance-id`, không cần biết nơi tạo UUID. Điều này giúp thay đổi chính sách tạo ID mà không phải sửa mọi consumer.

## 6. Khi nào chọn random và khi nào chọn cachedrandom?

| Nhu cầu | Lựa chọn phù hợp | Lý do |
| --- | --- | --- |
| UUID mới cho mỗi lần tra cứu | `random.uuid` | Không yêu cầu cache theo key |
| Số ngẫu nhiên cho test hoặc cấu hình tạm | `random.int`, `random.long` | Cấu hình ngắn, được Spring Boot hỗ trợ |
| Một giá trị dùng chung giữa nhiều bean | `cachedrandom.<key>.<type>` | Cùng key trả lại cùng giá trị |
| Giữ giá trị khi ApplicationContext được restart trong cùng JVM | `cachedrandom.<key>.<type>` | Cache tồn tại ngoài vòng đời một context |
| Giữ ID qua restart JVM/container | Nguồn lưu bền vững | Cache in-memory không tồn tại qua process |
| Secret dùng cho xác thực production | Secret manager/KMS/Vault | Cần quản lý vòng đời, quyền truy cập và rotation |
| ID duy nhất cho nhiều replica | ID service/database/UUID theo thiết kế phân tán | Cache của từng JVM không dùng chung |
| Port test ngẫu nhiên | `random.int[...]` hoặc test utility chọn port | Không cần ổn định sau restart |

### 6.1. Ví dụ cho cấu hình test

Có thể dùng `random.int` để tạo một giá trị thử nghiệm trong giới hạn:

~~~yaml
test:
  retry:
    delay-millis: "${random.int[50,250]}"
~~~

Mỗi lần cấu hình được resolve trong process test, giá trị nằm trong khoảng 50 đến nhỏ hơn 250. Không dùng giá trị này để xác định port thật nếu chưa kiểm tra port có đang được hệ điều hành sử dụng hay không.

### 6.2. Ví dụ cho định danh ổn định trong một process

~~~yaml
app:
  diagnostics:
    process-id: "${cachedrandom.orders.process-id.uuid}"
~~~

Các bean trong cùng process có thể dùng cùng process ID. Khi context được tạo lại trong cùng JVM, cùng key có thể trả lại giá trị cũ. Khi process khởi động lại, ID có thể thay đổi.

Nếu mục tiêu là định danh một bản triển khai qua nhiều lần restart, cần lưu ID ở nguồn bền vững hoặc nhận ID từ nền tảng triển khai.

## 7. Không dùng random property làm secret mật mã

Tên property có thể gợi ý rằng `random.value` là lựa chọn để tạo password, token hoặc encryption key. Tuy nhiên, RandomValuePropertySource được thiết kế để cung cấp giá trị ngẫu nhiên cho cấu hình và test; không nên mặc định xem nó là một hệ thống quản lý secret hoặc bộ sinh khóa mật mã chuyên dụng.

Không dùng `random.*` hoặc `cachedrandom.*` làm nguồn sinh secret mật mã cho production. Đối với dữ liệu nhạy cảm:
- Dùng Vault, KMS, secret manager hoặc cơ chế tương đương.
- Dùng `java.security.SecureRandom` khi ứng dụng thực sự phải tự sinh dữ liệu ngẫu nhiên có yêu cầu mật mã. `RandomValuePropertySource` là tiện ích cấu hình, không phải cam kết về bộ sinh số ngẫu nhiên mật mã.
- Lưu trữ và phân phối secret theo chính sách của hệ thống.
- Có kế hoạch rotation, thu hồi và audit.
- Không ghi giá trị secret vào log, metric, trace hoặc Actuator endpoint.
- Không dùng cachedrandom để chia sẻ secret giữa replicas hoặc qua lần restart process.

Một giá trị cached ổn định không đồng nghĩa với một secret an toàn. Cache chỉ giải quyết tính nhất quán của giá trị trong phạm vi bộ nhớ được quản lý.

## 8. Tác động khi refresh cấu hình

Spring Cloud Context hỗ trợ cập nhật Environment và refresh bean trong ứng dụng. Tuy nhiên, thao tác refresh không đồng nghĩa với xóa cache của CachedRandomPropertySource.

Nếu một property dùng:

~~~yaml
app:
  node:
    id: "${cachedrandom.orders.node-id.uuid}"
~~~

thì việc gọi refresh cấu hình và resolve lại cùng cache key vẫn có thể trả giá trị đã cache. Muốn tạo một giá trị khác, cần dùng key khác hoặc một cơ chế quản lý giá trị có vòng đời riêng.

Với `random.uuid`, mỗi lần tra cứu mới có thể tạo giá trị mới. Nhưng nếu giá trị đã được bind vào một singleton hoặc lưu trong field, việc đọc lại Environment không tự thay đổi field đó. Cần hiểu rõ property đang được resolve ở thời điểm nào.

### 8.1. Đổi cache key là một cách tạo giá trị mới

Ví dụ:

~~~yaml
app:
  node:
    current-id: "${cachedrandom.orders.node-id-v2.uuid}"
~~~

Key `orders.node-id-v2` khác key trước, vì vậy yêu cầu một entry cache mới. Đây là cách tạo giá trị mới theo cấu hình, nhưng cần quản lý việc đổi key có chủ đích để tránh thay ID ngoài ý muốn.

Không nên gắn timestamp hoặc UUID mới vào key mỗi lần refresh nếu mục tiêu là cache ổn định; cách đó biến mỗi lần tra cứu thành một entry khác và làm mất ý nghĩa của cache key.

## 9. Kiểm thử hai hành vi

Nên kiểm tra hai property source riêng biệt để không nhầm kết quả do placeholder đã được resolve trong bean với hành vi của property source.

### 9.1. Unit test cho RandomValuePropertySource

Ví dụ kiểm tra cùng một property được tra cứu hai lần:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.env.RandomValuePropertySource;

class RandomValuePropertySourceTests {

    @Test
    void generatesNewUuidForRepeatedLookups() {
        RandomValuePropertySource source =
                new RandomValuePropertySource();

        Object first = source.getProperty("random.uuid");
        Object second = source.getProperty("random.uuid");

        assertThat(first).isNotEqualTo(second);
    }
}
~~~

Test này kiểm tra trực tiếp property source. Trong ứng dụng thực, `@Value` thường chỉ resolve placeholder tại thời điểm bean được tạo, vì vậy không nên dùng một field đã inject để kết luận rằng property source có cache hay không.

### 9.2. Unit test cho CachedRandomPropertySource

Spring Cloud cung cấp `CachedRandomPropertySource`. Có thể kiểm tra cùng key trả về cùng giá trị:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.env.RandomValuePropertySource;
import org.springframework.cloud.util.random.CachedRandomPropertySource;

class CachedRandomPropertySourceTests {

    @AfterEach
    void clearCache() {
        CachedRandomPropertySource.clearCache();
    }

    @Test
    void reusesValueForTheSameCacheKey() {
        CachedRandomPropertySource source =
                new CachedRandomPropertySource(
                        new RandomValuePropertySource()
                );

        Object first =
                source.getProperty("cachedrandom.orders.instance-id.uuid");

        Object second =
                source.getProperty("cachedrandom.orders.instance-id.uuid");

        assertThat(first).isEqualTo(second);
    }

    @Test
    void usesIndependentValuesForDifferentKeys() {
        CachedRandomPropertySource source =
                new CachedRandomPropertySource(
                        new RandomValuePropertySource()
                );

        Object primaryFirst =
                source.getProperty("cachedrandom.orders.primary-id.uuid");
        Object primaryAgain =
                source.getProperty("cachedrandom.orders.primary-id.uuid");

        Object secondaryFirst =
                source.getProperty("cachedrandom.orders.secondary-id.uuid");
        Object secondaryAgain =
                source.getProperty("cachedrandom.orders.secondary-id.uuid");

        assertThat(primaryAgain).isEqualTo(primaryFirst);
        assertThat(secondaryAgain).isEqualTo(secondaryFirst);
    }
}
~~~

Test dùng `clearCache()` để cô lập trạng thái giữa các lần chạy. Đây là API của CachedRandomPropertySource; hãy kiểm tra package/API theo release train Spring Cloud mà dự án sử dụng.

Hai key độc lập được kiểm tra riêng. Không nên viết assertion yêu cầu hai giá trị ngẫu nhiên của hai key khác nhau tuyệt đối, vì hai giá trị độc lập vẫn có xác suất trùng nhau dù xác suất đó rất nhỏ.

### 9.3. Integration test cho ApplicationContext restart

Unit test ở trên xác nhận cache theo key trong một instance property source. Nếu muốn kiểm tra hành vi qua ApplicationContext restart, cần chạy ứng dụng bằng SpringApplication với Spring Cloud Context trên classpath để EnvironmentPostProcessor được đăng ký.

Một kịch bản integration test:
1. Khởi chạy context đầu tiên trong JVM test.
2. Đọc `cachedrandom.test.instance-id.uuid` từ Environment.
3. Đóng context đầu tiên.
4. Khởi chạy context thứ hai trong cùng JVM.
5. Đọc lại cùng cache key.
6. Xác nhận giá trị bằng nhau.
7. Dùng một key khác để xác nhận cache entry độc lập.

Không dùng hai process/JVM riêng biệt cho test này nếu mục tiêu là kiểm tra cache qua context restart. Hai JVM có hai vùng nhớ độc lập.

## 10. Chẩn đoán khi cachedrandom không hoạt động

Nếu placeholder `cachedrandom.*` không được resolve như mong đợi, kiểm tra theo thứ tự:

1. Spring Cloud Context/Commons có trong classpath không?
2. Phiên bản Spring Cloud BOM có tương thích với Spring Boot không?
3. EnvironmentPostProcessor của CachedRandomPropertySource có được đăng ký không?
4. Property source `cachedrandom` có xuất hiện trong Environment không?
5. Placeholder có đúng dạng `cachedrandom.[key].[type]` không?
6. Các lần đọc có thực sự dùng cùng key không?
7. Có property source khác ghi đè property đích không?
8. Có test nào gọi clearCache() hoặc thay đổi cache trong lúc chạy không?
9. Ứng dụng có bị restart process thay vì chỉ restart context không?

Có thể dùng Actuator `env` trong môi trường test hoặc management network được bảo vệ để xem property source. Không expose endpoint hoặc giá trị random/secret trên production chỉ để debug.

### 10.1. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `cachedrandom.*` không resolve | Thiếu Spring Cloud Context hoặc processor không được đăng ký | Kiểm tra dependency, BOM và EnvironmentPostProcessor |
| Cùng property `random.uuid` cho kết quả khác nhau | Random property source không cache theo key | Dùng cachedrandom nếu cần dùng lại giá trị |
| Cùng cachedrandom nhưng giá trị đổi sau deploy | JVM/process mới tạo cache mới | Dùng nguồn lưu bền vững nếu cần qua process restart |
| Hai replica có cùng cache key nhưng giá trị khác | Mỗi JVM có cache riêng | Dùng Config Server, Vault hoặc ID service dùng chung |
| Hai bean có ID khác nhau | Dùng key khác nhau hoặc resolve qua cơ chế random riêng | Dùng cùng cache key và type nếu cần cùng giá trị |
| Giá trị field không đổi sau refresh | Field đã giữ giá trị được inject trước đó | Kiểm tra thời điểm resolve/binding và vòng đời bean |
| Giá trị cachedrandom đổi sau khi sửa key | Key mới tạo entry cache khác | Giữ key ổn định hoặc quản lý đổi key có chủ đích |
| Random value bị lộ qua Actuator | Expose endpoint hoặc show-values quá rộng | Giới hạn exposure, masking và quyền truy cập |

## 11. Checklist chọn cơ chế

Trước khi thêm random placeholder vào cấu hình, hãy xác định:

- [ ] Giá trị có cần mới ở mỗi lần tra cứu hay phải ổn định theo key?
- [ ] Giá trị có cần giữ qua lần tạo lại ApplicationContext không?
- [ ] Có cần giữ qua JVM/container restart không?
- [ ] Có cần chia sẻ cùng giá trị giữa nhiều replica không?
- [ ] Giá trị có phải secret hoặc khóa mật mã không?
- [ ] Cache key đã có tên ổn định và không trùng với mục đích khác chưa?
- [ ] Dependency Spring Cloud Context và BOM có tương thích không?
- [ ] Test đã phân biệt property source lookup với giá trị đã inject vào bean chưa?
- [ ] Log, Actuator và telemetry có vô tình hiển thị giá trị nhạy cảm không?

## Ghi nhớ

`random.*` của Spring Boot sinh giá trị ngẫu nhiên khi property được tra cứu và không cache theo khóa. `cachedrandom.[yourkey].[type]` của Spring Cloud Context bổ sung cache theo key, giúp cùng key nhận lại giá trị khi ApplicationContext được tạo lại trong cùng JVM. Cache này nằm trong bộ nhớ process, không phải nơi lưu bền vững và không dùng chung giữa các replica. Hãy chọn `random` cho giá trị cần thay đổi, `cachedrandom` cho giá trị cần ổn định trong phạm vi cache của process, và dùng secret manager hoặc nguồn lưu trữ bền vững khi cần bảo toàn giá trị qua restart/deploy.

## Tài liệu tham khảo

- Spring Cloud Commons – CachedRandomPropertySource: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/cachedrandompropertysource.html
- Spring Boot – Externalized Configuration / Configuring Random Values: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot – RandomValuePropertySource API: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/env/RandomValuePropertySource.html


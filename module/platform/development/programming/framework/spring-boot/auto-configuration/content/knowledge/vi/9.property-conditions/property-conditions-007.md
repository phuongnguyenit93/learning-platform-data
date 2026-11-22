# Chuẩn hóa tên khóa dạng kebab-case và kiểm tra nguồn giá trị hiệu lực

> **Ý chính:** Trong Spring Boot Auto Configuration, cần trả lời đúng **hai câu hỏi khác nhau**: (1) condition đang kiểm tra **khóa cấu hình nào** và khóa ấy đã được viết theo dạng chuẩn chưa; (2) tại lúc condition được đánh giá, **giá trị hiệu lực của khóa ấy** đến từ `PropertySource` nào sau khi Spring Boot áp dụng thứ tự ưu tiên. Chỉ nhìn vào một dòng trong `application.yml` thường không đủ để kết luận vì biến môi trường, Java system property, tham số dòng lệnh, profile và tệp cấu hình ngoài ứng dụng có thể ghi đè nó.

Bài học sử dụng Spring Boot **3.3.x**, Java **17+**, trọng tâm là cấu hình có điều kiện thông qua `@ConditionalOnProperty`.

## 1. Dạng khóa chuẩn: lowercase kebab-case

Quy ước canonical của Spring Boot là: dùng chữ thường, dấu chấm để chia các phần của đường dẫn cấu hình, dấu gạch ngang `-` giữa các từ trong mỗi phần.

Ví dụ về **một khóa chuẩn**:

~~~properties
demo.feature.audit-enabled=true
~~~

Trong ví dụ này:

- `demo.feature` là tiền tố (prefix), thể hiện nhóm cấu hình.
- `audit-enabled` là tên thuộc tính gồm hai từ nối bằng dấu `-`.
- Toàn bộ khóa `demo.feature.audit-enabled` là căn cứ thống nhất để viết code, tài liệu và kiểm tra lỗi.

### Cùng ý nghĩa qua các nguồn cấu hình

| Nơi khai báo | Ví dụ | Lưu ý |
| --- | --- | --- |
| `application.properties` | `demo.feature.audit-enabled=true` | Dạng chuẩn nên dùng. |
| `application.properties` (camelCase) | `demo.feature.auditEnabled=true` | Relaxed binding có thể nhận diện khi truy vấn tên chuẩn; nên thống nhất về kebab-case để dễ đối chiếu. |
| `application.properties` (underscore) | `demo.feature.audit_enabled=true` | Một dạng khác được hỗ trợ trong binding; không nên trộn các cách viết của cùng một cấu hình. |
| `application.yml` | `demo: { feature: { audit-enabled: true } }` | Sau khi flatten thành đường dẫn thuộc tính, khóa tương ứng là `demo.feature.audit-enabled`. |
| Biến môi trường hệ điều hành | `DEMO_FEATURE_AUDITENABLED=true` | Dấu chấm → `_`, **bỏ dấu `-`**, rồi viết hoa. |
| Tham số dòng lệnh | `--demo.feature.audit-enabled=true` | Sử dụng đường dẫn canonical. |
| Java system property | `-Ddemo.feature.audit-enabled=true` | Đặt trước `-jar` khi khởi chạy JVM. |

**Quy tắc đổi tên sang biến môi trường** theo tài liệu Spring Boot:

1. Thay dấu chấm bằng gạch dưới: `demo.feature.audit-enabled` → `demo_feature_audit-enabled`.
2. **Xóa** gạch ngang trong một segment: → `demo_feature_auditenabled`.
3. Viết hoa: → `DEMO_FEATURE_AUDITENABLED`.

Vì vậy, đừng đoán `DEMO_FEATURE_AUDIT_ENABLED` là tên tương đương của `demo.feature.audit-enabled`. Các dấu `_` thêm vào có thể được hiểu như phân tách các phần khác nhau của đường dẫn; hãy suy tên từ canonical key theo đúng ba bước, rồi thử trên runtime thực tế.

Cấu hình YAML tương đương, dễ đọc hơn dạng inline:

~~~yaml
demo:
  feature:
    audit-enabled: true
~~~

Trong annotation, chọn cách viết:

~~~java
@ConditionalOnProperty(
    prefix = "demo.feature",
    name = "audit-enabled",
    havingValue = "true"
)
~~~

Spring Boot ghép `prefix` và `name` thành `demo.feature.audit-enabled`. Đối với `@ConditionalOnProperty`, Javadoc khuyến nghị `name` ở dạng lowercase dashed notation. `@ConfigurationProperties(prefix = "demo.feature")` cũng yêu cầu prefix canonical; khi lấy giá trị bằng `@Value`, nên dùng placeholder dạng `@Value("${demo.feature.audit-enabled}")` vì cách viết chuẩn giúp Boot áp dụng khả năng nhận diện các biến thể tên tương ứng.

**Phân biệt:** *relaxed binding* giúp liên hệ các tên hợp lệ giữa những nguồn khác nhau; nó **không** có nghĩa mọi chuỗi tùy ý với dấu chấm/gạch dưới/gạch ngang đều được coi là một khóa. Một khóa sai cấu trúc vẫn có thể không khớp condition.

## 2. Condition xét giá trị gì?

`@ConditionalOnProperty` là điều kiện dựa trên thuộc tính có thể truy vấn từ Spring `Environment` **tại thời điểm đánh giá cấu hình**. Trong trường hợp trên, nó nhìn `demo.feature.audit-enabled`; nếu condition không khớp thì bean hoặc class cấu hình được đánh dấu sẽ không được đăng ký theo nhánh đó.

Cần đọc đủ bốn yếu tố:

- `prefix` + `name`: tên khóa đầy đủ.
- `havingValue`: chuỗi giá trị được yêu cầu; nên chỉ rõ khi muốn bật/tắt theo cờ.
- `matchIfMissing`: có cho qua khi không tìm được thuộc tính hay không; mặc định `false`.
- Các giá trị trong `name = {"a", "b"}`: **tất cả** các khóa được nêu phải thỏa điều kiện, không phải chỉ một khóa.

Bảng sau minh họa kết quả (giả sử property tồn tại và có đúng chuỗi ghi trong cột đầu):

| Giá trị hiệu lực | Không khai báo `havingValue` | `havingValue="true"` | `havingValue="false"` |
| --- | --- | --- | --- |
| `true` | Khớp | Khớp | Không khớp |
| `false` | Không khớp | Không khớp | Khớp |
| `custom` | Khớp | Không khớp | Không khớp |
| *Không có khóa* | Không khớp nếu `matchIfMissing=false` | Không khớp nếu `matchIfMissing=false` | Không khớp nếu `matchIfMissing=false` |

Mặc định `havingValue=""` có nghĩa property **phải có mặt và không bằng `false`**; nó **không** tương đương với yêu cầu giá trị boolean `true`. Với tính năng chỉ nên bật khi cấu hình thật sự là `true`, hãy khai báo `havingValue = "true"` một cách tường minh.

Đặt `matchIfMissing = true` chỉ khi chủ ý coi trường hợp **không khai báo** là được bật. Nó không làm cho giá trị `false` đã được khai báo biến thành “missing”. `@ConditionalOnProperty` cũng **không** thích hợp để kiểm tra đáng tin cậy việc tồn tại các phần tử của list, chẳng hạn chỉ có `demo.targets[0]` mà không có `demo.targets`; khi cần điều kiện phức tạp trên collection, dùng custom condition hoặc thiết kế khác.

## 3. “Nguồn giá trị hiệu lực” nghĩa là gì?

`Environment` tập hợp nhiều `PropertySource`. Một khóa có thể xuất hiện ở nhiều nơi với những giá trị khác nhau. Spring Boot có quy tắc ưu tiên; thông thường **nguồn có ưu tiên cao nhất đang cung cấp giá trị hợp lệ** quyết định giá trị mà condition đọc được.

Với các nguồn thông dụng trong **Spring Boot 3.3**, có thể hình dung thứ tự từ ưu tiên cao xuống thấp như sau:

| Ưu tiên tương đối | Nguồn | Ví dụ |
| --- | --- | --- |
| Cao | Tham số dòng lệnh ứng dụng (`--key=value`) | `--demo.feature.audit-enabled=false` |
| ↓ | `SPRING_APPLICATION_JSON` | `{"demo":{"feature":{"audit-enabled":true}}}` |
| ↓ | Java system properties (`-D...`) | `-Ddemo.feature.audit-enabled=true` |
| ↓ | Biến môi trường OS | `DEMO_FEATURE_AUDITENABLED=true` |
| ↓ | Config data: `application.properties` / YAML, file ngoài JAR, tài liệu theo profile, file import | `demo.feature.audit-enabled=false` |
| Thấp hơn | Default properties của `SpringApplication` | Giá trị mặc định khi chưa có override |

Đây là bản rút gọn cho các nguồn hay gặp, không phải danh sách đầy đủ: JNDI, servlet parameters, nguồn do test tạo, `@PropertySource` và Devtools cũng có vị trí trong thứ tự thực tế. Nguồn từ test có thể được xếp cao hơn command-line. Trong nhóm config data, các nguồn cũng có thứ tự riêng; ví dụ cấu hình profile đang kích hoạt thường ghi đè cấu hình chung theo quy tắc tải config data. Thứ tự **không** được quyết định bằng cách sắp tên tệp hoặc tên property theo bảng chữ cái.

### Ví dụ có ba nơi khai báo

Trong JAR:

~~~yaml
# application.yml
demo:
  feature:
    audit-enabled: false
~~~

Trong môi trường chạy (shell POSIX):

~~~bash
export DEMO_FEATURE_AUDITENABLED=true
~~~

Khi chạy bằng command line:

~~~bash
java -jar app.jar --demo.feature.audit-enabled=false
~~~

Kết quả khi ứng dụng khởi động theo cấu hình thông thường:

1. Config data có `false`.
2. OS environment đưa `true` và thắng config data nếu không có nguồn cao hơn.
3. Command-line đưa `false` và thắng cả hai nguồn trước.

**Giá trị hiệu lực là `false`**, nên `@ConditionalOnProperty(prefix = "demo.feature", name = "audit-enabled", havingValue = "true")` **không khớp**. Nếu bỏ tham số dòng lệnh, biến môi trường `true` có thể trở thành giá trị thắng. Nếu bỏ cả biến môi trường, `false` trong YAML là giá trị hiệu lực.

Cũng cần kiểm tra `spring.profiles.active`, `spring.config.import`, `spring.config.location` và `spring.config.additional-location`: một profile/file được kích hoạt hoặc vị trí bổ sung có thể khiến bạn đang quan sát **khác nguồn** so với tệp vừa sửa. Nếu cùng một vị trí có cả `application.properties` và `application.yml`, Boot ưu tiên tệp `.properties`; nên tránh duy trì hai bản chứa cùng một khóa.

Một giá trị xuất hiện trong `application.yml` chỉ chứng minh **đã khai báo trong tệp đó**, không chứng minh đó là giá trị condition sẽ thấy. Để xác minh, phải xem trạng thái `Environment` và các source có hiệu lực ở runtime.

## 4. Quy trình chẩn đoán từ khóa đến nguồn thắng

Khi thấy bean chưa được tạo hoặc được tạo sai với mong đợi, làm lần lượt:

**Bước 1 — Viết lại khóa canonical trên giấy.** Từ annotation xác định chính xác `prefix + name`. Ví dụ `prefix = "demo.feature"` và `name = "audit-enabled"` cho ra `demo.feature.audit-enabled`. Kiểm tra lỗi dấu chấm, gạch ngang, số ít/số nhiều và chính tả.

**Bước 2 — Kiểm tra các biến thể nhập liệu.** Xem khóa trong YAML/properties, biến OS, `-D`, `--`, `SPRING_APPLICATION_JSON`. Dùng phép đổi sang biến môi trường chuẩn, ví dụ `DEMO_FEATURE_AUDITENABLED`. Chú ý biến môi trường đã thực sự được truyền vào **tiến trình Java** hay mới chỉ nằm ở một terminal, IDE run configuration, container hoặc pod khác.

**Bước 3 — Xem profile và config data.** Ghi lại profile đang active và vị trí nạp cấu hình. Đối chiếu file trong JAR, file ngoài JAR và các file được import. Đừng chỉ nhìn tệp mình mới sửa nếu ứng dụng đang được khởi chạy với nguồn override.

**Bước 4 — Quan sát giá trị hiệu lực bằng `Environment`.** Ở nơi có thể tiêm `Environment`:

~~~java
// Minh họa bên trong một bean/component đã được Spring quản lý
String canonicalKey = "demo.feature.audit-enabled";
String effectiveValue = environment.getProperty(canonicalKey);
System.out.println("Effective value = " + effectiveValue);
~~~

Đoạn mã trên giả định biến `environment` là một `org.springframework.core.env.Environment` đã được inject; nó **không** là chương trình Java độc lập. Giá trị `null` thường có nghĩa khóa không được phân giải, không khẳng định tệp cấu hình không tồn tại. Tránh in giá trị của password/token/secret khi chẩn đoán.

**Bước 5 — Tìm nguồn và origin, không dừng ở giá trị.** Nếu có `spring-boot-starter-actuator`, trong môi trường chẩn đoán được bảo vệ có thể cho phép truy cập:

~~~properties
management.endpoints.web.exposure.include=health,conditions,env,configprops
~~~

Sau đó kiểm tra:

~~~text
GET /actuator/env/demo.feature.audit-enabled
GET /actuator/conditions
GET /actuator/configprops
~~~

- `/actuator/env/{name}` giúp kiểm tra giá trị được chọn và các nguồn cấu hình liên quan; dữ liệu `origin` (ví dụ tên file/dòng) có thể xuất hiện khi nguồn hỗ trợ.
- `/actuator/conditions` trả lời **vì sao** condition của auto-configuration khớp hoặc không khớp; hữu ích khi property đúng tên nhưng sai `havingValue`.
- `/actuator/configprops` giúp đối chiếu kết quả bind vào `@ConfigurationProperties`; kết quả bind này không tự chứng minh nhánh `@ConditionalOnProperty` khớp.

Các endpoint `env` và `configprops` có cơ chế che giá trị nhạy cảm. Actuator **không** mở các endpoint này ra HTTP theo mặc định; khi cần xem phải cấu hình exposure và bảo vệ quyền truy cập. Trong production, không bật công khai chỉ để thử điều kiện.

Ngoài ra, chạy ứng dụng với `--debug` có thể hiển thị **Condition Evaluation Report** trong log, tùy cấu hình logging. Báo cáo condition giải thích quyết định tạo cấu hình; bảng property source giải thích nguồn của giá trị. Hai loại thông tin bổ sung cho nhau.

### Xác định origin trong Java khi cần kiểm chứng sâu

Spring Boot có API `ConfigurationPropertySources` để truy vấn nguồn theo **tên canonical**. Đoạn sau là một phương thức minh họa, có thể đặt trong một class của ứng dụng với dependency Spring Boot 3.3:

~~~java
import org.springframework.boot.context.properties.source.ConfigurationProperty;
import org.springframework.boot.context.properties.source.ConfigurationPropertyName;
import org.springframework.boot.context.properties.source.ConfigurationPropertySource;
import org.springframework.boot.context.properties.source.ConfigurationPropertySources;
import org.springframework.core.env.ConfigurableEnvironment;

public final class PropertyProbe {
    private PropertyProbe() {}

    public static void inspect(ConfigurableEnvironment environment) {
        ConfigurationPropertyName key =
                ConfigurationPropertyName.of("demo.feature.audit-enabled");

        for (ConfigurationPropertySource source :
                ConfigurationPropertySources.get(environment)) {
            ConfigurationProperty property =
                    source.getConfigurationProperty(key);
            if (property != null) {
                System.out.println("value=" + property.getValue());
                System.out.println("origin=" + property.getOrigin());
                return; // Lấy nguồn đầu tiên có giá trị theo thứ tự ưu tiên
            }
        }
        System.out.println("property missing");
    }
}
~~~

Đây là class Java hợp lệ nhưng phải được **gọi từ một ứng dụng Spring Boot đang có `ConfigurableEnvironment`**; nó không tự tạo context. Nếu `Origin` là `null` thì source đó không cung cấp metadata xuất xứ. Không tự suy luận dòng file khi metadata không có; và không in bí mật cấu hình ra log. Khi dùng cơ chế nguồn cấu hình đặc biệt, hãy so sánh với `/actuator/env` hoặc báo cáo thực tế để xác nhận.

## 5. Ví dụ chạy được: condition và thứ tự nguồn bằng ApplicationContextRunner

Ví dụ dưới đây là **một tệp test Java hoàn chỉnh** trên Spring Boot 3.3 + JUnit 5 + AssertJ, phù hợp dự án Java 17+ có `spring-boot-starter` và dependency test `spring-boot-starter-test`.

**Tệp:** `src/test/java/example/conditions/AuditConditionTest.java`

~~~java
package example.conditions;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.MapPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

class AuditConditionTest {
    private static final String KEY = "demo.feature.audit-enabled";

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(AuditAutoConfiguration.class));

    @Test
    void absentKeyDoesNotRegisterBean() {
        runner.run(context ->
                assertThat(context).doesNotHaveBean("auditMarker"));
    }

    @Test
    void trueValueRegistersBean() {
        runner.withPropertyValues(KEY + "=true").run(context -> {
            assertThat(context).hasBean("auditMarker");
            assertThat(context.getEnvironment().getProperty(KEY))
                    .isEqualTo("true");
        });
    }

    @Test
    void falseValueDoesNotRegisterBean() {
        runner.withPropertyValues(KEY + "=false").run(context ->
                assertThat(context).doesNotHaveBean("auditMarker"));
    }

    @Test
    void nonTrueValueDoesNotRegisterBean() {
        runner.withPropertyValues(KEY + "=custom").run(context ->
                assertThat(context).doesNotHaveBean("auditMarker"));
    }

    @Test
    void higherPriorityPropertySourceWins() {
        runner.withInitializer(context -> {
            var sources = context.getEnvironment().getPropertySources();
            sources.addLast(new MapPropertySource(
                    "example-low-priority",
                    Map.of(KEY, "false")));
            sources.addFirst(new MapPropertySource(
                    "example-high-priority",
                    Map.of(KEY, "true")));
        }).run(context -> {
            assertThat(context.getEnvironment().getProperty(KEY))
                    .isEqualTo("true");
            assertThat(context).hasBean("auditMarker");
        });
    }

    @AutoConfiguration
    static class AuditAutoConfiguration {
        @Bean
        @ConditionalOnProperty(
                prefix = "demo.feature",
                name = "audit-enabled",
                havingValue = "true")
        String auditMarker() {
            return "audit-active";
        }
    }
}
~~~

**Chạy test** từ thư mục gốc một dự án Maven/Gradle đã thiết lập test theo Spring Boot 3.3:

~~~bash
mvn -Dtest=AuditConditionTest test
# Hoặc dùng Gradle wrapper trên Linux/macOS:
./gradlew test --tests example.conditions.AuditConditionTest
~~~

**Kết quả mong đợi:** **5 test PASS**; không có stdout cố định vì đây là các assertion của JUnit. Test cuối cố tình tạo hai `MapPropertySource` cùng chứa `demo.feature.audit-enabled`. `addFirst` ưu tiên giá trị `true` của `example-high-priority` hơn `false` của `example-low-priority`; bean `auditMarker` được tạo. Đây là **mô phỏng trực tiếp thứ tự nguồn**, không phải mô phỏng tên nguồn “command line” hoặc “OS environment” trong Spring Boot thật.

Từ đó, có thể mở rộng test để kiểm tra key canonical xuất hiện trong `application.yml`, override khi active profile hoặc thêm source ưu tiên cao. Luôn kiểm tra cả **giá trị Environment** lẫn **bean có được đăng ký**; chỉ kiểm tra một phía có thể bỏ sót nguyên nhân.

## 6. Bảng quyết định khi gặp cấu hình bất thường

| Triệu chứng | Kiểm tra nhanh | Hướng sửa |
| --- | --- | --- |
| `@ConditionalOnProperty` không khớp dù file có `true` | Có override `false` từ `--`, `-D`, OS env, profile, JSON không? | Tìm giá trị hiệu lực và nguồn thắng; thay đổi ở đúng nguồn. |
| Bean vẫn được đăng ký khi giá trị là `custom` | Có quên `havingValue = "true"` không? | Chỉ rõ `havingValue` cho cờ bật/tắt. |
| Biến môi trường không tác động đến condition | Có đặt đúng `DEMO_FEATURE_AUDITENABLED` và truyền vào process Java không? | Chuẩn hóa tên từ canonical key; kiểm tra env thực tại lúc chạy. |
| `matchIfMissing` cho kết quả khó hiểu | Khóa thật sự vắng mặt hay có `false`/chuỗi rỗng? | Phân biệt **không có khóa** với **có khóa nhưng giá trị không đạt**. |
| Chỉ sai trên một profile | File `application-{profile}.yml` hoặc `spring.config.import` ghi đè không? | Xem toàn bộ config data được nạp và thứ tự ưu tiên. |
| Bật/tắt property sau khi context khởi động nhưng bean không thay đổi | Condition được đánh giá tại lúc đăng ký configuration/bean | Cần cơ chế runtime feature flag riêng nếu phải thay đổi mà không khởi động lại. |

**Sai lầm hay gặp khác:** Dùng kết quả binding của `@ConfigurationProperties` để khẳng định một `@ConditionalOnProperty` chắc chắn khớp. Hai cơ chế có liên quan đến nguồn cấu hình nhưng không hoàn toàn đồng nhất về mục đích; condition còn xét `havingValue`, `matchIfMissing`, thời điểm đánh giá và cách khai báo khóa. Ngoài ra, không tự suy đoán source thắng bằng cách nhìn thứ tự dòng xuất hiện trong một file YAML.

## 7. Tự kiểm tra hiểu bài

1. Từ `billing.invoice.retry-enabled`, biến môi trường canonical tương ứng là gì? **`BILLING_INVOICE_RETRYENABLED`** — thay dấu chấm bằng `_`, xóa dấu `-`, viết hoa.
2. `application.yml` ghi `demo.feature.audit-enabled=false`; môi trường đặt `DEMO_FEATURE_AUDITENABLED=true`; command line không có override. Giá trị thường có hiệu lực là gì? **`true`**, vì OS environment ưu tiên hơn config data.
3. Có thêm command line `--demo.feature.audit-enabled=false`. Điều kiện `havingValue="true"` còn khớp không? **Không**, vì giá trị hiệu lực trở thành `false`.
4. `@ConditionalOnProperty(prefix="demo.feature", name="audit-enabled")` gặp giá trị `custom`. Nó có khớp không? **Có**, theo mặc định nó chỉ loại bỏ giá trị `false` và trường hợp thiếu thuộc tính; dùng `havingValue="true"` nếu muốn chính xác `true`.
5. Vì sao `/actuator/conditions` và `/actuator/env/...` đều hữu ích? **Conditions** cho biết lý do khớp hoặc không khớp; **env** giúp tìm giá trị/nguồn hiệu lực. Cả hai phải được truy cập trong môi trường được bảo vệ.

## Tài liệu đối chiếu

- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): canonical key, relaxed binding, thứ tự `PropertySource`, cấu hình profile, `env`/`configprops`.
- [Spring Boot 3.3 — ConditionalOnProperty API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html): `name` dạng dashed, `havingValue`, `matchIfMissing` và giới hạn với collection.
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): property condition trong auto-configuration.
- [Spring Boot 3.3 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): `env`, `configprops`, `conditions` và cách expose endpoint.

**Ghi nhớ:** Viết **một tên khóa chuẩn** cho code và tài liệu; khi hành vi không đúng kỳ vọng, truy đến **giá trị hiệu lực và nguồn đã thắng** tại thời điểm điều kiện được đánh giá, rồi xác minh lại bằng một test context nhỏ.

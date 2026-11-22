# Quy trình truy vết giá trị: khóa, nguồn, profile, vị trí và thời điểm đọc

Trong Spring Boot Externalized Configuration, một giá trị như `app.client.timeout=2s` có thể được khai báo ở nhiều nơi: `application.yml`, `application-prod.yml`, tệp bên ngoài JAR, Config Data được import, biến môi trường, JVM system property, tham số command-line hoặc một `PropertySource` tùy biến. Khi chương trình chạy, cùng một key có thể có **nhiều giá trị ứng viên** nhưng Spring Boot chỉ dùng giá trị phù hợp với **thứ tự ưu tiên và thời điểm đọc** để bind vào object Java.

Một sự cố quen thuộc: người phát triển nhìn thấy `timeout: 5s` trong YAML, nhưng service thực tế nhận `500ms`. Hoặc môi trường production chạy sai profile, một dòng cấu hình được đặt đúng file nhưng file đó chưa được nạp, hoặc file vừa được sửa nhưng một bean immutable vẫn dùng giá trị cũ. Để chẩn đoán có hệ thống, không nên đoán “Spring cache cấu hình” hay sửa ngẫu nhiên một file.

Bài này hướng dẫn truy vết theo **năm trục**:

1. **Khóa (key):** ứng dụng đang yêu cầu chính xác property nào, dưới tên canonical nào?
2. **Nguồn (source):** những `PropertySource` nào chứa ứng viên, và nguồn nào có ưu tiên cao nhất?
3. **Profile:** active/default profiles có đúng và đã khiến tài liệu Config Data cần thiết được nạp không?
4. **Vị trí (origin/location):** giá trị đến từ file nào, dòng nào, biến môi trường hay đối số nào?
5. **Thời điểm (time):** ứng dụng đọc/bind/copy giá trị vào object lúc nào, và có refresh hay không?

Các ví dụ viết cho Spring Boot 3.x, Java 17+; thuật ngữ như `ConfigData`, `Environment`, `PropertySource`, `Binder`, `OriginLookup`, `@ConfigurationProperties` và `Actuator` là cơ sở để áp dụng trên dự án thực. Những ví dụ log, lệnh kiểm tra và báo cáo chỉ dùng giá trị **không nhạy cảm**; không in password/token hay toàn bộ environment ở production.

## 1. Bản đồ từ file cấu hình tới giá trị đang được sử dụng

~~~text
Nguồn đầu vào
  ├── application.yml / application.properties
  ├── application-<profile>.yml
  ├── spring.config.import / file:/... / configtree:/...
  ├── OS environment: APP_CLIENT_TIMEOUT
  ├── JVM system property: -Dapp.client.timeout=...
  ├── application arguments: --app.client.timeout=...
  └── PropertySource do ứng dụng / thư viện tạo
                      |
                      v
       Spring Environment / Config Data
       - profile nào active?
       - những source nào được nạp?
       - thứ tự ưu tiên nguồn thế nào?
                      |
                      v
          Property lookup / Binder
       - tìm đúng canonical key
       - chọn value hiệu lực
       - giải quyết placeholder
       - chuyển String -> Duration
                      |
                      v
      @ConfigurationProperties / @Value
       hoặc Environment.getProperty(...)
                      |
                      v
           Bean hoặc service consumer
       - đang giữ snapshot lúc startup?
       - đọc lại Environment mỗi lần gọi?
       - có refresh/recreate hay không?
~~~

Ở từng bước đều có thể phát sinh chênh lệch:

- **Sai khóa:** YAML có `app.client.time-out` nhưng model muốn `app.client.timeout`.
- **Sai nguồn:** file đúng nhưng một biến môi trường ưu tiên cao hơn ghi đè.
- **Sai profile:** `application-prod.yml` chưa được nạp vì active profile là `dev`.
- **Sai vị trí:** sửa `src/main/resources/application.yml` trong workspace, nhưng JAR chạy là bản cũ hoặc đang dùng file external.
- **Sai thời điểm:** tệp đã đổi sau startup, nhưng bean vẫn giữ dữ liệu đã bind.
- **Sai loại dữ liệu:** value được tìm thấy nhưng không convert được sang kiểu Java.
- **Sai consumer:** cấu hình đúng nhưng service lưu một bản copy hoặc tự đặt default khác.

Không gộp mọi trường hợp thành “Spring không đọc cấu hình”; phải xác định tầng đầu tiên bị lệch.

## 2. Đặt câu hỏi truy vết trước khi sửa

Một mẫu ghi chép ngắn cho ticket kỹ thuật:

~~~text
Ứng dụng: order-service
Môi trường: staging
Key cần điều tra: app.client.timeout
Giá trị mong đợi: 5s
Giá trị quan sát: 500ms
Consumer: ClientProperties.timeout()
Profile đang chạy: staging
Loại đọc: @ConfigurationProperties (startup bind)
Nguồn dự kiến: application-staging.yml
Triệu chứng: client timeout sớm
~~~

Các trường cần xác nhận bằng bằng chứng thực tế, không điền theo suy đoán. Ví dụ nếu chưa biết active profiles thì ghi “chưa xác nhận”, không lấy tên môi trường Kubernetes hay branch Git làm câu trả lời.

**Một key, một lần truy vết:** bắt đầu từ một property có thể kiểm chứng trước, rồi mở rộng sang những key liên quan. Không dump toàn bộ config để tìm vấn đề đơn lẻ.

## 3. Trục 1 — Xác định khóa canonical

Giả sử Java model:

~~~java
package com.example.orders.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    Duration timeout,
    int maxRetries
) {}
~~~

Các key canonical tương ứng:

~~~properties
app.client.timeout=2s
app.client.max-retries=3
~~~

Nếu trong YAML:

~~~yaml
app:
  client:
    timeout: 2s
    max-retries: 3
~~~

thì cấu trúc là đúng. Với `@ConfigurationProperties`, Spring Boot hỗ trợ **relaxed binding**, giúp các cách viết phổ biến của một tên property có thể map sang camelCase Java component.

Nhưng relaxed binding không tự sửa lỗi chính tả:

~~~properties
app.clinet.timeout=2s
~~~

`clinet` không phải `client`. Nếu application có default hoặc không validate field, key sai có thể bị bỏ qua trong khi bean vẫn khởi động.

### Phân biệt prefix với field

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(Duration timeout) {}
~~~

Model trên cần `app.client.timeout`, không phải `app.timeout` và cũng không phải `client.timeout`.

Nếu consumer dùng:

~~~java
environment.getProperty("app.client.timeout")
~~~

hãy kiểm đúng key. Nếu consumer dùng `@Value`, hãy kiểm placeholder được viết như thế nào:

~~~java
@Value("\${app.client.timeout:2s}")
private Duration timeout;
~~~

Ở đây `:2s` là fallback của placeholder nếu property không được giải quyết theo cách phù hợp; không phải bằng chứng nguồn YAML đã cung cấp 2 giây.

**Tách rõ tên property, kiểu Java và default của consumer** trước khi xét precedence.

## 4. Quy tắc tên biến môi trường cho Spring Boot

Một deployment có thể đặt:

~~~text
APP_CLIENT_TIMEOUT=500ms
APP_CLIENT_MAXRETRIES=4
SPRING_PROFILES_ACTIVE=prod
SERVER_PORT=8080
~~~

Với canonical property:

~~~text
app.client.timeout        -> APP_CLIENT_TIMEOUT
app.client.max-retries    -> APP_CLIENT_MAXRETRIES
spring.profiles.active    -> SPRING_PROFILES_ACTIVE
server.port               -> SERVER_PORT
~~~

Quy tắc phổ biến khi chuyển tên canonical sang environment variable cho `@ConfigurationProperties`:

1. Thay dấu chấm `.` bằng dấu gạch dưới `_`.
2. Bỏ dấu gạch ngang `-` trong segment.
3. Chuyển thành chữ hoa.
4. Đối với list index, dùng số được phân tách bằng underscore theo quy tắc Binder.

Ví dụ:

~~~text
app.gateways[0].timeout   -> APP_GATEWAYS_0_TIMEOUT
app.client.base-url       -> APP_CLIENT_BASEURL
~~~

Không mặc định coi `APP_CLIENT_BASE_URL` và `APP_CLIENT_BASEURL` là hoàn toàn tương đương đối với mọi đường đọc. `@ConfigurationProperties` và `Environment.getProperty(...)` có các cơ chế ánh xạ/lookup không giống hệt nhau trong tất cả tình huống; nên ưu tiên canonical form và kiểm bằng test thực.

**Lưu ý Docker Compose:** biến chỉ có trong file `.env` dùng cho Compose interpolation **không tự được đưa vào container**. Trước khi đổ lỗi cho Spring, xác định biến đã thực sự nằm trong process environment.

## 5. Trục 2 — Nguồn và giá trị ứng viên

Spring Boot `Environment` tập hợp các `PropertySource`. Một key có thể có ở nhiều nguồn cùng lúc.

Ví dụ:

~~~yaml
# application.yml
app:
  client:
    timeout: 5s
~~~

~~~yaml
# application-prod.yml
app:
  client:
    timeout: 8s
~~~

Biến môi trường trong process:

~~~text
APP_CLIENT_TIMEOUT=2s
~~~

Lệnh chạy:

~~~bash
java -jar order-service.jar \
  --spring.profiles.active=prod \
  --app.client.timeout=500ms
~~~

Trong một ứng dụng Spring Boot thông thường, command-line property có ưu tiên cao hơn environment variables và Config Data. Do đó, property hiệu lực là `500ms`, mặc dù file cơ sở ghi `5s`, file prod ghi `8s`, OS environment ghi `2s`.

Không phải file nào chứa key cũng là nguồn thắng. Một bảng suy luận:

| Nguồn | Key/value ứng viên | Có tham gia? | Kết luận |
| --- | --- | --- | --- |
| `application.yml` | `5s` | Có | Không thắng |
| `application-prod.yml` | `8s` | Có nếu prod active | Không thắng |
| OS environment | `APP_CLIENT_TIMEOUT=2s` | Có trong process | Không thắng |
| Application CLI | `--app.client.timeout=500ms` | Có | Thắng trong ví dụ |

**Chỉ khi đã xác nhận source thực sự được nạp**, mới kết luận nó bị một source cao hơn ghi đè. Một file chưa được nạp không phải ứng viên.

## 6. Thứ tự ưu tiên — hiểu theo hướng tổng quát

Trong Spring Boot, thứ tự PropertySources thường được xây để nguồn có ưu tiên cao hơn có thể ghi đè nguồn thấp hơn. Các nhóm quan trọng trong triển khai:

- Tham số dòng lệnh Spring Boot dạng `--key=value` thường có ưu tiên rất cao.
- `SPRING_APPLICATION_JSON` là một nguồn có vị trí riêng trong precedence.
- JVM system properties `-Dkey=value` thường cao hơn OS environment.
- OS environment thường cao hơn Config Data từ file.
- Config Data gồm file packaged, external, profile-specific và imported theo quy tắc chi tiết.
- `@PropertySource` có thứ tự và thời điểm bổ sung riêng, không phải công cụ phù hợp để override mọi cài đặt giai đoạn sớm.
- Default properties do application cung cấp nằm ở mức dự phòng thấp hơn trong nhiều tình huống.

Đây là **khung tư duy**, không phải danh sách tuyệt đối cho mọi dự án. Các nguồn từ test, servlet/JNDI, custom `EnvironmentPostProcessor`, chương trình tự thêm `PropertySource` hoặc starter riêng có thể làm thứ tự cụ thể khác đi.

Khi xảy ra tranh chấp, **đừng chỉ học thuộc precedence rồi suy đoán**: hãy quan sát các nguồn thực tế trong `ConfigurableEnvironment` hoặc thông tin Actuator đã được bảo vệ.

Một sự thật quan trọng: field default trong Java record/JavaBean **không phải một PropertySource**. Đó là fallback trong logic tạo/bind object, không tham gia tranh priority như file hay OS environment.

## 7. Kiểm giá trị Spring Environment đang trả

Một cách đơn giản để thử tại thời điểm chạy:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class TimeoutReporter {
    private final Environment environment;

    public TimeoutReporter(Environment environment) {
        this.environment = environment;
    }

    public String currentTimeout() {
        return environment.getProperty(
            "app.client.timeout", "<missing>");
    }
}
~~~

Ví dụ method có thể trả `"500ms"` nếu command-line source đang thắng. **Chỉ dùng method này cho key không nhạy cảm**. Đối với secret, không log hoặc trả nó qua HTTP endpoint.

Để nhận giá trị có kiểu:

~~~java
Duration timeout = environment.getProperty(
    "app.client.timeout",
    Duration.class
);
~~~

Spring `Environment` có thể chuyển value sang `Duration` nếu conversion tương ứng được cấu hình hỗ trợ. `@ConfigurationProperties` Binder có cơ chế conversion và relaxed binding phù hợp riêng; do đó test qua `Environment.getProperty` hữu ích để thấy value hiệu lực, nhưng không thay thế test binding của một nhóm cấu hình phức tạp.

### Trường hợp key vắng

~~~java
String value = environment.getProperty(
    "app.client.timeout");
~~~

Nếu trả `null`, có thể key chưa có trong các sources thấy được bằng cách lookup đó. Nhưng service vẫn nhận timeout qua một default của `@Value`, `@DefaultValue` hoặc field initializer. **Giá trị consumer không nhất thiết chỉ từ property lookup**.

## 8. Duyệt PropertySources theo thứ tự thực tế

Khi cần biết **nguồn nào chứa key**, có thể dùng `ConfigurableEnvironment`:

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;
import org.springframework.stereotype.Component;

@Component
public class PropertySourceInspector {
    private final ConfigurableEnvironment environment;

    public PropertySourceInspector(
        ConfigurableEnvironment environment
    ) {
        this.environment = environment;
    }

    public void inspectNamesForNonSensitiveKey() {
        String key = "app.client.timeout";
        for (PropertySource<?> source
                : environment.getPropertySources()) {
            Object rawValue = source.getProperty(key);
            if (rawValue != null) {
                System.out.println(
                    "candidate source: " + source.getName());
            }
        }
    }
}
~~~

**Quan trọng:** ví dụ chỉ in **tên source**, không in value. Spring `MutablePropertySources` được duyệt theo thứ tự precedence mà Environment sử dụng tại thời điểm gọi. Phần tử đầu tiên cung cấp giá trị cho lookup tương ứng thường là source thắng.

Một hạn chế thực tế: một số `PropertySource` cung cấp relaxed aliasing, placeholder resolution hoặc xử lý origin đặc thù. `source.getProperty(key)` là phép kiểm tra trực tiếp đối với source đó, nhưng **không phải công cụ khôi phục hoàn hảo mọi spelling/index/value đã qua Binder**. Với nested list/map và environment aliases, luôn kiểm kết quả bind typed thực tế.

Không cho endpoint công khai quyền duyệt hoặc hiển thị tất cả PropertySources; chúng có thể chứa password, token, private key và thông tin nội bộ.

## 9. Tìm nguồn thắng nhưng không tiết lộ value

Một helper kiểu chẩn đoán có thể dừng ở source đầu tiên cung cấp một key không nhạy cảm:

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

public final class PropertyDiagnostics {
    private PropertyDiagnostics() {}

    public static String firstCandidateSourceName(
        ConfigurableEnvironment env,
        String key
    ) {
        for (PropertySource<?> source : env.getPropertySources()) {
            if (source.getProperty(key) != null) {
                return source.getName();
            }
        }
        return "<no direct candidate>";
    }
}
~~~

Cách dùng:

~~~java
String sourceName =
    PropertyDiagnostics.firstCandidateSourceName(
        environment, "app.client.timeout");
~~~

Đây là một công cụ **định hướng**: tìm source đầu tiên có value trả bởi `PropertySource.getProperty` cho key được hỏi. Nếu project có custom resolver, dynamic source, deferred resolution hoặc relaxed binding đặc thù, hãy kiểm thêm bằng Binder/Actuator/test.

Nếu key là secret, **chỉ có source name cũng có thể tiết lộ cấu trúc hạ tầng**. Hạn chế quyền xem kết quả và không biến helper thành chức năng người dùng cuối.

## 10. Trục 3 — Profile đang active là profile nào?

Đừng suy luận active profile từ tên máy chủ, tên branch hay file tồn tại trong repository. Hãy lấy thông tin từ Spring Environment:

~~~java
import java.util.Arrays;
import org.springframework.core.env.Environment;

public void reportProfiles(Environment env) {
    System.out.println(
        "active profiles = "
            + Arrays.toString(env.getActiveProfiles()));
    System.out.println(
        "default profiles = "
            + Arrays.toString(env.getDefaultProfiles()));
}
~~~

`getActiveProfiles()` trả các profile đang active trong Environment. `getDefaultProfiles()` trả profile mặc định được sử dụng khi không có profile active theo cơ chế Spring. Hai khái niệm khác nhau.

Ví dụ:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

hoặc biến môi trường:

~~~text
SPRING_PROFILES_ACTIVE=prod
~~~

kích hoạt `prod` theo cấu hình Spring thông thường. Nhưng nếu một nguồn ưu tiên cao hơn đặt `spring.profiles.active` khác, kết quả phải được xác nhận trên Environment thực.

### Một lỗi hay gặp

Developer đọc `application-prod.yml` và nói “production đã dùng 8s”. Nhưng `getActiveProfiles()` cho `[staging]`. File production tồn tại trong artifact nhưng **không vì thế tự được nạp**. Hãy tìm active profiles và nguồn cung cấp chúng trước khi debug từng key.

## 11. Active và default profiles không giống nhau

Giả sử:

~~~properties
spring.profiles.default=local
~~~

Nếu không có explicit active profile, các điều kiện theo default profile có thể tham gia. Nếu `spring.profiles.active=prod` đã được cung cấp, default profile không có vai trò giống như một active profile bổ sung.

Cần phân biệt:

- **Active profiles:** được kích hoạt một cách tường minh hoặc qua cơ chế hợp lệ, tác động đến lựa chọn Config Data và bean `@Profile`.
- **Default profiles:** dùng khi không có active profiles.
- **Profile groups:** có thể nhóm nhiều profile với `spring.profiles.group.*` trong cấu hình hợp lệ; một active group có thể dẫn tới nhiều profile được active.
- **Profile-specific documents:** được nạp/chọn khi profile tương ứng active, không phải chỉ vì có file.

Không tự tính toán danh sách file profile bằng cách nối tên môi trường. Xem danh sách profile thực tế và cơ chế Config Data của Boot.

## 12. Nơi được đặt spring.profiles.active

Trong Spring Boot Config Data, không nên đặt `spring.profiles.active` hoặc các thuộc tính điều khiển kích hoạt profile tại tài liệu đã được kích hoạt theo profile theo cách trái với quy tắc của phiên bản Boot.

Ví dụ cấu hình cơ sở:

~~~yaml
# application.yml - tài liệu cơ sở
spring:
  profiles:
    active: dev
~~~

có thể là cách thiết lập active profile trong bối cảnh phù hợp, nhưng production thường nên điều khiển profile bằng môi trường triển khai hoặc CLI, tránh đóng cứng `dev` vào artifact dùng chung.

Một file như `application-prod.yml` không phải nơi đáng tin để “tự bật profile prod”, vì file đó được chọn **sau khi** hệ thống đã xác định profile theo các nguồn hợp lệ.

Tương tự, tài liệu YAML có `spring.config.activate.on-profile` không phải nơi để tuỳ ý định nghĩa lại `spring.profiles.active` nhằm tạo vòng kích hoạt profile.

**Quy tắc gỡ lỗi:** kiểm vị trí khai báo active/default/include/group; không di chuyển những key này qua profile-specific file mà không xét hạn chế Config Data.

## 13. Đọc nhiều YAML document theo profile

Một file `application.yml` có thể chứa nhiều tài liệu:

~~~yaml
app:
  client:
    timeout: 3s

---
spring:
  config:
    activate:
      on-profile: prod
app:
  client:
    timeout: 8s
~~~

Khi profile `prod` active và không có source cao hơn ghi đè, tài liệu thứ hai có thể cung cấp `app.client.timeout=8s`. Khi `prod` không active, tài liệu điều kiện đó không được áp dụng.

Cần phân biệt:

- File có được tìm và nạp không?
- Tài liệu YAML nào trong file được kích hoạt?
- Một profile-specific file khác có khai báo cùng key không?
- Có Config Data import hoặc environment property ưu tiên hơn không?
- Giá trị cuối được convert/bind như thế nào?

**“Đã đọc application.yml” không có nghĩa mọi tài liệu trong file đều active.**

## 14. Trục 4 — Vị trí khai báo (Origin)

Trong Spring Boot, một số property sources có thể lưu thông tin **origin**, ví dụ file cấu hình, tên resource và số dòng/column. Từ đó failure analyzer đôi khi in:

~~~text
Property: app.client.timeout
Value: "soon"
Origin: class path resource [application.yml] - 7:14
Reason: Failed to convert from String to Duration
~~~

Đây là mẫu minh họa, không phải một chuỗi log được bảo đảm giống nhau trên mọi phiên bản. `Origin` rất có ích vì nó cho biết **nơi value được lấy**, không phải tệp developer đang nghĩ tới.

### Origin có những loại nào?

- Classpath resource trong executable JAR.
- External file từ file location.
- Profile-specific YAML/properties.
- Import resource, config tree hoặc PropertySource có hỗ trợ origin.
- Biến môi trường hoặc system property với metadata nguồn tương ứng khi có.
- Custom PropertySource có thể không cung cấp thông tin chi tiết.

**Không phải mọi nguồn đều có số dòng.** Một biến môi trường do container cung cấp thường không có “dòng trong YAML” theo nghĩa ứng dụng Java có thể biết. Nếu origin vắng, không được tự bịa vị trí file.

## 15. Truy vấn OriginLookup cho một key

Spring Boot có API origin hỗ trợ lấy metadata từ những source có origin tracking. Mã minh họa:

~~~java
import org.springframework.boot.origin.Origin;
import org.springframework.boot.origin.OriginLookup;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

public final class OriginInspector {
    private OriginInspector() {}

    public static void inspectNonSensitiveKey(
        ConfigurableEnvironment env,
        String key
    ) {
        for (PropertySource<?> source : env.getPropertySources()) {
            Object candidate = source.getProperty(key);
            if (candidate == null) {
                continue;
            }

            Origin origin = OriginLookup.getOrigin(source, key);
            System.out.println("source = " + source.getName());
            System.out.println(
                "origin available = " + (origin != null));
        }
    }
}
~~~

Ví dụ này tránh in `candidate` hoặc `origin` nguyên văn. Khi đã xác nhận **key không nhạy cảm** và môi trường kiểm thử cho phép, có thể hiển thị thông tin origin đã được chọn lọc để biết file/dòng cần xem. Những resource path có thể tiết lộ thông tin triển khai, nên không tự công khai.

`OriginLookup.getOrigin(...)` có thể trả `null` khi source không cung cấp origin, hoặc khi lookup không map vào một origin cụ thể. Tên source và origin cùng nhau hữu ích, nhưng không thay thế việc hiểu PropertySource precedence.

### Source name không phải lúc nào là filepath

Ví dụ `systemEnvironment`, `systemProperties` hoặc `commandLineArgs` là tên source theo cơ chế Spring. Không có nghĩa chúng tương ứng với file vật lý. Nếu cần biết biến container được cấp ở Compose file nào, phải kiểm **hạ tầng triển khai**; Spring Environment không tự nắm toàn bộ lịch sử Compose interpolation.

## 16. Classpath file, external file và artifact đang chạy

Một nguyên nhân phổ biến là chỉnh đúng `src/main/resources/application.yml` trong repo nhưng ứng dụng thực tế chạy từ **JAR đã build trước đó**.

Ví dụ:

~~~text
Workspace:
  src/main/resources/application.yml  -> timeout 8s

Đang chạy:
  order-service.jar                   -> timeout 3s
~~~

Nếu không rebuild/redeploy, sửa workspace file không tự thay nội dung packaged resource đã nằm trong JAR.

Đường chẩn đoán:

1. Xác định version/image digest/JAR thực sự đang chạy.
2. Xác định file classpath mà artifact chứa tại thời điểm build.
3. Xác định có external Config Data đang ghi đè không.
4. Kiểm active profiles và các nguồn cao hơn.
5. Kiểm thời điểm process đã start so với thời điểm file bị sửa.

Không nói “đã sửa file, Spring không nhận” trước khi phân biệt **file nguồn** với **file nằm trong artifact**.

## 17. External configuration ngoài JAR

Spring Boot có thể lấy Config Data từ các vị trí bên ngoài JAR theo quy tắc tìm mặc định hoặc cấu hình location.

Ví dụ chạy:

~~~bash
java -jar order-service.jar \
  --spring.config.additional-location=optional:file:./config/
~~~

Nếu thư mục được nạp và chứa file cấu hình phù hợp, những property trong đó có thể tác động giá trị cuối. Với directory location, dấu `/` cuối đường dẫn có ý nghĩa trong cú pháp.

Các điểm cần kiểm:

- `./config/` được tính theo working directory của process nào?
- File ở đó có tên đúng `application.yml`/profile-specific name không?
- Có đặt `spring.config.name` hoặc location khác không?
- Import/optional location có tồn tại và đọc được không?
- Path trong container có thực sự được mount không?
- Có một nguồn ưu tiên cao hơn ghi đè giá trị không?

### spring.config.location và additional-location khác nhau

`spring.config.location` thay đổi cách chỉ định các vị trí cấu hình được xét theo semantics riêng; `spring.config.additional-location` bổ sung các vị trí vào chuỗi tìm kiếm. Không xem chúng như hai spelling tương đương.

Những thuộc tính điều khiển vị trí Config Data cần có **rất sớm** để Boot tìm được config files. Đặt chúng vào một file vốn chỉ được đọc sau khi đã xác định location có thể không có tác dụng như kỳ vọng. Ưu tiên cấp qua CLI, system property hoặc environment phù hợp.

## 18. spring.config.import và vị trí của source

Một file có thể import dữ liệu khác:

~~~properties
# application.properties
spring.config.import=optional:file:./config/client.properties
~~~

Tệp import:

~~~properties
# ./config/client.properties
app.client.timeout=7s
~~~

Boot đưa import vào Config Data theo quy tắc của framework. Khi hai tài liệu cùng khai báo một key, thứ tự và mức ưu tiên của imported document cần được xét; không mặc định nó có độ ưu tiên cao/ thấp tùy ý chỉ vì tên file.

Trong cách dùng Config Data của Spring Boot, **import có quy tắc ưu tiên so với tài liệu khai báo import**, đồng thời còn chịu ảnh hưởng bởi các nguồn khác như môi trường, CLI và profile. Khi truy vết, ghi rõ:

1. Tài liệu nào có `spring.config.import`?
2. Resource import đã được giải quyết đến đường dẫn nào?
3. File import có tồn tại và được nạp không?
4. Key ở file import có bị một PropertySource khác ghi đè không?
5. Có `optional:` khiến việc thiếu file được bỏ qua không?

Đừng sửa một YAML classpath mà quên import file đang thực sự cung cấp key thắng.

## 19. configtree và file được mount

Một container có thể mount secrets/config thành file dưới một directory:

~~~text
/run/secrets/
  app.client.timeout
  spring.datasource.password
~~~

Với:

~~~properties
spring.config.import=configtree:/run/secrets/
~~~

mỗi file có thể trở thành một property theo tên file. Ví dụ file `app.client.timeout` chứa `4s` sẽ cho key phù hợp.

**Origin của một property configtree liên quan resource được import**, không nhất thiết có “dòng YAML” theo kiểu `application.yml`.

Trong chẩn đoán:

- Kiểm chính xác tên file.
- Kiểm mount path ở **bên trong container**, không chỉ trên máy host.
- Kiểm quyền đọc của process.
- Kiểm container đã restart/refresh sau khi mount thay đổi chưa.
- Không in nội dung secret files.

`configtree:/run/secrets/` là cơ chế cấp Config Data, không tự bảo đảm Spring Boot thay mọi bean ngay khi file được cập nhật.

## 20. Trục 5 — Thời điểm giá trị được đọc

Đây là phần thường bị bỏ qua. Cùng một `Environment` nhưng các consumer có thể đọc giá trị ở những thời điểm khác nhau.

~~~text
Process khởi động
     |
     +-- Environment chuẩn bị
     |     - system properties
     |     - environment variables
     |     - Config Data load, profile resolution
     |
     +-- Bean definitions / configuration parsing
     |
     +-- @ConfigurationProperties bean được bind
     |     -> ClientProperties(timeout=2s)
     |
     +-- Service tạo ra
     |     -> có thể copy timeout vào một client object
     |
     +-- Ứng dụng nhận request
           -> dùng timeout đã được giữ
           -> hoặc đọc Environment mỗi lần
~~~

Một record:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(Duration timeout) {}
~~~

thường được bind khi bean được tạo trong quá trình khởi động context. Một service inject record rồi giữ tham chiếu đó:

~~~java
@Service
public class ClientService {
    private final ClientProperties properties;

    public ClientService(ClientProperties properties) {
        this.properties = properties;
    }

    public Duration configuredTimeout() {
        return properties.timeout();
    }
}
~~~

Khi file YAML bên ngoài được sửa sau startup, không thể mặc định `properties.timeout()` đổi ngay. Config Data thông thường **không phải file watcher** tự rebind bean.

## 21. Environment lookup tại thời điểm gọi khác snapshot ở bean

Đối chiếu hai cách:

**Cách A — đọc Environment mỗi lần:**

~~~java
@Service
public class DynamicLookupService {
    private final Environment env;

    public DynamicLookupService(Environment env) {
        this.env = env;
    }

    public String timeoutText() {
        return env.getProperty("app.client.timeout");
    }
}
~~~

**Cách B — dùng typed bean đã bind:**

~~~java
@Service
public class BoundConfigService {
    private final ClientProperties config;

    public BoundConfigService(ClientProperties config) {
        this.config = config;
    }

    public Duration timeout() {
        return config.timeout();
    }
}
~~~

Với A, method hỏi Environment mỗi lần. Nhưng nếu underlying PropertySources **không thay đổi**, A vẫn nhận giá trị cũ dù file host đã sửa.

Với B, method đọc giá trị của object đã tạo. Nếu underlying Environment thay đổi do một cơ chế custom, B vẫn có thể giữ snapshot cũ cho tới khi bean được refresh/rebind/recreate theo kiến trúc.

**Không suy luận “đọc mỗi lần” đồng nghĩa “reload file mỗi lần”.** Hai việc thuộc hai cơ chế khác nhau.

## 22. Khi service đã copy giá trị vào dependency khác

Một service có thể dùng cấu hình khi xây HTTP client:

~~~java
@Bean
WebClient remoteWebClient(
    WebClient.Builder builder,
    ClientProperties properties
) {
    return builder
        .baseUrl("https://api.example.test")
        .build();
}
~~~

Ví dụ chỉ minh họa lifecycle, chưa áp dụng timeout. Một client thực tế có thể cấu hình timeout lúc tạo underlying HTTP transport. Khi ấy:

- `ClientProperties` có thể thay đổi nếu có cơ chế rebind.
- Nhưng client object đã tạo có thể vẫn giữ timeout cấu hình từ lần khởi tạo đầu.
- Cần recreate/reconfigure client để áp dụng giá trị mới.

Điểm chẩn đoán là **thời điểm consumer chụp/copy giá trị**, không chỉ thời điểm Binder nhận value. Ngay cả khi `Environment.getProperty("app.client.timeout")` cho giá trị mới, một connection pool, scheduler hoặc HTTP client cũ có thể vẫn dùng cấu hình cũ.

## 23. Bean tạo sớm và PropertySource thêm muộn

Một số property được Spring Boot đọc rất sớm trong startup. Ví dụ các thiết lập điều khiển logging và `spring.main.*` thường được xét trước khi các bước cấu hình ứng dụng phía sau hoàn tất.

Nếu thêm một source muộn qua `@PropertySource` trong một `@Configuration`, source đó có thể được đưa vào context **quá muộn** đối với một số thiết lập được đọc ở giai đoạn đầu.

Một ví dụ cần cân nhắc:

~~~java
@Configuration
@PropertySource("classpath:custom.properties")
public class CustomConfiguration {}
~~~

Không xem `custom.properties` là nguồn thích hợp để điều khiển mọi thuộc tính startup sớm như thể nó đã được Config Data loader nạp trước. Nếu cần một key được đọc sớm, hãy chọn một nguồn mà Spring Boot nạp kịp ở giai đoạn chuẩn bị Environment.

**Khi debug, hỏi “ai đọc property này lần đầu?”**. Nếu hệ thống logging đã khởi tạo trước khi một source xuất hiện, thay đổi source về sau không tự áp dụng lại logging policy.

## 24. Spring profiles cũng được xác định ở giai đoạn đầu

`spring.profiles.active` có ý nghĩa đối với quyết định Config Data nào được nạp. Vì vậy, việc cố thay active profiles quá muộn trong một bean sau startup không tương đương với việc khởi động ứng dụng ngay từ đầu với profile đó.

Ví dụ:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

khác về thời điểm với một service gọi code động sau khi context đã sẵn sàng:

~~~java
System.setProperty("spring.profiles.active", "prod");
~~~

Lời gọi `System.setProperty` lúc runtime có thể làm JVM system property thay đổi, nhưng không tự yêu cầu Spring Boot **tải lại tất cả profile-specific Config Data và tạo lại bean graph**. Không dùng kỹ thuật này làm cơ chế profile switching động.

Cách an toàn: cấu hình profile **trước khi ứng dụng khởi động**, rồi restart/rollout có kiểm soát khi deployment cần chuyển profile.

## 25. Vì sao chỉnh file không tự refresh?

Giả sử process chạy lúc 09:00:

~~~text
09:00 - Spring Boot đọc application.yml, timeout=2s
09:01 - ClientProperties được tạo với timeout=2s
09:05 - Developer sửa application.yml thành timeout=8s
09:06 - Service vẫn có ClientProperties(timeout=2s)
~~~

Tình huống trên là bình thường khi không có cơ chế reload. Mô hình:

~~~text
Thay đổi file trên ổ đĩa
   != PropertySource được cập nhật
   != ConfigurationProperties bean được bind lại
   != HTTP client/pool được tạo lại
~~~

Nếu có Spring Boot DevTools trong môi trường phát triển, một số thay đổi có thể gây restart ứng dụng theo cơ chế DevTools; đó là **restart context**, không phải bằng chứng Binder hỗ trợ live reload của mọi file.

Nếu hệ thống dùng Spring Cloud Config, refresh endpoint, Kubernetes reload integration hoặc custom source watcher, phải mô tả chính xác cơ chế nào thay Environment, refresh scope, rebind bean và recreate dependent objects. Không giả định những tính năng này có sẵn trong Spring Boot lõi.

## 26. Ghi rõ thời gian của bằng chứng

Một báo cáo chẩn đoán nên ghi thời điểm đo:

~~~text
Process started: 09:00
Config file modified: 09:05
Environment lookup observed: 09:07
Bound properties observed: 09:07
Container recreated: No
Config refresh mechanism: None
~~~

Nếu hai người thu kết quả từ **hai container khác nhau** (rolling deployment), mỗi container có startup time, image version và Environment riêng. Không kết luận “Spring trả giá trị không nhất quán” khi đang so sánh instance cũ với instance mới.

Với Kubernetes hoặc Compose, ghi container ID/Pod name/revision theo quy trình vận hành, không cần in environment toàn bộ.

## 27. Một case tổng hợp: timeout sai trên production

Giả sử nguồn như sau:

~~~yaml
# application.yml
app:
  client:
    timeout: 5s
~~~

~~~yaml
# application-prod.yml
app:
  client:
    timeout: 8s
~~~

Container runtime:

~~~text
APP_CLIENT_TIMEOUT=2s
SPRING_PROFILES_ACTIVE=prod
~~~

Lệnh Java:

~~~bash
java -jar app.jar --app.client.timeout=500ms
~~~

Consumer:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(Duration timeout) {}
~~~

**Quy trình truy vết:**

1. **Key:** Java component `timeout` với prefix `app.client` yêu cầu `app.client.timeout`.
2. **Profile:** `prod` active, nên profile-specific file có thể tham gia.
3. **Nguồn:** file cơ sở 5s, file prod 8s, env 2s, CLI 500ms.
4. **Precedence:** CLI thắng các source thông thường còn lại trong tình huống này.
5. **Origin:** source thắng là application CLI; không có số dòng YAML của giá trị 500ms.
6. **Thời điểm:** Bean `ClientProperties` được bind lúc startup với `Duration.ofMillis(500)`.
7. **Kết luận:** sửa YAML prod không thay value khi CLI vẫn cấp 500ms. Cần sửa hoặc gỡ override cao hơn, rồi redeploy/restart phù hợp.

Không nên “fix” bằng cách đổi code để ép timeout tối thiểu nếu chính sách thời gian chờ thực sự chỉ bị triển khai sai. Tất nhiên, validation nghiệp vụ như giới hạn timeout tối thiểu có thể được bổ sung riêng.

## 28. Trường hợp profile sai, không phải precedence sai

Một tình huống khác:

~~~yaml
# application-staging.yml
app:
  client:
    timeout: 7s
~~~

Khi chạy, `environment.getActiveProfiles()` chỉ trả `[dev]`. Developer kỳ vọng staging timeout `7s` nhưng app nhận `3s` từ file cơ sở.

Đây trước hết là lỗi **profile selection**, không phải một source staging bị source dev ghi đè trong mọi trường hợp. File staging có thể không được nạp.

Kiểm tra:

- Có biến `SPRING_PROFILES_ACTIVE=staging` thật trong container không?
- Compose file `.env` chỉ có `APP_PROFILE=staging` nhưng chưa truyền sang `SPRING_PROFILES_ACTIVE`?
- Command line có `--spring.profiles.active=dev` cao hơn env?
- Một profile group hoặc logic startup khác có ảnh hưởng?
- Process đang chạy có phải instance vừa deploy hay container cũ?

Dù tên file có `staging`, nó chỉ là ứng viên khi Spring chọn tài liệu đó theo quy tắc Config Data.

## 29. Trường hợp Origin trỏ sang file ngoài JAR

Giả sử repo có:

~~~text
src/main/resources/application.yml
  app.client.timeout: 3s
~~~

Nhưng container mount:

~~~text
/etc/order-config/application.yml
  app.client.timeout: 9s
~~~

và Spring Boot được cấu hình nạp external location phù hợp. Nếu source ngoài JAR thắng, origin có thể chỉ ra resource `file:/etc/order-config/application.yml`.

Đừng sửa packaged file trong repository rồi mong thời gian chờ đổi nếu runtime đang nhận source khác. Hãy xác định:

1. Mount path host → container.
2. Config location trong command/env.
3. Thứ tự source thực tế.
4. Permission và file content **không nhạy cảm**.
5. Có khởi động lại process sau khi file đổi không.

Nếu source chỉ có tên file nhưng không có origin line metadata, vẫn có thể dùng URL/path đó làm điểm khởi đầu, rồi kiểm file cụ thể bằng công cụ vận hành được phép.

## 30. Trường hợp placeholder làm khó đọc raw value

File:

~~~yaml
app:
  client:
    timeout: "\${CLIENT_TIMEOUT:2s}"
~~~

Một source có thể chứa raw text `\${CLIENT_TIMEOUT:2s}`, nhưng khi Spring giải quyết placeholder nó có thể trở thành `5s` nếu `CLIENT_TIMEOUT=5s` có trong Environment.

Vì vậy có thể có sự khác nhau:

- `PropertySource.getProperty("app.client.timeout")`: value gốc hoặc value được source cung cấp.
- `Environment.getProperty("app.client.timeout")`: value sau cơ chế resolver/placeholder phù hợp.
- `Binder.bind(...)`: typed value sau binding/conversion.
- Bean `ClientProperties.timeout()`: value đã bind khi bean được tạo.

Một cách debug đúng là tách **nơi placeholder được viết** với **nguồn biến mà placeholder tham chiếu**. Nếu `CLIENT_TIMEOUT` thiếu, fallback `2s` không phải một giá trị “thắng file staging”; đó là default ở biểu thức placeholder.

Nếu placeholder không thể giải quyết và không có fallback, lỗi có thể xuất hiện ở cơ chế resolution/binding tùy context, không chỉ conversion.

## 31. Trường hợp list và map có semantics khác scalar

Một key scalar có thể được override riêng lẻ. Nhưng với `@ConfigurationProperties`, **list thường được thay thế bởi list từ PropertySource có ưu tiên cao hơn**, không deep merge từng index theo kỳ vọng.

File cơ sở:

~~~yaml
app:
  gateways:
    - name: primary
      timeout: 2s
    - name: secondary
      timeout: 5s
~~~

Một nguồn cao hơn chỉ khai báo:

~~~properties
app.gateways[0].timeout=1s
~~~

Không nên mặc định rằng kết quả là primary timeout 1s nhưng vẫn giữ mọi field của cả primary và secondary từ file gốc. Có thể xảy ra list replacement, thiếu trường hoặc phần tử.

Khi truy vết collection:

1. Tìm property **root của list**, không chỉ field leaf.
2. Xác định nguồn nào cung cấp list cao ưu tiên.
3. Kiểm toàn bộ shape và index của list trong nguồn đó.
4. Kiểm nested conversion và validation.
5. Nếu muốn merge theo identifier, xem xét `Map<String,Gateway>`.

**Một property leaf có vẻ được “override đúng” chưa chứng minh cấu trúc list cuối cùng đúng.**

## 32. Phân biệt bind sai, convert sai và validate sai

Sau khi biết key/source/profile/origin/time, vẫn có thể thất bại ở bước bind:

| Loại vấn đề | Ví dụ | Hướng sửa |
| --- | --- | --- |
| Sai key hoặc shape | `app.gateway.timeout` nhưng Java cần `app.gateways[0].timeout` | Sửa cấu trúc/tên property |
| Conversion | `app.client.timeout=soon` nhưng Java cần `Duration` | Sửa format value |
| Validation | `timeout=0s` nhưng policy yêu cầu thời gian dương | Sửa value hoặc constraint |
| Bean registration | Record có `@ConfigurationProperties` nhưng chưa scan/enable | Đăng ký typed bean đúng cơ chế |
| Consumer cache | Environment mới nhưng client cũ | Recreate/rebind/restart thích hợp |

Lỗi conversion hoặc validation có thể được **bọc trong `BindException`/`ConfigurationPropertiesBindException`**. Vì vậy, tìm `Reason` và root cause của exception, không kết luận mọi dòng “Failed to bind properties” đều là YAML sai.

Nếu key sai nhưng `ignoreUnknownFields` cho phép bỏ qua, app có thể không fail startup; cần validation và test để phát hiện những field bắt buộc bị thiếu.

## 33. Actuator env để xem nguồn và property

Spring Boot Actuator có endpoint `env`, hữu ích cho điều tra môi trường và nguồn cấu hình khi được bật **với bảo vệ thích hợp**.

Để nghiên cứu một property không nhạy cảm trong môi trường test, endpoint có thể hỗ trợ truy vấn theo tên:

~~~text
GET /actuator/env/app.client.timeout
~~~

Tùy Spring Boot version và cấu hình, response có thể thể hiện nguồn, value được sanitize, hoặc thông tin origin liên quan. Endpoint không thay thế việc kiểm consumer đã bind và giữ snapshot hay chưa.

**Security là bắt buộc trong tư duy vận hành:**

- Không đưa `env` ra Internet công khai.
- Chỉ expose cho người vận hành được ủy quyền.
- Bảo vệ bằng authentication, authorization và giới hạn network.
- Cẩn trọng với endpoint names, property sources và origin metadata.
- Không đặt `show-values=always` bừa bãi trên production.

Một lựa chọn cấu hình để không hiển thị giá trị:

~~~properties
management.endpoint.env.show-values=never
~~~

Nếu cần thấy value ở môi trường test, phải xác định quyền truy cập, data classification và những tùy chọn được phiên bản Spring Boot đang chạy hỗ trợ. **Masking không có nghĩa endpoint an toàn để public**.

## 34. Actuator configprops để xem typed configuration

Endpoint `configprops` của Actuator giúp quan sát các bean `@ConfigurationProperties` đã được bind, có thể đi kèm metadata inputs theo phiên bản và cấu hình.

~~~text
GET /actuator/configprops
~~~

Dùng nó để trả lời câu hỏi khác với `env`:

- `env`: Environment đang có những property candidates/sources nào?
- `configprops`: các configuration properties beans được bind với cấu trúc nào, ở ngữ cảnh quan sát nào?

Trong nhiều ứng dụng, typed bean chứa secret. Đừng bật hiển thị toàn bộ values chỉ để debug một timeout. Có thể đặt:

~~~properties
management.endpoint.configprops.show-values=never
~~~

và bảo vệ endpoint. `never` là lựa chọn bảo thủ cho một môi trường chưa được đánh giá an toàn.

**So sánh env với configprops có thể gợi ý khác biệt thời điểm bind**, nhưng diễn giải phải xét cơ chế caching, refresh, bean lifecycle và cách Actuator thu thập dữ liệu ở phiên bản cụ thể.

## 35. Khi không thể bật Actuator

Không phải hệ thống nào cũng có Spring Boot Actuator, và production có thể không cho phép expose các endpoint chẩn đoán. Thay thế:

1. Tạo test context riêng với đúng property input của một môi trường.
2. Chỉ log một **allowlist key không nhạy cảm** trong startup thử nghiệm.
3. Duyệt source name của một key qua `ConfigurableEnvironment`.
4. Sử dụng failure analyzer khi startup bị lỗi.
5. Kiểm deployment spec để xác nhận env/CLI/mount thật.
6. So sánh artifact version và process start time.

Ví dụ log thông tin không nhạy cảm:

~~~java
log.info(
    "springProfiles={}, clientTimeoutPresent={}",
    Arrays.toString(env.getActiveProfiles()),
    env.containsProperty("app.client.timeout")
);
~~~

Không log `System.getenv()`, `getSystemProperties()`, toàn bộ `PropertySources` hoặc `@ConfigurationProperties` record chứa password/token.

## 36. Kiểm thử precedence với ApplicationContextRunner

Một context test nhỏ có thể minh họa việc property input cao hơn default file trong test hoặc giá trị được bind.

Ví dụ record:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(Duration timeout) {}
~~~

Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class ClientBindingTest {
    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(Config.class);

    @Test
    void bindsExplicitValue() {
        runner
            .withPropertyValues("app.client.timeout=500ms")
            .run(context -> {
                assertThat(context).hasNotFailed();
                ClientProperties props =
                    context.getBean(ClientProperties.class);
                assertThat(props.timeout())
                    .isEqualTo(Duration.ofMillis(500));
            });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(ClientProperties.class)
    static class Config {}
}
~~~

Test này chứng minh **một value được bind và convert đúng** trong context test. Nó chưa chứng minh production profile hoặc external file thực tế đã được nạp. Muốn kiểm Config Data và active profiles, dùng integration test/setup tương ứng.

## 37. Kiểm active profile bằng integration test

Một test dùng `@ActiveProfiles`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.core.env.Environment;

@SpringBootTest
@ActiveProfiles("prod")
class ProdProfileTest {
    @Autowired
    Environment environment;

    @Test
    void expectedProfileIsActive() {
        assertThat(environment.getActiveProfiles())
            .contains("prod");
    }
}
~~~

Test này xác nhận Spring Test context active `prod` theo cấu hình test; không tự chứng minh **deployment ngoài test** đang active cùng profile.

Có thể inject `ClientProperties` và assert timeout mong đợi trong test khi sources được setup nhất quán. Nếu test có `@SpringBootTest(properties=...)`, chính test property có thể override file khác, nên ghi rõ những overrides dùng trong test.

## 38. Tạo ma trận thử nghiệm năm trục

| Case | Key | Source | Profile | Origin | Thời điểm |
| --- | --- | --- | --- | --- | --- |
| A | `app.client.timeout` | application.yml | default | classpath resource | startup |
| B | `app.client.timeout` | application-prod.yml | prod | profile resource | startup |
| C | `app.client.timeout` | OS env | prod | environment source | startup |
| D | `app.client.timeout` | CLI | prod | commandLineArgs | startup |
| E | `app.client.timeout` | mounted file | prod | external file | startup |
| F | `app.client.timeout` | Config Data import | prod | imported resource | startup |
| G | `app.client.timeout` | same source, file edited | prod | file mới | after startup, chưa refresh |
| H | `app.client.timeout` | Environment thay đổi | prod | dynamic source | consumer đọc lại hoặc giữ snapshot |

Mục tiêu của bảng không phải giả định mọi case tạo khác biệt, mà là **cô lập một biến điều kiện tại một thời điểm**. Khi xác định được source thắng ở case D, thử bỏ CLI override để xem source thắng kế tiếp là gì trong một môi trường thử nghiệm an toàn; không thay production ngay để thử mò.

## 39. Khi một giá trị đến từ Docker Compose

Một trường hợp deployment:

~~~dotenv
# .env - Compose interpolation
CLIENT_TIMEOUT=5s
~~~

~~~yaml
services:
  api:
    environment:
      APP_CLIENT_TIMEOUT: "\${CLIENT_TIMEOUT:-3s}"
~~~

Giá trị `CLIENT_TIMEOUT` do Compose lấy từ môi trường CLI và đưa thành container env `APP_CLIENT_TIMEOUT`. Spring Boot có thể bind `app.client.timeout` từ key container đó.

Nếu Compose YAML không khai báo `environment` hoặc `env_file` tương ứng, file `.env` đơn lẻ **không đưa biến vào container**.

Dấu hiệu chẩn đoán:

- Biến trên host có đúng nhưng container thiếu: kiểm Compose interpolation vs service runtime environment.
- Container có biến nhưng Spring lấy khác: kiểm Spring precedence, CLI và profiles.
- Spring có biến mới nhưng bean vẫn cũ: kiểm startup time/refresh.
- Bean mới nhưng HTTP client vẫn cũ: kiểm thời điểm consumer copy settings.

Đây là ví dụ điển hình cho lý do phải truy vết **đến tận consumer**, không dừng ở một file.

## 40. Khi JVM -D và Spring --arg cùng tồn tại

Lệnh:

~~~bash
java -Dapp.client.timeout=3s \
  -jar order-service.jar \
  --app.client.timeout=500ms
~~~

`-Dapp.client.timeout=3s` trước `-jar` là Java system property. `--app.client.timeout=500ms` sau JAR là Spring Boot application argument, khi command-line properties được bật.

Trong cấu hình mặc định thông thường của Spring Boot, CLI property có ưu tiên cao hơn JVM system property, nên value cuối `500ms`.

Một lỗi cú pháp:

~~~bash
java -jar order-service.jar -Dapp.client.timeout=3s
~~~

`-D...` **sau** `-jar` là application argument, không còn được Java launcher xử lý thành JVM system property. Không nên nghĩ nó tương đương với lệnh đúng. Nếu ứng dụng không tự parse argument kiểu này, property có thể không được áp dụng như mong muốn.

Cần ghi lại **lệnh thực sự chạy** trong container/service manager, không chỉ JVM options mà developer tưởng đã cấu hình.

## 41. Khi @Value và @ConfigurationProperties cho kết quả không như nhau

Một component dùng:

~~~java
@Value("\${app.client.timeout:2s}")
private Duration timeout;
~~~

Bean khác dùng:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(Duration timeout) {}
~~~

Có thể khác nhau vì:

- `@Value` có placeholder fallback `2s`, model record có thể không có default.
- Hai consumer được tạo ở thời điểm khác nhau khi Environment thay đổi.
- Đường conversion của Spring Core `@Value` không hoàn toàn giống Binder chuyên dụng trong mọi tình huống.
- Một consumer giữ snapshot; consumer khác đọc lại Environment.
- Một field được cấu hình qua Java default, không phải PropertySource.

Đừng suy ra Spring Boot “chọn hai nguồn khác nhau” chỉ vì hai giá trị khác nhau. Kiểm **cách mỗi consumer nhận cấu hình** trước.

## 42. Trường hợp custom PropertySource

Một thư viện có thể thêm nguồn ngoài bằng `EnvironmentPostProcessor` hoặc programmatically sửa `MutablePropertySources` theo cơ chế lifecycle phù hợp. Khi đó tên và vị trí của source trong danh sách ảnh hưởng kết quả.

Ví dụ khái niệm:

~~~java
ConfigurableEnvironment env = ...;
PropertySource<?> custom = ...;

env.getPropertySources().addFirst(custom);
~~~

Đây là pseudo-code để minh họa ý tưởng, không phải cấu hình khuyến nghị sao chép nguyên vào production. `addFirst` đặt source ở ưu tiên cao trong MutablePropertySources hiện tại. Một module khác cũng có thể thêm source theo thứ tự khác.

Hỏi:

- Source được thêm lúc nào?
- Nó nằm trước hay sau system environment/config data?
- Source có key theo canonical spelling không?
- Nó có origin metadata không?
- Binder đã được gọi trước hay sau khi source được thêm?
- Có caching hoặc snapshots ở consumer không?

Một số property do Spring Boot đọc quá sớm; thêm source lúc context refresh không nhất thiết thay được những quyết định đó.

## 43. Cách đọc thông báo Failed to bind có Origin

Ví dụ startup failure giả định:

~~~text
Failed to bind properties under 'app.client.timeout'
to java.time.Duration:

    Property: app.client.timeout
    Value: "someday"
    Origin: file [./config/application-prod.yml] - 12:16
    Reason: failed to convert String to Duration
~~~

Quy trình:

1. Property cho biết **key** cần sửa.
2. Target type cho biết cần **Duration**.
3. Value `someday` không phải định dạng Duration hợp lệ.
4. Origin chỉ vị trí **file external production**, không phải `src/main/resources/application.yml`.
5. Profile và Config Data quyết định vì sao file external đó được nạp.
6. Startup failure chứng tỏ lỗi xuất hiện khi bind; không cần tìm một “refresh bug” sau startup.
7. Sửa value ở nguồn thắng thành thời lượng hợp lệ như `2s` hoặc `500ms` theo nhu cầu thực.

Không in value nếu property có thể chứa secret; chú trọng key, target type và reason đã được làm sạch.

## 44. Quy trình truy vết 15 bước có thể áp dụng ngay

1. **Xác định lỗi quan sát được** và consumer: controller, datasource, HTTP client, scheduler, config record?
2. **Chốt key canonical**, prefix và Java target type.
3. **Liệt kê default** có thể đến từ `@Value` placeholder, `@DefaultValue`, field initializer hoặc caller fallback.
4. **Xác nhận process/Pod/container** thực sự đang chạy, image/JAR version và start time.
5. **Đọc active/default profiles** từ `Environment` thực, không từ tên environment.
6. **Liệt kê source candidates** cho key không nhạy cảm qua `PropertySources` hoặc công cụ chẩn đoán được bảo vệ.
7. **Xác định source thắng** theo thứ tự runtime, không suy diễn chỉ từ file.
8. **Lấy origin** nếu source hỗ trợ; nếu không, ghi “không có origin”.
9. **Kiểm Config Data locations**: packaged, external, import, configtree, profile-specific.
10. **Kiểm host/container/CI variable**: đã thực sự được truyền vào process hay chỉ dùng để Compose nội suy?
11. **Kiểm command-line và JVM -D** có ghi đè không; để ý vị trí `-D`.
12. **Kiểm placeholder resolution**, conversion sang kiểu và constraint validation.
13. **Kiểm thời điểm đọc**: startup snapshot, method đọc Environment, bean được refresh, dependency đã copy config.
14. **Tái hiện bằng test nhỏ** hoặc môi trường staging an toàn, chỉ thay một điều kiện mỗi lần.
15. **Sửa đúng nguồn và đúng lifecycle**, redeploy/restart/recreate component khi cần; xác nhận trên đúng instance.

Ghi kết quả có bằng chứng ở mỗi bước. Không cần mở/đổ toàn bộ environment ra log. Khi một bước chưa thể xác nhận, đánh dấu rõ “chưa biết” thay vì điền kết luận.

## 45. Checklist nhanh theo triệu chứng

| Triệu chứng | Kiểm đầu tiên |
| --- | --- |
| App không thấy key | Prefix, spelling, PropertySources, missing source |
| File prod có value nhưng app nhận file dev | Active profiles thực tế |
| YAML đúng nhưng value runtime khác | CLI, `-D`, OS env, imports và external config |
| Actuator env cho value mới, bean còn cũ | Thời điểm bind/refresh |
| Bean mới nhưng HTTP client vẫn cũ | Dependency đã copy config lúc tạo |
| Source name là systemEnvironment | Cấp biến ở container/OS nào |
| Config source là external file không quen | `spring.config.location`, `additional-location`, import |
| Origin không có số dòng | Source không hỗ trợ file/line origin |
| CLI làm value thành 500ms | Kiểm startup arguments thực tế |
| `@Value` có 2s nhưng Binder không có | Placeholder default khác model default |
| Đổi file sau startup không tác dụng | Config Data startup load; thiếu refresh |
| Thêm `@PropertySource` nhưng logging không đổi | Property được đọc quá sớm |
| List bị mất phần tử | List replacement/PropertySource precedence |
| Value hiện diện nhưng BindException | Conversion, shape hoặc validation root cause |
| Container không nhận biến từ `.env` | Compose interpolation không đồng nghĩa runtime env |
| Hai Pod trả hai timeout khác nhau | So start time, image revision, env và rollout |

## 46. Bài tập 1 — Truy vết giá trị thắng

Có:

~~~text
application.yml: app.client.timeout=5s
application-prod.yml: app.client.timeout=8s
APP_CLIENT_TIMEOUT=2s
CLI: --app.client.timeout=500ms
Active profile: prod
~~~

**Hỏi:** giá trị `Duration timeout` là gì theo precedence thông thường?

**Đáp án:** `Duration.ofMillis(500)`. CLI thắng các nguồn còn lại trong tình huống minh họa. File prod có được nạp không không thay đổi kết quả cuối khi CLI vẫn cao ưu tiên.

## 47. Bài tập 2 — File tồn tại nhưng profile không active

~~~text
application-staging.yml có timeout 7s
Environment.getActiveProfiles() -> [dev]
~~~

**Hỏi:** tại sao Spring không lấy 7s?

**Đáp án:** chưa có bằng chứng file staging được chọn theo Config Data. Cần active profile phù hợp hoặc cách load tệp được cấu hình có chủ đích, không chỉ tạo tệp.

## 48. Bài tập 3 — Source có nhưng bean không đổi

~~~text
09:00: bean bind timeout=2s
09:05: external file sửa thành 8s
09:06: bean vẫn cho 2s
~~~

**Đáp án:** đây có thể là snapshot startup bình thường. File đổi không tự thay PropertySource, rebind bean hay recreate consumer. Xác định cơ chế reload thực có tồn tại không trước khi chẩn đoán lỗi.

## 49. Bài tập 4 — Có key trong .env nhưng container không có

~~~dotenv
# .env
APP_CLIENT_TIMEOUT=5s
~~~

~~~yaml
services:
  api:
    image: example/app:local
~~~

**Đáp án:** file `.env` mặc định phục vụ Compose interpolation, không tự inject toàn bộ key. Cần `environment` hoặc `env_file` ở service theo ý định triển khai.

## 50. Bài tập 5 — JVM option sai vị trí

~~~bash
java -jar app.jar -Dapp.client.timeout=1s
~~~

**Đáp án:** JVM launcher không nhận `-D` ở vị trí này như system property; sau `-jar` nó là application argument. Đặt `-Dapp.client.timeout=1s` trước `-jar` hoặc dùng Spring CLI property `--app.client.timeout=1s` sau JAR.

## 51. Bài tập 6 — Origin trỏ tới file import

~~~properties
spring.config.import=file:./config/client.properties
~~~

File import khai báo `app.client.timeout=7s`. File gốc khai báo `2s`.

**Đáp án:** cần xét Config Data import precedence; trong quy tắc import của Spring Boot, imported file có thể thắng tài liệu khai báo import. Nhưng vẫn phải kiểm có CLI/env/system property cao ưu tiên hơn không, và file thực sự tồn tại/được load hay chưa.

## 52. Bài tập 7 — Raw value khác resolved value

~~~yaml
app:
  client:
    timeout: "\${CLIENT_TIMEOUT:2s}"
~~~

Environment có `CLIENT_TIMEOUT=9s`.

**Đáp án:** file có placeholder raw, Spring có thể giải quyết thành `9s`, Binder chuyển thành Duration. Đừng nhầm raw text trong resource với value cuối trong bean.

## 53. Bài tập 8 — Lỗi do list replacement

File cơ sở có hai gateways. Một nguồn cao hơn chỉ khai báo `app.gateways[0].timeout=1s`.

**Đáp án:** không mặc định giữ đủ hai gateways và nested fields của nguồn thấp hơn. Với Binder list, cần xem toàn bộ source thắng và semantics thay thế list.

## 54. Bài tập 9 — Custom source thêm muộn

App cần thay `logging.level.root`. Một `@PropertySource` được thêm trong configuration parsing giai đoạn sau.

**Đáp án:** nguồn có thể đến quá muộn để tác động việc khởi tạo logging ban đầu. Dùng nguồn config được nạp sớm phù hợp thay vì cho rằng mọi PropertySource đều có hiệu lực ở cùng thời điểm.

## 55. Bài tập 10 — Secret và debugging

Một developer muốn in `System.getenv()` và tất cả `PropertySources` để thấy database password.

**Đáp án:** không nên. Các output đó có thể lộ token/password và dữ liệu nhạy cảm. Truy vết **tên key, source name, existence, origin được phân quyền**, và dùng secret manager/audit theo quy trình thay vì dump value.

## 56. Bảng ghi nhớ cuối bài

| Câu hỏi | Nơi/khái niệm cần xem |
| --- | --- |
| Key chuẩn là gì? | Prefix `@ConfigurationProperties` + Java component + canonical naming |
| Biến môi trường tương ứng? | Relaxed binding/`APP_CLIENT_TIMEOUT` |
| Nguồn nào đang thắng? | `ConfigurableEnvironment.getPropertySources()`, precedence |
| Value Environment trả lúc này? | `Environment.getProperty(key)` |
| Profile nào active? | `Environment.getActiveProfiles()` |
| Default profile? | `Environment.getDefaultProfiles()` |
| File YAML nào được chọn? | Config Data, profile-specific resources, imports |
| Origin file/dòng? | Failure analysis, `OriginLookup` khi source hỗ trợ |
| External location ở đâu? | `spring.config.location`, `spring.config.additional-location` |
| Một import có được load? | `spring.config.import` và resource location |
| File-mounted config? | `configtree:` hoặc file Config Data |
| Value đã convert sang Java chưa? | Binder/`@ConfigurationProperties` |
| Bean giữ giá trị khi nào? | Bean creation/bind time |
| Consumer còn dùng snapshot cũ? | Dependency lifecycle và caching |
| Có tự reload khi sửa file? | Thông thường không; cần cơ chế refresh/restart |
| Có thể debug qua Actuator? | `env` và `configprops` được bảo vệ/sanitize |
| CLI đang override? | `--key=value` sau JAR |
| JVM system property đúng vị trí? | `-Dkey=value` trước `-jar` |
| Compose .env có vào container? | Không tự động, cần `environment`/`env_file` |
| Key là secret? | Không in raw value, hạn chế origin/metadata |

## 57. Kết luận

Để chẩn đoán một giá trị Spring Boot đang “khác file”, hãy luôn đi theo thứ tự:

**Khóa chính xác → nguồn ứng viên và nguồn thắng → profile quyết định tài liệu được nạp → origin của value → thời điểm Environment, Binder và consumer đọc giá trị.**

Năm trục này giúp tránh các hướng sửa sai: đổi YAML trong khi CLI đang override, kích hoạt nhầm profile, sửa file không nằm trong artifact, bỏ qua Config Data import, hoặc mong một bean immutable tự cập nhật khi mounted file thay đổi. Khi đã xác định được một key, source thắng và thời điểm chụp value, việc sửa thường trở thành một thay đổi cấu hình có thể chứng minh, kiểm thử và triển khai an toàn — thay vì một chuỗi thử nghiệm không có cơ sở.

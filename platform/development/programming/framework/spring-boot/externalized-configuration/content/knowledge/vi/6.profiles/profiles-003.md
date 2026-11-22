# Profile mặc định và thuộc tính `spring.profiles.default` trong Spring Boot 3.3

## 1. Vì sao cần hiểu default profile?

Spring Boot sử dụng **profile** để chọn cấu hình và bean phù hợp cho từng môi trường chạy, chẳng hạn `dev`, `test`, `staging` hoặc `prod`. Khi có ít nhất một **active profile**, Spring Boot xét các file như `application-dev.yaml` hay `application-prod.properties` và các điều kiện `@Profile` tương ứng.

Nhưng điều gì xảy ra khi **không có active profile nào được khai báo**? Spring Framework có một tập **default profiles** để dùng làm phương án dự phòng. Spring Boot 3.3 mặc định đặt tập này thành `[default]`, nghĩa là profile mang tên `default` được xét trong tình huống không có active profile.

Có thể tùy chỉnh tên mặc định đó bằng property:

```properties
spring.profiles.default=local
```

Đây là chủ đề của bài viết: phân biệt **active profiles** với **default profiles**, hiểu chính xác lúc nào `spring.profiles.default` có tác dụng, khi nào `application-default.*` hoặc `application-local.*` được nạp, cách khai báo hợp lệ và cách kiểm tra ở runtime.

**Quy tắc nền tảng:**

> Nếu có ít nhất một active profile thì Spring sử dụng các active profiles. Nếu không có active profile, tập default profiles được dùng để kiểm tra điều kiện profile; theo mặc định tập đó chứa tên `default`.

**Default profile không phải môi trường “an toàn”, “development” hay “production” theo một chuẩn ngầm định.** `default` chỉ là tên profile dự phòng. Nội dung của nó do chính dự án quyết định.

## 2. Ba khái niệm phải tách bạch

| Khái niệm | Định nghĩa | Ví dụ |
| --- | --- | --- |
| **Active profiles** | Các profile được kích hoạt rõ ràng qua cấu hình, command line, API hoặc cơ chế bổ sung profile | `dev`, `prod`, `test` |
| **Default profiles** | Tập profile thay thế khi **không có active profile** | Mặc định `[default]`; có thể thay bằng `[local]` |
| **Profile-specific configuration** | File hoặc tài liệu cấu hình chỉ tham gia khi profile tương ứng được chấp nhận | `application-default.yaml`, `application-prod.properties`, tài liệu có `spring.config.activate.on-profile` |

Spring Environment có các phương thức liên quan:

```java
String[] activeProfiles = environment.getActiveProfiles();
String[] defaultProfiles = environment.getDefaultProfiles();
```

Ví dụ ứng dụng chưa đặt `spring.profiles.active`:

```text
getActiveProfiles()  -> []
getDefaultProfiles() -> ["default"]
```

Sau khi đặt `spring.profiles.default=local` trong cấu hình chung:

```text
getActiveProfiles()  -> []
getDefaultProfiles() -> ["local"]
```

Khi chạy với `--spring.profiles.active=prod`, dù vẫn cấu hình default là `local`:

```text
getActiveProfiles()  -> ["prod"]
getDefaultProfiles() -> ["local"]
```

Ở tình huống cuối, `local` còn nằm trong danh sách **default profiles** nhưng **không được dùng làm phương án dự phòng**, vì đã có active profile `prod`. Do đó không thể nhìn riêng `getDefaultProfiles()` rồi kết luận profile đó đang có hiệu lực cho các điều kiện `@Profile`.

## 3. Hành vi mặc định khi không cấu hình gì

Giả sử ứng dụng có ba tệp tại `src/main/resources`:

```text
src/main/resources/
├── application.yaml
├── application-default.yaml
└── application-prod.yaml
```

Nội dung của chúng:

**`application.yaml`**:

```yaml
app:
  greeting: "Hello from common config"
  timeout: 3s
```

**`application-default.yaml`**:

```yaml
app:
  greeting: "Hello from default profile"
```

**`application-prod.yaml`**:

```yaml
app:
  greeting: "Hello from production"
  timeout: 10s
```

Khởi chạy mà **không** cung cấp active profile:

```bash
java -jar myapp.jar
```

Theo cấu hình profile thông thường của Boot 3.3:

- `application.yaml` luôn là tài liệu cấu hình chung nếu nằm ở location đang được tìm.
- Không có active profile nên tập default profiles `[default]` được sử dụng.
- `application-default.yaml` được xét như file profile-specific của profile `default`.
- `application-prod.yaml` không được xét chỉ vì file đó hiện diện.

Kết quả giả định không có nguồn ưu tiên cao hơn ghi đè:

```text
app.greeting = Hello from default profile
app.timeout  = 3s
```

Vì file `application-default.yaml` không khai báo `app.timeout` nên giá trị chung `3s` vẫn còn hiệu lực. File profile-specific có thể ghi đè các property trùng khóa của cấu hình chung.

**Lưu ý:** `application-default.yaml` không phải file mặc định luôn được nạp. Nó chỉ tham gia khi profile `default` được chấp nhận, chủ yếu trong trường hợp không có active profile và default profile vẫn mang tên `default`.

## 4. `spring.profiles.default`: đổi tập profile dự phòng

### 4.1. Khai báo trong `application.properties`

```properties
# application.properties — tài liệu không đặc thù profile
spring.profiles.default=local
```

Khi không có active profile, Spring Boot dùng `local` thay cho `default`. Vì vậy các cấu hình profile-specific như `application-local.properties` hoặc `application-local.yaml` có thể được xét.

Ví dụ:

```text
src/main/resources/
├── application.properties
├── application-local.properties
├── application-default.properties
└── application-prod.properties
```

```properties
# application.properties
spring.profiles.default=local
app.mode=common
```

```properties
# application-local.properties
app.mode=local-fallback
```

```properties
# application-default.properties
app.mode=old-default
```

Khi chạy `java -jar myapp.jar`, kết quả `app.mode=local-fallback`, vì tập default profiles là `[local]`. Sự hiện diện của file `application-default.properties` không khiến nó được nạp nếu `default` không còn là profile được chấp nhận.

### 4.2. Khai báo tương đương trong YAML

```yaml
# application.yaml
spring:
  profiles:
    default: local
```

Cú pháp YAML là ánh xạ lồng nhau, tương đương property phẳng `spring.profiles.default=local`. Nên dùng một định dạng cấu hình rõ ràng tại mỗi location, vì khi cùng location có cả `application.properties` và YAML, Spring Boot có quy tắc ưu tiên định dạng có thể gây bất ngờ.

### 4.3. Nhiều default profiles

Default profiles là một **tập tên profile**, không nhất thiết chỉ một tên. Có thể cấu hình danh sách phân tách bằng dấu phẩy:

```properties
spring.profiles.default=local,metrics
```

Hoặc:

```yaml
spring:
  profiles:
    default: local,metrics
```

Nếu không có active profile, cả `local` và `metrics` thuộc tập fallback, nên các file `application-local.*` và `application-metrics.*` có thể tham gia nạp. Khi hai profile cùng cung cấp một property, thứ tự giữa các file profile-specific chịu quy tắc precedence của Config Data, bao gồm nguyên tắc profile sau có thể ghi đè profile trước **trong cùng location group**.

Điều này **không có nghĩa** mọi nguồn có default profile sẽ cộng dồn danh sách. `spring.profiles.default` là một property thông thường chịu thứ tự ưu tiên PropertySource; nếu được khai báo khác nhau ở nhiều nơi, giá trị có ưu tiên cao hơn được dùng.

### 4.4. Các nguồn cung cấp property

Có thể đặt `spring.profiles.default` ở:

**File cấu hình chung:**

```properties
spring.profiles.default=local
```

**Command-line option:**

```bash
java -jar myapp.jar --spring.profiles.default=local
```

**JVM system property:**

```bash
java -Dspring.profiles.default=local -jar myapp.jar
```

**Biến môi trường:**

```bash
SPRING_PROFILES_DEFAULT=local java -jar myapp.jar
```

Với Docker Compose hay Kubernetes, có thể khai báo `SPRING_PROFILES_DEFAULT` như một environment variable của container trước khi tiến trình Java khởi chạy. Mục đích là định nghĩa **fallback** cho những lần chạy không cung cấp `spring.profiles.active`.

Khác với các property xác định đường tìm file như `spring.config.name` hay `spring.config.location`, `spring.profiles.default` **được phép nằm trong tài liệu Config Data chung** như `application.properties`/`application.yaml`; Spring Boot xử lý thông tin profile trong giai đoạn Config Data và có quy tắc xác định các file theo profile.

## 5. `spring.profiles.default` khác `spring.profiles.active` như thế nào?

Hai property có vai trò khác nhau:

- `spring.profiles.active=prod`: **chọn profile đang hoạt động rõ ràng** là `prod`.
- `spring.profiles.default=local`: **chỉ chọn profile dự phòng** là `local` khi không có active profile.

Ví dụ cấu hình chung:

```properties
spring.profiles.default=local
app.name=inventory-service
```

**Trường hợp A — không truyền active profile**

```bash
java -jar myapp.jar
```

Khi đó `local` là fallback. Nếu có `application-local.properties`, file đó có thể tham gia nạp; `@Profile("local")` có thể khớp điều kiện.

**Trường hợp B — truyền active profile là `prod`**

```bash
java -jar myapp.jar --spring.profiles.active=prod
```

Lúc này `prod` là active profile. `local` không được cộng thêm vào chỉ vì nó là default profile. `application-prod.properties` được xét, còn `application-local.properties` không được xét theo fallback.

**Trường hợp C — truyền active profile trùng tên default**

```bash
java -jar myapp.jar --spring.profiles.active=local
```

Lúc này `local` là **active profile thực sự**, không còn là fallback. Các file và điều kiện `local` có thể tạo cùng hiệu ứng nhìn thấy bên ngoài, nhưng `environment.getActiveProfiles()` sẽ khác trường hợp A.

Bảng so sánh:

| Cấu hình khởi chạy | `getActiveProfiles()` | `getDefaultProfiles()` | Profile được xét nếu không có cơ chế bổ sung khác |
| --- | --- | --- | --- |
| Không đặt gì | `[]` | `[default]` | `default` |
| `spring.profiles.default=local` | `[]` | `[local]` | `local` |
| `spring.profiles.default=local,metrics` | `[]` | `[local, metrics]` | `local` và `metrics` |
| `spring.profiles.default=local` và `spring.profiles.active=prod` | `[prod]` | `[local]` | `prod` |
| `spring.profiles.active=default` | `[default]` | `[default]` | `default` là active profile rõ ràng |
| `spring.profiles.default=none`, không có active | `[]` | `[none]` | profile fallback mang tên `none` |

Các giá trị trong bảng là trường hợp minh họa khi không có API `setAdditionalProfiles`, `spring.profiles.include`, profile group hoặc extension khác bổ sung thêm active profiles.

### Tập default không tự “tham gia cùng” tập active

Giả sử `spring.profiles.default=local` và `spring.profiles.active=prod`. Đừng suy luận rằng ứng dụng chạy với cả `local,prod`. Nếu thực sự muốn kích hoạt hai profile, hãy chỉ định chúng trong active profiles hoặc dùng cơ chế cộng profile phù hợp:

```bash
java -jar myapp.jar --spring.profiles.active=local,prod
```

Khi đó `local` và `prod` đều là **active**, còn việc `local` có đồng thời là tên default không liên quan đến quyết định này.

## 6. Giá trị `none`: tránh tự dùng profile tên `default`

Tài liệu chính thức của Spring Boot 3.3 đưa ra ví dụ:

```properties
spring.profiles.default=none
```

Hoặc:

```yaml
spring:
  profiles:
    default: "none"
```

**Ý nghĩa thực tế:** thay tên default profile từ `default` thành `none`. Nếu ứng dụng không có active profiles, `application-default.*` và các bean chỉ dành cho `@Profile("default")` không còn được kích hoạt chỉ bởi fallback.

Tuy nhiên cần hiểu chính xác: `none` là **một tên profile**, không phải một lệnh “tắt hoàn toàn cơ chế profile” mang tính phổ quát. Với cấu hình này, `getDefaultProfiles()` có thể trả về `["none"]`, và nếu trong ứng dụng có `application-none.yaml` hoặc `@Profile("none")` thì chúng có thể được xét khi không có active profile.

Vì thế:

- Dùng `spring.profiles.default=none` khi muốn tránh sử dụng các thiết lập dành cho profile mặc định tên `default`.
- Không tạo nhầm `application-none.*` nếu mục tiêu là chỉ dùng cấu hình chung khi không có active profile.
- Không dùng `none` như tên active profile nếu chỉ muốn biểu thị “không chọn profile nào”; `--spring.profiles.active=none` **thực sự kích hoạt** profile mang tên `none`.

**Ví dụ có chủ đích:**

```text
src/main/resources/
├── application.yaml
├── application-default.yaml
└── application-prod.yaml
```

```yaml
# application.yaml
spring:
  profiles:
    default: "none"
app:
  log-format: plain
```

Nếu không chỉ định active profile, file `application-default.yaml` không được chọn theo fallback `default`. Giá trị `app.log-format=plain` từ cấu hình chung vẫn được dùng, trừ khi có nguồn khác ghi đè.

## 7. Quan hệ với `application-default.*`, `application-local.*` và các file profile-specific

Spring Boot nạp cấu hình từ các location đang được tìm bằng cơ chế Config Data. Ngoài `application.properties`/`application.yaml`, Boot xét các biến thể `application-{profile}.properties`/`application-{profile}.yaml`/`application-{profile}.yml` cho tập profile phù hợp.

**Ví dụ:**

```text
config/
  application.properties
  application-default.properties
  application-local.properties
  application-prod.properties
```

Khi `config/` là một location đang được tìm:

- Không có active profile, default vẫn là `default` → xét `application-default.properties`.
- Không có active profile, `spring.profiles.default=local` → xét `application-local.properties`.
- Có active profile `prod` → xét `application-prod.properties`, dù property default đang là `local`.
- Có active profile `local,prod` → xét cả hai profile theo quy tắc ưu tiên Config Data.

Các file chung **vẫn được xét trong mọi trường hợp**. Default profile không thay thế `application.properties`; nó quyết định các file **phụ theo profile** nào được thêm vào tập Config Data khi không có profile được kích hoạt rõ ràng.

Khi cùng khóa xuất hiện ở tài liệu chung và tài liệu profile-specific cùng nhóm vị trí, file theo profile có mức ưu tiên cao hơn. Tuy nhiên, nếu có các location bên ngoài JAR, import, hoặc nhiều location groups, cần xét đầy đủ thứ tự Config Data; không thể chỉ nhìn tên file mà suy ra thắng thua cho mọi nguồn.

**Ví dụ thực tế:**

```properties
# application.properties
spring.profiles.default=local
app.base-url=https://api.example.test
app.read-timeout=3s
```

```properties
# application-local.properties
app.base-url=http://localhost:8080
```

```properties
# application-prod.properties
app.base-url=https://api.prod.example.test
app.read-timeout=10s
```

Kết quả:

| Cách chạy | `app.base-url` | `app.read-timeout` |
| --- | --- | --- |
| Không có active profile | `http://localhost:8080` | `3s` |
| `--spring.profiles.active=prod` | `https://api.prod.example.test` | `10s` |

Dòng đầu cho thấy fallback `local` không xóa mọi property của tài liệu chung: chỉ các khóa được ghi đè mới thay đổi. Dòng thứ hai cho thấy default `local` bị bỏ qua khi `prod` đã active.

## 8. Default profile và YAML nhiều tài liệu

Ngoài file `application-{profile}.*`, Boot cho phép chứa nhiều **Config Data documents** trong cùng YAML, phân tách bằng `---`, và kích hoạt một document dựa trên profile:

```yaml
# application.yaml — document chung
spring:
  profiles:
    default: local
app:
  message: "common"
---
# Document chỉ được xét khi local phù hợp
spring:
  config:
    activate:
      on-profile: local
app:
  message: "local-fallback"
---
# Document chỉ được xét khi prod phù hợp
spring:
  config:
    activate:
      on-profile: prod
app:
  message: "production"
```

Khi **không có active profile**, default là `local` nên document có `spring.config.activate.on-profile=local` được xét. Giá trị `app.message` dự kiến là `local-fallback`, nếu không có nguồn khác ưu tiên hơn.

Khi khởi chạy với:

```bash
java -jar myapp.jar --spring.profiles.active=prod
```

Document kích hoạt bởi `prod` được xét, document `local` không được chọn chỉ do nó là tên default. Giá trị `app.message` dự kiến là `production`.

**Đặt đúng vị trí:** `spring.profiles.default` thuộc **document chung, không đặc thù profile**, như document đầu ở ví dụ. Không chuyển property đó vào một document có `spring.config.activate.on-profile`.

Trong .properties nhiều tài liệu, ranh giới document được biểu diễn bằng `#---` (trên một dòng riêng), không phải `---` của YAML. Ví dụ:

```properties
# application.properties — document chung
spring.profiles.default=local
app.message=common
#---
spring.config.activate.on-profile=local
app.message=local-fallback
```

Tại runtime, `spring.config.activate.on-profile` dùng biểu thức profile để xác định document có được kích hoạt không. Khi default profile được sử dụng, profile đó có thể thỏa điều kiện activation tương ứng.

## 9. Default profile và `@Profile` trên bean

Profile không chỉ quyết định file nào được nạp. Spring Framework dùng điều kiện `@Profile` để quyết định đăng ký bean/configuration.

Ví dụ:

```java
package com.example.demo.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
public class StorageConfig {

    @Bean
    @Profile("local")
    StorageClient localStorage() {
        return new InMemoryStorageClient();
    }

    @Bean
    @Profile("prod")
    StorageClient prodStorage() {
        return new CloudStorageClient();
    }
}
```

Giả sử `StorageClient`, `InMemoryStorageClient` và `CloudStorageClient` là các kiểu do ứng dụng tự định nghĩa.

Khi `spring.profiles.default=local` và không có active profiles, `@Profile("local")` có thể khớp nhờ fallback; khi active profile là `prod`, điều kiện `@Profile("prod")` khớp và fallback `local` không được dùng.

Một ví dụ theo default ban đầu:

```java
@Configuration
@Profile("default")
public class DefaultCacheConfig {

    @Bean
    CacheAdapter defaultCacheAdapter() {
        return new LocalCacheAdapter();
    }
}
```

Với `spring.profiles.default` chưa tùy chỉnh và không có active profile, class này có thể được đăng ký. Nhưng nếu ứng dụng đặt `spring.profiles.default=none` hoặc `local`, điều kiện `@Profile("default")` không còn được thỏa nhờ fallback.

### `@Profile("default")` không đồng nghĩa “bean vô điều kiện”

Đây là lỗi suy luận phổ biến. `@Profile("default")` vẫn là điều kiện profile:

- Khớp khi không có active profiles và default profiles có chứa `default`.
- Không khớp khi active profile là `prod`, trừ trường hợp chính `default` cũng được kích hoạt.
- Không khớp nhờ fallback nếu default profiles đã đổi thành một tập không chứa `default`.

Một bean **không có** `@Profile` nói chung không bị lọc bởi điều kiện profile này. Nếu chức năng phải luôn có bất kể môi trường chạy, không nên gắn `@Profile("default")` chỉ vì nghĩ rằng `default` là cấu hình chung.

### Biểu thức profile phủ định

`@Profile("!prod")` có thể khớp khi `prod` không hoạt động, kể cả lúc đang sử dụng default profile `default` hoặc `local`. Điều đó khác với `@Profile("default")`: biểu thức phủ định kiểm tra **không có prod**, còn biểu thức `default` kiểm tra tên profile được chấp nhận có chứa `default`.

## 10. Giới hạn bắt buộc: không đặt `spring.profiles.default` vào tài liệu đặc thù profile

Tài liệu Spring Boot 3.3 nêu rõ cả hai property sau **chỉ được dùng trong non-profile-specific documents**:

- `spring.profiles.active`
- `spring.profiles.default`

Nghĩa là **không** khai báo chúng bên trong:

1. File `application-dev.properties`, `application-prod.yaml` hoặc một file thuộc profile cụ thể.
2. Một document YAML hoặc .properties được kích hoạt bởi `spring.config.activate.on-profile`.

**Ví dụ hợp lệ:**

```yaml
# application.yaml — document không đặc thù profile
spring:
  profiles:
    default: local
app:
  name: shared
```

**Ví dụ không hợp lệ — đặt default trong file theo profile:**

```properties
# application-local.properties
spring.profiles.default=prod
```

**Ví dụ không hợp lệ — đặt default vào document điều kiện:**

```yaml
# application.yaml
app:
  name: common
---
spring:
  config:
    activate:
      on-profile: local
  profiles:
    default: prod
```

Lý do là các property quyết định tập profile phải được giải quyết theo quy tắc của quá trình Config Data. Nếu cho phép một tài liệu chỉ bật theo profile tự thay đổi tập profile ở ngay trong tài liệu đó, cấu hình có nguy cơ phụ thuộc vòng tròn.

Khi cần dùng một fallback chung, đặt `spring.profiles.default` trong **document chung** hoặc nguồn ngoài như OS environment/CLI/JVM system property. Nếu muốn một nhóm cấu hình chỉ áp dụng cho `local`, dùng `spring.config.activate.on-profile=local` hoặc file `application-local.*` để khai báo **các property nghiệp vụ** tương ứng.

## 11. PropertySource precedence: nhiều chỗ cùng đặt `spring.profiles.default`

`spring.profiles.default` tuân theo thứ tự ưu tiên nguồn cấu hình. Ví dụ:

```properties
# application.properties
spring.profiles.default=local
```

Nhưng chạy bằng:

```bash
java -jar myapp.jar --spring.profiles.default=staging
```

Nếu không có active profiles khác, giá trị command-line cao hơn giá trị trong file cấu hình, nên fallback là `staging`. File `application-staging.*` có thể được xét thay vì `application-local.*`.

Tương tự, có thể có:

```bash
SPRING_PROFILES_DEFAULT=local \
java -Dspring.profiles.default=staging -jar myapp.jar
```

Với thứ tự PropertySource mặc định của Boot 3.3, JVM system property `-D...` có mức ưu tiên cao hơn OS environment variable cùng khóa, nên giá trị `staging` thắng. Đây là quy tắc **chọn giá trị property**, còn quyết định fallback chỉ được dùng **nếu không có active profile**.

Nếu cùng lúc có:

```bash
java -jar myapp.jar \
  --spring.profiles.default=staging \
  --spring.profiles.active=prod
```

thì default profiles có thể là `[staging]` nhưng ứng dụng dùng `prod` vì đây là active profile. Command line mặc định không biến default profile thành active profile.

## 12. Các cơ chế khác có thể khiến fallback không được dùng

Đừng chỉ tìm `spring.profiles.active` rồi kết luận chắc chắn không có active profiles. Spring Boot và Spring Framework có thêm các cơ chế đưa profile vào tập active, ví dụ:

- `spring.profiles.include`: thêm profile được yêu cầu vào tập active, theo quy tắc giới hạn tài liệu và xử lý của Boot.
- `spring.profiles.group.<group-name>`: mở rộng một profile logic thành một nhóm profile khi nhóm đó được kích hoạt.
- `SpringApplication.setAdditionalProfiles(...)` hoặc `SpringApplicationBuilder.profiles(...)`: kích hoạt thêm profile từ mã khởi động.
- `ConfigurableEnvironment.setActiveProfiles(...)`/`addActiveProfile(...)` nếu được gọi ở giai đoạn phù hợp.
- Trong test, `@ActiveProfiles` của Spring Test có thể kích hoạt một hoặc nhiều profile cho test context.

Ví dụ:

```java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setAdditionalProfiles("metrics");
app.run(args);
```

Khi `metrics` thực sự được thêm vào active profiles, default profile có thể không còn được dùng làm fallback.

**Điểm kiểm tra:** hãy quan sát `environment.getActiveProfiles()` **sau giai đoạn chuẩn bị Environment**. Danh sách này phản ánh các profile đang hoạt động, bao gồm các profile được thêm qua cơ chế mà ứng dụng sử dụng. Nếu không rỗng, đừng kỳ vọng `spring.profiles.default` tự kích hoạt thêm một profile.

### Test với `@ActiveProfiles`

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class OrderServiceTest {

    @Test
    void loadsApplicationContext() {
    }
}
```

Trong test này, `test` là active profile do test framework cung cấp. Nếu `application.properties` chứa `spring.profiles.default=local`, điều đó không tự khiến `application-local.*` được nạp theo fallback trong test. Thông thường các file `application-test.*` được xét khi profile `test` active.

Không nên mặc định rằng **mọi** `@SpringBootTest` tự động kích hoạt `test`; nếu không chỉ định profile và không có cơ chế khác kích hoạt, test có thể vẫn sử dụng default profile của ứng dụng.

## 13. Quan hệ với cấu hình sớm và Config Data

Spring Boot giải quyết tập profile và các file profile-specific trong quá trình chuẩn bị `Environment`, trước khi `ApplicationContext` hoàn tất refresh. Vì thế, cần phân biệt các nhóm property:

| Nhóm | Ví dụ | Thời điểm/cách cung cấp |
| --- | --- | --- |
| Xác định tên và location để **bắt đầu tìm file** | `spring.config.name`, `spring.config.location`, `spring.config.additional-location` | Phải có rất sớm từ OS environment, JVM `-D`, command line hoặc launcher trước `run`. |
| Chọn active/default profile trong quá trình Config Data | `spring.profiles.active`, `spring.profiles.default` | Có thể được khai báo trong **tài liệu Config Data không đặc thù profile**, hoặc nguồn ngoài đủ sớm. |
| Kích hoạt một Config Data document | `spring.config.activate.on-profile` | Khai báo bên trong document cần kiểm soát. |
| Giá trị nghiệp vụ theo profile | `app.*`, `server.*`, `spring.datasource.*` | Đặt trong file profile-specific hoặc document được kích hoạt phù hợp. |

Một trường hợp dễ nhầm:

```properties
# application.properties, tại location mặc định
spring.profiles.default=local
spring.config.location=file:./custom/
```

`spring.profiles.default=local` là cấu hình hợp lệ ở **tài liệu chung** để chọn fallback profile; nhưng `spring.config.location` ở ngay file đang được nạp không phải phương án đáng tin để định tuyến lại danh sách location tìm kiếm đã được chọn ở giai đoạn sớm. Để đổi location ban đầu, truyền `spring.config.location` từ nguồn sớm, rồi để các file được tìm thấy quyết định profile theo cơ chế Config Data.

Nếu `spring.config.location` hoặc `spring.config.name` đã đổi từ sớm, có thể ứng dụng không còn đọc file `application.properties` mà bạn đang chỉnh sửa. Khi gặp tình huống “đã set `spring.profiles.default` nhưng không có hiệu lực”, hãy kiểm tra file chứa property **có thực sự nằm trong các nguồn Config Data đã nạp hay không**.

## 14. Quan sát ở runtime: active hay default?

Một cách chẩn đoán an toàn là in **tên** các profile và một vài giá trị cấu hình không nhạy cảm sau khi Environment được chuẩn bị. Ví dụ dùng `ApplicationRunner`:

```java
package com.example.demo;

import java.util.Arrays;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration
public class ProfileDiagnostics {

    @Bean
    ApplicationRunner showProfiles(Environment environment) {
        return args -> {
            System.out.println("Active profiles:  "
                    + Arrays.toString(environment.getActiveProfiles()));
            System.out.println("Default profiles: "
                    + Arrays.toString(environment.getDefaultProfiles()));
            System.out.println("Configured spring.profiles.default: "
                    + environment.getProperty("spring.profiles.default"));
        };
    }
}
```

Giả sử `spring.profiles.default=local` và không có active profile, đầu ra có thể là:

```text
Active profiles:  []
Default profiles: [local]
Configured spring.profiles.default: local
```

Chạy với `--spring.profiles.active=prod`:

```text
Active profiles:  [prod]
Default profiles: [local]
Configured spring.profiles.default: local
```

Điểm mấu chốt: giá trị `spring.profiles.default` **vẫn tồn tại** ngay cả khi nó **không phải tập profile đang được sử dụng**.

### Kiểm tra profile nào được chấp nhận

Spring Framework cung cấp API để kiểm tra điều kiện profile:

```java
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;

boolean localApplies = environment.acceptsProfiles(Profiles.of("local"));
boolean prodApplies = environment.acceptsProfiles(Profiles.of("prod"));
```

Nếu active profile trống và default profiles là `[local]`, `localApplies` có thể là `true`. Nếu active profile là `prod`, `prodApplies` là `true`, còn `localApplies` thường là `false` khi chỉ có các profile trên.

Cách đọc có lợi khi chẩn đoán điều kiện `@Profile` và tài liệu Config Data được kích hoạt theo profile. Hãy kiểm tra kết quả trong cùng điều kiện startup, bởi khi truyền thêm profile qua CLI, test framework hay API, câu trả lời có thể thay đổi.

### Dấu hiệu trong log startup

Spring Boot thường ghi thông điệp cho biết các active profiles đang dùng hoặc cho biết không có active profile rồi fallback sang default profile. Chẳng hạn có thể thấy dạng thông điệp:

```text
No active profile set, falling back to 1 default profile: "default"
```

Nội dung chi tiết phụ thuộc phiên bản và cấu hình logging. Nếu đặt `spring.profiles.default=local` đúng cách, thông điệp fallback sẽ thể hiện tên `local` thay cho `default`.

Đừng xem log fallback là lỗi. Nó đơn giản cho biết không có profile được kích hoạt rõ ràng và cơ chế default profiles được sử dụng.

## 15. Các tình huống thường gây hiểu nhầm

### Tình huống A: Có `application-default.yaml` nhưng nó không được đọc

**Nguyên nhân có thể:** một active profile như `prod` đã được cung cấp từ command line, environment variable, test hoặc API; hoặc `spring.profiles.default` đã đổi thành `local`/`none`. Khi đó `default` không còn nằm trong tập profile được chấp nhận theo fallback.

**Hướng xử lý:** kiểm tra `getActiveProfiles()`, `getDefaultProfiles()`, nguồn khai báo `spring.profiles.active` và `spring.profiles.default`.

### Tình huống B: Đặt `spring.profiles.default=dev` rồi thấy ứng dụng “chạy dev” ở mọi nơi

Default `dev` có tác dụng **bất cứ khi nào không có active profile**, kể cả môi trường staging hoặc production nếu launcher bỏ quên `spring.profiles.active`. Vì vậy chọn fallback `dev` là một quyết định cấu hình có ảnh hưởng vận hành. Với ứng dụng cần tách môi trường chặt chẽ, nên thiết lập active profile rõ ràng cho production và lựa chọn fallback phù hợp với yêu cầu an toàn.

### Tình huống C: Đặt `spring.profiles.default=none` nhưng `@Profile("none")` vẫn khớp

Đây là hành vi có thể xảy ra vì `none` vẫn là **tên default profile**. Không dùng tên `none` cho các bean/file đặc biệt nếu ý định của nhóm là “không có fallback tùy chỉnh”.

### Tình huống D: Đặt default ở `application-prod.yaml`

`spring.profiles.default` trong profile-specific file là cấu hình không hợp lệ theo các quy tắc của Boot 3.3. Đưa property vào tài liệu chung hoặc nguồn ngoài.

### Tình huống E: Đặt active profile `default` rồi cho rằng đó là fallback

`--spring.profiles.active=default` là **kích hoạt rõ ràng** profile tên `default`. Điều này khiến `getActiveProfiles()` có `default`, khác với trường hợp không active profile và `getDefaultProfiles()` có `default`.

### Tình huống F: Dùng `@Profile("default")` cho bean cần có ở mọi môi trường

Bean này biến mất khi profile active chuyển thành `prod` hoặc khi default profile đổi tên. Bean dùng chung nên không bị gắn điều kiện profile nếu không cần thiết.

### Tình huống G: Cấu hình rải rác ở nhiều nguồn

Một file khai báo `spring.profiles.default=local`, nhưng biến môi trường đặt `SPRING_PROFILES_DEFAULT=none`. Giá trị có ưu tiên cao hơn thắng, nên ứng dụng không dùng fallback `local` như dự kiến. Kiểm tra precedence, thay vì chỉ kiểm tra file bạn vừa sửa.

### Tình huống H: File `application-default.properties` ở location không được tìm

Ngay cả khi default profile là `default`, file chỉ được nạp nếu nó nằm ở location/basename mà Config Data đang tìm. Nếu `spring.config.location` hoặc `spring.config.name` đã được đổi từ sớm, hãy kiểm tra file profile-specific nằm đúng nơi/tên đang được sử dụng.

### Tình huống I: Test bất ngờ dùng cấu hình local

Một test `@SpringBootTest` không dùng `@ActiveProfiles` có thể nhận fallback `local` từ `spring.profiles.default=local`. Nếu test cần cấu hình tách biệt, có thể khai báo `@ActiveProfiles("test")` hoặc một nguồn active profile phù hợp.

## 16. Công thức áp dụng nhanh

### Công thức 1 — Chỉ dùng mặc định của Spring Boot

```text
Không khai báo spring.profiles.active
Không khai báo spring.profiles.default
→ activeProfiles = []
→ defaultProfiles = [default]
→ application-default.* được xét nếu tồn tại và nằm trong location đang tìm
```

### Công thức 2 — Chọn local làm fallback

```properties
# application.properties
spring.profiles.default=local
```

```text
Không có active profiles
→ dùng fallback local
→ application-local.* / @Profile("local") có thể có hiệu lực
```

### Công thức 3 — Chọn production rõ ràng

```bash
java -jar myapp.jar --spring.profiles.active=prod
```

```text
activeProfiles = [prod]
→ các default profiles chỉ là tập dự phòng
→ application-prod.* / @Profile("prod") có thể có hiệu lực
```

### Công thức 4 — Không muốn profile `default` ngầm áp dụng

```properties
# application.properties — tài liệu chung
spring.profiles.default=none
```

```text
Không có active profiles
→ fallback mang tên none
→ không tự dùng application-default.* hay @Profile("default")
→ tránh tạo application-none.* / @Profile("none") nếu muốn chỉ dùng cấu hình chung
```

### Công thức 5 — Dùng default profile cùng nhiều tài liệu YAML

```yaml
# application.yaml — common
spring:
  profiles:
    default: local
app:
  feature-enabled: false
---
spring:
  config:
    activate:
      on-profile: local
app:
  feature-enabled: true
```

Khi không có active profile, tài liệu `local` phù hợp và `app.feature-enabled` được lấy là `true`, trừ khi bị một nguồn có ưu tiên cao hơn ghi đè.

## 17. Tóm tắt kiến thức cần nhớ

1. Spring Boot 3.3 mặc định dùng **profile tên `default`** khi **không có active profiles**.
2. `spring.profiles.default` thay đổi **tập profile dự phòng**, không chủ động bật một active profile khi đã có `spring.profiles.active`.
3. `application-default.*` là file **theo profile**; không được đảm bảo luôn nạp. Khi default thay thành `local`, Boot có thể nạp `application-local.*` trong trường hợp không có active profiles.
4. `spring.profiles.default=none` là cách quen thuộc để **không dùng profile tên `default` theo fallback**; `none` vẫn là tên default profile, vì vậy tránh tạo cấu hình mang tên đó nếu không muốn.
5. `spring.profiles.default` và `spring.profiles.active` chỉ được đặt trong **tài liệu không đặc thù profile** hoặc nguồn ngoài phù hợp.
6. `@Profile("default")` phụ thuộc điều kiện profile, khác với một bean không có `@Profile`.
7. Khi điều tra lỗi, xem cả `getActiveProfiles()` và `getDefaultProfiles()`; kiểm tra Config Data location, nguồn property và profile bổ sung.

## 18. Tài liệu tham khảo

- Spring Boot **3.3** Reference Guide – **Profiles**, các mục *Adding Active Profiles*, *Profile Groups* và phần giải thích default profile: https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html
- Spring Boot **3.3** Reference Guide – **Externalized Configuration**, mục *Profile Specific Files*, *PropertySource Order*, *Working With Multi-Document Files* và *Activation Properties*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot **3.3** Reference Guide – **Properties and Configuration**, mục *Set the Default Profile Name*: https://docs.spring.io/spring-boot/3.3/how-to/properties-and-configuration.html
- Spring Framework – `Environment`, `ConfigurableEnvironment`, `Profiles` và `@Profile`: https://docs.spring.io/spring-framework/reference/core/beans/environment.html

**Thông điệp chính:** `spring.profiles.default` trả lời câu hỏi “**nếu không có active profile thì dùng profile nào?**”. Nó không thay thế `spring.profiles.active` và không tự thêm fallback vào ứng dụng vốn đã có active profiles.

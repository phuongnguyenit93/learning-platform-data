# Biểu thức profile với toán tử !, & và |

## 1. Vì sao cần biểu thức profile?

Trong ứng dụng Spring Boot, một số cấu hình chỉ nên có hiệu lực khi **nhiều điều kiện về môi trường cùng đúng**. Ví dụ:

- Chỉ bật cách kết nối giả lập khi ứng dụng đang chạy ở `dev` và **không** chạy trong `cloud`.
- Bật cấu hình theo dõi bổ sung khi ứng dụng ở `staging` **hoặc** `prod`.
- Chỉ nạp thông số của một hạ tầng khi ứng dụng vừa thuộc `prod` **và** có profile `cloud`.
- Nạp một bộ tham số dành cho môi trường ngoài production ở mọi nơi **trừ** `prod`.

Nếu dùng một tên profile đơn lẻ cho từng tổ hợp, danh sách tên sẽ nhanh chóng trở nên khó quản lý: `dev-local`, `dev-cloud`, `staging-cloud`, `prod-cloud`, v.v. Spring hỗ trợ **biểu thức profile**, cho phép kết hợp những tên profile độc lập bằng các toán tử logic.

Ba toán tử quan trọng:

| Toán tử | Nghĩa | Ví dụ | Khi nào đúng? |
| --- | --- | --- | --- |
| `!` | Phủ định (NOT) | `!prod` | Profile `prod` không hoạt động |
| `&` | Đồng thời (AND) | `prod & cloud` | Cả `prod` và `cloud` đều hoạt động |
| `|` | Một trong hai (OR) | `dev | staging` | Ít nhất một trong `dev`, `staging` hoạt động |

Dấu ngoặc tròn `( )` giúp nhóm các điều kiện:

```text
(prod | staging) & cloud

           AND
          /   \
         OR   cloud
        /  \
      prod staging
```

Biểu thức này chỉ đúng khi có `cloud` **và** ít nhất một trong `prod` hoặc `staging` hoạt động. Nói cách khác, có `cloud` một mình là chưa đủ; có `prod` một mình cũng chưa đủ.

Trong nhóm kiến thức “Tài liệu có điều kiện”, biểu thức profile đặc biệt hữu ích với `spring.config.activate.on-profile`: **Spring Boot dùng kết quả biểu thức để quyết định tài liệu cấu hình nào được nạp**.

## 2. Profile hoạt động là gì?

Một profile là một tên điều kiện do ứng dụng hoặc nền tảng triển khai lựa chọn. Một ứng dụng Spring có thể có **nhiều active profiles cùng lúc**.

Chẳng hạn:

```bash
java -jar app.jar --spring.profiles.active=prod,cloud
```

Ở lần khởi động này, tập profile hoạt động chứa hai tên `prod` và `cloud`. Với tập đó:

```text
prod               -> true
cloud              -> true
staging            -> false
!staging           -> true
prod & cloud       -> true
prod | staging     -> true
staging & cloud    -> false
```

Phân biệt rõ **tên profile** và **biểu thức profile**:

- `prod` là một tên profile độc lập.
- `prod & cloud` là một biểu thức cần đánh giá trên **tập profile hoạt động**.
- `spring.profiles.active=prod,cloud` là danh sách profile cần kích hoạt; dấu phẩy ở đây phân tách **tên**.
- `spring.config.activate.on-profile: "prod & cloud"` là điều kiện để kích hoạt **một tài liệu cấu hình**; dấu `&` ở đây là phép AND.

Không dùng chuỗi `prod & cloud` làm tên môi trường rồi kỳ vọng Spring tự hiểu nó là hai profile được kích hoạt. Điều kiện logic thuộc về nơi khai báo biểu thức; còn tập profile hoạt động được chọn bằng cơ chế kích hoạt profile.

Khi không có active profile nào được đặt, Spring vẫn có khái niệm **default profiles** (mặc định thường là `default`). Vì vậy, biểu thức `!prod` có thể đúng trong lần chạy không kích hoạt profile nào. Toán tử `!` kiểm tra **sự vắng mặt của tên profile được phủ định**; nó không đồng nghĩa với “đang ở môi trường dev”.

## 3. Toán tử !: điều kiện phủ định

Cú pháp đơn giản nhất:

```text
!prod
```

Ý nghĩa: điều kiện đúng khi profile `prod` không hoạt động.

| Active profiles | `!prod` |
| --- | --- |
| Không khai báo profile nào | Đúng |
| `dev` | Đúng |
| `staging` | Đúng |
| `prod` | Sai |
| `prod,cloud` | Sai |
| `dev,cloud` | Đúng |

Ví dụ trong tài liệu YAML có điều kiện:

```yaml
spring:
  config:
    activate:
      on-profile: "!prod"

feature:
  diagnostic-banner: true
```

Tài liệu này chỉ tham gia khi điều kiện `!prod` đúng. Vì `!prod` cũng đúng trong môi trường `staging` hoặc khi không có active profile nào, nó **không thể thay thế trực tiếp điều kiện `dev`** nếu mục tiêu là chỉ bật cho phát triển.

Một cách diễn đạt chặt hơn cho “dev, nhưng không cloud” là:

```yaml
spring:
  config:
    activate:
      on-profile: "dev & !cloud"
```

**Chú ý dấu nháy trong YAML:** Ký tự `!` đứng đầu một giá trị không được trích dẫn có thể bị YAML hiểu như phần khai báo tag. Để rõ ràng và tránh lỗi phân tích cú pháp, hãy viết biểu thức profile dưới dạng chuỗi trong dấu nháy đơn hoặc nháy kép, đặc biệt khi có `!`, `&` và `|`.

### Phủ định một nhóm

So sánh:

```text
!(prod | staging)
!prod & !staging
```

Hai biểu thức này đều đúng khi **cả `prod` và `staging` đều không hoạt động**. Dấu ngoặc ở biểu thức đầu phủ định toàn bộ phép OR, không chỉ tên `prod`.

Ngược lại:

```text
!prod | staging
```

Nghĩa là “không phải prod **hoặc** có staging”. Biểu thức đó vẫn đúng khi cả `prod` và `staging` cùng hoạt động. Nó không có nghĩa “không phải cả prod và staging”. Để tránh nhầm lẫn, nên diễn đạt yêu cầu bằng lời trước, sau đó mới viết logic.

## 4. Toán tử &: yêu cầu đồng thời

Cú pháp:

```text
prod & cloud
```

Điều kiện chỉ đúng khi **cả hai tên profile** đều có hiệu lực.

| Active profiles | `prod & cloud` |
| --- | --- |
| `prod` | Sai |
| `cloud` | Sai |
| `prod,cloud` | **Đúng** |
| `prod,staging` | Sai |
| `prod,staging,cloud` | **Đúng** |

Ví dụ nạp tài liệu chỉ khi production chạy trên môi trường cloud:

```yaml
spring:
  config:
    activate:
      on-profile: "prod & cloud"

storage:
  use-managed-service: true
```

Ở đây, `prod` biểu thị giai đoạn triển khai, còn `cloud` biểu thị kiểu hạ tầng. Hai điều kiện phải cùng đúng.

Toán tử AND có thể kết hợp điều kiện phủ định:

```text
dev & !cloud
```

Điều kiện chỉ đúng khi `dev` hoạt động và `cloud` không hoạt động. Nó phù hợp cho một số cấu hình phục vụ phát triển tại máy cá nhân nhưng không muốn sử dụng khi chạy dev trên hạ tầng cloud.

Với ba điều kiện, có thể viết:

```text
prod & cloud & metrics
```

Điều kiện đúng khi cả ba profile đều hoạt động. Dùng những tên profile phản ánh ngữ cảnh rõ ràng; đừng biến một profile thành một cờ cho mọi lựa chọn độc lập nếu một thuộc tính cấu hình riêng diễn đạt yêu cầu tốt hơn.

## 5. Toán tử |: chấp nhận ít nhất một điều kiện

Cú pháp:

```text
prod | staging
```

Điều kiện đúng khi **ít nhất một** trong hai profile hoạt động.

| Active profiles | `prod | staging` |
| --- | --- |
| `dev` | Sai |
| `prod` | **Đúng** |
| `staging` | **Đúng** |
| `prod,staging` | **Đúng** |
| `prod,cloud` | **Đúng** |

Dấu `|` là **OR bao gồm**: cả `prod` và `staging` đều hoạt động thì biểu thức vẫn đúng. Nó không phải “chỉ một trong hai”.

Ví dụ cấu hình được phép nạp ở hai môi trường gần với production:

```yaml
spring:
  config:
    activate:
      on-profile: "prod | staging"

observability:
  enhanced-tracing: true
```

Cấu hình này không đòi cả hai profile hoạt động. Nó chỉ yêu cầu một trong hai đủ để tài liệu tham gia.

Cũng có thể kết hợp hơn hai lựa chọn:

```text
dev | test | staging
```

Khi ít nhất một trong ba tên có hiệu lực, toàn biểu thức đúng.

### Đừng nhầm OR với danh sách trong @Profile

Trong Java, `@Profile({"prod", "staging"})` trên bean cũng cho phép bean hoạt động nếu **ít nhất một** tên phù hợp. Để viết điều kiện phức tạp, dễ đọc hơn khi dùng **một biểu thức** như `@Profile("prod | staging")`. Với AND cần `@Profile("prod & cloud")`, không dùng danh sách hai chuỗi rồi kỳ vọng đó là AND.

## 6. Kết hợp !, & và | bằng dấu ngoặc

Biểu thức thường chứa hơn một phép logic. Ví dụ:

```text
(prod | staging) & cloud
```

Ta đánh giá từ trong ngoặc:

1. `prod | staging` đúng nếu `prod` hoặc `staging` hoạt động.
2. `cloud` đúng nếu `cloud` hoạt động.
3. Dùng `&` ghép hai kết quả: cả hai phải đúng.

Bảng chân trị minh họa:

| Active profiles | `prod | staging` | `cloud` | `(prod | staging) & cloud` |
| --- | --- | --- | --- |
| `prod` | Đúng | Sai | Sai |
| `staging` | Đúng | Sai | Sai |
| `cloud` | Sai | Đúng | Sai |
| `prod,cloud` | Đúng | Đúng | **Đúng** |
| `staging,cloud` | Đúng | Đúng | **Đúng** |
| `dev,cloud` | Sai | Đúng | Sai |
| `prod,staging,cloud` | Đúng | Đúng | **Đúng** |

So sánh hai biểu thức sau:

```text
(prod | staging) & cloud
prod | (staging & cloud)
```

Với active profiles chỉ là `prod`:

- Biểu thức thứ nhất **sai**: thiếu `cloud`.
- Biểu thức thứ hai **đúng**: riêng `prod` đã đủ.

Dấu ngoặc quyết định ý nghĩa nghiệp vụ của điều kiện. Đây không chỉ là chuyện định dạng.

### Quy tắc quan trọng: không trộn & và | mà thiếu ngoặc

Spring sử dụng cú pháp biểu thức profile của Spring Framework. Khi một biểu thức chứa cả `&` và `|`, **phải dùng dấu ngoặc để làm rõ cấu trúc**. Không nên viết:

```text
prod & cloud | staging
```

Cú pháp trộn hai toán tử cùng cấp mà không nhóm rõ là không hợp lệ theo quy tắc của bộ phân tích biểu thức profile. Hãy chọn một ý nghĩa:

```text
(prod & cloud) | staging
```

hoặc:

```text
prod & (cloud | staging)
```

Hai cách không tương đương; lựa chọn phải xuất phát từ yêu cầu thực tế.

Đối với phủ định của cả nhóm:

```text
!(prod & cloud)
```

điều kiện chỉ sai khi **cả `prod` và `cloud` đều hoạt động**. Trong các trường hợp còn lại, nó đúng. Đặt `!` ngoài ngoặc khác hẳn với `!prod & cloud`.

## 7. spring.config.activate.on-profile: tài liệu YAML có điều kiện

Spring Boot có thể tổ chức nhiều tài liệu cấu hình trong **một tệp YAML** bằng dấu `---`. Mỗi tài liệu có thể chứa điều kiện:

```yaml
spring:
  config:
    activate:
      on-profile: "prod & cloud"
```

Khi biểu thức đúng, tài liệu đó tham gia vào tập cấu hình được nạp; khi sai, các thuộc tính riêng của tài liệu đó không được đưa vào như nguồn cấu hình có hiệu lực.

Ví dụ:

```yaml
# application.yml — tài liệu chung
service:
  timeout: 5s
  endpoint: https://example.invalid/default

---
# Tài liệu dành cho dev không chạy trên cloud
spring:
  config:
    activate:
      on-profile: "dev & !cloud"

service:
  timeout: 15s
  endpoint: http://localhost:9000/mock

---
# Tài liệu dành cho staging hoặc production trên cloud
spring:
  config:
    activate:
      on-profile: "(staging | prod) & cloud"

service:
  timeout: 2s
  endpoint: https://example.invalid/managed
```

Các địa chỉ `example.invalid` chỉ là dữ liệu minh họa, không phải endpoint có thể kết nối.

Kết quả dự kiến trong tình huống không có nguồn ưu tiên cao hơn:

| Active profiles | Tài liệu phù hợp | `service.timeout` |
| --- | --- | --- |
| Không có profile hoạt động tường minh | Tài liệu chung | `5s` |
| `dev` | Chung + `dev & !cloud` | `15s` |
| `dev,cloud` | Chỉ tài liệu chung | `5s` |
| `staging` | Chỉ tài liệu chung | `5s` |
| `staging,cloud` | Chung + `(staging | prod) & cloud` | `2s` |
| `prod,cloud` | Chung + `(staging | prod) & cloud` | `2s` |

Lưu ý: nếu thêm tham số `--service.timeout=20s` khi khởi động, nguồn command-line có thể ghi đè cả tài liệu theo profile. **Điều kiện nạp tài liệu** và **thứ tự ưu tiên giữa các nguồn** là hai cơ chế riêng.

### Cấu hình có điều kiện chỉ bổ sung những khóa nó khai báo

Nếu tài liệu chung có:

```yaml
service:
  timeout: 5s
  retries: 3
```

và tài liệu có điều kiện chỉ ghi đè:

```yaml
spring:
  config:
    activate:
      on-profile: "prod"

service:
  timeout: 2s
```

thì khi `prod` hoạt động, `timeout` nhận `2s` còn `retries` vẫn có thể lấy giá trị `3` từ tài liệu chung. Không có quy tắc mặc định rằng kích hoạt một tài liệu sẽ xóa mọi thuộc tính còn lại của nhánh `service` trong tài liệu trước.

Đối với cấu trúc như danh sách hoặc cấu hình phức tạp, quy tắc binding có thể khác từng khóa scalar; ví dụ trên cố tình dùng các giá trị đơn giản để tập trung vào biểu thức profile.

## 8. Thực hành đầy đủ: bốn điều kiện trong một application.yml

Ta xây dựng một chương trình Spring Boot rất nhỏ để kiểm chứng toán tử `!`, `&` và `|` bằng các kết quả Boolean, thay vì đoán từ log.

Cấu trúc tối thiểu:

```text
src/main/
├── java/com/example/profileexpr/
│   └── ProfileExpressionApplication.java
└── resources/
    └── application.yml
```

Trong `src/main/resources/application.yml`, viết một tài liệu chung cùng bốn tài liệu có điều kiện:

```yaml
# Tài liệu chung: giá trị mặc định cho tất cả các điều kiện
lab:
  flags:
    dev-local: false
    release-like: false
    managed-release: false
    not-prod: false

---
# Chỉ dev không có cloud
spring:
  config:
    activate:
      on-profile: "dev & !cloud"

lab:
  flags:
    dev-local: true

---
# Staging hoặc prod
spring:
  config:
    activate:
      on-profile: "staging | prod"

lab:
  flags:
    release-like: true

---
# Cloud và (staging hoặc prod)
spring:
  config:
    activate:
      on-profile: "(staging | prod) & cloud"

lab:
  flags:
    managed-release: true

---
# Bất kỳ trường hợp nào không có prod
spring:
  config:
    activate:
      on-profile: "!prod"

lab:
  flags:
    not-prod: true
```

Mỗi tài liệu chỉ ghi đè một khóa thử nghiệm; điều này tránh phải suy luận về thứ tự của hai tài liệu cùng khai báo một khóa. Kết quả của mỗi cờ phản ánh trực tiếp việc tài liệu có điều kiện có được kích hoạt hay không.

Tạo `ProfileExpressionApplication.java`:

```java
package com.example.profileexpr;

import java.util.Arrays;
import java.util.List;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class ProfileExpressionApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProfileExpressionApplication.class, args);
    }

    @Bean
    ApplicationRunner showFlags(Environment environment) {
        return args -> {
            System.out.println("=== PROFILE EXPRESSION LAB ===");
            System.out.println("Active profiles: " +
                Arrays.toString(environment.getActiveProfiles()));

            for (String key : List.of(
                    "dev-local",
                    "release-like",
                    "managed-release",
                    "not-prod")) {
                System.out.println(key + " = " +
                    environment.getProperty("lab.flags." + key));
            }
        };
    }
}
```

`Environment.getActiveProfiles()` hiển thị các profile được kích hoạt tường minh. Các giá trị `lab.flags.*` cho biết những tài liệu YAML có điều kiện nào đã đóng góp cấu hình.

Trong trường hợp dùng project Gradle có plugin Spring Boot, có thể đóng gói bằng `./gradlew bootJar` (Linux/macOS) hoặc `gradlew.bat bootJar` (Windows), rồi thay `app.jar` trong các lệnh bên dưới bằng đường dẫn tới JAR thực tế.

### Trường hợp A: chỉ bật dev

```bash
java -jar app.jar --spring.profiles.active=dev
```

Kỳ vọng:

```text
dev-local = true
release-like = false
managed-release = false
not-prod = true
```

Giải thích: `dev & !cloud` đúng vì có dev và không có cloud. `staging | prod` sai vì thiếu cả staging lẫn prod. Điều kiện `!prod` đúng.

### Trường hợp B: bật dev và cloud

```bash
java -jar app.jar --spring.profiles.active=dev,cloud
```

Kỳ vọng:

```text
dev-local = false
release-like = false
managed-release = false
not-prod = true
```

Chỉ cần bổ sung `cloud` là điều kiện `dev & !cloud` chuyển từ đúng sang sai. Điều này chứng minh vai trò của phép phủ định trong điều kiện AND.

### Trường hợp C: chỉ bật prod

```bash
java -jar app.jar --spring.profiles.active=prod
```

Kỳ vọng:

```text
dev-local = false
release-like = true
managed-release = false
not-prod = false
```

`staging | prod` đúng nhờ có prod. Tuy nhiên `(staging | prod) & cloud` sai vì thiếu cloud.

### Trường hợp D: bật prod và cloud

```bash
java -jar app.jar --spring.profiles.active=prod,cloud
```

Kỳ vọng:

```text
dev-local = false
release-like = true
managed-release = true
not-prod = false
```

Vì prod và cloud cùng hoạt động, cả biểu thức OR thuộc nhóm release và biểu thức kết hợp AND/OR đều đúng.

### Trường hợp E: bật staging và cloud

```bash
java -jar app.jar --spring.profiles.active=staging,cloud
```

Kỳ vọng:

```text
dev-local = false
release-like = true
managed-release = true
not-prod = true
```

`staging` thỏa nhánh OR, `cloud` thỏa điều kiện AND, và vì không có `prod` nên `!prod` vẫn đúng. Đây là ví dụ nhiều điều kiện độc lập cùng đúng trong một lần khởi động.

### Trường hợp F: không chọn active profile

```bash
java -jar app.jar
```

Giả sử môi trường máy không cấp thêm profile, kết quả:

```text
dev-local = false
release-like = false
managed-release = false
not-prod = true
```

Khi đó `!prod` đúng vì `prod` không hoạt động. Điều này củng cố một lưu ý quan trọng: **`!prod` không có nghĩa “dev”**, mà chỉ có nghĩa “không có profile prod”.

Để các lần chạy độc lập, cần loại bỏ biến môi trường `SPRING_PROFILES_ACTIVE` hoặc system property `-Dspring.profiles.active` còn sót từ phiên trước. Mỗi lần chạy nên là một tiến trình mới.

## 9. Kết quả tổng hợp của thí nghiệm

| Active profiles | `dev & !cloud` | `staging | prod` | `(staging | prod) & cloud` | `!prod` |
| --- | --- | --- | --- | --- |
| Không có active profile | Sai | Sai | Sai | Đúng |
| `dev` | Đúng | Sai | Sai | Đúng |
| `dev,cloud` | Sai | Sai | Sai | Đúng |
| `staging` | Sai | Đúng | Sai | Đúng |
| `prod` | Sai | Đúng | Sai | Sai |
| `prod,cloud` | Sai | Đúng | Đúng | Sai |
| `staging,cloud` | Sai | Đúng | Đúng | Đúng |
| `prod,staging,cloud` | Sai | Đúng | Đúng | Sai |

Có thể dùng bảng để kiểm tra tư duy trước khi chạy lệnh. Việc hiểu đúng một biểu thức cho phép bạn dự đoán tài liệu nào được nạp cho **mọi tổ hợp profile**, không cần kiểm tra bằng cách sửa YAML nhiều lần.

Nhìn vào hàng `staging,cloud`, ta có thể thấy rõ tính độc lập của các toán tử: `staging | prod` đúng, `cloud` đúng, và `!prod` cũng đúng. Một ứng dụng không bắt buộc chỉ có một tài liệu có điều kiện được kích hoạt tại một thời điểm.

## 10. Phân biệt on-profile với @Profile

Tên khá giống nhau, nhưng vị trí áp dụng khác nhau:

| Cơ chế | Đối tượng được điều kiện hóa | Ví dụ |
| --- | --- | --- |
| `spring.config.activate.on-profile` | Một tài liệu Config Data | Nạp YAML khi `"prod & cloud"` đúng |
| `@Profile` | Một định nghĩa bean hoặc cấu hình bean | Đăng ký bean Java khi `"prod & cloud"` đúng |
| `spring.profiles.active` | Tập profile đang được chọn | `prod,cloud` |
| `Environment.acceptsProfiles(Profiles.of(...))` | Kiểm tra một biểu thức ở runtime | `"(prod | staging) & cloud"` |

### 10.1. Dùng @Profile với biểu thức

Giả sử ứng dụng có một bean chuyên làm việc vận hành trên hạ tầng cloud:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
public class CloudConfiguration {

    @Bean
    @Profile("prod & cloud")
    CloudClient cloudClient() {
        return new CloudClient();
    }
}
```

`CloudClient` ở đây là một kiểu giả định do ứng dụng tự khai báo. Mục tiêu của ví dụ là cú pháp annotation. Bean `cloudClient` chỉ được đăng ký khi **cả prod và cloud** hoạt động.

Nếu annotation dùng:

```java
@Profile("prod | staging")
```

thì chỉ cần một trong hai profile hoạt động.

Nếu dùng:

```java
@Profile("!prod")
```

thì bean được đăng ký trong tất cả những lần chạy thỏa điều kiện không có `prod`, bao gồm cả một số trường hợp không mong muốn nếu dự án giả định nhầm “không prod = dev”.

### 10.2. Không dùng @Profile để thay thế mọi điều kiện cấu hình

Nếu chỉ thay đổi URL, timeout, số lần retry hoặc mức log, thông thường dễ duy trì hơn khi dùng các thuộc tính cấu hình và `@ConfigurationProperties`. Không cần tạo những bean nghiệp vụ gần như giống nhau chỉ vì profile khác nhau.

Dùng `@Profile` khi sự khác biệt thật sự nằm ở **việc đăng ký hay lựa chọn một thành phần**. Dùng `spring.config.activate.on-profile` khi cần **nạp một nhóm giá trị cấu hình có điều kiện**. Trong cả hai trường hợp, logic các toán tử vẫn là AND/OR/NOT trên tập profile.

### 10.3. Kiểm tra biểu thức trong mã với Profiles.of

Spring Framework có API `Profiles.of(...)` để biểu diễn điều kiện profile và `Environment.acceptsProfiles(...)` để đánh giá nó:

```java
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;

public final class ProfileChecks {

    private final Environment environment;

    public ProfileChecks(Environment environment) {
        this.environment = environment;
    }

    public boolean isManagedRelease() {
        return environment.acceptsProfiles(
            Profiles.of("(staging | prod) & cloud")
        );
    }
}
```

Phép kiểm tra này có thể hữu ích trong những đoạn mã chẩn đoán hoặc điều kiện khởi tạo được tổ chức phù hợp. Tuy nhiên, nếu đây là thuộc tính của một bean được đăng ký theo điều kiện, dùng `@Profile` hoặc cơ chế cấu hình điều kiện có sẵn thường làm ý định rõ hơn so với rải lệnh `acceptsProfiles` vào logic nghiệp vụ.

## 11. Đừng nhầm biểu thức với danh sách active profiles

Có hai dòng cấu hình dễ bị nhầm:

```properties
spring.profiles.active=prod,cloud
spring.config.activate.on-profile=prod & cloud
```

Dòng thứ nhất là một danh sách **kích hoạt profile**. Dòng thứ hai là một **điều kiện của tài liệu** và chỉ nên đặt trong ngữ cảnh tài liệu cấu hình thích hợp.

Khi dùng YAML:

```yaml
spring:
  config:
    activate:
      on-profile: "prod & cloud"
```

Đừng viết:

```yaml
spring:
  profiles:
    active: "prod & cloud"
```

với ý định kích hoạt cùng lúc hai tên `prod` và `cloud`. Giá trị `spring.profiles.active` là một danh sách tên, không phải biểu thức logic để Spring suy luận một tập profile.

Tương tự, `spring.profiles.active=prod|cloud` không phải cú pháp chọn “prod hoặc cloud”. Những biểu thức như `prod | cloud` được đánh giá tại nơi cần điều kiện, **không quyết định profile nào sẽ được bật**.

## 12. Ràng buộc về vị trí khai báo trong Config Data

Trong Spring Boot, cần phân biệt **chọn active profiles** và **nạp tài liệu dựa trên active profiles**.

Một tài liệu được kích hoạt bằng:

```yaml
spring:
  config:
    activate:
      on-profile: "prod"
```

đã phụ thuộc vào tập profile đang hoạt động. Vì vậy, nó không phải chỗ phù hợp để quyết định lại chính tập profile đó.

Các thuộc tính như `spring.profiles.active`, `spring.profiles.default`, `spring.profiles.include` và `spring.profiles.group` có những ràng buộc về tài liệu không phụ thuộc profile. Không khai báo chúng trong một tài liệu đang được kích hoạt bằng `spring.config.activate.on-profile` hoặc trong file riêng theo profile như `application-prod.yml` rồi kỳ vọng Spring Boot cho phép thiết lập lại active profiles ở đó.

Ví dụ nên tránh:

```yaml
spring:
  config:
    activate:
      on-profile: "dev"

  profiles:
    active: prod
```

Đoạn này cố chuyển sang `prod` từ một tài liệu chỉ có hiệu lực khi `dev` đã được chọn. Spring Boot xử lý lựa chọn profile ở giai đoạn phù hợp của quá trình nạp cấu hình và giới hạn kiểu khai báo vòng như vậy.

Cách đúng là **chọn profile từ bên ngoài** (ví dụ tham số `--spring.profiles.active=dev`), sau đó để các tài liệu có `on-profile` tự quyết định chúng có được nạp hay không.

## 13. Một lỗi khác: YAML có nhiều tài liệu và nhiều điều kiện cùng đúng

Giả sử file `application.yml`:

```yaml
service:
  timeout: 10s

---
spring:
  config:
    activate:
      on-profile: "prod | staging"

service:
  timeout: 5s

---
spring:
  config:
    activate:
      on-profile: "prod & cloud"

service:
  timeout: 2s
```

Với `prod,cloud`, **cả hai tài liệu có điều kiện đều đúng**. Trong file YAML nhiều tài liệu như ví dụ và khi không có nguồn bên ngoài ưu tiên cao hơn, tài liệu xuất hiện sau có thể ghi đè giá trị của tài liệu trước cho cùng khóa, nên `service.timeout` trở thành `2s`.

Tuy nhiên, điều đó không có nghĩa toán tử `&` có “ưu tiên ghi đè cao hơn” toán tử `|`. Toán tử chỉ quyết định một tài liệu **có khớp điều kiện hay không**. **Thứ tự tài liệu và thứ tự nguồn cấu hình** mới quyết định giá trị nào được chọn nếu nhiều tài liệu cùng cung cấp một thuộc tính.

Nếu đổi vị trí hai tài liệu, kết quả với cùng tập profile có thể thay đổi. Bởi vậy, nên:

- Sắp xếp tài liệu từ quy tắc tổng quát đến quy tắc cụ thể khi có ý định ghi đè.
- Tránh nhiều tài liệu cùng ghi một khóa nếu việc ghi đè không được thiết kế và giải thích rõ.
- Giữ những khác biệt theo profile dễ đọc, thay vì xây dựng một chuỗi điều kiện chồng chéo khó lần theo.
- Khi kết quả khác mong đợi, kiểm tra cả điều kiện kích hoạt **và** vị trí nguồn trong thứ tự ưu tiên.

Một biểu thức đúng chỉ là điều kiện cần để tài liệu được nạp; nó chưa đủ để bảo đảm thuộc tính trong tài liệu đó trở thành giá trị cuối cùng mà bean nhận.

## 14. Thực hành phủ định có ngoặc

Xem ba biểu thức:

```text
A. !(prod | staging)
B. !prod & !staging
C. !prod | !staging
```

A và B tương đương: cả hai chỉ đúng khi **không có prod và không có staging**.

C khác: chỉ cần thiếu **ít nhất một** trong hai profile là đúng. Vì thế, với active profiles chỉ có `prod`, C đúng do `!staging`; trong khi A và B sai.

Một ví dụ khác:

```text
D. !(prod & cloud)
E. !prod | !cloud
F. !prod & !cloud
```

D và E tương đương: điều kiện chỉ sai khi **cả prod và cloud** hoạt động. F khắt khe hơn: cả prod và cloud đều phải vắng mặt.

Cần nhớ các quy tắc logic De Morgan:

```text
!(A | B) == !A & !B
!(A & B) == !A | !B
```

Đây là những quy tắc logic, không phải hành vi riêng của Spring. Nhưng khi đưa chúng vào biểu thức profile, **dấu ngoặc càng quan trọng** vì vừa giúp người đọc hiểu đúng, vừa giúp tránh lỗi khi trộn AND với OR.

## 15. Tình huống vận hành: điều kiện nào nên diễn đạt bằng profile?

Giả sử nhóm triển khai có những ngữ cảnh độc lập:

- `dev`, `staging`, `prod`: giai đoạn của môi trường.
- `cloud`: ứng dụng chạy trên hạ tầng cloud.
- `local`: ứng dụng chạy tại máy cá nhân.
- `metrics`: cho phép một chế độ đo đạc thử nghiệm.

Một số nhu cầu có thể diễn đạt:

| Nhu cầu | Biểu thức phù hợp |
| --- | --- |
| Chỉ dev và không phải cloud | `dev & !cloud` |
| Staging hoặc prod | `staging | prod` |
| Cloud ở staging hoặc prod | `(staging | prod) & cloud` |
| Không phải prod | `!prod` |
| Không thuộc staging và prod | `!(staging | prod)` |
| Prod có metrics nhưng không local | `prod & metrics & !local` |

Tuy nhiên, **không phải mọi lựa chọn đều nên được mô hình hóa thành một profile**. Nếu `metrics` chỉ là cờ bật/tắt nhỏ và có thể đổi độc lập, một thuộc tính như `observability.metrics-enabled=true` có thể đơn giản hơn tạo thêm profile. Nếu một giá trị thay đổi theo từng người dùng hoặc theo từng yêu cầu, đó cũng thường là dữ liệu nghiệp vụ, không phải Spring profile.

Dùng biểu thức khi các tên profile đã có ý nghĩa rõ ràng và thật sự cần điều kiện kết hợp. Mỗi biểu thức nên diễn đạt một quy tắc đủ ngắn để người vận hành có thể dự đoán từ tập profile hoạt động.

## 16. Phân biệt tên profile với biểu thức có toán tử

Một tên profile như `prod-cloud` chỉ là **một tên**. Nó không có ý nghĩa logic “prod và cloud” trừ khi ứng dụng chủ động kích hoạt tên `prod-cloud` hoặc thiết kế profile group cụ thể.

Trái lại:

```text
prod & cloud
```

là biểu thức đúng khi **hai tên riêng biệt** cùng hoạt động.

Một profile group trong Spring Boot có thể cho phép một tên cấp cao kích hoạt nhiều profile thành viên. Ví dụ một nhóm `production` có thể làm `prod` và `cloud` cùng hoạt động nếu ứng dụng khai báo như vậy tại vị trí hợp lệ. Sau khi các profile thành viên đã hoạt động, biểu thức `prod & cloud` sẽ khớp.

Nhưng **profile group** khác với **biểu thức điều kiện**:

- Profile group giúp định nghĩa *kích hoạt những tên nào cùng nhau*.
- Biểu thức `on-profile` hoặc `@Profile` giúp định nghĩa *khi nào một tài liệu hoặc bean được áp dụng*.

Đừng trộn hai trách nhiệm bằng cách đặt logic kích hoạt vào bên trong tài liệu chỉ được nạp khi biểu thức đã khớp.

## 17. Những lỗi hay gặp khi triển khai

### 17.1. Quên dấu nháy quanh ! trong YAML

Ví dụ dễ sai:

```yaml
spring:
  config:
    activate:
      on-profile: !prod
```

YAML có thể hiểu `!prod` như cú pháp tag, gây lỗi phân tích tài liệu. Hãy viết:

```yaml
spring:
  config:
    activate:
      on-profile: "!prod"
```

Trích dẫn toàn bộ biểu thức cũng giúp người đọc nhận ra đây là một chuỗi điều kiện, đặc biệt với dấu `&` và `|`.

### 17.2. Trộn AND và OR thiếu ngoặc

Không viết `prod & cloud | staging`. Thay bằng `(prod & cloud) | staging` hoặc `prod & (cloud | staging)` tùy ý nghĩa thực sự. Không đoán thứ tự ưu tiên toán tử theo ngôn ngữ lập trình khác.

### 17.3. Dùng !prod để chỉ dev

`!prod` đúng cả ở `staging`, `test` và nhiều trạng thái khác. Nếu chỉ muốn dev, dùng `dev`; nếu muốn dev không cloud, dùng `dev & !cloud`.

### 17.4. Kỳ vọng biểu thức tự kích hoạt profile

`on-profile: "prod & cloud"` chỉ đánh giá các profile đã hoạt động. Nó không tự bật `prod` và `cloud`. Cần truyền `--spring.profiles.active=prod,cloud` hoặc cấp profile bằng cơ chế khởi động thích hợp.

### 17.5. Nhầm on-profile và Java @Profile

`on-profile` chỉ điều kiện hóa tài liệu Config Data. Nó không trực tiếp bật/tắt một bean Java nếu bean đó không có cơ chế điều kiện riêng. Ngược lại, `@Profile` trên bean không tự tạo hoặc xóa một file YAML. Cả hai cùng đánh giá profile nhưng tác động lên đối tượng khác nhau.

### 17.6. Nhầm có hiệu lực với thắng ưu tiên

Một tài liệu có thể được nạp đúng theo `on-profile` nhưng giá trị của nó vẫn bị biến môi trường, command line hoặc Config Data có ưu tiên cao hơn ghi đè. Khi chẩn đoán, kiểm tra theo thứ tự: profile đang hoạt động → điều kiện nào đúng → những nguồn nào cung cấp khóa → nguồn nào có giá trị cuối cùng.

### 17.7. Mong profile đổi ngay khi tiến trình đang chạy

Các tài liệu cấu hình theo profile thường được nạp lúc ứng dụng khởi động. Thay biến môi trường hoặc file YAML sau khi bean đã được tạo không tự làm Spring Boot đánh giá lại mọi biểu thức và liên kết lại mọi giá trị. Một lần thử nghiệm mới nên khởi động một tiến trình mới, hoặc dự án phải có cơ chế cập nhật cấu hình được thiết kế riêng.

## 18. Bài tập tự đánh giá

### Bài tập 1: Chọn biểu thức

Đối với mỗi yêu cầu, hãy viết một biểu thức hợp lệ:

1. Chỉ nạp khi `prod` hoặc `staging` hoạt động.
2. Chỉ nạp khi `dev` hoạt động nhưng `cloud` không hoạt động.
3. Chỉ nạp khi có `cloud` và ít nhất một trong `prod`, `staging`.
4. Chỉ nạp khi không có cả `prod` lẫn `staging`.
5. Nạp khi `prod` hoạt động, hoặc khi cả `staging` và `cloud` hoạt động.

Đáp án tham khảo:

```text
1. prod | staging
2. dev & !cloud
3. cloud & (prod | staging)
4. !(prod | staging)
5. prod | (staging & cloud)
```

### Bài tập 2: Đánh giá tổ hợp profile

Cho biểu thức:

```text
(dev | staging) & !cloud
```

Hãy đánh giá kết quả với các tập profile:

| Active profiles | Kết quả |
| --- | --- |
| `dev` | Đúng |
| `staging` | Đúng |
| `dev,cloud` | Sai |
| `staging,cloud` | Sai |
| `prod` | Sai |
| `dev,staging` | Đúng |

Giải thích: phải có ít nhất một trong `dev/staging`, đồng thời không được có `cloud`.

### Bài tập 3: Phân biệt hai cách nhóm

Hai biểu thức:

```text
A: (prod | staging) & cloud
B: prod | (staging & cloud)
```

Với chỉ `prod` hoạt động, A sai còn B đúng. Với chỉ `staging,cloud` hoạt động, cả A và B đều đúng. Hãy tự lập bảng cho `cloud`, `prod,cloud`, `prod,staging` và `dev,cloud`.

### Bài tập 4: Tài liệu YAML nhiều điều kiện

Cho file:

```yaml
feature:
  mode: base

---
spring:
  config:
    activate:
      on-profile: "dev | test"
feature:
  mode: development

---
spring:
  config:
    activate:
      on-profile: "prod & cloud"
feature:
  mode: managed
```

Dự đoán `feature.mode` khi chạy lần lượt với:

- Không có active profile: `base`.
- `dev`: `development`.
- `test`: `development`.
- `prod`: `base`.
- `prod,cloud`: `managed`.

Trong các tình huống trên không có hai tài liệu có điều kiện cùng khai báo khóa và cùng đúng. Vì vậy, kết quả phụ thuộc trực tiếp vào điều kiện của từng tài liệu, miễn là không có nguồn ưu tiên cao hơn.

### Bài tập 5: Dò lỗi cấu hình

Một tài liệu chứa:

```yaml
spring:
  config:
    activate:
      on-profile: "prod & cloud | metrics"
```

Yêu cầu: tài liệu được nạp nếu (`prod` và `cloud`) hoặc có `metrics`. Hãy sửa thành:

```yaml
spring:
  config:
    activate:
      on-profile: "(prod & cloud) | metrics"
```

Nếu yêu cầu thay đổi thành “có prod và (cloud hoặc metrics)”, phải viết `prod & (cloud | metrics)`. Chỉ thay vị trí dấu ngoặc đã làm thay đổi hành vi.

## 19. Cách ghi nhớ dễ áp dụng

Biểu thức profile là một **câu hỏi logic về tập profile đang hoạt động**.

- `!A`: A có vắng mặt không?
- `A & B`: A và B có cùng hoạt động không?
- `A | B`: có ít nhất một trong A, B hoạt động không?
- `(A | B) & C`: C có hoạt động, và ít nhất một trong A/B cũng hoạt động không?

Khi viết điều kiện cho tài liệu YAML, đặt biểu thức ở `spring.config.activate.on-profile`, **trích dẫn chuỗi** và dùng **ngoặc tường minh** khi phối hợp AND với OR. Khi viết điều kiện cho bean Java, dùng `@Profile("...")` với cùng ý nghĩa logic.

Luồng xử lý có thể hình dung:

```text
Chọn active profiles lúc khởi động
                |
                v
Đánh giá biểu thức on-profile
                |
        +-------+-------+
        |               |
      true            false
        |               |
 Nạp tài liệu       Không nạp
        |
        v
Tham gia thứ tự ưu tiên PropertySource
        |
        v
Giá trị có hiệu lực được liên kết vào bean
```

Quan trọng nhất: **một biểu thức đúng quyết định tài liệu có được tham gia hay không, còn thứ tự nguồn cấu hình quyết định giá trị cuối cùng**. Phân biệt được hai bước này sẽ giúp giải thích chính xác vì sao một cấu hình theo profile đã “đúng điều kiện” nhưng bean vẫn nhận giá trị khác.

Tham khảo thêm: [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html), [Spring Boot — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html), và tài liệu Spring Framework về biểu thức `@Profile` và `Profiles.of(...)`.
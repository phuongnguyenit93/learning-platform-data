# application-{profile}.properties hoặc YAML tương ứng

Trong ứng dụng Spring Boot, cùng một mã nguồn thường phải hoạt động trong nhiều môi trường: máy lập trình viên, môi trường kiểm thử, staging và production. Những môi trường này có thể dùng URL dịch vụ khác nhau, mức logging khác nhau, timeout khác nhau hoặc bật những tính năng khác nhau. Nếu phải sửa code Java mỗi lần triển khai, cấu hình sẽ nhanh chóng trở nên khó kiểm soát.

Spring Boot giải quyết nhu cầu này bằng **Spring Profiles** kết hợp với hệ thống **externalized configuration**. Một quy ước đặc biệt quan trọng là file **`application-{profile}.properties`** hoặc **`application-{profile}.yml` / `application-{profile}.yaml`**. Khi một profile được kích hoạt, Spring Boot có thể nạp file cấu hình tương ứng và dùng các giá trị trong đó để bổ sung hoặc ghi đè những giá trị cấu hình chung.

Ví dụ:

```text
src/main/resources/
├── application.yml
├── application-dev.yml
├── application-test.yml
└── application-prod.yml
```

Trong trường hợp thông thường:

- `application.yml` chứa giá trị áp dụng chung.
- `application-dev.yml` chứa giá trị dành cho profile `dev`.
- `application-test.yml` chứa giá trị dành cho profile `test`.
- `application-prod.yml` chứa giá trị dành cho profile `prod`.

**Tên file không tự kích hoạt profile.** File `application-prod.yml` chỉ được sử dụng như cấu hình theo profile khi profile `prod` được chọn theo cơ chế cấu hình của Spring Boot. Bài học này thuộc chương **Profile** của *Spring Boot Fundamentals*, tập trung vào quy ước tên file, cách kích hoạt, thứ tự ưu tiên, cách kết hợp properties và YAML, các lỗi thường gặp và phương pháp kiểm thử cấu hình.

## 1. Profile là gì và giải quyết bài toán nào?

**Profile** là một nhãn môi trường/ngữ cảnh cấu hình mà Spring có thể dùng để lựa chọn bean hoặc cấu hình phù hợp. Các tên thường gặp:

- `dev`: phát triển trên máy cá nhân.
- `test`: chạy integration tests.
- `staging`: môi trường gần giống production để thử nghiệm.
- `prod`: môi trường production.
- `cloud`: một tập cấu hình chung cho môi trường cloud.
- `batch`: một loại hình chạy tác vụ nền.

Đó chỉ là những tên minh họa. Spring không áp đặt rằng profile bắt buộc phải tên `dev` hoặc `prod`; đội ngũ có thể chọn tên diễn đạt đúng cách triển khai.

Giả sử một ứng dụng gọi API đối tác:

| Thuộc tính | Development | Production |
| --- | --- | --- |
| Base URL | Dịch vụ giả lập trên localhost | Dịch vụ đối tác thực tế |
| Connect timeout | 1 giây | 5 giây |
| Log nghiệp vụ | DEBUG | INFO hoặc WARN |
| Chế độ gửi thông báo | Console | Hệ thống gửi thông báo thật |

Logic nghiệp vụ không cần hard-code các giá trị này. Chỉ cần sử dụng cấu hình được Spring Boot bind vào bean hoặc đọc qua `Environment`; profile quyết định nguồn giá trị được lựa chọn.

### 1.1. Cấu hình theo profile khác bean theo profile

Spring có hai cách phổ biến sử dụng profile:

1. **File cấu hình theo profile:** `application-dev.yml` cung cấp property values khi `dev` active.
2. **Bean theo profile:** `@Profile("dev")` cho phép đăng ký một cấu hình hoặc bean chỉ trong profile phù hợp.

Hai cơ chế dùng chung khái niệm active profiles nhưng có trách nhiệm khác nhau:

- File profile-specific quyết định **giá trị cấu hình**.
- `@Profile` quyết định **bean definition có được đăng ký** hay không.

Chỉ vì có `application-dev.yml` không đồng nghĩa mọi bean sẽ tự thay implementation. Ngược lại, `@Profile("dev")` không bắt buộc phải có file `application-dev.yml`.

## 2. Cú pháp tên file application-{profile}

Với base name mặc định `application`, Spring Boot tìm các file cấu hình chung và biến thể theo profile.

| File | Vai trò |
| --- | --- |
| `application.properties` | Cấu hình chung dạng Java properties |
| `application.yml` | Cấu hình chung dạng YAML |
| `application.yaml` | Cấu hình chung dạng YAML, đuôi đầy đủ |
| `application-dev.properties` | Cấu hình dành cho profile `dev` |
| `application-dev.yml` | Cấu hình YAML dành cho `dev` |
| `application-dev.yaml` | Tương tự đuôi `.yml`, dành cho `dev` |
| `application-prod.properties` | Cấu hình dành cho profile `prod` |
| `application-prod.yml` | Cấu hình YAML dành cho profile `prod` |

Phần nằm giữa `application-` và extension là **tên profile**, không phải tên package Java hay tên database.

Ví dụ:

```text
application-local.yml     -> profile "local"
application-qa.properties -> profile "qa"
application-blue.yaml     -> profile "blue"
```

### 2.1. Đuôi .yml và .yaml

`.yml` và `.yaml` đều biểu diễn YAML. Spring Boot hỗ trợ cả hai trong hệ thống cấu hình thông thường. Đội dự án nên chọn một quy ước nhất quán để tránh tạo hai file có cùng mục đích rồi không biết file nào được ưu tiên.

### 2.2. Không nhất thiết phải có đủ file cho mọi profile

Nếu ứng dụng chỉ cần khác biệt giữa `dev` và `prod`, có thể chỉ cần:

```text
application.yml
application-dev.yml
application-prod.yml
```

Không có `application-test.yml` không mặc nhiên là lỗi. Khi chạy với profile `test`, các giá trị chung vẫn có thể đến từ `application.yml` và những nguồn cấu hình khác. Chỉ khi ứng dụng yêu cầu property chưa có giá trị phù hợp mới phát sinh vấn đề ở bước bind hoặc sử dụng.

### 2.3. Tên file không kích hoạt profile

Đây là điểm rất quan trọng:

```text
Có file application-prod.yml
          ≠
Profile prod đang active
```

Nếu không kích hoạt `prod` theo cơ chế tương ứng, Spring Boot không tự chọn `application-prod.yml` chỉ vì file có trong `resources`.

## 3. Cấu hình chung và cấu hình theo profile

Xét một ứng dụng có file chung:

```properties
# src/main/resources/application.properties
spring.application.name=catalog-service

app.notification.mode=console
app.notification.timeout=3s
app.notification.retry-count=2

logging.level.com.example.catalog=INFO
```

Trong development:

```properties
# src/main/resources/application-dev.properties
app.notification.timeout=1s
logging.level.com.example.catalog=DEBUG
```

Trong production:

```properties
# src/main/resources/application-prod.properties
app.notification.mode=remote
app.notification.timeout=5s
logging.level.com.example.catalog=WARN
```

Giả sử chỉ profile `dev` active. Những giá trị cuối cùng có thể được hiểu như sau:

| Key | Giá trị chung | Giá trị dev | Kết quả khi dev active |
| --- | --- | --- | --- |
| `spring.application.name` | `catalog-service` | Không khai báo | `catalog-service` |
| `app.notification.mode` | `console` | Không khai báo | `console` |
| `app.notification.timeout` | `3s` | `1s` | `1s` |
| `app.notification.retry-count` | `2` | Không khai báo | `2` |
| `logging.level.com.example.catalog` | `INFO` | `DEBUG` | `DEBUG` |

Spring Boot không cần bản sao đầy đủ của tất cả thuộc tính trong mỗi file. File theo profile thường chỉ chứa **những giá trị khác biệt so với cấu hình chung**.

Khi chỉ profile `prod` active, `mode` thành `remote`, `timeout` thành `5s` và log level thành `WARN`. `retry-count` vẫn lấy giá trị chung vì không bị ghi đè.

### 3.1. Đây là cơ chế bổ sung và ghi đè property

Với những scalar properties như chuỗi, số, boolean hoặc duration, cấu hình theo profile có thể ghi đè key cùng tên được khai báo trong file chung ở cùng nhóm vị trí cấu hình.

Tuy nhiên, hệ thống externalized configuration của Spring Boot còn nhiều nguồn khác: biến môi trường, JVM system properties, command-line arguments và file cấu hình bên ngoài JAR. **Profile-specific không phải nguồn có độ ưu tiên tuyệt đối trước mọi nguồn khác.**

Ví dụ, với cách chạy:

```bash
java -jar catalog-service.jar --spring.profiles.active=prod --app.notification.timeout=10s
```

Giá trị `app.notification.timeout=10s` từ command line thông thường được ưu tiên hơn giá trị `5s` trong `application-prod.properties`.

### 3.2. Chỉ ghi đè thứ cần thay đổi

Nếu `app.notification.retry-count` luôn bằng 2, hãy để trong file chung. Nếu copy cùng một property vào ba file, mỗi lần thay đổi phải sửa ở nhiều nơi và dễ tạo drift giữa môi trường.

Một mẫu tốt:

```text
application.properties       -> giá trị mặc định có thể dùng rộng rãi
application-dev.properties   -> phần chỉ khác ở development
application-prod.properties  -> phần chỉ khác ở production
```

Không nên lạm dụng profile files để lặp lại toàn bộ cấu hình ứng dụng.

## 4. Viết cấu hình tương đương bằng YAML

Các ví dụ `.properties` ở trên có thể chuyển sang YAML.

File chung:

```yaml
# src/main/resources/application.yml
spring:
  application:
    name: catalog-service

app:
  notification:
    mode: console
    timeout: 3s
    retry-count: 2

logging:
  level:
    com.example.catalog: INFO
```

File development:

```yaml
# src/main/resources/application-dev.yml
app:
  notification:
    timeout: 1s

logging:
  level:
    com.example.catalog: DEBUG
```

File production:

```yaml
# src/main/resources/application-prod.yml
app:
  notification:
    mode: remote
    timeout: 5s

logging:
  level:
    com.example.catalog: WARN
```

Cả hai phong cách mô tả cùng các property keys:

```text
Properties: app.notification.timeout=5s

YAML:
  app:
    notification:
      timeout: 5s
```

Spring Boot “làm phẳng” cấu trúc YAML thành các tên property thích hợp để bind vào bean cấu hình.

### 4.1. Lưu ý về thụt dòng YAML

YAML dựa vào indentation. Ví dụ sai:

```yaml
app:
  notification:
  timeout: 5s
```

Đoạn trên đặt `timeout` ngang cấp với `notification`, không phải thuộc nhóm `app.notification` như mong muốn.

Đoạn đúng:

```yaml
app:
  notification:
    timeout: 5s
```

Hãy dùng spaces nhất quán, tránh tab trong indentation. Nếu cấu hình không có tác dụng, kiểm tra cấu trúc YAML và tên property trước khi nghi ngờ profile.

### 4.2. Dấu hai chấm, dấu # và chuỗi đặc biệt

YAML có ký hiệu riêng. Khi giá trị chứa những ký tự có ý nghĩa cú pháp hoặc có thể bị suy diễn kiểu, nên quote:

```yaml
app:
  notification:
    label: "Catalog: Production"
    marker: "value # not a comment"
```

Đừng nhầm key YAML với biểu thức Java. Spring Boot xử lý cấu hình rồi mới cung cấp giá trị cho bean hoặc `Environment`.

### 4.3. Có cần chuyển từ .properties sang YAML không?

Không bắt buộc. Chọn dựa trên độ phức tạp:

| Tiêu chí | .properties | YAML |
| --- | --- | --- |
| Cú pháp | `key=value` | Phân cấp theo indentation |
| Dễ đọc khi ít key | Rất thuận tiện | Thuận tiện |
| Dễ biểu diễn cấu trúc lồng nhau | Tên key dài hơn | Gọn và trực quan |
| Rủi ro indentation | Thấp | Cần cẩn thận |
| Danh sách / map | Cần quy ước tên key | Có cú pháp tự nhiên |
| Cấu hình nhiều tài liệu trong một file | Có cú pháp multi-document riêng | `---` rõ ràng |

Không có phong cách nào làm profile “mạnh” hơn. Chúng chỉ khác cách biểu diễn.

## 5. Cách kích hoạt profile

Spring Boot chỉ biết cần nạp file `application-{profile}.*` khi profile đó được xác định là active hoặc default theo quy tắc của Spring.

### 5.1. Qua command line

```bash
java -jar catalog-service.jar --spring.profiles.active=dev
```

Khi chạy như vậy, Spring Boot có thể nạp:

```text
application.yml
application-dev.yml
```

cùng những cấu hình khác trong các location được hỗ trợ.

Đổi sang production:

```bash
java -jar catalog-service.jar --spring.profiles.active=prod
```

Không cần sửa mã Java hoặc đổi tên file.

### 5.2. Qua biến môi trường

Trên Linux/macOS:

```bash
SPRING_PROFILES_ACTIVE=prod java -jar catalog-service.jar
```

Trên Windows PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
java -jar catalog-service.jar
```

Biến `SPRING_PROFILES_ACTIVE` tương ứng với property `spring.profiles.active` theo cơ chế environment-property mapping của Spring Boot.

Đây là cách thường dùng trong container, CI/CD và môi trường triển khai, nơi code và artifact giống nhau nhưng môi trường cung cấp giá trị profile khác nhau.

### 5.3. Qua cấu hình chung

Có thể khai báo trong `application.properties`:

```properties
spring.profiles.active=dev
```

Hoặc trong `application.yml`:

```yaml
spring:
  profiles:
    active: dev
```

Khi ứng dụng được deploy, biến môi trường hoặc command-line argument có thể ghi đè giá trị này theo thứ tự ưu tiên cấu hình. Tuy nhiên, **hard-code `dev` làm active profile trong artifact dùng chung cho production thường không phải lựa chọn tốt**. Nên để profile do môi trường deploy quyết định, trừ khi ứng dụng có lý do đặc biệt.

### 5.4. Qua Java API

Khi cần launcher kiểm soát profile theo chương trình, có thể thêm profile trước khi chạy:

```java
public static void main(String[] args) {
    SpringApplication application =
            new SpringApplication(CatalogApplication.class);
    application.setAdditionalProfiles("batch");
    application.run(args);
}
```

`setAdditionalProfiles` bổ sung profile cho ứng dụng. Nó không hoàn toàn giống việc đặt `spring.profiles.active`, vốn là property có thể chịu ảnh hưởng từ những property sources khác nhau.

Trong phần lớn hệ thống triển khai, nên ưu tiên command-line args hoặc environment variables thay vì cố định profile trong code.

## 6. Profile active và profile mặc định

Nếu không cấu hình active profiles, Spring sử dụng tập default profiles. Tên default profile thông thường là `default`.

Điều này có hệ quả đáng chú ý: file **`application-default.properties`** hoặc **`application-default.yml`** có thể được nạp khi không có active profile nào.

Ví dụ:

```text
application.yml
application-default.yml
application-dev.yml
application-prod.yml
```

Nếu không có active profiles, cấu hình default có thể được áp dụng. Nếu kích hoạt `dev`, cấu hình dành cho `dev` được áp dụng theo cơ chế active profile.

### 6.1. Cấu hình default profile

Trong cấu hình chung có thể đặt:

```properties
spring.profiles.default=local
```

Khi không có active profile, `local` được dùng như default profile, nên `application-local.properties` hoặc biến thể YAML tương ứng có thể được nạp.

**Default profile không phải active profile được tự thêm vào mọi lần chạy.** Nó có vai trò khi không có active profiles. Nếu ứng dụng có active profile `prod`, đừng giả định profile `local` cũng đang được áp dụng chỉ vì `spring.profiles.default=local`.

### 6.2. Tránh mặc định không an toàn

Một giá trị như `spring.profiles.default=local` có thể thuận tiện khi chạy máy cá nhân, nhưng nếu deployment quên thiết lập `SPRING_PROFILES_ACTIVE` thì ứng dụng production có thể chạy với cấu hình local.

Đối với hệ thống quan trọng, có thể yêu cầu môi trường xác định profile rõ ràng, validate cấu hình tại startup và không cung cấp giá trị fallback gây nguy hiểm.

## 7. Thứ tự ưu tiên: file chung, file profile và nguồn bên ngoài

Đây là phần dễ phát sinh lỗi nhất vì **profile file chỉ là một lớp trong hệ thống Config Data** của Spring Boot.

### 7.1. Trong cùng một location

Với một location đang được Spring Boot tìm kiếm, file cấu hình profile-specific có thể ghi đè những property trùng key trong file chung.

Ví dụ:

```properties
# application.properties
app.feature.enabled=false
```

```properties
# application-prod.properties
app.feature.enabled=true
```

Khi profile `prod` active và không có nguồn độ ưu tiên cao hơn ghi đè, giá trị cuối của `app.feature.enabled` là `true`.

### 7.2. File bên ngoài JAR

Spring Boot mặc định tìm config data từ những vị trí phổ biến trên classpath và trên filesystem, ví dụ các vị trí `classpath:/`, `classpath:/config/`, `./`, `./config/` và một số location mở rộng theo quy tắc cấu hình của Boot.

Hình dung:

```text
artifact.jar
  └── BOOT-INF/classes/application.yml
  └── BOOT-INF/classes/application-prod.yml

./config/
  └── application-prod.yml
```

File bên ngoài JAR có thể ghi đè các giá trị từ file đóng gói bên trong JAR theo cơ chế precedence mặc định. Đây là nền tảng của externalized configuration: cùng một artifact, mỗi môi trường cung cấp dữ liệu cấu hình ngoài phù hợp.

**Không nên suy luận precedence chỉ dựa trên phần tên `-prod`.** Cần biết location, loại nguồn và các override được cung cấp khi khởi động.

### 7.3. Các nguồn có độ ưu tiên cao

Trong mô hình cấu hình Spring Boot thông thường, command-line properties và environment variables có thể ghi đè những giá trị trong Config Data files.

Ví dụ:

```text
Trong JAR:
  application-prod.yml    app.notification.timeout=5s

Trong environment:
  APP_NOTIFICATION_TIMEOUT=8s

Trong CLI:
  --app.notification.timeout=10s

Giá trị được resolve:
  10s (nếu không có nguồn ưu tiên cao hơn can thiệp)
```

Đây là ví dụ khái quát về precedence; hệ thống còn hỗ trợ các nguồn khác như system properties, JSON cấu hình, test properties và những cơ chế chuyên biệt. Khi gặp sai khác, cần xem property source và origin thực tế thay vì cố nhớ toàn bộ thứ tự dưới dạng một câu đơn.

### 7.4. File .properties và YAML cùng tên ở cùng location

Nếu cùng một location có cả `application-prod.properties` và `application-prod.yml`, trong Spring Boot thông thường **file `.properties` được ưu tiên hơn file YAML** đối với những property trùng nhau.

Ví dụ:

```text
config/
├── application-prod.properties
└── application-prod.yml
```

Đây là tình huống nên tránh: người bảo trì có thể sửa YAML nhưng không thấy tác dụng vì property cùng key trong `.properties` đang thắng.

Khuyến nghị: **mỗi nhóm cấu hình tại một location nên chọn một định dạng** nếu không có yêu cầu tích hợp đặc biệt.

## 8. Nhiều active profiles cùng lúc

Spring cho phép kích hoạt nhiều profile:

```bash
java -jar catalog-service.jar --spring.profiles.active=prod,cloud
```

Khi đó Boot có thể nạp:

```text
application.yml
application-prod.yml
application-cloud.yml
```

Đây là một cách tách cấu hình theo nhiều trục:

- `prod`: chính sách production.
- `cloud`: giá trị dành cho môi trường cloud.

### 8.1. Profile được liệt kê sau có thể thắng khi cùng key

Giả sử:

```yaml
# application-prod.yml
app:
  http:
    timeout: 4s
```

```yaml
# application-cloud.yml
app:
  http:
    timeout: 8s
```

Với `spring.profiles.active=prod,cloud`, trong các profile-specific files cùng location được xử lý theo quy tắc last-wins của Spring Boot, giá trị từ `cloud` có thể ghi đè giá trị từ `prod`.

Nếu đổi thành `spring.profiles.active=cloud,prod`, kết quả của property trùng key có thể đổi theo.

Đừng sử dụng nhiều profile tùy tiện nếu chúng cùng định nghĩa hàng loạt property gây xung đột. Cấu hình sẽ khó dự đoán và rủi ro khi bổ sung profile mới.

### 8.2. Sự hiện diện của profile không bảo đảm key có giá trị riêng

Không có `application-cloud.yml` cũng không làm profile `cloud` trở thành vô hiệu. Profile có thể được dùng cho `@Profile("cloud")` hoặc các tài liệu `spring.config.activate.on-profile`. File profile-specific là một cơ chế cung cấp property, không phải định nghĩa duy nhất của profile.

### 8.3. Mô hình nhiều trục cần rõ ý định

Ví dụ có thể chọn:

```text
prod + cloud
prod + onprem
dev + local
test + ci
```

Nhưng cần thiết kế ownership: key nào chỉ thuộc môi trường, key nào thuộc hạ tầng, có key nào bị ghi đè ở nhiều file không. Nếu `prod` và `cloud` đều đặt `app.http.timeout`, hãy ghi rõ precedence được kỳ vọng.

## 9. Các tài liệu YAML theo profile trong cùng một file

Ngoài cách tạo file `application-dev.yml` và `application-prod.yml`, Spring Boot còn hỗ trợ **multi-document YAML** với marker `---`. Mỗi document có thể được kích hoạt bằng `spring.config.activate.on-profile`.

Ví dụ:

```yaml
# application.yml: cấu hình chung
app:
  notification:
    mode: console
    timeout: 3s

---
spring:
  config:
    activate:
      on-profile: dev

app:
  notification:
    timeout: 1s

---
spring:
  config:
    activate:
      on-profile: prod

app:
  notification:
    mode: remote
    timeout: 5s
```

Ý nghĩa:

- Document đầu tiên không có activation condition nên cung cấp cấu hình chung.
- Document thứ hai chỉ được áp dụng khi `dev` khớp.
- Document thứ ba chỉ được áp dụng khi `prod` khớp.

Đây là lựa chọn thay thế cho nhiều file tách riêng khi số lượng cấu hình nhỏ. Với project lớn, file `application-{profile}.yml` thường thuận tiện hơn để phân chia trách nhiệm.

### 9.1. on-profile hỗ trợ biểu thức profile

Có thể dùng biểu thức profile:

```yaml
spring:
  config:
    activate:
      on-profile: "prod & cloud"
```

Document này được áp dụng khi biểu thức yêu cầu cả `prod` và `cloud` cùng phù hợp.

Một ví dụ khác:

```yaml
spring:
  config:
    activate:
      on-profile: "!prod"
```

Document khớp khi `prod` không active theo ngữ nghĩa profile expression. Khi viết expression, nên quote để tránh xung đột với cú pháp YAML.

### 9.2. on-profile không kích hoạt profile

`spring.config.activate.on-profile=prod` có nghĩa **“chỉ áp dụng document này khi profile prod phù hợp”**, không có nghĩa “đặt prod làm active profile”.

Nếu muốn active `prod`, hãy dùng property `spring.profiles.active` từ một nguồn cấu hình hợp lệ, environment hoặc command-line.

### 9.3. Không lặp lại cùng cấu hình ở nhiều nơi nếu không cần

Nếu project đã có `application-prod.yml`, việc lại định nghĩa cùng key trong một document `on-profile: prod` của `application.yml` có thể khiến người bảo trì khó tìm nguồn thắng.

Hãy chọn một chiến lược:

- Một file chung + các file `application-{profile}.*`.
- Hoặc một file YAML nhiều document cho những cấu hình ít và rõ ràng.

Có thể kết hợp, nhưng chỉ khi đã quy định ownership và thứ tự ưu tiên.

## 10. Vị trí hợp lệ để đặt spring.profiles.active

Một quy tắc quan trọng trong hệ thống Config Data của Spring Boot hiện đại là những thuộc tính xác định **profile nào được kích hoạt** phải được khai báo ở nơi hợp lệ, không phải trong chính file chỉ được nạp sau khi profile đó đã active.

### 10.1. Cấu hình đúng

Trong file chung `application.properties`:

```properties
spring.profiles.active=dev
```

Hoặc từ command line:

```bash
java -jar app.jar --spring.profiles.active=dev
```

Hoặc từ environment:

```bash
SPRING_PROFILES_ACTIVE=dev java -jar app.jar
```

### 10.2. Đừng đặt active trong application-prod.yml

Ví dụ cấu hình sai:

```yaml
# application-prod.yml
spring:
  profiles:
    active: prod
```

Spring Boot hiện đại không cho phép `spring.profiles.active` ở profile-specific resource hoặc document đã được kích hoạt bằng `spring.config.activate.on-profile`. Điều này tránh vòng lặp logic: phải biết profile nào active mới nạp file, nhưng file lại tìm cách thay đổi tập active profiles.

Trong các phiên bản Spring Boot dùng Config Data, tình huống này có thể gây lỗi kiểu `InvalidConfigDataPropertyException` trong quá trình startup.

### 10.3. Đừng đặt active trong document có on-profile

Ví dụ sai:

```yaml
spring:
  config:
    activate:
      on-profile: dev
  profiles:
    active: prod
```

Document này chỉ được áp dụng sau khi `dev` đã khớp nhưng lại cố đặt active profile mới. Cách thiết kế đó không được phép trong quy tắc Config Data hiện đại.

### 10.4. default, include và group cũng có quy tắc riêng

Các thuộc tính `spring.profiles.default`, `spring.profiles.include` và `spring.profiles.group.*` cũng cần được đặt trong các nguồn **không phải profile-specific** theo những quy tắc tương ứng. Không nên chuyển chúng vào `application-prod.yml` hoặc document `on-profile: prod` với kỳ vọng Boot sẽ thay đổi tập profile trong lúc nạp.

Hãy nghĩ tới hai giai đoạn:

1. Xác định tập profiles cần xử lý.
2. Tải những profile-specific config data liên quan.

Tách các trách nhiệm này giúp cấu hình có kết quả nhất quán.

## 11. spring.profiles.include và profile groups

Khi một profile luôn kéo theo các profile khác, Spring Boot có cơ chế khai báo bổ sung.

### 11.1. spring.profiles.include

Trong cấu hình chung:

```properties
spring.profiles.include=common-observability
```

Thuộc tính này dùng để **bổ sung** profile vào tập profile được xử lý, thay vì chỉ là một cách thay thế `spring.profiles.active`.

Không nên dùng include như một chuỗi điều kiện rối rắm; nó phù hợp khi có một tập cấu hình chung được áp dụng cùng các profile khác.

### 11.2. Profile groups

Có thể khai báo nhóm profile trong cấu hình không profile-specific:

```properties
spring.profiles.group.production[0]=prod
spring.profiles.group.production[1]=cloud
spring.profiles.group.production[2]=observability
```

Khi kích hoạt nhóm:

```bash
java -jar app.jar --spring.profiles.active=production
```

Spring Boot có thể mở rộng tập profiles để bao gồm các thành viên `prod`, `cloud`, `observability`. Nhờ đó, người vận hành chỉ chọn một nhãn profile cấp cao.

YAML tương đương:

```yaml
spring:
  profiles:
    group:
      production:
        - prod
        - cloud
        - observability
```

### 11.3. Khi nào nên dùng group?

Nhóm profile phù hợp khi các tập cấu hình có thể tái sử dụng và có tên rõ. Ví dụ:

- `production` gồm `prod` + `observability`.
- `local-integration` gồm `dev` + `mock-services`.

Nhưng không nên tạo hàng loạt nhóm lồng nhau thiếu tài liệu vì sẽ khó tìm lý do một file profile-specific nào đó được nạp.

## 12. Kết hợp profile files với @Profile

Giả sử ứng dụng có hai implementation cho cùng một interface:

```java
public interface MessageSender {
    void send(String message);
}
```

Implementation dành cho phát triển:

```java
@Component
@Profile("dev")
public class ConsoleMessageSender implements MessageSender {

    @Override
    public void send(String message) {
        System.out.println("[DEV] " + message);
    }
}
```

Implementation production:

```java
@Component
@Profile("prod")
public class RemoteMessageSender implements MessageSender {

    @Override
    public void send(String message) {
        // Gửi qua dịch vụ external đã được cấu hình.
    }
}
```

Cấu hình theo profile có thể cung cấp timeout/endpoint cho các implementation:

```yaml
# application-prod.yml
app:
  message:
    timeout: 5s
    endpoint: "https://messages.example.invalid/api"
```

Khi `prod` active:

1. Spring xử lý bean có `@Profile("prod")` phù hợp.
2. Config Data system nạp các property tương ứng với `prod`.
3. Bean nhận những property cần thiết qua `@ConfigurationProperties` hoặc cơ chế binding khác.

Tuy nhiên, nếu đồng thời active `dev` và `prod`, cả hai implementation có thể được đăng ký và constructor injection theo interface `MessageSender` có thể bị mơ hồ. Cần design profile combinations, `@Primary` hoặc qualifier phù hợp.

**Profile file không tự xử lý xung đột nhiều bean cùng type.** Profile và DI candidate resolution là hai cơ chế cần phối hợp.

## 13. Đọc giá trị profile-specific trong code Java

Spring Boot khuyến nghị dùng cấu hình có type rõ ràng cho một nhóm property liên quan.

### 13.1. Ví dụ với @ConfigurationProperties

File chung:

```yaml
# application.yml
app:
  downstream:
    base-url: "https://service.example.invalid"
    connect-timeout: 3s
```

File dev:

```yaml
# application-dev.yml
app:
  downstream:
    base-url: "http://localhost:9090"
    connect-timeout: 1s
```

File prod:

```yaml
# application-prod.yml
app:
  downstream:
    base-url: "https://api.partner.example.invalid"
    connect-timeout: 5s
```

Java record:

```java
package com.example.catalog.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.downstream")
public record DownstreamProperties(
        String baseUrl,
        Duration connectTimeout
) {
}
```

Trong Spring Boot với constructor binding cho record được hỗ trợ, có thể đăng ký bằng `@ConfigurationPropertiesScan` trên class khởi động:

```java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
```

Service sử dụng typed properties:

```java
package com.example.catalog.service;

import com.example.catalog.config.DownstreamProperties;
import org.springframework.stereotype.Service;

@Service
public class PartnerClientService {

    private final DownstreamProperties properties;

    public PartnerClientService(DownstreamProperties properties) {
        this.properties = properties;
    }

    public String target() {
        return properties.baseUrl();
    }
}
```

Với `dev`, `target()` nhận URL localhost; với `prod`, nó nhận URL production. Code Java không phải viết `if ("prod".equals(...))` để chọn URL.

### 13.2. Vì sao dùng Duration thay vì String?

Spring Boot Binder có khả năng chuyển các giá trị như `1s`, `500ms` hoặc `5m` thành `Duration`. Điều này giúp cấu hình có type rõ và tránh việc tự phân tích chuỗi trong nhiều service.

Nếu property được khai báo sai định dạng, ứng dụng có thể báo lỗi binding trong quá trình khởi tạo, thay vì dùng im lặng một giá trị không phù hợp.

### 13.3. @Value cho một property đơn giản

Khi chỉ đọc một property nhỏ:

```java
@Component
class GreetingPrinter {

    private final String banner;

    GreetingPrinter(@Value("${app.banner:Hello}") String banner) {
        this.banner = banner;
    }
}
```

Ví dụ dùng placeholder với giá trị mặc định `Hello`. Với nhiều property liên quan, `@ConfigurationProperties` thường dễ bảo trì hơn vì gom cấu hình và hỗ trợ validation/binding rõ ràng.

### 13.4. Environment cho nhu cầu đặc biệt

`Environment` cũng cung cấp cách tra cứu:

```java
@Component
class ProfileDiagnostics {

    private final Environment environment;

    ProfileDiagnostics(Environment environment) {
        this.environment = environment;
    }

    void printCurrentMode() {
        System.out.println(
                environment.getProperty("app.notification.mode")
        );
    }
}
```

Không nên để business code hỏi active profiles ở mọi nhánh để quyết định hành vi. Ưu tiên inject giá trị cấu hình hoặc strategy bean đúng, vì cách đó giảm coupling với tên môi trường.

## 14. Danh sách và map khi ghi đè theo profile

Không phải mọi kiểu cấu hình được merge theo cùng một cách. Đây là nguồn lỗi âm thầm khi người học chuyển từ scalar properties sang YAML lists.

### 14.1. List thường được thay thế, không cộng thêm từng phần tử

Giả sử cấu hình chung:

```yaml
app:
  routes:
    - "/health"
    - "/catalog"
```

Cấu hình `prod`:

```yaml
app:
  routes:
    - "/public"
```

Khi bind một List bằng `@ConfigurationProperties`, Spring Boot thường lấy **list từ nguồn có độ ưu tiên cao nhất phù hợp**, thay vì tự động nối thành ba phần tử.

Nếu mục tiêu là danh sách gồm cả `/health`, `/catalog` và `/public`, phải khai báo đầy đủ trong nguồn thắng hoặc tổ chức cấu hình theo cách khác. Không dựa vào kỳ vọng rằng YAML list sẽ được append.

### 14.2. Map có thể được kết hợp theo key

Với map:

```yaml
# application.yml
app:
  labels:
    owner: platform
    stage: shared
```

```yaml
# application-prod.yml
app:
  labels:
    stage: production
```

Khi bind map theo cơ chế của Spring Boot, các key có thể được kết hợp từ nhiều nguồn: `owner` giữ giá trị chung, còn `stage` nhận giá trị ưu tiên cao hơn.

Tuy nhiên, hành vi cụ thể còn phụ thuộc kiểu giá trị map và quy tắc binding; với object phức tạp hoặc list lồng nhau, nên kiểm thử kết quả thay vì suy luận từ cấu trúc YAML.

### 14.3. Đừng coi YAML là deep-merge tổng quát

Spring Boot làm việc với property sources và binder, không đơn giản trộn hai cây YAML bằng một thuật toán deep merge không điều kiện. Với các collection, kiểm thử binding thực tế là cách an toàn.

## 15. Giá trị bí mật trong profile-specific files

Một sai lầm phổ biến là commit cả mật khẩu production vào `application-prod.yml`:

```yaml
spring:
  datasource:
    username: production_user
    password: my-real-password
```

Đó không phải cách quản lý bí mật an toàn. File trong repository hoặc JAR thường có thể được đọc bởi nhiều người có quyền truy cập artifact.

Nên để secrets đến từ biến môi trường, secret manager hoặc nguồn cấu hình bảo mật của nền tảng.

Ví dụ dùng placeholder:

```yaml
# application-prod.yml
spring:
  datasource:
    url: "jdbc:postgresql://db.internal.example:5432/catalog"
    username: "${DB_USERNAME}"
    password: "${DB_PASSWORD}"
```

Ở đây, `${DB_USERNAME}` và `${DB_PASSWORD}` là placeholder do Spring resolve từ Environment; không phải giá trị thật. Nền tảng triển khai cần cung cấp các biến tương ứng.

### 15.1. Đừng đặt default secret yếu

Tránh kiểu:

```yaml
spring:
  datasource:
    password: "${DB_PASSWORD:password123}"
```

Nếu quên cung cấp biến môi trường trong production, ứng dụng có thể khởi động với secret yếu. Với thông tin bắt buộc và nhạy cảm, thường nên thất bại rõ ràng khi thiếu cấu hình hơn là âm thầm dùng default không an toàn.

### 15.2. Log và Actuator cũng cần được bảo vệ

Các endpoint `/actuator/env`, `/actuator/configprops` và debug logging có thể cho biết cấu trúc cấu hình, nguồn property hoặc metadata nội bộ. Không nên expose tùy tiện cho người dùng công khai. Spring Boot có cơ chế sanitization nhưng không nên xem nó là lý do để bỏ kiểm soát truy cập.

## 16. Cấu hình bên ngoài JAR cho từng profile

Một lợi ích lớn của externalized configuration là không cần build lại artifact mỗi khi đổi URL, timeout hay level logging.

Ví dụ project build ra:

```text
deploy/
├── catalog-service.jar
└── config/
    ├── application.yml
    └── application-prod.yml
```

Nếu chạy tại thư mục `deploy` với cấu hình location mặc định phù hợp:

```bash
java -jar catalog-service.jar --spring.profiles.active=prod
```

Spring Boot có thể nạp file `./config/application-prod.yml` nằm ngoài JAR. Các giá trị ngoài JAR có thể ghi đè giá trị đóng gói trong artifact theo precedence mặc định.

### 16.1. Đường dẫn ./ là working directory

`./config/` được hiểu tương đối với **working directory của tiến trình**, không nhất thiết là thư mục chứa file JAR.

Nếu khởi động:

```bash
cd /opt/app
java -jar /srv/releases/catalog-service.jar --spring.profiles.active=prod
```

thì các đường dẫn tương đối như `./config/` liên hệ tới `/opt/app`, không tự chuyển sang `/srv/releases`.

Đây là nguyên nhân thường gặp khi một file có mặt trên máy nhưng Spring Boot không tìm thấy vì service manager hoặc Docker `WORKDIR` khác với dự kiến.

### 16.2. spring.config.location

Có thể chỉ định các location cần nạp bằng `spring.config.location`, ví dụ:

```bash
java -jar app.jar --spring.config.location=optional:file:./deployment-config/
```

**Lưu ý:** `spring.config.location` thay thế tập location mặc định. Nếu muốn giữ mặc định rồi thêm một location bổ sung, `spring.config.additional-location` thường phù hợp hơn.

### 16.3. spring.config.additional-location

Ví dụ:

```bash
java -jar app.jar --spring.config.additional-location=optional:file:./deployment-config/
```

Boot giữ các location mặc định và còn xem xét location mới theo quy tắc precedence của Config Data. Những biến thể profile-specific tại location được thêm cũng có thể được xét.

### 16.4. Prefix optional:

`optional:` cho biết một location/resource được chỉ định có thể không tồn tại mà không nhất thiết khiến startup thất bại vì thiếu location đó.

Không nên dùng `optional:` cho nguồn chứa cấu hình **bắt buộc** để ứng dụng hoạt động an toàn. Nếu một file chứa endpoint/secret quan trọng, việc im lặng bỏ qua file có thể khiến ứng dụng sử dụng giá trị mặc định sai.

### 16.5. Thời điểm đọc các thiết lập location

`spring.config.name`, `spring.config.location` và `spring.config.additional-location` tham gia **giai đoạn xác định nơi nạp Config Data**. Vì vậy, chúng cần được cung cấp đủ sớm, chẳng hạn qua command-line arguments, environment variables hoặc JVM system properties phù hợp, thay vì đặt trong chính file mà Boot chưa biết cần tìm ở đâu.

## 17. Import cấu hình bổ sung từ profile file

Spring Boot còn hỗ trợ `spring.config.import` để import nguồn Config Data khác. Đây là cơ chế nâng cao khi cấu hình được chia theo module hoặc được cung cấp bên ngoài.

Ví dụ:

```properties
# application-prod.properties
spring.config.import=optional:file:./external/catalog-prod.properties
```

Khi profile `prod` được nạp, document này có thể import nguồn cấu hình bổ sung. Nội dung được import tham gia quy tắc precedence của Config Data; import không đơn thuần là phép nối text vào file gốc.

### 17.1. Import không thay thế profile

`spring.config.import` chỉ định những nguồn cấu hình khác. `spring.profiles.active` quyết định tập profile được xử lý. Cần phân biệt hai trách nhiệm.

Nếu import tài liệu có biến thể profile-specific, hệ thống Config Data có thể xét các biến thể phù hợp theo quy tắc của Boot.

### 17.2. Không tạo chuỗi import khó kiểm soát

Nếu `application-prod.yml` import A, A import B, B lại phụ thuộc vào environment và nhiều condition, việc tìm origin của một property có thể trở nên rất khó. Hãy đặt quy tắc ownership rõ:

- Cấu hình chung thuộc ứng dụng.
- Cấu hình deploy thuộc hạ tầng.
- Cấu hình nhạy cảm thuộc secret manager.
- Cấu hình module chỉ chứa key của module đó.

## 18. Kiểm thử cấu hình theo profile

Không nên chờ tới production mới phát hiện `application-prod.yml` sai indentation, thiếu property hoặc ghi đè nhầm giá trị.

### 18.1. Dùng @ActiveProfiles trong test

Spring Test hỗ trợ `@ActiveProfiles`:

```java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.catalog.config.DownstreamProperties;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("dev")
class DevelopmentConfigurationTest {

    @Autowired
    DownstreamProperties properties;

    @Test
    void loadsDevelopmentOverrides() {
        assertThat(properties.baseUrl())
                .isEqualTo("http://localhost:9090");
        assertThat(properties.connectTimeout())
                .isEqualTo(Duration.ofSeconds(1));
    }
}
```

`@SpringBootTest` khởi tạo Spring Boot application context cho test. `@ActiveProfiles("dev")` chọn profile cần thử; hệ thống Config Data tải giá trị trong `application-dev.yml` theo quy tắc bình thường.

### 18.2. Test profile production

```java
@SpringBootTest
@ActiveProfiles("prod")
class ProductionConfigurationTest {

    @Autowired
    DownstreamProperties properties;

    @Test
    void loadsProductionOverrides() {
        assertThat(properties.baseUrl())
                .isEqualTo("https://api.partner.example.invalid");
        assertThat(properties.connectTimeout())
                .isEqualTo(Duration.ofSeconds(5));
    }
}
```

Trong test này, chỉ kiểm tra binding và cấu hình; không nên cho test tự gọi dịch vụ production thật. Có thể mock những client thực thi network calls hoặc kiểm thử property binding bằng context nhỏ theo cách phù hợp.

### 18.3. Test môi trường không có profile active

Một test khác có thể xác minh default configuration:

```java
@SpringBootTest
class DefaultConfigurationTest {

    @Autowired
    DownstreamProperties properties;

    @Test
    void loadsCommonDefaults() {
        assertThat(properties.connectTimeout())
                .isEqualTo(Duration.ofSeconds(3));
    }
}
```

Nếu môi trường chạy test tự thiết lập `spring.profiles.active` hoặc `spring.profiles.default`, kết quả có thể khác. Test cần kiểm soát môi trường/profile để tránh phụ thuộc máy phát triển hoặc CI.

### 18.4. Test nhiều profile

Có thể dùng:

```java
@SpringBootTest
@ActiveProfiles({"prod", "cloud"})
class CloudProductionConfigurationTest {
    // Kiểm tra property trùng key và thứ tự ưu tiên mong đợi.
}
```

Đừng chỉ kiểm tra rằng context tạo được. Nên assert những property quan trọng, chẳng hạn endpoint, timeout, feature flags hoặc một bean được chọn theo profile.

### 18.5. Phân biệt override của test với file theo profile

Trong `@SpringBootTest(properties = "...")`, giá trị được cung cấp trực tiếp bởi test có thể ghi đè file `application-dev.yml`. Ví dụ:

```java
@SpringBootTest(properties = "app.downstream.connect-timeout=9s")
@ActiveProfiles("dev")
class OverrideTest {
}
```

Nếu test thấy `9s`, đó chưa phải bằng chứng `application-dev.yml` chứa `9s`. Để kiểm thử file theo profile, hạn chế các override test không cần thiết và kiểm tra origin khi kết quả khác dự kiến.

## 19. Quan sát active profiles khi ứng dụng chạy

Spring có API đọc tập profile:

```java
@Component
class ActiveProfileLogger implements ApplicationRunner {

    private final Environment environment;

    ActiveProfileLogger(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(
                "Active profiles: "
                        + Arrays.toString(environment.getActiveProfiles())
        );
        System.out.println(
                "Default profiles: "
                        + Arrays.toString(environment.getDefaultProfiles())
        );
    }
}
```

Ví dụ cần các import như `java.util.Arrays`, `org.springframework.boot.ApplicationRunner`, `org.springframework.boot.ApplicationArguments`, `org.springframework.core.env.Environment` và `org.springframework.stereotype.Component`.

### 19.1. getActiveProfiles() có thể là mảng rỗng

Nếu không có active profile tường minh, `getActiveProfiles()` có thể rỗng trong khi `getDefaultProfiles()` chứa `default` hoặc default profile được cấu hình.

Không nên kết luận “không có profile nào được dùng” chỉ vì mảng active rỗng. Cần xét đến default profiles.

### 19.2. Spring Boot ghi log active profiles

Khi startup, Spring Boot thường ghi các thông tin về active/default profiles. Đây là một điểm đầu tiên nên kiểm tra khi `application-prod.yml` không được nạp.

Không nên in toàn bộ Environment hoặc các property sources ra log production vì có thể chứa thông tin nhạy cảm.

### 19.3. Actuator env và configprops

Trong ứng dụng có Spring Boot Actuator, các endpoint như `/actuator/env` và `/actuator/configprops` có thể hỗ trợ điều tra những property được resolve và cấu hình được bind.

Endpoint và mức độ chi tiết phụ thuộc exposure/security/sanitization configuration. Chỉ expose cho môi trường và người có quyền phù hợp; không mở công khai chỉ để xem giá trị profile.

### 19.4. Log giai đoạn nạp cấu hình

Khi cần điều tra file nào được phát hiện, có thể tạm thời tăng logging cho phần Config Data:

```properties
logging.level.org.springframework.boot.context.config=TRACE
```

Đây là cách chẩn đoán trong môi trường phát triển hoặc sự cố có kiểm soát. Log có thể rất dài và có thể tiết lộ đường dẫn/configuration metadata. Tắt lại sau khi đã tìm nguyên nhân.

## 20. Lỗi thường gặp với application-{profile}

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
| --- | --- | --- |
| `application-dev.yml` không có tác dụng | `dev` chưa active | Kiểm tra `spring.profiles.active` và log startup |
| Profile active nhưng một property không đổi | Có nguồn ưu tiên cao hơn, key sai hoặc file không nằm ở location được đọc | Kiểm tra Environment/property origin và path |
| YAML không bind đúng | Indentation sai hoặc tên key không phù hợp | Kiểm tra cấu trúc YAML và class `@ConfigurationProperties` |
| File `application-prod.yml` có nhưng không được nạp | Profile khác active hoặc file nằm ngoài config location | Kiểm tra tên file, working directory, CLI config locations |
| Đặt `spring.profiles.active` trong profile file gây lỗi | Thuộc tính activation đặt ở nơi không hợp lệ | Chuyển active profile sang nguồn non-profile-specific hoặc environment |
| Giá trị trong YAML không thắng | Có file `.properties` cùng base/location và trùng key | Chọn một định dạng, tránh file kép |
| Khi active `prod,cloud` giá trị bất ngờ | Hai file ghi đè cùng key, thứ tự profile hoặc source khác can thiệp | Kiểm tra profile order và property sources |
| List mất phần tử chung | List binding bị thay thế bởi nguồn ưu tiên cao hơn | Khai báo toàn bộ danh sách cần thiết ở nguồn thắng |
| Profile test vô tình gọi dịch vụ thật | Test dùng profile production và client thật tự khởi tạo | Mock client, cô lập integration và xác định phạm vi test |
| Thiếu secret khi deploy | Secret không được cung cấp từ environment/secret manager | Xác minh injection và validation của nền tảng |
| Ứng dụng khác nhau giữa local và container | Working directory hoặc config location khác | Kiểm tra `WORKDIR` và đường dẫn `./config/` |

### 20.1. Đừng sửa bằng cách hard-code profile khắp nơi

Nếu file profile không được nạp, có thể dễ bị cám dỗ sửa từng bean:

```java
if ("prod".equals(activeProfile)) {
    timeout = Duration.ofSeconds(5);
}
```

Cách này phân tán policy môi trường vào business code và làm hệ thống khó test. Thông thường, nên sửa ở tầng config discovery hoặc property precedence, rồi inject typed properties vào service.

### 20.2. Không dùng tên profile để thay thế bảo mật

Chỉ đặt `@Profile("prod")` trên một security configuration chưa đủ đảm bảo các môi trường khác an toàn. Security policies nên có giá trị mặc định bảo vệ, cấu hình bắt buộc rõ ràng và test độc lập, không dựa hoàn toàn vào một nhãn profile dễ bị quên khi khởi động.

## 21. Quy trình điều tra khi cấu hình theo profile không được áp dụng

Giả sử `application-prod.yml` khai báo `app.downstream.connect-timeout=5s` nhưng ứng dụng đang dùng `3s`.

**Bước 1 — Xác định profile thật sự active.** Đọc log startup hoặc `Environment.getActiveProfiles()`. Nếu không có `prod`, việc file không được chọn là điều bình thường.

**Bước 2 — Kiểm tra tên file.** Đảm bảo đúng `application-prod.yml`, không phải `applications-prod.yml`, `application-production.yml` hoặc đuôi không phù hợp với tên profile thực tế.

**Bước 3 — Kiểm tra location.** File có trong `src/main/resources`, trên runtime classpath hoặc location ngoài JAR mà Spring Boot đang tìm không? Đường dẫn `./config/` có đúng với working directory không?

**Bước 4 — Kiểm tra cấu trúc YAML/key.** Ví dụ `connect-timeout` nằm đúng dưới `app.downstream` chưa? Nếu có typographical error, property có thể trở thành key khác.

**Bước 5 — Tìm nguồn override.** Có CLI `--app.downstream.connect-timeout=3s`, biến môi trường hoặc external config đang thắng không?

**Bước 6 — Kiểm tra định dạng kép.** Có cả `application-prod.properties` và `application-prod.yml` tại cùng location không?

**Bước 7 — Kiểm tra binding.** `DownstreamProperties` có được đăng ký, prefix và property names có đúng không? Có validation/type conversion error không?

**Bước 8 — Xác nhận kết quả.** Tạo một test hoặc chạy ứng dụng trong môi trường kiểm soát, đọc giá trị qua bean được bind, rồi ghi nhận cấu hình cuối cùng.

Một mẫu ghi nhận sự cố:

```text
Expected profile:
Observed active/default profiles:
Expected configuration file:
File location / working directory:
Expected property:
Observed resolved value:
Override source (if any):
Root cause:
Change applied:
Verification:
```

Những thông tin này giúp phân biệt **file không được phát hiện**, **profile không được kích hoạt**, **property bị ghi đè** và **binding không đúng**.

## 22. Bài tập thực hành

### Bài tập 1 — Chuyển đổi .properties và YAML

Tạo cấu hình chung bằng `application.properties`:

```properties
app.banner=Welcome
app.timeout=3s
```

Tạo `application-dev.properties` ghi đè timeout bằng `1s`. Sau đó chuyển cả hai file sang YAML trong một project demo khác. Giải thích vì sao hai cách biểu diễn cho cùng property values.

### Bài tập 2 — Kích hoạt dev/prod

Tạo `application.yml`, `application-dev.yml` và `application-prod.yml`, mỗi file theo profile chỉ ghi đè `app.banner`. Chạy:

```bash
java -jar app.jar --spring.profiles.active=dev
java -jar app.jar --spring.profiles.active=prod
```

Quan sát giá trị qua `Environment.getProperty("app.banner")`.

### Bài tập 3 — Kiểm tra default profile

Tạo `application-default.yml` với một banner riêng. Chạy ứng dụng khi không có active profile, rồi chạy với `dev`. Xác định lúc nào giá trị default được sử dụng.

### Bài tập 4 — Nhiều active profiles

Tạo `application-prod.yml` và `application-cloud.yml` cùng ghi đè một property. Chạy với `prod,cloud` rồi `cloud,prod`. Ghi lại kết quả và giải thích thứ tự áp dụng trong cùng location.

### Bài tập 5 — Phân biệt @Profile và file profile-specific

Tạo hai bean implement `MessageSender` có `@Profile("dev")` và `@Profile("prod")`. Cùng lúc, dùng `application-dev.yml` và `application-prod.yml` để cấu hình timeout.

Giải thích sự khác nhau giữa chọn bean và chọn property. Thử active cả hai profile để quan sát vấn đề nhiều bean cùng type.

### Bài tập 6 — Dùng @ConfigurationProperties

Tạo record `DownstreamProperties` có `String baseUrl` và `Duration connectTimeout`. Khai báo các giá trị chung, dev và prod. Viết hai `@SpringBootTest` với `@ActiveProfiles("dev")` và `@ActiveProfiles("prod")` để xác nhận binding.

### Bài tập 7 — Thử file cấu hình ngoài JAR

Đóng gói ứng dụng với một `application.yml` mặc định. Tạo thư mục `./config` cạnh working directory và đặt `application-prod.yml` trong đó. Chạy với profile `prod`, xác định file nào được dùng và thử chuyển working directory để thấy ảnh hưởng.

### Bài tập 8 — Tìm lỗi cấu hình

Chủ động tạo ba lỗi trong project demo:

1. Đặt sai tên file `application-production.yml` nhưng kích hoạt `prod`.
2. Đặt `spring.profiles.active` bên trong `application-prod.yml`.
3. Có cả `application-prod.properties` và `application-prod.yml`, hai file chứa giá trị cùng key khác nhau.

Với từng trường hợp, dự đoán triệu chứng và cách sửa đúng tầng.

### Bài tập 9 — List và map

Tạo một `List<String>` và một `Map<String, String>` trong `@ConfigurationProperties`. Khai báo các giá trị chung, rồi khai báo một phần ở `application-prod.yml`. Xác định kết quả bind thực tế và giải thích sự khác nhau giữa list replacement và map key override.

### Bài tập 10 — Thiết kế cấu hình production an toàn

Một ứng dụng cần datasource URL, username và password trong production. Hãy quyết định giá trị nào có thể ở `application-prod.yml` và giá trị nào cần secret manager/environment. Thiết kế validation để ứng dụng thất bại rõ ràng khi thiếu bí mật bắt buộc.

## 23. Tổng kết

Quy ước **`application-{profile}.properties`** hoặc **`application-{profile}.yml` / `application-{profile}.yaml`** cho phép Spring Boot quản lý khác biệt giữa các môi trường mà không cần sửa business code. File chung mang những giá trị được chia sẻ; file profile-specific chỉ ghi đè phần cần khác. Spring Boot chọn những tài liệu profile-specific dựa trên active/default profiles và kết hợp chúng với những property sources khác theo quy tắc Config Data.

Những nguyên tắc cốt lõi:

- **Tên file không tự kích hoạt profile.** Profile cần được chọn bằng `spring.profiles.active`, default profiles, API phù hợp hoặc cơ chế tương ứng.
- **Profile-specific config ghi đè giá trị chung** khi cùng key và điều kiện precedence cho phép, nhưng không luôn thắng command-line arguments, environment variables hoặc external configuration.
- **`.properties` và YAML là hai cách biểu diễn.** Tránh dùng đồng thời cả hai với cùng base name/location vì dễ tạo xung đột.
- **Nhiều active profiles có thứ tự.** Khi cùng ghi đè một key trong cùng location, profile sau thường có thể thắng.
- **`application-default.*` có vai trò khi không có active profile.** Default profile không tự động được dùng kèm mọi active profile.
- **`spring.config.activate.on-profile` chỉ chọn document**, không kích hoạt profile mới.
- **Không đặt `spring.profiles.active` hay các property mở rộng tập profile ở file profile-specific.** Hãy cung cấp từ nguồn cấu hình hợp lệ đủ sớm.
- **Chú ý cách bind list và map.** List thường được thay thế; map có thể kết hợp key.
- **Không commit production secrets vào repository hoặc JAR.** Dùng nguồn bí mật bên ngoài và validation rõ ràng.
- **Dùng `@ConfigurationProperties` và test theo profile** để giảm việc đọc property tùy tiện trong business code.

Khi một giá trị cấu hình không đúng như mong đợi, hãy đi theo chuỗi **profile nào đang active → file nào được tìm thấy → location và format nào đang được ưu tiên → property nào ghi đè → bean nào nhận giá trị cuối cùng**. Hiểu đúng chuỗi này là nền tảng để triển khai cùng một ứng dụng Spring Boot trong nhiều môi trường một cách có thể dự đoán, kiểm thử và vận hành an toàn.

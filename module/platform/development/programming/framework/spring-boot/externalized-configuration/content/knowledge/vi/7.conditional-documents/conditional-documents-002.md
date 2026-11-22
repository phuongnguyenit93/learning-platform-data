# Tách tài liệu YAML bằng `---` và Properties bằng `#---` hoặc `!---` trong Spring Boot

## 1. Một tệp vật lý có thể chứa nhiều tài liệu cấu hình

Spring Boot cho phép chia **một tệp cấu hình vật lý** thành nhiều **tài liệu logic (logical documents)**. Mỗi tài liệu là một nhóm thuộc tính riêng và được đưa vào cơ chế Config Data của Spring Boot. Khi khởi động, Spring Boot xử lý các tài liệu **từ trên xuống dưới**; tài liệu phía sau có thể ghi đè các thuộc tính trùng tên của tài liệu phía trước nếu cả hai cùng được kích hoạt.

Đây là cách hữu ích để giữ cấu hình mặc định và các phần chỉ áp dụng trong một điều kiện cụ thể trong **cùng một tệp**:

- Tài liệu đầu tiên: giá trị chung cho mọi môi trường.
- Tài liệu tiếp theo: thay đổi khi profile `dev` được kích hoạt.
- Tài liệu khác: thay đổi khi profile `prod` được kích hoạt.
- Tài liệu chỉ dành cho một nền tảng cloud: chỉ áp dụng khi Spring Boot phát hiện nền tảng phù hợp, ví dụ Kubernetes.

Điểm quan trọng: **dấu phân tách phụ thuộc định dạng tệp**.

| Định dạng | Dấu bắt đầu tài liệu mới | Ví dụ tệp |
| --- | --- | --- |
| YAML | `---` | `application.yml` hoặc `application.yaml` |
| Java Properties | `#---` hoặc `!---` | `application.properties` |

Hai dấu trong file Properties là những **dòng comment đặc biệt** mà Spring Boot dùng để tách tài liệu. Đây là cơ chế của **Spring Boot Config Data**, không phải cú pháp của Java Properties thuần túy mà mọi thư viện đọc Properties đều hiểu.

## 2. Tách tài liệu YAML bằng `---`

### 2.1. Cú pháp

YAML hỗ trợ cấu trúc nhiều tài liệu (multi-document YAML) bằng dòng `---`:

~~~yaml
app:
  name: Demo Service
  timeout: 3s

---
app:
  timeout: 10s
~~~

Về mặt logic, file trên có hai tài liệu:

**Tài liệu 1**

~~~yaml
app:
  name: Demo Service
  timeout: 3s
~~~

**Tài liệu 2**

~~~yaml
app:
  timeout: 10s
~~~

Nếu cả hai tài liệu đều tham gia và không có nguồn ưu tiên cao hơn, giá trị hiệu lực là:

~~~properties
app.name=Demo Service
app.timeout=10s
~~~

Thuộc tính `app.name` không xuất hiện trong tài liệu 2 nên vẫn lấy từ tài liệu 1. `app.timeout` xuất hiện ở cả hai nên giá trị `10s` trong tài liệu 2 ghi đè `3s`.

### 2.2. Dòng phân tách phải ở đúng vị trí

Hãy dùng `---` trên **một dòng riêng** ở cấp đầu tài liệu:

~~~yaml
app:
  timeout: 3s
---
app:
  timeout: 10s
~~~

Không đặt dấu phân tách như một phần của giá trị:

~~~yaml
# Dấu --- trong chuỗi sau không tạo tài liệu mới:
app:
  title: "Phiên bản A --- Phiên bản B"
~~~

Cũng không thụt dấu phân tách vào trong cấu trúc `app:` rồi mong nó hoạt động như dấu tách cấp cao. Cơ chế tách tài liệu áp dụng cho YAML document stream, không phải một khóa con.

### 2.3. Mỗi tài liệu là một đơn vị cấu hình

Mỗi tài liệu YAML có thể chứa cây dữ liệu riêng. Spring Boot làm phẳng các khóa phân cấp thành tên property:

~~~yaml
app:
  client:
    endpoint: https://sandbox.example.test
    timeout: 3s
---
app:
  client:
    timeout: 8s
~~~

Kết quả cuối có `app.client.endpoint=https://sandbox.example.test` và `app.client.timeout=8s`. Dòng `---` không buộc Spring Boot bỏ toàn bộ `app.client` của tài liệu trước; quá trình giải quyết property diễn ra theo các tên thuộc tính.

Tuy nhiên, khi bind sang `List` bằng `@ConfigurationProperties`, danh sách ở nguồn ưu tiên cao có thể **thay cả danh sách** ở nguồn thấp. Đừng suy ra mọi cấu trúc đều được nối hoặc deep-merge theo kiểu dữ liệu JSON.

## 3. Tách tài liệu Properties bằng `#---` hoặc `!---`

### 3.1. Vì sao không dùng `---` thuần trong file Properties?

Java Properties không sử dụng YAML document separator. Với một tệp `application.properties`, Spring Boot quy định dòng comment đặc biệt `#---` hoặc `!---` để đánh dấu điểm bắt đầu tài liệu tiếp theo.

Ví dụ với `#---`:

~~~properties
app.name=Demo Service
app.timeout=3s
#---
app.timeout=10s
~~~

Tương đương về ý tưởng với ví dụ YAML hai tài liệu ở phần trước: `app.name` vẫn là `Demo Service`, còn `app.timeout` có giá trị `10s` nếu không có nguồn khác ghi đè.

Cũng có thể dùng `!---`:

~~~properties
app.name=Demo Service
app.timeout=3s
!---
app.timeout=10s
~~~

Trong Java Properties, ký tự `#` và `!` thường đánh dấu comment. **Spring Boot nhận diện chính xác hai mẫu comment đặc biệt này như ranh giới tài liệu** khi nạp tệp bằng Config Data.

### 3.2. Các điều kiện cú pháp bắt buộc

Dòng phân tách của Properties có quy tắc chặt hơn một comment thông thường:

1. **Không có khoảng trắng trước dấu `#` hoặc `!`.** Dòng phải bắt đầu ngay ở cột đầu tiên.
2. **Có đúng ba dấu gạch ngang liên tiếp**, không phải hai hoặc bốn.
3. **Không có khoảng trắng giữa tiền tố comment và các dấu gạch.** Viết `#---` hoặc `!---`, không phải `# ---` hay `! ---`.
4. **Các dòng ngay trước và ngay sau separator không được là comment có cùng tiền tố** với separator. Ví dụ, nếu dùng `#---` thì tránh đặt dòng `# ghi chú` sát ngay trên hoặc ngay dưới dấu phân tách; với `!---` thì tránh các dòng comment bắt đầu bằng `!` nằm sát nó.

Các ví dụ **không hợp lệ để làm separator**:

~~~properties
# Sai: có một khoảng trắng đầu dòng
 #---
app.timeout=10s
~~~

~~~properties
# Sai: có khoảng trắng giữa # và ---
# ---
app.timeout=10s
~~~

~~~properties
# Sai: thiếu hoặc thừa dấu gạch ngang
#--
app.timeout=10s
~~~

~~~properties
#----
app.timeout=10s
~~~

Một mẫu nên dùng:

~~~properties
app.name=Demo Service
app.timeout=3s
#---
spring.config.activate.on-profile=prod
app.timeout=10s
~~~

Dòng ngay trước separator là property và ngay sau separator cũng là property; cách bố trí này tránh tình huống comment liền kề cùng tiền tố làm Spring Boot không nhận diện separator như dự kiến.

### 3.3. Có thể trộn `#---` và `!---` không?

Cả hai đều được Spring Boot chấp nhận như dấu tách tài liệu của file Properties. Tuy nhiên, một nhóm dự án thường chọn **một kiểu nhất quán** để người đọc dễ nhận ra ranh giới:

~~~properties
app.timeout=3s
#---
spring.config.activate.on-profile=dev
app.timeout=5s
#---
spring.config.activate.on-profile=prod
app.timeout=15s
~~~

Nếu repository đang dùng `!---` thì áp dụng tương tự. Cần tuân thủ quy tắc dấu phân tách và comment sát dòng cho từng vị trí.

## 4. Tài liệu logic được xử lý theo thứ tự nào?

Giả sử trong `application.yml` có ba tài liệu **không có điều kiện**:

~~~yaml
app:
  endpoint: https://one.example.test
  timeout: 3s
  retries: 1

---
app:
  timeout: 5s
  retries: 2

---
app:
  timeout: 8s
~~~

Spring Boot xử lý tài liệu theo thứ tự xuất hiện từ trên xuống dưới. Trong phạm vi file này:

| Thuộc tính | Tài liệu 1 | Tài liệu 2 | Tài liệu 3 | Giá trị cuối |
| --- | --- | --- | --- | --- |
| `app.endpoint` | `https://one.example.test` | Không có | Không có | `https://one.example.test` |
| `app.timeout` | `3s` | `5s` | `8s` | `8s` |
| `app.retries` | `1` | `2` | Không có | `2` |

Điều đó minh họa quy tắc **later document overrides earlier document** đối với thuộc tính trùng tên. Một tài liệu sau không xóa một khóa đã khai báo ở tài liệu trước chỉ vì tài liệu sau không nhắc đến khóa đó.

Cần phân biệt:

- **Thứ tự tài liệu trong cùng tệp:** tài liệu phía dưới có thể ghi đè tài liệu phía trên khi cả hai được kích hoạt.
- **Thứ tự các nguồn cấu hình khác nhau:** biến môi trường, Java system properties hoặc đối số dòng lệnh có thể có ưu tiên cao hơn dữ liệu file, kể cả tài liệu cuối file.
- **Điều kiện kích hoạt tài liệu:** một tài liệu chứa `spring.config.activate.on-profile` hoặc `on-cloud-platform` có thể **không tham gia** nếu điều kiện không thỏa.

Ví dụ nếu tài liệu cuối ghi `app.timeout=8s` nhưng khi khởi chạy có `--app.timeout=20s`, giá trị hiệu lực thông thường là `20s`. Dấu `---` không làm một tài liệu chiến thắng mọi nguồn khác.

## 5. Kích hoạt tài liệu có điều kiện bằng `spring.config.activate.on-profile`

Điểm mạnh của multi-document config files là mỗi tài liệu có thể khai báo **điều kiện để được sử dụng**.

### 5.1. YAML có tài liệu chung và tài liệu theo profile

~~~yaml
# application.yml — tài liệu chung
app:
  endpoint: https://sandbox.example.test
  timeout: 3s
  cache-enabled: false

---
spring:
  config:
    activate:
      on-profile: dev
app:
  timeout: 5s

---
spring:
  config:
    activate:
      on-profile: prod
app:
  endpoint: https://api.example.test
  timeout: 12s
  cache-enabled: true
~~~

Nếu không có cấu hình khác ghi đè:

| Profile được kích hoạt | `app.endpoint` | `app.timeout` | `app.cache-enabled` |
| --- | --- | --- | --- |
| Không phải `dev` hoặc `prod` | `https://sandbox.example.test` | `3s` | `false` |
| `dev` | `https://sandbox.example.test` | `5s` | `false` |
| `prod` | `https://api.example.test` | `12s` | `true` |

Để kích hoạt `prod` từ CLI:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Lúc khởi động, Spring Boot xem điều kiện `on-profile` của từng tài liệu. Tài liệu dành cho `dev` không tham gia khi chỉ có `prod` được kích hoạt. Giá trị cuối được xác định từ những tài liệu **đang hoạt động**, sau đó tiếp tục chịu quy tắc ưu tiên của các nguồn config data khác.

### 5.2. Tương đương bằng `application.properties`

~~~properties
app.endpoint=https://sandbox.example.test
app.timeout=3s
app.cache-enabled=false
#---
spring.config.activate.on-profile=dev
app.timeout=5s
#---
spring.config.activate.on-profile=prod
app.endpoint=https://api.example.test
app.timeout=12s
app.cache-enabled=true
~~~

Đây là **một file Properties gồm ba tài liệu logic**. Không cần tạo `application-dev.properties` và `application-prod.properties` chỉ để minh họa các điều kiện này.

Tuy nhiên, tên file theo profile như `application-prod.yml` vẫn là một cơ chế khác được Spring Boot hỗ trợ. Hai cách có thể phối hợp trong hệ thống thực tế; cần hiểu thứ tự và các nguồn hiệu lực khi có xung đột.

### 5.3. Biểu thức profile thay vì một tên đơn lẻ

`spring.config.activate.on-profile` hỗ trợ profile expression, ví dụ:

~~~properties
app.timeout=3s
#---
spring.config.activate.on-profile=prod | staging
app.timeout=10s
~~~

Tài liệu thứ hai sẽ được kích hoạt khi điều kiện `prod | staging` phù hợp: **có profile `prod` hoặc `staging`**.

Trong YAML:

~~~yaml
app:
  timeout: 3s

---
spring:
  config:
    activate:
      on-profile: "prod | staging"
app:
  timeout: 10s
~~~

Có thể dùng các toán tử biểu thức profile do Spring hỗ trợ, chẳng hạn phủ định `!dev` và kết hợp logic theo cú pháp quy định. Khi dùng trong YAML, đặt biểu thức trong dấu nháy để tránh ký tự như `!` bị diễn giải sai bởi YAML parser.

## 6. Kích hoạt tài liệu theo nền tảng bằng `on-cloud-platform`

Spring Boot hỗ trợ:

~~~yaml
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
~~~

Tài liệu chứa điều kiện này được kích hoạt khi Spring Boot **nhận diện nền tảng cloud tương ứng**. Ví dụ:

~~~yaml
app:
  storage:
    mode: local
    path: ./data

---
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
app:
  storage:
    mode: mounted
    path: /data
~~~

Khi chạy ở môi trường được nhận diện là Kubernetes và không có nguồn cao hơn ghi đè, `app.storage.mode=mounted` và `app.storage.path=/data`. Khi điều kiện cloud platform không thỏa, ứng dụng giữ `local` và `./data` từ tài liệu chung.

Với Properties:

~~~properties
app.storage.mode=local
app.storage.path=./data
!---
spring.config.activate.on-cloud-platform=kubernetes
app.storage.mode=mounted
app.storage.path=/data
~~~

Việc chạy một container Docker **không tự động đồng nghĩa** điều kiện `kubernetes` sẽ đúng. Điều kiện dựa trên cách Spring Boot nhận diện cloud platform, không chỉ dựa vào tên profile hoặc việc ứng dụng được đóng gói trong image.

## 7. Kết hợp điều kiện profile và cloud platform

Một tài liệu có thể đồng thời yêu cầu profile phù hợp **và** một nền tảng cloud được phát hiện:

~~~yaml
app:
  timeout: 3s
  endpoint: https://sandbox.example.test

---
spring:
  config:
    activate:
      on-profile: "prod | staging"
      on-cloud-platform: kubernetes
app:
  timeout: 15s
~~~

Tài liệu thứ hai chỉ tham gia khi **cả hai** điều kiện được đáp ứng:

1. Biểu thức profile `prod | staging` phù hợp.
2. Spring Boot nhận diện nền tảng là `kubernetes`.

Nếu chỉ bật `prod` nhưng không chạy trên môi trường được nhận diện là Kubernetes, tài liệu thứ hai **không** đóng góp `app.timeout=15s`; giá trị từ tài liệu chung vẫn có thể được dùng.

Tương đương trong Properties:

~~~properties
app.timeout=3s
app.endpoint=https://sandbox.example.test
#---
spring.config.activate.on-profile=prod | staging
spring.config.activate.on-cloud-platform=kubernetes
app.timeout=15s
~~~

Điều này đặc biệt hữu ích khi một môi trường có nhiều đặc điểm cùng lúc: ứng dụng dùng profile `prod` nhưng cấu hình volume, đường dẫn hoặc một số giới hạn vận hành chỉ thích hợp với Kubernetes.

## 8. Ví dụ thực tế: bốn tài liệu trong một file

Giả sử dự án Spring Boot có một `src/main/resources/application.yml`:

~~~yaml
# Tài liệu 1: mặc định
spring:
  application:
    name: order-service

server:
  port: 8080

app:
  partner-url: https://sandbox.example.test
  timeout: 3s
  retries: 1
  audit-enabled: false

---
# Tài liệu 2: dev
spring:
  config:
    activate:
      on-profile: dev

app:
  timeout: 5s
  retries: 0

---
# Tài liệu 3: prod
spring:
  config:
    activate:
      on-profile: prod

app:
  partner-url: https://api.example.test
  timeout: 12s
  retries: 3
  audit-enabled: true

---
# Tài liệu 4: khi được nhận diện là Kubernetes và đang chạy prod
spring:
  config:
    activate:
      on-profile: prod
      on-cloud-platform: kubernetes

server:
  port: 9090

app:
  timeout: 20s
~~~

Xét các trường hợp trong bảng sau; giả định không có property source khác ghi đè:

| Môi trường | `server.port` | `app.partner-url` | `app.timeout` | `app.retries` | `app.audit-enabled` |
| --- | --- | --- | --- | --- | --- |
| Không có `dev`/`prod`, không phát hiện Kubernetes | `8080` | Sandbox | `3s` | `1` | `false` |
| Profile `dev`, không phát hiện Kubernetes | `8080` | Sandbox | `5s` | `0` | `false` |
| Profile `prod`, không phát hiện Kubernetes | `8080` | Production | `12s` | `3` | `true` |
| Profile `prod` và nhận diện Kubernetes | `9090` | Production | `20s` | `3` | `true` |

Ở trường hợp cuối:

- Tài liệu 1 luôn áp dụng, cung cấp giá trị chung.
- Tài liệu 2 không áp dụng vì `dev` không hoạt động.
- Tài liệu 3 áp dụng vì `prod` hoạt động.
- Tài liệu 4 áp dụng vì cả `prod` và `kubernetes` phù hợp, ghi đè `server.port` và `app.timeout`.
- `app.partner-url`, `app.retries`, `app.audit-enabled` được giữ từ tài liệu 3, vì tài liệu 4 không khai báo các thuộc tính đó.

Nếu chạy:

~~~bash
java -jar app.jar --spring.profiles.active=prod --app.timeout=25s
~~~

`--app.timeout=25s` vẫn có thể ghi đè giá trị `20s` của tài liệu điều kiện Kubernetes. Độ ưu tiên giữa CLI và config data hoạt động độc lập với việc file được chia thành bao nhiêu tài liệu.

**Lưu ý:** Các endpoint ở ví dụ là địa chỉ minh họa. Một hệ thống triển khai thật cần xác định URL, port và timeout theo yêu cầu vận hành riêng.

## 9. Những giới hạn khi dùng multi-document Properties

Multi-document `application.properties` là tính năng của bộ xử lý **Config Data** trong Spring Boot. Hai annotation Spring quen thuộc:

- `@PropertySource`
- `@TestPropertySource`

**không hỗ trợ nạp multi-document Properties theo cơ chế phân tách `#---`/`!---` này**. Nếu dùng những annotation đó để đọc file Properties trực tiếp, không thể giả định các tài liệu logic và quy tắc `spring.config.activate.*` sẽ được xử lý giống `application.properties` do Spring Boot Config Data nạp.

Để sử dụng đúng tính năng multi-document, nên đặt tài liệu trong cấu hình mà Spring Boot tự nạp, hoặc import qua `spring.config.import` trong luồng Config Data.

Ví dụ:

~~~properties
# application.properties — được Spring Boot nạp như config data
app.timeout=3s
#---
spring.config.activate.on-profile=prod
app.timeout=12s
~~~

Khác với cách chỉ định file đó làm một `@PropertySource` trên lớp `@Configuration`, hai tài liệu ở đây được xử lý theo cơ chế cấu hình của Spring Boot.

## 10. Cách sử dụng trong kiểm thử và phát triển

Một ví dụ rất nhỏ giúp quan sát giá trị cuối cùng.

Cấu hình `application.yml`:

~~~yaml
app:
  mode: default
  timeout: 3s

---
spring:
  config:
    activate:
      on-profile: dev
app:
  mode: development
  timeout: 5s

---
spring:
  config:
    activate:
      on-profile: prod
app:
  mode: production
  timeout: 12s
~~~

Một component dùng `Environment`:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ConfigReporter {
    public ConfigReporter(Environment environment) {
        String mode = environment.getProperty("app.mode");
        String timeout = environment.getProperty("app.timeout");
        System.out.println("mode=" + mode + ", timeout=" + timeout);
    }
}
~~~

Chạy các lần sau:

~~~bash
java -jar app.jar
java -jar app.jar --spring.profiles.active=dev
java -jar app.jar --spring.profiles.active=prod
~~~

Giá trị sẽ lần lượt là `default/3s`, `development/5s` và `production/12s`, giả sử không có nguồn khác cung cấp các property này.

Khi ứng dụng thực tế có cấu hình có kiểu, có thể khai báo `@ConfigurationProperties(prefix = "app")` để bind `timeout` sang `Duration`. Các tài liệu logic chỉ quyết định **nguồn của property**, không thay đổi cách cấu hình được truy xuất hoặc bind sang Java.

Không nên in hoặc log token, password hay secret khi dùng phương pháp quan sát cấu hình.

## 11. Khi nào nên dùng nhiều tài liệu trong cùng một file?

Cách chia tài liệu phù hợp khi:

- Một số giá trị mặc định dùng chung, chỉ có vài thay đổi nhỏ theo profile.
- Muốn xem ngay trong một file những trường nào phụ thuộc `dev`/`prod`/cloud.
- Có cấu hình ngắn, liên quan chặt chẽ và dễ giữ thứ tự tài liệu rõ ràng.
- Một file mount cần chứa nhiều nhóm cấu hình có điều kiện mà không cần nhiều file vật lý.

Khi số tài liệu tăng lớn, mỗi tài liệu dài hoặc cần các nhóm vận hành sở hữu độc lập, có thể cân nhắc tách file theo profile như `application-prod.yml`, sử dụng `spring.config.import`, hoặc cung cấp config data từ nguồn ngoài JAR. Số lượng tài liệu trong một file tự nó không tạo ra cơ chế quản trị, bảo mật hay reload động.

Hai cách **multi-document** và **file theo profile** không loại trừ nhau. Ví dụ `application-prod.yml` vẫn có thể chứa nhiều YAML documents có điều kiện bổ sung, nhưng cần chú ý giới hạn về vị trí được phép khai báo các thuộc tính liên quan đến profile.

## 12. Quy tắc về thuộc tính quản lý profile

Trong tài liệu có điều kiện, hãy dùng:

~~~yaml
spring:
  config:
    activate:
      on-profile: prod
~~~

hoặc:

~~~properties
spring.config.activate.on-profile=prod
~~~

Đây là điều kiện chọn tài liệu.

**Không đặt `spring.profiles.active` hay `spring.profiles.include` bên trong tài liệu đã được kích hoạt theo profile**, ví dụ một tài liệu có `spring.config.activate.on-profile=prod`. Các thuộc tính xác định profile hoạt động chỉ được dùng trong tài liệu không phụ thuộc profile theo những quy tắc của Spring Boot; Spring Boot có thể báo lỗi cấu hình không hợp lệ khi đặt chúng trong tài liệu profile-specific hoặc profile-activated.

Một ví dụ cần tránh:

~~~yaml
spring:
  config:
    activate:
      on-profile: prod
  profiles:
    active: staging
~~~

Cách đúng để bật profile cho lần chạy, nếu được phép theo thiết kế ứng dụng, là truyền tường minh ở nguồn phù hợp:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Hoặc đặt cấu hình quản lý profile ở nguồn/tài liệu không chịu điều kiện profile và phù hợp với quy tắc startup. Đừng tạo vòng kích hoạt gián tiếp bên trong tài liệu mà chính nó đợi profile được bật.

## 13. Những lỗi thường gặp và cách nhận biết

| Hiện tượng | Nguyên nhân có thể xảy ra | Hướng xử lý |
| --- | --- | --- |
| `application.properties` không được chia tài liệu | Dùng `---` hoặc `# ---` thay vì `#---`/`!---` | Viết đúng comment separator, không có leading whitespace và đúng ba dấu `-` |
| Separator Properties không được nhận diện | Có comment ngay sát separator với cùng tiền tố | Để property line sát separator hoặc bố trí lại comment hợp lệ |
| YAML không được chia tài liệu | `---` nằm trong chuỗi hoặc bị thụt vào cấu trúc khác | Dùng dòng `---` độc lập ở cấp document |
| Cấu hình prod không được áp dụng | Profile `prod` chưa hoạt động | Kiểm tra `spring.profiles.active` và điều kiện `on-profile` |
| Cấu hình Kubernetes không được áp dụng | Spring Boot không nhận diện `kubernetes` | Kiểm tra điều kiện cloud platform và môi trường vận hành |
| Bật profile nhưng vẫn nhận giá trị cũ | Một property source khác có ưu tiên cao hơn | Kiểm tra CLI, system properties, environment và các config data source |
| App không khởi động | Sai YAML/Properties, giá trị không bind được, cấu hình profile sai chỗ | Đọc lỗi startup; sửa cú pháp và property tương ứng |
| Dùng `@PropertySource` nhưng multi-document không hoạt động | Annotation không hỗ trợ separator của Spring Boot Config Data | Đưa file vào Config Data hoặc `spring.config.import` |
| Sửa file khi app đang chạy mà bean không đổi | Giá trị được nạp/bind khi startup | Khởi động lại hoặc dùng cơ chế refresh riêng có chủ đích |

Trong quá trình chẩn đoán, có thể kiểm tra giá trị hiệu lực qua `Environment` hoặc các endpoint Spring Boot Actuator phù hợp như `/actuator/env` và `/actuator/configprops` nếu đã bật và bảo vệ. Không đưa secrets vào log hoặc mở công khai endpoint chẩn đoán chứa thông tin nhạy cảm.

## 14. Bài tập: xác định giá trị khi nhiều tài liệu cùng tham gia

Cho file `application.properties`:

~~~properties
app.mode=base
app.timeout=3s
app.retries=1
#---
spring.config.activate.on-profile=staging
app.mode=stage
app.timeout=7s
#---
spring.config.activate.on-profile=prod
app.mode=live
app.timeout=15s
app.retries=3
~~~

**Tình huống A:** chạy:

~~~bash
java -jar app.jar --spring.profiles.active=staging
~~~

Kết quả: `app.mode=stage`, `app.timeout=7s`, `app.retries=1`. Tài liệu staging ghi đè hai khóa; `retries` vẫn giữ từ tài liệu chung.

**Tình huống B:** chạy:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Kết quả: `app.mode=live`, `app.timeout=15s`, `app.retries=3`.

**Tình huống C:** chạy:

~~~bash
java -jar app.jar --spring.profiles.active=prod --app.timeout=30s
~~~

Kết quả: `app.mode=live`, `app.timeout=30s`, `app.retries=3`. Dòng lệnh ghi đè `app.timeout` từ config data.

**Tình huống D:** chạy không bật profile `staging` hoặc `prod`:

~~~bash
java -jar app.jar
~~~

Nếu không có một nguồn khác kích hoạt các profile này, chỉ tài liệu chung áp dụng: `app.mode=base`, `app.timeout=3s`, `app.retries=1`.

Bài tập cho thấy **một file nhiều tài liệu** có thể biểu diễn cả giá trị mặc định và những phần thay đổi có điều kiện, nhưng kết quả cuối phải tính theo tài liệu nào đang được kích hoạt và nguồn nào có ưu tiên cao hơn.

## 15. Ghi nhớ

- YAML dùng một dòng `---` để mở đầu tài liệu tiếp theo; Spring Boot xử lý các tài liệu trong file theo thứ tự **từ trên xuống dưới**.
- Properties dùng comment separator đặc biệt `#---` hoặc `!---`: **không có leading whitespace, đúng ba dấu gạch ngang**, và chú ý comment liền kề cùng tiền tố.
- Tài liệu sau chỉ ghi đè **những property trùng tên** của tài liệu trước khi cả hai đều hoạt động.
- `spring.config.activate.on-profile` và `spring.config.activate.on-cloud-platform` giúp mỗi tài liệu chỉ được nạp khi điều kiện tương ứng phù hợp.
- Multi-document Properties cần luồng nạp **Config Data**; `@PropertySource` và `@TestPropertySource` không hỗ trợ cơ chế này.
- Nhiều tài liệu trong một file vẫn nằm trong **thứ tự ưu tiên cấu hình chung**. CLI, environment và các nguồn khác có thể quyết định giá trị hiệu lực.

### Tài liệu tham khảo

- Spring Boot 3.3 Reference — Externalized Configuration, Working With Multi-Document Files: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.files.multi-document
- Spring Boot 3.3 Reference — Activation Properties: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.files.activation-properties
- Spring Boot Reference — Profiles: https://docs.spring.io/spring-boot/reference/features/profiles.html

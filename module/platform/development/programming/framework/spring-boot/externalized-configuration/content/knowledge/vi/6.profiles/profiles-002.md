# Kích hoạt profile bằng `spring.profiles.active` từ các nguồn cấu hình trong Spring Boot

## 1. Mục tiêu và bối cảnh

Trong Spring Boot, **profile** là cơ chế chọn các thành phần và giá trị cấu hình phù hợp với ngữ cảnh chạy. Một ứng dụng có thể sử dụng cùng một bản build cho local, development, test, staging và production, nhưng mỗi môi trường cần cổng HTTP, địa chỉ dịch vụ, chính sách kết nối hoặc cách triển khai thành phần khác nhau.

Thuộc tính **`spring.profiles.active`** là cách phổ biến để chỉ định những profile đang hoạt động. Nó có thể được cung cấp qua nhiều nguồn trong hệ thống **Externalized Configuration**: file `application.properties` hoặc `application.yml`, biến môi trường hệ điều hành, Java system property, đối số dòng lệnh và các nguồn cấu hình được Spring Boot nạp đủ sớm trong quá trình khởi động.

Ví dụ: ứng dụng có cấu hình cơ sở và hai file theo môi trường:

~~~text
src/main/resources/
├── application.properties
├── application-dev.properties
└── application-prod.properties
~~~

~~~properties
# application.properties
spring.application.name=order-service
app.client.timeout=5s
~~~

~~~properties
# application-dev.properties
app.client.timeout=2s
~~~

~~~properties
# application-prod.properties
app.client.timeout=10s
~~~

Khi chạy với `spring.profiles.active=dev`, Spring Boot có thể nạp cấu hình dành cho `dev`, nên `app.client.timeout` nhận `2s` nếu không có nguồn có độ ưu tiên cao hơn ghi đè. Khi chạy với `prod`, giá trị sẽ là `10s` theo cùng điều kiện. Khi không kích hoạt `dev` hoặc `prod`, giá trị mặc định trong file cơ sở là `5s`, trừ khi có profile mặc định hoặc nguồn ghi đè khác.

Điểm cần nhớ: `spring.profiles.active` **chọn profile**, còn `application-{profile}.properties`, `@Profile` và `spring.config.activate.on-profile` **sử dụng profile đó** để quyết định cấu hình hoặc bean nào có hiệu lực. Hai việc này diễn ra ở các lớp khác nhau.

## 2. Profile là gì và Spring Boot dùng active profile để làm gì?

### 2.1. Khái niệm active profile

Spring Framework cung cấp `Environment` và cơ chế profile. Spring Boot dựa trên đó để áp dụng cấu hình theo môi trường lúc khởi động.

Các profile có thể có tên như:

- `dev`: chạy ở máy phát triển với dịch vụ giả lập hoặc cấu hình nhẹ.
- `test`: chạy kiểm thử tích hợp với database riêng hoặc dữ liệu thử.
- `staging`: môi trường gần production để xác minh trước khi phát hành.
- `prod`: môi trường phục vụ tải thực tế.
- `cloud` hoặc `docker`: một đặc tính của hạ tầng thay vì một giai đoạn phát triển.

Tên profile không tự mang ý nghĩa đặc biệt với Spring. Profile `prod` không khiến ứng dụng tự an toàn hơn hoặc nhanh hơn; chỉ những file, bean và điều kiện cấu hình gắn với `prod` mới tạo ra hành vi khác.

Có thể kích hoạt **nhiều profile cùng lúc**, ví dụ `dev,cloud`. Với các file cấu hình theo profile có trùng khóa, thứ tự profile và vị trí các nguồn ảnh hưởng đến giá trị cuối cùng.

### 2.2. Profile điều khiển cả bean và giá trị cấu hình

Ví dụ tạo bean khác nhau theo profile:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
public class PaymentClientConfiguration {

    @Bean
    @Profile("dev")
    PaymentClient fakePaymentClient() {
        return new FakePaymentClient();
    }

    @Bean
    @Profile("prod")
    PaymentClient realPaymentClient() {
        return new RealPaymentClient();
    }
}
~~~

Đây chỉ là ví dụ mô hình: `PaymentClient`, `FakePaymentClient` và `RealPaymentClient` cần được định nghĩa trong dự án. Trong thiết kế thực tế, nên xác định rõ điều gì xảy ra khi không profile nào trong hai profile trên hoạt động hoặc khi kích hoạt cả hai; nếu cả hai bean cùng kiểu được tạo, có thể cần điều kiện rõ ràng hoặc lựa chọn bean khác.

Cùng một active profile cũng được Spring Boot dùng để tìm các file như `application-dev.yml`, `application-prod.properties` và các document được kích hoạt có điều kiện. Vì vậy, thay đổi `spring.profiles.active` có thể tác động **đồng thời** tới cấu hình và thành phần được khởi tạo.

## 3. Khai báo profile trong `application.properties`

Cách cơ bản:

~~~properties
# application.properties
spring.profiles.active=dev

spring.application.name=order-service
app.client.timeout=5s
~~~

Khi ứng dụng khởi động mà không có nguồn ưu tiên cao hơn khai báo `spring.profiles.active`, profile `dev` trở thành active. Spring Boot sẽ cân nhắc file dành cho `dev` và các điều kiện `@Profile("dev")`.

**Điểm cần lưu ý:** nếu đóng gói sẵn `spring.profiles.active=dev` trong JAR, mọi môi trường sẽ mặc định dùng `dev` trừ khi bị ghi đè. Cách này thuận tiện cho dự án thử nghiệm nhưng ít phù hợp với một artifact dùng chung cho nhiều môi trường. Trong hệ thống triển khai thực tế, thường đặt cấu hình cơ sở không gắn profile hoặc chỉ định profile từ môi trường chạy.

Có thể khai báo danh sách nhiều profile:

~~~properties
spring.profiles.active=dev,cloud
~~~

Điều này yêu cầu kích hoạt cả `dev` và `cloud`. Việc liệt kê nhiều tên trong một thuộc tính khác với tạo nhiều thuộc tính `spring.profiles.active` trong cùng file; nên có một khai báo rõ ràng để tránh sự nhập nhằng.

### 3.1. Profile-specific file được nạp như thế nào?

Giả sử:

~~~properties
# application.properties
app.endpoint=https://api.example.test
app.timeout=5s
~~~

~~~properties
# application-dev.properties
app.endpoint=http://localhost:8081
app.timeout=1s
~~~

~~~properties
# application-prod.properties
app.timeout=12s
~~~

Nếu `dev` được kích hoạt, giá trị tương ứng là:

~~~text
app.endpoint = http://localhost:8081
app.timeout  = 1s
~~~

Nếu `prod` được kích hoạt, giá trị là:

~~~text
app.endpoint = https://api.example.test
app.timeout  = 12s
~~~

`app.endpoint` vẫn nhận giá trị cơ sở ở chế độ `prod` vì file `application-prod.properties` không khai báo lại khóa đó. File theo profile **bổ sung và có thể ghi đè** giá trị, không bắt buộc lặp lại mọi property.

Ví dụ giả định các file ở cùng một tập location thông thường, không có nguồn bên ngoài, biến môi trường hoặc command-line property ưu tiên cao hơn.

## 4. Khai báo profile trong `application.yml`

YAML biểu diễn cùng thuộc tính dưới dạng cấu trúc lồng nhau:

~~~yaml
# application.yml
spring:
  profiles:
    active: dev

app:
  client:
    timeout: 5s
~~~

Cấu hình trên tương đương với `spring.profiles.active=dev` trong `application.properties`.

Muốn kích hoạt nhiều profile, có thể viết:

~~~yaml
spring:
  profiles:
    active: dev,cloud
~~~

Một cách tổ chức dễ bảo trì là giữ `application.yml` chỉ chứa giá trị chung, còn các file `application-dev.yml` và `application-prod.yml` chứa phần khác biệt. Việc chọn profile khi triển khai có thể thực hiện bằng biến môi trường hoặc đối số chạy.

### 4.1. YAML nhiều document và `spring.config.activate.on-profile`

Một file YAML có thể gồm nhiều document tách bằng `---`. Spring Boot cho phép kích hoạt document riêng dựa trên một profile **đã được chọn**:

~~~yaml
# application.yml: cấu hình chung
app:
  display-name: Order Service
  client:
    timeout: 5s
---
spring:
  config:
    activate:
      on-profile: dev

app:
  client:
    timeout: 2s
---
spring:
  config:
    activate:
      on-profile: prod

app:
  client:
    timeout: 10s
~~~

Khi `dev` hoạt động, document tương ứng có thể ghi đè `app.client.timeout` thành `2s`. Với `prod`, giá trị có thể thành `10s`.

Cần phân biệt:

- `spring.profiles.active`: **chọn** profile đang hoạt động.
- `spring.config.activate.on-profile`: **điều kiện để document được nạp** theo các profile đã chọn.
- `@Profile("dev")`: **điều kiện đăng ký bean**.
- `application-dev.yml`: **file cấu hình theo tên profile**.

Trong Spring Boot hiện đại, **không đặt `spring.profiles.active` trong document đã được kích hoạt bằng `spring.config.activate.on-profile`**. Đó là cấu hình vòng lặp: document cần profile để quyết định có nạp hay không, nhưng lại cố thay đổi profile sau khi được chọn.

## 5. Kích hoạt profile bằng biến môi trường

Đây là một trong những cách phù hợp nhất khi muốn giữ nguyên JAR và chỉ thay đổi cấu hình lúc triển khai.

Tên biến môi trường tương ứng với `spring.profiles.active` là:

~~~text
SPRING_PROFILES_ACTIVE
~~~

Spring Boot hỗ trợ cách ánh xạ tên property và tên biến môi trường theo quy tắc cấu hình của nó. Với khóa này, có thể cung cấp `SPRING_PROFILES_ACTIVE=prod` mà không phải chỉnh sửa `application.properties`.

### 5.1. Linux hoặc macOS

Trong một shell POSIX:

~~~bash
export SPRING_PROFILES_ACTIVE=prod
java -jar order-service.jar
~~~

Hoặc truyền cho đúng một lần chạy:

~~~bash
SPRING_PROFILES_ACTIVE=prod java -jar order-service.jar
~~~

Để kích hoạt nhiều profile:

~~~bash
export SPRING_PROFILES_ACTIVE=prod,cloud
java -jar order-service.jar
~~~

Giá trị biến môi trường là chuỗi chứa các tên profile phân tách bởi dấu phẩy. Dùng một chuỗi rõ ràng giúp dễ kiểm tra trong script triển khai.

### 5.2. Windows PowerShell

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
java -jar order-service.jar
~~~

Lệnh này đặt biến môi trường cho tiến trình PowerShell hiện tại và các tiến trình con được chạy từ đó. Nó không tự sửa `application.properties` bên trong JAR.

Có thể bỏ biến này trong phiên PowerShell khi không cần nữa:

~~~powershell
Remove-Item Env:SPRING_PROFILES_ACTIVE
~~~

### 5.3. Windows Command Prompt

~~~bat
set SPRING_PROFILES_ACTIVE=dev
java -jar order-service.jar
~~~

Giá trị có hiệu lực cho phiên `cmd.exe` tương ứng và các tiến trình con. Cú pháp của `set` không giống PowerShell nên tránh sao chép lẫn hai môi trường.

### 5.4. Docker Compose

Có thể cung cấp active profile từ cấu hình container:

~~~yaml
services:
  order-service:
    image: example/order-service:1.0
    environment:
      SPRING_PROFILES_ACTIVE: prod
~~~

Container chạy cùng một image, nhưng Spring Boot nhận profile `prod` từ biến môi trường. Khi dùng nhiều profile:

~~~yaml
services:
  order-service:
    image: example/order-service:1.0
    environment:
      SPRING_PROFILES_ACTIVE: "prod,cloud"
~~~

Không cần tạo một image riêng chỉ để hardcode `spring.profiles.active` theo môi trường.

### 5.5. Kubernetes

Trong Pod hoặc Deployment, cấu hình biến môi trường cho container:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: order-service
          image: example/order-service:1.0
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: "prod,cloud"
~~~

Đây là ví dụ về cách cung cấp profile qua môi trường. Trong thực tế có thể dùng ConfigMap, hệ thống triển khai hoặc công cụ quản lý manifest để quản lý giá trị. Profile không thay thế chính sách cấp quyền, bảo vệ secret hoặc kiểm soát hạ tầng.

## 6. Kích hoạt bằng Java system property

Java cho phép đặt system property bằng tùy chọn JVM `-D`:

~~~bash
java -Dspring.profiles.active=prod -jar order-service.jar
~~~

Tùy chọn `-Dspring.profiles.active=prod` nằm **trước** `-jar` vì nó là đối số dành cho Java launcher. Nếu đặt sau `-jar`, nó thường được đưa tới chương trình như đối số ứng dụng và không còn là cách thiết lập Java system property.

Nhiều profile:

~~~bash
java -Dspring.profiles.active=prod,cloud -jar order-service.jar
~~~

Một Java process có thể chứa các system properties cấu hình khác:

~~~bash
java \
  -Dspring.profiles.active=prod \
  -Dserver.port=9090 \
  -jar order-service.jar
~~~

Cách này hữu ích khi công cụ chạy ứng dụng có nơi cung cấp JVM options riêng. Không cần sửa file trong JAR.

**Phân biệt ba dạng đầu vào:**

| Cách | Ví dụ | Được đưa vào đâu? |
| --- | --- | --- |
| Biến môi trường | `SPRING_PROFILES_ACTIVE=prod` | Environment của hệ điều hành |
| Java system property | `-Dspring.profiles.active=prod` | Java system properties |
| Command-line argument | `--spring.profiles.active=prod` | Đối số ứng dụng Spring Boot |

Chúng có thể chứa cùng một ý nghĩa nhưng thuộc các `PropertySource` khác nhau và có thể có độ ưu tiên khác nhau.

## 7. Kích hoạt bằng command-line arguments của Spring Boot

Đối số khởi động `--spring.profiles.active=...` là một cách chỉ định profile trực tiếp:

~~~bash
java -jar order-service.jar --spring.profiles.active=dev
~~~

Chạy production:

~~~bash
java -jar order-service.jar --spring.profiles.active=prod
~~~

Nhiều profile:

~~~bash
java -jar order-service.jar --spring.profiles.active=prod,cloud
~~~

Spring Boot mặc định đưa các đối số ứng dụng dạng `--key=value` vào `Environment`. Đối số command line thường có độ ưu tiên cao so với cấu hình file, biến môi trường và Java system properties.

Ví dụ:

~~~properties
# application.properties
spring.profiles.active=dev
~~~

Nhưng chạy:

~~~bash
java -jar order-service.jar --spring.profiles.active=prod
~~~

Trong cấu hình Spring Boot mặc định, profile có hiệu lực từ property này là `prod`; `dev` trong file không tự được cộng thêm.

Có thể cấu hình `SpringApplication` để không thêm command-line properties vào `Environment` (ví dụ `setAddCommandLineProperties(false)`). Khi làm vậy, không thể mặc định dựa vào quy tắc ưu tiên đối số `--spring.profiles.active` như trên. Những ví dụ ở đây giả định hành vi khởi động Spring Boot thông thường.

### 7.1. Truyền đối số khi chạy qua Maven hoặc Gradle

Khi chạy từ công cụ build, profile thường được truyền qua cấu hình của plugin tương ứng hoặc đối số cho ứng dụng. Chẳng hạn với Spring Boot Maven Plugin:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=dev
~~~

Đây là **tham số của Maven plugin**, không phải Java system property `spring.profiles.active` trực tiếp. Plugin sẽ dùng cấu hình đó để thiết lập profile cho ứng dụng khi chạy. Cú pháp có thể khác tùy công cụ và phiên bản plugin.

Với Gradle, cách phổ biến là cấu hình `bootRun` truyền đối số ứng dụng:

~~~groovy
// build.gradle
tasks.named('bootRun') {
    args '--spring.profiles.active=dev'
}
~~~

Nên tránh hardcode profile phát triển trong script build dùng để đóng gói production, trừ khi đó là chủ đích của dự án.

## 8. Quy tắc ưu tiên khi nhiều nguồn cùng đặt `spring.profiles.active`

Externalized Configuration cho phép một khóa xuất hiện ở nhiều nguồn. `spring.profiles.active` cũng tuân theo quy tắc độ ưu tiên của property sources.

Xem ví dụ:

~~~properties
# application.properties
spring.profiles.active=dev
~~~

Môi trường hệ điều hành:

~~~bash
export SPRING_PROFILES_ACTIVE=staging
~~~

Và lệnh khởi động:

~~~bash
java -Dspring.profiles.active=test \
  -jar order-service.jar \
  --spring.profiles.active=prod
~~~

Trong Spring Boot thông thường, đối số `--spring.profiles.active=prod` có độ ưu tiên cao hơn Java system property, biến môi trường và file config; profile được chọn qua `spring.profiles.active` sẽ là `prod`.

Có thể ghi nhớ một số thứ tự thường gặp, từ độ ưu tiên thấp lên cao:

~~~text
application.properties / application.yml
                ↓
OS environment variables
                ↓
Java system properties
                ↓
Spring Boot command-line arguments
~~~

Đây là **rút gọn của thứ tự nguồn cấu hình**, không phải bảng đầy đủ: Spring Boot còn có external Config Data, `SPRING_APPLICATION_JSON`, nguồn từ test framework, các source khác và khả năng tùy biến lúc khởi động. Tài liệu Config Data có quy tắc ưu tiên chi tiết giữa file ngoài, file classpath và file profile-specific. Khi hai nguồn trùng nhau, luôn xem xét **toàn bộ thứ tự thực tế**.

### 8.1. Toàn bộ danh sách profile bị thay thế, không tự ghép với nguồn thấp hơn

Giả sử:

~~~properties
# application.properties
spring.profiles.active=dev,metrics
~~~

Và biến môi trường:

~~~bash
SPRING_PROFILES_ACTIVE=prod
~~~

Giá trị `spring.profiles.active` đến từ nguồn có độ ưu tiên cao hơn là `prod`. Spring Boot không tự ghép danh sách thành `dev,metrics,prod` chỉ vì nguồn thấp hơn khai báo nhiều profile.

Điều này khác với **`spring.profiles.include`** và **profile groups**, vốn tồn tại nhằm bổ sung hoặc gom các profile có quan hệ.

### 8.2. Một profile có thể xuất hiện từ nhiều cơ chế

Khi kiểm tra các profile đang active, đôi lúc nhận thấy có nhiều profile hơn danh sách cuối cùng của `spring.profiles.active`. Nguyên nhân có thể là:

- `spring.profiles.include` bổ sung profile.
- `spring.profiles.group.<name>` mở rộng một profile nhóm.
- Code dùng `SpringApplication.setAdditionalProfiles(...)`.
- Test framework sử dụng `@ActiveProfiles` hoặc cung cấp profile trong quá trình dựng context.
- Một extension của ứng dụng can thiệp vào quá trình chuẩn bị `Environment`.

Vì vậy, **“giá trị effective của property”** và **“tập active profiles cuối cùng trong Environment”** là hai thông tin liên quan nhưng không luôn trùng nhau.

## 9. Cấu hình nhiều profile và thứ tự ghi đè

### 9.1. Khai báo nhiều profile

~~~bash
java -jar order-service.jar --spring.profiles.active=dev,cloud
~~~

Spring Boot sẽ xem xét cả hai profile. Nếu có các file:

~~~properties
# application.properties
app.client.timeout=5s
~~~

~~~properties
# application-dev.properties
app.client.timeout=2s
~~~

~~~properties
# application-cloud.properties
app.client.timeout=8s
~~~

Trong ví dụ đơn giản khi các file nằm tại cùng một location group và không có nguồn ưu tiên cao hơn, **profile xuất hiện sau có thể ghi đè profile xuất hiện trước**, nên `app.client.timeout` có thể là `8s`.

Nếu đổi thành:

~~~bash
java -jar order-service.jar --spring.profiles.active=cloud,dev
~~~

giá trị sẽ có thể là `2s` trong cùng điều kiện. Đó là quy tắc **last wins** khi xử lý profile-specific properties ở cùng cấp vị trí.

### 9.2. File location cũng có mức ưu tiên

Thứ tự profile không phải yếu tố duy nhất. Spring Boot có thể đọc file tại:

~~~text
classpath:/application.properties
classpath:/config/application.properties
file:./application.properties
file:./config/application.properties
file:./config/*/application.properties
~~~

Các location được sắp theo thứ tự/nhóm ưu tiên của Config Data. Một file bên ngoài có độ ưu tiên cao hơn có thể ghi đè giá trị từ file profile-specific bên trong JAR.

Với `spring.config.location` hoặc `spring.config.additional-location`, cách nhóm location bằng dấu `,` và `;` cũng có thể ảnh hưởng đến kết quả khi nhiều profile được kích hoạt. Khi giải thích giá trị cuối, cần kết hợp thứ tự property source, location group và thứ tự profile.

### 9.3. Không hiểu profile như cơ chế merge file nguyên khối

Khi có `application.properties` và `application-prod.properties`, Spring Boot không đơn giản chọn một file rồi bỏ file còn lại. Các property sources đều có thể góp giá trị; khóa nào không bị ghi đè có thể được giữ từ nguồn cơ sở.

Ngược lại, một số thuộc tính có giá trị dạng danh sách có quy tắc binding riêng và không nhất thiết hợp nhất phần tử giữa các nguồn. Đối với `spring.profiles.active`, nguồn có độ ưu tiên cao hơn quyết định danh sách khai báo của property đó.

## 10. Khác biệt giữa `spring.profiles.active`, `default` và `include`

### 10.1. `spring.profiles.default`

Spring Framework có khái niệm **default profile** được dùng khi không có active profile tường minh. Trong Spring Boot, tên default profile thông thường là `default`. Có thể cấu hình:

~~~properties
spring.profiles.default=local
~~~

Nếu không có active profile nào được chỉ định theo các cơ chế phù hợp, `local` sẽ là profile mặc định được áp dụng. Điều này có thể làm file `application-local.properties` tham gia vào Config Data.

Nếu đã kích hoạt `prod`, default profile không thay thế `prod`.

Khi muốn không sử dụng default profile:

~~~properties
spring.profiles.default=none
~~~

Đây là cấu hình được Spring Boot hỗ trợ để vô hiệu hóa default profile theo quy ước; không nên tự đặt một file `application-none.properties` rồi coi `none` như môi trường production.

### 10.2. `spring.profiles.include`

Khi một profile chính cần đi kèm một số profile phụ, có thể dùng:

~~~properties
spring.profiles.active=prod
spring.profiles.include=metrics
~~~

Mục tiêu: bổ sung profile `metrics` bên cạnh `prod`. Thông thường, include được dùng khi nhiều môi trường đều cần những thành phần giống nhau.

Lưu ý: `spring.profiles.include` được xử lý theo quy tắc riêng cho từng `PropertySource` và không đơn thuần bị thay thế như toàn bộ chuỗi `spring.profiles.active`. Điều này quan trọng trong hệ thống có nhiều location.

### 10.3. Profile groups

Một lựa chọn khác là định nghĩa nhóm profile:

~~~properties
spring.profiles.group.production[0]=proddb
spring.profiles.group.production[1]=prodmq
~~~

Sau đó chạy:

~~~bash
java -jar order-service.jar --spring.profiles.active=production
~~~

Nhóm `production` được mở rộng để kích hoạt các profile bổ sung `proddb` và `prodmq`. Cách này giúp người vận hành dùng một tên ngắn, trong khi từng profile phụ có thể điều khiển cấu hình hoặc bean cụ thể.

Trong YAML, cách viết dễ đọc:

~~~yaml
spring:
  profiles:
    group:
      production:
        - proddb
        - prodmq
~~~

Cả `spring.profiles.include` và định nghĩa `spring.profiles.group.*` cần được đặt trong **document không đặc thù cho profile** theo quy tắc Config Data của Spring Boot hiện đại.

## 11. Những nơi không được đặt `spring.profiles.active`

Đây là một giới hạn cần nhớ khi dùng Spring Boot Config Data.

**`spring.profiles.active` và `spring.profiles.default` chỉ được đặt trong các document không đặc thù cho profile.** Không được đặt các thuộc tính này trong:

1. File profile-specific như `application-prod.properties`.
2. YAML document đã có `spring.config.activate.on-profile=prod`.

Ví dụ sai:

~~~properties
# application-prod.properties — KHÔNG HỢP LỆ
spring.profiles.active=prod,cloud
~~~

Ví dụ sai tương tự trong YAML:

~~~yaml
spring:
  config:
    activate:
      on-profile: prod
  profiles:
    active: cloud
~~~

Spring Boot hiện đại có thể báo lỗi dạng `InvalidConfigDataPropertyException` khi gặp cấu hình như vậy. Lý do: Boot cần biết các profile đang active **trước khi** quyết định nạp nội dung theo profile. Một file đã được nạp có điều kiện không thể dùng cách này để tự ý thay đổi điều kiện chọn file.

**Cách sửa đúng:** đưa lựa chọn profile vào nguồn không đặc thù cho profile, ví dụ:

~~~properties
# application.properties
spring.profiles.active=prod,cloud
~~~

Hoặc đặt qua biến môi trường/đối số chạy:

~~~bash
java -jar order-service.jar --spring.profiles.active=prod,cloud
~~~

Nếu mục tiêu là các profile phụ `cloud` luôn đi cùng `prod`, cân nhắc định nghĩa `spring.profiles.group.prod` ở document không đặc thù cho profile.

Tương tự, không đặt `spring.profiles.include` hay định nghĩa `spring.profiles.group` trong document profile-specific hoặc document có `spring.config.activate.on-profile`.

## 12. Chọn active profile từ code Java

Ngoài property ngoài ứng dụng, Spring Boot còn có API khởi động chương trình. Đây là cơ chế khác với khai báo `spring.profiles.active` trực tiếp.

Ví dụ bổ sung profile qua `SpringApplication`:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication application = new SpringApplication(OrderApplication.class);
        application.setAdditionalProfiles("local");
        application.run(args);
    }
}
~~~

`setAdditionalProfiles("local")` dùng để **bổ sung** profile cho phiên khởi động này. Nó có thể tồn tại cùng với profile được chọn qua cấu hình ngoài. Không nên coi API này là tương đương hoàn toàn với việc đặt property `spring.profiles.active` ở một nguồn cụ thể.

Spring Framework cũng có `ConfigurableEnvironment.setActiveProfiles(...)`, nhưng nếu tự can thiệp vào môi trường cần thực hiện ở giai đoạn đủ sớm để phù hợp với thứ tự nạp Config Data. Thay đổi profile sau khi application context đã tạo bean không tự động xây lại các bean hoặc nạp lại toàn bộ file cấu hình theo profile.

**Khuyến nghị:** để profile là lựa chọn của môi trường triển khai nếu không có yêu cầu đặc biệt. Nếu gắn profile bắt buộc trong Java code, cần ý thức rằng hành vi của ứng dụng có thể khó thay đổi chỉ bằng cấu hình bên ngoài.

## 13. Active profile trong kiểm thử Spring Boot

Với bài kiểm thử tích hợp, có thể sử dụng annotation của Spring Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class OrderApplicationTests {

    @Test
    void contextLoads() {
    }
}
~~~

Annotation `@ActiveProfiles("test")` nói với Spring TestContext Framework profile nào cần hoạt động khi tạo context cho bài kiểm thử. Khi dự án có `application-test.properties`, những cấu hình dành cho profile `test` có thể được áp dụng.

Ví dụ:

~~~properties
# src/test/resources/application-test.properties
app.payment.mode=fake
app.client.timeout=500ms
~~~

Cách này giúp bài kiểm thử xác định môi trường một cách rõ ràng, giảm phụ thuộc vào biến môi trường của máy chạy CI.

Cần phân biệt `@ActiveProfiles` với việc tự đặt `spring.profiles.active` trong `application-test.properties`: file `application-test.properties` đã là file profile-specific nên không được dùng để tự kích hoạt thêm profile bằng `spring.profiles.active`. Khi cần profile bổ sung, hãy cấu hình ở nơi không profile-specific hoặc qua cơ chế test phù hợp.

## 14. Một quy trình triển khai nhất quán

Giả sử dự án có các file sau:

~~~text
src/main/resources/
├── application.yml
├── application-dev.yml
├── application-staging.yml
└── application-prod.yml
~~~

Cấu hình chung:

~~~yaml
# application.yml
spring:
  application:
    name: order-service

app:
  client:
    timeout: 5s
  feature:
    demo-mode: false
~~~

Môi trường development:

~~~yaml
# application-dev.yml
app:
  client:
    timeout: 2s
  feature:
    demo-mode: true
~~~

Môi trường staging:

~~~yaml
# application-staging.yml
app:
  client:
    timeout: 4s
~~~

Môi trường production:

~~~yaml
# application-prod.yml
app:
  client:
    timeout: 10s
~~~

Chạy ở máy phát triển:

~~~bash
java -jar order-service.jar --spring.profiles.active=dev
~~~

Chạy tại staging:

~~~bash
SPRING_PROFILES_ACTIVE=staging java -jar order-service.jar
~~~

Chạy tại production qua Java system property:

~~~bash
java -Dspring.profiles.active=prod -jar order-service.jar
~~~

Kết quả kỳ vọng trong tình huống không có property source khác ghi đè:

| Môi trường | Profile active | `app.client.timeout` | `app.feature.demo-mode` |
| --- | --- | --- | --- |
| Development | `dev` | `2s` | `true` |
| Staging | `staging` | `4s` | `false` |
| Production | `prod` | `10s` | `false` |

Bản build và mã Java không cần thay đổi giữa ba môi trường. Tất cả khác biệt được biểu diễn bằng cấu hình và profile được chọn khi khởi động.

Đối với secret như mật khẩu database, API key hoặc private key, không nên chỉ dùng profile để bảo vệ. Chúng cần được đưa vào từ nguồn bí mật thích hợp; profile chỉ quyết định **bộ cấu hình** và bean áp dụng.

## 15. Quan sát active profile trong ứng dụng

### 15.1. Đọc qua `Environment`

Spring Framework cung cấp `Environment.getActiveProfiles()`:

~~~java
import java.util.Arrays;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ActiveProfileInspector {
    private final Environment environment;

    public ActiveProfileInspector(Environment environment) {
        this.environment = environment;
    }

    public String[] activeProfiles() {
        return environment.getActiveProfiles();
    }

    public String describe() {
        return "Active profiles: " + Arrays.toString(activeProfiles());
    }
}
~~~

Kết quả có thể là `[prod]` hoặc `[prod, cloud]`, tùy cách khởi động và các cơ chế bổ sung profile. Nếu không đặt active profile, `getActiveProfiles()` có thể trả về mảng rỗng ngay cả khi Spring có **default profile**; muốn xem default profile cần gọi `getDefaultProfiles()`.

### 15.2. Đọc riêng property và danh sách active

Hai cách đọc sau không tương đương trong mọi trường hợp:

~~~java
String rawActive = environment.getProperty("spring.profiles.active");
String[] activeProfiles = environment.getActiveProfiles();
~~~

`rawActive` cho biết giá trị `spring.profiles.active` được phân giải từ các nguồn thuộc tính; `activeProfiles` cho biết tập profile mà môi trường xem là active, có thể bao gồm profile đến từ include, group hoặc API khởi động.

Khi điều tra lỗi, nên kiểm tra **cả hai** nếu nghi ngờ profile được bổ sung theo cách không nằm trong giá trị property.

### 15.3. Log lúc khởi động

Spring Boot thường ghi thông báo về profile đang hoạt động trong quá trình khởi động ứng dụng. Thông báo cụ thể và độ chi tiết phụ thuộc phiên bản và cấu hình logging.

Nếu cần chẩn đoán các file được nạp và điều kiện profile, có thể bật log chi tiết cho gói Config Data:

~~~bash
java -jar order-service.jar \
  --logging.level.org.springframework.boot.context.config=TRACE
~~~

Đây là mức log dùng để điều tra trong môi trường phù hợp. Tránh bật log chi tiết rộng rãi ở production khi không cần, và không ghi những property nhạy cảm vào log.

## 16. Các lỗi thường gặp

### 16.1. Đặt `spring.profiles.active` trong `application-prod.properties`

**Sai:**

~~~properties
# application-prod.properties
spring.profiles.active=prod
~~~

File này cần profile `prod` để được chọn, nên không được dùng nó để chọn chính profile đó. Đặt property trong `application.properties` không profile-specific hoặc truyền qua môi trường khi chạy.

### 16.2. Nghĩ rằng file `application-prod.yml` tự kích hoạt `prod`

Chỉ đặt file `application-prod.yml` trong JAR không đủ để làm `prod` hoạt động. Cần khai báo profile ở nguồn phù hợp, ví dụ:

~~~bash
java -jar order-service.jar --spring.profiles.active=prod
~~~

Hoặc có cơ chế khác đã kích hoạt `prod` trước đó.

### 16.3. Bị nguồn ưu tiên cao hơn ghi đè mà không biết

~~~properties
# application.properties
spring.profiles.active=dev
~~~

Nếu process có `SPRING_PROFILES_ACTIVE=prod`, kết quả thường là `prod`. Kiểm tra biến môi trường, JVM options và command-line arguments trước khi kết luận file cấu hình không được đọc.

### 16.4. Kích hoạt nhiều profile rồi gặp cấu hình trùng khóa

~~~bash
java -jar order-service.jar --spring.profiles.active=dev,prod
~~~

Khi hai profile cùng khai báo một khóa, kết quả phụ thuộc thứ tự profile và location group. Không nên bật cả `dev` và `prod` nếu các profile đó được thiết kế loại trừ nhau và có bean xung đột.

### 16.5. Nhầm `spring.profiles.default` với `spring.profiles.active`

`spring.profiles.default` chỉ có ý nghĩa khi không có active profile tường minh. Đặt default profile là `local` không có nghĩa profile `local` luôn cùng hoạt động với `prod`.

### 16.6. Dùng tên biến môi trường sai

Đối với thuộc tính `spring.profiles.active`, tên biến môi trường thông dụng là `SPRING_PROFILES_ACTIVE`. Cách đặt `SPRING_PROFILE_ACTIVE` (thiếu chữ `S` trong `PROFILES`) không khớp thuộc tính đang cần.

### 16.7. Đổi biến môi trường sau khi ứng dụng đã khởi động

Spring Boot xử lý lựa chọn profile và nạp Config Data ở giai đoạn khởi động. Thay đổi `SPRING_PROFILES_ACTIVE` trong terminal khác sau khi tiến trình đang chạy không làm context tự tải lại bean hoặc file theo profile. Thông thường cần khởi động lại ứng dụng, hoặc sử dụng cơ chế cấu hình động được thiết kế riêng.

### 16.8. Dùng `@PropertySource` để chọn profile quá muộn

`@PropertySource` của Spring Framework được xử lý khi application context đang dựng. Các quyết định liên quan Config Data và một số tính năng khởi động được thực hiện sớm hơn. Vì vậy, không nên dựa vào `@PropertySource` để cung cấp `spring.profiles.active` nhằm chọn các file `application-{profile}.*`. Sử dụng một trong những nguồn khởi động được Boot hỗ trợ để chọn profile từ đầu.

### 16.9. Xem profile như ranh giới bảo mật

Việc dùng `@Profile("prod")` không thay thế bảo vệ quyền truy cập, bí mật cấu hình hoặc xác thực. Tên profile là một cờ cấu hình; người có quyền thay đổi biến môi trường/đối số chạy có thể thay đổi bộ profile được chọn. Các biện pháp an toàn thực sự cần được áp dụng tại hạ tầng và ứng dụng.

## 17. Quy trình chẩn đoán một profile không hoạt động như mong đợi

Khi một bean `@Profile("prod")` không được tạo hoặc file `application-prod.yml` dường như không có hiệu lực, lần lượt kiểm tra:

1. **Profile được kích hoạt ở đâu?** Tìm trong file không profile-specific, biến môi trường, Java system properties, command line, cấu hình test và API khởi động.
2. **Tên property và tên profile có chính xác không?** Dùng `spring.profiles.active`, `SPRING_PROFILES_ACTIVE`; tên profile `prod` phải khớp với `@Profile("prod")` và `application-prod.yml`.
3. **Nguồn nào có độ ưu tiên cao nhất?** Nếu file khai báo `dev` nhưng command line khai báo `prod`, hãy giải thích theo thứ tự nguồn thay vì chỉ đọc nội dung file.
4. **Có cơ chế include/group/additional profile không?** Các cơ chế này có thể bổ sung profile không thấy trong chuỗi property.
5. **Có cấu hình bị đặt sai vị trí không?** `spring.profiles.active` trong file profile-specific hoặc document có `spring.config.activate.on-profile` là không hợp lệ trong Config Data hiện đại.
6. **Đường dẫn và tên file có chính xác không?** File `application-prod.yml` phải nằm tại location mà Spring Boot đang tìm; `spring.config.location` và `spring.config.additional-location` có thể thay đổi tập location.
7. **Có nhiều profile cùng ghi đè một khóa không?** Xem thứ tự profile và location group.
8. **Có bean trùng hoặc thiếu bean khi profile thay đổi không?** Kiểm tra `@Profile`, các điều kiện tạo bean và dependency injection.
9. **Sau khi đổi cấu hình đã khởi động lại tiến trình chưa?** Profile thông thường không tự thay đổi trong context đang chạy.
10. **Giá trị effective thực tế là gì?** Đọc `Environment.getActiveProfiles()`, `getDefaultProfiles()` và property cần xét; nếu có Actuator phù hợp thì xem nguồn config đã được che dữ liệu nhạy cảm.

Đối với môi trường có Spring Boot Actuator và kiểm soát quyền truy cập phù hợp, endpoint `/actuator/env` có thể hỗ trợ chẩn đoán property sources. Không mở endpoint cấu hình ra Internet chỉ để xem profile và không làm lộ secret khi bật công cụ debug.

## 18. Checklist triển khai

| Câu hỏi | Cách xử lý đề xuất |
| --- | --- |
| Ứng dụng có dùng cùng một JAR cho nhiều môi trường không? | Giữ file chung trong JAR, truyền `spring.profiles.active` qua môi trường chạy |
| Profile chạy local được chọn bằng gì? | `--spring.profiles.active=dev` hoặc `SPRING_PROFILES_ACTIVE=dev` |
| Profile production được chọn bằng gì? | Biến môi trường, JVM option hoặc command-line argument của hệ thống triển khai |
| Có nhiều profile cùng hoạt động không? | Liệt kê bằng dấu phẩy; xem thứ tự và các khóa trùng |
| Có profile phụ luôn cần đi kèm không? | Xem `spring.profiles.include` hoặc profile groups trong document không profile-specific |
| Có muốn mặc định dùng cấu hình local khi chưa chọn active profile không? | Cân nhắc `spring.profiles.default=local` |
| Bị báo lỗi khai báo profile trong file theo profile? | Chuyển `spring.profiles.active` ra nguồn không profile-specific |
| File theo profile không được nạp? | Kiểm tra tên profile, location, working directory và thứ tự Config Data |
| Runtime có profile ngoài mong đợi? | So sánh `Environment.getActiveProfiles()` với property cùng các cơ chế include/group |
| Thay đổi profile mà ứng dụng không đổi hành vi? | Kiểm tra đã khởi động lại và bean/property nào thực sự phụ thuộc profile |

## 19. Kết luận

**`spring.profiles.active` là khóa chọn tập profile hoạt động trong Spring Boot**, có thể được cung cấp qua file cấu hình không đặc thù cho profile, biến môi trường `SPRING_PROFILES_ACTIVE`, Java system property `-Dspring.profiles.active` hoặc command-line argument `--spring.profiles.active`. Khi nhiều nguồn cùng khai báo, Spring Boot áp dụng thứ tự ưu tiên của Externalized Configuration.

Việc chọn profile chỉ là bước đầu: Boot sau đó dùng profile để nạp file `application-{profile}.*` và các document có `spring.config.activate.on-profile`, còn Spring Framework dùng profile để kiểm soát bean có `@Profile`. Đối với nhiều profile, cần quan tâm thứ tự, location group và cơ chế include/group. Đừng đặt `spring.profiles.active` trong chính file hay document đã yêu cầu profile đó để được nạp.

Một thiết kế dễ vận hành là **giữ cấu hình chung trong artifact, đặt phần khác biệt ở các file theo profile, và chọn profile bằng nguồn cấu hình của môi trường triển khai**. Cách đó giúp đổi môi trường mà không phải sửa mã nguồn hoặc build lại JAR.

### Tài liệu tham khảo

- [Spring Boot Reference — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html)
- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Framework — Environment Abstraction](https://docs.spring.io/spring-framework/reference/core/beans/environment.html)

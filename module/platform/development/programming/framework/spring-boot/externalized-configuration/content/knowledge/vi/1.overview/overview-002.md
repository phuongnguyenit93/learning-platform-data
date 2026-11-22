# Một bản dựng dùng cho nhiều môi trường: mã nguồn và cấu hình thay đổi độc lập

## 1. Vấn đề cần giải quyết

Một ứng dụng Spring Boot thường đi qua nhiều môi trường: máy lập trình viên (local), phát triển chung (dev), kiểm thử (staging) và sản xuất (prod). Chúng có thể dùng URL cơ sở dữ liệu, cổng HTTP, mức ghi log, địa chỉ dịch vụ ngoài và thông tin xác thực khác nhau. Tuy nhiên, **logic nghiệp vụ được kiểm thử và phát hành phải là cùng một phiên bản**.

Cách làm dễ gây rủi ro là sửa các giá trị cấu hình trong mã nguồn rồi build một file JAR riêng cho từng môi trường. Khi đó rất khó chứng minh bản chạy ở production chính là bản đã kiểm thử ở staging, và một thay đổi cấu hình nhỏ cũng kéo theo biên dịch, đóng gói lại.

Spring Boot giải quyết bằng **externalized configuration**: mã nguồn định nghĩa ứng dụng làm gì, còn cấu hình được cung cấp khi ứng dụng khởi động để quyết định ứng dụng kết nối và vận hành ở đâu, theo tham số nào.

~~~text
Một commit mã nguồn
       |
       v
Build + test một lần
       |
       v
   app.jar (một artifact)
       |
       +---- cấu hình DEV ----> chạy ở DEV
       |
       +---- cấu hình STAGING -> chạy ở STAGING
       |
       +---- cấu hình PROD ---> chạy ở PROD
~~~

**Nguyên tắc:** *Build once, deploy many*. Có thể triển khai cùng một JAR hoặc cùng một Docker image sang nhiều môi trường bằng cách thay đổi cấu hình tại thời điểm chạy.

## 2. Phân biệt mã nguồn, bản dựng và cấu hình

| Thành phần | Chứa gì? | Khi nào cần thay đổi? |
| --- | --- | --- |
| **Mã nguồn** | Controller, service, quy tắc nghiệp vụ, xử lý dữ liệu | Khi hành vi ứng dụng hoặc hợp đồng API thay đổi |
| **Artifact** | JAR hoặc Docker image được tạo từ một phiên bản mã nguồn | Khi phát hành phiên bản ứng dụng mới |
| **Cấu hình** | Host, port, endpoint, timeout, pool size, feature flag phù hợp, thông tin kết nối | Khi điều kiện vận hành của môi trường thay đổi |
| **Secret** | Mật khẩu, token, khóa truy cập | Theo chính sách cấp phát, luân chuyển và thu hồi bí mật |

Ví dụ, một service đọc đơn hàng vẫn dùng cùng một phương thức Java ở dev và prod. Điểm khác là **spring.datasource.url** trỏ đến hai database khác nhau; thông tin xác thực được cấp riêng cho từng môi trường. Không cần sửa controller hoặc tạo nhánh mã nguồn "dành cho production".

Cấu hình có thể nằm trong file đóng gói để cung cấp **giá trị mặc định không nhạy cảm**, trong file nằm ngoài JAR, biến môi trường, Java system properties hoặc tham số dòng lệnh. Spring Boot kết hợp các nguồn đó và áp dụng quy tắc độ ưu tiên khi cùng một property được khai báo ở nhiều nơi.

## 3. Ví dụ Spring Boot: cùng code, nhiều giá trị cấu hình

Giả sử dự án dùng Java 21, Spring Boot 3.x và dependency **spring-boot-starter-web**. Ta tạo một API **GET /greeting** để nhìn thấy kết quả cấu hình.

**Tệp ConfigDemoApplication.java:**

~~~java
package com.example.configdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConfigDemoApplication.class, args);
    }
}
~~~

**Tệp AppProperties.java:** dùng **@ConfigurationProperties** để ràng buộc một nhóm property vào kiểu Java, thay vì rải các chuỗi key trong nhiều lớp.

~~~java
package com.example.configdemo;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(String greeting, String environmentLabel) {
}
~~~

**Tệp GreetingController.java:**

~~~java
package com.example.configdemo;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    private final AppProperties properties;

    public GreetingController(AppProperties properties) {
        this.properties = properties;
    }

    @GetMapping("/greeting")
    public Map<String, String> greeting() {
        return Map.of(
            "message", properties.greeting(),
            "environment", properties.environmentLabel()
        );
    }
}
~~~

Các lớp nằm trong cùng package **com.example.configdemo**. **@ConfigurationPropertiesScan** giúp Spring Boot đăng ký **AppProperties**; controller chỉ phụ thuộc vào đối tượng cấu hình, không cần tự dò biến môi trường.

Trong thư mục **src/main/resources**, thêm ba file:

**application.yml** — cấu hình mặc định:

~~~yaml
server:
  port: 8080

app:
  greeting: "Xin chào từ cấu hình mặc định"
  environment-label: "default"
~~~

**application-dev.yml** — cấu hình cho profile dev:

~~~yaml
server:
  port: 8081

app:
  greeting: "Xin chào từ DEV"
  environment-label: "dev"
~~~

**application-prod.yml** — cấu hình cho profile prod:

~~~yaml
server:
  port: 8080

app:
  greeting: "Xin chào từ PROD"
  environment-label: "prod"
~~~

File **application.yml** và các file theo profile đều có thể được đóng gói trong cùng một JAR. Điều thay đổi lúc chạy là **profile được kích hoạt** và những giá trị cấu hình đến từ môi trường triển khai. Trong dự án thực, những thông số nhạy cảm và thông số thay đổi thường xuyên nên được cấp từ bên ngoài artifact.

## 4. Build một lần, chạy thử ở hai môi trường

Với một dự án Gradle có Spring Boot plugin, tạo JAR bằng:

~~~bash
./gradlew bootJar
~~~

Ví dụ giả sử artifact được tạo là **build/libs/config-demo-0.0.1-SNAPSHOT.jar**. Thay đường dẫn này bằng tên JAR thực tế của dự án; ở các lệnh dưới đây, **không chạy build lại**.

**Lần 1 — chạy với profile dev:**

~~~bash
java -jar build/libs/config-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=dev
~~~

Gọi API:

~~~bash
curl http://localhost:8081/greeting
~~~

Kết quả minh họa:

~~~json
{
  "message": "Xin chào từ DEV",
  "environment": "dev"
}
~~~

Dừng tiến trình này, sau đó **dùng chính file JAR đó** để chạy profile prod:

~~~bash
java -jar build/libs/config-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=prod
~~~

~~~bash
curl http://localhost:8080/greeting
~~~

~~~json
{
  "message": "Xin chào từ PROD",
  "environment": "prod"
}
~~~

Ở hai lần chạy, controller, lớp cấu hình và bytecode trong JAR không thay đổi. Spring Boot đọc **spring.profiles.active** tại thời điểm khởi động rồi nạp cấu hình ứng với profile. Profile là cách chọn nhóm cấu hình; nó không tự tạo một artifact mới.

> Trong hệ thống nhiều môi trường, **dev**, **staging** và **prod** thường là các profile hoặc tập cấu hình khác nhau, nhưng một số thiết lập chung vẫn có thể nằm trong **application.yml**. Không nên coi profile là lý do để viết lại luồng nghiệp vụ ở mỗi môi trường.

## 5. Thay đổi cấu hình ngoài JAR bằng biến môi trường

Ta không cần sửa bất kỳ file Java hay YAML nào để ghi đè lời chào ở ví dụ trên. Spring Boot hỗ trợ cách ánh xạ tên property sang biến môi trường:

| Property Spring Boot | Biến môi trường |
| --- | --- |
| **spring.profiles.active** | **SPRING_PROFILES_ACTIVE** |
| **server.port** | **SERVER_PORT** |
| **app.greeting** | **APP_GREETING** |

Đối với shell Linux/macOS, có thể chạy:

~~~bash
SPRING_PROFILES_ACTIVE=prod APP_GREETING="Lời chào từ biến môi trường" SERVER_PORT=8082 \
  java -jar build/libs/config-demo-0.0.1-SNAPSHOT.jar
~~~

Trong PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "prod"
$env:APP_GREETING = "Lời chào từ biến môi trường"
$env:SERVER_PORT = "8082"
java -jar build/libs/config-demo-0.0.1-SNAPSHOT.jar
~~~

Khi gọi **http://localhost:8082/greeting**, thuộc tính **message** lấy từ **APP_GREETING**, còn **environment** vẫn là **prod** theo **application-prod.yml**. Cổng dịch vụ đổi sang **8082** vì **SERVER_PORT** ghi đè giá trị trong YAML. Giá trị này có hiệu lực với tiến trình vừa khởi động; sửa biến môi trường của shell sau đó thường đòi hỏi khởi động lại ứng dụng để nạp lại.

Lưu ý: cú pháp biến môi trường trên là ví dụ cho các property đã nêu; quy tắc chuyển đổi tổng quát của Spring Boot còn liên quan đến dấu chấm, dấu gạch ngang và chỉ số danh sách. Khi đặt key mới, nên kiểm tra tên biến tương ứng theo quy tắc *relaxed binding*.

## 6. Đưa file cấu hình ra ngoài artifact

Biến môi trường tiện cho container và nền tảng triển khai; file cấu hình ngoài JAR hữu ích khi cần một nhóm tham số. Ví dụ, người vận hành tạo file **./config/application.yml** trên máy đích:

~~~yaml
app:
  greeting: "Lời chào do môi trường triển khai cấp"
~~~

Khởi động ứng dụng và chỉ rõ vị trí cấu hình bổ sung:

~~~bash
java -jar build/libs/config-demo-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=optional:file:./config/
~~~

Spring Boot có thể nạp cấu hình từ vị trí bổ sung và sử dụng giá trị này cho **app.greeting**. Tham số **optional:** có nghĩa là không báo lỗi chỉ vì đường dẫn ấy không tồn tại; bỏ **optional:** khi việc thiếu file phải được coi là lỗi triển khai.

Hai lựa chọn dễ nhầm:

- **spring.config.additional-location**: bổ sung vị trí tìm cấu hình bên cạnh các vị trí mặc định.
- **spring.config.location**: khai báo vị trí cấu hình để thay thế tập vị trí mặc định; dùng khi chủ động muốn kiểm soát toàn bộ nguồn file.

Các property chỉ nơi tìm cấu hình cần được cung cấp sớm, ví dụ qua biến môi trường, system property hoặc đối số khi khởi động, để Spring Boot biết phải đọc file ở đâu.

Với cơ sở dữ liệu, cùng một JAR có thể lấy **SPRING_DATASOURCE_URL**, **SPRING_DATASOURCE_USERNAME** và **SPRING_DATASOURCE_PASSWORD** từ từng môi trường (khi ứng dụng đã có cấu hình và dependency datasource tương ứng). Production trỏ đến database production, staging trỏ đến database staging. **Không đặt mật khẩu thật vào application-prod.yml đã commit hoặc nhúng secret vào Docker image.** Hãy cấp secret bằng cơ chế an toàn của nền tảng vận hành.

## 7. Khi nhiều nguồn định nghĩa cùng một property

Spring Boot sử dụng độ ưu tiên nguồn cấu hình. Với ví dụ này, có thể hiểu theo thứ tự thường gặp:

1. Giá trị trong file **application.yml** là mặc định chung.
2. Giá trị ở file **application-prod.yml** áp dụng khi kích hoạt **prod** và có thể ghi đè giá trị cùng key từ file mặc định.
3. Biến môi trường **APP_GREETING** có thể ghi đè giá trị tương ứng trong các file cấu hình.
4. Đối số dòng lệnh như **--app.greeting=Hello** thường có độ ưu tiên cao hơn biến môi trường và các file YAML.

Đây là **một phần** của hệ thống thứ tự ưu tiên, không phải danh sách đầy đủ mọi nguồn Spring Boot hỗ trợ. Thứ tự thực tế còn phụ thuộc vị trí file, loại nguồn và cách ứng dụng được khởi tạo. Với một property gây bất ngờ, hãy truy ngược nguồn đã cấp giá trị cuối cùng thay vì sửa đại một file YAML.

Ví dụ:

~~~bash
java -jar build/libs/config-demo-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=prod \
  --app.greeting="Giá trị từ command line"
~~~

Dù **application-prod.yml** ghi **Xin chào từ PROD**, kết quả từ API sẽ hiển thị **Giá trị từ command line**.

## 8. Cùng Docker image cho staging và production

Trong môi trường container, quy tắc vẫn không đổi:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY build/libs/config-demo-0.0.1-SNAPSHOT.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Build image từ artifact đã kiểm thử:

~~~bash
docker build -t config-demo:1.0.0 .
~~~

Triển khai image ấy ở staging:

~~~bash
docker run --rm -p 8081:8080 \
  -e SPRING_PROFILES_ACTIVE=prod \
  -e APP_GREETING="Staging" \
  config-demo:1.0.0
~~~

Sau đó triển khai **cùng image** ở production với cấu hình do hệ thống production cấp:

~~~bash
docker run --rm -p 8080:8080 \
  -e SPRING_PROFILES_ACTIVE=prod \
  -e APP_GREETING="Production" \
  config-demo:1.0.0
~~~

Hai lệnh trên dùng cùng **config-demo:1.0.0**; chỉ giá trị cấu hình runtime khác nhau. Trong thực tế nên dùng định danh image bất biến (chẳng hạn image digest) để chắc chắn hai lần triển khai tham chiếu đúng cùng nội dung. Lệnh Docker ở đây chỉ minh họa cách cấp tham số; hệ thống production cần chính sách quản lý secret, mạng và tài nguyên phù hợp.

## 9. Những lỗi thiết kế thường gặp

**Build riêng cho từng môi trường.** Khi JAR dev và JAR prod được tạo từ các cấu hình hoặc nhánh code khác nhau, kết quả kiểm thử ở dev không còn đại diện chính xác cho sản phẩm chạy prod. Cần ưu tiên một artifact đã qua kiểm thử, còn khác biệt môi trường được cấp trong quá trình triển khai.

**Hardcode endpoint, password hoặc feature flag vào Java.** Điều này khiến thay đổi vận hành kéo theo sửa code và phát hành lại. Với cấu hình môi trường, nên sử dụng property và cơ chế quản lý secret phù hợp.

**Đưa secret thật vào Git hoặc log.** Một file tên **application-prod.yml** không tự làm nội dung an toàn. Secret có thể bị lộ qua repository, image, bản sao log hoặc cấu hình debug. Cần giới hạn quyền truy cập, hỗ trợ luân chuyển và không trả secret ra API.

**Cho rằng đổi file cấu hình sẽ tự cập nhật tiến trình đang chạy.** Spring Boot thông thường nạp cấu hình khi khởi động. Việc thay đổi biến môi trường hoặc file bên ngoài thường cần restart/redeploy; muốn làm mới cấu hình động phải có cơ chế riêng được thiết kế có chủ đích.

**Dùng profile để tạo hai ứng dụng nghiệp vụ khác nhau.** Profile phù hợp để chọn bean hoặc hạ tầng theo môi trường trong trường hợp cần thiết, nhưng không nên biến production thành một phiên bản logic nghiệp vụ chưa được kiểm thử. Mục tiêu của bài là giữ hành vi phát hành nhất quán.

## 10. Cách kiểm chứng nguyên tắc "build once, deploy many"

Khi triển khai một phiên bản, có thể xác nhận theo trình tự:

1. Ghi nhận commit, phiên bản và checksum của JAR hoặc digest của Docker image đã build.
2. Dùng nguyên artifact đó triển khai lần lượt sang các môi trường.
3. Cung cấp **spring.profiles.active**, URL phụ thuộc, secret và tham số vận hành qua nguồn cấu hình được quản lý của từng môi trường.
4. Kiểm tra service khởi động và kết nối đúng tài nguyên môi trường, ví dụ gọi **GET /greeting** trong bản demo.
5. Nếu chỉ thay endpoint hoặc timeout, cập nhật cấu hình và khởi động lại theo quy trình triển khai; không cần compile lại mã nguồn.
6. Nếu thay logic nghiệp vụ, tạo **artifact phiên bản mới**, kiểm thử rồi tiếp tục quy trình phát hành.

Có thể ghi chú nguồn của một property khi điều tra sự cố, nhưng tránh in giá trị secret. Trong môi trường production, không công khai các endpoint chẩn đoán có khả năng tiết lộ cấu hình.

## 11. Bài thực hành

Dùng bản demo trên để tự chứng minh mã nguồn và cấu hình thay đổi độc lập:

- **Lượt A:** build JAR một lần; chạy profile **dev** và quan sát cổng **8081** cùng thông điệp **DEV**.
- **Lượt B:** dừng tiến trình; chạy **cùng JAR** với profile **prod**, quan sát cổng **8080** và thông điệp **PROD**.
- **Lượt C:** vẫn dùng JAR cũ; cấp **APP_GREETING** và **SERVER_PORT** từ biến môi trường; kiểm tra giá trị API và cổng đã đổi.
- **Lượt D:** thêm file **./config/application.yml** ở ngoài JAR và chạy với **spring.config.additional-location**; kiểm tra nội dung file ngoài đã được sử dụng.
- **Lượt E:** đối chiếu tên và checksum của file JAR giữa các lượt. Nếu checksum không đổi nhưng hành vi cấu hình đổi đúng như mong đợi, bạn đã quan sát được tính chất **một bản dựng, nhiều môi trường**.

**Điểm cần ghi nhớ:** phiên bản mã nguồn quyết định **ứng dụng có khả năng làm gì**; cấu hình được cấp khi chạy quyết định **ứng dụng kết nối, lắng nghe và vận hành như thế nào**. Tách hai phần này giúp triển khai lặp lại được, truy vết được artifact đã kiểm thử và giảm rủi ro khi đưa cùng một phiên bản từ dev tới production.
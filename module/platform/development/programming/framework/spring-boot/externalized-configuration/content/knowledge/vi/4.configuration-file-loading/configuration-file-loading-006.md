# Quy tắc đường dẫn tệp, thư mục và dấu gạch chéo cuối

## 1. Bài toán: Spring Boot nhận một đường dẫn là file hay thư mục?

Spring Boot cho phép tách cấu hình khỏi mã nguồn và JAR. Khi khởi động, ứng dụng tìm các tệp **application.properties**, **application.yml**, các biến thể theo profile và những tệp được chỉ định bổ sung.

Một trong những lỗi cấu hình phổ biến nhất là viết đường dẫn tới **thư mục** nhưng quên dấu gạch chéo **/** cuối. Với hệ thống **Config Data** của Spring Boot 3.3, cú pháp biểu diễn nơi tìm file ảnh hưởng trực tiếp đến cách Spring Boot xử lý:

- **Directory location**: một thư mục để Spring Boot tự ghép **tên file cấu hình** cần tìm vào.
- **File location**: một tệp cụ thể với tên và phần mở rộng rõ ràng; Spring Boot nạp chính file đó.
- **Classpath location**: tài nguyên trên classpath của ứng dụng, thường có trong JAR sau khi build.
- **Filesystem location**: file/thư mục thực trên hệ thống tệp của tiến trình đang chạy.

Bài này tập trung vào **spring.config.location**, **spring.config.additional-location**, đường dẫn tương đối/tuyệt đối, ký tự **/** cuối, wildcard, profile và các trường hợp dễ nhầm với **spring.config.import**.

## 2. Các vị trí tìm cấu hình mặc định

Spring Boot mặc định dùng basename **application**, nên các tên thường gặp là:

~~~text
application.properties
application.yml
application.yaml
application-dev.properties
application-prod.yml
~~~

Spring Boot 3.3 tìm Config Data trong các nhóm vị trí mặc định sau:

| Vị trí | Ý nghĩa |
| --- | --- |
| **classpath:/** | Thư mục gốc classpath |
| **classpath:/config/** | Thư mục config trên classpath |
| **file:./** | Thư mục làm việc hiện tại |
| **file:./config/** | Thư mục config nằm dưới thư mục làm việc |
| **file:./config/*/** | Các thư mục con trực tiếp của thư mục config bên ngoài JAR |

Các giá trị ở vị trí có độ ưu tiên cao hơn có thể ghi đè key trùng tên từ vị trí trước. File có tên theo profile, ví dụ **application-prod.yml**, được xét khi profile tương ứng hoạt động.

Ví dụ, sau khi build:

~~~text
myproject/
├── app.jar
├── config/
│   ├── application.yml
│   ├── application-prod.yml
│   └── mysql/
│       └── application.properties
└── logs/
~~~

Khi chạy trong **myproject/**, Spring Boot có thể thấy các tệp ngoài JAR ở **./config/** và **./config/mysql/** theo đường tìm kiếm mặc định.

**Điểm cần nhớ:** dấu **./** được tính từ *working directory của tiến trình Java*, không bắt buộc là thư mục chứa **app.jar**. Nếu cùng JAR được chạy từ thư mục khác, ý nghĩa của **file:./config/** cũng thay đổi.

## 3. Quy tắc nhận diện thư mục và dấu / cuối

Với các vị trí được khai báo trong **spring.config.location** hoặc **spring.config.additional-location**, nếu mục đích là **chỉ định một thư mục**, hãy **kết thúc bằng dấu /**. Spring Boot sẽ nối thêm những tên file sinh từ **spring.config.name** khi tìm.

| Chuỗi đường dẫn | Ý định và cách xử lý |
| --- | --- |
| **file:./settings/** | Thư mục ngoài JAR; tìm application.properties, application.yml, ... |
| **classpath:/settings/** | Thư mục trong classpath; tìm các file theo basename cấu hình |
| **file:/etc/myapp/** | Thư mục tuyệt đối trên hệ thống Unix |
| **file:./settings/runtime.properties** | File cụ thể; nạp runtime.properties trực tiếp |
| **classpath:/defaults/base.yml** | File cụ thể trên classpath |
| **file:./settings** | Thiếu dấu **/** cho ý định “đây là một thư mục” |
| **file:./settings/runtime.properties/** | Thêm dấu **/** sau tên file, sai với ý định trỏ tới file |

Vì vậy, hai câu sau **không đồng nghĩa**:

~~~text
--spring.config.additional-location=file:./external/
--spring.config.additional-location=file:./external
~~~

Ở lệnh đầu, **external/** được biểu diễn là thư mục. Ở lệnh sau, người viết chưa cung cấp dấu hiệu kết thúc **/** mà Spring Boot mong đợi đối với directory location; nơi nạp có thể bị hiểu sai và các file application bên trong không được tìm như mong muốn.

Quy tắc này không liên quan đến việc Windows Explorer thường hiển thị dấu **\\** hay Linux dùng dấu **/** để ngăn cách thư mục. Ở đây ta đang dùng cú pháp location kiểu URL/URI do Spring Boot định nghĩa, nên ví dụ dùng **/** cho rõ ràng và nhất quán.

## 4. Directory location: Spring Boot tự ghép tên file

Giả sử đang đứng tại thư mục **run/**:

~~~text
run/
├── app.jar
└── deploy-config/
    ├── application.properties
    ├── application-dev.properties
    └── application-prod.properties
~~~

Nội dung **deploy-config/application.properties**:

~~~properties
app.banner=external-default
server.port=8080
~~~

Nội dung **deploy-config/application-dev.properties**:

~~~properties
app.banner=external-development
server.port=8081
~~~

Nội dung **deploy-config/application-prod.properties**:

~~~properties
app.banner=external-production
server.port=8080
~~~

Khởi động:

~~~bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:./deploy-config/ \
  --spring.profiles.active=dev
~~~

Spring Boot biết **file:./deploy-config/** là một thư mục và dùng tên mặc định **application** để tìm các file phù hợp. Với profile **dev**, hai file liên quan là:

~~~text
./deploy-config/application.properties
./deploy-config/application-dev.properties
~~~

Key **app.banner** có thể nhận **external-development** từ phiên bản theo profile.

Đổi thành:

~~~bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:./deploy-config/ \
  --spring.profiles.active=prod
~~~

Spring Boot xét **application-prod.properties** và có thể nhận **external-production**. Cả hai lượt sử dụng **cùng một JAR**.

Nếu tên file mặc định không phải **application**, ví dụ muốn dùng **orders.yml**, hãy cấp **spring.config.name=orders** từ lúc khởi động:

~~~bash
java -jar app.jar \
  --spring.config.name=orders \
  --spring.config.additional-location=optional:file:./deploy-config/
~~~

Khi đó directory location được tìm theo basename **orders** thay vì **application**. Tham số **spring.config.name** không phải một tên thư mục.

## 5. File location: Spring Boot nạp đúng tệp đã nêu

Một ứng dụng có thể nhận cấu hình từ file không mang tên **application**:

~~~text
run/
├── app.jar
└── deploy-config/
    ├── runtime.properties
    └── runtime-prod.properties
~~~

**runtime.properties**:

~~~properties
app.banner=runtime-default
~~~

**runtime-prod.properties**:

~~~properties
app.banner=runtime-production
~~~

Lệnh:

~~~bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:./deploy-config/runtime.properties \
  --spring.profiles.active=prod
~~~

Đây là **file location**, nên Spring Boot nạp **runtime.properties** theo tên cụ thể. Các biến thể profile thích hợp của file location cũng được xét; với profile **prod**, file **runtime-prod.properties** có thể được nạp.

So sánh rõ:

~~~text
file:./deploy-config/
  -> tìm các file theo spring.config.name trong thư mục

file:./deploy-config/runtime.properties
  -> nạp file runtime.properties được nêu trực tiếp
~~~

Nếu chỉ định file **runtime.properties**, thay đổi **spring.config.name=orders** không đổi tên chính file đã chỉ rõ ấy.

**Không thêm dấu /** sau **runtime.properties**. Phần mở rộng **.properties**, **.yml** hoặc **.yaml** giúp bộ nạp nhận dạng định dạng của file thường gặp.

Trong cùng một vị trí, khi đồng thời có các file **application.properties** và **application.yml** cùng basename, Spring Boot ưu tiên **.properties** theo quy tắc tài liệu. Để tránh sự nhập nhằng, tốt nhất thống nhất một định dạng cấu hình cho mỗi ứng dụng.

## 6. Phân biệt classpath: với file:

### 6.1. classpath: dành cho tài nguyên ứng dụng

Giả sử mã nguồn có:

~~~text
src/main/resources/
├── application.yml
└── defaults/
    ├── application.yml
    └── base.properties
~~~

Sau khi build, các tài nguyên này thường được đóng gói và có thể truy cập trên classpath:

~~~text
classpath:/application.yml
classpath:/defaults/
classpath:/defaults/base.properties
~~~

Nếu muốn Spring Boot tìm file theo tên mặc định trong **defaults/**:

~~~bash
java -jar app.jar \
  --spring.config.additional-location=classpath:/defaults/
~~~

Nếu muốn nạp một file cụ thể trong thư mục:

~~~bash
java -jar app.jar \
  --spring.config.additional-location=classpath:/defaults/base.properties
~~~

**classpath:** không có nghĩa “thư mục cùng cấp với JAR”. Sửa một file ở **src/main/resources** sau khi build không làm thay đổi bản tài nguyên đã đóng gói trong JAR trước đó.

### 6.2. file: dành cho hệ thống tệp hiện hành

Một số ví dụ:

~~~text
file:./config/                    thư mục tương đối
file:./config/application.yml     file tương đối
file:/etc/orders/                 thư mục tuyệt đối trên Unix
file:/etc/orders/application.yml  file tuyệt đối trên Unix
file:C:/apps/orders/config/       ví dụ cú pháp URI cho thư mục trên ổ C
~~~

Một thư mục ngoài JAR có thể do người vận hành tạo, do hệ thống triển khai quản lý, hoặc được mount vào container. Ứng dụng phải có quyền đọc các vị trí ấy.

Ví dụ:

~~~bash
cd /srv/orders
java -jar /opt/apps/orders.jar \
  --spring.config.additional-location=file:./config/
~~~

Trong ví dụ này **./config/** là **/srv/orders/config/**, không phải **/opt/apps/config/**, vì working directory là **/srv/orders**.

Docker **WORKDIR**, thư mục làm việc của IDE và thuộc tính **WorkingDirectory** trong service manager đều có thể quyết định đường dẫn tương đối được giải quyết từ đâu.

## 7. spring.config.location và spring.config.additional-location khác nhau thế nào?

### 7.1. spring.config.location thay thế danh sách mặc định

~~~bash
java -jar app.jar \
  --spring.config.location=optional:file:./site-config/
~~~

Spring Boot sử dụng những location được nêu trong **spring.config.location** để thay thế các vị trí tìm kiếm mặc định. Nếu ứng dụng phụ thuộc vào một file **application.yml** đóng gói trong JAR mà không được bao gồm trong danh sách mới, các giá trị chỉ có ở đó có thể không còn được nạp.

Dùng cơ chế này khi bạn có chủ đích kiểm soát toàn bộ tập vị trí cần tìm.

### 7.2. spring.config.additional-location bổ sung

~~~bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:./site-config/
~~~

Spring Boot vẫn sử dụng những vị trí mặc định, rồi nạp thêm vị trí được cung cấp. Giá trị ở các vị trí bổ sung có thể ghi đè giá trị cùng key trong cấu hình mặc định.

Đây thường là lựa chọn phù hợp khi JAR chứa cấu hình mặc định chung, còn môi trường triển khai chỉ thêm một số giá trị riêng.

### 7.3. Ba thuộc tính cần được cung cấp đủ sớm

Các thuộc tính **spring.config.name**, **spring.config.location** và **spring.config.additional-location** được dùng rất sớm để quyết định những tệp nào cần nạp. Hãy cấp chúng bằng một nguồn sẵn có ngay lúc khởi động, như:

~~~bash
java -jar app.jar --spring.config.name=orders
~~~

Hoặc bằng biến môi trường:

~~~bash
SPRING_CONFIG_ADDITIONAL_LOCATION="optional:file:./site-config/" \
  java -jar app.jar
~~~

Hoặc Java system property:

~~~bash
java -Dspring.config.additional-location=optional:file:./site-config/ \
  -jar app.jar
~~~

Không đặt **spring.config.location** trong một file đang cần chính thuộc tính ấy để được phát hiện rồi mong hệ thống quay lại tìm từ đầu.

## 8. File nằm đâu khi sử dụng đường dẫn tương đối?

Nhìn vào hai cấu trúc giả định:

~~~text
/opt/myapp/app.jar
/srv/run/config/application.properties
~~~

Nếu người vận hành khởi động như sau:

~~~bash
cd /srv/run
java -jar /opt/myapp/app.jar \
  --spring.config.additional-location=file:./config/
~~~

đường dẫn **file:./config/** trỏ tới **/srv/run/config/**. Spring Boot không tự chuyển sang vị trí bên cạnh JAR.

Vì thế:

- Trên máy phát triển, đường dẫn **./config/** thường phụ thuộc IDE hoặc terminal đang chạy từ đâu.
- Trong container, đường dẫn **./config/** thường phụ thuộc **WORKDIR** và cấu hình runtime.
- Với service, đường dẫn có thể phụ thuộc tùy chọn working directory của trình quản lý service.
- Nếu vị trí phải cố định giữa các lần chạy, sử dụng một đường dẫn tuyệt đối có chủ đích, ví dụ **file:/etc/myapp/**.

Một đường dẫn tuyệt đối còn phải có ý nghĩa **bên trong môi trường chạy**. Đường dẫn trên máy host không tự xuất hiện trong container nếu chưa được mount.

## 9. Nhiều vị trí: dấu phẩy và dấu chấm phẩy

Bạn có thể khai báo nhiều location:

~~~bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:./base/,optional:file:./overrides/
~~~

Cả hai đều là thư mục vì có **/** cuối. Khi xử lý lần lượt các vị trí, giá trị ở vị trí về sau có thể ghi đè các key trùng tên của vị trí trước.

Spring Boot còn cho phép **location groups**: những vị trí thuộc cùng mức ưu tiên được ngăn cách bằng dấu **;**.

~~~text
classpath:/cfg/,classpath:/ext/
classpath:/cfg/;classpath:/ext/
~~~

Hai cách viết có thể cho kết quả khác nhau khi sử dụng **nhiều profile** như **prod,live**. Dấu phẩy thể hiện các vị trí/nhóm vị trí được xử lý theo thứ tự; dấu chấm phẩy gom các vị trí cùng một nhóm để áp dụng thứ tự profile ở cùng mức.

Ví dụ minh họa theo tài liệu Spring Boot:

~~~text
/cfg/
  application-live.properties

/ext/
  application-prod.properties
  application-live.properties
~~~

Với **classpath:/cfg/,classpath:/ext/**, các file trong **cfg/** được xử lý trước các file thuộc **ext/**. Với **classpath:/cfg/;classpath:/ext/**, các file theo profile ở hai thư mục được xét ở cùng mức, nên thứ tự override có thể khác.

Trong shell, dấu **;** có thể là ký tự đặc biệt. Nếu dùng group, đặt nguyên tham số trong dấu ngoặc kép:

~~~bash
java -jar app.jar \
  "--spring.config.location=classpath:/cfg/;classpath:/ext/"
~~~

Đối với một location đơn giản, không cần tạo nhóm phức tạp.

## 10. Wildcard: khi config nằm ở nhiều thư mục con

Spring Boot hỗ trợ một ký tự **\*** trong wildcard location. Ví dụ:

~~~text
workspace/
└── config/
    ├── mysql/
    │   └── application.properties
    ├── redis/
    │   └── application.properties
    └── queue/
        └── application.properties
~~~

Đường dẫn:

~~~text
file:./config/*/
~~~

giúp tìm file cấu hình ở những **thư mục con trực tiếp** của **./config/**. Đây cũng là một vị trí trong danh sách tìm kiếm mặc định của Spring Boot.

Các giới hạn cần nhớ:

1. Mỗi wildcard location chỉ chứa **một dấu sao**.
2. Với wildcard thư mục, đường dẫn phải kết thúc bằng ***/**.
3. Với wildcard file, dùng dạng ***/<tên-file>**, chẳng hạn **file:./config/*/application.properties**.
4. Wildcard áp dụng với **các vị trí bên ngoài**, không áp dụng cho **classpath:**.
5. Các đường dẫn được mở rộng từ wildcard được sắp xếp theo thứ tự chữ cái dựa trên đường dẫn tuyệt đối.

Wildcard **không phải lệnh tìm đệ quy vô hạn**. **config/*/** tập trung vào một cấp thư mục con trực tiếp, không tự quét mọi cấp lồng nhau.

## 11. Khi đường dẫn không tồn tại: optional:

Nếu một location được chỉ định mà không tồn tại, Spring Boot có thể ném **ConfigDataLocationNotFoundException** và từ chối khởi động.

Ví dụ:

~~~bash
java -jar app.jar \
  --spring.config.additional-location=file:./must-exist/
~~~

Nếu thư mục **must-exist/** không có, ứng dụng có thể dừng vì thiếu location bắt buộc.

Nếu việc thiếu thư mục là chấp nhận được ở một số môi trường, thêm **optional:** ở đầu:

~~~bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:./local-overrides/
~~~

**optional:** chỉ nói rằng thiếu location này thì có thể bỏ qua. Nó không sửa nội dung file sai cú pháp, không tạo thư mục và không đảm bảo một property bắt buộc có giá trị.

Các mẫu đúng:

~~~text
optional:file:./config/
optional:file:./config/custom.properties
optional:classpath:/defaults/
~~~

Spring Boot còn hỗ trợ **spring.config.on-not-found=ignore** để bỏ qua các lỗi không tìm thấy location ở phạm vi rộng hơn. Với một vị trí cụ thể được phép thiếu, **optional:** diễn đạt mục đích rõ ràng hơn.

## 12. spring.config.import và quy tắc đường dẫn riêng

**spring.config.import** được khai báo trong một tài liệu cấu hình đã nạp để kéo thêm dữ liệu cấu hình.

Ví dụ **application.properties**:

~~~properties
spring.config.import=optional:file:./config/extra.properties
~~~

Spring Boot sẽ tìm **extra.properties** ở đường dẫn được nêu. Các giá trị import có thể ghi đè giá trị cùng key trong tài liệu chứa câu lệnh import.

Có hai kiểu đường dẫn import:

- **Fixed location**: bắt đầu bằng **/** hoặc một prefix như **file:**, **classpath:**. Nó giữ ý nghĩa vị trí đã chỉ rõ.
- **Import-relative location**: không có các prefix trên; đường dẫn được giải quyết tương đối với **file đã khai báo import**.

Ví dụ:

~~~text
/demo/
├── application.properties
└── core/
    ├── core.properties
    └── extra/
        └── extra.properties
~~~

Trong **/demo/application.properties**:

~~~properties
spring.config.import=optional:core/core.properties
~~~

Trong **/demo/core/core.properties**:

~~~properties
spring.config.import=optional:extra/extra.properties
~~~

Import thứ hai trỏ tới **/demo/core/extra/extra.properties**, bởi nó được tính từ nơi chứa **core.properties**.

Ngược lại, nếu viết:

~~~properties
spring.config.import=optional:file:./extra/extra.properties
~~~

thì prefix **file:** khiến đường dẫn trở thành fixed location: **./extra/** được giải quyết theo working directory, không theo thư mục của **core.properties**. **optional:** không làm thay đổi quy tắc fixed/import-relative này.

### Configuration tree không giống thư mục application.*

Một số nền tảng mount nhiều file nhỏ, mỗi file chứa giá trị của một property:

~~~text
/etc/config/
└── db/
    ├── username
    └── password
~~~

Nếu muốn biến tên file thành key như **db.username** và **db.password**, Spring Boot cung cấp cơ chế:

~~~properties
spring.config.import=optional:configtree:/etc/config/
~~~

Đó là **configtree:**, có quy tắc riêng. Chỉ khai báo một directory location **file:/etc/config/** không đồng nghĩa Spring Boot sẽ đọc mọi file nhỏ trong cây và biến tên của chúng thành property.

## 13. Thực hành kiểm chứng với một ứng dụng tối thiểu

Giả sử dự án Spring Boot 3.3 có **spring-boot-starter-web**. Tạo controller dưới đây:

~~~java
package com.example.config;

import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ConfigController {
    private final Environment env;

    public ConfigController(Environment env) {
        this.env = env;
    }

    @GetMapping("/config-banner")
    public String banner() {
        return env.getProperty("app.banner", "missing");
    }
}
~~~

Trong **src/main/resources/application.properties**:

~~~properties
app.banner=from-jar
server.port=8080
~~~

Build một JAR bằng Gradle wrapper:

~~~bash
./gradlew bootJar
~~~

Để thử các lệnh dưới, đặt tên JAR thực tế là **app.jar** hoặc đổi **app.jar** trong các lệnh thành đúng tên file build ra. Chuẩn bị thư mục:

~~~text
run/
├── app.jar
└── runtime/
    ├── application.properties
    ├── application-prod.properties
    └── custom.properties
~~~

**runtime/application.properties**:

~~~properties
app.banner=from-directory
~~~

**runtime/application-prod.properties**:

~~~properties
app.banner=from-prod
~~~

**runtime/custom.properties**:

~~~properties
app.banner=from-explicit-file
~~~

Đứng tại thư mục **run/**, thử lần lượt các trường hợp sau.

**A. Chỉ dùng cấu hình đóng gói:**

~~~bash
java -jar app.jar
curl http://localhost:8080/config-banner
~~~

Kết quả minh họa: **from-jar**.

**B. Chỉ định đúng directory location:**

~~~bash
java -jar app.jar \
  --spring.config.additional-location=file:./runtime/
~~~

Gọi API và nhận **from-directory**.

**C. Directory location và profile prod:**

~~~bash
java -jar app.jar \
  --spring.config.additional-location=file:./runtime/ \
  --spring.profiles.active=prod
~~~

Gọi API và nhận **from-prod**.

**D. Chỉ định file rõ tên:**

~~~bash
java -jar app.jar \
  --spring.config.additional-location=file:./runtime/custom.properties
~~~

Gọi API và nhận **from-explicit-file**.

**E. Bỏ dấu /** ở cuối đường dẫn thư mục:

~~~bash
java -jar app.jar \
  --spring.config.additional-location=file:./runtime
~~~

Quan sát việc đường dẫn không còn được xử lý như directory location mong muốn; sau đó sửa thành **file:./runtime/** để nạp các file **application**.

**F. Kiểm tra optional location:**

~~~bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:./not-present/
~~~

Khi thư mục **not-present/** không tồn tại, location tùy chọn được bỏ qua; ứng dụng vẫn có thể sử dụng các nguồn cấu hình khác, chẳng hạn **from-jar**.

Dừng tiến trình trước khi bắt đầu lượt tiếp theo vì các ví dụ cùng sử dụng cổng **8080**.

## 14. Khi file không được nạp, kiểm tra gì?

Nếu giá trị khác dự kiến, hãy kiểm tra những điều sau theo thứ tự:

1. **Bạn đang muốn chỉ tệp hay thư mục?** Một thư mục phải kết thúc bằng **/**.
2. **Bạn đã dùng đúng prefix?** Tài nguyên trong JAR dùng **classpath:**; file ngoài dùng **file:**.
3. **Working directory hiện tại là gì?** Đường dẫn **./** không tự động tính từ nơi chứa JAR.
4. **Đúng tên file chưa?** Directory location tìm theo **spring.config.name**, mặc định là **application**.
5. **Có profile phù hợp không?** File **application-prod.yml** chỉ được xét khi profile **prod** hoạt động theo cơ chế nạp.
6. **Bạn đã vô tình thay thế vị trí mặc định?** **spring.config.location** thay thế, còn **spring.config.additional-location** bổ sung.
7. **Location có tồn tại không?** Prefix **optional:** có thể khiến một vị trí vắng mặt được bỏ qua mà không gây lỗi.
8. **Wildcard có hợp lệ không?** Chỉ một **\***, đúng dạng ***/**, và không ở classpath.
9. **Có file ở vị trí ưu tiên cao hơn ghi đè không?** Nạp được không có nghĩa giá trị cuối cùng đến từ file bạn đang nhìn.
10. **Quyền truy cập và cú pháp file có đúng không?** Một đường dẫn hợp lệ vẫn có thể trỏ tới tệp không đọc được hoặc dữ liệu cấu hình bị lỗi.

Để xem log chi tiết quá trình nạp Config Data trong môi trường phát triển, có thể bật:

~~~bash
java -jar app.jar \
  --logging.level.org.springframework.boot.context.config=TRACE
~~~

Không in nội dung secret hoặc thông tin nhạy cảm khi điều tra vấn đề. Với Spring Boot Actuator, chỉ mở endpoint môi trường/cấu hình cho người được phép và có cơ chế bảo vệ phù hợp.

## 15. Kết luận kỹ thuật

- **file:./config/** là một thư mục; **file:./config/custom.yml** là một file cụ thể.
- **Dấu /** cuối là tín hiệu quan trọng đối với đường dẫn **thư mục** trong Config Data.
- **Directory location** được ghép thêm basename cấu hình và biến thể theo profile; **file location** nạp tên file được chỉ định và cũng có thể xét biến thể theo profile.
- **classpath:** và **file:** tham chiếu hai kiểu nguồn khác nhau.
- **./** dựa trên working directory của tiến trình, không mặc định dựa trên vị trí JAR.
- **spring.config.location** thay thế các vị trí mặc định, còn **spring.config.additional-location** giữ các vị trí mặc định rồi bổ sung vị trí mới.
- **optional:** cho phép thiếu location, nhưng không khắc phục lỗi định dạng hoặc lỗi giá trị cấu hình.
- Wildcard **file:./config/*/** cho phép quét các thư mục con trực tiếp ở bên ngoài classpath.
- **spring.config.import** có quy tắc fixed và import-relative riêng, và **configtree:** là một cơ chế khác để đọc cấu hình dạng cây tệp.

Biểu diễn đúng đường dẫn giúp Spring Boot nạp cấu hình chính xác, dễ dự đoán và dễ triển khai cùng một JAR ở nhiều môi trường.

## Tài liệu tham khảo

- Spring Boot 3.3 — Externalized Configuration, *Config File Locations*, *Optional Locations*, *Wildcard Locations*, *Profile Specific Files* và *Importing Additional Data*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 — Profiles: https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html

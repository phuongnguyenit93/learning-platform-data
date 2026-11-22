# spring.config.name, location và additional-location

Bài học thuộc chương **Nạp cấu hình** của module **SPRING_CLOUD_CORE**. Ba thuộc tính `spring.config.name`, `spring.config.location` và `spring.config.additional-location` quyết định Spring Boot tìm tệp cấu hình nào, ở những vị trí nào và cách các vị trí đó tương tác với cấu hình mặc định.

Đây là các thuộc tính quan trọng khi triển khai cùng một ứng dụng lên máy cá nhân, máy chủ, container hoặc nhiều môi trường khác nhau. Chúng thường được truyền qua command line, system property hoặc environment variable ngay lúc khởi động. Nếu hiểu sai sự khác nhau giữa **thay thế** và **bổ sung** vị trí tìm kiếm, ứng dụng có thể bỏ qua cấu hình được đóng gói trong JAR hoặc nạp nhầm tệp theo working directory.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Giải thích Spring Boot Config Data tìm và nạp cấu hình trong giai đoạn khởi động như thế nào.
2. Dùng `spring.config.name` để đổi tên cơ sở của các tệp cấu hình được tìm kiếm.
3. Dùng `spring.config.location` để chỉ định các vị trí cấu hình và hiểu rằng thuộc tính này thay thế các vị trí mặc định.
4. Dùng `spring.config.additional-location` để thêm vị trí bên ngoài mà vẫn giữ các vị trí mặc định.
5. Phân biệt đường dẫn thư mục và đường dẫn tệp, hiểu ý nghĩa dấu `/`, tiền tố `optional:` và thứ tự ưu tiên.
6. Kết hợp cấu hình tên tệp, vị trí, profile và biến môi trường khi chạy ứng dụng từ Maven, Gradle hoặc executable JAR.
7. Phân biệt các thuộc tính định vị file với `spring.config.import`, đặc biệt khi tích hợp Spring Cloud Config Server.
8. Thiết kế phép thử để chứng minh ứng dụng đã nạp đúng nguồn cấu hình.

## 2. Spring Boot nạp cấu hình ở thời điểm nào?

Trong quá trình khởi động, Spring Boot cần biết các nguồn cấu hình trước khi tạo và cấu hình nhiều bean trong `ApplicationContext`. Cơ chế Config Data đọc các vị trí cấu hình, profile và các tài nguyên được import để tạo các property source cho môi trường ứng dụng.

~~~mermaid
flowchart TD
    START["Khởi chạy JVM / SpringApplication"] --> EARLY["Đọc thuộc tính định vị cấu hình sớm"]
    EARLY --> NAME["Xác định spring.config.name"]
    EARLY --> LOC["Xác định location / additional-location"]
    NAME --> SEARCH["Tìm tài nguyên cấu hình"]
    LOC --> SEARCH
    SEARCH --> PROFILE["Xét profile đang hoạt động"]
    PROFILE --> LOAD["Nạp tài liệu cấu hình và import"]
    LOAD --> ENV["Environment chứa các property source"]
    ENV --> CTX["Tạo / cấu hình ApplicationContext và beans"]
    CTX --> RUN["Ứng dụng sẵn sàng chạy"]
~~~

Ba thuộc tính trong bài ảnh hưởng đến **việc tìm tài nguyên cấu hình**. Chúng cần được biết đủ sớm để Spring Boot xác định nơi cần đọc. Vì vậy, không thể đặt `spring.config.location` trong chính tệp `application.yml` rồi kỳ vọng Spring Boot dùng giá trị vừa đọc để tìm tệp đó: tệp phải được tìm thấy trước thì nội dung bên trong mới có thể được đọc.

Các nguồn phù hợp để truyền những thuộc tính này gồm:

- Tham số dòng lệnh của ứng dụng, đặt sau tên JAR.
- System property của JVM, đặt trước `-jar`.
- Environment variable của process.
- Cơ chế khởi chạy hoặc nền tảng triển khai có khả năng cung cấp các nguồn trên.

Ví dụ:

~~~bash
java -jar app.jar --spring.config.name=orders
~~~

Hoặc:

~~~bash
java -Dspring.config.name=orders -jar app.jar
~~~

Cả hai cách đều cung cấp thuộc tính trước khi Spring Boot nạp các tệp cấu hình. Khi cần xác định giá trị nào thắng nếu nhiều nguồn cùng khai báo, phải xét quy tắc precedence của Spring Boot và nguồn cấu hình thực tế.

## 3. Phân biệt ba thuộc tính

| Thuộc tính | Câu hỏi nó trả lời | Hành vi chính |
| --- | --- | --- |
| `spring.config.name` | Tìm các tệp theo tên cơ sở nào? | Đổi tên mặc định `application` thành tên khác, ví dụ `orders`. |
| `spring.config.location` | Tìm cấu hình ở đâu? | Chỉ định các vị trí cấu hình thay thế tập vị trí mặc định. |
| `spring.config.additional-location` | Cần tìm thêm ở đâu? | Bổ sung vị trí, vẫn giữ tập vị trí mặc định. |

Hãy nhớ sự khác biệt quan trọng:

- `location` = **thay thế** các vị trí mặc định.
- `additional-location` = **bổ sung** vị trí vào các vị trí mặc định.

Hai thuộc tính location đều có thể nhận nhiều vị trí. Các vị trí được xử lý theo thứ tự khai báo; cấu hình ở vị trí sau có thể ghi đè giá trị cùng khóa từ vị trí trước. Các quy tắc cụ thể còn chịu ảnh hưởng của profile và loại tài nguyên được nạp.

## 4. spring.config.name: đổi tên tệp cấu hình

### 4.1. Tên mặc định và tên tùy chỉnh

Theo mặc định, Spring Boot tìm cấu hình có tên cơ sở `application`, ví dụ:

~~~text
application.properties
application.yml
application.yaml
application-local.properties
application-local.yml
application-prod.yml
~~~

Khi đặt:

~~~bash
java -jar app.jar --spring.config.name=orders
~~~

Spring Boot dùng tên cơ sở `orders` khi tìm cấu hình trong các vị trí thư mục:

~~~text
orders.properties
orders.yml
orders.yaml
orders-local.properties
orders-local.yml
orders-prod.yml
~~~

Tên cơ sở là phần trước phần mở rộng. Thuộc tính này không đổi tên JAR, package Java, `spring.application.name` hay service ID trong registry.

**Không nhầm hai thuộc tính sau:**

| Thuộc tính | Mục đích |
| --- | --- |
| `spring.config.name` | Tên cơ sở của tệp cấu hình, ví dụ `orders.yml`. |
| `spring.application.name` | Tên logic của ứng dụng, thường dùng trong log, metrics, discovery hoặc cấu hình tích hợp. |

Một ứng dụng có thể có `spring.application.name=order-service` nhưng vẫn dùng `spring.config.name=orders`. Hai giá trị phục vụ hai mục đích khác nhau.

### 4.2. Khi nào nên đổi tên?

Đổi tên có ích khi:

- Một tiến trình cần một bộ cấu hình có tên riêng.
- Nhiều ứng dụng cùng dùng chung một thư mục cấu hình nhưng cần tách file.
- Muốn đặt tên dễ nhận biết theo vai trò, ví dụ `gateway.yml`, `worker.yml`, `scheduler.yml`.
- Có quy ước triển khai riêng giữa tên artifact và tên cấu hình.

Ví dụ thư mục:

~~~text
deployment/
└── config/
    ├── orders.yml
    ├── orders-prod.yml
    ├── billing.yml
    └── billing-prod.yml
~~~

Khởi chạy ứng dụng orders:

~~~bash
java -jar orders.jar --spring.config.name=orders --spring.config.additional-location=optional:file:./config/
~~~

Ứng dụng billing có thể dùng cùng thư mục nhưng chọn tên khác:

~~~bash
java -jar billing.jar --spring.config.name=billing --spring.config.additional-location=optional:file:./config/
~~~

Hai process không cần đổi tên artifact để chọn bộ cấu hình tương ứng.

### 4.3. Tên cấu hình không phải tên file tùy ý ở mọi vị trí

Khi chỉ định một **thư mục**, Spring Boot kết hợp thư mục đó với tên cơ sở và các profile đang hoạt động để tìm tài liệu cấu hình phù hợp.

Khi chỉ định một **tệp cụ thể**, tệp đó được nạp trực tiếp theo đường dẫn đã chỉ định. Nếu muốn quản lý rõ ràng một bộ file cơ sở và các file profile theo cùng tên, ưu tiên chỉ định thư mục rồi kết hợp `spring.config.name` với profile đang hoạt động.

## 5. spring.config.location: chỉ định vị trí thay thế

### 5.1. Thuộc tính này làm gì?

`spring.config.location` chỉ định các vị trí cấu hình cần dùng và **thay thế tập vị trí tìm kiếm mặc định**. Điều này có nghĩa cấu hình mặc định trong classpath hoặc các vị trí mặc định khác có thể không còn được tìm kiếm như trước.

Ví dụ:

~~~bash
java -jar app.jar --spring.config.location=file:./runtime-config/
~~~

Vì giá trị kết thúc bằng `/`, đây là vị trí thư mục. Spring Boot tìm các tệp có tên cơ sở tương ứng, ví dụ `application.yml` nếu không đổi `spring.config.name`.

Nếu muốn dùng tên `orders`:

~~~bash
java -jar app.jar --spring.config.name=orders --spring.config.location=file:./runtime-config/
~~~

Trong thư mục `runtime-config`, tệp phù hợp là `orders.yml`, cùng các biến thể profile tương ứng nếu profile được kích hoạt.

### 5.2. Ví dụ thay thế hoàn toàn vị trí mặc định

Giả sử JAR có sẵn:

~~~text
app.jar
  └── BOOT-INF/classes/
      └── application.yml
~~~

Ngoài ra có cấu hình triển khai:

~~~text
runtime-config/
└── application.yml
~~~

Khi chạy:

~~~bash
java -jar app.jar --spring.config.location=file:./runtime-config/
~~~

Spring Boot tìm ở vị trí được chỉ định thay vì tập vị trí mặc định. Không nên mong đợi `application.yml` đóng gói trong JAR tự động được hợp nhất như trước. Nếu muốn giữ file mặc định trong JAR và ghi đè một số giá trị bằng file ngoài, hãy cân nhắc `spring.config.additional-location`.

### 5.3. Nhiều vị trí

Có thể chỉ định nhiều location, phân tách bằng dấu phẩy:

~~~bash
java -jar app.jar --spring.config.location=file:./base-config/,file:./environment-config/
~~~

Các vị trí được xử lý theo thứ tự khai báo. Nếu cùng một khóa xuất hiện ở cả hai nơi, giá trị từ vị trí sau có thể ghi đè giá trị từ vị trí trước.

Ví dụ:

`base-config/application.yml`:

~~~yaml
app:
  region: ap-southeast
  feature-mode: standard
~~~

`environment-config/application.yml`:

~~~yaml
app:
  feature-mode: restricted
~~~

Kết quả hợp nhất theo nguyên tắc property source: `app.region` vẫn có giá trị `ap-southeast`, còn `app.feature-mode` nhận giá trị `restricted` từ vị trí sau. Đây là cách tư duy về override; nếu cùng lúc có profile, import hoặc các nguồn cấu hình khác, cần xét thêm thứ tự precedence tương ứng.

### 5.4. Đường dẫn thư mục và đường dẫn file

Hai dạng location không giống nhau:

| Dạng | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Thư mục | `file:./config/` | Spring Boot tìm tên file cấu hình trong thư mục dựa trên `spring.config.name` và profile. |
| Tệp cụ thể | `file:./config/orders-prod.yml` | Nạp trực tiếp tài nguyên tệp được chỉ định. |
| Thư mục classpath | `classpath:/config/` | Tìm tài nguyên trong thư mục classpath. |
| Tệp classpath | `classpath:/tenant/orders.yml` | Nạp tài nguyên cụ thể trong classpath. |
| Thư mục tuyệt đối | `file:/etc/orders/config/` | Tìm cấu hình trong thư mục ngoài theo đường dẫn tuyệt đối. |

Khi chỉ định **thư mục**, hãy kết thúc đường dẫn bằng dấu `/`. Đây là dấu hiệu để Config Data xử lý location như một thư mục và kết hợp nó với tên cấu hình. Đường dẫn tương đối như `file:./config/` được phân giải theo **working directory của process**, không mặc nhiên theo thư mục chứa file JAR.

## 6. spring.config.additional-location: bổ sung cấu hình bên ngoài

### 6.1. Khi nào dùng?

Đây thường là lựa chọn phù hợp khi muốn:

- Giữ cấu hình mặc định được đóng gói trong ứng dụng.
- Thêm cấu hình riêng của máy chủ hoặc môi trường.
- Cho phép cấu hình bên ngoài ghi đè một phần giá trị mặc định.
- Dùng cùng một artifact cho nhiều môi trường mà không build lại.

Ví dụ:

~~~bash
java -jar app.jar --spring.config.additional-location=optional:file:./config/
~~~

Spring Boot tiếp tục tìm ở các vị trí mặc định, đồng thời tìm thêm trong `./config/`. Vị trí bổ sung được xử lý với mức ưu tiên cao hơn vị trí mặc định tương ứng, nên có thể ghi đè giá trị đã đóng gói.

### 6.2. Minh họa hợp nhất cấu hình

Trong JAR có `application.yml`:

~~~yaml
spring:
  application:
    name: order-service

server:
  port: 8080

app:
  region: ap-southeast
  feature-mode: standard
~~~

Bên ngoài JAR, file `./config/application.yml`:

~~~yaml
server:
  port: 8081

app:
  feature-mode: restricted
~~~

Khi chạy với:

~~~bash
java -jar app.jar --spring.config.additional-location=optional:file:./config/
~~~

Kết quả mong đợi theo các property source:

| Thuộc tính | Giá trị hiệu lực | Nguồn |
| --- | --- | --- |
| `spring.application.name` | `order-service` | File mặc định trong JAR |
| `server.port` | `8081` | File bên ngoài |
| `app.region` | `ap-southeast` | File mặc định trong JAR |
| `app.feature-mode` | `restricted` | File bên ngoài |

Cấu hình bên ngoài không cần lặp lại mọi khóa. Nó chỉ cần khai báo những giá trị cần thay đổi. Đây là lợi ích quan trọng của cơ chế externalized configuration.

### 6.3. Nhiều additional locations

Ví dụ:

~~~bash
java -jar app.jar --spring.config.additional-location=optional:file:./site-config/,optional:file:/etc/orders/
~~~

Các location được xử lý theo thứ tự. Nếu cùng khóa xuất hiện ở nhiều vị trí, vị trí được xử lý sau có thể ghi đè vị trí trước. Hãy thống nhất thứ tự giữa các nhóm cấu hình để tránh một máy chạy ra kết quả khác chỉ vì danh sách location khác nhau.

## 7. Tiền tố optional: và xử lý vị trí không tồn tại

### 7.1. Vị trí bắt buộc

Nếu một location không có tiền tố `optional:`, Spring Boot có thể dừng khởi động khi không tìm thấy tài nguyên bắt buộc.

~~~bash
java -jar app.jar --spring.config.additional-location=file:/etc/orders/
~~~

Cách này phù hợp khi file ngoài là điều kiện bắt buộc để ứng dụng chạy an toàn, chẳng hạn cấu hình endpoint hoặc thông số môi trường mà thiếu nó phải fail fast.

### 7.2. Vị trí tùy chọn

Thêm `optional:` trước location:

~~~bash
java -jar app.jar --spring.config.additional-location=optional:file:./config/
~~~

Nếu thư mục không tồn tại, ứng dụng có thể tiếp tục mà không nạp tài nguyên từ vị trí đó. Điều này phù hợp với thư mục override chỉ có ở một số môi trường.

Dùng optional có trách nhiệm. Nếu một file chứa cấu hình thiết yếu, đánh dấu optional có thể khiến ứng dụng khởi động với giá trị mặc định ngoài dự kiến. Với cấu hình quan trọng, nên để thiếu file gây lỗi rõ ràng hoặc bổ sung validation để dừng khởi động khi giá trị bắt buộc không hợp lệ.

### 7.3. Optional không có nghĩa là mọi lỗi đều bị bỏ qua

`optional:` xử lý trường hợp location/tài nguyên không có theo cơ chế Config Data. Nó không phải cách che mọi lỗi cú pháp YAML, sai kiểu dữ liệu, lỗi phân tích nội dung hoặc lỗi khởi tạo bean do giá trị cấu hình không phù hợp. Khi ứng dụng vẫn dừng, hãy đọc exception gốc và xác định đó là lỗi không tìm thấy tài nguyên hay lỗi xử lý nội dung.

## 8. Kết hợp với profile

Profile cho phép dùng cấu hình riêng theo môi trường hoặc vai trò chạy. Ví dụ:

~~~text
config/
├── orders.yml
├── orders-local.yml
├── orders-staging.yml
└── orders-prod.yml
~~~

Kích hoạt profile:

~~~bash
java -jar app.jar --spring.config.name=orders --spring.config.additional-location=optional:file:./config/ --spring.profiles.active=prod
~~~

Spring Boot tìm cấu hình cơ sở `orders` và cấu hình profile tương ứng `orders-prod` trong các thư mục location. Tài liệu profile-specific được nạp để ghi đè giá trị cơ sở theo quy tắc Config Data.

### 8.1. Ví dụ

`orders.yml`:

~~~yaml
server:
  port: 8080

app:
  retry-limit: 2
  payment-mode: sandbox
~~~

`orders-prod.yml`:

~~~yaml
server:
  port: 8080

app:
  retry-limit: 4
  payment-mode: live
~~~

Khi profile `prod` hoạt động, các khóa có trong `orders-prod.yml` sẽ ghi đè giá trị tương ứng trong `orders.yml`. Khóa không khai báo trong file profile vẫn kế thừa giá trị cơ sở hoặc nguồn cấu hình khác theo precedence.

Không dùng profile làm nơi duy nhất để lưu secret. Thông tin nhạy cảm nên được cấp qua secret management phù hợp, và quyền đọc phải giới hạn.

### 8.2. Đổi tên file nhưng quên đổi profile

Một lỗi thường gặp là đổi `spring.config.name=orders` nhưng vẫn tạo `application-prod.yml`. Khi đó, file profile mong muốn có thể không được tìm thấy theo tên cơ sở mới.

Hãy kiểm tra đồng bộ:

- Tên cơ sở: `spring.config.name`.
- Tên file: `orders.yml`, `orders-prod.yml`.
- Profile đang active: `spring.profiles.active=prod`.
- Vị trí chứa file: `spring.config.location` hoặc `spring.config.additional-location`.

## 9. Truyền các thuộc tính từ môi trường khởi chạy

### 9.1. Command-line arguments

Các tham số sau tên JAR là application arguments:

~~~bash
java -jar app.jar \
  --spring.config.name=orders \
  --spring.config.additional-location=optional:file:./config/ \
  --spring.profiles.active=prod
~~~

Cách này dễ nhìn thấy trong lệnh triển khai và thuận tiện cho một lần chạy. Với shell Windows, cách xuống dòng và escape khác Bash; có thể viết toàn bộ lệnh trên một dòng.

### 9.2. JVM system properties

Các tùy chọn `-D...` đặt trước `-jar`:

~~~bash
java \
  -Dspring.config.name=orders \
  -Dspring.config.additional-location=optional:file:./config/ \
  -jar app.jar \
  --spring.profiles.active=prod
~~~

Đừng đặt `-Dspring.config.name=orders` sau tên JAR và mong JVM xử lý như system property; sau `-jar app.jar`, các đối số được chuyển cho ứng dụng.

### 9.3. Environment variables

Spring Boot hỗ trợ relaxed binding từ biến môi trường. Các tên tương ứng:

| Property | Environment variable |
| --- | --- |
| `spring.config.name` | `SPRING_CONFIG_NAME` |
| `spring.config.location` | `SPRING_CONFIG_LOCATION` |
| `spring.config.additional-location` | `SPRING_CONFIG_ADDITIONALLOCATION` |

Bash:

~~~bash
export SPRING_CONFIG_NAME=orders
export SPRING_CONFIG_ADDITIONALLOCATION=optional:file:./config/
export SPRING_PROFILES_ACTIVE=prod
java -jar app.jar
~~~

PowerShell:

~~~powershell
$env:SPRING_CONFIG_NAME = "orders"
$env:SPRING_CONFIG_ADDITIONALLOCATION = "optional:file:./config/"
$env:SPRING_PROFILES_ACTIVE = "prod"
java -jar app.jar
~~~

Biến môi trường thuộc về process được khởi chạy. Thay đổi biến trong terminal sau khi ứng dụng đã chạy không tự cập nhật môi trường của process đó. Muốn thay các thuộc tính định vị cấu hình, cần khởi chạy lại ứng dụng với môi trường mới.

### 9.4. Maven và Gradle

Với Maven:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.arguments="--spring.config.name=orders --spring.config.additional-location=optional:file:./config/ --spring.profiles.active=prod"
~~~

Với Gradle:

~~~bash
./gradlew bootRun --args='--spring.config.name=orders --spring.config.additional-location=optional:file:./config/ --spring.profiles.active=prod'
~~~

Cú pháp quote cần điều chỉnh theo shell đang dùng. Khi chạy executable JAR, truyền cùng các tham số sau tên JAR để xác minh cấu hình trong artifact thực tế.

## 10. Working directory và đường dẫn tương đối

Location dạng `file:./config/` phụ thuộc **working directory** của process. Nó không mặc nhiên trỏ đến nơi chứa JAR.

Ví dụ:

~~~text
/opt/orders/
├── app.jar
└── config/
    └── orders-prod.yml
~~~

Nếu process được khởi chạy với working directory là `/opt/orders`, location `file:./config/` trỏ đến `/opt/orders/config/`. Nếu service manager đặt working directory là `/`, cùng chuỗi location có thể trỏ đến `/config/` và không tìm thấy file mong đợi.

Để giảm bất ngờ:

- Dùng working directory được xác định rõ trong systemd, container hoặc service manager.
- Dùng đường dẫn tuyệt đối khi môi trường triển khai yêu cầu tính ổn định cao.
- Ghi rõ mount path trong container và trỏ location tới đường dẫn **bên trong container**.
- Không phụ thuộc vào thư mục hiện tại của người dùng đăng nhập.

Ví dụ location tuyệt đối:

~~~bash
java -jar /opt/orders/app.jar \
  --spring.config.additional-location=file:/etc/orders/
~~~

Với Windows, có thể dùng URI file tuyệt đối với dấu gạch chéo xuôi, ví dụ `file:///C:/apps/orders/config/`. Kiểm tra quyền truy cập của process chạy ứng dụng.

## 11. Phân biệt location với spring.config.import

Ba thuộc tính trong bài xác định **tên và vị trí tìm kiếm cấu hình**. `spring.config.import` là cơ chế khai báo một tài nguyên cấu hình khác cần được import trong quá trình Config Data loading.

Ví dụ với Spring Cloud Config Client trong các phiên bản hỗ trợ Config Data import:

~~~yaml
spring:
  application:
    name: orders
  config:
    import: "optional:configserver:http://config-server:8888"
~~~

Ứng dụng cần dependency Config Client phù hợp và Config Server có thể truy cập được. Cấu hình import này là cơ chế tích hợp Config Server; không thay thế vai trò của `spring.config.additional-location` khi cần thêm một thư mục file bên ngoài.

So sánh:

| Cơ chế | Dùng cho | Ví dụ |
| --- | --- | --- |
| `spring.config.name` | Đổi tên cơ sở của file được tìm. | `orders` |
| `spring.config.location` | Thay tập vị trí mặc định bằng các vị trí chỉ định. | `file:/etc/orders/` |
| `spring.config.additional-location` | Thêm vị trí file ngoài vào các vị trí mặc định. | `optional:file:./config/` |
| `spring.config.import` | Import tài nguyên Config Data khác, bao gồm tích hợp Config Server khi có resolver/dependency phù hợp. | `optional:configserver:http://config-server:8888` |

Không đặt `spring.config.import` vào cùng nhóm với việc đổi tên hoặc thay đường dẫn tìm kiếm. Khi tích hợp Spring Cloud Config, hãy theo hướng dẫn của release train Spring Cloud đang dùng; cách cấu hình cũ dựa trên bootstrap context có thể khác với cơ chế Config Data hiện đại.

## 12. Các mẫu triển khai thường gặp

### 12.1. Giữ mặc định và thêm override bên ngoài

Dùng khi JAR có cấu hình an toàn mặc định, môi trường chỉ override một số khóa:

~~~bash
java -jar app.jar --spring.config.additional-location=optional:file:/etc/orders/
~~~

Đây thường là lựa chọn dễ hiểu nhất cho cấu hình theo máy chủ vì file trong JAR vẫn được nạp.

### 12.2. Chỉ sử dụng bộ cấu hình do môi trường cung cấp

Dùng khi muốn location được chỉ định là nguồn file cấu hình chính:

~~~bash
java -jar app.jar --spring.config.name=orders --spring.config.location=file:/etc/orders/
~~~

Hãy chắc chắn thư mục tồn tại, có đủ file cần thiết và đã hiểu rằng tập vị trí mặc định bị thay thế. Nếu muốn giữ thêm một số vị trí mặc định, cân nhắc cấu hình bổ sung hoặc khai báo từng nguồn rõ ràng.

### 12.3. Dùng chung một thư mục cho nhiều ứng dụng

~~~text
/etc/platform/
├── orders/
│   ├── orders.yml
│   └── orders-prod.yml
├── inventory/
│   ├── inventory.yml
│   └── inventory-prod.yml
└── gateway/
    ├── gateway.yml
    └── gateway-prod.yml
~~~

Mỗi process chọn tên và thư mục tương ứng:

~~~bash
java -jar orders.jar --spring.config.name=orders --spring.config.location=file:/etc/platform/orders/ --spring.profiles.active=prod
java -jar inventory.jar --spring.config.name=inventory --spring.config.location=file:/etc/platform/inventory/ --spring.profiles.active=prod
~~~

Cách này giúp tách quyền và vòng đời cấu hình theo service. Cần bảo đảm mỗi process có quyền đọc đúng thư mục và không thể truy cập cấu hình của service khác nếu không cần thiết.

### 12.4. Container và volume cấu hình

Ví dụ minh họa:

~~~bash
docker run --rm \
  -p 8080:8080 \
  -v "$PWD/config:/run/config:ro" \
  -e SPRING_CONFIG_ADDITIONALLOCATION=optional:file:/run/config/ \
  orders-image:latest
~~~

Ứng dụng nhìn thấy volume tại `/run/config/` trong container. Location phải dùng đường dẫn trong container, không phải đường dẫn host. Mount read-only giúp process ứng dụng đọc cấu hình mà không tùy tiện sửa file trên host.

Không đưa secret trực tiếp vào command line nếu có nguy cơ bị lộ trong process list hoặc log triển khai. Dùng secret mount/environment mechanism được nền tảng hỗ trợ và quản lý quyền truy cập phù hợp.

## 13. Ma trận kiểm chứng cấu hình

Không nên chỉ nhìn log startup rồi kết luận đúng file đã được nạp. Hãy thiết kế một thử nghiệm nhỏ với các khóa có giá trị khác nhau để xác minh nguồn thắng.

| Ca thử | Thiết lập | Điều cần xác nhận |
| --- | --- | --- |
| L1 | Không truyền thuộc tính nào. | Ứng dụng dùng tên và vị trí mặc định theo phiên bản. |
| L2 | Chỉ đặt `spring.config.name=orders`. | File `orders.yml` được tìm thay cho tên mặc định. |
| L3 | Đặt `spring.config.location=file:./custom/`. | Vị trí mặc định bị thay thế; file trong custom được nạp. |
| L4 | Đặt `spring.config.additional-location=optional:file:./custom/`. | File mặc định vẫn được nạp và giá trị ngoài có thể override. |
| L5 | Đặt hai additional locations có cùng khóa. | Xác nhận location sau thắng theo thứ tự. |
| L6 | Kích hoạt profile `prod`. | File `<name>-prod.yml` được áp dụng. |
| L7 | Location bắt buộc không tồn tại. | Ứng dụng dừng với lỗi location không tìm thấy. |
| L8 | Location có tiền tố `optional:` không tồn tại. | Ứng dụng tiếp tục nếu không có lỗi cấu hình khác. |
| L9 | Chạy từ working directory khác. | Xác định đường dẫn tương đối đang được phân giải ở đâu. |
| L10 | Đặt cùng khóa trong file và command line. | Xác nhận nguồn có precedence cao hơn theo quy tắc Boot. |

### 13.1. Ví dụ kiểm chứng bằng khóa marker

Tạo cấu hình cơ sở:

`application.yml`:

~~~yaml
app:
  config-source: packaged
  retry-limit: 2
~~~

Tạo cấu hình ngoài:

`./config/application.yml`:

~~~yaml
app:
  config-source: external
~~~

Tạo endpoint lab chỉ trả về hai thuộc tính này, hoặc kiểm tra bằng test Spring Boot:

- Nếu dùng additional-location, mong đợi `config-source=external`.
- `retry-limit` vẫn là 2 do file ngoài không khai báo khóa này.
- Nếu dùng location thay thế và file ngoài không có `retry-limit`, không được giả định giá trị 2 từ file packaged vẫn tồn tại.

Không expose endpoint phản chiếu toàn bộ Environment trong production. Chỉ trả các giá trị thử nghiệm không nhạy cảm hoặc kiểm tra trong test/integration environment.

### 13.2. Tiêu chí PASS

Một lần kiểm chứng chỉ PASS khi:

1. Biết chính xác lệnh và working directory đã dùng.
2. Xác nhận process nhận đúng thuộc tính định vị cấu hình.
3. Có giá trị quan sát được cho khóa marker.
4. Giá trị khớp với nguồn thắng theo thứ tự đã dự đoán.
5. Có thể lặp lại bằng cùng artifact và cùng điều kiện.

Nếu kết quả khác dự đoán, lưu startup log và exception đầy đủ; kiểm tra profile, vị trí file, extension, quyền đọc và precedence trước khi kết luận.

## 14. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Đổi `spring.config.name` nhưng file không được nạp. | File vẫn mang tên `application.yml`, hoặc location không phải thư mục tìm kiếm như mong muốn. | Đổi tên file phù hợp, kiểm tra `spring.config.name` và kiểu location. |
| Có file ngoài nhưng ứng dụng vẫn dùng giá trị trong JAR. | Đã đặt sai đường dẫn, working directory khác, hoặc dùng location không đúng. | Kiểm tra đường dẫn tuyệt đối và thử marker key. |
| Sau khi đặt `spring.config.location`, cấu hình mặc định biến mất. | Đây là hành vi thay thế vị trí mặc định của location. | Dùng `spring.config.additional-location` nếu cần giữ cấu hình mặc định. |
| File ngoài không override được giá trị. | Location không được nạp, thứ tự khai báo khác dự đoán hoặc khóa không trùng. | Kiểm tra đường dẫn, thứ tự, profile và chính tả property. |
| Thiếu file nhưng ứng dụng không khởi động. | Location là bắt buộc và không tồn tại. | Tạo file đúng vị trí hoặc thêm `optional:` nếu file thực sự tùy chọn. |
| Thêm `optional:` nhưng ứng dụng vẫn lỗi. | Lỗi có thể nằm trong nội dung file, binding hoặc khởi tạo bean. | Đọc nguyên nhân gốc; optional không bỏ qua mọi lỗi. |
| Profile không nạp file mong muốn. | Sai profile, sai tên cơ sở hoặc tên file profile không khớp. | Kiểm tra `spring.profiles.active`, `spring.config.name` và `<name>-<profile>.yml`. |
| Chạy trong IDE được nhưng chạy service manager thất bại. | Working directory, environment hoặc quyền đọc file khác nhau. | Đặt working directory và environment rõ ràng; kiểm tra từ chính process triển khai. |
| Đặt location trong application.yml nhưng không có tác dụng. | Thuộc tính cần được biết trước khi file được tìm và nạp. | Truyền qua command line, system property hoặc environment. |
| Tưởng additional-location sẽ tải Config Server. | Nhầm vị trí file với cơ chế import của Spring Cloud Config. | Dùng `spring.config.import` và Config Client tương thích. |

## 15. Checklist hoàn thành

- [ ] Giải thích được vai trò của Spring Boot Config Data trong quá trình khởi động.
- [ ] Nêu được vì sao `spring.config.name` phải được cung cấp trước khi tệp cấu hình được tìm.
- [ ] Đổi được tên cơ sở từ `application` sang `orders` và tạo file tương ứng.
- [ ] Phân biệt `spring.config.location` thay thế với `spring.config.additional-location` bổ sung.
- [ ] Dùng đúng cú pháp location dạng thư mục và dạng file.
- [ ] Giải thích được ý nghĩa dấu `/` ở cuối đường dẫn thư mục.
- [ ] Biết location tương đối phụ thuộc working directory của process.
- [ ] Phân biệt location bắt buộc với location có tiền tố `optional:`.
- [ ] Kết hợp được tên file, profile và vị trí cấu hình.
- [ ] Truyền thuộc tính qua command line, JVM system property và environment variable.
- [ ] Phân biệt được các thuộc tính location với `spring.config.import` của Config Data và Spring Cloud Config.
- [ ] Chạy được phép thử marker để chứng minh file nào cung cấp giá trị cuối cùng.
- [ ] Không đưa secret vào file cấu hình được commit hoặc log.

**Tài liệu cần đối chiếu khi thực hành:** Spring Boot Reference về Externalized Configuration và Config Data; tài liệu Spring Cloud Config Client về Config Data import của release train đang sử dụng. Kiểm tra đúng phiên bản Boot/Cloud trước khi áp dụng cú pháp vào môi trường triển khai.

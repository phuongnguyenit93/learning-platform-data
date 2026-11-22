# Truyền cấu hình qua tệp, biến môi trường và tham số dòng lệnh trong Spring Boot

## 1. Mục tiêu của bài học

Trong Spring Boot, cùng một ứng dụng có thể chạy ở máy phát triển, môi trường thử nghiệm, staging và production mà không phải biên dịch lại mỗi khi đổi cổng HTTP, đường dẫn, timeout hoặc thông số kết nối. Cơ chế này gọi là **externalized configuration**: các giá trị cấu hình được cung cấp từ nhiều nguồn, hợp nhất thành Environment và được Spring Boot hoặc các Bean của ứng dụng sử dụng lúc khởi động.

Bài học tập trung vào cấu hình web-runtime và máy chủ nhúng, với ba kênh phổ biến nhất:

1. **Tệp cấu hình:** application.properties, application.yml/application.yaml, tệp theo profile và tệp ngoài artifact.
2. **Biến môi trường:** SERVER_PORT, SPRING_PROFILES_ACTIVE và các biến dành cho ứng dụng.
3. **Tham số dòng lệnh:** --server.port=9090, --spring.profiles.active=prod và các option khác truyền sau JAR.

Sau bài học, bạn có thể chọn nguồn cấu hình phù hợp, giải thích giá trị cuối cùng khi nhiều nguồn trùng key, chạy cùng một JAR với cấu hình khác nhau, sử dụng ConfigurationProperties để binding/validation và chẩn đoán lỗi khi server không bind đúng cổng.

Các ví dụ Java và Gradle được trình bày theo Spring Boot 3.3.x và Java 17 trở lên. Các nguyên lý external configuration cũng áp dụng rộng rãi cho các nhánh Spring Boot mới hơn, nhưng luôn đối chiếu tài liệu đúng phiên bản để kiểm tra tên starter, property và mặc định có thể thay đổi.

## 2. Phân biệt mã ứng dụng, artifact và cấu hình runtime

Mã nguồn xác định ứng dụng *làm gì*; cấu hình xác định ứng dụng *hoạt động với những giá trị nào*.

Ví dụ cùng một executable JAR có thể chạy như sau:

| Môi trường | Cổng HTTP | Chế độ ứng dụng | Nguồn cấu hình thường gặp |
| --- | --- | --- | --- |
| Laptop | 8080 | local | application.yml bên trong JAR |
| Staging | 9090 | staging | tệp bên ngoài, biến môi trường |
| Production | 8081 | production | ConfigMap/Secret, biến môi trường, tham số khởi chạy |
| Kiểm thử HTTP | cổng ngẫu nhiên | test | test properties hoặc RANDOM_PORT |

Để nhận request, Spring Boot phải tìm được giá trị cấu hình phù hợp, tạo ApplicationContext, khởi tạo embedded server và bind thành công vào port. Cấu hình không hợp lệ có thể khiến startup thất bại trước khi bất kỳ controller nào được gọi.

Một số nhóm property quan trọng cho web-runtime:

- server.port: cổng mà HTTP server lắng nghe; mặc định thông dụng là 8080.
- server.address: địa chỉ interface mà server bind vào.
- server.servlet.context-path: context path dành cho Servlet/Spring MVC.
- server.compression.enabled: bật/tắt nén HTTP response phù hợp.
- server.shutdown: chính sách shutdown trong các nhánh có hỗ trợ thuộc tính này.
- spring.lifecycle.timeout-per-shutdown-phase: thời gian chờ mỗi giai đoạn đóng lifecycle.
- spring.profiles.active: xác định profile đang kích hoạt.
- logging.level.root: điều chỉnh mức log.
- app.*: namespace tự định nghĩa cho cấu hình nghiệp vụ của ứng dụng.

Một property không nhất thiết tồn tại ở mọi Spring Boot version hoặc mọi web stack. Chẳng hạn server.servlet.context-path liên quan Servlet; với Spring WebFlux, cần cấu hình đường dẫn nền đúng API reactive tương ứng. Không sao chép nguyên khối cấu hình của MVC sang WebFlux khi chưa kiểm tra.

## 3. Spring Environment và PropertySource hoạt động ra sao?

Spring đặt các nguồn cấu hình vào một Environment gồm nhiều PropertySource. Khi cần tìm một key, cơ chế tra cứu xem xét độ ưu tiên và lấy giá trị phù hợp. Spring Boot dùng giá trị đó để cấu hình server, logging, auto-configuration và các Bean của ứng dụng.

Khái niệm cần phân biệt:

- **Property name:** tên logic, ví dụ server.port.
- **Property value:** giá trị sau khi được chọn, ví dụ 9090.
- **Property source:** nơi cung cấp key/value, ví dụ hệ điều hành, file YAML hoặc command-line.
- **Binding:** chuyển các giá trị dạng text sang kiểu Java như int, boolean, Duration, URI hoặc object có cấu trúc.
- **Profile:** cơ chế kích hoạt những nhóm cấu hình theo môi trường hoặc vai trò ứng dụng.

Một số property được đọc **rất sớm** trong bootstrap. Chẳng hạn spring.config.name, spring.config.location và spring.config.additional-location phải có hiệu lực trước khi Spring Boot xác định những file cấu hình cần nạp. Vì vậy, hãy cấp chúng qua môi trường, system property hoặc tham số khởi chạy, không đặt chúng vào chính file mà bạn đang cố yêu cầu Spring Boot tìm.

Giá trị từ Environment thường được xác định lúc ứng dụng startup. Thay đổi biến môi trường trong terminal khác hoặc sửa file YAML trên đĩa **không mặc nhiên cập nhật** port hoặc Bean đã được khởi tạo. Muốn thay đổi cấu hình runtime ổn định, thông thường phải khởi động lại tiến trình hoặc có một cơ chế refresh cấu hình được thiết kế riêng.

## 4. Cách 1: Tệp application.properties và application.yml

Spring Boot tự nhận diện những tệp cấu hình có basename application trong các vị trí được hỗ trợ. Hai định dạng phổ biến là Java Properties và YAML. Nên thống nhất một định dạng cho cùng một ứng dụng để giảm nhầm lẫn.

Ví dụ tệp src/main/resources/application.properties:

~~~properties
spring.application.name=server-config-demo
server.port=8080
server.compression.enabled=true
app.mode=local
app.request-timeout=2s
~~~

Cấu hình tương đương trong src/main/resources/application.yml:

~~~yaml
spring:
  application:
    name: server-config-demo

server:
  port: 8080
  compression:
    enabled: true

app:
  mode: local
  request-timeout: 2s
~~~

Cả hai file cùng biểu diễn các property logic như server.port và app.request-timeout. YAML dùng cấu trúc thụt dòng để nhóm thuộc tính; Spring Boot flatten chúng thành key dạng phân cấp. Ví dụ server.compression.enabled tương ứng với server -> compression -> enabled.

**Lưu ý:**

- YAML phải có mức thụt dòng chính xác, nên dùng dấu cách thay vì tab.
- Giá trị có ký tự đặc biệt có thể cần đặt trong dấu nháy; tránh dựa vào suy luận kiểu ngầm của YAML.
- Spring tự chuyển chuỗi "2s" thành Duration khi binding tới kiểu Duration thích hợp.
- Không đặt password/token thật trong file được commit vào Git.
- Nếu cùng vị trí chứa cả application.properties và YAML, tài liệu Spring Boot ưu tiên bản .properties; tốt hơn là không lưu hai phiên bản có cùng key.
- Khi tệp nằm trong resources và được đóng gói vào JAR, thay giá trị trong đó thường đòi hỏi rebuild artifact; dùng tệp ngoài cho những thay đổi theo môi trường.

### 4.1. Cấu hình theo profile

Một cấu trúc phổ biến:

~~~text
src/main/resources/
  application.yml
  application-dev.yml
  application-prod.yml
~~~

Tệp application.yml chứa mặc định dùng chung:

~~~yaml
server:
  port: 8080

app:
  mode: local
  request-timeout: 2s
~~~

Tệp application-dev.yml:

~~~yaml
server:
  port: 8085

app:
  mode: development
~~~

Tệp application-prod.yml:

~~~yaml
server:
  port: 8081

app:
  mode: production
  request-timeout: 5s
~~~

Kích hoạt profile prod bằng một trong các cách:

~~~bash
SPRING_PROFILES_ACTIVE=prod java -jar build/libs/server-config-demo-1.0.0.jar
~~~

~~~bash
java -jar build/libs/server-config-demo-1.0.0.jar --spring.profiles.active=prod
~~~

Khi profile prod thực sự được kích hoạt và không có nguồn ưu tiên cao hơn ghi đè, server.port nhận 8081, app.mode nhận production và app.request-timeout nhận 5s.

Đừng đặt spring.profiles.active trong application-prod.yml để tự kích hoạt chính profile prod. Profile phải được chọn từ môi trường hoặc một nguồn cấu hình hợp lệ trước khi tệp profile-specific được xử lý. Với nhiều active profile, thứ tự và nhóm config location có thể ảnh hưởng key nào thắng; không giả định mọi file sẽ luôn được ghép theo một thứ tự bất biến.

## 5. Tìm tệp cấu hình ở đâu?

Trong cấu hình mặc định của Spring Boot 3.3, các vị trí phổ biến gồm:

1. Classpath root, thường là resources đóng gói trong JAR.
2. Thư mục config trên classpath.
3. Thư mục làm việc hiện tại của tiến trình.
4. Thư mục config ngay dưới thư mục làm việc.
5. Những thư mục con trực tiếp của config bên ngoài artifact.

Các file ngoài JAR ở vị trí ưu tiên cao hơn có thể ghi đè file bên trong JAR. Vì thế hai tiến trình dùng cùng một JAR nhưng được khởi chạy từ hai working directory khác nhau có thể nhận cấu hình khác nhau.

Ví dụ cấu trúc triển khai:

~~~text
deploy/
  server-config-demo-1.0.0.jar
  config/
    application-prod.yml
~~~

Nếu chạy từ thư mục deploy với active profile prod, Spring Boot có thể tìm thấy tệp bên ngoài deploy/config/application-prod.yml. Nếu chạy cùng JAR từ một thư mục khác, file tương đối có thể không được tìm thấy như dự kiến.

Nên xác định rõ working directory, đường dẫn tuyệt đối/tương đối, profile và quyền đọc file. Không coi vị trí JAR và working directory luôn là cùng một thư mục.

### 5.1. spring.config.location

Property spring.config.location chỉ định vị trí sẽ được xét để nạp config data và **thay thế các vị trí mặc định**. Ví dụ chạy bằng thư mục chứa application.yml:

~~~bash
java -jar build/libs/server-config-demo-1.0.0.jar --spring.config.location=file:./deployment-config/
~~~

Thư mục trong config location cần dấu / ở cuối; Spring Boot sẽ nối basename của file cấu hình khi tìm. Nếu đặt một file cụ thể thay vì thư mục, file đó được nạp trực tiếp. Việc dùng location có thể tác động tới tập file profile-specific cần tìm.

Vì spring.config.location thay thế các vị trí mặc định, dùng nó thiếu chủ ý có thể làm ứng dụng mất các thiết lập mặc định trong JAR. Chỉ nên chọn khi muốn kiểm soát đầy đủ tập vị trí.

### 5.2. spring.config.additional-location

Nếu muốn giữ các vị trí mặc định và bổ sung file triển khai có độ ưu tiên cao hơn, dùng spring.config.additional-location:

~~~bash
java -jar build/libs/server-config-demo-1.0.0.jar --spring.config.additional-location=optional:file:./deployment-config/
~~~

Spring Boot vẫn xét các vị trí mặc định và bổ sung thư mục deployment-config. Từ khóa optional: cho phép bỏ qua vị trí không tồn tại. Nếu config là bắt buộc cho việc khởi chạy an toàn, bỏ optional: để lỗi xuất hiện sớm khi file/thư mục thiếu.

Dùng đường dẫn thật của môi trường, bảo đảm service account/process có quyền đọc. Không dựa vào working directory khi deploy bằng service manager nếu chưa xác minh.

### 5.3. spring.config.import

Có thể thêm tài nguyên cấu hình từ trong một file đã được đọc:

~~~yaml
spring:
  config:
    import: "optional:file:./extra-config.yml"
~~~

Tệp extra-config.yml có thể ghi đè các key được định nghĩa trong file đã khai báo import theo quy tắc của config data. Khi có nhiều import hoặc nhiều group location, cần nắm quy tắc ưu tiên tương ứng.

Cơ chế import còn hỗ trợ config tree, tiện khi nền tảng triển khai cung cấp nhiều file nhỏ như Secret hoặc ConfigMap:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
~~~

Ví dụ một file /run/secrets/app.token có thể tạo property app.token cho ứng dụng. Không nên đánh dấu optional: đối với secret thực sự bắt buộc rồi để ứng dụng chạy tiếp với giá trị thiếu.

## 6. Cách 2: Biến môi trường của hệ điều hành

Biến môi trường là cách phổ biến để truyền cấu hình vào tiến trình mà không sửa file bên trong JAR. Khi một process được tạo, nó nhận một bản sao environment của process cha cùng các giá trị được nền tảng cung cấp.

Trong Spring Boot, dạng mapping dễ nhớ nhất là:

| Property logic | Biến môi trường | Ý nghĩa |
| --- | --- | --- |
| server.port | SERVER_PORT | Cổng của embedded server |
| server.address | SERVER_ADDRESS | Địa chỉ bind |
| spring.profiles.active | SPRING_PROFILES_ACTIVE | Danh sách profile |
| logging.level.root | LOGGING_LEVEL_ROOT | Mức logging gốc |
| app.mode | APP_MODE | Chế độ tự định nghĩa |
| app.request-timeout | APP_REQUESTTIMEOUT | Thời lượng timeout tự định nghĩa |

Quy tắc relaxed binding chuẩn để đổi từ canonical property sang environment variable là: thay dấu chấm bằng dấu gạch dưới, **bỏ dấu gạch ngang**, rồi viết hoa. Vì thế app.request-timeout trở thành APP_REQUESTTIMEOUT. Với list, chỉ số thường được đặt giữa các dấu gạch dưới, ví dụ MY_SERVICE_0_OTHER cho my.service[0].other.

Các tài liệu/annotation dùng @ConfigurationProperties thường khuyến nghị tên canonical dạng chữ thường kebab-case, như app.request-timeout. Tránh đoán quy tắc binding từ việc tự chèn thêm underscore giữa mọi từ.

### 6.1. Linux/macOS: truyền tạm cho một tiến trình

~~~bash
SERVER_PORT=9090 APP_MODE=staging java -jar build/libs/server-config-demo-1.0.0.jar
~~~

Cách này chỉ cấp giá trị cho process được khởi chạy trong lệnh. Nó không thay đổi file YAML và không gán biến vĩnh viễn cho mọi terminal.

Để đặt biến cho shell hiện tại:

~~~bash
export SERVER_PORT=9090
export APP_MODE=staging
java -jar build/libs/server-config-demo-1.0.0.jar
~~~

Nếu muốn hủy biến trong shell hiện tại:

~~~bash
unset SERVER_PORT
unset APP_MODE
~~~

### 6.2. Windows PowerShell

~~~powershell
$env:SERVER_PORT = "9090"
$env:APP_MODE = "staging"
java -jar build/libs/server-config-demo-1.0.0.jar
~~~

Các biến này áp dụng cho process được khởi chạy từ phiên PowerShell đó. Để xóa trong phiên hiện tại:

~~~powershell
Remove-Item Env:SERVER_PORT
Remove-Item Env:APP_MODE
~~~

Nếu chạy ứng dụng bằng IDE, Windows Service, container hoặc CI/CD, biến môi trường phải được cấp cho đúng process. Việc đặt một biến trong terminal khác không tự thay đổi environment đã được truyền cho tiến trình ứng dụng đang chạy.

### 6.3. Biến môi trường và placeholder trong file

Có thể tham chiếu một biến bằng cú pháp placeholder Spring:

~~~yaml
server:
  port: ${PORT:8080}

app:
  mode: ${APP_MODE:local}
~~~

Ví dụ trên sử dụng biến PORT và APP_MODE nếu có; nếu không có thì dùng giá trị mặc định sau dấu hai chấm. Đây là một cách chủ động định nghĩa alias PORT cho server.port trong YAML.

Phân biệt hai cơ chế:

- SERVER_PORT trực tiếp ánh xạ vào property server.port từ OS environment.
- PORT chỉ được dùng để thay thế placeholder trong ví dụ trên; nó không phải tên environment variable canonical của server.port.

Nếu cả SERVER_PORT và PORT cùng tồn tại, SERVER_PORT có thể ghi đè giá trị lấy từ file YAML vì OS environment có ưu tiên cao hơn config data. Đừng giả định placeholder làm thay đổi quy tắc precedence của Spring Boot.

### 6.4. Docker Compose

Trong container, các biến môi trường được chuyển qua cấu hình service. Ví dụ:

~~~yaml
services:
  web:
    image: example/server-config-demo:1.0
    environment:
      SERVER_PORT: "8080"
      APP_MODE: "production"
      APP_REQUESTTIMEOUT: "5s"
    ports:
      - "8080:8080"
~~~

Đây là mẫu minh họa cho một image đã được xây dựng có lệnh start ứng dụng phù hợp. Phần bên trái của ports là port trên host; phần bên phải là port trong container. Nếu đổi SERVER_PORT thành 9090, cần đồng bộ port trong container với mapping/Service/health check, ví dụ "8080:9090".

Khi cấu hình không khớp, một container vẫn có thể chạy nhưng request từ host không đến đúng server. Luôn kiểm tra log bind port và lệnh curl theo port thực tế.

## 7. Cách 3: Tham số dòng lệnh của Spring Boot

Theo mặc định, SpringApplication đọc option dạng --key=value từ arguments của main rồi thêm vào Environment. Ví dụ:

~~~bash
java -jar build/libs/server-config-demo-1.0.0.jar --server.port=9191 --app.mode=cli
~~~

Ở đây --server.port và --app.mode là **Spring Boot application arguments**. Khi đồng thời tồn tại giá trị từ file, environment hoặc JVM system property, command-line arguments này thường có ưu tiên cao hơn trong ứng dụng chạy thông thường.

Có thể khởi chạy với nhiều option, bao gồm profile:

~~~bash
java -jar build/libs/server-config-demo-1.0.0.jar --spring.profiles.active=prod --server.port=9191 --logging.level.root=INFO
~~~

Dấu -- là thành phần quan trọng. Chỉ viết server.port=9191 không có -- sẽ không tạo property theo cú pháp mặc định. Cũng không đặt --server.port trước -jar và mong JVM hiểu đó là một tùy chọn Java.

### 7.1. Tham số JVM -D và tham số Spring Boot -- khác nhau

Hai lệnh dưới đây cấp cùng một property theo hai cơ chế:

~~~bash
java -Dserver.port=9095 -jar build/libs/server-config-demo-1.0.0.jar
~~~

~~~bash
java -jar build/libs/server-config-demo-1.0.0.jar --server.port=9095
~~~

Lệnh thứ nhất đặt Java system property trước -jar. Lệnh thứ hai truyền application argument cho Spring Boot sau đường dẫn JAR. Khi đồng thời có hai giá trị, --server.port của Spring Boot thường có ưu tiên cao hơn -Dserver.port.

Các JVM options như -Xmx512m hoặc -Dserver.port=9095 phải đặt ở vị trí dành cho Java launcher, tức là trước -jar. Nếu chuyển -Dserver.port=9095 ra sau tên JAR, nó chỉ là chuỗi application argument và không được Java launcher xử lý như system property.

### 7.2. Truyền arguments với Gradle bootRun

Trong project có Spring Boot Gradle plugin và task bootRun phù hợp:

~~~bash
./gradlew bootRun --args='--server.port=9191 --app.mode=cli'
~~~

Đây là lựa chọn tiện cho development. Lệnh java -jar sau khi build executable JAR giúp kiểm thử artifact gần cách deploy hơn.

### 7.3. Tắt command-line properties có được không?

Có. Khi tự cấu hình SpringApplication, ứng dụng có thể gọi setAddCommandLineProperties(false) để không đưa các option --key=value vào Environment. Đây là thay đổi có chủ đích trong bootstrap và sẽ làm khác đi quy tắc precedence. Nếu gặp trường hợp CLI không ghi đè file như mong đợi, cần xác minh ứng dụng có tùy biến này hay không.

Không nên tắt cơ chế này chỉ vì muốn giữ một giá trị cố định; hãy xác định rõ chính sách cấu hình của ứng dụng và triển khai.

## 8. Thứ tự ưu tiên khi nhiều nguồn cùng khai báo

Spring Boot 3.3 xác định thứ tự PropertySource chi tiết hơn danh sách dưới đây. Với một ứng dụng production thông thường, chỉ xét các nguồn đang học, thứ tự tổng quát **từ mạnh xuống yếu** là:

1. Spring Boot application arguments --key=value.
2. SPRING_APPLICATION_JSON.
3. Java system properties truyền qua -Dkey=value.
4. OS environment variables.
5. Config data từ file .properties/.yml (vị trí ngoài JAR có thể ghi đè cấu hình đóng gói).
6. Các giá trị mặc định do ứng dụng đặt.

Trong unit/integration test, @TestPropertySource, @DynamicPropertySource và test properties có mức ưu tiên riêng, có thể cao hơn CLI. Do đó không đem bảng giản lược này áp dụng máy móc cho mọi loại test.

Ngay trong config data, giá trị profile-specific thường ghi đè giá trị không gắn profile khi các file tương ứng được xét theo đúng quy tắc location/group. File bên ngoài thường ưu tiên hơn file bên trong JAR. Với nhiều location và profile khác nhau, thứ tự xử lý chi tiết có thể phức tạp; hãy dùng chính cấu hình đang chạy để xác minh.

Ví dụ xung đột minh họa:

| Nguồn | server.port |
| --- | ---: |
| application.yml trong JAR | 8080 |
| application-prod.yml bên ngoài | 8081 |
| SERVER_PORT | 9090 |
| -Dserver.port | 9190 |
| --server.port | 9290 |

Nếu tất cả nguồn trên thực sự đang hoạt động trong một lần chạy bình thường, port hiệu lực sẽ là **9290** vì tham số Spring Boot --server.port có độ ưu tiên cao nhất trong nhóm này.

Nếu bỏ CLI thì port thành 9190; bỏ cả JVM -D thì port thành 9090; bỏ environment thì có thể về 8081. Đó là ví dụ để học precedence, không có nghĩa mỗi project đều phải đặt cùng key ở năm nơi.

### 8.1. Ví dụ lệnh giải quyết xung đột

Giả sử file mặc định chứa server.port=8080:

~~~bash
SERVER_PORT=9090 java -Dserver.port=9190 -jar build/libs/server-config-demo-1.0.0.jar --server.port=9290
~~~

Kết quả kỳ vọng là server cố gắng bind cổng 9290. Kỳ vọng này chỉ đúng nếu port rảnh, cấu hình liên quan hợp lệ và ứng dụng chưa tùy chỉnh cơ chế đọc command-line property.

### 8.2. SPRING_APPLICATION_JSON

Spring Boot cũng hỗ trợ truyền JSON cấu hình trong biến môi trường:

~~~bash
SPRING_APPLICATION_JSON='{"server":{"port":9090},"app":{"mode":"json"}}' java -jar build/libs/server-config-demo-1.0.0.jar
~~~

Nội dung JSON tương ứng server.port=9090 và app.mode=json. Trong thứ tự mặc định, nguồn này ưu tiên hơn OS environment nhưng dưới command-line arguments. Đây là công cụ hữu ích cho các môi trường cần truyền cấu hình phân cấp mà không tạo nhiều biến riêng.

Không đặt secret vào command history hoặc lệnh shell có thể bị ghi log. Giá trị null trong JSON cũng không được coi là cơ chế đáng tin để xóa giá trị của một property ở nguồn thấp hơn.

## 9. Thực hành Java 17+ và Spring Boot 3.3: một JAR, ba nguồn cấu hình

Phần này là một project mẫu độc lập. Điều kiện: có JDK 17+, Gradle Wrapper phiên bản tương thích Spring Boot 3.3 và truy cập repository phụ thuộc. Không cần tự cài Tomcat riêng vì starter web cung cấp embedded server.

Cấu trúc:

~~~text
server-config-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/example/web/
        ServerConfigApplication.java
        AppSettings.java
        RuntimeConfigController.java
      resources/
        application.yml
    test/
      java/example/web/
        AppSettingsTest.java
~~~

### 9.1. Tệp settings.gradle

~~~groovy
rootProject.name = 'server-config-demo'
~~~

### 9.2. Tệp build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Trong dự án đã có cấu hình Gradle hoặc dependency management riêng, giữ quy ước phiên bản và plugin được dự án quản lý. Các version trong ví dụ chỉ phục vụ việc tái hiện một project Spring Boot 3.3, không phải lời khuyên nâng/hạ version cho module hiện hữu.

### 9.3. Tệp application.yml

~~~yaml
spring:
  application:
    name: server-config-demo

server:
  port: 8080

app:
  mode: local
  request-timeout: 2s
~~~

### 9.4. Tệp ServerConfigApplication.java

~~~java
package example.web;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ServerConfigApplication {
    public static void main(String[] args) {
        SpringApplication.run(ServerConfigApplication.class, args);
    }
}
~~~

@ConfigurationPropertiesScan sẽ tìm class cấu hình phù hợp trong vùng scan và đăng ký Bean binding vào Environment.

### 9.5. Tệp AppSettings.java

~~~java
package example.web;

import java.time.Duration;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record AppSettings(
        @NotBlank String mode,
        @NotNull Duration requestTimeout
) {
}
~~~

Record Java giúp mô tả một nhóm property bất biến. Thuộc tính app.mode binding vào String mode; app.request-timeout binding vào Duration requestTimeout. Validation starter cung cấp Bean Validation để kiểm tra khi binding.

Ví dụ, thiếu app.mode hoặc app.request-timeout ở mọi nguồn có thể làm startup thất bại thay vì để lỗi null xuất hiện khi xử lý request. Cơ chế đó giúp phát hiện cấu hình thiếu sớm, nhưng chỉ áp dụng khi Bean cấu hình được đăng ký/validate đúng.

### 9.6. Tệp RuntimeConfigController.java

~~~java
package example.web;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RuntimeConfigController {
    private final AppSettings settings;

    public RuntimeConfigController(AppSettings settings) {
        this.settings = settings;
    }

    @GetMapping("/api/runtime-config")
    public Map<String, Object> currentConfig() {
        return Map.of(
                "mode", settings.mode(),
                "requestTimeoutMs", settings.requestTimeout().toMillis()
        );
    }
}
~~~

Đây là endpoint học tập chỉ trả hai giá trị không nhạy cảm. Khi triển khai thật, không nên tạo endpoint tự ý công khai mọi cấu hình, nhất là secret và thông tin mạng nội bộ.

### 9.7. Chạy với cấu hình trong tệp

Trên Linux/macOS:

~~~bash
./gradlew bootRun
~~~

Khi ứng dụng bind thành công cổng 8080, chạy ở terminal khác:

~~~bash
curl -i http://localhost:8080/api/runtime-config
~~~

Response HTTP mong đợi là 200, body có hai field và giá trị tương đương:

~~~json
{"mode":"local","requestTimeoutMs":2000}
~~~

Thứ tự các key JSON không được bảo đảm; điều phải kiểm tra là giá trị. Nếu server khởi động lỗi, xem exception và log trước khi gọi endpoint.

### 9.8. Chạy cùng artifact bằng biến môi trường

Build trước:

~~~bash
./gradlew test
./gradlew bootJar
~~~

Sau đó chạy trên Linux/macOS:

~~~bash
SERVER_PORT=9090 APP_MODE=staging APP_REQUESTTIMEOUT=5s java -jar build/libs/server-config-demo-1.0.0.jar
~~~

Gọi:

~~~bash
curl -i http://localhost:9090/api/runtime-config
~~~

Kỳ vọng HTTP 200 và JSON có mode=staging, requestTimeoutMs=5000. Tệp application.yml không cần sửa. Biến SERVER_PORT đã ghi đè server.port=8080 từ JAR.

### 9.9. Chạy cùng artifact bằng tham số dòng lệnh

~~~bash
java -jar build/libs/server-config-demo-1.0.0.jar --server.port=9191 --app.mode=cli --app.request-timeout=3s
~~~

Sau khi server khởi động thành công:

~~~bash
curl -i http://localhost:9191/api/runtime-config
~~~

Kỳ vọng HTTP 200, mode=cli và requestTimeoutMs=3000. Cách này không tạo lại JAR; chỉ thay những giá trị được cấp khi khởi chạy.

### 9.10. Kết hợp ba nguồn

Đặt file YAML mặc định như trên, xuất biến:

~~~bash
export SERVER_PORT=9090
export APP_MODE=staging
~~~

Rồi chạy:

~~~bash
java -jar build/libs/server-config-demo-1.0.0.jar --server.port=9191
~~~

Cổng hiệu lực là 9191 vì CLI ghi đè biến môi trường; app.mode vẫn là staging vì CLI không ghi đè key này. requestTimeout tiếp tục lấy 2s từ YAML nếu không có nguồn ưu tiên cao hơn.

Đây là cơ chế **ghi đè theo key**, không có nghĩa toàn bộ file YAML bị thay thế bởi một biến môi trường. Các key không bị override vẫn giữ giá trị từ nguồn thấp hơn.

### 9.11. Test binding của AppSettings

Tệp src/test/java/example/web/AppSettingsTest.java:

~~~java
package example.web;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(properties = {
        "app.mode=test",
        "app.request-timeout=7s",
        "server.port=0"
})
class AppSettingsTest {

    @Autowired
    AppSettings settings;

    @Test
    void bindsPropertiesFromTestConfiguration() {
        assertEquals("test", settings.mode());
        assertEquals(Duration.ofSeconds(7), settings.requestTimeout());
    }
}
~~~

Test này kiểm tra cấu hình binding khi Spring ApplicationContext khởi tạo. Thuộc tính server.port=0 ở đây là một cấu hình minh họa, không khẳng định test đang mở một HTTP port vì @SpringBootTest mặc định dùng mock web environment. Muốn kiểm thử HTTP server thật, hãy dùng webEnvironment=RANDOM_PORT và HTTP client trong test.

Chạy:

~~~bash
./gradlew test
~~~

Đối với CI/CD, nên chạy cả test cấu hình thiếu/sai và test khởi động với profile quan trọng để phát hiện cấu hình lệch trước triển khai.

## 10. Khi nào dùng @Value, Environment, @ConfigurationProperties?

### @Value: lấy một giá trị riêng lẻ

Ví dụ một đoạn code minh họa nằm trong một Spring Bean:

~~~java
@Value("${app.mode:local}")
private String mode;
~~~

Dấu hai chấm sau property name đặt giá trị fallback. Cách này ngắn gọn, nhưng khi nhiều property liên quan đến nhau, chúng dễ bị rải rác trên nhiều class và khó kiểm soát validation.

### Environment: truy vấn trực tiếp

Trong một Spring Bean có thể inject Environment rồi gọi:

~~~java
String port = environment.getProperty("server.port", "8080");
~~~

Đây là đoạn minh họa cho biến environment kiểu org.springframework.core.env.Environment đã được inject. Nó đọc property theo key và có giá trị fallback; không phải cách lấy cổng HTTP thực đã bind nếu bạn dùng server.port=0. Trong trường hợp port ngẫu nhiên, cần lấy actual local server port theo API phù hợp.

### @ConfigurationProperties: nhóm cấu hình có cấu trúc

Với nhiều field liên quan, @ConfigurationProperties thường phù hợp hơn. Lợi ích là type-safe binding, hỗ trợ enum/Duration/DataSize, validation và dễ viết test. Record AppSettings ở phần 9 cho thấy cấu hình nhóm app.* được bind một lần rồi inject vào controller.

Quy tắc thiết kế thực tế:

- Đặt tên nhóm rõ ràng, ví dụ app.http-client hoặc app.features.
- Dùng các kiểu có nghĩa: Duration cho timeout, DataSize cho byte size, boolean cho flag.
- Định nghĩa default có chủ đích; không đặt default không an toàn cho secret bắt buộc.
- Validate ràng buộc bắt buộc.
- Hạn chế đọc từng property bằng chuỗi hard-code ở nhiều nơi.
- Cần phân biệt setting của Spring Boot (server.*) với setting tự định nghĩa của ứng dụng (app.*).

## 11. Relaxed binding và lỗi đặt tên property

Spring Boot cho phép binding một số biến thể cách viết như kebab-case, camelCase, underscore và tên biến môi trường viết hoa. Nhưng không nên coi mọi biến thể là tương đương trong mọi hoàn cảnh.

Ví dụ property canonical:

~~~properties
app.request-timeout=5s
~~~

Biến environment theo quy tắc chính thức:

~~~bash
export APP_REQUESTTIMEOUT=5s
~~~

Các lỗi thường gặp:

- Tự đổi dấu gạch ngang thành dấu gạch dưới rồi cho rằng APP_REQUEST_TIMEOUT chắc chắn là tên tương đương; theo phép chuyển canonical -> OS environment, dấu gạch ngang cần **bị loại bỏ**.
- Nhầm property app.request-timeout với server.connection-timeout hoặc timeout của HTTP client; các key này điều khiển thành phần khác nhau.
- Dùng key có dấu chấm trong tên biến Linux shell, khiến lệnh export không hợp lệ.
- Đặt tên biến khác nhau giữa Docker, Kubernetes, CI/CD và local environment.
- Tự thiết kế alias kiểu PORT nhưng quên cấu hình placeholder tương ứng trong file.
- Truyền boolean và Duration sai định dạng, gây binding error khi startup.

Với map hoặc list property, quy tắc tên environment phức tạp hơn; nên đối chiếu tài liệu chính thức khi cấu hình danh sách server, các endpoint hoặc key dạng bản đồ. Với Map từ environment, tên key có thể bị hạ về chữ thường, nên tránh phụ thuộc vào key phân biệt hoa/thường nếu cấu hình bằng OS env.

## 12. Các kiểu và đơn vị đo trong cấu hình server

Spring Boot dùng binding để chuyển từ text thành kiểu Java. Một số cấu hình của embedded server có kiểu thời lượng hoặc số, nhưng không phải property nào cũng dùng cùng đơn vị hoặc tồn tại trên mọi server.

Ví dụ cấu hình chung:

~~~yaml
server:
  port: 8080
  compression:
    enabled: true
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Nên viết đơn vị rõ ràng cho Duration khi property cho phép, ví dụ 500ms, 2s hoặc 20s. Không đoán rằng mọi timeout đều dùng milliseconds; tên property, version và type có thể quy định mặc định đơn vị khác nhau.

Đối với các property server.tomcat.*, server.jetty.*, server.undertow.* hoặc server.netty.*, phải xác định web stack/server đang dùng. Đặt một property dành cho Tomcat khi ứng dụng thực tế chạy Jetty không tự biến cấu hình đó thành setting Jetty. Với Spring Boot 4.x, Undertow không còn là embedded server được tích hợp theo cách của Boot 3.x; luôn kiểm tra phiên bản nếu học sâu property riêng của server.

### 12.1. Thay port và địa chỉ bind

Trong môi trường container, cổng mà Spring Boot bind phải phù hợp với container port, host port, ingress hoặc Service. Ví dụ SERVER_PORT=9090 khiến ứng dụng cố bind cổng 9090; việc publish một port khác trên host là cấu hình của Docker/Kubernetes, độc lập với property này.

server.address có thể giới hạn interface lắng nghe. Nếu bind vào 127.0.0.1 trong container, yêu cầu từ ngoài container thường không vào được dù có publish port. Kiểm tra address thực tế và network topology thay vì chỉ nhìn server.port.

### 12.2. Port 0 trong kiểm thử

server.port=0 yêu cầu hệ điều hành chọn một cổng còn trống khi embedded server thực sự được khởi chạy. Đây là lựa chọn hữu ích để giảm xung đột cổng trong integration test. Tuy nhiên giá trị property cấu hình vẫn là 0, còn cổng thực được cấp sau bind là một số khác; cần đọc actual server port bằng API test/runtime phù hợp.

## 13. Dùng file, environment và CLI trong container/Kubernetes

Ở quy mô triển khai nhiều môi trường, việc cố định một mẫu artifact giúp kiểm soát version và rollback. Cấu hình nên được đưa vào lúc chạy.

Các cách thường gặp:

- Environment variables cho các giá trị đơn giản như profile, port, feature flag.
- File cấu hình mount từ ConfigMap hoặc volume khi nhiều property có cấu trúc.
- Secret store/Secret volume cho thông tin nhạy cảm như mật khẩu, private key và token.
- Command-line arguments cho override có chủ đích trong một job hoặc tình huống vận hành ngắn hạn.
- spring.config.import hoặc configtree: để Spring Boot tìm những file mount phù hợp.

Ví dụ một phần manifest Kubernetes để đặt environment, giả sử container image đã có lệnh chạy ứng dụng:

~~~yaml
env:
  - name: SPRING_PROFILES_ACTIVE
    value: "prod"
  - name: SERVER_PORT
    value: "8080"
  - name: APP_MODE
    value: "production"
ports:
  - name: http
    containerPort: 8080
~~~

Đây là phần trường của một container spec, không phải Deployment YAML hoàn chỉnh. Manifest thực cần apiVersion, kind, metadata, spec và các thành phần triển khai khác. Cấu hình readiness/liveness cũng phải trỏ tới port và path thực tế.

Một file application-prod.yml được mount có thể được tìm bằng spring.config.additional-location. Nếu file cần thiết không tồn tại, quá trình khởi động nên thất bại rõ ràng thay vì âm thầm dùng giá trị production sai.

Mỗi lần deploy, hãy ghi nhận artifact version, cấu hình không nhạy cảm, profile và thay đổi config có chủ đích. Tránh sửa trực tiếp ConfigMap/Secret ngoài quy trình có kiểm soát làm runtime không còn tương ứng với định nghĩa triển khai.

## 14. Bảo mật cấu hình

Externalized configuration giúp tách cấu hình khỏi artifact, nhưng không tự biến mọi nguồn thành an toàn.

- **Không commit secret thật** vào application.yml, source code, tài liệu hay test fixture công khai.
- **Không đặt secret trong CLI** nếu có thể tránh, vì tham số có thể xuất hiện trong command history, process inspection hoặc log triển khai.
- **Biến môi trường không phải secret vault.** Chúng vẫn có thể bị lộ qua dump, log, công cụ quản trị hoặc quyền truy cập process không phù hợp.
- **Dùng cơ chế quản lý secret** của nền tảng, có quyền truy cập tối thiểu và quy trình rotate.
- **Không trả toàn bộ Environment qua HTTP** hoặc log toàn bộ cấu hình khi startup.
- **Giới hạn Actuator env/configprops** theo yêu cầu vận hành, vì các endpoint này có thể hé lộ tên key hoặc metadata cấu hình dù giá trị nhạy cảm được sanitize.
- **Validation và fail fast** với cấu hình bắt buộc giúp tránh chạy ứng dụng trong trạng thái không an toàn.
- **Phân biệt default an toàn** với default tiện lợi; ví dụ thiếu token production nên fail, không tự điền token mẫu.

Việc người dùng có thể override cấu hình bằng --... cũng là một quyền vận hành đáng kiểm soát. Quy trình startup, Helm chart, systemd unit hoặc job definition cần được review như một phần cấu hình hạ tầng.

## 15. Cách xác minh giá trị hiệu lực khi khởi động

Khi cấu hình không như dự kiến, nên kiểm tra theo trình tự:

1. Xác định **tiến trình thực sự được chạy**: JAR nào, lệnh khởi chạy gì, working directory nào.
2. Xác định **active profiles**: prod, dev, test hoặc default.
3. Liệt kê **những nguồn cấu hình dự kiến** cho đúng key: file packaged, file ngoài, env, -D và --.
4. Kiểm tra **tên key** và mapping environment, đặc biệt tên có dấu gạch ngang.
5. Kiểm tra **path và quyền đọc** của file, config location/import và sự tồn tại của file theo profile.
6. Tìm **lỗi binding/validation** trong stack trace nếu ApplicationContext thất bại.
7. Đọc **log embedded server** để xác nhận actual bind address/port.
8. Gửi **request HTTP thật** đến port/path dự kiến và kiểm tra status/body.

Spring Boot Actuator có endpoint env và configprops phục vụ chẩn đoán khi được bật và bảo vệ phù hợp. Có thể dùng chúng để xác định nguồn/giá trị không nhạy cảm theo khả năng của phiên bản. Không mở endpoint này công khai chỉ để debug production.

Tham số --debug hỗ trợ xem condition evaluation report của auto-configuration; không đồng nghĩa luôn in chính xác toàn bộ nguồn gốc mọi property. Để tìm lý do một Bean không được tạo, đọc condition report; để tìm lý do server.port có giá trị cụ thể, xem property sources và cấu hình thực.

### 15.1. Ví dụ lỗi cổng đã bị chiếm

Nếu SERVER_PORT=9090 mà một process khác đang lắng nghe 9090, ứng dụng có thể không start được. Đây là lỗi bind port chứ không phải bằng chứng Spring Boot bỏ qua env.

Cách phân biệt:

- Log cho biết application đã đọc đúng port 9090 nhưng bind thất bại: xử lý xung đột port.
- Log cho biết server chạy ở port 8080: kiểm tra biến env có được truyền cho process và có nguồn ưu tiên cao hơn không.
- Server chạy port 9090 nhưng curl đến localhost:9090 thất bại từ máy khác/container khác: kiểm tra bind address, network, mapping và firewall.
- Server trả 404: kiểm tra route/context path; kết nối đến server đã được thiết lập, vì vậy đây là vấn đề khác bind port.

## 16. Bảng lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng khắc phục |
| --- | --- | --- |
| File application-prod.yml không có hiệu lực | Profile prod chưa kích hoạt hoặc file sai vị trí | Kiểm tra SPRING_PROFILES_ACTIVE, working directory và config location |
| Đặt SERVER_PORT nhưng vẫn dùng port khác | Biến không tới process, CLI/-D override hoặc tên key sai | Kiểm tra lệnh start, process environment và precedence |
| spring.config.location làm mất default trong JAR | location thay thế đường dẫn mặc định | Dùng additional-location nếu mục tiêu chỉ là bổ sung |
| Thiếu file dẫn đến startup fail | Config bắt buộc không tồn tại hoặc thiếu quyền đọc | Cấp đúng path/permission; dùng optional: chỉ khi thực sự tùy chọn |
| application.yml bị lỗi parse | Thụt dòng YAML sai hoặc ký tự đặc biệt chưa quote | Kiểm tra YAML syntax và line gây lỗi |
| app.request-timeout binding thất bại | Giá trị không thể chuyển thành Duration | Dùng đơn vị rõ ràng như 5s; đọc cause trong stack trace |
| @ConfigurationProperties không được inject | Class chưa đăng ký qua scan/enable hoặc package nằm ngoài vùng scan | Kiểm tra @ConfigurationPropertiesScan, package và Bean registration |
| Đổi biến env nhưng app vẫn giữ giá trị cũ | Process đã chạy với environment trước đó | Restart theo quy trình; không dựa vào tự refresh |
| CLI có --server.port nhưng không ghi đè | Cú pháp sai hoặc ứng dụng đã tắt addCommandLineProperties | Kiểm tra argument và SpringApplication bootstrap |
| Docker publish port nhưng không gọi được app | Port container khác server.port, bind sai address hoặc routing lỗi | Đồng bộ port mapping và xác minh actual listener |
| Secret xuất hiện trong log | In Environment/configprops hoặc bật debug nhạy cảm | Loại bỏ log; bảo vệ secret và rotate nếu đã lộ |
| Giá trị profile không đúng như mong đợi | Nhiều profile/location cùng định nghĩa key | Xác minh nguồn hiệu lực và thứ tự config data |

## 17. Quy tắc thiết kế cấu hình cho một ứng dụng web

Một chiến lược dễ duy trì:

1. Đặt các default an toàn, ít phụ thuộc môi trường trong application.yml bên trong artifact.
2. Nhóm property riêng của ứng dụng bằng một prefix rõ ràng như app.*.
3. Dùng @ConfigurationProperties cho nhóm cấu hình có type, validation và tài liệu cụ thể.
4. Dùng biến môi trường cho các override đơn giản, nhất quán giữa container/CI/CD.
5. Dùng file ngoài hoặc ConfigMap khi nhóm cấu hình có nhiều trường hoặc cần quản lý như một đơn vị.
6. Dùng secret manager hoặc secret mount cho credential, không ghi secret vào version control.
7. Dùng CLI override có chủ đích khi cần thay một giá trị của một lần chạy; tránh để các lệnh thủ công rời rạc trở thành chuẩn production.
8. Định nghĩa rõ profile, working directory, đường dẫn config ngoài và những key bắt buộc.
9. Kiểm thử startup với profile quan trọng và kiểm thử HTTP đối với server settings.
10. Ghi nhận cấu hình không nhạy cảm và version triển khai, có khả năng rollback nhanh.

Phân tách trách nhiệm giữa các đội rõ hơn khi ứng dụng sở hữu schema và validation cho app.*, còn hệ thống deploy sở hữu giá trị khác nhau theo môi trường. Dù giá trị đến từ đâu, ứng dụng phải tự kiểm tra tính hợp lệ và tránh để những cấu hình không an toàn lọt vào runtime.

## 18. Bài thực hành tổng hợp

Mục tiêu: chứng minh một JAR Spring Boot có thể nhận cấu hình từ cả ba kênh và giải thích thứ tự ưu tiên.

**Bước 1:** Dựng project ở phần 9; chạy bằng application.yml. Kiểm tra server.port=8080, mode=local và requestTimeoutMs=2000.

**Bước 2:** Đặt SERVER_PORT=9090 và APP_MODE=staging. Chạy lại JAR, xác minh URL phải đổi sang localhost:9090 và mode=staging.

**Bước 3:** Giữ env ở bước 2, thêm --server.port=9191. Xác minh port 9191 thắng môi trường và mode vẫn là staging.

**Bước 4:** Thêm -Dapp.mode=jvm ở vị trí trước -jar, không truyền --app.mode. Xác minh mode=jvm vì JVM system property ưu tiên hơn OS env.

**Bước 5:** Truyền --app.mode=cli đồng thời với -Dapp.mode=jvm. Xác minh mode=cli vì command-line arguments có ưu tiên cao hơn JVM system property.

**Bước 6:** Tạo application-prod.yml, kích hoạt profile prod và quan sát chỉ các key được định nghĩa có giá trị khác; những key còn lại vẫn có thể lấy từ application.yml.

**Bước 7:** Thử spring.config.additional-location với thư mục config ngoài. Kiểm tra xem key mới có ghi đè default như dự kiến không, rồi so với spring.config.location để giải thích khác biệt.

**Bước 8:** Xóa app.request-timeout ở mọi nguồn cấu hình cần thiết trong một bản thử nghiệm và kiểm tra lỗi binding/validation. Phục hồi trước khi chạy tiếp.

**Bước 9:** Thử server.port=0 trong một integration test thật, ghi nhận actual port được cấp, rồi so sánh với giá trị property cấu hình.

**Bước 10:** Tổng hợp kết quả bằng bảng gồm nguồn, lệnh chạy, active profile, server.port thực tế, app.mode, requestTimeoutMs, status HTTP và lời giải thích về precedence.

Bài thực hành đạt khi có log/HTTP evidence cho các lần chạy, có khả năng dự đoán giá trị theo nguồn, và không cần sửa hay build lại source code để thay port/mode.

## 19. Tự kiểm tra

1. Tại sao cùng một JAR có thể chạy trên nhiều port?
2. Spring Environment khác một file application.yml ở điểm nào?
3. Khi cả file và SERVER_PORT cùng khai báo server.port, nguồn nào thường có ưu tiên cao hơn?
4. Nếu truyền --server.port=9191 và -Dserver.port=9095, port nào thường được chọn? Vì sao?
5. Tại sao -Dserver.port phải đứng trước -jar?
6. spring.config.location khác spring.config.additional-location như thế nào?
7. Tại sao cần chú ý working directory khi tìm tệp ngoài JAR?
8. application-prod.yml chỉ được nạp trong điều kiện gì?
9. app.request-timeout ánh xạ sang tên environment theo quy tắc nào?
10. Khi nào nên dùng @Value, Environment hoặc @ConfigurationProperties?
11. Vì sao đổi biến môi trường không tự làm cổng HTTP của tiến trình đang chạy thay đổi?
12. Khi nhận lỗi bind port, làm sao phân biệt config sai với port đang bị chiếm?
13. Vì sao secret trong CLI hoặc environment vẫn cần chính sách bảo vệ?
14. Vì sao test @SpringBootTest mặc định không chứng minh embedded server đang lắng nghe một port thật?
15. Nếu Kubernetes Service trỏ đến port 8080 nhưng ứng dụng bind 9090, cần kiểm tra những cấu hình nào?

## Tài liệu chính thức để đối chiếu

- [Spring Boot 3.3 – Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot 3.3 – Profiles](https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html)
- [Spring Boot 3.3 – Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot 3.3 – Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html)
- [Spring Boot – Current Externalized Configuration Reference](https://docs.spring.io/spring-boot/reference/features/external-config.html)

Hãy dùng tài liệu tương ứng với phiên bản đang chạy để xác nhận thứ tự nguồn, cấu hình được hỗ trợ và hành vi bootstrap trước khi áp dụng vào production.

# Config Data: cấu hình đóng gói và cấu hình bên ngoài ứng dụng

## 1. Vấn đề cần giải quyết

Một ứng dụng Spring Boot thường được đóng gói thành một file JAR duy nhất nhưng phải chạy tại nhiều môi trường: máy lập trình viên, kiểm thử, staging và production. Mã nguồn có thể giống nhau, còn cổng HTTP, URL cơ sở dữ liệu, thời gian chờ hay các tính năng bật/tắt có thể khác nhau.

Nếu đưa mọi giá trị của từng môi trường vào mã Java hoặc build riêng JAR cho từng môi trường, việc triển khai khó kiểm soát. Cách làm phù hợp là **đóng gói các giá trị mặc định hợp lý trong ứng dụng** và **cấp giá trị đặc thù của môi trường từ bên ngoài** khi chạy.

Spring Boot gọi cơ chế nạp các file cấu hình ứng dụng như `application.properties` và `application.yml` là **Config Data**. Các file này được nạp vào `Environment`, nơi Spring tra cứu các thuộc tính bằng tên khóa như `server.port` hoặc `app.notification.enabled`.

Sau bài này, bạn cần có thể:

- Phân biệt cấu hình **đóng gói trong JAR** và **nằm ngoài JAR**.
- Xác định các vị trí Spring Boot tự tìm file `application.*`.
- Giải thích thứ tự ghi đè khi cùng một khóa xuất hiện ở nhiều file, kể cả file theo profile.
- Dùng `spring.config.location`, `spring.config.additional-location`, `spring.config.import` và `optional:` đúng mục đích.
- Tự phân tích giá trị cuối cùng mà một ứng dụng nhận được khi khởi động.

## 2. Config Data là gì?

Trong phạm vi Spring Boot 3.3, **Config Data** chủ yếu là dữ liệu đọc từ các file cấu hình `application.properties`, `application.yaml` hoặc `application.yml`, cùng các nguồn được nhập thêm bằng `spring.config.import`. Cấu hình được xử lý ngay từ giai đoạn khởi động để các thành phần như web server, datasource và bean có thể sử dụng.

Có hai nhóm vị trí quan trọng:

| Nhóm | Ví dụ | Đặc điểm |
| --- | --- | --- |
| **Packaged / classpath** | `src/main/resources/application.yml` được đưa vào JAR | Đi theo artifact khi build và triển khai; phù hợp cho giá trị mặc định chung |
| **External / filesystem** | `./config/application.yml` hoặc `/etc/my-service/application.yml` | Được cung cấp bên ngoài JAR; có thể thay đổi theo môi trường mà không cần build lại |

Ví dụ cấu trúc khi phát triển và sau khi triển khai:

~~~text
my-service/
├── src/main/resources/
│   └── application.yml        # Được đóng gói khi build
└── build/libs/my-service.jar

/deploy/my-service/
├── my-service.jar
└── config/
    ├── application.yml        # Cấu hình ngoài JAR
    └── application-prod.yml   # Ghi đè khi profile prod hoạt động
~~~

**Lưu ý quan trọng:** một đường dẫn tương đối như `./config/` được tính theo **working directory của tiến trình Java** (thư mục hiện hành khi chạy lệnh), không mặc định theo thư mục chứa JAR. Nếu chạy `java -jar /opt/apps/my-service.jar` từ `/srv/runtime`, Spring sẽ tìm `./config/` dưới `/srv/runtime`.

`Config Data` chỉ là **một nhóm nguồn thuộc tính** trong `Environment`; biến môi trường hệ điều hành, Java system properties và đối số dòng lệnh là những nguồn khác, có thể tiếp tục ghi đè giá trị đã đọc từ file.

## 3. Spring Boot tự tìm file cấu hình ở đâu?

Khi không khai báo vị trí tùy chỉnh, Spring Boot tìm các file tên `application` với phần mở rộng được hỗ trợ ở những vị trí mặc định sau:

| Thứ tự tìm kiếm | Vị trí | Ý nghĩa |
| --- | --- | --- |
| 1 | `classpath:/` | Gốc classpath, thường là `src/main/resources/` sau khi build |
| 2 | `classpath:/config/` | Thư mục `config` bên trong classpath/JAR |
| 3 | `file:./` | Thư mục làm việc của tiến trình |
| 4 | `file:./config/` | Thư mục `config` bên ngoài ứng dụng |
| 5 | `file:./config/*/` | Các thư mục con trực tiếp của `./config/` |

Những mục xuất hiện sau có thể ghi đè thuộc tính trùng tên từ mục trước. `file:` nghĩa là tài nguyên trên hệ thống tệp; `classpath:` nghĩa là tài nguyên nằm trên classpath. Mẫu `*/` ở vị trí mặc định áp dụng cho thư mục con trực tiếp bên ngoài ứng dụng, không quét đệ quy vô hạn.

Spring Boot nhận cả `.properties`, `.yaml` và `.yml`. Nếu cùng một vị trí có đồng thời file `.properties` và YAML cho cùng tên ứng dụng, **file `.properties` được ưu tiên**. Để tránh khó đoán nguồn gốc, nên thống nhất một định dạng cho cùng một ứng dụng.

Không cần khai báo `spring.config.location` chỉ để Spring nhận ra `./config/application.yml`: vị trí này đã có trong đường dẫn tìm kiếm mặc định.

## 4. Thứ tự ưu tiên giữa packaged, external và profile

Trong **riêng nhóm Config Data** (bỏ qua các cơ chế nhập file tùy chỉnh), các nhóm file được xét theo thứ tự từ **ưu tiên thấp đến ưu tiên cao**:

1. File `application.*` đóng gói trong JAR.
2. File `application-{profile}.*` đóng gói trong JAR.
3. File `application.*` bên ngoài JAR.
4. File `application-{profile}.*` bên ngoài JAR.

Nguồn ưu tiên cao hơn ghi đè **theo từng khóa**, không thay thế toàn bộ file cấu hình. Khóa không có trong file bên ngoài vẫn có thể nhận giá trị mặc định từ file đóng gói.

Xét bốn file đều định nghĩa `server.port`:

| Nguồn | Nội dung | Mức ưu tiên |
| --- | --- | --- |
| `classpath:/application.yml` | `server.port: 8080` | Thấp nhất |
| `classpath:/application-prod.yml` | `server.port: 8081` | Cao hơn mặc định đóng gói |
| `file:./config/application.yml` | `server.port: 9080` | Cao hơn mọi file đóng gói ở ví dụ này |
| `file:./config/application-prod.yml` | `server.port: 9180` | Cao nhất trong bốn file |

Khi kích hoạt profile `prod`, kết quả là **9180**. Nếu xóa file `./config/application-prod.yml`, kết quả trở thành **9080**, chứ không phải 8081: file mặc định **bên ngoài** vẫn được ưu tiên hơn file theo profile **đóng gói**.

Nếu không kích hoạt `prod`, chỉ các file chung được sử dụng trong ví dụ này; kết quả sẽ là **9080**.

Khi kích hoạt nhiều profile, chẳng hạn `prod,live`, file theo profile được áp dụng theo nguyên tắc **profile sau có thể ghi đè profile trước**, xét trong cùng nhóm vị trí. Việc nhóm các vị trí lại bằng `;` trong `spring.config.location` có thể ảnh hưởng đến thứ tự này; không nên suy luận đơn giản rằng tên file có chữ `prod` luôn thắng mọi nguồn khác.

## 5. Ví dụ chạy ứng dụng với cấu hình trong và ngoài JAR

Giả sử dự án có file **`src/main/resources/application.yml`**:

~~~yaml
spring:
  application:
    name: order-service
server:
  port: 8080
app:
  greeting: "Xin chào từ cấu hình đóng gói"
  notification:
    enabled: false
  request-timeout: 3s
~~~

Tạo file bên ngoài tại **`/deploy/order-service/config/application.yml`**:

~~~yaml
server:
  port: 9090
app:
  notification:
    enabled: true
  request-timeout: 5s
~~~

Và file **`/deploy/order-service/config/application-prod.yml`**:

~~~yaml
server:
  port: 9191
app:
  request-timeout: 10s
~~~

Giả sử `order-service.jar` nằm tại `/deploy/order-service/order-service.jar`. Chạy từ đúng thư mục triển khai:

~~~bash
cd /deploy/order-service
java -jar order-service.jar --spring.profiles.active=prod
~~~

Khi đó các thuộc tính có hiệu lực là:

| Thuộc tính | Giá trị cuối cùng | Nguồn thắng |
| --- | --- | --- |
| `spring.application.name` | `order-service` | `application.yml` đóng gói |
| `app.greeting` | `Xin chào từ cấu hình đóng gói` | `application.yml` đóng gói |
| `app.notification.enabled` | `true` | `./config/application.yml` |
| `server.port` | `9191` | `./config/application-prod.yml` |
| `app.request-timeout` | `10s` | `./config/application-prod.yml` |

Ví dụ thể hiện hai hành vi: giá trị ngoài JAR ghi đè khi cùng khóa, còn những khóa không được khai báo lại vẫn lấy từ cấu hình đóng gói.

Nếu chạy từ một working directory khác, chẳng hạn `/tmp`, đường dẫn mặc định `./config/` sẽ trỏ tới `/tmp/config/`. Muốn tránh phụ thuộc vị trí chạy, hãy dùng đường dẫn tuyệt đối với `spring.config.additional-location`.

## 6. Thay đổi cách tìm cấu hình

### 6.1. `spring.config.name`: đổi tên file cơ sở

Mặc định Spring tìm các file tên `application`. Có thể đổi sang `service-config`:

~~~bash
java -jar order-service.jar --spring.config.name=service-config
~~~

Khi đó, Spring tìm `service-config.properties`, `service-config.yml`, `service-config-prod.yml`... trong các vị trí cấu hình tương ứng.

### 6.2. `spring.config.location`: thay thế danh sách vị trí mặc định

~~~bash
java -jar order-service.jar --spring.config.location=optional:file:/etc/order-service/
~~~

Giá trị trên yêu cầu Spring tìm cấu hình theo vị trí được chỉ định **thay cho các vị trí mặc định**. Nếu vẫn muốn nạp các giá trị mặc định trong JAR, phải đưa vị trí classpath cần thiết vào danh sách hoặc chọn `spring.config.additional-location`.

Khi trỏ đến **thư mục**, đường dẫn nên kết thúc bằng dấu `/`, vì Spring sẽ ghép tên file từ `spring.config.name` vào đó. Khi trỏ đến **file cụ thể**, Spring đọc file đó trực tiếp.

Nhiều vị trí có thể cách nhau bằng dấu phẩy. Vị trí được khai báo sau có thể ghi đè vị trí trước. Dấu chấm phẩy `;` dùng để đưa các vị trí vào **cùng một location group** khi cần kiểm soát thứ tự nạp file theo profile.

### 6.3. `spring.config.additional-location`: bổ sung vị trí bên ngoài

Đây là lựa chọn phổ biến khi muốn **giữ cấu hình mặc định đóng gói** và cho phép môi trường triển khai ghi đè:

~~~bash
java -jar order-service.jar --spring.config.additional-location=optional:file:/etc/order-service/
~~~

Spring vẫn tìm các vị trí mặc định, sau đó tìm thêm `/etc/order-service/`. Giá trị từ vị trí bổ sung có thể ghi đè giá trị trong các nguồn Config Data mặc định.

Vì `spring.config.name`, `spring.config.location` và `spring.config.additional-location` quyết định **nơi** phải tải dữ liệu, chúng được xử lý **rất sớm** khi ứng dụng khởi động. Hãy cung cấp chúng bằng đối số dòng lệnh, biến môi trường (ví dụ `SPRING_CONFIG_ADDITIONAL_LOCATION`) hoặc Java system property. Đừng đặt `spring.config.location` vào chính file mà bạn hy vọng nó sẽ giúp Spring khám phá.

### 6.4. `optional:`: vị trí có thể không tồn tại

Nếu cấu hình một vị trí bắt buộc mà Spring không tìm thấy, ứng dụng có thể dừng với `ConfigDataLocationNotFoundException`. Thêm tiền tố `optional:` để cho phép vắng mặt:

~~~bash
java -jar order-service.jar --spring.config.additional-location=optional:file:/etc/order-service/
~~~

Tiền tố này chỉ nói rằng **thiếu vị trí đó thì không phải lỗi khởi động**; nó không tạo giá trị mặc định cho các khóa bắt buộc. Nếu application cần một URL hay mật khẩu để chạy, vẫn phải cung cấp hoặc kiểm tra giá trị đó.

## 7. Nhập cấu hình khác bằng `spring.config.import`

Ngoài các vị trí tự tìm, một file cấu hình có thể khai báo thêm nguồn nhập:

~~~yaml
# src/main/resources/application.yml
spring:
  config:
    import: "optional:file:/etc/order-service/feature-flags.yml"
app:
  notification:
    enabled: false
~~~

Và `/etc/order-service/feature-flags.yml`:

~~~yaml
app:
  notification:
    enabled: true
~~~

Nếu file nhập tồn tại, giá trị `app.notification.enabled` thành **true**: tài liệu được import có quyền ưu tiên hơn tài liệu khai báo import. Nếu không có file đó, `optional:` cho phép tiếp tục khởi động và giá trị mặc định **false** vẫn áp dụng.

Một số quy tắc cần biết:

- `spring.config.import` có thể có nhiều vị trí; các import sau có thể ghi đè import trước.
- Mỗi tài nguyên chỉ được import một lần, dù được tham chiếu lặp lại.
- Vị trí bắt đầu bằng `file:`, `classpath:` hoặc `/` được hiểu là vị trí cố định; đường dẫn tương đối không có các tiền tố này có thể được giải quyết tương đối so với file khai báo import.
- Spring Boot cũng xét các biến thể theo profile của file được import khi thích hợp.

Trong môi trường dùng volume mount như Kubernetes, có thể import một **configuration tree**: mỗi tên file trở thành khóa cấu hình, còn nội dung file là giá trị.

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
~~~

Ví dụ file `/run/secrets/db.password` có thể tạo thuộc tính `db.password`. Với bí mật triển khai, cần giới hạn quyền truy cập volume và tránh đưa nội dung bí mật vào log.

**Phân biệt:** `spring.config.additional-location` bổ sung **nơi Spring tự tìm các file cấu hình tên chuẩn**; `spring.config.import` được khai báo **trong một tài liệu cấu hình** để nhập tài nguyên cụ thể.

## 8. Thứ tự ưu tiên của các nguồn ngoài Config Data

Không phải mọi giá trị cuối cùng đều do một trong các file `application.*` quyết định. Trong ứng dụng Spring Boot thông thường, những nguồn dưới đây có thể ghi đè giá trị từ Config Data:

| Nguồn | Ví dụ thiết lập `server.port` | Mức ưu tiên tương đối |
| --- | --- | --- |
| Config Data | `server.port: 9090` trong `application.yml` | Thấp hơn ba nguồn sau |
| Biến môi trường OS | `SERVER_PORT=7070` | Cao hơn Config Data |
| Java system property | `-Dserver.port=6060` | Cao hơn biến môi trường |
| Đối số chương trình | `--server.port=5050` | Cao hơn Java system property |

Ví dụ:

~~~bash
java -Dserver.port=6060 -jar order-service.jar --server.port=5050
~~~

Nếu lệnh này không có một nguồn đặc biệt khác có ưu tiên cao hơn, cổng cuối cùng là **5050** vì đối số `--server.port=5050` được ưu tiên hơn các file Config Data và Java system property.

Thứ tự trên là **đoạn thường gặp** của hệ thống `PropertySource`; Spring Boot còn có các nguồn dành cho test, Devtools, cấu hình JSON hay môi trường servlet. Không suy luận rằng file ngoài JAR có thể ghi đè mọi thứ. Một biến môi trường được triển khai sẵn như `SERVER_PORT` có thể giải thích vì sao sửa `application.yml` mà ứng dụng vẫn dùng cổng cũ.

## 9. Đọc giá trị cấu hình trong mã Java

Có thể lấy thuộc tính đơn lẻ bằng `@Value`:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class GreetingService {
    private final String greeting;

    public GreetingService(@Value("${app.greeting}") String greeting) {
        this.greeting = greeting;
    }

    public String message() {
        return greeting;
    }
}
~~~

Với một nhóm thuộc tính có cấu trúc, nên dùng `@ConfigurationProperties` để ánh xạ sang kiểu dữ liệu rõ ràng. Ví dụ:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import java.time.Duration;

@ConfigurationProperties(prefix = "app")
public record AppProperties(
        String greeting,
        Duration requestTimeout,
        Notification notification
) {
    public record Notification(boolean enabled) {}
}
~~~

Kích hoạt quét các lớp cấu hình trong ứng dụng:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Spring Boot kết hợp các nguồn theo thứ tự ưu tiên rồi bind giá trị vào `AppProperties`. Ví dụ `10s` được chuyển thành `Duration`; `app.notification.enabled` trở thành `boolean`. Phần quan trọng ở bài này là **nơi giá trị đến từ và tại sao nó thắng**, còn cách thiết kế/validate cấu hình có kiểu là một chủ đề tiếp theo.

## 10. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra/xử lý |
| --- | --- | --- |
| Sửa `./config/application.yml` nhưng không thấy thay đổi | Chạy JAR từ working directory khác | In working directory lúc khởi động; dùng đường dẫn tuyệt đối qua `spring.config.additional-location` |
| File trong JAR không được nạp | Đã đặt `spring.config.location` nên thay thế default search locations | Dùng `spring.config.additional-location` hoặc khai báo rõ classpath trong `location` |
| Khởi động lỗi `ConfigDataLocationNotFoundException` | File/thư mục được chỉ định không tồn tại | Kiểm tra đường dẫn, mount, quyền đọc; dùng `optional:` nếu thật sự tùy chọn |
| `application-prod.yml` không có hiệu lực | Profile `prod` chưa kích hoạt hoặc có nguồn khác ưu tiên hơn | Kiểm tra `spring.profiles.active`, file ngoài JAR, biến môi trường và đối số CLI |
| Thay file cấu hình nhưng giá trị vẫn bất ngờ | Một nguồn cùng khóa có ưu tiên cao hơn, hoặc vừa có `.properties` vừa có YAML cùng vị trí | Liệt kê từng nơi khai báo khóa và thứ tự ưu tiên; chọn một định dạng file |
| Đã cập nhật file ngoài JAR nhưng ứng dụng đang chạy vẫn dùng giá trị cũ | Config Data thường được đọc khi khởi động | Khởi động lại hoặc dùng cơ chế refresh cấu hình được thiết kế riêng nếu hệ thống hỗ trợ |
| Lộ URL/token/password | Đưa secret vào `application.yml` đã commit hoặc log toàn bộ `Environment` | Đưa secret qua kênh quản lý bí mật phù hợp, giới hạn quyền truy cập và không in secret ra log |

Khi cần điều tra một thuộc tính, hãy kiểm tra **giá trị đang có** và **nguồn đóng góp**. Nếu dự án bật Spring Boot Actuator, các endpoint `env` và `configprops` có thể hỗ trợ chẩn đoán; chỉ sử dụng với quyền truy cập phù hợp và cấu hình che dữ liệu nhạy cảm.

## 11. Bài tập tự kiểm tra

**Bài 1 — Giá trị mặc định và ghi đè**

Trong JAR có:

~~~properties
server.port=8080
app.color=blue
~~~

Ngoài JAR tại `./config/application.properties` có:

~~~properties
server.port=9090
~~~

Ứng dụng được chạy ở đúng thư mục chứa `config/`, không có profile hay override khác. Hãy xác định `server.port` và `app.color`.

**Đáp án:** `server.port=9090` lấy từ file bên ngoài; `app.color=blue` giữ giá trị đóng gói vì file ngoài không khai báo khóa này.

**Bài 2 — Profile không bảo đảm thắng external mặc định**

Trong JAR: `application-prod.yml` đặt `server.port=8081`. File ngoài: `./config/application.yml` đặt `server.port=9080`. Kích hoạt `prod` và không có override khác. Cổng nào được sử dụng?

**Đáp án:** **9080**, vì Config Data ngoài JAR (không đặc thù profile) có ưu tiên cao hơn Config Data theo profile nhưng đóng gói trong JAR.

**Bài 3 — Chọn cơ chế nạp file**

Bạn muốn JAR luôn giữ `application.yml` làm bộ mặc định; mỗi môi trường có thêm thư mục `/etc/order-service/`. Thư mục có thể vắng mặt ở máy lập trình viên. Hãy chọn một thuộc tính và đưa ra lệnh chạy.

**Đáp án gợi ý:**

~~~bash
java -jar order-service.jar --spring.config.additional-location=optional:file:/etc/order-service/
~~~

Lệnh bổ sung đường dẫn ngoài, giữ các vị trí mặc định và cho phép thư mục ngoài không tồn tại.

## 12. Ghi nhớ khi triển khai

- Cấu hình đóng gói trong JAR dùng làm **mặc định có thể chạy được**; cấu hình bên ngoài dùng để **thay đổi theo môi trường**.
- Thứ tự trong riêng Config Data là **packaged chung → packaged theo profile → external chung → external theo profile**; các nguồn như biến môi trường và CLI có thể ưu tiên hơn nữa.
- **Working directory** quyết định ý nghĩa của `./config/`.
- Dùng `spring.config.additional-location` để bổ sung vị trí tìm; `spring.config.location` để thay danh sách mặc định; `spring.config.import` để nạp tài nguyên khai báo trong một file.
- Chỉ dùng `optional:` khi thật sự cho phép thiếu tài nguyên; đừng dùng nó để che lỗi thiếu cấu hình bắt buộc.
- Giữ secret ra khỏi mã nguồn và kiểm tra nguồn đang ghi đè trước khi kết luận file cấu hình không hoạt động.

**Tài liệu tham khảo:** [Spring Boot 3.3 Reference — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

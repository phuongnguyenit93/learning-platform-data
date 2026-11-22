# Đọc log khởi động để xác định endpoint được công bố

Khi ứng dụng Spring Boot khởi động, bạn có thể thấy dòng:

```text
Exposing 3 endpoints beneath base path '/actuator'
```

Dòng này là bằng chứng hữu ích về việc công bố các điểm truy cập quản trị Actuator qua web. Để dùng đúng, cần đọc cùng phiên bản chạy, cấu hình, cổng và trạng thái khởi động cuối cùng; sau đó xác minh tên endpoint bằng đường khám phá hoặc phản hồi HTTP.

Bài học dùng Spring Boot 3.3, với thí nghiệm cố định ở 3.3.5. Mục tiêu là đi từ một dòng log tới câu trả lời có bằng chứng: **có bao nhiêu endpoint được công bố, chúng nằm dưới đường dẫn nào, và làm sao xác định đường truy cập thực tế**.

## 1. Dòng log nói điều gì?

Ví dụ dưới đây rút gọn phần trình bày để giữ mức log, tên logger và thông điệp:

```text
INFO org.springframework.boot.actuate.endpoint.web.EndpointLinksResolver : Exposing 3 endpoints beneath base path '/actuator'
```

Trong Spring Boot 3.3.5, `EndpointLinksResolver` ghi thông điệp tại mức `INFO`, dùng số phần tử của tập endpoint được truyền cho nó và đường dẫn gốc tương ứng. Có thể đối chiếu [mã nguồn chính thức EndpointLinksResolver tại v3.3.5](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.5/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/endpoint/web/EndpointLinksResolver.java).

| Phần cần đọc | Ý nghĩa trong ví dụ |
| --- | --- |
| `INFO` | Mức ghi của thông điệp |
| `EndpointLinksResolver` | Thành phần tạo thông điệp liên quan tới liên kết endpoint web |
| `3 endpoints` | Số endpoint trong tập được công bố tại cấu hình này |
| `base path '/actuator'` | Đường dẫn gốc dành cho các endpoint, chưa phải toàn bộ URL |

**Endpoint** ở đây là một khả năng quản trị có định danh, chẳng hạn `health` hoặc `metrics`. Một endpoint có thể có nhiều thao tác hoặc đường dẫn con.

### 1.1. Không dùng số lượng để đoán tên

Từ số 3, bạn chưa biết chắc đó là `health`, `info`, `metrics`. Một ứng dụng khác có thể có ba endpoint khác hoặc có endpoint tùy chỉnh.

Cũng không được hiểu đây là:

- Tổng số API nghiệp vụ của ứng dụng.
- Tổng số URL hoặc phương thức HTTP.
- Tổng số bean trong Spring.
- Số endpoint JMX.
- Số chức năng mà người gọi hiện tại có quyền sử dụng.

Trong thí nghiệm phía dưới, một endpoint `health` có thể tạo cả liên kết health và liên kết có đường dẫn con. Số mục trong `_links` vì vậy có thể khác số endpoint.

### 1.2. Dòng này chưa xác nhận toàn bộ ứng dụng đã sẵn sàng

Thông điệp công bố endpoint được tạo trong quá trình khởi tạo. Nếu một bước sau đó thất bại, nó vẫn có thể đã xuất hiện trong log.

Đừng dừng đọc ngay tại chữ `Exposing`. Cần xem thông tin máy chủ đã khởi động, thông tin ứng dụng khởi động xong và có lỗi nào xảy ra sau đó không. Spring Boot có cơ chế báo lỗi khởi động; tham khảo [SpringApplication — Startup Failure](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.startup-failure).

Ví dụ chuỗi sự kiện minh họa, không phải một bản log nguyên văn:

```text
Đã cấu hình tập endpoint web
        ↓
Máy chủ gặp lỗi khi hoàn tất khởi động
        ↓
Ứng dụng dừng khởi động
```

Lúc này, thông tin tập endpoint giúp hiểu cấu hình đã đi tới đâu, nhưng không chứng minh URL đang phục vụ được.

## 2. Đọc theo đúng tiến trình và đúng lần khởi động

Log đầy đủ thường có thời gian, mức ghi, mã tiến trình, tên luồng và tên logger. Tên logger có thể được rút gọn để vừa định dạng hiển thị. Cách trình bày thay đổi khi dùng cấu hình logging riêng. Xem [Spring Boot 3.3 — Logging](https://docs.spring.io/spring-boot/3.3/reference/features/logging.html).

Khi tìm dòng công bố endpoint, thực hiện theo thứ tự:

1. Xác định ứng dụng và lần khởi động đang kiểm tra.
2. Ghi lại profile được kích hoạt và phiên bản phần mềm nếu có trong log.
3. Tìm thông điệp chứa `Exposing` và `beneath base path`.
4. Đọc cổng, đường dẫn ngữ cảnh và các thông tin máy chủ liên quan.
5. Đọc tiếp tới kết quả khởi động cuối cùng.
6. Xác minh HTTP từ vị trí có quyền và có đường mạng phù hợp.

Nếu log của nhiều tiến trình hoặc nhiều lần khởi động được gộp chung, đừng ghép số endpoint của tiến trình A với cổng của tiến trình B. Với khởi động lại trong môi trường phát triển, luôn kiểm tra những dòng thuộc lần chạy mới nhất đang còn hoạt động.

### 2.1. Tìm trong một tệp log có sẵn

Trên PowerShell, có thể lọc những dòng cần đọc:

```powershell
Select-String -Path ".\startup.log" -Pattern "Exposing .* endpoint","beneath base path","Tomcat started","Started ","APPLICATION FAILED TO START"
```

`startup.log` là tên tệp ví dụ. Lệnh chỉ đọc, không tự tạo tệp hoặc bật lưu log. Các thông điệp máy chủ có thể khác nếu dùng Netty, Jetty hoặc Undertow; đừng lấy từ khóa Tomcat làm điều kiện duy nhất.

Kết quả lọc là điểm bắt đầu. Khi thấy lỗi, mở phần log xung quanh để đọc nguyên nhân và thời điểm; đừng chỉ giữ các dòng thành công.

### 2.2. Khi không thấy dòng công bố

Không thấy thông điệp chưa đủ để kết luận không có Actuator. Có thể:

- Mức log đang chặn `INFO` của logger liên quan.
- Log được chuyển sang tệp hoặc hệ thống tập trung.
- Ứng dụng dừng trước khi tới phần cấu hình đó.
- Ứng dụng không có hạ tầng web tương ứng.
- Phiên bản hoặc cấu hình logging có cách trình bày khác.
- Bạn đang xem sai tiến trình hoặc chỉ xem một đoạn log.

Nếu cần trong môi trường kiểm tra, có thể đặt mức ghi riêng:

```properties
logging.level.org.springframework.boot.actuate.endpoint.web.EndpointLinksResolver=INFO
```

Thuộc tính phải được áp dụng trước lần khởi động mà bạn muốn quan sát. Đổi mức ghi sau khi dòng khởi động đã bị bỏ qua không làm dòng quá khứ tự xuất hiện trở lại.

## 3. Những điều quyết định endpoint được công bố

Trước khi diễn giải số lượng, phân biệt ba việc:

| Việc cần xét | Ví dụ câu hỏi |
| --- | --- |
| Khả năng tồn tại của tính năng | Có dependency và các thành phần cần thiết chưa? |
| Bật và công khai endpoint | Endpoint được bật, có nằm trong chính sách công khai qua web không? |
| Cho phép bên gọi truy cập | Người gọi có quyền và đi đúng đường mạng không? |

Trong Spring Boot 3.3, mặc định chỉ `health` được công khai qua HTTP. Có thể chọn danh sách bằng `management.endpoints.web.exposure.include`; các mục trong `exclude` có thể loại endpoint khỏi danh sách. Điểm truy cập cần thêm thư viện không tự xuất hiện chỉ vì tên được viết trong `include`. Xem [Spring Boot 3.3 — Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

Ví dụ với ứng dụng có đủ thành phần tương ứng:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics"
```

Trong cấu hình thử nghiệm sạch ở phần 4, lựa chọn này tạo thông điệp công bố ba endpoint. Với ứng dụng thực tế, hãy xác minh lại các điều kiện và cấu hình hiệu lực thay vì coi con số đó là mặc định chung.

### 3.1. Danh sách cấu hình chưa phải kết quả hiệu lực

Bạn có thể viết cấu hình trong YAML, properties, biến môi trường hoặc tham số dòng lệnh. Spring Boot kết hợp các nguồn theo thứ tự ưu tiên; một nguồn khác có thể làm giá trị hiệu lực khác tệp bạn đang đọc. Xem [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

Vì vậy, nếu tệp ghi ba endpoint nhưng log chỉ báo một, hãy kiểm tra profile, tham số khởi động và điều kiện tính năng. Chưa có cơ sở để công khai toàn bộ endpoint.

### 3.2. Có thể công khai nhưng không được phép gọi

Dòng công bố không mô tả chính sách xác thực của từng người dùng. Khi dùng Spring Security, một endpoint có thể đã được ánh xạ nhưng yêu cầu quyền mà bên gọi chưa có.

Đây là lý do cần ghi riêng hai kết quả: cấu hình công bố từ log và phản hồi truy cập thực tế. Không đổi mọi quyền thành cho phép công khai chỉ để làm một lệnh kiểm tra thành công.

## 4. Thí nghiệm đầy đủ: đọc log rồi xác minh HTTP

Thí nghiệm tạo một ứng dụng nhỏ chỉ có starter web và Actuator, không thêm Spring Security hay API nghiệp vụ. Nó dành cho máy học tập, lắng nghe địa chỉ loopback `127.0.0.1`.

### 4.1. Chuẩn bị dependency

Dùng JDK 17 trở lên và Gradle tương thích. Trong thư mục mới, tạo `settings.gradle`:

```groovy
rootProject.name = 'actuator-startup-log-demo'
```

Tạo `build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.5')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}

tasks.register('copyDemoLibraries', Copy) {
    from configurations.runtimeClasspath
    into layout.projectDirectory.dir('lib')
}
```

Phiên bản cố định phục vụ việc tái lập. Đây là dự án Java dùng BOM để quản lý dependency; lệnh bên dưới chạy trực tiếp class đã biên dịch. Nó không yêu cầu tạo executable JAR.

Dùng thư mục riêng để tránh trộn các cấu hình hoặc thư viện của dự án khác. Nếu thư viện chưa có trong bộ nhớ đệm, Gradle cần kết nối kho Maven.

### 4.2. Mã Java hoàn chỉnh

Tạo `src/main/java/lab/actuator/StartupLogDemo.java`:

```java
package lab.actuator;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StartupLogDemo {
    public static void main(String[] args) {
        SpringApplication.run(StartupLogDemo.class, args);
    }
}
```

Biên dịch tại thư mục gốc của thí nghiệm:

```powershell
gradle copyDemoLibraries
javac -encoding UTF-8 -cp "lib/*" -d out src/main/java/lab/actuator/StartupLogDemo.java
```

Có thể dùng Gradle Wrapper của dự án thử nếu đã có. Trên Linux/macOS, classpath khi chạy dùng `:` thay cho `;`.

### 4.3. Lần chạy A: giữ chính sách công khai mặc định

Trong terminal thứ nhất:

```powershell
java -cp "out;lib/*" lab.actuator.StartupLogDemo --server.address=127.0.0.1 --server.port=8080
```

Thông điệp liên quan mong đợi trong môi trường thử nghiệm sạch:

```text
Exposing 1 endpoint beneath base path '/actuator'
```

Ứng dụng giữ tiến trình chạy để phục vụ HTTP. Ngày giờ, PID, thời gian khởi động và cách rút gọn logger phụ thuộc lần chạy, nên không xem toàn bộ console là một stdout cố định.

Sau khi ứng dụng khởi động thành công, ở terminal thứ hai:

```powershell
curl.exe -i "http://127.0.0.1:8080/actuator"
curl.exe -i "http://127.0.0.1:8080/actuator/health"
curl.exe -i "http://127.0.0.1:8080/actuator/metrics"
```

Trong cấu hình thí nghiệm không có bảo mật bổ sung, đường khám phá và health truy cập được, còn metrics chưa được công khai qua web. Nếu kết quả khác, kiểm tra log và cấu hình thật trước khi kết luận.

Nếu cổng 8080 đã có tiến trình khác sử dụng, chọn một cổng trống rồi sửa đồng bộ các lệnh gọi. Đừng đọc phản hồi từ một ứng dụng cũ và tưởng đó là lần chạy vừa khởi động.

### 4.4. Lần chạy B: công khai ba endpoint cụ thể

Dừng ứng dụng ở terminal thứ nhất bằng `Ctrl+C`, rồi chạy:

```powershell
java -cp "out;lib/*" lab.actuator.StartupLogDemo --server.address=127.0.0.1 --server.port=8080 "--management.endpoints.web.exposure.include=health,info,metrics"
```

Thông điệp liên quan:

```text
Exposing 3 endpoints beneath base path '/actuator'
```

Gọi lại trang khám phá, rồi thử từng đường:

```powershell
curl.exe -i "http://127.0.0.1:8080/actuator"
curl.exe -i "http://127.0.0.1:8080/actuator/health"
curl.exe -i "http://127.0.0.1:8080/actuator/info"
curl.exe -i "http://127.0.0.1:8080/actuator/metrics"
```

Endpoint `info` có thể trả đối tượng rỗng nếu chưa có dữ liệu thông tin để công bố. Endpoint tồn tại và payload có nhiều nội dung là hai điều khác nhau. Xem [Actuator Info REST API 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/info.html).

Với metrics, đọc danh sách tên thực tế thay vì đòi một số đo có giá trị cố định. Cấu trúc API có trong [Actuator Metrics REST API 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

### 4.5. Kết quả đã được kiểm chứng cho hai cấu hình

Với Spring Boot 3.3.5 và ứng dụng thử nghiệm trên, các kiểm tra HTTP cục bộ cho kết quả:

| Cấu hình | Số endpoint trong log | Trang khám phá | Health | Metrics |
| --- | --- | --- | --- | --- |
| Mặc định | 1 | 200 | 200 | 404 |
| `health,info,metrics` | 3 | 200 | 200 | 200 |

Bảng nói về cấu hình đã nêu. Một ứng dụng có bảo mật, proxy, điều kiện sức khỏe khác hoặc cấu hình tùy chỉnh có thể trả mã khác; phải ghi nhận và diễn giải mã thật.

Để kết thúc mỗi lần thử, dừng đúng tiến trình vừa chạy. Không cần mở thêm endpoint để hoàn thành thí nghiệm.

## 5. Xác định tên endpoint bằng trang khám phá

Ở đường dẫn gốc Actuator, trang khám phá trả về các liên kết dưới `_links` khi tính năng này được bật và bạn có quyền truy cập.

Ví dụ trích lại một phần các trường liên quan, với địa chỉ của lần chạy B:

```json
{
  "_links": {
    "self": {
      "href": "http://127.0.0.1:8080/actuator",
      "templated": false
    },
    "health": {
      "href": "http://127.0.0.1:8080/actuator/health",
      "templated": false
    }
  }
}
```

Đây không phải toàn bộ phản hồi của lần chạy B. Hãy đọc dữ liệu thật để tìm các liên kết `info`, `metrics` và các đường thao tác khác.

Trang khám phá được mô tả trong [Hypermedia for Actuator Web Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.hypermedia). Các thao tác của từng endpoint có cấu trúc riêng; tham khảo [Actuator REST API 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/index.html).

### 5.1. Vì sao không đếm _links để thay cho số endpoint?

`self` là liên kết tới trang hiện tại. Một endpoint còn có thể cung cấp nhiều thao tác, bao gồm đường có tham số. Do đó, mỗi mục liên kết không nhất thiết là một định danh endpoint riêng.

Trong thí nghiệm Spring Boot 3.3.5 không có bảo mật bổ sung:

| Cấu hình | Số endpoint trong log | Số mục dưới `_links` |
| --- | --- | --- |
| Chỉ health theo mặc định | 1 | 3 |
| `health,info,metrics` | 3 | 6 |

Đây là kết quả quan sát của thí nghiệm, không phải công thức cố định cho mọi ứng dụng. Không suy ra “log báo 3 nhưng JSON có 6 mục là bị công bố dư ba endpoint”.

Khi liên kết có `templated: true`, cần điền tham số đúng theo thao tác; không coi cả chuỗi mẫu là một địa chỉ hoàn chỉnh để gọi nguyên trạng.

### 5.2. Trang khám phá không tồn tại chưa có nghĩa endpoint con bị tắt

Dừng ứng dụng rồi thêm thuộc tính sau vào lệnh lần chạy B:

```text
--management.endpoints.web.discovery.enabled=false
```

Vẫn giữ `health,info,metrics` trong danh sách công khai. Trong thí nghiệm đã kiểm chứng, kết quả là:

| Quan sát | Kết quả |
| --- | --- |
| Log công bố | Vẫn báo 3 endpoint dưới `/actuator` |
| GET `/actuator` | 404 |
| GET `/actuator/health` | 200 |
| GET `/actuator/metrics` | 200 |

Thuộc tính này điều khiển trang khám phá. Nó không đồng nghĩa tắt tất cả endpoint con. Khi trang khám phá không được cung cấp, dùng cấu hình, báo cáo điều kiện hoặc các ánh xạ đã được phép xem để tìm đường cần kiểm tra.

Cũng không nên coi mọi lỗi ở đường gốc là do thuộc tính này. Sai cổng, sai đường dẫn, quyền truy cập hoặc một proxy cũng có thể làm kết quả khác dự kiến.

## 6. Từ base path trong log tới URL đầy đủ

Dòng `base path '/actuator'` không chứa giao thức, máy chủ, cổng hoặc toàn bộ đường dẫn ngữ cảnh.

Trong trường hợp Servlet dùng cùng cổng phục vụ và không có proxy, có thể hình dung:

```text
URL endpoint =
giao thức + địa chỉ + cổng
+ context path của ứng dụng
+ base path Actuator
+ đường endpoint sau khi ánh xạ
```

Đây là cách ghép cho trường hợp đã nêu. Khi tách cổng quản trị hoặc có proxy, phải xác định lại các thành phần tương ứng.

### 6.1. Thí nghiệm đổi đường dẫn và ánh xạ health

Dừng ứng dụng rồi chạy:

```powershell
java -cp "out;lib/*" lab.actuator.StartupLogDemo --server.address=127.0.0.1 --server.port=8080 "--management.endpoints.web.exposure.include=health,info,metrics" --server.servlet.context-path=/shop --management.endpoints.web.base-path=/manage --management.endpoints.web.path-mapping.health=status
```

Thông điệp liên quan vẫn chỉ nêu base path:

```text
Exposing 3 endpoints beneath base path '/manage'
```

Các thành phần đường dẫn có vai trò khác nhau:

| Cấu hình | Giá trị | Vai trò |
| --- | --- | --- |
| `server.servlet.context-path` | `/shop` | Đường ngữ cảnh của ứng dụng Servlet |
| `management.endpoints.web.base-path` | `/manage` | Gốc các endpoint Actuator |
| `management.endpoints.web.path-mapping.health` | `status` | Đổi phần đường dẫn của endpoint health |

Vì vậy, các lệnh kiểm tra là:

```powershell
curl.exe -i "http://127.0.0.1:8080/shop/manage"
curl.exe -i "http://127.0.0.1:8080/shop/manage/status"
curl.exe -i "http://127.0.0.1:8080/shop/manage/metrics"
```

Trong thí nghiệm, trang khám phá trả liên kết health với đường `/shop/manage/status`, và các đường kiểm tra tương ứng hoạt động. Định danh endpoint vẫn là `health`; việc đổi phần URL sang `status` không làm nó trở thành một endpoint mới cần viết `status` trong danh sách công khai.

Cơ chế đổi đường và ánh xạ được mô tả trong [Spring Boot 3.3 — Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

### 6.2. Nếu dùng cổng quản trị riêng

Khi `management.server.port` khác cổng ứng dụng, có thể thấy thông tin của nhiều máy chủ trong log. Cần xác định máy chủ nào phục vụ endpoint quản trị; dòng `EndpointLinksResolver` không tự cung cấp cổng đó.

Với cổng quản trị riêng, base path Actuator được xét theo `management.server.base-path`. Không tự lấy `server.servlet.context-path` của máy chủ chính rồi ghép vào cổng quản trị như trường hợp dùng chung cổng.

Hãy ghi riêng:

```text
Cổng phục vụ ứng dụng: 8080.
Cổng phục vụ quản trị: 8081.
Đường gốc quản trị: /ops.
Base path endpoint: /manage.
URL health dự kiến cần kiểm tra: http://127.0.0.1:8081/ops/manage/health.
```

Đây là ghi chép cho một cấu hình minh họa, giả sử health giữ đường mặc định và quản trị dùng HTTP. Nó không phải kết quả của thí nghiệm dùng chung cổng ở phần 4; hãy lấy các giá trị và kết quả kiểm tra từ ứng dụng thật.

### 6.3. Nếu có reverse proxy

Log của ứng dụng phản ánh cấu hình bên trong. Địa chỉ người dùng gọi từ bên ngoài có thể thêm hoặc bỏ một tiền tố đường dẫn, đổi cổng hay dùng HTTPS trong khi đoạn kết nối nội bộ dùng HTTP.

Muốn xác định URL công khai, cần đọc cả cấu hình định tuyến của môi trường và phản hồi từ đường truy cập đó. Không suy ra tên miền công khai chỉ từ một dòng base path trong ứng dụng.

## 7. Dùng thêm bằng chứng khi tên endpoint vẫn chưa rõ

### 7.1. Báo cáo điều kiện cấu hình

Nếu endpoint mong đợi không xuất hiện, tùy chọn `--debug` giúp xem vì sao một cấu hình tự động được áp dụng hoặc không được áp dụng:

```powershell
java -cp "out;lib/*" lab.actuator.StartupLogDemo --server.address=127.0.0.1 --server.port=8080 --debug
```

Ví dụ này chạy lại cấu hình mặc định, không mặc định giữ tham số của lần trước. Nếu muốn chẩn đoán lần chạy B hoặc cấu hình đường dẫn riêng, phải truyền lại các tham số của đúng lần đó.

Tìm cấu hình liên quan tới endpoint cần kiểm tra rồi đọc nguyên nhân. Nhiều điều kiện không khớp là bình thường vì ứng dụng không dùng công nghệ tương ứng. Tham khảo [Spring Boot 3.3 — Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html).

Báo cáo điều kiện trả lời về việc cấu hình, không tự xác nhận người dùng ngoài mạng truy cập thành công.

### 7.2. Thông tin ánh xạ khi đã được phép xem

Endpoint `mappings` có thể cung cấp thông tin ánh xạ yêu cầu khi nó đã được bật, công khai và cho phép truy cập. Nó là một nguồn bổ sung, không phải điều kiện bắt buộc để hoàn thành thí nghiệm tối thiểu.

Nếu sử dụng, đọc đường dẫn và phương thức HTTP cụ thể thay vì chỉ tìm tên bean. Cấu trúc dữ liệu được mô tả trong [Actuator Mappings REST API 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/mappings.html).

Không cần công khai tất cả điểm quản trị hoặc bật `TRACE` toàn ứng dụng để tìm một đường health. Chọn nguồn bằng chứng vừa đủ cho câu hỏi đang điều tra.

## 8. Các tình huống dễ đọc sai

### “Log báo ba endpoint, vậy ba URL tôi đoán đều phải trả 200”

Con số không cho biết tên endpoint. Cần lấy tên từ cấu hình hiệu lực và nguồn khám phá phù hợp, rồi kiểm tra từng thao tác.

Một endpoint có thể trả mã sức khỏe khác khi thành phần được kiểm tra không khỏe. Mục đích của bài không phải ép mọi phản hồi thành 200, mà xác định đúng đường và hiểu đúng kết quả.

### “Tệp cấu hình ghi metrics nhưng log chỉ báo một; chắc thư viện hỏng”

Có thể tệp không được dùng trong profile hiện tại, bị tham số khác thay thế, endpoint bị tắt hoặc điều kiện chưa đủ. Kiểm tra cấu hình hiệu lực và báo cáo điều kiện trước khi thay dependency.

### “Không có dòng Exposing thì Actuator chắc chắn chưa được nạp”

Mức ghi và nơi nhận log có thể làm bạn không thấy dòng đó. Hãy kiểm tra đúng logger, nguồn log và lần khởi động; xác minh trực tiếp theo cấu hình khi có thể.

### “Đã thấy dòng Exposing thì ứng dụng đã chạy xong”

Một bước khởi động sau đó vẫn có thể thất bại. Luôn đọc tiếp trạng thái cuối cùng, rồi kiểm tra từ vị trí thực sự cần sử dụng endpoint.

### “GET đường gốc trả 404 thì mọi endpoint con đều bị tắt”

Trang khám phá có chính sách riêng, như thí nghiệm tắt discovery đã cho thấy. Kiểm tra đường con đã biết và cấu hình tương ứng.

### “Đường gốc trong log là toàn bộ đường URL”

Còn có cổng, đường ngữ cảnh, ánh xạ riêng và có thể có proxy. Trong thí nghiệm đổi đường, log ghi `/manage` nhưng health nằm ở `/shop/manage/status`.

### “Log của một phiên bản chạy đại diện cho toàn bộ dịch vụ”

Các phiên bản chạy có thể dùng cấu hình khác nhau hoặc đang ở các đợt triển khai khác nhau. Khi điều tra, gắn bằng chứng với đúng tiến trình, phiên bản, profile và thời điểm.

## 9. Một quy trình đọc log có thể lặp lại

| Bước | Việc cần làm | Kết quả nên ghi |
| --- | --- | --- |
| 1 | Xác định đúng lần chạy | Ứng dụng, phiên bản, profile và thời điểm |
| 2 | Tìm dòng công bố endpoint | Số lượng và base path đúng nguyên văn |
| 3 | Đọc thông tin máy chủ | Cổng, đường ngữ cảnh và cơ chế phục vụ |
| 4 | Xem kết quả khởi động cuối | Thành công hay lỗi xảy ra sau dòng công bố |
| 5 | Tìm tên endpoint | Liên kết khám phá, cấu hình hoặc ánh xạ phù hợp |
| 6 | Xác minh yêu cầu HTTP | URL, phương thức, mã phản hồi và nội dung cần thiết |
| 7 | Ghi phạm vi kết luận | Đã xác nhận từ vị trí nào, điều gì còn chưa biết |

Ví dụ một ghi chép đã điền theo thí nghiệm đổi đường:

```text
Ứng dụng: StartupLogDemo, Spring Boot 3.3.5.
Tập endpoint: 3, base path /manage.
Ngữ cảnh Servlet: /shop; cổng thử nghiệm: 8080.
Tên health được ánh xạ đường: status.
URL kiểm tra: http://127.0.0.1:8080/shop/manage/status.
Phạm vi: truy cập trực tiếp từ cùng máy, không có Spring Security bổ sung.
```

Ghi thời điểm thật của lần thử bên cạnh ghi chép. Không coi kết quả trên cùng máy là bằng chứng rằng mọi máy bên ngoài đều truy cập được.

### Bài tập tự kiểm tra

1. Với cấu hình mặc định của thí nghiệm, tìm dòng công bố rồi xác định health bằng liên kết thật.
2. Công khai ba endpoint cụ thể, dự đoán số lượng trước khi chạy lại.
3. So sánh số endpoint với số mục `_links` và giải thích vì sao khác nhau.
4. Đổi base path, context path và đường health như ví dụ; ghi URL đầy đủ.
5. Tắt trang khám phá rồi kiểm tra riêng health.
6. Với một log khởi động thất bại, xác định vì sao dòng công bố endpoint chưa đủ để xác nhận dịch vụ đang hoạt động.

Bạn đọc log đúng khi chuyển được một thông điệp khởi động thành giả thuyết có kiểm chứng, đồng thời giữ rõ ranh giới giữa cấu hình công bố, trạng thái ứng dụng và quyền truy cập thực tế.

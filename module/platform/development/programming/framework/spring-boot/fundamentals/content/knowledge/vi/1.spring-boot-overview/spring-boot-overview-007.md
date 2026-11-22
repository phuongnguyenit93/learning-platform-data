# Mã nguồn, cấu hình, dependency và môi trường cùng quyết định hành vi ứng dụng

Một ứng dụng Spring Boot không hoạt động chỉ theo những dòng Java mà lập trình viên viết. Khi chạy, Spring Boot kết hợp **mã nguồn**, **các thư viện có mặt trên classpath**, **cấu hình có hiệu lực** và **điều kiện của môi trường chạy** để tạo ra một ứng dụng cụ thể. Vì vậy, hai lần chạy từ cùng một mã nguồn có thể mở cổng khác nhau, sử dụng cơ sở dữ liệu khác nhau, trả kết quả khác nhau hoặc thậm chí một lần khởi động thành công còn lần kia thất bại.

Trong bức tranh Spring Boot, đây là cách nhìn quan trọng để hiểu vì sao framework có thể tự cấu hình nhiều thành phần và vì sao một lỗi chỉ xuất hiện trên máy khác hoặc ở môi trường triển khai.

## 1. “Hành vi ứng dụng” bao gồm những gì?

Hành vi không chỉ là giá trị trả về từ một phương thức. Với một dịch vụ web Spring Boot, nó có thể bao gồm:

- Ứng dụng có khởi động được hay không, mở cổng nào và đăng ký những HTTP endpoint nào.
- Một request nhận mã trạng thái, header, nội dung phản hồi hoặc thông báo lỗi ra sao.
- Ứng dụng kết nối đến cơ sở dữ liệu, message broker hay dịch vụ ngoài nào.
- Một tính năng được bật hay tắt; bean nào được tạo và bean nào được chọn để xử lý.
- Log được ghi ở mức nào, file được lưu ở đâu, thời gian được diễn giải theo múi giờ nào.
- Ứng dụng phản ứng thế nào khi thiếu biến môi trường, không truy cập được DNS, hết bộ nhớ hoặc gặp giới hạn kết nối.

Có thể hình dung:

~~~text
Mã nguồn + dependency đã được giải quyết
                 |
                 v
          Build ra ứng dụng
                 |
                 v
   Classpath lúc chạy + cấu hình có hiệu lực
                 |
                 v
   Spring Boot khởi tạo ApplicationContext
                 |
                 v
    Bean + auto-configuration + web server
                 |
                 v
      Hành vi khi nhận request/sự kiện
                 ^
                 |
     JVM, hệ điều hành, mạng, DB,
     tài nguyên và dữ liệu bên ngoài
~~~

Sơ đồ là mô hình để suy nghĩ, không phải trình tự tuyệt đối: mã nguồn cũng có thể đọc cấu hình trực tiếp; môi trường có thể tác động ngay trong lúc Spring khởi động; request và dữ liệu thực tế tiếp tục ảnh hưởng đến kết quả sau đó.

## 2. Bốn yếu tố chính và trách nhiệm của từng yếu tố

| Yếu tố | Quyết định điều gì? | Ví dụ điển hình | Thay đổi thường cần gì? |
|---|---|---|---|
| **Mã nguồn (source code)** | Logic nghiệp vụ, endpoint, cấu trúc lớp, bean tự định nghĩa và cách xử lý dữ liệu | `@GetMapping("/hello")`, lớp `@Service`, quy tắc tính giá | Sửa mã, biên dịch và tạo bản build mới |
| **Dependency** | Những API, framework, driver và khả năng tích hợp hiện diện trên classpath; các điều kiện auto-configuration có thể thỏa mãn | Spring MVC, Spring Data JPA, JDBC driver | Cập nhật khai báo dependency, giải quyết phiên bản rồi build lại |
| **Cấu hình (configuration)** | Giá trị được dùng lúc chạy và nhiều lựa chọn bật/tắt thành phần | `server.port`, `spring.profiles.active`, URL database, feature flag | Có thể đổi giá trị cung cấp lúc khởi động mà không sửa Java; thường phải khởi động lại |
| **Môi trường (environment)** | Những điều kiện thực tế mà tiến trình đang chạy trong đó | JDK/JVM, biến môi trường, hệ điều hành, CPU/RAM, network, DNS, quyền file, dịch vụ ngoài | Thay đổi hạ tầng, biến môi trường, tài nguyên, kết nối hoặc quyền truy cập |

Bốn yếu tố có liên hệ chặt chẽ. **Dependency** làm cho một tính năng có khả năng tồn tại; **cấu hình** cung cấp giá trị và điều kiện để sử dụng tính năng đó; **mã nguồn** quyết định ứng dụng dùng tính năng như thế nào; **môi trường** quyết định nó có thể hoạt động trong thực tế hay không.

Ví dụ: thêm thư viện kết nối PostgreSQL không tự tạo ra một database. Cấu hình URL và tài khoản hợp lệ cũng không có tác dụng nếu thiếu driver cần thiết. Dù cả hai đều đúng, ứng dụng vẫn không kết nối được nếu máy chủ database không hoạt động hoặc mạng chặn kết nối.

## 3. Điều gì xảy ra khi một ứng dụng Spring Boot khởi động?

Với ứng dụng Java thông thường, điểm vào là phương thức `main`. Với Spring Boot, điểm vào thường gọi `SpringApplication.run(...)` trong lớp đánh dấu `@SpringBootApplication`.

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Annotation `@SpringBootApplication` kết hợp những khả năng quan trọng: khai báo cấu hình Spring, quét component từ package phù hợp và bật auto-configuration. Khi chạy, Spring Boot xử lý một loạt công việc liên quan:

1. **JVM nạp mã và thư viện.** Các lớp thực sự có thể sử dụng phụ thuộc vào artifact và classpath của tiến trình.
2. **Spring tạo `Environment` và đọc các nguồn cấu hình.** Giá trị có thể đến từ file, profile, biến môi trường, system property hoặc tham số dòng lệnh.
3. **Spring tìm định nghĩa bean.** Component scan nhận ra các lớp như `@Component`, `@Service`, `@Repository`, `@Controller` trong phạm vi quét; các lớp `@Configuration` có thể định nghĩa bean rõ ràng.
4. **Auto-configuration đánh giá điều kiện.** Spring Boot xem xét class có tồn tại, bean đã được người dùng cung cấp chưa, property nào được đặt và các điều kiện khác trước khi tạo cấu hình mặc định phù hợp.
5. **ApplicationContext khởi tạo bean và dịch vụ cần thiết.** Nếu là ứng dụng web với stack phù hợp, quá trình này bao gồm việc khởi động web server.
6. **Ứng dụng xử lý tác vụ thực tế.** Khi có HTTP request, Spring MVC (nếu có) định tuyến đến controller; mã nghiệp vụ sử dụng các bean, giá trị cấu hình và dịch vụ ngoài.

Vì vậy, `@SpringBootApplication` không đồng nghĩa với việc “bật tất cả khả năng của Spring”. Auto-configuration là **cấu hình có điều kiện**: khi thiếu một thư viện, thiếu một bean cần thiết hoặc không thỏa điều kiện, kết quả có thể khác.

Một khái niệm rất đáng nhớ là **classpath**: tập hợp các lớp và thư viện mà ứng dụng có thể nạp trong một lần chạy. Dependency được khai báo trong Maven/Gradle góp phần quyết định classpath, nhưng chỉ những artifact thực sự được giải quyết và đưa vào runtime classpath mới tác động trực tiếp đến tiến trình đang chạy.

## 4. Ví dụ xuyên suốt: cùng một endpoint, nhiều hành vi khác nhau

Xét một ứng dụng Spring Boot dùng Spring MVC. Ví dụ dưới đây minh họa cách tổ chức thường gặp ở Spring Boot 3.x với Java 17 trở lên; tên starter có thể khác giữa các phiên bản lớn nên cần đối chiếu phiên bản dự án đang sử dụng.

### 4.1. Dependency cung cấp khả năng chạy HTTP

Một dự án Maven có thể khai báo dependency sau trong file `pom.xml`, khi đã có cơ chế quản lý phiên bản Spring Boot thích hợp:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

Spring Boot starter thường gom các thư viện cần thiết cho một mục đích. Với starter web truyền thống ở Spring Boot 3.x, đó là các thành phần phục vụ Spring MVC, JSON và embedded servlet server. Các thư viện bên dưới được kéo vào theo quan hệ **transitive dependency**, nên không phải khai báo từng thư viện một.

Nếu thiếu web stack phù hợp, mã có `@RestController` thôi chưa đủ để tạo ra một HTTP server hoạt động. Ngược lại, chỉ thêm starter cũng chưa tạo ra endpoint `/hello`: endpoint đó đến từ mã nguồn.

### 4.2. Mã nguồn định nghĩa endpoint và cách sử dụng cấu hình

Đặt controller trong package `com.example.demo` hoặc package con để nằm trong phạm vi component scan của lớp `DemoApplication`.

~~~java
package com.example.demo;

import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    private final String greeting;

    public GreetingController(@Value("${app.greeting}") String greeting) {
        this.greeting = greeting;
    }

    @GetMapping("/hello")
    public Map<String, String> hello() {
        return Map.of("message", greeting);
    }
}
~~~

Ở đây:

- `@RestController` giúp Spring MVC nhận diện lớp xử lý request và ghi kết quả vào HTTP response.
- `@GetMapping("/hello")` xác định đường dẫn và phương thức HTTP GET.
- `@Value("${app.greeting}")` yêu cầu Spring lấy giá trị property `app.greeting` từ cấu hình có hiệu lực rồi truyền vào constructor.
- Phương thức `hello()` quyết định hình dạng dữ liệu trả về; bộ chuyển đổi JSON của web stack tuần tự hóa `Map` thành JSON.

Phần **mã nguồn** xác định rằng GET `/hello` trả về một JSON object có khóa `message`. Phần **cấu hình** quyết định chuỗi message cụ thể.

### 4.3. Cấu hình mặc định cung cấp giá trị

Tạo file `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

app:
  greeting: "Xin chào từ cấu hình mặc định"
~~~

Sau khi chạy ứng dụng, truy cập:

~~~http
GET http://localhost:8080/hello
~~~

Kết quả dự kiến:

~~~json
{
  "message": "Xin chào từ cấu hình mặc định"
}
~~~

Cổng `8080` là giá trị đã đặt trong YAML và cũng là cổng mặc định thường gặp ở ứng dụng servlet Spring Boot khi chưa có cấu hình khác. Nếu controller vẫn giữ nguyên mà `app.greeting` đổi, response thay đổi theo giá trị được nạp khi khởi động.

### 4.4. Profile chọn cấu hình cho môi trường phát triển

Tạo thêm file `src/main/resources/application-dev.yml`:

~~~yaml
app:
  greeting: "Xin chào từ môi trường dev"
~~~

Khi chạy bản JAR đã build với profile `dev`:

~~~bash
java -jar target/ten-ung-dung.jar --spring.profiles.active=dev
~~~

Response dự kiến của GET `/hello`:

~~~json
{
  "message": "Xin chào từ môi trường dev"
}
~~~

Ở đây, `application.yml` cung cấp nền tảng chung; `application-dev.yml` bổ sung hoặc ghi đè property tương ứng khi profile `dev` được kích hoạt. Không cần viết thêm nhánh `if (dev)` trong controller để lấy lời chào khác nhau.

**Phân biệt:** Spring profile chọn nhóm bean/cấu hình theo điều kiện runtime. Maven profile hoặc cơ chế build tương tự có thể thay đổi cách build và dependency, là một khái niệm khác. Spring profile tự nó không thay thế artifact hay thêm thư viện vào JAR.

### 4.5. Biến môi trường và tham số chạy ghi đè giá trị

Trên một shell kiểu Bash, có thể chạy cùng JAR với:

~~~bash
APP_GREETING="Xin chào từ biến môi trường" SERVER_PORT=9090 java -jar target/ten-ung-dung.jar --spring.profiles.active=dev
~~~

Trong Spring Boot, cách ánh xạ tên biến môi trường thường dùng cho property này là `APP_GREETING` tương ứng `app.greeting`, còn `SERVER_PORT` tương ứng `server.port`. Khi đó request đến `http://localhost:9090/hello` trả về lời chào từ biến môi trường.

Ví dụ tương đương với PowerShell:

~~~powershell
$env:APP_GREETING = "Xin chào từ biến môi trường"
$env:SERVER_PORT = "9090"
java -jar target/ten-ung-dung.jar --spring.profiles.active=dev
~~~

Các lệnh trên chỉ minh họa cách cung cấp cấu hình cho **tiến trình được khởi động**. Tên `ten-ung-dung.jar` là chỗ giữ chỗ, cần thay bằng tên artifact thực tế sau khi build. Việc sửa file cấu hình đóng gói trong JAR hoặc sửa biến môi trường sau khi ứng dụng đã khởi động thường không tự cập nhật bean đang chạy; cần cơ chế refresh rõ ràng hoặc khởi động lại.

Có thể đặt tiếp một tham số dòng lệnh:

~~~bash
java -jar target/ten-ung-dung.jar --server.port=9191
~~~

Với nguồn property mặc định phổ biến của Spring Boot, tham số dòng lệnh `--server.port=9191` sẽ có độ ưu tiên cao hơn giá trị `SERVER_PORT` nếu cả hai cùng hiện diện và không bị ứng dụng tùy biến cơ chế đọc tham số.

### 4.6. So sánh các lần chạy

Giả sử tất cả lần chạy đều dùng cùng mã Java và cùng artifact JAR chứa controller trên:

| Lần chạy | Profile | Nguồn `app.greeting` có hiệu lực | Cổng | Kết quả của `GET /hello` |
|---|---|---|---|---|
| Mặc định | Không có `dev` | `application.yml` | 8080 | “Xin chào từ cấu hình mặc định” |
| Phát triển | `dev` | `application-dev.yml` | 8080 | “Xin chào từ môi trường dev” |
| Phát triển có biến môi trường | `dev` | `APP_GREETING` | 9090 qua `SERVER_PORT` | “Xin chào từ biến môi trường” |

Bảng này chỉ so sánh các giá trị được nêu trong ví dụ, giả định không có nguồn cấu hình nào khác ghi đè chúng. Nó minh họa một nguyên tắc: **giữ nguyên mã nguồn và dependency nhưng thay cấu hình hoặc môi trường vẫn có thể thay đổi hành vi**.

## 5. “Cấu hình có hiệu lực” khác với một file cấu hình

Trong dự án thực tế, chỉ mở `application.yml` rồi đọc một giá trị có thể dẫn đến kết luận sai. Spring Boot có thể nhận cùng một khóa property từ nhiều nguồn. Giá trị mà ứng dụng nhìn thấy là kết quả sau khi áp dụng những quy tắc nạp và ưu tiên nguồn cấu hình.

Các nguồn thường gặp:

- `application.yml` hoặc `application.properties` nằm trong ứng dụng hay tại vị trí cấu hình bên ngoài.
- Các file theo profile như `application-dev.yml`, `application-prod.properties`.
- Biến môi trường của hệ điều hành hoặc container, ví dụ `SPRING_PROFILES_ACTIVE=prod`.
- Java system property, ví dụ `-Dserver.port=9090` đặt trước `-jar`.
- Tham số ứng dụng trên dòng lệnh, ví dụ `--server.port=9191`.
- Các nguồn bổ sung được khai báo bằng cơ chế nạp cấu hình hoặc được mã nguồn đăng ký.

Với các nguồn phổ biến trong cấu hình Spring Boot thông thường, tham số dòng lệnh có ưu tiên cao hơn Java system property, Java system property cao hơn biến môi trường, và biến môi trường cao hơn file `application.yml`. Nhưng đây **không phải toàn bộ bảng thứ tự property source**: vị trí file ngoài, file theo profile, import, tài liệu kiểm thử, code tùy biến và những nguồn khác đều có quy tắc riêng. Khi cần xác định chính xác một property, phải xem các nguồn thực tế đã được nạp và thứ tự ưu tiên của phiên bản Spring Boot đang dùng.

### Profile là cách chọn ngữ cảnh cấu hình

Một profile như `dev` hay `prod` là nhãn cấu hình có thể kích hoạt thông qua `spring.profiles.active`. Nó giúp áp dụng giá trị và bean riêng cho môi trường.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
public class ExampleConfiguration {

    @Bean
    @Profile("dev")
    public DiagnosticService diagnosticService() {
        return new DiagnosticService();
    }
}
~~~

Trong ví dụ này, bean chỉ được tạo khi profile `dev` hoạt động (giả định lớp `DiagnosticService` đã được định nghĩa trong dự án). Nếu mã khác yêu cầu bean đó không điều kiện ở môi trường `prod`, ứng dụng có thể lỗi khi khởi động vì không tìm được bean. Đây là một ví dụ cho thấy **điều kiện cấu hình tác động trực tiếp lên cấu trúc ApplicationContext**, không chỉ lên một chuỗi văn bản.

Không nên dùng profile như “lối tắt” để bỏ qua mọi kiểm tra môi trường. Dù profile `prod` đang bật, một URL database sai, secret thiếu hoặc service ngoài không kết nối được vẫn có thể làm ứng dụng lỗi.

### Ưu tiên kiểu cấu hình có cấu trúc

Khi một nhóm property phát triển lớn, `@ConfigurationProperties` thường rõ ràng hơn nhiều `@Value` rời rạc vì có thể bind một nhóm giá trị thành một đối tượng và hỗ trợ validation. Ví dụ về cấu trúc:

~~~yaml
app:
  notification:
    enabled: true
    retry-count: 3
    timeout: 5s
~~~

Các khóa trên chỉ có tác dụng khi có bean hoặc code thực sự đọc và sử dụng chúng. Spring Boot không tự tạo hành vi nghiệp vụ chỉ vì YAML có property `app.notification.enabled`.

## 6. Dependency ảnh hưởng đến hành vi theo những cách nào?

### 6.1. Thêm thư viện có thể kích hoạt auto-configuration

Spring Boot có các điều kiện như `@ConditionalOnClass`, `@ConditionalOnMissingBean` và `@ConditionalOnProperty`. Tùy lớp, bean và property nào hiện diện, một auto-configuration có thể được áp dụng hoặc bỏ qua.

Lấy trường hợp một ứng dụng muốn làm việc với cơ sở dữ liệu quan hệ:

1. Dependency liên quan đến JDBC hoặc Spring Data giúp các lớp tích hợp có mặt trên classpath.
2. JDBC driver phù hợp cung cấp khả năng nói chuyện với loại database cụ thể.
3. Cấu hình như `spring.datasource.url`, tên người dùng và thông tin xác thực cho biết điểm kết nối.
4. Auto-configuration đánh giá điều kiện để tạo các bean như `DataSource` khi thích hợp; bean tự định nghĩa có thể thay thế mặc định.
5. Mạng, DNS, database server và tài khoản thực tế quyết định kết nối có thành công không.

Một ứng dụng có thể **build thành công nhưng lỗi khi startup** nếu dependency đã đủ mà database không truy cập được; cũng có thể startup được nhưng chỉ lỗi khi có request đầu tiên đụng tới database, tùy cơ chế khởi tạo và sử dụng kết nối.

### 6.2. Version và phạm vi dependency cũng quan trọng

Không phải mọi phiên bản thư viện đều tương thích với nhau. Maven/Gradle giải quyết đồ thị dependency theo quy tắc của công cụ build và các cơ chế quản lý phiên bản trong dự án. Việc thay một phiên bản transitive có thể làm thay đổi API hoặc cách chạy mà không cần sửa dòng Java gọi thư viện đó.

Những lỗi như `ClassNotFoundException`, `NoClassDefFoundError` hoặc `NoSuchMethodError` có thể xuất hiện khi runtime classpath thiếu lớp hoặc có phiên bản khác với kỳ vọng của mã đã biên dịch. Cần phân biệt:

- **Compile classpath**: các lớp dùng để biên dịch.
- **Runtime classpath**: các lớp thực sự có mặt khi ứng dụng chạy.
- **Test classpath**: có thể bao gồm công cụ hoặc thư viện chỉ phục vụ kiểm thử.

Ví dụ, một thư viện chỉ thuộc phạm vi test sẽ không tự nhiên xuất hiện trong runtime của bản JAR triển khai. Tương tự, việc thêm một dependency chỉ có ý nghĩa khi bản build mới thực sự chứa hoặc truy cập được dependency đó.

### 6.3. Bean của bạn có thể thay đổi mặc định

Nhiều auto-configuration chỉ tạo bean mặc định khi chưa có bean tương ứng do ứng dụng định nghĩa. Bởi vậy, hai dự án có cùng starter vẫn có thể hành xử khác nhau nếu một dự án khai báo bean tùy chỉnh.

Điều này cũng giải thích vì sao “thêm dependency” không luôn đồng nghĩa với “Spring Boot tự bật toàn bộ tính năng”. Tên starter, điều kiện tự cấu hình, bean tự cung cấp và property điều khiển phải được xét cùng nhau.

## 7. Môi trường chạy là một phần của ứng dụng đang hoạt động

Một artifact JAR có thể giống hệt về byte nhưng kết quả chạy vẫn khác vì điều kiện xung quanh khác nhau.

| Khía cạnh môi trường | Ảnh hưởng có thể quan sát | Tình huống minh họa |
|---|---|---|
| Phiên bản Java/JVM | Khả năng nạp bytecode, cấu hình bộ nhớ, runtime behavior | JAR biên dịch cho phiên bản Java mới hơn không chạy trên JVM quá cũ |
| Biến môi trường và system property | Ghi đè Spring property hoặc dữ liệu do code đọc trực tiếp | `SERVER_PORT=9090` đổi cổng server |
| Network, DNS và firewall | Khả năng gọi API, database, message broker | Hostname database chỉ phân giải trong một mạng riêng |
| File system và quyền truy cập | Khả năng đọc chứng chỉ, tạo file log, lưu file tải lên | Tiến trình trong container không có quyền ghi vào thư mục |
| CPU, RAM, giới hạn container | Thời gian phản hồi, GC, khả năng khởi động | Container bị dừng vì vượt giới hạn bộ nhớ |
| Time zone, locale và clock | Định dạng, lịch trình, timestamp | Tác vụ chạy theo múi giờ không như kỳ vọng |
| Dịch vụ và dữ liệu bên ngoài | Phản hồi nghiệp vụ và tính sẵn sàng | Database có dữ liệu khác nhau giữa staging và production |

Đặc biệt cần hiểu ý nghĩa của `localhost`. Trong một container, `localhost` chỉ chính container đó; trong một máy ảo, nó chỉ máy ảo; trên máy cá nhân, nó chỉ máy cá nhân. Vì vậy, `jdbc:postgresql://localhost:5432/...` có thể hợp lệ khi chạy tất cả dịch vụ trên một máy nhưng sai khi chuyển ứng dụng sang container riêng.

**Một profile không tạo ra môi trường vật lý.** Bật `prod` không tự tạo production database, không cấp quyền file, cũng không thiết lập mạng. Profile chỉ chọn cấu hình và điều kiện Spring; hạ tầng thực tế vẫn phải thỏa mãn các yêu cầu đó.

## 8. Tìm nguyên nhân khi hành vi khác kỳ vọng

Khi ứng dụng “chạy trên máy A nhưng lỗi trên máy B”, một cách điều tra có hệ thống là lần lượt trả lời bốn câu hỏi sau, thay vì sửa ngẫu nhiên file YAML.

### 8.1. Có thực sự chạy cùng mã và artifact không?

Xác định commit, bản build, phiên bản ứng dụng và cách đóng gói đang được sử dụng. Nếu vừa sửa controller nhưng vẫn chạy JAR cũ, thay đổi mã sẽ không thể xuất hiện. Nếu dùng bản build khác nhau, dependency bên trong cũng có thể khác.

Ví dụ các lệnh hỗ trợ xem dependency theo công cụ dự án:

~~~bash
./mvnw dependency:tree
./gradlew dependencies --configuration runtimeClasspath
~~~

Đây là các lệnh tham khảo để người học hiểu cách kiểm tra đồ thị dependency; sử dụng lệnh phù hợp với dự án Maven hoặc Gradle của mình.

### 8.2. Giá trị cấu hình nào thực sự được nạp?

Đối chiếu profile hoạt động, file cấu hình đã đóng gói, file ngoài ứng dụng, biến môi trường, system property và tham số dòng lệnh. Với ví dụ endpoint ở trên, hãy tìm nguồn có hiệu lực của `app.greeting` và `server.port`.

Log lúc khởi động và các công cụ quan sát có thể cung cấp thông tin hữu ích. Nếu ứng dụng bật Spring Boot Actuator, một số endpoint quản trị có thể giúp xem cấu hình hoặc điều kiện auto-configuration; cần hạn chế quyền truy cập và tránh lộ giá trị nhạy cảm.

### 8.3. Classpath và bean có phù hợp không?

Nếu server không khởi tạo, bean không tìm thấy hoặc phương thức thư viện không tồn tại, hãy kiểm tra starter, scope, phiên bản transitive, phạm vi component scan và các điều kiện `@Conditional...`. Với auto-configuration, điều cần biết là **điều kiện nào được thỏa mãn hoặc bị loại**, không chỉ “đã khai báo dependency trong file build hay chưa”.

### 8.4. Môi trường có đáp ứng được yêu cầu không?

Kiểm tra cổng đang được dùng, tài nguyên, quyền, kết nối mạng, địa chỉ host, DNS, certificate, secret và trạng thái của dịch vụ ngoài. Nếu yêu cầu đến ứng dụng nhưng xử lý thất bại, kết quả cũng có thể phụ thuộc vào dữ liệu đầu vào hoặc trạng thái của database tại thời điểm đó.

Một số triệu chứng thường gặp:

| Triệu chứng | Vùng cần xem trước | Vì sao? |
|---|---|---|
| `GET /hello` trả 404 | Mã nguồn, package/component scan, dependency web | Endpoint có thể không được đăng ký hoặc request sai đường dẫn |
| Cổng chạy khác `8080` | Property có hiệu lực, tham số chạy, biến môi trường | `server.port` có thể bị ghi đè |
| Ứng dụng báo thiếu bean | Component scan, cấu hình theo profile, auto-configuration, dependency | Bean có thể không được tạo vì điều kiện không thỏa |
| Lỗi thiếu lớp hoặc phương thức | Artifact, phiên bản và runtime classpath | Thư viện cần thiết có thể thiếu hoặc không tương thích |
| Chỉ lỗi khi chạy trong container | Mạng, `localhost`, DNS, file permission, tài nguyên | Container có môi trường tách biệt với máy phát triển |
| Không kết nối được database | URL/credentials/driver và trạng thái database, mạng | Cần đồng thời đúng cả cấu hình, thư viện và hạ tầng |

## 9. Thiết kế để có hành vi dự đoán được

Việc nhìn rõ bốn yếu tố giúp thiết kế và triển khai ứng dụng ổn định hơn:

1. **Giữ logic trong mã nguồn và dùng cấu hình cho những giá trị thay đổi theo môi trường.** Ví dụ, endpoint và quy tắc nghiệp vụ nằm trong Java, còn URL database, port, timeout hoặc giới hạn nghiệp vụ được khai báo qua property phù hợp.
2. **Quản lý dependency nhất quán.** Dùng cơ chế quản lý phiên bản tương thích với Spring Boot và tạo artifact có thể truy vết. Hạn chế thay đổi ngẫu nhiên phiên bản transitive.
3. **Dùng profile có chủ đích.** Xác định rõ giá trị chung và giá trị riêng của `dev`, `test`, `prod`; không giả định tên profile bảo đảm chất lượng hay an toàn của môi trường.
4. **Cung cấp cấu hình nhạy cảm từ nguồn an toàn.** Không commit mật khẩu, token hay khóa bí mật vào repository. Sử dụng biến môi trường hoặc secret manager tùy nền tảng và kiểm soát quyền đọc, log.
5. **Ưu tiên triển khai cùng một artifact qua các môi trường khi có thể.** Khi đó khác biệt hành vi dễ lần theo cấu hình và điều kiện chạy hơn; vẫn cần biết môi trường và dữ liệu ngoài có thể khác.
6. **Quan sát thông tin đủ để chẩn đoán.** Ghi nhận phiên bản build, profile được kích hoạt, trạng thái phụ thuộc ngoài và lỗi cụ thể, nhưng không in secret ra log.

Có hai nhầm lẫn cần tránh. Thứ nhất, **cấu hình không tự sinh ra mã xử lý**: thêm property mới chỉ có tác dụng nếu framework hoặc code đọc nó. Thứ hai, **dependency không thay thế hạ tầng**: thêm driver hay starter mới không tự khởi tạo database bên ngoài hoặc mở quyền kết nối mạng.

Khi đọc một hiện tượng Spring Boot, hãy xác định *đoạn mã nào xử lý*, *những lớp và bean nào có mặt*, *property nào thực sự có hiệu lực* và *tiến trình đang chạy trong điều kiện nào*. Bốn câu hỏi này nối từ cách Spring Boot khởi động đến hành vi mà người dùng cuối quan sát được.

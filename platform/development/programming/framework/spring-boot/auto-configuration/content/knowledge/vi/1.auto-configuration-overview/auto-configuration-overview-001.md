# Tự cấu hình (auto-configuration) trong Spring Boot: giảm lặp lại cấu hình như thế nào?

## 1. Vấn đề mà auto-configuration giải quyết

Khi nhiều ứng dụng Java dùng chung một công nghệ, lập trình viên thường phải viết lại những đoạn cấu hình rất giống nhau. Ví dụ, một ứng dụng web Spring MVC cần đăng ký các thành phần xử lý HTTP, chuyển đổi JSON, xử lý lỗi, tích hợp máy chủ web và nhiều thiết lập mặc định. Một ứng dụng dùng JDBC lại cần tạo DataSource, kết nối tới cơ sở dữ liệu, cung cấp JdbcTemplate và kết nối với transaction manager khi đáp ứng điều kiện.

Nếu mỗi dự án đều khai báo thủ công toàn bộ những thành phần hạ tầng ấy, nhóm phát triển gặp các vấn đề:

- **Lặp mã cấu hình:** nhiều dự án có các lớp **@Configuration** và phương thức **@Bean** gần như giống nhau.
- **Chi phí khởi tạo:** một ứng dụng đơn giản cũng phải hiểu và ghép nhiều thành phần hạ tầng trước khi viết nghiệp vụ.
- **Sai khác khó kiểm soát:** mỗi nhóm sao chép, sửa và nâng cấp các cấu hình mặc định theo cách khác nhau.
- **Bảo trì tốn công:** khi thư viện hoặc framework thay đổi, phải rà soát những bản cấu hình lặp lại.

Spring Boot giải quyết phần đáng kể của vấn đề bằng **auto-configuration**: cung cấp sẵn các cấu hình hạ tầng có điều kiện, phù hợp với các thư viện và thiết lập mà ứng dụng thực sự đang dùng. Lập trình viên chủ yếu cung cấp dependency, thuộc tính và bean đặc thù của hệ thống.

Ví dụ, thay vì tự lắp ráp cấu hình MVC và JSON cho từng REST API, ứng dụng dùng Spring Boot cùng **spring-boot-starter-web** có thể tập trung khai báo controller. Spring Boot thiết lập phần lớn hạ tầng web cần thiết dựa trên các điều kiện được thỏa mãn.

## 2. Auto-configuration là gì?

**Auto-configuration** là cơ chế Spring Boot **tự đăng ký những cấu hình và bean mặc định phù hợp với ngữ cảnh ứng dụng**, dựa trên các yếu tố như:

1. **Classpath:** có thư viện hay kiểu dữ liệu cần thiết hay không.
2. **Các bean đã được định nghĩa:** ứng dụng có cung cấp bean tương đương hay chưa.
3. **Thuộc tính và môi trường:** giá trị trong application.properties, application.yml, profile và biến môi trường.
4. **Loại ứng dụng:** ví dụ môi trường Servlet, Reactive hoặc ứng dụng không có web server.
5. **Các điều kiện đặc biệt khác** mà cấu hình thư viện đặt ra.

Đây là **cấu hình có điều kiện**, không phải cơ chế đoán hoàn toàn ý định của lập trình viên. Một dependency xuất hiện trên classpath chỉ là một dữ kiện; nó không bảo đảm mọi bean liên quan đều được tạo ra.

Có thể đọc mối quan hệ theo sơ đồ:

~~~text
Ứng dụng chọn dependency / starter
              +
Spring Boot biết thuộc tính, loại ứng dụng và bean đã có
              |
              v
Nạp các lớp auto-configuration ứng viên
              |
              v
Đánh giá các điều kiện @Conditional...
              |
        +-----+------+
        |            |
    Thỏa mãn    Không thỏa mãn
        |            |
        v            v
Đăng ký cấu hình   Bỏ qua cấu hình
và bean mặc định   hoặc bean tương ứng
        |
        v
Ứng dụng sử dụng hạ tầng đã được cấu hình
~~~

**Nguyên tắc then chốt:** Spring Boot cung cấp mặc định hợp lý; khi cần, ứng dụng vẫn có thể định cấu hình rõ ràng hoặc cung cấp bean của riêng mình. Cơ chế này giúp giảm phần công việc lặp lại mà không tước quyền kiểm soát cấu hình.

### Phân biệt ba khái niệm thường bị nhầm

| Khái niệm | Vai trò |
| --- | --- |
| **Starter** như spring-boot-starter-web | Một nhóm dependency tiện dụng, đưa những thư viện cần thiết lên classpath. Bản thân starter không phải lớp cấu hình. |
| **Auto-configuration** | Các lớp cấu hình Spring Boot kiểm tra điều kiện và tạo bean mặc định khi thích hợp. |
| **Component scanning** | Tìm các class của ứng dụng có **@Component**, **@Service**, **@Controller**, **@Configuration**... trong phạm vi quét để đăng ký bean. |

Ba cơ chế phối hợp, nhưng không đồng nhất: starter đưa thư viện vào, auto-configuration cấu hình hạ tầng, còn component scanning phát hiện thành phần do ứng dụng viết.

## 3. Spring Boot kích hoạt cơ chế này như thế nào?

Một ứng dụng Boot thường có:

~~~java
@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Đây là **đoạn minh họa**, chỉ cho thấy điểm khởi chạy. Annotation **@SpringBootApplication** bao gồm các thành phần tương ứng với **@SpringBootConfiguration**, **@EnableAutoConfiguration** và **@ComponentScan**. Vì vậy, khi chạy ứng dụng Boot thông thường, ta không cần tự thêm **@EnableAutoConfiguration** lần nữa.

Ở Spring Boot 3.x, các module auto-configuration công bố lớp cấu hình ứng viên thông qua tài nguyên:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Mỗi dòng trong tệp liệt kê một lớp auto-configuration. Khi xử lý cấu hình, Spring Boot xem xét các ứng viên này cùng điều kiện tương ứng. **Không phải mọi lớp trong danh sách đều có hiệu lực**, và cũng không phải mọi bean trong một lớp đều được tạo.

Các annotation điều kiện tiêu biểu:

| Điều kiện | Ý nghĩa |
| --- | --- |
| **@ConditionalOnClass** | Chỉ áp dụng nếu một số class có mặt trên classpath. |
| **@ConditionalOnMissingBean** | Chỉ tạo bean mặc định nếu chưa có bean phù hợp theo điều kiện khai báo. |
| **@ConditionalOnBean** | Chỉ áp dụng khi đã tồn tại bean cần thiết. |
| **@ConditionalOnProperty** | Phụ thuộc giá trị thuộc tính cấu hình. |
| **@ConditionalOnWebApplication** | Phụ thuộc việc ứng dụng đang chạy trong loại web application tương ứng. |

Chẳng hạn, cấu hình hạ tầng JSON thường phụ thuộc vào sự hiện diện của thư viện Jackson; một bean ObjectMapper mặc định có thể được đăng ký nếu ứng dụng chưa cung cấp ObjectMapper phù hợp. Chi tiết điều kiện phải xem ở đúng lớp auto-configuration của phiên bản đang sử dụng.

### Trình tự khái quát lúc khởi động

1. **SpringApplication** xây dựng môi trường, nhận cấu hình từ các nguồn được hỗ trợ và khởi tạo **ApplicationContext**.
2. Spring xử lý cấu hình của ứng dụng, component scanning và các cấu hình được import, bao gồm auto-configuration.
3. Spring Boot đánh giá điều kiện để quyết định cấu hình/định nghĩa bean nào được áp dụng.
4. Spring hoàn thiện ApplicationContext và tạo các bean theo cơ chế vòng đời, phụ thuộc của Spring.
5. Ứng dụng bắt đầu phục vụ yêu cầu hoặc chạy tác vụ theo loại ứng dụng.

Đây là trình tự tư duy, **không phải thứ tự tuyệt đối của mọi sự kiện nội bộ**: xử lý bean definition, import và condition có thể diễn ra qua nhiều giai đoạn. Điều cần hiểu là **quyết định tự cấu hình được đưa ra dựa trên trạng thái thực của context và môi trường**.

## 4. Ví dụ chạy được: REST API hầu như không cần cấu hình hạ tầng web

Xét một project độc lập dùng **Java 21, Gradle và Spring Boot 3.3.x**. Mục tiêu là cung cấp một endpoint trả JSON. Ví dụ này cố ý đơn giản để thấy phần Boot tự làm.

Cấu trúc:

~~~text
auto-config-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/demo/
    ├── DemoApplication.java
    └── HelloController.java
~~~

Tệp **settings.gradle**:

~~~groovy
rootProject.name = 'auto-config-demo'
~~~

Tệp **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Tệp **src/main/java/com/example/demo/DemoApplication.java**:

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

Tệp **src/main/java/com/example/demo/HelloController.java**:

~~~java
package com.example.demo;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public Map<String, String> hello() {
        return Map.of("message", "Xin chào Spring Boot");
    }
}
~~~

Chạy trong thư mục project với Gradle đã được cài và JDK 21 sẵn có:

~~~bash
gradle bootRun
~~~

Nếu project có Gradle Wrapper, dùng **./gradlew bootRun** (macOS/Linux) hoặc **.\gradlew.bat bootRun** (Windows). Sau khi ứng dụng khởi động thành công, ở terminal khác:

~~~bash
curl -s http://localhost:8080/hello
~~~

Nội dung JSON trả về:

~~~json
{"message":"Xin chào Spring Boot"}
~~~

Đây là **response body** của endpoint, không phải toàn bộ stdout của lệnh chạy ứng dụng; log khởi động và thông tin môi trường có thể khác nhau.

### Điều gì đã được Boot lo liệu?

- Starter web mang theo Spring MVC, các thư viện HTTP/JSON tương ứng và máy chủ Servlet nhúng mặc định trong bộ dependency thông thường.
- Với các điều kiện phù hợp, auto-configuration thiết lập **DispatcherServlet**, hạ tầng Spring MVC, chuyển đổi response thành JSON thông qua Jackson và các bean hạ tầng liên quan.
- Component scanning phát hiện **HelloController** vì package **com.example.demo** nằm dưới package của **DemoApplication**.
- Spring MVC ánh xạ **GET /hello** tới phương thức **hello()**.
- Boot cung cấp cấu hình mặc định cho cổng web (8080 khi không có thiết lập ghi đè hoặc xung đột cổng).

Lập trình viên **không viết các lớp @Configuration để tự đăng ký DispatcherServlet, ObjectMapper hoặc cấu hình JSON HTTP converter** cho ví dụ này. Phần logic cần viết là controller và hành vi của endpoint.

Điều đó cho thấy chính xác giá trị của auto-configuration: **hạ tầng phổ biến được tái sử dụng thay vì sao chép cấu hình qua từng project**. Tuy nhiên, đây không có nghĩa Boot tự viết controller, định nghĩa API hay logic nghiệp vụ cho ứng dụng.

## 5. Vì sao giảm lặp lại? So sánh trước và sau

Trong một ứng dụng Spring Framework cấu hình thủ công, nhóm phát triển có thể cần tự khai báo nhiều thành phần, như tạo context Servlet/MVC, cấu hình JSON message conversion, chọn server/runtime, cấu hình DataSource và các tích hợp khi dùng tới chúng. Phần việc chính xác phụ thuộc stack và cách triển khai; không phải dự án Spring thuần nào cũng phải khai báo tất cả các mục.

Với Boot, phần cấu hình chung dịch sang **các auto-configuration đã được kiểm thử và phát hành cùng framework**. Các dự án dùng chung nguyên tắc mặc định; ứng dụng chỉ ghi rõ điểm khác biệt.

| Vấn đề | Khi nhiều cấu hình hạ tầng làm thủ công | Khi dùng Spring Boot auto-configuration |
| --- | --- | --- |
| Tạo project mới | Lặp lại các lớp đăng ký hạ tầng | Chọn starter/dependency, viết phần ứng dụng |
| Cấu hình JSON/MVC | Dễ sao chép nhiều thiết lập giống nhau | Boot bật thiết lập thích hợp nếu điều kiện thỏa mãn |
| Cấu hình riêng của dự án | Gắn nhiều giá trị trực tiếp trong mã | Ưu tiên thuộc tính và bean tùy biến khi cần |
| Nâng cấp thư viện | Phải rà soát nhiều bản cấu hình lặp | Dùng mặc định do phiên bản Boot quản lý, kiểm tra thay đổi tương thích |
| Nguy cơ sai khác | Mỗi dự án giữ bản cấu hình của riêng mình | Các dự án có cùng nền tảng mặc định có tính nhất quán cao hơn |

Ví dụ khác là JDBC. Khi một ứng dụng có các dependency JDBC thích hợp, một JDBC driver được hỗ trợ, thuộc tính datasource hợp lệ và các điều kiện liên quan được đáp ứng, Boot có thể cấu hình **DataSource** cùng các tiện ích phù hợp. Nhờ đó, nhiều dịch vụ không cần chép lại cùng một phương thức **@Bean** tạo connection pool. Nhưng Boot **không thể tự suy ra mật khẩu database, URL môi trường production hay yêu cầu bảo mật của hệ thống**: những dữ kiện đó vẫn phải cấu hình rõ ràng.

### Công thức ghi nhớ

**Dependency xác định khả năng + điều kiện xác định tính phù hợp + thuộc tính/bean của ứng dụng xác định điểm tùy chỉnh = cấu hình mặc định có thể tái sử dụng.**

Đây là một mô hình tư duy, không phải công thức thực thi trong Spring.

## 6. Mặc định có điều kiện: khi nào Boot không tự tạo bean?

Hãy xét ba trường hợp để tránh hiểu sai thành “Spring Boot luôn tạo mọi thứ”:

**Trường hợp A: dependency phù hợp có mặt và chưa có bean thay thế.** Một auto-configuration về JSON có thể khởi tạo ObjectMapper mặc định nếu điều kiện của nó phù hợp. Ứng dụng hưởng lợi từ các thiết lập chuẩn mà không phải viết lớp cấu hình riêng.

**Trường hợp B: ứng dụng khai báo bean của mình.** Một số auto-configuration dùng **@ConditionalOnMissingBean**, do đó có thể **nhường quyền** khi người dùng đã định nghĩa bean cùng loại hoặc phù hợp theo điều kiện. Cơ chế này thường gọi là *back off*. Không được suy rộng rằng mọi auto-configuration đều nhường quyền theo mọi kiểu bean; phải kiểm tra điều kiện cụ thể.

**Trường hợp C: dependency, kiểu ứng dụng hoặc thuộc tính không phù hợp.** Ví dụ một auto-configuration chỉ dành cho Servlet sẽ không có hiệu lực trong mọi ứng dụng Reactive hay non-web. Một số cấu hình chỉ hoạt động khi property được bật. Lúc này, bean mong đợi có thể không tồn tại; đó có thể là hành vi đúng của điều kiện.

Điều kiện không được kiểm tra theo cảm tính. Khi nghi ngờ, cần xem báo cáo condition evaluation và lớp auto-configuration tương ứng.

## 7. Ứng dụng tùy chỉnh cấu hình bằng cách nào?

### 7.1. Điều chỉnh thuộc tính thay vì viết lại hạ tầng

Trong ví dụ REST API ở trên, thêm **src/main/resources/application.yml**:

~~~yaml
server:
  port: 9090
~~~

Khởi động lại, endpoint chuyển sang **http://localhost:9090/hello**. Spring Boot đọc cấu hình và áp dụng giá trị khi xây dựng máy chủ web; ta không cần viết phương thức **@Bean** chỉ để đổi cổng. Giá trị này cũng có thể được cung cấp từ những nguồn cấu hình có thứ tự ưu tiên khác, chẳng hạn biến môi trường hoặc tham số chạy.

### 7.2. Định nghĩa bean của ứng dụng khi thực sự cần

Ứng dụng có thể viết **@Configuration** và **@Bean** cho thành phần đặc thù. Ví dụ minh họa độc lập với demo REST ở trên:

~~~java
@Configuration(proxyBeanMethods = false)
class ApplicationClockConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
~~~

Đoạn này cần các import của **org.springframework.context.annotation.Configuration**, **org.springframework.context.annotation.Bean** và **java.time.Clock**; nó chỉ minh họa cấu hình của ứng dụng, **không tự chứng minh có auto-configuration cho Clock**. Khi thư viện có một bean mặc định được bảo vệ bởi **@ConditionalOnMissingBean(Clock.class)**, bean do người dùng tạo có thể khiến mặc định ấy không được đăng ký. Điều kiện chính xác vẫn là yếu tố quyết định.

Nên ưu tiên các cơ chế extension/cấu hình chính thức do từng starter hỗ trợ. Tạo bean thay thế bằng tay có thể vô tình mất các tùy chỉnh mặc định; ví dụ đối với Jackson, hãy cân nhắc tùy biến qua những API mà Spring Boot cung cấp trước khi thay cả ObjectMapper.

### 7.3. Chủ động loại trừ một auto-configuration

Nếu thật sự cần vô hiệu hóa một auto-configuration cụ thể, Boot hỗ trợ cơ chế exclude. Ví dụ sau **chỉ minh họa cú pháp**, không dùng như cách sửa mọi lỗi database:

~~~java
@SpringBootApplication(
    exclude = org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration.class
)
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Có thể cấu hình loại trừ bằng thuộc tính **spring.autoconfigure.exclude** trong trường hợp phù hợp. Chỉ nên exclude sau khi hiểu lý do cấu hình đó được kích hoạt và những tính năng phụ thuộc vào nó. Trong ứng dụng cần kết nối cơ sở dữ liệu, việc exclude DataSource chỉ để che lỗi thiếu URL/driver là giải pháp sai.

## 8. Quan sát auto-configuration thay vì đoán

Khi ứng dụng chạy nhưng bean không được tạo hoặc có bean ngoài dự kiến, hãy kiểm tra **Condition Evaluation Report**.

Với ứng dụng ví dụ, chạy:

~~~bash
gradle bootRun --args='--debug'
~~~

Hoặc thêm tham số **--debug** cho ứng dụng khi chạy JAR. Debug mode cho phép xem các nhóm cấu hình có điều kiện thỏa mãn hoặc không thỏa mãn và thông tin nguyên nhân trong báo cáo (mức độ chi tiết phụ thuộc phiên bản và thiết lập logging).

Một số mục cần xem trong báo cáo:

- **Positive matches:** điều kiện được đáp ứng.
- **Negative matches:** điều kiện không được đáp ứng, kèm lý do.
- **Exclusions:** các auto-configuration bị loại trừ.
- **Unconditional classes:** các lớp được xem xét mà không có điều kiện cấp lớp, nếu báo cáo thể hiện.

Khi có **Spring Boot Actuator**, endpoint **/actuator/conditions** cũng có thể cung cấp dữ liệu về kết quả đánh giá điều kiện nếu endpoint được bật và cho phép truy cập phù hợp. Đừng giả định endpoint này được mở sẵn qua HTTP hoặc công khai trong production.

Quy trình xử lý nhanh khi một bean bị thiếu:

1. Kiểm tra starter/dependency và version thực tế trong dependency tree.
2. Kiểm tra property, profile và loại ApplicationContext đang chạy.
3. Kiểm tra ứng dụng có khai báo bean khác làm auto-configuration back off không.
4. Đọc báo cáo condition evaluation để xác định điều kiện cụ thể.
5. Chỉ sau đó mới thêm cấu hình tùy chỉnh, dependency hoặc exclude nếu có lý do.

## 9. Giới hạn và những hiểu lầm thường gặp

**“Thêm starter là chắc chắn có tất cả bean.”** Sai. Starter chủ yếu gom dependency; auto-configuration còn phải vượt qua điều kiện về classpath, bean, property và runtime.

**“Auto-configuration và component scanning là một.”** Sai. Component scanning tìm class của ứng dụng theo phạm vi quét. Auto-configuration nạp những cấu hình ứng viên được thư viện công bố và đánh giá điều kiện của chúng.

**“Spring Boot loại bỏ hoàn toàn cấu hình.”** Sai. Ứng dụng vẫn phải khai báo endpoint, nghiệp vụ, bảo mật, endpoint bên ngoài, thông tin database và tùy chỉnh cần thiết. Boot giảm cấu hình hạ tầng phổ biến, không xóa bỏ quyết định kiến trúc.

**“Mỗi lần Boot khởi động sẽ tải cấu hình từ Internet.”** Sai. Danh sách cấu hình và class cần thiết đến từ các thư viện và tài nguyên có sẵn trên classpath (trừ khi ứng dụng tự tích hợp cơ chế tải cấu hình ngoài khác).

**“Mặc định luôn tối ưu cho production.”** Sai. Mặc định là điểm khởi đầu, không thay kiểm tra security, hiệu năng, kết nối, quan sát và tính tương thích với yêu cầu thực tế.

**“Không thấy một bean thì cứ thêm @Bean thủ công.”** Không nên. Hãy xác định auto-configuration nào liên quan và điều kiện nào thất bại; nếu không, rất dễ tạo bean trùng hoặc che giấu dependency cấu hình sai.

**“Mọi bean tự cấu hình đều có thể ghi đè bằng cùng một cách.”** Không đúng. Một số auto-configuration có cơ chế back off, một số yêu cầu property hoặc customizer riêng. Cách tùy biến phải dựa trên contract chính thức của thành phần.

## 10. Tự kiểm tra sau bài học

1. Một REST service chỉ có controller nhưng trả được JSON. **Điều gì thuộc trách nhiệm của component scanning và điều gì đến từ auto-configuration?** Component scanning phát hiện controller; auto-configuration có điều kiện cung cấp hạ tầng MVC/JSON cần thiết.
2. Hai ứng dụng có cùng spring-boot-starter-web nhưng có cấu hình hoặc bean người dùng khác nhau. **Có chắc chúng tạo cùng tập bean không?** Không; condition evaluation xét context thực tế.
3. Thêm thư viện JDBC nhưng không có driver hoặc thông số cần thiết. **Boot có chắc tạo DataSource hoạt động không?** Không; điều kiện và cấu hình datasource phải hợp lệ.
4. Muốn đổi cổng HTTP từ 8080 sang 9090. **Có cần viết cấu hình server bằng Java không?** Thường không; đặt **server.port=9090** là đủ với ứng dụng web theo thiết lập Boot tiêu chuẩn.
5. Một bean mặc định không tồn tại. **Nên làm gì trước?** Kiểm tra dependency, property, bean đã có và Condition Evaluation Report trước khi viết cấu hình mới.

## Kết luận

**Auto-configuration là cơ chế chọn và đăng ký cấu hình mặc định dựa trên điều kiện thực tế của ứng dụng.** Nó giúp các dự án Spring Boot tránh sao chép cấu hình hạ tầng phổ biến như MVC, JSON hay JDBC, đồng thời duy trì khả năng thay đổi thông qua dependency, thuộc tính và bean do ứng dụng cung cấp.

Điểm cần nắm vững: **Boot cung cấp mặc định khi điều kiện phù hợp, còn lập trình viên chịu trách nhiệm với những lựa chọn đặc thù của hệ thống.** Hiểu cơ chế condition và cách đọc báo cáo đánh giá điều kiện sẽ giúp tận dụng tốc độ phát triển của Spring Boot mà vẫn kiểm soát cấu hình khi dự án trở nên phức tạp.

# Nhóm thuộc tính spring.main.* và thời điểm được áp dụng trong Spring Boot

## 1. spring.main.* cấu hình thành phần nào?

**spring.main.*** là nhóm thuộc tính dùng để **cấu hình chính đối tượng SpringApplication đang khởi động**: chọn loại ứng dụng web hay không web, bật/tắt banner, cách khởi tạo bean, xử lý bean trùng tên hoặc vòng tham chiếu, log khởi động và một số chính sách vòng đời. Spring Boot liên kết (bind) các giá trị này từ **Environment** vào **SpringApplication** trong quá trình bootstrap.

Đây không phải tiền tố của mọi cấu hình Spring Boot. Ví dụ:

- **spring.main.web-application-type** quyết định dạng context mà SpringApplication cố gắng tạo; **server.port** điều chỉnh cổng của web server *nếu có web server*.
- **spring.main.lazy-initialization** tác động chính sách khởi tạo bean nói chung; một cấu hình **@Lazy** trên bean cụ thể có thể tạo ngoại lệ cho bean đó.
- **spring.main.banner-mode** chọn chế độ in banner; **spring.banner.location** chỉ đến tệp banner.
- **spring.config.location**, **spring.config.name** quyết định nơi lấy tệp cấu hình từ giai đoạn sớm hơn; **spring.profiles.active** chọn profile; chúng không thuộc nhóm **spring.main.***.

Các ví dụ và danh sách bên dưới lấy **Spring Boot 3.3.x** làm mốc, tương thích **Java 17+**. Khi nâng phiên bản Boot, đối chiếu phụ lục Application Properties của chính phiên bản đang sử dụng vì tên và khả năng cấu hình có thể thay đổi.

## 2. Điểm cốt lõi: đọc và áp dụng trước khi refresh ApplicationContext

**Không phải đợi tạo xong bean rồi Spring mới áp dụng spring.main.***. Thứ tự rút gọn của một lần khởi động thành công là:

~~~text
Mã main:
  new SpringApplication(MyApplication.class) / SpringApplication.run(...)
       |
       v
SpringApplication.run bắt đầu
  -> ApplicationStartingEvent
       |
       v
Chuẩn bị Environment
  -> đọc tham số --..., System properties, biến môi trường
  -> xử lý Config Data: application.properties / application.yaml,
     tài liệu theo profile, import cấu hình
  -> ApplicationEnvironmentPreparedEvent
       |
       v
Liên kết các thuộc tính spring.main.* vào SpringApplication
  -> bindToSpringApplication(Environment)
       |
       v
In banner (nếu được bật)
  -> chọn và tạo ApplicationContext thích hợp
  -> chuẩn bị context, đăng ký sources, tinh chỉnh bean factory
       |
       v
Refresh ApplicationContext
  -> đăng ký/xử lý bean definitions
  -> khởi tạo các bean không lazy
  -> thực thi các cơ chế vòng đời container
       |
       v
ApplicationStartedEvent -> ApplicationRunner / CommandLineRunner
  -> ApplicationReadyEvent -> readiness
       |
       v
SpringApplication.run(...) trả về ApplicationContext
~~~

Đây là **sơ đồ khái quát**, không phải danh sách đầy đủ các callback nội bộ. Điểm quan trọng nhất: **Environment và Config Data đã được chuẩn bị trước khi SpringApplication tạo/refresh context**. Vì vậy các thiết lập như loại context, chính sách bean factory và lazy initialization có cơ hội phát huy tác dụng trong chính lần khởi động ấy.

Các thời điểm cần phân biệt:

1. **Khi khởi tạo đối tượng SpringApplication:** Boot suy đoán một số giá trị mặc định từ classpath, chẳng hạn loại ứng dụng web; mã Java cũng có thể gọi các setter để tùy chỉnh trước khi chạy.
2. **Trong prepareEnvironment:** Spring Boot tập hợp các PropertySource, xử lý cấu hình ngoài và profile; sau đó liên kết những **spring.main.*** phù hợp với thuộc tính của SpringApplication.
3. **Trước hoặc trong prepareContext/refresh:** từng thuộc tính được *sử dụng* ở thời điểm cần thiết: chọn context, in banner, xử lý nguồn cấu hình, quản lý bean definitions và khởi tạo bean.
4. **Sau startup và khi shutdown:** một số tùy chọn đã được đọc từ đầu nhưng tác dụng thực tế xuất hiện về sau, ví dụ giữ JVM sống hoặc shutdown hook.

**Đọc cấu hình sớm** và **nhìn thấy tác dụng của cấu hình** là hai việc khác nhau. Chẳng hạn **spring.main.lazy-initialization=true** được liên kết sớm nhưng thể hiện rõ khi Spring quyết định tạo bean trong giai đoạn refresh hoặc khi bean được truy cập sau đó.

## 3. Các thuộc tính spring.main.* thường gặp trong Spring Boot 3.3

Bảng sau bao gồm các khóa chính được liệt kê trong phụ lục Common Application Properties của Spring Boot 3.3.13. Giá trị mặc định có thể bị thay bởi ứng dụng hoặc nguồn cấu hình ưu tiên cao hơn.

| Thuộc tính | Mặc định Boot 3.3 | Công dụng và thời điểm tác động |
| --- | --- | --- |
| **spring.main.web-application-type** | Tự phát hiện theo classpath | Chọn **none**, **servlet** hoặc **reactive**; được dùng lúc chọn/tạo ApplicationContext, trước refresh. |
| **spring.main.banner-mode** | **console** | **console**, **log** hoặc **off**; quyết định cách xử lý banner ở đầu startup, trước khi context được refresh. |
| **spring.main.log-startup-info** | **true** | Bật/tắt các dòng thông tin khởi động do SpringApplication tạo; ảnh hưởng log ở các mốc khởi động, không tắt toàn bộ logging. |
| **spring.main.lazy-initialization** | **false** | Cho phép khởi tạo bean theo nhu cầu; được cài vào chính sách bean trước giai đoạn khởi tạo bean lúc refresh. |
| **spring.main.allow-bean-definition-overriding** | **false** | Cho phép/không cho phép đăng ký bean definition mới có **cùng tên** với bean definition hiện có; tác động trong giai đoạn đăng ký định nghĩa bean. |
| **spring.main.allow-circular-references** | **false** | Cho phép Spring cố gắng giải quyết một số vòng tham chiếu bean; cấu hình bean factory trước khởi tạo bean, không bảo đảm giải được mọi vòng. |
| **spring.main.sources** | Không khai báo thêm | Bổ sung nguồn cấu hình như tên lớp hoặc package; được dùng khi Spring nạp các sources vào context trước refresh. |
| **spring.main.register-shutdown-hook** | **true** | Cho phép đăng ký hook để đóng context khi JVM shutdown; thiết lập lúc bootstrap, hiệu quả thực tế ở giai đoạn dừng. |
| **spring.main.keep-alive** | **false** | Giữ JVM sống ngay cả khi không còn thread non-daemon khác; hữu ích với tác vụ dùng virtual threads; tác dụng liên quan vòng đời tiến trình sau startup. |
| **spring.main.cloud-platform** | Tự phát hiện nếu phù hợp | Ghi đè giá trị nhận diện nền tảng cloud của SpringApplication; chỉ đặt khi có lý do rõ ràng để thay kết quả tự phát hiện. |

Một số cách dùng điển hình:

- Chương trình CLI/batch không cần HTTP server: **spring.main.web-application-type=none**.
- Muốn giảm tiếng ồn ở console: **spring.main.banner-mode=off**; cân nhắc **log-startup-info=false** nếu thực sự không cần dòng log thông tin khởi động.
- Muốn thử tối ưu startup: **spring.main.lazy-initialization=true**, sau đó đo lại latency request đầu tiên và kiểm tra lỗi bean được phát hiện trễ.
- Ứng dụng Java 21 dùng **@Scheduled** với virtual threads và có nguy cơ không còn non-daemon thread giữ JVM sống: cân nhắc **spring.main.keep-alive=true**. Thuộc tính này không thay thế điều kiện readiness hoặc kiểm tra sức khỏe.

### 3.1. web-application-type và classpath

Nếu không cấu hình rõ, SpringApplication suy ra dạng ứng dụng từ những thư viện trên classpath:

- **servlet:** thường dùng Spring MVC và một servlet web server.
- **reactive:** dùng hệ WebFlux/reactive nếu điều kiện classpath phù hợp.
- **none:** context thông thường, không khởi động embedded web server.

Khi có cả Spring MVC lẫn WebFlux, Spring MVC thường được ưu tiên khi tự nhận diện. Có thể dùng **spring.main.web-application-type=reactive** để yêu cầu dạng reactive trong trường hợp dependencies phù hợp. Đặt **none** ngăn SpringApplication khởi chạy embedded web server cho context đó, dù **server.port** vẫn nằm trong file cấu hình.

Chọn kiểu context **không tự động bổ sung dependencies**. Nếu ép **servlet** hoặc **reactive** mà thiếu thành phần runtime tương ứng, startup có thể thất bại.

### 3.2. bean definition overriding khác với bean trùng kiểu

**spring.main.allow-bean-definition-overriding=true** cho phép bean definition cùng **tên** ghi đè nhau trong các trường hợp tương ứng. Nó không giải quyết mọi tình huống có **hai bean cùng kiểu** khi tiêm dependency; lỗi **NoUniqueBeanDefinitionException** vẫn cần **@Primary**, **@Qualifier** hoặc cách thiết kế phù hợp. Bật overriding bừa bãi dễ che mất xung đột cấu hình.

**spring.main.allow-circular-references=true** cũng không phải cách sửa mọi vòng phụ thuộc. Một vòng constructor injection bắt buộc giữa hai bean thường không thể được giải quyết chỉ bằng bật cờ này. Cách tốt hơn là tách trách nhiệm, tránh chu trình phụ thuộc hoặc tái thiết kế điểm giao tiếp giữa các bean.

### 3.3. lazy-initialization không có nghĩa "không tạo bean"

Khi lazy initialization bật, Spring vẫn phải tạo những bean cần thiết để chạy bootstrap, những bean được yêu cầu bởi bean khác hoặc những bean đã được khai báo **@Lazy(false)**. Bean chưa cần tới có thể chỉ được tạo khi một endpoint, listener hoặc mã của bạn gọi đến. Vì vậy việc ứng dụng khởi động thành công **không đảm bảo** mọi bean lazy đều hợp lệ.

Lazy initialization có thể giảm thời gian startup nhưng đánh đổi bằng độ trễ ở lần truy cập đầu tiên và khả năng phát hiện lỗi cấu hình muộn.

## 4. Viết các giá trị spring.main.* ở đâu?

### 4.1. application.properties

Đặt trong **src/main/resources/application.properties**:

~~~properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
spring.main.lazy-initialization=true
spring.main.allow-bean-definition-overriding=false
spring.main.allow-circular-references=false
~~~

Đây là cấu hình cho một ứng dụng **không dùng web**, minh họa việc giảm banner/log khởi động và sử dụng lazy initialization. Các cờ **false** ở hai dòng cuối nhắc lại chính sách mặc định trong Boot 3.3; bạn không bắt buộc phải khai báo chúng.

Cùng nội dung dưới dạng **application.yaml** (chọn một định dạng chính cho dự án):

~~~yaml
spring:
  main:
    web-application-type: none
    banner-mode: off
    log-startup-info: false
    lazy-initialization: true
    allow-bean-definition-overriding: false
    allow-circular-references: false
~~~

### 4.2. Tham số khi chạy

Khi có file JAR Spring Boot có tên **app.jar**:

~~~bash
java -jar app.jar --spring.main.banner-mode=console --spring.main.lazy-initialization=false
~~~

Trong cấu hình thông thường, hai tham số này sẽ được đưa vào **Environment** và có mức ưu tiên cao hơn các giá trị cùng tên trong **application.properties**. Đây là cách thử thay đổi cấu hình cho một lần chạy mà không sửa file.

Với Gradle Boot plugin, có thể chuyển các tham số này vào chương trình:

~~~bash
./gradlew bootRun --args='--spring.main.lazy-initialization=false'
~~~

Nếu dự án dùng Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun --args="--spring.main.lazy-initialization=false"
~~~

**Lưu ý:** **--spring.main.*** là tham số của ứng dụng Spring Boot. Nó khác với tùy chọn của chính trình chạy Gradle hoặc JVM như **-Xmx**.

### 4.3. Biến môi trường và JVM System properties

Các giá trị có thể đến từ môi trường hệ điều hành, JVM system properties, Config Data hoặc tham số command line. Spring Boot hỗ trợ relaxed binding cho tên thuộc tính. Ví dụ tên biến môi trường tiêu chuẩn là **SPRING_MAIN_LOGSTARTUPINFO**, tương ứng **spring.main.log-startup-info**: thay dấu chấm bằng gạch dưới, bỏ dấu gạch nối và viết hoa.

Với Java system property:

~~~bash
java -Dspring.main.banner-mode=off -jar app.jar
~~~

Trong mẫu này **-D** đứng trước **-jar** để JVM tự thiết lập system property.

### 4.4. Thứ tự ưu tiên và Java setter

SpringApplication có setter Java để cấu hình trước khi chạy:

~~~java
SpringApplication application = new SpringApplication(MyApplication.class);
application.setBannerMode(org.springframework.boot.Banner.Mode.OFF);
application.run(args);
~~~

Nếu **application.properties** lại chứa:

~~~properties
spring.main.banner-mode=console
~~~

giá trị bên ngoài sẽ **ghi đè thuộc tính đã đặt bằng setter** khi Spring Boot bind **spring.main.*** vào SpringApplication. Do đó banner được in ở chế độ **console**, với điều kiện không có nguồn khác ưu tiên cao hơn thay đổi giá trị này.

**Ngoại lệ đáng nhớ:** các *primary sources* đã truyền vào constructor **new SpringApplication(MyApplication.class)** hoặc sources chính từ SpringApplicationBuilder được giữ lại. Nếu đặt **spring.main.sources=com.example.MoreConfig**, nguồn đó **được bổ sung**, không thay thế **MyApplication.class**.

Trong trường hợp cấu hình phổ biến, **command line arguments** ưu tiên cao hơn **Java system properties**, cao hơn **OS environment variables**, và các nguồn này ưu tiên hơn **application.properties/application.yaml**. Config Data có các quy tắc riêng đối với vị trí, profile và tài liệu import; khi cần tìm giá trị thực tế, kiểm tra PropertySource đang thắng thay vì chỉ nhìn một file.

## 5. Vì sao @PropertySource và @PostConstruct thường "quá muộn"?

Đây là lỗi rất dễ gặp khi phân biệt **cấu hình bootstrap** với **cấu hình bean**:

~~~java
@Configuration
@PropertySource("classpath:late.properties")
class ExtraConfiguration {
}
~~~

Nếu **late.properties** chứa:

~~~properties
spring.main.web-application-type=none
~~~

không nên trông chờ nó thay đổi loại ApplicationContext. Spring Boot đọc **@PropertySource** trên lớp **@Configuration** khi đang xử lý/refresh context, trong khi **spring.main.*** đã được bind vào SpringApplication **trước khi refresh**. Đó là lý do tài liệu Spring Boot nêu rõ **@PropertySource** quá muộn cho các thuộc tính như **logging.*** và **spring.main.***.

Tương tự:

~~~java
@PostConstruct
void changeStartupOption() {
    System.setProperty("spring.main.banner-mode", "off");
}
~~~

Ví dụ này chỉ minh họa **thao tác sai thời điểm** (giả sử có bean chứa phương thức trên). Khi **@PostConstruct** chạy, banner đã được xử lý, loại context đã được chọn và nhiều cấu hình startup đã được áp dụng. Việc chỉnh System property lúc đó không quay lại chạy những bước đã hoàn tất.

**Quy tắc áp dụng:** muốn cấu hình cách SpringApplication khởi động, cung cấp thuộc tính qua **Config Data**, CLI, environment hoặc system properties **trước lúc bootstrap đọc chúng**. Với cấu hình ảnh hưởng cả việc tìm file cấu hình như **spring.config.name**, **spring.config.location**, **spring.config.additional-location**, phải cung cấp từ giai đoạn rất sớm (thường qua CLI, System property hoặc biến môi trường), không đặt nó trong chính file cần tìm.

## 6. Ví dụ Java 17+ chạy được: quan sát lazy initialization và thời điểm bind

Tạo ứng dụng Boot 3.3 có dependency **spring-boot-starter** và plugin build tương ứng. File Java:

**src/main/java/com/example/runtime/MainPropertiesDemo.java**

~~~java
package com.example.runtime;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class MainPropertiesDemo {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(MainPropertiesDemo.class, args)) {

            System.out.println("Context active = " + context.isActive());

            boolean alreadyCreated =
                    context.getBeanFactory()
                           .containsSingleton("expensiveService");

            System.out.println(
                    "ExpensiveService created before lookup = "
                            + alreadyCreated);

            context.getBean(ExpensiveService.class).sayHello();
        }
    }

    @Bean
    ExpensiveService expensiveService() {
        return new ExpensiveService();
    }

    static class ExpensiveService {
        ExpensiveService() {
            System.out.println("Creating ExpensiveService");
        }

        void sayHello() {
            System.out.println("Hello from ExpensiveService");
        }
    }
}
~~~

Đặt trong **src/main/resources/application.properties**:

~~~properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
spring.main.lazy-initialization=true
~~~

Chạy:

~~~bash
./gradlew bootRun
~~~

Trong trường hợp không có thành phần khác chủ động yêu cầu bean **expensiveService** trước khi hàm **main** tra cứu, các dòng do chương trình tự in, theo thứ tự, là:

~~~text
Context active = true
ExpensiveService created before lookup = false
Creating ExpensiveService
Hello from ExpensiveService
~~~

Giải thích: **run(...)** đã trả về một context active, nhưng bean **expensiveService** chưa được khởi tạo do lazy initialization. Lệnh **context.getBean(...)** tạo bean, phát sinh dòng **Creating...**, rồi mới gọi phương thức **sayHello()**. Một số thành phần thư viện khác có thể in log xen kẽ tùy cấu hình.

Chạy lại và ghi đè thuộc tính từ command line:

~~~bash
./gradlew bootRun --args='--spring.main.lazy-initialization=false'
~~~

Khi tắt lazy initialization, bean singleton thông thường này được tạo trong quá trình refresh, **trước khi run(...) trả về**. Những dòng chương trình in sẽ có thứ tự:

~~~text
Creating ExpensiveService
Context active = true
ExpensiveService created before lookup = true
Hello from ExpensiveService
~~~

Điểm kiểm chứng ở đây là **giá trị từ CLI đã tác động đến quá trình tạo bean trước khi câu lệnh đầu tiên sau run(...) chạy**.

**Vì sao ví dụ đóng context?** Đây là chương trình **non-web** ngắn, dùng **try-with-resources** để giải phóng context sau phép quan sát. Trong ứng dụng web phục vụ lâu dài, không đóng context ngay sau **SpringApplication.run(...)**, vì sẽ dừng ứng dụng.

## 7. Liên hệ cụ thể giữa nhóm thuộc tính và các mốc lifecycle

Không nên hiểu tất cả thuộc tính có cùng một thời điểm tác dụng. Có thể phân nhóm như sau:

| Giai đoạn | Nhóm thuộc tính liên quan | Điều quan sát được |
| --- | --- | --- |
| Sau khi Environment/Config Data sẵn sàng | Toàn bộ **spring.main.*** có mapping phù hợp | Giá trị từ Environment được bind vào SpringApplication trước khi tạo/refresh context. |
| In banner | **banner-mode** | Có in banner ra console, log hay bỏ qua. |
| Tạo và chuẩn bị context | **web-application-type**, **sources**, **cloud-platform** | Chọn context, đăng ký cấu hình đầu vào và áp dụng đặc điểm môi trường. |
| Đăng ký và tạo bean | **allow-bean-definition-overriding**, **allow-circular-references**, **lazy-initialization** | Tác động đến bean factory và cách bean được đăng ký/khởi tạo. |
| Các mốc log khởi động | **log-startup-info** | Bật/tắt những dòng log thông tin startup do SpringApplication quản lý. |
| Vòng đời ứng dụng | **register-shutdown-hook**, **keep-alive** | Tác động việc JVM tiếp tục sống và/hoặc context được đóng khi JVM shutdown. |

**ApplicationStartedEvent** được phát **sau refresh**, trước **ApplicationRunner/CommandLineRunner**. **ApplicationReadyEvent** được phát **sau runner**. Cấu hình **spring.main.*** đã phát huy ảnh hưởng đến bootstrap từ trước các sự kiện này; đợi đến runner mới đặt lại các thuộc tính khởi động sẽ quá muộn cho lần chạy hiện tại.

Các sự kiện đầu chuỗi, như **ApplicationEnvironmentPreparedEvent**, xuất hiện trước khi context được tạo; listener có thể quan sát hoặc điều chỉnh Environment ở giai đoạn sớm thích hợp, nhưng cần hiểu thứ tự listener và Config Data. Cách dễ kiểm soát nhất khi không cần tùy biến framework là cung cấp cấu hình ngay từ **application.properties**, **application.yaml**, CLI hoặc hệ thống triển khai.

## 8. Lỗi phổ biến và cách chẩn đoán

### 8.1. Đặt spring.main.web-application-type=none nhưng vẫn mong endpoint HTTP hoạt động

**none** chủ đích bỏ web application context/embedded server. Để mở HTTP endpoint, cần kiểu ứng dụng web và dependencies thích hợp; **server.port=8080** riêng nó không tạo server khi SpringApplication chạy ở chế độ none.

### 8.2. Bật allow-circular-references=true để "sửa" vòng constructor injection

Thuộc tính chỉ cho phép Spring cố gắng giải quyết các dạng vòng tham chiếu được hỗ trợ. Vòng constructor injection không thể tự biến thành đồ thị phụ thuộc hợp lệ nhờ một cờ cấu hình. Hãy xem stack trace, xác định bean trong vòng và thiết kế lại dependency.

### 8.3. Bật overriding để tránh lỗi inject hai bean cùng type

**allow-bean-definition-overriding** xử lý tình huống **trùng tên definition**; **@Qualifier** hoặc **@Primary** giải quyết việc chọn bean khi có nhiều ứng viên cùng kiểu. Hai lỗi có nguyên nhân khác nhau.

### 8.4. Tắt log-startup-info và nghĩ rằng toàn bộ log bị vô hiệu hóa

**spring.main.log-startup-info=false** không tắt logger của thư viện, bean, web server hoặc ứng dụng. Kiểm soát các log khác bằng **logging.level.*** và cấu hình logging tương ứng.

### 8.5. Chỉ nhìn application.properties nhưng kết quả không như mong đợi

Kiểm tra biến môi trường, Java System properties, tham số **--...**, các file ngoài JAR và file theo profile. Ví dụ **--spring.main.banner-mode=console** ở CLI có thể thắng **spring.main.banner-mode=off** trong file. Sử dụng cơ chế kiểm tra nguồn giá trị thuộc tính khi cần, chẳng hạn Actuator **env** trong môi trường được bảo vệ phù hợp.

### 8.6. Đổi Environment sau khi ứng dụng đã ready rồi mong startup tự chạy lại

Sau **run(...)**, Spring không tự tạo lại ApplicationContext hoặc khởi chạy lại các bước in banner, nạp sources và cấu hình bean factory. Muốn thay đổi nhóm thuộc tính bootstrap, thông thường phải **khởi động lại ứng dụng** bằng cấu hình mới.

### 8.7. Bật lazy init và cho rằng mọi lỗi cấu hình đã được phát hiện lúc startup

Bean lazy có thể chỉ bộc lộ lỗi khi request đầu tiên hoặc tác vụ lần đầu yêu cầu nó. Cần test luồng sử dụng thực tế, đặc biệt với dependency quan trọng; cân nhắc **@Lazy(false)** cho bean bắt buộc xác nhận sớm.

## 9. Câu hỏi tự kiểm tra

**Câu A.** Trong **application.properties** đặt **spring.main.banner-mode=off**. Trong mã Java lại gọi **application.setBannerMode(Banner.Mode.CONSOLE)** trước **run(args)**. Không có nguồn cấu hình nào khác ghi đè. Kết quả?

**Đáp án:** Chế độ **off** từ external configuration được bind vào SpringApplication trong bootstrap và thắng giá trị setter Java.

**Câu B.** Bạn đặt **spring.main.web-application-type=none** trong file được nạp bằng **@PropertySource** trên lớp **@Configuration**. Có bảo đảm SpringApplication chọn context non-web?

**Đáp án:** Không. **@PropertySource** được xử lý quá muộn cho nhóm **spring.main.***; hãy đặt giá trị trong Config Data, CLI, system properties hoặc biến môi trường phù hợp.

**Câu C.** Đã nhận **ApplicationReadyEvent** nhưng một bean lazy chưa từng được yêu cầu. Bean đó chắc chắn đã được tạo?

**Đáp án:** Không. **ApplicationReadyEvent** nói về mốc startup/runner; chính sách lazy initialization có thể trì hoãn việc khởi tạo bean đến lúc nó được yêu cầu.

**Câu D.** **spring.main.sources** khai báo thêm hai lớp cấu hình. Lớp **MyApplication.class** đã truyền vào constructor có biến mất?

**Đáp án:** Không. Nguồn bổ sung cùng tham gia context; primary source ban đầu không bị thay thế chỉ vì cấu hình thêm sources.

**Câu E.** Tắt **register-shutdown-hook** có làm ứng dụng ngừng chạy ngay sau **run(...)**?

**Đáp án:** Không. Cờ này điều chỉnh việc đăng ký shutdown hook, không ra lệnh thoát tiến trình. Nếu tắt hook mặc định, ứng dụng cần có cách đóng context/tài nguyên đúng vòng đời.

## 10. Ghi nhớ

**spring.main.*** là các công tắc cấu hình **SpringApplication trước khi context hoàn tất khởi tạo**, được lấy từ Environment và gắn vào đối tượng launcher trong giai đoạn bootstrap. **Thời điểm bind** diễn ra sớm; **thời điểm phát huy tác dụng** tùy thuộc từng thuộc tính: in banner, chọn context, đăng ký và tạo bean, log startup hoặc shutdown/JVM lifecycle.

Khi một giá trị không phát huy tác dụng, hãy kiểm tra **nguồn cấu hình nào thực sự thắng** và **giá trị có sẵn đủ sớm hay chưa**. Đặc biệt, **@PropertySource** và **@PostConstruct** không phải nơi phù hợp để thay đổi các quyết định bootstrap đã được đưa ra.

### Tài liệu tham khảo chính thức

- Spring Boot 3.3.13 — Common Application Properties (xem nhóm spring.main.*): https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html
- Spring Boot 3.3 — Externalized Configuration (thứ tự PropertySource, cảnh báo @PropertySource quá muộn): https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 — SpringApplication API (bindToSpringApplication, createApplicationContext): https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot — Properties and Configuration / Externalize the Configuration of SpringApplication: https://docs.spring.io/spring-boot/how-to/properties-and-configuration.html
- Spring Boot 3.3 — SpringApplication (lazy initialization, lifecycle/events): https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
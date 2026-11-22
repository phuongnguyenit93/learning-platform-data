# Dùng SpringApplicationBuilder để biểu diễn quá trình khởi chạy ứng dụng Spring Boot

## 1. Mục tiêu và ý nghĩa

Khi bắt đầu một ứng dụng Spring Boot, cách viết quen thuộc nhất là gọi **SpringApplication.run(MyApplication.class, args)** trong phương thức **main**. Cách này ngắn gọn và phù hợp với đa số ứng dụng. Khi cần **diễn đạt rõ từng lựa chọn cấu hình trước khi khởi chạy**, có thể dùng **SpringApplicationBuilder**.

**SpringApplicationBuilder** là lớp builder trong package **org.springframework.boot.builder**, cung cấp một fluent API: các lời gọi nối tiếp nhau trả về builder để mô tả nguồn cấu hình, profile, loại ứng dụng web/non-web, thuộc tính mặc định, listener và cách tổ chức ApplicationContext. Lời gọi **run(args)** ở cuối mới thực sự tiến hành bootstrap ứng dụng và trả về **ConfigurableApplicationContext** đã chạy.

Ví dụ hình dung:

~~~java
new SpringApplicationBuilder(MyApplication.class)
        .bannerMode(Banner.Mode.OFF)
        .profiles("local")
        .properties("app.mode=demo")
        .web(WebApplicationType.NONE)
        .run(args);
~~~

Đoạn trên nói rằng: lấy **MyApplication** làm nguồn cấu hình; tắt startup banner; bổ sung profile **local**; cung cấp giá trị mặc định **app.mode=demo**; chạy dạng **non-web**; sau cùng khởi động với đối số dòng lệnh của chương trình.

**Điểm quan trọng:** thứ tự gọi **bannerMode → profiles → properties → web** trong chuỗi không phải thứ tự thực thi từng giai đoạn của Spring Boot. Trước **run**, builder chủ yếu tích lũy các tùy chọn. Spring Boot thực hiện chuỗi startup thật sự khi **run(args)** được gọi.

## 2. Biểu diễn luồng khởi chạy bằng builder

Có thể phân quá trình thành hai pha rõ ràng:

~~~text
PHA 1 — DIỄN ĐẠT CẤU HÌNH (trong main)
  new SpringApplicationBuilder(Application.class)
      ├── sources(...) / nguồn bean
      ├── profiles(...) / profile bổ sung
      ├── properties(...) / thuộc tính mặc định
      ├── bannerMode(...) / startup banner
      ├── web(...) / loại ứng dụng
      ├── listeners(...) / listener
      └── initializers(...) / initializer
                        |
                        v
PHA 2 — KHỞI CHẠY THỰC SỰ
                    run(args)
                        |
                        v
                SpringApplication
                        |
                        v
      Chuẩn bị Environment / ApplicationContext
                        |
                        v
      Nạp cấu hình, tạo bean, refresh context
                        |
                        v
           Chạy ApplicationRunner và
                 CommandLineRunner
                        |
                        v
              ApplicationReadyEvent
                        |
                        v
             Ứng dụng hoạt động
                        |
                        v
         Trả về ConfigurableApplicationContext
          (để quan sát hoặc đóng khi phù hợp)
~~~

Trong thứ tự thời gian, các runner chạy **trước khi phương thức run trả kết quả về main**. Các startup event và công việc chuẩn bị khác do Spring Boot xử lý; sơ đồ trên tập trung vào những mốc học tập chính, không phải danh sách đầy đủ tất cả internal callback.

Mối quan hệ giữa các lớp:

- **SpringApplicationBuilder:** diễn đạt cách tạo và khởi chạy ứng dụng, hỗ trợ cấu trúc nhiều context.
- **SpringApplication:** thực thi tiến trình bootstrap theo cấu hình đã nhận.
- **Environment:** cung cấp properties và active profiles; chịu ảnh hưởng của nhiều nguồn cấu hình.
- **ApplicationContext:** quản lý bean, dependency injection và vòng đời các bean.
- **ConfigurableApplicationContext:** context mà **run** trả về; có thể dùng để kiểm tra trạng thái, lấy bean và đóng context khi đúng yêu cầu của ứng dụng.

Builder là công cụ **khởi tạo runtime**; bản thân nó không phải bean container và cũng không biến mỗi lời gọi fluent thành một “bước startup” chạy độc lập.

## 3. Những API thường dùng và ý nghĩa chính xác

| API | Vai trò | Điểm cần nhớ |
| --- | --- | --- |
| **new SpringApplicationBuilder(App.class)** | Chỉ định một hoặc nhiều primary sources cho ứng dụng | Thường là class có **@SpringBootApplication** hoặc **@Configuration** |
| **sources(OtherConfig.class)** | Bổ sung nguồn cấu hình/bean cho ứng dụng | Không đồng nghĩa với kích hoạt tự động mọi package trong classpath |
| **profiles("dev")** | Bổ sung active profile | Không nên mặc định hiểu là xóa toàn bộ profile có sẵn |
| **properties("key=value")** | Đặt default properties | Giá trị có độ ưu tiên thấp hơn nhiều nguồn external config, ví dụ command-line arguments |
| **properties(Map)** | Đặt nhiều default properties từ map | Thích hợp khi cấu hình được lập trình tạo ra |
| **bannerMode(Banner.Mode.OFF)** | Ẩn startup banner | Không đồng nghĩa với tắt toàn bộ logging |
| **web(WebApplicationType.NONE)** | Chọn ứng dụng non-web | Không tạo HTTP server từ cơ chế web auto-configuration |
| **web(WebApplicationType.SERVLET)** | Yêu cầu mô hình servlet web app | Cần các dependency tương thích với servlet web runtime |
| **web(WebApplicationType.REACTIVE)** | Yêu cầu mô hình reactive web app | Cần hạ tầng reactive tương ứng |
| **listeners(...)** | Đăng ký application event listener từ sớm | Hữu ích cho event trước khi context tạo bean |
| **initializers(...)** | Đăng ký **ApplicationContextInitializer** | Chạy khi context được chuẩn bị trước khi bean definitions được tải |
| **logStartupInfo(false)** | Tắt một phần thông tin startup do SpringApplication log | Không thay thế cấu hình logging đầy đủ |
| **lazyInitialization(true)** | Bật khởi tạo bean lười | Có thể chuyển lỗi tạo bean từ startup sang thời điểm bean được dùng |
| **parent(...)**, **child(...)** | Tạo ApplicationContext phân cấp | Làm tăng độ phức tạp của phạm vi bean, events và cấu hình |
| **build()** | Tạo **SpringApplication** đã cấu hình | Chưa đồng nghĩa với khởi tạo/refresh ApplicationContext |
| **run(args)** | Khởi chạy và nhận **ConfigurableApplicationContext** | Đây là mốc thực thi quan trọng nhất |

Trong code của một ứng dụng đơn giản, không cần gọi mọi API. Cấu hình chỉ nên dùng những lựa chọn có lý do rõ ràng; cấu hình Spring Boot từ file và biến môi trường thường đủ cho nhiều trường hợp.

### So sánh ba cách khởi chạy

**Cách 1 — static convenience API:**

~~~java
SpringApplication.run(DemoApplication.class, args);
~~~

**Cách 2 — tạo SpringApplication rồi tùy biến:**

~~~java
SpringApplication application = new SpringApplication(DemoApplication.class);
application.setBannerMode(Banner.Mode.OFF);
application.setWebApplicationType(WebApplicationType.NONE);
application.run(args);
~~~

**Cách 3 — fluent builder API:**

~~~java
new SpringApplicationBuilder(DemoApplication.class)
        .bannerMode(Banner.Mode.OFF)
        .web(WebApplicationType.NONE)
        .run(args);
~~~

Cả ba có thể bootstrap cùng một ứng dụng. Builder phù hợp khi nhiều tùy chọn cần đặt cạnh nhau để dễ đọc, khi muốn diễn đạt cấu trúc context phân cấp, hoặc khi muốn xây dựng **SpringApplication** trước khi chạy. Đừng chọn builder chỉ vì tin rằng nó tự làm runtime chạy nhanh hơn.

## 4. Ví dụ đầy đủ Java 17+: quan sát startup từ builder

### 4.1. Tạo dự án

Tạo dự án Maven bằng Spring Initializr, chọn Java 17 trở lên và Spring Boot 3.x (ví dụ bản 3.5.x phù hợp với dự án). Dùng dependency **Spring Boot Starter** cho ứng dụng non-web; không cần thêm Spring Web để thực hiện bài tập này. Đặt package là **com.example.demo**, và tạo/đổi tên main class thành **BuilderStartupApplication**. Nếu dự án khởi tạo sẵn một main class khác, bảo đảm chỉ chạy class được minh họa trong bài.

File **src/main/java/com/example/demo/BuilderStartupApplication.java**:

~~~java
package com.example.demo;

import java.util.Arrays;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class BuilderStartupApplication {

    public static void main(String[] args) {
        System.out.println("01 | Configure builder");

        try (ConfigurableApplicationContext context =
                new SpringApplicationBuilder(BuilderStartupApplication.class)
                        .bannerMode(Banner.Mode.OFF)
                        .web(WebApplicationType.NONE)
                        .profiles("lab")
                        .properties("lesson.mode=builder")
                        .run(args)) {
            System.out.println("03 | Context active=" + context.isActive());
        }

        System.out.println("04 | Context closed");
    }

    @Bean
    ApplicationRunner inspectRuntime(Environment environment) {
        return args -> {
            System.out.println("02 | ApplicationRunner");
            System.out.println("     profile lab active="
                    + Arrays.asList(environment.getActiveProfiles())
                            .contains("lab"));
            System.out.println("     lesson.mode="
                    + environment.getProperty("lesson.mode"));
        };
    }
}
~~~

**Giải thích từng phần:**

1. **@SpringBootApplication** cung cấp điểm cấu hình chính của ứng dụng, bao gồm các cơ chế Spring Boot liên quan đến auto-configuration và component scan.
2. **new SpringApplicationBuilder(BuilderStartupApplication.class)** chọn class nguồn và khởi tạo builder.
3. **bannerMode(Banner.Mode.OFF)** tắt phần banner trang trí, không ngăn các log khởi động khác.
4. **web(WebApplicationType.NONE)** buộc đây là một runtime non-web; bài tập không tạo REST endpoint và không mở HTTP port.
5. **profiles("lab")** bổ sung profile **lab** vào tập active profiles.
6. **properties("lesson.mode=builder")** tạo giá trị mặc định cho thuộc tính học tập.
7. **run(args)** thực hiện startup, tạo/refresh context và chạy các runner trước khi quay về main.
8. Bean **ApplicationRunner** in ra giá trị lấy từ **Environment** khi startup đã đạt tới bước chạy runner.
9. **try-with-resources** đóng context sau khi main đi qua khối try. Cách này **cố ý minh họa vòng đời ngắn**; một HTTP server phục vụ lâu dài thường không tự đóng ngay sau khi **run** trả về.

### 4.2. Chạy thử

Từ thư mục gốc dự án được tạo bằng Spring Initializr:

~~~bash
# Linux/macOS
./mvnw spring-boot:run

# Windows (PowerShell/cmd)
# .\mvnw.cmd spring-boot:run
~~~

Các dòng **do mã ví dụ tự in** theo thứ tự sẽ là:

~~~text
01 | Configure builder
02 | ApplicationRunner
     profile lab active=true
     lesson.mode=builder
03 | Context active=true
04 | Context closed
~~~

Spring Boot có thể in thêm logging và dữ liệu môi trường khác giữa các dòng này; khối trên không tuyên bố là toàn bộ stdout. Kết quả trên giả định không có nguồn cấu hình ngoài ghi đè **lesson.mode** và không có lỗi startup. **Context active=true** được in khi khối try còn mở; sau khi đóng, main in **Context closed**.

Không thể lấy riêng file Java rồi biên dịch bằng **javac** không kèm classpath Spring Boot. Chạy qua Maven Wrapper/Gradle Wrapper của dự án để công cụ build cấp các dependency và thực thi đúng main class.

### 4.3. Truyền command-line arguments và xem độ ưu tiên cấu hình

Đóng gói dự án:

~~~bash
./mvnw package
~~~

Chạy file JAR thực thi được tạo ra trong thư mục **target** (điền đúng tên file JAR của dự án):

~~~bash
java -jar target/builder-demo.jar --lesson.mode=command-line
~~~

Nếu artifact thực tế có tên khác, thay **builder-demo.jar** bằng tên file JAR đã build. Khi command-line properties được bật theo mặc định, tham số **--lesson.mode=command-line** có độ ưu tiên cao hơn default property đã khai báo bằng **properties("lesson.mode=builder")**. Lúc đó dòng tương ứng đổi thành:

~~~text
     lesson.mode=command-line
~~~

Đây là cách thể hiện sự khác nhau giữa **“giá trị mặc định mà builder đề xuất”** và **“giá trị hiệu lực mà Environment tra cứu”**. Các nguồn cấu hình khác, ví dụ environment variables, config files hay command-line arguments, vẫn tham gia vào cơ chế externalized configuration của Spring Boot.

Nếu ứng dụng cần cấu hình dành riêng cho từng môi trường triển khai, hãy cân nhắc dùng application.yml, profile và biến môi trường. Đừng đóng cứng secret như mật khẩu hay API token vào **properties(...)** trong source code.

## 5. Builder và mốc hoạt động của SpringApplication

### Trước run(args)

Builder chỉ giữ các lựa chọn được cung cấp. Chẳng hạn:

~~~java
SpringApplicationBuilder builder =
        new SpringApplicationBuilder(BuilderStartupApplication.class)
                .web(WebApplicationType.NONE);

SpringApplication application = builder.build();
~~~

**build()** trả về một **SpringApplication** có thể tiếp tục dùng để chạy về sau:

~~~java
ConfigurableApplicationContext context = application.run(args);
~~~

Nếu chỉ gọi **build()** và không gọi **run()**, ứng dụng chưa được bootstrap thành một context đang hoạt động. Trong code thông thường, gọi trực tiếp **builder.run(args)** dễ đọc hơn khi không cần giữ đối tượng SpringApplication.

### Trong run(args)

Các hoạt động chính do Spring Boot điều phối gồm: chuẩn bị Environment, tạo ApplicationContext thích hợp, áp dụng cấu hình, khởi tạo và kết nối bean, refresh context, chạy các runner rồi phát các startup event tương ứng. Event như **ApplicationStartingEvent** xuất hiện rất sớm; **ApplicationPreparedEvent** xảy ra trước khi refresh; **ApplicationStartedEvent** xảy ra khi context đã refresh nhưng trước các runner; **ApplicationReadyEvent** xảy ra sau khi runner hoàn tất. Khi startup gặp lỗi, **ApplicationFailedEvent** có thể được phát.

Điều này giúp xác định đúng hook cho mỗi nhu cầu:

| Nhu cầu | Gợi ý |
| --- | --- |
| Can thiệp sớm trước khi bean được tải | **ApplicationContextInitializer** khi đúng trường hợp |
| Lắng nghe các event rất sớm | **builder.listeners(...)**, thay vì chỉ một bean listener được tạo muộn |
| Chạy một tác vụ sau khi context đã khởi tạo | **ApplicationRunner** hoặc **CommandLineRunner** |
| Phản ứng khi ứng dụng được Boot đánh dấu đã sẵn sàng | **ApplicationReadyEvent** |
| Thực thi logic nghiệp vụ mỗi khi có request | Controller/service hoặc thành phần xử lý tương ứng; không đặt trong **main** |

Với ứng dụng có readiness/liveness probe, **ApplicationReadyEvent** là mốc của Spring Boot; trạng thái thực tế được hệ thống triển khai dùng để nhận traffic còn phụ thuộc cấu hình probe và các phụ thuộc bên ngoài. Không suy ra rằng hệ thống hoàn toàn khỏe chỉ vì **run(args)** đã trả về.

### Sau run(args)

Biến **context** cho phép đọc trạng thái, lấy bean khi thật sự cần hoặc gọi **close()** nếu vòng đời của ứng dụng yêu cầu. Với ứng dụng web liên tục phục vụ request, đoạn **main** thường không lập tức đóng context; Spring Boot thường đăng ký JVM shutdown hook để đóng các tài nguyên được quản lý khi dừng bình thường.

Phải phân biệt **một tiến trình Java đang chạy** với **một ApplicationContext đang hoạt động**. Builder tạo runtime bằng cách yêu cầu SpringApplication bootstrap một context; tài nguyên tiến trình và JVM vẫn do các lớp tương ứng quản lý.

## 6. Biến thể: khởi chạy ứng dụng web từ builder

Khi dự án có dependency **Spring Web** và main class là ứng dụng servlet web, có thể viết:

~~~java
new SpringApplicationBuilder(ApiApplication.class)
        .bannerMode(Banner.Mode.OFF)
        .web(WebApplicationType.SERVLET)
        .properties("server.port=8088")
        .run(args);
~~~

Đây là **đoạn cấu hình minh họa**, không phải chương trình Java đầy đủ độc lập vì class **ApiApplication** và dependencies chưa được định nghĩa trong đoạn. Với servlet web runtime hợp lệ, Boot tạo server theo cấu hình và mở port **8088** nếu không bị nguồn cấu hình ưu tiên cao hơn ghi đè.

Nếu chỉ muốn Boot tự chọn kiểu ứng dụng dựa trên classpath, có thể **không gọi web(...)**. Khi cùng classpath có cả MVC và WebFlux, việc nhận diện mặc định tùy theo quy tắc Spring Boot; đặt **web(WebApplicationType.REACTIVE)** hay **SERVLET** chỉ khi bạn chủ động lựa chọn loại runtime tương ứng và có đủ dependency.

Đừng dùng **WebApplicationType.NONE** rồi chờ REST controller tự mở port HTTP: NONE cố ý không khởi tạo web server. Đừng đóng context ngay bằng try-with-resources như ví dụ non-web nếu mục tiêu là giữ HTTP server phục vụ các request tiếp theo.

## 7. Nâng cao: biểu diễn quan hệ parent/child ApplicationContext

Một tính năng nổi bật của **SpringApplicationBuilder** là tạo phân cấp context khi ứng dụng thật sự có nhu cầu tách lớp cấu hình dùng chung và lớp web:

~~~java
new SpringApplicationBuilder(ParentConfiguration.class)
        .web(WebApplicationType.NONE)
        .child(WebApplication.class)
        .web(WebApplicationType.SERVLET)
        .run(args);
~~~

Đoạn trên **chỉ minh họa cấu trúc builder**; để chạy được cần tự định nghĩa **ParentConfiguration**, **WebApplication**, các bean và dependency phù hợp, đồng thời tránh component scanning đăng ký trùng cấu hình giữa hai context.

Cách đọc đoạn code:

1. Tạo cấu hình cho **parent context** từ **ParentConfiguration** và chọn parent là non-web.
2. **child(WebApplication.class)** chuyển sang builder đại diện cho child context, sử dụng **WebApplication** làm nguồn cấu hình con.
3. **web(WebApplicationType.SERVLET)** đặt web type cho context con.
4. **run(args)** khởi động cấu trúc phân cấp và trả về context ở cấp builder hiện hành.

Những quy tắc cần hiểu trước khi áp dụng:

- Bean trong **child context** có thể tìm bean từ **parent** thông qua cơ chế tra cứu phù hợp; parent không tự nhìn thấy bean chỉ nằm trong child.
- Spring Boot đặt một số giới hạn đối với context hierarchy; **web components phải thuộc child context**, và các context trong hierarchy dùng chung **Environment** theo hợp đồng của builder.
- Startup event của child có thể lan lên parent. Listener ở parent có thể nhận event cùng loại nhiều lần vì có nhiều context; nên so sánh context nguồn event nếu cần phân biệt.
- Các lời gọi **parent(...)** và **child(...)** ảnh hưởng cấu trúc context, không có nghĩa hai context hoàn toàn tách biệt về properties hay sự kiện.
- Đừng tạo hierarchy chỉ để “chia module” cho code. Phần lớn ứng dụng Boot dùng một ApplicationContext với cấu trúc package/bean bình thường sẽ dễ duy trì hơn.

Với mô hình microservices, hai service độc lập thường là hai tiến trình/ứng dụng được triển khai riêng; parent/child context **không tương đương** với hai microservices.

## 8. Khi nào nên dùng SpringApplicationBuilder?

**Tình huống phù hợp:**

- Muốn nhìn thấy rõ các lựa chọn khởi động tại một nơi trong **main**: profile, loại runtime, cấu hình mặc định hoặc listener.
- Cần dựng ứng dụng non-web để chạy một chương trình nền với hạ tầng bean của Spring.
- Cần tùy biến bootstrap trước khi **ApplicationContext** xuất hiện.
- Cần tổ chức một hierarchy parent/child trong thiết kế có chủ đích.

**Tình huống không cần thiết:**

- Một dịch vụ Spring Boot bình thường với startup mặc định; **SpringApplication.run(...)** đủ rõ.
- Chỉ cần thay port, database URL hay log level giữa các môi trường; file cấu hình và biến môi trường thường hợp lý hơn.
- Muốn cấu hình một bean nghiệp vụ; nên dùng **@Bean**, component stereotype và dependency injection.
- Muốn điều khiển logic request/transaction sau startup; builder không đảm nhiệm chức năng này.

Các lựa chọn trong builder là những thiết lập bootstrap cấp ứng dụng, không thay thế việc thiết kế bean, cấu hình thread pool, timeout, security hoặc monitoring cho runtime.

## 9. Lỗi thường gặp và cách nhận biết

| Dấu hiệu / ngộ nhận | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Gọi **build()** mà không thấy ứng dụng chạy | **build** chỉ tạo SpringApplication | Gọi **run(args)** ở builder hoặc SpringApplication |
| Đã gọi **web(NONE)** nhưng không có HTTP port | NONE là chế độ non-web | Đổi web type hợp lý và thêm dependency cần thiết |
| Cấu hình từ **properties(...)** bị “mất” | Đây là default properties, có thể bị nguồn khác ghi đè | Kiểm tra Environment, command-line args, profile, env vars |
| Không thấy banner nhưng vẫn thấy log | Banner và logging là hai cơ chế khác nhau | Cấu hình logging riêng nếu có nhu cầu |
| Listener viết thành bean không thấy event rất sớm | Event phát trước khi ApplicationContext tạo bean | Đăng ký từ bootstrap bằng **listeners(...)** nếu phù hợp |
| Có bean nhưng ứng dụng lỗi khi startup | Thiếu dependency, bean conflict, cấu hình không hợp lệ hoặc lỗi khởi tạo | Đọc exception gốc và startup log; không đoán do builder |
| Runner bị chạy trước khi đoạn code sau **run(...)** thực thi | Đó là thứ tự đúng: runner chạy trong pha startup | Chuyển logic sang hook phù hợp với yêu cầu |
| Khởi chạy web rồi đóng context ngay | **close()**/try-with-resources chấm dứt vòng đời context | Không đóng khi cần tiếp tục phục vụ |
| Parent có vẻ không tìm được bean trong child | Chiều tra cứu bean giữa context không đối xứng | Đặt bean dùng chung trong parent hoặc thiết kế lại |
| Event listener chạy nhiều lần trong hierarchy | Event child lan lên parent | Kiểm tra ApplicationContext gắn với event |
| Thêm **profiles("dev")** rồi mặc định tin chỉ còn một profile | profiles có tính bổ sung; nhiều nguồn có thể kích hoạt profile | Quan sát **Environment.getActiveProfiles()** thực tế |

## 10. Bài tập củng cố

**Bài tập 1 — Default property và command-line override:** chạy ví dụ phần 4 như bình thường, sau đó chạy JAR với **--lesson.mode=command-line**. So sánh dòng **lesson.mode**. Giải thích vì sao kết quả thay đổi dù builder giữ nguyên lời gọi **properties(...)**.

**Bài tập 2 — Non-web và web:** trả lời vì sao **web(WebApplicationType.NONE)** không mở port dù có Spring Boot trong classpath. Sau đó phác thảo những dependency và thay đổi cần thiết để dùng **WebApplicationType.SERVLET** phục vụ một REST endpoint.

**Bài tập 3 — Thứ tự startup:** điền thứ tự của bốn mốc: tạo builder, **run(args)**, **ApplicationRunner**, dòng **Context active=true** trong main. Giải thích vì sao runner xảy ra trước dòng cuối dù code bean được khai báo ở phía dưới main.

**Bài tập 4 — Phân cấp context:** xem đoạn minh họa parent/child và xác định context nào nên chứa web component; parent có thể trực tiếp truy cập bean chỉ khai báo trong child hay không; vì sao listener parent có thể nhìn thấy nhiều event.

Đáp án trọng tâm: (1) command-line property ưu tiên hơn default property; (2) NONE chọn không khởi tạo web runtime, servlet mode cần đúng dependency; (3) tạo builder → run bắt đầu → runner thực thi trong run → run trả context rồi main in trạng thái; (4) web ở child, tra cứu bean chủ yếu từ child lên parent, event có thể truyền lên tổ tiên.

## 11. Ghi nhớ và nguồn tham khảo

**SpringApplicationBuilder giúp diễn đạt cấu hình khởi chạy một cách tường minh và có thể tạo context hierarchy. Phương thức run(args) mới tạo runtime, trả về ApplicationContext đang hoạt động và kích hoạt các mốc startup của Spring Boot.** Phân biệt rõ các giai đoạn **cấu hình builder → thực thi SpringApplication → vận hành context** là điều cốt lõi của bài.

Tài liệu chính thức để tra cứu hành vi theo phiên bản dự án:

- Spring Boot Reference — SpringApplication, Fluent Builder API và Application Events: https://docs.spring.io/spring-boot/4.0/reference/features/spring-application.html
- Spring Boot 3.5 API — SpringApplicationBuilder: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/builder/SpringApplicationBuilder.html
- Spring Boot Reference — How-to / ApplicationContext hierarchy, non-web application: https://docs.spring.io/spring-boot/4.0/how-to/application.html

Khi đưa ví dụ vào dự án có phiên bản Spring Boot khác, cần đối chiếu lại JavaDoc đúng phiên bản đó, đặc biệt với cấu hình bootstrap nâng cao và behavior của context hierarchy.
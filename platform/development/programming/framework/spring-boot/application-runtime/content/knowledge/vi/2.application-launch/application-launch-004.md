# Giá trị trả về ConfigurableApplicationContext và thời điểm SpringApplication.run hoàn tất

## 1. SpringApplication.run(...) trả về gì?

Trong ứng dụng Spring Boot, lời gọi **SpringApplication.run(...)** khởi động một lần chạy của ứng dụng và, nếu thành công, trả về đối tượng kiểu **org.springframework.context.ConfigurableApplicationContext**. Đây là Spring IoC container đã được tạo, cấu hình và làm mới (refresh) cho lần chạy ấy. Nó quản lý các bean, môi trường cấu hình, sự kiện ứng dụng và vòng đời của context.

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(DemoApplication.class, args);

        System.out.println("Context active: " + context.isActive());
    }
}
~~~

Trong một lần khởi động bình thường, dòng in sau lệnh run cho ra **Context active: true**. Phần log khởi động do Spring Boot sinh ra có thể xuất hiện trước dòng này và thay đổi theo cấu hình.

Hai cách gọi phổ biến có cùng kiểu giá trị trả về:

~~~java
// Cách tiện dụng, sử dụng cấu hình mặc định:
ConfigurableApplicationContext context =
        SpringApplication.run(DemoApplication.class, args);

// Cách tự tạo SpringApplication để tùy chỉnh trước khi chạy:
SpringApplication app = new SpringApplication(DemoApplication.class);
// app.setAdditionalProfiles("dev"); // Ví dụ tùy chỉnh nếu cần
ConfigurableApplicationContext anotherContext = app.run(args);
~~~

Hai lệnh ở ví dụ trên minh họa **hai cách gọi độc lập**; không đặt cả hai vào một luồng main thực tế nếu bạn chỉ muốn khởi chạy một ứng dụng. Lớp context cụ thể phụ thuộc loại ứng dụng và cấu hình: ứng dụng servlet, reactive và không phải web có thể dùng các triển khai context khác nhau. Vì thế nên lập trình theo kiểu giao diện **ConfigurableApplicationContext**, tránh ép kiểu sang một triển khai cố định.

## 2. ConfigurableApplicationContext dùng để làm gì?

**ApplicationContext** cung cấp khả năng truy cập các bean do Spring quản lý; **ConfigurableApplicationContext** còn có những thao tác quản lý vòng đời như đóng context. Những khả năng thường gặp:

| API | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| **context.getBean(MyService.class)** | Lấy bean được quản lý theo kiểu | Lỗi nếu không có hoặc có nhiều bean phù hợp mà không phân giải được |
| **context.getEnvironment()** | Đọc thuộc tính và profile đang kích hoạt | Thuộc tính chịu thứ tự ưu tiên các nguồn cấu hình |
| **context.isActive()** | Kiểm tra context đang ở trạng thái active | Không tương đương với việc mọi dịch vụ bên ngoài đều khỏe |
| **context.getId()** | Lấy định danh của context | Hữu ích khi chẩn đoán nhiều context |
| **context.close()** | Đóng context, hủy singleton phù hợp và giải phóng tài nguyên | Có thể dừng web server; chỉ gọi khi thật sự muốn kết thúc vòng đời |

Ví dụ minh họa truy cập một bean đã đăng ký:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(DemoApplication.class, args);

MyService service = context.getBean(MyService.class);
service.doWork();
~~~

Đoạn này **giả định** dự án có bean **MyService** và phương thức **doWork()**; đây là minh họa cách sử dụng context, không phải một chương trình độc lập. Trong mã ứng dụng thường ngày, ưu tiên constructor injection để nhận dependency; không cần truyền đối tượng context khắp các tầng chỉ để tra cứu bean.

Giữ tham chiếu context hữu ích trong mã bootstrap, test tích hợp hoặc ứng dụng chạy theo lệnh. Với ứng dụng web thông thường, bạn không cần gọi **close()** ngay sau **run(...)**: điều đó sẽ bắt đầu quá trình dừng ứng dụng vừa khởi chạy.

## 3. “run hoàn tất” có nghĩa chính xác là gì?

Điểm dễ nhầm là **context được refresh xong** và **phương thức run trả về** là hai mốc khác nhau. Spring Boot còn thực hiện các callback và phát sự kiện ở giữa.

Trình tự quan trọng khi khởi động thành công (Spring Boot 3.x, cách phát sự kiện mặc định):

1. Chuẩn bị Environment, tạo ApplicationContext, đăng ký cấu hình và các bean definition.
2. **Refresh context**: kích hoạt quá trình tạo/khởi tạo các singleton không lazy, xử lý vòng đời container; với ứng dụng web, web server thường được khởi tạo trong giai đoạn này.
3. Phát **ApplicationStartedEvent**: context đã refresh, nhưng **ApplicationRunner/CommandLineRunner chưa được gọi**.
4. Phát tín hiệu liveness **LivenessState.CORRECT**.
5. Gọi các bean **ApplicationRunner** và **CommandLineRunner**. Nếu có nhiều runner, dùng **@Order** hoặc **Ordered** khi cần thứ tự rõ ràng.
6. Phát **ApplicationReadyEvent**, rồi tín hiệu readiness **ReadinessState.ACCEPTING_TRAFFIC**.
7. **SpringApplication.run(...) trả về ConfigurableApplicationContext** cho mã gọi; các câu lệnh kế tiếp trong **main** mới chạy.

Dòng thời gian rút gọn:

~~~text
main: trước run
    |
    v
chuẩn bị + refresh ApplicationContext
    |
    v
ApplicationStartedEvent
    |
    v
ApplicationRunner / CommandLineRunner
    |
    v
ApplicationReadyEvent
    |
    v
ReadinessState.ACCEPTING_TRAFFIC
    |
    v
run(...) TRẢ VỀ context
    |
    v
main: câu lệnh tiếp theo
~~~

**Hệ quả:** nếu mã trong runner đang chạy đồng bộ và chưa xong, lời gọi **run(...)** chưa trả về. Nếu listener xử lý sự kiện theo cơ chế đồng bộ mặc định, phần xử lý listener cũng nằm trên đường khởi động trước thời điểm trả về. Tuy nhiên, công việc đã được đẩy sang thread khác, scheduler hoặc hệ thống hàng đợi không mặc nhiên được chờ đến khi hoàn tất.

**ContextRefreshedEvent** cũng xuất hiện khi context được refresh, sớm hơn **ApplicationStartedEvent**. Đừng nhầm sự kiện này với mốc “toàn bộ ứng dụng đã ready”.

## 4. Ví dụ chạy được: tự quan sát thứ tự

Ví dụ dưới đây dùng **Java 17+** và dự án **Spring Boot 3.x** có dependency **spring-boot-starter**. Đặt file **src/main/java/com/example/runtime/RuntimeDemoApplication.java** trong một dự án Boot đã cấu hình plugin build thích hợp. Đặt ứng dụng thành loại **NONE** để không khởi tạo web server, giúp ví dụ tập trung vào vòng đời.

~~~java
package com.example.runtime;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class RuntimeDemoApplication {

    public static void main(String[] args) {
        System.out.println("1 | Before run");

        SpringApplication app =
                new SpringApplication(RuntimeDemoApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        ConfigurableApplicationContext context = app.run(args);

        System.out.println(
                "5 | After run; context active = " + context.isActive());
    }

    @Bean
    ApplicationListener<ApplicationStartedEvent> startedListener() {
        return event ->
                System.out.println("2 | ApplicationStartedEvent");
    }

    @Bean
    ApplicationRunner startupRunner() {
        return arguments ->
                System.out.println("3 | ApplicationRunner");
    }

    @Bean
    ApplicationListener<ApplicationReadyEvent> readyListener() {
        return event ->
                System.out.println("4 | ApplicationReadyEvent");
    }
}
~~~

Chạy bằng Gradle Wrapper của dự án Boot (lệnh đầu dành cho Linux/macOS, lệnh thứ hai dành cho Windows):

~~~bash
./gradlew bootRun
~~~

~~~powershell
.\gradlew.bat bootRun
~~~

Trong các dòng do chương trình tự in, **thứ tự kỳ vọng chính xác** là:

~~~text
1 | Before run
2 | ApplicationStartedEvent
3 | ApplicationRunner
4 | ApplicationReadyEvent
5 | After run; context active = true
~~~

Log banner, thời gian khởi động và các thông báo của Spring Boot có thể xen giữa những dòng trên. Ví dụ minh họa đúng mốc thời gian: **ApplicationStartedEvent** không có nghĩa runner đã xong; **ApplicationReadyEvent** đến sau runner; chỉ sau đó code phía sau **app.run(args)** mới được thực thi.

Lưu ý ví dụ là một ứng dụng **không phải web**. Nếu không còn thread không-daemon giữ JVM sống, tiến trình có thể kết thúc sau khi **main** chạy xong. Trong ứng dụng servlet/reactive, web server và các thành phần runtime thường tiếp tục giữ tiến trình hoạt động sau khi **run(...)** đã trả về.

## 5. Phân biệt các mốc “started”, “ready” và “kết thúc tiến trình”

| Mốc | Điều đã xảy ra | Điều chưa được suy ra |
| --- | --- | --- |
| Context refresh hoàn tất | Container đã khởi tạo theo cơ chế eager và các bước refresh đã thành công | Runner đã chạy xong, mọi bean lazy đã được khởi tạo |
| ApplicationStartedEvent | Context đã refresh, runner chưa chạy | Ứng dụng đã hoàn thành tác vụ khởi động |
| ApplicationReadyEvent | Các runner đã được gọi xong thành công | Mọi tác vụ bất đồng bộ hoặc nghiệp vụ ngoài hệ thống đã kết thúc |
| run(...) trả về | Chuỗi khởi động đồng bộ của SpringApplication thành công đến mốc trả về | JVM đã thoát hoặc web server đã ngừng |
| Tiến trình JVM kết thúc | Không còn luồng giữ JVM sống hoặc đã có yêu cầu dừng tiến trình | Chỉ dựa vào thời điểm run trả về không thể suy ra điều này |

**Với web app:** server có thể bind port trong quá trình refresh, tức **trước** khi runner hoàn tất và trước khi **ApplicationReadyEvent** được phát. Vì thế “port đã mở” không đồng nghĩa “đã được công bố sẵn sàng nhận traffic”. Trên hệ thống có readiness probe, nên phân biệt thời điểm network listener bắt đầu hoạt động với trạng thái **ReadinessState.ACCEPTING_TRAFFIC**. Tín hiệu readiness chỉ thể hiện trạng thái do ứng dụng công bố; nó không tự bảo đảm tất cả dependency bên ngoài hoặc mọi tác vụ nền đều thành công.

**Với ứng dụng batch/CLI:** muốn chạy logic một lần sau khi container sẵn sàng, đặt nó trong runner. Nếu cần chương trình trả exit code rồi thoát có kiểm soát, xem hợp đồng **SpringApplication.exit(context)** và cách đóng context phù hợp thay vì suy ra exit code từ việc **run(...)** trả về.

## 6. Khi khởi động thất bại thì sao?

Nếu có lỗi trong quá trình tạo context, refresh, gọi runner hoặc listener đồng bộ trước điểm trả về, **run(...) không trả về một context thành công**; Spring Boot xử lý thất bại khởi động và phát **ApplicationFailedEvent**. Ví dụ, nếu runner ném ngoại lệ:

~~~java
@Bean
ApplicationRunner failingRunner() {
    return arguments -> {
        throw new IllegalStateException("Khoi tao du lieu that bai");
    };
}
~~~

Khi thêm runner này vào ví dụ ở trên, dòng **After run; context active = true** sẽ không được in trong luồng khởi động thành công như trước. Bạn không nên viết logic kiểu “nếu run trả về thì tự động có thể bỏ qua lỗi khởi tạo” vì lỗi xảy ra **trước** điểm trả về sẽ cắt luồng bình thường.

Khi cần xử lý lỗi ở tầng bootstrap, bọc lời gọi **run(...)** trong **try/catch** phù hợp và bảo đảm lỗi được ghi nhận hoặc báo ra cho hệ thống vận hành. Không nuốt ngoại lệ rồi tuyên bố ứng dụng đã ready.

## 7. Những giới hạn cần nhớ

- **Bean lazy/prototype:** context đã active không đồng nghĩa tất cả bean tồn tại dưới dạng instance. Bean lazy có thể chỉ được tạo khi thật sự yêu cầu; prototype không được khởi tạo đồng loạt lúc refresh.
- **Tác vụ nền:** **@Async**, scheduler, thread tự tạo, message consumer và I/O được khởi chạy bất đồng bộ có thể còn đang làm việc sau **ApplicationReadyEvent** và sau khi **run(...)** trả về. Nếu readiness cần phụ thuộc kết quả của chúng, phải thiết kế tín hiệu trạng thái và đồng bộ hóa rõ ràng.
- **Runner chạy lâu:** một runner làm việc đồng bộ quá lâu khiến **run(...)** lâu trả về và làm chậm mốc ready. Với công việc không cần chặn readiness, cân nhắc cơ chế xử lý nền có giám sát thích hợp.
- **Đóng context:** không gọi **context.close()** ngay sau **run(...)** trong ứng dụng web phục vụ lâu dài. Dùng cơ chế shutdown có chủ đích để các bean và tài nguyên được đóng đúng vòng đời.
- **Thứ tự giữa nhiều runner:** chỉ dựa vào interface **ApplicationRunner** và **CommandLineRunner** không tạo ra một thứ tự nghiệp vụ cố định; khai báo **@Order** hoặc **Ordered** khi thứ tự quan trọng.
- **Tên mốc:** sự kiện **ApplicationStartedEvent** trong Spring Boot 3.x xảy ra **sau refresh, trước runners**. Không dùng ý nghĩa của tên gọi để tự suy luận mà bỏ qua thứ tự vòng đời cụ thể.
- **Đọc context:** **isActive() == true** là trạng thái của Spring context, khác với health check và readiness ở cấp hệ thống. Kiểm tra sức khỏe dịch vụ qua health/readiness phù hợp khi vận hành.

## 8. Bài tự kiểm tra

**Tình huống A.** Trong main có **System.out.println("after")** ngay sau **SpringApplication.run(...)**. Một **ApplicationRunner** chạy đồng bộ trong 5 giây. Dòng “after” có được in khi runner còn chạy không?

**Trả lời:** Không, nếu runner thuộc chính lần khởi động đó và không tự chuyển việc sang luồng khác. Spring Boot chờ callback runner trở về trước khi chuyển sang mốc ready rồi trả về từ **run(...)**.

**Tình huống B.** Web server đã bắt đầu lắng nghe ở port 8080 nhưng **ApplicationRunner** chưa xong. Có thể khẳng định ứng dụng đã phát **ApplicationReadyEvent** chưa?

**Trả lời:** Chưa. Việc server bind port có thể xảy ra trong refresh, trước runner; **ApplicationReadyEvent** theo sau các runner.

**Tình huống C.** **SpringApplication.run(...)** đã trả về context. Có chắc mọi tác vụ khởi tạo chạy bằng **@Async** đã xong và JVM sắp thoát không?

**Trả lời:** Không. Công việc bất đồng bộ có vòng đời riêng; JVM của ứng dụng web thường còn chạy lâu sau khi lời gọi run hoàn tất.

## 9. Ghi nhớ để áp dụng

Một cách đọc đúng đoạn bootstrap là: **SpringApplication.run(...)** trả về **ConfigurableApplicationContext** sau khi chuỗi khởi động đồng bộ của Spring Boot hoàn tất thành công, gồm refresh context, runners và các sự kiện ready theo thứ tự mặc định. Kết quả này cho phép mã gọi tiếp tục sử dụng container đang chạy; nó **không** có nghĩa toàn bộ tác vụ nền đã hoàn thành hoặc tiến trình ứng dụng đã kết thúc.

Tham khảo chính thức:
- Spring Boot Reference — SpringApplication, Application Events and Listeners, ApplicationRunner/CommandLineRunner: https://docs.spring.io/spring-boot/reference/features/spring-application.html
- Spring Boot 3.3 API — SpringApplication: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3 API — SpringApplicationRunListener: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplicationRunListener.html
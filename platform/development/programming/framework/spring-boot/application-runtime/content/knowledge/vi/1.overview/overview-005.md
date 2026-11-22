# Phân biệt ứng dụng chạy một lần với dịch vụ hoạt động lâu dài trong Spring Boot

## 1. Bản chất của hai kiểu chạy

Một ứng dụng **chạy một lần (one-shot application)** được khởi động để thực hiện một công việc có điểm kết thúc rõ ràng: đọc đầu vào, xử lý, ghi kết quả, giải phóng tài nguyên rồi kết thúc tiến trình. Ví dụ: nhập một tệp dữ liệu, tạo báo cáo cuối ngày, chạy một lệnh quản trị hoặc xử lý một lô dữ liệu được kích hoạt theo lịch bên ngoài.

Một **dịch vụ hoạt động lâu dài (long-running service)** được khởi động để duy trì khả năng phục vụ nhiều yêu cầu hoặc sự kiện trong suốt thời gian triển khai. Ví dụ: REST API, ứng dụng nhận thông điệp từ hàng đợi, dịch vụ tiêu thụ sự kiện hoặc tiến trình điều phối các tác vụ định kỳ. Dịch vụ chỉ ngừng khi nhận yêu cầu dừng, cần triển khai lại hoặc gặp sự cố.

Điểm phân biệt là **hợp đồng vòng đời của tiến trình**, không phải thời gian chạy đo bằng phút hay giờ. Một job chạy ba giờ vẫn có thể là one-shot nếu hoàn thành công việc rồi thoát; một REST API vừa khởi động đã bị dừng sau hai phút vẫn là một dịch vụ lâu dài về mặt thiết kế.

## 2. So sánh theo các khía cạnh thực tế

| Tiêu chí | Ứng dụng chạy một lần | Dịch vụ hoạt động lâu dài |
| --- | --- | --- |
| Mục tiêu | Hoàn thành một khối công việc xác định | Luôn sẵn sàng tiếp nhận yêu cầu hoặc sự kiện mới |
| Điều kiện hoàn tất | Toàn bộ công việc của lần chạy đã thành công hoặc thất bại | Không có điểm “xong toàn bộ dịch vụ” trong vận hành bình thường |
| Cách kích hoạt | Lệnh CLI, người vận hành, lịch bên ngoài, Job/CronJob, pipeline | Deployment, hệ thống điều phối, dịch vụ quản lý tiến trình |
| Đầu vào | Tham số lệnh, tệp, bản ghi cần xử lý, job parameters | HTTP, thông điệp, sự kiện, tác vụ đến trong lúc chạy |
| Đầu ra | Kết quả xử lý, tệp/bản ghi mới, log, mã thoát | Phản hồi từng yêu cầu/sự kiện, thay đổi trạng thái, metric |
| Trạng thái bình thường sau khi khởi động | Xử lý công việc rồi kết thúc | Tiếp tục chờ và xử lý các yêu cầu tiếp theo |
| Cách báo thành công/thất bại | Kết quả nghiệp vụ và exit code của từng lần chạy | Kết quả từng request/event, health, metric và trạng thái tiến trình |
| Quản lý tài nguyên | Mở khi thực hiện, đóng khi hoàn thành hoặc lỗi | Tài nguyên sống cùng dịch vụ, đóng khi shutdown |
| Phương án triển khai thường gặp | Kubernetes Job/CronJob, tác vụ CI, lệnh vận hành | Kubernetes Deployment, service manager, container chạy thường trực |
| Khi có lỗi | Cần xác định có retry cả job hay bước lỗi, chống ghi trùng | Cô lập lỗi theo request/event; dịch vụ thường tiếp tục nhận việc |

Không đồng nhất **one-shot** với “chạy một luồng” và **long-running** với “đa luồng”: cả hai đều có thể xử lý song song. Cũng không đồng nhất “không có HTTP” với “chạy một lần”; consumer của message broker có thể hoạt động liên tục mà không mở cổng HTTP.

## 3. Spring Boot khởi động giống nhau, vòng đời tiếp theo khác nhau

Hai kiểu đều có thể dùng cùng cơ chế khởi tạo của Spring Boot:

1. Phương thức main gọi SpringApplication.run(...), trực tiếp hoặc thông qua SpringApplication được cấu hình.
2. Spring Boot chuẩn bị Environment, tạo và refresh ApplicationContext, khởi tạo các bean cùng hạ tầng đã cấu hình.
3. Với ứng dụng web, embedded server có thể được khởi tạo và bắt đầu lắng nghe cổng.
4. Sau khi context được refresh, Spring Boot gọi các bean ApplicationRunner và CommandLineRunner; khi các runner hoàn tất, ứng dụng phát ApplicationReadyEvent.
5. **Điểm rẽ của vòng đời:** one-shot chủ động hoàn thành và kết thúc; dịch vụ tiếp tục phục vụ nhờ web server, listener hoặc cơ chế xử lý dài hạn thích hợp.

**ApplicationReadyEvent không đồng nghĩa “job đã thành công” hoặc “đã xử lý xong mọi request”.** Nó báo giai đoạn khởi động Spring Boot đã hoàn tất, bao gồm các startup runner. Một service có thể ready rồi còn chạy vô hạn; một one-shot có thể ready ngay trước khi đóng context.

Spring Boot xác định kiểu web từ classpath và cấu hình. Với spring-boot-starter-web, ứng dụng thông thường chạy servlet web server; với ứng dụng CLI thuần, nên chỉ rõ WebApplicationType.NONE để không khởi động web server ngoài ý muốn. Tuy nhiên **WebApplicationType.NONE không tự định nghĩa job đã hoàn tất**: nếu ứng dụng còn listener, executor với luồng không phải daemon hoặc hoạt động nền khác, tiến trình vẫn có thể còn sống.

## 4. Ví dụ one-shot: xử lý một lần rồi thoát

Ví dụ sau dành cho **một dự án Spring Boot 3.x riêng biệt**, Java 17+, có spring-boot-starter. Lưu lớp trong src/main/java/demo/OneShotApplication.java.

~~~java
package demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class OneShotApplication implements CommandLineRunner {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(OneShotApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        ConfigurableApplicationContext context = app.run(args);
        int exitCode = SpringApplication.exit(context);
        System.exit(exitCode);
    }

    @Override
    public void run(String... args) {
        System.out.println("Xử lý hoàn tất.");
    }
}
~~~

Nếu dự án đã cấu hình Spring Boot Gradle plugin, có thể chạy bằng lệnh:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell, dùng:

~~~powershell
.\gradlew.bat bootRun
~~~

Dòng do mã ví dụ tự in ra (bỏ qua log khởi động của Spring Boot) là:

~~~text
Xử lý hoàn tất.
~~~

**Diễn giải từng bước:**

- ApplicationContext được khởi tạo; WebApplicationType.NONE yêu cầu chế độ không có web server.
- Vì lớp ứng dụng là một Spring bean thực thi CommandLineRunner, Spring Boot gọi run(...) một lần trong mỗi lần khởi động thành công.
- Khi run(...) trả về, SpringApplication.run(...) hoàn tất và trả về context.
- SpringApplication.exit(context) đóng context và lấy exit code từ các ExitCodeGenerator được đăng ký (nếu có); mặc định không có mã lỗi thì trả về 0.
- System.exit(exitCode) chuyển mã này thành mã thoát của tiến trình JVM. Đây là hành vi phù hợp với ứng dụng thực thi một lần có caller cần nhận kết quả.

**Lưu ý quan trọng:** CommandLineRunner chỉ là hook chạy khi khởi động. Nó **không tự biến toàn bộ ứng dụng thành one-shot**. Nếu cùng ứng dụng còn có web server hay thành phần chạy lâu dài, runner xong không có nghĩa tiến trình nên thoát. Đặt System.exit(...) ở luồng điều phối cấp cao của chương trình one-shot; không gọi nó từ xử lý nghiệp vụ dùng chung, controller hoặc listener.

Khi job có kết quả thất bại, cần xác định mã thoát khác 0 một cách có chủ đích (ví dụ qua ExitCodeGenerator/ExitCodeExceptionMapper và cơ chế xử lý lỗi của ứng dụng). Đóng context trong finally hoặc dùng cách quản lý vòng đời phù hợp nếu tự điều phối nhiều bước. Không nuốt exception rồi trả 0 như thể job thành công. Với công việc có tác dụng phụ, thiết kế retry và tính idempotent để chạy lại không tạo dữ liệu trùng.

## 5. Ví dụ long-running: REST API luôn tiếp nhận request

Ví dụ độc lập thứ hai dùng Java 17+, Spring Boot 3.x và spring-boot-starter-web. Lưu trong src/main/java/demo/ApiApplication.java của **một dự án khác** với ví dụ one-shot.

~~~java
package demo;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(ApiApplication.class, args);
    }

    @GetMapping("/ping")
    public Map<String, String> ping() {
        return Map.of("status", "ok");
    }
}
~~~

Sau khi chạy dự án với Gradle, có thể gửi nhiều lần:

~~~bash
curl -s http://localhost:8080/ping
~~~

Phản hồi JSON trong cấu hình cổng mặc định là:

~~~json
{"status":"ok"}
~~~

Khác biệt chính: main không gọi SpringApplication.exit(...) hoặc System.exit(...) ngay sau khi khởi động. Embedded HTTP server tiếp tục lắng nghe và xử lý nhiều request cho đến khi hệ thống dừng ứng dụng. Mỗi request kết thúc không kéo theo việc kết thúc toàn bộ tiến trình. Cổng 8080 chỉ là mặc định trong trường hợp chưa cấu hình server.port hoặc môi trường khác.

Một service không nhất thiết phải có @RestController: ứng dụng xử lý sự kiện hoặc consumer liên tục cũng thuộc kiểu long-running khi nó phải duy trì vòng đời tiếp nhận công việc. Với loại đó, cần cấu hình listener, vòng đời thread/executor và shutdown đúng cách; chỉ đặt web-application-type=none không đủ tạo một tiến trình nhận sự kiện.

## 6. Dừng ứng dụng, mã thoát và khả năng phục hồi

**Với one-shot:**

- Thành công thường tương ứng với exit code 0; lỗi đã được phân loại cần mã khác 0 để scheduler, CI/CD hoặc Kubernetes Job có thể phát hiện.
- Đảm bảo đóng kết nối, transaction, stream, executor và những tài nguyên còn mở. Đừng dựa vào việc hệ điều hành thu hồi tài nguyên thay cho cleanup nghiệp vụ.
- Nếu bị dừng giữa chừng, xác định checkpoint, transaction boundary, cơ chế tiếp tục hoặc chạy lại. “Chạy một lần” mô tả một lần khởi động, không hứa chỉ có một lần thực thi trên toàn hệ thống.
- Cần ghi nhận số bản ghi xử lý, số lỗi, thời lượng, kết quả và dấu vết lần chạy; theo dõi job completion thay vì coi thời gian uptime dài là thành công.

**Với long-running service:**

- Khi nhận yêu cầu dừng có kiểm soát (ví dụ SIGTERM ở môi trường triển khai), Spring Boot có thể đóng ApplicationContext và gọi các cơ chế hủy bean; tài nguyên đang phục vụ cần được giải phóng.
- Với web server, có thể bật graceful shutdown để hạn chế ngắt ngang request đang xử lý. Ví dụ trong application.yml:

~~~yaml
server:
  shutdown: graceful
spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

- Health/readiness/liveness khi được cấu hình (thường qua Spring Boot Actuator và hệ thống triển khai) giúp quyết định instance có sẵn sàng nhận lưu lượng và có cần khởi động lại hay không. Readiness không thay thế trạng thái thành công của từng tác vụ.
- Cần xử lý timeout, backpressure, pool kết nối, retry và lỗi riêng từng request/event. Không nên để một lỗi nghiệp vụ bình thường làm cả JVM kết thúc.

Cả hai đều nên xử lý tài nguyên bằng quản lý vòng đời bean, try-with-resources khi thích hợp và shutdown của executor; **khác nhau chủ yếu ở thời điểm đóng context và ý nghĩa của việc tiến trình kết thúc**.

## 7. Chọn kiến trúc theo yêu cầu, không theo annotation

Hãy trả lời lần lượt:

1. **Công việc có điều kiện kết thúc cho mỗi lần khởi động không?** Nếu có và không cần nhận công việc mới sau đó, nghiêng về one-shot.
2. **Sau công việc đầu tiên, tiến trình còn phải lắng nghe request, queue hoặc trigger mới không?** Nếu có, đó là service lâu dài, kể cả khi từng request chỉ mất vài mili giây.
3. **Ai quyết định lúc khởi chạy lại?** Một bộ lập lịch bên ngoài thường hợp với Job/CronJob; một tiến trình chờ thông điệp liên tục thường hợp với Deployment hoặc service manager.
4. **Kết quả mà hệ thống vận hành phải theo dõi là gì?** Với one-shot là kết quả từng lần chạy và exit code; với service là khả năng sẵn sàng, hiệu năng và kết quả của nhiều yêu cầu.

Ví dụ quyết định:

| Tình huống | Lựa chọn hợp lý | Lý do |
| --- | --- | --- |
| Mỗi đêm đọc tệp và xuất báo cáo rồi kết thúc | One-shot, chạy bằng lịch bên ngoài | Mỗi lần chạy có kết quả hoàn tất xác định |
| Phục vụ API tra cứu sản phẩm | Long-running service | Phải liên tục nhận request độc lập |
| Consumer Kafka nhận thông điệp cả ngày, không có HTTP | Long-running service | Cần duy trì listener dù không có web server |
| Người quản trị chạy lệnh đồng bộ một lần | One-shot | Lệnh trả kết quả/mã thoát cho caller |
| Một dịch vụ có @Scheduled chạy dọn dẹp mỗi giờ | Long-running service | Tiến trình duy trì bộ lập lịch để chờ lần kích hoạt tiếp |
| Service nạp dữ liệu cấu hình một lần lúc khởi động, sau đó phục vụ API | Long-running service | Thao tác khởi tạo một lần không quyết định vòng đời toàn hệ thống |

## 8. Các nhầm lẫn dễ gây lỗi

**Nhầm 1: “Có CommandLineRunner là one-shot”.** Sai. Runner chạy ở giai đoạn startup cho cả ứng dụng web và non-web. Gọi System.exit(...) sau SpringApplication.run(...) trong service sẽ khiến service thoát ngay, dù HTTP endpoint được đăng ký.

**Nhầm 2: “Đặt WebApplicationType.NONE thì JVM tự thoát”.** Không chắc. NONE chỉ tắt phần web runtime; thread, scheduler, consumer hoặc tài nguyên nền có thể giữ JVM sống. Ngược lại, non-web app không có việc dài hạn có thể kết thúc khi chỉ còn daemon threads mà không cần một web server.

**Nhầm 3: “ApplicationReadyEvent nghĩa là job đã hoàn thành”.** Sự kiện này chỉ đánh dấu việc khởi động và startup runners đã chạy xong; kết quả nghiệp vụ, xử lý bất đồng bộ và những request tương lai có vòng đời riêng.

**Nhầm 4: “Service chỉ cần vòng lặp vô hạn để sống”.** Vòng lặp chờ mù, sleep vô hạn hoặc busy-wait làm khó shutdown và giám sát. Hãy dùng web server, listener hoặc scheduler/executor được quản lý đúng vòng đời theo mục đích thực tế.

**Nhầm 5: “Job chạy một lần thì không cần quan tâm retry”.** Job có thể được scheduler hoặc người vận hành chạy lại sau lỗi; thao tác ghi ngoài transaction hoặc gọi API bên ngoài có thể đã thành công một phần. Cần kiểm soát việc chạy lại, idempotency và quan sát kết quả.

**Nhầm 6: “Hoàn tất một request thì đóng ApplicationContext”.** Điều này chỉ phù hợp nếu bản thân tiến trình chỉ phục vụ đúng một tác vụ được thiết kế trước. Với API/consumer, đóng context sẽ cắt khả năng nhận các request/event tiếp theo.

## 9. Tự kiểm tra

- Một chương trình Spring Boot đọc 5 triệu bản ghi, mất hai giờ, sau đó xuất file và thoát: **one-shot**, vì có điều kiện hoàn tất rõ ràng.
- Một ứng dụng không mở HTTP nhưng liên tục tiêu thụ hàng đợi: **long-running service**, vì phải tiếp nhận sự kiện mới.
- Một REST API dùng CommandLineRunner để nạp cache khi khởi động: **long-running service**, vì runner chỉ là một bước khởi tạo.
- Một Kubernetes CronJob tạo Pod, chạy xử lý rồi Pod kết thúc với exit code 0: **one-shot** cho mỗi lần kích hoạt.

**Ghi nhớ:** Câu hỏi quyết định là *“Sau khi hoàn thành công việc hiện tại, tiến trình có cần tiếp tục sống để nhận công việc mới không?”* Trả lời câu hỏi đó trước, rồi chọn runner, web server/listener, cấu hình shutdown, mã thoát và loại workload triển khai tương ứng.
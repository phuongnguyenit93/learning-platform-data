# Thông tin khởi động và `spring.main.log-startup-info`

Khi khởi chạy Spring Boot, màn hình console thường xuất hiện banner và nhiều dòng log: lớp ứng dụng đang được chạy, phiên bản Java, tiến trình (PID), profile đang hoạt động, quá trình tạo `ApplicationContext`, máy chủ web được khởi tạo và thời gian khởi động. Các dòng này giúp người phát triển nhận biết ứng dụng đã tiến đến bước nào, nhưng **không phải tất cả đều do cùng một thành phần sinh ra**.

Thuộc tính **`spring.main.log-startup-info`** điều khiển nhóm **thông tin khởi động do `SpringApplication` chủ động ghi ra**. Hiểu đúng phạm vi của thuộc tính này giúp giảm thông báo không cần thiết mà vẫn giữ được các log chẩn đoán quan trọng từ thư viện, máy chủ web và mã nghiệp vụ.

## 1. Đọc những thông tin khởi động thường gặp

Ở chế độ log mặc định, một ứng dụng Spring Boot có thể in các thông báo tương tự:

~~~text
INFO  ... c.example.StartupInfoDemo : Starting StartupInfoDemo using Java 21 ...
INFO  ... c.example.StartupInfoDemo : The following 1 profile is active: "dev"
INFO  ... o.s.b.w.embedded.tomcat.TomcatWebServer : Tomcat initialized with port 8080 (http)
INFO  ... o.s.b.w.embedded.tomcat.TomcatWebServer : Tomcat started on port 8080 (http) with context path '/'
INFO  ... c.example.StartupInfoDemo : Started StartupInfoDemo in 2.345 seconds (process running for 2.789)
~~~

Đây là **mẫu minh họa các nhóm thông báo**, không phải kết quả cố định của mọi lần chạy. Thời gian, PID, phiên bản Java, tên lớp, đường dẫn, máy chủ web và thứ tự những dòng đến từ thư viện thay đổi theo ứng dụng và môi trường.

| Nhóm hiển thị | Thông tin nhận được | Thành phần thường ghi |
| --- | --- | --- |
| `Starting StartupInfoDemo ...` | Tên ứng dụng/lớp khởi chạy, phiên bản Java, PID, vị trí chạy và các chi tiết môi trường nếu có | Bộ ghi thông tin khởi động của `SpringApplication` |
| `The following 1 profile is active ...` hoặc `No active profile set ...` | Profile đang hoạt động hoặc profile mặc định | `SpringApplication` |
| `Tomcat initialized ...`, `Tomcat started ...` | Trạng thái máy chủ HTTP nhúng | Các lớp của Tomcat/Spring Boot Web Server |
| `Started StartupInfoDemo in ...` | Thời gian từ lúc bắt đầu đến khi `ApplicationContext` đã được khởi tạo và làm mới thành công | Bộ ghi thông tin khởi động của `SpringApplication` |
| Log từ `@Service`, `@Component` hay các thư viện khác | Kết quả khởi tạo bean, kết nối, kiểm tra nghiệp vụ và chẩn đoán riêng | Logger của thành phần tương ứng |

**Không suy luận rằng mọi dòng xuất hiện trong giai đoạn startup đều là “startup info” của `SpringApplication`.** Ví dụ log Tomcat cũng xuất hiện khi khởi động nhưng do logger khác quản lý.

## 2. `spring.main.log-startup-info` là gì?

`spring.main.log-startup-info` là thuộc tính kiểu boolean của Spring Boot, được liên kết với cấu hình của `SpringApplication`. Giá trị mặc định là **`true`**.

- **`true` (mặc định):** `SpringApplication` được phép ghi thông tin mở đầu phiên chạy, các profile đang hoạt động và thông báo `Started ...` khi khởi tạo ngữ cảnh thành công, tùy ngưỡng log đang áp dụng.
- **`false`:** bỏ các thông báo khởi động nêu trên do chính `SpringApplication` phát ra, kể cả thông báo về profile và `Started ...`. Ứng dụng vẫn thực hiện quy trình khởi tạo thông thường.

Ở phiên bản Spring Boot 3.3, cờ này được sử dụng tại hai thời điểm chính: khi chuẩn bị `ApplicationContext` để quyết định có gọi `logStartupInfo(...)` và `logStartupProfileInfo(...)` hay không; sau khi làm mới context thành công để quyết định có ghi `Started ...` hay không.

### Điều gì vẫn có thể hiển thị khi đặt `false`?

| Loại đầu ra | Bị `log-startup-info=false` tắt trực tiếp? | Giải thích |
| --- | --- | --- |
| `Starting ...` của lớp chính | **Có** | Thuộc nhóm log mở đầu do `SpringApplication` ghi |
| `No active profile ...` / `The following ... profile ...` | **Có** | Là thông tin profile do `SpringApplication` ghi |
| `Started ... in ... seconds` của lớp chính | **Có** | Thuộc nhóm log hoàn tất tạo/làm mới context |
| Banner Spring Boot | **Không** | Banner được điều khiển riêng bởi `spring.main.banner-mode` |
| Log khởi tạo Tomcat, Hibernate, HikariCP hoặc thư viện | **Không** | Chúng sử dụng logger riêng; vẫn phụ thuộc vào cấu hình logging của chúng |
| `log.info(...)` trong mã ứng dụng | **Không** | Do logger và ngưỡng log của ứng dụng quyết định |
| `System.out.println(...)` trong mã ứng dụng | **Không** | In trực tiếp ra luồng đầu ra chuẩn |
| Lỗi khởi động, exception và xử lý lỗi | **Không** | Cờ không tắt cơ chế báo lỗi hoặc ngăn quá trình khởi động thất bại |

Một số dòng log vẫn có thể bị ẩn bởi **mức logging** được cấu hình ở nơi khác. Vì thế, để kết luận tác dụng của cờ này, cần giữ nguyên cấu hình log rồi chỉ thay đổi `spring.main.log-startup-info` giữa hai lần chạy.

Cờ này **không vô hiệu hóa việc tải bean, không đổi profile, không bỏ qua bước khởi động web server, không rút ngắn vòng đời của ứng dụng và không thay đổi kết quả kinh doanh**. Nó chỉ thay đổi một nhóm thông điệp dùng để quan sát quá trình khởi động.

## 3. Cơ chế xử lý khi `SpringApplication.run(...)` được gọi

Có thể hình dung các mốc liên quan đến thông tin khởi động như sau:

~~~text
main(String[] args)
    |
    v
SpringApplication.run(args)
    |
    +-- Chuẩn bị Environment, đọc cấu hình spring.main.*
    |
    +-- In banner nếu chế độ banner cho phép
    |
    +-- Tạo và chuẩn bị ApplicationContext
    |      |
    |      +-- log-startup-info=true?
    |             +-- Có: thông tin Starting ... và profile
    |             +-- Không: bỏ nhóm log này
    |
    +-- Refresh ApplicationContext, khởi tạo bean và máy chủ web nếu có
    |      +-- Các thành phần khác có thể tự ghi log
    |
    +-- log-startup-info=true?
    |      +-- Có: thông tin Started ... và thời gian startup
    |      +-- Không: bỏ nhóm log này
    |
    +-- Phát ApplicationStartedEvent và gọi ApplicationRunner / CommandLineRunner
    |
    +-- Phát ApplicationReadyEvent khi các runner hoàn tất
    |
    v
Ứng dụng sẵn sàng theo vòng đời Spring Boot
~~~

Sơ đồ mô tả **luồng liên quan đến bài học**, không liệt kê mọi callback hay listener nội bộ.

Ba điều cần phân biệt:

1. **Đã có log `Started ...` không có nghĩa mọi tác vụ sau đó đều đã hoàn tất.** Trong Spring Boot 3.3, thông báo hoàn tất khởi tạo context được ghi trước khi chạy `ApplicationRunner` và `CommandLineRunner`. `ApplicationReadyEvent` xuất hiện sau các runner.
2. **Ẩn log `Started ...` không có nghĩa ứng dụng chưa chạy.** Có thể kiểm tra trạng thái bằng sự kiện vòng đời hoặc cơ chế health/readiness nếu ứng dụng đã cấu hình chúng.
3. **Thời gian trong log không phải thời gian sẵn sàng phục vụ mọi yêu cầu nghiệp vụ.** Ví dụ công việc trong runner có thể cần thêm thời gian, phụ thuộc ngoài có thể chưa khỏe hoặc readiness chưa cho phép nhận lưu lượng.

## 4. Cấu hình qua tệp, dòng lệnh và biến môi trường

Có nhiều cách cung cấp cùng một thuộc tính. Trong một thử nghiệm, nên chọn một nguồn rõ ràng để dễ so sánh.

### Cách A — `application.properties`

Trong `src/main/resources/application.properties`:

~~~properties
spring.main.log-startup-info=false
~~~

Để quay lại hành vi mặc định, xóa dòng này hoặc đặt:

~~~properties
spring.main.log-startup-info=true
~~~

### Cách B — `application.yml`

Trong `src/main/resources/application.yml`:

~~~yaml
spring:
  main:
    log-startup-info: false
~~~

Không cần khai báo đồng thời cả `application.properties` và `application.yml` cho cùng một bài thử, vì sẽ gây khó theo dõi nguồn cấu hình thực tế.

### Cách C — Đối số ứng dụng khi chạy JAR hoặc Gradle

Với JAR thực thi do dự án Spring Boot tạo:

~~~bash
java -jar build/libs/startup-info-demo.jar --spring.main.log-startup-info=false --spring.profiles.active=dev
~~~

Với tác vụ `bootRun` của Gradle:

~~~bash
./gradlew bootRun --args="--spring.main.log-startup-info=false --spring.profiles.active=dev"
~~~

Trong PowerShell trên Windows:

~~~powershell
.\gradlew.bat bootRun --args="--spring.main.log-startup-info=false --spring.profiles.active=dev"
~~~

`startup-info-demo.jar` là tên JAR minh họa; cần dùng đúng tên tệp được tạo từ dự án của bạn. Hai đối số có tiền tố `--` được truyền cho ứng dụng, cho phép Spring Boot đưa chúng vào hệ thống cấu hình theo cơ chế mặc định. Dù thông báo về profile `dev` không còn trên startup log, **profile `dev` vẫn được kích hoạt**.

Có thể truyền system property của **JVM ứng dụng**:

~~~bash
java -Dspring.main.log-startup-info=false -jar build/libs/startup-info-demo.jar
~~~

Đối với `java -jar`, hãy đặt `-D...` **trước** `-jar`. Khi chạy qua Gradle, đừng giả định `./gradlew -Dspring.main.log-startup-info=false bootRun` tự chuyển system property của Gradle sang JVM ứng dụng. Dùng `--args` như trên hoặc cấu hình `bootRun` rõ ràng nếu cần VM options.

### Cách D — Biến môi trường

Ví dụ trong Bash:

~~~bash
SPRING_MAIN_LOG_STARTUP_INFO=false java -jar build/libs/startup-info-demo.jar
~~~

Ví dụ trong PowerShell:

~~~powershell
$env:SPRING_MAIN_LOG_STARTUP_INFO = "false"
java -jar build/libs/startup-info-demo.jar
~~~

Spring Boot hỗ trợ liên kết thuộc tính cấu hình từ biến môi trường theo quy tắc đặt tên thích hợp; tên biến ở đây tương ứng với `spring.main.log-startup-info`.

Nếu một thuộc tính được đặt ở nhiều nguồn, **quy tắc ưu tiên nguồn cấu hình** sẽ quyết định giá trị mà Spring Boot nhận. Chẳng hạn, đối số ứng dụng `--spring.main.log-startup-info=true` thường có ưu tiên cao hơn giá trị `false` trong `application.properties`. Khi thử nghiệm, kiểm tra các nguồn ghi đè trước khi kết luận thuộc tính không hoạt động.

## 5. Bật hoặc tắt bằng Java

Với điểm vào chuẩn, Spring Boot tự liên kết thuộc tính từ cấu hình:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StartupInfoDemo {
    public static void main(String[] args) {
        SpringApplication.run(StartupInfoDemo.class, args);
    }
}
~~~

Nếu cần cấu hình đối tượng `SpringApplication` trực tiếp trước khi chạy, có thể viết:

~~~java
public static void main(String[] args) {
    SpringApplication application = new SpringApplication(StartupInfoDemo.class);
    application.setLogStartupInfo(false);
    application.run(args);
}
~~~

Đoạn `main` thứ hai là **phương án thay thế** cho đoạn `main` đầu tiên, cùng nằm trong lớp `StartupInfoDemo` và cần các import đã nêu. Phương thức `setLogStartupInfo(false)` điều khiển cùng ý định ở cấp API. Khi thử nghiệm, hãy tránh đồng thời đặt cấu hình mâu thuẫn trong nhiều nguồn mà không kiểm tra thứ tự liên kết.

Nếu chỉ cần tắt thông tin khởi động theo môi trường, tệp cấu hình hoặc đối số dòng lệnh thường dễ quản lý hơn. Cách thiết lập bằng Java phù hợp khi ứng dụng tự xây dựng và tùy biến `SpringApplication`.

## 6. Ví dụ thực hành có thể chạy trong dự án Spring Boot 3.x

Tạo một dự án **Spring Boot 3.x dùng Java 17 trở lên** với ít nhất `spring-boot-starter` và Gradle hoặc Maven. Trong package `com.example.runtime`, tạo `StartupInfoDemo.java`:

~~~java
package com.example.runtime;

import java.util.Arrays;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class StartupInfoDemo {

    public static void main(String[] args) {
        SpringApplication.run(StartupInfoDemo.class, args);
    }

    @Bean
    ApplicationRunner showProfiles(Environment environment) {
        return arguments -> System.out.println(
                "APP_DIAGNOSTIC activeProfiles="
                        + Arrays.toString(environment.getActiveProfiles()));
    }
}
~~~

Đây là chương trình hoàn chỉnh **trong một dự án đã có Spring Boot và phụ thuộc của nó**, chứ không thể biên dịch chỉ bằng lệnh `javac StartupInfoDemo.java` khi không có Spring Boot trên classpath.

### Lượt 1: bật thông tin khởi động

Chạy bằng Gradle Wrapper:

~~~bash
./gradlew bootRun --args="--spring.profiles.active=dev --spring.main.log-startup-info=true"
~~~

Bạn có thể quan sát những nhóm thông báo sau (giả định mức INFO được bật):

- Thông báo `Starting StartupInfoDemo ...`.
- Thông báo profile `dev` được kích hoạt.
- Thông báo `Started StartupInfoDemo in ...` nếu việc khởi tạo context thành công.
- Dòng do **mã ví dụ** in: `APP_DIAGNOSTIC activeProfiles=[dev]`.

Các log khác tùy phụ thuộc của dự án. Với ví dụ chỉ có `spring-boot-starter`, không có lý do tự động xuất hiện log khởi động Tomcat. Nếu thêm `spring-boot-starter-web`, các dòng từ máy chủ web nhúng có thể xuất hiện.

### Lượt 2: tắt thông tin khởi động

Giữ nguyên dự án và chạy:

~~~bash
./gradlew bootRun --args="--spring.profiles.active=dev --spring.main.log-startup-info=false"
~~~

Kết quả cần so sánh:

| Dấu hiệu | `true` | `false` |
| --- | --- | --- |
| `Starting StartupInfoDemo ...` do `SpringApplication` ghi | Có, nếu logger cho phép INFO | Không |
| Thông báo profile `dev` do `SpringApplication` ghi | Có, nếu logger cho phép INFO | Không |
| `Started StartupInfoDemo in ...` do `SpringApplication` ghi | Có, nếu logger cho phép INFO | Không |
| `APP_DIAGNOSTIC activeProfiles=[dev]` từ `ApplicationRunner` | Có | Có |
| Bean được khởi tạo, runner được gọi | Có, nếu không có lỗi khác | Có, nếu không có lỗi khác |
| Banner hoặc log của các thành phần khác | Theo cấu hình riêng | Theo cấu hình riêng |

Lệnh chạy Gradle có thể phát log của **Gradle** như trạng thái tác vụ hoặc `BUILD SUCCESSFUL` sau khi tiến trình ứng dụng kết thúc; các dòng này cũng không chịu điều khiển của `spring.main.log-startup-info`.

Dòng `APP_DIAGNOSTIC activeProfiles=[dev]` là kiểm chứng quan trọng: cấu hình profile vẫn có hiệu lực dù log profile của `SpringApplication` không còn. Nếu project có thêm startup runner khác, thời điểm hoặc thứ tự dòng từ chúng phụ thuộc vào việc sắp xếp runner; riêng cơ chế bật/tắt của thuộc tính vẫn như trên.

## 7. Phân biệt với banner, mức log và `--debug`

Ba nhóm cấu hình này xử lý các việc khác nhau:

| Mục tiêu | Cấu hình phù hợp | Phạm vi |
| --- | --- | --- |
| Ẩn log mở đầu, profile và `Started ...` từ `SpringApplication` | `spring.main.log-startup-info=false` | Một nhóm log startup cụ thể |
| Ẩn hình banner Spring Boot | `spring.main.banner-mode=off` | Banner, không phải mọi log |
| Ẩn phần lớn thông báo INFO | `logging.level.root=WARN` hoặc cấu hình logger chi tiết | Tất cả logger bị ngưỡng đó chi phối; tác động rộng hơn |
| Xem thêm thông tin chẩn đoán điều kiện cấu hình tự động | `--debug` và cấu hình logging phù hợp | Chẩn đoán, không dùng để bật/tắt riêng thông tin khởi động |

Ví dụ để giảm cả hai loại đầu ra thường thấy:

~~~properties
spring.main.log-startup-info=false
spring.main.banner-mode=off
~~~

Hai dòng trên **không phải chế độ im lặng hoàn toàn**. Log từ framework, thư viện và ứng dụng vẫn có thể xuất hiện. Nếu cần thay đổi mức log, nên cấu hình chính xác logger hoặc nhóm logger liên quan và giữ lại thông báo lỗi cần thiết.

Lưu ý thêm: đặt `logging.level.root=ERROR` chỉ để ẩn `Starting ...` có thể vô tình mất cả những thông báo INFO hữu ích từ Hibernate, máy chủ web, kết nối cơ sở dữ liệu hoặc mã ứng dụng. Trường hợp chỉ muốn gọn log khởi động, `spring.main.log-startup-info=false` có phạm vi nhỏ hơn.

## 8. Thông tin khởi động và trạng thái sẵn sàng là hai việc khác nhau

Log `Started ...` chỉ cung cấp **tín hiệu quan sát** rằng một giai đoạn khởi động đã đi qua. Để điều phối hệ thống thực tế, cần dựa vào sự kiện/vùng kiểm tra trạng thái thích hợp:

- `ApplicationStartedEvent`: phát sau khi `ApplicationContext` được làm mới, trước khi gọi `ApplicationRunner` và `CommandLineRunner`.
- `ApplicationReadyEvent`: phát sau khi các runner hoàn tất; cho biết ứng dụng đã đạt giai đoạn sẵn sàng của vòng đời Spring Boot.
- **Readiness/health check**: nếu ứng dụng đã bật các cơ chế kiểm tra thích hợp, chúng cung cấp tín hiệu vận hành để bộ điều phối quyết định có chuyển lưu lượng vào ứng dụng hay chưa.

Thay đổi `spring.main.log-startup-info` không thay đổi thời điểm các sự kiện trên phát ra. Ví dụ khi dùng container orchestration, đừng dùng sự xuất hiện hay biến mất của chuỗi `Started` làm cách duy nhất để đánh giá sức khỏe ứng dụng. Khi app gặp lỗi thật trong quá trình khởi tạo, nó vẫn có thể thất bại dù startup info đã bị tắt.

## 9. Các lỗi hiểu nhầm thường gặp

**Tình huống 1: Đặt `false` nhưng vẫn thấy log Tomcat.** Điều này bình thường. Log Tomcat đến từ logger của máy chủ nhúng. Nếu muốn kiểm soát chúng, hãy tìm logger và mức log tương ứng; đừng chờ `spring.main.log-startup-info` tắt chúng.

**Tình huống 2: Đặt `true` nhưng không thấy `Starting ...`.** Kiểm tra ngưỡng log của lớp chính/gốc, nguồn cấu hình ghi đè, cách khởi chạy và vị trí thu thập log. `true` cho phép `SpringApplication` ghi log; nó không ép mọi hệ thống logging phải hiển thị INFO.

**Tình huống 3: Không thấy log profile nên tưởng profile không hoạt động.** `false` tắt thông báo nhưng không đổi `Environment.getActiveProfiles()`. Hãy kiểm tra profile qua `Environment`, cấu hình hiệu lực hoặc công cụ chẩn đoán thích hợp.

**Tình huống 4: Tắt cả banner vẫn thấy dòng `Started ...`.** `spring.main.banner-mode=off` chỉ xử lý banner. Hãy đặt `spring.main.log-startup-info=false` nếu muốn bỏ thông tin khởi động của `SpringApplication`.

**Tình huống 5: Thấy `Started ...` và khẳng định mọi công việc khởi tạo xong.** Runner có thể chưa hoàn thành. Hãy quan sát `ApplicationReadyEvent` hoặc readiness khi cần xác nhận thời điểm thích hợp cho lưu lượng.

**Tình huống 6: Truyền thuộc tính sai tiến trình.** `java -Dspring.main.log-startup-info=false -jar ...` tác động vào JVM ứng dụng. Nhưng `./gradlew -Dspring.main.log-startup-info=false bootRun` có thể chỉ đặt thuộc tính trong JVM của Gradle; để rõ ràng hãy dùng `bootRun --args="--spring.main.log-startup-info=false"`.

**Tình huống 7: Dùng `false` để “giấu” mọi thông tin khi lỗi khởi động.** Thuộc tính này không phải công cụ xử lý lỗi hoặc bảo mật. Thông báo lỗi do cơ chế khác phát ra và việc in dữ liệu nhạy cảm cần được kiểm soát tại nguồn log.

## 10. Bài tự kiểm tra

1. Nếu có `spring.main.log-startup-info=false` và `spring.main.banner-mode=console`, banner có thể xuất hiện không? **Có.** Đây là hai nhóm cấu hình độc lập.
2. Nếu đặt `--spring.profiles.active=dev` cùng `--spring.main.log-startup-info=false`, profile nào hoạt động? **`dev`.** Chỉ dòng log profile do `SpringApplication` phát ra bị ẩn.
3. Vì sao đổi `logging.level.root=WARN` khác với đổi `spring.main.log-startup-info=false`? **Vì mức log áp dụng rộng cho nhiều logger**, còn thuộc tính startup info chỉ điều khiển một nhóm thông báo từ `SpringApplication`.
4. Khi không còn log `Started`, muốn biết ứng dụng đã sẵn sàng thì dựa vào đâu? **Sự kiện `ApplicationReadyEvent`, readiness/health thích hợp và kiểm chứng vận hành**, tùy nhu cầu.
5. Khi thêm `spring-boot-starter-web` rồi thấy `Tomcat started ...` dù đã tắt startup info, có phải cấu hình sai không? **Không.** Đó là log của thành phần web server.

**Ghi nhớ:** `spring.main.log-startup-info` quyết định có ghi **các thông tin mở đầu, profile và hoàn tất giai đoạn startup của `SpringApplication`** hay không. Nó **không thay đổi quy trình chạy**, **không tắt banner**, **không vô hiệu hóa log của các thành phần khác** và **không phải tín hiệu readiness**.

### Tài liệu tham khảo

- Spring Boot 3.3 — `SpringApplication` API, `setLogStartupInfo(boolean)`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot — SpringApplication / Startup Information: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
- Spring Boot — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot 3.3 — mã nguồn `SpringApplication` để đối chiếu nhánh `logStartupInfo`: https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot/src/main/java/org/springframework/boot/SpringApplication.java

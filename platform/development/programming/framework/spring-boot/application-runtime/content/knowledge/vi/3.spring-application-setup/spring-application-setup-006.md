# Tùy chỉnh banner khi khởi động Spring Boot bằng banner.txt, Banner và Banner.Mode

## 1. Banner nằm ở đâu trong quá trình khởi chạy?

Khi gọi `SpringApplication.run(...)`, Spring Boot thường in một khối chữ hoặc hình ASCII ở đầu đầu ra khởi động, trước những thông báo như `Starting ...` và `Started ...`. Khối này được gọi là **startup banner**. Banner giúp nhận diện ứng dụng, bản phát hành hoặc thương hiệu khi xem terminal và log, nhưng **không phải** giao diện web, thông báo ứng dụng đã sẵn sàng, cơ chế ghi log nghiệp vụ hay phép kiểm tra sức khỏe.

Ba công cụ trong bài giải quyết ba nhu cầu khác nhau:

| Công cụ | Trách nhiệm | Khi nào nên dùng? |
| --- | --- | --- |
| `banner.txt` | Khai báo **nội dung** banner bằng một tài nguyên văn bản trong classpath hoặc vị trí do cấu hình chỉ định | Banner tĩnh, ASCII art, biến phiên bản/tên ứng dụng |
| `org.springframework.boot.Banner` | Tự **tạo nội dung** banner bằng Java trong phương thức `printBanner(...)` | Banner có quy tắc định dạng hoặc điều kiện tính toán bằng mã |
| `Banner.Mode` | Chọn **cách xuất** banner: console, logger hoặc tắt | Điều chỉnh theo môi trường chạy và yêu cầu thu thập log |

Có thể hình dung:

```text
SpringApplication.run(args)
    |
    v
Chuẩn bị Environment và cấu hình spring.main.*
    |
    v
Chọn nội dung banner: tài nguyên văn bản / Banner tùy chỉnh / banner mặc định
    |
    v
Banner.Mode
    +--> CONSOLE: in ra System.out
    +--> LOG:     đưa vào logger đã cấu hình
    +--> OFF:     không in banner
    |
    v
Tiếp tục chuẩn bị, làm mới ApplicationContext và khởi động ứng dụng
```

Banner xuất hiện trong giai đoạn khởi động khi `Environment` đã được chuẩn bị. Nó có thể hiển thị giá trị cấu hình mà `Environment` đang biết, nhưng không nên yêu cầu một bean nghiệp vụ phải được khởi tạo để in được banner.

## 2. Cách đơn giản nhất: đặt banner.txt trong classpath

Trong dự án Spring Boot dùng Gradle hoặc Maven, đặt file đúng đường dẫn:

```text
banner-demo/
  src/
    main/
      java/
        demo/banner/BannerDemoApplication.java
      resources/
        application.properties
        banner.txt
```

Nội dung `src/main/resources/banner.txt`:

```text
====================================
          BANNER DEMO
====================================
Application: ${spring.application.name}
Spring Boot: ${spring-boot.version}
====================================
```

`src/main/resources/application.properties`:

```properties
spring.application.name=banner-demo
```

Lớp khởi chạy cơ bản tại `src/main/java/demo/banner/BannerDemoApplication.java`:

```java
package demo.banner;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BannerDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(BannerDemoApplication.class, args);
    }
}
```

Đây là lớp Java độc lập trong một **dự án Spring Boot có plugin và dependency tương ứng**; nó không phải chương trình Java thuần chạy chỉ bằng `javac` không có thư viện. Dependency `spring-boot-starter` đủ cho ví dụ khởi chạy không cần web server; dự án web có thể dùng `spring-boot-starter-web`.

Chạy bằng Gradle wrapper của dự án:

```bash
./gradlew bootRun
```

Hoặc đóng gói rồi chạy tệp JAR thực tế do build tạo ra:

```bash
./gradlew bootJar
java -jar build/libs/ten-file-jar-thuc-te.jar
```

Với bản Spring Boot có phiên bản giả sử là `3.3.x`, các dòng banner có dạng:

```text
====================================
          BANNER DEMO
====================================
Application: banner-demo
Spring Boot: 3.3.x
====================================
```

`3.3.x` trong khối trên **chỉ là ký hiệu minh họa**; giá trị thực tế phụ thuộc phiên bản Spring Boot đang dùng. Các dòng log khởi động khác vẫn xuất hiện sau banner.

**Vì sao đặt trong `src/main/resources`?** Build tool sao chép file vào tài nguyên đầu ra và đóng gói cùng ứng dụng. Khi tạo executable Spring Boot JAR, file thường nằm ở `BOOT-INF/classes/banner.txt`. Spring Boot có thể đọc tài nguyên đó từ classpath; không cần giữ thư mục `src/main/resources` trên máy chạy JAR.

Không đặt nhầm vào `src/test/resources` nếu banner cần xuất hiện ở bản phát hành; tài nguyên test thường không được đóng vào application JAR.

## 3. Dời file hoặc đổi tên với spring.banner.location

Tên mặc định là `banner.txt` ở gốc classpath. Nếu muốn nhóm tài nguyên theo thư mục, tạo:

```text
src/main/resources/branding/welcome.txt
```

Sau đó đặt:

```properties
spring.banner.location=classpath:branding/welcome.txt
```

Cũng có thể truyền vị trí trực tiếp khi chạy:

```bash
java -jar app.jar --spring.banner.location=classpath:branding/welcome.txt
```

Nếu muốn banner do bộ phận vận hành quản lý độc lập với artifact, có thể trỏ vào hệ thống tệp, ví dụ trên Linux:

```properties
spring.banner.location=file:/opt/demo/branding/welcome.txt
```

Phân biệt:

- `classpath:branding/welcome.txt`: tìm một tài nguyên trên **runtime classpath**; thích hợp khi file đã được đóng gói.
- `file:/opt/demo/branding/welcome.txt`: đọc một **tệp vật lý** từ đường dẫn tuyệt đối trên Linux.
- `file:./branding/welcome.txt`: tra cứu tệp ngoài tương đối với **working directory của tiến trình**; đổi cách chạy có thể đổi tệp được tìm thấy.

Không dùng `src/main/resources/banner.txt` như đường dẫn tương đối của hệ thống tệp để cấu hình bản phát hành. Cấu trúc thư mục mã nguồn có thể không tồn tại khi triển khai.

Đặt `spring.banner.charset=UTF-8` nếu cần chỉ rõ cách giải mã tệp văn bản. UTF-8 là mặc định trong Spring Boot hiện đại; dùng UTF-8 khi ghi tiếng Việt và các ký tự Unicode. Nếu terminal hiển thị lỗi dấu hoặc các cột ASCII bị lệch, hãy kiểm tra cả encoding của file, encoding/locale đầu ra và phông chữ terminal. Không phải mọi ký tự Unicode đều có bề rộng hiển thị bằng một cột.

## 4. Các biến thay thế trong banner.txt

Spring Boot có thể thay thế các placeholder trong file bằng dữ liệu đã có trong `Environment` và một số biến banner đặc biệt.

| Biến trong file banner | Ý nghĩa |
| --- | --- |
| `${spring.application.name}` | Lấy cấu hình `spring.application.name` từ `Environment` |
| `${spring-boot.version}` | Phiên bản thư viện Spring Boot tại thời điểm chạy |
| `${spring-boot.formatted-version}` | Phiên bản Spring Boot được định dạng để hiển thị, ví dụ `(v3.3.x)` |
| `${application.title}` | Tên ứng dụng từ thuộc tính `Implementation-Title` trong manifest, nếu được cung cấp |
| `${application.version}` | Phiên bản ứng dụng từ `Implementation-Version` trong manifest, nếu được cung cấp |
| `${application.formatted-version}` | Biến phiên bản ứng dụng được định dạng để hiển thị |
| `${AnsiColor.GREEN}`, `${AnsiColor.DEFAULT}` | Mã điều khiển màu chữ ANSI khi môi trường hỗ trợ |

Ví dụ một file không phụ thuộc giá trị phiên bản của chính ứng dụng:

```text
${AnsiColor.GREEN}=== ${spring.application.name} ===${AnsiColor.DEFAULT}
Powered by Spring Boot ${spring-boot.version}
```

Nếu muốn dùng `${application.version}`, cần hiểu nguồn của nó. Spring Boot lấy phiên bản ứng dụng qua thông tin manifest và cơ chế launcher hỗ trợ. Khi chạy qua IDE hoặc khởi chạy class trực tiếp từ các thư mục đầu ra, giá trị có thể **không hiện như khi chạy executable JAR**. Tương tự, trong native image, nhóm biến `application.*` không được bảo đảm như với Spring Boot launcher. Không lấy các biến này làm đầu vào điều khiển nghiệp vụ.

Các placeholder cấu hình cũng phụ thuộc nguồn property tại thời điểm in banner. Để tránh dòng trống hoặc không giải quyết được biến, khai báo rõ các khóa muốn hiển thị hoặc thử nghiệm với cách khởi động thực tế.

**Màu ANSI** có thể tự động bật/tắt tùy môi trường và khả năng hỗ trợ terminal. Nếu muốn thử màu ở máy phát triển:

```properties
spring.output.ansi.enabled=always
```

Nên kiểm tra hệ thống thu thập log trước khi ép màu trong môi trường production, vì escape sequence có thể xuất hiện thành ký tự khó đọc trong log lưu trữ. `spring.output.ansi.enabled` liên quan màu đầu ra; nó không chọn `Banner.Mode`.

## 5. Banner.Mode: CONSOLE, LOG và OFF

`Banner.Mode` là enum lồng trong `org.springframework.boot.Banner`. Ba giá trị cần biết:

| Mode | Banner được đưa đi đâu? | Hệ quả quan sát |
| --- | --- | --- |
| `Banner.Mode.CONSOLE` | `System.out` | Thường thấy trực tiếp ở terminal/stdout, không nhất thiết đi qua pattern/level/filter của logger |
| `Banner.Mode.LOG` | Hệ thống logger Spring Boot sử dụng | Phụ thuộc cấu hình mức log, appender/handler và nơi log được thu thập |
| `Banner.Mode.OFF` | Không xuất banner | Ẩn riêng banner; ứng dụng vẫn khởi chạy và các dòng log khác vẫn có thể xuất hiện |

Cấu hình bằng `application.properties`:

```properties
# Chọn đúng một giá trị: console, log hoặc off.
spring.main.banner-mode=console
```

Đổi mode bằng tham số dòng lệnh mà không phải sửa artifact:

```bash
java -jar app.jar --spring.main.banner-mode=off
```

Hoặc:

```bash
java -jar app.jar --spring.main.banner-mode=log
```

Dạng YAML tương đương:

```yaml
spring:
  main:
    banner-mode: log
```

**Đặt mode không làm thay đổi nội dung banner.** Nếu `banner.txt` có nội dung `BANNER DEMO`, chuyển `console` sang `log` chỉ đổi đường xuất; chuyển sang `off` thì bỏ qua việc in banner. Không nhầm `off` với việc vô hiệu hóa mọi logging, dừng ứng dụng hoặc thay đổi health/readiness.

**Lưu ý với LOG:** banner được đưa qua logger nên có thể không thấy nếu cấu hình mức log hay appender loại bỏ thông báo. Không thấy banner trong file log không tự chứng minh rằng Spring Boot chưa khởi chạy. Với `CONSOLE`, việc chuyển hướng stdout của container hoặc service quyết định nơi người vận hành nhìn thấy nó.

## 6. Cấu hình Banner.Mode trực tiếp trong Java

Khi muốn quyết định mode trong mã khởi động, thay lệnh tĩnh `SpringApplication.run(...)` bằng một instance:

```java
package demo.banner;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BannerDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(BannerDemoApplication.class);

        application.setBannerMode(Banner.Mode.CONSOLE);
        application.run(args);
    }
}
```

Các phương án:

```java
application.setBannerMode(Banner.Mode.OFF);     // Không in banner
application.setBannerMode(Banner.Mode.CONSOLE); // In ra stdout
application.setBannerMode(Banner.Mode.LOG);     // Gửi qua logger
```

Ba dòng này là **ba lựa chọn thay thế**, không đặt liên tiếp trong chương trình thực tế vì dòng cuối sẽ thay dòng trước.

Có thể cấu hình bằng `SpringApplicationBuilder`:

```java
new SpringApplicationBuilder(BannerDemoApplication.class)
        .bannerMode(Banner.Mode.OFF)
        .run(args);
```

Đoạn trên cần import `org.springframework.boot.builder.SpringApplicationBuilder` và nằm trong phương thức khởi động phù hợp; đây là phương án khác với cách tạo `new SpringApplication(...)`.

**Quan hệ giữa code và cấu hình ngoài:** `spring.main.banner-mode` là thuộc tính được Spring Boot bind vào `SpringApplication` trong giai đoạn khởi động. Cấu hình ngoài có thể ghi đè thiết lập mode đã đặt bằng Java. Ví dụ nếu code gọi `setBannerMode(OFF)` nhưng `application.properties` được nạp đặt `spring.main.banner-mode=console`, kết quả có thể là vẫn in banner theo cấu hình. Hãy chọn một nơi cấu hình chủ đạo và kiểm tra các nguồn property đang hoạt động trước khi kết luận rằng setter bị bỏ qua.

## 7. Khi cần logic riêng: triển khai org.springframework.boot.Banner

File `banner.txt` đủ cho nội dung tĩnh và placeholder. Nếu muốn format tùy theo environment, nhóm triển khai hoặc một quy tắc đơn giản, cài đặt interface `Banner`.

Tạo file `src/main/java/demo/banner/RuntimeBanner.java`:

```java
package demo.banner;

import java.io.PrintStream;
import org.springframework.boot.Banner;
import org.springframework.core.env.Environment;

public final class RuntimeBanner implements Banner {

    @Override
    public void printBanner(
            Environment environment,
            Class<?> sourceClass,
            PrintStream out) {

        String name = environment.getProperty(
                "spring.application.name", "banner-demo");
        String stage = environment.getProperty(
                "app.stage", "local");

        out.println("====================================");
        out.println(" Application: " + name);
        out.println(" Stage: " + stage);
        out.println("====================================");
    }
}
```

Trong `BannerDemoApplication`, đăng ký bằng `setBanner(...)`:

```java
package demo.banner;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BannerDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(BannerDemoApplication.class);

        application.setBanner(new RuntimeBanner());
        application.setBannerMode(Banner.Mode.CONSOLE);
        application.run(args);
    }
}
```

Cấu hình ví dụ:

```properties
spring.application.name=banner-demo
app.stage=development
```

Nếu chương trình chọn `RuntimeBanner` (và không có tài nguyên banner văn bản được ưu tiên hơn), đầu ra banner từ đoạn `printBanner` là:

```text
====================================
 Application: banner-demo
 Stage: development
====================================
```

**Ba tham số trong `printBanner`:**

- `Environment environment` cho phép đọc các cấu hình đã có khi banner được tạo. Nên dùng `getProperty(key, defaultValue)` cho các giá trị tùy chọn.
- `Class<?> sourceClass` cung cấp thông tin về lớp nguồn của ứng dụng trong ngữ cảnh thích hợp; nên xử lý cả trường hợp không có lớp nguồn. Ví dụ trên không cần dùng tham số này.
- `PrintStream out` là luồng **Spring Boot cung cấp** để in banner. Dùng `out.print(...)` / `out.println(...)`, không tùy tiện chuyển sang `System.out`. Khi mode là `LOG`, Spring Boot có thể kết xuất banner sang bộ đệm trước khi chuyển vào logger; in thẳng ra `System.out` sẽ làm sai ý định cấu hình.

`Banner` là một callback chạy trong giai đoạn khởi động sớm. Không nên xây dựng banner dựa vào `@Autowired`, bean nghiệp vụ, kết nối cơ sở dữ liệu hoặc network call vì các thành phần ấy có thể chưa sẵn sàng. Banner nên tạo đầu ra nhanh, ổn định và an toàn.

Đặc biệt, **`setBanner(new RuntimeBanner())` không có nghĩa là luôn bỏ qua `banner.txt`**. Trong cơ chế in banner của Spring Boot, tài nguyên banner văn bản tìm được theo `spring.banner.location` có thể được ưu tiên so với `Banner` đăng ký làm fallback. Nếu đang thử ví dụ Java nhưng vẫn thấy ASCII art từ file, hãy bỏ/đổi tài nguyên `banner.txt` phù hợp, hoặc chọn một hướng tùy chỉnh nhất quán. Không kết luận rằng `printBanner` bị lỗi chỉ vì nó chưa được gọi.

## 8. Mô hình chọn nội dung: file, code và mặc định

Cần phân biệt **chọn nội dung** với **chọn nơi xuất**. Một quy trình suy luận thực tế với banner văn bản là:

```text
Có banner.txt hoặc tài nguyên từ spring.banner.location?
   |
   +-- Có  ---> Nội dung trong tài nguyên văn bản
   |
   +-- Không --> Có Banner tùy chỉnh qua setBanner(...)?
                   |
                   +-- Có  ---> Nội dung do printBanner(...) tạo
                   |
                   +-- Không --> Banner Spring Boot mặc định
                                           |
                                           v
                                  Kiểm tra Banner.Mode
```

Sơ đồ phản ánh ưu tiên cơ bản giữa tài nguyên banner văn bản, fallback banner lập trình và banner mặc định. Nếu dự án dùng các loại banner tài nguyên khác theo tính năng của phiên bản Spring Boot đang dùng, cần đối chiếu thêm hành vi hỗ trợ ở phiên bản đó.

Các tình huống:

1. Chỉ có `src/main/resources/banner.txt` và dùng `CONSOLE`: in banner trong file.
2. Không có banner riêng, không gọi `setBanner(...)` và dùng `CONSOLE`: hiển thị banner Spring Boot mặc định.
3. Không có banner file, có `setBanner(new RuntimeBanner())` và dùng `LOG`: nội dung do Java tạo được gửi tới logger.
4. Có `banner.txt`, đồng thời có `setBanner(new RuntimeBanner())`: tài nguyên banner văn bản thường được chọn trước fallback trong cơ chế trên.
5. Bất kể nguồn nội dung, `Banner.Mode.OFF`: bỏ qua việc hiển thị banner.

Một lỗi hay gặp là đặt `spring.banner.location` trỏ sai đường dẫn rồi kỳ vọng sẽ thấy nội dung của file đó. Hãy kiểm tra file thực sự có trong runtime classpath hoặc filesystem và xem có fallback banner được chọn thay thế hay không.

## 9. Thực hành: chạy cùng một ứng dụng ở cả ba mode

Giữ dự án trong mục 2, có `banner.txt` và `spring.application.name=banner-demo`. Thử lần lượt từng mode, mỗi lần là **một quá trình chạy riêng**:

```bash
./gradlew bootRun --args='--spring.main.banner-mode=console'
./gradlew bootRun --args='--spring.main.banner-mode=log'
./gradlew bootRun --args='--spring.main.banner-mode=off'
```

Các dòng lệnh minh họa cho shell hiểu dấu nháy đơn như Bash; nếu môi trường PowerShell hoặc plugin khác xử lý tham số khác, dùng cú pháp trích dẫn tương ứng.

Kết quả mong đợi:

| Lượt chạy | Điều cần kiểm tra |
| --- | --- |
| `console` | Khối `BANNER DEMO` xuất hiện trực tiếp trên stdout trước hoặc cùng giai đoạn các dòng log khởi động |
| `log` | Khối banner được gửi qua logger; quan sát output/appender tương ứng và mức INFO |
| `off` | Khối banner không xuất hiện, nhưng ứng dụng vẫn khởi động bình thường và các dòng log khởi động có thể còn |

Nếu chạy bằng executable JAR:

```bash
java -jar app.jar --spring.main.banner-mode=console
java -jar app.jar --spring.main.banner-mode=log
java -jar app.jar --spring.main.banner-mode=off
```

Thay `app.jar` bằng đường dẫn artifact đã build. Đối với ứng dụng không có web server, tiến trình có thể tự kết thúc sau khi hoàn tất khởi chạy nếu không có thành phần giữ tiến trình hoạt động; điều này không làm thí nghiệm banner mất ý nghĩa.

**Thử nghiệm tiếp theo:** bỏ `banner.txt` khỏi tài nguyên build, khai báo `setBanner(new RuntimeBanner())`, rồi quan sát đầu ra. Sau đó đưa `banner.txt` trở lại và so sánh. Khi thay đổi tài nguyên, build lại artifact để tránh dùng JAR cũ.

## 10. Banner và logging: những điều dễ hiểu nhầm

**CONSOLE không giống LOG.** `CONSOLE` in trực tiếp ra stdout thông qua cơ chế của Spring Boot; `LOG` đưa nội dung vào logger. Khi container gửi stdout và log của ứng dụng về chung một nơi, người quan sát có thể tưởng chúng là cùng cơ chế. Sự khác biệt xuất hiện khi có log pattern, lọc level, appender hoặc chính sách lưu log.

**Banner không chứng minh ứng dụng đã sẵn sàng.** Nó được tạo ở giai đoạn đầu của quá trình khởi động, trước khi có bảo đảm rằng mọi bean khởi tạo thành công hay ứng dụng sẵn sàng xử lý yêu cầu. Dùng health checks, `ApplicationReadyEvent` hoặc cơ chế readiness để xác định trạng thái phục vụ, không quét chuỗi banner.

**OFF không tắt log.** `spring.main.banner-mode=off` chỉ điều khiển banner. Nếu muốn giảm chi tiết các thông báo khởi động, đó là cấu hình khác của Spring Boot hoặc logging, ví dụ `spring.main.log-startup-info`. Không trộn chúng vào cùng một thiết lập.

**ANSI không đảm bảo màu ở mọi nơi.** Một số terminal hỗ trợ màu, trong khi log viewer hoặc file text có thể giữ nguyên escape code. Với banner cần xuất vào file log hoặc hệ thống tập trung, ưu tiên văn bản thuần dễ đọc.

**Không in bí mật trong banner.** Dù `Environment` cho phép truy cập property, banner có thể được gửi ra terminal hoặc hệ thống log của nhiều người. Không lấy mật khẩu, API key, connection string nhạy cảm hay token để in, kể cả chỉ ở môi trường thử nghiệm.

**Không biến banner thành logic nghiệp vụ.** Tránh dựa vào banner để thực hiện migration, gọi API hay thiết lập trạng thái ứng dụng. Nếu banner phát sinh ngoại lệ, quá trình khởi chạy có thể chịu ảnh hưởng không cần thiết.

## 11. Xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân nên xem | Hướng xử lý |
| --- | --- | --- |
| Vẫn thấy banner Spring Boot mặc định | `banner.txt` chưa nằm trên classpath hoặc `spring.banner.location` sai | Kiểm tra `src/main/resources/banner.txt`, build lại và xem nội dung JAR |
| Không thấy banner nào | `spring.main.banner-mode=off`, cấu hình ngoài ghi đè mode hoặc logger đã lọc khi dùng LOG | Kiểm tra mode thực tế, tham số chạy và logging |
| Đã gọi `setBanner(...)` nhưng nội dung Java không xuất hiện | Có banner text resource được chọn trước fallback | Loại bỏ/đổi vị trí banner text hoặc dùng duy nhất một cơ chế |
| Tên ứng dụng không thay thế trong file | Thiếu `spring.application.name` trong `Environment` hoặc lỗi cú pháp placeholder | Khai báo property, giữ cú pháp `${spring.application.name}` |
| `${application.version}` không có giá trị như mong đợi | Không có `Implementation-Version` trong manifest hoặc chạy bằng launcher không cung cấp giá trị | Kiểm tra manifest và thử lại qua executable Spring Boot JAR |
| Chữ tiếng Việt hoặc ASCII bị vỡ | Encoding file/terminal không khớp, font hiển thị khác độ rộng | Lưu file UTF-8, kiểm tra `spring.banner.charset`, font và encoding đầu ra |
| Màu không hiện hoặc hiện chuỗi escape lạ | Terminal không hỗ trợ ANSI, cấu hình ANSI không thích hợp hoặc log sink không xử lý escape | Kiểm tra `spring.output.ansi.enabled`; ưu tiên banner không màu trong hệ thống log |
| Cùng ứng dụng nhưng banner ở môi trường khác nhau | Profile, cấu hình ngoài, tham số `spring.banner.location` hoặc working directory khác | Xác định location thực tế theo runtime classpath/đường dẫn tuyệt đối |
| Banner xuất hiện nhưng service vẫn lỗi khởi động | Banner in trước khi application ready | Kiểm tra stack trace, log lỗi và readiness độc lập |

Có thể kiểm tra việc đóng gói banner bằng lệnh sau, với tên JAR thật:

```bash
jar tf build/libs/app.jar
```

Trong danh sách, hãy tìm entry `BOOT-INF/classes/banner.txt` hoặc đường dẫn bạn đã cấu hình dưới `BOOT-INF/classes/branding/`. Tên `app.jar` chỉ là ví dụ.

Nếu `LOG` không xuất hiện trong khi `CONSOLE` có, hãy xem cấu hình logging, mức log và appender trước khi sửa file banner. Nếu `CONSOLE` không xuất hiện mà `OFF` đang được đặt trong nguồn cấu hình bên ngoài, thay đổi mã `setBannerMode(...)` một mình có thể chưa đủ.

## 12. Cách chọn trong dự án thực tế

Với dự án nhỏ hoặc bản phát hành có ASCII art cố định, chọn **`banner.txt`**. Nó đơn giản, dễ review và người thiết kế có thể thay nội dung mà không sửa mã Java.

Với banner cần định dạng có điều kiện từ cấu hình nhưng vẫn chỉ dựa vào dữ liệu có sẵn lúc khởi động, chọn **`Banner` tùy chỉnh**. Hạn chế thao tác có tác dụng phụ và chỉ in ra `PrintStream out`.

Với ứng dụng chạy trong hệ thống gom log, cân nhắc **`Banner.Mode.LOG`** khi cần banner đi theo pipeline log; chọn **`OFF`** nếu banner chỉ gây nhiễu. Chọn **`CONSOLE`** khi quan sát trực tiếp stdout là mục đích chính. Đây là lựa chọn vận hành chứ không phải thay đổi tính năng nghiệp vụ của ứng dụng.

Một chính sách dễ bảo trì:

- Giữ một nguồn banner chính: file văn bản **hoặc** callback Java.
- Dùng `spring.main.banner-mode` để tùy chỉnh cách xuất theo từng môi trường.
- Dùng tên ứng dụng/phiên bản được công bố hợp lệ, không in bí mật.
- Kiểm tra cả `bootRun` và executable JAR, nhất là khi dùng `application.version` hoặc đường dẫn file ngoài.
- Đừng coi dòng banner là tín hiệu ứng dụng đã ready.

## 13. Câu hỏi tự kiểm tra

1. Vì sao đặt `banner.txt` trong `src/main/resources` có thể hoạt động sau `java -jar`, còn trỏ bằng đường dẫn filesystem `src/main/resources/banner.txt` có thể thất bại?
2. Nếu muốn banner đi qua appender của logger, nên đặt `spring.main.banner-mode` là giá trị nào? Vì sao `CONSOLE` có thể khác dù đầu ra cùng xuất hiện trong terminal?
3. `spring.main.banner-mode=off` có đồng nghĩa với vô hiệu hóa toàn bộ log và health check không?
4. Tại sao `${spring-boot.version}` thường ổn định hơn `${application.version}` giữa cách chạy IDE và executable JAR?
5. Khi đã cài `application.setBanner(new RuntimeBanner())` nhưng vẫn thấy nội dung `banner.txt`, cần kiểm tra điều gì?
6. Vì sao nên dùng `out.println(...)` trong `Banner#printBanner(...)` thay vì gọi trực tiếp `System.out.println(...)`?
7. Banner xuất hiện có chứng minh toàn bộ `ApplicationContext` đã khởi tạo thành công và ứng dụng đang nhận request được không?

Bài thực hành kết thúc khi bạn có thể tự tạo banner tĩnh, thay banner bằng Java, chuyển ba mode mà không sửa nội dung, kiểm chứng khác biệt giữa `bootRun` và JAR, và giải thích nguồn cấu hình nào quyết định kết quả.

**Tham khảo chính thức:** [Spring Boot 3.3 — SpringApplication: Customizing the Banner](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html) và [Spring Boot — Externalize the Configuration of SpringApplication](https://docs.spring.io/spring-boot/how-to/properties-and-configuration.html).

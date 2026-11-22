# Thứ tự chung khi đồng thời có ApplicationRunner và CommandLineRunner trong Spring Boot

## 1. Câu trả lời cốt lõi

Trong Spring Boot, `ApplicationRunner` và `CommandLineRunner` đều là những callback khởi động được gọi **sau khi `ApplicationContext` đã được refresh thành công, nhưng trước khi quá trình `SpringApplication.run(...)` hoàn tất**.

Khi **cùng một ứng dụng có bean của cả hai interface**, Spring Boot **không áp dụng nguyên tắc "chạy hết `ApplicationRunner` rồi mới chạy `CommandLineRunner`" như một quy tắc ưu tiên bắt buộc**. Thay vào đó, hai nhóm runner cùng tham gia **một thứ tự sắp xếp chung**, có thể điều khiển bằng:

- `org.springframework.core.annotation.Order`: annotation `@Order(n)` trên class runner.
- `org.springframework.core.Ordered`: interface cho phép bean cung cấp giá trị thứ tự qua `getOrder()`.

**Giá trị order nhỏ hơn được ưu tiên chạy trước**; giá trị lớn hơn chạy sau, bất kể bean triển khai `ApplicationRunner` hay `CommandLineRunner`.

Ví dụ có bốn bean:

| Bean | Interface | Giá trị order | Vị trí gọi |
| --- | --- | ---: | ---: |
| `prepareRunner` | `CommandLineRunner` | 10 | 1 |
| `loadRunner` | `ApplicationRunner` | 20 | 2 |
| `verifyRunner` | `CommandLineRunner` | 30 | 3 |
| `reportRunner` | `ApplicationRunner` | 40 | 4 |

Thứ tự sẽ là:

```text
CommandLineRunner (10)
        ↓
ApplicationRunner (20)
        ↓
CommandLineRunner (30)
        ↓
ApplicationRunner (40)
        ↓
ApplicationReadyEvent
```

**Không có hai hàng đợi độc lập theo loại runner**. Thứ tự trong ví dụ là kết quả của giá trị order, không phải tên interface, tên bean, tên file hoặc vị trí khai báo method.

> Phạm vi: Bài học mô tả Spring Boot 3.3.x / Spring Framework 6.x với Java 17 trở lên và luồng khởi động `SpringApplication` bình thường. Các API và nguyên tắc sắp xếp được thể hiện trong tài liệu Spring Boot; khi nâng cấp phiên bản lớn, nên đối chiếu lại Javadoc và thực hành kiểm tra.

## 2. Hai interface giống và khác nhau ở điểm nào?

Hai interface đều có một phương thức `run`, nhưng khác kiểu tham số:

```java
// Spring Boot API, rút gọn để đối chiếu:
public interface CommandLineRunner {
    void run(String... args) throws Exception;
}

public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}
```

Đây là **chữ ký minh họa**, không phải hai file mà ứng dụng cần định nghĩa lại. Hãy import interface có sẵn từ `org.springframework.boot`.

| Khía cạnh | `CommandLineRunner` | `ApplicationRunner` |
| --- | --- | --- |
| Phương thức callback | `run(String... args)` | `run(ApplicationArguments args)` |
| Dữ liệu đầu vào | Mảng chuỗi đối số gốc từ `main` | Đối tượng phân tích đối số của Spring Boot |
| Đọc option `--mode=demo` | Tự phân tích chuỗi hoặc dùng API khác | `containsOption("mode")`, `getOptionValues("mode")` |
| Đọc positional arguments | Tự kiểm tra `args` | `getNonOptionArgs()` |
| Đăng ký | Bean Spring, thường `@Component` hoặc `@Bean` | Bean Spring, thường `@Component` hoặc `@Bean` |
| Thời điểm gọi | Giai đoạn runners sau refresh | Cùng giai đoạn runners sau refresh |
| Điều khiển thứ tự | `@Order` hoặc `Ordered` | Cùng cơ chế `@Order` hoặc `Ordered` |

**Không có interface nào mặc nhiên "cao cấp hơn" để được chạy trước.** Chọn `ApplicationRunner` khi cần truy cập tham số được phân loại; chọn `CommandLineRunner` khi muốn xử lý mảng đối số gốc, viết lệnh nhỏ hoặc đã có API nhận `String[]`.

Ví dụ nhận tham số:

```bash
java -jar app.jar --mode=demo report.csv
```

Tại runtime:

- Với `CommandLineRunner`, `args` về bản chất chứa `"--mode=demo"` và `"report.csv"`.
- Với `ApplicationRunner`, `args.containsOption("mode")` là `true`, `args.getOptionValues("mode")` chứa `"demo"` và `args.getNonOptionArgs()` chứa `"report.csv"`.
- `ApplicationArguments.getSourceArgs()` vẫn cho phép lấy lại mảng đối số gốc.

Ví dụ này là một lệnh minh họa, yêu cầu có file JAR tương ứng. Đừng nhầm `ApplicationArguments` với `Environment`: việc một option dòng lệnh đồng thời được đưa vào property sources là một cơ chế cấu hình riêng của Spring Boot.

## 3. SpringApplication xử lý runners vào thời điểm nào?

Luồng khởi động rút gọn:

```text
SpringApplication.run(...)
    |
    +-- Chuẩn bị Environment
    +-- Tạo ApplicationContext
    +-- Đăng ký bean definitions và refresh context
    |      +-- khởi tạo các singleton không lazy phù hợp
    |      +-- thực hiện callback khởi tạo bean
    |
    +-- ApplicationStartedEvent
    |      (context đã refresh, runners chưa chạy)
    |
    +-- Thu thập hai nhóm runner:
    |      ApplicationRunner beans
    |      CommandLineRunner beans
    |
    +-- Sắp xếp chung theo order
    |
    +-- Lần lượt gọi run(...) trên các runner
    |
    +-- ApplicationReadyEvent
    |      (chỉ khi giai đoạn runners hoàn tất thành công)
    |
    +-- SpringApplication.run(...) trả về context
```

Tất cả những runner thông thường chạy trong giai đoạn này khi `SpringApplication.run` thực sự khởi động ứng dụng. Chúng **không tự chạy vào lúc bean được tạo**, không chạy do phương thức `@PostConstruct` của một bean khác và không đợi đến lần HTTP request đầu tiên.

Điều này giải thích một số hiện tượng:

1. `@PostConstruct` của bean runner có thể chạy **trước** cả hai loại `run(...)`, bởi việc tạo bean diễn ra trong quá trình refresh.
2. `ApplicationStartedEvent` được phát trước giai đoạn gọi runner.
3. `ApplicationReadyEvent` được phát sau các runner, và không phát trên đường khởi động lỗi.
4. Một runner chặn quá lâu sẽ kéo dài thời gian startup và làm chậm việc đạt trạng thái ready.
5. Khi một runner phát sinh exception làm `SpringApplication.run` thất bại, không thể mặc định các runner xếp sau vẫn được gọi.

Spring Boot khuyến nghị runner cho công việc cần thực hiện **sau khi context đã dựng xong nhưng trước khi ứng dụng được báo ready**, ví dụ kiểm tra một điều kiện khởi động, nạp dữ liệu nhỏ hoặc thiết lập một trạng thái cần thiết.

## 4. Vì sao hai loại được xếp chung chứ không chạy theo nhóm?

Về ý tưởng, việc thực thi runners trong Spring Boot 3.3 có thể mô tả như sau:

```text
1. Lấy các bean thuộc ApplicationRunner từ context
2. Lấy các bean thuộc CommandLineRunner từ context
3. Đưa chúng vào danh sách ứng viên chung
4. Sắp xếp ứng viên bằng bộ so sánh hiểu Ordered / @Order
5. Tránh lặp cùng một instance runner trong vòng lặp thích hợp
6. Duyệt theo thứ tự đã sắp và gọi callback tương ứng
```

Đoạn Java dưới đây là **pseudo-code diễn giải cơ chế**, không phải source nguyên văn của Spring Boot và không có ý định biên dịch độc lập:

```java
List<Object> runners = new ArrayList<>();

runners.addAll(findApplicationRunners());
runners.addAll(findCommandLineRunners());

AnnotationAwareOrderComparator.sort(runners);

for (Object runner : deduplicateInOrder(runners)) {
    if (runner instanceof ApplicationRunner applicationRunner) {
        applicationRunner.run(applicationArguments);
    }
    if (runner instanceof CommandLineRunner commandLineRunner) {
        commandLineRunner.run(rawArguments);
    }
}
```

Các hàm `findApplicationRunners`, `findCommandLineRunners` và `deduplicateInOrder` trong pseudo-code chỉ biểu diễn ý tưởng. Khi đọc code Spring Boot 3.3 thực tế, có thể quan sát luồng `SpringApplication#callRunners` và cách sử dụng `AnnotationAwareOrderComparator`.

**Chỗ cần ghi nhớ:** cả hai nhóm cùng được đưa vào việc so sánh giá trị order. Spring Boot không chạy một vòng `ApplicationRunner` hoàn chỉnh rồi mới mở vòng `CommandLineRunner` như một hợp đồng vận hành.

Nếu chưa đặt order, bạn có thể **quan sát** một thứ tự xuất hiện lặp lại qua nhiều lần chạy do thứ tự duyệt bean trong một bản Boot cụ thể. Đừng biến quan sát đó thành phụ thuộc nghiệp vụ. Chỉ các quan hệ order được khai báo rõ, với giá trị khác nhau, mới nên là điều kiện để ứng dụng quyết định trình tự.

## 5. Các quy tắc của @Order và Ordered

### 5.1. Giá trị thấp hơn chạy trước

Ví dụ:

```java
@Order(-10)
@Component
class FirstStartupTask implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("first");
    }
}

@Order(20)
@Component
class SecondStartupTask implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("second");
    }
}
```

Đoạn này thuộc một dự án Spring Boot có import `@Component`, `@Order`, hai interface runner và `ApplicationArguments`; mỗi class có thể đặt trong file riêng hoặc cùng file Java nếu không trùng public class.

Khi cả hai bean được đăng ký đúng, kết quả là:

```text
first
second
```

**`-10` sớm hơn `20`**, vì giá trị nhỏ hơn được ưu tiên. Giá trị order có thể âm, bằng 0 hoặc dương.

### 5.2. Ordered là lựa chọn bằng interface

Bean có thể cung cấp thứ tự qua:

```java
@Component
class ExplicitlyOrderedRunner implements ApplicationRunner, Ordered {

    @Override
    public int getOrder() {
        return 5;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("order 5");
    }
}
```

Đoạn này cần import `org.springframework.core.Ordered`, `Component`, `ApplicationRunner` và `ApplicationArguments`. Nếu đưa thêm vào demo đang có, bạn phải tính lại output vì bean mới được Spring Boot gọi ở vị trí order 5.

`Ordered` có thể hữu ích khi class muốn xác định thứ tự bằng code. Đừng để `getOrder()` phụ thuộc vào state thay đổi bất thường trong lúc sắp xếp; giá trị order nên ổn định trong một lần khởi động.

### 5.3. Giá trị mặc định và hằng số

Spring định nghĩa những mốc quan trọng trong `Ordered`:

- `Ordered.HIGHEST_PRECEDENCE`: độ ưu tiên cao nhất trong mô hình integer order; thường tương đương `Integer.MIN_VALUE`.
- `Ordered.LOWEST_PRECEDENCE`: độ ưu tiên thấp nhất; thường tương đương `Integer.MAX_VALUE`.

Một bean không có `@Order` hoặc `Ordered` thường được xem như không đưa ra độ ưu tiên cụ thể, với thứ tự mặc định ở mức thấp. **Nếu nhiều bean cùng mức ưu tiên, không nên dựa vào thứ tự tương đối giữa chúng**.

### 5.4. @Order và Ordered cùng xuất hiện?

Với cơ chế so sánh dựa trên `AnnotationAwareOrderComparator` của Spring Framework, nếu một instance triển khai `Ordered` thì kết quả `getOrder()` thường được dùng làm order cho instance đó, thay vì chỉ lấy annotation trên class. Đây là tình huống nên tránh nếu không cần thiết vì người đọc code có thể nhầm lẫn hai nguồn ưu tiên.

Khuyến nghị: một runner nên có **một cơ chế order rõ ràng**, và mỗi bước thực sự phụ thuộc thứ tự nên có một giá trị ưu tiên riêng biệt.

## 6. Ví dụ hoàn chỉnh: hai loại runner chạy xen kẽ theo cùng một thứ tự

Đây là ví dụ **Java 17+ / Spring Boot 3.3.x** có thể chạy trong một dự án Gradle phù hợp. Mục tiêu là chứng minh: **CommandLineRunner có thể chạy trước ApplicationRunner, rồi một ApplicationRunner khác chạy trước CommandLineRunner khác**, đúng theo `@Order`.

### 6.1. Cấu trúc dự án

```text
runner-order-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          runners/
            RunnerOrderApplication.java
      resources/
        application.properties
```

Để giảm số file trong ví dụ, tất cả các class runner được định nghĩa **package-private và top-level** trong cùng file Java với một public application class.

### 6.2. File build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

`settings.gradle`:

```groovy
rootProject.name = 'runner-order-demo'
```

Cấu hình Spring Boot 3.3 ở đây dùng một bản cụ thể để minh họa API; trong dự án production cần chọn bản đang được tổ chức hỗ trợ và bảo trì. Dự án cần Gradle wrapper tương thích với Spring Boot và Java toolchain phù hợp; đoạn build không tự tạo wrapper.

### 6.3. File application.properties

```properties
spring.application.name=runner-order-demo
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=ERROR
```

Chúng ta dùng `NONE` vì demo không cần HTTP server. Các callback runner vẫn được gọi trong non-web context. Thiết lập logging giảm log thông thường; output bên dưới chỉ trình bày các dòng do mã ứng dụng in ra.

### 6.4. Source Java runnable

File `src/main/java/demo/runners/RunnerOrderApplication.java`:

```java
package demo.runners;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class RunnerOrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(RunnerOrderApplication.class, args);
    }
}

@Component
@Order(10)
class PrepareCommandLineRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println(
                "10 | CommandLineRunner | prepare | rawArgs=" + args.length);
    }
}

@Component
@Order(20)
class LoadApplicationRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(
                "20 | ApplicationRunner | load | dryRun="
                + args.containsOption("dry-run"));
    }
}

@Component
@Order(30)
class VerifyApplicationRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("30 | ApplicationRunner | verify");
    }
}

@Component
@Order(40)
class ReportCommandLineRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("40 | CommandLineRunner | report");
    }
}
```

Các class package-private ở đây hợp lệ: Java cho phép chỉ một top-level public class trong file và các class top-level khác không public. `@Component` giúp chúng được quét trong package `demo.runners` nằm dưới package của `@SpringBootApplication`.

### 6.5. Chạy và xem kết quả

Khi dự án có Gradle wrapper:

```bash
./gradlew bootRun
```

Các dòng do code demo in ra, với **không có đối số ứng dụng bổ sung**:

```text
10 | CommandLineRunner | prepare | rawArgs=0
20 | ApplicationRunner | load | dryRun=false
30 | ApplicationRunner | verify
40 | CommandLineRunner | report
```

Đây là **thứ tự xác định theo giá trị order**. Có thể có những log Spring Boot/Gradle khác, không tính vào bốn dòng minh họa.

Nếu chạy:

```bash
./gradlew bootRun --args='--dry-run'
```

với môi trường shell xử lý dấu nháy như trên, số lượng đối số gốc và giá trị option thay đổi:

```text
10 | CommandLineRunner | prepare | rawArgs=1
20 | ApplicationRunner | load | dryRun=true
30 | ApplicationRunner | verify
40 | CommandLineRunner | report
```

Với PowerShell trên Windows, có thể dùng dấu nháy kép cho tham số Gradle tương ứng theo shell. Không nên dựa vào cú pháp nháy đơn của Unix cho mọi shell.

### 6.6. Bằng chứng thứ tự chung

Giả sử có hai hàng đợi tách biệt, một hàng cho mỗi interface, thì hai loại sẽ không được xen kẽ đúng theo `10, 20, 30, 40`. Nhưng kết quả demo thực tế là:

- `CommandLineRunner` order 10 chạy **trước** `ApplicationRunner` order 20.
- `ApplicationRunner` order 30 chạy **trước** `CommandLineRunner` order 40.
- Không có pha gọi riêng theo tên interface; order được so sánh trên **cả hai loại cùng nhau**.

Vì vậy biểu thức “`ApplicationRunner` luôn chạy trước `CommandLineRunner`” hoặc ngược lại **không phải quy tắc áp dụng khi có priority rõ ràng**.

## 7. Nếu thay @Order bằng Ordered thì sao?

Cả hai cơ chế đều cung cấp giá trị dùng để so sánh thứ tự. Bạn có thể thay `PrepareCommandLineRunner` trong demo bằng một class tương tự:

```java
@Component
class PrepareOrderedRunner implements CommandLineRunner, Ordered {

    @Override
    public int getOrder() {
        return 10;
    }

    @Override
    public void run(String... args) {
        System.out.println(
                "10 | CommandLineRunner | prepare | rawArgs=" + args.length);
    }
}
```

Đoạn này cần import `org.springframework.core.Ordered`, `Component` và `CommandLineRunner`. Đây là **biến thể thay thế**, không phải một bean cần thêm song song vào demo, nếu bạn muốn giữ chính xác bốn dòng kết quả.

Sau khi bỏ bean `PrepareCommandLineRunner` cũ và thay bằng bean này, thứ tự vẫn là 10, 20, 30, 40. Ngược lại, nếu giữ cả hai với cùng order 10, thứ tự tương đối giữa chúng không còn là hợp đồng đáng tin.

**Khi nào nên dùng Ordered?**

- Cần xác định order bằng logic trong instance, ví dụ class hạ tầng dùng một giá trị được cấu hình trong constructor.
- Muốn tránh phụ thuộc annotation ở những class dùng chung.
- Đang triển khai một hạ tầng Spring vốn đã dùng interface `Ordered`.

Với các bước startup cố định, `@Order(10)` thường gọn và minh bạch hơn `implements Ordered` chỉ để trả về một hằng số.

## 8. Nếu không đặt @Order thì ai chạy trước?

Đây là nơi gây hiểu nhầm nhất. Hãy phân biệt:

**A. Hành vi quan sát trong một bản Spring Boot cụ thể**

Một phiên bản Spring Boot có thể thu thập các `ApplicationRunner` trước, rồi các `CommandLineRunner`, hoặc dùng thứ tự duyệt bean nhất định trong quá trình xây danh sách. Nếu các đối tượng đều có cùng order mặc định, kết quả trên máy bạn có thể liên tục thể hiện một thứ tự giống nhau.

**B. Điều ứng dụng được phép xem là hợp đồng**

Tài liệu Spring Boot hướng dẫn dùng `Ordered` hoặc `@Order` khi nhiều runner **phải chạy theo thứ tự cụ thể**. Không có lời hứa rằng thứ tự mặc định giữa các bean bằng ưu tiên sẽ ổn định khi:

- Đổi phiên bản Spring Boot hoặc Spring Framework.
- Thêm/bớt starter, auto-configuration hoặc bean runner của thư viện khác.
- Đổi cách đăng ký bean (`@Component`, `@Bean`, conditional configuration).
- Đổi tên class/bean, classpath hay cách xây context.
- Chuyển sang cấu trúc nhiều application context hoặc custom bootstrap.

Vì vậy câu trả lời kỹ thuật chính xác là:

> **Không khai báo ưu tiên rõ ràng thì không nên phụ thuộc vào một thứ tự giữa các runner có cùng order.**

Nếu kết quả bước B phụ thuộc vào dữ liệu bước A tạo ra, phải có cơ chế dependency hoặc điều phối minh bạch. Tránh kiểu dựa vào “ở môi trường local thì Spring gọi A trước B”.

### Nếu hai runner có cùng @Order(10)

```java
@Component
@Order(10)
class FirstTask implements ApplicationRunner { ... }

@Component
@Order(10)
class SecondTask implements CommandLineRunner { ... }
```

Đoạn này là **pseudo-code rút gọn** (dấu ba chấm không phải Java source hợp lệ). Cả hai cùng priority 10, nên `@Order` **không tạo quan hệ thứ tự** giữa chúng. Nếu A phải trước B, dùng giá trị khác nhau, ví dụ `@Order(10)` và `@Order(20)`, hoặc gộp bước phụ thuộc vào một orchestrator.

### @Order không sắp xếp thứ tự khởi tạo bean

`@Order(10)` trên runner **điều khiển vị trí gọi `run(...)`**, không bảo đảm constructor, `@PostConstruct` hay `InitializingBean.afterPropertiesSet()` của runner đó chạy trước bean có `@Order(20)`. Đây là hai giai đoạn khác nhau của container:

```text
Refresh ApplicationContext:
    tạo / inject / khởi tạo singleton theo quy tắc container
    |
    v
ApplicationStartedEvent
    |
    v
Giai đoạn runners:
    sắp xếp và gọi run(...) theo order
```

Muốn quản lý quan hệ **khởi tạo bean**, dùng constructor injection, `@DependsOn` khi phù hợp hoặc các cơ chế container khác. Muốn điều phối **logic startup có thứ tự**, dùng order và/hoặc một orchestrator minh bạch. Đừng kỳ vọng một annotation xử lý mọi loại thứ tự.

## 9. Bean đăng ký bằng @Bean có xếp chung với @Component không?

**Có.** `SpringApplication` quan tâm đến **các bean trong context triển khai interface runner**; cách chúng được đăng ký không tự tạo một pha thực thi riêng.

Ví dụ:

```java
@Configuration
class RunnerConfiguration {

    @Bean
    CommandLineRunner simpleCommandRunner() {
        return args -> System.out.println("command bean ran");
    }

    @Bean
    ApplicationRunner simpleApplicationRunner() {
        return args -> System.out.println("application bean ran");
    }
}
```

Đoạn này cần import `Configuration`, `Bean`, `CommandLineRunner` và `ApplicationRunner`. Hai bean đều là runner hợp lệ. **Chưa có order rõ ràng**, vì đây là các lambda thuần.

Một bẫy phiên bản: **không nên mặc định `@Order` đặt trên phương thức `@Bean` luôn đủ để điều khiển runner lambda trong mọi phiên bản Spring Boot**. Ví dụ trên tập trung chứng minh chúng đều được thu thập, không chứng minh ưu tiên. Trong Spring Boot 3.3, để có thứ tự dễ dự đoán, ưu tiên:

- Một class runner có `@Order` trên **class** và được đăng ký bằng `@Component`.
- Một class implements `Ordered` với `getOrder()` rõ ràng.
- Một bean `@Bean` trả về instance của class runner có cấu hình order được bộ so sánh nhận biết.

Nếu dự án muốn dựa vào annotation trên `@Bean` factory method, phải kiểm chứng phiên bản Spring Boot và bộ so sánh thực tế. Đừng suy luận từ việc `@Order` trên factory method hoạt động trong một số cơ chế injection/sorting khác rằng nó tự động có cùng tác dụng với callback runner.

### Dùng @Bean và một implementation có @Order

```java
@Order(15)
class AuditRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("audit order 15");
    }
}

@Configuration
class AuditConfiguration {

    @Bean
    AuditRunner auditRunner() {
        return new AuditRunner();
    }
}
```

Đây là ví dụ source có thể đặt trong package hợp lệ, cần import `Order`, `Configuration`, `Bean` và `CommandLineRunner`. Bean `AuditRunner` được đăng ký qua `@Bean` nhưng class của instance có annotation order rõ ràng, nên có thể tham gia thứ tự chung.

Nếu đưa vào demo mục 6, `AuditRunner` sẽ được gọi giữa runner order 10 và runner order 20. Vì vậy **không** thêm nguyên đoạn này khi bạn muốn giữ nguyên output mẫu bốn dòng.

## 10. Trường hợp một bean implements cả hai interface

Một class có thể triển khai đồng thời `ApplicationRunner` và `CommandLineRunner`:

```java
package demo.runners;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(25)
class DualRunner implements ApplicationRunner, CommandLineRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("25 | dual | ApplicationRunner");
    }

    @Override
    public void run(String... args) {
        System.out.println("25 | dual | CommandLineRunner");
    }
}
```

Đoạn này là một class Java hợp lệ, có thể đặt vào file `DualRunner.java` trong cùng package của demo. Hãy lưu ý Java cho phép overload method `run` vì một overload nhận `ApplicationArguments`, overload còn lại nhận `String[]`.

Trong luồng `callRunners` của Spring Boot 3.3, **cùng một instance** có thể xuất hiện trong hai nhóm bean được tìm kiếm. Cơ chế duyệt runner tránh việc một instance được duyệt hai lần, nhưng khi xử lý một instance triển khai cả hai interface, Boot kiểm tra **cả hai**:

1. Nếu là `ApplicationRunner`, gọi `run(ApplicationArguments)`.
2. Nếu là `CommandLineRunner`, gọi `run(String...)`.

Vì vậy bean này có **một vị trí order 25** trong danh sách đối tượng runner, nhưng có **hai callback `run` khác chữ ký** được gọi khi đến vị trí ấy. Với demo mục 6, kết quả sau khi thêm `DualRunner` là:

```text
10 | CommandLineRunner | prepare | rawArgs=0
20 | ApplicationRunner | load | dryRun=false
25 | dual | ApplicationRunner
25 | dual | CommandLineRunner
30 | ApplicationRunner | verify
40 | CommandLineRunner | report
```

Đây là trường hợp nâng cao và không nhất thiết là thiết kế tốt. Hai interface thường khác nhau chỉ ở cách cung cấp arguments; triển khai cả hai dễ gây **hai lần thực thi logic startup** nếu hai overload cùng gọi một service, mở kết nối hay gửi yêu cầu đến hệ thống ngoài.

**Khuyến nghị:** khi cần một bước startup, thường chỉ chọn **một** interface. Nếu cần cả đối số gốc lẫn đối số phân tích, `ApplicationRunner` vẫn có `ApplicationArguments.getSourceArgs()` để lấy raw args. Dùng `DualRunner` chủ yếu khi hiểu rõ lý do vì sao phải có hai callback độc lập.

## 11. Khi một runner ném exception: thứ tự chung bị ảnh hưởng thế nào?

Các runner được gọi theo thứ tự đã sắp xếp trong quá trình khởi động. Nếu một runner ném exception mà Spring Boot xem là lỗi startup, **chuỗi gọi không tiếp tục bình thường đến các runner phía sau**.

Giả sử:

| Order | Runner | Hành vi |
| ---: | --- | --- |
| 10 | `CommandLineRunner` | Hoàn tất |
| 20 | `ApplicationRunner` | Ném `IllegalStateException` |
| 30 | `CommandLineRunner` | Chưa chạy |
| 40 | `ApplicationRunner` | Chưa chạy |

Ví dụ minh họa cho một phương thức trong class implements `ApplicationRunner`:

```java
@Override
public void run(ApplicationArguments args) {
    System.out.println("runner order 20 started");
    throw new IllegalStateException("required data unavailable");
}
```

Đây là **đoạn method đặt trong class runner**, không phải một chương trình Java độc lập. Trong luồng bình thường, sau dòng in của runner order 20, `SpringApplication.run` thất bại. `ApplicationReadyEvent` sẽ không được phát cho lần chạy thất bại đó.

`SpringApplication` xử lý lỗi, phát `ApplicationFailedEvent` theo cơ chế của Boot và thực hiện dọn dẹp context khi phù hợp. Exception có thể được bọc thêm bởi hạ tầng runner, nên khi chẩn đoán hãy đọc **root cause** thay vì chỉ đọc loại exception ngoài cùng.

**Không nên dựa vào “runner cuối sẽ dọn tài nguyên cho mọi runner trước”**. Nếu một runner trước đó lỗi, runner sau không còn được đảm bảo chạy. Tài nguyên phải được quản lý bởi bean lifecycle, `@PreDestroy`, `DisposableBean`, `AutoCloseable` hoặc khối `try/finally` phù hợp; công việc dọn dẹp quan trọng không nên đặt duy nhất trong runner cuối.

Nếu một công việc khởi tạo không thiết yếu có lỗi nhưng ứng dụng vẫn được phép chạy, cần thiết kế chính sách lỗi rõ ràng, xử lý exception có chọn lọc và ghi nhận trạng thái. Không mặc định bắt hết `Exception` rồi coi startup thành công, vì như vậy có thể làm ứng dụng chạy khi dữ liệu cần thiết chưa sẵn sàng.

## 12. Khi nào nên dùng @Order, khi nào nên có một orchestrator?

`@Order` là công cụ tốt khi có vài thao tác **độc lập hoặc có phụ thuộc đơn giản theo tuyến tính**, chẳng hạn:

```text
10 - kiểm tra thông tin cấu hình
20 - khởi tạo một cache nhỏ
30 - xác minh cache
40 - ghi kết quả startup
```

Khi các bước phụ thuộc chặt, có rollback, giao dịch hoặc nhiều nhánh, đặt tất cả trong một **startup orchestrator** thường dễ kiểm soát hơn.

### Ví dụ orchestrator dùng ApplicationRunner

```java
@Component
class StartupOrchestrator implements ApplicationRunner {

    private final StartupVerifier verifier;
    private final CacheWarmup warmup;

    StartupOrchestrator(StartupVerifier verifier, CacheWarmup warmup) {
        this.verifier = verifier;
        this.warmup = warmup;
    }

    @Override
    public void run(ApplicationArguments args) {
        verifier.verifyConfiguration();
        warmup.populate();
        verifier.verifyCache();
    }
}
```

Đây là **một đoạn thiết kế minh họa**: cần cung cấp hai service `StartupVerifier` và `CacheWarmup` với các method được gọi, cùng import `Component` và `ApplicationRunner` / `ApplicationArguments`. Nó không biên dịch độc lập nếu thiếu hai service này.

Ưu điểm:

- Thứ tự giữa `verifyConfiguration`, `populate` và `verifyCache` được thể hiện trực tiếp trong một hàm.
- Có thể bổ sung transaction boundary, timeout, retry và error handling theo yêu cầu.
- Dễ unit test một lần gọi `run(...)`.
- Không phụ thuộc vào ưu tiên của nhiều runner do các starter hoặc module khác cung cấp.

**Cảnh báo:** orchestrator không tự giải quyết những tác vụ bất đồng bộ mà nó khởi chạy rồi không chờ kết quả. Nếu `populate()` chỉ bắt đầu một thread và trả về ngay, các bước sau vẫn có thể chạy trước khi thread hoàn tất. Cần cơ chế await/synchronization phù hợp hoặc đặt trách nhiệm startup rõ ràng.

### Nguyên tắc thiết kế

- Chỉ có vài runner, quan hệ đơn giản → `@Order` là đủ.
- Nhiều bước quan trọng, cần rollback/error policy → cân nhắc một orchestrator.
- Logic phải có trước khi bean được tạo → runner **quá muộn**, dùng điểm mở rộng thích hợp ở giai đoạn trước refresh.
- Công việc phải chạy định kỳ sau startup → dùng scheduler/job system phù hợp, không dùng runner như timer lặp.
- Cần theo dõi runtime sau ready → dùng health/availability checks, không xem runner là tín hiệu sức khỏe liên tục.

## 13. Đừng nhầm thứ tự runner với các annotation/lifecycle khác

| Cơ chế | Điều khiển chính | Có bảo đảm thứ tự `run` giữa hai loại runner không? |
| --- | --- | --- |
| `@Order` trên class runner | Thứ tự gọi runner khi được bộ sắp xếp nhận biết | **Có**, khi giá trị ưu tiên xác định rõ |
| `Ordered#getOrder()` | Thứ tự động của instance runner | **Có**, theo giá trị trả về |
| `@DependsOn` | Quan hệ tạo bean và hủy bean | **Không trực tiếp**; không phải API xếp runner |
| Constructor injection | Bean được tạo với dependency cần thiết | **Không trực tiếp**; bảo đảm dependency chứ không xếp run |
| `@PostConstruct` | Callback khởi tạo của từng bean | Chạy trong lifecycle bean, **trước** giai đoạn runner |
| `InitializingBean.afterPropertiesSet()` | Callback khởi tạo bean | Không xếp các runner |
| `ApplicationStartedEvent` | Sự kiện sau refresh, trước runner | Không phải “runner order” |
| `ApplicationReadyEvent` | Sự kiện sau runners | Không quyết định thứ tự bên trong runners |
| `SmartLifecycle` | Start/stop các lifecycle beans theo phase | Cơ chế phase khác với runner order |
| `@Priority` / comparator khác | Tùy cơ chế áp dụng | Không nên suy diễn giống `@Order` nếu chưa xác minh |
| Thứ tự khai báo trong `@Configuration` | Thứ tự xuất hiện trong source file | **Không** phải hợp đồng thứ tự runner |
| Thứ tự tên bean alphabet | Tên định danh | **Không** phải hợp đồng thứ tự runner |

Một số ứng dụng có quy trình:

```text
Tạo bean A / B (constructor, @PostConstruct)
        |
        v
ContextRefreshedEvent
        |
        v
ApplicationStartedEvent
        |
        v
Runner order 10
        |
        v
Runner order 20
        |
        v
ApplicationReadyEvent
```

Không thay thế các mũi tên bằng “`@Order` sắp xếp toàn bộ vòng đời từ constructor tới ready”. Annotation đó có vai trò cụ thể khi Spring Boot so sánh runner.

## 14. Các tình huống thường gặp trong ứng dụng thật

### 14.1. Khởi tạo dữ liệu trước khi kiểm tra dữ liệu

Yêu cầu:

```text
SeedDataRunner (CommandLineRunner)
          ↓
ValidateDataRunner (ApplicationRunner)
```

Có thể đặt:

```java
@Order(10)
class SeedDataRunner implements CommandLineRunner { ... }

@Order(20)
class ValidateDataRunner implements ApplicationRunner { ... }
```

Đây là **pseudo-code rút gọn**; dấu `...` chỉ biểu diễn nội dung method cần viết, không phải Java source hợp lệ. Trong trường hợp này, `@Order` khác nhau tạo quan hệ chạy rõ. Tuy nhiên với migration hoặc dữ liệu quan trọng cần tính nguyên tử/rollback, nên dùng công cụ chuyên dụng hoặc orchestrator có cơ chế lỗi phù hợp.

### 14.2. Hai module riêng cùng đăng ký runner

Module A có `ApplicationRunner` order 100, module B có `CommandLineRunner` order 50. Dù dependency của module A được khai báo trước trong file build, runner B vẫn chạy trước vì `50 < 100` trong thứ tự chung.

Đừng phụ thuộc vào thứ tự import starter hoặc vị trí file JAR trên classpath để sắp xếp logic startup; hãy có hợp đồng order liên module hoặc một coordinator.

### 14.3. Muốn runner chỉ chạy trong môi trường dev

Có thể kết hợp điều kiện bean:

```java
@Component
@Profile("dev")
@Order(10)
class DevDataRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("Development-only startup task");
    }
}
```

Đoạn này cần import `Profile`, `Component`, `Order` và `CommandLineRunner`. Nếu profile `dev` không active, bean không được đăng ký, nên sẽ không được gọi. Trong trường hợp đó, những runner còn lại giữ thứ tự riêng của chúng. `@Order` không khiến một bean bị `@Profile` loại bỏ được tạo ra.

### 14.4. Một runner khởi chạy tác vụ async

Nếu một runner gọi:

```java
backgroundExecutor.execute(() -> doWork());
```

đó là đoạn pseudo-code với hai biến/phương thức chưa được định nghĩa. `run(...)` có thể trả về **trước khi `doWork()` hoàn tất**, nên Spring Boot sẽ chuyển sang runner kế tiếp, rồi tới ready. `@Order` chỉ sắp xếp **lời gọi `run`**, không mặc định chờ mọi tác vụ bất đồng bộ do chúng phát sinh.

Muốn bước sau thực sự phụ thuộc kết quả bước trước, hãy trả về `Future`/`CompletableFuture` rồi chờ phù hợp, dùng orchestrator, hoặc thiết kế cơ chế ready/availability không cho nhận traffic khi chưa đủ điều kiện. Tránh blocking không giới hạn trong bootstrap.

## 15. Cách kiểm thử thứ tự chung

### Kiểm thử đơn giản với console

Dùng demo mục 6, chạy không đối số, rồi xác nhận thứ tự chính xác:

```text
10 | CommandLineRunner | prepare | rawArgs=0
20 | ApplicationRunner | load | dryRun=false
30 | ApplicationRunner | verify
40 | CommandLineRunner | report
```

Sau đó đổi order:

- Đổi `PrepareCommandLineRunner` từ 10 thành 35.
- Giữ ba giá trị 20, 30, 40 còn lại.

Dự đoán và kiểm chứng output:

```text
20 | ApplicationRunner | load | dryRun=false
30 | ApplicationRunner | verify
10 | CommandLineRunner | prepare | rawArgs=0
40 | CommandLineRunner | report
```

Lưu ý trong dòng thứ ba của ví dụ thay đổi, **chuỗi "10 | ..." là text cố định do method in ra từ source**, trong khi `@Order(35)` đã được đổi. Đây là một mẹo dễ gây hiểu lầm: nhãn log không tự đổi theo annotation. Khi thử thật, nên sửa text thành `35 | ...` để phản ánh ưu tiên mới. Nếu đã sửa cả text, các dòng mong đợi là 20, 30, 35, 40.

Để không nhầm, cách tốt hơn là in thứ tự từ một hằng số dùng chung hoặc sử dụng một recorder của test thay vì xem nhãn là nguồn truth.

### Kiểm thử bằng recorder thay cho console

Có thể tạo một bean singleton giữ danh sách các tên bước được runner ghi vào. Sau khi `SpringApplication.run(...)` trả về thành công, kiểm tra danh sách:

```java
List<String> steps = List.of(
        "command-prepare",
        "application-load",
        "application-verify",
        "command-report");

System.out.println(steps);
```

Đoạn trên chỉ là ví dụ về **giá trị kỳ vọng**, chưa phải test thực thi: muốn có test thật cần recorder được các runner ghi vào và assertion so với danh sách này. Khi chạy nhiều Spring context trong cùng JVM hoặc dùng async executor, tránh recorder static chia sẻ và phải bảo đảm isolation.

Một lưu ý quan trọng về framework test: `ApplicationContextRunner` là công cụ kiểm tra auto-configuration/context, **không tương đương** gọi đầy đủ `SpringApplication.run(...)` với luồng gọi runners. Nếu mục tiêu là kiểm tra thứ tự startup runners, hãy dùng cách khởi chạy thực sự gọi `SpringApplication` hoặc test integration tương ứng, không giả định chỉ tạo context là các runner sẽ tự chạy.

### Kiểm thử giá trị ưu tiên bằng reflection? Không cần

Để chứng minh thứ tự chung, quan sát hành vi runtime là cách rõ nhất. Kiểm tra tồn tại `@Order` bằng reflection chỉ chứng minh annotation có mặt, không chứng minh bean được tạo, có mặt trong context hay được Spring Boot chọn làm runner.

## 16. Những lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Nguyên nhân đáng kiểm tra | Cách xử lý |
| --- | --- | --- |
| `CommandLineRunner` chạy trước mặc dù developer nghĩ ApplicationRunner luôn ưu tiên | Hai nhóm không có luật ưu tiên cố định; order nhỏ hơn được xếp trước | Gán `@Order`/`Ordered` rõ ràng, kiểm tra output |
| Hai runner cùng `@Order(1)` chạy không theo ý muốn | Cùng priority, không tạo quan hệ thứ tự | Đổi thành các giá trị khác nhau hoặc gộp logic |
| Đổi tên bean nhưng thứ tự không theo tên | Tên bean không phải cơ chế order | Dùng `@Order` hoặc `Ordered` |
| Đặt `@Order` vào một chỗ nhưng callback không đổi | Annotation đặt sai đối tượng, runtime type, proxy, factory-method metadata hoặc phiên bản xử lý khác mong đợi | Đặt trên class thực thi hoặc dùng `Ordered`; kiểm tra Boot version |
| `@Order` ở runner A nhưng bean B khởi tạo trước | Thứ tự `run` khác thứ tự constructor/`@PostConstruct` | Khai báo dependency/init lifecycle riêng |
| Runner không chạy | Class không phải bean, profile/condition không thỏa, hoặc app lỗi trước giai đoạn runner | Kiểm tra component scanning, bean registry, startup exception |
| Runner chạy hai lần | Bean có thể implement cả hai interface hoặc callback được gọi thủ công ngoài Boot | Kiểm tra implements, vị trí gọi, số instance/context |
| Runner sau không chạy | Runner trước ném exception hoặc `run` đang block | Đọc stack trace, kiểm tra thread và timeout |
| `ApplicationReadyEvent` không xuất hiện | Runner thất bại hoặc startup không hoàn thành | Xem lỗi ở runner trước và `ApplicationFailedEvent` |
| Chạy trong test khác production | Test slice/context loader khác hoặc không thực thi toàn bộ `SpringApplication` | Dùng integration test đúng phạm vi và cấu hình |
| Runner xếp thứ tự nhưng dữ liệu async chưa sẵn | `run` trả về trước khi công việc background kết thúc | Đồng bộ kết quả hoặc dùng cơ chế readiness thích hợp |
| Một module thêm starter làm thứ tự thay đổi | Thêm runner tự cấu hình có order khác hoặc tie không xác định | Xác định các bean runner thực tế và quy hoạch priority |
| Web endpoint nhận request trước khi runner hoàn tất | Server có thể bind trong refresh, trước giai đoạn ready | Không dựa vào runner để đảm bảo isolation tuyệt đối ở tầng HTTP; dùng readiness/gating phù hợp |

Quy trình chẩn đoán có thể làm theo các bước:

1. Kiểm tra **đúng class implements interface runner** và bean thật sự nằm trong context.
2. Liệt kê các runner mà ứng dụng có: bean tự khai báo và bean từ starter/auto-configuration.
3. Ghi lại giá trị `@Order` hoặc `Ordered.getOrder()` **của mỗi instance**.
4. Phân biệt **thứ tự gọi `run(...)`** với thứ tự tạo bean và các event.
5. Tìm các runner cùng order hoặc không có order; đây là nguyên nhân thường gặp của phụ thuộc thứ tự ngầm.
6. Đọc exception đầu tiên nếu chuỗi dừng giữa đường; runner sau có thể không chạy do runner trước lỗi.
7. Nếu dự án dùng đa context hoặc tự gọi runner thủ công, xác nhận đây đúng luồng `SpringApplication` mà bạn định quan sát.
8. Nếu dữ liệu vẫn sai dù order đúng, kiểm tra công việc có thực sự **hoàn thành đồng bộ trước khi `run` trả về** hay không.

## 17. Bài tập và câu hỏi kiểm tra

### Bài 1: dự đoán thứ tự trộn hai loại

Giả sử:

```text
App-A: ApplicationRunner, @Order(15)
Cmd-B: CommandLineRunner, @Order(5)
App-C: ApplicationRunner, @Order(25)
Cmd-D: CommandLineRunner, @Order(20)
```

Thứ tự đúng:

```text
Cmd-B → App-A → Cmd-D → App-C
```

Tại sao? Vì `5 < 15 < 20 < 25`, không có bước ưu tiên theo tên interface.

### Bài 2: trường hợp bằng nhau

Hai runner đều `@Order(10)`, một thuộc mỗi loại. Có thể đảm bảo cái nào chạy trước không? Không nên. Nếu một runner phải đọc kết quả do runner còn lại ghi, hãy đặt order khác nhau và cân nhắc điều phối phụ thuộc rõ ràng hơn.

### Bài 3: @Order không đổi thứ tự khởi tạo

Thêm `@PostConstruct` vào hai runner có order khác nhau, rồi log constructor và callback `run`. Phân biệt:

- Thời điểm bean được tạo/khởi tạo.
- Thời điểm `SpringApplication` gọi `run`.
- Thứ tự nào do `@Order` tác động.

Đừng viết test bắt thứ tự constructor phải giống thứ tự runner.

### Bài 4: so sánh đối số

Chạy demo với `--dry-run`. Tại sao `CommandLineRunner` nhận `String[]` còn `ApplicationRunner` nhận `ApplicationArguments`? Tại sao code gọi `args.containsOption("dry-run")` chỉ hợp lệ với kiểu `ApplicationArguments`?

### Bài 5: lỗi startup

Trong một runner order 20, ném `IllegalStateException` sau khi in dòng log. Dự đoán runner order 30/40 và `ApplicationReadyEvent` có xảy ra không. Kiểm tra exception gốc và xác nhận startup fail thay vì im lặng bỏ qua lỗi.

### Bài 6: một bean hai interface

Thêm `DualRunner` order 25 ở mục 10. Dự đoán vì sao có hai dòng log ở cùng vị trí đối tượng runner, và vì sao callback `ApplicationRunner` được gọi trước overload `CommandLineRunner` trên chính instance đó trong cách triển khai Boot 3.3.

### Bài 7: thiết kế lại startup nhiều bước

Giả sử ứng dụng có bảy bước startup, trong đó ba bước có phụ thuộc dữ liệu và hai bước cần retry khi gọi dịch vụ ngoài. Hãy chỉ ra phần nào nên dùng runner đơn có order, phần nào nên gom vào orchestrator hoặc xử lý readiness riêng. Mục tiêu là tránh dùng số nguyên order như một workflow engine không có kiểm soát.

## 18. Tóm tắt cần nhớ

- **`ApplicationRunner` và `CommandLineRunner` được xếp chung trong giai đoạn startup**, không bắt buộc chạy hết một nhóm trước nhóm kia.
- Spring Boot dùng cơ chế so sánh order của Spring; **số nhỏ hơn chạy trước**, bất kể loại runner.
- `@Order` trên class runner hoặc `Ordered.getOrder()` giúp xác định thứ tự. Các runner cùng priority hoặc thiếu priority **không nên có phụ thuộc thứ tự ngầm**.
- `@Order` điều khiển **thứ tự gọi `run`**, không quyết định constructor, `@PostConstruct`, `@DependsOn` hay toàn bộ lifecycle.
- Cả hai loại runner được gọi **sau `ApplicationStartedEvent` và trước `ApplicationReadyEvent`** trong startup thành công.
- Runner trước ném lỗi thì các runner sau không được bảo đảm chạy; `ApplicationReadyEvent` không xuất hiện trong startup thất bại.
- Một bean implement cả hai interface có thể nhận **hai lần gọi vào hai overload** ở cùng vị trí runner trong Spring Boot 3.3; thường nên chọn một interface để tránh trùng logic.
- Nếu startup có nhiều bước phụ thuộc chặt, một orchestrator rõ ràng và cơ chế xử lý lỗi hợp lý thường an toàn hơn dựa vào hàng loạt giá trị `@Order`.

### Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Using the ApplicationRunner or CommandLineRunner](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): thời điểm gọi runner và `@Order`/`Ordered`.
- [Spring Boot 3.3 — ApplicationRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html): `run(ApplicationArguments)`, thứ tự và mục đích.
- [Spring Boot 3.3 — CommandLineRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/CommandLineRunner.html): `run(String...)`, thứ tự và mục đích.
- [Spring Framework — Ordered API](https://docs.spring.io/spring-framework/docs/6.1.17/javadoc-api/org/springframework/core/Ordered.html): giá trị `getOrder()` và các hằng số ưu tiên.
- [Spring Framework — Order Annotation API](https://docs.spring.io/spring-framework/docs/6.1.17/javadoc-api/org/springframework/core/annotation/Order.html): cách khai báo order cho thành phần Spring.

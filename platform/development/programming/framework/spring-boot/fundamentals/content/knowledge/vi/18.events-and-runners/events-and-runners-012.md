# Ordered, @Order và thứ tự các runner

Trong Spring Boot, `ApplicationRunner` và `CommandLineRunner` là hai cách phổ biến để chạy một đoạn code sau khi `ApplicationContext` được khởi tạo. Khi ứng dụng có nhiều runner, thứ tự thực thi có thể rất quan trọng: một runner chuẩn bị dữ liệu, runner tiếp theo đọc dữ liệu đã chuẩn bị, còn runner cuối cùng in báo cáo.

Spring Boot cho phép bạn quy định thứ tự runner bằng interface `Ordered` hoặc annotation `@Order`. Quy tắc cốt lõi là **giá trị order càng nhỏ thì runner càng chạy sớm**. Cả `ApplicationRunner` và `CommandLineRunner` cùng tham gia việc sắp xếp; chúng không được chạy thành hai nhóm cố định độc lập.

Bài học thuộc chương **Sự kiện và runner** của **Spring Boot Fundamentals**. Chúng ta sẽ xem runner được gọi ở thời điểm nào, cách `Ordered` và `@Order` hoạt động, những trường hợp thứ tự không được bảo đảm, sự khác biệt giữa thứ tự *thực thi runner* và *khởi tạo bean*, rồi thực hành với một ứng dụng Spring Boot có nhiều runner.

## 1. Runner là gì và chạy ở đâu trong quá trình khởi động?

`CommandLineRunner` là functional interface của Spring Boot:

```java
package org.springframework.boot;

@FunctionalInterface
public interface CommandLineRunner {

    void run(String... args) throws Exception;
}
```

`ApplicationRunner` cũng là functional interface:

```java
package org.springframework.boot;

@FunctionalInterface
public interface ApplicationRunner {

    void run(ApplicationArguments args) throws Exception;
}
```

Điểm giống nhau là Spring Boot gọi phương thức `run(...)` của các bean triển khai những interface này sau khi context được refresh. Điểm khác nhau là cách nhận tham số dòng lệnh.

| Interface | Tham số của `run(...)` | Khi nên dùng |
|---|---|---|
| `CommandLineRunner` | `String... args` | Cần xử lý các chuỗi đối số gốc |
| `ApplicationRunner` | `ApplicationArguments args` | Cần phân biệt option và non-option arguments |
 
Cả hai cần được đăng ký thành **Spring bean**. Một class chỉ implement interface nhưng không nằm trong container sẽ không tự được Spring Boot gọi.

### 1.1. Vị trí tương đối trong lifecycle

Với quy trình startup Spring Boot thông thường, các mốc quan trọng là:

```text
SpringApplication.run(...)
          │
          ▼
Chuẩn bị Environment và ApplicationContext
          │
          ▼
Load bean definitions, tạo singleton cần thiết
          │
          ▼
Refresh ApplicationContext hoàn tất
          │
          ▼
ApplicationStartedEvent
          │
          ▼
Lấy các ApplicationRunner và CommandLineRunner
          │
          ▼
Sắp xếp runner theo order
          │
          ▼
Gọi run(...) của từng runner
          │
          ▼
ApplicationReadyEvent
          │
          ▼
Ứng dụng được coi là ready
```

`ApplicationStartedEvent` được phát sau khi context refresh nhưng **trước** khi các runner được gọi. `ApplicationReadyEvent` được phát sau khi các runner hoàn tất thành công.

Nếu một runner ném exception không được xử lý, quá trình khởi động có thể thất bại và ứng dụng không đến được mốc ready. Vì vậy, runner không chỉ là một tiện ích chạy code: nó nằm trên đường khởi động của ứng dụng.

### 1.2. Runner thường dùng để làm gì?

Một số ví dụ:

- Kiểm tra cấu hình hoặc dữ liệu cần thiết trước khi ứng dụng sẵn sàng.
- Chuẩn bị một lượng nhỏ dữ liệu khởi tạo.
- Chạy công việc CLI hoặc batch cần đến dependency injection.
- Đọc command-line arguments và điều phối một tác vụ.
- In thông tin khởi động hoặc báo cáo chẩn đoán ngắn.

Không nên đặt một tác vụ kéo dài vô hạn trong runner của web application nếu ứng dụng cần chuyển sang trạng thái ready. Runner dài sẽ trì hoãn `ApplicationReadyEvent` và có thể làm readiness probe không đạt yêu cầu.

## 2. Tạo một CommandLineRunner đơn giản

Ví dụ:

```java
package com.example.demo.startup;

import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

@Component
public class GreetingRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("GreetingRunner đã chạy");
    }
}
```

Khi class nằm trong vùng component scan, Spring đăng ký một bean `greetingRunner`. Sau khi context refresh hoàn tất, Spring Boot gọi `run(...)`.

Ví dụ nếu ứng dụng có main class:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Thì sau các log khởi tạo, bạn sẽ thấy:

```text
GreetingRunner đã chạy
```

Runner chạy theo **lần khởi động ApplicationContext**, không chạy lại cho mỗi HTTP request.

### 2.1. ApplicationRunner nhận đối số đã được phân tích

Ví dụ:

```java
package com.example.demo.startup;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class ArgumentRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Có --mode: "
                + args.containsOption("mode"));

        System.out.println("Các giá trị mode: "
                + args.getOptionValues("mode"));

        System.out.println("Đối số không phải option: "
                + args.getNonOptionArgs());
    }
}
```

Chạy:

```bash
java -jar demo.jar --mode=import input.csv
```

Kết quả minh họa:

```text
Có --mode: true
Các giá trị mode: [import]
Đối số không phải option: [input.csv]
```

`ApplicationRunner` hữu ích khi cần phân tích options. `CommandLineRunner` vẫn thích hợp khi bạn muốn xử lý `String[]` gốc hoặc dùng một parser riêng.

## 3. Nếu có nhiều runner, Spring Boot gọi theo thứ tự nào?

Giả sử ứng dụng có ba runner:

```text
PrepareRunner
ImportRunner
ReportRunner
```

Bạn muốn:

```text
PrepareRunner
      │
      ▼
ImportRunner
      │
      ▼
ReportRunner
```

Nếu không khai báo thứ tự, **không nên dựa vào** thứ tự tên class, tên bean, thứ tự file Java, thứ tự component scanning hoặc thứ tự class được ghi trong project.

Spring Boot thu thập các bean triển khai `ApplicationRunner` và `CommandLineRunner`, sắp xếp chúng bằng comparator có hỗ trợ metadata order, rồi gọi các runner theo danh sách đã sắp xếp.

Để quy định thứ tự, có hai cơ chế chính:

1. Gắn annotation `@Order` lên class runner.
2. Cho runner implement interface `Ordered` và trả về giá trị từ `getOrder()`.

### 3.1. Nguyên tắc giá trị nhỏ chạy trước

| Giá trị order | Thứ tự tương đối |
|---:|---|
| `-100` | Sớm hơn `-10` |
| `-10` | Sớm hơn `0` |
| `0` | Sớm hơn `10` |
| `10` | Sớm hơn `100` |
| `100` | Muộn hơn các giá trị phía trên |

Số âm là hợp lệ. Không cần bắt đầu từ 1, và không cần đánh số liên tục.

Chẳng hạn, `@Order(10)` sẽ chạy trước `@Order(20)`, bất kể runner nào được đăng ký trước.

## 4. Cách 1: dùng annotation @Order

Import:

```java
import org.springframework.core.annotation.Order;
```

Ví dụ runner chuẩn bị dữ liệu:

```java
package com.example.demo.startup;

import org.springframework.boot.CommandLineRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
public class PrepareRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("1 - Chuẩn bị dữ liệu");
    }
}
```

Runner nhập dữ liệu:

```java
package com.example.demo.startup;

import org.springframework.boot.CommandLineRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(20)
public class ImportRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("2 - Nhập dữ liệu");
    }
}
```

Runner báo cáo:

```java
package com.example.demo.startup;

import org.springframework.boot.CommandLineRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(30)
public class ReportRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("3 - In báo cáo");
    }
}
```

Kết quả:

```text
1 - Chuẩn bị dữ liệu
2 - Nhập dữ liệu
3 - In báo cáo
```

Điểm quan trọng là Spring Boot sắp xếp theo các giá trị `10`, `20`, `30`. Các chuỗi `1`, `2`, `3` trong log chỉ là nội dung minh họa.

### 4.1. @Order là metadata khai báo

`@Order(10)` là một chỉ dẫn tĩnh gắn với class. Nó thuận tiện khi thứ tự hiếm khi thay đổi và được xác định ngay ở định nghĩa runner.

Ví dụ:

```java
@Component
@Order(5)
public class ValidateConfigurationRunner
        implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        // Kiểm tra cấu hình.
    }
}
```

Ưu điểm:

- Dễ đọc.
- Không cần thêm phương thức `getOrder()`.
- Phù hợp với một class có vị trí rõ ràng trong chuỗi startup.

Nhược điểm: nếu giá trị order cần tính hoặc phụ thuộc vào một cấu hình bên ngoài, annotation không cung cấp cơ chế động trực tiếp.

### 4.2. Không nhầm import @Order

Annotation cần dùng là:

```java
org.springframework.core.annotation.Order
```

Đừng nhầm với annotation khác có tên tương tự từ thư viện thứ ba. Khi code không chạy theo thứ tự dự kiến, một trong những điều đầu tiên nên xem là import.

## 5. Cách 2: implement interface Ordered

`Ordered` là interface của Spring Framework:

```java
import org.springframework.core.Ordered;
```

Interface có phương thức:

```java
int getOrder();
```

Một runner có thể implement cả `ApplicationRunner` và `Ordered`:

```java
package com.example.demo.startup;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;

@Component
public class ValidateRunner implements ApplicationRunner, Ordered {

    @Override
    public int getOrder() {
        return 5;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Kiểm tra trước các runner order 10+");
    }
}
```

Với `getOrder() = 5`, runner chạy trước một runner có `@Order(10)`.

### 5.1. Ordered phù hợp khi cần biểu đạt thứ tự bằng code

`Ordered` có thể hữu ích khi:

- Class đã có logic điều khiển thứ tự hoặc implements một interface ordering tương ứng.
- Bạn muốn dùng hằng số như `Ordered.HIGHEST_PRECEDENCE`.
- Một thành phần cần cung cấp order bằng phương thức.
- Bạn muốn tái sử dụng cùng quy ước ordering ở nhiều cơ chế Spring.

Ví dụ:

```java
@Component
public class BootstrapValidationRunner
        implements CommandLineRunner, Ordered {

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE;
    }

    @Override
    public void run(String... args) {
        System.out.println("Chạy rất sớm trong nhóm runner");
    }
}
```

`Ordered` không phải lifecycle hook. Phương thức `getOrder()` chỉ cung cấp giá trị sắp xếp; Spring Boot vẫn gọi `run(...)` trong giai đoạn runner sau khi context refresh.

### 5.2. HIGHEST_PRECEDENCE và LOWEST_PRECEDENCE

Interface `Ordered` định nghĩa hai hằng số:

```java
Ordered.HIGHEST_PRECEDENCE
Ordered.LOWEST_PRECEDENCE
```

Tương ứng:

```java
Integer.MIN_VALUE
Integer.MAX_VALUE
```

Ý nghĩa:

- `HIGHEST_PRECEDENCE` là một trong các giá trị chạy sớm nhất có thể dùng theo comparator.
- `LOWEST_PRECEDENCE` là giá trị chạy muộn nhất.
- Mọi giá trị nguyên giữa hai mốc được phép dùng.

**Không nhầm tên “highest” với số nguyên lớn.** Trong hệ ordering này, giá trị càng nhỏ thì mức ưu tiên chạy càng cao.

Ví dụ:

```java
@Override
public int getOrder() {
    return Ordered.HIGHEST_PRECEDENCE;
}
```

sẽ được xếp trước:

```java
@Order(0)
```

và cả:

```java
@Order(100)
```

nếu các runner khác không có cùng order nhỏ nhất.

### 5.3. Không có @Order thì sao?

Với runner không implement `Ordered` và không có metadata order phù hợp, comparator thường xem nó như có `LOWEST_PRECEDENCE`.

Điều đó có nghĩa runner không khai báo order thường chạy sau các runner có order cụ thể nhỏ hơn giá trị mặc định.

Tuy nhiên, khi nhiều runner cùng không khai báo order hoặc cùng có giá trị thấp nhất, **không có thứ tự nghiệp vụ được cam kết giữa chúng**.

## 6. Dùng @Order hay Ordered?

Hai cơ chế cùng cung cấp một con số để Spring Boot sắp xếp runner.

| Tiêu chí | `@Order` | `Ordered` |
|---|---|---|
| Cách viết | Annotation trên class | Implement interface và `getOrder()` |
| Giá trị | Số nguyên khai báo trong annotation | Số nguyên trả về từ method |
| Phù hợp nhất | Thứ tự cố định, dễ thấy trên class | Thứ tự cần biểu đạt qua code/interface |
| Có cần thêm method? | Không | Có |
| Được comparator của Spring nhận diện? | Có | Có |
| Có áp dụng chung cho cả hai loại runner? | Có | Có |

Một ví dụ đủ dùng:

```java
@Component
@Order(10)
public class StartRunner implements CommandLineRunner {
    @Override
    public void run(String... args) {
        // ...
    }
}
```

Và một ví dụ tương đương:

```java
@Component
public class StartRunner implements CommandLineRunner, Ordered {

    @Override
    public int getOrder() {
        return 10;
    }

    @Override
    public void run(String... args) {
        // ...
    }
}
```

Trong ứng dụng thông thường, `@Order` thường gọn và dễ nhìn. Nếu class đã có hợp đồng `Ordered` hoặc cần dùng hằng số/logic cho order, có thể dùng interface.

### 6.1. Nếu một class có cả @Order và Ordered

Ví dụ:

```java
@Component
@Order(100)
public class MixedRunner implements CommandLineRunner, Ordered {

    @Override
    public int getOrder() {
        return 10;
    }

    @Override
    public void run(String... args) {
        System.out.println("MixedRunner");
    }
}
```

Comparator có hỗ trợ annotation của Spring ưu tiên giá trị do instance `Ordered` cung cấp khi class implement interface này. Vì vậy, giá trị `getOrder() = 10` quyết định vị trí runner trong trường hợp trên, thay vì `@Order(100)`.

Dù biết quy tắc này, **không nên khai báo hai giá trị cạnh tranh trên cùng class**. Người đọc sẽ dễ hiểu sai. Hãy chọn một cơ chế phù hợp, hoặc bảo đảm hai nơi nhất quán nếu một thư viện buộc phải dùng cả hai.

## 7. ApplicationRunner và CommandLineRunner được sắp xếp chung

Một điểm rất quan trọng: Spring Boot **không chạy tất cả ApplicationRunner trước rồi mới chạy CommandLineRunner**, hoặc ngược lại, chỉ vì loại interface.

Các runner được thu thập và sắp xếp theo ordering metadata, bất kể implement interface nào.

Ví dụ:

```java
@Component
@Order(10)
public class FirstRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("A - CommandLineRunner");
    }
}
```

```java
@Component
@Order(20)
public class SecondRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("B - ApplicationRunner");
    }
}
```

```java
@Component
@Order(30)
public class ThirdRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("C - CommandLineRunner");
    }
}
```

Kết quả:

```text
A - CommandLineRunner
B - ApplicationRunner
C - CommandLineRunner
```

Lý do là order `10`, `20`, `30`; không phải loại runner.

### 7.1. Đổi order, đổi thứ tự

Nếu đặt `@Order(5)` cho `SecondRunner`, kết quả trở thành:

```text
B - ApplicationRunner
A - CommandLineRunner
C - CommandLineRunner
```

Đây là ví dụ trực tiếp cho thấy `ApplicationRunner` có thể chạy trước `CommandLineRunner` nếu giá trị order của nó nhỏ hơn.

### 7.2. Một bean implement cả hai interface

Về mặt Java, một class có thể implement cả `ApplicationRunner` và `CommandLineRunner`:

```java
@Component
@Order(10)
public class DualRunner
        implements ApplicationRunner, CommandLineRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("ApplicationRunner callback");
    }

    @Override
    public void run(String... args) {
        System.out.println("CommandLineRunner callback");
    }
}
```

Trong cơ chế gọi runner của Spring Boot, một bean như vậy có thể được nhận diện theo cả hai interface và cả hai phương thức `run(...)` được gọi trong lượt xử lý runner đó.

Vì vậy, nếu mục tiêu chỉ là thực hiện một tác vụ duy nhất, **nên chọn một trong hai interface**. Tránh implement đồng thời cả hai chỉ để nhận hai dạng đối số, vì có thể làm cùng một công việc được thực hiện hai lần nếu hai callback cùng gọi logic chung.

## 8. Thứ tự bằng nhau: điều gì được bảo đảm?

Giả sử hai runner đều khai báo:

```java
@Order(10)
```

hoặc cả hai không khai báo order.

Trong trường hợp này, chúng có **cùng mức ưu tiên**. Không nên dựa vào thứ tự classpath scanning, thứ tự tên bean hoặc thứ tự khai báo source code để tạo dependency nghiệp vụ giữa chúng.

Ví dụ:

```java
@Component
@Order(10)
public class InitializeA implements CommandLineRunner {
    @Override
    public void run(String... args) {
        System.out.println("A");
    }
}
```

```java
@Component
@Order(10)
public class InitializeB implements CommandLineRunner {
    @Override
    public void run(String... args) {
        System.out.println("B");
    }
}
```

Nếu A bắt buộc phải hoàn thành trước B, hãy đặt order khác nhau:

```java
@Order(10) // InitializeA
```

```java
@Order(20) // InitializeB
```

Không nên viết code chỉ hoạt động khi các runner cùng order tình cờ được chạy theo một thứ tự nhất định.

### 8.1. Vì sao đôi khi cùng order vẫn luôn ra cùng một kết quả?

Một version Spring Boot với cùng classpath và cùng cách đăng ký bean có thể cho kết quả lặp lại qua nhiều lần chạy. Điều đó chỉ cho thấy thứ tự thu thập/sắp xếp đang ổn định trong môi trường ấy, **không phải hợp đồng thứ tự nghiệp vụ** giữa hai runner cùng order.

Việc nâng cấp Boot, thay component scanning, thêm dependency hoặc thay cách build có thể khiến thứ tự thu thập candidate thay đổi.

### 8.2. Khi nào cần thứ tự tuyệt đối?

Nếu các bước phải nối tiếp nhau chặt chẽ, cân nhắc đặt chúng vào **một runner điều phối**:

```java
@Component
public class ImportWorkflowRunner implements ApplicationRunner {

    private final PreparationService preparationService;
    private final ImportService importService;
    private final ReportService reportService;

    public ImportWorkflowRunner(
            PreparationService preparationService,
            ImportService importService,
            ReportService reportService
    ) {
        this.preparationService = preparationService;
        this.importService = importService;
        this.reportService = reportService;
    }

    @Override
    public void run(ApplicationArguments args) {
        preparationService.prepare();
        importService.importData();
        reportService.generate();
    }
}
```

Cách này tạo thứ tự rõ ràng theo code gọi method, dễ kiểm soát lỗi và dễ test. `@Order` phù hợp khi cần sắp xếp **nhiều tác vụ độc lập ở pha startup**, còn orchestration nhiều bước có quan hệ phụ thuộc mạnh thường nên có một entry point điều phối.

## 9. @Order không quyết định thứ tự tạo bean

Một nhầm lẫn phổ biến là coi `@Order` trên runner như chỉ dẫn Spring phải **khởi tạo object runner trước** những bean khác.

Đó là hai việc khác nhau.

Spring tạo và inject các bean cần thiết trong quá trình refresh context. Sau đó Boot mới sắp xếp danh sách runner và gọi các phương thức `run(...)`.

```text
GIAI ĐOẠN TẠO BEAN
  Constructor, dependency injection,
  @PostConstruct, initialization
               │
               ▼
      Context refresh hoàn tất
               │
               ▼
GIAI ĐOẠN CHẠY RUNNER
  Sắp xếp theo @Order / Ordered
               │
               ▼
   Gọi run(...) lần lượt
```

Một runner `@Order(100)` hoàn toàn có thể được Spring khởi tạo trước runner `@Order(1)` nếu dependency graph hoặc cơ chế refresh dẫn tới kết quả đó. Điều được sắp xếp là **lời gọi run**, không phải mọi bước khởi tạo bean.

### 9.1. Ví dụ constructor và run có thứ tự khác nhau

```java
@Component
@Order(20)
public class LaterRunner implements CommandLineRunner {

    public LaterRunner() {
        System.out.println("Constructor LaterRunner");
    }

    @Override
    public void run(String... args) {
        System.out.println("Run LaterRunner");
    }
}
```

```java
@Component
@Order(10)
public class EarlierRunner implements CommandLineRunner {

    public EarlierRunner() {
        System.out.println("Constructor EarlierRunner");
    }

    @Override
    public void run(String... args) {
        System.out.println("Run EarlierRunner");
    }
}
```

Khi startup, thứ tự hai dòng constructor có thể phụ thuộc vào cơ chế tạo bean. Nhưng hai dòng `Run ...` được sắp xếp theo order nếu không có lỗi khác:

```text
Run EarlierRunner
Run LaterRunner
```

Không nên dùng log constructor để suy luận rằng `@Order` không hoạt động.

## 10. @DependsOn khác @Order như thế nào?

`@DependsOn` của Spring chỉ định rằng một bean cần được khởi tạo sau một hoặc nhiều bean khác.

Ví dụ:

```java
@Component
public class SetupRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("Setup run");
    }
}
```

```java
@Component
@DependsOn("setupRunner")
public class ImportRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("Import run");
    }
}
```

`@DependsOn("setupRunner")` bảo đảm bean `setupRunner` được **khởi tạo** trước bean `importRunner` theo quan hệ dependency khai báo. Nhưng nó **không tự bảo đảm** lời gọi `setupRunner.run(...)` xảy ra trước `importRunner.run(...)`.

Nếu cần thứ tự runner, phải dùng `@Order` hoặc `Ordered`; nếu cần thứ tự **khởi tạo bean**, dùng dependency injection hoặc `@DependsOn` theo mục đích tương ứng.

### 10.1. Bảng đối chiếu

| Cơ chế | Điều khiển điều gì? | Dùng cho trường hợp nào? |
|---|---|---|
| `@Order` | Thứ tự tương đối khi runner được gọi | Nhiều runner trong startup phase |
| `Ordered#getOrder()` | Thứ tự tương đối khi runner được gọi | Tương tự `@Order`, nhưng giá trị từ instance |
| `@DependsOn` | Quan hệ khởi tạo bean trước/sau | Một bean cần một bean khác được khởi tạo sẵn |
| Constructor injection | Quan hệ dependency để tạo object hợp lệ | Bean A cần instance B |
| `@PostConstruct` | Callback initialization của từng bean | Chuẩn bị bean sau injection |
| `ApplicationReadyEvent` | Event sau khi runner chạy xong | Hành động cần chờ mốc ready |

Nên chọn công cụ theo đúng mốc lifecycle cần điều khiển.

## 11. @Order của runner khác @Order của collection injection

`@Order` được Spring sử dụng trong nhiều ngữ cảnh. Nó có thể giúp sắp xếp các phần tử được inject vào một collection:

```java
@Component
@Order(10)
public class FirstValidator implements OrderValidator {
    // ...
}
```

```java
@Component
@Order(20)
public class SecondValidator implements OrderValidator {
    // ...
}
```

```java
@Service
public class ValidationService {

    private final List<OrderValidator> validators;

    public ValidationService(List<OrderValidator> validators) {
        this.validators = validators;
    }
}
```

Spring có thể cung cấp `validators` theo thứ tự của metadata order.

Đó là cùng ý tưởng **sắp xếp các object trong một tập**, nhưng ngữ cảnh khác với Spring Boot runner invocation. Không nên suy luận rằng `@Order` điều khiển mọi thứ trong Spring, chẳng hạn thứ tự tạo singleton, thứ tự request handling hoặc thứ tự transaction commit.

### 11.1. @Order không giống @Primary

`@Primary` giải quyết một vấn đề khác: khi inject **một bean duy nhất** nhưng có nhiều ứng viên cùng type, Spring ưu tiên bean được đánh dấu primary.

`@Order` chủ yếu được sử dụng khi phải **sắp xếp một tập ứng viên** hoặc các bước xử lý có hỗ trợ ordering.

Ví dụ:

- Cần chọn **một** `PaymentGateway` từ nhiều bean: cân nhắc `@Primary` hoặc `@Qualifier`.
- Cần sắp xếp **nhiều** `ApplicationRunner`: dùng `@Order` hoặc `Ordered`.

Đừng thêm `@Primary` lên runner rồi kỳ vọng nó chạy trước các runner khác. Tương tự, `@Order(1)` không có nghĩa bean đó được chọn thay cho các bean khác khi inject một interface đơn lẻ.

## 12. Ordered, PriorityOrdered và @Priority

Trong hạ tầng Spring còn có các khái niệm gần với ordering:

- `Ordered`: interface cung cấp `getOrder()`.
- `PriorityOrdered`: interface đặc biệt được dùng bởi một số cơ chế Spring để phân biệt nhóm ưu tiên cao ở những giai đoạn như bean post-processing.
- `@Priority`: annotation chuẩn Jakarta có thể được các comparator nhận diện trong một số ngữ cảnh.
- `@Order`: annotation của Spring cho metadata ordering.

Với bài toán sắp xếp `ApplicationRunner` và `CommandLineRunner`, hai lựa chọn dễ hiểu và được tài liệu Spring Boot hướng dẫn trực tiếp là **`Ordered` và `@Order`**.

### 12.1. Không cần dùng PriorityOrdered cho runner thông thường

`PriorityOrdered` có ý nghĩa đặc biệt trong một số cơ chế nội bộ của Spring, nhưng không nên áp dụng nó chỉ vì muốn runner chạy đầu tiên. Với runner, bạn có thể dùng:

```java
@Order(Ordered.HIGHEST_PRECEDENCE)
```

hoặc:

```java
@Override
public int getOrder() {
    return Ordered.HIGHEST_PRECEDENCE;
}
```

Đó là cách trực tiếp để biểu đạt thứ tự chạy.

### 12.2. @Priority không phải @Primary

Dù hai tên gần giống nhau:

- `@Priority` của Jakarta liên quan đến mức ưu tiên/order trong những cơ chế có hỗ trợ.
- `@Primary` của Spring liên quan đến chọn một bean khi dependency injection có nhiều candidate.

Đừng dùng `@Priority` như cách thay thế mặc định cho `@Order` trong một bài hướng dẫn về startup runners nếu chỉ cần số thứ tự đơn giản.

## 13. Ví dụ hoàn chỉnh: ba runner với hai cơ chế ordering

Ta xây dựng một Spring Boot application gồm ba bước:

1. Kiểm tra cấu hình trước khi chạy.
2. Nạp dữ liệu.
3. In báo cáo.

Trong đó runner đầu tiên dùng `Ordered`, hai runner còn lại dùng `@Order`; một số runner là `ApplicationRunner`, số khác là `CommandLineRunner`.

### 13.1. Cấu trúc project

```text
src/main/java/com/example/runnerdemo/
├── RunnerDemoApplication.java
└── startup/
    ├── ValidateConfigurationRunner.java
    ├── ImportDataRunner.java
    └── ReportRunner.java
```

Dependency tối thiểu với Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Giả định project đã cấu hình Spring Boot Gradle plugin và phiên bản Java tương thích với dòng Boot đang dùng.

### 13.2. Main application

```java
package com.example.runnerdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RunnerDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(RunnerDemoApplication.class, args);
    }
}
```

### 13.3. Runner thứ nhất: Ordered + ApplicationRunner

```java
package com.example.runnerdemo.startup;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;

@Component
public class ValidateConfigurationRunner
        implements ApplicationRunner, Ordered {

    @Override
    public int getOrder() {
        return 10;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("01 - Kiểm tra cấu hình");

        if (args.containsOption("dry-run")) {
            System.out.println("Chế độ thử nghiệm đã bật");
        }
    }
}
```

### 13.4. Runner thứ hai: @Order + CommandLineRunner

```java
package com.example.runnerdemo.startup;

import org.springframework.boot.CommandLineRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(20)
public class ImportDataRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("02 - Nạp dữ liệu");
    }
}
```

### 13.5. Runner thứ ba: @Order + ApplicationRunner

```java
package com.example.runnerdemo.startup;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(30)
public class ReportRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("03 - In báo cáo");
    }
}
```

### 13.6. Chạy và quan sát

Chạy chương trình:

```bash
java -jar runner-demo.jar --dry-run
```

Phần log từ các runner minh họa:

```text
01 - Kiểm tra cấu hình
Chế độ thử nghiệm đã bật
02 - Nạp dữ liệu
03 - In báo cáo
```

Lưu ý: các log startup của Spring Boot có thể xuất hiện trước, sau hoặc xen kẽ ở những chỗ khác nhau. Thứ tự được bảo đảm ở đây là **thứ tự lời gọi các runner dựa trên metadata**: `10`, `20`, `30`.

Cơ chế này không phụ thuộc việc runner đầu tiên là `ApplicationRunner`, runner thứ hai là `CommandLineRunner`.

### 13.7. Đổi thứ tự để kiểm chứng

Nếu đổi `ReportRunner` thành:

```java
@Order(5)
```

thì runner báo cáo sẽ được gọi trước validate và import:

```text
03 - In báo cáo
01 - Kiểm tra cấu hình
Chế độ thử nghiệm đã bật
02 - Nạp dữ liệu
```

Ví dụ này cố tình tạo một thứ tự nghiệp vụ không hợp lý để bạn thấy rằng `@Order` chỉ điều khiển **thứ tự kỹ thuật**. Spring không biết báo cáo phải chạy sau khi import trừ khi chính bạn biểu đạt yêu cầu đó.

## 14. Dùng runner như workflow: khi nào nên và không nên?

Có hai cách tổ chức tác vụ startup.

### 14.1. Nhiều runner với thứ tự rõ ràng

```text
@Order(10) ValidateRunner
           │
           ▼
@Order(20) PrepareRunner
           │
           ▼
@Order(30) ReportRunner
```

Phù hợp khi các bước tương đối độc lập, có thể tách thành các startup concern rõ ràng, và nhu cầu điều khiển thứ tự không quá phức tạp.

Tuy nhiên, khi thêm một runner mới ở giữa, người bảo trì phải biết quy ước order của cả hệ thống.

### 14.2. Một orchestration runner

```java
@Component
public class StartupWorkflow implements ApplicationRunner {

    private final DataValidator validator;
    private final DataImporter importer;
    private final ReportGenerator reporter;

    public StartupWorkflow(
            DataValidator validator,
            DataImporter importer,
            ReportGenerator reporter
    ) {
        this.validator = validator;
        this.importer = importer;
        this.reporter = reporter;
    }

    @Override
    public void run(ApplicationArguments args) {
        validator.validate();
        importer.importData();
        reporter.generate();
    }
}
```

Phù hợp khi từng bước phụ thuộc kết quả của bước trước. Thứ tự nằm trực tiếp trong `run`, dễ thiết lập transaction/exception handling ở cấp workflow và dễ test.

Nếu một workflow cần retry, timeout, checkpoint hoặc scheduling phức tạp, có thể cần framework batch/job orchestration thay vì chỉ các runner đơn giản.

## 15. Lỗi trong runner ảnh hưởng mốc ApplicationReadyEvent

Giả sử runner có order 10 ném exception:

```java
@Component
@Order(10)
public class ValidateRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        throw new IllegalStateException("Cấu hình chưa hợp lệ");
    }
}
```

Khi exception không được xử lý, `SpringApplication.run(...)` có thể thất bại. Các runner còn lại có thể không được gọi, và ứng dụng không phát `ApplicationReadyEvent` theo đường startup thành công.

Điều này có thể là hành vi đúng với một validation bắt buộc: nếu cấu hình sai, ứng dụng không nên nhận traffic.

### 15.1. Tránh nuốt lỗi chỉ để chạy hết các runner

Ví dụ:

```java
@Override
public void run(ApplicationArguments args) {
    try {
        validateConfiguration();
    } catch (Exception ex) {
        System.err.println("Validation failed: " + ex.getMessage());
    }
}
```

Nếu validation thất bại nhưng exception bị nuốt, các runner sau vẫn có thể chạy với trạng thái không hợp lệ.

Hãy xác định rõ chính sách lỗi:

- Bước bắt buộc: để lỗi làm startup thất bại hoặc xử lý có chủ đích.
- Bước tùy chọn: log và tiếp tục khi thật sự an toàn.
- Bước có thể retry: thiết kế retry/timeout phù hợp, tránh chặn startup vô hạn.

`@Order` chỉ điều khiển thứ tự; nó không cung cấp transaction, retry hay error recovery.

### 15.2. Runner kéo dài sẽ trì hoãn readiness

```java
@Override
public void run(ApplicationArguments args) throws Exception {
    Thread.sleep(60000);
}
```

Ví dụ trên làm runner block trong lúc startup. Vì `ApplicationReadyEvent` được phát sau runner, thời điểm ready bị trì hoãn.

Trong ứng dụng phục vụ HTTP, hãy cân nhắc mức độ cần thiết của tác vụ trước readiness. Nếu một công việc có thể chạy sau startup mà không ảnh hưởng an toàn khi nhận request, nên thiết kế nó theo cơ chế phù hợp như event, scheduler hoặc background worker thay vì để runner chặn đường startup.

Đối với CLI/batch, runner có thể chính là nhiệm vụ chính, nên việc chờ hoàn tất lại là mong muốn.

## 16. Chạy runner trong ứng dụng có nhiều instance

Runner không được chạy “một lần cho cả hệ thống”. Nó được gọi khi **mỗi ApplicationContext** được khởi động theo quy trình Spring Boot.

Nếu bạn triển khai ba replica của cùng ứng dụng:

```text
Replica A: start -> runners chạy
Replica B: start -> runners chạy
Replica C: start -> runners chạy
```

Một runner tạo tài khoản admin, seed dữ liệu hoặc thực hiện migration có thể chạy ba lần. `@Order` không giúp đồng bộ giữa các replica.

Nếu thao tác phải chạy duy nhất một lần trên toàn hệ thống, cần thiết kế thêm:

- Tính idempotent của tác vụ.
- Database constraint hoặc lock.
- Job/migration orchestration riêng.
- Một cơ chế leader election hoặc distributed lock nếu phù hợp.

Không nên dùng thứ tự `@Order` để giải quyết vấn đề đồng thời giữa nhiều process.

### 16.1. Context restart hoặc integration test

Test khởi động nhiều context độc lập có thể khiến runner chạy nhiều lần. Nếu runner ghi dữ liệu hoặc gọi dịch vụ ngoài, test có thể có side effect ngoài dự kiến.

Có thể dùng `@Profile`, `@ConditionalOnProperty` hoặc cấu hình test để kiểm soát runner nào được đăng ký. Điều này khác với `@Order`: condition quyết định **runner có tồn tại không**, còn order quyết định **runner chạy trước hay sau** trong tập đã có.

## 17. @Order và ApplicationStartedEvent, ApplicationReadyEvent

Một số người muốn dùng `@Order` để “chạy trước sự kiện startup”. Nhưng runner và application event nằm ở các mốc khác nhau.

Ví dụ:

```java
@Component
public class StartupEventLogger {

    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        System.out.println("STARTED event");
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("READY event");
    }
}
```

Và runner:

```java
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class EarlyRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("RUNNER");
    }
}
```

Trình tự điển hình:

```text
STARTED event
RUNNER
READY event
```

Dù runner có order sớm nhất, nó vẫn được gọi **sau `ApplicationStartedEvent`**. `@Order` không thay đổi thứ tự các pha lifecycle của `SpringApplication`.

Nếu bạn có nhiều listener cho cùng một event, cơ chế ordering của event listeners là một chủ đề liên quan nhưng riêng biệt. Đừng coi số order của một runner là số order của một event listener trong cùng một danh sách toàn cục.

### 17.1. Khi nào dùng runner và khi nào dùng event?

| Mục tiêu | Cơ chế phù hợp |
|---|---|
| Cần chạy tác vụ sau context refresh, trước khi app ready | `ApplicationRunner` / `CommandLineRunner` |
| Cần quan sát mốc đã refresh context | `ApplicationStartedEvent` listener |
| Cần xử lý khi ứng dụng báo ready | `ApplicationReadyEvent` listener |
| Cần khởi tạo trạng thái nội bộ của một bean | `@PostConstruct` hoặc init method |
| Cần khởi tạo bean sau bean khác | Dependency injection hoặc `@DependsOn` |
| Cần chạy job định kỳ | `@Scheduled` hoặc scheduler/job framework |

Chọn cơ chế theo **thời điểm cần chạy**, sau đó mới áp dụng ordering trong phạm vi cơ chế đó.

## 18. Một số cách định nghĩa runner bằng @Bean

Không bắt buộc mỗi runner phải là một class `@Component` riêng. Bạn cũng có thể đăng ký chúng bằng `@Bean`:

```java
@Configuration(proxyBeanMethods = false)
public class StartupRunnerConfiguration {

    @Bean
    public CommandLineRunner loggingRunner() {
        return args -> System.out.println("Runner từ @Bean");
    }
}
```

Đây là một bean triển khai `CommandLineRunner` và sẽ được Spring Boot gọi sau startup.

Nếu cần thứ tự rõ ràng cho nhiều runner, cách dễ quan sát là khai báo runner bằng class có `@Order` hoặc implement `Ordered`:

```java
public final class LoggingRunner
        implements CommandLineRunner, Ordered {

    @Override
    public int getOrder() {
        return 50;
    }

    @Override
    public void run(String... args) {
        System.out.println("Runner order 50");
    }
}
```

```java
@Configuration(proxyBeanMethods = false)
public class StartupRunnerConfiguration {

    @Bean
    public CommandLineRunner loggingRunner() {
        return new LoggingRunner();
    }
}
```

Spring Boot sắp xếp runner object theo `getOrder()` mà không phụ thuộc vào việc object đến từ component scan hay phương thức `@Bean`.

### 18.1. Vì sao nên cẩn thận với order đặt trên factory method?

Thứ tự runner được xác định khi Spring Boot lấy **bean instances** và sắp xếp chúng. Nếu bean được trả về là một lambda hoặc object không có `Ordered`, metadata order gắn ở một điểm khác có thể không được áp dụng theo cách bạn kỳ vọng trong mọi phiên bản hoặc tình huống proxy.

Khi thứ tự là yêu cầu quan trọng, hãy để ý định thể hiện rõ trên **runner class** hoặc `Ordered#getOrder()` của instance được trả về. Với code dùng `@Bean`, cách này ít gây hiểu nhầm hơn.

## 19. Chiến lược đặt số order trong dự án thật

Bạn không nhất thiết dùng các giá trị 1, 2, 3. Một quy ước có khoảng trống giúp thêm runner sau này mà không phải đổi mọi số:

| Nhóm runner | Khoảng order ví dụ |
|---|---:|
| Kiểm tra cấu hình bắt buộc | 10–19 |
| Chuẩn bị tài nguyên | 20–29 |
| Seed hoặc import dữ liệu | 30–39 |
| Báo cáo/thông báo startup | 40–49 |

Ví dụ:

```java
@Order(10) // ValidateConfigurationRunner
```

```java
@Order(20) // PrepareCacheRunner
```

```java
@Order(30) // SeedDemoDataRunner
```

```java
@Order(40) // StartupSummaryRunner
```

Đây chỉ là một quy ước nội bộ minh họa. Spring không quy định các khoảng số này.

### 19.1. Có nên khai báo constants?

Nếu nhiều runner thuộc cùng module cần chia sẻ quy ước, có thể tạo constants:

```java
public final class StartupOrder {

    public static final int VALIDATION = 10;
    public static final int PREPARATION = 20;
    public static final int IMPORT = 30;
    public static final int REPORT = 40;

    private StartupOrder() {
    }
}
```

Dùng:

```java
@Component
@Order(StartupOrder.VALIDATION)
public class ValidationRunner implements CommandLineRunner {
    // ...
}
```

Annotation argument cần là compile-time constant. Các `public static final int` được khởi tạo bằng literal đáp ứng yêu cầu đó.

Nếu dự án rất nhỏ, ghi trực tiếp `@Order(10)` có thể đủ rõ. Constants hữu ích khi có nhiều class cần hiểu cùng một hệ thống thứ tự.

### 19.2. Nếu muốn cấu hình order theo property?

Giá trị annotation `@Order` là hằng số được khai báo ở source. Nếu thực sự cần giá trị order do code quyết định, có thể implement `Ordered` và trả về giá trị phù hợp.

Tuy nhiên, quyết định thứ tự startup bằng cấu hình thay đổi liên tục có thể gây khó chẩn đoán. Hãy giữ thứ tự của các bước khởi tạo bắt buộc đơn giản và có thể dự đoán được.

## 20. Các lỗi và hiểu lầm thường gặp

| Hiện tượng | Nguyên nhân hoặc cách hiểu cần xem lại | Hướng xử lý |
|---|---|---|
| Runner không chạy | Class không được đăng ký thành bean | Kiểm tra `@Component`, `@Bean` và component scanning |
| Hai runner chạy sai thứ tự mong đợi | Không có order hoặc cùng giá trị order | Khai báo các giá trị khác nhau |
| `@Order(100)` chạy sau `@Order(1)` | Giá trị nhỏ có precedence cao hơn | Đây là quy tắc đúng |
| Runner được khởi tạo trước nhưng `run` lại chạy sau | Bean initialization khác runner execution | Quan sát đúng phase |
| `@DependsOn` không làm run được gọi trước | `@DependsOn` chủ yếu điều khiển khởi tạo bean | Dùng `@Order`/`Ordered` để sắp xếp runner |
| Có cả ApplicationRunner và CommandLineRunner | Hai loại được sắp xếp chung | Không suy luận thứ tự theo interface |
| Runner bắt đầu rất sớm nhưng event STARTED vẫn chạy trước | Order không thay đổi lifecycle phase | Chọn event hoặc runner theo mốc cần thiết |
| Ứng dụng không ready | Runner ném exception hoặc chạy quá lâu | Kiểm tra lỗi và thời gian chạy runner |
| Runner chạy nhiều lần khi triển khai nhiều replica | Runner chạy theo mỗi context/process | Thiết kế idempotency hoặc orchestration |
| `@Primary` không làm runner chạy trước | `@Primary` dùng cho lựa chọn bean đơn lẻ | Dùng `@Order` hoặc `Ordered` |
| Runner implement cả hai interface bị thực hiện hai callback | Cả hai `run` overload có thể được gọi | Chọn một interface nếu chỉ cần một tác vụ |
| Giá trị `HIGHEST_PRECEDENCE` là số âm rất nhỏ | Comparator ưu tiên số nhỏ trước | Không hiểu “highest” là integer lớn |

### 20.1. Cách đọc log đúng

Nếu bạn đang quan sát thứ tự, hãy in log riêng trong constructor và `run`:

```java
public ExampleRunner() {
    System.out.println("constructor");
}

@Override
public void run(String... args) {
    System.out.println("runner");
}
```

Khi so sánh ordering, chỉ dùng log `run` để kết luận về thứ tự runner. Log constructor phản ánh giai đoạn tạo bean.

### 20.2. Không đoán từ thứ tự package

Các class có thể được scan theo một thứ tự có vẻ ổn định. Nhưng nếu thứ tự là yêu cầu nghiệp vụ, hãy khai báo rõ. Không nên dùng tên như `AFirstRunner` và `BSecondRunner` để ép Spring chạy theo alphabet.

## 21. Quy trình chẩn đoán thứ tự runner

Khi một ứng dụng có nhiều runner mà thứ tự không như dự kiến, áp dụng trình tự:

1. **Xác nhận từng runner có là bean không.** Kiểm tra `@Component`, `@Bean`, profile và conditional registration.
2. **Liệt kê giá trị order thực tế.** Với `@Order` đọc annotation; với `Ordered` xem `getOrder()`.
3. **Kiểm tra runner có cả hai cơ chế không.** `Ordered` có thể quyết định giá trị thay cho annotation.
4. **Đảm bảo các bước cần thứ tự khác nhau.** Tránh dùng cùng order cho các bước có dependency.
5. **Phân biệt log constructor và log run.** Thứ tự tạo bean không phản ánh thứ tự runner.
6. **Kiểm tra có cả ApplicationRunner lẫn CommandLineRunner.** Chúng được sắp xếp chung.
7. **Tìm exception hoặc tác vụ chặn.** Runner trước thất bại hoặc không kết thúc có thể ngăn runner sau chạy.
8. **Kiểm tra số context/process.** Nhiều replica hoặc test context có thể tạo nhiều chuỗi log runner độc lập.
9. **Xem lại thiết kế.** Nếu chuỗi công việc phụ thuộc mạnh, cân nhắc một runner orchestration.

Ví dụ log tối giản:

```text
[RUNNER order=10] validate
[RUNNER order=20] prepare
[RUNNER order=30] import
[RUNNER order=40] report
```

Ghi rõ order trong log rất hữu ích khi ứng dụng có nhiều module hoặc plugin cung cấp runner.

## 22. Bài thực hành

### Bài 1 — Hai CommandLineRunner

Tạo hai bean `CommandLineRunner`, gắn `@Order(10)` và `@Order(20)`. Chạy ứng dụng rồi đổi hai giá trị để quan sát thứ tự log thay đổi.

### Bài 2 — Kết hợp hai loại runner

Tạo một `ApplicationRunner` với `@Order(5)` và một `CommandLineRunner` với `@Order(10)`. Dự đoán thứ tự rồi chạy để xác nhận rằng các runner được sắp xếp chung.

### Bài 3 — Ordered interface

Thay `@Order` của một runner bằng `implements Ordered` với `getOrder() = -10`. Quan sát runner đó chạy trước các runner có order lớn hơn.

### Bài 4 — Cùng giá trị order

Tạo hai runner cùng `@Order(10)`. Quan sát kết quả, sau đó giải thích vì sao không nên dựa vào thứ tự này để xây dựng workflow. Đổi thành `10` và `20` nếu có phụ thuộc thực tế.

### Bài 5 — Bean initialization khác runner execution

In log trong constructor, `@PostConstruct` và `run` của hai runner. Quan sát các dòng khởi tạo có thể không theo thứ tự `@Order` trong khi lời gọi `run` được sắp xếp.

### Bài 6 — @DependsOn

Cho runner B dùng `@DependsOn("runnerA")`, nhưng `@Order` của B nhỏ hơn A. Quan sát và giải thích sự khác biệt giữa thứ tự **tạo bean** và thứ tự **chạy run**.

### Bài 7 — Thử lỗi startup

Cho runner có order nhỏ nhất ném `IllegalStateException`. Quan sát các runner sau và việc phát `ApplicationReadyEvent`. Sau đó xử lý lỗi có chủ đích để khôi phục startup.

### Bài 8 — Dùng ApplicationArguments

Tạo `ApplicationRunner` đọc `--mode=import`. Thêm runner chuẩn bị dữ liệu trước đó bằng `@Order`. Giải thích khi nào cần dùng `ApplicationArguments` thay vì `String... args`.

### Bài 9 — Một orchestration runner

Gộp ba bước validate, import, report vào một `ApplicationRunner`. So sánh cách đọc code, xử lý lỗi và test với phương án ba runner có `@Order`.

### Bài 10 — Nhiều instance

Giả lập hai lần khởi động ApplicationContext. Quan sát runner chạy hai lần và thảo luận cách bảo đảm một tác vụ seed dữ liệu không tạo bản ghi trùng lặp.

## 23. Tài liệu tham khảo chính thức

- [Spring Boot Reference — SpringApplication: CommandLineRunner and ApplicationRunner](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.command-line-runner): vòng đời runner và hướng dẫn sắp xếp với `Ordered` hoặc `@Order`.
- [Spring Boot API — ApplicationRunner](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/ApplicationRunner.html): phương thức `run(ApplicationArguments)`.
- [Spring Boot API — CommandLineRunner](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/CommandLineRunner.html): phương thức `run(String... args)`.
- [Spring Framework API — Ordered](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/Ordered.html): `getOrder()` và các hằng số precedence.
- [Spring Framework API — Order](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/annotation/Order.html): annotation khai báo order.
- [Spring Boot Reference — Application Events and Listeners](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.application-events-and-listeners): vị trí của `ApplicationStartedEvent` và `ApplicationReadyEvent` trong startup.

**`Ordered` và `@Order` giải quyết thứ tự gọi các runner trong Spring Boot.** Giá trị order càng nhỏ thì runner chạy càng sớm; `ApplicationRunner` và `CommandLineRunner` tham gia cùng một danh sách sắp xếp. Việc sắp xếp này diễn ra sau khi context refresh, vì vậy không thể dùng order của runner để điều khiển constructor hoặc `@PostConstruct` của các bean. Khi các tác vụ có phụ thuộc chặt chẽ, hãy biểu đạt thứ tự và cách xử lý lỗi rõ ràng, có thể bằng một runner điều phối thay vì chỉ dựa vào các con số order.

# Điều phối nhiều runner với `Ordered` và `@Order`

Trong Spring Boot, `ApplicationRunner` và `CommandLineRunner` là các điểm mở rộng để chạy công việc **sau khi `ApplicationContext` đã refresh** và **trước khi `SpringApplication.run(...)` hoàn tất**. Một ứng dụng có thể có nhiều runner: kiểm tra cấu hình, nạp dữ liệu nền, chuẩn bị cache và xác nhận trạng thái hệ thống. Nếu chúng phải thực hiện theo một trật tự, Spring Boot hỗ trợ **`org.springframework.core.Ordered`** hoặc **`org.springframework.core.annotation.Order`**.

Mục tiêu của bài này là hiểu **giá trị order**, cách Spring Boot trộn cả hai loại runner vào **một thứ tự chung**, cách khai báo bằng annotation và interface, điều gì xảy ra khi runner đồng hạng hoặc lỗi, cùng ví dụ **Java 17 + Spring Boot 3.3.x** có thể chạy để quan sát kết quả.

## 1. Runner nằm ở đâu trong vòng đời startup?

~~~text
SpringApplication.run(args)
   |
   +-- Chuẩn bị Environment
   +-- Tạo và refresh ApplicationContext
   +-- Hoàn thành các singleton không lazy cần khởi tạo sớm
   |
   +-- ApplicationStartedEvent
   |        Runner chưa được gọi
   |
   +-- Thu thập các bean ApplicationRunner / CommandLineRunner
   +-- Xác định order và sắp thứ tự
   +-- Chạy từng runner theo thứ tự đã sắp
   |
   +-- ApplicationReadyEvent
   +-- ReadinessState.ACCEPTING_TRAFFIC
   |
   v
SpringApplication.run trả về ConfigurableApplicationContext
~~~

Trong Spring Boot 3.3, sự kiện `ApplicationStartedEvent` được phát **trước** các runner. `ApplicationReadyEvent` được phát **sau** khi tất cả runner chạy thành công. Dòng log `Started ... in ... seconds` thường xuất hiện tại mốc started; không nên hiểu rằng mọi runner đã hoàn tất khi nhìn thấy log đó.

Runner **là bean Spring**. Container có thể tạo instance runner và chạy callback `@PostConstruct` trong giai đoạn refresh, nhưng **phương thức `run(...)` của runner** được Spring Boot gọi sau đó. Đây là hai thứ tự độc lập: **thứ tự tạo bean** và **thứ tự thực thi runner**.

## 2. Hai giao diện runner

### `ApplicationRunner`

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;

public final class OptionsRunner implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        System.out.println("mode=" + args.getOptionValues("mode"));
    }
}
~~~

`ApplicationRunner.run(ApplicationArguments)` nhận một đối tượng đã phân tích dòng lệnh. Các phương thức hữu ích: `getSourceArgs()`, `getOptionNames()`, `containsOption(...)`, `getOptionValues(...)` và `getNonOptionArgs()`. Với đối số `--mode=demo`, `getOptionValues("mode")` trả về một danh sách chứa `demo`.

Class ví dụ **chỉ được Spring Boot gọi khi đã được đăng ký làm bean**, ví dụ qua `@Component` hoặc `@Bean`; chỉ tạo tệp Java không tự làm nó thành runner.

### `CommandLineRunner`

~~~java
import java.util.Arrays;
import org.springframework.boot.CommandLineRunner;

public final class RawRunner implements CommandLineRunner {
    @Override
    public void run(String... args) {
        System.out.println("args=" + Arrays.toString(args));
    }
}
~~~

`CommandLineRunner.run(String...)` nhận mảng đối số gốc. Với `--mode=demo`, `Arrays.toString(args)` cho `[--mode=demo]`.

| Nhu cầu | Giao diện thuận tiện |
| --- | --- |
| Phân tích option theo tên/giá trị | `ApplicationRunner` |
| Đọc đúng các chuỗi đối số ban đầu | `CommandLineRunner` |
| Chạy công việc một lần sau refresh | Cả hai |
| Áp dụng `Ordered` hoặc `@Order` | Cả hai |

**Không có quy tắc “toàn bộ `ApplicationRunner` chạy trước toàn bộ `CommandLineRunner`”.** Chúng được sắp thứ tự cùng nhau.

## 3. Quy tắc: order **nhỏ** chạy **trước**

| Bean runner | Order | Vị trí dự kiến |
| --- | ---: | ---: |
| Kiểm tra cấu hình | 10 | 1 |
| Nạp dữ liệu | 20 | 2 |
| Chuẩn bị cache | 30 | 3 |
| Hoàn tất thiết lập | 40 | 4 |
| Không chỉ định order | `Ordered.LOWEST_PRECEDENCE` | Cuối trong nhóm ví dụ |

`@Order(1)` chạy trước `@Order(10)`; `@Order(10)` chạy trước `@Order(100)`. Giá trị âm vẫn hợp lệ, nhưng trong dự án thường chọn những mức rõ ràng để dễ bảo trì.

Hai hằng số:

- `Ordered.HIGHEST_PRECEDENCE` = `Integer.MIN_VALUE`, ưu tiên cao nhất.
- `Ordered.LOWEST_PRECEDENCE` = `Integer.MAX_VALUE`, ưu tiên thấp nhất.

Một runner không được cấu hình thứ tự thường được comparator xem ở mức `LOWEST_PRECEDENCE`. **Nếu hai runner cùng order**, không nên dựa vào thứ tự của chúng để làm điều kiện nghiệp vụ; hãy đặt mức khác nhau hoặc điều phối bằng một runner duy nhất.

## 4. Cách 1: khai báo `@Order`

Import:

~~~java
import org.springframework.core.annotation.Order;
~~~

Đặt trên class:

~~~java
@Order(10)
public final class ValidateRunner implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        System.out.println("validate");
    }
}
~~~

Đoạn này cần import `ApplicationRunner` và `ApplicationArguments` và phải được đăng ký thành bean để được gọi. Annotation đặt mức ưu tiên **10** cho runner class.

Đặt trên phương thức factory `@Bean`:

~~~java
@Bean
@Order(20)
CommandLineRunner loadReferenceData() {
    return args -> System.out.println("load data");
}
~~~

Đây là **phương thức nằm trong class cấu hình** có các import `Bean`, `Order` và `CommandLineRunner`. Trong Spring Boot **3.3.13**, logic sắp runner có thể đọc `@Order` từ **factory method tạo bean**; vì vậy cách đặt annotation này cũng hợp lệ.

**Không nên** chỉ gắn `@Order` lên class cấu hình rồi nghĩ rằng toàn bộ các runner do những phương thức `@Bean` trong class đó tạo ra đều nhận cùng một mức ưu tiên. Hãy đặt annotation lên đúng **class runner** hoặc **factory method runner**.

`@Order` phù hợp khi mức ưu tiên cố định, dễ đọc. Nó **không quyết định thứ tự Spring tạo tất cả singleton bean**; thứ tự tạo bean chịu tác động của quan hệ phụ thuộc và các quy tắc container khác.

## 5. Cách 2: triển khai `Ordered`

Import:

~~~java
import org.springframework.core.Ordered;
~~~

Với `Ordered`, object cung cấp order qua `getOrder()`:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.Ordered;

public final class CacheRunner implements ApplicationRunner, Ordered {
    private final int priority;

    public CacheRunner(int priority) {
        this.priority = priority;
    }

    @Override
    public int getOrder() {
        return priority;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("cache priority=" + priority);
    }
}
~~~

Đăng ký bean:

~~~java
@Bean
ApplicationRunner cacheRunner() {
    return new CacheRunner(30);
}
~~~

Đoạn factory method trên phải nằm trong class cấu hình có import `Bean`. Runner trả về order 30. Với hai instance `new CacheRunner(10)` và `new CacheRunner(20)` được đăng ký dưới hai tên bean khác nhau, chúng có thể được sắp theo **giá trị của từng instance**.

| Tiêu chí | `@Order` | `Ordered` |
| --- | --- | --- |
| Nguồn order | Annotation trên class/factory method | `getOrder()` của instance |
| Thường có giá trị cố định | Có | Có thể, nhưng cũng có thể lấy từ constructor |
| Cần method riêng | Không | Có |
| Phù hợp | Runner đơn giản, ít tùy biến | Class runner tái sử dụng với nhiều mức ưu tiên |

Tránh đồng thời khai báo hai mức order mâu thuẫn bằng `@Order` và `Ordered` trên cùng một bean. Người đọc khó biết nên coi mức nào là nguồn chính, và code trở nên khó bảo trì.

`getOrder()` nên ổn định, chạy nhanh và không gây tác dụng phụ. Spring Boot xác định thứ tự tại thời điểm gọi các runner, không tự chạy lại toàn bộ runner khi một thuộc tính order thay đổi sau đó.

## 6. Cơ chế điều phối thực tế trong Spring Boot 3.3

Mã nguồn `SpringApplication.callRunners(...)` của Spring Boot 3.3.13 thể hiện các bước:

1. Lấy những bean thuộc giao diện chung `Runner` từ `ApplicationContext`; các bean này có thể là `ApplicationRunner` hoặc `CommandLineRunner`.
2. Gắn instance với tên bean để tra cứu thông tin thứ tự từ metadata của bean/factory method khi cần.
3. Sắp tất cả bean runner bằng comparator có hỗ trợ `Ordered` và `@Order`.
4. Với từng object đã sắp, gọi callback của giao diện mà object thực hiện.
5. Khi không có exception, tiếp tục đến mốc ready.

Ví dụ:

~~~text
ApplicationRunner A: order 30
CommandLineRunner B: order 10
ApplicationRunner C: order 20

Thứ tự gọi: B -> C -> A
~~~

Vì sắp **một tập chung**, `CommandLineRunner` order 10 có thể chạy trước `ApplicationRunner` order 20.

### Bean triển khai cả hai interface

Một object có thể thực hiện cả `ApplicationRunner` và `CommandLineRunner`:

~~~java
public final class DualRunner
        implements ApplicationRunner, CommandLineRunner, Ordered {

    @Override
    public int getOrder() {
        return 50;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("application callback");
    }

    @Override
    public void run(String... args) {
        System.out.println("command-line callback");
    }
}
~~~

Đoạn mã cần các import tương ứng và phải đăng ký bean. Với Spring Boot 3.3.13, khi đến lượt object này, `SpringApplication` có thể gọi **cả hai phương thức**; phần do chúng in là:

~~~text
application callback
command-line callback
~~~

Đừng dùng cả hai giao diện chỉ để làm cùng một tác vụ hai lần. Nếu hai việc độc lập, hai runner bean riêng với mức order rõ ràng thường dễ quản lý hơn.

## 7. Ví dụ thực hành Java 17 / Spring Boot 3.3: năm runner

Ứng dụng sau chạy không có web server, tránh log Tomcat. Nó thể hiện:

- `@Order` trên **class `ApplicationRunner`**;
- `@Order` trên **phương thức `@Bean` tạo `CommandLineRunner`**;
- `Ordered` trên **instance `ApplicationRunner`**;
- Runner có order lớn hơn;
- Runner không có order.

### Tạo dự án

Cấu trúc:

~~~text
ordered-runners/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/ordered/OrderedRunnersApplication.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'ordered-runners'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'com.example'
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
    // Native BOM để xác định version cho các dependency Spring Boot.
    implementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

**Lưu ý Gradle:** Spring Boot plugin kết hợp với Gradle native BOM ở trên cung cấp quản lý phiên bản cho starter không ghi version. Nếu dùng project có sẵn đã có cơ chế dependency-management khác, dùng cơ chế phù hợp với project thay vì khai báo trùng.

Tệp `src/main/java/com/example/ordered/OrderedRunnersApplication.java`:

~~~java
package com.example.ordered;

import java.util.Arrays;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;

@SpringBootApplication
public class OrderedRunnersApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(OrderedRunnersApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("MAIN active=" + context.isActive());
        }
    }

    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        System.out.println("EVENT started");
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("EVENT ready");
    }

    @Bean
    ApplicationRunner validate() {
        return new ValidateRunner();
    }

    @Order(10)
    static final class ValidateRunner implements ApplicationRunner {
        @Override
        public void run(ApplicationArguments args) {
            System.out.println(
                "RUN 10 mode=" + args.getOptionValues("mode"));
        }
    }

    @Bean
    @Order(20)
    CommandLineRunner prepareData() {
        return args -> System.out.println(
            "RUN 20 args=" + Arrays.toString(args));
    }

    @Bean
    ApplicationRunner prepareCache() {
        return new CacheRunner(30);
    }

    static final class CacheRunner implements ApplicationRunner, Ordered {
        private final int order;

        CacheRunner(int order) {
            this.order = order;
        }

        @Override
        public int getOrder() {
            return order;
        }

        @Override
        public void run(ApplicationArguments args) {
            System.out.println("RUN " + order + " cache");
        }
    }

    @Bean
    @Order(40)
    CommandLineRunner finalSetup() {
        return args -> System.out.println("RUN 40 setup");
    }

    @Bean
    CommandLineRunner unrankedRunner() {
        return args -> System.out.println("RUN default");
    }
}
~~~

Đây là chương trình hoàn chỉnh **trong dự án Spring Boot có dependencies đã khai báo**, không biên dịch bằng `javac OrderedRunnersApplication.java` đơn lẻ. Hai class nested được tạo bằng `@Bean`, không cần thêm `@Component`. Đừng khai báo thêm một bean runner khác vô tình trùng chức năng của chúng.

Các phương thức `@EventListener` ở class cấu hình được Spring đăng ký khi context khởi tạo, để nhận các sự kiện started/ready xuất hiện sau refresh.

### Chạy và kết quả

Nếu dự án có Gradle Wrapper tương thích:

~~~bash
./gradlew bootRun --args="--mode=demo"
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun --args="--mode=demo"
~~~

Nếu chưa có wrapper nhưng đã cài Gradle tương thích:

~~~bash
gradle bootRun --args="--mode=demo"
~~~

Phần **do `System.out.println` trong mã ví dụ** tạo ra theo thứ tự trong lần chạy thành công:

~~~text
EVENT started
RUN 10 mode=[demo]
RUN 20 args=[--mode=demo]
RUN 30 cache
RUN 40 setup
RUN default
EVENT ready
MAIN active=true
~~~

Các log Gradle/Spring khác có thể xen vào; đây chỉ là những dòng do demo chủ động in.

Đọc kết quả:

1. `EVENT started` ở đầu vì `ApplicationStartedEvent` xuất hiện trước runner.
2. `RUN 10` được ưu tiên do `@Order(10)` trên class `ValidateRunner`.
3. `RUN 20` là `CommandLineRunner` với `@Order(20)` trên phương thức `@Bean`, vẫn chạy trước `ApplicationRunner` order 30.
4. `RUN 30` là `ApplicationRunner` triển khai `Ordered`.
5. `RUN 40` chạy sau 30; runner không order ở cuối.
6. `EVENT ready` chứng minh các runner đã hoàn tất trên đường thành công.
7. `MAIN active=true` chứng minh `SpringApplication.run(...)` đã trả về context.

### Thí nghiệm: đổi thứ tự

Đổi `@Order(40)` của `finalSetup()` thành `@Order(5)` và đồng thời đổi chuỗi in từ `RUN 40 setup` thành `RUN 5 setup`. Runner đó sẽ được gọi **trước** `ValidateRunner` order 10, mặc dù nó nằm dưới trong file source.

### Thí nghiệm: order bằng nhau

Đổi hai runner thành cùng `@Order(20)`. Không nên coi thứ tự in thực tế của hai runner đồng mức là một cam kết thiết kế. Đối với các bước phụ thuộc chặt chẽ, hãy đặt số khác nhau hoặc gom thành một runner điều phối tường minh.

## 8. Vì sao order bằng nhau không đủ cho phụ thuộc nghiệp vụ?

Một giá trị order chỉ thể hiện **độ ưu tiên tương đối**. Nếu A và B cùng order 10, chúng cùng mức. Thứ tự thu thập bean và những chi tiết triển khai khác có thể ảnh hưởng đến tie-break, không phải thứ tự được cam kết như một hợp đồng cho nghiệp vụ.

Hậu quả: nếu runner B cần dữ liệu runner A tạo, việc để cả hai ở order 10 sẽ tạo ra phụ thuộc ngầm dễ lỗi. Nên sửa thành:

~~~text
A: @Order(10) -> chuẩn bị dữ liệu
B: @Order(20) -> xác nhận dữ liệu đã sẵn sàng
~~~

Hoặc gom trong một runner:

~~~text
StartupWorkflowRunner.run(...)
   +-- validateConfiguration()
   +-- loadReferenceData()
   +-- warmUpCache()
~~~

Cách thứ hai phù hợp khi những bước này **thật sự là một quy trình gắn chặt** và cần quản lý lỗi, transaction hoặc retry thống nhất.

Trong Spring Boot 3.3.13, cơ chế thu thập runner có dùng một map theo identity của instance trước bước sắp xếp. Điều này càng củng cố việc **không dựa vào thứ tự ngẫu nhiên của các bean đồng hạng**.

## 9. `@Order` chỉ bảo đảm thứ tự **gọi**, không bảo đảm tác vụ async đã hoàn tất

Spring Boot gọi phương thức `run(...)` theo thứ tự. Nhưng nếu runner A chỉ khởi chạy công việc nền rồi trả về, runner B có thể chạy khi việc A chưa hoàn tất.

Ví dụ minh họa:

~~~java
@Override
public void run(ApplicationArguments args) {
    executor.submit(this::loadData);
    // Runner trả về khi task có thể vẫn đang chạy.
}
~~~

Đoạn này **không độc lập**, giả định class có `executor` và `loadData`. Nếu runner B cần dữ liệu từ A, phải có cơ chế đồng bộ hoàn tất, hoặc runner A chờ điều kiện cần thiết trước khi trả về. Chỉ đặt `@Order(10)` cho A và `@Order(20)` cho B **không đủ** để bảo đảm công việc nền của A đã xong.

Tương tự, một runner có vòng lặp vô hạn sẽ ngăn `SpringApplication.run` đi tiếp đến mốc ready. Với consumer hay worker hoạt động lâu dài, xem xét quản lý bằng `SmartLifecycle` và hệ thống readiness phù hợp.

## 10. Nếu một runner ném exception

Giả sử ba runner có order 10, 20, 30. Runner 20 ném exception:

~~~java
@Bean
@Order(20)
CommandLineRunner failingStep() {
    return args -> {
        throw new IllegalStateException("Required data unavailable");
    };
}
~~~

Đây là **đoạn minh họa trong class cấu hình**, cần import `Bean`, `Order`, `CommandLineRunner`. Không thêm vào bản demo mặc định nếu không chủ định kiểm thử nhánh lỗi.

Diễn biến:

~~~text
Runner 10: hoàn tất
Runner 20: ném IllegalStateException
Runner 30: không chạy trên đường thành công
ApplicationReadyEvent: không được phát trên đường thành công
SpringApplication.run: không trả về như một lần startup thành công
~~~

Spring Boot sẽ xử lý lỗi khởi động; khi chẩn đoán, đọc **root cause** và tên runner gặp lỗi trong stack trace. Việc runner 20 thất bại không có nghĩa các tác dụng phụ của runner 10 được tự động rollback: giao dịch, idempotency và bước bù phải được thiết kế rõ ràng nếu cần.

## 11. Thứ tự runner và readiness

Runner thường dùng để chuẩn bị ứng dụng trước khi báo sẵn sàng nhận lưu lượng:

~~~text
Context refreshed
   |
   +-- ApplicationStartedEvent
   +-- @Order(10): kiểm tra cấu hình
   +-- @Order(20): nạp dữ liệu bắt buộc
   +-- @Order(30): warm up cache
   |
   +-- ApplicationReadyEvent
   +-- ReadinessState.ACCEPTING_TRAFFIC
~~~

Tuy nhiên, readiness không có nghĩa **mọi phụ thuộc ngoài đều luôn khỏe**; hệ thống vận hành cần health/readiness checks thích hợp. Nếu runner trả về khi một task nền vẫn chạy, Spring Boot có thể tiến tới ready trước khi task hoàn tất. Nếu máy chủ web đã mở cổng trong refresh, cũng không được suy ra là mọi runner hoàn thành.

## 12. Phân biệt các cơ chế cùng tên

| Cơ chế | Điều khiển | Không tự điều khiển |
| --- | --- | --- |
| `@Order` / `Ordered` trên runner | Thứ tự gọi các runner `run(...)` | Constructor hay `@PostConstruct` của mọi bean |
| Constructor injection / `@DependsOn` | Quan hệ tạo bean | Thứ tự gọi nhiều runner độc lập |
| `SmartLifecycle.getPhase()` | Thứ tự start/stop của Lifecycle bean | Thứ tự gọi runner |
| `@Order` trên listener | Thứ tự gọi listener ở điểm phát event hỗ trợ sắp xếp | Runner |
| `ApplicationStartedEvent` | Mốc sau refresh, trước runner | Mốc sau runner |
| `ApplicationReadyEvent` | Mốc sau runners thành công | Bảo đảm mọi hệ thống ngoài luôn sẵn sàng |

Đặt `@Order(10)` lên runner không có nghĩa Spring sẽ tạo class đó trước mọi singleton `@Order(20)`. Thứ tự khởi tạo đi theo graph phụ thuộc và quy tắc container.

## 13. Lỗi phổ biến

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Class runner không chạy | Chưa đăng ký bean | Dùng `@Component` hoặc `@Bean` |
| Runner nằm ở cuối file nhưng chạy trước | Có order ưu tiên cao hơn | Đọc giá trị `@Order`/`getOrder()` |
| `CommandLineRunner` chạy trước `ApplicationRunner` | Hai giao diện được sắp chung | Không dựa vào loại interface |
| Runner đồng order có thứ tự không mong muốn | Không có tie-break bảo đảm | Dùng order khác nhau |
| Runner không order chạy cuối | `LOWEST_PRECEDENCE` | Chỉ định order nếu cần |
| `@Order` không làm constructor chạy trước | Order runner khác order khởi tạo bean | Đọc quan hệ dependency |
| Runner A submit async, B thiếu dữ liệu | A mới khởi động task | Chờ hoàn tất hoặc đồng bộ tường minh |
| `ApplicationReadyEvent` không đến | Runner treo hoặc lỗi | Xem stack trace, timeout, thread dump |
| Dữ liệu bị tạo lặp sau restart | Runner không idempotent | Kiểm tra trạng thái, giao dịch phù hợp |
| Cùng bean triển khai hai runner interface | Callback có thể chạy hai lần | Tách chức năng hoặc dùng một interface |
| `build.gradle` không phân giải starter | Thiếu BOM/dependency management | Import Spring Boot BOM hoặc plugin tương thích |

## 14. Tự kiểm tra

1. `CommandLineRunner` order 10 và `ApplicationRunner` order 20, ai chạy trước? **Runner order 10**.
2. `@Order(0)` hay `@Order(100)` ưu tiên cao hơn? **0**.
3. Runner không có order thường ở mức nào? **`LOWEST_PRECEDENCE`**.
4. `Ordered` lấy ưu tiên qua đâu? **`getOrder()` của instance**.
5. `@Order` làm `@PostConstruct` chạy theo thứ tự tương ứng không? **Không**.
6. Hai runner cùng order có bảo đảm thứ tự không? **Không nên dựa vào thứ tự đồng hạng**.
7. Runner 10 chỉ submit task nền, runner 20 có phải chờ task kết thúc không? **Không tự động**.
8. Runner order 20 ném exception chưa xử lý, runner 30 có được gọi theo đường thành công không? **Không**.
9. `ApplicationStartedEvent` xuất hiện trước hay sau runner? **Trước**.
10. `ApplicationReadyEvent` xuất hiện trước hay sau runner? **Sau khi các runner thành công**.
11. Trong Spring Boot 3.3, `@Order` trên factory method `@Bean` tạo runner có tác dụng không? **Có**.
12. Một bean triển khai cả hai giao diện có thể nhận hai callback không? **Có**.
13. Vì sao `getOrder()` không nên thực hiện network I/O? **Vì sắp xếp cần nhanh, ổn định và không có tác dụng phụ**.
14. Ba bước startup phụ thuộc chặt nên tổ chức ra sao? **Dùng order khác nhau và đảm bảo hoàn tất, hoặc orchestrator runner tường minh**.

**Ghi nhớ:** `Ordered` và `@Order` điều khiển **thứ tự Spring Boot gọi phương thức `run(...)`**, không phải thứ tự tạo bean. `ApplicationRunner` và `CommandLineRunner` được sắp **chung**, số nhỏ chạy trước; các runner đồng thứ tự không nên dùng làm phụ thuộc nghiệp vụ; công việc bất đồng bộ không tự hoàn tất chỉ nhờ `@Order`.

### Tài liệu tham khảo

- Spring Boot 3.3 — Using the ApplicationRunner or CommandLineRunner: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3.13 — ApplicationRunner API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html
- Spring Boot 3.3.13 — CommandLineRunner API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/CommandLineRunner.html
- Spring Boot 3.3.13 — SpringApplication.callRunners source: https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot/src/main/java/org/springframework/boot/SpringApplication.java
- Spring Framework 6.1 — Ordered: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/Ordered.html
- Spring Framework 6.1 — Order: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/annotation/Order.html
- Spring Boot 3.3 Gradle plugin — dependency management: https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html

# Phân biệt khởi tạo một lần mỗi tiến trình với công việc chỉ được chạy một lần toàn hệ thống

## 1. Vấn đề cốt lõi: “chạy một lần” là một hợp đồng chưa đủ rõ

Trong Spring Boot, **ApplicationRunner** và **CommandLineRunner** được SpringApplication gọi sau khi ApplicationContext đã refresh và trước mốc ứng dụng ready. Chúng rất phù hợp để khởi tạo cache, kiểm tra cấu hình hoặc thực hiện startup task. Tuy nhiên, câu “runner chạy một lần” **không có nghĩa là tác vụ chỉ chạy đúng một lần trong toàn bộ hệ thống phân tán**.

Một ứng dụng có thể có nhiều tiến trình JVM, Pod, container, replica, máy chủ hoặc những lần khởi động lại. Mỗi lần một SpringApplication với các runner bean được khởi động thành công đến giai đoạn runner, những runner đó lại được gọi. Bởi vậy, nếu đặt tác vụ gửi email chào mừng, ghi dữ liệu khởi tạo hoặc thanh toán định kỳ ngay trong runner mà không có kiểm soát dùng chung, **mỗi instance có thể thực hiện lại tác vụ**.

Có hai loại yêu cầu rất khác nhau:

- **Khởi tạo cục bộ theo lần khởi động của từng tiến trình/instance:** mỗi JVM hoặc mỗi ApplicationContext cần chuẩn bị tài nguyên riêng. Chạy lặp lại sau restart là hành vi mong muốn.
- **Công việc chỉ được áp dụng một lần theo phạm vi toàn hệ thống:** các replica và những lần restart cùng nhìn thấy trạng thái đã hoàn thành, không được tạo tác dụng phụ trùng cho cùng **khóa nghiệp vụ**. Yêu cầu này cần một cơ chế điều phối hoặc kiểm soát tính duy nhất **ngoài bộ nhớ của từng JVM**.

Bài học tập trung vào cách chọn nơi đặt logic, điều kiện cạnh tranh giữa nhiều instance, transaction, idempotency và các giới hạn thực tế của lời hứa “exactly once”.

## 2. Runner thực sự có hợp đồng gì?

Spring Boot hỗ trợ hai loại runner:

~~~java
public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}
~~~

~~~java
public interface CommandLineRunner {
    void run(String... args) throws Exception;
}
~~~

Đây là **chữ ký rút gọn để học**, bỏ package và annotation; khi lập trình phải dùng interface chính thức trong package **org.springframework.boot**. Cả hai loại bean được gọi trong chuỗi **SpringApplication.run(...)** sau **ApplicationStartedEvent** và trước **ApplicationReadyEvent**. Chúng khác chủ yếu ở cách nhận tham số: ApplicationRunner nhận **ApplicationArguments** đã phân tích; CommandLineRunner nhận mảng đối số thô.

Những điểm cần phân biệt:

1. Với một lần startup đi đến giai đoạn runner và một runner bean được đăng ký, SpringApplication thông thường gọi **run(...) một lần cho bean đó trong lần startup ấy**.
2. Nếu tiến trình khởi động lại, đó là **một lần startup mới** và runner lại có cơ hội chạy.
3. Nếu triển khai **ba replica**, mỗi replica có JVM/context riêng và có thể chạy cùng runner, thường là ba lần startup độc lập.
4. Nếu trong cùng một JVM có nhiều SpringApplication hoặc một cấu trúc context đặc biệt, cần đánh giá từng context; không nên coi “một lần mỗi JVM” là bảo đảm tuyệt đối của API.
5. Có thể có nhiều runner bean. **@Order/Ordered** chỉ sắp thứ tự các runner trong **cùng một SpringApplication**, không đồng bộ các tiến trình JVM khác nhau.
6. Nếu runner ném exception, startup thất bại trước nhánh ready thành công. Một hệ thống điều phối có thể restart instance, khi đó runner có thể **được gọi lại**.

**Thuật ngữ chính xác:** Runner là hook **mỗi lần ứng dụng khởi động**, không phải dịch vụ “run once for the whole cluster”. Nếu muốn khẳng định công việc chạy một lần toàn hệ thống, cần định nghĩa phạm vi và cơ chế bảo đảm độc lập với runner.

## 3. Hai mô hình đặt cạnh nhau

| Tiêu chí | Một lần mỗi startup/instance | Một lần toàn hệ thống theo khóa |
| --- | --- | --- |
| Phạm vi | JVM/ApplicationContext đang khởi động | Kho dữ liệu hoặc bộ điều phối chung cho các instance |
| Khi restart | Thường phải làm lại | Không làm lại nếu cùng khóa đã hoàn tất |
| Khi scale từ 1 lên 3 Pod | Mỗi Pod chạy bước khởi tạo của riêng mình | Chỉ một kết quả nghiệp vụ được chấp nhận cho cùng khóa |
| Cơ chế cơ bản | Runner, bean lifecycle, initialization | Unique constraint, transaction, idempotency, coordination/job orchestration |
| State trong biến Java | Có thể phù hợp cho state cục bộ | Không đủ vì mỗi process có bộ nhớ riêng |
| Mất Pod hoặc JVM | State RAM biến mất; startup mới làm lại | State hoàn thành phải tồn tại ở kho bền vững bên ngoài |
| Mục tiêu thường gặp | Nạp cache tại node, khởi tạo metric, cấu hình kết nối | Dữ liệu seed theo phiên bản, phát hành tác vụ một lần theo kỳ, migration |
| Kiểm thử quan trọng | Restart, startup failure, thứ tự runner | Nhiều replica cùng lúc, crash/retry, trùng request, tính nguyên tử |

Ví dụ **khởi tạo mỗi tiến trình**: Mỗi replica cần một cache nóng để phục vụ HTTP. Replica A nạp cache A, replica B nạp cache B. Nếu B không nạp lại cache khi restart, B có thể phục vụ request với state chưa đủ. Vì vậy **lặp lại là điều đúng**.

Ví dụ **một lần toàn hệ thống**: Hệ thống cần tạo bản ghi “đã áp dụng gói dữ liệu chuẩn v3” trong database dùng chung. Nếu mỗi replica đều insert một bộ dữ liệu giống nhau khi startup, có thể trùng bản ghi hoặc trùng tác dụng phụ. Cần kiểm soát bằng ràng buộc dữ liệu, transaction và một khóa nhận diện gói dữ liệu v3.

## 4. Câu hỏi đầu tiên: “một lần” theo khóa nào?

Trước khi chọn công cụ, hãy xác định chính xác **đơn vị công việc**. “Một lần” có thể có nhiều ý nghĩa:

- **Một lần cho từng lần khởi động:** mỗi instance khởi tạo một state cục bộ.
- **Một lần trong toàn bộ vòng đời sản phẩm:** ví dụ tạo danh mục ban đầu khi cài hệ thống mới.
- **Một lần cho mỗi phiên bản dữ liệu:** ví dụ áp dụng seed script phiên bản v3 đúng một lần, còn v4 là một công việc mới.
- **Một lần cho mỗi khách hàng:** mỗi tenant được tạo tài nguyên khởi đầu một lần.
- **Một lần mỗi kỳ:** gửi thông báo hoặc chốt số liệu theo bộ khóa (tenant, tháng, loại báo cáo).
- **Một lần cho từng request nghiệp vụ:** mỗi idempotency key chỉ tạo một hiệu ứng logic, dù client retry.

Nếu không định nghĩa khóa, cơ chế “chạy một lần” có thể chặn cả công việc hợp lệ trong tương lai hoặc cho phép nhân bản công việc cũ.

Các ví dụ về khóa:

~~~text
seed:catalog:v3
tenant:acme:onboarding:v1
billing:tenant-42:2026-11
report:customer-123:month-2026-10
~~~

**Không dùng thời điểm khởi động, hostname hay Pod UID làm khóa cho việc chỉ được thực hiện một lần toàn hệ thống**, vì các giá trị đó thay đổi qua restart/scale-out. Chúng chỉ phù hợp khi chủ đích là theo từng instance.

## 5. Vì sao biến static, AtomicBoolean và kiểm tra “đã tồn tại chưa” đều không đủ?

### 5.1. Biến bộ nhớ chỉ bảo vệ phạm vi JVM

~~~java
private static final AtomicBoolean initialized = new AtomicBoolean();

public void run(ApplicationArguments args) {
    if (initialized.compareAndSet(false, true)) {
        // Chi mot thread trong JVM nay thang cuoc.
    }
}
~~~

Đây là **đoạn minh họa trong lớp Java**; cần import AtomicBoolean và ApplicationArguments. Nó có thể ngăn một thao tác bị thực hiện lại bởi các thread sử dụng cùng một biến trong **một JVM**, nhưng:

- Mỗi replica có biến static riêng; replica nào cũng có thể thấy false.
- Restart JVM làm biến trở về trạng thái ban đầu.
- Nếu đánh dấu true trước rồi công việc thất bại, lần gọi kế tiếp trong JVM có thể không thử lại.
- Nó không bảo đảm chính xác một hiệu ứng trong database hoặc dịch vụ bên ngoài.

### 5.2. Kiểm tra rồi ghi tạo race condition

Mã có vấn đề:

~~~text
if (database.doesNotContain("seed:v3")) {
    database.insert("seed:v3");
    performBusinessEffect();
}
~~~

Đây là **pseudocode**, không phải Java runnable. Xét hai replica A/B:

~~~text
Thời điểm | Replica A                     | Replica B
----------+-------------------------------+----------------------------
T1        | SELECT: chưa có seed:v3       |
T2        |                               | SELECT: chưa có seed:v3
T3        | insert seed:v3                 |
T4        |                               | insert seed:v3
T5        | thực hiện hiệu ứng            | thực hiện hiệu ứng
~~~

Cả hai đều có thể vượt qua kiểm tra ban đầu trước khi bên còn lại ghi. **SELECT rồi INSERT không phải một thao tác nguyên tử**. Dùng transaction thông thường nhưng thiếu unique constraint hoặc cơ chế khóa phù hợp cũng chưa chắc loại được tình huống cạnh tranh.

### 5.3. @Order không phải distributed lock

~~~java
@Order(1)
@Component
class OnceRunner implements ApplicationRunner {
    // ...
}
~~~

**@Order** sắp thứ tự runner trong context hiện tại. Nếu có năm replica, cả năm vẫn có runner order 1 và có thể chạy đồng thời. Thứ tự trong mỗi JVM không trở thành thứ tự trên toàn cluster.

## 6. Bốn mức bảo đảm thường bị nhầm

| Mục tiêu | Ý nghĩa | Rủi ro còn lại |
| --- | --- | --- |
| At most once attempt | Không cố chạy lặp lại cùng công việc | Nếu crash sau khi đánh dấu “đã nhận” nhưng trước hiệu ứng, công việc có thể bị bỏ sót |
| At least once attempt | Thử lại cho đến khi có kết quả chấp nhận được | Có thể chạy lặp, cần idempotency |
| Một hiệu ứng DB duy nhất theo khóa | Kho dữ liệu từ chối hoặc biến lần ghi trùng thành no-op | Chỉ áp dụng trong transaction/DB được bảo vệ; không tự bao gồm email, HTTP, queue |
| Exactly once end-to-end | Mọi tác dụng phụ quan sát được bên ngoài chỉ xảy ra một lần | Rất khó nếu nhiều hệ thống không chia sẻ transaction; cần hợp đồng/idempotency/coordination theo từng đích |

**Điểm quan trọng:** Khóa duy nhất và transaction có thể làm cho một **thay đổi trong cùng database** xảy ra tối đa một lần theo khóa. Điều đó **không chứng minh phương thức run(...) chỉ được gọi một lần** và cũng không chứng minh email/API bên ngoài chỉ được xử lý một lần.

Ví dụ tình huống không thể suy luận bằng log:

~~~text
Worker gửi API thành công
       |
       +-- Process crash trước khi lưu "DONE"
       |
Restart -> không biết API đã thành công hay chưa -> retry
~~~

Nếu không có idempotency key được hệ thống đích hỗ trợ, lần retry có thể tạo hiệu ứng trùng. Để bảo đảm gần với exactly-once ở mức nghiệp vụ, cần xác định rõ bên nào sở hữu trạng thái, khóa idempotency, cách xác minh kết quả và chính sách phục hồi khi phản hồi bị mất.

## 7. Kiến trúc khuyến nghị: runner cục bộ + điều kiện duy nhất dùng chung

Một cách tổ chức hiệu quả:

~~~text
             +-------------------+
Pod A ------>|                   |
Pod B ------>| Shared database   |-- Unique work_key
Pod C ------>|                   |-- Transaction
             +-------------------+
    |                   |
    |                   v
    +-- Local init      Accepted effect for work_key
        (từng Pod)      (một kết quả nghiệp vụ)
~~~

Đối với **những thay đổi nằm hoàn toàn trong cùng một database**:

1. Tạo khóa nghiệp vụ bền vững, ví dụ **seed:catalog:v3**.
2. Dùng **UNIQUE constraint / PRIMARY KEY** trên khóa.
3. Thực hiện **claim và hiệu ứng DB trong cùng một transaction**, nếu cần cả hai bước. Nếu effect fail thì transaction phải rollback luôn claim.
4. Khi một lần chạy khác gặp duplicate key, kiểm tra kết quả đã hoàn chỉnh; nếu đúng thì bỏ qua idempotently, nếu bất nhất thì báo lỗi.
5. Khi tăng version hoặc thay đổi phạm vi công việc, dùng một khóa mới có kiểm soát.
6. Dùng database **thực sự dùng chung** giữa các replica (PostgreSQL, MySQL hoặc hệ thống có giao dịch và unique constraint phù hợp). Tránh file riêng trong từng container.

**Lưu ý về database isolation:** Không chỉ phụ thuộc vào câu “đã SELECT thấy chưa”. Ràng buộc UNIQUE là chốt kiểm soát tính duy nhất tại nơi dữ liệu được ghi. Transaction bảo đảm các bước ghi vào **cùng database** commit hoặc rollback cùng nhau; cần xác nhận kiểu lỗi duplicate và chính sách retry của database cụ thể.

## 8. Ví dụ chạy được: Spring Boot 3.x/Java 17+ với H2 lưu trên đĩa

Ví dụ minh họa cả hai hành vi:

- **LocalInitRunner** luôn chạy trên mỗi lần SpringApplication khởi động, in thông báo khởi tạo cục bộ.
- **GlobalOnceRunner** cũng luôn được gọi, nhưng nhờ **unique key + transaction**, tác dụng phụ ghi vào database chỉ được áp dụng lần đầu cho cùng khóa.

Ví dụ dùng **H2 file database** để chạy tuần tự nhiều lần trên một máy và quan sát dữ liệu tồn tại qua restart. **H2 file không phải giải pháp điều phối cluster thực tế**; trên production nhiều Pod/máy cần thay bằng database chung có khả năng đồng thời, backup và HA phù hợp.

### 8.1. Cấu trúc project

~~~text
runner-scope-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          RunnerScopeDemo.java
      resources/
        application.properties
        schema.sql
~~~

Tệp **settings.gradle**:

~~~groovy
rootProject.name = 'runner-scope-demo'
~~~

Tệp **build.gradle**:

~~~groovy
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
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
~~~

Spring Boot 3.3.x và JDK 17+ là phạm vi được dùng cho ví dụ. Project cần Gradle tương thích, kết nối repository hoặc dependency đã có trong cache.

### 8.2. Cấu hình kết nối H2 trên đĩa

Tệp **src/main/resources/application.properties**:

~~~properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false

spring.datasource.url=jdbc:h2:file:./once-demo-db
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

**jdbc:h2:file:./once-demo-db** lưu database tương ứng trong working directory của ứng dụng, nên kết quả vẫn tồn tại sau khi JVM kết thúc. **Không dùng jdbc:h2:mem:** cho bài thử restart, vì database in-memory thông thường biến mất khi process đóng.

Trong ví dụ này, chạy từng lần **tuần tự**, với cùng working directory. H2 file database ở chế độ embedded mặc định không phải nơi cho nhiều Pod độc lập cùng truy cập; nếu thử nhiều JVM đồng thời, phải cân nhắc client/server hoặc mixed mode của H2, và giới hạn phù hợp. Phần công việc toàn hệ thống trong production cần một shared data store thực sự.

Tệp **src/main/resources/schema.sql**:

~~~sql
CREATE TABLE IF NOT EXISTS run_claim (
    work_key VARCHAR(120) PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS setup_effect (
    work_key VARCHAR(120) PRIMARY KEY,
    detail VARCHAR(200) NOT NULL
);
~~~

Spring Boot chạy SQL initialization khi khởi động với **spring.sql.init.mode=always**. **IF NOT EXISTS** giúp lần chạy sau không xóa dữ liệu. Đối với database thật, cần dùng công cụ migration có lịch sử và khóa như Flyway/Liquibase thay vì tự quản trị schema lâu dài bằng startup script.

### 8.3. Mã Java hoàn chỉnh

Tệp **src/main/java/demo/RunnerScopeDemo.java**:

~~~java
package demo;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@SpringBootApplication
public class RunnerScopeDemo {
    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(RunnerScopeDemo.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("MAIN_RETURNED");
        }
    }
}

@Component
@Order(10)
class LocalInitRunner implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        // Vi du cho init cua tung lan startup / tung instance.
        System.out.println("LOCAL_INITIALIZED");
    }
}

@Service
class OnceWorkService {
    static final String WORK_KEY = "seed:catalog:v1";

    private final JdbcTemplate jdbc;

    OnceWorkService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void applyOnce() {
        // Claim va business effect nam trong cung DB transaction.
        jdbc.update(
                "INSERT INTO run_claim (work_key) VALUES (?)",
                WORK_KEY);

        jdbc.update(
                "INSERT INTO setup_effect (work_key, detail) VALUES (?, ?)",
                WORK_KEY, "initialized catalog v1");
    }

    public boolean isComplete() {
        Integer claims = jdbc.queryForObject(
                "SELECT COUNT(*) FROM run_claim WHERE work_key = ?",
                Integer.class, WORK_KEY);

        Integer effects = jdbc.queryForObject(
                "SELECT COUNT(*) FROM setup_effect WHERE work_key = ?",
                Integer.class, WORK_KEY);

        return claims != null && claims == 1
                && effects != null && effects == 1;
    }
}

@Component
@Order(20)
class GlobalOnceRunner implements ApplicationRunner {
    private final OnceWorkService onceWorkService;

    GlobalOnceRunner(OnceWorkService onceWorkService) {
        this.onceWorkService = onceWorkService;
    }

    @Override
    public void run(ApplicationArguments args) {
        try {
            onceWorkService.applyOnce();
            System.out.println("GLOBAL_EFFECT_APPLIED");
        } catch (DuplicateKeyException duplicate) {
            // Chi bo qua neu qua trinh truoc da hoan tat dung.
            if (!onceWorkService.isComplete()) {
                throw duplicate;
            }
            System.out.println("GLOBAL_ALREADY_COMPLETED");
        }
    }
}

@Component
class ReadyObserver {
    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        System.out.println("APPLICATION_READY");
    }
}
~~~

Giải thích từng phần:

1. **LocalInitRunner** in **LOCAL_INITIALIZED** ở **mọi lần startup** đi đến runner. Đây là hành vi đúng cho khởi tạo cục bộ từng instance.
2. **GlobalOnceRunner** cũng được gọi ở mọi lần startup; nó **không phải** runner đặc biệt chạy một lần toàn cluster.
3. **OnceWorkService.applyOnce()** là method **@Transactional** nằm trên Spring service riêng. Runner gọi method qua bean được inject, cho phép transaction proxy Spring áp dụng. Không gọi **this.applyOnce()** từ chính service rồi kỳ vọng tự động có transaction.
4. Câu INSERT vào **run_claim** yêu cầu khóa WORK_KEY chưa tồn tại; PRIMARY KEY ngăn hai transaction cùng commit khóa trùng.
5. INSERT vào **setup_effect** là **tác dụng phụ nghiệp vụ giả lập trong cùng DB**. Nếu bước này thất bại, RuntimeException làm transaction rollback theo cấu hình giao dịch mặc định, vì vậy claim không được commit riêng.
6. Khi key đã tồn tại, JDBC ném **DuplicateKeyException**. Runner bắt exception **ngoài method @Transactional**, sau khi transaction thất bại đã kết thúc, rồi gọi **isComplete()** để xác minh cả claim lẫn effect.
7. Nếu claim tồn tại nhưng effect không có (dữ liệu bị sửa thủ công hoặc sự cố bất thường), chương trình **không im lặng coi là hoàn thành** mà ném lại lỗi.
8. **@Order(10)** và **@Order(20)** đảm bảo trong cùng context, LocalInitRunner chạy trước GlobalOnceRunner. **@Order không đồng bộ các instance khác nhau**.
9. **ApplicationReadyEvent** xuất hiện sau khi runner hoàn tất theo nhánh thành công. Main đóng context sau khi SpringApplication.run(...) trả về, vì demo là một job một lần chứ không phải web service lâu dài.

### 8.4. Chạy hai lần và quan sát

Nếu project có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Nếu chưa có wrapper, dùng một Gradle tương thích đã cài:

~~~bash
gradle bootRun
~~~

**Lần đầu** với database mới, các dòng do chính chương trình in ra theo thứ tự:

~~~text
LOCAL_INITIALIZED
GLOBAL_EFFECT_APPLIED
APPLICATION_READY
MAIN_RETURNED
~~~

**Lần thứ hai**, chạy lại dự án với cùng working directory và giữ nguyên tệp H2, các dòng do chương trình in là:

~~~text
LOCAL_INITIALIZED
GLOBAL_ALREADY_COMPLETED
APPLICATION_READY
MAIN_RETURNED
~~~

Spring Boot, HikariCP và Gradle có thể in các dòng log bổ sung; ở đây chỉ liệt kê các dòng do ví dụ in. Database H2 được lưu trên đĩa. Nếu thay đổi working directory hoặc xóa các tệp DB, bạn đã tạo một kho dữ liệu mới, nên lần sau lại được xem là lần đầu.

**Kết luận của thí nghiệm:** cả hai runner đều chạy trong mỗi startup. Chỉ **tác dụng phụ ghi DB có khóa** được bảo vệ khỏi tạo trùng khi chạy lại.

### 8.5. Kịch bản lỗi và kiểm tra transaction

Nếu thay câu INSERT thứ hai trong **applyOnce()** bằng một câu SQL gây RuntimeException, trong transaction đúng, thao tác insert claim trước đó sẽ rollback. Lần startup sau có thể thử lại vì claim không bị đánh dấu hoàn thành sai. Đây là nguyên tắc **atomic claim + effect**.

Không dùng thí nghiệm này làm bằng chứng “exactly once cho Kafka/email/HTTP”. Nó chỉ tạo hai bản ghi trong **cùng một H2 database transaction**. Trong sản phẩm thực tế, sử dụng PostgreSQL/MySQL dùng chung và kiểm tra hành vi cạnh tranh, deadlock, isolation, timeout, unique constraint cùng transaction manager thực sự.

## 9. Khi có nhiều replica khởi động đồng thời

Giả sử các Pod A, B, C cùng khởi động và mỗi Pod đều có GlobalOnceRunner. Điều đúng cần xảy ra:

~~~text
Pod A ---> INSERT work_key=seed:catalog:v1 ---+
Pod B ---> INSERT work_key=seed:catalog:v1 ---+--> Shared DB PRIMARY KEY
Pod C ---> INSERT work_key=seed:catalog:v1 ---+
                                               |
                                      Mot transaction commit
                                      Hai ben khac thay duplicate
                                               |
                                      Chi mot ket qua DB hop le
~~~

Đây là cách nhìn đơn giản hóa. Cạnh tranh thực có thể khiến một transaction phải **chờ lock**, gặp **unique violation**, timeout hoặc lỗi giao dịch khác, tùy database và isolation. Cần chính sách retry cho lỗi **có thể retry** (ví dụ deadlock/serialization) chứ không gom tất cả lỗi SQL vào nhánh “đã hoàn thành”.

Với PostgreSQL, có thể sử dụng cú pháp:

~~~sql
INSERT INTO run_claim(work_key)
VALUES ('seed:catalog:v1')
ON CONFLICT (work_key) DO NOTHING
RETURNING work_key;
~~~

**Chỉ tiến trình nhận được hàng RETURNING mới thực hiện các câu SQL nghiệp vụ tiếp theo**, và các câu này phải nằm trong **cùng transaction** với claim nếu muốn bảo đảm commit/rollback cùng nhau. Nếu không nhận hàng RETURNING, cần xác minh trạng thái đã hoàn tất. Câu SQL trên là **đoạn minh họa PostgreSQL**, không phải lệnh portable cho mọi database.

Không nhất thiết phải có bảng claim tách riêng nếu **bản ghi hiệu ứng nghiệp vụ** đã có PRIMARY KEY/UNIQUE theo đúng khóa; khi đó insert/upsert idempotent trực tiếp có thể đơn giản hơn. Chọn thiết kế ít trạng thái nhất nhưng đủ bảo đảm cho hợp đồng.

## 10. Lựa chọn công cụ theo loại công việc toàn hệ thống

### 10.1. Migration database: Flyway hoặc Liquibase

Với việc thay đổi schema và seed có version, nên dùng **Flyway** hoặc **Liquibase**. Chúng theo dõi lịch sử migration và sử dụng cơ chế phối hợp/khóa phù hợp để tránh cùng áp dụng một migration trong database dùng chung. Khi nhiều instance khởi động, chúng có thể **cùng kiểm tra trạng thái migration**, nhưng một version đã áp dụng thành công sẽ không bị chạy lại như một migration mới.

Lưu ý:

- Migration chỉ bao phủ **database và phạm vi version do công cụ quản lý**.
- Cần phân tích cách xử lý migration thất bại hoặc không có transaction cho một số DDL tùy database.
- Không tự kết luận “mỗi ứng dụng chỉ chạy migration một lần”; từng instance có thể chạy logic kiểm tra migration.
- Đừng đặt logic thay đổi schema phức tạp trực tiếp trong ApplicationRunner nếu một công cụ migration chuẩn giải quyết đúng yêu cầu.

### 10.2. Job riêng do hạ tầng điều phối

Nếu công việc là import dữ liệu lớn, tạo chỉ mục hoặc xử lý một chiến dịch theo kỳ, có thể tách thành **Job** thay vì chạy nó trên mọi replica của web service. Trong Kubernetes, một **Job** được cấu hình số completions/parallelism/backoff theo nhu cầu; trong CI/CD có thể có một bước migration hoặc provisioning riêng.

Nhưng **Kubernetes Job không tự tạo exactly-once cho tất cả tác dụng phụ**: Pod có thể bị thay thế, task có thể chạy lại do lỗi hoặc retry. Logic job vẫn nên idempotent hoặc có khóa nghiệp vụ, nhất là khi làm việc với dịch vụ bên ngoài.

Điểm mạnh của Job riêng là tách **lifecycle công việc dùng chung** khỏi **lifecycle startup từng Pod**. Web service có thể chỉ đọc dữ liệu đã chuẩn bị thay vì tự chạy một bản sao công việc lớn mỗi lần scale-out.

### 10.3. Distributed lock, leader election và lease

Nếu chỉ một instance được phép **thực thi đồng thời** một đoạn code, có thể dùng lock trong database, Redis hoặc hệ thống điều phối có hỗ trợ leader election.

Tuy nhiên, **“một instance tại một thời điểm” khác với “chỉ một tác dụng phụ từng tồn tại”**:

- Nếu leader crash, lease hết hạn, instance khác có thể nhận lại quyền.
- Leader cũ có thể tạm mất kết nối rồi tiếp tục thực hiện side effect sau khi lease bị thay thế.
- Để ngăn stale owner, các hệ thống nhạy cảm cần **fencing token** hoặc compare-and-set/transaction tại nơi ghi hiệu ứng.
- Nếu ghi trạng thái DONE trước side effect, crash giữa hai bước có thể làm mất công việc.
- Nếu side effect xảy ra trước DONE, crash giữa hai bước có thể làm lặp side effect khi retry.

Lock chỉ giải quyết một phần vấn đề điều phối; vẫn cần **idempotency** hoặc **atomic commit** tại điểm tạo tác dụng phụ.

### 10.4. Spring Batch và trạng thái JobRepository

Đối với tác vụ batch có nhiều bước, checkpoint, restart và xử lý chunk, **Spring Batch** cung cấp JobRepository, JobParameters, JobInstance và JobExecution để theo dõi và điều phối vòng đời job. Chọn JobParameters đúng là quan trọng vì chúng ảnh hưởng identity của một JobInstance.

Spring Batch không làm việc tự động “exactly once với mọi remote service”. Job restart/retry và các tác dụng phụ bên ngoài vẫn cần idempotency, transaction boundary và recovery phù hợp.

### 10.5. Queue và transactional outbox

Với việc gửi email, thanh toán, tích hợp REST hoặc message broker, hãy xem xét mô hình **outbox**:

1. Trong transaction DB của nghiệp vụ, lưu **bản ghi kết quả + outbox event** có khóa duy nhất.
2. Một worker độc lập lấy outbox event và gửi tới hệ thống đích.
3. Worker có thể retry; hệ thống đích hoặc consumer cần **idempotency key/deduplication**.
4. Ghi nhận delivered/processed theo hợp đồng; theo dõi sự kiện lỗi và dead-letter.
5. Nếu bên ngoài đã xử lý nhưng phản hồi mất, retry cùng idempotency key giúp tránh tạo hiệu ứng trùng **nếu bên đích hỗ trợ**.

Mô hình này thường tốt hơn việc runner trực tiếp gửi email một lần rồi đánh dấu DONE ở database, vì DB và SMTP/API khác nhau không chia sẻ một transaction nguyên tử thông thường.

## 11. “Một lần trước ready” có khác “một lần toàn hệ thống” không?

**Có.** Runner chạy trước ApplicationReadyEvent theo luồng khởi động Spring Boot. Điều đó tạo một **readiness barrier trong từng instance**: nếu runner cần hoàn tất, instance chưa vào nhánh ready thành công.

Nhưng khi có nhiều replica:

~~~text
Replica A: Started -> Runner A -> Ready A
Replica B: Started -> Runner B -> Ready B
Replica C: Started -> Runner C -> Ready C
~~~

Mỗi replica có readiness riêng. Nếu Runner A phải giành khóa global còn Runner B/C phải chờ hoặc kiểm tra trạng thái, cần quyết định:

- **Có bắt buộc công việc global hoàn tất trước khi mọi instance ready?** Nếu có, các replica phải kiểm tra trạng thái hoàn thành an toàn và có timeout/fail-fast; chỉ một instance thực hiện phần effect.
- **Có thể phục vụ một phần chức năng trước khi job global hoàn tất?** Có thể tách job và dùng feature readiness/health hoặc cơ chế degrade được thiết kế, tránh block toàn bộ startup vô thời hạn.
- **Có tốt hơn khi tách global job khỏi web deployment?** Thường có, đặc biệt với migration dài, import lớn, email chiến dịch hoặc tác vụ có retry phức tạp.

Đừng dùng **Thread.sleep()** hoặc polling vô hạn trong runner để “chờ replica khác”. Cần deadline, backoff, metric và trạng thái công việc rõ ràng. Nếu việc toàn hệ thống mất lâu, mô hình job riêng sẽ dễ vận hành hơn.

## 12. Vì sao chỉ bắt DuplicateKeyException vẫn chưa đủ?

Trong ví dụ H2, khi gặp duplicate key, **isComplete()** xác minh cả claim và effect. Đây là một thói quen quan trọng:

- Nếu hệ thống từng commit **claim** nhưng chưa tạo **effect** do triển khai sai hoặc thao tác thủ công, duplicate không chứng minh công việc đã thành công.
- Nếu có nhiều loại công việc, phải xác minh **đúng work_key và đúng version/payload**.
- Nếu DB trả về lỗi timeout hoặc network, **không được coi lỗi đó là “already completed”**. Client có thể không biết transaction đã commit hay chưa; cần truy vấn kiểm tra trạng thái từ nguồn đáng tin cậy.
- Nếu thực thi side effect bên ngoài transaction, phải lưu trạng thái phù hợp như **PENDING**, **IN_PROGRESS**, **DONE**, **FAILED** và thiết kế recovery/lease rõ ràng. Nhưng đừng đơn giản ghi DONE trước rồi hy vọng side effect sẽ thành công.

Trong hệ thống cạnh tranh thật, bản ghi claim và effect trong một transaction dùng chung bảo đảm rằng những người đọc sau commit thấy trạng thái phù hợp. Việc đối chiếu **isComplete()** sau duplicate không thay thế thiết kế transaction/constraint, nhưng giúp phát hiện dữ liệu không nhất quán thay vì im lặng.

## 13. Kiểm thử đúng phạm vi

### Bài thử 1 — Restart một instance

Chạy ví dụ H2 hai lần cùng working directory. Kỳ vọng:

- Cả hai lần đều có **LOCAL_INITIALIZED**.
- Chỉ lần đầu có **GLOBAL_EFFECT_APPLIED**.
- Lần hai có **GLOBAL_ALREADY_COMPLETED**.
- Database chỉ có một hàng cùng work_key ở mỗi bảng.

Đây là kiểm thử **lưu trạng thái qua restart** trên một máy, không phải kiểm thử cluster thực.

### Bài thử 2 — Thất bại giữa hai câu SQL

Trong môi trường test, gây RuntimeException sau khi insert claim nhưng trước khi commit effect. Kiểm tra transaction rollback cả claim. Sau đó chạy lại với code đúng; công việc vẫn có thể được thực hiện.

Không tạo lỗi này trên hệ thống production để “thử may mắn”, và không chỉ dựa vào stdout. Hãy kiểm tra trạng thái dữ liệu thực.

### Bài thử 3 — Nhiều instance cạnh tranh

Chạy nhiều instance cùng kết nối tới **cùng PostgreSQL/MySQL test database** với khóa giống nhau. Kiểm tra:

- Chỉ một kết quả DB duy nhất được commit theo work_key.
- Những instance còn lại không tạo hiệu ứng trùng.
- Lỗi duplicate được xử lý đúng như “đã hoàn tất” chỉ khi trạng thái thực sự đầy đủ.
- Deadlock/timeout/serialization error có chính sách retry riêng, không bị che.
- Không instance nào công bố ready khi dữ liệu bắt buộc vẫn thiếu.

### Bài thử 4 — Crash sau commit, trước khi log thành công

Giả lập tiến trình bị dừng ngay sau khi transaction commit nhưng trước khi runner log **GLOBAL_EFFECT_APPLIED**. Khi khởi động lại, database phải là nguồn sự thật: một khóa đã commit thì không ghi trùng, dù log lần trước không nói đã hoàn tất.

### Bài thử 5 — Tác dụng phụ ngoài DB

Giả lập API bên ngoài nhận request nhưng client timeout trước khi nhận response. Kiểm tra retry với idempotency key; nếu bên đích không hỗ trợ, phải có quy trình đối soát hoặc compensation phù hợp. Đừng khẳng định “exactly once” chỉ vì service đã có distributed lock.

### Bài thử 6 — Rollout và scale-out

Trong staging, triển khai hai hoặc nhiều replica, thực hiện rolling update, kill Pod giữa startup, scale lên rồi xuống. Kiểm tra state bền vững, uniqueness, thời gian readiness, khả năng retry, metrics lỗi và việc không có deadlock.

## 14. Ma trận lựa chọn thực tế

| Công việc | Mục tiêu đúng | Cách triển khai nên xét |
| --- | --- | --- |
| Nạp cache RAM cục bộ | Mỗi instance/mỗi startup | ApplicationRunner hoặc init service, lặp lại an toàn |
| Validate config của bean | Mỗi lần bean được tạo | Constructor/@PostConstruct/initMethod |
| Thiết lập connection pool | Mỗi ApplicationContext | Quản lý lifecycle của bean/DataSource |
| Warm up bắt buộc trước traffic | Mỗi instance/mỗi startup | Runner có timeout, readiness barrier |
| Migration schema version vN | Một lần theo version và database | Flyway/Liquibase + migration history/locking |
| Tạo dữ liệu seed vN | Một lần theo version/tenant | Unique key + DB transaction, hoặc migration có idempotency |
| Gửi email chào mừng cho tenant | Một hiệu ứng logic theo tenant/event key | Outbox, idempotency tại bên gửi/đích, retry/đối soát |
| Chốt kỳ thanh toán | Mỗi tenant + kỳ | Unique constraint theo kỳ, transaction, job orchestrator |
| Tạo báo cáo tháng lớn | Một job theo tháng, có restart | Batch/job riêng, checkpoint + deduplication |
| Listener xử lý queue lâu dài | Mỗi replica hoặc consumer-group partition | Consumer container/SmartLifecycle, không dùng runner làm toàn bộ vòng đời |
| Khởi tạo index tìm kiếm chung | Một job theo version/alias | Job/leader/lock, checkpoint và idempotent index writes |
| Một nhiệm vụ chỉ một leader xử lý tại thời điểm | Mutual exclusion tạm thời | Distributed lock/lease + fencing, vẫn cần idempotency |

## 15. Các lỗi thiết kế thường gặp

**Lỗi 1 — Gọi runner là “chạy đúng một lần” mà không nói phạm vi.** Khi autoscale, restart hoặc rolling update, runner chạy trên instance mới. Hãy dùng thuật ngữ **mỗi lần startup**.

**Lỗi 2 — Dùng static boolean để khóa cả cluster.** Biến static chỉ chia sẻ trong một JVM/classloader, không qua Pod khác và mất khi restart.

**Lỗi 3 — Dùng @Order để đồng bộ Pod.** @Order chỉ sắp runner trong context; không cung cấp distributed mutual exclusion.

**Lỗi 4 — SELECT trước rồi INSERT mà không có unique constraint.** Hai replica có thể cùng thấy “chưa tồn tại” và cùng ghi.

**Lỗi 5 — Ghi DONE trước rồi gọi API.** Crash giữa hai bước làm công việc có thể bị bỏ sót mãi mãi.

**Lỗi 6 — Gọi API trước rồi ghi DONE.** Crash sau API trước DONE có thể gây tác dụng phụ trùng ở lần retry.

**Lỗi 7 — Coi distributed lock là exactly once.** Lease hết hạn, failover, stale holder và crash vẫn có thể tạo retry/duplicate; cần fencing hoặc idempotent effect.

**Lỗi 8 — Bắt mọi SQLException và in “đã chạy rồi”.** Lỗi mạng, database full, transaction timeout hoặc schema hỏng không phải duplicate key. Phân loại và báo lỗi trung thực.

**Lỗi 9 — Swallow exception của runner bắt buộc.** SpringApplication có thể tiếp tục phát ApplicationReadyEvent dù dữ liệu chuẩn bị chưa đầy đủ.

**Lỗi 10 — Cài một database H2 file riêng trong mỗi container rồi gọi đó là global uniqueness.** Các Pod nhìn dữ liệu riêng nên mỗi Pod đều có thể tạo kết quả “duy nhất” ở chính nó.

**Lỗi 11 — Đặt toàn bộ schema migration vào runner của web service.** Dễ va chạm khi nhiều phiên bản chạy chồng nhau, khó rollback và khó kiểm soát lịch sử; ưu tiên migration tooling.

**Lỗi 12 — Chọn idempotency key bằng timestamp của request.** Mỗi retry có timestamp mới, làm mất tác dụng dedup. Key phải gắn với cùng một intent nghiệp vụ.

**Lỗi 13 — Chờ khóa trong startup vô thời hạn.** Có thể giữ mọi instance ở trạng thái chưa ready, dẫn tới rollout timeout và hiệu ứng domino; phải có deadline và kế hoạch vận hành.

**Lỗi 14 — Không kiểm tra transaction được áp dụng qua proxy.** Self-invocation của method @Transactional có thể bỏ qua AOP proxy; claim và effect vô tình commit tách rời.

**Lỗi 15 — Tin rằng Job/Kubernetes/Scheduler cam kết exactly once.** Các cơ chế này có retry, replacement và failover; nghiệp vụ vẫn cần chống trùng hoặc đối soát.

**Lỗi 16 — Nhầm “một hiệu ứng DB duy nhất” với “method thực thi duy nhất”.** Method có thể được gọi nhiều lần; điều quan trọng là ranh giới side effect tại nguồn sự thật.

## 16. Checklist trước khi triển khai

Trước khi đặt công việc vào runner, cần trả lời rõ:

1. Đây là **khởi tạo state của từng instance** hay **một kết quả nghiệp vụ dùng chung**?
2. “Một lần” có nghĩa **một lần vĩnh viễn, theo version, theo tenant hay theo kỳ**?
3. Có bao nhiêu replica/JVM/pod có thể cùng khởi động hoặc restart?
4. Kho nào là **nguồn sự thật bền vững** cho trạng thái hoàn thành? Nó có thực sự được chia sẻ không?
5. Có **UNIQUE constraint** hoặc atomic compare-and-set tại nơi ghi effect không?
6. Claim và effect có nằm trong **cùng transaction** được không?
7. Nếu effect liên quan nhiều hệ thống, có **idempotency key, outbox, retry và reconciliation** không?
8. Nếu leader/lock bị mất giữa chừng, stale process có còn được phép ghi không? Có cần fencing token?
9. Một instance có được ready trước khi global work xong không? Có timeout/fail-fast và readiness phù hợp không?
10. Khi rollout phiên bản mới, khóa công việc có thay đổi theo version đúng hợp đồng không?
11. Có thử restart, concurrent startup, crash after commit, timeout và schema conflict chưa?
12. Có metric để biết **đã thử**, **đã áp dụng**, **đã bỏ qua**, **đang chờ**, **thất bại** và **retry** theo key chưa?

## 17. Tự kiểm tra

**Câu 1.** Hai Pod có cùng ApplicationRunner khởi động đồng thời. Runner được gọi mấy lần?  
**Đáp án:** Thông thường mỗi Pod gọi runner một lần trong startup của nó, tức hai lần gọi độc lập.

**Câu 2.** Sau restart một Pod, @Order(1) của runner có giúp bỏ qua công việc đã chạy trước đó không?  
**Đáp án:** Không. @Order chỉ quy định thứ tự giữa các runner trong một context, không lưu trạng thái qua restart.

**Câu 3.** Nạp cache ở RAM cho từng replica nên chạy một lần toàn cluster hay mỗi replica?  
**Đáp án:** Mỗi replica cần có cache riêng, nên khởi tạo theo từng instance/startup.

**Câu 4.** Muốn seed danh mục v3 trong database dùng chung và không insert trùng khi có 10 Pod, cần gì?  
**Đáp án:** Work key theo version, unique constraint, transaction/idempotency; dùng migration tooling nếu thích hợp.

**Câu 5.** Hai replica đều SELECT thấy chưa có hàng; vì sao cả hai có thể ghi trùng?  
**Đáp án:** Đây là race condition check-then-act. Cần enforce uniqueness hoặc atomic coordination tại kho chung.

**Câu 6.** Claim đã commit rồi tiến trình crash trước khi gọi API; công việc có chắc thành công?  
**Đáp án:** Không. Mark-before-effect có thể làm mất task; cần state machine/retry và bảo đảm ở nguồn hiệu ứng.

**Câu 7.** Bên ngoài đã gửi email thành công nhưng client timeout trước khi lưu DONE; lần sau có thể gửi trùng không?  
**Đáp án:** Có. Nên dùng idempotency key tại bên gửi/đích, outbox và chính sách đối soát.

**Câu 8.** Unique constraint của PostgreSQL có làm ApplicationRunner chỉ được gọi một lần trên toàn cluster không?  
**Đáp án:** Không. Runner vẫn được gọi trên từng replica; DB từ chối các lần ghi trùng theo key.

**Câu 9.** Vì sao demo dùng @Transactional trên một service riêng thay vì gọi method trong cùng runner?  
**Đáp án:** Để lời gọi đi qua bean proxy của Spring và transaction thực sự bao phủ cả claim lẫn effect.

**Câu 10.** Kubernetes Job chạy một lần có bảo đảm mọi external API call đúng một lần không?  
**Đáp án:** Không. Job có thể retry hoặc Pod bị thay thế; cần idempotency và xác minh tác dụng phụ.

**Câu 11.** Sử dụng file H2 riêng cho mỗi container có thể kiểm soát một lần toàn cluster không?  
**Đáp án:** Không. Trạng thái không được chia sẻ. Demo file H2 chỉ chứng minh hành vi qua restart trên cùng một working directory.

**Câu 12.** Có cần giữ mọi web replica ở trạng thái chưa ready cho đến khi một job global mất 20 phút hoàn thành không?  
**Đáp án:** Phụ thuộc hợp đồng. Thường nên tách job có lifecycle, health và retry riêng; nếu thực sự bắt buộc thì cần barrier, timeout và chính sách vận hành rõ ràng.

**Ghi nhớ cuối cùng:** **Runner chạy trong từng lần khởi động của SpringApplication, không có quyền năng “chạy một lần toàn hệ thống”.** Dùng runner cho khởi tạo cục bộ và công việc startup của từng instance. Đối với một kết quả nghiệp vụ dùng chung, hãy định nghĩa **khóa công việc**, áp dụng **unique constraint/transaction** tại nguồn dữ liệu, hoặc dùng **migration/job/lock/outbox** đúng yêu cầu. Phân biệt “đoạn code được gọi bao nhiêu lần” với “tác dụng phụ được ghi nhận bao nhiêu lần”, vì độ tin cậy của hệ thống nằm ở ranh giới tác dụng phụ.

### Tài liệu tham khảo

- [Spring Boot — Using ApplicationRunner or CommandLineRunner](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Spring Boot 3.3 — ApplicationRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html)
- [Spring Framework — Transaction rollback semantics](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [H2 Database — Connection modes and persistent databases](https://h2database.com/html/features.html)
- [Spring Batch — JobRepository and job instances](https://docs.spring.io/spring-batch/reference/job.html)
- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/reference/howto/data-initialization.html)

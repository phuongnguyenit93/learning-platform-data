# Tách logic nghiệp vụ khỏi @Scheduled để kiểm thử độc lập

Một method vừa có **@Scheduled**, vừa tự đọc thời gian hệ thống, query database, quyết định ai quá hạn, gửi email và tự bắt mọi exception thường tạo ra bộ test khó kiểm soát: phải chờ lịch chạy thật, phụ thuộc đồng hồ máy CI, phụ thuộc dữ liệu đã có trong DB, khó test lỗi và dễ chạy trùng khi nhiều instance ứng dụng cùng hoạt động. Cách thiết kế bền vững là **coi @Scheduled chỉ là một inbound adapter/trigger**, còn nghiệp vụ là một **use case có thể gọi trực tiếp** bằng Java, nhận **Clock** và các **port/interface** cho phụ thuộc ngoài.

Bài thuộc nhóm **Bất đồng bộ và lịch chạy** của **Spring Boot - testing**. Mục tiêu là **tách logic nghiệp vụ khỏi @Scheduled để kiểm thử độc lập**. Ví dụ dùng **Java 17, Spring Boot 3.4.5, Spring Framework 6.2, JUnit Jupiter và Mockito**, với use case **vô hiệu hóa tài khoản dùng thử đã hết hạn**. Toàn bộ nghiệp vụ được kiểm thử với Clock.fixed và repository in-memory, không chờ cron, không khởi server, không ngủ một giây nào. Một test riêng xác minh @Scheduled adapter chỉ gọi service đúng một lần; một Spring context test xác minh có thể **tắt job trong test** bằng property.

Điều đặc biệt phải nhớ: **test nghiệp vụ đúng không tự chứng minh cron/scheduler wiring đúng**, và **test annotation @Scheduled không tự chứng minh nghiệp vụ đúng**. Đó là hai hợp đồng khác nhau, cần những test khác nhau, có phạm vi rõ.

## 1. @Scheduled thực sự chịu trách nhiệm gì?

Spring Framework đọc **@Scheduled** trên **Spring-managed bean** khi scheduling được kích hoạt (thường bằng **@EnableScheduling**) và đăng ký task với **TaskScheduler**. Đến thời điểm trigger, scheduler gọi method được đánh dấu. Một method @Scheduled thông thường:

- Không nhận method parameters.
- Thường trả **void**; giá trị trả về của scheduled invocation bình thường không được framework dùng.
- Có thể cấu hình cron, fixedDelay hoặc fixedRate; không đặt tùy tiện cả ba trong một annotation.
- Chạy trên scheduler thread; mặc định Spring Boot 3.4 dùng ThreadPoolTaskScheduler một thread khi không bật virtual threads và không có custom TaskScheduler.
- Không bảo đảm chỉ chạy một lần trong cả cluster; **mỗi JVM/application instance có thể đăng ký cùng job**.
- Không tự cung cấp retry business, idempotency, distributed locking, transaction hay exactly-once delivery.
- Không tự giải quyết business timezone hay clock injection; cron trigger timezone khác với thời điểm nghiệp vụ dùng để tính hết hạn.

Một annotation điển hình:

~~~java
@Scheduled(cron = "0 0 * * * *", zone = "UTC")
public void run() {
    // gọi service, không đặt logic nghiệp vụ dài ở đây
}
~~~

**Cron của Spring có sáu trường: giây, phút, giờ, ngày trong tháng, tháng, thứ trong tuần**. Biểu thức **0 0 * * * *** nghĩa là **đầu mỗi giờ** theo timezone được chọn. Nó **không** phải cú pháp cron Unix năm trường thường dùng bởi một số hệ thống khác.

### Sơ đồ phân tầng mong muốn

~~~text
Spring scheduler / cron / fixedDelay
                |
                v
        TrialExpirationJob
       [inbound scheduling adapter]
        - không đọc database
        - không tính thời gian quá hạn
        - gọi service, log kết quả
                |
                v
      TrialExpirationService
         [business use case]
        - lấy Instant.now(clock)
        - tìm account active đã hết hạn
        - áp dụng policy hết hạn
        - gọi repository conditional update
        - trả số lượng thay đổi thật
                |
                v
       TrialAccountRepository
          [outbound port]
                |
                v
      InMemory / JDBC / JPA adapter
~~~

Khi kiểm thử:
- **Service unit test:** gọi trực tiếp **expireDueTrials()**, truyền **Clock.fixed** và fake repository.
- **Job adapter test:** tạo job bằng constructor với service mock, gọi trực tiếp **run()**; assert delegate đúng.
- **Spring wiring test:** khởi context nhưng tắt job qua property, assert không đăng ký job bean ở chế độ test.
- **Scheduler integration test (khi cần):** bật scheduling trong môi trường test riêng, đo trigger và concurrency bằng đồng bộ hóa/tín hiệu, không dùng Thread.sleep tùy ý.

## 2. Anti-pattern: nhồi nghiệp vụ vào @Scheduled

**Mẫu sai, chỉ để phân tích:**

~~~java
@Component
class ExpirationJob {
    private final AccountRepository repository;
    private final EmailSender email;

    @Scheduled(cron = "0 0 * * * *")
    public void expireAndNotify() {
        Instant now = Instant.now();

        for (Account account : repository.findActiveAccounts()) {
            if (account.expiresAt().isBefore(now)) {
                account.disable();
                email.sendExpiredNotice(account.email());
                repository.save(account);
            }
        }
    }
}
~~~

Đây là **trích đoạn phản ví dụ**, không phải file runnable của dự án bên dưới. Những vấn đề cần chỉ ra:

1. **Instant.now() hard-code:** unit test muốn một account đúng hạn hay quá hạn phải dùng thời gian thực hoặc sleep, dễ fail ở ranh giới giây/phút.
2. **Logic phụ thuộc scheduler:** để test quy tắc hạn sử dụng có người cố chờ cron thay vì gọi service.
3. **Quá nhiều trách nhiệm:** scheduler, query, deadline policy, email và persistence cùng một class.
4. **Không có idempotency:** cùng account có thể nhận email hai lần khi nhiều nodes chạy song song.
5. **Rủi ro thứ tự side effects:** gửi email trước khi DB save thất bại có thể gửi trùng khi retry; save trước rồi email thất bại có thể mất thông báo.
6. **Không bounded batch:** findActiveAccounts() có thể quét toàn table.
7. **Không có context về timezone:** cron mặc định có thể theo timezone runtime, trong khi “hết hạn” dựa trên Instant UTC.
8. **Khó chẩn đoán:** khi test fail không biết do scheduler, timestamp, email adapter hay database.

**Sửa kiến trúc:** một method scheduled mỏng chỉ gọi use case. Business service lấy thời gian qua Clock, repository xử lý cập nhật có điều kiện, còn external notification (nếu có) dùng port/outbox và được test riêng.

## 3. @Scheduled adapter là chi tiết hạ tầng, không phải business API

Tên, signature và trách nhiệm:

~~~java
@Component
public class TrialExpirationJob {
    private final TrialExpirationService service;

    public TrialExpirationJob(TrialExpirationService service) {
        this.service = service;
    }

    @Scheduled(cron = "0 0 * * * *", zone = "UTC")
    public void run() {
        service.expireDueTrials();
    }
}
~~~

Đây là **trích đoạn hình thái**, class đầy đủ có điều kiện bật/tắt và logger nằm ở phần 6.7.

**Business service không cần biết annotation @Scheduled**. Nó có thể được gọi từ:
- scheduler ở thời gian định kỳ;
- một admin endpoint cần thao tác chạy lại có kiểm soát;
- CLI maintenance command;
- integration test/job test;
- một message consumer nhận trigger.

Đây là lợi ích kiến trúc: **trigger thay đổi nhưng chính sách nghiệp vụ vẫn kiểm thử độc lập**.

Không gắn **@Scheduled** lên method nghiệp vụ rồi gọi trực tiếp chính method đó để coi như đã test scheduler. Gọi trực tiếp chỉ chứng minh nội dung Java method; annotation được Spring đọc khi đăng ký task trên bean. Tương tự, dùng Mockito.verify(service).expireDueTrials() chỉ chứng minh adapter delegate, **không chứng minh nó đã tự được chạy đúng giờ**.

## 4. Định nghĩa business rule có thể test không cần thời gian thực

Bài mẫu chọn rule rõ:
- Một TrialAccount có **id, expiresAt: Instant, active: boolean**.
- Tại thời điểm **now**, account cần bị vô hiệu hóa nếu **active == true** và **expiresAt <= now**.
- Tài khoản hết hạn **đúng bằng now** cũng cần vô hiệu hóa (ranh giới inclusive).
- Account đã inactive không được tính lại.
- Tài khoản chưa hết hạn không bị thay đổi.
- **Mỗi lần chạy** chỉ xử lý tối đa **batchSize** accounts; những accounts còn lại được xử lý lần sau.
- Một lời gọi update có điều kiện có thể trả **false** vì account đã được instance khác xử lý; service chỉ đếm thay đổi thực.
- Chạy use case hai lần liên tiếp không phải vô hiệu hóa lại cùng một account.

Dùng **Instant** (mốc thời gian tuyệt đối) cho expiration; dùng **Clock** để lấy now. **Timezone chỉ dùng khi chuyển lịch địa phương sang Instant hoặc diễn giải cron**, không dùng LocalDateTime không gắn timezone để so sánh expiration của các user tại nhiều vùng.

### Định nghĩa rõ ranh giới so sánh

~~~text
now = 2026-05-01T10:00:00Z

Trial A: expiresAt=09:59:59Z, active=true   -> deactivate
Trial B: expiresAt=10:00:00Z, active=true   -> deactivate
Trial C: expiresAt=10:00:01Z, active=true   -> keep active
Trial D: expiresAt=09:00:00Z, active=false  -> unchanged

Khi chạy lần đầu: changed = 2
Khi chạy lại cùng now: changed = 0
~~~

Đây là dữ liệu fixtures tĩnh để lập luận, **không phải stdout thực đã chạy**. Lịch cron có thể kích hoạt lúc 10:00:02 do load của scheduler; service vẫn dùng thời điểm thật được cấp bởi Clock và điều kiện nghiệp vụ nhất quán.

## 5. @Scheduled: cron, fixedDelay, fixedRate có giống nhau không?

| Thuộc tính | Ý nghĩa | Trường hợp phù hợp | Sai lầm thường gặp |
| --- | --- | --- | --- |
| **cron** | Chạy theo biểu thức lịch, có timezone | Đầu mỗi giờ, mỗi ngày, ngày làm việc | Nhầm cron 5 trường với Spring 6 trường |
| **fixedDelay** | Đợi khoảng thời gian từ **khi lần trước kết thúc** tới lần kế tiếp bắt đầu | Polling phải nghỉ sau mỗi batch | Tưởng nó chạy đều theo thời điểm bắt đầu |
| **fixedRate** | Kích hoạt theo cadence tính từ các lần bắt đầu dự kiến | Tác vụ nhẹ cần nhịp cố định | Giả định luôn chính xác, không bị trễ hoặc overlap |
| **initialDelay** | Trì hoãn lần kích hoạt đầu tiên với fixedRate/fixedDelay | Chờ ứng dụng warm up | Dùng để chữa race thay vì readiness rõ |
| **zone** | Time zone cho cron | Lịch theo múi giờ nghiệp vụ | Nhầm timezone trigger với Clock của business |
| **timeUnit** | Đơn vị cho các số fixedDelay/fixedRate/initialDelay | Tránh nhầm milliseconds | Áp cho cron dù cron không dùng thuộc tính này |

Ví dụ **minh họa**, không cùng lúc gắn vào một method:

~~~java
@Scheduled(fixedDelayString = "PT30S")
public void pollThirtySecondsAfterPreviousFinish() {
    service.expireDueTrials();
}
~~~

~~~java
@Scheduled(fixedRateString = "PT1M", initialDelayString = "PT10S")
public void pollByFixedCadence() {
    service.expireDueTrials();
}
~~~

~~~java
@Scheduled(cron = "0 0 2 * * *", zone = "Asia/Ho_Chi_Minh")
public void runEveryLocalDayAtTwoAm() {
    service.expireDueTrials();
}
~~~

Các đoạn này **chỉ minh họa các lựa chọn trigger**; không thuộc runnable project, vì trong project chọn một cron UTC duy nhất. **PT30S/PT1M/PT10S** là ISO-8601 duration strings được Spring hỗ trợ. Nếu dùng fixedRate ở nhiều scheduler tasks hay @Async, phải kiểm tra scheduler pool, độ dài job và concurrency; **không được mặc định một cron/fixedRate tự khóa mọi instance của cluster**.

### Điều gì xảy ra nếu job chạy lâu?

- **fixedDelay:** sau khi invocation hoàn thành mới bắt đầu đếm delay tiếp theo.
- **fixedRate:** framework cố duy trì nhịp định kỳ, nhưng scheduling thread/pool bận có thể gây trễ; không hứa chính xác tuyệt đối.
- **cron:** trigger theo mốc lịch và timezone, nhưng không bảo đảm invocation thực tế bắt đầu đúng microsecond.
- **Tác vụ chạy trên nhiều replicas:** mỗi replica có scheduler riêng; có thể cùng xử lý một business object.
- **@Scheduled nhiều lần trên cùng method:** Spring xử lý từng declaration độc lập, có thể có overlapping trigger.

Thiết kế rule **idempotent**, có repository conditional update và metric/alert quan trọng hơn việc cố đo chính xác millisecond của cron trong một unit test.

## 6. Dự án Java 17 + Spring Boot 3.4.5 đầy đủ

Project dùng storage adapter **ConcurrentHashMap chỉ để minh họa**. Nó giúp ví dụ chạy không cần PostgreSQL, Docker, email hoặc external API. Trong production, thay bằng JDBC/JPA repository có **atomic conditional UPDATE**, transaction và durable state. Scheduler mặc định **TẮT**, chỉ bật có chủ ý bằng application property.

### 6.1. Cây file

~~~text
settings.gradle
build.gradle
src/main/resources/application.yml
src/main/java/com/example/jobs/TrialJobsApplication.java
src/main/java/com/example/jobs/ClockConfig.java
src/main/java/com/example/jobs/TrialAccount.java
src/main/java/com/example/jobs/TrialAccountRepository.java
src/main/java/com/example/jobs/InMemoryTrialAccountRepository.java
src/main/java/com/example/jobs/TrialExpirationService.java
src/main/java/com/example/jobs/TrialExpirationJob.java
src/test/java/com/example/jobs/TrialExpirationServiceTest.java
src/test/java/com/example/jobs/TrialExpirationJobTest.java
src/test/java/com/example/jobs/SchedulerDisabledWiringTest.java
~~~

### 6.2. Gradle settings và dependencies

**settings.gradle**

~~~groovy
rootProject.name = 'scheduled-business-isolation'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**spring-boot-starter** đủ để tạo ApplicationContext, scheduler infrastructure và logging. Không cần starter-web nếu bài không mở HTTP controller; không cần data-jpa nếu storage demo là in-memory. **spring-boot-starter-test** đã có JUnit Jupiter/Mockito cho unit và Spring context tests. **Spring Boot BOM** quản lý các phiên bản tương thích trong bộ dependencies.

### 6.3. Cấu hình mặc định an toàn

**src/main/resources/application.yml**

~~~yaml
app:
  jobs:
    trial-expiration:
      enabled: false
      cron: "0 0 * * * *"
      zone: "UTC"
      batch-size: 100

spring:
  task:
    scheduling:
      thread-name-prefix: "trial-jobs-"
      pool:
        size: 1
~~~

**enabled=false** có chủ đích: tạo project/test không làm thay đổi dữ liệu theo lịch ngầm. Trong ứng dụng thật, bật job bằng configuration/command line của môi trường có quyền thực thi. Không bật lịch cho tất cả profiles hoặc trên mọi replica mà chưa đánh giá duplicate/concurrency.

**cron** và **zone** được inject vào annotation @Scheduled bằng placeholders. **batch-size** đi vào service qua constructor; unit test truyền trực tiếp số 100/2, không dùng Spring Environment.

### 6.4. Application class bật scheduling infrastructure

**src/main/java/com/example/jobs/TrialJobsApplication.java**

~~~java
package com.example.jobs;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class TrialJobsApplication {
    public static void main(String[] args) {
        SpringApplication.run(TrialJobsApplication.class, args);
    }
}
~~~

**@EnableScheduling** cho Spring đăng ký xử lý @Scheduled. Nó **không buộc job phải tồn tại**: job bean có **@ConditionalOnProperty** nên mặc định không được tạo. Ngược lại, có một method @Scheduled trên object được new thủ công trong unit test **không** làm scheduler tự động gọi nó.

### 6.5. Clock được inject, không gọi Instant.now() lung tung

**src/main/java/com/example/jobs/ClockConfig.java**

~~~java
package com.example.jobs;

import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ClockConfig {

    @Bean
    public Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

**Production:** Clock.systemUTC() phản ánh thời gian hệ thống.

**Test:** Clock.fixed(Instant.parse(...), ZoneOffset.UTC) mang một thời điểm bất biến, khiến unit test có thể kiểm tra account hết hạn đúng mốc **expiresAt == now** mà không chờ đồng hồ. Với nghiệp vụ phụ thuộc giờ/ngày địa phương, Clock cho phép kiểm thử DST/timezone rõ.

**Đừng mock Instant.now() như một static global** nếu có thể inject Clock; static mocks có scope phức tạp và dễ làm rò trạng thái giữa test methods.

### 6.6. Domain record

**src/main/java/com/example/jobs/TrialAccount.java**

~~~java
package com.example.jobs;

import java.time.Instant;
import java.util.Objects;

public record TrialAccount(
        String id,
        Instant expiresAt,
        boolean active) {

    public TrialAccount {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException(
                    "id must not be blank");
        }
        Objects.requireNonNull(expiresAt, "expiresAt");
    }
}
~~~

**Instant** là absolute moment UTC-timeline; không phải LocalDateTime không timezone. Validation trong record giữ dữ liệu đầu vào nhất quán. **active** là state chuyển từ true sang false khi job xử lý, và không tự chuyển lại true trong service này.

### 6.7. Repository port: business không phụ thuộc JDBC/JPA

**src/main/java/com/example/jobs/TrialAccountRepository.java**

~~~java
package com.example.jobs;

import java.time.Instant;
import java.util.List;
import java.util.Optional;

public interface TrialAccountRepository {

    void save(TrialAccount account);

    List<TrialAccount> findActiveDue(Instant now, int limit);

    boolean deactivateIfDue(String accountId, Instant now);

    Optional<TrialAccount> findById(String accountId);
}
~~~

**findActiveDue** là query candidate list tối đa limit, chỉ tài khoản active và hết hạn. **deactivateIfDue** phải bảo đảm state transition có điều kiện **active=true AND expiresAt <= now** ở thời điểm update; trả **true khi đã thực sự thay đổi**, false nếu không. Điều kiện ở update quan trọng vì candidate query và update có thể bị một worker khác chen vào giữa.

Một repository adapter production có thể dùng SQL:

~~~sql
UPDATE trial_accounts
SET active = false
WHERE id = :id
  AND active = true
  AND expires_at <= :now;
~~~

**Affected row count = 1** nghĩa worker thực hiện transition; **0** nghĩa row không tồn tại, chưa đến hạn hoặc đã bị worker khác xử lý. Với JPA, cần transaction và chú ý persistence context stale khi dùng bulk update. Đây là **SQL minh họa**, không phải script chạy trong demo; placeholder :id/:now là named parameters phù hợp với Spring Data/JdbcTemplate named parameter context, không phải JDBC positional question mark.

**Không suy từ query findActiveDue riêng lẻ rằng update chắc thành công**. Phải đếm dựa trên conditional update result.

### 6.8. In-memory storage adapter dùng ConcurrentHashMap

**src/main/java/com/example/jobs/InMemoryTrialAccountRepository.java**

~~~java
package com.example.jobs;

import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.stereotype.Repository;

@Repository
public class InMemoryTrialAccountRepository
        implements TrialAccountRepository {

    private final ConcurrentHashMap<String, TrialAccount> rows =
            new ConcurrentHashMap<>();

    @Override
    public void save(TrialAccount account) {
        rows.put(account.id(), account);
    }

    @Override
    public List<TrialAccount> findActiveDue(
            Instant now, int limit) {
        return rows.values().stream()
                .filter(TrialAccount::active)
                .filter(a -> !a.expiresAt().isAfter(now))
                .sorted(Comparator
                    .comparing(TrialAccount::expiresAt)
                    .thenComparing(TrialAccount::id))
                .limit(limit)
                .toList();
    }

    @Override
    public boolean deactivateIfDue(
            String accountId, Instant now) {
        AtomicBoolean changed = new AtomicBoolean(false);

        rows.computeIfPresent(accountId, (id, current) -> {
            if (current.active()
                    && !current.expiresAt().isAfter(now)) {
                changed.set(true);
                return new TrialAccount(
                    current.id(), current.expiresAt(), false);
            }
            return current;
        });

        return changed.get();
    }

    @Override
    public Optional<TrialAccount> findById(String accountId) {
        return Optional.ofNullable(rows.get(accountId));
    }
}
~~~

**ConcurrentHashMap.computeIfPresent** thực hiện update atomic **trên từng key** đối với một JVM. Candidate query là snapshot/iteration có thể thay đổi trong concurrent scenario, nên **conditional update** vẫn phải kiểm tra lại. Count của service chỉ phản ánh worker thực sự chuyển state, không phải số candidate đã đọc.

**Quan trọng:** Demo adapter không durable, không chia sẻ state giữa replicas, không thực hiện database transaction và không có distributed lock. Nó đủ để học **architecture và deterministic tests**. Trên production thay bằng PostgreSQL/MySQL/JPA adapter và conditional update SQL; dùng database test/Testcontainers để kiểm chứng concurrency và isolation thật.

### 6.9. Business service độc lập với scheduler

**src/main/java/com/example/jobs/TrialExpirationService.java**

~~~java
package com.example.jobs;

import java.time.Clock;
import java.time.Instant;
import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class TrialExpirationService {

    private final TrialAccountRepository repository;
    private final Clock clock;
    private final int batchSize;

    public TrialExpirationService(
            TrialAccountRepository repository,
            Clock clock,
            @Value("${app.jobs.trial-expiration.batch-size:100}")
            int batchSize) {
        if (batchSize <= 0) {
            throw new IllegalArgumentException(
                    "batchSize must be positive");
        }
        this.repository = repository;
        this.clock = clock;
        this.batchSize = batchSize;
    }

    public int expireDueTrials() {
        Instant now = Instant.now(clock);

        List<TrialAccount> candidates =
                repository.findActiveDue(now, batchSize);

        int changed = 0;
        for (TrialAccount candidate : candidates) {
            if (repository.deactivateIfDue(
                    candidate.id(), now)) {
                changed++;
            }
        }
        return changed;
    }
}
~~~

**Tách trách nhiệm:**
- Service tự biết business rule về dueAt/expiresAt, limit và transition.
- Service **không import @Scheduled, không sleep, không tạo thread, không tự tra cron expression**.
- **Clock** cho thời điểm kiểm tra; lấy **một lần ở đầu run** để mọi candidates dùng cùng cutoff. Nếu một batch xử lý vài giây, policy vẫn nhất quán theo thời điểm bắt đầu run.
- **Repository port** thực hiện query/update, nên có thể fake trong unit test hoặc thay bằng JPA/JDBC trong integration test.
- Return value là **số state transitions thành công**, không phải số records tìm thấy hoặc số notifications được gửi.

**Giới hạn cố ý:** Nếu số due accounts lớn hơn batchSize và cron chạy mỗi giờ, xử lý backlog có thể lâu. Production cần polling cadence, pagination/claim strategy và metrics phù hợp. Nhưng không đổi business logic để phụ thuộc vào scheduler period; service vẫn có thể gọi lặp hoặc chạy manual.

### 6.10. Scheduled adapter có điều kiện bật/tắt và logging

**src/main/java/com/example/jobs/TrialExpirationJob.java**

~~~java
package com.example.jobs;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
    prefix = "app.jobs.trial-expiration",
    name = "enabled",
    havingValue = "true")
public class TrialExpirationJob {

    private static final Logger log =
            LoggerFactory.getLogger(TrialExpirationJob.class);

    private final TrialExpirationService service;

    public TrialExpirationJob(TrialExpirationService service) {
        this.service = service;
    }

    @Scheduled(
        cron = "${app.jobs.trial-expiration.cron:0 0 * * * *}",
        zone = "${app.jobs.trial-expiration.zone:UTC}")
    public void run() {
        int changed = service.expireDueTrials();
        log.info("trial expiration completed changed={}", changed);
    }
}
~~~

**Đây là method “mỏng”**: không SQL, không lặp account, không Instant.now(), không tính dueAt hoặc gọi email. Business failure được phép lan ra caller của run(); Spring scheduler infrastructure có cơ chế xử lý/log exception theo cấu hình, nhưng **không suy ra có retry tức thì**. Cần metrics, alerts và retry strategy rõ cho production.

**@ConditionalOnProperty(... havingValue="true")**: chỉ tạo bean khi **app.jobs.trial-expiration.enabled=true**. Khi property vắng mặt hoặc false (với matchIfMissing mặc định false), bean không được tạo, vì vậy không có annotated method để scheduling infrastructure đăng ký. Điều này giúp mọi unit/context test **không tự chạy lịch** khi dự án ở cấu hình mặc định.

**Đừng dùng Thread.sleep để đợi @Scheduled được gọi** khi điều muốn kiểm tra chỉ là “run delegate đúng một lần”. Hãy gọi **new TrialExpirationJob(serviceMock).run()** trực tiếp và verify. Gọi trực tiếp không xác nhận Spring đã đăng ký trigger — đó là một contract khác.

## 7. Unit test business với Clock.fixed và repository thật in-memory

**src/test/java/com/example/jobs/TrialExpirationServiceTest.java**

~~~java
package com.example.jobs;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class TrialExpirationServiceTest {

    private static final Instant NOW =
            Instant.parse("2026-05-01T10:00:00Z");

    private InMemoryTrialAccountRepository repository;
    private Clock clock;
    private TrialExpirationService service;

    @BeforeEach
    void setUp() {
        repository = new InMemoryTrialAccountRepository();
        clock = Clock.fixed(NOW, ZoneOffset.UTC);
        service = new TrialExpirationService(
                repository, clock, 100);
    }

    @Test
    void expiresPastAndExactlyDueButNotFutureOrInactive() {
        repository.save(new TrialAccount(
                "past", NOW.minusSeconds(60), true));
        repository.save(new TrialAccount(
                "exact", NOW, true));
        repository.save(new TrialAccount(
                "future", NOW.plusSeconds(1), true));
        repository.save(new TrialAccount(
                "already-inactive", NOW.minusSeconds(3600), false));

        assertEquals(2, service.expireDueTrials());

        assertFalse(repository.findById("past")
                .orElseThrow().active());
        assertFalse(repository.findById("exact")
                .orElseThrow().active());
        assertTrue(repository.findById("future")
                .orElseThrow().active());
        assertFalse(repository.findById("already-inactive")
                .orElseThrow().active());

        // Chạy lại cùng Clock: không transition lần thứ hai.
        assertEquals(0, service.expireDueTrials());
    }

    @Test
    void usesInjectedClockWithoutSleep() {
        repository.save(new TrialAccount(
                "soon", NOW.plusSeconds(10), true));

        assertEquals(0, service.expireDueTrials());
        assertTrue(repository.findById("soon")
                .orElseThrow().active());

        Clock laterClock = Clock.fixed(
                NOW.plusSeconds(11), ZoneOffset.UTC);
        TrialExpirationService later =
                new TrialExpirationService(
                    repository, laterClock, 100);

        assertEquals(1, later.expireDueTrials());
        assertFalse(repository.findById("soon")
                .orElseThrow().active());
    }

    @Test
    void appliesBatchSizeAndCanProcessBacklogInNextRun() {
        repository.save(new TrialAccount(
                "a", NOW.minusSeconds(30), true));
        repository.save(new TrialAccount(
                "b", NOW.minusSeconds(20), true));
        repository.save(new TrialAccount(
                "c", NOW.minusSeconds(10), true));

        TrialExpirationService batched =
                new TrialExpirationService(
                    repository, clock, 2);

        assertEquals(2, batched.expireDueTrials());
        assertFalse(repository.findById("a")
                .orElseThrow().active());
        assertFalse(repository.findById("b")
                .orElseThrow().active());
        assertTrue(repository.findById("c")
                .orElseThrow().active());

        assertEquals(1, batched.expireDueTrials());
        assertFalse(repository.findById("c")
                .orElseThrow().active());
        assertEquals(0, batched.expireDueTrials());
    }

    @Test
    void countsOnlySuccessfulConditionalUpdates() {
        TrialAccountRepository contended =
                mock(TrialAccountRepository.class);

        when(contended.findActiveDue(NOW, 100))
            .thenReturn(List.of(
                new TrialAccount(
                    "claimed-elsewhere", NOW, true)));

        when(contended.deactivateIfDue(
                "claimed-elsewhere", NOW))
            .thenReturn(false);

        TrialExpirationService underTest =
                new TrialExpirationService(
                    contended, clock, 100);

        assertEquals(0, underTest.expireDueTrials());
        verify(contended).deactivateIfDue(
                "claimed-elsewhere", NOW);
    }

    @Test
    void repositoryFailureIsNotSilentlyReportedAsSuccess() {
        TrialAccountRepository failing =
                mock(TrialAccountRepository.class);

        IllegalStateException outage =
                new IllegalStateException("database unavailable");

        when(failing.findActiveDue(NOW, 100))
            .thenThrow(outage);

        TrialExpirationService underTest =
                new TrialExpirationService(
                    failing, clock, 100);

        IllegalStateException actual = assertThrows(
                IllegalStateException.class,
                underTest::expireDueTrials);
        assertSame(outage, actual);
    }

    @Test
    void rejectsZeroOrNegativeBatchSize() {
        assertThrows(IllegalArgumentException.class,
                () -> new TrialExpirationService(
                    repository, clock, 0));

        assertThrows(IllegalArgumentException.class,
                () -> new TrialExpirationService(
                    repository, clock, -5));
    }
}
~~~

### Phân tích giá trị của từng test

**expiresPastAndExactlyDueButNotFutureOrInactive** chứng minh bốn vùng boundary (past, exact, future, inactive) và gọi lại không làm hiệu ứng lặp. Đây là business policy, không cần cron thực.

**usesInjectedClockWithoutSleep** dùng hai Clock.fixed cho hai thời điểm khác nhau, không hề chờ 11 giây. Nếu project dùng Instant.now() trực tiếp, test này dễ bị phụ thuộc thời gian máy chạy; Clock injection giải quyết root cause.

**appliesBatchSizeAndCanProcessBacklogInNextRun** chứng minh một run chỉ xử lý tối đa hai rows và run tiếp theo xử lý backlog. Nó không cần chờ scheduled trigger tiếp theo.

**countsOnlySuccessfulConditionalUpdates** mô phỏng race: query thấy row nhưng worker khác đã chuyển state trước khi update, nên repository trả false. Service trả changed=0, không đếm candidate giả.

**repositoryFailureIsNotSilentlyReportedAsSuccess** chứng minh hạ tầng lỗi không bị nuốt rồi báo count=0 giả. Scheduler có thể log lỗi/alert theo policy. **@Scheduled tự nó không tạo business retry**.

**rejectsZeroOrNegativeBatchSize** chứng minh config invalid được chặn sớm. Mọi test là JUnit thuần; **không có @SpringBootTest**, không cần Docker, database, mail server hay thread scheduler.

## 8. Unit test scheduled adapter: không chờ cron

**src/test/java/com/example/jobs/TrialExpirationJobTest.java**

~~~java
package com.example.jobs;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class TrialExpirationJobTest {

    @Mock
    private TrialExpirationService service;

    private TrialExpirationJob job;

    @BeforeEach
    void setUp() {
        job = new TrialExpirationJob(service);
    }

    @Test
    void delegatesOneRunToBusinessServiceOnce() {
        when(service.expireDueTrials()).thenReturn(3);

        job.run();

        verify(service, times(1)).expireDueTrials();
    }

    @Test
    void doesNotSwallowBusinessFailure() {
        IllegalStateException failure =
                new IllegalStateException("database unavailable");

        when(service.expireDueTrials()).thenThrow(failure);

        IllegalStateException thrown = assertThrows(
                IllegalStateException.class, job::run);

        assertSame(failure, thrown);
        verify(service, times(1)).expireDueTrials();
    }
}
~~~

**Đây là adapter test, không phải trigger timing test.** Job được new trực tiếp, không có Spring context nên @Scheduled chưa được scheduler đăng ký. Khi gọi job.run() và verify service một lần, test chứng minh adapter mỏng làm đúng nhiệm vụ. Mockito mock của service không cần Clock/repository vì đó là trách nhiệm của TrialExpirationServiceTest.

**Không dùng @MockBean/@MockitoBean để ép toàn ApplicationContext chạy chỉ nhằm verify một lời gọi**. Khi thật sự cần kiểm tra Spring bean wiring, một test riêng sẽ phù hợp hơn (phần 9).

### Phân biệt kết quả service và trigger

Nếu cron đổi từ mỗi giờ sang mỗi phút mà business logic không đổi, **TrialExpirationServiceTest phải vẫn PASS** vì rule hết hạn không phụ thuộc schedule. Nếu service đổi từ expiresAt <= now sang expiresAt < now, unit test boundary exact phải FAIL. Nếu Scheduled adapter quên gọi service, **TrialExpirationJobTest FAIL**. Mỗi nhóm bảo vệ đúng phần code mình sở hữu.

## 9. Spring context test: tắt job để tránh side effects trong suite

**src/test/java/com/example/jobs/SchedulerDisabledWiringTest.java**

~~~java
package com.example.jobs;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(properties = {
    "app.jobs.trial-expiration.enabled=false",
    "app.jobs.trial-expiration.batch-size=2"
})
class SchedulerDisabledWiringTest {

    @Autowired
    private ApplicationContext context;

    @Autowired
    private TrialExpirationService service;

    @Test
    void businessBeanIsWiredButScheduledAdapterAbsent() {
        assertNotNull(service);
        assertEquals(
            0,
            context.getBeanNamesForType(
                TrialExpirationJob.class).length);
    }
}
~~~

**Điểm cần chứng minh:** ứng dụng vẫn tạo business service và các dependencies nhưng job adapter **không được tạo** vì property false. Nhờ vậy test suite có thể chạy mà không có một background job bất ngờ vô hiệu hóa dữ liệu kiểm thử.

**Không cố chứng minh annotation sẽ tự chạy đúng lịch bằng cách Thread.sleep trong @SpringBootTest**. Khi cần test wiring kích hoạt thật, nên tạo một integration test context khác với property enabled=true, dùng scheduler-aware assertions và deterministic synchronization, nhưng phải cô lập DB/resources, không để nó ảnh hưởng test còn lại.

### Vì sao property guard tốt hơn chỉ chờ cron rất xa?

Một cron “ngày 1/1 lúc 00:00” vẫn có khả năng chạy khi CI đúng mốc đó, đặc biệt khi timezone khác. **@ConditionalOnProperty** đảm bảo job bean không tồn tại khi disable; đó là bằng chứng rõ ràng và chủ động. Cron special value **"-"** cũng có thể vô hiệu hóa một trigger khi đặt qua property, nhưng khi dùng nó **bean vẫn tồn tại**; hai cơ chế có mục tiêu khác.

## 10. Chạy test mà không khởi động scheduler thật

Với JDK 17+, Gradle Wrapper tương thích và dependencies như build.gradle:

~~~bash
./gradlew clean test
./gradlew test --tests com.example.jobs.TrialExpirationServiceTest
./gradlew test --tests com.example.jobs.TrialExpirationJobTest
./gradlew test --tests com.example.jobs.SchedulerDisabledWiringTest
./gradlew test --tests com.example.jobs.TrialExpirationServiceTest.expiresPastAndExactlyDueButNotFutureOrInactive
~~~

Trên Windows dùng **gradlew.bat** với tham số tương ứng. Các test được thiết kế để PASS theo code nếu tệp/package/dependencies giống bài; **không khẳng định một phiên chạy Gradle thực tế đã được quan sát**.

### Bảng expected outcomes

| Test | Contract chứng minh |
| --- | --- |
| expiresPastAndExactlyDueButNotFutureOrInactive | past/exact due thành inactive, future giữ active, inactive không đổi, lần hai changed=0 |
| usesInjectedClockWithoutSleep | Clock khác làm thay đổi kết quả mà không sleep |
| appliesBatchSizeAndCanProcessBacklogInNextRun | Mỗi run ≤2; backlog xử lý 2+1; cuối còn 0 |
| countsOnlySuccessfulConditionalUpdates | Race update=false không được đếm |
| repositoryFailureIsNotSilentlyReportedAsSuccess | Dependency exception được propagate |
| rejectsZeroOrNegativeBatchSize | Invalid configuration bị reject |
| delegatesOneRunToBusinessServiceOnce | Job chỉ delegate một lần |
| doesNotSwallowBusinessFailure | Job không biến lỗi thành success giả |
| businessBeanIsWiredButScheduledAdapterAbsent | Spring tạo business bean, không tạo scheduled bean khi disabled |

**Không cần chạy ứng dụng và chờ đến đầu giờ** để test nghiệp vụ. Nếu một test chỉ có thể pass khi chờ cron, đó là dấu hiệu đã trộn trách nhiệm hoặc đang test scheduling integration nhưng chưa thiết kế đồng bộ thời gian tốt.

## 11. Chạy ứng dụng thật và bật lịch đúng chỗ

Cấu hình mặc định job đã disabled. Để bật trong môi trường an toàn có test data:

~~~bash
./gradlew bootRun --args='--app.jobs.trial-expiration.enabled=true'
~~~

Khi bật, @Scheduled trigger đăng ký trên Spring-managed bean và chạy theo cron/zone. **Mặc định không có account nào trong in-memory repository** vì demo không seed dữ liệu ở startup, nên job chỉ có thể log changed=0 cho đến khi có logic thêm account. Đó là chủ đích: ví dụ tập trung kiến trúc và testability, không tự sinh dữ liệu production giả.

Bạn có thể đổi property của cron bằng argument:

~~~bash
./gradlew bootRun --args='--app.jobs.trial-expiration.enabled=true --app.jobs.trial-expiration.cron=0 */5 * * * *'
~~~

**Chú ý quoting của shell và Spring Boot Gradle plugin:** đối với cron có dấu cách, command line parser/shell có thể yêu cầu escape/quote khác nhau. Trong project production, nên đặt cron trong YAML/environment config đã được kiểm soát thay vì viết lệnh shell phức tạp. Để tránh nhập nhằng, trong demo dùng cron từ application.yml mặc định.

**Không đổi clock từ UTC sang local timezone chỉ vì cron theo local timezone.** Clock của business dùng Instant và UTC timeline; nếu rule là “hết hạn vào 00:00 theo timezone người dùng”, chuyển LocalDate + ZoneId của user thành Instant một cách tường minh ở business layer rồi unit test các biên DST.

## 12. @Scheduled và @Async không phải cùng cơ chế

**@Scheduled** chọn **khi nào kích hoạt** method. **@Async** (nếu được bật bằng @EnableAsync) chạy method qua **async executor**. Hai annotation khác nhiệm vụ:

| Vấn đề | @Scheduled | @Async |
| --- | --- | --- |
| Trigger theo thời gian | Có | Không |
| Chạy trên thread khác caller | TaskScheduler thread | Executor thread |
| Có business retry tự động | Không | Không |
| Có transaction propagation tự động sang thread khác | Không mặc nhiên | Không mặc nhiên |
| Dễ test business bằng plain JUnit | Khi tách service | Khi tách service |
| Có thể chạy song song nhiều instances | Có | Có |
| Cần quan sát completion/errors | Có | Có |

Đặt cả @Scheduled và @Async lên cùng method dễ làm quyền kiểm soát lifecycle, overlapping invocations và exception propagation phức tạp. Không làm vậy trong demo. Nếu job cần chạy song song, nên có **queue/claim strategy**, durable state và bounded concurrency, không coi @Async là giải pháp cho race condition.

Spring Boot cấu hình **spring.task.scheduling** cho TaskScheduler và **spring.task.execution** cho AsyncTaskExecutor. Hai namespaces không tương đương. Trong Java 21+ với virtual threads, Boot có thể chọn scheduler implementation khác; bài dùng **Java 17**, không bật virtual-thread mode.

## 13. Tại sao unit test không nên sleep?

Một test kiểu:

~~~java
awaitSomeSeconds();
verify(notificationService, times(1)).send(...);
~~~

là anti-pattern khi mục tiêu thật chỉ là tính “đã hết hạn chưa”. Nó:
- chạy chậm mỗi lần;
- phụ thuộc tải CI và thời điểm machine;
- dễ fail khi cron chưa đến mốc;
- có thể bị ảnh hưởng timezone/DST;
- không phân biệt scheduler chưa kích hoạt hay service tính sai.

**Thay bằng Clock.fixed + direct service invocation**. Với integration test scheduling thật, có thể dùng Awaitility, CountDownLatch hoặc test-specific trigger instrumentation để chờ **observable condition** với bounded timeout. Nhưng đó là test scheduling infrastructure — ít cases hơn, không phải mọi business scenario.

### Test run đúng hạn không cần chờ scheduler

~~~java
Instant target = Instant.parse("2026-05-01T10:00:00Z");
Clock fixedClock = Clock.fixed(target, ZoneOffset.UTC);

TrialExpirationService service =
    new TrialExpirationService(repository, fixedClock, 100);

assertEquals(2, service.expireDueTrials());
~~~

Đây là **trích đoạn** đã được cụ thể hóa đầy đủ trong TrialExpirationServiceTest. Kết quả dựa trên fixture data và injected Clock, **không phải đồng hồ hệ điều hành**.

## 14. Đừng nhầm unit test với kiểm thử Spring registration

Một test:

~~~java
TrialExpirationJob job = new TrialExpirationJob(mockService);
job.run();
verify(mockService).expireDueTrials();
~~~

chỉ kiểm tra **adapter method**. Spring không quản lý object đó, @Scheduled chưa được đăng ký. Ngược lại, một @SpringBootTest bật cron và nhìn thấy log job đã chạy không chứng minh policy **expiresAt <= now** hoặc idempotency đúng.

### Khi nào cần integration test schedule registration?

Khi một thay đổi liên quan đến:
- cron placeholder binding và syntax;
- timezone/cron DST behavior;
- @ConditionalOnProperty enable/disable;
- custom TaskScheduler bean hoặc scheduler pool;
- bean scanning, @EnableScheduling, @Profile;
- distributed lock/leader election integration;
- task exceptions, metrics, actuator/observability;
- concurrency/backpressure khi nhiều schedules cùng chạy.

Một strategy:
1. Khởi một context riêng với enabled=true và một scheduling test-only configuration.
2. Dùng một test service/fake event recorder, hoặc @MockitoBean nếu cần Spring bean override.
3. Cấu hình trigger ngắn **chỉ trong test context đó**, không trong app mặc định.
4. Chờ một sự kiện quan sát được với timeout hữu hạn bằng Awaitility/latch, assert invocation.
5. Đóng context/dừng scheduler và cleanup dữ liệu để test khác không bị ảnh hưởng.

**Không yêu cầu mọi unit test bật scheduler** chỉ để kiểm tra một annotation. Thiết kế một hoặc vài integration tests có kiểm soát thay cho hàng chục sleep-based tests.

## 15. Cạnh tranh giữa nhiều instances và idempotency

Một @Scheduled method chạy trong **mỗi instance của ứng dụng** nếu cùng bật config. Giả sử có ba pods cùng chạy cron 10:00 UTC:

~~~text
pod A: SELECT accounts due -> account-7
pod B: SELECT accounts due -> account-7
pod C: SELECT accounts due -> account-7

pod A: UPDATE ... WHERE active=true AND expires_at<=now -> 1 row
pod B: UPDATE ... WHERE active=true AND expires_at<=now -> 0 rows
pod C: UPDATE ... WHERE active=true AND expires_at<=now -> 0 rows
~~~

**Conditional update** giúp chỉ một worker thực sự đổi trạng thái của account-7. Đây là lý do service đếm **boolean success của update** thay vì đếm candidates. Trong demo ConcurrentHashMap.atomic computeIfPresent mô phỏng transition atomic **trong một JVM**, còn JDBC update với WHERE condition là thiết kế cho shared DB.

**Tuy nhiên conditional update chưa đủ cho mọi loại side effect.** Nếu ngoài việc disable còn cần gửi email/payment event, thứ tự send/commit và retry có thể gây duplicates/loss. Khi cần reliable event publishing, dùng **transactional outbox**, unique business event ID và idempotent consumer; đồng thời test concurrency/failure trên database + message broker thật.

### Distributed lock khác idempotency

Distributed lock (ShedLock, Quartz clustered scheduler, DB lease hoặc leader election) có thể giảm số worker đồng thời chạy cùng job. Nhưng lock có thể expire, worker crash, network partition hoặc bị retry. **Không dùng lock như bằng chứng duy nhất rằng side effect exactly-once**. Dữ liệu nghiệp vụ cần unique constraints/conditional transitions và durable retry semantics.

### Batch processing và pagination

Một batchSize lớn có thể giữ transaction quá lâu; một batch quá nhỏ có thể tồn backlog. Khi query candidate list và update trên DB:
- lọc trực tiếp **active=true AND expires_at<=now**;
- order ổn định và limit phù hợp;
- update conditional/optimistic locking;
- ghi metric số candidates, changed, skipped, failed, duration;
- cân nhắc lock/claim/SKIP LOCKED nếu nhiều workers;
- tránh offset pagination trên một tập dữ liệu đang bị thay đổi liên tục vì có thể bỏ qua rows.

**Use case service chịu trách nhiệm chiến lược batch**, không phải method @Scheduled biết SQL pagination chi tiết. Adapter chỉ trigger use case.

## 16. Transaction boundaries và retry

@Scheduled method chạy ở scheduler thread, không tự kế thừa transaction của một HTTP request hoặc JUnit test thread. Nếu business service hoặc repository ghi DB, phải có transaction semantics rõ bằng Spring transaction management.

Với một production Spring Data adapter có thể dùng:

~~~java
@Transactional
public int processBatch() {
    // load due rows, apply updates, commit
}
~~~

Đây là **trích đoạn**, không thuộc runnable project vì demo dùng ConcurrentHashMap. @Transactional có tác dụng khi method được gọi qua Spring-managed proxy phù hợp; **self-invocation** bỏ qua proxy có thể làm transaction không được áp dụng như mong đợi.

### Một job thất bại thì lịch kế tiếp có chạy không?

Trong Spring TaskScheduler, lỗi của periodic task có thể được error handler ghi log và xử lý, rồi scheduling tiếp tục tùy implementation/error handler. **Không nên giả định Spring sẽ tự retry business operation ngay lập tức** hay mọi exception luôn dừng cả ứng dụng. Trách nhiệm production:
- log structured jobId/runId, duration, changed/failed counts;
- alert khi liên tiếp fail;
- retry với backoff cho transient errors có kiểm soát;
- đảm bảo partial progress được phép chạy lại;
- không swallow lỗi rồi báo metric success;
- tránh retry vô hạn poison record;
- có playbook/manual rerun an toàn.

Trong demo, service và job để exception propagate; **unit tests kiểm tra propagation**, còn infrastructure xử lý/log tùy cấu hình. Điều này dễ chẩn đoán hơn bắt Exception rồi return 0 giả “không có account quá hạn”.

### Test partial failure

Nếu trong batch 100 records, 20 records đã transition rồi record thứ 21 gây exception, không phải mọi thay đổi nhất định bị rollback khi không có transaction. In-memory demo không có atomic batch transaction; chạy lại service vẫn an toàn với accounts đã inactive. Production DB adapter cần lựa chọn:
- một transaction cho toàn batch (all-or-nothing);
- per-item transaction và retry;
- atomic claim + outbox;
- snapshot/pagination phù hợp.

Unit test logic idempotent chưa chứng minh production transaction rollback; khi yêu cầu phụ thuộc DB, thêm **@DataJpaTest hoặc Testcontainers database integration** với đúng repository adapter và transaction policy.

## 17. Thời gian nghiệp vụ, cron timezone và DST

Một clock test đúng cần phân biệt:

**Instant:** mốc tuyệt đối; ví dụ expiresAt="2026-05-01T10:00:00Z". So sánh với Instant.now(clock) đúng nếu policy dựa vào expiry tuyệt đối.

**LocalDate/LocalDateTime:** biểu diễn ngày hoặc giờ không nhất thiết có timezone. Nếu yêu cầu “hết hạn cuối ngày địa phương của người dùng”, phải biết ZoneId và quy tắc DST để chuyển thành Instant.

**Cron zone:** chọn lúc scheduler trigger. Cron **0 0 2 * * *** ở zone có DST có thể gặp ngày thiếu 02:00 hoặc có lặp một giờ; không đặt business policy ở “số lần cron thực thi” nếu yêu cầu là “xử lý mỗi account hết hạn đúng một lần”.

**Clock.systemUTC vs Clock.fixed:** một cái dùng trong runtime, một cái dùng trong test. Inject Clock ở boundary; đừng chỉnh timezone/global system clock của CI để tạo edge case.

**Offset/time synchronization:** trên nhiều nodes, system clock skew có thể tạo khác biệt cutoff vài giây. Nếu critical, dùng authoritative time source hoặc DB current timestamp theo contract và test phù hợp. Bài demo chọn Clock tại use case vì dễ test và đủ cho chủ đề tách nghiệp vụ khỏi schedule.

## 18. Những lựa chọn khác: cron disabled, profiles, scheduler bean

### Cách A: @ConditionalOnProperty trên job bean

~~~java
@ConditionalOnProperty(
    prefix = "app.jobs.trial-expiration",
    name = "enabled",
    havingValue = "true")
~~~

Khi disabled, **job bean không tồn tại**; đây là cách project demo sử dụng. Nó giúp scheduler không đăng ký job ở unit/integration test contexts thông thường.

### Cách B: cron expression "-" để tắt trigger

Spring Framework @Scheduled cho phép cron value **"-"** biểu thị disabled trigger:

~~~java
@Scheduled(cron = "${jobs.some-cron:-}")
public void runScheduled() {
    service.expireDueTrials();
}
~~~

Đây là **trích đoạn**, không thuộc project. **Bean có thể vẫn tồn tại**, nhưng annotation registration bỏ qua cron bị disable. Phù hợp khi muốn giữ bean để manual invocation dù không có trigger, nhưng test cần phân biệt **bean present** và **task registered**.

### Cách C: Spring @Profile

Một job chỉ tồn tại khi profile phù hợp, ví dụ @Profile("production-jobs"). Profiles tiện nhưng dễ làm test behavior lệ thuộc config matrix. **Explicit enabled property** thường dễ quan sát hơn; không cần gắn job với mọi profile production nếu muốn chỉ một số nodes chuyên xử lý jobs.

### Cách D: cấu hình riêng @EnableScheduling

Có thể tách @EnableScheduling vào @Configuration bật theo property/profile, để contexts không cần scheduling không tạo infrastructure. Đây là một lựa chọn khi nhiều jobs cần được disable đồng loạt. Demo luôn có @EnableScheduling nhưng job có conditional bean.

**Không dùng @DirtiesContext để tắt lịch**: nó chỉ làm context được dựng lại, job trong context mới vẫn có thể chạy nếu enabled=true. Tắt ở configuration trước khi khởi context mới là đúng cách.

## 19. Khi có nhiều scheduled methods

Một ứng dụng có thể có:
- trial expiry;
- invoice payment reminder;
- cache cleanup;
- email digest;
- inventory reconciliation;
- report generation.

Không nên gom mọi logic vào một class có nhiều @Scheduled rồi test cả bằng một SpringBootTest chờ thread timing. Hãy có một use case per job hoặc domain orchestration rõ:

~~~text
ExpiryScheduledAdapter -> ExpireTrialAccountsUseCase
ReminderScheduledAdapter -> PrepareInvoiceRemindersUseCase
CacheCleanupAdapter    -> EvictExpiredCacheEntriesUseCase
ReportScheduledAdapter -> GenerateReportUseCase
~~~

Các adapters chỉ chứa scheduling metadata, logging và delegation; mỗi service có **Clock/ports/test fixtures** độc lập. Nếu cần đảm bảo thứ tự chạy giữa hai jobs, **đó là workflow dependency**, không phải vấn đề giải bằng hy vọng cron A chạy vài phút trước cron B. Dùng orchestration, queue/event, workflow engine hoặc state machine phù hợp, kiểm thử explicit ordering contract.

### Không lạm dụng @Async trên method @Scheduled

@Async có thể làm scheduled trigger nhanh chóng return trong khi work tiếp tục trên executor; dẫn đến overlapping invocation nếu period ngắn hơn work duration. Cần bounded queue, backpressure, idempotency, cancellation/shutdown policy và metric. Một scheduled adapter mỏng gọi service đồng bộ có thể đơn giản hơn rất nhiều để học và kiểm thử.

## 20. Observability giúp phân biệt “không chạy” và “không có việc”

Khi một job chỉ log changed=0, cần phân biệt:
- scheduler trigger không được đăng ký (bean/property disabled);
- trigger được đăng ký nhưng chưa đến giờ;
- trigger chạy nhưng repository tìm 0 candidate;
- repository tìm candidates nhưng conditional update 0 vì worker khác đã xử lý;
- execution bị lỗi giữa chừng nhưng error bị swallow;
- job bị dừng bởi shutdown;
- log bị trễ/mất trong pipeline.

Nên có thông tin:
- **job name** và **run ID**;
- **trigger source**: scheduled/manual/retry;
- **startedAt**, **duration**;
- **candidateCount**, **changedCount**, **skippedCount**, **errorCount**;
- **success/failure status**;
- **instance ID** khi có nhiều replicas;
- **backlog age** (tuổi account quá hạn cũ nhất chưa xử lý).

Trong code demo log **changed** để giữ adapter mỏng. Production có thể dùng Micrometer Observation/metrics và tracing; đặt metrics ở adapter/orchestrator, còn business service trả kết quả có cấu trúc thay vì để scheduler query nội bộ.

**Không cần test log exact timestamp/Thread.sleep để biết business thành công**. Unit tests đã assert domain state và count trực tiếp; observability integration tests chỉ cần khi metric/log contract có giá trị sản phẩm.

## 21. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Sửa thế nào |
| --- | --- | --- |
| Test mất vài phút để chờ cron | Business logic nằm trong @Scheduled | Chuyển sang service và gọi trực tiếp |
| Test thỉnh thoảng fail sát nửa đêm | Instant.now()/LocalDate.now() hard-code | Inject Clock.fixed |
| Test chạy lẻ pass, chạy suite fail | Background @Scheduled đang chạy trong @SpringBootTest | Disable job qua property/conditional bean |
| @Scheduled không chạy dù app đã start | Thiếu @EnableScheduling, bean không được scan, property disabled | Kiểm tra config và scheduled bean registration |
| Unit test new Job nhưng cron không chạy | Object không phải Spring-managed bean | Đó là expected; chỉ test delegate, integration riêng |
| Test chỉ verify service call mà business sai | Mock cả subject | Unit test service thật với fake repository |
| Count=3 dù workers race và chỉ 1 update | Đếm candidates thay vì affected rows | Conditional update result |
| Hai pods vô hiệu hóa một account hai lần | Mỗi instance có scheduler riêng | DB atomic update/idempotency, lock khi cần |
| Email gửi hai lần khi retry | Send và mark không atomic | Outbox, unique event id, idempotent consumer |
| Job error nhưng log success changed=0 | Catch-all Exception rồi swallow | Propagate/report failure, metrics |
| 0 candidate nhưng DB có expired records | Timezone/Instant conversion sai, query filter sai | Clock/DB query integration tests |
| Test cố giả lập thời gian bằng Thread.sleep | Timing nondeterministic | Clock.fixed, manual invocation |
| @DirtiesContext mà job vẫn chạy | Context mới vẫn bật scheduling | Tắt job bằng property trước context creation |
| Cron chạy vào giờ sai | Zone default khác mong muốn | @Scheduled(zone=...) và test cron parse |
| Cùng task bị gọi nhiều lần liên tiếp | Repeatable @Scheduled / nhiều instances / multiple beans | Kiểm tra registrations/replicas |
| @Async làm job overlap | Work vượt period, executor không bounded | Control concurrency/backpressure |
| Batch 1000 rows chiếm tài nguyên lâu | Không limit hoặc transaction quá lớn | Bounded batch/query order/claim strategy |
| Test DB fake pass, production JDBC fail | In-memory không mô phỏng locking/transaction | Testcontainers DB integration |
| Scheduling job dùng static Clock mock | State rò qua tests | Inject Clock per test |
| Test muốn kiểm cron nên chỉ assert method có annotation | Metadata chưa chứng minh registration/execution | Context/scheduler integration test riêng |
| Test fixedRate 1s fail trên CI tải cao | Hệ điều hành/scheduler không realtime | Assert trigger eventually với timeout, không exact milliseconds |
| Nhiều CI jobs dùng chung DB | Data fixture đụng nhau | Isolated DB/schema/unique keys/cleanup |

## 22. Chọn phương pháp test theo tầng

| Điều muốn bảo vệ | Cách test nên dùng | Không cần |
| --- | --- | --- |
| Hết hạn đúng thời điểm | Plain JUnit + Clock.fixed + fake repo | @SpringBootTest, cron |
| Exactly-at-now boundary | Fixed Clock và Instant so sánh <= | Thay system clock |
| Batch size/retry idempotency | Plain JUnit + fixture data | Đợi scheduler lần thứ hai |
| Job delegate | Mockito mock service, gọi job.run() | Scheduler thread |
| Job enabled=false | @SpringBootTest + getBeanNamesForType | Thread.sleep |
| Cron expression/zone binding | Spring context/cron parser test | Business dataset lớn |
| Service SQL conditional update | @DataJpaTest/JDBC integration, H2 hoặc production DB | Kafka/HTTP |
| Nhiều pods cùng xử lý | DB concurrency integration, unique/atomic condition | Mockito call counts |
| Distributed lock/leader election | Multi-instance integration | Unit business test đơn lẻ |
| Email/outbox reliability | DB+broker/message integration test | Claim từ một service mock |
| Scheduler invocation reliability | TaskScheduler integration có latch/Awaitility | Thread.sleep đoán |

### Câu hỏi trước khi thêm @SpringBootTest

**Test này có cần Spring container để chứng minh điều gì không?** Nếu câu trả lời là “chỉ cần tính expiredAt <= now”, không. Nếu cần verify property conditional bean, scheduler registrar, task executor hoặc transaction proxy, có.

## 23. Bài tập tự kiểm tra

**1.** Mục tiêu là xác minh tài khoản hết hạn đúng tại now. Có cần chờ cron không? **Không.** Inject Clock.fixed, gọi service trực tiếp.

**2.** @Scheduled method có nên tự query DB và gửi mail không? **Không nên** khi có thể tách use case và outbound adapters; lịch chỉ trigger.

**3.** new TrialExpirationJob(serviceMock).run() có chứng minh Spring đã đăng ký cron không? **Không**, chỉ kiểm tra delegate Java method.

**4.** Cron "0 0 * * * *" trong Spring là lúc nào? **Đầu mỗi giờ**, vì biểu thức có sáu trường.

**5.** fixedDelay và fixedRate khác nhau điểm nào? **fixedDelay đo sau khi lần trước hoàn thành; fixedRate cố giữ nhịp từ các lần bắt đầu**.

**6.** Property enabled=false trong demo có kết quả gì? **TrialExpirationJob bean không được tạo**, dù @EnableScheduling vẫn hiện diện.

**7.** Có thể dùng cron "-" để disable trigger không? **Có**, nhưng bean vẫn có thể tồn tại; khác @ConditionalOnProperty.

**8.** Clock.systemUTC dùng ở đâu? **Production wiring**; Clock.fixed dùng trong tests để kiểm soát business now.

**9.** expiresAt bằng đúng now có được expire trong rule bài không? **Có**, policy inclusive **expiresAt <= now**.

**10.** Vì sao service lấy Instant.now(clock) một lần mỗi run? Để dùng **cùng cutoff** trong toàn batch, tránh khác biệt micro-time giữa các records.

**11.** Chạy service hai lần cùng now có deactivate cùng account hai lần không? **Không** khi repository conditional update idempotent.

**12.** Query tìm 2 candidates, nhưng một row đã bị node khác xử lý trước update. Changed count bằng 2? **Không**, chỉ đếm số update thành công.

**13.** @Scheduled trên ba pods có tự chạy một lần toàn cluster không? **Không**, mỗi pod có scheduler riêng.

**14.** Distributed lock có đủ bảo đảm exactly-once email không? **Không**, vẫn cần idempotency/atomicity/outbox khi có external side effects.

**15.** @Transactional trong JUnit test có rollback job chạy trên scheduler thread không? **Không tự động**, transaction thread khác.

**16.** Test muốn xác minh cron timezone có phải business unit test không? **Không**, đó là scheduling/config integration test.

**17.** Test @SpringBootTest bật job mà không cần làm vậy có nguy cơ gì? Background job mutate state, gây flaky và thứ tự phụ thuộc.

**18.** Vì sao Thread.sleep thường không phù hợp? Chậm, flaky, không kiểm soát chính xác scheduler/clock.

**19.** Khi DB unavailable, service nên return 0 để job xanh không? **Không**, phải truyền/report lỗi để quan sát và retry policy.

**20.** In-memory ConcurrentHashMap trong demo có bảo đảm cluster idempotency không? **Không**, chỉ trong một JVM và một key; cần DB shared/atomic update.

**21.** Batch limit=2 và ba account due. Một lần chạy cần changed bao nhiêu? **2**, chạy tiếp nếu không có race thì thêm **1**.

**22.** @DirtiesContext có chắc dừng mọi job mãi mãi không? **Không**, context mới có cùng enabled property sẽ đăng ký lại task.

**23.** Spring Boot 3.4 thường cấu hình pool scheduler bằng namespace nào? **spring.task.scheduling**; khác spring.task.execution cho async executor.

**24.** Nếu scheduled task cần gửi event Kafka sau DB update thì nên chú ý gì? **Atomicity và retry**, cân nhắc transactional outbox + idempotent consumer.

**25.** Có nên test việc một annotation tồn tại bằng reflection rồi coi như lịch chạy đúng? **Không**, cần integration test registration và execution khi đó là contract.

### Checklist QA trước khi chốt bài

- Business logic đã nằm trong **TrialExpirationService**, không trong @Scheduled method?
- Có repository port thay vì SQL nằm trong scheduler?
- Business lấy now qua **Clock** được inject, không gọi Instant.now() trực tiếp?
- Đã định nghĩa rõ **expiresAt <= now**, active flag, batch size và idempotency?
- Service unit tests dùng Clock.fixed, không Thread.sleep?
- Có test quá hạn, đúng hạn, chưa đến hạn, đã inactive và chạy lại?
- Có test batch boundary, conditional update race và dependency failure?
- Job adapter test chỉ kiểm delegate, không giả vờ đã chạy cron thật?
- App @EnableScheduling và job @ConditionalOnProperty có được hiểu đúng?
- Trong test context, job có **enabled=false** và không có background side effects?
- Có phân biệt cron, fixedDelay, fixedRate, initialDelay và zone?
- Có hiểu timezone/DST của cron khác thời điểm business được inject?
- Có kế hoạch cho multiple replicas, DB atomic update và external side effects?
- In-memory fake không bị coi là durable DB production?
- Khi cần SQL/transaction correctness, có thêm DB integration test?
- Không lạm dụng @Async/@Transactional để “chữa” race mà không hiểu thread boundaries?
- Có đo được job runs, changed, failure, backlog thay vì chỉ một dòng log?
- Không dùng @DirtiesContext hay disable cron ngẫu nhiên để che các test flaky?
- Không tuyên bố đã thực chạy Gradle/cron khi không có execution evidence?

**Kết luận:** **@Scheduled nên quyết định khi nào chạy, không quyết định nghiệp vụ phải làm gì.** Chuyển rule vào một use case độc lập với **Clock**, repository port và conditional update giúp test chính xác mọi boundary bằng JUnit trong mili-giây, không phụ thuộc scheduler thread hay đồng hồ CI. Scheduled adapter chỉ delegate, được test bằng Mockito; việc enable/disable và cron wiring được kiểm tra riêng khi thật cần. Khi triển khai nhiều instances, vẫn phải bảo đảm idempotency, transactions, retry/observability và data isolation — những vấn đề mà annotation @Scheduled tự nó không giải quyết.

## Tài liệu chính thức

- Spring Framework 6.2 — Annotation @Scheduled Javadoc (cron 6 trường, zone, fixedRate, fixedDelay, CRON_DISABLED): https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/Scheduled.html
- Spring Framework 6.2 — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html
- Spring Boot 3.4 — Task Execution and Scheduling, spring.task.scheduling.pool.size: https://docs.spring.io/spring-boot/3.4/reference/features/task-execution-and-scheduling.html
- Spring Boot 3.4 — ConditionalOnProperty Javadoc: https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html
- Spring Framework 6.2 — Spring TestContext Framework: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework.html
- Spring Framework — Transaction Propagation and AOP proxies: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Java SE 17 — Clock: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html

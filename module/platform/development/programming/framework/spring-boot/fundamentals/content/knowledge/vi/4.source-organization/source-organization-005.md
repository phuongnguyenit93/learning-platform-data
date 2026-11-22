# Vai trò của service, adapter, configuration và thành phần truy cập dữ liệu

Khi một ứng dụng Spring Boot mới có một REST controller trả về lời chào, có thể đặt gần như mọi đoạn mã trong một class. Nhưng khi ứng dụng phải nhận HTTP request, kiểm tra quy tắc nghiệp vụ, lưu database, gửi thông báo và xử lý công việc nền, cách tổ chức ấy nhanh chóng khiến mã khó hiểu, khó kiểm thử và khó thay đổi.

**Tổ chức mã nguồn** là xác định mỗi thành phần chịu trách nhiệm gì, có quyền gọi phần nào và phụ thuộc vào phần nào. Trong ứng dụng Spring Boot, bốn nhóm quan trọng là:

- **Service:** thực hiện hoặc điều phối một ca sử dụng và những quy tắc nghiệp vụ liên quan.
- **Adapter:** chuyển các tương tác từ bên ngoài thành lời gọi của ứng dụng, hoặc chuyển yêu cầu của ứng dụng thành lời gọi đến công nghệ bên ngoài.
- **Configuration:** khai báo các bean, kết nối dependency và những giá trị cấu hình môi trường.
- **Thành phần truy cập dữ liệu:** thực hiện thao tác lưu, đọc, cập nhật, xóa dữ liệu qua database hay nguồn lưu trữ khác.

Những vai trò này là **ranh giới trách nhiệm**, không chỉ là tên thư mục hay annotation. Một class có hậu tố Service nhưng tự xử lý HTTP, mở JDBC connection và viết SQL vẫn có quá nhiều trách nhiệm.

## 1. Toàn cảnh một yêu cầu đi qua ứng dụng

Giả sử xây dựng ứng dụng quản lý công việc. Client muốn tạo một nhiệm vụ mới:

~~~http
POST /api/tasks
Content-Type: application/json

{"title":"Học Spring Boot"}
~~~

Ứng dụng cần nhận request, kiểm tra tiêu đề, lưu nhiệm vụ và trả mã định danh. Có thể chia trách nhiệm như sau:

~~~text
Client
   │ HTTP POST /api/tasks
   ▼
TaskController                        ← Adapter đầu vào: HTTP
   │ chuyển JSON thành lời gọi Java
   ▼
TaskService                           ← Service: quy tắc và ca sử dụng
   │ gọi hợp đồng lưu trữ
   ▼
TaskStore                             ← Port: ứng dụng cần khả năng lưu
   ▲
   │ implementation
TaskJpaAdapter                        ← Adapter đầu ra: JPA
   │ chuyển mô hình dữ liệu và gọi thư viện
   ▼
Spring Data JPA Repository            ← Cơ chế truy cập dữ liệu
   │
   ▼
Database

TaskConfiguration                     ← Cấu hình bean, Clock, thuộc tính
   └── tham gia lắp ráp hệ thống lúc khởi động
~~~

**Controller** biết HTTP method, URL, request body và response status. **Service** biết “tạo nhiệm vụ” gồm những bước gì. **TaskStore** mô tả nhu cầu lưu mà không nói tới SQL. **TaskJpaAdapter** biết cách lưu bằng JPA. **Configuration** cung cấp những dependency và giá trị cần thiết khi application context được khởi tạo.

Đây là cách tổ chức theo hướng **ports and adapters**. Một dự án nhỏ cũng có thể dùng cách phân lớp đơn giản hơn: controller → service → Spring Data repository. Hai cách sẽ được so sánh ở phần sau.

## 2. Service: nơi thể hiện ca sử dụng

**Service** đại diện cho thao tác có ý nghĩa đối với ứng dụng, chẳng hạn:

- Tạo nhiệm vụ sau khi kiểm tra dữ liệu.
- Xác nhận đơn hàng khi tồn kho đủ.
- Tính phí giao hàng theo quy tắc giá.
- Phê duyệt yêu cầu theo trạng thái và quyền nghiệp vụ.
- Điều phối lưu dữ liệu và gửi sự kiện sau khi thao tác hoàn thành.

Trong Spring, annotation **@Service** là một dạng chuyên biệt của **@Component**. Class nằm trong vùng component scanning sẽ được đăng ký thành bean và có thể được đưa vào bean khác qua dependency injection:

~~~java
package com.example.tasks.application;

import org.springframework.stereotype.Service;

@Service
public class TitleNormalizer {

    public String normalize(String title) {
        return title == null ? null : title.strip();
    }
}
~~~

Annotation **@Service** giúp container quản lý class; nó **không tự tạo quy tắc nghiệp vụ**. Nội dung các phương thức, hợp đồng của class và cách class phụ thuộc vào những phần khác mới xác định vai trò thật sự.

### Application service và domain service

| Loại | Trách nhiệm | Ví dụ |
|---|---|---|
| **Application service** | Điều phối một ca sử dụng, làm việc với port/repository, ranh giới transaction | CreateTaskService, CheckoutService |
| **Domain service** | Thực hiện quy tắc nghiệp vụ không thuộc riêng một entity nào | PricingPolicy, ShippingPolicy |

Một application service có thể gọi domain service để tính giá, rồi lưu kết quả. Nếu nghiệp vụ đơn giản, bạn không nhất thiết phải tạo hai loại class riêng. Điều quan trọng là biết logic nào thuộc **nghiệp vụ**, logic nào thuộc **cách giao tiếp với công nghệ**.

### Service thường không nên làm gì?

- Trả trực tiếp **ResponseEntity**, tự chọn HTTP status code hoặc đọc **HttpServletRequest** nếu đó chỉ là nghiệp vụ thông thường.
- Tự viết SQL hoặc mở kết nối database khi persistence đã có thành phần riêng.
- Tự tạo các dependency mà Spring có thể inject, khiến việc thay thế và kiểm thử khó hơn.
- Đọc chuỗi cấu hình ở nhiều vị trí bằng những tên khóa rời rạc.
- Chứa tất cả nghiệp vụ trong một **CommonService** khổng lồ.

Service có giá trị khi thể hiện một **ca sử dụng rõ ràng** hoặc một nhóm quy tắc liên quan, chứ không phải lớp chuyển tiếp được sinh ra cho đủ số tầng.

## 3. Adapter: ranh giới giao tiếp với bên ngoài

**Adapter** chuyển đổi cách bên ngoài tương tác thành hợp đồng mà ứng dụng hiểu, hoặc hiện thực một hợp đồng để ứng dụng giao tiếp với công nghệ bên ngoài.

### Adapter đầu vào

Adapter đầu vào nhận tín hiệu làm bắt đầu công việc:

| Adapter | Tín hiệu | Ví dụ |
|---|---|---|
| REST controller | HTTP request | POST /api/tasks |
| CLI runner | Lệnh và tham số terminal | Import một file CSV |
| Message listener | Message từ queue/broker | Xử lý sự kiện đơn hàng |
| Scheduled job | Lịch định kỳ | Tạo báo cáo mỗi đêm |

Các adapter đầu vào khác nhau có thể gọi cùng **TaskService**. Khi thay một lệnh terminal bằng endpoint HTTP, quy tắc tạo nhiệm vụ không nhất thiết phải viết lại.

### Adapter đầu ra

Adapter đầu ra giúp ứng dụng sử dụng tài nguyên hoặc dịch vụ bên ngoài:

| Ứng dụng cần | Port / hợp đồng | Adapter hiện thực |
|---|---|---|
| Lưu nhiệm vụ | TaskStore | JPA, JDBC, file storage |
| Gửi email | NotificationSender | SMTP, email provider API |
| Lấy tỷ giá | ExchangeRateProvider | HTTP client |
| Lưu tài liệu | FileStorage | Filesystem, object storage |
| Phát sự kiện | EventPublisher | Kafka, RabbitMQ |

Tên class không nhất thiết phải kết thúc bằng **Adapter**. Bạn có thể gặp tên **EmailGateway**, **JpaTaskStore** hoặc **ExternalPaymentClient**. “Adapter” mô tả trách nhiệm thực tế của chúng.

### Port là gì?

**Port** là một hợp đồng ứng dụng dùng để mô tả khả năng nó cần, thường được viết thành Java interface:

~~~java
package com.example.tasks.application;

import java.time.Instant;
import java.util.Optional;
import com.example.tasks.domain.Task;

public interface TaskStore {
    Task save(String title, Instant createdAt);
    Optional<Task> findById(Long id);
}
~~~

Service phụ thuộc vào interface **TaskStore**, không phụ thuộc trực tiếp vào **JpaRepository** hay câu SQL. Một adapter JPA có thể **implements TaskStore**:

~~~text
TaskService ──► TaskStore (interface)
                     ▲
                     │ implements
               TaskJpaAdapter
                     │
                     ▼
               Spring Data JPA
~~~

Trong cách này, code nghiệp vụ và hợp đồng lưu trữ hướng vào bên trong; phần kỹ thuật hiện thực hợp đồng từ phía ngoài. Đây là nguyên tắc **đảo ngược phụ thuộc**.

Không cần ép mọi lớp đều phải có interface. Port hữu ích khi muốn tách hợp đồng ứng dụng khỏi một công nghệ cụ thể hoặc có nhiều adapter có thể thay thế.

## 4. Thành phần truy cập dữ liệu: lưu gì và lưu bằng cách nào?

Một thành phần truy cập dữ liệu thường giải quyết việc tạo, tìm, cập nhật và xóa bản ghi. Với Spring Data JPA, giao diện mở rộng **JpaRepository** đã cung cấp các thao tác phổ biến như **save**, **findById**, **findAll** và **deleteById**.

~~~java
package com.example.tasks.adapter.persistence;

import org.springframework.data.jpa.repository.JpaRepository;

public interface SpringDataTaskRepository
        extends JpaRepository<TaskEntity, Long> {
}
~~~

Spring Data tạo implementation/proxy của repository tại runtime. Bạn không phải tự viết class triển khai những thao tác CRUD cơ bản, nhưng vẫn phải khai báo entity, cấu hình datasource và tổ chức transaction khi phù hợp.

### Phân biệt ba loại mô hình dữ liệu

| Loại | Vai trò | Ví dụ |
|---|---|---|
| **HTTP DTO** | Hợp đồng request/response giữa client và API | CreateTaskRequest, TaskResponse |
| **Domain model** | Dữ liệu và quy tắc mà nghiệp vụ quan tâm | Task |
| **Persistence entity** | Ánh xạ dữ liệu vào bảng, cột và quan hệ database | TaskEntity |

Một dự án CRUD đơn giản có thể dùng chung một số kiểu dữ liệu. Khi hệ thống lớn hơn, tách DTO khỏi entity giúp tránh làm hợp đồng HTTP phụ thuộc vào schema database, hạn chế lộ trường không mong muốn và kiểm soát cách biểu diễn dữ liệu.

### @Repository và @Service khác nhau thế nào?

**@Repository** cũng là một dạng chuyên biệt của **@Component**, nhưng nó biểu thị vai trò truy cập dữ liệu. Trong những trường hợp được Spring hỗ trợ và cấu hình phù hợp, annotation này còn liên quan đến cơ chế chuyển đổi exception của persistence sang hệ phân cấp **DataAccessException**.

**@Service** biểu thị nghiệp vụ hoặc ca sử dụng. Cả hai có thể nhận dependency qua constructor. Việc đổi annotation chỉ để chương trình khởi động thành công không giải quyết được vấn đề phân chia trách nhiệm.

## 5. Configuration: lắp ráp bean và quản lý thông số

**Configuration** xác định cách các thành phần được tạo, kết nối và tùy chỉnh. Spring Boot có hai nhóm cơ chế thường gặp:

1. **Cấu hình bằng Java:** @Configuration, @Bean, @EnableConfigurationProperties và những khai báo liên quan.
2. **Cấu hình bên ngoài mã nguồn:** application.yml, application.properties, biến môi trường, tham số dòng lệnh và các nguồn khác.

Class gắn **@Service**, **@Component** và **@Repository** thường được Spring tìm qua component scanning. Nhưng các đối tượng từ thư viện ngoài hoặc Java chuẩn, ví dụ **java.time.Clock**, có thể cần khai báo bean riêng:

~~~java
package com.example.tasks.config;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ClockConfiguration {

    @Bean
    public Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

Service có thể inject **Clock** qua constructor thay vì gọi thẳng **Instant.now()**. Khi cần kiểm thử, một **Clock.fixed(...)** có thể tạo thời điểm cố định, tránh phụ thuộc vào thời gian thực.

### Gom cấu hình bằng @ConfigurationProperties

Ví dụ, giới hạn tiêu đề công việc được định nghĩa trong **application.yml**:

~~~yaml
app:
  tasks:
    max-title-length: 120
~~~

Tạo lớp cấu hình:

~~~java
package com.example.tasks.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.tasks")
public record TaskSettings(int maxTitleLength) {
}
~~~

Đăng ký cấu hình và bean khác:

~~~java
package com.example.tasks.config;

import java.time.Clock;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(TaskSettings.class)
public class TaskConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

Spring Boot bind khóa **app.tasks.max-title-length** vào **TaskSettings.maxTitleLength** theo quy tắc relaxed binding. Service chỉ biết đối tượng cấu hình kiểu Java, không phải ghi nhớ tên khóa dạng chuỗi.

Hai class **ClockConfiguration** và **TaskConfiguration** là **hai cách minh họa khác nhau để đăng ký Clock**. Trong ví dụ ứng dụng hoàn chỉnh phía dưới, chỉ dùng **TaskConfiguration**, tránh tạo hai bean Clock trùng chức năng.

### Cấu hình không phải nơi xử lý nghiệp vụ

**@Configuration** thích hợp để tạo HTTP client, cấu hình bean Clock, đăng ký properties hoặc tùy chỉnh thành phần hạ tầng. Nó không nên chứa logic tính phí vận chuyển hay quy tắc xét duyệt đơn hàng.

Spring Boot còn có **auto-configuration**: khi có những dependency và thông tin cần thiết, Boot tự chuẩn bị nhiều bean mặc định, ví dụ các thành phần MVC hoặc JPA. Cấu hình Java của ứng dụng chỉ nên bổ sung hoặc tùy chỉnh phần thật sự cần.

## 6. Xây dựng ví dụ nhỏ có đủ bốn vai trò

Ta sẽ ghép các thành phần vào một ứng dụng tạo và đọc nhiệm vụ. Ví dụ này dùng **Java, Spring Web, Spring Data JPA và H2 Database**. Trên Spring Initializr, chọn các dependency tương ứng:

- **Spring Web** để viết REST controller.
- **Spring Data JPA** để truy cập database qua JPA.
- **H2 Database** để thử nghiệm với cơ sở dữ liệu trong bộ nhớ.

Đặt class chính trong package **com.example.tasks**, với cấu trúc:

~~~text
src/main/java/com/example/tasks/
├── TaskApplication.java
├── domain/
│   └── Task.java
├── application/
│   ├── TaskStore.java
│   ├── TaskService.java
│   └── TaskNotFoundException.java
├── adapter/
│   ├── web/
│   │   ├── TaskController.java
│   │   └── TaskErrorHandler.java
│   └── persistence/
│       ├── TaskEntity.java
│       ├── SpringDataTaskRepository.java
│       └── TaskJpaAdapter.java
└── config/
    ├── TaskSettings.java
    └── TaskConfiguration.java

src/main/resources/
└── application.yml
~~~

Đặt class **@SpringBootApplication** ở package gốc giúp component scanning mặc định tìm các thành phần trong package con.

### 6.1. Class khởi động

File **TaskApplication.java**:

~~~java
package com.example.tasks;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TaskApplication {

    public static void main(String[] args) {
        SpringApplication.run(TaskApplication.class, args);
    }
}
~~~

Class này tạo ứng dụng Spring Boot, không trực tiếp làm nghiệp vụ hay truy cập database.

### 6.2. Domain model

File **domain/Task.java**:

~~~java
package com.example.tasks.domain;

import java.time.Instant;

public record Task(Long id, String title, Instant createdAt) {
}
~~~

Trong ví dụ cơ bản, **Task** là record bất biến chứa dữ liệu nghiệp vụ. Nó không phải entity JPA và không chứa annotation HTTP. Trong hệ thống lớn, domain model có thể chứa hành vi và bất biến phong phú hơn.

### 6.3. Port truy cập dữ liệu

File **application/TaskStore.java**:

~~~java
package com.example.tasks.application;

import java.time.Instant;
import java.util.Optional;
import com.example.tasks.domain.Task;

public interface TaskStore {

    Task save(String title, Instant createdAt);

    Optional<Task> findById(Long id);
}
~~~

Port chỉ diễn đạt nhu cầu của ứng dụng. Nó không cần import **JpaRepository**, **EntityManager** hay một JDBC driver.

### 6.4. Service

File **application/TaskNotFoundException.java**:

~~~java
package com.example.tasks.application;

public class TaskNotFoundException extends RuntimeException {

    public TaskNotFoundException(long id) {
        super("Không tìm thấy nhiệm vụ có id=" + id);
    }
}
~~~

File **application/TaskService.java**:

~~~java
package com.example.tasks.application;

import java.time.Clock;
import java.time.Instant;

import com.example.tasks.config.TaskSettings;
import com.example.tasks.domain.Task;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TaskService {

    private final TaskStore store;
    private final Clock clock;
    private final TaskSettings settings;

    public TaskService(
            TaskStore store,
            Clock clock,
            TaskSettings settings) {
        this.store = store;
        this.clock = clock;
        this.settings = settings;
    }

    @Transactional
    public Task create(String title) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException(
                    "Tiêu đề nhiệm vụ không được để trống");
        }

        String normalized = title.strip();
        if (normalized.length() > settings.maxTitleLength()) {
            throw new IllegalArgumentException(
                    "Tiêu đề vượt quá "
                    + settings.maxTitleLength() + " ký tự");
        }

        return store.save(normalized, Instant.now(clock));
    }

    @Transactional(readOnly = true)
    public Task get(long id) {
        return store.findById(id)
                .orElseThrow(() -> new TaskNotFoundException(id));
    }
}
~~~

Service dùng ba dependency do Spring inject:

- **TaskStore** để lưu/truy vấn nhiệm vụ mà không phụ thuộc trực tiếp JPA.
- **Clock** để lấy thời gian qua dependency có thể thay thế.
- **TaskSettings** để đọc giới hạn đã cấu hình.

**@Transactional** đặt ranh giới giao dịch quanh ca sử dụng tạo nhiệm vụ. **@Transactional(readOnly = true)** mô tả thao tác đọc và cung cấp gợi ý tối ưu hóa cho transaction manager/persistence provider; nó không phải cơ chế bảo mật ngăn mọi lệnh ghi.

Spring thường áp dụng transaction qua proxy. Nếu một phương thức gọi trực tiếp phương thức khác **trong cùng object**, lời gọi đó có thể không đi qua proxy và không kích hoạt transaction annotation theo cách mong đợi. Trong ví dụ này, web controller gọi service do Spring quản lý, phù hợp với cách dùng thông thường.

### 6.5. Persistence entity

File **adapter/persistence/TaskEntity.java**:

~~~java
package com.example.tasks.adapter.persistence;

import java.time.Instant;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "task_items")
public class TaskEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String title;

    @Column(nullable = false)
    private Instant createdAt;

    protected TaskEntity() {
        // Constructor cho JPA.
    }

    public TaskEntity(String title, Instant createdAt) {
        this.title = title;
        this.createdAt = createdAt;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
~~~

**TaskEntity** là mô hình lưu trữ. Annotation **jakarta.persistence** mô tả bảng và cột. Lưu ý giới hạn **length = 120** cần phù hợp với giới hạn ở cấu hình nghiệp vụ; khi triển khai thực tế, cần quản lý tính nhất quán giữa schema và validation.

### 6.6. Spring Data repository và persistence adapter

File **adapter/persistence/SpringDataTaskRepository.java**:

~~~java
package com.example.tasks.adapter.persistence;

import org.springframework.data.jpa.repository.JpaRepository;

public interface SpringDataTaskRepository
        extends JpaRepository<TaskEntity, Long> {
}
~~~

File **adapter/persistence/TaskJpaAdapter.java**:

~~~java
package com.example.tasks.adapter.persistence;

import java.time.Instant;
import java.util.Optional;

import com.example.tasks.application.TaskStore;
import com.example.tasks.domain.Task;
import org.springframework.stereotype.Repository;

@Repository
public class TaskJpaAdapter implements TaskStore {

    private final SpringDataTaskRepository repository;

    public TaskJpaAdapter(SpringDataTaskRepository repository) {
        this.repository = repository;
    }

    @Override
    public Task save(String title, Instant createdAt) {
        TaskEntity entity = new TaskEntity(title, createdAt);
        TaskEntity saved = repository.save(entity);
        return toDomain(saved);
    }

    @Override
    public Optional<Task> findById(Long id) {
        return repository.findById(id).map(this::toDomain);
    }

    private Task toDomain(TaskEntity entity) {
        return new Task(
                entity.getId(),
                entity.getTitle(),
                entity.getCreatedAt());
    }
}
~~~

Adapter hiện thực hợp đồng **TaskStore**, gọi Spring Data và chuyển **TaskEntity** sang **Task**. Nếu đổi cách lưu trữ, code service có thể giữ nguyên miễn adapter mới đáp ứng cùng hợp đồng. Ví dụ giả định chỉ có **một bean** hiện thực TaskStore; nếu có nhiều implementation, cần lựa chọn rõ bằng **@Qualifier**, **@Primary** hoặc cấu hình tương đương.

### 6.7. Configuration và database

File **config/TaskSettings.java**:

~~~java
package com.example.tasks.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.tasks")
public record TaskSettings(int maxTitleLength) {
}
~~~

File **config/TaskConfiguration.java**:

~~~java
package com.example.tasks.config;

import java.time.Clock;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(TaskSettings.class)
public class TaskConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

File **src/main/resources/application.yml**:

~~~yaml
app:
  tasks:
    max-title-length: 120

spring:
  datasource:
    url: jdbc:h2:mem:taskdb
    driver-class-name: org.h2.Driver
    username: sa
    password:
  jpa:
    hibernate:
      ddl-auto: create-drop
~~~

**H2 in-memory** phục vụ thực hành: dữ liệu không bền vững khi tiến trình kết thúc. **ddl-auto: create-drop** cho Hibernate tạo schema khi khởi động và xóa schema khi đóng context, chỉ thích hợp cho môi trường thử nghiệm có thể bỏ dữ liệu. Ứng dụng thật thường dùng migration có kiểm soát như Flyway hoặc Liquibase.

Các khóa dưới **spring.datasource** điều khiển kết nối database; **spring.jpa** liên quan JPA/Hibernate; **app.tasks** là namespace cấu hình của ứng dụng. Boot tận dụng starter và auto-configuration để tạo những thành phần kỹ thuật phù hợp; **TaskConfiguration** bổ sung Clock và đăng ký TaskSettings.

### 6.8. Web adapter

File **adapter/web/TaskController.java**:

~~~java
package com.example.tasks.adapter.web;

import java.net.URI;
import java.time.Instant;

import com.example.tasks.application.TaskService;
import com.example.tasks.domain.Task;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/tasks")
public class TaskController {

    private final TaskService service;

    public TaskController(TaskService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<TaskResponse> create(
            @RequestBody CreateTaskRequest request) {
        Task created = service.create(request.title());
        URI location = URI.create("/api/tasks/" + created.id());

        return ResponseEntity.created(location)
                .body(TaskResponse.from(created));
    }

    @GetMapping("/{id}")
    public TaskResponse get(@PathVariable long id) {
        return TaskResponse.from(service.get(id));
    }

    public record CreateTaskRequest(String title) {
    }

    public record TaskResponse(
            Long id,
            String title,
            Instant createdAt) {

        static TaskResponse from(Task task) {
            return new TaskResponse(
                    task.id(),
                    task.title(),
                    task.createdAt());
        }
    }
}
~~~

Hai DTO được viết thành record lồng trong controller để dễ theo dõi ví dụ; dự án lớn có thể tách chúng thành file riêng. Controller chuyển request thành lời gọi service và chuyển kết quả thành HTTP response. **ResponseEntity.created(...)** thể hiện HTTP **201 Created** và header **Location** trỏ đến nhiệm vụ vừa tạo.

Để chuyển exception nghiệp vụ thành HTTP response, thêm file **adapter/web/TaskErrorHandler.java**:

~~~java
package com.example.tasks.adapter.web;

import com.example.tasks.application.TaskNotFoundException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class TaskErrorHandler {

    @ExceptionHandler(IllegalArgumentException.class)
    ProblemDetail invalidInput(IllegalArgumentException exception) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST, exception.getMessage());
    }

    @ExceptionHandler(TaskNotFoundException.class)
    ProblemDetail taskNotFound(TaskNotFoundException exception) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND, exception.getMessage());
    }
}
~~~

Với cách này, service không phải import **HttpStatus**. Adapter web quyết định lỗi nghiệp vụ nào được chuyển thành HTTP 400 hoặc 404. Khi ứng dụng có nhiều loại lỗi đầu vào, nên dùng kiểu exception nghiệp vụ riêng thay vì để một handler bắt mọi **IllegalArgumentException**.

### 6.9. Chạy thử và quan sát

Chạy project bằng **bootRun** nếu dùng Gradle hoặc **spring-boot:run** nếu dùng Maven. Với cấu hình web mặc định, server thường dùng **localhost:8080**.

Trên Linux/macOS:

~~~bash
curl -i -X POST http://localhost:8080/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"title":"Học Spring Boot"}'
~~~

Trên Windows PowerShell:

~~~powershell
$body = @{ title = "Học Spring Boot" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:8080/api/tasks" -Method Post -ContentType "application/json" -Body $body
~~~

Phản hồi minh họa:

~~~http
HTTP/1.1 201 Created
Location: /api/tasks/1
Content-Type: application/json

{"id":1,"title":"Học Spring Boot","createdAt":"2026-01-01T00:00:00Z"}
~~~

**id** và **createdAt** ở trên chỉ minh họa định dạng; giá trị thật do database và thời gian thực thi quyết định. Có thể đọc lại:

~~~bash
curl http://localhost:8080/api/tasks/1
~~~

Nếu id tồn tại, ứng dụng trả dữ liệu; nếu không tồn tại, service ném **TaskNotFoundException** và adapter web trả **404**. Khi tiêu đề rỗng hoặc vượt giới hạn, service từ chối tạo và adapter web trả **400**.

Theo dõi từng phần trong POST:

| Bước | Class | Vai trò |
|---|---|---|
| Nhận HTTP | TaskController | Parse request DTO, gọi service |
| Xử lý nghiệp vụ | TaskService | Kiểm tra tiêu đề, lấy thời gian, điều phối transaction |
| Giao ước lưu trữ | TaskStore | Mô tả khả năng save/findById |
| Kết nối JPA | TaskJpaAdapter | Ánh xạ TaskEntity, gọi repository |
| Làm việc với database | SpringDataTaskRepository | Thực hiện thao tác qua JPA |
| Trả HTTP | TaskController | Tạo response DTO, mã 201 và Location |
| Lắp ráp dependency | TaskConfiguration | Tạo Clock, đăng ký TaskSettings khi khởi động |

**Configuration không nằm giữa controller và database như một bước nghiệp vụ mỗi lần có request**. Nó chủ yếu giúp các bean sẵn sàng trong ApplicationContext.

## 7. Hướng phụ thuộc quan trọng hơn tên thư mục

Trong ví dụ:

- **domain/Task.java** không import Spring MVC hoặc JPA.
- **application/TaskStore.java** không import Spring Data.
- **TaskService** phụ thuộc vào port, model và cấu hình, không biết tên bảng.
- **adapter/persistence/** phụ thuộc vào port và model để hiện thực persistence.
- **adapter/web/** phụ thuộc vào service để kích hoạt ca sử dụng.

~~~text
Web adapter ──► Application service ──► Domain
                         │
                         ▼
                    TaskStore port
                         ▲
                         │
                    JPA adapter ──► Spring Data ──► Database

Spring container / configuration lắp ráp các bean.
~~~

Trong ví dụ, application service vẫn sử dụng annotation Spring như **@Service**, **@Transactional**. Đây là mức tách biệt vừa phải: nghiệp vụ tránh phụ thuộc trực tiếp vào HTTP và JPA nhưng vẫn dùng Spring cho quản lý bean/transaction. Nếu cần phần lõi thuần Java nghiêm ngặt hơn, có thể dời những concern hạ tầng này ra ngoài; đổi lại cấu trúc sẽ phức tạp hơn.

### Tổ chức theo tầng hay theo feature?

**Theo tầng kỹ thuật:**

~~~text
com.example.app/
├── controller/
│   ├── TaskController.java
│   └── UserController.java
├── service/
│   ├── TaskService.java
│   └── UserService.java
├── repository/
│   ├── TaskRepository.java
│   └── UserRepository.java
└── config/
~~~

**Theo tính năng:**

~~~text
com.example.app/
├── task/
│   ├── application/
│   ├── domain/
│   └── adapter/
├── user/
│   ├── application/
│   ├── domain/
│   └── adapter/
└── shared/
~~~

Cấu trúc theo tầng dễ tiếp cận khi có ít class. Khi có nhiều tính năng, tổ chức theo feature đặt những file cùng nghiệp vụ gần nhau, làm rõ quyền sở hữu và hạn chế thư mục **service/** phát triển quá lớn. Cách đặt tên không quan trọng bằng việc có **hướng phụ thuộc nhất quán** và trách nhiệm rõ ràng.

## 8. Trường hợp đơn giản: service gọi trực tiếp JpaRepository

Không phải mỗi project đều cần một port và adapter riêng. Với một ứng dụng CRUD nhỏ, mô hình:

~~~text
Controller → Service → JpaRepository → Database
~~~

có thể đủ rõ. Ví dụ giản lược, với **TaskRepository** kế thừa JpaRepository và **TaskNotFoundException** đã được định nghĩa:

~~~java
@Service
public class TaskService {

    private final TaskRepository repository;

    public TaskService(TaskRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public TaskEntity get(Long id) {
        return repository.findById(id)
                .orElseThrow(() -> new TaskNotFoundException(id));
    }
}
~~~

Ưu điểm là ít interface và mapper. Nhược điểm là service phụ thuộc trực tiếp vào Spring Data và JPA entity. Nếu cần thay persistence hoặc kiểm thử nghiệp vụ hoàn toàn tách khỏi database, việc này có thể làm thay đổi nhiều lớp hơn.

**Ports and adapters** đem lại khả năng cô lập công nghệ nhưng có chi phí thêm file và mapping. Hãy chọn theo độ phức tạp thật sự, không phải vì mọi dự án đều cần cấu trúc giống nhau.

## 9. Transaction thuộc trách nhiệm nào?

Khi một ca sử dụng gồm nhiều thao tác dữ liệu cần cùng thành công hoặc cùng rollback, **application service** thường là nơi phù hợp để xác định ranh giới transaction.

~~~text
CheckoutService.checkout(...)
  ├── Kiểm tra hàng hóa
  ├── Trừ tồn kho
  ├── Ghi đơn hàng
  └── Hoàn tất giao dịch
~~~

Ví dụ minh họa vị trí annotation:

~~~java
@Service
public class CheckoutService {

    @Transactional
    public void checkout(CheckoutCommand command) {
        // Các thao tác database thuộc cùng một ca sử dụng.
    }
}
~~~

Đoạn trên dùng **CheckoutCommand** giả định để minh họa ranh giới transaction, không phải class thuộc ứng dụng quản lý nhiệm vụ đã xây dựng.

Những điểm quan trọng:

- **@Transactional** làm việc qua transaction manager tương ứng; nó không tự tạo transaction phân tán bao trùm database, email và HTTP API.
- Mặc định Spring thường rollback với **RuntimeException** và **Error**; checked exception có quy tắc khác nếu không cấu hình thêm.
- **readOnly = true** là chỉ dẫn cho hạ tầng transaction, không phải quy tắc bảo mật.
- Khi cần vừa ghi database vừa gửi message, phải thiết kế xử lý thất bại và nhất quán phù hợp, chẳng hạn transactional outbox hoặc cơ chế retry có kiểm soát.

Transaction đi cùng **ca sử dụng** thường tự nhiên hơn transaction gắn cứng với controller, vì cùng nghiệp vụ có thể được gọi từ web, CLI hoặc worker.

## 10. Dependency injection kết nối các phần như thế nào?

~~~text
Spring ApplicationContext
  ├── TaskController
  │      └── cần TaskService
  ├── TaskService
  │      ├── cần TaskStore
  │      ├── cần Clock
  │      └── cần TaskSettings
  ├── TaskJpaAdapter (implements TaskStore)
  │      └── cần SpringDataTaskRepository
  ├── SpringDataTaskRepository (proxy)
  ├── Clock (từ @Bean)
  └── TaskSettings (từ @ConfigurationProperties)
~~~

**Constructor injection** công khai dependency của class. Với một constructor duy nhất, Spring thông thường không yêu cầu **@Autowired**. Nếu thiếu bean cần thiết, có nhiều bean cùng kiểu không có quy tắc lựa chọn, hoặc có phụ thuộc vòng tròn, khởi tạo ApplicationContext có thể thất bại.

Ví dụ **TaskService → NotificationService → TaskService** là dấu hiệu nên xem lại luồng sở hữu nghiệp vụ, thay vì mặc định bật lazy initialization cho mọi bean để che vòng lặp.

## 11. Một service có thể được gọi từ nhiều adapter

Giả sử muốn tạo một nhiệm vụ khi CLI chạy. Một adapter đầu vào khác có thể gọi lại **TaskService**:

~~~java
@Component
class TaskImportCommand implements ApplicationRunner {

    private final TaskService tasks;

    TaskImportCommand(TaskService tasks) {
        this.tasks = tasks;
    }

    @Override
    public void run(ApplicationArguments args) {
        tasks.create("Nhiệm vụ nhập từ CLI");
    }
}
~~~

Hoặc một job theo lịch:

~~~java
@Component
class DailyTaskJob {

    private final TaskService tasks;

    DailyTaskJob(TaskService tasks) {
        this.tasks = tasks;
    }

    @Scheduled(cron = "0 0 8 * * *", zone = "Asia/Ho_Chi_Minh")
    void createDailyTask() {
        tasks.create("Kiểm tra công việc đầu ngày");
    }
}
~~~

Hai ví dụ bổ sung này cần các import tương ứng; scheduler còn cần bật **@EnableScheduling**. Chỉ thêm chúng nếu thực sự muốn ứng dụng chạy những công việc đó. Điểm chính là **quy tắc kiểm tra và lưu vẫn nằm ở service**, bất kể tín hiệu bắt đầu đến từ HTTP, CLI hay lịch.

## 12. Kiểm thử theo trách nhiệm

Tổ chức mã rõ ràng giúp thiết kế kiểm thử đúng phạm vi:

| Thành phần | Điều cần xác nhận | Cách tiếp cận thường dùng |
|---|---|---|
| **Service** | Quy tắc tiêu đề, lỗi nghiệp vụ, điều phối | Fake/mock TaskStore và Clock cố định |
| **Web adapter** | Mapping, JSON, HTTP status, error response | Test lớp web bằng MockMvc hoặc cấu hình tương ứng |
| **Persistence adapter** | Ánh xạ entity, truy vấn và ràng buộc dữ liệu | Integration test với database phù hợp |
| **Configuration** | Binding giá trị, tạo bean, chọn đúng bean | Test Spring context có cấu hình kiểm soát được |
| **Luồng hoàn chỉnh** | Request được lưu và có thể đọc lại | Integration test với thành phần cần thiết |

Một service sử dụng **TaskStore** dễ kiểm tra khi database chưa sẵn sàng: có thể thay port bằng implementation trong bộ nhớ. Ngược lại, lỗi ánh xạ entity thuộc phạm vi persistence adapter sẽ phù hợp hơn với integration test.

Không cần viết test chỉ để chứng minh một getter gọi một getter khác. Nên tập trung vào **hành vi đáng tin cậy**: tiêu đề rỗng bị từ chối, nhiệm vụ hợp lệ được lưu, id không tồn tại trả 404 và transaction xử lý đúng yêu cầu.

## 13. Những lỗi tổ chức mã thường gặp

### Controller ôm toàn bộ công việc

~~~java
@PostMapping("/orders")
public ResponseEntity<?> create(@RequestBody OrderRequest request) {
    // Kiểm tra mọi quy tắc nghiệp vụ.
    // Viết SQL, tính tiền, gửi email và quyết định retry.
    // Trả HTTP response.
}
~~~

Nếu controller làm quá nhiều việc, khi cần xử lý cùng nghiệp vụ từ queue hoặc CLI, bạn sẽ khó tái sử dụng. Hãy để adapter HTTP lo giao thức, service lo ca sử dụng, adapter đầu ra lo tích hợp.

### Service chỉ chuyển tiếp vô nghĩa

~~~java
public TaskEntity save(TaskEntity entity) {
    return repository.save(entity);
}
~~~

Không phải mọi phương thức chuyển tiếp đều sai, nhưng nếu toàn bộ service chỉ nhân bản CRUD mà không thể hiện ca sử dụng, hãy xem lại liệu tầng đó có giá trị thực tế không.

### Repository chứa quy tắc nghiệp vụ không thuộc dữ liệu

Repository có thể thực hiện truy vấn phức tạp, nhưng các quyết định như “khách VIP được giảm bao nhiêu” hoặc “đơn hàng có được phê duyệt không” thường thuộc domain/application. Không nên tự động đẩy mọi nghiệp vụ xuống câu SQL chỉ vì có thể viết được.

### Configuration trở thành nơi chứa mọi tiện ích

Class **AppConfig** quá lớn, vừa tạo bean vừa đọc file, tính giá và gửi HTTP request, làm mờ ranh giới giữa lắp ráp và xử lý. Configuration nên tập trung vào tạo bean và cấu hình.

### Trả thẳng JPA entity qua API

Entity có thể chứa quan hệ lazy-loading hoặc trường không dành cho client. Dùng DTO tường minh giúp hợp đồng HTTP độc lập hơn với schema và kiểm soát dữ liệu trả ra.

### Tạo interface cho mọi class dù không có ranh giới cần bảo vệ

Port hữu ích khi tránh phụ thuộc công nghệ hoặc có nhiều adapter, nhưng sinh interface cho tất cả class mà không có nhu cầu có thể khiến việc lần theo mã phức tạp hơn.

### Đặt class khởi động sai vùng component scanning

Nếu class **@SpringBootApplication** nằm dưới package con trong khi service/controller ở ngoài vùng scan mặc định, Spring có thể không tạo bean. Cách thường gặp là đặt class khởi động ở package gốc chứa những package con của ứng dụng.

## 14. Xác định trách nhiệm bằng câu hỏi

| Câu hỏi | Nơi xử lý thường hợp lý |
|---|---|
| “Đường dẫn HTTP nào nhận request? Trả 201 hay 404?” | Web adapter / Controller |
| “Lệnh CLI nhận tham số và gọi nghiệp vụ ra sao?” | CLI adapter / Runner |
| “Khi tạo đơn hàng phải làm những bước nào?” | Application service |
| “Quy tắc giá và giảm giá được xác định thế nào?” | Domain model / Domain service |
| “Ứng dụng cần khả năng lưu dữ liệu qua hợp đồng nào?” | Output port |
| “Chuyển domain model thành JPA entity ở đâu?” | Persistence adapter |
| “Viết truy vấn database thế nào?” | Repository / Data access |
| “URL API ngoài, timeout, giới hạn tiêu đề cấu hình ở đâu?” | Configuration properties |
| “Tạo Clock hoặc HTTP client dùng chung như thế nào?” | @Configuration / @Bean |

Những câu hỏi này hữu ích hơn việc chỉ nhìn vào tên class. **OrderService** trả **ResponseEntity** đang mang trách nhiệm HTTP; **OrderRepository** tự gửi email đang mang thêm trách nhiệm tích hợp bên ngoài.

## 15. Nguyên tắc để tiếp tục phát triển dự án

**Giữ controller mỏng và rõ.** Controller lo request/response, còn service lo hành động nghiệp vụ. Nếu controller phức tạp lên theo số quy tắc kinh doanh, đó là tín hiệu nên xem lại ranh giới.

**Đặt transaction theo ca sử dụng khi phù hợp.** Nhiều cập nhật dữ liệu có cùng ý nghĩa nghiệp vụ thường cần cùng ranh giới transaction, thay vì từng adapter tự quyết định.

**Ưu tiên constructor injection.** Class khai báo rõ dependency, dễ thay thế khi test và dễ phát hiện thiếu bean lúc startup.

**Tách tích hợp ngoài ở những ranh giới có thể thay đổi.** Database, email provider, payment gateway, message broker thường thay đổi độc lập với quy tắc nghiệp vụ.

**Gom cấu hình theo chức năng.** Đối tượng cấu hình có tên rõ ràng giúp tránh rải các khóa dạng chuỗi trong toàn bộ mã. Thông tin nhạy cảm cần được đưa vào nguồn secret phù hợp, không nhúng cứng trong repository.

**Tránh phụ thuộc vòng và package dùng chung vô hạn.** Khi các service gọi lẫn nhau không có hướng rõ, việc thay đổi và kiểm thử sẽ ngày càng khó. Phân chia theo feature giúp xác định chủ sở hữu của một ca sử dụng.

**Chọn mức độ kiến trúc phù hợp.** REST API CRUD nhỏ có thể bắt đầu bằng controller → service → repository. Khi nhu cầu kiểm thử, tái sử dụng hoặc thay công nghệ xuất hiện, có thể tách port và adapter tại ranh giới cần thiết.

## Kết luận

Trong Spring Boot, **service** thực hiện và điều phối ca sử dụng; **adapter** kết nối ứng dụng với HTTP, CLI, scheduler, database hoặc hệ thống ngoài; **configuration** tạo bean và cung cấp cấu hình; **thành phần truy cập dữ liệu** tập trung vào lưu trữ và truy vấn.

Luồng quan trọng cần nhớ là: **adapter đầu vào nhận yêu cầu → service xử lý nghiệp vụ → port/adapter đầu ra truy cập tài nguyên cần thiết → adapter đầu vào trả kết quả**. Configuration giúp các dependency được lắp ráp đúng khi ứng dụng khởi động.

Khi các trách nhiệm này rõ ràng, thêm endpoint mới, chuyển một tác vụ sang worker, thay database hoặc kiểm thử một quy tắc nghiệp vụ ít làm xáo trộn những phần không liên quan. Đó là giá trị thực tế của việc tổ chức mã nguồn theo ranh giới trách nhiệm.

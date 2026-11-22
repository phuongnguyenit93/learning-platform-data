# Docker Compose trong test và lựa chọn theo khả năng hỗ trợ của Spring Boot

**Docker Compose** và **Testcontainers** đều giúp một ứng dụng Spring Boot chạy cùng PostgreSQL, Redis, Kafka hoặc các dịch vụ khác trong Docker, nhưng chúng **không có cùng lifecycle, phạm vi tự động cấu hình hay mức độ cô lập test**. Câu hỏi đúng không chỉ là “có container chạy chưa?”, mà còn là “ai khởi động container, connection URL lấy từ đâu, container sống tới khi nào, test có rollback/cleanup không và CI có hỗ trợ Docker/Compose không?”.

Trong Spring Boot **3.4.x**, có hai cơ chế chính:
- **Spring Boot Docker Compose support** qua dependency **spring-boot-docker-compose**. Nó có thể khám phá Compose file, gọi Docker Compose CLI và tạo **service connection** cho những image được hỗ trợ. Đây trước hết là cơ chế **development-time services**. **Khi chạy tests, mặc định Spring Boot bỏ qua Docker Compose**.
- **Spring Boot Testcontainers support** qua **spring-boot-testcontainers**, Testcontainers Java và **@ServiceConnection**. Container được khai báo gần test hoặc dưới dạng test configuration bean; Spring Boot tự cung cấp connection details cho auto-configuration của ứng dụng.

**Đáp án lựa chọn:** Với integration tests cần database thật, tập trung vào một test class/context, **Testcontainers + @ServiceConnection** thường là mặc định tốt nhất trên Spring Boot 3.1+; với một **Compose stack nhiều service đã chuẩn hóa** hoặc khi chính Compose orchestration là mục tiêu, có thể bật Docker Compose trong tests **một cách tường minh**. Khi runner không có Docker/Compose, cần một loại test phù hợp khác (unit/mock/embedded DB) hoặc cấp Docker cho CI; **không âm thầm biến test PostgreSQL thành H2 rồi coi như đã kiểm thử PostgreSQL**.

Bài dùng **Java 17, Spring Boot 3.4.5, Gradle, JUnit Jupiter, Spring Data JPA và PostgreSQL 16**. Hai bộ integration tests cùng dùng một entity/repository, nhưng khởi tạo database theo hai lựa chọn khác nhau: **Boot-managed Compose** và **Testcontainers-managed PostgreSQL**. Mỗi test dùng unique business key và rollback để tránh phụ thuộc dữ liệu còn lại. Các lệnh là hướng dẫn để chạy thực tế, không phải stdout đã quan sát trong khi biên soạn.

## 1. Đừng nhầm bốn khái niệm

| Khái niệm | Định nghĩa | Ai quản lý? |
| --- | --- | --- |
| **Docker Engine/Daemon** | Hạ tầng chạy containers | Docker Desktop, Docker Engine hoặc môi trường CI |
| **Docker Compose CLI** | Công cụ đọc file YAML rồi quản lý nhiều containers/networks/volumes | Người dùng, CI hoặc Spring Boot Docker Compose support |
| **Spring Boot Docker Compose integration** | Tự phát hiện/gọi Compose, chờ readiness và tạo service connection beans cho supported images | Spring Boot khi dependency có mặt và tính năng được bật |
| **Testcontainers Java** | API Java/JUnit quản lý container lifecycle cho integration tests | Testcontainers extension hoặc Spring bean lifecycle |
| **@ServiceConnection** | Gợi ý Spring Boot tạo ConnectionDetails beans từ container đã khai báo | Spring Boot testcontainers auto-configuration |

**Docker Compose không tự trở thành Testcontainers** chỉ vì nó khởi động PostgreSQL. Và **@ServiceConnection không bắt đầu một container bất kỳ nếu thiếu declaration/lifecycle thích hợp**; nó giúp Spring Boot biết kết nối thế nào tới dịch vụ do container cung cấp.

### Kết nối service khác việc kiểm thử service

Một test có thể chứng minh ứng dụng kết nối PostgreSQL và chạy query thành công, nhưng chưa chứng minh được toàn bộ Compose YAML gồm Kafka, Redis, healthchecks, networks và production credentials. Hãy viết assertion cho những dịch vụ thực sự nằm trong **test contract**, không suy từ việc một database lên thành công rằng mọi hệ thống ngoài đã sẵn sàng.

## 2. Spring Boot hỗ trợ Docker Compose từ phiên bản nào?

Để quyết định đúng cần biết **Spring Boot version thực tế**, thay vì sao chép một bài hướng dẫn dành cho version khác.

| Dòng Spring Boot | Boot-managed Docker Compose | Testcontainers và service connections |
| --- | --- | --- |
| **Spring Boot 2.x / 3.0** | Chưa có cơ chế Boot-managed Docker Compose như dòng 3.1+ | Có thể dùng Testcontainers JUnit và **@DynamicPropertySource**; không giả định có Boot **@ServiceConnection** |
| **Spring Boot 3.1+** | Có module **spring-boot-docker-compose** và service connection integration | Có module **spring-boot-testcontainers** và **@ServiceConnection** |
| **Spring Boot 3.4.x** | Có **spring.docker.compose.skip.in-tests** mặc định **true**; cho phép bật trong test và tùy chỉnh lifecycle | Hỗ trợ PostgreSQLContainer và JdbcConnectionDetails qua **@ServiceConnection** |
| **Spring Boot đời khác** | Kiểm tra tài liệu của đúng major/minor version | Không tự áp dụng nguyên xi dependency/API của 3.4 sang mọi đời |

Điểm quan trọng của **Boot 3.4**: **không đủ** nếu chỉ thêm spring-boot-docker-compose vào build và gọi ./gradlew test. Theo mặc định Boot **skip Compose khi chạy test**. Để bật nó, phải đồng thời có dependency ở **test runtime classpath** và đặt **spring.docker.compose.skip.in-tests=false**. Khi dùng Gradle, tài liệu chính thức chỉ rõ configuration **testAndDevelopmentOnly**.

**@ServiceConnection** đến từ module **spring-boot-testcontainers**, còn JUnit lifecycle annotation **@Testcontainers** và **@Container** đến từ thư viện Testcontainers. Không trộn các package này với những annotation Spring Data hay Docker Compose YAML.

## 3. Sơ đồ các đường chạy integration test

~~~text
A. Boot-managed Docker Compose
Gradle test
  -> Spring TestContext
  -> Boot Docker Compose integration (nếu test dependency + skip=false)
  -> docker compose up (theo lifecycle và trạng thái hiện tại)
  -> nhận port publish thực tế, tạo JdbcConnectionDetails
  -> Spring DataSource/JPA -> PostgreSQL
  -> chạy JUnit assertions
  -> Spring/Compose quản lý shutdown theo policy

B. Spring Boot + Testcontainers
Gradle test
  -> Spring TestContext
  -> @TestConfiguration @Bean PostgreSQLContainer + @ServiceConnection
  -> Boot start container bean trước datasource beans
  -> tạo JdbcConnectionDetails
  -> Spring DataSource/JPA -> PostgreSQL
  -> chạy JUnit assertions
  -> Spring context shutdown thì dừng container bean

C. Docker Compose do CI điều phối ngoài ứng dụng
CI job
  -> docker compose up -d / --wait
  -> truyền JDBC URL, user, password đã xác định
  -> Spring Boot test với docker-compose integration disabled
  -> assert DB/HTTP
  -> CI job chịu trách nhiệm docker compose down/cleanup
~~~

Cả ba đều có thể dùng PostgreSQL thật; khác biệt là **nơi cấu hình service**, **ai kiểm soát lifecycle**, **mapping port** và **mức cô lập fixture**.

## 4. Boot Docker Compose support hoạt động như thế nào?

Khi spring-boot-docker-compose có trên classpath phù hợp và được bật, Spring Boot có thể:
1. Tìm các tên file Compose thông dụng trong working directory, hoặc dùng file cấu hình tại **spring.docker.compose.file**.
2. Gọi Docker Compose CLI để **up** các service nếu cần.
3. Chờ readiness của service theo **Docker healthcheck** hoặc TCP readiness check.
4. Nhận **mapped host/port** từ Docker Compose thay vì giả sử internal port bằng host port.
5. Với image được hỗ trợ, tạo **ConnectionDetails bean** (ví dụ JdbcConnectionDetails đối với PostgreSQL).
6. Tạo DataSource tự động từ connection details; khi shutdown quản lý Compose theo **lifecycle-management**.

### Điều kiện cần

- Docker daemon/Engine chạy được và user/process có quyền truy cập.
- Có **docker** và **docker compose** CLI trên PATH của process chạy Spring Boot. Boot 3.4 tài liệu yêu cầu Docker Compose phiên bản được hỗ trợ (tối thiểu 2.2.0 theo tài liệu dòng này).
- Docker image có thể pull được hoặc đã có cache trên runner.
- File Compose đúng working directory / đường dẫn được cấu hình.
- Service thuộc nhóm image được Boot hỗ trợ; custom image có thể cần label **org.springframework.boot.service-connection**.

**Không assume Docker CLI có mặt trong mọi CI container.** Một runner có Docker socket nhưng không có Compose CLI sẽ không tự chạy được Boot-managed Compose, dù Testcontainers Java có thể hoạt động nếu có Docker API.

### Service connection tự nhận host port

Một Compose service có:

~~~yaml
ports:
  - "5432"
~~~

có nghĩa container dùng **port 5432 nội bộ**, còn Docker publish một **host port động**. Nếu Docker map thành 127.0.0.1:32781, client Spring Boot phải kết nối đến **host-mapped port 32781**, không phải 5432. Khi Boot nhận diện PostgreSQL Compose service, JdbcConnectionDetails dùng port được map; bạn không cần hard-code spring.datasource.url=jdbc:postgresql://localhost:5432/....

Với một service đặt trong Docker network khác, địa chỉ **postgres:5432** thường là tên service nội bộ dùng giữa các containers, không đồng nghĩa một Java test process chạy trên host có thể resolve nó. Phân biệt **host** của test JVM với **network namespace** của service.

## 5. Vì sao Docker Compose mặc định không chạy trong tests?

Docker Compose support được Spring Boot thiết kế cho **development-time services**. Một bài test slice/unit không nên tự động dựng cả stack chỉ vì project có file Compose. Spring Boot 3.4 đặt:

~~~properties
spring.docker.compose.skip.in-tests=true
~~~

theo mặc định. Muốn **opt in** ở một test profile:

~~~properties
spring.docker.compose.skip.in-tests=false
~~~

Với Gradle, dependency cần ở test classpath:

~~~groovy
dependencies {
    testAndDevelopmentOnly 'org.springframework.boot:spring-boot-docker-compose'
}
~~~

Trong các bản hướng dẫn khác, dependency thường được khai báo như:

~~~groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-docker-compose'
}
~~~

**developmentOnly** phù hợp dev application run, nhưng **không phải lựa chọn đủ cho Compose-in-tests theo hướng dẫn Boot 3.4**. Cần **testAndDevelopmentOnly** nếu muốn tính năng trên test classpath. Ngoài ra, chỉ thay scope dependency mà **không bật skip.in-tests=false** thì Spring Boot vẫn skip Compose trong tests.

**Nên bật trong profile test có chủ đích**, không viết skip.in-tests=false trong mọi application.yml rồi bắt mọi unit test khởi động PostgreSQL bất kể chúng có cần không.

## 6. Docker Compose readiness và lifecycle

### Readiness

Spring Boot khuyên Compose service có **healthcheck**. Nếu không có healthcheck, Boot có thể dùng TCP readiness: khi một cổng đã nhận connection không có nghĩa database đã hoàn tất migrations hoặc consumer group đã sẵn sàng. Với PostgreSQL, healthcheck dùng **pg_isready** cho ý định rõ ràng.

Các properties có thể điều chỉnh:
- **spring.docker.compose.readiness.timeout**: giới hạn tổng thời gian chờ.
- **spring.docker.compose.readiness.tcp.connect-timeout** và **read-timeout**.
- **spring.docker.compose.readiness.wait**: policy chờ readiness.
- **spring.docker.compose.profiles.active**: chọn Docker Compose profiles cho service stack.

**Docker Compose profile khác Spring profile.** Spring profile chọn cấu hình bean/application; Docker Compose profile chọn services trong Compose project. Bạn có thể dùng một Spring test profile để bật tương ứng Compose profile, nhưng hai cơ chế không tự đồng bộ chỉ vì cùng tên.

### Lifecycle

| Giá trị spring.docker.compose.lifecycle-management | Ý nghĩa |
| --- | --- |
| **none** | Boot không tự start/stop Compose; chỉ dùng các service có thể kết nối theo cấu hình/phát hiện phù hợp |
| **start-only** | Boot có thể start service nhưng không stop lúc application dừng |
| **start-and-stop** | Mặc định: Boot quản lý start/stop khi nó khởi động Compose |

Nếu Compose project **đã chạy trước** khi Spring Boot khởi động, Boot theo tài liệu sẽ dùng service connections từ containers đó và không tự gọi up/stop lại theo hành vi mặc định. **Không tin rằng mọi test JVM sẽ sở hữu lifecycle của một project Compose đang chạy chung**.

**docker compose stop** khác **docker compose down**: stop dừng containers nhưng không nhất thiết xóa containers/networks/volumes; down loại containers/network theo option, còn down --volumes có thể xóa dữ liệu volume. Trong test shared project, tự động đổi stop.command=down hoặc down -v có thể phá dữ liệu/chạy service của người khác. Chỉ dùng lệnh xóa khi **test project có quyền sở hữu riêng**.

## 7. Dự án runnable: PostgreSQL chung cho hai chiến lược

Bài mẫu chạy **cùng ứng dụng** nhưng có hai kiểu cung cấp JDBC connection:

- **ComposeManagedPostgresTest** dùng Spring Boot Docker Compose integration, chọn profile compose-it.
- **TestcontainersPostgresTest** dùng @Bean PostgreSQLContainer có @ServiceConnection.
- Cả hai kiểm tra **SELECT current_database()** trả **lessondb**, và Spring Data JPA insert/query thành công với PostgreSQL thật.
- Mỗi test dùng **SKU ngẫu nhiên** và **@Transactional rollback**, không cố định generated ID hoặc dùng dữ liệu test trước.

### 7.1. Cây file

~~~text
settings.gradle
build.gradle
compose.test.yaml
src/main/resources/application.yml
src/main/java/com/example/composeqa/ComposeQaApplication.java
src/main/java/com/example/composeqa/InventoryItem.java
src/main/java/com/example/composeqa/InventoryRepository.java
src/test/resources/application-compose-it.yml
src/test/java/com/example/composeqa/ComposeManagedPostgresTest.java
src/test/java/com/example/composeqa/PostgresContainerConfig.java
src/test/java/com/example/composeqa/TestcontainersPostgresTest.java
~~~

### 7.2. Gradle build

**settings.gradle**

~~~groovy
rootProject.name = 'spring-compose-testcontainers-choice'
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
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'

    testAndDevelopmentOnly 'org.springframework.boot:spring-boot-docker-compose'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Các dependency có vai trò khác nhau:

- **spring-boot-starter-data-jpa**: Spring Data/JPA/Hibernate và transaction support.
- **postgresql driver**: JDBC driver để DataSource mở connection.
- **spring-boot-starter-test**: JUnit Jupiter và Spring test infrastructure.
- **spring-boot-testcontainers**: Spring Boot @ServiceConnection / test connection factories.
- **org.testcontainers:postgresql**: PostgreSQLContainer.
- **org.testcontainers:junit-jupiter**: JUnit @Testcontainers/@Container khi chọn lifecycle JUnit; build bao gồm để có thể thử đường đó, dù runnable example chính dùng **container bean**.
- **testAndDevelopmentOnly spring-boot-docker-compose**: có Docker Compose integration trên test classpath.

Spring Boot BOM quản lý các phiên bản tương thích của những dependencies được hỗ trợ. Không gắn một bản Docker Java, Testcontainers, Hibernate và Spring Framework tùy ý ngoài BOM khi chưa có lý do/test tương thích.

**Quan trọng:** Gradle config **testAndDevelopmentOnly** là cấu hình Spring Boot Gradle plugin dành cho development + test. Nếu dùng Maven, cần cấu hình dependency scope theo Maven và tài liệu Boot tương ứng; không chép cấu hình Gradle sang pom.xml.

### 7.3. Compose file chỉ dành cho test

**compose.test.yaml**

~~~yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: lessondb
      POSTGRES_USER: lesson
      POSTGRES_PASSWORD: lesson-pass
    ports:
      - "5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U lesson -d lessondb"]
      interval: 2s
      timeout: 3s
      retries: 20
~~~

**Điểm cần kiểm tra:**

- **postgres:16-alpine** là image chuẩn mà Spring Boot 3.4 nhận diện cho JdbcConnectionDetails.
- Cổng được publish với random host port, giảm xung đột khi máy chạy PostgreSQL khác ở 5432.
- **pg_isready** chờ DB sẵn sàng cho connection; nó không kiểm chứng business schema/migrations hoặc dữ liệu seed đúng.
- Credentials **lesson/lesson-pass** chỉ là dữ liệu mẫu dành cho test; production phải dùng secrets và cách quản lý an toàn.
- Không gắn named volume production vào compose.test.yaml. Nếu test sử dụng Compose volumes cần kế hoạch cleanup riêng.
- Các test có thể chạy cùng source checkout nhưng nhiều CI jobs dùng chung Compose project name có nguy cơ collision; dùng project name/working directory riêng mỗi job.

**Không nhầm vị trí file:** tên compose.test.yaml không nằm trong các tên Boot tự khám phá mặc định; phần tiếp theo đặt **spring.docker.compose.file** để chỉ rõ nó.

### 7.4. Application YAML và test profile

**src/main/resources/application.yml**

~~~yaml
spring:
  jpa:
    open-in-view: false
~~~

Ở đây **không hard-code spring.datasource.url/username/password**. Các integration tests sẽ nhận thông tin qua **ConnectionDetails** do Compose/Testcontainers sinh ra. Không có container thì application hiện chưa có datasource cấu hình; dự án này được xây cho integration test chạy theo một trong hai modes, không hứa rằng chỉ bootRun trần sẽ tự có PostgreSQL.

**src/test/resources/application-compose-it.yml**

~~~yaml
spring:
  docker:
    compose:
      skip:
        in-tests: false
      file: compose.test.yaml
      lifecycle-management: start-and-stop
  jpa:
    hibernate:
      ddl-auto: create-drop
    open-in-view: false
~~~

**skip.in-tests=false** chính là opt-in quan trọng. **file: compose.test.yaml** trỏ Compose file ở project root tương đối với working directory Gradle test (mặc định thường project directory). Nếu runner đổi working directory, đặt path tương ứng. **ddl-auto=create-drop** chỉ dành cho database/schema **do tests độc quyền sở hữu**; không chạy profile này trỏ vào một PostgreSQL server hoặc Compose project đang chứa dữ liệu dev/production. Với nhóm tests có migrations, nên dùng Flyway/Liquibase trên test DB thay vì Hibernate tự tạo/xóa schema.

### 7.5. Main application

**src/main/java/com/example/composeqa/ComposeQaApplication.java**

~~~java
package com.example.composeqa;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ComposeQaApplication {
    public static void main(String[] args) {
        SpringApplication.run(ComposeQaApplication.class, args);
    }
}
~~~

### 7.6. Entity InventoryItem

**src/main/java/com/example/composeqa/InventoryItem.java**

~~~java
package com.example.composeqa;

import java.util.Objects;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

@Entity
@Table(
    name = "inventory_items",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_inventory_item_sku",
        columnNames = {"sku"}))
public class InventoryItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 100)
    private String sku;

    @Column(nullable = false)
    private int quantity;

    protected InventoryItem() {
        // For JPA.
    }

    public InventoryItem(String sku, int quantity) {
        this.sku = Objects.requireNonNull(sku, "sku");
        if (quantity < 0) {
            throw new IllegalArgumentException("quantity must be >= 0");
        }
        this.quantity = quantity;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }
}
~~~

Entity này giữ test đơn giản: một bảng, một unique SKU, một giá trị quantity. **Generated identity không bảo đảm reset về 1 sau rollback**; test chỉ assert ID được cấp (không cố định con số). **SKU sử dụng UUID** để tránh dữ liệu từ test trước hoặc một DB run khác trùng unique constraint.

### 7.7. Repository

**src/main/java/com/example/composeqa/InventoryRepository.java**

~~~java
package com.example.composeqa;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface InventoryRepository
        extends JpaRepository<InventoryItem, Long> {

    Optional<InventoryItem> findBySku(String sku);
}
~~~

**findBySku** giúp assertion theo key do test tự tạo, thay vì query count trên toàn bảng có thể có dữ liệu ngoài test. Khi làm multi-tenant thật, cần thêm tenant scope vào repository predicate và cleanup.

## 8. Mode A: chạy Compose trong Spring Boot test

**src/test/java/com/example/composeqa/ComposeManagedPostgresTest.java**

~~~java
package com.example.composeqa;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@ActiveProfiles("compose-it")
@Transactional
class ComposeManagedPostgresTest {

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private InventoryRepository items;

    @Test
    void connectsToRealPostgresViaComposeServiceConnection() {
        String database = jdbc.queryForObject(
                "select current_database()", String.class);
        assertEquals("lessondb", database);

        String sku = "compose-" + UUID.randomUUID();
        InventoryItem saved = items.saveAndFlush(
                new InventoryItem(sku, 7));

        assertNotNull(saved.getId());
        assertEquals(7, items.findBySku(sku)
                .orElseThrow().getQuantity());
    }

    @Test
    void anotherMethodCreatesIndependentFixture() {
        String sku = "compose-" + UUID.randomUUID();
        assertTrue(items.findBySku(sku).isEmpty());

        items.saveAndFlush(new InventoryItem(sku, 3));
        assertEquals(3, items.findBySku(sku)
                .orElseThrow().getQuantity());
    }
}
~~~

**Điều được chứng minh:**

1. @ActiveProfiles chọn **application-compose-it.yml** từ test classpath.
2. Gradle có **testAndDevelopmentOnly** dependency và profile có **skip.in-tests=false**, nên Boot có thể khởi động/khám phá Compose.
3. Compose service Postgres được nhận diện; Spring tạo **JdbcConnectionDetails** và DataSource kết nối port được publish.
4. **select current_database()** là hàm PostgreSQL và phải trả **lessondb**. Nếu kết nối nhầm H2, test này không thể xanh với cùng SQL.
5. Spring Data JPA saveAndFlush và findBySku sử dụng database thật.
6. @Transactional mở **test-managed transaction** và rollback cuối mỗi method; mỗi method có UUID SKU riêng.

**Không tự kết luận test này chứng minh tất cả trường hợp production.** Nó kiểm chứng kết nối PostgreSQL và ORM query qua Compose với schema test; chưa chứng minh migration production, network latency, auth/TLS production hoặc toàn bộ service stack.

### Tại sao không dùng @DataJpaTest theo mặc định?

**@DataJpaTest** có thể cấu hình embedded database thay datasource test nếu H2 nằm trên classpath. Nếu muốn dùng PostgreSQL thật trong JPA slice, cân nhắc **@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)** để không thay DataSource. Trong runnable demo dùng **@SpringBootTest** để tập trung vào service connection và giữ rõ backend được sử dụng.

## 9. Mode B: Testcontainers + @ServiceConnection

Khi mục tiêu là integration test kết nối một backend thật được quản lý bởi Java/Spring test lifecycle, **Testcontainers** rất phù hợp. Spring Boot 3.4 cho phép một **@Bean PostgreSQLContainer** trong **@TestConfiguration**, đánh dấu **@ServiceConnection**. Spring Boot sẽ start container bean đủ sớm để tạo DataSource và stop khi ApplicationContext bị hủy.

Cách **container bean** này giúp lifecycle gắn với Spring context; đặc biệt hữu ích khi TestContext cache qua nhiều classes, tránh một JUnit static @Container bị dừng ở cuối class trong khi cached Spring context vẫn còn giữ connection details cũ.

**src/test/java/com/example/composeqa/PostgresContainerConfig.java**

~~~java
package com.example.composeqa;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.PostgreSQLContainer;

@TestConfiguration(proxyBeanMethods = false)
public class PostgresContainerConfig {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>("postgres:16-alpine")
                .withDatabaseName("lessondb")
                .withUsername("lesson")
                .withPassword("lesson-pass");
    }
}
~~~

**Vì sao dùng @Bean?** Spring Boot quản lý start/stop container như một bean theo context lifecycle, phù hợp khi DataSource bean cần container còn sống trong lúc Spring context shutdown. **@ServiceConnection** dựa trên container type PostgreSQLContainer để tạo **JdbcConnectionDetails**; không cần khai báo JDBC URL, password và port qua application properties.

### Test Testcontainers trên cùng repository

**src/test/java/com/example/composeqa/TestcontainersPostgresTest.java**

~~~java
package com.example.composeqa;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.jdbc.JdbcConnectionDetails;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(properties = {
        "spring.docker.compose.enabled=false",
        "spring.jpa.hibernate.ddl-auto=create-drop"
})
@Import(PostgresContainerConfig.class)
@Transactional
class TestcontainersPostgresTest {

    @Autowired
    private JdbcConnectionDetails connectionDetails;

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private InventoryRepository items;

    @Test
    void serviceConnectionPointsToTestcontainersPostgres() {
        assertTrue(connectionDetails.getJdbcUrl()
                .startsWith("jdbc:postgresql:"));

        assertEquals("lessondb", jdbc.queryForObject(
                "select current_database()", String.class));

        String sku = "testcontainers-" + UUID.randomUUID();
        InventoryItem saved = items.saveAndFlush(
                new InventoryItem(sku, 11));

        assertNotNull(saved.getId());
        assertEquals(11, items.findBySku(sku)
                .orElseThrow().getQuantity());
    }

    @Test
    void secondTestDoesNotNeedFirstTestData() {
        String sku = "testcontainers-" + UUID.randomUUID();
        assertTrue(items.findBySku(sku).isEmpty());

        items.saveAndFlush(new InventoryItem(sku, 4));
        assertEquals(4, items.findBySku(sku)
                .orElseThrow().getQuantity());
    }
}
~~~

**Đặc điểm quan trọng:**

- **spring.docker.compose.enabled=false** giữ rõ rằng test này dùng **Testcontainers**, không vô tình khởi động Compose.
- **@Import(PostgresContainerConfig.class)** thêm container bean test-only vào ApplicationContext.
- Spring Boot **start** container bean trước các beans phụ thuộc. **@ServiceConnection** tạo JdbcConnectionDetails, DataSource tự kết nối random host port tương ứng.
- **select current_database()** và repository save/query là assertions cho một **PostgreSQL thật**, không chỉ assert rằng container báo running.
- Test dùng @Transactional rollback mỗi method, UUID SKU riêng. Kết thúc context thì Spring dừng container bean.

**Không đặt @ServiceConnection lên một field PostgreSQLContainer mà không có dependency spring-boot-testcontainers.** Thiếu module đó, annotation/factory không có trong test classpath. Và không nhầm việc Testcontainers start container thành tự động chạy database migrations/schema nếu project không có DDL/schema policy; ví dụ dùng **ddl-auto=create-drop** chỉ trên test DB.

### JUnit @Testcontainers/@Container là một cách khác

Spring Boot 3.4 cũng hỗ trợ cách khai báo **static container field** với JUnit extension:

~~~java
@Testcontainers
@SpringBootTest(properties = "spring.docker.compose.enabled=false")
class ExampleJUnitContainerLifecycle {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
~~~

Đây là **trích đoạn để so sánh**, chưa có imports và test methods nên **không phải runnable file trong cây dự án**. **@Testcontainers** nằm trong org.testcontainers.junit.jupiter, **@Container** trong cùng package, **@ServiceConnection** nằm trong org.springframework.boot.testcontainers.service.connection.

**Lưu ý lifecycle:** static @Container do JUnit extension quản lý theo test class. Khi Spring TestContext cache một ApplicationContext được tạo bằng connection details của container đó sang class khác, container có thể bị stop trước khi cached context bị đóng. Vì vậy với nhiều classes reuse context, **container bean theo Spring context** thường có lifecycle dễ kiểm soát hơn; hoặc chủ động thiết kế shared container/context strategy đúng.

## 10. @DynamicPropertySource cho phiên bản hoặc service không có @ServiceConnection

**@ServiceConnection không hỗ trợ tùy ý mọi container/service**. Boot dùng ContainerConnectionDetailsFactory để suy ra ConnectionDetails từ loại container hoặc image name. Với custom service không có factory, hoặc trên Spring Boot 3.0 trở xuống chưa có Boot service connection support, dùng **@DynamicPropertySource** (Spring TestContext) là lựa chọn rõ:

~~~java
@Testcontainers
@SpringBootTest(properties = "spring.docker.compose.enabled=false")
class LegacyStylePostgresIT {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void datasourceProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
~~~

Đây là **trích đoạn** cần các imports và test methods; không phải runnable class của dự án chính. **@DynamicPropertySource** lấy host/port/credentials runtime sau khi container sẵn sàng, thay vì hard-code 5432. Đừng dùng cả @ServiceConnection và @DynamicPropertySource cho cùng DataSource một cách mập mờ; **ConnectionDetails thường có precedence trên properties** và làm việc debug connection source khó hơn.

Trong một test có nhiều databases cùng loại, phải xác định từng connection bean rõ ràng bằng tên/configuration, không mặc định Boot đoán một datasource theo ý định của bạn. Với containers không được Boot nhận diện do custom image name, xem label/service connection factory hoặc tạo ConnectionDetails bean tường minh.

## 11. Boot Compose vs Testcontainers: bảng lựa chọn

| Nhu cầu | Lựa chọn phù hợp | Vì sao |
| --- | --- | --- |
| Unit test pure Java/Mockito | **Không cần Docker** | Nhanh, không external backend |
| Repository test chỉ cần SQL rất cơ bản | H2/@DataJpaTest nếu chấp nhận hạn chế dialect | Nhanh; không chứng minh PostgreSQL semantics |
| Integration test PostgreSQL thật trên Boot 3.1+ | **Testcontainers + @ServiceConnection** | Container gần test, lifecycle rõ, random port, dễ chạy CI có Docker |
| Integration test cần 2–3 services được cấu hình bằng Java | Testcontainers multi-container/test configuration | Có thể quản lý dependencies/network/fixtures trực tiếp trong test |
| Dev stack đã chuẩn hóa bằng Compose YAML | **Boot Docker Compose support** | Tái sử dụng định nghĩa services và service connections |
| Muốn kiểm thử chính Compose stack trong test | **Compose-in-tests opt-in** | Cho tests thật sự dùng file Compose/healthchecks/service mappings |
| CI đã chạy docker compose up từ trước | **External Compose + explicit properties** | CI chịu trách nhiệm lifecycle, Boot không tự start/stop nữa |
| Boot 2.x/3.0 | Testcontainers + @DynamicPropertySource hoặc external Compose | Không giả định có Boot 3.1 @ServiceConnection |
| Runner không có Docker daemon | Unit/mock/embedded DB, hoặc cấp CI Docker | Không thể gọi đó là PostgreSQL container test nếu không có container |
| Tính năng phụ thuộc production PostgreSQL index/lock/collation | Container PostgreSQL đúng major version | H2 không mô phỏng đầy đủ vendor behavior |
| Test contract cần TLS/proxy/real deployment network | Environment-level integration/e2e | Container DB local chỉ là một lớp bằng chứng |

**Không có một lựa chọn luôn tốt nhất.** Chọn theo mục tiêu test, độ cô lập, khả năng Docker/Compose trên CI, số lượng services, lifecycle và chi phí startup.

### “Dùng Compose file sẵn có” không nhất thiết mạnh hơn “Testcontainers”

Compose có lợi khi bạn muốn stack giống dev, các dịch vụ được cấu hình chung và muốn kiểm tra orchestration. Nhưng nếu chỉ cần một PostgreSQL tạm cho mỗi test context, Testcontainers thường đơn giản hơn: Java định nghĩa image/version, Spring Boot tự tạo connection details và lifecycle gắn test. Ngược lại, nếu project có Compose file chính là contract cần xác minh, Testcontainers chỉ chạy một container Postgres có thể bỏ sót cấu hình networks/aliases/healthchecks/other services.

## 12. Chạy hai mode và chẩn đoán

### Kiểm tra Docker và Compose trước khi chạy

~~~bash
docker version
docker compose version
docker info
~~~

Nếu **docker version** chỉ cho client nhưng daemon không truy cập được, Testcontainers và Compose đều có thể fail. Trong CI, runner cần quyền truy cập Docker daemon/socket hoặc runner được cấp Docker-in-Docker theo policy. **Không đề xuất cấp quyền 0777 cho /var/run/docker.sock** để chữa lỗi quyền: Docker socket cho phép quyền rất cao trên host, phải dùng runner/permissions được kiểm soát.

### Chạy mỗi lựa chọn riêng

~~~bash
./gradlew test --tests com.example.composeqa.ComposeManagedPostgresTest
./gradlew test --tests com.example.composeqa.TestcontainersPostgresTest
./gradlew clean test
~~~

Trên Windows dùng **gradlew.bat**. **./gradlew clean test** chạy cả hai nhóm và vì vậy cần **Docker daemon + Docker Compose CLI**. Nếu CI chỉ có Docker Engine mà không có Compose CLI, nên chạy Testcontainers class và để Compose class trong suite/CI job chỉ hỗ trợ Compose, thay vì mặc định cả bộ test đều phải có Compose.

**Kết quả dự kiến** nếu Docker và dependencies hoạt động:

| Test | Expected evidence |
| --- | --- |
| ComposeManagedPostgresTest.connectsToRealPostgresViaComposeServiceConnection | current_database() == lessondb; JPA insert/query quantity 7 |
| ComposeManagedPostgresTest.anotherMethodCreatesIndependentFixture | UUID SKU mới, JPA insert/query quantity 3 |
| TestcontainersPostgresTest.serviceConnectionPointsToTestcontainersPostgres | JDBC URL bắt đầu jdbc:postgresql:; database lessondb; quantity 11 |
| TestcontainersPostgresTest.secondTestDoesNotNeedFirstTestData | UUID SKU mới, quantity 4 |

Bảng chỉ diễn giải **contract assertions**, không bịa log Spring/Gradle thực tế. Port random và ID identity thay đổi giữa runs, do đó không đưa ra con số port/ID cố định.

### Debug Compose khi test không kết nối được

~~~bash
docker compose -f compose.test.yaml ps
docker compose -f compose.test.yaml logs postgres
docker compose -f compose.test.yaml port postgres 5432
~~~

Nếu Spring Boot đặt project name/working directory/Compose profile khác command thủ công, command kiểm tra cần dùng đúng Compose project/options; không suy từ một danh sách docker ps không cùng project. **Không tự chạy down --volumes trên Compose project shared**; xác nhận test sở hữu project trước khi xóa dữ liệu.

### Debug Testcontainers

- Kiểm tra Docker API và daemon truy cập được từ JVM.
- Testcontainers có pull được image postgres:16-alpine?
- @ServiceConnection và spring-boot-testcontainers có trên test runtime classpath?
- Container bean có được @Import vào test context?
- Có startup wait/readiness failures hoặc datasource setup trước khi container sẵn sàng không?
- Có context reuse kết hợp JUnit static containers đã bị stop không?

**Không hard-code localhost:5432** để “fix” connection error. Với random mapped port, 5432 thường không phải port đúng.

## 13. Nếu Docker Compose do CI điều phối, không để Boot tự quản lý nữa

Có những CI systems đã chạy các services qua Compose trước khi gọi Gradle. Khi đó Boot không nhất thiết phải khởi động Compose:

~~~bash
docker compose -f compose.test.yaml up -d --wait
# CI lấy host/mapped port từ docker compose port và export JDBC settings.
./gradlew test --tests com.example.composeqa.TestcontainersPostgresTest
# CI cleanup riêng cho Compose project của mình.
~~~

Đoạn shell trên chỉ mô tả **trình tự điều phối**, không phải script chạy nguyên xi: TestcontainersPostgresTest trong dự án mẫu dùng **container riêng** nên **không sử dụng external Compose**. Muốn dùng external Compose thật, cần tạo một test class/config không @Import(PostgresContainerConfig), truyền đúng datasource URL/username/password do CI cung cấp và đặt **spring.docker.compose.enabled=false**. Đừng chạy lệnh này rồi tuyên bố TestcontainersPostgresTest kiểm thử chính Compose service đó.

**Ví dụ external Compose mode rõ ràng hơn:**

~~~properties
spring.docker.compose.enabled=false
spring.datasource.url=jdbc:postgresql://127.0.0.1:HOST_PORT/lessondb
spring.datasource.username=lesson
spring.datasource.password=lesson-pass
spring.jpa.hibernate.ddl-auto=validate
~~~

Đây là **mẫu cấu hình minh họa**, **HOST_PORT** phải được thay bằng mapped port thật từ CI; không phải property file runnable và **validate** chỉ hợp lệ khi migrations/DDL đã tạo schema. Một CI task đầy đủ cần đảm bảo readiness, set variables, tạo schema/migrations, chạy test và finally cleanup Compose project riêng.

**Có thể đặt lifecycle-management=none** nếu Boot Compose integration vẫn cần nhận biết services đã chạy nhưng không được tự start/stop. Nếu CI đã truyền explicit datasource properties và không cần Boot Compose, đặt **spring.docker.compose.enabled=false** đơn giản hơn.

## 14. Điểm nguy hiểm: ghi đè datasource và service connection precedence

Khi có một **JdbcConnectionDetails bean** từ Docker Compose hoặc Testcontainers, auto-configuration của Spring Boot dùng connection details đó, và nó thường **ưu tiên hơn spring.datasource.url/username/password**. Điều này giúp các random mapped ports hoạt động nhưng cũng tạo lỗi debug:

- application-test.yml ghi jdbc:postgresql://localhost:5432, nhưng @ServiceConnection từ Testcontainers thắng -> app thực sự kết nối container random port khác.
- Boot Compose được bật ngoài ý định, JDBC properties đang trỏ vào một CI database nhưng connection details mới đè lên -> test đọc sai database.
- Project có hai PostgreSQL containers và một DataSource không được qualify -> lựa chọn ambiguous.

**Giải pháp:** mỗi test mode sở hữu đúng **một nguồn connection details** và có assertion thực: JDBC URL/DB identity hoặc backend version, đọc/ghi một row độc lập. Tránh sử dụng cùng lúc Compose integration và Testcontainers service connection cho cùng một database nếu không có thiết kế multi-datasource rõ ràng.

### Custom Docker images và auto recognition

Boot Compose thường nhận service theo **image name**. Ví dụ image custom **mycompany/postgres-with-extensions** có thể không được suy ra loại dịch vụ PostgreSQL. Có thể khai báo label:

~~~yaml
services:
  postgres:
    image: mycompany/postgres-with-extensions:16
    labels:
      org.springframework.boot.service-connection: postgres
~~~

Đây là **trích đoạn**, không thuộc runnable compose.test.yaml vì image giả định không có thật. Label phải tương ứng loại service connection được Boot hỗ trợ. Nếu không có factory cho dịch vụ custom, tự cấu hình client/connection details. Không nhầm **org.springframework.boot.ignore** (bỏ qua container) với service connection label.

## 15. Data isolation khi dùng database trong container

**Container mới không có nghĩa mỗi test method có database mới.** Với:
- Compose start-and-stop, cùng Compose project có thể được dùng lại giữa nhiều test contexts; stop không xóa volume.
- Testcontainers @Bean lifecycle theo Spring context, context cache có thể giữ DB qua nhiều test methods/classes.
- JUnit static @Container thường sống suốt class; không nhất thiết được tạo lại cho từng method.
- Reused Testcontainers containers có thể sống lâu hơn một test run theo policy nếu feature reuse được bật.

Dù backend là PostgreSQL trong container, **rollback/cleanup vẫn bắt buộc**:
- @Transactional trên repository integration test thường rollback DML của test thread.
- HTTP RANDOM_PORT gửi request sang server thread, service có transaction khác, **rollback của JUnit test không dọn data server đã commit**.
- @Commit/@Rollback(false) khiến test transaction commit; phải dọn sau commit.
- REQUIRES_NEW đã commit độc lập, không rollback theo outer JUnit transaction.
- SQL migrations/fixtures được seed ở context startup có thể tồn tại ngoài test transaction.

Với các tests trong dự án này, **@Transactional rollback** và **UUID SKU** giảm phụ thuộc. Nhưng **ddl-auto=create-drop** còn tạo/xóa schema ở context lifecycle, nên không chạy song song nhiều contexts có thể cùng trỏ một Compose/Postgres database; hãy cho mỗi CI job/Compose project/database tên riêng hoặc serialize suite appropriately. Với production-like integration tests, ưu tiên migrations trên disposable DB thay vì create-drop.

### Rollback khác cleanup, cleanup khác destroy container

| Mục tiêu | Công cụ phù hợp |
| --- | --- |
| Xóa thay đổi ORM của test thread | Spring test-managed rollback |
| Xóa row đã commit bởi server/REQUIRES_NEW | DELETE scoped hoặc cleanup transaction riêng |
| Trả lại dữ liệu baseline nhiều bảng | SQL seed/cleanup có transaction policy rõ |
| Reset toàn database cho suite | Disposable container/schema riêng |
| Dừng containers | Spring/Compose/Testcontainers lifecycle |
| Xóa volumes/schema lâu dài | Quy trình destroy riêng, giới hạn tài nguyên test sở hữu |

**Không dùng docker compose down -v trên một project đã được chia sẻ với developers** chỉ để test “sạch hơn”. Những volumes có thể chứa dữ liệu quan trọng. Không dùng destructive schema reset khi datasource không được chứng minh là test-only.

## 16. @DataJpaTest, @SpringBootTest và khả năng thay datasource

**@DataJpaTest** chạy JPA slice và có thể tự thay DataSource bằng embedded database trong test nếu dependency cho phép. Nếu muốn JPA slice thực sự kết nối PostgreSQL từ Testcontainers hoặc Compose, thường thêm:

~~~java
@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE)
@Import(PostgresContainerConfig.class)
class RepositoryPostgresSliceTest {
}
~~~

Đây là **trích đoạn**, chưa có test methods và imports; nó dùng container config đã có ở project. Nó cho thấy chủ đích **không thay PostgreSQL bằng H2**. Trong Boot 3.4, behavior của @AutoConfigureTestDatabase với service connections có thêm cơ chế nhận diện các test databases, nên vẫn nên **kiểm chứng connection thực tế** thay vì đoán chỉ từ annotation.

**@SpringBootTest** tải full application context, hợp khi muốn kiểm chứng autoconfiguration nhiều layers và service connection. Nó không mặc nhiên @Transactional: runnable tests đã thêm @Transactional để rollback. Với real HTTP RANDOM_PORT, phải cleanup commit ở server thread riêng, không dựa vào outer test rollback.

### Khi nào unit test không cần Docker?

Không phải mọi method test cần DB engine. Với pure business function, JUnit/Mockito giúp feedback nhanh. Với repository mapping và SQL cơ bản, H2 có thể đủ nếu hạn chế dialect được chấp nhận. **Nếu business rule phụ thuộc PostgreSQL JSONB, transactions, locks, collations, indexes**, dùng container PostgreSQL thật để giảm fake confidence. Nên tách **fast tests** và **integration tests** để CI có khả năng chạy thường xuyên mà vẫn không mất coverage quan trọng.

## 17. Network, readiness và lỗi CI thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Test dùng Compose nhưng không thấy Postgres start | **skip.in-tests=true** mặc định hoặc module không có trên test classpath | Bật skip=false ở profile và testAndDevelopmentOnly dependency |
| bootRun có Compose nhưng ./gradlew test không có | Chỉ khai báo developmentOnly hoặc tests mặc định skip | Scope dependency và property test đúng |
| Compose CLI không tìm thấy | CI có Docker Engine nhưng thiếu Compose plugin/CLI | Cấp Compose CLI hoặc dùng Testcontainers nếu phù hợp |
| Could not find Docker environment | Docker daemon/socket không truy cập được | Kiểm tra runner và Docker permissions |
| Connection refused 127.0.0.1:5432 | Dùng internal port thay mapped host port | Dùng ConnectionDetails/getMappedPort, bỏ hard-code |
| Spring tự kết nối sai database | ConnectionDetails ưu tiên hơn datasource properties | Tách mode, tắt Compose trong TC tests, assert current_database |
| Custom image không được nhận diện | Image name không khớp service connection factory | Label org.springframework.boot.service-connection hoặc config explicit |
| App start trước khi DB ready | Thiếu/không đúng healthcheck/readiness | pg_isready, timeout hợp lý, kiểm tra logs |
| Test pass riêng, fail cả suite | Shared Compose DB/schema, context cache, fixtures còn lại | Unique DB/project name, rollback/cleanup, serialize khi cần |
| Context vẫn sống nhưng JUnit container đã dừng | @Container static class lifecycle ngắn hơn cached context | Spring-managed @Bean container hoặc lifecycle rõ |
| @DataJpaTest chạy H2 thay Postgres | Embedded DB replacement | @AutoConfigureTestDatabase(replace=NONE), assert real PostgreSQL |
| Container đã stop nhưng volume còn data | Compose stop không down/delete volume | Disposable project + cleanup riêng, không xóa shared volumes |
| Boot test tắt Docker Compose nhưng datasource chưa có | Không có Testcontainers/external datasource | Cung cấp đúng backend theo test mode |
| Docker image pull bị timeout | CI network/registry credentials/caches | Pre-pull/cache image, network policy, bounded retry |
| Tests flaky vì timeouts ngắn | DB startup/migrations chậm | Healthcheck + readiness timeout hợp lý, không Thread.sleep |
| Test CI không có Docker nhưng đã skip hết integration tests | Coverage bị bỏ mà không báo | Phân tầng CI, fail rõ job integration khi Docker yêu cầu |
| Dữ liệu dev bị xóa khi test kết thúc | ddl-auto=create-drop hoặc down -v trên shared DB | Dùng test-only database/project/schema, bảo vệ destructive operations |

## 18. Quy trình ra quyết định cho dự án thật

**Câu 1: Đang test tầng nào?** Unit/service logic không cần DB có thể chạy không Docker. Repository/database integration cần DB thật nếu SQL dialect/transactions là trọng tâm.

**Câu 2: Spring Boot version?** Từ 3.1+ có Boot-managed Compose và @ServiceConnection. Nếu version cũ, dùng Testcontainers + @DynamicPropertySource hoặc external Compose configuration.

**Câu 3: Ai sở hữu file cấu hình services?** Nếu team chuẩn hóa Compose YAML gồm PostgreSQL/Redis/Kafka và muốn kiểm tra nó, chọn Compose. Nếu mỗi Java integration test tự định nghĩa backend, chọn Testcontainers.

**Câu 4: CI có Docker daemon và Compose CLI?** Testcontainers chủ yếu cần Docker API, Boot-managed Compose cần Docker CLI/Compose CLI. Nếu một trong hai thiếu, không chọn đường đó mà vẫn tuyên bố test backend thật.

**Câu 5: Lifecycle và cleanup thế nào?** Test method rollback không xóa commits ngoài thread; Compose stop không đồng nghĩa DB reset; context cache không đồng nghĩa container mới. Quy định rõ ai tạo/stop/xóa database.

**Câu 6: Có dùng service connection tự động?** Xác minh image/container type được Boot hỗ trợ, dependency hiện diện và không có hai nguồn connection details cạnh tranh. Assert database identity thực tế.

**Câu 7: Có cần chạy parallel/retry?** Dùng database/schema/project per job, unique test data và cleanup scoped. Tránh collision giữa nhiều Gradle invocations cùng source checkout.

### Quy tắc thực dụng

- **Bắt đầu với Testcontainers + @ServiceConnection** nếu integration test phụ thuộc một hoặc vài backends, project trên Boot 3.1+ và CI có Docker.
- **Chọn Boot Docker Compose-in-tests** khi Compose stack là một phần contract, team đã duy trì Compose file, Compose CLI sẵn có, và đã opt-in test mode.
- **Chọn external Compose do CI điều phối** khi test process không nên sở hữu lifecycle của stack, hoặc muốn dùng compose up/down ở pipeline rõ ràng.
- **Dùng H2/fake** cho test không đòi semantics Postgres, nhưng giữ một tầng integration bằng Postgres container để bảo vệ SQL/migrations quan trọng.

## 19. Câu hỏi tự kiểm tra

**1.** Boot 3.4 có spring-boot-docker-compose dependency, chạy ./gradlew test có tự start Compose mặc định? **Không**; skip.in-tests mặc định true.

**2.** Muốn Compose trong tests với Gradle cần hai điều kiện gì? **testAndDevelopmentOnly** dependency và **spring.docker.compose.skip.in-tests=false** trong test configuration.

**3.** Compose dùng ports: "5432" có bảo đảm host cũng là 5432? **Không**; host port có thể được publish động.

**4.** Spring Boot nhận JDBC URL từ đâu khi container được nhận diện? Từ **JdbcConnectionDetails** service connection, không cần URL hard-code.

**5.** @ServiceConnection chỉ cần spring-boot-starter-test là đủ? **Không**, cần **spring-boot-testcontainers**.

**6.** Testcontainers có cần Docker Engine? **Có** trong integration test chạy containers; nếu không có Docker, test không thể tự chạy Postgres container thật.

**7.** Có cần Docker Compose CLI riêng cho Testcontainers PostgreSQLContainer? **Không theo cách sử dụng PostgreSQLContainer trực tiếp**; Testcontainers dùng Docker API, còn Boot Docker Compose cần Compose CLI.

**8.** Testcontainers @Bean và JUnit static @Container có lifecycle giống hệt không? **Không**; bean theo Spring context, @Container theo JUnit extension/class lifecycle.

**9.** @DataJpaTest có thể dùng H2 thay datasource được mong đợi? **Có thể**, vì embedded DB replacement; cần config/connection assertions rõ.

**10.** @SpringBootTest tự rollback DML mỗi test? **Không**; cần @Transactional test khi phù hợp.

**11.** Test @Transactional gửi HTTP tới server thật đã commit row. Row có bị rollback cùng JUnit test? **Không tự động**, vì thread/transaction khác.

**12.** Boot service connections ưu tiên hay datasource properties luôn ưu tiên? **ConnectionDetails thường được auto-configuration ưu tiên** khi có bean phù hợp.

**13.** Compose stop có xóa volume dữ liệu không? **Không mặc định**. Xóa volumes là hành động khác cần giới hạn scope.

**14.** @DirtiesContext có đảm bảo PostgreSQL Compose database sạch không? **Không**; context reset không thay DB cleanup.

**15.** H2 pass có chứng minh PostgreSQL JSONB/locking/indexes đúng không? **Không**; cần database engine production khi có yêu cầu dialect.

**16.** Nếu custom image không được Boot nhận diện, nên làm gì? Kiểm tra **org.springframework.boot.service-connection** label/factory hoặc tự cung cấp ConnectionDetails/properties.

**17.** Testcontainers @Bean class muốn được Spring TestContext dùng cần gì? **@Import(TestConfiguration.class)** hoặc cách đăng ký test config được Spring hỗ trợ.

**18.** Healthcheck pg_isready có chứng minh schema/migrations đúng không? **Không**; chỉ giúp kiểm chứng DB sẵn sàng nhận connection, test phải query/validate schema riêng.

**19.** Nhiều CI jobs dùng chung một Compose project name có an toàn? **Không** nếu cùng stack/DB và destructive test setup; tách project/database/schema.

**20.** Khi chọn giữa Compose và Testcontainers, câu hỏi đầu tiên nên là gì? **Test đang chứng minh điều gì và ai sở hữu lifecycle của backend?**

### Checklist QA trước khi chốt

- Có xác định đúng **Spring Boot version** và capability của version đó?
- Có phân biệt Docker Engine, Compose CLI, Boot integration, Testcontainers và @ServiceConnection?
- Test dùng Compose đã đặt skip.in-tests=false và dependency testAndDevelopmentOnly?
- Compose file test có healthcheck, image supported, mapped port và lifecycle rõ?
- Testcontainers có spring-boot-testcontainers cùng driver/module tương ứng?
- Có loại bỏ việc Compose và Testcontainers cùng cấp competing connection details?
- Có assert PostgreSQL thật bằng query/database identity, không chỉ “test context started”?
- Có tránh hard-code host port 5432 nếu Docker mapping là dynamic?
- Có chỉ dùng ddl-auto=create-drop trên test DB do suite độc quyền sở hữu?
- Tests có rollback/cleanup side effects và không phụ thuộc dữ liệu còn lại?
- CI có Docker daemon, image pull access, Compose CLI nếu mode yêu cầu?
- Có quản lý project name/schema/parallel runs và contexts dùng chung DB?
- @DataJpaTest có kiểm soát embedded datasource replacement?
- Có dùng Testcontainers + @DynamicPropertySource khi Boot version không có @ServiceConnection?
- Có chạy test riêng cho từng mode và ghi rõ khi chưa thực chạy?
- Lệnh destructive Compose/database chỉ áp dụng tài nguyên test được phép sở hữu?

**Kết luận:** Docker Compose trong Spring Boot 3.4 **không được bật tự động khi chạy test**; muốn dùng phải thêm dependency đúng test classpath và opt-in qua **spring.docker.compose.skip.in-tests=false**. **Testcontainers + @ServiceConnection** cung cấp một đường integration test thuận tiện với lifecycle được kiểm soát gần test và random port tự động. Chọn Compose nếu muốn kiểm thử stack YAML/orchestration hoặc tận dụng nền tảng development đã có; chọn Testcontainers nếu muốn kiểm thử một backend thật độc lập theo test context; chọn external Compose nếu CI sở hữu stack. Trong mọi trường hợp, phải đảm bảo **readiness, connection source, transaction/fixture cleanup, Docker availability và isolation** trước khi coi test đáng tin.

## Tài liệu chính thức

- Spring Boot 3.4 — Development-time Services / Docker Compose in Tests: https://docs.spring.io/spring-boot/3.4/reference/features/dev-services.html
- Spring Boot 3.4 — Testcontainers, JUnit lifecycle, Spring-managed container beans, Service Connections: https://docs.spring.io/spring-boot/3.4/reference/testing/testcontainers.html
- Spring Boot 3.4 — Common Application Properties (spring.docker.compose.*): https://docs.spring.io/spring-boot/3.4/appendix/application-properties/
- Spring Boot 3.4 — Docker Compose How-to, custom JDBC parameters and sharing services: https://docs.spring.io/spring-boot/3.4/how-to/docker-compose.html
- Spring Boot 3.4 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.4/reference/testing/spring-boot-applications.html
- Testcontainers Java — PostgreSQL Module: https://java.testcontainers.org/modules/databases/postgres/
- Docker — Compose specification, healthcheck and ports: https://docs.docker.com/compose/compose-file/

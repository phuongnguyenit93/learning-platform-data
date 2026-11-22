# Dự án REST API Spring Boot trên Cloud Run và Cloud SQL

Trong dự án này, người học sẽ tự xây dựng và triển khai một **REST API Java Spring Boot** quản lý công việc (Task API), sử dụng **Cloud SQL for PostgreSQL** làm cơ sở dữ liệu và **Cloud Run** làm nền tảng chạy ứng dụng. Thay vì chỉ triển khai một endpoint “Hello World”, ta đi trọn vòng đời: tổ chức Google Cloud project, thiết kế dữ liệu và mã nguồn, xác thực và phân quyền, kiểm thử, tạo cơ sở dữ liệu, quản lý mật khẩu, build/deploy, gọi API, quan sát hoạt động, tối ưu chi phí và thu hồi tài nguyên.

Đây là một bài thực hành trong module **CLOUD_PROVIDERS_GCP**: người học áp dụng kiến thức về project, IAM và VPC cùng Compute Engine/GKE/Cloud Run, lưu trữ, cơ sở dữ liệu, tự động hóa phát hành và theo dõi độ tin cậy/chi phí. Dự án chọn Cloud Run vì ứng dụng HTTP stateless không cần quản trị VM hoặc cluster; chọn Cloud SQL vì cần giao dịch và quan hệ dữ liệu SQL. Các ví dụ dùng **Java 21**, **Spring Boot 3.5.x**, **Maven**, **PostgreSQL 16** và **Cloud SQL Java Connector**. Khi sử dụng thực tế, kiểm tra lịch hỗ trợ runtime và bản vá dependency tại thời điểm triển khai.

> **Giới hạn thực hành:** Những lệnh gcloud trong bài là hướng dẫn để người học chủ động chạy trên **project thử nghiệm của riêng mình**. Chúng có thể tạo tài nguyên **phát sinh phí**, đặc biệt Cloud SQL instance. Bài học không tự động thực thi lệnh, không tạo tài nguyên trong tài khoản người học và không yêu cầu đưa credential hay password vào source control.

## 1. Kết quả cần đạt

Sau khi hoàn thành, người học có thể:

1. Tạo cấu trúc một REST API gồm controller, repository, model và database migration.
2. Thiết kế các endpoint tạo, liệt kê, xem, hoàn thành và xóa công việc.
3. Kiểm tra dữ liệu đầu vào, trả HTTP status phù hợp và tránh ghép chuỗi SQL không an toàn.
4. Chạy ứng dụng với PostgreSQL local và kiểm thử tự động bằng JUnit 5/Testcontainers.
5. Tạo Cloud SQL PostgreSQL instance và database trong GCP project được cấp quyền.
6. Dùng Cloud SQL Java Connector để kết nối với Cloud SQL qua IAM và kết nối được mã hóa; phân biệt IAM với quyền đăng nhập PostgreSQL.
7. Lưu DB password trong Secret Manager thay vì code, Docker image hoặc Git.
8. Tạo service account Cloud Run có quyền tối thiểu và triển khai ứng dụng từ source bằng Cloud Build/buildpacks.
9. Gọi API có xác thực, xem log/metric, tính connection budget, kiểm tra lỗi và rollback revision.
10. Xóa tài nguyên đúng phạm vi sau thực hành để tránh chi phí kéo dài.

### 1.1. Đặc tả API

| Phương thức | Đường dẫn | Ý nghĩa | Kết quả kỳ vọng |
|---|---|---|---|
| `POST` | `/api/tasks` | Tạo công việc | `201 Created` và đối tượng mới |
| `GET` | `/api/tasks` | Danh sách tối đa 100 công việc mới nhất | `200 OK` |
| `GET` | `/api/tasks/{id}` | Xem chi tiết | `200 OK` hoặc `404 Not Found` |
| `PATCH` | `/api/tasks/{id}/complete` | Đánh dấu hoàn thành | `200 OK` hoặc `404 Not Found` |
| `DELETE` | `/api/tasks/{id}` | Xóa công việc | `204 No Content` hoặc `404 Not Found` |
| `GET` | `/actuator/health` | Kiểm tra tiến trình sẵn sàng | `200 OK` khi health đạt |

API dùng JSON, mã hóa UTF-8 và timestamp theo UTC. Để tránh truy vấn không giới hạn, endpoint danh sách trong phiên bản bài tập chỉ trả tối đa 100 bản ghi. Phần mở rộng sẽ thêm cursor-based pagination và authentication/authorization cấp người dùng.

### 1.2. Kiến trúc mục tiêu

~~~mermaid
flowchart LR
    Dev[Developer / CI] -->|Source deployment| Build[Cloud Build + buildpacks]
    Build --> Reg[Artifact Registry image]
    Reg --> Run[Cloud Run tasks-api]
    Caller[Authenticated caller] -->|HTTPS + ID token| Run
    Run -->|ADC / Cloud SQL Java Connector| SQL[(Cloud SQL PostgreSQL)]
    Secret[Secret Manager: DB password] -->|Cloud Run secret reference| Run
    SA[Runtime service account] -->|IAM Cloud SQL Client + Secret Accessor| Run
    Run --> Logs[Cloud Logging / Monitoring]
~~~

**Đường đi request:** client đã được phép gọi Cloud Run → Spring Boot controller → JdbcTemplate/HikariCP → PostgreSQL database. Cloud Run có thể tạo thêm instance khi tăng traffic; mỗi instance mở một connection pool riêng nên tổng số kết nối database cần được giới hạn.

**Đường đi triển khai:** repository source → Cloud Build/buildpacks → container image trong Artifact Registry → Cloud Run revision. Cloud Run không lưu state nghiệp vụ; database trên Cloud SQL là nguồn dữ liệu có thẩm quyền.

## 2. Yêu cầu và điều kiện an toàn

### 2.1. Công cụ cục bộ

- JDK 21 và Maven hoặc Maven Wrapper; kiểm tra bằng `java -version` và `./mvnw -version`.
- Docker/Podman để chạy PostgreSQL local và Testcontainers.
- Google Cloud CLI (`gcloud`) đã đăng nhập.
- Công cụ gửi HTTP request như curl, HTTPie hoặc Postman.
- Trình soạn thảo Java và kiến thức cơ bản về Maven, SQL, Spring MVC.

Nếu chạy trên Windows, dùng PowerShell tương đương hoặc WSL cho các ví dụ shell Bash. Các lệnh `export`, `$(...)` và dấu nối dòng `\` được viết theo Bash, không dán trực tiếp vào PowerShell 5.1.

### 2.2. GCP project và billing

Dùng một **Google Cloud project dành riêng cho lab**, không dùng project production. Người học phải có quyền tạo/bật dịch vụ, tạo Cloud SQL instance, service account, secret và deploy Cloud Run; ở môi trường tổ chức, có thể nhờ platform admin provision các bước này.

| Hạng mục | Quyền hoặc vai trò thường cần | Phạm vi |
|---|---|---|
| Bật API | Service Usage Admin hoặc quyền tương đương | Project lab |
| Tạo Cloud SQL | Cloud SQL Admin hoặc custom role | Project lab |
| Tạo runtime identity | Service Account Admin | Project lab |
| Deploy Cloud Run | Cloud Run Admin/Developer, Service Account User | Service/project |
| Source build | Cloud Run Source Developer và build service account phù hợp | Project lab |
| Đọc secret khi chạy | Secret Manager Secret Accessor | Một secret |
| Kết nối Cloud SQL bằng connector | Cloud SQL Client | Project chứa instance |
| Gọi service private | Cloud Run Invoker | Service cụ thể |

Không cấp `Owner` hoặc `Editor` cho runtime service account để “chữa” lỗi permission. Role của **deployer**, **build identity** và **runtime identity** có trách nhiệm khác nhau.

### 2.3. Chi phí dự kiến

Cloud Run có mô hình tính phí theo tài nguyên/yêu cầu, nhưng **Cloud SQL instance vẫn có chi phí khi không có request**, cùng với storage, backup, network, build và logging. Bật Cloud Billing budget/alerts cho project lab; budget alert **không phải hard cap**. Chuẩn bị phương án xóa resource ngay khi hoàn thành.

### 2.4. Thông số mẫu

Những biến sau dùng thống nhất trong bài:

~~~bash
export PROJECT_ID="YOUR_UNIQUE_GCP_PROJECT_ID"
export REGION="asia-southeast1"
export SERVICE="tasks-api"
export SQL_INSTANCE="tasks-pg-lab"
export DB_NAME="tasksdb"
export DB_USER="tasks_app"
export SA_NAME="tasks-api-runtime"
export SA_EMAIL="$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"
export INSTANCE_CONNECTION_NAME="$PROJECT_ID:$REGION:$SQL_INSTANCE"

gcloud config set project "$PROJECT_ID"
gcloud config get-value project
~~~

Thay các giá trị mẫu bằng project và region được phép sử dụng. Cloud Run và Cloud SQL được đặt **cùng region** để giảm latency, network cost và phụ thuộc liên vùng. Trong production, region cần đáp ứng data residency, quota, service availability, HA/DR và SLO.

## 3. Chuẩn bị GCP project và API

### 3.1. Kiểm tra danh tính và project

~~~bash
gcloud auth login
gcloud config set project "$PROJECT_ID"
gcloud auth list
gcloud projects describe "$PROJECT_ID" \
  --format="table(projectId,name,lifecycleState)"
~~~

Lệnh `gcloud auth login` phục vụ CLI. Java client library dùng **Application Default Credentials (ADC)**, có thể khác danh tính CLI. Trong Cloud Run, ADC được lấy từ **runtime service account**; không cần copy JSON key.

### 3.2. Bật các API

~~~bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com \
  iam.googleapis.com \
  --project="$PROJECT_ID"
~~~

Nếu organization policy chặn API hoặc quota, dừng để quản trị viên phê duyệt; không chuyển sang project production làm đường vòng. Việc bật API cần vai trò Service Usage phù hợp.

### 3.3. Billing và guardrails

Trước khi tạo database:

1. Kiểm tra project liên kết đúng billing account thử nghiệm.
2. Tạo budget và thông báo cho owner.
3. Xác định ai có quyền xóa Cloud SQL instance sau buổi học.
4. Xem bảng giá Cloud SQL ở region dự kiến và xác nhận cấu hình đủ nhỏ cho lab.
5. Đặt quy ước tên tài nguyên có suffix lab, không chứa dữ liệu khách hàng.

Không xóa hoặc sửa tài nguyên có cùng tên nhưng thuộc project khác; mọi lệnh quản trị nên dùng `--project="$PROJECT_ID"` hoặc kiểm tra active project.

## 4. Tạo project Spring Boot bằng Maven

### 4.1. Cấu trúc thư mục đề xuất

~~~text
tasks-api/
├── pom.xml
├── mvnw
├── .mvn/
├── project.toml
├── src/
│   ├── main/
│   │   ├── java/com/example/tasks/
│   │   │   ├── TasksApplication.java
│   │   │   ├── TaskDtos.java
│   │   │   ├── TaskRepository.java
│   │   │   ├── TaskController.java
│   │   │   └── CloudSqlDataSourceConfig.java
│   │   └── resources/
│   │       ├── application.yml
│   │       └── db/migration/V1__create_tasks.sql
│   └── test/java/com/example/tasks/
│       └── TaskApiIntegrationTest.java
└── .gitignore
~~~

Các code block tiếp theo tương ứng với các file cùng tên. Có thể tạo skeleton bằng [Spring Initializr](https://start.spring.io/) với Java 21, Maven, Spring Web, JDBC, Validation, Actuator và PostgreSQL; hoặc dùng một project Maven trống rồi điền cấu hình bên dưới.

### 4.2. Maven pom.xml

Ví dụ này cố định Spring Boot 3.5.16 (một bản có thật của dòng 3.5) và Cloud SQL Java Connector 1.30.0. Những version này dùng cho **lab tại thời điểm viết**; khi dùng production phải đánh giá security advisories, compatibility và bản vá mới. Không dùng placeholder version `LATEST` trong build.

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>tasks-api</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <properties>
    <java.version>21</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
      <groupId>org.postgresql</groupId>
      <artifactId>postgresql</artifactId>
      <scope>runtime</scope>
    </dependency>
    <dependency>
      <groupId>org.flywaydb</groupId>
      <artifactId>flyway-core</artifactId>
    </dependency>
    <dependency>
      <groupId>org.flywaydb</groupId>
      <artifactId>flyway-database-postgresql</artifactId>
    </dependency>
    <dependency>
      <groupId>com.google.cloud.sql</groupId>
      <artifactId>postgres-socket-factory</artifactId>
      <version>1.30.0</version>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-testcontainers</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.testcontainers</groupId>
      <artifactId>postgresql</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.testcontainers</groupId>
      <artifactId>junit-jupiter</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Spring Boot parent quản lý nhiều phiên bản dependency/plugin; chỉ override khi có yêu cầu kiểm soát hợp lý. Maven Wrapper nên được commit vào repository để CI và developer dùng cùng phiên bản Maven.

### 4.3. Main class

File `src/main/java/com/example/tasks/TasksApplication.java`:

~~~java
package com.example.tasks;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TasksApplication {
    public static void main(String[] args) {
        SpringApplication.run(TasksApplication.class, args);
    }
}
~~~

### 4.4. DTO và validation

File `src/main/java/com/example/tasks/TaskDtos.java`:

~~~java
package com.example.tasks;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.time.Instant;

record CreateTaskRequest(
        @NotBlank @Size(max = 200) String title) {
}

record TaskResponse(
        long id, String title, boolean completed, Instant createdAt) {
}
~~~

Hai record được dùng trong cùng package nên có thể để package-private trong một file. Validation được kích hoạt khi controller dùng `@Valid`. Không lưu trực tiếp input từ người dùng vào tên bảng/column trong SQL.

## 5. Thiết kế bảng PostgreSQL và migration

### 5.1. Schema

File `src/main/resources/db/migration/V1__create_tasks.sql`:

~~~sql
CREATE TABLE tasks (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    completed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_tasks_created_at
    ON tasks (created_at DESC, id DESC);
~~~

**Flyway** phát hiện file migration có tên dạng `V1__*.sql` và quản lý lịch sử schema trong bảng `flyway_schema_history`. Khi phát hành migration V2, tạo file mới; không sửa V1 sau khi nó đã được áp dụng trên môi trường chung. Trong production, nên chạy schema migration bằng deployment step/Cloud Run Job có identity database riêng thay vì để mọi instance Cloud Run tự chạy DDL trong startup.

### 5.2. Cấu hình application.yml

File `src/main/resources/application.yml`:

~~~yaml
server:
  address: 0.0.0.0
  port: ${PORT:8080}

spring:
  application:
    name: tasks-api
  flyway:
    enabled: true

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      probes:
        enabled: true
~~~

Spring Boot lấy giá trị `PORT` do Cloud Run cấp hoặc dùng 8080 khi chạy local. Không bật toàn bộ Actuator endpoints ra Internet. Cloud Run request authentication chỉ kiểm soát người có quyền gọi service; ứng dụng vẫn cần authentication/authorization ở tầng domain nếu phục vụ nhiều người dùng với quyền khác nhau.

## 6. Repository: truy vấn SQL an toàn

File `src/main/java/com/example/tasks/TaskRepository.java`:

~~~java
package com.example.tasks;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class TaskRepository {
    private static final RowMapper<TaskResponse> TASK_MAPPER =
            (rs, rowNumber) -> fromRow(rs);

    private final JdbcTemplate jdbc;

    public TaskRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<TaskResponse> findRecent() {
        return jdbc.query("""
                SELECT id, title, completed, created_at
                FROM tasks
                ORDER BY created_at DESC, id DESC
                LIMIT 100
                """, TASK_MAPPER);
    }

    public Optional<TaskResponse> findById(long id) {
        return jdbc.query("""
                SELECT id, title, completed, created_at
                FROM tasks WHERE id = ?
                """, TASK_MAPPER, id).stream().findFirst();
    }

    public TaskResponse create(String title) {
        Long id = jdbc.queryForObject(
                "INSERT INTO tasks(title) VALUES (?) RETURNING id",
                Long.class, title);
        return findById(id).orElseThrow();
    }

    public boolean complete(long id) {
        return jdbc.update(
                "UPDATE tasks SET completed = TRUE WHERE id = ?", id) == 1;
    }

    public boolean delete(long id) {
        return jdbc.update("DELETE FROM tasks WHERE id = ?", id) == 1;
    }

    private static TaskResponse fromRow(ResultSet rs)
            throws SQLException {
        return new TaskResponse(
                rs.getLong("id"),
                rs.getString("title"),
                rs.getBoolean("completed"),
                rs.getTimestamp("created_at").toInstant());
    }
}
~~~

Các câu SQL sử dụng placeholder `?` và parameter binding của `JdbcTemplate`, không nối dữ liệu nhập thành SQL string. Với ứng dụng lớn hơn, tách thêm service layer để giữ business rules, transaction, authorization và idempotency thay vì đặt hết logic trong controller.

## 7. Controller: REST endpoints và HTTP semantics

File `src/main/java/com/example/tasks/TaskController.java`:

~~~java
package com.example.tasks;

import jakarta.validation.Valid;
import java.net.URI;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/tasks")
public class TaskController {
    private final TaskRepository repository;

    public TaskController(TaskRepository repository) {
        this.repository = repository;
    }

    @GetMapping
    public List<TaskResponse> list() {
        return repository.findRecent();
    }

    @GetMapping("/{id}")
    public TaskResponse get(@PathVariable long id) {
        return repository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Task not found"));
    }

    @PostMapping
    public ResponseEntity<TaskResponse> create(
            @Valid @RequestBody CreateTaskRequest request) {
        TaskResponse created =
                repository.create(request.title().trim());
        return ResponseEntity
                .created(URI.create("/api/tasks/" + created.id()))
                .body(created);
    }

    @PatchMapping("/{id}/complete")
    public TaskResponse complete(@PathVariable long id) {
        if (!repository.complete(id)) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Task not found");
        }
        return get(id);
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable long id) {
        if (!repository.delete(id)) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Task not found");
        }
        return ResponseEntity.noContent().build();
    }
}
~~~

### 7.1. Vì sao dùng những status này?

- `201 Created` kèm `Location`: resource đã được tạo.
- `200 OK`: trả representation của resource khi GET/PATCH thành công.
- `204 No Content`: xóa thành công và response không có body.
- `400 Bad Request`: dữ liệu đầu vào không hợp lệ do `@Valid`.
- `404 Not Found`: không có task mang ID đã yêu cầu.
- `500 Internal Server Error`: lỗi bất ngờ, cần log và khắc phục; không trả stack trace hoặc SQL password cho caller.

Ứng dụng lab đơn giản chưa có pagination chuẩn, giới hạn người dùng, rate limiting hay chống concurrent edits. Đó là phần mở rộng, không phải thuộc tính tự động có sẵn từ Cloud Run.

## 8. Chạy và kiểm thử với PostgreSQL local

### 8.1. Chạy PostgreSQL container

Chỉ dùng password ví dụ bên dưới ở **máy local/test**; không dùng cho Cloud SQL hoặc production:

~~~bash
docker run --rm -d \
  --name tasks-postgres-local \
  -e POSTGRES_DB=tasksdb \
  -e POSTGRES_USER=tasks_local \
  -e POSTGRES_PASSWORD=local-lab-only \
  -p 5432:5432 \
  postgres:16
~~~

Đặt biến môi trường và chạy ứng dụng:

~~~bash
export SPRING_DATASOURCE_URL="jdbc:postgresql://localhost:5432/tasksdb"
export SPRING_DATASOURCE_USERNAME="tasks_local"
export SPRING_DATASOURCE_PASSWORD="local-lab-only"

./mvnw spring-boot:run
~~~

Khi application chạy local không bật profile `cloud`, Spring Boot auto-configure DataSource từ các biến môi trường trên. Flyway tạo bảng `tasks` trong database local. Nếu port 5432 đã bị chiếm, đổi mapping Docker và JDBC URL tương ứng.

### 8.2. Gọi API local

~~~bash
curl -i http://localhost:8080/actuator/health

curl -i -X POST http://localhost:8080/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"title":"Viết tài liệu Spring Boot"}'

curl -s http://localhost:8080/api/tasks
curl -s http://localhost:8080/api/tasks/1
curl -i -X PATCH http://localhost:8080/api/tasks/1/complete
curl -i -X DELETE http://localhost:8080/api/tasks/1
~~~

ID `1` chỉ đúng nếu đây là bản ghi đầu tiên. Với database đã có dữ liệu, hãy lấy `id` từ response POST thay vì giả định.

### 8.3. Kết quả kiểm thử bằng tay

| Hành động | Kỳ vọng |
|---|---|
| POST title hợp lệ | 201, có ID, completed=false |
| GET theo ID vừa tạo | 200, nội dung khớp |
| PATCH complete | 200, completed=true |
| DELETE theo ID | 204 |
| GET sau DELETE | 404 |
| POST title rỗng | 400, không tạo record |
| POST title dài hơn 200 ký tự | 400 |

## 9. Kiểm thử tích hợp tự động với Testcontainers

Testcontainers giúp chạy PostgreSQL tạm trong môi trường test, xác nhận Flyway, JDBC và REST endpoint mà chưa cần tài nguyên GCP thật.

File `src/test/java/com/example/tasks/TaskApiIntegrationTest.java`:

~~~java
package com.example.tasks;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.http.ResponseEntity;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class TaskApiIntegrationTest {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> db =
            new PostgreSQLContainer<>("postgres:16");

    @Autowired
    TestRestTemplate http;

    @Test
    void createThenReadTask() {
        ResponseEntity<TaskResponse> created =
                http.postForEntity(
                        "/api/tasks",
                        new CreateTaskRequest("test from JUnit"),
                        TaskResponse.class);

        assertThat(created.getStatusCode().value()).isEqualTo(201);
        assertThat(created.getBody()).isNotNull();

        long id = created.getBody().id();
        TaskResponse loaded =
                http.getForObject("/api/tasks/" + id,
                        TaskResponse.class);

        assertThat(loaded.title()).isEqualTo("test from JUnit");
        assertThat(loaded.completed()).isFalse();
    }
}
~~~

Chạy:

~~~bash
./mvnw -B clean verify
~~~

Lưu ý: Docker phải chạy để Testcontainers tạo PostgreSQL. Nếu có cả Docker container local trên port 5432 và Testcontainers, `@ServiceConnection` dùng datasource của container test, không cần dùng database phát triển. Test này xác minh REST + PostgreSQL thật nhưng **chưa kiểm thử IAM, network và Cloud SQL**; cần một smoke/integration test trên project GCP sau deploy.

### 9.1. Các test nên bổ sung

- POST title rỗng và title vượt 200 ký tự → 400.
- GET/PATCH/DELETE với ID không tồn tại → 404.
- Tạo nhiều task, xác minh sorting/limit 100.
- Test concurrent update và transaction khi bổ sung quy tắc nghiệp vụ.
- Test Flyway migration trên database sạch.
- Test lỗi database timeout và health behavior.
- Test không ghi password hoặc giá trị secret ra log.

## 10. Tạo Cloud SQL PostgreSQL trong project lab

### 10.1. Tạo instance

Đây là bước **có chi phí liên tục**, cần xác nhận project/region trước khi chạy:

~~~bash
gcloud sql instances create "$SQL_INSTANCE" \
  --project="$PROJECT_ID" \
  --database-version=POSTGRES_16 \
  --edition=ENTERPRISE \
  --tier=db-custom-1-3840 \
  --region="$REGION" \
  --storage-size=10 \
  --assign-ip
~~~

Ví dụ dùng cấu hình một instance nhỏ cho lab, không phải template production. Tùy quota, chính sách tổ chức, vùng và thay đổi catalog, tier có thể cần chỉnh. Đối với môi trường production, đánh giá HA, backup/PITR, maintenance, deletion protection, private IP và DR thay vì sử dụng nguyên cấu hình lab.

### 10.2. Xem trạng thái và connection name

~~~bash
gcloud sql instances describe "$SQL_INSTANCE" \
  --project="$PROJECT_ID" \
  --format="table(name,region,state,connectionName)"
~~~

Connection name có dạng `PROJECT_ID:REGION:INSTANCE`. Đây không phải mật khẩu. Cloud SQL Java Connector sẽ sử dụng tên này để tìm instance, lấy thông tin kết nối và thiết lập kết nối xác thực/mã hóa.

### 10.3. Tạo database

~~~bash
gcloud sql databases create "$DB_NAME" \
  --instance="$SQL_INSTANCE" \
  --project="$PROJECT_ID"
~~~

### 10.4. Tạo người dùng PostgreSQL

Trong Console chọn Cloud SQL instance → **Users** → tạo user PostgreSQL kiểu built-in tên `tasks_app` với **mật khẩu mạnh, duy nhất cho lab**. Hoặc có thể tạo user bằng gcloud rồi dùng lệnh đổi mật khẩu có prompt để tránh đưa mật khẩu trực tiếp vào shell history:

~~~bash
gcloud sql users create "$DB_USER" \
  --instance="$SQL_INSTANCE" \
  --project="$PROJECT_ID"

gcloud sql users set-password "$DB_USER" \
  --instance="$SQL_INSTANCE" \
  --project="$PROJECT_ID" \
  --prompt-for-password
~~~

Không xuất password ra log hoặc commit vào Git. Lệnh đầu tạo user nhưng user chưa dùng được cho password authentication cho đến khi mật khẩu đã được đặt. Nếu Cloud SQL organization policy hoặc phiên bản CLI yêu cầu quy trình khác, dùng Console để tạo và đặt mật khẩu tương đương.

Trong lab, user này cần đủ quyền tạo bảng Flyway trong database `tasksdb`. Trong **production**, nên tách một **migration user** có quyền DDL khỏi **runtime user** chỉ được SELECT/INSERT/UPDATE/DELETE trên bảng và USAGE trên sequence; quyền PostgreSQL phải được cấu hình tại database/schema, không chỉ bằng IAM role Cloud SQL Client.

### 10.5. Public IP hay private IP?

Tài liệu dùng Cloud SQL **public IP** và **Cloud SQL Java Connector** để giữ lab tương đối ngắn gọn. Kết nối qua connector dùng IAM cho việc thiết lập kết nối, mã hóa transport và database authentication riêng. Nó không đồng nghĩa mở PostgreSQL tự do cho Internet; không cấu hình authorized networks rộng như `0.0.0.0/0`.

Với production cần private connectivity, dùng Cloud SQL private IP/PSC theo kiến trúc và **Cloud Run Direct VPC egress** hoặc Serverless VPC Access phù hợp. Khi chọn private IP trong Java connector, dùng `ipTypes=PRIVATE` và bảo đảm network path tồn tại. **Connector không tự tạo đường mạng nếu VPC route chưa có.**

## 11. Lưu DB password trong Secret Manager

### 11.1. Tạo secret

~~~bash
gcloud secrets create tasks-db-password \
  --project="$PROJECT_ID" \
  --replication-policy=automatic
~~~

Tại Google Cloud Console → **Secret Manager** → `tasks-db-password` → **Add new version**, nhập đúng mật khẩu đã đặt cho DB user `tasks_app`. Cách nhập qua giao diện tránh đặt plaintext password trong command arguments và shell history. Ghi nhận version mới (thường là `1` với secret mới).

Trong môi trường có automation, có thể dùng secret provisioning pipeline hoặc stdin/secret manager phù hợp, tuyệt đối không đưa mật khẩu vào YAML/source code, Dockerfile, log build hoặc `--set-env-vars`.

### 11.2. Tạo runtime service account

~~~bash
gcloud iam service-accounts create "$SA_NAME" \
  --project="$PROJECT_ID" \
  --display-name="Cloud Run tasks-api runtime"
~~~

### 11.3. Cấp quyền đúng phạm vi

~~~bash
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/cloudsql.client"

gcloud secrets add-iam-policy-binding tasks-db-password \
  --project="$PROJECT_ID" \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/secretmanager.secretAccessor"
~~~

`roles/cloudsql.client` phục vụ cơ chế kết nối Cloud SQL; **không thay thế** tài khoản/mật khẩu hay quyền SQL bên trong PostgreSQL. Secret Accessor được cấp **trên một secret**, không cần toàn bộ secrets của project. Không cấp Cloud SQL Admin hoặc Secret Manager Admin cho runtime chỉ vì ứng dụng cần đọc/ghi task.

## 12. Kết nối JDBC từ Cloud Run bằng Cloud SQL Java Connector

Sử dụng Cloud SQL Java Connector như một socket factory cho PostgreSQL JDBC driver. Nó dùng **ADC của runtime service account** để xác thực với Cloud SQL, không yêu cầu JSON credential file.

### 12.1. DataSource config cho profile cloud

File `src/main/java/com/example/tasks/CloudSqlDataSourceConfig.java`:

~~~java
package com.example.tasks;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
@Profile("cloud")
public class CloudSqlDataSourceConfig {
    @Bean
    DataSource dataSource(
            @Value("${DB_NAME}") String database,
            @Value("${DB_USER}") String username,
            @Value("${DB_PASS}") String password,
            @Value("${INSTANCE_CONNECTION_NAME}") String instance) {

        HikariConfig config = new HikariConfig();
        config.setJdbcUrl("jdbc:postgresql:///" + database);
        config.setUsername(username);
        config.setPassword(password);
        config.setMaximumPoolSize(5);
        config.setMinimumIdle(0);
        config.setConnectionTimeout(10000);
        config.setIdleTimeout(600000);
        config.setMaxLifetime(1800000);

        config.addDataSourceProperty(
                "socketFactory",
                "com.google.cloud.sql.postgres.SocketFactory");
        config.addDataSourceProperty(
                "cloudSqlInstance", instance);
        config.addDataSourceProperty("ipTypes", "PUBLIC");
        config.addDataSourceProperty(
                "cloudSqlRefreshStrategy", "lazy");

        return new HikariDataSource(config);
    }
}
~~~

Ở chế độ **cloud**, Bean DataSource được tạo từ DB_NAME, DB_USER, DB_PASS, INSTANCE_CONNECTION_NAME. Ở chế độ local/test, profile cloud không active nên Spring Boot sử dụng auto-configuration với `SPRING_DATASOURCE_URL` hoặc Testcontainers.

Google Cloud khuyến nghị `cloudSqlRefreshStrategy=lazy` cho serverless để tránh background refresh trên instance khi CPU không được cấp liên tục. `ipTypes=PUBLIC` phù hợp Cloud SQL public-IP lab; thay bằng PRIVATE chỉ khi đã tạo private IP và đường VPC egress.

**Không trộn hai cơ chế một cách không chủ đích:** Java Connector kết nối theo socket factory đã cấu hình; không bắt buộc dùng cờ `--add-cloudsql-instances` chỉ để mount Unix socket trong ví dụ này. Nếu chọn Cloud Run built-in Cloud SQL connection/Unix socket thay cho Java Connector, cấu hình JDBC và cách mount socket sẽ khác.

### 12.2. Tính ngân sách connection pool

Ví dụ Cloud Run `--max-instances=3`, mỗi instance Hikari `maximumPoolSize=5`:

\[
\text{MaxConnections}_{\text{API}} \approx
3 \times 5 = 15 .
\]

Phải cộng cả migration, admin sessions, job và service khác dùng chung Cloud SQL. Nếu tăng maximum instances lên 50 nhưng vẫn giữ pool 20, ứng dụng có thể đòi tới 1.000 kết nối, vượt khả năng instance. Cần load test, timeout, backpressure hoặc connection pooling chuyên biệt phù hợp, không chỉ tăng quota ứng dụng.

### 12.3. Flyway ở runtime

Với lab, Flyway chạy schema migration khi ứng dụng startup. Để đi production:

- Tách Flyway thành CI/CD migration step hoặc Cloud Run Job với DB DDL role.
- Chạy migration backward-compatible trước khi chuyển traffic.
- Chỉ sau khi migration pass, deploy image/revision mới.
- Không tự sửa migration V1 đã được apply.
- Kiểm tra database schema backup và rollback strategy khi thay đổi phá vỡ tương thích.

## 13. Build và deploy từ source lên Cloud Run

### 13.1. Cố định Java runtime trong buildpacks

File `project.toml` tại thư mục gốc:

~~~toml
[[build.env]]
name = "GOOGLE_RUNTIME_VERSION"
value = "21"
~~~

Cloud Buildpacks đọc cấu hình để chọn Java major version thay vì âm thầm chọn mặc định mới hơn. Maven sử dụng Java 21; runtime container cũng chạy Java 21. Khi nâng JDK, phải kiểm tra Spring Boot/dependency, class-file version, base image và lịch hỗ trợ Cloud Run.

### 13.2. Build/test trước deploy

~~~bash
./mvnw -B clean verify
~~~

Không bỏ test trên CI chỉ để build nhanh. Nếu developer machine không có Docker, cần sửa môi trường Testcontainers; đừng gỡ test integration mà không có thay thế.

### 13.3. Quyền của build identity

Deploy source dùng Cloud Build và Artifact Registry. Ngoài quyền người triển khai (`roles/run.sourceDeveloper`, Service Account User trên runtime identity và các quyền deploy), **Cloud Build service account** cần quyền build/deploy tương ứng, thường có `roles/run.builder` theo hướng dẫn Cloud Run. Mặc định build identity có thể khác nhau theo project và organization policy.

Nếu gặp lỗi `PERMISSION_DENIED` ở Cloud Build, xác minh identity đang thực thi build trước khi cấp quyền. Không tự động cấp Owner/Editor cho default service account.

### 13.4. Lệnh triển khai

Tại thư mục có `pom.xml`:

~~~bash
gcloud run deploy "$SERVICE" \
  --project="$PROJECT_ID" \
  --source=. \
  --region="$REGION" \
  --service-account="$SA_EMAIL" \
  --set-env-vars="SPRING_PROFILES_ACTIVE=cloud,DB_NAME=$DB_NAME,DB_USER=$DB_USER,INSTANCE_CONNECTION_NAME=$INSTANCE_CONNECTION_NAME" \
  --update-secrets="DB_PASS=tasks-db-password:1" \
  --no-allow-unauthenticated \
  --memory=1Gi \
  --cpu=1 \
  --concurrency=20 \
  --max-instances=3 \
  --min-instances=0
~~~

Giải thích các thành phần:

- `--source=.`: Cloud Build/buildpacks xây image từ source, lưu trong Artifact Registry rồi deploy.
- `--service-account`: Cloud Run revision dùng runtime identity riêng.
- `SPRING_PROFILES_ACTIVE=cloud`: chọn cấu hình Cloud SQL Java Connector.
- `--update-secrets`: Cloud Run lấy DB password từ Secret Manager khi instance khởi động.
- `--no-allow-unauthenticated`: giữ API private, chỉ caller có quyền Invoker gọi được.
- `--max-instances=3`: giới hạn độ mở rộng ban đầu để bảo vệ Cloud SQL.
- `--min-instances=0`: cho phép scale về 0 khi không có traffic, có thể có cold start.

Ở production, dùng image digest đã được build/test/scan và promote qua môi trường thay vì rebuild source độc lập tại mỗi deployment. Tùy chính sách tổ chức, Cloud Run source deployment có thể yêu cầu quyền Artifact Registry, Cloud Build service account, quota hoặc repository setup bổ sung.

### 13.5. Kiểm tra trạng thái

~~~bash
gcloud run services describe "$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format="table(metadata.name,status.url,status.latestReadyRevisionName)"

gcloud run revisions list \
  --service="$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION"
~~~

Nếu service không ready, xem Cloud Logging trước khi thay cấu hình tùy tiện. Các lỗi thường gặp: thiếu secret, sai user/password, không có quyền Cloud SQL Client, Java connector không kết nối được IP, Flyway DDL bị từ chối hoặc thiếu `PORT`/startup timeout.

## 14. Gọi REST API có xác thực

### 14.1. Grant Invoker cho đúng người thử

Người thử API phải được cấp `roles/run.invoker` trên service. Quản trị viên có thể làm:

~~~bash
export TEST_CALLER_EMAIL="YOUR_ACCOUNT_EMAIL"

gcloud run services add-iam-policy-binding "$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --member="user:$TEST_CALLER_EMAIL" \
  --role="roles/run.invoker"
~~~

Không cấp Invoker cho `allUsers` nếu lab chủ đích kiểm thử private service. Với CI hoặc service-to-service, cấp cho một service account caller cụ thể.

### 14.2. Lấy URL service

~~~bash
export SERVICE_URL="$(gcloud run services describe "$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format='value(status.url)')"

echo "$SERVICE_URL"
~~~

### 14.3. Gọi API bằng ID token

~~~bash
export ID_TOKEN="$(gcloud auth print-identity-token)"

curl -i "$SERVICE_URL/actuator/health" \
  -H "Authorization: Bearer $ID_TOKEN"

curl -i -X POST "$SERVICE_URL/api/tasks" \
  -H "Authorization: Bearer $ID_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"Deploy Spring Boot on Cloud Run"}'

curl -s "$SERVICE_URL/api/tasks" \
  -H "Authorization: Bearer $ID_TOKEN"
~~~

Không ghi token vào file, shell history hoặc public log. Nếu organization identity khiến `gcloud auth print-identity-token` tạo token sai audience hoặc không được phép invoke, có thể dùng `gcloud run services proxy` hay cấu hình identity token theo audience của service. Service IAM authentication yêu cầu **ID token**, không phải một access token Google Cloud bất kỳ.

### 14.4. Kết quả kỳ vọng

Ví dụ khi POST thành công:

~~~http
HTTP/1.1 201 Created
Location: /api/tasks/1
Content-Type: application/json

{
  "id": 1,
  "title": "Deploy Spring Boot on Cloud Run",
  "completed": false,
  "createdAt": "2026-11-19T08:00:00Z"
}
~~~

ID/timestamp chỉ là ví dụ. Để kiểm chứng persistence, gửi GET cùng task sau khi service scale down/up hoặc sau một deployment revision mới; dữ liệu vẫn phải tồn tại trong Cloud SQL.

## 15. Kiểm thử end-to-end và tiêu chí nghiệm thu

### 15.1. Functional acceptance

| Test case | Input | Kết quả pass |
|---|---|---|
| Health | GET actuator/health | 200, health UP |
| Create task | POST JSON title hợp lệ | 201, Location, id khác null |
| Query task | GET id vừa tạo | 200, title và completed đúng |
| List task | GET /api/tasks | 200, có task vừa tạo |
| Complete task | PATCH /id/complete | 200, completed=true |
| Delete task | DELETE /id | 204 |
| Unknown id | GET id không tồn tại | 404 |
| Validation | POST title trống | 400 |
| Private endpoint | Gọi không có token | 401/403 theo lớp bảo vệ |
| Persistence | Deploy revision mới và GET task | Dữ liệu vẫn tồn tại |

### 15.2. Non-functional acceptance

- API không tiết lộ password/stack trace/JDBC URL nhạy cảm.
- Runtime service account chỉ có các quyền cần thiết.
- Health và startup không timeout trong điều kiện bình thường.
- Đọc/ghi database qua connector bảo mật.
- Cloud Run logs có request method, status, latency; application logs không ghi PII không cần thiết.
- Database connection count không vượt ngân sách.
- Có kế hoạch backup/restore và giới hạn chi phí; biết cách xóa lab.
- Có thể rollback revision và xác định xử lý schema/database nếu rollback.

## 16. Logging, Monitoring và troubleshooting

### 16.1. Xem log Cloud Run

~~~bash
gcloud run services logs read "$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --limit=100
~~~

Trong Console, xem Cloud Run service → **Logs**, **Metrics**, **Revisions**. Theo dõi request count, latency p95/p99, 4xx/5xx, CPU/memory, instance count và startup time. Có thể bổ sung Micrometer/OpenTelemetry và Cloud Trace theo mức độ bài tập nâng cao.

### 16.2. Xem Cloud SQL

Cloud SQL Console → instance → **Overview/Monitoring/Logs/Query Insights** (nếu đã bật). Theo dõi active connections, CPU, disk space, transaction throughput và query latency. Dùng logs để phân biệt lỗi network, IAM connector, PostgreSQL password và schema.

### 16.3. Bảng xử lý lỗi

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
|---|---|---|
| Cloud Run container không ready | App không lắng nghe PORT hoặc startup lỗi | Logs, bind 0.0.0.0, server.port |
| `Cloud SQL API has not been used` | API chưa bật | Kiểm tra sqladmin.googleapis.com |
| `PERMISSION_DENIED` từ connector | Runtime SA thiếu Cloud SQL Client | Service identity và IAM policy |
| `password authentication failed` | Sai DB_USER/DB_PASS | Secret version, Cloud SQL Users, PostgreSQL logs |
| `connection timed out` | Sai IP path/region, network | Public IP, connector, private VPC egress |
| `relation "tasks" does not exist` | Flyway migration chưa apply | Flyway logs, schema và DB_NAME |
| `permission denied for schema public` | DB user thiếu DDL/USAGE | Kiểm tra SQL grants/migration identity |
| `too many clients already` | Pool × số instance quá lớn | Hikari, Cloud Run max instances, DB connections |
| 401/403 khi gọi URL | Thiếu ID token hoặc Invoker | Token audience, IAM, service URL |
| 400 cho POST hợp lệ | JSON/validation sai | Request body, Content-Type, @Valid |
| 404 sau khi xóa | Đúng theo contract | GET id đã delete phải 404 |
| 500 sau deploy schema | Migration không tương thích | Xem revision, Flyway history và rollback plan |
| Build fail vì quyền | Cloud Build identity thiếu role | Build history, roles/run.builder, artifact access |

**Không sửa bằng cách đặt `--allow-unauthenticated`, mở authorized networks toàn Internet, commit DB password hoặc cấp Owner cho runtime.** Phân loại lỗi theo tầng rồi cấp đúng quyền/cấu hình.

## 17. An toàn dữ liệu, vận hành và độ tin cậy

### 17.1. Stateless compute, stateful database

Cloud Run instance có thể bị dừng hoặc tạo mới, do đó:

- Không lưu dữ liệu task trong static Map/in-memory database.
- Không dựa vào filesystem local để lưu thông tin bền vững.
- Không đặt application session cần persist trong RAM của một instance.
- Transaction và schema thay đổi cần kiểm soát tại Cloud SQL.
- Service phải hỗ trợ graceful shutdown và retry hợp lý.

### 17.2. Backup, HA và RPO/RTO

Cloud SQL lab có thể cấu hình rút gọn, nhưng production cần xem backup, PITR, HA, regional availability, maintenance và DR. **Backup job thành công không thay thế restore drill.** Nếu cần RTO/RPO nghiêm ngặt, phải thiết kế và diễn tập.

### 17.3. Khi tăng tải

Cloud Run autoscaling tăng số instance có thể cải thiện throughput HTTP nhưng làm tăng số connection pool và IOPS trên Cloud SQL. Nếu database là bottleneck, thêm Cloud Run instance có thể làm lỗi tăng. Đo p95/p99 latency, pool active/pending, DB CPU và max connections trước khi điều chỉnh concurrency.

### 17.4. Mô hình quyền với người dùng cuối

API trong lab bảo vệ bằng Cloud Run Invoker ở cấp service, **chưa có phân quyền theo task/user**. Nếu chuyển thành API nhiều người dùng, phải bổ sung xác thực end user (OIDC/JWT/session phù hợp), authorization theo owner/tenant, audit, rate limit, idempotency cho command và bảo vệ dữ liệu cá nhân.

## 18. CI/CD, image và rollback

### 18.1. Pipeline khuyến nghị

~~~mermaid
flowchart LR
    Git[Commit / PR] --> Build[Maven verify]
    Build --> Scan[Dependency / image scan]
    Scan --> Image[Build immutable image]
    Image --> Stage[Deploy staging]
    Stage --> Smoke[Integration + smoke tests]
    Smoke --> Prod[Controlled prod rollout]
    Prod --> Observe[Metrics / alerts]
~~~

Với CI/CD thực tế, dùng Cloud Build triggers hoặc hệ thống CI của tổ chức, pin Maven/JDK/plugin và image digest. Dùng service account build/deploy riêng runtime service account. Không tự động deploy vào production từ pull request chưa được duyệt.

### 18.2. Cloud Run revisions và rollback

Cloud Run tạo revision khi cấu hình hoặc image thay đổi. Có thể kiểm tra:

~~~bash
gcloud run revisions list \
  --service="$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION"
~~~

Khi một revision mới có lỗi, có thể chuyển traffic về revision trước đã được kiểm chứng thông qua Console hoặc gcloud traffic management. **Rollback application code không tự rollback database schema hoặc dữ liệu đã ghi**. Vì vậy migration phải backward-compatible và deployment có kế hoạch phân kỳ.

### 18.3. Bảo vệ chuỗi cung ứng

- Quét dependency và image có CVE, cập nhật JDK/base image.
- Không nhúng secrets vào image/build logs.
- Dùng Artifact Registry, IAM tối thiểu, lưu commit SHA/image digest.
- Có provenance/SBOM và chính sách signing nếu tổ chức yêu cầu.
- Tách secrets, config và build artifact giữa dev/staging/prod.

## 19. Dọn dẹp tài nguyên và kết thúc lab

Cloud SQL tiếp tục tính phí ngay cả khi Cloud Run không có request. Sau khi chụp bằng chứng và hoàn tất bài:

### 19.1. Kiểm tra project, region và scope

~~~bash
gcloud config get-value project
gcloud run services describe "$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION"
gcloud sql instances describe "$SQL_INSTANCE" \
  --project="$PROJECT_ID"
~~~

Xác minh đây là tài nguyên **đã tạo riêng cho lab**, không đang được shared team hoặc pipeline khác sử dụng.

### 19.2. Xóa Cloud Run service

~~~bash
gcloud run services delete "$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION"
~~~

### 19.3. Xóa Cloud SQL instance

~~~bash
gcloud sql instances delete "$SQL_INSTANCE" \
  --project="$PROJECT_ID"
~~~

Lệnh này **phá hủy database instance và dữ liệu**; không chạy nếu chưa xác nhận phạm vi, backup cần giữ, deletion protection, các client khác và quyền owner. Nếu Cloud SQL có deletion protection, phải xử lý theo quy trình quản trị đã được phê duyệt; không tự vô hiệu hóa bảo vệ trong môi trường chung.

### 19.4. Xóa secret và service account nếu chỉ phục vụ lab

~~~bash
gcloud secrets delete tasks-db-password \
  --project="$PROJECT_ID"

gcloud iam service-accounts delete "$SA_EMAIL" \
  --project="$PROJECT_ID"
~~~

Xem thêm Artifact Registry repository/images và Cloud Build artifacts được tạo bởi source deployment; có thể giữ hoặc xóa **chỉ phần thuộc lab** theo retention/cost policy. Không xóa repository dùng chung cho nhiều dịch vụ. Cuối cùng đối chiếu Cloud Billing để chắc chắn không còn instance, disk, image hoặc dịch vụ có phí đáng kể.

## 20. Bài tập mở rộng

1. **Pagination:** thay `LIMIT 100` bằng keyset pagination theo created_at và id, có nextPageToken.
2. **Service layer:** bổ sung `TaskService` với transaction và business rule; controller chỉ xử lý HTTP.
3. **Authentication:** dùng Identity Platform hoặc OIDC/JWT và phân quyền theo task owner.
4. **Idempotency:** thêm Idempotency-Key cho POST để retry không tạo trùng.
5. **Audit:** ghi created_by, updated_at, version và structured logs có trace ID.
6. **Optimistic locking:** cột version và trả 409 khi hai người sửa cùng task.
7. **CI/CD:** Cloud Build trigger chạy Maven verify → scan → deploy staging → smoke test.
8. **Private IP:** chuyển Cloud SQL sang private connectivity, Cloud Run Direct VPC egress và `ipTypes=PRIVATE`.
9. **Migrations:** tách Flyway thành một deployment job với DDL role; runtime chỉ có quyền DML.
10. **Observability:** tích hợp OpenTelemetry, tạo SLO 99,9% availability và alert theo error budget.
11. **Load test:** thử các mức concurrency và max instances, đo DB connection saturation và p99 latency.
12. **DR:** backup/restore Cloud SQL sang một test instance, kiểm chứng RPO/RTO.

## 21. Checklist nghiệm thu bài thực hành

### Mã nguồn và test

- [ ] Có `pom.xml`, Maven Wrapper và Java 21.
- [ ] Spring Boot chạy local với PostgreSQL Docker.
- [ ] Flyway tạo bảng `tasks`, có lịch sử migration.
- [ ] REST endpoints đúng phương thức, status và JSON contract.
- [ ] Validation trả 400 với title không hợp lệ.
- [ ] JUnit/Testcontainers test chạy thành công.
- [ ] Không chứa plaintext DB password hoặc service account key trong Git.

### Google Cloud và deployment

- [ ] Project/region/billing được xác nhận, budget alert đã bật.
- [ ] Cloud SQL instance, database và user thuộc project lab.
- [ ] Secret Manager giữ DB password, không nằm trong image.
- [ ] Runtime service account có Cloud SQL Client và chỉ được đọc secret cần thiết.
- [ ] Cloud Run source deploy thành công, Java 21 và profile cloud đúng.
- [ ] API private, chỉ caller được cấp Invoker có thể gọi.
- [ ] Có 201/200/204/400/404 và persistence sau khi đổi revision.

### Vận hành và cleanup

- [ ] Có log/metric để phân tích lỗi startup/database.
- [ ] Connection pool × max instances không vượt ngân sách DB.
- [ ] Đã ghi rủi ro HA, backup, DR, cost và kiểm thử mở rộng.
- [ ] Có bằng chứng test và thông tin service/revision.
- [ ] Đã xóa resource lab không còn dùng theo đúng scope.
- [ ] Đã kiểm tra không còn Cloud SQL instance phát sinh phí.

## 22. Tài liệu chính thức

- [Build and deploy a Java Spring Boot app to Cloud Run](https://cloud.google.com/run/docs/quickstarts/build-and-deploy/deploy-java-service)
- [Deploy services from source code](https://cloud.google.com/run/docs/deploying-source-code)
- [Cloud Run service identity](https://cloud.google.com/run/docs/securing/service-identity)
- [Cloud Run IAM authentication](https://cloud.google.com/run/docs/authenticating/overview)
- [Configure Cloud Run secrets](https://cloud.google.com/run/docs/configuring/services/secrets)
- [Connect Cloud Run to Cloud SQL for PostgreSQL](https://cloud.google.com/sql/docs/postgres/connect-run)
- [Connect using Cloud SQL language connectors](https://cloud.google.com/sql/docs/postgres/connect-connectors)
- [Cloud SQL Java Connector](https://github.com/GoogleCloudPlatform/cloud-sql-jdbc-socket-factory)
- [Cloud SQL PostgreSQL users](https://cloud.google.com/sql/docs/postgres/create-manage-users)
- [Cloud SQL IAM database authentication](https://cloud.google.com/sql/docs/postgres/iam-authentication)
- [Cloud SQL backup and recovery](https://cloud.google.com/sql/docs/postgres/backup-recovery/backup-options)
- [Cloud Build default and user-specified service accounts](https://cloud.google.com/build/docs/cloud-build-service-account)
- [Spring Boot Data SQL](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Spring Boot testing with Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html)
- [Flyway documentation](https://documentation.red-gate.com/flyway)
- [Cloud Run pricing](https://cloud.google.com/run/pricing)
- [Cloud SQL pricing](https://cloud.google.com/sql/pricing)

## 23. Tổng kết

Một REST API Spring Boot triển khai thành công trên GCP cần nhiều hơn một container đang chạy. Với Cloud Run và Cloud SQL, người học thực hành cách tách **compute stateless** khỏi **data stateful**, quản lý database schema, kết nối qua IAM/connector, lưu secret an toàn, giới hạn connection pool, dùng Cloud Build và kiểm chứng API có xác thực. Bài học hoàn thành khi có kết quả kiểm thử rõ ràng, dữ liệu vẫn tồn tại qua các revision, người học hiểu ranh giới trách nhiệm bảo mật/vận hành và có thể **thu hồi tài nguyên lab an toàn**. Đây là nền tảng để mở rộng ứng dụng sang CI/CD, HA, quan sát độ tin cậy, FinOps và các kiến trúc cloud-native phức tạp hơn.

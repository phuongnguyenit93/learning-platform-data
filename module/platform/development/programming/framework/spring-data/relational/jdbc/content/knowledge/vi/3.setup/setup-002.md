# Khai báo spring-boot-starter-data-jdbc và quản lý dependency bằng BOM

Muốn sử dụng **Spring Data JDBC** trong ứng dụng Spring Boot, bước khởi tạo quan trọng là khai báo đúng thư viện trong công cụ build. Một cấu hình tốt cần trả lời ba câu hỏi: **thêm starter nào**, **ai quản lý phiên bản của các thư viện liên quan**, và **driver nào giúp ứng dụng kết nối với cơ sở dữ liệu thực tế**.

Trong phần lớn dự án Spring Boot, bạn chỉ cần khai báo dependency `org.springframework.boot:spring-boot-starter-data-jdbc` cùng JDBC driver của hệ quản trị cơ sở dữ liệu, rồi để **Spring Boot BOM** quản lý phiên bản tương thích. Không cần tự chọn phiên bản riêng lẻ cho từng thư viện Spring Data, Spring JDBC và driver đã được BOM quản lý.

Bài học này sử dụng **Spring Boot 3.3.5 và Java 21 để minh họa cú pháp cấu hình**. Đây là cặp phiên bản minh họa có chủ đích, không hàm ý rằng 3.3.5 là bản mới nhất. Khi áp dụng vào dự án, hãy dùng phiên bản Spring Boot đã được dự án lựa chọn và bảo đảm BOM tương ứng với phiên bản đó.

## 1. Hiểu đúng ba thành phần cần khai báo

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| **Starter** | `spring-boot-starter-data-jdbc` | Tập hợp các dependency cần thiết để dùng Spring Data JDBC và tự động cấu hình những thành phần phù hợp trong Spring Boot. |
| **BOM (Bill of Materials)** | `spring-boot-dependencies` | Định nghĩa phiên bản được quản lý cho một tập hợp thư viện, nhằm giảm xung đột và duy trì tính tương thích. |
| **JDBC driver** | `org.postgresql:postgresql` | Cung cấp cách giao tiếp JDBC cụ thể với PostgreSQL; có thể thay bằng driver MySQL, MariaDB, H2, v.v. |

Hình dung đường đi từ công cụ build đến cơ sở dữ liệu:

```text
build.gradle hoặc pom.xml
    |
    +-- spring-boot-starter-data-jdbc
    |       |
    |       +-- Spring Data JDBC / Spring Data Relational
    |       +-- Spring JDBC
    |       +-- các thư viện hỗ trợ cần thiết
    |
    +-- Driver (ví dụ PostgreSQL JDBC driver)
    |
    +-- BOM Spring Boot: quản lý phiên bản tương thích
            |
            v
      Ứng dụng Java / Spring Boot
            |
            v
      Repository -> JDBC -> Driver -> Database
```

Sơ đồ chỉ minh họa các nhóm dependency chính; dependency graph thực tế có thể khác theo phiên bản Spring Boot.

**Starter không phải database.** Thêm starter giúp ứng dụng có thư viện truy cập dữ liệu, nhưng chưa tạo cơ sở dữ liệu, bảng hay tài khoản kết nối. Driver cũng không tạo bảng; cấu hình kết nối và migration schema là những việc tiếp theo.

## 2. `spring-boot-starter-data-jdbc` là gì?

Dependency Maven/Gradle có tọa độ:

```text
Group ID:    org.springframework.boot
Artifact ID: spring-boot-starter-data-jdbc
Version:     do Spring Boot BOM quản lý
```

Spring Boot starter là một **điểm vào thuận tiện**: thay vì phải tự liệt kê tất cả thư viện để dùng `JdbcTemplate`, Spring Data JDBC repositories, Spring Data Relational và hạ tầng JDBC liên quan, bạn khai báo starter, còn hệ thống quản lý dependency sẽ giải quyết các dependency bắc cầu phù hợp.

Phân biệt những starter dễ nhầm:

| Dependency | Công dụng | Có thay thế `spring-boot-starter-data-jdbc` không? |
| --- | --- | --- |
| `spring-boot-starter-jdbc` | Hỗ trợ JDBC thông qua Spring JDBC, `JdbcTemplate`, cấu hình `DataSource`. | **Không hoàn toàn.** Không cung cấp đầy đủ repository/mapping của Spring Data JDBC. |
| `spring-boot-starter-data-jdbc` | Thêm Spring Data JDBC repository và ánh xạ aggregate, cùng hạ tầng JDBC. | **Đúng lựa chọn** của bài học. |
| `spring-boot-starter-data-jpa` | Tích hợp Spring Data JPA, JPA provider như Hibernate và mô hình ORM. | **Không.** JPA và Data JDBC có cơ chế persistence khác nhau. |
| `spring-boot-starter-data-r2dbc` | Hỗ trợ truy cập dữ liệu quan hệ theo API reactive R2DBC. | **Không.** R2DBC không sử dụng JDBC blocking. |

Nếu chỉ sử dụng Spring Data JDBC, thông thường **không cần khai báo thêm `spring-boot-starter-jdbc`**, vì starter Data JDBC đã mang theo hạ tầng tương ứng. Thêm đồng thời Data JPA vì tưởng nó là điều kiện bắt buộc của repository cũng là một hiểu nhầm phổ biến.

## 3. BOM là gì và vì sao cần dùng?

**BOM (Bill of Materials)** trong hệ sinh thái Maven là một tệp POM chuyên quản lý phiên bản của các dependency. Spring Boot phát hành BOM `org.springframework.boot:spring-boot-dependencies` tương ứng với từng phiên bản Spring Boot.

Ví dụ về mặt khái niệm, một BOM có thể quản lý các phiên bản của:

- `org.springframework.data:spring-data-jdbc`;
- `org.springframework:spring-jdbc`;
- `org.postgresql:postgresql`;
- các thành phần HikariCP, Jackson, thư viện test và nhiều dependency khác.

Khi đã áp dụng BOM đúng cách, trong khai báo dependency ứng dụng bạn có thể viết:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-data-jdbc'
runtimeOnly 'org.postgresql:postgresql'
```

Bạn **không phải gắn `:version`** vào hai tọa độ trên vì BOM đã cung cấp phiên bản được quản lý.

### 3.1. BOM giải quyết vấn đề gì?

Giả sử một dự án tự đặt phiên bản cho Spring Data JDBC, Spring Framework, driver và các thư viện hỗ trợ, người viết build phải tự bảo đảm chúng tương thích. Nếu một thư viện được nâng cấp độc lập, dependency graph có thể chứa các phiên bản lệch nhau gây lỗi khi chạy hoặc lỗi liên kết phương thức.

BOM giúp đưa phần lớn lựa chọn phiên bản về **một nguồn quản lý nhất quán**. Với Spring Boot, bạn thường cập nhật phiên bản Boot/BOM theo kế hoạch, rồi build sẽ nhận bộ phiên bản quản lý tương ứng.

```text
Không có BOM:
  Spring Data JDBC version A
  Spring JDBC version B
  Spring Framework version C
  Driver version D
  -> tự theo dõi sự tương thích

Có Spring Boot BOM:
  Spring Boot/BOM version X
  -> tập phiên bản được Spring Boot quản lý cùng nhau
```

BOM giúp **giảm rủi ro** xung đột; không có nghĩa mọi tập dependency trong dự án tự động tương thích tuyệt đối, nhất là khi thêm thư viện ngoài phạm vi BOM hoặc ghi đè phiên bản.

### 3.2. BOM quản lý gì và không quản lý gì?

BOM chủ yếu quản lý **phiên bản dependency**:

- Không tự thêm `spring-boot-starter-data-jdbc` vào dự án. Bạn vẫn phải khai báo thư viện mình dùng.
- Không tự cài driver cho mọi loại database. Bạn phải thêm đúng driver.
- Không quản lý phiên bản **Gradle plugin hoặc Maven plugin** theo cùng cơ chế dependency management thông thường; `spring-boot-starter-parent` của Maven có thêm cơ chế plugin management riêng.
- Không tạo bảng, chạy migration, cấp quyền database, quản lý mật khẩu hay kiểm thử nghiệp vụ.
- Không bảo đảm dependency do bạn ép phiên bản thủ công vẫn tương thích với toàn bộ các thư viện khác.

Vì vậy, cách làm thông dụng là **khai báo dependency cần dùng, để BOM quản lý phiên bản, và chỉ ghi đè version khi có lý do đã được kiểm chứng**.

## 4. Khai báo bằng Gradle Groovy DSL (`build.gradle`)

Với dự án Spring Boot dùng `build.gradle`, một ví dụ hoàn chỉnh ở mức dependency như sau:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jdbc'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Vai trò từng khai báo:

| Cấu hình | Ý nghĩa |
| --- | --- |
| `id 'java'` | Bật các tác vụ Java và cấu hình source set, compile, test. |
| `id 'org.springframework.boot'` | Tích hợp tác vụ và cách đóng gói ứng dụng Spring Boot với Gradle. |
| `id 'io.spring.dependency-management'` | Kích hoạt cơ chế dependency management; khi dùng cùng Spring Boot Gradle plugin, BOM Spring Boot tương ứng được áp dụng tự động. |
| `mavenCentral()` | Cho phép Gradle tải artifact từ Maven Central. |
| `implementation '...starter-data-jdbc'` | Đưa Spring Data JDBC cùng các dependency bắc cầu vào compile/runtime classpath thích hợp. |
| `runtimeOnly 'org.postgresql:postgresql'` | Đưa JDBC driver PostgreSQL vào runtime classpath, không bắt buộc mã nghiệp vụ phải biên dịch phụ thuộc trực tiếp driver. |
| `testImplementation '...starter-test'` | Thêm hạ tầng kiểm thử Spring Boot. |
| `JavaLanguageVersion.of(21)` | Chọn Java toolchain phục vụ biên dịch/chạy các tác vụ Java; không quyết định phiên bản thư viện Spring. |

**Vì sao không có số phiên bản sau starter và driver?** Spring Boot Gradle plugin kết hợp với `io.spring.dependency-management` tự động sử dụng BOM `spring-boot-dependencies` khớp phiên bản Spring Boot plugin. Nhờ đó các tọa độ được BOM quản lý có thể khai báo không có version.

Lưu ý rằng **phiên bản của hai plugin trong khối `plugins` vẫn phải được khai báo hoặc quản lý tại nơi khác bằng cơ chế quản lý plugin của Gradle**. BOM dependency không tự chọn phiên bản plugin `io.spring.dependency-management`.

### 4.1. Cấu hình tương tự trong Gradle Kotlin DSL

Nếu dự án dùng `build.gradle.kts`:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.3.5"
    id("io.spring.dependency-management") version "1.1.6"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jdbc")
    runtimeOnly("org.postgresql:postgresql")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
```

Hai ví dụ Gradle cùng một ý nghĩa; bạn chọn cú pháp ứng với loại tệp build của dự án, không trộn Groovy DSL vào `build.gradle.kts`.

### 4.2. Cách khác: Gradle native BOM với `platform(...)`

Gradle còn có cơ chế quản lý phiên bản chuẩn của chính Gradle: import BOM bằng `platform(...)`, **không cần plugin `io.spring.dependency-management`**. Nếu ứng dụng đang dùng Spring Boot Gradle plugin, có thể tham chiếu tọa độ BOM gắn với chính phiên bản plugin đó:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )

    implementation 'org.springframework.boot:spring-boot-starter-data-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Trong ví dụ này:

1. `SpringBootPlugin.BOM_COORDINATES` cung cấp tọa độ Spring Boot BOM tương ứng phiên bản Spring Boot plugin.
2. `platform(...)` nhập các ràng buộc phiên bản dependency của BOM theo cơ chế Gradle native.
3. Các dependency có trong BOM tiếp tục được khai báo không có phiên bản riêng.

Khi xây dựng một dự án mới, thường nên **chọn một chiến lược BOM** rõ ràng: dùng plugin dependency management của Spring hoặc dùng Gradle native platform. Tránh nhập nhiều BOM tương tự một cách tùy tiện vì khó biết cấu hình nào quyết định phiên bản cuối cùng.

Nếu dự án chỉ có Gradle `java` plugin mà không áp dụng Spring Boot plugin, cũng có thể viết trực tiếp:

```groovy
dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')
    implementation 'org.springframework.boot:spring-boot-starter-data-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
```

Ở trường hợp này, **phiên bản BOM được chỉ định tường minh**. Đây là cách có thể dùng cho module thư viện hoặc một build không dùng Spring Boot Gradle plugin; cần quản lý phiên bản BOM phù hợp với ứng dụng tiêu thụ.

## 5. Khai báo bằng Maven (`pom.xml`)

Maven hỗ trợ hai cách dùng phiên bản quản lý của Spring Boot: kế thừa `spring-boot-starter-parent` hoặc import `spring-boot-dependencies` như một BOM trong `dependencyManagement`.

### 5.1. Cách phổ biến: kế thừa `spring-boot-starter-parent`

Ví dụ `pom.xml` tối giản cho ứng dụng Spring Boot dùng PostgreSQL:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>jdbc-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jdbc</artifactId>
        </dependency>

        <dependency>
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
            <scope>runtime</scope>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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
```

`spring-boot-starter-parent` kế thừa dependency management dựa trên BOM Spring Boot, đồng thời cung cấp các mặc định và plugin management hữu ích cho Maven. Đó là lý do đoạn trên không phải ghi `<version>` cho starter, driver và Spring Boot Maven plugin.

**Không nhầm tên:** `spring-boot-starter-parent` là một **parent POM**; `spring-boot-dependencies` là **BOM** quản lý phiên bản dependency. Parent thường đưa BOM vào mô hình quản lý dependency và bổ sung cấu hình build; chúng có liên hệ nhưng không phải một artifact.

### 5.2. Khi dự án đã có parent POM riêng: import BOM

Một `pom.xml` chỉ có thể khai báo một parent trực tiếp. Nếu dự án đã kế thừa parent doanh nghiệp/đa module, có thể import Spring Boot BOM vào `dependencyManagement` thay vì thay parent hiện có.

Các phần cấu hình quan trọng:

```xml
<properties>
    <spring-boot.version>3.3.5</spring-boot.version>
    <maven.compiler.release>21</maven.compiler.release>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>${spring-boot.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Đặt các khối trên **bên trong `<project>` của POM**, đồng thời giữ nguyên parent hợp lệ đang sử dụng. Phần import BOM làm cho Maven biết các phiên bản dependency đã được quản lý. Tuy nhiên, **import BOM không mang theo các mặc định build/plugin management của `spring-boot-starter-parent`**; nếu ứng dụng cần Spring Boot Maven plugin, bạn phải cấu hình plugin và phiên bản của nó trong `build/plugins` hoặc qua parent/pluginManagement của dự án:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <version>${spring-boot.version}</version>
        </plugin>
    </plugins>
</build>
```

Có thể cần cấu hình thêm compiler/test/resource plugin tùy parent POM đang dùng. BOM giải quyết phiên bản của dependency, không thay toàn bộ chức năng của Spring Boot parent.

## 6. Thêm JDBC driver đúng với cơ sở dữ liệu

`spring-boot-starter-data-jdbc` cung cấp tầng truy cập dữ liệu, còn driver phải phù hợp với database và JDBC URL.

Một số ví dụ cho Gradle:

```groovy
// PostgreSQL
runtimeOnly 'org.postgresql:postgresql'

// MySQL
runtimeOnly 'com.mysql:mysql-connector-j'

// MariaDB
runtimeOnly 'org.mariadb.jdbc:mariadb-java-client'

// H2 (cơ sở dữ liệu nhúng, thường dùng cho demo/test)
runtimeOnly 'com.h2database:h2'
```

**Chỉ khai báo driver thật sự cần thiết cho môi trường ứng dụng.** Các dòng trên là các lựa chọn thay thế để minh họa, không phải yêu cầu thêm cả bốn driver cùng lúc.

`runtimeOnly` thường thích hợp khi mã Java chỉ gọi giao diện JDBC chuẩn (`DataSource`, `Connection`) hoặc repository của Spring Data, không tham chiếu trực tiếp lớp đặc thù của driver. Nếu mã nguồn cố ý import lớp của driver để compile, scope cần được cân nhắc lại.

Cách khai báo tương đương trong Maven, ví dụ PostgreSQL:

```xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
```

**Không ghi version nếu nó đã được BOM đang dùng quản lý.** Nếu chọn một driver ngoài danh sách BOM, phải cung cấp phiên bản bằng cấu hình quản lý dependency thích hợp.

## 7. Cấu hình `DataSource` sau khi đã thêm dependency

Thêm dependency chỉ khiến các lớp và cơ chế cấu hình có mặt trên classpath. Ứng dụng vẫn cần biết database nằm ở đâu và dùng thông tin gì để đăng nhập.

Ví dụ `src/main/resources/application.yml` cho PostgreSQL:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/shopdb
    username: ${DB_USER}
    password: ${DB_PASSWORD}
```

Giải thích:

- `spring.datasource.url` là JDBC URL trỏ đến database `shopdb` trên PostgreSQL ở máy hiện tại.
- `spring.datasource.username` và `password` lấy giá trị từ biến môi trường; không đặt mật khẩu thật trực tiếp trong ví dụ hoặc mã nguồn.
- Driver PostgreSQL đã được thêm bằng `runtimeOnly`, nên Spring Boot có thể nhận diện driver tương ứng từ URL và classpath.
- Spring Boot thường dùng pool kết nối được cung cấp cùng hạ tầng JDBC khi thành phần phù hợp có trên classpath.

Cần tạo database `shopdb` và cấp quyền truy cập trước. Ngoài ra, **Spring Data JDBC không tự tạo cấu trúc bảng như chế độ `hibernate.ddl-auto` của JPA/Hibernate**. Schema thường do SQL migration (ví dụ Flyway hoặc Liquibase) hoặc thao tác tạo bảng được quản lý riêng đảm nhiệm.

Ví dụ tạo bảng thủ công:

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(150) NOT NULL
);
```

Đây là DDL của PostgreSQL để minh họa. Schema và migration thực tế phải phù hợp với database và phiên bản hệ thống của ứng dụng.

## 8. Một ví dụ nhỏ để thấy dependency đã phục vụ mục đích gì

Với starter, driver, datasource và bảng `customers` được cấu hình đúng, bạn có thể viết aggregate root và repository như sau:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public record Customer(@Id Long id, String name) {
}
```

```java
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
```

Một service có thể nhận `CustomerRepository` qua constructor injection rồi gọi `save`, `findById` hoặc `findAll`. Ví dụ:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerService {
    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Customer create(String name) {
        return repository.save(new Customer(null, name));
    }
}
```

Trong mô hình record bất biến ở trên, phương thức `save` trả về đối tượng chứa ID được sinh sau khi thêm bản ghi; ứng dụng nên sử dụng **đối tượng được trả về**. Spring Data JDBC tạo SQL/ánh xạ cho repository, JDBC driver giao tiếp với PostgreSQL, và database lưu hàng dữ liệu.

Ví dụ giả định các lớp nằm trong package được Spring Boot component/repository scanning phát hiện. Nếu tách package ngoài phạm vi scan mặc định, cần điều chỉnh cấu hình scan phù hợp. Các class Java ở trên dùng để minh họa rằng dependency đã đủ hỗ trợ repository; chúng không thay thế cấu hình kết nối, migration và việc chạy database.

## 9. Cách kiểm tra dependency nào và phiên bản nào thực sự được chọn

Đọc `build.gradle` hoặc `pom.xml` cho biết dependency đã khai báo; **dependency graph được resolve** mới cho biết thư viện và phiên bản thực sự đi vào classpath. Khi gặp lỗi version hoặc thiếu driver, đây là nơi nên bắt đầu xem xét.

Các lệnh tham khảo trong thư mục dự án (không thực thi lệnh trong bài học này):

**Gradle:**

```bash
# Xem dependency runtime và các phiên bản được resolve
./gradlew dependencies --configuration runtimeClasspath

# Xem vì sao một thư viện được chọn vào runtimeClasspath
./gradlew dependencyInsight \
  --dependency org.springframework.data:spring-data-jdbc \
  --configuration runtimeClasspath
```

Trên Windows dùng `gradlew.bat`, hoặc chạy các tham số trên cùng một dòng cho phù hợp shell.

**Maven:**

```bash
# Xem cây dependency
mvn dependency:tree

# Xem mô hình POM sau khi kế thừa/import BOM
mvn help:effective-pom
```

Khi kiểm tra, hãy tìm ba điều:

1. `spring-boot-starter-data-jdbc` và `spring-data-jdbc` có trong dependency graph.
2. Driver tương ứng (ví dụ `org.postgresql:postgresql`) có trong **runtime** classpath.
3. Các phiên bản được chọn khớp chiến lược BOM của dự án, trừ những ngoại lệ đã được chủ động quản lý.

Có thể sử dụng thêm báo cáo dependency của IDE hoặc công cụ phân tích dependency nếu dự án đã có sẵn. Đừng suy đoán phiên bản dựa trên việc một dependency không ghi `version` trong file build.

## 10. Xử lý các lỗi thường gặp khi khởi tạo

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `Could not find ...` / không resolve được dependency | Thiếu `repositories { mavenCentral() }`, thông số artifact sai hoặc không truy cập được repository. | Kiểm tra tọa độ dependency, cấu hình repository, mạng/proxy và nguồn artifact. |
| Không xác định được version của starter hoặc driver | Chưa import/áp dụng BOM đúng hoặc dependency không được BOM hiện tại quản lý. | Kiểm tra Spring Boot parent, `dependencyManagement`, Gradle plugin dependency management hoặc `platform(...)`. |
| `Failed to configure a DataSource` vì thiếu URL | Chưa cấu hình datasource, không có embedded database phù hợp hoặc môi trường thiếu biến cấu hình. | Bổ sung `spring.datasource.url`, username/password và chạy database tương ứng. |
| `No suitable driver` / không tải được JDBC driver | Thiếu driver hoặc URL không khớp driver trên classpath. | Thêm driver vào runtime classpath và kiểm tra tiền tố JDBC URL. |
| `Connection refused` | Không có database đang lắng nghe tại host/port đã khai báo, hoặc mạng bị chặn. | Kiểm tra host, port, Docker/network và trạng thái database. |
| Lỗi `relation "customers" does not exist` | Database kết nối được nhưng bảng chưa có hoặc nằm ở schema khác. | Tạo/migrate schema đúng database và kiểm tra schema/search path. |
| Không inject được `CustomerRepository` | Interface chưa được Spring Data nhận diện, package scan không phù hợp hoặc hạ tầng repository chưa bật/khởi tạo. | Kiểm tra starter, vị trí package và cấu hình Spring Boot. |
| `NoSuchMethodError` / lỗi linkage sau khi nâng cấp thư viện | Có thể có các phiên bản thư viện không tương thích trên classpath. | Xem `dependencyInsight` hoặc `dependency:tree`, gỡ ghi đè dư thừa và căn chỉnh theo BOM. |

Những thông báo này là ví dụ về **nhóm lỗi**, không phải mọi trường hợp đều có cùng nguyên nhân. Nên đọc cả phần `Caused by` và dependency graph trước khi đổi phiên bản thư viện.

## 11. Khi nào cần tự chỉ định phiên bản dependency?

Mục tiêu của BOM là có một cơ sở phiên bản thống nhất, nhưng đôi khi dự án cần sử dụng phiên bản cụ thể: bản sửa lỗi bảo mật được kiểm chứng, thư viện ngoài phạm vi BOM hoặc yêu cầu tương thích có tài liệu.

Ví dụ Gradle với phiên bản driver được ghim tường minh:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jdbc'
    runtimeOnly 'org.postgresql:postgresql:42.7.4'
}
```

Đây là **ví dụ cú pháp override**, không phải khuyến nghị chọn phiên bản `42.7.4` cho mọi dự án. Khi thêm phiên bản riêng, cần kiểm tra phiên bản Java, Spring Boot, driver, các lỗ hổng bảo mật liên quan và kết quả resolve thực tế.

Với Maven, có thể điều chỉnh phiên bản dependency bằng cơ chế `dependencyManagement` của dự án hoặc một khai báo `<version>` trực tiếp ở dependency cụ thể. Nếu nhiều BOM cùng được import, thứ tự và mức ưu tiên quản lý dependency phải được xem xét theo cấu hình Maven thực tế. Không nên thêm nhiều override không rõ lý do.

Đối với dự án **đa module**, cũng cần xác định nơi quản lý phiên bản chung: parent POM, root Gradle convention/build logic hoặc version catalog. Những module dùng chung Spring Boot nên có chiến lược phiên bản nhất quán thay vì mỗi module tự đoán một BOM khác nhau.

## 12. Những nhầm lẫn cần tránh

**“Thêm starter nghĩa là PostgreSQL driver đã có sẵn.”** Không đúng. Starter không mặc định chọn database cụ thể; khi dùng PostgreSQL, hãy khai báo driver PostgreSQL.

**“Có Spring Boot plugin là Gradle luôn tự quản lý dependency.”** Chưa đủ để kết luận. Với Gradle, cần xem dự án đang dùng `io.spring.dependency-management`, native `platform(...)`, hoặc convention management được cấu hình theo cách khác. Spring Boot plugin có thể phối hợp với các cách đó nhưng bản thân một khai báo plugin không thay thế việc kiểm tra dependency management.

**“BOM tự thêm các thư viện đã liệt kê.”** Không đúng. BOM đưa ra phiên bản, còn ứng dụng chỉ kéo những dependency thực sự được khai báo trực tiếp hoặc được kéo vào như dependency bắc cầu.

**“Phiên bản trong Spring Boot BOM quản lý cả Gradle plugin.”** Không đúng. Phiên bản của Gradle plugin được xử lý qua Gradle plugin management; cần phân biệt với dependency version management.

**“Dùng Spring Data JDBC vẫn phải thêm starter JPA.”** Không đúng. JPA không phải điều kiện cần; việc thêm JPA ngoài ý muốn có thể tạo thêm auto-configuration, hành vi persistence và dependency không cần thiết.

**“Tự thêm mọi phiên bản chắc chắn ổn định hơn.”** Không đúng. Các phiên bản rời rạc có thể lệch nhau; chỉ nên override một cách có kiểm soát và xác minh dependency graph.

**“Kết nối được tức là bảng và dữ liệu đã sẵn sàng.”** Không đúng. Khởi tạo kết nối và quản lý schema là hai trách nhiệm riêng. Trong hệ thống thực tế cần migration, ràng buộc dữ liệu, quy trình backup và kiểm soát thay đổi schema.

## 13. Tự thực hành

Hãy thử ba tình huống để củng cố cách cấu hình:

1. **Tạo ứng dụng dùng PostgreSQL:** khai báo `spring-boot-starter-data-jdbc`, driver PostgreSQL và BOM qua Spring Boot parent hoặc cấu hình Gradle phù hợp; dùng `application.yml` để đặt JDBC URL và credential qua biến môi trường.
2. **Đổi sang H2 cho demo:** thay driver bằng `com.h2database:h2`, cấu hình JDBC URL H2 thích hợp và giải thích vì sao dữ liệu in-memory không được bảo toàn qua lần khởi tạo lại database.
3. **Dự án đã có parent Maven riêng:** import `spring-boot-dependencies` trong `dependencyManagement`, giữ parent hiện tại và chỉ rõ cách quản lý phiên bản Spring Boot Maven plugin.

Khi xem xét kết quả, hãy trả lời được: tại sao starter không có `version`, tại sao vẫn cần driver, BOM được áp dụng bằng cơ chế nào, và dependency graph giải thích các phiên bản cuối cùng ra sao.

**Ghi nhớ:** Khởi tạo Spring Data JDBC hiệu quả bắt đầu từ **`spring-boot-starter-data-jdbc` + driver phù hợp + một chiến lược Spring Boot BOM rõ ràng**. Starter đưa khả năng truy cập dữ liệu vào ứng dụng; BOM giữ phiên bản dependency thống nhất; driver kết nối ứng dụng với hệ quản trị cơ sở dữ liệu. Sau bước dependency, vẫn phải cấu hình `DataSource` và quản lý schema đúng cách.


# Dependency kiểm thử trong Spring Boot: hiểu đúng `testImplementation` và `testRuntimeOnly`

> **Module:** Spring Boot – testing  
> **Nhóm kiến thức:** Thiết lập kiểm thử  
> **Trọng tâm:** Cách Gradle đặt thư viện kiểm thử vào **test compile classpath** và **test runtime classpath**, khi nào dùng `testImplementation` hay `testRuntimeOnly`, cách cấu hình JUnit/Spring Boot và cách tự chẩn đoán lỗi.

## 1. Tại sao phải chia phạm vi dependency?

Khi viết test cho ứng dụng Spring Boot, chúng ta cần nhiều loại thư viện:

- **API dùng trong mã test:** `org.junit.jupiter.api.Test`, AssertJ, Mockito, `@SpringBootTest`, `MockMvc`, Testcontainers API, v.v.
- **Thành phần chỉ cần lúc thực thi test:** JUnit Platform Launcher, một test engine chuyên biệt chỉ được khám phá lúc chạy, JDBC driver được nạp động, nhà cung cấp logging hoặc thư viện được tìm qua Java ServiceLoader.
- **Thư viện ứng dụng thực:** starter web, data JPA, JDBC driver sản xuất, domain libraries.

Đặt tất cả vào `implementation` khiến ranh giới giữa mã sản xuất và mã kiểm thử mờ đi: dễ mang theo dependency thừa vào classpath/chế độ đóng gói của ứng dụng, chậm giải quyết dependency và tăng khả năng xung đột phiên bản. Gradle cung cấp các **configuration** giúp xác định thư viện cần ở giai đoạn nào.

**Quy tắc quan trọng nhất:**

- **`testImplementation`:** test code **cần để biên dịch** và **cần khi chạy**.
- **`testRuntimeOnly`:** **chỉ** cần khi chạy test; không có trong classpath biên dịch của test.

Đây là khái niệm của **Gradle**, không phải tên thư viện hoặc annotation của Spring Boot. Cả Spring Boot unit test, slice test và integration test đều có thể sử dụng hai configuration này. `testImplementation` cũng không có nghĩa “chỉ unit test”; nó bao gồm các thư viện mà **mọi test trong source set `test`** cần biên dịch và chạy.

## 2. Hiểu đúng classpath và source set

Java compiler (`javac`) cần classpath để tìm các kiểu mà mã nguồn import, kế thừa hoặc gọi. Khi chạy test, JVM và test runner lại cần **runtime classpath** chứa các lớp đã biên dịch cùng thư viện để thực thi.

Với plugin Gradle `java`, cấu trúc chuẩn:

```text
src/
  main/
    java/           # Mã ứng dụng thực
    resources/      # Cấu hình/tài nguyên cho ứng dụng
  test/
    java/           # Mã test được biên dịch riêng
    resources/      # application-test.yml, fixture, dữ liệu thử, ...
```

Có hai source set mặc định là `main` và `test`. Plugin Gradle `java` thiết lập `compileJava`, `compileTestJava`, `test` và các classpath tương ứng.

```text
             CÁC DEPENDENCY ĐƯỢC KHAI BÁO
                  ┌─────────────────┐
                  │ implementation  │ ───► main compile & runtime
                  │ runtimeOnly     │ ───► main runtime
                  └─────────────────┘

                  ┌────────────────────┐
                  │ testImplementation │ ───► test compile & runtime
                  │ testCompileOnly    │ ───► test compile
                  │ testRuntimeOnly    │ ───► test runtime
                  └────────────────────┘

src/main/java ──compileJava────────────► build/classes/java/main
src/test/java ──compileTestJava────────► build/classes/java/test
                                             │
                                             ▼
                      test task (forked test JVM + JUnit Platform)
                      └─ testRuntimeClasspath + test classes
```

### 2.1. Các configuration được sử dụng ở đâu?

| Configuration | Biên dịch `main` | Chạy `main` | Biên dịch `test` | Chạy `test` | Trường hợp phổ biến |
| --- | :---: | :---: | :---: | :---: | --- |
| `implementation` | Có | Có | Có* | Có* | `spring-boot-starter`, `spring-boot-starter-web`, business libraries |
| `runtimeOnly` | Không | Có | Không | Có* | Driver database của ứng dụng, provider được nạp lúc chạy |
| `compileOnly` | Có | Không | Không mặc định | Không mặc định | API chỉ cần lúc biên dịch `main` |
| **`testImplementation`** | **Không** | **Không** | **Có** | **Có** | `spring-boot-starter-test`, `spring-security-test`, API Testcontainers |
| `testCompileOnly` | Không | Không | Có | Không | API thực sự chỉ dùng để biên dịch test |
| **`testRuntimeOnly`** | **Không** | **Không** | **Không** | **Có** | `junit-platform-launcher`, H2 khi chỉ dùng cho test |

\* Mặc định của Gradle Java plugin: `test` được kiểm thử cùng đầu ra của `main` và dependency chạy `main`; cụ thể `testImplementation` kế thừa `implementation`, `testRuntimeOnly` kế thừa `runtimeOnly`. Bảng cho thấy ảnh hưởng thực tế tới classpath của source set chuẩn, không mô tả mọi cấu hình Gradle tùy biến.

Đừng nhầm các *configuration dùng để khai báo dependency* với các *configuration dùng để phân giải classpath*:

- Khai báo trong `dependencies { testImplementation ... }` hoặc `testRuntimeOnly`.
- Xem thư viện biên dịch test qua **`testCompileClasspath`**.
- Xem thư viện chạy test qua **`testRuntimeClasspath`**.

`testCompileClasspath` và `testRuntimeClasspath` là những **resolvable configurations** để Gradle dựng classpath; không nên khai báo trực tiếp dependency ứng dụng vào chúng.

### 2.2. Cách đọc bằng một tình huống

Giả sử test có dòng sau:

```java
import org.junit.jupiter.api.Test;
```

Compiler phải nhìn thấy lớp `Test` nên JUnit Jupiter API thuộc `testImplementation` (thường có sẵn transitively từ `spring-boot-starter-test`). Nếu chỉ đặt nó ở `testRuntimeOnly`, test không thể compile import đó.

Ngược lại, Gradle test worker cần một **JUnit Platform Launcher** để tổ chức việc phát hiện/chạy test. Mã test thông thường không import lớp launcher: đặt `org.junit.platform:junit-platform-launcher` ở `testRuntimeOnly` là hợp lý. Test runner sử dụng nó khi chạy.

## 3. Mẫu cấu hình Spring Boot/Gradle chạy được

Ví dụ dùng **Java 17, Spring Boot 3.5.16, Gradle 8.14.x, Groovy DSL (`build.gradle`)**. Đó là bộ phiên bản minh họa nhất quán: Spring Boot 3.5 hỗ trợ Java 17+ và dòng Gradle 8 theo tài liệu chính thức. Khi dự án dùng Spring Boot 4 hoặc Gradle 9, hãy kiểm tra compatibility matrix của chính dòng phiên bản đó; ý nghĩa hai configuration vẫn giữ nguyên.

### 3.1. `settings.gradle`

```groovy
rootProject.name = 'testing-dependency-scopes'
```

### 3.2. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
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
    // Mã ứng dụng cần starter này để biên dịch và chạy.
    implementation 'org.springframework.boot:spring-boot-starter'

    // Test import @Test, assertions, @SpringBootTest, Mockito...:
    // các API được dùng khi biên dịch test và khi chạy test.
    testImplementation 'org.springframework.boot:spring-boot-starter-test'

    // Gradle/JUnit Platform cần launcher ở thời điểm chạy test.
    // Mã test bên dưới không import bất kỳ class nào từ launcher.
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Giải thích chính xác từng dòng quan trọng:

- `java` tạo source sets, các cấu hình `testImplementation` / `testRuntimeOnly` và task `test`.
- Plugin `org.springframework.boot` hỗ trợ build/packaging Spring Boot.
- Plugin `io.spring.dependency-management` kết hợp với Spring Boot plugin nhập BOM `spring-boot-dependencies` để quản lý phiên bản của các dependency được BOM quản lý; do đó có thể bỏ version ở ba thư viện trong `dependencies`.
- `spring-boot-starter-test` mang những phần thường dùng cho test (Spring Boot Test, JUnit Jupiter, AssertJ, Mockito, Spring Test, ...). Vì mã test phải import các API này, đặt nó ở `testImplementation`.
- `junit-platform-launcher` dành cho quá trình thực thi JUnit Platform, vì vậy đặt ở `testRuntimeOnly`. Đây cũng là khai báo được Gradle khuyến nghị để có launcher tương thích tường minh ở runtime.
- `useJUnitPlatform()` yêu cầu task `test` dùng JUnit Platform để tìm/chạy JUnit Jupiter test. **Có dependency không thay thế cho việc cấu hình test runner**.
- Phiên bản test libraries phải được quản lý thống nhất với BOM hoặc khai báo trực tiếp. Đừng tùy tiện thêm phiên bản JUnit khác vào một artifact đơn lẻ khi toàn bộ stack đang được BOM quản lý.

### 3.3. Cấu trúc project và mã nguồn

```text
testing-dependency-scopes/
├── settings.gradle
├── build.gradle
├── gradlew                 # Wrapper nếu project được tạo bằng Initializr/Gradle
├── gradlew.bat
└── src/
    ├── main/java/com/example/testingdeps/
    │   ├── TestingDepsApplication.java
    │   └── GreetingService.java
    └── test/java/com/example/testingdeps/
        ├── GreetingServiceTest.java
        └── ApplicationContextTest.java
```

Tạo các tệp đúng đường dẫn và tên class sau.

```java
// src/main/java/com/example/testingdeps/TestingDepsApplication.java
package com.example.testingdeps;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestingDepsApplication {
    public static void main(String[] args) {
        SpringApplication.run(TestingDepsApplication.class, args);
    }
}
```

```java
// src/main/java/com/example/testingdeps/GreetingService.java
package com.example.testingdeps;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên không được rỗng");
        }
        return "Xin chào, " + name.trim() + "!";
    }
}
```

```java
// src/test/java/com/example/testingdeps/GreetingServiceTest.java
package com.example.testingdeps;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class GreetingServiceTest {
    private final GreetingService service = new GreetingService();

    @Test
    void trimsUserName() {
        assertThat(service.greet("  An  "))
                .isEqualTo("Xin chào, An!");
    }

    @Test
    void rejectsBlankName() {
        assertThatThrownBy(() -> service.greet("   "))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("Tên không được rỗng");
    }
}
```

```java
// src/test/java/com/example/testingdeps/ApplicationContextTest.java
package com.example.testingdeps;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class ApplicationContextTest {
    @Autowired
    GreetingService service;

    @Test
    void springCreatesServiceBean() {
        assertThat(service.greet("Mai"))
                .isEqualTo("Xin chào, Mai!");
    }
}
```

**Điều gì được kiểm chứng?** `GreetingServiceTest` chỉ chạy Java class thật mà không nạp Spring context; `ApplicationContextTest` kiểm tra Spring có tạo/tiêm bean `GreetingService`. **Điều gì khác nhau ở Gradle dependency?** Không khác: cả hai dùng chung source set `test` nên cùng nhận `testImplementation` và `testRuntimeOnly`. Unit/slice/integration là **phạm vi kiểm tra hành vi**, còn `testImplementation`/`testRuntimeOnly` là **phạm vi dependency theo giai đoạn biên dịch/chạy**.

Hai test compile vì JUnit/AssertJ/Spring Boot Test API nằm trên test compile classpath. Chúng chạy qua JUnit Platform, còn launcher nằm trên test runtime classpath. Không có code nào import launcher trực tiếp.

### 3.4. Chạy bằng Gradle Wrapper

Nếu project có Gradle Wrapper (khuyến nghị sử dụng), tại thư mục chứa `build.gradle`:

```bash
./gradlew test
./gradlew test --tests 'com.example.testingdeps.GreetingServiceTest'
./gradlew test --tests 'com.example.testingdeps.ApplicationContextTest'
./gradlew check
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests "com.example.testingdeps.GreetingServiceTest"
.\gradlew.bat check
```

Nếu tạo project thủ công mà chưa có Wrapper, dùng bản Gradle 8.14.x đã cài để tạo Wrapper:

```bash
gradle wrapper --gradle-version 8.14.3
```

Đừng chép các lệnh chạy vào mã Java. Khi build thành công, Gradle có thể hiển thị `BUILD SUCCESSFUL`; số task, thời gian, log Spring và mức độ `UP-TO-DATE` khác nhau theo máy. **Đầu ra của method được assert chính xác:** `greet("  An  ")` → `Xin chào, An!`; `greet("Mai")` → `Xin chào, Mai!`. Test này không cố định stdout vì code không gọi `System.out.println`.

## 4. Những dependency nào thực sự thuộc `testImplementation`?

Dùng `testImplementation` khi trong `src/test/java` hoặc `src/test/kotlin` có **import, type reference, annotation, assertion, extension** của thư viện.

| Dependency | Khi dùng | Vì sao là `testImplementation` |
| --- | --- | --- |
| `org.springframework.boot:spring-boot-starter-test` | JUnit Jupiter, `@SpringBootTest`, AssertJ, Mockito, Spring Test utilities | Test import những API đó và cần chúng khi chạy |
| `org.springframework.security:spring-security-test` | `@WithMockUser`, `SecurityMockMvcRequestPostProcessors`, test OAuth2/security filter | Source test cần biên dịch các annotation/lớp test security |
| `org.testcontainers:junit-jupiter` | `@Testcontainers`, `@Container` | Test import extension JUnit |
| `org.testcontainers:postgresql` | Test trực tiếp dựng `PostgreSQLContainer` | Test tham chiếu type/container API |
| `com.squareup.okhttp3:mockwebserver` (nếu dùng Java API trực tiếp) | Test tự tạo mock HTTP server bằng class của thư viện | Test có import/lời gọi tới API |

Các dependency trong bảng là **ví dụ lựa chọn**, không phải danh sách bắt buộc của mọi dự án. Khi thêm Testcontainers, cần chọn đúng module/phiên bản tương thích với BOM và driver; khi dùng Spring Boot Testcontainers integration có thể cần thêm `org.springframework.boot:spring-boot-testcontainers`.

### 4.1. Tại sao không khai báo `spring-boot-starter-test` bằng `implementation`?

`spring-boot-starter-test` chứa framework và helper phục vụ test; code sản xuất không nên phụ thuộc vào JUnit, Mockito, AssertJ hoặc Spring Boot Test chỉ để ứng dụng chạy. Ví dụ không phù hợp:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-test' // Sai mục đích
}
```

Sửa thành:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Thư viện khai báo ở `testImplementation` **không tự động đi vào bootJar/JAR sản phẩm hoặc dependency API xuất bản** theo cấu hình Java/Spring Boot chuẩn. Nếu dự án tự cấu hình packaging đặc biệt, hãy kiểm tra cấu hình riêng đó.

## 5. Những dependency nào thuộc `testRuntimeOnly`?

Dùng `testRuntimeOnly` khi thư viện chỉ phải tồn tại lúc **test worker/JVM chạy**, còn Java test code không cần import/lấy kiểu từ thư viện đó để compile.

### 5.1. JUnit Platform Launcher

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

Phân biệt ba vai trò:

1. **JUnit Jupiter API:** định nghĩa `@Test`, `@BeforeEach`, `Assertions`, extension model; mã test import, nên cần trên **test compile classpath**.
2. **JUnit Jupiter Engine:** cơ chế phát hiện và thực thi test Jupiter; bắt buộc phải có trên **test runtime classpath**. `spring-boot-starter-test` thường đưa engine vào thông qua tập dependency JUnit Jupiter, nên không nhất thiết thêm dòng riêng.
3. **JUnit Platform Launcher:** lớp điều phối test engine, Gradle dùng ở **test runtime**; nên khai báo `testRuntimeOnly` tường minh.

Nếu cấu hình JUnit **không dùng starter** mà khai báo thủ công, có thể dùng:

```groovy
dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Đoạn này chỉ đầy đủ khi Gradle đã có cơ chế **quản lý phiên bản** cho các module JUnit (chẳng hạn Spring Boot BOM). Nếu không có BOM/version catalog phù hợp, phải khai báo phiên bản tương thích rõ ràng. `junit-jupiter` tổng hợp API và engine; vì vậy không cần thêm một `junit-jupiter-engine` dư thừa nếu nó đã có trong runtime graph. Có thể tách thành API `testImplementation` và engine `testRuntimeOnly` nếu chủ đích muốn kiểm soát chặt từng module.

### 5.2. H2 chỉ dành cho test

Giả sử ứng dụng dùng Spring Data JPA, production kết nối PostgreSQL, nhưng một số repository test dùng H2:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    // Driver dành cho ứng dụng chạy ở môi trường thật.
    runtimeOnly 'org.postgresql:postgresql'

    // Driver nhúng chỉ xuất hiện khi chạy test.
    testRuntimeOnly 'com.h2database:h2'
}
```

Với Spring Boot auto-configuration và cấu hình test phù hợp, H2 có thể được nhận diện để tạo DataSource thử nghiệm. Mã test bình thường gọi `JpaRepository`/`JdbcTemplate`, không import trực tiếp `org.h2.Driver`, nên H2 không cần trên test compile classpath.

**Giới hạn:** H2 không luôn tái hiện hành vi PostgreSQL (SQL dialect, JSONB, constraints, locking, transactions). Với truy vấn đặc thù DB hoặc yêu cầu độ trung thực cao, ưu tiên test chạy đúng engine, chẳng hạn PostgreSQL Testcontainers. Khi dự án đã cấu hình URL/driver cụ thể qua `application.yml` hoặc profile, cấu hình test phải chọn DB tường minh; **chỉ thêm H2 không bảo đảm Spring sẽ dùng H2**.

Nếu mã test tự viết:

```java
import org.h2.Driver;
```

thì `org.h2.Driver` là type cần khi compile, và **`testRuntimeOnly 'com.h2database:h2'` không đủ**. Khi thực sự cần import API đó, chuyển dependency sang `testImplementation`. Đa phần test JPA không nên thao tác trực tiếp với driver class.

### 5.3. Runtime engines/providers khác

Một engine được Java ServiceLoader/JUnit Platform phát hiện khi chạy có thể thuộc `testRuntimeOnly` nếu test code không import engine API. Ngược lại, annotation, extension hoặc type mà test dùng để khai báo test phải có trên `testCompileClasspath`; hãy kiểm tra chính xác module nào chứa API và module nào chứa engine. Không mặc định thư viện nào có chữ “test” cũng thuộc `testRuntimeOnly`.

## 6. So sánh cụ thể: đặt sai scope thì sao?

### Tình huống A — Đưa JUnit API vào `testRuntimeOnly`

```groovy
dependencies {
    testRuntimeOnly 'org.junit.jupiter:junit-jupiter-api'
}
```

Mã test:

```java
import org.junit.jupiter.api.Test;
class ExampleTest {
    @Test void verifiesSomething() {}
}
```

Với classpath test thông thường và **không có nguồn JUnit API nào khác**, `compileTestJava` sẽ báo lỗi đại loại `package org.junit.jupiter.api does not exist` vì API chỉ có ở runtime, không có lúc biên dịch. Giải pháp: `testImplementation 'org.junit.jupiter:junit-jupiter'` hoặc `spring-boot-starter-test`.

### Tình huống B — Đưa launcher vào `testImplementation`

```groovy
dependencies {
    testImplementation 'org.junit.platform:junit-platform-launcher'
}
```

Trường hợp này **không nhất thiết thất bại** vì `testImplementation` cũng góp mặt trong test runtime classpath; nhưng launcher xuất hiện không cần thiết ở classpath biên dịch. Nếu mã test không import launcher, `testRuntimeOnly` thể hiện đúng vai trò hơn và giới hạn classpath tốt hơn.

### Tình huống C — Bỏ `useJUnitPlatform()`

Với thiết lập `java`/`test` truyền thống, có dependency JUnit Jupiter không tự làm Gradle tự chuyển sang JUnit Platform. Cần cấu hình:

```groovy
tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Nếu sử dụng cấu hình khác như **Gradle JVM Test Suite `useJUnitJupiter()`**, plugin đó có thể làm sẵn phần lựa chọn framework. Xem đúng task nào đang chạy trước khi thêm cấu hình trùng lặp.

### Tình huống D — Thêm JDBC driver bằng `testRuntimeOnly` nhưng vẫn lỗi DataSource

Scope đúng là **điều kiện cần**, không đảm bảo test có URL, credentials, database, schema và profile phù hợp. Ví dụ `@SpringBootTest` có datasource chỉ tới PostgreSQL mà không có PostgreSQL đang chạy thì thêm H2 vào runtime không tự sửa URL. Cần kiểm tra cấu hình datasource hoặc dùng Testcontainers/dedicated test database.

### Tình huống E — Thấy test library có trong test classpath và tưởng nó nằm trong `bootJar`

Test runtime chứa cả dependency dành cho production lẫn test; đó là thiết kế. Nhưng Spring Boot `bootJar` chuẩn đóng gói từ runtime classpath của **main**, không phải `testRuntimeClasspath`. Phải kiểm tra scope đúng trong `build.gradle` và cấu hình build tùy biến thay vì kết luận từ nội dung dependency report của test.

## 7. Cách Gradle giải quyết dependency và đường truyền bắc cầu

Một thư viện được khai báo có thể kéo theo **transitive dependencies**. Ví dụ `spring-boot-starter-test` mang theo nhiều API test và JUnit modules. Không cần khai báo lại tất cả nếu dependency graph đã chứa chúng. Tuy nhiên:

- Dù một dependency xuất hiện “gián tiếp”, **classpath vẫn quyết định** việc mã test có compile/chạy được không.
- Một module có thể đến từ nhiều đường; Gradle chọn phiên bản dựa trên dependency constraints, platform/BOM và quy tắc resolution.
- Dependency management plugin của Spring Boot giúp đồng bộ phiên bản mà Boot đã kiểm thử. Bản Gradle/Boot khác nhau có thể dùng BOM khác nhau.
- `testRuntimeOnly` không “tước” transitive dependencies của `testImplementation` ở runtime. Những thứ cần thiết để chạy test và khai báo đúng metadata vẫn có thể đi kèm theo.
- `testImplementation` không đồng nghĩa “được export như API” cho module khác. Những dependency này phục vụ source set `test` của **chính module**.

Chú ý: `testImplementation` không tạo ra một task “unit test” riêng. Nếu có custom source set `integrationTest` hoặc JVM Test Suite `integrationTest`, dependency configuration tương ứng có thể là `integrationTestImplementation`/`integrationTestRuntimeOnly`; không mặc định giả định chúng kế thừa toàn bộ `testImplementation`. Hãy đọc cấu hình source set/suite của dự án trước khi chỉnh.

## 8. Lệnh thực tế để kiểm chứng đúng classpath

Thay vì đoán một thư viện đang ở đâu, hỏi chính Gradle:

```bash
# Liệt kê những thứ compiler nhìn thấy khi biên dịch test:
./gradlew dependencies --configuration testCompileClasspath

# Liệt kê những thứ test JVM có khi thực thi:
./gradlew dependencies --configuration testRuntimeClasspath

# Giải thích đường nào mang JUnit launcher vào test runtime:
./gradlew dependencyInsight --dependency junit-platform-launcher --configuration testRuntimeClasspath

# Xem nguyên nhân chọn phiên bản JUnit Jupiter:
./gradlew dependencyInsight --dependency junit-jupiter --configuration testRuntimeClasspath

# Biên dịch test (chưa chạy assertion):
./gradlew compileTestJava

# Chạy test:
./gradlew test

# Xem log chi tiết khi test không được phát hiện hoặc thiếu class lúc runtime:
./gradlew test --info
```

Trên Windows, đổi `./gradlew` thành `.\gradlew.bat`.

**Cách diễn giải đơn giản:**

- `junit-jupiter-api`/AssertJ xuất hiện trong `testCompileClasspath` để test source có thể import.
- `junit-platform-launcher` nên xuất hiện trong `testRuntimeClasspath` (nếu không bị kéo từ đường khác thì không thấy trên test compile classpath).
- `h2` khi khai báo bằng `testRuntimeOnly` sẽ có trong test runtime nhưng không nằm ở test compile.
- `spring-boot-starter` và những implementation dependency của ứng dụng có thể xuất hiện trong **cả** main và test runtime vì test cần chạy mã ứng dụng thực.
- Nếu dependency report hiển thị `(*)`, `(c)` hoặc constraint/version selection, đó là ký hiệu báo cáo Gradle; không suy ra mất thư viện chỉ từ một dòng bị rút gọn.

**Lưu ý về Gradle cache:** Nếu Gradle cho rằng task up-to-date và bỏ qua chạy test, dùng `./gradlew test --rerun-tasks` khi thực sự cần kiểm tra lại; không nên luôn ép chạy lại trong CI nếu không có lý do.

## 9. Cùng khái niệm trong Kotlin DSL

Nếu build dùng `build.gradle.kts`, tên configuration **giữ nguyên**, chỉ cú pháp khác:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.16"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.named<Test>("test") {
    useJUnitPlatform()
}
```

Đây là **phiên bản thay thế** của `build.gradle`, không đặt cả hai build file cạnh nhau trong một project rồi mong Gradle ghép cấu hình. Chọn một DSL theo dự án.

## 10. Khác gì với Maven `scope=test`?

Maven và Gradle cùng có ý tưởng quản lý classpath, nhưng **tên scope không tương ứng 1–1**.

Ví dụ Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Trong Maven, `test` scope cho phép dependency dùng trong **test compilation** và **test execution**, tương đối gần ý nghĩa `testImplementation`. Maven không có một scope chuẩn tên `testRuntimeOnly`; đừng dịch máy móc thành `<scope>runtime</scope>`, vì `runtime` của Maven có thể tham gia runtime chính của ứng dụng.

| Mục đích | Gradle (source set `test`) | Maven chuẩn |
| --- | --- | --- |
| Dependency cần ở compile và runtime của test | `testImplementation` | `scope=test` |
| Dependency chỉ ở test runtime | `testRuntimeOnly` | Không có scope chuẩn đối ứng trực tiếp |
| Driver cần ở runtime chính của app | `runtimeOnly` | `scope=runtime` |
| Thư viện compile/run cho mã chính | `implementation` | Thường `scope=compile` mặc định |

Maven Surefire/Failsafe có cách dựng test runtime classpath riêng; đừng suy luận cấu hình Gradle áp nguyên cho Maven.

## 11. Quy tắc ra quyết định nhanh

Hãy bắt đầu từ **test Java/Kotlin có import lớp của dependency hay không**, rồi hỏi thêm dependency đó có cần cho ứng dụng chạy thật hay không.

1. **Mã sản xuất dùng trực tiếp thư viện để compile và chạy?** → `implementation`.
2. **Mã sản xuất chỉ cần nó khi JVM chạy (ví dụ JDBC driver)?** → `runtimeOnly`.
3. **Test source import API/annotation hoặc gọi lớp của thư viện?** → `testImplementation`.
4. **Test source không tham chiếu nó khi compile, nhưng test JVM/runner cần tìm hoặc tải nó lúc chạy?** → `testRuntimeOnly`.
5. **Chỉ cần khi compile test, hoàn toàn không cần ở runtime?** → cân nhắc `testCompileOnly`; đây là tình huống ít gặp, và dùng nhầm có thể gây `NoClassDefFoundError` lúc chạy.

Nếu source test import một class và chỉ thêm thư viện vào `testRuntimeOnly`, lỗi thường xảy ra **ở `compileTestJava`**. Nếu source compile được nhưng lúc chạy thiếu driver/engine/provider, lỗi thường nằm **ở `test` / test runtime**. Hai loại lỗi dẫn đến hai classpath cần kiểm tra khác nhau.

## 12. Checklist khi cấu hình test Spring Boot

- [ ] Đã áp dụng plugin `java` hoặc plugin JVM tương ứng, có source set `test`.
- [ ] Đã đặt `spring-boot-starter-test` vào `testImplementation` (hoặc khai báo bộ test tương đương).
- [ ] Đã bật `useJUnitPlatform()` cho test task chạy JUnit Jupiter, trừ khi test suite plugin đã cấu hình tương đương.
- [ ] Đã khai báo `junit-platform-launcher` ở `testRuntimeOnly` theo hướng dẫn Gradle.
- [ ] Nếu dùng Spring Security test/Testcontainers API, các lớp import từ chúng nằm trên **test compile classpath**.
- [ ] Nếu dùng runtime test driver/engine, chúng nằm trên **test runtime classpath** và phiên bản tương thích.
- [ ] Đã phân biệt driver production `runtimeOnly` với driver test-only `testRuntimeOnly`.
- [ ] Đã xem `testCompileClasspath` và `testRuntimeClasspath` bằng `dependencies` thay vì suy đoán từ file build.
- [ ] Đã chạy `compileTestJava` và `test`; đếm số test được thực thi, phát hiện test bị skip ngoài dự kiến.
- [ ] Không đưa các thư viện unit testing vào `implementation` chỉ vì lỗi import ở `src/test/java`.

## 13. Tự kiểm tra kiến thức

**Câu 1:** Vì sao test chứa `import org.junit.jupiter.api.Test;` không compile khi chỉ khai báo JUnit API ở `testRuntimeOnly`?  
**Trả lời:** Vì compiler test chỉ nhìn `testCompileClasspath`, còn `testRuntimeOnly` chỉ đóng góp cho `testRuntimeClasspath`.

**Câu 2:** Vì sao `testImplementation 'spring-boot-starter-test'` vẫn có mặt khi chạy test?  
**Trả lời:** `testImplementation` góp mặt ở cả test compile và runtime classpaths; “implementation” trong tên không có nghĩa compile-only.

**Câu 3:** Có thể đặt launcher ở `testImplementation` không?  
**Trả lời:** Về mặt classpath, thường vẫn chạy được vì runtime bao gồm `testImplementation`; nhưng `testRuntimeOnly` thể hiện chính xác mục đích và tránh thêm không cần thiết vào compile classpath.

**Câu 4:** Vì sao `testRuntimeOnly 'com.h2database:h2'` có thể phù hợp cho JPA test?  
**Trả lời:** Spring/DataSource nạp JDBC driver lúc test chạy, trong khi test code có thể chỉ import JPA repository và không import H2.

**Câu 5:** Nếu test cần `@WithMockUser`, chọn scope nào cho `spring-security-test`?  
**Trả lời:** `testImplementation`, vì mã test tham chiếu annotation đó lúc biên dịch.

**Câu 6:** Test bằng Gradle đang báo “No tests found”. Chỉ thêm launcher có đủ không?  
**Trả lời:** Chưa chắc; còn phải xác nhận `useJUnitPlatform()`, test engine, đường dẫn source set, annotation và filter `--tests`.

**Câu 7:** Dependency ở `testRuntimeOnly` có tự động được đóng gói vào `bootJar` chính không?  
**Trả lời:** Không, với cấu hình chuẩn `bootJar` dùng runtime classpath của `main`, còn `testRuntimeOnly` chỉ phục vụ source set `test`.

## 14. Tài liệu chính thức

- Gradle – [Dependency configurations](https://docs.gradle.org/current/userguide/dependency_configurations.html): khái niệm scope, `testImplementation` và `testRuntimeOnly`.
- Gradle – [Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): relationship giữa configuration khai báo và hai test classpath.
- Gradle – [Testing in Java & JVM projects](https://docs.gradle.org/current/userguide/java_testing.html): `useJUnitPlatform()`, test task, JUnit launcher, test source set.
- Spring Boot 3.5 – [Gradle Plugin](https://docs.spring.io/spring-boot/3.5/gradle-plugin/): phiên bản Gradle tương thích và cấu hình plugin.
- Spring Boot 3.5 – [System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html): Java/Gradle được hỗ trợ.
- Spring Boot – [Managing Dependencies](https://docs.spring.io/spring-boot/3.5/gradle-plugin/managing-dependencies.html): Spring Boot BOM và dependency management.
- JUnit 5 – [User Guide](https://junit.org/junit5/docs/current/user-guide/): JUnit Jupiter/Platform và engine.

**Điểm cần nhớ:** `testImplementation` trả lời “*test code cần thư viện này để biên dịch và chạy không?*”, còn `testRuntimeOnly` trả lời “*thư viện chỉ cần xuất hiện khi test được thực thi không?*”. Hiểu được khác biệt đó giúp cấu hình build đúng, tránh mang dependency test vào ứng dụng và chẩn đoán chính xác lỗi compile so với lỗi runtime.
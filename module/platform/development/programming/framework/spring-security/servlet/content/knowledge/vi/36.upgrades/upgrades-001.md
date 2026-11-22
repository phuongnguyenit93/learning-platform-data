# Đọc hướng dẫn di chuyển đúng cặp phiên bản và quản lý dependency bằng BOM

> **Bối cảnh:** Java 17+, Spring Security **Servlet**, Spring Boot, Maven/Gradle. Nâng cấp an toàn không chỉ là sửa số phiên bản cho build thành công. Cần chọn **đúng cặp nguồn → đích**, sử dụng migration guide khớp cặp đó, quản lý các dependency liên quan thống nhất bằng BOM và kiểm thử lại hành vi bảo mật của HTTP filter chain.
>
> **Lưu ý về phiên bản:** Những số như Spring Boot `3.5.0`, Spring Security `6.5.0` trong các ví dụ cú pháp chỉ là **phiên bản minh họa**, không phải khẳng định bản mới nhất hoặc một chỉ dẫn áp dụng cứng cho dự án của bạn. Trước khi nâng cấp thật, phải kiểm tra release được hỗ trợ, managed dependencies của **chính Spring Boot target** và resolved dependency graph trong build.

## 1. Vì sao không thể chỉ “nâng Spring Security lên bản mới nhất”?

Một ứng dụng Spring Security Servlet hoạt động trong một hệ sinh thái gồm:

- **JDK** biên dịch và chạy.
- **Spring Boot**: auto-configuration, starters, managed dependencies và packaging.
- **Spring Framework**: Web MVC, DI, AOP, transactions, HTTP abstractions.
- **Spring Security**: authentication, authorization, Servlet filters, sessions, OAuth2.
- **Servlet container/Jakarta API**: Tomcat/Jetty/Undertow, `jakarta.servlet.*`.
- **Thư viện bổ sung**: Spring Session, Spring Cloud, JPA, OAuth client/resource server, JWT, SAML và test framework.

Các thành phần này phải **tương thích ở thời điểm chạy**. Ví dụ một Maven module compile với `spring-security-config` thuộc release mới nhưng runtime lại kéo `spring-security-web` hoặc `spring-core` cũ có thể gây `NoSuchMethodError`, `NoClassDefFoundError` hoặc thay đổi hành vi filter.

Ngược lại, mọi artifact đều resolve được cũng **chưa chứng minh** hệ thống an toàn: thay đổi mặc định của Spring Security có thể khiến `/api/**` bị form-login redirect thay vì Bearer 401, CSRF bị xử lý khác hoặc một custom `SecurityFilterChain` không được chọn.

**Quy trình đúng:** biết phiên bản thực tế → xác định release target → đọc hướng dẫn migration source-to-target → align dependency qua một nguồn quản lý nhất quán → kiểm tra resolved versions → chạy security regression tests.

## 2. “Cặp phiên bản” nghĩa là gì?

Không chỉ có một cặp `spring-security-core` cũ và mới. Cần ghi lại **ma trận tương thích** của toàn ứng dụng.

| Thành phần | Bản nguồn phải đo được | Bản đích cần xác định | Rủi ro nếu đoán |
| --- | --- | --- | --- |
| Java runtime/toolchain | JDK trong CI và container | Minimum Java của Boot đích | Build pass trong IDE, runtime fail |
| Spring Boot | Parent/BOM/plugin release thật | Release Boot được tổ chức chọn | Auto-config/starter thay đổi |
| Spring Framework | Resolved `spring-*` artifacts | Bản do Boot đích quản lý | API incompatibility |
| Spring Security | Resolved `core`, `web`, `config`, OAuth2, test | Nhánh/patch do Boot target quản lý | Lệch Security filters/DSL |
| Servlet/Jakarta | Servlet API và container hiện tại | Container tương thích Boot target | `javax`/`jakarta` mismatch |
| Modules liên quan | Session, Cloud, Data, OAuth, SAML | Release train tương thích | Config/classpath không khớp |
| Test tooling | `spring-security-test`, JUnit, MockMvc | Test artifacts cùng hệ target | Test giả/lỗi runtime |

Ví dụ **loại đường nâng cấp**, không phải một cặp duy nhất:

1. **Patch update** trong cùng nhánh Boot: xem release notes, security advisories, dependency changes và tests.
2. **Minor update** Boot 3.x → Boot 3.y: đọc upgrading/release notes của minor target và Security release tương ứng.
3. **Major update** Boot 2.7 → Boot 3.x: cần đọc Boot 2→3, Security 5→6, Framework/Jakarta guidance và nâng Java đúng baseline.
4. **Major tiếp theo** Boot 3.x → nhánh sau: đọc **guide cho đúng source/target**, không lặp máy móc checklist 2→3.
5. **Non-Boot Spring app** dùng Security trực tiếp: có thể dùng Security BOM nhưng vẫn phải đối chiếu Framework/Servlet compatibility riêng.

Đừng suy “Boot 3 luôn gắn với một bản Security 6.y cố định” cho mọi patch/minor. Version cuối cùng là kết quả của **managed dependencies và dependency resolution**; kiểm tra thực tế.

## 3. Phân biệt dependency được khai báo và dependency đã resolve

Một dòng Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
```

Không khai báo `<version>` có thể **đúng và nên làm** khi Maven project kế thừa `spring-boot-starter-parent` hoặc import `spring-boot-dependencies`. Version được điền bởi dependency management.

Ngược lại, dòng:

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-web</artifactId>
    <version>6.5.0</version>
</dependency>
```

trong một Boot app đã quản lý Security có thể vô tình **override** version mà Boot target dự kiến. Không nên ghim version từng module một cách tùy tiện.

Cần phân biệt:

- **Declared**: dependency được khai báo.
- **Managed**: version được BOM hoặc parent đề xuất/quản lý.
- **Resolved**: version build tool chọn cuối cùng sau dependency graph, constraints/overrides.
- **Runtime**: thư viện thật sự được deploy và classloader nạp.

Đây không phải bốn cách nói cùng một dữ liệu. **Dependency tree/effective POM/Gradle insight** mới cho bằng chứng resolved versions; dependency trong `pom.xml` hoặc IDE display riêng lẻ chưa đủ.

## 4. Xác minh baseline trước khi chọn migration guide

### 4.1. Maven

Chạy tại root của dự án Maven (nếu multi-module, kiểm tra cả module deploy):

```bash
mvn -version
mvn help:effective-pom -Doutput=effective-pom.xml
mvn dependency:tree "-Dincludes=org.springframework.security:*"
mvn dependency:tree "-Dincludes=org.springframework:*"
mvn dependency:tree "-Dincludes=org.springframework.boot:*"
mvn clean verify
```

**Đọc kết quả:**
- `spring-security-core`, `spring-security-web`, `spring-security-config`, `spring-security-test` cùng release line/version hay không?
- Có một dependency hoặc `dependencyManagement` cố định version khác BOM không?
- `spring-framework`/`spring-webmvc` theo Boot release đang dùng không?
- Có artifact `javax.servlet` hoặc Spring Framework cũ đi vào runtime sau khi lên Jakarta không?
- Maven profiles, parent POM, properties hoặc reactor modules có override nhau không?

`mvn help:effective-pom` giúp quan sát model sau khi parent/import/profile có hiệu lực. `mvn dependency:tree` cho bạn **resolved dependency graph**. Với project nhiều module, cần chạy/báo cáo đúng module; không suy từ dependency tree của module phụ sang application deploy.

### 4.2. Gradle

```bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency spring-security-web \
  --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew clean test
```

Trên Windows, có thể dùng `gradlew.bat` hoặc `.\gradlew.bat` theo shell. `runtimeClasspath`, `compileClasspath`, `testRuntimeClasspath` có thể khác nhau; `dependencyInsight` giúp tìm **vì sao** Gradle chọn một version.

Với multi-project, dùng đường dẫn module cụ thể (chẳng hạn `:api:dependencyInsight`) vì root project có thể không chứa runtime dependencies. Đừng dựa vào một màn hình IDE hiển thị library versions rồi khẳng định mọi cấu hình Gradle có cùng classpath.

### 4.3. Lưu bằng chứng trước khi sửa

Một migration record hữu ích gồm:
- JDK/CI/container runtime;
- Boot parent/plugin/BOM version;
- Security resolved artifacts và versions;
- Servlet/container target;
- ứng dụng sử dụng form login, session, Basic, Bearer, JWT, opaque, OAuth2 login hay SAML;
- kết quả unit/integration/security tests trước upgrade;
- danh sách explicit overrides, compatibility constraints và known issues.

Nếu thiếu baseline, khi upgrade gặp lỗi sẽ khó biết đó là lỗi **version alignment** hay lỗi **thay đổi behavior**.

## 5. Đọc tài liệu migration đúng nguồn và đúng đích

Các điểm vào tài liệu chính thức:

- **Spring Boot Reference — Upgrading**: `https://docs.spring.io/spring-boot/how-to/upgrading.html`.
- **Spring Security Reference — Migration**: `https://docs.spring.io/spring-security/reference/migration/`.
- **Spring Framework documentation**: lựa chọn migration/upgrade notes theo phiên bản Framework do Boot target quản lý.
- **Spring Boot dependency versions**: xem danh sách managed dependencies/BOM của **release được chọn**, không chọn theo một bảng phiên bản chung đã cũ.

Các đường dẫn trên là **điểm vào**; khi đọc phải chọn selector/nhánh/release notes phù hợp. Tài liệu “current” có thể mô tả phiên bản mới hơn dự án. Không thay một guide version-specific bằng snippet blog không ghi rõ version.

### 5.1. Chọn guide theo kiểu nâng cấp

| Source → target | Cách đọc | Chú ý |
| --- | --- | --- |
| Boot patch → patch | Changelog, CVEs, dependency update, smoke tests | Không mặc định “patch không thay behavior” |
| Boot minor → minor | Release notes target, upgrading guide, Security minor notes | Defaults, plugins, auto-config, deprecations |
| Boot 2.x → 3.x | Boot 2→3, Security 5→6, Framework 5→6 và Jakarta | Java 17, Servlet/Jakarta packages, DSL |
| Security 5.x → 6.x không dùng Boot | Security migration guide source→target, Framework/Servlet compatibility | Removed APIs, request matchers, custom providers |
| Boot 3.x → major mới | Guide Boot 3→target, tương ứng Security/Framework target | **Không** áp lại checklist Boot 2→3 một cách mù quáng |
| Security patch override trong Boot | Boot-managed versions, chính sách override được hỗ trợ, advisory | Tránh trộn patch artifacts và release trains |

**Quan trọng:** “nâng lên Spring Security 6” chỉ mô tả major. Các target minor/patch của Security 6 không tự giống nhau. Chọn actual resolved target versions rồi đọc guide phần “breaking change/behavior change” của những bước đi qua.

### 5.2. Biến guide thành danh sách hành động

Với từng mục migration note, ghi:
1. **API/config bị ảnh hưởng** (nếu project có dùng).
2. **Thay đổi code** cần làm.
3. **Thay đổi behavior/default** dù code không lỗi compile.
4. **Dependency/library liên quan**.
5. **Test hồi quy** xác minh hành vi trước–sau.
6. **Rủi ro triển khai/rollback**.

Ví dụ Security guide đề cập HTTP authorization. Đừng chỉ đổi tên method; hãy kiểm `/api/**` còn được chọn bởi chain đúng, user thiếu quyền bị từ chối 403, request anonymous nhận 401 hoặc redirect đúng và CSRF không vô ý tắt.

## 6. BOM: Bill of Materials làm gì?

**BOM** là một bản mô tả các **managed dependency versions** của một họ artifact hoặc một platform. Với Maven, BOM được import trong `<dependencyManagement>` (thường `type=pom`, `scope=import`). Với Gradle, BOM có thể được tiêu thụ bằng native `platform(...)` hoặc dependency-management plugin.

BOM không làm các việc sau:
- Không tự thêm dependencies vào project.
- Không tạo `SecurityFilterChain`/JWT decoder/CSRF filter.
- Không chứng nhận Spring Boot + một Security override tùy ý là tương thích.
- Không đảm bảo runtime classloader không có JAR external do container đưa vào.
- Không thay integration tests hay code review.

Mục tiêu: **một tập artifact dùng các version đã được quản lý cùng nhau**, tránh việc developer ghi riêng `spring-security-core=6.5.0`, `web=6.2.0`, `config=5.8.16`.

### 6.1. Spring Boot app: ưu tiên Boot quản lý dependency

`spring-boot-dependencies` quản lý Spring Security **và nhiều thư viện khác** (Spring Framework, JSON, embedded container, test tooling...). Đó thường là lựa chọn mặc định cho Spring Boot application.

Nếu ứng dụng không dùng Boot nhưng sử dụng Spring Security trên Spring MVC/Servlet trực tiếp, có thể import `spring-security-bom` để đồng bộ nhóm Security. **Tuy nhiên Security BOM không quản lý toàn bộ Framework/Servlet ecosystem**, nên compatibility vẫn phải kiểm riêng.

## 7. Maven: dùng spring-boot-starter-parent

Ví dụ một Maven POM ứng dụng Spring Boot, minh họa với Boot version `3.5.0`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>security-upgrade-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
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

Ở đây **không ghi version cho Security starter hoặc Security Test**. Parent Boot quản lý những version tương thích theo release của nó. Khi sử dụng Resource Server, thêm `spring-boot-starter-oauth2-resource-server` mà không cần ghim version riêng, rồi cấu hình JWT/introspection phù hợp. Không coi việc có dependency là đủ để authentication an toàn.

Parent Boot còn cung cấp build/plugin defaults tiện lợi. Tuy nhiên nó vẫn không tự thêm mọi starter, không tự phân quyền cho từng endpoint và không thay việc cấu hình HTTPS/CSRF/session.

### 7.1. Multi-module Maven và parent nội bộ

Nếu công ty dùng corporate parent POM, một module không thể có **hai** parent. Có thể:
- Dùng corporate parent kế thừa tiếp Boot parent nếu policy cho phép; hoặc
- Import Spring Boot BOM trong `dependencyManagement` của corporate/root POM, quản lý build plugins riêng.

Dù chọn cách nào, các child modules vẫn có thể khai báo explicit version hoặc `dependencyManagement` riêng. Phải kiểm tra effective POM từng module trọng yếu.

## 8. Maven: import spring-boot-dependencies khi không dùng Boot parent

Phần POM minh họa:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.5.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Đây là một **đoạn POM**, không phải file chạy độc lập. Nó quản lý dependency versions nhưng **không kế thừa tất cả cấu hình Maven plugin** của `spring-boot-starter-parent`. Vì vậy dự án cần quản lý `maven-compiler-plugin`, `maven-surefire-plugin`, `spring-boot-maven-plugin` và các plugin khác theo parent/build policy của chính mình.

**Không nhầm:** `dependencyManagement` cung cấp version rules; `dependencies` mới yêu cầu artifact đi vào graph. Import BOM không tự khai báo `spring-security-config`, cũng không làm ứng dụng nhận bearer token khi thiếu Resource Server configuration.

### 8.1. Nhiều BOM có thể xung đột

Một build import Boot BOM và một BOM khác có thể có cùng artifact keys. Thứ tự import, direct declarations, existing dependencyManagement và version overrides có thể ảnh hưởng version được chọn. Không sử dụng mẹo “BOM cuối cùng luôn thắng” như quy tắc chung. Hãy đọc **effective POM** và **resolved dependency tree**.

Đối với project Boot, ưu tiên để **một nguồn Boot BOM** quản lý nhóm Spring. Chỉ dùng Security version override khi có advisory/compatibility evidence và đã kiểm thử toàn bộ runtime modules.

## 9. Maven: khi nào dùng spring-security-bom riêng?

Nếu ứng dụng dùng Spring Security Servlet **không thông qua Spring Boot BOM**, có thể import Security BOM:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-bom</artifactId>
            <version>6.5.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-config</artifactId>
    </dependency>
</dependencies>
```

**Không áp dụng đoạn này như một override tùy tiện bên cạnh Spring Boot BOM.** Nó minh họa tình huống non-Boot. Security BOM thống nhất module Security, nhưng không quyết định Spring Framework, Servlet container, JWT/OAuth integrations hoặc application server version. Vẫn phải đối chiếu compatibility của cả hệ thống.

Ví dụ dependency tree **đáng nghi**:

```text
org.springframework.security:spring-security-core:6.5.0
org.springframework.security:spring-security-web:6.5.0
org.springframework.security:spring-security-config:5.8.16
org.springframework.security:spring-security-test:6.5.0
```

Đây là dữ liệu giả minh họa mismatch, **không phải kết quả từ project thật**. Hãy tìm nơi pin config 5.8.16 hoặc nơi dependency resolution chọn bản cũ, rồi sửa ở nguồn quản lý version. Đừng tùy tiện exclude `spring-security-config` nếu ứng dụng cần Security DSL.

## 10. Gradle: Boot plugin và dependency-management plugin

Ví dụ `build.gradle.kts` cho một Spring Boot application dùng Java 17:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.0"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}

tasks.test {
    useJUnitPlatform()
}
```

Khi kết hợp Boot Gradle plugin và `io.spring.dependency-management` plugin theo tài liệu tương ứng, Boot BOM được sử dụng để quản lý versions. Vì vậy không cần thêm từng version Security.

Version của Boot/Gradle/dependency-management plugin trong ví dụ là **cú pháp minh họa**. Trong dự án thật hãy kiểm tra compatibility Gradle/JDK/plugins theo target Boot và dùng wrapper version đã được nghiệm thu.

### 10.1. Gradle native platform: cách khác để sử dụng BOM

Nếu dùng Gradle native BOM, ví dụ một Java module với Groovy DSL:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.5.0')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.5.0')
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

test {
    useJUnitPlatform()
}
```

`platform(...)` đưa các BOM constraints vào configurations liên quan; BOM **không tự thêm** các dependencies mà project chưa khai báo. Dùng `dependencyInsight` để xác minh selected versions, đặc biệt khi có constraints/forced versions khác.

Không nhất thiết vừa dùng dependency-management plugin, vừa import cùng Boot BOM qua native platform, lại vừa ép Security BOM khác version. Nếu có nhiều cơ chế trong một build phức tạp, cần policy rõ ràng và kiểm tra graph thực.

**`enforcedPlatform`** có thể cưỡng ép versions mạnh hơn `platform`; tránh dùng bừa trong shared libraries vì có thể áp lực lên downstream consumers. Gradle version catalogs (`libs.versions.toml`) giúp quản lý **khai báo versions** nhưng không tự thay thế việc tiêu thụ một BOM nhất quán.

## 11. Java 17 thực hành: phát hiện Security artifacts bị trộn versions

Đây là bài tập Java thuần dùng JDK 17; minh họa cách **kiểm tra tính nhất quán nội bộ** của module Security sau khi đã lấy resolved data từ Maven/Gradle. Nó **không phải** bộ kiểm tra chính thức cho compatibility Boot/Security và không đọc build file.

File `SecurityVersionAuditDemo.java`:

```java
import java.util.List;

public final class SecurityVersionAuditDemo {
    record Dependency(String group, String artifact, String version) {}

    static String audit(List<Dependency> deps) {
        List<String> versions = deps.stream()
            .filter(d -> d.group().equals("org.springframework.security"))
            .map(Dependency::version)
            .distinct()
            .sorted()
            .toList();

        if (versions.isEmpty()) return "NONE";
        if (versions.size() == 1) return "ALIGNED " + versions.get(0);
        return "MIXED " + versions;
    }

    public static void main(String[] args) {
        List<Dependency> aligned = List.of(
            new Dependency("org.springframework.security", "spring-security-core", "6.5.0"),
            new Dependency("org.springframework.security", "spring-security-web", "6.5.0"),
            new Dependency("org.springframework.security", "spring-security-config", "6.5.0")
        );
        List<Dependency> mixed = List.of(
            new Dependency("org.springframework.security", "spring-security-core", "6.5.0"),
            new Dependency("org.springframework.security", "spring-security-web", "6.5.0"),
            new Dependency("org.springframework.security", "spring-security-config", "5.8.16")
        );

        System.out.println(audit(aligned));
        System.out.println(audit(mixed));
    }
}
```

Biên dịch/chạy:

```bash
javac SecurityVersionAuditDemo.java
java SecurityVersionAuditDemo
```

Stdout chính xác:

```text
ALIGNED 6.5.0
MIXED [5.8.16, 6.5.0]
```

**Giới hạn:** output `ALIGNED` ở đây chỉ nghĩa các Security modules trong **danh sách giả lập** có cùng version string. Nó không chứng minh Boot, Spring Framework và Servlet container có tương thích; cũng không kiểm transitive dependencies, advisory hay test behavior. Với dự án thật, nguồn dữ liệu phải đến từ resolved dependency graph của build tool, không phải danh sách viết tay.

## 12. Migration Spring Security 5 → 6: các điểm trọng yếu trên Servlet

Khi thực sự nâng qua Security major 6, đọc migration guide về API removals, defaults và những điều kiện cần chuẩn bị từ nhánh 5.x. Các mục dưới đây là **những điểm cần kiểm tra**, không phải yêu cầu sửa mọi project.

### 12.1. WebSecurityConfigurerAdapter → SecurityFilterChain bean

Cấu hình kiểu cũ:

```java
// Mã legacy dùng để nhận diện khi migrate, không dùng ở Security 6:
public class LegacySecurityConfig extends WebSecurityConfigurerAdapter {
    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http.authorizeRequests()
            .anyRequest().authenticated();
    }
}
```

`WebSecurityConfigurerAdapter` bị deprecated trong Security 5.7 và đã bị loại trong Security 6. Mẫu mới:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated());
        return http.build();
    }
}
```

Đây là code **trong Spring Boot/Spring Security application**, không chạy độc lập bằng `javac`. Đừng chỉ sửa cho compile: nếu ứng dụng cũ có nhiều chains, custom authentication hoặc route-specific config, phải chuyển semantics/thứ tự đúng và kiểm thử filter selection.

### 12.2. authorizeHttpRequests và requestMatchers

Cú pháp `antMatchers`/`mvcMatchers` của config API cũ được thay bằng các matcher APIs phù hợp trong Security 6. Ví dụ:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated());
```

**`http.securityMatcher(...)` chọn toàn bộ SecurityFilterChain**, trong khi `authorizeHttpRequests(...requestMatchers...)` quyết định rules **sau khi chain đã được chọn**. Spring Security thường chọn **SecurityFilterChain đầu tiên khớp request** theo order. Một catch-all chain đứng trước API chain có thể khiến API filters không bao giờ chạy.

Không đổi `antMatchers` → `requestMatchers` máy móc rồi bỏ qua thay đổi semantics: test URL với contextPath, servletPath, MVC mapping, encoded slashes và firewall behaviors theo app.

### 12.3. Java 17 và javax → jakarta

Spring Boot 3/Spring Framework 6 sử dụng Jakarta APIs cho nhiều Java EE namespaces. Ví dụ:

```java
// Trước (đối với các Java EE APIs cũ):
import javax.servlet.Filter;
import javax.servlet.http.HttpServletRequest;
import javax.validation.Valid;

// Sau:
import jakarta.servlet.Filter;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
```

Không tìm-thay **tất cả** `javax.`, vì `javax.crypto`, `javax.net.ssl` và nhiều Java SE packages không đổi. Chỉ di chuyển các Jakarta EE packages tương ứng và nâng dependencies của Servlet container/Validation/JPA libraries theo guide. Một WAR Jakarta không tự chạy được trên servlet container Java EE cũ.

Spring Boot 3 yêu cầu Java 17 trở lên; cũng phải nâng **CI JDK, toolchain, Docker runtime và compiler plugin** cho đúng target, không chỉ sửa `java.version` trong POM.

### 12.4. Method security

Nếu ứng dụng đang dùng `@EnableGlobalMethodSecurity`, đọc guide cho `@EnableMethodSecurity` và các khác biệt về AuthorizationManager, defaults và cách chạy expressions.

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {}
```

`@PreAuthorize`/`@PostAuthorize` còn phải được test với user đủ và thiếu quyền. Một method được gọi trực tiếp qua `this.method()` có thể bypass Spring proxy; việc nâng annotation không sửa được kiến trúc proxy sai.

### 12.5. SecurityContext và lưu context

Ở Security 6 Servlet, cơ chế `SecurityContextHolderFilter` và `SecurityContextRepository`/explicit save có thể ảnh hưởng custom authentication. Nếu tự tạo `Authentication` sau login **cần persist qua request tiếp theo**, phải xem guide và cân nhắc:

```java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authenticated);
SecurityContextHolder.setContext(context);

// Chỉ với luồng stateful cần ghi context cho request sau:
securityContextRepository.saveContext(context, request, response);
```

Đây là **snippet trong handler đã có authenticated/request/response/repository**, không phải file độc lập. Không “fix” bằng cách lưu mọi Bearer Authentication vào HTTP session: Resource Server stateless có threat model khác.

### 12.6. Những thay đổi không gây compile error

Đặc biệt cần kiểm thử:
- `GET /api/**` anonymous trả 401 hay redirect 302?
- `POST` cookie-authenticated còn CSRF protection?
- Session fixation đổi ID sau login?
- Logout, remember-me và concurrent sessions còn chính xác?
- Resource Server vẫn xác minh JWT signature/issuer/audience/expiry?
- Access denied trả 403 khi thiếu scope/authority?
- Static assets và public endpoints có nhận headers theo thiết kế?
- Custom filter có được thêm đúng chain/đúng thứ tự, không double registration?
- Error/async dispatch có đi qua security boundary cần thiết?

**BOM không phát hiện những lỗi hành vi này.**

## 13. Ví dụ Spring Security 6: hai chains có hành vi test được

File `TwoChainsConfig.java` trong một Spring Boot Servlet app:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class TwoChainsConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http)
            throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/assets/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
```

Chain API đứng trước web catch-all. `securityMatcher` chọn chain; `requestMatchers` trong `authorizeHttpRequests` chọn rule. Ví dụ không tắt CSRF toàn cục: browser có thể tự gửi HTTP Basic credentials hoặc cookie, nên CSRF cần đánh giá theo cơ chế credential. Nếu API thật dùng Bearer header-only, hãy thiết kế Resource Server + CSRF riêng theo trust model; không copy `csrf.disable()` tùy tiện.

File `SmokeController.java`:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SmokeController {
    @GetMapping("/api/public/ping")
    String ping() { return "pong"; }

    @GetMapping("/api/private")
    String privateApi() { return "private"; }

    @GetMapping("/dashboard")
    String dashboard() { return "dashboard"; }
}
```

Những endpoint này chỉ phục vụ regression tests về security chains, không có dữ liệu nghiệp vụ. Nếu test Basic đăng nhập thành công, cần cung cấp `UserDetailsService`/test credentials tương ứng; riêng các anonymous tests dưới đây không cần giả định user cụ thể.

## 14. MockMvc security regression tests sau upgrade

File `SecurityUpgradeSmokeTests.java` trong project có `spring-boot-starter-test` và `spring-security-test`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityUpgradeSmokeTests {
    @Autowired MockMvc mvc;

    @Test
    void anonymousApiGetsBasicChallenge() throws Exception {
        mvc.perform(get("/api/private"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "WWW-Authenticate", containsString("Basic")));
    }

    @Test
    void publicApiIsAccessible() throws Exception {
        mvc.perform(get("/api/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void anonymousWebRedirectsToLogin() throws Exception {
        mvc.perform(get("/dashboard"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void similarPrefixIsNotApiChain() throws Exception {
        mvc.perform(get("/apiary"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }
}
```

Chạy:

```bash
mvn -Dtest=SecurityUpgradeSmokeTests test
# Hoặc với Gradle project đã cấu hình test task:
./gradlew test --tests SecurityUpgradeSmokeTests
```

Đây là bộ test **minimum smoke**. Không có stdout ứng dụng cố định vì test runner quyết định report. Nó chứng minh một số boundary giữa API/web chains; không tự chứng minh JWT cryptographic verification, CSRF của POST, sessions hoặc method authorization.

### 14.1. Ma trận test cần có ngoài smoke

| Chủ đề | Negative/positive tests |
| --- | --- |
| Login/session | Password sai/đúng; session fixation ID rotation; concurrent sessions nếu có |
| CSRF | Unsafe POST thiếu token bị chặn khi cookie-auth; POST đủ token được phép nếu đủ quyền |
| HTTP Basic | Không header / header sai / credentials đúng; entry point không redirect nhầm |
| JWT Resource Server | JWT ký sai, hết hạn, issuer/audience không đúng; scope đúng/sai |
| OAuth2 Login | Authorization redirect, callback, state, user mapping, logout |
| Method security | `@PreAuthorize` với user đủ/thiếu role và owner |
| URL matchers | `/api/**`, `/apiary`, contextPath/servletPath, encoded path variants |
| HTTP headers | CSP, nosniff, HSTS trên HTTPS, session cookie flags |
| Session/remember-me | Logout/invalidated session, remember-me token lifecycle |
| Error/async | Error dispatch, async worker/auth context, custom filters |
| Persistence/Jakarta | Controller, validation, JPA, Servlet filter compile và chạy đúng |

**Khi dùng `with(jwt())` trong Spring Security Test**, đó là mock authentication, **không phải bằng chứng JWT decoder đã kiểm chữ ký của token thật**. Phải có test integration tương ứng nếu Resource Server là thành phần quan trọng.

## 15. Phân biệt lỗi version/classpath với lỗi security behavior

| Triệu chứng | Kiểm tra trước |
| --- | --- |
| `NoSuchMethodError` | Có hai versions Framework/Security/Jakarta trong runtime? |
| `ClassNotFoundException` / `NoClassDefFoundError` | Artifact bị thiếu, scope sai, classpath WAR/container khác IDE? |
| Build compile nhưng app không start | Boot auto-config, Servlet container, plugin/Java baseline, version graph |
| API 302 về login thay vì 401 | SecurityFilterChain match/order, authentication entry point |
| 403 sau upgrade | CSRF filter hay AuthorizationFilter/method security? |
| Anonymous request được 200 ở protected endpoint | Chain không match, bypass/permitAll sai, method security mất hiệu lực |
| JWT hợp lệ bị 401 | Decoder/issuer/audience/clock/algorithm, filter đúng chain? |
| `spring-security-test` gặp lỗi runtime | Test module version có đồng bộ runtime Security/Framework? |
| Static asset mất security headers | `web.ignoring`, matcher, filter chain, proxy/CDN rewrite? |
| App lên Boot 3 chạy trên server cũ | Servlet/Jakarta container incompatibility? |

Nếu classpath chưa đúng, **sửa dependency alignment trước** để các lỗi sau có ý nghĩa. Nếu classpath đã đúng mà request sai, phân tích security behavior bằng logs an toàn, chain inventory và tests. Đừng sửa bằng cách nới `permitAll` hoặc tắt CSRF cho nhanh.

## 16. Rollout và rollback sau nâng cấp

Với một ứng dụng production, upgrade nên có stages:

1. **Baseline:** lưu dependency tree, test results, Java/container versions, security config và các HTTP contracts.
2. **Select target:** xác minh release/lifecycle được hỗ trợ, BOM/managed versions, compatibility matrix.
3. **Read source→target guides:** Boot + Security + Framework/Jakarta + integrations, ghi migration ledger.
4. **Align build:** đổi version tại đúng parent/BOM/plugin; xóa overrides không cần; test multi-module.
5. **Migrate source:** sửa APIs, imports, filter-chain selection, method security và custom auth lifecycle.
6. **Test:** compile, full test suite, MockMvc, integration HTTP, browser/session, OAuth/JWT, deployment smoke.
7. **Staging:** chạy trên JDK/container thật, kiểm logs/headers/metrics, xác minh cookie/sessions.
8. **Rollout:** canary hoặc progressive rollout; giám sát 401/403/5xx, login failures, latency, token validation.
9. **Rollback:** giữ artifact/container image và cấu hình trước nâng; đánh giá migrations schema/session/serialization có tương thích khi rollback không.
10. **Document:** ghi cặp source/target, dependency tree trước/sau, guides được dùng, test evidence và vấn đề cần theo dõi.

**Cảnh báo:** không bật `org.springframework.security=TRACE` diện rộng lâu trên production; log có thể chứa thông tin URL, session, principal hoặc bị custom filters ghi raw credential. Không đưa bearer token, cookie hoặc password vào CI artifacts.

## 17. Các sai lầm phổ biến

1. **Tìm “Spring Security latest” rồi ghim version vào Boot app** thay vì xem Boot BOM.
2. **Dùng BOM trong `dependencies` như JAR runtime** thay vì dependencyManagement/platform.
3. **Tin mọi module đã đồng bộ vì starter không ghi version** nhưng một module khác override `spring-security-web`.
4. **Đọc migration guide cho một major không đi qua**, dẫn đến sửa code thừa hoặc sai.
5. **Nâng riêng `spring-security-config`** mà bỏ qua `core`, `web`, `test` và Framework.
6. **Dùng `javax` → `jakarta` tìm/thay toàn bộ** và vô tình sửa các packages Java SE không đổi.
7. **Chỉ sửa cho compile**, không test filter chain, 401/403, CSRF, authorization và sessions.
8. **Nhầm `securityMatcher` và `authorizeHttpRequests().requestMatchers`**, khiến endpoint vào chain sai.
9. **Để catch-all chain đứng trước API chain**, API authentication filter không được chọn.
10. **Bỏ qua container/JDK đang chạy thật**: build trên JDK mới nhưng deploy lên JVM cũ hoặc servlet container không tương thích.
11. **Import nhiều BOM/đặt version constraints chồng nhau** mà không dùng `dependencyInsight`/effective POM để xem kết quả.
12. **Dùng `enforcedPlatform` để ép toàn bộ dependency graph** trước khi hiểu nguyên nhân conflict.
13. **Lẫn test classpath với runtime**: `spring-security-test` có thể khác release line hoặc CI profile khác local.
14. **Disable CSRF hoặc nới permitAll để tests xanh**, bỏ qua vấn đề bảo mật thực.
15. **Cho rằng một smoke test 200 chứng minh migration an toàn**; cần negative tests và auth flows.
16. **Không chuẩn bị rollback**, đặc biệt khi có thay đổi session state, token persistence hoặc DB schema.

## 18. Checklist tự nghiệm thu

- [ ] Có bảng source/target cho **Java, Boot, Security, Framework, Servlet** và integrations.
- [ ] Đã đọc **đúng** Boot/Security/Framework migration guides cho từng bước nâng cấp.
- [ ] Boot app dùng Boot parent/BOM/plugin làm nguồn version management chính.
- [ ] Không pin các modules Spring Security riêng lẻ nếu không có lý do và support evidence.
- [ ] Maven effective POM hoặc Gradle dependencyInsight xác nhận resolved versions.
- [ ] `spring-security-test` cùng release line phù hợp runtime.
- [ ] Java toolchain, CI image, Servlet container/Jakarta dependencies tương thích.
- [ ] `SecurityFilterChain` beans có matcher/order đúng; không có endpoints nhạy cảm nằm ngoài chain.
- [ ] Method security, authentication providers, custom filters, logout và session lifecycle được test lại.
- [ ] CSRF còn được bảo vệ đúng theo cách browser gửi credential.
- [ ] JWT/OAuth login/Resource Server tests xác minh semantics thật, không chỉ mock Authentication.
- [ ] Có negative tests cho 401, 403, session, token sai và các URL patterns nhạy cảm.
- [ ] Đã chạy ứng dụng trên staging gần production, quan sát security logs/metrics an toàn.
- [ ] Có kế hoạch canary/rollback, đặc biệt cho migrations không dễ hoàn tác.
- [ ] PR/issue lưu version pair, dependency graph trước/sau và kết quả QA.

**Kết luận:** Trong Spring Security Servlet, nâng cấp đúng là một **quy trình kiểm soát cặp phiên bản**, không phải thay từng dependency ngẫu nhiên. Hãy **đọc migration guide chính xác nguồn→đích**, ưu tiên **Spring Boot BOM** khi dùng Boot, xem dependency tree/insight để xác nhận classpath, sau đó chứng minh bằng **HTTP security regression tests** rằng các chain, login, sessions, CSRF, JWT/OAuth và authorization không bị thay đổi trái ý muốn. BOM giải quyết version alignment; **nó không thay code migration hoặc kiểm thử bảo mật**.

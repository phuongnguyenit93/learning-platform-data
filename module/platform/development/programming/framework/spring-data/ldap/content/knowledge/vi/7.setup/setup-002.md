# Khai báo dependency bằng Gradle hoặc Maven

Để sử dụng **Spring Data LDAP** trong ứng dụng Java, trước hết cần khai báo đúng các thư viện tại hệ thống build. Việc chọn dependency quyết định dự án có thể sử dụng **LdapRepository** để thao tác với entry LDAP, **LdapTemplate** để xây dựng truy vấn chi tiết, cũng như có đầy đủ công cụ kiểm thử với một LDAP directory hay không.

Bài này hướng dẫn cấu hình **Maven** và **Gradle** trong chương trình học Spring Data LDAP, giải thích dependency nào cần thiết, cách quản lý phiên bản, phân biệt các lựa chọn thư viện và kiểm tra classpath trước khi viết CRUD, mapping DN/objectClass hoặc filter. Các ví dụ dùng **Spring Boot 4.2.0** và **Java 21** để có bộ cấu hình nhất quán. Khi làm việc với dự án đã tồn tại, hãy giữ phiên bản Spring Boot đã được dự án lựa chọn và sử dụng BOM tương ứng; không tự nâng cấp chỉ để sao chép ví dụ.

## 1. Spring Data LDAP cần những lớp thư viện nào?

Spring Data LDAP không phải LDAP server. Nó cung cấp các API Java để truy cập một directory LDAP, trong khi server như OpenLDAP hoặc Active Directory lưu dữ liệu, kiểm tra schema, objectClass và quyền truy cập.

~~~mermaid
flowchart TD
  A["Mã ứng dụng / service"] --> B["Spring Data LDAP: LdapRepository, mapping"]
  B --> C["Spring LDAP: LdapTemplate, ContextSource"]
  C --> D["JNDI / LDAP provider trong JDK"]
  D --> E[("LDAP server: DN, entry, schema, ACL")]
  F["spring-boot-starter-data-ldap"] -. "Gom thư viện và hỗ trợ cấu hình" .-> B
  F -.-> C
~~~

| Dependency / thành phần | Vai trò | Khi nào cần |
| --- | --- | --- |
| **org.springframework.boot:spring-boot-starter-data-ldap** | Starter Spring Boot cho Spring Data LDAP; kéo theo các thành phần phù hợp để dùng repository và tích hợp LDAP | **Lựa chọn mặc định** cho ứng dụng Spring Boot học mô hình repository |
| **org.springframework.data:spring-data-ldap** | Thư viện Spring Data LDAP: repository abstraction, hỗ trợ kết nối domain với entry | Khi tự cấu hình Spring Data LDAP không thông qua starter |
| **org.springframework.ldap:spring-ldap-core** | Spring LDAP: LdapTemplate, ContextSource, API truy vấn LDAP và các thao tác LDAP khác | Khi chỉ cần truy cập LDAP qua template, hoặc khi cấu hình không dùng starter |
| **java.naming** (JDK) | Chứa JNDI: DirContext, LdapContext, Name, LdapName | Là một phần của JDK; **không** thêm bằng Maven/Gradle |
| **org.springframework.boot:spring-boot-starter-data-ldap-test** | Hỗ trợ các thành phần kiểm thử Spring Data LDAP trong Spring Boot 4 | Dùng trong **test scope** khi kiểm thử repository/LDAP |
| **com.unboundid:unboundid-ldapsdk** | LDAP server nhúng in-memory phục vụ kiểm thử | Dùng trong **test scope**, tránh phụ thuộc máy chủ LDAP dùng chung |

**Quy tắc chọn thư viện:** Nếu mục tiêu là sử dụng **LdapRepository**, ưu tiên starter **spring-boot-starter-data-ldap**. Nếu chỉ dùng **LdapTemplate** thì có thể dùng **spring-boot-starter-ldap** của Spring Boot 4, hoặc khai báo **spring-ldap-core** theo mô hình cấu hình phù hợp. Nếu đã dùng starter data LDAP thì **không cần khai báo trùng** spring-data-ldap và spring-ldap-core chỉ để chúng có mặt trên classpath.

Spring Data LDAP khác với **Spring Data JPA**. LDAP lưu entry có DN phân cấp và objectClass theo schema; JPA làm việc với entity theo cơ sở dữ liệu quan hệ. Không cần thêm **spring-boot-starter-data-jpa** hay JDBC driver để truy vấn LDAP thuần túy.

## 2. Kiểm tra điều kiện trước khi khai báo dependency

Với ví dụ **Spring Boot 4.2.0**, môi trường build cần đáp ứng:

- **JDK 17 trở lên**; bài này dùng **JDK 21** thông qua Maven property hoặc Gradle toolchain.
- **Maven 3.6.3 trở lên** nếu chọn Maven.
- **Gradle 8.14 trở lên thuộc nhánh 8.x**, hoặc **Gradle 9.x** nếu chọn Gradle.
- Kết nối đến repository artifact, thường là **Maven Central**, để tải dependency.

Kiểm tra nhanh:

~~~bash
java -version
mvn -version
gradle --version
~~~

Thông thường, dự án đã có **Maven Wrapper** (\`mvnw\`, \`mvnw.cmd\`) hoặc **Gradle Wrapper** (\`gradlew\`, \`gradlew.bat\`). Hãy ưu tiên wrapper của repository để các máy phát triển dùng chung phiên bản công cụ. Ở Windows, sử dụng **mvnw.cmd** hoặc **gradlew.bat** tương ứng; các lệnh ví dụ bên dưới viết theo shell Unix.

Nếu hệ thống đang chạy **Spring Boot 3.x**, hãy chọn bộ phiên bản Java, Gradle/Maven, Spring Data tương thích với chính nhánh đó. Đừng ghép một starter Boot 4.x vào dự án Boot 3.x chỉ vì tọa độ Maven nhìn giống nhau.

## 3. Maven: ví dụ pom.xml đầy đủ

Trong dự án Maven dùng Spring Boot, **spring-boot-starter-parent** cung cấp cấu hình plugin và dependency management từ BOM Spring Boot. Khi đó các dependency do BOM quản lý có thể bỏ thẻ **version** riêng.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
            https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.2.0</version>
        <relativePath/>
    </parent>

    <groupId>org.example</groupId>
    <artifactId>ldap-learning</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>ldap-learning</name>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <!-- Spring Data LDAP repository + Spring LDAP integration -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-ldap</artifactId>
        </dependency>

        <!-- Bộ thư viện kiểm thử chung (JUnit Jupiter, AssertJ, Mockito...) -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>

        <!-- Hỗ trợ @DataLdapTest và cấu hình LDAP test của Spring Boot 4 -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-ldap-test</artifactId>
            <scope>test</scope>
        </dependency>

        <!-- LDAP server nhúng để kiểm thử tích hợp -->
        <dependency>
            <groupId>com.unboundid</groupId>
            <artifactId>unboundid-ldapsdk</artifactId>
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

### 3.1. Phân tích các phần quan trọng

| Thành phần POM | Công dụng |
| --- | --- |
| **parent: spring-boot-starter-parent** | Cung cấp dependency/plugin management và các mặc định build cho Spring Boot |
| **java.version** | Xác định phiên bản Java biên dịch dự án |
| **spring-boot-starter-data-ldap** | Là dependency chính để làm việc với repository LDAP |
| **spring-boot-starter-test** | Hỗ trợ unit test và những nhu cầu kiểm thử Spring Boot thông dụng |
| **spring-boot-starter-data-ldap-test** | Bổ sung bộ cấu hình và công cụ test liên quan đến Spring Data LDAP |
| **unboundid-ldapsdk** | Cung cấp LDAP server nhúng trong môi trường test |
| **spring-boot-maven-plugin** | Hỗ trợ tác vụ build/chạy ứng dụng Spring Boot; không phải LDAP driver |

Maven tự tải các **transitive dependencies** mà starter công bố. Ví dụ, các interface của Spring Data LDAP và API LdapTemplate đến từ các artifact khác nhau, nhưng thông thường chỉ cần khai báo một starter data LDAP ở cấp ứng dụng.

### 3.2. Trường hợp dự án có parent riêng

Một số doanh nghiệp sử dụng parent POM nội bộ nên không thể đổi parent thành **spring-boot-starter-parent**. Khi đó, có thể quản lý phiên bản qua BOM:

~~~xml
<properties>
    <spring-boot.version>4.2.0</spring-boot.version>
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
        <artifactId>spring-boot-starter-data-ldap</artifactId>
    </dependency>
</dependencies>
~~~

Đây là phần cấu hình **đưa vào POM hiện hữu**, không phải một file pom.xml độc lập. BOM quản lý **phiên bản dependency**, nhưng không thay thế toàn bộ cấu hình plugin/build defaults mà **spring-boot-starter-parent** cung cấp. Nếu không dùng parent của Boot, cần quản lý riêng phiên bản và cấu hình các Maven plugin cần thiết.

### 3.3. Kiểm tra dependency Maven

Từ thư mục chứa pom.xml:

~~~bash
./mvnw -q -DskipTests compile
./mvnw dependency:tree -Dincludes=org.springframework.boot,org.springframework.data,org.springframework.ldap,com.unboundid
./mvnw test
~~~

Trên Windows có thể dùng **mvnw.cmd**. Khi xem cây dependency, hãy xác nhận có starter **spring-boot-starter-data-ldap** và **spring-data-ldap**, **spring-ldap-core** được resolve theo cùng hệ quản lý phiên bản. **unboundid-ldapsdk** chỉ cần thiết ở classpath kiểm thử; không có lý do mang LDAP server nhúng vào runtime production.

## 4. Gradle Groovy DSL: build.gradle

Nếu dự án sử dụng **Gradle** với file **build.gradle**, có thể khai báo như sau:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.2.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'org.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-data-ldap'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-data-ldap-test'
    testImplementation 'com.unboundid:unboundid-ldapsdk'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**implementation** khai báo thư viện dùng bởi mã chính, **testImplementation** chỉ đưa thư viện vào classpath kiểm thử. Gradle plugin **io.spring.dependency-management** phối hợp với Spring Boot plugin để nhập BOM tương ứng, cho phép lược bỏ version ở các dependency được quản lý.

File **settings.gradle** có thể chứa:

~~~groovy
rootProject.name = 'ldap-learning'
~~~

Nếu dự án chỉ muốn sử dụng Gradle BOM support và không áp dụng plugin **io.spring.dependency-management**, cấu hình thay thế như sau:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.2.0'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    implementation 'org.springframework.boot:spring-boot-starter-data-ldap'

    testImplementation platform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-data-ldap-test'
    testImplementation 'com.unboundid:unboundid-ldapsdk'
}
~~~

Hai cách quản lý dependency là **hai lựa chọn độc lập**; không cần kết hợp cả hai trong cùng ví dụ. Với dự án có nhiều module, cần đưa BOM vào các module chứa dependency liên quan hoặc sử dụng cơ chế quản lý tập trung ở build chung.

## 5. Gradle Kotlin DSL: build.gradle.kts

Dự án Gradle Kotlin DSL dùng cú pháp với dấu ngoặc và chuỗi kiểu Kotlin:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "4.2.0"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "org.example"
version = "0.0.1-SNAPSHOT"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.boot:spring-boot-starter-data-ldap-test")
    testImplementation("com.unboundid:unboundid-ldapsdk")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Với **settings.gradle.kts**, khai báo:

~~~kotlin
rootProject.name = "ldap-learning"
~~~

Không trộn cú pháp Groovy của **build.gradle** (ví dụ \`implementation 'group:artifact'\`) vào **build.gradle.kts**, bởi Kotlin DSL yêu cầu cú pháp lời gọi hàm như \`implementation("group:artifact")\`.

### 5.1. Kiểm tra classpath Gradle

~~~bash
./gradlew compileJava
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-data-ldap --configuration runtimeClasspath
./gradlew test
~~~

Trên Windows dùng **gradlew.bat**. Lệnh **dependencyInsight** hữu ích khi một thư viện bị kéo về từ nhiều dependency và bạn muốn biết phiên bản nào được chọn, qua đường nào.

## 6. Giữa starter, core và security: chọn đúng dependency

Một lỗi phổ biến là thêm thư viện theo tên có chữ “LDAP” nhưng không khớp yêu cầu nghiệp vụ.

| Nhu cầu | Nên khai báo | Vì sao |
| --- | --- | --- |
| Repository và mapping entry bằng **@Entry**, **@Attribute**, **@Id** | **spring-boot-starter-data-ldap** | Cung cấp Spring Data LDAP cùng tầng kết nối phù hợp |
| Chỉ đọc/sửa thuộc tính bằng **LdapTemplate** trong Spring Boot 4 | **spring-boot-starter-ldap** | Phù hợp khi không sử dụng repository |
| Cấu hình Spring LDAP mà không dùng Spring Boot starter | **spring-ldap-core** và các thành phần cần thiết | Tự cấu hình ContextSource, LdapTemplate, dependency management |
| Xác thực tài khoản ứng dụng bằng LDAP qua Spring Security | **spring-security-ldap** và cấu hình Spring Security thích hợp | Đây là một bài toán xác thực/ủy quyền, không được starter Data LDAP tự động giải quyết |
| Test repository trên LDAP server nhúng | **spring-boot-starter-data-ldap-test** và **unboundid-ldapsdk** | Tạo môi trường tích hợp có directory, DN, schema, filter thực |
| Ánh xạ JPA entity vào database quan hệ | **spring-boot-starter-data-jpa** | Không thay thế Spring Data LDAP |

Trong Spring Boot 4.x, **spring-boot-starter-ldap** và **spring-boot-starter-data-ldap** là hai lựa chọn riêng. Đừng giả định starter chỉ chứa LDAP core có đầy đủ Spring Data repository. Đồng thời, **spring-security-ldap** không tự bật LDAP authentication nếu chưa cấu hình cơ chế bảo mật.

### 6.1. Ví dụ dependency Spring Security LDAP, khi thực sự cần

Ở Maven, thêm trong thẻ **dependencies** của POM đang được quản lý phiên bản Spring Boot:

~~~xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-ldap</artifactId>
</dependency>
~~~

Hoặc với Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.security:spring-security-ldap'
}
~~~

Tùy yêu cầu xác thực web và HTTP security, dự án có thể cần thêm starter Spring Security tương ứng. Chỉ thêm **spring-security-ldap** chưa tạo endpoint đăng nhập, chưa định nghĩa user search và chưa cấp bất kỳ quyền nào trong OpenLDAP.

## 7. Sau khi có dependency, Spring Boot tự cấu hình gì?

Khi starter Data LDAP có mặt trên classpath, Spring Boot có thể tự cấu hình **LdapContextSource**, **LdapTemplate** và phát hiện **LDAP repository** theo cơ chế auto-configuration và component scanning. Ứng dụng vẫn phải cung cấp **endpoint**, **base DN** và thông tin xác thực phù hợp với directory thật.

Ví dụ **src/main/resources/application.yml**:

~~~yaml
spring:
  ldap:
    urls: "ldaps://ldap.example.org:636"
    base: "dc=example,dc=org"
    username: "uid=reader,ou=services,dc=example,dc=org"
    password: "${LDAP_BIND_PASSWORD}"
~~~

Ở đây:

- **urls** xác định máy chủ LDAP và giao thức kết nối; với **ldaps://** phải có TLS hoạt động và trust material phù hợp.
- **base** là suffix/base DN để thư viện tính các DN tương đối. Ví dụ base ở **dc=example,dc=org** thì query tới nhân viên thường chỉ cần **ou=people**.
- **username** là DN của tài khoản dùng để **bind**, không phải user ID của người đang gọi API.
- **password** được lấy từ biến môi trường **LDAP_BIND_PASSWORD**, tránh ghi mật khẩu thật vào source control.

Cấu hình này chưa tự chứng minh kết nối LDAP thành công: cần LDAP server hoạt động, chứng chỉ được JVM tin cậy, tài khoản bind hợp lệ, entry đúng schema và đủ quyền ACL. **Đừng tắt xác minh chứng chỉ** khi thử kết nối LDAPS; hãy cấu hình CA/truststore hoặc SSL bundle phù hợp với phiên bản Boot và môi trường.

### 7.1. Kiểm tra nhanh các class có trên classpath

Sau khi biên dịch, các import dưới đây phải được IDE/JDK nhận diện:

~~~java
import javax.naming.Name; // JNDI có trong JDK
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.data.ldap.repository.LdapRepository;
~~~

**@Id** cho LDAP entry trong ví dụ này là **org.springframework.ldap.odm.annotations.Id**, không phải **org.springframework.data.annotation.Id** của một số module Spring Data khác. Đây là chi tiết dễ gây nhầm khi IDE tự gợi ý import.

Ví dụ entity thể hiện mục tiêu của dependency:

~~~java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"}
)
public class Person {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    // Constructors và getters/setters được lược bỏ.
}
~~~

~~~java
import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<Person> {
    Optional<Person> findByUid(String uid);
}
~~~

Với Spring Boot, repository được phát hiện qua package scanning mặc định nếu đặt đúng vị trí trong project. Có thể tùy chỉnh bằng **@EnableLdapRepositories** khi cần. Phần mã ở trên chỉ minh họa API do dependency cung cấp; để chạy truy vấn thật cần lớp chạy Spring Boot, directory có dữ liệu phù hợp và cấu hình kết nối.

## 8. Dependency cho kiểm thử tích hợp với LDAP directory

Kiểm thử LDAP không chỉ là thử logic Java. Một truy vấn hoặc lời gọi **save(...)** còn phụ thuộc vào cấu trúc DN, quy tắc schema, **objectClass**, LDAP filter và quyền ACL.

### 8.1. Vì sao phải có UnboundID trong test classpath?

Spring Boot hỗ trợ LDAP server nhúng **UnboundID**. Khi dependency này có mặt trong môi trường kiểm thử và cấu hình **spring.ldap.embedded.base-dn** phù hợp, bài kiểm thử có thể thực hiện thao tác trên một directory tạm thời, không cần dùng tài khoản LDAP thật.

Ví dụ **src/test/resources/application.yml**:

~~~yaml
spring:
  ldap:
    base: "dc=example,dc=org"
    embedded:
      base-dn: "dc=example,dc=org"
      ldif: "classpath:ldap-test.ldif"
~~~

Tạo **src/test/resources/ldap-test.ldif** trong dự án thực hành:

~~~ldif
dn: dc=example,dc=org
objectClass: top
objectClass: domain
dc: example

dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: uid=linh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@example.org
~~~

Khi khai báo **base-dn** trùng với suffix của data mẫu, hãy kiểm tra cơ chế khởi tạo của server nhúng tại phiên bản đang dùng: base entry có thể đã được tạo từ cấu hình; file LDIF cần điều chỉnh tránh **entryAlreadyExists** nếu môi trường đã sinh entry gốc. Mục tiêu là bảo đảm dữ liệu và base DN tương thích với cách UnboundID được Spring Boot khởi tạo.

Với Spring Boot 4.x, kiểm thử theo lát cắt dữ liệu dùng **@DataLdapTest** với import:

~~~java
import org.springframework.boot.data.ldap.test.autoconfigure.DataLdapTest;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.ldap.core.LdapTemplate;
import static org.assertj.core.api.Assertions.assertThat;

@DataLdapTest
class PersonDirectoryTest {
    @Autowired
    LdapTemplate ldapTemplate;

    @Test
    void contextHasLdapTemplate() {
        assertThat(ldapTemplate).isNotNull();
    }
}
~~~

Đây là phép kiểm tra **wiring/auto-configuration** tối thiểu; nó chưa chứng minh query và mapping đúng. Bài kiểm thử đầy đủ cần truy vấn entry đã nạp và xác nhận DN, thuộc tính, schema cùng hành vi ACL khi dùng server phù hợp. ACL của OpenLDAP và UnboundID không hoàn toàn giống nhau, nên các quy tắc ACL riêng của OpenLDAP cần được kiểm thử thêm bằng OpenLDAP thật (ví dụ qua Testcontainers hoặc môi trường kiểm thử độc lập).

**Lưu ý về phiên bản:** Trong Spring Boot 4, import của **@DataLdapTest** là **org.springframework.boot.data.ldap.test.autoconfigure.DataLdapTest** và module kiểm thử LDAP được tách riêng. Các hướng dẫn Spring Boot 3.x có thể dùng package/khai báo starter test khác; nên kiểm tra tài liệu đúng với phiên bản của dự án.

## 9. Quản lý phiên bản dependency để tránh xung đột

Vấn đề thường gặp không nằm ở cú pháp Maven/Gradle mà là việc trộn các nhánh thư viện:

- **BOM Spring Boot** chọn bộ phiên bản Spring Framework, Spring LDAP và Spring Data phù hợp để chạy chung.
- **Starter** kéo các thư viện cần thiết nhưng không thay thế việc quản lý BOM khi dự án tự xây build.
- **Transitive dependency** có thể kéo cùng một thư viện từ nhiều đường khác nhau; build tool phải chọn một phiên bản cuối cùng.
- **Override version** chỉ nên thực hiện sau khi có nhu cầu rõ ràng và kiểm tra tính tương thích, vì một module LDAP đời khác có thể không còn khớp API với Spring Data/Boot đang chạy.

Ví dụ cần tránh trong dự án Boot quản lý phiên bản:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-ldap'

    // Không thêm bản spring-ldap-core được chọn tùy ý để "sửa" lỗi build.
    // implementation 'org.springframework.ldap:spring-ldap-core:VERSION_BAT_KY'
}
~~~

Nếu phát hiện dependency conflict, đọc **mvn dependency:tree** hoặc **gradlew dependencyInsight** trước khi thay đổi BOM. Trong multi-module Maven, hãy chắc chắn module sử dụng LDAP kế thừa dependencyManagement từ parent đúng; trong Gradle, hãy xác nhận từng subproject áp dụng plugin/BOM thích hợp.

### 9.1. Dependency scope và khác biệt compile/test

| Maven | Gradle | Ý nghĩa |
| --- | --- | --- |
| **compile** (mặc định) | **implementation** | Dùng cho mã sản phẩm |
| **test** | **testImplementation** | Chỉ dùng trong kiểm thử |
| **runtime** | **runtimeOnly** | Có ở runtime nhưng không dùng trực tiếp khi biên dịch mã chính |

Trong lab, **unboundid-ldapsdk** thường đủ đặt ở **test**/**testImplementation**. Nếu code test trực tiếp import API UnboundID thì testImplementation là lựa chọn hợp lý; nếu chỉ cần server được auto-configure thông qua classpath và không import thư viện, có thể cân nhắc **testRuntimeOnly**.

## 10. Lỗi cài đặt thường gặp và cách xác minh

| Triệu chứng | Nguyên nhân hay gặp | Hướng kiểm tra |
| --- | --- | --- |
| **Could not find spring-boot-starter-data-ldap** | Sai tọa độ, repository Maven Central không truy cập được hoặc BOM/repository cấu hình sai | Xác nhận **org.springframework.boot:spring-boot-starter-data-ldap** và repository |
| **package org.springframework.data.ldap.repository does not exist** | Thiếu starter data LDAP, chỉ khai báo spring-ldap-core | Kiểm tra dependency cây build và import repository |
| **package org.springframework.ldap.core does not exist** | Thiếu Spring LDAP hoặc dependency chưa tải thành công | Xem runtime/compile classpath |
| **NoClassDefFoundError / NoSuchMethodError** | Trộn phiên bản Spring Framework, Spring LDAP, Spring Data hoặc plugin | Kiểm tra BOM và dependency conflict |
| **No qualifying bean of type LdapTemplate** | Thiếu auto-configuration, tắt cấu hình tự động hoặc tự tạo bean không đầy đủ | Kiểm tra starter, điều kiện auto-config và ContextSource |
| **No bean for PersonRepository** | Repository scan chưa bao gồm package hoặc chưa bật repository support | Kiểm tra package chính, @EnableLdapRepositories |
| **Could not resolve dependency** | Lỗi mạng, proxy, DNS, repository, SSL artifact registry | Kiểm tra kết nối và cấu hình repository/proxy |
| **LDAP connection refused / CommunicationException** | Build đã đúng nhưng LDAP server không chạy/sai endpoint | Kiểm tra spring.ldap.urls, host, cổng, TLS |
| **Invalid credentials / Insufficient access** | Bind DN/mật khẩu sai hoặc ACL không đủ | Kiểm tra tài khoản bind và quyền phía LDAP server |
| **Schema violation khi save** | Entry thiếu thuộc tính bắt buộc hoặc objectClass không phù hợp | Kiểm tra DN, cn/sn, schema của directory |

**Phân biệt hai loại lỗi:** lỗi “cannot resolve artifact/import” xuất hiện ở **build/classpath**; lỗi “invalid credentials/schema violation” xuất hiện khi ứng dụng thực sự giao tiếp với **LDAP server**. Việc thêm dependency khác không tự sửa ACL, DN hay schema phía server.

### Quy trình xác minh sau khi cấu hình

1. Chạy **compile** để xác nhận thư viện tải được và IDE resolve các import.
2. Xem dependency tree để kiểm tra **spring-data-ldap**, **spring-ldap-core** và hệ BOM được chọn.
3. Chạy test tối thiểu với **@DataLdapTest** nếu cần tích hợp LDAP nhúng.
4. Kiểm tra truy vấn thực với entry giả có đủ **DN**, **objectClass**, **cn**, **sn** và quyền đọc.
5. Chỉ khi build/classpath đã ổn mới đi sâu vào chẩn đoán kết nối LDAPS, LDAP filter, ACL và lỗi schema.

## 11. Ghi nhớ và câu hỏi tự kiểm tra

**Ghi nhớ:** Trong Spring Boot, cách phổ biến nhất để học **Spring Data LDAP repository** là khai báo **spring-boot-starter-data-ldap** với dependency management phù hợp. Maven thường dùng parent/BOM, Gradle dùng plugin dependency management hoặc native BOM. Thư viện test LDAP và server nhúng đặt ở **test scope**. Các dependency chỉ cung cấp API và auto-configuration; khi truy cập directory thật, vẫn cần cấu hình đúng DN, objectClass, schema, filter, endpoint, TLS và quyền bind.

Tự trả lời những câu hỏi sau:

1. Tại sao **spring-boot-starter-data-ldap** phù hợp hơn **spring-ldap-core** nếu ứng dụng cần **LdapRepository**?
2. BOM của Spring Boot mang lại lợi ích gì khi dự án có nhiều thư viện Spring?
3. **testImplementation** khác **implementation** ở điểm nào? Tại sao UnboundID thường không nên đưa vào runtime production?
4. Vì sao build thành công không đảm bảo **findByUid(...)** trả được dữ liệu LDAP?
5. Khi gặp **NoSuchMethodError**, bạn sẽ kiểm tra dependency tree như thế nào trước khi sửa source code?
6. Có cần thêm **spring-data-jpa** hoặc **spring-security-ldap** chỉ để sử dụng LDAP repository hay không?

## Tài liệu tham khảo chính thức

- [Spring Boot — LDAP và embedded LDAP](https://docs.spring.io/spring-boot/reference/data/nosql.html#data.nosql.ldap)
- [Spring Boot — Quản lý dependency bằng Gradle](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html)
- [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
- [Spring Data LDAP — Reference](https://docs.spring.io/spring-data/ldap/reference/)
- [Spring LDAP — Getting Spring LDAP](https://docs.spring.io/spring-ldap/reference/getting-spring-ldap.html)

Các ví dụ được chốt phiên bản để dễ tái hiện khi học; khi bắt đầu dự án mới, hãy kiểm tra phiên bản GA, yêu cầu Java/build tool và tài liệu tương ứng tại trang chính thức trước khi cập nhật.

# Nâng cấp Spring Data LDAP, Spring LDAP và JDK

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Lập ma trận tương thích giữa JDK, Spring Boot, Spring Framework, Spring Data LDAP và Spring LDAP trước khi đổi dependency.
2. Phân biệt vai trò của Spring Data LDAP repository, Spring LDAP core/ODM và JDK JNDI để biết thành phần nào thực sự cần nâng cấp.
3. Dùng Spring Boot BOM hoặc các BOM phù hợp để quản lý phiên bản, tránh ghép thủ công những module Spring không cùng thế hệ.
4. Chọn JDK mục tiêu phù hợp, đồng bộ JDK dùng build, JDK dùng chạy ứng dụng và toolchain trên CI/CD.
5. Nhận diện thay đổi API, validation và hành vi khi nâng Spring LDAP, gồm AttributeSchema, LdapQueryBuilder, DirContextAdapter và ODM.
6. Xử lý advisory bảo mật liên quan đến empty-password bind, LDAP test server và filter builder trước khi phát hành.
7. Nâng cấp cấu hình TLS/LDAPS, kiểm thử repository, LdapTemplate, LdapClient, schema, ACL, filter và xác thực trên directory thử nghiệm.
8. Triển khai theo từng giai đoạn, quan sát lỗi và chuẩn bị rollback khi phiên bản mới không tương thích với LDAP server thực tế.

Bài thuộc chương **Triển khai** của module `SPRING_DATA_LDAP`. Module giúp ứng dụng Java truy cập dịch vụ thư mục LDAP qua Spring Data LDAP repository, ánh xạ entry phân cấp sang object Java, sử dụng DN, `objectClass`, schema, truy vấn repository/`LdapTemplate`, CRUD, filter an toàn, kết nối bảo mật và kiểm thử với directory. Nâng cấp thư viện cần bảo toàn các hợp đồng đó trong môi trường build, runtime và LDAP server.

## 1. Hiểu đúng các thành phần cần nâng cấp

Một ứng dụng Spring Data LDAP thường có nhiều lớp phiên bản:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| JDK | Runtime, compiler, JNDI và TLS provider | JDK 17, 21, 25 |
| Spring Boot | Auto-configuration, starter, dependency management | `spring-boot-starter-data-ldap` |
| Spring Framework | Container và core utilities | `spring-context`, `spring-core` |
| Spring Data Commons | Hạ tầng repository dùng chung | `spring-data-commons` |
| Spring Data LDAP | Repository và tích hợp Spring Data với LDAP | `spring-data-ldap` |
| Spring LDAP | `ContextSource`, `LdapTemplate`, `LdapClient`, ODM và utilities | `spring-ldap-core`, `spring-ldap-odm` |
| LDAP server | Dữ liệu, schema, ACL, TLS và referral | OpenLDAP, Active Directory hoặc directory khác |

Các thành phần này **không có cùng lịch phát hành hoặc cùng số phiên bản**. Spring Data LDAP 4.2.0 và Spring LDAP 4.2.0 có cùng số phiên bản trong release train tham khảo hiện tại, nhưng không nên suy ra các thế hệ luôn phải trùng số. Hãy dựa vào **BOM và ma trận tương thích chính thức**.

### 1.1. Spring Data LDAP và Spring LDAP giải quyết hai lớp khác nhau

- **Spring Data LDAP** cung cấp repository abstraction, ODM integration và cách khai báo truy vấn theo mô hình Spring Data.
- **Spring LDAP** cung cấp API làm việc trực tiếp với directory như `ContextSource`, `LdapTemplate`, `LdapClient`, `LdapQueryBuilder` và `LdapNameBuilder`.
- **JDK JNDI** cung cấp API nền như `javax.naming.Name`, `DirContext`, `Attributes`, `ModificationItem` và LDAP provider.

Ví dụ repository thuộc Spring Data LDAP:

```java
public interface PersonRepository
        extends LdapRepository<PersonEntry> {
    List<PersonEntry> findByLoginId(String loginId);
}
```

Nếu service gọi:

```java
ldapTemplate.search(query, mapper);
```

thì thao tác trực tiếp thuộc Spring LDAP. Cả hai đều phụ thuộc Spring Framework, JDK và cùng cấu hình directory.

**Nâng cấp riêng một JAR có thể không đủ.** Ví dụ đổi `spring-data-ldap` lên phiên bản mới nhưng giữ `spring-data-commons` quá cũ có thể tạo lỗi `NoSuchMethodError`, `NoClassDefFoundError` hoặc lỗi khởi tạo repository.

### 1.2. Xác định đúng dependency theo nhu cầu

Nếu dùng repository Spring Data LDAP, starter của Spring Boot thường là cách đơn giản:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-ldap</artifactId>
</dependency>
```

Không cần thêm một phiên bản riêng cho từng module Spring Data/Spring LDAP nếu Boot BOM đã quản lý chúng.

Nếu ứng dụng chỉ dùng Spring LDAP core mà không dùng repository, có thể chỉ cần `spring-ldap-core` hoặc starter LDAP tương ứng với phiên bản Spring Boot. Nếu dùng tính năng bổ sung như LDIF, ODM hoặc LDAP test, hãy khai báo module cần thiết theo tài liệu đúng phiên bản.

## 2. Ma trận tương thích tham khảo tại ngày 26-11-2026

Các phiên bản dưới đây là **mốc stable được tài liệu Spring công bố tại thời điểm biên soạn**, dùng để minh họa một đích nâng cấp đồng bộ:

| Thành phần | Mốc tham khảo | Ghi chú |
| --- | --- | --- |
| Spring Boot | **4.2.0** | GA ngày 19-11-2026 |
| Java | **17 trở lên** | Boot 4.2 hỗ trợ đến Java 27 |
| Spring Framework | **7.1.0 trở lên** | Boot 4.2 quản lý phiên bản phù hợp |
| Spring Data Release Train | **2026.1.0** | BOM quản lý các module Spring Data tương thích |
| Spring Data LDAP | **4.2.0** | Phiên bản trong train 2026.1.0 |
| Spring LDAP | **4.2.0** | Stable hiện hành trong tài liệu Spring LDAP |
| Maven | **3.6.3 trở lên** | Boot 4.2 hỗ trợ |
| Gradle | **8.14 trở lên trong nhánh 8.x, hoặc 9.x** | Đối chiếu plugin và wrapper của dự án |

Đây là **một cấu hình tham chiếu**, không phải yêu cầu mọi ứng dụng phải nâng lên Boot 4.2 ngay lập tức. Nếu dự án còn ở Boot 3.x, hãy dùng dependency management của chính dòng Boot đó và kiểm tra các phiên bản Spring Data/Spring LDAP mà BOM đang quản lý.

Nguồn chính thức:

- Spring Boot 4.2.0 System Requirements: Java 17+, Spring Framework 7.1+, Maven/Gradle baseline.
- Spring Data Release Train 2026.1.0: Spring Data LDAP 4.2.0.
- Spring Boot managed dependency coordinates: các artifact `spring-data-ldap`, `spring-ldap-core`, `spring-ldap-odm` và `spring-ldap-test`.

### 2.1. Chọn JDK LTS thay vì chỉ chọn JDK mới nhất

Spring Boot 4.2.0 hỗ trợ một dải JDK rộng, nhưng môi trường production cần tính đến **thời hạn hỗ trợ, bản cập nhật bảo mật, image container và nhà cung cấp JDK**.

Tại thời điểm bài học:

- **Java 17** là mức tối thiểu Spring Boot 4.2 yêu cầu.
- **Java 21** là một lựa chọn LTS đã được sử dụng rộng rãi.
- **Java 25** là LTS mới hơn, phù hợp khi thư viện, build plugin, container base image và tổ chức đã kiểm chứng.
- Java 26/27 là các bản feature release; không nên chọn chỉ vì số phiên bản cao hơn nếu tổ chức cần chu kỳ hỗ trợ dài.

Java 25 là LTS theo roadmap của Oracle. Lịch hỗ trợ và điều khoản cập nhật khác nhau theo nhà phân phối JDK; hãy kiểm tra chính sách của nhà cung cấp mà hệ thống đang sử dụng.

### 2.2. Không ghép phiên bản theo cảm tính

Ví dụ **không nên** tự ghép:

```text
Spring Boot:       4.2.0
Spring Framework:  6.2.x
Spring Data LDAP:  4.2.0
Spring LDAP:       3.3.x
JDK:               17
```

Bộ phiên bản trên có thể vi phạm quan hệ tương thích, dù từng artifact đều tải được từ Maven Central. Lỗi thường chỉ xuất hiện khi Spring khởi tạo repository, inject bean hoặc gọi method có chữ ký thay đổi.

Hãy chọn **một BOM làm nguồn quản lý chính**, sau đó kiểm tra dependency tree để biết phiên bản thực tế mà build đã giải quyết.

## 3. Kiểm kê hệ thống trước khi nâng cấp

Không bắt đầu bằng việc thay số phiên bản trong `pom.xml` hoặc `build.gradle`. Trước tiên cần biết ứng dụng đang dùng thành phần nào và hợp đồng LDAP nào đang phụ thuộc vào chúng.

### 3.1. Ghi lại JDK và build tool

Chạy tại máy build/CI và môi trường runtime:

```bash
java -version
javac -version
mvn -v
./gradlew --version
```

Trên Windows có thể dùng `gradlew.bat --version`.

Ghi nhận:

- JDK thực tế mà Maven/Gradle sử dụng.
- JDK trong container chạy production.
- `JAVA_HOME` của CI runner và máy developer.
- Phiên bản Maven/Gradle wrapper.
- Compiler release/target hiện tại.
- Có dùng `jlink`, custom runtime image, GraalVM native image hay không.

**JDK chạy lệnh java không nhất thiết là JDK mà build tool đang dùng.** Maven Toolchains hoặc Gradle Java Toolchains có thể chọn một JDK khác.

### 3.2. Kiểm tra dependency tree

Maven:

```bash
mvn help:effective-pom

mvn dependency:tree \
  -Dincludes=org.springframework.data:*,org.springframework.ldap:*,org.springframework:spring-*
```

Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency spring-data-ldap \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency spring-ldap-core \
  --configuration runtimeClasspath
```

Đối chiếu:

- Có nhiều phiên bản `spring-data-commons` cùng lúc không?
- `spring-data-ldap` có được BOM quản lý không?
- `spring-ldap-core` và `spring-ldap-odm` có lệch thế hệ không?
- Có dependency bị override qua `resolutionStrategy`, Maven property hoặc dependency management khác không?
- Có JAR Spring cũ bị đóng gói trực tiếp trong thư mục `lib/` của ứng dụng không?

### 3.3. Lập danh sách API và hành vi LDAP đang sử dụng

| Khu vực | Ví dụ cần rà soát |
| --- | --- |
| Repository | `LdapRepository`, `@EnableLdapRepositories`, derived query, `@Query` |
| ODM | `@Entry`, `@Id`, `@Attribute`, `@DnAttribute`, custom converter |
| Query | `LdapQueryBuilder`, `LdapQuery`, `SearchScope`, `fromQuery(...)` |
| Core API | `LdapTemplate`, `LdapClient`, `ContextSource` |
| Authentication | `authenticate`, `DirContextAuthenticationStrategy`, empty/null password |
| Writes | `bind`, `rebind`, `unbind`, `modifyAttributes`, `rename` |
| Connection | Pooling, referral, timeout, LDAPS, StartTLS |
| Testing | `spring-ldap-test`, `EmbeddedLdapServer`, UnboundID, LDIF fixtures |
| Schema | Custom attribute name, custom `objectClass`, multi-valued attribute |

Ngoài code, ghi lại **hành vi server** đang phụ thuộc:

- DN base và search scope.
- Schema/`objectClass` và attribute bắt buộc.
- ACL theo bind identity.
- Matching rule của DN, `member`, `uniqueMember` và `uid`.
- Referral, paging, size/time limit.
- Cơ chế nhóm `member`/`memberOf`.
- Certificate chain, hostname và truststore.
- Replica topology và read-after-write behavior.

Một thư viện mới không tự sửa schema, ACL hay dữ liệu LDAP hiện tại. Nếu server không cho phép đọc `member`, nâng cấp Spring LDAP không thể biến quyền đó thành quyền hợp lệ.

### 3.4. Lưu trạng thái có thể so sánh trước và sau

Trước khi đổi dependency, nên lưu:

1. Effective POM hoặc dependency graph.
2. Kết quả test hiện tại.
3. Một bộ LDIF fixture đại diện.
4. Kết quả các truy vấn quan trọng (DN, `objectClass`, attribute cần đọc).
5. Thời gian kết nối/bind/search ở môi trường test.
6. Danh sách cấu hình TLS, referral và timeout đã được phê duyệt.

Không đưa password, token, dữ liệu cá nhân hoặc LDIF production chưa được làm sạch vào artifact kiểm thử.

## 4. Quản lý phiên bản bằng BOM

### 4.1. Dự án Spring Boot dùng Maven

Với Spring Boot 4.2.0, có thể dùng parent để nhận dependency management của Boot:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.2.0</version>
    <relativePath/>
</parent>

<properties>
    <java.version>21</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-ldap</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Ví dụ chọn Java 21 để minh họa một JDK LTS. Nếu tổ chức chọn Java 25, thay `java.version` và toolchain tương ứng sau khi kiểm tra toàn bộ plugin/dependency.

**Không khai báo version riêng** cho `spring-data-ldap`, `spring-data-commons` hoặc `spring-ldap-core` nếu Boot BOM đã quản lý chúng. Nếu có lý do override, phải kiểm tra tương thích và security advisory của đúng dòng đó.

Nếu không dùng `spring-boot-starter-parent`, có thể import `spring-boot-dependencies` BOM vào `dependencyManagement`, giữ cùng nguyên tắc không tự pin các artifact mà BOM đã quản lý.

### 4.2. Dự án Spring Boot dùng Gradle

Ví dụ Groovy DSL:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.2.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-ldap'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Boot plugin và dependency management plugin sẽ quản lý phiên bản phù hợp. Nếu dùng Gradle Kotlin DSL, cú pháp plugin/dependency khác nhưng nguyên tắc BOM và toolchain vẫn giống nhau.

### 4.3. Dự án không dùng Spring Boot

Nếu ứng dụng dùng Spring Framework và Spring LDAP độc lập:

- Dùng **Spring Data BOM** để quản lý các module Spring Data, bao gồm Spring Data LDAP.
- Dùng **Spring Framework BOM** để giữ `spring-core`, `spring-context`, `spring-beans` và các module Framework cùng thế hệ.
- Khai báo phiên bản Spring LDAP theo ma trận tương thích của release tương ứng.
- Không tự chọn `spring-data-ldap` mới rồi giữ `spring-data-commons` cũ.

Ví dụ dependency management Maven:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.data</groupId>
            <artifactId>spring-data-bom</artifactId>
            <version>2026.1.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>

        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-framework-bom</artifactId>
            <version>7.1.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.data</groupId>
        <artifactId>spring-data-ldap</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.ldap</groupId>
        <artifactId>spring-ldap-core</artifactId>
        <version>4.2.0</version>
    </dependency>
</dependencies>
```

Đây là ví dụ quản lý phiên bản ở một đích tham khảo cụ thể. Dự án độc lập cần kiểm tra **Spring Framework baseline** của release Spring Data/Spring LDAP đã chọn trước khi sử dụng cấu hình này.

## 5. Nâng cấp JDK đồng bộ giữa build và runtime

### 5.1. Phân biệt JDK build và JDK runtime

Một ứng dụng có thể được compile bằng JDK 25 nhưng chạy trên runtime image JDK 17 nếu bytecode/API mục tiêu vẫn tương thích. Ngược lại, build thành công bằng JDK mới **không bảo đảm** runtime image cũ có đủ module, provider hoặc TLS behavior.

Kiểm tra cả ba lớp:

| Lớp | Câu hỏi |
| --- | --- |
| Compiler | Source/bytecode target là phiên bản Java nào? |
| Build tool | Maven/Gradle đang chạy bằng JDK nào? |
| Runtime | Container/VM production dùng JRE/JDK nào? |

Với Spring Boot 4.2, Java 17 là baseline. Khi chọn 21 hoặc 25, hãy kiểm tra vendor support, container image, agent giám sát, thư viện LDAP bên ngoài và policy của tổ chức.

### 5.2. Cấu hình Maven compiler release

Nếu dự án không dùng Boot parent, có thể đặt:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

`--release` giới hạn API Java mà compiler cho phép dùng theo release mục tiêu. Nó hữu ích hơn việc chỉ đặt `source` và `target`, nhưng **không thay thế** việc kiểm thử trên đúng runtime.

### 5.3. Cấu hình Gradle Java Toolchain

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Toolchain giúp build nhất quán trên máy developer và CI. Cần xác minh runner có thể tải hoặc đã cài đúng JDK, và container production cũng chạy đúng phiên bản dự kiến.

### 5.4. JNDI vẫn dùng namespace javax.naming

Spring LDAP sử dụng JNDI của JDK, ví dụ:

```java
import javax.naming.Name;
import javax.naming.directory.DirContext;
import javax.naming.directory.Attributes;
import javax.naming.ldap.LdapName;
```

Không đổi những import này thành namespace `jakarta.naming` chỉ vì dự án nâng Spring Framework hoặc Spring Boot. JNDI thuộc Java SE, không phải một API Servlet/JPA được chuyển namespace theo cách tương tự.

Nếu dùng `module-info.java`, kiểm tra module `java.naming`; nếu tạo runtime image tối giản bằng `jlink`, kiểm tra thêm LDAP provider module `jdk.naming.ldap` và các module TLS/crypto cần thiết. Không loại bỏ module chỉ vì ứng dụng compile thành công trên JDK đầy đủ.

## 6. Những thay đổi Spring LDAP cần rà soát

Đọc tài liệu **What's New**, release notes và upgrade notes của tất cả phiên bản bị bỏ qua. Nếu nâng qua nhiều thế hệ, không chỉ đọc release note của bản đích.

### 6.1. Validation của AttributeSchema trong Spring LDAP 4.2

Spring LDAP 4.2 bổ sung validation cho `AttributeSchema`: tên LDAP attribute phải chuyển đổi được thành một **Java identifier hợp lệ** trong ngữ cảnh schema API.

Điều này cần được kiểm tra nếu ứng dụng:

- Khai báo custom attribute schema.
- Dùng tên attribute tùy biến có dấu gạch ngang, dấu chấm hoặc ký tự không phù hợp với quy tắc Java identifier.
- Dùng ODM/converter dựa vào metadata attribute.
- Tạo schema metadata động từ tên attribute lấy trong cấu hình.

Không tự đổi tên attribute trong LDAP production chỉ để làm code mới chạy. Hãy xác định API đang validate tên nào, kiểm thử custom mapping, dùng ánh xạ tường minh phù hợp hoặc truy cập bằng `LdapTemplate` khi schema metadata không phù hợp.

### 6.2. DirContextAdapter và thao tác với giá trị nhiều trị

Spring LDAP 4.2 bổ sung khả năng tùy chỉnh việc `DirContextAdapter` loại bỏ giá trị:

- Có trường hợp adapter có thể **remove từng giá trị** của một attribute nhiều trị.
- Có trường hợp cần **replace toàn bộ attribute** theo matching/schema semantics.
- `setMayRemoveByValue` cho phép kiểm soát hành vi theo attribute.

Nếu ứng dụng cập nhật `member`, `mail`, `telephoneNumber` hoặc attribute nhiều giá trị khác, hãy kiểm thử:

1. Thêm một giá trị có giữ nguyên các giá trị còn lại không?
2. Xóa một giá trị có vô tình replace toàn bộ attribute không?
3. Attribute có equality matching rule phù hợp để remove-by-value không?
4. Khi hai client cập nhật đồng thời, có bị lost update không?
5. `groupOfNames.member` có còn ít nhất một giá trị theo schema không?

Không mặc định đổi collection trong Java rồi gọi update sẽ có semantics giống nhau trên mọi phiên bản.

### 6.3. LdapClient có thêm điểm mở rộng post-processing

Spring LDAP 4.2 bổ sung `LdapClient.Builder#dirContextPostProcessor` để tùy chỉnh quá trình post-processing `DirContextAdapter`.

Nếu ứng dụng dùng `LdapClient`, hãy đọc release notes và kiểm tra custom post-processor, converter, mapping hoặc logic context adapter hiện tại. Đây là khả năng mở rộng mới; không cần thêm code chỉ để nâng cấp nếu ứng dụng không có nhu cầu.

### 6.4. Kiểm tra ODM và repository

Với entity:

```java
@Entry(
    base = "ou=people",
    objectClasses = {
        "top", "person", "organizationalPerson", "inetOrgPerson"
    }
)
public class PersonEntry {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String loginId;

    @Attribute(name = "cn")
    private String commonName;
}
```

Hãy xác minh:

- `@Id Name dn` vẫn được populate đúng, nhất là DN tương đối/đầy đủ theo base.
- `@Entry.base` và `ContextSource.base` không bị cộng hai lần.
- Attribute có tên khác property Java vẫn được ánh xạ đúng.
- Multi-valued attribute có converter phù hợp.
- Custom `ContextMapper`/`AttributesMapper` không phụ thuộc implementation detail.
- Repository derived query vẫn tạo filter đúng.
- Query custom không làm mất filter điều kiện bắt buộc.
- Rename/move không làm cache hoặc object đã load giữ DN cũ.

Không dùng một test repository đơn giản để kết luận tất cả thao tác ODM đã tương thích. Cần kiểm tra cả read, create, modify, rename và delete theo schema thực.

## 7. Security advisory cần xử lý trong quá trình nâng cấp

Nâng cấp thư viện LDAP cần đối chiếu advisory bảo mật của **đúng artifact và đúng nhánh phiên bản**. Ba advisory dưới đây đặc biệt liên quan đến Spring LDAP.

### 7.1. CVE-2026-41720: xác thực có thể bị bypass bằng mật khẩu rỗng

Spring LDAP trong các phiên bản bị ảnh hưởng không từ chối bind có username/DN không rỗng nhưng password rỗng hoặc null. Theo RFC 4513, đây là **unauthenticated simple bind**; server cho phép kiểu bind này có thể trả thành công nhưng trạng thái authorization là anonymous.

| Nhánh bị ảnh hưởng theo advisory | Phiên bản sửa |
| --- | --- |
| Spring LDAP 4.0.0–4.0.3 | 4.0.4 trở lên trong nhánh được sửa |
| Spring LDAP 3.3.0–3.3.7 | 3.3.8 trở lên trong nhánh được sửa |
| Spring LDAP 3.2.0–3.2.17 | 3.2.18 (Enterprise Support) |
| Spring LDAP 2.4.4 trở xuống | 2.4.5 (Enterprise Support) |
| Dòng 4.1 | Bản 4.1.0 đã có thay đổi khắc phục theo công bố phát hành |

Dù dùng phiên bản đã sửa, ứng dụng vẫn nên **từ chối password null/rỗng trước khi gọi authenticate hoặc bind**:

```java
public boolean authenticate(String loginId, String password) {
    if (loginId == null || loginId.isBlank()
            || password == null || password.isEmpty()) {
        return false;
    }

    return ldapTemplate.authenticate(
        query()
            .base("ou=people")
            .where("uid").is(loginId),
        password
    );
}
```

Kiểm thử ít nhất ba trường hợp: password đúng, password sai và password rỗng/null. Không chỉ mock phương thức; cần kiểm thử với LDAP server test để xác minh semantics bind.

### 7.2. CVE-2026-59367: embedded test LDAP server mở trên mọi network interface

Advisory này ảnh hưởng artifact **`spring-ldap-test`**. `EmbeddedLdapServer` trong các phiên bản bị ảnh hưởng lắng nghe trên mọi network interface và dùng credential quản trị cố định được biết công khai. Người có thể kết nối đến cổng đó có thể đọc, thêm, sửa hoặc xóa entry trong directory test.

Các phiên bản bị ảnh hưởng được Spring công bố gồm:

- Spring LDAP 4.1.0–4.1.2.
- Spring LDAP 4.0.0–4.0.6.
- Spring LDAP 3.3.0–3.3.9.
- Spring LDAP 3.2.0–3.2.19.
- Spring LDAP 2.4.6 và các bản cũ hơn.

Các bản sửa tương ứng:

| Nhánh | Phiên bản sửa |
| --- | --- |
| 4.1.x | 4.1.3 |
| 4.0.x | 4.0.7 |
| 3.3.x | 3.3.10 |
| 3.2.x | 3.2.20 (Enterprise Support) |
| 2.4.x | 2.4.7 (Enterprise Support) |

Đây là rủi ro của **test fixture**, không phải khẳng định mọi kết nối tới LDAP server production đều bị ảnh hưởng. Tuy nhiên, test server trên shared CI runner, container có published port hoặc mạng development dùng chung có thể bị truy cập ngoài ý muốn.

Khi nâng cấp:

1. Kiểm tra version của `spring-ldap-test` trong **testRuntimeClasspath**, không chỉ runtime.
2. Nâng lên bản đã sửa của nhánh đang dùng hoặc một nhánh stable mới hơn.
3. Không expose port LDAP test ra mạng không tin cậy.
4. Dùng network isolation và dữ liệu giả cho fixture.
5. Không sử dụng embedded test server như directory production.

### 7.3. CVE-2026-59368: LdapQueryBuilder có thể bỏ filter cũ

Trong các phiên bản bị ảnh hưởng, khi tạo builder từ một `LdapQuery` bằng `fromQuery(...)` rồi chỉ định filter mới, filter ban đầu có thể bị **loại bỏ âm thầm**. Điều này có thể làm truy vấn rộng hơn dự kiến và bỏ qua một điều kiện lọc quan trọng.

Các nhánh bị ảnh hưởng và bản sửa:

| Nhánh | Phiên bản sửa |
| --- | --- |
| 4.1.x | 4.1.3 |
| 4.0.x | 4.0.7 |
| 3.3.x | 3.3.10 |
| 3.2.x | 3.2.20 |

Trong các bản sửa, việc thêm filter mới lên builder tạo bằng `fromQuery(LdapQuery)` sẽ bị từ chối bằng `IllegalStateException` thay vì âm thầm thay filter. API `fromQuery(...)` cũng được deprecate để chuyển sang `withQuery(...)`.

Ví dụ, khi muốn tạo query mới từ các thuộc tính query cũ nhưng **đặt một filter mới**, hãy dùng API mới và viết rõ filter cuối cùng:

```java
LdapQuery baseQuery = query()
    .base("ou=people")
    .searchScope(SearchScope.SUBTREE)
    .attributes("uid", "cn")
    .where("objectClass").is("inetOrgPerson")
    .build();

LdapQuery byEmail = LdapQueryBuilder
    .withQuery(baseQuery)
    .filter(
        "(&(objectClass=inetOrgPerson)(mail={0}))",
        email
    )
    .build();
```

`withQuery(...)` sao chép các thành phần của query nguồn **ngoại trừ filter**. Vì vậy ví dụ trên chủ động đưa điều kiện `objectClass` trở lại filter mới. Nếu mục tiêu là giữ nguyên filter nguồn và thêm điều kiện, hãy kết hợp filter cũ một cách tường minh thay vì giả định builder tự giữ lại nó.

**Việc cần làm khi nâng cấp:** tìm mọi chỗ gọi `LdapQueryBuilder.fromQuery(...)`, đọc lại filter cuối cùng và thêm test khẳng định điều kiện tenant/OU/objectClass/authorization không bị bỏ.

### 7.4. Ma trận bảo mật khi đánh giá version

Tại thời điểm bài học, Spring LDAP 4.2.0 là stable hiện hành và nằm ngoài các dải phiên bản bị ảnh hưởng nêu trong ba advisory trên. Nếu phải duy trì nhánh cũ, không chỉ so sánh version số lớn/nhỏ; cần dùng **bản sửa tương ứng của chính nhánh đó** hoặc kế hoạch nâng cấp có hỗ trợ.

Đừng dùng một bảng CVE tĩnh thay cho kiểm tra advisory mới nhất khi phát hành. Trước mỗi release, kiểm tra Spring Security Advisories và dependency scanner cho toàn bộ dependency tree, kể cả test scope.

## 8. Cấu hình LDAPS/TLS sau khi nâng cấp Spring Boot

Spring Boot 4.2 bổ sung hỗ trợ **SSL bundle cho LDAP** trên auto-configured `LdapContextSource`. Đây là cách gom trust material vào cấu hình có tên, dùng lại được và không cần tự tạo trust manager chấp nhận mọi chứng chỉ.

### 8.1. Cấu hình truststore bằng SSL bundle

Ví dụ `application.yml`:

```yaml
spring:
  ssl:
    bundle:
      jks:
        ldap-client:
          truststore:
            location: "file:/run/secrets/ldap-truststore.p12"
            password: "${LDAP_TRUSTSTORE_PASSWORD}"
            type: "PKCS12"

  ldap:
    urls: "ldaps://ldap.example.org:636"
    base: "dc=example,dc=org"
    username: "uid=ldap-reader,ou=service,dc=example,dc=org"
    password: "${LDAP_BIND_PASSWORD}"
    ssl:
      bundle: "ldap-client"
```

Ý nghĩa:

- `spring.ssl.bundle.jks.ldap-client` định nghĩa trust material tên `ldap-client`.
- `truststore.location` trỏ đến truststore có CA/certificate cần thiết.
- `spring.ldap.ssl.bundle` gắn bundle với LDAP client auto-configuration.
- `ldaps://` dùng TLS ngay khi mở kết nối.
- Password bind và truststore được đưa từ secret/environment, không commit vào repository.

Nếu chỉ dùng trust material mặc định của platform, Spring Boot cũng có property `spring.ldap.ssl.enabled=true`. Dù chọn cách nào, vẫn cần xác minh hostname, certificate chain và chính sách TLS của server.

### 8.2. LDAPS và StartTLS không phải cùng một cấu hình

| Cơ chế | Đặc điểm | Cách cấu hình |
| --- | --- | --- |
| LDAPS | TLS ngay từ đầu trên endpoint `ldaps://` | `spring.ldap.ssl.bundle` hoặc `spring.ldap.ssl.enabled` trên auto-configured context source |
| StartTLS | Mở LDAP rồi nâng cấp kết nối lên TLS | `DirContextAuthenticationStrategy` như `DefaultTlsDirContextAuthenticationStrategy` và SSL socket factory phù hợp |

SSL bundle LDAP của Boot áp dụng cho kết nối **LDAPS**. Không dùng nó như cấu hình StartTLS và không trộn `ldap://` với property SSL bundle dành cho LDAPS trong cùng danh sách URL.

### 8.3. Nếu tự khai báo ContextSource

Các property SSL bundle ở trên áp dụng cho **auto-configured `LdapContextSource`**. Nếu ứng dụng tự tạo `LdapContextSource`, `PooledContextSource` hoặc `ContextSource` tùy chỉnh, phải cấu hình TLS cho bean đó theo cách phù hợp.

Khi thay auto-configured context source, kiểm tra:

- Bean tùy chỉnh có được đánh dấu `@Primary` nếu cần không?
- `LdapTemplate` có đang dùng đúng `ContextSource` không?
- URL, base DN, bind principal và credential có được truyền đúng không?
- Pool có đóng/release context đúng không?
- Truststore và hostname verification có còn được bật không?

Không tắt kiểm tra certificate hoặc chuyển sang `ldap://` chỉ để khắc phục lỗi sau nâng cấp.

## 9. Quy trình nâng cấp có kiểm soát

Nên tách công việc thành những thay đổi có thể kiểm tra và quy trách nhiệm rõ.

### Bước 1: Đóng băng baseline

- Chạy test suite hiện tại và lưu kết quả.
- Ghi dependency tree/effective POM.
- Ghi JDK build/runtime.
- Lưu fixture LDIF giả và các truy vấn quan trọng.
- Export/backup dữ liệu theo quy trình vận hành trước các thay đổi có thể ảnh hưởng dữ liệu LDAP.
- Xác nhận rollback artifact và image cũ vẫn còn.

### Bước 2: Chọn target matrix

Quyết định rõ:

- Có nâng Spring Boot lên 4.2.0 không?
- Nếu chưa nâng Boot, Spring Data/Spring LDAP sẽ dùng nhánh nào được BOM hiện tại hỗ trợ?
- JDK mục tiêu là 21 hay 25?
- Có dùng Spring Data repository, ODM, `LdapTemplate`, `LdapClient`, LDIF hay test server không?
- Có dependency bên ngoài phụ thuộc vào Spring Framework/JNDI không?

Ghi version mục tiêu trong một tài liệu release hoặc pull request. Tránh để mỗi developer tự override một module theo ý mình.

### Bước 3: Nâng JDK và build tool

- Cập nhật JDK cài trên CI.
- Cập nhật Maven/Gradle wrapper đến version được Boot hỗ trợ.
- Cấu hình compiler release/toolchain.
- Cập nhật base image của build và runtime.
- Chạy build với JDK mục tiêu trước khi thay đổi LDAP behavior nếu kiến trúc cho phép tách giai đoạn.

Mục đích là phân biệt lỗi do JDK/build tool với lỗi do Spring dependency.

### Bước 4: Nâng Spring Boot/BOM và Spring Data LDAP

Nếu dùng Boot, ưu tiên đổi **Boot version** và để BOM quản lý các module Spring. Nếu dự án standalone, import Spring Data BOM và Spring Framework BOM tương thích rồi chỉ định Spring LDAP version đúng ma trận.

Sau khi đổi:

- Xóa các version override không còn cần.
- Chạy dependency tree.
- Xác nhận chỉ còn một thế hệ Spring Framework.
- Kiểm tra `spring-data-commons`, `spring-data-ldap`, `spring-ldap-core`, `spring-ldap-odm` và `spring-ldap-test`.
- Xác nhận artifact test không bị giữ ở phiên bản cũ.

### Bước 5: Sửa code và cấu hình bị ảnh hưởng

Tập trung vào:

- `LdapQueryBuilder.fromQuery(...)` và filter có thể bị mất.
- Empty/null password trước bind.
- Custom `AttributeSchema` và custom LDAP attribute names.
- ODM converters, `@Attribute`, `@Id`, multi-valued attributes.
- `DirContextAdapter` và cách remove/replace giá trị.
- TLS/SSL bundle hoặc StartTLS.
- ContextSource tùy chỉnh và connection pool.
- Test fixture embedded LDAP server.

Không refactor toàn bộ repository chỉ để dùng API mới nếu API cũ vẫn được hỗ trợ và không nằm trong vấn đề tương thích. Sửa đúng điểm bị ảnh hưởng rồi kiểm thử.

### Bước 6: Chạy kiểm thử theo tầng

1. Compile và unit tests.
2. Context startup tests: bean, auto-configuration, repository scanning.
3. LDAP integration tests: bind/search/modify/rename/delete trên server thử nghiệm.
4. TLS tests: CA đúng/sai, hostname, LDAPS và StartTLS nếu dùng.
5. Authorization tests: ACL, group membership, primary group và cache.
6. Security regression tests: empty password và filter preservation.
7. Runtime tests trên JDK/container thực tế.

### Bước 7: Triển khai staging/canary

- Dùng cùng loại LDAP server/schema/ACL với production.
- So sánh kết quả truy vấn giữa phiên bản cũ và mới bằng dữ liệu test hoặc shadow read được phê duyệt.
- Theo dõi lỗi bind, timeout, referral, search, mapping và TLS.
- Chỉ tăng traffic sau khi xác nhận kết quả đúng.
- Giữ artifact/container image cũ để rollback nhanh.

### Bước 8: Hoàn tất và ghi nhận

- Cập nhật version matrix thực tế.
- Ghi những thay đổi API/configuration đã thực hiện.
- Ghi kết quả test, security scan và trạng thái rollback.
- Xác nhận team vận hành biết JDK/runtime image mới.
- Theo dõi advisory mới sau phát hành.

## 10. Bộ kiểm thử hồi quy dành riêng cho Spring Data LDAP

Nâng cấp chỉ compile thành công chưa đủ. Hãy kiểm tra hành vi thực tế trên directory server có schema/ACL tương tự production.

### 10.1. Kiểm thử JDK và JNDI

| Tình huống | Kết quả cần xác minh |
| --- | --- |
| Chạy app bằng JDK mục tiêu | JVM khởi động, module JNDI/LDAP provider có mặt |
| Build bằng toolchain khác runtime | Bytecode/API mục tiêu tương thích runtime |
| `java.naming` trong custom runtime | JNDI API có thể được load |
| `jdk.naming.ldap` trong jlink image | LDAP provider có thể được tìm thấy |
| TLS handshake trên JDK mới | Certificate, protocol, cipher và hostname đúng |
| Đổi CA/truststore | Client từ chối certificate không tin cậy |
| Referral/pooling | Context được release, connection không bị leak |

### 10.2. Kiểm thử Spring Data repository và ODM

| Tình huống | Kết quả cần xác minh |
| --- | --- |
| Repository scanning | Repository interface được tạo đúng |
| Derived query theo `uid` | Filter và search base đúng |
| Custom `@Query` | Filter không bị bỏ điều kiện |
| `@Entry` và `@Id Name` | DN được ánh xạ đúng |
| `@Attribute` custom name | Attribute được đọc/ghi đúng |
| Multi-valued attribute | ADD/REMOVE một giá trị không làm mất giá trị khác |
| Rename/move | DN mới được phản ánh, tham chiếu được đối soát |
| Attribute không tồn tại | Mapper xử lý đúng null/missing value |
| Custom converter | Kiểu dữ liệu trước/sau nâng cấp không thay đổi ngoài dự kiến |
| Case/matching rule | Query vẫn khớp theo server schema thực |

### 10.3. Kiểm thử xác thực và security

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| User + password đúng | Bind xác thực thành công |
| User + password sai | Bị từ chối |
| User + password rỗng | Ứng dụng từ chối trước khi bind |
| User + password null | Ứng dụng từ chối trước khi bind |
| User bị khóa/hết hạn | Theo đúng policy account của hệ thống |
| Service account bind được nhưng thiếu ACL | Search/modify bị xử lý đúng, không giả định có quyền |
| Filter builder từ query cũ | Điều kiện bảo mật không bị mất |
| Group membership | Direct/nested/primary group theo đúng directory |
| Test server trong CI | Không mở listener ra network không tin cậy |
| TLS certificate không hợp lệ | Client từ chối, không bỏ qua kiểm tra |

### 10.4. Kiểm thử ghi dữ liệu

Dùng fixture riêng, ví dụ:

```ldif
dn: dc=example,dc=org
objectClass: top
objectClass: domain
dc: example

dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: ou=groups,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: groups

dn: uid=an.nguyen,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an.nguyen
cn: An Nguyen
sn: Nguyen

dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=an.nguyen,ou=people,dc=example,dc=org
```

Kiểm thử:

- Thêm một user vào `developers`.
- Xóa đúng một member và xác nhận member khác vẫn còn.
- Cập nhật entry có DN Unicode/ký tự đặc biệt.
- Thử xóa member cuối của `groupOfNames` và xác nhận schema xử lý đúng.
- Rename/move user và xác minh tham chiếu DN.
- Thử account chỉ đọc để xác nhận server từ chối modify.
- Đọc lại dữ liệu sau write, không chỉ tin response từ client.

Không chạy fixture ghi dữ liệu lên production. Không dùng credential hoặc thông tin người dùng thật trong LDIF kiểm thử.

## 11. Kiểm tra bằng công cụ build sau khi thay đổi

### 11.1. Maven

```bash
mvn -U clean verify

mvn dependency:tree \
  -Dincludes=org.springframework.data:*,org.springframework.ldap:*,org.springframework:spring-*
```

Nếu cần kiểm tra POM đã resolve:

```bash
mvn help:effective-pom
```

Đối chiếu output với ma trận phiên bản đã chọn. `mvn clean verify` phải chạy trên JDK/toolchain dự kiến của CI.

### 11.2. Gradle

```bash
./gradlew clean test

./gradlew dependencies --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency spring-data-ldap \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency spring-ldap-core \
  --configuration runtimeClasspath
```

Kiểm tra thêm `testRuntimeClasspath` để bảo đảm `spring-ldap-test` không bị giữ ở phiên bản bị ảnh hưởng.

### 11.3. Kiểm tra source compatibility và runtime image

Nếu có module Java:

```java
module com.example.directory {
    requires java.naming;
    // Các module ứng dụng và Spring cần thiết khác.
}
```

Nếu build runtime bằng `jlink`, xác minh runtime image chứa module JNDI và LDAP provider cần thiết. Nếu dùng container, chạy smoke test **bên trong image cuối**, không chỉ trên máy developer.

## 12. Triển khai, quan sát và rollback

### 12.1. Các tín hiệu cần theo dõi

| Tín hiệu | Điều cần phát hiện |
| --- | --- |
| LDAP connect/bind failures | Sai credential, TLS, DNS hoặc server policy |
| Search latency/error | Filter/base/scope, ACL, timeout, referral |
| ODM mapping errors | Custom attribute, converter, schema |
| Authentication failures | Empty password, bind DN, account lock |
| Membership lookup differences | `member`, `memberOf`, primary/nested groups |
| Connection pool usage | Context leak, pool sizing, idle connection |
| TLS errors | Certificate expiry, hostname, truststore |
| Test fixture network exposure | Embedded server lắng nghe ngoài phạm vi cần thiết |

Log nên có loại thao tác và nhóm lỗi, không chứa bind password, token hoặc full filter chứa dữ liệu cá nhân. Không biến một lần search rỗng do ACL thành “user chắc chắn không thuộc group”.

### 12.2. Rollback không chỉ là quay lại JAR

Nếu bản mới đã thực hiện ghi LDAP hoặc thay schema, rollback artifact không tự khôi phục dữ liệu.

Một kế hoạch rollback cần xác định:

1. Artifact/container image cũ có sẵn và chạy được trên runtime hiện tại không?
2. Nếu đổi JDK, image cũ có cần JDK cũ riêng không?
3. Cấu hình TLS/SSL bundle cũ có còn được hỗ trợ không?
4. Có thay đổi schema/LDIF/ACL nào trong quá trình nâng cấp không?
5. Có ghi dữ liệu hoặc thay membership cần đối soát/restore không?
6. Có cache/token/session chứa DN hoặc authority được tạo bởi phiên bản mới không?

Ưu tiên rollback code/config trước khi thực hiện các thao tác dữ liệu khó đảo ngược. Nếu schema hoặc dữ liệu đã thay đổi, phải dùng kế hoạch phục hồi được kiểm thử, không chỉ redeploy image cũ.

## 13. Những lỗi thường gặp khi nâng cấp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `NoSuchMethodError` sau khi deploy | Spring Data Commons hoặc Framework bị lệch phiên bản | Dùng BOM, kiểm tra dependency tree |
| `ClassNotFoundException` với JNDI | Runtime image thiếu module Java | Kiểm tra `java.naming` và LDAP provider module |
| App chạy trên máy dev nhưng fail trong container | Build JDK và runtime JDK khác nhau hoặc truststore thiếu | Test trong image cuối |
| Repository bean không tạo được | Version Spring Data LDAP/Commons không tương thích hoặc scanning sai | Kiểm tra BOM và `@EnableLdapRepositories` |
| ODM không ánh xạ custom attribute | Validation/schema/converter thay đổi | Rà soát `AttributeSchema`, `@Attribute` và converter |
| Search trả nhiều kết quả hơn sau nâng cấp | Filter cũ bị bỏ khi dùng `fromQuery(...)` | Nâng bản sửa, chuyển `withQuery(...)`, test filter cuối |
| Login thành công với password rỗng | Phiên bản Spring LDAP bị ảnh hưởng hoặc app không validate input | Nâng bản sửa và chặn null/empty password |
| Test LDAP bị truy cập từ mạng khác | Embedded test server phiên bản bị ảnh hưởng | Nâng `spring-ldap-test`, cô lập network |
| LDAPS handshake fail | CA/truststore/hostname hoặc SSL bundle chưa cấu hình | Kiểm tra certificate và URL |
| StartTLS không còn hoạt động | Nhầm StartTLS với SSL bundle dành cho LDAPS | Dùng `DirContextAuthenticationStrategy` và socket factory phù hợp |
| `memberOf` không xuất hiện | Directory không hỗ trợ, operational attr, ACL hoặc primary group | Kiểm tra server semantics và yêu cầu attribute |
| Multi-valued attribute bị mất giá trị | ODM/adapter dùng replace thay vì remove-by-value | Kiểm tra `DirContextAdapter` và Modify semantics |
| Connection pool cạn | Context không được đóng/release hoặc sizing thay đổi | Kiểm tra lifecycle và load test |
| Rollback app nhưng quyền user vẫn sai | DN/group membership/cache đã bị ghi thay đổi | Đối soát dữ liệu LDAP và invalidation cache |

## 14. Bài thực hành

Một ứng dụng đang dùng:

```text
JDK:               11
Spring Boot:       2.x
Spring Data LDAP:  dependency version khai báo riêng
Spring LDAP:       phiên bản transitive cũ
LDAP:              LDAPS, groupOfNames.member
Build:             Maven
```

Nhóm muốn chuẩn bị nâng lên một stack mới có hỗ trợ repository, `LdapTemplate`, JDK LTS và bảo mật mới.

**Câu A.** Vì sao không nên chỉ sửa version của `spring-data-ldap` rồi giữ nguyên `spring-data-commons` và Spring Framework?

**Câu B.** Nếu chọn Spring Boot 4.2.0, JDK tối thiểu là bao nhiêu và nên kiểm tra JDK runtime nào ngoài JDK build?

**Câu C.** Nếu dự án dùng Spring Boot BOM, có cần khai báo riêng version cho `spring-ldap-core` và `spring-data-ldap` không?

**Câu D.** Vì sao phải kiểm tra cả `testRuntimeClasspath` của `spring-ldap-test`?

**Câu E.** Một query builder được tạo từ query cũ bằng `fromQuery(...)` rồi đặt filter mới. Rủi ro gì đã được advisory CVE-2026-59368 mô tả?

**Câu F.** Nếu user nhập password rỗng, vì sao cần chặn ở application dù LDAP server có thể từ chối?

**Câu G.** Boot 4.2 dùng SSL bundle cho `ldaps://`. Có thể dùng cùng property đó để cấu hình StartTLS không?

**Câu H.** Vì sao test `LdapTemplate` bằng mock không đủ để kết luận upgrade thành công?

**Câu I.** Nếu rename user đã cập nhật DN nhưng một group vẫn giữ `member` cũ, việc rollback JAR có tự khôi phục membership không?

### Gợi ý đáp án

- **A:** Các module Spring Data/Framework có quan hệ tương thích; lệch phiên bản có thể gây lỗi liên kết binary hoặc khởi tạo repository.
- **B:** Spring Boot 4.2 yêu cầu Java 17 trở lên; phải kiểm tra JDK trong container/VM production và JDK mà CI thật sự dùng.
- **C:** Không, nếu BOM quản lý chúng; chỉ override khi có lý do rõ và đã xác minh tương thích.
- **D:** Vì artifact test cũng có advisory bảo mật riêng; test fixture có thể mở cổng LDAP với credential cố định.
- **E:** Filter nguồn có thể bị loại âm thầm khi đặt filter mới, khiến điều kiện bảo mật bị mất; dùng bản sửa và `withQuery(...)` với filter cuối được viết rõ.
- **F:** Simple bind DN không rỗng + password rỗng có thể trở thành unauthenticated bind trên server cho phép, không chứng minh mật khẩu hợp lệ.
- **G:** Không. SSL bundle LDAP của Boot áp dụng cho LDAPS; StartTLS cần strategy/socket factory phù hợp.
- **H:** Mock không kiểm tra schema, ACL, TLS, bind, referral, matching rule, replica hoặc server behavior.
- **I:** Không. Rollback code không tự sửa dữ liệu directory; phải đối soát và phục hồi membership theo kế hoạch riêng.

## 15. Ghi nhớ cốt lõi

- **Nâng cấp theo ma trận tương thích**, không theo số phiên bản từng JAR một cách độc lập.
- Khi dùng Spring Boot, ưu tiên **Boot BOM và starter phù hợp**; với dự án standalone, quản lý Spring Data và Spring Framework bằng BOM tương ứng.
- **JDK build và runtime phải được kiểm tra riêng**; Spring Boot 4.2 yêu cầu Java 17+, nhưng môi trường production nên chọn JDK LTS có support phù hợp.
- Khi nâng Spring LDAP, kiểm tra ODM, custom `AttributeSchema`, multi-valued attribute, query builder và connection/TLS configuration.
- Xử lý advisory **CVE-2026-41720**, **CVE-2026-59367** và **CVE-2026-59368** bằng phiên bản đã sửa của đúng nhánh; vẫn chặn password rỗng và test filter cuối.
- Kiểm thử bằng directory thật hoặc container test cô lập để xác minh **bind, search, schema, ACL, TLS, group membership và write semantics**.
- Triển khai theo giai đoạn, quan sát lỗi và chuẩn bị rollback cả **code, runtime, cấu hình và dữ liệu LDAP**.

## Tài liệu tham khảo

1. [Spring Boot 4.2 — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html) — Java, Spring Framework, Maven và Gradle baseline.
2. [Spring Boot 4.2 — Working with NoSQL Technologies / LDAP](https://docs.spring.io/spring-boot/reference/data/nosql.html) — starter, auto-configuration, `LdapContextSource`, repository và SSL bundle LDAP.
3. [Spring Boot — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html) — các dependency được Boot BOM quản lý.
4. [Spring Data LDAP — Dependencies](https://docs.spring.io/spring-data/ldap/reference/data-commons/dependencies.html) — Spring Data BOM và phiên bản Spring Data LDAP.
5. [Spring Data LDAP — Upgrade Notes](https://docs.spring.io/spring-data/ldap/reference/commons/upgrade.html) — cách đọc upgrade notes theo release.
6. [Spring LDAP — Getting Spring LDAP](https://docs.spring.io/spring-ldap/reference/getting-spring-ldap.html) — starter, version override và dependency alignment.
7. [Spring LDAP — What's New](https://docs.spring.io/spring-ldap/reference/whats-new.html) — thay đổi theo release.
8. [Spring LDAP — API Reference](https://docs.spring.io/spring-ldap/reference/api/java/index.html) — `LdapTemplate`, `LdapClient`, ODM và query APIs.
9. [Spring Security Advisories — CVE-2026-41720](https://spring.io/security/cve-2026-41720/) — authentication bypass với empty password.
10. [Spring Security Advisories — CVE-2026-59367](https://spring.io/security/cve-2026-59367/) — embedded test LDAP server dùng credential cố định và lắng nghe mọi network interface.
11. [Spring Security Advisories — CVE-2026-59368](https://spring.io/security/cve-2026-59368/) — `LdapQueryBuilder` có thể bỏ filter cũ.
12. [Spring LDAP 2026.06 Releases](https://spring.io/blog/2026/06/08/spring-ldap-releases-2026-06/) — các bản sửa empty-password bind.
13. [Spring LDAP 4.2.0 Reference](https://docs.spring.io/spring-ldap/reference/) — tài liệu stable và API của dòng 4.2.
14. [Spring Boot 4.2.0 Release](https://spring.io/blog/2026/11/19/spring-boot-4-2-0-available-now/) — phát hành GA và các thay đổi đáng chú ý.
15. [Oracle Java SE Support Roadmap](https://www.oracle.com/technetwork/java/javase/documentation/eol-135779.html) — các dòng JDK LTS và lịch hỗ trợ của Oracle.
16. [Oracle Java 25 Release](https://www.oracle.com/news/announcement/oracle-releases-java-25-2025-09-16/) — thông tin LTS của Java 25.
17. [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511.html) và [RFC 4513 — LDAP Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513.html) — giao thức LDAP và simple bind.
18. [RFC 4519 — LDAP Schema for User Applications](https://www.rfc-editor.org/rfc/rfc4519.html) — schema user/group và attribute.

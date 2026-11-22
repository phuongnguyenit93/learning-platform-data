# Quản lý phiên bản phụ thuộc tương thích với Spring Framework khi thiết lập Spring AOP

## 1. Mục tiêu và phạm vi

Khi thiết lập **Spring AOP**, việc khai báo đúng các thư viện mới chỉ là bước đầu. Dự án còn phải dùng **các module Spring Framework tương thích với nhau**, phiên bản AspectJ phù hợp và cơ chế quản lý dependency đúng với cách dự án đang dùng Spring Framework thuần hay Spring Boot.

Bài này tập trung vào **phiên bản dependency phục vụ Spring AOP dựa trên proxy trong Spring Framework**, gồm cách chọn artifact, Maven BOM, Gradle platform, Spring Boot dependency management, kiểm tra dependency graph, xử lý xung đột và nâng cấp có kiểm chứng. Đây là kiến thức cấu hình Spring AOP; không đi sâu vào lý thuyết Aspect chung hoặc cấu hình compiler/weaving của AspectJ.

Sau bài học, bạn có thể:

1. Xác định dependency tối thiểu để dùng `@Aspect` và `@EnableAspectJAutoProxy` trong Spring Framework.
2. Giữ các artifact `org.springframework` cùng một phiên bản thông qua BOM hoặc Spring Boot.
3. Phân biệt dependency giữa **Spring Boot 3.x** và **Spring Boot 4.x** khi bật AOP.
4. Đọc dependency tree để tìm các phiên bản bị kéo vào ngoài ý muốn và sửa ở nơi quản lý phiên bản.
5. Chứng minh bằng một chương trình chạy được rằng các dependency thực sự cho phép advice hoạt động.

## 2. Xác định ai quản lý phiên bản của các artifact AOP

Khi dự án dùng Spring AOP với `@Aspect`, ba thành phần chính thường là **`spring-context`** (container), **`spring-aop`** (hạ tầng proxy) và **`aspectjweaver`** (kiểu annotation, phân tích và đối sánh pointcut `@AspectJ`). Các dependency có thể đi qua starter hoặc dependency bắc cầu; điều phải kiểm tra là **phiên bản thực sự được resolve** trên runtime classpath.

| Nhóm phụ thuộc | Nguồn quản lý phiên bản trong Spring Framework thuần | Nguồn quản lý phiên bản trong Spring Boot |
| --- | --- | --- |
| `org.springframework:spring-context`, `spring-aop` cùng `spring-core`, `spring-beans`, `spring-expression` | Một `spring-framework-bom` thống nhất | Boot parent/BOM đồng bộ các module Spring |
| `org.aspectj:aspectjweaver` | Khai báo phiên bản AspectJ tương thích riêng và kiểm chứng | Boot BOM quản lý phiên bản thông qua starter AOP/AspectJ |
| `org.springframework:spring-aspects` (chỉ dùng cho tích hợp weaving chuyên biệt) | Spring Framework BOM, nếu thực sự có nhu cầu | Boot BOM, nếu được sử dụng |
| `org.aspectj:aspectjtools` (chỉ dùng khi biên dịch/weaving bằng AspectJ) | Version/toolchain của AspectJ, không thuộc Spring Framework BOM | Không cần cho Spring proxy AOP thông thường |

**Điểm mấu chốt của bài quản lý phiên bản:** các module `org.springframework:spring-*` phải đồng bộ theo release Spring Framework, nhưng AspectJ có chu kỳ phát hành và số hiệu riêng. Ví dụ `spring-aop:7.0.9` đi cùng `aspectjweaver:1.9.25.1` là bình thường khi BOM quản lý tổ hợp đó. Sự có mặt của `aspectjweaver` **không tự kích hoạt AspectJ weaving**; ứng dụng bật `@EnableAspectJAutoProxy` vẫn dùng Spring proxy AOP.


## 3. Nguyên tắc chọn phiên bản

### 3.1. Chọn nền tảng trước, sau đó để nền tảng quản lý dependency

- **Ứng dụng Spring Boot:** chọn phiên bản **Spring Boot** phù hợp dự án, để **Spring Boot parent/BOM và plugin quản lý các phiên bản Spring Framework, AspectJ**. Thường không tự chèn `<version>` hoặc `:version` cho từng module AOP.
- **Ứng dụng Spring Framework thuần:** chọn **một phiên bản Spring Framework**, import `org.springframework:spring-framework-bom`, khai báo các module `org.springframework` **không ghi version riêng**; quản lý `org.aspectj:aspectjweaver` bằng phiên bản độc lập phù hợp.
- **Dự án có nhiều module:** quản lý BOM/constraints tại một vị trí thống nhất và kiểm tra resolved dependencies trong từng module chạy thực tế.
- **Khi nâng cấp:** cập nhật một nền tảng rồi chạy biên dịch, kiểm thử ứng dụng và kiểm tra dependency tree; không nâng riêng `spring-aop` lên phiên bản khác với `spring-context`.

### 3.2. Ví dụ những tổ hợp đã được công bố

Bảng minh họa các phiên bản được khai báo trong tài liệu/metadata phát hành. Đây **không phải** quy tắc dự đoán phiên bản tương lai; trong dự án thực tế cần đối chiếu BOM đang dùng.

| Nền tảng | Phiên bản Spring Framework do nền tảng quản lý | Starter Spring AOP | AspectJ Weaver do nền tảng quản lý |
| --- | --- | --- | --- |
| Spring Boot **3.5.16** | **6.2.19** | `org.springframework.boot:spring-boot-starter-aop` | **1.9.25.1** |
| Spring Boot **4.0.8** | **7.0.9** | `org.springframework.boot:spring-boot-starter-aspectj` | Do Boot 4.0.8 BOM quản lý; xem effective dependency graph |

Với Spring Boot **4.0**, starter `spring-boot-starter-aop` được **đổi tên** thành `spring-boot-starter-aspectj`. Không sao chép nguyên dependency của Boot 3 sang dự án Boot 4 rồi giả định artifact cũ vẫn được BOM quản lý. Tên mới **không có nghĩa** mỗi ứng dụng phải cấu hình AspectJ bytecode weaving: starter vẫn cung cấp `spring-aop` và `aspectjweaver` để Spring dùng hỗ trợ `@AspectJ`.

Spring Framework **6.x và 7.x** đều yêu cầu tối thiểu **Java 17**, nhưng Spring 7 còn nâng baseline của một số công nghệ Jakarta liên quan; khi nâng từ Boot 3 sang Boot 4 cần kiểm tra **cả ứng dụng**, không chỉ AOP. Các phiên bản liệt kê dùng để học cách quản lý dependency; không nên nâng cấp theo bảng mà bỏ qua trạng thái hỗ trợ của phiên bản và nhu cầu dự án.

**Nguyên tắc tương thích quan trọng:** Các dependency `org.springframework:spring-*` trong *một ứng dụng* thường nên được căn chỉnh theo **đúng cùng phiên bản release**, ví dụ toàn bộ Spring Framework **7.0.9**. Việc thấy `spring-context:7.0.9` cùng `spring-aop:6.2.19` là dấu hiệu phải kiểm tra, kể cả khi mã vẫn biên dịch.

## 4. Spring Framework thuần với Maven BOM

Khi không dùng Spring Boot, cách tránh lệch phiên bản là nhập **Spring Framework BOM** trong phần `dependencyManagement`. Ví dụ chạy với **Java 17+**, Spring Framework **7.0.9** và AspectJ Weaver **1.9.25.1**:

**`pom.xml` đầy đủ**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-aop-version-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework</groupId>
                <artifactId>spring-framework-bom</artifactId>
                <version>7.0.9</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.25.1</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Ở đây, cả `spring-context` và `spring-aop` đều không cần ghi version vì BOM quản lý chúng. Các dependency Spring chuyển tiếp như `spring-core`, `spring-beans` cũng được căn chỉnh theo BOM. `aspectjweaver` nằm trong **group khác**, nên Spring Framework BOM không được xem là nguồn xác định version của thư viện này; ta chọn version rõ ràng và kiểm tra tương thích.

### 4.1. Chương trình để kiểm tra thiết lập AOP

Thư mục dự án:

```text
spring-aop-version-demo/
├── pom.xml
└── src/main/java/example/
    ├── AppConfig.java
    ├── MessageService.java
    ├── AuditAspect.java
    └── Main.java
```

**`MessageService.java`**

```java
package example;

public class MessageService {
    public void send() {
        System.out.println("Service: send");
    }
}
```

**`AuditAspect.java`**

```java
package example;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class AuditAspect {
    @Before("execution(* example.MessageService.send(..))")
    public void beforeSend() {
        System.out.println("Aspect: before");
    }
}
```

**`AppConfig.java`**

```java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy
public class AppConfig {
    @Bean
    public MessageService messageService() {
        return new MessageService();
    }

    @Bean
    public AuditAspect auditAspect() {
        return new AuditAspect();
    }
}
```

**`Main.java`**

```java
package example;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            MessageService service = context.getBean(MessageService.class);
            System.out.println("AOP proxy: " + AopUtils.isAopProxy(service));
            service.send();
        }
    }
}
```

Tại thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
```

Các dòng do `Main` và các phương thức ví dụ in ra, theo thứ tự:

```text
AOP proxy: true
Aspect: before
Service: send
```

**Vì sao ví dụ chứng minh dependency tương thích?** Nếu Maven resolve được các artifact, biên dịch thành công, context khởi động, tự tạo AOP proxy và advice chạy đúng thì đường đi `spring-context` → `spring-aop` → `aspectjweaver` đã hoạt động cho trường hợp này. Kết quả đó **không thay thế** kiểm thử hồi quy toàn ứng dụng sau nâng cấp.

Lưu ý: `@EnableAspectJAutoProxy` chỉ bật xử lý proxy cho context tương ứng; `AuditAspect` được đăng ký qua `@Bean`. Nếu có thư viện trên classpath nhưng thiếu bước bật AOP hoặc chưa đăng ký aspect làm bean thì việc resolve dependency thành công **không tự khiến advice chạy**.

### 4.2. Nếu dùng Gradle thay Maven

Trong dự án Java dùng **Gradle Groovy DSL**, ví dụ nội dung `build.gradle` tương ứng:

```groovy
plugins {
    id 'java'
    id 'application'
}

group = 'example'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('org.springframework:spring-framework-bom:7.0.9')
    implementation 'org.springframework:spring-context'
    implementation 'org.springframework:spring-aop'
    implementation 'org.aspectj:aspectjweaver:1.9.25.1'
}

application {
    mainClass = 'example.Main'
}
```

Đặt bốn file Java ở cùng đường dẫn như mục 4.1, sau đó chạy:

```bash
./gradlew run
```

Trên Windows PowerShell dùng `./gradlew.bat run`; yêu cầu project có Gradle Wrapper. Kết quả nghiệp vụ vẫn là ba dòng của ví dụ. Với Gradle, `platform(...)` cung cấp **version constraints**, nhưng resolution có thể chọn version cao hơn khi dependency khác đưa vào yêu cầu mạnh hơn; vì vậy **vẫn phải kiểm tra phiên bản thực tế** sau khi resolve. Tránh ép `enforcedPlatform` bừa bãi lên một library được phân phối cho ứng dụng khác.

## 5. Ứng dụng Spring Boot: ưu tiên starter và BOM của Boot

### 5.1. Spring Boot 4.x (ví dụ Maven Boot 4.0.8)

Đây là cấu hình Maven tối giản cho một ứng dụng Boot 4 sử dụng `@Aspect`. Parent đã quản lý version của các dependency cần thiết:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.8</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>boot-aop-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aspectj</artifactId>
        </dependency>
    </dependencies>
</project>
```

Ứng dụng Boot thật vẫn cần các starter khác theo chức năng (web, data, test, v.v.). Điểm cần học ở đây là **cách khai báo AOP và ai sở hữu phiên bản**:

- Parent `spring-boot-starter-parent:4.0.8` dùng dependency management của Boot 4.0.8.
- Starter `spring-boot-starter-aspectj` mang vào `spring-aop` và `aspectjweaver` phù hợp với nền tảng.
- Không chèn `spring-aop:6.x` hoặc `aspectjweaver` phiên bản tự chọn vào ví dụ Boot 4 khi chưa có lý do đã kiểm chứng.
- Spring Boot có auto-configuration hỗ trợ AOP; với AspectJ trên classpath, thông thường **không cần viết thêm `@EnableAspectJAutoProxy`**. Cần đăng ký lớp `@Aspect` thành Spring bean qua `@Component` hoặc `@Bean`.

Nếu dự án **Gradle Boot 4** đã cấu hình Spring Boot plugin và dependency management/BOM chuẩn, phần AOP thường chỉ cần:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aspectj'
}
```

Chỉ bỏ version của starter khi **BOM thực sự đang được áp dụng**; riêng khai báo plugin Spring Boot trong một build tùy biến chưa luôn đồng nghĩa dependency management đã được cấu hình đúng. Kiểm tra resolved graph.

### 5.2. Spring Boot 3.x (ví dụ Boot 3.5.16)

Với ứng dụng đang sử dụng Spring Boot 3, dependency được quản lý bằng Boot 3 parent/BOM và starter có tên cũ:

```xml
<!-- Bên trong <dependencies> của dự án sử dụng Boot 3.5.x BOM/parent -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aop</artifactId>
</dependency>
```

Bản tương ứng của Gradle Boot 3 (sau khi đã áp dụng Boot BOM):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

**Không trộn hai thế hệ:** Boot **3.5.16** quản lý Spring Framework **6.2.19**, còn Boot **4.0.8** quản lý Spring Framework **7.0.9**. Không sao chép nguyên cấu hình Spring Framework 7 vào dự án Boot 3 để “chỉ cập nhật AOP”. Khi chuyển Boot 3 → Boot 4, thực hiện kế hoạch nâng cấp framework toàn ứng dụng và đổi starter AOP tương ứng.

### 5.3. Chỉ dùng Spring Boot BOM, không dùng parent

Trong dự án Maven có parent riêng, import BOM của Boot:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>4.0.8</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Sau đó thêm `spring-boot-starter-aspectj` **không ghi version** vào `<dependencies>`. Import BOM **chỉ quản lý phiên bản**, không tự cung cấp plugin biên dịch/chạy, các mặc định của Boot parent, hoặc tạo ra dependency ứng dụng nếu chưa khai báo.

Trong Gradle, có thể dùng `platform('org.springframework.boot:spring-boot-dependencies:4.0.8')` trong `dependencies` để quản lý phiên bản cho các dependency liên quan. Dự án dùng plugin `io.spring.dependency-management` có cú pháp import BOM riêng; không chồng nhiều cách quản lý khi chưa hiểu thứ tự ưu tiên và kết quả resolved.

## 6. Kiểm tra phiên bản **đã resolve**, không chỉ phiên bản đã khai báo

Một file `pom.xml` hoặc `build.gradle` có vẻ đúng vẫn có thể gặp xung đột bởi dependency transitives, parent/BOM khác, constraints, explicit version, plugin hoặc module con.

### 6.1. Maven

Chạy tại đúng Maven module chứa Spring AOP:

```bash
mvn dependency:tree
mvn help:effective-pom
```

Tìm các mục:

```text
org.springframework:spring-aop
org.springframework:spring-context
org.springframework:spring-core
org.springframework:spring-beans
org.aspectj:aspectjweaver
```

Kiểm tra rằng các artifact Spring Framework được resolve **cùng phiên bản** (trong ví dụ Maven thuần là `7.0.9`), và `aspectjweaver` thực sự có trên classpath. Nếu nghi ngờ BOM không được áp dụng, xem `effective-pom` và phần `dependencyManagement`. Chú ý những phiên bản đã bị Maven bỏ qua do version mediation; nhìn riêng dependency trực tiếp chưa đủ.

### 6.2. Gradle

Chạy ở module ứng dụng, ví dụ:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-aop --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-context --configuration runtimeClasspath
./gradlew dependencyInsight --dependency aspectjweaver --configuration runtimeClasspath
```

Trên Windows dùng `./gradlew.bat` hoặc chạy task với đường dẫn module, ví dụ `:app:dependencyInsight`, khi `app` là Gradle subproject ứng dụng.

Ví dụ ý nghĩa của kết quả giả định:

```text
org.springframework:spring-aop:6.2.19 -> 7.0.9
```

Ký hiệu `->` trong cây phụ thuộc Gradle thể hiện **phiên bản yêu cầu được thay bằng phiên bản resolve**. Hãy tìm **lý do chọn phiên bản** qua `dependencyInsight`; không xem chuỗi này là bằng chứng lỗi tự động nếu tất cả module Spring cuối cùng đã được căn chỉnh và tổ hợp đó được hỗ trợ.

### 6.3. Kiểm tra sự hiện diện và vận hành của AOP

Dù graph hợp lệ, hãy thử `AopUtils.isAopProxy(bean)` trên bean phù hợp hoặc tạo một kiểm thử gọi phương thức có advice. Nếu chương trình lỗi `ClassNotFoundException`, `NoClassDefFoundError` hoặc `NoSuchMethodError`, kiểm tra **class nào đang thiếu**, version thực tế, classpath runtime và bước đóng gói. Các lỗi này **có thể** bắt nguồn từ lệch dependency, nhưng không nên gán nguyên nhân chỉ từ tên exception.

## 7. Các lỗi cấu hình thường gặp và cách sửa

| Hiện tượng | Nguyên nhân đáng kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `NoClassDefFoundError` liên quan `org.aspectj.*` | Thiếu `aspectjweaver` trên classpath lúc chạy, scope sai hoặc packaging loại bỏ dependency | Thêm starter đúng thế hệ Boot hoặc dependency AspectJ trong ứng dụng Spring thuần; kiểm tra runtimeClasspath |
| `NoSuchMethodError` xuất hiện sau khi nâng Spring | Nhiều phiên bản `spring-*` bị trộn hoặc thư viện thứ ba chưa tương thích | Đối chiếu dependency tree; căn chỉnh Spring BOM/nền tảng; kiểm tra lại thư viện tích hợp |
| Maven báo thiếu version cho `spring-boot-starter-aop` trên Boot 4 | Đang dùng artifact cũ không được Boot 4 BOM quản lý | Chuyển sang `spring-boot-starter-aspectj` khi áp dụng Boot 4 BOM |
| Spring context chạy nhưng `@Before` không thực thi | Aspect chưa thành bean, AOP chưa bật, pointcut không khớp hoặc lời gọi bỏ qua proxy | Kiểm tra khai báo aspect, `@EnableAspectJAutoProxy`/Boot auto-configuration, proxy và đường gọi |
| Cùng lúc thấy Spring 6 và Spring 7 trong dependency graph | Override trực tiếp, parent/BOM khác nhau, dependency transitives hoặc resolution rule | Chọn một nền tảng nhất quán, bỏ version override thừa và xem effective graph |
| Build compile được nhưng runtime lỗi trên JDK khác | Baseline Java/bytecode của framework và library không phù hợp môi trường chạy | Kiểm tra `java -version`, cấu hình compiler/toolchain và JVM chạy thực tế |

**Ba sai lầm cần tránh:**

1. **Viết version cho mọi dependency:** dễ dẫn đến `spring-aop`, `spring-context` và các Spring modules khác lệch release. Sử dụng BOM/parent trước.
2. **Cho rằng thêm `spring-aspects` thay thế `spring-aop`:** chúng có vai trò khác nhau; proxy-based Spring AOP không cần spring-aspects mặc định.
3. **Nâng AspectJ hoặc Spring AOP độc lập với nền tảng:** không kết luận tương thích chỉ từ việc Maven/Gradle tải artifact thành công.

## 8. Quy trình nâng cấp Spring AOP an toàn trong dự án

1. **Xác định nguồn quản lý version:** Spring Boot parent/BOM, Spring Framework BOM, Gradle platform, plugin dependency management, corporate parent hoặc version catalog.
2. **Ghi lại graph hiện tại:** xem version của `spring-aop`, `spring-context`, `spring-core`, `spring-beans`, `aspectjweaver`, JDK; nếu multi-module, kiểm tra module chạy.
3. **Chọn một bộ phiên bản được hỗ trợ:** nâng Boot như một nền tảng hoàn chỉnh, hoặc thay một Spring Framework BOM thống nhất khi không dùng Boot; xác minh baseline JDK.
4. **Giữ dependency declaration đơn giản:** xóa override phiên bản không cần thiết; chọn đúng starter theo Boot 3 hay Boot 4.
5. **Resolve và đối chiếu lại:** Maven `dependency:tree`/`help:effective-pom` hoặc Gradle `dependencies`/`dependencyInsight`. Không chỉ dựa vào nội dung file build.
6. **Chạy kiểm thử Spring AOP:** ít nhất một bean có `@Aspect` match và một lời gọi qua proxy; chạy thêm integration tests của ứng dụng để phát hiện thay đổi tương thích.
7. **Chỉ nâng cấp xong khi build và runtime đều đạt:** đảm bảo artifact đóng gói chứa dependency cần thiết và môi trường triển khai dùng Java phù hợp.

### Bài tập vận dụng

Dự án có Boot `4.0.8`, khai báo đồng thời `spring-boot-starter-aop`, `spring-aop:6.2.19` và `aspectjweaver:1.9.25.1`. Hãy xác định điều cần sửa.

**Đáp án:** Dùng starter `spring-boot-starter-aspectj` của Boot 4; bỏ khai báo version `spring-aop:6.2.19` vì Boot 4.0.8 quản lý Spring Framework `7.0.9`; bỏ khai báo `aspectjweaver` thủ công nếu starter đã cung cấp và không có nhu cầu đặc biệt. Cuối cùng, kiểm tra Maven/Gradle resolved graph và chạy test `@Aspect` thực tế. Việc ghim `aspectjweaver:1.9.25.1` có thể trùng version mà BOM quản lý, nhưng tạo thêm một điểm override dễ gây lệch khi nâng Boot về sau.

## 9. Tài liệu gốc để đối chiếu phiên bản

- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): cấu hình Spring proxy và yêu cầu AspectJ trên classpath.
- [Spring Framework — Spring Framework Artifacts](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Artifacts): artifact, dependency và override theo phiên bản.
- [Spring Framework BOM trên Maven Central](https://central.sonatype.com/artifact/org.springframework/spring-framework-bom): xem release BOM thực tế.
- [Spring Boot 3.5 — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html): Spring và AspectJ được Boot 3.5 quản lý.
- [Spring Boot 4.0 — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/4.0/appendix/dependency-versions/coordinates.html): Spring và starter được Boot 4.0 quản lý.
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): thay đổi tên starter AOP/AspectJ.
- [Spring Boot — Aspect-Oriented Programming](https://docs.spring.io/spring-boot/reference/features/aop.html): auto-configuration Spring AOP và proxy.

# Quản lý phiên bản qua Spring Boot BOM và kiểm soát ghi đè dependency

> **Ngữ cảnh:** Spring Security fundamentals · nhóm **Phiên bản và học tiếp** · Spring Boot 3.x, Java 17+, Maven và Gradle. Bài này giải thích **BOM (Bill of Materials)**, cách Spring Boot quản lý phiên bản của Spring Security cùng các thư viện liên quan, cách override có kiểm soát, cách kiểm tra phiên bản thực được resolve và quy trình cập nhật để tránh lệch dependency. Ví dụ sử dụng **Spring Boot 3.5.16** làm snapshot đã được tài liệu chính thức xác nhận; con số này chỉ để tái hiện bài học, không phải khuyến nghị giữ nguyên cho production về sau.

## 1. Bài toán: vì sao không tự chọn version cho mỗi thư viện?

Trong Spring Boot, ta thường viết Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
```

hoặc Gradle:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-security'
```

Không có `<version>` hoặc `:version` vì project thường đã dùng **Spring Boot dependency management**. Spring Boot phát hành một bộ version được kiểm thử kết hợp: Spring Security, Spring Framework, Jackson, logging, servlet container, thư viện test và nhiều thành phần khác.

Nếu người học tự thêm:

```groovy
// Ví dụ nguy hiểm để nhận diện, không dùng cho production:
implementation 'org.springframework.security:spring-security-web:6.4.5'
implementation 'org.springframework.security:spring-security-config:6.5.11'
```

thì nhóm Security modules có thể bị lệch phiên bản. Cách Gradle thực sự resolve có thể khác số viết trực tiếp, nhưng nếu final classpath không tương thích thì có thể gây `NoSuchMethodError`, `NoClassDefFoundError`, hành vi filter khác dự kiến hoặc bỏ sót bản vá bảo mật. Việc tự ghim mọi module đồng nghĩa project phải tự gánh trách nhiệm tương thích mà BOM vốn đã giúp giảm bớt.

### Kết quả học tập

Sau bài này, cần trả lời được: BOM là gì và khác starter như thế nào; Maven parent và Maven import BOM khác gì; Gradle `io.spring.dependency-management` và native `platform(...)` khác gì; override bằng cách nào; vì sao phải kiểm tra **resolved graph**; khi nào nên nâng Boot patch thay vì chỉ sửa một module Spring Security; và làm sao ngăn dependency drift trong CI/CD.

## 2. BOM, starter, plugin và resolved graph

### 2.1. BOM (Bill of Materials)

Spring Boot cung cấp `org.springframework.boot:spring-boot-dependencies`. Đây là POM quản lý các tọa độ `groupId:artifactId:version` của bộ thư viện phù hợp với một Spring Boot release.

```text
Project chọn Spring Boot 3.5.16
           |
           v
spring-boot-dependencies:3.5.16
           |
           +-- Spring Security core/web/config/test -> 6.5.11
           +-- Spring Framework modules             -> curated versions
           +-- Jackson, Logback, Tomcat, ...         -> curated versions
           |
           v
Build tool giải graph từ các dependency project đã khai báo
           |
           v
Compile / runtime / test classpaths thực tế
```

Theo bảng managed coordinates của Spring Boot 3.5.16, các module `spring-security-core`, `spring-security-config`, `spring-security-web` và `spring-security-test` cùng phiên bản **6.5.11**. Đây là thông tin **gắn với một Boot release cụ thể**; khi đổi Boot, cần đọc bảng mới và chạy lại dependency tree.

**BOM không tự thêm thư viện.** Nó quản lý phiên bản cho artifact đã có trong đồ thị, không tự biến classpath thành Spring Security.

### 2.2. Starter

`spring-boot-starter-security` là dependency khởi đầu, kéo các module cần thiết vào classpath theo quan hệ transitive. Starter và BOM có vai trò khác nhau:

- Starter: **cần thư viện nào**?
- BOM: **dùng phiên bản nào cho các thư viện được quản lý**?
- Build resolver: sau mọi constraints và overrides, **phiên bản nào thực sự được chọn**?

Một version trong BOM không phải lúc nào cũng là version runtime: explicit direct version, BOM khác, constraints, lockfile, conflict resolution hoặc forced version có thể làm kết quả khác.

### 2.3. Dependency management khác plugin management

| Thành phần | Chức năng | Ví dụ |
| --- | --- | --- |
| Maven `<dependencies>` | Đưa artifact vào graph | `spring-boot-starter-security` |
| Maven `<dependencyManagement>` | Điều khiển metadata phiên bản dependency | `spring-boot-dependencies` import |
| Maven `<pluginManagement>` | Điều khiển build plugins | `maven-compiler-plugin` |
| Gradle `plugins` | Version công cụ build | `org.springframework.boot` plugin |
| Gradle `platform(...)` | Native constraints từ BOM | `spring-boot-dependencies` |
| Gradle dependency-management plugin | Quản lý dependency theo kiểu Maven | `io.spring.dependency-management` |

Đừng nhầm `spring-boot-maven-plugin` với `spring-boot-dependencies`. Import BOM không tự mang theo mọi cấu hình compiler/repackage của `spring-boot-starter-parent`.

## 3. Nguyên tắc chọn version của Spring Boot và Spring Security

Một release Boot đã được thiết kế, kiểm thử với một tập phiên bản cụ thể. Thực hành an toàn thường là:

1. **Chọn Spring Boot release được hỗ trợ** phù hợp Java và framework stack.
2. Dùng BOM đi kèm release đó để quản lý dependencies.
3. Không khai báo version cho các starter/module đã có trong BOM, trừ khi có lý do override được review.
4. Theo dõi bản vá bảo mật; khi có Boot patch mới, cân nhắc nâng Boot/BOM trước.
5. Chỉ override trực tiếp khi thật sự cần và đã kiểm tra compatibility.
6. Sau đó xác nhận bằng **resolved graph và integration tests**, không chỉ đọc POM/Gradle file.

**Cảnh báo:** Spring Security major 7.x không phải một “patch” thay cho Security 6.5.x của Boot 3.5.x. Những dòng major có thể yêu cầu Spring Framework mới và có thay đổi breaking APIs. Nâng Security/Framework/Boot major cần xem compatibility matrix và migration guide, không lắp ghép chỉ vì version cao hơn.

Version number trong ví dụ là snapshot để học; khi mở bài vào thời điểm khác, hãy đối chiếu bảng `Managed Dependency Coordinates` và support policy hiện hành.

## 4. Maven cách A: kế thừa spring-boot-starter-parent

Tệp `pom.xml` **hoàn chỉnh** cho lab Java 17:

```xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>bom-security-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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

**Vì sao chạy được mà không có version trên dependencies?** Parent kế thừa BOM, quản lý các starter và `spring-security-test`. Parent còn mang compiler defaults, resource filtering và plugin management. Java 17 được khai báo trong properties. Không cần pin riêng phiên bản Security core/web/config/test.

`<relativePath/>` báo Maven không tự tìm parent POM ở đường `../pom.xml`, tránh nhầm corporate/local parent nếu tình cờ có file cùng chỗ.

### Kiểm tra parent và graph

```bash
# Khi project có Maven Wrapper:
./mvnw test
./mvnw help:effective-pom -Doutput=effective-pom.xml
./mvnw dependency:tree -Dincludes=org.springframework.security
./mvnw dependency:tree -Dscope=test
./mvnw help:evaluate -Dexpression=project.parent.version -q -DforceStdout
```

Giá trị `project.parent.version` từ POM minh họa là `3.5.16`. Kết quả chi tiết `dependency:tree` phụ thuộc graph thực tế và phiên bản plugin; cần xem **mọi Security module đang resolve**, không đòi cây in ra đúng thứ tự cứng.

## 5. Maven cách B: import BOM khi có corporate parent

Maven chỉ có **một parent trực tiếp**. Nếu ứng dụng đã kế thừa parent doanh nghiệp, không thể tiếp tục kế thừa đồng thời `spring-boot-starter-parent` như một parent thứ hai. Khi đó có thể **import Spring Boot BOM**:

```xml
<!-- Trích đoạn của pom.xml với parent khác, không phải POM đầy đủ -->
<properties>
    <java.version>17</java.version>
    <spring-boot.version>3.5.16</spring-boot.version>
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
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
</dependencies>
```

BOM import quản lý dependency versions, **không mang theo toàn bộ build plugin defaults** của Boot parent. Nếu corporate parent không quản lý compiler, plugin và repackage phù hợp, phải cấu hình rõ. Ví dụ trích đoạn:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.14.0</version>
            <configuration>
                <release>17</release>
            </configuration>
        </plugin>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <version>${spring-boot.version}</version>
            <executions>
                <execution>
                    <goals><goal>repackage</goal></goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Đây là ví dụ về **build configuration bổ sung**, không nên chèn vào corporate parent nếu nơi đó đã có quy tắc khác. `dependencyManagement` và `pluginManagement` là hai hệ thống khác nhau.

## 6. Maven override: parent property khác imported BOM

### 6.1. Khi kế thừa Boot parent

Spring Boot dùng properties cho managed versions. Ví dụ:

```xml
<!-- Trong <properties> của POM có parent Spring Boot -->
<properties>
    <java.version>17</java.version>
    <spring-security.version>6.5.11</spring-security.version>
</properties>
```

Với Boot 3.5.16, `6.5.11` chính là bản được BOM quản lý; đoạn trên **minh họa cơ chế property**, chưa phải nâng cấp. Nếu phải vá sang phiên bản khác, hãy thay bằng **version thực được upstream phát hành** và đã kiểm chứng compatibility, sau đó đọc `effective-pom` và `dependency:tree`.

Boot còn có property `spring-framework.version`. Đừng tự ghim Spring Framework chỉ vì thấy version mới: Spring Security và Boot phụ thuộc vào một baseline Framework tương thích.

### 6.2. Khi chỉ import BOM

Nếu **không kế thừa Boot parent** mà chỉ có `spring-boot-dependencies` import, việc đặt `spring-security.version` trong project **không tự sửa các property bên trong imported BOM theo cách giống parent inheritance**. Theo Spring Boot Maven docs, muốn override phải thêm entry trực tiếp trong `<dependencyManagement>`, ưu tiên trước BOM import:

```xml
<!-- Ví dụ minh họa cú pháp; 6.5.11 trùng version BOM, chưa phải nâng -->
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-web</artifactId>
            <version>6.5.11</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.5.16</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

**Cảnh báo:** override một `spring-security-web` không tự bảo đảm `spring-security-config`, `core`, `test` và OAuth2 modules cũng được cập nhật. Khi cần override cả họ Security, hãy xét BOM của Spring Security (hoặc entry family có kiểm soát) và xem precedence giữa các BOM. **Cách ưu tiên thường là nâng Boot patch để nhận bộ đã được kiểm thử**.

### 6.3. Direct dependency version không phải “managed version”

Nếu bạn viết `<version>6.4.5</version>` trực tiếp cho `spring-security-web` trong `<dependencies>`, đó là yêu cầu cụ thể cho dependency này. Nó có thể lệch với dependencyManagement khác hoặc module transitive. Không đọc mỗi dòng trong POM để khẳng định runtime version; dùng Maven dependency tree.

## 7. Gradle cách A: io.spring.dependency-management

Spring Boot Gradle plugin nhận biết khi áp dụng `io.spring.dependency-management` và tự import BOM cùng Boot plugin version.

`settings.gradle`:

```groovy
rootProject.name = 'bom-security-demo'
```

`build.gradle` **hoàn chỉnh — lựa chọn A**:

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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đoạn này dùng version của **plugin Spring Boot** làm nguồn xác định BOM được import. Không cần ghi version riêng cho các starter và `spring-security-test`.

Nếu cần override qua property của BOM:

```groovy
// Chèn vào build.gradle cách A khi đã review.
// 6.5.11 là version do BOM 3.5.16 mặc định chọn.
ext['spring-security.version'] = '6.5.11'
```

Giá trị property có thể được thay bằng một bản vá upstream thích hợp, nhưng phải chạy `dependencyInsight` và regression tests. Với project **publish Maven POM**, property override của Gradle dependency-management plugin có các giới hạn về published POM; hãy xem hướng dẫn plugin và cân nhắc override bằng dependency-management entry để metadata xuất bản phản ánh đúng.

**Không ghép đoạn này tùy tiện với `platform(...)` ở cách B** nếu chưa xác định rõ nguồn management và precedence.

## 8. Gradle cách B: native platform(...)

Gradle hỗ trợ import Maven BOM bằng `platform(...)` mà không cần dependency-management plugin.

`build.gradle` **thay thế toàn bộ cách A**:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
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
    implementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )
    testImplementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )

    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`SpringBootPlugin.BOM_COORDINATES` trỏ tới BOM ứng với phiên bản plugin Boot được khai báo. `platform` đưa **version constraints** vào configuration. Tùy graph, yêu cầu phiên bản khác có thể khiến resolved version **khác version trong BOM**; vì vậy cần `dependencyInsight`. Việc import BOM chỉ ảnh hưởng các configuration đã khai báo và các configuration kế thừa phù hợp; ví dụ đặt vào cả `implementation` và `testImplementation` để thể hiện ý định rõ.

### platform và enforcedPlatform

| Cơ chế | Ý nghĩa | Đánh đổi |
| --- | --- | --- |
| `platform(...)` | BOM versions là constraints/recommendations; version khác có thể được resolver chọn | Thường linh hoạt hơn; cần xem selected version |
| `enforcedPlatform(...)` | Ép mạnh BOM versions qua strict constraints | Có thể xung đột hoặc áp giới hạn lên consumers |
| `strictly(...)` trên dependency | Yêu cầu version strict | Resolution có thể fail nếu các constraints không tương thích |
| `resolutionStrategy.force(...)` | Cưỡng ép bản chọn | Dễ che incompatibility, cần review đặc biệt |

**Không dùng enforcedPlatform để “vá bảo mật” bằng cách ép bản cũ.** Nếu một thư viện đòi patch mới hơn, force theo BOM cũ có thể khiến runtime không tương thích hoặc chưa vá CVE.

### Native platform không nhận property override kiểu plugin A

Trong Gradle native `platform`, `ext['spring-security.version'] = '...'` không tự sửa các property nội bộ của Spring Boot BOM như khi dùng `io.spring.dependency-management`. Muốn override phải dùng một cơ chế Gradle hợp lệ: version constraint, explicit version, resolution strategy hoặc platform/BOM khác có chủ đích. Kiểm tra resolved graph để xác nhận.

## 9. Các nguồn override và precedence

| Ngữ cảnh | Nơi phát sinh override | Điều cần kiểm tra |
| --- | --- | --- |
| Maven inherit parent | `spring-security.version`, `spring-framework.version` | Effective POM |
| Maven import BOM | Entry riêng trong `dependencyManagement` | POM local vs imported BOM |
| Maven direct dependency | `<dependency><version>...` | Direct version vs management |
| Maven nhiều BOM | Thứ tự imports và direct entries | Với conflict BOM, Maven dùng quy tắc import của Maven |
| Gradle dependency-management plugin | `ext['...']`, DSL imports/dependencies | BOM import **sau** có thể override BOM trước |
| Gradle native platform | Constraints, explicit versions | Resolver chọn theo graph, không “last wins” đơn giản |
| Gradle force/strict | `enforcedPlatform`, `strictly`, `force` | Có thể override/khóa version quá mức |
| Gradle version catalog | `libs.versions.toml` aliases | Catalog không tự ràng buộc toàn graph |
| Lockfiles | Resolved versions đã khóa | BOM update không chắc đổi runtime nếu chưa refresh locks |

### 9.1. Maven và Gradle plugin có luật BOM order khác nhau

Trong Maven, một entry được khai báo trực tiếp trong dependencyManagement của project có ưu tiên đối với imported management. Khi **hai BOM import** quản lý trùng tọa độ, Maven dùng thứ tự import theo luật riêng (BOM xuất hiện trước thường thắng trong trường hợp xung đột).

Trong Gradle **io.spring.dependency-management plugin**, các BOM được xử lý theo thứ tự import và dependency management của **BOM cuối** có thể thắng cho cùng module. **Gradle native platform** dùng version constraints/conflict resolution nên không thể suy “BOM cuối thắng”.

Đây là lý do không copy nguyên thứ tự `mavenBom(...)` từ một project Gradle sang Maven rồi tin hành vi y hệt.

### 9.2. BOM của Spring Security và Spring Framework

Khi dùng Spring Boot, ưu tiên để Boot BOM kiểm soát. Chỉ import `spring-security-bom` riêng nếu có **lý do rõ**, phiên bản đã xác nhận tương thích và hiểu precedence. Một cấu hình Boot 3.5.x + Security 7.x không phải cách vá tự động; Security 7.x có thể cần Spring Framework 7.x.

Khi cần override một bản vá Security 6.5.x, hãy rà toàn bộ các module liên quan (core/config/web/test/oauth2) và thư viện nền, không chỉ `spring-security-web`. Thời điểm tốt để bỏ override là khi Boot release mới đã quản lý bản fix.

## 10. Đọc Maven dependency tree, effective POM

Bắt đầu bằng:

```bash
./mvnw help:effective-pom -Doutput=effective-pom.xml
./mvnw dependency:tree -Dincludes=org.springframework.security
./mvnw dependency:tree -Dincludes=org.springframework
./mvnw dependency:tree -Dscope=test
./mvnw help:evaluate -Dexpression=spring-security.version -q -DforceStdout
```

Đọc để biết:

- `effective-pom.xml` đã import đúng BOM và parent chưa?
- Có property override hoặc direct `dependencyManagement` entry nào không?
- Có thêm corporate parent hoặc Maven profile thay đổi version không?
- `spring-security-core`, `config`, `web`, `test` cuối cùng là các version nào?
- `spring-core`, `spring-web`, Jackson, Logback đã lệch curated set không?
- Có plugin/compiler versions khác giữa laptop và CI không?

**Lưu ý:** việc `help:evaluate` in một property nào đó chưa chứng minh classpath đang dùng bản đó. Khi chỉ import BOM, project property có thể không tác động tới imported BOM như cách kế thừa parent. `dependency:tree` mới cho thấy resolution.

Ví dụ tree rút gọn **minh họa**, không phải output thực tế nguyên văn:

```text
spring-boot-starter-security:3.5.16
  +-- spring-security-config:6.5.11
  +-- spring-security-web:6.5.11
  +-- spring-security-core:6.5.11
spring-security-test:6.5.11 [test]
```

Mục đích là so version **cả family**, không phụ thuộc thứ tự cây hay indentation của một bản Maven plugin cụ thể.

### Quy tắc Maven nearest definition

Trong Maven, transitive conflict thường dùng “nearest definition”; cùng độ sâu có thể dùng thứ tự khai báo. `dependencyManagement` bổ sung quy tắc quản lý version và direct declared version có ưu tiên riêng. Đừng suy Maven mediation cho Gradle native resolution, vì hai công cụ có cơ chế khác nhau.

## 11. Đọc Gradle dependencies và dependencyInsight

```bash
# Xem đồ thị runtime:
./gradlew dependencies --configuration runtimeClasspath

# Điều tra một module cụ thể:
./gradlew dependencyInsight \
  --dependency spring-security-web \
  --configuration runtimeClasspath

# Test version riêng:
./gradlew dependencyInsight \
  --dependency spring-security-test \
  --configuration testRuntimeClasspath

# Kiểm tra thư viện nền:
./gradlew dependencyInsight \
  --dependency spring-core \
  --configuration runtimeClasspath
```

`dependencyInsight` giúp thấy **requested version**, **selected version**, lý do chọn (constraint/conflict/force/strict tùy Gradle version) và đường dependency kéo module vào. Nếu `build.gradle` yêu cầu `6.4.x` nhưng graph cuối dùng `6.5.x`, đừng ghi báo cáo “đã downgrade” chỉ vì đọc khai báo; kiểm tra selected version.

`runtimeClasspath` và `testRuntimeClasspath` có thể khác nhau. Một `spring-security-test` lệch major/minor có thể làm test fail hoặc che compatibility issue. Không coi test pass với mocked principal là bằng chứng đầy đủ về authentication JWT/session runtime.

## 12. Demo Spring Boot Java 17 dùng được với các cấu hình build trên

Dùng một bộ source cho Maven hoặc **một** Gradle variant đã chọn:

```text
bom-security-demo/
  pom.xml                 # Khi dùng Maven
  build.gradle            # Khi dùng Gradle, chọn cách A hoặc B
  settings.gradle
  src/main/java/com/example/bomdemo/
      BomDemoApplication.java
      SecurityConfig.java
      PingController.java
  src/test/java/com/example/bomdemo/
      SecuritySmokeTest.java
```

### `BomDemoApplication.java`

```java
package com.example.bomdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BomDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(BomDemoApplication.class, args);
    }
}
```

### `SecurityConfig.java`

```java
package com.example.bomdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/ping")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
```

### `PingController.java`

```java
package com.example.bomdemo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {
    @GetMapping("/api/ping")
    public String ping() {
        return "pong";
    }
}
```

### `SecuritySmokeTest.java`

```java
package com.example.bomdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecuritySmokeTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousIsRejected() throws Exception {
        mvc.perform(get("/api/ping"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedGetsPong() throws Exception {
        mvc.perform(get("/api/ping")
                .with(user("learner").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }
}
```

Chạy khi có Maven wrapper:

```bash
./mvnw clean test
./mvnw package
./mvnw spring-boot:run
```

Hoặc Gradle wrapper:

```bash
./gradlew clean test
./gradlew bootJar
./gradlew bootRun
```

Nếu project chưa có wrapper, cần Maven/Gradle tương thích hoặc tạo wrapper theo quy định. Mã Java cần classpath do build tool cấp; không thể `javac` từng file rồi chạy độc lập mà thiếu Spring dependencies.

**Kết quả test:** anonymous GET `/api/ping` bị HTTP Basic entry point trả 401; request có `with(user(...))` trả 200 và body chính xác `pong`. Đây là body HTTP, **không phải stdout của `java`**. Test dùng principal giả để kiểm tra Spring Security chain; nó không kiểm tra user/password database thực. Với app local chưa có UserDetailsService riêng, Boot có thể tạo generated user/password; không dùng cơ chế user mặc định như authentication production.

## 13. Khi phát hiện CVE: nâng Boot trước hay override?

Quy trình đề xuất:

1. Xác minh **artifact/group/version** bị ảnh hưởng, advisory, exploit conditions; scanner không phải lúc nào cũng đúng về runtime applicability.
2. Xác định đường transitive bằng `dependency:tree` hoặc `dependencyInsight`.
3. Kiểm tra **Boot patch release được hỗ trợ** đã nâng artifact này chưa. Nếu có, ưu tiên nâng parent/plugin/BOM.
4. Nếu Boot chưa có fix và mức độ rủi ro yêu cầu xử lý gấp, chọn **targeted override** có compatibility review và giới hạn phạm vi.
5. Với Spring Security, xét **bộ module cùng họ**, không chỉ một artifact; với Framework, xét baseline được Boot hỗ trợ.
6. Chạy compile, unit/integration tests, MockMvc filter chain, authentication/authorization, CSRF, sessions, OAuth2/JWT nếu ứng dụng dùng.
7. Kiểm tra selected dependencies và **artifact/JAR/container image**, tạo SBOM, quét lại CVE thực tế.
8. Lưu owner, lý do, ngày hết hạn và đường rollback.
9. Khi bản Boot BOM mới đã tích hợp bản vá, **xóa override tạm**, kiểm tra lại graph và tests.

Ví dụ biên bản:

```text
Dependency: org.springframework.security:spring-security-web
Baseline: Spring Boot BOM của ứng dụng
Finding: advisory chính thức, mô tả điều kiện áp dụng
Decision: nâng Boot patch hoặc override family đã được review
Evidence: dependency tree + MockMvc + runtime test + SBOM
Owner/Expiry: người duyệt, ngày phải xóa override
```

Không nên tuyên bố “Security 7.x luôn tốt hơn Security 6.5.x” nếu Boot/Framework của project chưa sẵn sàng cho major upgrade. Và cũng không giữ mãi một override khi Boot BOM đã quản lý cùng phiên bản fix.

## 14. Nhiều BOM, dự án nhiều module và lockfile

Trong project thực, ngoài Boot BOM còn có Spring Cloud, Testcontainers, Jackson, Netty, SDK bên ngoài hoặc corporate BOM. Một module có thể được **nhiều BOM cùng quản lý**. Luôn xem compatibility matrix của BOM khác (đặc biệt Spring Cloud release train với Boot) và resolution rules của build tool.

### Maven multi-module

- Parent quản lý `dependencyManagement`; child cần **kế thừa parent** chứ không chỉ nằm trong `<modules>`.
- Child khai báo dependency được sử dụng, tránh pin version trái parent.
- Aggregator có `<modules>` không tự khiến child inherit BOM nếu child không khai báo `<parent>`.
- Không để module A dùng Security 6.4, module B dùng 6.5 rồi đóng gói chung mà không review.

### Gradle multi-project

- Có thể dùng convention plugin/version catalog để chia sẻ plugin version, dependency declarations.
- `libs.versions.toml` là danh mục aliases/versions được yêu cầu, **không thay thế việc resolve BOM constraints**.
- Mỗi subproject cần platform/dependency-management đúng với configurations nó dùng.
- `dependencyInsight` cho `:api` và `:security-config` riêng biệt nếu cần, không chỉ root.

### Dependency locking

Gradle dependency locking giữ những version đã chọn cho configs được khóa, hữu ích để tái lập release nhưng **không tự cập nhật bản vá**.

```groovy
dependencyLocking {
    lockAllConfigurations()
}
```

Với cấu hình locking được bật:

```bash
./gradlew dependencies --configuration runtimeClasspath --write-locks
./gradlew dependencies --configuration testRuntimeClasspath --write-locks
```

Commit/review lockfiles theo policy; khi nâng BOM phải cập nhật locks và kiểm tra chúng không giữ phiên bản dễ bị tổn thương. `platform` không phải lockfile; `enforcedPlatform` cũng không thay thế supply-chain verification.

## 15. Supply chain, reproducibility và release gate

BOM giúp đồng bộ dependencies, nhưng không tự bảo đảm:

- Wrapper Maven/Gradle cùng version ở laptop/CI.
- JDK/toolchain đúng release; Boot 3.5.16 yêu cầu Java 17+ và Gradle/Maven trong phạm vi được hỗ trợ.
- Repository đáng tin; hạn chế dynamic versions, snapshots/milestones nếu không có quy trình.
- Hash/signature/dependency verification để phát hiện artifact không đúng nguồn.
- SBOM/SCA scanning trên artifact thực và runtime classpath.
- Quyền dữ liệu, authentication và CSRF code đúng.
- Gradle lockfiles đồng bộ với BOM.
- Không có một BOM import khác ghi đè version.
- Không có một `resolutionStrategy.force(...)` từ plugin corporate làm selected version khác mong đợi.

### CI pipeline minh họa

```text
Build tool wrapper + approved JDK
    |
    v
Resolve managed dependencies
    |
    v
Check effective POM / dependencyInsight / locking
    |
    v
Compile + unit + Spring Security integration tests
    |
    v
Package JAR/container + generate SBOM
    |
    v
Dependency vulnerability/licensing checks
    |
    v
Staging smoke tests + approval
    |
    v
Deploy đúng artifact digest đã kiểm thử
```

Không xây lại artifact production từ một POM/Gradle graph đã thay đổi sau khi staging pass. Version BOM trong Git là một phần của release provenance, nhưng cần ghi cả resolved dependency graph/artifact digest.

## 16. Chẩn đoán lỗi thường gặp

| Triệu chứng | Khả năng nguyên nhân | Cách xác minh |
| --- | --- | --- |
| Maven báo missing dependency version | Không inherit Boot parent, BOM import thiếu hoặc child không nhận parent | `help:effective-pom` |
| Version property Maven không có hiệu lực | Đang import BOM thay vì inherit parent | Xem dependencyManagement/override entry |
| Gradle ext property không đổi classpath | Dùng native platform thay plugin dependency-management | `dependencyInsight` |
| Build compile pass nhưng runtime `NoSuchMethodError` | Runtime jars lệch bản, API binary không tương thích | Inspect runtimeClasspath và tree |
| Test `spring-security-test` lỗi API | Test module lệch core/web/config | Inspect testRuntimeClasspath |
| Nâng Boot plugin nhưng thư viện vẫn cũ | Gradle lockfile, explicit version, BOM khác hoặc force | `dependencyInsight` và locks |
| Maven/Gradle cho version khác nhau | Management semantics, plugin, profile/repository khác | So sánh resolved graphs |
| CVE còn trong image sau PR fix | Build artifact cũ, transitive dependency chưa nâng | SBOM và artifact digest |
| Spring Security major update làm startup fail | Boot/Framework baseline không tương thích | Migration guide, revert và test lại |
| Một path filter khác hành vi sau bump | Security fix thay rule/ordering, matcher config không phù hợp | MockMvc full chain + live HTTP tests |

**Phân biệt lỗi build và lỗi runtime:** compile phát hiện một số API mismatch; linkage errors như `NoSuchMethodError` chỉ xuất hiện khi JVM đi vào nhánh code liên quan. Một unit test có `@WithMockUser` pass không chứng minh toàn bộ runtime authentication pipeline hoạt động với IdP/JWT.

## 17. Các lỗi quản lý phiên bản cần tránh

1. Pin version riêng cho mọi Spring Boot starter dù đã có BOM.
2. Nghĩ import BOM tự thêm Spring Security vào classpath.
3. Nghĩ Maven `dependencyManagement` tự quản lý Maven plugin versions.
4. Nhầm property override của **Maven parent** với **Maven imported BOM**.
5. Dùng `ext['spring-security.version']` với **native Gradle platform** và tin rằng BOM đổi.
6. Dùng đồng thời nhiều cách Gradle management mà không biết bên nào quyết định.
7. Nhập Spring Security BOM major khác Boot baseline.
8. Chỉ override `spring-security-web`, không kiểm tra `core`/`config`/`test`.
9. Bỏ qua Maven BOM import order hoặc Gradle plugin BOM import order.
10. Tin số khai báo trong build file thay vì resolved versions.
11. Không kiểm tra testRuntimeClasspath, Gradle lockfile, corporate plugins.
12. Ép `enforcedPlatform`/`force` rộng để làm hết warning.
13. Upgrade major chỉ vì “phiên bản mới hơn” mà không đọc migration guide.
14. Không có regression tests cho authn/authz, CSRF, JWT, filter chains.
15. Không có owner/expiry cho override để lại từ lần vá CVE.
16. Chỉ chạy static scan source, không kiểm tra JAR/image thực tế.
17. Không pin Maven/Gradle wrapper, JDK và repositories.
18. Tưởng BOM thay thế toàn bộ security review hoặc configuration testing.

## 18. Checklist hoàn thành trước merge

- [ ] Xác nhận Spring Boot version, JDK, Maven/Gradle wrapper và support status.
- [ ] Chỉ rõ project dùng Maven parent/import BOM hay Gradle plugin/native platform.
- [ ] Dùng đúng BOM ứng với Boot release.
- [ ] Các starters/modules được BOM quản lý không có pin version không cần thiết.
- [ ] Đã xem `spring-security.version` và `spring-framework.version` nếu có override.
- [ ] Không trộn Security major và Framework major không tương thích với Boot.
- [ ] Đã kiểm tra multiple BOM precedence.
- [ ] Maven: `effective-pom` và `dependency:tree` đúng.
- [ ] Gradle: `dependencies`/`dependencyInsight` đúng cho runtime/test.
- [ ] Các Spring Security modules core/web/config/test/OAuth2 có version nhất quán.
- [ ] Lockfiles và constraints không giữ version lỗi thời.
- [ ] Unit + MockMvc + integration security tests pass.
- [ ] Có SBOM, dependency scanning và artifact provenance.
- [ ] Mọi override có lý do, owner, ngày review/hết hạn và rollback.
- [ ] Khi BOM mới có bản fix, đã xóa override không còn cần thiết.

### Câu hỏi tự kiểm tra

1. BOM khác starter như thế nào?
2. Vì sao `spring-boot-starter-security` không cần version trong project có Boot BOM?
3. Maven `spring-boot-starter-parent` cung cấp thêm gì ngoài dependency management?
4. Vì sao project import BOM không nên mặc nhiên override bằng `<spring-security.version>`?
5. Có thể dùng lệnh nào để xem actual Spring Security modules trong Maven?
6. `platform(...)` khác `enforcedPlatform(...)`?
7. Gradle dependency-management plugin và native platform có sử dụng `ext['spring-security.version']` giống nhau không?
8. Khi có nhiều BOM, Maven import order và Gradle dependency-management plugin import order có đồng nhất không?
9. Vì sao không nên ghép Security 7.x vào Boot 3.5.x chỉ vì mới hơn?
10. Làm sao biết một direct version bị Gradle conflict resolution đổi thành version khác?
11. Vì sao testRuntimeClasspath cũng cần được rà soát?
12. Khi Boot BOM đã mang bản vá, làm gì với override tạm?
13. Lockfile và BOM khác nhau như thế nào?
14. Vì sao SBOM/artifact scan vẫn cần dù dependency tree đã được review?

**Gợi ý:** (1) BOM quản lý version, starter kéo dependencies; (2) management cung cấp version; (3) compiler/plugin defaults; (4) imported BOM có property isolation, dùng dependencyManagement; (5) `dependency:tree`; (6) recommendation vs strict enforcement; (7) không; (8) không; (9) compatibility/breaking changes; (10) `dependencyInsight`; (11) test modules cũng phải đồng bộ; (12) xóa override và chạy lại tests; (13) lock ghi resolved versions cụ thể; (14) binary artifact có thể khác dự kiến.

## 19. Tài liệu chính thức

- Spring Boot 3.5 Maven Plugin — parent và import BOM: https://docs.spring.io/spring-boot/3.5/maven-plugin/using.html
- Spring Boot 3.5 Gradle Plugin — Managing Dependencies: https://docs.spring.io/spring-boot/3.5/gradle-plugin/managing-dependencies.html
- Spring Boot 3.5 Managed Dependency Coordinates: https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html
- Spring Boot 3.5 Version Properties: https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/properties.html
- Spring Boot 3.5 System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- Spring Security — Getting Spring Security: https://docs.spring.io/spring-security/reference/getting-spring-security.html
- Maven — Introduction to the Dependency Mechanism: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Gradle — Platforms/BOM Import: https://docs.gradle.org/current/userguide/platforms.html
- Gradle — Viewing and Debugging Dependencies: https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html
- Gradle — Dependency Locking: https://docs.gradle.org/current/userguide/dependency_locking.html
- Spring Gradle Dependency Management Plugin: https://docs.spring.io/dependency-management-plugin/docs/current/reference/html/

**Ghi nhớ:** BOM giúp bắt đầu từ một tập dependency **được kiểm thử chung**, nhưng không thể thay thế bước kiểm chứng **phiên bản được resolver chọn**, kiểm thử tích hợp và quản lý override. Khi phát hiện lỗi hoặc CVE, ưu tiên **nâng Boot BOM thích hợp**; chỉ override có phạm vi, bằng chứng, review và kế hoạch xóa.

# BOM và quản lý phiên bản thư viện theo dòng Spring Boot tương thích

## 1. Vấn đề: một starter phải tương thích với cả hệ sinh thái dependency

Một custom starter thường kết nối nhiều thành phần: Spring Boot auto-configuration, Spring Framework, thư viện lõi của nhà cung cấp và một số dependency bên thứ ba. Nếu mỗi module tự chọn version độc lập, ứng dụng tiêu thụ có thể gặp:

- Hai module Spring Boot ở các version khác nhau.
- Spring Framework module không cùng release line mà Spring Boot đã kiểm thử.
- Thư viện runtime bị nâng lên version không tương thích với API mà auto-configuration đang gọi.
- Dependency graph có nhiều version của cùng một thư viện.
- Ứng dụng nâng Spring Boot nhưng starter vẫn kéo một bộ dependency cũ.

**Bill of Materials (BOM)** giúp quản lý tập version có liên quan như một bộ đã được phối hợp. Spring Boot phát hành BOM `spring-boot-dependencies`, chứa danh sách dependency được tuyển chọn và kiểm thử cho từng release. Khi ứng dụng nâng Spring Boot và dùng đúng BOM của release đó, các dependency được quản lý sẽ chuyển sang bộ version tương ứng.

Bài này dùng **Spring Boot 3.3.13 và Java 17** làm baseline minh họa để các đoạn Maven/Gradle có version cụ thể, dễ tái lập. Đây là ví dụ về cách căn chỉnh release line, không phải tuyên bố rằng mọi dự án mới ở thời điểm hiện tại nên chọn 3.3.13. Khi triển khai thật, hãy chọn release line còn được tổ chức hỗ trợ, đọc system requirements và compatibility matrix của thư viện đang dùng.

## 2. BOM là gì và nó giải quyết điều gì?

BOM là một POM có:

~~~xml
<packaging>pom</packaging>
~~~

và thường chứa một khối:

~~~xml
<dependencyManagement>
    <dependencies>
        <!-- Các dependency và version được quản lý tại đây -->
    </dependencies>
</dependencyManagement>
~~~

BOM mô tả **version nên dùng cho một nhóm artifact**. Ví dụ, BOM Spring Boot quản lý version của các module Spring, logging, JSON, database drivers và nhiều thư viện bên thứ ba.

Khi một dependency nằm trong BOM, dự án có thể khai báo tọa độ mà không phải lặp version:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

Nếu dependency management đang quản lý artifact này, Maven sẽ lấy version được quản lý.

### 2.1. BOM quản lý version, không tự thêm dependency

Đây là điểm cần nhớ:

- `dependencyManagement` nói rằng **nếu dự án khai báo dependency này**, version mặc định/được quản lý là gì.
- `dependencies` mới thực sự **thêm dependency** vào project.
- Import BOM không tự đưa mọi thư viện trong BOM lên classpath.
- BOM cũng không tự tạo bean, không cấu hình auto-configuration và không thay thế việc kiểm thử runtime.

Ví dụ:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.13</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đoạn này chỉ nhập bảng version. Muốn dùng MVC, ứng dụng vẫn phải khai báo:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

### 2.2. BOM không phải lockfile

BOM là tập version được quản lý/khuyến nghị. Kết quả dependency graph cuối cùng vẫn có thể bị ảnh hưởng bởi:

- Version được khai báo trực tiếp ở dependency.
- Dependency management của project/parent hoặc BOM khác.
- Dependency mediation và các constraint của build tool.
- Resolution strategy của Gradle.
- Các rule/platform do tổ chức áp dụng.

Do đó, import BOM chưa đủ để chứng minh runtime classpath đã đồng nhất. Sau khi cấu hình, cần xem dependency tree hoặc dependency insight.

## 3. Chọn đúng dòng Spring Boot tương thích

Một release Spring Boot đi kèm một bộ dependency được phối hợp, bao gồm cả version Spring Framework nền tảng. Vì vậy, không nên tự chọn riêng version `spring-core`, `spring-context`, `spring-web` hoặc `spring-boot-autoconfigure` chỉ vì thấy một bản mới hơn.

### 3.1. Chọn một release line trước khi chọn dependency

Khi phát triển custom starter, cần xác định:

1. Thư viện hỗ trợ Spring Boot major/minor line nào?
2. Java baseline tối thiểu là bao nhiêu?
3. Spring Framework generation nào được hỗ trợ?
4. Starter dùng namespace API nào, ví dụ `javax.*` hay `jakarta.*`?
5. Các dependency bên thứ ba nào được BOM của Boot quản lý?
6. Những version nào đã được build và test trong CI?

Boot major line có thể kéo theo thay đổi lớn về Java baseline, Spring Framework và Jakarta namespace. Ví dụ, ứng dụng Boot 3 dùng Java 17+ và hệ sinh thái Spring Framework 6/Jakarta; không thể lấy một module được build cho Boot 2/Framework 5 rồi giả định nó tương thích chỉ vì tên class giống nhau.

Không chọn version chỉ bằng cách nhìn một số version trên Maven Central. Hãy đọc tài liệu system requirements, upgrade guide và release notes của đúng Boot line.

### 3.2. Dùng version BOM cùng release với Spring Boot

Với baseline minh họa này:

~~~text
Spring Boot release: 3.3.13
BOM: org.springframework.boot:spring-boot-dependencies:3.3.13
Maven plugin: org.springframework.boot:spring-boot-maven-plugin:3.3.13
Gradle plugin: org.springframework.boot:org.springframework.boot.gradle.plugin:3.3.13
~~~

Các module Boot như `spring-boot`, `spring-boot-autoconfigure`, `spring-boot-starter` nên đi cùng release line và patch version do BOM quản lý. Không trộn tùy tiện, ví dụ:

~~~text
spring-boot                 3.3.13
spring-boot-autoconfigure   3.4.0
spring-boot-starter         3.2.12
~~~

Bộ version như trên có thể gây lệch API, classpath hoặc hành vi runtime. Nếu muốn nâng một module Spring Boot riêng lẻ, trước hết cần có lý do tương thích được xác minh, không dùng override ngẫu nhiên để xử lý một lỗi chưa hiểu rõ.

### 3.3. Version thư viện Acme không bắt buộc giống version Spring Boot

Giả sử nhà cung cấp có:

~~~text
com.acme:acme-report-core:1.4.0
com.acme:acme-spring-boot-autoconfigure:1.4.0
com.acme:acme-spring-boot-starter:1.4.0
com.acme:acme-spring-boot-bom:1.4.0
~~~

Version `1.4.0` là version của thư viện Acme. Nó không phải version Spring Boot. BOM Acme có thể công bố rằng release Acme 1.4.0 đã được kiểm thử với Spring Boot 3.3.x, ví dụ 3.3.13.

Một thư viện có thể chọn một trong các chính sách:

- **Một release library cho một Boot line:** dễ kiểm soát dependency baseline, đổi release khi chuyển Boot line.
- **Một release library hỗ trợ nhiều Boot line:** chỉ công bố nếu CI thực sự build/test trên từng line và API/bytecode tương thích.
- **Tách BOM theo Boot line:** hữu ích khi các dependency hoặc module cần version khác nhau theo Boot line.

Điều quan trọng là **công bố rõ ma trận tương thích**. Không để người dùng suy luận từ việc version Acme tình cờ gần giống version Boot.

## 4. Maven: dùng spring-boot-starter-parent hay import BOM?

Maven có hai cách thường dùng để nhận dependency management của Spring Boot.

### 4.1. Cách A — kế thừa spring-boot-starter-parent

Đây là cách đơn giản cho một ứng dụng Spring Boot thông thường:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>sample-application</artifactId>
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
~~~

Parent này cung cấp nhiều mặc định hữu ích ngoài dependency management, bao gồm plugin management và cấu hình build Maven theo quy ước Spring Boot. Vì vậy ứng dụng có thể khai báo dependency được quản lý mà không ghi version từng dòng.

### 4.2. Cách B — import spring-boot-dependencies BOM

Nếu tổ chức đã có parent POM riêng hoặc không muốn kế thừa Spring Boot parent, có thể import BOM:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>sample-application</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <spring-boot.version>3.3.13</spring-boot.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-dependencies</artifactId>
                <version>\${spring-boot.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
                <version>\${spring-boot.version}</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Ở đây, BOM quản lý version dependency nhưng **không cung cấp toàn bộ cấu hình build mà parent POM cung cấp**. Khi không dùng `spring-boot-starter-parent`, dự án cần tự quản lý plugin version, compiler settings, encoding và những cấu hình Maven khác mà nó cần.

### 4.3. So sánh hai cách

| Tiêu chí | Kế thừa Spring Boot parent | Import Spring Boot BOM |
| --- | --- | --- |
| Quản lý version dependency | Có | Có |
| Plugin management mặc định của Boot | Có | Không tự kế thừa |
| Dễ dùng với parent POM công ty | Không thể có hai parent trực tiếp | Phù hợp |
| Tùy biến build Maven | Kế thừa rồi override khi cần | Tự kiểm soát rõ hơn |
| Phù hợp với | Ứng dụng đơn giản, không cần parent khác | Tổ chức có parent riêng, thư viện hoặc build nhiều module |

**Không được khai báo Spring Boot BOM như một dependency runtime thông thường.** BOM được import trong `dependencyManagement` với `type=pom` và `scope=import`.

### 4.4. Version được quản lý có thể bị override

Ví dụ, BOM đang quản lý Jackson nhưng project ghi version riêng:

~~~xml
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
    <version>2.x.y</version>
</dependency>
~~~

Version được khai báo trực tiếp có thể override version BOM. Đây là hành động có chủ đích nhưng cần kiểm tra tương thích. Không nên override version chỉ để làm dependency tree trông mới hơn; Spring Boot release được kiểm thử với một tập dependency cụ thể.

## 5. Thiết kế custom starter và custom BOM

Một custom starter thường được tách thành các module để quản lý rõ ràng code auto-configuration, thư viện runtime và dependency mà ứng dụng cần.

### 5.1. Cấu trúc module gợi ý

~~~text
acme-report/
├── acme-report-core/
│   └── API và implementation nghiệp vụ
├── acme-spring-boot-autoconfigure/
│   ├── @AutoConfiguration
│   ├── @ConfigurationProperties
│   └── AutoConfiguration.imports
├── acme-spring-boot-starter/
│   └── dependency descriptor cho người dùng
└── acme-spring-boot-bom/
    └── BOM quản lý version các module Acme và Boot
~~~

Vai trò:

- **core:** chứa API/implementation không nhất thiết phụ thuộc Spring Boot.
- **autoconfigure:** chứa class auto-configuration, properties và tích hợp Spring Boot.
- **starter:** gom dependency cần thiết để người dùng chỉ cần thêm một dependency.
- **bom:** quản lý version của các module Acme và, nếu chính sách yêu cầu, import BOM Spring Boot tương thích.

Spring Boot khuyến nghị starter bên thứ ba không dùng tên bắt đầu bằng `spring-boot`; nên đặt tên theo sản phẩm, ví dụ `acme-spring-boot-starter`. Module auto-configuration và starter có thể tách riêng hoặc gộp nếu tính năng đủ đơn giản.

### 5.2. Module autoconfigure dùng Boot BOM để căn chỉnh dependency

Một phần POM của module auto-configuration có thể như sau:

~~~xml
<properties>
    <spring-boot.version>3.3.13</spring-boot.version>
    <acme.version>1.4.0</acme.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>\${spring-boot.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-autoconfigure</artifactId>
    </dependency>

    <dependency>
        <groupId>com.acme</groupId>
        <artifactId>acme-report-core</artifactId>
        <version>\${acme.version}</version>
    </dependency>
</dependencies>
~~~

POM trên là phần dependency quan trọng, có thể đặt trong module Maven riêng. Boot BOM quản lý version `spring-boot-autoconfigure`; version Acme core do release của Acme quản lý.

Nếu auto-configuration tích hợp với một thư viện bên thứ ba tùy chọn, cần cân nhắc khai báo dependency đó là optional và đặt condition theo classpath. Starter sau đó mới quyết định có đưa dependency tùy chọn đó vào bộ mặc định hay không.

### 5.3. Starter module chỉ gom dependency cần thiết

POM rút gọn của starter:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.acme</groupId>
        <artifactId>acme-spring-boot-autoconfigure</artifactId>
        <version>1.4.0</version>
    </dependency>

    <dependency>
        <groupId>com.acme</groupId>
        <artifactId>acme-report-core</artifactId>
        <version>1.4.0</version>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
</dependencies>
~~~

Đây là ví dụ cấu trúc. Trong project thật, có thể dùng parent/BOM nội bộ để quản lý version module Acme thay vì lặp `1.4.0`. Starter nên chứa những dependency cần thiết cho trường hợp sử dụng thông thường; không đưa mọi integration tùy chọn vào chỉ vì chúng có thể hữu ích.

### 5.4. Tạo BOM riêng cho các artifact Acme

BOM của Acme giúp ứng dụng tiêu thụ các module cùng một release:

**acme-spring-boot-bom/pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.acme</groupId>
    <artifactId>acme-spring-boot-bom</artifactId>
    <version>1.4.0</version>
    <packaging>pom</packaging>

    <properties>
        <spring-boot.version>3.3.13</spring-boot.version>
        <acme.version>1.4.0</acme.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-dependencies</artifactId>
                <version>\${spring-boot.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>

            <dependency>
                <groupId>com.acme</groupId>
                <artifactId>acme-report-core</artifactId>
                <version>\${acme.version}</version>
            </dependency>

            <dependency>
                <groupId>com.acme</groupId>
                <artifactId>acme-spring-boot-autoconfigure</artifactId>
                <version>\${acme.version}</version>
            </dependency>

            <dependency>
                <groupId>com.acme</groupId>
                <artifactId>acme-spring-boot-starter</artifactId>
                <version>\${acme.version}</version>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
~~~

BOM này quản lý version các module Acme và import luôn Spring Boot BOM 3.3.13. Vì vậy nó **có chủ đích gắn release BOM Acme 1.4.0 với Boot 3.3.13/3.3.x**. Khi import BOM này, consumer có một bộ version được phối hợp cho các artifact mà BOM quản lý.

Nếu Acme muốn hỗ trợ một Boot line khác có dependency baseline khác, cần phát hành BOM hoặc cấu hình tương thích tương ứng và test riêng. Không thay version Boot trong BOM cũ mà không đánh giá lại toàn bộ dependency graph.

### 5.5. Ứng dụng tiêu thụ custom BOM

Trong POM của ứng dụng:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-spring-boot-bom</artifactId>
            <version>1.4.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.acme</groupId>
        <artifactId>acme-spring-boot-starter</artifactId>
    </dependency>
</dependencies>
~~~

Ứng dụng không phải lặp version cho starter. BOM Acme quản lý version module Acme và, trong ví dụ này, cung cấp dependency management từ Boot BOM đã import.

**Lưu ý về Maven:** dependency management không tự truyền một cách vô hạn qua mọi dependency graph. Khi một ứng dụng import BOM, nó nhận dependency management từ BOM đó theo cơ chế import. Khi một library chỉ dùng BOM trong build riêng của nó, không nên mặc định rằng mọi ứng dụng tiêu thụ sẽ tự kế thừa toàn bộ dependency management của library. Hãy kiểm tra POM đã publish và dependency graph của consumer; nếu muốn cung cấp một bộ version cho consumer, hãy publish một BOM có chủ đích và hướng dẫn import nó.

## 6. Gradle: dùng BOM bằng platform

Gradle hỗ trợ BOM thông qua `platform()` và `enforcedPlatform()`. Spring Boot cũng có thể dùng plugin `io.spring.dependency-management`.

### 6.1. Cách A — Spring Dependency Management plugin

Khi dùng Spring Boot Gradle plugin cùng dependency management plugin:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Khi plugin dependency management được áp dụng, Spring Boot Gradle plugin tự import `spring-boot-dependencies` BOM cùng version của plugin. Vì vậy có thể bỏ version ở dependency được quản lý.

Cách này quen thuộc với người dùng Maven vì cho phép tùy chỉnh version qua các property mà BOM hỗ trợ, tùy plugin và cấu hình.

### 6.2. Cách B — Gradle native BOM support

Gradle cũng có thể dùng platform trực tiếp:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')

    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Với cách này, `platform(...)` nhập constraints từ BOM vào configuration liên quan. Đây là lựa chọn native của Gradle, không cần plugin dependency management để đọc BOM.

### 6.3. platform và enforcedPlatform khác nhau

| Cách khai báo | Ý nghĩa |
| --- | --- |
| `platform("...")` | Đưa các version constraint từ BOM vào dependency resolution; Gradle vẫn xét các constraint khác trong graph |
| `enforcedPlatform("...")` | Ép version từ BOM thành yêu cầu nghiêm ngặt, override version khác trong graph |

Ví dụ:

~~~groovy
dependencies {
    implementation enforcedPlatform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
}
~~~

Dùng `enforcedPlatform` khi thực sự muốn buộc toàn bộ graph tuân theo version trong BOM và hiểu tác động tới dependency khác. Với thư viện được publish để nhiều ứng dụng tiêu thụ, việc phát tán constraint cưỡng chế có thể làm hạn chế quyền chọn version của ứng dụng. Thông thường nên cân nhắc `platform` trước; chỉ dùng `enforcedPlatform` cho chính sách kiểm soát version có chủ đích.

### 6.4. Version catalog không thay thế BOM

Gradle version catalog (`libs.versions.toml`) giúp tập trung tọa độ và alias dependency. Nó là công cụ quản lý khai báo, còn platform/BOM tham gia vào dependency resolution để đưa ra version constraints.

Có thể dùng catalog cùng BOM:

~~~toml
[versions]
spring-boot = "3.3.13"

[libraries]
spring-boot-bom = { module = "org.springframework.boot:spring-boot-dependencies", version.ref = "spring-boot" }
spring-boot-web = { module = "org.springframework.boot:spring-boot-starter-web" }
~~~

~~~groovy
dependencies {
    implementation platform(libs.spring.boot.bom)
    implementation libs.spring.boot.web
}
~~~

Catalog giúp tên dependency thống nhất; BOM giúp phối hợp version. Hai công cụ có thể bổ trợ nhau.

## 7. Quản lý version trong nhiều module và nhiều release line

### 7.1. Không để từng module tự chọn Boot version

Một multi-module project có thể có:

~~~text
acme-report-parent
  ├── acme-report-core
  ├── acme-spring-boot-autoconfigure
  ├── acme-spring-boot-starter
  └── acme-spring-boot-bom
~~~

Hãy quản lý version ở một nơi:

- Version nội bộ của Acme dùng property hoặc parent/BOM.
- Version Spring Boot dùng một property thống nhất trong build line đang kiểm thử.
- Spring Framework version lấy từ Boot BOM.
- Plugin Maven/Gradle tương thích với release line được chọn.
- Annotation processor và test dependencies cũng được căn chỉnh theo cùng release line.

Tránh để module core dùng một version Spring Boot, module auto-config dùng version khác và module test dùng version thứ ba.

### 7.2. Chính sách phát hành theo Boot line

Một ma trận tương thích cần được công bố cùng thư viện:

| Acme library/BOM | Spring Boot line được kiểm thử | Java baseline | Ghi chú |
| --- | --- | --- | --- |
| `1.4.x` | `3.3.x` | 17+ | Ví dụ chính sách cho BOM 1.4.0 |
| `1.5.x` | `3.4.x` | 17+ | Ví dụ một release line tiếp theo, chỉ công bố sau khi CI xác nhận |
| `2.x` | Boot major mới | Theo system requirements của Boot line | Có thể cần thay đổi API hoặc namespace |

Các hàng trên là **ví dụ cách tổ chức ma trận**, không phải tuyên bố về một sản phẩm Acme có thật. Khi phát hành, thay bằng những version đã được kiểm thử và cam kết hỗ trợ thực tế.

Có thể chọn các chính sách versioning:

**Một version thư viện, nhiều Boot line:** phù hợp khi source/API tương thích và CI kiểm thử tất cả line. Consumer vẫn phải chọn Boot BOM tương ứng với ứng dụng.

**Một BOM cho từng Boot line:** hữu ích khi dependency management hoặc module variant khác nhau. Có thể đặt version BOM độc lập nhưng mô tả rõ nó import Boot release nào.

**Tách major version thư viện:** phù hợp khi bỏ một Boot line cũ, nâng Java baseline hoặc thay API/namespace không tương thích. Không nhất thiết phải bump major chỉ vì Boot patch tăng; quyết định dựa trên compatibility contract của thư viện.

### 7.3. Đừng dùng version range hoặc dynamic version cho starter production

Tránh các kiểu khai báo:

~~~xml
<version>[3.3,4.0)</version>
~~~

hoặc Gradle:

~~~groovy
implementation 'org.springframework.boot:spring-boot-autoconfigure:3.+'
~~~

Các version range/dynamic version có thể khiến build hôm nay và ngày mai resolve ra kết quả khác nhau. Chúng làm giảm khả năng tái lập và khiến lỗi tương thích khó điều tra.

Với build/release production, dùng version cụ thể hoặc BOM cụ thể. Nếu muốn nhận bản patch mới, hãy nâng BOM có chủ đích, chạy CI và phát hành lại.

## 8. Những dependency nào nên để Boot BOM quản lý?

### 8.1. Spring Boot và Spring Framework

Không ghi version thủ công cho các module Spring Boot/Spring Framework đã được Boot BOM quản lý:

~~~xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-context</artifactId>
</dependency>
~~~

Không tự đặt version riêng cho `spring-core`, `spring-beans`, `spring-web` hoặc `spring-webmvc` trong một ứng dụng Boot thông thường. Các module Spring Framework có quan hệ tương thích với release Boot.

### 8.2. Thư viện bên thứ ba

BOM Boot cũng quản lý nhiều thư viện bên thứ ba như JSON, logging, database drivers và test libraries. Hãy dùng version từ BOM nếu dependency đó nằm trong danh sách được quản lý.

Nếu dependency không được Boot BOM quản lý, hãy:

1. Xác định BOM riêng của nhà cung cấp nếu có.
2. Xem compatibility matrix của thư viện đó.
3. Chọn version đã được kiểm thử cùng Boot line.
4. Quản lý version tại custom BOM của tổ chức nếu nhiều module cùng dùng.

Không giả định BOM Boot bao phủ mọi dependency trên Maven Central.

### 8.3. Spring Cloud và các release train liên quan

Nếu starter tích hợp Spring Cloud, Spring Data hoặc một hệ sinh thái có BOM riêng, phải xem compatibility matrix của chính hệ sinh thái đó. Ví dụ Spring Cloud có release train được ánh xạ với các Spring Boot line. Không chọn release train mới nhất độc lập với Boot version đang dùng.

Khi có nhiều BOM:

- Ghi rõ BOM nào quản lý nhóm artifact nào.
- Tránh hai BOM quản lý cùng một artifact với version xung đột mà không có quy tắc.
- Kiểm tra effective POM/dependency insight sau khi import.
- Chỉ override một version khi có lý do, owner và test xác nhận.

## 9. Kiểm tra dependency graph sau khi import BOM

BOM chỉ có giá trị khi kết quả resolution cuối cùng đúng như dự kiến.

### 9.1. Maven

Xem dependency tree:

~~~bash
mvn dependency:tree
~~~

Chỉ xem các module Spring:

~~~bash
mvn dependency:tree -Dverbose -Dincludes=org.springframework.boot,org.springframework
~~~

Xem POM hiệu lực:

~~~bash
mvn help:effective-pom -Doutput=target/effective-pom.xml
~~~

Kiểm tra:

- Có nhiều version của cùng artifact không?
- Version Spring Boot có cùng patch không?
- Spring Framework modules có cùng release line mà Boot BOM quản lý không?
- Dependency bị omitted for conflict là version nào và vì sao?
- Có dependency trực tiếp khai báo version override BOM không?
- Có một starter khác kéo dependency không mong muốn không?

### 9.2. Gradle

Xem runtime dependency graph:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Xem vì sao một version được chọn:

~~~bash
./gradlew dependencyInsight --dependency spring-boot-autoconfigure --configuration runtimeClasspath
~~~

Kiểm tra Spring Framework:

~~~bash
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
~~~

`dependencyInsight` cho biết dependency nào yêu cầu version, constraint nào tham gia resolution và lý do Gradle chọn version cuối cùng.

### 9.3. Maven Enforcer để phát hiện dependency convergence

Có thể thêm rule convergence trong build Maven:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-enforcer-plugin</artifactId>
            <version>3.5.0</version>
            <executions>
                <execution>
                    <id>check-dependency-convergence</id>
                    <goals>
                        <goal>enforce</goal>
                    </goals>
                    <configuration>
                        <rules>
                            <dependencyConvergence/>
                        </rules>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

Rule này có thể phát hiện trường hợp nhiều dependency path yêu cầu các version khác nhau của cùng artifact. Nó không tự giải quyết mọi xung đột và đôi khi cần xử lý ngoại lệ có chủ đích. Khi build fail, đọc dependency path trước khi thêm exclusion hoặc override.

## 10. Kiểm thử compatibility trong CI

Một thư viện chỉ nên công bố hỗ trợ Boot line mà nó đã kiểm thử. Một quy trình CI có thể:

1. Build core và auto-config với Java baseline tối thiểu.
2. Chạy unit tests cho properties, conditions và bean back-off.
3. Chạy integration tests với Spring Boot line được hỗ trợ.
4. Kiểm tra dependency graph và convergence.
5. Build/publish starter POM vào local repository hoặc staging repository.
6. Tạo một ứng dụng consumer nhỏ chỉ khai báo starter, xác nhận auto-configuration được phát hiện và chạy.
7. Lặp lại với từng Boot line trong compatibility matrix.

Nếu dùng Maven import BOM qua property:

~~~xml
<properties>
    <spring-boot.version>3.3.13</spring-boot.version>
</properties>
~~~

CI có thể truyền version đã chọn:

~~~bash
mvn -Dspring-boot.version=3.3.13 clean verify
~~~

Khi kiểm tra một line khác, dùng version BOM tương ứng và chạy lại toàn bộ tests. Không thay version dependency trong một bước mà bỏ qua test consumer.

Với Gradle, có thể tạo matrix job theo version catalog/property hoặc build parameter. Điều quan trọng là mỗi job phải thực sự resolve BOM của line đó; chỉ đổi tên job mà không thay dependency constraints không tạo ra một compatibility test mới.

### 10.1. Kiểm tra POM đã publish

Với custom starter, không chỉ test module source. Cần kiểm tra artifact đã publish:

- POM của starter có khai báo đúng dependencies không?
- Version dependency có được resolve đúng trong consumer không?
- Optional dependency có bị kéo vào ngoài ý muốn không?
- Custom BOM có quản lý đúng version của các module Acme không?
- BOM có import nhầm Boot line không?
- Một ứng dụng chỉ import BOM và khai báo starter có build được không?

POM được publish là một phần API phân phối của thư viện. Một module compile được trong reactor chưa chứng minh consumer độc lập có thể resolve đúng dependency.

## 11. Một ví dụ chiến lược phát hành hoàn chỉnh

Giả sử Acme phát hành bộ thư viện báo cáo:

~~~text
acme-report-core                  1.4.0
acme-spring-boot-autoconfigure    1.4.0
acme-spring-boot-starter          1.4.0
acme-spring-boot-bom              1.4.0
Spring Boot baseline              3.3.13
Java baseline                     17
~~~

Chính sách:

- Tất cả module Acme cùng release 1.4.0.
- Custom BOM 1.4.0 import `spring-boot-dependencies:3.3.13`.
- Module auto-config dùng `spring-boot-autoconfigure` từ Boot BOM.
- Starter gom core + auto-config + dependency tối thiểu.
- Ứng dụng tiêu thụ import BOM Acme và khai báo starter không version.
- CI kiểm thử trên Java 17 với Boot 3.3.13 và thêm các patch trong line nếu tổ chức cam kết hỗ trợ.
- Nếu muốn hỗ trợ Boot 3.4, tạo ma trận test riêng; chỉ tái sử dụng Acme 1.4.0 khi API và dependency thực sự tương thích. Nếu cần dependency baseline khác, phát hành BOM/library variant phù hợp.
- Khi nâng Boot patch, nâng BOM, kiểm tra dependency tree, chạy CI và phát hành lại theo quy trình.

Đây là cách versioning tách biệt:

~~~text
Acme release version       -> version của thư viện Acme
Spring Boot BOM version    -> release Boot mà bộ dependency tương thích
Java baseline              -> runtime/compiler tối thiểu được hỗ trợ
Compatibility matrix       -> các tổ hợp đã được kiểm thử/cam kết
~~~

Không buộc version Acme phải trùng version Boot. Điều cần thống nhất là contract tương thích được công bố và xác minh.

## 12. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Starter kéo nhiều version Spring Boot | Module tự khai báo version khác nhau hoặc BOM không được import đúng | Căn chỉnh về cùng Boot BOM và xem dependency tree |
| Spring Framework version lệch với Boot | Override spring-core/spring-context riêng | Bỏ version thủ công và để Boot BOM quản lý |
| Import BOM nhưng dependency không có trên classpath | Nhầm dependencyManagement với dependencies | Khai báo dependency thực tế trong dependencies |
| Không dùng Boot parent nên plugin không có version | BOM không quản lý plugin Maven | Khai báo plugin version/configuration rõ ràng |
| Custom starter build được nhưng consumer resolve lỗi | POM publish thiếu hoặc sai dependency/version management | Test từ project consumer độc lập và inspect POM |
| BOM Acme kéo Boot line không tương thích | BOM được publish với mapping không rõ | Gắn BOM với Boot line, công bố matrix và test |
| Dùng enforcedPlatform làm ứng dụng khác không nâng được thư viện | Constraint bị ép mạnh từ dependency | Dùng platform khi phù hợp, chỉ enforce theo chính sách rõ ràng |
| Version range làm build không tái lập | Resolver chọn version khác theo thời điểm | Pin BOM/release cụ thể |
| Import nhiều BOM tạo version khác dự kiến | Các BOM cùng quản lý artifact | Xem effective POM/dependencyInsight và xác định owner |
| Spring Cloud không tương thích Boot | Chọn release train độc lập | Dùng compatibility matrix Spring Cloud |
| Chỉ test module autoconfigure, không test starter | Chưa xác nhận artifact phân phối | Tạo consumer smoke test với starter đã publish |

## 13. Checklist trước khi phát hành custom starter

### Version policy

- [ ] Xác định Boot major/minor line được hỗ trợ.
- [ ] Xác định Java baseline và Spring Framework generation.
- [ ] Dùng Boot BOM cùng release với Boot plugin.
- [ ] Để BOM quản lý Spring Boot/Spring Framework modules.
- [ ] Không dùng version range hoặc dynamic version trong release production.
- [ ] Công bố version Acme và Boot compatibility matrix.

### Maven/Gradle

- [ ] Phân biệt parent POM, imported BOM và dependency thực tế.
- [ ] Custom BOM quản lý version các module nội bộ.
- [ ] Nếu custom BOM import Boot BOM, ghi rõ Boot line mà nó gắn với.
- [ ] Gradle platform/enforcedPlatform được chọn có chủ đích.
- [ ] Plugin version được quản lý rõ ràng, đặc biệt khi không dùng Boot parent.

### Verification

- [ ] Kiểm tra Maven dependency tree/effective POM hoặc Gradle dependencyInsight.
- [ ] Kiểm tra dependency convergence.
- [ ] Build và test trên từng Boot line đã công bố.
- [ ] Test artifact starter từ consumer độc lập.
- [ ] Kiểm tra POM/BOM đã publish và dependency scope/optional.
- [ ] Ghi lại version thực tế trong release notes.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** BOM khác `dependencies` ở điểm nào?  
**Đáp án:** BOM cung cấp dependency management/version constraints; `dependencies` mới đưa artifact vào classpath.

**Câu 2.** Vì sao nên dùng `spring-boot-dependencies` đúng release với Spring Boot đang chạy?  
**Đáp án:** Mỗi release Boot có một bộ dependency được tuyển chọn và kiểm thử. Dùng đúng BOM giúp Spring Boot, Spring Framework và third-party libraries đi cùng bộ version phù hợp.

**Câu 3.** Kế thừa `spring-boot-starter-parent` và import `spring-boot-dependencies` có giống nhau hoàn toàn không?  
**Đáp án:** Không. Cả hai cung cấp dependency management, nhưng parent còn cung cấp plugin management và nhiều build defaults; import BOM chỉ nhập dependency management.

**Câu 4.** Một custom BOM có thể quản lý version các module Acme và import Boot BOM không?  
**Đáp án:** Có. Đó là cách cung cấp một bộ version thống nhất cho consumer; cần công bố rõ BOM Acme tương thích Boot line nào.

**Câu 5.** Version Acme 1.4.0 có bắt buộc phải dùng Spring Boot 1.4.0 không?  
**Đáp án:** Không. Hai version thuộc hai sản phẩm/release train khác nhau. Acme phải công bố ma trận tương thích thay vì dựa vào số version trùng nhau.

**Câu 6.** Vì sao `enforcedPlatform` cần thận trọng khi publish thư viện Gradle?  
**Đáp án:** Nó áp đặt version constraints mạnh lên dependency graph của consumer, có thể ngăn ứng dụng chọn version phù hợp với hệ sinh thái riêng của họ.

**Câu 7.** Làm sao xác nhận version cuối cùng sau khi import BOM?  
**Đáp án:** Maven dùng `dependency:tree` và `help:effective-pom`; Gradle dùng `dependencies` và `dependencyInsight`.

**Câu 8.** Chỉ build module auto-config thành công có đủ chứng minh custom starter đã sẵn sàng phát hành không?  
**Đáp án:** Không. Phải kiểm tra POM/BOM đã publish và build một consumer độc lập chỉ dùng starter.

## 15. Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Build Systems và Dependency Management](https://docs.spring.io/spring-boot/3.3/reference/using/build-systems.html)
- [Spring Boot 3.3 — Managing Dependencies with Gradle](https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html)
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Gradle — Platforms and BOM Support](https://docs.gradle.org/current/userguide/platforms.html)
- [Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)

**Ghi nhớ:** Hãy chọn **Spring Boot release line tương thích trước**, import BOM đúng release, để BOM quản lý các module Spring và dependency liên quan, rồi quản lý version riêng của thư viện trong custom BOM. Parent POM, BOM và dependency có trách nhiệm khác nhau; Gradle `platform` và `enforcedPlatform` cũng có mức ràng buộc khác nhau. Cuối cùng, kiểm tra dependency graph và chạy CI trên từng tổ hợp Boot/Java mà thư viện cam kết hỗ trợ.

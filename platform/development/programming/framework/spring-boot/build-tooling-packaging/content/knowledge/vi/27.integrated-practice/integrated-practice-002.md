# Chuyển một dự án dùng parent riêng sang quản lý phụ thuộc bằng BOM

Một dự án Maven thường dùng **custom parent POM** để chia sẻ dependency versions, properties, cấu hình compiler, plugin, repositories và quy ước build cho nhiều module. Khi nhiều ứng dụng cần dùng chung dependency versions nhưng không muốn kế thừa toàn bộ build conventions, có thể tách phần quản lý dependencies thành **BOM (Bill of Materials)**.

BOM là một POM chuyên quản lý phiên bản dependencies thông qua **dependencyManagement**. Dự án tiêu thụ import BOM bằng dependency có **type=pom** và **scope=import** trong dependencyManagement của chính nó.

Việc chuyển đổi phải bảo toàn hành vi build hiện tại. **BOM thay thế phần quản lý dependency versions; nó không thay thế toàn bộ khả năng kế thừa của parent POM.** Nếu custom parent đang cấu hình Java compiler, plugin executions, Spring Boot packaging, repositories hoặc properties, những phần đó cần được giữ ở build parent riêng hoặc chuyển vào POM của dự án.

## 1. Parent POM và BOM giải quyết hai bài toán khác nhau

### 1.1. Parent POM: kế thừa cấu hình dự án

Một Maven project có thể khai báo một parent trực tiếp:

~~~xml
<parent>
    <groupId>com.acme.build</groupId>
    <artifactId>company-parent</artifactId>
    <version>5.2.0</version>
</parent>
~~~

Parent POM có packaging pom và có thể cung cấp nhiều loại cấu hình cho child:

- groupId, version và metadata chung.
- Properties như Java release, encoding và plugin versions.
- DependencyManagement để quản lý version/scope của project dependencies.
- Dependencies được kế thừa như dependencies thực sự của child.
- Repositories và pluginRepositories.
- Build, plugins, pluginManagement, executions và plugin configuration.
- Reporting, SCM, issue management và các cấu hình dự án khác.
- Profiles và các hiệu ứng cấu hình profile được kích hoạt theo quy tắc Maven.

Khi child kế thừa parent, Maven xây dựng effective POM từ child, parent và Super POM. Vì vậy, xóa parent có thể làm thay đổi nhiều hành vi ngoài dependency versions. [Maven POM Reference: Inheritance](https://maven.apache.org/pom.html).

### 1.2. BOM: tập trung dependency versions

Một BOM cũng là Maven POM, thường có packaging pom, nhưng mục đích chính là khai báo dependencyManagement:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
            <version>4.0.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Khi project import BOM, Maven đưa các managed dependency entries từ BOM vào dependencyManagement của project. Nhờ đó, project có thể khai báo dependency mà không cần lặp version.

**BOM không tự thêm library vào classpath.** Nó chỉ quản lý thông tin của dependency nếu dependency đó được khai báo trực tiếp hoặc xuất hiện qua dependency graph. Project vẫn cần khai báo thư viện sử dụng trong dependencies. [Maven Dependency Mechanism: BOMs](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html).

### 1.3. So sánh nhanh

| Khả năng | Parent POM | Imported BOM |
| --- | --- | --- |
| Quản lý dependency versions | Có | Có |
| Quản lý transitive dependency versions | Có, qua dependencyManagement | Có, qua imported dependencyManagement |
| Cung cấp dependencies thực sự cho child | Có thể qua dependencies kế thừa | Không |
| Kế thừa properties của POM | Có | Không |
| Kế thừa build/plugin configuration | Có | Không |
| Kế thừa pluginManagement | Có | Không |
| Kế thừa repositories/reporting | Có | Không |
| Dùng cùng một parent khác | Không, chỉ một parent trực tiếp | Có thể import nhiều BOM |
| Dùng để chuẩn hóa version cho nhiều hệ build | Maven inheritance | Maven và Gradle có thể tiêu thụ BOM |

### 1.4. Khi nào nên tách BOM?

Tách dependency management thành BOM có ích khi:

- Nhiều ứng dụng cần dùng cùng bộ Spring, Jackson, logging, test libraries hoặc internal SDK versions.
- Các ứng dụng đang dùng nhiều parent khác nhau nhưng vẫn cần đồng bộ dependencies.
- Một nhóm muốn giữ build conventions riêng mà không bắt nhóm khác kế thừa toàn bộ custom parent.
- Một thư viện nội bộ phát hành nhiều artifacts cần được dùng cùng một release train.
- Các project Gradle cũng cần tiêu thụ dependency versions đã được chuẩn hóa trong Maven BOM.

Nếu chỉ có một dự án nhỏ và custom parent đang hoạt động tốt, tạo BOM riêng có thể làm tăng số POM cần quản lý mà không đem lại lợi ích tương xứng. Hãy tách khi có nhu cầu chia sẻ dependency policy độc lập với build policy.

## 2. Cơ chế import BOM trong Maven

### 2.1. Cấu trúc import bắt buộc

Maven chỉ hỗ trợ scope import cho dependency có type pom nằm trong dependencyManagement:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.acme.platform</groupId>
            <artifactId>acme-dependencies-bom</artifactId>
            <version>2.4.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Các quy tắc:

- type phải là pom.
- scope phải là import.
- Entry phải nằm trong dependencyManagement.
- BOM phải resolve được từ reactor/local/remote repository theo cách build đang dùng.
- Không đặt BOM import trong dependencies của application.

Import là cơ chế thay thế entry import bằng danh sách managed dependencies của POM được import. Nó không tạo dependency runtime tới BOM và không đưa các library được liệt kê trong BOM vào classpath. [Maven Dependency Mechanism: Importing Dependencies](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html).

### 2.2. Dependency được quản lý không có nghĩa dependency đã được thêm

Ví dụ BOM quản lý version:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.18.2</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Project cần thư viện đó vẫn khai báo:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>
</dependencies>
~~~

Maven lấy version từ dependencyManagement khi dependency không chỉ định version riêng. Nếu project không khai báo dependency và dependency đó cũng không xuất hiện transitively, Maven sẽ không tải thư viện chỉ vì BOM có entry.

### 2.3. BOM quản lý cả dependency trực tiếp và transitive

Dependency management không chỉ giúp bỏ version trong dependencies trực tiếp. Nó còn có thể điều khiển version của một artifact xuất hiện như transitive dependency.

~~~text
orders-api
   |
   +--> library-a
   |       |
   |       +--> jackson-core:2.17.x
   |
   +--> library-b
           |
           +--> jackson-core:2.18.x

Imported BOM:
   jackson-core:2.18.2
~~~

Nếu BOM quản lý jackson-core, Maven có thể dùng version được quản lý thay cho version được khai báo trong các POM dependency. Điều này giúp alignment nhưng cũng có thể làm thư viện phụ thuộc gặp lỗi nếu version bị ép xuống quá cũ. Luôn xem dependency tree sau khi thay BOM. [Maven POM Reference: Dependency Management](https://maven.apache.org/pom.html).

### 2.4. BOM không quản lý transitive dependencies của Maven plugins

Maven project dependency graph và Maven plugin dependency graph là hai phạm vi khác nhau.

dependencyManagement quản lý dependencies của project. Nó không tự áp dụng cho transitive dependencies của plugins trong cùng effective POM. Nếu custom parent từng khóa plugin versions hoặc plugin dependencies, phải chuyển phần đó vào build/plugins hoặc build/pluginManagement. [Maven Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html).

## 3. Thiết kế một BOM nội bộ

Một BOM nội bộ nên có tọa độ và version độc lập với các application artifacts:

~~~text
com.acme.platform:acme-dependencies-bom:2.4.0
~~~

Nó có thể import BOM của framework và bổ sung version của các thư viện nội bộ.

### 3.1. Cấu trúc project

~~~text
platform-dependencies/
└── pom.xml

orders-api/
└── pom.xml

billing-api/
└── pom.xml
~~~

platform-dependencies/pom.xml là BOM. Các application có thể import cùng BOM mà không phải kế thừa một custom build parent duy nhất.

### 3.2. Ví dụ đầy đủ platform-dependencies/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.acme.platform</groupId>
    <artifactId>acme-dependencies-bom</artifactId>
    <version>2.4.0</version>
    <packaging>pom</packaging>

    <name>Acme Dependencies BOM</name>
    <description>Managed dependency versions for Acme applications</description>

    <properties>
        <spring-boot.version>4.0.0</spring-boot.version>
        <observability.version>2.4.0</observability.version>
        <http-client.version>3.1.0</http-client.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <!-- Import the Spring Boot dependency catalog -->
            <dependency>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-dependencies</artifactId>
                <version>${spring-boot.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>

            <!-- Manage Acme internal libraries -->
            <dependency>
                <groupId>com.acme.platform</groupId>
                <artifactId>acme-observability-starter</artifactId>
                <version>${observability.version}</version>
            </dependency>

            <dependency>
                <groupId>com.acme.platform</groupId>
                <artifactId>acme-http-client</artifactId>
                <version>${http-client.version}</version>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
~~~

Trong ví dụ này:

- packaging=pom xác định artifact là một POM package, không phải JAR chứa code.
- Spring Boot BOM cung cấp bộ version được framework kiểm thử cùng nhau.
- BOM nội bộ thêm các tọa độ của Acme libraries.
- Version của BOM nội bộ là 2.4.0; version của từng library được quản lý riêng.
- dependencies không được khai báo ở root vì mục tiêu là cung cấp version policy, không tự thêm library vào application.

Các version 4.0.0, 2.4.0 và 3.1.0 chỉ là version minh họa. Trong project thật, chọn release tương thích với Java, Spring Boot, các SDK nội bộ và repository policy của tổ chức.

### 3.3. Có thể import nhiều BOM

Một BOM có thể import nhiều BOM khác:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>4.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>

        <dependency>
            <groupId>com.fasterxml.jackson</groupId>
            <artifactId>jackson-bom</artifactId>
            <version>2.18.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đây là ví dụ cú pháp; không nên tùy tiện kết hợp các BOM có release train không tương thích. Nếu Spring Boot BOM đã quản lý Jackson, việc import thêm Jackson BOM có thể tạo xung đột version. Chỉ thêm BOM thứ hai khi có lý do kỹ thuật rõ ràng và đã kiểm tra dependency graph.

### 3.4. Properties của BOM không được export như properties của parent

Khi import BOM, Maven nhập các managed dependency entries của BOM. Nó không khiến toàn bộ properties của BOM trở thành properties có thể tham chiếu trực tiếp trong consumer POM.

Ví dụ, consumer không nên giả định có thể dùng property spring-boot.version chỉ vì BOM nội bộ đã khai báo property đó. Nếu cần dùng version này để cấu hình Maven plugin, khai báo property tương ứng trong consumer hoặc kế thừa từ build parent.

Các version đã được resolve bên trong BOM vẫn được sử dụng trong managed dependency entries được import.

## 4. Chuyển một child project từ custom parent sang BOM

Giả sử project trước đây dùng cấu trúc:

~~~text
company-parent
├── dependencyManagement
├── properties
├── build/pluginManagement
└── repositories

orders-api
└── inherits company-parent
~~~

Parent đang quản lý cả Spring dependencies và các thiết lập build.

### 4.1. Trước migration: child kế thừa custom parent

Ví dụ POM cũ:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.acme.build</groupId>
        <artifactId>company-parent</artifactId>
        <version>5.2.0</version>
    </parent>

    <artifactId>orders-api</artifactId>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <dependency>
            <groupId>com.acme.platform</groupId>
            <artifactId>acme-observability-starter</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

Child không cần khai báo version vì parent cung cấp dependencyManagement. Nó cũng có thể đang dựa vào parent để nhận groupId/version, Java compiler configuration, Spring Boot repackage execution, Surefire/Failsafe settings hoặc các plugin khác.

### 4.2. Sau migration: khai báo tọa độ và import BOM

Khi bỏ parent, child cần khai báo lại các thông tin trước đây được kế thừa. Ví dụ:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.acme.orders</groupId>
    <artifactId>orders-api</artifactId>
    <version>1.8.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring-boot.version>4.0.0</spring-boot.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.acme.platform</groupId>
                <artifactId>acme-dependencies-bom</artifactId>
                <version>2.4.0</version>
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
            <groupId>com.acme.platform</groupId>
            <artifactId>acme-observability-starter</artifactId>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>

            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <version>${spring-boot.version}</version>
                <executions>
                    <execution>
                        <goals>
                            <goal>repackage</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Các thay đổi quan trọng:

- Child có groupId/version riêng vì không còn kế thừa chúng từ parent.
- BOM được import trong dependencyManagement.
- Các dependencies vẫn nằm trong dependencies, nhưng không lặp version.
- Java release và source encoding được khai báo rõ.
- Plugin versions và execution được cấu hình trực tiếp vì BOM không quản lý chúng.
- Spring Boot Maven plugin có version rõ và goal repackage để tạo executable Boot JAR khi không kế thừa spring-boot-starter-parent.

Version plugin trong ví dụ cần được kiểm tra theo Maven/JDK và Spring Boot release đang dùng. Nếu dự án có cấu hình compiler, Surefire, Failsafe, Checkstyle, JaCoCo hoặc plugin khác trong custom parent, phải chuyển các cấu hình cần thiết tương ứng.

### 4.3. Nếu chỉ muốn tách dependency management nhưng vẫn cần build parent

Không bắt buộc phải xóa custom parent. Một phương án thường phù hợp là:

~~~text
company-build-parent
  ├── properties
  ├── build/plugins
  ├── pluginManagement
  └── imports acme-dependencies-bom

orders-api
  └── inherits company-build-parent
~~~

Khi đó custom parent vẫn cung cấp compiler, plugins, repositories và quy ước build; BOM là nguồn quản lý dependency versions.

Trong company-build-parent/pom.xml:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.acme.platform</groupId>
            <artifactId>acme-dependencies-bom</artifactId>
            <version>2.4.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Child tiếp tục khai báo parent như trước. Nhờ vậy, các project khác nhau có thể dùng chung BOM dù chúng không dùng chung build parent. Đây là cách tách hai trách nhiệm mà không phải sao chép toàn bộ plugin configuration sang từng ứng dụng.

### 4.4. Nếu cần giữ custom parent và dùng Spring Boot BOM

Maven chỉ cho một parent trực tiếp. Nếu dự án đã có custom parent, không thể đồng thời khai báo spring-boot-starter-parent làm parent thứ hai.

Thay vào đó:

1. Giữ custom parent nếu cần build conventions của nó.
2. Import spring-boot-dependencies BOM trong dependencyManagement của custom parent hoặc child.
3. Kiểm tra Java/compiler properties và encoding.
4. Cấu hình spring-boot-maven-plugin và goal repackage nếu parent hiện tại chưa cung cấp.
5. Kiểm tra resource filtering defaults và plugin executions mà Spring Boot parent thường thiết lập.

Spring Boot starter parent cung cấp nhiều mặc định ngoài dependency versions, gồm compiler level, encoding, parameter metadata, resource filtering và plugin configuration. Import riêng BOM chỉ cung cấp dependency management; không có toàn bộ các mặc định đó. [Spring Boot Maven: Using the Plugin and Parent](https://docs.spring.io/spring-boot/maven-plugin/using.html).

## 5. Chuyển nội dung custom parent thành các phần phù hợp

Trước khi xóa parent, lập bảng kiểm kê. Không chuyển tất cả nội dung của parent vào BOM.

| Nội dung trong custom parent | Nơi chuyển phù hợp |
| --- | --- |
| Dependency versions trong dependencyManagement | BOM |
| Import các framework BOM | BOM hoặc build parent |
| Version Java/compiler | Build parent hoặc child properties/plugin config |
| Source encoding | Build parent hoặc child |
| Plugin versions | pluginManagement hoặc build/plugins |
| Plugin executions/configuration | Build parent hoặc build/plugins |
| Dependencies được khai báo trực tiếp trong parent | Child dependencies hoặc một starter/library artifact |
| Repositories/pluginRepositories | Build parent, child hoặc settings/repository policy |
| Profiles ảnh hưởng build | Build parent hoặc child POM |
| Reporting configuration | Build parent hoặc child |
| groupId/version mặc định | Parent hoặc khai báo rõ ở từng project |
| SCM, organization, license metadata | Parent hoặc POM dự án |
| distributionManagement | Build/release parent hoặc cấu hình release riêng |

### 5.1. Chú ý các dependencies kế thừa từ parent

Có hai khu vực rất khác nhau trong POM:

~~~xml
<dependencyManagement>
    <dependencies>
        <!-- Chỉ quản lý version/scope/configuration -->
    </dependencies>
</dependencyManagement>

<dependencies>
    <!-- Thực sự thêm dependency vào project -->
</dependencies>
~~~

Nếu custom parent có dependencies, child đã kế thừa chúng như project dependencies. Khi thay parent bằng BOM, các dependencies đó không tự xuất hiện nữa.

Hãy kiểm tra từng dependency:

- Nếu mọi application đều thực sự cần library, có thể tạo starter/library nội bộ hoặc khai báo rõ ở consumers.
- Nếu chỉ một số ứng dụng cần, khai báo trong từng ứng dụng sử dụng.
- Nếu chỉ muốn quản lý version, chuyển entry sang BOM nhưng vẫn khai báo dependency ở consumer.
- Không thêm toàn bộ dependencies vào BOM để mong chúng tự được tải.

### 5.2. Chú ý properties

Các properties thường gặp trong parent:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <maven-surefire-plugin.version>3.5.2</maven-surefire-plugin.version>
</properties>
~~~

Đây là build configuration, không phải dependency catalog. Có thể giữ chúng trong build parent hoặc chuyển sang consumer POM.

BOM có thể dùng properties của chính nó để khai báo versions cho managed dependencies. Tuy nhiên, consumer import BOM không kế thừa các properties đó như khi kế thừa parent.

### 5.3. Chú ý pluginManagement và plugins

pluginManagement cung cấp default plugin versions/configuration cho plugin được sử dụng trong build. build/plugins khai báo plugin được sử dụng và có thể chứa executions gắn vào lifecycle.

BOM không nhập hai phần này. Khi bỏ parent, kiểm tra ít nhất:

- Compiler plugin và Java release.
- Surefire/Failsafe test execution.
- Spring Boot repackage.
- Resource filtering.
- Annotation processors.
- JaCoCo, Checkstyle, Spotless, PMD hoặc Sonar integration.
- Packaging, source/Javadoc attachment và signing plugins.
- Plugin versions để tránh phụ thuộc default version ngầm.

Không nhầm dependencyManagement với pluginManagement. Quản lý version của spring-boot-starter-web không đồng nghĩa quản lý version của spring-boot-maven-plugin.

## 6. Quy tắc ưu tiên khi nhiều BOM quản lý cùng một dependency

Khi import nhiều BOM, thứ tự và override cần được kiểm soát rõ.

### 6.1. Entry trực tiếp trong POM tiêu thụ có thể override imported BOM

Ví dụ project muốn dùng một version riêng cho Jackson:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.acme.platform</groupId>
            <artifactId>acme-dependencies-bom</artifactId>
            <version>2.4.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>

        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.18.3</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Entry trực tiếp trong POM hiện tại có thể ghi đè entry được nhập từ BOM. Chỉ override khi có lý do rõ ràng, ví dụ security fix, compatibility requirement hoặc một release train được kiểm thử riêng.

Override cục bộ làm giảm tính đồng nhất giữa các consumers. Nếu nhiều project cần cùng một override, cập nhật BOM và phát hành version BOM mới sẽ dễ kiểm soát hơn.

### 6.2. BOM import trước được ưu tiên khi hai BOM trùng entry

Giả sử BOM X quản lý library-a version 1.1 và BOM Y quản lý cùng artifact version 1.2. Nếu consumer import X trước Y và không khai báo entry trực tiếp, Maven chọn version 1.1 trong trường hợp xung đột này.

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>bom-x</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>

        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>bom-y</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Maven docs minh họa BOM import đầu tiên thắng khi hai imported BOM quản lý cùng dependency và POM tiêu thụ không có entry riêng. [Maven: Import order and dependency management precedence](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html).

Không dựa vào thứ tự import như một cách ngầm để xử lý conflict. Nên chọn một BOM làm nguồn chính, sau đó khai báo override rõ trong BOM nội bộ hoặc consumer nếu thật sự cần.

### 6.3. Parent dependencyManagement và local dependencyManagement

Nếu project vẫn kế thừa một build parent, dependencyManagement được khai báo trực tiếp trong child có thể override quản lý từ parent. Imported BOM entries cũng được hợp nhất vào dependencyManagement theo quy tắc Maven.

Để tránh kết quả khó đoán:

- Không quản lý cùng một artifact ở nhiều nơi nếu không cần.
- Nếu cần override, khai báo entry trực tiếp với version và lý do rõ.
- Kiểm tra effective POM sau khi thay thứ tự BOM.
- Kiểm tra dependency tree, đặc biệt các transitive dependencies quan trọng.

### 6.4. Dependency khai báo version riêng

Khi mục tiêu là sử dụng version từ BOM, dependency trong dependencies nên bỏ version:

~~~xml
<dependency>
    <groupId>com.acme.platform</groupId>
    <artifactId>acme-http-client</artifactId>
</dependency>
~~~

Nếu một dependency trực tiếp vẫn khai báo version riêng, đó là lựa chọn override cục bộ và cần được review. Đừng để version rải rác trong child POM vô tình làm sai lệch policy BOM.

### 6.5. Maven match dependency theo coordinates đầy đủ

Việc match dependencyManagement không chỉ dựa vào groupId và artifactId trong mọi trường hợp. Bộ khóa quản lý bao gồm:

- groupId
- artifactId
- type
- classifier

Đối với JAR không classifier, type mặc định là jar nên thường chỉ cần groupId/artifactId. Với test-jar, WAR hoặc artifact có classifier, khai báo type/classifier phù hợp để Maven match đúng entry. [Maven Dependency Management: Matching Coordinates](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html).

## 7. Các bẫy khi thiết kế và publish BOM

### 7.1. Đặt BOM trong cùng reactor rồi import từ một submodule

Maven docs cảnh báo không import một POM được định nghĩa trong submodule của chính project hiện tại theo cách làm BOM import trước khi artifact có thể được resolve. Cách an toàn là publish/install BOM trước, hoặc tổ chức dependency management theo parent inheritance trong cùng reactor khi phù hợp.

Ví dụ cấu trúc dễ gây vấn đề:

~~~text
root/
├── pom.xml
├── bom/
│   └── pom.xml
└── app/
    └── pom.xml  (imports bom module)
~~~

Nếu app cần import bom như một external BOM, hãy bảo đảm BOM đã được cài vào local repository hoặc publish vào repository mà build có thể truy cập trước khi resolve POM consumer. Đừng giả định Maven tự resolve mọi BOM import từ sibling module chỉ vì root POM aggregate chúng. [Maven BOM import restrictions](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html).

### 7.2. Import vòng lặp

Không tạo chu trình:

~~~text
BOM A imports BOM B
BOM B imports BOM A
~~~

Cũng không thiết kế POM import BOM đồng thời BOM đó lại kế thừa ngược POM import nó. Maven không thể xây dựng effective model khi có vòng lặp.

Thiết kế dependency catalog theo một chiều: BOM nền tảng → BOM nội bộ → application consumers.

### 7.3. BOM không tự trở thành dependency transitive của library

Nếu library A import BOM X trong POM của A, ứng dụng B phụ thuộc A không nên giả định toàn bộ dependency management từ BOM X tự động được truyền sang B như một parent. Dependency management không phải dependency runtime transitive.

Nếu B cần cùng version policy, B nên import BOM trực tiếp hoặc kế thừa một parent/build platform có import BOM đó.

### 7.4. Không đặt version BOM là mutable release

Không ghi đè nội dung BOM đã phát hành dưới cùng version. Nếu thay đổi dependency versions, exclusions hoặc managed metadata, phát hành version BOM mới, ví dụ 2.4.1.

BOM là một phần của build contract. Cùng tọa độ BOM phải có nội dung ổn định để developer và CI resolve cùng effective dependency management.

### 7.5. Không ép dependency version cũ một cách mù quáng

Dependency management có thể override version transitive. Nếu một library cần tối thiểu version mới hơn, BOM quản lý version cũ có thể làm build vẫn thành công nhưng runtime lỗi.

Kiểm tra release notes, compatibility matrix, CVE fixes và dependency tree trước khi nâng/hạ version.

### 7.6. Không quản lý tất cả mọi thứ bằng một BOM khổng lồ

Một BOM có thể trở nên khó nâng cấp nếu chứa nhiều nhóm dependencies không liên quan. Cân nhắc tách:

- Framework BOM: Spring Boot, Jackson, Netty.
- Internal platform BOM: SDK, starters, clients của tổ chức.
- Test BOM: JUnit, Mockito, Testcontainers.
- Data/observability BOM nếu có release train riêng.

Chỉ tách khi các nhóm có lifecycle và compatibility policy khác nhau. Quá nhiều BOM lại làm tăng xung đột import order và độ khó truy xuất version.

## 8. Spring Boot: dùng BOM khi không kế thừa starter parent

Spring Boot cung cấp hai artifact quan trọng:

- spring-boot-starter-parent: parent POM với build defaults và dependency management.
- spring-boot-dependencies: BOM chứa dependency versions được Spring Boot quản lý.

Nếu project không thể dùng spring-boot-starter-parent vì đã có custom parent, có thể import spring-boot-dependencies trong dependencyManagement. Khi đó cần tự cấu hình các plugin/build defaults mà parent trước đây cung cấp.

### 8.1. Cấu hình import Spring Boot BOM trực tiếp

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>4.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Sau đó khai báo các Spring Boot starters mà project thực sự dùng mà không cần version:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Spring Boot BOM quản lý version của các dependencies được curated trong release train. Version cụ thể phải khớp release Boot mà project đang sử dụng. [Spring Boot Build Systems: Dependency Management](https://docs.spring.io/spring-boot/reference/using/build-systems.html).

### 8.2. Cấu hình plugin khi không dùng starter parent

Khi không kế thừa starter parent, thêm plugin và execution rõ:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <version>4.0.0</version>
            <executions>
                <execution>
                    <goals>
                        <goal>repackage</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

Nếu thiếu repackage execution, project có thể tạo JAR Maven bình thường nhưng không tạo executable Spring Boot JAR theo cách mong muốn. Cũng cần chuyển các cấu hình Java release, encoding, resource filtering và plugin versions cần thiết từ parent cũ.

### 8.3. Không trộn version Spring Boot tùy tiện

Giữ version của:

- spring-boot-dependencies BOM.
- spring-boot-maven-plugin.
- Spring Boot starters.
- Spring Boot build plugins khác.

trong cùng một release train tương thích. Không nên import BOM 4.x nhưng chạy plugin 3.x hoặc override một số Spring Framework artifacts mà không có compatibility review.

## 9. Gradle có thể tiêu thụ Maven BOM

Dù bài học tập trung vào Maven, BOM còn có ích khi một số project dùng Gradle. Gradle hỗ trợ Maven BOM thông qua platform() và enforcedPlatform().

### 9.1. Import BOM với platform()

Groovy DSL:

~~~groovy
dependencies {
    implementation platform(
        'com.acme.platform:acme-dependencies-bom:2.4.0'
    )

    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'com.acme.platform:acme-observability-starter'
}
~~~

Kotlin DSL:

~~~kotlin
dependencies {
    implementation(
        platform("com.acme.platform:acme-dependencies-bom:2.4.0")
    )

    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("com.acme.platform:acme-observability-starter")
}
~~~

Dependencies có version được cung cấp từ BOM. platform() đưa dependency constraints từ BOM vào Gradle resolution. Gradle có thể giải quyết version cuối cùng dựa trên các constraints và graph của nó. [Gradle Platforms: Importing a BOM](https://docs.gradle.org/current/userguide/platforms.html).

### 9.2. platform() và enforcedPlatform()

| Cách dùng | Ý nghĩa |
| --- | --- |
| platform(bom) | Áp dụng dependency constraints như version recommendations/constraints trong Gradle resolution |
| enforcedPlatform(bom) | Áp dụng các version theo cách cưỡng chế mạnh hơn, có thể ghi đè version khác trong graph |

Không chọn enforcedPlatform() chỉ vì muốn “chắc chắn đồng bộ”. Nó có thể áp đặt version lên cả consumers không dự kiến và làm dependency graph khó phối hợp. Dùng platform() làm mặc định; chỉ dùng enforced platform khi policy thực sự cần và đã kiểm tra graph. [Spring Boot Gradle Dependency Management](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html).

### 9.3. Gradle BOM không thay plugin management

BOM không quản lý Gradle plugins. Version của Spring Boot Gradle plugin, Java toolchain và build plugins vẫn cần được quản lý qua plugin DSL, version catalog hoặc convention plugins.

Nếu mục tiêu là chia sẻ dependency versions giữa Maven và Gradle, BOM là giao diện chung hữu ích. Nếu mục tiêu là chia sẻ toàn bộ build conventions, mỗi build system vẫn cần cơ chế riêng.

## 10. Quy trình migration có kiểm soát

Không nên xóa parent và thay đổi dependency versions trong một lần không có baseline. Hãy chia migration thành các bước có thể kiểm chứng.

### Bước 1 — tạo baseline trước thay đổi

Chạy trên branch hiện tại:

~~~bash
mvn help:effective-pom -Doutput=target/effective-pom-before.xml
~~~

Ghi lại dependency tree:

~~~bash
mvn dependency:tree -Dverbose -DoutputFile=target/dependency-tree-before.txt
~~~

Lưu kết quả test/package và các thông tin sau:

- Java/Maven versions.
- GroupId/artifactId/version của dependencies trực tiếp.
- Các transitive versions quan trọng.
- Compiler release và encoding.
- Plugin versions, executions và configuration.
- Spring Boot repackage output.
- Profiles đang được kích hoạt.
- Repositories và release behavior.

Effective POM giúp nhìn cấu hình sau khi Maven hợp nhất parent và child. Dependency tree giúp thấy dependency nào thực sự xuất hiện và version nào được chọn.

### Bước 2 — kiểm kê custom parent

Đọc custom parent và phân loại từng section thành:

1. Dependency management chuyển sang BOM.
2. Build configuration cần giữ ở parent/plugin management.
3. Dependencies thực sự được kế thừa.
4. Metadata và release configuration.
5. Các profile hoặc properties được child sử dụng.

Đừng xóa parent trước khi biết child đang phụ thuộc vào phần nào của parent.

### Bước 3 — tạo BOM

Tạo POM mới có packaging pom. Chuyển dependency versions cần quản lý vào dependencyManagement, import framework BOM nếu phù hợp, thêm internal managed dependencies và kiểm tra coordinates.

Không chuyển build/plugins, pluginManagement, compiler configuration hoặc application dependencies vào BOM với kỳ vọng chúng được kế thừa.

### Bước 4 — publish hoặc install BOM

Trong local development có thể cài BOM vào local repository:

~~~bash
mvn -f platform-dependencies/pom.xml clean install
~~~

Trong CI/release, publish BOM vào Maven repository nội bộ hoặc repository quản trị phù hợp. Consumers phải resolve được tọa độ BOM trước khi build.

Dùng release version bất biến và có quyền ghi phù hợp. Không sử dụng một BOM snapshot/mutable release cho production mà không có policy rõ.

### Bước 5 — cập nhật một consumer thử nghiệm

Import BOM vào một application trước. Bỏ version khỏi dependencies đã được BOM quản lý. Giữ lại các version override có chủ ý và ghi rõ lý do.

Nếu bỏ parent, bổ sung groupId/version, properties và build plugin config cần thiết. Nếu vẫn cần build conventions, giữ parent hoặc tạo build parent mỏng có import BOM.

### Bước 6 — so sánh effective POM và dependency tree

~~~bash
mvn help:effective-pom -Doutput=target/effective-pom-after.xml
mvn dependency:tree -Dverbose -DoutputFile=target/dependency-tree-after.txt
~~~

So sánh trước/sau:

- Dependency trực tiếp còn đầy đủ không?
- Transitive versions có thay đổi ngoài ý muốn không?
- Test/runtime scopes có được giữ nguyên không?
- Exclusions có mất không?
- Plugin versions và executions còn đúng không?
- Java compiler release/encoding có còn đúng không?
- Spring Boot repackage có tạo executable JAR không?

### Bước 7 — chạy full validation

~~~bash
mvn clean verify
~~~

Nếu project có integration tests hoặc profile bắt buộc, chạy đúng các profiles đó. Kiểm tra output package, reports và các plugin executions.

### Bước 8 — mở rộng sang các consumer còn lại

Khi application đầu tiên pass, cập nhật những consumers khác theo cùng BOM. Tránh đồng thời đổi BOM version, Spring Boot version, Java release và plugin major versions nếu không cần thiết; thay đổi từng nhóm giúp dễ xác định regression.

### Bước 9 — loại bỏ parent cũ khi không còn consumer

Chỉ ngừng phát hành/duy trì custom parent khi:

- Không còn project cần build conventions của parent đó.
- Mọi dependencies trước đây được kế thừa đã được phân loại.
- Mọi plugin executions/configuration cần thiết đã được chuyển.
- Các consumers đã import BOM và build thành công.
- Release, CI và rollback paths đã được kiểm chứng.

Nếu parent vẫn cung cấp giá trị cho build conventions, giữ nó và để BOM làm nguồn dependency management độc lập.

## 11. Các lệnh Maven hữu ích khi migration

| Lệnh | Mục đích |
| --- | --- |
| mvn help:effective-pom | Xem effective POM sau inheritance/import |
| mvn dependency:tree | Xem dependency graph và selected versions |
| mvn dependency:tree -Dverbose | Hiển thị thêm thông tin conflict/omitted nodes |
| mvn dependency:analyze | Hỗ trợ phát hiện used/undeclared/unused dependencies |
| mvn clean verify | Chạy lifecycle tới verify, bao gồm tests/package |
| mvn -U clean verify | Buộc kiểm tra cập nhật snapshot/release metadata theo Maven behavior |
| mvn help:effective-settings | Xem settings effective để chẩn đoán repository/mirror |

Ví dụ lưu kết quả để so sánh:

~~~bash
mvn help:effective-pom -Doutput=target/effective-pom.xml
mvn dependency:tree -Dverbose -DoutputFile=target/dependency-tree.txt
mvn dependency:analyze
mvn clean verify
~~~

Nếu dependency tree khác trước migration, xác định rõ artifact/version nào thay đổi. Đừng chỉ dựa vào việc build pass: một dependency downgrade vẫn có thể gây lỗi runtime hoặc compatibility issue mà unit tests chưa bao phủ.

## 12. Kiểm tra dependency convergence và version conflicts

Khi BOM quản lý nhiều thư viện, nên kiểm tra các version conflicts có chủ đích.

### 12.1. Dependency tree

~~~bash
mvn dependency:tree -Dverbose
~~~

Một dependency tree có thể cho thấy version bị chọn hoặc version khác bị bỏ qua do mediation. Đặc biệt kiểm tra:

- Logging APIs và implementations.
- Jackson modules.
- Netty components.
- Spring Framework modules.
- Database drivers.
- HTTP clients.
- Test frameworks.
- Internal SDKs.

### 12.2. Maven Enforcer

Có thể dùng Maven Enforcer Plugin với rule dependency convergence để fail build khi nhiều paths yêu cầu version không thống nhất:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.5.0</version>
    <executions>
        <execution>
            <id>enforce-dependency-convergence</id>
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
~~~

Rule này có thể phát hiện version conflicts cần xử lý, nhưng không phải mọi conflict đều tự động là lỗi. Một số thư viện có compatibility policy cho phép nhiều version ở những nhánh riêng. Review exception có chủ ý và không tắt rule rộng chỉ để build pass.

### 12.3. Không dùng dependencyManagement để che lỗi dependency declaration

Nếu source code trực tiếp sử dụng một library, hãy khai báo nó trực tiếp trong dependencies thay vì chỉ dựa vào việc một dependency khác đang kéo nó transitively.

Điều này làm POM phản ánh đúng dependency của source code và giảm nguy cơ build hỏng khi library upstream thay đổi dependency graph. Maven cũng khuyến nghị khai báo rõ các dependencies mà project sử dụng trực tiếp. [Maven: Transitive Dependency Best Practices](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html).

## 13. Những lỗi phổ biến khi chuyển từ parent sang BOM

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Maven báo thiếu version | Dependency không có trong BOM hoặc import sai | Kiểm tra tọa độ, type/classifier và effective POM |
| BOM không được resolve | BOM chưa publish/install hoặc repository thiếu quyền | Cài local để thử hoặc publish BOM trước consumer |
| Import BOM báo lỗi scope/type | Import không nằm trong dependencyManagement hoặc thiếu type pom | Sửa đúng cấu trúc import |
| Build pass nhưng library không có trên classpath | Chỉ thêm entry trong dependencyManagement | Khai báo dependency trong dependencies |
| Sau khi xóa parent, nhiều dependencies biến mất | Parent có dependencies thực sự được kế thừa | Chuyển dependencies cần thiết vào consumer/starter |
| Java compiler dùng sai version | Parent từng cấu hình compiler/toolchain | Khai báo maven.compiler.release và compiler plugin |
| Spring Boot JAR không executable | Mất repackage execution từ starter parent/custom parent | Thêm spring-boot-maven-plugin và goal repackage |
| Plugin version thay đổi ngoài ý muốn | pluginManagement bị mất khi xóa parent | Chuyển plugin versions/configuration sang build parent hoặc child |
| Maven chọn version từ BOM khác | BOM imports trùng artifact, thứ tự import khác | Chuẩn hóa BOM chính và khai báo override rõ |
| Dependency transitive bị downgrade | BOM quản lý version thấp hơn dependency yêu cầu | Xem dependency tree và cập nhật BOM/override |
| Plugin vẫn kéo version cũ | dependencyManagement không áp dụng cho plugin transitive deps | Quản lý plugin riêng trong pluginManagement |
| Consumer không thấy property của BOM | BOM import không kế thừa properties như parent | Khai báo property ở consumer/build parent |
| Local pass nhưng CI fail | BOM chưa publish, repository/mirror hoặc credentials khác | Kiểm tra repository resolution trong CI |
| Module trong reactor không resolve BOM sibling | Import BOM nằm trong submodule của cùng reactor | Publish/install BOM trước hoặc tổ chức lại model |
| Effective POM có dependency nhưng dependency tree không có | Entry chỉ được quản lý, chưa được khai báo/transitive | Kiểm tra dependencies thực sự |
| Dependency convergence fail | Các nhánh graph yêu cầu version không thống nhất | Xem conflict, chọn version tương thích và ghi rõ override |

## 14. Checklist hoàn thành migration

### BOM

- [ ] BOM có tọa độ groupId/artifactId/version rõ ràng.
- [ ] packaging được đặt là pom.
- [ ] Dependency versions cần chia sẻ nằm trong dependencyManagement.
- [ ] Import BOM ngoài bằng type pom và scope import.
- [ ] BOM chỉ quản lý dependencies cần thiết, không chứa dependency thực sự ngoài ý muốn.
- [ ] Version BOM là immutable release.
- [ ] Các BOM import không có vòng lặp và đã xử lý conflict.

### Consumer POM

- [ ] Import đúng BOM version.
- [ ] Dependencies cần dùng vẫn được khai báo trong dependencies.
- [ ] Bỏ version khỏi dependencies được BOM quản lý, trừ override có chủ ý.
- [ ] groupId/version đã được khai báo nếu không còn parent cung cấp.
- [ ] Properties compiler/encoding cần thiết đã được chuyển.
- [ ] Plugin versions, executions và configuration đã được bảo toàn.
- [ ] Parent dependencies đã được phân loại và chuyển đúng.
- [ ] Repositories, profiles, reporting và release configuration đã được kiểm tra.

### Spring Boot

- [ ] Spring Boot BOM và plugin dùng version tương thích.
- [ ] Nếu không dùng starter parent, đã cấu hình compiler/encoding.
- [ ] spring-boot-maven-plugin có version rõ.
- [ ] Goal repackage chạy khi cần executable Boot JAR.
- [ ] Resource filtering và các plugin defaults quan trọng đã được kiểm tra.

### CI và release

- [ ] BOM được publish trước consumer build.
- [ ] Effective POM trước/sau đã được so sánh.
- [ ] Dependency tree trước/sau đã được review.
- [ ] Dependency convergence/conflicts đã được xử lý.
- [ ] mvn clean verify pass.
- [ ] Artifact packaging và runtime smoke test pass.
- [ ] Repository credentials/mirrors hoạt động trong CI.
- [ ] BOM version được lưu trong release record để truy xuất.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** BOM trong Maven là gì?

**Trả lời:** Một POM, thường có packaging pom, cung cấp danh sách managed dependencies để các consumer dùng chung version policy.

**Câu 2.** Tại sao phải đặt BOM import trong dependencyManagement?

**Trả lời:** Vì scope import chỉ hợp lệ với dependency type pom trong dependencyManagement; Maven thay entry đó bằng các managed dependencies từ BOM.

**Câu 3.** Import BOM có tự thêm tất cả library vào classpath không?

**Trả lời:** Không. BOM chỉ quản lý version/configuration. Project vẫn khai báo dependencies thực tế trong dependencies.

**Câu 4.** Có thể dùng nhiều BOM trong một POM không?

**Trả lời:** Có. Khi các BOM quản lý cùng dependency, thứ tự import ảnh hưởng kết quả; BOM được import trước thắng nếu consumer không khai báo entry override trực tiếp.

**Câu 5.** Entry dependencyManagement trực tiếp trong consumer có thể override imported BOM không?

**Trả lời:** Có. Dùng override trực tiếp khi có lý do rõ và đã kiểm tra compatibility.

**Câu 6.** Import BOM có kế thừa properties và pluginManagement của POM được import không?

**Trả lời:** Không. Nó nhập dependencyManagement entries. Properties, build/plugin configuration và reporting không được kế thừa như parent inheritance.

**Câu 7.** Nếu custom parent có dependencies trong phần dependencies thì điều gì xảy ra khi bỏ parent?

**Trả lời:** Các dependencies kế thừa đó không tự xuất hiện qua BOM import. Phải khai báo chúng ở consumer hoặc cung cấp qua một starter/library phù hợp.

**Câu 8.** Vì sao Maven dependencyManagement không quản lý transitive dependencies của Maven plugins?

**Trả lời:** Plugin dependency graph được xử lý riêng. Plugin versions/configuration cần được quản lý trong build/plugins hoặc pluginManagement.

**Câu 9.** Khi không kế thừa Spring Boot starter parent, cần chú ý điều gì?

**Trả lời:** Import spring-boot-dependencies BOM để quản lý library versions, đồng thời tự cấu hình Java compiler, encoding, plugin versions và Spring Boot repackage execution cần thiết.

**Câu 10.** Làm thế nào chứng minh migration không làm thay đổi dependency graph ngoài ý muốn?

**Trả lời:** So sánh effective POM và dependency tree trước/sau, chạy dependency analysis/convergence checks, rồi chạy clean verify và smoke test artifact.

**Câu 11.** BOM có thể được import từ submodule của cùng reactor không?

**Trả lời:** Maven docs cảnh báo không import BOM được định nghĩa trong submodule của project hiện tại theo cách cần resolve POM trước khi module đó được build. Hãy publish/install BOM trước hoặc chọn cấu trúc parent/inheritance phù hợp.

**Câu 12.** Gradle dùng Maven BOM bằng cách nào?

**Trả lời:** Dùng platform(bom) để áp dependency constraints; enforcedPlatform(bom) áp đặt constraints mạnh hơn và cần dùng thận trọng.

## 16. Tài liệu chính thức

- Apache Maven — [Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): dependencyManagement, import scope, BOM, conflict resolution và transitive dependencies.
- Apache Maven — [POM Reference](https://maven.apache.org/pom.html): parent inheritance, properties, build, pluginManagement và dependencyManagement.
- Apache Maven — [Maven Help Plugin: effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html): kiểm tra effective POM sau inheritance và import.
- Apache Maven — [Maven Dependency Plugin](https://maven.apache.org/plugins/maven-dependency-plugin/): dependency tree và dependency analysis.
- Spring Boot — [Build Systems](https://docs.spring.io/spring-boot/reference/using/build-systems.html): dependency management và Spring Boot BOM.
- Spring Boot — [Using the Maven Plugin](https://docs.spring.io/spring-boot/maven-plugin/using.html): khác biệt giữa starter parent và dependency BOM, plugin defaults.
- Gradle — [Platforms](https://docs.gradle.org/current/userguide/platforms.html): import Maven BOM bằng platform/enforcedPlatform.
- Gradle — [Centralizing Dependencies](https://docs.gradle.org/current/userguide/centralizing_dependencies.html): quản lý dependency versions tập trung.

**Ghi nhớ:** Parent POM là cơ chế kế thừa cấu hình dự án; BOM là dependency catalog được import vào dependencyManagement. Hãy chuyển dependency versions sang BOM, giữ lại các build conventions ở parent/build configuration phù hợp, khai báo dependencies thực tế tại consumer và xác minh effective POM cùng dependency tree trước khi phát hành migration.

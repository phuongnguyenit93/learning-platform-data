# Vai trò của tệp mô tả build, tệp cấu hình và build wrapper

Một dự án Java thường có nhiều tệp nằm ở thư mục gốc và các thư mục con. Một số tệp mô tả dự án cần được build như thế nào, một số tệp cung cấp các giá trị cấu hình, còn build wrapper giúp mọi thành viên sử dụng cùng phiên bản build tool. Hiểu đúng vai trò của từng tệp giúp ta biết nơi cần chỉnh sửa khi thêm dependency, thay đổi task, cấu hình phiên bản Java hoặc xử lý khác biệt giữa máy cá nhân và CI.

Trong bài này, ta tập trung vào hai hệ sinh thái phổ biến là Gradle và Maven. Cả hai đều dùng cấu hình có thể được quản lý bằng mã nguồn, nhưng tên tệp, cách tổ chức và một số quy ước khác nhau.

## 1. Phân biệt ba nhóm tệp

Trước tiên, cần tách ba trách nhiệm thường bị nhầm lẫn:

| Nhóm | Câu hỏi mà nhóm tệp trả lời | Ví dụ |
|---|---|---|
| Tệp mô tả build | Dự án gồm những phần nào, cần plugin/dependency nào, và tạo artifact ra sao? | Gradle `build.gradle` / `build.gradle.kts`; Maven `pom.xml` |
| Tệp cấu hình | Các giá trị, tùy chọn hoặc môi trường nào ảnh hưởng đến cách build được thực hiện? | Gradle `gradle.properties`, Maven `settings.xml`, `.mvn/maven.config`, `.mvn/jvm.config` |
| Build wrapper | Dùng phiên bản build tool nào và khởi động nó bằng cách nào trên máy chưa cài build tool toàn cục? | Gradle Wrapper (`gradlew`, `gradlew.bat`, `gradle/wrapper/`); Maven Wrapper (`mvnw`, `mvnw.cmd`, `.mvn/wrapper/`) |

Ba nhóm có liên quan nhưng không thay thế nhau. Tệp mô tả build định nghĩa cách dự án được xây dựng; tệp cấu hình điều chỉnh các tham số cho quá trình đó; wrapper chọn và khởi chạy phiên bản Gradle hoặc Maven đã được dự án chỉ định.

Ví dụ, thay phiên bản Gradle mà dự án sử dụng thường liên quan đến cấu hình wrapper. Thêm thư viện Java thường liên quan đến tệp mô tả build. Điều chỉnh bộ nhớ của Gradle daemon thường liên quan đến `gradle.properties`. Nếu nhầm ba trách nhiệm này, ta có thể sửa đúng cú pháp nhưng sai tệp nên hành vi không thay đổi như mong đợi.

## 2. Các tệp thường gặp trong một dự án Gradle

Một dự án Gradle đơn giản có thể có cấu trúc như sau:

```text
my-java-project/
├── settings.gradle.kts
├── build.gradle.kts
├── gradle.properties
├── gradle/
│   ├── libs.versions.toml
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── gradlew
├── gradlew.bat
└── src/
    ├── main/java/
    └── test/java/
```

Tên và số lượng tệp có thể khác nhau. Gradle hỗ trợ cả Groovy DSL (`.gradle`) và Kotlin DSL (`.gradle.kts`); một dự án thường chọn một kiểu cho các tệp build của mình.

### 2.1. `settings.gradle` hoặc `settings.gradle.kts`

Tệp settings mô tả cấu trúc tổng thể của một Gradle build. Nó được đọc ở giai đoạn khởi tạo (initialization), trước khi Gradle cấu hình từng project.

Các trách nhiệm thường gặp gồm:

- Đặt tên root project.
- Khai báo những project con tham gia build nhiều project.
- Chỉ định cách tìm plugin và dependency ở cấp build khi cần.
- Cấu hình một số chính sách hoặc hành vi áp dụng cho toàn build.

Ví dụ `settings.gradle.kts`:

```kotlin
rootProject.name = "order-system"

include(":api")
include(":domain")
include(":infrastructure")
```

Với cấu hình này, Gradle nhận diện một root project tên `order-system` và ba project con. Mỗi project con có thể có thư mục và `build.gradle.kts` riêng.

Settings cũng có thể khai báo repository tìm plugin:

```kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}
```

Trong các build có quản lý repository dependency tập trung, settings còn có thể dùng `dependencyResolutionManagement` để quy định repository cho các project. Việc đặt repository ở settings hay build script phải nhất quán với chính sách của dự án.

**Khi nào sửa settings?** Khi thêm/bỏ project con, đổi tên root project hoặc thay đổi cách phân giải plugin/repository ở cấp toàn build. Thêm một thư viện chỉ dùng trong một module thường thuộc trách nhiệm của build file module đó.

### 2.2. `build.gradle` hoặc `build.gradle.kts`

Build file mô tả cách một project được xây dựng. Đây thường là nơi ta nhìn thấy plugin, dependency, cấu hình biên dịch, source set và task.

Ví dụ `build.gradle.kts` cho một ứng dụng Java:

```kotlin
plugins {
    java
    application
}

group = "com.example"
version = "1.0.0"

repositories {
    mavenCentral()
}

dependencies {
    implementation("com.google.guava:guava:33.3.1-jre")
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.0")
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.test {
    useJUnitPlatform()
}
```

Ví dụ này cho biết project áp dụng Java và Application plugin, dùng Maven Central để tìm dependency, khai báo thư viện cho mã nguồn chính và kiểm thử, chọn Java toolchain 21 và cấu hình JUnit Platform cho task test.

Các khối cấu hình quan trọng:

- `plugins`: áp dụng plugin bổ sung task và quy ước build, ví dụ Java, Application hoặc Spring Boot.
- `repositories`: khai báo nơi Gradle tìm dependency.
- `dependencies`: khai báo thư viện cần cho biên dịch, chạy và kiểm thử.
- `java`: cấu hình liên quan đến Java, bao gồm toolchain và một số tùy chọn biên dịch.
- `tasks`: cấu hình task có sẵn hoặc task do plugin cung cấp; cũng có thể đăng ký task mới.
- `group`, `version`: thông tin nhận diện và phiên bản artifact của project.

Trong dự án nhiều module, root `build.gradle(.kts)` có thể chứa cấu hình dùng chung, còn build file trong từng module khai báo phần riêng của module. Không nên đặt dependency của mọi module vào root chỉ vì muốn gom các tệp lại; cấu hình cần phản ánh đúng quyền sở hữu và nhu cầu của từng project.

### 2.3. `gradle.properties`

`gradle.properties` chứa các Gradle property và tùy chọn ảnh hưởng đến quá trình build. Tệp này thường được dùng để cấu hình Gradle daemon, hiệu năng, chế độ thực thi hoặc một số giá trị build có thể thay đổi theo môi trường.

Ví dụ:

```properties
org.gradle.jvmargs=-Xmx2g -Dfile.encoding=UTF-8
org.gradle.parallel=true
org.gradle.caching=true

appVersion=1.4.0
```

Một số điểm cần phân biệt:

- `org.gradle.jvmargs` cấu hình JVM chạy Gradle daemon. Nó không trực tiếp đặt heap cho ứng dụng Java được build hoặc ứng dụng được chạy bằng một task khác.
- `org.gradle.parallel` cho phép Gradle thực hiện một số công việc song song khi build và cấu trúc build cho phép.
- `org.gradle.caching` bật cơ chế build cache; hiệu quả phụ thuộc task có khai báo đầu vào/đầu ra phù hợp và có thể cache hay không.
- `appVersion` là một Gradle project property tùy biến, có thể được build script đọc nếu dự án sử dụng nó.

Gradle có thể đọc `gradle.properties` ở cấp project hoặc trong thư mục Gradle user home của người dùng. Giá trị cũng có thể được truyền từ dòng lệnh, ví dụ `-PappVersion=1.5.0`. Khi một property có nhiều nguồn, cần hiểu quy tắc ưu tiên của Gradle thay vì giả định mọi tệp cùng lúc có giá trị cuối cùng.

Không nên lưu mật khẩu, token hoặc khóa truy cập vào `gradle.properties` được commit lên Git. Hãy dùng biến môi trường, secret store của CI hoặc cấu hình cục bộ không được commit theo quy ước của dự án.

### 2.4. `gradle/libs.versions.toml`

Gradle Version Catalog cho phép khai báo tập trung phiên bản plugin và dependency trong tệp TOML, thường đặt tại `gradle/libs.versions.toml`.

Ví dụ:

```toml
[versions]
junit = "5.11.0"
guava = "33.3.1-jre"

[libraries]
junit-jupiter = { module = "org.junit.jupiter:junit-jupiter", version.ref = "junit" }
guava = { module = "com.google.guava:guava", version.ref = "guava" }

[plugins]
```

Build script có thể tham chiếu catalog qua accessor được Gradle tạo, ví dụ:

```kotlin
dependencies {
    testImplementation(libs.junit.jupiter)
    implementation(libs.guava)
}
```

Version Catalog giúp tránh lặp lại chuỗi tên và phiên bản dependency ở nhiều module. Nó là nơi quản lý danh mục phiên bản; việc khai báo dependency nào thực sự được một module sử dụng vẫn nằm trong build file hoặc cấu hình tương ứng của module đó.

## 3. Gradle Wrapper: dùng cùng phiên bản Gradle

Gradle Wrapper là tập script và tệp hỗ trợ để chạy Gradle theo phiên bản mà dự án đã cấu hình. Thành viên mới không cần tự cài đúng phiên bản Gradle toàn cục trước khi build.

Các tệp wrapper thường gặp:

| Tệp | Vai trò |
|---|---|
| `gradlew` | Script khởi chạy wrapper trên Linux/macOS |
| `gradlew.bat` | Script khởi chạy wrapper trên Windows |
| `gradle/wrapper/gradle-wrapper.jar` | Mã khởi động wrapper, tải và gọi Gradle distribution được cấu hình |
| `gradle/wrapper/gradle-wrapper.properties` | Cấu hình distribution Gradle mà wrapper cần sử dụng |

Ví dụ `gradle-wrapper.properties`:

```properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-8.5-bin.zip
networkTimeout=10000
validateDistributionUrl=true
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
```

Thuộc tính quan trọng nhất là `distributionUrl`: nó chỉ ra bản phân phối Gradle wrapper sẽ tải và chạy. Các giá trị còn lại điều khiển nơi lưu distribution, timeout mạng và một số kiểm tra liên quan.

Khi chạy:

```bash
# Linux/macOS
./gradlew build

# Windows
gradlew.bat build
```

wrapper kiểm tra distribution đã có trong Gradle user home hay chưa. Nếu chưa, nó tải distribution theo URL, sau đó khởi chạy Gradle bằng phiên bản đó. Những lần chạy tiếp theo thường tái sử dụng distribution đã tải.

### Wrapper giải quyết và không giải quyết điều gì?

Wrapper giúp thống nhất **phiên bản Gradle** giữa máy lập trình viên và CI. Điều này làm giảm lỗi do mỗi người dùng một bản Gradle khác nhau.

Wrapper không tự bảo đảm mọi thành phần môi trường đều giống nhau:

- Nó không tự cài đặt hay pin phiên bản JDK mà Gradle cần để chạy.
- Nó không tự bảo đảm dependency Maven bên ngoài luôn có sẵn hoặc repository luôn truy cập được.
- Nó không thay thế cấu hình Java toolchain trong build.
- Nó không bảo đảm hệ điều hành, biến môi trường, quyền truy cập hoặc dịch vụ bên ngoài giống nhau.

Vì vậy, một build ổn định thường kết hợp wrapper với Java toolchain, dependency được khai báo rõ ràng và cấu hình CI nhất quán.

### Cập nhật phiên bản Gradle Wrapper

Khi dự án chủ động nâng cấp Gradle, có thể cập nhật wrapper bằng task `wrapper`:

```bash
./gradlew wrapper --gradle-version 8.5
```

Sau khi cập nhật, cần kiểm tra các tệp wrapper thay đổi, xác nhận `distributionUrl` trỏ đúng phiên bản mong muốn và build bằng wrapper mới. Nên commit cả script wrapper, wrapper JAR và tệp properties do dự án quản lý vào hệ thống kiểm soát phiên bản.

Nếu dự án sử dụng checksum cho Gradle distribution, cần cập nhật checksum tương ứng khi thay distribution. Không nên bỏ qua kiểm tra tính toàn vẹn chỉ để làm build chạy qua.

## 4. Các tệp thường gặp trong một dự án Maven

Một dự án Maven đơn giản thường có cấu trúc như sau:

```text
my-maven-project/
├── pom.xml
├── .mvn/
│   ├── wrapper/
│   │   ├── maven-wrapper.properties
│   │   └── maven-wrapper.jar        # tùy kiểu wrapper
│   ├── maven.config                 # tùy chọn
│   └── jvm.config                   # tùy chọn
├── mvnw
├── mvnw.cmd
└── src/
    ├── main/java/
    ├── main/resources/
    └── test/java/
```

Maven dùng Project Object Model (POM) để mô tả dự án. Các cấu hình người dùng/máy thường nằm ngoài POM.

### 4.1. `pom.xml`

`pom.xml` là tệp mô tả chính của một Maven project. Nó chứa thông tin nhận diện project, quan hệ kế thừa/module, dependency, plugin và cấu hình build.

Ví dụ rút gọn:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>order-service</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>21</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.0</version>
            <scope>test</scope>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Các thành phần quan trọng:

- `groupId`, `artifactId`, `version`: tọa độ định danh artifact Maven.
- `packaging`: loại artifact được tạo, ví dụ `jar` hoặc `pom`.
- `properties`: các giá trị có thể được tái sử dụng trong POM.
- `dependencies`: thư viện project cần sử dụng, kèm scope như `compile`, `runtime`, `test` hoặc `provided`.
- `build/plugins`: plugin thực hiện các bước build như compile, test, đóng gói hoặc kiểm tra.
- `modules`: khai báo các module con trong một Maven reactor build.
- `parent`: kế thừa cấu hình từ một POM cha.

Một POM có thể dài hơn đáng kể khi dự án cần cấu hình plugin, profile, quản lý dependency hoặc nhiều module. Không phải mọi giá trị đều phải lặp lại ở từng module: parent POM và `dependencyManagement`/`pluginManagement` có thể cung cấp cấu hình dùng chung.

### 4.2. Phân biệt `dependencies` và `dependencyManagement`

Trong Maven, `dependencies` khai báo thư viện mà project thực sự sử dụng. `dependencyManagement` ở POM cha hoặc POM hiện tại quản lý phiên bản và cấu hình mặc định cho dependency khi các module khai báo sử dụng chúng.

Ví dụ POM cha:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.0</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Module con muốn sử dụng thư viện vẫn cần khai báo dependency:

```xml
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
    </dependency>
</dependencies>
```

Khai báo trong `dependencyManagement` không tự đưa dependency vào mọi module. Nó cung cấp quy tắc quản lý để module dùng dependency có thể kế thừa phiên bản và thuộc tính đã định nghĩa.

Tương tự, `pluginManagement` quản lý cấu hình mặc định cho plugin; plugin thường cần được khai báo trong phần `build/plugins` để được áp dụng vào build theo cách dự án mong muốn.

### 4.3. `settings.xml`

Maven `settings.xml` chứa cấu hình cho môi trường người dùng hoặc cài đặt Maven, ví dụ:

- Địa chỉ mirror thay thế repository.
- Thông tin xác thực để truy cập repository riêng.
- Proxy mạng.
- Vị trí local repository.
- Profile cấu hình dành cho môi trường người dùng.

Tệp thường nằm ở một trong hai vị trí:

```text
${maven.home}/conf/settings.xml       # cấu hình ở cấp Maven installation
${user.home}/.m2/settings.xml         # cấu hình người dùng
```

Ví dụ cấu hình mirror:

```xml
<settings>
    <mirrors>
        <mirror>
            <id>company-mirror</id>
            <mirrorOf>*</mirrorOf>
            <url>https://repo.example.com/maven-public</url>
        </mirror>
    </mirrors>
</settings>
```

`settings.xml` không phải nơi thay thế `pom.xml`. POM mô tả project và dependency mà project cần; settings điều chỉnh cách Maven của người dùng/máy truy cập repository và thực thi trong môi trường đó.

Không commit mật khẩu hoặc token vào POM hay settings dùng chung. Thông tin xác thực nên được cung cấp bằng cơ chế an toàn của máy/CI; khi cấu hình `<server>`, giá trị `<id>` phải khớp với repository hoặc mirror tương ứng.

### 4.4. Các tệp tùy chọn trong `.mvn/`

Maven hỗ trợ một số tệp cấu hình bổ sung trong thư mục `.mvn/` ở root dự án:

- `maven.config`: chứa các tùy chọn dòng lệnh Maven mặc định cho build của dự án.
- `jvm.config`: chứa các tùy chọn JVM dùng khi khởi chạy Maven, ví dụ giới hạn bộ nhớ hoặc encoding.
- `wrapper/`: chứa cấu hình và các tệp hỗ trợ Maven Wrapper.

Ví dụ `.mvn/jvm.config`:

```text
-Xms256m
-Xmx2g
-Dfile.encoding=UTF-8
```

Các tùy chọn trong `jvm.config` tác động đến JVM chạy Maven. Chúng không tự cấu hình heap cho ứng dụng được tạo ra từ Maven.

## 5. Maven Wrapper: dùng Maven theo phiên bản của dự án

Maven Wrapper có mục tiêu tương tự Gradle Wrapper: cho phép khởi chạy Maven theo phiên bản đã khai báo trong dự án mà không cần người dùng tự cài đúng phiên bản Maven toàn cục.

Các tệp thường gặp:

| Tệp | Vai trò |
|---|---|
| `mvnw` | Script khởi chạy trên Linux/macOS |
| `mvnw.cmd` | Script khởi chạy trên Windows |
| `.mvn/wrapper/maven-wrapper.properties` | Khai báo Maven distribution và một số tùy chọn wrapper |
| `.mvn/wrapper/maven-wrapper.jar` | Thành phần hỗ trợ wrapper ở một số kiểu phân phối; không phải mọi kiểu wrapper đều dùng cùng tập tệp |

Ví dụ `maven-wrapper.properties`:

```properties
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip
wrapperUrl=https://repo.maven.apache.org/maven2/org/apache/maven/wrapper/maven-wrapper/3.3.2/maven-wrapper-3.3.2.jar
```

Tập thuộc tính cụ thể có thể khác theo phiên bản và kiểu Maven Wrapper được tạo. `distributionUrl` chỉ định Maven distribution mà wrapper sẽ sử dụng. Wrapper có thể tải distribution khi cần rồi chạy lệnh với phiên bản đó.

Chạy build:

```bash
# Linux/macOS
./mvnw clean verify

# Windows
mvnw.cmd clean verify
```

Khi thêm Maven Wrapper vào một dự án hoặc nâng phiên bản Maven, cần dùng cách tạo/cập nhật wrapper phù hợp với phiên bản Maven Wrapper của dự án, sau đó kiểm tra các script và tệp cấu hình được sinh ra. Hãy commit những tệp wrapper mà dự án sử dụng để mọi máy và CI có thể gọi cùng một entry point.

Maven Wrapper cũng không tự pin JDK. Phiên bản Maven và phiên bản Java chạy Maven là hai yếu tố riêng; dự án vẫn cần quy định và kiểm tra JDK phù hợp.

## 6. Theo dõi một lần build từ lệnh đến artifact

Khi chạy build bằng wrapper, có thể lần theo các bước khái quát sau:

```text
Người dùng / CI
      |
      v
gradlew hoặc mvnw
      |
      v
Đọc cấu hình wrapper
      |
      v
Chọn / tải đúng Gradle hoặc Maven distribution
      |
      v
Khởi chạy build tool bằng một JDK phù hợp
      |
      v
Đọc settings và build descriptor
      |
      v
Phân giải plugin, dependency và cấu hình task/phase
      |
      v
Biên dịch -> kiểm thử -> đóng gói
      |
      v
Artifact trong thư mục build hoặc target
```

Sơ đồ là mô hình khái quát. Gradle có các giai đoạn initialization, configuration và execution; Maven thực thi lifecycle phase cùng các goal của plugin. Tuy tên gọi khác nhau, cả hai đều cần đọc mô tả dự án và cấu hình trước khi thực hiện các bước tạo artifact.

Một lệnh wrapper đơn giản:

```bash
./gradlew clean build
```

hoặc:

```bash
./mvnw clean verify
```

cho phép người dùng bắt đầu build bằng phiên bản tool mà dự án đã chọn. `clean`, `build` và `verify` có ý nghĩa theo lifecycle/task model của từng hệ sinh thái; không nên mặc định hai lệnh trên thực hiện chính xác cùng một tập bước.

## 7. Dự án nhiều module: cấu hình ở cấp root và cấp module

Khi dự án có nhiều module, cần nhận diện phạm vi của từng tệp.

Với Gradle:

```text
root/
├── settings.gradle.kts          # khai báo các project tham gia build
├── build.gradle.kts             # cấu hình dùng chung ở root nếu cần
├── gradle.properties            # Gradle properties của build
├── gradlew
├── gradlew.bat
├── gradle/wrapper/               # phiên bản Gradle Wrapper
├── api/
│   └── build.gradle.kts         # cấu hình riêng của api
└── domain/
    └── build.gradle.kts         # cấu hình riêng của domain
```

`settings.gradle.kts` quyết định project nào tham gia build. Build file root có thể áp dụng quy tắc chung; build file module mô tả plugin, dependency và task riêng của module. Một module không được tham gia build chỉ vì thư mục của nó tồn tại; trong multi-project Gradle, nó cần được include trong settings.

Với Maven, root aggregator POM có thể khai báo:

```xml
<packaging>pom</packaging>

<modules>
    <module>api</module>
    <module>domain</module>
</modules>
```

Mỗi module thường có POM riêng. Root POM có thể vừa là aggregator (gom module vào reactor build), vừa là parent (cung cấp cấu hình được kế thừa), nhưng hai khái niệm này khác nhau. Một POM có thể làm một vai trò hoặc cả hai tùy cấu trúc dự án.

Khi sửa cấu hình, hãy xác định thay đổi thuộc toàn build, một nhóm module hay một module cụ thể. Đặt cấu hình ở đúng phạm vi giúp tránh làm các module không liên quan thay đổi hành vi.

## 8. Cấu hình phiên bản Java và phiên bản build tool

Đây là hai loại phiên bản thường bị nhầm:

**Phiên bản build tool** là phiên bản Gradle hoặc Maven mà wrapper khởi chạy. Gradle Wrapper lưu URL distribution trong `gradle-wrapper.properties`; Maven Wrapper lưu URL Maven distribution trong `maven-wrapper.properties`.

**Phiên bản Java** liên quan đến JVM chạy build tool và phiên bản Java mà mã nguồn được biên dịch/nhắm tới. Ví dụ với Gradle, Java toolchain có thể chọn compiler JDK cho task Java; với Maven, compiler plugin có thể cấu hình `release`. Build tool cũng có yêu cầu JDK tối thiểu riêng cho phiên bản của nó.

Vì vậy, khi thấy thông báo lỗi tương thích, hãy xác định lỗi đang nói về:

- JDK hiện tại không đủ mới để chạy Gradle/Maven.
- Compiler đang dùng không hỗ trợ tùy chọn hoặc ngôn ngữ mục tiêu.
- Bytecode được tạo bởi JDK mới hơn runtime mà ứng dụng đang dùng.
- Plugin hoặc dependency yêu cầu một phiên bản Java khác.

Chỉ thay `distributionUrl` của wrapper không tự giải quyết được mọi vấn đề liên quan đến JDK hoặc bytecode.

## 9. Quy ước quản lý các tệp build trong Git

Thông thường, những tệp mô tả build và wrapper là một phần của mã nguồn dự án và nên được commit:

- Gradle: `settings.gradle(.kts)`, `build.gradle(.kts)`, `gradle.properties` dùng chung, version catalog, wrapper scripts, wrapper JAR và wrapper properties.
- Maven: `pom.xml`, các tệp `.mvn/` dùng chung và wrapper scripts/tệp hỗ trợ được dự án sử dụng.

Những đầu ra build có thể tái tạo như `build/` của Gradle hoặc `target/` của Maven thường không cần commit, trừ khi dự án có một quy ước đặc biệt.

Các tệp cấu hình cá nhân hoặc chứa thông tin nhạy cảm thường không được commit. Ví dụ, `~/.m2/settings.xml` thuộc môi trường người dùng; nó có thể chứa thông tin xác thực hoặc mirror nội bộ. Tương tự, cấu hình local và secret của CI cần được quản lý riêng.

Wrapper script và wrapper JAR là thành phần có ảnh hưởng đến mã được thực thi trên máy build. Nên lấy chúng từ nguồn tin cậy, xem xét thay đổi khi nâng cấp và dùng checksum/verification phù hợp khi dự án hỗ trợ. Không nên chấp nhận thay đổi wrapper không rõ nguồn gốc chỉ vì build đang yêu cầu cập nhật.

## 10. Cách xác định đúng tệp cần sửa

Khi cần thay đổi một phần của build, có thể bắt đầu bằng cách xác định mục tiêu:

| Nhu cầu | Tệp hoặc vị trí thường cần xem |
|---|---|
| Thêm dependency cho một Gradle module | `build.gradle(.kts)` của module hoặc catalog cùng build file sử dụng alias |
| Thêm/bỏ Gradle subproject | `settings.gradle(.kts)` |
| Đổi phiên bản Gradle | `gradle/wrapper/gradle-wrapper.properties` và các tệp wrapper được cập nhật |
| Điều chỉnh JVM chạy Gradle daemon | `gradle.properties` hoặc cấu hình tương ứng của môi trường |
| Quản lý phiên bản dependency tập trung trong Gradle | `gradle/libs.versions.toml` nếu dự án sử dụng Version Catalog |
| Thêm dependency cho Maven project | `pom.xml` của project cần dependency |
| Quản lý phiên bản dependency dùng chung giữa Maven modules | `dependencyManagement` trong parent/aggregator POM phù hợp |
| Đổi phiên bản Maven Wrapper | `.mvn/wrapper/maven-wrapper.properties` và các tệp wrapper liên quan |
| Cấu hình mirror hoặc thông tin xác thực Maven | `settings.xml` ở môi trường Maven/user/CI |
| Điều chỉnh JVM chạy Maven | `.mvn/jvm.config` hoặc cấu hình môi trường tương ứng |

Sau khi sửa, hãy chạy build bằng wrapper của dự án để xác nhận cấu hình thực sự được áp dụng. Nếu lỗi chỉ xảy ra trên CI hoặc một máy cụ thể, hãy so sánh JDK, biến môi trường, quyền truy cập repository và cấu hình người dùng trước khi kết luận POM/build script sai.

## 11. Những nhầm lẫn thường gặp

**Nhầm build file với wrapper properties.** Build file mô tả project cần làm gì; wrapper properties chọn phiên bản build tool. Thêm dependency vào wrapper properties sẽ không làm dependency xuất hiện trong project.

**Nhầm wrapper với JDK toolchain.** Wrapper chọn Gradle/Maven. Toolchain hoặc cấu hình compiler xác định Java dùng để biên dịch. Cả hai có thể cần được cấu hình để build nhất quán.

**Nhầm Gradle `settings.gradle` với `build.gradle`.** Settings xác định cấu trúc và chính sách cấp build; build file cấu hình project và task. Thêm một module vào thư mục nhưng không include trong settings sẽ không tự động khiến Gradle build nó.

**Nhầm Maven `settings.xml` với `pom.xml`.** POM mô tả project; settings điều chỉnh môi trường Maven của người dùng/máy. Dependency của ứng dụng thuộc POM, còn thông tin đăng nhập repository thuộc cấu hình an toàn của môi trường.

**Cho rằng có wrapper là build sẽ luôn chạy offline.** Wrapper có thể cần tải build tool distribution; dependency và plugin cũng có thể cần tải. Chỉ khi distribution và các dependency cần thiết đã được cache đầy đủ thì build mới có thể chạy offline.

**Commit secret trong tệp cấu hình dùng chung.** Những giá trị nhạy cảm phải đi qua secret management hoặc biến môi trường, không đưa vào build file hay tệp cấu hình được chia sẻ công khai.

## 12. Ghi nhớ

- Tệp mô tả build định nghĩa cấu trúc project, plugin, dependency, task hoặc lifecycle cần thực hiện.
- Tệp cấu hình cung cấp giá trị và tùy chọn ảnh hưởng đến build, có thể ở phạm vi project, người dùng hoặc môi trường.
- Build wrapper cung cấp entry point để mọi người và CI sử dụng cùng phiên bản Gradle/Maven đã được dự án chọn.
- Gradle thường dùng `settings.gradle(.kts)`, `build.gradle(.kts)`, `gradle.properties`, version catalog và `gradle/wrapper/`.
- Maven thường dùng `pom.xml`, `settings.xml`, các tệp tùy chọn trong `.mvn/` và `.mvn/wrapper/`.
- Wrapper pin phiên bản build tool; cấu hình JDK/toolchain và phiên bản bytecode là trách nhiệm riêng cần được xác định rõ.
- Hãy sửa tệp đúng phạm vi, không commit secret, và xác nhận thay đổi bằng lệnh wrapper của dự án.

Khi mở một dự án Java mới, hãy tìm build file trước để hiểu project được tạo ra như thế nào, xem settings để biết cấu trúc module, kiểm tra tệp cấu hình để hiểu các tham số môi trường, rồi đọc wrapper properties để biết build tool nào sẽ được sử dụng. Trình tự đó giúp ta hình thành bức tranh rõ ràng về cấu trúc build trước khi thay đổi nó.

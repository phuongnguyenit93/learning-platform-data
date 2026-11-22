# Cấu hình group, version, repositories và dependencies trong Gradle với Spring Boot

## 1. Bốn nhóm cấu hình quyết định bản dựng lấy gì và tạo ra gì

Khi bắt đầu một ứng dụng Spring Boot bằng Gradle, lập trình viên thường nhìn thấy những dòng như **group = 'com.example'**, **version = '1.0.0'**, **repositories { mavenCentral() }** và **dependencies { implementation '...' }**. Chúng ngắn nhưng đảm nhận những việc khác nhau:

- **group**: xác định nhóm định danh của **project/artifact** đang được build.
- **version**: xác định phiên bản của **project/artifact** đang được build.
- **repositories**: chỉ ra **nguồn để Gradle tìm dependency artifacts** khi giải các thư viện.
- **dependencies**: khai báo **dự án cần module, thư viện hoặc project khác nào** và chúng thuộc classpath/phạm vi sử dụng nào.

Với Spring Boot, còn một mảnh ghép quan trọng: **Spring Boot Gradle Plugin** giúp chạy và đóng gói ứng dụng; **BOM/dependency management** cung cấp bộ phiên bản thư viện được Spring Boot quản lý. Cấu hình group/version của project **không thay thế** việc chọn Spring Boot plugin version hoặc các dependency versions.

Mục tiêu sau bài: tự đọc và viết các cấu hình trên trong **build.gradle** (Groovy DSL) hoặc **build.gradle.kts** (Kotlin DSL); hiểu sự khác nhau giữa project identity, library coordinates và plugin repositories; chọn dependency scope phù hợp; dùng Spring Boot BOM đúng cách; kiểm tra dependency graph và chạy một project thực tế.

## 2. Bản đồ cấu hình của một dự án Gradle

Một dự án Java/Spring Boot Gradle cơ bản có cấu trúc:

~~~text
order-service/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/
    │   ├── java/...
    │   └── resources/...
    └── test/
        └── java/...
~~~

**settings.gradle** quyết định tên root project, các subproject, và có thể tập trung cấu hình repository/plugin resolution. **build.gradle** mô tả plugins, group/version, Java toolchain, repositories, dependencies và tasks của project. **gradlew / gradlew.bat** là Gradle Wrapper, giúp dùng bản Gradle project lựa chọn thay vì bản cài ngẫu nhiên trên máy.

Nếu project dùng **Kotlin DSL**, tên tệp tương ứng là **settings.gradle.kts** và **build.gradle.kts**. Cú pháp Groovy/Kotlin khác nhau, còn các khái niệm group, version, repository, dependency configuration và BOM là giống nhau.

Một sơ đồ ngắn về dòng dữ liệu:

~~~text
settings.gradle : rootProject.name / included projects / repository policy
                        |
                        v
build.gradle : plugins + group + version + repositories + dependencies
                        |
                        v
Gradle resolve plugin và dependency metadata/artifacts
                        |
                        v
Java compile/test -> Spring Boot bootJar -> build/libs/<name>-<version>.jar
                        |
                        v
java -jar + cấu hình runtime -> ứng dụng chạy
~~~

Không nên hiểu toàn bộ bước này xảy ra chỉ vì khai báo group hoặc version. Gradle phải có plugin, task và dependencies phù hợp; cần thực sự gọi task như **build** hoặc **bootJar** để tạo artifact.

## 3. group: định danh của project, không phải Java package

### 3.1. Khai báo group

Trong **build.gradle** (Groovy DSL):

~~~groovy
group = 'com.example.training'
~~~

Trong **build.gradle.kts** (Kotlin DSL):

~~~kotlin
group = "com.example.training"
~~~

**group** là một thuộc tính của Gradle **Project**. Khi project được publish theo chuẩn Maven, nó thường trở thành **groupId** trong tọa độ artifact. Nó giúp phân biệt các module có tên giống nhau thuộc các tổ chức khác nhau.

Ví dụ project có:
- group = **com.example.training**
- name = **order-service**
- version = **1.0.0-SNAPSHOT**

Tọa độ mô-đun theo kiểu Maven là:

~~~text
com.example.training:order-service:1.0.0-SNAPSHOT
          group       :    name     :     version
~~~

**group không phải Java package name bắt buộc.** Cấu trúc thư mục Java có thể là **com/example/orders/** và dòng **package com.example.orders;**. Để dễ quản trị, thường chọn package name có liên hệ tới group, nhưng Gradle không tự đổi package declaration, Spring component scanning hay vị trí mã nguồn theo group.

**group không phải tên Spring application.** Thuộc tính runtime **spring.application.name** được Spring Boot đọc riêng từ **application.properties**, YAML, biến môi trường hoặc các nguồn cấu hình khác. Gán group không tự đổi URL, cổng hay tên service trong hệ thống vận hành.

### 3.2. Nếu không đặt group thì sao?

Gradle vẫn có thể build project Java nội bộ khi group không được cấu hình, nhưng định danh publish sẽ thiếu hoặc mang giá trị mặc định không mong muốn. Với project cần lưu trữ artifact hoặc dùng làm dependency ở dự án khác, nên chọn group ổn định, nhất quán theo namespace của tổ chức.

Chọn group là quyết định danh tính phát hành. Không tự ý đổi group đối với artifact đã có consumer; từ góc nhìn Maven/Gradle dependency resolution, **com.example:a:1.0** và **com.other:a:1.0** là hai module khác nhau dù mã giống nhau.

## 4. version: phiên bản của sản phẩm đang build

### 4.1. Khai báo version

Trong **build.gradle**:

~~~groovy
version = '1.0.0-SNAPSHOT'
~~~

Trong **build.gradle.kts**:

~~~kotlin
version = "1.0.0-SNAPSHOT"
~~~

Thuộc tính **project.version** là định danh phát hành của project. Khi dùng Spring Boot task **bootJar**, mặc định tên archive thường dựa vào **project.name** và **project.version**, ví dụ **order-service-1.0.0-SNAPSHOT.jar** trong **build/libs**. Tên này có thể thay đổi khi cấu hình archive task.

Nếu không đặt version, Gradle có giá trị mặc định dạng **unspecified**; đừng coi đó là version phát hành ổn định. Với service đã được đưa vào CI/release pipeline, nên đặt chính sách version rõ ràng.

### 4.2. project.name ở đâu?

Tên project thường đặt trong **settings.gradle**:

~~~groovy
rootProject.name = 'order-service'
~~~

Hoặc **settings.gradle.kts**:

~~~kotlin
rootProject.name = "order-service"
~~~

Bộ ba **group:name:version** mô tả danh tính mô-đun khi dùng Maven-style coordinates. **name** trong ví dụ đến từ tên Gradle project, không tự lấy từ **spring.application.name**. Việc thay **rootProject.name** có thể làm tên output mặc định và đường dẫn project/task thay đổi; thay **version** có thể làm tên archive/version metadata thay đổi.

### 4.3. Project version khác ba loại version dễ nhầm

| Cấu hình | Ví dụ | Đang chọn phiên bản của ai? |
| --- | --- | --- |
| **version = '1.0.0-SNAPSHOT'** | Project | Artifact của ứng dụng/module đang build |
| **id 'org.springframework.boot' version '3.5.16'** | Plugin | Spring Boot **Gradle Plugin** và nhánh Boot đi kèm |
| **implementation 'com.example:some-lib:2.4.0'** | Dependency | Thư viện external **some-lib** |
| **java.toolchain.languageVersion = 17** | JDK | JDK dùng cho các task Java hỗ trợ toolchain |

Một thay đổi **version = '2.0.0'** của project **không nâng Spring Boot từ 3.5 lên 4.0**, không cập nhật Jackson và không đổi JVM chạy ứng dụng. Cần thay đúng cấu hình tương ứng.

### 4.4. Có nên dùng SNAPSHOT?

Hậu tố **-SNAPSHOT** thường thể hiện build phát triển có thể thay đổi trước bản release cố định. Với artifact dùng trong production, đội ngũ nên có quy tắc đánh version theo commit/tag và lưu output bất biến. Gradle không tự phát hành lên Maven Central hay registry chỉ vì bạn đặt version; việc publish cần plugin/task, repository đích và quyền ghi riêng.

Nếu muốn version do CI truyền vào, có thể **thay thế** dòng version tĩnh bằng cấu hình lấy một Gradle property:

~~~groovy
version = providers.gradleProperty('releaseVersion')
        .orElse('1.0.0-SNAPSHOT')
        .get()
~~~

Sau đó chạy ví dụ:

~~~bash
./gradlew -PreleaseVersion=1.1.0 bootJar
~~~

Lúc này project.version là **1.1.0** cho build đó. Đây là **phương án thay thế** dòng version tĩnh trong demo, không nên giữ hai dòng version cùng lúc rồi dự đoán dòng nào có hiệu lực. Chọn version phải đi cùng chính sách release và kiểm thử để tránh trộn nhiều artifact mang cùng định danh.

## 5. repositories: Gradle tìm thư viện từ đâu?

### 5.1. Maven Central là nguồn thường dùng

Trong **build.gradle** (Groovy):

~~~groovy
repositories {
    mavenCentral()
}
~~~

Trong **build.gradle.kts** (Kotlin):

~~~kotlin
repositories {
    mavenCentral()
}
~~~

**mavenCentral()** khai báo một Maven-compatible repository công khai chứa nhiều thư viện Java. Khi project khai báo một dependency, Gradle dựa trên metadata, module coordinates và danh sách repository để tìm artifact và các dependency bắc cầu.

**repositories không phải nơi Gradle publish đầu ra của project theo mặc định.** Khối **repositories** ở đây là **nguồn tải/resolve**. Đích upload artifact khi áp dụng **maven-publish** hoặc cơ chế phát hành khác thường được cấu hình riêng trong **publishing.repositories**.

### 5.2. Repository cho plugin khác repository cho dependencies

Đây là hai đường giải khác nhau:

| Muốn tìm gì? | Thường cấu hình ở đâu? | Ví dụ |
| --- | --- | --- |
| **Gradle plugins** như **org.springframework.boot** | **pluginManagement.repositories** trong settings, hoặc mặc định Gradle Plugin Portal | gradlePluginPortal() |
| **Libraries** như spring-boot-starter-web, Jackson, JUnit | **repositories** trong build script, hoặc **dependencyResolutionManagement.repositories** trong settings | mavenCentral() |
| **Artifacts để phát hành** | publishing repositories hay pipeline/registry tương ứng | Maven repository nhận output |
| **JDK/toolchain distribution** | Cơ chế provision toolchain riêng | Không được thay bằng mavenCentral() theo mặc định |

Nếu lỗi **Plugin [id: 'org.springframework.boot'] was not found**, thêm **mavenCentral()** vào khối dependency repositories chưa chắc sửa được: vấn đề có thể nằm ở plugin repositories, plugin version hoặc mạng. Ngược lại, nếu tìm được plugin nhưng không resolve được **org.springframework.boot:spring-boot-starter-web**, cần kiểm tra dependency repositories/BOM/network.

Thông thường, **plugins { ... }** có thể tải plugin từ **Gradle Plugin Portal** mặc định mà không cần khai báo pluginManagement. Tuy nhiên, một công ty dùng mirror hoặc proxy nội bộ có thể phải cấu hình plugin repositories trong **settings.gradle(.kts)**.

### 5.3. Dự án nhiều module: khai báo tập trung ở settings

Khi muốn tất cả module dùng một danh sách repository được duyệt, có thể đặt cấu hình trong **settings.gradle** như một **phương án thay thế** cho **repositories { mavenCentral() }** ở từng build.gradle:

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS
    repositories {
        mavenCentral()
    }
}

rootProject.name = 'order-service'
~~~

**FAIL_ON_PROJECT_REPOS** yêu cầu khai báo dependency repositories ở settings và báo lỗi nếu một project/build script cố thêm repository riêng. Khi chọn mẫu này, **bỏ khối repositories ở build.gradle**; nếu giữ cả hai, cấu hình có thể bị từ chối ngay theo chính sách đã chọn.

Gradle cũng có **PREFER_SETTINGS** hoặc **PREFER_PROJECT** (mặc định) để quy định cách ưu tiên repositories giữa settings và project. Chọn cách nào là chính sách build của tổ chức; đừng dán cả cấu hình tập trung lẫn cấu hình tản mát mà không hiểu cách Gradle chọn nguồn.

Tài liệu: https://docs.gradle.org/current/userguide/centralizing_repositories.html

### 5.4. Repository riêng và xác thực

Với thư viện nội bộ, tổ chức có thể dùng một Maven-compatible repository riêng:

~~~groovy
repositories {
    maven {
        url = uri('https://repo.example.invalid/releases')
        credentials {
            username = providers.gradleProperty('repoUser')
                    .orElse(providers.environmentVariable('REPO_USER'))
                    .orNull
            password = providers.gradleProperty('repoPassword')
                    .orElse(providers.environmentVariable('REPO_PASSWORD'))
                    .orNull
        }
    }
    mavenCentral()
}
~~~

**Đây chỉ là đoạn minh họa**: hostname **example.invalid** không phải repository hoạt động. Dùng URL thật do tổ chức cung cấp, chọn cơ chế xác thực được hạ tầng hỗ trợ và không commit mật khẩu hoặc token vào build.gradle/gradle.properties của repository. Có thể cung cấp bí mật qua environment variables, user-level Gradle properties hoặc secret store của CI.

Thứ tự và phạm vi repository ảnh hưởng resolution. Một library có thể xuất hiện ở nhiều nơi, dẫn đến khác biệt nguồn artifact; với kho nội bộ, cân nhắc **content filters/exclusive content** và mirror đã kiểm chứng để hạn chế artifact được lấy sai nguồn.

### 5.5. Những nguồn ít nên dùng tùy tiện

- **mavenLocal()**: có thể lấy artifact đã cài vào local Maven repository của máy cá nhân, không nhất thiết giống với CI; thường không phù hợp làm nguồn mặc định của build phát hành.
- **flatDir / files('libs/x.jar')**: dùng local JAR nhưng thiếu metadata về transitive dependencies và version constraints; khó kiểm soát/cập nhật hơn module đã publish.
- **jcenter()**: không nên lấy làm repository mặc định cho dự án Spring Boot mới; sử dụng Maven Central hoặc nguồn hiện được dự án/thư viện hỗ trợ.
- **Maven snapshot repositories**: chỉ thêm khi thật sự cần snapshot artifacts; dependency động hoặc snapshot có thể làm kết quả build đổi theo thời gian.

Một build có tính lặp lại cần kiểm soát **version, repository, cache, metadata và trạng thái phụ thuộc động**, không chỉ có dòng mavenCentral().

## 6. dependencies: khai báo những gì được đưa lên từng classpath

### 6.1. Tọa độ thư viện external

Trong Gradle, một dependency external thường dùng dạng:

~~~text
group:name:version
~~~

Ví dụ:

~~~groovy
dependencies {
    implementation 'com.google.guava:guava:33.4.8-jre'
}
~~~

Giải thích:
- **com.google.guava** là group của **thư viện Guava**, không phải group của project đang build.
- **guava** là artifact/module name.
- **33.4.8-jre** là phiên bản yêu cầu của thư viện.
- **implementation** là dependency configuration cho main source của project.

Gradle còn resolve **transitive dependencies** mà artifact này khai báo, rồi áp dụng quy tắc chọn phiên bản, constraints và conflict resolution. Do đó một dòng dependency có thể kéo theo nhiều JAR khác nhau.

### 6.2. Dependency configuration thể hiện lúc nào cần thư viện

Khi dự án áp dụng Java plugin, các cấu hình phổ biến là:

| Configuration | Có cho compile main? | Có cho runtime main? | Mục đích |
| --- | --- | --- | --- |
| **implementation** | Có | Có | Thư viện ứng dụng dùng trong code và lúc chạy |
| **compileOnly** | Có | Không | Chỉ cần compile, chẳng hạn annotation type hoặc API do môi trường cung cấp |
| **runtimeOnly** | Không | Có | Driver/provider chỉ cần lúc chạy; ví dụ driver database khi code dùng JDBC abstraction |
| **annotationProcessor** | Cho annotation processing, không phải classpath nghiệp vụ thông thường | Không | Các processor chạy lúc compile, ví dụ Lombok |
| **testImplementation** | Cho compile test, không thêm vào compile main | Cho runtime test | JUnit, Spring Boot Test, test helpers |
| **testRuntimeOnly** | Không cho compile test | Cho runtime test | Test engine/launcher hoặc thành phần chỉ cần khi thực thi test |

Ví dụ mở rộng, **không phải danh sách cần dán toàn bộ vào ứng dụng đơn giản**:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    // Nếu thực sự viết ứng dụng truy cập database qua JDBC:
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'

    // Nếu dự án thật sự dùng Lombok:
    compileOnly 'org.projectlombok:lombok'
    annotationProcessor 'org.projectlombok:lombok'

    // Kiểm thử:
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
~~~

Các dependencies không có version ở đây **giả định project đã cấu hình Spring Boot dependency management/BOM** cho từng configuration cần thiết. Nếu chưa có cơ chế quản lý phiên bản, Gradle có thể báo **Could not find ...** hoặc không xác định được version. Ngoài ra, nếu tự ý thêm **spring-boot-starter-jdbc** vào một demo không có datasource, Spring Boot có thể yêu cầu cấu hình database khi khởi động; đừng thêm dependency chỉ vì thấy nó trong ví dụ.

**api** là cấu hình thường thấy với **java-library** plugin để công bố dependency nằm trên public API của thư viện. Một ứng dụng Spring Boot với Java plugin thường dùng **implementation**; đừng gọi **api** nếu project không áp dụng plugin tạo configuration đó.

### 6.3. Không nhầm runtimeClasspath với runtimeOnly

**runtimeOnly** là nơi **khai báo** dependency chỉ cần runtime. **runtimeClasspath** là một configuration dùng để **resolve** tổng classpath runtime, kết hợp dependencies từ implementation, runtimeOnly và những nguồn phù hợp. Tương tự, **compileClasspath** là kết quả resolve cho việc biên dịch, không phải tên scope thông thường để khai báo library.

Spring Boot task **bootJar** đóng gói các runtime dependencies dựa trên classpath phù hợp do plugin định nghĩa. Vì thế **compileOnly** thông thường không đi vào executable archive, trong khi implementation/runtimeOnly thường có mặt nếu cần. Vẫn phải kiểm tra plugin custom, exclusions và cấu hình packaging thực tế.

## 7. Spring Boot Gradle Plugin và quản lý phiên bản dependencies

### 7.1. Plugin Boot không đồng nghĩa mọi starter đều tự có version

Trong **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
}
~~~

Plugin Spring Boot cung cấp khả năng **bootRun**, **bootJar**, **bootWar** và các tích hợp khác khi kết hợp plugin Java/War thích hợp. Tuy nhiên, theo tài liệu Spring Boot, để bỏ version ở những dependency được Boot quản lý, project cần **một phương án dependency management**:

1. Áp dụng **io.spring.dependency-management** plugin; khi đi cùng Spring Boot plugin, BOM Spring Boot tương ứng được nhập tự động.
2. Dùng **Gradle native BOM support** qua **platform(...)** hoặc **enforcedPlatform(...)**.

Chỉ viết **implementation 'org.springframework.boot:spring-boot-starter-web'** trong project không có BOM/management phù hợp có thể không resolve được version. **group/version của chính project cũng không giải quyết được chuyện này.**

### 7.2. Phương án A — Gradle native platform (dùng ở ví dụ hoàn chỉnh bên dưới)

Trong **dependencies**:

~~~groovy
dependencies {
    implementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )
    testImplementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )

    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

**BOM_COORDINATES** đến từ Spring Boot Gradle Plugin, chỉ đúng bộ **spring-boot-dependencies** đi cùng phiên bản plugin. **platform(...)** đưa các version constraints của BOM vào configuration đó và các configuration kế thừa phù hợp. Vì scope có thể khác nhau, ví dụ khai báo platform ở **implementation** và **testImplementation** để minh bạch cả main/test.

**platform** dùng các version được BOM khuyến nghị làm constraints; nếu có các yêu cầu/constraints khác trong dependency graph, phiên bản được resolve có thể khác BOM. **enforcedPlatform** đặt ràng buộc mạnh hơn và có thể ảnh hưởng người tiêu thụ library khi publish; không chuyển sang enforcedPlatform một cách tùy tiện để “sửa” xung đột mà chưa phân tích nguyên nhân.

**Điểm mạnh:** sử dụng cơ chế gốc của Gradle, thường giảm overhead. **Điểm cần nhớ:** không dùng cách override property kiểu **ext['slf4j.version']** giống Spring dependency-management plugin để đổi version bên trong BOM; phải dùng dependency constraints/override phù hợp của Gradle và kiểm chứng graph.

### 7.3. Phương án B — Spring Dependency Management Plugin

Một lựa chọn khác trong Groovy DSL:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Khi Spring Boot plugin và **io.spring.dependency-management** cùng được áp dụng, Boot tích hợp để import BOM **spring-boot-dependencies** tương ứng; các starter trong ví dụ không cần version tường minh. Cơ chế này cho phép override một số managed versions qua property của BOM, ví dụ **ext['slf4j.version']** với property có trong nhánh Boot tương ứng. Chỉ override khi đã kiểm tra tương thích, vì Spring Boot đã thử nghiệm một tập dependency versions đi cùng nhau.

Đây là **phương án thay thế** phương án A. Không cần dùng đồng thời cả hai phương án cho cùng bộ dependency chỉ để “chắc ăn”: kết quả cuối cùng có thể chịu nhiều cơ chế constraints/management khó phân tích. Chọn một chính sách rõ ràng cho project, và nhớ **Gradle không có chức năng parent POM tương đương Maven**.

### 7.4. BOM không tự thêm thư viện

Dù dùng phương án A hay B, BOM chỉ quản lý **các phiên bản có thể áp dụng**, không tự thêm mọi starter. Nếu chưa khai báo **spring-boot-starter-web**, ứng dụng sẽ không tự có Spring MVC controller/server. Nếu chưa khai báo **spring-boot-starter-test**, project không tự có bộ công cụ kiểm thử tương ứng chỉ vì đã nhập BOM.

BOM cũng không quản lý tất cả thư viện trên internet. Với một dependency không nằm trong managed set, bạn phải chọn version/constraint hoặc version catalog phù hợp. Đừng bỏ mọi version khỏi mọi dependency rồi dự đoán Gradle sẽ tự điền.

Nguồn Spring Boot: https://docs.spring.io/spring-boot/3.5/gradle-plugin/managing-dependencies.html

## 8. Ví dụ hoàn chỉnh, có thể chạy: một ứng dụng Spring Boot Gradle

Ví dụ kỹ thuật chọn **Spring Boot 3.5.16**, **Java 17** và **Gradle Wrapper 8.14**. Đây là một tổ hợp phục vụ minh họa nằm trong dải tương thích được tài liệu Boot 3.5 công bố; dự án thật cần kiểm tra phiên bản được tổ chức hỗ trợ và các plugin bổ sung. Dùng **Gradle Groovy DSL** và **native BOM platform**, chỉ đưa các dependency cần cho endpoint/test.

### 8.1. Tạo project và Wrapper

Tạo project Gradle có Java 17, ví dụ qua Spring Initializr, với tên **order-service**, sau đó giữ các tệp Wrapper đã tạo và chọn Gradle 8.14 theo quy trình cập nhật Wrapper được tài liệu Gradle hỗ trợ. Bản ví dụ bên dưới gồm các tệp nguồn cấu hình và Java; các lệnh **./gradlew** giả định Wrapper đã tồn tại và đúng phiên bản.

Cấu trúc cụ thể:

~~~text
order-service/
├── settings.gradle
├── build.gradle
├── gradlew                 # Wrapper do công cụ tạo project cung cấp
├── gradlew.bat
├── gradle/wrapper/...      # distributionUrl và Wrapper JAR
└── src/
    ├── main/java/com/example/orders/
    │   ├── OrderServiceApplication.java
    │   └── PingController.java
    └── test/java/com/example/orders/
        └── PingControllerTests.java
~~~

### 8.2. settings.gradle

~~~groovy
rootProject.name = 'order-service'
~~~

Điều này xác định project name cho Gradle. Nếu build script không override archive name, mặc định Boot JAR sử dụng **order-service** làm base name. Nó không tự tạo Java package **com.example.orders**; package được viết trong source Java.

### 8.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
}

group = 'com.example.training'
version = '1.0.0-SNAPSHOT'

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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**Vì sao cấu hình này đủ?**

- **java** plugin tạo các Java source sets, classpaths và tasks như compileJava/test.
- **org.springframework.boot** plugin bổ sung bootJar/bootRun cho ứng dụng.
- **group + version + rootProject.name** mô tả định danh artifact của chính service.
- **toolchain Java 17** yêu cầu JDK thích hợp để compile/test; không tự thay đổi JVM mà Gradle daemon đang sử dụng.
- **repositories { mavenCentral() }** cho phép lấy thư viện đã publish; plugin Boot được giải qua cơ chế plugin repositories riêng.
- **platform(BOM_COORDINATES)** cung cấp managed version constraints phù hợp với Boot plugin.
- **starter-web** đưa các thành phần web cần cho controller; **starter-test** và JUnit launcher phục vụ kiểm thử.
- **useJUnitPlatform()** yêu cầu Gradle test task chạy trên JUnit Platform.

Không cần ghi version riêng cho các Boot starters ở đây vì platform đã quản lý. Lệnh **./gradlew --version** phải cho thấy đúng bản Gradle/JVM đang chạy. Dùng JDK 17+ tương thích với Spring Boot 3.5 và Gradle 8.14; với bài này nên kiểm thử trên JDK 17 để khớp runtime mục tiêu.

### 8.4. Java application class

Tệp **src/main/java/com/example/orders/OrderServiceApplication.java**:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderServiceApplication.class, args);
    }
}
~~~

### 8.5. Controller trả response cố định

Tệp **src/main/java/com/example/orders/PingController.java**:

~~~java
package com.example.orders;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
~~~

Main class có package **com.example.orders**, nên Spring Boot component scanning mặc định tìm thấy controller cùng package. Java package không phụ thuộc vào việc Gradle project khai báo group là **com.example.training**.

### 8.6. Kiểm thử endpoint bằng Spring Boot Test

Tệp **src/test/java/com/example/orders/PingControllerTests.java**:

~~~java
package com.example.orders;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PingControllerTests {

    @Autowired
    private MockMvc mvc;

    @Test
    void pingReturnsPong() throws Exception {
        mvc.perform(get("/ping"))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"));
    }
}
~~~

**testImplementation** làm JUnit/Spring Boot Test và MockMvc có mặt trên test classpath. Các thư viện test không phải thành phần HTTP runtime của ứng dụng và thông thường không đi vào executable JAR. Nếu xóa **starter-test**, Java main vẫn có thể compile nhưng test code sẽ không có những thư viện cần thiết.

### 8.7. Build, kiểm tra và chạy

Trên Linux/macOS, đứng ở thư mục gốc:

~~~bash
./gradlew --version
./gradlew clean test bootJar
java -jar build/libs/order-service-1.0.0-SNAPSHOT.jar
~~~

Trên Windows, chạy **gradlew.bat** thay cho **./gradlew**. **build/libs/order-service-1.0.0-SNAPSHOT.jar** là tên dự kiến với giá trị name/version hiện tại và cấu hình archive mặc định; hãy kiểm tra tên thực tế nếu project có custom archive settings.

Sau khi ứng dụng khởi động với cổng 8080 mặc định, ở terminal thứ hai:

~~~bash
curl http://localhost:8080/ping
~~~

Response body mong đợi chính xác:

~~~text
pong
~~~

Kết quả build logs không cố định theo môi trường, Gradle cache hay plugin versions. Endpoint **/ping** mới cho output body được xác định bởi source code. Nếu ứng dụng đã đặt **server.port** khác, URL cần thay cho phù hợp.

Lệnh **bootJar** đóng gói executable Spring Boot archive chứa ứng dụng cùng runtime dependencies. Nó không tự publish lên Maven repository; project.version và group vẫn chưa làm một release xuất hiện ngoài máy build.

## 9. Cùng ý tưởng với Kotlin DSL

Nếu project sử dụng **build.gradle.kts**, không dán cú pháp Groovy nguyên xi. Một cấu hình Kotlin DSL tương đương cho core settings (thay thế hoàn toàn build.gradle của demo) là:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.16"
}

group = "com.example.training"
version = "1.0.0-SNAPSHOT"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation(
        platform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    )
    testImplementation(
        platform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    )

    implementation("org.springframework.boot:spring-boot-starter-web")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Trong **settings.gradle.kts**:

~~~kotlin
rootProject.name = "order-service"
~~~

Khác biệt dễ thấy: Kotlin dùng hàm như **implementation("...")**, Groovy thường dùng **implementation '...'**. Tương tự, Groovy **group = '...'** và Kotlin **group = "..."**; không trộn ký hiệu Gradle task syntax hay quoting của hai DSL khi copy cấu hình.

Các tệp Java phần 8 dùng được cho cả hai DSL vì cách khai báo build không đổi nội dung Java source.

## 10. Project dependency và multi-project build

Không phải dependency nào cũng được tải từ Maven Central. Nếu một Gradle build có các subproject **api** và **common**, có thể khai báo đường phụ thuộc bằng **project(...)**.

Ví dụ **settings.gradle** của một project nhiều module:

~~~groovy
rootProject.name = 'business-system'
include 'api', 'common'
~~~

Trong **api/build.gradle**, nếu Java plugin và những cấu hình phụ thuộc đã được áp dụng:

~~~groovy
dependencies {
    implementation project(':common')
}
~~~

Gradle dùng output/variants của project **:common** theo quan hệ build thay vì tra **:common** như một artifact external trên Maven Central. Cấu hình này có thể kéo theo thứ tự build, classpath và transitive project dependencies phù hợp.

Một subproject có **name** riêng (thường từ **settings.gradle**), và có thể có **group/version** riêng nếu cần publish. Không giả định **group/version của root** luôn tự động được đặt cho tất cả child project theo một chính sách; khi cần hãy định nghĩa trong từng module hoặc convention plugin của tổ chức.

Với module Java library, thường nên áp dụng **java-library** và dùng **api** cho các dependencies thật sự lộ ra trong public types; service ứng dụng Boot chủ yếu dùng **implementation**. Trong multi-project, việc áp dụng Boot plugin cho mọi module dù chỉ có module app cần bootJar thường gây đóng gói/lifecycle khó quản lý, nên cần chọn plugin theo vai trò module.

## 11. Xem Gradle thực sự resolve được dependency nào

Một dependency khai báo là **yêu cầu đầu vào**, chưa chắc version cuối cùng đúng như người viết dự đoán vì Gradle có transitive dependencies, constraints, platform và conflict resolution.

### 11.1. Liệt kê configurations và resolved dependencies

Tại root project single-module demo:

~~~bash
./gradlew dependencies
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
~~~

Đọc mỗi cây theo mục đích:

- **compileClasspath**: thư viện compiler nhìn thấy khi compile main.
- **runtimeClasspath**: thư viện khả dụng cho ứng dụng lúc chạy và thường được dùng khi tạo executable Boot JAR.
- **testRuntimeClasspath**: classpath để test chạy; thường rộng hơn vì có test tools.
- **implementation** nếu quan sát trực tiếp thường mô tả **khai báo**, không phải lúc nào là configuration dùng để resolve đầy đủ. Khi cần versions cuối cùng, ưu tiên cấu hình resolvable như runtimeClasspath.

Các nhánh dependency có thể mang ký hiệu cho thấy version được chọn khác yêu cầu, constraints hoặc dependencies trùng. Nội dung và cách trình bày thay đổi theo Gradle version, vì vậy không nên sao chép một cây output cố định làm bằng chứng cho project khác.

### 11.2. Vì sao version của một thư viện khác dự kiến?

Dùng:

~~~bash
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

**dependencyInsight** tập trung vào một dependency và nguyên nhân chọn version/đường dẫn phụ thuộc trong một configuration. Nếu project không dùng một module nhất định, truy vấn có thể không tìm thấy module đó; điều này không chứng minh repository bị lỗi.

Đối với multi-project, ghi đúng project path, ví dụ **./gradlew :api:dependencyInsight --dependency spring-core --configuration runtimeClasspath** khi module **:api** có configuration đó.

### 11.3. Kiểm tra group/version/name thực tế

~~~bash
./gradlew properties
./gradlew --version
./gradlew tasks --all
~~~

Tìm **group**, **name**, **version** trong properties. **--version** cho biết Gradle/JVM đang chạy; nó không in project.version của service. **tasks --all** giúp xác định có **bootJar**, **test**, **dependencies** hay các task do plugin khác thêm.

Đừng nhầm **group/version được hiển thị trong project properties** với **group/version của thư viện trong dependency graph**. Hai cấp thuộc tính hoàn toàn khác nhau.

## 12. Thay đổi phiên bản dependency cho đúng

### 12.1. Dependency có version tường minh

Đối với một module không thuộc BOM managed set, có thể khai báo version cố định:

~~~groovy
dependencies {
    implementation 'com.google.guava:guava:33.4.8-jre'
}
~~~

Version cố định giúp dễ truy vết yêu cầu hơn version động kiểu **1.+**, **latest.release** hoặc snapshot không kiểm soát. Nhưng một phiên bản được yêu cầu vẫn có thể không phải phiên bản cuối cùng được resolve nếu graph có constraints/selection rules khác; xác nhận bằng **dependencyInsight**.

### 12.2. Library được Spring Boot BOM quản lý

Với starter hoặc thư viện có trong BOM, ưu tiên để BOM quản lý version, trừ khi có lý do đủ rõ để override. Spring Boot kiểm thử bộ thư viện tương thích theo từng release; tự nâng một library lõi có thể phá một API liên quan dù **bootJar** vẫn tạo thành công.

Nếu cần override:
1. Xác định thư viện và version hiện tại bằng **dependencyInsight**.
2. Xem **Spring Boot Dependency Versions** của đúng release đang dùng.
3. Chọn version mục tiêu và kiểm tra compatibility notes.
4. Áp dụng version/constraint theo cơ chế BOM đã chọn (native platform hoặc dependency-management plugin).
5. Chạy lại compile, unit/integration test và thử artifact/runtime thật.

**Native BOM** không dùng cú pháp override property của Maven BOM như một Maven parent. **Spring dependency-management plugin** có thể hỗ trợ property overrides theo tài liệu của nó. Không trộn hai cơ chế tùy tiện.

### 12.3. Version catalog giúp tập trung, không thay thế BOM

Dự án nhiều module có thể lưu aliases trong **gradle/libs.versions.toml**. Ví dụ tệp version catalog:

~~~toml
[versions]
guava = "33.4.8-jre"

[libraries]
guava = { module = "com.google.guava:guava", version.ref = "guava" }
~~~

Khi version catalog được Gradle nhận theo vị trí mặc định, trong Groovy DSL:

~~~groovy
dependencies {
    implementation libs.guava
}
~~~

Điều này tiện khi nhiều module cần cùng một thư viện ngoại vi. **Version catalog chỉ giúp tập trung khai báo/alias, không tự thêm repositories và không tự thay thế Gradle BOM conflict resolution**. Với dependency đã do Boot BOM quản lý, thường không cần sao chép cứng version vào catalog trừ khi tổ chức có chủ đích quản lý khác.

## 13. Tính lặp lại và an toàn của dependency resolution

Bản build ổn định cần nhiều hơn group/version và một dòng mavenCentral():

- **Ghim Gradle Wrapper** trong VCS để laptop và CI dùng cùng Gradle distribution; quản lý Java toolchain/JDK riêng.
- **Ghim Spring Boot plugin version** và xác nhận nhánh Boot tương thích với phiên bản Gradle/Java đã chọn.
- **Ưu tiên version cố định/BOM đã kiểm chứng**; tránh dynamic versions hoặc snapshots không được kiểm soát trong bản dựng phát hành.
- **Kiểm tra nguồn repository**. Không tùy tiện thêm repository chưa được kiểm chứng, vì cùng coordinates có thể được phục vụ từ các nguồn khác nhau.
- **Giữ secrets ngoài repository**; dùng env vars, Gradle user-home hoặc hệ thống secret management của CI để xác thực kho private.
- **Quan sát graph thực tế** bằng dependencies và dependencyInsight; kiểm tra CVE/updates theo quy trình bảo mật của tổ chức.
- **Cân nhắc dependency locking và dependency verification** khi cần kết quả tái lập/kiểm tra checksum nghiêm ngặt. Lock files, verification metadata và policy repositories cần được quản lý và review như mã nguồn.
- **Không coi build thành công là deploy thành công**: JVM, cấu hình datasource, network, secrets và readiness vẫn thuộc môi trường runtime.

Tài liệu:
- https://docs.gradle.org/current/userguide/dependency_locking.html
- https://docs.gradle.org/current/userguide/dependency_verification.html

### Đừng khắc phục mọi lỗi bằng --refresh-dependencies

**./gradlew --refresh-dependencies** yêu cầu Gradle kiểm tra/tải lại metadata/artifacts cần thiết theo quy tắc cache. Nó hữu ích khi nghi cache không còn phù hợp, nhưng không sửa được tọa độ sai, BOM thiếu, repository bị chặn, thiếu credentials hoặc version không tồn tại. Trước tiên đọc lỗi resolution và xác minh source/version.

## 14. Lỗi thường gặp và cách xử lý

| Dấu hiệu | Vấn đề cần nghĩ tới | Cách xác minh |
| --- | --- | --- |
| **Plugin [id: 'org.springframework.boot'] was not found** | Thiếu plugin repository, sai plugin version hoặc network/proxy | settings.pluginManagement.repositories, Plugin Portal, version và kết nối |
| **Could not find org.springframework.boot:spring-boot-starter-web** | Repository hoặc BOM/version management chưa cấu hình đúng | repositories / dependencyResolutionManagement và BOM |
| Gradle báo **Could not find :...:.** hoặc no version | Dependency không có version và chưa được managed | platform/BOM, dependency-management plugin hoặc version explicit |
| Chạy test được nhưng **java -jar** báo class thiếu | Library đặt **testImplementation** hoặc **compileOnly** thay vì runtime/implementation | runtimeClasspath, dependencyInsight, bootJar content |
| **Cannot resolve external dependency ... because no repositories are defined** | Chưa khai báo source tải library | repositories { mavenCentral() } hoặc settings dependencyResolutionManagement |
| **Build was configured to prefer settings repositories over project repositories** | Cấu hình repository tập trung và project repos xung đột | repositoriesMode và nơi khai báo |
| **401/403** với private Maven repository | Thiếu/sai credentials, quyền hoặc token hết hạn | CI secrets, repo URL, credentials, proxy |
| **404** khi resolve một library | Sai group:name:version hoặc nguồn không có artifact | Tọa độ từ nhà phát hành, URL đúng và repository support |
| Output JAR mang tên không mong muốn | project.name/version khác dự đoán hoặc có custom archive | settings.gradle, Gradle properties, bootJar archive settings |
| Đổi **version** nhưng Spring Boot vẫn bản cũ | Đã đổi project.version thay vì Boot plugin/BOM version | plugins block, dependencies graph |
| **No signature of method: api()** | Dùng **api** khi project không có java-library plugin/configuration phù hợp | plugins block, dependency configurations |
| **No matching toolchains found** | Chưa có JDK đúng mức và chưa cấu hình provisioning | java.toolchain, JDK cài đặt, toolchain repositories |
| Compile pass nhưng test thiếu JUnit | Test dependency scope hoặc JUnit Platform task config chưa đủ | testRuntimeClasspath, starter-test, useJUnitPlatform |
| Module nội bộ không resolve qua **project(':x')** | Tên subproject/path không tồn tại hoặc chưa include | settings.gradle, ./gradlew projects |
| Build chỉ chạy trên laptop có **mavenLocal()** | Đã dùng artifact chỉ tồn tại ở máy cá nhân | Repository policy, remove local source hoặc publish artifact chuẩn |

Khi gặp lỗi, xác định **plugin resolution**, **dependency resolution**, **compile**, **test**, **packaging** hay **runtime** đang thất bại. Phân tích theo đúng tầng giúp tránh sửa những thứ không liên quan.

## 15. Bài tập thực hành có lời giải

### Bài tập 1: Đổi version của chính ứng dụng

Bạn có:

~~~groovy
group = 'com.example.training'
version = '1.0.0-SNAPSHOT'
~~~

Yêu cầu build ứng dụng cùng source thành **1.1.0-SNAPSHOT**. Sửa dòng **version** thành **1.1.0-SNAPSHOT** và chạy **./gradlew bootJar**. Nếu giữ archive defaults, tên JAR tương ứng chuyển từ **order-service-1.0.0-SNAPSHOT.jar** sang **order-service-1.1.0-SNAPSHOT.jar**.

**Không cần sửa** version của Spring Boot plugin chỉ để đổi định danh của ứng dụng. Nếu đổi project.name ở settings, archive base name mới có thể đổi theo.

### Bài tập 2: Thêm thư viện chỉ dùng trong test

Thêm một test library đã được project/BOM quản lý vào **testImplementation**, rồi chạy:

~~~bash
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencies --configuration runtimeClasspath
~~~

Hãy quan sát: test-only library thường nằm trong **testRuntimeClasspath** nhưng không nằm trong main **runtimeClasspath** trừ khi một dependency main khác cũng kéo nó vào. Vì vậy test libraries thường không được đóng vào Boot JAR.

### Bài tập 3: Repository nào ảnh hưởng starter-web?

Nếu project đã resolve plugin Spring Boot nhưng báo không tải được **starter-web**, cần kiểm tra **repositories của dependencies**, quyền mạng và BOM/version management. Việc thêm một plugin repo vào **pluginManagement.repositories** không nhất thiết cấp nguồn tải starter-web. Hai repository chains phục vụ hai đối tượng khác nhau.

### Bài tập 4: Đọc lý do một version được chọn

Chạy:

~~~bash
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
~~~

Tìm đường phụ thuộc nào kéo module vào classpath và constraint/version nào quyết định bản thực sự được dùng. Sau đó đối chiếu với Spring Boot BOM đang import; khi có nhiều version yêu cầu, hãy phân tích xung đột trước khi ép version.

### Bài tập 5: Phát hiện lỗi trong một đoạn cấu hình

Đoạn có lỗi:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
}

group = 'com.example'
version = '2.0.0'

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

**Có ít nhất hai điểm cần bổ sung**: một dependency repository (ví dụ **mavenCentral()** nếu settings chưa cung cấp), và một cơ chế BOM/dependency management để starter không cần version. Định nghĩa **group/version** của project không thể thay thế hai phần này.

Một đáp án dùng native BOM:

~~~groovy
repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Trong project thật, nếu dependency repositories đã khai báo tập trung ở settings với **FAIL_ON_PROJECT_REPOS**, **không** bổ sung khối repositories ở build.gradle; chỉ thêm phần BOM/dependencies thích hợp.

## 16. Checklist trước khi chốt cấu hình

- [ ] **settings.gradle** đặt đúng **rootProject.name**, các included subprojects nếu có.
- [ ] **group** và **version** biểu thị đúng định danh của sản phẩm; phân biệt với tên Java package, Spring app và version của plugin.
- [ ] **plugins** áp dụng Java và Spring Boot Gradle Plugin tương thích với Gradle/JDK dự án.
- [ ] **repositories** khai báo tại project hoặc settings đúng chính sách; plugin repos và dependency repos được xác định riêng.
- [ ] **dependencies** dùng đúng configuration: implementation, runtimeOnly, compileOnly, annotationProcessor, testImplementation, testRuntimeOnly.
- [ ] Dùng **native platform BOM** hoặc **io.spring.dependency-management**, tránh dựa vào version trống mà không có BOM.
- [ ] Phân tích phiên bản cuối cùng bằng **dependencies/dependencyInsight**; đánh giá mọi override của Spring Boot managed versions.
- [ ] Lưu Wrapper, kiểm tra build/test, **bootJar** và **java -jar** thực tế.
- [ ] Không commit repository credentials; hạn chế dynamic versions/repositories không được kiểm soát.
- [ ] Khi nhiều module, chọn đúng project dependency và áp dụng Boot plugin theo vai trò module.

**Ghi nhớ:** **group/version** trả lời “artifact của project này mang danh tính gì”; **repositories** trả lời “Gradle có thể tìm thư viện ở nguồn nào”; **dependencies** trả lời “cần thư viện nào và dùng trong classpath nào”; còn **Spring Boot plugin + BOM** quyết định cách build ứng dụng và bộ phiên bản thư viện Spring Boot phù hợp. Hiểu ranh giới này giúp đọc cấu hình nhanh, sửa lỗi resolution đúng chỗ và tạo được artifact ổn định.

## Tài liệu tham khảo chính thức

- Spring Boot 3.5 — Gradle Plugin: https://docs.spring.io/spring-boot/3.5/gradle-plugin/
- Spring Boot 3.5 — Getting Started: https://docs.spring.io/spring-boot/3.5/gradle-plugin/getting-started.html
- Spring Boot 3.5 — Managing Dependencies: https://docs.spring.io/spring-boot/3.5/gradle-plugin/managing-dependencies.html
- Spring Boot 3.5 — Packaging Executable Archives: https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html
- Gradle — Declaring Dependencies: https://docs.gradle.org/current/userguide/declaring_dependencies_basics.html
- Gradle — Dependency Configurations: https://docs.gradle.org/current/userguide/dependency_configurations.html
- Gradle — Declaring Repositories: https://docs.gradle.org/current/userguide/declaring_repositories.html
- Gradle — Centralizing Repository Declarations: https://docs.gradle.org/current/userguide/centralizing_repositories.html
- Gradle — Multi-Project Builds: https://docs.gradle.org/current/userguide/multi_project_builds.html
- Gradle — Dependency Locking: https://docs.gradle.org/current/userguide/dependency_locking.html
- Gradle — Dependency Verification: https://docs.gradle.org/current/userguide/dependency_verification.html
- Gradle — Gradle Wrapper: https://docs.gradle.org/current/userguide/gradle_wrapper.html

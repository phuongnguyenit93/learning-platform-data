# Phân biệt publishToMavenLocal với publish lên repository từ xa

**Chủ đề:** Build Tool Gradle  
**Nhóm kiến thức:** Xuất bản artifact

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích đúng khái niệm **publication**, **Maven coordinates**, **artifact**, **POM**, **Gradle Module Metadata** và **repository**, thay vì đồng nhất “đã build JAR” với “đã publish”.
2. Phân biệt **publishToMavenLocal** (cài publication vào kho Maven cục bộ của máy) và **publish** (gửi publications đến các repositories được khai báo ở **publishing.repositories**).
3. Nhận ra rằng **publish không tự bao gồm publishToMavenLocal**, và **publishToMavenLocal không cần một mavenLocal() trong publishing.repositories**.
4. Phân biệt hai nơi khai báo repository: **repositories** hoặc dependencyResolutionManagement.repositories để **đọc dependencies**, và **publishing.repositories** để **ghi artifacts**.
5. Biết tên các Gradle tasks được sinh tự động như **publishMavenJavaPublicationToMavenLocal** và **publishMavenJavaPublicationToStagingDirectoryRepository**, cùng ý nghĩa của task tổng hợp **publish**.
6. Tạo và chạy dự án **Gradle Groovy DSL + Java 17** có **java-library** và **maven-publish**, sinh binary JAR, sources JAR, Javadoc JAR và publication metadata.
7. Thử hai lộ trình: xuất bản vào **Maven Local** và xuất bản vào một **repository định dạng Maven nằm trong thư mục build/** (mô phỏng đích publish, không phải máy chủ từ xa).
8. Tạo consumer project riêng, xác minh có thể **resolve cùng group:artifact:version** lần lượt từ Maven Local và từ repository thư mục, rồi chạy Java 17 với stdout xác định.
9. Cấu hình đúng một **repository HTTPS từ xa** khi có máy chủ thật, dùng **credentials(PasswordCredentials)** và Gradle properties/environment variables thay vì hardcode secrets.
10. Thiết kế quy trình CI/release gồm kiểm thử, provenance, signing, snapshot/release policy, chỉ chọn đúng upload task, kiểm tra artifact đã xuất hiện và xử lý các lỗi 401/403/404/409.
11. Hiểu vì sao **mavenLocal() không nên là dependency repository mặc định của CI/production**, vì artifacts có thể bị ghi đè, không có provenance rõ và làm build khó tái lập.
12. Biết giới hạn của Maven Central hiện hành: không thể suy rằng generic maven-publish với một URL OSSRH cũ là đủ để phát hành lên Central.

**Kết luận trước:** Trong Gradle Maven Publish Plugin, **publishToMavenLocal** phục vụ thử nghiệm tích hợp trên chính máy đang chạy Gradle; **publish** xuất bản tới các repository **mà dự án chủ động khai báo làm nơi nhận artifact**. Repository đó có thể là thư mục local hoặc dịch vụ HTTPS thật. Vì vậy **tên task publish không tự bảo đảm đã upload ra mạng**, và một publication xuất hiện dưới ~/.m2/repository **không có nghĩa đồng nghiệp hoặc CI đã có thể tải được nó**.

## 1. Thuật ngữ nền tảng: build, publication và repository

Một thư viện Java được Gradle biên dịch có thể có:

~~~text
build/classes/java/main/demo/lib/Greetings.class
build/libs/greeting-kit-1.0.0.jar
~~~

Những file này là **build outputs** trong workspace. Chúng không tự trở thành một dependency có thể được consumer lấy bằng Maven coordinates từ một repository.

Để publish đúng chuẩn Maven, bạn cần:

- **Maven publication**: định nghĩa component/artifacts nào được xuất bản.
- **Identity**: groupId, artifactId, version.
- **Repository destination**: nơi có cấu trúc Maven để lưu file.
- **Metadata**: POM và, khi phù hợp, Gradle Module Metadata.
- **Task publish**: thực hiện xuất bản đến một đích cụ thể.

Một module ví dụ:

~~~text
groupId    = edu.example
artifactId = greeting-kit
version    = 1.0.0

Dependency notation:
edu.example:greeting-kit:1.0.0
~~~

Đường dẫn Maven thường ánh xạ groupId thành nhiều thư mục:

~~~text
edu/example/greeting-kit/1.0.0/
    greeting-kit-1.0.0.jar
    greeting-kit-1.0.0.pom
    greeting-kit-1.0.0-sources.jar
    greeting-kit-1.0.0-javadoc.jar
    greeting-kit-1.0.0.module
    ...
~~~

**Không nhầm:** Filename/path trong build/libs và filename/path trong repository có thể giống, nhưng nơi lưu và cách consumer tìm thấy chúng **khác nhau**. Consumer thường chọn dependency theo **coordinates + repository**, không dò file build/libs của một project tùy ý.

### 1.1. Những khái niệm dễ trộn lẫn

| Khái niệm | Vai trò | Điều nó không tự làm |
|---|---|---|
| **jar** | Tạo JAR nhị phân cho Java component | Không tự upload lên Maven repository |
| **assemble/build** | Tạo outputs và có thể chạy validations | Không tự cài vào ~/.m2 hoặc publish remote |
| **MavenPublication** | Mô tả artifacts, coordinates và metadata | Không tự publish nếu không gọi task tương ứng |
| **publishToMavenLocal** | Ghi tất cả Maven publications vào Maven Local của tài khoản chạy Gradle | Không upload lên server từ xa |
| **publish** | Ghi tất cả publications tới tất cả repositories ở publishing.repositories | Không tự ghi vào Maven Local |
| **publish<Pub>PublicationTo<Repo>Repository** | Ghi một publication vào một repository cụ thể | Không mặc nhiên ghi sang những đích khác |
| **mavenLocal() khi resolve** | Cho consumer đọc Maven Local như dependency repository | Không publish artifact |
| **mavenCentral() khi resolve** | Cho consumer tải dependencies từ Maven Central | Không tạo quyền publish lên Maven Central |

**Điểm quan trọng:** Bản thân **maven-publish** là core plugin Gradle. Không cần ghi version cho id 'maven-publish'; chỉ cần một Gradle distribution hỗ trợ API. Bạn vẫn phải tạo **MavenPublication** như mavenJava(MavenPublication) trong build.gradle.

## 2. publishToMavenLocal: “install” lên chính máy đang chạy Gradle

Gradle task:

~~~bash
./gradlew publishToMavenLocal
~~~

được Maven Publish Plugin tạo khi có Maven publications. Nó copy/generate artifacts và metadata vào **Maven Local repository**, thường là:

~~~text
~/.m2/repository
~~~

trên Linux/macOS và tương ứng thư mục người dùng trên Windows:

~~~text
C:\Users\<user>\.m2\repository
~~~

Dấu <user> ở đây là **ký hiệu người dùng**, không phải tên thật cần điền trong Gradle script.

**Maven Local là một kho theo người dùng trên máy hiện tại**, không phải kho chia sẻ tự động. Nếu laptop A publishToMavenLocal, laptop B và CI runner khác **không tự nhìn thấy** artifact ấy.

### 2.1. Maven Local có thể ở chỗ khác ~/.m2/repository

Gradle tìm Maven Local dựa trên cấu hình có thứ tự ưu tiên:

1. Java system property **maven.repo.local**, nếu có.
2. **localRepository** trong ~/.m2/settings.xml, nếu có.
3. **localRepository** trong $M2_HOME/conf/settings.xml, nếu được cấu hình.
4. Mặc định **~/.m2/repository**.

Vì vậy đừng hardcode ~/.m2/repository rồi kết luận Gradle sai nếu file thật được ghi nơi khác. Kiểm tra system properties, Maven settings và môi trường máy.

### 2.2. Không cần publishing.repositories.mavenLocal()

Với publication đã tồn tại, Gradle tự đăng ký task kiểu **PublishToMavenLocal**. Nó **không yêu cầu** bạn khai báo một target mavenLocal() trong publishing.repositories.

Ví dụ:

~~~groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }
}
~~~

Chỉ riêng cấu hình trên đã đủ để có task **publishToMavenLocal** cho publication mavenJava (các thông tin group/version cần thiết được cấu hình ở build thực tế).

**Không thêm một repository tên MavenLocal vào publishing.repositories chỉ để làm task này xuất hiện.** Maven Publish Plugin đã cung cấp tác vụ chuyên biệt cho Maven Local.

### 2.3. Tên task và phạm vi

Giả sử tên publication là **mavenJava**. Gradle tạo:

~~~text
publishMavenJavaPublicationToMavenLocal
publishToMavenLocal
~~~

- **publishMavenJavaPublicationToMavenLocal**: chỉ xuất bản publication mavenJava vào Maven Local.
- **publishToMavenLocal**: tập hợp mọi task PublishToMavenLocal của mọi Maven publications trong project đó.
- Nếu có nhiều publications (mavenJava, docs, marker...), aggregate task sẽ xử lý chúng theo mô hình hiện tại.

**Trong multi-project build:** Một lệnh **:lib:publishToMavenLocal** nhắm project :lib. Đừng nhầm nó với mọi publication của toàn repository; cần xác định project paths thực sự được yêu cầu. Một root task không tự đại diện cho mọi subprojects.

### 2.4. Maven Local giúp việc gì?

Những trường hợp hợp lý:

- Bạn sửa một library và muốn **thử nhanh một consumer ở cùng máy**.
- Cần kiểm tra **POM/Gradle Module Metadata** và sources/Javadoc classifiers trước release.
- Muốn kiểm tra migration/relocation POM trong một consumer tạm.
- Phát triển plugin/module liên kết Maven, trong khi chưa thiết lập remote staging repository.
- Thử **Maven interoperability**: một Maven hoặc Gradle consumer có thể lấy artifact vừa install.

Những điều **không nên dùng** Maven Local như bằng chứng:

- Không chứng minh artifact đã được lưu trên một server mà team truy cập được.
- Không chứng minh checksum/signature/provenance đạt yêu cầu release.
- Không chứng minh CI sẽ resolve được nếu CI không có cùng nội dung Maven Local.
- Không chứng minh phiên bản là immutable — local artifacts rất dễ bị ghi đè.

### 2.5. PublishToMavenLocal không sinh checksum như publish repository

Theo Gradle User Manual, **publishToMavenLocal không tạo các checksum files** trong Maven Local. Khi xuất bản vào Maven repository được cấu hình, Gradle có thể tạo checksum files bên cạnh artifacts theo chính sách publication/repository.

Vì vậy nếu mục tiêu là kiểm tra file **.sha256/.sha512** của gói phát hành, nên publish thử vào một repository định dạng Maven qua **file URL** trước, không dùng chỉ Maven Local làm tiêu chuẩn đầy đủ.

## 3. publish: xuất bản tới các repositories được cấu hình

Task:

~~~bash
./gradlew publish
~~~

là một **aggregate task**. Theo Maven Publish Plugin, nó phụ thuộc vào những tasks kiểu:

~~~text
publish<PublicationName>PublicationTo<RepositoryName>Repository
~~~

với mỗi cặp publication/repository được cấu hình.

Ví dụ có một publication mavenJava và một repo tên **stagingDirectory**:

~~~text
publish
    └── publishMavenJavaPublicationToStagingDirectoryRepository
          ├── generatePomFileForMavenJavaPublication
          ├── generateMetadataFileForMavenJavaPublication
          └── các task tạo artifacts cần publish
~~~

Đây là **sơ đồ minh họa**, không cam kết đúng tên/tập mọi dependencies ở mọi Gradle/plugin version. Kiểm tra bằng **./gradlew tasks --all** hoặc **./gradlew publish --dry-run**.

### 3.1. publish không đồng nghĩa remote

Bạn có thể khai báo:

~~~groovy
publishing {
    repositories {
        maven {
            name = 'stagingDirectory'
            url = layout.buildDirectory.dir('demo-repo')
        }
    }
}
~~~

Khi đó:

~~~bash
./gradlew publish
~~~

**ghi vào thư mục build/demo-repo trên máy**, không gửi qua Internet. Nó vẫn là **publish task** vì đó là MavenArtifactRepository được cấu hình, nhưng không phải **remote deployment**.

Muốn upload tới một máy chủ HTTPS thật, cần **repository URL từ xa**, network/permissions và thường là credentials:

~~~groovy
publishing {
    repositories {
        maven {
            name = 'companyReleases'
            url = uri('https://repo.example.invalid/maven/releases')
            // credentials sẽ được cấu hình khi repo thật tồn tại.
        }
    }
}
~~~

**Tên miền .invalid và URL ở trên chỉ là placeholder, không phải server thực tế.** Không chạy lệnh publish với nó và không coi URL ví dụ là đích mà nhóm đang sở hữu.

### 3.2. publish không tự gọi publishToMavenLocal

Ngay cả khi build có cả hai task:

~~~bash
./gradlew publish
./gradlew publishToMavenLocal
~~~

đây là **hai yêu cầu riêng**. Chạy dòng đầu không có nghĩa Gradle đã cài artifact vào Maven Local. Chạy dòng sau không có nghĩa Gradle đã upload lên repository trong publishing.repositories.

**Nếu thực sự cần cả hai** trong workflow local, yêu cầu cả hai:

~~~bash
./gradlew publishToMavenLocal publish
~~~

Nhưng trên CI/release production, thường **không cần Maven Local**; hãy chạy đúng named repository target hoặc aggregate publish theo policy để tránh side effects ngoài ý muốn.

### 3.3. Nếu publishing.repositories trống?

Một project có MavenPublication nhưng **không khai báo repository xuất bản** vẫn có thể có task tổng hợp **publish**; song nó không có target PublishToMavenRepository tương ứng. Vì thế một lệnh publish kết thúc mà không upload đi đâu **không phải bằng chứng remote artifact đã tồn tại**.

**Kiểm tra thực tế:**
- Có repository name + URL trong publishing.repositories không?
- Có task **publishMavenJavaPublicationTo...Repository** trong danh sách task không?
- Lệnh đó có thật sự chạy không?
- Artifact/POM/module metadata có xuất hiện ở destination không?
- Consumer khác có thể resolve từ URL đó không?

Đừng dùng duy nhất dòng **BUILD SUCCESSFUL** để kết luận đã publish lên remote.

### 3.4. Nhiều repositories được cấu hình

Nếu project có:

~~~groovy
publishing {
    repositories {
        maven {
            name = 'staging'
            url = uri('/some/local/staging/path')
        }
        maven {
            name = 'releases'
            url = uri('https://repo.example.invalid/releases')
        }
    }
}
~~~

task **publish** sẽ lên lịch xuất bản publication cho **tất cả repositories** phù hợp. Một nơi là thư mục local và nơi khác là máy chủ, nên chạy publish có thể tạo side effects ở **cả hai**.

Để chỉ nhắm một đích:

~~~bash
./gradlew publishMavenJavaPublicationToStagingRepository
~~~

**Lưu ý:** Tên task lấy từ **publication name** và **repository name**, không phải artifactId hoặc path thư mục. Task riêng tránh upload vô tình khi một build có nhiều đích.

## 4. Hai loại repositories: tải dependency và xuất bản

Trong Gradle có ít nhất ba context repositories thường gặp:

| Context | Khai báo | Chức năng |
|---|---|---|
| **Project dependency repositories** | repositories { mavenCentral() } | Tìm và tải dependencies để compile/run/test |
| **Centralized dependency repositories** | settings.gradle dependencyResolutionManagement { repositories ... } | Tập trung chính sách resolve dependencies cho các projects |
| **Publishing repositories** | publishing { repositories { maven { ... } } } | Nhận những Maven publications mà project upload/ghi |
| **Plugin repositories** | settings.gradle pluginManagement { repositories ... } | Tìm Gradle plugin implementations |

Ba việc khác nhau:
- **Maven Local (mavenLocal()) trong repositories để đọc** không phải publish command.
- **Publishing repository trong publishing** không tự được dùng để resolve dependencies của consumer.
- **Plugin Portal** không phải Maven Central và không phải nơi tự động nhận một Java library MavenPublication.

Ví dụ:

~~~groovy
repositories {
    mavenCentral()
}

publishing {
    repositories {
        maven {
            name = 'stagingDirectory'
            url = layout.buildDirectory.dir('demo-repo')
        }
    }
}
~~~

- **mavenCentral()** trong khối trên đầu được dùng để resolve third-party Java dependencies.
- **stagingDirectory** trong khối publishing là nơi **ghi release artifacts**.
- Không có lệnh nào trong ví dụ này upload lên Maven Central.

### 4.1. Consumer phải tự khai báo repository để đọc

Sau khi publisher ghi:

~~~text
build/demo-repo/edu/example/greeting-kit/1.0.0/...
~~~

một consumer khác muốn resolve module phải khai báo:

~~~groovy
repositories {
    maven {
        url = uri('/absolute/path/to/demo-repo')
    }
}
dependencies {
    implementation 'edu.example:greeting-kit:1.0.0'
}
~~~

Đường dẫn trên là **mẫu**, cần thay bằng path thật của repository. Publisher không “push một cấu hình” làm consumer tự biết repository URL.

Với Maven Local, consumer dùng:

~~~groovy
repositories {
    mavenLocal()
}
~~~

nhưng điều này chỉ hoạt động nếu **Maven Local của consumer** thực sự có module đúng version. Trên máy CI sạch, thường không có artifact local của developer.

### 4.2. Thứ tự repositories ảnh hưởng resolution

Gradle xét repositories theo thứ tự khi resolve metadata/modules. Nếu consumer có:

~~~groovy
repositories {
    mavenLocal()
    mavenCentral()
}
~~~

một phiên bản module trùng tọa độ trong Maven Local có thể **che** phiên bản đúng từ remote. Kết quả:
- Máy developer compile được với JAR mới tự publish.
- CI sạch resolve JAR remote cũ, hoặc không tìm thấy module.
- Cùng group:artifact:version nhưng bytes khác nhau.
- Khó tái hiện lỗi và mất tính reproducibility.

**Khuyến nghị của tài liệu Gradle:** Hạn chế mavenLocal() cho **prototyping**, tránh dùng làm nguồn dependency chuẩn của production/CI. Khi cần test local, nên giới hạn repository bằng content filter hoặc consumer project riêng, không đưa Maven Local mặc định vào mọi build.

## 5. Bài lab hoàn chỉnh: Java 17 library và hai đích publish

Ta tạo một thư viện **greeting-kit** và một consumer độc lập. Bài lab **không upload dữ liệu lên remote thật**, nhưng dùng hai con đường giống Gradle đang phân biệt:

1. **publishToMavenLocal** → Maven Local của tài khoản.
2. **publish** → repository **định dạng Maven** ở build/demo-repo (file-based staging).

Sau đó consumer lần lượt dùng **mavenLocal()** và **file-based Maven repository** để chứng minh **cả hai** chứa module cùng tọa độ và Java app chạy.

### 5.1. Yêu cầu

- JDK 17 hoặc Gradle Java toolchain 17 phù hợp.
- Gradle Wrapper tương thích với JDK/toolchain; khuyến nghị dùng Wrapper được commit.
- Không cần third-party Java library cho code demo.
- **Javadoc và Maven publication** dùng core plugins, không cần community plugin.
- Không cần tài khoản/credential remote trong bài lab.

Cấu trúc:

~~~text
publish-destinations-lab/
├── settings.gradle
├── build.gradle
├── gradlew                         # nếu dùng Wrapper
├── gradlew.bat
├── gradle/wrapper/...               # nếu dùng Wrapper
├── src/main/java/demo/lib/
│   └── Greetings.java
└── consumer/
    ├── settings.gradle
    ├── build.gradle
    └── src/main/java/demo/consumer/
        └── Main.java
~~~

**consumer** là một **Gradle build độc lập** có settings.gradle riêng, không phải subproject được include trong parent settings.gradle. Ta làm vậy để mô phỏng dự án khác sử dụng artifact đã publish, thay vì lén dùng project(':lib') làm dependency.

### 5.2. Parent settings.gradle

~~~groovy
rootProject.name = 'greeting-kit'
~~~

Tên root project là mặc định **artifactId** khi tạo MavenPublication từ components.java và không override artifactId.

### 5.3. Parent build.gradle đầy đủ

~~~groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'edu.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }

    // Sinh sourcesJar, javadocJar và documentation variants.
    withSourcesJar()
    withJavadocJar()
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

tasks.named('javadoc', Javadoc) {
    options.encoding = 'UTF-8'
    options.charSet = 'UTF-8'
    options.docEncoding = 'UTF-8'
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            // Java component: binary + sources/Javadoc variants + metadata.
            from components.java

            pom {
                name = 'Greeting Kit'
                description = 'Java 17 library demonstrating Maven publication targets'
            }
        }
    }

    repositories {
        // File-based Maven repository: an upload destination
        // for demonstration, NOT a remote HTTP server.
        maven {
            name = 'stagingDirectory'
            url = layout.buildDirectory.dir('demo-repo')
        }
    }
}
~~~

**Những điểm phải hiểu:**

- **java-library** tạo Java component và tasks compile/jar/Javadoc.
- **maven-publish** tạo publishing extension và publish tasks.
- **group/version** cùng project.name xác định coordinates **edu.example:greeting-kit:1.0.0**.
- **withSourcesJar()** tạo sources JAR theo chuẩn classifier sources.
- **withJavadocJar()** tạo Javadoc JAR theo chuẩn classifier javadoc.
- **from components.java** đưa Java binary và documentation variants vào Maven publication.
- **pom** cung cấp name/description minh họa, chưa đủ metadata cho mọi public repository.
- **publishing.repositories.maven** với name stagingDirectory nhận artifacts khi dùng **publish**.
- Đích demo-repo ở dưới build/ chỉ là **local directory**, không phải server từ xa.
- Không có mavenLocal() trong publishing.repositories nhưng **publishToMavenLocal vẫn tồn tại**.

**Không thêm các dòng artifact tasks.named('sourcesJar') hoặc artifact tasks.named('javadocJar') vào cùng publication**, vì withSourcesJar/withJavadocJar đã gắn chúng với Java component. Đính kèm lại có thể gây duplicate classifier conflicts.

### 5.4. Thư viện Greetings.java

**src/main/java/demo/lib/Greetings.java**

~~~java
package demo.lib;

/**
 * Public greeting API for the publishing tutorial.
 *
 * <p>This class is stateless and supports Java 17.</p>
 *
 * @since 1.0.0
 */
public final class Greetings {
    private Greetings() {
    }

    /**
     * Creates a greeting for a nonblank name.
     *
     * @param name a nonblank recipient name
     * @return a deterministic greeting
     * @throws IllegalArgumentException when name is null or blank
     */
    public static String hello(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name is blank");
        }
        return "Hello, " + name.strip() + "!";
    }
}
~~~

Code dùng Java 17 hợp lệ: String.isBlank()/strip() có từ Java 11, và method static trả một chuỗi xác định. API documentation giúp Javadoc task sinh HTML hợp lệ.

### 5.5. Tạo các artifacts nhưng chưa publish

Từ root **publish-destinations-lab**, Linux/macOS:

~~~bash
./gradlew clean build
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean build
~~~

Vì thư viện demo chưa khai báo test sources, các test tasks có thể là **NO-SOURCE**. Điều đó không tự chứng minh test suite chất lượng đã chạy. Mục tiêu bước này là tạo/sẵn sàng artifacts và Javadoc theo cấu hình.

Các outputs thông thường:

~~~text
build/libs/greeting-kit-1.0.0.jar
build/libs/greeting-kit-1.0.0-sources.jar
build/libs/greeting-kit-1.0.0-javadoc.jar
build/docs/javadoc/index.html
~~~

Lưu ý **build** có thể không tự chạy sourcesJar/javadocJar trong mọi task wiring tùy Gradle lifecycle và plugin version; nếu muốn tạo chắc chắn để quan sát, chạy:

~~~bash
./gradlew jar sourcesJar javadocJar
~~~

Dùng JDK jar tool:

~~~bash
jar --list --file build/libs/greeting-kit-1.0.0.jar
jar --list --file build/libs/greeting-kit-1.0.0-sources.jar
jar --list --file build/libs/greeting-kit-1.0.0-javadoc.jar
~~~

Các entry cần thấy lần lượt:
- **demo/lib/Greetings.class** trong binary JAR.
- **demo/lib/Greetings.java** trong sources JAR.
- **index.html** và trang **demo/lib/Greetings.html** trong Javadoc JAR.

**Đây mới là giai đoạn xây artifact**, không có bằng chứng bất kỳ consumer repository nào đã nhận gói.

### 5.6. Lộ trình A — publishToMavenLocal

Chạy:

~~~bash
./gradlew publishToMavenLocal --console=plain
~~~

PowerShell:

~~~powershell
.\gradlew.bat publishToMavenLocal --console=plain
~~~

Gradle sẽ lên lịch task:

~~~text
publishMavenJavaPublicationToMavenLocal
~~~

và những prerequisites cần tạo binary/POM/sources/Javadoc/metadata.

Sau thành công, đường dẫn Maven Local thông thường là:

~~~text
~/.m2/repository/edu/example/greeting-kit/1.0.0/
    greeting-kit-1.0.0.jar
    greeting-kit-1.0.0.pom
    greeting-kit-1.0.0-sources.jar
    greeting-kit-1.0.0-javadoc.jar
    greeting-kit-1.0.0.module     # khi Gradle Module Metadata được publish
    ...
~~~

**Nếu Maven Local được redirect**, thay ~/.m2/repository bằng đường dẫn thật. **Không bắt buộc phải có .sha256 hoặc .sha512** trong Maven Local; Gradle documentation ghi rõ publishToMavenLocal không sinh checksum files ở đây.

Kiểm tra trên Unix khi dùng path mặc định:

~~~bash
jar --list --file "$HOME/.m2/repository/edu/example/greeting-kit/1.0.0/greeting-kit-1.0.0.jar"
~~~

Windows PowerShell với path mặc định:

~~~powershell
jar --list --file "$HOME\.m2\repository\edu\example\greeting-kit\1.0.0\greeting-kit-1.0.0.jar"
~~~

**Quan trọng:** Kiểm tra nội dung file có thật; task SUCCESS chưa đủ nếu bạn đang nhìn **Maven Local của một user khác** hoặc tìm sai path.

### 5.7. Lộ trình B — publish vào repository thư mục bằng task publish

Chạy:

~~~bash
./gradlew publish --console=plain
~~~

Vì chỉ có **một** named repository **stagingDirectory**, task tổng hợp publish sẽ gọi:

~~~text
publishMavenJavaPublicationToStagingDirectoryRepository
~~~

Nó ghi Maven publication dưới:

~~~text
build/demo-repo/edu/example/greeting-kit/1.0.0/
    greeting-kit-1.0.0.jar
    greeting-kit-1.0.0.pom
    greeting-kit-1.0.0-sources.jar
    greeting-kit-1.0.0-javadoc.jar
    greeting-kit-1.0.0.module
    các checksum files được tạo theo Gradle/repository policy
~~~

**Đây là publish vào FILE-BASED REPOSITORY, không phải upload từ xa.** Bài lab dùng file repo để bạn có thể quan sát an toàn cùng cơ chế Maven publish task trước khi thay đích bằng HTTPS thật.

Tác dụng của câu lệnh này **không bao gồm publishToMavenLocal**. Nếu bạn mới chạy lộ trình B sau clean trên một máy chưa có Maven Local artifact, đừng đi tìm publication ở ~/.m2 rồi kết luận Gradle đã tự cài nó.

### 5.8. Lộ trình C — chỉ publish một cặp publication/repository

Nếu bạn không muốn chạy aggregate task (đặc biệt trong project có nhiều repositories), chạy tên cụ thể:

~~~bash
./gradlew publishMavenJavaPublicationToStagingDirectoryRepository --console=plain
~~~

Gradle chỉ xuất bản **mavenJava** tới **stagingDirectory**. Nó không tự gửi sang những repositories khác và không tự install vào Maven Local.

**Đọc tên task như một câu:**
- **publish**: thao tác.
- **MavenJavaPublication**: publication tên mavenJava.
- **ToStagingDirectoryRepository**: repository tên stagingDirectory.

Đây là một thói quen hữu ích để tránh upload nhầm khi project sau này có staging, snapshots, releases và internalRepository.

## 6. Consumer Gradle độc lập: phân biệt đúng nơi resolve

Bây giờ tạo một consumer dưới **consumer/** có settings.gradle riêng. Nó chỉ dùng **tọa độ đã publish**, không tham chiếu trực tiếp source project.

### 6.1. consumer/settings.gradle

~~~groovy
rootProject.name = 'greeting-consumer'
~~~

### 6.2. consumer/build.gradle hoàn chỉnh

~~~groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.consumer.Main'
}

repositories {
    // -PrepoMode=staging: lấy từ file repository publisher vừa tạo.
    // Mặc định: đọc Maven Local (chỉ dành cho demo thử nghiệm).
    if (findProperty('repoMode') == 'staging') {
        maven {
            url = uri('../build/demo-repo')
        }
    } else {
        mavenLocal()
    }
}

dependencies {
    implementation 'edu.example:greeting-kit:1.0.0'
}
~~~

**Giải thích:**
- application là core plugin, cung cấp Java tasks và run.
- repoMode là **Gradle project property** để chọn nguồn resolve.
- Khi gọi **-PrepoMode=staging**, consumer đọc repo dạng file của parent publisher.
- Nếu không có property ấy, consumer đọc Maven Local của máy.
- Maven Local trong ví dụ này **chỉ để học/thử**, không phải khuyến nghị bật trong mọi production build.
- implementation trỏ tới **Maven module coordinates**, không dùng implementation project(':parent').

**Đường dẫn tương đối** '../build/demo-repo' được giải quyết từ **consumer project directory**. Với cấu trúc lab, nó dẫn tới **publish-destinations-lab/build/demo-repo**. Nếu di chuyển consumer sang một repo khác, phải thay đường dẫn/URL phù hợp.

### 6.3. consumer/src/main/java/demo/consumer/Main.java

~~~java
package demo.consumer;

import demo.lib.Greetings;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greetings.hello(" Linh "));
    }
}
~~~

Class imports API được đóng trong JAR publisher, không phụ thuộc sources JAR hoặc Javadoc JAR khi chạy.

### 6.4. Chạy consumer từ Maven Local

Từ root, sau **lộ trình A** đã publishToMavenLocal:

Linux/macOS:

~~~bash
cd consumer
../gradlew run --quiet
cd ..
~~~

Windows PowerShell:

~~~powershell
Set-Location consumer
..\gradlew.bat run --quiet
Set-Location ..
~~~

**Stdout do Main.main in:**

~~~text
Hello, Linh!
~~~

Nếu Gradle báo **Could not find edu.example:greeting-kit:1.0.0**, hãy kiểm tra:
- Bạn đã chạy publishToMavenLocal chưa?
- Consumer và publisher đang dùng cùng Maven Local path/user?
- POM và JAR thực sự ở thư mục group/artifact/version?
- Có typo group/artifact/version không?
- Có corporate settings nào thay đổi repository policy không?

Không thêm mavenCentral() như giải pháp mặc định: module demo **không được publish lên Maven Central**.

### 6.5. Chạy consumer từ repository thư mục

Sau **lộ trình B** đã chạy publish:

~~~bash
cd consumer
../gradlew run --quiet -PrepoMode=staging
cd ..
~~~

PowerShell:

~~~powershell
Set-Location consumer
..\gradlew.bat run --quiet -PrepoMode=staging
Set-Location ..
~~~

**Stdout vẫn là:**

~~~text
Hello, Linh!
~~~

Cùng kết quả runtime nhưng **hai cách lấy dependency khác nhau**. Đó là cách kiểm tra chính xác đích publish, thay vì chỉ nhìn tên task.

### 6.6. Dùng javac/java trực tiếp với JAR đã publish

Để xác nhận JAR thật chứa code chạy Java 17, bạn có thể dùng JDK không cần chạy Gradle consumer:

Linux/macOS từ root, sau lộ trình B:

~~~bash
mkdir -p build/manual-consumer
javac -encoding UTF-8 \
  -cp build/demo-repo/edu/example/greeting-kit/1.0.0/greeting-kit-1.0.0.jar \
  -d build/manual-consumer \
  consumer/src/main/java/demo/consumer/Main.java

java -cp "build/manual-consumer:build/demo-repo/edu/example/greeting-kit/1.0.0/greeting-kit-1.0.0.jar" \
  demo.consumer.Main
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build\manual-consumer | Out-Null
javac -encoding UTF-8 -cp build\demo-repo\edu\example\greeting-kit\1.0.0\greeting-kit-1.0.0.jar -d build\manual-consumer consumer\src\main\java\demo\consumer\Main.java
java -cp "build\manual-consumer;build\demo-repo\edu\example\greeting-kit\1.0.0\greeting-kit-1.0.0.jar" demo.consumer.Main
~~~

**Stdout đúng:**

~~~text
Hello, Linh!
~~~

Lệnh này kiểm tra **artifact binary** thực sự, không kiểm tra Maven POM/dependency metadata hoặc khả năng publish remote. Vì vậy kiểm thử qua Gradle consumer ở mục 6.4–6.5 vẫn cần thiết để xác minh **repository resolution**.

## 7. So sánh kết quả quan sát bằng một bảng

| Câu lệnh tại publisher | Nơi ghi | Có ghi Maven Local? | Có upload qua HTTPS? | Có thể kiểm bằng |
|---|---|---|---|---|
| **./gradlew jar** | build/libs | Không | Không | jar --list |
| **./gradlew publishToMavenLocal** | Maven Local của user | **Có** | Không | Tìm tọa độ dưới Maven Local, thử consumer mavenLocal() |
| **./gradlew publish** với stagingDirectory=file path | build/demo-repo | Không tự động | **Không** | Xem thư mục repo, thử consumer -PrepoMode=staging |
| **./gradlew publishMavenJavaPublicationToStagingDirectoryRepository** | Chỉ stagingDirectory | Không tự động | Không | Tìm đúng repo target |
| **./gradlew publish** với một repo HTTPS đã cấu hình | Server repository từ xa | Không tự động | **Có, nếu upload thành công** | Kiểm tra server, xác thực consumer sạch |
| **./gradlew publish** với nhiều repos | Tất cả repository targets đã cấu hình | Không tự động | Có thể, nếu có HTTPS trong danh sách | Kiểm tra từng target |

Điều kiện “**nếu upload thành công**” rất quan trọng: lỗi authentication, firewall, server policy hoặc conflict có thể khiến publish FAILED. Dòng “publish task có trong task graph” chưa chứng minh artifacts được lưu remote.

### 7.1. Tên task cụ thể khác task aggregate

| Task | Phạm vi |
|---|---|
| **publishToMavenLocal** | Mọi Maven publications của project vào Maven Local |
| **publishMavenJavaPublicationToMavenLocal** | Chỉ mavenJava vào Maven Local |
| **publish** | Mọi publications vào mọi repositories trong publishing.repositories |
| **publishMavenJavaPublicationToStagingDirectoryRepository** | Chỉ mavenJava vào stagingDirectory |
| **publishAllPublicationsToStagingDirectoryRepository** | Mọi publications vào stagingDirectory |

Tên task phát sinh theo **publicationName/repositoryName**, không dựa vào project group hoặc version. Trong multi-project build, có prefix project path như **:library:publish...**.

### 7.2. Kiểm tra trước khi thực thi

~~~bash
./gradlew tasks --all
./gradlew publish --dry-run
./gradlew publishToMavenLocal --dry-run
~~~

**--dry-run chỉ xem task graph, không upload artifacts và không tạo publication mới theo execution task actions.** Nó giúp xác định những targets sắp chạy, nhưng **không xác minh credentials, quyền remote hoặc upload end-to-end**.

Nếu CI cần publish đúng một nơi, nên gọi **named repository task** thay vì tập hợp publish khi dự án có nhiều destinations.

## 8. Cấu hình repository HTTPS từ xa an toàn

Khi tổ chức có Nexus, Artifactory, GitHub Packages hoặc một repository Maven chuẩn, cần:

1. URL chính xác cho **releases** hoặc **snapshots**.
2. Tên repository rõ ràng trong Gradle.
3. Credentials với quyền publish (không hardcode).
4. Network/TLS, proxy, authentication phù hợp.
5. Chính sách release immutable, signing, checksums và metadata.
6. CI runner có quyền upload và logs an toàn.

**Ví dụ cấu hình THAY THẾ cho phần publishing.repositories của publisher:**

~~~groovy
import org.gradle.api.credentials.PasswordCredentials

publishing {
    repositories {
        maven {
            name = 'companyReleases'
            url = uri('https://repo.example.invalid/maven/releases')
            credentials(PasswordCredentials)
        }
    }
}
~~~

**Đây không phải URL thực tế.** Hãy thay bằng endpoint do tổ chức cung cấp trước khi chạy publish. Với **name = 'companyReleases'**, Gradle tìm credentials từ hai Gradle properties:

~~~text
companyReleasesUsername
companyReleasesPassword
~~~

Bạn có thể lưu các properties an toàn trong **~/.gradle/gradle.properties** của user/CI với quyền truy cập phù hợp, hoặc dùng environment variables có prefix **ORG_GRADLE_PROJECT_**:

~~~text
ORG_GRADLE_PROJECT_companyReleasesUsername
ORG_GRADLE_PROJECT_companyReleasesPassword
~~~

**Không commit password/token** trong build.gradle, ~/.m2/settings.xml thuộc repository source, gradle.properties được commit hoặc code examples chứa giá trị thật. Trong CI, cung cấp chúng từ secret manager và mask logs.

### 8.1. Khi nào Gradle cần credentials?

Theo tài liệu Gradle, cơ chế credentials(PasswordCredentials) có thể lấy giá trị dựa trên **tên repository**. Credentials chỉ bắt buộc khi task cần dùng repository được yêu cầu; chỉ chạy local build hoặc publishToMavenLocal **không nên buộc có secrets từ xa** do một repository HTTPS được khai báo mà không được sử dụng.

Nếu Gradle báo thiếu **companyReleasesUsername/Password**, hãy xem:
- Repository name có đúng chữ hoa/chữ thường không?
- Credentials được cung cấp bằng Gradle properties/env đúng prefix không?
- CI job có quyền đọc secrets không?
- Có đang yêu cầu publish tới repo đó dù workflow chỉ định local không?

### 8.2. Ví dụ lệnh publish vào một repository cụ thể

Khi URL đã được thay bằng endpoint thật và credentials được cung cấp:

~~~bash
./gradlew publishMavenJavaPublicationToCompanyReleasesRepository
~~~

Hoặc nếu build chỉ có đúng một publication + repository cần publish:

~~~bash
./gradlew publish
~~~

**Đừng dùng lệnh publish cho nhiều repositories mà không xem task graph trước**; nó có thể upload snapshots và releases cùng lúc nếu hai targets đều cấu hình và không có guard.

### 8.3. HTTPS và các kiểu authentication

**PasswordCredentials** phù hợp với username/password hoặc token dưới dạng password khi repository hỗ trợ Basic auth. Một số services yêu cầu:
- Header/token authentication,
- OAuth/personal access token,
- AWS S3 credentials,
- GitHub Packages permissions,
- SSL truststore hoặc corporate proxy.

Gradle hỗ trợ những credentials types khác như **HttpHeaderCredentials**. Đừng tự áp Basic auth cho dịch vụ chỉ nhận bearer token header. Dùng hướng dẫn chính thức của repository provider và giữ secrets ngoài source.

**Không bật allowInsecureProtocol=true** chỉ để bỏ một lỗi HTTPS trong pipeline production; sửa server certificate/truststore hoặc kết nối đúng endpoint.

### 8.4. Snapshot vs release URL

Các tổ chức thường tách:

~~~text
https://repo.example.invalid/maven/snapshots/
https://repo.example.invalid/maven/releases/
~~~

Một chính sách minh họa:

~~~groovy
publishing {
    repositories {
        maven {
            name = 'company'
            def snapshots = uri('https://repo.example.invalid/maven/snapshots')
            def releases = uri('https://repo.example.invalid/maven/releases')
            url = project.version.toString().endsWith('-SNAPSHOT')
                    ? snapshots : releases

            credentials(PasswordCredentials)
        }
    }
}
~~~

Đoạn này là **phương án thay thế**, không cần chèn đồng thời vào bài lab file-based repo. Khi gọi một repository có tên company, credentials properties tương ứng là **companyUsername/companyPassword**.

**Giới hạn:** Snapshot/release routing không tự tạo các repository đích; server URLs phải tồn tại và tài khoản có quyền. Nhiều repository managers cấm overwrite release version nhưng cho phép snapshot publish nhiều build. Hãy tuân thủ policy server.

### 8.5. Maven Central hiện hành là quy trình riêng

Gradle User Manual ghi nhận **Maven Central không còn hỗ trợ legacy OSSRH/Maven Deploy protocol từ 30/06/2025**. Vì vậy khi cần phát hành lên Maven Central, hãy dùng **plugin/quy trình phù hợp với Central Portal hiện hành**, đủ POM metadata, license, developer/SCM info, sources/Javadoc, signing và xác minh tài khoản.

**Không khẳng định** cứ cấu hình maven-publish đến một OSSRH endpoint cũ là có thể phát hành public artifact. Bài lab chỉ dùng Maven Local và file repo, không đưa ra thao tác upload Maven Central thật.

## 9. Versioning, immutable releases và rủi ro ghi đè

### 9.1. Maven Local có thể bị ghi đè cùng version

Bạn publish:

~~~text
edu.example:greeting-kit:1.0.0
~~~

rồi sửa code nhưng vẫn giữ **version = '1.0.0'** và chạy lại publishToMavenLocal. File local có thể đổi bytes dưới **cùng coordinates**, làm consumer khác nhau trên hai máy nhận **hai implementation**.

Đây là nguyên nhân phổ biến của:
- "Works on my machine".
- Local test pass nhưng CI remote fail.
- Source/Javadoc đính kèm không khớp binary release.
- Dependency cache bị lệch với artifact mới ghi đè.
- Debug khó tái hiện vì Git version và Maven coordinates không nói đúng bytes.

**Chính sách tốt:** Đổi version khi phát hành release mới, dùng -SNAPSHOT cho phát triển theo chính sách tổ chức, không tái phát hành release binary khác nội dung dưới cùng tọa độ.

### 9.2. Repository server có thể chặn redeploy releases

Một repository manager có thể:
- Cho upload lần đầu.
- Từ chối 409 Conflict khi group/artifact/version đã tồn tại.
- Chặn overwrite release versions.
- Yêu cầu artifact signing/metadata/provenance.
- Giới hạn quyền từng nhóm hoặc từng repo.

Do đó **publishToMavenLocal thành công không dự đoán được publish HTTPS có thành công không**. Hai đích có cơ chế kiểm soát khác nhau.

### 9.3. Một artifact version cần gắn với một source commit

Một release ổn định nên lưu:
- Git commit/tag,
- Gradle Wrapper/JDK versions,
- build/test results và CI run ID,
- SHA256/digest của artifacts,
- Publication coordinates,
- Repository URL và publish timestamp,
- Signing/provenance details theo chính sách.

Những thông tin này giúp trả lời “JAR này đến từ commit nào?”. Maven Local mặc định không cung cấp hệ thống phê duyệt/provenance tương đương repository manager.

### 9.4. Snapshot không thay thế integration versioning

-SNAPSHOT chỉ là **version convention**, không tự làm mọi library binary tương thích. Maven snapshot repositories có thể có metadata/timestamp handling riêng. Consumer có thể cache metadata theo rules và không lập tức thấy snapshot vừa publish.

Khi cần kiểm tra một build cụ thể, kiểm tra snapshot version, repository state và Gradle refresh policy; không giải quyết bằng cách xóa toàn bộ ~/.gradle hoặc đổi version một cách tùy tiện.

## 10. Publishing metadata và tính tương thích của consumer

### 10.1. POM là gì?

Gradle tạo **Maven POM** mô tả:
- groupId, artifactId, version.
- Tên/mô tả và metadata khác nếu khai báo.
- Dependencies được publish từ Java component.
- Các thông tin license, developers, SCM nếu khai báo.
- Packaging và những cấu trúc Maven cần thiết.

Gradle Module Metadata có thể bổ sung thông tin **variants, attributes, capabilities và rich dependency constraints** mà POM không biểu diễn đầy đủ.

**Không nên chỉ upload một .jar thủ công lên HTTP server** mà bỏ POM/Module Metadata rồi tuyên bố đây là publication Maven hoàn chỉnh. Consumer resolution có thể cần metadata để biết dependencies đúng.

### 10.2. from components.java là cấu hình chuẩn

Trong java-library:

~~~groovy
publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }
}
~~~

Java component mang các artifacts và dependency variants theo plugin. Khi bạn bật **withSourcesJar()/withJavadocJar()**, documentation variants được thêm vào component và Maven publication sẽ có các classifiers sources/javadoc tương ứng.

Nếu thay bằng cách thủ công:

~~~groovy
artifact tasks.named('jar')
~~~

bạn cần tự chịu trách nhiệm nhiều phần metadata/variants. Với Java library thông thường, **from components.java** giúp tránh sai sót.

### 10.3. Direct dependencies và resolved versions

Theo Gradle Maven Publish Plugin, mặc định **published dependency versions** đến từ những **declared versions** trong build script, không nhất thiết là versions thực tế được resolve sau conflict rules/constraints. Khi cần publish resolved versions có kiểm soát, có thể dùng **versionMapping**.

Ví dụ minh họa:

~~~groovy
publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
            versionMapping {
                usage('java-api') {
                    fromResolutionOf('runtimeClasspath')
                }
                usage('java-runtime') {
                    fromResolutionResult()
                }
            }
        }
    }
}
~~~

Đoạn này chỉ có ý nghĩa với module có dependencies ngoài và chính sách publication rõ ràng; **không cần** trong lab chỉ dùng JDK types. Đây là phần quan trọng khi có dependency locking hoặc dynamic versions: publishToMavenLocal và remote publish dùng **cùng publication metadata đã định nghĩa**, nên cả hai có thể giống lỗi POM nếu build cấu hình sai.

### 10.4. Test consumer là phép kiểm tra end-to-end

Một file tồn tại tại Maven Local hoặc HTTP repository **chưa đủ** nếu:
- POM ghi sai group/artifact/version.
- Binary JAR thiếu classes hoặc chứa Java version không tương thích.
- API dependencies không được đưa vào POM đúng scope.
- Sources/Javadoc classifiers bị đính kèm sai version.
- Repository credentials/content filters không cho consumer tải.
- Consumer nhận module variant khác kỳ vọng.

Bài lab dùng **consumer độc lập** để kiểm chứng đúng interface. Trong CI thật, cần chạy consumer trên **clean environment** và repository đích thực tế, tránh Maven Local cũ che artifacts.

## 11. Mô hình CI an toàn: thử local rồi publish remote

Một pipeline release gợi ý:

~~~text
Git commit/tag
    |
    v
Check Gradle Wrapper, JDK, version
    |
    v
compile + test + code quality + checks
    |
    v
generate publication artifacts/POM/metadata
    |
    v
publish vào file repo / staging (dry-run safety)
    |
    v
validate artifacts & clean consumer
    |
    v
approve release + credentials
    |
    v
publish đúng HTTPS release repository
    |
    v
verify server storage + resolve consumer từ server
    |
    v
record release artifacts, checksums, provenance
~~~

**Không bắt buộc publishToMavenLocal là bước của CI release**. Nó đặc biệt phù hợp với việc developer kiểm tra tích hợp **trên cùng máy**. CI nên dùng clean, isolated workspace, staging repository hoặc remote artifact manager có traceable logs.

### 11.1. Preflight trước remote upload

1. **Coordinates** đúng group/artifact/version?
2. **Version** được phép publish, không trùng immutable release?
3. **Repository URL** đúng snapshot/release target?
4. **Task graph** chỉ chứa intended publication/repository?
5. **Credentials** có quyền tối thiểu cần thiết, không in plaintext?
6. **Artifacts/POM/.module** tồn tại và có nội dung đúng?
7. **JDK/Gradle** versions khớp policy?
8. **Unit/integration tests** đã chạy theo yêu cầu, không chỉ build cache hit khi cần fresh verification?
9. **License/NOTICE/signatures** đã đúng theo kho nhận?
10. **Dependency versions** và lock state được review?
11. **Signing keys** có được bảo vệ không?
12. **Publication identity** gắn đúng commit/tag/CI job?
13. **Consumer thử nghiệm** resolve được artifact từ staging?
14. Có quy trình rollback/quarantine nếu server nhận artifact lỗi?
15. Không publish cùng version với bytes khác nếu release bất biến?

### 11.2. CI không nên upload bằng lệnh publish mơ hồ

Một ví dụ job release đã kiểm tra đủ điều kiện:

~~~bash
./gradlew clean check
./gradlew publishMavenJavaPublicationToCompanyReleasesRepository
~~~

Câu lệnh thứ hai chỉ đúng khi build có **companyReleases** repository với **URL thật**, credentials hợp lệ và MavenPublication mavenJava. Không chép lệnh vào máy thật nếu chưa có pipeline permissions/approval.

**Lợi ích của named task:** Một build có repositories staging, snapshots, releases, internal; lệnh **publish** có thể nhắm tất cả, còn named task chỉ nhắm một.

### 11.3. Không dùng publishToMavenLocal để “điền dependency” cho CI

Nếu CI cần artifact do một module khác tạo, có các lựa chọn rõ hơn:
- **Composite build/project dependency** khi module nằm cùng source workspace.
- **Published snapshot/staging repository** có quyền và version.
- **CI artifact handoff** giữa stages nếu pipeline cho phép, kèm metadata hợp lệ.
- **Isolated file-based Maven repository** được tạo trong job (khác với Maven Local dùng chung).

Tự populate ~/.m2/repository rồi dựa vào nó trong production build có thể làm mất tính hermetic/reproducibility và khiến những runner khác không tái hiện được.

### 11.4. Multi-project publishing

Giả sử:

~~~text
root/
├── core/
├── api/
└── app/
~~~

Mỗi project có thể tạo **MavenPublication** riêng. Một task theo đường dẫn project:

~~~bash
./gradlew :core:publishToMavenLocal
./gradlew :api:publishMavenJavaPublicationToCompanyReleasesRepository
~~~

không tương đương với publish mọi modules. Xác định **nơi khai báo maven-publish** và **task path** trên từng subproject.

Khi modules có dependency project(':core'), Gradle Maven Publish Plugin có thể thể hiện Maven coordinates của dependency trong metadata, nhưng consumer chỉ resolve được nếu cả upstream modules cần thiết cũng đã publish/được cung cấp. **Không upload chỉ app JAR rồi mặc định remote đã có tất cả project dependencies**.

### 11.5. Publish remote xong phải xác minh độc lập

Một upload task SUCCESS là tín hiệu tốt nhưng chưa phải xác minh đầy đủ. Có thể kiểm tra:
- Giao diện/API repository manager thấy đúng group/artifact/version.
- File JAR/POM/.module/classifiers và checksums xuất hiện.
- Server không thay đổi metadata đáng ngờ.
- Một clean consumer **không dùng mavenLocal()** có thể resolve đúng version.
- Consumer compile/run đúng Java/JDK version đã công bố.
- Repository access policy cho nhóm nhận đã được cấu hình.

**Đừng chỉ kiểm tra POM bằng cách tải JAR một URL đoán ra** rồi kết luận Gradle metadata cũng đúng. Consumer test là phép đo có ý nghĩa hơn.

## 12. Lỗi thường gặp và cách xử lý

### Lỗi 1 — Đã chạy publishToMavenLocal nhưng đồng nghiệp không thấy artifact

**Nguyên nhân:** Maven Local thuộc máy/user đang chạy; không chia sẻ tự động.

**Cách sửa:** Publish vào repository tập trung được cấu hình trong publishing.repositories, cung cấp URL và quyền đọc cho consumer. Không chép ngẫu nhiên thư mục .m2 của developer lên server.

### Lỗi 2 — Chạy publish nhưng không thấy file ở ~/.m2

**Nguyên nhân:** **publish không tự thực thi publishToMavenLocal**.

**Cách sửa:** Nếu thực sự muốn install local, gọi publishToMavenLocal. Nếu mục tiêu remote, hãy kiểm tra publishing.repositories.

### Lỗi 3 — publish thành công nhưng artifact chưa ở remote

**Nguyên nhân:** Repo target là **file path** hoặc không có publishing.repositories thực sự.

**Cách sửa:** Xem repository URL và task graph; repo dạng file:// là local staging. Khi dùng HTTPS thật, kiểm tra logs và server artifact listing.

### Lỗi 4 — Không thấy task publishToMavenLocal

**Nguyên nhân:** Chưa áp **maven-publish**, hoặc chưa tạo MavenPublication phù hợp.

**Cách sửa:** Kiểm tra plugins { id 'maven-publish' }, publishing.publications, và ./gradlew tasks --all. Không giải quyết bằng việc thêm mavenLocal() vào repositories đọc dependency.

### Lỗi 5 — Đã có MavenPublication nhưng publish không upload gì

**Nguyên nhân:** Chưa có destination trong publishing.repositories, hoặc task không được gọi cho đúng project.

**Cách sửa:** Khai báo MavenArtifactRepository có URL, kiểm tra publishMavenJavaPublicationTo...Repository và dùng đúng task path.

### Lỗi 6 — Consumer không tìm thấy module trong Maven Local

**Nguyên nhân:** Khác user/Maven Local path, tọa độ sai, version khác hoặc consumer không khai báo mavenLocal().

**Cách sửa:** Kiểm tra location precedence, filesystem path, POM/JAR, và consumer repositories. Đừng assume path ~/.m2 nếu system property/settings đã override.

### Lỗi 7 — Consumer local chạy được, CI không chạy được

**Nguyên nhân:** Developer có artifact tự publish vào Maven Local; CI clean runner không có nó.

**Cách sửa:** Publish vào shared/staging repository và để CI resolve từ đó; không dựa vào trạng thái ẩn của máy developer.

### Lỗi 8 — HTTP 401 Unauthorized

**Nguyên nhân:** Thiếu/sai credentials, token hết hạn hoặc scheme auth sai.

**Cách sửa:** Kiểm tra repository name và Gradle properties tương ứng, secret manager, token scope và authentication type. Không in password trong build logs để debug.

### Lỗi 9 — HTTP 403 Forbidden

**Nguyên nhân:** Credentials được nhận nhưng user/token không có quyền publish vào path/repository, hoặc repo policy cấm thao tác.

**Cách sửa:** Kiểm tra ACL/role, repository target và endpoint path; yêu cầu quyền phù hợp, không tự đổi sang public/anonymous upload.

### Lỗi 10 — HTTP 404 Not Found

**Nguyên nhân:** URL sai, endpoint publishing khác URL browser/download, repository không tồn tại hoặc path bị proxy rewrites.

**Cách sửa:** Kiểm tra documented deployment endpoint của Nexus/Artifactory/hosting service, dùng đúng releases/snapshots URL.

### Lỗi 11 — HTTP 409 Conflict hoặc server cấm redeploy

**Nguyên nhân:** Release version đã tồn tại và repository bất biến, hoặc policy snapshots/releases không phù hợp.

**Cách sửa:** Không ghi đè release; chọn version mới, điều chỉnh repo policy theo quy trình được phép, xác minh tọa độ trước khi upload.

### Lỗi 12 — credentials bị yêu cầu cả khi chỉ chạy build local

**Nguyên nhân:** Build script có logic tự get secrets sớm hoặc task publishing tới repo được thêm vào graph ngoài ý muốn.

**Cách sửa:** Dùng credentials(PasswordCredentials) lazy lookup theo repo name, không tự gọi providers...get() bắt buộc trong configuration nếu không cần. Kiểm tra task graph và build logic/plugin callbacks.

### Lỗi 13 — Source/Javadoc không có trong publication

**Nguyên nhân:** Chưa gọi withSourcesJar()/withJavadocJar() hoặc publication không dùng from components.java.

**Cách sửa:** Cấu hình java extension và Java component đúng, kiểm tra tasks sourcesJar/javadocJar, metadata và files sau publish. Không đính kèm trùng khi chúng đã là variants của component.

### Lỗi 14 — POM thiếu dependency hoặc version khác kỳ vọng

**Nguyên nhân:** Publication bị dựng thủ công, versionMapping chưa đúng, dependency scope api/implementation sai hoặc metadata từ Java component không được dùng.

**Cách sửa:** Dùng from components.java, review generated POM, xem các dependency declarations/constraints và versionMapping khi cần.

### Lỗi 15 — Cùng version nhưng consumer nhận JAR cũ

**Nguyên nhân:** Maven Local đã ghi đè, build caches/repository metadata caches, server có bản cũ, repository order hoặc version release bị tái sử dụng.

**Cách sửa:** So sánh SHA256/byte content, xác định nguồn artifact, đổi version đúng khi release mới; không xóa caches mù quáng hoặc cố tiếp tục deploy release cùng version.

### Lỗi 16 — mavenLocal() đứng trước Maven Central gây kết quả khác máy

**Nguyên nhân:** Local module trùng tọa độ được ưu tiên resolve theo repository order.

**Cách sửa:** Hạn chế Maven Local trong consumer demo, không đưa mặc định vào production/CI, sử dụng content filters hoặc remote repository thống nhất.

### Lỗi 17 — Một lần publish upload vào nhiều repos ngoài ý muốn

**Nguyên nhân:** Aggregate task publish nhắm tất cả configured publishing repositories.

**Cách sửa:** Dùng named task publish<Publication>PublicationTo<Repository>Repository hoặc tổ chức tasks/policies rõ ràng. Kiểm tra publish --dry-run trước khi release.

### Lỗi 18 — Một file-based Maven repository bị tưởng là remote

**Nguyên nhân:** Nhìn chữ publish hoặc MavenArtifactRepository mà không xem URL.

**Cách sửa:** Phân biệt **file:// hoặc local filesystem path** với **https://**. Lab publish vào build/demo-repo hoàn toàn local.

### Lỗi 19 — Gradle Maven Local không có checksum files

**Nguyên nhân:** Gradle publishToMavenLocal không tạo checksum files theo tài liệu.

**Cách sửa:** Nếu cần kiểm tra checksum sidecars, publish thử vào file-based Maven repository hoặc remote staging phù hợp; không coi khác biệt này là lỗi publication.

### Lỗi 20 — Maven Central từ chối generic deploy

**Nguyên nhân:** Central Portal hiện đại không dùng legacy OSSRH deployment protocol như các ví dụ cũ.

**Cách sửa:** Chọn quy trình/plugin Central hiện hành, ký artifacts, hoàn tất POM/metadata/license và kiểm tra release requirements.

### Lỗi 21 — Artifact đã lên server nhưng consumer không resolve được

**Nguyên nhân:** Repository read credentials khác publish credentials, POM/module metadata hỏng, content filters/mirror/proxy sai, dependencies chưa được publish hoặc Java bytecode không tương thích.

**Cách sửa:** Kiểm tra consumer từ một clean workspace, đúng repository URL và quyền đọc; chạy dependencies/dependencyInsight khi phù hợp và xem server access logs.

## 13. Mẫu quyết định thực tế

| Tình huống | Nên chọn |
|---|---|
| Developer thử library với một app khác **trên cùng laptop** | **publishToMavenLocal**, consumer demo dùng mavenLocal() có kiểm soát |
| Muốn kiểm tra files/checksums/POM trước upload mà không cần server | **publish** vào một **file-based Maven repo** trong build/ hoặc workspace staging |
| Team cần dùng chung internal library | **publish** vào internal HTTPS Maven repository và cung cấp consumer read access |
| CI release chính thức | Validate, sign theo policy, publish tới đúng named remote release task |
| Multi-repository build chỉ muốn upload một đích | Dùng **specific publish...To...Repository task**, tránh aggregate publish |
| Muốn kiểm tra một dependency nội bộ mà không xuất bản lên server | Composite/project dependency hoặc isolated staging repository có provenance |
| Release lên Maven Central | Dùng quy trình/plugin Central Portal hiện hành, không phụ thuộc OSSRH cũ |
| Muốn build CI tái lập được | Tránh mavenLocal(); dùng remote repository được quản lý, pin version và xác minh artifacts |
| Cần kiểm tra published module source/API | MavenPublication từ components.java và consumer clean workspace |
| Đang debug 401/403/409 | Kiểm tra credentials/ACL/version/repo policy, không đổi sang anonymous/insecure |

## 14. Checklist kiến thức trước khi bấm Publish

**Về build và publication:**

1. Đã tạo đúng MavenPublication, ví dụ mavenJava?
2. Có group, artifactId, version chính xác không?
3. Java component và dependency metadata đúng với consumer chưa?
4. Binary/sources/Javadoc files có cùng commit/version không?
5. Generated POM/.module có được inspect không?
6. Test/build checks cần thiết đã PASS chưa?

**Về đích và Gradle task:**

7. Đích là **Maven Local**, **file repo** hay **remote HTTPS**?
8. Đã đọc đúng publishing.repositories thay vì project repositories?
9. Lệnh publish có thể nhắm **nhiều repos** không?
10. Có dùng task cụ thể nếu chỉ muốn một repo không?
11. Đã dùng --dry-run để xem task graph khi có rủi ro upload nhầm chưa?
12. Maven Local path có bị override bởi settings/system property không?

**Về bảo mật và release:**

13. Credentials có ở Gradle properties/secret manager chứ không hardcode?
14. HTTPS/certificate/proxy phù hợp môi trường?
15. Repository server có cho overwrite release không?
16. Snapshot/release route có chọn đúng theo version?
17. Signing/checksum/notice/license policy có được đáp ứng?
18. Có quyền publish đúng module path, không dùng token quá rộng?

**Về xác minh kết quả:**

19. Artifact/POM/.module có thật tại destination không?
20. Consumer đọc **đúng đích** và đúng coordinates?
21. Consumer sạch không phụ thuộc Maven Local trên laptop?
22. Có ghi lại artifact hashes và source commit cho release?
23. Nếu publish failed, có xác minh upload partial trước khi retry không?
24. Có cách rollback/quarantine artifact lỗi thay vì ghi đè bí mật cùng version?

## 15. Bài tập thực hành

**Bài 1.** Trong một project có publication mavenJava và publishing.repositories trống, chạy publishToMavenLocal có cần thêm mavenLocal() vào publishing.repositories mới hoạt động không?

**Bài 2.** Cùng project đó, chạy ./gradlew publish sẽ tự upload tới Maven Central không? Vì sao?

**Bài 3.** Một project có publishing.repositories.maven URL trỏ đến build/demo-repo. Chạy publish có được gọi là remote upload không?

**Bài 4.** Một consumer muốn tải module edu.example:greeting-kit:1.0.0 mà publisher vừa cài bằng publishToMavenLocal. Consumer phải cấu hình repository nào?

**Bài 5.** Vì sao consumer trên laptop A tải được một module qua mavenLocal(), nhưng laptop B không thấy?

**Bài 6.** Tên publication mavenJava và repository stagingDirectory tạo task cụ thể nào?

**Bài 7.** publish và publishToMavenLocal khác nhau thế nào về task dependencies?

**Bài 8.** Vì sao thêm repositories { mavenCentral() } trong publisher không cấp quyền upload lên Maven Central?

**Bài 9.** Nếu một Maven Local có module 1.0.0 với bytes khác remote 1.0.0, vì sao consumer với mavenLocal() đứng đầu có thể dùng sai bản?

**Bài 10.** Trong bài lab, lệnh nào ghi library vào ~/.m2/repository và lệnh nào ghi vào build/demo-repo?

**Bài 11.** Người dùng chạy jar nhưng tìm POM trong Maven Local không có. Có phải Gradle lỗi không?

**Bài 12.** Tại sao một remote HTTPS repository cần credentials nhưng publishToMavenLocal trên cùng build có thể không cần remote credentials?

**Bài 13.** Với repo name companyReleases và credentials(PasswordCredentials), những tên Gradle properties nào cần cung cấp?

**Bài 14.** Với repo name companyReleases, lệnh cụ thể để chỉ upload mavenJava vào đó là gì?

**Bài 15.** Tại sao publishToMavenLocal không đủ để xác minh checksum sidecars của một publication remote?

**Bài 16.** Nếu publish thành công vào file repo nhưng consumer không resolve, bạn sẽ kiểm tra những file/đường dẫn nào?

**Bài 17.** Khi project có hai repositories là staging và releases, chạy task publish có thể upload vào bao nhiêu đích?

**Bài 18.** Vì sao nên tăng version thay vì ghi đè 1.0.0 ở release repository?

**Bài 19.** Sau khi publish một library Java, vì sao cần kiểm tra consumer từ workspace sạch chứ không chỉ dựa vào build/libs/*.jar?

**Bài 20.** Một repository manager trả HTTP 409 khi publish release. Điều này thường biểu thị gì và nên xử lý ra sao?

**Bài 21.** Tại sao một GitHub Actions/CI runner không nên phụ thuộc vào ~/.m2/repository của developer?

**Bài 22.** Maven Central hiện hành có nên publish bằng legacy OSSRH deploy protocol như tài liệu trước năm 2025 không?

### Đáp án gợi ý

1. **Không.** Maven Publish Plugin tự tạo PublishToMavenLocal tasks cho Maven publications.
2. **Không.** publish nhắm publishing.repositories; không có đích thì không tự gửi Maven Central.
3. **Không.** Đó là repository local filesystem được cấu hình làm đích publish.
4. Consumer thêm **repositories { mavenLocal() }** trong bối cảnh demo, với cùng Maven Local.
5. Maven Local thuộc **máy/user**, không phải shared server.
6. **publishMavenJavaPublicationToStagingDirectoryRepository**.
7. publish gom tasks publication→configured repositories; publishToMavenLocal gom tasks publication→Maven Local.
8. mavenCentral() là **dependency resolution repository**, không phải publish endpoint/authentication.
9. Local repo có thể override resolution theo thứ tự repositories, gây khác biệt giữa máy.
10. **publishToMavenLocal** ghi Maven Local; **publish** với stagingDirectory ghi build/demo-repo.
11. **Không.** jar chỉ tạo JAR trong workspace, không tự publish POM.
12. Maven Local là local filesystem; credentials của named remote repo chỉ cần khi task dùng remote target được yêu cầu.
13. **companyReleasesUsername** và **companyReleasesPassword**, có thể thông qua ORG_GRADLE_PROJECT_... environment variables.
14. **publishMavenJavaPublicationToCompanyReleasesRepository**.
15. Theo Gradle docs, Maven Local publication không tạo checksum files tương tự repository publishing.
16. Kiểm tra group/artifact/version path, JAR/POM/.module/classifiers, consumer repository URL và project properties, dependency metadata.
17. **Hai** đích nếu cả hai được cấu hình và có publication thích hợp.
18. Bảo toàn tính immutable và reproducibility, tránh khác bytes dưới cùng coordinates.
19. Consumer sạch xác nhận coordinates, metadata, read permissions và classpath độc lập với local outputs.
20. Thường là conflict/đã có version hoặc policy cấm redeploy; chọn version mới, kiểm tra repository policy.
21. Maven Local của developer không chuyển tự động sang CI và có thể chứa artifact đã bị ghi đè.
22. **Không.** Dùng workflow/plugin hiện hành theo Central Portal.

## Tài liệu tham khảo chính thức

- [Gradle User Manual — The Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html): MavenPublication, publish, publishToMavenLocal, tasks, publication/repository mapping, checksum khác biệt, current Maven Central note.
- [Gradle User Manual — Publishing Overview](https://docs.gradle.org/current/userguide/publishing_overview.html): publishing components, artifacts và Maven/Ivy repositories.
- [Gradle User Manual — Declaring Repositories Basics](https://docs.gradle.org/current/userguide/declaring_repositories_basics.html): đọc dependencies, local/remote repositories và thứ tự resolve.
- [Gradle User Manual — Supported Repository Types](https://docs.gradle.org/current/userguide/supported_repository_types.html): Maven Local location/nhược điểm khi dùng cho production.
- [Gradle User Manual — Supported Repository Protocols](https://docs.gradle.org/current/userguide/supported_repository_protocols.html): HTTPS, authentication và credentials(PasswordCredentials).
- [Gradle User Manual — Securing Repositories](https://docs.gradle.org/current/userguide/securing_repositories.html): credentials, trust và repository policies.
- [Gradle API — RepositoryHandler.mavenLocal](https://docs.gradle.org/current/javadoc/org/gradle/api/artifacts/dsl/RepositoryHandler.html): thứ tự xác định Maven Local path.
- [Gradle API — MavenPublication](https://docs.gradle.org/current/javadoc/org/gradle/api/publish/maven/MavenPublication.html): identity, artifacts, pom, versionMapping.
- [Gradle API — PublishToMavenLocal](https://docs.gradle.org/current/javadoc/org/gradle/api/publish/maven/tasks/PublishToMavenLocal.html): nhiệm vụ xuất bản Maven Local.
- [Gradle API — PublishToMavenRepository](https://docs.gradle.org/current/javadoc/org/gradle/api/publish/maven/tasks/PublishToMavenRepository.html): nhiệm vụ xuất bản Maven repository đích.
- [Gradle User Manual — The Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): java-library component và dependencies metadata.
- [Gradle User Manual — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): cố định phiên bản Gradle cho build/release.

**Ghi nhớ:** **publishToMavenLocal** cài mọi Maven publications của project vào Maven Local của máy, hữu ích cho thử nghiệm consumer tại chỗ nhưng không chia sẻ tự động. **publish** gửi publications đến các destinations trong **publishing.repositories**, có thể là **file-based repository** hoặc **HTTPS server**; nó **không tự publishToMavenLocal**. Dùng named publish task khi chỉ muốn một nơi nhận, dùng credentials và version policy đúng khi upload remote, kiểm tra POM/JAR/metadata tại đích và xác minh bằng consumer sạch. Không để mavenLocal() trở thành nguồn phụ thuộc ẩn trong production/CI.
# Phân biệt phát hành thư viện với triển khai ứng dụng

Một dự án Java có thể tạo ra JAR, ZIP distribution hoặc container image, nhưng việc tạo artifact chưa nói lên nó được dùng như thế nào sau build. Một thư viện được phát hành để project khác khai báo và sử dụng; một ứng dụng được triển khai để một môi trường thực thi và phục vụ người dùng hoặc hệ thống khác. Hai hoạt động có thể dùng chung build tool và repository, nhưng có mục tiêu, metadata, versioning, cách phân phối và trách nhiệm vận hành khác nhau.

**Phát hành thư viện (library release)** tạo ra một thành phần có thể được consumer tích hợp vào dependency graph. Consumer cần biết tọa độ artifact, phiên bản, API công khai, dependency bắc cầu, variant và các điều kiện tương thích.

**Triển khai ứng dụng (application deployment)** đưa một chương trình có thể chạy vào một môi trường cụ thể. Đơn vị triển khai có thể là executable JAR, application distribution, container image hoặc package phù hợp với nền tảng. Môi trường đó cần runtime, cấu hình, secrets, quyền truy cập, tài nguyên và quy trình cập nhật/rollback.

Phân biệt hai hoạt động giúp nhóm chọn đúng task Gradle/Maven, repository, quy tắc version và pipeline phát hành. Một library JAR có thể được publish lên Maven repository nhưng không cần được chạy trực tiếp. Một application JAR cũng có thể được lưu trong artifact repository, nhưng việc lưu artifact không đồng nghĩa ứng dụng đã được triển khai và đang phục vụ.

## 1. Hai mục tiêu khác nhau

| Khía cạnh | Phát hành thư viện | Triển khai ứng dụng |
|---|---|---|
| Người/đối tượng tiếp nhận | Developer, build của project consumer hoặc hệ thống phụ thuộc | Runtime environment, máy chủ, container platform hoặc người vận hành |
| Mục tiêu | Cung cấp API/implementation có thể tái sử dụng | Khởi chạy một chương trình để thực hiện chức năng |
| Artifact thường gặp | Library JAR, POM, Gradle Module Metadata, sources/Javadoc JAR, chữ ký và checksum | Executable JAR, distribution ZIP/TAR, container image, package cài đặt |
| Metadata quan trọng | Coordinates, version, dependency graph, variants, API/ABI, license | Entry point, runtime requirement, config, port, health check, resource và deployment manifest |
| Versioning | Thể hiện mức thay đổi contract và compatibility | Thể hiện bản phát hành của ứng dụng hoặc image được triển khai |
| Nơi phân phối | Maven-compatible repository, artifact registry | Registry, server, container registry, package store hoặc nền tảng triển khai |
| Kiểm chứng chính | Consumer có resolve và sử dụng đúng API/dependency không? | Ứng dụng có khởi động, hoạt động và đáp ứng yêu cầu vận hành không? |
| Cập nhật | Consumer nâng dependency version và build lại | Thay phiên bản ứng dụng trong môi trường đích |
| Rollback | Consumer quay về version thư viện trước trong dependency graph | Triển khai lại image/package/version ứng dụng trước |

Luồng khái quát:

~~~text
                 Source code
                      |
                      v
                    Build
                      |
             +--------+--------+
             |                 |
             v                 v
       Library artifact   Application artifact
             |                 |
             v                 v
      Publish to repo     Package for runtime
             |                 |
             v                 v
      Consumer resolves   Deploy to environment
      dependency          and starts application
             |                 |
             v                 v
      Consumer compiles   Monitor / update / rollback
      and runs
~~~

Build là bước tạo output. Publish là bước đưa artifact cùng metadata vào nơi consumer có thể lấy. Deploy là bước đưa ứng dụng vào môi trường chạy và kích hoạt nó theo quy trình vận hành. Các bước có thể nằm trong cùng một CI pipeline, nhưng không nên xem chúng là một hành động duy nhất.

## 2. Phát hành thư viện có nghĩa là công bố một contract

### 2.1. Library cung cấp thành phần cho consumer

Một thư viện thường cung cấp một hoặc nhiều package public, ví dụ:

~~~java
package com.example.money;

import java.math.BigDecimal;

public final class Money {
    private final BigDecimal amount;
    private final String currency;

    public Money(BigDecimal amount, String currency) {
        this.amount = amount;
        this.currency = currency;
    }

    public BigDecimal amount() {
        return amount;
    }

    public String currency() {
        return currency;
    }
}
~~~

Consumer khai báo dependency đến artifact chứa lớp Money, sau đó import và sử dụng API. Consumer không cần chạy thư viện như một process độc lập.

Một library release vì vậy phải quan tâm đến:

- Tên và tọa độ artifact ổn định.
- Version có ý nghĩa đối với compatibility.
- API public và các thay đổi có thể ảnh hưởng consumer.
- Dependency bắc cầu được công bố đúng.
- Variant phù hợp với compile/runtime hoặc platform.
- Metadata đủ để build tool phân giải artifact.
- License, nguồn gốc, chữ ký và checksum theo chính sách phát hành.
- Tài liệu và ví dụ để consumer tích hợp.

### 2.2. Maven coordinates nhận diện artifact

Artifact Maven thường được nhận diện bằng groupId, artifactId, version, packaging/type và classifier nếu có. Ví dụ:

~~~text
com.example.platform:money-core:2.4.1
~~~

Consumer Maven khai báo:

~~~xml
<dependency>
    <groupId>com.example.platform</groupId>
    <artifactId>money-core</artifactId>
    <version>2.4.1</version>
</dependency>
~~~

Gradle consumer khai báo:

~~~kotlin
dependencies {
    implementation("com.example.platform:money-core:2.4.1")
}
~~~

Coordinates phải ổn định và không nên thay nội dung của một release version đã phát hành. Nếu artifact 2.4.1 đã được consumer tải về, thay file ở repository bằng nội dung khác có thể khiến hai build cùng khai báo 2.4.1 nhưng nhận bytecode khác nhau. Điều này phá tính tái lập và làm điều tra lỗi rất khó.

### 2.3. Metadata quan trọng không chỉ là file JAR

Một library release thường cần metadata bên cạnh JAR:

- Maven POM mô tả coordinates, dependency, scope, packaging và thông tin project.
- Gradle Module Metadata có thể mô tả variants, capabilities và dependency information chi tiết hơn cho consumer Gradle.
- Sources JAR giúp consumer đọc source khi debug hoặc IDE hiển thị implementation.
- Javadoc JAR cung cấp tài liệu API.
- Checksums và signatures hỗ trợ kiểm tra tính toàn vẹn và nguồn phát hành.
- License/notice và release notes giúp consumer đánh giá quyền sử dụng và thay đổi.

Nếu chỉ copy file JAR vào một thư mục mà không công bố metadata, consumer có thể phải tự quản lý dependency bắc cầu và version. Việc publish đúng repository format giúp build tool giải quyết graph tự động.

## 3. Versioning của thư viện và compatibility

### 3.1. Version là một phần của contract

Thư viện thường dùng semantic versioning hoặc một chính sách version tương đương. Với dạng MAJOR.MINOR.PATCH:

- MAJOR: thay đổi không tương thích với consumer theo contract đã công bố.
- MINOR: bổ sung tính năng tương thích ngược.
- PATCH: sửa lỗi tương thích ngược, không chủ ý thay đổi API contract.

Ví dụ, từ 2.4.1 lên 2.4.2 thường là bản sửa lỗi; từ 2.4.1 lên 2.5.0 thường là bổ sung tính năng tương thích; từ 2.4.1 lên 3.0.0 có thể bao gồm breaking changes.

Semantic versioning chỉ hữu ích khi nhóm định nghĩa rõ public API và tuân thủ chính sách. Không nên tăng PATCH cho một thay đổi làm consumer không compile được. Cũng không nên tăng MINOR cho việc xóa method public mà không có quy ước compatibility khác được công bố.

### 3.2. API compatibility và binary compatibility

Một thay đổi có thể ảnh hưởng consumer theo nhiều cách:

- Source compatibility: mã nguồn consumer còn biên dịch được không?
- Binary compatibility: bytecode consumer đã biên dịch có tiếp tục liên kết và chạy được không?
- Behavioral compatibility: hành vi có còn phù hợp với contract không?
- Serialization/data compatibility: dữ liệu được ghi bởi version trước có đọc được bởi version mới không?
- Runtime compatibility: thư viện còn hỗ trợ Java runtime và dependency versions đã công bố không?

Ví dụ, đổi tên method public có thể làm source consumer không biên dịch. Xóa method hoặc thay đổi signature có thể khiến bytecode cũ gặp NoSuchMethodError. Thay đổi cách xử lý null hoặc rounding có thể giữ compile/binary compatibility nhưng phá behavioral compatibility.

### 3.3. Deprecation trước khi loại bỏ API

Với thư viện có nhiều consumer, nên có lộ trình:

1. Giới thiệu API mới.
2. Đánh dấu API cũ deprecated và giải thích cách chuyển đổi.
3. Cung cấp release notes và migration guide.
4. Cho consumer đủ thời gian chuyển đổi theo chính sách hỗ trợ.
5. Chỉ loại bỏ API cũ trong release có mức version phản ánh breaking change.

Ví dụ:

~~~java
public class MoneyFormatter {
    @Deprecated
    public String formatLegacy(Money money) {
        return format(money);
    }

    public String format(Money money) {
        return money.amount() + " " + money.currency();
    }
}
~~~

Trong code thực tế, có thể thêm Javadoc chỉ ra API thay thế. Mức version và thời điểm loại bỏ phải theo chính sách của thư viện.

### 3.4. Versioning không tự bảo đảm tương thích

Hai artifact có cùng major version không tự động tương thích nếu nhóm không kiểm soát API, dependency hoặc hành vi. Có thể dùng API compatibility checker, binary compatibility validator, compile test với consumer mẫu và integration test để phát hiện thay đổi ngoài ý muốn.

Đối với thư viện public, một sample consumer hoặc compatibility test thường hữu ích hơn chỉ chạy unit test bên trong thư viện. Unit test xác nhận implementation; consumer test xác nhận artifact đã publish có thể được sử dụng theo cách người nhận mong đợi.

## 4. Dependency metadata và ranh giới API

### 4.1. Dependency bắc cầu

Giả sử library money-core sử dụng slf4j-api. Consumer khai báo money-core và build tool cần biết dependency nào phải có trên classpath.

Nếu metadata của library công bố dependency đúng, consumer có thể resolve dependency bắc cầu. Nếu chỉ phát hành JAR mà bỏ POM/Module Metadata, consumer có thể thiếu thư viện lúc compile hoặc runtime.

Gradle Java Library plugin phân biệt dependency được công bố qua API với dependency implementation nội bộ. Ví dụ:

~~~kotlin
plugins {
    id("java-library")
}

dependencies {
    api("com.example.platform:money-types:1.3.0")
    implementation("org.slf4j:slf4j-api:2.0.13")
}
~~~

Nếu kiểu của money-types xuất hiện trong public API của library, api có thể phù hợp. Nếu SLF4J chỉ được dùng bên trong implementation, implementation giúp không làm dependency đó trở thành compile API của consumer.

Trong Maven, scope và dependency management cũng ảnh hưởng metadata consumer nhận. Hãy chọn scope theo cách thư viện dùng dependency và cách consumer cần nhìn thấy nó.

### 4.2. Dependency optional và exclusions

Không phải mọi dependency của library đều cần tự động truyền sang consumer. Một integration tùy chọn có thể được công bố theo cách optional hoặc qua module/artifact riêng. Consumer chỉ thêm integration nếu cần.

Exclusion có thể loại một dependency bắc cầu, nhưng dùng rộng rãi có thể khiến consumer thiếu class hoặc nhận graph không tương thích. Library nên công bố dependency graph có chủ đích và kiểm tra bằng một consumer project độc lập.

### 4.3. Platform và BOM

Nếu nhiều library thuộc cùng một release train, có thể phát hành BOM/platform để consumer căn chỉnh version. Ví dụ, platform có thể quản lý version của money-core, money-format và money-jdbc.

Consumer Maven import BOM trong dependencyManagement; consumer Gradle có thể dùng platform dependency. BOM không nhất thiết kéo mọi library vào classpath; consumer vẫn khai báo module mà nó cần.

## 5. Snapshot, prerelease và release version

### 5.1. Snapshot là trạng thái phát triển

Trong Maven, version có hậu tố SNAPSHOT như 2.5.0-SNAPSHOT thường đại diện cho trạng thái phát triển chưa phải release bất biến. Repository snapshot có thể cập nhật artifact theo thời gian và metadata chỉ đến timestamped snapshot cụ thể.

Snapshot hữu ích cho nhóm phối hợp giữa các module trước khi phát hành chính thức, nhưng không nên dùng như dependency production lâu dài nếu yêu cầu build tái lập. Một build chạy hôm nay và ngày mai có thể resolve snapshot khác nhau.

Gradle không có một loại version SNAPSHOT đặc biệt trong core giống Maven, nhưng tổ chức có thể dùng naming convention, repository policy và dynamic/changing module semantics cho artifact phát triển. Cần hiểu cache và refresh behavior của build tool đang dùng.

### 5.2. Release version nên bất biến

Khi một release version được publish, không nên ghi đè cùng coordinates bằng nội dung mới. Nếu cần sửa lỗi, phát hành version tiếp theo. Điều này giúp consumer có thể tái lập build, cache nhất quán, checksum/provenance ổn định và truy vết artifact trong production.

### 5.3. Prerelease

Alpha, beta, milestone hoặc release candidate có thể giúp consumer thử trước. Quy ước version phải rõ ràng và repository nên phân tách quyền truy cập/prerelease khỏi release ổn định. Không để prerelease vô tình được dùng trong production chỉ vì version range hoặc dependency resolution chọn nó.

## 6. Publish library bằng Gradle

### 6.1. Cấu hình Maven Publish Plugin

Gradle Maven Publish Plugin tạo publication từ component của project. Ví dụ:

~~~kotlin
plugins {
    id("java-library")
    id("maven-publish")
}

group = "com.example.platform"
version = "2.4.1"

java {
    withSourcesJar()
    withJavadocJar()
}

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])
            artifactId = "money-core"
        }
    }

    repositories {
        maven {
            name = "internalReleases"
            url = uri("https://repo.example.com/releases")
            credentials {
                username = providers.gradleProperty("repoUser").orNull
                password = providers.gradleProperty("repoPassword").orNull
            }
        }
    }
}
~~~

Ở ví dụ này:

- java-library tạo Java library component.
- maven-publish cung cấp khả năng publish Maven-compatible publication.
- group, version và artifactId xác định coordinates.
- from(components["java"]) đưa component Java vào publication.
- withSourcesJar() và withJavadocJar() tạo artifact phụ nếu chính sách phát hành yêu cầu.
- Repository trong publishing là đích publish; nó khác repository dùng để resolve dependency.

Credentials được lấy từ Gradle properties để minh họa. Trong môi trường thực tế, nên cung cấp secrets từ CI secret store hoặc cơ chế credential an toàn; không commit username/password vào build file hoặc gradle.properties chia sẻ.

### 6.2. Publish task

Gradle tạo task theo publication và repository, ví dụ:

~~~bash
./gradlew tasks --all
./gradlew publishToMavenLocal
./gradlew publish
~~~

publishToMavenLocal đưa publication vào Maven local repository của người dùng để thử nghiệm tích hợp. Nó không chứng minh artifact đã được publish lên repository dùng chung.

publish thực hiện các task publish được cấu hình cho repository. Trong CI, cần đảm bảo credentials, URL, version và branch/tag policy đúng trước khi chạy task này.

### 6.3. Kiểm tra publication trước khi publish

Có thể kiểm tra:

- JAR chứa đúng class/resource.
- POM và Gradle Module Metadata mô tả đúng coordinates/dependencies.
- Sources/Javadoc artifact có mặt nếu yêu cầu.
- Version không phải release đã tồn tại.
- Public API không có thay đổi ngoài dự kiến.
- Dependency graph được consumer mong đợi.
- Checksums/signatures được tạo theo chính sách repository.

Dùng lệnh jar tf để xem nội dung JAR và xem POM/Module Metadata được tạo trong publication staging/build output hoặc repository local. Không chỉ dựa vào việc task publish kết thúc thành công.

### 6.4. Test bằng consumer độc lập

Một cách kiểm tra có giá trị là tạo một project nhỏ không dùng project dependency trực tiếp, mà resolve đúng coordinates từ local hoặc staging repository.

Consumer test có thể:

1. Khai báo dependency theo coordinates.
2. Resolve compile/runtime classpath.
3. Compile một đoạn code sử dụng public API.
4. Chạy test hoặc một smoke test nhỏ.
5. Kiểm tra dependency bắc cầu và version được chọn.

Điều này xác nhận artifact đã publish và metadata của nó có thể được sử dụng độc lập. Nếu chỉ dùng project dependency trong cùng multi-project build, một số vấn đề metadata publication có thể bị che khuất.

## 7. Publish library bằng Maven

### 7.1. POM mô tả artifact

Một library Maven thường có packaging jar và coordinates:

~~~xml
<groupId>com.example.platform</groupId>
<artifactId>money-core</artifactId>
<version>2.4.1</version>
<packaging>jar</packaging>
~~~

POM có thể khai báo dependencies, properties, license, developers, SCM, issue management và các thông tin khác tùy yêu cầu repository/tổ chức.

Ví dụ dependency:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.slf4j</groupId>
        <artifactId>slf4j-api</artifactId>
        <version>2.0.13</version>
    </dependency>
</dependencies>
~~~

Maven sẽ đưa dependency metadata thích hợp vào POM phát hành để consumer có thể resolve dependency bắc cầu theo scope.

### 7.2. Repository đích qua distributionManagement

POM có thể khai báo repository phát hành:

~~~xml
<distributionManagement>
    <repository>
        <id>internal-releases</id>
        <url>https://repo.example.com/releases</url>
    </repository>
    <snapshotRepository>
        <id>internal-snapshots</id>
        <url>https://repo.example.com/snapshots</url>
    </snapshotRepository>
</distributionManagement>
~~~

ID repository được liên kết với credentials trong settings.xml của người dùng/CI, không nên ghi secret trực tiếp trong POM.

Ví dụ settings.xml:

~~~xml
<settings>
    <servers>
        <server>
            <id>internal-releases</id>
            <username>CI_USER</username>
            <password>INJECTED_SECRET</password>
        </server>
    </servers>
</settings>
~~~

Giá trị trong ví dụ là placeholder. CI nên tạo settings phù hợp từ secret store hoặc dùng cơ chế credential được tổ chức hỗ trợ.

### 7.3. Publish bằng deploy lifecycle

Chạy:

~~~bash
./mvnw deploy
~~~

Maven thực thi các phase trước đó trong default lifecycle, bao gồm compile, test, package, verify và deploy theo plugin binding/configuration. Vì vậy, deploy thường vừa build/test vừa upload artifact và metadata lên repository.

Nếu cần chỉ tạo artifact local để kiểm tra, có thể dùng package hoặc install theo mục đích. install đưa artifact vào local Maven repository; deploy đưa artifact tới remote repository đã cấu hình. Hai bước này không giống nhau.

### 7.4. Phân biệt local install và remote deploy

| Lệnh | Đích | Người tiêu thụ |
|---|---|---|
| mvnw package | Thư mục target của project | Người build kiểm tra artifact cục bộ |
| mvnw install | Local Maven repository của người dùng | Các project build trên cùng máy |
| mvnw deploy | Remote repository trong distributionManagement hoặc cấu hình deploy | Các consumer được cấp quyền truy cập |

Không nên dùng local install như bằng chứng release đã được công bố. Máy khác không tự nhìn thấy artifact trong local Maven repository của bạn.

## 8. Triển khai ứng dụng là đưa artifact vào runtime environment

### 8.1. Ứng dụng có entry point và runtime contract

Một ứng dụng Java thường có main class hoặc launcher do framework cung cấp. Ví dụ:

~~~java
package com.example.order;

public class OrderApplication {
    public static void main(String[] args) {
        System.out.println("Order service starting");
    }
}
~~~

Để triển khai, cần biết cách khởi chạy và tham số JVM, Java runtime version, dependency runtime, resource, port/protocol, network access, cấu hình môi trường, secrets, quyền truy cập, health check, logging, metrics, shutdown behavior và tài nguyên CPU/RAM. Chỉ có JAR không đảm bảo các điều kiện này đã được đáp ứng.

### 8.2. Các dạng artifact ứng dụng

| Dạng | Đặc điểm | Khi phù hợp |
|---|---|---|
| Thin executable JAR | JAR ứng dụng, dependency được cung cấp bên ngoài | Ứng dụng đơn giản hoặc distribution có thư mục lib/script |
| Fat/uber JAR | Gộp dependency vào một archive | Muốn triển khai một file, plugin xử lý resource/metadata đúng |
| Framework executable JAR | Archive có launcher và cấu trúc theo framework | Ứng dụng dùng framework hỗ trợ kiểu đóng gói này |
| Application distribution | JAR, dependency và script trong ZIP/TAR | Cần JVM options, script, nhiều file runtime |
| Container image | Ứng dụng cùng runtime/base image và file cần thiết | Triển khai trên container platform hoặc orchestration |
| Native image/package | Executable hoặc package theo công cụ/framework | Khi cần mô hình runtime/native cụ thể và đã đánh giá trade-off |

Không có một dạng duy nhất phù hợp mọi ứng dụng. Lựa chọn phụ thuộc nền tảng vận hành, cách quản lý runtime, nhu cầu scale, startup, observability và quy trình cập nhật.

### 8.3. Application distribution với Gradle

Gradle Application plugin có thể tạo distribution chứa application JAR, runtime dependency và script:

~~~kotlin
plugins {
    id("application")
}

application {
    mainClass.set("com.example.order.OrderApplication")
}
~~~

Chạy ứng dụng trong build:

~~~bash
./gradlew run
~~~

Tạo distribution:

~~~bash
./gradlew installDist
./gradlew distZip
./gradlew distTar
~~~

Distribution thường có thư mục bin chứa script và lib chứa JAR. Script giúp thiết lập classpath và gọi main class. Artifact distribution có thể được upload như build artifact hoặc đưa vào package/deployment process.

### 8.4. Executable JAR không đồng nghĩa đã deploy

Một JAR có Main-Class có thể chạy bằng java -jar nếu runtime dependency được cung cấp. Nhưng nó chưa được triển khai chỉ vì lệnh chạy thử thành công trên máy developer.

Deployment còn cần đặt artifact vào môi trường đích, cấp cấu hình, secrets, network policy, quyền truy cập, tài nguyên và cách giám sát. Một ứng dụng chạy trong terminal local có thể thất bại trong container nếu thiếu certificate, timezone, filesystem permission hoặc biến môi trường.

## 9. Cấu hình ứng dụng theo môi trường

### 9.1. Không đóng cứng cấu hình production vào artifact

Một artifact nên có thể được dùng ở nhiều môi trường nếu thiết kế cho phép. Cấu hình thay đổi theo môi trường như database URL, endpoint, feature flag và log level thường được truyền từ bên ngoài.

Ví dụ, ứng dụng có thể đọc environment variables:

~~~java
String databaseUrl = System.getenv("DATABASE_URL");
String portValue = System.getenv().getOrDefault("PORT", "8080");
~~~

Hoặc dùng system properties:

~~~bash
java -Dapp.environment=staging -jar order-service.jar
~~~

Cấu hình thực tế phụ thuộc framework, nhưng nguyên tắc chung là tách code/artifact khỏi giá trị môi trường có thể thay đổi.

### 9.2. Secrets cần được cấp an toàn

Không đặt password, token, private key hoặc credential production trong source code, JAR, Version Catalog/POM, file properties được commit, Docker image layer công khai hoặc build log.

Dùng secret manager, CI/CD secret store hoặc cơ chế cấp credential của nền tảng triển khai. Hạn chế quyền của từng secret và tránh in giá trị vào log.

### 9.3. Config mặc định và config bên ngoài

Có thể đóng gói default properties trong resource, sau đó cho phép external config ghi đè. Thứ tự ưu tiên phải được định nghĩa rõ để người vận hành biết giá trị nào thắng khi có nhiều nguồn. Không nên để cấu hình cùng key được đọc theo thứ tự không rõ ràng.

### 9.4. Một artifact, nhiều môi trường

Một pipeline tốt thường build artifact một lần từ source revision đã xác định, sau đó đưa cùng artifact qua các môi trường dev/test/staging/production với cấu hình riêng. Điều này giảm nguy cơ mỗi môi trường chạy một binary khác nhau do build lại với property khác.

Nếu build cần tạo artifact riêng theo môi trường, hãy ghi rõ lý do và lưu metadata/provenance tương ứng. Không nên mặc định build lại cho production nếu mục tiêu là promote cùng một artifact đã được kiểm thử.

## 10. Container image và triển khai ứng dụng

### 10.1. Container image đóng gói runtime contract

Một container image thường chứa ứng dụng, runtime hoặc base image, thư viện hệ thống và lệnh khởi chạy. Ví dụ Dockerfile đơn giản:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY build/libs/order-service.jar app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Ví dụ này minh họa image có JRE 21 và JAR ứng dụng. Trong production cần pin base image theo digest hoặc version policy phù hợp, quét image, chạy bằng user ít quyền, quản lý certificate/timezone và không nhúng secret vào image.

### 10.2. Build image và deploy image là hai bước

- Build image: tạo container image từ JAR, base image và các lớp filesystem.
- Push image: đưa image lên container registry.
- Deploy image: cấu hình nền tảng chạy image, số replica, resource limit, network, secret và health check.
- Rollout: thay workload đang chạy bằng version mới theo chiến lược được chọn.

Push image thành công chưa có nghĩa workload đã được triển khai thành công. Deployment có thể bị từ chối, container crash, health check fail hoặc không kết nối được dịch vụ phụ trợ.

### 10.3. Tag image và tính bất biến

Tag như latest hoặc staging có thể được di chuyển sang digest khác theo thời gian. Đối với release cần truy vết, nên lưu digest image và dùng định danh bất biến khi promote/rollback.

~~~text
registry.example.com/order-service:2.4.1
registry.example.com/order-service@sha256:...
~~~

Tag thuận tiện cho con người, digest định danh chính xác nội dung image. Chính sách cụ thể tùy registry và deployment platform.

## 11. Publish artifact ứng dụng và deploy là hai hoạt động có thể tách rời

Ứng dụng cũng có thể được lưu trong artifact repository. Ví dụ CI upload executable JAR hoặc distribution ZIP vào repository để một deployment job lấy về. Việc publish ở đây là lưu trữ và phân phối file; deployment là cài đặt/cập nhật runtime.

~~~text
Commit / Tag
     |
     v
Compile + Test
     |
     v
Package application
     |
     v
Publish artifact to repository
     |
     v
Deploy to test environment
     |
     v
Smoke / integration checks
     |
     v
Promote same artifact to production
     |
     v
Monitor / rollback if required
~~~

Đối với library, publish lên repository thường là hành động cung cấp version mới cho consumer. Đối với application, upload artifact là một phần trong chuỗi triển khai; cần bước đưa nó vào môi trường chạy.

## 12. Versioning ứng dụng và release strategy

### 12.1. Application version

Ứng dụng cũng cần version để truy vết release. Version có thể theo semantic versioning, calendar versioning hoặc chính sách nội bộ. Ngoài version hiển thị, release nên lưu Git commit/tag, build run ID, artifact checksum, dependency lock/graph, build tool và JDK version, image digest nếu có, migration/version schema liên quan.

Những thông tin này giúp biết chính xác code và dependency nào đang chạy trong production.

### 12.2. Version library và version application có thể độc lập

Một ứng dụng có thể phụ thuộc money-core 2.4.1 nhưng có version riêng 7.8.0. Khi phát hành money-core 2.4.2, application không tự động đổi version dependency cho đến khi build được cập nhật và phát hành theo quy trình của ứng dụng.

Ngược lại, một application release có thể thay đổi code mà không phát hành library mới. Hai chu kỳ release phục vụ hai consumer khác nhau.

### 12.3. Release candidate và promotion

Một release candidate của ứng dụng có thể được triển khai ở staging, kiểm tra smoke/integration, sau đó promote cùng artifact/image digest sang production. Nếu build lại ở mỗi môi trường, artifact có thể khác nhau do dependency, timestamp, configuration filtering hoặc môi trường build.

Với thư viện, release candidate có thể được publish vào staging repository để consumer test trước. Sau khi xác nhận, artifact được promote hoặc publish vào release repository theo chính sách bất biến.

## 13. Repository phát hành và môi trường triển khai

| Nơi lưu trữ | Vai trò | Đối tượng sử dụng |
|---|---|---|
| Maven repository | Lưu JAR/POM và metadata theo coordinates | Maven/Gradle consumer |
| Gradle-compatible repository | Lưu module, metadata và variants | Gradle consumer |
| Artifact registry tổng quát | Lưu build outputs, ZIP/TAR, package hoặc release assets | CI/CD và người vận hành |
| Container registry | Lưu container images theo tag/digest | Container runtime/orchestrator |
| Deployment platform | Lưu trạng thái workload/configuration và quản lý rollout | Runtime/operator |

Một repository có thể phục vụ nhiều loại artifact, nhưng policy cần phân biệt snapshot/release, quyền đọc/ghi và retention. Không cấp quyền publish cho mọi developer nếu tổ chức cần kiểm soát release production.

## 14. Gradle: tách publishing và application distribution

### 14.1. Library project

~~~kotlin
plugins {
    id("java-library")
    id("maven-publish")
}

group = "com.example.platform"
version = "2.4.1"

java {
    withSourcesJar()
    withJavadocJar()
}

publishing {
    publications {
        create<MavenPublication>("library") {
            from(components["java"])
            artifactId = "money-core"
        }
    }

    repositories {
        maven {
            name = "staging"
            url = uri("https://repo.example.com/staging")
        }
    }
}
~~~

Task publish sẽ tạo publication cho consumer. Không cần cấu hình main class nếu artifact chỉ là library.

### 14.2. Application project

~~~kotlin
plugins {
    id("application")
}

group = "com.example.apps"
version = "7.8.0"

application {
    mainClass.set("com.example.order.OrderApplication")
}
~~~

Application plugin hỗ trợ run và tạo distribution. Ví dụ:

~~~bash
./gradlew run
./gradlew installDist
./gradlew distZip
~~~

Nếu tổ chức muốn lưu ZIP distribution trong artifact repository, có thể upload output distribution bằng pipeline hoặc cấu hình publication phù hợp. Nhưng bước triển khai vẫn cần đưa distribution vào môi trường chạy, cấu hình và khởi động ứng dụng.

### 14.3. Không dùng một publication cho mọi mục tiêu mà không xác định consumer

Gradle Maven Publish có thể publish cả library và application artifact. Việc plugin cho phép publish không có nghĩa artifact đó phù hợp làm dependency cho consumer. Hãy quyết định consumer cần một component API hay một gói triển khai có entry point và runtime dependency.

## 15. Maven: tách install/deploy artifact khỏi deployment ứng dụng

### 15.1. Library

Với library project, POM mô tả coordinates và dependencies. Chạy:

~~~bash
./mvnw verify
./mvnw deploy
~~~

verify kiểm tra artifact qua các phase được cấu hình; deploy upload artifact và metadata lên repository đích.

### 15.2. Application

Ứng dụng Maven có thể tạo executable JAR hoặc distribution qua plugin phù hợp. Sau khi package, CI có thể lưu file JAR/ZIP như artifact rồi chuyển sang deployment job.

~~~bash
./mvnw package
~~~

Lệnh này tạo package theo cấu hình project; nó không tự cài đặt ứng dụng lên production. Deployment có thể do container pipeline, script, Ansible, Kubernetes, service manager hoặc nền tảng khác thực hiện.

### 15.3. Maven deploy không đồng nghĩa triển khai ứng dụng

Maven phase deploy có nghĩa đưa artifact của Maven project lên remote repository theo cấu hình. Nó không có nghĩa kết nối vào server production, restart service hoặc cập nhật workload. Tên phase dễ gây hiểu nhầm nếu không phân biệt ngữ cảnh build lifecycle với vận hành ứng dụng.

## 16. Kiểm chứng trước khi phát hành thư viện

Trước khi publish library, cần xác nhận artifact thực sự dùng được từ góc nhìn consumer.

### 16.1. Build và test

Chạy test, kiểm tra Javadoc/source nếu yêu cầu và xác nhận không có lỗi API hoặc dependency. Với thư viện có nhiều module, kiểm tra các artifact liên quan được version nhất quán.

### 16.2. Kiểm tra publication metadata

Xác nhận POM/Gradle Module Metadata chứa đúng group/artifact/version, dependency và scope/variant, license và thông tin SCM nếu repository yêu cầu, sources/Javadoc artifacts nếu policy yêu cầu, và không chứa URL repository hoặc secret riêng của máy build.

### 16.3. Kiểm tra consumer

Dùng project consumer độc lập để resolve đúng coordinates. Compile code sử dụng API public, chạy smoke test và xem dependency tree. Điều này phát hiện lỗi metadata mà test nội bộ có thể bỏ sót.

### 16.4. Kiểm tra tính toàn vẹn và nguồn gốc

Tạo checksum của artifact cuối cùng, ký theo policy nếu cần, lưu provenance và release notes. Consumer hoặc repository policy có thể dùng thông tin đó để xác minh nguồn và nội dung.

## 17. Kiểm chứng trước khi triển khai ứng dụng

Một ứng dụng cần kiểm tra cả artifact lẫn điều kiện vận hành.

### 17.1. Artifact và runtime

- Đúng entry point hoặc launcher.
- Đủ runtime dependencies.
- Đúng Java runtime version.
- Resource và file cần thiết được đóng gói.
- Native dependency tương thích OS/architecture nếu có.
- Image/package được tạo từ source revision dự kiến.

### 17.2. Configuration và secrets

- Giá trị config bắt buộc đã được cấp.
- Secrets lấy từ nguồn an toàn.
- Không có secret bị nhúng vào JAR/image/log.
- External config có quyền đọc đúng.
- Cấu hình theo environment được review.

### 17.3. Readiness và health

- Ứng dụng khởi động thành công.
- Health endpoint hoặc cơ chế kiểm tra tương đương hoạt động.
- Kết nối database/message broker/service ngoài được xác nhận.
- Log và metrics được thu thập.
- Shutdown/restart hoạt động theo chính sách.

### 17.4. Rollout và rollback

Deployment plan cần xác định cập nhật tuần tự hay rolling/canary/blue-green, tiêu chí tiếp tục hoặc dừng rollout, thời gian quan sát và health threshold, cách quay về version/image digest trước, tương thích database schema giữa phiên bản cũ và mới, và ai có quyền thực hiện/xác nhận deployment.

Một container chạy được chưa chắc deployment hoàn tất. Cần kiểm tra ứng dụng đã sẵn sàng phục vụ và không gây lỗi cho hệ thống phụ thuộc.

## 18. Database migration và compatibility khi triển khai

Ứng dụng thường phụ thuộc database schema. Nếu version mới yêu cầu cột hoặc bảng chưa tồn tại, rollout có thể thất bại. Nếu migration phá tương thích ngay trong lúc instance cũ vẫn đang chạy, rolling deployment có thể gây lỗi.

Một chiến lược thường dùng là expand-and-contract:

1. Thêm schema mới theo cách vẫn tương thích với application version đang chạy.
2. Deploy application version có thể đọc/ghi theo schema chuyển tiếp.
3. Migrate dữ liệu hoặc chuyển dần traffic.
4. Xác nhận không còn instance/code cũ cần schema cũ.
5. Loại bỏ schema cũ ở release sau.

Không phải migration nào cũng cần nhiều giai đoạn, nhưng với deployment không downtime hoặc rolling rollout, cần xem xét compatibility giữa application version và schema version.

Thư viện cũng có thể ảnh hưởng serialization hoặc schema contract, nhưng việc migrate database của ứng dụng tiêu thụ thường thuộc trách nhiệm deployment/application chứ không phải library publish đơn thuần.

## 19. Promotion, rollback và truy vết release

### 19.1. Promote cùng artifact

Một quy trình an toàn thường build một lần, test artifact, sau đó promote cùng artifact qua các môi trường. Lưu checksum/digest giúp xác nhận staging và production nhận đúng nội dung đã kiểm thử.

Với library, staging repository có thể giữ release candidate để consumer thử. Khi được chấp thuận, artifact được chuyển sang release repository theo policy.

Với application, registry có thể lưu image và digest. Deployment staging dùng digest đó; production promote cùng digest thay vì build lại từ source.

### 19.2. Rollback ứng dụng

Rollback thường là triển khai lại application version hoặc image digest trước. Cần đảm bảo artifact cũ vẫn được lưu, cấu hình tương thích với version cũ, database migration không làm version cũ không thể chạy, secrets và external contracts vẫn hợp lệ, health check và monitoring xác nhận rollback thành công.

### 19.3. Rollback thư viện

Library release đã publish thường không nên bị xóa hoặc ghi đè vì consumer có thể đang phụ thuộc vào nó. Nếu release có lỗi, phát hành version sửa lỗi và hướng dẫn consumer nâng cấp. Consumer có thể pin về version trước trong khi chờ bản mới.

Với repository nội bộ, policy có thể cho phép quarantine hoặc deprecate một release, nhưng không nên thay byte của cùng coordinates/version mà không có quy trình thông báo và xử lý rõ ràng.

## 20. Bảo mật và quyền trong hai quy trình

Library publishing và application deployment thường cần quyền khác nhau.

| Quyền | Library release | Application deployment |
|---|---|---|
| Ghi artifact repository | Có thể cần | Có thể cần để lưu build output |
| Ghi container registry | Không nhất thiết | Thường cần nếu deploy container |
| Truy cập production secrets | Không cần cho compile/publish thông thường | Chỉ job/runtime được cấp quyền phù hợp |
| Thay đổi production workload | Không cần | Chỉ deployment identity/operator có quyền |
| Ký artifact | Theo release policy | Theo release/image policy |
| Xóa/ghi đè release | Thường bị hạn chế | Tag có thể thay đổi theo policy; digest nên được truy vết bất biến |

Không nên cấp cho job build từ pull request không tin cậy quyền publish release hoặc deploy production. Tách build/test, publish và deployment theo trust boundary giúp giảm rủi ro khi mã thay đổi chưa được review.

Credentials nên được giới hạn theo repository/environment, có thời hạn hoặc rotation theo policy. Không truyền secrets qua command line nếu có nguy cơ xuất hiện trong process list hoặc log; dùng cơ chế secret injection được nền tảng hỗ trợ.

## 21. Những nhầm lẫn thường gặp

- **Cho rằng build thành công là đã release.** Build chỉ tạo output; publish còn cần metadata, repository và quyền phát hành.
- **Cho rằng Maven deploy là deploy ứng dụng.** Maven deploy upload artifact lên repository; deployment vận hành là bước khác.
- **Cho rằng mọi JAR đều là library.** Executable JAR có thể là ứng dụng; vai trò phụ thuộc consumer và cách sử dụng.
- **Cho rằng mọi executable JAR đều chứa dependency.** Thin JAR có thể cần classpath hoặc thư mục lib bên ngoài.
- **Dùng SNAPSHOT làm dependency production không kiểm soát.** Nội dung có thể thay đổi giữa các lần resolve.
- **Ghi đè release version đã publish.** Điều này phá tính bất biến, cache và khả năng tái lập.
- **Không công bố dependency metadata.** Consumer có thể compile hoặc chạy thất bại dù JAR đã tải được.
- **Chỉ test nội bộ library.** Consumer có thể gặp lỗi do POM/variants/API publication.
- **Build lại artifact ở mỗi môi trường.** Các môi trường có thể chạy bytecode khác nhau; nên promote cùng artifact khi quy trình yêu cầu.
- **Đưa production secrets vào JAR hoặc image.** Artifact có thể được lưu trữ/chia sẻ rộng và không nên chứa bí mật.
- **Coi push image là deployment thành công.** Workload còn phải được khởi chạy, health check và giám sát.
- **Không có kế hoạch rollback.** Release có thể gây lỗi dù build/test thành công.
- **Bỏ qua database compatibility.** Schema thay đổi có thể làm rolling deployment hoặc rollback thất bại.

## 22. Bảng chọn quy trình theo loại project

| Loại project | Build output | Bước tiếp theo chính | Câu hỏi kiểm chứng |
|---|---|---|---|
| Java library | JAR + POM/Module Metadata, có thể kèm sources/Javadoc | Publish lên Maven-compatible repository | Consumer resolve, compile và chạy được không? |
| Shared platform/BOM | POM/platform metadata | Publish version policy cho nhiều consumer | Version constraints có đúng và nhất quán không? |
| CLI application | Executable JAR hoặc application distribution | Phân phối package và cấu hình runtime | Lệnh khởi chạy và dependency có đầy đủ không? |
| Web/service application | Executable JAR, distribution hoặc container image | Deploy vào server/container platform | Health, config, network và resource có đúng không? |
| Batch application | JAR/image và job configuration | Đăng ký/chạy job trong scheduler | Input, retry, idempotency và output có đúng không? |
| Framework/plugin extension | Plugin/library artifact và metadata | Publish để host application resolve | Host framework version và extension contract có tương thích không? |

## 23. Ví dụ: một repository có library và application

Giả sử hệ thống có hai project Gradle: domain là thư viện dùng chung và application là chương trình chạy.

Cấu trúc:

~~~text
order-platform/
├── settings.gradle.kts
├── domain/
│   └── build.gradle.kts
└── application/
    └── build.gradle.kts
~~~

Module domain:

~~~kotlin
plugins {
    id("java-library")
    id("maven-publish")
}

group = "com.example.order"
version = "1.5.0"

publishing {
    publications {
        create<MavenPublication>("domainLibrary") {
            from(components["java"])
            artifactId = "order-domain"
        }
    }
}
~~~

Module application:

~~~kotlin
plugins {
    id("application")
}

group = "com.example.order"
version = "4.2.0"

application {
    mainClass.set("com.example.order.OrderApplication")
}

dependencies {
    implementation(project(":domain"))
}
~~~

Hai version độc lập:

- order-domain 1.5.0 là version của library contract.
- order application 4.2.0 là version của ứng dụng được triển khai.

Khi domain được cập nhật, application cần build/test lại với version hoặc project output tương ứng. Sau đó application có thể tạo distribution hoặc container image để triển khai. Publish domain không tự deploy application; build application cũng không tự phát hành domain lên repository trừ khi pipeline được cấu hình rõ.

## 24. Ví dụ pipeline: library release

Một pipeline library release có thể gồm:

~~~text
Checkout tagged source
        |
        v
Validate version and working tree
        |
        v
Compile + unit tests
        |
        v
API compatibility checks
        |
        v
Build JAR + sources/Javadoc
        |
        v
Inspect POM / Gradle metadata
        |
        v
Consumer integration test
        |
        v
Sign + checksum + provenance
        |
        v
Publish immutable release
        |
        v
Release notes / announce to consumers
~~~

Các bước cụ thể phụ thuộc repository và chính sách tổ chức. Điểm quan trọng là consumer metadata/API phải được xác nhận trước khi publish, và release version phải bất biến sau khi công bố.

## 25. Ví dụ pipeline: application deployment

Một pipeline ứng dụng có thể gồm:

~~~text
Checkout source revision
        |
        v
Compile + unit/integration tests
        |
        v
Package executable artifact
        |
        v
Create image/distribution
        |
        v
Scan + sign + store artifact
        |
        v
Deploy to staging
        |
        v
Smoke / health / integration checks
        |
        v
Promote same digest to production
        |
        v
Monitor rollout
        |
        +---- healthy ----> Complete
        |
        +---- unhealthy --> Rollback / investigate
~~~

Artifact repository hoặc container registry là nơi lưu trữ; deployment platform là nơi quản lý workload đang chạy. Pipeline cần tách quyền publish khỏi quyền deploy và chỉ cấp quyền production ở bước được kiểm soát.

## 26. Bài tập vận dụng

Một tổ chức có thư viện order-domain và ứng dụng order-service. Thư viện cung cấp public API cho nhiều ứng dụng nội bộ; order-service sử dụng thư viện, kết nối PostgreSQL và chạy trong container.

Hãy xác định:

1. Artifact nào nên được phát hành như library và coordinates gồm những thành phần nào?
2. Vì sao library release cần POM hoặc Gradle Module Metadata ngoài JAR?
3. Khi public API của thư viện thay đổi không tương thích, version nên phản ánh điều gì?
4. Consumer test giúp phát hiện vấn đề nào mà unit test nội bộ có thể bỏ sót?
5. Vì sao không nên ghi đè nội dung của cùng release coordinates/version?
6. publishToMavenLocal, Maven install và remote deploy khác nhau như thế nào?
7. Executable JAR của order-service cần những điều kiện runtime nào?
8. Vì sao publish JAR lên artifact repository chưa có nghĩa service đã được triển khai?
9. Cấu hình database và password nên được cấp vào container bằng cách nào?
10. Vì sao nên promote cùng image digest từ staging sang production?
11. Nếu database schema thay đổi, cần kiểm tra compatibility với application version cũ ra sao?
12. Library release lỗi và application deployment lỗi có chiến lược rollback khác nhau ở điểm nào?
13. Job nào nên có quyền ghi release repository và job nào cần quyền thay đổi production workload?
14. Những thông tin nào cần lưu để truy vết một application release đang chạy?

Có thể thực hành bằng cách tạo một Gradle Java Library project và một Application project phụ thuộc vào nó. Publish library vào Maven local, tạo consumer project resolve coordinates, sau đó tạo application distribution. Cuối cùng, đóng gói ứng dụng thành container image thử nghiệm và phân biệt rõ bước build image, push image và chạy workload.

## 27. Nguyên tắc duy trì lâu dài

- Xác định consumer trước khi chọn cách phát hành artifact.
- Giữ tọa độ và release version của library ổn định, bất biến.
- Công bố dependency metadata, variants và tài liệu API đúng.
- Dùng versioning phản ánh mức compatibility của public contract.
- Kiểm tra library từ một consumer độc lập trước khi publish.
- Tách repository release, snapshot và staging theo policy.
- Cấp credentials publish qua secret store và giới hạn quyền.
- Chọn application package theo runtime/deployment platform.
- Tách cấu hình môi trường và secrets khỏi artifact.
- Build artifact một lần rồi promote cùng artifact/digest khi quy trình yêu cầu.
- Kiểm tra health, observability, resource và database compatibility sau deploy.
- Lưu checksum, signature, provenance, source revision và release metadata.
- Chuẩn bị rollback trước khi triển khai thay đổi có rủi ro.

Phát hành thư viện là công bố một thành phần có contract để consumer tích hợp; triển khai ứng dụng là đưa một chương trình vào môi trường runtime và chịu trách nhiệm cho hoạt động của nó. Khi giữ rõ hai mục tiêu này, nhóm có thể dùng đúng cơ chế publish của Gradle/Maven cho library, đúng distribution/container/deployment workflow cho application, đồng thời quản lý version, metadata, bảo mật và rollback theo trách nhiệm của từng loại artifact.

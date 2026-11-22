# Kiểm chứng trước phát hành bằng một dự án tiêu thụ độc lập

Một thư viện Gradle có thể biên dịch thành công, vượt qua unit test và tạo được JAR nhưng vẫn phát hành ra một package mà project khác không sử dụng được. Nguyên nhân có thể nằm ở publication metadata, tọa độ artifact, dependency transitive, variant, file bị thiếu trong package hoặc cấu hình repository.

Kiểm chứng bằng một **dự án tiêu thụ độc lập** giúp kiểm tra sản phẩm từ góc nhìn của người dùng thư viện. Dự án consumer chỉ biết tọa độ dependency và repository được công bố; nó không tham chiếu source project, task nội bộ hoặc đường dẫn build của producer.

Đây là bước quan trọng trước khi release một library, plugin, platform hoặc package dùng chung. Nó xác nhận artifact đã publish có thể được tìm thấy, resolve, biên dịch, chạy và sử dụng theo contract mà nhà phát hành cam kết.

## 1. Vì sao cần một consumer độc lập?

Trong cùng một Gradle multi-project build, consumer có thể khai báo:

~~~groovy
dependencies {
    implementation project(':orders-client')
}
~~~

Gradle dùng project component của producer để cung cấp variant và artifact phù hợp. Cách này tốt cho phát triển nhiều mô-đun trong cùng build, nhưng chưa kiểm tra đầy đủ những gì người dùng bên ngoài sẽ nhận được sau khi publish.

Một publication có thể gặp lỗi mà project dependency không bộc lộ:

- JAR được publish thiếu class hoặc resource cần thiết.
- POM không khai báo đúng dependency transitive.
- Gradle Module Metadata mô tả sai variant hoặc dependency.
- Tọa độ group, artifact hoặc version khác với tài liệu.
- Artifact classifier hoặc packaging không đúng.
- API công khai sử dụng kiểu từ dependency nhưng dependency không được công bố đúng scope.
- Plugin marker hoặc plugin implementation không được publish đầy đủ.
- Module descriptor không có trong JAR hoặc khai báo sai tên module.
- Consumer cần một repository hoặc credential chưa được hướng dẫn.
- Publication chỉ hoạt động trên máy producer vì consumer vô tình dùng project path hoặc artifact cũ trong local repository.

Một consumer độc lập loại bỏ các đường tắt đó. Nó chỉ dùng artifact đã publish và các repository được cấu hình như một người dùng thực tế.

~~~text
Producer project
      |
      v
Build and test
      |
      v
Create publication
      |
      v
Publish to staging repository
      |
      v
Published files + metadata
      |
      v
Independent consumer project
      |
      +--> Resolve coordinates
      |
      +--> Compile against public API
      |
      +--> Run tests/application
      |
      +--> Inspect runtime/transitive dependencies
      |
      v
Release decision
~~~

Kiểm thử này không thay thế unit test hoặc integration test của producer. Nó bổ sung một góc nhìn khác: artifact mà repository thực sự cung cấp có dùng được như một dependency độc lập hay không.

## 2. Phân biệt project dependency với published dependency

Hai cách khai báo dưới đây có ý nghĩa khác nhau:

~~~groovy
// Cùng một Gradle build
dependencies {
    implementation project(':orders-client')
}
~~~

~~~groovy
// Một build độc lập tiêu thụ artifact đã publish
dependencies {
    implementation 'com.example.orders:orders-client:1.4.0-rc.1'
}
~~~

Ở cách thứ nhất, Gradle biết producer project và có thể lấy component từ project model. Ở cách thứ hai, Gradle phải resolve module theo tọa độ từ một repository.

| Khía cạnh | Project dependency | Published dependency |
|---|---|---|
| Nguồn component | Project trong cùng build | Repository |
| Định danh | Project path, ví dụ :orders-client | Group, artifact, version |
| Metadata | Project component/variants | Gradle Module Metadata, POM hoặc metadata repository |
| File được dùng | Output component của project | Artifact đã publish |
| Kiểm tra publication | Chưa đầy đủ | Có |
| Phụ thuộc cấu trúc multi-project | Có | Không |
| Gần với trải nghiệm người dùng thư viện | Một phần | Có |

Một consumer độc lập không nên có dòng project dependency tới producer, không include producer bằng composite build và không đọc JAR từ thư mục build của producer. Nếu dùng một trong các cách đó, bài kiểm tra không còn chứng minh publication có thể được tiêu thụ qua repository.

## 3. Các thành phần cần kiểm chứng trong một publication

Một publication không chỉ là file JAR. Nó là một tập hợp artifact và metadata gắn với tọa độ module.

Với một thư viện Java dùng Maven Publish plugin, repository thường có cấu trúc:

~~~text
staging-repository/
  com/
    example/
      orders/
        orders-client/
          1.4.0-rc.1/
            orders-client-1.4.0-rc.1.jar
            orders-client-1.4.0-rc.1.pom
            orders-client-1.4.0-rc.1.module
            orders-client-1.4.0-rc.1-sources.jar
            orders-client-1.4.0-rc.1-javadoc.jar
~~~

Tập file chính xác phụ thuộc publication và cấu hình. Ví dụ, sources JAR và Javadoc JAR chỉ có nếu producer yêu cầu tạo và publish chúng.

| Thành phần | Mục đích kiểm chứng |
|---|---|
| Main artifact | Có đúng binary và nội dung cần phân phối không? |
| POM | Maven consumer có nhận đúng tọa độ, dependency và metadata không? |
| Gradle Module Metadata | Gradle consumer có nhận đúng variants, attributes và dependency không? |
| Sources JAR | Source code được publish có khớp với binary/API không? |
| Javadoc JAR | Documentation artifact có được tạo và publish không? |
| Checksums/signatures | File có thể được xác minh tính toàn vẹn và nguồn gốc không? |
| Plugin marker | Với Gradle plugin, plugin ID có thể được resolve qua plugin DSL không? |

Không phải mọi loại publication đều cần mọi file. Cần kiểm tra đúng contract của sản phẩm và consumer mà tổ chức hỗ trợ.

## 4. Chọn repository staging để thử publication

Nên publish bản thử nghiệm vào một repository riêng, dễ xóa và không ảnh hưởng đến release đã phát hành. Một Maven repository dạng thư mục cục bộ là lựa chọn thuận tiện để kiểm tra trước khi đẩy lên repository từ xa.

Ví dụ cấu trúc workspace:

~~~text
workspace/
  orders-client/
    settings.gradle
    build.gradle
    src/
    build/
      staging-repository/
  consumer-smoke/
    settings.gradle
    build.gradle
    src/
~~~

Hai project là hai Gradle build riêng biệt. Consumer không được include producer trong settings.

Repository staging đặt dưới thư mục build của producer giúp output thử nghiệm được quản lý cùng build và có thể xóa bằng clean. Trong CI, nếu consumer chạy ở job hoặc runner khác, cần upload staging repository hoặc publication bundle làm artifact để job consumer tải xuống.

### Vì sao không nên mặc định dùng mavenLocal?

Có thể publish bằng:

~~~shell
./gradlew publishToMavenLocal
~~~

và thêm:

~~~groovy
repositories {
    mavenLocal()
}
~~~

Cách này tiện cho thử nghiệm nhanh nhưng Maven local repository thường được chia sẻ giữa nhiều project và nhiều lần build trên cùng máy. Nó có thể chứa version cũ, publication từ nhánh khác hoặc file được cài thủ công. Một consumer có thể resolve thành công từ artifact cũ và tạo ra kết quả sai lệch.

Repository staging riêng có lợi thế:

- Đường dẫn và nội dung được kiểm soát cho đúng lần thử.
- Không cần dọn toàn bộ Maven local repository.
- Có thể giới hạn module được resolve từ staging.
- Dễ đóng gói và chuyển sang CI job khác.
- Tránh nhầm lẫn với artifact do project khác publish cùng tọa độ.

Nếu vẫn dùng mavenLocal, hãy dùng version thử nghiệm riêng, kiểm tra chính xác file đã cài và bảo đảm consumer không vô tình lấy artifact từ repository khác.

## 5. Cấu hình producer để publish vào staging repository

Giả sử producer là một Java library:

~~~groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.example.orders'
version = '1.4.0-rc.1'

java {
    withSourcesJar()
    withJavadocJar()
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
            groupId = 'com.example.orders'
            artifactId = 'orders-client'
            version = project.version.toString()
        }
    }

    repositories {
        maven {
            name = 'staging'
            url = uri(layout.buildDirectory.dir('staging-repository'))
        }
    }
}
~~~

Ví dụ dùng Groovy DSL. Với Kotlin DSL, cú pháp khai báo plugin, publication và property sẽ khác.

Các phần quan trọng:

- Java Library plugin cung cấp component Java với compile/runtime variants.
- Maven Publish plugin tạo publication từ component.
- Group, artifact và version xác định tọa độ module.
- Sources/Javadoc JAR được yêu cầu tạo để có thể đưa vào publication.
- Repository tên staging trỏ đến thư mục riêng của producer.

Khi publication tên mavenJava và repository tên staging, Gradle tạo task publish tương ứng, thường có tên:

~~~shell
./gradlew publishMavenJavaPublicationToStagingRepository
~~~

Có thể xem task được đăng ký bằng:

~~~shell
./gradlew tasks --all
~~~

Tên task thực tế phụ thuộc publication và repository name. Không nên đoán tên nếu project có nhiều publication.

### Dùng version thử nghiệm riêng

Ví dụ version:

~~~text
1.4.0-rc.1
~~~

Version này cho biết đây là release candidate. Có thể dùng version riêng cho mỗi build thử nghiệm nếu quy trình cần phân biệt nhiều candidate. Tránh ghi đè cùng tọa độ trên một repository release bất biến.

Một repository staging cục bộ có thể cho phép ghi đè file, nhưng điều đó không nên trở thành cách phát hành chính thức. Nếu thay đổi nội dung artifact, tăng version candidate hoặc tạo staging repository mới để bảo đảm kết quả có thể truy vết.

### Tọa độ phải nhất quán

Tọa độ được công bố phải khớp với dependency mà consumer khai báo:

~~~text
groupId:    com.example.orders
artifactId: orders-client
version:    1.4.0-rc.1
~~~

Consumer sẽ dùng:

~~~groovy
dependencies {
    implementation 'com.example.orders:orders-client:1.4.0-rc.1'
}
~~~

Nếu group/artifact/version trong publication khác một phần, consumer sẽ không tìm thấy module theo tọa độ mong muốn. Hãy kiểm tra POM và cấu trúc repository thay vì chỉ nhìn project name hoặc tên file JAR.

## 6. Tạo consumer project thực sự độc lập

Consumer nên là một Gradle build riêng, có settings và build script riêng. Ví dụ:

~~~text
consumer-smoke/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        com/example/consumer/
          Main.java
    test/
      java/
        com/example/consumer/
          OrdersClientSmokeTest.java
~~~

settings.gradle:

~~~groovy
rootProject.name = 'orders-client-consumer-smoke'
~~~

Consumer không khai báo include producer, không dùng project(':orders-client') và không includeBuild producer.

Build script consumer:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    exclusiveContent {
        forRepository {
            maven {
                name = 'staging'
                url = uri('../orders-client/build/staging-repository')
            }
        }
        filter {
            includeModule('com.example.orders', 'orders-client')
        }
    }

    mavenCentral()
}

dependencies {
    implementation 'com.example.orders:orders-client:1.4.0-rc.1'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.0'
}

application {
    mainClass = 'com.example.consumer.Main'
}

test {
    useJUnitPlatform()
}
~~~

Đường dẫn repository là ví dụ theo cấu trúc workspace ở trên. Cần điều chỉnh theo vị trí thực tế của hai build.

### Vì sao dùng exclusiveContent?

Cấu hình này yêu cầu module orders-client được lấy từ repository staging đã chỉ định. Các dependency khác có thể được resolve từ Maven Central.

Điều đó giúp tránh trường hợp consumer tìm thấy cùng tọa độ ở một repository khác và vô tình kiểm tra nhầm artifact. Nếu Gradle version của project không hỗ trợ cấu hình này, có thể dùng repository content filter hoặc một repository test riêng với chính sách tương đương.

Nếu library có transitive dependency riêng nằm trong repository nội bộ, hãy cấu hình thêm repository phù hợp cho những module đó. Không giới hạn staging chỉ cho module chính nếu các dependency cần kiểm chứng cũng được publish vào cùng staging repository.

### Consumer cần khai báo đúng dependency công khai

Consumer chỉ khai báo tọa độ của library. Nó không cần biết:

- Source project nằm ở đâu.
- Task nào tạo JAR.
- Thư mục build của producer.
- Tên class nội bộ dùng để đóng gói.
- Publication được tạo từ task nào.

Đây chính là góc nhìn cần kiểm chứng trước phát hành.

## 7. Viết smoke test dùng public API

Consumer cần import và sử dụng API công khai như một người dùng thực tế.

Ví dụ source consumer:

~~~java
package com.example.consumer;

import com.example.orders.api.GreetingService;

public class Main {
    public static void main(String[] args) {
        GreetingService service = new GreetingService();
        System.out.println(service.greet("Gradle consumer"));
    }
}
~~~

Ví dụ JUnit test:

~~~java
package com.example.consumer;

import com.example.orders.api.GreetingService;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OrdersClientSmokeTest {
    @Test
    void publishedLibraryCanBeUsed() {
        GreetingService service = new GreetingService();

        assertEquals(
            "Hello, Gradle consumer",
            service.greet("Gradle consumer")
        );
    }
}
~~~

Tên class và method ở đây là minh họa; thay bằng API thực tế của thư viện.

Test này chứng minh một số điều:

- Consumer resolve được tọa độ publication.
- Compiler tìm thấy public API trong artifact.
- Consumer compile được với classpath đã resolve.
- Test runtime có thể nạp và sử dụng class.
- Hành vi cơ bản của API hoạt động khi dùng artifact đã publish.

Smoke test nên kiểm tra những điểm đại diện cho contract công khai. Không cần sao chép toàn bộ unit test nội bộ của producer sang consumer.

### Chạy compile, test và application

Từ thư mục consumer:

~~~shell
./gradlew clean test
./gradlew run
~~~

Lệnh đầu compile main/test source và chạy smoke test. Lệnh thứ hai chạy application sample nếu đã cấu hình application plugin.

Nếu consumer chỉ là project test không có main class, có thể bỏ application plugin và dùng task test hoặc một task nhỏ để kiểm tra runtime.

## 8. Kiểm tra transitive dependencies

Một publication có thể chứa JAR đúng nhưng thiếu dependency cần thiết. Vấn đề thường chỉ xuất hiện khi consumer gọi API hoặc chạy code thực tế.

Ví dụ library công khai một method trả về kiểu từ dependency khác:

~~~java
package com.example.orders.api;

import com.example.money.Money;

public interface OrderPrice {
    Money total();
}
~~~

Consumer phải có khả năng biên dịch với kiểu Money nếu kiểu đó xuất hiện trong public API. Với Java Library plugin, producer thường cần khai báo dependency đó bằng configuration api:

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    api 'com.example.money:money-model:2.0'
}
~~~

Nếu producer khai báo dependency là implementation nhưng public API cần kiểu của dependency đó, consumer có thể gặp lỗi compile hoặc không có dependency trên compile API như mong đợi.

### api và implementation có ý nghĩa trong publication

| Producer configuration | Ý nghĩa với consumer |
|---|---|
| api | Dependency thuộc compile API được công bố cho consumer theo Java Library model |
| implementation | Dependency phục vụ implementation/runtime; không được phơi bày như compile API dependency |
| runtimeOnly | Dependency chỉ cần ở runtime |
| compileOnly | Dependency cần ở compile của producer nhưng không được đưa vào runtime theo cách thông thường |
| annotationProcessor | Dependency phục vụ annotation processing |

POM và Gradle Module Metadata biểu diễn dependency theo cách khác nhau. Gradle consumer có thể nhận thêm thông tin variant từ Gradle Module Metadata; Maven consumer chủ yếu dựa vào POM scopes. Vì vậy, cần kiểm tra đúng định dạng mà người dùng mục tiêu sẽ tiêu thụ.

### Kiểm tra dependency graph của consumer

Chạy:

~~~shell
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
~~~

Nếu một dependency công khai bị thiếu ở compileClasspath hoặc dependency runtime không có ở runtimeClasspath, kiểm tra configuration producer và publication metadata.

Có thể xem chi tiết một dependency:

~~~shell
./gradlew dependencyInsight --dependency money-model --configuration compileClasspath
~~~

Lệnh này giúp xác định dependency đến từ đâu, version nào được chọn và vì sao.

### Không chỉ kiểm tra resolve thành công

Một dependency graph resolve được chưa chứng minh mọi API cần thiết đều dùng được. Hãy compile source consumer có sử dụng public types và chạy test thực tế. Việc đó mới kiểm tra được cả metadata lẫn binary.

## 9. Kiểm tra POM và Gradle Module Metadata

Gradle publication thường có thể tạo cả POM và Gradle Module Metadata.

**POM** là metadata Maven XML, được Maven và nhiều công cụ khác sử dụng. Nó mô tả tọa độ module, packaging, dependency và các scope Maven.

**Gradle Module Metadata** là metadata riêng của Gradle, mô tả variants, attributes, capabilities và dependency theo mô hình phong phú hơn POM.

Ví dụ đường dẫn:

~~~text
com/example/orders/orders-client/1.4.0-rc.1/
  orders-client-1.4.0-rc.1.pom
  orders-client-1.4.0-rc.1.module
~~~

### Vì sao cần kiểm tra cả hai?

Gradle consumer có thể chọn Gradle Module Metadata nếu metadata này được publish và repository cung cấp. Maven consumer không sử dụng file .module theo cách Gradle sử dụng; nó dựa vào POM.

Một publication có thể hoạt động với Gradle consumer nhưng có vấn đề với Maven consumer nếu POM không thể hiện đúng dependency/scope hoặc metadata tùy chỉnh chỉ có trong Gradle Module Metadata.

| Consumer | Metadata thường dùng |
|---|---|
| Gradle | Gradle Module Metadata nếu có và được chọn; có thể dùng POM |
| Maven | POM |
| Công cụ khác hỗ trợ Maven repository | Thường dựa vào POM và artifact |
| Consumer cần variant đặc thù Gradle | Gradle Module Metadata có thể quan trọng |

### Kiểm tra nội dung POM

Mở file POM trong staging repository và xem:

- groupId.
- artifactId.
- version.
- packaging.
- dependencies.
- dependency scopes.
- exclusions nếu có.
- dependency management hoặc BOM liên quan.
- thông tin license, developers và SCM nếu publication yêu cầu.

Không chỉ kiểm tra POM có tồn tại. Hãy đối chiếu dependency và scope với API/runtime contract.

### Kiểm tra Gradle Module Metadata

File .module có thể chứa nhiều variant. Xem:

- Variant API/compile.
- Variant runtime.
- Attributes như Usage, Category, LibraryElements và target JVM.
- Dependency và dependency constraints.
- Artifact file và checksum metadata.
- Capability nếu publication có dùng.

Nếu consumer gặp lỗi no matching variant, hãy so sánh attributes consumer yêu cầu với variants producer công bố. Đừng sửa bằng cách thêm file JAR trực tiếp vì cách đó bỏ qua contract metadata đang cần kiểm chứng.

## 10. Kiểm thử bằng Maven consumer khi cần hỗ trợ Maven

Nếu library công bố cho cả người dùng Gradle và Maven, một Gradle consumer độc lập chưa đủ để kiểm tra POM behavior.

Có thể tạo một Maven project nhỏ:

~~~text
maven-consumer/
  pom.xml
  src/main/java/
    com/example/consumer/Main.java
~~~

pom.xml minh họa:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.consumer</groupId>
    <artifactId>orders-client-smoke</artifactId>
    <version>1.0.0</version>

    <repositories>
        <repository>
            <id>staging</id>
            <url>file:///path/to/staging-repository</url>
        </repository>
    </repositories>

    <dependencies>
        <dependency>
            <groupId>com.example.orders</groupId>
            <artifactId>orders-client</artifactId>
            <version>1.4.0-rc.1</version>
        </dependency>
    </dependencies>
</project>
~~~

Đường dẫn file repository phải được thay bằng đường dẫn hợp lệ trên máy hoặc CI runner. Với repository từ xa, dùng URL và credential theo chính sách tương ứng.

Chạy:

~~~shell
mvn clean test
~~~

Maven consumer kiểm tra POM và dependency scopes theo cách Maven thực sự resolve. Nếu Maven là một consumer được hỗ trợ, đây là kiểm chứng có giá trị.

### Trường hợp không cần Maven consumer

Nếu sản phẩm chỉ cam kết hỗ trợ Gradle, consumer Gradle độc lập có thể là bước chính. Tuy nhiên, POM vẫn có thể được dùng bởi công cụ khác hoặc repository. Cần công bố rõ hệ sinh thái consumer được hỗ trợ và kiểm tra metadata tương ứng.

## 11. Kiểm tra nội dung JAR đã publish

Một JAR có thể tồn tại nhưng không chứa class hoặc resource mà API cần.

Dùng công cụ JDK:

~~~shell
jar --list --file orders-client-1.4.0-rc.1.jar
~~~

Hoặc:

~~~shell
jar tf orders-client-1.4.0-rc.1.jar
~~~

Kiểm tra:

- Public API class có trong JAR không.
- Package path có đúng không.
- Resource cần thiết có được đóng gói không.
- File service descriptor có được đưa vào không.
- Module descriptor có trong JAR nếu sản phẩm dùng JPMS không.
- Không có file nội bộ hoặc secret không nên phát hành.
- Class file target có phù hợp với JDK được hỗ trợ không.

### Kiểm tra module descriptor nếu dùng JPMS

Nếu library là explicit named module:

~~~shell
jar --describe-module --file orders-client-1.4.0-rc.1.jar
~~~

Kết quả cần phù hợp với tên module và các directive dự kiến. Consumer named module có thể khai báo:

~~~java
module com.example.consumer {
    requires com.example.orders.client;
}
~~~

Tên module trong ví dụ phải được thay bằng module name thực tế được khai báo trong module-info.java hoặc suy ra theo quy tắc automatic module.

Một consumer chạy trên classpath không kiểm tra được mọi quy tắc readability/exports của JPMS. Nếu library cam kết hỗ trợ named modules, hãy có một consumer modular riêng để compile và chạy trên module path.

### Kiểm tra classifier và file đính kèm

Nếu publication có sources JAR, Javadoc JAR hoặc artifact classifier khác, xác nhận chúng được tạo và upload đúng. Một số repository có thể nhận main JAR nhưng thiếu artifact phụ do cấu hình publication.

Không giả định rằng việc main JAR resolve được đồng nghĩa tất cả classifier đã được publish.

## 12. Kiểm tra variant và target JVM

Một library có thể công bố metadata cho target JVM. Consumer yêu cầu target khác có thể nhận hoặc từ chối variant tùy attributes và compatibility rules.

Ví dụ producer dùng Java toolchain:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Nếu library được biên dịch cho Java 17, consumer cần có runtime tương thích hoặc cao hơn theo bytecode compatibility. Consumer dùng JDK 11 không thể chạy class file Java 17.

Cần kiểm tra:

- JDK dùng để chạy Gradle.
- Toolchain dùng để compile library.
- Target bytecode/compiler release.
- Target JVM attribute trong publication.
- JDK của consumer và runtime mục tiêu.
- Dependency transitive có yêu cầu Java version cao hơn không.

Không chỉ nhìn java -version trên máy producer. Toolchain có thể chọn JDK khác JVM chạy Gradle.

### Kiểm thử ma trận phiên bản

Nếu library hỗ trợ nhiều phiên bản Java hoặc Gradle, nên kiểm tra consumer ở các môi trường đại diện:

| Consumer environment | Mục tiêu |
|---|---|
| JDK thấp nhất được hỗ trợ | Xác nhận bytecode và API tương thích |
| JDK hiện tại của CI | Kiểm tra build chính |
| Gradle version tối thiểu được hỗ trợ | Kiểm tra metadata/plugin compatibility |
| Gradle version mới hơn | Phát hiện thay đổi resolution hoặc deprecation |
| Maven version được hỗ trợ | Kiểm tra POM interoperability nếu cần |

Không cần chạy mọi tổ hợp nếu ma trận quá lớn. Chọn tổ hợp dựa trên cam kết hỗ trợ của sản phẩm.

## 13. Kiểm tra dependency locking và tính tái lập

Consumer độc lập nên khai báo version rõ ràng cho artifact đang thử. Các dependency transitive có thể được quản lý bằng version catalog, constraints hoặc dependency locking theo chính sách.

Dependency locking giúp consumer tái lập kết quả resolution giữa các lần build khi repository có version mới hoặc metadata thay đổi.

Ví dụ bật locking cho configurations:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Sau khi resolve dependency, Gradle có thể tạo lock state bằng task hoặc tùy chọn phù hợp với Gradle version/project.

Trong smoke test trước phát hành, điều quan trọng là ghi nhận dependency graph thực tế và version đã được chọn. Nếu dùng dynamic version trong dependency của library, cần đánh giá kỹ tác động đến tính tái lập.

### Kiểm tra dependency constraints và platform

Nếu library công bố constraints hoặc dùng platform/BOM, consumer cần xác nhận các constraints được truyền đúng. Ví dụ:

- Dependency version được chọn có phù hợp không.
- Platform/BOM có được resolve không.
- Strict version constraint có gây conflict ngoài dự kiến không.
- Dependency bị exclude có làm thiếu class/runtime component không.
- Optional dependency có được tài liệu hóa đúng không.

Gradle Module Metadata có thể mang thông tin phong phú hơn POM. Nếu người dùng Maven cũng cần sử dụng platform hoặc constraints, hãy kiểm tra cách chúng được biểu diễn trong POM.

## 14. Kiểm thử Gradle plugin bằng một build consumer riêng

Nếu sản phẩm phát hành là Gradle plugin, consumer độc lập cần áp dụng plugin bằng plugin DSL theo cách người dùng sẽ dùng.

Ví dụ producer:

~~~groovy
plugins {
    id 'java-gradle-plugin'
    id 'maven-publish'
}

group = 'com.example.build'
version = '1.2.0-rc.1'

gradlePlugin {
    plugins {
        qualityPlugin {
            id = 'com.example.quality'
            implementationClass = 'com.example.quality.QualityPlugin'
        }
    }
}
~~~

Plugin project có thể tạo plugin marker artifact và implementation artifact. Publication phải bao gồm những thành phần cần thiết để plugin DSL resolve theo plugin ID/version.

Consumer settings:

~~~groovy
pluginManagement {
    repositories {
        maven {
            url = uri('../quality-plugin/build/staging-repository')
        }
        gradlePluginPortal()
    }
}
~~~

Consumer build:

~~~groovy
plugins {
    id 'com.example.quality' version '1.2.0-rc.1'
}
~~~

Consumer cần có một build script tối thiểu áp dụng plugin và gọi task hoặc cấu hình mà plugin công bố.

### Những gì cần kiểm tra

- Plugin ID có resolve qua plugin DSL không.
- Plugin marker artifact có được publish không.
- Marker có trỏ đến đúng implementation module/version không.
- Plugin implementation có được resolve không.
- Plugin có tương thích Gradle/JDK tối thiểu được hỗ trợ không.
- Plugin task/configuration hoạt động trong một build độc lập.
- Plugin không phụ thuộc vào file hoặc project path của repository phát triển.

Chỉ thêm implementation JAR vào buildscript classpath không kiểm tra được toàn bộ trải nghiệm plugin DSL. Hãy kiểm thử đúng cách sử dụng mà tài liệu hướng dẫn cho người dùng.

## 15. Tránh consumer vô tình dùng artifact cũ

Một trong những lỗi nguy hiểm nhất là smoke test pass nhưng đang resolve artifact cũ.

Các nguồn gây nhầm:

- Maven local repository có version cũ.
- Repository cache còn metadata/artifact từ lần trước.
- Consumer vẫn dùng project dependency hoặc composite build.
- Repository order cho phép lấy artifact cùng tọa độ từ một nguồn khác.
- Snapshot/changing module có metadata cache.
- Consumer build không được chạy từ thư mục độc lập như dự kiến.

### Các cách giảm nguy cơ

1. Dùng version candidate riêng cho publication cần thử.
2. Dùng staging repository mới hoặc xóa riêng repository staging của lần thử.
3. Dùng exclusiveContent để giới hạn tọa độ module về staging repository.
4. Xác nhận consumer build không include producer.
5. Kiểm tra resolved dependency report và đường dẫn artifact.
6. Dùng --refresh-dependencies khi cần xác nhận lại metadata; không dùng nó thay cho việc chọn đúng repository.
7. Không dựa vào file đã tồn tại trong consumer workspace.

Có thể kiểm tra dependency:

~~~shell
./gradlew dependencyInsight --dependency orders-client --configuration runtimeClasspath
~~~

Nếu cần kiểm tra file được resolve, có thể dùng Gradle dependency report hoặc một task chẩn đoán trong consumer để in artifact file. Trong quy trình phát hành, lưu log resolution để biết chính xác nguồn và version.

## 16. Repository order, content filter và exclusive content

Gradle repository được cấu hình theo thứ tự và content rules. Nếu cùng tọa độ tồn tại ở nhiều repository, hành vi resolution có thể phụ thuộc repository metadata đã chọn và cache.

Đối với kiểm chứng publication, nên đảm bảo module đang thử chỉ có thể đến từ staging repository.

Ví dụ:

~~~groovy
repositories {
    exclusiveContent {
        forRepository {
            maven {
                name = 'staging'
                url = uri('../orders-client/build/staging-repository')
            }
        }
        filter {
            includeModule('com.example.orders', 'orders-client')
        }
    }

    mavenCentral()
}
~~~

Điều này giữ module chính ở staging repository và vẫn cho phép dependency khác lấy từ Maven Central.

Nếu publication có nhiều module cùng được tạo trong staging, thêm từng module vào filter hoặc dùng một repository scope phù hợp. Đừng giới hạn repository quá chặt đến mức transitive dependency nội bộ không thể resolve.

### Kiểm tra repository được cấu hình ở đúng scope

- Dependency consumer: repositories của consumer build hoặc dependencyResolutionManagement.
- Plugin DSL: pluginManagement.repositories trong settings.
- Legacy buildscript dependency: buildscript.repositories.
- Repository phát hành: publishing.repositories của producer.

Repository dùng để publish không tự động trở thành repository dùng để resolve dependency. Producer và consumer là hai cấu hình độc lập.

## 17. Kiểm tra bằng CI job độc lập

Consumer độc lập có thể được đưa vào pipeline như một job sau khi producer publish vào staging.

~~~text
Build producer
     |
     v
Publish to staging
     |
     v
Upload staging repository/artifact bundle
     |
     v
Independent consumer job
     |
     +--> Download staging bundle
     |
     +--> Configure staging repository
     |
     +--> Resolve published coordinates
     |
     +--> Compile and test
     |
     v
Release gate
~~~

Nếu producer và consumer chạy trên cùng một runner trong cùng job, consumer có thể đọc file repository qua path cục bộ. Nếu chúng chạy trên hai runner khác nhau, file system của producer không tự xuất hiện ở consumer. Phải truyền staging repository hoặc publication bundle qua CI artifact storage, shared repository hoặc một repository staging từ xa.

### Consumer job không nên checkout producer source để thay dependency

Consumer job có thể checkout source của consumer smoke project. Nó không cần checkout producer source để compile thư viện từ source. Nếu pipeline checkout producer và thêm nó vào composite build, nó sẽ kiểm tra source integration thay vì published artifact.

Một consumer job có thể dùng commit riêng hoặc source fixture được quản lý độc lập. Điều quan trọng là dependency library phải resolve theo tọa độ đã publish.

### Giữ thông tin build giữa các jobs

Nên lưu metadata của publication cùng artifact:

- Group/artifact/version.
- Commit SHA của producer.
- Pipeline run ID.
- Repository/staging identifier.
- Checksum.
- Gradle/JDK version.
- Publication variant hoặc classifier nếu có.

Consumer job có thể dùng metadata này để xác nhận đúng package candidate đang được thử.

## 18. Kiểm tra package đúng với binary đã build

Khi publish, cần xác nhận artifact trong repository là output của đúng build candidate.

Có thể so sánh checksum của JAR trong thư mục output producer với JAR đã publish:

~~~shell
sha256sum orders-client-1.4.0-rc.1.jar
~~~

Trên PowerShell:

~~~powershell
Get-FileHash .\orders-client-1.4.0-rc.1.jar -Algorithm SHA256
~~~

Nếu publication repository chứa artifact đã ký hoặc được transform, checksum của file có thể khác theo đúng quy trình. Khi đó cần xác định artifact nào là nguồn và kiểm tra signature/metadata tương ứng.

Checksum giúp phát hiện file bị thay đổi trong quá trình copy/upload/download. Nó không chứng minh người tạo artifact là ai nếu nguồn checksum không đáng tin cậy.

### Kiểm tra chữ ký

Nếu publication yêu cầu signing, consumer hoặc release verification step cần kiểm tra chữ ký theo public key/trust policy đã công bố.

Không chỉ xác nhận có file .asc. Cần kiểm tra:

- Chữ ký tương ứng với đúng artifact và metadata.
- Key fingerprint đúng.
- Key còn được tin cậy theo chính sách.
- File không bị thay đổi sau khi ký.
- Signature metadata được upload cùng publication.

Cách ký và kiểm tra phụ thuộc repository và quy trình phát hành.

## 19. Kiểm tra sources, Javadoc và tài liệu người dùng

Một library phát hành thường cung cấp thêm source/Javadoc artifacts để IDE và người dùng tra cứu API.

Với Java plugin:

~~~groovy
java {
    withSourcesJar()
    withJavadocJar()
}
~~~

Khi publication được tạo từ component Java, các artifact phụ có thể được gắn vào publication theo cấu hình plugin.

Kiểm tra:

- Sources JAR có class tương ứng với binary không.
- Javadoc JAR có được tạo thành công không.
- Public API có tài liệu đủ dùng không.
- Class/method deprecated có thông tin phù hợp không.
- Ví dụ trong README dùng đúng tọa độ và API của version candidate.
- Tài liệu không tham chiếu project path hoặc task nội bộ mà consumer không có.

Sources/Javadoc không thay thế smoke test. Chúng là artifact phụ giúp người dùng hiểu và tích hợp package.

## 20. Kiểm tra backward compatibility trước release

Một consumer mới compile được với version candidate không tự chứng minh library tương thích ngược với version trước.

Nếu library có cam kết semantic versioning, cần kiểm tra:

- Public class/interface đã bị xóa hoặc đổi tên chưa.
- Method signature, visibility và generic type có thay đổi không.
- Constructor hoặc overload có bị thay đổi không.
- Exception behavior và nullability contract có thay đổi không.
- Dependency public API có thay đổi không.
- Module name, exported package và service contract có thay đổi không.
- Runtime behavior có phá vỡ consumer hiện có không.

Có thể duy trì một consumer fixture đại diện cho cách sử dụng version trước, sau đó nâng dependency sang candidate và chạy compile/test. Điều này giúp phát hiện một số breaking change ở source/binary contract.

Với library quan trọng, có thể dùng công cụ API compatibility chuyên dụng và lưu baseline. Consumer smoke test là một lớp xác nhận thực tế, không thay thế phân tích API compatibility đầy đủ.

## 21. Version candidate, snapshot và release bất biến

Trước release, thường có nhiều trạng thái version:

- Snapshot/development version.
- Release candidate.
- Final release.
- Hotfix hoặc patch release.

Version snapshot thường có thể thay đổi theo quy ước repository. Release candidate nên được định danh rõ để người tiêu thụ biết đó chưa phải final. Final release thường cần tọa độ bất biến: cùng tọa độ không được ghi đè bằng nội dung khác.

Ví dụ:

~~~text
1.4.0-SNAPSHOT
1.4.0-rc.1
1.4.0-rc.2
1.4.0
~~~

Tên và thứ tự version phải tuân theo chính sách dự án và version scheme được công bố.

### Không sửa nội dung dưới cùng tọa độ release

Nếu artifact đã được publish dưới version 1.4.0 và consumer đã dùng, thay file tại cùng tọa độ có thể khiến các máy resolve ra nội dung khác nhau tùy cache và thời điểm. Điều này phá tính tái lập và gây khó truy vết.

Nếu cần sửa, tạo version mới hoặc tuân theo quy trình repository cho phép thay đổi snapshot/candidate. Không ghi đè release final.

## 22. Những lỗi thường gặp trong consumer verification

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Could not find module | Sai tọa độ hoặc repository | So sánh dependency với POM và staging path |
| Consumer resolve được version cũ | mavenLocal/cache/repository khác | Dùng version candidate mới và giới hạn nguồn |
| Compile không tìm thấy public class | JAR thiếu class hoặc package không được công bố | Kiểm tra JAR contents và publication component |
| Thiếu kiểu từ dependency trong API | Producer dùng implementation thay vì api | Kiểm tra API dependency và metadata |
| Runtime NoClassDefFoundError | Runtime dependency thiếu hoặc scope sai | Xem runtimeClasspath và POM/module metadata |
| Gradle consumer chạy, Maven consumer lỗi | POM không biểu diễn dependency như mong đợi | Kiểm tra Maven scopes và POM |
| No matching variant | Attributes/target JVM không tương thích | Xem consumer attributes và published variants |
| Plugin DSL không tìm thấy plugin | Marker artifact hoặc plugin repository sai | Kiểm tra plugin marker publication và pluginManagement |
| JPMS module not found | Module name hoặc module path sai | Kiểm tra module-info và JAR descriptor |
| Consumer chỉ chạy trong producer repo | Vẫn dùng project dependency hoặc included build | Tách build và resolve tọa độ từ repository |
| Sources/Javadoc không tải được | Artifact phụ chưa publish | Kiểm tra withSourcesJar/withJavadocJar và publication |
| Test consumer dùng sai binary | Artifact cũ hoặc khác run được tải | Kiểm tra run ID, commit và checksum |
| Snapshot không cập nhật | Metadata cache hoặc snapshot policy | Kiểm tra repository snapshot behavior và refresh policy |

## 23. Quy trình kiểm chứng trước phát hành

Một quy trình thực tế có thể đi theo thứ tự sau:

1. **Xác định contract**: tọa độ, API công khai, runtime requirements, Gradle/Maven/Java versions được hỗ trợ.
2. **Build producer**: tạo artifact và chạy test nội bộ theo pipeline.
3. **Publish candidate**: publish vào staging repository riêng, dùng version candidate.
4. **Kiểm tra file publication**: xác nhận JAR, POM, Gradle Module Metadata và classifier cần thiết.
5. **Tạo consumer độc lập**: dùng build riêng, không project dependency và không composite include producer.
6. **Giới hạn nguồn artifact**: cấu hình consumer resolve module candidate từ staging repository.
7. **Compile public API**: viết code dùng các class/method được tài liệu công bố.
8. **Kiểm tra dependency graph**: xác nhận compile/runtime transitive dependency và version.
9. **Chạy test/runtime**: kiểm tra hành vi cơ bản và các use case đại diện.
10. **Kiểm tra metadata khác hệ sinh thái**: chạy Maven consumer hoặc modular consumer nếu sản phẩm cam kết hỗ trợ.
11. **Kiểm tra identity/integrity**: xác nhận version, commit, run ID, checksum và signature nếu có.
12. **Ghi kết quả candidate**: lưu log, metadata và kết luận để release gate sử dụng.

Không phải mọi library đều cần Maven, JPMS và mọi JDK matrix. Chọn consumer fixtures theo cam kết hỗ trợ thực tế, nhưng luôn có ít nhất một consumer độc lập cho artifact được phát hành.

## 24. Ví dụ lệnh từ producer đến consumer

Giả sử producer đã cấu hình publication tên mavenJava và repository staging:

~~~shell
cd orders-client
./gradlew clean test publishMavenJavaPublicationToStagingRepository
~~~

Sau khi publish thành công, chuyển sang consumer:

~~~shell
cd ../consumer-smoke
./gradlew --refresh-dependencies clean test
./gradlew run
~~~

Lệnh consumer resolve dependency theo tọa độ từ staging repository được cấu hình trong build script.

Có thể xem dependency graph:

~~~shell
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
~~~

Và kiểm tra một module cụ thể:

~~~shell
./gradlew dependencyInsight --dependency orders-client --configuration runtimeClasspath
~~~

Các lệnh trên là ví dụ cho shell kiểu Unix. Trên Windows PowerShell, có thể chạy Wrapper tương ứng và dùng Set-Location hoặc lệnh chuyển thư mục phù hợp.

Nếu consumer job chạy ở runner khác, cần upload staging repository hoặc artifact bundle từ producer job rồi download vào vị trí mà consumer build cấu hình. Không giả định đường dẫn local của runner producer tồn tại ở runner consumer.

## 25. Tổ chức consumer fixture có thể tái sử dụng

Đối với library được phát hành thường xuyên, có thể giữ một hoặc nhiều consumer fixture trong repository riêng hoặc thư mục verification độc lập.

Ví dụ:

~~~text
verification/
  gradle-consumer/
    settings.gradle
    build.gradle
    src/
  maven-consumer/
    pom.xml
    src/
  modular-consumer/
    settings.gradle
    build.gradle
    src/
~~~

Các fixture có thể đại diện cho:

- Consumer Gradle dùng API chính.
- Consumer Maven nếu Maven được hỗ trợ.
- Consumer JPMS nếu module support là một phần của contract.
- Consumer chạy trên JDK thấp nhất được hỗ trợ.
- Consumer sử dụng plugin bằng plugin DSL nếu sản phẩm là Gradle plugin.

### Fixture phải tiêu thụ publication thực tế

Khi chạy fixture, pipeline cần publish candidate trước và truyền repository/coordinate của candidate vào consumer. Không nên để fixture tự include producer hoặc compile source producer trực tiếp.

Có thể parameterize version/repository bằng Gradle property:

~~~groovy
def candidateVersion = providers.gradleProperty('candidateVersion')
    .getOrElse('1.4.0-rc.1')

dependencies {
    implementation "com.example.orders:orders-client:" + candidateVersion
}
~~~

Nếu cần, repository path cũng có thể được cấu hình bằng property để CI dùng file repository đã download. Giá trị property phải được truyền rõ trong pipeline và log để truy vết.

## 26. Release gate: khi nào candidate sẵn sàng?

Consumer verification là một bằng chứng trong quyết định release. Có thể đặt các điều kiện:

| Điều kiện | Bằng chứng |
|---|---|
| Producer build thành công | Build log/task result |
| Unit test pass | Test report |
| Publication đầy đủ | File listing của staging repository |
| Consumer resolve được artifact | Dependency resolution log |
| Public API compile được | Consumer compile/test result |
| Runtime dependency đầy đủ | Consumer runtime test |
| Metadata đúng | POM và .module inspection |
| Compatibility phù hợp | JDK/Gradle/Maven consumer matrix |
| Binary đúng candidate | Version, commit, run ID, checksum |
| Integrity/trust đạt yêu cầu | Signature/provenance verification nếu có |

Nếu consumer verification thất bại, cần phân loại nguyên nhân: lỗi artifact, metadata, repository, môi trường consumer hoặc fixture. Không nên chuyển candidate thành release chỉ vì producer unit test pass.

Khi tất cả điều kiện bắt buộc đạt, có thể promote cùng artifact đã kiểm chứng sang repository release. Nếu quy trình yêu cầu rebuild để ký hoặc tạo metadata final, phải xác định rõ binary cuối cùng có còn đúng với binary đã kiểm thử hay không và lặp lại bước xác minh phù hợp.

## 27. Những nhầm lẫn thường gặp

| Dễ nhầm | Cách hiểu đúng |
|---|---|
| Project dependency pass nghĩa publication đúng | Project dependency dùng project component, chưa kiểm tra đầy đủ repository metadata |
| Consumer độc lập chỉ cần import class | Cần resolve theo tọa độ, compile, kiểm tra dependency và runtime |
| JAR tồn tại nghĩa package hoàn chỉnh | POM, .module, classifier và plugin marker có thể còn thiếu |
| Gradle consumer pass nghĩa Maven consumer pass | Maven dựa vào POM; Gradle có thể dùng Gradle Module Metadata |
| mavenLocal luôn là staging sạch | Nó là repository dùng chung, có thể chứa artifact cũ |
| Build producer thành công là đủ | Người dùng có thể gặp lỗi publication/metadata sau khi publish |
| Cache hit chứng minh artifact mới được publish | Cache có thể khôi phục output task; nó không xác nhận repository chứa candidate |
| Consumer fixture có thể include producer | Điều đó bỏ qua published dependency path |
| Resolve thành công nghĩa API tương thích | Cần compile source và chạy test sử dụng public API |
| Main JAR có mặt nghĩa mọi classifier có mặt | Sources/Javadoc/artifact phụ phải được publish riêng |
| Cùng version có thể ghi đè an toàn | Release tọa độ nên bất biến để bảo đảm tính tái lập |
| Upload staging repository qua CI không cần metadata | Consumer cần đúng tọa độ, version và repository layout |
| Smoke test thay thế toàn bộ QA | Nó bổ sung kiểm chứng publication, không thay unit/integration/API compatibility test |

## 28. Nguyên tắc kiểm chứng trước phát hành

Hãy kiểm tra package từ góc nhìn của người sẽ sử dụng nó. Producer chịu trách nhiệm tạo và publish artifact; consumer độc lập chỉ nhận tọa độ và repository, sau đó resolve, compile và chạy bằng public API.

Dùng repository staging riêng và version candidate để tránh nhầm artifact. Kiểm tra JAR cùng POM/Gradle Module Metadata, transitive dependencies, variants và runtime behavior. Nếu sản phẩm hỗ trợ Maven, JPMS hoặc Gradle plugin DSL, tạo consumer tương ứng để kiểm chứng đúng con đường tích hợp đó.

Khi candidate đạt release gate, giữ nguyên identity của artifact đã kiểm chứng và promote nó theo quy trình phát hành. Mục tiêu là xác nhận người dùng có thể tiêu thụ đúng package đã publish, không chỉ xác nhận source project của nhà phát triển có thể build thành công.

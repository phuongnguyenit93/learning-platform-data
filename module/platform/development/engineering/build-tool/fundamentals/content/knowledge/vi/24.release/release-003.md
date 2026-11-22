# Công bố phụ thuộc bắc cầu chính xác cho thư viện được phát hành

Khi phát hành một thư viện Java, artifact JAR chỉ chứa bytecode và resource. Để consumer sử dụng đúng thư viện, metadata được phát hành cùng JAR còn phải mô tả chính xác các dependency mà thư viện cần. Những dependency đó có thể tiếp tục đưa các module khác vào dependency graph của ứng dụng; chúng được gọi là **phụ thuộc bắc cầu** (transitive dependencies).

Nếu metadata công bố sai, consumer có thể thiếu class khi biên dịch, thiếu implementation khi chạy, nhận thêm thư viện nội bộ không cần thiết hoặc chọn phiên bản không tương thích. Vì vậy, người phát hành cần phân biệt dependency thuộc API công khai với dependency chỉ phục vụ implementation, khai báo đúng configuration trong Gradle và kiểm tra metadata thực tế mà consumer sẽ đọc.

Với thư viện dùng Gradle Java Library plugin, các configuration như **api**, **implementation**, **compileOnly**, **compileOnlyApi** và **runtimeOnly** thể hiện vai trò dependency ở từng classpath. Khi publish, Gradle có thể tạo Maven POM và Gradle Module Metadata. Hai định dạng này có khả năng biểu diễn khác nhau, vì vậy cần kiểm tra cả cách consumer Gradle lẫn consumer Maven nhìn thấy thư viện.

## 1. Dependency bắc cầu trong thư viện được phát hành

Giả sử một thư viện tên **order-client** sử dụng **json-core** và **http-transport**:

~~~text
Ứng dụng consumer
└── order-client
    ├── json-core
    └── http-transport
~~~

Ứng dụng chỉ khai báo order-client trực tiếp. Gradle hoặc Maven đọc metadata của order-client để biết các module mà thư viện này cần, sau đó đưa chúng vào dependency graph theo scope và quy tắc phân giải tương ứng.

Trong ví dụ:

- **order-client** là dependency trực tiếp của ứng dụng.
- **json-core** và **http-transport** là dependency bắc cầu đối với ứng dụng.
- Các dependency của json-core hoặc http-transport có thể tiếp tục tạo thêm các cạnh trong graph.

Một thư viện được publish đúng phải mô tả đủ dependency cần thiết để consumer biên dịch và chạy. Nó cũng cần tránh công bố những dependency nội bộ không cần thiết trên compile classpath của consumer.

### Vì sao metadata chính xác quan trọng?

Metadata sai có thể gây ra các tình huống:

- Consumer không biên dịch được vì kiểu xuất hiện trong public API không có trên compile classpath.
- Ứng dụng biên dịch thành công nhưng lỗi runtime vì thiếu implementation.
- Consumer bị kéo thêm thư viện test hoặc công cụ build không cần thiết.
- Dependency nội bộ bị công bố như API, làm tăng coupling.
- Hai dependency yêu cầu các phiên bản không tương thích và Gradle phải giải quyết conflict.
- Consumer dùng Maven và Gradle nhận graph khác nhau do hai định dạng metadata không biểu diễn giống nhau.

JAR có thể được tạo thành công dù metadata sai. Vì vậy, kiểm tra artifact cần bao gồm cả file JAR và publication metadata.

## 2. API công khai quyết định dependency nào cần được xuất ra

Khi thiết kế một thư viện, hãy xem các kiểu dependency có xuất hiện trong API mà consumer nhìn thấy hay không.

Ví dụ thư viện công khai lớp:

~~~java
package com.example.orders;

import com.example.json.JsonDocument;

public class OrderClient {
    public JsonDocument getOrder(String id) {
        // ...
        return null;
    }
}
~~~

Kiểu **JsonDocument** xuất hiện trong kiểu trả về public method. Consumer biên dịch mã gọi API này cần có JsonDocument trên compile classpath.

Nếu order-client khai báo json-core là dependency chỉ dùng nội bộ, consumer Gradle có thể không nhận json-core trên compile classpath. Khi consumer gọi hoặc xử lý kiểu JsonDocument, việc biên dịch có thể thất bại.

Ngược lại, nếu thư viện chỉ sử dụng json-core bên trong một implementation detail và public API không để lộ kiểu của nó, consumer thường không cần dependency đó trên compile classpath.

### Những vị trí thường làm dependency trở thành một phần API

Hãy xem dependency có xuất hiện trong:

- Kiểu tham số của public hoặc protected method.
- Kiểu trả về của public hoặc protected method.
- Kiểu generic trong public signature.
- Superclass hoặc interface mà public class kế thừa/triển khai.
- Kiểu field hoặc property được công khai qua API.
- Annotation hoặc kiểu dữ liệu mà consumer cần để biên dịch và sử dụng API.
- Public interface hoặc abstract class mà consumer phải implement.

Không phải mọi lần import một class trong source đều có nghĩa dependency phải là API dependency. Điều quan trọng là dependency có trở thành một phần của contract mà consumer cần nhìn thấy khi biên dịch hay không.

## 3. Dùng Java Library plugin để mô tả API và implementation

Gradle Java plugin cung cấp cấu hình Java cơ bản. Với thư viện được phát hành cho consumer, **Java Library plugin** bổ sung mô hình API/implementation rõ ràng hơn.

Kotlin DSL:

~~~kotlin
plugins {
    id("java-library")
}
~~~

Groovy DSL:

~~~groovy
plugins {
    id 'java-library'
}
~~~

Java Library plugin tạo các configuration để phân biệt dependency của thư viện với dependency được xuất cho consumer. Hai configuration quan trọng nhất là **api** và **implementation**.

### api

Dependency khai báo trong api là một phần của API công khai của thư viện. Nó được dùng khi biên dịch và chạy thư viện, đồng thời được xuất cho consumer trên compile và runtime classpath phù hợp.

Ví dụ:

~~~kotlin
dependencies {
    api("com.example:json-core:2.4.0")
}
~~~

Dùng api khi public signature của thư viện yêu cầu consumer nhìn thấy kiểu từ json-core.

### implementation

Dependency khai báo trong implementation được dùng để biên dịch và chạy chính thư viện. Consumer vẫn nhận dependency cần thiết ở runtime, nhưng dependency đó không tự động được đưa lên compile classpath của consumer chỉ vì thư viện sử dụng nó.

Ví dụ:

~~~kotlin
dependencies {
    implementation("com.example:http-transport:3.1.0")
}
~~~

Nếu http-transport chỉ được dùng bên trong OrderClient và không xuất hiện trong public API, implementation thường phù hợp.

### Sơ đồ classpath

~~~text
Thư viện order-client
    api: json-core
    implementation: http-transport

Consumer compile classpath:
    order-client
    json-core

Consumer runtime classpath:
    order-client
    json-core
    http-transport
~~~

Sơ đồ này thể hiện cách hiểu tổng quát với Java Library plugin. Các variant và metadata được publish sẽ quyết định consumer thực tế nhận dependency trên classpath nào.

## 4. Phân biệt các configuration dependency của Java Library plugin

Các configuration thường gặp:

| Configuration | Thư viện cần khi nào? | Consumer nhận ở compile? | Consumer nhận ở runtime? |
|---|---|---:|---:|
| **api** | Compile và runtime của thư viện; dependency thuộc API công khai | Có | Có |
| **implementation** | Compile và runtime của thư viện; dependency nội bộ | Không | Có |
| **compileOnly** | Chỉ cần để biên dịch thư viện | Không | Không |
| **compileOnlyApi** | Cần khi biên dịch thư viện và API consumer | Có trong Gradle variant phù hợp | Không |
| **runtimeOnly** | Chỉ cần khi chạy thư viện | Không | Có |
| **testImplementation** | Chỉ dùng để biên dịch test của thư viện | Không | Không |
| **testRuntimeOnly** | Chỉ dùng khi chạy test của thư viện | Không | Không |

Bảng này mô tả mục đích của các configuration và hành vi variant trong Gradle. Khi publish sang định dạng khác như Maven POM, một số semantics không thể biểu diễn chính xác như Gradle Module Metadata; cần kiểm tra metadata đã tạo.

### compileOnly

Dùng khi dependency cần cho compile của chính thư viện nhưng không phải dependency runtime mà thư viện muốn cung cấp cho consumer.

Ví dụ một API do container hoặc môi trường triển khai cung cấp:

~~~kotlin
dependencies {
    compileOnly("jakarta.servlet:jakarta.servlet-api:6.0.0")
}
~~~

Thư viện có thể biên dịch với Servlet API, nhưng ứng dụng chạy trong servlet container dự kiến nhận API đó từ môi trường. Dependency compileOnly không nên được coi là một thư viện runtime bắc cầu thông thường.

### compileOnlyApi

Dùng khi kiểu của dependency xuất hiện trong public API nên consumer cần dependency đó khi biên dịch, nhưng dependency được cung cấp bởi môi trường chạy hoặc không cần nằm trong runtime graph của thư viện.

~~~kotlin
dependencies {
    compileOnlyApi("jakarta.servlet:jakarta.servlet-api:6.0.0")
}
~~~

Gradle Module Metadata có thể biểu diễn rõ variant compile và runtime. Maven POM không có mô hình variant giống Gradle để thể hiện chính xác mọi trường hợp compile-only nhưng vẫn cần truyền cho compile classpath của consumer. Vì vậy, hãy kiểm tra POM được tạo và xác nhận cách consumer Maven cần khai báo API này; đừng giả định POM và Gradle Module Metadata luôn giữ cùng semantics.

### runtimeOnly

Dùng khi thư viện cần một implementation lúc chạy nhưng không cần implementation đó để biên dịch mã nguồn chính.

~~~kotlin
dependencies {
    runtimeOnly("org.postgresql:postgresql:42.7.3")
}
~~~

Ví dụ này phù hợp khi thư viện hoặc ứng dụng cần PostgreSQL driver được nạp lúc runtime. Nếu API công khai không sử dụng kiểu từ driver, consumer không cần driver trên compile classpath.

### testImplementation và testRuntimeOnly

Các dependency chỉ phục vụ test phải được khai báo trong configuration test tương ứng:

~~~kotlin
dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}
~~~

Dependency test không nên bị công bố như dependency runtime hoặc compile của thư viện. Consumer không cần kéo JUnit của chính thư viện chỉ vì thư viện dùng JUnit để kiểm thử.

## 5. Vì sao không nên dùng implementation cho mọi dependency?

Nếu dùng implementation cho tất cả dependency, consumer sẽ có compile classpath gọn hơn, nhưng có thể thiếu kiểu cần thiết để biên dịch với public API.

Ví dụ:

~~~kotlin
dependencies {
    implementation("com.example:json-core:2.4.0")
}
~~~

Trong khi public API có method:

~~~java
public JsonDocument getOrder(String id) {
    // ...
    return null;
}
~~~

Consumer Gradle có thể thấy OrderClient nhưng không có JsonDocument trên compile classpath. Khi consumer sử dụng method hoặc kiểu đó, compiler không resolve được kiểu.

Cách khai báo phù hợp hơn:

~~~kotlin
dependencies {
    api("com.example:json-core:2.4.0")
}
~~~

Một lỗi ngược lại cũng có thể xảy ra: dùng api cho mọi dependency khiến implementation detail bị lộ ra compile classpath của consumer. Điều này:

- Làm compile classpath lớn hơn.
- Tăng coupling giữa các project.
- Khiến consumer có thể vô tình phụ thuộc vào thư viện nội bộ.
- Làm thay đổi implementation gây ảnh hưởng rộng hơn.
- Làm public dependency graph khó quản lý.

Quyết định api hay implementation nên dựa trên public contract, không dựa vào việc dependency có quan trọng với thư viện hay không.

## 6. Ví dụ build.gradle.kts cho thư viện

Một thư viện order-client có thể cấu hình:

~~~kotlin
plugins {
    id("java-library")
}

group = "com.example"
version = "1.0.0"

repositories {
    mavenCentral()
}

dependencies {
    // Kiểu JsonDocument xuất hiện trong public API.
    api("com.example:json-core:2.4.0")

    // HTTP transport chỉ được dùng bên trong implementation.
    implementation("com.example:http-transport:3.1.0")

    // Driver chỉ cần khi chạy.
    runtimeOnly("org.postgresql:postgresql:42.7.3")

    // API servlet cần khi biên dịch nhưng do container cung cấp.
    compileOnlyApi("jakarta.servlet:jakarta.servlet-api:6.0.0")

    // Chỉ phục vụ kiểm thử của chính thư viện.
    testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Mô hình này phân chia dependency theo mục đích:

- json-core thuộc API công khai.
- http-transport là implementation detail.
- PostgreSQL driver chỉ cần lúc runtime.
- Servlet API cần cho compile của thư viện và compile consumer nếu public API dùng kiểu đó, nhưng runtime được môi trường cung cấp.
- JUnit chỉ dành cho test của thư viện.

Không phải dự án nào cũng cần đủ các configuration này. Chỉ khai báo những dependency thực sự được dùng và chọn configuration phù hợp với contract.

## 7. Outgoing variants: Gradle công bố API và runtime như thế nào?

Gradle không chỉ publish một file JAR. Với Java Library plugin, component Java cung cấp các **outgoing variants** để consumer chọn theo mục đích sử dụng.

Hai variant quan trọng:

- **apiElements**: variant dùng cho consumer compile classpath.
- **runtimeElements**: variant dùng cho consumer runtime classpath.

Có thể hình dung:

~~~text
                 java component
                       |
             +---------+---------+
             |                   |
         apiElements        runtimeElements
             |                   |
       API dependencies     Runtime dependencies
       compile usage        runtime usage
             |                   |
       Consumer compile     Consumer runtime
          classpath            classpath
~~~

Các variant có attributes như usage, category, library elements và thông tin tương thích khác. Khi consumer khai báo dependency đến thư viện, Gradle chọn variant phù hợp với configuration đang phân giải.

Ví dụ:

~~~kotlin
dependencies {
    implementation("com.example:order-client:1.0.0")
}
~~~

Khi Gradle phân giải compile classpath, nó chọn variant API phù hợp. Khi phân giải runtime classpath, nó chọn runtime variant.

Đây là một lý do quan trọng để publish từ component Java thay vì chỉ đính kèm một JAR thủ công: component mang theo thông tin dependency và variant cần thiết.

## 8. Maven POM biểu diễn dependency bắc cầu ra sao?

Maven POM dùng dependency scope để mô tả phạm vi dependency. Khi publish Java library sang Maven repository, Gradle tạo POM từ component publication.

Các scope phổ biến:

| Maven scope | Vai trò khái quát |
|---|---|
| **compile** | Dependency cần cho compile và runtime của consumer theo mô hình Maven |
| **runtime** | Dependency cần khi chạy, không cần cho compile chính |
| **provided** | Dependency cần trong môi trường biên dịch/kiểm thử nhưng môi trường triển khai dự kiến cung cấp |
| **test** | Chỉ phục vụ test của project khai báo |
| **system** | Dependency gắn với đường dẫn cục bộ; không phù hợp để publish thư viện thông thường |

Trong publication Java Library thông thường, Gradle ánh xạ các dependency API và implementation vào POM theo semantics Maven:

- Dependency **api** thường được công bố với scope compile.
- Dependency **implementation** thường được công bố với scope runtime.
- Dependency **runtimeOnly** được công bố với scope runtime.
- Dependency test không được công bố như dependency của consumer.
- Dependency compileOnly thường không được công bố như dependency runtime/compile thông thường.

Với **compileOnlyApi**, POM không thể biểu diễn hoàn toàn giống variant Gradle: consumer cần dependency ở compile nhưng không cần nó ở runtime. Hãy xem POM được sinh ra và kiểm thử bằng Maven consumer nếu thư viện cần hỗ trợ trường hợp này. Gradle Module Metadata giữ được nhiều semantics variant hơn.

### Ví dụ POM rút gọn

Giả sử thư viện khai báo api cho json-core và implementation cho http-transport. POM có thể chứa dạng:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>json-core</artifactId>
        <version>2.4.0</version>
        <scope>compile</scope>
    </dependency>

    <dependency>
        <groupId>com.example</groupId>
        <artifactId>http-transport</artifactId>
        <version>3.1.0</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Khi Maven consumer đọc POM, scope ảnh hưởng classpath mà dependency được đưa vào. Vì Maven và Gradle có quy tắc phân giải riêng, không nên suy ra mọi kết quả sẽ giống hệt nhau chỉ từ tên configuration.

## 9. Gradle Module Metadata và Maven POM khác nhau

Gradle có định dạng metadata riêng là **Gradle Module Metadata**. Tệp này thường có phần mở rộng .module và được publish cùng artifact khi dùng Gradle publishing phù hợp.

| Khả năng | Maven POM | Gradle Module Metadata |
|---|---|---|
| Định dạng | XML | JSON |
| Dependency scopes | Có | Được biểu diễn qua variant và dependency |
| API/runtime variants | Hạn chế, suy ra từ scope | Biểu diễn rõ ràng |
| Attributes | Không có mô hình variant tương đương | Có |
| Rich version constraints | Hạn chế | Hỗ trợ phong phú hơn |
| Capabilities | Không biểu diễn đầy đủ | Có |
| Compile-only API variant | Không thể hiện đầy đủ | Có thể biểu diễn |
| Dependency constraints/platform semantics | Một phần qua dependencyManagement/BOM | Hỗ trợ trực tiếp hơn |

Khi Gradle consumer đọc một module được publish từ Gradle, Gradle có thể dùng Gradle Module Metadata để chọn variant phù hợp. Maven consumer chỉ đọc POM và artifact theo mô hình Maven.

Vì vậy, một thư viện có thể hoạt động chính xác với Gradle consumer nhưng cần kiểm tra thêm với Maven consumer, đặc biệt khi sử dụng compileOnlyApi, rich version constraints, capabilities hoặc variant tùy chỉnh.

### Không nên chỉ kiểm tra POM

Nếu publication có cả POM và .module, hãy kiểm tra cả hai. POM giúp xác nhận khả năng tương thích với hệ sinh thái Maven; module metadata giúp xác nhận Gradle consumer nhận đúng variant và dependency.

Khi cần mô phỏng consumer chỉ đọc POM, có thể cấu hình repository trong một build kiểm thử:

~~~kotlin
repositories {
    maven {
        url = uri("../producer/build/repo")

        metadataSources {
            mavenPom()
        }
    }
}
~~~

Cấu hình này giới hạn nguồn metadata ở Maven POM trong repository được chỉ định. Nó hữu ích để kiểm tra fallback POM của Gradle, nhưng không thay thế việc chạy Maven consumer thật nếu thư viện cam kết hỗ trợ Maven.

## 10. Publish component thay vì chỉ publish JAR

Khi dùng Maven Publish plugin, nên publish component Java để metadata dependency và variant được đưa vào publication.

Ví dụ Kotlin DSL:

~~~kotlin
plugins {
    id("java-library")
    id("maven-publish")
}

group = "com.example"
version = "1.0.0"

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])
            artifactId = "order-client"
        }
    }

    repositories {
        maven {
            name = "localTest"
            url = uri(layout.buildDirectory.dir("test-repository"))
        }
    }
}
~~~

Trong ví dụ:

- Java Library plugin tạo component Java.
- Maven Publish plugin cung cấp publication và repository.
- from(components["java"]) lấy artifact và metadata từ component.
- artifactId đặt tên module được publish.
- Repository local trong build directory dùng để kiểm tra publication.

Có thể bổ sung thông tin POM:

~~~kotlin
publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])
            artifactId = "order-client"

            pom {
                name.set("Order Client")
                description.set("Client library for order services")
                url.set("https://example.com/order-client")

                licenses {
                    license {
                        name.set("The Apache License, Version 2.0")
                        url.set("https://www.apache.org/licenses/LICENSE-2.0.txt")
                    }
                }
            }
        }
    }
}
~~~

Thông tin name, description, license, developers và SCM giúp consumer hiểu artifact và nguồn gốc của nó. Metadata mô tả dependency vẫn được lấy từ component.

### Vì sao không chỉ dùng artifact(tasks.jar)?

Nếu publication chỉ đính kèm JAR thủ công mà không lấy component, Gradle có thể không có đủ thông tin outgoing variants và dependency để tạo metadata chính xác.

Ví dụ cách publish component:

~~~kotlin
from(components["java"])
~~~

thường phù hợp hơn cho Java library cần công bố dependency bắc cầu.

Nếu cần thêm artifact như sources JAR hoặc Javadoc JAR, có thể cấu hình các artifact đó cùng publication, nhưng vẫn giữ component Java làm nguồn metadata chính.

## 11. Cấu hình publication và kiểm tra repository cục bộ

Sau khi khai báo publication, Gradle tạo task publish tương ứng. Có thể publish vào repository kiểm thử cục bộ:

~~~bash
./gradlew publishMavenJavaPublicationToLocalTestRepository
~~~

Tên task phụ thuộc tên publication và repository. Có thể liệt kê task:

~~~bash
./gradlew tasks --all
~~~

Repository ví dụ sẽ có cấu trúc gần như:

~~~text
build/test-repository/
└── com/example/order-client/1.0.0/
    ├── order-client-1.0.0.jar
    ├── order-client-1.0.0.pom
    └── order-client-1.0.0.module
~~~

Tên file và sự hiện diện của metadata phụ thuộc cấu hình publication và Gradle version. Mục tiêu kiểm tra là xác nhận artifact, POM và Gradle Module Metadata được tạo ở đúng tọa độ.

Không nên kiểm tra chỉ file JAR. Hãy mở POM và module metadata để xem dependency nào được công bố, scope/variant nào chứa chúng và version nào được ghi.

## 12. Đọc POM và Gradle Module Metadata đã publish

POM là XML, có thể kiểm tra các phần:

- groupId, artifactId và version.
- packaging.
- dependencies.
- scope.
- exclusions.
- optional.
- dependencyManagement nếu có.

Ví dụ phần dependency:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>http-transport</artifactId>
    <version>3.1.0</version>
    <scope>runtime</scope>
</dependency>
~~~

Nếu http-transport là implementation detail, scope runtime thường là kết quả mong muốn trong POM.

Gradle Module Metadata chứa variants và dependency theo variant. Hãy kiểm tra:

- Variant API và runtime có được tạo không.
- Dependency nào nằm trong compile/API variant.
- Dependency nào chỉ có trong runtime variant.
- Attributes có phù hợp với consumer không.
- Constraints và capabilities có được giữ không.
- Artifact file nào gắn với từng variant.

Đừng sửa POM được sinh ra như một giải pháp đầu tiên nếu component model đang sai. Sửa dependency configuration hoặc publication model để metadata được sinh đúng. Nếu dùng POM XML customization, cần kiểm tra nguy cơ POM và .module không còn nhất quán.

## 13. Consumer Gradle kiểm tra dependency bắc cầu

Tạo một project consumer riêng, khai báo repository local và dependency đã publish:

~~~kotlin
repositories {
    maven {
        url = uri("../producer/build/test-repository")
    }
    mavenCentral()
}

dependencies {
    implementation("com.example:order-client:1.0.0")
}
~~~

Sau đó xem compile classpath:

~~~bash
./gradlew dependencies --configuration compileClasspath
~~~

Xem runtime classpath:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Nếu cần biết vì sao một module xuất hiện:

~~~bash
./gradlew dependencyInsight --dependency json-core --configuration compileClasspath
~~~

~~~bash
./gradlew dependencyInsight --dependency http-transport --configuration runtimeClasspath
~~~

Consumer test cần xác nhận:

- Kiểu được dùng trong public API có mặt trên compile classpath.
- Dependency implementation không bị lộ không cần thiết lên compile classpath.
- Dependency runtime có mặt khi chạy.
- Dependency test của producer không bị truyền sang consumer.
- Version được chọn đúng theo constraint và các dependency khác trong graph.

## 14. Consumer Maven kiểm tra POM

Nếu thư viện hỗ trợ Maven consumer, hãy tạo một Maven project kiểm thử độc lập và khai báo dependency:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>order-client</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

Cấu hình Maven repository local trỏ tới thư mục publication của producer hoặc cài artifact vào repository test phù hợp.

Kiểm tra dependency graph bằng:

~~~bash
mvn dependency:tree
~~~

Có thể kiểm tra compile và runtime classpath theo Maven lifecycle. Quan trọng là consumer thực sự biên dịch và chạy được với POM đã publish, không chỉ là POM trông có vẻ hợp lý.

Nếu consumer Maven cần một dependency compile-only API mà POM không thể truyền chính xác, tài liệu thư viện phải nêu dependency môi trường mà consumer cần cung cấp, hoặc thiết kế publication/API sao cho phù hợp hơn với cả hai hệ sinh thái.

## 15. Exclusions và optional dependencies

Một dependency có thể kéo theo module không cần thiết hoặc không tương thích. Gradle cho phép khai báo exclusion ở dependency:

~~~kotlin
dependencies {
    implementation("com.example:http-transport:3.1.0") {
        exclude(
            group = "org.example",
            module = "legacy-adapter"
        )
    }
}
~~~

Exclusion tác động đến nhánh dependency cụ thể. Nếu một dependency khác cũng yêu cầu legacy-adapter, module đó vẫn có thể xuất hiện qua đường khác.

Khi publish, exclusion là một phần metadata cần được kiểm tra. Không nên loại một dependency chỉ vì nó không được import trực tiếp trong source; hãy xác định liệu implementation có cần nó lúc runtime hay không.

### Optional dependency

Optional dependency là dependency phục vụ một tính năng bổ sung mà không phải mọi consumer đều cần. Maven POM có thuộc tính optional, nhưng semantics optional của Maven không giống hoàn toàn với api/implementation trong Gradle.

Nếu thư viện có feature tùy chọn, hãy cân nhắc:

- Tách feature thành module riêng.
- Dùng Java Library feature variants khi consumer Gradle cần chọn feature.
- Công bố dependency optional phù hợp cho Maven consumer.
- Tài liệu hóa dependency mà consumer phải thêm nếu sử dụng feature.
- Kiểm thử cả trường hợp feature được bật và không được bật.

Không nên đánh dấu một dependency là optional nếu thư viện cần nó cho chức năng cơ bản. Consumer sẽ gặp lỗi runtime khi sử dụng tính năng mà metadata không công bố dependency cần thiết.

## 16. Version constraints, platform và BOM

Một thư viện có thể phụ thuộc vào nhiều module cần được dùng cùng một dòng version. Chỉ khai báo version ở từng dependency đôi khi chưa đủ để giữ các module tương thích khi consumer có graph lớn hơn.

Gradle hỗ trợ dependency constraints và platform để mô tả quy tắc version.

Ví dụ constraint:

~~~kotlin
dependencies {
    constraints {
        api("com.example:json-core:2.4.0") {
            because("Public API is compiled against this version line")
        }
    }
}
~~~

Constraint không tự thêm module vào graph nếu không có dependency nào yêu cầu module đó. Nó ảnh hưởng đến version khi module xuất hiện trong graph.

Một BOM (Bill of Materials) có thể quản lý version tập trung. Consumer Gradle có thể dùng platform:

~~~kotlin
dependencies {
    implementation(platform("com.example:example-bom:1.0.0"))
    implementation("com.example:order-client")
}
~~~

Nếu thư viện cần các version constraints được truyền tới consumer vì chúng là một phần của contract dependency, hãy chọn configuration và publication model phù hợp. Gradle Module Metadata biểu diễn rich constraints và variants tốt hơn POM.

### Publish BOM bằng Java Platform plugin

Một project BOM có thể dùng Java Platform plugin:

~~~kotlin
plugins {
    id("java-platform")
    id("maven-publish")
}

group = "com.example"
version = "1.0.0"

dependencies {
    constraints {
        api("com.example:order-client:1.0.0")
        api("com.example:json-core:2.4.0")
        api("com.example:http-transport:3.1.0")
    }
}

publishing {
    publications {
        create<MavenPublication>("mavenBom") {
            from(components["javaPlatform"])
            artifactId = "example-bom"
        }
    }
}
~~~

BOM publication tạo POM có dependencyManagement để Maven consumer import BOM, đồng thời có thể có Gradle metadata cho Gradle consumer. BOM quản lý version; nó không có nghĩa tất cả module trong BOM tự động trở thành dependency của ứng dụng.

Không nên ép version một cách tùy tiện trong thư viện. Ưu tiên constraint hoặc platform phù hợp và kiểm tra ảnh hưởng đến consumer graph.

## 17. Tránh dynamic version trong metadata phát hành

Dynamic version như:

~~~kotlin
dependencies {
    implementation("com.example:json-core:2.+")
}
~~~

có thể khiến kết quả phân giải thay đổi theo thời gian khi repository có phiên bản mới. Điều này làm giảm khả năng tái lập build và khiến consumer nhận graph khác nhau giữa các lần resolve.

Với thư viện phát hành, nên dùng version cụ thể hoặc quy tắc constraint có chủ đích. Nếu dùng version range hay rich constraint, hãy kiểm tra cách chúng được biểu diễn trong Gradle Module Metadata và Maven POM.

Một publication tốt nên giúp consumer hiểu dependency nào được yêu cầu và version nào có thể được chọn. Tránh để metadata chứa version không ổn định mà không có lý do.

## 18. Exposed API và binary compatibility

Dependency công khai là một phần của contract thư viện. Khi thay đổi dependency API, có thể ảnh hưởng tới consumer ngay cả khi source của thư viện không đổi nhiều.

Ví dụ phiên bản mới của thư viện thay đổi kiểu trả về từ JsonDocument sang JsonTree. Consumer đã biên dịch với API cũ có thể không tương thích source hoặc binary tùy thay đổi.

Một số điều cần cân nhắc:

- Dependency xuất hiện trong public signature làm consumer phụ thuộc vào kiểu của dependency đó.
- Nâng version dependency có thể thay đổi method, interface hoặc annotation.
- Chuyển dependency từ api sang implementation có thể làm consumer không biên dịch nếu họ đang sử dụng kiểu đó.
- Chuyển từ implementation sang api làm compile classpath consumer rộng hơn và có thể vô tình mở rộng public contract.
- Thay đổi dependency runtime có thể gây lỗi khi service provider hoặc implementation không còn tương thích.

Khi phát hành version mới, xem xét API compatibility và dependency compatibility cùng nhau. Không chỉ so sánh source code của thư viện.

## 19. Không dựa vào dependency bắc cầu tình cờ

Một lỗi phổ biến là source của thư viện dùng một module mà build vẫn biên dịch được vì module đó tình cờ xuất hiện qua dependency khác.

Ví dụ:

~~~text
order-client
└── http-transport
    └── json-core
~~~

Nếu code order-client trực tiếp import JsonDocument nhưng chỉ khai báo http-transport, build có thể thành công vì json-core xuất hiện bắc cầu. Tuy nhiên, metadata của order-client không thể hiện trực tiếp dependency mà source của nó sử dụng.

Điều này làm build dễ vỡ khi http-transport thay đổi dependency hoặc loại json-core khỏi graph.

Nguyên tắc:

- Khai báo trực tiếp module mà source của project trực tiếp sử dụng.
- Chọn api nếu module đó thuộc public API.
- Chọn implementation nếu module chỉ dùng nội bộ.
- Không dựa vào dependency bắc cầu của dependency khác như một cách khai báo ngầm.
- Dùng dependencyInsight để tìm nguồn của module khi cần.

Khai báo dependency trực tiếp làm metadata publication dễ hiểu và ổn định hơn.

## 20. Kiểm tra publication trước khi phát hành

Một quy trình kiểm tra publication nên gồm cả metadata và consumer.

### Kiểm tra tọa độ và artifact

Xác nhận:

- group, artifactId và version đúng.
- JAR đúng phiên bản.
- Sources/Javadoc artifact nếu dự án yêu cầu.
- POM và Gradle Module Metadata được publish.
- Repository URL và layout đúng.

### Kiểm tra dependency metadata

Mở POM và .module, kiểm tra:

- Dependency API nằm trong variant/scope phù hợp.
- Dependency implementation không bị xuất lên compile classpath ngoài ý muốn.
- Runtime dependency được công bố.
- Compile-only và test dependency không bị công bố sai.
- Exclusions, constraints và platform được biểu diễn như mong muốn.
- Version request ổn định.

### Kiểm tra consumer

Tạo project consumer dùng đúng tọa độ publication trong repository thử nghiệm. Chạy compile, test và runtime. Nếu hỗ trợ cả Gradle và Maven, kiểm tra bằng cả hai công cụ.

### Kiểm tra dependency graph

Dùng:

~~~bash
./gradlew dependencies --configuration compileClasspath
~~~

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Và dependencyInsight cho từng module cần xác minh.

Không nên kết luận publication chính xác chỉ vì task publish thành công. Publish task chỉ xác nhận artifact và metadata được tạo/đẩy theo cấu hình; nó không chứng minh consumer nhận đúng graph.

## 21. Những lỗi thường gặp khi công bố dependency

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Consumer không biên dịch được kiểu trong public API | Dependency bị khai báo implementation thay vì api | Xem lại public signature và dùng api nếu phù hợp |
| Consumer compile được nhưng runtime thiếu implementation | Runtime dependency không được khai báo hoặc metadata publish thiếu | Kiểm tra runtimeElements, POM scope runtime và runtimeClasspath |
| Consumer thấy dependency nội bộ trên compile classpath | Dùng api quá rộng | Chuyển sang implementation nếu dependency không thuộc public API |
| Test framework bị kéo vào consumer | Dependency test khai báo sai configuration | Chuyển sang testImplementation/testRuntimeOnly |
| Maven và Gradle nhận graph khác nhau | POM và Gradle Module Metadata có khả năng biểu diễn khác nhau | Kiểm tra cả hai metadata và thử consumer thật |
| Compile-only API thiếu ở Maven consumer | POM không thể mô tả chính xác variant compile-only của Gradle | Kiểm tra POM sinh ra, tài liệu hóa dependency môi trường hoặc điều chỉnh API/publication |
| Consumer nhận version không mong muốn | Conflict, constraint hoặc BOM chưa được thiết kế đúng | Dùng dependencyInsight và kiểm tra version alignment |
| Dependency không xuất hiện dù được khai báo | Sai configuration, component publication hoặc dependency không thuộc variant được chọn | Kiểm tra outgoing variants và publication metadata |
| Artifact JAR publish được nhưng dependency mất | Publication chỉ gắn JAR thủ công, không lấy component metadata | Publish từ components["java"] |
| Build producer thành công nhưng consumer lỗi | Chưa thử publication trong project consumer độc lập | Tạo consumer test và kiểm tra compile/runtime |

## 22. Quy trình công bố dependency bắc cầu chính xác

Có thể áp dụng trình tự sau cho một thư viện:

1. Xác định public API và các kiểu dependency xuất hiện trong signature.
2. Liệt kê dependency trực tiếp mà source của thư viện thực sự sử dụng.
3. Phân loại từng dependency thành api, implementation, compileOnly, compileOnlyApi hoặc runtimeOnly.
4. Đặt test dependency trong testImplementation/testRuntimeOnly.
5. Dùng Java Library plugin để tạo API/runtime variants.
6. Khai báo version cụ thể hoặc constraint có chủ đích; tránh dynamic version không cần thiết.
7. Dùng platform/BOM nếu nhiều module cần version alignment.
8. Publish component Java qua Maven Publish plugin bằng from(components["java"]).
9. Kiểm tra POM và Gradle Module Metadata được tạo.
10. Kiểm tra consumer Gradle trên compileClasspath và runtimeClasspath.
11. Nếu hỗ trợ Maven, kiểm tra POM bằng Maven consumer thật.
12. Xác nhận exclusions, optional feature, constraints và compile-only API không tạo khác biệt ngoài dự kiến.
13. Chạy test trên artifact đã publish từ repository thử nghiệm.
14. Chỉ phát hành khi consumer sử dụng được API và runtime dependency đúng như contract.

## 23. Những nguyên tắc cần nhớ

- Metadata publication quyết định dependency bắc cầu mà consumer nhìn thấy; JAR đơn lẻ không mô tả đầy đủ graph.
- Dùng Java Library plugin cho thư viện cần phân biệt API và implementation.
- **api** dành cho dependency xuất hiện trong public contract; **implementation** dành cho dependency nội bộ.
- **compileOnly** và **runtimeOnly** mô tả nhu cầu của thư viện ở các classpath riêng; **testImplementation** và **testRuntimeOnly** chỉ phục vụ test.
- **compileOnlyApi** có semantics compile-only cho consumer; kiểm tra POM vì Maven không có mô hình variant tương đương hoàn toàn.
- Gradle tạo outgoing variants như apiElements và runtimeElements để consumer chọn classpath phù hợp.
- Publish từ **components["java"]** để metadata dependency và variant được đưa vào publication.
- Maven POM dùng scope compile/runtime/provided; Gradle Module Metadata có thể biểu diễn variants và constraints chi tiết hơn.
- Kiểm tra cả POM lẫn .module nếu thư viện hỗ trợ consumer Gradle và Maven.
- Khai báo trực tiếp dependency mà source sử dụng; không dựa vào dependency bắc cầu tình cờ.
- Dùng constraints hoặc BOM để quản lý version alignment; tránh dynamic version trong publication nếu không có chủ đích.
- Kiểm thử consumer độc lập là cách xác nhận metadata thực sự hoạt động sau khi publish.

Một thư viện được phát hành tốt phải công bố đúng contract mà consumer cần: dependency nào cần để biên dịch API, dependency nào chỉ cần khi chạy, và dependency nào chỉ phục vụ việc phát triển hoặc kiểm thử thư viện. Khi cấu hình Gradle phản ánh đúng các vai trò đó và publication được kiểm tra bằng consumer thật, dependency graph bắc cầu sẽ rõ ràng, ổn định và ít gây bất ngờ cho ứng dụng sử dụng thư viện.

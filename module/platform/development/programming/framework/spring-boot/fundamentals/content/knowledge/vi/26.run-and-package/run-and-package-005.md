# Lớp main, manifest, dependency và cấu trúc JAR thực thi

Khi học Spring Boot, chúng ta thường bắt đầu bằng một lớp chứa `main()`, chạy ứng dụng từ IDE rồi thấy server khởi động. Nhưng khi đóng gói để triển khai, câu hỏi quan trọng hơn là: **JVM tìm thấy lớp main bằng cách nào, các dependency được tải ở đâu và vì sao một file JAR Spring Boot có thể chạy bằng `java -jar` mà không cần tự xây dựng classpath dài?**

Để hiểu điều đó, cần phân biệt bốn thành phần:

1. **Lớp main của ứng dụng**: chứa `public static void main(String[] args)` và thường gọi `SpringApplication.run(...)`.
2. **JAR manifest**: metadata tại `META-INF/MANIFEST.MF` cho Java launcher biết điểm vào của archive.
3. **Dependencies**: các thư viện ứng dụng cần khi chạy, được công cụ build xác định từ dependency graph.
4. **Cấu trúc executable JAR**: bố cục đặc biệt do Spring Boot packaging plugin tạo, gồm boot loader, application classes và thư viện JAR lồng nhau.

Nhìn bốn thành phần như một dòng thực thi giúp giải thích những lỗi như `no main manifest attribute`, `ClassNotFoundException` hoặc tình trạng file JAR chạy trong IDE nhưng thất bại khi triển khai.

## 1. Phân biệt chạy trong IDE và chạy bản đóng gói

Khi chạy từ IDE hoặc sử dụng `bootRun`, IDE/build tool thường tạo classpath từ:

- Thư mục chứa bytecode ứng dụng đã biên dịch.
- Resource directory như `src/main/resources`.
- Các dependency cần thiết cho runtime.
- Lớp main được chọn làm entry point.

Sơ đồ:

~~~text
IDE / bootRun
    |
    +-- target/main class: CatalogApplication
    |
    +-- application classes (build/classes/java/main)
    |
    +-- resources (build/resources/main)
    |
    +-- dependency JARs từ Gradle/Maven runtime classpath
    |
    v
JVM chạy CatalogApplication.main(...)
~~~

Trong khi đó, một executable JAR Spring Boot mang theo phần lớn dependency runtime ở bên trong archive:

~~~text
java -jar catalog-service.jar
    |
    v
Đọc META-INF/MANIFEST.MF
    |
    v
Boot launcher (Main-Class)
    |
    v
Nạp application classes + nested dependencies
    |
    v
Gọi CatalogApplication.main(...) (Start-Class)
    |
    v
SpringApplication.run(...)
~~~

Điểm khác biệt: khi chạy `java -jar`, JVM **không** tự hiểu toàn bộ JAR lồng nhau như các phần tử classpath tiêu chuẩn. Spring Boot cung cấp launcher/loader để xử lý bố cục executable archive.

## 2. Lớp main thực sự của ứng dụng

Một lớp main điển hình:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Ba thành phần quan trọng:

- `public static void main(String[] args)`: entry point Java của chương trình.
- `@SpringBootApplication`: gom các cơ chế cấu hình cơ bản của Spring Boot.
- `SpringApplication.run(CatalogApplication.class, args)`: khởi tạo, refresh và vận hành application context.

`@SpringBootApplication` là annotation kết hợp những chức năng như Spring Boot configuration, auto-configuration và component scanning. Nó không có nhiệm vụ tự viết JAR manifest. Manifest được công cụ đóng gói tạo trong **build phase**.

### 2.1. Vì sao vị trí package của main quan trọng?

Component scan mặc định bắt đầu từ package chứa lớp được đánh dấu `@SpringBootApplication` và quét các package con.

Ví dụ nên tổ chức:

~~~text
src/main/java/
└── com/example/catalog/
    ├── CatalogApplication.java
    ├── web/
    │   └── CatalogController.java
    ├── service/
    │   └── CatalogService.java
    └── repository/
        └── CatalogRepository.java
~~~

`CatalogApplication` thuộc `com.example.catalog`, nên các component bên dưới các package con có thể được phát hiện theo cấu hình scan mặc định.

Nếu đặt main trong `com.example.catalog.launcher` còn service ở `com.example.catalog.service`, service sẽ nằm **ngoài cây package con của launcher**. JAR vẫn có thể đóng gói và chạy, nhưng application context có thể thiếu bean. Đó là lỗi cấu hình component scan, không phải lỗi manifest hay dependency packaging.

Có thể xử lý bằng cách bố trí lớp main ở package gốc phù hợp hoặc cấu hình scanning/import một cách tường minh. Không nên mở scan toàn bộ `com` hoặc package của nhiều thư viện chỉ để sửa một lỗi package.

### 2.2. Main class không nhất thiết là lớp chứa mọi bean

Lớp main thường chỉ làm nhiệm vụ bootstrap. Controller, service, repository và các bean nghiệp vụ nằm ở class khác. Bên trong executable JAR, chúng đều được đóng gói thành class files; Java launcher không tự động tạo mọi object từ những class đó. Spring container quyết định bean nào được đăng ký và khởi tạo.

## 3. JAR là gì và manifest là gì?

JAR (Java Archive) dựa trên định dạng ZIP, có thể chứa:

- Bytecode `.class`.
- Resource files như YAML, XML, template và static assets.
- Metadata của thư viện.
- Thư mục `META-INF` và file manifest.

Manifest nằm ở:

~~~text
META-INF/MANIFEST.MF
~~~

Một Java JAR chạy được bằng `java -jar` thông thường cần một manifest có `Main-Class` trỏ tới class có phương thức main phù hợp.

Ví dụ cho một JAR Java độc lập đơn giản:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.tools.CliApplication
~~~

Khi chạy:

~~~bash
java -jar tool.jar
~~~

Java launcher đọc `Main-Class` và gọi `com.example.tools.CliApplication.main(...)`.

Nhưng executable JAR Spring Boot **thường có hai vai trò entry point**: entry point của JVM và entry point ứng dụng.

## 4. Main-Class khác Start-Class trong Spring Boot executable JAR

Với executable JAR do Spring Boot đóng gói, manifest thường trông tương tự:

~~~text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.catalog.CatalogApplication
Spring-Boot-Version: 3.x.y
Spring-Boot-Classes: BOOT-INF/classes/
Spring-Boot-Lib: BOOT-INF/lib/
~~~

Các giá trị minh họa ở trên dùng kiểu tên launcher của **Spring Boot 3.2+**. Trên Spring Boot 2.x và một số bản Boot 3 trước khi loader đổi package, `Main-Class` có thể là:

~~~text
Main-Class: org.springframework.boot.loader.JarLauncher
~~~

Không nên sửa tay launcher class theo một ví dụ lấy từ phiên bản khác. Công cụ đóng gói phù hợp với phiên bản Spring Boot sẽ ghi giá trị đúng.

Ý nghĩa:

| Manifest attribute | Vai trò |
|---|---|
| `Manifest-Version` | Version cú pháp manifest |
| `Main-Class` | Class mà JVM gọi đầu tiên khi chạy `java -jar` |
| `Start-Class` | Class main của ứng dụng, được Boot launcher khởi động |
| `Spring-Boot-Version` | Metadata phiên bản Boot do công cụ đóng gói ghi khi phù hợp |
| `Spring-Boot-Classes` | Vị trí chứa application classes/resources trong archive |
| `Spring-Boot-Lib` | Vị trí chứa nested runtime dependency JARs |

Các attribute `Spring-Boot-*` khác có thể xuất hiện tùy phiên bản và tùy chọn build; không phải mọi executable archive đều có manifest y hệt ví dụ.

### 4.1. Vì sao Main-Class không phải CatalogApplication?

Nếu đặt `Main-Class: com.example.catalog.CatalogApplication` trong một archive mà application classes nằm dưới `BOOT-INF/classes` và dependencies nằm trong `BOOT-INF/lib`, Java launcher chuẩn không tự thiết lập classpath theo bố cục đó.

Spring Boot cần launcher để:

1. Hiểu layout của executable archive.
2. Tìm application classes và nested library JARs.
3. Tạo class loading environment phù hợp.
4. Tìm `Start-Class` trong manifest.
5. Gọi phương thức `main(String[] args)` của ứng dụng.

Vì vậy:

~~~text
Main-Class = điểm vào ở cấp JVM
Start-Class = điểm vào logic ở cấp ứng dụng Spring Boot
~~~

Không nhầm hai attribute khi điều tra “main class nào được chạy”.

## 5. Bố cục tiêu biểu của executable JAR Spring Boot

Ví dụ archive `catalog-service.jar`:

~~~text
catalog-service.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── ...
├── org/
│   └── springframework/
│       └── boot/
│           └── loader/
│               └── ... (Boot launcher/loader classes)
└── BOOT-INF/
    ├── classes/
    │   ├── com/
    │   │   └── example/
    │   │       └── catalog/
    │   │           ├── CatalogApplication.class
    │   │           ├── service/
    │   │           └── web/
    │   ├── application.yml
    │   ├── static/
    │   └── templates/
    ├── lib/
    │   ├── spring-boot-....jar
    │   ├── spring-context-....jar
    │   ├── spring-web-....jar
    │   └── ... other runtime dependencies
    ├── classpath.idx       (có thể có)
    └── layers.idx          (có thể có)
~~~

Tên cụ thể và các file index tùy phiên bản Spring Boot, loại plugin và cấu hình build. Cây trên là mô hình để đọc cấu trúc, không phải danh sách cố định của mọi project.

### 5.1. BOOT-INF/classes

Nơi chứa:

- Các file `.class` do ứng dụng tự biên dịch.
- Resources từ `src/main/resources` sau quá trình resource processing.
- File `application.yml`, template và static resources nếu được đóng gói.
- Các tài nguyên classpath khác thuộc ứng dụng.

Ví dụ:

~~~text
src/main/java/com/example/catalog/CatalogApplication.java
    -> BOOT-INF/classes/com/example/catalog/CatalogApplication.class

src/main/resources/application.yml
    -> BOOT-INF/classes/application.yml

src/main/resources/templates/invoice.html
    -> BOOT-INF/classes/templates/invoice.html
~~~

Đây vẫn là tài nguyên **classpath**, không phải file path vật lý độc lập nằm cạnh executable JAR trên ổ đĩa.

### 5.2. BOOT-INF/lib

Nơi chứa các dependency JAR dùng trong runtime và được build plugin chọn để đóng gói.

Ví dụ:

~~~text
BOOT-INF/lib/spring-boot-3.x.y.jar
BOOT-INF/lib/spring-core-6.x.y.jar
BOOT-INF/lib/jackson-databind-2.x.y.jar
BOOT-INF/lib/tomcat-embed-core-....jar
~~~

Tên/version trong ví dụ mang tính minh họa, không phải một bộ dependency đã được kiểm chứng là tương thích với nhau.

Mỗi dependency là một **JAR nằm trong JAR chính**, thay vì bung toàn bộ class của thư viện vào một thư mục chung.

### 5.3. Boot loader classes

Các class launcher/loader là một phần của executable archive và được đặt ở cấu trúc mà Java launcher có thể nạp khi đọc `Main-Class`. Với các bản Boot mới hơn, Java package thường có `org.springframework.boot.loader.launch`; với các bản cũ hơn, package có thể khác.

Boot loader thực hiện nhiệm vụ tạo classpath từ `BOOT-INF/classes` và các thư viện dưới `BOOT-INF/lib`. Nó không phải business code và thường không cần sửa.

### 5.4. classpath.idx và layers.idx

Một số executable JAR có thêm:

- `BOOT-INF/classpath.idx`: mô tả thứ tự classpath được launcher sử dụng trong tình huống phù hợp.
- `BOOT-INF/layers.idx`: mô tả cách phân lớp nội dung archive để các công cụ đóng gói container tối ưu cache/layer.

Các file này **không phải** nơi chứa source hoặc dependency bytecode. Chúng là metadata phụ trợ. Không tự thêm hay chỉnh chúng bằng tay nếu không có lý do về packaging pipeline.

## 6. Vì sao dùng nested JAR thay vì bung toàn bộ dependency?

Có nhiều cách gom thư viện vào một artifact:

| Kiểu artifact | Bố cục | Điểm đặc trưng |
|---|---|---|
| Plain JAR | Application classes/resources | Thường không chứa toàn bộ runtime dependencies |
| Spring Boot executable JAR | `BOOT-INF/classes`, `BOOT-INF/lib/*.jar` và launcher | Giữ các thư viện dưới dạng nested JARs |
| Shaded/uber JAR | Bung và hợp nhất nhiều dependency classes vào một namespace archive | Cần xử lý file trùng, resources/services và relocation khi cần |

Spring Boot executable JAR thường được gọi là **fat JAR**, nhưng nó không nhất thiết là shaded JAR.

Ưu điểm của nested JAR layout:

- Đóng gói ứng dụng và dependency vào một artifact.
- Không yêu cầu script triển khai liệt kê hàng chục JAR trên `-cp`.
- Giữ nhiều dependency dưới dạng archive riêng.
- Hỗ trợ launcher và metadata để chạy trên môi trường chuẩn.
- Có thể sử dụng layered archive để cải thiện việc build container image.

Hạn chế/đặc điểm cần nhớ:

- Một số công cụ đọc classpath trực tiếp có thể không hiểu nested JAR layout nếu không được thiết kế cho nó.
- Không phải mọi thư viện hoặc cơ chế class loading tùy chỉnh đều tương thích nếu chúng giả định mọi JAR đều là file riêng trên filesystem.
- Archive lớn hơn plain JAR vì có thêm dependencies và loader.
- Cần dùng plugin/version phù hợp để tạo định dạng đúng.

## 7. java -jar thực sự làm gì?

Lệnh:

~~~bash
java -jar catalog-service.jar
~~~

kích hoạt chuỗi sau:

~~~text
1. JVM mở JAR
         |
         v
2. Đọc META-INF/MANIFEST.MF
         |
         v
3. Nạp Main-Class (Boot JarLauncher)
         |
         v
4. Launcher đọc cấu trúc BOOT-INF/
         |
         v
5. Tạo class loader cho application classes + nested libraries
         |
         v
6. Nạp Start-Class (CatalogApplication)
         |
         v
7. Gọi CatalogApplication.main(args)
         |
         v
8. SpringApplication.run(...)
         |
         v
9. Tạo ApplicationContext, auto-configuration, embedded server...
~~~

Đây là luồng khái niệm, không phải chính xác mọi class/method nội bộ của loader qua tất cả phiên bản.

### 7.1. Vì sao -cp không thay được Boot loader?

Java launcher chuẩn không biến mọi file `BOOT-INF/lib/*.jar` thành classpath entries chỉ vì chúng xuất hiện trong ZIP.

Lệnh như:

~~~bash
java -cp catalog-service.jar com.example.catalog.CatalogApplication
~~~

không phải cách chạy mặc định của Spring Boot executable JAR có layout `BOOT-INF`. Application class không nằm ở root classpath của JAR, và các thư viện lồng nhau cũng chưa được Java classpath chuẩn liệt kê.

**Cách đúng:** dùng `java -jar` để kích hoạt Boot launcher, hoặc chạy từ IDE/build tool với classpath do chúng tạo.

### 7.2. JVM options và application arguments

Ví dụ:

~~~bash
java -Xms256m -Xmx1g -Duser.timezone=UTC \
     -jar catalog-service.jar \
     --spring.profiles.active=prod \
     --server.port=8081
~~~

Phân biệt:

- `-Xms256m`, `-Xmx1g`, `-Duser.timezone=UTC`: options của JVM, đứng **trước** `-jar`.
- `--spring.profiles.active=prod` và `--server.port=8081`: arguments được truyền tới phương thức `main(args)` và thường được Spring Boot xử lý như command-line properties.

Nếu chạy lệnh trên Windows PowerShell, ví dụ tương đương có thể viết trên một dòng để tránh khác biệt cú pháp nối dòng giữa shell.

### 7.3. Chạy trên server có nhất thiết cần Maven/Gradle không?

Không. Một executable JAR hoàn chỉnh có thể chạy với Java runtime tương thích bằng `java -jar`; server triển khai không cần Gradle hoặc Maven chỉ để gọi ứng dụng.

Tuy nhiên, server vẫn cần:

- Java runtime/JDK phù hợp với bản Spring Boot và bytecode.
- Cấu hình và credentials của môi trường.
- Quyền đọc JAR, network, filesystem và các tài nguyên liên quan.
- Database, broker và các dịch vụ ngoài nếu ứng dụng phụ thuộc vào chúng.

Với Spring Boot 3, nền tảng Java tối thiểu thông thường là **Java 17**. Các dòng Boot khác có baseline và compatibility matrix riêng; khi nâng cấp phải kiểm tra Java runtime tương thích.

## 8. Dependencies đến từ đâu?

Dự án Spring Boot không tự quyết định phiên bản thư viện dựa trên tên package import. Nó sử dụng dependency graph do Maven hoặc Gradle tạo từ build configuration, bao gồm direct và transitive dependencies.

Ví dụ Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    runtimeOnly 'org.postgresql:postgresql'

    compileOnly 'org.projectlombok:lombok'
    annotationProcessor 'org.projectlombok:lombok'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đây là đoạn cấu hình dependencies, giả định dự án đã áp dụng plugin và cơ chế quản lý versions Spring Boot phù hợp.

Ý nghĩa:

| Gradle configuration | Ý nghĩa thông thường |
|---|---|
| `implementation` | Cần cho compilation và runtime |
| `api` trong `java-library` | Expose API dependency cho consumer khi phù hợp |
| `runtimeOnly` | Không cần compile-time API trong code ứng dụng, nhưng cần khi chạy |
| `compileOnly` | Chỉ cần compile; không tự động nằm trong runtime classpath |
| `annotationProcessor` | Dùng trong annotation processing lúc build |
| `testImplementation` / `testRuntimeOnly` | Phục vụ test; không dùng làm runtime dependency của ứng dụng |

Spring Boot packaging task thường dựa vào runtime classpath và các quy tắc packaging liên quan để đưa thư viện cần thiết vào executable JAR.

### 8.1. Transitive dependencies

Khi khai báo:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-web'
~~~

starter có thể mang theo nhiều dependency như Spring MVC, JSON support và embedded servlet container phù hợp. Bạn không cần khai báo thủ công từng thư viện nếu starter và dependency management đã xử lý chúng.

Tuy nhiên, **dependency có mặt trong IDE chưa chắc có mặt trong executable JAR** nếu nó chỉ thuộc test/compile-only configuration hoặc đã bị exclude bởi cấu hình packaging.

### 8.2. Không nhúng một version tùy ý cho từng thư viện Spring

Các dependency của Spring Boot thường được quản lý theo phiên bản tương thích thông qua Boot parent/BOM hoặc cơ chế dependency management tương ứng. Tự override một thư viện lõi mà không kiểm tra compatibility có thể làm build vẫn thành công nhưng runtime xuất hiện `NoSuchMethodError`, `NoClassDefFoundError` hoặc hành vi bất thường.

Khi cần nâng cấp thư viện, hãy xem dependency graph cuối cùng và dependency management của đúng dòng Boot đang sử dụng.

## 9. Đóng gói bằng Gradle: bootJar khác jar

Trong dự án Gradle dùng Spring Boot plugin, các task liên quan thường gồm:

- `compileJava`: biên dịch source.
- `processResources`: xử lý/copy resources.
- `classes`: kết hợp các output của compilation/resources.
- `jar`: tạo archive Java thông thường.
- `bootJar`: tạo **Spring Boot executable JAR**.
- `bootRun`: chạy ứng dụng bằng classpath trong môi trường build.
- `build`: thực hiện lifecycle build gồm nhiều task tương ứng.

Ví dụ cấu hình ứng dụng đã áp dụng plugin Spring Boot:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
}

springBoot {
    mainClass = 'com.example.catalog.CatalogApplication'
}

tasks.named('bootJar') {
    archiveFileName = 'catalog-service.jar'
}
~~~

Đây là **fragment**, giả định version Spring Boot plugin đã được xác định qua plugin management hoặc cấu hình ở root project. Trong một project độc lập, vẫn cần version/plugin repositories phù hợp.

Đóng gói:

~~~bash
./gradlew clean bootJar
~~~

Kết quả minh họa:

~~~text
build/libs/catalog-service.jar
~~~

Chạy:

~~~bash
java -jar build/libs/catalog-service.jar
~~~

### 9.1. Vì sao build/libs có hai file JAR?

Nhiều phiên bản plugin có thể sinh cả:

~~~text
catalog-service.jar
catalog-service-plain.jar
~~~

`catalog-service.jar` có thể là executable JAR do `bootJar` tạo; `catalog-service-plain.jar` là plain archive từ `jar` theo convention cấu hình plugin ở phiên bản đó.

Không dựa tuyệt đối vào tên file khi build script tùy biến archive classifiers. Hãy kiểm tra **manifest và cấu trúc file** để xác định artifact nào chạy bằng `java -jar`.

### 9.2. bootRun không kiểm chứng executable archive

~~~bash
./gradlew bootRun
~~~

chạy ứng dụng dựa trên classpath do Gradle quản lý. Nó hữu ích cho phát triển, nhưng **không chứng minh** `bootJar` sẽ có manifest, dependencies và layout chính xác.

Nếu mục tiêu là xác nhận artifact phát hành, cần kiểm tra/chạy đúng file do `bootJar` tạo.

### 9.3. Dự án là library có cần bootJar không?

Nếu module chỉ cung cấp một thư viện Java dùng chung và không có entry point ứng dụng, một plain JAR thường phù hợp hơn executable Spring Boot JAR.

Không nên buộc mọi module trong multi-module build tạo executable archive. Module `application` có thể dùng `bootJar`, còn các module `domain`, `common` hoặc `client-sdk` tạo library JAR bình thường rồi được ứng dụng đưa vào runtime dependency graph.

## 10. Đóng gói bằng Maven: spring-boot-maven-plugin repackage

Với Maven, source Java thường được biên dịch và đóng gói theo lifecycle:

~~~bash
./mvnw clean package
~~~

Để biến archive thông thường thành executable Spring Boot JAR, có thể dùng `spring-boot-maven-plugin` với goal `repackage`.

Ví dụ fragment trong `pom.xml`:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
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

Với những project kế thừa `spring-boot-starter-parent`, plugin execution hoặc defaults có thể đã được cấu hình theo convention của parent. Không nên thêm execution trùng mà chưa kiểm tra cấu hình cuối cùng của project.

Sau `package`, executable archive thường nằm ở:

~~~text
target/catalog-service-<version>.jar
~~~

Trong một số cấu hình repackage, Maven có thể lưu bản JAR ban đầu bằng hậu tố như `.original`. Điều này giúp phân biệt archive trước repackage và executable archive.

### 10.1. Maven scopes ảnh hưởng dependency packaging

Maven dùng các scope như `compile`, `runtime`, `test`, `provided` và dependency `optional`. Những scope này ảnh hưởng tới dependency graph và cách packaging plugin chọn libraries.

Lưu ý:

- `test` dependencies không phải runtime libraries của ứng dụng phát hành.
- `provided` có semantics riêng và cách xử lý của executable JAR/WAR có thể khác nhau; không nên suy luận từ tên scope rằng mọi file provided đều bị bỏ qua trong mọi packaging layout.
- `optional` ảnh hưởng cách dependency được truyền sang project tiêu thụ; nó không phải công tắc đơn giản “không đóng gói vào artifact đang build”.
- Với executable WAR có thể có thư mục `WEB-INF/lib-provided` dành cho dependencies chỉ cần khi chạy embedded container.

Hãy kiểm tra archive thực tế và cấu hình plugin thay vì kết luận bằng một bảng scope đơn giản áp dụng cho mọi archive type.

## 11. Trường hợp có nhiều main classes

Một project có thể chứa nhiều class:

~~~java
public class CatalogApplication {
    public static void main(String[] args) { /* ... */ }
}
~~~

~~~java
public class MigrationTool {
    public static void main(String[] args) { /* ... */ }
}
~~~

Nếu packaging plugin không xác định được main class một cách rõ ràng, build có thể báo lỗi hoặc chọn entry point không như mong đợi tùy cấu hình và phiên bản.

Nên khai báo tường minh cho artifact ứng dụng.

Với Gradle:

~~~groovy
springBoot {
    mainClass = 'com.example.catalog.CatalogApplication'
}
~~~

Hoặc đặt trên task `bootJar` khi muốn chọn main class cho task cụ thể:

~~~groovy
tasks.named('bootJar') {
    mainClass = 'com.example.catalog.CatalogApplication'
}
~~~

Với Maven plugin, có thể chỉ định main class trong cấu hình plugin:

~~~xml
<configuration>
    <mainClass>com.example.catalog.CatalogApplication</mainClass>
</configuration>
~~~

Sau khi đóng gói, kiểm tra `Start-Class` trong manifest để xác nhận entry point thực tế của artifact.

**Không nhầm:** setting Java application main class cho một tool/plugin khác và setting main class mà Spring Boot packaging task dùng có thể có liên hệ nhưng không phải lúc nào là một trong mọi cấu hình tùy biến.

## 12. Cách kiểm tra cấu trúc executable JAR

JDK cung cấp công cụ `jar` để liệt kê nội dung:

~~~bash
jar tf build/libs/catalog-service.jar
~~~

Để lọc những đường dẫn quan trọng trên PowerShell:

~~~powershell
jar tf build/libs/catalog-service.jar |
    Select-String 'MANIFEST.MF|BOOT-INF/classes|BOOT-INF/lib|JarLauncher|layers.idx'
~~~

Ví dụ những entry có thể thấy:

~~~text
META-INF/MANIFEST.MF
org/springframework/boot/loader/launch/JarLauncher.class
BOOT-INF/classes/com/example/catalog/CatalogApplication.class
BOOT-INF/classes/application.yml
BOOT-INF/lib/spring-boot-3.x.y.jar
BOOT-INF/lib/spring-context-6.x.y.jar
~~~

Dòng `JarLauncher.class` ở đây giả định Spring Boot với loader package dạng `org.springframework.boot.loader.launch`. Archive từ phiên bản cũ có thể có path khác.

### 12.1. Đọc manifest

Nếu môi trường có `unzip`:

~~~bash
unzip -p build/libs/catalog-service.jar META-INF/MANIFEST.MF
~~~

Trên môi trường chỉ có JDK `jar`, có thể giải nén vào một thư mục tạm rồi đọc `META-INF/MANIFEST.MF`, tránh giải nén lên folder source code đang chứa file trùng tên.

Ví dụ các dòng cần tìm:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.catalog.CatalogApplication
Spring-Boot-Classes: BOOT-INF/classes/
Spring-Boot-Lib: BOOT-INF/lib/
~~~

Làm rõ:

- Nếu không có `Main-Class` phù hợp, `java -jar` không biết entry point.
- Nếu `Main-Class` là Boot launcher nhưng `Start-Class` sai, launcher có thể không tải được application main class.
- Nếu thiếu loader classes hoặc dependency JARs, archive có thể bị đóng gói sai hoặc đã bị công cụ khác sửa làm hỏng cấu trúc.

### 12.2. Kiểm tra dependency nằm trong JAR chưa

~~~powershell
jar tf build/libs/catalog-service.jar |
    Select-String 'BOOT-INF/lib/'
~~~

Nếu ứng dụng gặp `ClassNotFoundException` khi chạy JAR, hãy đối chiếu loại class thiếu với dependency cần thiết và archive thực tế. Thấy dependency trong Gradle/Maven cache không có nghĩa dependency đó chắc chắn nằm trong executable archive.

### 12.3. Kiểm tra resource

~~~powershell
jar tf build/libs/catalog-service.jar |
    Select-String 'BOOT-INF/classes/application'
~~~

Nếu code dùng `classpath:application.yml` hoặc `classpath:templates/invoice.html`, kiểm tra resource có được copy đúng vị trí dưới `BOOT-INF/classes` hay không.

## 13. Spring Boot loader và class loading

Java classpath thông thường trỏ tới:

- Thư mục chứa các class files.
- Một hoặc nhiều file JAR có thể truy cập như archive riêng.

Nested JAR lại nằm **bên trong** archive Spring Boot:

~~~text
catalog-service.jar
  └── BOOT-INF/lib/dependency-a.jar
  └── BOOT-INF/lib/dependency-b.jar
~~~

Launcher/loader Spring Boot được thiết kế để tải classes và resources trong layout này. Các quy tắc class loading cụ thể phụ thuộc implementation của Boot loader theo phiên bản, nhưng ý nghĩa vận hành là: **không cần giải nén toàn bộ dependencies ra một folder mới có thể chạy ứng dụng**.

### 13.1. Class loader tùy chỉnh có thể gặp khác biệt

Một số thư viện cũ giả định rằng URL của resource luôn map đến một file thật trên ổ đĩa, ví dụ tự ép thành `java.io.File`:

~~~java
File file = new File(
        getClass().getResource("/config/template.txt").toURI()
);
~~~

Code này có thể chạy từ thư mục resources trong IDE nhưng thất bại khi resource nằm trong JAR hoặc nested archive.

Thay vì yêu cầu resource là một file vật lý, hãy dùng stream API khi chỉ cần đọc nội dung:

~~~java
try (InputStream input = getClass()
        .getResourceAsStream("/config/template.txt")) {

    if (input == null) {
        throw new IllegalStateException("Template not found");
    }

    byte[] bytes = input.readAllBytes();
    // Xử lý bytes...
}
~~~

Với Spring, có thể dùng `ResourceLoader` và `Resource.getInputStream()`. Nếu thư viện bắt buộc phải nhận một file vật lý, có thể cần copy resource ra một temporary file có lifecycle/permission phù hợp, nhưng đừng mặc định mọi classpath resource có đường dẫn File trực tiếp.

### 13.2. Classloader của Boot không giải quyết mọi dependency conflict

Loader có thể tìm thấy nested JARs, nhưng không tự sửa những vấn đề như:

- Hai phiên bản thư viện không tương thích.
- Một dependency vắng mặt ở runtime classpath.
- Duplicate classes/resources từ các dependency.
- Thư viện dùng API bị thay đổi ở version khác.

Các vấn đề này vẫn cần giải quyết ở dependency graph/build configuration.

## 14. Vị trí application.yml và externalized configuration

Trong executable JAR, file:

~~~text
src/main/resources/application.yml
~~~

thường trở thành:

~~~text
BOOT-INF/classes/application.yml
~~~

Spring Boot có thể đọc resource từ classpath thông qua loader. Nhưng trong triển khai production, không nên sửa nội dung JAR mỗi lần muốn đổi cổng hoặc database URL.

Ví dụ chạy với cấu hình ngoài artifact:

~~~bash
java -jar catalog-service.jar \
     --spring.profiles.active=prod \
     --server.port=8081
~~~

Hoặc môi trường cung cấp properties:

~~~text
SPRING_PROFILES_ACTIVE=prod
SERVER_PORT=8081
DB_PASSWORD=<giá trị do secret store cấp>
~~~

Đây là ví dụ tên environment variables và placeholder mô tả, không chứa secret thật.

**Phân biệt đóng gói code với cấu hình vận hành:**

- Application classes và dependencies thường cố định theo artifact build.
- Externalized configuration có thể khác nhau theo deployment.
- Secret không nên hard-code trong `application.yml` đã đóng gói vào JAR.

Một executable JAR không có nghĩa mọi tài nguyên, credential, database hoặc remote service mà ứng dụng cần đều đã có trong file đó.

## 15. Boot JAR khác executable WAR

Spring Boot cũng có thể đóng gói ứng dụng thành WAR, ví dụ khi cần triển khai lên servlet container bên ngoài.

Bố cục tiêu biểu của WAR:

~~~text
catalog-service.war
├── META-INF/
├── WEB-INF/
│   ├── classes/
│   ├── lib/
│   └── lib-provided/    (có thể có)
└── org/springframework/boot/loader/... (khi executable)
~~~

So sánh:

| Đặc điểm | Executable JAR | Executable WAR |
|---|---|---|
| Lớp ứng dụng | `BOOT-INF/classes` | `WEB-INF/classes` |
| Dependencies chính | `BOOT-INF/lib` | `WEB-INF/lib` |
| Loader | JarLauncher (khi dùng launcher mặc định) | WarLauncher (khi executable) |
| Mục đích phổ biến | Chạy độc lập bằng `java -jar` | Chạy độc lập hoặc triển khai servlet container theo cấu hình |
| Embedded server | Thường được đóng gói theo starter/runtime | Cần cấu hình phù hợp với external container nếu deploy WAR |

Trong Spring Boot 3.2+ package launcher ví dụ là `org.springframework.boot.loader.launch.WarLauncher`; các phiên bản cũ có thể dùng tên khác.

Để WAR có thể triển khai vào container ngoài, ứng dụng có thể cần kế thừa `SpringBootServletInitializer` và cấu hình dependency scope cho servlet container đúng cách.

**Không nhầm:** WAR do Maven/Gradle tạo ở dạng truyền thống không nhất thiết là executable WAR. Tương tự, một plain JAR cũng không tự trở thành executable Boot JAR chỉ vì có application main class.

## 16. Layered JAR và cách đóng gói Docker image

Khi triển khai Spring Boot trong container, executable JAR thường được copy vào image:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app

COPY build/libs/catalog-service.jar app.jar

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Ví dụ base image trên phù hợp về Java baseline cho nhiều ứng dụng Spring Boot 3, nhưng image/tag thực tế phải được chọn theo phiên bản Boot, target platform và chính sách bảo mật của dự án.

Cách này đơn giản: container chứa Java runtime và executable JAR. Tuy nhiên, mỗi lần thay application classes, toàn bộ file JAR có thể thay đổi, khiến layer chứa nó phải build/push lại.

### 16.1. layers.idx để tối ưu cache

Spring Boot packaging hỗ trợ layered archives trong những phiên bản/cấu hình phù hợp. File `BOOT-INF/layers.idx` mô tả các nhóm nội dung có thể được tách thành Docker layers.

Các nhóm mặc định thường xoay quanh:

- Dependencies ít thay đổi.
- Snapshot dependencies có thể thay đổi thường xuyên hơn.
- Spring Boot loader.
- Application classes/resources.

Ví dụ khái niệm:

~~~text
dependencies
spring-boot-loader
snapshot-dependencies
application
~~~

Khi application source đổi nhưng dependencies giữ nguyên, layer dependencies có thể được tái sử dụng trong quy trình build container hỗ trợ layered extraction.

### 16.2. Không đồng nhất layers.idx với runtime classpath

`layers.idx` phục vụ packaging/layer tooling; launcher vẫn cần nạp application classes và dependencies theo layout executable archive hoặc theo cách image đã được trích xuất/thiết lập.

Không tự chỉnh `layers.idx` để sửa lỗi `ClassNotFoundException`. Hãy kiểm tra dependency graph và archive layout trước.

### 16.3. jarmode layertools phụ thuộc phiên bản

Một số phiên bản Spring Boot cung cấp cơ chế jarmode/layer tooling để liệt kê và trích xuất layers của executable archive. Lệnh và availability thay đổi giữa các dòng Boot, đặc biệt khi packaging/build-image workflow thay đổi.

Vì vậy, hãy dùng hướng dẫn của **đúng phiên bản Boot** và kiểm tra artifact có hỗ trợ jarmode/layer extraction đó. Không nên sao chép một lệnh từ Boot 2 hoặc 3 vào dự án mới hơn rồi giả định cú pháp vẫn giống.

Spring Boot build plugins cũng có thể hỗ trợ tạo container image trực tiếp bằng buildpacks. Đây là một lựa chọn khác với Dockerfile tự viết; nó không làm thay đổi bản chất `Main-Class` và `Start-Class` bên trong executable JAR.

## 17. Có thể chạy trực tiếp file JAR như chương trình hệ điều hành không?

Lệnh chuẩn, tương thích rộng, là:

~~~bash
java -jar catalog-service.jar
~~~

Một số cơ chế packaging trên môi trường Unix/Linux hỗ trợ **fully executable archive** bằng cách thêm launch script phía trước file JAR. Khi được cấu hình như vậy và file có quyền execute, có thể gọi trực tiếp như một chương trình:

~~~bash
./catalog-service.jar
~~~

Nhưng đó là chế độ đóng gói riêng, không phải đặc tính mặc định của mọi executable JAR. Hơn nữa, một số ZIP/JAR tools không xử lý tốt archive có launch script prefix.

Nếu không có nhu cầu chạy dạng script/service trực tiếp, `java -jar` thường dễ dự đoán và ít phụ thuộc môi trường hơn.

## 18. Vì sao ứng dụng chạy trong IDE nhưng JAR không chạy?

Một số nguyên nhân phổ biến:

### 18.1. Chạy nhầm plain JAR

Có thể thấy:

~~~text
no main manifest attribute, in catalog-service-plain.jar
~~~

Plain JAR thường không có Boot launcher manifest. Hãy dùng artifact của `bootJar` (Gradle) hoặc artifact đã được `repackage` (Maven), không cố “sửa bằng cách đổi tên file”.

### 18.2. Main-Class hoặc Start-Class sai

Nếu project có nhiều main classes hoặc build customization gây nhầm, manifest có thể trỏ đến lớp khác.

Kiểm tra:

~~~text
Main-Class: ...
Start-Class: ...
~~~

Trong executable JAR Spring Boot, `Main-Class` phải là launcher phù hợp với loader được đóng gói, còn `Start-Class` phải là ứng dụng chính mong muốn.

### 18.3. Missing dependency

Nếu chạy:

~~~text
java.lang.NoClassDefFoundError: com/vendor/client/Client
~~~

cần xác định dependency chứa class đó có nằm ở runtime classpath khi build không và có được đưa vào `BOOT-INF/lib` không.

Một thư viện chỉ được khai báo `compileOnly` hoặc `testImplementation` không phải dependency runtime theo cấu hình thông thường.

### 18.4. Version conflict

Có thể gặp `NoSuchMethodError` dù class vẫn tồn tại. Một nguyên nhân là chương trình chạy với version thư viện khác version mà code được compile hoặc một dependency yêu cầu API không tương thích.

Hãy kiểm tra Gradle/Maven dependency resolution, dependency constraints và các dependency bị override. Không đổ lỗi ngay cho Boot loader khi thực chất là xung đột version.

### 18.5. Java runtime không tương thích

Ví dụ lỗi:

~~~text
UnsupportedClassVersionError
~~~

Bytecode đã được biên dịch cho Java version cao hơn runtime đang dùng, hoặc runtime không đáp ứng baseline của Spring Boot/framework.

Đối chiếu:

~~~bash
java -version
~~~

với build toolchain, target release và phiên bản Spring Boot.

### 18.6. Resource được truy cập như file vật lý

Code dùng `new File(resource.getURI())` có thể hoạt động trong IDE và lỗi trong JAR do resource nằm bên trong archive.

Dùng stream abstraction như `ClassLoader.getResourceAsStream(...)` hoặc Spring `Resource`, trừ khi thư viện đích yêu cầu file thật.

### 18.7. Component scan sai package

JAR vẫn khởi chạy được nhưng service/controller không được đăng ký vì lớp `@SpringBootApplication` ở sai package root hoặc module chưa import cấu hình.

Đây là vấn đề context composition, không phải `Main-Class`.

### 18.8. Port, database hoặc secret không sẵn sàng

Executable JAR có thể được đóng gói đúng nhưng ứng dụng vẫn thất bại vì:

- Cổng bị chiếm.
- Database không kết nối được.
- Thiếu environment variable/secret.
- File cấu hình ngoài artifact không tồn tại.
- Permission của filesystem không phù hợp.

Phân biệt **lỗi tạo archive**, **lỗi class loading** và **lỗi khởi tạo application context** để xử lý đúng tầng.

## 19. Bảng chẩn đoán lỗi đóng gói và khởi chạy

| Dấu hiệu | Tầng cần kiểm tra | Hành động |
|---|---|---|
| `no main manifest attribute` | Manifest/artifact type | Xác nhận đang dùng bootJar/repackaged JAR |
| `Could not find or load main class ...JarLauncher` | Manifest và loader classes | Kiểm tra launcher class/path và archive có bị sửa/corrupt không |
| `ClassNotFoundException` cho application class | Start-Class và BOOT-INF/classes | Kiểm tra class đã biên dịch, package và manifest |
| `NoClassDefFoundError` cho dependency | BOOT-INF/lib/runtime classpath | Kiểm tra dependency scopes và excludes |
| `NoSuchMethodError` | Dependency compatibility | Kiểm tra resolved versions và transitive dependency conflicts |
| `UnsupportedClassVersionError` | JVM/toolchain | Dùng Java runtime hỗ trợ bytecode và Boot version |
| Resource đọc được ở IDE nhưng không có trong JAR | processResources và BOOT-INF/classes | Kiểm tra source resource path và cách đọc classpath |
| `BeanCreationException` / `UnsatisfiedDependencyException` | Spring context/bean definitions | Kiểm tra component scan, auto-configuration và dependency injection |
| Server không nghe trên cổng dự kiến | Runtime config/embedded server | Kiểm tra `server.port`, profiles và lỗi khởi động |
| Chạy nhầm main class | Start-Class | Chỉ định mainClass và kiểm tra manifest |
| JAR hợp lệ nhưng Docker container thoát | Runtime/container environment | Kiểm tra JVM, entrypoint, ports, env, logs và external services |
| File quá lớn hoặc có dependency không cần thiết | Build dependency graph | Loại bỏ transitive dependency dư thừa bằng cấu hình có chủ đích |
| Archive có `BOOT-INF/lib` nhưng dùng lệnh `java -cp` | Launch strategy | Dùng `java -jar` để chạy qua Boot launcher |

## 20. Kiểm tra dependency graph của Maven và Gradle

Trước khi đóng gói, hoặc khi điều tra runtime error, xem dependency resolution bằng lệnh của build tool.

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Nếu cần xem một dependency cụ thể:

~~~bash
./gradlew dependencyInsight \
    --configuration runtimeClasspath \
    --dependency spring-core
~~~

Maven:

~~~bash
./mvnw dependency:tree
~~~

Các lệnh này cho thấy graph mà build tool giải quyết. Nhưng để xác nhận **artifact phát hành**, vẫn cần so với danh sách JAR thực tế bên trong `BOOT-INF/lib`. Custom packaging settings, task exclusions và artifact transformations có thể thay đổi đầu ra.

### 20.1. Có cần đóng gói mọi dependency trong JAR?

Không phải mọi dependency của toàn bộ project đều cần có trong runtime artifact:

- Unit-test libraries không cần hiện diện trong production JAR.
- Annotation processors là build-time tools, không phải runtime dependencies thông thường.
- Compile-only dependencies không nên được giả định có mặt lúc chạy.
- Embedded server dependencies phụ thuộc loại ứng dụng và kiểu JAR/WAR.
- Một dependency được provided bởi container ngoài có thể cần packaging khác.

Mục tiêu là chứa **đúng những thư viện cần thiết** để chạy artifact theo deployment model đã chọn, không phải nhét mọi thư viện của repository vào một ZIP lớn.

## 21. Security và vận hành executable JAR

Executable JAR là artifact chứa bytecode, resources và dependencies. Do đó cần coi nó như một phần của software supply chain.

### 21.1. Không đưa secret vào application resources

Nếu đặt password trong:

~~~text
src/main/resources/application-prod.yml
~~~

nó có thể nằm dưới:

~~~text
BOOT-INF/classes/application-prod.yml
~~~

trong JAR phát hành. Người có file JAR thường có thể liệt kê và giải nén nội dung. **JAR không phải kho lưu secret được mã hóa**.

Hãy cấp secret từ environment, mounted secret files hoặc secret manager theo chính sách triển khai.

### 21.2. Theo dõi dependency versions

Mỗi nested JAR là một dependency có version và có thể có lỗ hổng bảo mật. Nên có:

- Dependency update policy.
- Kiểm tra vulnerability/dependency scanning phù hợp.
- Kiểm soát nguồn artifact và repository tin cậy.
- Quy trình build có thể tái lập ở mức hợp lý.
- Lưu lại thông tin version và provenance khi phát hành.

Tên file trong `BOOT-INF/lib` có thể giúp nhận diện version, nhưng với một số JAR được rename hoặc repackaged, nên kết hợp với dependency graph và metadata build để hiểu chính xác thành phần.

### 21.3. Không sửa trực tiếp JAR sau khi build

Sửa manifest hoặc thêm JAR vào `BOOT-INF/lib` thủ công sau khi build có thể làm index, chữ ký, checksums hoặc reproducibility không còn đúng.

Nếu cần thêm dependency hoặc đổi main class, nên thay build configuration rồi tạo lại archive bằng plugin phù hợp. Sửa trực tiếp artifact chỉ nên dành cho tình huống chuyên biệt có quy trình kiểm soát kỹ thuật rõ ràng.

## 22. Quy trình phát hành từ source đến runtime

Có thể dùng sơ đồ tổng thể:

~~~text
Source code + application resources
                  |
                  v
Maven / Gradle resolve dependencies
                  |
                  v
Compile main application classes
                  |
                  v
Process resources
                  |
                  v
Spring Boot packaging plugin
                  |
       +----------+-----------+
       |                      |
       v                      v
META-INF/MANIFEST.MF      Executable JAR layout
 Main-Class=Launcher        BOOT-INF/classes
 Start-Class=App            BOOT-INF/lib
       |                      |
       +----------+-----------+
                  |
                  v
        catalog-service.jar
                  |
                  v
        java -jar catalog-service.jar
                  |
                  v
             Boot launcher
                  |
                  v
       CatalogApplication.main
                  |
                  v
         SpringApplication.run
                  |
                  v
          ApplicationContext
                  |
                  v
         Web server / runners
~~~

Một quy trình kiểm tra artifact có thể đi theo thứ tự:

1. Xác định main class mà ứng dụng muốn chạy.
2. Kiểm tra build plugin tạo executable archive.
3. Kiểm tra archive filename và artifact type.
4. Đọc manifest: `Main-Class` và `Start-Class`.
5. Liệt kê `BOOT-INF/classes` và `BOOT-INF/lib`.
6. Chạy bằng Java runtime tương thích.
7. Kiểm tra runtime configuration và kết quả startup.
8. Dùng log/health check phù hợp để xác định ứng dụng đã sẵn sàng.

STEP kiểm tra này là minh họa workflow cho người học, không phải yêu cầu mỗi dự án phải chạy lại toàn bộ pipeline trong lúc đang đọc tài liệu.

## 23. Những hiểu nhầm dễ gặp

| Hiểu nhầm | Cách hiểu chính xác |
|---|---|
| “`@SpringBootApplication` tự tạo executable JAR.” | Annotation cấu hình bootstrap; build plugin tạo archive. |
| “`Main-Class` phải là class chứa `@SpringBootApplication`.” | Với Boot executable JAR thông thường, `Main-Class` là Boot launcher; `Start-Class` là application main. |
| “`java -jar` tự đọc được mọi JAR lồng nhau.” | Boot launcher/loader xử lý nested dependencies; Java classpath chuẩn không tự làm vậy. |
| “Có JAR là chắc chắn chạy độc lập.” | Plain JAR có thể thiếu main manifest/dependencies. |
| “`bootRun` thành công nghĩa là `bootJar` chắc chắn đúng.” | Hai cách chạy dùng cơ chế classpath/artifact khác nhau. |
| “Dependencies trong IDE đều nằm trong `BOOT-INF/lib`.” | Phụ thuộc scope, runtime graph và packaging configuration. |
| “File `application.yml` nằm cạnh JAR.” | File được đóng gói thường nằm trong `BOOT-INF/classes`; external config là nguồn riêng. |
| “JAR có thể bảo vệ password vì không đọc được source.” | JAR là archive có thể liệt kê/giải nén, không phải secret store. |
| “Đổi tên plain JAR thành app.jar là sẽ chạy.” | Tên file không tạo loader, manifest hay nested dependencies. |
| “Dự án Spring Boot nào cũng cần executable WAR.” | Executable JAR thường là lựa chọn đơn giản cho ứng dụng chạy độc lập. |

## 24. Nguyên tắc ghi nhớ

1. **Main method** là điểm vào Java của ứng dụng, thường gọi `SpringApplication.run(...)`.
2. **Manifest** là metadata để Java launcher biết class đầu tiên cần chạy.
3. Trong **Spring Boot executable JAR**, `Main-Class` thường là Boot launcher, còn `Start-Class` là main class của ứng dụng.
4. `BOOT-INF/classes` chứa application bytecode và resources; `BOOT-INF/lib` chứa các nested runtime JARs.
5. **Boot loader** là thành phần nối Java launcher với layout nested dependencies.
6. `bootJar` (Gradle) hoặc `spring-boot-maven-plugin:repackage` (Maven) tạo executable archive; `jar` thông thường có thể tạo plain JAR.
7. **Runtime dependency graph** quyết định những thư viện được đóng gói theo plugin/configuration; test và compile-only dependencies không nên bị mặc định coi là runtime.
8. Dùng `java -jar` cho executable archive, không dùng `java -cp app.jar ApplicationMain` như một sự thay thế trực tiếp.
9. Khi có nhiều main classes, **chỉ định rõ mainClass** và kiểm tra `Start-Class` trong manifest.
10. Kiểm tra **archive thực tế** bằng `jar tf`, manifest và danh sách `BOOT-INF/lib`; không chỉ dựa vào tên file.
11. **Plain JAR, executable JAR, shaded JAR và WAR** có layout/mục tiêu khác nhau.
12. Tài nguyên classpath trong JAR thường không thể dùng trực tiếp như `java.io.File`; ưu tiên stream/`Resource`.
13. **JAR không chứa an toàn secret chỉ vì nó được nén**; dùng externalized configuration và secret injection.
14. Nếu lỗi lúc chạy, phân biệt rõ lỗi manifest/launcher, thiếu dependency, Java version và lỗi Spring context.

**Kết luận:** Để hiểu cách Spring Boot chạy ngoài IDE, hãy nhìn executable JAR như một gói có **lớp main ứng dụng, manifest chỉ đường cho JVM, Boot loader và runtime dependencies được bố trí ở các vị trí riêng**. JVM đọc `Main-Class` để khởi động launcher; launcher tìm `Start-Class` và thiết lập classpath cho `BOOT-INF/classes` cùng `BOOT-INF/lib`; ứng dụng sau đó gọi `SpringApplication.run(...)` để tạo Spring context. Khi nắm được chuỗi này, việc đóng gói, triển khai và chẩn đoán lỗi `java -jar` sẽ trở nên rõ ràng hơn nhiều.

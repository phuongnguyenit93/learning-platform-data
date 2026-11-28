# Khai báo spring-boot-starter-data-neo4j và quản lý dependency

Spring Data Neo4j (SDN) cung cấp mô hình entity, repository và cơ chế ánh xạ giữa Java object với node, relationship trong Neo4j. Trong một ứng dụng Spring Boot, cách khởi đầu thông dụng là khai báo starter có tọa độ:

~~~text
org.springframework.boot:spring-boot-starter-data-neo4j
~~~

Starter tập hợp các dependency cần thiết để tích hợp Spring Data Neo4j với Spring Boot, bao gồm Spring Data Neo4j và Neo4j Java Driver tương ứng với bộ phiên bản mà Spring Boot quản lý. Nhờ vậy, ứng dụng có thể sử dụng repository và cấu hình tự động của Spring Boot mà không phải tự ghép từng thư viện nền tảng.

Bài học này trình bày cách khai báo starter bằng Maven và Gradle, cách để Spring Boot quản lý phiên bản thư viện, và cách kiểm tra dependency sau khi thêm vào dự án.

## 1. Chọn phiên bản Spring Boot trước khi thêm starter

Starter thuộc hệ sinh thái Spring Boot. Phiên bản của nó cần đi cùng phiên bản Spring Boot mà dự án đang sử dụng. Spring Boot cung cấp một bộ phiên bản đã được kiểm thử và quản lý qua Spring Boot dependency management (BOM). BOM này cũng quản lý phiên bản của Spring Data và nhiều thư viện nền tảng khác.

Khi tạo dự án mới, hãy xác định:

- Phiên bản Spring Boot phù hợp với JDK và nền tảng triển khai.
- Phiên bản Neo4j Server mà ứng dụng sẽ kết nối.
- Công cụ build mà dự án sử dụng: Maven hay Gradle.

Sau đó chọn phiên bản Spring Boot có hỗ trợ JDK của dự án và kiểm tra ma trận tương thích giữa Neo4j Java Driver với Neo4j Server. Driver thường được quản lý gián tiếp qua BOM của Spring Boot; không nên tự chọn một phiên bản driver khác chỉ vì đó là phiên bản mới nhất.

Không trộn các phiên bản Spring Boot, Spring Data Neo4j và Neo4j Java Driver một cách tùy tiện. Việc ghi đè dependency có thể gây lỗi liên kết lúc chạy, ví dụ NoSuchMethodError hoặc NoClassDefFoundError, dù dự án vẫn biên dịch thành công.

## 2. Khai báo dependency với Maven

### 2.1. Dùng Spring Boot parent

Nếu dự án có thể kế thừa từ Spring Boot parent, khai báo parent trong pom.xml. Thay giá trị phiên bản minh họa bằng một phiên bản Spring Boot đã được dự án lựa chọn:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.x.y</version>
    <relativePath/>
</parent>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-neo4j</artifactId>
    </dependency>
</dependencies>
~~~

Điểm cần chú ý là dependency starter không khai báo thẻ version. Spring Boot parent đã nhập BOM và cung cấp dependency management, vì vậy Maven tự chọn phiên bản phù hợp với bộ phiên bản của Spring Boot đang dùng.

Nếu dự án đã có một parent POM của tổ chức và không thể khai báo thêm parent, không thể đặt hai phần tử parent trong cùng một POM. Khi đó, dùng cách nhập BOM ở phần tiếp theo.

### 2.2. Nhập Spring Boot BOM khi không dùng Spring Boot parent

Một POM chỉ có thể kế thừa trực tiếp một parent. Với dự án có parent riêng, có thể nhập BOM của Spring Boot trong dependencyManagement. Ví dụ:

~~~xml
<properties>
    <spring-boot.version>3.x.y</spring-boot.version>
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
        <artifactId>spring-boot-starter-data-neo4j</artifactId>
    </dependency>
</dependencies>
~~~

Giá trị 3.x.y là chỗ giữ chỗ trong ví dụ; hãy thay bằng phiên bản Spring Boot thực tế của dự án. BOM được nhập với scope import và type pom. Từ đó, các dependency được BOM quản lý có thể bỏ thẻ version trong phần dependencies.

Nếu dự án cần đóng gói và chạy theo quy ước Spring Boot, có thể cấu hình spring-boot-maven-plugin trong build/plugins. Plugin đóng gói ứng dụng và BOM quản lý phiên bản dependency là hai vai trò liên quan nhưng khác nhau.

### 2.3. Dự án Maven nhiều module

Trong dự án nhiều module, nên đặt phiên bản Spring Boot và phần nhập BOM tại POM cha dùng chung. Module cần truy cập Neo4j chỉ khai báo starter:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-neo4j</artifactId>
    </dependency>
</dependencies>
~~~

Cách tổ chức này giúp các module dùng chung một bộ phiên bản, giảm nguy cơ mỗi module kéo vào một phiên bản Spring Data hoặc Neo4j Driver khác nhau.

## 3. Khai báo dependency với Gradle

Gradle có thể dùng Spring Boot plugin cùng BOM của Spring Boot để quản lý dependency. Ví dụ với build.gradle dùng Groovy DSL:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.x.y'
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.x.y')
    implementation 'org.springframework.boot:spring-boot-starter-data-neo4j'
}
~~~

Thay cả hai giá trị 3.x.y bằng cùng phiên bản Spring Boot đã chọn. Dòng platform nhập BOM vào cấu hình dependency của Gradle; starter nhờ đó nhận phiên bản được BOM quản lý. Nếu dự án đã có cơ chế dependency management do convention plugin hoặc nền tảng nội bộ cung cấp, hãy kiểm tra cơ chế đó trước khi nhập thêm BOM.

Với Kotlin DSL trong build.gradle.kts, cú pháp tương ứng là:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "3.x.y"
}

dependencies {
    implementation(platform("org.springframework.boot:spring-boot-dependencies:3.x.y"))
    implementation("org.springframework.boot:spring-boot-starter-data-neo4j")
}
~~~

Có thể khai báo phiên bản BOM trong một biến dùng chung của build logic hoặc version catalog để tránh lặp lại. Điều quan trọng là phiên bản plugin Spring Boot và BOM cần được quản lý nhất quán.

## 4. Starter cung cấp những gì?

Khi thêm spring-boot-starter-data-neo4j, dự án nhận các thư viện nền tảng cần cho tích hợp SDN. Các thành phần thường gặp gồm:

| Thành phần | Vai trò |
| --- | --- |
| Spring Data Neo4j | Ánh xạ node và relationship, cung cấp repository abstraction và hỗ trợ truy vấn Cypher |
| Neo4j Java Driver | Tạo kết nối và trao đổi dữ liệu với Neo4j Server qua giao thức Bolt |
| Spring Boot auto-configuration | Tự cấu hình các thành phần Neo4j dựa trên dependency và thuộc tính ứng dụng |
| Spring Boot starter dependencies | Cung cấp các thành phần Spring cần thiết để ứng dụng hoạt động |

Vì starter đã kéo các dependency nền tảng theo bộ phiên bản tương thích, ứng dụng thông thường không cần khai báo riêng spring-data-neo4j hoặc neo4j-java-driver. Chỉ thêm trực tiếp một thư viện riêng khi có yêu cầu kỹ thuật cụ thể và đã xác minh tính tương thích.

Starter chỉ giải quyết việc đưa thư viện vào classpath và kích hoạt cơ chế cấu hình tự động phù hợp. Nó không tự cài đặt Neo4j Server, không tạo database cho ứng dụng và không thay thế cấu hình địa chỉ kết nối hoặc thông tin xác thực.

## 5. Cấu hình kết nối sau khi thêm starter

Sau khi dependency đã có trong dự án, ứng dụng cần biết địa chỉ Neo4j và cách xác thực. Ví dụ application.yml:

~~~yaml
spring:
  neo4j:
    uri: bolt://localhost:7687
    authentication:
      username: neo4j
      password: ${NEO4J_PASSWORD}
~~~

Địa chỉ bolt://localhost:7687 là ví dụ cho Neo4j đang chạy trên cùng máy và dùng cổng Bolt mặc định. Thay URI theo môi trường thực tế, chẳng hạn máy chủ phát triển, môi trường kiểm thử hoặc dịch vụ Neo4j được quản lý.

Đặt mật khẩu trong biến môi trường NEO4J_PASSWORD hoặc kho bí mật của môi trường triển khai. Không commit mật khẩu thật vào mã nguồn hay file cấu hình được chia sẻ. Nếu cấu hình xác thực không đúng, dependency vẫn có thể được resolve và ứng dụng vẫn có thể biên dịch, nhưng kết nối sẽ thất bại khi ứng dụng truy cập Neo4j.

## 6. Kiểm tra dependency đã được resolve

Sau khi chỉnh sửa build file, hãy tải dependency và kiểm tra cây dependency.

Với Maven:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.springframework.data:spring-data-neo4j,org.neo4j.driver:neo4j-java-driver
mvn clean test
~~~

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-data-neo4j --configuration runtimeClasspath
./gradlew dependencyInsight --dependency neo4j-java-driver --configuration runtimeClasspath
./gradlew test
~~~

Hãy xác nhận starter xuất hiện trong runtime classpath, Spring Data Neo4j và Neo4j Java Driver được resolve về phiên bản dự kiến, đồng thời không có dependency conflict ngoài ý muốn. Trên Windows, có thể dùng mvnw.cmd hoặc gradlew.bat tương ứng với wrapper của dự án.

Kiểm tra dependency tree không chứng minh rằng Neo4j Server có thể truy cập. Sau khi build thành công, cần chạy ứng dụng trong môi trường có Neo4j và xác minh kết nối bằng một thao tác truy cập dữ liệu phù hợp.

## 7. Các lỗi khai báo thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Maven báo thiếu version cho starter | POM chưa kế thừa Spring Boot parent hoặc chưa nhập BOM | Kiểm tra parent và dependencyManagement |
| Gradle không resolve được dependency | Sai tọa độ artifact, repository hoặc cấu hình BOM | Kiểm tra group, artifact, phiên bản plugin và repository |
| Spring Data Neo4j hoặc driver có phiên bản bất ngờ | Có dependency khác ghi đè hoặc nhiều BOM quản lý cùng thư viện | Xem dependency tree và loại bỏ override không cần thiết |
| Build thành công nhưng ứng dụng không kết nối được | URI, cổng, thông tin xác thực hoặc trạng thái Neo4j Server chưa đúng | Kiểm tra cấu hình spring.neo4j và khả năng truy cập server |
| Lỗi NoSuchMethodError hoặc NoClassDefFoundError | Các thư viện Spring Data, Spring Framework hoặc Neo4j Driver không tương thích | Dùng bộ phiên bản do cùng một Spring Boot BOM quản lý, sau đó kiểm tra lại dependency tree |

Tránh thêm đồng thời nhiều phiên bản của cùng thư viện bằng cách khai báo starter rồi lại khai báo một phiên bản Spring Data Neo4j hoặc Neo4j Driver riêng mà không có lý do rõ ràng. Nếu cần ghi đè phiên bản vì một yêu cầu tương thích đã xác định, hãy ghi lại lý do, kiểm tra ma trận tương thích và chạy kiểm thử tích hợp với Neo4j Server mục tiêu.

## 8. Bài tập tự kiểm tra

1. Tìm tọa độ Maven của starter dùng để tích hợp Spring Data Neo4j với Spring Boot.
2. Trong Maven, giải thích sự khác nhau giữa kế thừa spring-boot-starter-parent và nhập spring-boot-dependencies BOM.
3. Vì sao dependency starter thông thường không cần khai báo thẻ version khi BOM đã được cấu hình?
4. Trong Gradle, platform có vai trò gì khi nhập Spring Boot BOM?
5. Dùng dependency tree để xác định phiên bản spring-data-neo4j và neo4j-java-driver mà dự án thực sự sử dụng.
6. Giải thích vì sao thêm starter thành công chưa có nghĩa ứng dụng đã kết nối được Neo4j Server.

Khi hoàn thành bài học, bạn cần có thể thêm đúng starter vào Maven hoặc Gradle, để Spring Boot quản lý phiên bản thư viện một cách nhất quán và xác minh được dependency đã resolve trước khi chuyển sang cấu hình entity, repository và truy vấn Cypher.

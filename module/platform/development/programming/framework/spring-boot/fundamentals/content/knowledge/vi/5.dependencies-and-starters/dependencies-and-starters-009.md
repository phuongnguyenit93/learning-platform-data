# Đọc dependency tree để tìm xung đột hoặc thư viện bị kéo vào ngoài dự kiến

Trong Spring Boot, khai báo một starter thường rất ngắn, nhưng thư viện thực sự được sử dụng có thể gồm hàng chục hoặc hàng trăm artifact. Một dòng khai báo `spring-boot-starter-web` có thể kéo theo Spring MVC, thư viện xử lý JSON, logging và embedded web server; một dòng `spring-boot-starter-data-jpa` có thể kéo theo Spring Data, Hibernate, các API liên quan đến persistence và transaction.

Khi ứng dụng gặp `NoSuchMethodError`, `ClassNotFoundException`, xung đột logging, thay đổi hành vi sau khi cập nhật phiên bản, hoặc xuất hiện một thư viện không mong muốn trong bản đóng gói, điều quan trọng là tìm được **đường dẫn từ dependency khai báo trực tiếp đến artifact đang gây vấn đề**. Công cụ hữu ích nhất để bắt đầu là **dependency tree**.

Bài này hướng dẫn cách đọc cây dependency của dự án Spring Boot dùng **Maven** hoặc **Gradle**, phân biệt dependency trực tiếp và gián tiếp, hiểu các ký hiệu chọn phiên bản, tìm thư viện bị kéo vào ngoài dự kiến và xử lý xung đột có kiểm soát.

## 1. Dependency tree cho ta biết điều gì?

**Dependency** là một thư viện hoặc thành phần được dự án sử dụng trong quá trình biên dịch, chạy hay kiểm thử. Dependency có thể được khai báo trực tiếp hoặc được kéo vào thông qua một dependency khác:

- **Direct dependency**: được dự án khai báo trong `pom.xml` hoặc `build.gradle`/`build.gradle.kts`.
- **Transitive dependency**: thư viện mà một dependency khác cần, nên trình quản lý dependency đưa vào đồ thị.
- **Resolved dependency**: phiên bản artifact sau khi Maven hoặc Gradle áp dụng quy tắc quản lý phiên bản, giải quyết xung đột, scope/configuration và các điều kiện liên quan.
- **Classpath**: tập các lớp và tài nguyên được trình biên dịch, JVM hoặc một tác vụ cụ thể sử dụng. Một dự án có thể có nhiều classpath khác nhau.

Ví dụ minh họa (không phải output nguyên văn của một phiên bản Spring Boot cụ thể):

~~~text
bookstore
└── spring-boot-starter-web
    ├── spring-boot-starter
    │   └── spring-boot-starter-logging
    ├── spring-web
    ├── spring-webmvc
    └── spring-boot-starter-tomcat
~~~

Nhìn vào cây, ta biết `spring-webmvc` hoặc `spring-boot-starter-tomcat` có thể có mặt do `spring-boot-starter-web` kéo vào. Nếu cần tìm “ai thêm Tomcat?”, câu trả lời nằm ở **nhánh cha**, không chỉ ở tên thư viện cuối cùng.

Cần phân biệt ba câu hỏi:

1. **Ai yêu cầu thư viện này?** Đọc các nhánh dẫn từ dự án gốc đến artifact.
2. **Phiên bản cuối cùng là gì?** Đọc kết quả *resolution* và quy tắc quản lý phiên bản.
3. **Artifact có mặt trong ngữ cảnh đang lỗi không?** Kiểm tra đúng scope/configuration và classpath đang dùng, ví dụ runtime của ứng dụng thay vì classpath test.

Dependency tree là **hình ảnh của đồ thị phụ thuộc đã được công cụ tính toán**. Nó không thay thế việc kiểm tra bản JAR thực tế, thư viện do container cung cấp hoặc class được nạp động, nhưng thường là đầu mối nhanh và có giá trị nhất.

## 2. Vì sao starter khiến việc đọc dependency tree trở nên quan trọng?

Spring Boot cung cấp nhiều *starter* để đưa vào một nhóm thư viện theo nhu cầu:

| Starter thường gặp | Mục đích | Các nhóm thư viện có thể xuất hiện trong cây |
|---|---|---|
| `spring-boot-starter-web` | Xây dựng web ứng dụng dựa trên Spring MVC | Spring Web, Spring MVC, JSON, embedded servlet server |
| `spring-boot-starter-webflux` | Xây dựng ứng dụng reactive web | Spring WebFlux, Reactor và các thành phần liên quan |
| `spring-boot-starter-data-jpa` | Truy cập dữ liệu qua Spring Data JPA | Spring Data, Hibernate ORM, Spring ORM, JDBC, transaction |
| `spring-boot-starter-security` | Tích hợp Spring Security | Các module Spring Security phù hợp |
| `spring-boot-starter-validation` | Bean Validation | API và implementation validation |
| `spring-boot-starter-test` | Hỗ trợ kiểm thử | Spring Test, JUnit, Mockito và thư viện kiểm thử liên quan |

Thành phần chính xác và phiên bản có thể thay đổi theo phiên bản Spring Boot. Vì thế, thay vì học thuộc tên từng artifact phụ thuộc, hãy đọc **cây của chính dự án và phiên bản đang sử dụng**.

Một starter không tự chứng minh rằng một thành phần sẽ được Spring khởi tạo. Dependency tree xác nhận **lớp/thư viện có thể hiện diện**; còn auto-configuration của Spring Boot vẫn xét classpath, property, bean đã định nghĩa và nhiều điều kiện khác. Ví dụ, chỉ có driver JDBC trên classpath không có nghĩa kết nối database sẽ thành công.

## 3. Đọc dependency tree trong Maven

### 3.1. Ví dụ dự án Maven

Một dự án Spring Boot có thể khai báo dependency như sau, khi đã sử dụng Spring Boot parent hoặc cách quản lý phiên bản tương đương:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Để hiển thị đồ thị dependency, chạy trong thư mục chứa `pom.xml`:

~~~bash
./mvnw dependency:tree
~~~

Trên Windows PowerShell hoặc Command Prompt, với Maven Wrapper:

~~~powershell
.\mvnw.cmd dependency:tree
~~~

Nếu dự án dùng Maven cài đặt sẵn, có thể thay `./mvnw` bằng `mvn`.

Lệnh gọi goal `dependency:tree` từ Maven Dependency Plugin. Kết quả có thể khác nhau giữa các phiên bản Maven, plugin và cách khai báo dự án.

### 3.2. Phân tích một đoạn output

Ví dụ sau chỉ mô phỏng hình dạng kết quả; mã phiên bản `X.Y.Z` là placeholder, không đại diện cho một release thực tế:

~~~text
[INFO] com.example:bookstore:jar:1.0.0
[INFO] +- org.springframework.boot:spring-boot-starter-web:jar:X.Y.Z:compile
[INFO] |  +- org.springframework:spring-web:jar:A.B.C:compile
[INFO] |  +- org.springframework:spring-webmvc:jar:A.B.C:compile
[INFO] |  \- org.springframework.boot:spring-boot-starter-tomcat:jar:X.Y.Z:compile
[INFO] +- org.postgresql:postgresql:jar:P.Q.R:runtime
[INFO] \- org.springframework.boot:spring-boot-starter-test:jar:X.Y.Z:test
~~~

Mỗi dòng dependency Maven thường có dạng:

~~~text
groupId:artifactId:type:version:scope
~~~

Cũng có thể xuất hiện `classifier`, chẳng hạn `groupId:artifactId:type:classifier:version:scope`. Trong ví dụ:

- `org.springframework.boot` là **groupId** của starter.
- `spring-boot-starter-web` là **artifactId**.
- `jar` là loại artifact.
- `X.Y.Z` là phiên bản được giải quyết.
- `compile`, `runtime` và `test` thể hiện phạm vi Maven ở kết quả đó.
- `+-` và `\-` cùng với các dấu `|` và khoảng trắng biểu diễn quan hệ cha–con.

Cách đọc là đi **từ trái sang phải và từ trên xuống dưới**: `spring-webmvc` nằm dưới `spring-boot-starter-web` nên được đưa vào thông qua nhánh của starter này. Cấu trúc thụt dòng chính là “vì sao thư viện có mặt”.

### 3.3. Lọc một nhóm thư viện

Khi cây quá dài, có thể yêu cầu Maven hiển thị những nhánh liên quan đến một artifact:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework:spring-webmvc
~~~

Hoặc lọc theo group:

~~~bash
./mvnw dependency:tree -Dincludes=org.slf4j:*
~~~

Có thể giới hạn scope tùy mục tiêu:

~~~bash
./mvnw dependency:tree -Dscope=runtime
~~~

Lưu ý: filter tạo ra **góc nhìn hẹp của cây**, không chứng minh rằng những nhánh khác không tồn tại trong toàn bộ dự án. Khi điều tra lỗi, nên đọc cây đầy đủ ít nhất một lần và xác định chính xác scope cần tìm.

Trong một số phiên bản PowerShell, cách xử lý ký tự đặc biệt của shell và tham số `-D...` có thể khác với Bash. Khi cần, đặt cả đối số trong dấu nháy như `"-Dincludes=org.slf4j:*"` để chuyển nguyên giá trị cho Maven.

### 3.4. Đọc các nhánh bị bỏ qua khi xung đột

Maven có thể nhận nhiều yêu cầu về **cùng một artifact nhưng khác phiên bản**. Phiên bản thực sự được chọn có thể không trùng với một phiên bản nằm sâu trong cây khai báo của dependency trung gian.

Với phiên bản Maven Dependency Plugin hỗ trợ hiển thị nhánh bị loại, có thể dùng:

~~~bash
./mvnw dependency:tree -Dverbose
~~~

Ví dụ minh họa:

~~~text
com.example:bookstore:jar:1.0.0
+- com.example:payment-sdk:jar:2.0:compile
|  \- com.example:json-helper:jar:3.1:compile
\- com.example:legacy-client:jar:1.0:compile
   \- (com.example:json-helper:jar:2.5:compile - omitted for conflict with 3.1)
~~~

Điều này có nghĩa:

- `payment-sdk` yêu cầu `json-helper:3.1`.
- `legacy-client` yêu cầu `json-helper:2.5`.
- Maven chọn `3.1` trong tình huống ví dụ.
- Nhánh `2.5` được hiển thị để giải thích xung đột, **không có nghĩa cả hai phiên bản đều được nạp vào runtime classpath**.

Ký hiệu và khả năng hiển thị nhánh bị loại phụ thuộc phiên bản plugin. Nếu không thấy `omitted for conflict`, không nên kết luận rằng chắc chắn không có tranh chấp phiên bản: có thể cần xem cây với tùy chọn phù hợp, effective POM hoặc dữ liệu resolution khác.

### 3.5. Vì sao Maven chọn phiên bản đó?

Một nguyên tắc nền tảng của Maven là **nearest definition**: trong xung đột transitive dependency thông thường, đường dẫn từ dự án gốc đến phiên bản ngắn hơn thường được ưu tiên. Nếu độ sâu bằng nhau, thứ tự khai báo có thể quyết định phiên bản được chọn trước. Tuy nhiên, `dependencyManagement` có thể quản lý/ghi đè phiên bản phụ thuộc và thay đổi kết quả; dependency khai báo trực tiếp cũng có tác động rõ rệt.

Ví dụ giả định:

~~~text
bookstore
├── module-a
│   └── library-x:2.0
└── module-b
    └── module-c
        └── library-x:1.0
~~~

Nếu không có quy tắc quản lý phiên bản ảnh hưởng, `library-x:2.0` ở nhánh ngắn hơn có khả năng được chọn. Nhưng nếu dự án quản lý `library-x` qua BOM hoặc `dependencyManagement`, phải xem **kết quả thực tế** thay vì tự suy ra từ độ sâu cây.

Trong dự án Spring Boot, parent POM hoặc `spring-boot-dependencies` BOM thường quản lý phiên bản của nhiều thư viện quan trọng. Một starter không ghi số phiên bản ở `pom.xml` không có nghĩa Maven tự chọn tùy ý; phiên bản thường được cung cấp thông qua cơ chế quản lý này.

## 4. Đọc dependency tree trong Gradle

### 4.1. Ví dụ dự án Gradle

Ví dụ với Groovy DSL trong `build.gradle`, giả định plugin Spring Boot và cơ chế quản lý dependency đã được cấu hình phù hợp:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Khác Maven, Gradle dùng các **configuration** để xác định nơi dependency được sử dụng. Một số configuration phổ biến trong dự án Java:

| Configuration | Ý nghĩa thực tế |
|---|---|
| `implementation` | Dependency dùng để biên dịch và chạy mã chính, không phơi bày như API công khai của thư viện Java |
| `api` | Dùng với plugin `java-library` để biểu thị dependency thuộc API công khai |
| `compileOnly` | Có trên compile classpath nhưng không tự được đưa vào runtime |
| `runtimeOnly` | Cần lúc chạy, không cần khi biên dịch mã chính |
| `testImplementation` | Dependency cho việc biên dịch/chạy test theo cấu hình test |
| `testRuntimeOnly` | Dependency chỉ cần khi chạy test |
| `runtimeClasspath` | Classpath đã giải quyết cho runtime của mã chính |
| `testRuntimeClasspath` | Classpath đã giải quyết cho runtime kiểm thử |

Nếu lỗi chỉ xuất hiện khi chạy ứng dụng, điều tra `runtimeClasspath` thường có ích hơn việc chỉ nhìn danh sách `implementation`. Nếu lỗi chỉ xuất hiện trong test, cần xem `testRuntimeClasspath`.

### 4.2. Hiển thị cây của một classpath cụ thể

Trên hệ điều hành kiểu Unix:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Trên Windows:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
~~~

Đối với test:

~~~bash
./gradlew dependencies --configuration testRuntimeClasspath
~~~

Kết quả phụ thuộc vào phiên bản Gradle, plugin, configuration và các constraint được khai báo. Đoạn sau chỉ minh họa định dạng:

~~~text
runtimeClasspath - Runtime classpath of source set 'main'.
+--- com.example:feature-a:1.0
|    \--- com.example:shared-lib:1.5 -> 2.1
+--- com.example:feature-b:3.0
|    \--- com.example:shared-lib:2.1
\--- org.springframework.boot:spring-boot-starter-web:...
~~~

Dòng `com.example:shared-lib:1.5 -> 2.1` cho biết nhánh đó yêu cầu `1.5` nhưng **phiên bản được chọn là `2.1`**. Đây là thông tin trọng tâm khi tìm xung đột. Nhìn vào phiên bản bên trái mũi tên mà kết luận ứng dụng đang chạy `1.5` là sai.

Gradle có thể hiển thị các ký hiệu như:

- `->`: phiên bản hoặc target được giải quyết khác với yêu cầu ban đầu.
- `(*)`: nhánh dependency đã được trình bày ở nơi khác trong báo cáo và không mở rộng lặp lại.
- `(c)`: dòng liên quan tới dependency constraint.
- `(n)`: dependency hoặc configuration chưa được giải quyết theo cách đang hiển thị.

Các ký hiệu có thể thay đổi theo phiên bản Gradle. Hãy xem chú giải ngay cuối output và đối chiếu với phiên bản Gradle của dự án.

### 4.3. Truy vấn một dependency cụ thể bằng dependencyInsight

Khi đã biết artifact nghi vấn, `dependencyInsight` giúp xác định **ai yêu cầu nó** và **vì sao Gradle chọn phiên bản đang dùng**:

~~~bash
./gradlew dependencyInsight \
  --dependency com.example:shared-lib \
  --configuration runtimeClasspath
~~~

Trên PowerShell, có thể viết một dòng:

~~~powershell
.\gradlew.bat dependencyInsight --dependency com.example:shared-lib --configuration runtimeClasspath
~~~

Kết quả thường có thể nêu các đường dẫn yêu cầu khác nhau và *selection reason* như do conflict resolution, constraint, rule hoặc một dạng quy tắc chọn phiên bản khác. Kết quả cụ thể phụ thuộc cấu hình Gradle.

Ví dụ tình huống giả định: `feature-a` yêu cầu `shared-lib:1.5`, `feature-b` yêu cầu `2.1`. Nếu Gradle giải quyết chọn `2.1`, `dependencyInsight` giúp ta thấy hai yêu cầu và nguyên nhân chọn. Đây là một khác biệt quan trọng với việc chỉ đọc file `build.gradle`, nơi không nhất thiết khai báo trực tiếp `shared-lib`.

**Lưu ý:** Gradle mặc định thường chọn phiên bản cao nhất khi giải quyết xung đột phiên bản động/transitive, nhưng constraint, platform/BOM, strict version, force, metadata và resolution rule có thể làm thay đổi kết quả. Đừng suy ra phiên bản thực tế chỉ dựa vào quy tắc chung; hãy xem output resolution.

## 5. Đọc đúng phạm vi: dependency có thể xuất hiện ở test nhưng không có lúc chạy

Một lỗi phổ biến là xem thấy thư viện trong dependency tree rồi cho rằng sản phẩm triển khai nhất định chứa nó.

### Maven scope

| Scope | Ý nghĩa thường gặp | Tác động đến điều tra |
|---|---|---|
| `compile` | Khả dụng ở compile và các classpath liên quan | Có thể góp mặt trong runtime artifact tùy cách đóng gói |
| `runtime` | Cần khi chạy nhưng không nhất thiết để biên dịch | Phù hợp với JDBC driver chỉ cần lúc chạy |
| `test` | Dành cho kiểm thử | Không nên kỳ vọng xuất hiện trong JAR ứng dụng thông thường |
| `provided` | Có khi biên dịch nhưng kỳ vọng runtime/container cung cấp | Có thể gây thiếu lớp nếu môi trường thực tế không cung cấp |
| `system` | Trỏ tới JAR cục bộ bằng đường dẫn cụ thể | Thường làm build khó tái lập; không nên là lựa chọn thông thường |
| `import` | Sử dụng trong `dependencyManagement` với BOM loại POM | Quản lý phiên bản, không tự có nghĩa là thư viện runtime |

Scope chịu các quy tắc truyền dẫn dependency của Maven, do đó scope ở kết quả cây có thể là kết quả của quan hệ giữa scope cha và con, không đơn giản sao chép mọi khai báo gốc.

### Gradle configuration

Trong Gradle, `implementation` không có nghĩa “tất cả dependency loại này đều có trên mọi classpath”. Hãy hỏi chính xác configuration nào đã được giải quyết:

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
~~~

Nếu dependency chỉ nằm trong `testRuntimeClasspath`, đừng dùng sự hiện diện của nó để giải thích hành vi của bản ứng dụng production. Ngược lại, một thư viện thiếu ở `runtimeClasspath` có thể gây `NoClassDefFoundError` dù mã biên dịch trước đó thành công nhờ `compileOnly` hoặc sự khác biệt của môi trường build.

## 6. Tìm một thư viện bị kéo vào ngoài dự kiến

Giả sử dự án Spring Boot dự định sử dụng WebFlux với Reactor Netty, nhưng khi xem dependency tree lại thấy embedded Tomcat. Hoặc dự án định dùng một logging stack nhưng xuất hiện thêm binding không mong muốn. Quy trình tìm nguyên nhân không bắt đầu bằng cách xóa ngẫu nhiên dependency; cần lần theo nhánh kéo artifact đó vào.

### Bước 1: xác định artifact cụ thể

Tên thư viện ở log có thể không trùng hoàn toàn với tên dependency. Ví dụ:

- Lỗi logging nhắc `SLF4J`: tìm group và artifact tương ứng với các provider/binding.
- Log nhắc `Tomcat`: tìm những artifact thuộc Tomcat và những starter web có thể kéo chúng vào.
- Lỗi Jackson: tìm `jackson-databind`, `jackson-core` và các module liên quan.
- Lỗi Java class: xác định class thuộc artifact nào trước khi lọc.

Nếu chưa biết artifact, nhìn cây đầy đủ hoặc tra metadata của thư viện liên quan. Đừng đoán tên groupId từ tên Java package mà chưa xác nhận.

### Bước 2: tìm đường đưa artifact vào

Trong Maven:

~~~bash
./mvnw dependency:tree -Dincludes=org.apache.tomcat.embed:*
~~~

Trong Gradle:

~~~bash
./gradlew dependencyInsight --dependency tomcat-embed-core --configuration runtimeClasspath
~~~

Ví dụ một đường dẫn khái niệm:

~~~text
bookstore
└── spring-boot-starter-web
    └── spring-boot-starter-tomcat
        └── tomcat-embed-core
~~~

Từ đó, thư viện Tomcat không “tự xuất hiện”: nó đến từ starter web. Nếu dự án sử dụng `spring-boot-starter-web` có chủ đích, Tomcat có thể hoàn toàn là dependency dự kiến. Nếu dự án chỉ muốn WebFlux/Netty, cần xem lại starter được thêm hoặc nhánh mang nó vào.

### Bước 3: kiểm tra cấu hình thực tế

Có trường hợp cùng một thư viện xuất hiện trên **test classpath** nhưng không có trên **runtime classpath**; có trường hợp project phụ đóng góp dependency; có trường hợp BOM chỉ quản lý phiên bản chứ không kéo artifact vào. Vì vậy cần xác định đúng configuration/scope và phân biệt “được yêu cầu”, “được chọn” và “được đưa vào artifact”.

### Bước 4: xác định tác động trước khi loại bỏ

Một transitive dependency có thể là phần thiết yếu của thư viện cha. Loại bỏ `tomcat-embed-core` khỏi web starter servlet mà không thay bằng embedded server phù hợp có thể làm ứng dụng không khởi động HTTP server. Loại một provider logging cần xem liệu còn implementation logging hoạt động không. Loại một Jackson module có thể làm thay đổi việc tuần tự hóa kiểu dữ liệu tương ứng.

Do đó, cần tìm **đường dẫn đưa thư viện vào và vai trò của nó** trước khi thêm exclusion.

## 7. Xung đột phiên bản: dấu hiệu và cách phân tích

Hai dependency có thể yêu cầu những phiên bản khác nhau của cùng một artifact:

~~~text
bookstore
├── payment-sdk:2.0
│   └── shared-json:3.2
└── inventory-client:1.4
    └── shared-json:2.7
~~~

Trong quá trình resolution thông thường, Maven/Gradle sẽ chọn một phiên bản cho tọa độ module tương ứng theo cơ chế của mình. Phiên bản được chọn có thể không tương thích nhị phân với một thư viện đã biên dịch dựa trên phiên bản khác.

### Dấu hiệu thường gặp

| Triệu chứng | Một nguyên nhân liên quan tới dependency có thể xảy ra | Kiểm tra tiếp |
|---|---|---|
| `java.lang.NoSuchMethodError` | Mã gọi phương thức không có trong phiên bản thư viện được nạp | Xem runtime classpath và phiên bản artifact chứa phương thức |
| `java.lang.NoClassDefFoundError` | Class cần thiết không có khi runtime hoặc không khởi tạo được | Kiểm tra classpath, scope và nguyên nhân lồng bên trong |
| `ClassNotFoundException` | Class được yêu cầu nạp động nhưng không tìm thấy | Tìm artifact cung cấp class và xem classpath runtime |
| `NoSuchFieldError` | Phiên bản class lúc chạy khác kỳ vọng lúc biên dịch | So phiên bản đã biên dịch và đã giải quyết |
| Lỗi auto-configuration sau khi thêm starter | Class/bean mới khiến điều kiện tự cấu hình thay đổi | Xem starter, dependency tree, bean và condition report |
| Có nhiều SLF4J provider/binding | Nhiều implementation hoặc provider logging trên classpath | Tìm tất cả provider và nhánh kéo chúng vào |
| Unit test chạy, ứng dụng đóng gói lỗi | Dependency chỉ có trong test hoặc compile classpath | So `testRuntimeClasspath` với `runtimeClasspath` |

**Chú ý:** các lỗi trên không chỉ có nguyên nhân duy nhất là dependency. `NoClassDefFoundError` còn có thể bắt nguồn từ lỗi khởi tạo class; lỗi Spring bean có thể do cấu hình hoặc component scan. Dependency tree chỉ là một phần của quá trình chẩn đoán.

### Phân biệt “nhiều yêu cầu phiên bản” với “nhiều JAR thực tế”

Thấy cả `shared-json:2.7` và `shared-json:3.2` trên báo cáo *verbose* không nhất thiết có hai JAR runtime: một phiên bản có thể là yêu cầu bị bỏ qua. Ngược lại, hai artifact **khác tọa độ** vẫn có thể đóng gói những class trùng tên, và dependency tree không tự chứng minh không có classpath collision hoặc shading.

Muốn biết phiên bản nào thực sự được JVM sử dụng trong lỗi cụ thể, ngoài resolved tree có thể cần kiểm tra JAR chạy thực tế và nguồn nạp class. Đây là bước sâu hơn sau khi đã hiểu dependency graph.

## 8. Spring Boot BOM và quản lý phiên bản

Spring Boot chủ động quản lý một tập phiên bản dependency tương thích theo từng phiên bản framework thông qua `spring-boot-dependencies` BOM. Việc dự án dùng Maven parent, import BOM hoặc dùng Gradle platform/dependency management theo cách cụ thể quyết định quy tắc quản lý phiên bản được áp dụng.

### Maven: dependencyManagement

Ví dụ dự án dùng Maven có thể import BOM trong trường hợp không dùng parent quản lý sẵn:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version><!-- phiên bản Spring Boot của dự án --></version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Trong một POM thực tế, trường `<version>` phải là một giá trị hoặc property hợp lệ; dòng comment trên chỉ minh họa vị trí cấu hình, không phải file hoàn chỉnh để copy chạy ngay.

Với BOM đã import, một dependency được quản lý có thể không cần khai báo phiên bản riêng:

~~~xml
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
</dependency>
~~~

BOM **quản lý phiên bản**; nó không tự thêm tất cả thư viện được quản lý vào classpath. Một thư viện chỉ xuất hiện khi có dependency trực tiếp hoặc đường transitive đưa nó vào.

### Gradle: platform/BOM và cơ chế quản lý phiên bản

Một cách sử dụng BOM với Gradle là:

~~~groovy
dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:VERSION'
    )
    implementation 'com.fasterxml.jackson.core:jackson-databind'
}
~~~

`VERSION` là placeholder, cần thay bằng phiên bản phù hợp với dự án. Nếu dự án Spring Boot đã có cơ chế quản lý phiên bản từ plugin/cấu hình hiện hữu, không nên tùy tiện khai báo chồng thêm cơ chế khác mà chưa hiểu kết quả resolution.

Tùy thiết lập, Gradle có thể báo một phiên bản được chọn do platform/constraint hoặc do conflict resolution. Dùng `dependencyInsight` để xem chính xác tại sao.

### Tại sao không nên sửa phiên bản một cách ngẫu nhiên?

Giả sử phát hiện `jackson-databind` có phiên bản không như mong đợi. Việc đặt phiên bản mới nhất vào mọi dependency không bảo đảm giải quyết lỗi, vì các module Jackson liên quan có thể cần nhất quán và một thư viện tích hợp có thể dựa trên API cụ thể. Trong Spring Boot, điểm bắt đầu hợp lý là kiểm tra **dependency management của đúng Spring Boot version**, các phiên bản đã override và thư viện thứ ba đang yêu cầu phiên bản khác.

Nếu phải override vì lỗi tương thích hoặc cập nhật bảo mật, cần hiểu phạm vi ảnh hưởng và đảm bảo các thư viện liên quan được giải quyết nhất quán. Trong một số trường hợp, nâng Spring Boot hoặc starter phù hợp sẽ giảm số override cần duy trì.

## 9. Cách sửa khi đã tìm được nguyên nhân

Không phải mọi xung đột đều sửa bằng cùng một thao tác. Hãy chọn phương án dựa trên **ai sở hữu dependency**, **tại sao nó được đưa vào** và **phiên bản nào tương thích**.

### 9.1. Ưu tiên đồng bộ dependency với phiên bản Spring Boot

Nếu hai thư viện thuộc hệ sinh thái Spring được khai báo phiên bản thủ công khác với các phiên bản Boot quản lý, thường nên xem lại khai báo đó trước. Với dự án được quản lý đúng, nhiều starter có thể dùng phiên bản không viết trực tiếp trong phần `dependencies`.

Ví dụ thay vì khóa một phiên bản starter không cần thiết:

~~~xml
<!-- Khi đã có BOM/parent quản lý phiên bản phù hợp -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

### 9.2. Loại transitive dependency thực sự không cần thiết

Maven hỗ trợ `exclusions` trên dependency là nguồn đưa thư viện vào:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>legacy-client</artifactId>
    <version>1.0</version>
    <exclusions>
        <exclusion>
            <groupId>com.example</groupId>
            <artifactId>unused-logging-adapter</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

Gradle hỗ trợ exclusion tương tự:

~~~groovy
dependencies {
    implementation('com.example:legacy-client:1.0') {
        exclude group: 'com.example', module: 'unused-logging-adapter'
    }
}
~~~

Các tọa độ trên là ví dụ tưởng tượng để trình bày cú pháp. Exclusion thường áp dụng cho **nhánh dependency được chỉ định**. Nếu cùng artifact còn được một nhánh khác kéo vào, nó vẫn có thể xuất hiện trong dependency tree. Do đó, sau khi thêm exclusion, cần nhìn lại những đường dẫn còn yêu cầu artifact đó trong kết quả resolution của dự án.

Không nên exclude thư viện chỉ vì tên lạ. Trước hết phải xác định chức năng nào dùng nó và liệu thư viện cha có cần nó ở runtime hay không.

### 9.3. Quản lý phiên bản có chủ đích

Trong Maven, có thể dùng `dependencyManagement` để xác định phiên bản dùng cho một artifact; trong Gradle có thể dùng constraint/platform hoặc cách quản lý phiên bản phù hợp với dự án. Chỉ nên chốt một phiên bản khi đã biết các thư viện yêu cầu nó có khả năng tương thích.

Ví dụ Maven:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>shared-json</artifactId>
            <version>3.2</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Trong Gradle:

~~~groovy
dependencies {
    constraints {
        implementation('com.example:shared-json:3.2') {
            because 'Cần thống nhất phiên bản cho các nhánh phụ thuộc'
        }
    }
}
~~~

**Constraint không có nghĩa giống hệt với force.** Tùy Gradle và các constraint hiện có, phiên bản được chọn có thể vẫn khác yêu cầu. Nếu cần hiểu hoặc áp đặt yêu cầu chặt hơn, phải xem cơ chế constraint/strictly cụ thể và kết quả `dependencyInsight`. `resolutionStrategy.force` cũng tồn tại, nhưng ép phiên bản có thể che mất bất tương thích và nên được dùng có lý do rõ ràng.

### 9.4. Thay starter khi nhu cầu công nghệ thực sự khác

Nếu dự án chỉ cần reactive stack, việc khai báo đồng thời starter servlet và reactive có thể đưa thêm web stack ngoài ý định. Nên xác định API và runtime cần dùng, sau đó chọn starter tương ứng. Tương tự, một ứng dụng không cần JPA thì không nên giữ `spring-boot-starter-data-jpa` chỉ vì từng sao chép cấu hình mẫu; nếu chỉ dùng JDBC, có thể dùng starter phù hợp hơn.

Đây là thay đổi **khả năng của ứng dụng**, vì vậy không nên xóa starter chỉ nhằm làm cây dependency ngắn hơn.

### 9.5. Cập nhật thư viện cha khi vấn đề đến từ dependency của nó

Một SDK cũ có thể kéo phiên bản thư viện transitive đã lỗi thời. Thay vì override liên tục, đôi khi nâng SDK lên phiên bản hỗ trợ stack hiện tại là lựa chọn bền vững hơn. Khi SDK chưa hỗ trợ phiên bản mới, cần cân nhắc tương thích và phạm vi thay đổi.

## 10. Tình huống thực hành 1: dependency xung đột sau khi thêm SDK

Giả sử một ứng dụng Spring Boot đang hoạt động bình thường. Sau khi thêm `payment-sdk`, khi gọi API thanh toán xuất hiện:

~~~text
java.lang.NoSuchMethodError:
  'java.lang.String com.example.json.JsonUtil.toJson(java.lang.Object)'
~~~

Đây là ví dụ lỗi giả định. Ta có thể lần theo:

**Bước 1 — xác định artifact có class `JsonUtil`.** Dựa vào package và tài liệu của SDK, tìm ra `com.example:shared-json` là artifact nghi vấn.

**Bước 2 — đọc các đường dẫn yêu cầu artifact.** Với Maven:

~~~bash
./mvnw dependency:tree -Dincludes=com.example:shared-json -Dverbose
~~~

Với Gradle:

~~~bash
./gradlew dependencyInsight --dependency shared-json --configuration runtimeClasspath
~~~

Giả sử kết quả giải quyết phiên bản cho biết:

~~~text
payment-sdk:2.0 -> shared-json:3.0 (yêu cầu)
legacy-reports:1.1 -> shared-json:1.8 (yêu cầu)
runtimeClasspath -> shared-json:1.8 (đã chọn)
~~~

Trong tình huống giả định này, ứng dụng đang dùng `1.8` ở runtime, trong khi SDK được biên dịch với API cần ở `3.0`. Điều đó *có thể* giải thích lỗi thiếu phương thức; vẫn cần xác định phương thức thực sự có mặt trong phiên bản nào.

**Bước 3 — tìm vì sao `1.8` được chọn.** Với Maven, kiểm tra dependency trực tiếp, khoảng cách nhánh và `dependencyManagement`; với Gradle, đọc selection reason và constraint trong `dependencyInsight`. Đừng tự áp dụng cơ chế “Maven chọn gần nhất” cho Gradle.

**Bước 4 — chọn cách xử lý phù hợp.** Có thể nâng `legacy-reports`, cập nhật SDK, điều chỉnh phiên bản theo BOM/constraint hoặc loại nhánh cũ thực sự không cần. Chọn cách nào phụ thuộc tương thích của hai thư viện và phiên bản Spring Boot. Không mặc định “cứ nâng shared-json lên bản cao nhất” sẽ an toàn.

**Bước 5 — xác nhận kết quả resolution.** Sau khi chỉnh khai báo dependency, đọc lại đúng cây `runtimeClasspath` (hoặc cây Maven phù hợp) để biết phiên bản đang được chọn. Kiểm tra chức năng lỗi trên bản build thực tế thuộc giai đoạn xác minh thay đổi, tách biệt với việc chỉ nhìn dependency tree.

## 11. Tình huống thực hành 2: nhiều logging provider

Một ứng dụng Spring Boot dùng logging mặc định, sau khi thêm SDK bên thứ ba xuất hiện cảnh báo liên quan tới nhiều SLF4J provider. Nhiều implementation/provider cùng hiện diện có thể gây cảnh báo và hành vi logging ngoài ý định.

Phân tích trong Maven:

~~~bash
./mvnw dependency:tree -Dincludes=org.slf4j:*,ch.qos.logback:*,org.apache.logging.log4j:*
~~~

Trong Gradle, có thể bắt đầu bằng:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Rồi truy vấn từng artifact nghi vấn bằng `dependencyInsight`.

Tìm những nhánh kéo các provider vào, phân biệt:

- **Logging API** (ví dụ SLF4J API) mà code và framework gọi.
- **Provider/implementation** mà runtime sử dụng để ghi log.
- **Bridge/adapter** chuyển lời gọi giữa các hệ thống logging.

Không nên loại một API cần thiết chỉ để hết cảnh báo; cũng không nên xóa bridge mà không hiểu hướng chuyển tiếp logging. Với Spring Boot, hãy xác định logging setup đang sử dụng và đảm bảo chỉ còn bộ implementation phù hợp với cấu hình đó.

## 12. Tình huống thực hành 3: thấy Tomcat dù dự án dùng WebFlux

Giả sử dự án có khai báo:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Việc cùng có hai starter khiến đồ thị chứa thành phần của cả Spring MVC và WebFlux. Trong điều kiện auto-configuration mặc định phổ biến của Spring Boot, khi cả hai stack cùng có mặt, kiểu ứng dụng servlet/MVC thường được ưu tiên so với reactive web application type, trừ khi có cấu hình rõ ràng khác. Do đó “đã thêm WebFlux” không đủ để kết luận ứng dụng sẽ sử dụng Netty reactive server.

Cách tìm nguồn Tomcat:

~~~bash
./gradlew dependencyInsight --dependency tomcat-embed-core --configuration runtimeClasspath
~~~

Hoặc Maven:

~~~bash
./mvnw dependency:tree -Dincludes=org.apache.tomcat.embed:*
~~~

Nếu kết quả chỉ tới `spring-boot-starter-web`, cần xác định có thật sự cần stack MVC hay không. Nếu ứng dụng chỉ dùng WebFlux, việc bỏ dependency web servlet không còn cần thiết có thể là cách phù hợp, nhưng phải xem xét controller, filter, client và các thành phần sử dụng MVC trước khi đổi starter.

Cùng một dependency tree có thể cho biết **thành phần nào đang hiện diện** nhưng không tự khẳng định **web server nào đang được chọn khi Spring Boot chạy**. Để xác nhận hành vi runtime, cần xem điều kiện auto-configuration và log khởi động.

## 13. Kiểm tra artifact đóng gói khi tree và runtime dường như không khớp

Trong Spring Boot, các plugin đóng gói có thể tạo **executable JAR** chứa thư viện trong cấu trúc như `BOOT-INF/lib/`, tùy loại artifact và cách build.

Với JDK có lệnh `jar`, có thể xem danh sách bên trong một JAR cụ thể:

~~~bash
jar tf build/libs/ten-ung-dung.jar
~~~

Với dự án Maven, file có thể nằm dưới `target/` thay vì `build/libs/`. Tên và cấu trúc file còn phụ thuộc cấu hình build, có phải executable JAR hay không và phiên bản công cụ.

Ví dụ dạng cây thư mục của executable JAR thông dụng:

~~~text
BOOT-INF/
├── classes/
│   └── com/example/...
└── lib/
    ├── spring-web-....jar
    ├── spring-webmvc-....jar
    └── ...
~~~

Nếu dependency tree cho thấy một thư viện hiện diện ở runtime, nhưng bản deploy không có thư viện đó, có thể xảy ra các tình huống:

- Artifact đang triển khai là build cũ hoặc được tạo bằng cấu hình khác.
- Đang xem một configuration không tương ứng với runtime của ứng dụng.
- Packaging có loại trừ hoặc cấu hình khác.
- Chạy WAR hoặc môi trường có container cung cấp dependency theo cơ chế riêng.
- Thư viện đến từ classpath bên ngoài artifact hoặc một launcher khác.

Tương tự, chỉ thấy tên artifact trong `BOOT-INF/lib` không chứng minh class nào đã được JVM nạp nếu có nhiều nguồn classloader. Dependency tree chủ yếu giải thích **resolution**, còn bước kiểm tra JAR giúp xác minh **packaging**.

## 14. Một quy trình đọc cây hiệu quả khi điều tra lỗi

Khi gặp vấn đề dependency trong một dự án Spring Boot, nên đi theo chuỗi câu hỏi sau:

~~~text
Biểu hiện lỗi hoặc thư viện ngoài dự kiến
                 |
                 v
      Xác định artifact nghi vấn
                 |
                 v
    Chọn đúng scope / configuration
                 |
                 v
        Hiển thị dependency tree
                 |
                 v
     Tìm mọi đường dẫn kéo artifact
                 |
                 v
   Xác định phiên bản resolved cuối cùng
                 |
                 v
 Tìm quy tắc chọn phiên bản / nguồn kéo vào
                 |
                 v
  Chọn sửa root dependency, BOM/constraint,
       exclusion hoặc version phù hợp
                 |
                 v
  Đọc lại tree và xác nhận artifact thực tế
~~~

Có thể dùng bảng sau để chọn công cụ nhanh:

| Cần biết | Maven | Gradle |
|---|---|---|
| Toàn bộ cây dependency | `./mvnw dependency:tree` | `./gradlew dependencies --configuration runtimeClasspath` |
| Ai kéo một artifact vào? | `dependency:tree -Dincludes=group:artifact` | `dependencyInsight --dependency artifact --configuration runtimeClasspath` |
| Phiên bản nào được chọn? | Cây đã giải quyết; xem verbose nếu cần | Cây với dấu `->` và `dependencyInsight` |
| Vì sao có xung đột? | Xem nhánh, `dependencyManagement`, dependency trực tiếp, nearest definition | Xem selection reason, constraint, platform, resolution rule |
| Chỉ quan tâm lúc chạy? | `dependency:tree -Dscope=runtime` | `dependencies --configuration runtimeClasspath` |
| Chỉ quan tâm kiểm thử? | `dependency:tree -Dscope=test` và ngữ cảnh test | `dependencies --configuration testRuntimeClasspath` |

Đừng giải thích kết quả của Maven bằng quy tắc chọn version của Gradle hoặc ngược lại. Hai công cụ có mô hình và cú pháp khác nhau dù đều giải quyết một đồ thị các module.

## 15. Những lỗi đọc dependency tree thường gặp

### “Thấy tên dependency trong POM/build.gradle nghĩa là nó đã ở runtime”

Sai trong nhiều trường hợp. Scope như `test`/`provided` hay Gradle configuration như `compileOnly` có thể khiến thư viện không có trong runtime của ứng dụng. Ngoài ra còn có exclusion và nhiều bước resolution/packaging.

### “Thấy hai phiên bản trong tree nghĩa là JVM tải hai bản cùng lúc”

Chưa chắc. Output có thể cho biết một phiên bản bị loại hoặc một yêu cầu được chuyển sang phiên bản đã chọn. Cần phân biệt **requested**, **selected** và **packaged**.

### “Chỉ nhìn dependency trực tiếp là đủ”

Không đủ khi starter hoặc SDK kéo các dependency transitive. Lỗi từ `jackson-databind` có thể bắt đầu ở một SDK hoặc starter, dù file build không nhắc trực tiếp đến Jackson.

### “Chỉ cần exclude mọi thư viện không quen tên”

Exclusion có thể làm mất class cần thiết ở runtime hoặc phá một auto-configuration. Tên lạ có thể là dependency bắt buộc của starter. Cần biết tại sao nó được kéo vào và phần nào đang sử dụng.

### “Có BOM nghĩa là không còn xung đột”

BOM giúp quản lý phiên bản, nhưng dependency trực tiếp có version rõ ràng, BOM khác, constraint, rule hoặc thư viện không nằm trong BOM vẫn có thể tạo xung đột. BOM không chứng minh tương thích với mọi SDK ngoài hệ sinh thái.

### “Dependency tree thể hiện chính xác mọi thứ JVM nạp”

Dependency tree mô tả dữ liệu build/resolution trong một configuration hoặc scope. Ứng dụng chạy trong app server, container, launcher đặc biệt hoặc runtime có classloader riêng có thể gặp khác biệt giữa build và thực tế. Khi cần, xem cả artifact đóng gói và cách khởi chạy.

### “Mọi `NoClassDefFoundError` đều do thiếu dependency”

Lỗi này đôi khi xảy ra vì class có mặt nhưng quá trình khởi tạo tĩnh của nó từng thất bại. Khi đọc stack trace, cần xem nguyên nhân gốc thay vì tự thêm dependency theo tên class.

## 16. Bài tập: tìm thư viện ngoài dự kiến

Giả sử dự án Spring Boot dùng Maven có ba dependency trực tiếp:

~~~text
bookstore
├── spring-boot-starter-web
├── document-exporter
└── spring-boot-starter-test (test)
~~~

Một ngày ứng dụng phát hiện trên runtime classpath có `legacy-xml-parser`, mặc dù không ai khai báo trực tiếp trong `pom.xml`.

Một kết quả tree giả định:

~~~text
bookstore
+- spring-boot-starter-web
|  \- ...
+- document-exporter:4.0
|  \- report-engine:2.0
|     \- legacy-xml-parser:1.1
\- spring-boot-starter-test (test)
   \- ...
~~~

Có thể trả lời lần lượt:

1. **Thư viện xuất hiện từ đâu?** Từ `document-exporter` qua `report-engine`.
2. **Có thật sự thuộc runtime không?** Trong ví dụ có, nhưng vẫn cần xác nhận scope/resolved artifact cụ thể của dự án.
3. **Có cần loại nó không?** Chưa đủ thông tin. `report-engine` có thể đang dùng parser cho xuất tài liệu.
4. **Nếu muốn thay nó?** Xem phiên bản mới của `report-engine` hoặc `document-exporter`, cấu hình hỗ trợ parser khác, và tác động đến tính năng xuất tài liệu.
5. **Nếu nó được xem là rủi ro bảo mật?** Xác định đúng phiên bản và khả năng sử dụng thực tế, kiểm tra bản sửa tương thích; dependency tree chỉ cho biết đường phụ thuộc, không tự đánh giá mức rủi ro.

Sau bài tập, thử tự vẽ lại đường dẫn:

~~~text
bookstore -> document-exporter -> report-engine -> legacy-xml-parser
~~~

Đó chính là dữ kiện cần có để trao đổi với người sở hữu dependency trực tiếp hoặc quyết định một thay đổi build có lý do.

## 17. Thói quen hữu ích khi quản lý dependency trong Spring Boot

Một cây dependency dễ hiểu thường đến từ một số lựa chọn nhất quán:

1. **Dùng starter đúng nhu cầu.** Starter là điểm đầu vào tiện lợi, nhưng kéo theo cả một nhóm khả năng. Bỏ các starter không còn sử dụng giúp giảm độ phức tạp của classpath.
2. **Để một cơ chế rõ ràng quản lý phiên bản.** Tránh nhiều cách override không cần thiết chồng lên BOM hoặc platform của Spring Boot.
3. **Khai báo rõ dependency quan trọng mà mã nguồn dùng trực tiếp.** Không nên dựa vào việc một class “tình cờ” xuất hiện do thư viện khác kéo vào nếu ứng dụng thật sự phụ thuộc vào API đó.
4. **Nhìn đúng runtime classpath khi tìm lỗi lúc chạy.** Test dependency không giải thích được mọi thứ ở production.
5. **Tìm mọi đường dẫn đến artifact trước khi exclude.** Loại từ một nhánh có thể không loại hết nếu còn nhánh khác.
6. **Không suy diễn tính tương thích chỉ từ số phiên bản.** Một phiên bản cao hơn vẫn có thể phá ABI hoặc hành vi mà thư viện khác dựa vào.
7. **Biết chính xác artifact đang triển khai.** Bản build cũ, profile build hoặc cấu hình packaging khác nhau có thể làm lệch kết luận từ cây dependency hiện tại.

Dependency tree còn hữu ích khi tối ưu thời gian build, nhận diện thư viện không dùng, phân tích footprint và lập danh mục thành phần phần mềm. Tuy nhiên, mỗi mục tiêu cần cách đánh giá riêng: một thư viện có mặt trong tree không tự chứng minh rằng ứng dụng đang gọi chức năng của thư viện đó.

## Kết luận

Đọc dependency tree là kỹ năng nền tảng khi làm việc với **dependency và starter trong Spring Boot**. Hãy luôn tìm **đường dẫn đưa artifact vào**, **phiên bản đã được chọn**, **scope/configuration đang xét**, và **quy tắc resolution đã quyết định kết quả**. Maven cung cấp `dependency:tree` và cơ chế `dependencyManagement`; Gradle cung cấp `dependencies`, `dependencyInsight` cùng hệ thống configuration, platform và constraint. Chúng phục vụ cùng mục tiêu nhưng có cách giải quyết xung đột khác nhau.

Khi biết “thư viện này đến từ đâu và vì sao phiên bản này được chọn”, việc sửa lỗi trở thành quyết định có căn cứ: đổi starter, cập nhật dependency cha, điều chỉnh version management hoặc loại bỏ một nhánh thật sự không cần thiết. Đó là cách biến một cây dependency dài thành bản đồ có thể dùng để hiểu và kiểm soát hành vi ứng dụng.

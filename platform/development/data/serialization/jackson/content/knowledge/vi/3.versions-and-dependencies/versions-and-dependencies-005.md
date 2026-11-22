# Kiểm tra dependency bắc cầu trong ứng dụng có framework

Trong một ứng dụng Java dùng framework, thư viện Jackson thường không xuất hiện chỉ vì nhóm phát triển khai báo trực tiếp `jackson-databind`. Một starter, extension hoặc thư viện tích hợp có thể kéo Jackson vào thông qua nhiều cấp dependency. Các dependency được đưa vào theo cách đó gọi là **dependency bắc cầu (transitive dependency)**.

Khi ứng dụng chạy, phiên bản Jackson thực tế là kết quả của quá trình phân giải dependency của Maven hoặc Gradle, kết hợp với các quy tắc quản lý phiên bản của framework. Vì vậy, muốn biết ứng dụng đang dùng Jackson phiên bản nào, cần xem dependency graph của đúng module và đúng classpath, tìm đường dẫn kéo thư viện vào, rồi xác định quy tắc nào đã chọn phiên bản cuối cùng.

## 1. Dependency bắc cầu xuất hiện như thế nào?

Giả sử một ứng dụng dùng web framework và khai báo một starter:

```text
my-application
└── web-starter
    └── json-integration
        └── jackson-databind
            ├── jackson-core
            └── jackson-annotations
```

Ứng dụng chỉ khai báo `web-starter`, nhưng graph có thể chứa `json-integration`, `jackson-databind`, `jackson-core` và `jackson-annotations`. Các thư viện ở những nhánh phía dưới là dependency bắc cầu của ứng dụng.

Trong hệ sinh thái Jackson 2.x, các artifact thường gặp gồm:

| Artifact | Vai trò |
|---|---|
| `com.fasterxml.jackson.core:jackson-core` | API đọc và ghi JSON ở mức token, parser và generator. |
| `com.fasterxml.jackson.core:jackson-annotations` | Các annotation như `@JsonProperty`, `@JsonIgnore` và `@JsonCreator`. |
| `com.fasterxml.jackson.core:jackson-databind` | Ánh xạ JSON với đối tượng Java và cung cấp tree model qua `ObjectMapper`, `JsonNode`. |
| `com.fasterxml.jackson.datatype:jackson-datatype-jsr310` | Hỗ trợ các kiểu ngày giờ Java Time như `LocalDate` và `Instant`. |
| `com.fasterxml.jackson.datatype:jackson-datatype-jdk8` | Hỗ trợ một số kiểu Java 8 như `Optional`. |
| `com.fasterxml.jackson.module:jackson-module-parameter-names` | Hỗ trợ lấy tên tham số constructor trong các trường hợp phù hợp. |
| `com.fasterxml.jackson.module:jackson-module-kotlin` | Tích hợp Jackson với Kotlin. |
| `com.fasterxml.jackson.dataformat:jackson-dataformat-yaml` | Đọc và ghi YAML thông qua hệ sinh thái Jackson. |

Không phải ứng dụng nào cũng cần tất cả artifact trên. Framework hoặc starter có thể chọn một tập module tùy theo tính năng mà nó cung cấp. Khi kiểm tra, cần phân biệt artifact mà ứng dụng trực tiếp khai báo với artifact được kéo vào qua một dependency khác.

### 1.1. Direct dependency và transitive dependency

- **Direct dependency:** xuất hiện trực tiếp trong phần `dependencies` của module đang xét.
- **Transitive dependency:** được một direct dependency hoặc một dependency bắc cầu khác khai báo kéo vào.

Ví dụ với Maven:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
```

Trong ví dụ này, starter web là direct dependency. Những thư viện JSON mà starter hoặc các thành phần nó sử dụng khai báo có thể là transitive dependency. Đường dẫn cụ thể phụ thuộc phiên bản Spring Boot và cấu hình build; không nên suy ra phiên bản hoặc danh sách artifact chỉ từ tên starter.

Với Gradle, ý nghĩa tương tự:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
}
```

`implementation` là dependency mà module khai báo trực tiếp. Những thư viện được starter yêu cầu sẽ xuất hiện ở các nhánh con trong graph đã phân giải.

### 1.2. Vì sao phải xem đúng classpath?

Một dự án có thể có nhiều tập dependency:

- `compileClasspath`: dependency phục vụ biên dịch mã nguồn chính.
- `runtimeClasspath`: dependency cần có khi chạy ứng dụng.
- `testCompileClasspath` hoặc `testCompileClasspath` tương ứng trong công cụ build: dependency phục vụ biên dịch test.
- `testRuntimeClasspath`: dependency cần khi chạy test.

Tên configuration cụ thể phụ thuộc build tool và plugin. Một thư viện có thể xuất hiện trong test nhưng không có trong runtime của ứng dụng, hoặc ngược lại. Nếu mục tiêu là tìm Jackson mà ứng dụng triển khai thực sự sử dụng, hãy ưu tiên kiểm tra runtime classpath của đúng module.

Với ứng dụng nhiều module, chạy lệnh ở root có thể hiển thị graph của nhiều module hoặc chỉ graph của project hiện tại tùy lệnh và cấu hình. Hãy xác định module chứa ứng dụng cần điều tra, rồi chỉ rõ module/configuration khi công cụ hỗ trợ.

## 2. Kiểm tra dependency graph bằng Maven

Maven Dependency Plugin cung cấp lệnh `dependency:tree` để hiển thị dependency theo cấu trúc cha-con. Đây thường là điểm bắt đầu tốt nhất khi cần tìm đường dẫn mà Jackson đi vào ứng dụng.

### 2.1. Xem toàn bộ cây dependency

Tại thư mục chứa `pom.xml`, chạy Maven Wrapper nếu dự án có cung cấp:

```bash
./mvnw dependency:tree
```

Trên Windows có thể dùng:

```powershell
./mvnw.cmd dependency:tree
```

Nếu dự án không có wrapper, dùng lệnh `mvn` đã cài trên máy:

```bash
mvn dependency:tree
```

Output có dạng khái quát như sau:

```text
com.example:orders-service:jar:1.0.0
\- org.springframework.boot:spring-boot-starter-web:jar:<version>:compile
   \- org.springframework.boot:spring-boot-starter-json:jar:<version>:compile
      \- com.fasterxml.jackson.core:jackson-databind:jar:<version>:compile
         +- com.fasterxml.jackson.core:jackson-annotations:jar:<version>:compile
         \- com.fasterxml.jackson.core:jackson-core:jar:<version>:compile
```

Đây là sơ đồ minh họa, không phải cây cố định cho mọi phiên bản framework. Hãy đọc output thật của dự án để biết dependency cha trực tiếp và các phiên bản đã được Maven chọn.

Mỗi dòng thể hiện tọa độ artifact và scope. Một tọa độ Maven thường có dạng:

```text
groupId:artifactId:type:version:scope
```

Khi lần theo nhánh từ project xuống `jackson-databind`, ta biết thành phần nào đã đưa Jackson vào graph. Từ `jackson-databind`, tiếp tục kiểm tra các dependency của nó như `jackson-core` và `jackson-annotations`.

### 2.2. Lọc riêng Jackson

Khi cây quá dài, có thể lọc theo artifact cần điều tra:

```bash
./mvnw dependency:tree -Dincludes=com.fasterxml.jackson.core:jackson-databind
```

Lệnh này tập trung vào `jackson-databind`. Có thể đổi artifact để kiểm tra module khác, chẳng hạn:

```bash
./mvnw dependency:tree -Dincludes=com.fasterxml.jackson.core:jackson-core
./mvnw dependency:tree -Dincludes=com.fasterxml.jackson.core:jackson-annotations
```

Nếu cần xem các module Jackson thuộc nhiều group khác nhau, chạy cây đầy đủ rồi tìm các dòng có `com.fasterxml.jackson`, hoặc dùng bộ lọc nhiều tọa độ theo cú pháp hỗ trợ bởi phiên bản Maven Dependency Plugin đang dùng. Bộ lọc theo một artifact cụ thể thường dễ đọc hơn khi điều tra một xung đột.

### 2.3. Hiển thị các phiên bản bị loại do xung đột

Maven có thể gặp cùng một artifact với nhiều phiên bản trên các nhánh khác nhau. Dùng `-Dverbose` để hiển thị thêm các dependency bị loại trong quá trình mediation:

```bash
./mvnw dependency:tree -Dverbose -Dincludes=com.fasterxml.jackson.core:jackson-databind
```

Output minh họa:

```text
com.example:orders-service:jar:1.0.0
+- com.example:legacy-client:jar:1.0.0:compile
|  \- com.fasterxml.jackson.core:jackson-databind:jar:2.x.a:compile
\- org.springframework.boot:spring-boot-starter-json:jar:<version>:compile
   \- com.fasterxml.jackson.core:jackson-databind:jar:2.x.b:compile
      \- (com.fasterxml.jackson.core:jackson-databind:jar:2.x.a:compile - omitted for conflict with 2.x.b)
```

Các phiên bản `2.x.a`, `2.x.b` ở đây chỉ là ký hiệu minh họa. Điều cần quan sát là:

- Có bao nhiêu đường dẫn yêu cầu cùng artifact.
- Phiên bản nào được giữ trong graph cuối cùng.
- Phiên bản nào bị loại do conflict.
- Nhánh nào khai báo phiên bản được chọn.

Maven thường áp dụng quy tắc **nearest definition**: dependency ở đường dẫn ngắn hơn được ưu tiên. Nếu các đường dẫn có cùng độ sâu, thứ tự khai báo có thể quyết định kết quả. Dependency được khai báo trực tiếp ở project thường có lợi thế vì ở độ sâu gần nhất. `dependencyManagement` có thể quản lý phiên bản được dùng cho dependency trong graph, nên không thể chỉ nhìn số cấp để giải thích mọi kết quả.

### 2.4. Kiểm tra phiên bản do BOM hoặc parent POM quản lý

Framework thường cung cấp BOM (Bill of Materials) để quản lý một tập phiên bản thư viện tương thích. Với Spring Boot, `spring-boot-dependencies` là BOM quản lý nhiều dependency, trong đó có các thư viện Jackson theo phiên bản Spring Boot tương ứng.

Nếu dự án dùng Spring Boot parent, phần parent có thể trông như sau:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>${spring-boot.version}</version>
    <relativePath/>
</parent>
```

Parent này cung cấp dependency management và các cấu hình build mặc định của Spring Boot. Khi đó, một dependency không khai báo version vẫn có thể nhận phiên bản từ dependency management.

Nếu không dùng parent, dự án có thể import BOM trong `dependencyManagement`:

```xml
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
```

Để xem POM hiệu lực sau khi kế thừa parent, import BOM và áp dụng profile, chạy:

```bash
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
```

Tìm `jackson-databind`, `jackson-core`, `jackson-annotations` và các module liên quan trong `effective-pom.xml`. Phần `dependencyManagement` cho biết phiên bản được quản lý sau khi Maven hợp nhất cấu hình.

Phân biệt hai khái niệm:

- `dependencyManagement` quản lý version, scope hoặc thông tin dependency khi dependency đó được khai báo hoặc được kéo vào; nó không tự thêm mọi dependency được liệt kê vào classpath.
- `dependencies` khai báo dependency mà module thực sự cần. Dependency có thể được thêm trực tiếp hoặc xuất hiện bắc cầu qua một dependency khác.

### 2.5. Phân biệt scope

Maven có các scope như `compile`, `provided`, `runtime`, `test` và `system`. Scope ảnh hưởng việc dependency xuất hiện ở classpath nào và có được đóng gói hay không. Vì vậy, một artifact xuất hiện trong cây dependency không đồng nghĩa nó chắc chắn có mặt trong môi trường chạy cuối cùng.

Để tập trung vào dependency cần khi chạy, có thể dùng:

```bash
./mvnw dependency:tree -Dscope=runtime
```

Nếu kết quả khác cây mặc định, hãy xác định sự khác nhau có đến từ scope hay không trước khi kết luận rằng dependency đã biến mất.

## 3. Kiểm tra dependency graph bằng Gradle

Gradle cung cấp task `dependencies` để in dependency graph của một configuration và `dependencyInsight` để giải thích vì sao một dependency được chọn.

### 3.1. Xem runtimeClasspath

Tại thư mục dự án có `gradlew`, chạy:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Trên Windows:

```powershell
./gradlew.bat dependencies --configuration runtimeClasspath
```

Output minh họa:

```text
runtimeClasspath
\--- org.springframework.boot:spring-boot-starter-web:<version>
     \--- org.springframework.boot:spring-boot-starter-json:<version>
          \--- com.fasterxml.jackson.core:jackson-databind:<selected-version>
               +--- com.fasterxml.jackson.core:jackson-annotations:<selected-version>
               \--- com.fasterxml.jackson.core:jackson-core:<selected-version>
```

Ký hiệu `+---`, `\\---` thể hiện các nhánh trong graph. Gradle cũng có thể hiển thị yêu cầu phiên bản và phiên bản đã chọn, ví dụ `requested -> selected`, hoặc các dấu hiệu liên quan đến constraint và conflict resolution.

Nếu cần điều tra classpath khác, đổi configuration:

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration testRuntimeClasspath
```

Hãy chọn configuration đúng với câu hỏi. Khi điều tra lỗi chỉ xuất hiện lúc khởi chạy ứng dụng, `runtimeClasspath` thường có ý nghĩa hơn `testRuntimeClasspath`.

### 3.2. Dùng dependencyInsight để biết vì sao phiên bản được chọn

`dependencyInsight` tập trung vào một dependency và giải thích các đường dẫn yêu cầu cũng như lý do chọn phiên bản:

```bash
./gradlew dependencyInsight \
    --dependency jackson-databind \
    --configuration runtimeClasspath
```

Ví dụ output có thể cho thấy một phiên bản được chọn vì conflict resolution, dependency constraint, platform hoặc một quy tắc khác trong build. Nội dung chính xác tùy graph và phiên bản Gradle.

Có thể chạy riêng cho các artifact cốt lõi:

```bash
./gradlew dependencyInsight --dependency jackson-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-annotations --configuration runtimeClasspath
```

Đọc output theo thứ tự:

1. Xác nhận configuration đang được kiểm tra.
2. Xác định module và phiên bản cuối cùng được chọn.
3. Tìm các dependency yêu cầu phiên bản khác.
4. Đọc phần selection reason để biết phiên bản được chọn do conflict resolution, constraint, platform, rule hay khai báo trực tiếp.
5. Lần theo đường dẫn quay về dependency gốc hoặc framework starter.

Gradle thường giải quyết conflict phiên bản module bằng cách chọn phiên bản phù hợp theo quy tắc resolution của nó; hành vi này khác quy tắc nearest definition của Maven. Vì vậy, không nên áp dụng cách giải thích Maven cho output Gradle.

### 3.3. Kiểm tra dependency constraint và platform

Gradle có thể quản lý phiên bản qua platform hoặc constraint. Một platform chứa các dependency constraint, thường được dùng để căn chỉnh phiên bản của một nhóm thư viện.

Ví dụ khai báo Jackson BOM trực tiếp trong Gradle:

```kotlin
dependencies {
    implementation(platform("com.fasterxml.jackson:jackson-bom:<jackson-version>"))

    implementation("com.fasterxml.jackson.core:jackson-databind")
    implementation("com.fasterxml.jackson.datatype:jackson-datatype-jsr310")
}
```

`<jackson-version>` là placeholder; hãy dùng phiên bản đã được chọn và kiểm tra tương thích với framework của dự án. Khi platform cung cấp constraint, các dependency tương ứng có thể không cần ghi version riêng.

Trong ứng dụng Spring Boot, phiên bản dependency thường đã được quản lý bởi BOM của Spring Boot thông qua plugin dependency management hoặc native Gradle platform. Nếu dự án đã dùng cơ chế đó, hãy kiểm tra BOM đang có hiệu lực trước khi thêm một Jackson BOM riêng. Hai bộ quản lý phiên bản có thể tạo ra kết quả khác với ý định ban đầu.

Ví dụ với native platform, khi dự án chủ động quản lý BOM của Spring Boot:

```kotlin
dependencies {
    implementation(platform("org.springframework.boot:spring-boot-dependencies:<boot-version>"))
    implementation("org.springframework.boot:spring-boot-starter-web")
}
```

Nếu Spring Boot Gradle plugin và dependency management plugin đã tự áp dụng BOM theo cấu hình dự án, không cần khai báo lặp lại chỉ để xem version. Hãy đọc `build.gradle` hoặc `build.gradle.kts` và output `dependencyInsight` để xác nhận cơ chế thực tế.

## 4. Hiểu vai trò của framework trong việc chọn phiên bản Jackson

Framework thường cố gắng cung cấp một tập dependency đã được kiểm thử cùng nhau. Vì vậy, starter hoặc BOM của framework có thể quản lý phiên bản Jackson thay cho từng module ứng dụng.

### 4.1. Starter không phải là phiên bản Jackson

Khi khai báo một starter, ứng dụng đang chọn một nhóm tính năng của framework. Starter có thể đưa vào một JSON integration module, và module đó lại phụ thuộc vào Jackson. Phiên bản Jackson được chọn còn phụ thuộc dependency management và các dependency khác trong toàn bộ graph.

Do đó, các nhận định sau không đủ để kết luận phiên bản thực tế:

- Chỉ biết tên starter.
- Chỉ biết version của `jackson-databind` trong một file build khác.
- Chỉ nhìn version được ghi trong một thư viện con.
- Chỉ kiểm tra `compileClasspath` trong khi lỗi xảy ra lúc runtime.

Hãy xem graph đã phân giải của module chạy ứng dụng.

### 4.2. Framework BOM và Jackson BOM

BOM là một POM hoặc platform tập hợp quy tắc quản lý version. Framework BOM thường quản lý nhiều thư viện thuộc một hệ sinh thái; Jackson BOM quản lý các artifact trong hệ sinh thái Jackson.

Trong một ứng dụng dùng framework, ưu tiên hiểu và sử dụng cơ chế quản lý dependency mà framework khuyến nghị. Ví dụ, nếu Spring Boot quản lý Jackson qua `spring-boot-dependencies`, việc tự ghi đè riêng `jackson-databind` có thể làm các module Jackson hoặc thư viện tích hợp khác không còn ở tập phiên bản mà framework đã kiểm thử.

Nếu cần nâng Jackson vì một yêu cầu cụ thể, hãy xác định trước:

- Phiên bản framework và BOM đang quản lý dependency.
- Những artifact Jackson nào xuất hiện trong runtime graph.
- Framework có cung cấp property hoặc cơ chế override được hỗ trợ hay không.
- Tất cả module Jackson liên quan có được căn chỉnh phiên bản hay không.
- Các thư viện tích hợp khác có tương thích với phiên bản mới hay không.

Không nên chỉ nâng một artifact theo số phiên bản mới nhất tìm thấy. Với Jackson 2.x, dùng BOM phù hợp giúp giữ các artifact Jackson ở một tập phiên bản nhất quán.

## 5. Nhận diện xung đột và dấu hiệu lệch phiên bản

Một dependency graph có thể chứa nhiều yêu cầu version cho cùng một artifact. Công cụ build thường giải quyết conflict và chọn một version, nhưng việc build thành công chưa chứng minh mọi thành phần đều tương thích ở runtime.

### 5.1. Một số dấu hiệu thường gặp

- Maven hiển thị các dòng `omitted for conflict with ...` trong cây verbose.
- Gradle hiển thị `requested -> selected` hoặc selection reason trong `dependencyInsight`.
- `jackson-databind`, `jackson-core` và `jackson-annotations` được quản lý bởi các nguồn version khác nhau.
- Ứng dụng biên dịch được nhưng gặp `NoSuchMethodError`, `NoClassDefFoundError` hoặc lỗi linkage khi chạy.
- Một module Jackson cần thiết không có trong runtime classpath.
- Kết quả test khác với ứng dụng đóng gói vì test runtime và runtime của ứng dụng có graph khác nhau.

Các dấu hiệu này giúp khoanh vùng, nhưng mỗi exception còn có thể do classloader, artifact đóng gói hoặc phiên bản thực tế trên môi trường triển khai. Hãy đối chiếu graph với nội dung artifact được triển khai.

### 5.2. Kiểm tra cả nhóm artifact, không chỉ databind

Một lỗi được biểu hiện tại `ObjectMapper` có thể liên quan đến `jackson-core`, `jackson-annotations` hoặc module datatype. Vì vậy, ngoài `jackson-databind`, hãy kiểm tra các artifact cốt lõi và module mà ứng dụng thực sự sử dụng.

Ví dụ, nếu DTO có `LocalDate` hoặc `Instant`, ứng dụng có thể cần `jackson-datatype-jsr310` và cấu hình đăng ký module phù hợp. Việc thấy `jackson-databind` trong graph không tự động chứng minh mọi kiểu dữ liệu đã có module hỗ trợ tương ứng.

### 5.3. Graph build và nội dung triển khai

Dependency graph mô tả kết quả phân giải của build. Trong một số môi trường, classpath thực tế còn chịu ảnh hưởng của packaging, application server, plugin system, container image hoặc classloader riêng.

Với Spring Boot executable JAR, có thể xem danh sách thư viện đóng gói bằng:

```bash
jar tf build/libs/application.jar
```

Hoặc với Maven:

```bash
jar tf target/application.jar
```

Tìm các file dưới `BOOT-INF/lib/` để xem thư viện đã được đóng gói trong executable JAR. Tên file thường chứa artifact và version. Đối với WAR hoặc ứng dụng chạy trong application server, cần xem cách đóng gói và quy tắc classloader của môi trường đó; thư viện do server cung cấp có thể ảnh hưởng classpath thực tế.

## 6. Điều chỉnh dependency sau khi đã xác định nguyên nhân

Chỉ sửa dependency sau khi đã biết artifact nào được kéo vào, đường dẫn nào yêu cầu version nào và framework đang quản lý phiên bản ra sao.

### 6.1. Ưu tiên cơ chế quản lý version của framework

Nếu ứng dụng dùng Spring Boot parent hoặc BOM, thông thường nên để BOM quản lý version Jackson. Dependency trực tiếp có thể không cần version:

```xml
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
</dependency>
```

Đây là ví dụ về cách khai báo khi dependency management đã cung cấp version. Không tự bỏ version khỏi dự án nếu dự án chưa có parent, BOM hoặc cơ chế quản lý tương đương.

Nếu framework không quản lý Jackson, có thể import Jackson BOM trong Maven:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson</groupId>
            <artifactId>jackson-bom</artifactId>
            <version>${jackson.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Sau đó khai báo các module Jackson cần dùng mà không phải lặp lại version ở từng dependency. Khi framework đã có BOM riêng, hãy kiểm tra cách framework hỗ trợ override trước khi bổ sung BOM khác.

### 6.2. Tránh khai báo version rời rạc cho từng module

Ví dụ không nên quản lý độc lập từng artifact nếu chúng thuộc cùng một bộ phiên bản:

```xml
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
    <version>...</version>
</dependency>
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-core</artifactId>
    <version>...</version>
</dependency>
```

Việc ghi version thủ công cho nhiều module dễ tạo trạng thái lệch khi một module được cập nhật mà module khác bị bỏ lại. BOM hoặc cơ chế dependency management tập trung giúp giảm rủi ro này.

### 6.3. Dùng exclusion khi một nhánh thực sự không cần dependency

Maven cho phép loại một dependency bắc cầu trên một cạnh cụ thể:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>legacy-client</artifactId>
    <version>${legacy-client.version}</version>
    <exclusions>
        <exclusion>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

Trong Gradle:

```kotlin
dependencies {
    implementation("com.example:legacy-client:<version>") {
        exclude(group = "com.fasterxml.jackson.core", module = "jackson-databind")
    }
}
```

Exclusion chỉ tác động đến nhánh được cấu hình. Nếu một dependency khác vẫn yêu cầu `jackson-databind`, artifact có thể tiếp tục xuất hiện trong graph. Sau khi exclusion, phải chạy lại cây dependency để xác nhận kết quả.

Không loại `jackson-core` hoặc `jackson-annotations` chỉ vì chúng xuất hiện nhiều lần trong cây. Đây là dependency nền tảng của Jackson Databind. Exclusion không phù hợp có thể làm ứng dụng thiếu class hoặc method khi chạy.

### 6.4. Hạn chế ép version toàn cục khi chưa hiểu graph

Maven có thể dùng dependency management để kiểm soát version; Gradle có thể dùng constraints, platform, resolution strategy hoặc `force`. Các cách ép version toàn cục có thể giải quyết một conflict trước mắt nhưng cũng có thể phá vỡ giả định tương thích của framework hoặc thư viện khác.

Trước khi ép version, hãy xác định lý do cần thay đổi và kiểm tra toàn bộ nhóm artifact liên quan. Sau khi sửa, chạy lại `dependency:tree` hoặc `dependencyInsight` để chứng minh graph đã chọn phiên bản mong muốn. Tiếp đó, kiểm tra build và chạy ứng dụng trong cấu hình tương ứng.

## 7. Quy trình điều tra thực tế

Khi một ứng dụng framework có lỗi liên quan đến Jackson hoặc cần biết Jackson được kéo vào từ đâu, có thể làm theo trình tự sau:

1. **Xác định module ứng dụng.** Tìm module chứa entry point hoặc module được đóng gói để triển khai.
2. **Xác định build tool.** Đọc `pom.xml`, `build.gradle` hoặc `build.gradle.kts` của module và các cấu hình parent/plugin liên quan.
3. **Chọn runtime graph.** Với Maven, chạy `dependency:tree`; với Gradle, chạy `dependencies --configuration runtimeClasspath`.
4. **Tìm artifact Jackson.** Tìm `jackson-databind`, `jackson-core`, `jackson-annotations` và các module datatype/dataformat đang dùng.
5. **Lần theo đường dẫn.** Xác định starter, framework integration hoặc thư viện nào đưa mỗi artifact vào.
6. **Tìm version được chọn.** Dùng Maven `-Dverbose` hoặc Gradle `dependencyInsight` để hiểu conflict và selection reason.
7. **Kiểm tra dependency management.** Xem parent POM, imported BOM, Gradle platform và constraint có hiệu lực.
8. **So sánh các module Jackson.** Xác nhận các artifact liên quan được căn chỉnh theo cơ chế version management dự định.
9. **Kiểm tra gói triển khai nếu cần.** Đối chiếu runtime graph với JAR/WAR hoặc classpath của môi trường thực tế.
10. **Điều chỉnh có chủ đích rồi kiểm tra lại.** Ưu tiên cơ chế quản lý version của framework; chỉ dùng exclusion hoặc override khi đã xác định nguyên nhân.

### Bảng lệnh tra cứu nhanh

| Mục đích | Maven | Gradle |
|---|---|---|
| Xem graph dependency | `./mvnw dependency:tree` | `./gradlew dependencies --configuration runtimeClasspath` |
| Tìm một artifact | `./mvnw dependency:tree -Dincludes=com.fasterxml.jackson.core:jackson-databind` | `./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath` |
| Xem conflict | `./mvnw dependency:tree -Dverbose` | `dependencyInsight` và đọc selection reason |
| Kiểm tra runtime | `./mvnw dependency:tree -Dscope=runtime` | `dependencies --configuration runtimeClasspath` |
| Xem cấu hình version hiệu lực | `./mvnw help:effective-pom` | Xem platform, constraints và kết quả `dependencyInsight` |

## 8. Những hiểu lầm thường gặp

**“Tôi không khai báo Jackson nên ứng dụng không dùng Jackson.”** Không đúng. Một starter hoặc thư viện tích hợp có thể đưa Jackson vào dưới dạng dependency bắc cầu. Dependency graph mới cho biết kết quả thực tế.

**“Version trong một dependency con là version ứng dụng đang chạy.”** Chưa chắc. Maven và Gradle đều có cơ chế phân giải conflict và quản lý version. Version yêu cầu ở một nhánh có thể không phải version được chọn cuối cùng.

**“Có `jackson-databind` nghĩa là đã có đủ mọi module Jackson.”** Không đúng. Các module như Java Time, Kotlin hoặc YAML là artifact riêng và chỉ xuất hiện khi dependency graph đưa chúng vào.

**“Build thành công chứng minh runtime không có xung đột.”** Không đủ. Lỗi linkage hoặc khác biệt classloader có thể chỉ xuất hiện khi chạy hoặc khi triển khai vào môi trường cụ thể.

**“Có thể loại một bản Jackson khỏi một nhánh để loại nó khỏi toàn ứng dụng.”** Không nhất thiết. Dependency khác có thể vẫn yêu cầu cùng artifact; exclusion thường áp dụng cho nhánh khai báo nó.

**“Framework nào cũng kéo cùng một cây Jackson.”** Không đúng. Graph phụ thuộc phiên bản framework, starter, plugin, BOM, cấu hình và các dependency trực tiếp khác của ứng dụng.

## Kết luận

Kiểm tra dependency bắc cầu là việc đọc graph đã được Maven hoặc Gradle phân giải, xác định đường dẫn đưa Jackson vào, rồi tìm quy tắc quản lý phiên bản của framework. Maven `dependency:tree` và `help:effective-pom`, cùng Gradle `dependencies` và `dependencyInsight`, cung cấp bằng chứng cần thiết để hiểu runtime classpath. Khi đã rõ graph, hãy căn chỉnh các module Jackson theo BOM hoặc dependency management phù hợp và chỉ điều chỉnh exclusion/override khi có nguyên nhân cụ thể.

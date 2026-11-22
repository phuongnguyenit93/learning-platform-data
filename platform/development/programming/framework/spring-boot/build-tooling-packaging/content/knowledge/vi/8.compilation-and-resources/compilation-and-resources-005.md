# Xử lý tài nguyên qua Maven Resources Plugin và Gradle processResources

## Mục tiêu và bức tranh tổng thể

Một dự án Spring Boot không chỉ chứa các file `.java`. Nó còn cần `application.properties`, `application.yml`, thông báo, template, file tĩnh, cấu hình thư viện và đôi khi dữ liệu mẫu. Trong quá trình build, **tài nguyên (resources)** phải được đưa từ thư mục nguồn sang đầu ra và, khi thật sự cần, được **lọc/thay giá trị** bằng thông tin của bản build.

Sau bài này, bạn có thể:

1. Phân biệt **copy resources**, **resource filtering** và **Spring Boot runtime property resolution**.
2. Đọc quá trình `process-resources` qua **Maven Resources Plugin**; biết `resources:resources` và `resources:testResources` chạy ở đâu.
3. Hiểu task **Gradle `processResources`**, cách `filesMatching`/`expand` xử lý file và quan hệ với `classes`/`jar`/`bootJar`.
4. Tạo ví dụ tái hiện được: một `build-info.properties` xuất hiện trong classpath với phiên bản dự án, nhưng `application.properties` vẫn giữ placeholder Spring.
5. Kiểm tra đầu ra thật ở `target/classes` hoặc `build/resources/main`, cách resource được đóng gói vào executable JAR, cùng lỗi encoding, file nhị phân, duplicate, filtering sai và cache.

**Phạm vi:** xử lý resource trong pipeline biên dịch và đóng gói Maven/Gradle của ứng dụng Spring Boot. Bài không thay cho hướng dẫn quản lý cấu hình môi trường, dependency hoặc triển khai hệ thống.

## 1. Resource nằm ở đâu và sẽ đi đến đâu?

Với một dự án Java Spring Boot theo quy ước:

```text
project/
├── pom.xml                       (Maven)
│   hoặc build.gradle[.kts]       (Gradle)
├── src/
│   ├── main/
│   │   ├── java/com/example/demo/...
│   │   └── resources/
│   │       ├── application.properties
│   │       ├── build-info.properties
│   │       ├── messages_vi.properties
│   │       ├── static/logo.png
│   │       └── templates/home.html
│   └── test/
│       ├── java/com/example/demo/...
│       └── resources/test-data.json
```

`src/main/java` chứa mã nguồn Java để **biên dịch**; `src/main/resources` chứa file không phải Java để **copy hoặc biến đổi**. `src/test/resources` là tài nguyên cho kiểm thử; không nên coi test resources là nội dung sẽ đi cùng sản phẩm phát hành.

Đường đi thông thường:

| Nguồn | Maven (mặc định) | Gradle Java plugin (mặc định) |
| --- | --- | --- |
| `src/main/resources/application.properties` | `target/classes/application.properties` | `build/resources/main/application.properties` |
| `src/main/resources/static/logo.png` | `target/classes/static/logo.png` | `build/resources/main/static/logo.png` |
| `src/test/resources/test-data.json` | `target/test-classes/test-data.json` | `build/resources/test/test-data.json` |
| `src/main/java` | `target/classes` (class đã biên dịch) | `build/classes/java/main` |
| `src/test/java` | `target/test-classes` (test class) | `build/classes/java/test` |

Các đường dẫn trên là quy ước của dự án Java đơn giản, có thể được thay trong `pom.xml`/`sourceSets` hoặc plugin; hãy nhìn cấu hình thực. Resource **không bắt buộc được biên dịch** để trở thành bytecode: tệp `.png` hoặc `.properties` thường được sao chép ở dạng tệp.

Trong executable Spring Boot JAR, tài nguyên chính được đóng gói vào `BOOT-INF/classes/` cùng class Java; ví dụ `BOOT-INF/classes/application.properties` hoặc `BOOT-INF/classes/static/logo.png`. Với executable WAR, vị trí tương ứng là `WEB-INF/classes/`. **`processResources`/`resources:resources` chuẩn bị tài nguyên**, còn task đóng gói có nhiệm vụ đặt chúng vào archive.

## 2. Ba khái niệm dễ nhầm: copy, filter và resolve lúc chạy

Xem file nguồn:

```properties
# src/main/resources/application.properties
spring.application.name=demo
server.port=${APP_PORT:8080}
```

- **Copy:** giữ nguyên byte/nội dung file và chuyển sang thư mục đầu ra.
- **Filter (thay giá trị tại build time):** biến token như `@project.version@` (Maven) hoặc `${appVersion}` (Gradle expand) thành giá trị cụ thể **trước khi tạo JAR**.
- **Resolve tại runtime:** Spring Boot đọc `${APP_PORT:8080}` khi ứng dụng chạy, tìm property `APP_PORT` và dùng `8080` nếu không có. Đây là việc của Spring Environment, **không phải Maven/Gradle bắt buộc thay token**.

Với ví dụ trên, điều mong đợi khi **không chủ ý filter `application.properties`** là file sau build vẫn có `server.port=${APP_PORT:8080}`. Nếu lỡ dùng Gradle `expand` lên toàn bộ resources, biểu thức `${APP_PORT:8080}` có thể bị SimpleTemplateEngine coi là biểu thức template và gây lỗi hoặc làm thay giá trị sớm.

**Quy tắc thiết kế:** giá trị **cố định theo artifact** như phiên bản dự án có thể lọc ở build time; giá trị **phụ thuộc môi trường khi khởi chạy** như port, URL dịch vụ và thông tin đăng nhập nên nhận từ cấu hình runtime/biến môi trường hoặc cơ chế quản lý bí mật. Không đưa password/token vào file được filter rồi đóng gói.

### Hai câu hỏi khi xem file trong JAR

1. File này **được copy** từ đâu, theo task nào?
2. Nếu giá trị khác với file nguồn, **ai đã filter/transform**, bằng property và cú pháp delimiter nào?

Đừng kết luận Spring Boot đã tự sửa file chỉ vì lúc chạy giá trị trả về khác: Spring có thể resolve placeholder động mà file lưu trong JAR vẫn nguyên.

## 3. Maven Resources Plugin: goal và lifecycle

Trong Maven, `maven-resources-plugin` xử lý các resource được khai báo ở `<build><resources>` hoặc `<build><testResources>` và được liên kết vào lifecycle.

| Goal | Phase thông thường | Nguồn mặc định | Đầu ra mặc định |
| --- | --- | --- | --- |
| `resources:resources` | `process-resources` | `src/main/resources` | `target/classes` |
| `resources:testResources` | `process-test-resources` | `src/test/resources` | `target/test-classes` |
| `resources:copy-resources` | Không tự có cùng ràng buộc mặc định; cần cấu hình khi sử dụng | Nguồn do goal được cấu hình | Thư mục do goal được cấu hình |

Các goal `resources:resources` và `resources:testResources` có thể chạy độc lập hoặc tự chạy khi Maven đi qua phase tương ứng của một project đóng gói Java.

```bash
# Chạy lifecycle đến giai đoạn copy main resources
./mvnw process-resources

# Gọi trực tiếp plugin goal cho main resources
./mvnw resources:resources

# Xử lý test resources
./mvnw process-test-resources

# Sau khi copy: biên dịch và đóng gói theo lifecycle
./mvnw package
```

Trên Windows PowerShell:

```powershell
.\mvnw.cmd process-resources
.\mvnw.cmd resources:resources
.\mvnw.cmd process-test-resources
```

`process-resources` là **tên phase của lifecycle**; `resources:resources` là **goal của plugin**. Hai lệnh thường đạt cùng mục đích trong một POM Java thông thường, nhưng **không nhất thiết cùng toàn bộ chuỗi hành động**: phase có thể chạy thêm execution được gắn vào nó, còn gọi goal trực tiếp thì chỉ chạy goal cụ thể. Khi nghi ngờ plugin chạy thêm lần, đọc `effective-pom` và log lifecycle.

### Mặc định có tự thay token không?

Trong Maven Resources Plugin nói chung, nếu không bật `filtering` cho một resource, nó được copy mà **không thay nội dung**. Ví dụ file `hello.txt` có `Hello ${name}` sẽ giữ nguyên token nếu nguồn không được bật filtering.

Tuy nhiên, một project Spring Boot **kế thừa `spring-boot-starter-parent`** có cấu hình hợp lý dành cho `application.properties`/`application.yml` và biến thể profile. Parent đó sử dụng delimiter `@...@` để tránh xung đột cú pháp `${...}` của Spring. **Đây là cấu hình do parent cung cấp**, không phải mặc định của mọi POM Maven. Project chỉ import `spring-boot-dependencies` BOM mà không kế thừa parent thì không được tự giả định có filtering đó.

Để biết **POM hiện tại có quy tắc gì**, hãy xem:

```bash
./mvnw help:effective-pom -Doutput=effective-pom.xml
```

Tìm `<resources>`, `<testResources>`, `<filtering>` và `maven-resources-plugin` trong POM hiệu lực. Một dòng `@project.version@` ở resource nguồn **không tự thay** nếu file không nằm trong tập resources được bật filtering hoặc delimiter không phù hợp.

## 4. Maven: cấu hình copy và filtering có kiểm soát

### 4.1 Một ví dụ độc lập, lọc đúng một file

Giả sử POM của project đã khai báo:

```xml
<groupId>com.example</groupId>
<artifactId>demo</artifactId>
<version>1.2.3</version>
```

Đây chỉ là **trích đoạn định danh POM**, không phải POM hoàn chỉnh. Tạo file:

```properties
# src/main/resources/build-info.properties
app.version=@project.version@
```

Một `pom.xml` **đã có Spring Boot parent với delimiter `@...@`** có thể dùng trích đoạn sau trong phần `<build>` để lọc **riêng file đó**:

```xml
<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>true</filtering>
            <includes>
                <include>build-info.properties</include>
            </includes>
        </resource>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>false</filtering>
            <excludes>
                <exclude>build-info.properties</exclude>
            </excludes>
        </resource>
    </resources>
</build>
```

**Cách đọc cấu hình:**

1. Nhóm `<resource>` đầu tiên chỉ xử lý `build-info.properties` và bật `filtering=true`.
2. Nhóm thứ hai copy các tài nguyên **còn lại** mà không lọc.
3. Dùng hai nhóm tránh xử lý ảnh `png`, `jpg`, font hoặc file nhị phân bằng cơ chế đọc và ghi text.
4. `<includes>` và `<excludes>` dùng mẫu đường dẫn tương đối đối với thư mục đã khai báo. `<filtering>false</filtering>` nói rằng chỉ copy, không thay token.
5. Việc **định nghĩa lại toàn bộ `<resources>`** như ví dụ có thể **thay thế quy tắc resource kế thừa từ Spring Boot parent**, trong đó có cấu hình lọc `application*.properties`/`application*.yml`. Nếu dự án hiện tại dựa vào cách filter sẵn của parent, hãy giữ/điều chỉnh cấu hình đó khi bổ sung resource, thay vì chép máy móc nguyên khối ví dụ.

Nếu không kế thừa parent và muốn **chỉ dùng delimiter `@...@`** thay vì cả `${...}`, cấu hình thêm plugin trong `<build><plugins>`:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-resources-plugin</artifactId>
    <configuration>
        <delimiters>
            <delimiter>@</delimiter>
        </delimiters>
        <useDefaultDelimiters>false</useDefaultDelimiters>
        <encoding>UTF-8</encoding>
    </configuration>
</plugin>
```

Đây cũng là **trích đoạn plugin**; project không dùng parent nên phải chọn phiên bản plugin phù hợp trong `<version>` hoặc `<pluginManagement>`, và đặt cấu hình vào đúng phần POM. `<useDefaultDelimiters>false</useDefaultDelimiters>` rất quan trọng: nếu không, các delimiter mặc định của Maven Resources Plugin có thể xử lý cả `${...}` của Spring. Không cần tự bổ sung plugin chỉ để "nhìn cho đủ" nếu effective POM đã cấu hình đúng.

### 4.2 Kết quả có thể dự đoán

Với `project.version=1.2.3` và lựa chọn lọc `build-info.properties` như trên:

```bash
./mvnw process-resources
```

Khi đó file `target/classes/build-info.properties` chứa đúng:

```properties
app.version=1.2.3
```

Trong cùng ví dụ, file `src/main/resources/application.properties` có:

```properties
spring.application.name=demo
server.port=${APP_PORT:8080}
```

Sau copy **không lọc file application.properties** theo cấu hình nhóm hai, nội dung tại `target/classes/application.properties` vẫn là:

```properties
spring.application.name=demo
server.port=${APP_PORT:8080}
```

Như vậy bản build biết `1.2.3`, còn Spring vẫn tự quyết định port lúc chạy. Đây là ví dụ về **ranh giới build time / runtime** có chủ đích.

### 4.3 Nếu muốn lọc file application của Spring Boot parent

Với project kế thừa `spring-boot-starter-parent` và chưa thay đổi cấu hình filtering mặc định của parent, bạn có thể khai báo:

```properties
spring.application.name=demo
app.version=@project.version@
server.port=${APP_PORT:8080}
```

Sau `process-resources`, `app.version` được thay theo Maven POM trong khi `server.port=${APP_PORT:8080}` được giữ lại cho Spring runtime. **Không lấy hành vi này làm mặc định nếu project đã override `<resources>`, delimiter hoặc không dùng Boot parent.**

### 4.4 Các nguồn property và file filter

Maven filtering có thể dùng project properties, system properties, filter file và giá trị truyền vào theo cách Maven hỗ trợ. Ví dụ project khai báo:

```xml
<properties>
    <app.buildLabel>release</app.buildLabel>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

Resource có `app.label=@app.buildLabel@`, khi filtering hoạt động thì được thay thành `app.label=release`. Nếu dùng `<build><filters>` để đọc file `.properties` chứa giá trị build, phải kiểm soát file filter tương ứng; lưu ý file giá trị có thể chứa thông tin nhạy cảm và tuyệt đối không đóng gói bí mật vào artifact.

Một lưu ý thường bị bỏ qua: `filtering=true` không có nghĩa **mọi placeholder lạ** đều bị thay đúng. Tên property phải tồn tại trong nguồn mà plugin đọc, delimiter phải khớp, và escape/encoding phải phù hợp. Nếu token còn nguyên, hãy điều tra **nguồn giá trị, delimiters, <resources> và effective POM** trước.

## 5. Gradle `processResources`: task Copy của Java plugin

Khi áp dụng Gradle `java` hoặc `java-library`, source set `main` có task `processResources` và source set `test` có task `processTestResources`. Chúng là các tác vụ dạng copy/transform file được mô tả bởi Gradle Java plugin.

```text
src/main/java                --> compileJava ------> build/classes/java/main
src/main/resources           --> processResources -> build/resources/main
                                        \                 /
                                         +-- classes ---+
                                               |
                                        jar / bootJar / runtime classpath

src/test/resources           --> processTestResources -> build/resources/test
```

Sơ đồ thể hiện quan hệ khái niệm. Task graph chính xác có thể có các task khác do plugin, source set và cấu hình project bổ sung.

Chạy trên dự án Gradle có Java plugin:

```bash
# Chỉ xử lý main resources
./gradlew processResources

# Xử lý test resources
./gradlew processTestResources

# Xem kế hoạch task mà chưa chạy
./gradlew classes --dry-run

# Chạy biên dịch + copy main resources
./gradlew classes
```

Windows PowerShell:

```powershell
.\gradlew.bat processResources
.\gradlew.bat processTestResources
.\gradlew.bat classes --dry-run
```

**Mặc định `processResources` chỉ copy**, không tự thay tất cả biến `${...}`. Đừng nhầm sự hiện diện của Spring Boot Gradle plugin `org.springframework.boot` với việc Gradle luôn filter resource. Task `processResources` đến từ **Gradle Java plugin**, còn Spring Boot plugin dùng kết quả source set để chạy/đóng gói khi áp dụng cùng Java plugin.

### 5.1 Cấu hình Groovy DSL: chỉ mở rộng một file

Ví dụ trong `build.gradle`, giả sử project dùng Java plugin (dùng Spring Boot plugin cũng không làm thay đổi nguyên lý này):

```groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.2.3'

def resourceVersion = project.version.toString()

tasks.named('processResources') {
    inputs.property('appVersion', resourceVersion)

    filesMatching('build-info.properties') {
        expand(appVersion: resourceVersion)
    }
}
```

Đây là cấu hình **Gradle Groovy DSL đầy đủ ở mức đủ để chạy task `processResources`** trong một project Gradle có Wrapper; nếu cần Spring Boot executable JAR, bạn áp dụng Spring Boot plugin và dependency của ứng dụng ở phần build khác.

File nguồn dùng **cú pháp Gradle SimpleTemplateEngine**:

```properties
# src/main/resources/build-info.properties
app.version=${appVersion}
```

Chạy:

```bash
./gradlew processResources
```

File `build/resources/main/build-info.properties` phải có:

```properties
app.version=1.2.3
```

Giải thích:

- `filesMatching('build-info.properties')` chỉ chọn file khớp mẫu để transform. Các file khác vẫn được copy nguyên trạng bởi task.
- `expand(appVersion: resourceVersion)` tạo một map tên `appVersion` → `1.2.3` cho template. Khi copy, token `${appVersion}` được thay.
- `inputs.property('appVersion', resourceVersion)` đăng ký giá trị được dùng bởi transformation là đầu vào task, giúp kiểm tra thay đổi khi Gradle thực hiện up-to-date check và cache. Trong build thật, các input khác của task được Gradle theo dõi theo cơ chế của nó.
- `version` của Gradle phải được định nghĩa, nếu không có thể nhận giá trị mặc định như `unspecified`.
- Mẫu này không dùng `expand(project.properties)` trên **toàn bộ resources**, vì làm vậy có nguy cơ diễn giải placeholder của Spring và nội dung template khác.

### 5.2 Kotlin DSL tương đương

Nếu file build là `build.gradle.kts`, dùng cú pháp Kotlin:

```kotlin
plugins {
    java
}

group = "com.example"
version = "1.2.3"

val resourceVersion = project.version.toString()

tasks.processResources {
    inputs.property("appVersion", resourceVersion)

    filesMatching("build-info.properties") {
        expand(mapOf("appVersion" to resourceVersion))
    }
}
```

Đây là cấu hình Kotlin DSL hoàn chỉnh về mặt processing trong một project Java Gradle. Không chép `expand(appVersion: resourceVersion)` của Groovy sang Kotlin DSL vì cách truyền map khác nhau. Khi dùng plugin `war`, Java plugin cũng được áp dụng và task `processResources` vẫn tồn tại.

### 5.3 Điều gì xảy ra với các file khác?

Giả sử resources chứa:

```text
src/main/resources/
├── build-info.properties
├── application.properties
├── static/logo.png
└── templates/home.html
```

Với `filesMatching('build-info.properties')`, chỉ file này được filter. `application.properties`, `static/logo.png` và `templates/home.html` được copy **không đổi** theo task. Do đó `server.port=${APP_PORT:8080}` vẫn giữ nguyên cho Spring đọc sau này và ảnh PNG không bị xử lý qua template engine.

Nếu chỉ muốn **bỏ qua** một file khỏi đầu ra, trong task `processResources` có thể dùng `exclude('path/relative/to/resources')`; với Maven có `<excludes>` tương đương về ý định. Exclude làm file **không vào đầu ra**, khác hoàn toàn với việc chỉ không filter nó.

## 6. Chú ý đặc biệt: placeholder của Spring Boot và Gradle

### Cú pháp trùng nhau nhưng thời điểm xử lý khác nhau

Spring runtime:

```properties
server.port=${APP_PORT:8080}
```

Gradle `expand` cũng sử dụng cú pháp `${...}` và có khả năng đánh giá biểu thức template bằng Groovy `SimpleTemplateEngine`. Nếu bạn viết:

```groovy
tasks.named('processResources') {
    expand(project.properties)
}
```

thì **toàn bộ file resources đi qua transformation**, kể cả `application.properties` nếu có. Trong đó `${APP_PORT:8080}` có thể bị hiểu thành cú pháp template không hợp lệ; khi một token tên biến tồn tại, nó còn có thể bị thay **ở build time** thay vì Spring resolve lúc chạy.

**Cách ưu tiên cho bài toán phiên bản build:** lọc duy nhất `build-info.properties` như ví dụ phần 5. Khi không nhất thiết gắn metadata vào `application.properties`, tách resource riêng là giải pháp dễ kiểm tra.

Nếu chủ động **filter chính `application.properties`** bằng Gradle, tài liệu Spring Boot cho biết cần escape placeholder của Spring. Ví dụ file nguồn:

```properties
app.version=${appVersion}
server.port=\${APP_PORT:8080}
```

Với task `processResources` được cấu hình `expand` **chỉ cho file đó**, `app.version` được thay bằng version, còn dấu escape trong nguồn giúp template engine để lại token Spring. Việc escape và dấu backslash trong YAML/Properties/Groovy phải được kiểm tra trực tiếp trên **file sau xử lý**, bởi template engine và Java properties/YAML có quy tắc escaping khác nhau.

Một cách triển khai ít phức tạp hơn là giữ cấu hình môi trường nguyên bản, đặt metadata build ở một resource riêng và chỉ lọc file đó. **Đừng xóa dấu escape bằng phỏng đoán** nếu chưa xem giá trị đầu ra thật.

### Với Maven Spring Boot parent, dùng `@...@`

Spring Boot Maven parent đổi delimiter resource filtering cho các file application thành `@...@` để có thể vừa dùng:

```properties
app.version=@project.version@
server.port=${APP_PORT:8080}
```

Ở cấu hình parent phù hợp, giá trị Maven được thay, còn placeholder Spring không bị Maven ăn mất. Nếu bạn **không kế thừa parent** hoặc đã bật Maven filtering thủ công với delimiter `${...}`, hãy cấu hình lại delimiter, ví dụ `<useDefaultDelimiters>false</useDefaultDelimiters>` và `<delimiter>@</delimiter>`, hoặc tách file được filter thành tài nguyên riêng.

### Không nhầm expansion với PropertyPlaceholder của Spring

Cùng một giá trị có thể tồn tại dưới ba dạng:

| Thời điểm | Biểu thức | Ai xử lý? |
| --- | --- | --- |
| Trong POM/build script | `project.version`/`version` | Maven hoặc Gradle khi cấu hình build |
| File resource ở build time | `@project.version@` hoặc `${appVersion}` | Maven Resources Plugin hoặc Gradle `expand` **nếu được bật** |
| Đang chạy ứng dụng | `${APP_PORT:8080}` | Spring Environment khi đọc cấu hình runtime |

Nếu gọi `java -jar` hai lần với hai biến môi trường khác nhau, một placeholder runtime có thể cho hai giá trị khác nhau mà **không phải rebuild**. Ngược lại, giá trị version đã filter vào file thì thường là một phần của artifact và không đổi chỉ vì biến môi trường runtime thay đổi.

## 7. Resource filtering trong Spring Boot packaging

### 7.1 Maven pipeline

Với POM Spring Boot dùng packaging `jar`:

```text
src/main/resources/
       |
       v
resources:resources          (process-resources)
       |
       v
target/classes/              (+ class từ compiler:compile)
       |
       v
jar:jar / spring-boot:repackage theo lifecycle đã cấu hình
       |
       v
target/<artifact>-<version>.jar
       |
       v
BOOT-INF/classes/...          (executable Spring Boot JAR)
```

`spring-boot-maven-plugin` không phải chính `maven-resources-plugin`. Plugin Resources chịu trách nhiệm copy/filter; plugin Boot chịu trách nhiệm tạo/repackage archive thực thi theo cấu hình hiện có. Một build có thể thay đổi thứ tự plugin executions tùy POM, vì vậy kiểm tra log và effective POM khi có customization.

### 7.2 Gradle pipeline

```text
src/main/resources/ --> processResources --> build/resources/main/
src/main/java/      --> compileJava     --> build/classes/java/main/
                                 \          /
                                    classes
                                      |
                                      v
                            jar / bootJar / bootWar
                                      |
                                      v
                              build/libs/...
```

`bootJar` và `bootWar` là task thuộc Spring Boot Gradle plugin khi dùng cùng Java/War plugin, còn `processResources` đến từ Java plugin. Cần file đã xử lý ở source set output trước khi đóng gói. Task `jar` thường đặt tài nguyên cùng package ở root archive; `bootJar` đặt class/resource chính dưới `BOOT-INF/classes`. Cần nhìn đúng archive khi kiểm tra.

### 7.3 Cách xác minh trong archive

Sau khi build, có thể liệt kê nội dung bằng `jar tf` (công cụ JDK, không cần code Java):

```bash
# Maven, khi pom.xml có cấu hình Spring Boot executable JAR
./mvnw package
jar tf target/demo-1.2.3.jar

# Gradle, khi đã áp dụng Spring Boot + java
./gradlew bootJar
jar tf build/libs/demo-1.2.3.jar
```

Tên archive `demo-1.2.3.jar` chỉ là **ví dụ**, phụ thuộc `artifactId`, `rootProject.name`, `version` và `archiveBaseName`. Trong output của `jar tf`, tìm `BOOT-INF/classes/build-info.properties` và `BOOT-INF/classes/application.properties`. `jar tf` liệt kê **tên file**, không hiển thị nội dung giá trị đã filter; muốn đọc nội dung thì xem `target/classes` / `build/resources/main` hoặc giải nén/inspect đúng archive.

Không thể kết luận resource bị mất chỉ vì tìm trong `build/classes/java/main`: ở Gradle, resource mặc định nằm ở `build/resources/main` và hai thư mục được ghép trong classpath/source set output.

## 8. Kiểm chứng bằng Java 17+: resource thực sự có trong classpath

Ví dụ độc lập về cách Java đọc resource sau Maven/Gradle processing. Tạo file `src/main/java/com/example/demo/ResourceProbe.java`:

```java
package com.example.demo;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class ResourceProbe {

    public static void main(String[] args) throws IOException {
        Properties properties = new Properties();

        try (InputStream input = ResourceProbe.class.getClassLoader()
                .getResourceAsStream("build-info.properties")) {
            if (input == null) {
                throw new IllegalStateException(
                        "Missing build-info.properties on classpath");
            }
            properties.load(input);
        }

        System.out.println("app.version=" + properties.getProperty("app.version"));
    }
}
```

Đây là **lớp Java hoàn chỉnh, chạy được với JDK 17+** trong project Java. Không cần Spring Boot để đọc file bằng `ClassLoader` và `java.util.Properties`. Nó sẽ tìm `build-info.properties` **trên classpath**, không phụ thuộc thư mục làm việc của tiến trình.

Nếu file nguồn `build-info.properties` được xử lý thành `app.version=1.2.3` theo hai ví dụ trên, dòng stdout từ **chính `ResourceProbe`** là:

```text
app.version=1.2.3
```

Maven (ứng dụng có POM Java hợp lệ và Wrapper):

```bash
./mvnw compile
java -cp target/classes com.example.demo.ResourceProbe
```

Gradle (ứng dụng có Java plugin và Wrapper; macOS/Linux dùng dấu `:` trong classpath):

```bash
./gradlew classes
java -cp build/classes/java/main:build/resources/main com.example.demo.ResourceProbe
```

Windows PowerShell:

```powershell
.\mvnw.cmd compile
java -cp target\classes com.example.demo.ResourceProbe

.\gradlew.bat classes
java -cp "build\classes\java\main;build\resources\main" com.example.demo.ResourceProbe
```

Chỉ chạy **bộ lệnh tương ứng công cụ build của dự án**. Nếu resource bị loại bởi include/exclude hoặc tên đường dẫn sai, Java sẽ ném `IllegalStateException` với message `Missing build-info.properties on classpath`. Nếu resource chưa được filter, stdout có thể in nguyên token như `@project.version@` hoặc `${appVersion}` — đó là bằng chứng vấn đề **xử lý build**, không phải vấn đề `ClassLoader`.

**Phân biệt:** output ví dụ chỉ áp dụng với `version=1.2.3`, file nguồn, quy tắc filter và classpath đã mô tả. Không đoán stdout log của toàn bộ Maven/Gradle/Spring Boot vì còn phụ thuộc phiên bản plugin và môi trường.

## 9. Include/exclude, mã hóa, file nhị phân và file trùng

### 9.1 Chỉ copy đúng những file cần thiết

Maven: mỗi `<resource>` có thể có `<directory>`, `<includes>`, `<excludes>`, `<filtering>`; có thể dùng `<targetPath>` nếu muốn đổi vị trí tương đối trong output.

Gradle: `processResources` là task dạng Copy, có `include`/`exclude` và `filesMatching`. Ví dụ Groovy DSL:

```groovy
tasks.named('processResources') {
    exclude('private-notes/**')

    filesMatching('build-info.properties') {
        expand(appVersion: project.version.toString())
    }
}
```

Ở đây `private-notes/**` bị **loại khỏi sản phẩm**, còn `build-info.properties` được transform. Nếu file chỉ là resource runtime nhạy cảm, cách phù hợp thường là **không chứa bí mật trong repo/artifact**; dùng biến môi trường hoặc secret store. Exclude chỉ kiểm soát build output, không phải biện pháp tự động xóa lịch sử Git.

### 9.2 Vì sao không filter ảnh/nhị phân?

Maven Resources Plugin filtering và Gradle `expand` về cơ bản xử lý văn bản. Khi cố đọc ảnh PNG, file PDF, font hay JAR như text, có thể làm hỏng byte. Maven Resources Plugin có các đuôi nhị phân mặc định không filter và hỗ trợ `nonFilteredFileExtensions`; các đuôi mặc định phụ thuộc phiên bản plugin. Thay vì trông cậy hoàn toàn vào danh sách extension, hãy **chỉ bật filtering cho file text cần thay biến**.

Nếu bắt buộc xử lý file text riêng nhưng thư mục chứa đủ loại tệp, dùng **hai resource groups Maven** như phần 4 hoặc **`filesMatching` Gradle** như phần 5 để giữ các file khác nguyên bản.

### 9.3 Encoding của file lọc

Nếu template có tiếng Việt, encoding sai có thể khiến ký tự có dấu bị lỗi sau build. Maven Resources Plugin đọc `encoding` từ `project.build.sourceEncoding` theo mặc định và có `propertiesEncoding` cho file `.properties` ở các phiên bản hỗ trợ. Ví dụ:

```xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

Chọn encoding phù hợp với nội dung thật của file và parser dùng ở runtime. Với Java `Properties.load(InputStream)` truyền thống, mã hóa được diễn giải theo chuẩn ISO-8859-1/escape của API; nếu bạn cần UTF-8 cho nội dung tiếng Việt, có thể dùng `Properties.load(Reader)` với `InputStreamReader(StandardCharsets.UTF_8)` hoặc cơ chế Spring Boot hỗ trợ. Ví dụ `ResourceProbe` chỉ đọc giá trị ASCII `1.2.3` nên không gặp vấn đề mã hóa dấu tiếng Việt.

Gradle `expand` cũng là phép xử lý text; mã hóa, escape backslash và template engine có thể ảnh hưởng nội dung. Với phiên bản Gradle hỗ trợ, `expand(map) { escapeBackslash = true }` giúp tránh một số chuyển đổi escape không mong muốn; chỉ dùng sau khi đã đối chiếu API/phiên bản Gradle hiện tại và kiểm tra file đầu ra.

### 9.4 Trùng đường dẫn đích

Ví dụ bạn thêm cả `src/main/resources` và thư mục tài nguyên khác chứa `application.properties` vào cùng output. Hai file có thể cùng đích. Maven chịu ảnh hưởng thứ tự tập resource và quy tắc overwrite/change detection; Gradle có `duplicatesStrategy` và có thể phát sinh lỗi/ghi đè theo cấu hình và phiên bản.

Khi thấy một file trong JAR có nội dung **khác dự kiến**, kiểm tra mọi nguồn được khai báo, đường đích tương đối, số task/execution xử lý và thứ tự chạy, trước khi kết luận plugin tự ngẫu nhiên sửa file.

Không thêm bản sao resource ở `src/main/java` chỉ để "đảm bảo đóng gói": cách này tạo nguồn sai chỗ và có nguy cơ trùng classpath.

## 10. Test resources khác main resources ở đâu?

Maven:

- `src/main/resources` → `resources:resources` → `target/classes`.
- `src/test/resources` → `resources:testResources` → `target/test-classes`.
- Với Spring Boot Maven parent, cấu hình lọc application resource thường dành cho **production resources**, không có nghĩa test resources được lọc y hệt. Nếu test cần filter, cấu hình `<testResources>` riêng có chủ đích.

Gradle:

- `src/main/resources` → `processResources` → `build/resources/main`.
- `src/test/resources` → `processTestResources` → `build/resources/test`.
- `tasks.named('processResources')` chỉ tùy chỉnh **main resources**. Nếu muốn thay token trong test resources, hãy thêm cấu hình `processTestResources` rõ ràng; đừng tưởng hai task tự dùng chung rules.
- Classpath kiểm thử thường chứa resource của test và main; nếu trùng tên, thứ tự classpath có thể ảnh hưởng file được đọc, tùy runner/test task. Đừng dựa vào giả định mơ hồ; dùng `ClassLoader.getResource(...)` để xem URL thực tế khi cần.

Ví dụ một file `src/test/resources/application-test.properties` nên mô tả cấu hình kiểm thử, không nhất thiết được đóng vào executable JAR. Nếu bạn chỉ thấy file trong `target/test-classes` hoặc `build/resources/test` nhưng không thấy trong JAR phát hành, đó là **phân tách đúng mục đích** chứ không mặc định là lỗi.

## 11. Incremental build, UP-TO-DATE và vấn đề stale resource

Khi file nguồn hoặc cấu hình transform không đổi, Gradle có thể báo task `processResources UP-TO-DATE` hoặc `FROM-CACHE`. Điều này thường là bình thường: hệ thống build đã theo dõi các input/output mà task khai báo. Nếu có một giá trị ngoài file nguồn tác động expansion, hãy khai báo nó bằng `inputs.property(...)` (như `appVersion` ở ví dụ) để Gradle biết lúc nào phải chạy lại.

Maven Resources Plugin cũng có logic quyết định khi nào cần copy/ghi đè resource. Hành vi chi tiết phụ thuộc phiên bản plugin và cấu hình, không nên suy luận "cứ Maven chạy là mọi file được ghi lại".

**Cách kiểm tra khi nội dung cũ vẫn xuất hiện:**

1. Xem đúng file nguồn, đúng resource directory và đúng output path.
2. In/kiểm tra giá trị phiên bản đầu vào tại thời điểm build.
3. Kiểm tra build đang chạy trên đúng module và đúng Wrapper.
4. Kiểm tra Gradle task được skip vì `UP-TO-DATE`/`FROM-CACHE` hay Maven plugin có bỏ qua copy.
5. Khi cần xác nhận, chạy build sạch trên **môi trường hoặc nhánh thực hành**, rồi so file đầu ra; tránh tự xóa dữ liệu ở workspace dùng chung.

`./mvnw clean process-resources` hoặc `./gradlew clean processResources` là các lệnh hữu ích trong project test, nhưng `clean` sẽ xóa thư mục đầu ra build; chỉ dùng ở môi trường bạn có quyền làm sạch. Nếu một lần clean làm kết quả đúng, cần tìm nguyên nhân tại input/task/cache/đường dẫn thay vì luôn dựa vào clean như "giải pháp" cố định.

## 12. Bảng so sánh nhanh Maven và Gradle

| Tiêu chí | Maven Resources Plugin | Gradle processResources |
| --- | --- | --- |
| Tên việc | Goal `resources:resources` | Task `processResources` |
| Vị trí trong pipeline | Phase `process-resources` | Task thuộc Java source set `main` |
| Nguồn main mặc định | `src/main/resources` | `src/main/resources` |
| Đầu ra main mặc định | `target/classes` | `build/resources/main` |
| Đầu ra test mặc định | `target/test-classes` | `build/resources/test` |
| Cấu hình nguồn | POM `<resources>`/`<resource>` | `sourceSets` và Copy task |
| Bật filtering | `<filtering>true</filtering>` trên resource group | `expand` hoặc bộ lọc khác trong task |
| Chọn file để filter | `includes/excludes` và nhóm resource | `filesMatching(...)` |
| Cú pháp token | Thường `${name}` hoặc `@name@` theo delimiter | `${name}`/`$name` theo `SimpleTemplateEngine` |
| Tránh đụng Spring `${...}` | Spring Boot parent dùng `@...@` và có thể cấu hình delimiter | Chỉ filter file cần thiết hoặc escape Spring placeholder |
| Test resources | `resources:testResources` | `processTestResources` |
| Đóng gói Spring Boot | Resources xử lý xong rồi Boot plugin repackage | Task Boot lấy source set output đã xử lý |
| Kiểm chứng | Xem `target/classes` và nội dung JAR | Xem `build/resources/main` và nội dung JAR |

Bảng trình bày hành vi chuẩn của Java project, **không thay thế việc đọc cấu hình thực tế**. Đặc biệt, plugin Spring Boot và các plugin khác có thể thay đổi tập resource, task graph, delimiter và tên archive.

## 13. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân nên xét | Cách kiểm tra/giải quyết |
| --- | --- | --- |
| File ở `src/main/resources` nhưng thiếu ở output | Exclude/include sai, sourceSets thay đổi, task chưa chạy, build ở module khác | Xem POM effective resources hoặc Gradle sourceSets; gọi goal/task xử lý resources và kiểm tra đúng thư mục |
| Token `@project.version@` còn nguyên trong Maven output | Chưa bật filtering trên file, thiếu delimiter `@`, POM không có property/parent tương ứng | Xem `<filtering>`, `<delimiters>`, `<useDefaultDelimiters>` và effective POM |
| Token `${appVersion}` còn nguyên trong Gradle output | `expand` chưa áp dụng cho file, `filesMatching` sai, map không chứa key | Xem task `processResources` và file tại `build/resources/main` |
| Maven đổi mất `${APP_PORT:8080}` | Filtering dùng delimiter `${...}` trên Spring config | Chọn `@...@` với `useDefaultDelimiters=false` hoặc không filter file đó |
| Gradle `expand` lỗi khi gặp placeholder Spring | `SimpleTemplateEngine` cố xử lý `${...}` của Spring | Chỉ filter file build-info; nếu filter application, escape đúng token Spring và verify output |
| Ảnh/binary bị hỏng sau build | Toàn bộ thư mục đã bị text filter | Tách file cần filter hoặc dùng `filesMatching`; không biến đổi binary |
| Dấu tiếng Việt thành ký tự lỗi | Encoding nguồn/filter/parser runtime không nhất quán | Chốt charset, kiểm tra UTF-8/`propertiesEncoding`/cách Java đọc properties |
| `processResources` UP-TO-DATE dù version kỳ vọng đổi | Input expansion bên ngoài chưa được khai báo hoặc đang kiểm tra sai module/output | Thêm `inputs.property` phù hợp, kiểm tra Gradle logs và file nguồn |
| Resource có ở `build/resources/main` nhưng không thấy trong `build/classes/java/main` | Đó là hai thư mục output riêng của Gradle | Kiểm tra `build/resources/main` hoặc JAR, không tìm sai chỗ |
| Có file trong test nhưng thiếu ở JAR sản phẩm | Test resource không thuộc main artifact | Đưa file cần runtime vào `src/main/resources` nếu phù hợp, không copy test data tùy tiện |
| Có nhiều bản `application.properties` với nội dung lạ | Nhiều resource root/trùng đường dẫn, filter chồng nhau | Kiểm tra include/exclude, bản output cuối cùng, task graph, `duplicatesStrategy` |
| Chạy từ IDE thấy config khác JAR | IDE có thể đọc resource trực tiếp/tự copy, build output đã cũ hoặc đang dùng profile khác | Chạy qua Wrapper, so file nguồn và file trong artifact, xác định classpath IDE |
| Secret xuất hiện trong JAR | Lọc build-time dữ liệu nhạy cảm vào resource | Loại bỏ secret khỏi artifact/source và dùng secret management/runtime configuration |

### Ví dụ phương pháp tìm nguyên nhân, không đoán

Nếu trong ứng dụng `app.version` in ra `@project.version@` thay vì `1.2.3`, trình tự điều tra hợp lý là:

1. Nhìn file `src/main/resources/build-info.properties` để xác nhận token.
2. Mở POM hiệu lực hoặc Gradle task để xem file có thật sự được filter không.
3. Xem `target/classes/build-info.properties` / `build/resources/main/build-info.properties`. **Nếu output vẫn nguyên token, lỗi nằm ở build-time filtering.**
4. Nếu output đúng nhưng ứng dụng in sai, kiểm tra classpath hoặc JAR đang chạy; có thể ứng dụng dùng artifact cũ, profile khác hoặc một resource cùng tên ở vị trí khác.
5. Xác nhận bằng lệnh `ResourceProbe` ở phần 8 và tệp phát hành thật. Chỉ thay đổi một nguyên nhân mỗi lần để dễ đánh giá.

Cách này cũng áp dụng cho YAML, template và messages: luôn tách "nguồn", "output sau process" và "resource được tải lúc chạy" thành ba bằng chứng khác nhau.

## 14. Bài thực hành có thể tự kiểm chứng

### Phần A – Maven

Dùng project Spring Boot Maven (hoặc Java Maven), đặt version `1.2.3` trong POM, tạo `src/main/resources/build-info.properties` chứa `app.version=@project.version@`. Nếu project dùng Boot parent, hãy đọc các quy tắc resource filtering sẵn có trước khi bổ sung cấu hình hai nhóm resource từ phần 4.

1. Chạy `./mvnw process-resources` và mở `target/classes/build-info.properties`.
2. Giải thích vì sao file đó có `app.version=1.2.3`; chỉ ra property gốc và delimiter.
3. Thêm `application.properties` có `server.port=${APP_PORT:8080}` và xác nhận token Spring vẫn còn nguyên **theo cấu hình không filter application ở ví dụ**.
4. Tạo `src/test/resources/test-data.json`, chạy `./mvnw process-test-resources`, giải thích vì sao file ở `target/test-classes`.
5. Dùng `ResourceProbe` để đọc giá trị từ classpath, kiểm tra stdout chính xác.
6. Trả lời: khác nhau giữa `process-resources` (phase) và `resources:resources` (goal) là gì? Điều gì thay đổi nếu kế thừa Boot parent?

### Phần B – Gradle

Dùng project Gradle có Java plugin, đặt `version = '1.2.3'`, cấu hình `processResources` bằng `filesMatching` + `expand` như phần 5.

1. Tạo `build-info.properties` chứa `app.version=${appVersion}`.
2. Chạy `./gradlew processResources`, kiểm tra `build/resources/main/build-info.properties`.
3. Giữ `application.properties` có `server.port=${APP_PORT:8080}` và xác nhận không bị filter.
4. Thêm một ảnh nhỏ vào `src/main/resources/static`, xác nhận ảnh được copy như file byte ban đầu, không đi qua template engine.
5. Chạy `./gradlew classes`, dùng `ResourceProbe` với classpath gồm **cả** `build/classes/java/main` và `build/resources/main`.
6. Thay version thành `1.2.4` trên nhánh thử nghiệm và chạy lại `processResources`, xác nhận output đổi thành `1.2.4` nhờ input property đã khai báo.
7. Nếu có Spring Boot Gradle plugin, chạy `bootJar` và xác định `BOOT-INF/classes/build-info.properties` trong executable archive.

### Phần C – So sánh và giải thích

Trả lời bằng cấu trúc:

- "**Nguồn:** file này đặt ở ..., có nội dung ...".
- "**Công cụ xử lý:** Maven goal ... / Gradle task ...".
- "**Quy tắc:** lọc file ... bằng delimiter ... với giá trị ...".
- "**Đầu ra build:** tôi đã đọc trực tiếp file tại ... và thấy ...".
- "**Runtime:** Java/Spring tải resource qua classpath hoặc Spring Environment resolve placeholder còn lại ...".
- "**Đóng gói:** file nằm tại ... bên trong executable JAR/WAR".

**Tiêu chí đạt:** trình bày được ít nhất một file đã filter và một file không filter trong **mỗi** công cụ; chỉ ra đúng output path, chứng minh được `ResourceProbe` đọc từ classpath, giải thích sự khác nhau giữa token build-time và placeholder runtime, và không làm hỏng file nhị phân.

## Tài liệu chính thức để đối chiếu

- Apache Maven Resources Plugin – Introduction/Goals: https://maven.apache.org/plugins/maven-resources-plugin/
- Maven Resources Plugin – Usage (`resources`, `testResources`): https://maven.apache.org/plugins/maven-resources-plugin/usage.html
- Apache Maven – Guide to Filtering Resources: https://maven.apache.org/guides/mini/guide-filtering-resources.html
- Maven Resources Plugin – Include/Exclude: https://maven.apache.org/plugins/maven-resources-plugin/examples/include-exclude.html
- Spring Boot – Maven Plugin, dùng Spring Boot parent và filtering `@..@`: https://docs.spring.io/spring-boot/3.3/maven-plugin/using.html
- Spring Boot – Properties and Configuration, tự mở rộng properties tại build time: https://docs.spring.io/spring-boot/how-to/properties-and-configuration.html
- Gradle – Building Java/JVM Projects, managing resources: https://docs.gradle.org/current/userguide/building_java_projects.html
- Gradle – ProcessResources DSL: https://docs.gradle.org/current/dsl/org.gradle.language.jvm.tasks.ProcessResources.html

**Ghi nhớ:** resource pipeline có ba lớp cần kiểm tra riêng: **file nguồn → file sau xử lý trong build output → file/giá trị mà ứng dụng thực sự dùng**. Maven Resources Plugin và Gradle `processResources` xử lý lớp thứ hai; Spring Boot xử lý cấu hình lúc chạy và đóng gói dựa trên kết quả đó.

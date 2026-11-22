# Kiểm tra ảnh hưởng của phụ thuộc provided, compileOnly và developmentOnly

## Mục tiêu học tập

Khi tùy biến đóng gói Spring Boot, một dependency có thể **xuất hiện lúc biên dịch**, **có khi chạy test hoặc chạy ở máy lập trình**, nhưng lại **không có trong JAR/WAR phát hành**. Điều ngược lại cũng xảy ra: dependency được khai báo `provided`, tưởng đã loại khỏi runtime, nhưng Spring Boot lại **cố ý đóng nó vào executable JAR/WAR**. Nếu chỉ nhìn tên scope/configuration và đoán, người học rất dễ làm hỏng WAR, khiến test thiếu Servlet runtime, đưa DevTools lên production hoặc tạo artifact chạy được trên máy mình nhưng lỗi ngoài môi trường triển khai.

Bài này trả lời câu hỏi cụ thể: **phụ thuộc `provided`, `compileOnly`, `developmentOnly` ảnh hưởng tới những classpath và loại archive nào, và làm thế nào để chứng minh bằng công cụ build?**

Sau bài học, bạn có thể:

1. Phân biệt Maven `<scope>provided</scope>` với Gradle `compileOnly`, `developmentOnly` và `providedCompile`/`providedRuntime` của War plugin.
2. Lập ma trận **compile → test → development runtime → production runtime → executable JAR/WAR** cho từng dependency.
3. Giải thích vì sao Maven Spring Boot `repackage` **vẫn đưa `provided` vào executable JAR**, hoặc xếp chúng vào `WEB-INF/lib-provided` của executable WAR.
4. Cấu hình Spring Boot Gradle plugin dùng `developmentOnly` cho DevTools, `compileOnly` + `annotationProcessor` cho Lombok, `providedRuntime` cho Tomcat khi đóng WAR.
5. Điều tra đúng bằng Maven `dependency:tree`/`help:effective-pom`, Gradle `dependencies`/`dependencyInsight`, cùng `jar tf` trên **artifact cuối cùng**.
6. Thực hiện bài kiểm tra hồi quy cho CI, tránh nhầm bản plain/archive thực thi và tránh coi tên configuration là bằng chứng đủ mạnh.

**Phiên bản ví dụ:** Spring Boot **3.3.13**, Java **17**, Gradle 8.x hoặc Maven 3.6.3+ tương thích. Các lệnh và dependency được trình bày trong ngữ cảnh này. Khi dùng Spring Boot 4.x, các starter/khả năng plugin có thể thay đổi: phải đọc tài liệu của đúng phiên bản. Không cần nâng cấp dự án chỉ để làm theo ví dụ.

## 1. Trước khi nói `provided`, hãy tách năm tầng khác nhau

Một dependency không phải chỉ có trạng thái "có" hoặc "không". Nó có thể tham gia vào **nhiều tập classpath và artifact**:

| Tầng | Câu hỏi cần trả lời | Ví dụ nơi quan sát |
| --- | --- | --- |
| **Dependency declaration** | Project khai báo gì, dưới scope/configuration nào? | `pom.xml`, `build.gradle`, `build.gradle.kts` |
| **Compile classpath** | Java compiler thấy lớp/API nào? | Maven compile scope resolution; Gradle `compileClasspath` |
| **Test classpath** | Compile và chạy test có những thư viện nào? | Maven test classpath; Gradle `testCompileClasspath`/`testRuntimeClasspath` |
| **Development runtime** | Khi chạy từ IDE, `bootRun`/`spring-boot:run`, dependency nào hiện diện? | Runtime task và classpath của chế độ chạy phát triển |
| **Packaged runtime** | `java -jar` có những thư viện nào bên trong JAR/WAR? | `BOOT-INF/lib`, `WEB-INF/lib`, `WEB-INF/lib-provided` |
| **External container** | Servlet container/JDK/hạ tầng bên ngoài cung cấp thêm thư viện nào? | Tomcat/Jetty runtime, image và server config |

Bảng có sáu dòng vì "**đóng gói**" và "**môi trường cung cấp thêm**" thường bị gộp nhầm vào chữ runtime.

Một hình dung đơn giản:

```text
                    khai báo dependency
                           |
           +---------------+----------------+
           |               |                |
      compile Java       chạy test       chạy khi dev
           |               |                |
           +---------------+----------------+
                           |
                      build plugin
                           |
           +---------------+-------------------+
           |                                   |
       plain JAR/WAR                      Boot JAR/WAR
   classes + content                   classes + dependencies
        có chọn lọc                          có chọn lọc
                                               |
                                      java -jar / container
```

**Không suy luận ngược không có bằng chứng:** Maven dependency xuất hiện trong `dependency:tree` không có nghĩa nó nằm trong `BOOT-INF/lib`; Gradle `runtimeClasspath` có DevTools không có nghĩa `bootJar` cũng có; tệp JAR có trong `WEB-INF/lib-provided` không có nghĩa external Tomcat sẽ nạp nó cùng với `WEB-INF/lib`.

### 1.1 Ba câu hỏi tối thiểu cần ghi vào báo cáo

Với bất kỳ dependency cần kiểm tra, ghi **tọa độ** (`groupId:artifactId` hoặc `group:module`), **module ứng dụng**, **loại sản phẩm** và **phép kiểm tra**:

1. "Khi compile/test, lớp này đến từ đâu?"
2. "Khi chạy local và khi đóng gói phát hành, lớp này có mặt ở đâu?"
3. "Nếu thư viện bị loại khỏi archive thông thường, nó sẽ được container cung cấp hay bị thiếu thật?"

Nếu không chỉ rõ **JAR thường, Boot executable JAR, WAR thường hay Boot executable WAR**, một câu như "provided không được đóng gói" có thể đúng ở ngữ cảnh này nhưng sai ở ngữ cảnh khác.

## 2. Maven `provided`: bản chất scope và ngoại lệ quan trọng của Spring Boot

### 2.1 Maven dependency scope `provided`

Maven có các scope phổ biến: `compile` (mặc định), `runtime`, `test`, `provided`. Theo Maven dependency mechanism:

- `compile`: có trên compile, runtime và test classpath, thường truyền tới consumer.
- `runtime`: không cần khi compile main, nhưng cần khi chạy và test.
- `test`: chỉ sử dụng trong phạm vi biên dịch/chạy test.
- **`provided`**: project cần lớp khi **compile và test** nhưng **mong đợi JDK hoặc container cung cấp khi chạy**. Scope này **không nằm trong runtime classpath thông thường của Maven** và không truyền bắc cầu đến consumer như dependency compile.

Ví dụ trích đoạn Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-tomcat</artifactId>
    <scope>provided</scope>
</dependency>
```

Với **ứng dụng Spring Boot MVC deploy lên external Tomcat**, Tomcat là thành phần được container bên ngoài cung cấp; việc đặt embedded server ở provided có mục đích. Nhưng không có nghĩa nên đánh dấu **mọi** dependency ứng dụng là provided.

Một tình huống khác: biên dịch mã có `jakarta.servlet.http.HttpServletRequest` cho một WAR Servlet, Servlet API thường do external container cung cấp. Đây là khái niệm provided kinh điển. Với Spring Boot 3.x, package API là **`jakarta.servlet.*`**, không phải `javax.servlet.*` của các thế hệ Java EE trước.

### 2.2 Ma trận Maven core (chưa xét Spring Boot repackage)

| Maven scope | Compile main | Test compile/run | Main runtime classpath Maven | Cần container ngoài cung cấp? |
| --- | --- | --- | --- | --- |
| `compile` | Có | Có | Có | Không theo kỳ vọng scope |
| `runtime` | Không cần dùng khi compile main | Có | Có | Không theo kỳ vọng scope |
| `test` | Không | Có | Không | Không; test-only |
| **`provided`** | **Có** | **Có** | **Không** | **Có, theo tuyên bố của project** |

Ma trận là **quy tắc classpath của Maven core**, không mô tả đầy đủ mọi behavior của Spring Boot Plugin và một số trường hợp compiler/test plugin custom.

**Bẫy:** nếu chạy một app ngoài Spring Boot với `java -cp ...` bằng classpath Maven runtime đơn thuần, thư viện provided có thể không có, gây `ClassNotFoundException`. Điều đó phù hợp với scope `provided`: bạn đã nói thư viện được môi trường bên ngoài cung cấp.

### 2.3 Spring Boot Maven `repackage` vẫn có thể **đưa provided vào**

Đây là điểm quan trọng nhất của bài. Khi `spring-boot-maven-plugin` chạy goal `repackage`, tài liệu Spring Boot mô tả nó **bao gồm các dependency `provided` của project**, trừ khi dependency bị loại bởi các quy tắc exclusion thích hợp.

Đối với **executable JAR**:

```text
pom.xml:
  spring-boot-starter-tomcat  (provided)
               |
               v
maven-jar-plugin:jar             (JAR thường trước repackage)
               |
               v
spring-boot:repackage
               |
               v
target/demo-0.0.1-SNAPSHOT.jar
  BOOT-INF/lib/tomcat-embed-core-...jar       <- có thể có
  BOOT-INF/lib/tomcat-embed-websocket-...jar  <- tùy graph
```

**Đừng dùng `provided` như cách bảo đảm "thư viện này tuyệt đối không vào Boot JAR".** Với Spring Boot executable JAR, Boot có mục tiêu tạo artifact đủ dependency cho `java -jar`. Nếu muốn bỏ một artifact cụ thể khỏi output, dùng Spring Boot Maven Plugin `<excludes>` hoặc sửa thiết kế/scope, rồi kiểm tra artifact. Cẩn thận: loại dependency cần tại runtime có thể khiến JAR không chạy được.

Đối với **executable WAR**:

```text
target/demo-0.0.1-SNAPSHOT.war
  WEB-INF/classes/...                    <- ứng dụng
  WEB-INF/lib/...                        <- dependency ứng dụng
  WEB-INF/lib-provided/tomcat-embed-...  <- dependency provided
  org/springframework/boot/loader/...    <- hỗ trợ java -jar
```

Boot đặt provided dependencies ở **`WEB-INF/lib-provided`**, tránh xung đột với những lớp container ngoài đã cung cấp. Đồng thời, khi chạy executable WAR bằng `java -jar`, launcher Boot có thể dùng chúng cho môi trường nhúng.

So sánh:

- Maven **WAR thường** do `maven-war-plugin` đóng gói theo scope: provided dependency thường **không vào `WEB-INF/lib`**.
- Maven **Boot executable WAR** do `repackage`: provided được giữ trong `WEB-INF/lib-provided`, **không phải biến mất**.
- Maven **Boot executable JAR**: provided có thể nằm trong `BOOT-INF/lib` vì không có external servlet container tự cấp khi chạy độc lập.

### 2.4 `optional` không đồng nghĩa `provided`

`<optional>true</optional>` chủ yếu ảnh hưởng **truyền dependency bắc cầu tới project tiêu thụ**. Nó không có nghĩa "dependency không còn trên classpath của project này". Một module thư viện có thể đánh dấu dependency optional để consumer lựa chọn. Với Spring Boot 3.3 Maven plugin, đừng dựa vào optional như một cơ chế tổng quát để bỏ dependency khỏi executable archive; các ngoại lệ built-in như `spring-boot-devtools` có cách loại riêng.

Ví dụ:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <optional>true</optional>
</dependency>
```

Spring Boot Maven Plugin có `excludeDevtools` mặc định bật; điều này **khác** với ngữ nghĩa Maven optional. Với WAR, việc phân loại DevTools và Docker Compose thành optional hoặc provided còn liên quan điều kiện loại của plugin. Kết luận phải dựa trên **POM hiệu lực + cấu hình plugin + file được repackage**.

### 2.5 Khi nào dùng provided là sai?

- JDBC driver thật sự phải được ứng dụng mang theo và container không cung cấp, nhưng bị chuyển thành provided chỉ để giảm dung lượng.
- Thư viện JSON, client HTTP hoặc framework dùng lúc runtime bị đánh dấu provided dù không có bên thứ ba cấp.
- DevTools bị đưa vào `provided` để tưởng rằng nó chắc chắn không vào executable JAR.
- Một module thư viện đánh dấu phụ thuộc API là provided mà mọi consumer thực tế không có dependency đó, dẫn đến lỗi runtime ở module tiêu thụ.

**Quy tắc:** provided không phải nút "exclude". Nó là một **hợp đồng với môi trường chạy**; Spring Boot repackage có chủ ý tương tác với hợp đồng đó theo loại archive.

## 3. Gradle `compileOnly`: chỉ xuất hiện khi biên dịch

### 3.1 Cấu hình của Gradle Java plugin

Khi dùng Gradle `java` hoặc `java-library`:

- `implementation`: các dependency cần cho **compile main + runtime**.
- `runtimeOnly`: dependency chỉ cần ở runtime, không cần khi compile.
- **`compileOnly`**: chỉ cần trên **main compile classpath**, **không có trên runtime classpath**, **không tự có trên test classpath**, **không được đóng trong JAR/WAR theo cơ chế chuẩn**.
- `annotationProcessor`: công cụ xử lý annotation khi `compileJava` chạy; khác với `compileOnly`.
- `testCompileOnly`, `testImplementation`, `testRuntimeOnly` và `testAnnotationProcessor`: các cấu hình dành riêng cho test.

Ví dụ Groovy DSL:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    // Chỉ là ví dụ tọa độ; cần cung cấp phiên bản hoặc BOM phù hợp.
    compileOnly 'org.projectlombok:lombok:1.18.36'
    annotationProcessor 'org.projectlombok:lombok:1.18.36'

    testCompileOnly 'org.projectlombok:lombok:1.18.36'
    testAnnotationProcessor 'org.projectlombok:lombok:1.18.36'
}
```

Đây là **trích đoạn build phục vụ phân loại dependency**, không phải một build Spring Boot đầy đủ. `compileOnly` cho phép compiler tìm annotation và API của Lombok trong source code, còn `annotationProcessor` cho Lombok chạy để tạo getter/constructor tại compile time. Chỉ khai báo `compileOnly` mà không cấp processor có thể khiến mã cần Lombok-generated methods **không biên dịch**.

Sau khi annotation processing tạo bytecode, đa phần lớp do Lombok hỗ trợ đã được biên dịch vào chính class của ứng dụng. Vì vậy việc loại `lombok-...jar` khỏi runtime thường là **đúng ý đồ**. Nhưng đừng suy rộng rằng **mọi** annotation library đều chỉ cần compile: một annotation/framework có thể được đọc bằng reflection ở runtime và lúc đó còn cần dependency runtime.

### 3.2 Vì sao `compileOnly` không thay được `providedRuntime`?

Giả sử app Spring MVC cần lớp Tomcat để chạy **web integration tests**. Nếu bạn đặt Tomcat ở `compileOnly`:

- Mã nguồn có thể biên dịch vì compiler nhìn thấy class.
- Nhưng **`testRuntimeClasspath` không tự mang nó theo**, vì `compileOnly` của main không thuộc runtime của main hay test.
- Spring test có thể không khởi tạo được embedded web server; lỗi không xuất hiện ở `compileJava` mà ở `test`.
- Một Boot executable WAR muốn chạy bằng `java -jar` cũng không được cung cấp Tomcat nếu chỉ dựa vào compileOnly, vì dependency này không được đóng gói bởi runtime/War rules chuẩn.

Với container ngoài, dùng cấu hình phù hợp có mặt trong **test/runtime khi phát triển** nhưng **được WAR packaging tách biệt** là cách chính xác hơn: `providedRuntime` của Gradle War plugin.

### 3.3 Test compile không tự kế thừa main compileOnly

Một lỗi thường gặp: `src/main/java` dùng Lombok biên dịch được, nhưng `src/test/java` dùng annotation Lombok lại lỗi. Bạn đã đặt Lombok vào `compileOnly`/`annotationProcessor` của main, chưa khai báo `testCompileOnly` và `testAnnotationProcessor` cho test.

Cũng có khi test compile được nhưng chạy test thiếu thư viện do một class của app tham chiếu runtime vào dependency vốn chỉ là compileOnly. Cách sửa không phải tự động thêm toàn bộ compileOnly vào testRuntime; cần phân tích **nó thật sự chỉ là compile-time API hay còn được sử dụng runtime**.

### 3.4 Các report cần xem

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testCompileClasspath
./gradlew dependencies --configuration testRuntimeClasspath
```

Trên Windows PowerShell dùng `.\gradlew.bat` thay `./gradlew`.

**Quan sát kỳ vọng** nếu dependency chỉ được khai báo `compileOnly` và không bị dependency khác kéo vào runtime:

- Có trong `compileClasspath`.
- Không có trong `runtimeClasspath`.
- Không mặc nhiên có trong `testCompileClasspath`/`testRuntimeClasspath`.
- Không có trong `BOOT-INF/lib` của `bootJar`.

Nếu bạn vẫn thấy module đó trong runtime, kiểm tra xem một starter/`implementation`/`runtimeOnly` khác có kéo lại nó không. "**Chỉ có trong compileOnly**" mới cho phép dự đoán vắng mặt từ cấu hình; artifact cuối phải được kiểm chứng.

## 4. Gradle `developmentOnly`: dùng lúc phát triển, loại khỏi Boot archive

### 4.1 Configuration do Spring Boot Gradle plugin bổ sung

Khi Spring Boot Gradle plugin được áp dụng cùng Java plugin, configuration `developmentOnly` được dùng cho những dependency cần khi **chạy phát triển** mà không nên nằm trong executable archive phát hành. Các ví dụ tiêu biểu là:

- `org.springframework.boot:spring-boot-devtools`: restart, LiveReload và các tiện ích phát triển.
- `org.springframework.boot:spring-boot-docker-compose`: tích hợp dịch vụ Docker Compose khi chạy local trong phiên bản Spring Boot phù hợp.

Ví dụ:

```groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
    developmentOnly 'org.springframework.boot:spring-boot-docker-compose'
}
```

Trong ví dụ, version của các module này được quản lý bằng `spring-boot-dependencies` BOM do cấu hình Spring Boot dependency management sử dụng. Nếu dự án không áp dụng cơ chế BOM tương ứng, hãy khai báo version hoặc dùng Gradle native platform thích hợp.

Khác với `compileOnly`, `developmentOnly` có thể góp mặt trong **runtimeClasspath của chế độ phát triển**, để `bootRun`/IDE chạy ứng dụng cùng công cụ hỗ trợ. Spring Boot Gradle plugin cũng cung cấp cấu hình `productionRuntimeClasspath` nhằm phân biệt các dependency runtime sản phẩm với những dependency chỉ dùng development.

Đây **không phải** cờ Spring profile `dev`/`prod`. Chỉ đặt `spring.profiles.active=prod` **không loại JAR DevTools khỏi artifact**; `developmentOnly` tác động ở **build classpath và packaging**, còn profile tác động ở **Spring runtime configuration**.

### 4.2 Không coi `runtimeClasspath` là bản mô tả hoàn hảo của Boot JAR

Với `developmentOnly`, `runtimeClasspath` phục vụ phát triển có thể **hiển thị DevTools**. Tuy nhiên theo tài liệu Spring Boot Gradle plugin, dependency thuộc `developmentOnly` **mặc định bị loại khỏi executable JAR/WAR**.

```text
Gradle:
    implementation starter-web
    developmentOnly devtools
             |
             +--> bootRun / dev runtimeClasspath ----> có thể thấy DevTools
             |
             \--> bootJar / bootWar output ----------> DevTools bị loại mặc định
```

Vì thế hai phát biểu sau không mâu thuẫn:

> "`./gradlew dependencies --configuration runtimeClasspath` có DevTools."

> "`jar tf build/libs/demo.jar` không có `spring-boot-devtools-...jar`."

Hai lệnh trả lời **hai câu hỏi khác nhau**. Ngược lại, nếu bạn gán DevTools vào `implementation` hoặc `runtimeOnly`, hoặc custom `bootJar.classpath` để thêm `developmentOnly`, bảo đảm loại trừ dựa trên cấu hình mặc định có thể không còn.

### 4.3 Các lệnh kiểm chứng Gradle

```bash
# Chỉ đọc nơi có Java plugin và Boot plugin phù hợp.
./gradlew dependencies --configuration runtimeClasspath

# Classpath production mà Spring Boot Gradle plugin cung cấp.
./gradlew dependencies --configuration productionRuntimeClasspath

# Ai kéo DevTools, có phải từ developmentOnly không?
./gradlew dependencyInsight --dependency spring-boot-devtools \
  --configuration runtimeClasspath

# Đóng gói Boot JAR và kiểm tra file cuối:
./gradlew clean bootJar
jar tf build/libs/demo-0.0.1-SNAPSHOT.jar
```

**Không mặc định mọi Gradle project đều có `developmentOnly`/`productionRuntimeClasspath`:** đó là configuration từ Spring Boot Gradle plugin trong bối cảnh Java tương ứng. Nếu lệnh báo không tồn tại, xác định đúng module, plugin có `apply false` hay không, Gradle Wrapper/Boot version và cấu hình Java trước.

**Lưu ý về tập giao nhau:** nếu một module vừa có đường vào qua `developmentOnly`, vừa được một dependency runtime hợp lệ khác kéo vào, kết quả resolution và packaging cần được xác nhận thực tế. Đừng suy luận từ một dòng khai báo rằng mọi byte của cùng `group:artifact` chắc chắn vắng mặt.

### 4.4 `testAndDevelopmentOnly` (nếu phiên bản plugin hỗ trợ)

Ở Spring Boot 3.3, plugin Gradle còn có configuration `testAndDevelopmentOnly` dùng cho dependency cần **khi phát triển và test** nhưng không cần cho production archive. Phân loại này có thể có ích cho một số công cụ hỗ trợ local/test. Đây là configuration **bổ sung**, không thay thế `developmentOnly` hay `testImplementation` trong mọi trường hợp; áp dụng khi hiểu rõ nhu cầu chạy test và khả năng plugin version thực tế.

Khi điều tra vì sao một dependency có trong test runtime hoặc dev runtime nhưng vắng trong packaged archive, hãy kiểm tra cả những configuration development/test đặc thù mà project đã khai báo.

## 5. Gradle War plugin: `providedCompile` và `providedRuntime` không phải `compileOnly`

### 5.1 Hai configuration chỉ xuất hiện khi áp dụng `war`

Gradle War plugin tự áp dụng Java plugin và bổ sung các configuration:

- **`providedCompile`**: dependency cần lúc compile và được servlet container ngoài cung cấp khi triển khai. Theo Gradle War plugin, chúng có mặt trên **main/test compile và runtime classpath**, nhưng bị loại khỏi **WAR thông thường**.
- **`providedRuntime`**: dependency cần để chạy nhưng do servlet container ngoài cung cấp. Chúng có mặt trên **main/test runtime classpath**, nhưng bị loại khỏi **WAR thông thường**.

| Cấu hình khi dùng Gradle War plugin | Main compile | Main/test runtime | Plain `war`, `WEB-INF/lib` | Mục đích |
| --- | --- | --- | --- | --- |
| `implementation` | Có | Có | Thường có | Thư viện ứng dụng tự mang |
| `compileOnly` | Có | **Không** nhờ bản thân cấu hình | Không | API/annotation chỉ compile |
| `providedCompile` | Có | **Có** | **Loại** | API container ngoài, cũng dùng khi test |
| `providedRuntime` | Không được chọn chỉ vì compile | **Có** | **Loại** | Runtime do external container cấp |
| `testImplementation` | Test only | Test only | Không | Thư viện test |
| `developmentOnly` (Boot plugin) | Không phải compile requirement | Dev runtime | Loại khỏi Boot archive mặc định | DevTools và local tools |

Các ô mô tả **ảnh hưởng trực tiếp của cấu hình**, không phải quy tắc bất biến của module khi bị kéo vào từ đường khác hoặc do task classpath custom.

### 5.2 Vì sao `providedRuntime` phù hợp với Spring Boot WAR?

Dùng Spring Boot 3.3 với MVC Servlet và Tomcat:

```groovy
plugins {
    id 'war'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
}
```

Đây là **trích đoạn Groovy DSL**: muốn build đầy đủ cần `group`, `version`, `repositories`, Java toolchain và mã ứng dụng. `war` tự áp dụng `java`. Khi dùng `providedRuntime`:

1. **Compile/test:** các API cần compile đã có qua các dependency ứng dụng thích hợp; Tomcat runtime còn có trên test classpath nên Spring web integration tests có môi trường server cần thiết.
2. **Plain WAR:** Tomcat được xem là dependency external container cung cấp nên **không nằm trong `WEB-INF/lib`** của WAR thường theo quy tắc Gradle War plugin.
3. **Boot executable WAR:** Spring Boot plugin **đưa provided runtime vào `WEB-INF/lib-provided`**, giúp file WAR chạy qua `java -jar` nhưng vẫn triển khai được vào external Tomcat không bị trộn embedded Tomcat vào `WEB-INF/lib`.
4. **Nếu dùng `compileOnly` thay thế:** Tomcat không tự xuất hiện trên test runtime và không được đưa vào `WEB-INF/lib-provided` nhờ providedRuntime; web integration test hoặc `java -jar` có thể thất bại.

Tài liệu Spring Boot **ưu tiên `providedRuntime` hơn `compileOnly`** cho embedded Servlet container trong WAR. Đây không phải quy tắc chung "mọi compileOnly đều sai", mà là lời khuyên cho dependency do external container cấp nhưng **vẫn cần để chạy test và executable WAR**.

### 5.3 Cấu hình này có tính bắc cầu

Gradle War plugin `providedCompile`/`providedRuntime` ảnh hưởng **dependency bắc cầu**. Khi một thư viện được đánh dấu provided, các dependency nó kéo theo cũng có thể bị loại khỏi `WEB-INF/lib` của plain WAR, **kể cả khi có một dependency trùng tọa độ được khai báo qua nhánh `implementation`**.

Ví dụ đồ thị giả định:

```text
implementation --> app-component --------> shared-util:1.0
providedRuntime --> container-helper ----> shared-util:1.0
```

Không thể kết luận `shared-util` chắc chắn xuất hiện ở `WEB-INF/lib` chỉ vì có nhánh `implementation`. Gradle War plugin cảnh báo sự lan truyền của provided configuration; xem resolved graph và file WAR thực tế. Khi cần tinh chỉnh, có thể tránh transitivity không mong muốn bằng một dependency dạng artifact-only `group:module:version@jar` trong các tình huống phù hợp, nhưng phải đánh giá kỹ vì việc bỏ dependency bắc cầu có thể khiến môi trường chạy bị thiếu lớp.

### 5.4 `providedCompile` vs `providedRuntime` có thay thế nhau được không?

Không hoàn toàn:

- Nếu mã Java **import trực tiếp** một API chỉ container cấp, `providedCompile` là lựa chọn phù hợp hơn trong mô hình Gradle WAR.
- Nếu mã Java không cần API đó để compile nhưng cần server/runtime trong test hoặc executable WAR, `providedRuntime` là lựa chọn thường gặp.
- Có thể dùng cả hai khi có những artifact thực sự có vai trò khác nhau.
- Không nên đặt nguyên `spring-boot-starter-web` vào provided chỉ vì Tomcat là provided; starter-web còn kéo các thành phần Spring MVC/JSON mà **external Tomcat không tự cung cấp**.
- Xem thư viện đã phân giải **theo từng artifact**, tránh biến cả nhóm Spring thành "container sẽ có".

## 6. Ba trường hợp điển hình: Lombok, DevTools, Tomcat

| Cần làm gì? | Maven phù hợp | Gradle phù hợp | Điểm xác minh |
| --- | --- | --- | --- |
| Tạo getter/constructor bằng Lombok khi biên dịch | Maven Compiler Plugin annotation processor, dependency Lombok có phân loại phù hợp; cấu hình plugin nếu cần loại runtime | `compileOnly` + `annotationProcessor`, và test variant khi dùng Lombok trong test | Class biên dịch có method; `lombok-...jar` không nằm trong Boot runtime archive |
| Có DevTools khi phát triển, không phát hành | `spring-boot-devtools` thường khai báo optional; Boot Maven `excludeDevtools=true` (mặc định) | `developmentOnly` | Có khi chạy dev; không có `spring-boot-devtools-...jar` trong Boot JAR/WAR |
| Deploy Boot MVC WAR vào Tomcat ngoài | `spring-boot-starter-tomcat` với `<scope>provided</scope>` | `providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'` | Boot WAR có `WEB-INF/lib-provided`; plain WAR không đưa container JAR vào `WEB-INF/lib` |
| Chạy ứng dụng Boot MVC JAR độc lập | Tomcat có thể là compile/runtime hoặc even provided vì Boot `repackage` bao gồm provided, nhưng không lạm dụng | Tomcat cần runtime của Boot JAR, không đẩy vào `compileOnly` | `BOOT-INF/lib/tomcat-embed-...jar` có mặt nếu embedded Tomcat được dùng |
| Dùng JUnit/Mockito để test | `<scope>test</scope>` | `testImplementation`/`testRuntimeOnly` | `test` hoạt động; không có JUnit trong packaged Boot runtime |

**Bẫy về Lombok:** `compileOnly` là Gradle configuration, không phải một **Maven scope** chuẩn. Không viết `<scope>compileOnly</scope>` trong `pom.xml`. Maven dùng dependency scopes, compiler plugin và annotation processor configuration tương ứng.

**Bẫy về DevTools:** Spring Boot DevTools cũng có cơ chế tự tắt khi chạy ứng dụng đóng gói. Nhưng "**tự tắt khi chạy**" **không đồng nghĩa** "**không tồn tại trong archive**"; chỉ `jar tf` mới xác định được artifact cuối có chứa JAR đó hay không.

## 7. Ví dụ Maven đầy đủ: `provided` Tomcat và DevTools không phát hành

Tạo project Spring Boot MVC sử dụng Maven Wrapper và Java 17. Tệp `pom.xml` minh họa:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <packaging>war</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-tomcat</artifactId>
            <scope>provided</scope>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-devtools</artifactId>
            <optional>true</optional>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <excludeDevtools>true</excludeDevtools>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Giải thích:

- `<packaging>war</packaging>` kích hoạt Maven WAR packaging trước Boot repackage.
- `spring-boot-starter-tomcat` với scope `provided` thông báo rằng **external servlet container** sẽ cung cấp phần này khi deploy WAR.
- `spring-boot-starter-web` vẫn thuộc dependency ứng dụng: external container không cung cấp tự động Spring MVC/Jackson.
- `spring-boot-devtools` optional hỗ trợ quá trình phát triển, còn `excludeDevtools` là thiết lập Boot packaging để không phát hành nó.
- `spring-boot-starter-test` thuộc test scope; không cần trong runtime archive.
- `spring-boot-starter-parent` đã cấu hình execution `repackage` cho Spring Boot Maven plugin; với project **chỉ nhập BOM mà không kế thừa parent**, phải tự nối execution để có executable archive.
- JAR/WAR và dependency versions thực có thể khác khi dùng profile, parent khác, exclusions hoặc overrides. Kiểm chứng bằng lệnh.

### 7.1 Một lớp Java 17+ chạy được ở chế độ embedded và external WAR

Tạo file `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class DemoApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(SpringApplicationBuilder app) {
        return app.sources(DemoApplication.class);
    }

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Đây là lớp Java **hoàn chỉnh trong một project Spring Boot có dependency**, không chạy bằng `javac DemoApplication.java` đơn lẻ khi chưa có classpath Spring. `SpringBootServletInitializer` phục vụ deploy lên external Servlet container; `main` phục vụ `java -jar`/`spring-boot:run`. Với cổng mặc định 8080 và không đổi context path, gọi `GET /ping` qua embedded server trả response body:

```text
pong
```

Đó là **nội dung HTTP response** của phương thức Java `ping()`, không phải toàn bộ stdout/log Spring Boot. Nếu deploy WAR lên external Tomcat, URL có thể là `/demo/ping` hoặc một context path khác do container quyết định.

### 7.2 Test Spring MVC khởi động context

Tệp `src/test/java/com/example/demo/DemoApplicationTests.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class DemoApplicationTests {

    @Test
    void contextLoads() {
    }
}
```

Test này kiểm tra **Spring context khởi động được**. Nó không xác minh HTTP endpoint, không chứng minh deploy external Tomcat thành công và không tự xác nhận archive đã loại DevTools. Nếu cần HTTP integration test, dùng `@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)` và test client tương ứng, với đủ runtime Servlet trên test classpath.

### 7.3 Build và dự đoán có điều kiện

```bash
./mvnw test
./mvnw dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-tomcat
./mvnw help:effective-pom -Doutput=effective-pom.xml
./mvnw clean package
jar tf target/demo-0.0.1-SNAPSHOT.war
```

Với POM, ứng dụng và môi trường tương thích, trong **Spring Boot executable WAR** mong đợi thấy các file tương tự:

```text
WEB-INF/classes/com/example/demo/DemoApplication.class
WEB-INF/lib/spring-webmvc-...jar
WEB-INF/lib-provided/tomcat-embed-core-...jar
```

Các dấu `...` là phiên bản thực do BOM/graph chọn, không phải file tên nguyên văn. **Không** kỳ vọng `spring-boot-devtools` hay thư viện JUnit đi vào các thư mục runtime của WAR. Vẫn cần kiểm tra đúng file đã build: không coi bảng kỳ vọng là log đã chạy.

Chạy executable WAR:

```bash
java -jar target/demo-0.0.1-SNAPSHOT.war
```

Ở terminal khác sau khi server khởi động:

```bash
curl http://localhost:8080/ping
```

Nếu external Tomcat được dùng, chỉ WAR tương thích với Servlet API/Jakarta và cách khởi tạo mới được deploy thành công. `provided` và `lib-provided` giải quyết phần phân loại dependency, **không tự bảo đảm tương thích server**.

### 7.4 Nếu đổi Maven `war` thành `jar`

Thay `<packaging>war</packaging>` thành `<packaging>jar</packaging>` trên bản sao/nhánh thử nghiệm rồi chạy lại `./mvnw clean package`. Với Boot Maven `repackage`, dependency provided như Tomcat **vẫn có thể xuất hiện** trong `BOOT-INF/lib` của executable JAR. Điều này tạo sự khác nhau trực quan:

| Phụ thuộc Tomcat scope provided | Maven Boot WAR | Maven Boot JAR |
| --- | --- | --- |
| Đặt ở đâu? | `WEB-INF/lib-provided` | `BOOT-INF/lib` |
| Có thể chạy `java -jar`? | Có với executable WAR phù hợp | Có với executable JAR phù hợp |
| Để deploy external servlet container? | WAR có mục đích đó | Không phải cách deploy Servlet WAR truyền thống |
| Có chứng minh `provided` không được đóng gói? | **Không** | **Không** |

Điều này không khuyến nghị dùng `provided` cho tất cả app JAR; nó chỉ cho thấy **hành vi Spring Boot repackage** cần kiểm chứng khác Maven scope core.

## 8. Ví dụ Gradle JAR: `compileOnly` Lombok và `developmentOnly` DevTools

### 8.1 `build.gradle` Groovy DSL đầy đủ

`settings.gradle`:

```groovy
rootProject.name = 'demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    compileOnly 'org.projectlombok:lombok'
    annotationProcessor 'org.projectlombok:lombok'
    testCompileOnly 'org.projectlombok:lombok'
    testAnnotationProcessor 'org.projectlombok:lombok'

    developmentOnly 'org.springframework.boot:spring-boot-devtools'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Trong ví dụ, dependency-management plugin nhập BOM của Boot phù hợp và cung cấp versions cho các artifact được BOM quản lý. Nếu dự án dùng native Gradle platform, cần khai báo BOM/constraints đúng thay vì chỉ xóa dependency-management plugin mà không làm gì khác.

Có thể dùng **cùng `DemoApplication.java`** trong phần 7, mặc dù class đó không cần Lombok; phần Lombok ở đây minh họa cách phân loại công cụ compile. Nếu muốn chứng minh annotation processing có hoạt động, thêm lớp nhỏ phía dưới.

### 8.2 Lớp dùng Lombok để kiểm tra compile-time

Tạo `src/main/java/com/example/demo/Greeting.java`:

```java
package com.example.demo;

import lombok.Getter;

@Getter
public final class Greeting {
    private final String value;

    public Greeting(String value) {
        this.value = value;
    }
}
```

Annotation `@Getter` khiến Lombok sinh method `getValue()` trong class biên dịch. Tạo `src/main/java/com/example/demo/GreetingProbe.java`:

```java
package com.example.demo;

public final class GreetingProbe {

    public static void main(String[] args) {
        Greeting greeting = new Greeting("hello");
        System.out.println(greeting.getValue());
    }
}
```

Với Gradle `compileOnly + annotationProcessor`, sau `./gradlew classes` có thể gọi chương trình đơn giản này mà **không cần Lombok jar lúc chạy**:

```bash
./gradlew classes
java -cp build/classes/java/main com.example.demo.GreetingProbe
```

Dòng stdout **của chính `GreetingProbe`**, khi hai class đã được biên dịch đúng:

```text
hello
```

Lệnh trên dành cho macOS/Linux hoặc môi trường có path phù hợp; Windows có thể dùng `java -cp build\classes\java\main com.example.demo.GreetingProbe`. `GreetingProbe` là chương trình Java 17+ không dùng Spring Boot runtime; nó chỉ dùng bytecode đã biên dịch. **Không chạy `javac Greeting.java` trực tiếp** nếu chưa cung cấp Lombok annotation processor. Không cần đặt `lombok-...jar` vào `BOOT-INF/lib` để method `getValue()` tồn tại.

### 8.3 Kiểm tra các classpath tương ứng

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencies --configuration productionRuntimeClasspath
./gradlew dependencyInsight --dependency lombok --configuration compileClasspath
./gradlew dependencyInsight --dependency spring-boot-devtools --configuration runtimeClasspath
./gradlew clean bootJar
jar tf build/libs/demo-0.0.1-SNAPSHOT.jar
```

Kết quả dự đoán **nếu không có cấu hình khác kéo module vào**:

- Lombok: xuất hiện ở compileClasspath, **không** nằm trong runtimeClasspath/`BOOT-INF/lib` chỉ vì `compileOnly`.
- DevTools: có thể xuất hiện ở runtimeClasspath phục vụ phát triển, **không** ở productionRuntimeClasspath/`BOOT-INF/lib` do `developmentOnly`.
- Tomcat embedded: vẫn được đóng vào `BOOT-INF/lib` do `spring-boot-starter-web` khi app cần web server chạy độc lập.
- JUnit: có trong test graph, không ở packaged runtime archive.

Không nhìn thấy Lombok trong `runtimeClasspath` cũng không chứng minh annotation processing đã tạo method; phần đó được kiểm chứng bằng `./gradlew classes` và chạy `GreetingProbe`.

### 8.4 Kotlin DSL cho cùng ý nghĩa

Trích đoạn `build.gradle.kts`, áp dụng trên project đã có plugin và BOM phù hợp:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    compileOnly("org.projectlombok:lombok")
    annotationProcessor("org.projectlombok:lombok")
    testCompileOnly("org.projectlombok:lombok")
    testAnnotationProcessor("org.projectlombok:lombok")
    developmentOnly("org.springframework.boot:spring-boot-devtools")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}
```

Đây là **trích đoạn**: để biên dịch/chạy từ đầu còn phải khai báo `group`, `version`, `java.toolchain`, `repositories` và `tasks.test.useJUnitPlatform()` như Groovy DSL. Không trộn cú pháp `compileOnly '...'` của Groovy vào `.gradle.kts`.

## 9. Ví dụ Gradle WAR: `providedRuntime` và executable WAR

Trên bản sao project Gradle JAR ở phần 8, đổi plugin `java` thành `war`; `war` đã áp dụng Java. Giữ Spring Boot/dependency management, thay phần Tomcat như sau:

```groovy
plugins {
    id 'war'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    // Container ngoài sẽ cung cấp Tomcat.
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'

    // Dependency chỉ dành cho lúc phát triển.
    developmentOnly 'org.springframework.boot:spring-boot-devtools'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

Đoạn trên chỉ gồm những phần cần thay, không phải `build.gradle` hoàn chỉnh. Giữ `repositories`, Java toolchain, group/version và cấu hình test từ ví dụ phần 8 nếu làm trên bản sao. Lớp `DemoApplication` trong phần 7 đã kế thừa `SpringBootServletInitializer` nên phù hợp để thử external Servlet container.

Tương đương Kotlin DSL (trích đoạn):

```kotlin
plugins {
    war
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    providedRuntime("org.springframework.boot:spring-boot-starter-tomcat")
    developmentOnly("org.springframework.boot:spring-boot-devtools")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}
```

### 9.1 Task `war` và `bootWar` không cùng nội dung

```bash
./gradlew clean war bootWar
jar tf build/libs/demo-0.0.1-SNAPSHOT-plain.war
jar tf build/libs/demo-0.0.1-SNAPSHOT.war
```

Khi dùng Spring Boot Gradle plugin hiện đại, `war` thường mang classifier `plain` để tránh trùng đầu ra với `bootWar`. Tên file có thể khác nếu dự án cấu hình `archiveClassifier`/`archiveBaseName`.

| Vị trí archive | Plain WAR từ `war` | Executable WAR từ `bootWar` |
| --- | --- | --- |
| `WEB-INF/classes` | Có | Có |
| `WEB-INF/lib` (dependency ứng dụng) | Có | Có |
| `WEB-INF/lib-provided` (provided servlet runtime) | Không phải cách plain WAR thường đóng gói | Có với `providedRuntime` |
| Spring Boot launcher | Không theo mặc định | Có |
| Chạy `java -jar` | Không phải mục tiêu mặc định | Có khi Boot WAR hợp lệ |
| Deploy external Servlet container | Có thể, nếu đúng ứng dụng Servlet | Có thể, với layout và initializer phù hợp |

**Không kết luận từ mỗi tên file.** Hãy mở archive thật và xác nhận Tomcat không nằm sai ở `WEB-INF/lib`, đồng thời có `WEB-INF/lib-provided` ở Boot WAR.

### 9.2 Vì sao test vẫn có Tomcat?

Gradle War plugin giữ `providedRuntime` trong **main/test runtime classpaths**, dù không đưa dependency vào plain WAR. Do đó integration test có embedded servlet runtime để khởi tạo ứng dụng. Đây chính là khác biệt quan trọng với `compileOnly` — một dependency chỉ compile sẽ không tự xuất hiện ở test runtime.

### 9.3 WAR cho container ngoài không chỉ là một classifier

Nếu muốn deploy vào Tomcat ngoài, ngoài dependency cần:

- Spring Boot app dùng **Spring MVC/Servlet**, không phải cố đóng gói ứng dụng reactive Netty thuần làm WAR Servlet truyền thống.
- Lớp chính kế thừa `SpringBootServletInitializer` khi ứng dụng cần container kích hoạt.
- Servlet/Jakarta API của container ngoài **tương thích** với phiên bản Spring Boot.
- Context path, version JDK, security và cấu hình triển khai đúng.
- Kiểm tra bằng **deploy thật** lên container ngoài, không chỉ bằng `java -jar`.

Việc `bootWar` thành công chỉ chứng minh build/package, không chứng minh external deploy thành công.

## 10. Cách đo đạc có chứng cứ: graph + classpath + nội dung archive

### 10.1 Quy trình thống nhất

Để trả lời "dependency X bị đưa vào hay loại khỏi sản phẩm?", làm theo đúng thứ tự:

**Bước 1 – Xác định mục tiêu.** Ghi build system, module, Spring Boot plugin version, loại archive, dependency tọa độ và mong đợi lúc chạy.

**Bước 2 – Kiểm tra khai báo.** Tìm Maven `<scope>provided</scope>`/`<optional>`/plugin `<excludes>`; Gradle `compileOnly`/`developmentOnly`/`providedRuntime` và task classpath.

**Bước 3 – Xác nhận dependency graph đã phân giải.** Đừng dùng một dòng declaration làm kết quả cuối; dependency có thể được kéo theo đường khác hoặc bị constraint/BOM đổi phiên bản.

**Bước 4 – Xác nhận classpath có mục đích.** Maven scope vs Gradle compile/test/runtime/productionRuntimeClasspath; chọn đúng module.

**Bước 5 – Build đúng artifact.** Maven `package` cùng Boot repackage hoặc Gradle `bootJar`/`bootWar`. Không đọc nhầm file plain, Maven `.jar.original` hoặc artifact cũ.

**Bước 6 – Dùng `jar tf` trên artifact và kiểm tra mục tiêu.** Với WAR, tìm cả `WEB-INF/lib` và `WEB-INF/lib-provided`; với JAR tìm `BOOT-INF/lib`.

**Bước 7 – Smoke test.** Chạy `java -jar` hoặc deploy WAR vào đúng container ngoài; điều tra lỗi runtime nếu lớp được khai báo provided nhưng môi trường không cấp.

### 10.2 Maven: xem graph và effective POM

```bash
./mvnw dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-tomcat
./mvnw dependency:tree -Dincludes=org.springframework.boot:spring-boot-devtools

# Mô hình POM sau parent, profiles và plugin configuration:
./mvnw help:effective-pom -Doutput=effective-pom.xml

# Tạo artifact cuối cùng, nếu được phép clean trong workspace thực hành:
./mvnw clean package
```

`dependency:tree` là bằng chứng về resolved graph của project; `effective-pom.xml` giúp xác định scope và cấu hình plugin. **Không** lấy sự vắng mặt của Tomcat trong Maven runtime classpath thông thường làm bằng chứng nó vắng khỏi Spring Boot repackaged JAR/WAR.

### 10.3 Gradle: dùng đúng configuration

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testCompileClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencies --configuration productionRuntimeClasspath

./gradlew dependencyInsight \
  --dependency spring-boot-devtools \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency lombok \
  --configuration compileClasspath

./gradlew dependencyInsight \
  --dependency spring-boot-starter-tomcat \
  --configuration runtimeClasspath
```

`productionRuntimeClasspath` là tên configuration từ Spring Boot Gradle plugin thích hợp; không phải Gradle core. Chỉ gọi khi project/module đã áp dụng plugin theo cách tạo configuration đó. Với project nhiều module, dùng `./gradlew :app:dependencies --configuration runtimeClasspath` nếu `:app` là module app thực tế. `dependencyInsight` giải thích version và các đường kéo vào, **không tự cho biết file nào đã được đóng trong archive**.

**Không cố phân giải `compileOnly` như một configuration resolvable trên các Gradle hiện đại:** đó là bucket khai báo. Để kiểm tra các dependency biên dịch, dùng `compileClasspath`.

### 10.4 Đọc executable JAR/WAR trên macOS/Linux

Sau khi build, chạy lệnh phù hợp với artifact thật:

```bash
# Maven executable JAR:
jar tf target/demo-0.0.1-SNAPSHOT.jar

# Maven executable WAR:
jar tf target/demo-0.0.1-SNAPSHOT.war

# Gradle executable JAR:
jar tf build/libs/demo-0.0.1-SNAPSHOT.jar

# Gradle executable WAR:
jar tf build/libs/demo-0.0.1-SNAPSHOT.war
```

Không dùng cả bốn trên cùng một project nếu project không tạo đủ các artifact đó. Với Boot JAR, hãy tìm `BOOT-INF/lib/`; với Boot WAR, tìm `WEB-INF/lib/` và `WEB-INF/lib-provided/`. Các file cấu trúc `META-INF/MANIFEST.MF` và Boot loader giúp phân biệt executable archive với plain archive.

Muốn tìm một artifact cụ thể:

```bash
jar tf build/libs/demo-0.0.1-SNAPSHOT.jar | grep -E '^BOOT-INF/lib/.*(lombok|spring-boot-devtools|tomcat-embed).*\.jar$'

jar tf build/libs/demo-0.0.1-SNAPSHOT.war | grep -E '^WEB-INF/(lib|lib-provided)/.*(spring-boot-devtools|tomcat-embed).*\.jar$'
```

Đây là **truy vấn gợi ý cho artifact ví dụ**, không phải một lệnh sẽ luôn in kết quả. Nếu `grep` không tìm thấy, cần kiểm tra đúng artifact, đúng phiên bản, đúng đường dẫn và khả năng dependency bị đổi tên/shade. Với WAR, một module có thể xuất hiện ở `lib-provided` chứ không ở `lib`.

### 10.5 Windows PowerShell

```powershell
.\gradlew.bat clean bootJar
$archive = "build\libs\demo-0.0.1-SNAPSHOT.jar"
$entries = & jar tf $archive

if ($LASTEXITCODE -ne 0) {
    throw "Cannot inspect archive: $archive"
}

$entries | Select-String -Pattern "BOOT-INF/lib/(lombok|spring-boot-devtools|tomcat-embed)"
```

Với Maven Wrapper dùng `.\mvnw.cmd`, đường JAR nằm ở `target\...`; WAR có `WEB-INF`. Đây là lệnh **xem những dòng khớp**, không phải lời khẳng định dependency bắt buộc xuất hiện. Nếu mục tiêu là kiểm tra loại trừ, việc không có dòng khớp mới là mong đợi cho Lombok/DevTools; Tomcat embedded trong Boot JAR lại có thể phải **có**.

## 11. Bài kiểm tra tự động: điều gì phải vắng và điều gì phải có?

Một CI gate có ích phải biểu đạt **chính sách cho một artifact cụ thể**. Ví dụ với Spring Boot JAR của phần 8: DevTools và Lombok không được nằm ở `BOOT-INF/lib`, nhưng embedded Tomcat có thể được yêu cầu bởi ứng dụng web.

### 11.1 Bash check cho executable JAR

```bash
#!/usr/bin/env bash
set -euo pipefail

artifact="build/libs/demo-0.0.1-SNAPSHOT.jar"

if [[ ! -f "$artifact" ]]; then
    echo "FAIL: release artifact missing"
    exit 1
fi

entries="$(jar tf "$artifact")"

if ! grep -Fq 'BOOT-INF/classes/' <<< "$entries"; then
    echo "FAIL: not an expected Boot JAR layout"
    exit 1
fi

# Đây là hai module mà ví dụ JAR chủ ý không đóng gói.
deny='^BOOT-INF/lib/(lombok|spring-boot-devtools)-[^/]+[.]jar$'
if grep -E "$deny" <<< "$entries"; then
    echo "FAIL: compile-only or development-only artifact packaged"
    exit 1
fi

# Ứng dụng ví dụ sử dụng embedded Tomcat để chạy web server.
if ! grep -Eq '^BOOT-INF/lib/tomcat-embed-core-[^/]+[.]jar$' <<< "$entries"; then
    echo "FAIL: expected embedded Tomcat missing"
    exit 1
fi

echo "PASS: Boot JAR dependency policy satisfied"
```

Khi artifact **đúng layout**, **không chứa hai module bị cấm** và **có Tomcat embedded** theo yêu cầu, dòng stdout do **script** in là:

```text
PASS: Boot JAR dependency policy satisfied
```

Đây là **kết quả kỳ vọng có điều kiện**, không phải log từ một lượt chạy thực tế. Nếu module bị cấm, script in file vi phạm rồi exit 1. Nếu không có Tomcat hoặc chọn nhầm plain JAR, gate cũng fail. Hãy thay denylist/allowlist theo mục đích thực tế thay vì dùng mặc định cho ứng dụng không chạy Servlet.

### 11.2 Bash check cho executable WAR

Với Gradle WAR ở phần 9:

```bash
#!/usr/bin/env bash
set -euo pipefail

artifact="build/libs/demo-0.0.1-SNAPSHOT.war"
entries="$(jar tf "$artifact")"

if ! grep -Fq 'WEB-INF/classes/' <<< "$entries"; then
    echo "FAIL: unexpected WAR layout"
    exit 1
fi

if ! grep -Eq '^WEB-INF/lib-provided/tomcat-embed-core-[^/]+[.]jar$' <<< "$entries"; then
    echo "FAIL: Tomcat missing from lib-provided"
    exit 1
fi

if grep -Eq '^WEB-INF/lib/tomcat-embed-core-[^/]+[.]jar$' <<< "$entries"; then
    echo "FAIL: embedded Tomcat wrongly placed in WEB-INF/lib"
    exit 1
fi

if grep -Eq '^WEB-INF/(lib|lib-provided)/spring-boot-devtools-[^/]+[.]jar$' <<< "$entries"; then
    echo "FAIL: DevTools packaged"
    exit 1
fi

echo "PASS: Boot WAR dependency policy satisfied"
```

Với WAR mẫu đã đóng gói đúng, script in:

```text
PASS: Boot WAR dependency policy satisfied
```

Nếu `jar tf` thất bại, shell với `set -e` dừng do lệnh lỗi. Đoạn này chỉ phù hợp khi **chính sách mong đợi Tomcat ở lib-provided**. Nếu project dùng Jetty/Undertow hoặc custom Boot layout, thay điều kiện tương ứng. Gate cần chạy trên **đúng file được stage deploy sử dụng**, không phải bất kỳ file trong `build/libs`.

### 11.3 Không lạm dụng "vắng trong ZIP" để bảo đảm hệ thống an toàn

Ngay cả khi `spring-boot-devtools-*.jar` không có trong archive:

- Developer có thể đã copy class debug vào `BOOT-INF/classes`.
- Một agent debug có thể được gắn lúc chạy qua `-javaagent`.
- Dockerfile/image layer có thể mang thêm file ngoài JAR.
- Runtime classpath do script khởi động tùy biến có thể khác classpath Boot launcher.
- Một thư viện có thể bị **shade/relocate** dưới tên mới.

Vì vậy CI gate về dependency là kiểm soát cần thiết nhưng không thay thế security review, secret scanning, smoke test hay kiểm tra image cuối.

## 12. Các lỗi thường gặp khi đổi scope/configuration

| Triệu chứng | Nguyên nhân có thể | Kiểm tra và hướng xử lý |
| --- | --- | --- |
| Java compile thành công nhưng `java -jar` lỗi `ClassNotFoundException` | Dependency runtime bị đặt vào `compileOnly` hoặc bị loại khỏi artifact | Xem `runtimeClasspath`, `BOOT-INF/lib` và import/runtime call stack |
| Maven `provided` vẫn thấy trong Boot JAR | Boot Maven `repackage` **cố ý bao gồm provided** | Đây là behavior có tài liệu, không mặc định là lỗi |
| Maven Boot WAR có Tomcat ở `lib-provided` | Boot dùng layout WAR để hỗ trợ java -jar và external container | Xác minh `WEB-INF/lib-provided` và server startup |
| WAR thường không có Tomcat trong `WEB-INF/lib` | `providedRuntime`/`providedCompile` mang nghĩa external container cấp | Đúng thiết kế khi deploy container tương thích |
| Gradle `compileOnly` class dùng được ở main nhưng test lỗi thiếu class | Main compileOnly không có trong test classpaths | Thêm dependency đúng cho test nếu cần; không nhét bừa vào runtime production |
| Lombok annotation nhận diện nhưng `getValue()` không sinh | Có `compileOnly` nhưng thiếu `annotationProcessor` | Cấu hình cả hai; chạy compileJava để chứng minh |
| DevTools có ở `runtimeClasspath` nhưng không có trong Boot JAR | `developmentOnly` được dùng đúng | Đối chiếu productionRuntimeClasspath và `jar tf`, không phán là build sai |
| DevTools xuất hiện trong `BOOT-INF/lib` | Dùng `implementation`/`runtimeOnly` hoặc custom Boot task classpath | Chuyển về `developmentOnly`/kiểm tra override; build lại |
| `providedRuntime` báo Unknown configuration | Chưa áp dụng Gradle `war` plugin ở project đang xét | Đọc `plugins`, `:module:tasks`, đặt dependency ở đúng module |
| Servlet API có ở compile nhưng external WAR không chạy | Container ngoài sai Jakarta Servlet version hoặc initializer/config | Kiểm tra `SpringBootServletInitializer`, server logs, compatibility |
| Test web integration lỗi sau khi thay `providedRuntime` thành `compileOnly` | Tomcat vắng test runtime | Trả về `providedRuntime` nếu đúng mô hình WAR |
| Gradle `war` chứa ít dependency hơn tưởng dù có nhánh `implementation` | Provided configurations tác động bắc cầu | Kiểm tra `dependencyInsight` và nội dung WAR, cân nhắc transitivity |
| Maven `dependency:tree` thấy dependency nhưng JAR không có | Scope/exclusion, task repackage, artifact hoặc phiên bản khác | So effective POM, plugin config và file JAR cuối |
| Gradle `dependencies --configuration compileOnly` không phân giải được | `compileOnly` là configuration khai báo, không phải compileClasspath resolvable | Dùng `compileClasspath` |
| Build tạo `-plain.jar` và executable JAR | Gradle `jar` và `bootJar` sinh hai loại archive | Chọn đúng output task; đừng chọn bằng wildcard |
| Maven có file `.jar.original` | `repackage` sao lưu JAR trước khi làm Boot executable | Kiểm tra file chính đã repackage, không chọn `.original` khi deploy |
| Đổi scope để giảm kích thước rồi ứng dụng crash | Không có runtime provider thực sự | Hoàn nguyên scope, xác định dependency nào cần runtime trước khi tối ưu |
| CI gate pass nhưng image khác vẫn lỗi | Stage deploy dùng artifact/image khác thứ đã scan | Gắn hash/digest và bảo đảm deploy đúng artifact đã kiểm tra |

### 12.1 Trường hợp đặc biệt: `developmentOnly` không tự làm test runtime giống dev runtime

Khi thiết kế test, cần phân biệt:

- `developmentOnly` phục vụ các dependency chỉ cần **phát triển**.
- `testImplementation` và `testRuntimeOnly` phục vụ **test**.
- `testAndDevelopmentOnly` (khi có) phục vụ trường hợp kết hợp **test + dev**.

Đừng đặt một thư viện test thiết yếu vào `developmentOnly` rồi đoán nó chắc chắn nằm trong mọi test classpath. Nếu test cần, hãy khai báo dependency ở configuration test có chủ đích và xác nhận `testRuntimeClasspath`. Tương tự, không đưa toàn bộ `testImplementation` vào runtime production chỉ vì `@SpringBootTest` cần chúng.

### 12.2 Trường hợp đặc biệt: có cùng module qua nhiều đường

Một module có thể xuất hiện ở nhiều cấu hình/đường dependency. Ví dụ `lombok` được đưa vào `compileOnly` nhưng một plugin khác lại thêm nó vào `runtimeOnly`; hoặc Tomcat được đưa vào `providedRuntime` và kéo bắc cầu từ `starter-web`.

Vì vậy câu trả lời "artifact X nằm trong Y vì có dòng Z" chỉ đúng khi xem **resolved graph + classpath cuối + archive cuối**. Kết quả Maven/Gradle có thể thay đổi bởi BOM, dependency constraints, exclusion, plugin version, resolution rules và cấu hình riêng của module.

## 13. Bài thực hành theo phương pháp đo trước–sau

### Thực hành A – Maven `provided` trong executable JAR/WAR

1. Dùng `pom.xml` và `DemoApplication` ở phần 7; giữ phiên bản đã ghim.
2. Chạy `dependency:tree` để xác định `spring-boot-starter-tomcat` đang có scope `provided`.
3. Build executable WAR, mở `target/demo-0.0.1-SNAPSHOT.war` bằng `jar tf`. Xác nhận các file `tomcat-embed-...jar` trong `WEB-INF/lib-provided`.
4. Chạy `java -jar ...war` và gọi `/ping`. Ghi response body.
5. Trên **nhánh/bản sao**, đổi packaging sang JAR, build lại rồi kiểm tra `BOOT-INF/lib`. Giải thích vì sao Maven provided không tự làm Tomcat biến mất khỏi executable JAR.
6. Xem `effective-pom` và nêu plugin/execution nào làm `repackage`.
7. Trả lời: `provided` của Maven core khác gì với quyết định packaging của Spring Boot?

### Thực hành B – Gradle `compileOnly` với Lombok

1. Dùng `build.gradle` phần 8 và thêm `Greeting.java`, `GreetingProbe.java`.
2. Chạy `./gradlew classes` và `java -cp build/classes/java/main com.example.demo.GreetingProbe`, xác nhận response `hello`.
3. Xem `compileClasspath` có Lombok, `runtimeClasspath` không có chỉ bởi dòng `compileOnly`.
4. Build `bootJar`; tìm `lombok-...jar` trong `BOOT-INF/lib` và ghi kết quả.
5. Trên bản sao, bỏ `annotationProcessor` nhưng giữ `compileOnly`; quan sát lỗi compiler do method `getValue()` không được sinh; hoàn nguyên cấu hình sau khi học.
6. Trả lời: tại sao `testCompileOnly` và `testAnnotationProcessor` là những cấu hình riêng?

### Thực hành C – Gradle `developmentOnly` với DevTools

1. Chạy `./gradlew dependencies --configuration runtimeClasspath`, tìm DevTools.
2. Chạy `./gradlew dependencies --configuration productionRuntimeClasspath`, đối chiếu đường dependency DevTools.
3. Chạy `./gradlew clean bootJar`, kiểm tra `BOOT-INF/lib` không có `spring-boot-devtools-...jar` theo mặc định.
4. Trên nhánh riêng, thử chuyển DevTools sang `runtimeOnly` và so sánh graph/package; **không** đưa artifact thử nghiệm vào pipeline release.
5. Giải thích sự khác nhau giữa DevTools "auto-disable khi packaged" và "không có byte DevTools trong artifact".

### Thực hành D – Gradle `providedRuntime` và WAR

1. Chuyển ứng dụng MVC Gradle sang War plugin và thêm Tomcat ở `providedRuntime`.
2. Chạy test theo cách thích hợp; nếu dùng web integration test, xác nhận có Servlet runtime.
3. Chạy `./gradlew clean war bootWar`, mở cả plain WAR và Boot WAR.
4. Xác nhận plain WAR không đưa Tomcat vào `WEB-INF/lib`, còn Boot WAR có nó trong `WEB-INF/lib-provided`.
5. Chạy `java -jar` cho Boot WAR và thử deploy lên external container **tương thích** nếu có môi trường.
6. Trên nhánh thử nghiệm, thay `providedRuntime` bằng `compileOnly`, chạy lại test/bootWar và giải thích khác biệt dựa trên evidence; hoàn nguyên sau thử nghiệm.
7. Tìm một dependency bắc cầu được đánh dấu provided; kiểm tra nó có bị loại khỏi WAR thường như tài liệu Gradle cảnh báo không.

### Thực hành E – Viết báo cáo có thể kiểm chứng

Với mỗi dependency trong bài, ghi báo cáo theo mẫu:

```text
Module:
Build system và phiên bản:
Loại artifact: plain JAR / Boot JAR / plain WAR / Boot WAR
Dependency (group:artifact:version):
Scope/configuration ở build file:
Xuất hiện ở compileClasspath? Bằng chứng:
Xuất hiện ở testRuntimeClasspath? Bằng chứng:
Xuất hiện ở development runtime? Bằng chứng:
Có trong artifact phát hành? Đường dẫn ZIP:
External container cung cấp gì?
Kết luận (vì sao dùng provided/compileOnly/developmentOnly):
```

Đây là **mẫu báo cáo cho người học**. Phần kết luận phải dựa trên lệnh thật của dự án, không điền toàn bộ "có/không" từ cảm giác. Nếu một report chỉ ghi "**dependency:tree có X**" hoặc "**Gradle build thành công**" mà không mở artifact, thì chưa hoàn thành mục tiêu kiểm tra đóng gói.

## 14. Tài liệu chính thức

- Apache Maven – Introduction to the Dependency Mechanism: `compile`, `provided`, `runtime`, `test`, `optional`: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Spring Boot 3.3 Maven Plugin – Packaging Executable Archives, `repackage`, provided dependencies, WAR layout và exclusions: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3 Gradle Plugin – Packaging Executable Archives, `bootJar`/`bootWar`, `developmentOnly`, `providedRuntime`: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot 3.3 – Traditional Deployment, Maven provided và Gradle providedRuntime cho external Servlet container: https://docs.spring.io/spring-boot/3.3/how-to/deployment/traditional-deployment.html
- Gradle – Java Plugin: compileOnly, annotationProcessor, test classpaths và runtimeClasspath: https://docs.gradle.org/current/userguide/java_plugin.html
- Gradle – War Plugin: providedCompile, providedRuntime, sự khác nhau với compileOnly và tính bắc cầu: https://docs.gradle.org/current/userguide/war_plugin.html
- Spring Boot 3.3 Gradle Plugin API – các tên configuration developmentOnly, testAndDevelopmentOnly và productionRuntimeClasspath: https://docs.spring.io/spring-boot/3.3/gradle-plugin/api/java/org/springframework/boot/gradle/plugin/SpringBootPlugin.html

**Ghi nhớ:** `provided`, `compileOnly` và `developmentOnly` không phải ba cách viết tương đương của "không đóng gói". Chúng là những **hợp đồng classpath khác nhau**. Riêng Spring Boot packaging có các bước xử lý bổ sung. Muốn kết luận đúng, hãy nối **khai báo → compile/test/dev runtime → Boot packaging → ZIP layout → startup thực tế**.

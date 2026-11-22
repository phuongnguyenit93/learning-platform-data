# Loại trừ phụ thuộc, xử lý optional và tránh thiếu thư viện khi chạy

## 1. Vấn đề cần giải quyết

Trong dự án Spring Boot, một dependency có thể kéo theo nhiều **transitive dependencies** (phụ thuộc bắc cầu). Đôi khi một thư viện không cần thiết, xung đột phiên bản hoặc đi kèm triển khai không phù hợp; khi đó cần **exclusion**. Đôi khi tác giả một thư viện muốn tính năng tích hợp chỉ hoạt động nếu người sử dụng chủ động chọn thêm thư viện hỗ trợ; Maven cung cấp cờ **optional**. Và đôi khi build/test thành công nhưng bản chạy thật thiếu lớp vì **runtime classpath** khác compile/test classpath hoặc khâu đóng gói không chứa dependency cần thiết.

Ba khái niệm cần tách biệt:

| Cơ chế | Quyết định điều gì? | Không có nghĩa là |
|---|---|---|
| Exclusion | Không kéo một dependency bắc cầu qua **đường phụ thuộc được chỉ định** | Xóa artifact đó khỏi mọi đường đi hoặc thay thế nó tự động |
| Maven `<optional>true</optional>` | Dự án **phụ thuộc vào thư viện của bạn** có tự động nhận dependency ấy hay không | Thư viện tùy chọn bị loại khỏi classpath của chính module khai báo |
| Scope/configuration + packaging | Dependency nằm trên compile, test, runtime classpath và artifact nào | Chỉ cần compile thành công là runtime chắc chắn đủ lớp |

Hình dung:

```text
Ứng dụng A
├── thư viện B
│   ├── thư viện C
│   └── thư viện D
└── thư viện E
    └── thư viện D

A loại trừ D qua nhánh B:
A -> B -X-> D
A -> E ---> D    (D vẫn có thể được chọn qua E)
```

**Nguyên tắc thực hành:** chỉ loại trừ khi đã biết thư viện đi vào qua đâu, tại sao không cần hoặc cần thay bằng gì, rồi xác minh đồ thị dependency **và** bản chạy cuối cùng.

## 2. Hiểu dependency ở từng giai đoạn

Một lớp có thể có mặt lúc biên dịch nhưng vắng mặt khi chạy. Đây là lý do lỗi **`NoClassDefFoundError`** hoặc **`ClassNotFoundException`** thường xuất hiện sau khi cấu hình scope, optional hoặc exclusion sai.

### Maven scope

| Scope trong `pom.xml` | Compile classpath | Runtime classpath Maven thông thường | Ý nghĩa |
|---|---|---|---|
| `compile` (mặc định) | Có | Có | Cần để biên dịch và chạy |
| `runtime` | Không | Có | Ví dụ JDBC driver được nạp bằng cơ chế runtime |
| `provided` | Có | Không | Chỉ dùng nếu môi trường chạy thực sự cung cấp |
| `test` | Không cho mã chính | Không cho ứng dụng chính | Chỉ phục vụ compile/chạy test |

Đây là **quy tắc classpath của Maven**, không phải cam kết mọi plugin đóng gói sẽ xử lý giống nhau. Ví dụ **Spring Boot Maven Plugin `repackage` có quy tắc riêng với dependency `provided`**: executable archive có thể bao gồm chúng; với executable WAR, dependency provided được đặt vào `WEB-INF/lib-provided` để không xung đột với servlet container. Vì vậy đừng chỉ nhìn scope, hãy kiểm tra cấu trúc JAR/WAR thực tế.

### Gradle configuration thường gặp

| Configuration | Compile chính | Runtime chính | Dùng khi |
|---|---|---|---|
| `implementation` | Có | Có | Ứng dụng dùng thư viện để compile và chạy |
| `runtimeOnly` | Không | Có | Driver hoặc provider chỉ cần khi chạy |
| `compileOnly` | Có | Không | API thực sự được runtime/môi trường khác cung cấp, hoặc một số công cụ compile-time |
| `testImplementation` | Chỉ compile test | Chỉ test runtime | Thư viện unit/integration test |

`api` của plugin `java-library` làm dependency xuất hiện trong API compile của module tiêu thụ; `implementation` của thư viện không xuất hiện trên **compile classpath** của người dùng thư viện, nhưng thường vẫn tham gia runtime của họ. Không coi `implementation` là “không bao giờ transitive”: điểm quan trọng là **phân biệt API compile và runtime**.

Nếu mã nguồn trực tiếp dùng một thư viện khi runtime, hãy khai báo dependency trực tiếp thay vì chỉ hy vọng một starter/thư viện khác kéo nó theo. BOM và `dependencyManagement` chỉ quản lý phiên bản; chúng **không tự thêm dependency** vào classpath.

## 3. Maven exclusions: loại đúng dependency, đúng nhánh

Giả sử:

```text
app
└── library-a
    └── legacy-json-lib
```

Nếu `library-a` kéo theo `legacy-json-lib` mà ứng dụng không sử dụng (hoặc đã thay bằng thư viện tương thích), có thể đặt exclusion **bên trong dependency khai báo `library-a`**:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>library-a</artifactId>
    <version>1.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>com.example</groupId>
            <artifactId>legacy-json-lib</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

Đây là **một đoạn XML minh họa**, không phải `pom.xml` độc lập; tọa độ `com.example` chỉ để mô tả quan hệ. Trong Maven, exclusion dùng `groupId` + `artifactId` và đặt trên **nhánh dependency** cần loại. Nó không cần biết phiên bản của artifact bị loại; nếu dependency tương tự vào qua nhánh khác, nhánh ấy vẫn có thể đưa artifact trở lại.

Đầu tiên hãy tìm đúng đường đi:

```bash
# Dự án Maven có wrapper:
./mvnw dependency:tree

# Chỉ quan tâm artifact mục tiêu; thay bằng tọa độ thực tế
./mvnw dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-logging

# Xem dependency thuộc runtime theo bộ lọc của Maven Dependency Plugin
./mvnw dependency:tree -Dscope=runtime
```

Trong Windows PowerShell, dùng `.\mvnw.cmd` thay `./mvnw`. Nếu dự án không có wrapper, dùng `mvn`. Lệnh `dependency:tree` hiển thị dependency sau resolution; đọc các nhánh cha để biết **nơi cần đặt exclusion**, và chạy lại sau khi sửa.

### Ví dụ thực tế: thay logging starter trong Spring Boot

Ở dự án **Spring Boot 3.x dùng Maven**, một cách chuyển từ logging starter mặc định sang Log4j2 là:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
        <exclusions>
            <exclusion>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-starter-logging</artifactId>
            </exclusion>
        </exclusions>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-log4j2</artifactId>
    </dependency>
</dependencies>
```

Đoạn này giả định `pom.xml` đã có `spring-boot-starter-parent` hoặc Spring Boot BOM quản lý phiên bản starter. Nó minh họa **loại phần không muốn và thêm phần thay thế**. Nếu những dependency khác cũng kéo `spring-boot-starter-logging`, phải xem lại cây dependency và xử lý các nhánh tương ứng; không được mặc định một exclusion sẽ xóa logging starter ở mọi nơi. Kiểm tra chỉ còn provider/implementation logging dự kiến trên runtime classpath.

Đừng loại `slf4j-api` một cách máy móc khi thay logging: API logging và implementation/provider là các thành phần khác nhau. Loại không đúng có thể khiến ứng dụng compile được nhưng lỗi nạp class ở runtime.

## 4. Gradle excludes: cùng mục đích, cú pháp khác

Với `build.gradle` dùng **Groovy DSL**, có thể loại dependency bắc cầu trên một nhánh:

```groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-logging'
    }

    implementation 'org.springframework.boot:spring-boot-starter-log4j2'
}
```

Ở đây giả định project đã cấu hình Spring Boot plugin, repositories và quản lý phiên bản dependency. `exclude` dùng **group + module**; trong Gradle, “module” tương ứng với `artifactId` khi làm việc với module Maven thông thường.

Cách viết Kotlin DSL tương đương:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web") {
        exclude(
            group = "org.springframework.boot",
            module = "spring-boot-starter-logging"
        )
    }

    implementation("org.springframework.boot:spring-boot-starter-log4j2")
}
```

Đây là **các khối dependencies để chèn vào file build đã cấu hình sẵn**, không phải toàn bộ file `build.gradle[.kts]`. Với Gradle, khi module bị exclude trên một đường đi nhưng đường khác vẫn yêu cầu nó, kết quả phụ thuộc **toàn bộ đồ thị và cấu hình resolution**. Dùng lệnh chẩn đoán:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-boot-starter-logging
```

Trên Windows dùng `gradlew.bat`. Nếu không có Gradle Wrapper, dùng `gradle` đã cài. Plugin Java/Spring Boot thông thường có configuration `runtimeClasspath`; dự án không áp dụng Java plugin hoặc dùng cấu hình đặc biệt cần kiểm tra tên configuration thực tế.

**Tránh exclude toàn cục** kiểu `configurations.all { exclude ... }` để “dọn cây” hàng loạt. Cách đó dễ bỏ nhầm thư viện do module khác thực sự cần, khiến runtime lỗi khó truy ra. Luôn ưu tiên một nhánh và một module cụ thể.

## 5. Maven optional: tác động đến người tiêu thụ thư viện

Maven `<optional>true</optional>` dùng khi **người viết thư viện** hỗ trợ một tính năng có thể chọn bật. Ví dụ module `reporting-core` có tích hợp PostgreSQL, nhưng người chỉ dùng phần xử lý dữ liệu cơ bản không cần driver PostgreSQL.

Trong `pom.xml` của **reporting-core** (giả định phiên bản PostgreSQL đã được quản lý bởi parent/BOM, hoặc cần ghi `version`):

```xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <optional>true</optional>
</dependency>
```

Ý nghĩa:

1. **Trong chính `reporting-core`**, dependency được khai báo vẫn có thể tham gia compile/runtime theo scope tương ứng. `optional` không phải một scope và không có nghĩa xóa dependency khỏi classpath của module này.
2. **Trong ứng dụng `orders-app` phụ thuộc vào `reporting-core`**, driver PostgreSQL **không tự động đi theo** chỉ vì `reporting-core` đánh dấu optional.
3. Nếu `orders-app` thực sự dùng chức năng PostgreSQL, ứng dụng **phải khai báo driver trực tiếp**.

Trong `pom.xml` của **orders-app** có parent/BOM quản lý version:

```xml
<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>reporting-core</artifactId>
        <version>1.0.0</version>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Ở đây `com.example:reporting-core:1.0.0` là tọa độ minh họa; phải có module thật khi chạy. `runtime` hợp lý khi ứng dụng dùng JDBC qua `DriverManager`/Spring JDBC, không tham chiếu trực tiếp các lớp driver để compile.

**Không nhầm optional với exclude:**

| Tình huống | Ai quyết định? | Hành vi |
|---|---|---|
| `reporting-core` khai báo PostgreSQL `optional` | Tác giả thư viện | Không truyền dependency ấy mặc định cho người tiêu thụ |
| `orders-app` loại một dependency qua `reporting-core` | Tác giả ứng dụng | Chặn dependency đi theo nhánh khai báo được chọn |
| `orders-app` khai báo PostgreSQL trực tiếp | Tác giả ứng dụng | Driver được đưa vào classpath phù hợp bất kể optional của `reporting-core` |
| `orders-app` chỉ import BOM | Tác giả ứng dụng | Phiên bản có thể được quản lý, nhưng driver chưa được thêm |

**Optional là quy tắc propagation trong metadata Maven.** Gradle có mô hình variant/feature capability riêng; không coi `optional` của Maven là bản sao hoàn chỉnh của `compileOnly`, `runtimeOnly` hay một Gradle configuration. Khi tiêu thụ thư viện xuất bản từ Maven bằng Gradle, hãy kiểm tra Gradle resolved graph thực tế thay vì suy luận máy móc.

Nếu nhiều tính năng tùy chọn độc lập tồn tại, thiết kế **module riêng** (`reporting-jdbc`, `reporting-core`...) hoặc feature variant rõ ràng thường dễ dùng và kiểm thử hơn so với lạm dụng optional.

### Optional khi đóng gói Spring Boot

Ứng dụng Spring Boot thường là thành phần cuối cùng được chạy, không phải thư viện được import bởi nhiều ứng dụng khác. Do đó, **đừng đánh dấu dependency cần cho production thành optional chỉ nhằm giảm kích thước executable JAR**. Hành vi đóng gói optional còn phụ thuộc phiên bản Spring Boot Maven Plugin và tham số như `includeOptional`; một số bản mới mặc định không đóng gói optional. Quyết định an toàn là khai báo đúng dependency runtime, cấu hình plugin khi thực sự cần, rồi **kiểm tra archive và chạy ứng dụng đã đóng gói**.

## 6. Tránh thiếu thư viện ở runtime: hiểu đúng classpath

**Compile classpath ≠ runtime classpath ≠ test runtime classpath.** Trường hợp phổ biến:

- Dependency bị đặt sai `provided`/`compileOnly`, trong khi môi trường chạy **không cung cấp** nó.
- Dependency chỉ có `test`/`testImplementation`: unit test có class nhưng ứng dụng chạy thật thì không.
- Một dependency optional bị bỏ khỏi cây khi thư viện được tiêu thụ; ứng dụng quên khai báo tính năng cần dùng.
- Exclusion xóa thư viện cần cho logic, reflection, serialization, SPI hoặc auto-configuration.
- Artifact JAR thông thường không nhúng dependency; chạy bằng `java -jar` thiếu classpath ngoài.
- Docker image/chạy CI lấy nhầm artifact, thiếu thư viện runtime hay chứa version khác.
- BOM giải quyết phiên bản khác kỳ vọng, dẫn tới `NoSuchMethodError` hoặc lỗi tương thích nhị phân.

### Thực nghiệm Java 17 độc lập: compile được nhưng chạy thiếu dependency

Đoạn sau **không dùng thư viện bên ngoài và chạy được trên Java 17+**. Nó mô phỏng ứng dụng biên dịch với thư viện có mặt, nhưng khi chạy thư viện bị bỏ khỏi classpath.

Tạo hai file:

`src/demo/lib/Feature.java`

```java
package demo.lib;

public final class Feature {
    private Feature() {}

    public static String message() {
        return "Feature available";
    }
}
```

`src/demo/app/Main.java`

```java
package demo.app;

import demo.lib.Feature;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Feature.message());
    }
}
```

Ở root ví dụ, trên **Linux/macOS**, chạy:

```bash
mkdir -p build/lib build/app
javac -d build/lib src/demo/lib/Feature.java
javac -cp build/lib -d build/app src/demo/app/Main.java

# Runtime thiếu dependency: chương trình không chạy thành công
java -cp build/app demo.app.Main

# Bổ sung thư mục lib vào runtime classpath:
java -cp "build/app:build/lib" demo.app.Main
```

Lệnh `java -cp build/app demo.app.Main` có thể báo `NoClassDefFoundError: demo/lib/Feature` vì JVM không tìm thấy `Feature` lúc gọi. Không dự đoán nguyên văn cả stack trace do thông báo chi tiết có thể khác giữa bản JDK. Lệnh cuối in chính xác:

```text
Feature available
```

Trong **Windows PowerShell**, thay dấu phân cách classpath `:` bằng `;`, ví dụ:

```powershell
New-Item -ItemType Directory -Force build/lib, build/app | Out-Null
javac -d build/lib src/demo/lib/Feature.java
javac -cp build/lib -d build/app src/demo/app/Main.java

# Có dependency lúc compile nhưng không có lúc runtime:
java -cp build/app demo.app.Main

# Có dependency lúc runtime:
java -cp "build/app;build/lib" demo.app.Main
```

Lệnh cuối cũng in `Feature available`. Nếu thư viện là JAR thay vì thư mục, runtime classpath phải trỏ đến **JAR đó**. Trong Maven/Gradle, chính scope/configuration và plugin đóng gói quản lý danh sách JAR/runtime classpath này.

### Các lỗi Java dễ bị nhầm lẫn

| Lỗi | Diễn giải và kiểm tra ban đầu |
|---|---|
| `ClassNotFoundException` | Thường do `Class.forName` hoặc class loader nạp tên lớp không có trên classpath |
| `NoClassDefFoundError` | JVM cần một định nghĩa class nhưng không có hoặc không khởi tạo được; kiểm tra runtime classpath và lỗi khởi tạo tĩnh |
| `NoSuchMethodError` | Có class nhưng phiên bản chạy thiếu method mà bytecode đã biên dịch trông đợi; thường do version/binary mismatch |
| `ServiceConfigurationError` hoặc không tìm thấy provider SPI | Provider/configuration `META-INF/services` không có, thiếu JAR, lỗi khởi tạo, hoặc bị đóng gói sai |
| `ClassCastException` | Không tự kết luận thiếu dependency; có thể do class loader hoặc kiểu dữ liệu khác nhau |
| Spring `NoSuchBeanDefinitionException` | Không tìm được bean phù hợp; có thể do điều kiện auto-configuration, component scan hoặc cấu hình, không nhất thiết thiếu JAR |

**Lưu ý:** Một thư viện hiện diện trong cây dependency chưa chắc có trên runtime classpath của artifact đang chạy; phải xét scope, exclusions, phiên bản sau resolution, packaging và class loader.

## 7. Kiểm tra artifact Spring Boot thật sự chứa gì

Spring Boot executable JAR được tạo bởi `spring-boot-maven-plugin:repackage` hoặc Gradle `bootJar` thường có cấu trúc:

```text
BOOT-INF/classes/  <- class và resource của ứng dụng
BOOT-INF/lib/      <- các dependency JAR được đóng gói
META-INF/
org/springframework/boot/loader/...
```

Cấu trúc cụ thể có thể thay đổi theo phiên bản và cách đóng gói; executable WAR có `WEB-INF/lib`, có thể có `WEB-INF/lib-provided`. Một JAR thông thường tạo bởi `maven-jar-plugin` hoặc Gradle `jar` thường **không** nhúng tất cả dependency.

Ví dụ dự án có artifact `target/boot-deps-demo-0.0.1-SNAPSHOT.jar`, trên Linux/macOS:

```bash
./mvnw clean package
jar tf target/boot-deps-demo-0.0.1-SNAPSHOT.jar | grep 'BOOT-INF/lib/'
java -jar target/boot-deps-demo-0.0.1-SNAPSHOT.jar
```

Trên Windows PowerShell:

```powershell
.\mvnw.cmd clean package
jar tf target/boot-deps-demo-0.0.1-SNAPSHOT.jar | Select-String 'BOOT-INF/lib/'
java -jar target/boot-deps-demo-0.0.1-SNAPSHOT.jar
```

**Đây là ví dụ lệnh kiểm tra cho một artifact có tên đã cho**, chỉ hoạt động nếu dự án thực sự tạo file đó và đã cấu hình executable JAR. Dùng đường dẫn artifact thật từ build log trên dự án khác. `jar` là công cụ đi cùng JDK. Không khẳng định đầu ra runtime của ứng dụng cụ thể khi chưa có mã ứng dụng và cấu hình.

Cần kiểm tra:
1. Dependency cần dùng có được **resolve** đúng phiên bản ở runtime không?
2. Trong executable JAR, có JAR phù hợp dưới `BOOT-INF/lib/` không, trừ dependency được môi trường ngoài cung cấp hợp lệ?
3. Artifact triển khai trên Docker/VM có đúng là artifact vừa kiểm tra?
4. Khi chạy từ `java -jar` (hoặc image/container thật), các nhánh chức năng cần thư viện đó có được kích hoạt và kiểm thử không?

**Đặc thù quan trọng của Spring Boot:** `repackage` có thể bao gồm dependency `provided` theo quy tắc riêng của plugin; executable WAR đặt chúng trong `WEB-INF/lib-provided`. `includeOptional` và loại trừ ở cấp plugin có hành vi phụ thuộc phiên bản. Không suy từ Maven scope thuần rằng dependency chắc chắn có hoặc không có trong `BOOT-INF/lib/`; **archive đã build** mới là bằng chứng cuối.

## 8. Quy trình an toàn trước và sau khi loại trừ

### Bước 1 — Xác định nguyên nhân

Trước khi sửa POM/Gradle, ghi rõ mục tiêu: thay logging provider, tránh dependency có lỗ hổng, loại module không cần thiết, hoặc sửa conflict phiên bản. Nếu lỗi chỉ là **version conflict**, đôi khi **quản lý phiên bản bằng BOM/constraint** phù hợp hơn exclusion. Không dùng exclude để che triệu chứng khi chưa xác định thư viện nào thật sự được nạp.

### Bước 2 — Xem đồ thị đã resolve

Maven:

```bash
./mvnw dependency:tree
./mvnw dependency:tree -Dincludes=org.postgresql:postgresql
./mvnw help:effective-pom
```

`help:effective-pom` hỗ trợ kiểm tra POM sau inheritance, profile và quản lý cấu hình. Bộ lọc `dependency:tree` giúp truy các đường phụ thuộc. Nếu dùng Windows, thay `./mvnw` bằng `.\mvnw.cmd`.

Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency postgresql
./gradlew dependencies --configuration testRuntimeClasspath
```

Kiểm tra cả **compileClasspath**, **runtimeClasspath** và **testRuntimeClasspath** khi lỗi chỉ xuất hiện ở một giai đoạn.

### Bước 3 — Sửa nhỏ và nêu trách nhiệm dependency

- Nếu một transitive dependency không cần, exclude **đúng trên nhánh kéo nó vào**.
- Nếu một implementation bị thay thế (như logging provider), thêm implementation mới rõ ràng.
- Nếu thư viện của bạn có tính năng tích hợp tự chọn, cân nhắc optional để người tiêu thụ không vô tình nhận module phụ.
- Nếu ứng dụng **cần** dependency lúc chạy, khai báo trực tiếp ở `compile`/`runtime` hoặc `implementation`/`runtimeOnly` tùy cách mã sử dụng nó.
- Tránh đặt dependency production ở `test`/`provided`/`compileOnly` chỉ để ép build nhẹ hơn.
- Kiểm tra version qua BOM/parent/constraint và tính tương thích Java; Maven có thể chọn phiên bản theo luật mediation, Gradle có cơ chế chọn phiên bản riêng.

### Bước 4 — Kiểm tra lại trên bản build thật

1. Xem lại resolved dependency tree sau chỉnh sửa để biết artifact nào **thực sự được chọn hoặc bị loại**.
2. Chạy build có test: `./mvnw clean verify` hoặc `./gradlew clean build`.
3. Kiểm tra JAR/WAR đầu ra; nếu Spring Boot executable JAR, xem `BOOT-INF/lib/`.
4. Chạy **chính artifact sẽ triển khai**; kiểm thử chức năng có dependency vừa thay đổi, không chỉ thấy ứng dụng startup.
5. Nếu đóng gói Docker, chạy thử image đã build; bảo đảm build stage và runtime stage dùng đúng artifact.

Một bộ test chỉ dùng mock có thể bỏ sót dependency runtime thực tế. Nếu thay driver cơ sở dữ liệu, cần kiểm tra kết nối thật trong môi trường thử nghiệm phù hợp; nếu thay logging provider, kiểm tra binding/provider và log thực tế.

## 9. Các tình huống ra quyết định

| Tình huống | Nên làm gì? | Vì sao? |
|---|---|---|
| Starter kéo logging mặc định, muốn dùng Log4j2 | Exclude logging starter trên nhánh tương ứng, thêm Log4j2 starter, kiểm tra toàn đồ thị | Thay implementation phải có implementation thay thế |
| Thư viện của bạn tích hợp một database chỉ dùng bởi một số consumer | `optional` trên dependency của thư viện hoặc tách module tích hợp | Tránh ép mọi consumer mang driver |
| Ứng dụng dùng tính năng của dependency optional | Khai báo trực tiếp dependency ấy ở ứng dụng | Optional không tự truyền xuống consumer |
| Compile thành công nhưng chạy thiếu class | Kiểm tra runtime scope/configuration, exclusion, packaging và artifact deployed | Compile classpath có thể rộng hơn runtime |
| Chỉ có lỗi `NoSuchMethodError` khi chạy | Kiểm tra version JAR thực tế và quá trình resolution | Có thể là bất tương thích nhị phân, không phải class hoàn toàn thiếu |
| Muốn ép phiên bản thư viện đang được kéo bắc cầu | Ưu tiên BOM/dependency management/constraint có kiểm chứng | Exclusion không thay thế mọi cơ chế giải quyết phiên bản |
| Lỗi ở unit test nhưng không ở production | Kiểm tra `test` dependencies và test runtime classpath | Classpath test và ứng dụng khác nhau |
| Muốn giảm kích thước executable JAR | Tìm thư viện thật sự không sử dụng, hiểu quan hệ, kiểm thử sau exclude | Xóa tùy tiện dễ làm hỏng chức năng chỉ được nạp lúc chạy |

## 10. Checklist trước khi kết luận đã sửa xong

- [ ] Biết tọa độ `groupId:artifactId` (Maven) hoặc `group:module` (Gradle) của dependency cần xem.
- [ ] Biết dependency đi vào qua **nhánh nào**; không suy từ một dependency trực tiếp.
- [ ] Nếu exclude, đã xác nhận không còn nhánh khác kéo module trở lại hoặc đã xử lý tương ứng.
- [ ] Nếu module bị exclude từng phục vụ một tính năng, đã thêm bản thay thế/khai báo trực tiếp khi cần.
- [ ] Nếu dùng Maven optional, hiểu **consumer không được tự động nhận dependency**, còn module khai báo vẫn có thể sử dụng.
- [ ] Scope/configuration đúng cho compile, test và runtime; biết ngoại lệ riêng của plugin đóng gói.
- [ ] Phiên bản resolve phù hợp với Spring Boot BOM/JDK và không có conflict API.
- [ ] Bản JAR/WAR/image thật có dependency cần thiết, được chạy và kiểm thử chức năng quan trọng.
- [ ] Không dùng thành công của lệnh `package` đơn thuần thay cho thử nghiệm runtime.

**Tóm lược:** exclusion cắt một **đường phụ thuộc bắc cầu**; optional để **người sử dụng thư viện tự quyết định có nhận thêm dependency hay không**; scope/configuration và packaging mới quyết định **lúc chạy có lớp hay không**. Muốn sửa lỗi thiếu thư viện, hãy lần từ exception → runtime classpath → resolved dependency tree → POM/Gradle → artifact cuối, và kiểm chứng từng thay đổi.

### Tài liệu chính thức

- [Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Maven — Optional and Excluded Dependencies](https://maven.apache.org/guides/introduction/introduction-to-optional-and-excludes-dependencies)
- [Gradle — How to Exclude Transitive Dependencies](https://docs.gradle.org/current/userguide/how_to_exclude_transitive_dependencies.html)
- [Gradle — Dependency Configurations](https://docs.gradle.org/current/userguide/dependency_configurations.html)
- [Spring Boot Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html)
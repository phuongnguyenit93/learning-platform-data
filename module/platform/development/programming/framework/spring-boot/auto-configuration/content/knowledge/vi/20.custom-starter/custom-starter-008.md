# Xuất bản JAR thư viện thông thường thay vì dùng executable JAR làm dependency

Một ứng dụng Spring Boot thường được đóng gói thành **executable JAR** để chạy bằng `java -jar`. Tuy nhiên, định dạng đó không phù hợp để dùng làm dependency thông thường của một ứng dụng Maven/Gradle khác. Nếu module chứa code dùng chung hoặc custom starter được publish như thư viện, artifact mà consumer nhận được phải là **plain library JAR**.

**Nguyên tắc cốt lõi:** executable JAR của Spring Boot đặt class ứng dụng trong `BOOT-INF/classes` và các dependency lồng trong `BOOT-INF/lib`. Class loader Java thông thường và Maven consumer không tự đọc các vị trí đặc biệt này như classpath của một JAR thư viện. Một library JAR thông thường đặt class tại đường dẫn package ở gốc archive, ví dụ `com/example/api/PaymentClient.class`; dependency được khai báo trong POM để Maven giải quyết.

Có ba hướng xử lý:

1. **Tốt nhất:** tách code tái sử dụng thành module thư viện riêng; module đó xuất bản JAR thông thường, module ứng dụng mới tạo executable JAR.
2. **Một module cần cả hai artifact:** giữ JAR thường làm artifact chính và gắn executable JAR với classifier như `exec`.
3. **Module chỉ là thư viện:** không chạy `spring-boot:repackage`; nếu execution được kế thừa từ parent hoặc cấu hình dùng chung, bật `spring-boot.repackage.skip` cho module đó.

## 1. Vì sao executable JAR không phải library JAR?

Một JAR là định dạng ZIP có cấu trúc entry. Khác biệt nằm ở **cách đóng gói và cách khởi chạy**.

### 1.1. JAR thư viện thông thường

Một library JAR có cấu trúc gần như:

```text
shared-api-1.0.0.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── maven/
├── com/
│   └── example/
│       └── api/
│           ├── PaymentClient.class
│           └── PaymentRequest.class
└── META-INF/
    └── spring/
        └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Các class nằm ở **gốc archive theo đúng package path**. Khi Maven đưa JAR vào compile/runtime classpath, JVM có thể tìm được `com.example.api.PaymentClient` theo quy tắc classpath thông thường.

JAR thư viện thường **không tự nhúng tất cả dependency**. Thay vào đó, POM được publish cùng artifact mô tả dependency, version và scope. Maven consumer đọc POM để tải các dependency cần thiết theo dependency graph. Đây là mô hình chuẩn của một thư viện Java.

### 1.2. Spring Boot executable JAR

Khi Maven plugin chạy goal `repackage`, JAR được biến thành executable archive. Cấu trúc điển hình:

```text
service-app-1.0.0.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   └── com/example/app/Application.class
    ├── lib/
    │   ├── spring-boot-*.jar
    │   ├── spring-context-*.jar
    │   └── other-dependency.jar
    └── classpath.idx
```

- `BOOT-INF/classes` chứa class và resource của ứng dụng.
- `BOOT-INF/lib` chứa các dependency dưới dạng JAR lồng.
- Boot loader trong archive biết cách đọc cấu trúc đặc biệt này và tạo class loader phù hợp khi chạy executable archive.
- Manifest được plugin quản lý, thường có `Main-Class` trỏ tới launcher của Spring Boot và `Start-Class` trỏ tới main class của ứng dụng.

Có thể chạy:

```bash
java -jar service-app-1.0.0.jar
```

Nhưng khi một dự án khác khai báo executable JAR này như dependency Maven thông thường, Maven chỉ thêm chính file JAR đó vào classpath. JVM không tự coi `BOOT-INF/classes` là gốc classpath và cũng không tự mở mọi JAR bên trong `BOOT-INF/lib`. Vì vậy class ứng dụng không được tìm thấy theo cách consumer mong đợi.

**Kết luận:** executable JAR vẫn là một file JAR hợp lệ để chạy bằng Boot launcher, nhưng nó không có layout của một library JAR thông thường. Đổi tên file hoặc đổi `finalName` không sửa được cấu trúc bên trong.

## 2. Nhận diện lỗi khi dùng nhầm executable JAR làm dependency

Giả sử dự án consumer khai báo:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>shared-api</artifactId>
    <version>1.0.0</version>
</dependency>
```

Maven resolve dependency thành công, nhưng code consumer:

```java
import com.example.api.PaymentClient;

public class CheckoutService {
    private final PaymentClient client;

    public CheckoutService(PaymentClient client) {
        this.client = client;
    }
}
```

có thể gặp lỗi compile như:

```text
package com.example.api does not exist
cannot find symbol: class PaymentClient
```

Hoặc khi lỗi chỉ xuất hiện ở runtime:

```text
java.lang.NoClassDefFoundError: com/example/api/PaymentClient
Caused by: java.lang.ClassNotFoundException: com.example.api.PaymentClient
```

Thông báo thực tế phụ thuộc việc compiler/runtime đã nhìn thấy những phần classpath nào. Điểm chẩn đoán là **artifact đã được resolve nhưng class không nằm ở vị trí mà classpath thông thường tìm kiếm**.

Các dấu hiệu thường gặp:

- Dependency xuất hiện trong `mvn dependency:tree` nhưng import class vẫn thất bại.
- `jar tf artifact.jar` cho thấy class nằm dưới `BOOT-INF/classes`.
- `BOOT-INF/lib` có dependency lồng nhưng consumer không nhìn thấy các dependency đó như dependency transitive.
- Dùng classifier executable như `exec` trong khai báo dependency dù artifact chính không classifier đã là JAR thường.
- Một module ứng dụng vừa chứa code dùng chung vừa được repackaged; module consumer phụ thuộc vào artifact chính đã bị thay bằng executable JAR.

Đừng vội thêm thủ công tất cả JAR trong `BOOT-INF/lib` vào consumer classpath. Điều đó bỏ qua POM metadata, dễ gây lệch version và không giải quyết việc class của chính ứng dụng nằm dưới `BOOT-INF/classes`.

## 3. Thiết kế nên dùng: tách library module và application module

Nếu code sẽ được nhiều ứng dụng sử dụng, cấu trúc multi-module giúp ranh giới artifact rõ ràng:

```text
payment-platform/
├── pom.xml
├── payment-api/
│   ├── pom.xml
│   └── src/main/java/com/example/payment/
│       ├── PaymentClient.java
│       └── PaymentRequest.java
└── checkout-app/
    ├── pom.xml
    └── src/main/java/com/example/checkout/
        └── CheckoutApplication.java
```

- `payment-api` chứa interface, DTO, abstraction hoặc code dùng chung. Module này xuất bản **plain JAR**.
- `checkout-app` phụ thuộc vào `payment-api` và chứa `@SpringBootApplication`, cấu hình triển khai và main class.
- Chỉ `checkout-app` áp dụng `spring-boot-maven-plugin` để tạo executable JAR.

### 3.1. Parent POM khai báo module

Ví dụ `payment-platform/pom.xml` dùng Spring Boot parent để quản lý dependency/plugin version:

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
    <artifactId>payment-platform</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>payment-api</module>
        <module>checkout-app</module>
    </modules>
</project>
```

Version `3.3.13` được chọn làm ví dụ đồng bộ với tài liệu Boot 3.3; dự án thực tế nên dùng version đã được tổ chức chuẩn hóa.

### 3.2. POM của library module

`payment-api/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>payment-platform</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>payment-api</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <!-- Chỉ khai báo dependency mà API thực sự cần. -->
    </dependencies>
</project>
```

Maven mặc định tạo JAR thường ở phase `package`. Module thư viện **không cần** `spring-boot-maven-plugin` hoặc goal `repackage`. Nếu plugin repackage được khai báo ở một parent POM nội bộ và kế thừa xuống module này, hãy skip tại module:

```xml
<properties>
    <spring-boot.repackage.skip>true</spring-boot.repackage.skip>
</properties>
```

Hoặc cấu hình `<skip>true</skip>` trong `spring-boot-maven-plugin` của module. Thuộc tính `spring-boot.repackage.skip` là user property của goal `repackage`. Chỉ dùng cách này khi module thực sự có execution đó; nếu plugin không được áp dụng thì không cần thêm cấu hình skip.

**Chú ý:** không phải cứ khai báo `spring-boot-starter-parent` là mọi JAR đều tự động bị repackaged. Parent chuẩn bị execution `repackage` cho plugin; plugin phải được áp dụng theo cấu hình build. Kiểm tra effective POM để biết module nào thực sự chạy goal này.

### 3.3. POM của application module

`checkout-app/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>payment-platform</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>checkout-app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>payment-api</artifactId>
            <version>1.0.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Nếu dự án kế thừa `spring-boot-starter-parent`, parent đã cấu hình execution `repackage`; khai báo plugin sẽ kích hoạt execution đó. Nếu chỉ import BOM mà không kế thừa parent, cần khai báo version plugin và goal `repackage` trong execution theo tài liệu Maven plugin.

Kết quả mong đợi:

- `payment-api/target/payment-api-1.0.0.jar` là JAR thường.
- `checkout-app/target/checkout-app-1.0.0.jar` là executable JAR.
- `checkout-app` sử dụng `payment-api` qua dependency coordinate bình thường.

Build cả hai module từ root:

```bash
mvn clean package
```

Chỉ cài vào local Maven repository:

```bash
mvn clean install
```

Khi publish cho các dự án khác, dùng `mvn deploy` sau khi cấu hình repository và credentials của tổ chức. Artifact `payment-api` được publish cùng POM mô tả các dependency cần thiết; executable artifact của ứng dụng được dùng để triển khai chạy.

## 4. Một module cần xuất bản cả JAR thường và executable JAR

Đôi khi chưa thể tách code ngay, hoặc một module vừa là artifact dùng lại vừa cần một bản chạy độc lập. Với Maven, cấu hình **classifier cho executable archive** để giữ JAR thường làm artifact chính.

Ví dụ `pom.xml` khi dùng `spring-boot-starter-parent`:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <executions>
                <execution>
                    <id>repackage</id>
                    <configuration>
                        <classifier>exec</classifier>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Ở đây execution id `repackage` là execution mà Spring Boot parent đã chuẩn bị. Ta thêm cấu hình classifier vào execution đó; tránh tạo một execution mới trùng chức năng.

Nếu **không** dùng `spring-boot-starter-parent`, khai báo goal rõ ràng:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>3.3.13</version>
    <executions>
        <execution>
            <goals>
                <goal>repackage</goal>
            </goals>
            <configuration>
                <classifier>exec</classifier>
            </configuration>
        </execution>
    </executions>
</plugin>
```

Version plugin cần đồng bộ với version Spring Boot của dự án; ví dụ dùng `3.3.13` để minh họa Boot 3.3. Nếu BOM quản lý dependency nhưng không quản lý plugin, hãy khai báo plugin version rõ ràng.

### 4.1. Artifact được tạo và publish

Với `groupId=com.example`, `artifactId=shared-module` và `version=1.0.0`, hai file có dạng:

```text
target/
├── shared-module-1.0.0.jar
└── shared-module-1.0.0-exec.jar
```

- `shared-module-1.0.0.jar` là artifact chính, giữ layout thư viện thông thường.
- `shared-module-1.0.0-exec.jar` là artifact bổ sung, đã được Boot repackage để chạy bằng `java -jar`.

Khi chạy `mvn install` hoặc `mvn deploy`, plugin gắn executable archive với classifier `exec` bên cạnh artifact chính. Dependency thông thường của consumer nên tham chiếu artifact **không classifier**:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>shared-module</artifactId>
    <version>1.0.0</version>
</dependency>
```

Không thêm `<classifier>exec</classifier>` vào dependency nếu consumer cần sử dụng class của thư viện. Nếu thêm classifier `exec`, consumer sẽ lấy executable archive và gặp lại vấn đề layout `BOOT-INF/classes`.

### 4.2. Chọn `classifier`, `skip` hay `attach=false`?

| Cấu hình | Hành vi | Dùng khi |
| --- | --- | --- |
| Không classifier, không skip | `repackage` thay artifact chính bằng executable JAR; bản gốc thường được đổi thành `.original` trong build output. | Module chỉ phát hành để chạy, không dùng làm library dependency. |
| `classifier=exec` | Giữ artifact chính là JAR thường và attach executable JAR dưới classifier `exec`. | Cần cả dependency JAR lẫn bản executable để chạy. |
| `skip=true` hoặc `spring-boot.repackage.skip=true` | Không thực hiện repackage; Maven giữ JAR thường. | Module chỉ là thư viện. |
| `attach=false` | Tạo executable archive trong build nhưng không attach executable archive để install/deploy; chỉ artifact gốc được cài/publish. | Muốn tạo bản chạy cục bộ nhưng chỉ phát hành JAR gốc. |

`classifier` là lựa chọn rõ ràng nhất khi cần publish **cả hai** artifact. `skip` phù hợp với module library. `attach=false` không tương đương classifier: executable archive không được gắn vào Maven publication.

## 5. Nếu dự án dùng Gradle

Spring Boot Gradle plugin cung cấp hai task có mục đích khác nhau:

- `bootJar` tạo executable JAR.
- `jar` tạo JAR thông thường.

Trong Spring Boot Gradle plugin 3.3, khi `bootJar` được cấu hình, task `jar` dùng classifier `plain` theo convention để tránh trùng tên. Nếu muốn artifact không classifier là JAR thường và executable JAR có classifier `exec`, cấu hình:

**Groovy DSL – `build.gradle`:**

```groovy
tasks.named("bootJar") {
    archiveClassifier = "exec"
}

tasks.named("jar") {
    archiveClassifier = ""
}
```

**Kotlin DSL – `build.gradle.kts`:**

```kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar
import org.gradle.jvm.tasks.Jar

tasks.named<BootJar>("bootJar") {
    archiveClassifier.set("exec")
}

tasks.named<Jar>("jar") {
    archiveClassifier.set("")
}
```

Khi đó artifact plain JAR giữ tên chính và executable archive được gắn classifier. Với một module chỉ là thư viện, có thể tắt task executable:

```kotlin
tasks.named<BootJar>("bootJar") {
    enabled = false
}
```

Nếu dùng `maven-publish`, kiểm tra publication đang xuất bản artifact của Java component và đúng JAR không classifier. Đừng giả định rằng file nào xuất hiện trong `build/libs` cũng tự động là artifact chính của publication.

Build và kiểm tra:

```bash
./gradlew clean build
```

Mở `build/libs` để xem tên file và dùng `jar tf` để kiểm tra layout. Nếu cấu hình publication, kiểm tra POM/module metadata được tạo và xác nhận artifact chính là plain JAR.

## 6. Kiểm chứng artifact trước khi publish

Không nên chỉ nhìn tên file. Hãy kiểm tra **nội dung archive**, Maven coordinates và khả năng consumer compile.

### 6.1. Kiểm tra cấu trúc bằng `jar tf`

Với JAR thư viện:

```bash
jar tf target/payment-api-1.0.0.jar
```

Kết quả cần có đường dẫn class ở gốc, ví dụ:

```text
com/example/payment/PaymentClient.class
com/example/payment/PaymentRequest.class
META-INF/MANIFEST.MF
```

Nếu là custom starter, kiểm tra thêm resource auto-configuration nằm ở gốc:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Với executable JAR:

```bash
jar tf target/checkout-app-1.0.0.jar
```

Kết quả thường có các entry:

```text
BOOT-INF/classes/com/example/checkout/CheckoutApplication.class
BOOT-INF/lib/spring-boot-*.jar
org/springframework/boot/loader/...
META-INF/MANIFEST.MF
```

Nếu class dùng chung vẫn nằm dưới `BOOT-INF/classes` trong artifact mà consumer sẽ nhận, đó vẫn là executable layout; đổi tên file không biến nó thành library JAR.

### 6.2. Kiểm tra Maven dependency tree

Trong consumer, chạy:

```bash
mvn dependency:tree -Dincludes=com.example:payment-api
```

Xác nhận consumer resolve đúng `groupId`, `artifactId`, version và không vô tình dùng classifier executable. Dependency tree cho biết artifact Maven đã resolve; nó chưa chứng minh class bên trong nằm đúng layout, nên vẫn cần kiểm tra `jar tf` và compile.

### 6.3. Kiểm thử bằng một consumer thật

Consumer POM:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>payment-api</artifactId>
    <version>1.0.0</version>
</dependency>
```

Tạo một class sử dụng API:

```java
package consumer;

import com.example.payment.PaymentClient;
import com.example.payment.PaymentRequest;

public class ConsumerExample {

    public PaymentClient createClient() {
        PaymentRequest request = new PaymentRequest("order-42");
        return new PaymentClient(request);
    }
}
```

Đây là minh họa; `PaymentClient` và `PaymentRequest` cần có constructor tương ứng trong thư viện thực tế.

Chạy:

```bash
mvn clean test
```

Nếu consumer compile thành công và test resolve được các dependency cần thiết qua POM, đó là bằng chứng mạnh hơn việc chỉ nhìn file trong thư mục build. Trong CI, nên có một consumer integration test để kiểm tra artifact đã publish vào staging repository hoặc local repository sau `mvn install`.

### 6.4. Kiểm tra cả POM metadata

Một plain JAR vẫn có thể không dùng được nếu POM publish sai:

- Dependency cần cho public API phải được khai báo với scope phù hợp.
- Dependency chỉ dùng nội bộ khi chạy có thể có scope khác tùy thiết kế.
- Dependency tùy chọn cần được đánh dấu `optional` khi contract thư viện yêu cầu consumer tự chọn.
- Không publish dependency cần thiết ở scope `test`.
- Version Spring Framework/Spring Boot cần tương thích với consumer và được quản lý nhất quán.
- Resource, service loader file, metadata auto-configuration và license cần được đóng gói ở vị trí chuẩn.

JAR thông thường không nhúng dependency, vì vậy **POM là một phần của contract phân phối**. Chỉ kiểm tra class file mà bỏ qua POM sẽ không phát hiện được lỗi thiếu transitive dependency.

## 7. Các lỗi cấu hình thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng executable JAR làm dependency chính | Consumer không tìm thấy class trong `BOOT-INF/classes` | Publish plain JAR; executable để classifier riêng hoặc module ứng dụng riêng. |
| Repackage module library và không cấu hình classifier | Artifact chính bị thay bằng executable; JAR gốc có thể thành `.original` | Skip repackage hoặc dùng classifier `exec`. |
| Đổi `finalName` nhưng không đổi layout | File vẫn là executable JAR | Kiểm tra `jar tf`; sửa repackage/packaging task. |
| Chỉ tắt layered JAR | Layout `BOOT-INF` vẫn còn | Layering và executable layout là hai tính năng khác nhau. |
| Dùng `layout=NONE` để giả làm library | Archive vẫn không trở thành plain Maven library theo cấu trúc classpath chuẩn | Dùng Maven JAR plugin/default jar task cho library. |
| Thêm classifier `exec` vào dependency consumer | Consumer tiếp tục nhận executable archive | Dependency library phải dùng artifact không classifier. |
| Module thư viện kế thừa execution repackage từ parent | Build có thể repackaging ngoài ý muốn hoặc lỗi không tìm thấy main class | Kiểm tra effective POM; skip ở module library. |
| Cả parent và module tự khai báo hai execution repackage | Có thể repackage lặp hoặc artifact bị xử lý không như dự kiến | Chỉ cấu hình execution có sẵn hoặc khai báo một execution duy nhất. |
| Publish file JAR đúng nhưng POM thiếu dependency | Consumer compile/runtime thiếu class phụ thuộc | Kiểm tra POM và dependency tree. |
| Gradle publication lấy nhầm bootJar | Consumer nhận archive executable | Cấu hình classifier và xác nhận artifact từ Java component. |

## 8. Quy trình lựa chọn theo tình huống

### Tình huống A: thư viện thuần Java/Spring

- Dùng packaging `jar` thông thường.
- Không áp dụng `spring-boot-maven-plugin` goal `repackage`.
- Publish JAR cùng POM.
- Nếu là Spring Boot starter, đặt auto-configuration imports và metadata tại vị trí chuẩn trong JAR.
- Kiểm thử từ một consumer độc lập.

### Tình huống B: module ứng dụng có code cần chia sẻ

- Tách API/service dùng chung ra module library.
- Đưa implementation chạy ứng dụng vào module app.
- App phụ thuộc library bằng Maven coordinates bình thường.
- Chỉ module app được repackage thành executable JAR.

### Tình huống C: chưa thể tách module, cần hai file

- Giữ JAR thường làm artifact chính.
- Cấu hình executable JAR với classifier `exec`.
- Publish cả hai artifact.
- Consumer dùng dependency không classifier; môi trường triển khai dùng file `-exec.jar`.

### Tình huống D: chỉ cần publish thư viện, plugin repackage được kế thừa

- Đặt `spring-boot.repackage.skip=true` cho module library.
- Xác nhận JAR đầu ra là normal JAR.
- Không cần tạo executable artifact cho module đó.

## 9. Checklist trước khi phát hành

- [ ] Xác định artifact là **library**, **application** hay cần cả hai.
- [ ] Kiểm tra effective POM hoặc Gradle task graph để biết có chạy repackage/bootJar không.
- [ ] Với library, class nằm ở gốc JAR; không nằm dưới `BOOT-INF/classes`.
- [ ] Dependency của library được khai báo trong POM/module metadata; không trông chờ nested JAR.
- [ ] Nếu có cả hai artifact, executable có classifier riêng như `exec`.
- [ ] Dependency consumer không khai báo classifier executable.
- [ ] Kiểm tra auto-configuration imports, service loader, resource và metadata nếu thư viện cần chúng.
- [ ] Chạy `mvn clean verify` hoặc `./gradlew clean build`.
- [ ] Kiểm tra archive bằng `jar tf`.
- [ ] Cài/publish vào repository thử nghiệm và build một consumer độc lập.
- [ ] Xác nhận version, POM, dependency scopes và checksum của artifact được phát hành.

**Ghi nhớ:** executable JAR được tối ưu để **khởi chạy ứng dụng bằng Boot loader**; plain JAR được tối ưu để **đưa lên classpath và tái sử dụng như dependency**. Hãy tách module thư viện khỏi module ứng dụng khi có thể. Nếu phải phát hành cả hai từ một Maven module, dùng classifier `exec` để giữ artifact chính là JAR thường. Luôn xác minh bằng cấu trúc archive, POM và một consumer build thực tế.

### Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Packaging Executable Archives (Maven): https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot — How-to: Use a Spring Boot Application as a Dependency: https://docs.spring.io/spring-boot/how-to/build.html
- Spring Boot 3.3 — Packaging Executable Archives (Gradle): https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot — Executable JAR Format: https://docs.spring.io/spring-boot/specification/executable-jar/index.html
- Apache Maven — Introduction to the Dependency Mechanism: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
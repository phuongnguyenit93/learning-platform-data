# Các cấu hình implementation, api, runtimeOnly, compileOnly và testImplementation trong Gradle

## 1. Tại sao Gradle cần nhiều cấu hình phụ thuộc?

Ứng dụng Spring Boot thường dùng nhiều thư viện: Spring Web để viết HTTP API, JDBC driver để kết nối cơ sở dữ liệu, Lombok để hỗ trợ lúc biên dịch, JUnit để kiểm thử và các thư viện nội bộ do team tự viết. Những thư viện đó **không cần xuất hiện ở cùng một thời điểm hoặc trên cùng một classpath**.

Trong Gradle, **dependency configuration** là một cấu hình xác định mục đích sử dụng dependency. Khi khai báo:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

ta đang nói ba điều khác nhau:

- **implementation**: cần thư viện để biên dịch và chạy mã ứng dụng.
- **runtimeOnly**: chỉ cần thư viện khi ứng dụng chạy; không cần Java source trực tiếp import thư viện đó khi compile.
- **testImplementation**: chỉ cần thư viện trong các mã/test task, không phải dependency của ứng dụng production.

Trong một **module thư viện** sử dụng plugin **java-library**, Gradle còn có **api** để công bố dependency chứa kiểu dữ liệu xuất hiện trong giao diện công khai của thư viện. **compileOnly** dành cho thư viện chỉ cần ở bước biên dịch.

**Phạm vi bài học:** năm cấu hình **implementation**, **api**, **runtimeOnly**, **compileOnly**, **testImplementation**, trong dự án Gradle Java/Spring Boot. Chúng liên hệ với BOM và transitive dependency, nhưng không phải cách định nghĩa một REST API, không phải một loại phiên bản Java và cũng không phải các lệnh Gradle task.

## 2. Bảng so sánh: dependency nằm ở classpath nào?

Bảng sau mô tả **dependency được khai báo trong một module thư viện dùng java-library**, rồi được một module Java khác tham chiếu bằng **implementation project(':core')**.

| Cấu hình | Khi compile **mã chính của module khai báo** | Khi chạy **mã chính của module khai báo** | Trên **compileClasspath của module tiêu thụ** | Trên **runtimeClasspath của module tiêu thụ** | Khi compile/chạy test module khai báo |
| --- | --- | --- | --- | --- | --- |
| **implementation** | Có | Có | Không được xuất trực tiếp như API | Có | Có, qua classpath của mã chính |
| **api** | Có | Có | Có | Có | Có |
| **runtimeOnly** | Không | Có | Không | Có | Có khi chạy test, không phải khi compile test |
| **compileOnly** | Có | Không | Không | Không | Không tự đưa vào classpath test |
| **testImplementation** | Không | Không | Không | Không | Có, cho test compile và test runtime |

**Đọc đúng bảng:** Cột “không” nói về những gì *configuration này cung cấp theo hợp đồng*, không loại trừ trường hợp thư viện tình cờ có mặt nhờ một đường dependency khác. Gradle có **variant-aware dependency resolution**; đối với một project dùng java-library, consumer thường chọn **apiElements** lúc compile và **runtimeElements** lúc runtime. Vì vậy **implementation** của thư viện vẫn xuất hiện ở runtime của consumer, dù bị ẩn khỏi compile classpath của consumer.

Một cách ghi nhớ:

~~~text
                  module khai báo dependency                  module tiêu thụ thư viện
              compile main       runtime main               compile       runtime
api                ✓                  ✓                        ✓             ✓
implementation     ✓                  ✓                        —             ✓
compileOnly        ✓                  —                        —             —
runtimeOnly        —                  ✓                        —             ✓
testImplementation chỉ dành cho compile/run test nội bộ; không phát hành ra consumer
~~~

Dấu “—” nghĩa là không được configuration ấy cung cấp. Đây là sơ đồ phạm vi, không phải sơ đồ tất cả mối quan hệ dependency trong Gradle.

## 3. Phải áp dụng plugin phù hợp trước khi khai báo dependency

Một **build.gradle** của ứng dụng Spring Boot thường khai báo:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}
~~~

Trong module này, các cấu hình **implementation**, **runtimeOnly**, **compileOnly**, **testImplementation** có sẵn nhờ Java plugin. Nhưng **api không phải cấu hình mặc định của java plugin**. Cố viết **api '...'** trong một module chỉ dùng **java** có thể gây lỗi “Could not find method api()”.

Đối với **module thư viện Java** có public API được project khác sử dụng, dùng:

~~~groovy
plugins {
    id 'java-library'
}
~~~

**java-library mở rộng java plugin**, cung cấp thêm **api**, **compileOnlyApi** và các outgoing variant phục vụ consumer. Không cần áp dụng đồng thời cả **java** và **java-library**: áp dụng java-library đã bao gồm phần khả năng của java plugin.

Trong project nhiều module, mỗi module có thể dùng plugin khác nhau. Một module **:core** thường xuất JAR thư viện và dùng **java-library**; module **:app** chạy Spring Boot và dùng **java + org.springframework.boot**. Tránh áp dụng Spring Boot plugin cho mọi thư viện thuần chỉ vì chúng nằm trong cùng repository.

## 4. implementation: dependency cho code nội bộ của module

Ví dụ module :core dùng Google Guava bên trong một phương thức:

~~~groovy
dependencies {
    implementation 'com.google.guava:guava:33.3.1-jre'
}
~~~

Gradle thêm Guava và các dependency liên quan vào **compileClasspath** và **runtimeClasspath** của :core. Trong class Java của :core, ta có thể dùng **com.google.common.base.CharMatcher**.

Khi module :app phụ thuộc vào :core:

~~~groovy
dependencies {
    implementation project(':core')
}
~~~

thì **mã app có thể gọi các class public do core định nghĩa**; nhưng Guava khai báo bằng **implementation** trong core **không được xuất cho compiler của app như một phần API**. Nếu app muốn import trực tiếp Guava, app nên khai báo dependency Guava của chính nó hoặc nhận nó qua một API được thiết kế rõ ràng.

**Vì sao nên mặc định ưu tiên implementation?**

1. **Đóng gói đúng phạm vi**: những thư viện phụ trợ bên trong :core không tự trở thành cam kết API với người dùng :core.
2. **Giảm classpath compile của consumer**: compiler của app không phải nhìn thấy mọi chi tiết của core, thường cải thiện hiệu năng build.
3. **Giảm rebuild không cần thiết**: thay đổi implementation dependency không liên quan binary API của core có thể không buộc các module phụ thuộc compile lại.
4. **Dễ bảo trì**: có thể đổi thư viện bên trong core mà không bắt consumer phải sửa import chỉ vì đã lạm dụng thư viện truyền qua transitive dependency.

**Lưu ý:** “Ẩn khỏi compile classpath của consumer” **không có nghĩa** implementation dependency bị loại khỏi runtime. Nếu core dùng Guava lúc chạy, Guava vẫn phải có trong runtime graph của app.

## 5. api: dependency thuộc hợp đồng công khai của thư viện

Ví dụ :core công bố một phương thức public trả về **org.apache.commons.lang3.tuple.Pair**, một kiểu từ Apache Commons Lang:

~~~groovy
dependencies {
    api 'org.apache.commons:commons-lang3:3.14.0'
}
~~~

Đây là lựa chọn hợp lý vì **Pair là một phần chữ ký public**. Code của :app sẽ cần biết **Pair** để biên dịch các lời gọi hoặc khai báo biến kiểu Pair:

~~~java
Pair<String, String> result = LabelMaker.describe("  java  ");
~~~

Nếu :core khai báo Commons Lang bằng **implementation**, :core tự compile được nhưng Gradle **không cam kết** Commons Lang xuất hiện trên compile classpath của :app. Khai báo bằng **api** giúp consumer compile trực tiếp với kiểu public ấy.

**Khi nào dùng api?** Khi một dependency chứa kiểu tham gia **public/protected method return type, parameter, generic signature, superclass, implemented interface, public field** hoặc annotation public mà consumer phải nhìn thấy lúc compile. Gradle documentation gọi đây là phần **ABI — Application Binary Interface**.

**Khi nào không dùng api?** Khi dependency chỉ phục vụ thuật toán, logging, database adapter, mapper nội bộ hoặc các helper không xuất hiện trong public contract. Dùng implementation giữ ranh giới thư viện rõ ràng.

Phân biệt **api** trong Gradle với “API HTTP”: cấu hình **api** không tạo endpoint REST, không cấp quyền truy cập và không điều khiển Spring Security.

### Một trường hợp đặc biệt: compileOnlyApi

Plugin **java-library** còn có **compileOnlyApi**. Nó cho phép xuất kiểu cần cho consumer **lúc compile**, nhưng **không yêu cầu hiện diện tại runtime**. Dùng cho các type annotation hoặc API đặc thù có thể được cung cấp ở môi trường khác, sau khi đã xác minh contract runtime. Không nên chuyển bừa dependency cần thiết lúc chạy sang compileOnlyApi.

## 6. runtimeOnly: chỉ đưa dependency vào runtime

Ví dụ điển hình là **JDBC driver**. Ứng dụng Spring Boot viết code theo **java.sql**, **javax.sql** hoặc **JdbcTemplate**, trong khi implementation cụ thể của database driver được nạp khi kết nối:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
~~~

- **spring-boot-starter-jdbc** chứa những API/lớp ứng dụng cần để code với Spring JDBC, được khai báo bằng implementation.
- **com.h2database:h2** là driver/engine database dùng khi chạy; ví dụ thông thường không cần import trực tiếp class H2 lúc compile.
- Khi khởi động với H2 có mặt trên classpath và không cấu hình database bên ngoài, Spring Boot có thể tự cấu hình cơ sở dữ liệu H2 in-memory cho ứng dụng dùng JDBC.

**runtimeOnly không nằm trên compileClasspath**. Nếu mã nguồn main viết **import org.h2.Driver;**, compiler không tìm thấy lớp H2 qua runtimeOnly; hoặc bỏ import phụ thuộc implementation cụ thể, hoặc khai báo dependency theo đúng nhu cầu compile thực sự.

Với Spring Boot executable JAR, **bootJar** dùng runtime classpath để tập hợp các thư viện cần lúc chạy. Một dependency runtimeOnly thường được đưa vào BOOT-INF/lib của executable JAR nếu nó thuộc runtime graph; khi triển khai, vẫn cần kiểm tra artifact và policy packaging thực tế.

**Lưu ý về đổi driver:** Có thể dùng PostgreSQL driver ở runtime khi đã cấu hình URL, credentials và database thực tế; chỉ thay H2 thành PostgreSQL **không** bảo đảm app tự khởi động nếu không có database hoặc connection properties tương ứng. Vì vậy H2 phù hợp hơn cho bài thực hành độc lập.

RuntimeOnly cũng hữu ích với **implementation của SPI**, plugin hoặc logger backend được nạp trong runtime. Không dùng runtimeOnly cho các thư viện mà mã nguồn cần gọi trực tiếp type khi compile.

## 7. compileOnly: dependency chỉ dành cho biên dịch

**compileOnly** thêm các class vào main **compileClasspath**, nhưng không thêm vào main **runtimeClasspath** và không đưa dependency đến consumer như api. Thường dùng khi:

- Một API được runtime container/host cung cấp và **thật sự bảo đảm có mặt** ở môi trường chạy tương ứng.
- Một annotation chỉ hỗ trợ IDE/biên dịch và **không cần có mặt ở runtime**.
- Các annotation của Lombok cần để compiler nhận ký hiệu, nhưng bản thân Lombok không nên bị đưa vào thư viện ứng dụng lúc chạy.

Ví dụ với Lombok trong **build.gradle** (đoạn dependency minh họa):

~~~groovy
dependencies {
    compileOnly 'org.projectlombok:lombok:1.18.34'
    annotationProcessor 'org.projectlombok:lombok:1.18.34'
}
~~~

**Tại sao cần hai dòng?** compileOnly cung cấp các annotation như **@Getter**, **@RequiredArgsConstructor** cho compiler. Nhưng để Lombok **thực sự sinh code**, cần đưa processor vào configuration **annotationProcessor**, vì Gradle dùng processor path riêng. Chỉ khai báo Lombok trong compileOnly **không bảo đảm** code generation được bật.

Nếu **mã test** cũng viết Lombok annotation, có thể cần:

~~~groovy
dependencies {
    testCompileOnly 'org.projectlombok:lombok:1.18.34'
    testAnnotationProcessor 'org.projectlombok:lombok:1.18.34'
}
~~~

Đây là **cấu hình bổ sung cho test**, không thay thế hai dòng của main. CompileOnly của main không tự động chảy sang **testCompileClasspath**. Các annotation processor khác cũng có thể dùng annotationProcessor; không được đánh đồng **compileOnly** với **annotationProcessor**.

**Sai lầm nghiêm trọng:** Chuyển một thư viện thực sự được ứng dụng gọi ở runtime (ví dụ Jackson Databind, Spring Web hoặc driver khi mã app trực tiếp dùng class của driver) sang compileOnly có thể khiến app compile thành công nhưng nổ **NoClassDefFoundError** hoặc **ClassNotFoundException** khi chạy. CompileOnly chỉ phù hợp khi dependency không cần ở runtime *hoặc* môi trường khác bảo đảm cung cấp nó.

## 8. testImplementation: dependency dành cho test

Trong Java plugin, **src/main/java** là source của ứng dụng; **src/test/java** là source của kiểm thử. **testImplementation** cung cấp dependency cho cả **biên dịch test** và **chạy test**, không đưa dependency test vào main runtime hay artifact public.

Ví dụ Spring Boot:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Starter test mang các thư viện test mà Spring Boot quản lý, thường gồm JUnit Jupiter, AssertJ và công cụ kiểm thử Spring. Trong :core thuần Java không áp dụng Spring Boot dependency management, có thể khai báo phiên bản test cụ thể:

~~~groovy
dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.3'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.3'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**testRuntimeOnly** chỉ xuất hiện lúc chạy test; **testCompileOnly** chỉ xuất hiện lúc compile test. Các cấu hình này khác testImplementation, dù đều nằm trong phạm vi test.

Lưu ý cấu hình **testImplementation** của plugin Java nhận thêm những dependency phù hợp từ **implementation** của main: test code có thể gọi class ứng dụng và những thư viện dùng để triển khai ứng dụng. Nhưng dependency **testImplementation không chuyển ngược vào src/main/java**. Nếu đặt **import org.junit.jupiter.api.Test;** trong mã main rồi chỉ khai báo JUnit ở testImplementation, compileJava không tìm được type này theo contract.

## 9. Bài thực hành hoàn chỉnh: một thư viện core và một ứng dụng Spring Boot

Bài thực hành sau làm rõ **tất cả năm cấu hình** trong một repository Gradle Groovy DSL. Có hai module: **:core** xuất kiểu public thuộc Commons Lang và dùng Guava nội bộ; **:app** là ứng dụng Spring Boot tiêu thụ core, sử dụng H2 tại runtime và Spring Boot Starter Test lúc kiểm thử.

### 9.1. Cấu trúc thư mục

~~~text
scope-demo/
├── settings.gradle
├── core/
│   ├── build.gradle
│   └── src/
│       ├── main/java/com/example/core/LabelMaker.java
│       └── test/java/com/example/core/LabelMakerTest.java
└── app/
    ├── build.gradle
    └── src/main/java/com/example/app/DemoApplication.java
~~~

Dự án thực tế nên có Gradle Wrapper (**gradlew**, **gradlew.bat**, **gradle/wrapper/**) được tạo/cung cấp với bản Gradle phù hợp Spring Boot 3.3.x và JDK 17. Các lệnh dưới đây dùng wrapper; nếu tự tạo skeleton thủ công mà chưa có wrapper, cần tạo wrapper bằng một bản Gradle đã cài trước khi gọi **./gradlew**.

**settings.gradle** tại gốc:

~~~groovy
rootProject.name = 'scope-demo'
include 'core', 'app'
~~~

Không bắt buộc có build.gradle gốc trong ví dụ vì từng module tự khai báo plugin, repository và Java toolchain; trong dự án lớn có thể gom cấu hình chung bằng convention plugin.

### 9.2. File core/build.gradle: java-library, api, implementation, compileOnly, testImplementation

~~~groovy
plugins {
    id 'java-library'
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
    api 'org.apache.commons:commons-lang3:3.14.0'
    implementation 'com.google.guava:guava:33.3.1-jre'
    compileOnly 'org.jetbrains:annotations:24.1.0'

    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.3'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.3'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Vì **Commons Lang Pair** xuất hiện trong kiểu trả về public nên nó thuộc api. **Guava** chỉ được dùng bên trong hàm normalize nên thuộc implementation. **@NotNull** của JetBrains chỉ đánh dấu private helper phục vụ phân tích tĩnh lúc biên dịch nên được đặt trong compileOnly. **JUnit** chỉ phục vụ test.

**core/src/main/java/com/example/core/LabelMaker.java**:

~~~java
package com.example.core;

import com.google.common.base.CharMatcher;
import org.apache.commons.lang3.tuple.Pair;
import org.jetbrains.annotations.NotNull;

import java.util.Locale;

public final class LabelMaker {
    private LabelMaker() {
    }

    public static Pair<String, String> describe(String input) {
        return Pair.of("normalized", normalize(input));
    }

    @NotNull
    private static String normalize(String input) {
        return CharMatcher.whitespace()
                .trimFrom(input)
                .toUpperCase(Locale.ROOT);
    }
}
~~~

Đây là một **file Java hoàn chỉnh**. API public của LabelMaker xuất **Pair**. Phần triển khai bên trong dùng **CharMatcher** và một annotation biên dịch; consumer không cần import Guava hoặc JetBrains annotations để gọi **describe**.

**core/src/test/java/com/example/core/LabelMakerTest.java**:

~~~java
package com.example.core;

import org.apache.commons.lang3.tuple.Pair;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class LabelMakerTest {
    @Test
    void normalizesWhitespaceAndUppercase() {
        Pair<String, String> actual = LabelMaker.describe("  java  ");
        assertEquals(Pair.of("normalized", "JAVA"), actual);
    }
}
~~~

JUnit chỉ có trong testImplementation/testRuntimeClasspath; file LabelMaker.java không có JUnit import. Test thành công nếu Java 17, Gradle plugin và các dependency tải được.

### 9.3. File app/build.gradle: Spring Boot, implementation, runtimeOnly, testImplementation

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation project(':core')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**BOM từ Spring Boot** quản lý phiên bản cho các dependency được Spring Boot hỗ trợ, vì app áp dụng đồng thời Spring Boot plugin và **io.spring.dependency-management**. Do đó ví dụ có thể bỏ version ở **spring-boot-starter-web**, **spring-boot-starter-jdbc**, **h2** và **spring-boot-starter-test**. Không suy ra mọi dependency trên Maven Central đều có trong BOM; những thư viện khác có thể phải khai báo version như core đã làm.

**app/src/main/java/com/example/app/DemoApplication.java**:

~~~java
package com.example.app;

import com.example.core.LabelMaker;
import org.apache.commons.lang3.tuple.Pair;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @RestController
    static class LabelController {
        @GetMapping("/label")
        String label() {
            Pair<String, String> result = LabelMaker.describe("  java  ");
            return result.getRight();
        }
    }
}
~~~

Đây là file Java **hoàn chỉnh** cho ứng dụng Spring Boot. App trực tiếp dùng type **Pair** mặc dù app không khai báo Commons Lang, nhờ core đã xuất dependency ấy qua **api**. App gọi **LabelMaker.describe** được vì có **implementation project(':core')**. **Guava** không được xuất thành compile API của app nhưng có mặt ở runtime để core thực thi normalize.

Khi Spring Boot chạy, H2 driver nằm trên runtimeClasspath nên starter-jdbc có thể khởi tạo embedded datasource. Ứng dụng này không thực hiện câu lệnh SQL; H2 chỉ minh họa runtimeOnly và tránh yêu cầu database server ngoài.

### 9.4. Build, chạy ứng dụng và kiểm chứng output

Đứng tại thư mục gốc **scope-demo** (có Gradle Wrapper và JDK tương thích). Chạy:

~~~bash
./gradlew :core:test :app:bootJar
./gradlew :app:bootRun
~~~

- **:core:test** biên dịch core, biên dịch test và chạy JUnit của core.
- **:app:bootJar** biên dịch app và tạo executable Spring Boot JAR với dependency runtime cần thiết.
- **:app:bootRun** khởi động Spring Boot ở foreground; để tiến trình tiếp tục chạy trong terminal này.
- Trên Windows dùng **gradlew.bat** thay **./gradlew**.

Mở **terminal thứ hai**, gọi:

~~~bash
curl http://localhost:8080/label
~~~

**HTTP response body chính xác** của endpoint:

~~~text
JAVA
~~~

Lệnh curl cũng có thể hiển thị thông tin phụ tùy tùy chọn và môi trường, còn Spring Boot in log riêng vào terminal chạy bootRun. Response body của endpoint là một chuỗi **JAVA**, không có JSON object bao quanh.

**Điều kiện thực thi:** Gradle/Spring Boot tương thích với Java 17, download được plugin/dependency, cổng 8080 còn trống và có H2 trên runtime classpath. Ví dụ được thiết kế để build/run độc lập, nhưng không khẳng định log Gradle/Spring Boot sẽ giống nhau trên mọi máy.

### 9.5. Thay api bằng implementation để nhìn thấy ranh giới

Trong **core/build.gradle**, thử đổi tạm:

~~~groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}
~~~

Đây là **đoạn thay thế dòng api của Commons Lang**, không phải toàn bộ block dependencies của core. Khi app compile **DemoApplication.java** và tham chiếu **Pair**, compiler của app có thể báo lỗi **package org.apache.commons.lang3.tuple does not exist** hoặc **cannot access Pair**, vì core không còn xuất Commons Lang qua apiElements. Nếu một dependency khác tình cờ đã mang Commons Lang vào app compileClasspath, lỗi có thể bị che; khi đó hãy kiểm tra graph bằng lệnh ở mục 11.

Đổi dòng đó trở lại **api** để public contract của LabelMaker được công bố đúng. **Không đưa Guava sang api** chỉ để app có thể import Guava, vì LabelMaker không phơi bày Guava trong chữ ký public.

## 10. Cấu hình và BOM: phạm vi khác với phiên bản

Một **BOM (Bill of Materials)** cung cấp tập version/constraint được quản lý; **implementation/api/runtimeOnly/testImplementation** quyết định **vị trí sử dụng dependency trong classpath và cách dependency truyền sang consumer**. Hai khái niệm giải quyết hai bài toán khác nhau.

Với Spring Boot Gradle, có hai hướng phổ biến:

**Hướng A — io.spring.dependency-management:** Khi app áp dụng plugin Spring Boot và plugin **io.spring.dependency-management**, BOM **spring-boot-dependencies** cùng phiên bản Spring Boot plugin được import tự động. Ví dụ app ở trên dùng hướng này.

**Hướng B — Native Gradle platform:** Không áp dụng io.spring.dependency-management, mà khai báo BOM trực tiếp trong dependencies. Ví dụ **fragment trong build.gradle của ứng dụng**:

~~~groovy
dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')
    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')

    implementation 'org.springframework.boot:spring-boot-starter-web'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Dùng **platform** áp dụng các version constraints của BOM lên các classpath chứa platform. Đoạn trên là **cách thay thế quản lý phiên bản**, không yêu cầu dùng đồng thời với io.spring.dependency-management. Nếu dùng native platform, đảm bảo plugin Spring Boot vẫn được khai báo nếu muốn **bootJar/bootRun**.

**Điều thường bị hiểu sai:**

- Đặt dependency trong runtimeOnly **không tự chọn version mới nhất**.
- Đặt dependency trong api **không miễn trừ conflict version**.
- BOM **không tự chuyển** dependency từ testImplementation sang implementation.
- Gradle có thể chọn phiên bản khác version “đề nghị” trong BOM do các constraint/conflict khác của graph. **platform** và **enforcedPlatform** có ý nghĩa khác nhau; enforcedPlatform cưỡng bức phiên bản và có thể ảnh hưởng đến consumer, nên chỉ dùng có chủ đích.
- Với module **java-library**, nếu muốn public API của thư viện mang theo version constraints cho consumer, cần thiết kế cách đưa platform/constraints qua biến thể API thích hợp; một platform chỉ ở implementation không phải lúc nào cũng là cam kết API cần công bố.

## 11. Kiểm tra bằng các lệnh Gradle thay vì đoán classpath

Từ gốc scope-demo, các lệnh sau hiển thị **dependency graph đã resolve**:

~~~bash
./gradlew :core:dependencies --configuration compileClasspath
./gradlew :core:dependencies --configuration runtimeClasspath

./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath

./gradlew :core:dependencies --configuration testCompileClasspath
./gradlew :core:dependencies --configuration testRuntimeClasspath
~~~

Trong output của **:core:compileClasspath**, dự kiến thấy Commons Lang, Guava và JetBrains annotations. Trong **:core:runtimeClasspath**, Commons Lang và Guava có mặt, nhưng **JetBrains annotations** từ compileOnly không được đưa vào do cấu hình này.

Trong **:app:compileClasspath**, qua **project(':core')**, compiler có thể nhìn thấy Commons Lang là api dependency, nhưng **không được core xuất Guava như compile API**. Trong **:app:runtimeClasspath**, có core, các dependency cần lúc chạy gồm Guava, các Spring starter và H2. **JUnit của core** không được xuất thành runtime dependency của app.

Để hiểu **vì sao một thư viện cụ thể được chọn ở version đó**, chạy:

~~~bash
./gradlew :app:dependencyInsight --dependency commons-lang3 --configuration compileClasspath
./gradlew :app:dependencyInsight --dependency h2 --configuration runtimeClasspath
./gradlew :core:dependencyInsight --dependency guava --configuration runtimeClasspath
~~~

**dependencyInsight** cho biết đường dẫn dependency/phiên bản liên quan trong configuration đã chỉ định. Nếu Gradle báo không tìm thấy dependency, kiểm tra đúng tên project, tên artifact và classpath được hỏi; một dependency có thể chỉ tồn tại ở runtime nên sẽ không xuất hiện khi kiểm tra compileClasspath.

**Nên hỏi compileClasspath/runtimeClasspath**, vì **implementation**, **api**, **runtimeOnly** là những “bucket” để *khai báo dependency*, không phải luôn là configuration dùng trực tiếp để resolve file cho task. Các classpath mới thể hiện thực tế compiler và runtime nhìn thấy.

### Test và executable JAR

Có thể xác nhận task:

~~~bash
./gradlew :core:test
./gradlew :app:test
./gradlew :app:bootJar
~~~

Với **bootJar**, các dependency thuộc **runtimeClasspath** của app thường được đóng vào executable Boot JAR. Đừng mặc định **testImplementation** sẽ được đóng gói trong JAR chạy production. Có thể kiểm tra cấu trúc JAR theo quy ước **BOOT-INF/lib/**; việc có class/library cụ thể còn phụ thuộc dependency resolution, plugin và các exclusion được cấu hình.

## 12. Những lỗi phổ biến

**Lỗi 1 — Dùng api trong module chỉ khai báo plugin java.** **api** được Java Library plugin thêm vào. Nếu module thật sự là thư viện có consumer thì dùng **java-library**; nếu là ứng dụng Spring Boot không xuất kiểu public để module khác compile, **implementation** thường phù hợp hơn.

**Lỗi 2 — Chuyển tất cả dependencies sang api cho tiện.** Điều đó làm rò rỉ chi tiết nội bộ ra compile classpath của consumer và tăng mức liên kết giữa các module. Chỉ những dependency thuộc public ABI cần **api**.

**Lỗi 3 — Nghĩ implementation không xuất hiện khi consumer chạy.** Với java-library, implementation được ẩn khỏi compile API của consumer nhưng vẫn thuộc runtimeElements. Nếu mã core gọi Guava lúc chạy thì app phải có Guava trong runtime graph.

**Lỗi 4 — Để type của implementation trong chữ ký public.** Core public method trả về **Pair**, nhưng khai báo Commons Lang bằng implementation, làm consumer thiếu type khi compile. Đổi thành **api** hoặc thay thiết kế public API để không phơi bày thư viện đó.

**Lỗi 5 — Import class JDBC driver khi chỉ khai báo runtimeOnly.** runtimeOnly không có trên compileClasspath. Nếu code thực sự cần type từ dependency lúc compile thì không thể dùng runtimeOnly làm nguồn duy nhất.

**Lỗi 6 — Đưa Spring Boot starter/web vào compileOnly.** Các Spring class được ứng dụng dùng khi chạy sẽ thiếu ở runtime trừ khi môi trường khác cung cấp đầy đủ. Kết quả có thể là ClassNotFoundException/NoClassDefFoundError. Với ứng dụng Boot thông thường, dùng implementation cho starter.

**Lỗi 7 — Chỉ thêm Lombok bằng compileOnly.** Annotation processor cần được khai báo qua **annotationProcessor**; nếu dùng Lombok trong test, cân nhắc **testCompileOnly** và **testAnnotationProcessor** riêng.

**Lỗi 8 — Dùng testImplementation cho dependency của src/main/java.** Dependency test chỉ có trong test classpath; mã main không được compile nhờ dependency test. Chuyển đúng dependency vào implementation/api/compileOnly tùy mục đích thực tế.

**Lỗi 9 — Tưởng testImplementation đi vào executable JAR.** testImplementation không phải runtime dependency của main và không được chia sẻ cho consumer. Các công cụ test thường không nên có trong production artifact.

**Lỗi 10 — Version bị lệch rồi đổ lỗi cho implementation/runtimeOnly.** Configuration quyết định classpath; version do constraint, BOM, direct/transitive dependency và conflict resolution. Dùng **dependencies** và **dependencyInsight** để kiểm tra graph.

**Lỗi 11 — Tin rằng runtimeOnly driver bảo đảm database kết nối thành công.** Driver có mặt là một điều kiện; URL, credentials, network, quyền truy cập, schema và database server vẫn phải phù hợp.

**Lỗi 12 — Cố dùng cấu hình compile hoặc runtime cũ của Gradle.** Những cấu hình lịch sử đó đã bị loại bỏ trong Gradle 7.0 đối với Java Library plugin. Dùng các tên hiện hành và kiểm tra tài liệu đúng phiên bản Gradle của repository.

## 13. Cách chọn cấu hình trong thực tế

Khi thêm một dependency mới, trả lời lần lượt:

1. **Có cần type của nó để compile mã main không?** Nếu **không** nhưng cần khi chạy, dùng **runtimeOnly**. Nếu chỉ phục vụ test, xét testImplementation/testRuntimeOnly.
2. **Nếu cần compile mã main, có cần nó tại runtime không?** Nếu **không**, và bạn biết rõ vì sao môi trường khác cung cấp hoặc type chỉ phục vụ compile, dùng **compileOnly**; nếu là processor cần **annotationProcessor**.
3. **Nếu cần cả compile và runtime, module có cung cấp public API cho consumer không?** Nếu không hoặc dependency chỉ dùng nội bộ, dùng **implementation**.
4. **Nếu public API của thư viện thực sự dùng type của dependency**, module dùng **java-library** và khai báo bằng **api** (hoặc compileOnlyApi trong trường hợp đặc thù không cần runtime).
5. **Nếu chỉ có test dùng dependency**, đặt **testImplementation** và cấu hình riêng cho test runtime khi cần.
6. **Nếu đang dùng Spring Boot BOM**, giữ việc quản lý version nhất quán, rồi kiểm tra đúng classpath đã resolve.

| Tình huống | Lựa chọn phổ biến |
| --- | --- |
| Spring MVC/REST starter trong ứng dụng Boot | **implementation** |
| Thư viện xử lý chuỗi chỉ được core gọi nội bộ | **implementation** |
| Kiểu Pair/DTO từ thư viện ngoài xuất hiện trong public API của core | **api** (với java-library) |
| H2/PostgreSQL JDBC driver chỉ được nạp khi chạy | **runtimeOnly** |
| Lombok annotations trong main source | **compileOnly** + **annotationProcessor** |
| JUnit/Spring Boot test support trong src/test | **testImplementation** |
| Thư viện chỉ cần chạy test mà test source không import type | **testRuntimeOnly** |

## 14. Tài liệu chính thức

- [Gradle — Java Library Plugin: API/implementation separation và configurations](https://docs.gradle.org/current/userguide/java_library_plugin.html)
- [Gradle — Dependency Configurations](https://docs.gradle.org/current/userguide/dependency_configurations.html)
- [Gradle — Creating Dependency Configurations](https://docs.gradle.org/current/userguide/declaring_configurations.html)
- [Gradle — Building Java & JVM Projects](https://docs.gradle.org/current/userguide/building_java_projects.html)
- [Spring Boot Gradle Plugin — Managing Dependencies và BOM](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html)

**Kết luận:** **implementation** giữ dependency phục vụ compile/runtime bên trong module; **api** xuất dependency thuộc public ABI để consumer compile; **runtimeOnly** chỉ tham gia runtime; **compileOnly** chỉ hỗ trợ compile; **testImplementation** chỉ phục vụ test. Trong Spring Boot, chọn scope theo nhu cầu classpath trước, rồi dùng BOM/dependency constraints để quản lý version.
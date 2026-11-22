# Vai trò của Gradle trong chuỗi biên dịch, kiểm thử, đóng gói và phát hành

## 1. Mục tiêu bài học

Sau bài học, bạn có thể:

- Giải thích vì sao một dự án Java cần công cụ build và Gradle đảm nhiệm phần nào trong quy trình đưa mã nguồn thành sản phẩm có thể sử dụng.
- Phân biệt **biên dịch**, **kiểm thử**, **đóng gói**, **phát hành artifact** và **triển khai ứng dụng**.
- Đọc và chạy các task Gradle thông dụng; hiểu các task liên kết thành đồ thị phụ thuộc.
- Tạo một ứng dụng Java nhỏ, chạy unit test, tạo JAR, đóng gói bản phân phối và xuất bản artifact vào Maven Local.
- Nhận biết những lỗi thường gặp khi dùng Gradle trong máy cá nhân và CI/CD.

## 2. Gradle là gì và đứng ở đâu trong quy trình?

**Gradle** là công cụ tự động hóa build. Thay vì yêu cầu lập trình viên tự gọi trình biên dịch, gom thư viện, chạy từng bộ kiểm thử, tạo file phát hành và lặp lại các bước này trên máy chủ CI, Gradle mô tả công việc qua các **task** cùng quan hệ phụ thuộc của chúng và thực thi theo thứ tự phù hợp.

Gradle **điều phối** những công cụ chuyên trách: Java compiler của JDK biên dịch mã Java; test framework như JUnit cung cấp test; các plugin Gradle định nghĩa task đóng gói và xuất bản. Gradle không thay thế JDK, JUnit hay hạ tầng triển khai.

Một luồng phổ biến:

~~~text
Mã nguồn + cấu hình build + dependency
                 |
                 v
   Gradle xác định task và quan hệ phụ thuộc
                 |
                 v
       Biên dịch mã nguồn chính
                 |
                 v
    Biên dịch test -> chạy kiểm thử
                 |
                 v
       Đóng gói JAR / distribution
                 |
                 v
       Xuất bản artifact vào repository
                 |
                 v
       Pipeline triển khai đến môi trường chạy
~~~

Sơ đồ thể hiện thứ tự nghiệp vụ thường gặp. Trong một lần chạy thực tế, Gradle lập **task graph** dựa trên task được yêu cầu; một số bước có thể được bỏ qua vì không cần thiết, đã cập nhật hoặc lấy được từ cache. Gradle cũng có thể chạy độc lập bước đóng gói hoặc kiểm thử tùy lệnh, nên không phải lúc nào cũng thực hiện toàn bộ sơ đồ.

## 3. Năm chặng: đầu vào, trách nhiệm và kết quả

| Chặng | Gradle làm gì? | Kết quả hoặc bằng chứng |
| --- | --- | --- |
| **1. Chuẩn bị build** | Đọc cấu hình, áp dụng plugin, xác định task và giải quyết các dependency cần thiết. | Task graph, classpath, cấu hình build. |
| **2. Biên dịch** | Gọi công cụ biên dịch để chuyển mã nguồn thành bytecode và xử lý resource. | File class dưới thư mục build, resource đã xử lý. |
| **3. Kiểm thử** | Biên dịch test, chuẩn bị test runtime và chạy test bằng cơ chế của plugin/test framework. | Kết quả PASS/FAIL, báo cáo HTML/XML, mã thoát của build. |
| **4. Đóng gói** | Tập hợp đầu ra thành JAR, ZIP/TAR distribution hoặc định dạng khác theo plugin. | Artifact như JAR và gói phân phối trong build/. |
| **5. Phát hành** | Đưa artifact và metadata tới kho artifact được cấu hình thông qua publishing plugin/task. | Gói có tọa độ group/artifact/version trong repository. |

**Phát hành khác triển khai:** phát hành là làm cho một artifact có phiên bản sẵn sàng để hệ thống khác lấy về; triển khai là cài/chạy artifact trên máy chủ, container hoặc nền tảng đích. Gradle có thể được tích hợp vào pipeline triển khai, nhưng **build** thành công tự nó không đồng nghĩa ứng dụng đã được triển khai.

## 4. Gradle mô tả công việc bằng plugin, task và dependency

### 4.1. Những file bạn sẽ gặp

- **settings.gradle**: đặt tên root project, khai báo project con trong multi-project build và một số cấu hình giải quyết plugin/dependency.
- **build.gradle**: áp dụng plugin, khai báo dependencies, cấu hình Java/toolchain, task và publishing; đây là ví dụ dùng **Groovy DSL**. Dự án cũng có thể chọn **settings.gradle.kts** và **build.gradle.kts** với Kotlin DSL.
- **gradlew**, **gradlew.bat**, **gradle/wrapper/**: Gradle Wrapper, giúp cả nhóm và CI chạy cùng bản Gradle mà dự án chỉ định.
- **src/main/java**, **src/main/resources**: mã nguồn và tài nguyên chạy thật.
- **src/test/java**, **src/test/resources**: mã và tài nguyên kiểm thử.
- **build/**: thư mục đầu ra được tạo lại từ build; thông thường không commit vào Git.

### 4.2. Plugin cung cấp công việc

Với dự án Java:

- **java** cung cấp cơ chế biên dịch, kiểm thử và tạo JAR.
- **application** cấu hình điểm vào main, thêm task chạy ứng dụng và đóng gói bản phân phối có script khởi động. Plugin này cũng áp dụng Java plugin.
- **maven-publish** cho phép công bố artifact và metadata theo định dạng Maven.

Gradle có ba giai đoạn chính: **initialization** (xác định các project tham gia), **configuration** (thiết lập project/task) và **execution** (chạy các task được chọn). Đây là các giai đoạn của một lần build, **khác** với năm chặng nghiệp vụ ở mục 3.

### 4.3. Task graph và các lệnh thường dùng

| Lệnh/task | Ý nghĩa |
| --- | --- |
| **compileJava** | Biên dịch mã nguồn Java chính. |
| **compileTestJava** | Biên dịch mã test, phụ thuộc vào đầu ra/cấu hình cần thiết. |
| **test** | Chạy test; tự yêu cầu những bước biên dịch liên quan. |
| **jar** | Tạo JAR từ đầu ra của source set chính. |
| **assemble** | Tập hợp các artifact của dự án; với application plugin thường gồm gói phân phối. |
| **check** | Chạy những tác vụ kiểm tra được plugin nối vào lifecycle; với Java plugin có test. |
| **build** | Lifecycle task phụ thuộc vào **assemble** và **check**. |
| **run** | Chạy main class qua application plugin. |
| **distZip** / **distTar** | Tạo ZIP/TAR phân phối ứng dụng cùng thư viện runtime và script. |
| **publishToMavenLocal** | Đưa Maven publication vào kho Maven trên máy hiện tại. |
| **clean** | Xóa đầu ra build do Gradle tạo, để xây dựng lại từ đầu. |

Ví dụ, yêu cầu **build** khiến Gradle tự xét các bước cần thiết như **compileJava**, **jar**, **compileTestJava**, **test**, **distZip** và các task tổng hợp. Trình tự chính xác phụ thuộc cấu hình, plugin, phiên bản và task graph; không nên hiểu bảng trên như một danh sách luôn chạy tuần tự.

## 5. Ví dụ thực hành: Java 17+, JUnit và Gradle

Ví dụ sau là một dự án **độc lập, có thể chạy được**. Cần cài JDK phù hợp với Gradle được chọn, mạng để tải dependency lần đầu và bản Gradle cài sẵn **một lần** để tạo Wrapper. Những lần sau dùng Wrapper.

### 5.1. Cấu trúc thư mục

~~~text
gradle-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   └── java/com/example/gradle/GreetingApp.java
    └── test/
        └── java/com/example/gradle/GreetingAppTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'gradle-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'application'
    id 'maven-publish'
}

group = 'com.example.learning'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'com.example.gradle.GreetingApp'
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.named('test') {
    useJUnitPlatform()
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }
}
~~~

Giải thích những phần cần hiểu:

1. **plugins** tạo các task và convention tương ứng.
2. **group** và **version**, kết hợp tên project **gradle-demo**, tạo tọa độ artifact **com.example.learning:gradle-demo:1.0.0**.
3. **repositories { mavenCentral() }** chỉ vị trí Gradle tìm dependency.
4. **java.toolchain** yêu cầu trình biên dịch Java 17, giúp xác định JDK dùng biên dịch. Môi trường cần có toolchain phù hợp hoặc đã cấu hình cơ chế cung cấp toolchain.
5. **testImplementation** thêm JUnit cho test; **testRuntimeOnly** cung cấp launcher khi chạy test; **useJUnitPlatform()** chọn JUnit Platform.
6. **mainClass** cho task **run** và script chạy trong distribution biết điểm vào.
7. **MavenPublication** lấy Java component, dùng để tạo artifact và metadata khi publish.

**src/main/java/com/example/gradle/GreetingApp.java**

~~~java
package com.example.gradle;

public final class GreetingApp {
    private GreetingApp() {
    }

    public static String greeting(String name) {
        if (name == null || name.isBlank()) {
            return "Xin chào, khách!";
        }
        return "Xin chào, " + name.strip() + "!";
    }

    public static void main(String[] args) {
        String name = args.length > 0 ? args[0] : "Gradle";
        System.out.println(greeting(name));
    }
}
~~~

Phương thức **greeting** chứa logic có thể kiểm thử riêng. **main** chỉ nhận đối số và in kết quả. **String.isBlank()** và **String.strip()** đều được Java 17 hỗ trợ.

**src/test/java/com/example/gradle/GreetingAppTest.java**

~~~java
package com.example.gradle;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingAppTest {
    @Test
    void greetsNamedUser() {
        assertEquals("Xin chào, Gradle!", GreetingApp.greeting("Gradle"));
    }

    @Test
    void greetsGuestWhenBlank() {
        assertEquals("Xin chào, khách!", GreetingApp.greeting("  "));
    }
}
~~~

Hai unit test lần lượt kiểm tra nhánh tên hợp lệ và nhánh tên trắng. Test dựa vào JUnit, nhưng **logic nghiệp vụ không phụ thuộc Gradle**; Gradle đảm nhiệm biên dịch, nạp thư viện test và khởi chạy test.

### 5.2. Tạo và sử dụng Wrapper

Tại thư mục **gradle-demo**, chạy lệnh sau nếu máy có Gradle CLI:

~~~bash
gradle wrapper
~~~

Lệnh tạo **gradlew**, **gradlew.bat** và file trong **gradle/wrapper/**. Commit những file Wrapper cần thiết để các máy khác và CI dùng cùng bản Gradle đã được khai báo trong **gradle-wrapper.properties**. Khi thay đổi bản Gradle, cập nhật Wrapper có chủ đích và kiểm tra khả năng tương thích với JDK/plugin.

Lệnh minh họa trên macOS/Linux dùng **./gradlew**; trên Windows PowerShell dùng **.\gradlew.bat** rồi cùng tên task/đối số. Ví dụ:

~~~powershell
.\gradlew.bat test
~~~

### 5.3. Chạy từng chặng và quan sát đầu ra

**Bước 1 — Xem các task:**

~~~bash
./gradlew tasks
./gradlew build --dry-run
~~~

**tasks** liệt kê các task có thể gọi; **--dry-run** cho biết các task dự kiến được thực thi mà không chạy phần hành động của task. Dùng để xem quan hệ phụ thuộc trước khi chạy build thật.

**Bước 2 — Biên dịch và kiểm thử:**

~~~bash
./gradlew compileJava
./gradlew test
~~~

Nếu hai test đều đạt, Gradle báo **BUILD SUCCESSFUL**. Kiểm tra báo cáo HTML tại **build/reports/tests/test/index.html** và XML tại **build/test-results/test/**. Nếu một assertion sai, task test thất bại và quy trình build phụ thuộc vào test cũng thất bại.

**Bước 3 — Chạy ứng dụng:**

~~~bash
./gradlew run --args="Linh"
~~~

Dòng stdout do ứng dụng in ra là:

~~~text
Xin chào, Linh!
~~~

Gradle còn in các dòng về task và kết quả build; chúng thay đổi theo phiên bản và trạng thái cache, nên không phải là stdout cố định của ứng dụng.

**Bước 4 — Build toàn bộ và tìm gói:**

~~~bash
./gradlew clean build
~~~

Với cấu hình trên, đầu ra đáng chú ý gồm:

~~~text
build/libs/gradle-demo-1.0.0.jar
build/distributions/gradle-demo-1.0.0.zip
build/distributions/gradle-demo-1.0.0.tar
build/reports/tests/test/index.html
~~~

- **JAR** chứa class/resource chính của project. JAR thông thường do Java plugin tạo **không tự động** là executable fat JAR, không tự mang mọi thư viện runtime và không mặc định có manifest Main-Class để chạy bằng **java -jar**.
- **ZIP/TAR distribution** do application plugin tạo có JAR, thư viện runtime và script khởi động cho Unix/Windows; dùng khi muốn phân phối ứng dụng CLI.
- **test report** là bằng chứng kiểm thử; chỉ nên phát hành bản build sau khi cổng chất lượng yêu cầu đã qua.

Để đóng gói distribution riêng hoặc tạo thư mục chạy giải nén sẵn:

~~~bash
./gradlew distZip
./gradlew installDist
~~~

Sau **installDist**, có thể chạy script trong **build/install/gradle-demo/bin/**. Việc tạo distribution không đồng nghĩa ứng dụng đã chạy trên production.

**Bước 5 — Xuất bản vào Maven Local:**

~~~bash
./gradlew publishToMavenLocal
~~~

Gradle tạo Maven publication dựa trên Java component và đưa artifact cùng POM/metadata vào kho Maven cục bộ (thường dưới **~/.m2/repository/com/example/learning/gradle-demo/1.0.0/**). Bước này cho phép dự án khác trên cùng máy dùng artifact như một dependency, nhưng **không xuất bản ra Internet**.

Để publish vào Nexus, Artifactory, GitHub Packages hoặc Maven-compatible repository khác, cần khai báo đích trong **publishing.repositories**, thiết lập thông tin xác thực phù hợp và chạy task publish tương ứng. **publish** chỉ gửi tới các repository đã cấu hình; **publishToMavenLocal** là đường riêng. Không đưa token hay mật khẩu vào file build được commit.

## 6. Gradle giải quyết dependency và tối ưu tốc độ như thế nào?

### 6.1. Dependency và classpath

Thay vì tải JAR thủ công, Gradle giải quyết **tọa độ phụ thuộc + phiên bản + quan hệ phụ thuộc bắc cầu** từ repository. Các cấu hình thông dụng:

- **implementation**: thư viện dùng trong mã chính và thường cần ở runtime; không tự động phơi toàn bộ dependency như API công khai của thư viện.
- **compileOnly**: có mặt khi biên dịch nhưng không được tự động đưa vào runtime.
- **runtimeOnly**: chỉ cần lúc chạy.
- **testImplementation**: dùng để biên dịch và chạy test.
- **testRuntimeOnly**: chỉ cần ở runtime của test.

Gradle xây dựng các classpath tương ứng, không đơn thuần chép mọi JAR vào một thư mục. Có thể kiểm tra dependency đã chọn bằng:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency junit-jupiter --configuration testRuntimeClasspath
~~~

Lệnh thứ hai hữu ích khi xuất hiện xung đột phiên bản hoặc muốn biết vì sao một dependency có mặt.

### 6.2. Incremental build, up-to-date và cache

Khi đầu vào và đầu ra của task cho thấy không có việc mới cần làm, Gradle có thể đánh dấu task **UP-TO-DATE**. Nếu đã cấu hình build cache và có kết quả phù hợp, Gradle có thể dùng **FROM-CACHE**. Những nhãn này khác với **NO-SOURCE**, tức task không có nguồn để xử lý.

Ba loại dữ liệu thường bị nhầm lẫn:

1. **Dependency cache** lưu các thư viện/metadata đã tải để giảm số lần tải từ repository.
2. **Up-to-date checks** tránh chạy lại task nếu đầu vào/đầu ra vẫn phù hợp.
3. **Build cache** tái sử dụng đầu ra task đủ điều kiện từ các lần build trước hoặc từ cache dùng chung.

Tăng tốc không làm biến mất trách nhiệm đảm bảo tính đúng đắn của task. Task custom phải khai báo input/output hợp lý để cơ chế cache hoạt động đáng tin. Dùng phiên bản dependency cố định, Gradle Wrapper, kiểm soát toolchain và cấu hình CI thống nhất sẽ giúp build dễ tái lập hơn; riêng Wrapper chưa bảo đảm build hoàn toàn reproducible.

## 7. Từ máy lập trình viên đến CI/CD và phát hành

Một pipeline phổ biến có các cổng:

~~~text
Checkout source
    |
    v
Cài/khởi tạo JDK phù hợp + chạy Gradle Wrapper
    |
    v
./gradlew clean build
    |
    +--> Biên dịch thành công?
    +--> Unit/integration test và các quality check bắt buộc đạt?
    |
    v
Lưu artifact + báo cáo test của build đã đạt
    |
    v
Gắn phiên bản / phê duyệt phát hành
    |
    v
Publish artifact tới repository bằng quyền CI được cấp
    |
    v
Pipeline triển khai lấy đúng artifact đã phát hành
    |
    v
Smoke test / theo dõi / rollback nếu cần
~~~

**Gradle xử lý phần build và publishing được cấu hình**. GitHub Actions, GitLab CI, Jenkins hay một hệ thống tương tự quyết định **khi nào** chạy các lệnh, cất giữ artifact, cấp credential, chặn phát hành khi kiểm thử không đạt và điều phối triển khai.

Các nguyên tắc thực hành:

- Chạy bằng **Wrapper** trong local lẫn CI để hạn chế khác biệt phiên bản Gradle.
- Dùng cùng target JDK/toolchain và phiên bản dependency đã quản lý.
- Chọn rõ quality gate: **test** chỉ chạy test; **build** đi qua **assemble** và **check** trong lifecycle thông thường. Các quality plugin có thể nối thêm lint, static analysis hoặc integration test.
- Đặt version artifact có ý nghĩa, gắn commit/tag nguồn và lưu báo cáo build; nếu có thể, publish **một artifact đã kiểm thử** qua các môi trường thay vì build lại tùy ý ở mỗi môi trường.
- Cấp quyền publish/deploy trong CI qua secret manager hoặc biến môi trường an toàn; không commit credential.
- Tách **build thành công**, **publish thành công** và **deploy thành công** thành ba trạng thái có thể quan sát riêng. Các bước sau có thể thất bại dù bước trước đã đạt.

## 8. Các nhầm lẫn và lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| **Task 'test' not found** | Chưa áp dụng plugin cung cấp test, đang ở nhầm project hoặc dùng sai tên task. | Kiểm tra **plugins**, chạy **./gradlew tasks --all** và xác định đúng project. |
| **No matching toolchains found** | Không có JDK đáp ứng yêu cầu toolchain, hoặc chưa cấu hình tải JDK tự động. | Cài JDK phù hợp, kiểm tra **java -version** và cấu hình toolchain. |
| **Could not resolve dependency** | Sai tọa độ, thiếu repository, mất mạng, vấn đề proxy hoặc credential. | Kiểm tra **repositories**, GAV/version, kết nối mạng và quyền truy cập repository. |
| **Test thất bại dù compileJava thành công** | Compile chỉ kiểm tra cú pháp/kiểu; assertion hoặc setup test có lỗi. | Đọc test report và stack trace; sửa nguyên nhân rồi chạy lại **test**. |
| **java -jar báo thiếu Main-Class hoặc ClassNotFoundException** | JAR thường không có manifest khởi động hoặc thiếu dependency runtime. | Chạy bằng **run** hoặc bản **application distribution**; chỉ dùng executable/fat JAR khi đã cấu hình đúng. |
| **Chạy build lần hai thấy UP-TO-DATE** | Không có thay đổi liên quan tới đầu vào/đầu ra của task. | Đây thường là tối ưu hợp lệ; dùng **clean build** khi cần xây lại có chủ đích. |
| **publish không đưa artifact lên server** | Chưa cấu hình publishing repository, publication hoặc credential. | Kiểm tra **publishing.publications**, **publishing.repositories** và task publish cụ thể. |
| **Chạy được local nhưng hỏng trên CI** | Khác Gradle/JDK, biến môi trường, hệ điều hành, repository hoặc cấu hình test. | Dùng Wrapper, pin toolchain, kiểm tra log và quy trình CI có thể tái lập. |

**Lưu ý về lệnh clean:** không cần chạy **clean** trước mọi build. Việc xóa đầu ra build làm mất lợi ích của up-to-date checks cho những đầu ra đó; dùng khi cần xác minh khả năng xây dựng lại hoặc xử lý vấn đề đầu ra cũ.

## 9. Tự kiểm tra kiến thức

1. Vì sao **./gradlew build** có thể chạy **test** dù người dùng không gọi trực tiếp task test?
2. Sự khác nhau giữa file **build/libs/gradle-demo-1.0.0.jar** và **build/distributions/gradle-demo-1.0.0.zip** là gì?
3. Nếu **compileJava** thành công nhưng unit test thất bại, pipeline có nên publish bản release đó không? Vì sao?
4. **publishToMavenLocal** có làm cho artifact xuất hiện trên Maven Central hoặc server production không?
5. Những yếu tố nào ngoài Gradle Wrapper cần được kiểm soát để build nhất quán trên máy cá nhân và CI?

**Đáp án gợi ý:** (1) task **build** phụ thuộc **check**, còn Java plugin nối **test** vào **check**; (2) JAR chính khác distribution có thư viện runtime và script; (3) không, khi test là quality gate bắt buộc; (4) không, chỉ vào Maven Local; (5) ít nhất là JDK/toolchain, dependency/repository, môi trường, cấu hình và input build.

## 10. Kết luận

Gradle là **bộ điều phối chuỗi build**: nhận source và cấu hình, chọn và sắp xếp task, giải quyết dependency, dùng JDK để biên dịch, dùng test framework để kiểm thử, tạo artifact qua plugin rồi publish khi được yêu cầu. Hiểu ranh giới giữa **compile → test → package → publish → deploy** giúp bạn đọc log đúng, chọn lệnh phù hợp, đặt quality gate trong CI/CD và không nhầm một build thành công với một bản phát hành hoặc triển khai thành công.

### Tài liệu tham khảo chính thức

- [Gradle — Task Basics](https://docs.gradle.org/current/userguide/task_basics.html)
- [Gradle — Base Plugin và lifecycle tasks](https://docs.gradle.org/current/userguide/base_plugin.html)
- [Gradle — Java/JVM Projects](https://docs.gradle.org/current/userguide/building_java_projects.html)
- [Gradle — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html)
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html)

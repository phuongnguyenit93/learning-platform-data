# Gradle là gì và những vấn đề tự động hóa build cần giải quyết

**Chủ đề:** Build Tool Gradle  
**Mục:** Tổng quan Gradle

## Mục tiêu học tập

Sau bài này, bạn có thể: (1) giải thích “build” bao gồm những công việc nào ngoài biên dịch; (2) nhận diện các vấn đề phát sinh khi build thủ công; (3) mô tả cách Gradle dùng project, plugin, dependency và task để giải quyết các vấn đề đó; (4) chạy một dự án Java 17 có kiểm thử bằng Gradle Wrapper; (5) phân biệt tính tự động, tốc độ build và khả năng tái lập kết quả.

## 1. Build thực chất là gì?

**Build** là quá trình biến mã nguồn cùng cấu hình, tài nguyên và thư viện phụ thuộc thành kết quả có thể kiểm tra, chạy hoặc phát hành. Với ứng dụng Java, một pipeline build điển hình gồm:

1. Xác định phiên bản Java, công cụ build, kho thư viện và cấu hình dự án.
2. Lấy các thư viện cần thiết (dependency resolution).
3. Biên dịch Java thành bytecode và xử lý tài nguyên.
4. Biên dịch và chạy unit test, kiểm tra chất lượng theo quy ước của nhóm.
5. Đóng gói thành JAR hoặc một bản phân phối; tùy dự án có thể tạo thêm báo cáo, tài liệu hay artifact để phát hành.

**Biên dịch chỉ là một công đoạn của build.** Ví dụ, lệnh javac có thể biên dịch một tệp Java độc lập, nhưng không tự quản lý hàng chục thư viện, biết test nào phải chạy, tạo bản phân phối hay bảo đảm cả nhóm sử dụng cùng quy trình.

Hãy hình dung một ứng dụng có 20 lập trình viên, nhiều thư viện và nhiều module. Nếu mỗi người tự gõ các lệnh để tải JAR, biên dịch, chạy test, copy file và đóng gói, quy trình sẽ vừa dài vừa dễ khác nhau. Một lỗi nhỏ như quên cập nhật classpath có thể khiến “chạy trên máy tôi” nhưng thất bại trên CI.

## 2. Những vấn đề tự động hóa build cần giải quyết

| Vấn đề khi làm thủ công | Hậu quả điển hình | Điều cần có trong hệ thống build |
|---|---|---|
| **Nhiều thao tác phải nhớ** | Quên bước test, tạo JAR hoặc copy resource | Quy trình chuẩn được mô tả bằng cấu hình và task, gọi lại bằng một lệnh |
| **Thứ tự công việc phức tạp** | Chạy test trước khi biên dịch, tạo artifact khi đầu vào chưa sẵn sàng | Quan hệ phụ thuộc giữa các task và lịch thực thi phù hợp |
| **Thư viện phụ thuộc chồng chéo** | Thiếu JAR, xung đột phiên bản, classpath khác nhau | Khai báo dependency, repository, phạm vi sử dụng và cách resolve nhất quán |
| **Môi trường không đồng nhất** | Máy A dùng Gradle/JDK khác máy B; CI cho kết quả khác | Wrapper để cố định bản Gradle, Java toolchain và quy ước cấu hình |
| **Build lặp lại quá tốn thời gian** | Sửa một file vẫn chạy toàn bộ công việc | Tránh chạy task không đổi, biên dịch tăng dần, tái sử dụng output hợp lệ |
| **Dự án lớn nhiều module** | Mỗi module có script riêng, khó xác định module nào phải build trước | Cấu trúc đa project và quan hệ phụ thuộc giữa các project |
| **Thiếu cổng kiểm soát chất lượng** | Mã chưa qua test vẫn được đóng gói/giao đi | Tích hợp kiểm thử và kiểm tra vào pipeline tự động |
| **Khó chạy lại lỗi trên CI** | Không biết chính xác lệnh/cấu hình tạo ra bản build | Cấu hình và script được quản lý bằng version control, log và artifact rõ ràng |

Có ba đích cần phân biệt:

- **Tự động hóa:** thay chuỗi bước thủ công bằng quy trình có thể gọi lại.
- **Tính tái lập (reproducibility):** cố gắng giữ đầu vào, phiên bản và môi trường nhất quán để cùng trạng thái mã tạo ra kết quả tương đương. Chỉ dùng Gradle không tự bảo đảm mọi build có byte-for-byte giống nhau.
- **Hiệu năng:** giảm công việc thừa và tận dụng cache khi các điều kiện đầu vào/đầu ra cho phép. Nhanh hơn không có nghĩa bỏ qua test quan trọng.

## 3. Gradle là gì?

**Gradle là công cụ tự động hóa build** (build automation tool). Bạn mô tả cấu trúc dự án, plugin, dependency và các công việc cần làm; Gradle lập kế hoạch và thực thi những công việc cần thiết. Gradle được dùng phổ biến cho Java, Kotlin, Android và có thể mở rộng sang các loại dự án khác qua plugin.

Gradle **không phải** ngôn ngữ Java, không phải Spring Boot, cũng không phải trình biên dịch Java. Nó thường điều phối trình biên dịch, framework kiểm thử, công cụ đóng gói và các plugin phù hợp. Gradle chạy trên JVM; **JDK chạy chính Gradle** và **JDK dùng để biên dịch/chạy mã ứng dụng** có thể được lựa chọn riêng bằng Java toolchain.

Những thành phần đầu tiên cần nắm:

| Khái niệm | Vai trò |
|---|---|
| **Build** | Toàn bộ công việc và cấu hình để tạo kết quả từ một hoặc nhiều project |
| **Project** | Một đơn vị cấu hình trong build; có thể là ứng dụng, thư viện hoặc module con |
| **settings.gradle / settings.gradle.kts** | Đặt tên build và khai báo những project tham gia |
| **build.gradle / build.gradle.kts** | Script cấu hình plugin, dependency, task và quy tắc của một project |
| **Plugin** | Bổ sung khả năng, task và quy ước, ví dụ plugin java hoặc application |
| **Task** | Đơn vị công việc có thể được yêu cầu và kết nối bằng quan hệ phụ thuộc |
| **Repository** | Nơi Gradle tìm module/phụ thuộc đã khai báo, ví dụ Maven Central |
| **Dependency** | Thư viện hoặc project khác mà mã cần lúc biên dịch, chạy hay kiểm thử |
| **Gradle Wrapper** | Bộ script gradlew/gradlew.bat và cấu hình dùng bản Gradle được dự án khai báo |

Gradle hỗ trợ **Groovy DSL** (tệp .gradle) và **Kotlin DSL** (tệp .gradle.kts). Cả hai đều cấu hình cùng mô hình Gradle; cú pháp khác nhau, không cần dùng cả hai cho một ví dụ.

**Phân biệt hai dạng “phụ thuộc”:** dependency thư viện như JUnit là đầu vào của chương trình hoặc test; dependency giữa các task là quan hệ công việc, ví dụ task test cần các lớp đã biên dịch. Khai báo một dependency thư viện không đồng nghĩa tự tạo một task kiểm thử: plugin và cấu hình kiểm thử mới đảm nhận việc đó.

## 4. Gradle lập kế hoạch build như thế nào?

### 4.1. Task và đồ thị phụ thuộc

Mỗi task có mục đích, ví dụ compileJava, test, jar, run hoặc clean. Plugin application áp dụng cả plugin java và cung cấp task run; plugin Java cung cấp các bước biên dịch/kiểm thử cơ bản. Khi yêu cầu một task, Gradle xác định các công việc phụ thuộc cần thực hiện trước.

Quan hệ tổng quát, đã giản lược:

~~~text
Mã Java ──> compileJava ──> classes ──> jar ──> assemble ──┐
                                │                         │
                                v                         build
                         compileTestJava                   ^
                                │                         │
                                v                         │
                               test ──────────> check ──────────┘
~~~

Sơ đồ minh họa các nhánh chính; danh sách và thứ tự task thực tế phụ thuộc plugin, cấu hình và Gradle version. Quan hệ task hình thành **đồ thị có hướng không chu trình (DAG)**. Gradle dựa vào DAG để tránh thiếu bước và có thể chạy song song những việc độc lập khi được phép.

### 4.2. Ba giai đoạn build

1. **Initialization:** đọc settings, xác định root project, subproject và included build.
2. **Configuration:** đánh giá cấu hình liên quan, đăng ký/cấu hình task và thiết lập đồ thị công việc sẽ chạy.
3. **Execution:** thực thi những task được chọn và các dependency cần thiết; kiểm tra trạng thái đầu vào/đầu ra để quyết định task nào có thể bỏ qua hoặc tái sử dụng kết quả.

Ví dụ, yêu cầu build không có nghĩa Gradle luôn chạy lại toàn bộ javac và test từ đầu. Khi đầu vào không đổi, task hỗ trợ theo dõi input/output có thể hiện trạng thái **UP-TO-DATE**. **Build cache** là cơ chế khác: tái sử dụng output đã lưu cho cùng đầu vào đủ điều kiện, có thể ở máy khác nếu cấu hình remote cache. **Configuration cache** lại lưu trạng thái cấu hình/task graph để giảm thời gian cấu hình trong các lần chạy phù hợp. Ba cơ chế có mục tiêu liên quan nhưng không giống nhau; không phải task hay plugin nào cũng tương thích với mọi chế độ cache.

## 5. Thực hành: một ứng dụng Java 17 có unit test

Ví dụ dưới dùng **Groovy DSL** và một ứng dụng console nhỏ. Bạn sẽ thấy Gradle quản lý thư viện JUnit, biên dịch, chạy test, chạy chương trình và đóng gói từ một cấu hình chung.

### 5.1. Cấu trúc thư mục

Tạo thư mục dự án gradle-hello với các tệp sau:

~~~text
gradle-hello/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/org/example/HelloGradle.java
    └── test/java/org/example/HelloGradleTest.java
~~~

Các tệp Wrapper (gradlew, gradlew.bat, gradle/wrapper/...) sẽ xuất hiện sau bước tạo Wrapper. Dùng JDK 17 tương thích và một bản Gradle hỗ trợ JDK/môi trường đó; khi tạo Wrapper lần đầu, máy cần có lệnh gradle hoạt động hoặc khởi tạo dự án bằng công cụ có tạo Wrapper sẵn.

**settings.gradle**

~~~groovy
rootProject.name = 'gradle-hello'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.10.2'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'org.example.HelloGradle'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Ý nghĩa từng phần:

- **application** bổ sung cách chạy ứng dụng qua task run và các task đóng gói; nó cũng áp dụng plugin java.
- **mavenCentral()** khai báo kho tìm dependency. JUnit chỉ dành cho test qua **testImplementation**; launcher cần cho việc chạy JUnit Platform.
- **java.toolchain** yêu cầu compiler/runtime Java 17 phù hợp cho các task Java mà plugin quản lý. Nếu không có JDK phù hợp và chưa cấu hình nguồn cấp toolchain, build có thể báo thiếu JDK.
- **mainClass** chỉ ra điểm vào ứng dụng; **useJUnitPlatform()** yêu cầu Gradle chạy test theo JUnit Platform.
- Phiên bản JUnit ở đây được khai báo cố định để ví dụ có đầu vào rõ ràng. Khi áp dụng thực tế, nhóm cần có chính sách cập nhật và kiểm tra các phiên bản thư viện.

**src/main/java/org/example/HelloGradle.java**

~~~java
package org.example;

public final class HelloGradle {
    private HelloGradle() {
    }

    public static String greeting(String name) {
        return "Xin chào, " + name + "!";
    }

    public static void main(String[] args) {
        System.out.println(greeting("Gradle"));
    }
}
~~~

**src/test/java/org/example/HelloGradleTest.java**

~~~java
package org.example;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class HelloGradleTest {
    @Test
    void greetingIncludesName() {
        assertEquals("Xin chào, Gradle!", HelloGradle.greeting("Gradle"));
    }
}
~~~

Bốn tệp Java/Groovy trên có vai trò tách bạch: settings xác định dự án; build script nêu cách build; mã sản phẩm chỉ chứa logic ứng dụng; test xác nhận đầu ra. JUnit được Gradle tải và đưa vào classpath test, nên bạn không phải tự tìm JAR rồi gõ classpath bằng tay.

### 5.2. Tạo Wrapper và chạy

Trong thư mục gốc dự án, chạy **một lần** bằng Gradle đã cài để tạo Wrapper:

~~~bash
gradle :wrapper
~~~

Sau đó lưu các tệp Wrapper vào Git cùng source và build script. Các lần tiếp theo, dùng **Wrapper của dự án**, ví dụ trên macOS/Linux:

~~~bash
./gradlew tasks
./gradlew test
./gradlew run
./gradlew build
~~~

Trên Windows PowerShell, những lệnh tương đương bắt đầu bằng:

~~~powershell
.\gradlew.bat tasks
.\gradlew.bat test
.\gradlew.bat run
.\gradlew.bat build
~~~

**Dòng do chương trình Java in ra khi chạy task run** là:

~~~text
Xin chào, Gradle!
~~~

Gradle còn in log và thông tin task của chính nó, có thể khác giữa các phiên bản/môi trường; khối trên chỉ biểu diễn đầu ra của ứng dụng. Nếu các tệp và môi trường đúng, task test chạy test JUnit và task build kiểm tra/đóng gói theo quan hệ do plugin cung cấp. Đầu ra build thường nằm dưới thư mục build/, chẳng hạn JAR dưới build/libs/.

Ở lần chạy đầu, Gradle cần kết nối mạng để tải bản phân phối Wrapper (nếu chưa có trong cache) và dependency JUnit. Sau đó các thành phần đã cache có thể được tái sử dụng; chạy offline chỉ khả thi khi mọi dependency cần thiết đã sẵn có.

### 5.3. Tự quan sát hiệu quả của tự động hóa

1. Chạy Wrapper với task build, ghi nhận những task thực sự đã chạy.
2. Chạy lại cùng lệnh khi không sửa gì: các task có input/output phù hợp có thể báo UP-TO-DATE hoặc FROM-CACHE.
3. Đổi giá trị kỳ vọng của assertEquals thành một chuỗi sai, rồi chạy task test: build phải báo kiểm thử thất bại. Sửa lại test để tiếp tục.
4. Đổi logic greeting hoặc test và chạy lại: Gradle xác định công việc chịu ảnh hưởng dựa trên cấu hình, đầu vào và phụ thuộc.
5. Chạy task clean rồi build lại nếu cần kiểm tra một build sạch; clean chủ động xóa output thông thường trong thư mục build nên có thể khiến nhiều bước phải chạy lại.

Thử nghiệm này minh họa lý do **build là chuỗi bước có thể kiểm chứng**, thay vì chỉ là nút “Compile”. Không nên mặc định thêm clean vào mọi lệnh thường ngày vì như vậy mất đi một phần lợi ích bỏ qua công việc không đổi.

## 6. Những lệnh Gradle nên biết trước tiên

| Lệnh (macOS/Linux) | Công dụng |
|---|---|
| ./gradlew tasks | Liệt kê các task được hiển thị cho dự án |
| ./gradlew help | Kiểm tra khả năng chạy Gradle và xem trợ giúp |
| ./gradlew run | Chạy ứng dụng khi có plugin application |
| ./gradlew test | Biên dịch phần cần thiết và chạy test do project cấu hình |
| ./gradlew check | Chạy các kiểm tra chất lượng gắn với task check |
| ./gradlew assemble | Tạo các artifact/bản phân phối được gắn vào assemble |
| ./gradlew build | Chạy vòng đời build gồm check và assemble theo plugin |
| ./gradlew clean | Xóa các output build do task clean quản lý |
| ./gradlew dependencies | Xem cây dependency theo cấu hình |
| ./gradlew build --stacktrace | In stack trace để điều tra lỗi build |
| ./gradlew build --info | Tăng mức chi tiết log chẩn đoán |

Trên Windows, thay ./gradlew bằng .\gradlew.bat. Chỉ gọi được task khi plugin hoặc build script thực sự định nghĩa task ấy; ví dụ một project không áp dụng application sẽ không tự có task run.

## 7. Gradle gắn với làm việc nhóm và CI ra sao?

Một nhóm muốn build đáng tin cậy cần đưa **source, settings, build scripts, Wrapper và cấu hình cần thiết** vào version control. Nhà phát triển và CI gọi cùng Wrapper, ví dụ:

~~~text
Checkout source
    ↓
Cài/cung cấp JDK phù hợp
    ↓
Chạy ./gradlew --no-daemon build
    ↓
Nếu test/build thành công: lấy artifact từ build/
Nếu thất bại: chặn bước phát hành và đọc log
~~~

CI không tự bảo đảm chất lượng chỉ vì đã chạy Gradle: nhóm phải cấu hình test, kiểm tra code, coverage hoặc các quality gate cần thiết. Để tăng tính ổn định, cần cố định hoặc kiểm soát phiên bản plugin/dependency, chọn repository đáng tin cậy, quản lý biến môi trường và secret, dùng Java toolchain và xem xét dependency locking/verification nếu phù hợp. Wrapper cố định **phiên bản Gradle**, không cố định tất cả thư viện hoặc môi trường chạy.

Với **multi-project build**, một settings file có thể khai báo nhiều subproject. Gradle hiểu quan hệ giữa các module và có thể chỉ dựng những thành phần cần cho task được yêu cầu. Đây là bước phát triển tự nhiên khi một ứng dụng tách thành library, service và các module liên quan; bài nhập môn này chưa yêu cầu tự thiết kế multi-project build.

## 8. Hiểu đúng giới hạn và các lỗi thường gặp

- **“Có Gradle rồi thì không cần biết Java/JDK.”** Sai. Gradle điều phối; compiler và runtime Java vẫn phải có và tương thích. Hãy phân biệt JDK chạy Gradle với toolchain biên dịch mã.
- **“Máy tôi đã cài Gradle, cứ dùng gradle là được.”** Trong dự án cộng tác, nên dùng Wrapper đã commit để tránh lệch bản Gradle.
- **“Khai báo dependency là Gradle tự tải được trong mọi trường hợp.”** Dependency resolution còn phụ thuộc repository, mạng, thông tin phiên bản và quyền truy cập. Lỗi Could not resolve... thường nên bắt đầu bằng kiểm tra tọa độ dependency/repository và log.
- **“Lệnh build luôn chạy lại toàn bộ.”** Gradle có khả năng tránh chạy task không cần thiết; nhưng tùy task khai báo input/output, cache và cấu hình thực tế.
- **“Task test thành công chứng tỏ không có bug.”** Nó chỉ xác nhận những kiểm thử đã viết và đã chạy đều qua. Thiếu test hoặc chất lượng test kém vẫn có thể bỏ sót lỗi.
- **“Build thành công đồng nghĩa đã deploy.”** build thường tạo/check artifact. Phát hành hoặc deploy là quy trình riêng, cần task/pipeline phù hợp.
- **“Sau khi đổi build script, sao kết quả khác?”** Cấu hình build, phiên bản thư viện, JDK, plugin và biến môi trường là một phần đầu vào; phải xem chúng như mã nguồn có thể thay đổi hành vi.
- **“Cần chạy clean để sửa mọi lỗi.”** clean đôi khi giúp loại output cũ nhưng không thay thế việc đọc nguyên nhân, chẳng hạn xung đột dependency, sai mainClass hoặc test thất bại.

Nếu gặp lỗi, đọc thông báo cụ thể của task thất bại, thử --stacktrace hoặc --info, kiểm tra JDK/dependency và so sánh môi trường với CI. Đừng xóa mọi cache hoặc bỏ qua test ngay khi thấy lỗi, vì có thể làm mất dấu vấn đề gốc.

## 9. Tự kiểm tra mức độ hiểu bài

1. Một đồng đội biên dịch Java thành công nhưng quên chạy test và đóng gói. Vì sao đó chưa phải pipeline build đầy đủ?
2. Nếu task tạo JAR phụ thuộc vào task biên dịch, Gradle biết thứ tự từ đâu? Nó có cần chạy lại compiler khi input không đổi hay không?
3. Wrapper, Java toolchain, version dependency và repository lần lượt kiểm soát những khía cạnh nào của tính tái lập?
4. Điểm khác nhau giữa dependency JUnit trong build script và quan hệ phụ thuộc giữa task test với các bước biên dịch là gì?
5. Vì sao không nên coi BUILD SUCCESSFUL là bằng chứng ứng dụng đã được deploy hoặc không còn lỗi?

**Gợi ý đáp án:** (1) còn thiếu các công việc và kiểm tra phải được định nghĩa/chạy; (2) từ task graph và các điều kiện tránh làm lại công việc; (3) lần lượt là Gradle distribution, JDK cho task, thư viện và nguồn tải; (4) một bên là thư viện trên classpath, bên kia là trình tự công việc; (5) build chỉ xác nhận các task cấu hình đã hoàn thành, không thay thế triển khai hay kiểm chứng đầy đủ nghiệp vụ.

## Tài liệu chính thức để đọc tiếp

- [Gradle User Manual – Build Lifecycle](https://docs.gradle.org/current/userguide/build_lifecycle.html)
- [Gradle User Manual – Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html)
- [Gradle User Manual – Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html)
- [Gradle User Manual – Testing in Java & JVM projects](https://docs.gradle.org/current/userguide/java_testing.html)
- [Gradle User Manual – Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html)

**Ghi nhớ:** Gradle biến kiến thức về cách build từ “các lệnh ai đó nhớ phải gõ” thành **quy tắc được khai báo, có thể chạy lại, kiểm tra và tự động hóa**. Giá trị cốt lõi đến từ việc mô hình hóa đúng đầu vào, dependency, task và chất lượng, không chỉ từ một lệnh build ngắn.
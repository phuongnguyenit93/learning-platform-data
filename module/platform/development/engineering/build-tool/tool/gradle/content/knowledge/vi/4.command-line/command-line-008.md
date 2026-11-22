# Dùng offline, refresh-dependencies, rerun-tasks đúng tình huống

**Chủ đề:** Build Tool Gradle  
**Nhóm:** Dòng lệnh

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích chính xác sự khác nhau giữa ba tùy chọn **--offline**, **--refresh-dependencies** và **--rerun-tasks** của Gradle.
2. Xác định vấn đề xảy ra ở bước **phân giải dependency** hay **thực thi task**, thay vì thêm các flag theo cảm tính.
3. Chọn lệnh phù hợp khi mất mạng, metadata dependency bị cũ, bản SNAPSHOT thay đổi, hoặc task báo UP-TO-DATE nhưng cần chạy lại.
4. Thực hành bằng dự án Java 17 có unit test và một task tự tạo; quan sát các trạng thái EXECUTED, UP-TO-DATE, FROM-CACHE, NO-SOURCE.
5. Biết giới hạn của từng flag đối với build cache, Gradle Wrapper, plugin, task có truy cập mạng, CI và khả năng tái lập build.

**Nguyên tắc quan trọng:** Cả ba flag đều điều khiển **một lần chạy Gradle**. Chúng không thay thế việc sửa dependency sai, khai báo input/output của task, cấu hình repository, hoặc thiết lập môi trường đúng.

## 1. Bắt đầu bằng hai câu hỏi: dependency hay task?

Trong một build, Gradle thực hiện các hoạt động có liên quan nhưng khác cơ chế:

- **Dependency resolution:** xác định phiên bản module và lấy metadata/artifact cho thư viện hoặc plugin mà build cần. Ví dụ, resolve JUnit từ Maven Central.
- **Task execution:** chạy công việc như compileJava, test, jar hoặc task tùy chỉnh. Gradle có thể bỏ qua hành động của một task khi kết quả vẫn hợp lệ hoặc lấy output từ build cache.

Đối với mỗi triệu chứng, hỏi:

- **Thiếu hoặc nghi ngờ thư viện đang dùng?** Xem dependency cache, repository, phiên bản và chế độ online/offline.
- **Thư viện đúng nhưng một công việc cần thực hiện lại?** Xem task inputs/outputs, trạng thái task và --rerun-tasks.

Cách nhìn này giúp phân biệt các cache:

| Loại dữ liệu/cache | Mục đích | Liên quan đến flag nào? |
|---|---|---|
| **Dependency cache** trong Gradle User Home | Lưu metadata, kết quả chọn phiên bản và các artifact thư viện đã tải | --offline và --refresh-dependencies |
| **Task output** trong thư mục build/ | Chứa class, báo cáo, JAR và các tệp do task tạo | --rerun-tasks tác động đến quyết định chạy task; clean có thể xóa output |
| **Build cache** (local/remote nếu bật) | Tái sử dụng output của task đủ điều kiện khi đầu vào phù hợp | --rerun-tasks bỏ qua khả năng lấy task output từ cache khi buộc chạy |
| **Configuration cache** (nếu bật và tương thích) | Tái sử dụng trạng thái pha cấu hình build | Không phải đối tượng chính của ba flag trong bài này |
| **Gradle distribution do Wrapper dùng** | Chứa bản Gradle mà dự án chọn | Wrapper có thể cần tải trước khi Gradle xử lý các flag |

**Tránh nhầm:** Dependency cache chứa thư viện; build cache chứa đầu ra công việc. Xóa thư mục build/ không đồng nghĩa xóa các thư viện trong Gradle User Home. Một dependency đã cache không bảo đảm task compileJava hay test được bỏ qua; còn task UP-TO-DATE không có nghĩa dependency cache đã được làm mới.

## 2. --offline: dùng dependency đã cache, không phân giải qua mạng

### 2.1. Cơ chế

Khi thêm **--offline**, Gradle phân giải dependency bằng dữ liệu đã có trong cache cục bộ và không truy cập repository qua mạng để tìm hoặc tải module mới. Những metadata về phiên bản động hoặc dependency dạng changing đã cache có thể được dùng ngay cả khi thông thường đã tới lúc kiểm tra lại.

Ví dụ trên Linux/macOS:

~~~bash
./gradlew test --offline
./gradlew build --offline
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test --offline
.\gradlew.bat build --offline
~~~

Trong các ví dụ, dùng **Gradle Wrapper** đã commit vào dự án để chọn phiên bản Gradle nhất quán. Dấu ./gradlew là cách gọi file script trên Linux/macOS; trên Windows dùng .\gradlew.bat.

Nếu dependency bắt buộc chưa từng được resolve/tải đủ vào cache đang sử dụng, build offline **thất bại**. Gradle không tự tạo một thư viện thiếu hoặc đoán nội dung của repository. Vì thế, --offline không có nghĩa là "luôn build thành công khi mất mạng".

### 2.2. Tình huống phù hợp

- Bạn đang trên máy bay hoặc mạng yếu, dự án đã build thành công trước đó và các dependency cần thiết đã có.
- Muốn chạy test hoặc thử một nhánh code mà không thay đổi kết quả dependency resolution do repository từ xa.
- Hệ thống CI dùng cache đã được chuẩn bị đầy đủ và **có chủ đích** hoạt động không cần truy vấn repository; quy trình phải bảo đảm nội dung cache phù hợp.

Nên chuẩn bị khi đang online: chạy đúng những task sẽ cần dùng offline để Gradle thực sự tải cả metadata **và artifact** cần thiết. Chỉ chạy task dependencies để xem cây dependency chưa chắc đã đưa mọi JAR vào cache dùng cho compile/test. Plugin từ plugin portal, các thành phần build logic hoặc các dependency khác cũng phải có sẵn.

### 2.3. Những giới hạn thường bị bỏ qua

1. **Wrapper có thể cần mạng trước khi Gradle khởi động.** Nếu bản Gradle được khai báo trong gradle/wrapper/gradle-wrapper.properties chưa có trên máy, script gradlew có thể cần tải distribution. Flag --offline của Gradle không ngăn hoặc thay thế bước bootstrap Wrapper.
2. **Task tùy chỉnh có thể tự truy cập mạng.** --offline chủ yếu điều khiển Gradle dependency resolution; không phải quy tắc firewall cho mọi plugin, shell command, API call hoặc chương trình chạy trong task. Một task tải file bằng HTTP vẫn có thể cố gọi mạng nếu code không tuân thủ chế độ offline.
3. **JDK/toolchain phải sẵn có.** Nếu build yêu cầu JDK 17 mà máy chưa cài, khả năng tự tải toolchain còn tùy cấu hình resolver và môi trường. Chuẩn bị JDK trước khi làm việc offline.
4. **Cache phụ thuộc ngữ cảnh.** Máy khác, Gradle User Home khác, repository khác hoặc phiên bản Gradle khác có thể không có đủ dữ liệu cần thiết, dù một máy trước đó build tốt.
5. **Không xác nhận dependency mới nhất.** Khi offline, Gradle không kiểm tra cập nhật remote; với dependency động/changing, bản cache có thể cũ.

**Không dùng --offline để chữa lỗi repository hoặc sai tọa độ dependency.** Nếu online không resolve được dependency do group/artifact/version sai, chuyển offline chỉ thay nguồn dữ liệu và có thể che giấu vấn đề bằng cache cũ.

## 3. --refresh-dependencies: kiểm tra lại trạng thái dependency

### 3.1. Cơ chế

Tùy chọn **--refresh-dependencies** (viết ngắn **-U**) yêu cầu Gradle thực hiện lại việc phân giải dependency, bỏ qua kết quả cache tương ứng và xác minh thông tin cần thiết từ các repository đã cấu hình:

~~~bash
./gradlew test --refresh-dependencies
./gradlew dependencies --configuration testRuntimeClasspath --refresh-dependencies
~~~

Khi phù hợp, Gradle kiểm tra metadata, danh sách phiên bản, checksum và artifact. **Không có nghĩa tất cả JAR sẽ bị tải lại bất kể có thay đổi hay không.** Gradle có thể kiểm tra từ xa rồi tái sử dụng artifact cục bộ có checksum phù hợp; lưu lượng mạng và số file thực tế tải lại tùy repository và nội dung thay đổi.

Có thể dùng -U tương đương:

~~~bash
./gradlew test -U
~~~

### 3.2. Khi nào nên dùng?

- Bạn nghi dependency dạng **dynamic version**, ví dụ 1.+, đang cho kết quả cũ vì metadata cache.
- Một module **changing** (ví dụ bản SNAPSHOT được công bố lại theo đúng quy ước) đã thay đổi trên repository, nhưng Gradle vẫn dùng dữ liệu đã cache.
- Repository từng cấu hình sai, thiếu metadata rồi đã được sửa và bạn cần kiểm tra lại trạng thái hiện tại.
- Kết quả dependency resolution giữa máy/CI có dấu hiệu lệch và bạn đã kiểm tra repository, phiên bản và các cấu hình liên quan.

Gradle mặc định cache kết quả phiên bản động và changing module trong một khoảng thời gian; mặc định thường là **24 giờ** cho từng loại, và build có thể cấu hình lại thời hạn. --refresh-dependencies là lựa chọn cho **một lần chạy** khi thật sự cần kiểm tra ngay, không phải thay thế cho chiến lược chọn phiên bản ổn định.

### 3.3. Những việc --refresh-dependencies KHÔNG làm

- Không xóa thư mục build/ như task clean.
- Không bắt buộc chạy lại compileJava/test nếu đầu vào và output không thay đổi. Sau khi resolve lại dependency mà artifact vẫn giống nhau, task có thể tiếp tục báo UP-TO-DATE.
- Không sửa group/artifact/version sai, repository chưa đăng ký, lỗi authentication, proxy, chứng chỉ TLS hoặc quyền truy cập.
- Không bảo đảm chọn phiên bản mới nếu bạn khai báo phiên bản cố định và artifact tương ứng không đổi.
- Không nên dùng cùng --offline để kỳ vọng vừa cấm network vừa kiểm tra dữ liệu mới từ remote; hai mục tiêu trái nhau. Khi cần cập nhật từ repository, hãy chạy online.

**Dấu hiệu tốt để dùng:** vừa xác nhận repository đã có bản SNAPSHOT mới và muốn thử cập nhật ngay. **Dấu hiệu không tốt:** test không chạy vì báo UP-TO-DATE; trong trường hợp đó, xem --rerun-tasks.

### 3.4. Lưu ý về tính tái lập

Dependency động/changing làm tăng nguy cơ cùng một commit nhưng các thời điểm khác nhau nhận artifact khác nhau. Trong CI/phát hành, ưu tiên version rõ ràng, dependency locking/verification khi phù hợp và quản trị repository đúng quy trình. Refresh chỉ giúp Gradle đối chiếu lại dữ liệu; nó không làm dependency vốn thay đổi trở nên bất biến.

## 4. --rerun-tasks: chạy lại hành động task dù output đã có

### 4.1. Cơ chế

Khi thêm **--rerun-tasks**, Gradle buộc thực thi các task thuộc đồ thị cần chạy, bỏ qua kiểm tra UP-TO-DATE và khả năng lấy đầu ra task từ **build cache** cho các task đó:

~~~bash
./gradlew test --rerun-tasks
./gradlew :app:test --rerun-tasks
./gradlew build --rerun-tasks
~~~

Flag này tác động đến **task được yêu cầu và các task phụ thuộc thuộc execution graph**, không có nghĩa tất cả task của mọi project đều được chạy. Ví dụ, yêu cầu test sẽ khiến các bước biên dịch cần thiết trong đồ thị được thực thi lại dù trước đó chúng UP-TO-DATE, nhưng một task triển khai không liên quan sẽ không tự chạy.

So với:

~~~bash
./gradlew clean test
~~~

thì **--rerun-tasks không yêu cầu xóa toàn bộ build/** trước khi thực hiện. Tương tự ở mục tiêu chạy lại bước build, nhưng khác rõ ràng về việc giữ các file output sẵn có; clean có thể xóa thêm nhiều artifact và ảnh hưởng những task khác. Không coi hai lệnh là tương đương tuyệt đối.

### 4.2. Khi nào nên dùng?

- Cần kiểm chứng một test có thực sự chạy và liệu kết quả có còn ổn định khi không lấy output từ cache.
- Điều tra một task có hành vi không ổn định hoặc nghi khai báo input/output sai.
- Muốn có một lượt thực thi task thật để quan sát log, profiler hoặc lỗi chỉ phát sinh trong action.
- Sau khi sửa công cụ hoặc môi trường, muốn chạy lại toàn bộ chuỗi task liên quan mà chưa muốn xóa artifact bằng clean.

**Lưu ý:** Đây là biện pháp chẩn đoán. Nếu task đọc một file không khai báo là input nên Gradle đánh dấu UP-TO-DATE sai, sửa mô hình input/output mới là giải pháp lâu dài. Dùng --rerun-tasks thường xuyên chỉ che giấu vấn đề và làm build chậm.

### 4.3. Những việc --rerun-tasks KHÔNG làm

- Không yêu cầu Gradle tải metadata hoặc dependency mới từ repository. Nó vẫn có thể dùng dependency cache theo quy tắc bình thường.
- Không bật network nếu đang --offline.
- Không chạy task ngoài đồ thị, không bỏ qua lỗi build và không bảo đảm những task không có source hoặc bị vô hiệu hóa sẽ có action thực hiện. Các trạng thái **NO-SOURCE**, **SKIPPED** hoặc điều kiện onlyIf vẫn có ý nghĩa.
- Không sửa lỗi do code/test sai và không làm JUnit test xuất hiện khi dự án không có test hoặc chưa cấu hình test.
- Không tương đương với việc xóa sạch cache của Gradle User Home.

Nếu vấn đề là "**đang dùng JAR cũ**", hãy kiểm tra dependency resolution và cân nhắc --refresh-dependencies; nếu "**test bị UP-TO-DATE nhưng tôi cần chạy lại**", hãy cân nhắc --rerun-tasks.

## 5. Chọn flag theo triệu chứng

| Tình huống thực tế | Lệnh gợi ý | Vì sao? | Kiểm tra thêm |
|---|---|---|---|
| Mất Internet, lần trước build đã tải đủ dependency | ./gradlew test --offline | Chỉ dùng dependency cache hiện có | Wrapper distribution, JDK, plugin, toàn bộ artifact đã sẵn chưa? |
| Mất mạng, dependency chưa từng được tải | Chưa có lệnh nào bảo đảm thành công | Cache thiếu module bắt buộc | Kết nối online để tải trước hoặc dùng repository/cache được chuẩn bị |
| Bản SNAPSHOT trên repository vừa thay đổi, muốn kiểm tra ngay | ./gradlew test --refresh-dependencies | Resolve lại trạng thái dependency | Changing dependency đã được đánh dấu đúng? |
| Bản dynamic 1.+ chưa chọn bản được công bố gần đây | ./gradlew dependencies --refresh-dependencies | Làm mới metadata chọn version | Có nên pin/lock version thay vì dùng bản động? |
| Task test UP-TO-DATE nhưng cần chứng kiến chạy lại | ./gradlew test --rerun-tasks | Bỏ qua UP-TO-DATE và build cache của các task được thực thi | Test thực sự tồn tại, được cấu hình và không bị skip? |
| Task compileJava UP-TO-DATE mặc dù input bên ngoài thay đổi | Chạy --rerun-tasks để chẩn đoán; sau đó sửa task input | Rerun xác nhận triệu chứng, sửa cấu hình để bền vững | Input/output khai báo đã đầy đủ chưa? |
| Vừa sửa dependency mà test vẫn UP-TO-DATE | Trước tiên xem dependency thực tế được resolve | Có thể artifact không đổi hoặc task không chịu ảnh hưởng | dependencies, dependencyInsight, --info |
| Cần kiểm chứng cả metadata dependency mới và thực thi mọi task liên quan | ./gradlew test --refresh-dependencies --rerun-tasks | Hai flag điều khiển hai khía cạnh riêng | Chỉ kết hợp khi cả hai nhu cầu có căn cứ |
| Muốn xóa output build trước khi dựng lại | ./gradlew clean build | clean xóa output mà task clean quản lý | Không đồng nghĩa xóa dependency cache |
| Lỗi “Could not resolve” do sai repository/credentials | Sửa cấu hình, quyền truy cập trước | Flag không sửa được thông tin sai | Repository, proxy, TLS, token và logs |

**Thứ tự xử lý lỗi:** đọc thông báo lỗi → xác định tầng dependency hay task → chọn **một** biện pháp sát nguyên nhân → quan sát kết quả → sửa cấu hình gốc nếu cần. Đừng thêm cả ba flag vào lệnh CI mặc định.

## 6. Thực hành: Java 17 + JUnit 5 + một task có output

Ví dụ sau được thiết kế để quan sát **cả hai cơ chế**: dependency resolution (JUnit 5) và quyết định chạy task (writeReport, compileJava, test). Dự án dùng Groovy DSL, Java toolchain 17 và một file output được khai báo đúng.

### 6.1. Chuẩn bị

Cần một JDK phù hợp để chạy Gradle, JDK 17 có thể được tìm thấy bởi toolchain, và bản Gradle tương thích. Lần đầu cần mạng nếu chưa tải Gradle distribution/JUnit. Ví dụ giả định đã có Wrapper của dự án; nếu chưa, dùng bản Gradle đã cài chạy **gradle wrapper** một lần, sau đó dùng ./gradlew (Linux/macOS) hoặc .\gradlew.bat (Windows).

Cấu trúc:

~~~text
gradle-flags-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── src/
    ├── main/java/demo/Hello.java
    └── test/java/demo/HelloTest.java
~~~

Nếu chưa tạo Wrapper, lúc đầu chỉ cần settings.gradle, build.gradle, src/; các file Wrapper sẽ được tạo sau.

**settings.gradle**

~~~groovy
rootProject.name = 'gradle-flags-lab'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.10.2'
}

tasks.named('test') {
    useJUnitPlatform()
}

// Đầu vào và đầu ra rõ ràng cho một task có thể UP-TO-DATE.
def messageProvider = providers.gradleProperty('reportMessage')
    .orElse('Xin chao Gradle')
def reportFile = layout.buildDirectory.file('reports/flag-demo.txt')

tasks.register('writeReport') {
    inputs.property('reportMessage', messageProvider)
    outputs.file(reportFile)

    doLast {
        def output = reportFile.get().asFile
        output.parentFile.mkdirs()
        output.setText(messageProvider.get() + "\n", 'UTF-8')
        println('Generated: ' + messageProvider.get())
    }
}
~~~

**src/main/java/demo/Hello.java**

~~~java
package demo;

public final class Hello {
    private Hello() {
    }

    public static String message() {
        return "Xin chao Java 17";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

**src/test/java/demo/HelloTest.java**

~~~java
package demo;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class HelloTest {
    @Test
    void messageIsStable() {
        assertEquals("Xin chao Java 17", Hello.message());
    }
}
~~~

**Giải thích:** Plugin java cung cấp các task compileJava, compileTestJava và test. JUnit được khai báo cho test và lấy từ Maven Central khi resolve. Java toolchain chọn JDK 17 cho những task Java được plugin quản lý. Task writeReport có input property và output file nên có thể được đánh dấu UP-TO-DATE ở lần chạy sau nếu không thay đổi. Nó không phụ thuộc JUnit; vì vậy có thể dùng riêng để quan sát task execution.

### 6.2. Quan sát task có và không bị chạy lại

Chạy:

~~~bash
./gradlew writeReport --console=plain
./gradlew writeReport --console=plain
./gradlew writeReport --rerun-tasks --console=plain
./gradlew writeReport -PreportMessage="Noi dung moi" --console=plain
~~~

Trong lần đầu, **dòng do action writeReport in ra** là:

~~~text
Generated: Xin chao Gradle
~~~

Ở lần thứ hai, nếu file output còn nguyên và không có input thay đổi, Gradle thường báo:

~~~text
> Task :writeReport UP-TO-DATE
~~~

Khi chạy --rerun-tasks, task thực thi lại action nên xuất hiện:

~~~text
Generated: Xin chao Gradle
~~~

Lần cuối với -PreportMessage, do input reportMessage thay đổi, action chạy mà **không cần** --rerun-tasks:

~~~text
Generated: Noi dung moi
~~~

File build/reports/flag-demo.txt tương ứng chứa một dòng thông điệp, thêm ký tự xuống dòng ở cuối. Các log khác của Gradle (thời gian chạy, tổng số task) không cố định và không được trình bày như stdout nguyên vẹn.

Điểm học được: có input/output rõ ràng giúp Gradle quyết định chính xác lúc nào cần chạy lại; --rerun-tasks chỉ ép chạy trong một lần cụ thể.

### 6.3. Quan sát dependency cache với test JUnit

Lần đầu khi **đang online**:

~~~bash
./gradlew test --console=plain
~~~

Nếu JDK/repository/mạng phù hợp, Gradle tải và resolve những thành phần JUnit cần dùng, biên dịch mã và chạy test. **Khi test thành công, JUnit không mặc nhiên in thông báo “test passed” từ test code**; theo dõi trạng thái task và báo cáo kiểm thử trong build/reports/tests/test/.

Ngay sau đó, thử:

~~~bash
./gradlew test --offline --console=plain
~~~

Khi dependency cần thiết đã có trong cache của **chính Gradle User Home** đó, lệnh offline có thể thành công mà không truy vấn Maven Central. Task test có thể UP-TO-DATE; thành công của offline ở đây chứng tỏ build dùng được dependency cục bộ, **không chứng tỏ test đã chạy lại**.

Nếu muốn **vừa không resolve qua mạng vừa buộc thực thi lại test**, chạy:

~~~bash
./gradlew test --offline --rerun-tasks --console=plain
~~~

Hai flag không xung đột: offline quản lý việc dùng dependency, rerun-tasks quản lý hành động task. Chúng không bảo đảm những task hoặc plugin tùy biến không tự gọi network.

### 6.4. Quan sát refresh-dependencies

Sau lần build online đầu tiên, chạy:

~~~bash
./gradlew test --refresh-dependencies --info --console=plain
~~~

Quan sát log phân giải dependency: Gradle có thể kiểm tra lại metadata và artifact trong repository. Vì các phiên bản JUnit của ví dụ được pin và nội dung không đổi, việc refresh có thể **không tải lại JAR** và task test vẫn có thể UP-TO-DATE. Điều đó là hợp lý, không phải flag bị lỗi.

Có thể xem cấu hình dependency bằng:

~~~bash
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency junit-jupiter --configuration testRuntimeClasspath
~~~

Hai lệnh trên giúp phân tích **phiên bản được chọn và lý do chọn**; chúng không thay thế hoàn toàn việc chạy task test để chuẩn bị artifact cần thiết cho offline. Khi dùng --refresh-dependencies với dependencies, Gradle có thể làm mới resolution nhưng vẫn không chạy test.

### 6.5. Chạy riêng ứng dụng Java

Sau khi Java đã được biên dịch:

~~~bash
./gradlew classes
java -cp build/classes/java/main demo.Hello
~~~

**Đầu ra đúng của lớp Java** (không tính log Gradle) là:

~~~text
Xin chao Java 17
~~~

Đây là bước đối chiếu rằng mã Java 17 chạy được độc lập với quyết định resolve JUnit của các task test. Trên Windows cũng có thể chạy class từ build/classes/java/main với classpath đúng hệ điều hành.

## 7. Chẩn đoán bằng trạng thái task và log

Một số trạng thái thường thấy:

| Trạng thái | Ý nghĩa cơ bản | Cách đọc đúng |
|---|---|---|
| **UP-TO-DATE** | Gradle xác định input/output phù hợp và không cần chạy lại task action | Không phải lỗi; --rerun-tasks dùng khi cần ép thực thi |
| **FROM-CACHE** | Output được lấy từ build cache đủ điều kiện | Không có nghĩa dependency từ repository vừa được tải mới |
| **NO-SOURCE** | Task không có nguồn cần xử lý | --rerun-tasks không tạo ra source hay test mới |
| **SKIPPED** | Task bị skip theo điều kiện/logic phù hợp | Kiểm tra enabled, onlyIf, task configuration |
| **FAILED** | Task/step thất bại | Đọc nguyên nhân trong log, có thể liên quan code, dependency hoặc môi trường |
| **EXECUTED** (thường thể hiện bằng dòng task không có hậu tố skip/cache) | Hành động task thực sự được chạy | Không suy ra mọi dependency đã được kiểm tra mới |

Lệnh hữu ích:

~~~bash
./gradlew test --info --console=plain
./gradlew test --stacktrace --console=plain
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew help --task test
~~~

- **--info** tăng thông tin vì sao task được/không được thực thi và các hoạt động liên quan.
- **--stacktrace** phù hợp khi cần xem stack trace lỗi Gradle/plugin; lỗi business logic trong test vẫn cần đọc test report.
- **dependencies** hiển thị dependency tree của configuration cần xem.
- **help --task** cho biết task và các option được hỗ trợ.

Trong multi-project build, chỉ rõ project để tránh nhìn nhầm:

~~~bash
./gradlew :service:test --offline
./gradlew :service:dependencies --configuration testRuntimeClasspath --refresh-dependencies
./gradlew :service:test --rerun-tasks
~~~

Các lệnh với :service: chỉ đúng khi project thực sự có subproject tên service và task tương ứng.

## 8. Lỗi phổ biến: nhận diện nguyên nhân và hành động

### 8.1. "Could not resolve" khi --offline

**Triệu chứng:** Gradle báo không có module/metadata/artifact trong cache offline.

**Nguyên nhân có thể:** Chưa chạy task cần artifact đó khi online; dependency phiên bản mới; đổi Gradle User Home, máy, repository hoặc plugin; JDK/Wrapper chưa được chuẩn bị.

**Cách xử lý:** Khi có mạng, kiểm tra repository và phiên bản, chạy task cần thiết để tải đủ; dùng đúng Gradle User Home; sau đó thử offline lại. Không giải quyết bằng --rerun-tasks, vì flag này chỉ điều khiển task execution.

### 8.2. Cùng phiên bản nhưng artifact đã bị publish lại

**Triệu chứng:** Repository chứa artifact thay đổi, nhưng môi trường đang dùng artifact cũ.

**Cách xử lý:** Xác minh cách publish và chính sách changing. Với SNAPSHOT/phiên bản động, dùng --refresh-dependencies để xác minh cập nhật. Với phiên bản release bất biến, **không nên publish lại cùng tọa độ/version**; đặt phiên bản mới đáng tin cậy sẽ tốt hơn. Đừng cho rằng refresh mặc nhiên sửa được lỗi cơ chế publish.

### 8.3. Test không chạy vì UP-TO-DATE

**Triệu chứng:** Task test UP-TO-DATE, bạn muốn thu thập log từ lần chạy thật.

**Cách xử lý:** Thử --rerun-tasks. Nếu test được báo NO-SOURCE, kiểm tra thư mục src/test/java, plugin và test framework. Nếu test bị SKIPPED, xem task configuration, enabled/onlyIf và filter. --refresh-dependencies không phải lệnh ép chạy test.

### 8.4. Rerun làm build chậm hoặc lỗi không biến mất

**Nguyên nhân:** Nhiều task phụ thuộc được thực thi lại, kể cả các bước biên dịch, không thể tận dụng UP-TO-DATE/build cache như bình thường. Nếu lỗi là do mã hoặc dependency sai, thực thi lại vẫn thất bại.

**Cách xử lý:** Chỉ rerun khi cần chẩn đoán; sửa input/output, plugin hoặc code/test thực chất. Đừng thêm --rerun-tasks mặc định vào mọi pipeline vì mất hiệu năng và che khuất cấu hình task không đúng.

### 8.5. Refresh không làm task test chạy lại

**Nguyên nhân:** Metadata đã được kiểm tra mới nhưng các artifact và input của task không thay đổi. Trạng thái UP-TO-DATE vì thế vẫn hợp lý.

**Cách xử lý:** Nếu mục tiêu là chạy lại test, cân nhắc --rerun-tasks. Nếu mục tiêu là dùng dependency khác, kiểm tra dependency tree, version constraint, repository và cách publish.

### 8.6. Offline vẫn xuất hiện kết nối mạng ở nơi khác

**Nguyên nhân:** Wrapper đang bootstrap distribution, toolchain cần cung cấp JDK, hoặc plugin/task/Java process tự gọi một dịch vụ mạng ngoài Gradle dependency resolution.

**Cách xử lý:** Phân loại nơi khởi phát request; chuẩn bị công cụ và dependency trước; cấu hình task/plugin để tôn trọng chế độ offline nếu công cụ đó hỗ trợ. Đừng dựa vào --offline như một lớp ngăn mọi truy cập mạng của hệ điều hành.

### 8.7. "Chữa" mọi lỗi bằng clean, refresh, rerun cùng lúc

**Hậu quả:** Tốn mạng và CPU, thay đổi nhiều yếu tố một lúc, khó nhận diện nguyên nhân, làm mất lợi ích cache.

**Cách xử lý:** Lặp lại lỗi bằng lệnh tối thiểu, thêm đúng một flag phù hợp, ghi nhận thay đổi rồi sửa nguyên nhân. Chỉ kết hợp khi có hai yêu cầu độc lập và đã xác minh.

## 9. Khi áp dụng trong CI và làm việc nhóm

1. **Ưu tiên Wrapper** và khai báo phiên bản plugin/dependency nhất quán. Wrapper có thể chuẩn hóa Gradle nhưng không tự đóng băng mọi dependency hoặc JDK.
2. **Bình thường chạy build/test không kèm ba flag.** Gradle tự quyết định có thể bỏ qua việc nào, và dependency cache giúp giảm tải mạng.
3. **Tách chiến lược cache.** Cache dependency hỗ trợ resolution, còn build cache hỗ trợ task output; mỗi loại có nguyên tắc bảo toàn và bảo mật khác nhau.
4. **Chỉ bật --offline có điều kiện**, khi đã chủ động chuẩn bị cache và dự kiến không cần repository từ xa. Cache trống trên CI mới dựng không thể tự hoàn thiện offline.
5. **Dùng --refresh-dependencies có chọn lọc** để điều tra metadata/artifact có khả năng cũ; nếu pipeline thường xuyên phải refresh mới đúng, nên sửa chính sách phiên bản, repository, locking và publish.
6. **Dùng --rerun-tasks có chọn lọc** khi cần thực thi task thật để chẩn đoán; không thay thế khai báo input/output và không cần thiết cho mọi lần CI.
7. **Giữ bằng chứng:** lưu lệnh chạy, phiên bản Gradle/JDK, tên task, dependency coordinates, thông báo lỗi và log có lọc secret. Điều này giúp xác định một lỗi thuộc độ tươi của dependency hay cơ chế bỏ qua task.

Ví dụ quy trình kiểm tra có căn cứ:

~~~text
Test lỗi do không tìm được artifact?
  -> Xác minh repository + phiên bản; khi online, cân nhắc --refresh-dependencies.

Không có mạng và cache đã đủ?
  -> Dùng --offline; nếu fail, xác định dependency/plugin/toolchain còn thiếu.

Test bị UP-TO-DATE nhưng cần chạy lại?
  -> Dùng --rerun-tasks cho task liên quan.

Cả dependency mới lẫn thực thi task thật đều cần kiểm chứng?
  -> Kết hợp --refresh-dependencies --rerun-tasks khi đang online.

Task sai kết quả vì không khai báo input?
  -> Sửa input/output của task; không dùng flag để che lỗi lâu dài.
~~~

## 10. Tự kiểm tra kiến thức

**Câu 1.** Bạn chuẩn bị demo trong chuyến bay, đã chạy test thành công online trước đó. Chọn flag nào và cần bảo đảm những thành phần nào đã có?

**Câu 2.** Module my-lib:1.0-SNAPSHOT vừa được cập nhật trên repository; project vẫn dùng bản cũ. Nên thử flag nào? Vì sao flag ấy không bắt buộc tải lại mọi JAR?

**Câu 3.** Task test in UP-TO-DATE nhưng bạn muốn thu lại kết quả từ một lần thực thi thật. Chọn flag nào? Nó có bắt buộc tải lại JUnit không?

**Câu 4.** Sau khi chạy --refresh-dependencies, test vẫn UP-TO-DATE. Gradle có làm sai không?

**Câu 5.** Một task tải tài nguyên qua HTTP bằng code tự viết. --offline có bảo đảm request sẽ bị ngăn không? Tại sao?

**Câu 6.** Khi nào kết hợp --offline và --rerun-tasks có ý nghĩa? Khi nào kết hợp --refresh-dependencies và --rerun-tasks có ý nghĩa?

**Gợi ý đáp án:**

1. --offline; bảo đảm Wrapper distribution, JDK/toolchain, plugin, dependency metadata và artifact cần thiết sẵn có; task custom có thể cần kiểm tra riêng.
2. --refresh-dependencies; Gradle kiểm tra lại resolution/metadata và chỉ tải artifact mới khi thực sự cần.
3. --rerun-tasks; flag đó không mặc nhiên refresh dependency.
4. Không; refresh xử lý dependency, còn UP-TO-DATE thuộc quyết định thực thi task và có thể vẫn đúng.
5. Không; task tự quản lý HTTP không nhất thiết tuân theo Gradle offline mode.
6. Offline + rerun khi cần chạy lại với artifact đã cache; refresh + rerun khi cần kiểm tra dependency mới **và** ép thực thi task trong một lượt online.

## Tài liệu tham khảo chính thức

- [Gradle User Manual — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): mô tả ba flag, task graph và force task execution.
- [Gradle User Manual — Dependency Caching](https://docs.gradle.org/current/userguide/dependency_caching.html): cache metadata/artifact, offline mode, dynamic/changing dependencies và refresh.
- [Gradle User Manual — Understanding Tasks](https://docs.gradle.org/current/userguide/more_about_tasks.html): task input/output, UP-TO-DATE và build cache.
- [Gradle User Manual — Adopting the Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache_adoption.html): phân biệt tác dụng --rerun-tasks khi cần thực thi task actions.
- [Gradle User Manual — The Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): cách Wrapper chọn và tải Gradle distribution.
- [Gradle User Manual — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html): quản trị phiên bản dependency để cải thiện khả năng tái lập.

**Ghi nhớ:** **--offline** sử dụng dependency cache thay vì cập nhật qua repository; **--refresh-dependencies** kiểm tra lại dependency resolution từ repository; **--rerun-tasks** buộc thực thi lại các task thuộc đồ thị, bỏ qua UP-TO-DATE và task output cache. Chọn flag theo **triệu chứng đã xác minh**, sau đó sửa nguyên nhân build nếu cần.
# Chọn bộ phiên bản tương thích giữa Java, Spring Boot, Maven và Gradle

## 1. Vì sao phải chọn phiên bản theo một bộ?

Một dự án Spring Boot có thể biên dịch tốt trên máy lập trình nhưng lỗi ngay khi chạy build ở CI hoặc triển khai lên server. Một nguyên nhân phổ biến là các công cụ và môi trường Java dùng **những phiên bản không tương thích**. Ví dụ:

- Nâng Spring Boot lên một nhánh mới nhưng giữ Gradle Wrapper quá cũ: plugin Spring Boot không hỗ trợ bản Gradle đó.
- Đặt Java 21 cho ứng dụng nhưng chạy Gradle 8.4 bằng JVM Java 21: bản Gradle này chưa được xác nhận hỗ trợ **chạy chính Gradle** trên Java 21.
- Biên dịch ứng dụng bằng Java 21 rồi triển khai trên Java 17: JVM ở server không đọc được class file mới hơn.
- Một người chạy Maven/Gradle bản cài toàn máy, người khác chạy Wrapper ghim phiên bản riêng của dự án: kết quả build có thể khác nhau.

Mục tiêu của bài là biết **chọn và xác minh một tổ hợp hoạt động được**, giải thích vì sao tổ hợp đó hợp lệ, và lưu lựa chọn vào cấu hình dự án để máy cá nhân, IDE và CI sử dụng nhất quán.

**Không cần dùng cả Maven lẫn Gradle để build cùng một ứng dụng.** Thông thường mỗi dự án chọn **một** công cụ: Maven **hoặc** Gradle. Khi nói “bộ Java – Spring Boot – Maven/Gradle”, ta cần kiểm tra tương thích của Spring Boot với Java và với công cụ build **đã chọn**, rồi kiểm tra các ràng buộc riêng của công cụ đó.

## 2. Phân biệt bốn phiên bản liên quan

| Thành phần | Vai trò | Nơi thường cấu hình/quan sát |
| --- | --- | --- |
| **Java/JDK** | JDK để chạy công cụ build, biên dịch và chạy kiểm thử; JVM/JRE để thực thi ứng dụng | JAVA_HOME, cấu hình IDE/CI, Gradle toolchain, Maven toolchains, image nền |
| **Spring Boot** | Framework và tập dependency/plugin của ứng dụng | Spring Boot parent/BOM và Maven Plugin; Gradle plugin/BOM |
| **Maven** | Quản lý dependencies, lifecycle, biên dịch, test, package đối với dự án Maven | pom.xml, Maven Wrapper trong .mvn/wrapper |
| **Gradle** | Quản lý dependencies, task graph, compiler/toolchain, test, package đối với dự án Gradle | build.gradle(.kts), Gradle Wrapper trong gradle/wrapper |

Đừng gộp mọi phiên bản Java thành một con số duy nhất. Ít nhất cần nhận diện:

1. **Java chạy Maven/Gradle**: JVM mà tiến trình build sử dụng; Maven có thể xem qua **./mvnw -version**, Gradle qua **./gradlew --version**.
2. **Java dùng để biên dịch/test**: JDK do Gradle Java toolchain hoặc Maven toolchains chọn; có thể khác JVM chạy công cụ build.
3. **Java mức ngôn ngữ/API/bytecode mục tiêu**: cấu hình **--release** hoặc tương đương; quyết định chương trình có thể dùng cú pháp/API nào.
4. **Java chạy ứng dụng khi triển khai**: JVM trong VM, container image hoặc runtime của nền tảng.

Một tổ hợp “đúng” phải thỏa tất cả những nơi liên quan; chỉ thấy **java -version** trên laptop là chưa đủ để kết luận.

## 3. Kiểm tra tương thích theo giao của các điều kiện

Có thể hình dung cách chọn phiên bản như sau:

~~~text
Bước 1: Chọn nhánh/patch Spring Boot được dự án chấp nhận
                 |
                 v
Bước 2: Chọn Java nằm trong khoảng Boot hỗ trợ
                 |
                 v
Bước 3: Chọn Maven HOẶC Gradle nằm trong danh sách Boot hỗ trợ
                 |
                 v
Bước 4: Nếu dùng Gradle, kiểm tra Gradle có chạy được trên JVM build
                 |
                 v
Bước 5: Kiểm tra Java biên dịch, target bytecode và JVM deploy
                 |
                 v
Bước 6: Ghim Wrapper, chạy build/test và thử artifact thực tế
~~~

Từng tài liệu tương thích chỉ giải quyết một phần:

- **Spring Boot System Requirements**: phiên bản Java tối thiểu/tối đa được hỗ trợ và phiên bản Maven/Gradle được hỗ trợ rõ ràng cho **nhánh Boot cụ thể**.
- **Gradle Java Compatibility Matrix**: phiên bản Gradle nào có thể **chạy trên một JVM** và bản nào hỗ trợ Java qua **toolchain** cho compile/test.
- **Tài liệu Maven và plugin trong dự án**: JDK tối thiểu để chạy Maven, yêu cầu của Maven Compiler Plugin, Spring Boot Maven Plugin và các plugin khác.
- **Môi trường triển khai**: JVM có đủ mới để chạy bytecode và các thư viện/framework hay không.

Phương pháp là lấy **giao** của những điều kiện này. Không thể suy luận “Spring Boot hỗ trợ Java 21” thành “mọi bản Gradle mà Spring Boot cho phép đều chạy được dưới Java 21”.

## 4. Các dải phiên bản tham khảo từ tài liệu chính thức

Bảng dưới ghi lại các ví dụ từ trang System Requirements của **từng nhánh/patch** (đối chiếu ngày 09/11/2026). Các dải là thông tin tương thích do dự án Spring Boot công bố; **không có nghĩa tất cả nhánh đều đang được hỗ trợ bảo trì ở thời điểm đọc bài**. Khi áp dụng thực tế, hãy mở trang của phiên bản dự án đang dùng và kiểm tra trạng thái hỗ trợ, bản vá mới nhất.

| Nhánh Spring Boot được tra cứu | Java mà nhánh đó công bố hỗ trợ | Maven được công bố hỗ trợ | Gradle được công bố hỗ trợ |
| --- | --- | --- | --- |
| **3.3.13** | Java 17 đến 23 | Maven 3.6.3+ | Gradle 7.x từ 7.5 hoặc Gradle 8.x |
| **3.5.16** | Java 17 đến 25 | Maven 3.6.3+ | Gradle 7.x từ 7.6.4 hoặc Gradle 8.x từ 8.4 |
| **4.0.9** | Java 17 đến 27 | Maven 3.6.3+ | Gradle 8.x từ 8.14 hoặc Gradle 9.x |
| **4.1.2** | Java 17 đến 27 | Maven 3.6.3+ | Gradle 8.x từ 8.14 hoặc Gradle 9.x |

Nguồn để tự kiểm tra:
- Boot 3.3: https://docs.spring.io/spring-boot/3.3/system-requirements.html
- Boot 3.5: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- Boot 4.0: https://docs.spring.io/spring-boot/4.0/system-requirements.html
- Boot 4.1 / bản tài liệu hiện hành: https://docs.spring.io/spring-boot/system-requirements.html

**Lưu ý 1 — Tra đúng nhánh:** Nếu dự án dùng Boot 3.5, không lấy quy định của trang “latest” thuộc nhánh 4.x để kết luận Gradle/Java có thể sử dụng cho Boot 3.5. Bản patch trong một nhánh cũng có thể cập nhật danh sách Java được hỗ trợ.

**Lưu ý 2 — Maven 3.6.3+ không có nghĩa bỏ qua plugin:** Bảng là mức hỗ trợ được Boot công bố. Đối với dự án thực, hãy kiểm tra thêm phiên bản Maven Compiler Plugin, Surefire, Kotlin/Lombok hoặc plugin công ty. Khi chọn Maven 3.x, ưu tiên bản 3.x mới được tổ chức cho phép và ghim bằng Maven Wrapper.

**Lưu ý 3 — Hỗ trợ Java tới phiên bản nào là có giới hạn:** Nếu Boot 3.3.13 công bố hỗ trợ đến Java 23 thì tự nâng runtime lên Java 25 là thay đổi **ngoài dải đã được xác nhận**; không nên tuyên bố được hỗ trợ chỉ vì ứng dụng có lúc khởi động thành công.

## 5. Tương thích Java của Gradle: phân biệt JVM chạy Gradle và toolchain

Đây là điểm dễ gây sai khi chọn phiên bản. Theo bảng Gradle Compatibility Matrix, một số ngưỡng tương thích Java phổ biến là:

| Java được xét | Gradle bắt đầu hỗ trợ **chạy Gradle** trên Java đó | Gradle bắt đầu hỗ trợ **Java toolchain** cho Java đó |
| --- | --- | --- |
| Java 17 | Gradle 7.3 | Gradle 7.3 |
| Java 21 | Gradle 8.5 | Gradle 8.4 |
| Java 25 | Gradle 9.1.0 | Gradle 9.1.0 |
| Java 27 | Gradle 9.8.0 | Gradle 9.8.0 |

Nguồn: https://docs.gradle.org/current/userguide/compatibility.html

Sự khác nhau giữa hai cột rất quan trọng. **Gradle 8.4 có hỗ trợ Java 21 làm toolchain để biên dịch**, nhưng theo ma trận nó **chưa hỗ trợ chạy bản thân Gradle trên JVM Java 21**. Nếu nhất định phải giữ Gradle 8.4, có thể chạy Gradle bằng JDK 17 và dùng Java 21 toolchain để biên dịch, nếu các plugin của dự án cho phép. Nếu muốn **chạy Gradle bằng JDK 21**, cần Gradle **8.5 trở lên** và vẫn phải nằm trong khoảng mà plugin Spring Boot hỗ trợ.

Ví dụ về giao điều kiện:

- **Boot 3.5.16 + Java 21 + Gradle 8.14**: thuộc phạm vi hỗ trợ của Boot 3.5 và Gradle 8.14 có thể chạy trên Java 21. Đây là một bộ hợp lý.
- **Boot 4.1.2 + Java 21 + Gradle 8.14**: cũng phù hợp với các phạm vi trên.
- **Boot 4.1.2 + Java 25 + Gradle 9.1**: Boot 4.1 cho phép Java 25, Boot 4.1 cho phép Gradle 9.x, Gradle 9.1 có thể chạy trên Java 25.
- **Boot 4.1.2 + Java 21 + Gradle 8.10**: không phù hợp dù Gradle 8.10 chạy được trên Java 21, vì Boot 4.1 yêu cầu Gradle 8.x từ **8.14**.
- **Boot 3.5.16 + Java 21 + Gradle 8.4 chạy bằng JDK 21**: không phù hợp ở tầng JVM chạy Gradle. Có thể xem xét JDK 17 để chạy Gradle và toolchain Java 21, hoặc nâng Gradle trong dải Boot hỗ trợ.

Trường hợp Boot hỗ trợ một phiên bản Java rất mới **không bảo đảm** mọi Gradle đã được Boot liệt kê đều có thể chạy/toolchain với Java đó. Phải chọn giao giữa hai ma trận, không chỉ đọc một bảng.

## 6. Quy trình chọn bộ phiên bản cho dự án mới hoặc dự án đang có

### Bước 1: Xác định yêu cầu trước khi chọn

Ghi rõ: dự án tạo mới hay đang bảo trì; có yêu cầu nâng Boot hay không; môi trường chạy hiện có JDK nào; bắt buộc dùng Maven hay Gradle; CI có thể cài JDK nào; các plugin/framework bổ sung có giới hạn riêng không. Một dự án phải chạy trên Java 17 không thể tự chọn bytecode Java 21 chỉ vì developer đã cài Java 21.

Đối với hệ thống đã chạy production, **ưu tiên nhận diện bộ hiện tại và phiên bản được hỗ trợ trước khi nâng cấp**. Đừng chọn tất cả bản mới nhất một cách độc lập rồi mới ghép lại.

### Bước 2: Chọn phiên bản Spring Boot phù hợp và được bảo trì

Kiểm tra trang tài liệu/versioned release của nhánh Boot, trạng thái hỗ trợ và tương thích thư viện phụ thuộc. Mỗi nhánh chính có thể thay đổi Java, Spring Framework, servlet API, Jakarta namespaces và plugin requirements. Việc nhảy nhánh lớn cần xem migration guide và kiểm thử lại mã nguồn, không chỉ đổi version trong pom.xml hay build.gradle.

Sau khi chọn nhánh, chốt một bản patch đã được kiểm chứng. Ở dự án Maven thường thống nhất phiên bản **spring-boot-starter-parent** hoặc BOM với **spring-boot-maven-plugin**. Ở dự án Gradle, thống nhất Spring Boot Gradle Plugin với dependency management/BOM tương ứng. Đừng trộn nhiều nhánh Boot trong classpath một cách vô tình.

### Bước 3: Chọn Java mục tiêu

Chọn Java nằm trong dải Boot hỗ trợ, đồng thời phù hợp runtime triển khai. Java 17, 21 và 25 là các ví dụ nhánh LTS; việc chọn nhánh nào còn phụ thuộc chính sách tổ chức, bản vá bảo mật và plugin khác.

Với ứng dụng Spring Boot cần Java 17 trở lên, **đặt --release 11 không biến toàn bộ ứng dụng thành Java 11-compatible**: các thư viện Boot vẫn đòi mức Java tối thiểu tương ứng. Chỉ có thể hạ mức bytecode tới phiên bản mà toàn bộ framework/dependencies/runtime thực sự hỗ trợ.

### Bước 4: Chọn Maven hoặc Gradle trong dải Boot hỗ trợ

**Nếu dùng Maven:** chọn phiên bản Maven được Boot hỗ trợ và hợp JDK chạy Maven, rồi ghim Maven Wrapper. Maven cần JDK để build Java; các plugin Maven có thể yêu cầu phiên bản JDK riêng.

**Nếu dùng Gradle:** chọn một phiên bản thỏa đồng thời:
1. Nằm trong dải Gradle mà Spring Boot plugin cho phép.
2. Hỗ trợ JVM sẽ chạy Gradle tại IDE/terminal/CI.
3. Hỗ trợ Java toolchain và các plugin bổ sung cần thiết.

Đừng nghĩ “Gradle 9 mới hơn Gradle 8 nên chắc chắn hợp với mọi Spring Boot 3.x”: một nhánh Boot cũ có thể chỉ công bố Gradle 7.x/8.x. Tương tự, một bản Boot mới có thể ngừng hỗ trợ Gradle cũ.

### Bước 5: Chốt Java biên dịch và Java runtime

Nếu cần Java 21 khi deploy, cấu hình toolchain và compiler target ở mức 21; JVM triển khai phải tương thích với bytecode đó và nằm trong dải Java mà Boot hỗ trợ. Đối với một artifact biên dịch với mức Java 21, chỉ đổi JAVA_HOME trên server sang Java 17 sẽ không giải quyết được lỗi khởi động.

Nên cho CI build/test artifact trong môi trường Java được kiểm soát và kiểm tra trực tiếp artifact cuối cùng bằng runtime dự kiến triển khai.

### Bước 6: Ghim, kiểm thử và ghi lại quyết định

Commit các tệp build, Wrapper, thiết lập toolchain/Java release và cấu hình CI vào version control. Ghi rõ trong README dự án bộ phiên bản đã được chọn cùng lý do và link tài liệu tham chiếu. Chạy build/test với **Wrapper**, rồi chạy artifact trên runtime đích. Khi nâng cấp một thành phần, xem lại toàn bộ giao điều kiện.

## 7. Java toolchain, --release, JAVA_HOME và IDE: bốn thứ khác nhau

### 7.1. Gradle Java toolchain

Ví dụ **build.gradle** (Groovy DSL), phần cấu hình Java của một project Gradle có Java plugin:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 21
}
~~~

- **toolchain.languageVersion** yêu cầu một bộ JDK 21 để thực thi các tác vụ Java có hỗ trợ toolchain. Gradle có thể phát hiện JDK đã cài; tải JDK tự động chỉ khi cấu hình kho toolchain phù hợp.
- **options.release = 21** yêu cầu compiler tạo bytecode và kiểm tra Java API theo mức 21, tránh vô tình dùng API mới hơn khi javac đến từ JDK cao hơn.
- Không nên coi đoạn này là một project build độc lập: nó phải nằm trong **build.gradle** đã áp dụng plugin Java (và các plugin cần thiết của ứng dụng).

Toolchain **không tự đổi JVM chạy daemon Gradle**. Gradle có thể chạy bằng JDK 17 và biên dịch với toolchain JDK 21, miễn phiên bản Gradle/plugin cho phép và JDK 21 có sẵn/được provision. Vì thế phải kiểm tra cả **./gradlew --version** lẫn danh sách toolchain.

Tham khảo: https://docs.gradle.org/current/userguide/toolchains.html

### 7.2. Maven: compiler release và toolchains

Trong project kế thừa **spring-boot-starter-parent**, thông thường có thể đặt Java mục tiêu:

~~~xml
<properties>
    <java.version>21</java.version>
</properties>
~~~

Tùy parent/plugin, **maven.compiler.release** có thể được cấu hình trực tiếp để bảo đảm mức API/bytecode mục tiêu. Ví dụ cấu hình compiler release đơn giản trong POM:

~~~xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
~~~

Đây là **đoạn XML minh họa**, phải đặt đúng vào phần properties của POM hoàn chỉnh và kiểm tra cấu hình parent/plugin hiệu lực. Thuộc tính release không tự cài JDK 21 và không quyết định Maven đang chạy trên JVM nào. Với project cần JDK biên dịch khác JDK chạy Maven, tìm hiểu **Maven Toolchains Plugin** và cấu hình toolchain của tổ chức. Khi không dùng toolchains, Maven thường sử dụng JDK đang chạy Maven để biên dịch.

### 7.3. JAVA_HOME và IDE

**JAVA_HOME** thường ảnh hưởng JDK mặc định dùng để chạy Maven/Gradle; IDE có thể có mục chọn **Gradle JVM** hoặc **Maven Runner JRE** riêng. Một người có thể thấy java -version trên terminal là 21, nhưng IDE đang chạy Gradle với JDK khác. Với Gradle mới, tiêu chí Daemon JVM hoặc quy định JVM của môi trường cũng có thể chi phối JDK chạy Gradle. Luôn kiểm tra từ chính lệnh build được dùng trong từng môi trường.

### 7.4. Runtime triển khai

Artifact Java chứa bytecode của mức Java được compile. Ví dụ thông dụng:

| Mức Java biên dịch | Major version của class file | JVM tối thiểu để đọc class file đó |
| --- | --- | --- |
| Java 17 | 61 | Java 17 |
| Java 21 | 65 | Java 21 |
| Java 25 | 69 | Java 25 |

Đây chỉ là **điều kiện bytecode**. JVM vẫn phải nằm trong dải mà Spring Boot, thư viện runtime và môi trường hạ tầng hỗ trợ. Dùng Java 25 để chạy class Java 21 có thể hợp bytecode, nhưng vẫn phải xem tương thích của Boot và dependencies.

## 8. Wrapper: ghim công cụ build để mọi môi trường dùng cùng bản

**Wrapper** là các script và cấu hình được lưu trong repository để lấy/khởi động phiên bản Maven hoặc Gradle của project. Wrapper giúp giảm tình trạng laptop có Gradle/Maven khác với server CI. Nó **không ghim luôn JDK**, nên vẫn phải quản lý Java song song.

### 8.1. Gradle Wrapper

Một cấu trúc thông dụng:

~~~text
project/
├── build.gradle
├── settings.gradle
├── gradlew
├── gradlew.bat
└── gradle/
    └── wrapper/
        ├── gradle-wrapper.jar
        └── gradle-wrapper.properties
~~~

Trong **gradle/wrapper/gradle-wrapper.properties**, trường **distributionUrl** chỉ tới bản Gradle được ghim; chẳng hạn URL bản Gradle 8.14 phải trỏ đến distribution ZIP 8.14. Khi đổi phiên bản, dùng task Wrapper theo quy trình nâng cấp của Gradle để cập nhật script, JAR và properties phù hợp:

~~~bash
./gradlew wrapper --gradle-version 8.14
./gradlew wrapper --gradle-version 8.14
./gradlew --version
~~~

Chạy lại task có thể cần để đồng bộ đầy đủ wrapper script/JAR theo hướng dẫn Gradle. Đây là **minh họa nâng/ghim một project được phép dùng Gradle 8.14**; không thực hiện lệnh khi dự án hiện tại chưa xác định được plugin có hỗ trợ 8.14 hay không.

Khi nâng Wrapper, kiểm tra nguồn tải distribution, mã SHA-256 nếu dùng và tính nguyên vẹn của **gradle-wrapper.jar**. Chỉ commit các tệp Wrapper từ nguồn tin cậy. Tài liệu: https://docs.gradle.org/current/userguide/gradle_wrapper.html

### 8.2. Maven Wrapper

Một cấu trúc thông dụng:

~~~text
project/
├── pom.xml
├── mvnw
├── mvnw.cmd
└── .mvn/
    └── wrapper/
        └── maven-wrapper.properties
~~~

Một số phương thức triển khai Maven Wrapper còn có **maven-wrapper.jar** hoặc downloader, tùy kiểu Wrapper đã tạo. File properties xác định Maven distribution mà Wrapper cần khởi động. Kiểm tra bằng:

~~~bash
./mvnw --version
./mvnw clean verify
~~~

Dùng **mvnw.cmd** trên Windows; dùng **gradlew.bat** với Gradle trên Windows. Trên Linux/macOS, script Wrapper cần quyền thực thi. Khi chạy Wrapper, CI thường chỉ phải cung cấp JDK, mạng/cache và các biến môi trường cần thiết; không phải tự cài một Maven/Gradle tùy ý rồi gọi trực tiếp.

Tài liệu: https://maven.apache.org/wrapper/ và https://maven.apache.org/install.html

## 9. Ví dụ cụ thể: chọn Java 21 và Spring Boot 3.5.16

Giả sử yêu cầu là **ứng dụng mới thử nghiệm**, runtime Java 21, team muốn dùng Maven hoặc Gradle; sau khi kiểm tra chính sách bảo trì cho dự án thực tế, ta lấy nhánh **Spring Boot 3.5.16** làm ví dụ kỹ thuật.

- Boot 3.5.16: hỗ trợ Java 21.
- Nếu chọn **Maven 3.9.x**, phiên bản này vượt mức Maven tối thiểu mà Boot công bố và có thể dùng JDK 21; cần kiểm tra các plugin của dự án.
- Nếu chọn **Gradle 8.14**, Boot 3.5 cho phép Gradle 8.x từ 8.4 và Gradle 8.14 chạy được với Java 21.
- Cấu hình target Java 21; CI build và server chạy trên Java 21; lưu đúng Wrapper tương ứng.

Hai cấu hình bên dưới là **hai lựa chọn thay thế** cho cùng ý tưởng ứng dụng. Chỉ tạo **pom.xml** khi chọn Maven, hoặc **build.gradle** khi chọn Gradle.

### 9.1. Lựa chọn Maven: POM tối thiểu hoàn chỉnh

Tệp **pom.xml** tại project root:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>version-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
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
~~~

Spring Boot parent quản lý nhiều phiên bản dependencies/plugins tương thích, nên ví dụ không tự chỉ định version cho starter. Plugin Boot được khai báo để tạo executable JAR qua lifecycle được parent cấu hình. **Java 21 JDK cần có sẵn**, hoặc môi trường Maven phải dùng toolchain thích hợp.

### 9.2. Lựa chọn Gradle: build.gradle tối thiểu hoàn chỉnh

Tệp **build.gradle** (Groovy DSL) tại project root:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

Project Gradle còn cần **settings.gradle** và một Gradle Wrapper phù hợp. Plugin Spring Boot và dependency management đảm nhận phiên bản managed dependencies; không tự đặt một phiên bản Spring Framework riêng không khớp Boot. Ở ví dụ này, Gradle 8.14 và Java 21 đáp ứng hai ma trận đã kiểm tra.

### 9.3. Mã Java dùng chung cho hai lựa chọn

Tệp **src/main/java/com/example/demo/VersionDemoApplication.java**:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class VersionDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(VersionDemoApplication.class, args);
    }
}
~~~

Đây là lớp Java hoàn chỉnh, biên dịch được khi project có các Spring Boot dependencies như trên. Ứng dụng không khai báo web endpoint nên khi chạy chỉ khởi động Spring application context rồi có thể kết thúc bình thường; không mong đợi một HTTP server trên cổng 8080. Log Spring Boot thay đổi theo phiên bản/môi trường nên không ấn định stdout cố định.

Đối với project **Maven đã có Maven Wrapper**:

~~~bash
./mvnw --version
./mvnw clean verify
java -jar target/version-demo-0.0.1-SNAPSHOT.jar
~~~

Đối với project **Gradle đã có Gradle Wrapper 8.14**:

~~~bash
./gradlew --version
./gradlew clean build
java -jar build/libs/version-demo-0.0.1-SNAPSHOT.jar
~~~

Các lệnh dùng cho Linux/macOS; đổi sang **mvnw.cmd** hoặc **gradlew.bat** trên Windows. Phần chạy JAR là bước xác minh executable artifact. Tên file JAR dựa trên group/artifact/version trong ví dụ; nếu build có chỉnh tên archive, hãy lấy đúng file thực tế của nó.

**Giới hạn của ví dụ:** cấu hình Maven/Gradle mô tả hai project lựa chọn, không có nghĩa chạy cả hai Wrapper trên cùng một project. Việc tạo Wrapper là bước chuẩn bị project; đoạn Java không thể tự biên dịch bằng javac thiếu Spring dependencies. Muốn đánh giá tương thích runtime thật, cần chạy build và artifact trên JDK/CI/container đúng mục tiêu.

## 10. Kịch bản nâng cấp và cách quyết định

### Tình huống A — nâng Java 17 lên Java 21, giữ Spring Boot 3.5

1. Kiểm tra bản patch Boot 3.5 hiện tại và tài liệu của nó có hỗ trợ Java 21.
2. Nếu Gradle Wrapper là **8.4** và Gradle chạy bằng Java 21, nâng lên Gradle **8.5+ trong dải Boot hỗ trợ** (ví dụ 8.14), hoặc giữ JVM Gradle 17 và thiết lập toolchain 21 nếu phù hợp.
3. Chuyển Gradle/Maven Java target lên 21 khi muốn sử dụng tính năng/bytecode Java 21. Không cần nâng target nếu mục đích chỉ là chạy ứng dụng bằng JVM Java 21 và vẫn phải hỗ trợ JVM 17.
4. Kiểm tra CI, IDE, Docker base image hoặc server JDK thực tế; build và chạy artifact để xác nhận.

### Tình huống B — nâng Spring Boot 3.5 lên 4.1, muốn giữ Gradle 8.10

Boot 4.1 yêu cầu Gradle 8.x từ **8.14** hoặc Gradle 9.x. Dù Gradle 8.10 có thể chạy trên Java 21, **tổ hợp Boot 4.1 + Gradle 8.10 không thuộc phạm vi được Boot 4.1 công bố hỗ trợ**. Cần chọn Gradle 8.14+ hoặc 9.x và kiểm tra plugin khác, sau đó mới nâng Boot. Đồng thời đọc migration guide của Boot để sửa thay đổi API/config liên quan.

### Tình huống C — muốn dùng Java 25 với Spring Boot 4.1

Boot 4.1 có hỗ trợ Java 25. Nếu muốn **chạy chính Gradle trên JVM Java 25**, cần Gradle **9.1+** (và vẫn thuộc nhánh Gradle 9.x mà Boot 4.1 hỗ trợ). Không chọn Gradle 8.14 rồi giả định đủ chỉ vì Boot cho phép Gradle 8.14: Gradle 8.14 không thuộc dải được xác nhận chạy trên Java 25.

Với Maven, cần chọn bản Maven/plugin tương thích Java 25, kiểm tra Maven Wrapper, rồi chạy lại tests và thử executable artifact. Việc Spring Boot hỗ trợ Java 25 không có nghĩa tất cả công cụ annotation processing hoặc thư viện của dự án đã hỗ trợ.

### Tình huống D — không thể đổi Java 17 ở môi trường triển khai

Chọn Spring Boot và dependencies vẫn hỗ trợ Java 17, đặt target bytecode Java 17 và kiểm thử ứng dụng trên JVM Java 17. Có thể dùng JDK mới hơn để build nếu compiler được cấu hình **--release 17** và cả build plugin/Boot vẫn phù hợp, nhưng cần kiểm tra thực tế; JDK mới trên CI không tự biến artifact thành Java 17-compatible.

## 11. Kiểm tra phiên bản đang chạy bằng lệnh cụ thể

Đứng tại project root và ghi lại kết quả từ **đúng máy và pipeline** đang build.

~~~bash
java -version
javac -version
~~~

Hai lệnh này cho biết Java mặc định theo PATH ở terminal. Chúng **không đủ** để xác định Gradle toolchain hoặc Maven Toolchains sẽ dùng JDK nào.

**Nếu dùng Gradle:**

~~~bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew clean test bootJar
~~~

- **--version**: quan sát bản Gradle và thông tin JVM liên quan.
- **javaToolchains**: liệt kê các bộ Java mà Gradle phát hiện để phục vụ Java toolchains.
- **clean test bootJar**: biên dịch, chạy test có trong project và tạo executable JAR khi Spring Boot Gradle Plugin được áp dụng. Việc build thành công chưa thay thế smoke test trên runtime triển khai.

**Nếu dùng Maven:**

~~~bash
./mvnw --version
./mvnw clean verify
~~~

- **--version**: quan sát bản Maven được Wrapper chạy và thông tin Java của tiến trình Maven.
- **clean verify**: chạy lifecycle đến verify theo các plugin được cấu hình. Với Spring Boot parent và Boot Maven Plugin như ví dụ, phase package tạo executable JAR nhờ repackage.

**Sau build**, chạy JAR đúng tên đầu ra và kiểm tra log khởi động, cấu hình/profile, kết nối dịch vụ, health endpoint (nếu project có) và hành vi nghiệp vụ trọng yếu. Đặt lại lệnh kiểm tra trong CI khi nâng JDK, Boot hoặc Wrapper.

### Đọc lỗi để biết đang lệch phiên bản nào

| Dấu hiệu | Thường sai ở đâu? | Bước kiểm tra |
| --- | --- | --- |
| **UnsupportedClassVersionError** khi java -jar | Java runtime đích thấp hơn class file của ứng dụng hoặc thư viện | java -version, Java target/release và dải Java của Boot |
| **Unsupported Java / Could not determine java version** từ Gradle | Gradle cũ chạy trên JVM quá mới | ./gradlew --version và Gradle Compatibility Matrix |
| **Spring Boot Gradle plugin requires Gradle ...** | Gradle Wrapper không nằm trong dải hỗ trợ của plugin Boot | Boot System Requirements, gradle-wrapper.properties |
| **invalid target release** hoặc **release version ... not supported** | JDK compiler không hỗ trợ mức --release được yêu cầu | javac -version, Gradle toolchain/Maven compiler |
| **No matching toolchains found** | Không tìm thấy JDK phù hợp và chưa cấu hình provisioning | ./gradlew -q javaToolchains, JDK cài đặt, toolchain repositories |
| **UnsupportedClassVersionError** ngay trong bước build plugin | JVM chạy công cụ build hoặc plugin quá cũ so với bytecode của plugin | ./mvnw --version hoặc ./gradlew --version, yêu cầu plugin |
| Build CLI thành công nhưng IDE thất bại | IDE dùng JDK/Gradle JVM hoặc importer khác CLI | IDE Gradle JVM/Maven Runner JRE và Wrapper |
| Test PASS nhưng JAR không chạy trên server | Runtime Java, cấu hình môi trường, dependencies hoặc packaging khác | Chạy chính JAR bằng JVM mục tiêu và kiểm tra logs |

Không nên sửa ngay bằng cách thêm random dependencies hoặc tắt kiểm thử. Xác định **bước nào** xảy ra lỗi (khởi động Gradle/Maven, resolve, compile, test, package, run) rồi đối chiếu chính phiên bản liên quan.

## 12. Những sai lầm thường gặp và thực hành tốt

- **Chọn mọi bản “latest” một cách độc lập:** Maven, Gradle, Boot và JDK mới nhất không tự tạo nên một tổ hợp được hỗ trợ. Luôn lấy giao các dải phiên bản.
- **Chỉ kiểm tra Java tối thiểu của Spring Boot:** còn phải xem **Java tối đa được xác nhận**, JVM chạy Gradle/Maven, toolchain và runtime.
- **Nhầm Java chạy Gradle với Java để compile:** toolchain có thể khác daemon JVM; điều này hữu ích nhưng phải được cấu hình/kiểm chứng.
- **Tưởng Wrapper ghim cả Java:** Wrapper chỉ ghim công cụ build; JDK cần quy định riêng trong CI, toolchain và môi trường deploy.
- **Trộn Boot plugin và BOM khác nhánh:** dễ tạo dependency graph không nhất quán hoặc build behavior khó đoán; quản lý bằng version set có chủ đích.
- **Không commit Wrapper:** thành viên phải phụ thuộc vào Gradle/Maven toàn máy và có nguy cơ chạy phiên bản khác CI.
- **Chỉ chạy bootRun hoặc chạy từ IDE:** có thể che lỗi của executable JAR và Java runtime mà production sẽ sử dụng.
- **Tự đổi target Java cao hơn runtime thực tế:** biên dịch PASS nhưng triển khai nổ UnsupportedClassVersionError.
- **Nâng phiên bản nhưng bỏ qua plugin bổ sung:** Kotlin, Lombok, JaCoCo, native-image, compiler plugin và annotation processors cũng có ma trận hỗ trợ riêng.

Một quyết định phiên bản tốt cần ghi lại ít nhất: **Spring Boot version + Java build/toolchain/release + Java deploy + Maven/Gradle Wrapper version + các plugin quan trọng + tài liệu tương thích đã tra + kết quả CI và smoke test**.

## 13. Tự kiểm tra bằng bốn câu hỏi

**Câu 1:** Dự án Spring Boot 4.1 dùng Java 21 và Gradle 8.10. Java 21 chạy được Gradle 8.10, vậy đã hợp lệ chưa?

**Trả lời:** Chưa. Boot 4.1 yêu cầu Gradle 8.x từ 8.14 hoặc Gradle 9.x, nên phải nâng Gradle vào dải này và kiểm tra plugin khác.

**Câu 2:** Dự án Boot 3.5 dùng Gradle 8.4. Có thể dùng Java 21 làm toolchain nhưng chạy Gradle trên Java 17 không?

**Trả lời:** Có thể theo các ngưỡng công bố: Gradle 8.4 hỗ trợ Java 21 toolchain và chạy được trên Java 17; Boot 3.5 cho phép Gradle 8.4. Cần kiểm tra phiên bản chính xác của các plugin và thực chạy build/test.

**Câu 3:** Chỉ cần đổi Maven Wrapper lên phiên bản mới thì server đang dùng Java 17 sẽ chạy được bytecode Java 21 chứ?

**Trả lời:** Không. Maven Wrapper chọn phiên bản Maven; nó không nâng JVM của server. Cần đổi target Java xuống mức hợp lệ hoặc nâng runtime server theo dải Boot hỗ trợ.

**Câu 4:** Dùng Java 25 để chạy Gradle 8.14 trong project Boot 4.1 được không, vì Boot 4.1 hỗ trợ Java 25 và Gradle 8.14?

**Trả lời:** Không theo ma trận Gradle: Gradle 8.14 không được xác nhận chạy trên Java 25. Chọn Gradle 9.1+ trong nhánh Gradle 9.x được Boot 4.1 hỗ trợ, hoặc chọn JVM chạy Gradle khác khi bài toán cụ thể cho phép.

## 14. Checklist chốt bộ phiên bản

- [ ] Chọn **một công cụ build** cho dự án: Maven hoặc Gradle.
- [ ] Xác định đúng **nhánh và bản patch Spring Boot**; tra System Requirements của chính nhánh đó.
- [ ] Chọn Java mục tiêu trong dải Boot hỗ trợ; xác nhận Java runtime của môi trường deploy.
- [ ] Chọn Maven/Gradle trong dải Boot hỗ trợ; nếu dùng Gradle kiểm tra **Java chạy Gradle** và **Java toolchain** riêng.
- [ ] Ghim Wrapper, plugin và dependency management; đồng bộ JDK/CI/IDE cần thiết.
- [ ] Chạy build, test, đóng gói và **khởi động artifact cuối cùng** trên JVM mục tiêu.
- [ ] Lưu bộ phiên bản và kết quả xác minh trong tài liệu dự án; đánh giá lại khi có nâng cấp.

**Ghi nhớ:** Tính tương thích là giao của các yêu cầu **Boot ↔ Java**, **Boot plugin ↔ Maven/Gradle**, **Gradle ↔ JVM của Gradle/toolchain** và **bytecode ↔ JVM triển khai**. Kiểm tra đủ các mối quan hệ đó giúp chọn được bộ phiên bản dễ build, dễ bảo trì, lặp lại được từ laptop tới CI và triển khai.

### Tài liệu tham khảo

- Spring Boot (bản hiện hành) — System Requirements: https://docs.spring.io/spring-boot/system-requirements.html
- Spring Boot 3.5 — System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- Spring Boot 4.0 — System Requirements: https://docs.spring.io/spring-boot/4.0/system-requirements.html
- Gradle — Compatibility Matrix: https://docs.gradle.org/current/userguide/compatibility.html
- Gradle — Toolchains for JVM Projects: https://docs.gradle.org/current/userguide/toolchains.html
- Gradle — Gradle Wrapper: https://docs.gradle.org/current/userguide/gradle_wrapper.html
- Apache Maven — Installing Maven: https://maven.apache.org/install.html
- Apache Maven — Maven Wrapper: https://maven.apache.org/wrapper/

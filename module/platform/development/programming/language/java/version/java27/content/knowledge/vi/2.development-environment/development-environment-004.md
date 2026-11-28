# Cấu hình SDK, mức ngôn ngữ và công cụ build trong IDE

Khi mở một dự án Java, IDE có thể hiển thị mã nguồn không có lỗi nhưng lệnh build ở terminal lại thất bại, hoặc dự án build được trên máy này nhưng không build được trên máy khác. Nguyên nhân thường là các thành phần đang sử dụng những phiên bản Java khác nhau: JDK của dự án, mức ngôn ngữ mà trình soạn thảo cho phép, phiên bản API và bytecode mục tiêu, hoặc JDK chạy chính công cụ build.

Với Java 27, cần cấu hình đồng bộ các thành phần này và để cấu hình của Maven hoặc Gradle làm nguồn thống nhất cho cả máy phát triển lẫn CI. IDE chịu trách nhiệm nhận diện JDK, hỗ trợ cú pháp và cung cấp trải nghiệm biên tập; build tool chịu trách nhiệm tái lập cách biên dịch, kiểm thử và đóng gói.

Nội dung dưới đây cập nhật theo tình trạng công cụ ngày **27/11/2026**. Java 27 đã phát hành chính thức ngày 15/09/2026; bản cập nhật JDK 27.0.1.1 phát hành ngày 17/11/2026. Java 27 là bản phát hành tính năng mới nhất, trong khi Java 25 vẫn là bản LTS mới nhất. Vì vậy, hãy dùng Java 27 khi dự án hoặc chương trình học yêu cầu phiên bản này; nếu chính sách triển khai của dự án yêu cầu một bản LTS, hãy chọn phiên bản LTS được dự án hỗ trợ và đặt đúng phiên bản đó trong build. Tham khảo [trang tải Java của Oracle](https://www.oracle.com/java/technologies/downloads/) và [ghi chú phát hành JDK 27](https://www.oracle.com/java/technologies/javase/27all-relnotes.html).

## 1. Phân biệt các lớp cấu hình Java

Các trường có tên gần giống nhau trong IDE và build tool có mục đích khác nhau. Trước khi thay đổi cấu hình, hãy xác định chính xác thành phần nào đang quyết định phiên bản.

| Thành phần | Ý nghĩa | Ví dụ với Java 27 |
| --- | --- | --- |
| JDK của dự án (Project SDK hoặc Project JDK) | Bộ công cụ Java mà IDE gắn với dự án, gồm compiler, runtime và các công cụ phát triển | JDK 27 |
| Mức ngôn ngữ (Language level) | Những cú pháp và tính năng ngôn ngữ mà IDE cho phép trong mã nguồn | Java 27; chỉ chọn Preview nếu dự án thực sự dùng tính năng preview |
| Phiên bản biên dịch mục tiêu (release) | Giới hạn cú pháp, API Java SE và định dạng class file mà compiler tạo ra | 27 nếu chạy trên Java 27; 25 nếu sản phẩm phải tương thích Java 25 |
| JDK chạy build tool | JVM dùng để khởi động Gradle daemon hoặc tiến trình Maven | Có thể là JDK 27 nếu phiên bản build tool hỗ trợ |
| Java toolchain | JDK cụ thể mà build tool chọn cho các tác vụ compile, test, run hoặc javadoc | JDK 27, độc lập với JDK khởi động Gradle/Maven trong các cấu hình phù hợp |
| Runtime của chính IDE | Java runtime mà IDE dùng để chạy giao diện và dịch vụ nội bộ của nó | Do bản IDE quản lý; không phải Project SDK của ứng dụng |

Ví dụ: một nhóm có thể chạy Gradle bằng JDK 27, biên dịch bằng toolchain JDK 27, nhưng đặt **release** là 25 để bảo đảm ứng dụng chỉ dùng cú pháp và API của Java 25. Khi đó, việc cài JDK 27 không tự động cho phép ứng dụng phụ thuộc API Java 27.

Ngược lại, nếu dự án cần sử dụng API Java 27 thì cả compiler được chọn và **release** phải hỗ trợ Java 27. Chỉ thay Language level trong IDE là chưa đủ để thay đổi cấu hình build.

## 2. Chuẩn bị JDK và kiểm tra hỗ trợ Java 27

### 2.1. Cài JDK 27

Chọn một bản phân phối JDK phù hợp với hệ điều hành và chính sách của tổ chức. Có thể sử dụng Oracle JDK, Eclipse Temurin, Amazon Corretto, Azul Zulu, Microsoft Build of OpenJDK, Red Hat Build of OpenJDK hoặc một bản phân phối OpenJDK được tổ chức phê duyệt. Dù chọn nhà cung cấp nào, hãy thống nhất vendor và phiên bản cập nhật giữa các máy nếu dự án yêu cầu khả năng tái lập chặt chẽ.

Tại thời điểm cập nhật bài viết, trang tải Oracle liệt kê JDK 27.0.1.1. Khi cài đặt, chọn gói đúng hệ điều hành và kiến trúc CPU; cài **JDK** để có compiler và công cụ phát triển, không chỉ cài runtime dành cho người dùng cuối.

Sau khi cài, kiểm tra trong terminal:

~~~~bash
java -version
javac -version
~~~~

Hai lệnh phải trỏ đến bản cài đặt dự kiến. Nếu kết quả không khớp, hãy kiểm tra JDK mà terminal đang tìm thấy trước khi thay đổi IDE. Cấu hình SDK trong IDE có thể trỏ trực tiếp đến thư mục JDK, vì vậy IDE và terminal có thể đang dùng hai bản cài đặt khác nhau.

### 2.2. Kiểm tra IDE có hỗ trợ Java 27

Không phải mọi phiên bản IDE đều hiểu cú pháp của JDK mới ngay khi JDK được cài trên máy. Cần dùng bản IDE hoặc thành phần hỗ trợ Java có khả năng phân tích đúng phiên bản dự án.

| IDE | Hỗ trợ Java 27 đã xác nhận | Lưu ý cấu hình |
| --- | --- | --- |
| IntelliJ IDEA | IntelliJ IDEA 2026.3 liệt kê Java 27 và tính năng preview | Đặt Project SDK và Language level trong Project Structure |
| Eclipse IDE | Eclipse 2026-09 (4.41) có gói hỗ trợ Java 27 ổn định | Cài Java 27 Support, sau đó chọn execution environment JavaSE-27 |
| Visual Studio Code | Java extension của Red Hat hỗ trợ Java 27 | Khai báo JDK dự án bằng **java.configuration.runtimes**; dự án Maven/Gradle vẫn cần cấu hình build tương ứng |

Tài liệu xác nhận: [IntelliJ IDEA supported Java versions](https://www.jetbrains.com/help/idea/supported-java-versions.html), [Java 27 in IntelliJ IDEA](https://blog.jetbrains.com/idea/2026/09/java-27-in-intellij-idea/), [Java 27 Support for Eclipse 2026-09](https://marketplace.eclipse.org/content/java-27-support-eclipse-2026-09-441) và [Java extension for Visual Studio Code](https://github.com/redhat-developer/vscode-java).

## 3. Cấu hình Project SDK và Language level trong IDE

### 3.1. IntelliJ IDEA

IntelliJ IDEA 2026.3 hỗ trợ Java 27. Thực hiện các bước sau:

1. Mở **File → Project Structure → Project**.
2. Trong **SDK**, chọn JDK 27 đã cài. Nếu chưa đăng ký JDK, chọn **Add JDK from Disk** và trỏ đến thư mục cài đặt; hoặc tải JDK từ hộp thoại **Download JDK**.
3. Trong **Language level**, chọn **27 – No new language features** cho mã nguồn Java 27 thông thường.
4. Mở phần **Modules** và bảo đảm module sử dụng Project SDK hoặc một SDK phù hợp với cấu hình build của module.
5. Kiểm tra cấu hình Run/Debug để tiến trình ứng dụng sử dụng đúng JDK của dự án.
6. Nếu dự án dùng Maven hoặc Gradle, đồng bộ lại dự án sau khi cập nhật build file để IDE nhận cấu hình mới.

Với một dự án Java 27 thông thường, lựa chọn Language level 27 tiêu chuẩn là đủ. IntelliJ IDEA mô tả mức này là không có tính năng ngôn ngữ mới trong bản phát hành; các tính năng ngôn ngữ mới vẫn đang ở trạng thái preview phải được bật riêng. Không chọn mức Preview chỉ để loại bỏ cảnh báo của IDE.

Không nhầm Project SDK với runtime dùng để khởi động IntelliJ IDEA. Thay đổi runtime nội bộ của IDE không phải cách cấu hình phiên bản Java của ứng dụng.

### 3.2. Eclipse IDE

Eclipse 2026-09 (4.41) cung cấp hỗ trợ Java 27 qua gói **Java 27 Support for Eclipse 2026-09 (4.41)**. Nếu chưa thấy JavaSE-27 trong danh sách execution environment, hãy cài gói hỗ trợ từ Eclipse Marketplace hoặc update site do Eclipse công bố:

~~~~text
https://download.eclipse.org/jdt/updates/4.41-P-builds/
~~~~

Sau khi cài:

1. Mở **Window → Preferences → Java → Installed JREs**.
2. Thêm JDK 27 bằng cách chọn thư mục JDK, sau đó đánh dấu bản JDK cần dùng nếu muốn đặt làm mặc định cho workspace.
3. Mở **Project → Properties → Java Build Path → Libraries** và kiểm tra **JRE System Library** của dự án. Chọn execution environment **JavaSE-27** hoặc JDK 27 tương ứng.
4. Mở **Project → Properties → Java Compiler** và đặt mức compiler compliance là 27.
5. Nếu dự án Maven hoặc Gradle, làm mới cấu hình dự án từ build descriptor sau khi cập nhật cấu hình build.

Trang Eclipse Marketplace xác nhận gói hỗ trợ có trạng thái Production/Stable và có thể kiểm tra cài đặt bằng cách tạo dự án Java với execution environment mặc định là JavaSE-27. Không dùng một bản Eclipse cũ rồi chỉ thay JDK trên máy để kỳ vọng editor hiểu toàn bộ cú pháp Java 27.

### 3.3. Visual Studio Code

Với VS Code, cài Extension Pack for Java hoặc Java extension phù hợp. Java extension hiện hỗ trợ mã nguồn đến Java 27. Để ánh xạ JDK đã cài vào workspace, mở Settings JSON và thêm cấu hình sau; thay đường dẫn ví dụ bằng đường dẫn thật trên máy:

~~~~json
{
  "java.configuration.runtimes": [
    {
      "name": "JavaSE-27",
      "path": "C:\\Java\\jdk-27",
      "default": true
    }
  ]
}
~~~~

Thuộc tính **name** phải nhận diện đúng execution environment; **path** phải trỏ đến thư mục gốc của JDK, không phải thư mục **bin**. Có thể khai báo nhiều JDK trong mảng này nếu máy cần mở các dự án dùng những phiên bản Java khác nhau. Chỉ đặt một runtime làm mặc định cho các thư mục Java độc lập không được quản lý bởi Maven hoặc Gradle.

Với dự án có **pom.xml** hoặc **build.gradle**, build descriptor mới là nơi cần khai báo phiên bản biên dịch và toolchain. Sau khi chỉnh sửa build file, chạy lệnh **Java: Reload Projects** từ Command Palette để Java Language Server nạp lại cấu hình. JDK chạy Java Language Server là một thành phần riêng; các bản extension theo nền tảng có thể đóng gói runtime cho dịch vụ này, còn JDK dự án vẫn phải được khai báo riêng.

## 4. Đặt cấu hình build làm nguồn thống nhất

Thiết lập SDK và Language level giúp IDE hiểu mã nguồn, nhưng build file mới quyết định cách compiler chạy trên máy lập trình viên và CI. Hãy ghi phiên bản Java vào cấu hình được quản lý cùng mã nguồn, sau đó để IDE import hoặc đồng bộ từ cấu hình đó.

### 4.1. Dự án Gradle

Gradle 9.8.0 trở lên hỗ trợ Java 27 cho cả Gradle daemon và Java toolchains. Có thể khai báo toolchain và giới hạn API biên dịch trong **build.gradle.kts**:

~~~~kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(27)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 27
}
~~~~

Hai cấu hình trên có vai trò riêng:

- **toolchain** yêu cầu Gradle chọn JDK 27 cho các tác vụ Java được hỗ trợ, chẳng hạn biên dịch và kiểm thử.
- **options.release** yêu cầu compiler biên dịch theo Java SE 27: kiểm tra cú pháp, API Java SE và tạo class file phù hợp với release đó.

Nếu dự án dùng Gradle Groovy DSL (**build.gradle**), cấu hình tương đương là:

~~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(27)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 27
}
~~~~

Nếu ứng dụng phải chạy trên Java 25 LTS, có thể giữ toolchain JDK 27 nhưng đặt **options.release = 25**, miễn là các tác vụ và thư viện liên quan tương thích với lựa chọn đó. Khi đó compiler sẽ giới hạn mã nguồn và API theo Java 25. Cấu hình **release** không tự chọn JVM chạy ứng dụng hoặc test; hãy bổ sung test job hoặc cấu hình launcher dùng JDK 25 để xác minh hành vi trên đúng runtime triển khai. Không đặt **release** cao hơn phiên bản JDK thực tế được dùng làm compiler.

Gradle daemon là tiến trình thực thi Gradle; toolchain là JDK dành cho tác vụ của dự án. Hai phiên bản này có thể được quản lý riêng. Kiểm tra phiên bản wrapper và khả năng tương thích trước khi nâng JDK chạy daemon. Theo ma trận tương thích hiện hành, Java 27 được hỗ trợ để chạy Gradle từ 9.8.0; Gradle 9.8.0 cũng công bố hỗ trợ Java 27 cho daemon và toolchain. Xem [Gradle Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html), [Gradle Toolchains](https://docs.gradle.org/current/userguide/toolchains.html) và [Gradle 9.8.0 Release Notes](https://docs.gradle.org/9.8.0/release-notes.html).

Đối với dự án dùng Gradle Wrapper, hãy kiểm tra phiên bản trong **gradle/wrapper/gradle-wrapper.properties** và cập nhật wrapper theo quy trình nâng cấp của dự án. Wrapper giúp các máy phát triển và CI sử dụng cùng phiên bản Gradle. Việc Gradle hỗ trợ Java 27 cũng không bảo đảm mọi plugin bên thứ ba đã hỗ trợ JDK này; cần kiểm tra riêng plugin tham gia build, phân tích mã nguồn hoặc kiểm thử.

### 4.2. Dự án Maven

Với Maven, đặt phiên bản biên dịch bằng thuộc tính **maven.compiler.release** và chỉ định phiên bản Maven Compiler Plugin rõ ràng trong **pom.xml**. Ví dụ dùng JDK 27 để biên dịch ứng dụng Java 27:

~~~~xml
<properties>
    <maven.compiler.release>27</maven.compiler.release>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.16.0</version>
        </plugin>
    </plugins>
</build>
~~~~

**release** truyền lựa chọn tương ứng đến compiler, giúp compiler kiểm soát cả quy tắc ngôn ngữ, API Java SE có thể sử dụng và định dạng bytecode. Vì thế, nó phù hợp hơn với việc chỉ đặt riêng mức ngôn ngữ và phiên bản bytecode. Plugin 3.16.0 là phiên bản ổn định hiện được Apache Maven công bố trên trang Compiler Plugin; hãy tiếp tục kiểm tra trang plugin khi nâng cấp build.

Theo mặc định, Maven Compiler Plugin sử dụng **javac** thuộc JDK đang chạy Maven. Nếu Maven chạy bằng JDK khác với JDK muốn dùng để biên dịch, hãy cấu hình Maven Toolchains để chọn compiler JDK phù hợp. Điều này đặc biệt hữu ích khi IDE khởi động Maven bằng một runtime riêng hoặc nhóm có nhiều dự án dùng các JDK khác nhau. Tham khảo [Maven Guide to Targeting a Java Version](https://maven.apache.org/guides/mini/guide-java-target.html), [Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/) và [Maven Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains).

Trong IntelliJ IDEA hoặc Eclipse, sau khi thay đổi **pom.xml**, hãy reload Maven project. Trong VS Code, chạy **Java: Reload Projects** hoặc thao tác cập nhật Maven project. Khi dự án được import đúng, IDE sẽ lấy cấu hình compiler từ Maven và hạn chế việc phải duy trì hai bộ thiết lập độc lập.

### 4.3. Vì sao cần phân biệt JDK chạy build và JDK biên dịch

Giả sử Maven được khởi động bằng JDK 25 nhưng dự án yêu cầu biên dịch bằng JDK 27. Chỉ đặt **maven.compiler.release** thành 27 không làm JDK 25 có thêm compiler Java 27. Hãy chọn JDK 27 bằng Maven Toolchains hoặc chạy Maven bằng JDK 27.

Tương tự, Gradle có thể chạy daemon trên một JDK được hỗ trợ và dùng toolchain riêng cho tác vụ compile/test. Gradle khuyến nghị toolchains để chỉ rõ JDK của dự án, đồng thời khuyến nghị **--release** khi cần biên dịch chéo nghiêm ngặt. **release** không chọn JDK; toolchain mới quyết định compiler JDK được sử dụng.

## 5. Khi nào cần bật tính năng preview của Java 27?

Mặc định hãy dùng mức ngôn ngữ Java 27 tiêu chuẩn. Tính năng preview chỉ dành cho việc thử nghiệm những tính năng chưa trở thành một phần ổn định của ngôn ngữ. Trong Java 27, IntelliJ IDEA 2026.3 hiển thị mức **27 (Preview)** cho tính năng *Primitive types in patterns, instanceof, and switch (fifth preview)*. Không nên bật preview cho dự án nếu mã nguồn không dùng tính năng này.

Preview phải được bật ở cả giai đoạn biên dịch và lúc chạy chương trình. Compiler và JVM cần đến từ cùng bản phát hành Java có preview tương ứng. Ví dụ, biên dịch mã Java 27 dùng preview bằng:

~~~~bash
javac --enable-preview --release 27 Example.java
java --enable-preview Example
~~~~

Nếu dùng Gradle, cấu hình compiler, test JVM và JavaExec:

~~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("--enable-preview")
}

tasks.withType<Test>().configureEach {
    jvmArgs("--enable-preview")
}

tasks.withType<JavaExec>().configureEach {
    jvmArgs("--enable-preview")
}
~~~~

Nếu dùng Maven Compiler Plugin, thuộc tính sau bật preview trong compiler:

~~~~xml
<properties>
    <maven.compiler.release>27</maven.compiler.release>
    <maven.compiler.enablePreview>true</maven.compiler.enablePreview>
</properties>
~~~~

Tiến trình chạy ứng dụng, test hoặc công cụ thực thi Maven cũng phải nhận VM option **--enable-preview**. Ví dụ, khi chạy trực tiếp bằng Java, thêm option này vào lệnh **java**; khi chạy từ IDE, thêm vào VM options của Run/Debug Configuration; khi chạy test bằng Maven, cấu hình VM arguments của test runner tương ứng. Nếu dự án đã có **argLine** hoặc JVM arguments khác, hãy ghép thêm option thay vì ghi đè các tham số hiện tại.

Preview có thể thay đổi hoặc bị loại bỏ ở những phiên bản sau. Class file phụ thuộc preview của một release bị ràng buộc với release đó, vì vậy không nên xem mã đã biên dịch với preview là đầu ra tương thích lâu dài. Gradle cũng khuyến nghị hạn chế preview trong thử nghiệm và tránh phát hành thư viện dùng preview cho người tiêu thụ rộng rãi. Xem [Oracle Preview Features](https://docs.oracle.com/en/java/javase/27/language/preview-language-vm-features.html) và [Gradle: Enabling Java Preview Features](https://docs.gradle.org/current/userguide/building_java_projects.html).

## 6. Đồng bộ IDE, build tool và môi trường chạy

Sau khi cấu hình, thực hiện kiểm tra theo thứ tự dưới đây:

1. **Kiểm tra JDK cài đặt:** chạy **java -version** và **javac -version** trong terminal.
2. **Kiểm tra JVM chạy build tool:** chạy **./gradlew -version** hoặc **./mvnw -v** để xem JVM mà Gradle/Maven đang sử dụng. Trên Windows PowerShell, dùng **.\gradlew.bat -version** hoặc **.\mvnw.cmd -v**.
3. **Kiểm tra toolchain và release:** xem lại **toolchain** và **options.release** trong Gradle, hoặc **maven.compiler.release** và Maven Toolchains trong Maven.
4. **Đồng bộ IDE:** reload Gradle/Maven project để IDE nạp lại cấu hình từ build file.
5. **Kiểm tra cấu hình chạy:** xác nhận Run/Debug và test runner sử dụng JDK tương thích với dự án; nếu dùng preview, các tiến trình này cũng phải nhận **--enable-preview**.
6. **Build từ terminal:** chạy tác vụ build mà dự án sử dụng, ví dụ **./gradlew clean test** hoặc **./mvnw clean verify**. Đây là bước xác nhận cấu hình được quản lý trong repository hoạt động ngoài IDE.

Khi nhóm làm việc qua nhiều máy, hãy ưu tiên commit Gradle Wrapper hoặc Maven Wrapper và cấu hình phiên bản Java của dự án vào repository. Không nên dựa vào một JDK mặc định chỉ có trên máy cá nhân, vì CI hoặc máy của đồng đội có thể chọn một phiên bản khác.

## 7. Xử lý các lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| IDE nhận cú pháp Java 27 nhưng build báo không hỗ trợ release 27 | Compiler thực tế vẫn chạy bằng JDK cũ | Kiểm tra JVM của Maven/Gradle và JDK toolchain; chọn compiler JDK 27 |
| Terminal build thành công nhưng IDE báo lỗi cú pháp | IDE chưa hỗ trợ Java 27 hoặc project model chưa được đồng bộ | Cập nhật IDE/Java extension có hỗ trợ Java 27 rồi reload Maven/Gradle project |
| Gradle không khởi động được bằng JDK 27 | Gradle Wrapper chưa đạt phiên bản hỗ trợ chạy trên Java 27 | Dùng Gradle Wrapper 9.8.0 trở lên và kiểm tra tương thích của các plugin |
| Ứng dụng biên dịch được nhưng chạy lỗi trên Java 25 | Build cho phép dùng API mới hơn môi trường triển khai | Đặt **release** thành 25 và biên dịch bằng JDK/toolchain có thể tạo target đó |
| Mã preview biên dịch được nhưng chạy thất bại | JVM chạy ứng dụng hoặc test chưa bật preview, hoặc dùng sai phiên bản JDK | Bật **--enable-preview** ở tiến trình chạy và dùng đúng JDK 27 |
| IDE và terminal hiển thị hai phiên bản Java khác nhau | Project SDK, runtime của build tool và PATH đang trỏ đến các JDK khác nhau | Đối chiếu Project SDK, Maven/Gradle JVM, toolchain và kết quả các lệnh kiểm tra |
| Build máy cá nhân chạy nhưng CI thất bại | Máy cá nhân có JDK hoặc plugin mà CI chưa có, hoặc wrapper/build file chưa cố định phiên bản | Đưa wrapper và cấu hình toolchain/release vào repository; dùng cùng cấu hình trong CI |

Không xử lý lỗi bằng cách tăng Language level một cách tùy ý. Hãy đọc thông báo lỗi để xác định compiler nào đang chạy, release nào đang được yêu cầu và tiến trình nào đang khởi động ứng dụng.

## 8. Checklist cấu hình cho dự án Java 27

- [ ] Máy phát triển đã cài một JDK 27 được tổ chức hoặc dự án chấp nhận.
- [ ] IDE đang dùng bản hỗ trợ Java 27.
- [ ] Project SDK/Project JDK trỏ đến đúng JDK.
- [ ] Language level là Java 27 tiêu chuẩn; chỉ bật Preview khi mã nguồn có yêu cầu rõ ràng.
- [ ] Gradle Wrapper hoặc Maven Wrapper được cố định trong repository.
- [ ] Build file khai báo toolchain và phiên bản release đúng với môi trường triển khai.
- [ ] Gradle Wrapper dùng phiên bản hỗ trợ chạy trên JDK 27 nếu daemon chạy bằng JDK 27.
- [ ] Maven Compiler Plugin được chỉ định phiên bản rõ ràng và Maven Toolchains được cấu hình nếu compiler JDK khác JVM chạy Maven.
- [ ] IDE đã reload dự án sau khi thay đổi build file.
- [ ] Run/Debug và test runner dùng JDK phù hợp; nếu dùng preview, đã bật preview ở cả compile và runtime.
- [ ] Build từ terminal thành công bằng wrapper của dự án.

Khi các điểm trên thống nhất, IDE, build tool và CI sẽ biên dịch mã nguồn theo cùng một hợp đồng phiên bản Java. Điều này giúp tránh lỗi chỉ xuất hiện trên một máy và giúp nhóm kiểm soát chính xác việc sử dụng tính năng Java 27 trong toàn bộ vòng đời phát triển.

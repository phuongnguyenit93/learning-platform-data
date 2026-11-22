# Phân biệt `sourceCompatibility`, `targetCompatibility` và `--release` trong Java

Khi cấu hình Java cho dự án dùng Gradle, Maven hoặc Spring Boot, ba tên `sourceCompatibility`, `targetCompatibility` và `--release` thường xuất hiện cạnh một con số như `8`, `11`, `17` hoặc `21`. Chúng liên quan đến phiên bản Java nhưng **kiểm soát các khía cạnh khác nhau**. Hiểu sai có thể dẫn đến tình huống: build báo thành công, file `.class` trông như dành cho Java 8, nhưng triển khai trên Java 8 lại lỗi.

Bài học thuộc chủ đề **Java và Wrapper** trong **Spring Boot Build Tooling Packaging**. Trọng tâm là lựa chọn và kiểm chứng phiên bản Java của mã nguồn, bytecode, API nền tảng và công cụ build; đặc biệt là hậu quả khi biên dịch bằng JDK mới để chạy trên JVM cũ.

## 1. Tách bốn khái niệm dễ bị trộn lẫn

Trước khi xem cấu hình, cần phân biệt:

1. **Phiên bản ngôn ngữ Java (source level)** quyết định cú pháp được phép viết: `var` (Java 10), `record` (Java 16), pattern matching và các đặc tính khác theo phiên bản.
2. **Phiên bản bytecode (class-file target)** quyết định JVM tối thiểu có thể đọc định dạng của file `.class`. Ví dụ, Java 8 dùng class-file major version **52**, Java 17 dùng **61**.
3. **Tập API nền tảng có thể gọi** quyết định mã có được tham chiếu những phương thức/lớp Java SE/JDK xuất hiện trong bản phát hành mục tiêu hay không. `String.repeat(int)` chỉ có từ Java 11; một chương trình dùng API này không thể hoạt động đúng trên Java 8, dù bytecode được tạo ở mức 8.
4. **JDK thật dùng để biên dịch** cung cấp phiên bản `javac` và môi trường build; còn **JVM thật dùng để chạy** cung cấp runtime. Hai phiên bản có thể khác nhau.

Một phép so sánh ngắn:

| Thiết lập | Kiểm soát chính | Chưa bảo đảm điều gì? |
| --- | --- | --- |
| Gradle `sourceCompatibility = 8` | Cú pháp Java 8 trong source, tương ứng `javac -source 8` | Không giới hạn API của JDK mới, không chọn JDK biên dịch |
| Gradle `targetCompatibility = 8` | Định dạng class file cho JVM Java 8, tương ứng `javac -target 8` | Không bảo đảm mọi API và thư viện đều tồn tại trên Java 8 |
| `javac --release 8` / Gradle `options.release = 8` | Đồng thời giới hạn cú pháp, class-file target và **API Java SE/JDK được hỗ trợ** theo bản phát hành 8 | Không lựa chọn JDK chạy `javac`, không tự kiểm tra toàn bộ dependency bên thứ ba và môi trường runtime |
| Gradle **Java toolchain 17** | Chọn công cụ JDK 17 dùng cho task Java tương ứng | Nếu muốn bảo đảm API nền tảng của một bản Java **cũ hơn 17**, vẫn cần `--release` hoặc cách kiểm soát tương đương |

Ghi nhớ: **`sourceCompatibility` trả lời “viết cú pháp nào?”; `targetCompatibility` trả lời “tạo bytecode cho JVM nào?”; `--release` trả lời “biên dịch như thể đang nhắm đến phiên bản Java nào, kể cả API nền tảng?”**. Toolchain trả lời một câu hỏi khác: **“Dùng JDK nào để thực sự biên dịch/chạy các task?”**

## 2. `sourceCompatibility`: giới hạn cú pháp Java

Trong Gradle Java plugin, thuộc tính `sourceCompatibility` quy định ngôn ngữ nguồn Java mà trình biên dịch phải chấp nhận. Một ví dụ Groovy DSL trong `build.gradle`:

```groovy
java {
    sourceCompatibility = JavaVersion.VERSION_17
}
```

Ở mức `javac`, ý nghĩa gần tương ứng:

```bash
javac -source 17 Hello.java
```

Nếu chọn Java 8, bạn không thể dùng cú pháp `record` được giới thiệu từ Java 16. Tuy nhiên, **ngôn ngữ Java 8 vẫn có thể gọi API xuất hiện ở Java 11** khi biên dịch bằng JDK mới và chỉ đặt `-source 8`: cú pháp và API là hai vấn đề khác nhau.

`sourceCompatibility` **không cài đặt/chọn JDK 17**. Nếu máy chạy Gradle với JDK không hỗ trợ source level được yêu cầu, task biên dịch có thể thất bại. Thứ quyết định compiler nào được sử dụng là cấu hình toolchain hoặc môi trường thực thi build.

Không nhầm `sourceCompatibility` với đường dẫn `src/main/java`: `src/main/java` là nơi đặt mã nguồn; `sourceCompatibility` là phiên bản cú pháp mã nguồn được phép dùng.

## 3. `targetCompatibility`: định dạng bytecode, chưa phải khả năng chạy hoàn chỉnh

Thuộc tính `targetCompatibility` của Gradle đặt phiên bản class file mà compiler tạo ra; tương ứng với `javac -target`. Ví dụ:

```groovy
java {
    targetCompatibility = JavaVersion.VERSION_17
}
```

Một số class-file major version thường gặp:

| Java | Major version |
| --- | ---: |
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |

Nếu JVM Java 8 gặp class file major 61, nó không đọc được định dạng bytecode đó và thường phát sinh `UnsupportedClassVersionError`. Tuy nhiên, chiều ngược lại **không đủ**: class file major 52 có thể chứa lời gọi đến phương thức chỉ tồn tại từ Java 11. JVM Java 8 đọc được file nhưng lỗi khi cần liên kết lời gọi đó.

Với `javac`, **target phải không thấp hơn source**; đòi source 17 nhưng target 8 là cấu hình không hợp lệ. Cấu hình source 8/target 17 có thể mang ý nghĩa kỹ thuật trong vài trường hợp nhưng gây nhầm lẫn và không giúp hỗ trợ JVM 8. Thông thường nên nhắm cùng một phiên bản trừ khi có yêu cầu riêng đã được kiểm chứng.

Lưu ý: `targetCompatibility` chỉ tác động đến class do task tương ứng biên dịch. Nó **không hạ phiên bản bytecode của thư viện phụ thuộc** và không biến toàn bộ JAR ứng dụng thành sản phẩm có thể chạy trên JVM cũ.

## 4. `--release`: chốt cú pháp, bytecode **và** API nền tảng

Kể từ JDK 9, `javac` cung cấp tùy chọn `--release` để nhắm đến một bản Java đã được compiler hỗ trợ:

```bash
javac --release 8 Hello.java
```

Khi yêu cầu `--release 8`, compiler đồng thời:

1. Chỉ chấp nhận các đặc tính ngôn ngữ phù hợp Java 8.
2. Tạo class file theo phiên bản bytecode Java 8 (major 52).
3. Kiểm tra tham chiếu tới các API Java SE/JDK được hỗ trợ ở Java 8; từ chối API nền tảng chỉ tồn tại ở các bản mới hơn.

Điểm thứ ba là phần **`-source` + `-target` không tự đảm bảo**. Compiler dùng thông tin API của bản phát hành mục tiêu, nên phát hiện sớm lỗi có thể chỉ xuất hiện khi chạy trên JVM cũ. `--release` không cấp quyền truy cập API nội bộ/không được hỗ trợ của JDK mục tiêu.

Trong lời gọi trực tiếp tới `javac`, **không dùng `--release` đồng thời với `-source` hoặc `-target`**; chúng là hai cách chỉ định mức tương thích thay thế nhau. Với Gradle, ưu tiên cấu hình `options.release` cho task compile thay vì cố ghép các thiết lập trùng mục đích. Phiên bản `--release` được hỗ trợ phụ thuộc JDK thực tế; dùng `javac --help` để xem danh sách compiler đang có hỗ trợ.

**Giới hạn quan trọng:** `--release` bảo vệ tương thích API của **nền tảng Java** khi biên dịch mã, chứ không chứng minh rằng các thư viện ngoài, reflection, JNI, tài nguyên hệ điều hành hoặc cách chạy thực tế đều tương thích với bản Java mục tiêu.

## 5. Thí nghiệm 1: class file Java 8 nhưng vẫn gọi API Java 11

Thí nghiệm này chạy bằng **JDK 17** (hoặc một JDK mới có hỗ trợ mục tiêu 8). Không cần Spring Boot, Maven hay Gradle để thấy bản chất lỗi.

Tạo file `ApiTrap.java`:

```java
public class ApiTrap {
    public static void main(String[] args) {
        System.out.println("ha".repeat(2));
    }
}
```

`String.repeat(int)` là API của `java.lang.String` được thêm từ Java 11. Cú pháp gọi phương thức thông thường vẫn hợp lệ ở source level 8.

### 5.1. Biên dịch bằng cách cũ

```bash
javac -source 8 -target 8 ApiTrap.java
java ApiTrap
```

Khi dùng JDK 17, lệnh biên dịch có thể đưa ra **cảnh báo** về bootclasspath, nhưng mã thường biên dịch được vì compiler nhìn thấy `String.repeat` từ thư viện nền tảng của JDK 17. Chạy bằng Java 17 in chính xác:

```text
haha
```

Kiểm tra bytecode:

```bash
javap -verbose ApiTrap
```

Trong kết quả có dòng:

```text
major version: 52
```

Đây là bằng chứng class file dùng định dạng Java 8; **không** phải bằng chứng mã hoạt động trên Java 8. Nếu chạy file `ApiTrap.class` này bằng JVM Java 8, khi thực hiện lời gọi `String.repeat` sẽ xảy ra lỗi liên kết như `java.lang.NoSuchMethodError` vì `String` của Java 8 không có phương thức đó. Tình huống “bytecode đúng phiên bản nhưng API sai phiên bản” chính là lỗ hổng của `sourceCompatibility` + `targetCompatibility`.

### 5.2. Biên dịch bằng `--release`

Giữ nguyên `ApiTrap.java` và chạy:

```bash
javac --release 8 ApiTrap.java
```

Compiler trên JDK 17 **từ chối biên dịch** vì không tìm thấy `String.repeat(int)` trong API của Java 8. Đây là lỗi được phát hiện sớm, ngay trong build. Nội dung chẩn đoán chính của `javac` tương đương:

```text
cannot find symbol
  symbol:   method repeat(int)
  location: class java.lang.String
```

Vị trí dòng và định dạng cảnh báo/lỗi có thể thay đổi theo JDK. Vì một lần biên dịch **thất bại có thể để lại file `.class` từ lần thành công trước**, không chạy nhầm artifact cũ để kết luận `--release` đã thành công; hãy xóa output cũ hoặc dùng thư mục build sạch khi thử nghiệm.

### 5.3. Ví dụ có thể biên dịch và chạy thật trên Java 8

Tạo file `HelloRelease.java`:

```java
public class HelloRelease {
    public static void main(String[] args) {
        System.out.println("Hello Java 8");
    }
}
```

Biên dịch và chạy bằng JDK 17:

```bash
javac --release 8 HelloRelease.java
java HelloRelease
```

Stdout chính xác:

```text
Hello Java 8
```

`javap -verbose HelloRelease` cũng cho thấy `major version: 52`. Vì chương trình chỉ dùng API và cú pháp có trong Java 8, class này **có thể** chạy bằng Java 8 nếu sử dụng một JVM Java 8 bình thường. Để khẳng định toàn bộ ứng dụng thực tế tương thích, vẫn phải chạy kiểm thử trên JVM mục tiêu và kiểm tra các dependency.

## 6. Cấu hình đúng trong Gradle

Dự án dùng **Gradle Wrapper** nên chạy bằng `./gradlew` (macOS/Linux) hoặc `.\gradlew.bat` (Windows PowerShell) để mọi máy dùng Gradle theo cấu hình của dự án. **Wrapper pin phiên bản Gradle**, không tự bảo đảm phiên bản JDK mà Gradle hoặc compiler dùng.

Các ví dụ dưới đây là những đoạn cấu hình thay thế theo mục tiêu; **không ghép tất cả vào cùng một build file**. Giữ nguyên các plugin và dependency đang có trong `build.gradle`, và chỉ thêm/cập nhật khối cần thiết.

### 6.1. Cách cũ: `sourceCompatibility` + `targetCompatibility`

Ví dụ Gradle Groovy DSL:

```groovy
java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}
```

Cấu hình này thường tạo mã Java 17 từ compiler đủ mới, nhưng không pin JDK biên dịch và không mang bảo đảm API của bản Java thấp hơn khi compiler mới hơn mục tiêu. Nó vẫn xuất hiện trong nhiều dự án cũ và cần hiểu đúng khi đọc build file.

### 6.2. Cách nên dùng cho ứng dụng Spring Boot chạy Java 17

Cấu hình Gradle Groovy DSL trong dự án đã áp dụng Java plugin (trực tiếp hoặc thông qua cấu hình build tương ứng):

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

Ý nghĩa:

- **Toolchain 17:** Gradle tìm/sử dụng compiler và công cụ Java 17 cho các task tương ứng. Nếu máy không có JDK phù hợp và không cấu hình nguồn tự tải toolchain, build sẽ báo thiếu toolchain.
- **`options.release = 17`:** các task `JavaCompile` sử dụng mức ngôn ngữ, bytecode và API nền tảng Java 17. Cách viết `tasks.withType(JavaCompile)` áp dụng cho cả task compile Java chính và các task compile Java khác phù hợp, bao gồm test nếu có.
- **Runtime deploy:** máy/container chạy ứng dụng vẫn phải có phiên bản JVM tương thích với **tất cả** class và dependency trong artifact.

Trong dự án có toolchain 17 và không nhắm phiên bản thấp hơn, toolchain thường đã đủ giúp build nhất quán. Ghi `options.release = 17` thể hiện rõ baseline API và giúp người đọc thấy chủ ý. Không nhất thiết phải khai báo thêm `sourceCompatibility` và `targetCompatibility` cho cùng mục tiêu.

### 6.3. Compiler Java 21, nhưng sản phẩm thư viện hướng tới Java 17

Ví dụ một **thư viện Java thường**, khi cần compiler JDK 21 nhưng API/classfile mục tiêu là Java 17:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.named('compileJava', JavaCompile) {
    options.release = 17
}
```

Ở đây: **JDK 21 là công cụ**, **Java 17 là hợp đồng tương thích của class do `compileJava` tạo ra**. Việc giới hạn riêng `compileJava` cho phép test hoặc một task khác có cấu hình riêng nếu cần; kiểm thử trên Java 17 vẫn phải được thiết lập có chủ đích. Compiler JDK 21 không thể tạo output hợp lệ cho một phiên bản `--release` mà chính compiler không hỗ trợ.

Không nên hạ `options.release` xuống 8 hoặc 11 cho một ứng dụng **Spring Boot 3.x** chỉ vì muốn chạy JVM cũ: Spring Boot 3.x yêu cầu tối thiểu Java 17. Lớp ứng dụng có major version 52 không làm các thư viện Spring Boot 3.x chạy được trên JVM 8.

### 6.4. So sánh với Kotlin DSL (`build.gradle.kts`)

Nếu dự án dùng Kotlin DSL, cú pháp tương ứng là:

```kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 17
}
```

Cả hai DSL đều cấu hình API Gradle tương đương. Đừng copy nguyên cú pháp `JavaVersion.VERSION_17` trong Groovy DSL sang vị trí không đúng của Kotlin DSL rồi cho rằng Gradle tự chuyển đổi.

## 7. Maven: `maven.compiler.source`, `target` và `release`

Trong Maven, khái niệm tương ứng được Maven Compiler Plugin truyền cho `javac`. Tên property khác tên trong Gradle:

| Ý nghĩa | Gradle (Java plugin) | Maven Compiler Plugin |
| --- | --- | --- |
| Cú pháp nguồn | `sourceCompatibility` | `maven.compiler.source` |
| Phiên bản bytecode | `targetCompatibility` | `maven.compiler.target` |
| Giới hạn cú pháp + bytecode + API nền tảng | `options.release` | `maven.compiler.release` |

Ví dụ Maven trong `pom.xml` khi nhắm Java 17:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Maven Compiler Plugin phiên bản phù hợp sẽ dùng `--release 17` với compiler hỗ trợ. Khi dùng các plugin cũ, compiler không phải `javac` hoặc chạy trên JDK quá cũ, hành vi có thể khác; hãy kiểm tra phiên bản plugin và lệnh compiler thực tế.

Cách truyền thống:

```xml
<properties>
    <maven.compiler.source>17</maven.compiler.source>
    <maven.compiler.target>17</maven.compiler.target>
</properties>
```

Nó có hạn chế tương tự `-source`/`-target`. Trên JDK 9+, ưu tiên `release` khi cần đảm bảo API Java đích. Trong lời gọi trực tiếp `javac` không kết hợp `--release` với `-source`/`-target`. Với Maven, tránh đặt song song cả ba property nếu không có lý do được xác minh theo phiên bản plugin cụ thể.

Lệnh kiểm tra build:

```bash
# macOS / Linux
./mvnw clean verify

# Windows PowerShell
.\mvnw.cmd clean verify
```

**Maven Wrapper** chọn phiên bản Maven; **Maven Toolchains Plugin** (nếu cấu hình) có thể giúp chọn JDK cho compiler. Wrapper Maven, giống wrapper Gradle, không tự đặt API target hoặc tự tải đúng Java runtime cho ứng dụng.

## 8. Vì sao vẫn cần phân biệt Toolchain, Wrapper, `JAVA_HOME` và runtime?

Bốn đối tượng có thể mang bốn phiên bản khác nhau:

| Thành phần | Nó quyết định | Cách kiểm tra/chỉnh thông dụng |
| --- | --- | --- |
| Gradle Wrapper | Phiên bản **Gradle** chạy build | `gradle/wrapper/gradle-wrapper.properties`; `./gradlew --version` |
| Maven Wrapper | Phiên bản **Maven** chạy build | `.mvn/wrapper/maven-wrapper.properties` hoặc cấu hình Wrapper tương ứng; `./mvnw -version` |
| JDK/toolchain biên dịch | Compiler `javac` thật dùng trong task | `java.toolchain` trong Gradle; Maven toolchains/compiler config |
| `--release` / `options.release` | Mục tiêu cú pháp, bytecode và API nền tảng | `javac --release` hoặc cấu hình task/compiler plugin |
| JVM chạy production | Runtime giải nạp và thực thi class | `java -version` trên host/container triển khai; image/base runtime |

`JAVA_HOME` thường ảnh hưởng JDK dùng để khởi động build tool khi không có cơ chế lựa chọn riêng. Nhưng Gradle Daemon, toolchain, thiết lập IDE và cấu hình CI có thể chọn JVM/JDK khác với cửa sổ terminal. Vì vậy **`java -version` không chứng minh task `compileJava` đang dùng đúng JDK**.

Trong dự án Gradle, có thể khảo sát môi trường bằng:

```bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew clean compileJava --info
```

Trên Windows đổi `./gradlew` thành `.\gradlew.bat`. Tên task `javaToolchains` và thông tin log tùy Gradle, plugin và phiên bản; quan sát đầu ra thực tế để biết các installation/toolchain được phát hiện và compiler mà task dùng. Nếu JDK cần thiết không được cài đặt hoặc không được cấu hình cơ chế provisioning, đừng mong `options.release` tự cung cấp JDK đó.

Quy tắc áp dụng trong CI/CD: chọn rõ **Gradle/Maven version**, **compiler JDK**, **release target**, **runtime image JDK**, sau đó kiểm tra toàn bộ chuỗi bằng build và bài test trên runtime mục tiêu. Java compile target không thay thế bước chọn đúng runtime.

## 9. Kiểm chứng bằng bytecode, API và chạy thực tế

Một quy trình kiểm tra hữu ích hơn việc chỉ nhìn file cấu hình:

**Bước 1 — Xác nhận compiler và release target.** Xem cấu hình Java toolchain hoặc Maven compiler và quan sát log task biên dịch. Khi gọi `javac` trực tiếp, chạy `javac -version` rồi `javac --help` để xem release khả dụng.

**Bước 2 — Xác nhận bytecode.** Với class Java tự biên dịch, dùng:

```bash
javap -verbose HelloRelease
```

Tìm `major version`: 52 là Java 8, 55 là Java 11, 61 là Java 17, 65 là Java 21. `javap` nên chạy với class file đúng từ thư mục output của lần build mới nhất; nếu có nhiều bản cùng tên trên classpath, hãy cung cấp đường dẫn class thực tế hoặc dùng `-classpath` phù hợp.

**Bước 3 — Kiểm tra API Java nền tảng.** Thử biên dịch bằng `--release <phiên-bản-mục-tiêu>`; đối với Gradle, kiểm tra `options.release`; với Maven, kiểm tra `maven.compiler.release`. Tránh kết luận API hợp lệ chỉ từ major version của class.

**Bước 4 — Kiểm tra dependency.** Một thư viện ngoài biên dịch bằng Java 21 có thể có class major 65; dù mã của bạn được biên dịch với `--release 17`, JVM Java 17 vẫn không chạy được dependency Java 21. Kiểm tra yêu cầu Java tối thiểu của từng dependency/plugin chính và artifact cuối.

**Bước 5 — Chạy trên JVM đích.** Chạy unit/integration tests và bản đóng gói trên JVM phù hợp (ví dụ JDK/JRE 17). Các đường chạy thông qua reflection, thư viện native hoặc tính năng chỉ kích hoạt khi runtime có thể không lộ ra ở bước compile. Đừng coi `compileJava` thành công là đủ để chứng minh tương thích triển khai.

Khi thay đổi cấu hình target, chạy **build sạch** để tránh class cũ lẫn vào kết luận:

```bash
# Gradle
./gradlew clean test bootJar

# Maven
./mvnw clean verify
```

Lệnh `bootJar` dành cho dự án Spring Boot có task/plugin tạo executable JAR; không phải mọi dự án thư viện Java đều có task đó. File output sẽ nằm trong `build/libs/` hoặc `target/` theo công cụ và plugin thực tế.

## 10. Chọn cấu hình theo tình huống

| Tình huống | Lựa chọn hợp lý | Vì sao? |
| --- | --- | --- |
| Ứng dụng Spring Boot 3.x triển khai trên Java 17 | Toolchain 17; target/release 17 | Đồng bộ với baseline runtime Java 17 của Spring Boot 3.x; build reproducible hơn |
| Code Java thông thường viết cho Java 8, biên dịch trên JDK 17 | JDK/compiler 17 + `--release 8` | Bắt lỗi cú pháp, bytecode và API Java 8 ngay khi biên dịch |
| Thư viện Java nhắm runtime 17 nhưng CI dùng JDK 21 | Toolchain JDK 21 + `options.release = 17`, kiểm tra dependency và test trên Java 17 | Compiler và mức Java mục tiêu là hai biến độc lập |
| Dự án có `sourceCompatibility = 8`, `targetCompatibility = 8`, build thành công trên JDK 17 | Kiểm tra API được dùng; cân nhắc chuyển sang `options.release = 8` | Cặp source/target không ngăn sử dụng API JDK mới |
| JAR có class major 61 nhưng chạy trên JVM 11 | Triển khai runtime Java 17+ hoặc build lại cho phiên bản **mà toàn bộ framework/dependency hỗ trợ** | JVM 11 không thể đọc class Java 17 |
| Dùng Gradle Wrapper nhưng các máy build chọn JDK khác nhau | Cấu hình Java toolchain, kiểm tra CI/IDE | Wrapper giải quyết phiên bản Gradle, không pin JDK biên dịch |

Đối với **Spring Boot**, luôn kiểm tra **system requirements của phiên bản Spring Boot đang dùng** trước khi cố hạ Java target. Chẳng hạn, Spring Boot 3.3 yêu cầu Java 17 trở lên; đặt `--release 8` cho mã ứng dụng không biến Spring Boot 3.3 thành ứng dụng chạy được bằng Java 8. Một framework có thể đã dùng class file của Java 17 dù mã của bạn là Java 8.

## 11. Những nhầm lẫn và lỗi thường gặp

**“Tôi có `targetCompatibility = 8`, vậy chắc chắn chạy Java 8.”** Không. Đó mới chỉ là class-file target của những class task biên dịch. API `String.repeat`, dependency mới hơn hoặc runtime-specific code vẫn có thể gây lỗi. Giải pháp: `--release 8` và kiểm thử với JVM 8, nếu toàn bộ dependency cho phép.

**“`sourceCompatibility = 17` đồng nghĩa Gradle dùng JDK 17.”** Không. Nó mô tả source level. Dùng Java toolchain để chọn compiler JDK; kiểm tra JVM chạy Gradle và compiler task khi debug.

**“Chỉ cần đặt `--release 17` thì không cần cài JDK.”** Không. `--release` là tùy chọn của compiler đang được sử dụng. Compiler phải tồn tại và hỗ trợ release 17; Gradle/Maven không tự có Java 17 chỉ nhờ con số đó.

**“`sourceCompatibility = 17` và `targetCompatibility = 8` là cách chạy Java 8.”** Không hợp lệ vì target thấp hơn source. Dùng source/release phù hợp phiên bản runtime thật sự hỗ trợ, nhưng không ép Spring Boot mới hạ xuống runtime mà framework không hỗ trợ.

**“Tôi có Java 17 trong terminal nhưng CI build dùng Java 21.”** Có thể là cấu hình toolchain/Gradle Daemon/runner khác. Kiểm tra `./gradlew --version`, `javaToolchains` và log `compileJava`; đọc cấu hình CI thay vì chỉ nhìn phiên bản shell.

**“`--release` kiểm tra toàn bộ JAR.”** Không. Nó giới hạn cách `javac` biên dịch source đang xét và các API Java nền tảng, **không biên dịch lại hoặc xác nhận bytecode/API của mọi dependency ngoài**. Hãy kiểm tra Java tối thiểu của framework/thư viện và chạy thử trên JVM đích.

**“Đã đổi `--release` nhưng `javap` vẫn hiện class cũ.”** Có thể đang xem nhầm output/đường dẫn hoặc class lưu từ build trước. Chạy `clean`, biên dịch lại, và dùng class/JAR vừa tạo để kiểm tra.

**“Có thể kết hợp trực tiếp `javac --release 8 -source 8 -target 8` để chắc chắn hơn.”** Không. `javac` cấm kết hợp `--release` với `-source`/`-target`. Hãy chọn một cách có ý nghĩa; khi cần cross-compilation an toàn, ưu tiên `--release`.

## 12. Checklist trước khi chốt Java target

- [ ] Biết **JVM tối thiểu** cần chạy ứng dụng và Java tối thiểu của Spring Boot/framework/dependency đang dùng.
- [ ] Biết compiler JDK được **Gradle/Maven thật sự chọn**; không suy từ Wrapper hay `sourceCompatibility`.
- [ ] Dùng **`options.release`/`maven.compiler.release`** khi cần khóa cú pháp, bytecode và API nền tảng theo target.
- [ ] Không đặt `sourceCompatibility` cao hơn `targetCompatibility`; tránh khai báo mục tiêu Java trùng lặp, mâu thuẫn.
- [ ] Xác minh class-file major bằng `javap -verbose` trên output mới build.
- [ ] Xác minh dependency và framework hỗ trợ phiên bản Java đích, cả về class file lẫn runtime API.
- [ ] Chạy build/test trên CI và kiểm thử sản phẩm trên **JVM đích**, không chỉ trên JDK mới của lập trình viên.

**Kết luận:** `sourceCompatibility` khóa **cú pháp nguồn**; `targetCompatibility` khóa **định dạng bytecode**; `--release` khóa cả **cú pháp + bytecode + API Java nền tảng** theo bản Java mục tiêu. Để build Spring Boot ổn định, kết hợp mục tiêu biên dịch phù hợp với **Java toolchain** và xác minh phiên bản Java thực sự của **framework, dependency và môi trường triển khai**.

## Tài liệu kỹ thuật chính thức

- [Gradle — Building Java & JVM projects: targeting a specific Java version](https://docs.gradle.org/current/userguide/building_java_projects.html)
- [Gradle — Toolchains for JVM projects](https://docs.gradle.org/current/userguide/toolchains.html)
- [Oracle — `javac`: `--release`, `--source` và `--target`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
- [Apache Maven — Guide to Targeting a Java Version](https://maven.apache.org/guides/mini/guide-java-target.html)
- [Spring Boot 3.3 — System Requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html)
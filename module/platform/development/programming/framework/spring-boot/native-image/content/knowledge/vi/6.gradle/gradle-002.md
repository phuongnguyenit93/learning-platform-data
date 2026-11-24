# Java toolchain và lựa chọn GraalVM dùng cho native build

Trong chương **Gradle** của module **SPRING_BOOT_NATIVE_IMAGE**, chúng ta cần trả lời một câu hỏi thực tế: **Gradle dùng bản Java nào để biên dịch ứng dụng Spring Boot và dùng bản GraalVM nào để tạo native executable?** Hai lựa chọn này có liên hệ với nhau nhưng không hoàn toàn giống nhau. Một máy có thể cài cùng lúc Temurin JDK, GraalVM JDK và nhiều phiên bản Java; nếu không kiểm soát toolchain, build JVM có thể thành công trong khi `nativeCompile` thất bại hoặc chọn nhầm công cụ.

Bài này hướng dẫn cấu hình **Java Toolchains của Gradle** và **GraalVM Native Build Tools** để thực hiện Spring AOT và tạo GraalVM Native Image. Đây là bước nền cho việc xử lý reflection/resource metadata, kiểm thử tương thích, đóng gói container và đo thời gian khởi động, bộ nhớ của Spring Boot native.

> **Phạm vi phiên bản:** các ví dụ dùng Java 21 và DSL của Gradle/GraalVM Native Build Tools ở dạng thông dụng. Khi làm dự án thật, phải chọn phiên bản Java, Gradle, Spring Boot và plugin Native Build Tools tương thích với nhau. Cấu hình mẫu giả định dự án đã áp dụng các plugin cần thiết; những thay đổi về API của plugin hoặc trình phát hiện toolchain phải được đối chiếu với phiên bản dự án đang dùng.

## 1. Kết quả học tập

Sau khi hoàn thành, bạn có thể:

1. Phân biệt **JVM chạy Gradle**, **JDK mà Java Toolchain lựa chọn** và **GraalVM JDK cung cấp công cụ Native Image**.
2. Khai báo ngôn ngữ Java và vendor GraalVM trong `build.gradle` hoặc `build.gradle.kts`.
3. Hiểu vai trò của `graalvmNative.toolchainDetection` và cách kiểm chứng công cụ thực sự được chọn.
4. Cấu hình môi trường có nhiều JDK trên máy cá nhân hoặc CI, không phụ thuộc vào phỏng đoán từ `java -version`.
5. Chẩn đoán các lỗi thường gặp: sai Java version, không tìm thấy GraalVM, thiếu executable `native-image` hoặc compiler/linker hệ điều hành.

## 2. Ba lớp lựa chọn Java trong một Gradle build

Gradle không chỉ có một khái niệm “đang dùng JDK nào”. Cần phân biệt:

| Lớp | Thành phần | Nhiệm vụ | Nguồn cấu hình thường gặp |
|---|---|---|---|
| **A. Gradle JVM** | Java chạy Gradle daemon/build logic | Chạy Gradle, build scripts và plugin | `JAVA_HOME`, IDE Gradle JVM, `org.gradle.java.home` hoặc cấu hình Daemon JVM |
| **B. Java Toolchain** | JDK cho tác vụ Java | Chạy compiler hoặc các task Java liên quan theo yêu cầu về phiên bản/vendor | Khối `java { toolchain { ... } }` và dịch vụ Java Toolchains |
| **C. Native Image toolchain** | GraalVM JDK có `native-image` | Phân tích ứng dụng và biên dịch native executable | Cơ chế phát hiện/chỉ định JDK trong plugin GraalVM Native Build Tools |

Các lớp có thể cùng trỏ đến **một GraalVM JDK**, nhưng không bắt buộc. Chẳng hạn:

~~~text
Gradle daemon       -> Temurin JDK 21
Java compile/test   -> GraalVM JDK 21
Native Image        -> GraalVM JDK 21, có native-image
Native linker       -> toolchain C/C++ của Linux
~~~

Hoặc một thiết lập dễ quản lý hơn:

~~~text
Gradle daemon       -> GraalVM JDK 21
Java compile/test   -> GraalVM JDK 21
Native Image        -> GraalVM JDK 21, có native-image
Native linker       -> toolchain C/C++ của hệ điều hành
~~~

### Sơ đồ quan hệ

~~~mermaid
flowchart TD
    S["Source Spring Boot"] --> G["Gradle daemon + plugins"]
    A["JDK chạy Gradle"] -. "Chạy build logic" .-> G
    G --> J["Java compile + Spring AOT"]
    B["Gradle Java Toolchain"] -. "Chọn compiler và Java launcher" .-> J
    J --> I["Class files, AOT code, metadata"]
    I --> N["nativeCompile / GraalVM Native Image"]
    C["GraalVM JDK có native-image"] -. "Chọn công cụ biên dịch native" .-> N
    D["OS C/C++ compiler và linker"] -. "Tạo executable cho nền tảng" .-> N
    N --> E["Native executable"]
~~~

**Java Toolchain không phải công cụ Native Image.** Một JDK thông thường có thể đáp ứng yêu cầu `languageVersion = 21` nhưng không cung cấp `native-image`. Ngược lại, GraalVM JDK có thể cung cấp cả compiler Java và Native Image nếu đúng phiên bản và thành phần được cài.

## 3. Java Toolchains giải quyết vấn đề gì?

Giả sử thành viên A dùng JDK 21 để chạy Gradle, thành viên B chạy Gradle bằng JDK 22, còn CI có JDK 17. Nếu dự án chỉ dựa vào Java mặc định của máy, kết quả biên dịch có thể không nhất quán.

Gradle Java Toolchains cho phép dự án **khai báo JDK mà các tác vụ Java cần dùng**, thay vì giả định mọi tác vụ đều sử dụng JVM đang chạy Gradle:

~~~groovy
// build.gradle (Groovy DSL)
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

Với Kotlin DSL:

~~~kotlin
// build.gradle.kts
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

Cấu hình này có ý nghĩa là **các task Java có hỗ trợ toolchain** cần công cụ Java 21. Nó không đồng nghĩa:

- Gradle daemon sẽ chuyển sang chạy Java 21.
- Gradle sẽ tự cài Java 21 trong mọi môi trường. Việc tải JDK tự động phụ thuộc cơ chế resolver được cấu hình và khả năng hỗ trợ của phiên bản Gradle.
- JDK Java 21 được chọn chắc chắn là **GraalVM**.
- Trong JDK đã chọn chắc chắn tồn tại executable `native-image`.

Vì vậy, chỉ khai báo `languageVersion` là chưa đủ cho một quy trình native build mà bạn cần kiểm soát rõ bản phân phối GraalVM.

### Java version, vendor và implementation

Java Toolchains có thể mô tả nhiều thuộc tính của JDK. Hai thuộc tính quan trọng nhất trong bài là:

- **`languageVersion`:** ví dụ Java 21; tương ứng thế hệ Java mà task cần.
- **`vendor`:** nhà phát hành hoặc bản phân phối JDK, chẳng hạn GraalVM thay vì một JDK bất kỳ.

Trong các phiên bản Gradle hỗ trợ hằng `JvmVendorSpec.GRAAL_VM`:

~~~groovy
// build.gradle
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
        vendor = JvmVendorSpec.GRAAL_VM
    }
}
~~~

~~~kotlin
// build.gradle.kts
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
        vendor = JvmVendorSpec.GRAAL_VM
    }
}
~~~

Trong những môi trường có cách nhận diện vendor khác nhau, một số phiên bản Gradle cho phép dùng `JvmVendorSpec.matching("...")` với chuỗi vendor thực tế. Để biết chuỗi nào được phát hiện, **xem đầu ra của `javaToolchains` trước khi tự điền tên**. Việc yêu cầu vendor đúng giúp loại bỏ JDK thường khỏi lựa chọn Java Toolchain, nhưng vẫn phải xác nhận công cụ Native Image hiện diện và plugin native đang sử dụng đúng JDK đó.

### `sourceCompatibility` và `options.release` khác toolchain ra sao?

Ví dụ:

~~~groovy
java {
    sourceCompatibility = JavaVersion.VERSION_21
    targetCompatibility = JavaVersion.VERSION_21
}
tasks.withType(JavaCompile).configureEach {
    options.release = 21
}
~~~

Các cấu hình tương thích nguồn/đích hoặc `--release` mô tả **mức ngôn ngữ và API/bytecode cần tạo**. Chúng không tự động chọn **nơi cài đặt JDK** để chạy compiler. Một compiler quá cũ có thể không hỗ trợ `--release 21`; và compiler mới hơn có thể tạo bytecode Java 21 mà không phải là GraalVM.

Với bài toán native build, hãy chọn toolchain trước, sau đó bổ sung quy tắc release nếu dự án cần giới hạn API và bytecode một cách tường minh.

## 4. GraalVM Native Build Tools chọn công cụ ra sao?

Khi dự án áp dụng plugin **`org.graalvm.buildtools.native`**, Gradle có các tác vụ như `nativeCompile` để tạo native executable. Plugin cần định vị một **GraalVM JDK có Native Image**.

Một cấu hình thông dụng là:

~~~groovy
// build.gradle
graalvmNative {
    toolchainDetection = true
}
~~~

~~~kotlin
// build.gradle.kts
graalvmNative {
    toolchainDetection = true
}
~~~

Khi bật phát hiện toolchain, plugin tích hợp với cơ chế phát hiện Java Toolchains của Gradle theo API của **phiên bản Native Build Tools đang dùng**. Với cấu hình vendor GraalVM ở phần trước, ý định của dự án rõ ràng hơn: cần Java 21 từ GraalVM, thay vì Java 21 bất kỳ.

Đừng suy luận rằng bật `toolchainDetection` đã kiểm chứng xong môi trường. Nếu máy không có GraalVM phù hợp, Gradle có thể báo không tìm thấy toolchain hoặc không tìm thấy Native Image. Nếu máy có nhiều bản GraalVM, phải xem log để xác định **executable nào thực sự được gọi**.

### Sự khác biệt với `JAVA_HOME` và `PATH`

`JAVA_HOME` và `PATH` là biến môi trường của tiến trình. Chúng rất hữu ích khi cấu hình nhanh máy lập trình, nhưng không đại diện cho toàn bộ cơ chế Java Toolchains:

- `JAVA_HOME` thường ảnh hưởng JVM dùng để khởi chạy Gradle wrapper, nếu không có lựa chọn ưu tiên khác.
- `PATH` quyết định lệnh `java` hoặc `native-image` nào được shell tìm thấy khi gọi trực tiếp.
- Gradle Java Toolchains có thể khám phá JDK ở nhiều thư mục khác và lựa chọn theo `languageVersion`/`vendor`.
- Plugin GraalVM Native Build Tools có quy tắc riêng để chọn launcher/executable, tùy phiên bản và chế độ phát hiện.

Ví dụ:

~~~text
JAVA_HOME=/opt/jdks/temurin-21
PATH có /opt/jdks/temurin-21/bin

Gradle java.toolchain:
  Java 21, vendor GraalVM

GraalVM đã cài:
  /opt/jdks/graalvm-jdk-21
~~~

Nếu Gradle phát hiện GraalVM và plugin native chọn đúng toolchain, `nativeCompile` vẫn có thể dùng GraalVM, dù `java -version` trong terminal hiển thị Temurin. **Giá trị thật phải được xác minh trong thông tin Gradle và log build.**

## 5. Ví dụ hoàn chỉnh phần cấu hình Gradle

Các đoạn sau tập trung vào **phần cấu hình toolchain** của một dự án Spring Boot đã khai báo plugin Spring Boot và GraalVM Native Build Tools. Chúng không gán phiên bản plugin cụ thể, vì phiên bản phù hợp phải được xác định theo dự án thực tế.

### 5.1. Groovy DSL — `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
    id 'org.graalvm.buildtools.native'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
        vendor = JvmVendorSpec.GRAAL_VM
    }
}

graalvmNative {
    toolchainDetection = true
}
~~~

Ở ví dụ này, dòng khai báo plugin **giả định phiên bản được quản lý bên ngoài khối này** (ví dụ qua `pluginManagement` hoặc cơ chế quản lý plugin của dự án). Nếu khởi tạo một dự án Gradle độc lập, bạn cần khai báo phiên bản plugin thích hợp ở nơi Gradle có thể phân giải chúng. Ngoài ra, ứng dụng Spring Boot còn phải có dependencies và mã nguồn cần thiết.

Ý nghĩa:

1. Plugin Java cung cấp các tác vụ Java và phần mở rộng `java.toolchain`.
2. Java Toolchain yêu cầu **Java 21, vendor GraalVM** cho các task hỗ trợ.
3. Plugin GraalVM Native Build Tools tạo tác vụ native và tìm công cụ Native Image theo cấu hình.
4. Spring Boot plugin tham gia quy trình build và hỗ trợ luồng Spring AOT cần thiết cho ứng dụng native.

Khi dự án đã có cấu hình `plugins`, chỉ **bổ sung hoặc điều chỉnh đúng các khối còn thiếu**, tránh khai báo lại plugin cùng tên.

### 5.2. Kotlin DSL — `build.gradle.kts`

~~~kotlin
plugins {
    java
    id("org.springframework.boot")
    id("org.graalvm.buildtools.native")
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
        vendor = JvmVendorSpec.GRAAL_VM
    }
}

graalvmNative {
    toolchainDetection = true
}
~~~

Hai cách viết thể hiện cùng ý định. Cú pháp plugin resolution, kiểu property và DSL chi tiết cần phù hợp phiên bản Gradle/plugin đang sử dụng. Nếu dự án đã áp dụng plugin native bằng convention plugin hoặc phiên bản nằm trong version catalog, **giữ nguyên cơ chế quản lý đó**.

### 5.3. Khi chỉ muốn một GraalVM JDK trên máy

Đối với bài thực hành đầu tiên, cách dễ tái tạo nhất là cài **một GraalVM JDK 21** tương thích với dự án, bảo đảm có lệnh `native-image`, dùng nó để chạy Gradle rồi khai báo Java Toolchain cùng phiên bản/vendor:

~~~bash
# Linux/macOS: thay đường dẫn bằng bản GraalVM thực tế
export JAVA_HOME=/opt/jdks/graalvm-jdk-21
export PATH="$JAVA_HOME/bin:$PATH"

java -version
native-image --version
./gradlew --version
./gradlew javaToolchains
~~~

Mỗi dòng kiểm chứng một khía cạnh khác nhau: Java được shell tìm thấy, Native Image trực tiếp, JVM chạy Gradle và danh sách toolchain mà Gradle biết.

Trên PowerShell:

~~~powershell
$env:JAVA_HOME = 'C:\jdks\graalvm-jdk-21'
$env:PATH = "$env:JAVA_HOME\bin;$env:PATH"

java -version
native-image --version
.\gradlew.bat --version
.\gradlew.bat javaToolchains
~~~

Lệnh thay đổi biến môi trường ở đây chỉ áp dụng **phiên terminal hiện tại**. Khi chạy từ IntelliJ IDEA hoặc CI, Gradle JVM và các đường dẫn toolchain có thể được thiết lập riêng.

## 6. Kiểm chứng JDK nào thật sự được chọn

### Bước 1: kiểm tra JVM đang chạy Gradle

~~~bash
./gradlew --version
~~~

Đầu ra cho biết phiên bản Gradle và thông tin JVM. Ở các phiên bản Gradle có tách launcher/daemon JVM, hãy đọc đúng dòng liên quan; một số phiên bản cũ hiển thị định dạng khác. Đừng lấy `java -version` của shell làm bằng chứng duy nhất.

### Bước 2: liệt kê Java Toolchains Gradle phát hiện

~~~bash
./gradlew javaToolchains
~~~

Tác vụ này liệt kê các JDK được Gradle phát hiện và những thuộc tính như đường dẫn, ngôn ngữ Java và vendor. Đầu ra minh họa:

~~~text
Detected toolchains (minh họa):
  /opt/jdks/temurin-21      -> Java 21, Eclipse Adoptium
  /opt/jdks/graalvm-jdk-21  -> Java 21, GraalVM
~~~

Không cần output của mọi máy giống hệt ví dụ. Mục tiêu là xác minh Gradle thấy **đúng bản GraalVM cần dùng**. Nếu kết quả không có GraalVM, trước hết kiểm tra thư mục cài đặt và cách Gradle phát hiện JDK.

### Bước 3: chạy tác vụ build native với thông tin chi tiết

~~~bash
./gradlew nativeCompile --info
~~~

Tác vụ sẽ chạy các bước cần thiết để tạo native executable, khi ứng dụng và plugin đã cấu hình đúng. Log có thể cho thấy đường dẫn toolchain và lệnh Native Image được thực thi. Khi lỗi, thêm `--stacktrace` để xem ngữ cảnh:

~~~bash
./gradlew nativeCompile --info --stacktrace
~~~

Đọc log để trả lời:

- Công cụ `native-image` đang được gọi từ **đường dẫn nào**?
- Nó thuộc **phiên bản GraalVM/Java nào**?
- Có bước xử lý Spring AOT, metadata và compile native phù hợp không?
- Lỗi phát sinh trong **Gradle configuration**, **Java compile**, **Spring AOT**, **Native Image analysis** hay **native linking**?

Nếu build hoàn thành, chạy executable và kiểm thử chức năng trước khi so sánh startup/memory với bản JVM. **Build được** chưa có nghĩa mọi reflection, resource, serialization hoặc endpoint đều đúng ở runtime.

### Bước 4: kiểm tra Gradle daemon khi thay đổi JDK

Nếu vừa đổi JVM của Gradle mà kết quả vẫn khó hiểu, có thể dừng daemon rồi chạy lại các lệnh kiểm chứng:

~~~bash
./gradlew --stop
./gradlew --version
./gradlew javaToolchains
~~~

`--stop` giúp loại trừ tình trạng có daemon cũ của cùng phiên bản Gradle đang hoạt động. Nó **không cài JDK, không sửa cấu hình toolchain** và không thay thế việc kiểm tra log.

## 7. Máy có nhiều JDK: định vị GraalVM một cách chủ động

Máy developer/CI thường có nhiều JDK cùng major version. Ví dụ hai thư mục cùng Java 21:

~~~text
/opt/jdks/temurin-21
/opt/jdks/graalvm-jdk-21
~~~

Để Gradle biết một thư mục cài JDK cụ thể, có thể cấu hình **đường dẫn Java installations** trong `gradle.properties`:

~~~properties
# Đường dẫn minh họa trên Linux; chỉnh theo máy hoặc CI.
org.gradle.java.installations.paths=/opt/jdks/graalvm-jdk-21
~~~

Property này **thêm một nơi để phát hiện JDK**, không ép mọi task dùng JDK đó và không chứng minh trong JDK có Native Image. Nếu còn nhiều installation khớp, dùng `vendor` và kiểm tra việc lựa chọn. Trên Windows, cú pháp đường dẫn trong `.properties` cần đặc biệt cẩn thận với dấu gạch chéo ngược và ký tự phân tách.

Một lựa chọn khác là cấu hình Gradle qua cơ chế toolchain resolver để tải JDK trong môi trường cho phép. Tính năng tải toolchain tự động phụ thuộc **phiên bản Gradle, repository/resolver và chính sách mạng CI**. Đừng giả định Gradle sẽ tự tải GraalVM chỉ nhờ dòng `vendor = JvmVendorSpec.GRAAL_VM`.

### Nên lưu cấu hình nào trong repository?

Nên commit:

- Phiên bản Gradle Wrapper, plugin Spring Boot và GraalVM Native Build Tools.
- Java version dự án yêu cầu; bộ lọc vendor khi dự án chủ động cần GraalVM.
- Cấu hình cần thiết cho build/test native và Spring AOT.

Nên cân nhắc trước khi commit đường dẫn như `/Users/ten-nguoi-dung/graalvm` hoặc `C:\jdks\graalvm`, vì chúng không di động. Với CI, có thể cài JDK vào vị trí chuẩn hoặc để pipeline khai báo đường dẫn đặc thù môi trường.

### Nếu muốn Gradle chạy bằng JDK khác với Java Toolchain

Ví dụ:

~~~text
JVM Gradle daemon: Temurin 21
Java Toolchain:    GraalVM 21
Native Image:      GraalVM 21
~~~

Đây là cách bố trí hợp lệ **khi các phiên bản Gradle/plugin hỗ trợ**. Không cần ép daemon dùng GraalVM chỉ để task Native Image chọn GraalVM. Nhưng cần tránh nghĩ rằng thay `JAVA_HOME` đủ để đổi Java Toolchain đã khai báo.

Trong IDE, cấu hình **Gradle JVM** có thể độc lập với project JDK và terminal. Để điều tra kết quả khác nhau giữa IDE và command line, so sánh JVM Gradle daemon, Java installations và native task log ở cả hai nơi.

## 8. Liên hệ với Spring AOT và nhiệm vụ `nativeCompile`

Spring AOT phân tích cấu hình ứng dụng và chuẩn bị mã, metadata để giảm phụ thuộc vào một số hành vi động của JVM. Khi kết hợp Spring Boot Gradle plugin và GraalVM Native Build Tools đúng cách, quy trình native build sẽ sử dụng dữ liệu đó để tạo executable.

Một chuỗi logic thường gặp:

~~~text
Mã Java / resources
    ↓
Java compile, dependency resolution
    ↓
Xử lý Spring AOT và generated sources/resources
    ↓
GraalVM Native Image phân tích reachability
    ↓
Native compiler/linker
    ↓
Native executable
~~~

**Chọn đúng GraalVM không giải quyết mọi lỗi AOT.** Nếu một thư viện truy cập lớp bằng reflection mà Native Image không nhìn thấy được trong phân tích tĩnh, ứng dụng có thể cần **Runtime Hints/reachability metadata**. Tương tự, tài nguyên phải được khai báo phù hợp nếu Native Image không tự bao gồm chúng. Đây là vấn đề **tương thích và metadata**, khác với lỗi Gradle chọn nhầm JDK.

Trong nhiều dự án Spring Boot, cấu hình chính cho build native là:

~~~bash
./gradlew nativeCompile
~~~

Nếu Gradle báo không tìm thấy task này, kiểm tra plugin Native Build Tools đã được áp dụng đúng chỗ (root hay subproject) và phiên bản plugin. Đừng kết luận GraalVM bị cài sai chỉ vì không tồn tại task.

### Trường hợp multi-module

Với dự án có nhiều subprojects, các khối `java.toolchain` và `graalvmNative` có thể nằm trong module ứng dụng hoặc convention plugin. Không phải cứ thêm cấu hình vào root project thì **tất cả subproject tự động nhận được**. Cần kiểm tra module nào đã apply plugin Java/Spring Boot/Native Build Tools và gọi task theo đường dẫn module, ví dụ:

~~~bash
./gradlew :application:nativeCompile --info
~~~

Tên `application` ở đây chỉ là ví dụ; hãy thay bằng tên module của dự án.

## 9. Native build trực tiếp khác với `bootBuildImage`

Hai đường build thường bị trộn lẫn:

| Hướng build | Công cụ Native Image chạy ở đâu? | JDK host có vai trò gì? |
|---|---|---|
| `nativeCompile` | Thường chạy trực tiếp trong môi trường thực thi Gradle task | Gradle/plugin định vị GraalVM và dùng toolchain native của máy |
| `bootBuildImage` với buildpack native | Chạy trong môi trường **builder image** của Cloud Native Buildpacks | JDK host chạy Gradle; bản GraalVM/Native Image trong builder có thể khác |

Với Spring Boot Gradle plugin, việc bật native trong buildpack có thể thực hiện thông qua môi trường buildpack nếu builder hỗ trợ:

~~~groovy
// Ví dụ Groovy DSL, trong dự án đã có task bootBuildImage.
tasks.named('bootBuildImage') {
    environment = ['BP_NATIVE_IMAGE': 'true']
}
~~~

Ở dự án đã cấu hình các biến môi trường khác cho task này, cần **gộp** giá trị mới thay vì thay thế map môi trường hiện có. Cách API nhận property `environment` có thể thay đổi theo phiên bản Spring Boot Gradle plugin; kiểm tra DSL của phiên bản đang chạy.

Khi dùng buildpacks, `./gradlew javaToolchains` trên host **không nhất thiết** cho biết GraalVM được dùng trong builder. Cần xem **log và cấu hình builder image**. Binary native thường được build cho hệ điều hành/kiến trúc của môi trường build thích hợp; không thể giả định tệp native Windows chạy được trong container Linux.

## 10. Vì sao chọn Java đúng version vẫn có thể lỗi native?

### 10.1. Toolchain chỉ chọn Java 21 nhưng đó là JDK thường

**Triệu chứng:** Gradle compile Java thành công nhưng `nativeCompile` không tìm thấy Native Image hoặc công cụ GraalVM phù hợp.

**Nguyên nhân:** `languageVersion = 21` có thể chọn Temurin 21, trong khi plugin native cần GraalVM JDK. **Xử lý:** xác định vendor toolchain và xem log native task; bổ sung ràng buộc GraalVM nếu dự án cần.

### 10.2. Gradle không phát hiện GraalVM đã cài

**Triệu chứng:** Có GraalVM trong thư mục máy nhưng `javaToolchains` không liệt kê hoặc plugin thông báo thiếu toolchain phù hợp.

**Nguyên nhân có thể:** thư mục JDK sai cấp, phát hiện JDK bị giới hạn, Gradle không thể truy cập đường dẫn, bản vendor/version không khớp hoặc resolver chưa cấu hình. **Xử lý:** kiểm tra `javaToolchains`, cấu hình `org.gradle.java.installations.paths` nếu cần và xem Gradle logs.

### 10.3. Đã chọn GraalVM JDK nhưng không có `native-image`

**Triệu chứng:** `java -version` cho thấy GraalVM, song native task báo không thấy executable Native Image.

**Nguyên nhân:** cách phân phối/cài đặt GraalVM hiện tại chưa có thành phần Native Image, hoặc plugin trỏ đến thư mục khác. Tùy phiên bản GraalVM, Native Image có thể đã đóng gói kèm hoặc phải cài riêng. **Không áp dụng máy móc một lệnh cài đặt chung cho mọi đời GraalVM.**

**Xử lý:** kiểm tra executable trong thư mục `bin` của JDK được chọn, chạy trực tiếp `native-image --version` từ đúng thư mục đó, sau đó đối chiếu với log plugin.

### 10.4. Lỗi Java class file version / unsupported release

**Triệu chứng:** thông báo về unsupported class file major version, invalid source release hoặc công cụ không hỗ trợ Java level.

**Nguyên nhân:** JDK compiler hoặc Native Image quá cũ so với bytecode/source dự án. **Xử lý:** so sánh Java source/target/release, JDK của toolchain, phiên bản Native Image và yêu cầu của Spring Boot/plugin.

### 10.5. Thiếu C/C++ compiler, linker hoặc thư viện hệ điều hành

**Triệu chứng:** Java compile và Spring AOT chạy nhưng Native Image báo thiếu `cc`, `ld`, `cl.exe`, headers hoặc SDK.

**Nguyên nhân:** GraalVM Native Image phụ thuộc công cụ native của hệ điều hành trong bước biên dịch/liên kết. **Xử lý:** cài toolchain phù hợp cho Linux/macOS/Windows; bảo đảm terminal/CI đã nạp môi trường compiler. Đây không phải lỗi Java Toolchains của Gradle.

### 10.6. Build native thành công nhưng ứng dụng lỗi runtime

**Triệu chứng:** executable chạy nhưng thất bại khi deserialize, dùng reflection hoặc tải tài nguyên.

**Nguyên nhân thường gặp:** thiếu Runtime Hints/resource metadata, giả định về dynamic class loading hoặc thư viện không tương thích. **Xử lý:** kiểm thử bản native, bổ sung metadata khi cần. Không thay JDK liên tục nếu đã xác nhận toolchain được chọn đúng.

### Bảng tra lỗi nhanh

| Bước lỗi | Bằng chứng cần xem | Khu vực cần sửa |
|---|---|---|
| Gradle không khởi động | `./gradlew --version`, Java của daemon | Gradle JVM/Gradle version |
| Không chọn được Java compiler | `./gradlew javaToolchains` | Java Toolchain version/vendor/discovery |
| Không thấy `nativeCompile` | Danh sách task và plugin áp dụng | Cấu hình Gradle Native Build Tools |
| Không thấy GraalVM/`native-image` | Log `nativeCompile --info` và thư mục GraalVM | Native toolchain detection/cài đặt |
| Lỗi compiler/linker native | Native build log | C/C++ toolchain/SDK của OS |
| Executable sai chức năng | Test runtime, stack trace, metadata | Spring AOT, reflection/resource, thư viện |

## 11. Chiến lược CI để build có thể lặp lại

Một pipeline native build đáng tin cậy nên ghi rõ:

1. **Gradle Wrapper** được dùng, tránh phụ thuộc Gradle được cài sẵn trên agent.
2. **Java version/vender** cần cho compiler và Native Image được khai báo trong dự án.
3. CI cài **GraalVM JDK phiên bản tương thích** và bảo đảm `native-image` hiện diện.
4. Môi trường cung cấp đúng **C/C++ compiler/linker** và thư viện nền tảng.
5. Pipeline ghi log `./gradlew --version`, `./gradlew javaToolchains` và `native-image --version` ở vị trí tương ứng; log native task xác nhận executable thực sự được gọi.
6. Native executable được chạy qua smoke test hoặc integration tests trên hệ điều hành/kiến trúc tương đương môi trường triển khai.

Một trình tự minh họa:

~~~bash
./gradlew --version
./gradlew javaToolchains
native-image --version
./gradlew clean nativeCompile --info
~~~

Đây là **trình tự tham khảo** khi Native Image chạy trên host. Trong CI thực tế, cần chỉ rõ GraalVM/Native Image được thiết lập ở đâu; kết quả `native-image --version` của `PATH` không thay thế việc xác minh native task log. `clean` có thể làm tăng đáng kể thời gian build, nên chỉ dùng khi cần build sạch hay đối chiếu kết quả.

**Tái lập build** không có nghĩa binary phải có checksum giống hệt trên mọi máy. Kết quả có thể chịu ảnh hưởng bởi phiên bản toolchain, OS/architecture, native libraries và các yếu tố build khác. Mục tiêu trước mắt là kiểm soát các đầu vào quan trọng và đo hiệu năng trong điều kiện nhất quán.

## 12. Thực hành có hướng dẫn

Giả sử bạn có dự án Spring Boot hỗ trợ Java 21, đã cấu hình plugin Spring Boot và GraalVM Native Build Tools. Máy có:

~~~text
JDK A: /opt/jdks/temurin-21
JDK B: /opt/jdks/graalvm-jdk-21
~~~

**Yêu cầu:** dùng JDK B để biên dịch Java và tạo native executable, bất kể Gradle daemon hiện chạy trên JDK nào.

**Bước 1.** Trong `build.gradle`, khai báo:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
        vendor = JvmVendorSpec.GRAAL_VM
    }
}
graalvmNative {
    toolchainDetection = true
}
~~~

**Bước 2.** Chạy:

~~~bash
./gradlew --version
./gradlew javaToolchains
~~~

Ghi lại **JVM chạy Gradle** và **đường dẫn JDK B** trong danh sách toolchains. Nếu JDK B chưa được phát hiện, điều chỉnh cơ chế phát hiện JDK (ví dụ đường dẫn Java installation) và xác minh lại.

**Bước 3.** Kiểm tra Native Image tại chính JDK B:

~~~bash
/opt/jdks/graalvm-jdk-21/bin/native-image --version
~~~

Nếu lệnh thất bại, kiểm tra cách đóng gói Native Image của bản GraalVM hiện có trước khi thử native build.

**Bước 4.** Khi công cụ C/C++ của OS đã sẵn sàng:

~~~bash
./gradlew nativeCompile --info
~~~

Quan sát đường dẫn executable Native Image trong log. Nếu nó khác JDK B, không vội thay `JAVA_HOME`; trước hết kiểm tra cấu hình plugin/toolchain và cơ chế phát hiện.

**Bước 5.** Chạy native executable được tạo và thực hiện một smoke test. Sau đó so sánh bản native với `java -jar` cùng chức năng, điều kiện và workload nếu muốn đánh giá thời gian khởi động/memory.

### Ba tình huống để tự suy luận

**Tình huống 1:** `./gradlew --version` báo Temurin 21, `./gradlew javaToolchains` thấy cả Temurin 21 và GraalVM 21; cấu hình `vendor = JvmVendorSpec.GRAAL_VM`. Có bắt buộc đổi Gradle daemon sang GraalVM không?

**Đáp án:** Không nhất thiết. Daemon có thể chạy bằng JDK tương thích khác trong khi Java Toolchain chọn GraalVM. Cần xác nhận task native dùng đúng executable GraalVM và các phiên bản tương thích.

**Tình huống 2:** Chỉ đặt `languageVersion = 21`, máy có hai JDK 21. Native build báo không tìm được `native-image`. Có thể suy ra tất cả Gradle config sai không?

**Đáp án:** Chưa đủ căn cứ. Cần kiểm tra Java Toolchain đang chọn vendor nào và native plugin tìm Native Image ở đâu. Ràng buộc vendor và kiểm tra đường dẫn công cụ có thể giải quyết phần lựa chọn sai JDK.

**Tình huống 3:** `bootBuildImage` tạo native container thành công nhưng lệnh `native-image` trên laptop không tồn tại. Có bất thường không?

**Đáp án:** Không nhất thiết. Buildpacks có thể dùng Native Image bên trong builder image. Đây là môi trường build khác với `nativeCompile` chạy trực tiếp trên host.

## 13. Checklist trước khi kết luận toolchain đã đúng

- [ ] Biết Java version mà dự án Spring Boot yêu cầu.
- [ ] Đã cố định và sử dụng Gradle Wrapper của dự án.
- [ ] Kiểm tra được JVM chạy Gradle bằng `./gradlew --version`.
- [ ] Java Toolchain khai báo đúng `languageVersion`; `vendor` phù hợp với nhu cầu native.
- [ ] `./gradlew javaToolchains` liệt kê đúng GraalVM JDK và đường dẫn.
- [ ] GraalVM JDK được chọn có `native-image` hoạt động.
- [ ] Plugin GraalVM Native Build Tools được áp dụng cho đúng project/subproject.
- [ ] Log `nativeCompile --info` xác nhận plugin gọi đúng Native Image executable.
- [ ] Native compiler/linker và thư viện hệ điều hành đầy đủ.
- [ ] Smoke test thành công với executable native; reflection/resource được kiểm thử riêng.
- [ ] Nếu dùng buildpacks, đã kiểm tra toolchain **trong builder image**, không nhầm với JDK host.

**Ghi nhớ:** **Gradle JVM** chạy công cụ build; **Gradle Java Toolchain** chọn JDK cho các task Java; **GraalVM Native Image** biên dịch bytecode thành executable native. Hãy khai báo rõ phiên bản/vendor, kiểm tra danh sách toolchain và xác minh đường dẫn Native Image trong log. Đây là cách tránh lỗi chọn sai JDK khi xây dựng và vận hành Spring Boot Native Image trên máy cá nhân, CI và container.

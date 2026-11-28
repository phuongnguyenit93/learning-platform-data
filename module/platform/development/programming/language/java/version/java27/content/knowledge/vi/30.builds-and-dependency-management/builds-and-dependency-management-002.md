# Khai báo Java toolchain và compiler release cho Java 27

Một dự án có thể được build trên máy lập trình dùng JDK 27 nhưng CI lại chạy Maven với JDK 21; một người khác dùng Gradle daemon trên JDK 25, còn ứng dụng được triển khai lên máy chủ chỉ có Java 21. Nếu chỉ viết “dự án dùng Java 27” trong README mà không ràng buộc **JDK biên dịch**, **mức ngôn ngữ/API được phép** và **JVM dùng để chạy**, kết quả build có thể thay đổi theo từng môi trường hoặc thất bại khi triển khai.

Bài học thuộc chương **Build và quản lý phụ thuộc**, dành cho **Java 27**. Mục tiêu là cấu hình có thể lặp lại bằng **Java toolchain** và tùy chọn compiler **`--release`**, trọng tâm là Gradle và Maven hiện hành. Nội dung phân biệt cơ chế chuẩn của `javac` với cấu hình do công cụ build cung cấp; dùng các API được hỗ trợ, không lấy hướng dẫn đã lỗi thời làm cách triển khai chính.

Với bản phát hành đang xét, **Java 27 là phiên bản Java SE đã phát hành**. Gradle chính thức hỗ trợ Java 27 làm toolchain và chạy daemon từ **Gradle 9.8.0**; Maven Compiler Plugin 3.x hiện hành hỗ trợ khai báo thuộc tính `maven.compiler.release`. Dù công cụ build có thể nâng cấp, nguyên tắc **khóa hợp đồng biên dịch vào mã cấu hình** vẫn giữ nguyên.

## 1. Ba câu hỏi khác nhau về phiên bản Java

Trước khi sửa file build, hãy trả lời ba câu hỏi:

1. **JDK nào chạy công cụ build?** Ví dụ JVM chạy Gradle daemon hoặc tiến trình Maven.
2. **JDK nào cung cấp `javac` để biên dịch?** Đây là Java **toolchain** của nhiệm vụ biên dịch.
3. **Mã nguồn và thư viện nền tảng được phép phụ thuộc vào bản Java nào?** Đây là **compiler release** hoặc mục tiêu tương thích.

Chúng có thể bằng nhau, nhưng **không nhất thiết**:

~~~~text
Máy lập trình / CI
┌─────────────────────────────────────────────────────────────┐
│ JVM chạy công cụ build, ví dụ JDK 21                        │
│                 │                                           │
│                 v                                           │
│       Gradle / Maven xác định toolchain                     │
│                 │                                           │
│                 v                                           │
│          Compiler từ JDK 27                                 │
│                 │                                           │
│          javac --release 27                                 │
│                 │                                           │
│                 v                                           │
│        Bytecode và API của Java 27                          │
└─────────────────────────────────────────────────────────────┘
                        │
                        v
                JVM triển khai Java 27+
           (và những dependency tương thích)
~~~~

Sơ đồ chỉ minh họa một cấu hình có thể có. Gradle hoặc Maven phải thực sự **hỗ trợ và chọn được** JDK 27; không phải phiên bản công cụ nào cũng vận hành được như sơ đồ. Để tránh hiểu sai, cần phân biệt:

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| **Build JVM / daemon JVM** | Chạy Gradle/Maven và plugin build | JVM 21, 25 hoặc 27 nếu công cụ hỗ trợ |
| **Compiler JDK (toolchain)** | Cung cấp `javac` và các công cụ JDK cho task | JDK 27 |
| **Compiler release** | Giới hạn cú pháp ngôn ngữ, bytecode và API nền tảng | `--release 27` |
| **Test runtime** | JVM thực thi unit/integration tests | Thường JDK do toolchain/task cấu hình |
| **Production runtime** | JVM thực sự chạy artifact được phát hành | Java 27 hoặc một bản mới hơn tương thích |
| **External dependencies** | JAR/plugin mà dự án sử dụng | Có yêu cầu bytecode/API và version độc lập |

**Định nghĩa mục tiêu:** nếu sản phẩm thực sự được phát hành cho **Java 27**, lựa chọn dễ kiểm tra nhất là **JDK toolchain 27 + `--release 27` + kiểm thử trên runtime 27**. Nếu sản phẩm phải chạy được trên Java 21 dù đội phát triển có JDK 27, mục tiêu phải là **`--release 21`**, không phải 27.

### 1.1. `JAVA_HOME` chưa đủ để tạo build có thể lặp lại

`JAVA_HOME` thường ảnh hưởng JDK mặc định được một command-line tool sử dụng. Tuy nhiên:

- Một **Gradle daemon** có thể chạy trên JVM được cấu hình riêng, tách khỏi JDK biên dịch.
- Maven có thể chọn **toolchain JDK** khác với JDK của `mvn`.
- IDE có các thiết lập Project SDK, Gradle JVM, Maven runner và compiler độc lập.
- CI có thể cài nhiều JDK; giá trị mặc định trên `PATH` không phải luôn là compiler được dùng.

Thay vì yêu cầu “mọi người tự đặt `JAVA_HOME` cho đúng”, hãy mô tả toolchain trong build và có bước xác minh môi trường.

## 2. `javac --release` bảo vệ điều gì?

`javac --release N` là khả năng chính thức của Java compiler từ JDK 9. Với một giá trị được hỗ trợ, nó kết hợp ba loại ràng buộc:

| Ràng buộc | Ý nghĩa của `--release 27` |
| --- | --- |
| **Ngôn ngữ** | Chỉ chấp nhận những đặc tính ngôn ngữ Java được cho phép theo release 27 |
| **Class file** | Sinh bytecode theo phiên bản class file tương ứng release 27 |
| **API nền tảng** | Biên dịch dựa trên những API JDK/Java SE đã được tài liệu hóa và xuất ra cho release 27 |

Các quy tắc này quan trọng khi biên dịch bằng JDK **mới hơn** nhưng muốn chạy trên release **cũ hơn**: `--release` ngăn code vô tình gọi API nền tảng chưa tồn tại ở phiên bản đích.

### 2.1. Ví dụ trực tiếp với `javac`

Giả sử có file Java sau, lưu thành `ReleaseDemo.java`:

~~~~java
import java.util.List;
import java.util.stream.Gatherers;

public class ReleaseDemo {
    public static void main(String[] args) {
        List<List<Integer>> windows = List.of(1, 2, 3, 4, 5)
                .stream()
                .gather(Gatherers.windowFixed(2))
                .toList();

        System.out.println(windows);
        // [[1, 2], [3, 4], [5]]
    }
}
~~~~

`Stream.gather` và `Gatherers` là API đã hoàn thiện từ JDK 24, nên có trong Java 27. Với **JDK 27** được cài và `javac` đúng phiên bản:

~~~~text
javac --version
javac --release 27 ReleaseDemo.java
java ReleaseDemo
~~~~

Nếu vẫn dùng compiler từ JDK 27 nhưng đổi thành:

~~~~text
javac --release 21 ReleaseDemo.java
~~~~

Code **không biên dịch thành công**, vì API `java.util.stream.Gatherers`/`Stream.gather` chưa thuộc Java 21. Đây là **tác dụng cần thiết của `--release`**: không để mã dùng API mới vô tình được công bố như tương thích với runtime cũ.

### 2.2. Không phải tùy chọn “thần kỳ” để biên dịch bằng JDK bất kỳ

`--release 27` yêu cầu compiler **có hỗ trợ release 27**; biên dịch bằng `javac` của JDK 21 hoặc 25 không thể biến thành compiler Java 27 chỉ bằng việc thêm flag ấy. Khi sử dụng một JDK mới hơn, chỉ những release nằm trong tập **được compiler hỗ trợ** mới có thể chọn. Dùng `javac --help` hoặc tài liệu của bản JDK đang chạy để kiểm tra.

**Không thể** dùng `--release` để:

- Tải hoặc cài đặt JDK 27.
- Cập nhật JVM được Gradle/Maven dùng làm build runtime.
- Đảm bảo mọi dependency bên ngoài chạy trên Java đích.
- Kiểm tra đầy đủ mọi lỗi vận hành trên hệ điều hành, JVM vendor hoặc container.
- Tự bật preview features, tự nâng build plugin hoặc khắc phục xung đột dependency.

### 2.3. So sánh `--release` với `--source` và `--target`

| Cách khai báo | Giới hạn cú pháp? | Giới hạn class file? | Ngăn dùng API Java mới hơn release đích? |
| --- | --- | --- | --- |
| `--source 21` | Có | Không đủ nếu đứng một mình | **Không** |
| `--target 21` | Không đủ nếu đứng một mình | Có | **Không** |
| `--source 21 --target 21` | Có | Có | **Không** nếu đang biên dịch trên JDK mới hơn mà không giới hạn platform API |
| **`--release 21`** | Có | Có | **Có**, đối với API nền tảng được compiler hỗ trợ cho release 21 |
| **`--release 27`** | Có | Có | Giới hạn theo Java 27 |

Vì vậy, nếu không có ràng buộc bất thường từ một toolchain đặc thù, **ưu tiên `--release`** thay cho cặp `sourceCompatibility`/`targetCompatibility` đơn thuần trong dự án mới.

Javadoc của `javac` cũng chỉ rõ **không kết hợp `--release` với `--source` hay `--target` trong cùng invocation**. Nếu build plugin lỡ tạo ra hai bộ tham số xung đột, cần sửa cấu hình thay vì để compiler đoán ý.

### 2.4. `--release 27` và class file version

Với class Java 27 bình thường, **major class-file version là 71**. Có thể kiểm tra bằng công cụ từ JDK:

~~~~text
javac --release 27 ReleaseDemo.java
javap -verbose ReleaseDemo
~~~~

Trong output của `javap`, tìm:

~~~~text
major version: 71
~~~~

Kiểm tra major version có ích để xác minh artifact, nhưng **chưa đủ** để chứng minh tính tương thích API hoặc runtime: một JAR có thể gồm nhiều class, dependency có bytecode khác, native libraries hoặc cơ chế runtime riêng.

### 2.5. Không bật preview trong bài build ổn định

`--enable-preview` chỉ dành cho các tính năng preview **của chính release đang biên dịch** và cần runtime tương ứng bật preview. Theo phạm vi bài học Java 27 này, **không dùng preview hoặc incubating APIs làm cơ sở build sản phẩm ổn định**.

~~~~text
# Build mặc định của tài liệu này:
javac --release 27 ReleaseDemo.java
~~~~

Nếu dự án khác thực sự thử preview, cần quản lý riêng compiler/runtime flags và tính tương thích; không thêm `--enable-preview` một cách máy móc để “sửa” code không biên dịch được.

## 3. Java toolchain là gì?

**Java toolchain** là tập công cụ đến từ một JDK hoặc Java installation, có thể bao gồm `javac`, `java` và `javadoc`. Công cụ build chọn installation phù hợp với **yêu cầu được khai báo** của project hoặc task.

Toolchain giúp:

1. Làm rõ bản Java mà project cần.
2. Tránh phụ thuộc ngẫu nhiên vào JDK chạy build daemon.
3. Cho phép developer và CI dùng cùng **major Java version** cho công việc build.
4. Tách JVM chạy build tool khỏi JVM/compiler được dùng cho task.
5. Dễ kiểm chứng khi có nhiều JDK cài trên cùng máy.

**Giới hạn:** chỉ ghi toolchain major version **27** không nhất thiết chọn **cùng một vendor, bản vá, architecture hoặc JVM implementation** trên mọi máy. Với nhu cầu tái lập build nghiêm ngặt, còn phải quản trị những thuộc tính đó, plugin versions, dependency graph, toolchain provisioning và môi trường hệ điều hành.

### 3.1. Bộ quy tắc dễ nhớ

~~~~text
Toolchain: Chọn "javac nào?".
--release: Chọn "được dùng ngôn ngữ, bytecode và API phiên bản nào?".
Runtime tests: Xác minh "artifact thật chạy trên JVM nào?".
Dependency resolution: Xác minh "các JAR khác có tương thích không?".
~~~~

Không sử dụng riêng một trong bốn cơ chế rồi cho rằng nó đã bảo đảm tất cả những cơ chế còn lại.

## 4. Gradle: khai báo Java 27 trong `build.gradle.kts`

Đối với Gradle hiện đại, cách thường được khuyến nghị là khai báo **Java toolchain** trong Java plugin và đặt **compiler `options.release`** để ràng buộc rõ phiên bản phát hành.

### 4.1. Gradle Kotlin DSL: cấu hình khuyến nghị

Nội dung minh họa cho `build.gradle.kts`:

~~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(27)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(27)
    options.encoding = "UTF-8"
}
~~~~

**Hai dòng không đồng nghĩa:**

- `languageVersion = JavaLanguageVersion.of(27)` yêu cầu Gradle tìm **Java 27 toolchain**.
- `options.release.set(27)` chuyển mục tiêu tương đương **`javac --release 27`** cho các task `JavaCompile`.

`options.encoding = "UTF-8"` là cấu hình encoding của **mã nguồn Java**. Nó không thay thế cấu hình charset của tài nguyên, file JSON hoặc các ứng dụng chạy sau build.

Các plugin/thư viện bên ngoài có thể thêm task biên dịch riêng hoặc dùng compiler riêng. Nếu project dùng **Kotlin, Scala, Groovy, Android hoặc task tùy chỉnh**, phải kiểm tra tài liệu plugin và những task đó thay vì giả định mọi thứ đều tuân theo `JavaCompile`.

### 4.2. Gradle Groovy DSL: cấu hình tương đương

Nếu project dùng `build.gradle` thay cho Kotlin DSL:

~~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(27)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 27
    options.encoding = 'UTF-8'
}
~~~~

Đây là **hai lựa chọn DSL**, không phải hai file phải tạo cùng lúc. Dùng bản phù hợp với hệ thống build hiện có.

### 4.3. Toolchain project áp dụng đến các task nào?

Với Java plugin chuẩn, Gradle dùng toolchain project làm mặc định cho nhiều công việc liên quan Java:

- Biên dịch Java: `JavaCompile`.
- Chạy unit tests với `Test`.
- Tạo Javadoc.
- Những task Java do plugin chuẩn nối với toolchain khi có hỗ trợ.

Điều này không có nghĩa **mọi Java process** do script hoặc plugin bất kỳ khởi chạy đều tự dùng JDK 27. Một command gọi `java` bằng script OS, một task `Exec` tùy biến hoặc một plugin có cài đặt riêng vẫn có thể chạy bằng JVM khác.

### 4.4. Điều kiện hỗ trợ Gradle + Java 27

Theo ma trận tương thích chính thức của Gradle:

| Gradle version | Java 27 làm toolchain | Chạy Gradle daemon bằng Java 27 |
| --- | --- | --- |
| Trước **9.8.0** | **Không được cam kết chính thức** trong ma trận cho Java 27 | Không được cam kết chính thức |
| **9.8.0 trở lên** trong họ 9.x phù hợp | Có | Có |

Gradle **9.8.0** phát hành ngày **24/09/2026** và đánh dấu hỗ trợ Java 27 cho cả **toolchains lẫn Gradle daemon**. Đối với project mới, ưu tiên bản Gradle ổn định có bản vá bảo mật mới phù hợp với plugin ecosystem, **không cố định 9.8.0 chỉ vì đây là bản đầu tiên hỗ trợ**. Vào thời điểm biên soạn tháng 11/2026, ma trận Gradle trực tuyến phản ánh họ **9.9.x**, nhưng vẫn cần xem ma trận tại thời điểm nâng cấp.

Nguồn: [Gradle Java Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html), [Gradle 9.8.0 Release Notes](https://docs.gradle.org/9.8.0/release-notes.html).

**Đừng phỏng đoán rằng Gradle cũ vẫn chạy ổn chỉ vì JDK 27 có trên máy.** Gradle, Groovy, Kotlin DSL, bytecode parsing, test plugins và static analyzers có **khả năng tương thích riêng**; cần kiểm chứng tất cả khi nâng major Java.

## 5. Gradle Wrapper, tìm toolchain và JDK provisioning

### 5.1. Ưu tiên Gradle Wrapper

Một project có Gradle Wrapper thường có lệnh:

~~~~text
# Linux/macOS
./gradlew --version
./gradlew clean test
./gradlew build

# Windows PowerShell
.\gradlew.bat --version
.\gradlew.bat clean test
~~~~

Wrapper giúp nhóm và CI chọn cùng **phiên bản Gradle**, thay vì tùy thuộc `gradle` được cài trên máy. Phiên bản distribution được khai báo trong cấu hình wrapper, do nhóm nâng cấp và kiểm soát. Với Java 27, xác nhận wrapper sử dụng một Gradle được hỗ trợ **ít nhất từ 9.8.0**.

**Wrapper không tự khóa JDK 27** và không bảo đảm bản JDK trong CI đã có. Đó là trách nhiệm của toolchain và cách provisioning.

Để tăng tính an toàn của chuỗi build, quản lý wrapper scripts/binary theo quy định, kiểm tra checksum của Gradle distribution khi phù hợp, và không chấp nhận những thay đổi wrapper không được review. Không cần commit JDK binary của mọi nền tảng vào project.

### 5.2. Gradle tự tìm JDK ở đâu?

Gradle có **auto-detection** cho những JDK đã cài ở các vị trí thông dụng và qua một số cơ chế như `JAVA_HOME`, trình quản lý JDK, IDE hoặc cấu hình toolchain khác.

Kiểm tra những installation mà Gradle nhìn thấy:

~~~~text
./gradlew -q javaToolchains
~~~~

Output sẽ liệt kê thông tin như **language version**, vendor, architecture, installation path và nơi phát hiện. Để biết compiler nào thực sự được chọn cho task, có thể chạy build với log:

~~~~text
./gradlew compileJava --info
~~~~

**Lưu ý:** `./gradlew --version` cho biết JVM **đang chạy Gradle**, không tự xác nhận `JavaCompile` dùng compiler từ JDK 27. Hãy kiểm tra **cả hai**.

### 5.3. Tự tải JDK chỉ khi đã cấu hình resolver

Khai báo:

~~~~kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(27)
    }
}
~~~~

**không có nghĩa** Gradle chắc chắn tải JDK 27 từ Internet. Nếu không có JDK phù hợp được tìm thấy, auto-provisioning chỉ hoạt động khi project **đã cấu hình toolchain download repository/resolver**, môi trường cho phép mạng và resolver cung cấp bản JDK được yêu cầu.

Ví dụ có thể cấu hình **resolver plugin đã được phê duyệt** trong `settings.gradle.kts`, rồi dùng repository theo quy định của tổ chức. Tài liệu Gradle có ví dụ Foojay Toolchains Resolver Convention; version plugin phải được chọn theo ma trận tương thích và chính sách bảo mật hiện hành, không sao chép một con số cũ.

Đối với môi trường CI không có Internet, một phương án dễ kiểm soát là **cài sẵn JDK 27 trong build image** và để Gradle tự phát hiện. Với môi trường dùng artifact mirror nội bộ, nên cấu hình resolver/repository từ nguồn JDK được tổ chức tin cậy.

### 5.4. Cấu hình nơi Gradle tìm JDK

Nếu toolchain không được auto-detect, Gradle có thể nhận đường dẫn bằng một trong các Gradle properties:

~~~~properties
# Ví dụ gradle.properties cho agent có JDK theo path cụ thể.
org.gradle.java.installations.paths=/opt/jdks/jdk-27
~~~~

Hoặc cấu hình tên **biến môi trường**:

~~~~properties
org.gradle.java.installations.fromEnv=JDK27_HOME
~~~~

Đây là **hai cách thay thế**; dùng phương án phù hợp với môi trường. Những giá trị path minh họa không phải đường dẫn có sẵn trên mọi máy. Với cấu hình chung cho developer và CI, ưu tiên cách không hardcode đường dẫn OS-specific trong kho mã.

Gradle cũng có thể cache thông tin toolchain trong daemon. Nếu vừa thay đổi cấu hình JDK nhưng Gradle vẫn chọn installation cũ, hãy kiểm tra report `javaToolchains` và cân nhắc:

~~~~text
./gradlew --stop
./gradlew -q javaToolchains
~~~~

Chỉ nên dừng Gradle daemon khi phù hợp với môi trường đang thao tác, ví dụ trước khi thử build lại trên CI hoặc máy local.

### 5.5. Phân biệt toolchain project với JVM của Gradle daemon

| Cơ chế | Tác dụng chủ yếu |
| --- | --- |
| `java.toolchain.languageVersion` | Chọn installation Java cho các task có hỗ trợ toolchain |
| `options.release` | Đặt release mục tiêu của `javac` |
| `JAVA_HOME` | Ảnh hưởng JDK mặc định cho các công cụ dùng biến này |
| Gradle daemon JVM criteria / `org.gradle.java.home` | Liên quan JVM chạy Gradle daemon |
| IDE Gradle JVM | JVM IDE dùng để khởi chạy Gradle/daemon |

Ví dụ **daemon chạy Java 21**, compiler toolchain **Java 27** là một tình huống có thể hợp lệ nếu bản Gradle và plugin hỗ trợ cả hai. Nếu daemon đã chạy JDK 27 nhưng project toolchain được cấu hình JDK 21, việc compile có thể dùng compiler JDK 21 thay vì 27. Không suy luận compiler version chỉ từ output của `./gradlew --version`.

## 6. Gradle: compiler release và tương thích ngược

### 6.1. Một project muốn chạy trên Java 21, dù build bằng JDK 27

Đôi khi nhóm phát triển chuyển sang JDK 27 để tận dụng bản sửa lỗi và công cụ mới nhưng sản phẩm vẫn cần chạy trên Java 21. Khi đó:

~~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(27)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(21)
}
~~~~

Điều này có nghĩa: **dùng `javac` từ JDK 27, nhưng chỉ chấp nhận ngôn ngữ/class file/API nền tảng của Java 21**.

**Không** có nghĩa ứng dụng đã được kiểm thử trên runtime Java 21. Nếu hỗ trợ Java 21 là cam kết sản phẩm, còn cần:

1. Chạy unit/integration tests trên Java 21.
2. Bảo đảm dependency có hỗ trợ Java 21.
3. Kiểm tra framework, reflection, native libraries và các hành vi runtime.
4. Ghi rõ Java 21 là phiên bản tối thiểu trong metadata/phát hành.

`--release 21` không “hạ cấp” một JAR third-party được build cho Java 27. Nếu dependency có class file version 71, runtime Java 21 không thể tải nó chỉ vì code ứng dụng dùng release 21.

### 6.2. Gradle: chỉ định JVM cho task kiểm thử

Với một project cố ý biên dịch **`--release 21`** nhưng muốn xác minh trên **JVM 21**, có thể đặt Java launcher cho task `test`:

~~~~kotlin
import org.gradle.api.tasks.testing.Test

tasks.named<Test>("test") {
    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(21)
    })
}
~~~~

Đây là một **đoạn cấu hình bổ sung** vào project Gradle Kotlin DSL có Java plugin. Nó không thay thế cấu hình `JavaCompile` phía trên. Muốn test trên Java 21, CI phải có JDK 21 hoặc resolver được phép cung cấp nó.

Với bài học **Java 27**, nếu sản phẩm chỉ nhắm Java 27, không cần ép task test xuống Java 21. Cấu hình đơn giản nhất thường để Java plugin dùng toolchain Java 27 cho compile/test/Javadoc.

### 6.3. Nhiều module và nhiều target Java

Một workspace có các module:

~~~~text
core-api/        -> yêu cầu tương thích Java 21
server-app/      -> Java 27
build-logic/     -> plugin Gradle chạy trên JVM của Gradle
~~~~

Cấu hình toolchain và `--release` **theo từng project/task**, không đặt nhầm một bộ release 27 áp dụng lên thư viện cần hỗ trợ 21. Ví dụ `server-app` có thể phụ thuộc `core-api` được build release 21, nhưng chiều ngược lại phải tránh: `core-api` không nên phụ thuộc vào mã chỉ chạy trên Java 27 nếu cần tương thích 21.

Trong hệ thống plugin build, **build logic** cũng có yêu cầu JVM và version Gradle/Groovy/Kotlin DSL riêng. Nó không tự động dùng cùng target với code nghiệp vụ.

## 7. Maven 3: xác định compiler release Java 27

Trong Maven, một bước build thường chạy thông qua **plugins**, trong đó `maven-compiler-plugin` cung cấp task biên dịch. Với Maven 3 hiện hành, cách rõ ràng để khai báo Java 27 là:

~~~~xml
<properties>
    <maven.compiler.release>27</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~~

Nếu cần cố định version plugin và bảo đảm không vô tình dùng version mặc định khác giữa các máy, khai báo plugin:

~~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.16.0</version>
            <configuration>
                <release>27</release>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~~

Hai snippet này có thể cùng tồn tại trong `pom.xml`: property là cấu hình chung, plugin chỉ rõ compiler plugin/version và release. **`maven.compiler.release` là cách gọn**, còn `<configuration><release>27</release></configuration>` hữu ích nếu cần cấu hình tường minh trong plugin.

`maven-compiler-plugin` **3.16.0** là bản thuộc nhánh Maven Compiler Plugin 3.x đã được phát hành tháng 08/2026; nó không có nghĩa build tự động chạy trên JDK 27. Nếu `javac` thực tế quá cũ, build vẫn thất bại với thông báo như `release version 27 not supported`.

Nguồn: [Maven — Guide to Targeting a Java Version](https://maven.apache.org/guides/mini/guide-java-target.html), [Maven Compiler Plugin — Setting --release](https://maven.apache.org/plugins/maven-compiler-plugin-4.x/examples/set-compiler-release.html).

### 7.1. Vì sao property release khác với chọn Maven JDK?

~~~~text
mvn --version
    |
    v
JDK chạy tiến trình Maven (có thể là JDK 21)
    |
    v
maven-toolchains-plugin chọn JDK 27
    |
    v
maven-compiler-plugin dùng compiler được chọn
    |
    v
javac --release 27
~~~~

Nếu Maven **không** có toolchain và chạy bằng JDK 21, chỉ thêm `maven.compiler.release=27` không khiến JDK 27 xuất hiện. Thuộc tính release là **yêu cầu của compiler**, không phải JDK installer.

### 7.2. Maven 4 không dùng cùng lời khuyên cấu hình trong mọi trường hợp

Maven Compiler Plugin **4.x** yêu cầu **Maven 4**; tài liệu chính thức của nhánh này ưu tiên mô hình `<sources><source><targetVersion>...</targetVersion></source></sources>` để mô tả release theo source. Vào thời điểm soạn bài, dòng Maven Compiler Plugin 4.x còn được công bố dưới dạng **beta**, nên các ví dụ production trong bài chọn **Maven 3 + Compiler Plugin 3.x** đã phát hành ổn định.

Không sao chép cấu hình `<sources>` của Maven 4 vào một project Maven 3 rồi mong nó hoạt động. Nếu tổ chức chuyển lên Maven 4 ổn định, cần đối chiếu tài liệu đúng phiên bản Maven/Compiler Plugin và quy trình migration.

## 8. Maven Toolchains Plugin: chọn JDK 27 thay vì chỉ đặt release

Maven Toolchains Plugin cho phép các plugin tương thích sử dụng **JDK khác JDK chạy Maven**. Maven Toolchains Plugin từ 3.2.0 có cơ chế tự phát hiện JDK; ví dụ dưới đây dùng **3.3.0**, một bản hiện hành theo tài liệu chính thức.

### 8.1. Cấu hình chọn toolchain Java 27

Trong `pom.xml` của Maven 3:

~~~~xml
<properties>
    <maven.compiler.release>27</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <toolchain.jdk.version>[27,28)</toolchain.jdk.version>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-toolchains-plugin</artifactId>
            <version>3.3.0</version>
            <executions>
                <execution>
                    <goals>
                        <goal>select-jdk-toolchain</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>

        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.16.0</version>
            <configuration>
                <release>27</release>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~~

Đây là **các phần tử đặt bên trong phần tử `<project>` của POM hợp lệ**, không phải tệp XML độc lập hoàn chỉnh.

- `toolchain.jdk.version=[27,28)` chọn phiên bản thuộc khoảng **Java 27.x**, không nhận Java 28.
- Goal `select-jdk-toolchain` tự gắn với phase **`validate`** theo plugin descriptor, nên được chạy trước phase `compile` trong một lifecycle build thông thường.
- Toolchains Plugin tìm JDK đã cài ở những vị trí/biến môi trường được hỗ trợ, hoặc mục được mô tả tường minh trong `~/.m2/toolchains.xml`.
- Compiler Plugin 3.x dùng toolchain mà Maven đã chọn khi có hỗ trợ, rồi áp dụng `release=27`.

Nếu chọn được toolchain Java 27 nhưng **Maven plugin khác** (ví dụ test hoặc Javadoc) được cấu hình chạy JDK khác, phải kiểm tra thêm. Chọn compiler toolchain **không có nghĩa** mọi plugin của bên thứ ba đều tự tuân theo nó.

### 8.2. Maven không tự tải JDK 27 chỉ từ `select-jdk-toolchain`

Toolchains Plugin **khám phá/chọn các JDK có sẵn** theo tiêu chí; nó không phải downloader JDK tương tự Gradle toolchain resolver. Vì vậy CI cần:

1. Cài/cung cấp JDK 27 qua machine image, package manager hoặc build environment đã được kiểm soát.
2. Đảm bảo Maven có thể phát hiện installation.
3. Chọn một toolchain khớp Java 27.
4. Kiểm tra compiler và test runtime thực tế.

Nếu có nhiều JDK cùng major 27, selection có thể dựa trên các tiêu chí bổ sung về vendor, version, môi trường và comparator. Muốn bản vá/vendor chính xác để tái lập build, phải thêm chính sách cung cấp JDK cụ thể ở tầng CI/infra.

### 8.3. Kiểm tra JDK Maven nhìn thấy

~~~~text
mvn --version

mvn org.apache.maven.plugins:maven-toolchains-plugin:3.3.0:display-discovered-jdk-toolchains

mvn -X compile
~~~~

**Giải thích:**

- `mvn --version`: JVM **đang chạy Maven**.
- `display-discovered-jdk-toolchains`: các JDK Maven Toolchains Plugin **có thể phát hiện**.
- `mvn -X compile`: log chi tiết để xem Maven plugin/toolchain được chọn, compiler và flags.

Các lệnh thực thi trong thư mục có `pom.xml` hợp lệ (trừ `mvn --version` có thể dùng ở nơi khác). Không cần bật debug thường trực ở CI nếu log có thể chứa đường dẫn hoặc thông tin cấu hình nhạy cảm; chỉ bật khi cần chẩn đoán.

### 8.4. Maven Surefire và test JVM

Theo tài liệu **Maven Surefire Plugin**, khi POM đã chọn main toolchain bằng Toolchains Plugin, Surefire có thể dùng toolchain được chọn làm JVM thực thi test. Nó còn hỗ trợ `<jdkToolchain>` riêng khi cần chạy test trên một JDK khác.

Vì vậy, nếu build `--release 27` nhưng máy Maven chạy JDK 21, **không được chạy test classes Java 27 bằng JDK 21**. Hãy xác minh forked test JVM là JDK 27 và version của Surefire/Failsafe có hỗ trợ môi trường thực tế. Chạy `mvn test` hoặc `mvn verify` và kiểm tra log trong tình huống migration.

Nguồn: [Maven Surefire — Using Maven Toolchains](https://maven.apache.org/surefire/maven-surefire-plugin/examples/toolchains), [Maven Toolchains Plugin — JDK Discovery](https://maven.apache.org/plugins/maven-toolchains-plugin/toolchains/jdk-discovery.html).

## 9. Một ví dụ `pom.xml` có thể dùng làm điểm khởi đầu

Đây là **POM minh họa đầy đủ** cho ứng dụng Java 27 đơn giản bằng **Maven 3**. Khi áp dụng vào dự án thật, thay groupId/artifactId/version và bổ sung dependencies/plugins theo nhu cầu:

~~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>java27-app</artifactId>
    <version>1.0.0</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>27</maven.compiler.release>
        <toolchain.jdk.version>[27,28)</toolchain.jdk.version>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-toolchains-plugin</artifactId>
                <version>3.3.0</version>
                <executions>
                    <execution>
                        <goals>
                            <goal>select-jdk-toolchain</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.16.0</version>
                <configuration>
                    <release>27</release>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~~

Ví dụ có thể dùng với cấu trúc project Maven tiêu chuẩn:

~~~~text
java27-app/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── App.java
~~~~

Nội dung `src/main/java/com/example/App.java` để thử:

~~~~java
package com.example;

import java.util.List;
import java.util.stream.Gatherers;

public class App {
    public static void main(String[] args) {
        System.out.println(List.of(1, 2, 3, 4, 5)
                .stream()
                .gather(Gatherers.windowFixed(2))
                .toList());
    }
}
~~~~

Với **Maven đã cài** và **JDK 27 được công cụ phát hiện**:

~~~~text
mvn clean package
~~~~

**Kỳ vọng:** Plugin Toolchains chọn JDK 27 trước khi Compiler Plugin biên dịch; `App.class` được tạo với release 27. `mvn package` tự tạo một JAR theo cấu hình packaging mặc định, nhưng **không tự sinh executable/fat JAR có Main-Class và tất cả dependencies**. Để chạy bằng `java -jar`, phải cấu hình manifest/plugin đóng gói tương ứng.

Nếu chỉ muốn kiểm tra class biên dịch trong ví dụ, dùng:

~~~~text
java -cp target/classes com.example.App
~~~~

Lệnh `java` này phải trỏ tới **runtime Java 27 hoặc mới hơn phù hợp**, không tự được Maven toolchain điều khiển chỉ vì trước đó đã chạy `mvn package`. Việc chạy lệnh trong terminal và việc Maven chọn `javac` là hai câu chuyện khác nhau.

## 10. Tương thích mã nguồn chưa đủ: dependency, plugin và runtime

### 10.1. Dependency có thể yêu cầu Java cao hơn

Giả sử code của bạn được biên dịch bằng `javac --release 21` trên JDK 27 nhưng sử dụng một thư viện third-party được build bằng `--release 27`. **Compiler release của code ứng dụng không hạ cấp bytecode của thư viện ấy**.

~~~~text
app.jar: Java 21 class files
    |
    +--> library.jar: Java 27 class files
             |
             v
    Máy chủ chỉ có Java 21
             |
             v
    Có nguy cơ UnsupportedClassVersionError khi tải lớp thư viện
~~~~

Vì vậy phải phân biệt:

| Thành phần | Giới hạn riêng cần kiểm tra |
| --- | --- |
| Mã Java của project | `--release` cho các `JavaCompile`/Compiler Plugin |
| Các dependency JAR | Minimum Java release và class file versions của thư viện |
| Runtime JVM | Phiên bản thực tế chạy ứng dụng |
| Build plugins | Phiên bản Gradle/Maven và JVM của build process |
| Annotation processors | Khả năng chạy trên compiler/JDK, khả năng sinh mã hợp lệ |
| Test tools | Engine, compiler support, bytecode agents/instrumentation |
| Native libraries | OS, architecture, ABI, JNI/FFM và runtime phù hợp |

Không gắn nhãn “Java 21 compatible” cho cả artifact chỉ vì **một module** được build release 21. Cần kiểm tra **cả runtime dependency graph** và quy trình đóng gói.

### 10.2. `--release` bảo vệ API nền tảng, không phải mọi thư viện trên classpath

`--release` ngăn code dùng các API JDK/Java SE của **release mới hơn mục tiêu**. Tuy nhiên, nó không tự kiểm tra một dependency có mang:

- Những class file được biên dịch cho Java mới hơn.
- Lời gọi `Class.forName` hoặc reflection đến API chỉ có trên Java mới.
- Native library chỉ hỗ trợ kiến trúc khác.
- Resource/config sử dụng tính năng runtime không tương thích.
- Trình tự hoạt động phụ thuộc một behavior JVM/vendor đặc thù.

Cách xác minh là **kiểm thử trên runtime đích** cùng bộ dependency thực tế. Nếu hỗ trợ nhiều Java releases, cần CI matrix theo các phiên bản đó.

### 10.3. Internal JDK APIs không phải giải pháp thay toolchain

Các class nội bộ như `jdk.internal.*` và những package không được xuất công khai **không phải API tương thích ổn định** để dùng trong ứng dụng. Với `--release`, `javac` chỉ công bố API nền tảng thích hợp cho release và hạn chế các cách phá encapsulation để truy cập internal classes.

Không “sửa” build Java 27 bằng cách thêm hàng loạt `--add-exports`/`--add-opens` nếu thư viện đang dựa vào internal APIs; hãy đánh giá thư viện có bản tương thích với Java 27 và APIs đã được công bố hay không.

### 10.4. Annotation processors và bytecode instrumentation

Build Java 27 thường có các công cụ:

- Annotation processors sinh Java source/classes.
- Coverage tools hoặc bytecode manipulators.
- Test mocking/instrumentation frameworks.
- Static analyzers, style checkers.
- IDE compilers và annotation processing tích hợp.

Những công cụ này có thể cần cập nhật để đọc/ghi class file version 71 hoặc nhận biết cú pháp/construct mới. **Compiler hỗ trợ Java 27 không tự đồng nghĩa mọi plugin hỗ trợ Java 27**. Gradle release notes cũng nêu rằng một số third-party tools chưa hỗ trợ Java 27 ngay ở thời điểm Gradle bắt đầu hỗ trợ.

Khi nâng JDK:

1. Nâng Gradle/Maven/Compiler Plugin lên phiên bản tương thích.
2. Kiểm tra toolchain resolution trên developer và CI.
3. Nâng processor/instrumentation plugin theo release notes chính thức.
4. Biên dịch cả main và test sources.
5. Chạy bộ kiểm thử trên JVM 27 và smoke test artifact đã đóng gói.

## 11. IDE, local và CI: cùng một hợp đồng build

### 11.1. IDE có nhiều “Java version” khác nhau

Trong IDE hiện đại, có thể cấu hình:

| Thiết lập IDE | Đối tượng ảnh hưởng |
| --- | --- |
| **Project SDK** | Hỗ trợ language model, code completion và một số công việc IDE |
| **Gradle JVM** | JVM chạy Gradle import/build/daemon trong IDE |
| **Maven runner JDK** | JVM chạy Maven từ IDE |
| **Java compiler bytecode target** | Đầu ra khi IDE biên dịch bằng cơ chế riêng |
| **Test Run Configuration JRE** | Runtime của test hoặc ứng dụng khi launch từ IDE |

Nếu IDE dùng compiler riêng thay vì ủy quyền cho Gradle/Maven, thiết lập của IDE có thể khác với build chính thức. Với project có wrapper, nên **ủy quyền build/test cho công cụ build** theo quy ước nhóm để giảm sai lệch.

Lỗi thường gặp: IDE nhận ra Java 27, viết được code dùng API mới, nhưng CI thực thi Gradle/Maven trên một compiler khác và từ chối code. Đây là lý do **version thuộc về cấu hình project**, không chỉ settings của IDE.

### 11.2. Checklist CI trước khi compile

Một pipeline hỗ trợ Java 27 có thể thực hiện các bước:

1. Lấy đúng source revision và xác minh wrapper/scripts.
2. Cung cấp JDK 27 qua image/toolchain resolver được phê duyệt.
3. Kiểm tra JVM chạy build tool và JDK dùng compile.
4. Resolve dependencies/plugins từ repository có kiểm soát.
5. Compile/test/package bằng wrapper hoặc Maven version đã khóa.
6. Kiểm tra class file version của output khi cần.
7. Chạy smoke tests bằng **JVM dùng cho production**.
8. Công bố artifact cùng metadata về target runtime và dependency versions.

Không dùng `java --version` **một mình** làm bằng chứng rằng `javac --release 27` đã được áp dụng.

### 11.3. Ví dụ bước xác minh cho Gradle trên CI

~~~~text
# CI đã được cấp JDK 27 hoặc resolver cấu hình phù hợp.
java --version
javac --version

./gradlew --version
./gradlew -q javaToolchains

# Build/test từ source bằng wrapper:
./gradlew clean test
./gradlew build

# Nếu build.gradle.kts ở ví dụ khai báo release 27:
./gradlew compileJava --info
~~~~

Những lệnh này là **hướng dẫn**, không yêu cầu chạy trên repository của bài học. Trên Windows, thay `./gradlew` bằng `.\gradlew.bat`. Nếu kết quả `java --version` là JDK 21 nhưng compile toolchain được cấu hình và chọn JDK 27, đó chưa chắc là lỗi; cần xem môi trường CI có chủ đích tách daemon/runtime khỏi toolchain hay không.

Để xem bytecode của class đã build (ví dụ project dùng Java plugin):

~~~~text
javap -verbose -classpath build/classes/java/main com.example.App
~~~~

Kiểm tra `major version: 71` nếu class ấy thật sự biên dịch theo release 27. Đường dẫn output có thể khác nếu build plugin hoặc cấu trúc source set tùy chỉnh.

### 11.4. Ví dụ bước xác minh Maven trên CI

~~~~text
mvn --version
mvn org.apache.maven.plugins:maven-toolchains-plugin:3.3.0:display-discovered-jdk-toolchains

# POM đã khai báo Toolchains/Compiler Plugins:
mvn -B -V clean verify

# Kiểm tra một class đã build:
javap -verbose -classpath target/classes com.example.App
~~~~

`-B` dùng batch mode và `-V` hiển thị Maven version. Với Maven Wrapper, dùng `./mvnw` hoặc `.\mvnw.cmd` thay `mvn` tùy OS. Điều quan trọng là runtime để chạy `javap` đủ mới để đọc class file version 71.

**Đừng** cho rằng chọn toolchain thành công ở phase `validate` đã chứng minh mọi plugin chạy trên JDK 27. Hãy kiểm tra log test runner, Javadoc, code generator hoặc task tùy chỉnh nếu chúng cần Java cụ thể.

### 11.5. Khóa wrapper, plugin và repository

Toolchain version chỉ là một yếu tố của **build reproducibility**. Để giảm sự khác biệt giữa developer và CI:

- **Gradle:** quản lý Wrapper distribution, kiểm tra distribution checksum khi dùng, cố định versions của plugins và dependencies khi phù hợp.
- **Maven:** quản lý Maven Wrapper/phiên bản Maven, khai báo version của compiler/toolchains/test plugins, kiểm soát dependency versions.
- Chỉ dùng artifact repositories/miền tải toolchain đã được phê duyệt; không mở nguồn tải JDK/JAR tùy ý cho mọi request build.
- Cân nhắc dependency lock/verification, SBOM, build attestation và cơ chế provenance theo chính sách của tổ chức.
- Ghi nhận JDK vendor, update version, OS và architecture của build agents khi cần tái hiện bug.

Không tự coi **major=27** là một cam kết reproducible byte-for-byte. Khác bản vá JDK, locale, timezone, plugin hoặc dependency vẫn có thể tạo hành vi khác nhau.

## 12. Kiểm tra runtime đích bằng chính chương trình Java

Một cách giúp smoke test xác nhận môi trường thực thi là đọc `Runtime.version()`:

~~~~java
public class RuntimeVersionCheck {
    public static void main(String[] args) {
        int feature = Runtime.version().feature();
        System.out.println("Java feature version: " + feature);

        if (feature != 27) {
            throw new IllegalStateException(
                    "This test environment requires exactly Java 27");
        }
    }
}
~~~~

Điều kiện `feature != 27` là **chính sách của bài kiểm thử** khi muốn test đúng Java 27, không phải bắt buộc chung cho mọi ứng dụng. Nếu sản phẩm công bố hỗ trợ runtime **27 trở lên**, có thể dùng:

~~~~java
if (Runtime.version().feature() < 27) {
    throw new IllegalStateException("Requires Java 27 or later");
}
~~~~

Phần mềm build bằng `--release 27` có thể chạy trên Java mới hơn **nếu** vẫn giữ tương thích và dependency phù hợp, nhưng phải kiểm thử các runtime được công bố hỗ trợ. Không suy ra mọi Java tương lai đều sẽ chạy mọi binary Java 27 trong mọi môi trường.

### 12.1. Kiểm thử phiên bản tối thiểu không phải kiểm thử toàn bộ tương thích

Code ở trên giúp phát hiện “đang chạy nhầm JVM”. Nó **không** phát hiện:

- Tất cả dependency dùng API không tương thích.
- Khác biệt behavior của DB driver hoặc TLS provider.
- Native library sai architecture.
- Vấn đề module access/reflection.
- Vấn đề concurrency hoặc khác biệt JIT/runtime.

Với production, cần test end-to-end/smoke thật cùng mô hình triển khai, không dừng ở kiểm tra version number.

## 13. Ma trận lựa chọn cấu hình

| Mục tiêu | JDK toolchain | Compiler release | Test runtime | Lưu ý |
| --- | --- | --- | --- | --- |
| Ứng dụng chỉ cần Java 27 | **27** | **27** | 27 | Cấu hình mặc định của bài |
| Library muốn hỗ trợ Java 21 dù đội dùng JDK 27 | **27** | **21** | 21 + 27 khi phù hợp | Kiểm tra dependencies có hỗ trợ 21 |
| Một module yêu cầu Java 27, module core hỗ trợ 21 | Theo từng module | 27 / 21 | Theo từng artifact | Không ép module core lên 27 |
| CI chạy Maven bằng JDK 21, compile code Java 27 | **27** qua toolchains | **27** | 27 | Maven JVM và compiler JVM khác nhau |
| Gradle daemon chạy JDK 21, compile Java 27 | **27** qua Gradle toolchain | **27** | 27 | Yêu cầu Gradle có hỗ trợ tương ứng |
| Chỉ đặt `JAVA_HOME=27`, không có toolchain/release | Không được ràng buộc | Không được ràng buộc | Không rõ | Khó lặp lại giữa các máy |
| Muốn chạy Java 27 nhưng compiler chỉ là JDK 21 | Không phù hợp | `27` không được hỗ trợ | — | Cần cung cấp compiler Java 27 |

Để chọn đúng, hãy bắt đầu từ **hợp đồng runtime của sản phẩm**, rồi mới xác định toolchain và release. Không chọn release theo JDK “tình cờ được cài gần nhất”.

## 14. Chẩn đoán lỗi thường gặp

### 14.1. `invalid target release: 27` hoặc `release version 27 not supported`

**Triệu chứng:** compiler từ chối mục tiêu Java 27 dù POM/Gradle script đã khai báo 27.

**Nguyên nhân thường gặp:**

- Compiler thực tế là JDK **nhỏ hơn 27**.
- Gradle/Maven không chọn được toolchain JDK 27 nên vẫn dùng compiler từ build JVM.
- IDE dùng Java compiler khác với CLI.
- Plugin không hỗ trợ phát hành Java 27 hoặc truyền flags không đúng.

**Cách điều tra:**

~~~~text
javac --version
java --version

# Gradle
./gradlew --version
./gradlew -q javaToolchains
./gradlew compileJava --info

# Maven
mvn --version
mvn org.apache.maven.plugins:maven-toolchains-plugin:3.3.0:display-discovered-jdk-toolchains
mvn -X compile
~~~~

**Cách sửa:** cung cấp JDK 27 thực sự và chọn nó qua toolchain được hỗ trợ, hoặc nâng công cụ build tương thích. Không đổi `--release 27` xuống 21 chỉ để build tạm chạy nếu sản phẩm phải sử dụng Java 27.

### 14.2. Gradle báo không tìm được matching toolchain

Ví dụ nội dung lỗi thường có ý nghĩa “No matching toolchains found” hoặc “No locally installed toolchains match requested specification”.

Kiểm tra theo thứ tự:

1. JDK 27 đã được cài trên máy/CI hay chưa?
2. `./gradlew -q javaToolchains` có phát hiện installation JDK 27?
3. Đường dẫn JDK trỏ tới **JDK đầy đủ** hay chỉ JRE?
4. Nếu muốn tự download, đã có **toolchain resolver repository** được cấu hình trong Gradle settings chưa?
5. Mạng và quyền tải artifact có cho phép không?
6. Phiên bản Gradle có hỗ trợ Java 27 chưa?
7. Gradle daemon có cache cấu hình JDK cũ không?

Không khắc phục bằng cách xóa ngẫu nhiên Gradle caches hoặc thêm một URL tải không tin cậy. Hãy xem rõ lỗi discovery/provisioning và sửa đúng nguồn.

### 14.3. Maven `mvn --version` báo JDK 21 dù POM chọn 27

Điều này **không nhất thiết sai**: Maven Toolchains Plugin có thể chọn compiler JDK 27 khác với JVM chạy Maven. Xác nhận plugin `select-jdk-toolchain` thực thi ở phase `validate` và Maven Compiler Plugin sử dụng toolchain đã chọn.

Tuy nhiên, nếu một plugin build/test nào đó **không hỗ trợ toolchain**, nó có thể vẫn chạy bằng JDK 21 và gặp lỗi với Java 27. Đây là vấn đề plugin/task-specific, không nên kết luận toàn bộ Maven build đã chạy JDK 27.

### 14.4. `UnsupportedClassVersionError` lúc chạy

Một runtime quá cũ có thể báo đã gặp class file major version **71** nhưng chỉ hỗ trợ đến một major version thấp hơn.

Ví dụ:

~~~~text
Ứng dụng được biên dịch release 27
          |
          v
    java -version -> 21
          |
          v
UnsupportedClassVersionError
~~~~

**Hướng xử lý:** chạy ứng dụng bằng JVM phù hợp **Java 27** hoặc thay đổi mục tiêu release và dependencies nếu hợp đồng sản phẩm thực sự chỉ cần Java thấp hơn. Không thể sửa lỗi bằng `-Xmx`, thay classpath ngẫu nhiên hoặc đổi tên JAR.

Lưu ý đôi khi **chính dependency** chứ không phải lớp do project biên dịch mang class file version cao hơn. Đọc thông báo tên class và kiểm tra cả dependency graph.

### 14.5. Build thành công nhưng test thất bại vì Java version

Kiểm tra:

- JVM được test runner thực sự sử dụng (không chỉ JVM chạy Maven/Gradle).
- Các plugin fork JVM có nhận toolchain không.
- Unit test và integration test có cấu hình launch khác nhau không.
- Có annotation agent/instrumentation dùng bytecode parser chưa hỗ trợ Java 27 không.
- Có dependency native hoặc JDK internal API không tương thích không.

**Không bỏ toàn bộ test bằng `-DskipTests` hoặc `-x test` rồi coi build đạt yêu cầu.** Có thể dùng cách đó cho chẩn đoán giới hạn, nhưng phát hành cần pipeline kiểm thử đúng runtime.

### 14.6. `--release 21` nhưng code gọi API Java 24+

Nếu compiler báo không tìm thấy `Gatherers` khi build với `--release 21`, đó thường là **hành vi đúng**: API này được bổ sung ở một release mới hơn 21. Hãy quyết định:

- **Giữ hỗ trợ Java 21:** thay code bằng API đã có trong Java 21 hoặc implementation tương thích.
- **Chuyển sản phẩm lên Java 27:** đổi hợp đồng target thành 27, nâng dependencies và CI/runtime rồi kiểm thử.

Không chuyển sang cặp `--source 21 --target 21` để lách kiểm tra API. Cách đó có thể tạo artifact trông như tương thích Java 21 nhưng nổ `NoSuchMethodError` hoặc `NoClassDefFoundError` khi chạy trên Java 21.

### 14.7. Compiler flags mâu thuẫn

Không kết hợp `--release` với `--source` hoặc `--target` như các compiler options độc lập trong cùng invocation. Khi Gradle/Maven plugin cấu hình một release mà plugin khác thêm flags cũ, hãy **hợp nhất về một policy duy nhất**.

Trong Gradle, ưu tiên:

~~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.release.set(27)
}
~~~~

Trong Maven 3:

~~~~xml
<properties>
    <maven.compiler.release>27</maven.compiler.release>
</properties>
~~~~

Không bổ sung các flags `-source`/`-target` thừa từ một cấu hình sao chép cũ nếu không có yêu cầu tương thích đặc biệt.

## 15. Các bẫy cần tránh khi bảo trì cấu hình Java 27

| Bẫy | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Chỉ cập nhật `JAVA_HOME` của developer | CI và IDE có thể dùng JDK khác | Khai báo toolchain và release trong project |
| Chỉ đặt `sourceCompatibility=27` | Không ràng buộc chắc API/target/compiler như `--release` | Dùng toolchain + `options.release` |
| Chỉ đặt `targetCompatibility=27` | Compiler/JDK/API có thể không đồng bộ | Dùng `--release` |
| Chỉ thêm `maven.compiler.release=27` khi Maven dùng JDK 21 | Compiler JDK21 không hỗ trợ release 27 | Chọn JDK27 bằng Maven toolchain |
| Dùng Gradle cũ với JDK 27 | Có thể lỗi daemon hoặc toolchain chưa được hỗ trợ | Kiểm tra compatibility matrix, dùng Gradle 9.8+ phù hợp |
| Dùng Gradle Wrapper nhưng không khai báo Java toolchain | Gradle version được khóa nhưng compiler vẫn có thể khác | Dùng cả Wrapper và toolchain |
| Nghĩ Gradle luôn tự tải JDK | Thiếu resolver/repository thì provisioning không hoạt động | Cấu hình resolver hoặc cài sẵn JDK |
| Chỉ chạy `./gradlew --version` | Chỉ thấy JVM chạy Gradle | Kiểm tra `javaToolchains` và compile log |
| Chỉ chạy `mvn --version` | Chỉ thấy JVM chạy Maven | Kiểm tra selected toolchain/compiler |
| Đặt version range toolchain quá rộng | CI có thể chọn JDK khác major mong muốn | Dùng `[27,28)` hoặc tiêu chí tương đương |
| Dùng `--release 21` nhưng dependency yêu cầu JDK27 | Runtime21 không tải được dependency | Kiểm tra bytecode và dependency minimum Java |
| Coi compile thành công là đã chạy test trên Java27 | Test runner có thể dùng JVM khác | Xác nhận test JVM/smoke deployment |
| Bật `--enable-preview` để biên dịch lỗi | Đưa API preview vào sản phẩm không có chủ đích | Giữ cấu hình stable, sửa đúng code/version |
| Hardcode JDK installation path trong script chung | Khó chạy trên OS/CI khác | Sử dụng discovery/biến môi trường được chuẩn hóa |
| Cho compiler JDK27 chạy với plugin bytecode cũ | Plugin có thể không hiểu class file 71 | Kiểm tra hỗ trợ và nâng plugin |
| Dùng JDK từ nguồn tải chưa kiểm chứng | Nguy cơ chuỗi cung ứng | Kiểm soát distribution, checksum và provenance |
| Không quản lý Maven/Gradle plugin versions | Kết quả build khác theo môi trường | Pin plugin/wrapper/dependency versions |
| Thay compiler target trong một module core để sửa lỗi module khác | Phá vỡ tương thích của core | Tách release theo module và ràng buộc dependency đúng |

## 16. Bài tập thực hành có kiểm chứng

### Bài tập A — Phân biệt compiler JDK với release

1. Cài **JDK 27** trong môi trường test.
2. Tạo `ReleaseDemo.java` ở mục 2.
3. Chạy `javac --release 27 ReleaseDemo.java`; ghi nhận mã biên dịch thành công.
4. Chạy `javap -verbose ReleaseDemo`; xác nhận `major version: 71`.
5. Đổi `--release 21` khi compile nguồn có `Gatherers`; quan sát compiler từ chối API chưa có trên Java 21.

**Kết luận mong đợi:** `--release` không chỉ ảnh hưởng bytecode, nó còn chặn sử dụng API nền tảng ngoài hợp đồng release.

### Bài tập B — Gradle tách daemon JVM và toolchain

1. Dùng Gradle Wrapper version có hỗ trợ Java 27.
2. Khai báo `JavaLanguageVersion.of(27)` trong `build.gradle.kts`.
3. Khai báo `options.release.set(27)`.
4. Chạy `./gradlew --version` và `./gradlew -q javaToolchains`.
5. Chạy `./gradlew compileJava --info`.
6. Ghi lại **JVM daemon** và **compiler toolchain** thực sự được dùng.

**Kết luận mong đợi:** version chạy Gradle và version được compiler task sử dụng là hai thuộc tính cần kiểm tra riêng.

### Bài tập C — Maven Toolchains Plugin

1. Có sẵn **JDK 27** trong máy/CI.
2. Sử dụng POM ở mục 9 với Maven 3 và plugins đã khai báo.
3. Chạy `display-discovered-jdk-toolchains`.
4. Chạy `mvn -B -V clean verify`.
5. Kiểm tra log `select-jdk-toolchain` và compiler release.

**Kết luận mong đợi:** Maven có thể chạy trên một JVM khác nhưng compiler được chọn vẫn là JDK 27.

### Bài tập D — Đảm bảo tương thích Java 21

1. Giữ compiler toolchain JDK 27.
2. Đổi target của một module library từ `--release 27` sang `--release 21`.
3. Cố biên dịch code sử dụng `Gatherers`; xem lỗi vì Java 21 chưa có API này.
4. Thay bằng code chỉ sử dụng API Java 21.
5. Chạy test của library trên JVM 21 và xác minh toàn bộ dependencies tương thích.

**Kết luận mong đợi:** việc chặn API mới hơn là tính năng bảo vệ tương thích, không phải một “vấn đề của Gradle/Maven” cần lách qua.

## 17. Checklist trước khi phát hành Java 27

- [ ] Đã xác định **minimum supported Java runtime** thật sự của sản phẩm.
- [ ] Có Java 27 JDK/compiler được quản trị, không chỉ JRE hoặc biến môi trường mơ hồ.
- [ ] Gradle Wrapper/Maven version hỗ trợ Java 27.
- [ ] Gradle toolchain hoặc Maven Toolchains Plugin chọn đúng JDK 27.
- [ ] Compiler release được khai báo tường minh bằng `--release 27` hoặc cấu hình plugin tương đương.
- [ ] Không trộn `--release` với các cặp source/target flags mâu thuẫn.
- [ ] IDE, CLI và CI có chính sách đồng nhất về toolchain/compilation.
- [ ] Đã xem compiler/toolchain logs; không chỉ xem JVM chạy build tool.
- [ ] Main classes, test classes và generated classes được biên dịch theo target đúng.
- [ ] Test runner và integration/smoke environment dùng runtime Java 27.
- [ ] Mọi runtime dependencies hỗ trợ Java 27 hoặc minimum release công bố.
- [ ] Annotation processors, bytecode tools, coverage và test plugins hiểu Java 27.
- [ ] Có kiểm tra class file version khi cần chứng minh compatibility.
- [ ] Toolchain provisioning đến từ repository/JDK distribution được phê duyệt.
- [ ] Gradle/Maven Wrapper và plugin/dependency versions được quản lý.
- [ ] Không bật preview features chỉ để vượt compiler errors.
- [ ] Nếu build đa module/đa release, từng module có target nhất quán với API mà nó công bố.
- [ ] CI ghi nhận đủ thông tin để điều tra sai khác OS, vendor, architecture và JDK patch.
- [ ] Có kiểm thử thật trên JVM mà artifact sẽ được triển khai.

## 18. Tài liệu chính thức

- [Oracle Java SE 27 — `javac` Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html): `--release`, `--source`, `--target`, giới hạn API nền tảng và những tùy chọn xung đột.
- [Oracle Java SE 27 — Preview Features](https://docs.oracle.com/en/java/javase/27/language/preview-language-vm-features.html): lý do preview cần bật riêng; phạm vi bài này không sử dụng preview.
- [Oracle JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): những thay đổi và trạng thái bản Java 27.
- [Gradle — Java Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html): hỗ trợ Java 27 cho Gradle runtime/toolchains từ 9.8.0.
- [Gradle 9.8.0 Release Notes](https://docs.gradle.org/9.8.0/release-notes.html): ngày phát hành và hỗ trợ Java 27.
- [Gradle — Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html): `java.toolchain`, `JavaCompile.options.release`, auto-detection, auto-provisioning và debug.
- [Gradle — Building Java & JVM Projects](https://docs.gradle.org/current/userguide/building_java_projects.html): so sánh toolchains, compiler release và source/target compatibility.
- [Apache Maven — Guide to Targeting a Java Version](https://maven.apache.org/guides/mini/guide-java-target.html): `maven.compiler.release` và API compatibility.
- [Apache Maven — Compiler Plugin 3.x](https://maven.apache.org/plugins/maven-compiler-plugin/): version Compiler Plugin và hướng dẫn cấu hình.
- [Apache Maven — Toolchains Plugin](https://maven.apache.org/plugins/maven-toolchains-plugin/): chọn JDK độc lập với Maven runtime.
- [Apache Maven — JDK Discovery Mechanism](https://maven.apache.org/plugins/maven-toolchains-plugin/toolchains/jdk-discovery.html): phát hiện installation, `toolchain.jdk.version` và `select-jdk-toolchain`.
- [Apache Maven — Surefire with Toolchains](https://maven.apache.org/surefire/maven-surefire-plugin/examples/toolchains): JVM dùng để chạy unit tests.

**Kết luận:** Một dự án **Java 27** đáng tin cậy không chỉ cần `java --version` trả về 27 ở máy lập trình. Hãy khai báo **JDK toolchain** để biết compiler nào được chọn, đặt **`--release 27`** để ràng buộc ngôn ngữ/bytecode/API, quản lý version **Gradle/Maven và plugins**, rồi **kiểm thử trên runtime đích** cùng dependencies thực tế. Với Gradle, dùng `JavaLanguageVersion.of(27)` và `options.release.set(27)` trên bản Gradle hỗ trợ; với Maven 3, dùng `maven.compiler.release` cùng Maven Toolchains Plugin khi muốn chọn JDK 27 độc lập với JVM chạy Maven. Phân biệt rõ **build JVM – compiler JDK – release – test/runtime** là nền tảng để tránh build không nhất quán giữa IDE, CI và production.

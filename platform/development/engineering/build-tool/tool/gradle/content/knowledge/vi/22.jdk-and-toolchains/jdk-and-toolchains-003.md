# Chọn vendor, phát hiện JDK và cấu hình nơi tìm JDK trong Gradle

## 1. Mục tiêu và tình huống thực tế

Một nhóm phát triển Java có thể làm việc trên máy Windows với Microsoft OpenJDK 17, máy Linux có Eclipse Temurin 17 và máy CI có nhiều bản JDK 11, 17, 21. Cùng một repository Gradle cần trả lời những câu hỏi rất cụ thể:

- **Dự án cần Java version nào để compile, test và chạy?**
- **Có yêu cầu vendor JDK cụ thể không**, ví dụ Eclipse Adoptium, Oracle, Amazon Corretto, Azul, Microsoft hay IBM/OpenJ9?
- **Gradle biết JDK đã cài ở đâu** nếu JDK nằm ngoài đường dẫn chuẩn?
- Khi máy có nhiều JDK tương thích, **Gradle chọn cái nào**?
- Khi không có JDK phù hợp, **Gradle tự tải được không**, và cần cấu hình gì?
- Vì sao `java -version` hoặc `JAVA_HOME` báo Java 21 nhưng `compileJava` vẫn dùng Java 17?

Gradle giải quyết bằng **Java toolchains**: build script khai **yêu cầu** về toolchain, còn Gradle phát hiện, chọn hoặc provision JDK đáp ứng yêu cầu đó. Nhờ vậy không bắt mọi người thay `JAVA_HOME` mỗi khi chuyển project.

~~~text
build.gradle: java.toolchain
   |  languageVersion = 17
   |  vendor = ADOPTIUM (nếu cần)
   v
Gradle Java Toolchain Service
   |--- local auto-detection: OS, JAVA_HOME, SDKMAN!, asdf...
   |--- custom locations: paths, fromEnv
   |--- provisioned JDKs tại Gradle User Home
   |--- auto-download resolver (nếu được cấu hình)
   v
Candidate JDKs phù hợp
   |--- lọc version / vendor / implementation
   |--- chọn theo precedence
   v
JavaCompiler / JavaLauncher / JavadocTool
   |
   +--> compileJava / compileTestJava
   +--> test / run / JavaExec
   +--> javadoc
~~~

**Mục tiêu hoàn thành bài:**
1. Phân biệt **JVM chạy Gradle Daemon** và **JDK toolchain được chọn để build/test/run**.
2. Viết Gradle Groovy DSL chọn `languageVersion`, `JvmVendorSpec` và khi cần `JvmImplementation`.
3. Hiểu **auto-detection**, `org.gradle.java.installations.paths`, `fromEnv`, `auto-detect` và cách kiểm tra với task `javaToolchains`.
4. Cấu hình **auto-provisioning** bằng toolchain resolver plugin trong `settings.gradle`, biết khi nào tải JDK không xảy ra.
5. Dùng Java toolchains ở **project** và **task** level, tránh hard-code đường dẫn `javac`/`java`.
6. Thực hành Java 17 bằng build hoàn chỉnh, xem stdout đáng tin và giải quyết các lỗi thường gặp trên CI/IDE.

Ví dụ chính dùng Gradle **Groovy DSL** (`build.gradle`/`settings.gradle`), Gradle Wrapper và JDK 17. Linux/macOS chạy `./gradlew`; Windows PowerShell chạy `.\gradlew.bat`. Các đường dẫn JDK trong phần hướng dẫn là **ví dụ**, phải thay bằng vị trí thực tế trước khi sử dụng.

## 2. Bốn thứ thường bị gọi chung là “Java version”

| Thành phần | Dùng để làm gì | Thường được kiểm soát bởi |
| --- | --- | --- |
| **Gradle client JVM** | Khởi chạy Gradle Wrapper/client | Shell, `JAVA_HOME`, executable `java` |
| **Gradle Daemon JVM** | Chạy logic Gradle, plugins, configuration và điều phối tasks | Daemon JVM criteria, `org.gradle.java.home`, môi trường khởi chạy theo chính sách |
| **Java toolchain của project** | Cung cấp compiler/launcher/javadoc tool cho Java tasks | `java { toolchain { ... } }` |
| **Java toolchain riêng của task** | Chạy `Test`, `JavaExec` hoặc compile bằng JDK đặc biệt | `javaToolchains.launcherFor`/`compilerFor` ở task |

Ví dụ thực tế hoàn toàn hợp lệ:

~~~text
Gradle Daemon: JDK 21
Project Java toolchain: JDK 17
compileJava: javac 17
run: java 17
Ứng dụng biên dịch và chạy theo Java 17.
~~~

Đây là **minh họa cấu hình**, không phải output mặc định của Gradle. Build có thể được điều phối bởi Daemon chạy Java 21 nhưng toolchain Java 17 vẫn biên dịch và chạy source code đúng mức yêu cầu. Gradle Daemon JVM **không bắt buộc trùng** toolchain JVM. Dù vậy, phiên bản Java dùng **để chạy Gradle** phải tương thích với **phiên bản Gradle Wrapper** bạn đang sử dụng.

### 2.1. `JAVA_HOME` không phải lệnh “chọn toolchain 17”

Biến môi trường `JAVA_HOME` thường ảnh hưởng Java dùng khởi động Gradle, và Gradle cũng có thể phát hiện nó như một vị trí JDK. Nhưng khi đã khai:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Gradle tìm **toolchain Java 17 phù hợp**, không mặc nhiên lấy JDK từ `JAVA_HOME` nếu `JAVA_HOME` trỏ Java 21. Nếu không có Java 17 và không có auto-provisioning khả dụng, build có thể thất bại dù `java -version` trả về Java 21.

**Ba lệnh kiểm tra ba câu hỏi khác nhau:**

~~~bash
java -version
./gradlew --version
./gradlew -q javaToolchains
~~~

- `java -version`: `java` mà shell hiện tại gọi từ PATH (có thể khác `JAVA_HOME/bin/java` nếu PATH cấu hình khác).
- `./gradlew --version`: thông tin Gradle và JVM đang dùng để thực thi Gradle, tùy Gradle version/client/daemon configuration.
- `./gradlew -q javaToolchains`: những JVM/JDK Gradle **phát hiện để cân nhắc làm toolchain**, kèm version, vendor, path và “Detected by”.

Không coi ba lệnh phải báo cùng một JDK.

### 2.2. `org.gradle.java.home` có vai trò khác

Trong `gradle.properties` có thể có:

~~~properties
org.gradle.java.home=/opt/gradle-daemon-jdk
~~~

Property này chỉ định Java home cho **Gradle build/Daemon JVM** theo Gradle, không phải cách tốt nhất để yêu cầu `compileJava` dùng một JDK theo version/vendor. Nó còn là đường dẫn đặc thù từng máy: không nên commit giá trị thật của developer vào repository.

Gradle cũng hỗ trợ **Daemon JVM criteria** để chọn JVM chạy Gradle theo version/vendor. Đây là một cơ chế riêng với **Java toolchain của project**. Ví dụ lệnh chính thức `updateDaemonJvm` có thể thiết lập tiêu chí Daemon JVM trong các Gradle versions hỗ trợ. Đừng nhầm nó với `java.toolchain.languageVersion`.

## 3. Chọn Java version bằng toolchain DSL

### 3.1. Cấu hình tối thiểu

**`build.gradle`:**

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Khi các tasks do Java plugin cung cấp cần compiler/launcher/javadoc tool, Gradle sẽ dùng toolchain đáp ứng **Java language version 17**. Việc chọn một toolchain không có nghĩa Gradle tự tải bản mới nhất của mọi vendor.

`JavaLanguageVersion.of(17)` chỉ định **major Java version**, không pin JDK patch release `17.0.x`, không pin vendor và không nói JVM cụ thể nằm ở directory nào.

Nếu có JDK 17 đủ điều kiện từ nhiều vendors, Gradle dùng những quy tắc chọn installation ở phần 7. Muốn hạn chế vendor, xem phần 4.

### 3.2. `--release` và source/target compatibility khác toolchain

Một nhiệm vụ thường gặp là **dùng JDK 17 để compile mã tương thích Java 11**:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 11
}
~~~

Ý nghĩa:
- Compiler thực tế: **`javac` từ JDK 17**.
- `--release 11` hướng compiler giới hạn source language level, target bytecode và public Java SE APIs tới Java 11.
- **Không có nghĩa** task `test` sẽ tự chạy trên Java 11. Nếu cần test trên Java 11, cần launcher/toolchain riêng cho `Test`.
- Chỉ đặt `sourceCompatibility = JavaVersion.VERSION_11` hoặc `targetCompatibility` không đầy đủ như `--release` trong việc chặn sử dụng API của JDK mới.

**Quy tắc:** `languageVersion` chọn **tool dùng để biên dịch**; `options.release` chọn **mức Java API/bytecode đích**. Chúng giải quyết hai câu hỏi khác nhau.

### 3.3. Đừng hard-code đường dẫn `javac`

**Không nên:**

~~~groovy
tasks.register('manualCompile', Exec) {
    commandLine '/Users/alice/.sdkman/candidates/java/17.0.0/bin/javac',
        '-d', 'build/classes', 'src/main/java/demo/Main.java'
}
~~~

Đây là **ví dụ sai về tính di động**: đường dẫn của một người dùng, hard-code output path, thiếu file input/output tracking phù hợp, và không chạy được trên Windows/CI.

**Nên:** dùng Java plugin + `java.toolchain` + `JavaCompile` task. Khi thật sự cần custom task dùng JVM, lấy `JavaCompiler`/`JavaLauncher` từ toolchain service bằng Provider thay vì tự nối `JAVA_HOME + '/bin/javac'`.

## 4. Chọn vendor cụ thể bằng `JvmVendorSpec`

### 4.1. Vendor có thể là một phần hợp đồng

Một dự án có thể cần:
- Temurin/Adoptium để thống nhất môi trường kiểm thử trong tổ chức.
- Oracle JDK khi sản phẩm có ràng buộc hỗ trợ cụ thể.
- Amazon Corretto, Azul Zulu hoặc Microsoft OpenJDK theo chính sách vận hành.
- IBM/OpenJ9 khi đang kiểm thử JVM implementation khác.
- GraalVM cho native-image-related build logic.

Nếu có yêu cầu thực, khai vendor:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
        vendor = JvmVendorSpec.ADOPTIUM
    }
}
~~~

Gradle chỉ chọn toolchain **thỏa cả version 17 và vendor Adoptium**. Nếu local có Microsoft JDK 17 nhưng không có Temurin 17, Microsoft JDK không được chọn để “thay tạm” vì nó **không thỏa vendor filter**. Khi đó Gradle cần tìm/provision Adoptium 17 phù hợp hoặc báo không tìm được.

### 4.2. Các vendor constants phổ biến

| Constant | JVM distribution thường được nhận dạng |
| --- | --- |
| `JvmVendorSpec.ADOPTIUM` | Eclipse Temurin / Eclipse Adoptium |
| `JvmVendorSpec.ADOPTOPENJDK` | AdoptOpenJDK cũ |
| `JvmVendorSpec.AMAZON` | Amazon Corretto |
| `JvmVendorSpec.AZUL` | Azul Zulu |
| `JvmVendorSpec.BELLSOFT` | BellSoft Liberica |
| `JvmVendorSpec.GRAAL_VM` | GraalVM |
| `JvmVendorSpec.IBM` | IBM/Semeru theo metadata JVM |
| `JvmVendorSpec.MICROSOFT` | Microsoft OpenJDK |
| `JvmVendorSpec.ORACLE` | Oracle JDK |
| `JvmVendorSpec.SAP` | SAPMachine |
| `JvmVendorSpec.JETBRAINS` | JetBrains Runtime, trên Gradle versions hỗ trợ |
| `JvmVendorSpec.TENCENT` | Tencent Kona, trên Gradle versions hỗ trợ |

Đây là **ví dụ các constants hỗ trợ trong Gradle hiện hành**, không phải lời khẳng định mọi Gradle version cũ đều nhận đầy đủ chúng. Tra [API `JvmVendorSpec`](https://docs.gradle.org/current/javadoc/org/gradle/jvm/toolchain/JvmVendorSpec.html) nếu cần tương thích một Gradle Wrapper cụ thể.

**`ADOPTIUM` không giống `ADOPTOPENJDK`** trong danh sách nhận diện vendor. Khi migrate JDK cũ, kiểm tra trường `Vendor` trong báo cáo `javaToolchains` thay vì chỉ dựa vào folder name chứa chữ `adopt`.

### 4.3. Vendor không nằm trong danh sách: `matching(...)`

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
        vendor = JvmVendorSpec.matching('MyCustomJVM')
    }
}
~~~

`JvmVendorSpec.matching(String)` khớp **substring không phân biệt chữ hoa/thường** trong `java.vendor` của JVM được phát hiện. `'MyCustomJVM'` là chuỗi giả định, sẽ không match nếu metadata JDK thực tế không chứa nó.

Ví dụ nếu vendor metadata thực sự có `Microsoft`:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
        vendor = JvmVendorSpec.matching('Microsoft')
    }
}
~~~

Nếu vendor đã được Gradle nhận dạng bằng constant chính thức (`MICROSOFT`), ưu tiên constant vì nó tránh lệ thuộc cách vendor thể hiện tên ở các bản JDK.

**Cảnh báo về cú pháp:** Dùng `JvmVendorSpec.matching('...')`, không dùng `vendor = 'Microsoft'` như một string tùy ý khi property yêu cầu `JvmVendorSpec`.

### 4.4. Khi nào không nên ép vendor?

Đối với một ứng dụng Java thuần dùng standard Java 17 APIs, thường chỉ cần:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Điều này cho phép máy của developer/CI dùng bất kỳ JDK 17 tương thích nào, giảm ma sát cài đặt. Nếu pin vendor chỉ do “đội hiện đang dùng Temurin” nhưng sản phẩm không đòi hỏi Temurin, nhiều máy có JDK 17 hợp lệ sẽ bị loại vô ích.

Đặt vendor constraint khi có lý do rõ (vendor-specific behavior, license/approval, test matrix, native-image tool), và **ghi lý do** trong README kỹ thuật của dự án.

## 5. Chọn VM implementation: HotSpot-like, OpenJ9 và Native Image

Ngoài vendor, Gradle hỗ trợ phân biệt **VM implementation** trong `JavaToolchainSpec`.

### 5.1. `JvmImplementation`

~~~groovy
import org.gradle.jvm.toolchain.JvmImplementation

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
        implementation = JvmImplementation.J9
    }
}
~~~

Mẫu trên yêu cầu Java 17 **J9/OpenJ9 implementation**. Nếu máy không có JDK thích hợp, Gradle không tự đổi sang HotSpot chỉ vì cả hai đều Java 17.

Các giá trị quan trọng:
- `JvmImplementation.J9`: chỉ những JVM OpenJ9/J9.
- `JvmImplementation.VENDOR_SPECIFIC`: trong API Gradle đóng vai trò **không hạn chế implementation**, không đồng nghĩa “chọn HotSpot cụ thể” hoặc “chọn vendor đã định”.

**Không nhầm vendor và VM implementation:** vendor có thể cung cấp nhiều runtime implementations; JVM engine và nhà phân phối là hai chiều khác nhau.

### 5.2. Đặt vendor cùng implementation

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
        vendor = JvmVendorSpec.IBM
        implementation = JvmImplementation.J9
    }
}
~~~

Điều này là intersection: JDK phải thỏa **cả** Java 17, IBM vendor và J9. Đây là snippet minh họa có yêu cầu cài đặt tương ứng, không phải cấu hình chạy trên mọi máy.

### 5.3. GraalVM Native Image capability

Trong Gradle versions hiện đại có hỗ trợ capability, có thể yêu cầu:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
        nativeImageCapable = true
    }
}
~~~

Nó giới hạn toolchain tới JDK có Native Image capability khi được phát hiện, khác với chỉ chọn vendor GraalVM. Không nên áp mẫu này vào mọi Java 17 project; nó yêu cầu toolchain/Gradle version và điều kiện tool support phù hợp.

### 5.4. Toolchain spec có quy tắc hợp lệ

`JavaToolchainSpec` được coi là hợp lệ nếu:
1. Không có property nào được đặt (empty specification, thường rơi về JVM đang chạy Gradle).
2. **`languageVersion` đã được đặt**, sau đó có thể thêm vendor, implementation và các yêu cầu phù hợp khác.

**Sai:**

~~~groovy
java {
    toolchain {
        vendor = JvmVendorSpec.ADOPTIUM
    }
}
~~~

Với các Gradle phiên bản mới (kể từ Gradle 8.0), chỉ đặt vendor/implementation mà **không** đặt languageVersion là spec không hợp lệ. Hãy luôn chỉ định major version cùng vendor trong một toolchain request có filter.

## 6. Gradle tự phát hiện những JDK nào?

Theo cơ chế **auto-detection**, Gradle có thể dò những nguồn phổ biến:

- Các thư mục JDK/JRE do hệ điều hành quản lý trên Linux, macOS, Windows.
- `JAVA_HOME`.
- Những công cụ như **SDKMAN!**, **asdf-vm**, **Jabba**.
- Maven Toolchains configuration.
- Java installations do IntelliJ IDEA quản lý.
- JDK Gradle đã provision trước đó trong Gradle User Home.

Không phải mọi nguồn đều hiện diện trên mọi OS/phiên bản Gradle. Danh sách thực tế là **những gì Gradle phát hiện** tại thời điểm build, không phải những gì shell đang liệt kê theo PATH.

**Trình tự kiểm tra đầu tiên:**

~~~bash
./gradlew -q javaToolchains
~~~

Báo cáo có thể hiển thị (đây là **minh họa, không phải stdout cố định**):

~~~text
+ Eclipse Temurin JDK 17.0.x
    | Location:         /opt/jdks/temurin-17
    | Language Version: 17
    | Vendor:           Eclipse Adoptium
    | Is JDK:           true
    | Detected by:      Gradle property 'org.gradle.java.installations.paths'

+ Microsoft JDK 21.0.x
    | Location:         /opt/jdks/microsoft-21
    | Language Version: 21
    | Vendor:           Microsoft
    | Is JDK:           true
    | Detected by:      ...
~~~

Dấu ba chấm ở đây có nghĩa **trường phụ thuộc máy và không phải literal để copy khi kiểm thử**. Báo cáo thật còn có thông tin architecture, auto-detection và auto-download settings. Để làm QA, đọc output trên máy của bạn thay vì so khớp nguyên văn với bảng minh họa.

### 6.1. JDK và JRE khác nhau

- **JDK** chứa compiler `javac` và các công cụ phát triển Java.
- **JRE** chủ yếu cung cấp runtime để chạy Java; tùy distribution/version, có thể không có `javac`.

Gradle có thể phát hiện **cả JRE/JDK**. Với task compile, cần compiler thích hợp; thông thường Gradle **ưu tiên JDK hơn JRE** giữa những toolchain candidates đủ điều kiện.

Trường `Is JDK: true/false` trong `javaToolchains` rất hữu ích nếu bạn thấy Java 17 tồn tại nhưng `compileJava` vẫn không tìm được Java compiler.

### 6.2. JDK có folder nhưng Gradle không nhận

Một số nguyên nhân:
- Thư mục đã được move/xóa.
- Đường dẫn trỏ vào **folder cha** có nhiều JDK, không trực tiếp là JDK home.
- Folder sai cấp (`bin/java` không ở vị trí Gradle mong đợi).
- Path bị sai phân cách trên Windows hoặc có khoảng trắng/đọc properties không phù hợp.
- JDK là bản không tương thích OS/CPU architecture.
- Gradle Daemon còn cache trạng thái discovery từ trước khi đổi cấu hình.

Các vị trí không tồn tại hoặc không chứa executable `bin/java` phù hợp có thể bị **bỏ qua kèm warning**, không nhất thiết làm build fail ở bước đọc `gradle.properties`. Lỗi thường xuất hiện muộn hơn khi **không còn candidate nào** đáp ứng request.

## 7. Thứ tự ưu tiên khi nhiều toolchain cùng phù hợp

Giả sử có ba JDK 17:
- Temurin 17.0.10 ở `/opt/jdks/temurin-17`.
- Microsoft OpenJDK 17.0.12 ở `/opt/jdks/microsoft-17`.
- Oracle JDK 17.0.9 ở một location khác.

Nếu toolchain spec chỉ cần `languageVersion=17`, Gradle có thể chọn một candidate theo **installation precedence**, không tự chọn “JDK mới nhất trên toàn máy” theo mọi tiêu chí.

Theo tài liệu Gradle hiện hành, sau khi **lọc candidates hợp lệ**, quy tắc precedence được áp dụng theo thứ tự:

1. Ưu tiên installation **đang chạy Gradle** nếu nó đáp ứng spec.
2. Ưu tiên **JDK** hơn JRE.
3. Ưu tiên một số **vendor** theo thứ tự định sẵn của Gradle.
4. Ưu tiên version cao hơn (major, minor/patch theo metadata/toolchain list).
5. Cuối cùng dùng thứ tự đường dẫn (lexicographic) để chọn xác định giữa candidates tương đương.

**Quan trọng:** Không nên nghĩ Gradle chỉ so sánh patch version trước. Ở bước ưu tiên vendor, một JDK với patch cũ hơn có thể được ưu tiên hơn vendor khác có patch mới hơn. Nếu vendor là tiêu chí nghiệp vụ, hãy khai `vendor` rõ; nếu patch/security level quan trọng, dùng CI-managed JDK installations/verification thay vì giả định `languageVersion=17` tự pin patch.

### 7.1. Custom paths có được ưu tiên hơn auto-detect không?

**Không.** Cấu hình `org.gradle.java.installations.paths` **bổ sung candidates**, không tự đặt những paths này lên trên các candidates khác. Nếu `auto-detect=true`, Gradle xét cả locations tự dò và locations bạn khai; winner được chọn theo precedence.

Muốn giới hạn tập candidates trên CI, có thể:
- Tắt auto-detection.
- Cấu hình explicit paths/fromEnv thật sự tồn tại.
- Tắt auto-download nếu policy cần kiểm soát chặt.
- Giữ JDK versions/vendors được duyệt trên runner.

Nhưng kể cả khi tắt auto-detect, bạn vẫn cần chạy `javaToolchains` để biết những installation sources nào Gradle thực tế dùng.

### 7.2. Đổi `JAVA_HOME` có thay ngay toolchain không?

Không nên chắc chắn. Nếu bạn đang dùng toolchain spec chọn `vendor=ADOPTIUM` và Gradle đã có Temurin 17, đổi `JAVA_HOME` từ JDK 21 sang JDK 22 có thể **không đổi** toolchain compiler. Khi thông tin toolchain/Daemon bị cache sau thay đổi cấu hình hoặc JDK installation, thử:

~~~bash
./gradlew --stop
./gradlew -q javaToolchains
~~~

Dùng `--stop` có chủ đích khi đang chẩn đoán. Không cần dừng Daemon trước mỗi build trong công việc thường ngày.

## 8. Thêm nơi tìm JDK bằng `gradle.properties`

Khi Gradle không thấy một JDK đã cài, có ba Gradle properties rất quan trọng.

### 8.1. `org.gradle.java.installations.paths`: danh sách đường dẫn trực tiếp

**`gradle.properties` trên một Linux CI runner (ví dụ):**

~~~properties
org.gradle.java.installations.paths=/opt/jdks/temurin-17,/opt/jdks/temurin-21
~~~

Gradle xét hai **JDK home directories** như candidates. Cú pháp là **comma-separated list**, không phải PATH kiểu `:`/`;`. Các folder này phải **tồn tại thực tế** trên runner; tên chỉ là ví dụ.

**Ví dụ trên Windows với dấu slash để dễ đọc:**

~~~properties
org.gradle.java.installations.paths=C:/Java/temurin-17,C:/Java/microsoft-21
~~~

Bạn cần thay bằng location hợp lệ trên máy Windows thực tế. Đừng dùng `C:/Java/temurin-17/bin` vì Gradle cần **installation root** chứa thư mục `bin/`, không phải folder chứa chính executable.

**Lưu ý lớn:** Gradle **không tự dò đệ quy** vào mọi folder con của path bạn khai trong `paths`. Nếu `/opt/jdks` chứa `jdk-17` và `jdk-21`, đừng chỉ viết `/opt/jdks` rồi mong Gradle tìm sâu các installations bên trong.

### 8.2. `org.gradle.java.installations.fromEnv`: tên biến môi trường

Giả sử CI đã xuất hai biến:

~~~bash
export JDK17_HOME=/opt/jdks/temurin-17
export JDK21_HOME=/opt/jdks/temurin-21
~~~

**`gradle.properties`:**

~~~properties
org.gradle.java.installations.fromEnv=JDK17_HOME,JDK21_HOME
~~~

Tính chất:
- Property chứa **tên biến**, không chứa actual path.
- Gradle đọc **giá trị** của từng biến và coi đó là một candidate JDK installation path.
- Nếu biến môi trường chưa được set hoặc trỏ sai path, không có candidate hợp lệ từ tên đó.
- Có thể dùng biến `JAVA_HOME` trong danh sách nếu muốn, nhưng Gradle auto-detection đã thường nhận `JAVA_HOME`; `fromEnv` hữu ích cho những biến **riêng** như `JDK17_HOME` và `JDK21_HOME`.

**Windows PowerShell, phiên làm việc hiện tại:**

~~~powershell
$env:JDK17_HOME = 'C:\Java\temurin-17'
$env:JDK21_HOME = 'C:\Java\microsoft-21'
.\gradlew.bat -q javaToolchains
~~~

Các biến này cần được thiết lập **trước khi** khởi chạy Gradle để Gradle phát hiện. Trên CI hãy cấu hình ở runner/job environment, không hard-code path developer vào repository.

### 8.3. `org.gradle.java.installations.auto-detect`

Gradle mặc định **tự phát hiện** JDK/JRE ở những sources hỗ trợ:

~~~properties
org.gradle.java.installations.auto-detect=true
~~~

Tắt nếu muốn giới hạn việc tìm kiếm:

~~~properties
org.gradle.java.installations.auto-detect=false
org.gradle.java.installations.fromEnv=JDK17_HOME
~~~

Lúc này, bạn chịu trách nhiệm bảo đảm `JDK17_HOME` hợp lệ hoặc có provisioning nguồn khác. **Tắt auto-detect không tự ép Gradle chọn directory tùy ý**; nó chỉ tắt nhóm sources được auto-scan.

Có thể bật/tắt cho một invocation với system property:

~~~bash
./gradlew -Dorg.gradle.java.installations.auto-detect=false -q javaToolchains
~~~

`-Dorg.gradle.java.installations.auto-detect=false` là **system property dành cho Gradle**, không phải `-P` project property và không phải Java source compiler option.

### 8.4. Cấu hình kết hợp paths và fromEnv

~~~properties
org.gradle.java.installations.auto-detect=false
org.gradle.java.installations.auto-download=false
org.gradle.java.installations.fromEnv=JDK17_HOME
org.gradle.java.installations.paths=/opt/approved-jdks/temurin-21
~~~

**Đây là policy ví dụ dành cho Linux CI, không thể copy nguyên sang máy khác.** Nó có ý nghĩa:
- Không dựa vào scan tự động các JDK tùy ý trong môi trường.
- Không tự provision JDK từ network.
- Thêm JDK17 từ env nếu có.
- Thêm JDK21 từ path được approved.
- Nếu build yêu cầu vendor/version khác không có, build thất bại thay vì tự chuyển sang JDK sai.

**Không nên commit những path đặc thù một máy vào repository**. Nếu build phân phối cho nhiều developers, đặt đường dẫn trong **Gradle User Home `gradle.properties`** của mỗi người hoặc CI-specific environment; commit các property chính sách chung (ví dụ bật/tắt auto-download) nếu cả team thống nhất.

## 9. Auto-provisioning: khi JDK chưa cài sẵn

Gradle có thể tự tải JDK phù hợp, nhưng cần hiểu **hai điều kiện độc lập**:

1. **Auto-download được cho phép** (`org.gradle.java.installations.auto-download=true`; mặc định true trong tài liệu hiện hành).
2. **Một toolchain download repository/resolver thực sự được cấu hình** để Gradle biết lấy JDK từ đâu.

**Chỉ bật `auto-download=true` không có nghĩa Gradle có sẵn nguồn tải JDK ở mọi bản Gradle hoặc mọi build.** Nếu thiếu resolver, Gradle có thể báo “No locally installed toolchains match and toolchain download repositories have not been configured”.

### 9.1. Thêm Foojay Toolchain Resolver Convention

Một cách phổ biến trong Gradle versions hiện đại là áp **settings plugin** sau:

**`settings.gradle`:**

~~~groovy
plugins {
    id 'org.gradle.toolchains.foojay-resolver-convention' version '1.0.0'
}

rootProject.name = 'toolchain-provisioning-demo'
~~~

Plugin được dùng trong **settings**, không phải `build.gradle`. Version `1.0.0` là phiên bản ví dụ đang được tài liệu Gradle trình bày; khi dùng một Gradle Wrapper cụ thể, hãy kiểm tra compatibility/version plugin theo tài liệu chính thức.

Sau đó `build.gradle` có thể khai:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
        vendor = JvmVendorSpec.ADOPTIUM
    }
}
~~~

Nếu máy không có JDK17 matching, Gradle **có thể provision** distribution phù hợp qua resolver, nếu có mạng, nguồn tải thực sự hỗ trợ yêu cầu và policy cho phép. Provisioned JDK được cài trong **Gradle User Home**, thường khu vực `jdks/`, để các build sau có thể dùng lại.

**Không cam kết** mọi vendor/version/OS/architecture đều có thể tải: resolver phải hỗ trợ yêu cầu cụ thể, repository truy cập được và artifact được phép download.

### 9.2. Tắt auto-download

**`gradle.properties`:**

~~~properties
org.gradle.java.installations.auto-download=false
~~~

Hoặc trong một lần chạy:

~~~bash
./gradlew -Dorg.gradle.java.installations.auto-download=false compileJava
~~~

Việc tắt provisioning phù hợp khi:
- CI image đã cung cấp JDK theo danh sách approved.
- Network không được phép trong build.
- Tổ chức yêu cầu kiểm soát license, integrity và nguồn phân phối JDK.
- Cần fail-fast nếu JDK chưa được cài đúng.

Lúc đó phải chắc chắn có candidate JDK đáp ứng spec. Nếu đổi settings nhưng Daemon chưa cập nhật detection, dừng Daemon và kiểm tra lại `javaToolchains`.

### 9.3. Custom resolver và toolchain repository

Tổ chức có repository JDK riêng có thể viết **toolchain resolver plugin** và cấu hình repository của nó trong **`settings.gradle`** qua `toolchainManagement { jvm { javaRepositories { ... } } }`. Một ví dụ cấu trúc:

~~~groovy
toolchainManagement {
    jvm {
        javaRepositories {
            repository('internal-jdks') {
                resolverClass = com.example.build.InternalJdkResolver
            }
        }
    }
}
~~~

**Đây là snippet kiến trúc, không chạy độc lập:** `com.example.build.InternalJdkResolver` là **class giả định** do plugin nội bộ phải cung cấp và apply trước/đúng phase. `toolchainManagement` không tự tải khi không có resolver implementation thật. Không tự chép snippet này vào build rồi nghĩ đã cấu hình thành công.

Các resolvers/repositories được xét theo thứ tự cấu hình khi provision. Credentials, kiểm soát nguồn tải và khả năng audit phải được quản lý như một phần supply-chain policy.

### 9.4. Plugin resolution khác toolchain resolution

Để áp Foojay settings plugin, Gradle phải tìm chính plugin đó qua **plugin resolution**. Sau khi plugin hoạt động, nó mới hỗ trợ **toolchain download**.

~~~text
pluginManagement / plugins resolution
      -> tải settings resolver plugin
      -> resolver cấu hình toolchain repositories
      -> Gradle tìm/provision JDK
      -> JavaCompile/Test/Javadoc sử dụng JDK
~~~

Nếu chạy ở mạng nội bộ không truy cập Plugin Portal, lỗi lấy settings plugin có thể xuất hiện **trước** lỗi chọn JDK. Phải xử lý plugin repository/mirror trước. Đừng nhầm Maven Central project dependency repository với JDK download resolver.

## 10. Gradle chọn JDK nào khi yêu cầu vendor?

Cân nhắc các installations trên CI giả định:

| Installation | Java | Vendor | Được tìm từ |
| --- | --- | --- | --- |
| `/opt/jdks/temurin-17` | 17 | Eclipse Adoptium | `paths` |
| `/opt/jdks/microsoft-17` | 17 | Microsoft | OS scan |
| `/opt/jdks/temurin-21` | 21 | Eclipse Adoptium | env `JDK21_HOME` |
| `/opt/jdks/ibm-17-j9` | 17 | IBM, J9 | `paths` |

### Trường hợp A — chỉ chọn Java 17

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Candidates là các installations Java 17 có thể phục vụ task. Gradle chọn theo precedence, **không bắt buộc** chọn folder nằm trong `paths` đầu tiên. Nên chạy `javaToolchains` và `compileJava --info` để kiểm chứng lựa chọn thật.

### Trường hợp B — Java 17 + Adoptium

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
        vendor = JvmVendorSpec.ADOPTIUM
    }
}
~~~

Trong tập giả định, chỉ Temurin 17 thỏa cả hai. Temurin 21 **không** thay thế được vì version không khớp.

### Trường hợp C — Java 17 + IBM/J9

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
        vendor = JvmVendorSpec.IBM
        implementation = JvmImplementation.J9
    }
}
~~~

Trong tập giả định, `ibm-17-j9` là candidate phù hợp. Nếu chỉ có IBM HotSpot-like 17, nó không tự thỏa J9 filter.

### Trường hợp D — không có vendor phù hợp

Nếu toolchain yêu cầu Microsoft JDK 17 mà CI chỉ có Temurin 17 và auto-download bị tắt, **build có thể fail** với no matching toolchain. **Không nên** âm thầm bỏ vendor rule nếu yêu cầu vendor là policy quan trọng. Sửa bằng cách provision JDK đúng hoặc điều chỉnh policy có căn cứ.

## 11. Bài thực hành hoàn chỉnh: Java 17 application không ràng buộc vendor

Bài này **chạy được trên nhiều máy** miễn có Java 17 toolchain hợp lệ (đã cài hoặc có resolver provisioning) và Gradle Wrapper tương thích. Chúng ta không ép vendor trong cấu hình chạy mặc định để tránh bài lab thất bại trên máy không có Temurin.

### 11.1. Cấu trúc

~~~text
jdk-toolchain-lab/
├── settings.gradle
├── build.gradle
├── src/
│   └── main/java/demo/Main.java
├── gradlew
├── gradlew.bat
└── gradle/wrapper/
    ├── gradle-wrapper.jar
    └── gradle-wrapper.properties
~~~

Nếu chưa có Wrapper, dùng Gradle đã cài để chạy `gradle wrapper` một lần và commit toàn bộ file Wrapper. Trước khi chạy, kiểm tra máy có JDK 17 trong `./gradlew -q javaToolchains`; nếu không có, xem phần 9 để cấu hình resolver hoặc cài JDK 17 thủ công.

### 11.2. `settings.gradle`

~~~groovy
rootProject.name = 'jdk-toolchain-lab'
~~~

### 11.3. `build.gradle` — toàn bộ

~~~groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.Main'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
}
~~~

Tại sao cấu hình này hợp lý?
- Application plugin cũng áp Java plugin, tạo Java extension và các tasks `compileJava`/`run`.
- `languageVersion=17` yêu cầu JDK/toolchain version 17 cho compile/test/JavaExec tasks thuộc Java model.
- Không chọn vendor nên Java 17 từ những vendors tương thích đều có thể được dùng.
- `options.release=17` nêu rõ mức Java SE API/bytecode đích; nó không thay đổi compiler được chọn nhưng củng cố hợp đồng compile Java 17.
- `UTF-8` giúp source encoding nhất quán.
- Không hard-code `JAVA_HOME` hay path `javac` trong script.

### 11.4. `src/main/java/demo/Main.java` — Java 17 hoàn chỉnh

~~~java
package demo;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("Gradle toolchain: OK");
        System.out.println("Java feature: " + Runtime.version().feature());
    }
}
~~~

`Runtime.version().feature()` có từ Java 9 và trả về **major feature version của JVM đang chạy chương trình**. Vì bài lab cấu hình `run` dùng Java 17 toolchain, chúng ta kỳ vọng giá trị 17.

### 11.5. Các lệnh thực hành

~~~bash
./gradlew -q javaToolchains
./gradlew compileJava --info
./gradlew run --quiet
~~~

**Stdout của chính ứng dụng ở cấu hình Java 17 (không tính Gradle logs):**

~~~text
Gradle toolchain: OK
Java feature: 17
~~~

Output này dựa trên yêu cầu `run` dùng Java 17 toolchain được Gradle Application/Java plugin tích hợp. Nếu thực tế báo Java feature khác, kiểm tra có task-level `javaLauncher` override, Gradle/Java plugin bị custom hóa, hoặc script lab không đúng. Không dùng `java -version` của shell làm bằng chứng ứng dụng Gradle `run` dùng JVM đó.

### 11.6. Kiểm chứng bằng `javac`/`java` độc lập

Nếu bạn muốn đối chiếu ngoài Gradle, dùng **chính JDK 17 đã cài** và thực hiện từ root:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/main/java/demo/Main.java
java -cp out demo.Main
~~~

Trên máy mà `javac` và `java` trong PATH đều thuộc JDK 17, stdout vẫn:

~~~text
Gradle toolchain: OK
Java feature: 17
~~~

**Cảnh báo:** Lệnh thủ công dùng `javac`/`java` từ PATH, **không tự dùng Gradle toolchain**. Nếu PATH trỏ JDK 21, ứng dụng chạy thủ công có thể in `Java feature: 21` dù Gradle build đúng 17. Khi muốn thực hành chính xác, gọi executable từ JDK17 home hoặc chỉnh shell PATH cho riêng phiên làm việc.

## 12. Mở rộng bài lab: chọn vendor và đối chiếu kết quả

Khi biết máy có **Eclipse Temurin 17**, hãy thêm vendor vào block `java.toolchain`:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
        vendor = JvmVendorSpec.ADOPTIUM
    }
}
~~~

Chạy:

~~~bash
./gradlew -q javaToolchains
./gradlew clean run --info
~~~

Nếu Temurin17 được nhận diện, app vẫn in **hai dòng như phần 11**. Vendor selection thay đổi **JDK làm toolchain**, không thay đổi source code.

Nếu CI dùng Microsoft OpenJDK17 và không có Temurin, đoạn này có thể thất bại. Hãy thử đổi thành `JvmVendorSpec.MICROSOFT` **chỉ khi** build có quyền dùng vendor ấy và đó là lựa chọn đúng. Đừng dùng vendor string đoán mò; kiểm tra field `Vendor` trong `javaToolchains`.

### 12.1. Dùng task-level toolchain khác project default

Giả sử source code được compile bằng Java 17 nhưng bạn muốn kiểm tra một `JavaExec`/`Test` task trên Java 21:

~~~groovy
tasks.withType(Test).configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

Đây là **snippet** để thêm trong project có Java/Test tasks và JDK21 (hoặc resolver). Nó yêu cầu tất cả `Test` tasks chạy bằng Java 21, trong khi project `compileJava` vẫn có thể compile bằng JDK17.

Nếu chỉ một task riêng cần Java21:

~~~groovy
tasks.named('run', JavaExec) {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

Khi áp snippet thứ hai vào lab, `run` sẽ dùng Java21 và dòng thứ hai từ `Main` trở thành:

~~~text
Java feature: 21
~~~

Dòng đầu vẫn là `Gradle toolchain: OK`. **Đây là thay đổi có chủ ý** để phân biệt project toolchain với **task override**, không phải một lỗi Gradle.

### 12.2. Khi một task cần compiler riêng

~~~groovy
tasks.withType(JavaCompile).configureEach {
    javaCompiler = javaToolchains.compilerFor {
        languageVersion = JavaLanguageVersion.of(17)
        vendor = JvmVendorSpec.ADOPTIUM
    }
}
~~~

Dùng `javaToolchains.compilerFor` để cấp `Provider<JavaCompiler>`. Với `Test` và `JavaExec`, dùng `javaToolchains.launcherFor` để cấp `Provider<JavaLauncher>`. Với `Javadoc` task, Gradle hỗ trợ `javaToolchains.javadocToolFor`.

**Không nên** gọi `javaToolchains.compilerFor { ... }.get().executablePath` trong configuration khi có thể gắn nguyên Provider vào task property; `.get()` có thể làm việc nhận diện/provision toolchain diễn ra sớm không cần thiết.

## 13. Trên CI: chiến lược kiểm soát vendor và JDK source

### 13.1. CI tự quản lý JDK được duyệt

Một pipeline quản lý JDK17 qua biến môi trường:

**Thiết lập ở CI job:**

~~~bash
export JDK17_HOME=/opt/approved-jdks/temurin-17
~~~

**`gradle.properties` dành cho môi trường này:**

~~~properties
org.gradle.java.installations.auto-detect=false
org.gradle.java.installations.auto-download=false
org.gradle.java.installations.fromEnv=JDK17_HOME
~~~

**`build.gradle`:**

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
        vendor = JvmVendorSpec.ADOPTIUM
    }
}
~~~

Nếu JDK17 theo env không đáp ứng version/vendor, build phải fail. Đây là **fail-fast có chủ đích**. Không có network provisioning vì `auto-download=false`.

**Lưu ý:** File `gradle.properties` này có giá trị như CI-specific policy. Nếu commit nguyên vào repository được dùng trên macOS/Windows, những developer không có `JDK17_HOME` có thể không build được. Thường dùng configuration chung trong Git, còn biến env/địa chỉ JDK cụ thể đặt trong CI hoặc Gradle User Home riêng.

### 13.2. CI cho phép Gradle provision toolchain

**`settings.gradle`:**

~~~groovy
plugins {
    id 'org.gradle.toolchains.foojay-resolver-convention' version '1.0.0'
}
~~~

**`gradle.properties`:**

~~~properties
org.gradle.java.installations.auto-download=true
~~~

**`build.gradle`** có thể dùng:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
        vendor = JvmVendorSpec.ADOPTIUM
    }
}
~~~

Trong chế độ này, nếu thiếu JDK compatible, Gradle **có thể** tải JDK qua resolver đã cấu hình. CI cần quyền network, tin cậy nguồn download và đủ storage/caching policy. Hãy kiểm soát plugin version/source và môi trường JDK, không coi auto-download là bằng chứng chuỗi cung ứng đã được xác thực toàn bộ.

### 13.3. Kiểm chứng đầu pipeline

Các lệnh có ý nghĩa:

~~~bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew compileJava --info
./gradlew test
~~~

`javaToolchains` mô tả **available candidates**, còn `compileJava --info`/test outcomes cho thấy **task thực tế** được thực thi đúng không. Không cần xóa `~/.gradle/caches` để “ép chọn JDK” khi đang chẩn đoán vendor: hãy kiểm tra toolchain spec, available installations và Daemon state trước.

## 14. Các tình huống dễ nhầm

### 14.1. “Tôi đã set `JAVA_HOME=JDK21`, sao compiler là JDK17?”

Vì project có `java.toolchain.languageVersion=17`. Gradle không cần chọn JDK mà shell dùng. Đây là hành vi đúng.

### 14.2. “Tôi đã khai `paths`, sao Gradle vẫn chọn JDK khác?”

Vì `paths` **bổ sung địa điểm tìm**, không áp ưu tiên riêng. Nếu auto-detect bật, Gradle còn thấy candidates khác và áp precedence. Nếu cần ràng buộc vendor/implementation, khai trên toolchain spec; nếu cần CI source kiểm soát chặt, tắt auto-detection và đưa candidate hợp lệ vào sources được phép.

### 14.3. “Tôi đã cài JDK17, sao Gradle báo chưa có matching toolchains?”

Kiểm tra:
- `javaToolchains` có hiển thị JDK17 không?
- Nó là JRE hay JDK?
- Vendor metadata có match `JvmVendorSpec` được yêu cầu không?
- Có yêu cầu thêm `JvmImplementation.J9`/native-image không?
- Gradle đang chạy trên OS/architecture nào?
- Path có thực sự là JDK home chứ không phải parent folder?
- Nếu mới thay đổi môi trường/`gradle.properties`, có cần `./gradlew --stop` không?

### 14.4. “Bật auto-download nhưng vẫn fail”

Nguyên nhân thường gặp:
- Không có **toolchain download repository/resolver**.
- Settings plugin không resolve được từ plugin repository.
- Network/proxy/TLS/authentication bị chặn.
- Resolver không cung cấp requested vendor/version/OS/architecture.
- Không đủ quyền ghi/đĩa tại Gradle User Home.
- `org.gradle.java.installations.auto-download=false` đang được đặt từ nguồn Gradle property ưu tiên hơn.
- CI offline policy không cho tải JDK.

Cách sửa là xác định **điều kiện nào thiếu**, không xóa vendor rule hoặc đổi `languageVersion` chỉ để build qua.

### 14.5. “Java 17 compile thành công, chạy ở máy Java11 bị UnsupportedClassVersionError”

Toolchain Java17 tạo bytecode Java17 trừ khi bạn giới hạn target bằng `options.release` phù hợp. Nếu sản phẩm phải chạy Java11:
- Compile bằng JDK17 với `options.release=11`.
- Kiểm thử trên **Java11 launcher** (cần toolchain Java11 cài/provision).
- Kiểm tra dependencies/bytecode của libraries và các API/runtime constraints khác.

Toolchain chọn compiler không tự đảm bảo toàn bộ output chạy trên mọi Java version thấp hơn.

### 14.6. “Tôi muốn chỉ dùng đúng JDK patch 17.0.13”

`JavaLanguageVersion.of(17)` chỉ lọc **major version**. `vendor` cũng không pin patch. Nếu chính sách cần exact security patch/vendor binary, hãy:
- Dùng CI image/runner cung cấp JDK patch đã kiểm định.
- Giới hạn nguồn installations được Gradle chọn.
- Kiểm tra metadata/vendor/JDK binary fingerprint theo quy trình build của tổ chức.
- Quản lý bản JDK cập nhật an toàn và audit.

Không cố dùng `JavaLanguageVersion.of(17.0.13)`: API nhận Java **major language version**, không nhận patch version như vậy.

### 14.7. “Toolchain version khác `sourceCompatibility`”

`sourceCompatibility`/`targetCompatibility` mô tả mức ngôn ngữ/bytecode; toolchain mô tả JDK/compiler thực tế. Nếu muốn hạn chế Java SE API, `options.release` là phương pháp mạnh hơn `sourceCompatibility`/`targetCompatibility` riêng lẻ. Không để chúng mâu thuẫn mà không giải thích.

## 15. Bảng sửa lỗi nhanh

| Triệu chứng | Nguồn lỗi hay gặp | Hành động đúng |
| --- | --- | --- |
| `No matching toolchains found` | Không có JDK đáp ứng version/vendor/implementation | Kiểm tra `javaToolchains`, cài/provision JDK đúng |
| `No locally installed toolchains match and toolchain download repositories have not been configured` | Thiếu download resolver | Cấu hình settings resolver plugin hoặc cài JDK thủ công |
| `JAVA_HOME` là Java21 nhưng build đòi 17 | Gradle toolchain spec 17 | Cài JDK17, không cần ép Daemon sang Java17 |
| JDK đã cài mà không xuất hiện trong `javaToolchains` | Sai path, auto-detect tắt, unsupported installation | Sửa `paths`/`fromEnv`, kiểm tra `bin/java` |
| Có JDK17 nhưng compiler không có | Có thể chỉ JRE, không phải JDK | Cài JDK đầy đủ, xem `Is JDK` |
| Có Temurin nhưng ADOPTIUM vẫn không match | Vendor metadata/version khác suy đoán | Xem `Vendor` thật và bản Gradle, xác minh matching |
| JDK ở `paths` không được chọn | Custom paths không ưu tiên | Xem precedence, vendor filter, running Gradle JVM |
| `fromEnv` không hoạt động | Dùng path thay vì **tên biến**, hoặc env chưa export | `fromEnv=JDK17_HOME` và thiết lập biến trước lệnh Gradle |
| `paths` trỏ folder chứa nhiều JDK | Gradle không dò đệ quy trong custom path | Liệt kê từng JDK home |
| Vừa đổi `gradle.properties` nhưng vẫn JDK cũ | Daemon cache/detection chưa cập nhật | `./gradlew --stop` rồi `javaToolchains` |
| `javaToolchains` chỉ thấy Java21 | JDK17 chưa cài/không được discover | Cài JDK17 hoặc cấu hình resolver |
| Java plugin không áp nên `java { toolchain... }` lỗi | Không có Java extension | Áp Java/Application plugin trước |
| `vendor` được khai mà không có `languageVersion` | Invalid toolchain spec | Thêm `languageVersion` |
| `java -version` khác `run` | Shell JVM khác launcher của Gradle | Xem `javaLauncher`/project toolchain |
| `compileJava` chạy với Java17 nhưng `Test` chạy Java21 | Task override hoặc custom toolchain | Kiểm tra `tasks.withType(Test)`/`javaLauncher` |
| IDE build khác terminal | IDE Gradle JVM khác `JAVA_HOME` hoặc daemon config | Đồng bộ Gradle JVM setting và toolchain discovery |
| Provision JDK bị chặn | Network/plugin repository/license policy | Dùng approved local JDK hoặc resolver được phép |
| `UnsupportedClassVersionError` | Target bytecode quá cao cho runtime | Dùng `options.release`/test runtime tương thích |

### 15.1. Quy trình chẩn đoán theo thứ tự

1. **Xác định lỗi ở Gradle JVM hay toolchain**: `./gradlew --version` và yêu cầu trong build script.
2. **Xem yêu cầu thật**: `languageVersion`, `vendor`, `implementation`, optional task overrides.
3. **Xem candidates**: `./gradlew -q javaToolchains` và các cột `Location`, `Vendor`, `Is JDK`, `Detected by`.
4. **Kiểm tra sources**: auto-detect, `paths`, `fromEnv`, valid JDK home, PATH/JAVA_HOME.
5. **Kiểm tra provisioning**: `auto-download` và download resolver settings.
6. **Kiểm tra task**: `compileJava --info`/`run --info`, Java toolchain runtime trong output nếu cần.
7. **Nếu vừa thay môi trường**: dừng Daemon có chủ đích, chạy lại report.
8. **Nếu CI và local khác**: so sánh Gradle Wrapper version, Gradle JVM, toolchain list, vendor, OS/architecture và environment sources.
9. **Nếu đòi tái lập cao**: kiểm soát JDK distro/patch và test matrix, không chỉ major version.
10. **Chỉ sửa đúng lớp lỗi**: không chuyển mọi task sang `JAVA_HOME` hoặc disable vendor policy khi chưa xác định nguyên nhân.

## 16. Bài tập có đáp án

### Bài 1 — Vendor

Build yêu cầu `JavaLanguageVersion.of(17)` và `JvmVendorSpec.ADOPTIUM`. Máy chỉ có Microsoft JDK17. Gradle có được chọn Microsoft JDK không?

**Đáp án:** Không. Version phù hợp nhưng vendor không phù hợp. Cần Temurin/Adoptium17, provisioning tương thích hoặc thay policy có chủ đích.

### Bài 2 — fromEnv

Cho `org.gradle.java.installations.fromEnv=JDK17_HOME,JDK21_HOME`. Hai chuỗi sau dấu bằng là gì?

**Đáp án:** **Tên biến môi trường**, không phải paths. Gradle lấy các giá trị của biến đó làm candidate installation directories.

### Bài 3 — Paths

`org.gradle.java.installations.paths=/opt/jdks`, nơi này có thư mục con `temurin-17` và `temurin-21`. Gradle có tự dò đệ quy hai JDK không?

**Đáp án:** Không. Với custom paths, cần liệt kê **từng JDK home trực tiếp** như `/opt/jdks/temurin-17,/opt/jdks/temurin-21`.

### Bài 4 — JDK được chọn theo thứ tự nào?

`paths` có Java17 nhưng `JAVA_HOME` cũng trỏ Java17 từ vendor khác. `paths` có luôn thắng không?

**Đáp án:** Không. Hai nguồn được xét như candidates và Gradle áp precedence (current Daemon JVM, JDK vs JRE, vendor, version, path) sau khi lọc spec.

### Bài 5 — Auto-download

`auto-download=true`, không có local JDK matching và cũng không có toolchain resolver. Gradle chắc chắn sẽ tải được JDK mới chứ?

**Đáp án:** Không. Cần **download repository/resolver đã cấu hình**, không chỉ bật flag.

### Bài 6 — Gradle JVM vs toolchain

`JAVA_HOME` Java21; project `java.toolchain.languageVersion=17`. Task `compileJava` có thể dùng Java17 không?

**Đáp án:** Có, nếu Gradle phát hiện hoặc provision được Java17 matching. Gradle Daemon JVM và toolchain compiler là hai lớp khác nhau.

### Bài 7 — JRE vs JDK

Report `javaToolchains` có Java17, `Is JDK: false`. Một JavaCompile task có chắc compile thành công không?

**Đáp án:** Không. JavaCompile cần compiler; nếu chỉ có JRE, có thể không có `javac`. Cần JDK thích hợp.

### Bài 8 — Toolchain spec invalid

~~~groovy
java {
    toolchain {
        vendor = JvmVendorSpec.AMAZON
    }
}
~~~

**Đáp án:** Không hợp lệ trong Gradle versions hiện đại vì chỉ đặt vendor mà không đặt `languageVersion`. Thêm `languageVersion=JavaLanguageVersion.of(17)` hoặc version thực sự cần.

### Bài 9 — Runtime khác compiler

Project Java17 nhưng task `run` bị override `javaLauncher` sang Java21. App dùng `Runtime.version().feature()` in gì?

**Đáp án:** `21`, vì đó là JVM **thực thi ứng dụng**. Compiler và runtime không nhất thiết trùng khi bạn chủ động override.

### Bài 10 — `--release`

Dùng JDK17 compiler với `options.release=11`. Source code có thể gọi một API chỉ có từ Java17 mà Java11 không có không?

**Đáp án:** Compiler sẽ báo lỗi khi API không có trong Java11 API surface, giúp ngăn compile thành công với API mà Java11 runtime không hỗ trợ.

### Bài 11 — Diagnostic

Bạn vừa sửa `JDK17_HOME` nhưng `javaToolchains` vẫn không hiển thị location mới. Nên làm gì trước khi xóa cache?

**Đáp án:** Xác minh biến được export trong shell/CI, path là JDK home hợp lệ, Gradle property `fromEnv` đúng; khi nghi thông tin Daemon chưa cập nhật, thử `./gradlew --stop` và báo cáo lại.

### Bài 12 — Thực hành chạy

1. Tạo project phần 11, chạy `javaToolchains` và ghi JDK17 hiện diện từ source nào.
2. Chạy `./gradlew run --quiet`, kiểm tra output `Gradle toolchain: OK` và `Java feature: 17`.
3. Thêm `vendor = JvmVendorSpec.ADOPTIUM` khi máy có Temurin17, chạy lại.
4. Thay `fromEnv` bằng một biến chưa set trong bản lab riêng, tắt auto-download, quan sát Gradle báo no matching toolchains (nếu không còn nguồn hợp lệ).
5. Khôi phục cấu hình đúng, chạy lại.
6. Nếu có JDK21, thử `tasks.named('run', JavaExec) { javaLauncher = javaToolchains.launcherFor { languageVersion = JavaLanguageVersion.of(21) } }` và giải thích output đổi thế nào.

**Tiêu chí đạt:** Bạn phân biệt được Gradle JVM, Java toolchain và JVM của task; khai được version/vendor/implementation; đưa được local JDK vào discovery qua `paths` hoặc `fromEnv`; biết điều kiện auto-provisioning; chẩn đoán được vì sao Gradle không chọn JDK mình mong muốn.

## 17. Checklist áp dụng cho nhóm phát triển

- [ ] Gradle Wrapper version hỗ trợ JDK dùng cho Gradle Daemon.
- [ ] Project toolchain khai `languageVersion` rõ ràng.
- [ ] Vendor chỉ pin nếu có requirement; không dùng filter quá chặt không cần thiết.
- [ ] Nếu vendor/implementation được khai, có `languageVersion`.
- [ ] Không đặt những absolute local JDK paths vào `build.gradle`.
- [ ] JDK locations được cung cấp qua user/CI properties hoặc env vars khi cần.
- [ ] `paths` trỏ đúng JDK home, không phải parent directory.
- [ ] `fromEnv` khai **tên biến**, mỗi tên có value hợp lệ.
- [ ] Không nghĩ custom path được ưu tiên hơn auto-detected sources.
- [ ] Auto-download cần resolver plugin/repository thật và egress policy phù hợp.
- [ ] Không phụ thuộc `java -version` của shell để phỏng đoán compiler Gradle.
- [ ] Toolchain cho JavaCompile, Test, JavaExec và Javadoc được cấu hình phù hợp.
- [ ] `--release` được dùng khi cần chạy trên Java runtime thấp hơn toolchain compiler.
- [ ] CI ghi nhận Gradle JVM, JDK candidates và vendor/patch khi reproducibility quan trọng.
- [ ] IDE Gradle JVM setting không bị nhầm với project toolchain.
- [ ] Không lưu credentials/khóa riêng trong Gradle properties hoặc build scripts được commit.
- [ ] Có kiểm thử với toolchain và runtime versions thực sự mà sản phẩm phải hỗ trợ.

## 18. Tài liệu Gradle chính thức

- [Gradle — Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html): toolchain version, vendor, implementation, auto-detection, custom locations, precedence và provisioning.
- [Gradle — Build Environment Configuration](https://docs.gradle.org/current/userguide/build_environment.html): `org.gradle.java.home`, `org.gradle.java.installations.*`, Daemon JVM args và property semantics.
- [Gradle — Toolchain Resolver Plugins](https://docs.gradle.org/current/userguide/toolchain_plugins.html): tự định nghĩa resolver và toolchain download repositories.
- [Gradle — Java Toolchains API: `JvmVendorSpec`](https://docs.gradle.org/current/javadoc/org/gradle/jvm/toolchain/JvmVendorSpec.html): vendor constants và `matching`.
- [Gradle — JavaToolchainSpec API](https://docs.gradle.org/current/javadoc/org/gradle/jvm/toolchain/JavaToolchainSpec.html): languageVersion/vendor/implementation.
- [Gradle — Gradle Daemon](https://docs.gradle.org/current/userguide/gradle_daemon.html): JVM chạy Daemon và Daemon JVM criteria.
- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): Java tasks, Java extension, compiler/test/javadoc behavior.
- [Gradle — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html): JavaExec `run`, application mainClass.
- [Gradle — Java Toolchain Service](https://docs.gradle.org/current/javadoc/org/gradle/jvm/toolchain/JavaToolchainService.html): `compilerFor`, `launcherFor`, `javadocToolFor` providers.
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): lazy task registration/configuration thay eager realization.

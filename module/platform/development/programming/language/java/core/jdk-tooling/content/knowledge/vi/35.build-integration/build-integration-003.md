# Java Toolchains trong Gradle

Gradle Java Toolchains cho phép khai báo rõ JDK mà từng phần của build cần sử dụng. Một dự án có thể được biên dịch bằng JDK 17, chạy test bằng JDK 21 và vẫn chạy Gradle Daemon bằng JDK 24. Cấu hình này giúp mọi máy developer và CI chọn cùng loại compiler/runtime theo yêu cầu của dự án, giảm lỗi do mỗi máy đang cài một Java khác nhau.

Toolchain là tập công cụ JVM mà một task cần dùng: Java compiler `javac`, Java launcher `java` hoặc Javadoc tool. Với Java plugin, Gradle có thể áp dụng toolchain cho các task compile, test và Javadoc. Bạn cũng có thể chọn toolchain riêng cho từng task hoặc tự định nghĩa task dùng một JDK cụ thể.

## 1. Vì sao cần Java Toolchains?

Không có toolchain, Gradle thường dùng JDK mặc định của môi trường để biên dịch và chạy code. Máy developer A có JDK 17, developer B có JDK 21, CI có JDK 24; cùng một lệnh build có thể tạo ra hành vi khác nhau hoặc thất bại khi dùng API/ngôn ngữ mới.

Ví dụ, dự án muốn:

- Biên dịch code bằng Java 17.
- Chỉ sử dụng API có từ Java 11 trở xuống để sản phẩm chạy được trên Java 11.
- Chạy một bộ test bổ sung bằng Java 21.
- Tạo Javadoc bằng JDK 17.
- Chạy Gradle Daemon bằng JDK 24.

Nếu chỉ đổi `JAVA_HOME`, tất cả công cụ Java được khởi chạy từ môi trường có thể bị ảnh hưởng. Toolchains cho phép mô tả yêu cầu ngay trong build script, còn Gradle chọn đúng compiler/launcher cho task tương ứng.

### 1.1. Ba JVM/JDK cần phân biệt

Một build Gradle có thể liên quan tới ba vai trò Java riêng:

| Vai trò | Nhiệm vụ | Cách chọn phổ biến |
|---|---|---|
| Gradle Client JVM | Chạy script `gradle` hoặc `gradlew` và gửi yêu cầu build tới Daemon | `JAVA_HOME`, `PATH` hoặc IDE |
| Gradle Daemon JVM | Chạy Gradle build engine, cấu hình project và thực thi task | `JAVA_HOME` mặc định, `org.gradle.java.home` hoặc Daemon JVM criteria |
| Project Toolchain | Cung cấp `javac`, `java` và `javadoc` cho các task của dự án | `java.toolchain` hoặc cấu hình riêng cho task |

Toolchain trong `build.gradle` không tự đổi JVM chạy Gradle Daemon. Ngược lại, chọn JDK cho Daemon không tự bảo đảm compiler của dự án dùng cùng JDK đó.

Ví dụ: terminal khởi chạy Gradle bằng JDK 24; Gradle Daemon chạy bằng JDK 24; `compileJava` dùng compiler JDK 17; task `run` dùng Java 17; task `runOn21` dùng Java 21. Đây là cấu hình hợp lệ nếu phiên bản Gradle hỗ trợ chạy trên JDK 24 và các JDK được yêu cầu có sẵn hoặc có thể được provision.

## 2. Cấu hình toolchain ở cấp project

Với Java plugin và Kotlin DSL, cấu hình tối thiểu trong `build.gradle.kts`:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

Với Groovy DSL trong `build.gradle`:

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

Khi build chạy, Gradle tìm một JDK phù hợp với Java 17. Nếu tìm được, các task Java plugin hỗ trợ toolchain sẽ dùng tool đó. Nếu không tìm được, Gradle chỉ tự tải JDK khi cấu hình download repository/resolver phù hợp đã được thêm vào build.

### 2.1. Task nào dùng toolchain?

Với Java plugin, toolchain cấp các công cụ cho những task sau:

| Task | Công cụ | Vai trò |
|---|---|---|
| `compileJava` | `JavaCompiler` | Biên dịch source thành bytecode |
| `compileTestJava` | `JavaCompiler` | Biên dịch source test |
| `test` | `JavaLauncher` | Khởi chạy test JVM |
| `run` của Application plugin | `JavaLauncher` | Khởi chạy ứng dụng |
| `javadoc` | `JavadocTool` | Tạo tài liệu API |

Gradle cũng dùng toolchain cho những task JVM khác được plugin tích hợp hỗ trợ. Một task tự viết không tự động dùng toolchain chỉ vì project có khai báo `java.toolchain`; task đó cần nhận `JavaCompiler`, `JavaLauncher`, `JavadocTool` hoặc đường dẫn executable tương ứng.

### 2.2. Chọn theo Java version, vendor và implementation

Cấu hình cơ bản chỉ yêu cầu major language version:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

Nếu tổ chức cần một bản phân phối JDK cụ thể, thêm vendor:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
        vendor.set(JvmVendorSpec.ADOPTIUM)
    }
}
~~~

Một số vendor thường dùng:

| JvmVendorSpec | Bản phân phối/nhà cung cấp |
|---|---|
| `ADOPTIUM` | Eclipse Temurin |
| `AMAZON` | Amazon Corretto |
| `AZUL` | Azul Zulu |
| `MICROSOFT` | Microsoft Build of OpenJDK |
| `ORACLE` | Oracle JDK |
| `IBM` | IBM Semeru |

Nếu vendor không nằm trong danh sách chuẩn, có thể dùng `JvmVendorSpec.matching("...")` để so khớp chuỗi `java.vendor`.

Có thể giới hạn implementation JVM. Ví dụ chỉ chọn OpenJ9/J9:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
        vendor.set(JvmVendorSpec.IBM)
        implementation.set(JvmImplementation.J9)
    }
}
~~~

Gradle cũng có thuộc tính `nativeImageCapable` cho trường hợp cần JDK có GraalVM Native Image:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
        nativeImageCapable.set(true)
    }
}
~~~

Quy tắc quan trọng: nếu chỉ định vendor hoặc implementation thì phải chỉ định `languageVersion`. Một `JavaToolchainSpec` rỗng có nghĩa dùng toolchain của build hiện tại; một spec có vendor/implementation mà không có language version là không hợp lệ.

### 2.3. Chọn theo major version hay patch version?

`languageVersion` chọn Java major version, ví dụ 17. Nó không phải cách pin chính xác một bản vá như 17.0.15. Khi có nhiều bản cài cùng thỏa mãn, Gradle áp dụng thứ tự ưu tiên để chọn một bản.

Nếu build phụ thuộc vào hành vi riêng của vendor hoặc implementation, khai báo thêm các tiêu chí đó. Nếu cần kiểm soát chặt patch level, hãy quản lý image/toolchain trong CI hoặc hạ tầng cài đặt theo chính sách của tổ chức; đừng giả định `JavaLanguageVersion.of(17)` đồng nghĩa với một bản patch cụ thể.

## 3. Toolchain và --release: hai mục đích khác nhau

Toolchain chọn JDK thực sự dùng để biên dịch/chạy task. Tùy chọn compiler `--release` giới hạn language level, bytecode target và bộ API Java mà code được phép tham chiếu.

Ví dụ dùng JDK 17 nhưng chỉ cho phép code tương thích Java 11:

Kotlin DSL:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(11)
}
~~~

Groovy DSL:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 11
}
~~~

Compiler chạy từ JDK 17, nhưng `--release 11` ngăn source sử dụng API chỉ có từ Java 12 trở lên và tạo class file tương thích Java 11. Cách này hữu ích khi CI chuẩn hóa compiler mới nhưng sản phẩm vẫn hỗ trợ runtime cũ.

### 3.1. So sánh các cách đặt Java version

| Cấu hình | Chọn JDK thật? | Giới hạn API theo release? | Phạm vi |
|---|---|---|---|
| Java Toolchains | Có | Không tự động | Project/task |
| `options.release` | Không | Có | JavaCompile task |
| `sourceCompatibility` + `targetCompatibility` | Không | Không đầy đủ như release | JavaCompile/project |
| `JAVA_HOME` | Chọn mặc định môi trường | Không | Môi trường/tiến trình |
| IDE Gradle JVM | Chọn JVM chạy build trong IDE | Không | IDE |

`sourceCompatibility` điều khiển mức cú pháp Java mà compiler chấp nhận; `targetCompatibility` điều khiển mức bytecode được tạo. Hai thuộc tính này không chọn compiler JDK và không bảo đảm code không gọi API mới đã được backport vào JDK đang dùng.

Với compiler Java 9 trở lên, `--release` thường là cách chặt chẽ hơn khi cần cross-compile. Không đặt `options.release` cao hơn JDK compiler có thể hỗ trợ. Toolchain và `--release` có thể kết hợp để vừa cố định compiler vừa giới hạn nền tảng đích.

### 3.2. Không nhầm bytecode version với runtime version

Class file có major version riêng. Một số mốc phổ biến:

| Java release | Class file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 24 | 68 |

Có thể kiểm tra class file bằng:

~~~bash
javap -verbose build/classes/java/main/demo/ToolchainProbe.class
~~~

Tìm dòng `major version`. Nếu build bằng JDK 17 với `--release 11`, class file phải có major version 55. Việc compiler chạy bằng Java 17 không có nghĩa output phải là bytecode Java 17.

## 4. Chọn toolchain riêng cho từng task

Một project có thể dùng một JDK mặc định và override task cụ thể. Gradle cung cấp extension `javaToolchains` với ba provider chính:

- `compilerFor` trả về `JavaCompiler`.
- `launcherFor` trả về `JavaLauncher`.
- `javadocToolFor` trả về `JavadocTool`.

### 4.1. Compile bằng Java 17, chạy test bằng Java 21

Kotlin DSL:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    javaCompiler.set(javaToolchains.compilerFor {
        languageVersion.set(JavaLanguageVersion.of(17))
    })
}

tasks.withType<Test>().configureEach {
    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion.set(JavaLanguageVersion.of(21))
    })
}
~~~

Groovy DSL:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    javaCompiler = javaToolchains.compilerFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(Test).configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

Khi chạy `test`, Gradle khởi chạy test JVM bằng Java 21. Compiler của source chính và test vẫn dùng Java 17. Nếu dự án cần test trên nhiều runtime, đăng ký thêm các `Test` task riêng như `testOn17`, `testOn21` và nối chúng vào task `check` theo yêu cầu của nhóm.

### 4.2. Chạy ứng dụng bằng một JDK khác

Với Application plugin:

~~~kotlin
tasks.register<JavaExec>("runOn21") {
    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion.set(JavaLanguageVersion.of(21))
    })
    classpath = sourceSets["main"].runtimeClasspath
    mainClass.set("demo.ToolchainProbe")
}
~~~

Task `runOn21` chạy classpath của ứng dụng bằng Java 21, dù project toolchain mặc định có thể là Java 17.

### 4.3. Chọn Javadoc tool

Nếu cần Javadoc được tạo bởi một phiên bản JDK riêng:

~~~kotlin
tasks.withType<Javadoc>().configureEach {
    javadocTool.set(javaToolchains.javadocToolFor {
        languageVersion.set(JavaLanguageVersion.of(17))
    })
}
~~~

### 4.4. Dùng toolchain trong custom task

Một custom task cần Java executable nên nhận provider một cách lazy:

~~~kotlin
val java21 = javaToolchains.launcherFor {
    languageVersion.set(JavaLanguageVersion.of(21))
}

tasks.register<JavaExec>("inspectWith21") {
    javaLauncher.set(java21)
    classpath = sourceSets["main"].runtimeClasspath
    mainClass.set("demo.ToolchainProbe")
}
~~~

Giữ provider thay vì gọi `get()` sớm trong giai đoạn cấu hình. Gradle có thể resolve/provision JDK khi task thực sự cần chạy. Việc resolve toolchain quá sớm có thể làm build tải JDK ngay cả khi task đó không được thực thi.

## 5. Gradle tự phát hiện JDK đã cài

Gradle tự động dò các JDK/JRE cục bộ theo mặc định. Những nguồn thường được nhận diện gồm:

- Các vị trí cài đặt thông thường của Windows, Linux và macOS.
- Biến môi trường `JAVA_HOME`.
- Các package manager như SDKMAN!, asdf-vm và Jabba.
- Maven toolchains specification.
- Các JDK cài cùng IntelliJ IDEA.

Gradle ưu tiên JDK khi cả JDK và JRE đều thỏa mãn yêu cầu, vì compile task cần compiler `javac`.

### 5.1. Liệt kê toolchain mà Gradle phát hiện

Chạy:

~~~bash
./gradlew -q javaToolchains
~~~

Trên Windows:

~~~powershell
.\gradlew.bat -q javaToolchains
~~~

Task `javaToolchains` hiển thị:

- Auto-detection có bật không.
- Auto-download có bật không.
- Language version.
- Vendor.
- Architecture.
- Đây là JDK hay JRE.
- Gradle phát hiện từ nguồn nào.

Đây là lệnh đầu tiên nên dùng khi Gradle báo không tìm được JDK phù hợp.

### 5.2. Thêm đường dẫn JDK tùy chỉnh

Nếu JDK nằm ngoài các vị trí Gradle tự dò, thêm đường dẫn vào `gradle.properties`:

~~~properties
org.gradle.java.installations.paths=/opt/jdks/jdk-17,/opt/jdks/jdk-21
~~~

Ví dụ trên Linux. Trên Windows, dùng đường dẫn thực tế của JDK đã cài:

~~~properties
org.gradle.java.installations.paths=C:/Java/jdk-17,C:/Java/jdk-21
~~~

Gradle có thể kết hợp đường dẫn tùy chỉnh với auto-detection mặc định. Cấu hình đường dẫn không tự cài đặt JDK; thư mục phải tồn tại và có các executable cần thiết.

### 5.3. Tắt auto-detection

Trong `gradle.properties`:

~~~properties
org.gradle.java.installations.auto-detect=false
~~~

Hoặc truyền system property khi gọi Gradle:

~~~bash
./gradlew -Dorg.gradle.java.installations.auto-detect=false build
~~~

Chỉ tắt auto-detection khi build environment đã quản lý đầy đủ đường dẫn toolchain. Nếu không, build có thể không tìm được JDK dù máy đã cài.

## 6. Auto-provisioning: Gradle tự tải JDK

Toolchain auto-provisioning cho phép Gradle tải JDK phù hợp khi không tìm thấy cài đặt cục bộ. JDK tải về được lưu trong Gradle User Home, thường nằm trong thư mục `jdks`, và có thể dùng lại cho những build sau.

Cần phân biệt hai bước:

1. Build khai báo yêu cầu JDK, ví dụ Java 17.
2. Một toolchain resolver plugin cung cấp repository để Gradle tìm và tải JDK tương ứng.

Gradle không tự biết mọi nguồn download JDK nếu build chưa cấu hình resolver.

### 6.1. Dùng Foojay toolchain resolver

Một lựa chọn phổ biến là Foojay Toolchains Resolver. Ví dụ trong `settings.gradle.kts`:

~~~kotlin
plugins {
    id("org.gradle.toolchains.foojay-resolver-convention").version("1.0.0")
}
~~~

Sau khi khai báo resolver, project có thể yêu cầu toolchain như bình thường:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

Nếu không có JDK 17 phù hợp cục bộ, Gradle có thể truy vấn resolver và tải một JDK GA phù hợp. Ví dụ plugin version 1.0.0 được dùng trong Gradle User Manual hiện hành; hãy kiểm tra phiên bản plugin, chính sách bảo mật và nguồn phân phối được tổ chức chấp thuận trước khi nâng cấp.

### 6.2. Giới hạn của auto-provisioning

- Gradle chỉ tự tải các bản Java GA; early-access release không được auto-provision theo cơ chế này.
- JDK đã tải về không được tự động cập nhật khi có patch mới.
- Auto-provisioning chỉ chạy khi auto-detection không tìm thấy toolchain phù hợp.
- Resolver cần truy cập mạng/repository; proxy, TLS inspection hoặc firewall có thể làm download thất bại.
- JDK được tải về dùng chung trong Gradle User Home cho các build tiếp theo.

Không nên để CI âm thầm tải từ nguồn không được phê duyệt. Hãy pin plugin resolver, quản lý cache, giới hạn vendor khi cần và dùng mirror/repository nội bộ nếu tổ chức yêu cầu.

### 6.3. Tắt auto-download

Trong `gradle.properties`:

~~~properties
org.gradle.java.installations.auto-download=false
~~~

Hoặc:

~~~bash
./gradlew -Dorg.gradle.java.installations.auto-download=false build
~~~

Khi tắt auto-download, tất cả toolchain yêu cầu phải có sẵn cục bộ hoặc trong đường dẫn tùy chỉnh. Sau khi thay đổi cấu hình toolchain, có thể dừng daemon để Gradle làm mới thông tin đã cache:

~~~bash
./gradlew --stop
~~~

## 7. Thứ tự Gradle chọn toolchain

Khi có nhiều JDK phù hợp, Gradle sắp xếp các bản cài theo quy tắc ưu tiên rồi chọn bản đầu tiên. Các yếu tố quan trọng gồm:

1. JDK đang chạy Gradle được ưu tiên trong một số trường hợp.
2. JDK được ưu tiên hơn JRE.
3. Vendor có thứ tự ưu tiên theo danh sách Gradle nhận diện.
4. Phiên bản phù hợp mới hơn được ưu tiên.
5. Đường dẫn cài đặt là tiêu chí cuối để quyết định ổn định khi các tiêu chí khác tương đương.

Vì vậy, chỉ khai báo `languageVersion = 17` không nhất thiết chọn cùng một vendor trên mọi máy. Nếu cần vendor cụ thể, khai báo `vendor`; nếu cần implementation cụ thể, khai báo `implementation`.

Gradle ghi nhận major version và các thuộc tính vendor/implementation đã khai báo làm input cho compile/test tasks. Điều này giúp build cache và up-to-date checks phân biệt các toolchain khác nhau. Nếu build phụ thuộc vào patch/vendor nhưng không khai báo tiêu chí đó, hãy quản lý môi trường CI chặt hơn và tránh giả định rằng mọi JDK cùng major đều có hành vi giống hệt nhau.

## 8. Toolchain của project khác JVM chạy Gradle Daemon

Đây là điểm thường gây nhầm lẫn nhất khi cấu hình build.

### 8.1. JAVA_HOME và org.gradle.java.home

`JAVA_HOME` thường quyết định Java executable dùng để khởi chạy Gradle Client và là mặc định cho Gradle Daemon nếu không có cấu hình khác.

Có thể đặt JVM riêng cho daemon bằng `org.gradle.java.home` trong `gradle.properties`:

~~~properties
org.gradle.java.home=/opt/jdks/jdk-21
~~~

Trên Windows:

~~~properties
org.gradle.java.home=C:/Java/jdk-21
~~~

Cấu hình này tác động tới JVM chạy Gradle Daemon. Nó không thay thế `java.toolchain` trong build script.

### 8.2. Daemon JVM criteria

Các phiên bản Gradle hỗ trợ Daemon JVM criteria cho phép lưu yêu cầu JVM của Gradle Daemon vào repository. Ví dụ:

~~~bash
./gradlew updateDaemonJvm --jvm-version=17
~~~

Có thể chỉ định vendor:

~~~bash
./gradlew updateDaemonJvm --jvm-version=17 --jvm-vendor=adoptium
~~~

Task tạo/cập nhật file:

~~~text
gradle/gradle-daemon-jvm.properties
~~~

File này mô tả JDK mà Gradle Daemon cần dùng. Khi có criteria, nó được ưu tiên hơn `JAVA_HOME` và `org.gradle.java.home`. Cơ chế tạo URL provisioning cần toolchain download repository được cấu hình. Có thể commit file này để chuẩn hóa daemon JVM giữa các máy.

Daemon JVM criteria vẫn khác project toolchain: một cái chạy build engine, một cái cung cấp compiler/launcher cho code của dự án.

### 8.3. Gradle Wrapper chọn phiên bản Gradle, không chọn JDK project

Wrapper lưu phiên bản Gradle trong:

~~~text
gradle/wrapper/gradle-wrapper.properties
~~~

Ví dụ tạo wrapper cho một bản Gradle:

~~~bash
gradle wrapper --gradle-version 9.2.1
~~~

Sau đó nhóm phát triển dùng `./gradlew` hoặc `gradlew.bat` để chạy cùng Gradle distribution. Wrapper giúp đồng nhất phiên bản build tool; JDK chạy Gradle vẫn được chọn bởi môi trường/daemon criteria, còn JDK biên dịch và chạy ứng dụng được chọn bởi toolchain.

## 9. Tương thích giữa Gradle và Java

Cần kiểm tra hai câu hỏi riêng:

1. JDK nào được hỗ trợ để chạy chính Gradle/Daemon?
2. JDK nào được hỗ trợ làm toolchain để compile hoặc test?

Một Java release có thể được hỗ trợ cho toolchain trước khi được hỗ trợ làm JVM chạy Gradle. Ví dụ, bảng tương thích của Gradle ghi nhận Java 17 toolchain và runtime từ Gradle 7.3 trở lên; Java 21 toolchain từ Gradle 8.4 và chạy Gradle từ 8.5; Java 24 toolchain và runtime từ Gradle 8.14. Bảng thay đổi theo Gradle release, nên phải tra đúng phiên bản dự án đang dùng.

Gradle 9.x yêu cầu JVM hiện đại hơn các nhánh cũ; không thể lấy một JDK mới rồi giả định mọi Gradle version đều khởi chạy được. Nếu build báo unsupported class file version hoặc unsupported JVM, kiểm tra:

- Gradle Wrapper version.
- Java version đang khởi chạy Gradle Client.
- JVM của Gradle Daemon.
- Java toolchain mà task yêu cầu.
- Compatibility matrix chính thức của Gradle.

Không nâng Gradle chỉ để đổi toolchain nếu plugin khác trong build chưa hỗ trợ phiên bản Gradle mới. Hãy kiểm tra cả Gradle version, Java version và Android/Kotlin/Scala/Groovy plugin compatibility.

## 10. Toolchains trong multi-project và các JVM language plugin

Trong multi-project build, nên dùng cùng một convention để các subproject có yêu cầu Java nhất quán. Có thể đặt cấu hình trong convention plugin hoặc áp dụng vào từng project có Java plugin.

Ví dụ cấu hình chung trong convention plugin Kotlin DSL:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

Các subproject áp dụng convention plugin này sẽ cùng dùng Java 17 trừ khi task/project có override cụ thể.

Gradle hỗ trợ toolchain cho Java plugin. Groovy plugin hỗ trợ compile toolchain nhưng Groovydoc có giới hạn theo Gradle User Manual. Scala plugin hỗ trợ compilation và Scaladoc. Kotlin Gradle plugin có API toolchain riêng, thường cấu hình bằng `kotlin { jvmToolchain(17) }`; cần kiểm tra tài liệu và version của Kotlin Gradle plugin đang dùng.

Không giả định một khai báo Java toolchain tự cấu hình mọi compiler bên thứ ba. Plugin có thể cần nhận toolchain provider hoặc cấu hình riêng cho compiler/task của nó.

## 11. Thực hành Java 17+: build bằng JDK 17, chạy bằng JDK 21

Ví dụ này chứng minh ba việc:

- Gradle Daemon có thể chạy trên JDK khác project toolchain.
- Compile dùng JDK 17 nhưng `--release 11` tạo bytecode Java 11.
- Task `runOn21` dùng JDK 21 trong khi task `run` mặc định dùng JDK 17.

Tạo cấu trúc:

~~~text
toolchain-demo/
├── settings.gradle.kts
├── build.gradle.kts
└── src/
    └── main/
        └── java/
            └── demo/
                └── ToolchainProbe.java
~~~

### 11.1. settings.gradle.kts

~~~kotlin
rootProject.name = "toolchain-demo"
~~~

### 11.2. build.gradle.kts

~~~kotlin
plugins {
    application
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("demo.ToolchainProbe")
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(11)
}

tasks.register<JavaExec>("runOn21") {
    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion.set(JavaLanguageVersion.of(21))
    })
    classpath = sourceSets["main"].runtimeClasspath
    mainClass.set("demo.ToolchainProbe")
}

tasks.register("showToolchain") {
    doLast {
        val compiler = javaToolchains.compilerFor {
            languageVersion.set(JavaLanguageVersion.of(17))
        }.get()
        println("COMPILER_FEATURE=" + compiler.metadata.languageVersion.asInt())
    }
}
~~~

### 11.3. ToolchainProbe.java

~~~java
package demo;

public final class ToolchainProbe {
    public static void main(String[] args) {
        System.out.println(
            "RUNTIME_FEATURE=" + Runtime.version().feature()
        );
    }
}
~~~

### 11.4. Build và kiểm tra

Đảm bảo máy có JDK 17 và JDK 21. Kiểm tra Gradle nhận diện các bản cài:

~~~bash
./gradlew -q javaToolchains
~~~

Chạy build, ứng dụng bằng toolchain mặc định và task riêng bằng Java 21:

~~~bash
./gradlew --no-daemon --console=plain clean build run runOn21 showToolchain
~~~

Output quan trọng:

~~~text
> Task :run
RUNTIME_FEATURE=17

> Task :runOn21
RUNTIME_FEATURE=21

> Task :showToolchain
COMPILER_FEATURE=17

BUILD SUCCESSFUL
~~~

Dòng `COMPILER_FEATURE=17` xác nhận provider chọn compiler Java 17. Task `run` dùng Java 17 theo toolchain project; `runOn21` dùng launcher Java 21 riêng.

Kiểm tra bytecode do `--release 11` tạo ra:

~~~bash
javap -verbose build/classes/java/main/demo/ToolchainProbe.class
~~~

Tìm:

~~~text
major version: 55
~~~

Major version 55 xác nhận class file tương thích Java 11. Ví dụ đã được biên dịch và chạy thành công với Gradle 9.2.1; Gradle Daemon chạy trên JDK 24.0.2, compiler toolchain là Amazon Corretto 17 và task riêng chạy bằng Microsoft JDK 21. Các phiên bản JDK/vendor thực tế được Gradle phát hiện phụ thuộc máy đang chạy.

## 12. Dùng toolchain trong CI/CD

Một pipeline ổn định nên làm rõ các lớp Java:

1. Dùng Gradle Wrapper để cố định Gradle version.
2. Chọn JVM chạy Gradle/Daemon theo compatibility matrix và policy.
3. Khai báo project toolchain trong build script.
4. Dùng resolver đã được phê duyệt hoặc cài sẵn JDK cần thiết trên runner.
5. Cache Gradle User Home nếu cần tái sử dụng các JDK đã provision.
6. Chạy `javaToolchains` trong bước chẩn đoán khi runner không tìm thấy JDK.
7. Chạy build/test trên cùng toolchain spec giữa developer và CI.
8. Nếu cần kiểm tra nhiều runtime, tạo test task riêng cho từng Java version.
9. Lưu output `--info` và Gradle daemon logs khi điều tra lỗi.

Ví dụ workflow trên Linux:

~~~bash
./gradlew -q javaToolchains
./gradlew clean check
~~~

Nếu runner không được phép truy cập internet, cài JDK vào image hoặc mount vào đường dẫn toolchain được cấu hình. Đừng phụ thuộc vào việc tự tải JDK trong mỗi lần build nếu môi trường CI có chính sách mạng hạn chế.

## 13. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| No matching toolchains found | Không có JDK thỏa mãn language version/vendor/implementation | Chạy `javaToolchains`; cài JDK hoặc cấu hình resolver |
| Gradle không nhận diện JDK đã cài | Đường dẫn ngoài vị trí auto-detection hoặc cấu hình auto-detect tắt | Thêm `org.gradle.java.installations.paths` và kiểm tra `bin/java`/`bin/javac` |
| Gradle không khởi động trên Java mới | Gradle version chưa hỗ trợ JVM đó | Kiểm tra Gradle Wrapper và compatibility matrix |
| Compile dùng JDK khác dự kiến | Task chưa dùng project toolchain hoặc task tự định nghĩa không nhận provider | Kiểm tra `JavaCompile.javaCompiler` và cấu hình task cụ thể |
| Test chạy bằng Java khác compile | `Test.javaLauncher` có override hoặc IDE cấu hình khác | Kiểm tra task `Test` và Gradle JVM trong IDE |
| JDK tự tải nhưng build thất bại | Chưa cấu hình resolver, mạng/proxy/TLS hoặc không có GA release phù hợp | Kiểm tra settings plugin, repository, proxy và log download |
| Gradle chọn vendor không mong muốn | Chỉ khai báo major version và nhiều JDK cùng thỏa mãn | Khai báo `vendor` hoặc `implementation` |
| Sửa toolchain nhưng Gradle vẫn dùng lựa chọn cũ | Daemon còn giữ metadata/cấu hình đã cache | Chạy `./gradlew --stop` rồi build lại |
| `--release` không thay runtime khi chạy ứng dụng | Release chỉ giới hạn compile/bytecode/API | Cấu hình `Test.javaLauncher` hoặc `JavaExec.javaLauncher` |
| JDK cài là JRE nên compile thất bại | Không có compiler `javac` | Cài JDK, không chỉ cài JRE |
| IDE và terminal chọn JDK khác nhau | Gradle JVM trong IDE khác `JAVA_HOME` hoặc toolchain | Cấu hình Gradle JVM của IDE và kiểm tra toolchain trong build |
| Alpine/musl phát hiện nhiều toolchain không đúng | Hạn chế phát hiện JVM trong môi trường musl | Ưu tiên một toolchain hoặc dùng môi trường glibc đã kiểm thử |

### 13.1. Kiểm tra thông tin chi tiết khi lỗi

Liệt kê toolchain:

~~~bash
./gradlew -q javaToolchains
~~~

Xem log chi tiết khi Gradle resolve task:

~~~bash
./gradlew --info compileJava
~~~

Kiểm tra Gradle runtime:

~~~bash
./gradlew --version
~~~

Kiểm tra Java mặc định của shell:

~~~bash
java --version
echo "$JAVA_HOME"
~~~

Dừng Daemon nếu vừa thay đổi đường dẫn/toolchain:

~~~bash
./gradlew --stop
~~~

Trên PowerShell, xem biến môi trường:

~~~powershell
java --version
$env:JAVA_HOME
~~~

Không xóa toàn bộ Gradle cache chỉ vì toolchain không được tìm thấy. Trước hết hãy kiểm tra đường dẫn, version, vendor, auto-detection, resolver và daemon.

## 14. Lưu ý về tính tái lập và bảo mật

Toolchain giúp build nhất quán hơn, nhưng không tự khóa toàn bộ môi trường. Kết quả còn phụ thuộc:

- Gradle Wrapper version.
- JVM chạy Gradle Daemon.
- JDK major/vendor/implementation được chọn.
- Dependency/plugin version.
- OS, architecture, locale và environment variables.
- Compiler flags, annotation processors và native tools.

Khi dùng auto-provisioning, JDK được tải từ repository resolver. Chỉ cấu hình resolver đáng tin cậy, pin version plugin và tuân theo chính sách vendor/license của tổ chức. Không đưa credential repository vào build script; dùng Gradle credentials hoặc secret store theo chính sách CI.

Toolchain được provision nằm trong Gradle User Home và có thể được các build khác trên máy dùng lại. Hãy quản lý quyền truy cập, dung lượng cache và chính sách cập nhật/loại bỏ JDK trên runner.

## 15. Checklist trước khi hoàn tất build integration

- [ ] Đã cố định Gradle Wrapper version.
- [ ] JVM chạy Gradle Daemon được Gradle version hỗ trợ.
- [ ] Đã phân biệt Client JVM, Daemon JVM và project toolchain.
- [ ] Đã khai báo `java.toolchain.languageVersion`.
- [ ] Đã chọn vendor/implementation nếu yêu cầu build cần.
- [ ] Đã kiểm tra `javaToolchains` để biết Gradle chọn JDK nào.
- [ ] Compile, Test, JavaExec và Javadoc dùng đúng toolchain.
- [ ] Đã dùng `options.release` nếu cần giới hạn API/bytecode đích.
- [ ] Resolver plugin và download repository được phê duyệt nếu dùng auto-provisioning.
- [ ] CI có JDK cục bộ hoặc quyền tải JDK phù hợp.
- [ ] Đã kiểm tra Gradle compatibility matrix cho Java runtime và toolchain.
- [ ] Đã kiểm thử build trong IDE và terminal.
- [ ] Đã dừng Daemon sau khi thay đổi cấu hình toolchain quan trọng.
- [ ] Đã ghi lại toolchain/JDK trong log build để điều tra khi cần.

## 16. Ghi nhớ

Java Toolchains cho Gradle là cách khai báo JDK mà project và từng task cần dùng. Dùng `java.toolchain.languageVersion` để chuẩn hóa compile/test/Javadoc; dùng `javaToolchains.compilerFor` hoặc `launcherFor` khi một task cần JDK riêng.

Kết hợp toolchain với `options.release` để kiểm soát cả compiler được chọn và API/bytecode đích. Dùng `javaToolchains` để xem JDK Gradle phát hiện, Foojay resolver khi cần auto-provisioning và Daemon JVM criteria khi muốn chuẩn hóa JVM chạy Gradle. Luôn kiểm tra compatibility matrix của đúng Gradle release, đặc biệt khi nâng JDK hoặc plugin.

Tài liệu tham khảo:

- [Toolchains for JVM projects — Gradle User Manual](https://docs.gradle.org/current/userguide/toolchains.html)
- [Gradle Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html)
- [Gradle Daemon and Daemon JVM criteria](https://docs.gradle.org/current/userguide/gradle_daemon.html)
- [Building Java & JVM projects](https://docs.gradle.org/current/userguide/building_java_projects.html)
- [Foojay Toolchains Resolver Plugin](https://github.com/gradle/foojay-toolchains)
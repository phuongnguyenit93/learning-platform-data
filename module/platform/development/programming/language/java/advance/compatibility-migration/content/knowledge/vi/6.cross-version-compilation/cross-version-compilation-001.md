# Phân biệt JDK chạy công cụ build, JDK biên dịch và JDK chạy ứng dụng

## 1. Vì sao phải phân biệt ba môi trường Java?

Khi một dự án khai báo “dùng Java 21”, thông tin đó chưa đủ để biết toàn bộ quá trình build và chạy ứng dụng đang dùng JDK nào. Một dự án có thể khởi chạy Gradle hoặc Maven bằng JDK 17, dùng JDK 21 làm compiler toolchain, tạo bytecode tương thích Java 17, chạy test trên Java 17 và triển khai artifact trên một runtime Java 17 khác. Một dự án khác có thể dùng JDK 21 ở cả ba giai đoạn. Hai cấu hình này có mục tiêu và giới hạn tương thích khác nhau.

Trong một quy trình Java, cần phân biệt ít nhất ba vai trò:

1. **JDK chạy công cụ build (build JVM):** JVM khởi chạy Gradle, Maven và các plugin chạy bên trong tiến trình build. Nó quyết định build tool và plugin có thể khởi động, thực thi hay không.
2. **JDK dùng để biên dịch (compiler JDK/toolchain):** JDK cung cấp `javac` và các compiler tool cần thiết để biến mã nguồn thành bytecode. Cùng với cấu hình release/source/target, nó quyết định cú pháp, API Java SE và định dạng class file mà compiler tạo ra.
3. **JDK/JVM chạy ứng dụng (application runtime):** JVM thực sự nạp và thực thi artifact trong test, staging hoặc production. Nó phải hiểu bytecode, cung cấp API cần thiết và đáp ứng yêu cầu runtime của các dependency.

Ba vai trò này có thể dùng cùng một phiên bản, nhưng không bắt buộc phải giống nhau. Việc chọn phiên bản cho mỗi vai trò phải dựa trên yêu cầu của build tool, compiler, dependency, môi trường triển khai và mức Java thấp nhất mà sản phẩm cam kết hỗ trợ.

Phân biệt đúng giúp tránh những kết luận sai thường gặp:

- “Máy đã cài JDK 21” không chứng minh Gradle/Maven đang chạy bằng JDK 21.
- “Build chạy trên JDK 21” không chứng minh compiler cũng dùng JDK 21; build tool có thể chọn toolchain riêng.
- “Compile thành công bằng JDK 21” không chứng minh artifact chạy được trên Java 17.
- “Unit test pass trên máy developer” không chứng minh test JVM và production runtime trong CI/container giống nhau.
- “Đặt target 17” không làm cho dependency bên thứ ba tự động tương thích Java 17.

## 2. Ba vai trò và trách nhiệm của từng JDK

### 2.1. JDK chạy công cụ build

Gradle và Maven là các chương trình Java. Khi gọi `./gradlew`, `gradlew.bat`, `mvn` hoặc Maven Wrapper, một JVM phải được khởi chạy để thực thi build tool. JVM này thường được chọn từ `JAVA_HOME`, `PATH` hoặc cấu hình của IDE/CI agent.

Build JVM thực hiện các công việc như:

- Nạp và chạy Gradle/Maven core, daemon và lifecycle.
- Nạp build script, plugin, extension và các tác vụ build viết bằng Java/Groovy/Kotlin.
- Thực thi các plugin sinh mã, kiểm tra dependency, đóng gói và tạo artifact.
- Điều phối compiler, test runner, code generator và các tiến trình con.
- Truy cập file system, repository, chứng thư, mạng và môi trường CI theo cấu hình build.

Vì plugin thường chạy trong cùng tiến trình build hoặc tương tác chặt với API của build tool, plugin cũng có yêu cầu về JVM và phiên bản Gradle/Maven. Một compiler toolchain mới hơn không thể giúp build khởi động nếu chính Gradle hoặc plugin đã lỗi trên build JVM.

Ví dụ, máy developer có cài JDK 21 nhưng terminal đang dùng `JAVA_HOME` trỏ tới JDK 17. Lệnh `./gradlew` có thể khởi động Gradle bằng Java 17. Nếu phiên bản Gradle hiện tại yêu cầu JVM mới hơn, lỗi xảy ra trước khi project được cấu hình và trước khi task compile chọn compiler toolchain.

### 2.2. JDK dùng để biên dịch

Compiler JDK cung cấp `javac`, compiler libraries và các công cụ liên quan. Trong Gradle, Java Toolchains có thể chọn JDK cho `JavaCompile`. Trong Maven, Maven Toolchains và các plugin hỗ trợ toolchain có thể chọn JDK khác với JVM đang chạy Maven.

Compiler JDK ảnh hưởng đến:

- Compiler implementation và khả năng hiểu các tính năng ngôn ngữ.
- API compiler mà annotation processor hoặc compiler plugin sử dụng.
- Các công cụ chạy trong quá trình compile, như annotation processor, code generator và bytecode instrumentation ở compile time.
- Khả năng dùng `--release`, `--source` và `--target` để xác định hợp đồng Java của artifact.

Cần phân biệt **phiên bản JDK của compiler** với **release target của artifact**. JDK 21 có thể biên dịch mã nguồn theo release 17 bằng `--release 17`. Khi đó compiler chạy trên JDK 21 nhưng class file được tạo theo định dạng Java 17 và compiler giới hạn việc sử dụng API Java SE ở mức Java 17.

Ngược lại, chỉ dùng `-source 17 -target 17` không mang lại cùng mức kiểm soát API như `--release 17`. Mã nguồn có thể vô tình tham chiếu API Java SE chỉ có ở JDK 21, rồi tạo bytecode target 17 nhưng không chạy được trên JVM 17.

### 2.3. JDK/JVM chạy ứng dụng

Application runtime là JVM thực sự nạp và chạy artifact. Runtime có thể là JDK đầy đủ, một JRE distribution, runtime image tùy biến bằng `jlink`, hoặc môi trường runtime do container cung cấp. Điều quan trọng là JVM và các module/API cần thiết phải đáp ứng yêu cầu của ứng dụng.

Runtime cần:

- Hỗ trợ class-file version của tất cả class trong ứng dụng và dependency.
- Cung cấp các API Java SE mà mã nguồn và thư viện sử dụng.
- Có các module, provider, native library, certificate và cấu hình cần thiết.
- Tương thích với framework, driver, agent, instrumentation và các thư viện native.
- Đáp ứng yêu cầu vận hành về TLS, charset, timezone, memory, GC, CPU và hệ điều hành.

Runtime của unit test có thể khác runtime production. Một dự án có thể compile bằng JDK 21, chạy unit test trên Java 17 để kiểm tra mức tương thích tối thiểu, rồi chạy thêm integration test trên Java 21. Nếu sản phẩm chỉ hỗ trợ Java 21, test chính phải chạy trên runtime Java 21 tương ứng với production.

## 3. Quan hệ giữa JDK, Java release và bytecode

Để hiểu vì sao ba JDK có thể khác nhau, cần tách ba khái niệm thường bị gộp chung:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Compiler JDK | JDK cung cấp compiler thực hiện việc biên dịch | JDK 21 |
| Java release/language level | Mức ngôn ngữ và API Java SE được phép dùng khi compile | `--release 17` |
| Class-file target | Định dạng bytecode được tạo ra | Major version 61 cho Java 17 |

Một số class-file major version phổ biến:

| Java release | Class-file major version |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Ví dụ: compiler JDK 21 tạo class file major version 61. JVM Java 17 có thể nạp định dạng này. Nếu compiler tạo class file major version 65, JVM Java 17 sẽ không nạp được và thường ném `UnsupportedClassVersionError`.

Tuy nhiên, class-file version phù hợp vẫn chưa đủ để bảo đảm runtime compatibility. Một class có thể mang major version 61 nhưng gọi API chỉ tồn tại trên Java 21, hoặc phụ thuộc vào thư viện bên thứ ba chỉ được biên dịch cho Java 21. Vì vậy, cần kiểm soát cả API Java SE và dependency graph.

### 3.1. Ý nghĩa của `--release`

Tùy chọn `--release` của `javac` đặt đồng thời mức ngôn ngữ, class-file target và tập API Java SE tương ứng với release được chọn. Khi dùng JDK 21 để tạo artifact chạy trên Java 17, cấu hình compiler nên dùng release 17.

Ví dụ:

```bash
javac --release 17 -d build/classes src/main/java/com/example/Main.java
```

Lệnh trên dùng `javac` của JDK đang được gọi, nhưng compile theo hợp đồng Java 17. Có thể xác nhận class file bằng:

```bash
javap -verbose build/classes/com/example/Main.class
```

Tìm dòng `major version: 61` để xác nhận class file Java 17. Nếu dùng `--release 21`, major version sẽ tương ứng Java 21.

`--release` chỉ kiểm soát mã nguồn Java SE được compiler kiểm tra. Nó không hạ bytecode của dependency, không xác nhận framework có hỗ trợ Java 17, không kiểm soát API nội bộ mà thư viện truy cập qua reflection và không bảo đảm hành vi runtime giống nhau.

### 3.2. Khi nào nên compile bằng JDK mới nhưng target cũ?

Mẫu này hữu ích trong giai đoạn chuyển tiếp khi tổ chức muốn chuẩn hóa môi trường build mới nhưng vẫn phải hỗ trợ consumer chạy trên JVM cũ. Ví dụ:

- CI đã chuyển sang JDK 21 vì build tool/plugin cần hoặc vì muốn dùng compiler mới.
- Artifact vẫn phải chạy trên Java 17 trong thời gian hợp đồng hỗ trợ còn hiệu lực.
- Nhóm muốn kiểm tra sớm mã nguồn trên compiler JDK 21 nhưng chưa thể nâng production runtime.
- Các thư viện và framework mục tiêu vẫn có phiên bản hỗ trợ Java 17.

Không nên giữ target cũ chỉ vì thói quen. Nếu framework hoặc dependency mục tiêu đã yêu cầu Java 21, compile target 17 sẽ không tạo ra một sản phẩm thực sự tương thích Java 17.

## 4. Ví dụ với Gradle Java Toolchains

Gradle Java Toolchains cho phép chỉ định JDK dùng cho các task Java mà không buộc JVM chạy Gradle phải có cùng phiên bản. Đây là cách rõ ràng để tách build JVM khỏi compiler/test JVM.

### 4.1. Build bằng JDK 21, tạo artifact Java 17

Ví dụ `build.gradle` dùng Groovy DSL:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

Trong cấu hình này:

- Gradle daemon vẫn chạy bằng JVM được chọn khi khởi chạy Gradle.
- `JavaCompile` dùng compiler JDK 21 do toolchain chọn.
- Compiler tạo class file theo Java 17 và giới hạn API Java SE ở release 17.
- Nếu không cấu hình riêng, các task như test thường dùng launcher theo toolchain mặc định của Java plugin.

Vì vậy, muốn kiểm tra runtime Java 17 một cách rõ ràng, có thể cấu hình test launcher riêng.

### 4.2. Chọn JVM chạy test riêng

Ví dụ compile bằng JDK 21, target Java 17 và chạy test trên JDK 17:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

tasks.withType(Test).configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Mẫu này kiểm tra artifact trên mức runtime thấp nhất đã cam kết. Nếu ứng dụng cần chạy Java 21 trong production, nên có thêm test task dùng Java 21 để kiểm tra hành vi trên runtime triển khai thực tế. Có thể tạo task test riêng hoặc cấu hình task theo ma trận CI.

### 4.3. Chọn launcher cho JavaExec và ứng dụng chạy local

Các task chạy ứng dụng hoặc công cụ Java có thể cần launcher riêng. Ví dụ với task `JavaExec`:

```groovy
tasks.withType(JavaExec).configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Các plugin như Spring Boot có thể cung cấp task chạy riêng dựa trên `JavaExec` hoặc cơ chế tương tự. Cần kiểm tra kiểu task và cách plugin hỗ trợ toolchain ở phiên bản đang dùng; không giả định mọi task bên thứ ba tự động dùng cùng launcher.

### 4.4. Xác định JVM Gradle đang dùng

Các lệnh hữu ích:

```bash
java -version
./gradlew --version
./gradlew -q javaToolchains
```

- `java -version` hiển thị Java được gọi từ `PATH` trong terminal hiện tại.
- `./gradlew --version` hiển thị JVM mà Gradle đang chạy trong phiên lệnh đó, cùng phiên bản Gradle.
- `./gradlew -q javaToolchains` hiển thị các toolchain Gradle phát hiện được.

Nếu IDE có Gradle JVM riêng, kết quả trong terminal và IDE có thể khác nhau. Hãy kiểm tra cấu hình Gradle JVM trong IDE và JVM được CI sử dụng.

## 5. Ví dụ với Maven Toolchains

Maven cũng chạy bên trong một JVM. JVM này được chọn khi Maven Wrapper hoặc lệnh `mvn` khởi chạy. Maven Toolchains cho phép một số plugin sử dụng JDK khác với JVM đang chạy Maven.

### 5.1. Khai báo JDK đã cài trong `toolchains.xml`

Một file `~/.m2/toolchains.xml` có thể khai báo các JDK sẵn có trên máy:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>21</version>
            <vendor>any</vendor>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/jdk-21</jdkHome>
        </configuration>
    </toolchain>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>17</version>
            <vendor>any</vendor>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/jdk-17</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
```

Đường dẫn trong ví dụ phải được thay bằng vị trí JDK thật trên máy hoặc agent. Không đưa đường dẫn cục bộ của một developer vào repository nếu các máy CI/developer khác không có cùng cấu trúc. Cần chuẩn hóa cài đặt JDK hoặc cung cấp cấu hình tương ứng cho từng môi trường.

### 5.2. Chọn toolchain và cấu hình compiler release

Ví dụ cấu hình Maven Toolchains Plugin để chọn JDK 21, đồng thời dùng Maven Compiler Plugin tạo artifact Java 17:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-toolchains-plugin</artifactId>
            <version>3.2.0</version>
            <executions>
                <execution>
                    <goals>
                        <goal>toolchain</goal>
                    </goals>
                </execution>
            </executions>
            <configuration>
                <toolchains>
                    <jdk>
                        <version>21</version>
                        <vendor>any</vendor>
                    </jdk>
                </toolchains>
            </configuration>
        </plugin>

        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>17</release>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Đây là ví dụ cấu hình minh họa; phiên bản plugin phải được xác minh với phiên bản Maven và JDK của dự án. Maven Toolchains chọn JDK cho các plugin có hỗ trợ toolchain. Maven process vẫn chạy trên JVM được chọn lúc khởi động Maven.

### 5.3. Chạy test bằng JDK khác

Maven Surefire/Failsafe có thể sử dụng toolchain được chọn khi phiên bản plugin hỗ trợ. Cần đọc tài liệu plugin cụ thể và kiểm tra log để xác nhận JVM thực sự khởi chạy forked test process. Nếu không cấu hình toolchain cho test, test có thể chạy bằng JVM của Maven hoặc JVM được plugin chọn theo mặc định.

Để kiểm tra Maven JVM:

```bash
mvn -version
```

Output cho biết Java version và Java home Maven đang dùng. Nó không tự chứng minh compiler/test plugin đã sử dụng cùng JDK đó hay toolchain khác.

## 6. Ví dụ ma trận ba JDK

Một dự án có thể tổ chức như sau trong giai đoạn vẫn phải hỗ trợ Java 17:

| Giai đoạn | Phiên bản | Cách xác nhận |
| --- | --- | --- |
| JVM chạy Gradle/Maven | JDK 21 | `./gradlew --version` hoặc `mvn -version` |
| Compiler toolchain | JDK 21 | Gradle `javaToolchains`, Maven toolchain/plugin log |
| Java release của artifact | 17 | `options.release = 17` hoặc Maven Compiler `<release>17</release>` |
| Unit test runtime tối thiểu | JDK 17 | Test launcher/toolchain và log JVM của test process |
| Integration test runtime | JDK 21 | Test container/agent được cấu hình JDK 21 |
| Production runtime | JDK 17 trong giai đoạn chuyển tiếp | Image/deployment config và runtime `java -version` |

Ma trận này chỉ là ví dụ. Nếu mục tiêu sản phẩm là Java 21, thay Java release và production runtime thành 21, sau đó xác nhận tất cả dependency và môi trường đều hỗ trợ. Không được chỉ đổi một ô trong bảng mà bỏ qua các ràng buộc ở những ô còn lại.

### 6.1. Ma trận runtime tối thiểu và runtime mục tiêu

Nếu thư viện được phân phối cho nhiều ứng dụng, có thể cần kiểm tra trên cả runtime thấp nhất được hỗ trợ và runtime khuyến nghị. Ví dụ, thư viện biên dịch bằng JDK 21 với `--release 17` có thể chạy trên Java 17 và Java 21 nếu dependency tương thích. CI nên chạy test trên cả hai JVM để phát hiện khác biệt hành vi.

Với ứng dụng triển khai duy nhất trên Java 21, không nhất thiết phải duy trì test matrix Java 17 nếu sản phẩm đã chính thức bỏ hỗ trợ Java 17. Tuy nhiên, nếu có plugin, công cụ hoặc thư viện dùng trong build cần Java 17, vẫn phải kiểm tra yêu cầu riêng của chúng.

## 7. Các lỗi thường gặp khi ba vai trò không được cấu hình rõ

### 7.1. Build tool không khởi động dù máy đã cài JDK mới

Nguyên nhân có thể là `JAVA_HOME`, `PATH`, Gradle JVM trong IDE hoặc cấu hình CI vẫn trỏ tới JDK cũ. Cũng có thể phiên bản Gradle/Maven hoặc plugin không hỗ trợ JVM đang dùng.

Hướng điều tra:

1. Chạy `java -version` trong đúng terminal/agent.
2. Chạy `./gradlew --version` hoặc `mvn -version` để xem JVM của build tool.
3. Kiểm tra Gradle JVM trong IDE và cấu hình JDK của CI runner.
4. Đối chiếu phiên bản build tool/plugin với ma trận Java compatibility.
5. Chỉ sau khi build tool khởi động ổn định mới điều tra compiler toolchain.

### 7.2. Build tool chạy được nhưng compile task dùng JDK không mong muốn

Nếu không khai báo toolchain, compiler có thể được chọn theo môi trường build hoặc cấu hình mặc định. Khi đó máy developer và CI có thể dùng compiler khác nhau.

Hãy khai báo toolchain rõ ràng, xem log task compile và kiểm tra đường dẫn `javac`/JDK được chọn. Không dùng kết quả `java -version` để suy ra compiler toolchain.

### 7.3. Compile thành công nhưng ứng dụng lỗi trên production

Các nguyên nhân thường gặp:

- Compiler tạo bytecode mới hơn JVM production.
- Artifact dùng API Java SE không có trong runtime cũ.
- Dependency bắc cầu được biên dịch bằng Java cao hơn target của ứng dụng.
- Runtime image thiếu module, certificate hoặc native library.
- Framework/driver có yêu cầu runtime riêng chưa được đáp ứng.

Kiểm tra `major version`, dependency graph, runtime image và JVM thực tế của tiến trình. Chạy artifact đã đóng gói bằng đúng image production là bằng chứng cần thiết; chạy class từ IDE không thay thế được bước này.

### 7.4. Unit test pass nhưng production vẫn lỗi

Test có thể đang chạy trên JDK mới trong khi production dùng JDK cũ, hoặc test dùng cấu hình classpath khác artifact thực tế. Một số khác biệt chỉ xuất hiện với TLS, charset, timezone, native library, container memory hoặc dịch vụ ngoài.

Hãy ghi rõ test JVM và production JVM, chạy integration test trên image tương ứng, và so sánh cấu hình runtime. Nếu sản phẩm hỗ trợ nhiều JVM, kiểm tra tối thiểu từng JVM đã cam kết.

### 7.5. Plugin hoặc annotation processor không tương thích compiler

Build plugin chạy trên build JVM, trong khi annotation processor thường được nạp trong compiler process và có thể phụ thuộc API của `javac`. Một plugin có thể chạy được trên JVM 17 nhưng processor của nó lỗi khi compiler JDK 21 thay đổi API.

Tách log khởi chạy build tool, log compiler và log processor. Xác định chính xác thành phần lỗi trước khi nâng toàn bộ plugin/dependency graph.

## 8. Kiểm tra phiên bản thực tế trong từng môi trường

Không nên chỉ ghi một giá trị “Java version” trong tài liệu dự án. Hãy thu thập thông tin từ từng process.

| Thành phần | Cách kiểm tra | Cần ghi nhận |
| --- | --- | --- |
| Terminal JDK | `java -version`, `where java` (Windows) hoặc `which java` (Unix) | JDK được gọi từ PATH |
| Gradle JVM | `./gradlew --version` | JVM chạy Gradle |
| Gradle toolchain | `./gradlew -q javaToolchains` | JDK được Gradle phát hiện và có thể chọn |
| Maven JVM | `mvn -version` | Java version và Java home của Maven |
| Compiler | Build log, toolchain configuration, `javac -version` từ JDK đã chọn | JDK thực hiện compile |
| Test process | Log JVM, test launcher/toolchain config | JDK chạy unit/integration test |
| Ứng dụng đang chạy | `java -version` trong container/host, process command line, startup log | JVM thực tế của service |
| Artifact | `javap -verbose`, SBOM và dependency report | Class-file version và dependency đóng gói |

`where java`/`which java` chỉ cho biết executable tìm thấy qua PATH. Nếu build tool, IDE hoặc container có cấu hình riêng, cần kiểm tra cấu hình đó trực tiếp.

### 8.1. Ghi phiên bản vào báo cáo khảo sát

Một báo cáo migration nên có bảng tương tự:

```text
Build JVM:          Eclipse Temurin 21.x
Build tool:         Gradle wrapper 8.x
Compiler toolchain: JDK 21.x
Java release:       17
Unit test JVM:      JDK 17.x
Integration JVM:    JDK 21.x
Production runtime: JRE/runtime image 17.x
Artifact target:    Java 17 / class-file major 61
```

Các phiên bản trên chỉ minh họa cách ghi nhận. Khi báo cáo thật, lấy số liệu từ build log, toolchain và image thực tế. Không ghi một phiên bản ước lượng dựa trên cấu hình mong muốn.

## 9. Những nguyên tắc cấu hình trong CI/CD và môi trường phát triển

### 9.1. Chuẩn hóa build JVM

CI nên chọn rõ JDK dùng để khởi chạy Gradle/Maven. Với Gradle, có thể cấu hình `JAVA_HOME` hoặc lựa chọn JDK trong runner; với Maven cũng tương tự. Đảm bảo Gradle daemon không giữ lại JVM cũ sau khi môi trường thay đổi; khi cần, dừng daemon và khởi động lại trong môi trường đã cấu hình đúng.

IDE cần thống nhất Gradle JVM/Maven runner JDK với yêu cầu dự án. Một cấu hình chạy trong terminal nhưng thất bại khi bấm nút Build trong IDE thường xuất phát từ hai JVM khác nhau.

### 9.2. Khai báo compiler toolchain thay vì phụ thuộc máy cá nhân

Gradle nên khai báo `java.toolchain` trong build script. Maven nên dùng Toolchains Plugin và cấu hình JDK cho từng agent. Có thể để CI cài sẵn JDK hoặc cho toolchain resolver tải JDK theo policy của tổ chức.

Không nên hard-code đường dẫn JDK cục bộ trong build script. Đường dẫn `/opt/jdks/jdk-21` hoặc `C:\Program Files\Java\jdk-21` có thể không tồn tại trên máy khác. Hãy dùng cơ chế toolchain và provisioning được chuẩn hóa.

### 9.3. Kiểm soát runtime bằng container image hoặc cấu hình triển khai

Production runtime thường được xác định bởi container image, VM image hoặc cấu hình service. Ghi nhận tag/digest của image, vendor, phiên bản JDK/JRE và các module runtime cần thiết.

Không suy ra runtime production từ JDK của CI. Build agent có thể dùng JDK 21 trong khi Dockerfile vẫn chọn image Java 17. Ngược lại, image production có thể đã nâng Java 21 trong khi test pipeline còn chạy Java 17.

### 9.4. Giữ ma trận phiên bản đồng bộ với chính sách hỗ trợ

Nếu tổ chức hỗ trợ nhiều runtime, định nghĩa rõ phiên bản thấp nhất và phiên bản khuyến nghị. CI cần kiểm tra trên các runtime nằm trong cam kết. Khi bỏ hỗ trợ một phiên bản, cập nhật tài liệu, artifact metadata, container image, pipeline và thông báo cho consumer.

Việc giữ ma trận quá rộng có chi phí: tăng thời gian CI, tăng số cấu hình cần hỗ trợ và làm chậm việc sử dụng API mới. Chỉ duy trì các phiên bản có nhu cầu và thời hạn hỗ trợ rõ ràng.

## 10. Kế hoạch chuyển đổi ba vai trò theo từng giai đoạn

Khi nâng cấp từ Java 17 lên Java 21, không nhất thiết phải đổi cả build JVM, compiler và application runtime trong một commit. Một lộ trình theo giai đoạn có thể như sau:

### Giai đoạn A: Khảo sát và cố định baseline

- Ghi nhận JDK đang chạy Gradle/Maven ở local và CI.
- Ghi nhận compiler thực tế, release target và class-file version.
- Ghi nhận JVM của test và production image.
- Kiểm tra build tool/plugin và dependency support matrix.
- Lưu kết quả build/test baseline để so sánh.

### Giai đoạn B: Nâng build JVM nếu build tool yêu cầu

- Xác minh phiên bản Gradle/Maven hỗ trợ JDK mục tiêu.
- Nâng wrapper/plugin cần thiết theo lộ trình được hỗ trợ.
- Chạy clean build và kiểm tra các plugin, code generator, annotation processor.
- Chưa đổi application runtime nếu chưa sẵn sàng.

### Giai đoạn C: Chọn compiler toolchain và release target

- Khai báo JDK 21 làm compiler toolchain.
- Chọn `--release 17` nếu artifact vẫn phải hỗ trợ Java 17.
- Chạy test trên Java 17 và Java 21 theo ma trận hỗ trợ.
- Kiểm tra dependency bytecode/API và các compiler plugin.

### Giai đoạn D: Nâng application runtime

- Cập nhật image/runtime lên JDK/JRE 21.
- Chạy integration/contract test trên image đích.
- Đo startup, latency, throughput, GC, memory và kết nối ngoài.
- Triển khai canary hoặc theo từng nhóm nếu nền tảng hỗ trợ.
- Xác nhận rollback hoặc roll-forward với thay đổi dữ liệu.

### Giai đoạn E: Đơn giản hóa cấu hình

Khi consumer đã chuyển sang Java 21 và không còn yêu cầu Java 17, nâng `--release` lên 21, loại bỏ test matrix cũ nếu không còn cần, cập nhật tài liệu và xóa các workaround không còn dùng.

Không phải dự án nào cũng cần đủ các giai đoạn trên. Nếu build tool, compiler và runtime đã cùng dùng Java 21, vẫn cần xác minh riêng các cấu hình và bằng chứng thay vì mặc định chúng đồng nhất.

## 11. Checklist kiểm soát trước khi phát hành

Trước khi kết luận migration thành công, hãy xác nhận:

- [ ] Đã xác định JVM chạy Gradle/Maven trong terminal, IDE và CI.
- [ ] Build tool và plugin hỗ trợ JVM dùng để khởi chạy build.
- [ ] Compiler toolchain được khai báo rõ và log xác nhận đúng JDK.
- [ ] `--release` hoặc cấu hình compiler tương đương khớp với runtime thấp nhất cần hỗ trợ.
- [ ] Dependency trực tiếp và bắc cầu không yêu cầu Java cao hơn runtime đã cam kết.
- [ ] Annotation processor, code generator và compiler plugin chạy được với compiler JDK.
- [ ] Unit test chạy trên JVM tối thiểu cần hỗ trợ.
- [ ] Integration test chạy trên runtime/image mục tiêu.
- [ ] Artifact đã đóng gói được kiểm tra class-file version và dependency.
- [ ] Production image/service dùng đúng runtime đã phê duyệt.
- [ ] Monitoring và rollback/roll-forward phù hợp với thay đổi dữ liệu và runtime.
- [ ] Tài liệu developer/CI nêu rõ từng phiên bản và cách xác minh.

Checklist là phương tiện ghi nhận bằng chứng. Một mục chỉ được đánh dấu hoàn thành khi có kết quả kiểm tra tương ứng, không chỉ vì file cấu hình đã được sửa.

## 12. Kết luận

JDK chạy build tool, JDK biên dịch và JDK chạy ứng dụng là ba vai trò riêng biệt. Build JVM quyết định Gradle/Maven và plugin có khởi động được hay không; compiler toolchain quyết định compiler nào tạo bytecode và kiểm tra API; application runtime quyết định artifact có thể nạp và hoạt động trong môi trường triển khai hay không.

Khi migration, hãy ghi nhận và kiểm chứng từng vai trò bằng đúng công cụ: `./gradlew --version` hoặc `mvn -version` cho build JVM, toolchain/log compiler cho JDK biên dịch, và image/process thực tế cho application runtime. Kết hợp với `--release`, dependency analysis và test trên các JVM đã cam kết, nhóm có thể kiểm soát rõ ràng khả năng tương thích thay vì dựa vào một nhãn “Java version” chung cho toàn dự án.

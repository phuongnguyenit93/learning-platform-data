# Kiểm tra artifact không tham chiếu API ngoài baseline Java 21

Khi một ứng dụng công bố Java 21 là phiên bản runtime tối thiểu, artifact phát hành phải chạy được trên Java 21 và không được phụ thuộc vào API chỉ xuất hiện ở JDK mới hơn. Việc đặt bytecode target thành 21 chưa đủ để bảo đảm điều đó: compiler có thể tạo class file tương thích về phiên bản nhưng code vẫn tham chiếu một method hoặc class chỉ có ở JDK mới hơn nếu build không giới hạn API platform.

Cách kiểm soát chính là biên dịch với `--release 21`. Tùy chọn này đồng thời giới hạn cú pháp/ngôn ngữ, API Java SE và JDK được phép dùng, đồng thời tạo class file cho Java 21. Sau đó, CI cần kiểm tra dependency và artifact đã đóng gói, chạy test trên runtime Java 21 thật và rà soát các đường nạp code động hoặc reflection mà compiler không thể kiểm tra.

## 1. Phân biệt build JDK, API baseline và runtime tối thiểu

Ba khái niệm này liên quan nhưng không giống nhau:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Build JDK | JDK chạy Maven/Gradle/compiler trong pipeline | CI dùng JDK 25 để build |
| API baseline | Phiên bản platform API mà source và bytecode được phép tham chiếu | Java 21 |
| Runtime tối thiểu | Phiên bản JVM thấp nhất được hỗ trợ để chạy artifact | Java 21 |

Có thể dùng JDK mới hơn để build artifact chạy trên Java 21, miễn compiler được cấu hình đúng với `--release 21` và các plugin/annotation processor không tạo ra bytecode hoặc tham chiếu không tương thích. Ngược lại, chỉ chạy Maven bằng JDK 21 cũng không tự bảo đảm project đã khai báo đúng baseline nếu build có nhiều compiler task, generated source hoặc dependency được biên dịch riêng.

Hãy ghi rõ baseline ở một nơi dùng chung và áp dụng cho mọi module, source set, test source và generated source. Nếu một module có baseline khác, phải thể hiện ngoại lệ rõ ràng thay vì để cấu hình ngầm kế thừa từ máy developer.

## 2. Dùng javac --release 21 làm cổng kiểm tra chính

Với `javac`, dùng:

```bash
javac --release 21 -d out src/main/java/com/example/App.java
```

`--release 21` yêu cầu compiler:

- Áp dụng quy tắc ngôn ngữ Java 21.
- Chỉ cho phép API Java SE và JDK được công bố cho release 21.
- Tạo class file có target tương ứng Java 21.

Nếu source gọi API chỉ xuất hiện ở JDK 22 trở lên, compiler sẽ báo lỗi thay vì tạo artifact có tham chiếu không thể liên kết trên Java 21.

### Vì sao -source 21 và -target 21 chưa đủ?

Hai option sau kiểm soát ngôn ngữ và phiên bản class file:

```bash
javac -source 21 -target 21 -d out src/main/java/com/example/App.java
```

Khi compiler đang chạy trên JDK mới hơn, cặp option này không tự giới hạn API platform xuống Java 21. Source có thể biên dịch thành class file version 65 nhưng vẫn tham chiếu một API mới hơn; khi chạy trên Java 21, ứng dụng có thể gặp `NoSuchMethodError`, `NoSuchFieldError` hoặc `NoClassDefFoundError`.

Với JDK 9 trở lên, ưu tiên `--release` thay cho chỉ kết hợp `-source` và `-target`. Không truyền đồng thời `--release` với `-source` hoặc `-target` vì `javac` không cho phép kết hợp các option này.

## 3. Cấu hình Maven Compiler Plugin

Với Maven, khai báo release ở project property để main source và test source dùng cùng baseline:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

Có thể cấu hình trực tiếp trong Maven Compiler Plugin nếu muốn thể hiện rõ plugin đang thực thi:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.16.0</version>
            <configuration>
                <release>21</release>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Chọn và pin phiên bản plugin đã được kiểm thử trong tổ chức; không để build phụ thuộc vào version ngầm do parent POM hoặc môi trường cung cấp. Nếu dùng property `maven.compiler.release`, tránh khai báo một giá trị release khác ở execution hoặc profile làm một module biên dịch theo baseline khác ngoài ý muốn.

### Kiểm tra cả main và test source

Maven Compiler Plugin có các goal compile và testCompile. Cấu hình `release` ở plugin áp dụng cho cả hai pha theo cấu hình tương ứng. Điều này quan trọng vì test source, test fixture hoặc mã kiểm thử tích hợp cũng có thể vô tình dùng API mới hơn Java 21; nếu test chỉ chạy trên JDK mới, lỗi sẽ bị che khuất.

Nếu một module có cấu hình riêng cho `maven-compiler-plugin`, hãy kiểm tra mọi execution, profile và compiler argument. Không chỉ tìm property ở root POM rồi kết luận tất cả module con đã tuân thủ.

## 4. Cấu hình Gradle với toolchain và options.release

Gradle có hai cấu hình bổ sung cho nhau:

- Java toolchain chọn JDK compiler/test/Javadoc theo version mong muốn.
- `options.release` yêu cầu compiler tuân thủ API và class-file baseline.

Ví dụ `build.gradle.kts`:

```kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 21
}
```

Ví dụ `build.gradle`:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 21
}
```

Toolchain giúp chọn compiler JDK 21; `options.release` thể hiện rõ API baseline của từng compile task. Nếu tổ chức chủ ý build bằng compiler JDK mới hơn nhưng vẫn nhắm Java 21, có thể chọn toolchain mới hơn và giữ `options.release = 21`. Khi đó, vẫn phải chạy test trên JDK 21 thật.

Không chỉ cấu hình `compileJava`. Với nhiều source set, plugin hoặc custom `JavaCompile` task, dùng `configureEach` để áp dụng release cho mọi task JavaCompile, rồi kiểm tra task graph trong CI. Với Kotlin, Scala hoặc compiler plugin khác, phải cấu hình target/API compatibility tương ứng; `options.release` chỉ kiểm soát các task `JavaCompile`.

### SourceCompatibility và TargetCompatibility

`sourceCompatibility` và `targetCompatibility` vẫn xuất hiện trong nhiều build cũ, nhưng không thay thế đầy đủ `options.release` khi cần chặn API mới hơn baseline. Không dựa vào hai thuộc tính này như cổng kiểm tra API Java 21.

## 5. Kiểm tra class-file version của artifact

Class file của Java 21 có major version `65`. Nếu một class thông thường trong artifact có major version cao hơn 65 và được Java 21 nạp, JVM có thể ném `UnsupportedClassVersionError`.

Có thể kiểm tra một class bằng `javap`:

```bash
javap -verbose -classpath target/classes com.example.App
```

Trong output, tìm:

```text
major version: 65
```

Hoặc xem class trong JAR:

```bash
javap -verbose -classpath target/application.jar com.example.App
```

Kiểm tra major version là bước hữu ích để phát hiện dependency hoặc generated bytecode được biên dịch cho JVM mới hơn. Tuy nhiên, major version 65 chỉ cho biết định dạng bytecode phù hợp với Java 21; nó không chứng minh các method/class được tham chiếu đều tồn tại trong Java 21. Một class version 65 vẫn có thể gọi nhầm API mới hơn nếu được biên dịch mà không giới hạn API.

Do đó, không dùng kiểm tra class-file version thay cho `--release 21` hoặc integration test trên Java 21.

## 6. Kiểm tra dependency đã đóng gói

`--release 21` bảo vệ các source được biên dịch trong project. Nó không biên dịch lại hoặc tự xác nhận mọi dependency JAR lấy từ repository. Một thư viện bên ngoài có thể:

- Được build với class-file version mới hơn 65 và không thể nạp trên Java 21.
- Có class-file version 65 nhưng tham chiếu method/class chỉ có ở JDK mới hơn.
- Dùng reflection, `MethodHandles`, `ServiceLoader`, JNI hoặc tải class động mà compiler của ứng dụng không nhìn thấy.
- Chỉ thực thi code không tương thích ở một nhánh tính năng hiếm được test thông thường bỏ qua.

Vì vậy, CI cần kiểm tra dependency graph, artifact thực tế và hành vi trên runtime Java 21. Xem dependency tree và xác định phiên bản thư viện có cam kết hỗ trợ Java 21; không chỉ dựa vào việc thư viện có thể resolve hoặc compile được.

### Maven: xem dependency tree

```bash
mvn dependency:tree
```

Với dependency có nhiều phiên bản hoặc nhiều đường kéo vào, xác định phiên bản cuối cùng Maven đã chọn. Nếu cần loại trừ hoặc khóa phiên bản, làm điều đó ở dependency management và kiểm thử lại toàn bộ ứng dụng.

### Gradle: xem dependency đã resolve

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Để tìm lý do một dependency được chọn:

```bash
./gradlew dependencyInsight \
  --dependency some-library \
  --configuration runtimeClasspath
```

Đánh giá cả runtime dependency và plugin/agent được nạp trong production. Một thư viện chỉ có trong runtime classpath vẫn có thể đưa API mới hơn vào đường chạy dù source chính đã biên dịch bằng `--release 21`.

## 7. Dùng jdeps đúng phạm vi

`jdeps` phân tích dependency ở cấp class/package/module và có thể phát hiện tham chiếu đến JDK internal APIs. Với artifact Java 21, có thể chạy:

```bash
# Kiểm tra dependency tới JDK internal APIs
jdeps --multi-release 21 --jdk-internals target/application.jar

# Xem dependency module ở chế độ Java 21
jdeps --multi-release 21 --recursive --summary target/application.jar

# Phát hiện dependency class không phân giải được
jdeps --multi-release 21 --missing-deps target/application.jar
```

Nếu artifact cần thư viện ngoài để phân giải dependency, truyền class path tương ứng bằng `--class-path`.

### jdeps không phải API-baseline checker hoàn chỉnh

`jdeps --jdk-internals` tìm việc phụ thuộc JDK internal APIs như package `sun.*` hoặc API nội bộ khác. Nó không trả lời đầy đủ câu hỏi “artifact có gọi method public nào chỉ được thêm sau Java 21 không?”.

Phân tích dependency của `jdeps` chủ yếu cho biết class/package/module mà bytecode tham chiếu. Nó không thay thế kiểm tra đầy đủ mọi method/field reference so với API signature của Java 21; cũng không phát hiện đầy đủ reflection, tên class được tạo từ chuỗi, JNI hoặc code tải động. Vì thế:

- Dùng `--release 21` để chặn source code của project gọi API platform mới hơn.
- Dùng `jdeps` để rà dependency, missing classes và JDK internal APIs.
- Dùng dependency metadata/API compatibility scanner phù hợp nếu cần kiểm tra bytecode của thư viện bên thứ ba ở mức method/field.
- Chạy integration test trên Java 21 để kiểm tra các đường code thực tế.

Không báo cáo `jdeps --jdk-internals` thành công như bằng chứng rằng toàn bộ artifact chỉ dùng API Java 21.

### Khi cần quét bytecode dependency ở mức API signature

Một API-signature checker có thể bổ sung kiểm tra cho class đã biên dịch, đặc biệt khi cần rà soát thư viện bên thứ ba mà source không được biên dịch trong build hiện tại. Ví dụ, Animal Sniffer có goal `build` để tạo signature từ Java runtime và goal `check` để kiểm tra class đã biên dịch.

Với baseline Java 21, signature dùng để kiểm tra phải được tạo từ một JDK 21 đã được phê duyệt và chỉ chứa API platform được phép dùng. Không lấy một signature cũ hơn rồi coi đó là Java 21; cũng không tạo signature từ toàn bộ implementation classpath mà không lọc, vì runtime có thể chứa class nội bộ không thuộc public API contract. Hãy lưu signature như một build input có version, checksum và quy trình cập nhật riêng.

Animal Sniffer mặc định bỏ qua class/method được định nghĩa trong dependency. Nếu muốn quét dependency, phải cấu hình rõ `ignoreDependencies` và đánh giá false positive cũng như phạm vi class thực sự được phân tích. Cần thử scanner bằng một class tham chiếu API chỉ có sau Java 21 để xác nhận gate thật sự từ chối trường hợp đó. Đây là lớp kiểm tra bổ sung; vẫn cần `--release 21`, `jdeps` và runtime test trên JDK 21.

## 8. Lưu ý với multi-release JAR

Multi-release JAR có thể chứa nhiều phiên bản class trong cùng artifact, đặt dưới `META-INF/versions/<N>/`. JVM chọn phiên bản class phù hợp với runtime. Vì vậy, khi kiểm tra một multi-release JAR cho Java 21, cần phân tích đúng góc nhìn Java 21.

```bash
jdeps --multi-release 21 --recursive --summary target/library.jar
```

Các class trong phần base và versioned entry có thể có major version khác nhau. Một entry dành riêng cho Java 22 trở lên không được JVM 21 chọn, nên không thể chỉ quét toàn bộ JAR rồi coi mọi class version cao là lỗi. Ngược lại, base entry và entry có version không lớn hơn 21 phải tương thích với Java 21.

Nếu chính project tạo multi-release JAR, cần:

1. Biên dịch base classes bằng `--release 8`, `--release 17` hoặc baseline thấp nhất mà artifact công bố hỗ trợ, tùy thiết kế thư viện.
2. Biên dịch phần `META-INF/versions/21` bằng `--release 21`.
3. Đặt manifest `Multi-Release: true`.
4. Kiểm tra nội dung JAR và chạy test trên từng runtime được hỗ trợ.

Với artifact chỉ hỗ trợ Java 21, không cần tạo multi-release JAR nếu không có lý do tương thích cụ thể. Một JAR thường với base classes được compile `--release 21` dễ kiểm tra và triển khai hơn.

## 9. Chạy test và smoke test trên đúng Java 21 runtime

Compiler kiểm tra source; test trên Java 21 kiểm tra artifact trong môi trường mà khách hàng sẽ chạy. CI nên có ít nhất một job dùng JDK 21 để chạy test, không chỉ build bằng JDK mới nhất.

Ví dụ các lệnh Maven:

```bash
java -version
mvn -B clean verify
java -jar target/application.jar --version
```

Với Gradle:

```bash
java -version
./gradlew clean check
java -jar build/libs/application.jar --version
```

Lệnh `--version` chỉ là smoke test minh họa nếu ứng dụng hỗ trợ option đó. Thay bằng lệnh khởi động/health check phù hợp với ứng dụng thực tế.

Nếu build JDK khác JDK runtime test, ghi lại cả hai version trong CI log. Đảm bảo test task thực sự chạy bằng Java 21 toolchain hoặc Java 21 runtime, không vô tình chạy bằng JVM khởi động Gradle/Maven daemon.

Test cần bao phủ các đường chạy dùng thư viện ngoài, serializer, driver, plugin, agent, reflection và service provider. Lỗi API mới hơn baseline thường chỉ xuất hiện khi class hoặc method đó được nạp/thực thi; test khởi động đơn giản không thể bao phủ mọi nhánh.

## 10. Thiết kế pipeline CI làm fail khi vi phạm baseline

Một pipeline cơ bản có thể tổ chức theo thứ tự:

```text
Checkout source
      |
Resolve pinned build tools and dependencies
      |
Compile all Java source with --release 21
      |
Run unit tests
      |
Package JAR / distribution
      |
Inspect class-file versions and JAR contents
      |
Run jdeps checks (missing deps and JDK internals)
      |
Run tests and smoke checks on Java 21 runtime
      |
Publish artifact only if every required gate passes
```

Các cổng nên có kết quả rõ ràng:

| Gate | Điều kiện PASS | Khi FAIL |
|---|---|---|
| Compile baseline | Mọi JavaCompile dùng release 21 | Sửa source hoặc cấu hình compiler task |
| Dependency review | Dependency có runtime support phù hợp; không có class file vượt runtime | Nâng/đổi dependency hoặc loại bỏ module không tương thích |
| Artifact inspection | Base class và entry được Java 21 chọn có bytecode phù hợp | Sửa target hoặc đóng gói multi-release JAR đúng cấu trúc |
| jdeps | Không có missing dependency hoặc JDK internal API không được chấp nhận | Thay API nội bộ, bổ sung dependency hoặc xử lý module path |
| Java 21 test | Unit/integration/smoke test chạy trên đúng JDK 21 | Sửa lỗi runtime hoặc điều chỉnh dependency |
| Publish gate | Tất cả gate bắt buộc đều thành công | Không publish artifact |

Không biến cảnh báo thành PASS nếu chính sách yêu cầu fail. Nếu phải chấp nhận một dependency đặc biệt, ghi exception với owner, phạm vi, lý do và ngày xem xét lại.

## 11. Các giới hạn mà compile-time check không thể giải quyết

Ngay cả khi toàn bộ source dùng `--release 21`, artifact vẫn có thể gặp vấn đề ngoài API compile-time:

- Reflection truy cập class hoặc method bằng tên chuỗi.
- JNI/native library phụ thuộc OS, kiến trúc hoặc ABI.
- Java agent hoặc plugin được nạp sau khi ứng dụng khởi động.
- Service provider hoặc implementation được tìm thấy lúc runtime.
- Dependency được tải từ plugin directory hoặc class loader tùy chỉnh.
- API phụ thuộc behavior/bug của vendor JDK thay vì API contract.
- Tính năng preview hoặc flag JVM không được bật trên runtime đích.

Đối với reflection, ghi rõ class/member được phép dùng và kiểm thử trên JDK 21. Đối với JNI, build native binary theo OS/architecture đích và chạy test trên image tương ứng. Đối với agent/plugin, kiểm tra manifest, class-file version, API dependency và chính sách nạp trên JVM đích.

`--release 21` cũng không có nghĩa mọi thư viện bên thứ ba được bảo đảm hỗ trợ Java 21. Nó chỉ kiểm soát compilation của source trong phạm vi compiler task nhận option đó. Phải kiểm tra dependency support matrix và runtime behavior riêng.

## 12. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ đặt `source` và `target` là 21 | Source vẫn có thể tham chiếu API mới hơn nếu compiler chạy trên JDK mới | Dùng `--release 21` |
| Chỉ kiểm tra class major version 65 | Bytecode có thể gọi method chỉ có trên JDK mới hơn | Kết hợp release compile, dependency review và test trên Java 21 |
| Chỉ chạy test trên JDK build mới | API mới có thể tồn tại trong test JVM nhưng không có ở runtime 21 | Có job test riêng trên JDK 21 |
| Cho rằng `jdeps --jdk-internals` kiểm tra toàn bộ API baseline | Không phát hiện đầy đủ public method/field được thêm sau Java 21 | Dùng đúng công cụ cho từng loại kiểm tra |
| Bỏ qua runtime dependency | Dependency có thể được build với bytecode/API mới hơn | Kiểm tra dependency graph và chạy integration test |
| Không cấu hình generated source/custom compile task | Một số class được biên dịch với release khác | Áp dụng cấu hình cho mọi compiler task và kiểm tra task graph |
| Quét multi-release JAR mà không chọn runtime view | Đánh dấu nhầm class dành cho runtime mới hơn | Dùng `jdeps --multi-release 21` và kiểm tra entry được Java 21 chọn |
| Chỉ chạy smoke test khởi động | Nhánh code hiếm có thể vẫn gọi API mới hơn | Bao phủ tính năng, serializer, plugin và integration path |

## 13. Checklist cho artifact Java 21

1. Khai báo Java 21 là runtime baseline trong tài liệu và build configuration.
2. Cấu hình `javac --release 21` qua Maven Compiler Plugin hoặc mọi Gradle `JavaCompile` task.
3. Không dựa riêng vào `sourceCompatibility`/`targetCompatibility` hoặc `-source`/`-target`.
4. Kiểm tra test source, generated source và custom compiler task cũng dùng release 21.
5. Xem dependency graph và xác minh phiên bản thư viện hỗ trợ runtime Java 21.
6. Kiểm tra class-file version; hiểu major version 65 là cần thiết nhưng chưa đủ.
7. Với multi-release JAR, phân tích đúng view Java 21.
8. Chạy `jdeps --multi-release 21 --missing-deps` và `--jdk-internals` theo chính sách dự án.
9. Không coi jdeps là API method-level baseline checker hoàn chỉnh.
10. Chạy unit, integration và smoke test bằng đúng Java 21 runtime.
11. Kiểm tra reflection, JNI, agent, plugin, ServiceLoader và code tải động.
12. Chỉ publish artifact khi mọi gate bắt buộc đều PASS; lưu JDK version, dependency tree và kết quả kiểm tra cùng build.

## Tài liệu tham khảo chính thức

- [Oracle Java SE 21 — The javac Command (`--release`)](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
- [Oracle Java SE 21 — The jdeps Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html)
- [Oracle Java SE 21 — The javap Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html)
- [Oracle Java SE 21 Migration Guide — Run jdeps on Your Code](https://docs.oracle.com/en/java/javase/21/migrate/preparing-migration.html)
- [Apache Maven Compiler Plugin — Setting the `--release` of the Java Compiler](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html)
- [Apache Maven — Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains)
- [MojoHaus Animal Sniffer — Generating signatures of the Java Runtime](https://www.mojohaus.org/animal-sniffer/animal-sniffer-maven-plugin/examples/generating-java-signatures.html)
- [MojoHaus Animal Sniffer — Checking a project against API signatures](https://www.mojohaus.org/animal-sniffer/animal-sniffer-maven-plugin/examples/checking-signatures.html)
- [Gradle — Building Java Projects and Targeting a Specific Java Version](https://docs.gradle.org/current/userguide/building_java_projects.html)
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html)

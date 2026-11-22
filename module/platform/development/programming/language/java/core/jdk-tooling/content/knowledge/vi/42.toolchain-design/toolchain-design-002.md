# Chọn tool phù hợp khi thiết kế Java toolchain

Trong chủ đề **Thiết kế toolchain**, chọn tool là chọn đúng công cụ cho đúng công việc và đầu ra cần tạo. Không phải mọi việc đều cần một công cụ mới: `javac` biên dịch source, `java` chạy chương trình, Maven hoặc Gradle điều phối build, IDE hỗ trợ phát triển, còn các công cụ chẩn đoán chỉ được thêm khi có câu hỏi cụ thể cần trả lời.

Bài học này giúp chọn đúng công cụ trong JDK và hệ sinh thái Java, phân biệt công cụ có chức năng gần nhau, ghép chúng thành một workflow dễ lặp lại và tránh cài quá nhiều công cụ chồng chéo.

Các lệnh được đối chiếu với trợ giúp tích hợp của Zulu/OpenJDK 24.0.2 trên Windows 11. Ví dụ Java dùng cú pháp và API tương thích Java 17+. Pipeline mẫu đã được chạy để kiểm tra compile, run, JAR, Javadoc, bytecode, dependency analysis, JShell, custom runtime image, application image, signing và JVM diagnostics.

## 1. Bắt đầu từ câu hỏi, không bắt đầu từ danh sách công cụ

Trước khi chọn tool, hãy xác định rõ đầu ra mong muốn:

- Cần biến source thành `.class` hay JAR?
- Cần chạy chương trình, thử một biểu thức hay debug một process?
- Cần dependency graph, API documentation hay module dependency?
- Cần đóng gói ứng dụng cho developer khác, hay tạo installer cho end user?
- Cần kiểm tra certificate, chữ ký, bytecode hay hiệu năng?
- Cần build tái lập trên máy local, CI hay nhiều hệ điều hành?

Mỗi đầu ra có một nhóm công cụ phù hợp. Chọn công cụ theo công việc giúp lệnh ngắn hơn, log dễ hiểu hơn và kết quả dễ xác minh hơn.

Ví dụ, nếu chỉ muốn xem bytecode của một class thì `javap` phù hợp. Nếu muốn xem thư viện phụ thuộc vào module nào thì `jdeps` phù hợp. Nếu muốn tạo installer cho end user thì `jpackage` phù hợp; `jar` chỉ tạo archive.

## 2. Bản đồ chọn tool theo công việc

| Công việc | Công cụ phù hợp | Kết quả chính |
|---|---|---|
| Compile Java source | `javac` | `.class` |
| Chạy class/JAR/module | `java` | Process Java |
| Thử code nhanh | `jshell` | Kết quả tương tác |
| Đóng gói hoặc xem JAR | `jar` | JAR archive |
| Sinh API documentation | `javadoc` | HTML documentation |
| Xem bytecode/API class | `javap` | Class signature/disassembly |
| Phân tích dependency/module | `jdeps` | Dependency report |
| Tìm API deprecated | `jdeprscan` | Deprecated API report |
| Tạo runtime image tùy chỉnh | `jlink` | Java runtime image |
| Đóng gói ứng dụng desktop/server | `jpackage` | Application image/installer |
| Quản lý keystore/certificate | `keytool` | Keystore/certificate |
| Ký và xác minh JAR | `jarsigner` | Signed JAR/verification result |
| Chẩn đoán JVM đang chạy | `jcmd` | Thread, heap, flags, JFR và nhiều báo cáo |
| Phân tích recording | `jfr` | Flight Recorder report |
| Kiểm tra thread/heap/GC | `jstack`, `jmap`, `jstat` | Thread dump, heap, GC statistics |
| Liệt kê Java process | `jps` | PID và thông tin process |
| Monitor bằng GUI | `jconsole` | JVM monitoring |
| Serve file tĩnh để thử nghiệm | `jwebserver` | HTTP server cục bộ |
| Quản lý dependency và lifecycle | Maven hoặc Gradle | Build/test/package/publish |
| Viết, refactor, debug | IDE | Source navigation/debugging |
| Kiểm thử tự động | JUnit/TestNG + build tool | Test result |
| Phân tích chất lượng | Checkstyle/PMD/SpotBugs/Error Prone | Static analysis report |

Bảng này là điểm bắt đầu. Một số công việc có thể dùng nhiều công cụ, nhưng nên có một công cụ chính cho mỗi mục tiêu và chỉ thêm công cụ khác khi nó cung cấp thông tin bổ sung.

## 3. Phân biệt JDK tool, build tool, IDE và tool quản lý môi trường

Bốn nhóm này thường bị gọi chung là “Java tools”, nhưng chúng giải quyết các vấn đề khác nhau:

| Nhóm | Ví dụ | Trách nhiệm |
|---|---|---|
| JDK tools | `javac`, `java`, `jar`, `javadoc`, `jcmd` | Compile, run, package, inspect và diagnose |
| Build tools | Maven, Gradle | Dependency, lifecycle, task graph, test, package và publish |
| IDE | IntelliJ IDEA, Eclipse, VS Code | Edit, navigate, refactor, debug và tích hợp build |
| JDK/environment managers | SDKMAN!, mise, asdf, jabba, package manager của OS | Cài đặt/chuyển JDK và quản lý môi trường developer |

Ví dụ, `javac` có thể compile một file Java độc lập nhưng không thay Maven/Gradle quản lý dependency, resources, test lifecycle, plugin và publication cho một project lớn. IDE có thể gọi Maven/Gradle, nhưng build script vẫn là cấu hình chia sẻ được cho CI và các developer khác.

## 4. `javac` và `java`: compile rồi chạy

Dùng `javac` khi cần compile source trực tiếp hoặc kiểm tra chính xác compiler options:

~~~text
javac --release 17 -encoding UTF-8 -Xlint:all -Werror -d out src/com/example/Main.java
~~~

- `--release 17` giới hạn language rules, API và class-file target ở Java 17.
- `-encoding UTF-8` cố định encoding source.
- `-Xlint:all` bật các cảnh báo compiler phổ biến.
- `-Werror` biến warning thành lỗi.
- `-d out` chọn thư mục output.

Dùng `java` để chạy class, JAR, module hoặc source-file mode:

~~~text
java -cp out com.example.Main
java -jar app.jar
java --module-path mods -m com.example.app/com.example.app.Main
java Main.java
~~~

Source-file mode phù hợp cho ví dụ nhỏ, script hoặc thử nghiệm nhanh trên Java 11+. Với ứng dụng nhiều source file, dependency và test, hãy chuyển sang Maven/Gradle.

Không nhầm compile target với runtime. `javac --release 17` tạo class tương thích Java 17; nó không làm process `java` đang chạy biến thành Java 17. Runtime thực tế do executable `java` được chọn quyết định.

## 5. `jshell`: thử API và ý tưởng nhanh

`jshell` là REPL của Java. Dùng khi cần thử một biểu thức, API, collection, regex, stream hoặc đoạn code nhỏ mà chưa cần tạo project.

Khởi chạy:

~~~text
jshell
~~~

Ví dụ:

~~~java
var names = java.util.List.of("Ada", "Linus", "Grace");
names.stream().map(String::toUpperCase).toList()
~~~

Có thể chạy file script và nạp classpath:

~~~text
jshell --class-path lib/example.jar probe.jsh
~~~

Dùng `jshell` để khám phá API và tạo reproduction ngắn cho bug. Khi logic đã ổn định, chuyển nó thành source code và test tự động trong project. REPL không thay thế unit test, build script hoặc dependency management.

## 6. `jar`: đóng gói và kiểm tra archive

Dùng `jar` khi cần tạo, liệt kê, cập nhật, trích xuất hoặc xem module descriptor trong JAR.

Tạo executable JAR:

~~~text
jar --create --file app.jar --main-class com.example.Main -C out .
~~~

Liệt kê nội dung và xem module:

~~~text
jar --list --file app.jar
jar --describe-module --file app.jar
~~~

Trích xuất manifest để kiểm tra:

~~~text
jar --extract --file app.jar META-INF/MANIFEST.MF
~~~

`jar` tạo archive; nó không giải quyết dependency transitive, không chạy test và không tự tạo installer. Khi project đã dùng Maven/Gradle, hãy để build tool cấu hình JAR task và manifest rồi dùng `jar` để inspect kết quả.

## 7. `javadoc`: tạo tài liệu API

Dùng `javadoc` để tạo HTML documentation từ package, module và source comments.

Ví dụ:

~~~text
javadoc -quiet -Xdoclint:all -Werror -d docs -sourcepath src -subpackages com.example
~~~

- `-d docs` chọn thư mục output.
- `-sourcepath src` chỉ vị trí source.
- `-subpackages` chọn package hierarchy.
- `-Xdoclint:all` kiểm tra cú pháp và nội dung Javadoc.
- `-Werror` làm build thất bại nếu còn warning.

Với Maven/Gradle project, cấu hình Javadoc task/plugin trong build để documentation được tạo tự động cùng release. Chọn `javadoc` khi cần API docs; README hướng dẫn sử dụng và tài liệu kiến trúc thường vẫn cần được viết riêng.

## 8. `javap`, `jdeps` và `jdeprscan`: ba câu hỏi khác nhau

Ba công cụ này thường bị dùng thay thế cho nhau:

**`javap`** trả lời: class đã compile chứa method, field và bytecode nào?

~~~text
javap -classpath app.jar -public com.example.Main
javap -classpath app.jar -c -p com.example.Main
javap -verbose -classpath app.jar com.example.Main
~~~

Dùng `-c` để xem bytecode, `-p` để xem cả member private và `-verbose` để xem class-file details.

**`jdeps`** trả lời: class/JAR phụ thuộc vào package hoặc module nào? Có dùng JDK internal API không?

~~~text
jdeps --summary app.jar
jdeps --print-module-deps app.jar
jdeps --jdk-internals app.jar
~~~

`jdeps --print-module-deps` hữu ích khi chuẩn bị danh sách module cho `jlink`. Phân tích tĩnh có thể bỏ sót dependency được nạp động qua reflection, service loader, plugin hoặc tên class được tạo từ config; hãy kiểm tra thêm test/runtime.

**`jdeprscan`** trả lời: binary có tham chiếu API đã deprecated trong một Java release không?

~~~text
jdeprscan --release 17 app.jar
~~~

Chọn `javap` để inspect một class, `jdeps` để phân tích dependency, và `jdeprscan` để rà deprecated API. Không dùng một báo cáo thay cho báo cáo còn lại.

## 9. `jlink` và `jmod`: làm việc với module/runtime image

`jlink` tạo runtime image chỉ chứa các module cần thiết. Nó hữu ích khi muốn phân phối ứng dụng modular cùng một runtime gọn hơn JDK đầy đủ.

Ví dụ:

~~~text
jlink --module-path "%JAVA_HOME%\jmods;mods" --add-modules com.example.app --output runtime
~~~

Với ứng dụng modular, có thể dùng `jdeps --print-module-deps` để tìm module phụ thuộc ban đầu, sau đó kiểm tra service binding, reflection và runtime paths trước khi link.

`jlink` làm việc với module graph. JAR trên classpath hoặc automatic module không thể được link như một named module thông thường; hãy modularize dependency hoặc dùng cách phân phối khác.

`jmod` tạo, liệt kê, extract, describe hoặc hash JMOD archive. JMOD thường xuất hiện trong quy trình xây dựng JDK/runtime và module nâng cao. Phần lớn ứng dụng Java thông thường không cần tự tạo JMOD.

## 10. `jpackage`: đóng gói ứng dụng cho người dùng cuối

Dùng `jpackage` khi cần application image hoặc native installer có launcher và runtime đi kèm.

Ví dụ tạo application image từ một JAR:

~~~text
jpackage --type app-image --name SampleApp --input dist --main-jar app.jar --main-class com.example.Main --dest packages
~~~

`app-image` là thư mục ứng dụng đã đóng gói; nó chưa phải installer. Tùy OS và công cụ native được cài, `jpackage` có thể tạo loại gói như `msi`, `exe`, `deb`, `rpm`, `dmg` hoặc `pkg`.

Chọn `jpackage` cho ứng dụng cần phân phối như desktop/server package. Chọn `jlink` khi mục tiêu chính là runtime image. `jpackage` có thể gọi `jlink` để tạo runtime đi kèm. Với ứng dụng modular, có thể dùng `--module`; với ứng dụng classpath, dùng `--main-jar` và `--main-class`.

Nếu mục tiêu là native executable không cần JVM runtime, đó là hướng khác, ví dụ GraalVM Native Image. Native Image không phải lệnh mặc định của JDK và có yêu cầu compatibility/build riêng.

## 11. `keytool` và `jarsigner`: certificate khác với JAR signature

Dùng `keytool` để tạo và quản lý keystore, key pair, certificate request, certificate và truststore.

Một số lệnh thường gặp:

~~~text
keytool -genkeypair -alias release -keyalg RSA -keysize 3072 -keystore release.p12 -storetype PKCS12
keytool -list -v -keystore release.p12
keytool -printcert -file publisher.cer
keytool -importcert -alias publisher -file publisher.cer -keystore truststore.p12
~~~

Dùng `jarsigner` để ký và xác minh JAR:

~~~text
jarsigner -keystore release.p12 -storetype PKCS12 -signedjar app-signed.jar app.jar release
jarsigner -verify -strict -verbose -certs app-signed.jar
~~~

`keytool` quản lý key/certificate; `jarsigner` ký hoặc xác minh JAR. Certificate self-signed có thể cho phép kiểm tra digest/chữ ký nhưng không tự tạo trust chain cho người dùng. Release cần certificate/key identity, fingerprint, timestamp và trust policy phù hợp.

Không ghi password hoặc private key vào POM, source repository, script đã commit hay log CI. Dùng secret store và cơ chế nhập credential an toàn. Chữ ký JAR cũng khác detached PGP signature do GPG tạo.

## 12. `jcmd`: điểm bắt đầu cho JVM diagnostics

Khi ứng dụng Java đang chạy, `jcmd` gửi diagnostic command tới JVM process. Trước tiên liệt kê process:

~~~text
jcmd -l
~~~

Xem các command mà JVM hỗ trợ:

~~~text
jcmd <pid> help
~~~

Một số ví dụ:

~~~text
jcmd <pid> VM.version
jcmd <pid> VM.flags
jcmd <pid> Thread.print -l
jcmd <pid> GC.heap_info
jcmd <pid> GC.class_histogram
~~~

`jcmd` có nhiều command hơn các công cụ chẩn đoán đơn lẻ và thường là điểm bắt đầu hữu ích. Command khả dụng phụ thuộc JVM/version và quyền attach. Thường cần chạy dưới cùng user với process đích; container, service account và attach-disabled JVM có thể giới hạn khả năng truy cập.

Chẩn đoán process production cần có mục tiêu rõ ràng, chọn command ít tác động trước và ghi lại thời điểm/lệnh đã chạy. Heap dump hoặc histogram có thể làm tăng pause và tiêu thụ nhiều disk/memory.

## 13. Chọn giữa `jstack`, `jmap`, `jstat`, `jps`, `jconsole` và `jhsdb`

| Công cụ | Dùng khi | Ví dụ |
|---|---|---|
| `jps` | Cần tìm Java process và PID | `jps -lv` |
| `jstack` | Cần thread dump độc lập | `jstack -l <pid>` |
| `jmap` | Cần heap histogram hoặc heap dump | `jmap -histo:live <pid>` |
| `jstat` | Cần xem GC/heap statistics theo thời gian | `jstat -gcutil <pid> 1000 5` |
| `jconsole` | Cần GUI xem MBeans, memory, thread và monitoring | `jconsole` |
| `jhsdb` | Cần debug JVM/core dump ở mức serviceability nâng cao | `jhsdb hsdb` |

Với JDK mới, hãy xem các diagnostic command của `jcmd` trước khi chọn một công cụ riêng. Ví dụ `jcmd <pid> Thread.print -l` tạo thread dump; `jcmd <pid> GC.heap_dump filename=heap.hprof` có thể tạo heap dump.

Heap dump có thể chứa token, password, request payload và dữ liệu người dùng trong memory. Lưu ở vị trí được bảo vệ, giới hạn quyền truy cập và xóa theo chính sách retention. Không tạo heap dump chỉ để “xem thử” trên production.

## 14. JFR và `jfr`: ghi nhận hiệu năng có dữ liệu

Java Flight Recorder (JFR) ghi lại event của JVM và ứng dụng như allocation, GC, thread, lock, class loading và một số event hệ thống.

Bắt đầu recording từ process đang chạy:

~~~text
jcmd <pid> JFR.start duration=60s filename=app.jfr
~~~

Xem summary và event:

~~~text
jfr summary app.jfr
jfr print --events jdk.GarbageCollection,jdk.ExecutionSample app.jfr
~~~

JFR hữu ích khi cần hiểu một khoảng thời gian có CPU cao, GC bất thường hoặc lock contention. Dùng cấu hình recording phù hợp với câu hỏi và đánh giá overhead theo workload. Java Mission Control (JMC) cung cấp giao diện phân tích recording; JMC có thể cần cài riêng tùy JDK distribution.

Chọn JFR cho profiling/recording theo thời gian. Chọn thread dump khi cần snapshot trạng thái thread tại một thời điểm. Hai kết quả bổ sung nhau.

## 15. `jwebserver`: server tĩnh cho local development

`jwebserver` là HTTP server đơn giản đi kèm JDK để phục vụ file tĩnh trong quá trình phát triển hoặc thử nghiệm.

Ví dụ:

~~~text
jwebserver --bind-address 127.0.0.1 --port 8000 --directory public
~~~

Mở `http://127.0.0.1:8000/` để kiểm tra file trong thư mục `public`. Server mặc định bind loopback; có thể đổi bind address khi thực sự cần.

Đây là tiện ích thử nghiệm nhanh, không phải web server production. Với API, authentication, TLS, routing hoặc workload thực tế, chọn framework/server phù hợp với yêu cầu ứng dụng.

## 16. Maven hay Gradle?

Maven và Gradle đều quản lý dependency, build lifecycle, compiler, test, JAR, publication và plugin. Hãy chọn một build system chính cho mỗi project, trừ khi có lý do tích hợp đặc biệt.

| Tiêu chí | Maven | Gradle |
|---|---|---|
| Cấu hình | POM XML theo convention | Groovy DSL hoặc Kotlin DSL |
| Lifecycle | Lifecycle phases chuẩn | Task graph linh hoạt |
| Dependency | POM, BOM, scopes | Configurations, variants, rich metadata |
| Build logic | Plugin và lifecycle convention | Task/plugin model có thể tùy biến sâu |
| Wrapper | Maven Wrapper | Gradle Wrapper |
| Phù hợp | Project convention rõ, Maven ecosystem | Build tùy biến, multi-project và variant-aware |

Dùng Maven khi project đã theo convention Maven, muốn lifecycle quen thuộc và POM tương thích hệ sinh thái rộng. Dùng Gradle khi cần task graph linh hoạt, build logic phức tạp hoặc variant model. Cả hai đều có thể build Java tốt; quyết định dựa trên nhu cầu project, kỹ năng nhóm và plugin cần dùng.

Không chọn Gradle chỉ vì build script ngắn hơn, cũng không chọn Maven chỉ vì XML quen thuộc. Hãy thử một vertical slice gồm compile, test, package, dependency và publish để đánh giá.

## 17. Wrapper và toolchain là một phần của lựa chọn build tool

Commit wrapper để mọi người dùng cùng phiên bản build tool:

~~~text
./mvnw -version
./gradlew --version
~~~

Wrapper pin Maven/Gradle distribution; nó không tự pin JDK. Để chọn JDK cho compiler/test, dùng Maven Toolchains hoặc Gradle Java Toolchains. Để chọn JVM chạy Maven/Gradle, cấu hình `JAVA_HOME`, IDE runner hoặc daemon JVM criteria phù hợp.

Một project nên ghi rõ target Java bằng `--release` hoặc cấu hình tương đương. Không dựa vào JDK mặc định trên máy developer.

## 18. Chọn test framework và test runner

JDK cung cấp compiler/runtime, nhưng không đi kèm một unit-test framework phổ biến như JUnit.

Các lựa chọn thường gặp:

- **JUnit Jupiter:** lựa chọn mặc định phổ biến cho unit test Java hiện đại.
- **TestNG:** phù hợp với nhóm đã có suite hoặc cần các tính năng TestNG cụ thể.
- **Mockito:** hỗ trợ mock/stub collaborator; đây không phải test runner.
- **Testcontainers:** chạy dependency/service thật trong container cho integration test.

Maven Surefire thường chạy unit test ở phase `test`; Maven Failsafe thường điều phối integration test ở các phase `integration-test` và `verify`. Gradle Java Plugin cung cấp task `test`; task `check` có thể gom các verification tasks, còn `build` thường kết hợp `check` và `assemble`. Có thể tạo task riêng cho integration test.

Chọn framework theo test style, hệ sinh thái, extension và khả năng tích hợp. Đừng thêm nhiều test framework vào cùng project nếu không có migration hoặc compatibility reason.

## 19. Chọn static analysis và formatter theo mục tiêu

Một số công cụ kiểm tra các lớp vấn đề khác nhau:

| Mục tiêu | Công cụ ví dụ |
|---|---|
| Compiler warnings | `javac -Xlint:all` |
| Code style/rules | Checkstyle |
| Source-level rule analysis | PMD |
| Bytecode bug patterns | SpotBugs |
| Compiler-time bug checks | Error Prone |
| Formatting | google-java-format hoặc Spotless |
| Quality dashboard/gate | SonarQube |

Không cần bật mọi công cụ cùng lúc. Chọn một formatter làm chuẩn, một bộ rule style, và analyzer có khả năng phát hiện lỗi mà compiler/tests chưa bao phủ. Pin version và cấu hình rule trong build để local/CI có kết quả nhất quán.

`javac -Werror` hữu ích khi nhóm đã kiểm soát warnings; bật nó trên legacy project có thể làm build thất bại vì warning cũ. Triển khai theo từng bước và xử lý warning có chủ đích.

## 20. Chọn IDE theo cách làm việc của nhóm

IDE giúp đọc và thay đổi code nhanh hơn, nhưng không nên trở thành nơi duy nhất lưu cấu hình build.

- IntelliJ IDEA: Java navigation, refactoring, debugging và tích hợp Maven/Gradle.
- Eclipse: Java tooling, workspace và plugin ecosystem lâu đời.
- Visual Studio Code với Extension Pack for Java: editor nhẹ hơn, hỗ trợ Java language server, debug và project integration.

Khi chọn IDE, thử mở project bằng wrapper, import dependency, chạy test, debug và xem Javadoc. Kiểm tra Project SDK, Maven Runner JRE, Gradle JVM và build delegation. Build trên terminal/CI phải cho kết quả tương đương với build được IDE ủy quyền.

Không commit các file chứa đường dẫn SDK tuyệt đối của một máy developer nếu chúng không thuộc project policy.

## 21. Chọn JDK manager và cách cài JDK

JDK manager hữu ích khi phải chuyển giữa nhiều Java release/vendor:

- SDKMAN! thường dùng trên Linux/macOS và shell tương thích.
- mise hoặc asdf quản lý nhiều runtime/tool version.
- jabba cung cấp workflow quản lý JDK đa nền tảng.
- Package manager của OS như winget, Homebrew hoặc Scoop có thể cài JDK.

Chọn một cơ chế cài/chuyển JDK chính cho từng máy để tránh nhiều manager cùng sửa PATH. Ghi yêu cầu JDK trong project bằng toolchain configuration và CI; file manager version của workstation là tiện ích môi trường, không thay project build contract.

Nếu tổ chức yêu cầu vendor, patch level hoặc license cụ thể, chọn distribution được phê duyệt và ghi rõ policy đó.

## 22. Chọn công cụ trong CI và container

CI cần tái lập môi trường và hiển thị bằng chứng JDK đang dùng. Ví dụ GitHub Actions:

~~~yaml
steps:
  - uses: actions/checkout@v4

  - uses: actions/setup-java@v4
    with:
      distribution: temurin
      java-version: '17'
      cache: maven

  - name: Show toolchain
    run: |
      java -version
      javac -version
      ./mvnw -version

  - name: Verify
    run: ./mvnw -B -ntp clean verify
~~~

Với Gradle, dùng `./gradlew --no-daemon clean check` và khai báo Java toolchain trong build. Với nhiều runtime được hỗ trợ, dùng CI matrix để chạy test trên từng version.

Trong Docker, chọn base image có JDK/JRE đúng với vai trò. Build stage thường cần JDK và build tool; runtime stage có thể dùng JRE hoặc custom image tạo từ `jlink`. Đường dẫn và process trong container tuân theo OS của image, không tự động theo host.

Khi cần build tái lập nghiêm ngặt, pin image digest, JDK distribution/patch, wrapper, plugin và dependency versions.

## 23. Workflow mẫu: từ source đến runtime image

Giả sử project nhỏ có source ở `src/com/example/tools/HelloToolchain.java` và main class là `com.example.tools.HelloToolchain`.

Compile Java 17:

~~~text
javac --release 17 -encoding UTF-8 -Xlint:all -Werror -d classes src/com/example/tools/HelloToolchain.java
~~~

Tạo JAR và chạy:

~~~text
jar --create --file dist/hello-toolchain.jar --main-class com.example.tools.HelloToolchain -C classes .
java -jar dist/hello-toolchain.jar
~~~

Stdout của ví dụ:

~~~text
JAVA_TOOLCHAIN_OK
~~~

Tạo Javadoc, inspect bytecode và dependency:

~~~text
javadoc -quiet -Xdoclint:all -Werror -d docs -sourcepath src -subpackages com.example.tools
javap -classpath dist/hello-toolchain.jar -c com.example.tools.HelloToolchain
jdeps --print-module-deps dist/hello-toolchain.jar
~~~

Với sample chỉ dùng Java base module, `jdeps` trả:

~~~text
java.base
~~~

Thử API trong JShell:

~~~text
jshell --class-path dist/hello-toolchain.jar --feedback concise probe.jsh
~~~

Tạo runtime image tối thiểu cho sample:

~~~text
jlink --add-modules java.base --output runtime-image --strip-debug --no-header-files --no-man-pages
~~~

Chạy bằng runtime image:

~~~text
runtime-image/bin/java -jar dist/hello-toolchain.jar
~~~

Stdout vẫn là `JAVA_TOOLCHAIN_OK`. Với ứng dụng thật, module list phải được lấy từ dependency analysis rồi kiểm tra dynamic loading/service binding trước khi phát hành.

## 24. Workflow mẫu: đóng gói và chẩn đoán

Tạo application image trên Windows:

~~~powershell
jpackage --type app-image --name HelloToolchain --input dist --main-jar hello-toolchain.jar --main-class com.example.tools.HelloToolchain --dest packages --app-version 1.0.0
~~~

Lệnh này tạo application image có launcher và runtime. Loại installer cuối cùng phụ thuộc OS và native packaging tools.

Tìm JVM process và xem trạng thái:

~~~text
jcmd -l
jcmd <pid> VM.version
jcmd <pid> Thread.print -l
~~~

Ghi JFR recording trong 60 giây và đọc summary:

~~~text
jcmd <pid> JFR.start duration=60s filename=app.jfr
jfr summary app.jfr
~~~

Nếu cần certificate và JAR signature, dùng `keytool` để chuẩn bị key/certificate và `jarsigner` để ký/xác minh. Tách bước signing khỏi compile/package để artifact chỉ được ký sau khi nội dung đã hoàn tất.

## 25. Chọn tool theo tình huống thực tế

| Tình huống | Bắt đầu bằng | Bổ sung khi cần |
|---|---|---|
| Học Java, thử API | `jshell` | IDE hoặc project nhỏ |
| Compile một ví dụ độc lập | `javac` + `java` | `jar` nếu cần archive |
| Phát triển ứng dụng nhiều module | Maven/Gradle + IDE | JUnit, static analysis |
| Phát hành Java library | Maven/Gradle | Sources/Javadoc, signing, SBOM |
| Kiểm tra class không rõ nội dung | `jar --list`, `javap` | `jdeps`, `jdeprscan` |
| Giảm runtime phân phối | `jdeps` + `jlink` | Runtime test trên từng OS |
| Tạo desktop installer | `jpackage` | Native packager theo OS |
| Lỗi treo hoặc deadlock | `jcmd Thread.print` | Thread dump nhiều thời điểm, JFR |
| CPU/GC bất thường | JFR | JMC, `jstat`, application metrics |
| Memory tăng bất thường | `jcmd GC.heap_info` | Histogram/heap dump, heap analyzer |
| TLS/certificate lỗi | `keytool` | Truststore inspection, TLS debug |
| JAR signature lỗi | `jarsigner -verify` | Certificate chain/fingerprint validation |
| Thử phục vụ file tĩnh | `jwebserver` | Web server/framework cho môi trường thật |

Bắt đầu với công cụ ít xâm lấn nhất có thể trả lời câu hỏi. Chỉ tạo heap dump, profiler recording dài hoặc thay đổi runtime image khi có mục tiêu và nơi lưu kết quả phù hợp.

## 26. Những lựa chọn sai thường gặp

### Dùng `jar` thay Maven/Gradle

`jar` không resolve dependency, compile source set, chạy test hoặc publish component metadata. Dùng nó cho archive đơn giản hoặc inspection; dùng build tool cho project có lifecycle.

### Dùng `javap` để tìm dependency

`javap` inspect một class. Dùng `jdeps` để xem package/module dependency và `jdeprscan` để tìm deprecated API.

### Dùng `jlink` để tạo installer

`jlink` tạo runtime image. Dùng `jpackage` để tạo application image/installer.

### Dùng `jpackage` để tạo native executable độc lập JVM

`jpackage` đóng gói ứng dụng cùng runtime image hoặc runtime có sẵn. Native executable là bài toán riêng, ví dụ GraalVM Native Image.

### Dùng JFR khi chỉ cần một thread dump

JFR ghi event trong một khoảng thời gian. Dùng `jcmd <pid> Thread.print -l` khi cần snapshot thread tại một thời điểm.

### Dùng heap dump trước khi xác định memory problem

Heap dump có thể lớn, chứa dữ liệu nhạy cảm và gây pause. Trước tiên xem metrics, `GC.heap_info`, histogram hoặc JFR; chỉ dump khi có câu hỏi cụ thể và đủ dung lượng lưu trữ.

### Dùng IDE settings thay build configuration

IDE setting chỉ phản ánh workstation. Đưa JDK, compiler release, dependency và test config vào Maven/Gradle/CI.

### Thêm nhiều formatter/analyzer trùng nhau

Các tool trùng rule có thể tạo warning lặp, cấu hình khó bảo trì và kết quả không nhất quán. Chọn tool theo khả năng bổ sung rõ ràng.

### Dùng JDK manager thay Maven/Gradle toolchain

JDK manager chọn JDK trên máy; Maven/Gradle toolchain chọn compiler/test launcher của project. Hai lớp cần được cấu hình đúng vai trò.

## 27. Tiêu chí đánh giá một công cụ trước khi đưa vào toolchain

Trước khi thêm tool, hãy trả lời:

1. **Mục tiêu:** công cụ giải quyết vấn đề cụ thể nào?
2. **Output:** tạo ra file, report, package hay thay đổi process nào?
3. **Compatibility:** hỗ trợ JDK, OS, architecture và build tool nào?
4. **Automation:** chạy được trong CI và không cần thao tác GUI không?
5. **Reproducibility:** có pin version, config và input được không?
6. **Security:** cần quyền gì, đọc dữ liệu gì, lưu secret ở đâu?
7. **Maintenance:** ai nâng version, xử lý warning và plugin conflict?
8. **Overlap:** công cụ có trùng chức năng với thứ project đang có không?
9. **Cost:** thời gian build, RAM, disk, license và chi phí vận hành?
10. **Team fit:** nhóm có thể debug và duy trì nó không?

Một công cụ chỉ nên được thêm khi lợi ích thực tế lớn hơn chi phí cài đặt, cấu hình, nâng cấp và hỗ trợ.

## 28. Checklist thiết kế Java toolchain

- [ ] Đã xác định source, artifact, runtime và môi trường phân phối.
- [ ] Dùng JDK tools đúng nhiệm vụ: compile, run, package, inspect, docs hoặc diagnostics.
- [ ] Dùng một build tool chính và commit wrapper.
- [ ] Pin Java toolchain và target release.
- [ ] IDE dùng cùng project build configuration với CLI/CI.
- [ ] Có test framework và test runner phù hợp.
- [ ] Chọn formatter/static analyzer theo mục tiêu, tránh rule trùng.
- [ ] Có cách inspect JAR, bytecode và dependency khi cần.
- [ ] Dùng `jlink`/`jpackage` đúng loại output.
- [ ] Certificate/private key được bảo vệ; signature được xác minh theo trust policy.
- [ ] JVM diagnostics có mục tiêu, giới hạn tác động và nơi lưu an toàn.
- [ ] CI chạy wrapper và in phiên bản Java/build tool.
- [ ] Runtime/installer được kiểm thử trên từng OS được hỗ trợ.
- [ ] Tool versions và cấu hình được ghi lại để tái lập build.
- [ ] Mỗi công cụ mới có người chịu trách nhiệm bảo trì.

## 29. Tài liệu tham khảo

- Oracle JDK 24 — JDK Tools and Utilities: https://docs.oracle.com/en/java/javase/24/docs/specs/man/index.html
- Oracle JDK 24 — `javac`: https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html
- Oracle JDK 24 — `java`: https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html
- Oracle JDK 24 — `jshell`: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jshell.html
- Oracle JDK 24 — `jar`: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html
- Oracle JDK 24 — `javadoc`: https://docs.oracle.com/en/java/javase/24/docs/specs/man/javadoc.html
- Oracle JDK 24 — `javap`: https://docs.oracle.com/en/java/javase/24/docs/specs/man/javap.html
- Oracle JDK 24 — `jdeps`: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeps.html
- Oracle JDK 24 — `jdeprscan`: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeprscan.html
- Oracle JDK 24 — `jlink` and `jpackage`: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jlink.html and https://docs.oracle.com/en/java/javase/24/docs/specs/man/jpackage.html
- Oracle JDK 24 — `jcmd` and JFR: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html and https://docs.oracle.com/en/java/javase/24/docs/specs/man/jfr.html
- Oracle JDK 24 — `keytool` and `jarsigner`: https://docs.oracle.com/en/java/javase/24/docs/specs/man/keytool.html and https://docs.oracle.com/en/java/javase/24/docs/specs/man/jarsigner.html
- Oracle JDK 24 — `jwebserver`: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jwebserver.html
- Maven — Introduction to the Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Maven — Maven Wrapper: https://maven.apache.org/wrapper/
- Gradle — Java Toolchains: https://docs.gradle.org/current/userguide/toolchains.html
- Gradle — Java Plugin: https://docs.gradle.org/current/userguide/java_plugin.html
- Gradle — Gradle Wrapper: https://docs.gradle.org/current/userguide/gradle_wrapper.html
- JUnit 5 — User Guide: https://junit.org/junit5/docs/current/user-guide/
- GraalVM — Native Image: https://www.graalvm.org/latest/reference-manual/native-image/

Chọn tool phù hợp là chọn đúng lớp công việc: JDK tool cho compile/run/inspect/diagnostics, Maven hoặc Gradle cho lifecycle và dependency, IDE cho phát triển, test/static-analysis tools cho chất lượng, và CI/toolchains cho tính nhất quán. Bắt đầu bằng đầu ra cần có, chọn bộ công cụ nhỏ nhất đáp ứng yêu cầu, rồi xác minh kết quả trên runtime và nền tảng thực tế.
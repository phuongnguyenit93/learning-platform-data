# Khác biệt giữa dependency của công cụ build và đường dẫn thực tế của JVM

## 1. Tình huống: khai báo dependency rồi mà JVM vẫn không tìm thấy lớp

Một ứng dụng Java khai báo thư viện trong Gradle `build.gradle` hoặc Maven `pom.xml`, biên dịch thành công, thậm chí các unit test đều chạy tốt. Nhưng khi lấy file JAR sang máy khác và chạy `java -jar app.jar`, ứng dụng có thể gặp:

~~~text
java.lang.NoClassDefFoundError: com/example/lib/Service
~~~

Điều này không mâu thuẫn. **Dependency do công cụ build quản lý** và **các class/JAR mà JVM có thể tìm lúc chạy** là hai lớp trách nhiệm khác nhau:

- **Build tool** (Gradle, Maven) đọc cấu hình, chọn phiên bản, tải artifacts, giải quyết phụ thuộc bắc cầu, hình thành các tập file cho biên dịch, kiểm thử, chạy task hoặc đóng gói.
- **Java compiler** (`javac`) kiểm tra mã nguồn với **compile classpath** (hoặc module path) được cung cấp.
- **Java launcher và ClassLoader** tìm bytecode khi chương trình chạy dựa trên **runtime classpath/module path, module resolution, manifest, cách đóng gói, launcher và các ClassLoader tùy chỉnh**. JVM không tự đọc `pom.xml`/`build.gradle` để tìm thư viện.
- **Artifact được phát hành** có thể chỉ chứa mã ứng dụng, hoặc đi kèm thư viện, hoặc có boot/shaded loader đặc biệt. Kết quả phụ thuộc task/plugin đóng gói thực tế.

**Mục tiêu bài học:** có khả năng xác định “thư viện có trong graph build” khác “class có thể tìm bởi loader lúc chạy” như thế nào; biết kiểm tra scope/configuration, lệnh launch, nội dung JAR/distribution và phiên bản thực tế; từ đó sửa đúng chỗ thay vì chỉ thêm dependency rồi đoán.

## 2. Bốn lớp cần theo dõi từ source đến runtime

~~~text
Khai báo build:
  implementation / compileOnly / runtimeOnly / api / Maven scope
                        |
                        v
Build tool resolve thành FILES và MODULES
  compileClasspath ----> javac
  runtimeClasspath ----> Gradle run / test task / packaging task (nếu được cấu hình)
                        |
                        v
Artifact và deployment thực tế
  classes + JAR riêng / app.jar + lib/*.jar / distribution / custom executable JAR
                        |
                        v
Lệnh khởi chạy JVM
  java -cp ... Main
  java -jar ... (manifest/launcher)
  java --module-path ... --module ...
                        |
                        v
ClassLoader tại runtime
  classpath URLs / resolved modules / parent delegation / custom loaders
                        |
                        v
Class<?> và các lỗi ClassNotFoundException / NoClassDefFoundError / LinkageError
~~~

Mỗi mũi tên là **một bước cấu hình khác nhau**. Artifact đã được tải vào Gradle cache hoặc Maven local repository **không** tự biến thành classpath của một tiến trình `java` độc lập. Tương tự, có JAR trong image/container chưa đủ: launcher và ClassLoader phải thực sự nhìn thấy nó.

### Các thuật ngữ cần phân biệt

| Thuật ngữ | Diễn giải |
|---|---|
| **Declared dependency** | Ý định của project trong build file, chưa khẳng định một JAR cụ thể đã được resolve |
| **Resolved dependency** | Artifact/version cụ thể được công cụ build chọn theo repositories, variant, scope, conflict rules |
| **Compile classpath** | Bộ lớp `javac` dùng để biên dịch source; có thể khác bộ file khi chạy |
| **Runtime classpath** | Bộ entries dành cho chạy ứng dụng ở một launch configuration nhất định |
| **Module path** | Đường dẫn modules cho JPMS, được dùng cùng module resolution/visibility, không đồng nghĩa classpath |
| **Artifact/distribution** | File JAR, directory, ZIP, image hoặc layout mà task build phát hành |
| **Actual JVM launch** | Command line, working directory, JVM options, môi trường, launcher script và class loader policies |
| **Defining ClassLoader** | Loader thực sự định nghĩa lớp; việc có file trên một path khác không buộc loader này nhìn thấy file đó |

Một dependency có thể xuất hiện trong **test runtimeClasspath** nhưng không có trong **production runtimeClasspath**. Một dependency cũng có thể có trong `runtimeClasspath` của Gradle nhưng không đi vào JAR thông thường khi bạn chỉ chạy task `jar`.

## 3. Gradle: configuration mô tả nhu cầu cho từng giai đoạn

Với project áp dụng plugin `java` hoặc `java-library` của Gradle, các configuration thường gặp là:

| Gradle configuration | Compile của mã chính | Runtime của mã chính | Ý nghĩa |
|---|---|---|---|
| `implementation` | Có | Có | Thư viện mã chính cần để biên dịch và chạy; mặc định nằm ngoài public compile API của consumers khi dùng `java-library` |
| `api` (**java-library**) | Có | Có | Thư viện nằm trong public API, được lộ tới compile classpath của consumer và cần ở runtime |
| `compileOnly` | Có | Không | Chỉ cần khi biên dịch; runtime phải có nguồn cung cấp nếu code thực sự sử dụng lúc chạy |
| `runtimeOnly` | Không | Có | Cần lúc chạy, không cần trực tiếp để biên dịch mã chính |
| `annotationProcessor` | Dùng cho tác vụ annotation processing | Không phải dependency runtime thông thường | Processor chạy trong giai đoạn biên dịch |
| `testImplementation` | Dành cho compile/runtime của test | Không phải dependency production runtime chỉ vì có chữ `test` | Thư viện dành cho mã kiểm thử |
| `testRuntimeOnly` | Không để compile test | Có trong test runtime | Phụ thuộc chỉ dùng lúc thực thi test |

Ví dụ với build Groovy DSL:

~~~groovy
plugins {
    id 'java'
}

dependencies {
    implementation 'org.example:api-client:1.2.0'
    compileOnly 'org.example:provided-api:1.2.0'
    runtimeOnly 'org.example:provider-impl:1.2.0'
    testImplementation 'org.example:testing-kit:1.2.0'
}
~~~

**Đây là mã mô tả cấu hình**, tọa độ `org.example` chỉ là ví dụ khái niệm, không được coi là thư viện tồn tại để download. Hãy thay bằng dependency có thật trong dự án của bạn.

Gradle dùng các configuration có thể resolve, đặc biệt:

~~~text
compileClasspath  <= implementation + compileOnly (và các quan hệ phù hợp của plugin)
runtimeClasspath  <= implementation + runtimeOnly
test...Classpath  <= testImplementation / testRuntimeOnly và dependencies được kế thừa
~~~

Đây là **mô hình chính của Java plugin**. Plugin bổ sung và custom configurations có thể thay đổi dependency graph thực tế. Để xác minh, đọc output của configuration/task thật thay vì suy luận chỉ từ chữ `implementation`.

### Lệnh Gradle kiểm tra

Trên Linux/macOS:

~~~sh
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency api-client --configuration runtimeClasspath
~~~

Trên Windows PowerShell/CMD, dùng `gradlew.bat` tương ứng:

~~~powershell
.\gradlew.bat dependencies --configuration compileClasspath
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency api-client --configuration runtimeClasspath
~~~

`dependencies` cho thấy graph ở configuration yêu cầu. `dependencyInsight` giúp tìm **vì sao** một dependency/version được chọn. Cả hai chứng minh resolution phía build; **không tự chứng minh** artifact đã được copy vào Docker image hoặc classpath của lệnh `java` ngoài Gradle.

### `run` và `jar` không giống nhau

- Plugin `application` của Gradle có task `run` dùng runtime classpath ứng dụng đã cấu hình; distribution tasks có thể mang dependencies đi kèm trong layout riêng.
- Task `jar` của Java plugin về cơ bản tạo JAR chứa classes/resources của project, **không tự gộp toàn bộ các JAR `implementation` và `runtimeOnly`** thành một fat/uber JAR.
- Nếu bạn mang **chỉ** JAR kết quả của `jar` sang máy khác rồi chạy bằng `java -jar` hoặc `-cp` mà thiếu các dependencies bên ngoài, khả năng runtime tìm thấy class sẽ khác lúc dùng `gradlew run`.
- Nếu dùng task/plugin đóng gói khác (shadow, bootJar, distribution, container plugin...), phải kiểm tra hợp đồng và nội dung **artifact đó**. Không đồng nhất behavior của các task.

Một trường hợp thường gặp: `compileOnly` hợp lý với Servlet API do servlet container cung cấp; chạy standalone mà không có container thì class có thể thiếu. Mặt khác, thay mọi dependency thành `implementation` không bảo đảm plain JAR tự chứa chúng.

## 4. Maven: dependency scope không phải đường dẫn JVM tự sinh

Một `pom.xml` có thể khai báo:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.example</groupId>
    <artifactId>core-lib</artifactId>
    <version>1.0.0</version>
  </dependency>

  <dependency>
    <groupId>org.example</groupId>
    <artifactId>container-api</artifactId>
    <version>1.0.0</version>
    <scope>provided</scope>
  </dependency>

  <dependency>
    <groupId>org.example</groupId>
    <artifactId>driver</artifactId>
    <version>1.0.0</version>
    <scope>runtime</scope>
  </dependency>
</dependencies>
~~~

**Đây là cấu hình minh họa**, các tọa độ `org.example` không được bảo đảm có artifact thật. Nó làm rõ ba ý nghĩa scope chứ không phải dự án mẫu để chạy Maven.

| Maven scope | Compile | Runtime của mã chính | Test | Lưu ý |
|---|---|---|---|---|
| `compile` (mặc định) | Có | Có | Có | Dùng phổ biến; dependency có thể truyền qua dependency graph tùy quy tắc transitivity |
| `provided` | Có | Không | Có | Giả định môi trường/JDK/container cung cấp lúc chạy |
| `runtime` | Không | Có | Có | Ví dụ JDBC driver khi mã ứng dụng dùng API chuẩn để kết nối |
| `test` | Không | Không | Có | Không dành cho runtime production |

Các scope khác như `system`/`import` phục vụ ngữ cảnh đặc biệt; không xem chúng là runtime classpath mặc định của một chương trình `java`. Các quy tắc dependency bắc cầu và dependency management có thể làm version/artifact thực sự khác mong đợi.

**Điểm quyết định:** Maven `compile` có nghĩa artifact là ứng viên cho **classpath của các tác vụ Maven**. Task đóng gói thông thường vẫn có thể sinh một JAR chỉ chứa lớp của chính project. Việc chạy một plain JAR bằng launcher độc lập cần runtime dependencies được phát hành/tham chiếu riêng hoặc bundling theo plugin cấu hình.

### Kiểm tra Maven

~~~sh
mvn dependency:tree
mvn dependency:tree -Dscope=runtime
~~~

Cây dependency trả lời “Maven chọn những dependencies nào” theo scope/filter. Muốn biết **artifact deploy cuối** chứa gì, phải inspect `target/*.jar`, thư mục distribution hoặc layout container. Đừng suy luận packaging chỉ bằng việc dependency xuất hiện trong `dependency:tree`.

## 5. Thực hành Gradle: task `run` khác plain `jar`

Ví dụ Java thuần `javac`/`java` đã có trong bài **Classpath lúc biên dịch khác classpath lúc chạy**. Để thấy vai trò riêng của build tool, thí nghiệm này sử dụng **cùng code và cùng dependency**, nhưng chạy qua `gradle run` rồi so với `java -jar` của artifact do task `jar` tạo.

### 5.1. Chuẩn bị dự án, không cần download thư viện từ internet

Tạo cấu trúc:

~~~text
build-path-demo/
├── settings.gradle
├── build.gradle
├── helper-src/demo/lib/Greeting.java
└── src/main/java/demo/app/Main.java
~~~

**`settings.gradle`:**

~~~groovy
rootProject.name = 'build-path-demo'
~~~

**`helper-src/demo/lib/Greeting.java`:**

~~~java
package demo.lib;

public final class Greeting {
    private Greeting() {}

    public static String message() {
        return "LIB_READY";
    }
}
~~~

**`src/main/java/demo/app/Main.java`:**

~~~java
package demo.app;

import demo.lib.Greeting;

public final class Main {
    public static void main(String[] args) {
        System.out.println("mainLoaded=true");
        System.out.println("library=" + Greeting.message());
    }
}
~~~

**`build.gradle` (Groovy DSL):**

~~~groovy
plugins {
    id 'application'
}

application {
    mainClass = 'demo.app.Main'
}

dependencies {
    implementation files('lib/greeting.jar')
}

tasks.named('jar') {
    manifest {
        attributes('Main-Class': 'demo.app.Main')
    }
}
~~~

Thư viện được tạo cục bộ bằng JDK 17+ tại root của ví dụ:

~~~bash
mkdir -p out/helper lib
javac --release 17 -d out/helper helper-src/demo/lib/Greeting.java
jar --create --file lib/greeting.jar -C out/helper .
~~~

Trên PowerShell, thay `mkdir -p` bằng `New-Item -ItemType Directory -Force out/helper,lib | Out-Null`; các lệnh Java giữ nguyên. Dùng `jar --list --file lib/greeting.jar` để kiểm tra entry `demo/lib/Greeting.class`.

### 5.2. Một dependency, hai đường chạy

Với Gradle được cài đặt hoặc wrapper có sẵn (khi có wrapper, dùng `./gradlew` thay `gradle`):

~~~bash
gradle run
gradle jar
java -jar build/libs/build-path-demo.jar
~~~

Task `run` dùng runtime classpath của plugin `application`, nên stdout ứng dụng có:

~~~text
mainLoaded=true
library=LIB_READY
~~~

Mặc dù `implementation files('lib/greeting.jar')` đưa thư viện vào `compileClasspath` và `runtimeClasspath`, task `jar` mặc định **chỉ đóng gói classes/resources của chính project**. Bản plain JAR ở `build/libs/build-path-demo.jar` có manifest `Main-Class`, nhưng không nhúng `Greeting.class` và cũng không có `Class-Path` manifest tới `greeting.jar`. Khi chạy bằng `java -jar`, ứng dụng có thể gặp `NoClassDefFoundError: demo/lib/Greeting`. Thời điểm resolve và chi tiết stack trace phụ thuộc JVM; đọc lỗi gốc thay vì dự đoán mọi dòng output.

Hãy chạy cùng JAR với classpath rõ ràng:

~~~bash
# Linux/macOS
java -cp "build/libs/build-path-demo.jar:lib/greeting.jar" demo.app.Main
~~~

~~~powershell
# Windows
java -cp "build/libs/build-path-demo.jar;lib/greeting.jar" demo.app.Main
~~~

Output lại có `mainLoaded=true` và `library=LIB_READY`. Source và dependency không đổi; **packaging và lệnh khởi chạy** mới là biến số của thí nghiệm.

### 5.3. Truy nguyên đúng tầng

| Câu hỏi | Kiểm tra |
| --- | --- |
| Gradle có resolve library cho runtime? | `gradle dependencies --configuration runtimeClasspath` |
| Task `run` có thấy library? | `gradle run` và dòng `LIB_READY` |
| Plain JAR thực sự chứa gì? | `jar --list --file build/libs/build-path-demo.jar` |
| JVM được cấu hình classpath ra sao? | So sánh `java -jar ...` với `java -cp ... demo.app.Main` |

Với Spring Boot/Shadow/application distribution hoặc Docker, việc đóng gói và launcher có thể khác. Cần xem artifact phát hành thật, thay vì giả định task nào cũng tạo fat JAR.

## 6. JVM tìm lớp qua những con đường nào?

### 6.1. Classpath của launcher

Khi chạy:

~~~sh
java -cp "out/classes:lib/a.jar:lib/b.jar" demo.app.Main
~~~

Trên hệ dùng dấu `:`, các mục cách nhau bởi dấu này. Một mục có thể là **thư mục gốc chứa hierarchy package**, JAR/ZIP, hoặc mục phù hợp theo hợp đồng launcher. Trên Windows dùng dấu `;`.

- Với class tên `demo.lib.Greeting` và classpath root là `out/classes`, JVM mong có đường tương ứng `out/classes/demo/lib/Greeting.class`.
- File `lib/a.jar` chỉ hỗ trợ tra cứu khi nó là entry được launcher hoặc ClassLoader sử dụng.
- Thư mục chứa `a.jar` không đồng nghĩa JAR đó đã được thêm vào classpath. Với cú pháp wildcard classpath `lib/*`, launcher Java mở rộng tới các JAR có đuôi .jar/.JAR trực tiếp trong thư mục; không nên giả định mọi thư mục con đều được quét đệ quy.
- Khi tự tạo `URLClassLoader`, nó có thể dùng URL khác hoàn toàn với classpath của launcher.

### 6.2. ClassLoader có thể ủy quyền và cô lập

Ba tên quen thuộc — bootstrap, platform và application/system — chỉ mô tả nhóm loader tích hợp. Framework có thể tạo loader riêng cho plugin, servlet application, module layer hoặc dynamic loading.

Vì thế:

- `System.getProperty("java.class.path")` thường giúp xem user classpath do launcher đặt, **không** là danh sách đầy đủ của mọi URL/module mà mọi loader tùy chỉnh có thể dùng.
- `SomeClass.class.getClassLoader()` xác định **defining loader** của class; với một số class nền tảng được bootstrap định nghĩa, kết quả là `null` hợp lệ.
- Một JAR có mặt trong process file system chưa chắc loader **đang yêu cầu** có quyền tìm tới.
- Hai loader khác nhau có thể định nghĩa hai class cùng binary name, dẫn tới khác type identity; không nên “sửa” bằng cách copy JAR vào mọi nơi mà không xét cơ chế cô lập.

### 6.3. Module path không phải classpath thứ hai đơn giản

Nếu dùng JPMS/named modules, launcher thường có dạng:

~~~sh
java --module-path mods --module com.example.app/com.example.app.Main
~~~

Các module được tìm/resolved theo root modules, `requires` và cấu hình; có JAR trên module path không có nghĩa **mọi** module trong thư mục sẽ được resolve. Các quy tắc `exports`/`opens`/readability còn ảnh hưởng đến truy cập sau khi tìm được class.

Ví dụ dạng phân biệt:

~~~text
build tool resolves JAR
  -> được chọn cho module path?
  -> module có được resolve?
  -> class thuộc module nào?
  -> module ánh xạ tới loader nào?
  -> package/class có quyền truy cập?
~~~

Vì vậy, nếu classpath đã đúng nhưng ứng dụng modular vẫn báo lỗi access hoặc module không được resolve, cần kiểm tra JPMS riêng thay vì tiếp tục thêm mục vào `-cp`.

## 7. Phụ thuộc bắc cầu, phiên bản và cách đóng gói

### 7.1. Dependency bắc cầu không chắc đi vào mọi artifact

Ví dụ:

~~~text
app -> client.jar -> codec.jar
~~~

Build tool có thể resolve cả `client.jar` và `codec.jar` vào runtime configuration nhờ metadata. Nhưng khi tự chạy:

~~~sh
java -cp "app.jar:client.jar" demo.app.Main
~~~

và `client.jar` thật sự cần `codec.jar`, runtime vẫn có thể thiếu `codec.jar`. **Classpath do bạn ghi không tự động đọc lại toàn bộ dependency metadata của Maven/Gradle để tải file còn thiếu.**

Cần đưa đủ artifact cần thiết vào runtime classpath/module path hoặc dùng distribution/packaging có hỗ trợ.

### 7.2. Compile version và runtime version có thể khác

Ví dụ build compile với `client-v2.jar` chứa method `Client.newFeature()`. Runtime lại dùng `client-v1.jar` có class `Client` nhưng **thiếu method đó**. ClassLoader vẫn có thể tìm được class, nhưng lúc gọi method sẽ có thể ném `NoSuchMethodError`.

| Triệu chứng | Một hướng nguyên nhân | Việc kiểm chứng |
|---|---|---|
| `ClassNotFoundException` | Lookup theo tên không tìm thấy class | Runtime entries, binary name, loader |
| `NoClassDefFoundError` | JVM không có định nghĩa class cần thiết, hoặc trạng thái lỗi initialization trước đó | Cause/stack trace; runtime classpath, initializer, version |
| `NoSuchMethodError` / `NoSuchFieldError` | Binary ABI mismatch giữa compile và runtime | Version/JAR thực tế, chữ ký member trong class |
| `UnsupportedClassVersionError` | Classfile được biên dịch cho JVM mới hơn runtime | `java -version`, target của compiler |
| `ClassCastException` khi class names giống nhau | Khác defining loader hoặc cast logic sai | Đối tượng `Class` và defining loader thực tế |
| `ServiceConfigurationError` | Provider declaration/class/dependency của `ServiceLoader` lỗi | Metadata `META-INF/services`/`provides` và visibility runtime |

**Không suy luận tất cả `NoClassDefFoundError` đều do thiếu JAR.** Một lớp đã thất bại trong static initialization cũng có thể khiến các lần sử dụng sau báo lỗi dạng này. Đọc `Caused by` và lỗi đầu tiên trong log.

### 7.3. Plain JAR, fat JAR, executable JAR và distribution

- **Plain JAR:** thường chứa classes/resources của project; dependencies ở JAR khác.
- **Fat/uber/shaded JAR:** build process đưa các classes/dependencies vào cùng một archive theo quy tắc cụ thể; có thể có đổi package (*relocation*) hoặc xung đột resource nếu cấu hình sai.
- **Executable JAR của framework:** có thể chứa nested libraries và dùng **custom launcher/ClassLoader** để tìm chúng; không nên giả định `java -cp framework.jar SomeClass` có cùng hiệu ứng với `java -jar framework.jar`.
- **Application distribution:** có thể gồm thư mục `lib/`, launcher script và file cấu hình; chính script tạo classpath khi chạy.
- **Container image:** phải chứa đủ các artifacts và dùng đúng `ENTRYPOINT`/`CMD` hoặc script; image copy thiếu `lib/` vẫn làm lỗi dù build local thành công.

Không có cách suy luận chắc chắn “dependency có trong build file nên có trong output” mà không biết task đóng gói cụ thể.

## 8. Quy trình kiểm tra đúng đường dẫn JVM đang dùng

Khi lỗi xảy ra sau deployment, thực hiện theo thứ tự:

1. **Xác định lệnh launch thật:** `java -cp` hay `java -jar`? Có `--module-path`/`--module`? Process chạy từ thư mục nào? Nếu dùng launcher script, container hoặc IDE, kiểm tra command mà chúng sinh ra.
2. **Đối chiếu compile/runtime dependencies:** trong Gradle kiểm tra `compileClasspath` vs `runtimeClasspath`; trong Maven xem dependency scopes và effective resolution.
3. **Xem artifact thực tế:** `jar --list --file ...` và layout thư mục deploy; library đã được copy/chèn vào JAR đúng cách hay chưa?
4. **So binary name và đường dẫn:** package path trong directory/JAR có đúng như tên class đang bị báo lỗi?
5. **Kiểm tra đúng JVM/JDK và version:** `java -version`, compiler release target, metadata của JAR dependency, sự khác nhau local/container.
6. **Xác định loader đang dùng:** custom ClassLoader, classloader isolation, plugin/servlet container có thể bỏ qua user classpath hoặc dùng parent khác.
7. **Nếu dùng named modules:** kiểm tra module path, resolution, readability, `exports` và class nằm trong module nào.
8. **Thu hẹp thành một lệnh tái hiện:** chạy với classpath tối thiểu, thêm đúng dependency còn thiếu, và so kết quả. Giữ nguyên source để xác định lỗi nằm ở runtime wiring.

### Chẩn đoán bằng câu lệnh và API

Trên JVM có hỗ trợ unified logging (ví dụ HotSpot 17+), có thể thử:

~~~sh
java -Xlog:class+load=info -cp "build/app:build/lib.jar" demo.app.Main
~~~

Log giúp quan sát **class nào được load từ nguồn nào**; khối lượng rất lớn nên nên lọc theo tên class cần điều tra. Đầu ra log khác nhau giữa runtime/vendor nên **không** dùng nó làm stdout cố định của bài.

Trong một phương thức Java, có thể dùng:

~~~java
System.out.println(System.getProperty("java.class.path"));
System.out.println(demo.app.Main.class.getClassLoader());
System.out.println(demo.app.Main.class.getModule().getName());
~~~

Đây là **mã minh họa**, không phải chương trình độc lập. `java.class.path` không liệt kê đầy đủ classpath của mọi custom loader. `getModule().getName()` có thể `null` với unnamed module; `getClassLoader()` có thể `null` với bootstrap-defined class. Đó là các giá trị hợp lệ cần giải thích theo ngữ cảnh.

### Bảng quyết định thực tế

| Quan sát | Suy luận có cơ sở | Bước tiếp theo |
|---|---|---|
| Có dependency trong `compileClasspath`, không có trong `runtimeClasspath` | Scope/configuration không đưa library vào runtime của mã chính | Xem `compileOnly`/`provided` và nguồn cung cấp từ môi trường |
| Có trong `runtimeClasspath`, nhưng không có trong deploy | Packaging/distribution/CI chưa đưa artifact vào output | Kiểm tra task tạo JAR/image và bước copy/upload |
| Có trong thư mục deploy nhưng launcher không thấy | Lệnh `-cp`/manifest/working directory không tham chiếu đúng | Sửa launcher hoặc distribution script |
| Có class trong JAR nhưng vẫn `ClassNotFoundException` | Loader đang tra cứu khác hoặc module/path/name không đúng | In loader, binary name, URL/module layout |
| Tìm được class nhưng lỗi `NoSuchMethodError` | Khả năng cao runtime đang dùng version không tương thích | Kiểm tra artifact/version thực sự được nạp |
| Chạy với Gradle task `run` được, `java -jar` lỗi | Runtime wiring của task khác executable JAR/deploy | So sánh classpaths và launcher/packaging |
| Local chạy tốt nhưng container lỗi | File copy, workdir, launch hoặc Java version khác | Kiểm tra image filesystem và runtime command |

## 9. Những ngộ nhận cần tránh

1. **“Có `implementation` là JAR ứng dụng chứa luôn dependency.”** Không đúng với plain `jar`; runtime configuration và packaging là hai bước khác.
2. **“`compileOnly` chạy thành công lúc compile thì runtime cũng chắc chắn có.”** Không đúng: dependency đã bị chủ động loại khỏi runtime classpath của mã chính.
3. **“Maven `provided` tự cài thư viện vào server.”** Không đúng: scope chỉ biểu thị kỳ vọng môi trường cung cấp; bạn vẫn phải bảo đảm môi trường có thư viện phù hợp.
4. **“`testImplementation` làm dependency sẵn có ở production.”** Không đúng theo cấu hình Java plugin thông thường.
5. **“`gradlew dependencies` chứng minh image đã đóng gói JAR.”** Chỉ chứng minh graph theo configuration, không phải artifact deploy.
6. **“Chạy `java -jar app.jar -cp lib.jar` sẽ thêm thư viện.”** Không đúng: tham số sau tên JAR đi vào `args` của main; `-jar` và app classpath phải được cấu hình theo hợp đồng launcher.
7. **“Thêm JAR vào cùng thư mục là JVM tự tìm thấy.”** Không đúng nếu launcher không tham chiếu nó qua classpath/manifest/loader hoặc cơ chế phù hợp.
8. **“Mọi lỗi class đều là thiếu file.”** Có thể là version mismatch, lỗi initialization, quyền truy cập JPMS hoặc classloader identity.
9. **“`java.class.path` chứa mọi class mà JVM có thể nhìn thấy.”** Không đúng với bootstrap/platform modules hoặc custom loaders.
10. **“Đưa cùng tên class vào nhiều ClassLoader chỉ làm nó dễ tìm hơn.”** Có thể tạo hai runtime types khác nhau, dẫn tới `ClassCastException`/`LinkageError`.
11. **“`--module-path` nghĩa là mọi JAR đã được load.”** Module resolution và class loading còn là các bước riêng.
12. **“Build trên JDK mới thì runtime JDK cũ vẫn chạy miễn classpath đúng.”** Có thể thất bại vì classfile version, API không tồn tại hoặc module compatibility.

## 10. Bài tập vận dụng

1. Gradle project khai báo `compileOnly 'org.example:api:1.0'`. Code compile, nhưng chạy standalone bị `NoClassDefFoundError`. Bạn kiểm tra configuration nào đầu tiên và vì sao?
2. Vì sao `./gradlew run` chạy được trong khi `java -jar build/libs/app.jar` thiếu class, dù không đổi source?
3. Maven `scope=provided` có đồng nghĩa JAR đóng gói xong luôn chứa thư viện không? Môi trường nào thường cung cấp dependency đó?
4. Trong thực hành, tại sao `gradle run` thấy `Greeting` nhưng `java -jar build/libs/build-path-demo.jar` lại thiếu thư viện?
5. Viết runtime classpath gồm `build/libs/build-path-demo.jar` và `lib/greeting.jar` trên Linux và Windows; dấu phân cách khác nhau thế nào?
6. Vì sao `java -jar build/app.jar` vẫn thiếu library sau khi đã tạo manifest có `Main-Class`?
7. Nếu project phụ thuộc A rồi A phụ thuộc B, tại sao copy mỗi A.jar sang server vẫn có thể không đủ?
8. Nếu class tìm thấy nhưng method vắng mặt, vì sao nên kiểm tra `NoSuchMethodError` và phiên bản runtime?
9. Cách nào kiểm tra JAR chứa class cụ thể? Cách nào kiểm tra Gradle đã resolve library cho runtime?
10. Vì sao `Class.getClassLoader()` và `Module.getName()` giúp phân tích vấn đề mà `System.getProperty("java.class.path")` không giải thích hết?
11. Một app chạy từ module path gặp lỗi `exports`; chỉ thêm dependency vào build file đã giải quyết chắc chắn chưa?
12. Với container image, hãy mô tả ba thứ phải khớp: file đã copy, runtime command và dependency/loader visibility.

**Tiêu chí hoàn thành:** chạy chính xác hai trường hợp của ví dụ Java 17+; giải thích được lý do compile thành công nhưng runtime thiếu class; phân biệt configuration build, artifact packaging, launcher và defining loader; biết chọn phép kiểm tra đúng khi lỗi phát sinh trên máy deploy.

## 11. Tài liệu chính thức

- [Gradle Java Plugin — Dependency management](https://docs.gradle.org/current/userguide/java_plugin.html): `compileClasspath`, `runtimeClasspath` và các dependency configurations của mã chính/test.
- [Gradle Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): phân biệt `api`, `implementation` và việc công bố dependency cho consumers.
- [Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): các scope `compile`, `provided`, `runtime`, `test` và dependency transitivity.
- [Java Launcher — `java`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): `-classpath`, `-jar`, `--module-path`, `--module` và cơ chế khởi chạy.
- [JAR File Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html): manifest `Main-Class`, `Class-Path` và cấu trúc archive.
- [Java SE 21 — `ClassLoader` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): delegation, defining loaders và việc tìm lớp.

Bài học tập trung vào **đường đi từ dependency của build tool đến khả năng tìm lớp ở runtime**. Ví dụ dùng Java chuẩn, không giả định một framework, plugin đóng gói hoặc CI cụ thể.
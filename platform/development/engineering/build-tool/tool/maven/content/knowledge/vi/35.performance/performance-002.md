# Phân biệt chi phí khởi động, phân giải phụ thuộc và chạy plugin trong Maven

## 1. Mục tiêu bài học

Một câu nói thường gặp khi build Java là: “Maven chậm”. Nhưng cùng một con số tổng thời gian có thể đến từ những nguyên nhân hoàn toàn khác nhau:

1. **Chi phí khởi động**: Maven Wrapper (nếu dùng) chuẩn bị Maven distribution, JVM được tạo, Maven Core và extensions khởi tạo, settings/POM/reactor model được đọc.
2. **Chi phí phân giải phụ thuộc (resolution)**: Maven kiểm tra repository, metadata, tải parent POM/BOM/project dependencies, plugins và dependencies của plugins, rồi dựng dependency/plugin classpaths.
3. **Chi phí chạy plugin (execution)**: các goals như `resources:resources`, `compiler:compile`, `surefire:test`, `jar:jar` và code generator thực sự làm công việc của chúng.

Ba nhóm này có biểu hiện, dữ liệu chẩn đoán và cách tối ưu rất khác. Nếu chậm vì tải artifacts qua mạng, chuyển `javac` sang JDK mới chưa chắc giúp. Nếu chậm vì chạy hàng nghìn integration tests, “xóa cache Maven” chỉ khiến việc build chậm hơn.

Sau bài học, bạn sẽ biết:

- Phân biệt **launcher/JVM startup**, **project model preparation**, **artifact resolution** và **plugin execution**.
- Hiểu sự khác biệt giữa dependency JAR của ứng dụng, plugin JAR và plugin dependencies.
- Đọc Maven log để nhận diện download/metadata, goal bắt đầu và test fork.
- Dùng `mvn -version`, `validate`, `clean verify`, `-o`, `-ntp` và local repository riêng **đúng ngữ cảnh**.
- Thiết kế phép đo cold/warm build và thu thập wall-clock time trên Unix/Linux/macOS và Windows PowerShell.
- Chạy một project Java 17 hoàn chỉnh để thấy cách Compiler, Surefire, Resources và JAR Plugins tạo ra work thật.
- So sánh đầy đủ giữa build sạch, build tăng dần, cache đã nóng, cache trống và test được bỏ qua có chủ đích.
- Tránh các “tối ưu” sai như luôn skip tests, không kiểm tra plugin versions hoặc nhầm `-T` là công cụ tăng tốc mọi project.
- Lập báo cáo bottleneck có thể kiểm chứng thay vì nêu số giây không có phép đo.

Các ví dụ dùng **JDK 17+**, Maven 3.9.x, Maven Dependency Plugin 3.8.1, Maven Compiler Plugin 3.13.0 và Surefire Plugin 3.2.5. Đây là phiên bản đã chọn để ví dụ tái lập được, **không phải** khẳng định bản mới nhất của từng công cụ.

## 2. Một công thức tư duy, không phải định luật cộng đơn giản

Có thể dùng mô hình gần đúng:

\[
T_{\text{wall}} \approx T_{\text{wrapper/JVM}} + T_{\text{model}} + T_{\text{resolution}} + T_{\text{mojo execution}} + T_{\text{finalization}}
\]

Giải thích:

- `T_wall` là thời gian thực từ lúc người dùng chạy lệnh đến lúc process kết thúc, đo bằng đồng hồ ngoài process.
- `T_wrapper/JVM` gồm launcher chuẩn bị distribution (khi cần) và khởi động Java process chạy Maven.
- `T_model` gồm đọc POM, parent POM, activation profiles, model interpolation, reactor projects và lifecycle plan.
- `T_resolution` gồm tìm/tải/cached dependencies, plugins, parent/BOM metadata và tạo classpaths.
- `T_mojo execution` là thời gian plugin goals làm việc, có thể bao gồm khởi động JVM tests hoặc các thao tác I/O riêng.
- `T_finalization` là ghi logs, báo cáo, đóng streams và những công việc kết thúc.

**Đây là một mô hình giải thích, không phải phép tách chính xác bằng log mặc định.** Resolution có thể diễn ra khi Maven đang dựng model, chuẩn bị plugin hoặc **bên trong một plugin goal**; trong reactor parallel có các tác vụ chồng thời gian. Vì vậy không thể lấy ba dòng số bất kỳ rồi cộng cho bằng wall-clock.

Cần phân biệt **exclusive time** (thời gian chỉ thuộc bước đó) với **inclusive time** (bao gồm lời gọi con). Nếu một plugin resolve một dependency rồi thực thi, “plugin duration” có thể đã bao gồm chi phí resolution. Đếm tiếp duration resolution sẽ **double-count**.

## 3. Sơ đồ luồng một lệnh Maven

~~~text
Người dùng gõ ./mvnw -B -ntp clean verify
                 |
                 v
Wrapper script / Maven distribution có sẵn?
                 |
          [Nếu chưa có: download]
                 |
                 v
Tạo JVM chạy Maven, load Maven Core/extensions
                 |
                 v
Đọc settings, POM, parent POM/BOM, profiles
                 |
                 v
Tạo reactor/lifecycle execution plan
                 |
                 v
Resolve artifacts & plugin dependencies khi cần
                 |
                 v
Thực thi từng plugin goal theo phase
    clean -> resources -> compiler -> testCompile
           -> surefire -> jar -> verify checks
                 |
                 v
BUILD SUCCESS / BUILD FAILURE
~~~

Đây là **sơ đồ tuyến tính để học**. Trên thực tế, parent resolution có thể xảy ra ngay khi tạo model, plugin resolution có thể xảy ra gần lúc chạy goal, và goals có thể tải thêm artifacts riêng. Trong multi-module parallel build, nhiều module có thể chạy cùng lúc.

**Điểm cốt lõi:** “Downloading…” là dấu hiệu work ở network/repository, còn “--- compiler:...:compile ---” là một plugin execution đang được Maven bắt đầu. Không được coi hai loại dòng log là cùng một bottleneck.

## 4. Chi phí số 1: khởi động Maven/Wrapper/JVM

Khi chạy:

~~~bash
./mvnw -version
~~~

trên Unix-like hoặc:

~~~powershell
.\mvnw.cmd -version
~~~

trên Windows, có thể có:

1. Khởi động shell wrapper.
2. Kiểm tra Maven distribution theo `.mvn/wrapper/maven-wrapper.properties`.
3. Nếu chưa có bản Maven này trong wrapper cache, tải distribution qua mạng.
4. Chạy Java process để in Maven/JDK information.

**Một lần download Maven distribution không phải chi phí khởi động ổn định**. Nếu đo lần đầu cài Wrapper và lấy giá trị đó làm baseline cho mọi build, bạn đã trộn network transfer với launcher startup.

Còn khi gọi trực tiếp:

~~~bash
mvn -version
~~~

không qua Wrapper, launcher sử dụng bản Maven đã cài trên PATH.

### Những thành phần có thể ảnh hưởng startup

- Thời gian tạo JVM của JDK/version/OS hiện hành.
- `JAVA_HOME` và JVM options (ví dụ heap, agents, extensions).
- Máy ảo/CI runner/container có cold filesystem cache hay không.
- Core extensions khai báo ở `.mvn/extensions.xml`.
- Filesystem I/O, antivirus/security scanner, network-mounted home directory.
- Maven Wrapper bootstrap khi distribution chưa cached.

**Không phải mọi thứ kể trên được `mvn -version` thực thi đầy đủ**. Lệnh `-version` chủ yếu cho thông tin Maven/JDK; nó không build project model, không tự chạy Compiler/Surefire của POM. Vì vậy đây chỉ là một **ước lượng launcher baseline**, không phải “thời gian khởi động toàn Maven project”.

## 5. Model-building là chi phí trước plugin execution

Trong một lệnh thực tế như:

~~~bash
./mvnw -B -ntp -N validate
~~~

Maven có thể đọc POM hiện tại, parent, profiles, settings và dựng project model. Nhưng:

- `-N` là non-recursive: không đi sâu vào các child modules của aggregator.
- `validate` là phase sớm của default lifecycle; nó **không** compile/test/package.
- Nếu POM bind Enforcer hoặc plugin khác vào `validate`, lệnh này vẫn chạy goals tương ứng.
- Nếu parent/BOM hoặc extension chưa cached, nó có thể cần resolution/network.
- Với project POM phức tạp, riêng model building cũng có thể đáng kể.

Do đó `mvn -N validate` là **baseline Maven project preparation tương đối nhẹ**, **không phải phép đo thuần chỉ JVM startup**.

### Vì sao parent POM và BOM xuất hiện ngay ở đây?

Khi dựng effective model, Maven cần các thông tin inherited/managed để xác định project. Parent POM có thể phải được resolve trước khi Maven chạy một goal bất kỳ. Một BOM được import trong `dependencyManagement` cũng có thể cần resolution lúc model construction.

Nếu `validate` chậm vì Maven đang tải parent POM/BOM, không được quy hết vào Maven Core startup. Đây là **resolution trong model preparation**.

## 6. Chi phí số 2: phân giải phụ thuộc

Maven sử dụng tọa độ artifacts và repository metadata để xác định các files cần có.

Một dependency bình thường:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.14.0</version>
</dependency>
~~~

Một lần resolution có thể gồm:

1. Xác định GAV/type/classifier.
2. Kiểm tra `dependencyManagement`, exclusions, scopes và transitive graph.
3. Kiểm tra local Maven repository (thường là `~/.m2/repository`).
4. Nếu thiếu artifact/metadata hoặc update policy yêu cầu, liên hệ remote repository/mirror.
5. Tải POM, JAR và các artifacts liên quan.
6. Xác thực checksum/metadata theo Maven/repository policy.
7. Chuẩn bị classpaths cho compile/test/runtime hoặc plugin goals.

**Một dependency đã cached không nhất thiết làm resolution bằng không.** Resolver vẫn phải tính graph và xác định artifact files; chỉ có chi phí download/network thường giảm đáng kể trong warm cache.

## 7. Parent, BOM, project dependency và Maven plugin khác nhau

| Loại artifact | Dùng để làm gì? | Có thể xuất hiện lúc nào? |
| --- | --- | --- |
| Parent POM | Inheritance của project model | Rất sớm khi dựng model |
| BOM POM | Quản lý dependency versions | Khi import dependencyManagement |
| Project dependency JAR | Classpath compile/test/runtime | Khi goal cần resolved dependencies |
| Maven plugin JAR | Chứa goal/Mojo implementation | Khi plugin được chuẩn bị/thực thi |
| Plugin transitive dependencies | Classpath của plugin | Khi tạo plugin realm |
| Test engine/provider JAR | Chạy tests, có thể qua Surefire provider | Khi Surefire chuẩn bị/chạy tests |
| Code generator tool artifacts | Tạo source/resources | Tùy custom plugin goal |
| Native/external file | Tool bên ngoài Maven repositories | Tùy plugin/script |

**Không nhầm** `commons-lang3` của ứng dụng với `maven-compiler-plugin` hay JUnit test provider. Ngay cả project có **không dependency trực tiếp** vẫn có thể phải tải Maven Compiler/Surefire/Resources/JAR Plugins.

## 8. Maven plugin resolution cũng tiêu tốn mạng và disk

Ví dụ trong POM:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
</plugin>
~~~

Version ghim giúp Maven biết plugin artifact nào được yêu cầu. Tuy nhiên ở máy mới:

- Compiler plugin JAR có thể chưa cached.
- Những plugin dependencies có thể phải được tải.
- Plugin descriptor cần được đọc.
- Plugin class realm cần được dựng.
- Plugin parameters cần được inject từ Maven model.

Các bước này xảy ra **trước hoặc trong giai đoạn chuẩn bị plugin execution**, nhưng không phải `javac` thực sự biên dịch source.

### Tại sao gọi goal theo prefix có thể chậm thêm?

~~~bash
mvn dependency:tree
~~~

Maven có thể phải resolve plugin prefix/version nếu nó không được xác định đầy đủ trong effective POM/configuration.

Để kiểm soát thí nghiệm, dùng fully-qualified goal có version:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
~~~

Cách này giảm sự mơ hồ của plugin version resolution, **không loại bỏ** chi phí tải plugin JAR/metadata khi local cache trống.

## 9. Project dependencies và plugin dependencies có cache riêng về logic

Maven local repository cùng chứa nhiều loại artifacts, nhưng chúng tham gia hai classpaths khác nhau:

- **Project dependency graph** quyết định classpath của code được compile/test/runtime.
- **Plugin classpath/realm** quyết định cách plugin goals chạy.

Nếu thiếu Commons Lang, Compiler Plugin có thể khởi động thành công nhưng compilation fail vì thiếu project dependency.

Nếu thiếu Compiler Plugin, Maven có thể fail **trước khi** chạy compiler goal, dù Commons Lang đã nằm trong local repo.

Khi debug `Could not resolve plugin`, đừng mất thời gian sửa Java source. Khi debug `Could not resolve dependencies for project`, cần xem project GAV/repositories/mirrors thay vì đổi version Compiler Plugin một cách mù quáng.

## 10. Local repository, remote repository và mirror

Maven local repository thường:

~~~text
~/.m2/repository
~~~

Trên Windows thường dưới user profile:

~~~text
C:\Users\<user>\.m2\repository
~~~

Đây là default thông dụng, có thể thay bởi Maven settings hoặc CLI. Remote repository có thể là Maven Central hoặc Nexus/Artifactory proxy thuộc tổ chức.

**Một build cold cache chậm** nếu phải tải nhiều POMs/JARs và metadata qua mạng. Một build warm cache thường nhanh hơn, nhưng còn phụ thuộc:

- Repository update policy đối với SNAPSHOT/dynamic versions.
- Disk/SSD và antivirus.
- Remote mirror latency hoặc rate limit.
- Plugin artifacts chưa từng được tải.
- Các profiles/modules thực sự được chọn.
- Network/proxy/TLS handshake.

**Không nên xóa toàn bộ local repository của người dùng chỉ để benchmark**. Dùng một đường dẫn riêng có chủ đích cho thí nghiệm, và để caches khác nguyên vẹn.

## 11. Cold build không chỉ có một nghĩa

Cần phân biệt bốn loại “lạnh”:

1. **Cold Maven distribution**: Wrapper phải tải Maven distribution vì chưa cached.
2. **Cold Maven artifact repository**: `maven.repo.local` trống, phải tải dependencies/plugins/POMs.
3. **Cold build outputs**: thư mục `target/` trống do `clean`; Compiler/Surefire phải làm lại công việc cần thiết.
4. **Cold filesystem/JVM/CI runner**: OS page cache chưa nóng, container/runner mới, JIT không được tái sử dụng giữa processes.

Nếu báo cáo chỉ ghi “cold=72s”, người đọc **không biết cold nào**. Phải ghi rõ cold dimension đã kiểm soát.

### So sánh hợp lệ

- Lần đầu chạy với **repo riêng trống** + `clean verify` → network/artifact resolution có thể lớn.
- Lần hai cùng repo ấy + `clean verify` → downloads giảm, nhưng source/test/package vẫn chạy.
- Lần hai cùng repo ấy + `verify` (không clean) → tăng dần/incremental build có thể bỏ qua một số work.
- Cùng repo warmed + `-o clean verify` → kiểm thử khả năng hoạt động không cần remote resolution.

Đừng dùng các kết quả này hoán đổi cho nhau vì chúng thay đổi **nhiều điều kiện**.

## 12. Chi phí số 3: chạy plugin goals thật

Với Java project packaging JAR, goals thường gặp:

~~~text
clean:clean
resources:resources
compiler:compile
resources:testResources
compiler:testCompile
surefire:test
jar:jar
~~~

Một goal có thể:

- Đọc/ghi nhiều file (Resources).
- Gọi Java compiler/annotation processors (Compiler).
- Khởi tạo JVM khác và chạy tests (Surefire).
- Nén JAR/ZIP (JAR Plugin).
- Tạo/generated source (Protobuf/ANTLR/OpenAPI plugin).
- Phân tích bytecode, kiểm tra styles/lint, SBOM hoặc static analysis.
- Chạy I/O/network riêng theo logic plugin.

**Thời gian goal không chỉ phụ thuộc số source files.** Ví dụ một test chờ HTTP timeout có thể làm Surefire mất nhiều thời gian hơn cả compile. Một code generator đọc schema qua network có thể khiến phase `generate-sources` chậm dù dependencies đã cached.

## 13. Plugin prefix trong log là điểm nhận diện, không phải phép đo

Đoạn log rút gọn minh họa:

~~~text
[INFO] --- resources:3.3.1:resources (default-resources) @ maven-cost-lab ---
[INFO] --- compiler:3.13.0:compile (default-compile) @ maven-cost-lab ---
[INFO] --- resources:3.3.1:testResources (default-testResources) @ maven-cost-lab ---
[INFO] --- compiler:3.13.0:testCompile (default-testCompile) @ maven-cost-lab ---
[INFO] --- surefire:3.2.5:test (default-test) @ maven-cost-lab ---
[INFO] --- jar:3.4.2:jar (default-jar) @ maven-cost-lab ---
[INFO] BUILD SUCCESS
~~~

Đây là **dạng log minh họa**, không phải transcript của một lần benchmark thực tế. Mỗi dòng goal cho biết **Maven đã bắt đầu** goal tương ứng. Nếu không có timestamp/duration instrumentation, **không thể** kết luận Compiler mất 5s chỉ từ hai dòng goal liền nhau.

Maven thường in tổng thời gian cuối build. Con số này hữu ích để so cùng CLI conditions, nhưng với phân tích sâu phải đo wall-clock ngoài process và dùng profiling phù hợp.

## 14. Surefire có thể tạo thêm JVM

Maven Surefire Plugin có thể fork một hoặc nhiều JVM cho unit tests, phụ thuộc cấu hình `forkCount` và `reuseForks`. Chi phí của test phase có thể gồm:

1. Resolve Surefire Plugin và provider/test classpath.
2. Chuẩn bị forked JVM và command line.
3. JVM mới khởi động/load classes.
4. Initialize JUnit/TestNG provider.
5. Chạy test setup/mocks/application context.
6. Chạy assertions/integration interactions.
7. Ghi reports và chờ shutdown.

Do đó một build “chậm ở `surefire:test`” chưa chắc do Maven startup hoặc download. Có thể do Spring test context, database container, test order, blocking I/O hoặc chính startup của **test JVM**.

**Phân biệt Maven JVM startup với Surefire forked JVM startup.** Hai JVM khác nhau, xảy ra ở hai giai đoạn khác nhau.

## 15. Lệnh nào đo được cái gì?

| Lệnh | Công việc chủ yếu | Có đo thuần startup không? |
| --- | --- | --- |
| `./mvnw -version` | Wrapper/launcher/JVM + in version | Không hoàn toàn; không dựng project |
| `./mvnw -N validate` | Maven project model + goals ở validate nếu có | Không; model/resolution có thể tham gia |
| `./mvnw clean verify` | Clean + lifecycle compile/test/package/verify | Không; là tổng toàn bộ build |
| `./mvnw -o clean verify` | Build với Maven offline resolution | Không; plugin execution vẫn chạy |
| `./mvnw dependency:go-offline` | Prefetch artifacts theo goal | Không; đây là một plugin goal có execution riêng |
| `./mvnw -DskipTests clean package` | Compile/test-compile, bỏ thực thi Surefire tests | Không; một phép so để ước lượng tác động tests |
| `./mvnw -Dmaven.test.skip=true clean package` | Bỏ compile và chạy tests theo plugin policy | Không; thay đổi nhiều công việc |
| `./mvnw -T 1C clean verify` | Reactor parallel execution khi có thể | Không phải tối ưu cho mọi single module |

**Ghi nhớ:** Không có một lệnh Maven phổ thông nào trả trực tiếp một báo cáo chính xác gồm ba cột “startup”, “resolution” và “execution” cho mọi goal mặc định. Phải **thiết kế thí nghiệm + instrument** nếu cần số liệu đáng tin.

## 16. Tạo một project Java 17 để thực hành

Chúng ta dùng một Maven project độc lập:

~~~text
maven-cost-lab/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/dev/learning/perf/App.java
│   │   └── resources/app.properties
│   └── test/
│       └── java/dev/learning/perf/AppTest.java
└── target/        (được tạo khi build)
~~~

Lab có hai nhóm project dependencies:

- `org.apache.commons:commons-lang3:3.14.0` cho compile/runtime.
- `org.junit.jupiter:junit-jupiter:5.11.4` cho test.

Các plugins bắt buộc cho lifecycle được ghim version. Điều này cho phép người học biết khi nào Maven tải dependency/plugin lần đầu và khi nào nó thật sự thực thi goals.

**Không cố ý đưa Sleep hoặc network call vào unit test.** Như vậy benchmark phản ánh pipeline bình thường hơn, và không có một timeout giả khiến Surefire chậm không cần thiết.

## 17. POM hoàn chỉnh cho lab

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.learning.perf</groupId>
    <artifactId>maven-cost-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.3.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-dependency-plugin</artifactId>
                <version>3.8.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Điểm quan trọng của cấu hình:**

- `release=17` đặt Java language/platform API/classfile target.
- Commons Lang ở scope compile, JUnit Jupiter ở test scope.
- Clean, Resources, Compiler, Surefire, JAR Plugin versions cụ thể.
- Dependency Plugin được ghim để chạy `tree` và `go-offline` không phụ thuộc version resolution tự do.
- `outputTimestamp` ổn định timestamp khi tạo archive JAR, **không phải tối ưu tốc độ**.
- Đây là **plain JAR**, không nhúng Commons Lang vào JAR chính; để chạy main qua Maven classpath sẽ dùng Exec Plugin ở phần sau.

Cấu hình plugin khác nhau có thể làm thời gian build khác nhau, nên chỉ so những lần chạy với cùng POM, Maven/JDK version, profile và goals.

## 18. Source Java 17

File `src/main/java/dev/learning/perf/App.java`:

~~~java
package dev.learning.perf;

import java.util.Locale;
import org.apache.commons.lang3.StringUtils;

public final class App {

    private App() {
    }

    public static String message() {
        return "maven-cost:" + StringUtils.upperCase("ready", Locale.ROOT);
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

Mã dùng Commons Lang thật. `Locale.ROOT` giúp uppercase không phụ thuộc default locale.

**Dòng stdout chính xác do Java main in:**

~~~text
maven-cost:READY
~~~

Nếu thư viện Commons Lang chưa có trong classpath, Java main có thể báo `NoClassDefFoundError` khi chạy. Đây là vấn đề runtime dependency/classpath, **không** nên ghi nhầm thành chi phí Maven startup.

## 19. Unit test JUnit Jupiter

File `src/test/java/dev/learning/perf/AppTest.java`:

~~~java
package dev.learning.perf;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class AppTest {

    @Test
    void rendersStableMessage() {
        assertEquals("maven-cost:READY", App.message());
    }
}
~~~

Surefire Plugin sẽ phát hiện `AppTest` theo pattern thông thường và chạy JUnit Jupiter nếu môi trường/plugin dependencies resolve đúng.

Mục đích lab: một test rất nhỏ giúp thấy rằng một lần Surefire phase vẫn có overhead chuẩn bị test infrastructure/JVM, ngay cả khi assertion chạy tức thì. **Không suy ra** số milliseconds của Surefire chỉ từ số lượng test bằng 1.

## 20. Resource file và Resources Plugin

File `src/main/resources/app.properties`:

~~~properties
app.name=maven-cost-lab
app.mode=teaching
~~~

Resources Plugin sẽ xử lý resource files trong lifecycle và copy đến build output như `target/classes/app.properties`. Dù file chỉ có hai dòng, Maven vẫn phải chạy logic plugin theo lifecycle nếu goal được bind.

Điều này giúp thấy:

- **Resource work** không phải compilation.
- Với nhiều resources/filtering lớn, copy/I/O có thể đáng kể.
- Với resource rất nhỏ, overhead gọi/chuẩn bị goal có thể lớn hơn byte-copy thực tế.

Không đánh giá performance của Resources Plugin chỉ từ kích thước file trong lab; production project có thể có hàng nghìn assets hoặc filtering phức tạp.

## 21. Kiểm tra project chạy đúng trước khi benchmark

Từ root project:

~~~bash
mvn -version
java -version
mvn -B -ntp clean verify
~~~

Kết quả theo cấu hình khi các plugin/dependencies resolve thành công:

- Compiler biên dịch `App.java`.
- Resources copy `app.properties`.
- Surefire chạy 1 JUnit test thành công.
- JAR Plugin tạo `target/maven-cost-lab-1.0.0.jar`.
- Maven kết thúc `BUILD SUCCESS`.

**Không đưa ra output thời gian cụ thể** vì thời gian phụ thuộc máy, network/cache và JDK thực.

Để chạy Java main qua Maven project dependency classpath:

~~~bash
mvn -B -ntp org.codehaus.mojo:exec-maven-plugin:3.5.0:java -Dexec.mainClass=dev.learning.perf.App
~~~

Dòng stdout của app:

~~~text
maven-cost:READY
~~~

Goal `exec:java` có thể cần **download Exec Plugin lần đầu**; đó là một nguồn resolution work ngoài lifecycle verify. Đừng dùng lần đầu gọi goal này làm phép đo “chỉ tốc độ chạy App.java”.

## 22. Vì sao không dùng java -jar để làm benchmark Maven?

JAR của lab được đóng là plain JAR, chưa đặt `Main-Class` trong manifest và không nhúng Commons Lang. Do vậy:

~~~bash
java -jar target/maven-cost-lab-1.0.0.jar
~~~

không phải cách chạy runnable theo thiết kế này.

Có thể chạy bằng classpath thích hợp hoặc dùng Exec Plugin như phần 21. Việc đo `java` launcher và chương trình riêng **khác** với đo Maven build.

Nếu một bài kiểm tra performance muốn tách **javac workload** khỏi Maven, có thể dùng JDK tools trực tiếp sau khi Commons Lang JAR đã có ở local repo. Tuy nhiên đó là một **thí nghiệm khác**: phải so các compiler options, classpaths, annotation processors và incremental behavior mới có giá trị tương đương.

## 23. Đo wall-clock time trên Linux/macOS

Nếu hệ điều hành có tiện ích `/usr/bin/time`:

~~~bash
/usr/bin/time -p ./mvnw -B -ntp -N validate
/usr/bin/time -p ./mvnw -B -ntp clean verify
~~~

Ví dụ format của công cụ:

~~~text
real  ...
user  ...
sys   ...
~~~

Dấu `...` ở trên là **ký hiệu** cho số đo mà máy của bạn tạo ra; không phải expected benchmark cố định.

Giải thích:

- `real`: elapsed wall-clock duration, gồm chờ I/O và network.
- `user`: CPU time ở user mode.
- `sys`: CPU time ở kernel mode.
- Có thể `user+sys` lớn hơn `real` nếu nhiều threads/processes CPU chạy song song, tùy công cụ và phạm vi accounting.

Không lấy `real` của một single run làm kết luận chắc chắn. Nên chạy nhiều lần sau warm-up và báo median/range, đồng thời ghi environment.

### Nếu chưa có Maven Wrapper

Có thể thay `./mvnw` bằng `mvn`, nhưng phải ghi Maven version được dùng. Thực hành tạo Wrapper nếu muốn khóa version:

~~~bash
mvn -N org.apache.maven.plugins:maven-wrapper-plugin:3.3.4:wrapper -Dmaven=3.9.9 -Dtype=only-script
~~~

Wrapper thêm bước launcher/distribution cache riêng; do đó khi so sánh, cả hai case phải cùng kiểu command (Wrapper hoặc direct Maven), không trộn tùy tiện.

## 24. Đo wall-clock time trên Windows PowerShell

Dùng Stopwatch để vừa lưu exit code vừa đo elapsed time.

~~~powershell
$watch = [System.Diagnostics.Stopwatch]::StartNew()

& .\mvnw.cmd -B -ntp clean verify
$code = $LASTEXITCODE

$watch.Stop()
Write-Host ("Maven exit code: {0}" -f $code)
Write-Host ("Wall time (seconds): {0:N3}" -f $watch.Elapsed.TotalSeconds)

if ($code -ne 0) {
    throw "Maven build failed; do not use this timing as a successful-build benchmark."
}
~~~

Script chạy Maven đúng một lần; `-B` là batch mode và `-ntp` bỏ transfer progress. Stopwatch tính cả thời gian launcher, Maven Core, resolution, plugin executions và kết thúc.

Để đo validation baseline, thay:

~~~powershell
& .\mvnw.cmd -B -ntp clean verify
~~~

bằng:

~~~powershell
& .\mvnw.cmd -B -ntp -N validate
~~~

**Đừng so trực tiếp 1 run `validate` với 1 run `verify` rồi kết luận phần chênh lệch 100% là plugin execution**, vì chúng có graph resolution khác nhau và có thể resolve thêm plugins khi dùng lifecycle sâu hơn.

## 25. Benchmark lạnh và ấm với repository riêng

Trên Linux/macOS, chọn một directory mới của thí nghiệm (chưa chứa Maven artifacts):

~~~bash
mkdir -p /tmp/maven-perf-repo-a
~~~

Lần đầu:

~~~bash
/usr/bin/time -p ./mvnw -B -ntp -Dmaven.repo.local=/tmp/maven-perf-repo-a clean verify
~~~

Lần hai **cùng repository**, **cùng lệnh**:

~~~bash
/usr/bin/time -p ./mvnw -B -ntp -Dmaven.repo.local=/tmp/maven-perf-repo-a clean verify
~~~

Diễn giải:

- Lần đầu có thể tải parent POM, plugins, plugin dependencies, Commons Lang, JUnit và metadata từ remote.
- Lần hai nhiều artifact đã cached, ít network downloads hơn.
- **Cả hai lần đều có `clean`**, nên Compiler/Surefire/JAR vẫn phải làm công việc build khi source/tests hiện diện.
- Chênh lệch là dấu hiệu của **cold vs warm repository** nhưng cũng chịu ảnh hưởng JVM/OS page cache, remote update policy và nhiễu môi trường.
- Một số plugin có thể cache riêng ngoài Maven repository. Phải ghi nhận nếu có.

**Không xóa `~/.m2/repository`** để làm thí nghiệm. Dùng repo riêng và chỉ dọn đúng đường dẫn bạn tạo, khi không còn cần dữ liệu.

## 26. Benchmark trên Windows với repository riêng

Chọn directory tách biệt, ví dụ:

~~~powershell
$repo = Join-Path $env:TEMP "maven-perf-repo-a"
New-Item -ItemType Directory -Force -Path $repo | Out-Null

$watch = [System.Diagnostics.Stopwatch]::StartNew()
& .\mvnw.cmd -B -ntp "-Dmaven.repo.local=$repo" clean verify
$exit = $LASTEXITCODE
$watch.Stop()

Write-Host ("Exit={0}; seconds={1:N3}" -f $exit, $watch.Elapsed.TotalSeconds)
~~~

Lặp lại **cùng command** với cùng `$repo` để tạo warm-cache case; không đổi JDK, network, profile hoặc working directory giữa hai runs.

Đừng tự giả định mọi trường hợp có lần hai nhanh hơn: remote snapshot policy, SSD cache, antivirus hoặc các goals không deterministic có thể làm kết quả dao động.

## 27. Có cần “tắt mạng” để tách resolution không?

Maven có option:

~~~bash
./mvnw -B -ntp -o clean verify
~~~

`-o` là offline mode: Maven không dùng remote repositories để resolve các artifacts còn thiếu. Nó **không**:

- Bỏ qua phase compile/test.
- Biến Maven thành process không cần classpath.
- Tắt mọi network call do plugin tùy biến, test code hoặc external tooling tự thực hiện.
- Tự tạo những artifacts chưa có trong cache.
- Đảm bảo build sẽ thành công nếu local repository trống.

Dùng `-o` sau khi đã populate cùng repository và cùng profiles/goals để so behavior khi không cần remote artifact resolution. Nếu offline build **fail vì artifact/plugin thiếu**, đó là **kết quả chẩn đoán hữu ích**, không nên che bằng việc skip toàn bộ build.

## 28. Prefetch artifacts bằng dependency:go-offline

Maven Dependency Plugin có goal:

~~~bash
./mvnw -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:go-offline
~~~

Theo tài liệu, goal này cố gắng resolve **project dependencies, plugins, report plugins và dependencies của chúng** theo project model.

Sau prefetch:

~~~bash
./mvnw -B -ntp -o clean verify
~~~

có thể thành công nếu **mọi artifact cần thiết** đã có trong local repository và các plugins/scripts không cần remote resources khác.

**Những giới hạn quan trọng:**

- Go-offline là một plugin goal, nên chính nó cũng có **startup, resolution và execution overhead**.
- Goals/profiles chưa được chạy trong prefetch có thể yêu cầu artifacts khác.
- Một số plugin tạo hoặc tải dependencies động trong lúc thực thi; go-offline không bảo đảm cover mọi trường hợp đó.
- Classifier, OS-specific dependencies, tools và build extensions có thể khác theo môi trường.
- Nếu có SNAPSHOT, update policy/metadata và cache state vẫn quan trọng.
- Vì vậy `go-offline BUILD SUCCESS` **không phải chứng chỉ tuyệt đối** rằng mọi project CI pipeline sẽ chạy offline.

Trong CI cần prefetch và kiểm tra offline bằng **chính active profiles/goals/module selection dự kiến**, hoặc sử dụng trusted artifact repository proxy/caching rõ ràng.

## 29. -ntp và -q chỉ thay cách hiển thị log

Maven CLI:

~~~bash
./mvnw -B -ntp clean verify
~~~

- `-B`: batch/non-interactive mode.
- `-ntp`: không hiển thị progress bars khi download/upload.

Hai cờ này hữu ích để logs CI sạch và dễ so sánh, nhưng **không loại bỏ network resolution**.

Nếu thêm:

~~~bash
./mvnw -q clean verify
~~~

`-q` làm log ít hơn, có thể khiến khó nhận ra goals nào chạy hoặc downloads xảy ra. Chỉ vì log không in “Downloading” **không có nghĩa Maven không dùng network**.

Để điều tra performance, giữ log mức INFO có chủ đích hoặc ghi file log, rồi so các executions đúng ngữ cảnh.

## 30. -X và -e để chẩn đoán, không dùng làm benchmark mặc định

Khi resolution có vấn đề:

~~~bash
./mvnw -B -ntp -X clean verify
~~~

`-X` bật debug logging, có thể lộ chi tiết repository selection, plugin classpath, configuration và file paths.

Khi build fail:

~~~bash
./mvnw -B -ntp -e clean verify
~~~

`-e` hiển thị error stack traces theo CLI options.

**Tại sao không dùng `-X` để benchmark chính thức?**

- Debug logging tạo thêm I/O và CPU overhead.
- Logs có thể chứa repository URLs, local paths, names hoặc thông tin nội bộ; cần review trước khi chia sẻ.
- Debug output có thể ảnh hưởng thời gian của chính thí nghiệm.
- Nó không tự động cộng duration của mọi loại work thành một profile chính xác.

Dùng một **diagnostic run riêng** có `-X`, sau đó quay lại commands/logging level bình thường để đo wall-clock.

## 31. -U có thể làm resolution tăng lên

Maven CLI có:

~~~bash
./mvnw -B -ntp -U clean verify
~~~

`-U` buộc kiểm tra missing releases và updated snapshots trên remote repositories theo Maven CLI behavior. Nó **không** là công tắc tăng tốc chung.

Với dự án dùng SNAPSHOT hoặc dependencies chưa cached, `-U` có thể khiến Maven liên hệ remote repository nhiều hơn. Vì vậy **không thêm `-U` vào một benchmark warm-cache nếu không định đo chính sách update đó**.

Ghi nhận mỗi run có dùng `-U` hay không. Cùng project/version nhưng khác flags update policies sẽ không cùng điều kiện so sánh.

## 32. Sự khác biệt giữa clean build và incremental build

Lệnh:

~~~bash
./mvnw -B -ntp clean verify
~~~

thường làm sạch `target/` trước khi chạy lifecycle nên Compiler phải viết lại outputs.

Lệnh:

~~~bash
./mvnw -B -ntp verify
~~~

trên source/build output đã warm có thể tận dụng incremental behavior (ví dụ Compiler Plugin thấy không cần compile lại), nhưng nhiều plugin vẫn được gọi và một số goals vẫn làm work.

**Không lấy chênh lệch giữa `clean verify` và `verify` làm “resolution time”.** Chênh lệch lớn có thể nằm ở compiler resources, JAR packaging hoặc test goals.

Muốn đo incremental build, báo rõ:

- Source files có thay đổi hay không.
- `target/` có tồn tại trước lệnh không.
- Các plugins có thực hiện incremental checks hay luôn chạy lại không.
- Tests có vẫn chạy không.
- Annotation processors/code generators có tạo outputs mới không.

## 33. skipTests khác maven.test.skip

Để ước lượng tác động thực thi tests trong project, có thể chạy:

~~~bash
./mvnw -B -ntp clean package -DskipTests
~~~

Với Surefire Plugin được cấu hình theo ví dụ, `skipTests` bỏ **chạy unit tests**, nhưng thường vẫn **compile test sources**.

Khác với:

~~~bash
./mvnw -B -ntp clean package -Dmaven.test.skip=true
~~~

Theo tài liệu Maven Compiler/Surefire, `maven.test.skip=true` bỏ **cả test compilation và test execution** theo những plugins hỗ trợ.

**Đừng dùng lệnh skip tests làm kết quả QA release.** Đây là phép thí nghiệm chẩn đoán chi phí, không phải cách thay thế cổng chất lượng.

### Cẩn thận với Failsafe

Trong các phiên bản Surefire/Failsafe mới, `-DskipTests` có thể **chỉ** điều khiển Surefire unit tests, còn Failsafe integration tests cần property riêng như `skipITs`. Behavior phụ thuộc versions và configuration. Kiểm tra goals thực chạy, đừng suy rằng một cờ sẽ bỏ mọi test trong toàn reactor.

## 34. Một bảng thí nghiệm công bằng

| Case | Command/điều kiện | Điều cần quan sát |
| --- | --- | --- |
| A | Wrapper `-version` khi distribution đã cached | Launcher/JVM baseline tương đối |
| B | `-N validate` ở POM không bind goals validate | Model preparation gần mức tối thiểu |
| C | `clean verify` với local repo thí nghiệm **trống** | Cold artifact downloads + plugin work |
| D | `clean verify` lặp lại trên **cùng repo đã warm** | Cùng build work, ít downloads hơn |
| E | `verify`, giữ `target/` và source không đổi | Incremental behavior |
| F | `-o clean verify` với repo đã đủ artifacts | Offline artifact resolution, vẫn chạy plugins |
| G | `clean package -DskipTests` | Tránh chạy Surefire unit tests |
| H | `clean package -Dmaven.test.skip=true` | Tránh compile/chạy tests theo hỗ trợ plugin |
| I | `dependency:go-offline` riêng | Work của prefetch goal, không coi là miễn phí |
| J | `-T 1C clean verify` trên multi-module reactor | Lợi ích/chi phí của parallel module scheduling |

Không bắt buộc chạy mọi case. Chọn cases tương ứng bottleneck, chạy từng case nhiều lần và **giữ những biến còn lại nhất quán**.

## 35. Ghi kết quả benchmark mà không bịa số

Bảng kết quả nên có:

| Trường | Giá trị ghi thật |
| --- | --- |
| Project/revision | Git commit hoặc source fingerprint |
| Maven CLI command | Full command và cờ |
| Maven version | Output của `./mvnw -version` |
| JDK version/vendor | Version, vendor, path nếu được phép ghi |
| OS/architecture | Runner type, CPU count, filesystem |
| Repository cache | Cold/warm, đường dẫn isolated repo |
| Maven Wrapper cache | Cached hay download lần đầu |
| Network/repository | Mirror/proxy/remote policies, không lộ secrets |
| POM/profiles/reactor | Active profiles, modules, goals |
| Build output | `target/` mới clean hay đã warm |
| Exit code | Bắt buộc bằng 0 mới tính success benchmark |
| Wall time | Số giây từ stopwatch/time của từng run |
| Runs | Số lần lặp, median, min/max hoặc spread |
| Download log evidence | URL/artifact count/size theo thông tin được phép |
| Bottleneck hypothesis | Startup/resolution/plugin execution và bằng chứng |

**Không cần điền số giả 1.2s, 8.3s hoặc “tăng 40%”** nếu chưa có lần chạy thật. Một bảng hoàn chỉnh về mặt phương pháp nhưng chưa đo chỉ nên để trống giá trị benchmark, không giả làm số liệu production.

## 36. Vì sao nên dùng median nhiều runs?

Wall-clock có nhiễu:

- CI runner chia sẻ CPU với job khác.
- Máy đang antivirus scan hoặc index files.
- Network jitter và remote repository latency.
- JIT, OS page cache, filesystem cache.
- Repository server rate limit.
- Plugin test order/race conditions.

Một run bất thường không nên quyết định optimization. Dùng ví dụ **5 runs cùng điều kiện** sau khi warm-up khi cần:

1. Giữ JDK/Maven/POM/flags cố định.
2. Không thay files/source giữa runs.
3. Chọn một cache condition rõ.
4. Ghi cả exit code và wall time từng lần.
5. Báo **median** (thời gian giữa sau khi sắp xếp), cùng min/max.
6. Nếu có nhiều outliers, kiểm tra môi trường trước khi kết luận.

Cũng không nên loại bỏ run chậm một cách tùy ý chỉ để số đẹp hơn; phải ghi rõ outlier rule trước khi phân tích.

## 37. Project một module với -T: thường không được lợi

Maven hỗ trợ:

~~~bash
./mvnw -B -ntp -T 1C clean verify
~~~

Trong CLI Maven, `1C` biểu thị mức thread song song tương ứng số CPU cores theo cú pháp option. Tùy version, cách scheduler và các plugin execution có thể khác.

**Ý quan trọng:** `-T` chủ yếu tạo cơ hội chạy **các reactor modules độc lập song song**. Nếu project chỉ có **một module**, không có nhiều module sẵn sàng chạy thì không có điều kỳ diệu nào khiến một `compiler:compile` goal tự chạy nhanh gấp nhiều lần.

Trong multi-module:

- Build graph giới hạn mức song song.
- Plugin cần thread-safe nếu dự án muốn hỗ trợ parallel builds an toàn.
- Parallel builds làm log interleaving khó đọc hơn.
- RAM, disk I/O và Maven repository contention có thể trở thành bottleneck mới.
- Tổng CPU time của modules có thể cao hơn wall-clock time vì có concurrency.

Dùng `-T` sau khi đo bottleneck và kiểm tra build/test thread safety, không phải công tắc mặc định cho mọi repository.

## 38. Maven Daemon (mvnd) và startup overhead

Apache Maven Daemon (`mvnd`) là công cụ riêng có thể giữ một tiến trình dài sống để giảm overhead khởi tạo và tận dụng caches trong các lần build tương tác.

Nhưng cần phân biệt:

- Nó không đồng nghĩa một option của Maven CLI tiêu chuẩn.
- Nó không tự sửa plugin goal chậm vì test/integration work.
- Nó có thể khác Maven standard invocation ở environment, logging, resource lifecycle và bản Maven Core đi kèm.
- Khi so benchmark, phải ghi rõ `mvnd` vs `mvn/./mvnw` và daemon hot/cold.
- Kết quả build cần xác minh tính tương thích và đúng Java/Plugin versions.

Đừng tuyên bố `mvnd` luôn nhanh hơn cho CI một-shot hoặc khi bottleneck chính là remote downloads; hiệu quả phụ thuộc workflow.

## 39. Resolution thất bại và plugin execution thất bại

| Log/error | Nhóm gợi ý | Điều cần kiểm tra |
| --- | --- | --- |
| `Could not resolve dependencies for project` | Project dependency resolution | GAV, repository, network, credentials, checksum |
| `Plugin ... or one of its dependencies could not be resolved` | Plugin resolution | Plugin version, pluginRepositories, mirror/cache |
| `Non-resolvable parent POM` | Model/parent resolution | parent coordinates, relativePath, repository |
| `Failed to read artifact descriptor` | POM/metadata resolution | Remote POM, corruption, repo policy |
| `No compiler is provided in this environment` | Plugin execution/toolchain | JDK vs JRE, JAVA_HOME |
| `Compilation failure` | Compiler goal execution | Source/API/compiler options |
| `There are test failures` | Surefire/Test execution | Tests, reports, environment |
| `NoClassDefFoundError` trong test | Test classpath/runtime | Missing test/runtime dependency |
| `BUILD SUCCESS` nhưng quá chậm | Cần đo riêng | Caches, plugins, code generation, external I/O |

Lỗi ở giai đoạn resolution có thể xảy ra trước khi goal chạy. Lỗi Compile goal xảy ra sau khi compiler plugin và classpath đã đủ để bắt đầu.

**Không chỉ nhìn dòng cuối cùng `BUILD FAILURE`.** Tìm đoạn lỗi đầu tiên có nguyên nhân cụ thể và mục tiêu đang chạy.

## 40. Quy trình chẩn đoán nhanh theo triệu chứng

### Tình huống A — máy mới chậm, máy cũ nhanh

1. Ghi Maven Wrapper distribution cache state.
2. Ghi Maven local artifact repository cold/warm.
3. Xem log `Downloading from ...` và `Downloaded from ...`.
4. Kiểm tra mirror/proxy, disk/antivirus.
5. Dùng cùng JDK/Maven version và commands.
6. So lần thứ nhất và thứ hai **cùng `clean verify`**.

Khả năng cao có yếu tố resolution/download, nhưng vẫn cần dữ liệu, không kết luận chỉ vì máy mới.

### Tình huống B — lần nào cũng chậm ở Surefire

1. Xem test report XMLs trong `target/surefire-reports`.
2. Kiểm tra số tests, test initialization và thời gian từng testcase.
3. Xem forkCount/reuseForks, test JVM flags.
4. Kiểm tra testcontainers/DB/network dependencies.
5. Thử skipTests như thí nghiệm, sau đó **khôi phục tests** cho build chuẩn.
6. Nếu nhiều suites có shared setup, tối ưu test design/test lifecycle, không xóa cache Maven.

### Tình huống C — build tới compile chậm nhưng không download

1. Xem `compiler:compile` goal và logs.
2. Kiểm tra số source files, annotation processors.
3. Kiểm tra incremental vs clean.
4. Kiểm tra JDK/compiler flags, memory/GC.
5. Dùng compiler-specific profiling khi cần.
6. Không nhầm “không có downloads” với “không có resolver work”.

### Tình huống D — multi-module nhiều thời gian

1. Vẽ reactor dependency graph.
2. Xem module nào nằm trên critical path.
3. Kiểm tra custom goals và thread safety.
4. Thử `-T` có kiểm soát nếu CI/resources cho phép.
5. Đọc log interleaving cẩn thận; dùng profiler/instrumentation nếu cần.
6. Đừng so sum CPU time các modules với elapsed wall time rồi kết luận số liệu mâu thuẫn.

## 41. Một case đặc biệt: plugin tự tải external tools

Ví dụ code generator có thể:

- Resolve Maven plugin JAR.
- Tải JDK toolchain/protoc binary riêng.
- Tải remote schemas.
- Generate source files.
- Chạy compiler.

Nếu mất 30 giây, đó có thể là:

~~~text
Maven plugin resolve       (repository)
External generator download (plugin-specific network)
Generator execution         (CPU/I/O)
Compiler execution          (CPU)
~~~

Đây là lý do phân loại ba tầng chỉ là **khung sơ bộ**. Cần thêm tầng external I/O trong plugin, thay vì tuyên bố mọi network activity đều là Maven dependency resolution.

Nếu plugin tải dữ liệu từ nơi khác, Maven `-o` có thể không ngăn được network call của nó; phải xem tài liệu plugin/launcher riêng.

## 42. Ghi log ra file để phân tích mà không che stdout

Maven hỗ trợ option `-l`:

~~~bash
./mvnw -B -ntp -l target/build-info.log clean verify
~~~

Nếu log path nằm trong `target/` **và** lệnh chạy `clean`, có nguy cơ Maven Clean Plugin xóa directory chứa file log trong quá trình build. Vì vậy khi benchmark và cần log bền, ưu tiên đặt file **ngoài `target/`**, ví dụ:

~~~bash
./mvnw -B -ntp -l build-measurement.log clean verify
~~~

Sau khi đo, có thể grep những dòng goal và transfer:

~~~bash
grep -E 'Downloading from|Downloaded from|--- .*:.*:.* @|BUILD SUCCESS|Total time' build-measurement.log
~~~

Đây là công cụ **sàng lọc thông tin**, không phải profiler duration chính xác. Maven log formats thay đổi theo version, và bạn phải che secrets/nội dung nhạy cảm trước khi chia sẻ.

**Đừng chạy `-l build-measurement.log` nhiều lần song song ghi cùng file.** Mỗi run nên có log path riêng.

## 43. Khi cần profiling chính xác hơn

Một phép đo wall time và Maven INFO log đủ để phát hiện “lần đầu tải rất nhiều artifacts” nhưng **không đủ** để tách exclusive CPU/I/O của các methods/plugin goals.

Lựa chọn sâu hơn tùy nhu cầu:

- **JDK Flight Recorder (JFR)** hoặc profiler được hỗ trợ cho JVM Maven, để xem CPU, allocations, GC, thread blocking.
- Instrumentation riêng trong plugin hoặc build extension đo boundaries/goals.
- Maven/CI build scan profiler phù hợp, nếu được tổ chức chấp thuận.
- So output/report của Surefire để tìm test bottlenecks.
- Phân tích network proxy/repository server metrics khi remote downloads là nghi vấn.
- OS disk/process telemetry nếu antivirus/filesystem là nguyên nhân.

Khi dùng JFR, nhớ: Surefire có thể **fork JVM riêng**, nên profile Maven JVM **không tự** đo CPU của forked test JVM. Cần instrument đúng process. Tương tự external generator executable không nằm trong Maven JVM.

**Không coi debug log `-X` là JFR**. Nó chủ yếu là text logging.

## 44. Những tối ưu nên thử sau khi biết bottleneck

| Nếu chủ yếu chậm vì… | Biện pháp có cơ sở | Cảnh báo |
| --- | --- | --- |
| Wrapper tải Maven mỗi lần | Pin distribution, cache wrapper downloads trong CI | Verify checksums; đừng share cache không tin cậy |
| Parent/plugin/dependency downloads | Trusted repository mirror/proxy, cache artifacts | Không vô hiệu hóa checksum/policy |
| SNAPSHOT metadata checks | Pin releases, review update policy | Không dùng stale SNAPSHOT cho release |
| Disk cache I/O | SSD, local repo gần filesystem, exclude path hợp lý theo security policy | Không vô hiệu hóa bảo vệ máy tùy tiện |
| Compiler goal | Incremental build, Java source/processor optimization | Vẫn cần clean build trong release gate |
| Resources goal | Tránh filtering thừa, giảm số file rất lớn | Đừng bỏ resources cần runtime |
| Surefire/test startup | Tối ưu test fixtures, reuse forks có kiểm soát, test grouping | Không được làm tests phụ thuộc trạng thái chung |
| Integration tests | Isolate external services, quản lý test environment | Không thay bằng skip trong release |
| Multi-module critical path | `-T` có kiểm soát, giảm module coupling | Thread-safe plugins và RAM |
| Code generation | Pin/cache tool binaries, incremental generators | Tránh generated output stale |
| Log output | `-ntp` và hợp lý verbosity | Ẩn log không làm resolver biến mất |

Tối ưu có giá trị phải được chứng minh bằng **trước/sau có cùng điều kiện**, không chỉ bằng cảm nhận.

## 45. Các anti-pattern về performance

### Xóa toàn bộ Maven repository

Không nên xóa `~/.m2/repository` thường xuyên; điều đó làm cold downloads tăng lên và có thể ảnh hưởng nhiều dự án cùng máy.

### Luôn thêm -U

`-U` có ích khi cần cập nhật metadata/SNAPSHOT thật, nhưng có thể tăng remote checks. Không coi đó là “tăng tốc”.

### Luôn dùng -o cho CI

Offline có thể làm build fail nếu artifact chưa được cached. Đối với release build, phải hiểu chính sách repository và verify inputs trước.

### Luôn bỏ tests

`-DskipTests` có thể làm thí nghiệm ngắn hơn, nhưng không chứng minh build chất lượng tương đương. Release phải có test policy rõ.

### Tăng -T càng nhiều càng tốt

Một project đơn module không tự tăng tốc đáng kể; trong multi-module, quá nhiều threads có thể tranh RAM/disk/network.

### Đo khi đang chạy -X

Debug logging thay đổi workload; phù hợp diagnostic hơn benchmark.

### So cold và warm không ghi điều kiện

Kết luận “Maven nhanh gấp đôi” khi một case tải 100 dependencies còn case kia cached không giải thích plugin performance.

## 46. Khi nào cần sửa POM, khi nào sửa CI?

| Bằng chứng | Nơi ưu tiên xem |
| --- | --- |
| Parent/BOM không resolve | POM coordinates + settings/mirror |
| Plugin version floating | POM pluginManagement/build/plugins |
| Thousands of small resources | Resources plugin configuration và source layout |
| Compiler chạy lại dù source không đổi | Compiler plugin incremental strategy |
| Surefire fork liên tục/chậm | Surefire configuration, test design |
| CI mỗi job có repo rỗng | CI cache/proxy and isolation policies |
| Runtime JDK khác nhau | Maven Wrapper/JDK toolchain/CI image |
| Network tới Maven Central chậm | Repository mirror, proxy, organization network |
| Module build chạy nối tiếp không cần thiết | Reactor graph và -T |
| CPU/GC cao | JDK memory flags, GC/profiler |

Không thêm plugin “tối ưu” ngẫu nhiên chỉ vì thấy một bài blog. Mỗi thay đổi phải gắn với bottleneck đã được đo và chạy regression tests.

## 47. Một báo cáo root-cause mẫu không bịa số

**Hiện tượng:** “Trên CI runner mới, build Maven lần đầu chậm hơn lần thứ hai.”

**Giả thuyết ban đầu:** artifact cache lạnh gây remote downloads.

**Bằng chứng cần thu thập:** Maven/JDK versions; POM/revision; local Maven repo path; log Downloading/Downloaded; wall time của 5 runs cold vs warm; cùng `clean verify`, giữ network/profile ổn định.

**Phép thử:** chạy cùng Maven project qua repository riêng lúc trống, rồi lần hai sử dụng cùng repository. So downloaded artifact count, build success và wall-clock distribution.

**Điều có thể kết luận nếu bằng chứng phù hợp:** cold artifact resolution là một yếu tố đóng góp. Không tuyên bố biết chính xác nó chiếm bao nhiêu phần trăm nếu chưa có instrumentation.

**Biện pháp:** cấu hình trusted repository proxy và warm cache theo CI policy; có cách rebuild sạch để phát hiện hidden dependencies.

**Xác minh sau thay đổi:** run lại build trên môi trường có kiểm soát; lưu raw measurements, không dựa vào câu “cảm thấy nhanh hơn”.

## 48. Hướng dẫn chọn phép thử đầu tiên

Có thể dùng quy tắc:

1. **Lâu trước khi thấy goal đầu tiên?** Xem Wrapper, Maven/JVM startup, POM/parent/BOM, plugin resolution.
2. **Nhiều Downloading từ repository?** Xem cache, mirror, network, repo policy.
3. **Goal Compiler/Surefire chạy rất lâu dù không download?** Xem source, annotation processor, tests và test forks.
4. **Có `BUILD SUCCESS` nhưng lặp lại vẫn lâu?** Đo clean vs incremental và test behavior.
5. **Nhiều modules?** Xem reactor critical path và parallel execution.
6. **Chỉ chậm trên CI?** So JDK/CPU/disk/cache/settings/profiles giữa CI và máy dev.
7. **Offline build fail?** Thu thập artifact/plugin thiếu; không tự kết luận Maven bị lỗi.
8. **Một command có nhiều goals?** Tách thành thí nghiệm có cùng prerequisites để xác định vùng chậm.
9. **Muốn số chính xác từng stage?** Thêm instrumentation, kiểm soát overlap và JVM forks.

Mục tiêu không phải “tạo nhiều benchmark”, mà là **một thí nghiệm đủ mạnh để bác bỏ hoặc xác nhận giả thuyết cụ thể**.

## 49. Checklist đo Maven công bằng

- [ ] Ghi project revision và POM/parent version.
- [ ] Ghi Maven/JDK/Wrapper versions.
- [ ] Ghi OS/CPU/architecture và CI runner context.
- [ ] Ghi active profiles, modules và full command.
- [ ] Phân biệt `mvn` với `./mvnw` và wrapper cache state.
- [ ] Phân biệt local artifact repo trống/ấm và `target` trống/ấm.
- [ ] Không xóa Maven cache người dùng.
- [ ] Dùng `-B -ntp` nhất quán nếu cần logs CI sạch.
- [ ] Không dùng `-X` trong benchmark chính.
- [ ] Ghi exit code; không lấy failed build duration làm successful build throughput.
- [ ] Ghi wall-clock của từng run, không tự tạo số giả.
- [ ] Chạy nhiều lần, báo median và mức phân tán.
- [ ] So cùng JDK, network/repository settings và resource limits.
- [ ] Nếu có `-o`, bảo đảm local cache đã có artifacts cần thiết.
- [ ] Nếu dùng `-U`, ghi rõ snapshot/metadata policy.
- [ ] Nếu dùng `-DskipTests`, không gọi output là quality-gated release build.
- [ ] Không trộn clean và incremental trong cùng nhóm benchmark.
- [ ] Không trộn single-module và multi-module reactor throughput.
- [ ] Phân biệt plugin downloads với plugin execution.
- [ ] Phân biệt Maven JVM và Surefire forked JVM.
- [ ] Xác minh compiler/test/package goals thực sự chạy.
- [ ] Nhận diện plugins có external network I/O.
- [ ] Nếu dùng -T, đánh giá log interleaving/parallel critical path.
- [ ] Nếu so mvnd, ghi trạng thái daemon và không so lẫn với Maven CLI.
- [ ] Không cộng inclusive durations thành một con số “breakdown” giả.
- [ ] Giữ logs có thể audit; redact secrets/internal endpoints.
- [ ] Khi tối ưu, đo lại cùng workflow và chạy tests.
- [ ] Không giảm dependency verification/security để đổi lấy tốc độ.
- [ ] Phân biệt performance optimization với correctness trade-off.
- [ ] Báo cáo bất kỳ blocker/caveat của phép đo.

## 50. Bài tập tự kiểm tra có đáp án

1. **Maven chậm có đồng nghĩa Compiler Plugin chậm?**  
   Không. Có thể do launcher, model, resolution, tests hoặc plugin khác.

2. **Wrapper lần đầu tải Maven thuộc loại chi phí nào?**  
   Bootstrap/distribution download; không phải Compiler execution.

3. **`mvn -version` có load và compile project không?**  
   Không; chủ yếu hiển thị Maven/JDK information.

4. **`mvn -N validate` có phải thuần JVM startup không?**  
   Không; có model/parent resolution và goals bind ở validate nếu có.

5. **Parent POM được resolve ở giai đoạn nào?**  
   Trong model construction, có thể trước plugin execution.

6. **BOM import có thể làm build mạng chậm trước compile không?**  
   Có, khi POM/metadata chưa cached.

7. **Một project không dependencies vẫn có thể download plugin?**  
   Có, Maven lifecycle plugins cần artifacts của chúng.

8. **Plugin dependencies có cùng graph với project dependencies không?**  
   Không, plugin realm/classpath khác.

9. **Warm cache có nghĩa resolution CPU time bằng 0?**  
   Không, Maven vẫn tính graph/tra cứu local artifacts.

10. **`-ntp` có tắt download không?**  
    Không, chỉ ẩn progress.

11. **`-o` làm Compiler/Surefire không chạy?**  
    Không, nó thay Maven remote repository resolution mode.

12. **`-o` có đảm bảo mọi plugin tự ngừng external network calls?**  
    Không.

13. **Go-offline có chắc mọi build tùy biến chạy offline?**  
    Không.

14. **`-U` có là cờ tăng tốc Maven không?**  
    Không, nó yêu cầu kiểm tra snapshot/missing-release updates.

15. **Maven `-X` dùng tốt cho benchmark thường xuyên không?**  
    Không, debug logs tạo overhead; dùng để chẩn đoán riêng.

16. **`clean verify` khác `verify` thế nào?**  
    Clean xóa outputs trước build; verify không tự xóa outputs.

17. **`-DskipTests` bỏ test compilation không?**  
    Với Surefire/Compiler behavior điển hình, không; nó bỏ chạy unit tests.

18. **`-Dmaven.test.skip=true` ảnh hưởng điều gì?**  
    Bỏ compile và chạy tests theo Compiler/Surefire/Failsafe support.

19. **Tại sao không dùng skip tests thay QA release?**  
    Vì test coverage bị mất.

20. **Surefire có thể fork JVM riêng?**  
    Có, tùy configuration.

21. **JFR chỉ gắn Maven JVM có đo được forked Surefire JVM không?**  
    Không trực tiếp; cần instrument đúng process.

22. **Một Maven goal log có cung cấp duration chính xác tự động?**  
    Không; thường chỉ biết goal bắt đầu.

23. **Số nào là wall-clock từ bên ngoài process?**  
    Thời gian `real` hoặc Stopwatch elapsed.

24. **Vì sao tổng CPU time có thể lớn hơn wall-clock?**  
    Parallel tasks/threads có thể dùng nhiều CPU cùng lúc.

25. **`-T 1C` có tự làm single-module compile song song?**  
    Không; reactor parallelism cần modules độc lập.

26. **Maven Daemon giúp nhóm chi phí nào nhiều nhất về lý thuyết?**  
    Launcher/JVM/Maven startup overhead cho các lần chạy lặp.

27. **Nếu log tải nhiều JAR, nhóm nào cần điều tra trước?**  
    Artifact/plugin resolution và repository cache/network.

28. **Nếu no downloads nhưng Surefire chậm?**  
    Xem tests, forks và test environment.

29. **Nếu Maven chạy trên máy mới chậm chỉ một lần?**  
    Kiểm tra distribution/cache/OS warming trước khi sửa POM.

30. **Lab Java main in dòng gì?**  
    `maven-cost:READY`.

31. **Library runtime của lab?**  
    `org.apache.commons:commons-lang3:3.14.0`.

32. **Thư viện test của lab?**  
    `org.junit.jupiter:junit-jupiter:5.11.4`.

33. **Lệnh đo startup/project preparation sơ bộ?**  
    `./mvnw -B -ntp -N validate`, nhưng không gọi là “startup thuần”.

34. **Một run chậm có chứng minh regression?**  
    Không; cần repeated measurements và kiểm soát biến.

35. **Có thể lấy thời gian hai stages inclusive cộng thành T_total?**  
    Không, có thể double-count hoặc overlap.

36. **Cách an toàn thử cold Maven artifact cache?**  
    Dùng một `-Dmaven.repo.local` riêng, không xóa repo chung.

37. **Nếu offline fail vì plugin thiếu, điều gì được chứng minh?**  
    Cache chưa đủ cho workflow đó, không phải Compiler chậm.

38. **Thông điệp quan trọng nhất của bài?**  
    Chẩn đoán startup, resolution và plugin execution **bằng chứng cứ riêng**, rồi mới tối ưu đúng bottleneck.

## 51. Tài liệu chính thức

- [Apache Maven — Maven CLI Options Reference 3.9.9](https://maven.apache.org/ref/3.9.9/maven-embedder/cli.html): `-B`, `-ntp`, `-o`, `-X`, `-U`, `-N`, `-T`, `-l`.
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): phases, goals và execution order.
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): transitive deps, scopes, mediation.
- [Apache Maven — Guide to Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html): reactor order và module dependencies.
- [Apache Maven — Maven Wrapper](https://maven.apache.org/tools/wrapper/): Maven distribution bootstrap và wrapper scripts.
- [Apache Maven — Maven Settings Reference](https://maven.apache.org/settings.html): localRepository, mirrors, proxies, profiles, servers.
- [Apache Maven Dependency Plugin — go-offline](https://maven.apache.org/plugins/maven-dependency-plugin/go-offline-mojo.html): prefetch project/plugin/report dependencies.
- [Apache Maven Dependency Plugin — tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): inspect resolved graph.
- [Apache Maven Compiler Plugin — compile](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html): compile goal và compiler parameters.
- [Apache Maven Resources Plugin — resources](https://maven.apache.org/plugins/maven-resources-plugin/resources-mojo.html): resource copying/filtering.
- [Apache Maven Surefire Plugin — surefire:test](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html): unit-test goal.
- [Apache Maven Surefire Plugin — Skipping Tests](https://maven.apache.org/surefire/maven-surefire-plugin/examples/skipping-tests.html): `skipTests` vs `maven.test.skip`.
- [Apache Maven Surefire Plugin — Fork Options](https://maven.apache.org/surefire/maven-surefire-plugin/examples/fork-options-and-parallel-execution.html): forkCount/reuseForks.
- [Apache Maven JAR Plugin](https://maven.apache.org/plugins/maven-jar-plugin/): artifact packaging.
- [Apache Maven Daemon](https://maven.apache.org/tools/mvnd/): daemon-style Maven workflow.

**Kết luận:** Khi đo Maven, hãy tách **bootstrap/model preparation**, **artifact/plugin resolution** và **plugin goal execution** thành những giả thuyết chẩn đoán riêng. `-version`, `validate`, `clean verify`, `-o`, `go-offline` và test skipping mỗi loại thay đổi một phần workload khác nhau; không có cờ nào tự trả một “biểu đồ phần trăm” chính xác cho mọi project. Chỉ tối ưu sau khi có wall-clock measurements lặp lại, log có bằng chứng và một phép so công bằng.

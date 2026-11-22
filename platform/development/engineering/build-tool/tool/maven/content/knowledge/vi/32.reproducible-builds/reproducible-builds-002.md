# Cố định Wrapper, JDK, phiên bản plugin và tập phụ thuộc trong Maven

## 1. Mục tiêu: build tái lập không chỉ là “trên máy tôi chạy được”

Một dự án Java có thể build thành công hôm nay nhưng thất bại hoặc tạo ra JAR khác vào ngày mai, dù source code trong Git không đổi. Nguyên nhân có thể là phiên bản Maven khác, JDK khác, Maven plugin không được ghim version, dependency range, SNAPSHOT được cập nhật, repository mirror, môi trường hệ điều hành hoặc timestamp tự động trong JAR.

**Build tái lập (reproducible build)** theo nghĩa nghiêm ngặt: với cùng source, build instructions và môi trường đã quy định, những người khác nhau có thể tạo **artifact byte-for-byte giống nhau**. Đây là một mục tiêu mạnh hơn việc build chỉ “thành công” hoặc code chạy giống nhau.

Để tiến tới mục tiêu đó với Maven, cần quản lý **ít nhất bốn lớp phiên bản**:

1. **Maven Wrapper**: khóa phiên bản chính xác của Maven launcher/distribution mà team dùng.
2. **JDK**: kiểm soát JDK dùng để chạy Maven, biên dịch Java và chạy tests; đừng nhầm Java target release với JDK đang sử dụng.
3. **Maven plugins**: khai báo version của Compiler, Surefire, Resources, JAR, Clean, Failsafe, Shade… theo các goals thực sự dùng.
4. **Dependency graph**: ghim direct dependencies, quản lý transitive versions qua BOM/dependencyManagement và tránh dynamic versions không được kiểm soát.

Để đạt mức **byte-for-byte reproducibility**, còn cần:

- Kiểm soát file timestamps/ZIP metadata và nội dung sinh tự động.
- Kiểm soát build profiles, settings, properties, encoding, OS/locale/time zone khi có ảnh hưởng.
- Kiểm soát annotation processors, code generators, toolchain và external tools.
- Xác minh hash artifact qua những lần build độc lập, không chỉ đọc `BUILD SUCCESS`.
- Bảo vệ integrity của Maven distribution/plugins/dependencies và giữ build provenance.

Bài này tập trung vào **cố định Wrapper, JDK, plugin versions và tập phụ thuộc**, rồi chỉ rõ chúng đóng góp vào reproducibility thế nào. Ví dụ sử dụng Maven **3.9.9**, Apache Maven Wrapper Plugin **3.3.4**, **JDK 17**, Java 17, JUnit Jupiter và Maven Enforcer. Những bản ghim là **giá trị của ví dụ**, không phải lời khẳng định phiên bản mới nhất.

## 2. Repeatable, reproducible và hermetic khác nhau

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Build thành công | Maven trả exit code 0 | `mvn package` ra JAR |
| Repeatable trên một máy | Lặp lại cùng môi trường cho kết quả nhất quán | Build hai lần trong CI runner cũ |
| Reproducible byte-for-byte | Cùng source/instructions/môi trường đã quy định cho artifact bytes giống nhau | SHA-256 của hai JAR trùng |
| Hermetic build | Build hạn chế các inputs ngoài tập đã khai báo, network/OS side effects bị kiểm soát | Build dùng pinned toolchain và repository mirror/cached inputs |
| Verifiable release | Có cách độc lập đối chiếu binary phát hành với source/build instructions | Rebuild và compare digest/artifact contents |

**Không được suy ra** “đã dùng Maven Wrapper” là JAR chắc chắn byte-identical. Wrapper chỉ kiểm soát **Maven distribution**. Một compiler plugin dùng timestamp hệ thống hoặc dependency SNAPSHOT thay đổi vẫn có thể tạo binary khác.

Một kiểm tra hash trùng trên cùng laptop cũng **không đủ** để chứng minh independent reproducibility, vì hai build có thể cùng dùng local cache, toolchain hoặc hidden inputs. Đó là một phép thử hữu ích ban đầu, không phải chứng chỉ cuối cùng.

## 3. Tại sao Maven version phải được cố định?

Maven là một build engine. Các version khác nhau có thể có khác biệt về:

- Maven Core, model building và dependency resolution.
- Default lifecycle/plugin bindings.
- Xử lý reactor multi-module, profiles, properties và errors.
- Maven Resolver/transport behavior.
- Cơ chế reproducible builds mặc định ở bản mới.
- Cách xử lý invalid POM và những trường hợp dependency graph đặc biệt.

Nếu developer A dùng Maven 3.9.x, CI runner dùng một bản khác, hai invocation `mvn clean verify` **không nhất thiết** có cùng tools.

**Maven Wrapper** cho phép project tự khai báo bản Maven mong muốn. Team gọi cùng scripts `./mvnw` hoặc `mvnw.cmd` thay vì mỗi người chọn `mvn` đang có trên PATH.

## 4. Maven Wrapper gồm những gì?

Các file cơ bản trong một dự án có Wrapper loại `only-script`:

~~~text
reproducible-lab/
├── mvnw
├── mvnw.cmd
├── .mvn/
│   └── wrapper/
│       └── maven-wrapper.properties
├── pom.xml
└── src/
~~~

- `mvnw`: script cho Unix-like shells.
- `mvnw.cmd`: script cho Windows.
- `.mvn/wrapper/maven-wrapper.properties`: chứa URL/thông tin Maven distribution cần chạy.
- Khi khởi động, wrapper tải Maven distribution nếu cache chưa có, sau đó chạy đúng bản đã chỉ định.

**Không phải mọi Wrapper đều chứa `maven-wrapper.jar`.** Loại `only-script` trong Apache Maven Wrapper hiện đại chỉ cần scripts và properties, tải Maven distribution trực tiếp. Các loại khác như `bin`, `source` và `script` có layout/bootstrap riêng.

Wrapper vẫn cần Java và môi trường có thể tải (hoặc đã cache) distribution. Nó không phải Java installer.

## 5. Tạo Wrapper khóa Maven 3.9.9

Bạn cần Maven được cài sẵn **một lần** để khởi tạo wrapper trong project chưa có Wrapper:

~~~bash
mvn -N org.apache.maven.plugins:maven-wrapper-plugin:3.3.4:wrapper -Dmaven=3.9.9 -Dtype=only-script
~~~

Trong lệnh trên:

- `-N`: không xử lý các module con của aggregator khi chỉ muốn tạo Wrapper ở root.
- `maven-wrapper-plugin:3.3.4:wrapper`: gọi phiên bản plugin cụ thể để tránh floating plugin prefix resolution lúc bootstrap.
- `-Dmaven=3.9.9`: ghim Maven distribution vào 3.9.9.
- `-Dtype=only-script`: dùng wrapper implementation không cần binary wrapper JAR trong source tree.

Sau khi tạo, đưa scripts/properties vào version control. Trên Unix-like có thể cần bảo đảm quyền executable:

~~~bash
chmod +x mvnw
git add mvnw mvnw.cmd .mvn/wrapper/maven-wrapper.properties
git update-index --chmod=+x mvnw
~~~

Các lệnh Git chỉ là **bước đề xuất trong một repository bạn được quyền sửa**; không chạy ngẫu nhiên trên project của người khác. Giữ các file wrapper nhất quán trong cùng một commit được review.

### Xác minh Wrapper

Linux/macOS:

~~~bash
./mvnw -version
./mvnw -B -ntp clean verify
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd -version
.\mvnw.cmd -B -ntp clean verify
~~~

Phần Maven version của output phải thể hiện **Apache Maven 3.9.9** nếu distribution đúng. Phần Java version có thể khác tùy máy: Wrapper **chưa** khóa JDK.

**Không tự thêm `mvnw` vào repo bằng cách viết một script tùy ý** rồi cho rằng đó là Wrapper chính thức. Dùng Maven Wrapper Plugin hoặc source phát hành tin cậy, kiểm tra files được tạo.

## 6. Nội dung Maven Wrapper properties

Ví dụ `.mvn/wrapper/maven-wrapper.properties`:

~~~properties
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip
~~~

File thực được plugin tạo ra có thể có properties bổ sung; **đừng xóa các thuộc tính đang được wrapper implementation của project cần** chỉ để làm giống đoạn ví dụ tối giản.

Nếu project đổi `distributionUrl` sang version khác, Wrapper sẽ chạy Maven version khác. Do đó:

- Review file này trong code review như bất kỳ build configuration quan trọng nào.
- Không trỏ URL tới một mirror không được kiểm soát.
- Nếu dùng internal repository proxy, kiểm tra trusted origin và download policy.
- Không dùng Maven binary từ một URL không rõ nguồn.

### Chống tampering bằng checksum

Apache Maven Wrapper hỗ trợ property:

~~~properties
distributionSha256Sum=...
~~~

và, khi dùng wrapper loại cần wrapper JAR:

~~~properties
wrapperSha256Sum=...
~~~

Dấu `...` ở đây chỉ là **ký hiệu giải thích**, KHÔNG phải cấu hình runnable. Bạn phải thay bằng **SHA-256 thật được xác minh từ nguồn phát hành/trusted distribution** trước khi thêm property vào file.

- `distributionSha256Sum` kiểm tra SHA-256 của Maven distribution đã tải.
- `wrapperSha256Sum` kiểm tra wrapper JAR khi wrapper type có sử dụng wrapper JAR.
- Với `only-script`, không có wrapper JAR để kiểm tra bằng `wrapperSha256Sum`.
- Ghim version URL mà **không xác thực checksum** vẫn để lại rủi ro binary tải về bị thay thế tại nguồn hoặc đường truyền không an toàn.
- Không tự tính checksum từ một binary vừa lấy từ nguồn không tin cậy rồi coi đó là bằng chứng supply-chain integrity.

Quy tắc an toàn: chỉ commit digest đã xác minh từ một nguồn phát hành tin cậy và review khi upgrade Maven.

## 7. Wrapper không khóa JDK: hai tầng runtime phải tách biệt

Đây là lỗi phổ biến nhất:

~~~bash
./mvnw -version
~~~

có thể in:

~~~text
Apache Maven 3.9.9
Java version: 21.x ...
~~~

dù project đang nhắm Java 17. Vì Wrapper chạy Maven 3.9.9 trên một JDK **do environment cung cấp**.

Ba khái niệm khác nhau:

1. **JDK chạy Maven**: phụ thuộc `JAVA_HOME`/PATH và launcher setup; Maven plugins thường chạy trong JVM này.
2. **JDK compiler dùng để biên dịch**: mặc định thường là compiler từ JDK chạy Maven, nhưng Maven Toolchains hoặc plugin-specific fork/toolchain có thể chọn JDK khác.
3. **Bytecode/API target**: `maven.compiler.release=17` yêu cầu compiler dùng Java 17 language/API level phù hợp. Nó không tự install/đổi JDK đang chạy Maven.

Vì vậy:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

**không đủ** để khẳng định build dùng JDK 17.

## 8. Khóa Java bytecode/API bằng --release

Với Maven Compiler Plugin có hỗ trợ, dùng:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>17</release>
    </configuration>
</plugin>
~~~

hoặc property:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Compiler Plugin truyền ý nghĩa tương đương `javac --release 17`, khi JDK/compiler hỗ trợ. Lợi ích:

- Giới hạn Java language features tương ứng release 17.
- Giới hạn visible platform APIs ở mức release đã chọn theo `javac`.
- Tạo classfile version phù hợp với Java 17.

Java 17 classfile major version thường là **61**. Có thể kiểm tra:

~~~bash
javap -verbose -classpath target/reproducible-lab-1.0.0.jar dev.learning.repro.App
~~~

Tìm dòng:

~~~text
major version: 61
~~~

**Nhưng:** `--release 17` không bảo đảm cùng Java compiler build/vendor/patch, cùng annotation processor, cùng runtime test engine hoặc cùng binary SHA-256. Để ghim toolchain nghiêm ngặt, cần kiểm soát JDK distribution và môi trường build.

## 9. Ghim JDK để chạy Maven: dùng Enforcer

Maven Enforcer Plugin có rule `requireJavaVersion`. Ví dụ:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.6.3</version>
    <executions>
        <execution>
            <id>check-build-toolchain</id>
            <phase>validate</phase>
            <goals>
                <goal>enforce</goal>
            </goals>
            <configuration>
                <rules>
                    <requireJavaVersion>
                        <version>[17,18)</version>
                    </requireJavaVersion>
                </rules>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Ý nghĩa:

- Build chỉ chấp nhận Java version trong range **từ 17, dưới 18** khi rule kiểm tra Maven runtime Java version.
- Nếu chạy Maven trên JDK 21, rule fail sớm ở `validate`.
- Nếu chạy trên JDK 17.0.4 hay 17.0.15, cả hai đều thuộc range.

**Lưu ý:** Range `[17,18)` khóa **major JDK**, không khóa vendor hoặc patch release. Nếu tổ chức cần bit-identical artifacts hoặc đồng nhất security patches, còn phải pin exact JDK image/distribution/digest trong CI.

Để bảo đảm đúng Maven version, Enforcer có rule tương tự:

~~~xml
<requireMavenVersion>
    <version>[3.9.9]</version>
</requireMavenVersion>
~~~

Dạng `[3.9.9]` biểu thị **đúng version 3.9.9** theo Maven version range rules. Đây là một lớp kiểm tra độc lập bên cạnh Wrapper: Wrapper chỉ giúp chạy đúng version; Enforcer giúp **fail** nếu ai bỏ qua Wrapper hoặc dùng runtime không phù hợp.

## 10. JDK Toolchains: compiler có thể khác Maven runtime

Một số tổ chức cần dùng JDK 21 chạy Maven, nhưng JDK 17 để compile/test module Java 17. Maven Toolchains hỗ trợ chọn JDK cho những plugins **toolchain-aware**, thay vì phụ thuộc hoàn toàn vào JVM đang chạy Maven.

Cấu trúc toolchains.xml trên máy build (đường dẫn là ví dụ, phải thay bằng JDK thật):

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>17</version>
            <vendor>temurin</vendor>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/temurin-17</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
~~~

File này thường ở `~/.m2/toolchains.xml`. Đây là **cấu hình môi trường**, không commit đường dẫn máy cá nhân vào project.

Một POM có thể yêu cầu toolchain qua Maven Toolchains Plugin theo hướng dẫn chính thức. Maven Toolchains Plugin 3.2.0 còn có cơ chế discovery và goal `select-jdk-toolchain`; behavior phụ thuộc version/configuration.

**Hai mô hình đều hợp lệ nhưng phải quyết định rõ:**

- **Mô hình A — đơn giản cho lab:** Maven runtime JDK 17, Compiler Plugin release 17, Enforcer requireJavaVersion 17. Không cần toolchains.
- **Mô hình B — CI đa JDK:** Maven chạy trên JDK tương thích, Toolchains chọn JDK 17 cho toolchain-aware plugins. Enforcer requireJavaVersion của Maven runtime phải được cấu hình phù hợp, không cố ép JDK17 runtime nếu chủ đích chạy Maven trên JDK21.

**Cảnh báo:** Không phải mọi plugin đều toolchain-aware. Một plugin có thể tiếp tục dùng JDK chạy Maven; cần kiểm tra docs, actual `java.home` và compiler/test logs. Toolchains không tự cấp exact vendor checksum hoặc kiểm soát mọi subprocess.

## 11. CI pin JDK bằng image/digest

Trong CI, cách mạnh hơn để tái lập môi trường là dùng một image build có JDK/Maven được ghim:

~~~text
JDK distribution: Temurin 17.x.y (chọn một bản cụ thể)
OS image: digest SHA-256 được duyệt
Maven: 3.9.9 qua Wrapper
Timezone: UTC
Locale: được chỉ rõ
Architecture: amd64 hoặc arm64 theo build matrix
~~~

Các giá trị `17.x.y` và SHA-256 nói trên là **mẫu checklist**, không phải dữ liệu để copy nguyên vào cấu hình chạy.

Một image tag như `eclipse-temurin:17-jdk` **có thể thay đổi** theo thời gian; nếu cần môi trường thật sự immutable, pin digest được xác minh và ghi lại version đầy đủ. Đồng thời cập nhật bản JDK có kế hoạch theo chính sách bảo mật; reproducibility không có nghĩa giữ mãi toolchain có lỗ hổng.

### So sánh mức bảo đảm

| Cơ chế | Cố định được gì? | Chưa bảo đảm |
| --- | --- | --- |
| Wrapper 3.9.9 | Maven distribution version | JDK, plugins, dependencies |
| `maven.compiler.release=17` | Java target API/classfile | JDK compiler vendor/patch |
| Enforcer `requireJavaVersion` | Maven runtime major/range | Exact JDK image digest |
| Maven Toolchains | JDK của plugins hỗ trợ toolchain | Mọi process/plugin/OS |
| Pin CI image digest | Filesystem/toolchain baseline | Network/repository volatility, runtime external inputs |
| Verify JAR SHA-256 | Byte equality cho artifact được so | Independent reproducibility nếu cả hai build dùng hidden shared inputs |

## 12. Maven plugin versions: nơi drift dễ bị bỏ sót

Giả sử POM khai báo:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
</plugin>
~~~

Nếu không có version ở đây hoặc trong effective `pluginManagement`, build có thể phụ thuộc vào Maven default lifecycle bindings hoặc plugin version resolution. Điều này không phù hợp nếu bạn muốn hiểu chính xác compiler behavior khi Maven upgrades.

**Ghim version mọi plugin thực sự dùng**:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
</plugin>
~~~

Các plugins thường cần chú ý:

- Maven Clean Plugin (clean lifecycle).
- Maven Resources Plugin (copy/filter resources).
- Maven Compiler Plugin.
- Maven Surefire Plugin (unit tests).
- Maven Failsafe Plugin (integration tests, nếu dùng).
- Maven JAR/WAR Plugin (packaging).
- Maven Shade/Assembly Plugin (fat JAR/distribution, nếu dùng).
- Maven Source/Javadoc Plugin (attached artifacts, nếu dùng).
- Maven Install/Deploy Plugin.
- Maven Enforcer Plugin.
- Plugin generate-code, annotation processing, OpenAPI/Protobuf hoặc image build được dùng.
- Plugin được gọi **trực tiếp trong CI** như Dependency/Help/Exec Plugin; nên dùng fully-qualified goal có version hoặc ghim ở POM.

Một plugin đổi version có thể thay đổi generated source, resources, ZIP entry order, manifest, test runner hoặc compiler options **ngay khi project dependencies không đổi**.

## 13. build/plugins và pluginManagement khác nhau

Hai vị trí POM cần phân biệt:

**Khai báo plugin execution trực tiếp:**

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-enforcer-plugin</artifactId>
            <version>3.6.3</version>
            <executions>
                <execution>
                    <id>quality-gate</id>
                    <phase>validate</phase>
                    <goals><goal>enforce</goal></goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

**Quản lý version/configuration cho module con:**

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

Trong parent POM:

- `pluginManagement` lưu phiên bản/cấu hình mặc định cho plugins khi được sử dụng/bind; **không có nghĩa mọi execution khai báo bên trong tự chạy**.
- `build/plugins` kích hoạt plugin được khai báo và có thể kế thừa execution xuống child modules.
- Với packaging `jar`, các standard lifecycle plugin goals có thể được bind mặc định; pluginManagement có thể cung cấp versions cho chúng.
- Với custom goal (ví dụ Enforcer), chỉ đặt version trong pluginManagement mà **không kích hoạt execution** không bảo đảm quality gate chạy.

Trong multi-module project, hãy kiểm tra `help:effective-pom` của child để biết plugin version/execution hiệu lực thật.

## 14. Chặn plugin versions không được ghim bằng Enforcer

Enforcer có rule `requirePluginVersions`. Ví dụ bổ sung vào `<rules>`:

~~~xml
<requirePluginVersions>
    <banMavenDefaults>true</banMavenDefaults>
    <banLatest>true</banLatest>
    <banRelease>true</banRelease>
    <banSnapshots>true</banSnapshots>
</requirePluginVersions>
~~~

Ý nghĩa:

- Plugin không được có version floating.
- Không dùng `LATEST`/`RELEASE` để chọn plugin.
- Không dùng SNAPSHOT plugins nếu policy cấm.
- Với `banMavenDefaults=true`, rule có thể yêu cầu project khai báo versions **ngay cả cho các plugins mặc định** lấy từ Maven lifecycle/super POM.

**Cẩn thận khi bật rule:** Nó có thể làm project cũ fail vì chưa ghim các default plugins như Resources, Clean, Install/Deploy hoặc site/reporting plugins. Cách đúng là **bổ sung version pin có chủ đích**, không để Enforcer skip vĩnh viễn.

Nếu `banMavenDefaults=false`, Maven defaults có thể được chấp nhận theo version Maven đã ghim; mức kiểm soát yếu hơn nhưng có thể là một bước chuyển tiếp. Quyết định đó cần được ghi trong build policy.

## 15. Dependency set: phải nhìn cả direct lẫn transitive

Trong POM:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.14.0</version>
</dependency>
~~~

đây là **direct dependency** có version cụ thể.

Nhưng dependency graph có thể là:

~~~text
app
├── framework-A:4.1
│   └── shared-lib:2.0
└── framework-B:5.2
    └── shared-lib:2.1
~~~

Maven **dependency mediation** chọn một version theo rules (đường dẫn gần hơn, nếu hòa độ sâu thì declaration trước thường thắng). Nếu parent/BOM/dependencyManagement can thiệp, resolved version cũng có thể khác.

**Chỉ ghim direct dependencies không phải lúc nào cũng cố định mọi transitive artifacts.** Transitive dependencies có thể mang ranges/dynamic SNAPSHOT hoặc bị thay đổi do managed versions, profiles, exclusions, repositories.

Để reproducibility tốt hơn:

1. Dùng release versions cụ thể cho direct dependencies.
2. Dùng `dependencyManagement` hoặc BOM đã ghim version để điều phối những transitive coordinates quan trọng.
3. Ghi lại resolved dependency tree và so sánh khi nâng cấp.
4. Dùng Enforcer rules để chặn ranges/dynamic versions, dependency conflicts, banned artifacts theo policy.
5. Duy trì repository immutability và checksum verification.
6. Đảm bảo CI sử dụng đúng profiles/settings/mirrors.
7. Không lệ thuộc local cache ngẫu nhiên để quyết định version được chọn.

## 16. dependencyManagement: một nguồn version truth

Trong POM hoặc parent:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Ở module con:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
    </dependency>
</dependencies>
~~~

Nếu effective dependencyManagement cung cấp version, consumer không cần lặp version ở `<dependencies>`; resolved version có thể được quản lý tập trung.

**Nhớ:**

- `dependencyManagement` không tự thêm dependency vào project.
- Nó quản lý version/scope/exclusions theo Maven model rules cho những dependencies có mặt.
- `dependencyManagement` của project **không tự pin Maven plugin dependencies**; chúng thuộc classpath plugin riêng.
- Một project có thể dùng nhiều BOM/parent, cần kiểm tra precedence/import order/effective POM.
- Không dùng `dependencyManagement` như công cụ chữa mọi incompatibility: version mới vẫn phải được test với các libraries khác.

## 17. BOM import để thống nhất một nhóm libraries

BOM (Bill of Materials) là POM chứa danh sách managed dependency versions. Có thể import:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.4.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đây là **ví dụ cú pháp BOM** (không thuộc lab runnable ở phần sau), không phải yêu cầu mọi project phải dùng Spring Boot.

Lợi ích:

- Một framework BOM pin phiên bản các libraries đã được kiểm thử cùng nhau.
- Giảm phân tán version properties ở nhiều modules.
- Thay đổi BOM version trở thành một update có thể review/kiểm thử.
- Các modules import cùng BOM có xu hướng thống nhất dependency graph.

Nhưng BOM **không tự khóa**:

- Maven Wrapper/Maven Core.
- Compiler/plugin versions nếu BOM không phải parent cấu hình plugins.
- JDK vendor/patch và môi trường CI.
- Tất cả transitive dependencies ngoài phạm vi BOM.
- Runtime dependencies được server/container cung cấp ngoài project.

**Đừng trộn một BOM release với dependency range khác không kiểm soát rồi cho rằng graph đã khóa tuyệt đối.**

## 18. Vì sao version ranges, LATEST, RELEASE, SNAPSHOT gây rủi ro?

### Version range

~~~xml
<version>[1.0,2.0)</version>
~~~

cho phép resolver lựa một version từ tập hợp dựa trên repository metadata. Khi repository có thêm release, một build sau có thể lấy version khác mà source POM không thay đổi.

### Dynamic LATEST/RELEASE

Các cách khai báo `LATEST` hoặc `RELEASE` lịch sử không phù hợp với strict reproducibility; hành vi còn phụ thuộc Maven version/metadata. **Không dùng** chúng để build release hiện đại.

### SNAPSHOT

~~~xml
<version>1.1.0-SNAPSHOT</version>
~~~

là một logical version có thể gắn với nhiều binary build. Nếu SNAPSHOT repository cập nhật, cùng source project vẫn có thể resolve binary khác ở thời điểm khác.

Trong hoạt động phát triển, SNAPSHOT có giá trị. Nhưng với release reproducibility cần phân biệt:

- Có thể cho phép SNAPSHOT ở development branch.
- Chặn SNAPSHOT/dynamic dependencies ở release branch.
- Khi bắt buộc dùng development artifact, cần record exact artifact identity/checksum và có chính sách repository retention.
- Không coi `-U` hoặc local Maven cache là “version lock”.

**Maven 3.x không cung cấp một lockfile tổng quát mặc định tương đương package-lock.json của npm** cho toàn bộ project/plugin/transitive graph. BOM và explicit pins là những thành phần quan trọng, nhưng muốn freeze toàn đồ thị để audit thường cần báo cáo cây phụ thuộc/SBOM và quy trình bổ sung.

## 19. Enforcer rules cho dependency policy

Bổ sung rules vào Enforcer configuration khi phù hợp:

~~~xml
<rules>
    <dependencyConvergence/>
    <banDuplicatePomDependencyVersions/>
    <requireReleaseDeps/>
    <banDynamicVersions/>
</rules>
~~~

Đây là **đoạn rules minh họa**, không phải ruleset mặc định bắt buộc mọi dự án.

| Rule | Mục tiêu |
| --- | --- |
| `dependencyConvergence` | Các đường dẫn tới cùng dependency nên nhất quán version |
| `requireUpperBoundDeps` | Ngăn resolved version thấp hơn requirement cao nhất theo rule |
| `banDuplicatePomDependencyVersions` | Chặn khai báo trùng GA/type/classifier trong POM |
| `requireReleaseDeps` | Không dùng SNAPSHOT dependencies khi policy yêu cầu releases |
| `banDynamicVersions` | Chặn những dạng dependency version động/range theo rule |
| `bannedDependencies` | Chặn artifacts/versions bị policy cấm |
| `requirePluginVersions` | Yêu cầu plugin versions được ghim |
| `requireMavenVersion` | Khóa Maven runtime version/range |
| `requireJavaVersion` | Khóa Java runtime version/range |

**Chú ý scope/optional/transitive semantics của từng rule.** Ví dụ convergence và bannedDependencies có các options riêng, không thể giả định mặc định giống nhau. Bật mọi rule mà không đánh giá dependency graph có thể gây false alarms hoặc block một SNAPSHOT module nội bộ chủ đích.

Cổng chất lượng nên **fail tại `validate`** với nguyên nhân rõ ràng, không bị skip trong CI release.

## 20. POM đầy đủ: dự án Java 17 với phiên bản được ghim

Project chạy độc lập:

~~~text
reproducible-lab/
├── pom.xml
├── mvnw
├── mvnw.cmd
├── .mvn/
│   └── wrapper/
│       └── maven-wrapper.properties
└── src/
    ├── main/
    │   └── java/dev/learning/repro/App.java
    └── test/
        └── java/dev/learning/repro/AppTest.java
~~~

Wrapper scripts/properties tạo bằng lệnh ở mục 5. Các source files/POM trình bày bên dưới.

### 20.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.learning.repro</groupId>
    <artifactId>reproducible-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
        <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
        <commons-lang3.version>3.14.0</commons-lang3.version>
        <junit.version>5.11.4</junit.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>${commons-lang3.version}</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
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
                <artifactId>maven-install-plugin</artifactId>
                <version>3.1.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-deploy-plugin</artifactId>
                <version>3.1.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-enforcer-plugin</artifactId>
                <version>3.6.3</version>
                <executions>
                    <execution>
                        <id>enforce-versions</id>
                        <phase>validate</phase>
                        <goals>
                            <goal>enforce</goal>
                        </goals>
                        <configuration>
                            <rules>
                                <requireMavenVersion>
                                    <version>[3.9.9]</version>
                                </requireMavenVersion>
                                <requireJavaVersion>
                                    <version>[17,18)</version>
                                </requireJavaVersion>
                                <dependencyConvergence/>
                                <banDuplicatePomDependencyVersions/>
                            </rules>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Vì sao POM này giúp ổn định build:**

1. Maven phải đúng 3.9.9 khi lifecycle chạy đến Enforcer.
2. JDK **chạy Maven** phải thuộc major 17.
3. Java compiler target `release=17`.
4. Encoding UTF-8 được khai báo.
5. `project.build.outputTimestamp` có timestamp ổn định cho những plugins hỗ trợ reproducible archive output.
6. Direct dependencies dùng versions cụ thể qua properties.
7. Maven plugins quan trọng của build và goals được dùng có versions cụ thể.
8. `dependencyConvergence` và `banDuplicatePomDependencyVersions` chặn hai nhóm graph/model problems.
9. JUnit Jupiter được khai báo `test` scope.
10. Exec Plugin được ghim để có thể chạy application qua Maven dependency classpath.

**Các giới hạn cần nói rõ:**

- POM chưa bật `requirePluginVersions` trong baseline, vì việc bật rule có thể yêu cầu kiểm kê **mọi** default/reporting plugin đang có hiệu lực. Bạn có thể thêm rule sau khi xác minh effective build.
- Mặc dù phiên bản dependency trực tiếp đã ghim, transitive graph vẫn phải được xem bằng `dependency:tree`; đây chưa phải một lockfile tuyệt đối.
- Timestamp ổn định giúp archive reproducibility, nhưng bytecode và generated files còn phụ thuộc JDK/vendor/OS và plugins.
- Không nên gọi `mvn deploy` với POM lab trừ khi bạn thật sự cấu hình và được phép publish vào repository thích hợp. Không có distributionManagement trong ví dụ.

### 20.2. App.java

File `src/main/java/dev/learning/repro/App.java`:

~~~java
package dev.learning.repro;

import java.util.Locale;
import org.apache.commons.lang3.StringUtils;

public final class App {
    private App() {
    }

    public static String message() {
        return "repro-lab:" + StringUtils.upperCase("stable", Locale.ROOT);
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

**Ý nghĩa:** sử dụng một external dependency thật (Commons Lang 3) ở compile/runtime. `Locale.ROOT` làm thao tác chuyển chữ hoa không phụ thuộc default locale của máy.

Dòng stdout **chính xác do chương trình in**:

~~~text
repro-lab:STABLE
~~~

### 20.3. AppTest.java

File `src/test/java/dev/learning/repro/AppTest.java`:

~~~java
package dev.learning.repro;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class AppTest {
    @Test
    void producesStableMessage() {
        assertEquals("repro-lab:STABLE", App.message());
    }
}
~~~

Test xác minh một behavioral output cố định. **Test PASS không chứng minh JAR byte-for-byte identical**; phép so hash ở phần sau đảm nhiệm một phần kiểm tra khác.

## 21. Chạy bài lab đúng cách

Giả sử bạn đã cài JDK 17 và Wrapper files đã được tạo rồi commit.

Linux/macOS:

~~~bash
java -version
./mvnw -version
./mvnw -B -ntp clean verify
~~~

Windows PowerShell:

~~~powershell
java -version
.\mvnw.cmd -version
.\mvnw.cmd -B -ntp clean verify
~~~

Đầu ra mong đợi về mặt ý nghĩa:

~~~text
Apache Maven 3.9.9
Java version: 17...
...
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
...
BUILD SUCCESS
~~~

Đây là **các dòng rút gọn dự kiến**, không phải transcript thực tế; Maven logs có nhiều plugin headers và paths tùy hệ điều hành.

Nếu Maven runtime là JDK21, phần Enforcer `requireJavaVersion` sẽ FAIL ở phase `validate`; không tiếp tục chạy compiler/tests. Nếu dùng Maven 3.9.8 hoặc bản 3.10.x, `requireMavenVersion` sẽ FAIL (nếu bạn chạy tới goal đó), ngay cả khi Java17 hợp lệ.

### Chạy App qua Maven dependency classpath

Linux/macOS:

~~~bash
./mvnw -B -ntp exec:java -Dexec.mainClass=dev.learning.repro.App
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd -B -ntp exec:java "-Dexec.mainClass=dev.learning.repro.App"
~~~

Ứng dụng in:

~~~text
repro-lab:STABLE
~~~

Lưu ý Maven có thể in thêm plugin logs. Stdout trên chỉ là **dòng do `App.main` in**.

## 22. Vì sao không dùng java -jar với JAR của lab?

POM tạo **plain JAR** và không đặt `Main-Class` trong manifest. Hơn nữa class `App` sử dụng `commons-lang3`, là một JAR riêng, **không được tự nhúng** vào main artifact.

Do đó:

~~~bash
java -jar target/reproducible-lab-1.0.0.jar
~~~

không phải lệnh runnable theo thiết kế demo.

Nếu muốn chạy bằng JDK launcher mà không thông qua Maven, cần classpath chứa **cả JAR ứng dụng và commons-lang3 JAR**:

Linux/macOS với local repository mặc định:

~~~bash
java -cp "target/reproducible-lab-1.0.0.jar:$HOME/.m2/repository/org/apache/commons/commons-lang3/3.14.0/commons-lang3-3.14.0.jar" dev.learning.repro.App
~~~

Windows PowerShell:

~~~powershell
java -cp "target\reproducible-lab-1.0.0.jar;$HOME\.m2\repository\org\apache\commons\commons-lang3\3.14.0\commons-lang3-3.14.0.jar" dev.learning.repro.App
~~~

Output:

~~~text
repro-lab:STABLE
~~~

Hai lệnh này **giả sử Maven local repository ở vị trí mặc định** và library JAR đã được Maven resolve. Nếu dùng custom `maven.repo.local`, đổi path tương ứng.

Nếu project cần fat JAR hoặc executable Jar, phải cấu hình Maven Shade/Assembly Plugin hoặc packaging phù hợp, **và phải ghim version của plugin ấy** để giữ reproducibility.

## 23. project.build.outputTimestamp: ổn định JAR ZIP timestamps

JAR là một ZIP archive. Nếu một plugin ghi timestamp hiện tại vào các entries, hai lần build cùng mã nguồn vẫn có thể sinh ra binary khác hash.

Trong Maven POM:

~~~xml
<properties>
    <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Plugins hỗ trợ reproducible build mode, như các Maven archiving plugins phiên bản phù hợp, có thể dùng property đó để gán archive entry timestamps ổn định.

**Thận trọng:**

- `outputTimestamp` không tự kiểm soát nội dung files do mọi plugin generate.
- Một custom plugin có thể ghi ngày hiện tại/user path/Git branch vào resources và phá byte equality.
- Cùng timestamp nhưng JDK compiler khác có thể tạo classfiles khác.
- POM/source revisions khác nhau đương nhiên có thể tạo artifacts khác nhau.
- Không đổi timestamp giữa hai build rồi kỳ vọng archive hash giống nhau.
- Bản Maven mới có cơ chế reproducible mode mặc định theo thay đổi của Maven Core, nhưng với lab Maven 3.9.9 ta **đặt property tường minh** để không phụ thuộc behavior mặc định của những version khác.

Theo hướng dẫn chính thức, reproducibility là một tập **plugin-level behaviors** và cần actual artifact comparison; không có một Maven flag duy nhất bảo đảm mọi plugin đều tạo binary giống hệt nhau.

## 24. Kiểm chứng SHA-256 qua hai lần build

Từ root project ở Linux/macOS:

~~~bash
./mvnw -B -ntp clean verify
sha256sum target/reproducible-lab-1.0.0.jar
cp target/reproducible-lab-1.0.0.jar /tmp/repro-first.jar

./mvnw -B -ntp clean verify
sha256sum target/reproducible-lab-1.0.0.jar
sha256sum /tmp/repro-first.jar
cmp /tmp/repro-first.jar target/reproducible-lab-1.0.0.jar
~~~

Nếu `cmp` trả exit code 0, hai files có nội dung giống hệt (byte equality). Hash SHA-256 phải trùng khi bytes trùng.

**Không đưa một digest giả làm expected output.** Giá trị SHA-256 cụ thể tùy build artifacts; lệnh chạy trên môi trường của bạn mới sinh ra digest thật.

### Kiểm chứng trên Windows PowerShell

~~~powershell
.\mvnw.cmd -B -ntp clean verify
Copy-Item "target\reproducible-lab-1.0.0.jar" "$env:TEMP\repro-first.jar"

.\mvnw.cmd -B -ntp clean verify
(Get-FileHash -Algorithm SHA256 "target\reproducible-lab-1.0.0.jar").Hash
(Get-FileHash -Algorithm SHA256 "$env:TEMP\repro-first.jar").Hash
~~~

So sánh hai chuỗi hash. Nếu chúng khác, cần điều tra nguồn bất định trước khi kết luận release reproducible.

**Một lưu ý về integrity:** SHA-256 giúp so bytes, nhưng **không tự chứng minh** rằng source, Maven distribution hay dependencies an toàn. Chữ ký/provenance/trusted checksum source là lớp kiểm soát khác.

## 25. Thử reproducibility với Maven Artifact Plugin

Apache Maven có hướng dẫn dùng Maven Artifact Plugin để kiểm tra build output:

~~~bash
./mvnw clean install
./mvnw clean verify artifact:compare
~~~

Đây là **mẫu command theo hướng dẫn chính thức**, phụ thuộc plugin goal resolution/configuration của version Maven/Artifact Plugin thực tế. Nếu xây CI nghiêm ngặt, nên pin version cụ thể của Maven Artifact Plugin trong POM hoặc gọi fully-qualified goal để tránh plugin version drift.

Ý nghĩa:

1. Lần đầu build và install artifact làm reference local.
2. Lần sau build tới verify và so artifact với reference.
3. Nếu khác, plugin giúp chỉ ra artifacts không khớp.

Hướng dẫn Maven còn đề xuất:

~~~bash
mvn artifact:check-buildplan
~~~

để kiểm tra plugin versions/plan tương thích reproducible builds, và `diffoscope` khi cần so nội dung artifacts khác nhau.

**Hạn chế:** hai lần build trên cùng máy vẫn chia sẻ JDK, filesystem và Maven cache. Để xác minh independent reproducibility, làm lại trên build environment thứ hai được mô tả/kiểm soát rõ ràng rồi so binary.

## 26. Fix build khi SHA-256 không trùng

Quy trình tìm nguyên nhân:

1. Ghi lại Maven version của cả hai build.
2. Ghi JDK version/vendor/patch và Java home.
3. So effective POM/plugin versions/active profiles.
4. So resolved dependency tree và repository origins.
5. So local Maven repository settings/mirror/proxy.
6. Dùng ZIP listing và diffoscope kiểm tra JAR entry names, order, timestamps, byte differences.
7. Nếu khác classfiles: xem compiler JDK, annotation processing, source generation, debug paths.
8. Nếu khác manifest/pom.properties: xem archiver, build properties, timestamp.
9. Nếu khác resources: xem filtering, CRLF/LF, locale, file encodings, generated files.
10. Nếu plugin tải data ngoài Maven repository: ghim/cache hoặc thiết kế lại theo policy.
11. Khi sửa, chạy hai independent builds và compare lại.

**Không “sửa” bằng cách bỏ qua hash mismatch** khi mục tiêu release attestation; không lý giải khác biệt bằng “thời gian build” mà chưa xác định artifact entries thực sự khác gì.

## 27. Tại sao local Maven cache có thể che lỗi?

Local repository thường ở:

~~~text
~/.m2/repository
~~~

Nếu hai developer dùng cùng GAV nhưng một người có snapshot JAR cũ, local results có thể khác dù POM giống nhau. Khi build trên CI:

- Cached dependencies tăng tốc, nhưng phải hiểu **cache validity/integrity**.
- Ưu tiên trusted Maven mirror/proxy, immutable releases và checksums.
- Khi test reproducibility, cân nhắc **isolated local repository** để phát hiện build dựa vào artifacts cài thủ công.
- Với offline mode `-o`, build chỉ thành công nếu Maven distribution (Wrapper) và các plugin/dependencies cần dùng đã có trong cache; offline success không chứng minh những artifacts cached là đúng provenance.

Ví dụ chạy với isolated repo trên Unix-like:

~~~bash
./mvnw -B -ntp -Dmaven.repo.local=/tmp/repro-lab-m2 clean verify
~~~

Đường dẫn repo này dùng cho Maven artifact resolution **trong lần chạy**, không thay đổi việc Wrapper tải Maven distribution vào wrapper cache riêng. Một isolated repository trống ban đầu có thể cần network truy cập Maven Central hoặc mirror nội bộ.

### Windows PowerShell

~~~powershell
.\mvnw.cmd -B -ntp "-Dmaven.repo.local=$env:TEMP\repro-lab-m2" clean verify
~~~

Đừng xóa toàn bộ `~/.m2/repository` của người khác chỉ để tái hiện lỗi; một isolated local repo có kiểm soát an toàn hơn.

## 28. Cố định dependency graph bằng báo cáo có thể review

Maven Dependency Plugin cho phép xem dependencies:

~~~bash
./mvnw -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
~~~

Để tập trung vào dependency scope:

~~~bash
./mvnw -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree -Dscope=runtime
~~~

Để ghi báo cáo:

~~~bash
./mvnw -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree -DoutputFile=target/dependency-tree.txt
~~~

Lưu dependency report/SBOM phục vụ review/version updates; nhưng **không gọi file text tree đó là lockfile** nếu build thực tế vẫn tiếp tục resolve dynamic versions từ remote metadata.

Đối với dự án lớn, có thể dùng SBOM plugins và vulnerability/license checks được pin version, với release process biết cách đối chiếu generated reports. SBOM mô tả components/provenance, không thay thế việc cấu hình Maven versions và repository immutability.

### Effective POM

~~~bash
./mvnw -B -ntp help:effective-pom -Doutput=target/effective-pom.xml
~~~

Effective POM giúp nhìn versions được kế thừa từ parent/BOM/pluginManagement, nhưng nếu dùng unversioned `help` goal, plugin version resolution là một input riêng. Trong CI nghiêm ngặt nên dùng fully-qualified Help Plugin goal có version đã được duyệt.

## 29. Những nguyên nhân khác ngoài bốn lớp versions

Ngay cả khi đã pin Wrapper/JDK/plugins/dependencies, những inputs sau vẫn có thể làm binary khác:

| Input | Ví dụ drift | Cách giảm rủi ro |
| --- | --- | --- |
| OS line endings | Windows CRLF, Linux LF | Normalize source/resources trong Git, filtering có kiểm soát |
| Charset | Default charset khác | Khai báo UTF-8, kiểm tra tool-specific encodings |
| Locale | Chuyển chữ theo default locale | Dùng `Locale.ROOT` hoặc locale cố định khi phù hợp |
| Timezone | Timestamp sinh từ local time | UTC, fixed build timestamps |
| Current clock | `LocalDateTime.now()` ghi vào resource | Tránh nondeterministic generated metadata |
| Working directory | Absolute paths embedded vào outputs | Tránh nhúng paths, dùng reproducible plugin configuration |
| Username/hostname | BuildInfo chứa tên người build | Chỉ ghi thông tin ổn định/được phép |
| Git state | Dirty tree, uncommitted files | Build từ clean tagged commit, record commit |
| Code generator | Download unpinned schema/CLI | Pin generator version/input checksum |
| Annotation processing | Processor update | Pin annotation processor versions và execution JDK |
| File enumeration | Unsorted directory iteration | Sắp thứ tự deterministic |
| Platform architecture | OS-specific native dependencies | Matrix build theo target platform |
| Network source | API/server trả dữ liệu mới | Không lấy unversioned dynamic data trong build |
| Maven settings | Mirror/profiles khác | Cấu hình CI rõ ràng, không hard-code secrets vào Git |

Độ tái lập của binary còn bị giới hạn bởi phần yếu nhất của toàn chuỗi inputs. Một team cần **thực sự chạy artifact comparison**, không chỉ tick checklist.

## 30. Wrapper và Maven properties: đừng nhầm những đường dẫn .mvn

Các files có vai trò khác nhau:

~~~text
.mvn/wrapper/maven-wrapper.properties
.mvn/maven.config
.mvn/jvm.config
~/.m2/settings.xml
~/.m2/toolchains.xml
pom.xml
~~~

- `maven-wrapper.properties`: Maven distribution URL/version và checksum.
- `.mvn/maven.config`: Maven command-line options mặc định của project; có thể chứa flags thống nhất, không nên chứa secrets.
- `.mvn/jvm.config`: JVM options dùng khi chạy Maven theo launcher support.
- `~/.m2/settings.xml`: Maven user settings, mirrors, proxies, credentials, local repo và profiles.
- `~/.m2/toolchains.xml`: ánh xạ toolchains JDK và installation paths.
- `pom.xml`: project model, plugins/dependencies/lifecycle.

**Không nhét JDK installation path của một developer vào Maven Wrapper properties** để giả vờ khóa JDK: Wrapper và Toolchains/config môi trường phục vụ hai việc khác nhau.

## 31. Phân biệt JDK chạy tests và bytecode target

Mô hình:

~~~text
JDK 17 runs Maven
        |
        +-- Compiler Plugin --release 17 -> classfile major 61
        |
        +-- Surefire Plugin -> fork JVM/test runtime theo cấu hình
        |
        +-- Jar Plugin -> ZIP artifact
~~~

Nếu Maven được chạy trên JDK17 và Surefire dùng runtime mặc định trong lab, tests chạy trên JVM tương thích JDK17. Nhưng trong project thật, Surefire có thể cấu hình `jdkToolchain` hoặc fork khác; verify actual test logs khi cần.

Khi CI chạy Maven trên JDK21 nhưng compiler toolchain dùng 17, Enforcer `requireJavaVersion [17,18)` sẽ ngăn build theo **Maven runtime JDK**, dù compiler dùng 17. Nếu đây là thiết kế có chủ đích, điều chỉnh Enforcer policy theo **Maven launcher** và dùng toolchain selection để ghim compiler/test JDK riêng.

**Không giảm yêu cầu Enforcer tùy tiện** khi chỉ vì máy local đang có JDK21; hãy quyết định toolchain policy nhất quán.

## 32. Multi-module: nên đặt phiên bản ở parent nào?

Giả sử:

~~~text
platform/
├── pom.xml              packaging pom
├── core/pom.xml          jar
└── app/pom.xml           jar
~~~

Phổ biến nhất:

1. Wrapper tại root platform; CI chạy `./mvnw` từ root.
2. Parent POM đặt `maven.compiler.release`, `project.build.outputTimestamp` và version properties.
3. Parent `dependencyManagement` pin shared library versions.
4. Parent `pluginManagement` pin shared plugin versions.
5. Enforcer Plugin execution trong `build/plugins` được kế thừa vào child modules nếu policy áp dụng cho tất cả.
6. Child POM khai báo dependencies/plugins thực sự dùng, tránh tự chọn versions khác không cần thiết.
7. CI build **đúng reactor selection**; `-N` chỉ kiểm tra root POM, không phải tất cả child projects.

**Không nhầm**: parent có `<modules>` chỉ liệt kê các modules, không làm app tự có core trên classpath; child dependency phải khai báo đúng.

Khi muốn build riêng app cùng những reactor dependencies đang sửa:

~~~bash
./mvnw -B -ntp -pl :app -am clean verify
~~~

Khi muốn build/test toàn bộ modules:

~~~bash
./mvnw -B -ntp clean verify
~~~

**Cùng một Wrapper và parent POM giúp giảm drift**, nhưng các child profiles/overrides vẫn phải được review.

## 33. Negative test: cố tình dùng sai JDK

Với POM lab đã có:

~~~xml
<requireJavaVersion>
    <version>[17,18)</version>
</requireJavaVersion>
~~~

Giả sử bạn chạy Maven từ JDK21:

~~~bash
./mvnw -B -ntp validate
~~~

Enforcer phải báo vi phạm requireJavaVersion và build fail ở `validate`.

Đó là hành vi **mong muốn** trong một quality gate: không âm thầm tạo artifact bằng toolchain ngoài chính sách.

### Cách sửa

- Đặt JDK17 đã được cài và kiểm chứng vào `JAVA_HOME`/PATH cho Maven launcher.
- Hoặc dùng CI image JDK17 được ghim.
- Hoặc nếu chủ đích Maven runtime là JDK21 nhưng compiler toolchain là 17, thiết kế Toolchains/Enforcer policy đúng và verify từng plugin.
- Không bỏ `requireJavaVersion` vĩnh viễn chỉ để job xanh.

**Không đặt giá trị JAVA_HOME giả**: chỉ sử dụng đường dẫn thật của JDK17 trên host.

## 34. Negative test: cố tình dùng Maven sai version

Wrapper muốn Maven 3.9.9; POM có:

~~~xml
<requireMavenVersion>
    <version>[3.9.9]</version>
</requireMavenVersion>
~~~

Nếu developer bỏ qua `mvnw` và dùng một `mvn` khác trên PATH, Enforcer có thể FAIL.

Điều này cho thấy **Wrapper + Enforcer phối hợp**:

- Wrapper cung cấp đúng version một cách thuận tiện.
- Enforcer đảm bảo phiên bản khác không lọt qua quality gate.

Trong CI nên dùng `./mvnw`/`mvnw.cmd`; Enforcer là guardrail bổ sung, không phải trình cài Maven.

## 35. Negative test: thay một dependency version

Trong POM lab, đổi:

~~~xml
<commons-lang3.version>3.14.0</commons-lang3.version>
~~~

thành một **phiên bản release hợp lệ khác**, rồi rebuild. Java code có thể vẫn in:

~~~text
repro-lab:STABLE
~~~

nhưng JAR hash **không nhất thiết** khác: main application JAR bình thường chứa **code ứng dụng**, không tự nhúng Commons Lang. Vì bytecode class App tham chiếu library API có thể giống hệt giữa hai versions, main JAR có thể vẫn byte-identical mặc dù runtime resolved dependency khác.

Đây là một **điểm rất quan trọng**:

**SHA-256 của một plain JAR trùng nhau không chứng minh dependency graph/runtime classpath trùng nhau.**

Để kiểm tra đầy đủ release inputs, phải kiểm soát cả:

- Main artifact hash.
- Effective dependency graph/BOM versions.
- Runtime dependencies/distribution.
- Parent/settings/plugin versions.
- Binary/SBOM/provenance của published release.

Một fat JAR có nhúng dependencies sẽ có những khả năng thay đổi hash khác so với plain JAR; không áp dụng một kết luận cho mọi packaging strategy.

## 36. Xử lý phụ thuộc trùng và convergence

Khi project có:

~~~text
app
├── helper-a:1.0 → api:2.0
└── helper-b:2.0 → api:2.1
~~~

Maven có thể chọn `api` version theo mediation; Enforcer `dependencyConvergence` sẽ báo khi các paths không thống nhất.

Nhưng convergence **không tự giải quyết**:

- Hai declarations lặp cùng GA/type/classifier trong POM.
- Hai JAR khác coordinates chứa cùng fully-qualified class.
- Artifact/version có lỗ hổng bảo mật.
- Plugin dependency không được pin.
- SNAPSHOT nội dung thay đổi qua thời gian.

Cần các rules/công cụ riêng: `banDuplicatePomDependencyVersions`, `bannedDependencies`, MojoHaus Extra Enforcer Rules `banDuplicateClasses`, vulnerability scanning, SBOM, plugin version policy.

**Không “sửa” mọi lỗi bằng cách thêm `<excludes>*</excludes>` quá rộng** trong convergence rule. Ngoại lệ càng rộng thì cổng chất lượng càng mất ý nghĩa.

## 37. Khi nào cần hash cả Wrapper distribution và dependencies?

Có hai mục tiêu:

**Integrity của build tools**: dự án có thể ghi SHA-256 hợp lệ của Maven distribution trong Wrapper properties; CI image cũng được pin digest.

**Integrity của artifacts được resolve**: Maven/Resolver/repository manager có cơ chế checksum và metadata; release pipeline nên dùng trusted repositories, immutable releases, signature/provenance policies và tránh artifact uploads từ nguồn không đáng tin.

Chỉ ghi:

~~~text
maven=3.9.9
commons-lang3=3.14.0
~~~

chưa đảm bảo file bytes tải về từ mirror A và mirror B là cùng một binary. Version pin cần đi cùng repository governance.

**Cẩn thận với việc tạo checksum**: hash từ file bạn vừa tải về có thể hữu ích để phát hiện thay đổi sau đó, nhưng để xác nhận authenticity cần một digest/chữ ký từ nguồn đáng tin cậy hoặc artifact provenance được xác minh.

## 38. Release build và development build khác nhau về chính sách

Development:

- Có thể cho phép SNAPSHOT để thử integration giữa các teams.
- Cache giúp tăng tốc local build.
- Có thể dùng Maven/JDK preview trong branch riêng.
- Có thể cho phép plugin experiments theo review.

Release:

- Ghim Maven Wrapper/JDK/plugin versions.
- Ghim toàn bộ relevant release dependencies và BOM versions.
- Bảo đảm snapshot/range policy phù hợp, tránh floating inputs.
- Build trên clean source revision, controlled CI image.
- Tạo và lưu checksums/SBOM/provenance.
- Chạy tests/integration/packaging validation.
- Publish immutable release coordinates.
- Kiểm chứng artifact có thể được independent rebuild.

**Không dùng một rule cấm SNAPSHOT không có ngoại lệ cho tất cả branches** nếu workflow development thực sự phụ thuộc snapshot artifacts; phải phân tách profiles/CI policy rõ ràng và vẫn enforce strict rules cho release.

## 39. CI workflow: những bước nên ghi lại

Một pipeline đáng tin có thể:

~~~text
Checkout immutable commit/tag
          |
          v
Set CI JDK 17 image (pinned digest)
          |
          v
Verify ./mvnw and Maven distribution checksum
          |
          v
./mvnw -version
          |
          v
./mvnw -B -ntp clean verify
          |
          +-- Enforcer: Maven/JDK/Dependency policy
          +-- Compiler: release 17
          +-- Surefire: unit tests
          +-- Jar: fixed output timestamp
          |
          v
Record JAR SHA-256 + dependency tree/SBOM
          |
          v
(Optional) independent rebuild and compare
          |
          v
Publish artifact with provenance
~~~

**Không nên dựa vào plugin goals chỉ chạy trực tiếp mà không ghim version**. Ví dụ muốn xuất dependency tree trong CI, gọi fully qualified goal:

~~~bash
./mvnw -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree -DoutputFile=target/dependency-tree.txt
~~~

Nếu pipeline uses generated code/protobuf, pin thêm generator/plugin versions và input schemas/tool binaries. Nếu pipeline builds container image, pin base image digest và kiểm soát layer metadata theo công cụ tương ứng.

## 40. Checklist trước khi nói build “reproducible”

- [ ] Wrapper scripts/properties nằm trong Git và được review.
- [ ] Wrapper dùng phiên bản Maven được ghim, ví dụ 3.9.9.
- [ ] Maven distribution checksum có giá trị thật từ nguồn đáng tin và đã được verify.
- [ ] Team dùng `./mvnw` hoặc `mvnw.cmd`, không tùy tiện dùng `mvn`.
- [ ] JDK Maven runtime version/range được kiểm tra bằng Enforcer hoặc CI.
- [ ] JDK vendor/patch/container image được pin nếu release cần exact environment.
- [ ] `maven.compiler.release` được khai báo rõ.
- [ ] Nếu Toolchains được dùng, compiler/test plugins thật sự nhận toolchain mong muốn.
- [ ] Maven Compiler/Surefire/Resources/JAR/Clean versions được ghim.
- [ ] Plugin versions của những goals chạy trực tiếp trong CI cũng được ghim.
- [ ] Nếu dùng Enforcer requirePluginVersions, các default lifecycle plugins đã được kiểm kê đầy đủ.
- [ ] Direct dependencies có versions tường minh hoặc managed versions.
- [ ] BOM/dependencyManagement versions được ghim và review.
- [ ] Không có ranges/LATEST/RELEASE/SNAPSHOT ngoài policy cho phép.
- [ ] Resolved dependency tree được lưu/so sánh ở những thay đổi quan trọng.
- [ ] Các test/integration plugins và code generators được pin versions.
- [ ] Active profiles và Maven settings/mirrors được kiểm soát.
- [ ] Repository releases là immutable, checksums/provenance được xác minh.
- [ ] Encoding/locale/timezone có thiết lập rõ khi ảnh hưởng output.
- [ ] `project.build.outputTimestamp` có giá trị cố định hoặc dùng reproducible mode tương đương.
- [ ] Không nhúng timestamps/hostname/current path ngẫu nhiên vào generated files.
- [ ] Source revision clean/immutable được ghi lại.
- [ ] Có phép kiểm tra hash JAR/ZIP giữa các build.
- [ ] Không kết luận runtime dependency graph giống chỉ vì plain JAR hash trùng.
- [ ] Có kiểm chứng independent rebuild khi chuẩn bị release quan trọng.
- [ ] Xử lý hash mismatch bằng diffoscope/artifact comparison.
- [ ] CI logs ghi Maven/JDK/build image versions và SHA-256 của artifacts.
- [ ] Nâng versions theo kế hoạch bảo mật và kiểm tra regression.
- [ ] Team phân biệt bit-identical artifact với functional equivalence.
- [ ] Không tự xóa Maven cache trên máy người khác khi điều tra drift.

## 41. Những lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Local pass, CI fail vì Java API | JDK runtime/compile khác nhau | Ghim CI JDK, `release`, Enforcer |
| Wrapper chạy Maven đúng nhưng Java sai | Wrapper không cài JDK | Cấu hình JAVA_HOME/CI image/Toolchains |
| Maven 3.9.9 Wrapper nhưng IDE dùng Maven khác | IDE bypasses Wrapper | Chỉ định IDE dùng Maven Wrapper |
| Plugin tự tăng version | Plugin thiếu version pin hoặc dùng LATEST | Khai báo plugin version cụ thể |
| Parent có pluginManagement mà Enforcer không chạy | Plugin chưa được kích hoạt | Đặt Enforcer trong build/plugins và bind execution |
| Dependency graph khác giữa hai lần build | Ranges/SNAPSHOT/metadata/repo khác | Pin versions, BOM, mirror, scan tree |
| Maven build thành công nhưng JAR hash khác | Timestamp/manifest/generated resource | `outputTimestamp`, diffoscope, fix generator |
| JAR hash trùng nhưng app runtime khác | Plain JAR không đóng transitive dependencies | Đối chiếu dependency tree/runtime classpath |
| `./mvnw` trên Linux Permission denied | Script chưa executable | Commit executable bit và `chmod +x mvnw` |
| Windows không chạy `./mvnw` | Shell không dùng Unix script | Dùng `.\mvnw.cmd` |
| Wrapper tải distribution thất bại | Network/proxy/checksum/URL | Kiểm tra trusted URL, proxy và checksum |
| `-o` offline fail | Cache thiếu plugin/dependency/distribution | Populate cache từ trusted repos |
| Enforcer Java 17 fail khi chạy Maven 21 | requireJavaVersion kiểm tra runtime JDK | Chọn policy runtime/Toolchains nhất quán |
| requirePluginVersions gây fail nhiều plugin | Chưa ghim lifecycle defaults | Bổ sung versions, không skip lâu dài |
| ZIP entry timestamp thay đổi | Archiver plugin không dùng reproducible mode | Upgrade plugin, outputTimestamp |
| JAR chênh trên Windows vs Linux | Newlines/encoding/file iteration | Normalize resources và test cross-platform |
| JAR chênh giữa two CI jobs | Build image/locale/time zone khác | Pin image digest và environment |
| Test ngẫu nhiên fail | Locale/timezone/order/external services | Isolate tests và remove nondeterminism |
| Dependency tree chỉ parent, không child | Chạy goal sai project | Dùng `-f` hoặc `-pl` cho module cụ thể |
| Ghim SNAPSHOT nhưng binary vẫn đổi | SNAPSHOT là mutable logical version | Dùng releases/immutable artifact với digest |
| Phát hành lại cùng GAV nhưng binary khác | Release repository cho phép overwrite | Enforce immutability/versioning |
| CI hash so trước/sau ở cùng cache | Chưa độc lập về input | Rebuild thứ hai trên fresh controlled env |
| Maven plugin đọc system clock | Plugin chưa reproducible | Upgrade/plugin config hoặc loại timestamp |
| Build dùng credentials không thuộc CI | settings khác nhau | Secret manager, explicit settings/profiles |

## 42. Bài tập có đáp án

1. **Wrapper giúp cố định gì?**  
   **Đáp án:** Maven distribution/version và cơ chế launcher cho project.

2. **Wrapper có tự cài JDK17 không?**  
   **Đáp án:** Không.

3. **Lệnh tạo Wrapper pin Maven 3.9.9 trong bài?**  
   **Đáp án:** `mvn -N org.apache.maven.plugins:maven-wrapper-plugin:3.3.4:wrapper -Dmaven=3.9.9 -Dtype=only-script`.

4. **Với Wrapper only-script, có bắt buộc commit maven-wrapper.jar không?**  
   **Đáp án:** Không; implementation này không cần wrapper JAR.

5. **File nào chứa Maven distribution URL?**  
   **Đáp án:** `.mvn/wrapper/maven-wrapper.properties`.

6. **Checksum property nào kiểm tra Maven distribution?**  
   **Đáp án:** `distributionSha256Sum`.

7. **Có nên nhập `distributionSha256Sum=...` nguyên văn?**  
   **Đáp án:** Không; cần hash SHA-256 thật đã verify từ trusted source.

8. **Maven runtime JDK khác compiler release thế nào?**  
   **Đáp án:** Runtime chạy Maven/plugins; release chọn Java API/classfile target.

9. **`maven.compiler.release=17` có bảo đảm Maven chạy trên JDK17?**  
   **Đáp án:** Không.

10. **Enforcer rule khóa Maven runtime?**  
    **Đáp án:** `requireMavenVersion`.

11. **Enforcer rule khóa Java runtime?**  
    **Đáp án:** `requireJavaVersion`.

12. **`[17,18)` có ghim exact JDK patch không?**  
    **Đáp án:** Không, chỉ range cho major 17.

13. **Toolchains giúp gì?**  
    **Đáp án:** Chọn JDK cho plugins hỗ trợ toolchains, có thể khác Maven runtime.

14. **Plugin nào biên dịch mã Java?**  
    **Đáp án:** Maven Compiler Plugin.

15. **Plugin nào chạy unit tests của lab?**  
    **Đáp án:** Maven Surefire Plugin.

16. **pluginManagement có tự chạy mọi plugin?**  
    **Đáp án:** Không; nó quản lý versions/configuration khi plugins được sử dụng.

17. **Rule nào phát hiện plugin thiếu version?**  
    **Đáp án:** `requirePluginVersions`.

18. **BOM import dùng type/scope gì trong Maven 3?**  
    **Đáp án:** `type=pom` và `scope=import` trong dependencyManagement.

19. **dependencyManagement có tự thêm dependencies không?**  
    **Đáp án:** Không.

20. **Maven 3 có default dependency lockfile bao phủ mọi plugin/transitive version như npm không?**  
    **Đáp án:** Không.

21. **Version range `[1.0,2.0)` có lợi cho strict reproducibility không?**  
    **Đáp án:** Không; nó có thể resolve versions khác khi repository metadata thay đổi.

22. **SNAPSHOT có chắc binary bất biến không?**  
    **Đáp án:** Không; logical SNAPSHOT version thường mutable.

23. **Rule nào bắt dependency paths hội tụ?**  
    **Đáp án:** `dependencyConvergence`.

24. **Plugin nào xem resolved dependency tree?**  
    **Đáp án:** Maven Dependency Plugin, goal `tree`.

25. **Property nào giúp fixed ZIP timestamps?**  
    **Đáp án:** `project.build.outputTimestamp` với plugins hỗ trợ.

26. **SHA-256 JAR trùng có chứng minh cùng runtime dependency graph không?**  
    **Đáp án:** Không, đặc biệt với plain JAR không nhúng dependencies.

27. **Làm sao kiểm tra byte equality của hai build?**  
    **Đáp án:** Compare artifact bytes hoặc SHA-256 sau hai lần build, rồi independent rebuild khi cần.

28. **Công cụ nào giúp xem khác biệt sâu trong ZIP/JAR?**  
    **Đáp án:** `diffoscope`.

29. **Java 17 classfile major version thường là bao nhiêu?**  
    **Đáp án:** 61.

30. **Dòng stdout App.main của lab?**  
    **Đáp án:** `repro-lab:STABLE`.

31. **Vì sao không chạy `java -jar` với plain JAR của lab?**  
    **Đáp án:** Chưa có Main-Class và runtime dependency commons-lang3 không được nhúng.

32. **Default locale có thể phá build output thế nào?**  
    **Đáp án:** Generated text chuyển hoa/thường hoặc format ngày tháng có thể khác.

33. **Vì sao dùng Locale.ROOT trong App?**  
    **Đáp án:** Để uppercase không phụ thuộc default locale.

34. **Một clean build cùng local cache có chứng minh independent reproducibility không?**  
    **Đáp án:** Không; vẫn chia sẻ hidden inputs.

35. **Nguyên tắc cuối của build tái lập?**  
    **Đáp án:** Ghim tools/plugins/dependencies, kiểm soát môi trường và **xác minh actual artifact bytes/provenance**.

## 43. Tài liệu chính thức và nguồn học thêm

- [Apache Maven Wrapper](https://maven.apache.org/tools/wrapper/): công dụng Wrapper, distribution types, scripts, checksum properties.
- [Apache Maven Wrapper Plugin — wrapper:wrapper](https://maven.apache.org/tools/wrapper/maven-wrapper-plugin/wrapper-mojo.html): flags `maven`, `type`, distribution URL, SHA-256.
- [Apache Maven Wrapper Plugin — Usage](https://maven.apache.org/tools/wrapper/maven-wrapper-plugin/usage.html): các Wrapper variants và initialization.
- [Apache Maven — Configuring for Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html): `project.build.outputTimestamp`, buildplan, artifact:compare, diffoscope.
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): mediation, BOM, dependencyManagement, scopes.
- [Apache Maven — Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains.html): JDK Toolchains, Maven runtime vs compiler.
- [Apache Maven Toolchains Plugin](https://maven.apache.org/plugins/maven-toolchains-plugin/): toolchain selection/discovery.
- [Apache Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html): `maven.compiler.release` và JDK/compiler semantics.
- [Apache Maven Enforcer Plugin](https://maven.apache.org/enforcer/maven-enforcer-plugin/): build policy gates.
- [Enforcer — Require Maven Version](https://maven.apache.org/enforcer/enforcer-rules/requireMavenVersion.html): Maven runtime range policy.
- [Enforcer — Require Java Version](https://maven.apache.org/enforcer/enforcer-rules/requireJavaVersion.html): JDK runtime range policy.
- [Enforcer — Require Plugin Versions](https://maven.apache.org/enforcer/enforcer-rules/requirePluginVersions.html): banMavenDefaults, banned dynamic plugin versions.
- [Enforcer — Dependency Convergence](https://maven.apache.org/enforcer/enforcer-rules/dependencyConvergence.html): graph conflicts.
- [Enforcer — Ban Dynamic Versions](https://maven.apache.org/enforcer/enforcer-rules/banDynamicVersions.html): tránh version ranges/SNAPSHOT theo policy.
- [Enforcer — Require Release Dependencies](https://maven.apache.org/enforcer/enforcer-rules/requireReleaseDeps.html): cấm snapshot dependencies ở release.
- [Apache Maven Dependency Plugin — tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): resolved dependency tree.
- [Apache Maven JAR Plugin](https://maven.apache.org/plugins/maven-jar-plugin/): archive packaging và reproducibility options.
- [Apache Maven — Maven Settings Reference](https://maven.apache.org/settings.html): mirrors, repositories, local cache, credentials.

**Kết luận:** Một build tái lập không đến từ một file cấu hình đơn lẻ. **Maven Wrapper** giúp mọi người dùng cùng Maven; **JDK/Toolchains + compiler release** ổn định môi trường và Java target; **plugin versions** ổn định build logic; **BOM/dependencyManagement/Enforcer** kiểm soát resolved dependency graph. Sau đó vẫn phải kiểm soát timestamps, profiles, repositories, generated files và kiểm chứng SHA-256 của artifacts — tốt nhất bằng những rebuild độc lập.

# Rủi ro từ mã thực thi trong plugin, extension và script build của Maven

## 1. Vì sao “chỉ chạy build” cũng là một quyết định bảo mật?

Khi nhận một repository Java từ đồng nghiệp, một pull request chưa được duyệt hoặc một dự án tải từ Internet, nhiều người có thói quen lập tức chạy:

~~~bash
mvn clean verify
~~~

Lệnh này không đơn thuần “đọc XML và biên dịch Java”. Maven có thể **tải và thực thi mã của các plugin**, nạp **extensions**, gọi **script hoặc chương trình bên ngoài**, chạy **annotation processors**, khởi động tests, hoặc dùng logic được cấu hình ở parent POM và profiles. Một số thành phần chạy **trước cả phase `validate`**.

Vì thế, khi input chưa tin cậy, build là một hoạt động có rủi ro supply chain: mã thực thi trong build process có thể được cấp quyền đọc file của tài khoản đang chạy, truy cập mạng, sửa workspace, nhìn thấy environment variables và tác động tới cache hoặc artifacts. Mức quyền cụ thể còn phụ thuộc hệ điều hành, container, runner và các biện pháp cô lập.

Bài Knowledge thuộc chủ đề **An toàn phụ thuộc**, tập trung vào **rủi ro từ mã thực thi trong plugin, extension và script build** — tức không chỉ quan tâm dependency của ứng dụng khi chạy production, mà còn kiểm tra **mã được phép chạy để tạo ra ứng dụng**.

Sau bài này, bạn có thể:

1. Phân biệt runtime dependency, Maven build plugin, plugin dependency, core/build extension, scripts, wrapper và test/annotation processor.
2. Xác định các điểm trong quy trình Maven có khả năng thực thi mã, đặc biệt những điểm chạy rất sớm.
3. Hiểu cơ chế plugin resolution, `pluginRepositories`, parent inheritance, profile activation và Maven lifecycle.
4. Rà soát một POM hoặc pull request **bằng phương pháp tĩnh trước khi chạy Maven**.
5. Phân biệt plugin version pinning, checksum, chữ ký, repository allowlist, sandbox và CI permissions.
6. Biết giới hạn token, secrets, network, filesystem và cache trên CI dành cho mã chưa tin cậy.
7. Thực hành Maven + Java 17 có **plugin chỉ in thông điệp vô hại** tại phase `validate`; quan sát điều gì thực sự chạy.
8. Viết policy cho việc bổ sung plugin, extension, wrapper hoặc build script mới.
9. Xử lý sự cố khả nghi mà không tự động chạy thử plugin nghi ngờ trên máy có quyền cao.
10. Biết giới hạn: Enforcer, `-o`, `-DskipTests` hay “BUILD SUCCESS” **không phải** hộp cát bảo mật.

**Phạm vi:** Maven 3.x, Java 17+, repository Java dùng POM 4.0.0. Các ví dụ phiên bản plugin được ghim để minh họa, không mặc nhiên là bản mới nhất hoặc không còn lỗ hổng. Phần thí nghiệm chỉ thực hiện thao tác vô hại; không dùng payload đánh cắp thông tin hay gọi server bên ngoài.

## 2. Threat model: ai điều khiển được đầu vào build?

Một phép build Maven có thể nhận input từ nhiều ranh giới tin cậy:

~~~text
Git repository
 ├── pom.xml / parent POM / profiles
 ├── .mvn/extensions.xml
 ├── .mvn/maven.config / .mvn/jvm.config
 ├── mvnw / mvnw.cmd / wrapper properties
 ├── src/main / src/test / resources
 ├── build scripts / CI workflow
 │
 ▼
Maven executable + JVM + settings.xml
 │
 ├── repositories → Maven plugins + plugin dependencies
 ├── repositories → ordinary dependencies + annotation processors
 ├── core/build extensions → bổ sung hoặc thay đổi Maven runtime
 ├── lifecycle/goal executions → chạy logic build
 ├── tests / spawned tools → chạy mã khác
 │
 ▼
Build output (JAR/WAR/POM/SBOM/reports)
 │
 ▼
Cache / artifact repository / release pipeline
~~~

Không phải mọi thành phần đều nguy hiểm; vấn đề là **mức quyền của mã**, nguồn gốc của nó và liệu một actor không đáng tin có thể thay đổi thứ được thực thi.

Một số đối tượng tấn công hoặc nguồn lỗi:

- Kẻ sửa pull request để thêm plugin execution không được duyệt.
- Tài khoản có quyền thay đổi parent POM dùng chung.
- Plugin/extension từ repository bị compromise hoặc bị phát hành bản độc hại.
- Plugin có dependency transitive bị compromise.
- Repository mirror không được kiểm soát hoặc cache bị thay artifact.
- Script `mvnw`, CI workflow hoặc file cấu hình JVM bị thay.
- Pipeline privileged checkout mã của pull request không tin cậy và cấp secrets.
- Developer chạy project lạ trên máy có SSH keys, cloud credentials, tokens, cấu hình ký phát hành.

**Nguy cơ điển hình:** đọc secrets, truy cập mạng ra ngoài, thay artifacts, ghi vào cache, sửa source hoặc generated code, thực thi process khác và tạo một release không phản ánh source đã được review. Những khả năng này đến từ quyền chung của process/build runner, không phải “Maven có chức năng đánh cắp dữ liệu” theo mặc định.

## 3. Plugin khác dependency thông thường thế nào?

### 3.1. Dependency của ứng dụng

~~~xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>3.14.0</version>
    </dependency>
</dependencies>
~~~

Dependency này thường được compiler/runtime/test classpath sử dụng theo scope. Maven không nhất thiết gọi trực tiếp method của thư viện đó trong JVM của Maven chỉ vì nó nằm dưới `<dependencies>`. Tuy vậy, mã của dependency có thể được **chạy khi unit/integration tests sử dụng nó**, hoặc các công cụ khác xử lý nó.

### 3.2. Maven build plugin

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-antrun-plugin</artifactId>
            <version>3.1.0</version>
        </plugin>
    </plugins>
</build>
~~~

Đây là **mảnh cấu hình**, chưa có execution. Maven plugin chứa Java classes/Mojos thực thi các build goals. Khi một goal được gọi trực tiếp hoặc bind vào lifecycle, mã plugin có thể chạy trong Maven process hoặc tạo process riêng, tùy plugin.

**Sự khác biệt bảo mật:** một plugin không chỉ là “library nằm trong JAR ứng dụng”; nó là **mã công cụ xây ứng dụng**, thường có quyền filesystem/network của build process.

### 3.3. Plugin dependency

Một plugin còn có dependencies của chính nó:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-antrun-plugin</artifactId>
    <version>3.1.0</version>
    <dependencies>
        <dependency>
            <groupId>org.apache.ant</groupId>
            <artifactId>ant</artifactId>
            <version>1.10.15</version>
        </dependency>
    </dependencies>
</plugin>
~~~

Đây là **mảnh minh họa việc plugin có classpath dependencies riêng**, không phải một thay đổi được yêu cầu trong lab runnable ở mục 10. Việc override plugin dependencies có thể thay mã mà goal thực thi, ngay cả khi `artifactId`/`version` của plugin chính không đổi.

Đừng chỉ review `<dependencies>` cấp project rồi bỏ qua `<build><plugins><plugin><dependencies>`. Công cụ quét runtime dependencies không nhất thiết bao phủ plugin dependencies; cần kiểm kê build-time supply chain riêng.

### 3.4. Plugin code có thể làm gì?

Tùy plugin, goals có thể:

- Biên dịch Java, sinh code, tạo resources, đọc/ghi file.
- Chạy Ant tasks, Groovy/other scripting engines hoặc chương trình hệ điều hành.
- Tải tools/binaries để build frontend/native artifacts.
- Khởi động container, service hoặc integration test environment.
- Gọi API hay repository server.
- Ký hoặc upload artifacts khi được cấp quyền và configuration.

Không suy luận plugin độc hại chỉ vì nó có khả năng chạy process hoặc network; các công cụ hợp pháp cũng cần điều đó. Điểm cần review là **mã nguồn/nhà phát hành, phiên bản, lý do sử dụng, execution, cấu hình, phạm vi quyền và hành vi quan sát được**.

## 4. Những nơi Maven có thể nạp code thực thi

### 4.1. Plugin goal gắn vào lifecycle

~~~xml
<executions>
    <execution>
        <id>safe-task</id>
        <phase>validate</phase>
        <goals>
            <goal>run</goal>
        </goals>
    </execution>
</executions>
~~~

Nếu goal `run` thuộc một plugin được khai báo và execution có configuration hợp lệ, gọi `mvn validate` **có thể thực thi goal đó**. Các phase sau như `test`, `package`, `verify` cũng đi qua `validate` trong default lifecycle.

Không được tin rằng chỉ `mvn package` mới chạy script. Một execution ở `validate` có thể chạy **trước compile/test**.

### 4.2. Goal chạy trực tiếp, ngoài lifecycle mặc định

Ví dụ:

~~~bash
mvn org.apache.maven.plugins:maven-antrun-plugin:3.1.0:run
~~~

Đây là ví dụ về cú pháp goal trực tiếp; nó cần configuration phù hợp mới có nhiệm vụ hữu ích. Một plugin goal không nhất thiết phải xuất hiện ở `<executions>` để được gọi từ CLI, Maven Wrapper, CI pipeline hoặc script.

### 4.3. Plugin được kế thừa từ parent

Một module con có thể không thấy plugin lạ trong POM của chính nó, nhưng vẫn **inherit `build/plugins` hoặc executions** từ parent POM. Nếu parent do nhóm khác phát hành, việc đổi parent version có thể thay mã/plugin logic của nhiều modules.

Lưu ý:

- `pluginManagement` thường quản lý versions/configurations, không tự kích hoạt một execution chưa được dùng.
- `build/plugins` có plugin/execution và có thể được child kế thừa.
- Một plugin mặc định của lifecycle cũng được gọi vì `packaging`/phase bindings.
- Profiles từ POM hoặc settings có thể đổi plugins và repositories khi active.

Sau **review tĩnh và thiết lập môi trường an toàn**, dùng effective POM để xem cấu hình kế thừa. Đừng chạy `mvn help:effective-pom` trên project chưa tin cậy chỉ vì tên lệnh có chữ “help”.

## 5. Core extension là ranh giới nguy hiểm hơn plugin thông thường

Theo tài liệu Maven, extensions cung cấp khả năng thêm hoặc thay thế components của Maven runtime, classloader, transport hoặc lifecycle behavior.

**Core extensions** được nạp sớm, trước phần lớn logic project build thông thường.

Những cách đăng ký thường gặp:

- File `.mvn/extensions.xml` trong project.
- CLI JVM/Maven property `maven.ext.class.path` trỏ đến extension JAR.
- Extensions cài tại Maven distribution theo cơ chế phiên bản tương ứng.

File `.mvn/extensions.xml` sử dụng cấu trúc chứa GAV của các core extensions:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<extensions xmlns="http://maven.apache.org/EXTENSIONS/1.1.0">
</extensions>
~~~

Đây là **file rỗng hợp lệ để minh họa hình dạng XML**, không đăng ký extension nào. Một file thực tế sẽ có các phần tử `<extension>` chứa `groupId`, `artifactId` và `version` của extension artifact; mỗi tọa độ cần được đánh giá theo nguồn phát hành và quyền thực thi.

### Build extensions

Ngoài core extension, Maven có các **build extensions** được khai báo trong POM, chẳng hạn `<build><extensions>` hoặc plugin với:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-antrun-plugin</artifactId>
    <version>3.1.0</version>
    <extensions>true</extensions>
</plugin>
~~~

**Đây là mảnh minh họa trường `<extensions>true</extensions>`, KHÔNG phải cấu hình lab hay khuyến nghị biến AntRun thành extension.** Muốn dùng build extension thật phải chọn plugin được thiết kế hỗ trợ extension, không bật flag tùy tiện.

Build extension và core extension khác thời điểm nạp/cơ chế classloader; không gộp mọi trường hợp thành "plugin sẽ chỉ chạy lúc `package`".

### Vì sao Enforcer không chặn hết core extension?

Maven Enforcer Plugin bản thân là một plugin/goal chạy trong lifecycle. **Nếu extension đã được nạp trước khi Enforcer bắt đầu**, Enforcer không thể được xem là biện pháp sandbox ngăn extension chạy mã từ đầu. Vì vậy:

1. Review file extension tĩnh trước.
2. Đảm bảo repository/extension artifact được phép và có provenance.
3. Chạy build trong môi trường không có secrets/đặc quyền nếu chưa tin.
4. Sau đó mới dùng Enforcer như một guardrail bổ sung.

### Maven runtime và cấu hình machine-wide

Một extension cũng có thể được cài qua Maven installation hoặc môi trường người dùng. Vì vậy trust boundary không chỉ là Git repository; cần biết Maven distribution, `MAVEN_HOME`, biến môi trường, user settings và CI runner image.

**Không kết luận “POM sạch thì Maven chắc chắn sạch”** nếu JVM/Maven runtime và user-level extensions bị quản trị sai.

## 6. `.mvn/maven.config`, `.mvn/jvm.config` và Maven Wrapper

Project directory `.mvn` có thể chứa cấu hình được commit cùng source:

- `.mvn/maven.config`: các CLI options được đưa vào khi chạy Maven.
- `.mvn/jvm.config`: JVM arguments khi Maven launcher khởi động.
- `.mvn/extensions.xml`: core extension declarations.
- `.mvn/wrapper/maven-wrapper.properties`: Maven Wrapper distribution/wrapper settings.
- `mvnw` và `mvnw.cmd`: shell/Windows scripts dùng khởi động Maven.

### `maven.config` không chỉ là ghi chú

Ví dụ cấu hình lành tính:

~~~text
--batch-mode
--no-transfer-progress
~~~

Maven 3.9+ có cách parse theo từng argument trên mỗi dòng. Những flags này chỉ ảnh hưởng output/interaction. Tuy nhiên một commit có thể thay file để thêm **properties, profiles hoặc lựa chọn Maven command behavior** khác. Cần so diff trước khi tin.

Không giả định cách parse comments/multiple args y hệt trên mọi Maven 3 minor: theo tài liệu Maven, Maven 3.9.0 thay đổi yêu cầu tách arguments, Maven 3.9.3 mới hỗ trợ comments trong `maven.config`.

### `jvm.config` ảnh hưởng JVM trước khi plugin lifecycle bắt đầu

JVM flags có thể điều chỉnh memory, system properties và **khả năng nạp thành phần JVM bổ sung**. Nếu một thay đổi thêm JVM agent hoặc custom classpath behavior, đó là thay đổi security boundary, không chỉ tuning.

Maven Enforcer ở `validate` chạy **sau khi JVM được khởi động**; nó không kiểm soát mã đã được nạp từ JVM startup configuration.

### Maven Wrapper cũng là code của repository

Lệnh:

~~~bash
./mvnw clean verify
~~~

trên Linux/macOS, hoặc:

~~~powershell
.\mvnw.cmd clean verify
~~~

trên Windows có thể thực thi **script thuộc repository** trước khi Maven runtime chính hoạt động. Wrapper có thể tải Maven distribution và, tùy wrapper distribution type, wrapper JAR/source code.

Vì vậy trước khi chạy project chưa được review, hãy kiểm tra:

- Diff của `mvnw`, `mvnw.cmd` và wrapper properties.
- `distributionUrl` trỏ đúng nguồn Maven được tổ chức cho phép.
- Khi hỗ trợ, `distributionSha256Sum` để kiểm integrity bản Maven distribution.
- `wrapperSha256Sum` khi project dùng wrapper JAR type phù hợp.
- Không có download URL/redirect/script changes không được phê duyệt.
- CI image sử dụng wrapper chính thức, không tự chạy một shell script từ nguồn không biết.

**Checksum chỉ có giá trị khi expected digest đến từ một kênh đáng tin.** Nếu attacker thay cả distribution URL và checksum trong cùng PR, sự khớp của hai giá trị không chứng minh publisher được tin cậy.

## 7. Script build và external tools

Không phải mọi tác vụ chạy mã đều thuộc JVM plugin do Maven quản lý.

Một số plugin hợp pháp có chức năng:

- Maven AntRun Plugin thực thi Ant tasks.
- Exec Maven Plugin chạy Java class hoặc executable theo configuration.
- Plugins build frontend gọi Node/npm/yarn/pnpm.
- Docker/container build plugins khởi động external process.
- Code generation plugins hoặc annotation processors sinh Java sources.
- Maven Invoker Plugin khởi động builds khác để integration test.
- Test runners chạy JUnit/test fixtures và các binary/container phụ trợ.

Một POM thay đổi từ "plugin tạo file" thành "plugin gọi external tool" có thể làm tăng đáng kể phạm vi quyền. Review cần xem:

- Executable path/command và source của binary.
- Arguments được nối từ property, branch name, PR title hoặc environment variables hay không.
- Working directory và files có thể được sửa.
- Environment variables được truyền sang child process.
- Network egress và credentials của build runner.
- Process lifetime/cleanup khi build fail.
- Chạy trên máy dev, shared CI hay release runner.

**Không phải chỉ plugin có tên `exec` mới nguy hiểm.** Plugin bất kỳ chạy Java trong build process cũng cần được tin; tên plugin/goal không thay thế kiểm tra provenance.

### Scripts ngoài POM

Tệp như `build.sh`, `build.ps1`, pipeline YAML và các script mà CI gọi có thể chạy trước/sau `mvn`. Chúng có thể tự thêm flags, thay `settings.xml`, cấp env secrets, đổi plugin repository hoặc gọi upload tool.

Cần review **cả call chain**:

~~~text
CI workflow
  -> checkout action
  -> setup JDK/Maven
  -> build script
  -> mvnw / Maven
  -> extensions/plugins/tests
  -> publish/cleanup scripts
~~~

Chỉ pin versions trong `pom.xml` chưa đủ nếu script bên ngoài tải và chạy một binary theo URL không cố định.

## 8. Phân biệt ba thời điểm có thể thực thi

| Thời điểm | Ví dụ | Vì sao quan trọng |
| --- | --- | --- |
| **Trước Maven lifecycle** | Wrapper scripts, JVM options/agents, core extensions. | Enforcer và test gate chưa chạy. |
| **Trong lifecycle** | Plugin goals tại `validate`, `generate-sources`, `compile`, `test`, `package`, `verify`, `deploy`. | “Chỉ build” vẫn thực thi code, có thể có filesystem/network access. |
| **Sau hoặc ngoài Maven** | CI scripts, artifact upload hooks, container promotion, reports parser. | Có thể dùng credentials hoặc sửa artifacts sau build. |

Maven lifecycle là cơ chế sắp xếp tasks, **không** là ranh giới sandbox bảo vệ máy.

### `help:effective-pom` có phải lệnh an toàn với mã lạ?

Không coi là chắc chắn an toàn. Để tạo effective model Maven vẫn có thể cần bootstrap project, nạp extensions hoặc thực thi Help Plugin itself. Các operations liên quan dependency/plugin resolution cũng có thể tiếp xúc mã/metadata chưa tin.

**Thứ tự đúng với project chưa tin: static diff/review trước; Maven commands chỉ chạy sau khi có môi trường cô lập phù hợp.**

### `mvn -o` có giúp không?

`-o`/`--offline` hạn chế Maven truy cập remote repositories theo resolver, nhưng **không ngăn plugins/extensions đã cache thực thi**, cũng không phải firewall cho mọi external process mà plugin tự khởi động. Offline mode không thay network isolation và không bảo vệ filesystem secrets.

### `-DskipTests` thì sao?

Skip unit tests không chặn các plugin goals trước `test`, extensions, build scripts hoặc annotation processors. Nó cũng có thể làm build kém tin cậy hơn về mặt chất lượng. Không dùng skip tests như security boundary.

## 9. Tấn công supply chain từ plugin artifact và repository

Maven tải plugin binaries theo tọa độ GAV. Đối với plugins, nguồn quan trọng là `pluginRepositories` và các mirrors/settings tương ứng; project library dependencies thường dùng `repositories`. Không nên dùng `<repositories>` như cách duy nhất để quản trị nơi plugin được tải.

Một thay đổi có thể:

1. Thêm plugin mới.
2. Nâng plugin lên version khác.
3. Thay plugin groupId/artifactId sang nguồn ít được kiểm soát.
4. Thêm `pluginRepositories` trỏ endpoint ngoài allowlist.
5. Thêm plugin dependency override.
6. Đưa plugin version vào property dễ bị profile/CI override.
7. Chuyển plugin sang SNAPSHOT/dynamic version.
8. Đổi repository mirror hoặc settings của CI.
9. Thay Maven distribution trong Wrapper.
10. Thêm core/build extension từ source chưa duyệt.

Điều này có thể xảy ra ngay cả khi phần `<dependencies>` cấp project **không đổi**.

### Vì sao pin plugin version quan trọng?

Nếu version của plugin không khai báo rõ, Maven có thể sử dụng phiên bản từ default bindings/Super POM hoặc resolver metadata tùy cấu hình. Điều đó làm khó tái lập build và review security updates. Pin version trong `<build><plugins>` hoặc `<pluginManagement>` của parent giúp ổn định input.

Ví dụ:

~~~xml
<pluginManagement>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
        </plugin>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.5.4</version>
        </plugin>
    </plugins>
</pluginManagement>
~~~

Đây là **mảnh parent POM**, không phải POM runnable riêng. Nó giữ versions rõ nhưng **không chứng minh mã plugin đã được audit**.

### Enforcer `requirePluginVersions`

Maven Enforcer có rule `requirePluginVersions`, giúp fail nếu plugins cần phiên bản tường minh theo policy. Có thể cấm `LATEST`, `RELEASE` và SNAPSHOT plugin versions; tùy tham số `banMavenDefaults` mà rule có kiểm tra tất cả các lifecycle plugins mặc định không.

**Giới hạn bảo mật:** Enforcer itself là plugin, chạy khi lifecycle đã bắt đầu. Nó có thể phát hiện cấu hình version sai ở giai đoạn kiểm tra, nhưng không sandbox extension đã nạp trước, không verify trust of plugin author và không loại bỏ nguy cơ một phiên bản đã pin bị compromise.

### Tại sao không dùng `LATEST` hoặc version ranges bừa bãi?

Một build có thể lấy code plugin khác vào những ngày khác nhau dù source commit không đổi. Với build tools được thực thi ở quyền CI, đó là rủi ro lớn hơn việc tự động nâng dependency runtime đơn thuần. Nên pin versions, đánh giá upgrades qua PR và test trên runner giới hạn quyền trước khi dùng trong release pipeline.

## 10. Ví dụ runnable, vô hại: plugin chạy ngay ở `validate`

Chúng ta xây một project Java 17 có một **plugin AntRun hợp pháp**. Goal trong profile `safe-execution-demo` chỉ in một dòng thông báo. Nó không đọc secrets, không kết nối mạng, không gọi process nguy hiểm, không sửa file hệ thống.

Mục đích là trực tiếp quan sát rằng **một plugin có thể chạy trước compile/test, chỉ bởi POM configuration**.

Cây thư mục:

~~~text
maven-build-execution-lab/
├── pom.xml
└── src/
    ├── main/java/demo/supplychain/App.java
    └── test/java/demo/supplychain/AppTest.java
~~~

Điều kiện: Maven 3.8+, JDK 17+, dependencies/plugins có thể resolve từ repositories được phép. Chỉ chạy demo này **trên môi trường học tập do bạn kiểm soát**; không đem ví dụ làm bằng chứng rằng mọi plugin AntRun hoặc mọi repository lạ đều an toàn.

### 10.1. Root `pom.xml` đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo.supplychain</groupId>
    <artifactId>maven-build-execution-lab</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
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
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-enforcer-plugin</artifactId>
                <version>3.6.2</version>
                <executions>
                    <execution>
                        <id>environment-baseline</id>
                        <phase>validate</phase>
                        <goals>
                            <goal>enforce</goal>
                        </goals>
                        <configuration>
                            <rules>
                                <requireMavenVersion>
                                    <version>[3.8,)</version>
                                </requireMavenVersion>
                                <requireJavaVersion>
                                    <version>[17,)</version>
                                </requireJavaVersion>
                            </rules>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>

    <profiles>
        <profile>
            <id>safe-execution-demo</id>
            <build>
                <plugins>
                    <plugin>
                        <groupId>org.apache.maven.plugins</groupId>
                        <artifactId>maven-antrun-plugin</artifactId>
                        <version>3.1.0</version>
                        <executions>
                            <execution>
                                <id>safe-echo</id>
                                <phase>validate</phase>
                                <goals>
                                    <goal>run</goal>
                                </goals>
                                <configuration>
                                    <target>
                                        <echo message="SAFE-LAB: AntRun plugin executed during validate"/>
                                    </target>
                                </configuration>
                            </execution>
                        </executions>
                    </plugin>
                </plugins>
            </build>
        </profile>
    </profiles>
</project>
~~~

**Phân tích bảo mật của demo:**

- Compiler/Surefire/JAR Plugin versions được ghim.
- Enforcer được bind `validate` và yêu cầu Maven runtime ít nhất 3.8, Java runtime ít nhất 17. Nó chứng minh environment baseline, **không phải sandbox**.
- AntRun Plugin là code thực thi; chỉ có trong **profile chưa active mặc định**.
- `<target><echo .../></target>` là Ant task **chỉ in thông báo**, không làm việc nguy hiểm.
- Khi bật `-Psafe-execution-demo`, Maven sẽ chạy AntRun goal `run` ở phase `validate` trước compile/test.
- Khi không bật profile, Maven **không chạy execution AntRun này**, nhưng các default lifecycle plugins và Enforcer vẫn chạy.
- Một attacker có thể lợi dụng cơ chế execution tương tự nếu được sửa POM/script mà không có review. Bài không hướng dẫn tạo payload khai thác.

### 10.2. `App.java` đầy đủ

Tạo `src/main/java/demo/supplychain/App.java`:

~~~java
package demo.supplychain;

public final class App {
    private App() {
    }

    public static String message() {
        return "Hello from reviewed Maven build";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

Class này không đọc environment variables, files hoặc network. Với JDK 17, nó compile và chạy bằng `java -cp`.

### 10.3. `AppTest.java` đầy đủ

Tạo `src/test/java/demo/supplychain/AppTest.java`:

~~~java
package demo.supplychain;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AppTest {
    @Test
    void returnsReviewedMessage() {
        assertEquals(
                "Hello from reviewed Maven build",
                App.message());
    }
}
~~~

Surefire `3.5.4` nhận class tên `*Test` và chạy JUnit Jupiter test. Kết quả kỳ vọng: **1 test, 0 failures, 0 errors, 0 skipped** nếu môi trường/plugin repositories hợp lệ.

### 10.4. Thực hành 1 — build bình thường

Trong thư mục chứa `pom.xml` của **demo do bạn tự tạo**, chạy:

~~~bash
mvn --version
java -version
mvn -B -ntp clean verify
~~~

Kỳ vọng:

- Enforcer chạy `environment-baseline` ở `validate`.
- Không có execution `safe-echo` vì profile chưa active.
- Compiler biên dịch `App.java`, Surefire chạy `AppTest`.
- JAR Plugin tạo `target/maven-build-execution-lab-1.0.0-SNAPSHOT.jar`.
- Build kết thúc `BUILD SUCCESS` nếu toolchain và dependencies hợp lệ.

Đây là **kết quả mong đợi theo cấu hình**, không phải bản ghi từ một lần build thực trên máy của người học.

Kiểm tra Java stdout:

~~~bash
java -cp target/classes demo.supplychain.App
~~~

**Stdout chính xác của chương trình:**

~~~text
Hello from reviewed Maven build
~~~

Trên Windows PowerShell, câu lệnh `java -cp target/classes demo.supplychain.App` cũng dùng được vì chỉ có một classpath entry; có thể dùng `target\classes` tương đương.

### 10.5. Thực hành 2 — bật plugin và chỉ chạy `validate`

~~~bash
mvn -B -ntp -Psafe-execution-demo validate
~~~

Trong log Maven, tìm đoạn tương đương:

~~~text
maven-antrun-plugin:3.1.0:run (safe-echo)
[echo] SAFE-LAB: AntRun plugin executed during validate
BUILD SUCCESS
~~~

Dòng log có thể khác về prefix, spacing, thời gian và phiên bản Maven. **Thông điệp xác định ở Ant task** là:

~~~text
SAFE-LAB: AntRun plugin executed during validate
~~~

Đây là minh chứng quan trọng: Maven chưa cần chạy `compile` hoặc `test` mà một plugin đã được thực thi ở `validate`.

### 10.6. Thực hành 3 — full build với profile

~~~bash
mvn -B -ntp -Psafe-execution-demo clean verify
~~~

Kỳ vọng cùng một lần chạy:

1. Enforcer environment baseline ở `validate`.
2. AntRun `safe-echo` in thông điệp.
3. Compiler và Surefire build/test Java.
4. JAR được tạo.
5. Build success.

Sau đó bỏ `-Psafe-execution-demo` và chạy `mvn validate` trên chính demo: không thấy AntRun execution này. **Không suy ra build không có plugin khác:** Enforcer và các default bindings vẫn tồn tại.

### 10.7. Ý nghĩa của minh họa

Một dòng Ant `echo` được phép vì bạn hiểu rõ nội dung và kiểm soát cấu hình. Nhưng nếu một plugin/script khác có quyền đọc filesystem hoặc network, nó có thể thực hiện hành động vượt xa in log. Trong thực tế, cần kiểm tra **mã plugin, source repository, version, cấu hình và quyền runner** chứ không chỉ tên execution `safe-echo`.

**Không thử khai thác bằng cách thêm các command đọc token/SSH keys** vào AntRun. Có thể học cơ chế thực thi đầy đủ chỉ với thông điệp vô hại ở trên.

## 11. Static review trước khi chạy một repository chưa tin cậy

**Quy trình an toàn bắt đầu từ việc đọc file và diff**, không bắt đầu bằng Maven goals.

Một bộ lệnh Git có tính chất xem xét, chạy ở checkout để phát hiện các file đáng rà soát:

~~~bash
git status --short
git diff --name-status -- pom.xml .mvn mvnw mvnw.cmd .github/workflows
git diff -- pom.xml .mvn mvnw mvnw.cmd .github/workflows
git ls-files -- pom.xml .mvn mvnw mvnw.cmd .github/workflows
~~~

Nếu thay đổi đã stage:

~~~bash
git diff --cached -- pom.xml .mvn mvnw mvnw.cmd .github/workflows
~~~

Nếu review so với branch gốc, xác định baseline commit/branch đúng theo quy trình Git của nhóm. Các lệnh trên không tự chạy Maven; tuy vậy Git configuration và các công cụ bạn gọi xung quanh Git cũng thuộc ranh giới tin cậy của máy — trên môi trường nguy cơ cao nên dùng viewer hoặc môi trường cô lập chỉ đọc.

**Danh sách file không thay thế review nội dung.** Nếu POM con/parent nằm trong thư mục module, phải xem từng POM đó nữa; ví dụ `git diff -- pom.xml` ở root **không** tự bao phủ toàn bộ `**/pom.xml`.

### 11.1. Các điểm trong POM cần rà soát

| Khu vực | Câu hỏi bảo mật |
| --- | --- |
| `build/plugins` | Plugin nào, GAV/version, goal/execution/phase nào chạy? |
| `build/pluginManagement` | Các plugin defaults/version nào thay đổi? |
| `build/extensions` | Có nạp extension code mới không? |
| `plugin><extensions>true</extensions>` | Plugin nào được bật extension behavior? |
| `plugin><dependencies>` | Plugin classpath bị override hoặc thêm artifact nào? |
| `pluginRepositories` | Plugin binaries được lấy từ đâu, có ngoài allowlist không? |
| `repositories` | Runtime/test dependencies lấy từ đâu, có mirror lạ không? |
| `parent` | Parent version/repository có đổi, kéo theo executable plugins không? |
| `profiles` | Profile nào active bằng default/property/JDK/OS/file; có script ẩn trong đó không? |
| `properties` | Có property thay command path, plugin version, URL hoặc skip flags không? |
| `distributionManagement` | Đích publish có bị đổi không? |
| `modules` | Có thêm module mới chứa plugin/execution lạ không? |

### 11.2. Các file ngoài POM cần rà soát

- `.mvn/extensions.xml` và user/Maven-installation extensions khi áp dụng.
- `.mvn/maven.config`, `.mvn/jvm.config`.
- `mvnw`, `mvnw.cmd` và `.mvn/wrapper/*`.
- CI workflow YAML, build scripts shell/PowerShell/batch.
- Dockerfile, container entrypoint scripts và package manager scripts được Maven gọi.
- Test setup, test resources, annotation processors và code generation configuration.

Một đổi nhỏ trong `.mvn/jvm.config` có thể chạy sớm hơn tất cả plugins. Một đổi trong CI workflow có thể cấp token cho code mà reviewer không thấy trong `pom.xml`.

### 11.3. Ba tầng review

1. **Nguồn thay đổi:** actor nào đề xuất, thay file nào, có review approval không?
2. **Mã sẽ chạy:** extension/plugin/script nào, version/digest/trust/behavior ra sao?
3. **Quyền khi chạy:** process có secrets, network, host filesystem, cloud metadata, Docker socket hoặc quyền publish không?

Chỉ khi cả ba tầng được xem xét phù hợp mới chuyển sang chạy build hoặc thử plugin trong môi trường được kiểm soát.

## 12. Kiểm soát repositories và dependency provenance

Một plugin có thể được resolve từ `pluginRepositories`, Maven Central hoặc mirror/repository manager. Các repository configs trong POM, parent và `settings.xml` ảnh hưởng đường đi tải binary.

### Chính sách khuyến nghị

- Ưu tiên plugin versions cố định, được phê duyệt theo allowlist.
- Chỉ dùng repository manager/mirrors được tổ chức kiểm soát.
- Phân biệt read proxy repositories với hosted publish repositories.
- Yêu cầu HTTPS/TLS, chính sách checksums và audit download.
- Hạn chế trực tiếp truy cập plugin repositories lạ trong CI.
- Không cho pull request tự thêm repository endpoint rồi chạy bằng credentials có quyền cao.
- Ghi nhận plugin + plugin dependencies + core/build extensions trong inventory/SBOM quy trình build nếu công cụ hỗ trợ.
- Tách caches của untrusted builds khỏi caches được dùng cho privileged release.
- Theo dõi security advisories/changelog của build tool plugins và các runtime quan trọng.

### Checksum/chữ ký có giới hạn gì?

Một SHA-256 checksum khớp giúp kiểm tra bytes so với digest được mong đợi. Nhưng nếu attacker kiểm soát **cả artifact và digest ở cùng một nguồn**, checksum không tự chứng minh tác giả. Chữ ký OpenPGP cũng chỉ có giá trị trust khi public key/fingerprint được xác minh qua kênh độc lập.

Không mặc định Maven 3 **tự xác minh đầy đủ chữ ký nhà phát hành cho mọi plugin** chỉ vì repository cung cấp file `.asc`. Cần chính sách verification/provenance hoặc tooling riêng nếu muốn bảo đảm đó.

### Wrapper checksum

Với Maven Wrapper, tài liệu chính thức mô tả `distributionSha256Sum` và, với wrapper JAR phù hợp, `wrapperSha256Sum` trong `.mvn/wrapper/maven-wrapper.properties`. Các giá trị này giúp phát hiện binary bị đổi so với expected digest, nhưng phải lấy digest từ nguồn tin cậy.

### Cache poisoning

Cache local Maven repository hoặc CI dependency cache có thể chứa artifacts từ lần build trước. Một pipeline dùng cache chung với untrusted job có thể làm mất sự độc lập của privileged job.

Biện pháp:

- Dùng ephemeral runners/containers cho untrusted jobs.
- Tách cache keys/scope/permissions; không cho untrusted job sửa cache privileged.
- Kiểm soát repository artifact immutability.
- Hạn chế tác vụ upload artifacts/cache từ pull request chưa duyệt.
- Rebuild release từ commit đã duyệt với trusted toolchain và plugin resolution.

`mvn -U` kiểm tra updates trong phạm vi Maven, **không chứng minh artifact đáng tin**. `mvn -o` cũng không sandbox một binary đã có trong cache.

## 13. CI chạy pull request không tin cậy: tách quyền

Một CI workflow chạy Maven từ pull request của người ngoài là trường hợp rủi ro cao. Họ có thể thay POM, extension declarations hoặc source tests. Nếu runner đồng thời có repository upload token, cloud credential hoặc GPG signing key, quyền đó có thể bị lạm dụng bởi **bất kỳ build code nào được thực thi**.

### Quy tắc kiến trúc

**PR validation (không tin cậy):**

- Token ở mức read-only khi hệ thống CI hỗ trợ.
- Không cấp release/signing/cloud production secrets.
- Dùng ephemeral runner hoặc container cô lập.
- Giới hạn network egress và filesystem mounts theo nhu cầu.
- Không cho PR thay CI reusable workflow được chạy với quyền elevated mà không review.
- Không publish release, không upload ghi vào hosted repo quan trọng.
- Audit logs và xóa ephemeral environment sau job.

**Release/publish (tin cậy):**

- Chạy từ protected branch/tag hoặc commit đã được phê duyệt.
- Dùng toolchain và plugin versions đã được review.
- Cấp secrets chỉ cho job thực sự cần.
- Có environment approval/staging khi thích hợp.
- Tách signing key và repository publish credential.
- Kiểm tra GAV, artifacts, checksums, provenance và kết quả tests.
- Không dùng build output/cache từ PR chưa tin cậy làm input đặc quyền mà không kiểm chứng.

### Ví dụ permission snippet GitHub Actions

~~~yaml
permissions:
  contents: read
~~~

Đây là **mảnh YAML để minh họa nguyên tắc token read-only**, không phải một workflow chạy được độc lập. Với GitHub Actions, các event/permissions khác nhau có quy tắc cấp secrets khác nhau; phải kiểm tra settings của tổ chức và repository cụ thể.

GitHub cảnh báo đặc biệt về `pull_request_target`: **không checkout và chạy code của pull request không tin cậy trong job có secrets hoặc token quyền cao**. Với workflows cần quyền elevated, tách việc đọc metadata (trusted workflow) với việc chạy code PR (untrusted job), không nối trực tiếp hai trust boundaries.

### Vì sao `pull_request_target` nguy hiểm trong trường hợp này?

Một workflow có thể được định nghĩa từ base branch đáng tin nhưng lại checkout PR head rồi gọi `./mvnw verify`. Từ đó POM/extensions/scripts của PR **được thực thi** trong privileged context. Đây là đường đi rủi ro dù step name chỉ là "Build and test".

Không khẳng định mọi workflow `pull_request_target` đều bị khai thác; điều kiện nguy hiểm là **thực thi nội dung chưa tin cậy cùng quyền/secret không thích hợp**.

### Runner tự quản trị

Self-hosted runner có thể giữ state, tool caches, Docker socket, SSH keys, service accounts hoặc mạng nội bộ. Đối với untrusted PR, ưu tiên runner tạm thời/cô lập; không cho phép container không tin cậy mount Docker socket của host hoặc thư mục secret.

**Container đơn thuần không bảo đảm an toàn** nếu runner cấp host network, privileged mode hoặc shared volumes chứa secrets.

## 14. Enforcer và policy guardrails: hữu ích nhưng không phải “tường lửa”

Maven Enforcer Plugin có các rules hữu ích:

- `requireMavenVersion` và `requireJavaVersion`: runtime baselines.
- `requirePluginVersions`: kiểm soát plugin versions khai báo, cấm dynamic/snapshot versions theo lựa chọn.
- `bannedDependencies`: ngăn dependencies theo policy trong graph được rule xử lý.
- Các rules khác cho dependency convergence và kiến trúc tùy plugin.

### Ba giới hạn bắt buộc nhớ

1. Enforcer là một **plugin**: nếu extension đã chạy ở Maven bootstrap, nó không chặn lại lịch sử đó.
2. Version pinning là điều kiện cần cho reproducibility, **không tự chứng minh binary an toàn**.
3. Rule chỉ có hiệu lực nếu execution được bind/active và không bị skip; chạy `mvn validate` chỉ có ý nghĩa **sau khi đã qua static review và cô lập môi trường**.

Ví dụ một project có thể pass Enforcer mà vẫn chạy một plugin được version-pin nhưng chứa bug hoặc bị compromise. Cần nhiều lớp bảo vệ: reviews, repository controls, signature/provenance, runner isolation, least privilege và audit.

### Cấm bypass trong release

Các flags như `-Denforcer.skip=true` hoặc `-DskipTests` có thể bỏ quality checks nhưng không làm code execution an toàn hơn. Release job không nên cho actor chưa tin cậy tùy ý thay profiles/skip flags để vượt policy.

`-D...skip` là property tùy plugin, không có một “global secure mode” bảo vệ mọi plugins/extensions của Maven.

## 15. Review thay đổi phiên bản plugin như thay đổi mã chạy quyền CI

Một PR bump plugin version từ A sang B nên được xem như **đổi một executable component**:

- Ai duy trì plugin? Source/repository và release history rõ không?
- GAV có đúng groupId/artifactId chính thức không?
- Plugin version mới yêu cầu Java/Maven minimum khác không?
- Plugin dependencies nào đã đổi?
- Changelog có sửa security issues hoặc đổi network/process behavior?
- Plugin có thêm goals hoặc executions mặc định nào không?
- Goal đang bind ở phase nào, có nạp extension không?
- Có thay configuration values, env, command path hay repo URL không?
- Build có dùng cùng version ở local và CI không?
- Đã chạy trên runner không có secrets trước khi áp dụng release chưa?

### Plugin name không phải sự bảo đảm

Tên như `maven-something-plugin`, groupId tương tự một plugin phổ biến hoặc một số lượt download cao không đủ xác nhận provenance. **Namespace lookalikes** có thể gây nhầm; review full coordinates và distribution source.

### Kiểm thử trên môi trường cô lập

Sau static review, có thể chạy CI validation trong môi trường không có secrets, network allowlist, disposable filesystem và cache tách biệt. Quan sát process/network/file changes để đánh giá plugin behavior theo policy. **Đừng cấp quyền publish chỉ để xem một plugin lạ có chạy không**.

## 16. Tình huống minh họa: đổi một file, mở rộng quyền không ngờ

### Tình huống A — thêm plugin vào parent

Parent `pom.xml` có plugin execution mới ở `validate`. Mọi module kế thừa parent có thể chạy goal này trong `mvn verify`, kể cả module không sửa source code.

**Điều tra:** so parent diff, dependencyManagement/pluginManagement vs build/plugins, execution ID, profiles, active modules, effective POM sau khi cách ly.

### Tình huống B — thêm core extension

Một PR thêm `.mvn/extensions.xml`. Kể cả root `pom.xml` không đổi, Maven có thể nạp extension **sớm**. Đánh giá GAV/plugin repository và quyền runner trước khi chạy `mvn validate`.

**Điều tra:** đối chiếu extension publisher/coordinate/version, artifact provenance, thay đổi .mvn/jvm.config, Maven runtime và settings.

### Tình huống C — wrapper thay URL

Một PR chỉ sửa `.mvn/wrapper/maven-wrapper.properties` để wrapper tải Maven distribution từ URL khác. Nếu review chỉ `pom.xml`, bạn sẽ bỏ sót thay đổi ảnh hưởng Maven executable.

**Điều tra:** URL có nằm trong allowlist? Digest được lấy từ đâu? Script `mvnw` có đổi không? CI có enforce trusted wrapper không?

### Tình huống D — build script cần secret mới

CI step thêm environment variable chứa publish token vào job vốn chạy `./mvnw test` trên PR. Ngay cả POM không đổi, build logic/test từ PR giờ có thể tiếp xúc secret.

**Điều tra:** người đề xuất quyền mới, có tách privileged publish job khỏi PR validation không, token scope ra sao và có runner isolation không.

### Tình huống E — plugin dependency override

Plugin version chính được giữ nguyên nhưng child POM thêm `<plugin><dependencies>` với version khác. Classpath plugin thay đổi; báo cáo “không upgrade plugin” có thể che đi sự thay đổi thực của mã được chạy.

**Điều tra:** plugin dependency graph, nguồn GAV, changelog, các lệnh và permissions của plugin.

### Tình huống F — chạy `help:effective-pom` quá sớm

Developer mới checkout repo lạ rồi chạy `mvn help:effective-pom` để "chỉ xem config". Nhưng Maven có thể nạp extensions/project context và chạy code plugin của Help Plugin. Đó không phải điểm bắt đầu static audit.

**Điều tra:** dùng text viewer/Git diff trước. Nếu cần effective POM, chỉ chạy sau khi cô lập và kiểm soát repo/plugin sources.

## 17. Khi phát hiện thay đổi nghi vấn, xử lý ra sao?

Một quy trình ứng phó an toàn:

1. **Không chạy** build/extension/script chưa được review trên developer workstation hoặc release runner có secrets.
2. Ghi rõ commit/PR, file thay đổi, full plugin/extension GAV, command/pipeline sẽ gọi và repository URLs.
3. Tách nội dung đáng ngờ để static review, không cố "kích hoạt thử" trên máy privileged.
4. Nếu đã chạy trên runner có quyền cao, báo incident theo quy trình nhóm; coi credentials đã tiếp xúc có nguy cơ cần rotate/revoke.
5. Kiểm tra audit logs của repository manager, CI, secret manager và các downstream artifacts bị publish trong khoảng thời gian liên quan.
6. Quarantine cache/artifacts hoặc ngừng promotion của build nghi vấn theo policy.
7. Tạo build mới từ commit được duyệt trên ephemeral runner sạch, toolchain/repository pinned.
8. Xác minh artifacts/provenance/chữ ký và consumer behavior trước khi phát hành lại.
9. Ghi root cause và cải thiện CI review gates (plugin allowlist, PR restrictions, wrapper checksum).
10. Không xóa audit evidence hoặc tự chạy script “cleanup” chưa được review.

**Nếu chỉ thấy một plugin chưa biết tên**, đó không tự động là sự cố; trước tiên xác định nguồn, chức năng và lý do nó xuất hiện. Nhưng khi chưa tin, đừng trao quyền secrets chỉ để giảm thời gian review.

## 18. Bài tập thực hành

### Bài A — xác định thứ tự thực thi

Với lab mục 10, hãy dự đoán:

1. `mvn clean verify` không profile: có log `SAFE-LAB` không?
2. `mvn -Psafe-execution-demo validate`: có compile Java không?
3. `mvn -Psafe-execution-demo clean verify`: plugin AntRun chạy ở phase nào?
4. Test `AppTest` chạy tại phase nào?
5. Khi gọi `mvn package` không profile, Enforcer có chạy không?
6. Nếu Enforcer PASS, có chứng minh mọi core extensions đều an toàn không?

**Đáp án:**

- (1) Không có thông điệp từ AntRun execution của profile.
- (2) AntRun có thể chạy tại `validate`, nhưng phase compile chưa được gọi.
- (3) `safe-echo` tại `validate`, trước compile/test.
- (4) Surefire tại `test`.
- (5) Có, vì `package` đi qua `validate` và execution baseline bind ở đó.
- (6) Không. Enforcer chạy sau Maven bootstrap và không phải sandbox.

### Bài B — static review không chạy Maven

Cho một PR làm các thay đổi:

~~~text
M pom.xml
A .mvn/extensions.xml
M .mvn/wrapper/maven-wrapper.properties
M .github/workflows/build.yml
M src/test/java/demo/supplychain/AppTest.java
~~~

Hãy:

1. Xếp hạng các thay đổi cần xem **trước khi chạy Maven**.
2. Chỉ ra nơi có thể nạp code sớm nhất.
3. Ghi rõ những plugin/extension GAV/versions/repos cần xác minh.
4. Kiểm tra build workflow có cấp secrets cho untrusted PR không.
5. Xác định cache và runner privileges.
6. Chọn nơi thực hiện dynamic verification an toàn.

**Gợi ý:** cả năm file đều có thể liên quan. `extensions.xml` và wrapper properties ảnh hưởng bootstrap, CI workflow ảnh hưởng quyền, POM ảnh hưởng plugin/lifecycle, test source được chạy ở `test`. Không chỉ đọc test source rồi bỏ qua build infrastructure.

### Bài C — phân biệt mitigations

Mỗi đề xuất dưới đây có đủ để biến một repo lạ thành an toàn không?

- Chạy `mvn -o verify`.
- Chạy `mvn -DskipTests verify`.
- Chỉ pin plugin versions.
- Chạy Enforcer ở `validate`.
- Chạy trong container có mounted Docker socket và cloud credentials.
- Chạy trong ephemeral runner không secrets, network hạn chế, cache tách biệt **sau khi** static review.

**Đáp án:** năm đề xuất đầu **không đủ** làm ranh giới an toàn. Đề xuất cuối là lớp bảo vệ tốt hơn nhưng cũng không bảo đảm tuyệt đối; phải xem cấu hình isolation và artifacts/repositories có được tin cậy không.

### Bài D — thiết kế CI hai tầng

Tổ chức có job kiểm tra pull request từ fork và job phát hành artifact lên private Maven repository.

Hãy định nghĩa:

1. Job nào nhận repository write token?
2. Job nào được nạp private signing key?
3. Khi nào được phép checkout và chạy PR code?
4. Runner/cache nào được reuse, loại nào không?
5. Làm sao xác minh plugin source và Maven Wrapper distribution?
6. Release job dựa trên branch/tag/commit nào đã được review?
7. Tại sao không dùng `pull_request_target` với untrusted PR checkout và privileged secrets?

**Gợi ý:** PR job không có publish secrets; release job trusted và được approval; publisher chạy từ commit đã được bảo vệ; plugin allowlist/repository proxy và digest verification là các lớp bổ sung.

### Bài E — xử lý phát hiện extension lạ

Một developer thấy thêm một core extension chưa được duyệt, trong khi người đóng góp nói đó chỉ là "build optimization".

Hãy lập checklist:

- Đọc mô tả/changelog/source/publisher và lý do cần extension.
- So toàn bộ Git diff, không chỉ `pom.xml`.
- Kiểm tra scope là core extension hay build extension.
- Xác minh exact coordinates, repository URL và version.
- Dùng ephemeral no-secret runner để quan sát sau static review.
- Không chạy thử trên máy có SSH/cloud/signing credentials.
- Yêu cầu code-owner/security review nếu cần; quyết định allowlist/denylist.
- Ghi và theo dõi quyết định trong PR/issue.

## 19. Checklist review trước khi nhận plugin/extension/script mới

**Nguồn gốc và versions:**

- [ ] GAV/plugin version/extension version đầy đủ, không dùng `LATEST`/`RELEASE` tùy tiện.
- [ ] Publisher và source/release history đủ tin cậy cho mức quyền yêu cầu.
- [ ] Plugin dependency overrides đã được xem.
- [ ] Repository/mirror URLs nằm trong allowlist.
- [ ] Maven Wrapper distribution URL và checksums được review.
- [ ] Có phương pháp cập nhật patches và theo dõi advisories.

**Execution và cấu hình:**

- [ ] Goal/execution ID/phase và inherited parent behavior được hiểu.
- [ ] Core/build extensions và JVM startup options được xem.
- [ ] `.mvn/maven.config` và active profiles được kiểm tra.
- [ ] Các external executable/script paths được xác minh.
- [ ] Test, annotation processing và generated source stages được đánh giá.
- [ ] Không có process/network/file side effects ngoài phạm vi đã duyệt.

**CI và bảo vệ secrets:**

- [ ] Untrusted PR không được cấp publish/signing/cloud production secrets.
- [ ] Token permissions tuân thủ least privilege.
- [ ] Runner ephemeral/cô lập, không mount Docker socket hoặc host secrets.
- [ ] Network egress giới hạn theo nhu cầu.
- [ ] Cache privileged tách khỏi untrusted jobs; artifacts provenance có kiểm tra.
- [ ] Release only từ commit/tag đã review/approved.
- [ ] Pipeline lưu audit trail và có quy trình xử lý bất thường.

**Verification:**

- [ ] Static review xong **trước** khi chạy Maven trên code chưa tin.
- [ ] Dynamic test chạy trên môi trường cô lập phù hợp.
- [ ] Plugin versions và effective model được kiểm tra sau khi trust boundary được thiết lập.
- [ ] Build/test outputs được xem cùng process/network behavior khi cần.
- [ ] Không nhầm Enforcer/`-o`/`skipTests` với sandbox.
- [ ] Không tin BUILD SUCCESS là bằng chứng build code không có hành vi ngoài ý muốn.

## 20. Kết luận

**An toàn phụ thuộc của Maven không chỉ là phiên bản JAR của ứng dụng; nó bao gồm toàn bộ mã được phép chạy để tạo ra artifact.** Maven plugins, plugin dependencies, core/build extensions, wrapper, JVM/Maven configs, tests và scripts có thể mang rủi ro supply chain.

Quy trình đáng tin cậy:

~~~text
Repo/PR chưa tin cậy
        │
        ▼
Static review: POM + .mvn + wrapper + CI scripts
        │
        ▼
Xác minh full GAV, version, publisher, repository, digest
        │
        ▼
Đánh giá execution phase + capabilities + permissions
        │
        ▼
Sandbox/ephemeral runner không secrets + hạn chế network/cache
        │
        ▼
Maven verify + Enforcer + tests + quan sát side effects
        │
        ▼
Approval, release toolchain và artifact provenance
~~~

Những ý quan trọng nhất:

- **Plugin/extension là executable build input**, không phải metadata thụ động.
- **Core extension/Wrapper/JVM configs có thể chạy trước `validate`**, nên Enforcer không phải cơ chế phòng thủ duy nhất.
- `mvn help:effective-pom`, `mvn validate`, `mvn -o` hay `-DskipTests` **không được mặc định xem là an toàn** với repository chưa tin.
- **Pin versions** giúp reproducibility nhưng không xác thực provenance hay ngăn mã độc trong một phiên bản đã pin.
- **Cô lập quyền và secrets** quan trọng bằng review source: mã chưa tin không được chạy chung với publish token, signing key, Docker socket hoặc cache privileged.
- **Rà soát từ CI workflow đến plugin dependencies** trước khi chấp nhận một thay đổi build tool.
- Tài liệu và bài lab chứng minh cơ chế bằng Ant `echo` vô hại; không cần dùng hành vi xâm hại để học cách phòng vệ.

## Tài liệu chính thức

- Apache Maven — Using Extensions: https://maven.apache.org/guides/mini/guide-using-extensions.html
- Apache Maven — Configuring Apache Maven (`.mvn/extensions.xml`, `maven.config`, `jvm.config`): https://maven.apache.org/configure
- Apache Maven — Introduction to the Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Apache Maven — POM Reference (plugins, pluginRepositories, profiles): https://maven.apache.org/pom.html
- Apache Maven — Guide to Configuring Plug-ins: https://maven.apache.org/guides/mini/guide-configuring-plugins.html
- Apache Maven — Guide to Using Multiple Repositories: https://maven.apache.org/guides/mini/guide-multiple-repositories.html
- Apache Maven AntRun Plugin `3.1.0` — Usage: https://maven.apache.org/plugins-archives/maven-antrun-plugin-3.1.0/usage.html
- Apache Maven Enforcer Rule — Require Plugin Versions: https://maven.apache.org/components/enforcer/enforcer-rules/requirePluginVersions.html
- Apache Maven Wrapper — binary checksum verification: https://maven.apache.org/tools/wrapper/
- GitHub Docs — Secure use of GitHub Actions: https://docs.github.com/en/actions/reference/security/secure-use
- GitHub Docs — Securely using `pull_request_target`: https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target

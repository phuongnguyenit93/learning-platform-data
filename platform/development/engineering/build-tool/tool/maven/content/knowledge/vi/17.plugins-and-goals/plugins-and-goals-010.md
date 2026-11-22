# Đọc cảnh báo plugin validation và kiểm tra tương thích Maven

## 1. Vì sao build vẫn thành công nhưng Maven báo cảnh báo?

Maven dựa trên **plugin** để biên dịch, kiểm thử, đóng gói và thực thi các bước mở rộng. Một plugin có thể vẫn chạy được hôm nay nhưng sử dụng Maven API cũ, khai báo dependency plugin không đúng scope, gọi một goal đã bị deprecate hoặc nhận tham số cấu hình không còn được khuyến nghị. Những vấn đề này có thể không làm build thất bại ngay, nhưng **tăng rủi ro khi nâng Maven, Java hoặc chính plugin**.

Từ dòng Maven **3.9.x**, Maven có cơ chế **Plugin Validation** để phát hiện một số vấn đề tiềm ẩn trong plugin và cách dự án cấu hình plugin. Maven 4 tiếp tục dùng cơ chế này trong quá trình nâng cấp hệ sinh thái.

Trong log, có thể thấy dòng tổng quát:

~~~text
[WARNING] Plugin validation issues were detected in ... plugin(s)
~~~

Dấu `...` ở trên là **ký hiệu minh họa**, không phải số lượng plugin cố định. Cảnh báo có thể xuất hiện khi goal chạy hoặc ở cuối build, tùy bản Maven và chế độ báo cáo.

**Điểm mấu chốt:**

- **`BUILD SUCCESS` + plugin validation warning** có nghĩa build hiện tại hoàn tất nhưng Maven phát hiện rủi ro cần xem xét; nó **không chứng minh plugin hoàn toàn tương thích với các bản Maven tương lai**.
- **`BUILD FAILURE`** cần đọc nguyên nhân lỗi đầu tiên: có thể là plugin không chạy được, phiên bản Maven/Java không đủ, POM sai hoặc lỗi dependency/network. Không mặc định mọi failure đều do Plugin Validation.
- **Không thấy cảnh báo** cũng không bảo đảm mọi plugin đều tương thích; Maven chỉ kiểm tra những vấn đề mà cơ chế validation của bản hiện tại nhận diện, với mức hiển thị đang bật.

Bài này tập trung vào việc **đọc đúng cảnh báo**, xác định **ai có thể sửa**, kiểm tra **plugin đang dùng thực tế**, so sánh **yêu cầu Maven/JDK**, và thiết lập quy trình kiểm chứng trước khi nâng Maven 3 sang Maven 4.

## 2. Phân biệt goal, plugin, Maven Core và plugin validation

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| **Maven Core** | Engine đọc POM, giải quyết project model, lifecycle, plugins và repository. | Maven 3.9.x, Maven 3.10.x hoặc Maven 4.x theo bản đang cài. |
| **Maven Plugin** | Artifact cung cấp các goal thực hiện công việc build. | `maven-compiler-plugin`, `maven-surefire-plugin`. |
| **Plugin goal (Mojo)** | Tác vụ cụ thể mà plugin cung cấp. | `compiler:compile`, `surefire:test`. |
| **Plugin parameter** | Thuộc tính dùng để cấu hình goal. | `release` của Compiler Plugin. |
| **Plugin descriptor** | Metadata của plugin về goal, tham số, yêu cầu runtime... | Thông thường trong `META-INF/maven/plugin.xml` của plugin JAR. |
| **Plugin Validation** | Cơ chế kiểm tra một số vấn đề cấu hình và cách plugin sử dụng Maven APIs. | Cảnh báo plugin dùng API deprecated. |
| **POM/model validation** | Kiểm tra tính hợp lệ của project model. | Khai báo trùng một plugin trong `build/plugins`. |

**Plugin Validation và POM/model validation không đồng nghĩa.** Một thông báo `build.plugins.plugin.(groupId:artifactId) must be unique` liên quan cấu trúc POM; một thông báo plugin dùng Maven API đã deprecated liên quan cách plugin được xây dựng. Các phiên bản Maven mới có thể tăng mức nghiêm ngặt của **model validation**, trong khi cấu hình `maven.plugin.validation` chủ yếu điều khiển **báo cáo Plugin Validation**.

Cũng không nhầm **plugin dependencies** với **project dependencies**. Một plugin có classloader và tập dependency riêng. Việc thêm một thư viện vào `project/dependencyManagement` **không tự sửa dependency nội bộ bị khai báo sai của Maven plugin**.

## 3. Hai nhóm cảnh báo Plugin Validation: Internal và External

Theo hướng dẫn chính thức của Apache Maven, Plugin Validation phân loại những vấn đề theo **nơi có thể xử lý**.

### 3.1. Internal: cấu hình của dự án có thể sửa

**Internal issues (project-local)** liên quan đến cách **POM của dự án sử dụng plugin**, chẳng hạn:

- Gọi **goal đã được đánh dấu deprecated**.
- Cấu hình **plugin parameter đã deprecated**.
- Cố đặt giá trị cho **tham số read-only** của plugin.
- Sử dụng một kiểu cấu hình không còn phù hợp với metadata/contract của goal.

Người duy trì dự án thường có thể xử lý bằng cách **sửa `pom.xml`**, đổi goal/parameter sang lựa chọn được tài liệu plugin khuyến nghị hoặc nâng plugin rồi cập nhật cấu hình tương ứng.

Ví dụ một log **mang tính sơ đồ**:

~~~text
[WARNING] ... deprecated plugin goal/parameter ...
[WARNING] ... read-only plugin parameter ...
~~~

Không có goal hoặc tên parameter cụ thể ở trên để tránh gán nhãn deprecated nhầm cho một tham số thực tế; **cần đọc nguyên văn warning của chính plugin đang dùng**. Đối với warning về deprecated parameter, việc đầu tiên là xem **tài liệu goal của đúng phiên bản plugin**, không xóa tham số theo phỏng đoán.

### 3.2. External: lỗi nằm trong bản thân plugin

**External issues** là những vấn đề Maven phát hiện **ở plugin implementation hoặc plugin metadata**, ví dụ:

- Plugin sử dụng **Maven API cũ, đã deprecated**, không phù hợp hướng đi của Maven 4.
- Plugin khai báo dependency vào một Maven Core artifact với scope không đúng; đối với plugin author, các Maven Core APIs phải dùng scope phù hợp, thông thường **`provided`**.
- Plugin vẫn phụ thuộc vào cơ chế cũ mà Maven 4 có thể loại bỏ.

Đây **không phải lỗi mà người dùng cuối sửa được chỉ bằng cách đổi một property của project**. Hướng xử lý thông thường:

1. Xác định **groupId:artifactId:version** của plugin bị cảnh báo.
2. Kiểm tra bản plugin mới hơn tương thích với **Maven/JDK hiện tại**.
3. Nâng bản plugin và chạy lại kiểm thử.
4. Nếu bản mới nhất phù hợp vẫn có cảnh báo, báo lỗi có log tối thiểu, bản Maven/JDK và bước tái hiện cho **người duy trì plugin**.
5. Khi tự phát triển plugin, sửa plugin code/descriptor/dependencies theo API và hướng dẫn phát triển plugin của Maven.

**Đừng “sửa” external issue bằng cách thay scope của dependency ứng dụng hoặc xóa tùy tiện repository.** Đó là hai phạm vi khác nhau.

### Bảng trách nhiệm

| Dấu hiệu | Nhóm chính | Ai thường sửa? | Hướng xử lý |
| --- | --- | --- | --- |
| Goal/parameter deprecated được POM sử dụng | **Internal** | Nhóm dự án | Đổi cấu hình/goal theo tài liệu plugin. |
| POM đặt tham số plugin chỉ-đọc | **Internal** | Nhóm dự án | Xóa cấu hình trái contract và dùng đầu vào được hỗ trợ. |
| Plugin dùng Maven API deprecated | **External** | Tác giả plugin | Nâng plugin hoặc phát hành plugin đã sửa. |
| Plugin dùng Maven Core dependencies sai scope | **External** | Tác giả plugin | Sửa POM của **plugin** và phát hành bản mới. |
| POM khai báo plugin trùng `groupId:artifactId` | **POM/model validation** | Nhóm dự án | Gộp thành một khai báo plugin. |
| Plugin yêu cầu Maven/JDK cao hơn bản đang chạy | **Compatibility/prerequisite** | Nhóm dự án hoặc quản trị build | Chọn bản tương thích hoặc nâng Maven/JDK có kiểm soát. |
| Không tải được plugin từ repository | **Resolution/network** | Nhóm dự án/hạ tầng | Kiểm tra repository, mirror, credentials, artifact. |

Không phải cảnh báo nào mang chữ `plugin` cũng là Plugin Validation. Hãy đọc **toàn bộ dòng thông báo**, loại issue và thời điểm xuất hiện.

## 4. Điều chỉnh độ chi tiết bằng `maven.plugin.validation`

Apache Maven tài liệu hóa user property `maven.plugin.validation` với **năm chế độ**. Giá trị không phân biệt chữ hoa/chữ thường.

| Giá trị | Hiển thị |
| --- | --- |
| **`NONE`** | Không báo cáo Plugin Validation. Chỉ che thông báo, **không sửa vấn đề**. |
| **`INLINE`** | **Mặc định trong hướng dẫn Maven hiện hành:** báo cáo Internal issues tại nơi chúng xảy ra; không mặc định liệt kê đầy đủ External issues. |
| **`BRIEF`** | Báo cáo Internal issues tại chỗ và liệt kê các plugin có External issues ở cuối build. |
| **`SUMMARY`** | Liệt kê các plugin có Internal/External issues ở cuối build. |
| **`VERBOSE`** | Báo cáo chi tiết các vấn đề Internal và External ở cuối build. |

Khi điều tra hoặc chuẩn bị nâng Maven, **`VERBOSE` thường hữu ích nhất** vì một bản Maven chỉ dùng INLINE có thể không cho thấy những rủi ro thuộc plugin code.

~~~bash
mvn --version
mvn -B -ntp -Dmaven.plugin.validation=VERBOSE clean verify
~~~

Lệnh trên chạy build bình thường tới `verify`, nhưng yêu cầu Maven xuất báo cáo validation chi tiết. **Nó không tự làm tất cả warning thành error**. Không nên tự động đánh giá build thất bại chỉ vì log chứa chữ WARNING, trừ khi pipeline có chính sách riêng.

Một số cách sử dụng khác:

~~~bash
mvn -B -ntp -Dmaven.plugin.validation=BRIEF verify
mvn -B -ntp -Dmaven.plugin.validation=SUMMARY verify
mvn -B -ntp -Dmaven.plugin.validation=INLINE verify
~~~

**Không đặt property này trong `<properties>` của `pom.xml` rồi kỳ vọng Maven Core áp dụng.** Tài liệu Maven quy định đây là user/CLI-oriented property; có thể thêm tham số qua **`.mvn/maven.config`** để đồng nhất cách gọi của dự án.

Ví dụ nội dung file **`.mvn/maven.config`** độc lập:

~~~text
-Dmaven.plugin.validation=VERBOSE
~~~

Đối với Maven hiện đại, mỗi dòng `.mvn/maven.config` là một đối số. File này khiến lệnh Maven của dự án yêu cầu chế độ VERBOSE khi Maven dùng đúng root config. Vì có thể tạo log dài và khác biệt giữa các bản Maven, hãy cân nhắc chỉ dùng trong job kiểm chứng tương thích hoặc tạm thời khi debug.

### Có nên dùng NONE để “làm sạch log”?

~~~bash
mvn -Dmaven.plugin.validation=NONE verify
~~~

Cú pháp trên **chỉ ẩn báo cáo validation**. Nó không chuyển plugin cũ sang Maven API mới, không đổi JDK, không giải quyết lỗi build và **không xác nhận plugin tương thích Maven 4**. Dùng NONE chỉ khi có quyết định vận hành ngắn hạn và issue đã được ghi nhận; mặc định nên ưu tiên xử lý nguyên nhân.

### Chỉ loại khỏi validation một plugin đã biết

Maven có property `maven.plugin.validation.excludes` để loại một plugin được chỉ rõ, theo danh tính **groupId:artifactId:version**:

~~~bash
mvn -B -ntp "-Dmaven.plugin.validation.excludes=vn.example:legacy-build-plugin:1.0.0" verify
~~~

Tọa độ `vn.example:legacy-build-plugin:1.0.0` **chỉ để minh họa**, không khẳng định plugin này tồn tại. Cơ chế exclude là **ngoại lệ cho báo cáo validation**, không phải cách bỏ plugin khỏi lifecycle hoặc loại bỏ những cảnh báo khác. Nếu thực sự dùng, nên giới hạn đúng version, ghi lại lý do, ngày xem xét và kế hoạch xử lý; không dùng wildcard tùy tiện.

## 5. Đọc log theo đúng trình tự

Khi thấy cảnh báo, đừng lập tức đổi toàn bộ plugin versions. Đọc theo thứ tự sau:

**Bước 1 — phiên bản công cụ thực sự chạy:**

~~~bash
mvn --version
java -version
~~~

`mvn --version` cho biết bản Maven và Java runtime Maven dùng. **Java mà Maven đang chạy có thể khác Java được tìm thấy bởi một shell/IDE khác**, nhất là khi máy có nhiều JDK hoặc CI dùng toolchain.

**Bước 2 — phân biệt cảnh báo và lỗi dừng build:**

~~~text
[WARNING] ...
[INFO] BUILD SUCCESS
~~~

hoặc:

~~~text
[ERROR] ...
[INFO] BUILD FAILURE
~~~

Đây chỉ là **dạng log rút gọn**. Build success không xóa rủi ro; build failure không mặc nhiên do Plugin Validation. Nếu build thất bại, cần đọc **root cause** phía trước `BUILD FAILURE`, không chỉ dòng cuối.

**Bước 3 — tìm đúng plugin bị nêu tên:** ghi lại **groupId, artifactId, version, goal và execution ID** nếu log cung cấp. Ví dụ dòng goal có thể ở dạng:

~~~text
--- compiler:3.13.0:compile (default-compile) @ plugin-compat-demo ---
~~~

Dòng trên minh họa cấu trúc nhận diện goal, không phải thông báo validation và không bảo đảm log bản Maven của bạn hiển thị y hệt.

**Bước 4 — xác định nhóm:** báo cáo liên quan goal/parameter ở POM là Internal; báo cáo deprecated Maven API trong plugin là External; duplicated plugins có thể là model validation.

**Bước 5 — chọn sửa hợp lý:** chỉnh POM nếu Internal/model, nâng hoặc báo tác giả plugin nếu External; kiểm tra yêu cầu Maven/JDK nếu có dấu hiệu version incompatible.

**Bước 6 — chạy lại build và đối chiếu:** ghi lại warning nào biến mất, warning nào mới xuất hiện, plugin version đã thay đổi gì và test nào đã chạy thực sự.

### Một warning có thể đến từ plugin gián tiếp

Không phải plugin nào xuất hiện trong build đều được bạn ghi tường minh ở `build/plugins`. Packaging `jar`, `war`, parent POM, profile và lifecycle mapping có thể làm Maven dùng những plugin mặc định. Khi warning nêu plugin lạ, đừng kết luận thư viện ứng dụng đã “bí mật gọi nó”; xem **effective POM**, lifecycle/packaging và log goal.

## 6. Kiểm tra đúng plugin version đang được sử dụng

Một dự án Maven có thể xác định plugin version tại nhiều nơi:

- `build/plugins/plugin/version` của chính module.
- `build/pluginManagement/plugins` từ POM hiện tại hoặc parent.
- Cấu hình do profile đang active đưa vào.
- Binding và cơ chế quản lý phiên bản của Maven Super POM hoặc core theo phiên bản đang chạy.
- Cách gọi goal trực tiếp bằng plugin prefix hoặc tọa độ đầy đủ.

**Pin version của những plugin quan trọng** trong project/parent để không phụ thuộc ngầm vào việc Maven thay đổi default plugin version.

### Xem effective POM

~~~bash
mvn help:effective-pom -Doutput=effective-pom.xml
mvn help:active-profiles
~~~

Xem phần `build/plugins` và `build/pluginManagement`, cũng như những `executions`, `configuration` và `version` đã được hợp nhất. **Một plugin chỉ xuất hiện trong `pluginManagement` không tự chứng minh goal của nó đang chạy**; plugin management chủ yếu đặt version/configuration khi plugin được sử dụng qua binding/khai báo.

Ở dự án nhiều module, phải kiểm tra **module thật sự chạy goal**. Một parent packaging `pom` có lifecycle binding khác module `jar`; log của parent không đại diện cho plugin trong từng child.

### Dùng Help Plugin để xem goal/parameter

~~~bash
mvn help:describe -Dplugin=org.apache.maven.plugins:maven-compiler-plugin:3.13.0 -Dgoal=compile -Ddetail
~~~

Help Plugin mô tả goal của **đúng plugin/version được chỉ định**: mục tiêu, parameter, default, read-only/deprecated metadata nếu plugin công bố. Đây là cách hữu ích để xác nhận POM có dùng đúng tên parameter và goal không.

**Giới hạn:** `help:describe` không thay thế toàn bộ báo cáo Plugin Validation, không tự kiểm thử code plugin với mọi bản Maven và có thể phải tải plugin từ repository. Tài liệu HTML của plugin, release notes và source code của plugin vẫn là nguồn cần đối chiếu khi warning phức tạp.

### Một lệnh gọi goal trực tiếp khác build lifecycle

~~~bash
mvn compiler:compile
~~~

không hoàn toàn tương đương:

~~~bash
mvn compile
~~~

Lệnh đầu gọi goal trực tiếp và cách plugin prefix/version được giải quyết có thể ảnh hưởng plugin nào chạy. Lệnh sau đi qua lifecycle tới phase compile và thực hiện các goal đã bind. Khi điều tra warning xuất hiện trong CI, **chạy lại đúng command line/phase/profile đã tạo cảnh báo**, không thay bằng một lệnh có vẻ tương đương.

## 7. Kiểm tra tương thích trên nhiều trục

Một plugin chạy được chỉ khi **tập điều kiện của môi trường và API** phù hợp. Đừng chỉ so sánh một con số version.

| Trục | Điều cần kiểm tra | Ví dụ lỗi |
| --- | --- | --- |
| **Maven runtime** | Plugin yêu cầu tối thiểu Maven version nào? | Plugin mới cần Maven 4, CI vẫn dùng Maven 3. |
| **Java chạy Maven** | Plugin yêu cầu JDK tối thiểu nào? | Plugin được biên dịch bằng Java 17 nhưng Maven chạy trên JDK 11. |
| **Java target của dự án** | `maven.compiler.release` và toolchain nào? | JDK chạy Maven không hỗ trợ `--release 21`. |
| **Maven API tương thích** | Plugin có dùng APIs deprecated/removed không? | Warning external trong Plugin Validation; Maven 4 bỏ API cũ. |
| **Plugin descriptor** | Goal, parameter, required Maven/Java version có đúng không? | Không tìm thấy goal hoặc parameter bị deprecated/read-only. |
| **Plugin dependencies** | Plugin có khai báo Maven Core dependencies đúng scope không? | External issue hoặc classloader conflict. |
| **POM/model của dự án** | Duplicate plugins, cấu hình goal/parameter hợp lệ? | Maven mới nghiêm ngặt hơn và từ chối model. |
| **Extensions và toolchains** | Build extension tương thích Maven mới; JDK toolchain tồn tại? | Extension tải được nhưng không khởi tạo; toolchain yêu cầu chưa có. |

### Java runtime của Maven khác Java release của ứng dụng

Trong POM:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Đây là **đoạn cấu hình**, nghĩa là Maven Compiler Plugin biên dịch source theo mức Java 17 khi có compiler phù hợp. Nó **không** tự làm tiến trình Maven chạy trên JDK 17 hoặc bảo đảm tất cả plugin chạy được trên mọi JDK.

Nếu `mvn --version` báo Maven đang chạy dưới Java 11 nhưng plugin mới yêu cầu Java 17, đặt `maven.compiler.release=17` **không sửa được yêu cầu Java để thực thi plugin**. Cần chọn JDK chạy Maven phù hợp hoặc phiên bản plugin hỗ trợ Java hiện tại. Maven Toolchains có thể cung cấp JDK khác cho một số plugin tác vụ, nhưng không biến JVM của Maven thành JVM khác và không tự sửa tất cả plugin prerequisites.

### Kiểm tra bảng System Requirements của đúng plugin version

Trang tài liệu chính thức của từng Apache Maven plugin thường có **Plugin Info → System Requirements**, ghi yêu cầu Maven/JDK tối thiểu và lịch sử yêu cầu theo từng phiên bản.

Ví dụ tài liệu **Maven Compiler Plugin** ghi các phiên bản **3.13.0–3.16.0** yêu cầu tối thiểu Maven **3.6.3** và JDK **8** để chạy plugin; trong khi nhánh Compiler Plugin **4.x beta** có yêu cầu Maven 4 RC và Java 17. Đây là **yêu cầu của chính plugin**, không có nghĩa dự án Java 17 có thể biên dịch bằng JDK 8 hoặc mọi plugin 4.x đều dùng được trên Maven 3.

Do đó khi chọn version plugin:

1. Xác định bản plugin đang được dùng trong log/effective POM.
2. Mở **trang tài liệu đúng nhánh/version** của plugin.
3. Đọc yêu cầu **Maven** và **JDK** tối thiểu.
4. Đối chiếu với `mvn --version` ở local **và CI**.
5. Xem release notes khi đổi major plugin version vì goal/parameter behavior có thể thay đổi.
6. Build/test thật trên đúng môi trường đích.

**Không tự động nâng plugin lên version mới nhất mà bỏ qua System Requirements.** Tên plugin giống nhau không có nghĩa mọi major version tương thích với Maven cũ.

## 8. Ví dụ Java 17 chạy được: dùng plugin đã chốt version và kiểm chứng

Ví dụ này cố ý dùng **plugin version rõ ràng** và một lớp Java đơn giản. Nó cho phép thực hành các lệnh kiểm chứng mà **không cố tạo warning giả**: trên các bản Maven phù hợp và plugin không có vấn đề, có thể **không có Plugin Validation warning**, và đó là kết quả bình thường.

Yêu cầu: JDK 17+, Maven 3.9.x hoặc phiên bản Maven phù hợp với các plugin được chọn, khả năng tải JUnit và Maven plugins từ repository đã cấu hình.

Cấu trúc:

~~~text
plugin-compat-demo/
├── pom.xml
└── src/
    ├── main/java/vn/example/plugincheck/Main.java
    └── test/java/vn/example/plugincheck/MainTest.java
~~~

### 8.1. pom.xml hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>plugin-compat-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
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
                <version>3.2.5</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-enforcer-plugin</artifactId>
                <version>3.6.3</version>
                <executions>
                    <execution>
                        <id>check-maven-and-java-runtime</id>
                        <phase>validate</phase>
                        <goals>
                            <goal>enforce</goal>
                        </goals>
                        <configuration>
                            <rules>
                                <requireMavenVersion>
                                    <version>[3.9,)</version>
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
</project>
~~~

Giải thích:

- Compiler Plugin `3.13.0` dùng thuộc tính `maven.compiler.release=17`; Maven đang chạy vẫn cần JDK/Toolchain phù hợp để biên dịch Java 17.
- Surefire `3.2.5` chạy JUnit Jupiter ở test; JAR Plugin `3.4.2` tạo JAR thường.
- Enforcer `3.6.3` gắn goal `enforce` vào phase `validate`; hai rule **requireMavenVersion** và **requireJavaVersion** từ chối build nếu môi trường không đạt Maven 3.9+ hoặc Java 17+.
- Hai rule Enforcer là **chính sách kiểm tra điều kiện môi trường do dự án khai báo**, **không phải Plugin Validation của Maven Core**. Chúng có thể tạo `BUILD FAILURE` có chủ đích, trong khi Plugin Validation có thể chỉ đưa ra WARNING.
- Đây là những version minh họa có chốt cụ thể để tái lập, **không khẳng định mới nhất** tại thời điểm người đọc thực hành.

### 8.2. src/main/java/vn/example/plugincheck/Main.java

~~~java
package vn.example.plugincheck;

public final class Main {
    private Main() {
    }

    public static int add(int a, int b) {
        return a + b;
    }

    public static void main(String[] args) {
        System.out.println("Plugin compatibility OK: " + add(2, 3));
    }
}
~~~

### 8.3. src/test/java/vn/example/plugincheck/MainTest.java

~~~java
package vn.example.plugincheck;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class MainTest {
    @Test
    void addsTwoNumbers() {
        assertEquals(5, Main.add(2, 3));
    }
}
~~~

### 8.4. Build, validation và stdout đáng tin

Từ thư mục `plugin-compat-demo`:

~~~bash
mvn --version
mvn -B -ntp -Dmaven.plugin.validation=VERBOSE clean verify
java -cp target/classes vn.example.plugincheck.Main
~~~

Khi Maven/JDK/plugin/repository đúng và test thành công, build tạo các class và báo cáo Surefire; dòng stdout **chính xác của riêng lệnh Java cuối cùng** là:

~~~text
Plugin compatibility OK: 5
~~~

Maven compile/test/build **không mặc nhiên gọi `Main.main`**; lệnh Java cuối cùng mới in chuỗi này. Chạy từ `target/classes` không cần thêm JUnit ở runtime vì mã Main chỉ dùng API JDK.

Nếu Plugin Validation không phát hiện lỗi trong các plugin được gọi, có thể không có báo cáo warning. **Không tạo ra một warning giả để “hoàn thành bài”**: mục tiêu là biết đọc những warning có thật khi môi trường/plugin cần được sửa.

### 8.5. Kiểm tra goal đang dùng

~~~bash
mvn help:effective-pom -Doutput=effective-pom.xml
mvn help:describe -Dplugin=org.apache.maven.plugins:maven-compiler-plugin:3.13.0 -Dgoal=compile -Ddetail
~~~

Đối chiếu plugin version trong effective POM với dòng goal thực tế của build. Nếu thay POM mẫu vào parent khác, version/config có thể bị hợp nhất theo quy tắc inheritance/management nên cần xem kết quả tại module đang chạy.

## 9. Ví dụ cấu hình lỗi: trùng plugin declaration

Plugin Validation không phải loại warning duy nhất quan trọng khi nâng Maven. **POM model validation** cũng có thể báo duplicate plugin declarations.

Giả sử `build/plugins` của dự án có **hai khối cùng groupId/artifactId** như sau:

~~~xml
<plugins>
    <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
    </plugin>
    <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <configuration>
            <release>17</release>
        </configuration>
    </plugin>
</plugins>
~~~

Đây là **đoạn sai có chủ ý**, **không dùng nó để thay POM chạy được ở mục 8**. Maven 3.9.x có thể báo warning về plugin trùng; các phiên bản mới hơn có thể từ chối model hoặc xem đây là lỗi nghiêm trọng. Đặc biệt, tài liệu **Maven 3.10.0** mô tả việc nâng mức kiểm tra POM khiến một số warning trước đây trở thành failure.

Sửa bằng cách **gộp**:

~~~xml
<plugins>
    <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
        <configuration>
            <release>17</release>
        </configuration>
    </plugin>
</plugins>
~~~

Điều cần học:

- **Một plugin chỉ nên có một entry cho mỗi groupId:artifactId** trong cùng danh sách `build/plugins`.
- Có thể có **nhiều execution** trong cùng entry plugin, với execution IDs rõ ràng, thay vì tạo plugin entry trùng.
- Phải hiểu POM inheritance nếu parent/child đều cấu hình plugin; Maven có cơ chế merge hợp lệ giữa các POM. Nó **khác** với khai báo hai entry trùng trong cùng một danh sách.
- Đừng dùng `maven.plugin.validation=NONE` để chữa duplicate POM: suppression plugin validation **không phải cách sửa POM model**.

## 10. Cách xử lý khi cảnh báo đến từ bản thân plugin

Giả sử báo cáo `VERBOSE` nêu một plugin sử dụng Maven API deprecated. Thứ tự xử lý hiệu quả:

1. **Xác định plugin**: tọa độ đầy đủ, bản Maven/JDK, goal đang thực thi, log cảnh báo.
2. **Tìm bản plugin đã sửa** phù hợp với Maven hiện tại. Đọc release notes, changelog, compatibility table của **đúng bản**.
3. **Nâng version có kiểm soát**: pin ở POM/parent và chạy lại kiểm thử. Chưa vội thay đồng thời toàn bộ Maven/JDK/plugin versions, vì sẽ khó biết thay đổi nào sửa lỗi.
4. **Nếu vẫn có cảnh báo** ở bản plugin mới phù hợp, lập issue cho maintainer: cung cấp minimal reproducer, log đã loại thông tin nhạy cảm, Maven/JDK versions và expected behavior.
5. **Nếu plugin không còn được duy trì**, cân nhắc thay bằng plugin được bảo trì, hoặc trì hoãn nâng Maven major nếu rủi ro không chấp nhận được.
6. **Chỉ khi hiểu và chấp nhận rủi ro**, cân nhắc `maven.plugin.validation.excludes` như ngoại lệ báo cáo. Việc exclude không đảm bảo plugin vẫn chạy khi Maven xóa API cũ.

### Nếu bạn là tác giả Maven plugin

Với plugin do tổ chức tự phát triển, cần nhìn vấn đề từ **plugin project**, không phải POM ứng dụng sử dụng plugin:

- Dùng Maven Plugin Tools/Maven Plugin Plugin để sinh descriptor đúng goal, parameter, default và metadata.
- Không phụ thuộc vào APIs Maven Core đã bị deprecated nếu có public replacement được hỗ trợ.
- Các Maven Core artifacts/API trong plugin POM cần scope phù hợp, thông thường `provided`, tránh mang các bản Maven Core xung đột vào plugin classloader.
- Kiểm tra plugin source annotations, injection, thread safety và compatibility requirements.
- Chạy integration tests với các bản Maven được tuyên bố hỗ trợ; kiểm tra đặc biệt khi Maven 4 bỏ cơ chế Maven 2 cũ, ví dụ dependency injection lỗi thời.
- Công bố release notes và **System Requirements** rõ ràng để người dùng biết Maven/JDK tối thiểu.

Tài liệu Maven 4 khuyến nghị dùng JSR-330 thay cho những cơ chế dependency injection cũ đã bị loại bỏ trong Maven 4. Việc plugin xây dựng trên API đã bị xóa có thể từ cảnh báo sớm biến thành lỗi runtime khi nâng cấp.

## 11. Maven 3.9.x, Maven 3.10.x và Maven 4: lưu ý khi nâng cấp

### Maven 3.9.x: quan sát và phân loại cảnh báo

Maven 3.9.x đã bổ sung nhiều kiểm tra plugin, với cách hiển thị mặc định được điều chỉnh giữa các phiên bản nhỏ. Theo Maven 3.9.3 release notes, chế độ mặc định trở lại báo cáo **inline**, tập trung vào những vấn đề cấu hình của dự án; External issues không được mặc định in đầy đủ.

Vì vậy, muốn đánh giá rủi ro nâng cấp **không chỉ chạy `mvn verify` rồi thấy ít warning**. Nên chạy **`-Dmaven.plugin.validation=VERBOSE`** và đọc cả Internal lẫn External.

### Maven 3.10.x: POM validation nghiêm hơn

Trong Maven 3.10.0 release notes, Maven mô tả việc nâng mức kiểm tra POM: một số POM có **duplicate plugin entries, duplicate dependency entries hoặc repository IDs không hợp lệ** có thể thất bại thay vì chỉ warning như một số bản 3.9.x.

**Đó là POM/model validation**, không nên nhầm với plugin implementation warnings. Khi cùng một dự án chạy trên Maven 3.9 nhưng fail trên 3.10, kiểm tra trước tiên lỗi model/duplicate/coordinate cụ thể, rồi mới xem tới Plugin Validation. Không sử dụng tùy chọn tắt validation như biện pháp lâu dài khi mô hình POM thực sự sai.

### Maven 4: chuẩn bị bằng một build có kiểm chứng

Maven 4 có nhiều thay đổi API và lifecycle/model; một số plugin Maven 2 cũ hoặc plugin dùng cơ chế injection đã bị loại có thể không chạy. Hướng dẫn Maven khuyến nghị:

1. **Chuẩn bị**: làm build ổn định trên Maven 3 đang được hỗ trợ; nâng plugin tới các bản cuối cùng tương thích Maven 3; xử lý warnings.
2. **Thử song song**: build với Maven 4 RC và JDK yêu cầu (Maven 4 sử dụng Java 17 trở lên ở các bản hiện đại); ghi nhận vấn đề riêng của plugin.
3. **Chỉ chuyển chính thức** khi CI, plugin executions, tests, packaging và deploy được xác nhận, sau đó mới dùng những khả năng mới của Maven 4.

**Đừng tự động nâng mọi plugin lên nhánh 4.x trước khi chuyển Maven Core**: nhiều plugin major 4.x yêu cầu Maven 4 RC và Java 17. Một dự án đang chạy Maven 3 cần version plugin tương thích Maven 3, ngay cả khi bản plugin 4.x có nhiều tính năng hơn.

### Ma trận kiểm chứng đề xuất

| Môi trường | Mục tiêu |
| --- | --- |
| Maven 3.x được đội đang dùng + JDK 17 | Giữ baseline đang vận hành thành công. |
| Maven 3.x mục tiêu nâng cấp + JDK 17 | Phát hiện POM/model validation nghiêm hơn và khác biệt plugin/runtime. |
| Maven 4 RC được đội chọn + JDK 17+ | Tìm rủi ro API/plugin/goal/config trước quyết định migrate. |
| JDK khác được hỗ trợ theo sản phẩm (nếu có) | Xác nhận yêu cầu runtime plugin và bytecode/test phù hợp. |

**Không giả định version Maven mới nhất hoặc plugin mới nhất từ trí nhớ.** Lấy bản cụ thể từ `mvn --version`, trang Apache Maven Releases và release notes tại thời điểm nâng cấp, rồi ghi vào kết quả CI.

## 12. CI: kiểm tra tương thích mà không che giấu lỗi

Một job CI kiểm chứng có thể chạy:

~~~bash
mvn -B -ntp -Dmaven.plugin.validation=VERBOSE clean verify
~~~

Nếu repo có Maven Wrapper, dùng wrapper để cố định Maven Core:

~~~bash
./mvnw -B -ntp -Dmaven.plugin.validation=VERBOSE clean verify
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd -B -ntp -Dmaven.plugin.validation=VERBOSE clean verify
~~~

**Các nguyên tắc CI hữu ích:**

- Lưu log/build scan theo chính sách bảo mật; đánh dấu đúng vị trí Plugin Validation issues, không chỉ đếm chuỗi `[WARNING]`.
- Dùng Maven Wrapper/Maven version policy để local và CI không vô tình chạy bản khác nhau.
- Chốt plugin versions, nhưng **cập nhật định kỳ có kiểm thử** thay vì để plugin cũ vô thời hạn.
- Chạy cả `mvn test`/`verify` và bước đóng gói nếu plugin bị cảnh báo có goal hoạt động trong phase khác.
- Với multi-module, kiểm tra đủ các module/packaging (`jar`, `war`, `pom`) hoặc các profile được dùng trong CI; một build chỉ chạy phase `validate` có thể chưa gọi plugin cần kiểm chứng.
- Một số cảnh báo chỉ xuất hiện khi plugin **được thực thi**; nên chạy đúng lifecycle, profile và goal của pipeline thật.
- Xem xét **Maven 4 `--fail-on-severity`** trong môi trường hỗ trợ nếu đội muốn chặn build theo mức severity; đó là chính sách xử lý log, **không phải thay thế cho việc sửa nguyên nhân**.
- Nếu một warning mới có rủi ro cao, dừng việc nâng Maven/plugin major cho tới khi đã xác định action owner và kế hoạch xử lý.

### Không biến mọi WARNING thành cùng một lỗi

Maven log có thể chứa thông báo từ compiler, test, resolver, checksum, POM model hoặc Plugin Validation. Một pipeline dùng regex thô tìm chữ `WARNING` dễ báo động giả hoặc bỏ sót vấn đề khác. Nên phân nhóm dựa trên **nguồn phát sinh, loại warning và severity**, rồi đưa vào quality policy của nhóm.

Nếu có cảnh báo Plugin Validation nhưng build success, có thể lưu một danh sách kỹ thuật cần xử lý; quyết định chặn release tùy rủi ro và policy, không suy diễn rằng Maven đã tự đánh fail.

## 13. Bảng lỗi thường gặp và cách đọc

| Triệu chứng | Loại vấn đề | Điều cần kiểm tra |
| --- | --- | --- |
| `Plugin validation issues were detected` | Plugin Validation | Bật `VERBOSE`; xem plugin/issue thuộc Internal hay External. |
| Deprecated plugin goal/parameter | Internal | Kiểm tra documentation và thay goal/parameter được hỗ trợ. |
| Read-only plugin parameter | Internal | Bỏ cấu hình trái metadata; tìm cách đặt thuộc tính hợp lệ. |
| Plugin uses deprecated Maven APIs | External | Cập nhật plugin phù hợp; nếu vẫn xảy ra thì báo maintainer. |
| Plugin dependency on Maven Core with inappropriate scope | External | Tác giả plugin sửa plugin POM/dependencies; người dùng nâng plugin. |
| Duplicate declaration of plugin | POM/model validation | Gộp các entry plugin trùng, không coi là warning plugin code. |
| `requires Maven version ...` | Runtime prerequisites | Xem plugin System Requirements và Maven đang chạy; chọn version phù hợp. |
| `UnsupportedClassVersionError` | Java runtime/bytecode | Xem JDK chạy Maven và bytecode của plugin; cập nhật JDK hoặc plugin. |
| `release version 21 not supported` | Java compiler/toolchain | JDK thực sự dùng để compile phải hỗ trợ `--release 21`; kiểm tra toolchain. |
| `No plugin found for prefix ...` | Plugin prefix resolution | Kiểm tra tên prefix, plugin groups, plugin repositories và metadata. |
| `PluginResolutionException` | Repository/resolution | Kiểm tra plugin artifact/version, mirror, credentials, network. |
| `MojoExecutionException`/`MojoFailureException` | Plugin goal runtime | Đọc root cause; không mặc định là lỗi Plugin Validation. |
| Warning chỉ xảy ra trên CI | Khác biệt môi trường | So Maven/JDK, profiles, settings, plugin version, effective POM. |
| Không thấy External warning ở mode mặc định | Độ chi tiết hiển thị | Dùng `-Dmaven.plugin.validation=VERBOSE`. |
| Bật `NONE` mà build vẫn fail | Lỗi thực tế không do báo cáo | Đọc ERROR root cause, kiểm tra plugin/POM/prerequisites. |

**Chẩn đoán theo bằng chứng:** ghi dòng log cụ thể, goal/execution, tọa độ plugin, Maven/JDK thực dùng; **không “sửa” lỗi bằng cách xóa toàn bộ cache hoặc loại dependency ngẫu nhiên**.

## 14. Khi cần log sâu hơn

Nếu đã bật VERBOSE nhưng vẫn chưa rõ dependency/API/goal nào gây lỗi:

~~~bash
mvn -X -B -ntp clean verify
~~~

`-X` bật debug logging, có thể giúp xác định plugin realm/classloader, parameters, repository và chi tiết lỗi. **Không chia sẻ nguyên log ra công khai**: đường dẫn nội bộ, URL repository, user configuration hoặc dữ liệu nhạy cảm có thể xuất hiện.

Kết hợp:

~~~bash
mvn help:effective-pom -Doutput=effective-pom.xml
mvn help:active-profiles
mvn help:describe -Dplugin=org.apache.maven.plugins:maven-compiler-plugin:3.13.0 -Dgoal=compile -Ddetail
~~~

Với Maven Wrapper, thay `mvn` bằng wrapper phù hợp. Khi nghi ngờ một plugin do parent mang vào, effective POM và log thực thi là hai nguồn chứng minh hữu ích. Với plugin do tổ chức tự viết, xem thêm plugin descriptor và thử plugin trong project tái hiện tối thiểu.

**Không chỉnh `effective-pom.xml`**: đó là đầu ra của Help Plugin để quan sát model, không phải POM nguồn. Muốn sửa, tìm đúng `pom.xml` của module/parent/profile quản lý plugin.

## 15. Quy trình xử lý một cảnh báo tới khi đóng issue

Một quy trình review có thể gồm:

1. **Ghi nhận**: sao lại đúng warning (đã loại thông tin nhạy cảm), Maven version, JDK version, OS/CI, plugin coordinates, goal và phase.
2. **Phân nhóm**: Internal, External, POM/model validation, prerequisite error hay unrelated warning.
3. **Xác định owner**: nhóm ứng dụng sửa Internal/POM; plugin maintainer sửa External; nhóm build platform xử lý Maven/JDK hoặc CI policy.
4. **Đối chiếu tài liệu plugin**: System Requirements đúng version, goal/parameter metadata và release notes.
5. **Chọn thay đổi nhỏ nhất đủ sửa**: sửa POM, nâng đúng plugin hoặc điều chỉnh Maven/JDK; tránh nâng tất cả một lần.
6. **Kiểm chứng**: chạy cùng command với `VERBOSE`, xem warning biến mất hoặc đã được giải thích; xác nhận tests/package/app vẫn đúng.
7. **Chạy ma trận phiên bản** nếu mục tiêu là nâng Maven/JDK major.
8. **Rà lại exclusions/suppression**: nếu đã dùng `NONE` hay `excludes`, xác định thời hạn và cách xóa ngoại lệ.
9. **Ghi kết luận**: đã sửa ở version nào, kết quả CI, warning còn lại và rủi ro được chấp nhận nếu có.

Một warning có thể được xếp lịch sửa nếu plugin vẫn chạy tốt và team chưa chuyển Maven major. Nhưng **không nên xem warning là vĩnh viễn vô hại**: Plugin Validation tồn tại để báo trước các hành vi có thể gãy ở bản Maven tương lai.

## 16. Những hiểu lầm cần tránh

**“`BUILD SUCCESS` nghĩa không có vấn đề tương thích.”** Sai: plugin validation có thể cảnh báo dù build hiện tại vẫn hoàn tất.

**“Mọi `[WARNING]` trong Maven đều là Plugin Validation.”** Sai: có POM validation, compiler warning, metadata/repository warning và nhiều nguồn khác.

**“Plugin validation warning nghĩa là plugin chắc chắn lỗi ở Maven 4.”** Sai: cảnh báo chỉ báo rủi ro do cơ chế kiểm tra phát hiện, không phải phép thử đầy đủ với mọi version.

**“Không có warning ở INLINE nghĩa là không có External issues.”** Sai: chế độ này mặc định không liệt kê đầy đủ External issues.

**“Bật VERBOSE sẽ fail build nếu có warning.”** Sai: VERBOSE là **độ chi tiết báo cáo**, không phải chính sách fail-on-warning.

**“Đặt `maven.plugin.validation=NONE` trong POM để sửa lỗi.”** Sai: property điều khiển validation không phải POM property được hỗ trợ và NONE chỉ che hiển thị.

**“Thêm dependency vào `dependencyManagement` của ứng dụng sẽ sửa Maven plugin dùng Maven Core sai scope.”** Sai: đó là vấn đề plugin implementation.

**“`maven.compiler.release=17` làm Maven chạy bằng JDK 17.”** Sai: cần kiểm tra `mvn --version` và toolchain.

**“Nâng plugin lên bản lớn nhất luôn là cách tốt nhất.”** Sai: major plugin có thể yêu cầu Maven/JDK cao hơn.

**“Duplicate plugin declaration chỉ là warning không quan trọng.”** Sai: POM model validation mới có thể biến nó thành lỗi dừng build; nên gộp entry trùng.

**“Nếu plugin không được khai báo trong POM thì Maven không dùng nó.”** Sai: packaging/lifecycle binding hoặc parent có thể đưa plugin vào build.

**“Một lần chạy `mvn validate` kiểm chứng mọi plugin.”** Sai: plugin chỉ dùng ở phase test/package/verify có thể chưa được thực thi.

## 17. Bài tập tự kiểm tra

**Bài 1 — Baseline.** Dựng project mục 8, chạy `mvn -B -ntp -Dmaven.plugin.validation=VERBOSE clean verify` và `java -cp target/classes vn.example.plugincheck.Main`. Xác nhận stdout của chương trình là **Plugin compatibility OK: 5**.

**Bài 2 — Đọc version plugin.** Chạy `help:effective-pom` và `help:describe` cho Compiler Plugin, xác nhận version `3.13.0` và đọc các parameter của goal `compile`.

**Bài 3 — Phân loại cảnh báo.** Với một log giả định có hai cảnh báo “deprecated goal” và “plugin uses deprecated Maven API”, chỉ ra cái nào nhóm dự án sửa bằng POM, cái nào phải do plugin maintainer sửa trước.

**Bài 4 — Mức log.** So sánh `INLINE`, `BRIEF`, `VERBOSE` trong dự án có plugin thực sự phát cảnh báo. Giải thích vì sao không thấy warning ở mode mặc định không chứng minh mọi plugin sạch.

**Bài 5 — Kiểm tra Java.** So `java -version`, `mvn --version` và `maven.compiler.release`. Nêu trường hợp Java target 17 không đồng nghĩa Maven chạy trên JDK 17.

**Bài 6 — Duplicate plugin.** Trong project thử nghiệm **có backup**, cố ý khai báo trùng Compiler Plugin ở cùng `build/plugins`, quan sát warning/error tùy Maven version rồi gộp đúng một entry; không làm trên nhánh production.

**Bài 7 — Maven 4.** Dùng ma trận CI có Maven 3 ổn định và Maven 4 RC đã lựa chọn, pin plugin versions phù hợp từng nhánh; ghi lại mọi Internal/External issues trước khi quyết định nâng cấp chính thức.

### Tóm tắt

**Đọc plugin validation theo ba câu hỏi:** (1) Maven/Java/plugin version nào đang chạy? (2) vấn đề thuộc **cấu hình dự án (Internal)** hay **bản thân plugin (External)**? (3) sửa ở POM, cập nhật plugin hay thay đổi môi trường/runtime? Bật **`-Dmaven.plugin.validation=VERBOSE`** để thấy nhiều chi tiết hơn, nhưng nhớ rằng đó là **chế độ báo cáo**, không phải cách sửa lỗi.

Một quy trình tương thích đáng tin luôn có **plugin versions được kiểm soát, System Requirements đúng bản, test thực tế và ma trận Maven/JDK cho lần nâng cấp**. Cảnh báo cần được hiểu và xử lý theo đúng nơi gây ra, không nên chỉ che đi để build trông sạch.

### Tài liệu chính thức

- [Apache Maven — Plugin Validation](https://maven.apache.org/guides/plugins/validation/)
- [Apache Maven — Starting with Maven 4](https://maven.apache.org/guides/mini/guide-migration-to-mvn4.html)
- [Apache Maven — What's New in Maven 4](https://maven.apache.org/whatsnewinmaven4.html)
- [Apache Maven — Maven 3.9.3 Release Notes](https://maven.apache.org/docs/3.9.3/release-notes.html)
- [Apache Maven — Maven 3.10.0 Release Notes](https://maven.apache.org/docs/3.10.0/release-notes.html)
- [Apache Maven — Maven Plugins Compatibility Plan](https://maven.apache.org/developers/compatibility-plan.html)
- [Apache Maven Compiler Plugin — Plugin Info & System Requirements](https://maven.apache.org/plugins/maven-compiler-plugin/plugin-info.html)
- [Apache Maven Help Plugin — help:describe](https://maven.apache.org/components/plugins/maven-help-plugin/describe-mojo.html)
- [Apache Maven Enforcer Plugin — requireMavenVersion](https://maven.apache.org/enforcer/enforcer-rules/requireMavenVersion.html)
- [Apache Maven Enforcer Plugin — requireJavaVersion](https://maven.apache.org/enforcer/enforcer-rules/requireJavaVersion.html)

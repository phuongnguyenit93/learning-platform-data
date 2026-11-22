# Tiếp tục từ một mô-đun bằng -rf và những đầu vào phải còn sẵn trong Maven Reactor

## 1. Bài toán: build nhiều mô-đun thất bại ở giữa

Một dự án Maven có thể có parent/aggregator POM và nhiều mô-đun phụ thuộc nhau:

```text
reactor-resume-lab (aggregator, packaging=pom)
    ├── core-lib        -> thư viện lõi
    ├── service-app     -> phụ thuộc core-lib
    └── ops-cli         -> phụ thuộc service-app
```

Khi chạy từ thư mục gốc:

```bash
mvn clean verify
```

Maven **Reactor** thu thập, sắp xếp rồi build những mô-đun đã chọn theo quan hệ phụ thuộc. Giả sử `core-lib` thành công nhưng unit test tại `service-app` thất bại. Với chế độ mặc định fail-fast, mô-đun `ops-cli` sau đó không được build.

Maven thường gợi ý:

```text
After correcting the problems, you can resume the build with the command
  mvn <args> -rf :service-app
```

Bạn sửa lỗi rồi chạy:

```bash
mvn verify -rf :service-app
```

Thoạt nhìn có vẻ đủ: không tốn thời gian chạy lại `core-lib`. Nhưng ở **Maven 3.x**, lệnh này có thể thất bại ngay tại bước resolve dependency:

```text
Could not find artifact com.example:core-lib:jar:1.0-SNAPSHOT
```

Tại sao? Vì `-rf` **bỏ các dự án ở trước điểm bắt đầu khỏi tập build**, trong khi `service-app` **vẫn cần artifact** do `core-lib` cung cấp. Nếu trước đó bạn chỉ chạy `verify` hoặc `package`, artifact của `core-lib` có thể nằm trong `core-lib/target/` nhưng **chưa được cài vào local Maven repository**. Khi `core-lib` không còn là thành viên active reactor, Maven không tự dùng đường dẫn `target/core-lib-1.0-SNAPSHOT.jar` thay cho dependency resolution theo tọa độ.

**Thông điệp chính: `-rf` tiết kiệm công sức build lại các dự án phía trước, nhưng không lưu trạng thái của chúng và không tự chuẩn bị các đầu vào còn thiếu.** Tất cả đầu vào mà dự án tiếp theo cần phải đã có sẵn qua Maven reactor, repository, filesystem hoặc hạ tầng tương ứng.

Bài này tập trung vào:
1. `--resume-from`/`-rf` chọn tập mô-đun thế nào.
2. Khác biệt giữa `-rf`, `-pl`, `-am`, `-amd`, `-N` và các chế độ failure.
3. Những đầu vào phải có sẵn: JAR/POM nội bộ, parent, plugins, generated resources, external services.
4. Lý do `target/*.jar` khác với `~/.m2/repository` và reactor-resolved artifacts.
5. Điểm hạn chế của **Maven 3** khi ghép `-rf` với `-am` và cải tiến của **Maven 4**.
6. Ví dụ Java 17 nhiều mô-đun đầy đủ, cố ý làm fail test, sửa lỗi, tiếp tục đúng cách.
7. Cách dùng `verify`, `install`, local repository cô lập và CI một cách an toàn.
8. Troubleshooting, checklist và bài tập kiểm chứng.

Ví dụ chính sử dụng **Maven 3.9.x**, **JDK 17+**, Maven Compiler Plugin 3.13.0, Surefire 3.5.2 và JUnit Jupiter 5.11.4. Maven 4 được trình bày riêng vì thứ tự chọn subprojects, `--resume` và kết hợp `--also-make` có khác biệt.

## 2. Reactor là gì và Maven quyết định thứ tự ra sao?

### 2.1. Aggregation không phải inheritance

Một POM có:

```xml
<packaging>pom</packaging>
<modules>
    <module>core-lib</module>
    <module>service-app</module>
    <module>ops-cli</module>
</modules>
```

đóng vai trò **aggregator**: Maven thấy danh sách modules để build chung.

Một POM con có:

```xml
<parent>
    <groupId>com.example</groupId>
    <artifactId>reactor-resume-lab</artifactId>
    <version>1.0-SNAPSHOT</version>
</parent>
```

là quan hệ **inheritance**: con kế thừa properties, pluginManagement và các cấu hình được phép từ parent. Hai khái niệm thường kết hợp, nhưng **không đồng nghĩa**. Có dự án aggregator không phải parent hoặc parent nằm ngoài source tree. Khi resume, việc aggregator/parent POM có thể được **đọc để dựng model** khác với chuyện parent được **thực thi như một project ở lifecycle phases**.

Trong bài thực hành, root POM vừa là aggregator vừa là parent để đơn giản. `<modules>` xác định các thư mục có module; `<parent>` trong mỗi con cho Maven biết POM kế thừa.

### 2.2. Reactor collection, sorting và selection

Tài liệu Maven mô tả ba công việc cốt lõi của Reactor:
1. **Thu thập** các modules được khai báo trong aggregator.
2. **Sắp xếp** để dự án cung cấp dependency được build trước dự án dùng nó.
3. **Thực thi** các project đã chọn theo thứ tự phù hợp.

Những quan hệ có ảnh hưởng sorting gồm:
- Dependency từ module này tới module khác trong reactor.
- Plugin declaration sử dụng plugin được xây trong reactor.
- Plugin dependency và build extension thuộc reactor.
- Các quan hệ parent/subproject tương ứng theo mô hình và phiên bản Maven.
- Thứ tự `<modules>` khi không có quan hệ mạnh hơn để sắp xếp.

**Chỉ có tên xuất hiện trong `dependencyManagement` hoặc `pluginManagement` chưa tạo quan hệ build-order instantiated.** Nếu muốn `service-app` thực sự phụ thuộc `core-lib`, phải khai báo dependency trong `<dependencies>` (hoặc có quan hệ plugin/build extension thực sự), không chỉ đặt version ở `dependencyManagement`.

Trong project minh họa:

```text
reactor-resume-lab
       |
       v
   core-lib
       |
       v
  service-app
       |
       v
    ops-cli
```

Mũi tên biểu diễn **thứ tự cần có**: `service-app` cần `core-lib`; `ops-cli` cần `service-app`. Dù `<modules>` liệt kê theo thứ tự khác, Reactor vẫn phải sắp theo dependency relationships.

### 2.3. Failure mode ảnh hưởng dự án sau lỗi

```bash
mvn -ff verify
mvn -fae verify
mvn -fn verify
```

- `-ff`/`--fail-fast`: dừng tại failure đầu tiên, là default thường gặp.
- `-fae`/`--fail-at-end`: tiếp tục những modules có thể build độc lập, rồi báo thất bại ở cuối.
- `-fn`/`--fail-never`: tiếp tục và không trả mã lỗi thất bại như thông thường; rất dễ làm CI hiểu nhầm kết quả.

Sau `-fae`, Reactor Summary có thể có **FAILURE**, **SUCCESS** và **SKIPPED** ở các vị trí khác nhau; không thể coi `-rf` là “chạy đúng những modules đã fail”. Nó chỉ chọn **một đoạn từ điểm bắt đầu trong reactor order**. Các module độc lập nằm trước điểm chọn nhưng từng thất bại có thể không được chạy lại.

Trong pipeline kiểm tra chất lượng, thường nên giữ fail-fast hoặc fail-at-end theo chính sách; đừng dùng fail-never để che test failures.

## 3. -rf / --resume-from thực sự làm gì?

### 3.1. Cú pháp

Hai cách tương đương:

```bash
mvn verify -rf :service-app
mvn verify --resume-from :service-app
```

Selector `:service-app` trỏ đến project có `artifactId=service-app` trong reactor; dạng `groupId:artifactId` hoặc đường dẫn tương đối cũng hữu ích khi tên trùng nhau. Ví dụ:

```bash
mvn verify -rf com.example:service-app
mvn verify -rf service-app
```

Trong lệnh từ aggregator root có module directory `service-app`, ba dạng trên có thể trỏ cùng module. Tuy nhiên **đừng đoán selector khi monorepo có nhiều module trùng artifactId**: dùng đầy đủ groupId:artifactId hoặc đường dẫn và xem Reactor Build Order.

Ở Maven 3, chạy từ **root aggregator** là cách ít nhầm nhất. Nếu bạn đang ở thư mục khác, dùng `-f path/to/root/pom.xml` hoặc chuyển về root để bảo đảm Reactor thấy tập dự án mong muốn.

### 3.2. Resume “từ” nghĩa là bao gồm module bắt đầu

Giả sử thứ tự sau sorting là:

```text
1. reactor-resume-lab (parent)
2. core-lib
3. service-app      <- lỗi
4. ops-cli
```

Lệnh:

```bash
mvn verify -rf :service-app
```

chọn các module từ `service-app` trở đi trong reactor order:

```text
service-app
ops-cli
```

**Không chọn core-lib**, cũng không chạy lifecycle trên parent aggregator. Điều này chính là tối ưu của `-rf`: **không làm lại phần phía trước**. Nhưng những phần phía trước vẫn có thể cung cấp dependencies, plugin JARs, generated code, files hoặc services cần thiết cho hai module sau.

`-rf` **không tự mở lại một Maven process đã dừng**, không giữ dependency graph đã nằm trong bộ nhớ, không snapshot `target`, và không lưu kết quả unit test đã chạy. Mỗi lệnh Maven là một lần khởi tạo reactor/project session mới.

### 3.3. Đừng hiểu -rf là incremental build hoặc cache

Nếu bạn chạy:

```bash
mvn clean verify -rf :service-app
```

`clean` sẽ áp dụng cho **các project thực sự nằm trong lần build được chọn**, không chạy `clean` trên `core-lib` đã bị bỏ qua. Nhưng cũng không khiến Maven tự “ghi nhớ” `core-lib` lần trước đã compile thành công theo cách dependency resolver có thể dùng.

Tương tự, nếu bạn thay đổi source của `core-lib` sau lần build thất bại mà chỉ resume từ `service-app`, phiên bản JAR cũ trong local repository có thể được sử dụng, làm build **xanh nhưng kiểm tra với code cũ**. Khi source upstream thay đổi, hãy chọn lại upstream vào reactor bằng `-pl ... -am` hoặc build đầy đủ.

### 3.4. -rf chọn một đoạn, không chọn riêng một module

Khi `ops-cli` đứng sau `service-app`, `-rf :service-app` chạy **cả hai** (nếu không có filter khác). Nếu chỉ muốn chạy `service-app` và dependencies cần thiết, dùng:

```bash
mvn -pl :service-app -am verify
```

Lệnh này chọn module mục tiêu và những upstream reactor dependencies cần thiết, chứ không tự lấy tất cả downstream modules. Khi muốn kiểm tra thay đổi trong `core-lib` ảnh hưởng cả `service-app`/`ops-cli`, có thể build full reactor hoặc chọn downstream đích rồi `-am`:

```bash
mvn -pl :ops-cli -am verify
```

Lệnh này rất hữu ích cho bài thực hành, vì module `ops-cli` phụ thuộc `service-app` rồi `core-lib`; Maven sẽ đưa các prerequisites cần thiết vào reactor selection.

## 4. Những đầu vào nào phải còn sẵn khi dùng -rf?

Không phải mọi module chạy sau đều chỉ cần bytecode của chính nó. Một module có thể cần **nhiều kiểu đầu vào**, và `-rf` bỏ những projects phía trước nên bạn phải phân biệt nguồn nào còn có thể resolve được.

### 4.1. Artifact nội bộ của upstream module

Ví dụ `service-app` khai báo:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>core-lib</artifactId>
    <version>1.0-SNAPSHOT</version>
</dependency>
```

Khi chạy **full reactor**, Maven có project `core-lib` trong session, có thể dùng **reactor workspace resolution** cho tọa độ `com.example:core-lib:1.0-SNAPSHOT`. Không cần cài module vào `~/.m2` chỉ để full-reactor `verify` hoạt động.

Khi chạy `-rf :service-app` trên Maven 3, `core-lib` bị loại khỏi active build selection. Maven sẽ cần một artifact có thể resolve theo tọa độ, thường là:
- Local repository: `~/.m2/repository/com/example/core-lib/1.0-SNAPSHOT/...jar` và POM liên quan, được cài qua `mvn install` từ lần trước.
- Remote repository/mirror, nếu artifact đã được publish và phù hợp dependency version.
- Một workspace/custom resolver có chủ đích khác, nếu môi trường hỗ trợ.

**File `core-lib/target/core-lib-1.0-SNAPSHOT.jar` còn nằm trong source tree không tự đủ.** `package` tạo output trong `target`; `install` thêm artifact và metadata thích hợp vào local repository. Đừng nhầm `BUILD SUCCESS ở core-lib package` với việc consumer ngoài active reactor có thể resolve tọa độ đó.

### 4.2. Parent POM và imported BOM

Các module con có parent:

```xml
<parent>
    <groupId>com.example</groupId>
    <artifactId>reactor-resume-lab</artifactId>
    <version>1.0-SNAPSHOT</version>
    <relativePath>../pom.xml</relativePath>
</parent>
```

Maven có thể dùng parent POM ở `../pom.xml` để dựng effective project model dù parent không được thực thi ở đoạn `-rf`. Tuy nhiên, nếu parent chỉ có trong repository, `relativePath` sai, hoặc parent là artifact của một module nằm ngoài lần build, việc resolve model/plugin versions có thể thất bại.

Nếu parent đã được install trong một lần `mvn install` trước đó thì dependency resolution ổn định hơn, nhưng **đừng lấy một parent POM sẵn có thay cho artifacts cần thiết khác**. Cấu hình parent và việc biên dịch/đóng gói libraries là hai nhiệm vụ riêng.

Với BOM import hoặc plugins dùng trong build, Maven vẫn cần POM/JAR tương ứng từ local/remote repo hoặc reactor nếu có. `-rf` không biến một Maven offline cache chưa đầy đủ thành cache đầy đủ.

### 4.3. Output sinh từ upstream

Một số dự án dùng plugin để tạo:
- Java sources hoặc bytecode trước `compile`;
- schema OpenAPI/Protobuf/Avro, generated classes;
- shared test fixtures/test-jar artifact có classifier `tests`;
- resource bundles/config đã được filtering;
- WAR, ZIP, Docker image, database migrations hoặc deployment descriptors;
- artifact build bởi plugin do module khác phát hành.

Nếu `service-app` cần `core-lib` tạo `core-lib-1.0-SNAPSHOT-tests.jar`, thì **JAR tests với classifier** cũng phải đã được build/resolve, không chỉ main JAR. Nếu build plugin ở module trước ghi file vào một path ngoài module của chính nó, `-rf` không bảo đảm file còn hoặc tương ứng đúng version.

Cần kiểm tra thực tế:
1. **Đầu vào là Maven artifact?** GAV + packaging + classifier có thể resolve trong reactor/repository không?
2. **Đầu vào là file path?** File còn tồn tại đúng vị trí, đúng version, đúng checksum không?
3. **Đầu vào là external state?** Service/container/db/environment variables có còn và được khởi tạo lại idempotently không?
4. **Đầu vào là plugin/build extension?** Artifact plugin, plugin dependencies và generated metadata có được Maven resolver tìm thấy không?
5. **Đầu vào là secret/toolchain?** Settings, profiles, JDK, Maven Wrapper, certificates, credentials có giống lần chạy đầu không?

### 4.4. Install, deploy, package và local repository

| Phase/lệnh | Đầu ra điển hình | Ý nghĩa với resume |
| --- | --- | --- |
| `mvn compile` | `target/classes` | Classfiles cho module; không tự tạo resolvable JAR trong local repo |
| `mvn package` | `target/*.jar` | Đóng gói artifact; không tự cài vào `~/.m2` |
| `mvn verify` | Artifact đã qua các checks tới verify | Thường chưa cài artifact vào local repo |
| `mvn install` | JAR/POM được cài vào local repo | Upstream modules đã install có thể được đoạn `-rf` sau resolve |
| `mvn deploy` | Artifact được publish vào remote repo | Có thể được phiên chạy sau tải qua repository/mirror |
| `mvn clean` | Xóa `target` của các modules được chọn | Không phải lệnh xóa `~/.m2` |

**Không mặc định nên chạy `install` mọi lần.** Nhiều nhóm muốn `mvn verify` để không đưa SNAPSHOT đang phát triển vào local repo, tránh che lỗi bằng artifact cũ. `install` chỉ hữu ích khi bạn **có lý do** cần consumer ngoài active reactor resolve artifact theo tọa độ.

### 4.5. SNAPSHOT cũ: build xanh vẫn có thể sai

Giả sử trong `~/.m2` đã có:

```text
com.example:core-lib:1.0-SNAPSHOT  (bản hôm qua)
```

Hôm nay bạn thay `core-lib/NumberRules.java` nhưng chỉ chạy `mvn verify -rf :service-app`. Nếu Maven resolve lại bản SNAPSHOT hôm qua, `service-app` có thể compile/test với API cũ hoặc xảy ra `NoSuchMethodError` lúc runtime.

Đừng sử dụng `-U` như câu thần chú để giải quyết mọi tình huống:
- `-U` tác động tới việc kiểm tra/cập nhật artifacts/SNAPSHOT từ remote repository theo policy và Maven version.
- Nó **không biên dịch source core-lib mới nhất** nếu core-lib không nằm trong reactor và không được publish.
- Nếu remote repository có snapshot cũ, `-U` còn có thể tải chính bản đó thay vì code trong working tree.

Đầu vào cần đúng **source revision + artifact version + configuration**, chứ không chỉ “resolve được gì đó cùng GAV”.

## 5. Phân biệt -rf, -pl, -am và -amd

### 5.1. Bảng so sánh Maven 3

| Tham số | Tên đầy đủ | Tác dụng |
| --- | --- | --- |
| `-rf :service-app` | `--resume-from` | Bắt đầu tại service-app trong reactor order và đi tiếp các modules phía sau |
| `-pl :service-app` | `--projects` | Chỉ chọn module nêu ra (khi không kết hợp tùy chọn khác) |
| `-pl :service-app -am` | `--also-make` | Chọn service-app **và upstream prerequisites** trong reactor |
| `-pl :core-lib -amd` | `--also-make-dependents` | Chọn core-lib **và các modules phụ thuộc vào nó** |
| `-pl :ops-cli -am` | `--projects` + `--also-make` | Chọn ops-cli và các module nó cần: core-lib, service-app, parent/model khi cần |
| `-N` | `--non-recursive` | Chỉ build project hiện tại thay vì đi vào modules |
| `-ff` | `--fail-fast` | Dừng khi có failure đầu tiên |
| `-fae` | `--fail-at-end` | Tiếp tục những modules còn có thể build, báo fail sau |

Trong Maven 3, với project đang đứng ở **root**, dạng `-pl :artifactId` rõ hơn đường dẫn tương đối; dạng `-pl module-dir` cũng hoạt động khi directory hợp lệ. Trong Maven 4 selection có thêm các thay đổi cho subproject discovery/aggregators, nên hãy xem guide đúng major version.

### 5.2. Không đánh đồng -am và -amd

`-am` chọn **dependencies đi ngược lên** từ module mục tiêu: khi chọn ops-cli, Maven cần service-app và core-lib.

`-amd` chọn **dependents đi xuôi xuống**: khi chọn core-lib, những module dùng nó (trực tiếp hoặc gián tiếp) có thể được thêm vào tập build.

Một trong các lệnh an toàn khi sửa `core-lib` và muốn kiểm tra tất cả module liên quan là:

```bash
mvn -pl :ops-cli -am verify
```

Nó xây lại đủ tuyến phụ thuộc để kiểm tra cuối `ops-cli`. Nếu dự án có nhiều nhánh downstream không đi qua ops-cli, build đầy đủ hoặc `-amd` từ core-lib sẽ thích hợp hơn.

### 5.3. Maven 3: -rf và -am có bẫy đã được ghi nhận

Maven 3 có hạn chế/bug lâu năm **MNG-6863**: kết hợp `--resume-from` với `--also-make` không tạo lại upstream modules như một số người kỳ vọng.

Lệnh:

```bash
mvn verify -rf :service-app -am
```

**không phải cách chữa đáng tin** khi `core-lib` trước đó chưa được install và đang bị loại khỏi đoạn resume. Nó có thể vẫn thiếu artifact của `core-lib`. Nếu bạn cần upstream code hiện hành, trên Maven 3 hãy ưu tiên:

```bash
mvn -pl :ops-cli -am verify
```

hoặc full reactor:

```bash
mvn verify
```

Tài liệu chính thức Maven 4 nêu cải tiến Reactors: bug MNG-6863 được sửa, và `-rf ... -am` có thể chọn lại các upstream dependencies theo quy tắc mới. Không áp lời giải Maven 4 cho những môi trường CI vẫn chạy Maven 3.

### 5.4. Maven 4: thêm --resume/-r

Maven 4 bổ sung:

```bash
mvn verify --resume
mvn verify -r
```

để tiếp tục từ subproject thất bại trong lần build trước theo khả năng của Maven 4. Trên Maven 4, docs còn minh họa:

```bash
mvn verify -rf :service-app -am
mvn verify -r -am
```

Những lựa chọn này **không nên được copy nguyên sang Maven 3**. Trong bài thực hành dưới đây, ta chủ động dùng Maven **3.9.x** và `-rf` có chỉ định module, rồi bảo đảm upstream artifacts có sẵn hoặc rebuild bằng `-pl/-am`.

## 6. Ví dụ đầy đủ Java 17: một root và ba module

Ví dụ không dùng Spring, database hay dịch vụ ngoài để tập trung vào **reactor dependency resolution**. Có một thư viện tính toán, một service format chuỗi, một CLI in output. Module giữa chứa một JUnit test có thể đổi assertion để **cố ý làm build fail ở giữa**.

### 6.1. Cấu trúc thư mục

```text
reactor-resume-lab/
├── pom.xml
├── core-lib/
│   ├── pom.xml
│   └── src/main/java/com/example/core/NumberRules.java
├── service-app/
│   ├── pom.xml
│   ├── src/main/java/com/example/service/ReportService.java
│   └── src/test/java/com/example/service/ReportServiceTest.java
└── ops-cli/
    ├── pom.xml
    └── src/main/java/com/example/cli/CliApp.java
```

**Dependency graph:**

```text
ops-cli -> service-app -> core-lib
```

Trong `<modules>` của root, ta sẽ **cố ý liệt kê ngược thứ tự dependency**, để chứng minh Reactor sắp lại đúng bằng các quan hệ instantiated dependency.

### 6.2. Root `pom.xml` đầy đủ

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>reactor-resume-lab</artifactId>
    <version>1.0-SNAPSHOT</version>
    <packaging>pom</packaging>

    <!-- Cố ý liệt kê ngược dependency order -->
    <modules>
        <module>ops-cli</module>
        <module>service-app</module>
        <module>core-lib</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
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
                    <version>3.5.2</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>3.4.2</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-install-plugin</artifactId>
                    <version>3.1.3</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
```

**Phân tích:**
- Root vừa aggregate vừa làm parent.
- `<modules>` liệt kê ops-cli trước core-lib, nhưng Reactor phải dùng dependency graph để sắp `core-lib` trước `service-app` trước `ops-cli`.
- `pluginManagement` ở root quản lý versions cho các goal được lifecycle mapping dùng; nó **không tự tạo dependency relationship giữa các modules**.
- `project.build.sourceEncoding` và Java `release=17` được con kế thừa.
- Các plugins được ghim để build không phụ thuộc quá nhiều vào super POM/default versions; `mvn -version` vẫn cần cho biết JDK hợp lệ.
- `1.0-SNAPSHOT` cùng tọa độ được giữ nhất quán ở cả bốn POM. Khi thay version, cập nhật toàn bộ các references đúng cách.

### 6.3. `core-lib/pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.example</groupId>
        <artifactId>reactor-resume-lab</artifactId>
        <version>1.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>core-lib</artifactId>
    <packaging>jar</packaging>
</project>
```

Vì đã có parent, module kế thừa groupId/version. Nếu cần deploy module độc lập mà parent không nằm tại `../pom.xml`, phải cung cấp parent theo repository hoặc chỉnh `relativePath` phù hợp. Ví dụ này giữ parent trên filesystem để dễ kiểm chứng.

### 6.4. `core-lib/src/main/java/com/example/core/NumberRules.java`

```java
package com.example.core;

public final class NumberRules {
    private NumberRules() {
    }

    public static int twice(int number) {
        return number * 2;
    }
}
```

Đây là code thư viện không cần dependency ngoài. `NumberRules.twice(4)` trả `8`, là đầu vào của service module.

### 6.5. `service-app/pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.example</groupId>
        <artifactId>reactor-resume-lab</artifactId>
        <version>1.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>service-app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>core-lib</artifactId>
            <version>1.0-SNAPSHOT</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

**Lưu ý:** Trong POM này, dependency `core-lib` là quan hệ **thực tế** trong `<dependencies>`, không phải một quản lý version chưa được dùng. Nó buộc Reactor sắp core-lib trước service-app. JUnit Jupiter chỉ là test-scope dependency và không tham gia runtime classpath của service.

### 6.6. `service-app/src/main/java/com/example/service/ReportService.java`

```java
package com.example.service;

import com.example.core.NumberRules;

public final class ReportService {
    private ReportService() {
    }

    public static String render(int value) {
        return "value=" + NumberRules.twice(value);
    }
}
```

Service có tham chiếu trực tiếp tới class của core-lib. Nếu `core-lib` bị thiếu trên **compile classpath**, Maven Compiler Plugin không thể biên dịch. Nếu compile thành công nhưng runtime classpath thiếu core-lib, việc gọi `render` có thể gây `NoClassDefFoundError`/`ClassNotFoundException`.

### 6.7. `service-app/src/test/java/com/example/service/ReportServiceTest.java`

```java
package com.example.service;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

final class ReportServiceTest {
    @Test
    void rendersDoubledNumber() {
        assertEquals("value=8", ReportService.render(4));
    }
}
```

Test này **mặc định PASS**. Để **tái hiện lỗi giữa reactor**, ta sẽ tạm đổi expected value `"value=8"` thành `"value=9"`. Không giữ assertion sai trong code cuối; nó chỉ phục vụ thí nghiệm thất bại và tiếp tục.

Vì Surefire 3.5.2 hỗ trợ JUnit Jupiter và tên class kết thúc `Test`, test này sẽ được phát hiện khi chạy phase `test` trong `service-app`.

### 6.8. `ops-cli/pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.example</groupId>
        <artifactId>reactor-resume-lab</artifactId>
        <version>1.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>ops-cli</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>service-app</artifactId>
            <version>1.0-SNAPSHOT</version>
        </dependency>
    </dependencies>
</project>
```

`ops-cli` phụ thuộc trực tiếp `service-app` và nhận `core-lib` như một transitive dependency khi phạm vi phù hợp. Việc dùng transitive dependency không thay đổi yêu cầu: khi chạy thật phải có cả service-app và core-lib trong runtime classpath. Phần demo CLI dùng cả ba thư mục `target/classes` để lệnh chạy độc lập với việc JAR có được install hay không.

### 6.9. `ops-cli/src/main/java/com/example/cli/CliApp.java`

```java
package com.example.cli;

import com.example.service.ReportService;

public final class CliApp {
    private CliApp() {
    }

    public static void main(String[] args) {
        System.out.println(ReportService.render(4));
    }
}
```

Đây là executable class giản lược, không có manifest Main-Class. Vì thế ví dụ chạy bằng `java -cp`, **không** dùng `java -jar ops-cli/target/ops-cli-1.0-SNAPSHOT.jar` rồi trông đợi nó có entry point.

### 6.10. Tạo project và kiểm tra baseline

Từ thư mục `reactor-resume-lab`:

```bash
mvn -version
mvn clean verify
```

Kỳ vọng Maven Reactor Summary sau khi test đúng:

```text
reactor-resume-lab .................... SUCCESS
core-lib .............................. SUCCESS
service-app ........................... SUCCESS
ops-cli ............................... SUCCESS
BUILD SUCCESS
```

Thời gian, đường kẻ và log đầy đủ có thể khác. Điều cần quan sát là **thứ tự thực thi** không trùng với thứ tự `<modules>` được liệt kê ngược. Surefire chạy **1 test, 0 failures** ở service-app; core-lib và ops-cli không có test.

Chạy CLI từ **root** trên Linux/macOS:

```bash
java -cp "ops-cli/target/classes:service-app/target/classes:core-lib/target/classes" com.example.cli.CliApp
```

Hoặc Windows PowerShell/CMD:

```powershell
java -cp "ops-cli/target/classes;service-app/target/classes;core-lib/target/classes" com.example.cli.CliApp
```

**Stdout chính xác của chương trình Java:**

```text
value=8
```

Đây là stdout của `CliApp.main`, không phải toàn bộ Maven log. Trong project thực tế, có thể dùng dependency plugin hoặc exec plugin để xây classpath nhưng phải cấu hình chính xác để tránh nhầm với deployment artifact.

## 7. Thí nghiệm A: verify fail, -rf thiếu upstream artifact

### 7.1. Chuẩn bị một local repository riêng (tùy chọn nhưng giúp kiểm chứng)

Nếu bạn đã từng `install` cùng tọa độ `com.example:core-lib:1.0-SNAPSHOT` vào `~/.m2`, một lệnh resume có thể “tình cờ” thành công nhờ bản cũ. Để quan sát đúng cơ chế mà không xóa dữ liệu dùng chung, có thể dùng một **local repo thử nghiệm riêng**. Trên các lệnh minh họa, truyền cùng một option:

```bash
-Dmaven.repo.local=./.m2-reactor-demo
```

Đây là một directory mới nằm dưới thư mục root **do chính bạn chọn**; Maven có thể tải lại plugins/dependencies cần thiết trong repo này. **Không xóa `~/.m2` hoặc repository làm việc thật để tái hiện lỗi.** Nếu không cần isolation, bỏ option này khỏi các lệnh và ghi nhận rằng kết quả chịu ảnh hưởng cache/local repository hiện có.

Khi dùng repo riêng, **giữ nguyên property ở mọi lần chạy trong chuỗi thí nghiệm**, tránh một lệnh nhìn repo A, lệnh sau nhìn repo B.

### 7.2. Cố ý làm test fail

Trong `ReportServiceTest.java`, tạm sửa:

```java
assertEquals("value=8", ReportService.render(4));
```

thành:

```java
assertEquals("value=9", ReportService.render(4));
```

Chạy từ root:

```bash
mvn -Dmaven.repo.local=./.m2-reactor-demo clean verify
```

Kỳ vọng (sau khi tải đủ plugins/dependencies):
- Root aggregator `SUCCESS`.
- `core-lib` compile/package `SUCCESS`.
- `service-app` test FAIL vì expected `value=9` nhưng actual `value=8`.
- `ops-cli` `SKIPPED` do fail-fast.
- Có file `core-lib/target/core-lib-1.0-SNAPSHOT.jar` vì `verify` đi qua `package`.
- **Không có core-lib JAR mới được install vào local repo thử nghiệm chỉ nhờ `verify`**.

Tóm tắt:

```text
reactor-resume-lab ............... SUCCESS
core-lib ......................... SUCCESS
service-app ...................... FAILURE (unit test assertion)
ops-cli .......................... SKIPPED
BUILD FAILURE
```

**Không nhầm nguyên nhân lỗi:** trong lần chạy đầu, service-app đã dùng core-lib ở reactor, nên dependency có sẵn. Lỗi chủ động là **assertion mismatch**, chưa phải lỗi dependency resolution.

### 7.3. Sửa test rồi thử resume

Khôi phục assertion đúng:

```java
assertEquals("value=8", ReportService.render(4));
```

Sau đó:

```bash
mvn -Dmaven.repo.local=./.m2-reactor-demo verify -rf :service-app
```

Với **Maven 3** và **repo cô lập chưa cài core-lib**, lệnh này có thể fail trước khi chạy test:

```text
Could not resolve dependencies for project com.example:service-app...
Could not find artifact com.example:core-lib:jar:1.0-SNAPSHOT
```

Đây là **dạng lỗi dự kiến**; phần plugin/stack trace, URL repository và thông báo chi tiết thay đổi theo Maven/settings. Maven không lấy lại core-lib từ reactor vì nó nằm **trước** `service-app` và đã bị `-rf` loại khỏi active reactor selection. File `core-lib/target/...jar` chỉ là output workspace, chưa được install.

**Không giải quyết bằng `-rf :core-lib -am` rồi tin Maven 3 sẽ tự làm mọi upstream như ý.** Đơn giản và chắc chắn nhất ở đây là chọn một tập dự án chứa cả các prerequisites:

```bash
mvn -Dmaven.repo.local=./.m2-reactor-demo -pl :ops-cli -am verify
```

hoặc full reactor:

```bash
mvn -Dmaven.repo.local=./.m2-reactor-demo verify
```

Cả hai đều đưa core-lib vào active reactor, nên service-app có thể resolve dependency từ project đang được build. Với code đã khôi phục, test pass và ops-cli cũng hoàn tất.

### 7.4. Vì sao không khuyên đổi mọi lần verify thành install?

Một cách khác là install upstream vào local repository. Nhưng nếu áp dụng `mvn install` cho mọi build trong ngày, local repo có thể chứa nhiều `SNAPSHOT` cũ, tăng nguy cơ consumer resolve bản khác với working tree. Maven 4 cải thiện reactor behaviors và khuyến nghị `verify` cho những build thông thường khi có thể.

Lời khuyên thực tế:
- **Phát triển và kiểm tra trong cùng reactor:** `verify` hoặc `-pl ... -am verify`.
- **Cần dùng -rf trên Maven 3:** chỉ làm khi upstream artifacts đã sẵn có theo đúng version, hoặc chuẩn bị chúng có chủ đích.
- **Cần consumer ngoài reactor dùng artifact nội bộ:** `install` có thể phù hợp, nhưng cần kiểm soát freshness, repository và CI.

## 8. Thí nghiệm B: install fail, -rf dùng lại upstream đã cài

### 8.1. Tạo lỗi rồi chạy install

Để tách với Thí nghiệm A, đưa assertion về `"value=9"` một lần nữa (chỉ trong thí nghiệm), và chạy:

```bash
mvn -Dmaven.repo.local=./.m2-reactor-demo clean install
```

Khi build theo thứ tự:
1. Root aggregator được `install` vào local repo (POM).
2. `core-lib` compile, package, **install** main JAR + POM vào local repo.
3. `service-app` compile được vì reactor có core-lib, nhưng test fail.
4. `service-app` chưa đi tới install phase; `ops-cli` bị skip.

Kết quả vẫn `BUILD FAILURE`, nhưng khác thí nghiệm A ở chỗ **artifact core-lib đã được cài vào local repository**. Trong repo thử nghiệm, đường dẫn dạng:

```text
.m2-reactor-demo/
  com/example/reactor-resume-lab/1.0-SNAPSHOT/...pom
  com/example/core-lib/1.0-SNAPSHOT/...jar
  com/example/core-lib/1.0-SNAPSHOT/...pom
```

Dấu `...` trong sơ đồ là tên tệp metadata/SNAPSHOT do Maven tạo; không phải một file phải tự tay viết. Đừng chỉnh/sao chép ngẫu nhiên các file trong local repo để sửa resolution.

### 8.2. Sửa lỗi và resume đúng

Khôi phục assertion:

```java
assertEquals("value=8", ReportService.render(4));
```

Chạy:

```bash
mvn -Dmaven.repo.local=./.m2-reactor-demo install -rf :service-app
```

Trong Maven 3, lúc này:
- Root/core-lib không được build lại vì bị `-rf` loại.
- `service-app` vẫn có thể resolve `com.example:core-lib:1.0-SNAPSHOT` từ local repo mà install trước đó đã tạo.
- `service-app` test pass và được install.
- `ops-cli` chạy sau, resolve service-app trong active reactor và core-lib qua dependency resolution.
- Cả hai modules trong đoạn resumed đạt `SUCCESS` khi code được khôi phục.

Kỳ vọng Reactor Summary của **lần resume**:

```text
service-app ...................... SUCCESS
ops-cli .......................... SUCCESS
BUILD SUCCESS
```

Đây là minh họa hiệu quả của `-rf` khi prerequisites **đã có sẵn**. Không nên hiểu rằng Maven luôn nhớ module trước đã thành công từ một kết quả lưu trong thư mục `target`.

### 8.3. Nếu initial build là verify, có thể chuẩn bị upstream bằng install riêng

Thay vì chạy full reactor install trước đó, bạn có thể chủ động install đúng upstream cần thiết:

```bash
mvn -Dmaven.repo.local=./.m2-reactor-demo -pl :core-lib -am install
mvn -Dmaven.repo.local=./.m2-reactor-demo -rf :service-app verify
```

Lệnh đầu chọn core-lib và các prerequisites reactor của nó, gồm parent khi cần, rồi install artifact. Lệnh thứ hai bắt đầu từ service-app. Cách này có thể hữu ích khi downstream build rất nặng và upstream artifact đã được kiểm soát.

Nhưng để CI/PR dễ tái lập, `mvn -pl :ops-cli -am verify` hoặc full `mvn verify` thường rõ ràng hơn, không phụ thuộc local install state.

## 9. Thế nào là “đầu vào còn sẵn” và “đầu vào đúng”?

### 9.1. Sẵn có không đồng nghĩa đúng phiên bản

Khi kiểm tra trước khi resume, hãy trả lời bốn câu:

1. **Cùng tọa độ?** Artifact có đúng `groupId:artifactId:version:type:classifier` không?
2. **Cùng nội dung nguồn?** Nó được build từ commit/source revision hiện tại hay bản cũ?
3. **Cùng build config?** Có cùng profile, JDK/toolchain, filter properties và annotation processors không?
4. **Cùng môi trường?** Có credentials/settings/repos giống CI? External services còn đúng schema/version không?

Một `core-lib:1.0-SNAPSHOT` trong local repo có thể được cài từ commit cũ với API tương thích tình cờ. Resume chạy xanh không bảo đảm bạn đã kiểm thử đúng thay đổi upstream của working tree.

### 9.2. Generated outputs và idempotency

Với source generation, một module trước có thể tạo schema/code vào `target/generated-sources`. `-rf` không chạy các goals sinh mã ở module trước. Nếu downstream tham chiếu file qua path tương đối thay vì qua Maven artifact được version hóa, việc còn tồn tại file cũ có thể tạo build thành công sai.

Nên ưu tiên:
- Đóng generated code/resources vào artifact có tọa độ rõ thay vì tham chiếu thẳng `../other-module/target`.
- Tạo inputs theo các phase chuẩn (`generate-sources`, `generate-resources`) trong đúng module chịu trách nhiệm.
- Làm startup/migrations/teardown scripts idempotent nếu cần resume.
- Xem README của build pipeline về generated metadata, container images, database schema và external state.
- Khi không chắc artifact tương ứng revision nào, **chạy lại full reactor hoặc `-pl ... -am`**.

### 9.3. Plugin/build extension module

Không chỉ Java libraries mới là prerequisites. Một module có thể tạo custom Maven plugin hoặc build extension mà các modules sau sử dụng. Reactor sorting có xét instantiated plugin/build-extension relationships. Nếu plugin module đứng trước `-rf` và artifact plugin chưa được install/resolve, resume có thể fail ngay trong build setup chứ không chờ compile.

Khi thấy `PluginResolutionException`, `PluginDescriptorParsingException`, hoặc lỗi tải build extension, đừng mặc định đó là cùng loại với core-lib JAR thiếu. Xác định **artifact plugin/extension** cần ở repo/active reactor và cách Maven load nó.

### 9.4. External infrastructure và CI cache

`-rf` không biết container database có chạy, queue đã được khởi tạo, test service có tồn tại hay secret token còn hợp lệ. Một pipeline có thể:
- chạy migration ở module trước rồi test ở module sau;
- tạo Docker image cho integration tests;
- viết fixture vào directory dùng chung;
- upload một artifact vào internal registry và tải ở bước sau.

Khi resume, các prerequisites ấy phải được **khôi phục từ artifact cache/registry** hoặc **chạy lại bước chuẩn bị** có chủ đích. Không nên dựa vào một container còn sống từ lần chạy trước như điều kiện ngầm để build pass.

**CI runner mới thường có workspace/local repository/cache khác.** Lệnh `-rf` thành công trên laptop nhờ `~/.m2` có sẵn không có nghĩa nó sẽ thành công trên runner sạch. CI nên truyền artifacts giữa jobs theo cơ chế rõ ràng hoặc build đủ dependency closure trong cùng job.

### 9.5. Điều gì xảy ra với -o và -U?

```bash
mvn -o verify -rf :service-app
mvn -U verify -rf :service-app
```

- `-o`/`--offline` chỉ dùng những artifact/metadata đã sẵn local; nếu core-lib chưa cài, resume càng rõ ràng thất bại.
- `-U` kiểm tra các snapshots/updates theo chính sách Maven Resolver; nó **không biến file `core-lib/target/*.jar` thành artifact đã install**.

Không sửa lỗi thiếu reactor dependency bằng cách chỉ tăng mức log `-X`, đổi `-U` hoặc xóa cache. Các lệnh đó không xây lại upstream source. Thường cần sửa **tập reactor được chọn** hoặc chuẩn bị artifact đúng cách.

## 10. Lựa chọn lệnh theo tình huống

| Tình huống | Lệnh Maven 3 phù hợp | Lý do |
| --- | --- | --- |
| Muốn build/test toàn bộ | `mvn clean verify` | Reactor có mọi modules và source hiện hành |
| Chỉ kiểm tra service-app và upstream | `mvn -pl :service-app -am verify` | core-lib tham gia active reactor |
| Kiểm tra tới ops-cli, bao gồm prerequisites | `mvn -pl :ops-cli -am verify` | Có cả core-lib và service-app |
| Đã install upstream đúng version, muốn tiếp tục từ service-app | `mvn verify -rf :service-app` | Local repo cung cấp core-lib |
| Đã chạy install và service-app thất bại | `mvn install -rf :service-app` | Tránh chạy lại root/core-lib nếu vẫn đúng |
| Mới chạy verify/package rồi fail, core-lib chưa install | `mvn -pl :ops-cli -am verify` hoặc full verify | Không phụ thuộc artifact upstream trong repo |
| Chỉ muốn install upstream để resume sau | `mvn -pl :core-lib -am install` | Cài core-lib/parent như prerequisites |
| Source core-lib vừa đổi | `mvn -pl :ops-cli -am verify` hoặc full verify | Không dùng SNAPSHOT cũ |
| Có nhiều module độc lập sau failure | Xem Reactor Summary trước khi chọn `-rf` | -rf chọn suffix, không phải danh sách modules cần retry |
| Maven 4 và muốn resume với prerequisites | `mvn verify -rf :service-app -am` hoặc `mvn verify -r -am` | Maven 4 xử lý reactor selection khác Maven 3 |

**Lưu ý mọi lệnh phải chạy với cùng Maven major version, đúng root POM/settings/profiles và local repo dự kiến.** Một ví dụ sử dụng `-rf` trong Maven 4 không chứng minh sẽ hoạt động tương tự trên Maven 3.9.x.

## 11. Troubleshooting khi resume bị lỗi

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `Could not find artifact ...:core-lib` | core-lib ở trước -rf và chưa install/publish | Dùng `-pl ... -am` hoặc install đúng upstream |
| `Could not resolve parent POM` | parent không có trong repo/relativePath sai | Kiểm tra parent coordinate, relativePath, install parent |
| `core-lib/target/*.jar` có nhưng Maven báo thiếu | target output không phải local repository | `install` hoặc đưa module vào active reactor |
| -rf chạy thành công với code cũ | SNAPSHOT/POM cũ trong local repo | Rebuild upstream, kiểm tra nguồn/version |
| `-rf ... -am` vẫn không thêm prerequisites | Maven 3 bug MNG-6863 | Dùng `-pl ... -am`; Maven 4 có fix |
| `-r` không hoạt động như ví dụ | Đang dùng Maven 3, không phải Maven 4 | Dùng `-rf :artifactId` hoặc lệnh Maven 3 tương ứng |
| `-rf :module` báo không tìm thấy project | Selector sai hoặc root reactor khác | Chạy từ root, xác minh `<modules>` và GAV |
| Module bị chạy sau -rf dù đã SUCCESS trước đó | -rf chọn suffix theo reactor order | Chọn `-pl`/`-am` nếu muốn tập khác |
| Module trước đã FAIL nhưng không được retry | Fail-at-end tạo nhiều failures, -rf chọn sau một điểm | Đọc Reactor Summary, chọn lại phạm vi đủ rộng |
| `NoClassDefFoundError` trong test | Classpath dùng artifact khác version/thiếu runtime dependency | Kiểm tra dependency:tree, jar, reactor selection |
| `PluginResolutionException` | Plugin artifact/build extension phía trước không resolve | Xem plugin graph, repo, cached artifact |
| Generated source thiếu | Generator ở module bị bỏ qua | Chạy upstream goal hoặc build prerequisites |
| CI mới fail trong khi laptop pass | Runner mới không có local repo/install state | Build full reactor hoặc cache/publish dependency đúng cách |
| `-o` làm lỗi resolve | Artifact chưa có trong local repo | Bỏ offline khi được phép hoặc chuẩn bị local artifacts |
| `-U` không giúp | Source upstream chưa build/install | Đưa upstream vào reactor hoặc install |
| Build order không giống `<modules>` | Maven sort theo instantiated dependencies | Đây là hành vi đúng |
| Build xanh nhưng không test module phụ thuộc | `-pl` chọn quá hẹp | Chọn downstream goal với `-am` hoặc build full reactor |
| `-N` khiến module con không build | Không recursive | Bỏ `-N` hoặc dùng lệnh root reactor đúng |
| Test report cũ khiến bạn nghĩ pass | Không clean/đọc sai module | Xem timestamp, Surefire reports theo từng module |

### 11.1. Bước xác định module lỗi

1. Đọc Maven **Reactor Summary** từ lần fail thật, ghi project/artifactId thất bại và những module đã SUCCESS/SKIPPED.
2. Ghi lại **lệnh ban đầu**, đặc biệt lifecycle goal (`package`, `verify`, `install`), `-P`, `-D`, `-s`, `-o`, `-U` và `-Dmaven.repo.local`.
3. Xác định module đích cần resume theo **artifactId/GAV hoặc đường dẫn thực**.
4. Liệt kê dependency/plugin/extension prerequisites của module ấy.
5. Kiểm tra chúng đang nằm trong active reactor, local/remote repository hay đường dẫn do plugin tạo.
6. Nếu có source upstream mới, ưu tiên build lại upstream thay vì dùng local SNAPSHOT cũ.
7. Chọn lệnh tối thiểu nhưng **đủ các modules liên quan**.
8. Kiểm tra test report, build output và runtime path sau lần chạy thành công.

### 11.2. Các lệnh hỗ trợ

```bash
mvn -version
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom
mvn org.apache.maven.plugins:maven-dependency-plugin:3.10.0:tree
mvn -pl :service-app -am verify
mvn -pl :ops-cli -am verify
```

- `help:effective-pom` giúp kiểm tra parent, dependencyManagement và pluginManagement đã có hiệu lực.
- `dependency:tree` giúp xem các dependencies Maven resolver thấy trong module; với multi-module, nên chỉ định `-pl`/cấu hình phù hợp và nhớ rằng CLI goal trực tiếp có thể cần upstream artifacts đã resolve.
- `mvn -X ...` cho debug resolution/classpath nhưng log có thể chứa đường dẫn nội bộ, credentials, repository endpoints; không chia sẻ log thô khi chưa lọc dữ liệu nhạy cảm.

## 12. Những ngộ nhận dễ dẫn tới lỗi

**“`-rf` sẽ ghi nhớ output của các modules đã build thành công.”** Sai. Nó chỉ chọn vị trí bắt đầu của reactor, không lưu snapshot in-memory hay automatically install artifacts.

**“Có `target/core-lib.jar` thì mọi module sau resolve được.”** Sai. Maven dependency resolution thông thường dùng reactor workspace hoặc repositories theo tọa độ, không tự tìm mọi file `target` lân cận.

**“`verify` và `install` để lại đầu vào như nhau cho lần Maven process kế tiếp.”** Sai. `install` đưa JAR/POM vào local repository, còn `verify` không.

**“Thêm `-am` vào `-rf` luôn giải quyết upstream dependencies.”** Sai với Maven 3 do limitation MNG-6863. Maven 4 đã thay đổi hành vi.

**“`-pl :service-app -am` chỉ chạy service-app.”** Sai. `-am` thêm dependencies cần build trong reactor, giúp tránh phụ thuộc local install state.

**“`-rf` nghĩa là chỉ chạy lại đúng module từng fail.”** Sai. Nó chạy từ module đó tới cuối tập reactor đã chọn, có thể gồm nhiều modules không trực tiếp phụ thuộc.

**“Build xanh sau -rf chứng minh source upstream mới nhất đã được kiểm thử.”** Sai. Nếu core-lib ở trước điểm resume đã đổi hoặc SNAPSHOT cũ còn ở local repo, test có thể chạy trên artifact không đúng commit.

**“Maven 4 -r và Maven 3 -rf là một.”** Sai. Maven 4 thêm `--resume/-r` dựa vào failure state; `-rf` luôn chỉ định module, và Maven 3 không có cùng semantics của Maven 4 `-r`.

**“Cứ dùng -U hay xóa ~/.m2 là chữa được.”** Sai. `-U` không build source. Xóa local repo có thể phá những bước cần artifact đã install, làm build chậm và phức tạp hơn.

**“Resume tự khôi phục external database, generated files và plugins.”** Sai. Các đầu vào đó phải được tái tạo/resolve độc lập theo contract của pipeline.

## 13. Bài tập tự kiểm tra

**Bài 1 — nhận diện suffix.** Reactor có root → core-lib → service-app → ops-cli. Nếu dùng `mvn verify -rf :service-app`, modules nào được thực thi? **service-app, ops-cli**; root/core-lib ở trước bị bỏ khỏi lần execution.

**Bài 2 — lỗi thiếu artifact.** `core-lib` đã chạy `package`, file JAR nằm trong `target`. Vì sao `-rf :service-app` còn có thể fail? Vì artifact chưa có trong local/remote repo khi core-lib bị loại khỏi active reactor.

**Bài 3 — giải pháp không phụ thuộc local repo.** Muốn chạy ops-cli và toàn bộ prerequisites trên Maven 3, chọn `mvn -pl :ops-cli -am verify`.

**Bài 4 — khi nào -rf thành công?** Initial build `mvn clean install`, root/core-lib đã INSTALL thành công, service-app test FAIL. Sửa test rồi dùng `mvn install -rf :service-app` nếu upstream artifacts vẫn đúng revision/version.

**Bài 5 — cùng source, khác cache.** Laptop `-rf` pass, CI runner sạch fail missing core-lib. Tại sao? Laptop có local artifact, CI không. Cần build đủ upstream trong reactor hoặc cấp artifact chính xác cho CI.

**Bài 6 — sai dùng -am.** Vì sao `mvn verify -rf :service-app -am` không nên dùng làm giải pháp mặc định trên Maven 3? Vì known issue MNG-6863 và selection rules có thể vẫn bỏ prerequisites phía trước.

**Bài 7 — Maven 4.** Maven 4 có lựa chọn nào để resume failure trước đó? `mvn verify -r`/`--resume`, và có thể kết hợp `-am` để thêm prerequisites; không áp điều này cho Maven 3.

**Bài 8 — thay source upstream.** Bạn sửa NumberRules.java sau khi install core-lib nhưng chỉ resume service-app. Rủi ro? Service-app dùng JAR cũ từ local repo; nên rebuild upstream bằng `-pl ... -am`.

**Bài 9 — test fixture classifier.** Module sau cần một `tests` classifier artifact của module trước. Chỉ install main JAR có đủ không? **Không chắc**: classifier artifact tương ứng cũng phải được build/resolve.

**Bài 10 — -fae.** Hai modules độc lập cùng fail ở vị trí khác nhau. Có nên chỉ `-rf` từ module lỗi sau cùng để chắc retry cả hai? **Không**. Cần đọc Reactor Summary và chọn đủ modules hoặc full reactor.

**Bài 11 — generated source.** Module trước tạo file ở `target/generated-sources`, module sau đọc trực tiếp. `-rf` bảo đảm file đã được tạo lại từ source mới không? **Không**.

**Bài 12 — package vs install.** File JAR sau `package` và sau `install` khác nhau như thế nào đối với lần Maven CLI tiếp theo? `install` bổ sung bản JAR/POM trong local repository có thể resolve theo Maven coordinates.

## 14. Checklist trước khi bấm resume trên dự án thật

- [ ] Đã biết Maven **3.x hay 4.x** và không dùng flag theo sai major version.
- [ ] Đã lưu lệnh build ban đầu, Maven/settings/profiles/JDK/repository tương ứng.
- [ ] Đã đọc Reactor Summary để biết chính xác failure và skipped modules.
- [ ] Đã biết `-rf` chọn suffix, không tự build lại upstream.
- [ ] Đã xác định direct/transitive dependencies của module bắt đầu.
- [ ] Các module ở trước vẫn cung cấp artifacts phù hợp qua repo/active reactor khi cần.
- [ ] Parent POMs, imported BOMs và plugin dependencies có thể resolve đúng.
- [ ] Không chỉ thấy `target/*.jar` rồi mặc định artifact đã cài vào local repo.
- [ ] Đã kiểm tra không dùng SNAPSHOT cũ khác source revision hiện tại.
- [ ] Nếu upstream code thay đổi, ưu tiên `-pl :downstream -am verify` hoặc full reactor.
- [ ] Nếu dùng Maven 3, không phụ thuộc `-rf ... -am` để tự khôi phục upstream.
- [ ] Generated sources/resources, test classifiers, build extensions và external services đã sẵn sàng.
- [ ] CI/cache không bị coi là nguồn dữ liệu bảo đảm nếu chưa version hóa/kiểm tra.
- [ ] Nếu dùng `-fae`, không bỏ sót những modules thất bại ở trước resume point.
- [ ] Đã chạy test và xác minh artifacts/runtime của những modules cần phát hành.
- [ ] Với pipeline release, có một bước full-build/full-tests đáng tin cậy, không chỉ resume từ trạng thái cũ.

**Kết luận:** `-rf`/`--resume-from` giúp **bắt đầu từ một module trong Reactor** thay vì build lại tất cả. Nhưng các module phía trước không tự trở lại active reactor ở Maven 3, và output còn trong `target` không nhất thiết đủ cho Maven resolve dependency. Hãy coi **“đầu vào còn sẵn và đúng version”** là điều kiện tiên quyết. Nếu không thể chứng minh, dùng **`-pl :module-cuối -am verify`** hoặc full build; nếu upstream đã được **install** đúng cách, `-rf` mới là tối ưu hợp lý. Maven 4 đã cải thiện vấn đề `-rf/-am` và thêm `--resume`, vì vậy luôn đối chiếu tài liệu đúng Maven major version.

### Tài liệu và nguồn tham khảo

- [Apache Maven 3 — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Apache Maven 4 — Guide to Working with Multiple Subprojects](https://maven.apache.org/guides/mini/guide-multiple-subprojects-4.html)
- [Apache Maven — What's New in Maven 4 (reactor improvements, MNG-6863)](https://maven.apache.org/whatsnewinmaven4.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Maven CLI Options Reference](https://maven.apache.org/ref/3-LATEST/maven-embedder/cli.html)
- [Apache Maven — Maven Install Plugin](https://maven.apache.org/plugins/maven-install-plugin/)
- [Sonatype — Maven: The Complete Reference, Chapter 6: Running Maven](https://www.sonatype.com/maven-complete-reference/running-maven)
- [Baeldung — Starting the Maven Build From the Point Where It Failed](https://www.baeldung.com/maven-resume-failed-build)

# Tiếp cận Maven 4 theo các bước chuẩn bị, chạy thử và chuyển đổi

## 1. Mục tiêu: chuyển đổi có kiểm soát, không đổi mọi thứ trong một lần

Nâng cấp từ Maven 3 sang Maven 4 không chỉ là thay file thực thi `mvn`. Maven 4 thay đổi yêu cầu Java để **chạy Maven**, cách xác minh POM, API/plugin compatibility, một số lifecycle behaviors, cách xác định project root và các tính năng mới cho multi-project builds. Nếu cùng lúc đổi Maven runtime, JDK, plugin versions, POM model, release pipeline và build extensions, khi build lỗi sẽ rất khó biết nguyên nhân.

Apache Maven khuyến nghị **ba giai đoạn riêng biệt**:

1. **Chuẩn bị (prepare):** làm cho project xây ổn định trên Maven 3 được hỗ trợ, Java 17 cho Maven process, plugins/CI/Wrapper rõ version và không còn những cảnh báo cấu hình cần sửa.
2. **Chạy thử (test):** xây **cùng mã nguồn** bằng Maven 3 và Maven 4, ban đầu giữ `pom.xml` ở model `4.0.0`; chỉ sửa những incompatibilities tối thiểu vẫn tương thích Maven 3, kiểm test/artifact/deploy pipeline.
3. **Chuyển đổi (migrate):** chỉ sau khi đã thông qua dual-build gates, quyết định ngừng Maven 3; rồi mới cân nhắc `modelVersion 4.1.0`, `<subprojects>`, root attribute, BOM packaging, version inference và các khả năng Maven 4-only.

Đây không phải lịch nâng cấp bắt buộc trong một ngày. Một tổ chức có thể duy trì giai đoạn **dual-build** trong nhiều sprint trước khi đổi default CI, và có thể chuyển Maven runtime lên 4 mà **không đổi POM model sang 4.1.0**.

### Trạng thái phiên bản khi biên soạn bài

Theo lịch phát hành chính thức được kiểm tra ngày **10/11/2026**, Maven 4 đang có **4.0.0-rc-7**, phát hành ngày **24/09/2026**, vẫn là **release candidate** chứ chưa GA. Apache Maven 3 có các nhánh GA được duy trì, trong đó có **3.9.16** và **3.10.0**. Các mốc này phục vụ ví dụ; **trước khi áp dụng thật phải kiểm lại [Maven Releases History](https://maven.apache.org/docs/history.html)** vì phiên bản mới có thể xuất hiện.

Không nên tuyên bố một RC đã sẵn sàng production cho mọi hệ thống. Release notes của rc-7 khuyến nghị đánh giá stability/compatibility theo yêu cầu từng project và thu thập phản hồi lỗi.

## 2. Phạm vi thay đổi: điều gì bắt buộc, điều gì chỉ là tùy chọn?

| Thành phần | Khi chạy thử Maven 4 | Khi chủ động dùng tính năng Maven 4-only |
| --- | --- | --- |
| Maven runtime | Cần cài Maven 4 song song Maven 3 | Chuyển Maven 4 thành runtime chính |
| Java chạy Maven | **JDK 17+** | Vẫn JDK 17+ theo Maven 4.x đang xét |
| Java bytecode project | Có thể giữ `maven.compiler.release` cũ nếu toolchain/compiler phù hợp | Chỉ nâng Java application khi business muốn |
| `pom.xml` model | **Tiếp tục dùng `<modelVersion>4.0.0</modelVersion>`** | Có thể đổi sang `4.1.0` |
| `<modules>` | Vẫn được hỗ trợ với model 4.0.0 | Có thể chuyển `<subprojects>` trong model 4.1.0 |
| Parent/subproject GAV | Giữ khai báo tường minh ở bước test | Có thể dùng Maven 4 inference khi đã test |
| `.mvn` root marker | Nên có, tương thích Maven 3 | Có thêm lựa chọn `root="true"` của 4.1 |
| Plugins | Ưu tiên versions tương thích Maven 3/4 | Nâng versions Maven 4-only khi cần |
| Build extensions | Phải test compatibility từng extension | Có thể thay bằng extension đời mới |
| Build POM và consumer POM | Cần kiểm output được publish | Có cơ chế Maven 4 consumer POM, flatten là tùy chọn |
| Release pipeline | Chạy thử/staging, chưa đổi production publish | Chuyển khi đạt quality gate và rollback plan |

**Maven 4 đòi JDK 17 để chạy Maven**, nhưng điều này **không đồng nghĩa mọi ứng dụng phải compile Java 17**. Maven Compiler Plugin với `<release>8</release>`, chẳng hạn, có thể tạo bytecode phù hợp Java 8 khi compiler/toolchain hỗ trợ. Phân biệt:
- `java -version`: JDK trên PATH;
- `mvn -version`: JVM/JDK Maven **thực sự chạy**;
- `maven.compiler.release`: target Java API/bytecode của project;
- Maven Toolchains: JDK được các plugins hỗ trợ chọn để compile/test, có thể khác JVM chạy Maven.

Không đổi Java target của production artifact chỉ vì nâng Maven runtime.

## 3. Giai đoạn 1 — Chuẩn bị: xây Maven 3 baseline đáng tin

### 3.1. Tạo nhánh và bản ghi ban đầu

Trước khi nâng cấp, giữ một source commit có thể quay lại. Ghi tối thiểu:

```bash
git status --short
git rev-parse HEAD
mvn -version
java -version
mvn -B -ntp clean verify
```

Nếu project không dùng Git, dùng revision ID của VCS khác. Không tự sửa source files theo lệnh trên; đây là các lệnh đọc trạng thái và build thông thường.

Đầu ra cần lưu trong báo cáo:
- Source revision chính xác;
- Maven 3 distribution/version;
- JVM vendor và version từ `mvn -version`;
- Operating system/CI runner;
- Danh sách profiles, goals và flags release;
- Số modules/test suites và kết quả `verify`;
- Artifacts quan trọng: JAR, WAR, sources, Javadoc, shaded/assembly ZIP;
- Cấu hình local repository, mirrors/proxies, đặc điểm cache;
- Maven Wrapper đang được dùng hay chưa.

**Baseline nên xanh trước khi thử Maven 4.** Nếu Maven 3 đã fail vì download hoặc flaky test, không nên quy lỗi đó cho Maven 4.

### 3.2. Dùng bản Maven 3 được hỗ trợ

Hướng dẫn migration Maven 4 của Apache giả định dự án đã build được bằng **bản Maven 3 mới được duy trì**, thường là nhánh 3.9.x mới nhất theo tài liệu. Trong bối cảnh phát hành 2026, có thể dùng Maven 3.9.16 hoặc nhánh 3.10.0 khi team đã xác minh tương thích.

Tập trung trước vào:
- Xóa cảnh báo duplicate plugins/dependencies trong POM;
- Ghim plugin versions đang dùng ở `pluginManagement`;
- Loại cấu hình lỗi thời/tùy chọn plugin đã bị deprecated;
- Dọn profile activation mơ hồ hoặc khác nhau giữa local và CI;
- Xác nhận parent/BOM/dependency versions có nguồn đáng tin;
- Chốt JDK 17 để chạy Maven 3, giữ application release riêng nếu cần.

**Không cập nhật tất cả plugins lên versions Maven 4-only khi vẫn phải hỗ trợ Maven 3.** Một phiên bản plugin mới có thể tăng minimum required Maven/JDK, làm hỏng Maven 3 baseline.

### 3.3. Kiểm kê plugins và extensions

Một repository thường có:
- Lifecycle plugins mặc định theo packaging (Resources, Compiler, Surefire, JAR/WAR);
- Explicit plugins trong `<build><plugins>`;
- Plugin versions/config được kế thừa từ parent;
- Profiles (`release`, `ci`, `docs`, `integration`);
- Project build extensions (`<extensions>true</extensions>` hoặc `<build><extensions>`);
- Core extensions ở `.mvn/extensions.xml`;
- Custom corporate plugins hoặc goal gọi trực tiếp ở CI.

Sử dụng Maven 3:

```bash
mvn -B -ntp help:effective-pom -Doutput=effective-pom.xml
mvn -B -ntp org.codehaus.mojo:versions-maven-plugin:2.19.1:display-plugin-updates
```

Lệnh Versions Plugin cần network hoặc artifacts đã có để tìm versions; output là **đề xuất**, không tự chứng minh versions đó tương thích Maven 3. Đánh giá plugin release notes và minimum Maven/Java requirements trước khi đổi.

**Không chỉ tìm chuỗi `<plugin>` trong root POM.** Plugin có thể do default lifecycle bind, parent/profile thêm, CI gọi bằng full coordinate hoặc extension tạo side effects.

### 3.4. Kiểm Maven Wrapper và môi trường CI

Nếu repository dùng Wrapper, kiểm:
- `mvnw`, `mvnw.cmd`;
- `.mvn/wrapper/maven-wrapper.properties`;
- `distributionUrl` thực tế;
- Wrapper scripts được commit/chmod đúng và CI có network/checksum policy;
- Không để local developer dùng Maven 4 nhưng CI vẫn chạy Maven 3 vô tình.

**Cách thử hai version:** dùng **hai Maven distributions riêng** hoặc hai CI jobs/checkout tách biệt. Một Wrapper file chỉ pin **một Maven distribution tại một thời điểm**; đừng sửa `distributionUrl` qua lại trong cùng worktree giữa hai jobs song song rồi tạo race.

### 3.5. Ghi baseline test và artifacts

Build tối thiểu:

```bash
mvn -B -ntp clean verify
```

Nếu release có integration tests, profiles, codegen hoặc tools, kiểm thêm những goals **đúng production pipeline**. Đừng dùng `-DskipTests` làm baseline nếu production thực sự chạy tests.

Đối chiếu không chỉ dòng `BUILD SUCCESS`, mà còn:
- Tests executed/failed/skipped;
- Dependency tree và plugin executions quan trọng;
- Release artifact names, attached classifiers;
- Effective POM/profiles;
- Checksum khi project có chính sách reproducible builds;
- Workflow install/deploy và repository metadata.

Maven 3 baseline là **mẫu đối chiếu**, không phải sự bảo đảm project đúng nếu test scope chưa đầy đủ.

## 4. Giai đoạn 2 — Chạy thử: đặt Maven 3 và Maven 4 cạnh nhau

### 4.1. Chạy Maven 4 trên JDK 17

Tải Maven distribution từ nguồn Apache chính thức theo version đã được team chọn. Không dùng URL tải ngẫu nhiên hoặc tự coi một RC là GA. Với hai bản Maven có sẵn, cấu hình đường dẫn rõ cho từng shell.

**Linux/macOS — giả sử hai biến môi trường trỏ tới file thực thi đã cài:**

```bash
"$MVN3" -version
"$MVN4" -version

"$MVN3" -B -ntp clean verify
"$MVN4" -B -ntp clean verify
```

`MVN3` và `MVN4` ở đây **là biến do người học tự thiết lập tới file `bin/mvn` thật**, không phải hai lệnh có sẵn của hệ điều hành. Không dùng nguyên xi trước khi cài và gán đường dẫn.

**Windows PowerShell — sau khi gán đường dẫn tới file `mvn.cmd`:**

```powershell
& $mvn3 -version
& $mvn4 -version

& $mvn3 -B -ntp clean verify
& $mvn4 -B -ntp clean verify
```

`$mvn3`, `$mvn4` là đường dẫn do bạn cung cấp. Không lẫn JVM/JAVA_HOME giữa các runs; xem chính dòng `Java version` của `mvn -version`.

### 4.2. Không đổi modelVersion ngay

Ở bước test, **giữ `pom.xml` model 4.0.0**. Maven 4 vẫn hiểu model Maven 3. Đây là một yêu cầu chiến lược: nếu thay cả model lên 4.1 trước, Maven 3 không còn parse được, mất khả năng dual-build và làm rollback khó.

Ví dụ root POM tương thích cả Maven 3 và 4:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.migration</groupId>
    <artifactId>migration-lab</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>core</module>
        <module>cli</module>
    </modules>
</project>
```

Đây là **một POM rút gọn hợp lệ** để minh họa model/aggregation. Ví dụ thực hành hoàn chỉnh ở mục 7 có parent properties, plugin versions và Java sources.

### 4.3. Cảnh báo Maven 3 có thể trở thành lỗi Maven 4

Maven 4 kiểm model nghiêm hơn ở một số trường hợp. Đặc biệt, cần sửa:
- **Duplicate plugin declarations** trong `<build><plugins>`/`pluginManagement`;
- Duplicated dependencies hoặc dependencyManagement entries mơ hồ;
- Plugin configuration values không hợp lệ;
- `parent.relativePath` trỏ sai POM;
- Những properties nội bộ đã bị thay/không còn;
- Bind goals vào phase đã thay đổi;
- Plugin hoặc core extension sử dụng Maven API cũ.

Ví dụ **POM fragment sai**:

```xml
<plugins>
    <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.1</version>
    </plugin>
    <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <configuration>
            <release>17</release>
        </configuration>
    </plugin>
</plugins>
```

Hai khai báo trùng **cùng `groupId:artifactId`**. Đúng hơn là gộp thành một:

```xml
<plugins>
    <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.1</version>
        <configuration>
            <release>17</release>
        </configuration>
    </plugin>
</plugins>
```

Hai code blocks này là **fragments của `<build>`**, không phải POM độc lập. Không vội dùng tool tự sửa POM nếu chưa backup và kiểm diff.

### 4.4. Maven 4 có chế độ fail theo severity

Maven 4 thêm CLI option **`--fail-on-severity WARN`** để biến warnings ở mức chỉ định thành build failure, hữu ích trong migration triage:

```bash
"$MVN4" -B -ntp --fail-on-severity WARN validate
```

Đây là ví dụ shell khi `$MVN4` đã được thiết lập. **Không giả định Maven 3 chấp nhận option này** và không áp dụng nó ngay trên mọi CI job: warnings từ dependency/plugin ecosystem có thể cần phân loại trước.

### 4.5. Các phase `pre-`/`post-` cần rà soát

Trong Maven 3, nhiều integration-test workflows gắn plugins vào:
- `pre-integration-test`;
- `integration-test`;
- `post-integration-test`;
- `verify`.

Maven 4 thay cơ chế một số `pre-`/`post-` bằng **`before:`/`after:` phases**, theo tài liệu migration. Ví dụ fragment cũ:

```xml
<phase>pre-integration-test</phase>
```

Sau khi chuyển riêng sang Maven 4, tương ứng:

```xml
<phase>before:integration-test</phase>
```

**Đừng chỉ thay chuỗi rồi coi behavior tương đương.** Cần kiểm kỹ environment setup/teardown, Failsafe execution và order của goals. Với dual-build Maven 3, giữ sửa đổi trong phạm vi Maven 3-compatible hoặc tách logic phù hợp cho giai đoạn migrate.

### 4.6. Plugin API và extensions là nguồn rủi ro lớn

Maven 4 hướng tới tương thích nhiều Maven 3.9 plugins, nhưng **không bảo đảm** những plugins dùng Maven 2/3 internals cũ hoặc private API sẽ hoạt động. Ưu tiên xem:
- Compiler, Surefire/Failsafe, Resources, JAR/WAR, Shade, Assembly;
- Spring Boot/Quarkus/Android/other ecosystem build plugins;
- Release/Deploy/Install plugins;
- Custom company Maven plugins;
- `.mvn/extensions.xml` core extensions;
- Plugin testing harness và CI integrations;
- Repository transport, authentication, proxy, mirror.

Nếu plugin fail với `NoSuchMethodError`, `ClassNotFoundException`, `PluginContainerException` hoặc dependency-injection error, không kết luận Maven 4 “không hỗ trợ Java code”. Hãy xem plugin version/API compatibility và release notes. Không sửa lỗi bằng cách copy JARs vào Maven lib directory ngẫu nhiên.

### 4.7. Khác biệt cần đo

| Hạng mục | Kỳ vọng khi dual-build | Cách kiểm |
| --- | --- | --- |
| Maven startup/model building | Cùng source được parse | `validate`, effective POM khi khả dụng |
| Compile Java | Cùng source compatibility | `compiler:compile`, bytecode/API level |
| Unit tests | Cùng số lượng và assertions | Surefire reports |
| Integration tests | Cùng test environment | Failsafe reports, containers |
| Packaging | Cùng classifier/types | Danh sách `target/` và JAR contents |
| Dependencies | Không đổi trái ý muốn | Dependency tree, effective configs |
| Project reactor | Các modules được xây đúng | Reactor Summary |
| Install/deploy | Artifacts đúng địa chỉ/metadata | Local isolated repo và staging repository |
| Extensions | Không crash hoặc đổi behavior sai | Smoke test từng extension |
| CI | Có thể chạy trên runner sạch | Job matrix, Maven Wrapper/distributions |
| Performance | Không regression lớn | Wall times nhiều lượt, cùng cache |
| Security | Credentials đúng, không leak | Settings/mirror/CI secrets review |

**Hash JAR khác không tự kết luận functional regression**: archiver, manifest, metadata hoặc timestamps có thể khác giữa Maven/plugin versions. Khi project yêu cầu bit-for-bit reproducibility, cần chuẩn hóa input/timestamp/toolchain và điều tra khác biệt từng archive entry, không bỏ qua checksums một cách mù quáng.

## 5. Maven Upgrade Tool `mvnup`: kiểm trước, sửa sau

Từ Maven **4.0.0-rc-4**, Apache Maven cung cấp công cụ **Maven Upgrade Tool (`mvnup`)**. Nó không phải goal `mvn help:...`, mà là **command-line tool riêng** đi kèm Maven 4 distribution.

Mục đích:
- Kiểm POM compatibility issues;
- Đề xuất/sửa plugin versions có vấn đề với Maven 4;
- Chuẩn hóa một số model config sai;
- Fix parent relative paths hoặc root `.mvn` khi thích hợp;
- Hỗ trợ migration sang model 4.1/inference khi bạn **chủ động chọn**.

### 5.1. Dry-run trên nhánh migration

Tại root project, sau khi có Maven 4 distribution chứa `mvnup`:

```bash
mvnup --help
mvnup check --model-version 4.0.0
```

**`check` là lệnh kiểm, không phải tự ghi POM**. Model `4.0.0` phù hợp giai đoạn dual-build, không yêu cầu bỏ Maven 3 ngay.

Nếu cần kiểm tiềm năng Maven 4-only:

```bash
mvnup check --model-version 4.1.0 --all
```

Lệnh này cho biết các thay đổi có thể thực hiện nếu muốn dùng 4.1.0; **không phải bước phải chạy để dùng Maven 4 runtime**.

### 5.2. Apply chỉ trên branch có thể review

Sau khi kiểm và commit baseline:

```bash
mvnup apply --model-version 4.0.0 --model --plugins
git diff -- pom.xml core/pom.xml cli/pom.xml
```

Các options `--model`, `--plugins` giới hạn nhóm thay đổi; bạn cũng có thể chỉ chạy một nhóm. **Không chấp nhận mọi thay đổi của tool mà không review**, nhất là custom plugins, profile activation, version properties hoặc parent POM.

Một thay đổi bình thường không được phép gây mất tests, thay dependency artifact hoặc xóa release profiles. Sau apply, chạy lại **cả Maven 3 và Maven 4**.

### 5.3. Tại sao chưa dùng `--model-version 4.1.0`?

`mvnup apply --model-version 4.1.0 --all` có thể chỉnh Build POM sang schema mà Maven 3 không hiểu. Đây là bước **migrate**, không phải **test**.

**Nếu vẫn còn CI release dùng Maven 3, chưa dùng 4.1.0.** Hoặc phải chấp nhận breaking change có kế hoạch và version gate, không bật tính năng 4-only tình cờ do tool.

### 5.4. Tool có giới hạn

`mvnup` không thay thế:
- Chạy tests/integration tests;
- Xác minh custom plugin/extension behavior;
- Review security/settings/mirrors;
- Kiểm artifact publishing và consumer compatibility;
- Thử rollback sau thay đổi;
- Chuyển đổi tự động mọi script CI tùy biến.

Nếu tool không nhận ra một plugin private, hỏi maintainer và test bằng Maven 4; không coi việc không có warning là bằng chứng đủ.

## 6. Thiết kế CI dual-build và rollback

### 6.1. Hai jobs độc lập

Một chiến lược CI đáng tin:
- Job A dùng pinned Maven 3 distribution và JDK 17;
- Job B dùng pinned Maven 4 RC/GA distribution và JDK 17;
- Cùng commit, goals, profiles, test data, repository mirror policies;
- Cả hai lưu Maven `-version`, log và Surefire reports;
- Maven 4 job **không deploy production**, chỉ `verify` hoặc staging có kiểm soát;
- Build release trên Maven 3 vẫn là chuẩn cho tới khi Maven 4 vượt gate.

Ví dụ script **minh họa Linux/macOS**:

```bash
set -eu

: "${MVN3:?Set MVN3 to Maven 3 executable}"
: "${MVN4:?Set MVN4 to Maven 4 executable}"

"$MVN3" -version
"$MVN3" -B -ntp -Dmaven.repo.local=.m2-maven3 clean verify

"$MVN4" -version
"$MVN4" -B -ntp -Dmaven.repo.local=.m2-maven4 clean verify
```

Chạy trong root của checkout **có quyền ghi thư mục `.m2-maven3` và `.m2-maven4`**. Các local repositories tách riêng để tránh Maven 3/4 cùng ghi cache và che resolution issues. Chúng có thể download artifacts giống nhau từ mirror; thời gian cold build vì vậy không so trực tiếp như warm performance benchmark.

Trong CI thực, nên chạy **hai jobs/containers song song**, mỗi job có workspace riêng và Maven install riêng. Script tuần tự trên một workspace chỉ là ví dụ cách đảm bảo đúng Maven executable.

### 6.2. Tránh tác dụng phụ cùng workspace

Không chạy hai Maven versions **đồng thời trên cùng thư mục `target`**: `clean`, compiler, test reports có thể đè lẫn nhau và làm kết quả ngẫu nhiên. Chọn:
- Hai checkout/worktrees;
- Hai CI jobs với workspace riêng;
- Hoặc chạy tuần tự như ví dụ, giữ logs/artifacts ra thư mục bên ngoài trước lần `clean` thứ hai.

Nếu muốn so artifact output, copy versioned files ra vị trí riêng **sau mỗi successful build** trước khi `clean` tiếp.

### 6.3. Matrix quyết định chuyển default

| Gate | Tiêu chí tối thiểu |
| --- | --- |
| Baseline | Maven 3 build/test green trên clean runner |
| Runtime | Maven 4 chạy với JDK 17+, đúng Maven version |
| Model | Maven 4 parse mọi project, không có lỗi POM validation |
| Plugins | Không fail ở các goals/custom plugins thiết yếu |
| Tests | Cùng test scope và expected pass/fail |
| Packaging | Artifact names/classifiers/contents hợp lệ |
| Dependency resolution | Không đổi GAV trái ý muốn, không thiếu private repos |
| Release rehearsal | Install/deploy staging đúng metadata khi cần |
| Security | Credentials/mirror/extension không bị nới quyền |
| Observability | Logs/reports đủ so regression |
| Rollback | Có thể chuyển lại Maven 3 chỉ bằng pipeline/wrapper pin |
| Ownership | Có người theo dõi RC issues và plugin regressions |

Không có một số ngày chờ cố định cho tất cả dự án. Với enterprise release, triển khai theo project tier và có approval rõ.

### 6.4. Rollback là một phần của migration

Trong giai đoạn dual-build, rollback đơn giản:
1. Chỉ đổi CI runner/distribution pin về Maven 3;
2. Không dùng model 4.1 trong source;
3. Giữ plugin versions vẫn hỗ trợ Maven 3;
4. Rebuild từ clean checkout và verify;
5. Kiểm release repositories không nhận artifact thử nghiệm sai GAV.

**Nếu đã nâng POM lên 4.1 hoặc plugin Maven 4-only, rollback phức tạp hơn**: cần revert source changes/versions. Đó là lý do trì hoãn breaking change tới sau acceptance.

## 7. Dự án thực hành Java 17: cùng một POM chạy Maven 3 và Maven 4

Để tránh biến Migration Guide thành lý thuyết, tạo một reactor gồm:
- `migration-lab`: root parent/aggregator;
- `core`: Java library và ba JUnit Jupiter tests;
- `cli`: ứng dụng Java dùng `core`.

Giữ **POM model 4.0.0** trong giai đoạn thử. Dự án không dựa vào Maven 4-only features, nên là baseline hợp lý cho **dual-build**.

### 7.1. Cây thư mục

```text
migration-lab/
├── pom.xml
├── .mvn/
│   └── .keep
├── core/
│   ├── pom.xml
│   └── src/
│       ├── main/java/com/example/migration/core/BuildLabel.java
│       └── test/java/com/example/migration/core/BuildLabelTest.java
└── cli/
    ├── pom.xml
    └── src/main/java/com/example/migration/cli/Main.java
```

`.mvn/.keep` là **file rỗng tùy chọn**, chỉ để thư mục `.mvn` được version control theo dõi. Không cần điền tùy chọn Maven vào đó; Maven 3 và Maven 4 đều có thể nhìn thấy `.mvn` root marker.

### 7.2. File root `migration-lab/pom.xml` hoàn chỉnh

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.migration</groupId>
    <artifactId>migration-lab</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>
    <name>Maven Migration Lab</name>

    <modules>
        <module>core</module>
        <module>cli</module>
    </modules>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <junit.jupiter.version>5.11.4</junit.jupiter.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>${junit.jupiter.version}</version>
                <scope>test</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.14.1</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.5.4</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-resources-plugin</artifactId>
                    <version>3.3.1</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>3.4.2</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-clean-plugin</artifactId>
                    <version>3.4.1</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
```

**Đây là full Maven POM**. Root là aggregator (`<modules>`) và parent (children khai báo `<parent>`). Chỉ `core` khai báo JUnit dependency; `dependencyManagement` tự nó không thêm JUnit vào tất cả modules. `pluginManagement` chốt versions, không tự tạo plugin goals ngoài lifecycle binding.

Quan trọng: plugin versions ở đây là **ví dụ có chủ đích để có dự án chạy thử**. Trước khi dùng trong production, kiểm plugin release notes và compatibility với Maven 4 candidate/GA version đang thử; không tuyên bố tất cả tổ hợp Maven/JDK/extension của mọi team được bảo đảm.

### 7.3. File `migration-lab/core/pom.xml` hoàn chỉnh

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.migration</groupId>
        <artifactId>migration-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>migration-core</artifactId>
    <packaging>jar</packaging>
    <name>Maven Migration Core</name>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
        </dependency>
    </dependencies>
</project>
```

`relativePath` được tính từ child `core/pom.xml`, nên `../pom.xml` trỏ đúng root parent. Parent GAV phải khớp. Đây là khai báo Maven 3-compatible, không dùng parent version inference Maven 4-only.

### 7.4. File `migration-lab/cli/pom.xml` hoàn chỉnh

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.migration</groupId>
        <artifactId>migration-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>migration-cli</artifactId>
    <packaging>jar</packaging>
    <name>Maven Migration CLI</name>

    <dependencies>
        <dependency>
            <groupId>com.example.migration</groupId>
            <artifactId>migration-core</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>
</project>
```

CLI phụ thuộc Core trong cùng Maven reactor. Khi build từ root, Maven phải build Core trước CLI; tăng `-T` không làm hai modules hoàn toàn độc lập.

### 7.5. File `core/src/main/java/com/example/migration/core/BuildLabel.java`

```java
package com.example.migration.core;

import java.util.Locale;

public final class BuildLabel {

    private BuildLabel() {
    }

    public static String normalize(String input) {
        if (input == null || input.isBlank()) {
            return "UNKNOWN";
        }
        return input.strip().toUpperCase(Locale.ROOT);
    }

    public static String summary() {
        return "Migration lab: " + normalize(" ready ");
    }
}
```

Java 17 compilable: `String.isBlank` và `String.strip` hợp lệ, `Locale.ROOT` giúp uppercase ổn định giữa các máy. Không đọc Maven version trong Java runtime vì Maven build tool không nhất thiết là một dependency của application.

### 7.6. File `core/src/test/java/com/example/migration/core/BuildLabelTest.java`

```java
package com.example.migration.core;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class BuildLabelTest {

    @Test
    void returnsStableSummary() {
        assertEquals("Migration lab: READY", BuildLabel.summary());
    }

    @Test
    void trimsAndUppercases() {
        assertEquals("MAVEN", BuildLabel.normalize("  maven  "));
    }

    @Test
    void handlesBlank() {
        assertEquals("UNKNOWN", BuildLabel.normalize("  "));
    }
}
```

Ba **JUnit Jupiter tests** có dữ liệu ổn định. Nếu project được compile và dependencies resolve đúng, kỳ vọng 3 tests, 0 failures, 0 errors. Đây là tests của logic Java; chúng **không tự chứng minh** mọi Maven plugin trong production tương thích Maven 4.

### 7.7. File `cli/src/main/java/com/example/migration/cli/Main.java`

```java
package com.example.migration.cli;

import com.example.migration.core.BuildLabel;

public final class Main {

    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(BuildLabel.summary());
        System.out.println("Core check: " + BuildLabel.normalize(" ok "));
    }
}
```

### 7.8. Chạy trên Maven 3 và Maven 4

Ở root `migration-lab`, sau khi chuẩn bị đúng distribution paths:

```bash
"$MVN3" -B -ntp clean verify
"$MVN4" -B -ntp clean verify
```

Mỗi lượt phải hoàn thành Maven reactor và chạy 3 tests của Core. Sau lượt build thứ hai, từ Linux/macOS:

```bash
java -cp "cli/target/classes:core/target/classes" com.example.migration.cli.Main
```

Trên Windows PowerShell:

```powershell
java -cp "cli/target/classes;core/target/classes" com.example.migration.cli.Main
```

**Stdout chính xác của Java `Main`** (không gồm Maven logs):

```text
Migration lab: READY
Core check: OK
```

POM không thêm `Main-Class` vào manifest và không bundle Core vào CLI JAR, nên **không mặc định chạy `java -jar cli/target/migration-cli-1.0.0.jar`**.

Artifacts dự kiến:
- `core/target/migration-core-1.0.0.jar`;
- `cli/target/migration-cli-1.0.0.jar`.

Dự án Java 17 này **cố tình không dùng Maven 4-only POM features**. Điều cần kiểm là cùng source/POM có thể build/test với cả hai Maven runtimes trong giai đoạn 2.

## 8. Giai đoạn 3 — Chuyển đổi: chỉ bật Maven 4-only features khi sẵn sàng

Sau khi dual-build xanh, team có hai lựa chọn:

**Lựa chọn A: dùng Maven 4 runtime nhưng giữ model 4.0.0.** Đây là lựa chọn hợp lệ, giảm mức thay đổi.

**Lựa chọn B: bỏ Maven 3 support rồi nâng Build POM lên model 4.1.0**, dùng khả năng mới có chọn lọc.

### 8.1. Model version 4.1.0

Fragment POM Maven 4-only:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.1.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.1.0 https://maven.apache.org/xsd/maven-4.1.0.xsd"
         root="true">
    <modelVersion>4.1.0</modelVersion>
    <groupId>com.example.migration</groupId>
    <artifactId>migration-lab</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>
    <subprojects>
        <subproject>core</subproject>
        <subproject>cli</subproject>
    </subprojects>
</project>
```

**Đây là mô hình minh họa một root POM mới, không phải file thay thế đầy đủ** cho root POM mục 7 (nó cố ý lược properties/dependencyManagement/pluginManagement). Nếu thực hành đổi, giữ các cấu hình cần thiết từ POM đầy đủ khi chuyển. Đặc biệt đừng copy đè file của bạn bằng fragment rồi mất JUnit/plugin versions.

Những thay đổi cần hiểu:
- Namespace/model 4.1.0: Maven 4 Build POM, **Maven 3 không parse**;
- `root="true"`: đánh dấu project root bằng thuộc tính mới; **không có trong model 4.0.0**;
- `<subprojects>`: tên mới thay `<modules>` trong model 4.1.0;
- Có thể dùng Maven 4 infer một số tọa độ version/parent/sibling, nhưng không phải mọi field được phép bỏ;
- Không cần đổi model version chỉ để chạy Maven 4.

### 8.2. Root directory và properties mới

Apache Maven khuyến nghị định nghĩa project root. Có hai cách:
1. Thư mục `.mvn` ở root — **dùng được cả Maven 3 và Maven 4**;
2. Thuộc tính `root="true"` — chỉ trên **model 4.1.0**.

Maven 4 đưa ra properties như `${project.rootDirectory}`, `${session.topDirectory}`, `${session.rootDirectory}` trong context phù hợp. Một số internal/deprecated directory properties trước đây như `executionRootDirectory`, `multiModuleProjectDirectory` có thể không còn tương đương.

**Không global-replace strings trong toàn bộ POM** mà chưa biết plugin nào sử dụng property. Cần test đường dẫn resource, codegen, checkstyle và parent relative paths sau thay.

### 8.3. `<modules>` và `<subprojects>`

Trong model 4.0.0:

```xml
<modules>
    <module>core</module>
    <module>cli</module>
</modules>
```

Trong model 4.1.0:

```xml
<subprojects>
    <subproject>core</subproject>
    <subproject>cli</subproject>
</subprojects>
```

Maven 4 vẫn nhận `<modules>` khi chạy model 4.0.0. Không đổi `<modules>` sang `<subprojects>` mà **quên nâng modelVersion/schema**, hoặc mong Maven 3 hiểu `<subprojects>`.

### 8.4. Version inference và CI-friendly properties

Maven 4 model 4.1.0 có những khả năng suy luận parent project và dependencies giữa các subprojects, giúp giảm GAV lặp lại. Maven 3 có cơ chế CI-friendly versions giới hạn hơn, thường cần khai báo parent version rõ.

**Không tự xóa toàn bộ `<version>` trong mọi dependencies**: chỉ bỏ những trường Maven 4 thực sự infer được trong một reactor đúng, đã kiểm bằng effective model và test clean checkout. Với private parent ngoài reactor, version/relativePath vẫn cần được resolve chính xác.

### 8.5. BOM packaging và consumer POM

Maven 4 model 4.1.0 cung cấp packaging `bom`, tách ý nghĩa Bill of Materials khỏi POM parent/aggregator khi phù hợp. Đây là thay đổi **optional**: dự án có BOM Maven 3 đang publish đúng không bắt buộc đổi ngay.

Maven 4 tạo **consumer POM** (POM được published/installed để tools khác đọc) tách với **Build POM** dùng trong source. Maven 4 rc-7 lưu bản Build POM có classifier `build`; consumer POM dùng model tương thích ecosystem Maven 3.

**Không nhầm “có consumer POM” với “mặc định được flatten hoàn toàn”.** Theo tài liệu Maven 4 rc-7, flattening **mặc định tắt**. Consumer POM mặc định vẫn có thể giữ parent, properties và build configuration; Maven 3 consumers có thể tiếp tục resolve parent. Khi bật `maven.consumer.pom.flatten=true`, nội dung POM được transform mạnh hơn; phải kiểm dependency scopes, BOM imports, metadata và consumers trước khi publish.

Đối với public libraries, một tiêu chí migration bắt buộc là: **artifact được Maven 4 publish có được project Maven 3 downstream sử dụng đúng không?** Build thành công trên Maven 4 **chưa đủ**.

### 8.6. `installAtEnd` và `deployAtEnd` đổi default

Theo Maven 4 migration guide, Maven Install Plugin và Deploy Plugin đổi default `installAtEnd`/`deployAtEnd` thành `true` khi dùng Maven 4.

Điều này có thể tác động:
- Multi-project reactor nơi modules từng được install ngay sau khi build;
- Custom build script tưởng mỗi module xuất hiện sớm trong local repository;
- Release jobs dựa vào deploy order;
- Reactor fail giữa chừng trước khi deploy hoàn tất.

**Không mặc định đặt `installAtEnd=false` để bắt Maven 4 giống mọi hành vi cũ.** Hãy kiểm build assumptions và plugin versions thật. Nếu pipeline phụ thuộc order cũ có lý do chính đáng, cấu hình tường minh và integration-test trên staging repository.

### 8.7. Maven 4 lifecycle và profiles

Ngoài before/after phases, Maven 4 có thay đổi về lifecycle execution scope và profile activation options. Các tính năng này có thể làm behavior của plugin execution khác khi nâng POM.

Kiểm:
- Goals được bind đúng phase, không lặp hoặc bị bỏ qua;
- Failsafe start/stop external containers đúng thứ tự;
- Build profiles không kích hoạt ngoài ý muốn;
- Multi-project parallel builds không thay đổi thứ tự phụ thuộc;
- `-pl`/`-am` và root detection vẫn chọn đúng subprojects.

Không đổi mọi lifecycle feature cùng lúc với nâng runtime Maven.

## 9. CI release rehearsal an toàn

Không dùng `mvn deploy` trực tiếp lên repository production trong lần đầu thử Maven 4. Thứ tự an toàn:

1. Build `clean verify` trên runner sạch;
2. Chạy integration tests, quality checks, SBOM/checksums nếu có;
3. Chạy `install` với local repository cô lập nếu cần kiểm metadata;
4. Dùng **staging repository có GAV/version không xung đột** để thử publish;
5. Dùng một Maven 3 consumer fixture tải artifact từ staging;
6. So dependency graph, POM metadata, jar/classifier contents và tests;
7. Chỉ cho phép production deploy sau approval.

**Tránh publish một GAV immutable đã tồn tại rồi ghi đè.** Nếu thử Maven 4 RC, dùng test artifacts/versions và repo được phép xóa sau thử nghiệm theo chính sách. Không dùng private credentials trong POM hoặc build logs được chia sẻ.

### Maven 3 consumer fixture để test published Maven 4 output

Một project Maven 3 với POM model 4.0.0, dependency tới artifact bạn vừa publish trên staging và repository config hợp lệ nên chạy:

```bash
"$MVN3" -B -ntp clean verify
```

Phải xác minh POM/dependencies/classes theo contract, không chỉ Maven 3 parse được consumer POM. Nếu consumer build cần parent POM trên private repo, staging/proxy config cũng phải cung cấp parent đó.

## 10. Các lỗi thường gặp khi thử Maven 4

| Triệu chứng | Nguyên nhân nghi ngờ | Cách kiểm |
| --- | --- | --- |
| Maven 4 không khởi động | JVM dưới Java 17 hoặc JAVA_HOME sai | `mvn -version`, JDK install |
| Maven 3 không parse sau khi đổi POM | Đã bật model 4.1.0 | Revert hoặc kết thúc dual-build theo kế hoạch |
| Duplicate plugin errors | POM khai báo cùng plugin nhiều lần | Gộp plugin entries |
| POM `relativePath` fail | Parent local path/GAV sai | Tính path từ child POM |
| Plugin goal không load | Maven API/plugin version không tương thích | Upgrade plugin có kiểm chứng |
| Core extension crash | `.mvn/extensions.xml` extension dùng API cũ | Test/upgrade/replace extension |
| `pre-integration-test` không chạy | Lifecycle phase semantics đổi | Rà before/after phase theo guide |
| Repo credentials fail | Maven resolver/settings/mirror khác | Kiểm id, settings, proxy và TLS |
| Maven 4 chọn root sai | Không có `.mvn`, root inference khác | Đặt `.mvn` ở root |
| Build pass nhưng tests giảm | Profiles/plugin config khác | So Surefire/Failsafe reports |
| JAR hash khác | Timestamp/manifest/archive tools khác | Diff entries, cấu hình reproducibility |
| `mvnup apply` làm diff lớn | Tool đổi model/inference/versions | Review diff và chạy A/B |
| Builds chậm hơn | Cold cache, extensions, tests/parallel behavior | Đo warm clean nhiều lượt |
| `install`/`deploy` order khác | installAtEnd/deployAtEnd defaults | Test staging, explicit configs nếu cần |
| Maven 3 downstream không lấy được artifact | Consumer POM/parent/dependency metadata | Test Maven 3 fixture từ staging |
| CI chạy sai Maven version | Wrapper/PATH/docker image chưa pin | Print `mvn -version` mỗi job |
| `-T` gây flaky tests | Parallelism, thread-unsafe plugins | Trở về sequential, xem logs |
| Deprecated internal property | Maven 4 root/path properties thay đổi | Rà interpolation và file paths |
| Maven 4 RC regression | Thay đổi trước GA | Tối thiểu hóa reproducer, báo issue |

### Đọc lỗi đúng thứ tự

1. Ghi exact Maven distribution, Java runtime, source commit.
2. Chạy `validate`/`clean verify` trên Maven 3 baseline.
3. Chạy cùng goals trên Maven 4, dùng `-e` khi cần stacktrace.
4. Xác định lỗi **model**, **plugin**, **dependency resolution**, **test**, **packaging** hay **deploy**.
5. Chỉ thay một điều kiện mỗi lần.
6. Chạy lại Maven 3 để bảo đảm fix vẫn dual-compatible.
7. Kiểm artifacts và downstream consumer.
8. Báo upstream khi nghi regression, cung cấp minimal reproducer sau khi lọc thông tin nhạy cảm.

**Đừng dùng `-X` debug log công khai** nếu có private repository URLs, token/proxy settings hoặc CI secrets.

## 11. Gắn nhãn các mức hoàn thành migration

| Mức | Điều được phép tuyên bố | Điều chưa nên tuyên bố |
| --- | --- | --- |
| PREPARED | Build ổn trên Maven 3 được hỗ trợ, JDK17, plugins đã kiểm | Maven 4 đã hoạt động |
| DUAL_BUILD_PASS | Maven 3 và Maven 4 xây cùng source/tests trong scope đã kiểm | Mọi third-party plugin và deploy pipeline production an toàn |
| RELEASE_REHEARSAL_PASS | Staging publish + Maven 3 consumer tests đã đạt | Production đã chính thức chuyển |
| MAVEN4_RUNTIME_DEFAULT | CI/release dùng Maven 4, rollback pin còn hoạt động | Đã bật model 4.1 nếu chưa |
| MAVEN4_MODEL_4_1 | Build POM dùng 4.1 và features có chọn lọc | POM build vẫn chạy Maven 3 |
| MIGRATION_COMPLETE | Contract, QA, release, monitoring, rollback và ownership đã chốt | Tất cả version Maven 4 tương lai đều tương thích |

Tên mức ở bảng là **quy ước quy trình trong bài**, không phải trạng thái có sẵn của Maven CLI.

## 12. Checklist thực hiện theo sprint

### Sprint chuẩn bị

- [ ] Ghim source commit và Maven 3 baseline.
- [ ] Chạy toàn bộ `clean verify` và release-profile tests.
- [ ] Chuyển Maven runtime JDK sang 17+ trên local/CI.
- [ ] Xác nhận target Java bytecode của project không bị đổi vô ý.
- [ ] Kiểm kê POM parent, BOM, plugins, core extensions và custom goals.
- [ ] Ghim plugin versions được hỗ trợ trên Maven 3.
- [ ] Dọn duplicate plugins, lỗi POM model và warnings đã biết.
- [ ] Xác minh Wrapper, settings, mirrors/proxies, CI credentials.
- [ ] Ghi baseline artifacts/tests/report và rollback plan.

### Sprint chạy thử

- [ ] Cài Maven 4 RC/GA phiên bản cố định trong job riêng.
- [ ] Giữ `modelVersion 4.0.0`, không dùng `<subprojects>`/root attr sớm.
- [ ] In `mvn -version` trong cả hai jobs.
- [ ] Chạy dual-build với cùng source/goals/profiles/JDK.
- [ ] Kiểm plugin compatibility và `.mvn/extensions.xml`.
- [ ] Phân loại model warnings/errors, không chỉ xem BUILD SUCCESS.
- [ ] Dùng `mvnup check --model-version 4.0.0` để review.
- [ ] Chỉ apply fixes trong nhánh có diff review.
- [ ] Re-run Maven 3 sau mỗi Maven 4 compatibility fix.
- [ ] So tests, artifacts, dependencies, packaging và performance.
- [ ] Thử Maven 4 staging publish, Maven 3 consumer nếu project phát hành libraries.
- [ ] Giữ Maven 3 làm production default đến khi gates đủ.

### Sprint chuyển đổi có kiểm soát

- [ ] Quyết định Maven 4 runtime thành default sau approval.
- [ ] Pin Maven version trong Wrapper/CI.
- [ ] Kiểm Install/Deploy plugin defaults, repository metadata.
- [ ] Chạy production-like release rehearsal ở staging.
- [ ] Monitor failures và có rollback executable.
- [ ] Quyết định có thật sự cần model 4.1.0 không.
- [ ] Nếu có, chạy `mvnup check --model-version 4.1.0 --all`.
- [ ] Đưa model 4.1 sang branch riêng, test mọi parent/BOM/subprojects.
- [ ] Chỉ thay `<modules>` bằng `<subprojects>` khi schema phù hợp.
- [ ] Kiểm consumer POM và Maven 3 downstream dùng artifact đã publish.
- [ ] Review flattening policy trước khi bật.
- [ ] Kiểm các root/path properties và profile/lifecycle behaviors.
- [ ] Cập nhật engineering docs, onboarding và CI templates.
- [ ] Dọn Maven 3 job theo chính sách khi giai đoạn dual-build kết thúc.

## 13. Câu hỏi thực hành

1. Maven 4 yêu cầu JDK bao nhiêu để **chạy Maven**? Điều đó có bắt Java application target cùng mức không?
2. Vì sao nên nâng Maven 3 baseline và dọn warnings trước khi thử Maven 4?
3. Khi dual-build, vì sao phải giữ `modelVersion 4.0.0`?
4. `mvnup check` khác `mvnup apply` ở đâu?
5. Vì sao không nên chạy `mvnup apply --model-version 4.1.0` trên branch còn dùng Maven 3 CI?
6. Plugin chạy trên Maven 3.9 có chắc hoạt động trên Maven 4 không?
7. Khi nào `--fail-on-severity WARN` hữu ích?
8. Vì sao Maven 4 chạy trên Java17 không bắt bạn phát hành JAR Java17?
9. `<modules>` và `<subprojects>` khác nhau theo POM model nào?
10. `.mvn` root marker có hoạt động với Maven 3 không?
11. `root="true"` được phép trong model 4.0.0 không?
12. Consumer POM Maven 4 có luôn được flatten đầy đủ theo default không?
13. Vì sao cần test Maven 3 downstream consumer sau khi artifact được Maven 4 publish?
14. Vì sao không chạy hai versions Maven đồng thời trong một workspace `target`?
15. `installAtEnd`/`deployAtEnd` đổi defaults có thể ảnh hưởng pipeline ra sao?
16. Trong ví dụ, module `cli` phụ thuộc module nào?
17. Java `Main` in đúng hai dòng nào?
18. Sau khi đã bật model 4.1.0, muốn rollback Maven 3 thì chỉ đổi PATH có đủ không?
19. Những hạng mục release nào chưa được chứng minh bởi `mvn clean verify`?
20. Khi gặp regression trên Maven 4 RC, nên thu thập bằng chứng gì trước khi mở issue?

### Đáp án định hướng

- **1:** JDK 17+ chạy Maven; project target có thể khác nếu compiler/toolchain hỗ trợ.
- **2:** Giảm biến số và chuẩn hóa nguồn so sánh.
- **3:** Giữ Maven 3 compatibility và rollback.
- **4:** Check dry-run, apply viết POM.
- **5:** Build POM 4.1 là Maven 4-only.
- **6:** Không chắc; custom/legacy API và extensions có thể fail.
- **7:** Khi muốn Maven 4 biến warnings đã được phân loại thành gate fail.
- **8:** Maven process runtime khác compiler target.
- **9:** Modules của 4.0.0; subprojects trong 4.1.0.
- **10:** Có.
- **11:** Không; đó là tính năng model 4.1.0.
- **12:** Không; flatten mặc định tắt trong rc-7.
- **13:** Để bảo đảm parent/dependency/classifier metadata cho ecosystem.
- **14:** Các builds có thể đè file `target`, test reports và cleanup.
- **15:** Artifact install/deploy được hoãn đến cuối build, thay timing/order.
- **16:** `migration-core`.
- **17:** `Migration lab: READY` và `Core check: OK`.
- **18:** Không; phải revert POM/schema/plugins Maven 4-only.
- **19:** Staging deploy, downstream consumers, artifact metadata, full release plugins.
- **20:** Maven/JDK version, commit, exact goals/profiles, logs/stacktrace, minimal reproducer.

## 14. Kết luận và quy tắc quyết định

**Đừng bắt đầu Maven 4 bằng việc đổi toàn bộ POM sang 4.1.0.** Cách ít rủi ro theo Apache Maven là:

**Chuẩn bị trên Maven 3 → chạy thử Maven 4 song song, chỉ sửa lỗi tương thích → chấp nhận release gates → mới cân nhắc Maven 4-only features.**

Cấu trúc này giữ source và tests làm chuẩn so sánh, cho phép rollback đơn giản trước breaking changes và tránh biến RC compatibility issues thành production outages. Model 4.1.0, subprojects, BOM packaging, version inference và consumer POM là những **khả năng đáng tìm hiểu**, nhưng không phải điều kiện để Maven 4 build một project Maven 3 POM hợp lệ.

Nếu một thành phần chưa tương thích (custom plugin, extension, CI publisher), ghi blocker và giữ production Maven 3 cho đến khi sửa hoặc có workaround được kiểm thử. **Một kế hoạch migration tốt cho phép tạm dừng an toàn**, không đổi tất cả trong một lần.

## Tài liệu Apache Maven chính thức

- [Starting with Maven 4 — Migration Guide](https://maven.apache.org/guides/mini/guide-migration-to-mvn4.html)
- [What's new in Maven 4?](https://maven.apache.org/whatsnewinmaven4.html)
- [Maven Upgrade Tool (`mvnup`)](https://maven.apache.org/tools/mvnup.html)
- [Maven Releases History](https://maven.apache.org/docs/history.html)
- [Maven 4.0.0-rc-7 Release Notes](https://maven.apache.org/docs/4.0.0-rc-7/release-notes.html)
- [Apache Maven POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven — Multi-Module Projects](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Maven Wrapper Plugin](https://maven.apache.org/wrapper/maven-wrapper-plugin/)
- [Apache Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/)
- [Apache Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/)
- [Apache Maven — Plugins Compatibility Plan](https://maven.apache.org/developers/compatibility-plan.html)
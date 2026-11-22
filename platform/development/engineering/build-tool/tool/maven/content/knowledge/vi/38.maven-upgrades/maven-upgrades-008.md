# Rà soát thay đổi về profile, reactor và hành vi install/deploy khi nâng cấp Maven

## 1. Vì sao một lần nâng cấp Maven có thể thay kết quả dù không sửa mã Java?

Giả sử một dự án có nhiều module, trước đây chạy được với Maven 3.9 và một tập plugin 3.x. Sau khi chuyển Maven runtime, Maven Wrapper hoặc plugins sang dòng mới, nhóm gặp ba hiện tượng:

1. Pipeline dùng `-Pci,legacy` vốn chỉ cảnh báo khi profile `legacy` không tồn tại; Maven mới báo lỗi thay vì bỏ qua.
2. Một lệnh resume reactor không còn chọn đúng các module như trước, hoặc cách dùng `-pl`, `-am`, `-rf` tạo tập modules khác; một module từng cần `mvn install` để tìm sibling dependency nay có thể được xử lý trong reactor.
3. Những JAR/POM từng xuất hiện sớm trong `~/.m2/repository` hoặc một remote Maven repository không còn được cài đặt/triển khai vào đúng thời điểm mà script ngoài Maven giả định.

Đây không phải các lỗi của Java compiler. Chúng liên quan tới **mô hình build**: active profiles làm thay effective POM và tập subprojects; reactor điều phối thứ tự và lựa chọn projects; lifecycle goals `install` và `deploy` tạo side effects lên repositories.

> **Khi nâng cấp Maven, không chỉ hỏi “BUILD SUCCESS không?” mà phải so các active profiles, tập module được build, thứ tự/đồ thị reactor, và artifacts đã install/deploy ở thời điểm nào.** Với hệ thống phát hành, điều kiện quan trọng còn là không publish bất kỳ artifact nào từ build chưa được kiểm đủ.

Bài thuộc nhóm **Nâng cấp Maven — Build Tool Maven**. Trọng tâm là quy trình rà soát từ **Maven 3.9.x** sang dòng **Maven 4.0.x (RC hoặc stable mà môi trường thực tế đã chọn)**, đồng thời áp dụng được cho các lần nâng Maven 3 hoặc nâng Maven Install/Deploy Plugins. Tài liệu Apache “Starting with Maven 4” khuyến nghị ba bước: chuẩn bị bản Maven 3.9, thử Maven 4 với thay đổi tối thiểu, sau đó mới sử dụng đặc tính POM 4.1.0. **Không mặc định toàn bộ hành vi Maven 4 áp dụng cho một project chỉ vì tên Maven CLI đã đổi**: plugin version, POM model, profile activation và lệnh chạy đều góp phần quyết định.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Xây baseline và matrix so Maven/JDK/plugin versions.
- Dùng `help:active-profiles` và `help:effective-pom` để kiểm profiles thật.
- Hiểu việc Maven 4 từ chối profile không tồn tại và cú pháp `-P?optional-id`.
- Xác định rủi ro `activeByDefault`, settings profiles, activation bằng property/JDK/OS/file.
- Kiểm tập modules khi root POM có profile thêm `<modules>`, và sự khác nhau giữa `<modules>` và `<subprojects>`.
- Dùng `-pl`, `-am`, `-amd`, `-rf` và Maven 4 `--resume`/`-r` đúng mục đích.
- Phân biệt `mvn verify`, `mvn install` và `mvn deploy`, tránh install chỉ để reactor build được.
- Hiểu `installAtEnd` và `deployAtEnd`: khác nhau giữa plugin 3.x và nhánh plugin/Maven 4, cùng giới hạn không-atomic của deploy.
- Biết vì sao JAR/POM đã install/deploy có thể gây sai lệch CI, caching và partial releases.
- Chạy một lab Maven multi-module bằng **Java 17/JUnit 5**, có profile làm đổi output và profile làm đổi tập modules.
- Kiểm hành vi deploy an toàn bằng một repository `file://` giả lập, **không dùng production credentials**.
- Viết checklist migration và rollback dựa trên bằng chứng thay vì đoán.

## 2. Cần phân biệt bốn loại “nâng cấp”

### 2.1. Maven runtime

Ví dụ dùng Maven Wrapper hoặc binary cài ngoài để chuyển Maven 3.9.x sang Maven 4.0.x. Maven runtime mới có thể thay:
- model validation, lỗi/warning;
- profile CLI semantics;
- reactor graph and resume behavior;
- lifecycle default bindings và scheduling;
- các thông tin root directory được công bố;
- Maven Resolver version/transport defaults.

**Maven 4 yêu cầu JDK 17 để chạy**, theo hướng dẫn migration. Maven 3.9 cũng có thể chạy trên Java 17, nên nên chuẩn bị môi trường bằng cách đưa JDK lên 17 ngay khi còn ở Maven 3.

### 2.2. Plugin versions

Maven Install Plugin 3.x và Install Plugin 4.x, Deploy Plugin 3.x và Deploy Plugin 4.x là **các plugin versions khác nhau**, dù cùng command `mvn install`/`mvn deploy`. Nhiều tham số được định nghĩa trong plugin descriptor và có mặc định riêng theo version.

Ví dụ đã được tài liệu Apache ghi nhận:
- **Install Plugin 3.2.0:** `installAtEnd` mặc định `false`.
- **Deploy Plugin 3.2.0:** `deployAtEnd` mặc định `false`.
- **Maven 4 migration hướng tới plugin versions tương thích Maven 4:** hai mặc định tương ứng chuyển sang `true`.

Vì vậy **không khẳng định mọi invocation chạy bằng Maven 4 chắc chắn có giá trị true** nếu project vẫn pin plugin 3.x hoặc có cấu hình override. Hãy xác minh goal descriptor, plugin version và effective settings/parameters của **lệnh thực tế**.

### 2.3. POM model 4.0.0 so với 4.1.0

Maven 4 vẫn có thể build nhiều dự án dùng `<modelVersion>4.0.0</modelVersion>`. POM model 4.1.0 cung cấp đặc tính mới như `root="true"`, `<subprojects>`, optional profile declarations, BOM packaging và một số version/model improvements.

**Migration an toàn:** giữ model 4.0.0 trong giai đoạn tương thích Maven 3/Maven 4, xử lý warnings và kiểm CI, sau đó mới chuyển sang 4.1.0 nếu đã quyết định không cần Maven 3 nữa. Chuyển sang POM 4.1.0 quá sớm sẽ làm Maven 3 không còn xử lý được project.

### 2.4. Settings, Wrapper và môi trường

Một bản Maven mới có thể vô tình:
- đọc `settings.xml` khác;
- dùng local repository khác;
- thay `JAVA_HOME` hoặc Toolchains;
- thay mirror/proxy hoặc credentials;
- hoạt động trên runner/Linux/Windows image khác;
- dùng plugin version từ Super POM mới.

**Không quy mọi khác biệt do Maven Core khi bằng chứng chỉ ra CI runtime/settings hoặc plugin versions thay đổi cùng lúc.**

## 3. Baseline: thu thập bằng chứng trước khi chỉnh POM

### 3.1. Ma trận kiểm thử

Một bảng migration có thể bắt đầu như sau:

| Case | Maven | JDK | POM model | Plugin install/deploy | Mục tiêu |
| --- | --- | --- | --- | --- | --- |
| A — baseline | Maven 3.9.x đã kiểm | 17 | 4.0.0 | 3.x được pin | Đo hành vi cũ |
| B — compatibility | Maven 4 được chọn | 17 | 4.0.0 | Giữ plugin 3.x tương thích | Tìm thay đổi Core |
| C — plugin migration | Maven 4 được chọn | 17 | 4.0.0 | Phiên bản plugin 4.x phù hợp | Tìm thay đổi plugin defaults |
| D — POM modernization | Maven 4 được chọn | 17+ | 4.1.0 | Plugins đã kiểm | Thử features mới |

Không làm cả bốn thay đổi trong một commit. Khi Case B fail, việc tách versions giúp xác định có phải Maven Core/profile/reactor hay không. Nếu Case B pass nhưng Case C fail, tập trung vào plugin compatibility/defaults.

### 3.2. Ghi phiên bản thực tế

```bash
mvn -version
java -version
```

Nếu dùng Maven Wrapper:

```bash
./mvnw -version
```

Trên Windows:

```powershell
.\mvnw.cmd -version
```

`mvn -version` và `./mvnw -version` có thể khác nhau; **CI phải dùng đúng binary/Wrapper mà matrix khai báo**. Ghi version, Java home, OS, locale/encoding, runner image và checksum của Maven distribution khi policy yêu cầu.

### 3.3. Kiểm active profiles

Một cách dùng Maven Help Plugin:

```bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.1:active-profiles
mvn -B -ntp -Pci-strict org.apache.maven.plugins:maven-help-plugin:3.5.1:active-profiles
```

Lệnh sẽ cho biết profiles active theo từng project trong reactor. Không giả định chỉ nhìn root POM là đủ: một child có thể có profile của chính nó hoặc settings profile kích hoạt khác.

Kiểm effective POM khi có profile:

```bash
mvn -B -ntp -Pci-strict -pl :app \
  org.apache.maven.plugins:maven-help-plugin:3.5.1:effective-pom \
  -Doutput=target/effective-app.xml
```

Dấu `\` trên dòng lệnh là cách xuống dòng **POSIX shell**; trên PowerShell hãy viết nguyên trên một dòng hoặc dùng backtick continuation đúng chuẩn PowerShell. `target/effective-app.xml` là file phân tích cục bộ. Khi dùng nhiều modules, cần xác định mỗi module có effective POM riêng; so XML đã xử lý profiles/inheritance, không chỉ so raw POM.

### 3.4. Các dữ kiện nên lưu

Trong baseline record hoặc CI artifacts:
- `mvn -version` và profile list;
- reactor project order/tổng module count;
- checksum/tên JAR/POM chính và attached artifacts;
- compilation/test counts; test skipped status;
- plugin versions Install/Deploy;
- local repository path và contents mới được install;
- remote repository target (dùng sandbox khi kiểm);
- các command flags (`-P`, `-pl`, `-am`, `-rf`, `-T`);
- log warnings từ model validation và plugin executions.

Khi rollback, bạn cần biết một thay đổi xuất phát từ Maven binary, plugin version, settings, POM model hay nguồn dependency. Không lưu deploy token/SSH secrets trong logs.

## 4. Profile activation khi nâng cấp Maven

### 4.1. Các nguồn profile

Maven có profiles trong:
- `pom.xml` của project hoặc parent;
- user settings `~/.m2/settings.xml`;
- global Maven settings tương ứng với bản Maven đã cài.

Profiles có thể được kích hoạt bằng `-P`, `<activeProfiles>` trong settings, `activeByDefault`, JDK/OS/property/file conditions.

**Các profile không được thừa kế nguyên bản như một đối tượng:** Maven Model Builder xử lý active profiles sớm, **chỉ các hiệu ứng phù hợp** như properties/plugins mới được kế thừa vào child POM. Implicit activation của profile thuộc POM nào thì xét trong ngữ cảnh POM đó, không chỉ dựa vào tên profile trùng nhau ở module khác.

### 4.2. Maven 4 từ chối profile không tồn tại

Đây là một breaking change dễ gặp trong CI scripts. Ví dụ:

```bash
mvn -B -ntp -Pci-strict,legacy verify
```

Nếu project/repo không có profile `legacy`:
- Maven 3 thường có thể cảnh báo rồi tiếp tục với các profiles tìm được.
- Maven 4 **không chấp nhận** activation/deactivation của profile không thể resolve, và build fail.

Nếu một profile thật sự **tùy chọn** trong môi trường chạy, Maven 4 có cú pháp:

```bash
mvn -B -ntp '-Pci-strict,?legacy' verify
```

Dấu `?` là yêu cầu optional **chỉ cho tên profile đó**. Cú pháp Maven 4 này không nên được giả định làm việc tương đương trong Maven 3; dùng điều kiện riêng trong CI matrix nếu cần duy trì Maven 3.

**Khuyến nghị:** Không gắn `?` cho profile bắt buộc như `release-sign` hoặc `security-check` chỉ để build xanh. Nếu thiếu profile quan trọng, phải fail. Optional marker phù hợp một profile hỗ trợ environment tùy chọn, không phải một cách vô hiệu hóa security gate.

### 4.3. activeByDefault có thể bị tắt bất ngờ

```xml
<profiles>
    <profile>
        <id>development-defaults</id>
        <activation>
            <activeByDefault>true</activeByDefault>
        </activation>
        <properties>
            <demo.mode>base</demo.mode>
        </properties>
    </profile>
</profiles>
```

Khi một profile khác **trong cùng POM** được activate, profile activeByDefault thường bị deactivated. Vì vậy một lệnh mới có `-Pci-strict` có thể làm default values biến mất nếu dự án đặt mọi cấu hình nền chỉ trong `activeByDefault`.

Cách an toàn:
- Đưa giá trị cơ sở cần mọi build vào `<properties>` ngoài profile.
- Chỉ override những gì thật sự khác trong profiles.
- Dùng `help:active-profiles` và `help:effective-pom` để so trước/sau nâng cấp.
- Không coi `activeByDefault` là “bật vĩnh viễn”.

### 4.4. Settings profiles và CI

Một settings fragment:

```xml
<settings>
    <activeProfiles>
        <activeProfile>corporate-mirror</activeProfile>
    </activeProfiles>
</settings>
```

có thể làm các repository/mirror/credentials behavior khác giữa developer và CI. **Đây chỉ là fragment minh họa**, không phải file settings đầy đủ và không có secrets.

Khi kiểm cấu hình:
- Ghi settings file thực tế (`-s ci-settings.xml` nếu được dùng).
- Xác nhận profile IDs/activation.
- Kiểm repository/mirror ID, local repository và pluginRepositories.
- Đừng dựa vào một property chỉ có trong settings profile để suy rằng project POM profile với cùng ID đã được activate theo đúng cách bạn nghĩ.

### 4.5. Property, OS, JDK và file activation

Một profile có thể dùng:

```xml
<activation>
    <property>
        <name>enable.audit</name>
        <value>true</value>
    </property>
</activation>
```

và được kích hoạt bằng:

```bash
mvn -Denable.audit=true verify
```

Khi nâng JVM/OS/CI, profile activation dựa `<jdk>` hoặc `<os>` có thể đổi dù bạn không chỉnh POM. Tương tự, điều kiện tồn tại file phụ thuộc working directory/filesystem.

Đối với Maven 4 POM model 4.1.0 còn có `<condition>` activation expressions mới; **không copy chúng vào POM 4.0.0 đang cần tương thích Maven 3**. Kiểm docs target version và chạy matrix để chắc profile condition mới không bật sai môi trường.

### 4.6. Profile order và xung đột properties

Khi nhiều active profiles trong cùng POM khai cùng property, thứ tự profile declarations có thể quyết định giá trị kết quả theo Maven Model Builder rules. Không xây business logic nhạy cảm dựa trên xung đột properties giữa nhiều profiles.

Để giảm rủi ro:
- Mỗi property quan trọng có ownership rõ.
- Nếu môi trường khác nhau, đặt distinct profile IDs với mục đích rõ.
- Ghi explicit `-P` trong CI.
- So effective POM của từng module, thay vì đoán theo thứ tự CLI flags.
- Dùng Enforcer hoặc kiểm effective properties trong CI trước khi publish.

## 5. Reactor: một lần nâng Maven có thể đổi tập modules được build

### 5.1. Reactor là gì?

Reactor tập hợp subprojects/modules, sắp xếp thứ tự và chạy lifecycle trên các projects đã chọn. Nó xét những quan hệ đã được instantiate như:
- project dependency của module này vào module kia;
- parent relationship;
- plugin/module relationship;
- build extension;
- thứ tự khai `<modules>` khi không có ràng buộc khác.

Chỉ có `dependencyManagement` không tự tạo dependency edge trong reactor; muốn project B build sau A vì B dùng A, phải có dependency thực trong POM B.

### 5.2. Hai thao tác cần tách

**Collect/discover:** Maven biết những module nào tồn tại và nằm trong reactor.

**Select:** Maven quyết định module nào được build cho một CLI invocation, dựa vào current directory, `-f`, `-pl`, `-am`, `-amd`, `-rf` và profile modules.

Một profile khai thêm module vào root sẽ thay **collection**; `-pl :app` sau đó thay **selection**. Nếu pipeline mới xuất hiện/tắt profile, có thể build thiếu module dù cả hai bản Maven đều báo `BUILD SUCCESS`.

### 5.3. Flags quan trọng

| Flag | Mục đích | Rủi ro khi nâng cấp |
| --- | --- | --- |
| `-pl :app` | Chọn project theo artifactId | Có thể chỉ chọn app, thiếu upstream artifact |
| `-pl :app -am` | Chọn app và upstream reactor dependencies | Thường phù hợp hơn build một module độc lập |
| `-pl :api -amd` | Chọn api và downstream dependents | Tốt để kiểm thay đổi API lan tới app |
| `-rf :app` | Resume từ app theo thứ tự reactor | Maven 3 có thể thiếu upstream artifact chưa install |
| `--resume` / `-r` (Maven 4) | Resume previous failed reactor state | Không coi là có trên mọi bản Maven 3 |
| `-N` | Non-recursive; chỉ project được chọn | Không kiểm cả multi-module build |
| `-ff` | Fail fast, dừng ở lỗi đầu tiên | Dễ đo nhưng không thấy mọi lỗi độc lập |
| `-fae` | Fail at end, cố build các module không phụ thuộc lỗi | Không được dùng làm điều kiện publish |
| `-fn` | Fail never, có thể trả exit code 0 dù build fail | Tuyệt đối không cho release gate |

Thử CLI từ **root** với `-pl` selectors tường minh. Đừng chỉ so wall time khi một phiên bản thực ra build ít module hơn.

### 5.4. Maven 4 cải thiện resume

Maven 3 có một trường hợp nổi tiếng: sau khi module app fail, gợi ý `-rf :app` có thể fail ngay vì upstream dependency (api) đã build nhưng chưa `install`, và resume không build lại api. Maven 4 khắc phục vấn đề xử lý `--also-make`/resume trong nhiều tình huống và bổ sung `--resume` (`-r`), nhận biết những subprojects đã build thành công khi resume.

Tuy vậy:
- `-rf :app` vẫn có ý nghĩa **chọn từ một điểm reactor** và có thể bỏ upstream tùy selection.
- Maven 4 resume cần build state thích hợp; không thay thế việc kiểm source/inputs khi CI container mới.
- Maven 3 workaround an toàn thường là `mvn -pl :app -am verify` thay vì install tất cả upstream artifacts vào global local repo.
- `-rf` và `-r` **không phải luôn cùng một chức năng**; đừng thay string đơn giản trong CI scripts mà không có integration test.

### 5.5. Maven 4 root/subprojects và Model 4.1.0

Ở Maven 3/POM model 4.0.0:

```xml
<modules>
    <module>api</module>
    <module>app</module>
</modules>
```

Trong POM model 4.1.0 của Maven 4, có cú pháp:

```xml
<subprojects>
    <subproject>api</subproject>
    <subproject>app</subproject>
</subprojects>
```

**Đây là hai fragments từ hai model versions khác nhau**, không thay thế tự động trong lab Maven 3-compatible. Maven 4 vẫn hỗ trợ `<modules>`, nhưng nó đã được đánh dấu deprecated trong model 4.1.0 và có thể bị loại ở tương lai.

Root directory có thể được xác định bằng `.mvn` directory hoặc `root="true"` (trên POM model 4.1.0). Maven 4 còn cải thiện nhận diện subprojects khi chạy từ thư mục con và có behavior khác về module auto-discovery cho một số POM 4.1.0 setup. Cần kiểm reactor summary **thật**, không suy từ cây thư mục.

### 5.6. Concurrent builder

Maven 4 có lifecycle representation dạng tree với cơ chế phase scheduling chi tiết hơn, và có concurrent builder có thể được bật chủ động (ví dụ `-b concurrent` theo docs). Không giả định một build dùng Maven 4 tự nhiên chạy song song giống mọi kịch bản mặc định.

Nếu thử builder này:
- kiểm multi-module order và plugin thread safety;
- tránh shared output directories;
- so test reports, attached artifacts, install/deploy side effects;
- tách nó khỏi thí nghiệm profiles và defaults.

Một pipeline có kết quả khác khi bật concurrent builder phải được điều tra về race/state của plugins, không tự quy là bug Maven 4.

## 6. Install và deploy: khác gì với verify?

### 6.1. Ba lệnh, ba phạm vi tác động

| Lệnh | Tác dụng chính | Side effects |
| --- | --- | --- |
| `mvn clean verify` | Compile/test/package và verify theo lifecycle | Tạo `target`, không mặc định install/publish |
| `mvn clean install` | Verify rồi install artifacts của projects vào **local Maven repository** | Thay đổi `~/.m2/repository` (hoặc repo tùy chọn) |
| `mvn clean deploy` | Verify, install và deploy theo lifecycle/bindings được áp dụng | Có thể upload remote artifacts và thay metadata |

Với Maven 3 default lifecycle, `deploy` đến sau `install`. Maven 4 dùng lifecycle tree và hỗ trợ một số cách thực hiện deploy mà không cần install như cách sắp xếp truyền thống, nhưng **compatibility default** được thiết kế nhằm giữ tương thích với nhiều Maven 3 projects.

Vì vậy audit phải **quan sát plugin goals chạy thực tế**, không tự động kết luận “Maven 4 deploy luôn không install”. Với nhiều builds thường ngày, Apache Maven khuyến nghị **`mvn verify` thay cho `mvn clean install`**: reactor tự biết sibling dependencies, tránh ghi local repository nếu không cần.

### 6.2. installAtEnd và deployAtEnd

**`installAtEnd`** thuộc Maven Install Plugin; **`deployAtEnd`** thuộc Maven Deploy Plugin.

Hai cờ cùng trả lời câu hỏi: “Thực hiện tác động lên repository ngay lúc mỗi module tới lifecycle phase, hay trì hoãn cho tới cuối batch?”

- Khi `installAtEnd=false`, mỗi project có thể được install vào local repository trong own install phase. Nếu module sau fail, những module trước có thể đã được cài.
- Khi `installAtEnd=true`, install requests được defer, giảm nguy cơ local repo có artifacts của một reactor build chưa toàn bộ thành công.
- Khi `deployAtEnd=false`, mỗi project có thể upload sớm; module sau fail khiến remote có một phần release.
- Khi `deployAtEnd=true`, deploy requests được gom rồi gửi khi các project có deploy execution đạt thời điểm batch; giảm nguy cơ publish trước lỗi ở modules trước đó.

### 6.3. Bảng mặc định phải kiểm

| Môi trường/plugin | `installAtEnd` | `deployAtEnd` | Ý nghĩa |
| --- | --- | --- | --- |
| Maven Install Plugin 3.2.0 và Deploy Plugin 3.2.0 | `false` mặc định | `false` mặc định | Side effects per module trừ khi override |
| Plugin/Maven 4 dòng mới theo migration guide | `true` mặc định | `true` mặc định | Deferred by default |
| POM/CLI khai rõ true/false | Theo cấu hình hiệu lực | Theo cấu hình hiệu lực | Explicit policy có thể override default |

**Chốt:** Mặc định gắn với **plugin implementation và phiên bản được thực thi**. Maven Core có thể cung cấp bindings mới cho plugin major tương ứng. Không so Maven 3 và Maven 4 trong khi vô tình dùng hai phiên bản plugin khác mà không ghi lại.

### 6.4. Deploy deferred không phải giao dịch atomic

**`deployAtEnd=true` không bảo đảm tất cả-or-không-gì-cả.** Theo tài liệu Deploy Plugin:
- Một batch có nhiều repositories vẫn có thể deploy tuần tự; lỗi giữa batch để lại artifacts đã upload trước đó.
- Một số modules không gắn deploy execution có thể chạy sau thời điểm batch flush và vẫn fail.
- Module cấu hình `deployAtEnd=false` có thể upload sớm, không được “rút lại” bởi việc defer module khác.
- Registry có immutable release policy; upload một phần có thể không rollback/redeploy được cùng version.

**Cần staging/promotion, repository policy, idempotency và manual recovery runbook** cho release nghiêm túc. Đừng viết báo cáo “atomic deploy” chỉ vì Maven có flag at-end.

### 6.5. Vấn đề local install pollution

`mvn install` đưa artifacts vào local Maven repository. Trong CI/dev:
- một run fail về sau có thể để lại artifacts đã install từ modules chạy trước;
- các build sau có thể resolve chúng dù source hiện tại khác hoặc branch khác;
- test resume Maven 3 có thể “tình cờ thành công” nhờ local repo cũ, khiến thiếu dependency build edge bị che khuất.

Để audit:
- dùng local repo cách ly khi cần;
- so thời điểm path xuất hiện;
- không xóa global `~/.m2` để tạo môi trường sạch;
- dùng `mvn verify` cho regular CI;
- chỉ dùng install khi thực sự cần tiêu thụ artifacts bên ngoài reactor hoặc để kiểm publish steps.

## 7. Lab Java 17/JUnit 5: profiles và reactor thật

Bài thực hành gồm một parent aggregator, một thư viện `api`, một ứng dụng `app` phụ thuộc `api` và một module `report` chỉ xuất hiện khi bật profile `with-report`. Profile `ci-strict` đổi một property được filter vào resource. Nhờ đó:
- `ci-strict` làm **đầu ra Java đổi**;
- `with-report` làm **tập modules đổi**;
- `-pl/-am/-amd` làm **tập modules chạy đổi**;
- `installAtEnd/deployAtEnd` có thể được kiểm an toàn ở repository thử nghiệm.

### 7.1. Cây thư mục

```text
maven-upgrade-review-lab/
├── pom.xml
├── api/
│   ├── pom.xml
│   └── src/main/java/dev/example/upgrade/ApiMarker.java
├── app/
│   ├── pom.xml
│   ├── src/main/java/dev/example/upgrade/AppMain.java
│   ├── src/main/resources/review.properties
│   └── src/test/java/dev/example/upgrade/AppMainTest.java
└── report/
    └── pom.xml
```

Cấu trúc này dùng **POM model 4.0.0** để test trên Maven 3 và Maven 4. Không tự chuyển sang `<subprojects>` trong lúc vẫn chạy Maven 3.

### 7.2. Root pom.xml đầy đủ

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.example</groupId>
    <artifactId>maven-upgrade-review-lab</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>pom</packaging>
    <name>Maven Upgrade Review Lab</name>

    <modules>
        <module>api</module>
        <module>app</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <demo.mode>base</demo.mode>
    </properties>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.14.0</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-resources-plugin</artifactId>
                    <version>3.3.1</version>
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
                    <version>3.2.0</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-deploy-plugin</artifactId>
                    <version>3.2.0</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>

    <profiles>
        <profile>
            <id>ci-strict</id>
            <properties>
                <demo.mode>strict</demo.mode>
            </properties>
        </profile>
        <profile>
            <id>with-report</id>
            <modules>
                <module>report</module>
            </modules>
        </profile>
    </profiles>
</project>
```

Các điểm chủ đích:
- Root có `pom` packaging, vừa làm aggregator vừa là parent.
- Hai modules `api` và `app` luôn có mặt; `report` chỉ được collect khi `with-report` active.
- `ci-strict` **không** tự thêm module; nó đổi property `demo.mode` từ `base` sang `strict`.
- Giá trị cơ sở nằm trong `properties` **ngoài** profile, nên không biến mất do `activeByDefault`.
- Versions Compiler/Resources/Surefire/JAR được pin, giảm khác biệt do Super POM giữa Maven versions.
- Install/Deploy Plugins **3.2.0** được pin: trong lab, defaults của hai cờ at-end theo tài liệu 3.x là false trừ khi đưa flag/config tường minh.
- Dùng `pluginManagement` để quản trị versions của default lifecycle plugins; nó không tự thêm một arbitrary goal vào lifecycle.
- Không có `distributionManagement` trỏ tới production. Thực nghiệm deploy sẽ dùng `altDeploymentRepository` hướng tới folder riêng.
- `1.0.0-SNAPSHOT` là version lab; không dùng như ví dụ phát hành immutable release thật.

### 7.3. api/pom.xml đầy đủ

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>dev.example</groupId>
        <artifactId>maven-upgrade-review-lab</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>api</artifactId>
    <packaging>jar</packaging>
</project>
```

`api` không có external dependencies. Module được build trước app do app khai dependency vào api, không phải chỉ do nó đứng trước trong `<modules>`.

### 7.4. api/src/main/java/dev/example/upgrade/ApiMarker.java

```java
package dev.example.upgrade;

public final class ApiMarker {

    private ApiMarker() {
    }

    public static int value() {
        return 42;
    }
}
```

Đây là class Java 17 hợp lệ, dùng để tạo một dependency edge thật trong reactor. Không có network, random hay dependency ngoài JDK.

### 7.5. app/pom.xml đầy đủ

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>dev.example</groupId>
        <artifactId>maven-upgrade-review-lab</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>dev.example</groupId>
            <artifactId>api</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <resources>
            <resource>
                <directory>src/main/resources</directory>
                <filtering>true</filtering>
            </resource>
        </resources>
    </build>
</project>
```

`app` phụ thuộc `api` cùng GAV version; Maven reactor có dependency edge thật. JUnit chỉ ở scope test. Resource filtering được bật để nội dung `review.properties` lấy từ `demo.mode`, minh họa profile activation làm output thay đổi.

### 7.6. app/src/main/resources/review.properties

```properties
demo.mode=${demo.mode}
```

Maven Resources Plugin sẽ filter property này trong phase `process-resources`. Không dùng `System.getenv()` để đo mode: goal là thử profile/effective POM, không thử environment variables. Khi profile không active, resource chứa `demo.mode=base`; khi active, chứa `demo.mode=strict`.

### 7.7. app/src/main/java/dev/example/upgrade/AppMain.java

```java
package dev.example.upgrade;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public final class AppMain {

    private AppMain() {
    }

    public static String mode() {
        try (InputStream input =
                     AppMain.class.getClassLoader()
                             .getResourceAsStream("review.properties")) {
            if (input == null) {
                throw new IllegalStateException(
                        "Missing review.properties");
            }
            Properties properties = new Properties();
            properties.load(
                    new InputStreamReader(input, StandardCharsets.UTF_8));

            String mode = properties.getProperty("demo.mode");
            if (mode == null || mode.isBlank()) {
                throw new IllegalStateException(
                        "Missing demo.mode");
            }
            return mode.strip();
        } catch (IOException exception) {
            throw new UncheckedIOException(exception);
        }
    }

    public static String message() {
        return "value=" + ApiMarker.value() + ";mode=" + mode();
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

Code chỉ phụ thuộc Java 17 và class `ApiMarker`. Resource được đọc từ classpath; nếu filtering/config sai, method sẽ thấy một giá trị khác/missing. `Properties.load(Reader)` với UTF-8 cho khả năng xử lý Unicode rõ ràng.

### 7.8. app/src/test/java/dev/example/upgrade/AppMainTest.java

```java
package dev.example.upgrade;

import java.util.Set;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

final class AppMainTest {

    @Test
    void apiValueStaysStable() {
        assertEquals(42, ApiMarker.value());
    }

    @Test
    void recognizedModeFromResource() {
        assertTrue(Set.of("base", "strict").contains(AppMain.mode()));
    }

    @Test
    void messageCombinesApiAndProfile() {
        assertEquals(
                "value=42;mode=" + AppMain.mode(),
                AppMain.message());
    }
}
```

Ba tests bảo đảm API stable, resource được filter thành một mode được hỗ trợ, và application nối đúng thông tin. Test chấp nhận cả `base` và `strict` **có chủ đích** vì bài sẽ chuyển profile để so outputs. Với CI production, thêm assertion về mode kỳ vọng từ release policy để không chấp nhận sai profile một cách vô ý.

### 7.9. report/pom.xml đầy đủ

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>dev.example</groupId>
        <artifactId>maven-upgrade-review-lab</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>report</artifactId>
    <packaging>pom</packaging>
</project>
```

`report` không khai Java source hoặc test. Mục đích là chứng minh profile có thể thay tập project được reactor collect. Module này vẫn có artifact POM, nên `install`/`deploy` trên toàn reactor có thể ảnh hưởng nó; không coi module “không có code” là “không được publish”.

## 8. Chạy lab và xác nhận stdout

### 8.1. Build không profile, không install

Từ root `maven-upgrade-review-lab`:

```bash
mvn -version
mvn -B -ntp clean verify
```

Kỳ vọng Maven build các project root, api và app. Trong app, Surefire chạy 3 tests:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Đây là **tóm tắt log**, không phải toàn bộ console output. Root và api không có JUnit tests, nên không được cộng 3 cho mỗi module.

Trên Linux/macOS, chạy:

```bash
java -cp "api/target/classes:app/target/classes" dev.example.upgrade.AppMain
```

**Stdout chính xác:**

```text
value=42;mode=base
```

Trên Windows PowerShell/CMD, classpath separator là dấu chấm phẩy:

```powershell
java -cp "api/target/classes;app/target/classes" dev.example.upgrade.AppMain
```

Stdout vẫn là `value=42;mode=base`.

### 8.2. Bật profile ci-strict

```bash
mvn -B -ntp -Pci-strict clean verify
```

Sau build, cùng lệnh `java -cp` cho OS của bạn sẽ in:

```text
value=42;mode=strict
```

Khi không bật profile nữa và chạy lại `clean verify`, output trở về `base`. Đây là bằng chứng **profile activation ảnh hưởng artifact/resource output**, dù Java source file không đổi.

Nếu output không đổi:
- kiểm `help:active-profiles` và effective POM;
- kiểm `app/target/classes/review.properties`;
- đảm bảo app đang dùng POM parent đúng;
- xác minh lệnh `java` dùng đúng `target/classes` được build mới, không lấy JAR stale trong `~/.m2`;
- kiểm CI settings có profile khác override property không.

### 8.3. Bật profile with-report

```bash
mvn -B -ntp -Pwith-report clean verify
```

Maven Reactor Summary lúc này phải có thêm project `report` (packaging pom), ngoài root/api/app. Số projects trong summary **có thêm một**, dù report không cần compile Java.

Nếu chỉ chạy không profile, module report **không nằm trong tập `<modules>` active** của root. Đừng nhầm việc directory `report/` tồn tại với việc Maven mặc định build nó ở POM model 4.0.0.

### 8.4. Bật đồng thời hai profiles

```bash
mvn -B -ntp -Pci-strict,with-report clean verify
```

Kỳ vọng:
- Tập modules gồm root, api, app, report.
- Application output là `value=42;mode=strict`.
- Test module app chạy đúng 3 tests.
- Không có local install hoặc remote deploy do chỉ chạy `verify`.

Đó là một test quan trọng: **mỗi profile có thể tác động phần khác nhau của build model**, và interaction của profiles phải được kiểm thay vì so một flag duy nhất.

## 9. Thử chọn module bằng reactor flags

### 9.1. Chỉ app nhưng vẫn build upstream

```bash
mvn -B -ntp -pl :app -am clean verify
```

Ở root, `-pl :app` chọn app theo artifactId; `-am` kéo các reactor dependencies cần thiết, đặc biệt api. Parent/aggregator có thể được xét theo reactor graph thực. Đây là cách bền vững hơn việc chỉ build `app` rồi trông chờ một JAR api cũ trong local repo.

### 9.2. API thay đổi, kiểm downstream app

```bash
mvn -B -ntp -pl :api -amd verify
```

`-amd` chọn api và những reactor projects phụ thuộc nó, nên app được xét. Với một codebase lớn, đây là cách kiểm tác động của API change mà không cần build mọi module không liên quan.

### 9.3. Resume trong Maven 3

Sau một failure ở app:

```bash
mvn -B -ntp -rf :app verify
```

Có thể fail vì api chưa được install và không có trong resume reactor selection; trong lần build trước api đã pass nhưng `verify` không ghi JAR lên local repository. Đừng “fix” ngay bằng `mvn install` trên tất cả modules; có thể dùng:

```bash
mvn -B -ntp -pl :app -am verify
```

Lệnh có upstream trong cùng reactor, giảm phụ thuộc local artifacts cũ.

### 9.4. Resume trong Maven 4

Maven 4 bổ sung:

```bash
mvn -B -ntp --resume verify
```

hoặc:

```bash
mvn -B -ntp -r verify
```

trong context **một reactor đã fail và có state phù hợp**. Đây là minh họa Maven 4 CLI, **không phải lệnh đầu tiên để chạy trong checkout mới chưa có failed build**. Behavior có thể thay theo builder và Maven version; test trên môi trường đang triển khai.

**Không đồng nhất `-r` với `-rf`**. `--resume-from :app` định vị module cụ thể, còn `--resume` có thể dùng thông tin build thất bại trước đó.

### 9.5. Non-recursive không chứng minh toàn reactor

```bash
mvn -B -ntp -N validate
```

chỉ kiểm root project theo chế độ non-recursive. Nếu dùng nó như migration gate, bạn chưa kiểm Java modules, test resources, active profile modules hoặc install/deploy behavior trên toàn reactor.

## 10. Kiểm hành vi installAtEnd với repository riêng

### 10.1. Vì sao phải cách ly local repository?

`mvn install` ghi artifacts vào local repo. Để so `installAtEnd=false` với `true` mà không làm bẩn `~/.m2/repository` người dùng, hãy dùng local repository riêng trong folder lab. Nó có thể tải lại dependencies/plugins, vì vậy lần đầu cần network.

Linux/macOS, từ root:

```bash
mvn -B -ntp -Dmaven.repo.local=./.m2-install-immediate \
  -DinstallAtEnd=false clean install
```

Sau đó:

```bash
mvn -B -ntp -Dmaven.repo.local=./.m2-install-deferred \
  -DinstallAtEnd=true clean install
```

Hai lần này đều dự kiến **BUILD SUCCESS** vì project lab không có lỗi và plugin Install 3.2.0 có property `installAtEnd`. Các artifacts thường xuất hiện theo Maven repository layout:

```text
.m2-install-deferred/dev/example/maven-upgrade-review-lab/1.0.0-SNAPSHOT/...
.m2-install-deferred/dev/example/api/1.0.0-SNAPSHOT/...
.m2-install-deferred/dev/example/app/1.0.0-SNAPSHOT/...
```

Snapshot filenames/metadata cụ thể do Maven plugin/version quyết định. Kiểm sự tồn tại các artifact POM/JAR, **không hard-code timestamped snapshot filename**.

### 10.2. Tạo một lỗi test có kiểm soát trong sandbox

Nếu muốn quan sát sự khác nhau khi app fail:
1. Trên **bản copy của demo** (không làm trên dự án thật), sửa `AppMainTest.apiValueStaysStable()` để tạm thời `assertEquals(41, ApiMarker.value())`. Đây là một test cố ý fail.
2. Dùng **hai local repositories cách ly, chưa có artifacts của demo**.
3. Chạy `mvn ... -DinstallAtEnd=false clean install` và ghi lại những artifacts đã được install trước khi app test fail.
4. Chạy `mvn ... -DinstallAtEnd=true clean install` với một local repo khác.
5. Kiểm folder `dev/example` trong mỗi repo để xem module nào có artifact.
6. Hoàn nguyên assertion về **42**, chạy `verify` và xác nhận build xanh.

**Kỳ vọng logic:**
- Immediate install có thể đã cài parent/api khi app fail, dù reactor build không thành công.
- Deferred install giảm khả năng để lại artifacts mới trước lỗi, vì requests đang chờ tới thời điểm xử lý cuối.
- Chỉ khẳng định những gì log và repository state **thực tế** cho thấy; khác biệt có thể phụ thuộc plugin version, execution bindings và module ordering.

Không coi `installAtEnd=true` là một transaction database. Nó điều khiển thời điểm Maven Install Plugin ghi local artifacts, không rollback mọi external side effect trong build.

### 10.3. Windows PowerShell

Một lệnh viết trên một dòng (tránh backslash continuation của Bash):

```powershell
mvn -B -ntp "-Dmaven.repo.local=./.m2-install-deferred" "-DinstallAtEnd=true" clean install
```

Kiểm repository trong project:

```powershell
Get-ChildItem -Path .m2-install-deferred/dev/example -Recurse -File
```

Không chạy `Remove-Item -Recurse` trên `$HOME/.m2` để tái tạo môi trường; dùng một thư mục demo rõ tên là đủ.

## 11. Kiểm deployAtEnd an toàn bằng file:// repository

### 11.1. Tuyệt đối không dùng registry thật để thử lỗi

Một lần `mvn deploy` không được sandbox có thể publish artifact thật, gây version conflict hoặc để lại partial release. Trong bài chỉ dùng repository `file://` riêng trên máy local. **Không cấu hình secrets hoặc distributionManagement production trong project lab.**

Maven Deploy Plugin 3.2.0 hỗ trợ property `altDeploymentRepository` với format:

```text
repositoryId::repositoryUrl
```

Không dùng format lịch sử 2.x `id::layout::url`, vì Deploy Plugin 3.x dùng format `id::url`.

### 11.2. Linux/macOS — preview repository

Từ root lab, tạo folder không dùng cho artifact sản xuất:

```bash
mkdir -p /tmp/maven-upgrade-preview-repo
mvn -B -ntp -DaltDeploymentRepository=preview::file:///tmp/maven-upgrade-preview-repo \
  -DdeployAtEnd=true clean deploy
```

Đây là **demo local** dùng Maven Deploy Plugin đã pin trong root POM. Nó có thể tạo POM/JAR/snapshot metadata dưới folder preview, nhưng không upload ra Internet. `file:///tmp/...` là URI absolute cho Unix. Không copy nguyên URL này vào Windows hoặc production.

Sau build:

```bash
find /tmp/maven-upgrade-preview-repo -type f
```

Kỳ vọng có artifacts thuộc `dev/example` cho những modules tham gia reactor. Vì version là `SNAPSHOT`, Deploy Plugin có thể dùng timestamped snapshot metadata. **Không đưa ra đường dẫn filename chính xác khi Maven/metadata thay đổi.**

### 11.3. Windows PowerShell — preview repository

Tạo trước folder riêng có quyền ghi:

```powershell
New-Item -ItemType Directory -Force -Path "C:\Temp\maven-upgrade-preview-repo"
mvn -B -ntp '-DaltDeploymentRepository=preview::file:///C:/Temp/maven-upgrade-preview-repo' '-DdeployAtEnd=true' clean deploy
```

Dạng URI sử dụng dấu `/` và ổ `C:`. Không đặt spaces trong URL mà chưa encode. Sau khi chạy:

```powershell
Get-ChildItem -Path "C:\Temp\maven-upgrade-preview-repo" -Recurse -File
```

Nếu transport `file://` không được hỗ trợ do runtime/custom extensions/permissions, đó là lỗi sandbox transport — **không chuyển sang Nexus/Maven Central production như workaround**.

### 11.4. So false với true trong sandbox

Để so semantics trên Maven 3/plugin 3.x:

```bash
mvn -B -ntp -DaltDeploymentRepository=preview::file:///tmp/maven-upgrade-immediate \
  -DdeployAtEnd=false clean deploy
```

và một run riêng dùng folder khác:

```bash
mvn -B -ntp -DaltDeploymentRepository=preview::file:///tmp/maven-upgrade-deferred \
  -DdeployAtEnd=true clean deploy
```

Với cả hai run thành công, artifacts cuối cùng có thể tương tự. **Khác biệt chính là thời điểm upload khi có lỗi ở module sau**. Để kiểm, có thể tạo lỗi JUnit có chủ đích như mục 10.2 trên **bản demo** rồi so folder contents/logs; sau đó khôi phục code và chạy `verify`.

### 11.5. Nhớ giới hạn at-end

Ngay cả khi `deployAtEnd=true`, nếu remote batch gặp lỗi giữa các uploads, một phần artifacts vẫn có thể tồn tại. Với production registry:
- kiểm staging/close/release state;
- xác nhận GAV nào đã hiện hữu;
- không auto-retry một immutable release GAV;
- có quy trình publish version mới/rollback promotion theo repository policy;
- lưu build provenance và approved tag.

**Deferred deploy giảm nguy cơ xuất bản nửa chừng trước lỗi reactor, không biến toàn bộ deployment thành atomic transaction.**

## 12. Maven 4: rà soát những thay đổi liên quan nhưng không nên gộp tùy tiện

### 12.1. Cấu hình model bị Maven 4 kiểm nghiêm

Maven 3.9 có thể log warnings về duplicate plugin declarations. Maven 4 có thể fail với cấu hình không hợp lệ như cùng `groupId:artifactId` plugin bị khai trùng.

Trước khi nâng:
- dọn warnings Maven 3;
- ghim versions của plugins;
- so effective POM;
- chỉ dùng `--fail-on-severity WARN` trong Maven 4 khi team sẵn sàng xử lý warnings thành failures.

### 12.2. Directory properties bị thay

Hướng dẫn migration nêu các properties cũ như `executionRootDirectory` và `multiModuleProjectDirectory` bị deprecated hoặc removed. Maven 4 có public properties mới `project.rootDirectory`, `session.topDirectory` và `session.rootDirectory`.

Khi scripts/plugins/profiles sử dụng path root:
- tìm đúng chỗ đang dùng properties cũ;
- kiểm cách Maven mới xác định root (có `.mvn` hoặc root attribute phù hợp);
- không tự thay text trong POM model 4.0.0 bằng property chỉ có Maven 4 khi vẫn muốn build bằng Maven 3;
- test từ root và thư mục con;
- kiểm `-f` và CI working directory.

### 12.3. Lifecycle phase pre-/post- thay đổi

Maven 4 có phases `before:integration-test` và `after:integration-test` thay cho cách tên `pre-integration-test`/`post-integration-test` truyền thống; có những aliases/deprecation theo version.

Nếu project bind start/stop test database/containers vào pre/post phases:
- đọc lifecycle migration docs;
- xác minh Failsafe/integration-test ordering;
- không đổi phase name giữa chừng khi còn Maven 3 support;
- có test chứng minh service setup/teardown luôn chạy theo đúng chuỗi;
- không để deployment bắt đầu trước khi integration tests/after-phase checks hoàn tất.

### 12.4. Super POM/default plugin versions

Maven 4 thay Super POM và default plugin bindings. Dự án không pin plugin versions có thể chạy compiler/resources/install/deploy khác mà người sửa chỉ nghĩ mình nâng Maven binary.

Mở:
- `mvn help:effective-pom`;
- `mvn help:describe -Dplugin=... -Dgoal=... -Ddetail`;
- build logs và reactor summary.

Pin plugin version giúp phân lập Core behavior và plugin behavior. **Không tự nâng mọi plugin lên 4.x khi vẫn muốn Maven 3 compatibility**: một số plugin major4 yêu cầu Maven 4.

### 12.5. Maven 4 model 4.1.0 không phải bước đầu tiên

Các đặc tính như root attribute, `<subprojects>`, auto versioning và optional profile declarations nằm trong giai đoạn modernize, **sau** khi compat build đã chạy tốt. Nếu bật 4.1.0:
- tạo branch migration riêng;
- không quay lại gọi Maven 3 cho source POM;
- kiểm published Consumer POM tương thích với consumers Maven 3 theo cơ chế Maven 4;
- rà soát auto-discovery: project con nào xuất hiện thêm?
- kiểm root detection từ subfolder;
- so dependencies, BOM/parent coordinates và reactor output.

## 13. Kiểm CI/CD và quy trình phát hành

### 13.1. PR pipeline không nên install/deploy

Một PR kiểm code chưa review nên chạy:

```bash
mvn -B -ntp clean verify
```

kèm `-P`/`-pl` tương ứng với matrix của dự án. Không cấp Maven remote deploy tokens cho PR, không dùng `-DskipTests` làm gate mặc định. Profiles mang tính bảo mật phải tồn tại thật; Maven 4 unknown-profile fail có thể giúp bắt lỗi cấu hình nhưng không thay mọi security checks.

### 13.2. Release pipeline tách khỏi verification

Một trình tự phù hợp:
1. Checkout protected tag/commit đã duyệt.
2. Dùng Maven Wrapper/JDK/plugin versions đã kiểm.
3. Xác minh active profiles và reactor module list như baseline release.
4. Chạy đầy đủ unit/integration tests (`verify` hoặc quality gates tương đương).
5. Kiểm versions của parent/children và artifact metadata.
6. Chọn chế độ publish theo **plugin version và at-end policy được duyệt**.
7. Sử dụng staging repository hoặc registry policy hỗ trợ validation/promotion.
8. Chỉ publish với credentials scoped đúng registry/job; có provenance/chữ ký theo policy.
9. Ghi chính xác modules/artifacts đã xuất bản và xử lý partial publication nếu có lỗi.

### 13.3. Vì sao “mvn deploy” trong CI có thể nguy hiểm hơn “mvn verify”?

`deploy` có side effects vượt ngoài workspace. Một plugin version change hoặc profile change có thể:
- thêm module report chưa từng xuất bản;
- bỏ module app vì activation condition không còn đúng;
- publish snapshot thay release;
- thay repository ID/URL qua `distributionManagement`/profiles;
- chạy một deploy goal ngoài ý muốn với `deployAtEnd=false`;
- vô tình truyền token vào PR pipeline.

**Không dựa vào một dòng BUILD SUCCESS để chứng minh artifact set phát hành đúng.** Kiểm inventory của remote registry/staging, GAV và checksums sau publish.

### 13.4. Phạm vi lệnh chính xác

- `verify` kiểm artifact theo Maven lifecycle.
- `install` ghi local repo và có thể che lỗi reactor/resume.
- `deploy` ghi remote repo hoặc `file://` target.
- `-P` chọn profiles, có thể đổi dependencies/plugins/modules/repo.
- `-pl/-am/-amd` chọn project graph.
- `-rf/-r` liên quan resume, không có nghĩa dependency đã được cài.
- `-T`/concurrent builder có thể đổi interleaving của logs/goals.
- `-s settings.xml` có thể đổi mirrors/repositories/credentials.
- `-Dmaven.repo.local` đổi local repository, hữu ích để kiểm pollution.

Khi audit, lưu **cả command line** chứ không chỉ `mvn -version`.

## 14. Bảng triệu chứng và nguyên nhân

| Triệu chứng sau nâng cấp | Nguyên nhân khả dĩ | Kiểm/khắc phục |
| --- | --- | --- |
| Maven 4 fail `-Plegacy` | Profile không tồn tại | Sửa tên; nếu thật optional dùng `-P?legacy` |
| Profile `activeByDefault` biến mất | Profile khác cùng POM được active | Đưa base properties ra ngoài profile |
| CI và local chọn repo khác | Settings profiles/mirrors/JDK khác | So effective settings/active profiles |
| Output vẫn base dù `-Pci-strict` | Profile không active, resource filtering sai | active-profiles, effective POM, target resource |
| Bật profile nhưng module report mất | with-report không active hoặc selector filter | So reactor summary, `-P` và `-pl` |
| Build thiếu app dù `verify` pass | Chỉ chọn `-pl :api`, không `-amd` | Kiểm reactor selection |
| App không resolve api khi `-pl :app` | Thiếu upstream build hoặc local artifact | Thử `-pl :app -am verify` |
| Maven 3 `-rf :app` fail lần hai | Upstream artifact chưa install | Dùng `-am` hoặc build lại upstream |
| Maven 4 `-r` không làm gì | Chưa có failed reactor state | Tạo failure scenario và dùng đúng builder |
| Module thứ tự thay | Dependency edges/profile modules khác | So actual POM dependencies và reactor logs |
| Maven 4 từ thư mục con build khác | Improved subproject collection/root detection | Kiểm root, `-f`, active model |
| Maven 4 báo duplicate plugin | Cấu hình POM từng warning | Hợp nhất plugin declarations |
| Maven 4 lỗi old directory property | Property deprecated/removed | Dùng public root props khi drop Maven 3 |
| Integration tests không chạy đúng phase | pre/post lifecycle migration | Kiểm bindings và logs |
| Install không ghi JAR ngay sau api | `installAtEnd=true` | Kiểm plugin defaults/flags và end batch |
| Local repo có artifact dù build fail | `installAtEnd=false` hoặc install trước failure | Isolated repo và log timing |
| Remote có chỉ một số modules | `deployAtEnd=false` hoặc partial batch | Kiểm registry state; staging/provenance |
| deployAtEnd=true nhưng vẫn partial | Batch không atomic, trailing modules | Không tuyên bố rollback toàn bộ |
| Maven 4 & plugin3 vẫn install per-module | Plugin 3.x default false/pinned | Kiểm version/parameter thực |
| Publish chậm/timeout sau nâng | More modules, new plugin transport, repo | Kiểm count/URL/timeout/runtime |
| Install plugin báo incomplete artifact | packaging không tạo main artifact | Sửa packaging/attach artifact hợp lệ |
| Deploy 401/403 | Credential/server ID/repository ACL | Kiểm settings và distributionManagement |
| Deploy 409 | GAV tồn tại hoặc immutable policy | Không retry mù; kiểm remote state |
| Deploy format sai | `id::layout::url` còn từ plugin 2.x | Dùng `id::url` với plugin 3/4 |
| Build pass với `-fn` dù module fail | Fail-never exit policy | Không dùng cho release gate |
| Maven4 dùng plugin version lạ | Super POM/defaults mới | Pin plugin versions |
| File repository không thấy JAR | Deploy chưa chạy, URI/path sai | Kiểm file:// URL và plugin logs |
| Resume sử dụng JAR cũ | Local repo polluted bởi install trước | Dùng isolated repo và `-am` |
| SNAPSHOT metadata khác giữa modules | Version/metadata policies khác | Kiểm effective versions, timestamp/registry |
| Maven4 `-b concurrent` lộ race | Plugin goals không thread-safe | Disable concurrent, sửa plugin state |

## 15. Quy trình điều tra theo thứ tự

**Bước 1 — Giữ nguyên evidence:** Lưu logs, Maven/JDK/plugin versions, effective profiles, reactor summary, command line và repository state. Không xóa cache hay overwrite release artifact.

**Bước 2 — So một trục tại một thời điểm:** Giữ POM model 4.0.0 và plugin3.x khi test Maven runtime; sau đó mới nâng plugin; cuối cùng mới xem POM 4.1.0.

**Bước 3 — Kiểm profiles:** Dùng `help:active-profiles` và `help:effective-pom`. Kiểm profile missing, activeByDefault, root/child/settings, OS/JDK/file conditions.

**Bước 4 — Kiểm reactor:** So tập modules với/không với `with-report`, `-pl :app -am`, `-pl :api -amd`; xem changed selection và ordering.

**Bước 5 — Kiểm lifecycle:** Quan sát `verify/install/deploy` goals và thời điểm install/deploy requests được flush. Kiểm explicit config vs plugin defaults.

**Bước 6 — Kiểm local repository:** Dùng `-Dmaven.repo.local=./.m2-sandbox` trong lab, kiểm xem artifacts có xuất hiện trước khi toàn reactor pass không.

**Bước 7 — Kiểm remote giả lập:** Chạy `deploy` tới repository `file://`, không production; so immediate/deferred bằng các folders riêng.

**Bước 8 — Kiểm release safety:** Xem profiles/repository policies, tag approvals, artifacts GAV, attached artifacts, checksums và staging status; bảo đảm partial failure có runbook.

**Bước 9 — Ghi regression tests:** Viết CI matrix để lần nâng Maven sau tiếp tục so active profiles, reactor inventory và at-end behavior.

## 16. Bài tập thực hành

**1.** Vì sao `mvn -version` chưa đủ để tái hiện bug sau nâng cấp? Vì settings, profiles, plugin versions, JDK, POM model và flags còn ảnh hưởng build.

**2.** Maven 4 chạy `-Punknown` không tìm thấy profile thì sao? **Fail**; nếu thực sự optional có thể dùng `-P?unknown`.

**3.** Dùng `-P?release-sign` chỉ để bỏ qua profile thiếu có an toàn không? **Không**, release signing là điều kiện bắt buộc; phải fail nếu thiếu.

**4.** Một profile activeByDefault bị mất khi kích hoạt ci-strict cùng POM? Đây là **hành vi có chủ đích**; đưa values cơ sở ra ngoài profile.

**5.** Profiles trong parent được child thừa kế nguyên object không? **Không**; effects của profiles đã active có thể được kế thừa, implicit activation có tính cục bộ.

**6.** Bật `with-report` làm thay điều gì? **Tập modules của reactor**, thêm report packaging pom.

**7.** Bật `ci-strict` làm thay điều gì? **Property/resource output**, từ mode base sang strict.

**8.** Khi không có profile, stdout AppMain là gì? **value=42;mode=base**.

**9.** Khi có ci-strict, stdout AppMain là gì? **value=42;mode=strict**.

**10.** `-pl :app -am` khác `-pl :app`? Thêm upstream reactor dependencies để app có thể build cùng api.

**11.** `-pl :api -amd` thích hợp khi nào? Khi cần kiểm downstream modules bị ảnh hưởng bởi API change.

**12.** Tại sao Maven 3 `-rf :app` có thể fail dù api vừa pass? Vì api không nằm trong resumed reactor và chưa được install vào local repo.

**13.** Maven 4 `-r` có giống `-rf :app` không? **Không**; một cái resume previous failure state, cái kia resume từ module chỉ định.

**14.** Vì sao `mvn verify` thường nên là default CI build? Vì không ghi artifacts vào local/remote repositories và reactor vẫn quản lý sibling modules.

**15.** Install Plugin 3.2.0 có `installAtEnd` mặc định gì? **false** nếu không override.

**16.** Deploy Plugin 3.2.0 có `deployAtEnd` mặc định gì? **false** nếu không override.

**17.** Theo Maven4 migration guide, hai defaults đó hướng tới gì? **true** trong các plugin versions tương ứng Maven 4.

**18.** Nếu đang dùng Maven4 nhưng project vẫn pin Install Plugin 3.2.0, có chắc at-end true không? **Không**; phải kiểm plugin default/config thực tế.

**19.** `deployAtEnd=true` có bảo đảm atomic publish toàn bộ reactor không? **Không**; batch có thể partial, một số modules có thể chạy sau flush.

**20.** Vì sao không thử `mvn deploy` lên Maven Central production để kiểm lỗi? Vì upload có side effect khó/không thể hoàn tác.

**21.** Format `altDeploymentRepository` hiện tại là gì? **id::url** với Deploy Plugin 3/4, không dùng layout ở giữa.

**22.** Vì sao `-fn` nguy hiểm trong release CI? Có thể trả exit code 0 dù một module fail.

**23.** Model `4.1.0` có dùng được để build lại với Maven 3 không? **Không**; nên migrate sau compatibility phase.

**24.** Chỉ đổi `<modules>` thành `<subprojects>` trong POM model 4.0.0 có đúng không? **Không**; `<subprojects>` là feature model 4.1.0.

**25.** Vì sao điều kiện `-Pwith-report` có thể làm phát hành thêm artifact POM? Vì module report packaging pom có lifecycle install/deploy.

**26.** Khi Maven 4 fail vì duplicate plugin declaration, có nên tắt validation không? **Không**; sửa POM, hợp nhất plugin declarations.

**27.** Vì sao việc nâng Maven 4 có thể thay các plugin defaults? Vì Super POM/core bindings/plugin versions có thể khác; cần pin versions.

**28.** Điều gì phải được lưu sau thử deploy file://? Tên GAV, artifact paths, trạng thái uploads, thời điểm flush và các lỗi/partial.

## 17. Checklist quyết định go/no-go khi nâng Maven

### Trước migration

- [ ] Đã chốt Maven 3.9.x/JDK17 baseline có log và checksum.
- [ ] Maven Wrapper/CI image/JAVA_HOME đã được kiểm.
- [ ] Các Maven plugins quan trọng có versions tường minh.
- [ ] Không còn duplicate plugins/malformed POM warnings quan trọng.
- [ ] Có danh sách profiles mặc định, CI, release và settings profiles.
- [ ] Đã ghi lại active profiles và effective POM của từng module.
- [ ] Đã lưu reactor summary và project selections với mọi `-P` quan trọng.
- [ ] Có snapshots của local/remote artifact states cần audit, không chứa secrets.
- [ ] `verify` và unit/integration tests chạy đầy đủ trước publish.

### Profiles và reactor

- [ ] Không có `-P` trỏ profile thiếu một cách vô ý.
- [ ] Optional `-P?x` chỉ dùng cho tùy chọn thật, không che gate bảo mật.
- [ ] Không đặt mọi base config trong `activeByDefault` có thể bị tắt.
- [ ] Settings/OS/JDK/file activation được kiểm ở CI và developers.
- [ ] Profile modules xuất hiện/biến mất đúng kỳ vọng.
- [ ] `-pl/-am/-amd` chọn đủ upstream/downstream modules.
- [ ] Resume commands đã được thử khi module sau fail.
- [ ] Không dùng `-N` để khẳng định whole-reactor QA.
- [ ] Không dùng `-fn` làm condition publish.
- [ ] Nếu dùng Maven4 concurrent builder, plugins thread safety đã được kiểm.

### Install/deploy

- [ ] Phân biệt chính xác `mvn verify`, `install` và `deploy`.
- [ ] Install/Deploy Plugin versions thực tế đã được xác nhận.
- [ ] `installAtEnd`/`deployAtEnd` được chốt explicit hoặc default theo đúng plugin version.
- [ ] Đã so local repo immediate vs deferred bằng isolated caches.
- [ ] Đã thử file:// deploy và failure scenario trong sandbox.
- [ ] Không gọi `deployAtEnd=true` là atomic transaction.
- [ ] Những modules POM-only/attachments cũng được tính vào artifact inventory.
- [ ] Publisher secrets không tồn tại trong PR pipeline.
- [ ] Repository ID, URL, settings server ID và ACL đã được đối chiếu.
- [ ] Có staging/promotion/partial-deploy recovery; không retry immutable GAV mù.
- [ ] Release job xác minh protected source/tag, versions và test gates.
- [ ] Không đưa Maven 4-only POM 4.1.0 vào giai đoạn Maven3 compatibility.

### Kết quả

- [ ] Cùng source/flags có active profiles và reactor inventory như kỳ vọng.
- [ ] Java output base/strict trong lab khớp hai cases.
- [ ] Test count là 3 tại module app; tests không bị skip.
- [ ] Artifacts từ install/deploy có GAV và scope module đúng.
- [ ] Không publish trước khi toàn bộ release gates đã pass.
- [ ] Rủi ro breaking change đã có owner và rollback path.
- [ ] CI matrix dùng đúng Maven binary mỗi case.
- [ ] Plugin/CLI/model migration được tách thành các commit nhỏ.
- [ ] Có báo cáo evidence để review/go-no-go trước production upgrade.

## 18. Kết luận

Khi nâng Maven, ba vùng dễ tạo khác biệt dây chuyền là **profiles**, **reactor** và **side effects của install/deploy**. Profiles quyết định effective POM, dependencies và đôi khi cả tập modules. Reactor quyết định dự án nào được build, thứ tự và khả năng resume. Install/Deploy Plugins quyết định khi nào artifact ra khỏi workspace sang local hoặc remote repositories.

Để tránh lỗi khó truy vết, hãy **chốt baseline trên Maven 3.9**, thử Maven 4 với POM 4.0.0 và plugin versions đã pin, kiểm từng profile/module/phase, rồi mới nâng plugins hoặc model 4.1.0. Dùng `mvn verify` làm default build, kiểm `installAtEnd`/`deployAtEnd` theo **plugin version**, và không dùng flag at-end như một đảm bảo atomic publishing. Mọi thay đổi phải được chứng minh bằng logs, reactor summary, effective POM, artifact inventory và sandbox deploy trước khi áp dụng cho release thật.

### Tài liệu chính thức

- [Apache Maven — Starting with Maven 4: migration guide](https://maven.apache.org/guides/mini/guide-migration-to-mvn4)
- [Apache Maven — What's new in Maven 4?](https://maven.apache.org/whatsnewinmaven4.html)
- [Apache Maven — Introduction to Build Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html)
- [Apache Maven — Guide to Working with Multiple Modules (Maven 3)](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Apache Maven — Guide to Working with Multiple Subprojects (Maven 4)](https://maven.apache.org/guides/mini/guide-multiple-subprojects-4.html)
- [Apache Maven — Install Plugin 3.2.0 install:install](https://maven.apache.org/plugins/maven-install-plugin/install-mojo.html)
- [Apache Maven — Deploy Plugin 3.2.0 deploy:deploy](https://maven.apache.org/plugins/maven-deploy-plugin/deploy-mojo.html)
- [Apache Maven — Install Plugin 4.x install:install](https://maven.apache.org/plugins/maven-install-plugin-4.x/install-mojo.html)
- [Apache Maven — Deploy Plugin 4.x deploy:deploy](https://maven.apache.org/plugins/maven-deploy-plugin-4.x/deploy-mojo.html)
- [Apache Maven — Introduction to Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Apache Maven — Guide to Configuring Plug-ins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)

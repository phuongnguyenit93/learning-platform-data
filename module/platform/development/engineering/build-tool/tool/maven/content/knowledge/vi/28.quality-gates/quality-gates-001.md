# Maven Enforcer Plugin và xác định điều kiện build được chấp nhận

## 1. Vì sao dự án Maven cần một cổng chất lượng ngay từ đầu?

Một dự án có thể chạy tốt trên laptop nhưng thất bại hoặc tạo ra artifact khác trên CI vì hai lập trình viên sử dụng phiên bản Maven/JDK khác nhau, một dependency bị cấm xuất hiện trong cây phụ thuộc, profile phát hành chưa được bật hoặc một tệp chính sách thiết yếu không tồn tại. Những khác biệt này thường không được Java compiler phát hiện: code vẫn biên dịch, nhưng điều kiện để **được phép build** chưa đạt.

**Maven Enforcer Plugin** biến một số điều kiện thành **quy tắc kiểm tra tự động (rules)**. Khi một rule ở mức lỗi không đạt, Maven kết thúc build với trạng thái thất bại và chỉ ra chính sách bị vi phạm. Ví dụ:

- Chỉ chấp nhận Maven **3.9.x**, không tự động chấp nhận Maven 4 khi chưa kiểm thử.
- Yêu cầu **JDK chạy Maven** là Java 17 trở lên.
- Chỉ chấp nhận `quality.channel` có giá trị `dev`, `ci` hoặc `release`.
- Yêu cầu có tệp `policy/BUILD-POLICY.md` trong repository.
- Không cho phép artifact `commons-codec:commons-codec` trong dependency tree của demo (đây chỉ là **một chính sách minh họa**, không phải khẳng định thư viện đó có lỗ hổng).
- Khi xây phiên bản phát hành thật, có thể thêm điều kiện **không dùng SNAPSHOT**.

Nhờ đặt goal `enforcer:enforce` ở phase `validate`, những điều kiện này được kiểm tra **trước các bước compile, test và package** trong vòng đời Maven thông thường.

Tuy nhiên cần hiểu một giới hạn quan trọng:

> **Enforcer quyết định các điều kiện build được chấp nhận theo những rule bạn đã cấu hình; Enforcer không chứng minh code đúng, không thay thế test/coverage/static analysis, không tự quét CVE và không tự xác nhận artifact deploy an toàn.**

Bài này dùng **Maven Enforcer Plugin 3.6.3**, Maven **3.9.x**, Java **17+**, Maven Compiler Plugin 3.13.0, Surefire Plugin 3.5.2, JAR Plugin 3.4.2 và JUnit Jupiter 5.11.4. Các ví dụ và giới hạn rule được đối chiếu với tài liệu chính thức của Enforcer 3.6.3.

### Mục tiêu học tập

Sau bài này, bạn có thể:
1. Giải thích Enforcer Plugin kiểm tra điều gì và chạy ở thời điểm nào.
2. Viết **tiêu chí chấp nhận build** đo được, thay vì một yêu cầu mơ hồ kiểu “build phải sạch”.
3. Cấu hình `requireMavenVersion`, `requireJavaVersion`, `requireProperty`, `requireFilesExist` và `bannedDependencies`.
4. Hiểu Maven version ranges, regex property, tọa độ dependency và phạm vi transitive.
5. Phân biệt `fail`, `failFast`, `level=WARN`, `skip` và `failIfNoRules`.
6. Cài đặt project Java 17/JUnit 5 hoàn chỉnh, test baseline PASS và cố ý tạo các rule violations.
7. Đánh giá `dependencyConvergence`, `requireUpperBoundDeps`, `requirePluginVersions`, `requireReleaseVersion` và `requireReleaseDeps` đúng phạm vi.
8. Đặt policy trong parent/multi-module Maven Reactor mà không vô tình bỏ kiểm tra ở module con.
9. Phối hợp Enforcer với CI, Maven Wrapper, dependency analysis, tests và quy trình release.
10. Troubleshoot khi rule fail, khi build “xanh” giả do skip, hoặc khi máy local khác CI.

## 2. Cổng chất lượng là hợp đồng có thể kiểm chứng

### 2.1. Từ mô tả sang tiêu chí có thể chấm

Yêu cầu mơ hồ:

```text
Nhóm phải sử dụng Maven và Java phù hợp.
Không được dùng dependency xấu.
Cấu hình CI phải đầy đủ.
```

Không thể tự động đánh giá chính xác vì không nêu phiên bản, tập library hoặc biến cấu hình. Thay bằng **hợp đồng build**:

| Điều kiện được chấp nhận | Cách kiểm tra bằng Enforcer | Ví dụ vi phạm |
| --- | --- | --- |
| Maven thuộc dải 3.9.x | `requireMavenVersion` | Maven 3.8.8 hoặc 4.0 |
| JDK dùng để chạy Maven từ 17 trở lên | `requireJavaVersion` | Maven chạy bằng JDK 11 |
| `quality.channel` thuộc `dev/ci/release` | `requireProperty` với regex | `-Dquality.channel=nightly` |
| `policy/BUILD-POLICY.md` tồn tại | `requireFilesExist` | File bị đổi tên hoặc chưa checkout |
| Artifact bị cấm không xuất hiện | `bannedDependencies` | Thêm `commons-codec:commons-codec` |
| Dependencies có versions nhất quán (nếu nhóm yêu cầu) | `dependencyConvergence` | Hai tuyến transitive đòi versions khác nhau |
| Không mang SNAPSHOT vào bản phát hành | `requireReleaseDeps` và `requireReleaseVersion` | Release job nhận dependency/project `-SNAPSHOT` |

Bảng là **mẫu chính sách**, không phải Maven tự suy ra các quy tắc trên. Bạn phải khai báo chúng vào POM và bảo đảm execution thực sự chạy trong CI.

### 2.2. “Được build” và “được release” không giống nhau

Có thể phân thành ba cấp:

1. **Build eligibility:** Máy dùng Maven/JDK hợp lệ, các metadata bắt buộc tồn tại, dependency policy không bị vi phạm.
2. **Code quality:** Source compile được, unit/integration tests đạt, coverage và static checks qua ngưỡng đã công bố.
3. **Release readiness:** Artifact có version, provenance, dependency/licensing/security status, approvals và deployment checks phù hợp.

Enforcer rất mạnh cho **cấp 1** và một phần ràng buộc của **cấp 3** (ví dụ cấm SNAPSHOT, ban library). Nhưng riêng `mvn validate` chỉ chứng minh những Enforcer rules ở phase này PASS; nó **không chạy compile/tests/package**. Muốn xác minh chuỗi kiểm soát sâu hơn, chạy phase như `mvn verify` cùng những plugins chất lượng tương ứng.

## 3. Enforcer vận hành trong Maven lifecycle như thế nào?

### 3.1. Goal `enforcer:enforce`

Goal chính:

```text
org.apache.maven.plugins:maven-enforcer-plugin:3.6.3:enforce
```

Theo metadata plugin 3.6.3:
- Goal chạy **một lần cho mỗi module** mà nó được thực thi.
- Có default binding phase `validate`.
- Hỗ trợ Maven parallel builds theo thiết kế goal.
- Cần Maven project để thực thi.
- Đọc cấu hình các rule dưới `<rules>`.

Lifecycle điển hình:

```text
validate              -> Enforcer kiểm tra policy
   |
generate-sources
   |
compile               -> Compiler Plugin
   |
test-compile
   |
test                  -> Surefire Plugin
   |
package               -> JAR/WAR Plugin
   |
verify                -> các kiểm tra bổ sung
   |
install / deploy      -> xuất bản artifact khi được yêu cầu
```

Không phải mọi plugin mặc định đều được bind tự động. Enforcer goal có default phase `validate` **không có nghĩa Enforcer tự chạy nếu POM không có plugin execution phù hợp**.

### 3.2. Cấu hình execution

Một phần `<build><plugins>`:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.6.3</version>
    <executions>
        <execution>
            <id>enforce-build-policy</id>
            <phase>validate</phase>
            <goals>
                <goal>enforce</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <rules>
            <requireMavenVersion>
                <version>[3.9.0,4.0.0)</version>
            </requireMavenVersion>
        </rules>
    </configuration>
</plugin>
```

Đây chỉ là fragment; chưa có `<project>`, groupId hay source. `<phase>validate</phase>` làm mục đích rõ ràng, dù goal này đã có default phase validate. `<version>3.6.3</version>` ghim plugin version độc lập với Maven runtime version được rule kiểm tra.

Đặt `<configuration>` ở **plugin level** trong ví dụ có lợi vì cả execution lifecycle và lệnh gọi goal trực tiếp có thể dùng cùng policy. Nếu đặt config chỉ trong một execution ID, gọi goal trực tiếp không nhất thiết lấy cấu hình của execution đó; khi cần gọi chính xác một execution, phải hiểu `default-cli` hoặc goal@execution syntax tương ứng.

### 3.3. Enforcer có thể dừng sớm nhưng không bỏ qua project model construction

Enforcer chạy trong `validate`, nhưng Maven vẫn phải đọc và tạo effective POM, resolve những plugin cần để chạy goal và làm một số bước khởi tạo trước khi rule được thực thi. Nếu POM XML sai, parent không resolve, plugin không tải được hoặc Maven chạy bằng JDK **không khởi động được**, lỗi có thể xuất hiện **trước Enforcer message**.

Ví dụ `requireJavaVersion` yêu cầu JDK 17 nhưng plugin/runtime Maven không thể start trên một JRE quá cũ; Enforcer không thể “cứu” bootstrap đã lỗi. Tương tự, bannedDependencies có thể cần dependency resolution và fail vì repository/network, không phải vì dependency bị cấm.

**Không cam kết mọi build fail đều xuất hiện dưới nhãn Enforcer.** Hãy phân biệt vấn đề khởi tạo Maven, rule violation và các phase compile/test/package.

## 4. Maven version ranges và quy tắc về môi trường

### 4.1. requireMavenVersion

`requireMavenVersion` dùng cú pháp **Enforcer version range**. Một số ví dụ:

| Range | Ý nghĩa |
| --- | --- |
| `[3.9.0,)` | Maven từ 3.9.0 trở lên |
| `[3.9.0,4.0.0)` | Từ 3.9.0, chưa đến 4.0.0 |
| `[3.9.11]` | Chỉ Maven 3.9.11 |
| `(,4.0.0)` | Bất kỳ phiên bản thấp hơn 4.0.0 |
| `(3.9.0,)` | Lớn hơn 3.9.0, không bao gồm 3.9.0 |

Dấu `[` hoặc `]` là cận **bao gồm**; `(` hoặc `)` là cận **không bao gồm**. Cú pháp Enforcer có một điều chỉnh đáng chú ý: giá trị đơn `3.9.0` được hiểu như **mức tối thiểu**, thay vì “Maven chọn 3.9.0 làm recommended version” như một số cách dùng Maven version constraint khác. Khi viết policy, nên dùng dấu ngoặc tường minh để tránh hiểu nhầm.

Ví dụ:

```xml
<requireMavenVersion>
    <version>[3.9.0,4.0.0)</version>
    <message>Build nay chi duoc chay voi Maven 3.9.x.</message>
</requireMavenVersion>
```

Việc khóa major Maven là một **quyết định tương thích của dự án**, không phải nhận định Maven 4 không tốt. Khi CI đã được kiểm thử trên Maven 4, có thể mở rộng range phù hợp.

### 4.2. requireJavaVersion

```xml
<requireJavaVersion>
    <version>[17,)</version>
    <message>Can JDK 17 tro len de build.</message>
</requireJavaVersion>
```

Rule này kiểm tra **Java runtime thực sự chạy Maven**. Nó không tương đương:
- `maven.compiler.release=17`: yêu cầu compiler sinh code theo Java 17 API/bytecode;
- `java.version` property tùy framework/parent: chỉ có tác dụng khi plugin được cấu hình sử dụng;
- Java toolchain riêng: có thể dùng compiler JDK khác với JDK chạy Maven;
- JVM thực tế ở production: được xác định bởi nơi triển khai.

Ví dụ `mvn -version` in Java 21, Compiler Plugin có `<release>17</release>`: `requireJavaVersion [17,)` PASS, source biên dịch theo Java 17 target. Nhưng điều đó **không bảo đảm mọi dependency JAR được chọn đều tương thích Java 17**, vì có thể có thư viện biên dịch bytecode mới hơn. Enforcer 3.6.3 có thêm built-in rule liên quan bytecode version; khi áp dụng hãy đọc docs rule và kiểm chứng runtime.

### 4.3. requireJavaVendor, requireOS và tính di động

Enforcer còn có `requireJavaVendor`/`requireOS`. Chỉ áp dụng nếu sản phẩm **thực sự** yêu cầu vendor cụ thể, OS family hoặc architecture. Một library Java thuần thường không nên cấm Windows hoặc Linux chỉ vì nhóm phát triển đang dùng một hệ điều hành.

Nếu phải build native component trên Linux x86_64, OS rule có thể là điều kiện hợp lý. Nhưng đừng khóa OS cho project không cần để tránh gây hỏng local developer workflow. Hãy đưa lý do và phạm vi vào README chính sách.

## 5. Kiểm tra properties và tệp bắt buộc

### 5.1. requireProperty và regex

Enforcer `requireProperty` có các tham số:
- `property`: tên Maven property cần kiểm tra.
- `message`: thông điệp khi property thiếu.
- `regex`: Java regular expression để kiểm tra value.
- `regexMessage`: thông điệp khi value không khớp pattern.

Regex được áp dụng cho **toàn bộ giá trị** (giống full match), không chỉ một substring. Ví dụ:

```xml
<requireProperty>
    <property>quality.channel</property>
    <message>quality.channel phai duoc khai bao.</message>
    <regex>dev|ci|release</regex>
    <regexMessage>Chi chap nhan dev, ci hoac release.</regexMessage>
</requireProperty>
```

Giá trị `ci` PASS; `staging` FAIL; `ci-extra` FAIL. Ở đây dấu `^...$` là tùy chọn vì regex matching đã kiểm tra toàn value, nhưng bạn có thể thêm nếu team muốn thể hiện rõ.

**Lưu ý:** một property dùng để mô tả channel **không tự chứng minh project đã đạt tiêu chuẩn release**. Nếu `quality.channel=release` chỉ là một biến, một lệnh `-Dquality.channel=release` có thể vượt qua rule property nhưng chưa chắc test, dependency, Git tag, snapshot rules hay approval đạt. Chính sách release thật cần checks bổ sung ở POM/CI.

### 5.2. CLI properties và POM properties

Nếu POM có:

```xml
<properties>
    <quality.channel>dev</quality.channel>
</properties>
```

thì mặc định `mvn validate` PASS khi các rule khác đạt. Lệnh:

```bash
mvn -Dquality.channel=nightly validate
```

đưa Maven user property `quality.channel=nightly` vào session; với regex trên, Enforcer báo FAIL. Lệnh:

```bash
mvn -Dquality.channel=ci validate
```

PASS rule property.

Đây là cách tạo default hợp lý cho local development mà vẫn cho CI truyền một channel có ý nghĩa. Đừng đặt credentials dưới dạng property để in ra log Enforcer; giá trị nhạy cảm nên được quản lý bằng secret stores/CI controls và không đưa vào bài ví dụ.

### 5.3. requireFilesExist: kiểm tra file, không kiểm tra chất lượng file

```xml
<requireFilesExist>
    <files>
        <file>${project.basedir}/policy/BUILD-POLICY.md</file>
    </files>
    <message>Thieu policy/BUILD-POLICY.md trong project.</message>
</requireFilesExist>
```

`requireFilesExist` kiểm tra đường dẫn file cần thiết có tồn tại hay không. Mặc định **mọi file** trong danh sách đều phải tồn tại; option `satisfyAny=true` có thể chấp nhận chỉ một file khi chính sách yêu cầu kiểu “A hoặc B”.

**Đừng dùng `requireFilesExist` ở phase validate để bắt một file chỉ được sinh ở phase package** — file đó chưa có trong clean build. Rule có thể bị cấu hình sai dù pipeline bình thường hoàn toàn đúng. Với file generated, hãy đặt kiểm tra vào phase sau khi file được tạo hoặc chọn rule khác.

Tệp có tồn tại **không bảo đảm nội dung hợp lệ**. Nếu cần kiểm tra checksum, nội dung quy định hoặc schema, xem các built-in rules `requireFileChecksum`/`requireTextFileChecksum` và các plugin chuyên dụng; một file Markdown rỗng cũng có thể vượt qua requireFilesExist.

### 5.4. Những giá trị thay đổi theo environment

Một số policy không nên đặt `requireProperty` vào tất cả builds. Ví dụ chỉ production deploy mới yêu cầu:
- mã môi trường deploy;
- credentials cấp bởi secret manager;
- URL artifact repository nội bộ;
- release approval ID.

Nếu áp dụng những điều kiện này cho mọi local `mvn validate`, người phát triển không thể chạy unit test offline. Hãy tách **core build policy** khỏi **release/deploy policy** bằng Maven profiles, CI jobs hoặc rule level; nhưng không để một profile phát hành vô tình bị bỏ qua trên job chính thức.

## 6. bannedDependencies: loại artifact khỏi cây phụ thuộc

### 6.1. Cấu hình cơ bản

```xml
<bannedDependencies>
    <searchTransitive>true</searchTransitive>
    <excludes>
        <exclude>commons-codec:commons-codec</exclude>
    </excludes>
    <message>Demo policy: commons-codec khong duoc phep.</message>
</bannedDependencies>
```

Rule kiểm tra dependency graph và FAIL nếu artifact match `excludes`. `searchTransitive=true` (mặc định) kiểm cả dependency được kéo gián tiếp bởi các dependencies khác. Có thể đặt false khi chỉ muốn kiểm direct dependencies, nhưng như vậy sẽ **bỏ qua thư viện bị cấm nếu nó xuất hiện qua một tuyến transitive**.

**Lựa chọn `commons-codec:commons-codec` chỉ phục vụ thí nghiệm.** Không suy ra thư viện này hiện có CVE hoặc phải bị cấm ở mọi dự án. Trong thực tế, tổ chức nên định nghĩa denylist có lý do, scope và cách thay thế, đồng thời cập nhật theo policy/SCA.

### 6.2. Tọa độ dùng trong bannedDependencies

Tài liệu 3.6.3 mô tả dạng:

```text
groupId[:artifactId][:version][:type][:scope][:classifier]
```

Có thể dùng wildcard trong từng phần. Ví dụ:

```xml
<excludes>
    <exclude>com.example:old-library</exclude>
    <exclude>org.example:legacy-*:[1.0,2.0)</exclude>
</excludes>
```

**Lưu ý khác với Shade artifactSet:** Ở `bannedDependencies`, phần thứ ba là **version**, không phải type/classifier như trong Shade patterns. Một rule gõ nhầm định dạng có thể không cấm artifact dự định. Cần đối chiếu tài liệu của **chính rule** bạn dùng.

Với version pattern:
- `com.example:lib:1.2` trong Enforcer bannedDependencies có nghĩa cấm version **1.2 trở lên** theo cú pháp tài liệu rule, không đơn giản là đúng một version.
- `com.example:lib:[1.2]` là ví dụ chỉ đúng **version 1.2**.
- `com.example:lib:[1.2,2.0)` có thể dùng cho version interval.

Tránh chính sách mơ hồ kiểu “chặn tất cả phiên bản cũ” mà thiếu cận phiên bản rõ.

### 6.3. includes của bannedDependencies không phải whitelist của Maven dependencies

Trong rule `bannedDependencies`:
- `excludes`: **tập bị cấm**.
- `includes`: **ngoại lệ cho tập bị cấm**.

Nếu artifact không match bất kỳ exclude nào, việc có tên ở includes **không bắt buộc** nó phải được dùng hoặc có mặt. Đây là behavior khác với Shade Plugin `artifactSet.includes` và một số plugin filters.

Ví dụ:

```xml
<bannedDependencies>
    <excludes>
        <exclude>org.example:legacy-*</exclude>
    </excludes>
    <includes>
        <include>org.example:legacy-compat:[2.0]</include>
    </includes>
</bannedDependencies>
```

Khi policy chấp nhận `legacy-compat:2.0` như ngoại lệ, hãy ghi rõ lý do, thời hạn và test. Đừng mở rộng wildcard quá lớn hoặc dùng bao gồm để vô tình vô hiệu hóa toàn bộ excludes.

### 6.4. BannedDependency rule không phải vulnerability scanner

Enforcer kiểm tra **tọa độ và phiên bản theo pattern bạn cấu hình**. Nó không tự lấy một database CVE, phân tích license, xác minh provenance/SBOM hay xem thư viện có bị khai thác không. Với security supply chain, dùng thêm:
- dependency scanning/SCA phù hợp;
- SBOM generation và vulnerability monitoring;
- license compliance;
- repository allowlist và checksum/signature verification;
- review upgrades và dependency tree.

Enforcer là một lớp **policy enforcement**, không phải hệ thống threat intelligence.

## 7. dependencyConvergence và requireUpperBoundDeps khác nhau thế nào?

### 7.1. Dependency convergence

Giả sử graph có:

```text
your-app
  ├── library-A -> common-lib:1.0
  └── library-B -> common-lib:2.0
```

`dependencyConvergence` muốn các tuyến phụ thuộc cùng dùng một version của artifact, không chỉ chấp nhận phiên bản Maven chọn cuối cùng khi các nhánh còn bất đồng. Nếu dependency mediation/management chưa làm graph hội tụ, rule có thể fail.

Cấu hình ví dụ:

```xml
<dependencyConvergence/>
```

Nên thêm rule này khi team muốn kiểm soát transitive version disagreement chặt chẽ, nhưng phải xử lý version alignment qua `dependencyManagement` hoặc nâng dependencies. Không vô hiệu hóa rule bằng một ignore list khổng lồ chỉ để build xanh.

### 7.2. Upper bound dependencies

`requireUpperBoundDeps` kiểm tra dependency version được giải quyết **không thấp hơn version cao nhất được yêu cầu trong các tuyến transitive liên quan**.

Ví dụ:
- Library A yêu cầu common-lib 1.0.
- Library B yêu cầu common-lib 2.0.
- Maven thực tế chọn common-lib 1.0 vì nearest-wins.
- Upper-bound rule FAIL vì version được chọn thấp hơn 2.0.

Nếu Maven chọn common-lib 2.0, upper-bound requirement có thể PASS **ngay khi những tuyến khai báo vẫn không giống nhau**; policy convergence vẫn có thể yêu cầu kiểm tra thêm. Đây là điểm khác biệt giữa hai rule.

Cấu hình:

```xml
<requireUpperBoundDeps/>
```

Tài liệu built-in rule nói `excludedScopes` mặc định gồm `test` và `provided`. Nếu team cần kiểm tra cả các scope này, hãy cấu hình phù hợp. Ngược lại, `dependencyConvergence` có những tùy chọn khác; đừng copy thẳng mọi excludes và mặc định chúng có cùng ý nghĩa.

### 7.3. Quy tắc nào phù hợp?

- **requireUpperBoundDeps:** hợp lý khi muốn tránh tình trạng phiên bản thực dùng **thấp hơn** yêu cầu của dependency khác.
- **dependencyConvergence:** hợp lý khi muốn **mọi tuyến** cùng một version để giảm mơ hồ và nâng độ nhất quán.
- **bannedDependencies:** loại phiên bản/artifact không được phép do policy.
- **Maven dependencyManagement/BOM:** công cụ **điều phối version**; các rule chủ yếu **kiểm tra** quyết định đó.

Kết hợp phải có lý do, nhất là với những graph lớn có nhiều versions hợp lệ. Khi rule fail, hãy đọc cả dependency paths trong báo cáo thay vì chỉ chèn một exclusion ngẫu nhiên.

## 8. Những built-in rules hữu ích khác

| Rule | Điều kiện được kiểm soát | Dùng khi nào? |
| --- | --- | --- |
| `requirePluginVersions` | Plugins cần có version kiểm soát | Muốn build tái lập giữa Maven runtimes |
| `banDuplicatePomDependencyVersions` | Tránh khai báo dependency trùng trong POM | Chống sai sót model maintenance |
| `requireReleaseVersion` | Project không phải SNAPSHOT | Release pipeline |
| `requireReleaseDeps` | Dependencies không chứa SNAPSHOT theo options | Release pipeline |
| `requireSameVersions` | Một nhóm dependencies/plugins đồng phiên bản | Align các plugin của cùng hệ sinh thái |
| `requireNoRepositories` | Kiểm soát repositories trong POM | Doanh nghiệp dùng settings/mirror tập trung |
| `bannedRepositories` | Chặn repository URL không được cho phép | Supply-chain policy |
| `requireProfileIdsExist` | Profile được chỉ định trên CLI thực sự tồn tại | Tránh typo profile bị bỏ qua |
| `requireActiveProfile` | Một profile cần thiết đang active | Một số job dùng policy dựa trên profile |
| `requireEnvironmentVariable` | Có biến môi trường bắt buộc | Jobs triển khai cần environment flag |
| `reactorModuleConvergence` | Một số best practices cho reactor nhiều module | Monorepo có nhiều parent/modules |
| `requireJavaVendor` | JDK vendor hợp lệ | Khi sản phẩm có chứng nhận theo vendor |

### 8.1. requirePluginVersions không giống pin Maven version

Khi dùng `requirePluginVersions`, nó kiểm tra versions của plugins trong `<plugins>`, `<pluginManagement>` và parents, tùy cấu hình. Mặc định `banMavenDefaults=true` có thể bắt bạn khai báo **cả những lifecycle plugins** mà Maven có default từ super POM/lifecycle. Vì vậy với một project mẫu đơn giản, bật rule này ngay với default có thể tạo thêm vi phạm không liên quan bài học.

Cấu hình nhẹ hơn:

```xml
<requirePluginVersions>
    <banLatest>true</banLatest>
    <banRelease>true</banRelease>
    <banSnapshots>true</banSnapshots>
    <banMavenDefaults>false</banMavenDefaults>
</requirePluginVersions>
```

Đây là **fragment bổ sung**, không nằm trong POM runnable chính. `banMavenDefaults=false` cho phép một số plugin defaults từ Maven/lifecycle; nếu tổ chức muốn reproducibility nghiêm ngặt, có thể giữ true và khai báo versions đầy đủ. Cần hiểu khác biệt giữa một **plugin declaration** và plugin được lifecycle mapping chọn gián tiếp.

### 8.2. requireReleaseVersion và requireReleaseDeps

Hai rule không giống nhau:

```xml
<requireReleaseVersion/>
<requireReleaseDeps>
    <searchTransitive>true</searchTransitive>
</requireReleaseDeps>
```

- `requireReleaseVersion`: project hiện tại không được có version `*-SNAPSHOT`; default cũng có thể kiểm parent snapshot theo option.
- `requireReleaseDeps`: dependency graph không được có SNAPSHOT dependencies; mặc định search transitive true. Có option `onlyWhenRelease` để chỉ áp dụng khi project version là release.

**Quan trọng:** project demo có version `1.0.0-SNAPSHOT`. Nếu thêm `requireReleaseVersion` vào core policy của POM runnable, baseline `mvn validate` sẽ FAIL theo đúng thiết kế. Vì thế phần chính không đặt release-only checks; chúng thuộc release profile/job khác.

Nếu cần release profile minh họa:

```xml
<profiles>
    <profile>
        <id>release-policy</id>
        <build>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-enforcer-plugin</artifactId>
                    <version>3.6.3</version>
                    <executions>
                        <execution>
                            <id>enforce-release</id>
                            <phase>validate</phase>
                            <goals>
                                <goal>enforce</goal>
                            </goals>
                            <configuration>
                                <rules>
                                    <requireReleaseVersion/>
                                    <requireReleaseDeps>
                                        <searchTransitive>true</searchTransitive>
                                    </requireReleaseDeps>
                                </rules>
                            </configuration>
                        </execution>
                    </executions>
                </plugin>
            </plugins>
        </build>
    </profile>
</profiles>
```

Đây là **đoạn bổ sung đặt trong `<project>`**, không phải một POM hoàn chỉnh. Khi thêm vào POM main, phải đảm bảo execution IDs và plugin configuration không bị merge theo cách vô tình chạy cả bộ core rules hai lần. Hãy đọc effective POM để thấy thực tế. Chạy `mvn -Prelease-policy verify` với project version SNAPSHOT **được kỳ vọng thất bại**, đúng vì version chưa phải release. Không tự đổi version chỉ để pass rồi gọi đó là sản phẩm sẵn sàng phát hành: CI còn phải kiểm tra tests, artifacts và release permissions.

### 8.3. EnforceBytecodeVersion: checks khác requireJavaVersion

Enforcer 3.6.3 đưa thêm rule kiểm tra bytecode version của dependencies. Điều này giải quyết lớp rủi ro khác với `requireJavaVersion` (JDK chạy Maven) và `maven.compiler.release` (bytecode của code project). Khi áp dụng, đọc docs phiên bản 3.6.3 để thiết lập bytecode target/ignored artifacts phù hợp.

Trong ví dụ đơn giản có Java 17/JUnit 5, không thêm rule bytecode để tránh tạo điều kiện ngầm về versions của transitive dependencies. Khi sản phẩm bắt buộc chạy trên JRE 17 nhưng được build trên JDK mới hơn, kiểm tra bytecode dependency là một phần đáng cân nhắc.

## 9. Ví dụ Maven 3.9 / Java 17 hoàn chỉnh: chính sách chấp nhận build

### 9.1. Cấu trúc thư mục

```text
enforcer-policy-lab/
├── pom.xml
├── policy/
│   └── BUILD-POLICY.md
└── src/
    ├── main/
    │   └── java/com/example/quality/App.java
    └── test/
        └── java/com/example/quality/AppTest.java
```

Project là JAR Java thuần, không cần Spring Boot, Docker, database hay dịch vụ ngoài. Test dùng JUnit Jupiter. Tệp policy là nguồn dữ liệu bắt buộc cho rule `requireFilesExist`; việc thiếu file này làm `validate` FAIL.

### 9.2. `pom.xml` đầy đủ

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>enforcer-policy-lab</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <quality.channel>dev</quality.channel>
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
                <version>3.5.2</version>
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
                        <id>enforce-build-policy</id>
                        <phase>validate</phase>
                        <goals>
                            <goal>enforce</goal>
                        </goals>
                    </execution>
                </executions>
                <configuration>
                    <fail>true</fail>
                    <failFast>false</failFast>
                    <failIfNoRules>true</failIfNoRules>
                    <rules>
                        <requireMavenVersion>
                            <version>[3.9.0,4.0.0)</version>
                            <message>Use Maven 3.9.x for this build.</message>
                        </requireMavenVersion>

                        <requireJavaVersion>
                            <version>[17,)</version>
                            <message>Use Java 17 or newer to run Maven.</message>
                        </requireJavaVersion>

                        <requireProperty>
                            <property>quality.channel</property>
                            <message>quality.channel must be configured.</message>
                            <regex>dev|ci|release</regex>
                            <regexMessage>Allowed: dev, ci, release.</regexMessage>
                        </requireProperty>

                        <requireFilesExist>
                            <files>
                                <file>${project.basedir}/policy/BUILD-POLICY.md</file>
                            </files>
                            <message>Missing policy/BUILD-POLICY.md.</message>
                        </requireFilesExist>

                        <bannedDependencies>
                            <searchTransitive>true</searchTransitive>
                            <excludes>
                                <exclude>commons-codec:commons-codec</exclude>
                            </excludes>
                            <message>Demo policy bans commons-codec.</message>
                        </bannedDependencies>
                    </rules>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**Tại sao POM hợp lệ và có thể chạy?**

1. `groupId/artifactId/version/packaging` hợp lệ cho Maven JAR project.
2. `maven.compiler.release=17` yêu cầu compiler mục tiêu Java 17; JDK chạy Maven phải từ Java 17 để rule PASS.
3. JUnit Jupiter ở `scope=test`, còn code ứng dụng không cần dependency production.
4. Maven Compiler, Surefire, JAR plugins đều có versions được ghim.
5. Enforcer **3.6.3** có execution bind `enforce` vào phase `validate`. Do đó `mvn validate`, `mvn test` hoặc `mvn verify` đều phải vượt cổng này.
6. `<fail>true</fail>` giữ việc vi phạm rule ở mức ERROR làm Maven thất bại.
7. `<failFast>false</failFast>` cho phép plugin thu thập nhiều rule violations trong một lần chạy thay vì chỉ dừng ở rule đầu.
8. `<failIfNoRules>true</failIfNoRules>` ngăn build giả xanh nếu vô tình xóa toàn bộ rules khỏi execution.
9. `requireFilesExist` trỏ tới file trong chính project, không phụ thuộc thư mục shell hiện tại theo path tương đối.
10. Rule cấm Commons Codec nhưng dependency hiện có chỉ JUnit Jupiter; project không dùng Codec trong code, nên baseline không vi phạm.
11. Cấu hình đặt ở plugin level, có thể tái sử dụng khi gọi goal trực tiếp cùng Maven project.
12. `quality.channel=dev` chỉ là giá trị mặc định của bài, không phải bằng chứng qua kiểm soát release thật.

### 9.3. `policy/BUILD-POLICY.md`

Tạo file:

```markdown
# Build acceptance policy

The default build must satisfy these conditions:

- Maven runtime: 3.9.x.
- Java runtime used by Maven: 17 or newer.
- quality.channel: dev, ci, or release.
- Disallowed dependency in this example: commons-codec:commons-codec.
- Validation rules run before compilation.
- A successful release requires additional testing and approval gates.
```

Đây là file thật phải tạo cùng project, không phải chỉ một tên trong POM. Trong dự án lớn, có thể đưa các thông tin build policy vào tài liệu version-controlled; nên review thay đổi file và POM cùng nhau vì Enforcer chỉ kiểm tra sự **tồn tại**, không tự so sánh hai danh sách này.

Nếu file bị xóa hoặc đổi tên, `mvn validate` FAIL ngay cả khi Java source không đổi.

### 9.4. `src/main/java/com/example/quality/App.java`

```java
package com.example.quality;

public final class App {
    private App() {
    }

    public static String greeting(String name) {
        if (name == null || name.isBlank()) {
            return "Hello, guest";
        }
        return "Hello, " + name.strip();
    }

    public static void main(String[] args) {
        System.out.println(greeting(" Maven "));
    }
}
```

Code sử dụng `String.isBlank()` và `String.strip()` có trong Java 17. Không có filesystem, HTTP, thời gian hoặc biến môi trường nên stdout là cố định. Đây là source ứng dụng thật, biên dịch được độc lập bằng Java 17; Enforcer chỉ quyết định build có được phép đi tới compiler hay không.

### 9.5. `src/test/java/com/example/quality/AppTest.java`

```java
package com.example.quality;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

final class AppTest {
    @Test
    void normalizesWhitespace() {
        assertEquals("Hello, Maven", App.greeting(" Maven "));
    }

    @Test
    void returnsGuestForBlankInput() {
        assertEquals("Hello, guest", App.greeting("  "));
    }
}
```

Surefire Plugin 3.5.2 hỗ trợ JUnit Jupiter; class có hậu tố `Test` được phát hiện theo convention. Hai test methods không phụ thuộc network hoặc resource khác. Chúng giúp phân biệt hai cổng:
- `validate` kiểm tra Enforcer conditions.
- `test` kiểm tra business logic.

Chạy `mvn validate` không chạy hai test này; chạy `mvn test` hoặc `mvn verify` sẽ chạy.

### 9.6. Baseline: kiểm tra environment rồi build

Tại thư mục `enforcer-policy-lab`:

```bash
mvn -version
java -version
mvn validate
mvn clean verify
```

Với Maven 3.9.x, Maven chạy bằng JDK 17+, file policy tồn tại, `quality.channel=dev` và chưa có Commons Codec trong graph:
- Enforcer rules PASS ở `validate`.
- Java code được compile.
- Surefire chạy **2 tests**, **0 failures/errors/skipped**.
- JAR được tạo tại `target/enforcer-policy-lab-1.0.0-SNAPSHOT.jar`.
- Maven kết thúc `BUILD SUCCESS` khi không có lỗi khác.

Dạng tóm tắt mong đợi (không phải toàn bộ Maven console):

```text
Enforcer: all configured ERROR rules passed
Surefire: Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Dòng Enforcer phía trên là **diễn giải**, không đảm bảo được Maven in nguyên văn vì format và logging của goal có thể khác giữa môi trường. Trong log thật, kiểm tra execution ID `enforce-build-policy` và thông tin rules.

### 9.7. Chạy code sau khi build

```bash
java -cp target/classes com.example.quality.App
```

**Stdout chính xác:**

```text
Hello, Maven
```

Không dùng `java -jar target/enforcer-policy-lab-1.0.0-SNAPSHOT.jar` để mong chạy entry point: POM không khai báo manifest `Main-Class`. Dùng `java -cp` như trên. Kết quả cho biết code chạy đúng, **không phải tự nó chứng minh Maven/Java policy**; phần đó đã được Enforcer xác nhận trong build.

### 9.8. Test nhanh chỉ cổng chất lượng

```bash
mvn validate
```

Đây là lệnh ít bước hơn `mvn verify`, hữu ích để kiểm tra các rule sớm trước các job build dài. Nó vẫn có thể cần resolve plugin/dependencies và không nhất thiết chạy được offline nếu repository/cache chưa đủ. `mvn validate` PASS chỉ có nghĩa **những rule được bind vào validate** PASS, không có nghĩa Java code đã được compile hay tests đã chạy.

## 10. Bốn thí nghiệm vi phạm và cách sửa đúng

Mỗi thí nghiệm dưới đây là **một thay đổi có chủ đích**, không thuộc POM hoàn chỉnh sau cùng. Thực hiện riêng từng thí nghiệm, quan sát lỗi rồi **khôi phục** trạng thái baseline trước khi chuyển sang thí nghiệm kế tiếp.

### 10.1. Sai property: quality.channel=nightly

```bash
mvn -Dquality.channel=nightly validate
```

Vì regex chỉ nhận `dev|ci|release`, Enforcer `requireProperty` FAIL và Maven trả mã lỗi. Một thông báo có thể nhắc:

```text
Allowed: dev, ci, release.
```

Đây là thông điệp `regexMessage` do POM khai báo, không đảm bảo toàn bộ log có đúng một dòng như vậy. **Cách sửa** không phải tắt Enforcer mà là dùng channel đúng:

```bash
mvn -Dquality.channel=ci validate
```

Nếu chính sách thực tế cho phép `nightly`, hãy cập nhật regex và tài liệu policy qua code review, rồi xác minh CI các channel khác vẫn đúng.

### 10.2. Thiếu file policy

Tạm thời đổi tên hoặc di chuyển `policy/BUILD-POLICY.md` ra khỏi đường dẫn được yêu cầu (lưu ý khôi phục ngay sau thử nghiệm). Chạy:

```bash
mvn validate
```

`requireFilesExist` FAIL vì file không còn tồn tại. Cách khắc phục là **khôi phục file đúng vị trí** hoặc thay đổi policy có phê duyệt; không tạo file rỗng để đánh lừa một quy định vốn yêu cầu nội dung thực tế.

Nếu file thực sự chỉ được tạo tại phase sau, thì yêu cầu `requireFilesExist` trong validate là thiết kế sai. Phải đổi phase hoặc cách tạo file; không disable toàn bộ cổng chất lượng.

### 10.3. Dependency bị cấm được thêm vào POM

Tạm thêm vào `<dependencies>`:

```xml
<dependency>
    <groupId>commons-codec</groupId>
    <artifactId>commons-codec</artifactId>
    <version>1.17.1</version>
</dependency>
```

Chạy:

```bash
mvn validate
```

`bannedDependencies` dự kiến FAIL vì GAV match `commons-codec:commons-codec`. Nếu lỗi mạng hoặc repository xảy ra trước, đó không phải bằng chứng Enforcer đã kiểm tra rule; hãy đảm bảo dependency resolve thành công mới kết luận.

**Cách sửa cho bài demo:** xóa dependency vừa thêm. Với project thật, trước tiên xác minh vì sao artifact cần thiết, có alternative được phép không và denylist có đang quá rộng không. Không nên đổi artifactId giả, loại transitive tùy tiện hoặc tắt rule chỉ để build xanh.

### 10.4. Maven hoặc JDK ngoài phạm vi

Nếu `mvn -version` đang dùng Maven 3.8.8 hoặc Maven 4, rule `requireMavenVersion [3.9.0,4.0.0)` sẽ không chấp nhận. Nếu Maven chạy bằng JDK 11, `requireJavaVersion [17,)` không chấp nhận.

**Không giả lập JDK thật bằng `-Djava.version=17`**. Rule kiểm tra runtime mà Maven dùng; thay đổi một project property không làm đổi JVM đang chạy. Khắc phục bằng:
- Maven Wrapper chỉ tới Maven distribution được hỗ trợ, hoặc cài Maven phù hợp;
- cấu hình `JAVA_HOME`/toolchain/CI image đúng JDK;
- chạy `mvn -version` lại để xác minh.

Hãy nhớ có thể Maven/plugin fail ở bootstrap trước khi Enforcer kiểm tra nếu runtime quá cũ. Trường hợp đó vẫn là build không đạt, nhưng chẩn đoán cần nhìn lỗi gốc.

## 11. fail, failFast, WARN, skip và failIfNoRules

### 11.1. fail=true: có vi phạm ERROR thì build fail

```xml
<fail>true</fail>
```

Đây là default của goal 3.6.3. Khi ít nhất một rule ở level ERROR không đạt, Enforcer báo error và Maven build FAIL. Đây là lựa chọn cho **policy bắt buộc**.

Có thể truyền:

```bash
mvn -Denforcer.fail=false validate
```

Tham số này khiến violations được ghi ở mức cảnh báo thay vì làm build fail theo behavior plugin. **Đây là một override để chẩn đoán**, không nên mặc định cho release CI, vì khiến chính sách không còn chặn artifact.

### 11.2. failFast=false: báo nhiều lỗi cùng lúc

```xml
<failFast>false</failFast>
```

Lựa chọn này cho Enforcer chạy thêm rules để thu thập nhiều vi phạm trong một lần execute, giúp developer sửa nhiều lỗi. Nếu `failFast=true`, plugin dừng sau rule đầu tiên không PASS. Đừng nhầm `failFast` với Maven Reactor option `--fail-fast/-ff`; hai tham số tác động hai tầng khác nhau.

Ví dụ:

```bash
mvn -Denforcer.failFast=true validate
```

Có thể hữu ích để khoanh vùng, nhưng không làm một rule xấu trở thành tốt.

### 11.3. level=WARN chỉ áp dụng cho rule đó

Từng rule có thể đặt:

```xml
<requirePluginVersions>
    <level>WARN</level>
    <banMavenDefaults>false</banMavenDefaults>
</requirePluginVersions>
```

Ở mức WARN, vi phạm rule này cảnh báo, **không làm build fail**, trong khi những rule khác mặc định ERROR vẫn chặn build. Đây là cách rollout rule mới theo giai đoạn: đo mức độ vi phạm trước, sau đó chuyển sang ERROR khi team đã chuẩn bị.

**Không nhầm `level=WARN` với `fail=false`:** `WARN` điều chỉnh mức một rule, còn `fail=false` điều chỉnh behavior của goal cho violations theo tham số plugin.

### 11.4. skip và các rủi ro bảo vệ CI

```bash
mvn -Denforcer.skip=true verify
```

`enforcer.skip` điều khiển bỏ qua toàn bộ Enforcer checks trong goal; build có thể tiếp tục tới compile/test/package mà **không xác nhận policy**. Trong CI quan trọng, phải quản lý ai được truyền flags, kiểm tra command line và không dùng skip như một cách chữa lâu dài.

```xml
<failIfNoRules>true</failIfNoRules>
```

Mặc định là true từ Enforcer 3.2.0: nếu không còn rule nào được chọn/cấu hình, goal sẽ fail. Điều này giúp tránh sai sót khi refactor POM khiến Enforcer chạy nhưng chẳng kiểm tra gì. Tuy vậy nếu `enforcer.skip=true` được truyền, chính sách vẫn có thể bị bỏ qua; `failIfNoRules` không phải một cơ chế chống mọi bypass.

### 11.5. Chọn rule theo ID hoặc tên

Enforcer 3.6.3 hỗ trợ user properties `enforcer.rules` (rulesToExecute) và `enforcer.skipRules` (rulesToSkip), cho phép kiểm tra/loại các rules theo danh sách matching. Các rules có thể có `ruleName` để phân biệt cấu hình khi cần. Đây là cơ chế hữu ích để debug một rule cụ thể, nhưng **không nên cho một release job tùy ý bỏ nhóm policy bắt buộc**.

Đừng sử dụng ví dụ từ phiên bản Enforcer quá cũ với property `rules` mà mặc định behavior giống 3.6.3: docs hiện hành ưu tiên `enforcer.rules`.

## 12. Multi-module: Enforcer hoạt động ở đâu trong Maven Reactor?

### 12.1. Parent plugin config có thể được kế thừa

Giả sử:

```text
root (parent + aggregator, packaging=pom)
├── core-lib
├── api
└── app
```

Đặt Enforcer Plugin vào `<build><plugins>` của **parent POM** có thể làm plugin configuration và execution được kế thừa bởi các module con theo Maven inheritance (trừ khi cấu hình inherited=false/merge khác). Goal `enforcer:enforce` theo docs chạy **mỗi module** có execution tương ứng. Vì vậy parent có thể kiểm JDK/Maven trên từng module, còn dependency rules phản ánh graph của từng module.

Nhưng `<pluginManagement>` đơn thuần **không tự kích hoạt goal ở mọi module**. Nó quản lý version/configuration cho plugin được sử dụng; phải có `<build><plugins>` hoặc execution activation phù hợp. Một root aggregator không phải parent của các module cũng **không tự truyền rules** vào child POMs.

### 12.2. requireFilesExist với project.basedir trong multi-module

Ví dụ rule:

```xml
<file>${project.basedir}/policy/BUILD-POLICY.md</file>
```

được thực thi ở module `api` sẽ dùng `api/policy/BUILD-POLICY.md`, không dùng root/policy file. Nếu chỉ root có file policy, các modules con có thể FAIL dù developer nghĩ đường dẫn là root.

Có ba chiến lược:
1. Mỗi module giữ một `policy/BUILD-POLICY.md` riêng, nếu policy thực sự per-module.
2. Dùng một property/path rõ ràng trỏ tới policy **ở aggregator root**, được kiểm chứng với cấu trúc monorepo và Maven versions cụ thể.
3. Chỉ chạy file rule ở root trong một execution riêng, còn JDK/Maven/dependency rules kế thừa cho modules (đồng thời đảm bảo root policy **thực sự được chạy** trong CI).

Không vô tình đặt `<inherited>false</inherited>` cho **toàn bộ Enforcer** nếu bạn vẫn muốn child dependencies bị kiểm tra. Và đừng quên rằng `mvn -pl :app verify` có thể không thực thi lifecycle trên aggregator root; một cổng chất lượng **chỉ ở root** có thể bị bỏ qua trong partial builds. Khi thiết kế, hãy thử cả full reactor và `-pl`.

### 12.3. Dependency rules theo từng module

`bannedDependencies` thường kiểm dependency graph của module đang chạy. Nếu một module `api` dùng library bị cấm nhưng module `app` không trực tiếp dùng, hãy xác định Enforcer có thực thi ở `api` không. Một lệnh chỉ chạy `-pl :app` không mặc nhiên xác minh mọi module trong repository; những module không tham gia lần build không có cơ hội chạy rule của chúng.

Vì thế kết quả “policy PASS” luôn có **scope**: phiên bản policy, project, active modules, profiles, Maven command và môi trường. Trong CI mono-repo, full build hoặc matrix of modules là cách làm rõ coverage.

## 13. CI: thiết kế cổng chất lượng không bị “xanh giả”

### 13.1. Pipeline ba bước

Một pipeline Maven thông thường có thể chia:

```text
Step 1 - Policy
    mvn -B -ntp -Dquality.channel=ci validate
          |
          v
Step 2 - Code and tests
    mvn -B -ntp -Dquality.channel=ci clean verify
          |
          v
Step 3 - Artifact checks and release
    security/SBOM/license/deployment checks
    release approval, publish
```

Lưu ý `clean verify` đã bao gồm phase validate trong cùng invocation, nên **Step 1 là fast feedback tùy chọn** nếu team muốn phát hiện policy fail sớm. Chạy hai lệnh sẽ kiểm policy hai lần; nếu latency quan trọng, có thể chỉ dùng `clean verify`.

- `-B` là batch mode dành cho CI.
- `-ntp` làm Maven ít hiển thị tiến trình download.
- `quality.channel=ci` giúp phân biệt job CI với local.
- `mvn verify` đi qua compilation/tests/package và các plugins khác đã cấu hình.

**Tuyệt đối không tự suy ra release-ready chỉ vì build `validate` PASS.** Chúng ta còn cần test coverage, security scanning, artifact provenance, publishing policy và kiểm thử runtime.

### 13.2. Maven Wrapper và Enforcer là hai lớp bổ sung

Maven Wrapper (`mvnw`/`mvnw.cmd`) có thể cố định Maven distribution mà repository muốn dùng; Enforcer `requireMavenVersion` kiểm phiên bản Maven **đã chạy thực tế**. Chúng bổ sung nhau:
- Wrapper giúp developer/CI khởi chạy đúng Maven version theo cấu hình project.
- Enforcer giúp ngăn build bằng Maven runtime không phù hợp, kể cả khi người dùng gọi trực tiếp `mvn`.

Wrapper không tự cố định JDK đang chạy Maven, nên vẫn cần JDK configuration/toolchain và `requireJavaVersion` khi phù hợp. Đồng thời Enforcer range không tự tải/cài Maven Wrapper hoặc JDK.

### 13.3. Profiles dev, CI và release

Một convention:
- Local dev mặc định `quality.channel=dev`, core rules chạy.
- CI test: `quality.channel=ci`, core rules + tests/coverage/analysis.
- CI release: `quality.channel=release`, core rules + release-only checks + security/deploy approvals.

Nhưng **đặt property channel không tự bật Maven profile** có cùng tên. Nếu muốn thực thi release-only Enforcer rules, phải kích hoạt profile (ví dụ `-Prelease-policy`) hoặc cấu hình CI gọi execution/goal rõ ràng. Đừng nhầm `-Dquality.channel=release` với `-Prelease-policy`.

### 13.4. Bảo vệ khỏi việc skip gate

Một pipeline có thể bị làm “xanh” giả nếu truyền:
- `-Denforcer.skip=true`;
- `-Denforcer.fail=false`;
- cấu hình `<level>WARN</level>` cho rule bắt buộc;
- `-DskipTests` hoặc `-Dmaven.test.skip=true` để bỏ test;
- `-pl` chỉ build subset modules nhưng vẫn báo toàn repository PASS;
- `-Prelease-policy` bị quên;
- build đọc snapshot JAR cũ trong cache.

Chính sách CI tốt cần **giới hạn quyền sửa workflow, review POM, không cho job publish bỏ required checks**, đồng thời lưu command line, tool versions, test results và build artifact metadata.

### 13.5. Enforcer không thay các plugin quality khác

| Nhiệm vụ | Thành phần phù hợp |
| --- | --- |
| Maven/JDK version, dependency denylist, required property/file | Enforcer |
| Unit/integration test | Surefire/Failsafe |
| Coverage đo và check ngưỡng | JaCoCo và policy CI |
| Kiểm tra format/style | Checkstyle/Spotless hoặc công cụ tương đương |
| Static analysis | PMD/SpotBugs/Sonar hoặc tương đương |
| Kiểm tra phụ thuộc dễ tổn thương | SCA/Dependency scanning và dữ liệu CVE |
| Tạo SBOM và kiểm nguồn gốc | CycloneDX/SPDX tooling, signing/provenance workflow |
| Kiểm thử deploy/runtime | Integration/environment smoke tests |

Đưa tất cả các mục trên vào một “Enforcer check” duy nhất sẽ tạo cảm giác an toàn sai. Hãy coi Enforcer là **một lớp chính sách** trong hệ thống cổng chất lượng nhiều lớp.

## 14. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `mvn validate` không chạy Enforcer | Chưa khai báo execution, plugin chỉ trong pluginManagement | Đưa plugin vào `build/plugins`, bind enforce |
| Enforcer nói Maven không đúng version | Range không bao gồm bản Maven đang chạy | Chạy `mvn -version`, dùng Wrapper hoặc điều chỉnh policy có review |
| Enforcer báo JDK quá cũ | Maven dùng `JAVA_HOME` khác JDK kỳ vọng | Kiểm tra `mvn -version`, CI image/toolchain |
| `maven.compiler.release=17` nhưng build policy PASS trên JDK 21 | Đúng: Java chạy Maven >=17 | Compiler target và runtime versions là hai kiểm tra khác |
| `requireProperty` FAIL dù nhìn thấy property trong POM | CLI/profile override, regex full match, property sai tên | Xem effective POM/user properties, sửa nguồn |
| `quality.channel=nightly` FAIL | Không match `dev|ci|release` | Chọn channel đúng hoặc sửa policy qua review |
| `requireFilesExist` FAIL ở module con | `project.basedir` của module, file chỉ ở root | Cấu hình path/per-module rule đúng |
| File được tạo ở `package` nhưng validate yêu cầu nó | Kiểm tra quá sớm | Đổi phase/check hoặc cách tạo file |
| bannedDependencies FAIL vì transitive | `searchTransitive=true` | Xem dependency tree và tuyến kéo artifact vào |
| Library bị cấm vẫn xuất hiện | Pattern sai GAV/version/scope hoặc rule không chạy | Đối chiếu rule docs và dependency tree |
| Banned rule `includes` không bắt buộc một library được dùng | Includes chỉ là ngoại lệ cho excludes | Dùng rule đúng mục tiêu thay vì whitelist giả |
| `dependencyConvergence` FAIL | Hai tuyến dependency dùng versions khác nhau | Dùng dependencyManagement/BOM/nâng dependency |
| `requireUpperBoundDeps` FAIL | Version Maven resolve thấp hơn transitive upper bound | Đọc dependency paths, sửa version mediation |
| `requirePluginVersions` FAIL dù project không khai báo plugin | Default lifecycle plugin chưa pin, banMavenDefaults | Pin plugins hoặc điều chỉnh policy có chủ đích |
| Enforcer kiểm tra một lần ở root, không ở modules | Plugin config không được child kế thừa/activation sai | Kiểm tra inheritance và effective POM từng module |
| `mvn -pl :app verify` PASS nhưng module khác vi phạm | Module khác không thuộc active reactor selection | Build đủ modules hoặc matrix |
| Build chạy dù rule báo WARN | Rule đặt `level=WARN` hoặc fail=false | Chuyển thành ERROR theo quality policy |
| Build không chạy bất kỳ rule nào nhưng xanh | Enforcer skip, plugin không được bind, hoặc config lỗi | Đọc execution log và failIfNoRules |
| Lệnh debug goal trực tiếp không thấy rules | Config chỉ ở một execution cụ thể | Đặt config ở plugin level hoặc gọi đúng execution |
| `-Denforcer.skip=true` làm policy biến mất | Skip all Enforcer rules | Bỏ cờ, khóa CI required checks |
| Maven không tải plugin trước khi Enforcer chạy | Repository/network/parent/bootstrap | Sửa resolution trước khi chẩn đoán rule |
| Build pass nhưng tests không chạy | Chỉ validate hoặc tests bị skip | Chạy verify, kiểm Surefire/Failsafe reports |

### 14.1. Quy trình điều tra ngắn

1. Chạy `mvn -version`; ghi Maven runtime và JDK mà Maven đang dùng.
2. Chạy `mvn validate`; xem goal `enforcer:enforce` có thực thi không.
3. Đọc rule bị fail và thông điệp được POM cấu hình; tránh suy diễn từ dòng `BUILD FAILURE` chung chung.
4. Kiểm tra `pom.xml`, parent POM và `help:effective-pom` để biết rule/phase/versions có hiệu lực.
5. Với property, so xem giá trị đến từ POM, CLI `-D`, Maven profile hay CI.
6. Với file, kiểm đường dẫn đã resolve theo `project.basedir` và phase tạo file.
7. Với dependency, chạy `dependency:tree`, tìm direct/transitive paths và điều chỉnh graph/policy.
8. Khi muốn tiếp tục build để điều tra lỗi khác, có thể dùng Enforcer WARN/fail=false **tạm thời ngoài release pipeline**, ghi rõ rằng build chưa qua gate.
9. Sau khi sửa, chạy lại `mvn clean verify` và kiểm tests/artifact thật.
10. Nếu nhiều module, kiểm tra reactor scope và những modules có execution Enforcer.

### 14.2. Lệnh kiểm tra cấu hình

```bash
mvn -version
mvn validate
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:describe "-Dplugin=org.apache.maven.plugins:maven-enforcer-plugin:3.6.3" -Dgoal=enforce -Ddetail=true
mvn org.apache.maven.plugins:maven-dependency-plugin:3.10.0:tree
mvn clean verify
```

`help:effective-pom` cho thấy POM sau inheritance/profile; `help:describe` mô tả metadata goal; `dependency:tree` hỗ trợ chẩn đoán artifact. Lưu ý khi Enforcer đang FAIL ở validate, **một số lệnh cũng có thể kích hoạt policy hoặc không tới được phase tiếp theo**, tùy cách bạn gọi goal/lifecycle và build environment. Không nên giả định mọi lệnh debug bỏ qua Enforcer.

`mvn -X` có thể giúp xem property resolution và dependency graph, nhưng debug logs có thể chứa đường dẫn, repository URLs và credentials; hãy lọc thông tin nhạy cảm trước khi chia sẻ.

## 15. Các ngộ nhận phổ biến

**“Khai báo Enforcer Plugin version là đủ để mọi build tự kiểm tra.”** Sai: cần plugin goal execution trong lifecycle hoặc gọi goal trực tiếp.

**“Enforcer chỉ chạy khi `mvn enforce`.”** Sai: nếu bind `enforce` vào validate, mọi lệnh lifecycle đi qua validate sẽ kích hoạt.

**“requireJavaVersion xác minh bytecode mà compiler tạo.”** Sai: nó kiểm JVM chạy Maven; bytecode target là vấn đề Compiler Plugin, dependency bytecode có rule riêng.

**“build.policy file có mặt nghĩa là build policy được thực thi đúng.”** Sai: `requireFilesExist` chỉ kiểm sự tồn tại.

**“bannedDependencies tự cập nhật CVE từ internet.”** Sai: nó kiểm artifact coordinates/version patterns đã được cấu hình.

**“includes của bannedDependencies là whitelist bắt buộc dependency phải xuất hiện.”** Sai: includes chỉ tạo ngoại lệ cho excludes.

**“`-Denforcer.skip=true` là cách sửa lỗi policy.”** Sai: đó là cách bỏ kiểm tra, không sửa nguyên nhân.

**“`level=WARN` vẫn chặn phát hành.”** Sai: WARN cảnh báo mà không fail build từ rule đó.

**“`failFast=false` nghĩa là policy không fail.”** Sai: nó chỉ cho phép kiểm tiếp nhiều rules; nếu có ERROR, `fail=true` vẫn làm build fail.

**“`mvn validate` PASS là code và test đạt.”** Sai: validate không mặc nhiên compile hoặc chạy tests.

**“Enforcer ở root POM luôn kiểm tất cả modules bất kể -pl.”** Sai: cần xét inheritance và reactor selection.

**“requireReleaseVersion và requireReleaseDeps là cùng một điều.”** Sai: một rule kiểm version project, rule còn lại kiểm SNAPSHOT dependencies.

## 16. Bài tập tự đánh giá

**Bài 1 — cổng môi trường.** Maven 3.8.8, JDK 17: `requireMavenVersion [3.9.0,4.0.0)` và `requireJavaVersion [17,)` có cùng PASS không? **Không**, Maven version FAIL dù JDK PASS.

**Bài 2 — property regex.** Với `quality.channel=dev|ci|release`, truyền `-Dquality.channel=staging` có được chấp nhận không? **Không**.

**Bài 3 — Maven 4.** POM yêu cầu `[3.9.0,4.0.0)`. Maven 4.0.0 PASS? **Không**, cận 4.0.0 loại trừ.

**Bài 4 — phase.** Vì sao nên bind rule môi trường vào validate? **Chặn sớm** trước compile/test/package, tiết kiệm công build sai.

**Bài 5 — file.** `requireFilesExist` kiểm `policy/BUILD-POLICY.md` có chứng minh Markdown đúng nội dung pháp lý không? **Không**, chỉ kiểm tồn tại.

**Bài 6 — transitive.** POM không khai Commons Codec trực tiếp nhưng một dependency kéo nó vào. Với `searchTransitive=true`, bannedDependencies có phát hiện không? **Có**, nếu artifact được resolve trong graph rule kiểm và match exclude pattern.

**Bài 7 — ignore cờ.** `mvn verify -Denforcer.skip=true` thành công có chứng minh Enforcer PASS không? **Không**, Enforcer đã bị skip.

**Bài 8 — WARN.** Một rule `level=WARN` không đạt nhưng các ERROR rules đều PASS. Build có nhất thiết FAIL không? **Không**, warning không fail build.

**Bài 9 — failFast.** `failFast=false` có đồng nghĩa bỏ qua lỗi không? **Không**; nó cho phép thu thập nhiều violations hơn.

**Bài 10 — release.** Project version `1.0.0-SNAPSHOT`, bật `requireReleaseVersion`. Kết quả? **FAIL** theo đúng policy; đổi thành version release và kiểm các checks khác trước khi publish.

**Bài 11 — dependency conflict.** Graph yêu cầu lib:1.0 và lib:2.0, Maven chọn lib:1.0. Rule nào có thể phát hiện chọn thấp hơn upper bound? **requireUpperBoundDeps**.

**Bài 12 — convergence.** Nếu Maven chọn lib:2.0 nhưng các nhánh vẫn khai version khác nhau, upperBoundDeps và dependencyConvergence có nhất thiết giống kết quả? **Không**.

**Bài 13 — multi-module.** Parent rule dùng `${project.basedir}/policy/...`, nhưng file chỉ ở root. Điều gì xảy ra khi rule kế thừa xuống module con? **File path trỏ vào module con**, có thể FAIL nếu không có file.

**Bài 14 — test.** `mvn validate` PASS, `mvn verify` FAIL ở JUnit test. Điều này có mâu thuẫn không? **Không**: hai tầng quality gate khác nhau.

**Bài 15 — khởi tạo Maven.** Parent POM không resolve nên Enforcer chưa kịp chạy. Có thể coi đó là rule FAIL không? **Không chính xác**; đó là lỗi dựng model/resolve trước Enforcer, dù kết quả tổng build vẫn FAILED.

## 17. Checklist đưa Maven Enforcer vào dự án thật

- [ ] Đã định nghĩa từng **điều kiện chấp nhận** thành một yêu cầu đo/kiểm được.
- [ ] Đã chọn và ghim Maven Enforcer Plugin version.
- [ ] Đã khai báo `<executions><execution><goal>enforce</goal>` trong `<build><plugins>`.
- [ ] Đã xác nhận goal được chạy ở `validate` hoặc phase phù hợp với dữ liệu cần kiểm.
- [ ] Đã tách điều kiện Maven runtime, JDK runtime và Java compiler release.
- [ ] Đã dùng version ranges tường minh, không vô tình loại một bản Maven/JDK được hỗ trợ.
- [ ] Đã kiểm tra regex/property values từ POM, profiles và CLI trong CI.
- [ ] Đã xác minh đường dẫn của requireFilesExist tại từng module và thời điểm file được tạo.
- [ ] Đã xác định dependency denylist có lý do; searchTransitive phù hợp.
- [ ] Đã phân biệt version graph convergence, upper-bound check và dependency mediation.
- [ ] Đã kiểm soát `fail`, `failFast`, `failIfNoRules`, `level` và bỏ skip flags trên CI bắt buộc.
- [ ] Khi dùng parent POM, đã xác nhận inheritance và pluginManagement activation.
- [ ] Khi dùng `-pl`/multi-module, đã xác nhận phạm vi module được kiểm tra.
- [ ] Đã phân biệt development policy và release-only policy.
- [ ] Đã chạy `mvn clean verify` để kiểm code/tests, không dừng ở validate.
- [ ] Đã có SCA/security/license/SBOM và runtime tests nếu hệ thống yêu cầu.
- [ ] Đã sử dụng Maven Wrapper/CI images phù hợp mà không chỉ dựa vào Enforcer.
- [ ] Đã thử ít nhất một tình huống rule PASS và một tình huống FAIL.
- [ ] Đã bảo vệ workflow CI khỏi skip rule và báo “build xanh” khi chưa qua cổng.
- [ ] Đã lập kế hoạch bảo trì version ranges, denylist và plugin versions khi nâng Maven/JDK.

**Kết luận:** Maven Enforcer Plugin cho phép biến những yêu cầu về **môi trường, cấu hình và dependencies** thành cổng quyết định build có được tiếp tục hay không. Điều quan trọng không nằm ở số lượng rules, mà là **điều kiện được viết chính xác, phase đặt đúng, báo lỗi hữu ích, không bị skip trong CI**, và được kết hợp với các chất lượng khác như test, coverage, security scanning và release approval. Một `mvn validate` PASS là **cổng điều kiện ban đầu**, không phải giấy chứng nhận sản phẩm đã sẵn sàng phát hành.

### Tài liệu chính thức

- [Apache Maven Enforcer Plugin 3.6.3 — Usage](https://maven.apache.org/enforcer/maven-enforcer-plugin/usage.html)
- [Apache Maven Enforcer Plugin 3.6.3 — enforcer:enforce](https://maven.apache.org/enforcer/maven-enforcer-plugin/enforce-mojo.html)
- [Apache Maven Enforcer — Built-In Rules](https://maven.apache.org/enforcer/enforcer-rules/index.html)
- [Require Maven Version](https://maven.apache.org/enforcer/enforcer-rules/requireMavenVersion.html)
- [Require Java Version](https://maven.apache.org/enforcer/enforcer-rules/requireJavaVersion.html)
- [Enforcer Version Range Specification](https://maven.apache.org/enforcer/enforcer-rules/versionRanges.html)
- [Require Property](https://maven.apache.org/enforcer/enforcer-rules/requireProperty.html)
- [Require Files Exist](https://maven.apache.org/enforcer/enforcer-rules/requireFilesExist.html)
- [Banned Dependencies](https://maven.apache.org/enforcer/enforcer-rules/bannedDependencies.html)
- [Dependency Convergence](https://maven.apache.org/enforcer/enforcer-rules/dependencyConvergence.html)
- [Require Upper Bound Dependencies](https://maven.apache.org/enforcer/enforcer-rules/requireUpperBoundDeps.html)
- [Require Plugin Versions](https://maven.apache.org/enforcer/enforcer-rules/requirePluginVersions.html)
- [Require Release Version](https://maven.apache.org/enforcer/enforcer-rules/requireReleaseVersion.html)
- [Require Release Dependencies](https://maven.apache.org/enforcer/enforcer-rules/requireReleaseDeps.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)

# Đọc cảnh báo tương thích và release notes trước khi nâng cấp Maven

## 1. Bắt đầu từ câu hỏi: Nâng lên bản mới sẽ thay đổi điều gì?

Trong chủ đề **Nâng cấp Maven**, đọc release notes không phải một bước hình thức. Maven là công cụ điều phối toàn bộ build: nó đọc POM, xây effective model, resolve dependency và plugin, thực thi compile/test/package, tương tác repository, tạo artifacts và kết hợp các Maven extensions.

Khi đổi phiên bản Maven Core, **cùng một commit Git và cùng một lệnh `mvn clean verify` vẫn có thể cho kết quả khác nhau**. Lý do không nhất thiết là code Java thay đổi. Maven mới có thể siết kiểm tra POM, thay dependency ordering, thay transport HTTP, bỏ backward compatibility của API plugin hoặc thay những mặc định từ Super POM.

Ví dụ thực tế theo release notes chính thức:

- **Maven 3.8 → 3.9:** Resolver mặc định dùng native HTTP thay vì Wagon; Maven không còn inject ngầm một thư viện `plexus-utils` cũ vào plugin classpath; `.mvn/maven.config` đổi cách hiểu arguments; plugin validation có thể phát cảnh báo.
- **Maven 3.9 → 3.10.0:** Resolver 2.x, POM validation nghiêm ngặt hơn, dependency classpath ordering thay đổi, Super POM defaults thay đổi, cơ chế giới hạn origin của repository credentials chặt hơn.
- **Maven 3 → Maven 4:** là một **major migration**, Maven 4 cần Java 17 để **chạy Maven**, đồng thời POM/plugins/CI lifecycle có những thay đổi cần thử riêng.

**Một WARNING mới có thể là thông báo khắc phục sớm, nhưng cũng có thể báo một lỗi sẽ trở thành ERROR ở bản sau.** Đánh giá cảnh báo dựa trên **mục release notes + build evidence**, không chỉ đếm số dòng màu vàng.

### Mục tiêu của bài

Sau khi học, bạn sẽ:
1. Tìm đúng Maven releases history, version-specific release notes, full changelog và migration guide.
2. Hiểu cách đọc `Potentially Breaking Changes`, `Known Issues`, `Security Hardening`, `Notable Changes`, `Plugin Validation` và yêu cầu Java.
3. Phân biệt nâng Maven Core với nâng plugin, Maven Wrapper và JDK.
4. Tạo bảng risk register: thay đổi nào, hệ thống nào bị ảnh hưởng, cách kiểm tra, cách sửa và rollback.
5. Xây một project Maven Java 17/JUnit 5 có **4 tests** để làm phép so baseline/candidate.
6. So sánh effective POM, profiles, dependency graph, test reports và artifact bytes, không chỉ BUILD SUCCESS.
7. Lập kế hoạch CI chạy hai Maven versions song song trước khi đổi production.
8. Xử lý một số lỗi thường gặp mà không tắt validations hoặc đưa secrets vào logs.

Bài sử dụng những bản phát hành làm **ví dụ cụ thể** là Maven 3.9.16 và Maven 3.10.0; nội dung hướng tới quy trình nâng cấp nói chung. Trước mỗi nâng cấp thật, luôn kiểm tra **release history mới nhất** của Apache Maven thay vì coi version trong bài là target bắt buộc.

## 2. Những tài liệu chính thức cần mở

### 2.1. Maven Releases History

Trang: https://maven.apache.org/docs/history.html

Xác định:
- Version, ngày phát hành, nhánh phiên bản.
- Trạng thái **General Availability (GA)** hay **Release Candidate/Beta**.
- Required Java Version.
- Nhánh đang được hỗ trợ, cảnh báo EOL/EOS.
- Links sang release notes, announcement và reference documentation.

**Không đánh đồng bản RC với bản production GA.** Có thể dùng RC để kiểm thử compatibility và cung cấp feedback, nhưng quyết định rollout production phải theo policy/risk của tổ chức.

### 2.2. Release notes theo đúng version

Các ví dụ nên đọc:
- https://maven.apache.org/docs/3.9.0/release-notes.html
- https://maven.apache.org/docs/3.9.16/release-notes.html
- https://maven.apache.org/docs/3.10.0/release-notes.html
- https://maven.apache.org/guides/mini/guide-migration-to-mvn4.html

**Nếu đang nâng từ Maven 3.8.9 lên 3.10.0, không chỉ đọc trang 3.10.0.** Bạn cần xem cả những thay đổi breaking khi đi vào nhánh 3.9 và sau đó vào 3.10. Những sửa lỗi tại 3.9.16 không làm mục breaking changes của 3.9.0 trở nên không liên quan.

### 2.3. All Release Notes, full changelog và issue tracker

Các release notes được tập hợp tại https://maven.apache.org/release-notes-all.html.

Trong mỗi trang:
- Đọc release notes overview.
- Đọc **Known Issues**.
- Đọc **Potentially Breaking Core Changes**.
- Theo **Full changelog/GitHub release** nếu một issue liên quan đến lỗi của dự án.
- Kiểm tra xem fix đã nằm ở version đích hay chỉ mới merged/chưa release.
- Xem các khuyến nghị riêng dành cho users đang đi từ một version series cụ thể.

Một issue có chữ “resolver” không tự động chứng minh nó giải thích mọi failure ở dependency resolution. Cần version, triệu chứng, điều kiện kích hoạt và reproduction phù hợp.

### 2.4. Maven plugin release notes là nguồn riêng

**Maven Core ≠ Maven Plugins.** Cập nhật Maven từ 3.9 lên 3.10 không có nghĩa tất cả Maven Compiler/Surefire/JAR/Deploy Plugins trong POM cũng được cập nhật.

Kiểm tra cả:
- Maven Compiler Plugin, Maven Surefire và Failsafe.
- Maven Resources Plugin và các plugin package JAR/WAR/Shade/Assembly.
- Install/Deploy/Release Plugins.
- Maven Enforcer Plugin, JaCoCo, Checkstyle, PMD, SpotBugs.
- Company/internal plugins và `.mvn/extensions.xml`.
- Maven Wrapper Plugin nếu dự án ghim tool version bằng wrapper.

**Đừng gộp việc nâng Maven Core, JDK, mọi dependencies và plugins vào một thay đổi lớn** nếu có thể tách. Khi lỗi xuất hiện, thay ít biến cùng lúc giúp xác định nguyên nhân dễ hơn.

## 3. Đọc release notes theo các cấp độ rủi ro

| Phần tài liệu | Câu hỏi cần trả lời | Quyết định có thể dẫn đến |
| --- | --- | --- |
| Required Java Version | Maven mới chạy trên JDK nào? | Block upgrade nếu CI không có JDK |
| Potentially Breaking Changes | API/config/default nào đổi? | Tạo testcase migration cụ thể |
| Known Issues | Known bug có trùng hệ thống của ta? | Đổi version/canary hoặc trì hoãn |
| Security Hardening | Repository auth/extension có bị siết? | Test lại server IDs, TLS, origin |
| Notable Features | Behavior/default nào dù không gọi là breaking? | So artifacts, classpath, outputs |
| Deprecations | Cấu hình nào đang sống nhờ behavior cũ? | Sửa POM/plugin trước khi nâng major |
| Plugin Validation | Cảnh báo plugin tự viết/cũ? | Nâng plugin hoặc sửa integration |
| Full Changelog | Có fix liên quan symptoms đặc thù không? | Đối chiếu issue và test |
| Migration Guide | Có thứ tự prepare-test-migrate? | Chia phase, giữ rollback |
| Release History | Stable hay prerelease? Có support không? | Chọn đúng candidate |

### 3.1. Severity nên phân loại thế nào?

- **BLOCKING:** Maven không chạy vì JDK requirement; build/required test fail; lỗi auth/repository; artifact sai contract; known issue ảnh hưởng trực tiếp release pipeline.
- **HIGH RISK:** thay dependency/classpath/order, POM validation, plugin API, deploy semantics hoặc security origin mà chưa thử được.
- **ACTIONABLE WARNING:** plugin deprecated, duplicated configuration hoặc unsupported plugin API có thể chưa gây fail trên baseline nhưng nên sửa.
- **INFORMATIONAL:** log/format/performance improvements không gây break trong các use cases đã kiểm chứng.

**Không thể đánh giá mức độ nghiêm trọng chỉ từ từ WARNING/ERROR trong log.** Một warning về duplicate plugin trong Maven cũ có thể trở thành model error ở bản mới; một breaking change liên quan deploy có thể không bộc lộ trong `mvn test`.

### 3.2. Mẫu ghi nhận một finding

```text
Upgrade path: Maven 3.9.16 -> 3.10.0
Official source: 3.10.0 release notes, Potentially Breaking
Change: stricter POM model validation
Potentially affected: parent pom.xml, build.plugins
Symptom: duplicate plugin declaration once warned, now fails model
Risk: required CI gate blocks all modules
Mitigation: merge duplicated plugin declarations
Evidence needed: baseline warning + candidate clean verify
Owner: build maintainers
Gate: full reactor, JUnit/IT, quality, packaging
Decision: NO-GO until POM fixed and verification passes
Rollback: restore previous Maven Wrapper/CI distribution
```

Đây là **mẫu báo cáo**, không phải kết quả của một lần chạy thật. Có thể dùng cho từng entry trong upgrade risk register.

## 4. Các cảnh báo quan trọng khi nâng Maven 3.8 lên 3.9

### 4.1. Resolver transport: Wagon → native HTTP

Theo release notes Maven 3.9.0, Maven Resolver thay default transport sang **native HTTP**. Một project vốn tải qua corporate proxy hoặc private Maven repository có thể thấy behavior khác.

Tình huống có rủi ro:
- Custom Wagon transport extension.
- Proxy/firewall, TLS certificate trust.
- Mirror/credential configuration trong `settings.xml`.
- Repository manager có hành vi HTTP đặc biệt.
- Scripts so log/metadata gắn chặt với transport cũ.

Nếu nhận 401, timeout hoặc TLS failure sau upgrade, kiểm tra **mirror URL, server ID, proxy, CA/truststore và transport config**, không tự tắt HTTPS verification hoặc hardcode token vào POM.

### 4.2. plexus-utils không còn được inject ngầm

Các Maven plugins đời cũ có thể dựa vào `plexus-utils` mà không khai báo dependency, vì Maven đã từng inject thư viện vào plugin classpath.

Từ Maven 3.9, behavior tương thích ngầm này bị bỏ. Dấu hiệu có thể là:
- `NoClassDefFoundError`.
- Plugin invocation fail trong một Mojo.
- Plugin hoạt động trên Maven 3.8 nhưng lỗi khi chạy Maven 3.9.

**Hướng sửa:** nâng plugin lên bản đã khai báo dependencies chính xác; nếu là custom plugin, thêm explicit Maven plugin dependency và integration test. Không tự chèn `plexus-utils` vào mọi application dependency section vì đây là vấn đề **plugin classpath**, không phải Java business code.

### 4.3. RepositorySystem API cũ

Một số plugins/extensions tự bootstrap `RepositorySystem` bằng API/ServiceLocator cũ. Maven 3.9 ngăn cách làm đó; plugin cần dùng instance do Maven cung cấp.

Khi thấy stack trace liên quan Maven Resolver, hãy xác định **plugin artifact/version** gây lỗi, đọc issue tương ứng rồi sửa theo API được hỗ trợ. Nâng Maven liên tục lên version mới hơn không bảo đảm plugin custom sẽ tự tương thích.

### 4.4. .mvn/maven.config: một dòng một CLI argument

Release notes nhấn mạnh: trong Maven 3.9, **mỗi dòng của `.mvn/maven.config` được hiểu là một argument**.

Ví dụ không nên giữ theo giả định cũ:

```text
-B -ntp -Pci
```

Để phù hợp với cách phân tích argument của Maven 3.9:

```text
-B
-ntp
-Pci
```

Mỗi dòng là **một argument độc lập**; với option có value, kiểm tra cú pháp chính xác theo version. Đừng dựa vào việc shell parse những file này giống cách nó parse một command line.

Một IDE importer, Maven Wrapper và CI pipeline cùng dùng `.mvn/maven.config` có thể đều bị ảnh hưởng. Nên xem file trước khi nâng chứ không chờ build fail mới đọc.

### 4.5. Properties, warnings và plugin validation

Maven 3.9 dọn dẹp cách xử lý user/system properties và bổ sung **plugin validation** báo plugin dùng API hoặc conventions không được hỗ trợ.

Phân biệt:
- Một lỗi Java compile thực tế.
- Plugin configuration sai.
- Deprecated/unsupported Maven internal API trong plugin/extension.
- Cảnh báo property behavior/CLI khác.
- Warning từ một plugin tự sinh khác Maven core.

**Tắt warning logging không sửa plugin.** Hãy tìm artifactId/version, upstream issue, API được hỗ trợ, rồi nâng đúng plugin tương thích với target Maven.

### 4.6. Vì sao phải đọc cả notes 3.9.0 và 3.9.16?

Một trang patch release mới có thể chỉ nêu regression fixes của patch gần nhất. Nhưng khi người dùng **đi từ 3.8.x**, các breaking changes phát sinh từ **3.9.0** vẫn còn hiệu lực. Không được chỉ xem ghi chú “No known issues” của patch mới và suy ra toàn bộ migration không có rủi ro.

## 5. Các thay đổi cần đọc kỹ trước Maven 3.9 → 3.10.0

Maven 3.10.0 dùng **Resolver 2.x**, vẫn cho phép chạy Maven Core với **Java 8+** giống nhánh 3.9. Tuy nhiên release notes có những điểm có thể gây build khác biệt đáng kể.

### 5.1. Stricter POM validation

Maven 3.10.0 nâng mức validation: nhiều POM warnings cũ trở thành lỗi.

Những nhóm cần kiểm tra:
- Duplicate plugin declarations.
- Version string có ký tự không hợp lệ.
- SNAPSHOT version sai format.
- Repository ID malformed/reserved.
- Parent `relativePath` không hợp lệ.
- Artifact/metadata coordinates bị Resolver từ chối.

**Phản ví dụ** trong một `<build><plugins>`:

```xml
<!-- SAI: hai declarations cho cùng một plugin -->
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
```

Hợp nhất thành một declaration:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.14.1</version>
    <configuration>
        <release>17</release>
    </configuration>
</plugin>
```

Đây chỉ là các snippets trong `<plugins>`, **không phải POM độc lập**.

Release notes đề cập workaround `-Dmaven.resolver.validation=off`. Chỉ dùng để **khoanh vùng nguyên nhân** trong môi trường chẩn đoán; không dùng để ép một release gate PASS bằng cách tắt kiểm tra mô hình sai. Fix POM và kiểm tra lại khi không còn workaround.

### 5.2. Classpath ordering đổi theo Resolver 2.x

Dependency graph traversal/classpath order có thể đổi từ **pre-order/depth-first** sang **level-order/breadth-first**. Khi có duplicate classes, resources hoặc dependency convergence issue, cùng source có thể chạy khác.

Dấu hiệu:
- Runtime dùng class/resource khác.
- `NoSuchMethodError`, `ClassCastException`, `ServiceLoader` issue.
- Unit/integration tests chỉ fail ở Maven candidate.
- `dependency:tree` có cùng các modules nhưng thứ tự/classpath khác.

Release notes có flag điều tra:

```bash
mvn -Daether.system.dependencyVisitor=preOrder clean verify
```

Đây là **temporary compatibility experiment**, không phải fix dài hạn cho duplicate classes hoặc conflicting dependency versions. Cần sửa dependency convergence/exclusions và test runtime behavior.

### 5.3. Super POM defaults thay đổi

Maven 3.10.0:
- Bỏ deprecated `release-profile` trong Super POM.
- Thay đổi default plugin management ở Super POM.
- Cấp default UTF-8 source/reporting encoding.
- Cấp default `project.build.outputTimestamp` để các plugins hỗ trợ tạo reproducible archive entry timestamps.

Tác động:
- Project không pin plugin version có thể resolve default khác.
- Bytes của JAR/WAR/ZIP có thể thay đổi do archive metadata.
- Release workflows từng dựa vào old release profile cần cấu hình release profile tường minh.
- Một test đọc ZIP entry timestamps có thể thấy mốc khác.

**Reproducibility mode không đồng nghĩa mọi build byte-for-byte identical.** Compiler JDK, plugins, generated resources, archive ordering và input dependencies vẫn có thể khác.

### 5.4. Credential origin binding là thay đổi bảo mật

Maven 3.10.0 ràng buộc credentials của `settings.xml/server` với repository/mirror origin thích hợp. Cấu hình ID/URL không chuẩn có thể gặp authentication behavior mới.

Đọc docs về `<repositoryOrigins>` nếu project có mirror/proxy phức tạp. Khi CI gặp 401/403:
1. So effective server/repository/mirror IDs.
2. Kiểm tra endpoint scheme/host/port đúng.
3. Xem CI secret injection và token scope.
4. Không ghi token trong POM, CLI args hay debug logs.
5. Dùng HTTPS/TLS và policy quyền tối thiểu.

**Đây là một hardening quan trọng**, không nên tắt kiểm tra để gửi credentials đến host không rõ nguồn.

### 5.5. Toolchains và reactor summary

Maven 3.10.0 cũng thay đổi:
- Một requested toolchain không phù hợp có thể **FAIL** rõ ràng thay vì silently fallback.
- Reactor summary được cải thiện để hiển thị modules và SKIPPED status rõ hơn.
- User/installation-wide extensions được hỗ trợ, bên cạnh project `.mvn/extensions.xml`.
- Một số thuộc tính root/session directories được hỗ trợ public.
- Resolver 2.x thêm chính sách filtering/metadata validation.

Điều này đặc biệt đáng đọc khi máy local/IDE có extension/plugin khác CI, hoặc build dùng Maven Toolchains để chọn compiler JDK không trùng JDK chạy Maven.

### 5.6. Ma trận kiểm tra Maven 3.10

| Change | Rủi ro chính | Phép kiểm tra |
| --- | --- | --- |
| Stricter POM validation | Build fail trước compile | `validate`, sửa model warnings |
| Resolver 2.x | Dependency/metadata resolution | `dependency:tree`, GAV, classpath |
| Classpath ordering | Duplicate classes/resources | Integration tests, diffoscope |
| Super POM | Plugin/default thay đổi | `help:effective-pom` |
| outputTimestamp default | JAR bytes/ZIP times khác | SHA-256, ZIP metadata |
| Credential origin binding | Auth không tới đúng origin | Settings ID/origin, private repo sandbox |
| Toolchains stricter | JDK requested missing | Toolchain config, JDK logs |
| Extensions | Plugin behavior local/CI khác | User/install/project extension scope |
| Reactor summary | Báo nhiều SKIPPED hơn | Không coi SKIPPED là PASS |

## 6. Khi chuẩn bị Maven 4: đọc migration guide theo ba giai đoạn

Apache Maven đề xuất:

1. **Prepare:** đảm bảo project build trên Maven 3 phiên bản phù hợp, sửa warnings, cập nhật plugins lên bản **vẫn tương thích Maven 3**.
2. **Test:** chạy Maven 4 song song với Maven 3, sửa những incompatibilities tối thiểu mà vẫn duy trì Maven 3 build.
3. **Migrate:** khi đã bỏ Maven 3 mới dùng các features Maven 4-specific như POM model 4.1.0.

**Java 17 là minimum runtime để chạy Maven 4.** Điều đó không có nghĩa Maven 4 chỉ biên dịch được Java source target 17; compiler/toolchains có thể target Java phiên bản khác tùy plugin/JDK.

Những thay đổi cần đánh dấu:
- Duplicate plugin entries và model validation nghiêm hơn.
- Một số directory properties nội bộ bị thay/loại.
- Plugin executions bind vào `pre-integration-test`, `post-integration-test` hoặc lifecycle phases đặc biệt có thể cần migration.
- Install/Deploy defaults như `installAtEnd`/`deployAtEnd`.
- Maven 4 model version 4.1.0 và `<subprojects>` là **tính năng migration tùy chọn về sau**, không nên ép vào POM khi production còn phải chạy Maven 3.
- Maven plugins dùng API Maven 2/3 cũ có thể cần update riêng.

### 6.1. Beta/RC không phải production target mặc định

Trước khi quyết định dùng Maven 4 phải kiểm tra Maven Releases History xem bản đích đã GA chưa, các known issues nào chưa giải quyết và CI plugins có hỗ trợ hay chưa. Khi còn là RC, sử dụng trong **compatibility test lane** là phù hợp; đổi Maven Wrapper/production CI lên RC cần policy chấp thuận đặc biệt.

### 6.2. Không nâng plugin vô điều kiện

Một plugin có major version mới có thể đòi Maven 4. Nếu production vẫn đang dùng Maven 3, cần chọn phiên bản plugin tương thích Maven 3. Tốt nhất:
- Stage 1: nâng plugins trong phạm vi Maven 3-compatible.
- Stage 2: thử Maven 4 trên cùng POM.
- Stage 3: sau khi chốt migration mới dùng Maven 4-only plugin features.

**Version lớn hơn không có nghĩa compatible với Core cũ.** Kiểm tra chính release notes của plugin.

## 7. Đo baseline trước khi thử candidate

Một upgrade có kiểm soát bắt đầu bằng **bằng chứng baseline**, không bắt đầu bằng thay version trong CI.

Ghi:
- Git SHA/tag và working tree.
- Maven version qua `mvn -version`.
- JDK runtime của Maven; không chỉ `java -version`.
- Maven Wrapper distribution URL/version.
- User/global settings paths, mirror/proxy/server IDs **không chứa secrets**.
- Active profiles, `.mvn/maven.config`, `.mvn/extensions.xml`.
- Exact `clean verify` command và CI flags.
- Reactor modules, test counts, Failsafe/quality goals.
- Dependencies/plugins versions và effective POM.
- Build logs, reports, artifact hashes, known warnings.
- Quyền rollback và owner.

**Một phép so chỉ có giá trị nếu có kiểm soát biến:** cùng source, cùng Maven plugin/dependency versions, cùng JDK/OS khi muốn cô lập ảnh hưởng của Maven Core. Khi nâng JDK/plugin là bắt buộc, ghi nó thành một migration sub-step rõ ràng.

## 8. Project mẫu Java 17: một bộ kiểm chứng Maven đơn giản

Bài lab cố ý **không dùng repository private, release credentials hoặc deploy**. Mục tiêu là tạo một project có kết quả chức năng đã biết trước, sau đó chạy bằng Maven baseline và candidate.

### 8.1. Cấu trúc file

```text
maven-upgrade-lab/
├── pom.xml
└── src/
    ├── main/java/dev/course/
    │   ├── Greeting.java
    │   └── App.java
    └── test/java/dev/course/
        └── GreetingTest.java
```

Yêu cầu: Java 17+, Maven 3.9.x/3.10.x được cài đúng, access repository cho plugins và JUnit nếu local cache trống.

### 8.2. POM hoàn chỉnh

Tạo `maven-upgrade-lab/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.course</groupId>
    <artifactId>maven-upgrade-lab</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.build.outputTimestamp>2025-01-01T00:00:00Z</project.build.outputTimestamp>
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
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
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
                        <id>enforce-minimum-runtime</id>
                        <phase>validate</phase>
                        <goals>
                            <goal>enforce</goal>
                        </goals>
                        <configuration>
                            <rules>
                                <requireMavenVersion>
                                    <version>[3.9.0,)</version>
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
```

**Vì sao cấu hình này hữu ích cho lab?**
- Ghim các plugin versions để không phụ thuộc ngầm vào default khác của Super POM baseline/candidate.
- Maven Enforcer kiểm tra Maven tối thiểu và Java 17+ ngay từ phase `validate`.
- Range `[3.9.0,)` chỉ kiểm tra **minimum**, không khẳng định Maven 4 tự động compatible.
- Surefire `failIfNoTests=true` tránh test discovery bị bỏ qua mà vẫn báo xanh.
- Cố định outputTimestamp để hạn chế khác biệt ZIP entry times nếu plugin hỗ trợ.
- Không có `distributionManagement`, không deploy artifact.
- Mục tiêu là học cách so Core Maven, không đồng thời thay toàn bộ plugin versions.

### 8.3. Greeting.java

Tạo `src/main/java/dev/course/Greeting.java`:

```java
package dev.course;

public final class Greeting {
    private Greeting() {
    }

    public static String say(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                    "Tên không hợp lệ");
        }
        return "Xin chào, " + name.strip() + "!";
    }
}
```

### 8.4. App.java

Tạo `src/main/java/dev/course/App.java`:

```java
package dev.course;

public final class App {
    private App() {
    }

    public static String message() {
        return "UPGRADE_LAB: " + Greeting.say(" Maven ");
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

Stdout **chính xác**:

```text
UPGRADE_LAB: Xin chào, Maven!
```

### 8.5. GreetingTest.java

Tạo `src/test/java/dev/course/GreetingTest.java`:

```java
package dev.course;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreetingTest {
    @Test
    void trimsSpaces() {
        assertEquals("Xin chào, Maven!",
                Greeting.say(" Maven "));
    }

    @Test
    void rejectsBlank() {
        assertThrows(IllegalArgumentException.class,
                () -> Greeting.say("   "));
    }

    @Test
    void rejectsNull() {
        assertThrows(IllegalArgumentException.class,
                () -> Greeting.say(null));
    }

    @Test
    void mainMessageIsStable() {
        assertEquals("UPGRADE_LAB: Xin chào, Maven!",
                App.message());
    }
}
```

Có **4 JUnit Jupiter tests**. Bài lab này không cố tình làm test FAIL trong happy path; những ví dụ POM duplicate/release warning chỉ là các snippets minh họa khác.

## 9. Chạy baseline và candidate với cùng source

### 9.1. Chạy một Maven version

Từ project root:

```bash
mvn -version
java -version
mvn -B -ntp clean verify
java -cp target/classes dev.course.App
```

Với Maven/JDK/dependencies hợp lệ, dấu hiệu mong đợi:

```text
Tests run: 4, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Đoạn trên là **log rút gọn minh họa**, không phải toàn bộ Maven output. Chương trình Java in đúng:

```text
UPGRADE_LAB: Xin chào, Maven!
```

JAR được tạo:

```text
target/maven-upgrade-lab-1.0.0-SNAPSHOT.jar
```

POM không khai báo Main-Class cho JAR, vì thế chạy qua `java -cp target/classes dev.course.App` thay vì giả định `java -jar` hoạt động.

### 9.2. Chuẩn bị hai Maven installations

Ví dụ trên Linux/macOS:

```bash
BASELINE_MVN="/absolute/path/to/apache-maven-3.9.16/bin/mvn"
CANDIDATE_MVN="/absolute/path/to/apache-maven-3.10.0/bin/mvn"

"$BASELINE_MVN" -version
"$CANDIDATE_MVN" -version
```

**Đây là đường dẫn mẫu**, người học phải thay theo máy mình. Không gán hai biến cho cùng binary rồi kết luận đã thử hai versions.

Windows PowerShell:

```powershell
$baseline = "C:\tools\apache-maven-3.9.16\bin\mvn.cmd"
$candidate = "C:\tools\apache-maven-3.10.0\bin\mvn.cmd"

& $baseline -version
& $candidate -version
```

Dùng bản Maven cũ và mới được cài tách rời, cùng JDK 17. Nếu IDE bundled Maven khác, kiểm tra Maven distributions mà IDE thực sự sử dụng, không chỉ terminal PATH.

### 9.3. Build hai lần nhưng giữ logs và exit codes

Script Bash từ project root, giả sử hai biến đường dẫn đã được thiết lập:

```bash
mkdir -p ../upgrade-evidence/baseline
mkdir -p ../upgrade-evidence/candidate

"$BASELINE_MVN" -B -ntp clean verify \
  > ../upgrade-evidence/baseline/build.log 2>&1
baseline_exit=$?

if [ -f target/maven-upgrade-lab-1.0.0-SNAPSHOT.jar ]; then
  cp target/maven-upgrade-lab-1.0.0-SNAPSHOT.jar \
    ../upgrade-evidence/baseline/app.jar
fi

if [ -d target/surefire-reports ]; then
  cp -R target/surefire-reports \
    ../upgrade-evidence/baseline/surefire-reports
fi

"$CANDIDATE_MVN" -B -ntp clean verify \
  > ../upgrade-evidence/candidate/build.log 2>&1
candidate_exit=$?

if [ -f target/maven-upgrade-lab-1.0.0-SNAPSHOT.jar ]; then
  cp target/maven-upgrade-lab-1.0.0-SNAPSHOT.jar \
    ../upgrade-evidence/candidate/app.jar
fi

if [ -d target/surefire-reports ]; then
  cp -R target/surefire-reports \
    ../upgrade-evidence/candidate/surefire-reports
fi

printf 'baseline_exit=%s\ncandidate_exit=%s\n' \
  "$baseline_exit" "$candidate_exit"

test "$baseline_exit" -eq 0 && test "$candidate_exit" -eq 0
```

**Giải thích:**
- `clean` xóa `target`, nên lưu log/JAR/reports **ngoài `target`** để so hai lần.
- `baseline_exit` và `candidate_exit` được giữ ngay sau từng Maven command, không bị `cp` làm ghi đè.
- Các điều kiện `if` chỉ copy file nếu nó tồn tại, nhằm giữ log ngay cả khi build FAIL.
- Gate cuối trả nonzero nếu một trong hai builds FAIL.
- Đây là Bash sample không bật `set -e` trước hai builds; nếu CI dùng `set -e`, cần xử lý shell condition để không mất cơ hội archive failure evidence.
- Production logs có thể chứa thông tin nội bộ. Không upload raw `-X` hoặc credentials.

### 9.4. So artifacts và tests, không chỉ BUILD SUCCESS

Nếu cả hai JAR tồn tại:

```bash
sha256sum ../upgrade-evidence/baseline/app.jar \
          ../upgrade-evidence/candidate/app.jar

cmp ../upgrade-evidence/baseline/app.jar \
    ../upgrade-evidence/candidate/app.jar
```

macOS có thể dùng `shasum -a 256` thay `sha256sum`. `cmp` trả exit code 0 và không in gì nếu bytes giống; nếu khác, nó trả nonzero.

**JAR có thể khác bytes dù code logic và test behavior giống**, do manifest, compiler, ZIP entry metadata hoặc generated files. Khi so upgrades phải xác định mức tương thích tổ chức yêu cầu: behavior/API, test coverage, published artifacts, byte reproducibility.

So reports:
- Cùng tên tests có được discover không?
- Tổng tests có bằng 4 không?
- Có failures, errors, skipped không?
- Test timeouts và flakiness có thay đổi?
- Failsafe integration tests có được bind và chạy tới `verify` trong dự án thật không?

**Một lần verify PASS không đồng nghĩa mọi quality/security tool đều chạy**, chỉ những goals được cấu hình mới chạy.

## 10. Các lệnh để so effective configuration

Chạy trong cả baseline/candidate môi trường:

```bash
mvn -version
mvn -B -ntp help:active-profiles
mvn -B -ntp help:effective-pom
mvn -B -ntp help:effective-settings
mvn -B -ntp dependency:tree
```

Khi so sánh hai distributions, thay `mvn` bằng đường dẫn version-specific tương ứng. Với kiểm tra khắt khe, dùng fully-qualified Maven Help/Dependency Plugin goals và ghim version để không dính plugin prefix resolution.

**Ý nghĩa:**

| Công cụ | Bằng chứng |
| --- | --- |
| `mvn -version` | Maven/JDK/runtime home/OS |
| `help:active-profiles` | Profile nào thực sự active |
| `help:effective-pom` | Super POM defaults, plugin configuration, properties |
| `help:effective-settings` | Mirrors, servers, proxies, local repo (nhạy cảm) |
| `dependency:tree` | Dependency graph và version mediation |
| `target/surefire-reports` | Unit test results thực tế |
| `target/failsafe-reports` | IT results khi Failsafe đã được bind |
| Hash/JAR inspection | Binary, manifest, resource/metadata differences |
| Reactor Summary | Modules SUCCESS/FAILURE/SKIPPED |
| CI exit code | Kết quả gate thật sự |

**Không gửi nguyên effective-settings hoặc `mvn -X` logs có credentials lên issue public.** Maven Help Plugin có tính năng mask passwords ở những modes/versions nhưng không bảo đảm mọi custom plugin/config/output đều an toàn.

## 11. Mô hình CI chạy thử hai phiên bản Maven

Ví dụ GitHub Actions dùng Maven container images theo version. **Đây là template để hiểu migration matrix, cần kiểm tra image tags thật và pin image digest trước khi dùng production.**

```yaml
name: Maven upgrade compatibility

on:
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        maven: ['3.9.16', '3.10.0']
    container:
      image: maven:${{ matrix.maven }}-eclipse-temurin-17

    steps:
      - uses: actions/checkout@v4

      - name: Inspect Maven and Java versions
        run: |
          mvn -version
          java -version

      - name: Full Maven verification
        run: mvn -B -ntp clean verify

      - name: Preserve unit test reports
        if: ${{ always() }}
        uses: actions/upload-artifact@v4
        with:
          name: surefire-${{ matrix.maven }}
          path: '**/target/surefire-reports/'
          if-no-files-found: warn
          retention-days: 7
```

- `fail-fast: false` để vẫn có results baseline khi candidate fail.
- `if: always()` khiến reports có cơ hội được giữ dù build FAIL.
- Không deploy production artifact, không cần release secrets.
- Hai matrix jobs cần cùng commit, JDK 17, plugin/dependency policy.
- A build failure vẫn phải khiến job failed; artifact upload success không làm gate chuyển xanh.
- Nếu organization cần native JUnit test dashboard, phải cấu hình test-report adapter ngoài upload-artifact.
- Check runner/image tags và pin digests, đồng thời review third-party action supply-chain policy.

**Không tự thay Maven Wrapper version ngay sau khi candidate test một lần PASS.** Cần full reactor, integration, quality và release dry-run gate trước rollout.

## 12. Maven Wrapper và Enforcer: khóa điều kiện, không thay release notes

Maven Wrapper dùng `.mvn/wrapper/maven-wrapper.properties` cùng `mvnw`/`mvnw.cmd` để chạy Maven distribution theo project.

Ví dụ URL minh họa:

```properties
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.16/apache-maven-3.9.16-bin.zip
```

Sau khi dự án đã cài wrapper:
```bash
./mvnw -version
./mvnw -B -ntp clean verify
```

Windows:
```powershell
.\mvnw.cmd -version
.\mvnw.cmd -B -ntp clean verify
```

Wrapper ghim Maven distribution, **không tự ghim JDK, settings, repository contents, plugins và OS**. Cần giữ metadata/checksums distribution theo supply-chain policy.

POM lab dùng Enforcer:

```xml
<requireMavenVersion>
    <version>[3.9.0,)</version>
</requireMavenVersion>
<requireJavaVersion>
    <version>[17,)</version>
</requireJavaVersion>
```

Nếu project hiện chỉ cho phép Maven 3, có thể dùng range giới hạn major:

```xml
<requireMavenVersion>
    <version>[3.9.0,4.0.0)</version>
</requireMavenVersion>
```

**Đây là cấu hình thay thế trong POM production Maven 3-only**, không phải snippet cần thêm vào lab khi muốn test Maven 4. Enforcer kiểm tra prerequisites, **không chứng minh mọi plugins tương thích Maven Core mới**.

## 13. Vì sao cần rollback plan trước khi upgrade?

Không nên xoá bản Maven cũ hoặc ghi đè toàn bộ CI image trước khi candidate được duyệt.

Một rollback plan tốt có:
- Commit trước upgrade và commit chứa changes wrapper/CI.
- Maven distribution baseline còn truy cập được.
- Bản settings/profile không chứa secrets trong backup public.
- Test/quality reports và binary output comparison baseline.
- CI pipeline có thể nhanh chóng quay lại Maven version cũ.
- Owner chịu trách nhiệm phát hiện/sửa regression.
- Chính sách phát hành immutable releases: không “test” bằng cách deploy đè một artifact release.

Nếu sau upgrade đã publish artifact lỗi, **rollback Maven binary không tự thu hồi artifact lỗi đó**. Cần xử lý theo quy trình release/incident riêng.

### 13.1. GO criteria

Có thể GO khi:
1. Đã đọc tất cả version-crossing release notes liên quan và known issues.
2. Candidate build PASS trên local/CI, full reactor, không skip tests.
3. Java/Maven/plugin prerequisites được đáp ứng.
4. No blocking plugin validation/POM model/Resolver/repository issue.
5. Dependency graph và application behavior tương thích hoặc difference được duyệt.
6. Packaging/API/ABI/artifact changes được giải thích.
7. Release dry-run/sandbox passes, security/quality gates không bị bỏ.
8. Rollback và monitoring đã có owner.

### 13.2. NO-GO criteria

- Candidate cần tắt tests/validation/TLS để build xanh.
- Runtime Java không đáp ứng Maven Core minimum.
- Corporate mirror không resolve/private repository credentials không hợp lệ.
- Custom plugin/extension vỡ API mà chưa fix.
- POM mới fail validation hoặc dependency classpath gây runtime regression.
- Full reactor chưa chạy hoặc modules bị skip.
- Known issue ảnh hưởng trực tiếp release pipeline.
- Không có cách rollback bản Maven distribution/CI settings.

## 14. Triage warnings và errors thường gặp

| Triệu chứng | Chỗ kiểm tra đầu tiên | Hướng sửa |
| --- | --- | --- |
| 3.8 PASS, 3.9 HTTP timeout | Resolver native HTTP, proxy/TLS | So mirror/transport docs |
| Maven 3.9 plugin NoClassDefFoundError | plexus-utils auto injection removed | Nâng/sửa plugin dependencies |
| Maven 3.9 maven.config parse khác | Mỗi dòng một CLI argument | Tách arguments thành dòng |
| Plugin validation warnings | Plugin/version/API deprecated | Đọc warning và cập nhật plugin |
| 3.10 duplicate plugin error | Model validation stricter | Hợp nhất declarations |
| 3.10 parent relativePath fail | Parent POM path/model check | Sửa relativePath |
| 3.10 dependency behavior khác | Resolver 2.x/classpath ordering | So tree, duplicate classes |
| JAR timestamp/hash khác | Super POM reproducible default | So manifest/ZIP metadata |
| CI 401 sau upgrade | Credential origin binding | Settings server ID/origin |
| 3.10 toolchain error | Requested toolchain không hợp lệ | Cài/chọn đúng JDK |
| Maven 4 chạy trên JDK 11 thất bại | Java 17 runtime requirement | Setup JDK 17+ |
| Maven 4 phase binding fail | Deprecated/removed lifecycle semantics | Dùng migration guide |
| Maven 4 plugin incompatible | Plugin API/prerequisite | Chọn đúng compatible version |
| Local PASS, CI FAIL | Settings/profile/JDK/cache khác | So effective inputs |
| Artifacts khác nhưng unit tests PASS | Packaging/metadata/bytecode | Diff archive + IT |
| CI xanh với skipped tests | skip flags/fail-never | Giữ gates và test count |
| Release bị deploy sai | Lifecycle/deploy config | Test staging, rollback policy |

**Đọc lỗi thật trước khi sửa.** Lệnh `mvn -q` che bớt logs, không thay behavior; `-X` có thể lộ credentials. Ưu tiên logs thường, Help Plugin và issue link từ release notes.

## 15. Checklist cuối trước khi merge PR nâng Maven

- [ ] Tên Maven baseline và candidate đã được ghi rõ.
- [ ] Đã xem release history, GA/RC và support status.
- [ ] Đã đọc release notes tại từng mốc breaking change trung gian.
- [ ] Đã xem Known Issues, Security Hardening, Potentially Breaking, Plugin Validation.
- [ ] Maven Core, Maven plugins, Maven Wrapper, JDK được đánh giá riêng.
- [ ] Đã kiểm tra `.mvn/maven.config` và Maven extensions.
- [ ] Đã kiểm tra minimum Java cho Core và compiler/toolchains.
- [ ] Đã kiểm tra POM duplicate/plugins/parent relativePath và resolved GAVs.
- [ ] Đã so active profiles/effective POM, dependency graph.
- [ ] Đã chạy baseline và candidate trên cùng source/JDK khi có thể.
- [ ] Đã xác minh test count và fail/skip semantics, không chỉ nhìn build xanh.
- [ ] Full reactor, Surefire/Failsafe và quality gates đều thực thi nếu yêu cầu.
- [ ] Đã so artifacts/manifest/metadata/checksums theo acceptance criteria.
- [ ] CI không dùng `-DskipTests`, `-fn` hoặc validation-off làm workaround lâu dài.
- [ ] Private repository credentials không xuất hiện trong POM/log/report.
- [ ] Đã thử wrapper/CI image candidate ở canary hoặc matrix.
- [ ] Có risk owner, GO/NO-GO decision và rollback binary/config.
- [ ] Không deploy production artifacts trong thử nghiệm migration.
- [ ] Sau merge có monitoring cho những builds đầu tiên.

## 16. Bài tập tự kiểm tra

1. Tại sao phải đọc cả Maven 3.9.0 notes khi nâng từ 3.8 lên 3.9.16?
2. Phân biệt Maven Core release notes với Surefire Plugin release notes.
3. `Known Issues` khác `Potentially Breaking Changes` như thế nào?
4. Native HTTP transport thay đổi điều gì trong Maven 3.9?
5. Vì sao một plugin cũ phụ thuộc plexus-utils có thể vỡ?
6. `.mvn/maven.config` mỗi dòng là một argument nghĩa là gì?
7. Plugin validation warning nên triage thế nào?
8. Maven 3.10 nâng validation của POM theo hướng nào?
9. Vì sao duplicate plugin declarations cần hợp nhất?
10. Resolver 2.x có thể làm classpath ordering khác thế nào?
11. `-Daether.system.dependencyVisitor=preOrder` giải quyết root cause hay chỉ là thử nghiệm?
12. Super POM Maven 3.10 thay đổi những default gì?
13. Repository credentials origin binding giảm nguy cơ nào?
14. Maven 4 đòi minimum Java runtime bao nhiêu?
15. Vì sao compiler release 17 không đồng nghĩa JDK Maven Core luôn là 17?
16. Tạo POM, Greeting.java, App.java và GreetingTest.java từ bài.
17. Chạy đủ 4 tests, xác nhận stdout `UPGRADE_LAB: Xin chào, Maven!`.
18. Vì sao nên pin Maven plugins trước khi so Core versions?
19. Vì sao phải cất output reference ngoài `target` khi dùng `clean`?
20. So SHA-256 giữa baseline và candidate, khi khác phải kiểm tra gì?
21. Khi CI 401 sau upgrade, vì sao không nên đưa token vào URL POM?
22. Enforcer version range có tự chứng nhận Maven 4 compatibility không?
23. Vì sao `-fn` gây nguy hiểm cho acceptance gate?
24. Một matrix có `fail-fast: false` giúp thu evidence thế nào?
25. Maven Wrapper pin được gì và không pin được gì?
26. Khi dùng Maven 4 RC, vì sao cần chạy song song trước đổi wrapper production?
27. Lập bảng risk assessment cho duplicate POM plugin.
28. Một lỗi JAR byte difference nên phân loại ra sao nếu policy bắt buộc reproducible?
29. Nếu candidate chỉ PASS với validation-off, GO hay NO-GO?
30. Tạo một rollback plan cụ thể cho CI.
31. Nếu đã deploy một artifact lỗi, rollback tool version có tự rút artifact không?
32. Nếu release notes không liệt kê issue gặp phải, bước điều tra tiếp theo là gì?

## 17. Tổng kết

Để nâng Maven an toàn, cần **đọc version-specific release notes theo đường nâng cấp thực tế**, không chỉ xem danh sách tính năng mới của version đích.

- Maven 3.8 → 3.9: chú ý native HTTP resolver, plugin APIs, `plexus-utils` và `.mvn/maven.config`.
- Maven 3.9 → 3.10: chú ý Resolver 2.x, stricter POM validation, classpath ordering, Super POM/reproducible builds và credential origin binding.
- Maven 3 → 4: Java 17 runtime và lộ trình **prepare → test in parallel → migrate**.

Một phép nâng cấp đáng tin phải có **baseline, candidate, same commit, test/quality gates, effective model, artifact comparison và rollback**. Đừng “sửa” upgrade bằng cách tắt tests hoặc tắt những cơ chế validation/bảo mật.

Dự án Java 17 trong bài chạy **4 JUnit tests** và in chính xác:

```text
UPGRADE_LAB: Xin chào, Maven!
```

**Maven mới không tự đồng nghĩa với build tốt hơn cho project của bạn. Chỉ có kiểm chứng tương thích và hiểu rõ cảnh báo mới cho phép quyết định nâng cấp có căn cứ.**

## 18. Tài liệu tham khảo chính thức

- [Apache Maven — Releases History](https://maven.apache.org/docs/history.html)
- [Apache Maven — Complete Release Notes](https://maven.apache.org/release-notes-all.html)
- [Apache Maven 3.9.0 Release Notes](https://maven.apache.org/docs/3.9.0/release-notes.html)
- [Apache Maven 3.9.16 Release Notes](https://maven.apache.org/docs/3.9.16/release-notes.html)
- [Apache Maven 3.10.0 Release Notes](https://maven.apache.org/docs/3.10.0/release-notes.html)
- [Apache Maven — Starting with Maven 4](https://maven.apache.org/guides/mini/guide-migration-to-mvn4.html)
- [Apache Maven — What's New in Maven 4](https://maven.apache.org/whatsnewinmaven4.html)
- [Apache Maven — Maven Wrapper](https://maven.apache.org/tools/mavenwrapper.html)
- [Apache Maven — Maven Wrapper Detailed](https://maven.apache.org/tools/wrapper/)
- [Apache Maven Enforcer — Require Maven Version](https://maven.apache.org/enforcer/enforcer-rules/requireMavenVersion.html)
- [Apache Maven Enforcer — Require Java Version](https://maven.apache.org/enforcer/enforcer-rules/requireJavaVersion.html)
- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html)
- [Apache Maven — Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html)

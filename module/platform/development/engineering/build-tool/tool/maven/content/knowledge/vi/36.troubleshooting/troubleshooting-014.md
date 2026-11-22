# Kiểm tra giả thuyết trước khi xóa cache hoặc bỏ qua bước thất bại trong Maven

## 1. Một Maven build đỏ không tự động chứng minh “cache bị hỏng”

Khi thấy `BUILD FAILURE`, lập trình viên thường thử ba thao tác: chạy `mvn -U`, xóa `~/.m2/repository`, hoặc thêm `-DskipTests` để có JAR. Các thao tác này thay đổi điều kiện build, nhưng **không chứng minh đã xác định hay sửa được nguyên nhân**.

Maven có nhiều lớp có thể thất bại độc lập: cú pháp POM, effective model, parent/BOM, dependency hoặc plugin resolution, credentials/mirror, JDK/toolchains, resource filtering, code generation, Java compiler, Surefire tests, Failsafe integration tests, JAR packaging hoặc CI runtime. Chỉ một số trường hợp liên quan tới cache.

Ba ví dụ:
- `Tests run: 3, Failures: 1` với `expected 135 but was 136` phản ánh **hành vi hoặc assertion** không đúng. Xóa cache không thay đổi phép tính.
- `Could not find artifact x:y:1.0.0 in company-mirror` có thể do artifact chưa publish, sai GAV/mirror, quyền truy cập hoặc kết quả 404 trước đó đã được nhớ.
- `invalid target release: 21` hướng tới **JDK/compiler configuration**, không phải lỗi trong `target/` hay `~/.m2`.

**Mục tiêu:** học cách xây dựng **giả thuyết có thể kiểm chứng**, ghi dự đoán, thử đúng một biến trong môi trường được phép, đánh giá kết quả và chỉ sau đó mới quyết định có cần làm mới cache hay không.

Đây là bài trong nhóm **Chẩn đoán lỗi** của Build Tool Maven. Nó không cổ vũ né test hay phá cache, mà hướng tới kết luận có thể tái hiện và dùng được cho CI/release review.

## 2. Quy trình tư duy điều tra: quan sát → giả thuyết → dự đoán → phép thử

~~~text
Quan sát lỗi và lưu bằng chứng
                 |
                 v
Xác định tầng Maven nào thất bại
                 |
                 v
Nêu giả thuyết H có thể bị bác bỏ
                 |
                 v
Dự đoán: Nếu H đúng, thử T sẽ tạo kết quả gì?
                 |
                 v
Chạy T trong sandbox, chỉ đổi một yếu tố
                 |
          +------+------+
          |             |
     Dự đoán đúng    Dự đoán sai
          |             |
          v             v
  Tăng độ tin cậy   Bác bỏ/chỉnh H
          |             |
          +------+------+
                 |
                 v
Sửa nguyên nhân, chạy full required Maven verification
~~~

Một giả thuyết **quá mơ hồ**: “Lỗi Maven do cache.” Nó không cho biết phải đo gì, so với cái gì.

Giả thuyết **có thể kiểm chứng**: “Artifact `vn.example:lib-api:1.2.0` đã được publish lên đúng mirror nhưng local Maven repository đang nhớ lần nhận 404 trước đó. Nếu giữ Git SHA, POM, JDK, goals và settings không đổi, build dùng repository local mới sẽ resolve được; repository cũ vẫn báo cached missing artifact.”

Nếu repository mới **cũng** trả 404, giả thuyết cache cũ yếu đi; cần kiểm tra GAV, mirror và remote content. Nếu repository mới PASS, vẫn phải kiểm tra timestamps và artifact versions, vì remote có thể vừa thay đổi đúng lúc phép thử.

## 3. Một bug report tốt bắt đầu bằng dữ liệu, không bằng hành động xóa

Trước khi chạy thử thêm, ghi:

~~~bash
git rev-parse --verify HEAD
git status --porcelain=v1 --untracked-files=all
mvn --version
java -version
javac -version
~~~

Ý nghĩa:
- `git rev-parse` cho SHA của HEAD, **không** bao gồm mọi thay đổi chưa commit.
- `git status` cho tracked/untracked changes, nhưng ignored outputs như `target/` có thể vẫn tồn tại.
- `mvn --version` nêu Maven và Java JVM đang chạy Maven.
- `java -version`/`javac -version` từ PATH có thể khác runtime/compiler do toolchains hoặc `JAVA_HOME`.

Ghi tiếp **exact Maven command**, working directory, module/POM path, `-P`/`-D` flags, `-pl`/`-am`, `-s` settings, repository/mirror, Git commit, local vs CI, và dòng lỗi đầu tiên kèm `Caused by`.

Lưu ý một số Maven plugin goals có side effects ngay ở `validate`/`verify`: chỉ chạy trên project tin cậy trong workspace được phép, không dùng release credentials cho PR không tin cậy.

### Log có ích

~~~bash
mvn -B -ntp -e verify
~~~

`-B`: batch, `-ntp`: tắt transfer progress, `-e`: hiện stack traces. `-X` thêm debug nhưng có thể làm lộ URLs, paths, settings/credentials và thông tin nội bộ. **Không đăng công khai nguyên bản `mvn -X` logs**.

Lỗi cuối cùng `BUILD FAILURE` không đủ; hãy tìm Maven goal, error line và lớp `Caused by` cụ thể.

## 4. Phân loại lỗi trước khi đặt giả thuyết

| Lỗi đầu tiên/triệu chứng | Nhóm khả dĩ | Bằng chứng cần đọc trước |
| --- | --- | --- |
| `Non-parseable POM`, XML parser error | XML syntax/model | POM path, line/column, dấu đóng thẻ, `&amp;` |
| `Malformed POM`, `Unrecognised tag` | Maven model | Vị trí `<dependency>`, `<plugin>`, modelVersion |
| `Non-resolvable parent POM` | Parent/model resolution | Parent GAV/`relativePath`, repository |
| `Could not resolve dependencies` | GAV, repo, mirror, cache | Artifact coordinates, HTTP status/URL/id |
| Plugin prefix/goal resolution failure | Plugin resolution | Fully qualified plugin goal, pluginRepositories |
| `invalid target release` | JDK/Compiler Plugin | `mvn --version`, target `release`, toolchains |
| `cannot find symbol` | Java/compile classpath | Compiler log, dependency tree, generated sources |
| `There are test failures` | Unit test/Surefire | Test report, expected/actual, environment |
| Failsafe `verify` failure | Integration test/runtime | Failsafe reports, services, resources |
| `no main manifest attribute` | JAR packaging | Jar Plugin config, `META-INF/MANIFEST.MF` |
| CI-only failure | Source/environment divergence | SHA, profiles, JDK/OS, settings, cache policy |

Một lỗi ở `compiler:compile` có thể là thiếu dependency trong POM **nhưng không phải XML malformed**. Một test fail có thể là regression thực hoặc fixture sai. Đừng chụp mũ “cache” cho mọi dòng `[ERROR]`.

## 5. Phân biệt bốn lớp cache khác nhau

| Lớp | Mục đích | Phép kiểm tra phù hợp |
| --- | --- | --- |
| **Maven local repository** (`~/.m2/repository` thông thường) | Artifacts tải về, metadata, artifacts cài bằng `install` | Isolated local repo, logs resolver, GAV |
| **Build outputs** (`target/`) | `.class`, generated sources, resources, JAR, reports | Clean build trong workspace an toàn |
| **IDE incremental cache** | Compiler/project model/indexing/classpath | Reload Maven Project, so CLI |
| **CI/repository-manager cache** | Artifacts giữa jobs hoặc proxy upstream | CI cache key, mirror/backend logs, controlled bypass |

**`mvn clean` không xóa Maven local repository** theo mặc định; nó dọn build outputs, thường dưới `target`. Ngược lại, xóa `~/.m2/repository` không chắc sửa `target/classes` đang cũ.

Đặc biệt `.m2` không đơn thuần là một folder “download lại được”: local repository còn có artifacts vừa `mvn install` và có thể **chưa tồn tại trên bất kỳ remote repository nào**. Thư mục `.m2` cũng thường chứa `settings.xml`/`toolchains.xml`; xóa cả `.m2` còn gây mất cấu hình.

## 6. Vì sao xóa bừa local repository là thao tác rủi ro?

- Mất artifact nội bộ chỉ được install local.
- Tải lại lượng lớn plugins/dependencies gây chậm và áp lực lên repository manager.
- SNAPSHOT có thể được thay bằng bytes mới, làm build không còn cùng input với lúc fail.
- Những Maven processes khác có thể đang dùng shared cache.
- Mất bằng chứng cần so sánh artifact cũ/mới, metadata và lỗi trước đó.
- Mất khả năng build offline khi mạng gián đoạn.
- “Chạy lại thành công” trở thành kết luận yếu vì đã đổi đồng thời input và cache.

Apache Maven Resolver hiện lưu metadata và có cơ chế phối hợp nhiều processes; local repository **không nên bị quản lý bằng thao tác file trực tiếp như một API ổn định**. Khi cần làm mới dependency, ưu tiên kiểm tra GAV và dùng tooling/isolated repository có phạm vi.

**Không chạy `Remove-Item -Recurse`, `rm -rf`, `git clean -fdx` hoặc `git reset --hard` trên workspace chung** chỉ để “thử xem”. Những lệnh đó có thể làm mất dữ liệu chưa commit hoặc artifacts người khác đang dùng.

## 7. `.lastUpdated` và negative cache: đọc đúng cơ chế

Khi Maven Resolver không resolve được artifact/metadata, policy có thể ghi metadata với suffix **`.lastUpdated`**, đặc biệt với **not-found**. Maven Resolver phân biệt:
1. **Not found** — artifact/metadata không tồn tại ở repository đang được hỏi.
2. **Other resolution errors** — authentication, timeout, transport, TLS, v.v.

Trong Maven 3, loại not-found thường được cache theo mặc định; các lỗi khác có chính sách cache khác. Maven 4 có thêm tùy chọn liên quan negative cache. **Không suy mọi file `.lastUpdated` là bằng chứng corruption**.

Kịch bản minh họa:

~~~text
09:00 repo trả 404 cho x:y:1.0.0
09:02 local repository ghi nhận cached miss
09:10 publisher đưa x:y:1.0.0 lên đúng repo
09:12 Maven vẫn có thể dùng cached not-found theo policy
09:15 thử refresh có kiểm soát hoặc local repo mới
~~~

Thời điểm chỉ dùng để minh họa. Trước khi đụng cache, kiểm tra **x:y:1.0.0 có thực sự tồn tại ở mirror mà Maven dùng không**, có đúng quyền không và remote policy nào đang áp dụng.

**Đừng xóa hàng loạt `.lastUpdated` files** để “giải quyết mọi 404”. Nó không sửa artifact chưa được publish, GAV bị gõ sai hay HTTP 403.

## 8. `-U` không phải “nút làm sạch Maven”

Maven CLI định nghĩa `-U`/`--update-snapshots` là **buộc kiểm tra remote đối với missing releases và updated snapshots**. Tùy Maven/Resolver version còn có các tùy chọn bổ sung; vì vậy tham chiếu đúng CLI đang chạy.

Ví dụ:

~~~bash
mvn -B -ntp verify
mvn -B -ntp -U verify
~~~

Nếu lỗi đầu là **cached missing artifact** và lần có `-U` resolve được, update-policy/negative-cache hypothesis được ủng hộ. Nhưng:
- Không có nghĩa mọi JAR cache cũ đều corrupt.
- Không sửa POM XML malformed.
- Không chữa Java compiler/JUnit assertions.
- Không cấp quyền cho HTTP 401/403.
- Không bảo đảm repository server đang online.
- Có thể khiến Maven tải SNAPSHOT mới, thay input của build.

Vì vậy **chụp log/versions trước khi dùng `-U`**, đừng đặt `-U` mặc định cho mọi lần build chỉ để “yên tâm”.

## 9. `-o` là offline, không phải phép thử chứng minh repository tốt

Lệnh:

~~~bash
mvn -B -ntp -o verify
~~~

buộc Maven làm việc offline. Kết quả:
- **PASS offline:** đủ artifacts cần thiết được resolve từ local data cho invocation đó; không chứng minh remote repository hiện có và không bị thay.
- **FAIL offline vì artifact thiếu:** có thể đơn giản là dependency/plugin chưa có local, không phải cache hỏng.
- **FAIL test offline:** vẫn có thể là test logic/env như khi online; không vì offline mà chuyển thành lỗi resolution.

**Không so hai phép thử online/offline mà bỏ qua thay đổi đầu vào khác**. Để điều tra thật, ghi chính xác missing GAV và error category.

## 10. Phép thử local repo mới: không xóa repo hiện tại

Nếu nghi data/metadata trong local repo hiện tại gây lỗi, thử **fresh local repository** trong **sandbox riêng**.

Linux/macOS, tại thư mục dự án sandbox:

~~~bash
mvn -B -ntp verify
mvn -B -ntp -Dmaven.repo.local=../m2-diagnostic-fresh verify
~~~

Windows PowerShell:

~~~powershell
mvn -B -ntp verify
mvn -B -ntp "-Dmaven.repo.local=..\m2-diagnostic-fresh" verify
~~~

**Yêu cầu trước khi thử:** folder `../m2-diagnostic-fresh` chưa được dùng bởi người khác, được đặt trong không gian thuộc quyền của bài thử và có kết nối repo được phép. Fresh repo có thể phải tải nhiều dependencies/plugins.

**Giữ các biến còn lại**: Git SHA, POM, Maven/JDK, settings, goals, profiles, network/mirror. Nếu hai runs cách nhau quá lâu, trạng thái remote có thể đổi; ghi cả thời điểm.

| Repo cũ | Repo mới | Hướng suy luận |
| --- | --- | --- |
| FAIL resolve, báo cached 404 | PASS | Nghi stale negative cache hoặc dữ liệu local khác; so GAV, remote, timestamps |
| FAIL resolve | FAIL cùng GAV/URL | Nghi artifact chưa có, wrong mirror/auth, không chỉ cache |
| PASS | FAIL | Repo mới còn thiếu artifacts, mạng/proxy hoặc offline policy |
| FAIL JUnit assertion | FAIL cùng assertion | Logic/test env có khả năng hơn dependency cache |
| PASS | PASS | Không tái hiện lỗi hiện tại; cần tái dựng điều kiện ban đầu |

**Nếu repo mới PASS không có nghĩa xóa repo cũ ngay là hành động đúng.** Kiểm tra versions/digests được tải, local installed artifacts và repository statuses trước khi kết luận.

## 11. `clean` vs fresh repo: hai phép thử cho hai giả thuyết khác nhau

Giả thuyết **stale build output**:
- Một class được sửa nhưng IDE hoặc incremental build đang dùng `.class` cũ.
- Generated source hoặc filtered resource còn từ lần trước.
- Thử trên workspace an toàn: `mvn clean verify`.
- Nếu clean giải quyết lỗi, điều tra logic incremental codegen/resource.

Giả thuyết **wrong dependency cache**:
- Maven chọn artifact bytes hoặc negative-cache metadata không đúng.
- Giữ goals/source/JDK và **đổi duy nhất local repo path**.
- Nếu lỗi chỉ xuất hiện ở repo cũ, so artifact versions, repository origin và log.

Giả thuyết **test logic fail**:
- Test expected/actual không khớp trên cùng code.
- Cả `clean` và repo mới vẫn fail; cần sửa logic hoặc test contract.

**Clean Plugin có thể được cấu hình custom filesets**, nên `mvn clean` không mặc nhiên vô hại trên một project lạ. Dùng checkout/runner tách biệt và lưu test evidence trước khi clean.

## 12. `-DskipTests` thay đổi cổng xác minh, không chữa lỗi

Theo tài liệu Maven Surefire/Failsafe:

| Tùy chọn | Thông thường ảnh hưởng | Cách diễn giải |
| --- | --- | --- |
| `-DskipTests` | Surefire không chạy unit tests; test sources vẫn compile theo plugin support | Chưa có bằng chứng unit tests PASS |
| `-Dmaven.test.skip=true` | Skip **test compilation lẫn test execution** trong Compiler/Surefire/Failsafe theo hỗ trợ | Phạm vi kiểm thử bị thu hẹp hơn |
| `-DskipITs` | Failsafe bỏ chạy integration tests | Không xác minh integration contract |
| `-Dtest=MyTest` | Chạy test class/method được chọn qua Surefire | Hữu ích cô lập, không thay full suite |
| `-Dit.test=MyIT` | Lọc tests Failsafe | Chỉ một nhánh chẩn đoán |
| `-Dmaven.test.failure.ignore=true` | Có thể tiếp tục build khi tests fail | Vẫn có failures; không được báo tests PASS |

Ví dụ:

~~~bash
mvn -B -ntp clean verify
mvn -B -ntp -DskipTests package
mvn -B -ntp -Dmaven.test.skip=true package
~~~

Ba lệnh **không có cùng tiêu chuẩn thành công**, nên việc lệnh thứ hai hiện `BUILD SUCCESS` không bác bỏ lỗi test của lệnh đầu.

Nếu phải bỏ qua một check để điều tra compile/package, đánh dấu trạng thái **`PARTIAL / TESTS SKIPPED`**, ghi lý do và quay lại full required goals trước merge/release.

## 13. Phân biệt Maven test failure với Maven compilation failure

Một failure ở `maven-compiler-plugin:compile` khiến tests có thể **chưa được chạy**. Nguyên nhân có thể là:
- Source Java syntax/type errors.
- Wrong JDK `release`/toolchain.
- Thiếu compile dependency thực trong POM.
- Generated classes chưa sinh.
- Annotation processor lỗi.

Một failure ở `maven-surefire-plugin:test` có nghĩa đã đến phase test, nhưng cần xem:
- Test method nào fail?
- Expected/actual và stack trace nào?
- Exception là assertion, timeout, missing resource, database connection hay test discovery?
- Có `target/surefire-reports/*.xml`/`.txt` của **lượt chạy hiện tại** không?

Một failure ở Failsafe `integration-test`/`verify` lại liên quan integration tests và có reports riêng.

**Đừng sửa test bằng cách tăng skip flag khi nguyên nhân là compiler; và đừng xóa cache khi test assertion là deterministic.**

## 14. Một test bị fail lần đầu rồi pass lần sau: giả thuyết flaky

Flaky tests thường phụ thuộc:
- Wall clock, time zone hoặc locale.
- Random seed chưa chốt.
- Parallelism/thread scheduling.
- Shared static state hoặc DB fixtures chưa cleanup.
- Test execution order.
- External service/network latency.
- CI CPU/memory pressure.

Cách điều tra:
1. Ghi tên test, exception, input seed, JDK và môi trường.
2. Re-run **đúng class** với cùng flags mà không xóa cache xen kẽ.
3. So serial vs parallel nếu POM bật parallel tests.
4. Kiểm tra fixture isolation, clock injection, cleanup.
5. Đọc Surefire reports để biết first-run FAIL vs rerun PASS.
6. Sửa nguyên nhân và chạy full suite/CI.

Maven Surefire hỗ trợ `rerunFailingTestsCount` và ghi nhận flakiness. **Không tăng retry count chỉ để che fail**; việc một test đậu ở lần thứ ba không chứng minh môi trường ổn định hoặc bug đã hết.

## 15. Những vấn đề cần kiểm tra trước khi chỉnh mirror/repository

Khi Maven báo HTTP 401/403, SSL/TLS, timeout hoặc `Could not transfer artifact`:

- Artifact GAV có đúng không?
- Repository `id` và URL nào được Maven dùng?
- `settings.xml` có mirror với `<mirrorOf>*</mirrorOf>` không?
- Credentials/token scope có được cấp cho repository tương ứng không?
- Proxy/VPN/DNS/certificate có phù hợp môi trường không?
- Plugin repository có khác dependency repository không?
- Artifact vừa publish có được internal repository manager proxy/sync chưa?
- `-o`, updatePolicy, SNAPSHOT metadata có ảnh hưởng không?

Một fragment **giả định**:

~~~xml
<mirrors>
    <mirror>
        <id>internal-mirror</id>
        <url>https://repository.example.invalid/maven/</url>
        <mirrorOf>*</mirrorOf>
    </mirror>
</mirrors>
~~~

Domain `.invalid` **không phải địa chỉ chạy thật**. Nếu tổ chức dùng mirror bắt buộc, không bypass nó bằng cách sửa POM sang public Maven Central nhằm né policy. Liên hệ repository admin với logs có redaction và server response thực.

`-U` không cấp token, không sửa URL và không đảm bảo server hết outage. Tránh đưa token vào POM hoặc chia sẻ toàn bộ `settings.xml`.

## 16. Effective POM và dependency graph giúp bác bỏ phỏng đoán

Khi Maven đã resolve được parent/model:

~~~bash
mvn -B -ntp help:effective-pom -Doutput=target/effective-pom.xml
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
~~~

Goal thứ hai là **`dependency:tree`** dưới tên fully-qualified plugin/goal. Nó cho thấy những dependencies thực sự được resolve; còn `dependencyManagement` chỉ quản lý metadata/version, **không tự thêm dependency**.

Effective POM cho biết parent inheritance, imported BOM, profile activation, pluginManagement và defaults đã tác động ra sao. Vì thế không chỉ `grep` một `<version>` trong source POM rồi kết luận Maven đã dùng đúng version đó.

**Nếu parent POM không resolve được**, `help:effective-pom` cũng có thể fail: kiểm tra `<parent>` GAV, `relativePath` và repository trước. Nếu compile fail vì API không có, xem selected dependency tree và `maven.compiler.release`, không mặc định nâng version plugins.

## 17. Maven Wrapper/JDK/profile là những biến không thể bỏ qua

Một báo cáo local PASS – CI FAIL phải so:
1. Git commit SHA và dirty/untracked state.
2. Maven version hoặc Maven Wrapper distribution.
3. JDK version/vendor mà **Maven process** dùng.
4. `maven.compiler.release` và Maven Toolchains.
5. Active profiles, `-D` flags, settings/mirrors.
6. OS/timezone/locale nếu tests phụ thuộc.
7. Reactor module selection, `-pl/-am/-rf`.
8. Local cache origin, CI cache key, network policy.

Ví dụ IDE Project SDK JDK 21 nhưng Maven Runner JDK 17. Một project yêu cầu `release=21` có thể compile trong IDE, nhưng Maven Compiler Plugin trên JDK 17 fail. **Đổi cache không thể bổ sung Java 21 APIs vào javac 17**.

Maven Wrapper chủ yếu chọn Maven distribution, **không tự cài JDK hoặc khóa transitive dependencies**. Sau khi so JDK và POM, mới quyết định xử lý ở runner/toolchain hay source.

## 18. `target/` và IDE cache có thể che lỗi source generation

Một IDE có thể giữ:
- Generated Java sources từ lần build trước.
- Compiled `.class` files cũ.
- Resource đã được filter ở lượt Maven build trước.
- IDE-only library classpath.
- Annotation processing outputs của IDE plugin khác version.

Khi Maven `clean verify` trên checkout sạch thất bại mà IDE Build PASS, kiểm tra:
- `generate-sources` plugin executions/inputs.
- `process-resources` và filtered output tại `target/classes`.
- Compiler Plugin/source root configuration.
- IDE import/Sync Maven Project.
- Local repo artifact versions nếu có bằng chứng resolution khác nhau.

Nếu source `app.version=@project.version@` nhưng runtime đọc literal `@project.version@`, vấn đề có thể là resource filtering **chưa được chạy**, không phải Maven local repository corrupt.

**Không copy generated files bằng tay vào `src/main/java` để che lỗi Maven build**. Sửa codegen goals, schema inputs, plugin version hoặc IDE source roots có chủ đích.

## 19. Reactor multi-module: module bị `SKIPPED` không nhất thiết hỏng

Ví dụ:

~~~text
platform/
├── pom.xml           aggregator
├── core/pom.xml      library
├── api/pom.xml       depends on core
└── service/pom.xml   depends on api
~~~

Khi `core` fail, Maven reactor có thể đánh dấu những modules sau là `SKIPPED`. Chúng **chưa được kiểm chứng**, không phải đã có failure riêng.

Phép thử thu hẹp phạm vi:

~~~bash
mvn -B -ntp -pl :api -am verify
mvn -B -ntp -pl :service -am verify
~~~

`-pl` chọn module, `-am` build reactor dependencies cần thiết; chúng không thay full root verification sau fix.

Option `-rf` resume reactor từ module được chọn, nhưng **có thể phụ thuộc artifacts cũ của modules trước đó**. Một `-rf` PASS không chứng minh toàn reactor được build sạch; cần kiểm tra root `clean verify` khi đó là required gate.

## 20. Artifact quality: có JAR chưa có nghĩa đã qua tests

Maven lifecycle rút gọn:

~~~text
validate -> compile -> test -> package
                            |
                            v
                  integration-test -> verify
                                      |
                                      v
                              install -> deploy
~~~

`mvn package` có thể tạo JAR khi một số gates chạy sau package; `verify` có thể gọi Failsafe/quality plugins **nếu bind đúng**. `install` ghi local repository; `deploy` có thể ghi remote repository và không phải phép thử cache an toàn.

Nếu cần kiểm tra packaging, xem:

~~~bash
jar tf target/your-app.jar
~~~

Đây là lệnh **minh họa**, thay bằng artifact path thực. Kiểm tra manifest, resources và runtime deps đúng loại JAR. Với executable JAR, smoke-test `java -jar`; với library, dùng consumer/API tests.

Khi phát hành cần tính checksum của **artifact cuối** sau khi các plugin đã biến đổi bytes. Trên Linux CI:

~~~bash
sha256sum target/shipping-quote-lab-1.0.0.jar
~~~

Digest là kết quả tính từ file thực, không có một SHA-256 cố định để chép từ tài liệu. **Checksum chứng minh bytes trùng reference**, nhưng không tự chứng minh source commit/provenance nếu thiếu bản ghi đáng tin.

## 21. Demo Java 17: tạo một lỗi có thể dự đoán trước

Project `vn.example.diagnosis:shipping-quote-lab:1.0.0` có một chương trình tính tổng đơn giản, ba JUnit Jupiter tests, Maven Compiler/Surefire/Jar plugins và Enforcer ở validate.

Cấu trúc:

~~~text
shipping-quote-lab/
├── pom.xml
└── src/
    ├── main/java/vn/example/diagnosis/ShippingQuote.java
    └── test/java/vn/example/diagnosis/ShippingQuoteTest.java
~~~

Yêu cầu: **Maven 3.9+**, **JDK 17+**, Maven repository được phép truy cập các dependency/plugin versions chỉ định. Không cần Docker, database hay remote deploy. Chỉ làm thí nghiệm làm hỏng POM/source trong **bản sao sandbox**.

### 21.1. `pom.xml` đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example.diagnosis</groupId>
    <artifactId>shipping-quote-lab</artifactId>
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
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.3.2</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-enforcer-plugin</artifactId>
                <version>3.5.0</version>
                <executions>
                    <execution>
                        <id>require-tools</id>
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

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>vn.example.diagnosis.ShippingQuote</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

POM dùng `modelVersion=4.0.0` tương thích Maven 3. Enforcer xác nhận baseline Maven/JDK; Compiler Plugin target Java 17; Surefire test scope JUnit 5; Jar Plugin tạo executable JAR. **Không có `<distributionManagement>`** vì không làm deploy.

Các con số version được pin là baseline thí nghiệm, không khẳng định các plugins đó mới nhất. Với dự án thật, hãy đối chiếu plugin/JDK requirements và policies trước khi nâng cấp.

### 21.2. `src/main/java/vn/example/diagnosis/ShippingQuote.java`

~~~java
package vn.example.diagnosis;

public final class ShippingQuote {
    private ShippingQuote() {
    }

    public static int total(int subtotal, int shipping) {
        if (subtotal < 0 || shipping < 0) {
            throw new IllegalArgumentException(
                    "Amounts must be non-negative");
        }
        return Math.addExact(subtotal, shipping);
    }

    public static void main(String[] args) {
        System.out.println("TOTAL: " + total(120, 15) + " VND");
    }
}
~~~

`Math.addExact` ném `ArithmeticException` khi phép cộng int overflow, thay vì âm thầm wrap. Hai đối số âm bị từ chối từ đầu, giúp unit tests kiểm tra rõ ràng.

### 21.3. `src/test/java/vn/example/diagnosis/ShippingQuoteTest.java`

~~~java
package vn.example.diagnosis;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ShippingQuoteTest {
    @Test
    void totalIncludesShipping() {
        assertEquals(135, ShippingQuote.total(120, 15));
    }

    @Test
    void rejectsNegativeAmount() {
        assertThrows(IllegalArgumentException.class,
                () -> ShippingQuote.total(-1, 15));
    }

    @Test
    void rejectsOverflow() {
        assertThrows(ArithmeticException.class,
                () -> ShippingQuote.total(Integer.MAX_VALUE, 1));
    }
}
~~~

Đây là **3 deterministic unit tests**, không dùng network, clock, random hay database. Tốt cho phép thử phân biệt bug logic với artifact cache.

## 22. Baseline đầy đủ và stdout chính xác

Từ thư mục demo:

~~~bash
mvn --version
mvn -B -ntp clean verify
java -jar target/shipping-quote-lab-1.0.0.jar
~~~

Khi các files và dependencies đúng:
- Enforcer PASS ở phase validate.
- Compiler Plugin biên dịch Java 17.
- Surefire chạy **3 unit test methods**.
- Jar Plugin package `shipping-quote-lab-1.0.0.jar`.
- Maven dừng tại verify, **không install/deploy**.

**Stdout chính xác của riêng `java -jar` cuối**:

~~~text
TOTAL: 135 VND
~~~

Maven console có thể khác theo môi trường/version. Khi chẩn đoán, xem reports thực tại `target/surefire-reports/` và không dựa vào một transcript log bịa.

## 23. Thí nghiệm 1 — làm lỗi behavior nhưng không làm lỗi compiler

Trong **bản sao** demo, đổi đúng một dòng:

~~~java
return Math.addExact(subtotal, shipping + 1);
~~~

Đoạn trên là mã sai **có chủ đích**.

Dự đoán:
1. Java code vẫn hợp lệ nên compiler có thể PASS.
2. `total(120,15)` bây giờ bằng **136**, không phải 135.
3. Surefire test `totalIncludesShipping` FAIL.
4. Test negative amount và overflow vẫn có thể PASS; đó là lý do cần đọc **số tests/expected/actual**, không chỉ dòng BUILD FAILURE.
5. `-U`, `clean` hay fresh repository **không sửa** công thức cộng sai.

Chạy:

~~~bash
mvn -B -ntp clean verify
~~~

Maven sẽ báo test failure. Assertion message có thể tương tự:

~~~text
expected: <135> but was: <136>
~~~

Đây là mẫu minh họa text JUnit, không hứa exact format của mọi Maven/Surefire version. Điều quan trọng là **assertion expected/actual**.

Để cô lập test mà không bỏ nó:

~~~bash
mvn -B -ntp -Dtest=ShippingQuoteTest test
~~~

Đây chỉ là phép thử một test class; sau fix vẫn chạy đầy đủ required `clean verify`.

## 24. Thí nghiệm 2 — skip test làm package PASS nhưng bug còn nguyên

Giữ một **bản sao có lỗi** ở mục 23, chạy:

~~~bash
mvn -B -ntp -DskipTests package
java -jar target/shipping-quote-lab-1.0.0.jar
~~~

Trong điều kiện dependencies/plugins resolve bình thường, `package` có thể thành công vì assertions không được chạy. **Stdout chính xác của JAR có lỗi**:

~~~text
TOTAL: 136 VND
~~~

So với baseline `TOTAL: 135 VND`, bạn đã có bằng chứng rằng **`-DskipTests` bỏ chặn lỗi chứ không chữa phép tính**. Report phải nói `TESTS SKIPPED`, không nói “3/3 tests PASS”.

Trong sandbox, có thể so thêm:

~~~bash
mvn -B -ntp -Dmaven.test.skip=true package
~~~

Tùy chọn này còn bỏ test compilation theo Maven Compiler/Surefire behavior, nên càng không thể dùng làm release gate.

Sau lab, **khôi phục** `return Math.addExact(subtotal, shipping);` và chạy `mvn clean verify`. Không dùng `git reset --hard` để khôi phục trên workspace nhiều người dùng.

## 25. Thí nghiệm 3 — artifact không tồn tại, không nên xóa local repository

Trên **một bản sao POM sandbox**, thêm một dependency giả dưới `<dependencies>`:

~~~xml
<dependency>
    <groupId>vn.invalid.example</groupId>
    <artifactId>artifact-never-published</artifactId>
    <version>99.0.0</version>
</dependency>
~~~

Đoạn này là **fault injection**, không phải dependency cần giữ trong dự án. Với repositories thông thường, artifact sẽ không tồn tại. Nhưng kiểm tra URL/server thực thay vì giả định bất cứ private repository nào cũng không có GAV ấy.

Dự đoán:
- Maven đọc POM hợp lệ nhưng fail khi resolve dependency.
- `-DskipTests` không tạo artifact bị thiếu.
- `-U` không thể tải thứ chưa được publish.
- Local repo mới vẫn fail nếu remote thực sự trả 404.
- Khi sửa GAV hoặc publisher publish artifact đúng quy trình, lỗi mới có thể biến mất.

Sau thí nghiệm, xóa **duy nhất fragment giả vừa thêm**, không xóa toàn `.m2` rồi gọi là đã sửa.

## 26. Thí nghiệm 4 — cached miss phải có bằng chứng remote đã tồn tại

Giả sử artifact đã publish nhưng Maven vẫn báo missing do update policy/negative cache. Trước khi thử phải xác nhận:
- Đúng artifact GAV/type/classifier.
- Đúng remote repository/mirror theo settings.
- Có quyền đọc, server trả artifact chứ không phải 401/403.
- Cùng POM, Maven/JDK, Git SHA và profiles.
- Không có SNAPSHOT bytes thay đổi giữa runs.

Thử riêng `-U` hoặc fresh local repo trong sandbox. Nếu vẫn 404 trên cùng remote, cần kiểm tra publisher/repository manager, không tiếp tục xóa file cache.

**Nếu hai lần chạy cách nhau một khoảng thời gian**, remote có thể vừa được publish; ghi timestamps và phiên bản được resolve để tránh kết luận quá chắc chắn.

## 27. `dependency:purge-local-repository` là thao tác xóa có giới hạn, không phải chẩn đoán mặc định

Maven Dependency Plugin có goal **`dependency:purge-local-repository`**. Tài liệu chính thức cho biết goal có thể xóa dependencies từ local repository rồi re-resolve; mặc định có thể ảnh hưởng transitive dependencies.

**Không chạy goal này vô điều kiện trên `.m2` dùng chung.** Nếu đã có bằng chứng một artifact cụ thể cần làm mới, hãy:
1. Thử fresh local repo trong sandbox trước.
2. Xác định GAV chính xác cần làm mới và nơi publish.
3. Đọc kỹ các tham số như `manualInclude`, `includes`, `resolutionFuzziness`, `reResolve`.
4. Chỉ thay những artifacts trong phạm vi được phép.
5. Ghi lại resolved artifact versions/digests trước và sau.

Ví dụ tên tham số để đọc tài liệu:

~~~text
-DmanualInclude=vn.example.library:pricing-api
-DreResolve=false
~~~

Đây là **tham số minh họa**, không phải lệnh phải chạy. Khi local repository chứa installed artifacts chưa publish hoặc có Maven jobs dùng chung, nguy cơ mất dữ liệu là thật.

## 28. Ma trận thí nghiệm để không đổi quá nhiều biến cùng lúc

| Biến | Baseline | Kiểm tra `-U` | Kiểm tra repo mới |
| --- | --- | --- | --- |
| Git source SHA | Giữ | Giữ | Giữ |
| Maven/JDK | Giữ | Giữ | Giữ |
| POM/settings/profiles | Giữ | Giữ | Giữ |
| Maven goals | `verify` | `verify` | `verify` |
| Update policy flag | Không | **Có `-U`** | Không |
| Local repo path | Hiện tại | Hiện tại | **Mới, sandbox** |
| Remote mirror | Giữ | Giữ | Giữ |
| Kết quả | Ghi error | Ghi error | Ghi error |

Một thay đổi ở mỗi phép thử giúp kiểm tra dự đoán. Nếu bạn cùng lúc thay Maven version, JDK, POM, mirror, code, local repo và skip tests, không thể biết yếu tố nào giải quyết lỗi.

**Kết luận “không xác định” cũng có giá trị** nếu logs không đủ hoặc server thay đổi giữa runs. Đừng ép mọi thí nghiệm ra một nguyên nhân chắc chắn khi dữ liệu chưa cho phép.

## 29. Cách đọc CI cache so với Maven local cache

Trong CI, một build thường được chạy từ checkout mới nhưng có **dependency cache restore**. Nếu cache key chỉ theo branch mà không theo toolchain/settings, một cache có thể chứa artifacts từ điều kiện khác.

Khi nghi CI cache gây lỗi:
- Chốt Git SHA và Maven/JDK/env trước.
- So build với và không restore cache **trên job sandbox** được phép.
- Không đổi POM hoặc skip checks trong lần so.
- Đọc dependency resolution logs và selected artifact versions.
- Nếu only cache-backed run fails, kiểm tra cache key, corruption, concurrency và repository manager.
- Sửa cache policy rồi chạy full gate.

**Không flush repository manager cache dùng chung** khi chưa có quyền và không có bằng chứng lỗi upstream; đó là thao tác ảnh hưởng nhiều dự án, khác hẳn thử local repo riêng.

## 30. Một case thực tế hơn: test flaky mà cache không liên quan

Giả sử test tính một deadline bằng `LocalDateTime.now()`, nhưng CI chạy timezone khác. Test FAIL theo thời điểm/region, rồi PASS khi rerun. Nếu bạn xóa cache giữa hai runs, có thể **ngộ nhận cache là nguyên nhân**, trong khi chỉ có thời gian thay đổi.

Giả thuyết đúng phải dự đoán:
- Với fixed clock/timezone, test ổn định.
- Với timezone khác, một assertion cụ thể thay đổi.
- Với same JDK/deps/cache nhưng retry theo thời gian, lỗi có thể biến động.

Giải pháp là **inject Clock**, chốt timezone hoặc sửa contract test, không xóa `.m2`. Với parallel tests, kiểm tra shared state/order/resource contention. Nếu Surefire ghi Flakes, coi đó là debt cần xử lý.

## 31. Khi nào “BUILD SUCCESS” là bằng chứng đủ mạnh?

Chỉ khi bạn biết **chính xác các goals, profiles và test gates đã chạy**.

Một câu kết luận tốt:

~~~text
Git SHA: [SHA thực tế]
Maven/JDK: [mvn --version thực tế]
Command: mvn -B -ntp clean verify
Test suites: [tên + số tests thực chạy]
Skipped tests: 0 (nếu reports xác nhận)
Artifacts: [GAV và path thực tế]
Checksum: [digest SHA-256 tính từ file]
Result: PASS (sau khi chạy thật)
~~~

Các giá trị trong ngoặc là **chỗ điền bằng chứng**, không phải kết quả đã được thực thi trong bài. Không bịa version, Git SHA, artifact hash hoặc test count cho một repository chưa được chạy.

Ngược lại, nếu dùng:
- `mvn -DskipTests package`: báo **`PACKAGE/COMPILE DIAGNOSTIC PASS; TESTS NOT RUN`**.
- `mvn -o verify`: báo chỉ phạm vi offline và local artifacts.
- `mvn -pl :service verify`: báo chỉ selected reactor scope.
- Surefire rerun PASS sau fail: ghi flaky/retries, không gọi deterministic clean pass.

## 32. Quy trình ra quyết định khi lỗi không giải quyết được ngay

~~~text
1. Có lỗi XML/POM model?
   -> Đọc line/column và sửa cấu trúc trước.
2. Có parent/BOM/dependency/plugin resolution failure?
   -> GAV + mirror/credentials/HTTP status.
   -> Chỉ nếu remote tồn tại và nghi negative cache: thử -U/fresh repo.
3. Có Enforcer/Compiler failure?
   -> JDK/toolchains/source/classpath, không skip test.
4. Có Surefire/Failsafe failure?
   -> Reports, expected/actual, fixture, flaky/env.
   -> Rerun test chọn lọc để cô lập, sau đó full suite.
5. Có packaging/runtime failure?
   -> Manifest, Jar/Assembly/Shade và actual artifact.
6. Chỉ CI fail?
   -> So SHA/JDK/settings/profile/OS/cache key.
7. Đã sửa nguyên nhân?
   -> Chạy đầy đủ clean verify trên runner được phép.
   -> Ghi logs, test count, artifact checksum và quyết định.
~~~

Sơ đồ này là **chuỗi ưu tiên**, không phải một script tự động chạy `clean`/`deploy`. Cần áp dụng theo loại lỗi thực tế. Không có cách “một lệnh sửa mọi lỗi” đáng tin.

## 33. Mẫu bug report theo giả thuyết

~~~text
Incident: ShippingQuote unit test fails after one-line change
Repository / Git SHA: [điền thực tế]
Working tree: [mô tả thực tế]
Command: mvn -B -ntp clean verify
Maven/JDK: [mvn --version thực tế]
First failed goal: maven-surefire-plugin:test
Test: ShippingQuoteTest.totalIncludesShipping
Expected/actual: 135 / 136
Hypothesis: source cộng thêm 1 vào shipping
Prediction: khôi phục Math.addExact(subtotal,shipping) -> PASS
Test plan: sửa một dòng trong sandbox, chạy lại verify
Observed result: [ghi sau khi chạy]
Verification: [full suite/test counts/artifact digest]
Status: [FIXED / NOT FIXED / INCONCLUSIVE]
~~~

Đây là **mẫu điền thông tin**, không khẳng định đã chạy Maven trong một repository thật. Không đưa secrets, full settings file hoặc raw debug logs chứa credential vào issue public.

Một báo cáo “giả thuyết bị bác bỏ” vẫn hữu ích: “fresh repo cũng nhận 403 từ corporate mirror; cached-miss hypothesis không giải thích được lỗi, cần kiểm tra token scope”. Cần phân biệt **observed facts** với **interpretation**.

## 34. Những anti-pattern nên loại khỏi quy trình

1. **Xóa toàn `~/.m2` vì một test fail.** Test assertions thường không do dependency cache.
2. **Thêm `-U` vào mọi lệnh.** Có thể tải SNAPSHOT mới và đổi input build.
3. **Đổi đồng thời Maven, JDK, POM, mirror và test flags.** Không còn phép thử có đối chứng.
4. **`-DskipTests` rồi báo tests pass.** Chỉ bỏ qua checks.
5. **`-Dmaven.test.skip=true` như một cách “test nhanh”.** Nó có thể bỏ cả test compilation.
6. **`-o` fail rồi gọi cache corrupt.** Có thể chỉ thiếu dependency local.
7. **Xóa `.lastUpdated` hàng loạt.** Không sửa GAV/remote 404/auth.
8. **Bỏ corporate mirror để bypass 403.** Có thể vi phạm policy bảo mật.
9. **Dùng `mvn deploy` để thử.** Deploy có thể ghi remote repository.
10. **Xóa `target/`/workspace chung không kiểm tra Clean Plugin.** Có nguy cơ mất artifacts/dữ liệu.
11. **Tăng `rerunFailingTestsCount` để che flaky bug.** Flakes còn tồn tại.
12. **Chạy test đơn lẻ rồi tuyên bố full reactor PASS.** Phải chạy required goals trên phạm vi chính thức.
13. **Đánh giá chỉ từ cuối console.** Cần goal, error và root-cause trace.
14. **Chọn giả thuyết sau khi thấy kết quả** mà không nêu dự đoán. Dễ thiên lệch xác nhận.

## 35. Bài tập tự kiểm tra

**Bài 1:** Một test trả 136 thay vì 135. Viết hai giả thuyết và một phép thử bác bỏ giả thuyết cache hỏng.

**Bài 2:** Tạo project Java/JUnit mục 21, chạy `mvn clean verify`, kiểm tra 3 unit tests và JAR in `TOTAL: 135 VND`.

**Bài 3:** Sửa lỗi có chủ đích ở mục 23, chạy test; so `mvn verify` và `mvn -DskipTests package`. Khi nào được gọi “full verification PASS”?

**Bài 4:** Phân biệt local `.m2/repository`, `target/`, IDE cache và CI cache. Cho mỗi loại một tín hiệu lỗi và một phép thử phù hợp.

**Bài 5:** Artifact vừa publish nhưng Maven báo cached 404. Viết H0/H1, dự đoán `-U` và fresh repo sẽ cho kết quả nào.

**Bài 6:** CI báo 403 với company mirror. Vì sao `-U`/fresh `.m2` không tự cấp quyền? Những trường nào nên gửi repository admin?

**Bài 7:** Một project dùng Java API 21 nhưng Maven chạy JDK 17. Lệnh nào cung cấp bằng chứng? Phải sửa JDK/toolchain hay xóa dependency?

**Bài 8:** Một test flake 1/10 runs. Thiết kế phép thử kiểm soát clock, seed, execution order và parallelism.

**Bài 9:** Reactor `api` fail làm `service` SKIPPED. Khi nào dùng `-pl :api -am verify`, khi nào vẫn cần root clean verify?

**Bài 10:** Viết bug report gồm environment, evidence, hypothesis, prediction, experiment, result, limitation và full verification status.

## 36. Checklist kết thúc một lần chẩn đoán Maven

1. Đã ghi đúng source SHA và working tree state.
2. Đã ghi exact Maven goals, JDK/Maven versions và module.
3. Đã xác định phase/goal đầu tiên thất bại.
4. Đã đọc exception/HTTP status/expected-actual thực.
5. Đã phân loại model, resolution, compile, test hoặc packaging.
6. Đã đưa ra ít nhất một giả thuyết có thể bác bỏ.
7. Đã dự đoán kết quả trước phép thử.
8. Đã thay đổi một yếu tố trong sandbox.
9. Không xóa cache hoặc dữ liệu không thuộc quyền.
10. Nếu nghi cached 404, đã kiểm tra remote GAV/repository.
11. Nếu dùng `-U`, đã ghi khác biệt resolution/snapshot.
12. Nếu dùng fresh repo, đã giữ JDK/POM/profiles không đổi.
13. Nếu dùng skip flag, ghi **partial diagnostic**, không “tests PASS”.
14. Nếu có flaky tests, đã ghi số lần rerun và điều kiện.
15. Nếu có CI-only failure, đã so source/JDK/settings/cache policy.
16. Sau fix, đã chạy required `mvn clean verify` với flags được duyệt.
17. Đã kiểm tra số tests chạy và skipped counts.
18. Đã xác minh artifact cuối khi project yêu cầu.
19. Đã lưu checksum/evidence nếu thuộc release workflow.
20. Đã giải thích root cause, cách xác minh và giới hạn kết luận.

### Tổng kết

**Đừng coi cache là nguyên nhân mặc định chỉ vì Maven đỏ.** Maven local repository, `target`, IDE caches và CI repository-manager caches là những lớp khác nhau. `-U` có phạm vi cập nhật nhất định; `-o` chỉ chạy offline; `-DskipTests` và `-Dmaven.test.skip=true` bỏ bớt checks chứ không sửa source.

Một quá trình chẩn đoán tốt phải **ghi bằng chứng → đặt giả thuyết → dự đoán kết quả → kiểm tra một biến → sửa nguyên nhân → chạy full verification**. Nếu nghi cache thật, dùng local repo mới trong sandbox hoặc refresh có kiểm soát sau khi xác minh artifact remote; không xóa hàng loạt dữ liệu chung. Nếu test fail, đọc Surefire/Failsafe reports và xử lý behavior/fixture/environment, không ngụy trang bằng một build skipped tests.

**Kết quả cuối cùng có giá trị là nguyên nhân có bằng chứng và việc CI/Maven required gates đã được chạy lại**, không chỉ một dòng `BUILD SUCCESS` sau khi thay quá nhiều thứ cùng lúc.

### Tài liệu chính thức

- [Apache Maven — CLI Options Reference](https://maven.apache.org/ref/3-LATEST/maven-embedder/cli.html)
- [Apache Maven — Local Repositories](https://maven.apache.org/repositories/local.html)
- [Apache Maven Resolver — Error Handling and Caching](https://maven.apache.org/resolver/local-repository.html)
- [Apache Maven — Mirrors](https://maven.apache.org/guides/mini/guide-mirror-settings.html)
- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Maven Surefire Plugin — Skipping Tests](https://maven.apache.org/surefire/maven-surefire-plugin/examples/skipping-tests.html)
- [Maven Surefire Plugin — Rerun Failing Tests](https://maven.apache.org/surefire/maven-surefire-plugin/examples/rerun-failing-tests.html)
- [Maven Failsafe Plugin — Skipping Tests](https://maven.apache.org/surefire/maven-failsafe-plugin/examples/skipping-tests.html)
- [Maven Dependency Plugin — Dependency Tree](https://maven.apache.org/plugins/maven-dependency-plugin/examples/tree-mojo.html)
- [Maven Dependency Plugin — Purging Local Repository](https://maven.apache.org/plugins/maven-dependency-plugin/examples/purging-local-repository.html)
- [Maven Enforcer Plugin — Introduction](https://maven.apache.org/enforcer/maven-enforcer-plugin/)

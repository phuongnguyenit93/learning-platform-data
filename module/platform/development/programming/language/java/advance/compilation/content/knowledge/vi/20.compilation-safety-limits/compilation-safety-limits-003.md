# Chỉ cho phép processor, plugin và phụ thuộc có nguồn tin cậy

## 1. Vì sao đây là một ranh giới an toàn của Java compilation?

Biên dịch Java không chỉ đọc file nguồn rồi phát sinh bytecode. Một build thực tế có thể **thực thi chương trình của bên thứ ba trước cả khi ứng dụng chạy**:

- **Annotation processor** (JSR 269) chạy bên trong hoặc cùng tiến trình biên dịch để phân tích annotation và tạo mã, tài nguyên hay chẩn đoán.
- **Compiler plugin** có thể gắn vào pipeline biên dịch, can thiệp vào cây cú pháp, kiểm tra hoặc sinh bytecode. Một số plugin sử dụng API nội bộ của compiler.
- **Gradle/Maven build plugin**, script, task và công cụ sinh mã chạy trong quá trình cấu hình hay thực thi build; quyền của chúng thường tương ứng với quyền của tài khoản đang chạy build.
- **Phụ thuộc thư viện** thường chỉ nằm trên classpath để compiler đọc, nhưng cần phân biệt thư viện dùng bởi chương trình với thư viện được tải và *thực thi* bởi processor/plugin/task. Plugin và processor còn có thể mang dependency bắc cầu do chính chúng sử dụng.

Một processor có khả năng truy cập file, biến môi trường, system properties, mạng và những quyền mà hệ điều hành cấp cho tiến trình. Một Gradle plugin có thể chạy mã khi cấu hình dự án, ngay cả trước khi task biên dịch bắt đầu. Vì vậy, “chỉ compile, chưa run ứng dụng” **không phải ranh giới an toàn**.

Ví dụ: nếu CI cung cấp token phát hành artifact, một processor hoặc plugin không tin cậy chạy trong build có thể đọc thông tin mà token đó cho phép truy cập. Việc mã nguồn ứng dụng không gọi processor trực tiếp không hạn chế những tác động này.

**Mục tiêu:** chỉ đưa nguồn mã và công cụ đã được thẩm định vào những classpath/thời điểm **có quyền thực thi**, cố định và xác minh đúng artifact đã phê duyệt, giảm quyền của build, đồng thời có cơ chế phát hiện và xử lý dependency bất thường.

## 2. “Có nguồn tin cậy” nghĩa là gì?

Không có thuộc tính duy nhất như “được tải từ Maven Central” đủ chứng minh mọi phiên bản artifact là an toàn. Cần kết hợp nhiều yếu tố:

| Câu hỏi cần trả lời | Bằng chứng/biện pháp phù hợp |
|---|---|
| **Ai phát hành?** | Chủ dự án, repository chính thức, tổ chức/nhà phát hành được duyệt; kiểm tra định danh và lịch sử dự án |
| **Đúng artifact đã phê duyệt?** | Group/artifact/version, checksum hoặc chữ ký xác minh; metadata verification được review |
| **Có thể bị thay đổi bất ngờ không?** | Phiên bản cụ thể, version locking, tránh dynamic version và SNAPSHOT trong đường phát hành cần kiểm soát |
| **Dependency kéo thêm gì?** | Xem dependency graph và artifact bắc cầu, gồm runtime của processor/plugin |
| **Có quyền thực thi gì?** | Processor path, compiler plugin, buildscript/plugin classpath, CI credentials, network/file access |
| **Đã được đánh giá rủi ro?** | Báo cáo lỗ hổng, thông báo bảo mật, changelog, cập nhật có kiểm thử, chính sách license nếu tổ chức yêu cầu |
| **Có thể truy vết và khôi phục?** | Lockfile, build manifest/SBOM, log thay đổi, quy trình nâng version, khả năng rollback |

**Tính toàn vẹn khác với mức độ đáng tin:** checksum cho biết artifact hiện tại khớp byte đã ghi nhận; nếu checksum được tạo từ chính artifact độc hại mà chưa có bước thẩm định, checksum vẫn “đúng” nhưng không chứng minh artifact an toàn. Chữ ký cũng phải gắn với **khóa và danh tính nhà phát hành đã tin cậy**, không chỉ là “có chữ ký”.

Một thư viện có tên gần giống tên chính thức có thể là *typosquatting*. Tránh dựa vào độ phổ biến, lượt tải, logo, hoặc đường dẫn được gửi trong pull request như bằng chứng duy nhất.

## 3. Phân loại phụ thuộc theo khả năng thực thi

Cần trả lời “dependency này đi vào đâu?” trước khi thêm nó vào build.

| Vị trí | Vai trò | Rủi ro đặc trưng |
|---|---|---|
| `implementation` / `api` | Tham gia compile/runtime của ứng dụng | Mã thường không chạy trong compilation chỉ vì nằm trên classpath; vẫn có rủi ro ở runtime và build tooling nếu được nạp |
| `compileOnly` | Có cho compiler kiểm tra kiểu; không đóng gói làm runtime dependency theo cấu hình Java thông thường | Thiếu runtime nếu ứng dụng cần sử dụng class đó khi chạy |
| `annotationProcessor` của Gradle | Tập hợp processor và các dependency cần để processor hoạt động | Có quyền thực thi khi JavaCompile chạy |
| `plugins { ... }` | Gradle plugin được áp dụng trong build | Có thể chạy mã ở thời điểm cấu hình, trước compilation |
| `buildscript { dependencies { classpath ... } }` | Công cụ dùng bởi buildscript/legacy plugins | Có khả năng thực thi từ logic build |
| Công cụ do task `Exec`/`JavaExec` gọi | Compiler ngoài, generator, linter, schema tool | Quyền tương ứng tiến trình được spawn; có thể ghi file/gọi mạng |
| `testRuntimeOnly` / `testImplementation` | Mã được test runtime sử dụng | Code của bên thứ ba được thực thi khi chạy test |

**Phân tách annotation API với processor implementation** là một bước quan trọng. Source thường chỉ cần annotation type để biên dịch; implementation của processor phải đặt trên `annotationProcessor`, không “nhét” processor vào `implementation` theo thói quen. Điều này làm classpath rõ ràng hơn và giúp giảm khả năng processor bị kích hoạt ngầm từ compile classpath.

Trên các bản JDK mới, hành vi discovery mặc định của `javac` có thể thay đổi; thiết lập processor tường minh qua công cụ build là cách dễ kiểm soát hơn so với mong đợi mọi processor trên classpath tự chạy.

## 4. Ví dụ Java 17 với processor được chỉ định rõ

Ví dụ sử dụng **AutoValue 1.11.0** như một tọa độ dependency cụ thể để minh họa kỹ thuật. Việc nêu tọa độ này **không có nghĩa phiên bản hay artifact đó đã được tổ chức thẩm định**. Trước khi dùng trong hệ thống thật, cần tự xác minh đúng nguồn phát hành, dependency bắc cầu, checksum, lỗ hổng và chính sách cho phép của dự án.

Giả sử cấu trúc:

~~~text
trusted-processor-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/
    ├── Person.java
    └── App.java
~~~

Dự án sử dụng **Gradle Wrapper đã được dự án quản lý** và JDK 17+; hãy kiểm tra và cố định phiên bản Gradle Wrapper phù hợp. Không copy URL wrapper lạ hoặc script “cài Gradle” không được review.

### 4.1. Tập trung nguồn repository tại settings.gradle

File `settings.gradle` (Groovy DSL):

~~~groovy
import org.gradle.api.initialization.resolve.RepositoriesMode

pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
    }
}

rootProject.name = "trusted-processor-demo"
~~~

Ở đây, `RepositoriesMode.FAIL_ON_PROJECT_REPOS` làm build thất bại khi project cố khai báo repository riêng (ví dụ một URL được chèn vào `build.gradle`). Đây là **kiểm soát nguồn resolution**: build chỉ dùng repository được cấu hình tập trung cho dependencies thông thường. `pluginManagement.repositories` điều khiển nơi tìm **plugin**; repository cho plugin và repository cho module dependencies là hai phạm vi khác nhau.

Cấu hình trên chỉ là **mức khởi đầu**. Các cơ chế resolution bổ sung như `buildscript`, included builds, init scripts, local repositories hoặc repository nội bộ của tổ chức cần có chính sách riêng tương ứng. Chỉ đặt `mavenCentral()` không tự động tạo allowlist cho **mọi artifact** từ Maven Central.

### 4.2. Đưa processor vào classpath phù hợp

File `build.gradle`:

~~~groovy
plugins {
    id "java"
}

dependencies {
    compileOnly "com.google.auto.value:auto-value-annotations:1.11.0"
    annotationProcessor "com.google.auto.value:auto-value:1.11.0"
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

`java` ở đây là plugin tích hợp của Gradle, không phải plugin bên ngoài cần tải từ plugin portal. Annotation API được dùng khi compile source; annotation processor được cấp cho compiler qua configuration chuyên dụng. Hai dependency dùng version cụ thể, nhưng **version cố định chỉ hạn chế thay đổi ngoài ý muốn, chưa xác minh nội dung artifact**.

Nếu một module có processor khác, đừng chỉ sao chép tọa độ từ blog. Kiểm tra tên group/artifact trong tài liệu nguồn đã duyệt; kiểm tra phiên bản processor tương thích JDK và compiler, cùng mọi dependency bắc cầu mà nó tải về.

### 4.3. Consumer buộc generated code phải dùng được

File `src/main/java/example/Person.java`:

~~~java
package example;

import com.google.auto.value.AutoValue;

@AutoValue
public abstract class Person {
    public abstract String name();

    public static Person of(String name) {
        return new AutoValue_Person(name);
    }
}
~~~

File `src/main/java/example/App.java`:

~~~java
package example;

public final class App {
    public static void main(String[] args) {
        System.out.println(Person.of("An").name());
    }
}
~~~

Khi xử lý `@AutoValue`, processor sinh implementation `AutoValue_Person` trong package `example`. Lời gọi từ `Person.of` buộc compiler kiểm tra class sinh ra ngay trong quá trình build. Nếu processor không chạy và không có class cũ lọt vào output, compilation phải thất bại vì không tìm thấy `AutoValue_Person`.

Chạy từ root dự án với Gradle Wrapper đã thiết lập:

~~~bash
./gradlew clean classes
java -cp build/classes/java/main example.App
~~~

Trên Windows PowerShell, dùng `.\gradlew.bat clean classes`. Khi dependencies đã giải quyết thành công và processor chạy đúng, output **của lệnh java** là:

~~~text
An
~~~

Có thể xem source generated tại vị trí mặc định của Gradle Java plugin:

~~~text
build/generated/sources/annotationProcessor/java/main/example/AutoValue_Person.java
~~~

Đường dẫn này có thể đổi nếu build cấu hình lại thư mục sinh nguồn. **Không** tự thêm file generated cũ vào source directory hoặc vào version control để làm test có vẻ xanh. Mục tiêu là một compilation sạch thực sự chạy processor đã lựa chọn.

## 5. Khóa phiên bản và xác minh integrity bằng Gradle

### 5.1. Tránh version động

Các ví dụ như `1.+`, `latest.release` và version range cho phép build resolve ra artifact khác theo thời gian. Với processor/plugin có quyền thực thi, thay đổi ngoài kế hoạch đặc biệt nguy hiểm. Nên dùng version được review cụ thể, và quản lý nâng cấp qua pull request có người kiểm tra.

Khi cần khóa transitive dependency của configurations, Gradle hỗ trợ dependency locking. Ví dụ trong `build.gradle`:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Sau khi quyết định rõ danh sách dependency/version đã duyệt, có thể chạy trên bản build thử được kiểm soát:

~~~bash
./gradlew compileJava --write-locks
~~~

Lockfile được tạo từ **những configuration được resolve** trong lệnh tương ứng; cần chạy những task/configurations liên quan khi muốn khóa toàn bộ plugin/test/processor paths. Commit lockfiles phù hợp và review thay đổi lockfile trong từng lần nâng cấp. Locking ngăn tự ý đổi **version được resolve**, nhưng chưa xác minh checksum hoặc tin cậy nhà phát hành.

### 5.2. Dependency verification

Gradle hỗ trợ metadata xác minh checksum/chữ ký cho artifacts được resolve; file thường nằm tại `gradle/verification-metadata.xml`. Để **khởi tạo metadata kiểm tra trong môi trường có giám sát**, một lệnh minh họa là:

~~~bash
./gradlew --write-verification-metadata sha256 compileJava
~~~

Việc tự sinh metadata từ bytes tải về **không chứng minh nguồn an toàn**. Trước khi phê duyệt, so khớp artifact và SHA-256 với nguồn phát hành đáng tin cậy hoặc thông tin đã review độc lập; kiểm cả dependencies bắc cầu. Sau đó commit metadata đã được kiểm tra, chạy build bình thường trong CI để Gradle kiểm tra artifact theo policy. Cần hiểu rõ coverage và ngoại lệ verification của phiên bản Gradle đang dùng, đặc biệt với plugin resolution và những repository riêng.

Cũng không nên tin vào một cache nội bộ chỉ vì artifact tồn tại ở đó. Remote cache và repository proxy cần quy định quyền ghi, quy trình quarantine và audit; checksum đã chấp thuận phải được bảo toàn khi mirror artifact.

### 5.3. Kiểm tra dependency graph

Ở ví dụ trên, có thể xem configuration chứa processor:

~~~bash
./gradlew dependencies --configuration annotationProcessor
./gradlew dependencyInsight --configuration annotationProcessor --dependency auto-value
~~~

Kiểm tra artifacts bắc cầu chứ không chỉ dependency khai báo trực tiếp. Đối với build plugin, phải xem dependency và mã được plugin kéo vào trong thời điểm cấu hình. Không quyết định độ tin cậy chỉ qua việc output `dependencies` không có conflict.

## 6. Giới hạn repository và plugin theo chính sách tổ chức

Một chiến lược thực tế là duy trì tập nguồn được phê duyệt, ưu tiên proxy/mirror nội bộ có quy tắc chấp nhận artifact, cùng allowlist ở cấp group/module khi cần. Những điểm cần thiết:

1. **Tách plugin resolution và dependency resolution.** Thay đổi `repositories` trong project không nhất thiết kiểm soát nguồn của Gradle plugins.
2. **Không chấp nhận URL tùy ý từ PR.** Một repository lạ được thêm lên trước repository tin cậy có thể đưa vào artifact trùng tên hoặc thay thứ tự resolution.
3. **Cố định plugin IDs/versions được dùng.** Plugin DSL có thể resolve plugin marker và các artifact triển khai/bắc cầu; chúng cũng cần được thẩm định.
4. **Review init scripts, included builds và build logic.** Đoạn Groovy/Kotlin chạy trong Gradle build là executable code, kể cả khi không xuất hiện dưới dạng dependency trong `build.gradle`.
5. **Không chạy `curl ... | sh` hoặc tải compiler extension từ link ngắn.** Nếu cần cài công cụ, dùng bản phát hành xác minh được từ nguồn đã duyệt, kiểm checksum/chữ ký theo chính sách.
6. **Cấm phụ thuộc snapshot/dynamic trong pipeline release** trừ khi có cơ chế quản lý nguồn và định danh artifact rõ ràng.

Repository allowlist là một lớp giảm bề mặt tấn công, **không thay thế** review version, integrity verification hay kiểm tra provenance của từng artifact.

## 7. Chạy compilation với quyền tối thiểu

Khi processor/plugin có thể thực thi mã, lớp bảo vệ tiếp theo là giới hạn tác động ngay cả nếu một bản dependency bị xâm nhập.

| Tài nguyên | Kiểm soát khuyến nghị |
|---|---|
| **CI credentials** | Job compile/test thông thường không có token publish/deploy; cấp token ngắn hạn chỉ trong job cần phát hành |
| **File system** | Workspace cô lập, chỉ mount những tệp cần thiết; hạn chế vùng ghi ngoài build output/cache được phép |
| **Network** | Giới hạn egress khi phù hợp; fetch dependencies từ proxy được kiểm soát và tách giai đoạn tải khỏi giai đoạn thực thi khi có thể |
| **Build agents** | Dùng agent/VM/container dùng một lần cho PR không tin cậy; không chạy với quyền administrator/root nếu không cần |
| **Caches** | Phân quyền đọc/ghi remote cache; tránh để build không tin cậy ghi vào cache dùng cho release |
| **Secrets trong log/artifact** | Không in token, biến môi trường nhạy cảm hoặc nguyên nội dung file cấu hình; kiểm soát quyền truy cập logs/artifacts |
| **Workflow triggers** | Với PR từ nguồn chưa tin cậy, tránh workflow có quyền ghi/publish hoặc cung cấp secrets rồi thực thi build logic của PR |

**Quan trọng:** container, sandbox, offline mode hay repository verification không mang lại cách ly tuyệt đối nếu tài khoản build vẫn có đường đọc secrets hoặc mạng ra ngoài. Hãy thiết kế quyền theo khả năng thực tế của job. Đồng thời đừng mặc định “một dependency là thư viện bình thường thì không thể chạy khi build”: plugin/test runner/codegen task có thể nạp và thực thi mã đó.

Nếu phải chạy thử một processor không được phê duyệt để phân tích, thực hiện trong môi trường cô lập, dùng tài khoản không có dữ liệu/secrets sản xuất; đừng đưa nó thẳng vào CI phát hành.

## 8. Quy trình phê duyệt processor/plugin mới

Một quy trình có thể thực hiện lặp lại:

1. **Xác nhận nhu cầu:** processor/plugin giải quyết vấn đề nào? Có thể dùng cơ chế JDK/Gradle tích hợp để giảm mã bên thứ ba phải thực thi không?
2. **Xác nhận danh tính:** truy ngược tọa độ Maven/plugin ID đến trang phát hành và repository nguồn chính thức; kiểm người duy trì, lịch sử thay đổi và dấu hiệu takeover.
3. **Chọn đúng version:** kiểm release notes, Java/Gradle compatibility, lịch sử lỗ hổng và trạng thái hỗ trợ. Không tự chọn phiên bản “mới nhất” khi chưa kiểm thử.
4. **Đánh giá toàn cây dependency:** xem transitive artifacts, processor path và plugin implementation path; kiểm scope nào thực thi code.
5. **Xác minh provenance/integrity:** kiểm checksum/chữ ký theo kênh tin cậy; cập nhật verification metadata và lockfiles dưới review.
6. **Chạy thử trong môi trường ít quyền:** build sạch, test compilation và generated outputs, quan sát truy cập mạng/file bất thường khi có công cụ giám sát phù hợp.
7. **Review diff:** mọi thay đổi build scripts, plugin repositories, lockfiles, verification metadata, wrapper và source generator đều cần được xem xét.
8. **Phát hành theo quyền đã định:** chỉ CI job được duyệt mới có credentials publish; giám sát và ghi nhận thành phần build để xử lý sự cố.
9. **Nâng cấp theo chu kỳ:** theo dõi cảnh báo bảo mật, sửa lỗi, cập nhật có kiểm thử và có đường rollback.

Khi phát hiện artifact nghi ngờ, dừng việc dùng version đó, xác định build/job đã sử dụng, thu hồi token nếu có khả năng đã lộ, kiểm tra logs và outputs, làm sạch caches có liên quan rồi rebuild từ dependency đã xác minh. Không giải quyết sự cố chỉ bằng cách đổi version string trong source.

## 9. Những hiểu lầm dễ gây lỗ hổng

**“Maven Central hoặc Gradle Plugin Portal là nguồn đáng tin tuyệt đối.”** Chúng là cơ chế phân phối phổ biến, nhưng artifact vẫn có thể bị phát hành bởi tài khoản bị xâm nhập hoặc nhà xuất bản chưa được thẩm định. Cần kiểm danh tính và chính xác artifact.

**“Compile không chạy mã.”** Sai với annotation processors, compiler plugins, Gradle plugins, buildscript và công cụ code generation. Đây là lý do phải kiểm soát cả build-time dependencies.

**“Đã khóa version thì đủ.”** Lockfile xác định versions, không tự bảo vệ trước artifact bị thay byte ở cùng tọa độ hoặc việc đưa vào version độc hại đã được khóa. Cần integrity/provenance và review.

**“Checksum khớp thì artifact an toàn.”** Checksum chỉ xác nhận artifact khớp bytes đã chấp thuận; nếu bytes được chấp thuận từ nguồn chưa kiểm tra, bước trust vẫn thiếu.

**“Thêm processor vào implementation luôn tương đương annotationProcessor.”** Không. Hai configuration có ý nghĩa khác nhau; cần đặt processor vào nơi compiler tìm và thực thi nó, trong khi không đưa implementation của processor vào runtime ứng dụng một cách không cần thiết.

**“Dùng `--offline` sẽ làm processor an toàn.”** Offline hạn chế tải mới qua Gradle nhưng không ngăn mã độc đã nằm trên classpath đọc file hoặc thực hiện hành động khác mà môi trường cho phép.

**“Chỉ PR phát hành mới cần quyền tối thiểu.”** Một PR thông thường vẫn có thể thay build logic hoặc compiler plugin. Nên tránh cấp secrets/permission cao cho job kiểm tra PR không tin cậy.

**“Pass unit test chứng tỏ processor an toàn.”** Test xanh chứng minh một số hành vi mong đợi, không chứng minh không có thao tác ngoài ý muốn hoặc không truy xuất dữ liệu nhạy cảm. Cần kiểm soát nguồn, quyền và đánh giá bảo mật.

## 10. Checklist trước khi đưa công cụ biên dịch bên thứ ba vào dự án

- [ ] Đã xác minh nhà phát hành và tọa độ chính xác của processor/plugin và các dependency trực tiếp/bắc cầu.
- [ ] Mọi phiên bản được pin/lock theo chính sách; không có dynamic version/SNAPSHOT ngoài ngoại lệ được phê duyệt.
- [ ] Artifact integrity và provenance được kiểm tra độc lập; verification metadata được review, không chấp thuận tự động vô điều kiện.
- [ ] Plugin repositories, dependency repositories, included builds, init scripts và tool installers nằm trong phạm vi quản lý.
- [ ] `annotationProcessor` tách khỏi `compileOnly`/`implementation`; không đưa code có quyền thực thi vào classpath sai mục đích.
- [ ] Có fixture biên dịch và sử dụng mã sinh thật, trên JDK/toolchain và classpath dự kiến; output build sạch.
- [ ] CI build/test chạy với quyền tối thiểu, không có secrets phát hành; PR không tin cậy dùng môi trường cô lập.
- [ ] Quyền ghi repository/cache/artifact được giới hạn; logs và generated outputs không chứa dữ liệu bí mật.
- [ ] Các lần cập nhật dependency đi qua review, kiểm tra lỗ hổng, test và có quy trình rollback/incident response.

**Nguyên tắc cuối:** với Java compilation, processor và build plugin là **mã được thực thi trong môi trường xây dựng phần mềm**. Chỉ cho phép công cụ có nguồn đã được thẩm định, ràng buộc đúng artifact và phiên bản, giới hạn quyền của tiến trình build, và kiểm tra kết quả sinh mã trong một build sạch. Không có một công cụ kiểm tra đơn lẻ nào thay thế toàn bộ các lớp kiểm soát này.
